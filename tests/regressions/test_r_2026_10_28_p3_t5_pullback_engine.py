"""
2차 T5: 엔진 연결 — 보유 중 매수 평가, 분할 매수, 늘 시장가, 회차 건너뜀.

계획 T5 시험 14개 + T3·T4 「T5 로 넘김」 항목 시험.
- 엔진: StrategyEngine(strategy_type="PULLBACK") + 손으로 적은 지표(ScriptedIndicators) 또는 실제 PullbackIndicators.
- 주문: 가짜 trader(FakeTrader) — 실제 업비트·DB·텔레그램에 닿지 않는다.
- 기동: run_live_loop 를 업비트 조회·시계·스레드를 대역으로 바꿔 워밍업까지 돌린다(boot 도우미).
- EMA·MACD 경로: 이미 보유 차단·시장가 인자·엔진 관리자 경로가 그대로인지 함께 본다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine -v
"""
from __future__ import annotations

import ast
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time as _time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401  (config 가 import 때 secrets 를 읽으므로 chdir 전에)
from config import MIN_FEE_RATIO  # noqa: E402
from core import strategy_engine as se  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.candle_buffer import Bar, CandleBuffer  # noqa: E402
from core.indicator_state import IndicatorState  # noqa: E402
from core.position_state import PositionState  # noqa: E402
from core.strategy_action import Action  # noqa: E402
import engine.engine_manager as engine_manager  # noqa: E402
import engine.live_loop as live_loop  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import (  # noqa: E402
    DEAD, ScriptedIndicators, V, ts_at,
)

USER = "t5u"
TICKER = "KRW-TEST"

CFG = {
    "ticker": TICKER, "interval": "minute3", "maType": "ema",
    "ma60p": 3, "ma200p": 10, "pullbackP": 5, "slopeLB": 2,
    "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": False,
    "maxSplits": 5, "maxPullbackBuys": 3, "tp": 5, "sl": 90,
    "deadcross": True, "compounding": False, "capital": 1_000_000, "fee": 0.05,
}


def cfg(**over):
    d = dict(CFG)
    d.update(over)
    return pbp.validate(d)


def bar(i, o=55.0, h=None, l=None, c=None, *, confirmed=True, source="REST_RECONCILED"):
    c = o if c is None else c
    h = max(o, c) if h is None else h
    l = min(o, c) if l is None else l
    return Bar(ts=ts_at(i), open=o, high=h, low=l, close=c, volume=1.0,
               is_closed=True, is_confirmed=confirmed, source=source)


DIP = dict(o=55, h=56, l=40, c=55)       # low 40 < maPullback 50 < close 55 → armed 후 같은 봉 매수 (high 는 TP 아래)
CALM = dict(o=55, h=56, l=52, c=55)      # low 52 ≥ 50 → armed 안 됨
DIFF = {"rest_failed": False, "changed_count": 0, "changed_ts": []}


# ---------------------------------------------------------------- 가짜 trader
class FakeTrader:
    def __init__(self, avail=10_000_000, test_mode=True, buy_ok=True):
        self.user_id = USER
        self.test_mode = test_mode
        self.avail = avail
        self.buy_ok = buy_ok
        self.balance_ok = True          # False 면 잔고 조회 실패(0.0 + last_krw_balance_ok=False)
        self.raise_on_buy = None        # 예외를 넣으면 buy_market 이 그 예외를 던진다
        self.strict_reject_code = None  # 넣으면 buy_market 이 {} 를 돌려주는 엄격 금액 거절(last_buy_error 없음)
        self.coin = 0.0
        self.buy_calls, self.limit_calls, self.sell_calls, self.rejects = [], [], [], []
        self.last_buy_error = None
        self.last_krw_balance_ok = True
        self.last_strict_reject_code = None

    def set_strategy_ref(self, s):
        self.strategy_ref = s

    def _krw_balance(self):
        self.last_krw_balance_ok = self.balance_ok
        return self.avail if self.balance_ok else 0.0

    def _coin_balance(self, ticker):
        return self.coin

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        self.buy_calls.append({"price": price, "ticker": ticker, "ts": ts, "meta": dict(meta or {}),
                               "krw_amount": krw_amount, "strict_amount": strict_amount})
        if self.raise_on_buy is not None:
            raise self.raise_on_buy
        if self.strict_reject_code:
            self.last_strict_reject_code = self.strict_reject_code
            return {}
        if not self.buy_ok:
            self.last_buy_error = "Upbit error [under_maintenance]: 점검"
            return {}
        qty = (krw_amount or 100_000) / price
        self.coin += qty
        return {"qty": qty, "price": price, "uuid": f"u{len(self.buy_calls)}"}

    def buy_limit(self, *a, **k):
        self.limit_calls.append((a, k))
        return {}

    def sell_market(self, qty, ticker, price, ts=None, meta=None):
        self.sell_calls.append({"qty": qty, "price": price, "meta": dict(meta or {})})
        self.coin = 0.0
        return {"qty": qty, "price": price}

    def _audit_preorder_reject(self, *, ticker, price, meta, code, note, extra=None):
        self.rejects.append({"code": code, "note": note, "meta": dict(meta or {}), "extra": dict(extra or {})})


