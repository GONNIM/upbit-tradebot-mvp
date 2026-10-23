import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tornado.testing import AsyncHTTPTestCase

from utils import v2_entry_token as et
from v2 import auth
from v2.handlers import ApiHandler
from v2.server import make_app

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://orionhunter7.cafe24.com"
GUIDE = "구버전 입장 화면에서 『신버전 대시보드』를 다시 눌러 주세요"


class _DummyApi(ApiHandler):
    def get(self):
        self.write({"user_id": self.current_user["user_id"]})

    def post(self):
        self.write({"ok": True})


class ServerBase(AsyncHTTPTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.static = self.dir / "static"
        self.static.mkdir()
        self.secret = self.dir / "secret"
        self.allow = self.dir / "allow"
        self.secret.write_bytes(os.urandom(48))
        os.chmod(self.secret, 0o600)
        self.allow.write_text("alice\n", encoding="utf-8")
        self._old = (et.SECRET_PATH, et.ALLOWLIST_PATH)
        et.SECRET_PATH = self.secret
        et.ALLOWLIST_PATH = self.allow
        self.addCleanup(self._restore)
        super().setUp()

    def _restore(self):
        et.SECRET_PATH, et.ALLOWLIST_PATH = self._old

    def get_app(self):
        app = make_app(static_dir=self.static)
        app.add_handlers(r".*", [(r"/v2/api/_test", _DummyApi)])
        return app

    def cookie(self, user="alice", mode="TEST"):
        return {"Cookie": "%s=%s" % (auth.SESSION_COOKIE,
                                     auth.make_session(user, mode))}


class ServerTests(ServerBase):
    def test_token_exchange_sets_cookie_and_redirects(self):
        tok = et.make_token("alice", "LIVE")
        r = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 302)
        self.assertEqual(r.headers["Location"], "/v2/")
        sc = r.headers["Set-Cookie"]
        self.assertTrue(sc.startswith(auth.SESSION_COOKIE + "="))
        low = sc.lower()
        self.assertIn("httponly", low)
        self.assertIn("secure", low)
        self.assertIn("samesite=lax", low)
        self.assertIn("path=/v2/", low)
        self.assertIn("max-age=%d" % auth.SESSION_TTL_SEC, low)
        value = sc.split(";", 1)[0].split("=", 1)[1]
        s = auth.read_session(value)
        self.assertEqual((s["user_id"], s["mode"]), ("alice", "LIVE"))

    def test_access_log_masks_token(self):
        tok = et.make_token("alice", "TEST")
        with self.assertLogs("tornado.access", level="INFO") as cm:
            r = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 302)
        text = "\n".join(cm.output)
        self.assertNotIn(tok, text)
        self.assertIn("/v2/?***", text)

    def test_access_log_masks_encoded_param_name(self):
        tok = et.make_token("alice", "TEST")
        with self.assertLogs("tornado.access", level="INFO") as cm:
            r = self.fetch("/v2/?%74=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 302)
        self.assertNotIn(tok, "\n".join(cm.output))

    def test_token_reuse_rejected(self):
        tok = et.make_token("alice", "TEST")
        r1 = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r1.code, 302)
        r2 = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r2.code, 401)
        self.assertNotIn("Set-Cookie", r2.headers)
        self.assertIn(GUIDE, r2.body.decode())

    def test_expired_token_page_has_guidance(self):
        tok = et.make_token("alice", "TEST", now=time.time() - 600)
        r = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 401)
        self.assertIn(GUIDE, r.body.decode())
        self.assertNotIn("Set-Cookie", r.headers)

    def test_not_allowlisted_token_same_guidance(self):
        tok = et.make_token("mallory", "TEST")
        r = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 401)
        self.assertIn(GUIDE, r.body.decode())
        self.assertNotIn("Set-Cookie", r.headers)

    def test_secret_missing_same_guidance(self):
        tok = et.make_token("alice", "TEST")
        self.secret.unlink()
        r = self.fetch("/v2/?t=" + tok, follow_redirects=False)
        self.assertEqual(r.code, 401)
        self.assertIn(GUIDE, r.body.decode())

    def test_api_without_session_401(self):
        r = self.fetch("/v2/api/_test")
        self.assertEqual(r.code, 401)
        self.assertEqual(r.headers["Content-Type"].split(";")[0],
                         "application/json")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_api_not_allowlisted_403(self):
        h = self.cookie("alice")
        self.allow.write_text("bob\n", encoding="utf-8")
        r = self.fetch("/v2/api/_test", headers=h)
        self.assertEqual(r.code, 403)
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_api_with_session_ok(self):
        r = self.fetch("/v2/api/_test", headers=self.cookie("alice"))
        self.assertEqual(r.code, 200)
        self.assertIn("alice", r.body.decode())
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_referrer_policy_header(self):
        for path in ("/v2/", "/v2/api/_test", "/v2/static/nope.js"):
            r = self.fetch(path)
            self.assertEqual(r.headers["Referrer-Policy"], "no-referrer", path)
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff",
                             path)

    def test_post_bad_origin_403(self):
        h = self.cookie("alice")
        r = self.fetch("/v2/api/_test", method="POST", body="{}", headers=h)
        self.assertEqual(r.code, 403)
        h2 = dict(h, Origin="https://evil.example")
        r = self.fetch("/v2/api/_test", method="POST", body="{}", headers=h2)
        self.assertEqual(r.code, 403)
        for m in ("PUT", "DELETE"):
            r = self.fetch("/v2/api/_test", method=m,
                           body=None if m == "DELETE" else "{}",
                           headers=dict(h, Origin="https://evil.example"))
            self.assertEqual(r.code, 403, m)
            r = self.fetch("/v2/api/_test", method=m,
                           body=None if m == "DELETE" else "{}", headers=h)
            self.assertEqual(r.code, 403, m)
        h3 = dict(h, Origin=ORIGIN)
        r = self.fetch("/v2/api/_test", method="POST", body="{}", headers=h3)
        self.assertEqual(r.code, 200)

    def test_static_index_not_served(self):
        (self.static / "index.html").write_text("<p>secret</p>")
        (self.static / "app.js").write_text("var a=1;")
        r = self.fetch("/v2/static/index.html")
        self.assertEqual(r.code, 404)
        r = self.fetch("/v2/static/Index.html")
        self.assertEqual(r.code, 404)
        r = self.fetch("/v2/static/app.js")
        self.assertEqual(r.code, 200)

    def test_root_without_session_401_guidance(self):
        r = self.fetch("/v2/", follow_redirects=False)
        self.assertEqual(r.code, 401)
        self.assertIn(GUIDE, r.body.decode())

    def test_root_with_session_serves_index(self):
        r = self.fetch("/v2/", headers=self.cookie("alice"))
        self.assertEqual(r.code, 404)  # index.html 없음
        (self.static / "index.html").write_text("<p>hello-v2</p>")
        r = self.fetch("/v2/", headers=self.cookie("alice"))
        self.assertEqual(r.code, 200)
        self.assertIn("hello-v2", r.body.decode())
        self.assertIn("text/html", r.headers["Content-Type"])


class StaticChecks(unittest.TestCase):
    def test_server_import_graph_clean(self):
        # Task 4·8 이 v2.api_read·v2.api_write 를 이 목록에 추가한다.
        code = ("import sys, v2.server, v2.handlers, v2.auth, v2.db; "
                "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
                "('config','streamlit','pyupbit','services','engine')); "
                "print('BAD:' + ','.join(bad))")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "BAD:")

    def test_server_code_has_no_upbit_host(self):
        for p in (ROOT / "v2").glob("*.py"):
            self.assertNotIn("api.upbit.com", p.read_text(encoding="utf-8"),
                             p.name)


if __name__ == "__main__":
    unittest.main()
