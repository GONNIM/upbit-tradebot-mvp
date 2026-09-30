"""
✅ WO-12 회귀: 서비스 기동 시 엔진 자동 재개 + 부팅 복원 보강 (2026-09-30)

원 결함:
- 엔진 자동 재개([AUTO-RESUME])와 마이그레이션이 대시보드 첫 접속 때만 실행 → 재시작 후 사람이
  접속할 때까지 손절 포함 매매 정지 (09-18 46분, 09-30 5·6분).
- 부팅 복원이 봇 주문만 읽어, 앱에서 산 포지션은 CRITICAL 후 첫 봉까지 약 8분 매도 평가 공백
  (09-30 18:02:07 KRW-JTO).

계획서 §4-1 여섯 케이스 + C7 두 케이스 (+ 복원 실패 시 CRITICAL 유지).

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_30_wo12_boot_resume -v
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_09_30_wo12"
TICKER = "KRW-JTO"
QTY = 1340.43626806


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo12_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self.notify = MagicMock(return_value=True)
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", self.notify),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(U)
        ensure_all_schemas(U)
        ensure_schema(U)
        import engine.boot_resume as br
        br._STATE.clear()
        self.br = br

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _notified(self, level):
        return [c for c in self.notify.call_args_list if c.args and c.args[0] == level]


# ─────────────────────────────────────────────────────────────
# §4-1 여섯 케이스
# ─────────────────────────────────────────────────────────────
class TestBootResume(_DbCase):

    def _set_status(self, running: bool, mode: str | None):
        from services.db import set_engine_status
        set_engine_status(U, running, last_mode=mode)

    def test_1_live_running_user_resumed_without_session(self):
        self._set_status(True, "LIVE")
        started = []
        res = self.br.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1_000_000.0),
                                      start=lambda uid: started.append(uid) or True)
        self.assertEqual(res, {U: "success"})
        self.assertEqual(started, [U])
        self.assertEqual(len(self._notified("INFO")), 1, "재개 성공 INFO 알림 1건")
        self.assertEqual(self.br.get_boot_resume_state(U)["result"], "success")

    def test_1b_default_start_uses_mode_live_not_session(self):
        """기본 start 경로가 engine_manager.start_engine(mode='LIVE') 를 부르는지 (세션 비의존)."""
        self._set_status(True, "LIVE")
        with patch("engine.engine_manager.engine_manager.start_engine", return_value=True) as se:
            self.br.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0))
        se.assert_called_once_with(U, test_mode=False, mode="LIVE")

    def test_2_verify_fail_no_start_critical_db_unchanged(self):
        from services.db import get_engine_status, get_last_engine_mode
        self._set_status(True, "LIVE")
        for reason in ("키 조회 실패: …", "운용자산 0"):
            self.notify.reset_mock()
            started = []
            res = self.br.boot_resume_all(users=[U], verify=lambda r=reason: (False, r, 0.0),
                                          start=lambda uid: started.append(uid) or True)
            self.assertEqual(res, {U: "fail"})
            self.assertEqual(started, [])
            self.assertEqual(len(self._notified("CRITICAL")), 1)
            self.assertTrue(get_engine_status(U), "DB 상태 무변경 (첫 접속 경로에 맡김)")
            self.assertEqual(get_last_engine_mode(U), "LIVE")

    def test_3_not_target_excluded(self):
        for running, mode in ((True, "TEST"), (False, "LIVE")):
            self._set_status(running, mode)
            started = []
            res = self.br.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0),
                                          start=lambda uid: started.append(uid) or True)
            self.assertEqual(res, {})
            self.assertEqual(started, [])

    def test_6_trading_paused_untouched_engine_resumed(self):
        from services.db import set_trading_paused, get_trading_paused
        self._set_status(True, "LIVE")
        set_trading_paused(U, True)
        res = self.br.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0), start=lambda uid: True)
        self.assertEqual(res, {U: "success"})
        self.assertTrue(get_trading_paused(U), "trading_paused 는 건드리지 않음")

    def test_migration_runs_at_boot_for_known_users(self):
        with patch("services.init_db.ensure_all_schemas") as eas:
            self.br.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0), start=lambda uid: True)
        eas.assert_called_with(U)


class TestEngineManagerStartLock(unittest.TestCase):
    """케이스 4·5: 두 경로(기동 재개·대시보드)가 겹쳐도 엔진 1개, Reconciler 카운트 1."""

    def setUp(self):
        from engine.engine_manager import EngineManager
        self.em = EngineManager()
        self.stop = threading.Event()
        self.internal_calls = 0

        def _fake_internal(user_id, tm, restart_count, captured_mode):
            self.internal_calls += 1
            time.sleep(0.05)  # 경쟁 창 넓히기
            t = threading.Thread(target=self.stop.wait, daemon=True)
            t.start()
            self.em._threads[user_id] = t
            self.em._engine_mode[user_id] = captured_mode
            return True

        self._patchers = [
            patch.object(self.em, "_start_engine_internal", side_effect=_fake_internal),
            patch("engine.engine_manager.get_reconciler", return_value=MagicMock()),
            patch("services.db.set_engine_status"),
            patch("engine.engine_manager.current_mode", side_effect=AssertionError("세션 모드 참조 금지")),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        self.stop.set()
        for p in self._patchers:
            p.stop()

    def test_4_second_path_skips_after_boot_resume(self):
        self.assertTrue(self.em.start_engine(U, test_mode=False, mode="LIVE"))
        with self.assertLogs("engine.engine_manager", level="INFO") as cm:
            self.assertFalse(self.em.start_engine(U, test_mode=False, mode="LIVE"))
        self.assertTrue(any("start_engine skip — 이미 실행 중" in m for m in cm.output))
        self.assertEqual(self.internal_calls, 1)
        self.assertEqual(self.em._live_engine_count, 1, "이미 실행 중이면 Reconciler 카운트 증가 금지")
        self.assertEqual(self.em.get_running_mode(U), "LIVE")

    def test_5_concurrent_calls_start_once(self):
        results = []
        ths = [threading.Thread(target=lambda: results.append(self.em.start_engine(U, test_mode=False, mode="LIVE")))
               for _ in range(2)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.internal_calls, 1)
        self.assertEqual(self.em._live_engine_count, 1)

    def test_mode_param_bypasses_session(self):
        # current_mode 는 AssertionError 로 막혀 있음 — mode 지정 시 호출되지 않아야 함
        self.assertTrue(self.em.start_engine(U, test_mode=False, mode="live"))
        self.assertEqual(self.em.get_running_mode(U), "LIVE")


class TestDashboardAutoResumeGuards(unittest.TestCase):
    def test_dashboard_skip_log_and_race_guard_present(self):
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)", src)
        self.assertIn('elif engine_manager.get_running_mode(user_id) == "LIVE":', src,
                      "동시 진입으로 start_engine=False 일 때 DB 를 '정지'로 정정하지 않음")

    def test_boot_script_mirrors_streamlit_run(self):
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        for s in ("_config._main_script_path", "bootstrap.load_config_options", "bootstrap.run(",
                  '"server_port"', '"server_address"', "boot_resume_all"):
            self.assertIn(s, src)


# ─────────────────────────────────────────────────────────────
# C7 부팅 복원 보강
# ─────────────────────────────────────────────────────────────
class _FakeEngine:
    def __init__(self, wallet_qty: float):
        from core.position_state import PositionState
        from core.strategy_engine import StrategyEngine
        self.trader = MagicMock()
        self.trader._coin_balance = MagicMock(return_value=wallet_qty)
        self.position = PositionState()
        self.user_id = U
        self.ticker = TICKER
        self.bar_count = 200
        # 첫 봉 [POSITION-SYNC] 와 같은 함수 그대로 사용
        self._reconcile_position_with_wallet = StrategyEngine._reconcile_position_with_wallet.__get__(self)


class TestBootSeedRecover(unittest.TestCase):

    def test_c7_no_bot_order_restores_from_upbit_avg_then_first_bar_skip(self):
        from engine.live_loop import _boot_seed_recover_from_wallet
        eng = _FakeEngine(QTY)
        with patch("services.db.get_position_entry_price", return_value=761.0), \
             patch("services.db.get_last_open_buy_order", return_value=None), \
             patch("services.notifier.send") as ns:
            with self.assertLogs("engine.live_loop", level="INFO") as cm:
                ok = _boot_seed_recover_from_wallet(eng, TICKER, U, QTY)
            self.assertTrue(ok)
            self.assertTrue(eng.position.has_position)
            self.assertEqual(eng.position.avg_price, 761.0)
            self.assertAlmostEqual(eng.position.qty, QTY)
            self.assertEqual(eng.position.entry_bar, 200, "첫 봉 복구와 같은 시점(워밍업 후 bar_count)")
            self.assertTrue(any(f"[BOOT-SEED] source=upbit_avg_buy_price entry=761.0 qty={QTY:.6f}" in m
                                for m in cm.output), cm.output)
            ns.assert_not_called()
            # 첫 봉: 같은 값 → "이미 일치 → 스킵" 1회
            with self.assertLogs("core.strategy_engine", level="INFO") as cm2:
                self.assertIsNone(eng._reconcile_position_with_wallet())
            self.assertTrue(any("[POSITION-SYNC] 이미 일치 → 스킵 (boot_seed source=upbit_avg_buy_price)" in m
                                for m in cm2.output))
            self.assertEqual(eng.position.avg_price, 761.0, "값 변경 없음")
            # 두 번째 봉부터는 스킵 로그 없음
            with self.assertNoLogs("core.strategy_engine", level="INFO"):
                eng._reconcile_position_with_wallet()

    def test_c7_wallet_zero_keeps_no_position_and_critical(self):
        from engine.live_loop import _boot_seed_recover_from_wallet
        eng = _FakeEngine(0.0)
        with patch("services.db.get_position_entry_price", return_value=761.0), \
             patch("services.db.get_last_open_buy_order", return_value=None), \
             patch("services.notifier.send") as ns:
            with self.assertLogs("engine.live_loop", level="CRITICAL") as cm:
                ok = _boot_seed_recover_from_wallet(eng, TICKER, U, QTY)
        self.assertFalse(ok)
        self.assertFalse(eng.position.has_position)
        self.assertTrue(any("DB 진입가 seed 실패" in m for m in cm.output))
        self.assertEqual(ns.call_args.args[0], "CRITICAL")

    def test_c7_no_price_source_keeps_existing_critical(self):
        from engine.live_loop import _boot_seed_recover_from_wallet
        eng = _FakeEngine(QTY)
        with patch("services.db.get_position_entry_price", return_value=None), \
             patch("services.db.get_last_open_buy_order", return_value=None), \
             patch("services.notifier.send") as ns:
            with self.assertLogs("engine.live_loop", level="CRITICAL"):
                self.assertFalse(_boot_seed_recover_from_wallet(eng, TICKER, U, QTY))
        self.assertFalse(eng.position.has_position)
        self.assertIn("포지션 seed 실패", ns.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