class EngineCase(unittest.TestCase):
    """DB·알림·reconciler 를 막고 PULLBACK 엔진을 만든다."""

    def setUp(self):
        self.notify = mock.MagicMock(return_value=True)
        self.capital = 3_000_000
        patches = [
            mock.patch("engine.reconciler_singleton.get_reconciler", return_value=mock.MagicMock()),
            mock.patch.object(se, "insert_buy_eval", mock.MagicMock(return_value="inserted")),
            mock.patch.object(se, "insert_sell_eval", mock.MagicMock(return_value="inserted")),
            mock.patch.object(se, "get_trading_paused", mock.MagicMock(return_value=False)),
            mock.patch.object(se, "annotate_buy_eval_blocked", mock.MagicMock()),
            mock.patch.object(se.StrategyEngine, "_record_invariant_snapshot", lambda self, **k: None),
            mock.patch("services.notifier.send", self.notify),
            mock.patch("services.db.get_initial_krw", side_effect=lambda u: self.capital),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def make(self, values=None, trader=None, *, strategy_type="PULLBACK", **over):
        trader = trader or FakeTrader()
        c = cfg(**over)
        strat = sp.IncrementalPullbackStrategy(USER, TICKER, c, 3)
        ind = ScriptedIndicators(values or [V()] * 40)
        ring = sp.PullbackSnapshotRing(sp.RING_CAPACITY)
        strat.bind(ind, ring)
        pos = PositionState(trader=trader, ticker=TICKER)
        eng = se.StrategyEngine(
            buffer=CandleBuffer(maxlen=500), indicators=IndicatorState(), position=pos,
            strategy=strat, trader=trader, user_id=USER, ticker=TICKER,
            strategy_type=strategy_type, q=None, interval_sec=180,
            take_profit=c["tp"] / 100, stop_loss=c["sl"] / 100,
        )
        eng.pullback_indicators = ind
        eng.pullback_ring = ring
        self.trader, self.strat, self.eng = trader, strat, eng
        return eng

    def feed(self, *bars):
        for b in bars:
            self.eng.on_new_bar_confirmed(b, pd.DataFrame(), dict(DIFF))
        return self.strat.last_action


# ================================================================ 계획 T5 시험 14개
class TestSplitBuy(EngineCase):
    def test_split_amount_is_capital_div_splits(self):
        self.make()
        self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)
        self.assertEqual(len(self.trader.buy_calls), 1)
        call = self.trader.buy_calls[0]
        self.assertEqual(call["krw_amount"], 600_000)
        self.assertTrue(call["strict_amount"])
        m = call["meta"]
        self.assertEqual((m["reason"], m["split_round"], m["pullback_round"]), ("PULLBACK", 1, 1))
        self.assertEqual((m["sizing_base"], m["per_buy"], m["strategy_type"]), (3_000_000, 600_000, "PULLBACK"))
        self.assertTrue(self.eng.position.has_position)

    def test_split_skip_below_min(self):
        self.capital = 20_000
        self.make()
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        codes = [r["code"] for r in self.trader.rejects]
        self.assertEqual(codes, ["split_below_min"])
        self.assertIn("1회 매수 금액 4,000원 < 최소 5,000원 — 1회차 건너뜀", self.trader.rejects[0]["note"])

    def test_split_skip_krw_short_audit(self):
        self.make(trader=FakeTrader(avail=500_000))
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual([r["code"] for r in self.trader.rejects], ["split_krw_short"])
        note = self.trader.rejects[0]["note"]
        self.assertIn("원화 잔고 부족", note)
        self.assertIn("가용 500,000원 < 회당 600,000원+수수료", note)
        self.assertIn("1회차 건너뜀", note)

    def test_pullback_always_market(self):
        self.make(trader=FakeTrader(test_mode=False))
        self.strat.buy_conditions = {"fixed_price_buy_enabled": True}  # 조건 파일에 지정가가 켜져 있어도
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.limit_calls, [])
        self.assertEqual(len(self.trader.buy_calls), 1)

    def test_pullback_skips_pending_queue(self):
        self.make()
        self.strat.last_buy_reason = "PULLBACK"
        self.strat.entry_count = 1
        with mock.patch.object(self.eng._pending_orders, "register") as reg:
            self.eng._execute_buy_or_defer(bar(0, **DIP, confirmed=False), {})
            self.eng._execute_buy(bar(0, **DIP, confirmed=False), {})
        reg.assert_not_called()
        self.assertEqual(self.trader.buy_calls, [])  # 미확정 봉은 PULLBACK 매수를 하지 않는다(이중 차단)
        self.assertTrue(all(r["code"] == "split_unconfirmed_bar" for r in self.trader.rejects))

    def test_pullback_buy_eval_while_holding(self):
        self.make()
        self.feed(bar(0, **DIP))                     # 1회차
        self.feed(bar(1, **CALM))                    # 체결 봉
        self.assertTrue(self.eng.position.has_position)
        self.assertIs(self.feed(bar(2, **DIP)), Action.BUY)  # 보유 중 다음 눌림 → 2회차
        self.assertEqual([c["meta"]["split_round"] for c in self.trader.buy_calls], [1, 2])
        self.assertEqual(self.trader.rejects, [])   # already_holding 차단 없음
        q1 = 600_000 / 55.0
        self.assertAlmostEqual(self.eng.position.qty, 2 * q1)
        self.assertAlmostEqual(self.eng.position.avg_price, 55.0)

    def test_pullback_pause_blocks_orders(self):
        self.make()
        se.get_trading_paused.return_value = True
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual([r["code"] for r in self.trader.rejects], ["trading_paused"])
        self.assertEqual((self.strat.entry_count, self.strat.pullback_count, self.strat.pending_fill), (0, 0, False))

    def test_skip_clears_armed_like_buy(self):
        self.make(trader=FakeTrader(avail=500_000))
        self.feed(bar(0, **DIP))
        self.assertFalse(self.strat.armed)
        self.assertEqual((self.strat.entry_count, self.strat.pullback_count, self.strat.pending_fill), (0, 0, False))
        self.feed(bar(1, **CALM), bar(2, o=55, h=58, l=51, c=57))  # 같은 눌림의 다음 봉들(새 눌림 없음)
        self.assertEqual(len(self.trader.rejects), 1)  # 건너뜀 감사 행이 쌓이지 않음
        # 보유 중 2회차 건너뜀도 회차 불변
        self.trader.avail = 10_000_000
        self.feed(bar(3, **DIP), bar(4, **CALM))
        self.assertEqual(self.strat.entry_count, 1)
        self.trader.avail = 100_000
        self.feed(bar(5, **DIP))
        self.assertEqual((self.strat.entry_count, self.strat.pullback_count, self.strat.pending_fill), (1, 1, False))
        self.assertFalse(self.strat.armed)
        self.assertEqual(self.trader.rejects[-1]["code"], "split_krw_short")
        self.assertIn("2회차 건너뜀", self.trader.rejects[-1]["note"])

    def test_pullback_trader_no_params_file(self):
        """엔진 관리자 PULLBACK 기동: load_params 안 부름, trader params_file=None, risk_pct=1/effMaxSplits."""
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            self.addCleanup(os.chdir, cwd)
            Path(f"{USER}_active_strategy.txt").write_text("PULLBACK")
            Path(pbp.applied_path(USER)).write_text(json.dumps(cfg(maxSplits=4)))
            got = run_engine_runner(self)
        self.assertEqual(got["load_params"].call_count, 0)
        kw = got["trader_cls"].call_args.kwargs
        self.assertIsNone(kw["params_file"])
        self.assertEqual(kw["strategy_type"], "PULLBACK")
        self.assertAlmostEqual(kw["risk_pct"], 0.25)
        args, kwargs = got["run"]
        self.assertEqual(kwargs["pullback_cfg"], cfg(maxSplits=4))
        self.assertEqual(args[0].strategy_type, "PULLBACK")
        self.assertEqual(args[0].cash, 3_000_000)
        # 실제 UpbitTrader 도 params_file=None 이면 order_ratio 파일을 읽지 않는다
        from core.trader import UpbitTrader
        with mock.patch("core.trader.get_account", return_value=1.0):
            t = UpbitTrader(USER, risk_pct=0.25, test_mode=True, strategy_type="PULLBACK", params_file=None)
        self.assertIsNone(t._params_file)
        self.assertEqual(t._current_risk_pct(), 0.25)


class TestStrictAmount(unittest.TestCase):
    def _trader(self, krw):
        from core.trader import UpbitTrader
        ps = [
            mock.patch("core.trader.pyupbit.Upbit"),
            mock.patch.object(UpbitTrader, "_krw_balance", side_effect=krw if isinstance(krw, list) else None,
                              return_value=None if isinstance(krw, list) else krw),
            mock.patch("core.trader.insert_order"),
            mock.patch("core.trader.insert_log"),
            mock.patch("services.notifier.send", mock.MagicMock(return_value=True)),
            mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
            mock.patch("engine.reconciler_singleton.get_reconciler", return_value=mock.MagicMock()),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        self.up = mock.patch("core.trader._upbit_buy_market", return_value={
            "ok": True, "status": 201, "error_name": None, "error_message": None,
            "exception": None, "body": "", "data": {"uuid": "x-1"}}).start()
        self.addCleanup(mock.patch.stopall)
        t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)
        self.rej = mock.patch.object(t, "_audit_preorder_reject").start()
        return t

    def test_split_never_shrinks_amount(self):
        t = self._trader(500_000)
        self.assertEqual(t.buy_market(1000.0, TICKER, meta={"reason": "PULLBACK"}, krw_amount=600_000,
                                      strict_amount=True), {})
        self.up.assert_not_called()
        self.assertEqual(self.rej.call_args.kwargs["code"], "split_krw_short")
        # 기본(strict_amount=False) 은 지금처럼 가용 금액까지 줄여 산다 (WO-24 회귀)
        t.buy_market(1000.0, TICKER, meta={}, krw_amount=600_000)
        self.up.assert_called_once_with(TICKER, math.floor(min(600_000, 500_000 / (1 + MIN_FEE_RATIO))))

    def test_strict_exact_amount_and_retry_loop_no_shrink(self):
        t = self._trader(700_000)
        t.buy_market(1000.0, TICKER, meta={}, krw_amount=600_000, strict_amount=True)
        self.up.assert_called_once_with(TICKER, 600_000)
        # 시도 직전 재조회에서 잔고가 줄면(외부 주문 등) 줄여 사지 않고 거절
        t2 = self._trader([700_000, 500_000])
        self.up.reset_mock()
        self.assertEqual(t2.buy_market(1000.0, TICKER, meta={}, krw_amount=600_000, strict_amount=True), {})
        self.up.assert_not_called()
        self.assertEqual(self.rej.call_args.kwargs["code"], "split_krw_short")


