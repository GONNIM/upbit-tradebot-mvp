"""
2차 T6: 분할 포지션 — PositionState 누적·평단, 분할 상태 새 테이블(pullback_state), 체결 반영(F2),
재시작 복원, 지갑 대조(desync), 그리고 T4·T5 「T6 로 넘김」 항목.

- 엔진: T5 시험의 EngineCase·FakeTrader·boot 를 그대로 쓰고, DB 는 임시 파일(get_db_path 패치)만 쓴다.
- LIVE 체결은 가짜 trader(LiveFakeTrader, buy_market 이 qty=0.0·uuid 를 돌려줌) + 체결 콜백을 손으로 부른다.
- 실제 업비트·텔레그램·서버 DB 에 닿지 않는다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t6_split_position -v
"""
from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time as _time
import logging
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from config import MIN_FEE_RATIO  # noqa: E402
from core import strategy_engine as se  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.candle_buffer import Bar, CandleBuffer  # noqa: E402
from core.indicator_state import IndicatorState  # noqa: E402
from core.position_state import PositionState  # noqa: E402
from core.strategy_action import Action  # noqa: E402
import engine.live_loop as live_loop  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import DEAD, V, ts_at  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    CALM, DIFF, DIP, EngineCase, FakeTrader, TICKER, USER, bar, boot, cfg, rising_df,
)

try:
    from services import pullback_state as pbs  # noqa: E402
except ImportError:  # 구현 전 실패 시험 단계
    pbs = None

KST = ZoneInfo("Asia/Seoul")
# EMA 공용 함수 무변경 대조 기준 — 2차 T10: 기준 해시는 baseline_commits 한 곳에서만 정한다(올리는 규칙도 그 파일)
from tests.regressions.baseline_commits import EMA_BASELINE_COMMIT as T5_COMMIT  # noqa: E402


def need_store(case):
    case.assertIsNotNone(pbs, "services.pullback_state 없음")
    return pbs


# ---------------------------------------------------------------- 가짜 LIVE trader
class LiveFakeTrader(FakeTrader):
    """LIVE 시장가: buy_market 이 qty=0.0·uuid 만 돌려준다(실제 체결은 콜백). 지갑은 coin·wallet_avg."""

    def __init__(self, **k):
        super().__init__(test_mode=False, **k)
        self.wallet_avg = 0.0
        self.upbit = SimpleNamespace(get_balances=self._balances)

    def _balances(self):
        return [{"currency": "KRW", "balance": str(self.avail), "locked": "0", "avg_buy_price": "0"},
                {"currency": "TEST", "balance": str(self.coin), "locked": "0",
                 "avg_buy_price": str(self.wallet_avg)}]

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        self.buy_calls.append({"price": price, "ticker": ticker, "ts": ts, "meta": dict(meta or {}),
                               "krw_amount": krw_amount, "strict_amount": strict_amount})
        if not self.buy_ok:
            self.last_buy_error = "Upbit error [under_maintenance]: 점검"
            return {}
        return {"time": ts, "side": "BUY", "qty": 0.0, "price": float(price),
                "uuid": f"L{len(self.buy_calls)}", "used_krw": krw_amount}


