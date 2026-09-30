"""
✅ WO-10 회귀: HTS 감지 잔여 결함 + 표시·로그 문구 (2026-09-30)

- B1: 봇 매수 주문이 orders 에 REQUESTED 로 있는 동안 잔고가 먼저 늘어도 HTS 로 기록하지 않음
      (2026-06-18~07-03 id 212/225/259/396 유형 — 07-03 19347ac SP-PI-3 로 해소, 테스트로 봉쇄)
- B2: 증가량 원화 환산이 5,000원 미만이면 HTS 감지 제외 (2026-09-11 id 990, Δ=9e-8 → Trailing 리셋)
      기준가 순서: 잔고 응답 avg_buy_price → 현재가(최근 체결가) → 없으면 기존대로 감지
- B4: 현재가 매수 알림 "다음 봉 (~N초)" → "약 M분 뒤", 설정 도움말 1분봉 예시 → 실제 봉 간격
- (d) 첫 봉 방어 로그에서 "CRITICAL" 단어 제거 + [POS-DESYNC] class= 분류 로그
- (d) _safe_alter 마이그레이션 성공 시 "[migrate] <함수명> OK (user_id=...)" (프로세스당 1회)

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_30_wo10_hts_residuals -v
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

USER = "test_r_2026_09_30_wo10"
TICKER = "KRW-JTO"


def _bal(avail: float, locked: float = 0.0, avg: float = 566.88820298) -> list[dict]:
    return [
        {"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0"},
        {"currency": "JTO", "balance": repr(avail), "locked": repr(locked), "avg_buy_price": repr(avg)},
    ]


class _FakeEngine:
    def __init__(self):
        from core.position_state import PositionState
        self.position = PositionState()
        self._execution_lock = threading.Lock()
        self.bar_count = 100
        self.ticker = TICKER


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo10_"))
        self.db_path = str(self.tmpdir / f"tradebot_{USER}.db")
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
        initialize_db(USER)
        ensure_all_schemas(USER)
        ensure_schema(USER)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _hts_rows(self):
        with sqlite3.connect(self.db_path) as c:
            return c.execute(
                "SELECT reason, price FROM audit_trades WHERE type='BUY' AND reason IN ('HTS_BUY','HTS_BUY_ADD') ORDER BY id"
            ).fetchall()


class TestHtsDetectResiduals(_DbCase):

    def setUp(self):
        super().setUp()
        from engine.order_reconciler import OrderReconciler
        from core.strategy_engine import StrategyEngine
        self.upbit = MagicMock()
        self.or_ = OrderReconciler(self.upbit, balance_sync_interval=0.0)
        self.or_._live_user_ids.add(USER)
        self.engine = _FakeEngine()
        pos = self.engine.position
        pos.avg_price, pos.qty, pos.entry_bar = 566.88820298, 895.47356476, 50
        pos.highest_price = pos.highest_since_entry = 580.0
        pos.trailing_armed, pos.trailing_fixed_amount, pos.trailing_activation_price = True, 5.0, 575.0
        self.calls = []

        def _cb(**kw):
            self.calls.append(kw)
            StrategyEngine._on_hts_detect(self.engine, **kw)

        self.or_.register_hts_detect_callback(USER, TICKER, _cb)

    def _seed(self, avail, locked=0.0, ep=566.88820298):
        from services.db import update_coin_position
        update_coin_position(USER, TICKER, avail, locked, entry_price=ep)

    def _sync(self, avail, locked=0.0, avg=566.88820298, current_price=None):
        self.upbit.get_balances.return_value = _bal(avail, locked, avg)
        self.or_._last_balance_sync = 0.0
        with patch.object(type(self.or_), "_current_price", staticmethod(lambda t: current_price)):
            self.or_._periodic_balance_sync()

    def _trailing_intact(self):
        p = self.engine.position
        self.assertTrue(p.trailing_armed)
        self.assertEqual(p.highest_price, 580.0)

    # ── B1 ──
    def test_b1_pending_bot_buy_order_blocks_hts_marking(self):
        from services.db import insert_order
        self._seed(0.0, 0.0, ep=0.0)
        insert_order(USER, TICKER, "BUY", 767.0, 0.0, "requested", state="REQUESTED",
                     provider_uuid="uuid-bot-limit", requested_at="2026-06-18T09:21:05+09:00")
        # 잔고가 봇 체결 기록보다 먼저 늘어난 상황 (id 212 유형: 3.6초 선행)
        self._sync(357.27582218, 0.0, avg=1123.0)
        self.assertEqual(self._hts_rows(), [], "봇 매수 대기 중 잔고 증가는 HTS 로 기록하지 않음")
        self.assertEqual(self.calls, [])

    # ── B2 ──
    def test_b2_dust_delta_ignored_trailing_kept(self):
        """id 990 재현: 895.47356476 → 895.47356485 (Δ=9e-8, ≈0.00005원)."""
        self._seed(895.47356476)
        self._sync(895.47356485)
        self.assertEqual(self._hts_rows(), [])
        self.assertEqual(self.calls, [], "Trailing 리셋 경로(HTS_BUY_ADD 콜백) 진입 금지")
        self._trailing_intact()

    def test_b2_just_below_threshold_ignored(self):
        self._seed(100.0, ep=1000.0)
        self._sync(100.0 + 4.999, avg=1000.0)   # 4,999원
        self.assertEqual(self._hts_rows(), [])

    def test_b2_at_threshold_detected(self):
        self._seed(100.0, ep=1000.0)
        self._sync(105.0, avg=1000.0)           # 5,000원
        self.assertEqual(self._hts_rows(), [("HTS_BUY_ADD", 1000.0)])

    def test_b2_first_detection_uses_balance_avg_price(self):
        """보유 0 → 첫 감지(HTS_BUY): 잔고 응답 avg_buy_price 로 환산."""
        self._seed(0.0, ep=0.0)
        self._sync(6.0, avg=1000.0, current_price=1.0)   # avg 기준 6,000원 → 감지 (현재가 1원이면 6원이지만 무시)
        self.assertEqual(self._hts_rows(), [("HTS_BUY", 1000.0)])

    def test_b2_avg_zero_falls_back_to_current_price(self):
        """avg_buy_price=0 → 현재가(최근 체결가)로 환산."""
        self._seed(0.0, ep=0.0)
        self._sync(6.0, avg=0.0, current_price=500.0)    # 3,000원 → 제외
        self.assertEqual(self._hts_rows(), [])
        self._seed(0.0, ep=0.0)
        self._sync(12.0, avg=0.0, current_price=500.0)   # 6,000원 → 감지
        self.assertEqual([r[0] for r in self._hts_rows()], ["HTS_BUY"])

    def test_b2_no_price_available_keeps_detection(self):
        """기준가를 전혀 얻지 못하면 기존대로 감지 (실제 매수를 놓치지 않음)."""
        self._seed(0.0, ep=0.0)
        self._sync(0.001, avg=0.0, current_price=None)
        self.assertEqual([r[0] for r in self._hts_rows()], ["HTS_BUY"])

    def test_b2_basis_order_unit(self):
        o = self.or_
        with patch.object(type(o), "_current_price", staticmethod(lambda t: 500.0)):
            self.assertEqual(o._hts_delta_krw(TICKER, 2.0, 1000.0), (2000.0, "avg_buy_price"))
            self.assertEqual(o._hts_delta_krw(TICKER, 2.0, 0.0), (1000.0, "current_price"))
        with patch.object(type(o), "_current_price", staticmethod(lambda t: None)):
            self.assertEqual(o._hts_delta_krw(TICKER, 2.0, 0.0), (None, "unknown"))


class TestMigrateOkLog(_DbCase):

    def test_migrate_ok_logged_once_per_function_user(self):
        import services.init_db as idb
        idb._MIGRATE_OK_LOGGED.clear()
        with self.assertLogs("services.init_db", level="INFO") as cm:
            idb.ensure_all_schemas(USER)
            idb.ensure_all_schemas(USER)
        oks = [m for m in cm.output if "ensure_audit_trades_reject_columns OK" in m]
        self.assertEqual(len(oks), 1, "프로세스당 1회만 (ensure_schema 반복 호출 로그 폭주 방지)")
        self.assertIn(f"[migrate] ensure_audit_trades_reject_columns OK (user_id={USER})", oks[0])
        self.assertEqual(len([m for m in cm.output if "[migrate] ensure_wo2_audit_columns OK" in m]), 1)


class TestWordingAndGuide(unittest.TestCase):

    def test_first_bar_guard_log_has_no_critical_word_and_classifies(self):
        src = (ROOT / "core" / "strategy_incremental.py").read_text(encoding="utf-8")
        self.assertNotIn("무결성 결손 CRITICAL", src)
        self.assertIn('logger.error(err_msg)', src, "레벨 ERROR 유지")
        for tag in ("class=first_bar_guard", "class=pos_desync_promoted", "class=integrity_gap"):
            self.assertIn(f"[POS-DESYNC] {tag}", src)

    def test_guide_commands_do_not_depend_on_critical_word(self):
        guide = (ROOT / "docs" / "operations" / "wo8-force-buy-verification-guide.md").read_text(encoding="utf-8")
        self.assertNotIn("grep 'core\\.strategy_incremental' | grep -c 'CRITICAL'", guide)
        self.assertNotIn("grep 'pos_desync_warn' | wc -l", guide, "로그에 없는 dedupe 키로 집계 금지")
        self.assertIn("class=pos_desync_promoted", guide)

    def test_limit_buy_alert_timeout_text(self):
        src = (ROOT / "core" / "trader.py").read_text(encoding="utf-8")
        self.assertNotIn("다음 봉 (~{interval_sec}초)", src)
        self.assertIn("미체결 시 자동 취소: 약 {interval_sec / 60:g}분 뒤", src)
        self.assertEqual(f"{1500 / 60:g}", "25", "minute5 × 5봉 = 1500초 → 약 25분")


class TestSettingsHelpRender(unittest.TestCase):
    """B4: 대기 봉 수 도움말이 실제 봉 간격(minute5)으로 계산되어 렌더되는지 (AppTest)."""

    def setUp(self):
        import config  # noqa: F401
        import services.db  # noqa: F401
        import engine.params  # noqa: F401
        self._cwd = os.getcwd()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo10ui_"))
        self.db_path = str(self.tmpdir / f"tradebot_{USER}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        initialize_db(USER)
        ensure_all_schemas(USER)
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_help_uses_interval(self):
        from config import PARAMS_JSON_FILENAME
        from engine.params import _scoped_path
        (self.tmpdir / f"{USER}_EMA_buy_sell_conditions.json").write_text(json.dumps({
            "buy": {"ema_gc": True, "fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 5},
            "sell": {"stop_loss": True, "stop_loss_pct": 0.7},
        }), encoding="utf-8")
        (self.tmpdir / _scoped_path(f"{USER}_{PARAMS_JSON_FILENAME}", "EMA")).write_text(json.dumps({
            "ticker": "JTO", "interval": "minute5", "fast_period": 60, "slow_period": 200,
            "signal_period": 9, "take_profit": 0.05, "stop_loss": 0.007, "cash": 1000000,
            "commission": 0.0005, "order_ratio": 0.1, "strategy_type": "EMA",
        }), encoding="utf-8")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "set_buy_sell_conditions.py"), default_timeout=60)
        for k, v in dict(user_id=USER, mode="LIVE", strategy="EMA").items():
            at.query_params[k] = v
        at.session_state["user_id"] = USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        wb = next(n for n in at.number_input if n.label.startswith("현재가 매수 대기 봉 수"))
        self.assertIn("현재 5분봉 기준: 3봉 ≈ 15분, 5봉 ≈ 25분", wb.help)
        self.assertNotIn("1분봉 기준", wb.help)


if __name__ == "__main__":
    unittest.main()
