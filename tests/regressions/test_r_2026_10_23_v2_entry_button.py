"""Task 5: 구버전 입장 버튼 (ui/v2_entry.py, app.py 호출 1줄) 회귀 시험."""
import ast
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from utils import v2_entry_token as et

REPO = Path(__file__).resolve().parents[2]
APP_PATH = REPO / "app.py"
UI_PATH = REPO / "ui" / "v2_entry.py"


def _entry_script(secret_path, allow_path, user_id, mode):
    # AppTest.from_function 은 함수 소스만 떼어 실행하므로 import 를 함수 안에서 한다.
    import streamlit as st  # noqa: F401
    import utils.v2_entry_token as et_mod
    import ui.v2_entry as entry

    from pathlib import Path as _P

    et_mod.SECRET_PATH = _P(secret_path)
    et_mod.ALLOWLIST_PATH = _P(allow_path)
    entry.render_v2_entry(user_id, mode)


class EntryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.secret = self.dir / "secret"
        self.allow = self.dir / "allow"
        self.secret.write_bytes(os.urandom(48))
        os.chmod(self.secret, 0o600)
        self.allow.write_text("alice\n", encoding="utf-8")
        self._old = (et.SECRET_PATH, et.ALLOWLIST_PATH)
        self.addCleanup(self._restore)

    def _restore(self):
        et.SECRET_PATH, et.ALLOWLIST_PATH = self._old

    def run_app(self, user_id="alice", mode="TEST"):
        at = AppTest.from_function(
            _entry_script,
            kwargs={
                "secret_path": str(self.secret),
                "allow_path": str(self.allow),
                "user_id": user_id,
                "mode": mode,
            },
        )
        return at.run()


class RenderTests(EntryBase):
    def test_allowed_shows_button_no_exception(self):
        at = self.run_app()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.button), 1)
        self.assertEqual(at.button[0].key, "btn_v2_entry")
        self.assertEqual(at.button[0].label, "📱 신버전 대시보드 (베타)")
        self.assertEqual(len(at.get("link_button")), 0)

    def test_not_allowed_shows_nothing(self):
        with self.assertNoLogs("ui.v2_entry", level="WARNING"):
            at = self.run_app(user_id="mallory")
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.button), 0)
        self.assertEqual(len(at.get("link_button")), 0)

    def test_render_no_exception_on_missing_corrupt_unreadable(self):
        cases = ["missing", "short", "unreadable"]
        for case in cases:
            with self.subTest(case=case):
                if case == "missing":
                    self.secret.unlink()
                elif case == "short":
                    self.secret.write_bytes(os.urandom(31))
                else:
                    if os.geteuid() == 0:
                        self.skipTest("root 는 0o000 파일도 읽을 수 있음")
                    os.chmod(self.secret, 0o000)
                try:
                    with self.assertLogs("ui.v2_entry", level="WARNING") as cm:
                        at = self.run_app()
                finally:
                    if self.secret.exists():
                        os.chmod(self.secret, 0o600)
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.button), 0)
                self.assertEqual(len(at.get("link_button")), 0)
                self.assertEqual(len(cm.records), 1)
                msg = cm.records[0].getMessage()
                self.assertEqual(msg, "[V2-ENTRY] hidden: TokenUnavailable")
                self.assertNotIn(str(self.dir), msg)
                self.assertNotIn("secret", msg)
                # 다음 사례를 위해 정상 키 복원
                self.secret.write_bytes(os.urandom(48))
                os.chmod(self.secret, 0o600)

    def test_token_made_on_click_not_on_render(self):
        real = et.make_token
        with mock.patch.object(et, "make_token", side_effect=real) as m:
            at = self.run_app()
            self.assertEqual(m.call_count, 0)
            at.button[0].click().run()
            self.assertEqual(m.call_count, 1)
            self.assertEqual(m.call_args.args, ("alice", "TEST"))

    def test_click_shows_link_with_token(self):
        at = self.run_app(mode="LIVE")
        at.button[0].click().run()
        self.assertEqual(len(at.exception), 0)
        links = at.get("link_button")
        self.assertEqual(len(links), 1)
        url = links[0].proto.url
        self.assertTrue(url.startswith("/v2/?t="), url)
        et.SECRET_PATH = self.secret
        payload = et.verify_token(url.split("?t=", 1)[1])
        self.assertEqual(payload["user_id"], "alice")
        self.assertEqual(payload["mode"], "LIVE")
        self.assertEqual(links[0].proto.label, "신버전 열기 (60초 안에 눌러 주세요)")
        texts = " ".join(str(getattr(e, "value", "")) for e in at.markdown) + " ".join(
            str(getattr(e, "value", "")) for e in at.caption
        )
        self.assertIn("구버전으로 돌아올 때는 다시 로그인해야 합니다", texts)

    def test_click_failure_hides_link_and_logs_once(self):
        at = self.run_app()
        with mock.patch.object(
            et, "make_token", side_effect=et.TokenUnavailable("x")
        ):
            with self.assertLogs("ui.v2_entry", level="WARNING") as cm:
                at.button[0].click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.get("link_button")), 0)
        self.assertEqual(len(cm.records), 1)
        self.assertEqual(
            cm.records[0].getMessage(), "[V2-ENTRY] hidden: TokenUnavailable"
        )


class LintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_src = APP_PATH.read_text(encoding="utf-8")
        cls.app_tree = ast.parse(cls.app_src)
        cls.ui_src = UI_PATH.read_text(encoding="utf-8")
        cls.ui_tree = ast.parse(cls.ui_src)

    def _calls(self):
        return [
            n
            for n in ast.walk(self.app_tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "render_v2_entry"
        ]

    def test_app_calls_render_v2_entry_once(self):
        self.assertEqual(len(self._calls()), 1)
        self.assertEqual(
            len(re.findall(r"^from ui\.v2_entry import render_v2_entry$",
                           self.app_src, re.M)),
            1,
        )

    def test_app_passes_username_not_session_user_id(self):
        call = self._calls()[0]
        first = call.args[0]
        self.assertIsInstance(first, ast.Name)
        self.assertEqual(first.id, "username")

    def test_app_and_ui_do_not_import_v2(self):
        for tree in (self.app_tree, self.ui_tree):
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        self.assertNotEqual(a.name.split(".")[0], "v2")
                elif isinstance(n, ast.ImportFrom):
                    self.assertNotEqual((n.module or "").split(".")[0], "v2")

    def test_not_inside_expander(self):
        # ui 모듈: expander 사용 없음
        self.assertNotIn("expander", self.ui_src)
        # app.py: 호출이 with ...expander 블록 안에 있지 않음
        call = self._calls()[0]
        for w in ast.walk(self.app_tree):
            if isinstance(w, ast.With) and "expander" in ast.unparse(w.items[0]):
                inner = {id(x) for x in ast.walk(w)}
                self.assertNotIn(id(call), inner)

    def test_ui_uses_module_attribute_access(self):
        for n in ast.walk(self.ui_tree):
            if isinstance(n, ast.ImportFrom) and n.module == "utils.v2_entry_token":
                self.fail("from utils.v2_entry_token import ... 금지")


if __name__ == "__main__":
    unittest.main()