# ---------------------------------------------------------------- 임시 DB 엔진
class T6Case(EngineCase):
    def setUp(self):
        super().setUp()
        self.dbdir = tempfile.mkdtemp(prefix="p3t6_")
        self.addCleanup(shutil.rmtree, self.dbdir, True)
        self.db_path = os.path.join(self.dbdir, f"tradebot_{USER}.db")
        for target in ("services.init_db.get_db_path", "services.db.get_db_path"):
            p = mock.patch(target, return_value=self.db_path)
            p.start()
            self.addCleanup(p.stop)
        from services.init_db import ensure_all_schemas, initialize_db
        initialize_db(USER)
        ensure_all_schemas(USER)
        from services.db import ensure_schema
        ensure_schema(USER)  # 기동 경로와 같은 보조 마이그레이션(settings_history_id 등)

    def q(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def audit_types(self, kind):
        return self.q("SELECT reason, note FROM audit_trades WHERE type=?", (kind,))

    def row(self, mode="TEST"):
        return need_store(self).load(USER, mode)

    def kst(self, i):
        return ts_at(i).tz_convert(KST).to_pydatetime()


P990 = [V(p=990.0)] * 2 + [V(p=945.0)] * 40
B1000 = dict(o=1000, h=1001, l=980, c=1000)   # 저가 980 < 990 < 종가 1000 → 1회차
C1000 = dict(o=1000, h=1001, l=995, c=1000)   # 눌림 없음
B950 = dict(o=960, h=961, l=940, c=950)       # 저가 940 < 945 < 종가 950 → 2회차
C950 = dict(o=950, h=951, l=946, c=950)


# ================================================================ PositionState
class TestApplySplitEntry(unittest.TestCase):
    def test_split_avg_recalc(self):
        p = PositionState()
        t0 = datetime(2026, 10, 28, 10, 0, tzinfo=KST)
        p.apply_split_entry(600.0, 1000.0, t0, "pullback_split")
        self.assertTrue(p.has_position)
        self.assertEqual((p.qty, p.avg_price, p.entry_ts), (600.0, 1000.0, t0))
        q2 = 600_000 / 950
        p.apply_split_entry(q2, 950.0, t0 + timedelta(minutes=6), "pullback_split")
        self.assertAlmostEqual(p.qty, 600 + q2)
        self.assertAlmostEqual(p.avg_price, 1_200_000 / (600 + q2))
        self.assertAlmostEqual(p.avg_price, 974.3589743589, places=6)
        self.assertEqual(p.entry_ts, t0)               # 첫 진입 시각은 그대로
        self.assertFalse(p.pending_order)

    def test_split_entry_on_base_snapshot(self):
        """LIVE 체결: 발주 때 잡은 기준(수량·원가)에 체결분을 더한다 — 지갑 동기화가 이미 qty 를 바꿨어도 두 번 더하지 않음."""
        p = PositionState()
        t0 = datetime(2026, 10, 28, 10, 0, tzinfo=KST)
        p.apply_split_entry(600.0, 1000.0, t0, "pullback_split")
        p.qty = 1231.0                                 # 지갑 동기화(sync_from_wallet)가 먼저 지갑 수량으로 바꿈
        p.apply_split_entry(631.0, 950.0, t0, "pullback_split_fill", base_qty=600.0, base_cost=600_000.0)
        self.assertAlmostEqual(p.qty, 1231.0)
        self.assertAlmostEqual(p.avg_price, (600_000 + 631 * 950) / 1231)

    def test_split_entry_rejects_bad_values(self):
        p = PositionState()
        for qty, price in ((0.0, 100.0), (1.0, 0.0), (-1.0, 100.0)):
            with self.assertRaises(ValueError):
                p.apply_split_entry(qty, price, datetime.now(KST), "x")
        self.assertFalse(p.has_position)

    def test_apply_entry_unchanged(self):
        """EMA 회귀: apply_entry·open_position·close_position·sync_from_wallet 본문이 T5 커밋과 같고 결과도 같다."""
        # 수정 1회차: 원문을 못 읽으면(빈 원문·git 실패) 조용히 넘기지 않고 실패한다
        old = subprocess.run(["git", "show", f"{T5_COMMIT}:core/position_state.py"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        self.assertTrue(old.strip(), f"{T5_COMMIT} 원문을 읽지 못함 — 대조 불가")
        if True:
            new = (ROOT / "core/position_state.py").read_text(encoding="utf-8")

            def body(src, name):
                tree = ast.parse(src)
                fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
                return ast.get_source_segment(src, fn)
            for name in ("apply_entry", "open_position", "close_position", "sync_from_wallet", "__init__"):
                self.assertEqual(body(new, name), body(old, name), name)
        p = PositionState()
        t0 = datetime(2026, 10, 28, 10, 0, tzinfo=KST)
        p.highest_price, p.trailing_armed = 5.0, True
        p.open_position(2.0, 1161.0, 201, t0)
        self.assertEqual((p.has_position, p.qty, p.avg_price, p.entry_bar, p.entry_ts), (True, 2.0, 1161.0, 201, t0))
        self.assertEqual((p.highest_price, p.trailing_armed, p.highest_since_entry), (1161.0, False, 1161.0))
        p.apply_entry(3.0, 900.0, 7, t0, "wallet_sync")
        self.assertEqual((p.qty, p.avg_price, p.entry_bar), (3.0, 900.0, 7))


# ================================================================ 저장소 services/pullback_state
class TestStore(T6Case):
    def _state(self, **over):
        d = {"ticker": TICKER, "interval": "minute3", "entry_count": 2, "pullback_count": 2,
             "first_entry_ts": ts_at(1), "first_entry_reason": "PULLBACK", "armed": True, "prev_golden": True,
             "trade_origin": "live", "pending_fill": False, "fill_n": 2, "inv_sum": 2 / 1000,
             "sizing_base_krw": 3_000_000.0, "realized_pnl_krw": 0.0, "qty": 1231.5, "cost_krw": 1_200_000.0,
             "avg_price": 974.36, "desync": False, "buy_fail_bar_ts": None, "params_sha256": "ab" * 32,
             "last_bar_ts": ts_at(5)}
        d.update(over)
        return d

    def test_roundtrip_times_always_kst_offset(self):
        s = need_store(self)
        self.assertTrue(s.save(USER, "TEST", self._state()))
        r = s.load(USER, "TEST")
        self.assertEqual(r["entry_count"], 2)
        self.assertEqual(r["first_entry_ts"], ts_at(1).tz_convert(KST).isoformat())
        self.assertTrue(r["first_entry_ts"].endswith("+09:00"))
        self.assertTrue(r["last_bar_ts"].endswith("+09:00"))
        self.assertTrue(r["updated_at"].endswith("+09:00"))
        # 저장값을 전략에 되돌리면 같은 순간 (_to_ts 는 시간대 없는 값을 KST 로 보므로 오프셋 필수)
        st = sp.IncrementalPullbackStrategy(USER, TICKER, cfg(), 3)
        st.restore_split_state({"first_entry_ts": r["first_entry_ts"], "last_ts": r["last_bar_ts"]})
        self.assertEqual(st.first_entry_ts, ts_at(1))
        self.assertEqual(st.last_ts, ts_at(5))

    def test_naive_time_rejected_not_saved(self):
        """시간대 없는 시각은 저장하지 않는다(_to_ts=KST · _kst_iso=UTC 규약 차이로 9시간 어긋날 수 있음 — Issue #2)."""
        s = need_store(self)
        ok = s.save(USER, "TEST", self._state(first_entry_ts=pd.Timestamp("2026-10-01 00:00")))
        self.assertFalse(ok)
        self.assertIsNone(s.load(USER, "TEST"))
        with self.assertRaises(ValueError):
            s.to_kst_iso(datetime(2026, 10, 1, 0, 0))
        self.assertEqual(s.to_kst_iso(pd.Timestamp("2026-10-01 00:00", tz="UTC")), "2026-10-01T09:00:00+09:00")

    def test_mode_rows_separated(self):
        s = need_store(self)
        s.save(USER, "TEST", self._state(entry_count=1))
        s.save(USER, "LIVE", self._state(entry_count=3))
        self.assertEqual((s.load(USER, "TEST")["entry_count"], s.load(USER, "LIVE")["entry_count"]), (1, 3))
        self.assertEqual(self.q("SELECT COUNT(*) FROM pullback_state")[0][0], 2)

    def test_reset_after_exit_accumulates_pnl(self):
        s = need_store(self)
        s.save(USER, "TEST", self._state(realized_pnl_krw=1000.0, desync=True))
        self.assertTrue(s.reset_after_exit(USER, "TEST", 2500.5))
        r = s.load(USER, "TEST")
        self.assertEqual((r["entry_count"], r["pullback_count"], r["armed"], r["qty"], r["cost_krw"], r["desync"]),
                         (0, 0, 0, 0.0, 0.0, 0))
        self.assertIsNone(r["first_entry_ts"])
        self.assertIsNone(r["first_entry_reason"])
        self.assertIsNone(r["avg_price"])
        self.assertIsNone(r["sizing_base_krw"])
        self.assertAlmostEqual(r["realized_pnl_krw"], 3500.5)
        self.assertEqual(r["prev_golden"], 1)          # 판정 상태 prev_golden 은 청산과 무관(원본 closePosition)


# ================================================================ 엔진: 체결 반영·저장
class TestEngineSplitFill(T6Case):
    def test_split_avg_recalc_engine_round2(self):
        self.make(values=P990)
        self.feed(bar(0, **B1000), bar(1, **C1000), bar(2, **B950))
        self.assertEqual(self.strat.entry_count, 2)
        q2 = 600_000 / 950
        self.assertAlmostEqual(self.eng.position.qty, 600 + q2)
        self.assertAlmostEqual(self.eng.position.avg_price, 974.3589743589, places=6)
        r = self.row()
        self.assertEqual(r["entry_count"], 2)
        self.assertAlmostEqual(r["qty"], 600 + q2)
        self.assertAlmostEqual(r["cost_krw"], 1_200_000.0)
        self.assertAlmostEqual(r["avg_price"], 974.3589743589, places=6)
        self.assertEqual(r["sizing_base_krw"], 3_000_000)

    def test_split_fill_test_mode_direct(self):
        self.make(values=P990)
        with mock.patch.object(PositionState, "apply_split_entry", autospec=True,
                               side_effect=PositionState.apply_split_entry) as ase:
            self.feed(bar(0, **B1000))
        self.assertEqual(ase.call_count, 1)
        self.assertEqual(self.strat.entry_count, 1)
        self.assertIsNone(self.eng._pending_split)
        self.assertEqual((self.eng.position.qty, self.eng.position.avg_price), (600.0, 1000.0))

    def test_split_fill_uses_executed_qty_avg(self):
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        self.assertEqual(len(tr.buy_calls), 1)
        self.assertEqual(self.eng._pending_split["uuid"], "L1")
        self.assertFalse(self.eng.position.has_position)          # 추정 수량(600)을 쓰지 않는다
        tr.coin, tr.wallet_avg = 598.8, 1002.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1002.0, executed_qty=598.8,
                                executed_ts=self.kst(0) + timedelta(seconds=2), state="FILLED")
        p = self.eng.position
        self.assertEqual((p.has_position, p.qty, p.avg_price, p.pending_order), (True, 598.8, 1002.0, False))
        self.assertIsNone(self.eng._pending_split)
        self.assertEqual(self.strat.entry_count, 1)
        r = self.row("LIVE")
        self.assertAlmostEqual(r["qty"], 598.8)
        self.assertAlmostEqual(r["avg_price"], 1002.0)
        self.assertEqual(r["entry_count"], 1)

    def test_live_round2_fill_avg_from_base_not_double(self):
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        tr.coin, tr.wallet_avg = 600.0, 1000.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1000.0, executed_qty=600.0,
                                executed_ts=self.kst(0), state="FILLED")
        self.feed(bar(1, **C1000), bar(2, **B950))
        self.assertEqual(self.eng._pending_split["uuid"], "L2")
        q2 = 600_000 / 950
        tr.coin = 600 + q2                                       # 지갑 반영이 콜백보다 먼저
        self.feed(bar(3, **C950))                                # sync_from_wallet 가 qty 를 지갑으로 바꿈
        self.eng._on_limit_fill(uuid="L2", executed_price=950.0, executed_qty=q2,
                                executed_ts=self.kst(2), state="FILLED")
        self.assertAlmostEqual(self.eng.position.qty, 600 + q2)
        self.assertAlmostEqual(self.eng.position.avg_price, 974.3589743589, places=6)
        self.assertEqual(self.strat.entry_count, 2)

    def test_split_fill_market_cancel_state(self):
        """시장가는 체결량이 있어도 cancel 로 끝나기도 한다 → reconciler 가 state=CANCELED 로 콜백 1회 → 분할 반영."""
        from engine.order_reconciler import OrderReconciler
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        rec = OrderReconciler(upbit=mock.MagicMock())
        calls = []

        def cb(**kw):
            calls.append(kw)
            self.eng._on_limit_fill(**kw)
        rec.register_fill_callback(USER, TICKER, cb)
        rec._pending["L1"] = {"user_id": USER, "ticker": TICKER, "side": "BUY", "meta": {}, "last": None}
        info = {"state": "cancel", "avg_price": "1002", "executed_volume": "598.8", "paid_fee": "0.3",
                "created_at": "2026-10-28T10:00:00+09:00",
                "trades": [{"created_at": "2026-10-28T10:00:01+09:00", "funds": "599997.6",
                            "volume": "598.8", "fee": "0.3"}]}
        tr.coin = 598.8
        with mock.patch.object(rec, "_finalize_order"):
            rec._handle("L1", info)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["state"], "CANCELED")
        self.assertEqual((self.eng.position.qty, self.eng.position.avg_price), (598.8, 1002.0))
        self.assertEqual(self.strat.entry_count, 1)

    def test_fill_pending_timeout_aligns_to_wallet(self):
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        tr.coin, tr.wallet_avg = 600.0, 1000.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1000.0, executed_qty=600.0,
                                executed_ts=self.kst(0), state="FILLED")
        self.feed(bar(1, **C1000), bar(2, **B950))               # 2회차 L2 체결 대기(콜백 안 옴)
        q2 = 600_000 / 950
        tr.coin, tr.wallet_avg = 600 + q2, 974.36
        self.feed(bar(3, **C950), bar(4, **C950), bar(5, **C950))
        self.assertIsNotNone(self.eng._pending_split)            # 3봉까지는 기다린다
        with self.assertLogs(se.logger, level="WARNING") as logs:
            self.feed(bar(6, **C950))                            # 3봉을 넘음
        self.assertTrue(any("[PULLBACK-SYNC] fill pending" in m for m in logs.output))
        self.assertIsNone(self.eng._pending_split)
        self.assertFalse(self.eng.position.pending_order)
        self.assertAlmostEqual(self.eng.position.qty, 600 + q2)
        self.assertAlmostEqual(self.eng.position.avg_price, 974.36)
        self.assertFalse(self.eng._pullback_desync)
        self.assertAlmostEqual(self.row("LIVE")["qty"], 600 + q2)

    def test_limit_fill_callback_unchanged_for_ema(self):
        from engine.order_reconciler import OrderReconciler
        tr = FakeTrader(test_mode=False)
        tr.upbit = SimpleNamespace(get_balances=lambda: [])
        pos = PositionState(trader=tr, ticker=TICKER)
        eng = se.StrategyEngine(
            buffer=CandleBuffer(maxlen=500), indicators=IndicatorState(), position=pos,
            strategy=mock.MagicMock(), trader=tr, user_id=USER, ticker=TICKER,
            strategy_type="EMA", q=None, interval_sec=180, take_profit=0.03, stop_loss=0.01,
        )
        eng._pending_buy_uuid = "E1"
        with mock.patch.object(pos, "apply_entry", wraps=pos.apply_entry) as ae:
            eng._on_limit_fill(uuid="E1", executed_price=100.0, executed_qty=5.0,
                               executed_ts=datetime.now(KST))           # 인자 그대로(state 기본 FILLED)
            self.assertEqual(ae.call_count, 1)
            self.assertIsNone(eng._pending_buy_uuid)
            eng._pending_buy_uuid = "E2"
            eng._on_limit_fill(uuid="E2", executed_price=100.0, executed_qty=2.0,
                               executed_ts=datetime.now(KST), state="CANCELED")  # 부분 체결 뒤 취소
            self.assertEqual(ae.call_count, 1)                  # D6: 부분 체결 미처리 그대로
            self.assertEqual(eng._pending_buy_uuid, "E2")
        # reconciler: FILLED BUY → 콜백 1회(state=FILLED), 체결량 있는 CANCELED → state=CANCELED 로 1회
        rec = OrderReconciler(upbit=mock.MagicMock())
        got = []
        rec.register_fill_callback(USER, TICKER, lambda **kw: got.append(kw))
        for uuid, st in (("F1", "done"), ("C1", "cancel"), ("Z1", "cancel")):
            rec._pending[uuid] = {"user_id": USER, "ticker": TICKER, "side": "BUY", "meta": {}, "last": None}
            vol = "0" if uuid == "Z1" else "5"
            with mock.patch.object(rec, "_finalize_order"):
                rec._handle(uuid, {"state": st, "avg_price": "100", "executed_volume": vol, "paid_fee": "0",
                                   "created_at": "2026-10-28T10:00:00+09:00", "trades": []})
        self.assertEqual([(g["uuid"], g["state"]) for g in got], [("F1", "FILLED"), ("C1", "CANCELED")])

    def test_position_updated_on_fill_finalize(self):
        from engine import order_reconciler as orm
        from services.db import get_position_total_qty
        upbit = mock.MagicMock()
        upbit.get_balances.return_value = [
            {"currency": "KRW", "balance": "100", "locked": "0", "avg_buy_price": "0"},
            {"currency": "TEST", "balance": "598.8", "locked": "0", "avg_buy_price": "1002"}]
        rec = orm.OrderReconciler(upbit=upbit)
        rec._pending["L1"] = {"user_id": USER, "ticker": TICKER, "side": "BUY",
                              "meta": {"reason": "PULLBACK", "split_round": 1}, "last": None}
        with mock.patch.object(orm, "update_position_from_balances",
                               wraps=orm.update_position_from_balances) as upd:
            rec._handle("L1", {"state": "done", "avg_price": "1002", "executed_volume": "598.8",
                               "paid_fee": "0.3", "created_at": "2026-10-28T10:00:00+09:00",
                               "trades": [{"created_at": "2026-10-28T10:00:01+09:00"}]})
        self.assertEqual(upd.call_count, 1)
        self.assertAlmostEqual(get_position_total_qty(USER, TICKER), 598.8)
        self.assertEqual(len(self.audit_types("BUY")), 1)       # 체결 BUY 행(30초 창의 근거)


