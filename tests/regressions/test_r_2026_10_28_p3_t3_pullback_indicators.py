"""
2차 T3: PULLBACK 증분 지표 상태 + 링 버퍼 + 워밍업·BACKFILL 분기 시험.

- 지표는 원본 백테스터 computeSMA(186-195)·computeEMA(199-212)·computeSlope(218-227)를
  같은 연산 순서로 옮긴 기준 함수와 봉마다 비교한다.
- 링 버퍼는 되살린 뒤 같은 봉을 다시 넣으면 처음과 같은 상태가 되는지 본다(ema·sma 둘 다).
- live_loop 는 PULLBACK 이 [BOOT] 직후 거부되므로(T1), 분기를 작은 함수로 빼 직접 부르고,
  run_live_loop 본문은 소스(ast)로 분기 위치·EMA 경로 불변을 확인한다.
- 주문 차단은 실제 주문 함수(UpbitTrader.buy_market·buy_limit·sell_market)를 막아 확인한다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t3_pullback_indicators -v
"""
from __future__ import annotations

import ast
import contextlib
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import strategy_pullback as sp  # noqa: E402
from core.candle_validator import CandleValidator  # noqa: E402
from core.strategy_pullback import PullbackIndicators, PullbackSnapshotRing  # noqa: E402

LIVE_LOOP = ROOT / "engine" / "live_loop.py"
PULLBACK_SRC = ROOT / "core" / "strategy_pullback.py"
MA_TYPES = ("ema", "sma")


