"""엔진 생존 파일(.engine_alive.json) 감시 스레드 시험 (scripts/tradebot_boot.py, 계획서 8-1).

가짜 engine_manager 만 쓴다(실제 엔진·Streamlit 서버를 띄우지 않는다). 임시 폴더만 쓴다.
"""
import importlib.util
import json
import os
import stat
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from v2 import db, status

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tradebot_boot.py"


def load_boot():
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("tradebot_boot_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)   # 모듈 맨 위에서 os.chdir(ROOT) 를 한다 — 아래에서 되돌린다
        return mod
    finally:
        os.chdir(cwd)


class FakeManager:
    """engine_manager 대역: 키 = _threads 의 키, 값 = 살아 있는 엔진 모드('LIVE'/'TEST') 또는 None."""

    def __init__(self, threads):
        self.threads = dict(threads)

    def get_active_user_ids(self):
        return list(self.threads.keys())

    def get_running_mode(self, uid):
        return self.threads.get(uid)


class AliveTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_boot()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, ".engine_alive.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_alive_dead_two_users_and_never_started(self):
        m = FakeManager({"mcmax33": "LIVE", "other": None})   # other: 스레드 죽음(예외 뒤 대기 중 아님)
        running = self.mod.engine_alive_tick(m, self.path)
        self.assertEqual(running, {"mcmax33": True, "other": False})
        body = self.read()
        self.assertEqual(set(body), {"pid", "at", "running"})
        self.assertEqual(body["running"], {"mcmax33": True, "other": False})
        self.assertEqual(body["pid"], os.getpid())
        # 한 번도 시작 안 한 계정은 키가 없다 → 신버전은 Stopped
        self.assertNotIn("never", body["running"])
        now = datetime.now(db.KST)
        self.assertFalse(status.engine_alive_running(body, "never", now))
        self.assertTrue(status.engine_alive_running(body, "mcmax33", now))
        self.assertFalse(status.engine_alive_running(body, "other", now))

    def test_thread_alive_during_restart_wait_counts_as_running(self):
        # 예외 뒤 재시작 대기(sleep) 중에는 스레드가 살아 있다 → get_running_mode 가 모드를 돌려준다
        m = FakeManager({"mcmax33": "LIVE"})
        self.mod.engine_alive_tick(m, self.path)
        self.assertTrue(self.read()["running"]["mcmax33"])

    def test_at_is_kst_iso_with_offset(self):
        self.mod.engine_alive_tick(FakeManager({}), self.path)
        at = self.read()["at"]
        self.assertTrue(at.endswith("+09:00"), at)
        dt = datetime.fromisoformat(at)
        self.assertLess(abs((datetime.now(db.KST) - dt).total_seconds()), 5)
        self.assertEqual(self.read()["running"], {})

    def test_file_permission_600_and_no_tmp_left(self):
        self.mod.engine_alive_tick(FakeManager({"u": "TEST"}), self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), [".engine_alive.json"])

    def test_atomic_write_uses_replace_and_failure_keeps_old_file(self):
        self.mod.engine_alive_tick(FakeManager({"u": "TEST"}), self.path)
        before = self.read()
        with mock.patch.object(self.mod.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                self.mod.engine_alive_tick(FakeManager({"u": None}), self.path)
        self.assertEqual(self.read(), before)   # 기존 파일은 그대로
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.replace(tmp, path)", src)
        self.assertIn("0o600", src)

    def test_loop_survives_manager_errors_and_stops(self):
        calls = {"n": 0}
        stop = threading.Event()

        class Flaky(FakeManager):
            def get_active_user_ids(self_inner):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("first call fails")
                if calls["n"] >= 3:
                    stop.set()
                return super().get_active_user_ids()

        m = Flaky({"u": "LIVE"})
        self.mod._engine_alive_loop(self.path, 0.001, lambda: m, stop)
        self.assertGreaterEqual(calls["n"], 3)
        self.assertEqual(self.read()["running"], {"u": True})   # 첫 실패 뒤에도 계속 기록

    def test_loop_returns_quietly_when_manager_import_fails(self):
        def boom():
            raise ImportError("no engine")
        self.mod._engine_alive_loop(self.path, 0.001, boom, threading.Event())   # 예외 없이 끝남
        self.assertFalse(os.path.exists(self.path))

    def test_start_delay_waits_before_import_and_stop_cancels(self):
        called = []

        def mgr():
            called.append(1)
            raise ImportError("not reached")
        stop = threading.Event()
        stop.set()   # 대기 중에 멈추면 import 하지 않고 끝난다
        self.mod._engine_alive_loop(self.path, 0.001, mgr, stop, start_delay=5.0)
        self.assertEqual(called, [])
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('start_delay=float(os.environ.get("TRADEBOT_BOOT_DELAY", "3")) + 2.0', src)

    def test_engine_manager_imported_lazily_inside_thread(self):
        src = SCRIPT.read_text(encoding="utf-8")
        lines = [ln for ln in src.splitlines() if "from engine.engine_manager import" in ln]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("    "), "모듈 맨 위에서 import 하면 안 된다: " + lines[0])

    def test_main_calls_bootstrap_run_even_if_alive_thread_cannot_start(self):
        try:
            from streamlit import config as st_config  # noqa: F401
            from streamlit.web import bootstrap
        except Exception:
            self.skipTest("streamlit 없음")
        saved_path = getattr(st_config, "_main_script_path", None)
        real_thread = threading.Thread

        def thread_factory(*a, **kw):
            if kw.get("name") == "engine_alive":
                raise RuntimeError("cannot start new thread")
            return real_thread(*a, **kw)

        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.addCleanup(setattr, st_config, "_main_script_path", saved_path)
        env = {"TRADEBOT_BOOT_RESUME": "0"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(self.mod.threading, "Thread", side_effect=thread_factory), \
                mock.patch.object(bootstrap, "run") as run, \
                mock.patch.object(bootstrap, "load_config_options"):
            self.mod.main()
        run.assert_called_once()

    def test_main_starts_alive_thread_before_bootstrap_run(self):
        src = SCRIPT.read_text(encoding="utf-8")
        body = src.split("def main()")[1]
        self.assertIn('name="engine_alive", daemon=True', body)
        self.assertLess(body.index('name="engine_alive"'), body.index("bootstrap.run("))
        # 기동 재개 끔(TRADEBOT_BOOT_RESUME=0)과 무관하게 시작한다
        self.assertGreater(body.index('name="engine_alive"'), body.index('"TRADEBOT_BOOT_RESUME"'))
        # 스레드 시작부는 try 로 감싼다
        self.assertRegex(body, r"try:\n\s+threading\.Thread\(target=_engine_alive_thread[^\n]*\.start\(\)\n\s+except Exception")

    def test_does_not_touch_trading_modules(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for bad in ("start_engine(", "stop_engine(", "set_trading_paused", "insert_log", "sqlite3"):
            self.assertNotIn(bad, src.split("def _write_engine_alive")[1].split("def main()")[0], bad)


if __name__ == "__main__":
    unittest.main()