class TestEmaUnchanged(EngineCase):
    def test_ema_still_blocks_already_holding(self):
        self.make(strategy_type="EMA")
        self.eng.strategy = SimpleNamespace(last_buy_reason="EMA_GC", buy_conditions={}, last_weak_entry=None)
        self.eng.position.open_position(1.0, 100.0, 0, ts_at(0))
        self.eng._execute_buy(bar(1), {"ema_fast": 1, "ema_slow": 2})
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual([r["code"] for r in self.trader.rejects], ["already_holding"])

    def test_ema_market_buy_args_unchanged(self):
        self.make(strategy_type="EMA")
        self.eng.strategy = SimpleNamespace(last_buy_reason="EMA_GC", buy_conditions={}, last_weak_entry=None)
        self.eng._execute_buy(bar(1), {"ema_fast": 1, "ema_slow": 2})
        self.assertEqual(len(self.trader.buy_calls), 1)
        c = self.trader.buy_calls[0]
        self.assertIsNone(c["krw_amount"])       # EMA 는 엄격 금액 인자를 넘기지 않음
        self.assertFalse(c["strict_amount"])
        self.assertNotIn("split_round", c["meta"])


class TestSellReject(EngineCase):
    def test_pullback_sell_reject_visible(self):
        from core.trader import UpbitTrader
        audit = mock.MagicMock()
        ps = [
            mock.patch("core.trader.pyupbit.Upbit"),
            mock.patch("core.trader.insert_trade_audit", audit),
            mock.patch("core.trader.insert_log"),
            mock.patch("core.trader.insert_order"),
            mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
            mock.patch.object(UpbitTrader, "_coin_balance", return_value=1000.0),
            mock.patch("core.trader._upbit_sell_market", return_value={
                "ok": False, "status": 400, "error_name": "insufficient_funds_ask",
                "error_message": "주문가능한 금액(KRW-TEST)이 부족합니다.", "exception": None, "body": "",
                "data": None}),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        trader = UpbitTrader(USER, risk_pct=0.2, test_mode=False, strategy_type="PULLBACK", params_file=None)
        self.make(trader=trader)
        self.eng.position.open_position(1000.0, 100.0, 0, ts_at(0))
        self.strat.restore_split_state({"entry_count": 1, "pullback_count": 1, "first_entry_ts": ts_at(0),
                                        "first_entry_reason": "PULLBACK", "trade_origin": "live", "last_ts": ts_at(0)})
        tp_bar = dict(o=100, h=106, l=99, c=104)
        self.assertIs(self.feed(bar(1, **tp_bar)), Action.SELL)
        rejected = [c for c in audit.call_args_list if c.args[4] == "SELL_REJECTED"]
        self.assertEqual(len(rejected), 1)
        bodies = [c.args[2] for c in self.notify.call_args_list if "매도 거절" in c.args[1]]
        self.assertTrue(bodies and "지정가 매도 주문이 있는지 확인" in bodies[0])
        # (T4 넘김 4) 매도 거절 뒤: 회차는 0, 보유는 그대로 → 다음 봉도 TP 재평가, 매수는 POS_DESYNC 로 막힘
        self.assertTrue(self.eng.position.has_position)
        self.assertIs(self.feed(bar(2, **tp_bar)), Action.SELL)
        self.feed(bar(3, **DIP))
        self.assertIn("POS_DESYNC", self.strat.last_eval["failed_keys"])


# ================================================================ T4 「T5 로 넘김」 (1)~(7)
class TestHandoverT4(EngineCase):
    def test_live_call_always_passes_position(self):
        """(3) 실시간 호출은 늘 엔진 position 을 넘기고, position 이 없으면 경고·NOOP."""
        self.make()
        seen = []
        orig = self.strat.on_bar
        self.strat.on_bar = lambda b, s, p, n: (seen.append(p), orig(b, s, p, n))[1]
        self.feed(bar(0, **CALM))
        self.assertIs(seen[0], self.eng.position)
        self.eng.position = None
        with self.assertLogs(se.logger, level="WARNING"):
            self.eng.on_new_bar_confirmed(bar(1, **DIP), pd.DataFrame(), dict(DIFF))
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.trader.buy_calls, [])

    def test_unconfirmed_bar_paths_noop(self):
        """형성 중 봉(on_new_bar) 은 PULLBACK 에서 NOOP — 지표·버퍼 불변."""
        self.make()
        calls = []
        orig = self.strat.on_bar
        self.strat.on_bar = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
        self.eng.on_new_bar(bar(0, **DIP, confirmed=False))
        self.assertEqual(calls, [])                      # 새 가드: 전략 판정 0
        self.assertEqual(len(self.eng.buffer), 0)        # 버퍼 불변
        self.assertEqual(self.eng.bar_count, 0)
        self.assertIsNone(self.eng.last_bar_ts)
        self.assertEqual(self.eng.pullback_indicators.update_count, 0)
        self.assertEqual(self.trader.buy_calls, [])
        self.strat.on_bar = orig
        self.feed(bar(1, **DIP, confirmed=False, source="WO2_OPTION_C_TENTATIVE:ws"))  # 잠정 봉
        self.assertEqual(self.eng.pullback_indicators.update_count, 0)
        self.assertEqual(self.strat.last_eval["failed_keys"], ["TENTATIVE"])

    def test_polluted_blocks_buy_keeps_deadcross_and_alerts(self):
        """(6) 오염: 매수 막고 CRITICAL 1회(재시작 안내), 데드크로스 매도는 유지."""
        vals = [V(), V(), V(), V(), V(**DEAD)]
        self.make(vals)
        self.feed(bar(0, **DIP), bar(1, **CALM))
        self.assertTrue(self.eng.position.has_position)
        self.eng.pullback_indicators.state_polluted = True
        self.feed(bar(2, **DIP))
        self.assertEqual(len(self.trader.buy_calls), 1)
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL" and "오염" in c.args[1]]
        self.assertEqual(len(crit), 1)
        self.assertIn("재시작", crit[0].args[2])
        self.feed(bar(3, **DIP))
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL" and "오염" in c.args[1]]
        self.assertEqual(len(crit), 1)  # 봉마다 다시 보내지 않음
        self.assertIs(self.feed(bar(4, **CALM)), Action.SELL)  # 데드크로스 매도
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertEqual(self.trader.sell_calls[0]["meta"]["reason"], "DEADCROSS")
        # 엔진 BUY 관문도 오염이면 막는다(전략이 BUY 를 내도)
        self.strat.last_buy_reason = "PULLBACK"
        self.eng.execute(Action.BUY, bar(5, **DIP), {})
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual(self.trader.rejects[-1]["code"], "state_polluted")

    def test_buy_fail_resignal_dedupe(self):
        """(7) 실보유 없이 매수 주문이 계속 실패: 회차 되돌림 + 쿨다운 동안 재주문 0, 지나면 다시 시도."""
        self.make(trader=FakeTrader(buy_ok=False))
        self.feed(bar(0, **DIP))
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual((self.strat.entry_count, self.strat.pending_fill), (0, False))
        self.feed(bar(1, **DIP))  # 바로 다음 봉 재신호
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual(self.trader.rejects[-1]["code"], "split_order_cooldown")
        n = se.PULLBACK_BUY_FAIL_COOLDOWN_BARS
        for i in range(2, n + 1):
            self.feed(bar(i, **CALM))
        self.feed(bar(n + 1, **DIP))
        self.assertEqual(len(self.trader.buy_calls), 2)

    def test_skip_alert_dedupe(self):
        """건너뜀 알림은 같은 거래·같은 사유에 1회."""
        self.make(trader=FakeTrader(avail=100_000))
        self.feed(bar(0, **DIP), bar(1, **DIP), bar(2, **DIP))
        self.assertEqual([r["code"] for r in self.trader.rejects], ["split_krw_short"] * 3)
        keys = {c.kwargs.get("dedupe_key") for c in self.notify.call_args_list if "건너뜀" in c.args[1]}
        self.assertEqual(len(keys), 1)


