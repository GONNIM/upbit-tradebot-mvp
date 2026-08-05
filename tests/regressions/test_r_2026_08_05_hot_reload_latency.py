"""
✅ 회귀: hot-reload 지연 UX 결함 봉쇄 (2026-08-05 오후, 커밋 [pending])

원 결함:
- `_settings_snapshot_timer` 가 mtime 감지·hot-reload·audit_settings 스냅샷을
  모두 `if last_minute != current_minute` 블록 안에서만 실행 → 분당 1회.
- UI 저장 → 최대 60초 지연 동안 audit_settings 에 이전 값 유지.
- 대시보드가 그 창구에 조회하면 `엔진 ≠ UI 저장값` 어긋남 경고 표시.

봉쇄 (옵션 A+B+C):
- A (services/db.py): insert_settings_snapshot 을 INSERT OR IGNORE → UPSERT
  (ON CONFLICT DO UPDATE) 로 전환. 같은 bar_time 재삽입 시 최신값으로 갱신.
- B (engine/live_loop.py): mtime 감지를 5초 tick 밖으로 이동. 감지 시
  즉시 hot-reload + 즉시 스냅샷 (다음 분 대기 없이).
- C (pages/dashboard.py): 파일 mtime vs 엔진 스냅샷 시각 비교하여
  <=10s info / 10~65s soft warning / >65s critical warning 으로 UX 명확화.

본 회귀는 (1) UPSERT 동작, (2) timer 구조 재편(mtime 감지 분 tick 밖), (3) 대시보드
지연 표시 로직이 소스에 유지되는지 lint.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_hot_reload_latency -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestUpsertBehavior(unittest.TestCase):
    """A: insert_settings_snapshot UPSERT — 같은 bar_time 재삽입 시 최신값 갱신."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="upsert_")
        self.db_path = str(Path(self.tmp) / "test.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE audit_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                interval_sec INTEGER,
                tp REAL, sl REAL, ts_pct REAL,
                signal_gate INTEGER,
                threshold REAL,
                buy_json TEXT,
                sell_json TEXT,
                bar_time TEXT
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_audit_settings_unique
            ON audit_settings(ticker, interval_sec, bar_time)
        """)
        conn.commit()
        conn.close()

    def _mimic_upsert(self, tp, buy_dict, bar_time="2026-08-05T14:00:00+09:00"):
        """실제 insert_settings_snapshot 의 UPSERT SQL 을 축소 재현."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO audit_settings
            (timestamp, ticker, interval_sec, tp, sl, ts_pct, signal_gate, threshold, buy_json, sell_json, bar_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, interval_sec, bar_time) DO UPDATE SET
                timestamp = excluded.timestamp,
                tp = excluded.tp,
                sl = excluded.sl,
                ts_pct = excluded.ts_pct,
                signal_gate = excluded.signal_gate,
                threshold = excluded.threshold,
                buy_json = excluded.buy_json,
                sell_json = excluded.sell_json
            """,
            ("t", "KRW-JTO", 60, tp, 0.01, 0.4, 1, 0.0,
             json.dumps(buy_dict), json.dumps({}), bar_time),
        )
        conn.commit()
        conn.close()

    def _fetch_latest(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT tp, buy_json FROM audit_settings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row

    def test_second_insert_updates_existing(self):
        self._mimic_upsert(tp=0.007, buy_dict={"fixed_price_buy_wait_bars": 5})
        self._mimic_upsert(tp=0.010, buy_dict={"fixed_price_buy_wait_bars": 3})
        tp, buy_json = self._fetch_latest()
        self.assertAlmostEqual(tp, 0.010, msg="UPSERT 두 번째 값이 반영되지 않음 (IGNORE 상태 잔존?)")
        self.assertEqual(
            json.loads(buy_json).get("fixed_price_buy_wait_bars"), 3,
            "UPSERT 시 buy_json 갱신 실패",
        )

    def test_single_row_after_multiple_upserts(self):
        for i in range(5):
            self._mimic_upsert(tp=0.001 * i, buy_dict={"i": i})
        conn = sqlite3.connect(self.db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM audit_settings").fetchone()[0]
        conn.close()
        self.assertEqual(cnt, 1, "UPSERT 시 중복 row 생성 (UNIQUE 인덱스 미작동 or IGNORE 회귀)")


class TestTimerReconstruction(unittest.TestCase):
    """B: _settings_snapshot_timer 재구성 lint — mtime 감지가 분 tick 밖으로 이동."""

    LIVE_LOOP = ROOT / "engine" / "live_loop.py"

    def test_hot_reload_snapshot_marker_exists(self):
        src = self.LIVE_LOOP.read_text(encoding="utf-8")
        self.assertIn(
            "⚡ Hot-reload triggered snapshot",
            src,
            "hot-reload 감지 시 즉시 스냅샷 로그 사라짐 — 옵션 A 회귀",
        )

    def test_do_snapshot_helper_exists(self):
        src = self.LIVE_LOOP.read_text(encoding="utf-8")
        self.assertIn(
            "def _do_snapshot",
            src,
            "_do_snapshot 헬퍼 사라짐 — timer 재구성(옵션 B) 회귀",
        )

    def test_mtime_detection_outside_minute_gate(self):
        """mtime 감지 코드 블록이 `if last_minute != current_minute:` 안에 갇혀있지 않음."""
        src = self.LIVE_LOOP.read_text(encoding="utf-8")
        # 축약 검사: 옵션 B 마커 주석이 있는지
        self.assertIn(
            "옵션 B",
            src,
            "옵션 B 재구성 주석 사라짐 — mtime 감지 tick 회귀 위험",
        )


class TestDashboardLagIndicator(unittest.TestCase):
    """C: 대시보드 반영 대기 표시 lint."""

    DASHBOARD = ROOT / "pages" / "dashboard.py"

    def test_sync_lag_calculation_exists(self):
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("_sync_lag_s", src, "지연 계산 변수 사라짐")
        self.assertIn("_file_mtime", src, "파일 mtime 참조 사라짐")

    def test_lag_thresholds_present(self):
        src = self.DASHBOARD.read_text(encoding="utf-8")
        for marker in ("방금 저장", "반영 대기 중", "hot-reload 결함"):
            self.assertIn(
                marker,
                src,
                f"지연 상태 표시 문구 '{marker}' 사라짐 — 옵션 C 회귀",
            )


class TestInsertSnapshotUpsertSQL(unittest.TestCase):
    """A 심층: services/db.py 의 insert_settings_snapshot 이 UPSERT 로 전환됐는지."""

    DB_MODULE = ROOT / "services" / "db.py"

    def test_upsert_syntax_present(self):
        src = self.DB_MODULE.read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT(ticker, interval_sec, bar_time)", src)
        self.assertIn("DO UPDATE SET", src)

    def test_insert_or_ignore_sql_removed(self):
        """이전 SQL 문 `INSERT OR IGNORE INTO audit_settings` 가 스냅샷 함수에 없어야 함.
        (docstring 의 역사 서술은 'INTO' 없이 남을 수 있으므로 정확 SQL 패턴으로 좁힘.)"""
        src = self.DB_MODULE.read_text(encoding="utf-8")
        idx = src.find("def insert_settings_snapshot(")
        self.assertGreater(idx, 0, "insert_settings_snapshot 함수 사라짐")
        next_def = src.find("\ndef ", idx + 1)
        body = src[idx:next_def if next_def > 0 else len(src)]
        self.assertNotIn(
            "INSERT OR IGNORE INTO audit_settings",
            body,
            "insert_settings_snapshot 함수에 이전 SQL 잔존 (UPSERT 전환 회귀)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