# ---------------------------------------------------------------- 원본 식 기준 함수(JS 그대로)
def ref_sma(closes, period):
    out = [None] * len(closes)
    s = 0.0
    for i in range(len(closes)):
        s += closes[i]
        if i >= period:
            s -= closes[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def ref_ema(closes, period):
    out = [None] * len(closes)
    if len(closes) < period:
        return out
    k = 2 / (period + 1)
    s = 0.0
    for i in range(period):
        s += closes[i]
    prev = s / period
    out[period - 1] = prev
    for i in range(period, len(closes)):
        prev = closes[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def ref_slope(ma, lookback):
    out = [None] * len(ma)
    for i in range(len(ma)):
        j = i - lookback
        if j >= 0 and ma[j] is not None and ma[i] is not None and ma[j] != 0:
            out[i] = (ma[i] - ma[j]) / abs(ma[j]) * 100
    return out


def rand_closes(n, seed=7):
    rnd = random.Random(seed)
    c = 1000.0
    out = []
    for _ in range(n):
        c = max(1.0, c * (1 + rnd.uniform(-0.01, 0.0105)))
        out.append(round(c, 2))
    return out


CFG = dict(ma60p=60, ma200p=200, pullbackP=20, slopeLB=5)


def make_ind(maType="ema", **over):
    c = dict(CFG)
    c.update(over)
    return PullbackIndicators(c["ma60p"], c["ma200p"], c["pullbackP"], c["slopeLB"], maType)


def ts_list(n, start="2026-10-01 00:00"):
    return list(pd.date_range(start, periods=n, freq="3min", tz="UTC"))


def series_of(closes, tss):
    return pd.DataFrame(
        {"Open": closes, "High": [c * 1.01 for c in closes], "Low": [c * 0.99 for c in closes],
         "Close": closes, "Volume": [1.0] * len(closes)},
        index=pd.DatetimeIndex(tss),
    )


class StubSplitStrategy:
    """T4 전 분할 판정 상태 자리 시험용: armed·prev_golden 을 지표로만 갱신(주문 없음)."""

    def __init__(self):
        self.armed = False
        self.prev_golden = False
        self.virtual_round = 0

    def replay_bar(self, bar, values):
        mp = values.get("maPullback")
        if mp is not None:
            if bar.low < mp:
                self.armed = True
            elif self.armed and bar.close > mp:
                self.armed = False
                self.virtual_round += 1
        t, m = values.get("maTrend"), values.get("ma200")
        if t is not None and m is not None:
            self.prev_golden = t > m

    def export_split_state(self):
        return {"armed": self.armed, "prev_golden": self.prev_golden, "virtual_round": self.virtual_round}

    def restore_split_state(self, d):
        self.armed = d["armed"]
        self.prev_golden = d["prev_golden"]
        self.virtual_round = d["virtual_round"]


def make_engine(strategy=None, maType="ema"):
    return SimpleNamespace(
        pullback_indicators=make_ind(maType),
        pullback_ring=PullbackSnapshotRing(sp.RING_CAPACITY),
        strategy=strategy,
        user_id="tuser", ticker="KRW-JTO", interval_sec=180, bar_count=0,
        position=SimpleNamespace(has_position=False),
    )


def feed_all(eng, df):
    for ts, row in df.iterrows():
        sp.feed_confirmed_bar(eng, sp.bar_from_row(ts, row))


def full_state(eng):
    return (eng.pullback_indicators.export_state(),
            eng.strategy.export_split_state() if eng.strategy is not None else None,
            eng.pullback_indicators.last_values)


@contextlib.contextmanager
def no_orders():
    """실제 주문 함수를 막는다. 불리면 AssertionError."""
    from core.trader import UpbitTrader
    boom = AssertionError("주문 함수가 불렸다")
    with patch.object(UpbitTrader, "buy_market", side_effect=boom) as b1, \
            patch.object(UpbitTrader, "buy_limit", side_effect=boom) as b2, \
            patch.object(UpbitTrader, "sell_market", side_effect=boom) as s1:
        yield (b1, b2, s1)
    for m in (b1, b2, s1):
        assert m.call_count == 0


# ================================================================ 지표
class TestIndicators(unittest.TestCase):
    def _compare(self, maType, ref):
        closes = rand_closes(1200)
        ind = make_ind(maType)
        got_t, got_m, got_p, got_s = [], [], [], []
        for c in closes:
            v = ind.update(c)
            got_t.append(v["maTrend"])
            got_m.append(v["ma200"])
            got_p.append(v["maPullback"])
            got_s.append(v["slope200"])
        exp_m = ref(closes, 200)
        for got, exp in ((got_t, ref(closes, 60)), (got_m, exp_m), (got_p, ref(closes, 20)),
                         (got_s, ref_slope(exp_m, 5))):
            for i, (g, e) in enumerate(zip(got, exp)):
                if e is None:
                    self.assertIsNone(g, f"i={i}")
                else:
                    self.assertTrue(g == e or abs(g - e) <= 1e-12, f"i={i} got={g} exp={e}")
        self.assertEqual(ind.update_count, 1200)

    def test_ema_matches_compute_ema(self):
        self._compare("ema", ref_ema)

    def test_sma_matches_compute_sma(self):
        self._compare("sma", ref_sma)

    def test_slope_none_when_zero_or_missing(self):
        ind = PullbackIndicators(1, 1, 1, 3, "sma")
        for c in (5.0, 6.0, 7.0):
            self.assertIsNone(ind.update(c)["slope200"])
        self.assertIsNotNone(ind.update(8.0)["slope200"])
        ind = PullbackIndicators(1, 1, 1, 2, "sma")
        ind.update(0.0)
        ind.update(1.0)
        self.assertIsNone(ind.update(2.0)["slope200"])
        ind = PullbackIndicators(1, 1, 1, 1, "sma")
        ind.update(1.0)
        v = ind.update(2.0)
        self.assertIsNotNone(v["slope200"])
        self.assertIsNone(v["slope200_lb"])
        self.assertEqual(ind.update(3.0)["slope200_lb"], v["slope200"])

    def test_no_full_recompute_function(self):
        src = PULLBACK_SRC.read_text(encoding="utf-8")
        for bad in ("ewm", "rolling", "talib"):
            self.assertNotIn(bad, src, bad)


# ================================================================ 링 버퍼
class TestRing(unittest.TestCase):
    def test_ring_capacity_401_and_restore(self):
        self.assertEqual(sp.RING_CAPACITY, 401)
        for maType in MA_TYPES:
            with self.subTest(maType=maType):
                eng = make_engine(StubSplitStrategy(), maType)
                df = series_of(rand_closes(450, seed=3), ts_list(450))
                feed_all(eng, df)
                self.assertEqual(len(eng.pullback_ring), 401)
                before = full_state(eng)
                snap = eng.pullback_ring.snapshot_before(df.index[-30])
                self.assertEqual(snap.bar_ts, df.index[-31])
                eng.pullback_ring.restore(snap, eng.pullback_indicators, eng.strategy)
                self.assertEqual(len(eng.pullback_ring), 401 - 30)
                self.assertEqual(eng.pullback_indicators.n, 450 - 30)
                self.assertNotEqual(eng.pullback_indicators.export_state(), before[0])
                feed_all(eng, df.iloc[-30:])
                self.assertEqual(full_state(eng), before)
                self.assertEqual(len(eng.pullback_ring), 401)

    def test_ring_front_boundary(self):
        """링 401칸: 400봉 되돌림까지 일치(맨 앞 기록이 기준), 401봉은 out_of_ring.
        실제 조회(RECONCILE_LOOKBACK_BARS=400, closed_ts 제외)에서 되돌림은 최대 399봉."""
        for maType in MA_TYPES:
            for k in (399, 400):
                with self.subTest(maType=maType, k=k), no_orders():
                    eng = make_engine(StubSplitStrategy(), maType)
                    df = series_of(rand_closes(900, seed=13), ts_list(900))
                    feed_all(eng, df)
                    before = full_state(eng)
                    res = sp.pullback_backfill(eng, first_ts=df.index[-k], series=df, until_ts=df.index[-1],
                                               changed_ts=[], audit_fn=MagicMock())
                    self.assertTrue(res["restored"])
                    self.assertEqual(res["replayed"], k)
                    self.assertEqual(full_state(eng), before)
            with self.subTest(maType=maType, k=401):
                eng = make_engine(StubSplitStrategy(), maType)
                df = series_of(rand_closes(900, seed=13), ts_list(900))
                feed_all(eng, df)
                res = sp.pullback_backfill(eng, first_ts=df.index[-401], series=df, until_ts=df.index[-1],
                                           changed_ts=[], audit_fn=MagicMock())
                self.assertEqual(res["reason"], "out_of_ring")

    def test_feed_atomic_on_replay_error(self):
        class Boom(StubSplitStrategy):
            def replay_bar(self, bar, values):
                raise RuntimeError("boom")

        eng = make_engine(StubSplitStrategy())
        df = series_of(rand_closes(260, seed=21), ts_list(260))
        feed_all(eng, df.iloc[:-1])
        eng.strategy = Boom()
        with self.assertRaises(RuntimeError):
            sp.feed_confirmed_bar(eng, sp.bar_from_row(df.index[-1], df.iloc[-1]))
        self.assertTrue(eng.pullback_indicators.state_polluted)
        # 지표 n 과 링 마지막 기록 n 이 같음(어긋나지 않음) → 되살리기 가능
        self.assertEqual(eng.pullback_ring._q[-1].ind_state["n"], eng.pullback_indicators.n)
        snap = eng.pullback_ring.snapshot_before(df.index[-3])
        eng.pullback_ring.restore(snap, eng.pullback_indicators, None)
        self.assertEqual(eng.pullback_indicators.n, 257)

    def test_restore_rejected_keeps_state(self):
        eng = make_engine()
        df = series_of(rand_closes(260, seed=22), ts_list(260))
        feed_all(eng, df)
        before = full_state(eng)
        # ① 링과 n 이 어긋남(링 밖에서 지표만 1봉 더 들어감) → restore_rejected, 오염 아님, 상태 불변
        eng.pullback_indicators.update(1234.0)
        before = full_state(eng)
        res = sp.pullback_backfill(eng, first_ts=df.index[-3], series=df, until_ts=df.index[-1],
                                   changed_ts=[], audit_fn=MagicMock())
        self.assertEqual(res["reason"], "restore_rejected")
        self.assertFalse(eng.pullback_indicators.state_polluted)
        self.assertEqual(full_state(eng), before)
        # ② 시간대가 없는 ts 로 조회(비교 예외) → restore_rejected, 오염 아님
        eng = make_engine()
        feed_all(eng, df)
        before = full_state(eng)
        naive = df.index[-3].tz_localize(None)
        res = sp.pullback_backfill(eng, first_ts=naive, series=df, until_ts=df.index[-1],
                                   changed_ts=[], audit_fn=MagicMock())
        self.assertEqual(res["reason"], "restore_rejected")
        self.assertFalse(eng.pullback_indicators.state_polluted)
        self.assertEqual(full_state(eng), before)
        # ③ 되살리는 중(전략 복원) 실패 → restore_failed, 오염
        class BadRestore(StubSplitStrategy):
            def restore_split_state(self, d):
                raise RuntimeError("bad")

        eng = make_engine(BadRestore())
        feed_all(eng, df)
        res = sp.pullback_backfill(eng, first_ts=df.index[-3], series=df, until_ts=df.index[-1],
                                   changed_ts=[], audit_fn=MagicMock())
        self.assertEqual(res["reason"], "restore_failed")
        self.assertTrue(eng.pullback_indicators.state_polluted)


# ================================================================ 워밍업 (live_loop)
def _pb_cfg(**over):
    d = dict(ticker="KRW-JTO", interval="minute3", maType="ema", ma60p=60, ma200p=1000, pullbackP=20,
             slopeLB=500, minSlope=0.0, slopeDrop=0.5, buyOnGoldenCross=True, maxSplits=5,
             maxPullbackBuys=2, tp=5.0, sl=3.0, deadcross=True, compounding=False, capital=3000000, fee=0.05)
    d.update(over)
    return d


def _warmup_request_expr():
    """run_live_loop 의 `warmup_request = ...` 식을 소스에서 꺼낸다(EMA·MACD 공용 식이 그대로인지도 확인)."""
    tree = ast.parse(LIVE_LOOP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "warmup_request"
                                                for t in node.targets):
            return ast.unparse(node.value)
    raise AssertionError("warmup_request 식 없음")


def _run_live_loop_src():
    text = LIVE_LOOP.read_text(encoding="utf-8")
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_live_loop":
            return ast.get_source_segment(text, node)
    raise AssertionError("run_live_loop 없음")


class TestWarmup(unittest.TestCase):
    def setUp(self):
        from engine import live_loop
        self.ll = live_loop

    def test_warmup_bars_pullback_only(self):
        min_hist, long_bars = self.ll._pullback_warmup_bars(_pb_cfg())
        self.assertEqual((min_hist, long_bars), (2010, 2011))
        expr = _warmup_request_expr()
        self.assertEqual(expr, "_long_bars + 1 if attempt == 1 else min_hist + 1")
        self.assertEqual(eval(expr, {}, {"_long_bars": long_bars, "min_hist": min_hist, "attempt": 1}), 2012)
        self.assertEqual(self.ll._pullback_warmup_bars(_pb_cfg(ma200p=200, slopeLB=5))[1], self.ll.LONG_SEED_BARS)
        from engine.params import LiveParams
        p = LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="EMA")
        mh = self.ll._min_history_bars_for(p, "EMA")
        src = _run_live_loop_src()
        self.assertIn("_long_bars = max(LONG_SEED_BARS, min_hist)", src)
        self.assertEqual(eval(expr, {}, {"_long_bars": max(self.ll.LONG_SEED_BARS, mh), "min_hist": mh,
                                         "attempt": 1}), max(800, mh) + 1)
        self.assertIn('if strategy_tag == "PULLBACK":\n        min_hist, _pb_long_bars = _pullback_warmup_bars(pullback_cfg)', src)
        self.assertIn('if strategy_tag == "PULLBACK":\n                _long_bars = _pb_long_bars', src)

    def test_warmup_retry_uses_required_bars(self):
        min_hist, long_bars = self.ll._pullback_warmup_bars(_pb_cfg())
        expr = _warmup_request_expr()
        self.assertEqual(eval(expr, {}, {"_long_bars": long_bars, "min_hist": min_hist, "attempt": 2}), 2011)
        self.assertEqual(eval(expr, {}, {"_long_bars": 800, "min_hist": 200, "attempt": 2}), 201)

    def test_warmup_short_refuses_start(self):
        sent = []
        notify = lambda level, title, body, **kw: sent.append((level, title, body))  # noqa: E731
        self.assertFalse(self.ll._pullback_warmup_check(1500, 2010, holding=False, user_id="tuser",
                                                        ticker="KRW-JTO", notify=notify))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "CRITICAL")
        self.assertIn("새 전략 워밍업 봉 부족 (받은 1500 / 필요 2010)", sent[0][1])
        sent.clear()
        self.assertFalse(self.ll._pullback_warmup_check(10, 2010, holding=True, user_id="tuser",
                                                        ticker="KRW-JTO", notify=notify))
        self.assertIn("운영자", sent[0][2])
        sent.clear()
        self.assertTrue(self.ll._pullback_warmup_check(2010, 2010, holding=False, user_id="tuser",
                                                       ticker="KRW-JTO", notify=notify))
        self.assertEqual(sent, [])
        # 시드: PULLBACK 시드는 IndicatorState(EMA·MACD 지표)를 건드리지 않고 자기 지표·링만 채운다
        eng = make_engine()
        eng.pullback_indicators = eng.pullback_ring = None
        eng.indicators = SimpleNamespace(seeded=False)
        df = series_of(rand_closes(700, seed=11), ts_list(700))
        ok, mode, _r, df_buf = self.ll._pullback_seed_warmup(eng, df, _pb_cfg(ma200p=200, slopeLB=5))
        self.assertEqual((ok, mode), (True, "pullback"))
        self.assertEqual(eng.indicators, SimpleNamespace(seeded=False))
        self.assertEqual(eng.pullback_indicators.n, 700)
        self.assertEqual(len(eng.pullback_ring), 401)
        self.assertEqual(len(df_buf), 500)
        # run_live_loop: 관문(형성 중 봉·봉 부족)은 시드 앞, PULLBACK 은 폴백 시드 호출 분기 밖
        src = _run_live_loop_src()
        self.assertLess(src.index("_pullback_warmup_gate("), src.index("_seed_warmup_indicators("))
        self.assertIn("_pullback_warmup_gate(\n                    initial_df, _wu_action, min_hist,", src)
        self.assertIn('if strategy_tag == "PULLBACK":\n                _seed_ok, _seed_mode, _reason, initial_df = _pullback_seed_warmup(', src)

    def test_warmup_forming_bar_dropped_then_refused(self):
        """정확히 required_bars 개, 마지막 봉이 형성 중 → _warmup_trim_forming 은 kept_insufficient 로 남기지만
        PULLBACK 관문이 빼고 다시 세어 거부·CRITICAL. 지표에는 아무 봉도 들어가지 않는다."""
        required = 260
        tss = ts_list(required)
        df = series_of(rand_closes(required, seed=31), tss)
        now = tss[-1] + pd.Timedelta(seconds=20)  # 마지막 봉 시작 20초 뒤 = 형성 중
        trimmed, action, _last, _el = self.ll._warmup_trim_forming(df, 180, now, required)
        self.assertEqual(action, "kept_insufficient")
        self.assertEqual(len(trimmed), required)
        sent = []
        notify = lambda level, title, body, **kw: sent.append((level, title))  # noqa: E731
        eng = make_engine()
        eng.pullback_indicators = eng.pullback_ring = None
        out = self.ll._pullback_warmup_gate(trimmed, action, required, holding=False, user_id="tuser",
                                            ticker="KRW-JTO", notify=notify)
        self.assertIsNone(out)
        self.assertEqual(sent[0][0], "CRITICAL")
        self.assertIn(f"받은 {required - 1} / 필요 {required}", sent[0][1])
        self.assertIsNone(eng.pullback_indicators)
        # 한 봉 더 받으면(형성 중 봉 빼고 정확히 required) 통과, 형성 중 봉은 들어가지 않음
        tss2 = ts_list(required + 1)
        df2 = series_of(rand_closes(required + 1, seed=31), tss2)
        t2, a2, _, _ = self.ll._warmup_trim_forming(df2, 180, tss2[-1] + pd.Timedelta(seconds=20), required)
        self.assertEqual(a2, "dropped")
        out2 = self.ll._pullback_warmup_gate(t2, a2, required, holding=False, user_id="tuser",
                                             ticker="KRW-JTO", notify=notify)
        self.assertEqual(len(out2), required)
        self.assertEqual(out2.index[-1], tss2[-2])
        # EMA·MACD: kept_insufficient 동작은 _warmup_trim_forming 그대로(형성 중 봉 유지)
        self.assertEqual(self.ll._warmup_trim_forming(df, 180, now, required)[1], "kept_insufficient")

    def test_holding_includes_pending_wallet_recover(self):
        """sync_from_wallet() 뒤 has_position 이 True 이거나, 봇 주문 기준 진입가가 없어 False 로 되돌리고
        워밍업 뒤 지갑 복원을 기다리는 수량(boot_seed_recover_qty)이 있으면 보유."""
        h = self.ll._pullback_holding
        self.assertTrue(h(SimpleNamespace(has_position=True), None))
        self.assertTrue(h(SimpleNamespace(has_position=False), 12.5))
        self.assertFalse(h(SimpleNamespace(has_position=False), None))
        self.assertFalse(h(SimpleNamespace(has_position=False), 0.0))
        src = _run_live_loop_src()
        self.assertLess(src.index("position.sync_from_wallet()"),
                        src.index("holding=_pullback_holding(engine.position, boot_seed_recover_qty)"))

    def test_seed_and_replay_same_filter(self):
        """같은 봉 배열(거래량 0 봉 포함)이면 워밍업 시드와 BACKFILL 재생 결과가 같다(F6)."""
        cfg = _pb_cfg(ma200p=200, slopeLB=5)
        df = series_of(rand_closes(400, seed=41), ts_list(400))
        df.iloc[-4, df.columns.get_loc("Volume")] = 0.0  # 유령 봉
        a = make_engine()
        self.ll._pullback_seed_warmup(a, df, cfg, CandleValidator(max_spike_ratio=0.05))
        self.assertEqual(a.pullback_indicators.n, 399)
        b = make_engine()
        self.ll._pullback_seed_warmup(b, df.iloc[:-10], cfg, CandleValidator(max_spike_ratio=0.05))
        with no_orders():
            res = sp.pullback_backfill(b, first_ts=df.index[-10], series=df, until_ts=df.index[-1],
                                       changed_ts=[], audit_fn=MagicMock(),
                                       validator=CandleValidator(max_spike_ratio=0.05))
        self.assertEqual(res["replayed"], 9)
        self.assertEqual(full_state(a), full_state(b))