class TestBackfillHandover(EngineCase):
    def test_backfill_keeps_trade_counters_when_holding(self):
        """(5) 보유 중 BACKFILL 재생은 지표·armed 만 바로잡고 회차(실주문 기준)는 바꾸지 않는다."""
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        before = self.strat.export_split_state()

        def fake_replay(engine, **kw):
            engine.strategy.entry_count = 3
            engine.strategy.pullback_count = 3
            engine.strategy.armed = True
            return {"restored": True, "replayed": 2, "audited": 1, "reason": ""}

        ls = pd.DataFrame({"Open": [1.0] * 3, "High": [1.0] * 3, "Low": [1.0] * 3, "Close": [1.0] * 3,
                           "Volume": [1.0] * 3}, index=[ts_at(0), ts_at(1), ts_at(2)])
        with mock.patch.object(sp, "pullback_backfill", side_effect=fake_replay), \
                mock.patch.object(live_loop, "log_to_file"):
            out = live_loop._pullback_backfill_step(self.eng, [ts_at(1)], ls, ts_at(2), USER, None)
        self.assertEqual(out, [])
        after = self.strat.export_split_state()
        for k in ("entry_count", "pullback_count", "first_entry_ts", "first_entry_reason", "trade_origin"):
            self.assertEqual(after[k], before[k], k)
        self.assertTrue(after["armed"])  # 판정 상태는 재생 결과

    def test_backfill_exception_marks_polluted(self):
        """(T3 넘김) pullback_backfill 예외를 감싸 오염 표식 + CRITICAL, 봉별 루프는 여전히 건너뜀."""
        self.make()
        ls = pd.DataFrame({"Open": [1.0] * 2, "High": [1.0] * 2, "Low": [1.0] * 2, "Close": [1.0] * 2,
                           "Volume": [1.0] * 2}, index=[ts_at(0), ts_at(1)])
        with mock.patch.object(sp, "pullback_backfill", side_effect=RuntimeError("boom")), \
                mock.patch.object(live_loop, "log_to_file"):
            out = live_loop._pullback_backfill_step(self.eng, [ts_at(0)], ls, ts_at(1), USER, None)
        self.assertEqual(out, [])
        self.assertTrue(self.eng.pullback_indicators.state_polluted)
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))


def _real_engine_case(case: EngineCase, closes):
    """실제 PullbackIndicators 로 시드한 엔진(재생·BACKFILL 시험용)."""
    eng = case.make()
    c = cfg()
    ind = sp.PullbackIndicators(c["ma60p"], c["ma200p"], c["pullbackP"], c["slopeLB"], c["maType"])
    ring = sp.PullbackSnapshotRing(sp.RING_CAPACITY)
    eng.pullback_indicators, eng.pullback_ring = ind, ring
    case.strat.bind(ind, ring)
    tss = [ts_at(i) for i in range(len(closes))]
    df = pd.DataFrame({"Open": closes, "High": [x * 1.001 for x in closes], "Low": [x * 0.999 for x in closes],
                       "Close": closes, "Volume": [1.0] * len(closes)}, index=tss)
    return eng, df


class TestCatchUp(EngineCase):
    def test_tentative_or_skipped_bar_enters_next_replay(self):
        """(2) 잠정·건너뛴 봉은 다음 주기 catch-up 재생에 반드시 들어간다(주문 없음)."""
        closes = [100 + i * 0.1 for i in range(40)]
        eng, df = _real_engine_case(self, closes)
        for ts, row in df.iloc[:30].iterrows():
            sp.feed_confirmed_bar(eng, sp.bar_from_row(ts, row))
        n0 = eng.pullback_indicators.n
        # 30번 봉: 잠정 봉 → 지표에 안 들어감
        r = df.iloc[30]
        self.feed(Bar(ts=df.index[30], open=r.Close, high=r.Close, low=r.Close, close=r.Close, volume=0.0,
                      is_closed=True, is_confirmed=False, source="WO2_OPTION_C_TENTATIVE:ws"))
        self.assertEqual(eng.pullback_indicators.n, n0)
        # 31번 봉: VERIFY 실패 등으로 건너뜀(엔진에 오지 않음). 32번 봉이 확정 대상.
        with mock.patch.object(live_loop, "log_to_file"):
            live_loop._pullback_catchup_step(eng, df.iloc[:33], df.index[32], USER, None)
        self.assertEqual(eng.pullback_indicators.n, n0 + 2)
        self.assertEqual(self.strat.last_ts, df.index[31])
        self.assertEqual(self.trader.buy_calls, [])
        ref = sp.PullbackIndicators(3, 10, 5, 2, "ema")
        for x in closes[:32]:
            ref.update(x)
        self.assertEqual(eng.pullback_indicators.last_values, ref.last_values)
        self.assertFalse(eng.pullback_indicators.state_polluted)

    def test_catchup_out_of_ring_marks_polluted(self):
        closes = [100 + i * 0.1 for i in range(10)]
        eng, df = _real_engine_case(self, closes)
        for ts, row in df.iloc[:5].iterrows():
            sp.feed_confirmed_bar(eng, sp.bar_from_row(ts, row))
        eng.pullback_ring._q.clear()  # 링에 되돌릴 기록 없음
        with mock.patch.object(live_loop, "log_to_file"):
            live_loop._pullback_catchup_step(eng, df.iloc[:8], df.index[7], USER, None)
        self.assertTrue(eng.pullback_indicators.state_polluted)
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))

    def test_run_live_loop_calls_catchup_after_verify(self):
        """(검수 2) catch-up 은 VERIFY 통과 뒤, engine.on_new_bar_confirmed 바로 앞에서만 (Issue #8)."""
        lines = ast.unparse(_run_live_loop_fn()).splitlines()
        i_verify = next(i for i, ln in enumerate(lines) if "verify_past_candles_with_upbit(" in ln)
        catch = [i for i, ln in enumerate(lines) if "_pullback_catchup_step(" in ln]
        self.assertTrue(catch)
        for i in catch:
            self.assertGreater(i, i_verify)
            nxt = next(ln for ln in lines[i + 1:] if ln.strip())
            self.assertIn("engine.on_new_bar_confirmed(", nxt)
        # on_new_bar_confirmed 를 부르는 실시간 경로(VERIFY 뒤)마다 catch-up 이 앞에 있다
        confirm = [i for i, ln in enumerate(lines) if "engine.on_new_bar_confirmed(" in ln and i > i_verify]
        self.assertEqual(len(confirm), len(catch))


