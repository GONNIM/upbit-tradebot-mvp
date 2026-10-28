"""
2차 T6: 분할 상태 새 테이블 `pullback_state` 마이그레이션 시험 (⚠ 스키마 변경 — 배포 승인 대상).

계획 T6 「마이그레이션」: 새 DB·기존 DB(테이블 없음) 모두 `ensure_all_schemas` 2회 →
테이블 1개·오류 0, 기존 테이블 행 수·칸 불변, `PRAGMA integrity_check == ok`.
임시 DB 만 쓴다(서버 DB·로컬 실 DB 를 열지 않는다).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t6_migration -v
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401

U = "p3t6mig"

EXPECTED_COLUMNS = [
    "user_id", "mode", "ticker", "interval", "entry_count", "pullback_count", "first_entry_ts",
    "first_entry_reason", "armed", "prev_golden", "trade_origin", "pending_fill", "fill_n", "inv_sum",
    "sizing_base_krw", "realized_pnl_krw", "qty", "cost_krw", "avg_price", "desync", "buy_fail_bar_ts",
    "params_sha256", "last_bar_ts", "updated_at",
]


class _TmpDb(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="p3t6mig_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.db_path = os.path.join(self.tmpdir, f"tradebot_{U}.db")
        for target in ("services.init_db.get_db_path", "services.db.get_db_path"):
            p = mock.patch(target, return_value=self.db_path)
            p.start()
            self.addCleanup(p.stop)
        import services.init_db as idb
        self.idb = idb

    def q(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def table_count(self, name):
        return self.q("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,))[0][0]

    def snapshot(self):
        """pullback_state 를 뺀 모든 테이블의 (칸 목록, 행 수)."""
        out = {}
        for (name,) in self.q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if name == "pullback_state":
                continue
            cols = [r[1:3] for r in self.q(f"PRAGMA table_info({name})")]
            n = self.q(f"SELECT COUNT(*) FROM {name}")[0][0]
            out[name] = (cols, n)
        return out

    def old_db(self):
        """T6 전 코드가 만든 DB = 지금 스키마에서 pullback_state 만 없는 DB + 행 몇 개."""
        self.idb.initialize_db(U)
        self.idb.ensure_all_schemas(U)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS pullback_state")
            conn.execute("INSERT OR REPLACE INTO users (username, display_name, virtual_krw, updated_at) "
                         "VALUES (?, ?, ?, ?)", (U, "u", 1_000_000, "2026-10-28T00:00:00+09:00"))
            conn.execute("INSERT INTO audit_trades (ticker, interval_sec, bar, type, reason, price) "
                         "VALUES ('KRW-TEST', 180, 1, 'BUY', 'EMA_GC', 100.0)")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.table_count("pullback_state"), 0)


class TestPullbackStateMigration(_TmpDb):
    def test_function_registered_in_ensure_all_schemas(self):
        self.assertTrue(hasattr(self.idb, "ensure_pullback_tables"))
        import ast
        src = (ROOT / "services/init_db.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "ensure_all_schemas")
        # 맨 끝에 추가 — 2차 T7 이 그 뒤에 ensure_trade_strategy_columns 를 더함(T7 시험이 마지막 줄을 고정)
        tail = [ast.unparse(s).strip() for s in fn.body[-2:]]
        self.assertEqual(tail, ["ensure_pullback_tables(user_id)", "ensure_trade_strategy_columns(user_id)"])

    def test_new_db_twice_one_table(self):
        self.idb.initialize_db(U)
        self.idb.ensure_all_schemas(U)
        self.idb.ensure_all_schemas(U)
        self.assertEqual(self.table_count("pullback_state"), 1)
        cols = [r[1] for r in self.q("PRAGMA table_info(pullback_state)")]
        self.assertEqual(cols, EXPECTED_COLUMNS)
        pk = [r[1] for r in sorted(self.q("PRAGMA table_info(pullback_state)"), key=lambda r: r[5]) if r[5] > 0]
        self.assertEqual(pk, ["user_id", "mode"])
        self.assertEqual(self.q("PRAGMA integrity_check")[0][0], "ok")

    def test_old_db_without_table_twice_rows_and_columns_unchanged(self):
        self.old_db()
        before = self.snapshot()
        self.idb.ensure_all_schemas(U)
        self.idb.ensure_all_schemas(U)
        self.assertEqual(self.table_count("pullback_state"), 1)
        self.assertEqual(self.snapshot(), before)  # 기존 테이블 칸·행 수 불변
        self.assertEqual(self.q("SELECT COUNT(*) FROM pullback_state")[0][0], 0)
        self.assertEqual(self.q("PRAGMA integrity_check")[0][0], "ok")
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])

    def test_mode_check_constraint(self):
        self.idb.initialize_db(U)
        self.idb.ensure_all_schemas(U)
        conn = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO pullback_state (user_id, mode, ticker, interval, updated_at) "
                             "VALUES ('u', 'DRY', 'KRW-TEST', 'minute3', 'x')")
        finally:
            conn.close()

    def test_engine_store_on_old_db_without_table_is_safe(self):
        """기존 DB(새 테이블 없음)에서 기동해도 문제없음: load → None, save → False(예외 없음), 테이블을 몰래 만들지 않음."""
        from services import pullback_state as pbs
        self.old_db()
        self.assertIsNone(pbs.load(U, "TEST"))
        ok = pbs.save(U, "TEST", {"ticker": "KRW-TEST", "interval": "minute3", "entry_count": 1})
        self.assertFalse(ok)
        self.assertFalse(pbs.reset_after_exit(U, "TEST", 0.0))
        self.assertEqual(self.table_count("pullback_state"), 0)  # 마이그레이션 함수만 만든다

    def test_store_does_not_create_missing_db_file(self):
        from services import pullback_state as pbs
        self.assertFalse(os.path.exists(self.db_path))
        self.assertIsNone(pbs.load(U, "TEST"))
        self.assertFalse(pbs.save(U, "TEST", {"ticker": "KRW-TEST", "interval": "minute3"}))
        self.assertFalse(os.path.exists(self.db_path))

    def test_revert_old_code_ignores_new_table(self):
        """되돌리기 무해성: 마이그레이션한 DB 에서 기존 쓰기 함수(insert_order·insert_trade_audit)가 그대로 동작."""
        self.idb.initialize_db(U)
        self.idb.ensure_all_schemas(U)
        from services.db import insert_order, insert_trade_audit
        insert_order(U, "KRW-TEST", "BUY", 100.0, 1.0, "completed")
        insert_trade_audit(user_id=U, ticker="KRW-TEST", interval_sec=180, bar=1, kind="BUY", reason="EMA_GC",
                           price=100.0, macd=None, signal=None, entry_price=None, entry_bar=None,
                           bars_held=None, tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None)
        self.assertEqual(self.q("SELECT COUNT(*) FROM orders")[0][0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM audit_trades")[0][0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM pullback_state")[0][0], 0)


if __name__ == "__main__":
    unittest.main()
