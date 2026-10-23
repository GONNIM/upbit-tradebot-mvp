import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

from utils import v2_entry_token as et
from v2 import db

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "v2" / "dev_server.py"


def load_script():
    spec = importlib.util.spec_from_file_location("dev_server", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # main() 은 __main__ 일 때만 호출되므로 서버가 뜨지 않는다
    return mod


def _inside(path, root):
    p = Path(path).resolve()
    return p == root.resolve() or root.resolve() in p.parents


class DevServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mod = load_script()
        self._old = (db.REPO_ROOT, db.DATA_DIR, et.SECRET_PATH, et.ALLOWLIST_PATH,
                     et.REPO_ROOT)
        self.addCleanup(self._restore)

    def _restore(self):
        (db.REPO_ROOT, db.DATA_DIR, et.SECRET_PATH, et.ALLOWLIST_PATH,
         et.REPO_ROOT) = self._old

    def test_fake_root_paths_inside_tmp(self):
        paths = self.mod.build_fake_root(self.root)
        self.assertTrue(paths)
        for k, p in paths.items():
            self.assertTrue(_inside(p, self.root), (k, p))
            self.assertTrue(Path(p).exists(), (k, p))

    def test_point_modules_to_redirects_all_paths(self):
        self.mod.build_fake_root(self.root)
        self.mod.point_modules_to(self.root)
        for name, p in (("db.REPO_ROOT", db.REPO_ROOT), ("db.DATA_DIR", db.DATA_DIR),
                        ("et.SECRET_PATH", et.SECRET_PATH),
                        ("et.ALLOWLIST_PATH", et.ALLOWLIST_PATH),
                        ("et.REPO_ROOT", et.REPO_ROOT)):
            self.assertTrue(_inside(p, self.root), (name, p))

    def test_secret_file_600_and_32_bytes(self):
        paths = self.mod.build_fake_root(self.root)
        sp = Path(paths["secret"])
        self.assertEqual(stat.S_IMODE(sp.stat().st_mode), 0o600)
        self.assertEqual(len(sp.read_bytes()), 32)

    def test_fake_db_readable_by_v2_query(self):
        self.mod.build_fake_root(self.root)
        self.mod.point_modules_to(self.root)
        rows = db.query("devuser", "SELECT id, timestamp FROM audit_buy_eval "
                        "ORDER BY id DESC LIMIT 5")
        self.assertGreater(len(rows), 0)
        sells = db.query("devuser", "SELECT triggered, trigger_key FROM audit_sell_eval "
                         "ORDER BY id DESC LIMIT 50")
        self.assertIn(1, [r["triggered"] for r in sells])
        self.assertIn("Stop Loss", [r["trigger_key"] for r in sells])
        logs = db.query("devuser", "SELECT id FROM logs ORDER BY id DESC LIMIT 100")
        self.assertEqual(len(logs), 60)
        self.assertEqual(db.active_strategy("devuser")[0], "EMA")
        self.assertEqual(db.strategy_params("devuser", "EMA")["interval"], "minute3")
        self.assertTrue(et.is_allowed("devuser"))
        self.assertIsNotNone(db.app_version())

    def test_default_port_is_8512_not_production_8502(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("default=8512", text)
        self.assertNotIn("default=8502", text)
        self.assertIn("운영 서버에서 실행하지 말 것", text)

    def test_dev_server_not_imported_by_v2(self):
        for p in (ROOT / "v2").glob("*.py"):
            self.assertNotIn("dev_server", p.read_text(encoding="utf-8"), p.name)


if __name__ == "__main__":
    unittest.main()
