"""
2차 T4: IncrementalPullbackStrategy.on_bar — 원본 simulate() 296-363행 평가 순서 시험.

- 손 제작 봉 배열 + 손으로 적은 지표 값(ScriptedIndicators)으로 순서 1~6 을 하나씩 본다.
- 결정 13-4 (가) 「원본과 같게」: 기동 직후 골든크로스 1차 매수는 다음 골든크로스까지 없고,
  감시 구간이면 눌림목 1회차는 바로 살 수 있다.
- 결정 13-5 (가): 잠정 봉(is_confirmed=False)은 지표·판정 상태에 넣지 않고 NOOP + 감사 TENTATIVE,
  확정값이 BACKFILL 로 오면 그 봉부터 링 버퍼 재생(주문 없음).
- 원본 대조: 원본 식을 옮긴 Python 기준(ref_simulate) 1개 + node 로 원본 HTML 을 그대로 돌린 기준 1회
  (원본 대조 일치 시험 묶음은 T10 범위 — 여기서는 1회만).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules -v
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.candle_buffer import Bar  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t3_pullback_indicators import (  # noqa: E402
    no_orders, ref_ema, ref_slope, ref_sma, series_of,
)

BASE_TS = pd.Timestamp("2026-10-01 00:00", tz="UTC")


def ts_at(i: int) -> pd.Timestamp:
    return BASE_TS + pd.Timedelta(minutes=3 * i)


def bar(i, o=100.0, h=None, l=None, c=None, *, confirmed=True, closed=True, source="REST_RECONCILED"):
    c = o if c is None else c
    h = max(o, c) if h is None else h
    l = min(o, c) if l is None else l
    return Bar(ts=ts_at(i), open=o, high=h, low=l, close=c, volume=1.0,
               is_closed=closed, is_confirmed=confirmed, source=source)


def V(t=11.0, m=10.0, p=50.0, s=1.0, slb=None):
    """손으로 적는 지표 값. 기본 = 골든(t>m)·감시 구간(s ≥ minSlope 0)·maPullback 50."""
    return {"maTrend": t, "ma200": m, "maPullback": p, "slope200": s, "slope200_lb": slb}


DEAD = dict(t=9.0, m=10.0)
NONE = dict(t=None, m=None, p=None, s=None)


class ScriptedIndicators:
    """봉마다 미리 적은 지표 값을 돌려주는 대역(update 순서대로)."""

    def __init__(self, values):
        self._values = list(values)
        self.n = 0
        self.update_count = 0
        self.state_polluted = False
        self.last_values = None

    def update(self, close):
        v = dict(self._values[self.n])
        self.n += 1
        self.update_count += 1
        self.last_values = v
        return dict(v)

    def export_state(self):
        return {"n": self.n}


BASE_PARAMS = {
    "ticker": "KRW-TEST", "interval": "minute3", "maType": "ema",
    "ma60p": 3, "ma200p": 5, "pullbackP": 2, "slopeLB": 1,
    "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": True,
    "maxSplits": 3, "maxPullbackBuys": 3, "tp": 5, "sl": 3,
    "deadcross": True, "compounding": False, "capital": 1_000_000, "fee": 0.05,
}


def make_strategy(values=None, **over):
    p = dict(BASE_PARAMS)
    p.update(over)
    st = sp.IncrementalPullbackStrategy("u1", p["ticker"], p, 3)
    if values is not None:
        st.bind(ScriptedIndicators(values), None)
    return st


def run(st, bars, position=None):
    """position=None 이면 전략의 가상 보유(원본 qty>0 과 같음)로 판정한다."""
    out = []
    for b in bars:
        a = st.on_bar(b, {}, position, 0)
        out.append((a, st.last_buy_reason if a is Action.BUY else
                    st.last_sell_reason if a is Action.SELL else None))
    return out


def actions(res):
    return [a.value for a, _ in res]


# ================================================================ 평가 순서 2·3 (매도)
class TestSellOrder(unittest.TestCase):
    def test_order_deadcross_before_tp(self):
        # 0: 데드(전환 전) 1: 골든 전환 → GOLDEN 매수 2: 체결 봉(open 100) 3: 데드 + high 200(TP 도 닿음)
        vals = [V(**DEAD), V(), V(), V(**DEAD)]
        st = make_strategy(vals)
        res = run(st, [bar(0), bar(1), bar(2, o=100, h=101, l=99, c=100), bar(3, o=100, h=200, l=99, c=100)])
        self.assertEqual(actions(res), ["HOLD", "BUY", "HOLD", "SELL"])
        self.assertEqual(res[1][1], "GOLDEN")
        self.assertEqual(res[3][1], "DEADCROSS")
        self.assertEqual(st.entry_count, 0)

    def test_tp_priority_same_bar(self):
        # 체결가 100 → TP 105, SL 97. 3번 봉 high 106·low 96 → TP
        vals = [V(**DEAD), V(), V(), V()]
        st = make_strategy(vals)
        res = run(st, [bar(0), bar(1), bar(2, o=100, h=101, l=99, c=100), bar(3, o=100, h=106, l=96, c=100)])
        self.assertEqual(actions(res), ["HOLD", "BUY", "HOLD", "SELL"])
        self.assertEqual(res[3][1], "TP")

    def test_sl_when_no_tp(self):
        vals = [V(**DEAD), V(), V(), V()]
        st = make_strategy(vals)
        res = run(st, [bar(0), bar(1), bar(2, o=100, h=101, l=99, c=100), bar(3, o=100, h=104, l=96, c=98)])
        self.assertEqual(res[3], (Action.SELL, "SL"))

    def test_tp_sl_from_signal_plus_two(self):
        # 신호 봉 1, 체결 봉 2(open 100) 는 high 110 이어도 매도 없음, 3 에서 TP
        vals = [V(**DEAD), V(), V(), V()]
        st = make_strategy(vals)
        res = run(st, [bar(0), bar(1), bar(2, o=100, h=110, l=99, c=100), bar(3, o=100, h=106, l=99, c=100)])
        self.assertEqual(actions(res), ["HOLD", "BUY", "HOLD", "SELL"])
        self.assertEqual(res[3][1], "TP")
        self.assertEqual((st.last_eval["reason"], st.last_eval["tp_price"]), ("TP", 105.0))


# ================================================================ 평가 순서 4·5 (매수)
class TestBuyOrder(unittest.TestCase):
    def test_golden_only_mode(self):
        # maxSplits=0 + buyOnGoldenCross → 골든 1회만, 눌림목(low<50<close) 0
        vals = [V(**DEAD), V(), V(), V(), V(), V()]
        st = make_strategy(vals, maxSplits=0, sl=90)
        bars = [bar(0), bar(1), bar(2, o=100, h=101, l=99, c=100),
                bar(3, o=60, h=61, l=40, c=55), bar(4, o=55, h=56, l=45, c=52), bar(5, o=52, h=60, l=40, c=55)]
        res = run(st, bars)
        buys = [r for a, r in res if a is Action.BUY]
        self.assertEqual(buys, ["GOLDEN"])
        self.assertEqual(st.pullback_count, 0)
        self.assertEqual(st.entry_count, 1)

    def test_armed_kept_when_splits_full(self):
        vals = [V(), V()]
        st = make_strategy(vals, maxSplits=2, buyOnGoldenCross=False, sl=90)
        # 회차 2/2 가 찬 보유 상태 + armed 를 되살린 뒤 low<maPullback 봉 → armed 그대로, 매수 0
        st.restore_split_state({**st.export_split_state(), "entry_count": 2, "pullback_count": 2,
                                "first_entry_ts": ts_at(-5), "armed": True, "prev_golden": True,
                                "fill_n": 2, "inv_sum": 2 / 60.0})
        res = run(st, [bar(0, o=60, h=61, l=40, c=45), bar(1, o=60, h=61, l=59, c=60)])
        self.assertEqual(actions(res), ["HOLD", "HOLD"])
        self.assertTrue(st.armed)

    def test_armed_cleared_when_pullback_capped(self):
        vals = [V()]
        st = make_strategy(vals, maxSplits=5, maxPullbackBuys=1, buyOnGoldenCross=False)
        st.restore_split_state({**st.export_split_state(), "entry_count": 1, "pullback_count": 1,
                                "first_entry_ts": ts_at(-5), "armed": True, "prev_golden": True,
                                "fill_n": 1, "inv_sum": 1 / 60.0})
        run(st, [bar(0, o=60, h=61, l=59, c=60)])
        self.assertFalse(st.armed)

    def test_armed_cleared_when_inactive(self):
        # 0: low 40 < 50, close 45 < 50 → armed  1: 골든이지만 slope<minSlope(감시 밖) → armed 해제
        # 2: 감시 구간·close 60 > 50 이지만 armed 아님 → 매수 0
        vals = [V(), V(s=-1.0), V()]
        st = make_strategy(vals, buyOnGoldenCross=False)
        run(st, [bar(0, o=60, h=61, l=40, c=45)])
        self.assertTrue(st.armed)
        res = run(st, [bar(1, o=45, h=46, l=44, c=45), bar(2, o=55, h=61, l=55, c=60)])
        self.assertFalse(st.armed)
        self.assertEqual(actions(res), ["HOLD", "HOLD"])

    def test_inactive_by_slope_drop(self):
        # slopeDrop 2: 과거 slope 5 → 지금 1 (둔화 4 > 2) → 감시 밖. 과거 slope 없으면 둔화 조건 통과.
        st = make_strategy([V(s=1.0, slb=5.0), V(s=1.0, slb=None)], buyOnGoldenCross=False, slopeDrop=2)
        res = run(st, [bar(0, o=60, h=61, l=40, c=55), bar(1, o=60, h=61, l=40, c=55)])
        self.assertEqual(actions(res), ["HOLD", "BUY"])

    def test_same_bar_arm_and_buy(self):
        st = make_strategy([V()], buyOnGoldenCross=False)
        res = run(st, [bar(0, o=60, h=61, l=40, c=55)])
        self.assertEqual(res, [(Action.BUY, "PULLBACK")])
        self.assertFalse(st.armed)
        self.assertEqual((st.entry_count, st.pullback_count), (1, 1))

    def test_second_split_while_holding(self):
        # 1회차(눌림) 체결 뒤 다시 눌림 → 2회차. TP/SL 은 닿지 않게(체결가 60 → TP 63, SL 58.2)
        vals = [V(), V(), V()]
        st = make_strategy(vals, buyOnGoldenCross=False, sl=50)
        res = run(st, [bar(0, o=60, h=61, l=40, c=55), bar(1, o=60, h=61, l=45, c=46),
                       bar(2, o=46, h=56, l=46, c=55)])
        self.assertEqual(actions(res), ["BUY", "HOLD", "BUY"])
        self.assertEqual((st.entry_count, st.pullback_count), (2, 2))
        self.assertEqual(st.first_entry_ts, ts_at(1))


# ================================================================ 기동 직후 (결정 13-4 가)
class TestStartup(unittest.TestCase):
    def test_no_golden_buy_right_after_start(self):
        # 워밍업 재생(replay_bar): 0 지표 없음, 1 처음 골든(원본이면 가상 GOLDEN 신호 — 주문 없음)
        # 기동 뒤 실시간 2~5: 계속 골든·감시 구간, 눌림 없음(low > 50), 실제 보유 없음 → GOLDEN 매수 0
        vals = [V(**NONE), V(), V(), V(), V(), V()]
        st = make_strategy(vals)
        flat = SimpleNamespace(has_position=False, avg_price=None)
        with no_orders():
            for i in range(2):
                b = bar(i, o=100, h=101, l=99, c=100)
                st.replay_bar(b, st.indicators.update(b.close))
            res = run(st, [bar(i, o=100, h=101, l=99, c=100) for i in range(2, 6)], position=flat)
        self.assertEqual(actions(res), ["HOLD"] * 4)
        self.assertNotIn("GOLDEN", [r for _, r in res])

    def test_pullback_first_buy_without_golden(self):
        # 처음부터 골든·감시 구간(골든 전환 없음). 2: low 40 < 50, close 45 → armed  3: close 55 > 50 → PULLBACK 1회차
        vals = [V(), V(), V(), V(), V()]
        st = make_strategy(vals, buyOnGoldenCross=False)
        st.restore_split_state({**st.export_split_state(), "prev_golden": True})  # 워밍업으로 이미 골든
        flat = SimpleNamespace(has_position=False, avg_price=None)
        bars = [bar(0, o=60, h=61, l=59, c=60), bar(1, o=60, h=61, l=59, c=60),
                bar(2, o=60, h=61, l=40, c=45), bar(3, o=45, h=56, l=45, c=55),
                bar(4, o=55, h=56, l=54, c=55)]
        res = run(st, bars[:4], position=flat)
        self.assertEqual(actions(res), ["HOLD", "HOLD", "HOLD", "BUY"])
        self.assertEqual(res[3][1], "PULLBACK")
        self.assertEqual(st.entry_count, 1)
        self.assertEqual(st.last_eval.get("split_round"), 1)
        # 원본 식 기준과 같음(같은 지표 값으로 ref_simulate)
        ref = ref_simulate_values(bars, vals, st.cfg)
        self.assertEqual(ref["buys"], [(3, "PULLBACK")])

    def test_virtual_trade_from_warmup_dropped_when_flat(self):
        # 워밍업 재생이 가상 1회차를 남겨도 실제 보유가 없으면 회차를 0 으로 맞춘다(armed·prev_golden 유지)
        vals = [V(**DEAD), V(), V()]
        st = make_strategy(vals)
        for i in range(2):
            b = bar(i)
            st.replay_bar(b, st.indicators.update(b.close))
        self.assertEqual(st.entry_count, 1)
        flat = SimpleNamespace(has_position=False, avg_price=None)
        st.on_bar(bar(2, o=100, h=101, l=99, c=100), {}, flat, 0)
        self.assertEqual(st.entry_count, 0)
        self.assertTrue(st.prev_golden)


# ================================================================ 확정 봉만 · 잠정 봉 (결정 13-5 가)
class TestConfirmedOnly(unittest.TestCase):
    def test_unconfirmed_bar_noop(self):
        st = make_strategy([V()], buyOnGoldenCross=False)
        before = st.export_split_state()
        # 형성 중 봉(on_new_bar 경로: WS, is_confirmed=False) · 닫히지 않은 봉 모두 NOOP
        a1 = st.on_bar(bar(0, o=60, h=61, l=40, c=55, confirmed=False, source="WS"), {}, None, 0)
        a2 = st.on_bar(bar(0, o=60, h=61, l=40, c=55, closed=False), {}, None, 0)
        self.assertEqual((a1.value, a2.value), ("NOOP", "NOOP"))
        self.assertEqual(st.indicators.n, 0)
        self.assertEqual(st.export_split_state(), before)

    def test_tentative_bar_not_in_indicators(self):
        st = make_strategy()
        for i in range(8):
            st.on_bar(bar(i, o=100 + i, h=101 + i, l=99 + i, c=100 + i), {}, None, 0)
        ind_before = st.indicators.export_state()
        split_before = st.export_split_state()
        ring_before = len(st.ring)
        a = st.on_bar(bar(8, o=50, h=50, l=50, c=50, confirmed=False, source="WO2_OPTION_C_TENTATIVE:WS"),
                      {}, None, 0)
        self.assertEqual(a.value, "NOOP")
        self.assertEqual(st.indicators.export_state(), ind_before)
        self.assertEqual(st.export_split_state(), split_before)
        self.assertEqual(len(st.ring), ring_before)
        self.assertEqual(st.last_eval["failed_keys"], ["TENTATIVE"])

    def test_old_or_duplicate_bar_noop(self):
        st = make_strategy()
        st.on_bar(bar(0), {}, None, 0)
        n = st.indicators.n
        self.assertEqual(st.on_bar(bar(0), {}, None, 0).value, "NOOP")
        self.assertEqual(st.indicators.n, n)

    def test_confirmed_after_tentative_replays(self):
        closes = [100, 101, 103, 102, 104, 106, 105, 107, 109, 108]
        lows = [c - 3 for c in closes]
        highs = [c + 1 for c in closes]

        def bars_upto(k):
            return [bar(i, o=closes[i], h=highs[i], l=lows[i], c=closes[i]) for i in range(k)]

        st = make_strategy()
        eng = SimpleNamespace(pullback_indicators=st.indicators, pullback_ring=st.ring, strategy=st,
                              user_id="u1", ticker="KRW-TEST")
        with no_orders():
            for b in bars_upto(9):
                st.on_bar(b, {}, None, 0)
            tentative = bar(9, o=111, h=111, l=111, c=111, confirmed=False, source="WO2_OPTION_C_TENTATIVE:WS")
            self.assertEqual(st.on_bar(tentative, {}, None, 0).value, "NOOP")
            df = series_of(closes, [ts_at(i) for i in range(10)])
            df["High"], df["Low"] = highs, lows
            last_action = st.last_action
            res = sp.pullback_backfill(eng, first_ts=ts_at(9), series=df, until_ts=ts_at(9),
                                       changed_ts=[ts_at(9)], audit_fn=lambda *a: None)
        self.assertEqual((res["restored"], res["replayed"], res["reason"]), (True, 1, ""))
        self.assertIs(st.last_action, last_action)  # 재생은 Action 을 내지 않는다
        ref = make_strategy()
        for b in bars_upto(9):
            ref.on_bar(b, {}, None, 0)
        b9 = bar(9, o=closes[9], h=highs[9], l=lows[9], c=closes[9])
        ref.replay_bar(b9, ref.indicators.update(b9.close))
        self.assertEqual(st.indicators.export_state(), ref.indicators.export_state())
        self.assertEqual({k: v for k, v in st.export_split_state().items()},
                         {k: v for k, v in ref.export_split_state().items()})


# ================================================================ 훅 · 재생 = 주문 없음
class TestHooks(unittest.TestCase):
    def test_replay_bar_returns_no_action_and_updates_state(self):
        st = make_strategy([V()], buyOnGoldenCross=False)
        b = bar(0, o=60, h=61, l=40, c=55)
        with no_orders():
            r = st.replay_bar(b, st.indicators.update(b.close))
        self.assertIsNone(r)
        self.assertEqual(st.entry_count, 1)  # 가상 회차
        self.assertEqual(st.last_eval.get("mode"), "replay")
        self.assertEqual(st.last_eval.get("replay_signal"), "BUY:PULLBACK")

    def test_ring_restores_split_state(self):
        st = make_strategy()
        closes = [100 + ((i * 7) % 11) - 5 for i in range(30)]
        for i, c in enumerate(closes):
            st.on_bar(bar(i, o=c, h=c + 2, l=c - 6, c=c), {}, None, 0)
        snap = st.ring.snapshot_before(ts_at(25))
        st.ring.restore(snap, st.indicators, st)
        # 비교 기준: 0~24봉만 새로 넣은 전략(링 기록을 다시 읽는 순환 비교가 아님)
        ref = make_strategy()
        for i, c in enumerate(closes[:25]):
            ref.on_bar(bar(i, o=c, h=c + 2, l=c - 6, c=c), {}, None, 0)
        self.assertEqual(st.export_split_state(), ref.export_split_state())
        self.assertEqual(st.indicators.export_state(), ref.indicators.export_state())

    def test_reload_conditions_and_interval(self):
        st = make_strategy()
        self.assertEqual(st.reload_conditions({"a": 1}, {"b": 2}), {})
        st.set_interval_min(5)
        self.assertEqual(st.interval_min, 5)

    def test_live_position_avg_used_for_tp(self):
        # 실보유 평단 200 → TP 210. 가상 체결가(open 100)가 아니라 실제 평단으로 본다.
        vals = [V(**DEAD), V(), V(), V()]
        st = make_strategy(vals)
        pos = SimpleNamespace(has_position=False, avg_price=None)
        st.on_bar(bar(0), {}, pos, 0)
        self.assertIs(st.on_bar(bar(1), {}, pos, 0), Action.BUY)
        pos.has_position, pos.avg_price = True, 200.0
        st.on_bar(bar(2, o=100, h=101, l=99, c=100), {}, pos, 0)
        a = st.on_bar(bar(3, o=205, h=206, l=199, c=205), {}, pos, 0)
        self.assertIs(a, Action.HOLD)  # 가상 평단 100 이면 TP 였을 봉


# ================================================================ 검수 반영 (A~E)
def follow_buys(st, pos, bars, *, fill_avg=None, keep_after_sell=False):
    """실보유 대역: BUY 뒤 보유로 바꾸고(평단 fill_avg 또는 신호 봉 종가), SELL 뒤 keep_after_sell 이면 보유 유지(매도 거절)."""
    out = []
    for b in bars:
        a = st.on_bar(b, {}, pos, 0)
        out.append((a.value, st.last_buy_reason if a is Action.BUY else
                    st.last_sell_reason if a is Action.SELL else None))
        if a is Action.BUY and not pos.has_position:
            pos.has_position, pos.avg_price = True, (fill_avg or b.close)
        elif a is Action.SELL and not keep_after_sell:
            pos.has_position, pos.avg_price = False, None
    return out


class TestReviewFixes(unittest.TestCase):
    def test_sell_reject_blocks_further_buys(self):
        # A. maxSplits=2, 2회 보유 중 TP 매도 거절 → 실보유 + 판정 회차 0 → 눌림목 매수 0
        st = make_strategy([V()] * 7, maxSplits=2, buyOnGoldenCross=False, sl=90)
        pos = SimpleNamespace(has_position=False, avg_price=None)
        bars = [bar(0, o=60, h=61, l=40, c=55), bar(1, o=60, h=61, l=45, c=46),
                bar(2, o=46, h=56, l=46, c=55), bar(3, o=55, h=70, l=54, c=60),
                bar(4, o=50, h=52, l=40, c=45), bar(5, o=45, h=56, l=45, c=55), bar(6, o=55, h=56, l=40, c=55)]
        res = follow_buys(st, pos, bars, keep_after_sell=True)
        self.assertEqual(res[:4], [("BUY", "PULLBACK"), ("HOLD", None), ("BUY", "PULLBACK"), ("SELL", "TP")])
        self.assertEqual([a for a, _ in res[4:]], ["HOLD", "HOLD", "HOLD"])
        self.assertIn("POS_DESYNC", st.last_eval["failed_keys"])

    def test_app_buy_holding_round0_no_buy(self):
        # A. 앱 매수 보유(판정 회차 0) → 골든 전환·눌림 봉이어도 매수 0
        st = make_strategy([V(**NONE), V(), V()], sl=90)
        pos = SimpleNamespace(has_position=True, avg_price=100.0)
        res = follow_buys(st, pos, [bar(0, o=60, h=61, l=59, c=60), bar(1, o=60, h=61, l=40, c=55),
                                    bar(2, o=60, h=61, l=40, c=55)])
        self.assertEqual([a for a, _ in res], ["HOLD", "HOLD", "HOLD"])
        self.assertIn("POS_DESYNC", st.last_eval["failed_keys"])

    def test_app_sell_clears_armed_no_immediate_rebuy(self):
        # B. 실거래 armed 상태에서 앱 매도 → 다음 봉 정리 때 armed 해제 → close>maPullback 이어도 재매수 0
        st = make_strategy([V()] * 3, buyOnGoldenCross=False, sl=90)
        pos = SimpleNamespace(has_position=False, avg_price=None)
        follow_buys(st, pos, [bar(0, o=60, h=61, l=40, c=55), bar(1, o=60, h=61, l=45, c=46)])
        self.assertTrue(st.armed)
        pos.has_position, pos.avg_price = False, None  # 앱 매도
        a = st.on_bar(bar(2, o=52, h=56, l=51, c=55), {}, pos, 0)
        self.assertEqual(a.value, "HOLD")
        self.assertEqual((st.entry_count, st.armed), (0, False))

    def test_warmup_virtual_trade_keeps_armed_then_pullback_first_buy(self):
        # B. 워밍업 재생이 만든 가상 거래 정리 때는 armed 유지 → 켠 직후 눌림목 1회차(결정 13-4 가)
        st = make_strategy([V()] * 3, buyOnGoldenCross=False, sl=90)
        for b in (bar(0, o=60, h=61, l=40, c=55), bar(1, o=60, h=61, l=45, c=46)):
            st.replay_bar(b, st.indicators.update(b.close))
        self.assertEqual((st.entry_count, st.armed), (1, True))
        flat = SimpleNamespace(has_position=False, avg_price=None)
        a = st.on_bar(bar(2, o=52, h=56, l=51, c=55), {}, flat, 0)
        self.assertEqual((a.value, st.last_buy_reason, st.last_eval["split_round"]), ("BUY", "PULLBACK", 1))

    def test_pending_fill_keeps_round_when_position_lags(self):
        # C. 신호 봉 다음 봉(체결 대기)에서 아직 has_position=False → 회차 유지, 그 다음 봉에도 없으면 정리
        st = make_strategy([V(**DEAD), V(), V(), V()], sl=90)
        flat = SimpleNamespace(has_position=False, avg_price=None)
        self.assertEqual(st.on_bar(bar(0), {}, flat, 0).value, "HOLD")
        self.assertEqual(st.on_bar(bar(1), {}, flat, 0).value, "BUY")
        st.on_bar(bar(2, o=60, h=61, l=59, c=60), {}, flat, 0)
        self.assertEqual(st.entry_count, 1)
        st.on_bar(bar(3, o=60, h=61, l=59, c=60), {}, flat, 0)
        self.assertEqual(st.entry_count, 0)

    def test_pending_fill_defer_blocks_buy_at_most_one_bar(self):
        # C 보강: 미룸 봉에 low<pm<close 여도 매수 0(PENDING_FILL), 다음 봉에도 실보유 없으면 정리 — 미룸은 최대 1봉
        st = make_strategy([V(**DEAD)] + [V()] * 6, sl=90)
        flat = SimpleNamespace(has_position=False, avg_price=None)
        st.on_bar(bar(0), {}, flat, 0)
        self.assertEqual(st.on_bar(bar(1), {}, flat, 0).value, "BUY")
        a = st.on_bar(bar(2, o=60, h=61, l=40, c=55), {}, flat, 0)
        self.assertEqual(a.value, "HOLD")
        self.assertIn("PENDING_FILL", st.last_eval["failed_keys"])
        self.assertEqual((st.entry_count, st.pending_fill), (1, False))
        st.on_bar(bar(3, o=60, h=61, l=59, c=60), {}, flat, 0)
        self.assertEqual(st.entry_count, 0)
        # 이후 실보유 없이 매수 신호가 이어져도 회차는 1 을 넘지 않는다(미룸이 반복되지 않음)
        buys = 0
        for i in range(4, 7):
            if st.on_bar(bar(i, o=60, h=61, l=40, c=55), {}, flat, 0) is Action.BUY:
                buys += 1
            self.assertLessEqual(st.entry_count, 1)
        self.assertLessEqual(buys, 2)

    def test_exception_mid_bar_no_double_feed(self):
        # D. on_bar 중 예외 → 같은 봉 재투입은 NOOP(지표 n+1 만, 링 ts 중복 없음), 판정 상태 되돌림, 오염 표식
        st = make_strategy()
        for i in range(5):
            st.on_bar(bar(i, o=100 + i, c=100 + i), {}, None, 0)
        n0 = st.indicators.n
        before = st.export_split_state()
        from unittest.mock import patch as _patch
        with _patch.object(st, "_step", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                st.on_bar(bar(5, o=105, c=105), {}, None, 0)
        self.assertEqual(st.on_bar(bar(5, o=105, c=105), {}, None, 0).value, "NOOP")
        self.assertEqual(st.indicators.n, n0 + 1)
        ring_ts = [s.bar_ts for s in st.ring._q]
        self.assertEqual(len(ring_ts), len(set(ring_ts)))
        self.assertEqual(st.export_split_state(), {**before, "last_ts": ts_at(5)})
        self.assertTrue(st.indicators.state_polluted)
        # 오염 상태에서 매수 조건 봉 → NOOP (대역 지표로 매수 조건을 만든다)
        st2 = make_strategy([V()], buyOnGoldenCross=False)
        st2.indicators.state_polluted = True
        a = st2.on_bar(bar(0, o=60, h=61, l=40, c=55), {}, None, 0)
        self.assertEqual(a.value, "NOOP")
        self.assertIn("STATE_POLLUTED", st2.last_eval["failed_keys"])
        self.assertEqual(st2.entry_count, 0)

    def test_restore_first_entry_ts_from_kst_string(self):
        # E. T6 저장 형식(KST ISO 문자열) → tz 있는 Timestamp. 시간대 없는 문자열은 KST 로 본다(Issue #2).
        st = make_strategy()
        for s in ("2026-10-01T09:06:00+09:00", "2026-10-01 09:06:00"):
            st.restore_split_state({**st.export_split_state(), "first_entry_ts": s, "last_ts": s})
            self.assertIsInstance(st.first_entry_ts, pd.Timestamp)
            self.assertIsNotNone(st.first_entry_ts.tzinfo)
            self.assertEqual(st.first_entry_ts, ts_at(2))
            self.assertEqual(st.last_ts, ts_at(2))
            self.assertTrue(ts_at(3) > st.first_entry_ts)


# ================================================================ 원본 대조 (Python 기준 · node 1회)
def ref_simulate_values(bars, vals, cfg):
    """원본 simulate() 296-363 을 신호만 옮긴 기준. vals[i] 는 봉 i 의 지표 값."""
    golden_only = cfg["buyOnGoldenCross"] and cfg["maxSplits"] == 0
    eff = 1 if golden_only else cfg["maxSplits"]
    buys, sells = [], []
    entry = pb = 0
    first_t = None
    inv = 0.0
    nfill = 0
    armed = prev_golden = False
    pending = False
    for i, b in enumerate(bars):
        v = vals[i]
        if pending:
            nfill += 1
            inv += 1.0 / b.open
            if first_t is None:
                first_t = b.ts
            pending = False
        t, m, s, slb, p = v["maTrend"], v["ma200"], v["slope200"], v["slope200_lb"], v["maPullback"]
        active = t is not None and m is not None and s is not None and t > m and s >= cfg["minSlope"]
        if active and cfg["slopeDrop"] > 0 and slb is not None and (slb - s) > cfg["slopeDrop"]:
            active = False
        was = prev_golden
        golden = t is not None and m is not None and t > m
        prev_golden = golden
        just = golden and not was
        if entry > 0 and cfg["deadcross"] and t is not None and m is not None and not (t > m):
            sells.append((i, "DEADCROSS"))
            entry = pb = nfill = 0; inv = 0.0; first_t = None; armed = False
            continue
        if entry > 0 and first_t is not None and b.ts > first_t:
            avg = nfill / inv
            if b.high >= avg * (1 + cfg["tp"] / 100):
                sells.append((i, "TP")); entry = pb = nfill = 0; inv = 0.0; first_t = None; armed = False
                continue
            if b.low <= avg * (1 - cfg["sl"] / 100):
                sells.append((i, "SL")); entry = pb = nfill = 0; inv = 0.0; first_t = None; armed = False
                continue
        last = i + 1 >= len(bars)
        if cfg["buyOnGoldenCross"] and just and entry == 0 and active and entry < eff and not last:
            buys.append((i, "GOLDEN")); entry += 1; pending = True; armed = False
            continue
        capped = pb >= cfg["maxPullbackBuys"]
        if not golden_only and not capped and active and entry < eff:
            if p is not None and b.low < p:
                armed = True
            if armed and p is not None and b.close > p and not last:
                buys.append((i, "PULLBACK")); entry += 1; pb += 1; pending = True; armed = False
        elif not active or golden_only or capped:
            armed = False
    return {"buys": buys, "sells": sells}


def rand_bars(n, seed=11):
    rnd = random.Random(seed)
    c = 1000.0
    out = []
    for i in range(n):
        o = c
        c = max(1.0, c * (1 + rnd.uniform(-0.012, 0.0125)))
        h = max(o, c) * (1 + rnd.uniform(0, 0.006))
        l = min(o, c) * (1 - rnd.uniform(0, 0.006))
        out.append(bar(i, o=round(o, 4), h=round(h, 4), l=round(l, 4), c=round(c, 4)))
    return out


REF_CFG = dict(BASE_PARAMS, ma60p=20, ma200p=60, pullbackP=10, slopeLB=5, minSlope=0, slopeDrop=0.3,
               maxSplits=4, maxPullbackBuys=3, tp=1.0, sl=1.5)


def run_virtual(cfg, bars):
    st = sp.IncrementalPullbackStrategy("u1", cfg["ticker"], cfg, 3)
    buys, sells, vals = [], [], []
    for i, b in enumerate(bars):
        a = st.on_bar(b, {}, None, 0)
        vals.append(dict(st.indicators.last_values))
        if a is Action.BUY:
            buys.append((i, st.last_buy_reason))
        elif a is Action.SELL:
            sells.append((i, st.last_sell_reason))
    return buys, sells, vals


class TestReference(unittest.TestCase):
    def test_virtual_mode_matches_reference_port(self):
        for mt in ("ema", "sma"):
            for gc in (True, False):
                cfg = dict(REF_CFG, maType=mt, buyOnGoldenCross=gc)
                bars = rand_bars(1500, seed=3 if gc else 5)
                buys, sells, vals = run_virtual(cfg, bars)
                ref = ref_simulate_values(bars, vals, cfg)
                buys = [x for x in buys if x[0] + 1 < len(bars)]  # 원본은 마지막 봉 신호를 체결하지 않음
                self.assertGreater(len(ref["buys"]), 5, (mt, gc))
                self.assertGreater(len(ref["sells"]), 2, (mt, gc))
                self.assertEqual(buys, ref["buys"], (mt, gc))
                self.assertEqual(sells, ref["sells"], (mt, gc))

    @unittest.skipUnless(shutil.which("node"), "node 없음")
    def test_virtual_mode_matches_original_html_once(self):
        cfg = dict(REF_CFG, maType="ema", buyOnGoldenCross=True)
        bars = rand_bars(1500, seed=3)
        buys, sells, _ = run_virtual(cfg, bars)
        ms = [int(b.ts.value // 1_000_000) for b in bars]
        js_cfg = {k: cfg[k] for k in ("maType", "ma60p", "ma200p", "pullbackP", "slopeLB", "minSlope",
                                      "slopeDrop", "buyOnGoldenCross", "maxSplits", "maxPullbackBuys",
                                      "tp", "sl", "capital", "fee")}
        js_cfg["deadcross"] = "yes" if cfg["deadcross"] else "no"
        js_cfg["compounding"] = "no"
        with tempfile.TemporaryDirectory() as d:
            fx, cf = Path(d) / "fx.json", Path(d) / "cfg.json"
            fx.write_text(json.dumps({"bars": [{"t": ms[i], "o": b.open, "h": b.high, "l": b.low, "c": b.close}
                                               for i, b in enumerate(bars)]}))
            cf.write_text(json.dumps(js_cfg))
            out = subprocess.run(["node", str(ROOT / "tests/v2/js/pullback_reference.mjs"), str(fx), str(cf)],
                                 capture_output=True, text=True, timeout=60, check=True)
        ref = json.loads(out.stdout)
        idx = {t: i for i, t in enumerate(ms)}
        ref_buys = [(idx[x["signal_bar_t"]], x["trigger"]) for x in ref["buys"]]
        ref_sells = [(idx[x["bar_t"]], x["type"]) for x in ref["sells"]]
        buys = [x for x in buys if x[0] + 1 < len(bars)]
        self.assertGreater(len(ref_buys), 5)
        self.assertGreater(len(ref_sells), 2)
        self.assertIn("PULLBACK", {x[1] for x in ref_buys})
        self.assertEqual(buys, ref_buys)
        self.assertEqual(sells, ref_sells)


if __name__ == "__main__":
    unittest.main()