# ================================================================ 지갑 대조·앱 주문
class TestWalletSync(T6Case):
    def test_pullback_hts_buy_sync(self):
        """지갑 수량 > 상태(앱 매수) → desync=1, 다음 눌림 주문 0, TP 봉 매도 1(지갑 기준)."""
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        q1 = 600_000 / 55.0
        self.trader.coin += 500.0                                 # 앱에서 추가 매수
        with self.assertLogs(se.logger, level="WARNING") as logs:
            self.feed(bar(2, **CALM))
        self.assertTrue(self.eng._pullback_desync)
        self.assertTrue(any("[PULLBACK-SYNC] wallet=" in m and "class=wallet_more" in m for m in logs.output))
        self.assertEqual(len(self.audit_types("PULLBACK_SYNC")), 1)
        self.assertEqual(self.row()["desync"], 1)
        self.assertAlmostEqual(self.eng.position.qty, q1 + 500)  # 지갑 우선
        self.feed(bar(3, **DIP))
        self.assertEqual(len(self.trader.buy_calls), 1)           # 추가 분할매수 멈춤
        self.assertIn("POS_DESYNC", self.strat.last_eval["failed_keys"])
        self.feed(bar(4, **CALM))
        self.assertEqual(len(self.audit_types("PULLBACK_SYNC")), 1)   # 바뀔 때 1회만
        self.assertIs(self.feed(bar(5, o=55, h=60, l=55, c=58)), Action.SELL)
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertAlmostEqual(self.trader.sell_calls[0]["qty"], q1 + 500)
        self.assertFalse(self.eng._pullback_desync)               # 청산 → 정상 상태
        self.assertEqual(self.row()["desync"], 0)

    def test_desync_ignores_pending_fill(self):
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        tr.coin, tr.wallet_avg = 600.0, 1000.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1000.0, executed_qty=600.0,
                                executed_ts=self.kst(0), state="FILLED")
        self.feed(bar(1, **C1000), bar(2, **B950))               # 2회차 체결 대기
        tr.coin = 590.0                                          # 지갑 < 상태 (대기 중)
        self.feed(bar(3, **C950))
        self.assertFalse(self.eng._pullback_desync)
        q2 = 600_000 / 950
        tr.coin = 600 + q2                                       # 지갑 > 상태 (콜백 전)
        self.feed(bar(4, **C950))
        self.assertFalse(self.eng._pullback_desync)
        self.eng._on_limit_fill(uuid="L2", executed_price=950.0, executed_qty=q2,
                                executed_ts=self.kst(2), state="FILLED")
        self.feed(bar(5, **C950))
        self.assertFalse(self.eng._pullback_desync)
        self.assertEqual(self.audit_types("PULLBACK_SYNC"), [])
        self.assertEqual(self.row("LIVE")["desync"], 0)

    def test_app_sell_resets_state(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        self.assertEqual(self.row()["entry_count"], 1)
        self.trader.coin = 0.0                                   # 앱에서 전량 매도
        self.feed(bar(2, **CALM))
        self.assertFalse(self.eng.position.has_position)
        self.assertEqual(len(self.audit_types("HTS_SELL")), 1)
        r = self.row()
        self.assertEqual((r["entry_count"], r["qty"], r["desync"]), (0, 0.0, 0))
        self.assertIsNone(r["first_entry_ts"])
        self.assertEqual(self.strat.entry_count, 0)

    def test_bot_split_buy_not_hts_30s(self):
        """분할 체결 BUY 행 뒤 30초 안 지갑 증가 → HTS_BUY_ADD 0, desync 0.
        31초 뒤 같은 증가 + 분할 체결 대기 없음 → HTS_BUY_ADD 1(지금 동작 고정)."""
        from engine.order_reconciler import OrderReconciler
        from services.db import insert_trade_audit, update_coin_position
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        tr.coin, tr.wallet_avg = 600.0, 1000.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1000.0, executed_qty=600.0,
                                executed_ts=self.kst(0), state="FILLED")
        update_coin_position(USER, TICKER, 600.0, 0.0, entry_price=1000.0)

        def run_sync(age_sec):
            insert_trade_audit(user_id=USER, ticker=TICKER, interval_sec=180, bar=1, kind="BUY",
                               reason="PULLBACK", price=950.0, macd=None, signal=None, entry_price=None,
                               entry_bar=None, bars_held=None, tp=None, sl=None, highest=None, ts_pct=None,
                               ts_armed=None,
                               timestamp=(datetime.now(KST) - timedelta(seconds=age_sec)).isoformat())
            update_coin_position(USER, TICKER, 600.0, 0.0, entry_price=1000.0)
            upbit = mock.MagicMock()
            upbit.get_balances.return_value = [
                {"currency": "TEST", "balance": "1231.578947", "locked": "0", "avg_buy_price": "974.36"}]
            rec = OrderReconciler(upbit=upbit)
            rec._live_user_ids.add(USER)
            rec.register_hts_detect_callback(USER, TICKER, self.eng._on_hts_detect)
            rec._periodic_balance_sync()
            return len(self.audit_types("BUY"))

        n0 = len(self.audit_types("BUY"))
        self.assertEqual(run_sync(5), n0 + 1)                      # 봇 BUY 행 1 + HTS 0
        self.assertEqual([r for r in self.q("SELECT reason FROM audit_trades") if r[0] == "HTS_BUY_ADD"], [])
        self.assertFalse(self.eng._pullback_desync)
        self.assertEqual(self.eng.position.avg_price, 1000.0)
        run_sync(31)
        hts = [r for r in self.q("SELECT reason FROM audit_trades") if r[0] == "HTS_BUY_ADD"]
        self.assertEqual(len(hts), 1)                              # 지금 동작 고정

    def test_late_wallet_increase_with_pending_split_not_hts(self):
        """30초를 넘겨 늦게 보인 지갑 증가라도 분할 체결 대기 중이면 엔진은 앱 매수로 보지 않는다."""
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        tr.coin, tr.wallet_avg = 600.0, 1000.0
        self.eng._on_limit_fill(uuid="L1", executed_price=1000.0, executed_qty=600.0,
                                executed_ts=self.kst(0), state="FILLED")
        self.feed(bar(1, **C1000), bar(2, **B950))
        self.assertIsNotNone(self.eng._pending_split)
        self.eng._on_hts_detect(avg_price=974.36, qty=1231.5, reason="HTS_BUY_ADD")
        self.assertEqual(self.eng.position.avg_price, 1000.0)
        self.assertFalse(self.eng._pullback_desync)

    def test_pullback_hts_buy_stop_loss_applies(self):
        """PULLBACK 데드 상태 앱 매수 → SL 봉 매도 1 (EMA Issue #17 예외 미적용, D11 b)."""
        self.make(values=[V(**DEAD)] * 5, deadcross=False, sl=3)
        self.eng.position.open_position(1000.0, 100.0, 0, ts_at(0))
        self.eng.position.metadata["hts_buy"] = True
        self.trader.coin = 1000.0
        self.assertIs(self.feed(bar(1, o=99, h=99, l=96, c=97)), Action.SELL)
        self.assertEqual(self.strat.last_sell_reason, "SL")
        self.assertEqual(len(self.trader.sell_calls), 1)
        # EMA 쪽 예외(데드 상태 hts_buy → STOP_LOSS 건너뜀) 코드는 그대로
        src = (ROOT / "core/strategy_incremental.py").read_text(encoding="utf-8")
        old = subprocess.run(["git", "show", f"{T5_COMMIT}:core/strategy_incremental.py"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        self.assertTrue(old.strip(), f"{T5_COMMIT} 원문을 읽지 못함 — 대조 불가")
        self.assertEqual(src, old)


# ================================================================ 재시작 복원
class TestRestart(T6Case):
    def _two_rounds_armed(self, trader=None):
        self.make(values=P990, trader=trader)
        self.feed(bar(0, **B1000), bar(1, **C1000), bar(2, **B950), bar(3, **C950))
        self.feed(bar(4, o=944, h=946, l=930, c=940))            # 저가 < 945, 종가 < 945 → armed, 매수 없음
        self.assertEqual((self.strat.entry_count, self.strat.armed), (2, True))
        return self.strat.export_split_state(), self.eng

    def test_state_survives_restart(self):
        before, old_eng = self._two_rounds_armed()
        r = self.row()
        self.assertEqual((r["entry_count"], r["armed"]), (2, 1))
        self.assertTrue(r["first_entry_ts"].endswith("+09:00"))
        coin = self.trader.coin
        old_pos = (old_eng.position.qty, old_eng.position.avg_price)
        tr = FakeTrader()
        tr.coin = coin
        self.capital = 1_000_000                                 # 운용자산이 바뀌어도 이 거래 배분 기준은 그대로
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        res = self.eng.pullback_restore_on_boot(None)
        self.assertTrue(res["restored"])
        after = self.strat.export_split_state()
        for k in ("entry_count", "pullback_count", "first_entry_ts", "first_entry_reason", "armed",
                  "prev_golden", "trade_origin", "fill_n"):
            self.assertEqual(after[k], before[k], k)
        self.assertAlmostEqual(after["inv_sum"], before["inv_sum"])
        self.assertEqual(self.eng._pullback_sizing_base, 3_000_000)
        p = self.eng.position
        self.assertTrue(p.has_position)
        self.assertAlmostEqual(p.qty, old_pos[0])
        self.assertAlmostEqual(p.avg_price, old_pos[1])

    def test_restart_holding_resumes_buy_not_pos_desync(self):
        """보유 중 재시작: 분할 상태 복원으로 POS_DESYNC 매수 막힘이 풀리고 3회차가 같은 배분 기준으로 나간다."""
        _, _ = self._two_rounds_armed()
        coin = self.trader.coin
        tr = FakeTrader()
        tr.coin = coin
        self.capital = 1_000_000
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        self.eng.pullback_restore_on_boot(None)
        self.assertIs(self.feed(bar(5, o=950, h=951, l=946, c=950)), Action.BUY)  # armed 복원 → 종가 > 945 매수
        self.assertNotIn("POS_DESYNC", self.strat.last_eval.get("failed_keys") or [])
        self.assertEqual(tr.buy_calls[-1]["krw_amount"], 600_000)
        self.assertEqual(tr.buy_calls[-1]["meta"]["split_round"], 3)

    def test_restore_wallet_zero_resets_db(self):
        self._two_rounds_armed()
        tr = FakeTrader()
        tr.coin = 0.0                                            # 꺼져 있는 동안 앱에서 전량 매도
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        with self.assertLogs(se.logger, level="WARNING"):
            res = self.eng.pullback_restore_on_boot(None)
        self.assertEqual(res["reason"], "wallet_zero")
        r = self.row()
        self.assertEqual((r["entry_count"], r["qty"]), (0, 0.0))
        self.assertFalse(self.eng.position.has_position)

    def test_restore_other_ticker_ignored(self):
        self._two_rounds_armed()
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE pullback_state SET ticker='KRW-OTHER'")
        conn.commit()
        conn.close()
        tr = FakeTrader()
        tr.coin = 10.0
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        res = self.eng.pullback_restore_on_boot(None)
        self.assertFalse(res["restored"])
        self.assertEqual(self.strat.entry_count, 0)

    def test_restore_wallet_mismatch_marks_desync(self):
        self._two_rounds_armed()
        coin = self.trader.coin
        tr = FakeTrader()
        tr.coin = coin + 300.0                                   # 꺼져 있는 동안 앱 매수
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        self.eng.pullback_restore_on_boot(None)
        self.assertTrue(self.eng._pullback_desync)
        self.assertAlmostEqual(self.eng.position.qty, coin + 300.0)
        self.assertEqual(self.strat.entry_count, 2)

    def test_cooldown_survives_restart(self):
        """쿨다운 영속: 매수 실패 뒤 재시작해도 남은 봉 동안 재주문하지 않는다(재시작으로 풀리지 않음)."""
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))                 # 1회차 보유
        self.trader.buy_ok = False
        self.feed(bar(2, **DIP))                                 # 2회차 주문 실패 → 쿨다운(실패 봉 ts_at(2))
        self.assertTrue(self.row()["buy_fail_bar_ts"].endswith("+09:00"))
        self.feed(bar(3, **CALM))
        coin = self.trader.coin
        tr = FakeTrader()
        tr.coin = coin
        self.make(trader=tr)
        self.eng.bar_count = 40
        self.eng.last_bar_ts = ts_at(3)
        self.eng.pullback_restore_on_boot(None)
        self.feed(bar(4, **DIP))                                 # 실패 봉 +2 → 막힘
        self.assertEqual(tr.buy_calls, [])
        self.feed(bar(5, **DIP))                                 # 실패 봉 +3 → 주문
        self.assertEqual(len(tr.buy_calls), 1)

    def test_compounding_sizing_base_adds_realized(self):
        self.make(compounding=True)
        self.feed(bar(0, **DIP), bar(1, **CALM))
        q1 = 600_000 / 55.0
        self.assertIs(self.feed(bar(2, o=55, h=60, l=55, c=58)), Action.SELL)
        realized = q1 * 58 * (1 - MIN_FEE_RATIO) - 600_000 * (1 + MIN_FEE_RATIO)
        self.assertAlmostEqual(self.row()["realized_pnl_krw"], realized, places=4)
        self.feed(bar(3, **DIP))
        self.assertEqual(self.trader.buy_calls[-1]["krw_amount"], int((3_000_000 + realized) // 5))
        self.assertAlmostEqual(self.row()["sizing_base_krw"], 3_000_000 + realized, places=4)

    def test_no_compounding_sizing_base_is_capital(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, o=55, h=60, l=55, c=58), bar(3, **DIP))
        self.assertNotEqual(self.row()["realized_pnl_krw"], 0.0)  # 기록은 하되
        self.assertEqual(self.trader.buy_calls[-1]["krw_amount"], 600_000)  # 배분 기준은 운용자산

    def test_boot_resume_restores_split_state(self):
        """WO-12 경로(boot_resume_all 가짜 start): 기동 마이그레이션 → run_live_loop 워밍업 → DB 분할 상태 복원."""
        from engine import boot_resume
        s = need_store(self)
        df = rising_df(300)
        s.save(USER, "TEST", {
            "ticker": TICKER, "interval": "minute3", "entry_count": 2, "pullback_count": 2,
            "first_entry_ts": df.index[-20], "first_entry_reason": "PULLBACK", "armed": False,
            "prev_golden": True, "trade_origin": "live", "pending_fill": False, "fill_n": 2,
            "inv_sum": 2 / 1290.0, "sizing_base_krw": 3_000_000.0, "realized_pnl_krw": 0.0,
            "qty": 1000.0, "cost_krw": 1_290_000.0, "avg_price": 1290.0, "desync": False,
            "last_bar_ts": df.index[-1]})
        tr = FakeTrader()
        tr.coin = 1000.0
        started = []

        def fake_start(uid):
            started.append(boot(self, cfg(), df, trader=tr))
            return True
        with mock.patch.object(boot_resume, "list_resume_targets", return_value=[USER]), \
                mock.patch("services.init_db.ensure_all_schemas", wraps=__import__(
                    "services.init_db", fromlist=["x"]).ensure_all_schemas) as eas:
            res = boot_resume.boot_resume_all(users=[USER], verify=lambda: (True, "ok", 1e6), start=fake_start)
        self.assertEqual(res, {USER: "success"})
        self.assertGreaterEqual(eas.call_count, 1)
        eng = started[0][0]
        st = eng.strategy
        self.assertEqual((st.entry_count, st.pullback_count, st.first_entry_reason, st.trade_origin),
                         (2, 2, "PULLBACK", "live"))
        self.assertEqual(st.first_entry_ts, df.index[-20])
        self.assertTrue(eng.position.has_position)
        self.assertEqual((eng.position.qty, eng.position.avg_price), (1000.0, 1290.0))
        self.assertEqual(eng._pullback_sizing_base, 3_000_000.0)
        nxt = df.index[-1] + pd.Timedelta(minutes=3)
        eng.on_new_bar_confirmed(Bar(ts=nxt, open=1299.5, high=1300.2, low=1299.4, close=1300.0, volume=10.0,
                                     is_closed=True, is_confirmed=True, source="REST_RECONCILED"),
                                 df, dict(DIFF))
        self.assertNotIn("POS_DESYNC", st.last_eval["failed_keys"])

    def test_boot_holding_without_state_still_pos_desync(self):
        """대조: 분할 상태가 없으면(앱 매수 보유) 지금처럼 POS_DESYNC 로 매수가 막힌다."""
        df = rising_df(300)
        tr = FakeTrader()
        tr.coin = 1000.0
        with mock.patch("services.db.get_position_entry_price", return_value=1290.0):
            eng, _ = boot(self, cfg(), df, trader=tr)
            nxt = df.index[-1] + pd.Timedelta(minutes=3)
            eng.on_new_bar_confirmed(Bar(ts=nxt, open=1299.5, high=1300.2, low=1299.4, close=1300.0,
                                         volume=10.0, is_closed=True, is_confirmed=True,
                                         source="REST_RECONCILED"), df, dict(DIFF))
        self.assertTrue(eng.position.has_position)
        self.assertIn("POS_DESYNC", eng.strategy.last_eval["failed_keys"])

    def test_boot_restore_replays_bars_after_saved_bar(self):
        """저장 봉 뒤 워밍업 봉은 DB 판정 상태에서 주문 없이 이어 재생 — 회차 칸은 DB 값 유지(보유 중 재생 규칙)."""
        s = need_store(self)
        df = rising_df(300)
        s.save(USER, "TEST", {
            "ticker": TICKER, "interval": "minute3", "entry_count": 1, "pullback_count": 1,
            "first_entry_ts": df.index[-30], "first_entry_reason": "PULLBACK", "armed": False,
            "prev_golden": True, "trade_origin": "live", "fill_n": 1, "inv_sum": 1 / 1270.0,
            "sizing_base_krw": 3_000_000.0, "qty": 500.0, "cost_krw": 635_000.0, "avg_price": 1270.0,
            "last_bar_ts": df.index[-6]})
        tr = FakeTrader()
        tr.coin = 500.0
        eng, _ = boot(self, cfg(), df, trader=tr)
        res = eng.pullback_restore_result
        self.assertTrue(res["restored"])
        self.assertEqual(res["replayed"], 5)
        self.assertEqual(eng.strategy.last_ts, df.index[-1])
        self.assertEqual((eng.strategy.entry_count, eng.strategy.trade_origin), (1, "live"))
        self.assertEqual(eng.trader.buy_calls, [])
        self.assertEqual(len(eng.pullback_ring), eng.pullback_indicators.n if eng.pullback_indicators.n
                         < sp.RING_CAPACITY else sp.RING_CAPACITY)


# ================================================================ trade_origin 경계 · 잔고 조회 스레드 안전
class TestHandover(T6Case):
    def test_backfill_replay_keeps_live_origin_when_fill_pending(self):
        """BACKFILL 재생이 실거래 GOLDEN 을 다시 만들어 trade_origin 을 replay 로 바꾸지 않는다(체결 대기·미보유여도)."""
        self.make()
        self.strat.restore_split_state({"entry_count": 1, "pullback_count": 0, "first_entry_reason": "GOLDEN",
                                        "trade_origin": "live", "pending_fill": False, "last_ts": ts_at(1)})
        self.assertFalse(self.eng.position.has_position)

        def fake_replay(engine, **kw):
            engine.strategy.trade_origin = "replay"
            engine.strategy.armed = True
            return {"restored": True, "replayed": 2, "audited": 1, "reason": ""}
        ls = pd.DataFrame({"Open": [1.0] * 3, "High": [1.0] * 3, "Low": [1.0] * 3, "Close": [1.0] * 3,
                           "Volume": [1.0] * 3}, index=[ts_at(0), ts_at(1), ts_at(2)])
        with mock.patch.object(sp, "pullback_backfill", side_effect=fake_replay), \
                mock.patch.object(live_loop, "log_to_file"):
            live_loop._pullback_backfill_step(self.eng, [ts_at(0)], ls, ts_at(2), USER, None)
        self.assertEqual((self.strat.trade_origin, self.strat.entry_count), ("live", 1))
        self.feed(bar(2, **CALM))                                # 실보유 없음 → 정리, 실거래라 armed 해제
        self.assertEqual(self.strat.entry_count, 0)
        self.assertFalse(self.strat.armed)

    def test_krw_balance_checked_returns_ok_without_shared_flag(self):
        """잔고 조회 표식 스레드 안전: 다른 스레드의 조회 실패가 엔진 스레드의 결과·표식에 섞이지 않는다."""
        import threading
        from core.trader import UpbitTrader
        with mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader.insert_log"):
            t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)
        t.upbit.get_balance.side_effect = [None, RuntimeError("x"), 123.0]
        self.assertEqual(t.krw_balance_checked(), (0.0, False))
        self.assertEqual(t.krw_balance_checked(), (0.0, False))
        self.assertEqual(t.krw_balance_checked(), (123.0, True))
        # 다른 스레드(trading_control 등)가 _krw_balance 를 불러 실패 → 이 스레드 표식은 그대로 True
        t.upbit.get_balance.side_effect = [RuntimeError("other thread")]
        seen = {}

        def other():
            seen["v"] = t._krw_balance()
            seen["ok"] = t.last_krw_balance_ok
        th = threading.Thread(target=other)
        th.start()
        th.join()
        self.assertEqual((seen["v"], seen["ok"]), (0.0, False))
        self.assertTrue(t.last_krw_balance_ok)
        # 반대로 엔진 스레드가 실패해도 다른 스레드의 성공 판정은 그대로
        t.upbit.get_balance.side_effect = [RuntimeError("main"), 50.0]
        self.assertEqual(t.krw_balance_checked(), (0.0, False))
        th = threading.Thread(target=lambda: seen.update(r=t.krw_balance_checked()))
        th.start()
        th.join()
        self.assertEqual(seen["r"], (50.0, True))
        self.assertFalse(t.last_krw_balance_ok)

    def test_engine_reads_checked_return_not_flag(self):
        class Tr(FakeTrader):
            def krw_balance_checked(self):
                return 0.0, False
        tr = Tr()
        tr.last_krw_balance_ok = True                            # 다른 스레드가 바꿔 놓은 표식
        self.make(trader=tr)
        self.feed(bar(0, **DIP))
        self.assertEqual([r["code"] for r in tr.rejects], ["split_krw_unknown"])
        self.assertEqual(tr.buy_calls, [])

    def test_buy_market_strict_uses_checked_ema_path_unchanged(self):
        from core.trader import UpbitTrader
        ps = [mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader.insert_order"),
              mock.patch("core.trader.insert_log"),
              mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
              mock.patch("core.trader._upbit_buy_market", return_value={
                  "ok": True, "status": 201, "error_name": None, "error_message": None,
                  "exception": None, "body": "", "data": {"uuid": "x-1"}})]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)
        t.upbit.get_balance.return_value = 10_000_000
        with mock.patch.object(t, "krw_balance_checked", wraps=t.krw_balance_checked) as kc:
            r = t.buy_market(100.0, TICKER, meta={}, krw_amount=600_000, strict_amount=True)
        self.assertEqual(r["uuid"], "x-1")
        self.assertGreaterEqual(kc.call_count, 2)                # 주문 전 + 시도 직전 (반환값으로 성공 여부)
        with mock.patch.object(t, "_krw_balance", wraps=t._krw_balance) as kb, \
                mock.patch.object(t, "krw_balance_checked", wraps=t.krw_balance_checked) as kc:
            t.buy_market(100.0, TICKER, meta={})                 # EMA 경로: 지금처럼 _krw_balance
        self.assertGreaterEqual(kb.call_count, 2)
        self.assertEqual(kc.call_count, 0)

    def test_live_refuse_kept(self):
        """LIVE 기동 거부는 T6 에서 풀지 않는다(해제는 사용자 결정)."""
        self.assertTrue(live_loop.PULLBACK_LIVE_REFUSE_MSG)
        src = (ROOT / "engine/live_loop.py").read_text(encoding="utf-8")
        self.assertIn('strategy_tag == "PULLBACK" and (pullback_cfg is None or RUN_MODE != "UPBIT_MATCH" '
                      'or not test_mode)', src)