# ================================================================ 기동(run_live_loop) — (1), 조건 파일, 워밍업 로그
def _run_live_loop_fn():
    tree = ast.parse((ROOT / "engine/live_loop.py").read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_live_loop")


def rising_df(n, end=None):
    end = end or (pd.Timestamp.now(tz="UTC").floor("3min") - pd.Timedelta(minutes=30))
    tss = pd.date_range(end=end, periods=n, freq="3min", tz="UTC")
    closes = [1000 + i * 1.0 for i in range(n)]
    return pd.DataFrame({"Open": [c - 0.5 for c in closes], "High": [c + 0.2 for c in closes],
                         "Low": [c - 0.6 for c in closes], "Close": closes, "Volume": [10.0] * n}, index=tss)


class _FakeThread:
    created = []

    def __init__(self, target=None, daemon=None, **k):
        self.target = target
        _FakeThread.created.append(self)

    def start(self):
        pass


def boot(case, pb_cfg, df, *, trader=None):
    """run_live_loop 을 워밍업까지 돌리고 첫 루프에서 멈춘다. (engine, mocks) 를 돌려준다."""
    stop = threading.Event()
    holder = {}
    real_engine_cls = se.StrategyEngine

    def make_engine(*a, **k):
        holder["engine"] = real_engine_cls(*a, **k)
        return holder["engine"]

    class FakeClock(live_loop.CandleClock):
        def should_close(self, now):
            stop.set()
            return False

    _FakeThread.created = []
    cond = mock.MagicMock(name="_load_trade_conditions", return_value={"buy": {"x": 1}, "sell": {"y": 2}})
    snap = mock.MagicMock(name="insert_settings_snapshot")
    th = SimpleNamespace(Thread=_FakeThread, Event=threading.Event, Lock=threading.Lock,
                         current_thread=threading.current_thread)
    ps = [
        mock.patch.object(live_loop, "RUN_MODE", "UPBIT_MATCH"),
        mock.patch.object(live_loop, "safe_fetch_rest", return_value=df),
        mock.patch.object(live_loop, "get_reconciler", return_value=mock.MagicMock()),
        mock.patch.object(live_loop, "_load_trade_conditions", cond),
        mock.patch.object(live_loop, "insert_settings_snapshot", snap),
        mock.patch.object(live_loop, "CandleClock", FakeClock),
        mock.patch.object(live_loop, "StrategyEngine", side_effect=make_engine),
        mock.patch.object(live_loop, "log_to_file"),
        mock.patch.object(live_loop, "threading", th),
    ]
    for p in ps:
        p.start()
    try:
        params = pbp.to_live_params(pb_cfg, 1_000_000)
        live_loop.run_live_loop(params, queue.Queue(), trader or FakeTrader(), stop, True, USER,
                                pullback_cfg=pb_cfg)
        # 설정 스냅샷 타이머 1회 돌리기(분 스냅샷 + 핫 리로드 검사) — sleep 에서 멈춤
        timer = next(t.target for t in _FakeThread.created if t.target.__name__ == "_settings_snapshot_timer")
        stop.clear()
        with mock.patch.object(live_loop, "time", SimpleNamespace(sleep=lambda s: stop.set(), time=_time.time)):
            timer()
    finally:
        for p in reversed(ps):
            p.stop()
    return holder["engine"], {"cond": cond, "snap": snap, "stop": stop}


class InTmpCwd(EngineCase):
    def setUp(self):
        super().setUp()
        self._cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self._cwd)


class TestBoot(InTmpCwd):
    def test_boot_strategy_before_seed_no_golden_first_bar(self):
        """(1) 시드 전에 engine.strategy = PULLBACK 전략 → 시드가 prev_golden 까지 만든다 → 기동 첫 봉 GOLDEN 0."""
        c = cfg(buyOnGoldenCross=True)
        df = rising_df(300)
        eng, _ = boot(self, c, df)
        st = eng.strategy
        self.assertIsInstance(st, sp.IncrementalPullbackStrategy)
        self.assertIs(st.indicators, eng.pullback_indicators)
        self.assertIs(st.ring, eng.pullback_ring)
        self.assertEqual(st.last_ts, df.index[-1])           # 시드 봉 수 = 전략이 본 마지막 봉
        self.assertEqual(eng.pullback_indicators.n, len(df))
        self.assertTrue(st.prev_golden)
        nxt = df.index[-1] + pd.Timedelta(minutes=3)
        last = float(df.Close.iloc[-1]) + 1
        eng.on_new_bar_confirmed(Bar(ts=nxt, open=last - 0.5, high=last + 0.2, low=last - 0.3, close=last,
                                     volume=10.0, is_closed=True, is_confirmed=True, source="REST_RECONCILED"),
                                 df, dict(DIFF))
        self.assertFalse(st.last_eval["just_crossed"])
        self.assertTrue(st.last_eval["golden"] and st.last_eval["active"])
        self.assertEqual(eng.trader.buy_calls, [])

    def test_pullback_does_not_load_conditions(self):
        Path(f"{USER}_buy_sell_conditions.json").write_text(json.dumps({"buy": {"fixed_price_buy_enabled": True},
                                                                        "sell": {"take_profit_pct": 9}}))
        eng, m = boot(self, cfg(), rising_df(300))
        m["cond"].assert_not_called()
        self.assertEqual(getattr(eng.strategy, "buy_conditions", {}) or {}, {})
        # 조건 파일 mtime 감시도 PULLBACK 에서는 경로를 잡지 않는다
        src = ast.unparse(_run_live_loop_fn())
        for line in [ln for ln in src.splitlines() if "_get_trade_conditions_path(" in ln]:
            self.assertIn("PULLBACK", line, line)

    def test_pullback_snapshot_uses_applied_tp_sl_empty_conditions(self):
        eng, m = boot(self, cfg(tp=5, sl=3), rising_df(300))
        m["cond"].assert_not_called()
        self.assertGreaterEqual(m["snap"].call_count, 1)
        kw = m["snap"].call_args.kwargs
        self.assertAlmostEqual(kw["tp"], 0.05)
        self.assertAlmostEqual(kw["sl"], 0.03)
        self.assertEqual((kw["buy_dict"], kw["sell_dict"]), ({}, {}))
        self.assertIsNone(kw["ts_pct"])
        self.assertEqual((kw["signal_gate"], kw["threshold"]), (False, 0.0))

    def test_record_warmup_log_pullback_label_and_progress(self):
        eng, _ = boot(self, cfg(), rising_df(300))
        calls = se.insert_buy_eval.call_args_list
        wu = [c for c in calls if (c.kwargs.get("checks") or {}).get("status") == "WARMUP"]
        self.assertTrue(wu)
        ck = wu[-1].kwargs["checks"]
        self.assertEqual((ck["strategy"], ck["strategy_mode"]), ("PULLBACK", "PULLBACK"))
        self.assertIn("지표 300/", wu[-1].kwargs["notes"])       # 지표 봉 수(버퍼 500 이 아님)
        self.assertNotIn("/24)", ck["progress"].replace("지표 300/24", ""))

    def test_pullback_cfg_none_refuses_critical(self):
        params = pbp.to_live_params(cfg(), 1_000_000)
        stop = threading.Event()
        with mock.patch.object(live_loop, "get_reconciler") as rec:
            live_loop.run_live_loop(params, queue.Queue(), FakeTrader(), stop, True, USER)
        rec.assert_not_called()
        self.assertTrue(stop.is_set())
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))

    def test_legacy_mode_refuses_pullback(self):
        params = pbp.to_live_params(cfg(), 1_000_000)
        stop = threading.Event()
        with mock.patch.object(live_loop, "RUN_MODE", "LEGACY_LOCAL"), \
                mock.patch.object(live_loop, "get_reconciler") as rec:
            live_loop.run_live_loop(params, queue.Queue(), FakeTrader(), stop, True, USER, pullback_cfg=cfg())
        rec.assert_not_called()
        self.assertTrue(stop.is_set())
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))


