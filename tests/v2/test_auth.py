import ast
import base64
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from utils import v2_entry_token as et
from v2 import auth


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class AuthBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.secret = self.dir / "secret"
        self.allow = self.dir / "allow"
        self.secret.write_bytes(os.urandom(48))
        os.chmod(self.secret, 0o600)
        self._old = (et.SECRET_PATH, et.ALLOWLIST_PATH)
        et.SECRET_PATH = self.secret
        et.ALLOWLIST_PATH = self.allow
        self.addCleanup(self._restore)

    def _restore(self):
        et.SECRET_PATH, et.ALLOWLIST_PATH = self._old


class TokenTests(AuthBase):
    def test_roundtrip(self):
        t = et.make_token("alice_1", "TEST", now=1000.0)
        p = et.verify_token(t, now=1010.0)
        self.assertEqual(set(p), {"v", "user_id", "mode", "nonce", "exp"})
        self.assertEqual(p["user_id"], "alice_1")
        self.assertEqual(p["mode"], "TEST")
        self.assertEqual(p["v"], 1)
        self.assertEqual(p["exp"], 1000.0 + et.TOKEN_TTL_SEC)

    def test_token_expired_rejected(self):
        t = et.make_token("alice", "LIVE", now=1000.0)
        with self.assertRaises(et.TokenInvalid):
            et.verify_token(t, now=1061.0)

    def test_token_tampered_rejected(self):
        t = et.make_token("alice", "TEST", now=1000.0)
        body, sig = t.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        payload["user_id"] = "bob"
        forged = _b64e(json.dumps(payload).encode()) + "." + sig
        with self.assertRaises(et.TokenInvalid):
            et.verify_token(forged, now=1001.0)
        with self.assertRaises(et.TokenInvalid):
            et.verify_token("garbage", now=1001.0)

    def test_token_nonalphabet_char_rejected(self):
        t = et.make_token("alice", "TEST", now=1000.0)
        body, sig = t.split(".")
        for bad in (sig[:5] + "!" + sig[5:], sig[:5] + "\n" + sig[5:],
                    sig[:5] + "+" + sig[5:]):
            with self.assertRaises(et.TokenInvalid):
                et.verify_token(body + "." + bad, now=1001.0)
        self.assertIsNone(auth.read_session(body + "." + sig[:5] + "!" + sig[5:]))

    def test_token_noncanonical_signature_rejected(self):
        import string
        t = et.make_token("alice", "TEST", now=1000.0)
        body, sig = t.split(".")
        raw = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        alphabet = string.ascii_letters + string.digits + "-_"
        variants = []
        for c in alphabet:
            if c == sig[-1]:
                continue
            alt = sig[:-1] + c
            if base64.urlsafe_b64decode(alt + "=" * (-len(alt) % 4)) == raw:
                variants.append(alt)
        self.assertTrue(variants)
        for alt in variants:
            with self.assertRaises(et.TokenInvalid):
                et.verify_token(body + "." + alt, now=1001.0)

    def test_token_wrong_version_rejected(self):
        payload = {"v": 2, "user_id": "alice", "mode": "TEST",
                   "nonce": "n", "exp": 2000.0}
        body = _b64e(json.dumps(payload).encode())
        import hashlib
        import hmac
        sig = hmac.new(self.secret.read_bytes(), body.encode(),
                       hashlib.sha256).digest()
        with self.assertRaises(et.TokenInvalid):
            et.verify_token(body + "." + _b64e(sig), now=1000.0)

    def test_token_reuse_rejected(self):
        t = et.make_token("alice", "TEST", now=1000.0)
        p = et.verify_token(t, now=1001.0)
        store = auth.NonceStore()
        self.assertTrue(store.consume(p["nonce"], p["exp"], now=1001.0))
        self.assertFalse(store.consume(p["nonce"], p["exp"], now=1002.0))

    def test_nonce_store_purges_expired(self):
        store = auth.NonceStore()
        store.consume("a", 1060.0, now=1000.0)
        store.consume("b", 1060.0, now=1000.0)
        self.assertEqual(len(store), 2)
        self.assertTrue(store.consume("c", 1200.0, now=1100.0))
        self.assertEqual(len(store), 1)

    def test_missing_secret_unavailable(self):
        self.secret.unlink()
        with self.assertRaises(et.TokenUnavailable):
            et.make_token("alice", "TEST")
        with self.assertRaises(et.TokenUnavailable):
            et.verify_token("a.b")

    def test_short_secret_unavailable(self):
        self.secret.write_bytes(os.urandom(31))
        with self.assertRaises(et.TokenUnavailable):
            et.make_token("alice", "TEST")

    def test_unreadable_secret_unavailable(self):
        if os.geteuid() == 0:
            self.skipTest("root 는 권한 0 파일도 읽는다")
        os.chmod(self.secret, 0o000)
        with self.assertRaises(et.TokenUnavailable):
            et.make_token("alice", "TEST")

    def test_secret_read_each_call(self):
        t = et.make_token("alice", "TEST", now=1000.0)
        self.secret.write_bytes(os.urandom(48))
        with self.assertRaises(et.TokenInvalid):
            et.verify_token(t, now=1001.0)

    def test_make_token_rejects_bad_input(self):
        for uid in ("", "a b", "a" * 33, "한글", "a;b", None):
            with self.assertRaises(ValueError):
                et.make_token(uid, "TEST")
        for mode in ("test", "PAPER", "", None):
            with self.assertRaises(ValueError):
                et.make_token("alice", mode)

    def test_session_value_rejected_as_token(self):
        s = auth.make_session("alice", "TEST")
        with self.assertRaises(et.TokenInvalid):
            et.verify_token(s)

    def test_token_rejected_as_session(self):
        t = et.make_token("alice", "TEST")
        self.assertIsNone(auth.read_session(t))