# ================================================================ 수정 1회차 (검수 반영)
class RacingTrader(LiveFakeTrader):
    """buy_market 이 돌려주기 전에 다른 스레드에서 체결 콜백을 쏜다(reconciler 가 빨리 본 경우)."""

    def __init__(self, **k):
        super().__init__(**k)
        self.engine = None
        self.cb_thread = None

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        r = super().buy_market(price, ticker, ts=ts, meta=meta, krw_amount=krw_amount, strict_amount=strict_amount)
        uuid = r.get("uuid")
        eng = self.engine

        def fire():
            eng._on_limit_fill(uuid=uuid, executed_price=1002.0, executed_qty=598.8,
                               executed_ts=datetime.now(KST), state="FILLED")
        self.cb_thread = threading.Thread(target=fire)
        self.cb_thread.start()
        _time.sleep(0.2)  # 콜백 스레드가 먼저 도착해 기다리게 한다
        return r


class DryRunTrader(FakeTrader):
    """WO-6 dry-run: 실주문 없이 qty=0.0·uuid='DRY_RUN' 을 돌려준다(core/trader.py buy_market)."""

    def __init__(self, **k):
        super().__init__(**k)
        self.dry_run = True

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        self.buy_calls.append({"price": price, "ticker": ticker, "ts": ts, "meta": dict(meta or {}),
                               "krw_amount": krw_amount, "strict_amount": strict_amount})
        return {"time": ts, "side": "BUY", "qty": 0.0, "price": float(price), "uuid": "DRY_RUN",
                "raw": {"dry_run": True}}


