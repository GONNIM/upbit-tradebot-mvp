"""
1101-06: 운영자 채널 시험 도구(scripts/v2/notify_operator_test.py) — 바깥 연결 없는 시험.

계획: docs/plans/2026-11-01-engine-start-overlap-guard/plan.md 4절.
- `.env` 에만 키가 있고 환경 변수는 빈 상태에서 「있음」으로 판정(config 의 load_dotenv 분기에 기대지 않음).
- 키가 없으면 보내지 않음, WO6_DRY_RUN=1 이면 발송 직전에서 멈춤, 보낼 때는 audience=operator 1건.
- 출력에 키 값이 없음.

실행:
    python3 -m unittest tests.regressions.test_r_2026_11_01_notify_operator_tool -v
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

TOOL = ROOT / "scripts" / "v2" / "notify_operator_test.py"
FAKE_TOKEN = "fake-token-value-123"
FAKE_CHAT = "-100987654321"
KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID_OPERATOR", "TELEGRAM_CHAT_ID", "WO6_DRY_RUN")


def _load_tool():
    spec = importlib.util.spec_from_file_location("notify_operator_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ToolCase(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = {k: os.environ.pop(k, None) for k in KEYS}
        # streamlit secrets 대체 경로를 막는다(시험 기계의 secrets.toml 을 읽지 않게)
        self.p_st = mock.patch.dict(sys.modules, {"streamlit": None})
        self.p_st.start()

    def tearDown(self):
        self.p_st.stop()
        for k in KEYS:
            os.environ.pop(k, None)
            if self.saved[k] is not None:
                os.environ[k] = self.saved[k]
        self.tmp.cleanup()

    def write_env(self, text):
        (self.root / ".env").write_text(text, encoding="utf-8")

    def run_tool(self, send_ret=True):
        import logging
        lg = logging.getLogger("services.notifier")
        saved = (list(lg.handlers), lg.propagate)   # 도구가 notifier 로거를 끄므로 시험 뒤 되돌림
        out = io.StringIO()
        try:
            with mock.patch("services.notifier.send", return_value=send_ret) as send, \
                    contextlib.redirect_stdout(out):
                rc = self.tool.main(self.root)
        finally:
            lg.handlers[:] = saved[0]
            lg.propagate = saved[1]
        return rc, out.getvalue(), send

    def test_env_only_keys_detected_dry_run_stops(self):
        self.write_env(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID_OPERATOR={FAKE_CHAT}\n")
        os.environ["WO6_DRY_RUN"] = "1"
        rc, out, send = self.run_tool()
        self.assertEqual(rc, 3)
        self.assertIn("토큰: 있음 · 운영자 채팅 ID: 있음", out)
        send.assert_not_called()
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertNotIn(FAKE_CHAT, out)

    def test_sends_one_operator_message(self):
        self.write_env(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID_OPERATOR={FAKE_CHAT}\n")
        rc, out, send = self.run_tool(send_ret=True)
        self.assertEqual(rc, 0)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs.get("audience"), "operator")
        self.assertIn("보냄", out)
        self.assertNotIn(FAKE_TOKEN, out)

    def test_send_false_reports_not_sent(self):
        self.write_env(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID_OPERATOR={FAKE_CHAT}\n")
        rc, out, _ = self.run_tool(send_ret=False)
        self.assertEqual(rc, 1)
        self.assertIn("못 보냄", out)

    def test_missing_operator_chat_does_not_send(self):
        self.write_env(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID=-1001\n")
        rc, out, send = self.run_tool()
        self.assertEqual(rc, 2)
        self.assertIn("운영자 채팅 ID: 없음", out)
        send.assert_not_called()

    def test_missing_env_file(self):
        rc, out, send = self.run_tool()
        self.assertEqual(rc, 2)
        self.assertIn(".env 없음", out)
        send.assert_not_called()

    def test_network_exception_does_not_print_token(self):
        """연결 실패 예외 문구에 토큰 URL 이 섞여도 터미널(stdout·stderr)에 토큰이 나오지 않는다."""
        import logging
        from services import notifier
        self.write_env(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID_OPERATOR={FAKE_CHAT}\n")
        lg = logging.getLogger("services.notifier")
        saved = (list(lg.handlers), lg.propagate)
        out, err = io.StringIO(), io.StringIO()
        boom = ConnectionError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
        try:
            with mock.patch.object(notifier, "_requests") as req, \
                    mock.patch.object(notifier, "_should_skip_by_dedupe", return_value=False), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                req.post.side_effect = boom
                # 루트 로거에 stderr 핸들러가 있어도 새지 않아야 한다
                root_h = logging.StreamHandler(sys.stderr)
                logging.getLogger().addHandler(root_h)
                try:
                    rc = self.tool.main(self.root)
                finally:
                    logging.getLogger().removeHandler(root_h)
        finally:
            lg.handlers[:] = saved[0]
            lg.propagate = saved[1]
        self.assertEqual(rc, 1)
        req.post.assert_called_once()
        self.assertNotIn(FAKE_TOKEN, out.getvalue() + err.getvalue())
        self.assertNotIn(FAKE_CHAT, out.getvalue() + err.getvalue())

    def test_tool_does_not_import_config(self):
        src = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("import config", src.replace("`import config`", ""))


if __name__ == "__main__":
    unittest.main()