class AllowlistTests(AuthBase):
    def test_allowlist_missing_or_unreadable_empty(self):
        self.assertEqual(et.load_allowlist(), frozenset())
        self.assertFalse(et.is_allowed("alice"))
        self.allow.write_text("alice\n")
        if os.geteuid() != 0:
            os.chmod(self.allow, 0o000)
            self.assertEqual(et.load_allowlist(), frozenset())
        self.assertEqual(et.load_allowlist(self.dir / "nope"), frozenset())

    def test_allowlist_comments(self):
        self.allow.write_text(
            "# 주석\n\nalice\n  bob_2  \ncarol # 뒤 주석\n")
        self.assertEqual(et.load_allowlist(),
                         frozenset({"alice", "bob_2", "carol"}))
        self.assertTrue(et.is_allowed("alice"))
        self.assertFalse(et.is_allowed("mallory"))
        self.assertFalse(et.is_allowed("a b"))

    def test_allowlist_read_each_call(self):
        self.allow.write_text("alice\n")
        self.assertFalse(et.is_allowed("dave"))
        self.allow.write_text("alice\ndave\n")
        self.assertTrue(et.is_allowed("dave"))


class SessionTests(AuthBase):
    def test_session_roundtrip(self):
        s = auth.make_session("alice", "LIVE")
        p = auth.read_session(s)
        self.assertEqual(p["user_id"], "alice")
        self.assertEqual(p["mode"], "LIVE")
        self.assertEqual(p["typ"], "session")
        self.assertGreater(p["exp"], 0)

    def test_session_expired_none(self):
        s = auth.make_session("alice", "TEST", now=1000.0)
        self.assertIsNotNone(auth.read_session(s, now=1000.0 + 100))
        self.assertIsNone(
            auth.read_session(s, now=1000.0 + auth.SESSION_TTL_SEC + 1))

    def test_session_tampered_or_garbage_none(self):
        s = auth.make_session("alice", "TEST")
        body, sig = s.split(".")
        self.assertIsNone(auth.read_session(body + "." + sig[:-2] + "AA"))
        for bad in ("", "x", "a.b", ".", None, "a.b.c"):
            self.assertIsNone(auth.read_session(bad))

    def test_session_no_secret(self):
        s = auth.make_session("alice", "TEST")
        self.secret.unlink()
        self.assertIsNone(auth.read_session(s))
        with self.assertRaises(et.TokenUnavailable):
            auth.make_session("alice", "TEST")

    def _signed(self, payload):
        return et.sign_payload(payload)

    def test_session_wrong_typ_none(self):
        base = {"user_id": "alice", "mode": "TEST", "exp": 9e12}
        self.assertIsNotNone(
            auth.read_session(self._signed(dict(base, typ="session"))))
        self.assertIsNone(
            auth.read_session(self._signed(dict(base, typ="entry"))))
        self.assertIsNone(auth.read_session(self._signed(dict(base))))

    def test_session_extra_or_missing_key_none(self):
        full = {"typ": "session", "user_id": "alice", "mode": "TEST",
                "exp": 9e12}
        self.assertIsNone(auth.read_session(self._signed(dict(full, x=1))))
        for k in ("user_id", "mode", "exp"):
            p = dict(full)
            del p[k]
            self.assertIsNone(auth.read_session(self._signed(p)))

    def test_session_bad_mode_none(self):
        for mode in ("PAPER", "test", "", None):
            p = {"typ": "session", "user_id": "alice", "mode": mode,
                 "exp": 9e12}
            self.assertIsNone(auth.read_session(self._signed(p)))

    def test_make_session_rejects_bad_input(self):
        for uid in ("", "a b", "a" * 33, "한글", None):
            with self.assertRaises(ValueError):
                auth.make_session(uid, "TEST")
        for mode in ("PAPER", "test", "", None):
            with self.assertRaises(ValueError):
                auth.make_session("alice", mode)

    def test_cookie_constants(self):
        self.assertEqual(auth.SESSION_COOKIE, "v2s")
        self.assertEqual(auth.SESSION_TTL_SEC, 43200)


class StdlibOnlyTests(unittest.TestCase):
    def test_entry_token_stdlib_only(self):
        allowed = {"hmac", "hashlib", "secrets", "base64", "json", "time",
                   "pathlib", "os", "typing"}
        src = Path(et.__file__).read_text(encoding="utf-8")
        found = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        self.assertLessEqual(found, allowed, found - allowed)


if __name__ == "__main__":
    unittest.main()