# ================================================================ 엔진 관리자 (T1 거부 처리 · T2 넘김)
def run_engine_runner(case, *, session=None, params=None, test_mode=True):
    lock = threading.Lock()
    stop = threading.Event()
    got = {"load_params": mock.MagicMock(name="load_params", return_value=params),
           "trader_cls": mock.MagicMock(name="UpbitTrader"),
           "insert_log": mock.MagicMock(name="insert_log")}

    def fake_run(*a, **k):
        got["run"] = (a, k)
        stop.set()

    ps = [
        mock.patch.object(engine_manager, "st", mock.MagicMock(session_state={"strategy_type": session})),
        mock.patch.object(engine_manager, "load_params", got["load_params"]),
        mock.patch.object(engine_manager, "UpbitTrader", got["trader_cls"]),
        mock.patch.object(engine_manager, "get_user_lock", return_value=lock),
        mock.patch.object(engine_manager, "insert_log", got["insert_log"]),
        mock.patch.object(engine_manager, "log_to_file"),
        mock.patch.object(engine_manager, "update_engine_status"),
        mock.patch.object(engine_manager, "set_engine_status"),
        mock.patch.object(engine_manager, "set_thread_status"),
        mock.patch.object(engine_manager, "remove_engine_thread"),
        mock.patch.object(engine_manager, "add_engine_thread"),
        mock.patch.object(engine_manager, "run_live_loop", side_effect=fake_run),
        mock.patch("services.db.get_coin_balance", return_value=0.0),
    ]
    for p in ps:
        p.start()
    try:
        t = threading.Thread(target=engine_manager.EngineManager()._engine_runner,
                             args=(USER, stop, test_mode, "TEST" if test_mode else "LIVE"), daemon=True)
        t.start()
        t.join(timeout=10)
        if t.is_alive():
            stop.set()
            t.join(timeout=3)
            case.fail("_engine_runner 가 끝나지 않음")
    finally:
        for p in reversed(ps):
            p.stop()
    got["lock"] = lock
    got["stop"] = stop
    return got


class TestEngineManager(InTmpCwd):
    def test_refuses_when_no_params_no_trader_critical(self):
        Path(f"{USER}_active_strategy.txt").write_text("PULLBACK")
        got = run_engine_runner(self, session="EMA")
        got["trader_cls"].assert_not_called()
        got["load_params"].assert_not_called()
        self.assertNotIn("run", got)
        self.assertFalse(got["lock"].locked())
        errors = [c.args[2] for c in got["insert_log"].call_args_list if c.args[1] == "ERROR"]
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in errors))
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))

    def test_refuses_when_live_params_fail(self):
        """(T2 넘김 ③) to_live_params 실패(운용자산 없음) → 거부·CRITICAL, 기동이 거부 절차 없이 죽지 않음."""
        Path(f"{USER}_active_strategy.txt").write_text("PULLBACK")
        Path(pbp.applied_path(USER)).write_text(json.dumps(cfg()))
        self.capital = None
        got = run_engine_runner(self)
        got["trader_cls"].assert_not_called()
        self.assertNotIn("run", got)
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertTrue(crit)
        errors = [c.args[2] for c in got["insert_log"].call_args_list if c.args[1] == "ERROR"]
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in errors))

    def test_ema_runner_path_unchanged(self):
        Path(f"{USER}_active_strategy.txt").write_text("EMA")
        p = pbp.to_live_params(cfg(), 1_000_000)
        p.strategy_type = "EMA"
        got = run_engine_runner(self, session=None, params=p)
        got["load_params"].assert_called_once_with(f"{USER}_{config.PARAMS_JSON_FILENAME}", strategy_type="EMA")
        kw = got["trader_cls"].call_args.kwargs
        self.assertEqual(kw["params_file"], engine_manager.scoped_params_path(
            f"{USER}_{config.PARAMS_JSON_FILENAME}", "EMA"))
        args, kwargs = got["run"]
        self.assertEqual(kwargs, {})            # EMA 는 pullback_cfg 를 넘기지 않음
        self.assertEqual(len(args), 6)


