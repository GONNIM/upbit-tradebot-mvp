"""
1101-05: 엔진 시작 겹침 막기 — 정지한 옛 매매 루프(작업 스레드)가 살아 있으면 시작 거절.

계획: docs/plans/2026-11-01-engine-start-overlap-guard/plan.md 3절 (시험 1~8).
근거 사고: 2026-11-01 16:45 신버전 정지 → 옛 run_live_loop 81초 재시도 → 구버전 시작으로 24초 겹침(주문 0).

- 진짜: EngineManager.start_engine / _start_engine_locked / _start_engine_internal / stop_engine,
  core.engine_control.alive_engine_threads, control_requests.Controller._stale_threads·_engine_start.
- 가짜: DB 기록·파일 로그·params·trader·run_live_loop 본문·Reconciler·텔레그램 발송(engine_exit_alert 의 Rig).
- 바깥 연결 없음(텔레그램은 services.notifier.send 를 가짜로 바꿈).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_11_01_engine_start_overlap -v
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
import engine.engine_manager as engine_manager  # noqa: E402
from core.engine_control import alive_engine_threads  # noqa: E402
from engine import control_requests  # noqa: E402
from tests.regressions.test_r_2026_10_29_engine_exit_alert import Rig  # noqa: E402

U = "overlap_guard_u1"
U2 = "overlap_guard_u2"


class OldThread:
    """이름만 엔진 스레드처럼 붙인, Event 로 붙잡아 둔 가짜 옛 스레드(시험 끝에 반드시 풀고 join)."""

    def __init__(self, name: str):
        self.release = threading.Event()
        self.th = threading.Thread(target=self.release.wait, name=name, daemon=True)
        self.th.start()

    def stop(self):
        self.release.set()
        self.th.join(timeout=5)


class Base(unittest.TestCase):
    def setUp(self):
        self.olds = []
        self.rig = Rig()
        self.rig.__enter__()
        self.em = self.rig.em

    def tearDown(self):
        for o in self.olds:
            o.stop()
        self.rig.__exit__(None, None, None)
        for th in threading.enumerate():
            if th.name.endswith((f"_{U}_TEST", f"_{U}_LIVE", f"_{U2}_TEST", f"_{U2}_LIVE")):
                th.join(timeout=10)

    def old(self, name):
        o = OldThread(name)
        self.olds.append(o)
        return o

    def warnings(self):
        return [r for r in self.rig.log_handler.records if "[ENGINE-START]" in r.getMessage()]


class TestRejectWhenOldAlive(Base):
    def test_1_old_worker_alive_rejects_both_modes_without_side_effects(self):
        self.old(f"run_live_loop_{U}_LIVE")
        live_users_before = set(self.em._live_users)
        # _start_engine_locked 는 함수 안에서 services.db.set_engine_status 를 부른다 — 그 실제 호출을 본다
        with mock.patch("services.db.set_engine_status") as db_status:
            for mode in ("LIVE", "TEST"):
                with self.subTest(mode=mode):
                    self.assertFalse(self.em.start_engine(U, mode=mode, strategy="PULLBACK"))
                    self.assertEqual(self.em.last_start_reject(U, mode), "old_engine_alive")
                    self.assertIsNone(self.em._threads.get(U))
                    self.assertNotIn(U, self.em._strategy_override)   # 거부 → 원복
                    db_status.assert_not_called()                      # DB 「실행 중」·last_mode 기록 0
        self.assertEqual([s for s in self.rig.status if s[1]], [])   # 실행 중(True) 기록 0
        self.rig.rec.start.assert_not_called()
        self.assertEqual(set(self.em._live_users), live_users_before)
        self.assertEqual(len(self.warnings()), 2)
        self.assertIn(("INFO", engine_manager.OLD_ALIVE_INVESTOR_LOG),
                      [(lv, m) for (u, lv, m) in self.rig.insert_logs if u == U])

    def test_2_after_old_ends_start_succeeds(self):
        o = self.old(f"run_live_loop_{U}_LIVE")
        self.assertFalse(self.em.start_engine(U, mode="TEST"))
        o.stop()
        self.assertTrue(self.em.start_engine(U, mode="TEST"))
        self.assertIsNone(self.em.last_start_reject(U, "TEST"))

    def test_3_other_users_thread_does_not_block(self):
        self.old(f"run_live_loop_{U2}_LIVE")
        self.assertTrue(self.em.start_engine(U, mode="TEST"))

    def test_4_old_manager_thread_alone_blocks(self):
        self.old(f"engine_runner_{U}_TEST")
        self.assertFalse(self.em.start_engine(U, mode="TEST"))
        self.assertEqual(self.em.last_start_reject(U), "old_engine_alive")

    def test_4b_name_must_match_exactly(self):
        self.old(f"run_live_loop_{U}_x_LIVE")
        self.old(f"run_live_loop_{U}")
        self.assertEqual(alive_engine_threads(U), [])
        self.assertTrue(self.em.start_engine(U, mode="TEST"))


class TestSameFunctionAsV2(Base):
    def test_5_controller_uses_same_function(self):
        self.old(f"run_live_loop_{U}_LIVE")
        self.assertEqual(control_requests.Controller._stale_threads(U), alive_engine_threads(U))
        self.assertEqual(len(alive_engine_threads(U)), 1)

    def test_5b_v2_start_race_returns_old_engine_alive(self):
        mgr = mock.MagicMock()
        mgr.get_running_mode.return_value = None
        mgr.start_engine.return_value = False
        mgr.last_start_reject.return_value = "old_engine_alive"
        ctl = control_requests.Controller(base_dir=ROOT / "nonexistent_overlap_dir", manager=mgr,
                                          notify=lambda *a, **k: None)
        with mock.patch.object(control_requests.Controller, "_stale_threads", staticmethod(lambda u: [])):
            r = ctl._engine_start({"user_id": U, "mode": "TEST"})
        self.assertEqual(r.get("code"), "old_engine_alive")
        mgr.last_start_reject.return_value = None
        with mock.patch.object(control_requests.Controller, "_stale_threads", staticmethod(lambda u: [])):
            r = ctl._engine_start({"user_id": U, "mode": "TEST"})
        self.assertEqual(r.get("code"), "start_failed")


class TestNormalPathUnchanged(Base):
    def test_6a_already_running_same_mode(self):
        self.assertTrue(self.em.start_engine(U, mode="TEST"))
        self.assertFalse(self.em.start_engine(U, mode="TEST"))
        self.assertIsNone(self.em.last_start_reject(U))
        self.assertEqual(self.warnings(), [])

    def test_6b_other_mode_is_mode_lock(self):
        self.assertTrue(self.em.start_engine(U, mode="TEST"))
        self.assertFalse(self.em.start_engine(U, mode="LIVE"))
        self.assertIsNone(self.em.last_start_reject(U))
        self.assertTrue(any("[MODE-LOCK]" in r.getMessage() for r in self.rig.log_handler.records))
        self.assertEqual(self.warnings(), [])

    def test_6c_stop_then_immediate_start_when_worker_ends_quickly(self):
        self.assertTrue(self.em.start_engine(U, mode="TEST"))
        self.em.stop_engine(U, mode="TEST")
        self.assertEqual(alive_engine_threads(U), [])
        self.assertTrue(self.em.start_engine(U, mode="TEST"))
        self.assertNotIn(U, self.em._stopped_at)   # 성공 시작 때 지움


class TestOperatorAlert(Base):
    def _alerts(self):
        return [s for s in self.rig.sends if s.get("dedupe_key") == f"engine_start_old_alive:{U}"]

    def test_7_alert_after_300s_outside_start_lock(self):
        self.old(f"run_live_loop_{U}_LIVE")
        held = []
        orig = engine_manager.EngineManager._send_old_alive_alert

        def spy(em_self, *a):
            held.append(em_self._start_lock(U).locked())
            return orig(em_self, *a)

        self.em._stopped_at[U] = time.monotonic() - 301
        with mock.patch.object(engine_manager.EngineManager, "_send_old_alive_alert", spy):
            self.assertFalse(self.em.start_engine(U, mode="LIVE"))
        alerts = self._alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["level"], "WARNING")
        self.assertEqual(alerts[0].get("audience"), "operator")
        self.assertEqual(held, [False])   # 시작 잠금을 푼 뒤 보냄

    def test_7b_no_alert_before_300s_or_without_stop_record(self):
        self.old(f"run_live_loop_{U}_LIVE")
        self.em._stopped_at[U] = time.monotonic() - 299
        self.assertFalse(self.em.start_engine(U, mode="LIVE"))
        self.em._stopped_at.pop(U)
        self.assertFalse(self.em.start_engine(U, mode="LIVE"))
        self.assertEqual(self._alerts(), [])
        self.assertTrue(any("since_stop=?" in r.getMessage() for r in self.warnings()))


class TestV2RejectAlert(Base):
    """1101-11: 신버전 시작 요청이 start_engine 앞에서 거절될 때도 정지 뒤 5분 넘으면 운영자 경보."""

    def _ctl(self):
        return control_requests.Controller(base_dir=ROOT / "nonexistent_overlap_dir", manager=self.em,
                                           notify=lambda *a, **k: None)

    def _alerts(self):
        return [s for s in self.rig.sends if s.get("dedupe_key") == f"engine_start_old_alive:{U}"]

    def test_v2_reject_after_300s_alerts_operator(self):
        self.old(f"run_live_loop_{U}_LIVE")
        self.em._stopped_at[U] = time.monotonic() - 301
        r = self._ctl()._engine_start({"user_id": U, "mode": "LIVE"})
        self.assertEqual(r.get("code"), "old_engine_alive")
        alerts = self._alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].get("audience"), "operator")
        self.assertEqual(alerts[0]["level"], "WARNING")

    def test_v2_reject_before_300s_or_no_stop_record_no_alert(self):
        self.old(f"run_live_loop_{U}_LIVE")
        self.em._stopped_at[U] = time.monotonic() - 299
        self.assertEqual(self._ctl()._engine_start({"user_id": U, "mode": "LIVE"}).get("code"), "old_engine_alive")
        self.em._stopped_at.pop(U)
        self.assertEqual(self._ctl()._engine_start({"user_id": U, "mode": "LIVE"}).get("code"), "old_engine_alive")
        self.assertEqual(self._alerts(), [])

    def test_v2_alert_failure_does_not_change_result(self):
        self.old(f"run_live_loop_{U}_LIVE")
        with mock.patch.object(self.em, "note_old_alive_reject", side_effect=RuntimeError("x")):
            r = self._ctl()._engine_start({"user_id": U, "mode": "LIVE"})
        self.assertEqual(r.get("code"), "old_engine_alive")


class TestOldUiMessage(unittest.TestCase):
    def test_8_dashboard_branch_message_and_no_alert(self):
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        i = src.index('elif engine_manager.last_start_reject(user_id) == "old_engine_alive":')
        j = src.index("else:", i)
        branch = src[i:j]
        self.assertIn("⏳ 이전 엔진이 아직 정리 중입니다. 1~3분 뒤 다시 눌러 주세요.", branch)
        self.assertNotIn("_notify", branch)
        self.assertNotIn("notifier", branch)


if __name__ == "__main__":
    unittest.main()