# ================================================================ BACKFILL
class TestBackfill(unittest.TestCase):
    def _setup(self, n=300, strategy=None, seed=5, maType="ema"):
        eng = make_engine(strategy, maType)
        df = series_of(rand_closes(n, seed=seed), ts_list(n))
        feed_all(eng, df)
        return eng, df

    def test_backfill_restores_from_ring(self):
        eng, df = self._setup()
        changed = list(df.index[-4:-1])  # 3봉
        audit = MagicMock()
        with patch.object(eng.pullback_ring, "restore", wraps=eng.pullback_ring.restore) as rs, no_orders():
            res = sp.pullback_backfill(eng, first_ts=min(changed), series=df, until_ts=df.index[-1],
                                       changed_ts=changed, audit_fn=audit)
        self.assertEqual(rs.call_count, 1)
        self.assertTrue(res["restored"])
        self.assertEqual(res["replayed"], 4)  # changed 3 + 마지막(안 바뀐) 1
        self.assertEqual(audit.call_count, 3)

    def test_backfill_out_of_ring_warns(self):
        eng, df = self._setup(n=450)
        before = full_state(eng)
        audit = MagicMock()
        with self.assertLogs("core.strategy_pullback", level="WARNING") as cm:
            res = sp.pullback_backfill(eng, first_ts=df.index[10], series=df, until_ts=df.index[-1],
                                       changed_ts=[df.index[10]], audit_fn=audit)
        self.assertFalse(res["restored"])
        self.assertEqual(res["reason"], "out_of_ring")
        self.assertTrue(any("[PULLBACK-BACKFILL] out of ring" in m for m in cm.output))
        self.assertEqual(full_state(eng), before)
        audit.assert_not_called()

    def test_backfill_replays_unchanged_tail(self):
        for maType in MA_TYPES:
            with self.subTest(maType=maType):
                eng, df = self._setup(n=300, strategy=StubSplitStrategy(), maType=maType)
                j = len(df) - 6
                changed_df = df.copy()
                changed_df.iloc[j, changed_df.columns.get_loc("Close")] *= 0.97
                changed_df.iloc[j, changed_df.columns.get_loc("Low")] *= 0.95
                audit = MagicMock()
                with no_orders():
                    res = sp.pullback_backfill(eng, first_ts=df.index[j], series=changed_df,
                                               until_ts=df.index[-1], changed_ts=[df.index[j]], audit_fn=audit)
                self.assertEqual(res["replayed"], 6)
                ref = make_engine(StubSplitStrategy(), maType)
                feed_all(ref, changed_df)
                self.assertEqual(full_state(eng), full_state(ref))
                self.assertEqual(audit.call_count, 1)

    def test_backfill_no_double_feed(self):
        from engine import live_loop as ll
        eng, df = self._setup(n=300)
        changed = [df.index[-5], df.index[-3]]
        closed_ts = df.index[-1] + pd.Timedelta(minutes=3)
        fed = []
        orig = eng.pullback_indicators.update

        def spy(c):
            fed.append(c)
            return orig(c)

        eng.pullback_indicators.update = spy
        count0 = eng.pullback_indicators.update_count
        audit = MagicMock()
        with patch.object(sp, "_default_audit", audit), patch.object(ll, "log_to_file"), no_orders():
            left = ll._pullback_backfill_step(eng, list(changed), df, closed_ts, "tuser", None)
        self.assertEqual(left, [])
        self.assertEqual(eng.pullback_indicators.update_count - count0, 5)  # df.index[-5] .. [-1] 각 1번
        self.assertEqual(fed, list(df["Close"].iloc[-5:]))
        self.assertEqual(audit.call_count, 2)
        self.assertEqual([c.args[1].ts for c in audit.call_args_list], changed)
        # run_live_loop: PULLBACK 분기가 봉별 루프 앞에서 목록을 비운다 → 봉별 루프(on_new_bar_confirmed) 0회
        src = _run_live_loop_src()
        i_pb = src.index('if strategy_tag == "PULLBACK" and backfill_ts_list:')
        i_loop = src.index("if backfill_ts_list:\n")
        self.assertLess(i_pb, i_loop)
        self.assertIn("backfill_ts_list = _pullback_backfill_step(", src[i_pb:i_loop])

    def test_ema_backfill_loop_unchanged(self):
        src = _run_live_loop_src()
        seg = src[src.index("if backfill_ts_list:\n"):]
        self.assertIn("for ts in sorted(backfill_ts_list):", seg)
        self.assertIn('"backfill_mode": True  # 실제 매매 금지 플래그', seg)
        self.assertIn("engine.on_new_bar_confirmed(bar, local_series, backfill_diff_summary)", seg)
        self.assertIn("saved_indicators.update(_backup_dead_cross_ts(engine.indicators))", seg)
        self.assertIn("_restore_dead_cross_ts(engine.indicators, saved_indicators)", seg)
        tree = ast.parse(src)
        ifs = [n for n in ast.walk(tree) if isinstance(n, ast.If)
               and ast.unparse(n.test) == "strategy_tag == 'PULLBACK' and backfill_ts_list"]
        self.assertEqual(len(ifs), 1)
        self.assertEqual(len(ifs[0].orelse), 0)
        self.assertEqual(len(ifs[0].body), 1)