class TestNoActivePullbackWriter(unittest.TestCase):
    def test_no_path_writes_pullback_active_or_applied(self):
        """T1 「T5 완료 전까지 활성 파일에 PULLBACK 을 쓰는 경로를 만들지 않는다(쓰는 곳은 T12)」 — 아직 없음."""
        offenders = []
        for p in ROOT.rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", ".venv", "venv/", ".superpowers")) or "/site-packages/" in rel:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "apply_saved(" in text and rel != "engine/pullback_params.py":
                offenders.append(rel)
            if "save_active_strategy(" in text and rel not in ("engine/params.py", "pages/set_config.py"):
                offenders.append(rel)
        self.assertEqual(offenders, [])
        # set_config 가 고를 수 있는 전략 목록(STRATEGY_TYPES)에 PULLBACK 이 없다 → 화면에서 활성 파일에 못 씀
        self.assertNotIn("PULLBACK", config.STRATEGY_TYPES)
        src = (ROOT / "pages/set_config.py").read_text(encoding="utf-8")
        self.assertNotIn('"PULLBACK"', src)
        self.assertNotIn("'PULLBACK'", src)


# ================================================================ T5 검수 반영 (10/28)
LIVE_REFUSE_TEXT = "새 전략은 실계좌(LIVE)에서 아직 쓸 수 없습니다 (분할 체결 반영 작업 뒤 엽니다)"


def run_one_close(case, *, verify_ok):
    """run_live_loop 을 기동 → 봉 마감 1회(closed_ts) 처리 → 멈춤. 사건 순서(events)를 돌려준다.
    시드는 마지막 2봉을 뺀 봉으로 하고, 마감 봉은 df 마지막 봉이다(사이 1봉이 catch-up 대상)."""
    c = cfg()
    df = rising_df(300)
    seed_df = df.iloc[:-2]
    closed = df.index[-1]
    events = []
    stop = threading.Event()
    phase = {"loop": False, "closes": [closed]}
    real_engine_cls = se.StrategyEngine

    def make_engine(*a, **k):
        e = real_engine_cls(*a, **k)
        orig = e.on_new_bar_confirmed

        def spy(b, ls, d):
            events.append(("confirm", b.ts))
            return orig(b, ls, d)

        e.on_new_bar_confirmed = spy
        return e

    class FakeClock(live_loop.CandleClock):
        def should_close(self, now):
            if phase["closes"]:
                phase["loop"] = True
                return True
            stop.set()
            return False

        def get_closed_ts(self, now):
            return phase["closes"].pop(0)

    real_catch = live_loop._pullback_catchup_step

    def catch_spy(*a, **k):
        events.append(("catchup",))
        return real_catch(*a, **k)

    def verify(*a, **kw):
        events.append(("verify",))
        return verify_ok

    _FakeThread.created = []
    th = SimpleNamespace(Thread=_FakeThread, Event=threading.Event, Lock=threading.Lock,
                         current_thread=threading.current_thread)
    ps = [
        mock.patch.object(live_loop, "RUN_MODE", "UPBIT_MATCH"),
        mock.patch.object(live_loop, "safe_fetch_rest", side_effect=lambda *a, **kw: (df if phase["loop"] else seed_df)),
        mock.patch.object(live_loop, "fetch_confirmed_candle", side_effect=lambda *a, **kw: df.loc[closed].copy()),
        mock.patch.object(live_loop, "verify_past_candles_with_upbit", side_effect=verify),
        mock.patch.object(live_loop, "_pullback_catchup_step", side_effect=catch_spy),
        mock.patch.object(live_loop, "get_reconciler", return_value=mock.MagicMock()),
        mock.patch.object(live_loop, "insert_settings_snapshot"),
        mock.patch.object(live_loop, "CandleClock", FakeClock),
        mock.patch.object(live_loop, "StrategyEngine", side_effect=make_engine),
        mock.patch.object(live_loop, "log_to_file"),
        mock.patch.object(live_loop, "threading", th),
        mock.patch.object(live_loop, "time", SimpleNamespace(sleep=lambda s: None, time=_time.time)),
    ]
    for p in ps:
        p.start()
    try:
        params = pbp.to_live_params(c, 1_000_000)
        live_loop.run_live_loop(params, queue.Queue(), FakeTrader(), stop, True, USER, pullback_cfg=c)
    finally:
        for p in reversed(ps):
            p.stop()
    return events, closed


class TestReviewRound(EngineCase):
    # ---- 1. LIVE 기동 거부 (T6 체결 반영 전)
    def test_pullback_live_refused_until_t6(self):
        params = pbp.to_live_params(cfg(), 1_000_000)
        stop = threading.Event()
        with mock.patch.object(live_loop, "RUN_MODE", "UPBIT_MATCH"), \
                mock.patch.object(live_loop, "get_reconciler") as rec, \
                self.assertLogs(live_loop.logger, level="ERROR") as logs:
            live_loop.run_live_loop(params, queue.Queue(), FakeTrader(test_mode=False), stop, False, USER,
                                    pullback_cfg=cfg())
        rec.assert_not_called()
        self.assertTrue(stop.is_set())
        self.assertTrue(any(LIVE_REFUSE_TEXT in m for m in logs.output))
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertTrue(any(LIVE_REFUSE_TEXT in (c.args[1] + c.args[2]) for c in crit))
        # 엔진 관리자: LIVE 면 적용본을 읽기 전에 거부, 실제 키 trader 를 만들지 않음
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            self.addCleanup(os.chdir, cwd)
            Path(f"{USER}_active_strategy.txt").write_text("PULLBACK")
            Path(pbp.applied_path(USER)).write_text(json.dumps(cfg()))
            self.notify.reset_mock()
            got = run_engine_runner(self, test_mode=False)
        got["trader_cls"].assert_not_called()
        self.assertNotIn("run", got)
        self.assertFalse(got["lock"].locked())
        errors = [c.args[2] for c in got["insert_log"].call_args_list if c.args[1] == "ERROR"]
        self.assertTrue(any(LIVE_REFUSE_TEXT in m for m in errors))
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertTrue(any(LIVE_REFUSE_TEXT in (c.args[1] + c.args[2]) for c in crit))

    # ---- 2. catch-up 은 VERIFY 통과 뒤에만
    def test_verify_fail_no_catchup(self):
        events, _ = run_one_close(self, verify_ok=False)
        self.assertIn(("verify",), events)
        self.assertNotIn(("catchup",), events)
        self.assertFalse([e for e in events if e[0] == "confirm"])

    def test_verify_pass_catchup_then_confirm(self):
        events, closed = run_one_close(self, verify_ok=True)
        self.assertEqual(events, [("verify",), ("catchup",), ("confirm", closed)])

    # ---- 3. 잔고 조회 실패 ≠ 잔고 부족
    def test_engine_balance_unknown_skip(self):
        self.make()
        self.trader.balance_ok = False
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual([r["code"] for r in self.trader.rejects], ["split_krw_unknown"])
        self.assertIn("잔고 조회 실패", self.trader.rejects[0]["note"])
        bodies = [c.args[1] + c.args[2] for c in self.notify.call_args_list]
        self.assertTrue(any("잔고 조회 실패" in b for b in bodies))
        self.assertFalse(any("잔고 부족" in b for b in bodies))
        self.assertEqual((self.strat.entry_count, self.strat.armed), (0, False))

    def _live_trader(self, balances):
        """실제 UpbitTrader(LIVE). upbit.get_balance 가 balances 를 차례로 돌려주거나 던진다."""
        from core.trader import UpbitTrader
        ps = [
            mock.patch("core.trader.pyupbit.Upbit"),
            mock.patch("core.trader.insert_order"),
            mock.patch("core.trader.insert_log"),
            mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        up_p = mock.patch("core.trader._upbit_buy_market", return_value={
            "ok": True, "status": 201, "error_name": None, "error_message": None,
            "exception": None, "body": "", "data": {"uuid": "x-1"}})
        up = up_p.start()
        self.addCleanup(up_p.stop)
        t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)
        t.upbit.get_balance.side_effect = balances
        rej_p = mock.patch.object(t, "_audit_preorder_reject")
        rej = rej_p.start()
        self.addCleanup(rej_p.stop)
        return t, up, rej

    def test_trader_balance_unknown_first_check(self):
        t, up, rej = self._live_trader([RuntimeError("network")])
        self.assertEqual(t.buy_market(1000.0, TICKER, meta={}, krw_amount=600_000, strict_amount=True), {})
        up.assert_not_called()
        self.assertEqual(rej.call_args.kwargs["code"], "split_krw_unknown")
        self.assertIn("잔고 조회 실패", rej.call_args.kwargs["note"])
        self.assertEqual(t.last_strict_reject_code, "split_krw_unknown")
        # EMA 공용 _krw_balance 는 지금처럼 0.0 을 돌려준다(시그니처·반환 불변)
        t.upbit.get_balance.side_effect = [RuntimeError("x")]
        self.assertEqual(t._krw_balance(), 0.0)
        self.assertFalse(t.last_krw_balance_ok)
        t.upbit.get_balance.side_effect = [123.0]
        self.assertEqual(t._krw_balance(), 123.0)
        self.assertTrue(t.last_krw_balance_ok)

    def test_trader_balance_unknown_retry_requery(self):
        t, up, rej = self._live_trader([700_000.0, RuntimeError("network")])
        self.assertEqual(t.buy_market(1000.0, TICKER, meta={}, krw_amount=600_000, strict_amount=True), {})
        up.assert_not_called()
        self.assertEqual(rej.call_args.kwargs["code"], "split_krw_unknown")

    # ---- 4·5. 결정 1028-03(다): 쿨다운 3봉 + 사용자 고지 (알림 1회 · 감사 1행)
    def _cool_notices(self):
        return [c for c in self.notify.call_args_list
                if c.args[0] == "WARNING" and "쉽니다" in (c.args[2] or "")]

    def _cool_rows(self, tr):
        return [r for r in tr.rejects if r["code"] == "split_order_cooldown"]

    def _fail_once(self, tr=None):
        tr = tr or FakeTrader(buy_ok=False)
        self.make(trader=tr)
        self.feed(bar(0, **DIP))
        fail = self.eng.bar_count
        self.assertEqual(self.eng._pullback_buy_fail_bar, fail)
        tr.buy_ok = True
        return tr, fail

    def test_cooldown_is_3_bars(self):
        self.assertEqual(se.PULLBACK_BUY_FAIL_COOLDOWN_BARS, 3)

    def test_cooldown_boundary_fail_plus_2_blocked(self):
        tr, fail = self._fail_once()
        self.feed(bar(1, **CALM))
        self.feed(bar(2, **DIP))
        self.assertEqual(self.eng.bar_count, fail + 2)
        self.assertEqual(len(tr.buy_calls), 1)
        self.assertEqual(self.strat.entry_count, 0)

    def test_cooldown_boundary_fail_plus_3_orders(self):
        tr, fail = self._fail_once()
        self.feed(bar(1, **CALM), bar(2, **CALM))
        self.feed(bar(3, **DIP))
        self.assertEqual(self.eng.bar_count, fail + 3)
        self.assertEqual(len(tr.buy_calls), 2)

    def test_cooldown_notice_once_and_audit_one_row(self):
        """고지: 쿨다운 시작 때 WARNING 1회 + 감사 BUY_REJECTED(split_order_cooldown) 1행. 쿨다운 중 반복 신호는 추가 0."""
        tr, fail = self._fail_once()
        notes = self._cool_notices()
        self.assertEqual(len(notes), 1)
        title, body = notes[0].args[1], notes[0].args[2]
        self.assertIn("3봉", body)
        self.assertIn("약 9분", body)                       # 3분봉 × 3
        self.assertIn("매도(익절·손절·데드크로스)는 계속합니다", body)
        self.assertIn("업비트 앱", body)                     # 사용자가 할 일
        self.assertIn("under_maintenance", body)            # 무엇이 실패했는지
        self.assertIn(f"pullback_cooldown:{USER}:{TICKER}:", notes[0].kwargs["dedupe_key"])
        self.assertTrue(notes[0].kwargs["dedupe_key"].endswith(ts_at(0).isoformat()))
        rows = self._cool_rows(tr)
        self.assertEqual(len(rows), 1)
        self.assertIn("3봉", rows[0]["note"])
        self.assertIn("끝나는 봉", rows[0]["note"])
        self.assertIn((ts_at(0) + pd.Timedelta(minutes=9)).tz_convert("Asia/Seoul").strftime("%m/%d %H:%M"),
                      rows[0]["note"])
        n_all = len(self.notify.call_args_list)
        self.feed(bar(1, **DIP), bar(2, **DIP))             # 쿨다운 중 반복 신호
        self.assertEqual(len(tr.buy_calls), 1)
        self.assertEqual(len(self._cool_rows(tr)), 1)        # 감사 행 추가 0
        self.assertEqual(len(self.notify.call_args_list), n_all)  # 알림 추가 0

    def test_strict_reject_enters_cooldown_with_notice(self):
        """trader strict 거절(잔고 부족 경쟁)도 쿨다운 + 고지 1회 — 사유 코드와 외부 주문 확인 안내."""
        tr = FakeTrader()
        tr.strict_reject_code = "split_krw_short"
        self.make(trader=tr)
        self.feed(bar(0, **DIP))
        self.assertEqual(self.eng._pullback_buy_fail_bar, 1)
        notes = self._cool_notices()
        self.assertEqual(len(notes), 1)
        self.assertIn("split_krw_short", notes[0].args[2])
        self.assertIn("외부", notes[0].args[2])
        self.assertEqual(len(self._cool_rows(tr)), 1)

    def test_engine_step_skips_do_not_enter_cooldown(self):
        """엔진 사전 검사 건너뜀(최소 미만·잔고 부족·잔고 조회 실패)은 쿨다운에 넣지 않는다 — 다음 봉 바로 주문."""
        tr = FakeTrader(avail=100_000)
        self.make(trader=tr)
        self.feed(bar(0, **DIP))                            # split_krw_short
        tr.balance_ok = False
        self.feed(bar(1, **DIP))                            # split_krw_unknown
        self.assertEqual([r["code"] for r in tr.rejects], ["split_krw_short", "split_krw_unknown"])
        self.assertIsNone(self.eng._pullback_buy_fail_bar)
        self.assertEqual(self._cool_notices(), [])
        tr.balance_ok, tr.avail = True, 10_000_000
        self.feed(bar(2, **DIP))
        self.assertEqual(len(tr.buy_calls), 1)
        # 최소 미만
        self.capital = 20_000
        tr2 = FakeTrader()
        self.make(trader=tr2)
        self.feed(bar(0, **DIP))
        self.assertEqual([r["code"] for r in tr2.rejects], ["split_below_min"])
        self.assertIsNone(self.eng._pullback_buy_fail_bar)

    def test_bot_sell_releases_cooldown(self):
        """봇 매도 체결(close_position reason=bot_sell) → 쿨다운 해제, 다음 신호 바로 주문. 해제 알림 없음."""
        tr = FakeTrader()
        self.make(trader=tr)
        self.feed(bar(0, **DIP), bar(1, **CALM))      # 1회차 체결
        tr.buy_ok = False
        self.feed(bar(2, **DIP))                       # 2회차 주문 실패 → 쿨다운 #3~#5
        self.assertEqual(self.eng._pullback_buy_fail_bar, 3)
        tr.buy_ok = True
        n_all = len(self.notify.call_args_list)
        self.assertIs(self.feed(bar(3, o=55, h=60, l=55, c=59)), Action.SELL)   # TP 매도 체결
        self.assertFalse(self.eng.position.has_position)
        self.assertIsNone(self.eng._pullback_buy_fail_bar)
        self.assertEqual([c for c in self.notify.call_args_list[n_all:] if "쉽니다" in (c.args[2] or "")], [])
        self.feed(bar(4, **DIP))                       # 쿨다운 안(#5)이지만 풀렸으므로 주문
        self.assertEqual(len(tr.buy_calls), 3)

    def test_wallet_zero_sync_keeps_cooldown(self):
        """앱 매도로 지갑 0 동기화(position_sync_wallet_zero)·회차 0 정리로는 풀지 않는다 — 3봉 뒤 저절로 끝남."""
        tr = FakeTrader()
        self.make(trader=tr)
        self.feed(bar(0, **DIP), bar(1, **CALM))
        tr.buy_ok = False
        self.feed(bar(2, **DIP))
        fail = self.eng._pullback_buy_fail_bar
        tr.buy_ok = True
        tr.coin = 0.0                                  # 앱에서 전량 매도
        with mock.patch.object(se.StrategyEngine, "_record_external_sell", lambda *a, **k: None):
            self.feed(bar(3, **CALM))
        self.assertFalse(self.eng.position.has_position)
        self.assertEqual(self.eng._pullback_buy_fail_bar, fail)
        self.feed(bar(4, **DIP))                       # #5 = fail+2 → 막힘
        self.assertEqual(len(tr.buy_calls), 2)
        self.feed(bar(5, **DIP))                       # #6 = fail+3 → 주문
        self.assertEqual(len(tr.buy_calls), 3)

    # ---- 6. execute 예외 → 주문 안 나갔으면 회차 되돌림 + pending 해제
    def test_execute_exception_rolls_back(self):
        tr = FakeTrader()
        tr.raise_on_buy = RuntimeError("socket")
        self.make(trader=tr)
        with self.assertRaises(RuntimeError):
            self.feed(bar(0, **DIP))
        self.assertEqual((self.strat.entry_count, self.strat.pullback_count, self.strat.pending_fill), (0, 0, False))
        self.assertFalse(self.strat.armed)
        self.assertFalse(self.eng.position.pending_order)
        self.assertFalse(self.eng.position.has_position)

    # ---- 7. 로그 태그
    def test_strategy_log_tag_and_core_keys(self):
        src = (ROOT / "engine/live_loop.py").read_text(encoding="utf-8")
        self.assertNotIn("[PULLBACK 전략]", src)
        line = next(ln for ln in src.splitlines() if "[PULLBACK-STRATEGY]" in ln)
        self.assertNotIn("{pullback_cfg}", line)

    # ---- 8(b). 실시간 확정 봉은 지표에 정확히 1번
    def test_live_confirmed_bar_enters_indicators_once(self):
        closes = [100 + i * 0.1 for i in range(32)]
        eng, df = _real_engine_case(self, closes)
        for ts, row in df.iloc[:30].iterrows():
            sp.feed_confirmed_bar(eng, sp.bar_from_row(ts, row))
        n0 = eng.pullback_indicators.n
        r = df.iloc[30]
        b = Bar(ts=df.index[30], open=r.Open, high=r.High, low=r.Low, close=r.Close, volume=1.0,
                is_closed=True, is_confirmed=True, source="REST_RECONCILED")
        self.feed(b)
        self.assertEqual(eng.pullback_indicators.n, n0 + 1)
        self.feed(b)                                   # 같은 봉 다시 → 중복 무시
        self.assertEqual(eng.pullback_indicators.n, n0 + 1)
        ref = sp.PullbackIndicators(3, 10, 5, 2, "ema")
        for x in closes[:31]:
            ref.update(x)
        self.assertEqual(eng.pullback_indicators.last_values, ref.last_values)
        self.assertEqual(self.strat.last_ts, df.index[30])


if __name__ == "__main__":
    unittest.main()