class TestRevision1(T6Case):
    def test_fill_callback_before_pending_set_waits_lock(self):
        """체결 콜백이 _pending_split 설정 전에 오면 락을 기다렸다가 등록 뒤에 반영된다."""
        tr = RacingTrader()
        self.make(values=P990, trader=tr)
        tr.engine = self.eng
        self.feed(bar(0, **B1000))
        self.assertEqual(len(tr.buy_calls), 1)
        tr.cb_thread.join(5)
        self.assertFalse(tr.cb_thread.is_alive())
        self.assertIsNone(self.eng._pending_split)
        self.assertEqual((self.eng.position.qty, self.eng.position.avg_price), (598.8, 1002.0))
        self.assertFalse(self.eng.position.pending_order)
        self.assertAlmostEqual(self.row("LIVE")["qty"], 598.8)

    def test_split_fill_log_levels(self):
        """CANCELED 콜백 발화 로그는 DEBUG, 엔진이 실제 반영했을 때만 INFO [SPLIT-FILL] applied. FILLED 발화는 INFO 그대로."""
        from engine import order_reconciler as orm
        tr = LiveFakeTrader()
        self.make(values=P990, trader=tr)
        self.feed(bar(0, **B1000))
        rec = orm.OrderReconciler(upbit=mock.MagicMock())
        rec.register_fill_callback(USER, TICKER, self.eng._on_limit_fill)
        info = {"state": "cancel", "avg_price": "1002", "executed_volume": "598.8", "paid_fee": "0.3",
                "created_at": "2026-10-28T10:00:00+09:00", "trades": []}
        rec._pending["L1"] = {"user_id": USER, "ticker": TICKER, "side": "BUY", "meta": {}, "last": None}
        with mock.patch.object(rec, "_finalize_order"), \
                self.assertLogs(orm.logger, level="DEBUG") as rl, self.assertLogs(se.logger, level="INFO") as el:
            rec._handle("L1", info)
        fired = [r for r in rl.records if "fill callback fired" in r.getMessage()]
        self.assertEqual([r.levelno for r in fired], [logging.DEBUG])
        self.assertTrue(any("[SPLIT-FILL] applied" in m and m.startswith("INFO") for m in el.output))
        # EMA 쪽(반영 없음)은 [SPLIT-FILL] applied 가 없다
        rec._pending["C9"] = {"user_id": USER, "ticker": TICKER, "side": "BUY", "meta": {}, "last": None}
        with mock.patch.object(rec, "_finalize_order"), self.assertLogs(orm.logger, level="DEBUG") as rl2:
            rec._handle("C9", dict(info))
        self.assertFalse(any("[SPLIT-FILL] applied" in r.getMessage() for r in rl2.records))
        # FILLED 발화는 INFO 그대로
        rec._pending["F9"] = {"user_id": USER, "ticker": TICKER, "side": "BUY", "meta": {}, "last": None}
        with mock.patch.object(rec, "_finalize_order"), self.assertLogs(orm.logger, level="DEBUG") as rl3:
            rec._handle("F9", {**info, "state": "done"})
        fired = [r for r in rl3.records if "fill callback fired" in r.getMessage()]
        self.assertEqual([r.levelno for r in fired], [logging.INFO])

    def test_accumulate_removed(self):
        self.assertFalse(hasattr(se.StrategyEngine, "_pullback_accumulate"))

    def test_load_distinguishes_missing_row_and_read_error(self):
        s = need_store(self)
        self.assertIsNone(s.load(USER, "TEST"))                  # 행 없음 = None
        self.assertTrue(hasattr(s, "PullbackStateReadError"))
        with mock.patch.object(s, "_COLS", tuple(s._COLS) + ("no_such_col",)):
            with self.assertRaises(s.PullbackStateReadError):
                s.load(USER, "TEST")                             # 읽기 오류 = 예외

    def _saved_row(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))                 # 1회차 보유, 행 저장
        r = self.row()
        self.assertEqual(r["entry_count"], 1)
        return r

    def test_read_error_blocks_persist(self):
        s = need_store(self)
        before = self._saved_row()
        coin = self.trader.coin
        tr = FakeTrader()
        tr.coin = coin
        self.make(trader=tr)
        with mock.patch.object(s, "load", side_effect=s.PullbackStateReadError("disk I/O error")), \
                self.assertLogs(se.logger, level="CRITICAL") as logs:
            res = self.eng.pullback_restore_on_boot(None)
        self.assertEqual(res["reason"], "read_error")
        self.assertTrue(any("저장 막음" in m for m in logs.output))
        self.feed(bar(2, **CALM))
        self.assertEqual(self.row(), before)                     # 첫 봉 뒤에도 저장 행 그대로

    def test_other_market_blocks_persist(self):
        self._saved_row()
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE pullback_state SET ticker='KRW-OTHER'")
        conn.commit()
        conn.close()
        before = self.row()
        tr = FakeTrader()
        tr.coin = 0.0
        self.make(trader=tr)
        with self.assertLogs(se.logger, level="CRITICAL"):
            res = self.eng.pullback_restore_on_boot(None)
        self.assertEqual(res["reason"], "other_market")
        self.feed(bar(2, **DIP), bar(3, **CALM))                 # 매수·판정이 있어도 덮어쓰지 않는다
        self.assertEqual(self.row(), before)

    def test_restore_exception_blocks_persist(self):
        """live_loop 복원 도우미에서 예외가 나면 저장 막음 — 첫 봉 뒤에도 저장 행 그대로."""
        before = self._saved_row()
        coin = self.trader.coin
        tr = FakeTrader()
        tr.coin = coin
        self.make(trader=tr)
        with mock.patch.object(self.eng, "pullback_restore_on_boot", side_effect=RuntimeError("boom")), \
                mock.patch.object(live_loop, "log_to_file"):
            live_loop._pullback_restore_split_state(self.eng, USER, None, None)
        self.assertTrue(self.eng._pullback_persist_blocked)
        self.feed(bar(2, **CALM))
        self.assertEqual(self.row(), before)

    def test_save_failure_logs_critical(self):
        s = need_store(self)
        self.make()
        with mock.patch.object(s, "save", return_value=False), \
                self.assertLogs(se.logger, level="CRITICAL") as logs:
            self.feed(bar(0, **DIP))
        self.assertTrue(any("[PULLBACK-STATE]" in m and "저장 실패" in m for m in logs.output))

    def test_dry_run_split_applies_immediately(self):
        """DRY_RUN uuid 는 체결 콜백이 오지 않으므로 체결 대기로 두지 않고 바로 반영한다."""
        tr = DryRunTrader()
        self.make(trader=tr)
        self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)
        self.assertIsNone(self.eng._pending_split)
        self.assertFalse(self.eng.position.pending_order)
        call = tr.buy_calls[0]
        self.assertTrue(self.eng.position.has_position)
        self.assertAlmostEqual(self.eng.position.qty, call["krw_amount"] / call["price"])
        # 다음 봉: 지갑이 그대로(0)라 공용 _reconcile_position_with_wallet 이 포지션을 닫는다(EMA dry-run 과 같음).
        # 분할 상태도 지갑 0 으로 초기화되고, 체결 대기가 남아 매수가 막히지 않는다.
        self.feed(bar(1, **CALM))
        self.assertIsNone(self.eng._pending_split)
        self.assertFalse(self.eng.position.pending_order)
        self.assertEqual(self.eng._pb_qty, 0.0)


if __name__ == "__main__":
    unittest.main()