# ================================================================ 실제 DB 감사 (임시 DB)
U = "t3audit"


class TestBackfillAuditDb(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="p3t3_"))
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

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rows(self):
        con = sqlite3.connect(self.db_path)
        try:
            return con.execute(
                "SELECT id, price, macd, signal, overall_ok, notes, backfill_close, backfill_type, prev_close "
                "FROM audit_buy_eval ORDER BY id").fetchall()
        finally:
            con.close()

    def test_default_audit_updates_backfill_columns_only(self):
        from services.db import insert_buy_eval
        bar_ts = pd.Timestamp(datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))
        bar_time = sp._kst_iso(bar_ts)
        self.assertTrue(bar_time.endswith("+09:00"))
        insert_buy_eval(user_id=U, ticker="KRW-JTO", interval_sec=180, bar=10, price=100.0, macd=1.5,
                        signal=1.2, have_position=False, overall_ok=True, failed_keys=[], checks={"a": 1},
                        notes="실시간", bar_time=bar_time)
        before = self._rows()
        self.assertEqual(len(before), 1)
        eng = SimpleNamespace(user_id=U, ticker="KRW-JTO", interval_sec=180, bar_count=11,
                              position=SimpleNamespace(has_position=False))
        bar = SimpleNamespace(ts=bar_ts, close=97.0)
        sp._default_audit(eng, bar, {"maTrend": 1.0, "ma200": 2.0, "maPullback": None,
                                     "slope200": None, "slope200_lb": None})
        after = self._rows()
        self.assertEqual(len(after), 1)  # 새 행 INSERT 0
        self.assertEqual(after[0][:6], before[0][:6])  # 실시간 칸 불변
        self.assertEqual(after[0][6], 97.0)
        self.assertEqual(after[0][7], "changed_close")
        self.assertEqual(after[0][8], 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
