"""1109 눌림목 실계좌 열기 — 작업 A: 모드 표식(실계좌/모의)과 기동 판정.

표식 파일 <user>_active_strategy_mode.txt:
  없음 = TEST(모의 사용자 기동을 막지 않음), 'LIVE' = 실계좌, 그 밖(빈 파일·이상한 내용·읽기 실패) = UNKNOWN.
활성 전략이 PULLBACK 일 때만 읽는다. 시험은 임시 폴더 + 가짜로만 돈다(바깥 연결 없음).
"""
import os
import tempfile
import unittest
from unittest import mock

import config  # noqa: F401  (st.secrets 는 작업 폴더 기준이라 chdir 전에 읽는다)
from engine import active_mode, engine_manager, params as _params, pullback_params, strategy_switch  # noqa: F401

USER = "marker_user"


class InTmp(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._d = tempfile.TemporaryDirectory()
        os.chdir(self._d.name)
        self.addCleanup(self._d.cleanup)
        self.addCleanup(os.chdir, self._cwd)


class TestMarkerFile(InTmp):
    def test_marker_missing_means_test(self):
        from engine import active_mode as am
        self.assertEqual(am.read_marker(USER), "TEST")

    def test_marker_unreadable_is_unknown(self):
        from engine import active_mode as am
        for body in ("", "LIVE\n더미", "live2", "TEST2"):
            with open(am.marker_path(USER), "w", encoding="utf-8") as f:
                f.write(body)
            self.assertEqual(am.read_marker(USER), "UNKNOWN", body)
        # 읽기 예외도 UNKNOWN
        with open(am.marker_path(USER), "w", encoding="utf-8") as f:
            f.write("LIVE")
        with mock.patch("builtins.open", side_effect=OSError("boom")):
            self.assertEqual(am.read_marker(USER), "UNKNOWN")

    def test_write_marker_roundtrip_and_verifies(self):
        from engine import active_mode as am
        am.write_marker(USER, "LIVE")
        self.assertEqual(am.read_marker(USER), "LIVE")
        am.write_marker(USER, "TEST")
        self.assertEqual(am.read_marker(USER), "TEST")
        with self.assertRaises(ValueError):
            am.write_marker(USER, "WHATEVER")

    def test_write_marker_is_atomic_no_empty_file_on_crash(self):
        from engine import active_mode as am
        am.write_marker(USER, "LIVE")
        with mock.patch("engine.pullback_params.os.replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                am.write_marker(USER, "TEST")
        self.assertEqual(am.read_marker(USER), "LIVE")           # 옛 내용 그대로, 빈 파일 없음
        left = [n for n in os.listdir(".") if n.endswith(".tmp")]
        self.assertEqual(left, [])


class TestBootDecision(InTmp):
    def _active(self, s):
        with open(f"{USER}_active_strategy.txt", "w", encoding="utf-8") as f:
            f.write(s)

    def test_ema_active_ignores_marker(self):
        """N7: 활성이 EMA·MACD 면 표식은 어떤 판정에도 쓰이지 않는다."""
        from engine import active_mode as am
        self._active("EMA")
        am.write_marker(USER, "LIVE")
        self.assertEqual(am.pullback_boot_allowed(USER, "TEST"), (True, ""))
        self.assertEqual(am.pullback_boot_allowed(USER, "LIVE"), (True, ""))

    def test_pullback_marker_must_match_boot_mode(self):
        from engine import active_mode as am
        self._active("PULLBACK")
        am.write_marker(USER, "LIVE")
        self.assertEqual(am.pullback_boot_allowed(USER, "LIVE"), (True, ""))
        self.assertEqual(am.pullback_boot_allowed(USER, "TEST"), (False, "marker_mismatch"))

    def test_pullback_no_marker_is_test(self):
        from engine import active_mode as am
        self._active("PULLBACK")
        self.assertEqual(am.pullback_boot_allowed(USER, "TEST"), (True, ""))
        self.assertEqual(am.pullback_boot_allowed(USER, "LIVE"), (False, "marker_mismatch"))

    def test_pullback_unknown_marker_refuses_live_but_not_test(self):
        """표식 이상 + 실계좌는 거부. 모의 사용자 기동은 막지 않는다(표식 없음은 TEST)."""
        from engine import active_mode as am
        self._active("PULLBACK")
        with open(am.marker_path(USER), "w", encoding="utf-8") as f:
            f.write("garbage")
        self.assertEqual(am.pullback_boot_allowed(USER, "LIVE"), (False, "marker_unknown"))
        ok, why = am.pullback_boot_allowed(USER, "TEST")
        self.assertFalse(ok)                       # 이상한 표식은 모의에서도 일치할 수 없다(실계좌 표식일 수 있음)
        self.assertEqual(why, "marker_unknown")


class TestStartEngineGuard(InTmp):
    """engine_manager._engine_runner 가 trader 를 만들기 전에 표식으로 거부 + CRITICAL 1회."""

    def _run(self, *, marker, test_mode):
        from engine import engine_manager as em, active_mode as am
        with open(f"{USER}_active_strategy.txt", "w", encoding="utf-8") as f:
            f.write("PULLBACK")
        if marker is not None:
            with open(am.marker_path(USER), "w", encoding="utf-8") as f:
                f.write(marker)
        import threading
        mgr = em.EngineManager()
        stop = threading.Event()
        lock = threading.Lock()
        with mock.patch("engine.pullback_params._notify_critical") as notify, \
                mock.patch.object(em, "UpbitTrader") as tcls, \
                mock.patch.object(em, "_pullback_boot_params", return_value=(None, None)) as bp, \
                mock.patch.object(em, "st", mock.MagicMock(session_state={})), \
                mock.patch.object(em, "get_user_lock", return_value=lock), \
                mock.patch.object(em, "insert_log"), mock.patch.object(em, "log_to_file"), \
                mock.patch.object(em, "update_engine_status"), mock.patch.object(em, "set_engine_status"), \
                mock.patch.object(em, "set_thread_status"), mock.patch.object(em, "remove_engine_thread"), \
                mock.patch.object(em, "add_engine_thread"), mock.patch.object(em, "run_live_loop"), \
                mock.patch("services.db.get_coin_balance", return_value=0.0):
            mgr._engine_runner(USER, stop, test_mode, "TEST" if test_mode else "LIVE")
        return notify, tcls, bp

    def test_live_boot_with_test_marker_refused(self):
        notify, tcls, bp = self._run(marker=None, test_mode=False)
        tcls.assert_not_called()
        bp.assert_not_called()
        self.assertEqual(notify.call_count, 1)
        self.assertIn("다른 모드", notify.call_args.args[0] + notify.call_args.args[1])

    def test_test_boot_with_live_marker_refused(self):
        notify, tcls, bp = self._run(marker="LIVE", test_mode=True)
        tcls.assert_not_called()
        bp.assert_not_called()
        self.assertEqual(notify.call_count, 1)

    def test_live_boot_with_live_marker_proceeds_to_params(self):
        notify, tcls, bp = self._run(marker="LIVE", test_mode=False)
        bp.assert_called_once()
        self.assertEqual(bp.call_args.args[:2], (USER, "LIVE"))
        tcls.assert_not_called()                   # 가짜 변환이 None 을 돌려줘 기동 거부로 끝난다

    def test_test_boot_without_marker_proceeds(self):
        notify, tcls, bp = self._run(marker=None, test_mode=True)
        bp.assert_called_once()
        self.assertEqual(bp.call_args.args[:2], (USER, "TEST"))


class TestSwitchWritesMarker(InTmp):
    """호출 순서(표식 → 활성 파일)와 실패 때 활성 파일 무변경은 test_r_2026_11_09_live_open_switch 가 실제 전환으로 본다.
    여기서는 표식 쓰기 도우미만 본다."""

    def test_write_mode_marker_helper_reports_failure(self):
        from engine import strategy_switch as ss, active_mode as am
        self.assertTrue(ss._write_mode_marker(USER, "LIVE"))
        self.assertEqual(am.read_marker(USER), "LIVE")
        with mock.patch.object(am, "write_marker", side_effect=OSError("x")):
            self.assertFalse(ss._write_mode_marker(USER, "LIVE"))

    def test_revert_and_recovery_write_does_not_touch_marker(self):
        from engine import strategy_switch as ss, active_mode as am
        with mock.patch.object(am, "write_marker", side_effect=AssertionError("표식 쓰기 금지")), \
                mock.patch("engine.params.save_active_strategy"), \
                mock.patch.object(ss, "_active_file", return_value="PULLBACK"):
            self.assertTrue(ss._write_active(USER, "PULLBACK"))        # 되돌림 경로(표식 안 씀)


if __name__ == "__main__":
    unittest.main()
