"""
2차 배포 요청서 2-1 3 · B7: scripts/v2/migration_dryrun.py 시험.

옛 DB(2차 전 스키마 = 새 표 3개·새 칸 2개 없음 + 행 몇 개)에 돌리면 PASS, 이미 마이그레이션한 DB 에도 PASS,
services/data 아래 파일·이름이 다른 파일은 거부(종료 코드 2). 임시 DB 만 쓴다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_30_b7_migration_dryrun -v
"""
from __future__ import annotations

import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from scripts.v2 import migration_dryrun as md  # noqa: E402

U = "b7dry"


class TestMigrationDryrun(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="b7dry_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.db_path = os.path.join(self.tmpdir, f"tradebot_{U}.db")
        with mock.patch("services.init_db.get_db_path", return_value=self.db_path), \
             mock.patch("services.db.get_db_path", return_value=self.db_path):
            import services.init_db as idb
            idb.initialize_db(U)
            idb.ensure_all_schemas(U)
        conn = sqlite3.connect(self.db_path)
        try:
            for t in md.NEW_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            for t, c in md.NEW_COLUMNS:
                conn.execute(f"ALTER TABLE {t} DROP COLUMN {c}")
            for i in range(3):
                conn.execute("INSERT INTO audit_trades (ticker, interval_sec, bar, type, reason, price) "
                             "VALUES ('KRW-TEST', 180, ?, 'BUY', 'EMA_GC', 100.0)", (i,))
            conn.commit()
        finally:
            conn.close()

    def _check(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = md.check(self.db_path, U)
        return ok, buf.getvalue()

    def test_old_db_passes_and_marks_max_id(self):
        ok, out = self._check()
        self.assertTrue(ok, out)
        self.assertIn("audit_trades.strategy_type not_null=0 legacy_max_id=3 expect=3", out)
        self.assertIn("RESULT PASS", out)
        rows = sqlite3.connect(self.db_path).execute("SELECT COUNT(*) FROM audit_trades").fetchone()[0]
        self.assertEqual(rows, 3)

    def test_already_migrated_db_passes(self):
        self.assertTrue(self._check()[0])
        ok, out = self._check()
        self.assertTrue(ok, out)
        self.assertIn("column existed before", out)

    def test_detects_row_loss(self):
        real = md.run_boot_migration

        def lossy(path, user_id):
            real(path, user_id)
            c = sqlite3.connect(path)
            c.execute("DELETE FROM audit_trades WHERE id=1")
            c.commit()
            c.close()

        with mock.patch.object(md, "run_boot_migration", lossy):
            ok, out = self._check()
        self.assertFalse(ok)
        self.assertIn("audit_trades:changed", out)

    def test_cli_runs_with_empty_keys_env(self):
        """적힌 명령 그대로(빈 UPBIT 키 환경)에서 CLI 가 RESULT PASS·rc 0 (Fable 1030 막음 1)."""
        import subprocess
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("UPBIT_", "TELEGRAM_", "PYTHONPATH", "NETGUARD"))}
        env["UPBIT_ACCESS"] = ""
        env["UPBIT_SECRET"] = ""
        p = subprocess.run([sys.executable, os.path.join(md.ROOT, "scripts", "v2", "migration_dryrun.py"),
                            self.db_path], capture_output=True, text=True, env=env, cwd=md.ROOT, timeout=120)  # 실행 위치 = 저장소(2-1 3)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("RESULT PASS", p.stdout)

    def test_refuses_repo_data_dir_and_bad_name(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(md.main(["x", os.path.join(md.ROOT, "services", "data", "tradebot_mcmax33.db")]), 2)
            bad = os.path.join(self.tmpdir, "copy.db")
            open(bad, "w").close()
            self.assertEqual(md.main(["x", bad]), 2)
            self.assertEqual(md.main(["x"]), 2)


if __name__ == "__main__":
    unittest.main()
