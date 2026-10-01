"""
✅ WO-14 (c) 회귀: audit_settings UNIQUE 인덱스 매 호출 재생성 제거 (2026-10-01)

원 결함:
- services/init_db.ensure_audit_settings_unique() 가 호출마다 DROP INDEX → CREATE UNIQUE INDEX.
  audit_settings 184,028행 재생성에 1~10초, DROP~CREATE 사이 UNIQUE 인덱스 부재로
  설정 스냅샷 upsert(ON CONFLICT(ticker, interval_sec, bar_time)) 실패
  (2026-09-30 19:44:30·35 `[SETTINGS-SNAPSHOT] ❌ Failed: ON CONFLICT ...`) + 워밍업 기록 database is locked.

계획서 §2 (c) 재현 테스트 4건.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo14c_index_idempotent -v
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_01_wo14c"
TARGET = (True, ["ticker", "interval_sec", "bar_time"])


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo14c_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        initialize_db(U)
        ensure_all_schemas(U)
        import services.init_db as idb
        self.idb = idb

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _state(self):
        conn = sqlite3.connect(self.db_path)
        try:
            return self.idb._audit_settings_unique_state(conn)
        finally:
            conn.close()

    def _traced_calls(self, n: int) -> list[str]:
        """ensure_audit_settings_unique() 를 n 번 부르며 실행 SQL 을 수집."""
        stmts: list[str] = []
        orig = self.idb._connect

        def _traced(user_id):
            conn = orig(user_id)
            conn.set_trace_callback(stmts.append)
            return conn

        with patch.object(self.idb, "_connect", _traced):
            for _ in range(n):
                self.idb.ensure_audit_settings_unique(U)
        return stmts


class TestIndexIdempotent(_DbCase):

    def test_1_target_index_present_no_drop(self):
        """목표 인덱스가 있으면 두 번 불러도 DROP INDEX 0건, 인덱스 유지."""
        self.assertEqual(self._state(), TARGET)
        stmts = self._traced_calls(2)
        drops = [s for s in stmts if "DROP INDEX" in s.upper()]
        creates = [s for s in stmts if "CREATE UNIQUE INDEX" in s.upper()]
        self.assertEqual(drops, [], f"DROP 실행됨: {drops}")
        self.assertEqual(creates, [], f"CREATE 실행됨: {creates}")
        self.assertEqual(self._state(), TARGET)

    def test_2_missing_index_created_once(self):
        """인덱스가 없으면 CREATE UNIQUE INDEX 1회, DROP 없음, 이후 존재."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP INDEX idx_audit_settings_unique")
        conn.commit()
        conn.close()
        self.assertIsNone(self._state())

        stmts = self._traced_calls(2)
        drops = [s for s in stmts if "DROP INDEX" in s.upper()]
        creates = [s for s in stmts if "CREATE UNIQUE INDEX" in s.upper()]
        self.assertEqual(drops, [])
        self.assertEqual(len(creates), 1)
        self.assertEqual(self._state(), TARGET)

    def test_3_old_definition_rebuilt_with_warning(self):
        """열 구성이 다른 옛 인덱스(timestamp 기준) → DROP·CREATE 로 목표 구성 + 경고 1줄."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP INDEX idx_audit_settings_unique")
        conn.execute(
            "CREATE UNIQUE INDEX idx_audit_settings_unique "
            "ON audit_settings(ticker, interval_sec, timestamp)"
        )
        conn.commit()
        conn.close()
        self.assertEqual(self._state(), (True, ["ticker", "interval_sec", "timestamp"]))

        with self.assertLogs("services.init_db", level="WARNING") as cm:
            stmts = self._traced_calls(1)
        warns = [m for m in cm.output if "ensure_audit_settings_unique 재생성" in m]
        self.assertEqual(len(warns), 1, cm.output)
        self.assertIn("열=ticker,interval_sec,timestamp", warns[0])
        self.assertEqual(len([s for s in stmts if "DROP INDEX" in s.upper()]), 1)
        self.assertEqual(self._state(), TARGET)

        # 재생성 후 다시 부르면 아무것도 하지 않음
        stmts2 = self._traced_calls(1)
        self.assertEqual([s for s in stmts2 if "INDEX" in s.upper() and "PRAGMA" not in s.upper()], [])

    def test_4_concurrent_upsert_never_fails(self):
        """다른 연결이 설정 스냅샷 upsert 를 반복하는 동안 반복 호출 → upsert 실패 0건."""
        # 인덱스 재생성 시간이 의미 있도록 행을 채운다 (옛 코드에서는 이 상태로 실패 재현)
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO audit_settings (timestamp, ticker, interval_sec, tp, sl, ts_pct, "
            "signal_gate, threshold, buy_json, sell_json, bar_time) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ("2026-09-01T00:00:00", "KRW-T%03d" % (i % 500), 300, 0.05, 0.02, 0.1,
                 1, 0.0, "{}", "{}", "2026-09-01T%05d" % i)
                for i in range(60000)
            ),
        )
        conn.commit()
        conn.close()

        from services.db import insert_settings_snapshot

        errors: list[str] = []
        stop = threading.Event()

        def _upserter():
            i = 0
            while not stop.is_set():
                try:
                    insert_settings_snapshot(
                        U, "KRW-JTO", 300, 0.05, 0.02, 0.1, True, 0.0, {}, {},
                        bar_time="2026-10-01T10:%02d:00" % (i % 60),
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e))
                i += 1

        t = threading.Thread(target=_upserter, daemon=True)
        t.start()
        try:
            for _ in range(15):
                self.idb.ensure_audit_settings_unique(U)
        finally:
            stop.set()
            t.join(timeout=30)

        on_conflict = [e for e in errors if "ON CONFLICT" in e]
        self.assertEqual(on_conflict, [], f"upsert 실패 {len(on_conflict)}건: {on_conflict[:2]}")
        self.assertEqual(self._state(), TARGET)


if __name__ == "__main__":
    unittest.main()
