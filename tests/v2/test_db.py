import ast
import json
import os
import re
import sqlite3
import stat
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from v2 import db


class DbTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data = self.root / "services" / "data"
        self.data.mkdir(parents=True)
        self._old = (db.REPO_ROOT, db.DATA_DIR)
        db.REPO_ROOT = self.root
        db.DATA_DIR = self.data

    def tearDown(self):
        db.REPO_ROOT, db.DATA_DIR = self._old
        self._tmp.cleanup()

    def make_live(self, user="u1"):
        p = self.data / f"tradebot_{user}.db"
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE t(a INTEGER)")
        c.execute("INSERT INTO t VALUES (1)")
        c.commit()
        c.close()
        return p


class TestDb(DbTestBase):
    def test_valid_user_id(self):
        self.assertTrue(db.valid_user_id("mcmax33"))
        for bad in ("", "../x", "a" * 33, "a-b"):
            self.assertFalse(db.valid_user_id(bad), bad)

    def test_open_live_ro_missing_creates_nothing(self):
        before = sorted(os.listdir(self.data))
        with self.assertRaises(FileNotFoundError):
            db.open_live_ro("u1")
        self.assertEqual(before, sorted(os.listdir(self.data)))

    def test_live_ro_insert_rejected(self):
        self.make_live()
        conn = db.open_live_ro("u1")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO t VALUES (2)")
        finally:
            conn.close()

    def test_query_requires_limit(self):
        self.make_live()
        with self.assertRaises(ValueError):
            db.query("u1", "SELECT * FROM t")
        self.assertEqual(db.query("u1", "SELECT a FROM t LIMIT 5"), [{"a": 1}])

    def test_query_limit_must_be_at_end(self):
        self.make_live()
        bad = ["SELECT a FROM t WHERE a IN (SELECT a FROM t LIMIT 1)",
               "SELECT a FROM t -- limit 5",
               "SELECT a FROM t /* limit 5 */",
               "SELECT a FROM t LIMIT 5 ORDER BY a",
               "SELECT 'limit 5' AS x FROM t"]
        for sql in bad:
            with self.assertRaises(ValueError, msg=sql):
                db.query("u1", sql)
        self.assertEqual(db.query("u1", "SELECT a FROM t LIMIT ? OFFSET 0 ;", (3,)),
                         [{"a": 1}])

    def test_v2hist_name_not_tradebot_prefix(self):
        import glob
        self.make_live()
        db.open_v2hist("u1").close()
        self.assertFalse(db.v2hist_path("u1").name.startswith("tradebot_"))
        names = [os.path.basename(x) for x in glob.glob(str(self.data / "tradebot_*.db"))]
        self.assertEqual(names, ["tradebot_u1.db"])

    def test_open_v2hist_new_file_is_600(self):
        self.make_live()
        db.open_v2hist("u1").close()
        self.assertEqual(stat.S_IMODE(os.stat(db.v2hist_path("u1")).st_mode), 0o600)

    def test_query_time_limit_interrupts(self):
        self.make_live()
        sql = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) "
               "SELECT count(*) FROM c LIMIT 1")
        with self.assertRaises(sqlite3.OperationalError):
            db.query("u1", sql)

    def test_open_v2hist_not_created_without_live_db(self):
        before = sorted(os.listdir(self.data))
        with self.assertRaises(FileNotFoundError):
            db.open_v2hist("u1")
        self.assertEqual(before, sorted(os.listdir(self.data)))

    def test_open_v2hist_existing_empty_file_gets_table_and_600(self):
        self.make_live()
        p = db.v2hist_path("u1")
        p.write_bytes(b"")
        os.chmod(p, 0o644)
        conn = db.open_v2hist("u1")
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE name='v2_settings_history'"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_open_v2hist_created_when_live_exists(self):
        self.make_live()
        conn = db.open_v2hist("u1")
        conn.close()
        self.assertTrue(db.v2hist_path("u1").exists())

    def test_insert_history_columns(self):
        self.make_live()
        dash = self.root / "pages"
        dash.mkdir()
        (dash / "dashboard.py").write_text('x = "v1.2026.10.23.1200"\n', encoding="utf-8")
        raw = '{"a": 1,  "b":2}'
        rid = db.insert_history("u1", raw, "메모")
        conn = db.open_v2hist("u1")
        conn.row_factory = sqlite3.Row
        try:
            r = conn.execute("SELECT * FROM v2_settings_history WHERE id=?", (rid,)).fetchone()
        finally:
            conn.close()
        self.assertRegex(r["saved_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+09:00$")
        self.assertEqual(r["source_page"], "v2_backtester")
        self.assertEqual(r["strategy_type"], "PULLBACK")
        self.assertEqual(r["params_json"], raw)
        self.assertIsNone(r["conditions_json"])
        self.assertIsNone(r["applied_at"])
        self.assertEqual(r["note"], "메모")
        self.assertEqual(r["user_id"], "u1")
        self.assertRegex(r["app_version"], r"^v1\.\d{4}\.\d{2}\.\d{2}\.\d{4}$")

    def test_app_version_missing(self):
        self.assertIsNone(db.app_version())

    def test_parse_ts_both_formats(self):
        a = db.parse_ts("2026-10-23T10:00:00+09:00")
        b = db.parse_ts("2026-10-23 10:00:00")
        self.assertEqual(a, b)
        self.assertEqual(a.utcoffset(), timedelta(hours=9))
        self.assertRegex(db.now_kst_iso(), r"\+09:00$")

    def test_active_strategy_and_params(self):
        self.assertEqual(db.active_strategy("u1"), (None, None))
        f = self.root / "u1_active_strategy.txt"
        f.write_text("EMA\n", encoding="utf-8")
        val, ts = db.active_strategy("u1")
        self.assertEqual(val, "EMA")
        self.assertIsNotNone(db.parse_ts(ts))
        self.assertEqual(db.strategy_params("u1", "EMA"), {})
        (self.root / "u1_latest_params_EMA.json").write_text(
            json.dumps({"ema_fast": 7}), encoding="utf-8")
        self.assertEqual(db.strategy_params("u1", "EMA"), {"ema_fast": 7})
        self.assertEqual(db.pullback_params_path("u1"),
                         self.root / "u1_latest_params_PULLBACK.json")


class TestStdlibOnly(unittest.TestCase):
    def test_db_module_stdlib_only(self):
        allowed = {"sqlite3", "os", "re", "stat", "json", "time", "pathlib",
                   "datetime", "zoneinfo", "typing"}
        src = (Path(__file__).resolve().parents[2] / "v2" / "db.py").read_text(encoding="utf-8")
        found = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                found |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                found.add((n.module or "").split(".")[0])
        self.assertLessEqual(found, allowed, found - allowed)


if __name__ == "__main__":
    unittest.main()
