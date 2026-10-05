"""
✅ WO-22 회귀: 지갑 동기화 복원의 진입가 우선순위 + 지갑 0 닫힘의 외부 매도 기록 (2026-10-05)

원 결함 (docs/plans/2026-10-05-wo22-wallet-sync-entry/incident.md):
- 10-05 08:26 봇 매수(id 564, 1,739.904822개 @777) → 09:39:53 앱 지정가 매도로 전량 체결 → 09:42:11 지갑 0 으로 닫힘
  (orders·audit_trades 기록 없음).
- 10:58:26 앱 지정가 매수 13.05483028개 @766 → 10:59:05 매 봉 지갑 동기화가 "외부 매수 복원" 하면서
  account_positions 캐시(1분 주기, 아직 0) 다음으로 orders 의 마지막 봇 BUY(777, 이미 앱 매도됨)를 진입가로 차용
  → pnl −1.42% → STOP_LOSS 시장가 매도(765).
처방:
- 진입가 1) Upbit avg_buy_price 직접 → 2) account_positions.entry_price → 3) orders 마지막 봇 BUY (체결 수량 = 지갑 수량일 때만).
- 지갑 0 닫힘 때 audit_trades 에 HTS_SELL(외부 매도) 1행. get_last_open_buy_order / get_last_open_buy_trade 가 이 행을 청산으로 본다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_05_wo22_wallet_sync_entry -v
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_05_wo22"
T = "KRW-JTO"
KST = ZoneInfo("Asia/Seoul")
BOT_QTY = 1739.90482236
APP_QTY = 13.05483028


class _Engine:
    """StrategyEngine 의 지갑 동기화 함수만 그대로 붙인 최소 엔진 (구 코드에 없는 보조 함수는 있으면만 붙인다)."""

    def __init__(self, wallet_qty, upbit_avg=None, test_mode=False):
        from core.position_state import PositionState
        from core.strategy_engine import StrategyEngine
        self.trader = MagicMock()
        self.trader.test_mode = test_mode
        self.trader._coin_balance = MagicMock(return_value=wallet_qty)
        bal = [{"currency": "JTO", "balance": str(wallet_qty), "avg_buy_price": str(upbit_avg)}] if upbit_avg else []
        self.trader.upbit.get_balances = MagicMock(return_value=bal)
        self.position = PositionState()
        self.user_id, self.ticker, self.bar_count, self.interval_sec = U, T, 1009, 60
        for name in ("_reconcile_position_with_wallet", "_fetch_upbit_avg_buy_price", "_record_external_sell"):
            fn = getattr(StrategyEngine, name, None)
            if fn is not None:
                setattr(self, name, fn.__get__(self))

    def set_wallet(self, qty, upbit_avg=None):
        self.trader._coin_balance.return_value = qty
        self.trader.upbit.get_balances.return_value = (
            [{"currency": "JTO", "balance": str(qty), "avg_buy_price": str(upbit_avg)}] if upbit_avg else [])


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo22_"))
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
        self._bot_buy()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _sql(self, q, args=()):
        con = sqlite3.connect(self.db_path)
        rows = con.execute(q, args).fetchall()
        con.commit()
        con.close()
        return rows

    def _bot_buy(self):
        """10-05 08:26 봇 매수 id 564 (orders) + audit_trades BUY — 이후 앱 매도는 어디에도 기록되지 않았다."""
        self._sql("INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, provider_uuid, state, "
                  "requested_at, executed_at, executed_volume, avg_price, updated_at, entry_bar) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (U, "2026-10-05T08:25:12.246442+09:00", T, "BUY", 777.0, 0, "requested", "u-564", "FILLED",
                   "2026-10-05T08:25:12+09:00", "2026-10-05T08:26:52+09:00", BOT_QTY, 777.0,
                   "2026-10-05T08:26:53.247743+09:00", 951))
        self._sql("INSERT INTO audit_trades (timestamp, ticker, interval_sec, bar, type, reason, price) VALUES (?,?,?,?,?,?,?)",
                  ("2026-10-05T08:26:53.250364+09:00", T, 60, 951, "BUY", "EMA_GC", 777.0))

    def _cache(self, entry_price):
        self._sql("INSERT OR REPLACE INTO account_positions (user_id, ticker, virtual_coin, entry_price, meta) VALUES (?,?,?,?,?)",
                  (U, T, 0.0, entry_price, "{}"))

    def _held_bot_position(self, eng):
        eng.position.apply_entry(qty=BOT_QTY, avg_price=777.0, entry_bar=951,
                                 entry_ts=datetime(2026, 10, 5, 8, 26, 52, tzinfo=KST), source="bot_limit_fill")


class TestWo22(_DbCase):

    def test_1_incident_upbit_avg_first(self):
        """(1) 사건 재현: orders 봇 BUY 777(이미 앱 매도됨, 기록 없음), 캐시 0, 지갑 13.05개 avg_buy_price 766 → 766 (출처 upbit_avg).
        구 코드: 캐시 다음 orders → 777."""
        self._cache(0.0)
        eng = _Engine(APP_QTY, upbit_avg=766.0)
        with self.assertLogs("core.strategy_engine", level="INFO") as cm:
            eng._reconcile_position_with_wallet()
        self.assertTrue(eng.position.has_position)
        self.assertEqual(eng.position.avg_price, 766.0)
        self.assertTrue(any("[POSITION-SYNC] entry_price=766.0 (출처: upbit_avg)" in m for m in cm.output))

    def test_2_fallback_order(self):
        """(2) Upbit 평균가 없음·캐시 770 → 770 (account_positions). 둘 다 없음 + orders BUY 수량 = 지갑 → 777 (orders).
        수량이 다르면 진입가 없음 → 포지션 복원 안 함 (기존 '신뢰 가능한 진입가 없음' 경로)."""
        self._cache(770.0)
        eng = _Engine(APP_QTY, upbit_avg=None)
        eng._reconcile_position_with_wallet()
        self.assertEqual((eng.position.has_position, eng.position.avg_price), (True, 770.0))

        self._cache(0.0)
        eng = _Engine(BOT_QTY, upbit_avg=None)
        with self.assertLogs("core.strategy_engine", level="INFO") as cm:
            eng._reconcile_position_with_wallet()
        self.assertEqual((eng.position.has_position, eng.position.avg_price), (True, 777.0))
        self.assertTrue(any("(출처: orders)" in m for m in cm.output))

        eng = _Engine(APP_QTY, upbit_avg=None)
        with self.assertLogs("core.strategy_engine", level="WARNING") as cm:
            eng._reconcile_position_with_wallet()
        self.assertFalse(eng.position.has_position)
        out = "\n".join(cm.output)
        self.assertIn("orders 마지막 봇 BUY 수량 불일치", out)
        self.assertIn("신뢰 가능한 진입가 없음", out)

    def test_3_wallet_zero_records_hts_sell(self):
        """(3) 지갑 0 닫힘 → audit_trades HTS_SELL 1행(가격 비움, 수량·직전 진입가), 그 뒤 get_last_open_buy_* 가 None."""
        eng = _Engine(BOT_QTY)
        self._held_bot_position(eng)
        eng.set_wallet(0.0)
        eng._reconcile_position_with_wallet()
        self.assertFalse(eng.position.has_position)
        rows = self._sql("SELECT type, reason, price, qty, entry_price FROM audit_trades WHERE type='HTS_SELL'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][:3], ("HTS_SELL", "HTS_SELL", None))
        self.assertAlmostEqual(rows[0][3], BOT_QTY)
        self.assertEqual(rows[0][4], 777.0)
        self.assertIsNone(self.db.get_last_open_buy_order(T, U))
        self.assertIsNone(self.db.get_last_open_buy_trade(U, T))
        self.assertEqual(self.db.trade_type_display("HTS_SELL"), "외부 매도")
        self.assertEqual(self.db.trade_kind("HTS_SELL"), "매도")

    def test_4_rebuy_after_hts_sell_does_not_borrow_old_buy(self):
        """(4) HTS_SELL 뒤 앱 재매수: Upbit 평균가·캐시가 아직 없어도 옛 봇 BUY(777)로 돌아가지 않는다 (진입가 없음 → 복원 보류)."""
        eng = _Engine(BOT_QTY)
        self._held_bot_position(eng)
        eng.set_wallet(0.0)
        eng._reconcile_position_with_wallet()
        self._cache(0.0)
        eng.set_wallet(BOT_QTY, upbit_avg=None)        # 수량이 같아도 HTS_SELL 로 청산된 BUY 는 쓰지 않는다
        eng._reconcile_position_with_wallet()
        self.assertFalse(eng.position.has_position)
        self.assertIsNone(eng.position.avg_price)

    def test_5_incident_replay_no_stop_loss(self):
        """(5) 사건 전체 재생: 777 봇 매수 보유 → 앱 매도(지갑 0) → 앱 매수 766 → 첫 매도 평가 종가 765:
        pnl ≈ −0.13% → STOP_LOSS 아님 (손절 1%). 구 코드: 진입가 777 → pnl −1.54% → STOP_LOSS."""
        from core.filters.sell_filters import StopLossFilter
        self._cache(0.0)
        eng = _Engine(BOT_QTY)
        self._held_bot_position(eng)
        eng.set_wallet(0.0)
        eng._reconcile_position_with_wallet()                  # 09:42:11 지갑 0 닫힘
        eng.set_wallet(APP_QTY, upbit_avg=766.0)
        eng._reconcile_position_with_wallet()                  # 10:59:05 외부 매수 복원
        sl = StopLossFilter(stop_loss_pct=0.01)
        sl.set_enabled(True)
        res = sl.evaluate(position=eng.position, current_price=765.0)
        self.assertEqual(eng.position.avg_price, 766.0)
        self.assertAlmostEqual(eng.position.get_pnl_pct(765.0), -0.0013, places=4)
        self.assertFalse(res.should_block, res.reason)


if __name__ == "__main__":
    unittest.main()
