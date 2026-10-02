"""
✅ WO-19 회귀: 워밍업이 실제 판정 감사 행을 WARMUP 자리표시자로 덮어쓰지 않음 (2026-10-02)

원 결함:
- 기동마다 워밍업 버퍼를 채우며 StrategyEngine.record_warmup_log → insert_buy_eval 실시간 분기로 들어가,
  같은 bar_time 의 기존 행을 "실시간 재판정" 으로 UPDATE — 기존 행이 실제 판정인지 자리표시자인지 구분 없음.
- 최근 7일 KRW-JTO audit_buy_eval WARMUP 566행 중 539행이 실시간 판정 뒤 덮인 것(journal 확인).
  예: 2026-10-01 14:10 봉(14:15 봇 매수 체결 봉) id 74864 가 10-01 20:11:03 기동 때 "WARMUP (완료 129/200)" 으로 덮임.
- 포지션 보유 중 기동이면 같은 경로가 insert_sell_eval 로 가 SELL 평가 행을 덮는다.

처방: 워밍업은 자기 자리표시자(checks.status == "WARMUP")만 갱신, 실제 판정 행은 건드리지 않음, 행이 없으면 삽입.
실시간 판정이 WARMUP 자리표시자를 덮는 기존 동작은 유지.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_02_wo19_warmup_audit_preserve -v
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_02_wo19"
T = "KRW-JTO"
BAR_UTC = datetime(2026, 10, 1, 5, 10, tzinfo=timezone.utc)   # = 2026-10-01 14:10 KST (봇 매수 체결 봉)
BAR_KST = "2026-10-01T14:10:00+09:00"
REAL_CHECKS = {"ema_gc": True, "ema_fast": 736.39, "ema_slow": 736.16, "strategy_mode": "EMA"}


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo19_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(U)
        ensure_all_schemas(U)
        ensure_schema(U)
        import services.db as db
        self.db = db

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _engine(self, has_position=False):
        from core.strategy_engine import StrategyEngine
        e = StrategyEngine.__new__(StrategyEngine)
        e.user_id, e.ticker, e.interval_sec, e.bar_count = U, T, 300, 129
        e.strategy_type = "EMA"
        e.strategy = MagicMock(enable_base_ema_gap=False)
        e.position = MagicMock(has_position=has_position)
        return e

    def _bar(self, close=749.0):
        from core.candle_buffer import Bar
        return Bar(ts=BAR_UTC, open=close, high=close, low=close, close=close, volume=1.0, is_closed=True)

    def _row(self, table="audit_buy_eval"):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        r = con.execute(f"SELECT * FROM {table} WHERE ticker=? AND bar_time=?", (T, BAR_KST)).fetchall()
        con.close()
        return [dict(x) for x in r]

    def _real_buy(self, price=749.0):
        self.db.insert_buy_eval(
            user_id=U, ticker=T, interval_sec=300, bar=210, price=price, macd=None, signal=None,
            have_position=False, overall_ok=True, failed_keys=None, checks=REAL_CHECKS,
            notes="🟢 BUY | Golden | bar=210", bar_time=BAR_KST,
        )


class TestWarmupAuditPreserve(_DbCase):

    def test_1_real_row_kept(self):
        """(1) 실제 판정 행이 있을 때 워밍업 호출 → 행 불변, 결과 'kept'. (옛 코드: WARMUP 으로 덮여 실패)"""
        self._real_buy()
        before = self._row()
        res = self._engine().record_warmup_log(self._bar(), "(완료 129/200)")
        after = self._row()
        self.assertEqual(len(after), 1)
        self.assertEqual(after, before)
        self.assertEqual(after[0]["overall_ok"], 1)
        self.assertNotIn("WARMUP", after[0]["notes"] or "")
        self.assertEqual(res, "kept")

    def test_2_warmup_row_updated(self):
        """(2) WARMUP 자리표시자 행이 있을 때 → 갱신(진행 표기 바뀜), 결과 'updated_placeholder'."""
        eng = self._engine()
        self.assertEqual(eng.record_warmup_log(self._bar(), "(완료 10/200)"), "inserted")
        res = eng.record_warmup_log(self._bar(750.0), "(완료 129/200)")
        rows = self._row()
        self.assertEqual(len(rows), 1)
        self.assertEqual(res, "updated_placeholder")
        self.assertEqual(json.loads(rows[0]["checks"])["status"], "WARMUP")
        self.assertIn("(완료 129/200)", rows[0]["notes"])
        self.assertEqual(rows[0]["price"], 750.0)

    def test_3_no_row_inserted(self):
        """(3) 행 없음 → 자리표시자 삽입, 결과 'inserted'."""
        res = self._engine().record_warmup_log(self._bar(), "(완료 1/200)")
        rows = self._row()
        self.assertEqual(res, "inserted")
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["checks"])["status"], "WARMUP")
        self.assertEqual(rows[0]["overall_ok"], 0)

    def test_4_realtime_overwrites_placeholder(self):
        """(4) 워밍업 뒤 실시간 판정 → WARMUP 자리표시자를 덮음 (기존 동작 유지)."""
        self._engine().record_warmup_log(self._bar(), "(완료 200/200)")
        self._real_buy(price=751.0)
        rows = self._row()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("status", json.loads(rows[0]["checks"]))
        self.assertEqual(rows[0]["overall_ok"], 1)
        self.assertEqual(rows[0]["price"], 751.0)

    def test_5_sell_path_same_rule(self):
        """(추가) 포지션 보유 중 기동(SELL 경로)도 같은 규칙: 실제 SELL 판정 행 보존, 없으면 삽입."""
        self.db.insert_sell_eval(
            user_id=U, ticker=T, interval_sec=300, bar=331, price=749.0, macd=None, signal=None,
            tp_price=760.0, sl_price=741.0, highest=None, ts_pct=None, ts_armed=False, bars_held=1,
            checks={"stop_loss": False, "ema_dc": False}, triggered=False, trigger_key=None,
            notes="HOLD", bar_time=BAR_KST,
        )
        before = self._row("audit_sell_eval")
        res = self._engine(has_position=True).record_warmup_log(self._bar(), "(완료 129/200)")
        self.assertEqual(res, "kept")
        self.assertEqual(self._row("audit_sell_eval"), before)

    def test_6_boot_log_line(self):
        """(추가) 기동마다 1줄 '[WARMUP] 감사 행 보존 | kept=N inserted=M updated_placeholder=K'."""
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn('f"[WARMUP] 감사 행 보존 | kept={_wu_audit.get(\'kept\', 0)} "', src)
        self.assertIn("_wu_res = engine.record_warmup_log(bar,", src)


if __name__ == "__main__":
    unittest.main()
