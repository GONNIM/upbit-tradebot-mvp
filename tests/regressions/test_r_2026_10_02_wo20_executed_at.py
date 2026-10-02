"""
✅ WO-20 회귀: orders.executed_at 기록 + 복원 조회 정렬·시각 대용 + boot_seed 평균가 유지 (2026-10-02)

원 결함 (WO-20 조사 보고 docs/plans/2026-10-02-wo20-executed-at/report.md):
- 체결 확인 경로(OrderReconciler 확정)가 orders.executed_at 을 쓰지 않음 → 전 주문 557행 NULL.
- get_last_open_buy_order 의 시각 열이 executed_at 이라 boot_seed 가 한 번도 적용되지 않음
  (재시작하면 매수 시각 = 재시작 시각).
- 같은 조회의 정렬이 "executed_at , timestamp DESC" (executed_at 오름차순) → executed_at 이 채워지기
  시작하면 옛 매수를 고름 (조사 재현: 734 대신 710 / 700).

처방: (다) + 정렬 수정 + 문구 수정.
- 확정 시 executed_at = Upbit trades[].created_at 중 가장 늦은 값, 취소 확정 시 canceled_at.
- 복원 시각 COALESCE(executed_at, updated_at), 정렬 COALESCE(executed_at, updated_at, timestamp) DESC.
- boot_seed 는 entry_ts·entry_bar 만 복원, avg_price 는 지갑 동기화 값 유지.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_02_wo20_executed_at -v
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

KST = ZoneInfo("Asia/Seoul")
U = "test_r_2026_10_02_wo20"
T = "KRW-JTO"


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo20_"))
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

    def _order(self, price, entry_bar, ts, executed_at=None, updated_at=None, side="BUY", state="FILLED",
               vol=318.01810267, uuid=None):
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, provider_uuid, state, "
            "requested_at, executed_at, executed_volume, avg_price, updated_at, entry_bar) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (U, ts, T, side, price, 0, "requested", uuid, state, ts, executed_at, vol, price,
             updated_at or ts, entry_bar),
        )
        con.commit()
        con.close()

    def _row(self, uuid):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM orders WHERE provider_uuid=?", (uuid,)).fetchone()
        con.close()
        return dict(r)


OLD1 = (700.0, 100, "2026-09-01T10:00:00+09:00")
OLD2 = (710.0, 200, "2026-09-15T10:00:00+09:00")
NEW_TS = "2026-10-02T08:00:12.437007+09:00"
NEW_EXEC = "2026-10-02T08:00:12+09:00"
NEW_UPD = "2026-10-02T08:00:14.045644+09:00"


class TestWo20(_DbCase):

    def test_1_order_picks_latest_buy(self):
        """(1) executed_at NULL 옛 행 + 채워진 새 행 → 최신 매수(734). 모두 채워져도 734. (옛 코드: 710 / 700)"""
        self._order(*OLD1)
        self._order(*OLD2)
        self._order(734.0, 330, NEW_TS, executed_at=NEW_EXEC, updated_at=NEW_UPD)
        r = self.db.get_last_open_buy_order(T, U)
        self.assertEqual((r["price"], r["entry_bar"]), (734.0, 330))
        self.assertEqual(r["entry_ts_iso"], NEW_EXEC)

        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE orders SET executed_at = timestamp WHERE executed_at IS NULL")
        con.commit()
        con.close()
        r = self.db.get_last_open_buy_order(T, U)
        self.assertEqual((r["price"], r["entry_bar"]), (734.0, 330))

    def test_2_finalize_records_executed_and_canceled_at(self):
        """(2) done(trades 2건) → executed_at=마지막 체결 시각. cancel → canceled_at. 진행(wait) → executed_at NULL."""
        from engine.order_reconciler import OrderReconciler
        upbit = MagicMock()
        upbit.get_balances.return_value = []
        orc = OrderReconciler(upbit)
        for u, side in (("u-done", "BUY"), ("u-cancel", "BUY"), ("u-wait", "SELL")):
            self._order(734.0, 330, NEW_TS, side=side, state="REQUESTED", vol=0, uuid=u)
            orc._pending[u] = {"user_id": U, "ticker": T, "side": side, "meta": {"bar": 330, "reason": "EMA_GC"}}

        orc._handle("u-done", {
            "state": "done", "avg_price": "734.0", "executed_volume": "318.01810267", "paid_fee": "0",
            "trades": [
                {"created_at": "2026-10-02T08:00:14+09:00", "volume": "100", "funds": "73400", "fee": "0"},
                {"created_at": "2026-10-02T08:00:12+09:00", "volume": "218.01810267", "funds": "160025", "fee": "0"},
            ],
        })
        done = self._row("u-done")
        self.assertEqual(done["state"], "FILLED")
        self.assertEqual(done["executed_at"], "2026-10-02T08:00:14+09:00")
        self.assertIsNone(done["canceled_at"])

        orc._handle("u-cancel", {"state": "cancel", "avg_price": "0", "executed_volume": "0", "paid_fee": "0",
                                 "trades": []})
        cancel = self._row("u-cancel")
        self.assertEqual(cancel["state"], "CANCELED")
        self.assertIsNotNone(cancel["canceled_at"])
        self.assertIsNone(cancel["executed_at"])

        orc._handle("u-wait", {"state": "wait", "avg_price": "740", "executed_volume": "10", "paid_fee": "0",
                               "trades": [{"created_at": "2026-10-02T09:30:11+09:00", "volume": "10",
                                           "funds": "7400", "fee": "0"}]})
        wait = self._row("u-wait")
        self.assertEqual(wait["state"], "PARTIALLY_FILLED")
        self.assertIsNone(wait["executed_at"])

    def _wallet_position(self, wallet_avg, qty=318.01810267):
        """sync_from_wallet 직후 상태 재현: has_position=True, avg_price=지갑 값, entry_ts=기동 시각."""
        from core.position_state import PositionState
        p = PositionState()
        p._has_position = True
        p.qty = qty
        p.avg_price = wallet_avg
        p.entry_ts = datetime(2026, 10, 2, 12, 0, 0, tzinfo=KST)   # 기동 시각
        p.entry_bar = None
        return p

    def test_3_boot_seed_uses_updated_at(self):
        """(3) executed_at NULL + updated_at → boot_seed 가 apply_entry, entry_ts = updated_at. (옛 코드: 시각 없음)"""
        self._order(734.0, 330, NEW_TS, executed_at=None, updated_at=NEW_UPD)
        from engine import live_loop
        r = live_loop._seed_entry_price_from_db(T, U)
        self.assertEqual(r.get("entry_ts_iso"), NEW_UPD)

        p = self._wallet_position(734.0)
        with self.assertLogs("core.position_state", level="INFO") as cm:
            applied = live_loop._apply_boot_seed(p, r, 318.01810267)
        self.assertTrue(applied)
        self.assertTrue(any("[POSITION-APPLY] source=boot_seed" in m for m in cm.output))
        self.assertEqual(p.entry_ts, datetime.fromisoformat(NEW_UPD))
        self.assertEqual(p.entry_bar, 330)

    def test_4_avg_price_keeps_wallet_value(self):
        """(4) 지갑 평균가 740, 주문 평균가 734, 수량 불일치(앱 추가 매수 혼합) → avg_price 740, entry_ts 주문 시각."""
        self._order(734.0, 330, NEW_TS, executed_at=NEW_EXEC, updated_at=NEW_UPD)
        from engine import live_loop
        r = live_loop._seed_entry_price_from_db(T, U)
        self.assertEqual(r["price"], 734.0)
        p = self._wallet_position(740.0, qty=400.0)
        self.assertTrue(live_loop._apply_boot_seed(p, r, 400.0))
        self.assertEqual(p.avg_price, 740.0)
        self.assertEqual(p.qty, 400.0)
        self.assertEqual(p.entry_ts, datetime.fromisoformat(NEW_EXEC))

        # 지갑 평균가를 구하지 못한 경우에만 주문 평균가
        p2 = self._wallet_position(None)
        self.assertTrue(live_loop._apply_boot_seed(p2, r, 318.01810267))
        self.assertEqual(p2.avg_price, 734.0)

    def test_5_old_entry_bar_uses_audit_fallback(self):
        """(5) 고정: 옛 entry_bar(330) > 현재 봉(201) → bars_held 음수가 아니라 audit 보정값. 기존 경로 그대로."""
        from core.position_state import PositionState
        from core.strategy_incremental import IncrementalEMAStrategy
        from core.candle_buffer import Bar
        strat = IncrementalEMAStrategy(user_id=U, ticker=T, take_profit=0.5, stop_loss=0.5,
                                       min_holding_period=1, trailing_stop_pct=None,
                                       buy_conditions={}, sell_conditions={})
        p = PositionState()
        p.apply_entry(qty=318.0, avg_price=740.0, entry_bar=330,
                      entry_ts=datetime.fromisoformat(NEW_EXEC), source="boot_seed")
        self.assertLess(p.get_bars_held(201), 0)
        ind = {"ema_fast": 741.0, "ema_slow": 739.0, "ema_base": 739.0,
               "prev_ema_fast": 740.9, "prev_ema_slow": 739.0}
        bar = Bar(ts=datetime(2026, 10, 2, 3, 5, tzinfo=ZoneInfo("UTC")), open=741, high=741, low=741,
                  close=741, volume=1.0, is_closed=True)
        with patch("services.db.estimate_bars_held_from_audit", return_value=18), \
                self.assertLogs("core.strategy_incremental", level="INFO") as cm:
            strat.on_bar(bar, ind, p, 201)
        self.assertEqual(p.entry_bar, 201 - 18)
        self.assertTrue(any("[MIN_HOLDING_CHECK] bars_held=18" in m for m in cm.output))

    def test_6_restart_with_position_sequence(self):
        """(6) 보유 중 재시작 재현: sync_from_wallet → _seed_entry_price_from_db → _apply_boot_seed.
        boot_seed 적용 로그 1줄, [BOOT-SEED] WARNING 0건, entry_ts=주문 체결 시각, avg_price=지갑 값."""
        self._order(*OLD2)
        self._order(734.0, 330, NEW_TS, executed_at=NEW_EXEC, updated_at=NEW_UPD)
        from core.position_state import PositionState
        from engine import live_loop
        trader = MagicMock()
        trader.user_id = U
        trader.test_mode = False
        trader._coin_balance.return_value = 318.01810267
        trader.upbit.get_balances.return_value = [{"currency": "JTO", "balance": "318.01810267",
                                                   "avg_buy_price": "734"}]
        p = PositionState(trader=trader, ticker=T)
        with self.assertLogs(level="INFO") as cm:
            p.sync_from_wallet()
            self.assertTrue(p.has_position)
            self.assertEqual(p.avg_price, 734.0)                 # 지갑(Upbit avg_buy_price)
            r = live_loop._seed_entry_price_from_db(T, U)
            live_loop._apply_boot_seed(p, r, 318.01810267)
        out = "\n".join(cm.output)
        self.assertEqual(out.count("[POSITION-APPLY] source=boot_seed"), 1)
        self.assertNotIn("[BOOT-SEED]", out)
        self.assertNotIn("P3 boot seed 시각 복원 실패", out)
        self.assertEqual(p.entry_ts, datetime.fromisoformat(NEW_EXEC))
        self.assertEqual(p.avg_price, 734.0)
        self.assertEqual(p.entry_bar, 330)

    def test_7_warning_text_when_no_time(self):
        """(추가) 시각을 정하지 못하면 apply_entry 미호출 + WARNING 문구(실제 동작: has_position=True 유지)."""
        from engine import live_loop
        p = self._wallet_position(734.0)
        with self.assertLogs("engine.live_loop", level="WARNING") as cm:
            applied = live_loop._apply_boot_seed(p, {"price": 734.0, "entry_bar": 330}, 318.01810267)
        self.assertFalse(applied)
        self.assertTrue(p.has_position)
        msg = "\n".join(cm.output)
        self.assertIn("[BOOT-SEED] 봇 주문의 체결 시각 없음 → boot_seed 미적용, 지갑 동기화 값 유지", msg)
        self.assertIn("has_position=True", msg)
        self.assertNotIn("has_position=False 유지", msg)


if __name__ == "__main__":
    unittest.main()
