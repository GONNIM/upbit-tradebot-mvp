"""
2차 T10: 재시작 시험 — 업비트 확정 봉(upbit_c, KRW-ETH 3분)으로 엔진(StrategyEngine PULLBACK)을 돌리다
가운데에서 엔진 객체를 버리고, DB(pullback_state) + 워밍업(앞 봉들)으로 새로 만든 뒤 나머지를 넣는다.

계획 T10 「재시작 시험」:
- 봉 k(배열 1/2 지점 뒤 첫 보유 봉 1곳 + 첫 미보유 봉 1곳)에서 재시작 → 판정 목록이 처음부터 넣은 것과 같다.
- 시험 조건(F16): 워밍업 입력은 「배열 첫 봉부터 k 까지 전부」(원본과 같은 시드 시작점).
- 실서버처럼 「최근 required_bars+1 봉만으로 재시드」한 경우는 판정 차이 봉 수를 기록만 한다
  (test_restart_recent_window_diff_recorded — 실패하지 않음, 차이는 배포 관찰 항목).

엔진·DB:
- T6 시험의 T6Case(임시 DB 파일만 씀 — get_db_path 패치)·EngineCase(알림·감사 대역)를 그대로 쓴다.
- 가짜 TEST trader 는 신호 봉 다음 봉 시가로 채운다(원본 px = nb.o) → 연속 실행 판정도 원본 기준값과 같아야 한다
  (엔진 경로 일치 덧시험 — 일치 시험 27건은 전략 단위, 여기서는 엔진·DB 저장·복원 경로).
- 실제 업비트·텔레그램·서버 DB 에 닿지 않는다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t10_restart -v
"""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import strategy_engine as se  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.candle_buffer import CandleBuffer  # noqa: E402
from core.indicator_state import IndicatorState  # noqa: E402
from core.position_state import PositionState  # noqa: E402
from core.strategy_action import Action  # noqa: E402
import engine.live_loop as live_loop  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import DIFF, FakeTrader, TICKER, USER  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t6_split_position import T6Case  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t10_parity import (  # noqa: E402
    _Quiet, bars_of, expected_lists, first_diff, js_cfg, load_expected, load_fixture, ms, py_params,
)

FIXTURE = "upbit_c"   # KRW-ETH 3분 — base 에서 GOLDEN 43·PULLBACK 187·매도 57
N_BARS = 4000         # 앞 4000봉(약 8.3일) — 1/2 지점 2000 근처에 보유·미보유 봉이 모두 있다
SPLIT_KEYS = ("entry_count", "pullback_count", "first_entry_ts", "first_entry_reason", "armed", "prev_golden",
              "fill_n", "trade_origin")


class NextOpenTrader(FakeTrader):
    """TEST 시장가 매수를 다음 봉 시가로 채운다(하네스가 next_open 을 미리 넣음). 매도는 FakeTrader 그대로(전량)."""

    next_open = None

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        return super().buy_market(self.next_open, ticker, ts=ts, meta=meta, krw_amount=krw_amount,
                                  strict_amount=strict_amount)


def pb_cfg():
    fx = load_fixture(FIXTURE)
    p = py_params(js_cfg("base"), fx)
    p.update(ticker=TICKER, capital=1_000_000)   # 엔진 종목 이름·운용자산(판정과 무관 — compounding no)
    return pbp.validate(p)


def frame(bars) -> pd.DataFrame:
    return pd.DataFrame({"Open": [b.open for b in bars], "High": [b.high for b in bars],
                         "Low": [b.low for b in bars], "Close": [b.close for b in bars],
                         "Volume": [b.volume for b in bars]},
                        index=pd.DatetimeIndex([b.ts for b in bars]))


class T10EngineCase(T6Case):
    def new_engine(self, trader=None):
        trader = trader or NextOpenTrader()
        c = pb_cfg()
        strat = sp.IncrementalPullbackStrategy(USER, TICKER, c, 3)
        pos = PositionState(trader=trader, ticker=TICKER)
        eng = se.StrategyEngine(
            buffer=CandleBuffer(maxlen=500), indicators=IndicatorState(), position=pos,
            strategy=strat, trader=trader, user_id=USER, ticker=TICKER,
            strategy_type="PULLBACK", q=None, interval_sec=180,
            take_profit=c["tp"] / 100, stop_loss=c["sl"] / 100,
        )
        eng.pullback_indicators = strat.indicators
        eng.pullback_ring = strat.ring
        eng._pullback_params_sha = None
        return eng

    def feed(self, eng, bars, start, stop, log, *, save_from=None):
        """bars[start:stop] 를 엔진 실시간 경로로. log 에 (i, 'BUY'|'SELL', 사유, 회차) 를 붙인다.
        save_from: 이 봉부터만 pullback_state 를 실제 DB 에 저장(그 앞은 저장 생략 — 봉마다 같은 1행 UPSERT 라
        재시작이 읽는 행은 마지막 저장과 같다. 봉당 sqlite 커밋 약 3ms 를 줄이려는 것). None 이면 늘 저장."""
        from services import pullback_state as pbs
        real_save = pbs.save
        tr = eng.trader
        for i in range(start, stop):
            b = bars[i]
            tr.next_open = bars[i + 1].open if i + 1 < len(bars) else b.close
            if save_from is None or i >= save_from:
                eng.on_new_bar_confirmed(b, pd.DataFrame(), dict(DIFF))
            else:
                with mock.patch.object(pbs, "save", side_effect=lambda *a, **k: True):
                    eng.on_new_bar_confirmed(b, pd.DataFrame(), dict(DIFF))
            assert pbs.save is real_save
            st = eng.strategy
            a = st.last_action
            if a is Action.BUY and i + 1 < len(bars):
                log.append((i, "BUY", st.last_buy_reason, st.last_eval.get("split_round")))
            elif a is Action.SELL:
                log.append((i, "SELL", st.last_sell_reason, st.last_eval.get("exit_round")))
        return log

    def restart(self, old, warm_df):
        """엔진 객체를 버리고 새로 만든다: 지갑 수량만 넘김 → 워밍업 시드(주문 없음) → pullback_state 복원."""
        tr = NextOpenTrader()
        tr.coin = old.trader.coin
        eng = self.new_engine(tr)
        ok, *_ = live_loop._pullback_seed_warmup(eng, warm_df, pb_cfg())
        self.assertTrue(ok)
        eng.bar_count = len(warm_df)
        eng.last_bar_ts = warm_df.index[-1]
        res = eng.pullback_restore_on_boot(warm_df, None)
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(tr.sell_calls, [])
        return eng, res

    # ------------------------------------------------ 공용 준비: 연속 실행 1회
    _continuous_cache = None   # (bars, log, states) — 판정 목록만 쓰므로 시험 사이에 한 번만 돌린다

    def continuous(self):
        if T10EngineCase._continuous_cache is not None:
            return T10EngineCase._continuous_cache
        bars = bars_of(load_fixture(FIXTURE))[:N_BARS]
        eng = self.new_engine()
        log, states = [], []
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            for i in range(len(bars)):
                self.feed(eng, bars, i, i + 1, log, save_from=len(bars))
                st = eng.strategy
                states.append({"holding": eng.position.has_position, "signal": st.last_action,
                               **{k: getattr(st, k) for k in SPLIT_KEYS}})
        T10EngineCase._continuous_cache = (bars, log, states)
        return T10EngineCase._continuous_cache

    def pick(self, states, holding: bool, armed=None) -> int:
        """1/2 지점 뒤 첫 봉 중 (보유 또는 미보유) + 그 봉 신호 없음 + 다음 봉도 신호 없음(경계 판정이 단순한 곳).
        armed 가 True/False 면 그 봉 판정 뒤 armed 도 그 값인 곳."""
        for k in range(len(states) // 2, len(states) - 2):
            s = states[k]
            if (s["holding"] is holding and (s["entry_count"] > 0) is holding
                    and s["signal"] is Action.HOLD and states[k + 1]["signal"] is Action.HOLD
                    and (armed is None or s["armed"] is armed)):
                return k
        self.fail(f"재시작 지점 없음 holding={holding} armed={armed}")


class TestRestart(T10EngineCase):
    def _run_restart(self, holding: bool, armed=None):
        bars, full_log, states = self.continuous()
        k = self.pick(states, holding, armed)
        # 1) 처음부터 k 까지 → 엔진 버림 (DB 의 pullback_state 는 봉마다 저장됨)
        eng = self.new_engine()
        head = []
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            self.feed(eng, bars, 0, k + 1, head, save_from=k - 5)
        before = {k2: getattr(eng.strategy, k2) for k2 in SPLIT_KEYS}
        pos_before = (eng.position.has_position, eng.position.qty, eng.position.avg_price)
        row = self.row()
        self.assertEqual(row["entry_count"], before["entry_count"])
        # 2) 새 엔진 = DB + 워밍업(배열 첫 봉 ~ k 전부, F16 시험 조건)
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            eng2, res = self.restart(eng, frame(bars[:k + 1]))
        del eng
        self.assertEqual(res["reason"], "restored" if holding else "flat", res)
        after = {k2: getattr(eng2.strategy, k2) for k2 in SPLIT_KEYS}
        if holding:
            self.assertEqual(after, before)
            self.assertEqual((eng2.position.has_position, eng2.position.qty), pos_before[:2])
            self.assertAlmostEqual(eng2.position.avg_price, pos_before[2], places=6)
        else:
            self.assertEqual({x: after[x] for x in ("entry_count", "armed", "prev_golden")},
                             {x: before[x] for x in ("entry_count", "armed", "prev_golden")})
            self.assertFalse(eng2.position.has_position)
        # 3) 나머지 봉
        tail = []
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            self.feed(eng2, bars, k + 1, len(bars), tail, save_from=len(bars))
        self.assertEqual(head + tail, full_log, f"재시작 k={k} 첫 차이 {first_diff(head + tail, full_log)}")
        n_after = sum(1 for x in full_log if x[0] > k)
        self.assertGreater(n_after, 5, "재시작 뒤 사건이 너무 적음")
        return k, n_after

    def test_restart_holding(self):
        k, n = self._run_restart(holding=True)
        print(f"\n[T10-RESTART] holding k={k} 재시작 뒤 사건 {n}건 일치", file=sys.stderr)

    def test_restart_holding_armed(self):
        """수정 1회차(verifier 변이 r3_armed_lost): 보유 중 + armed=True 인 지점 — 복원이 armed 를 버리면 실패."""
        k, n = self._run_restart(holding=True, armed=True)
        print(f"\n[T10-RESTART] holding+armed k={k} 재시작 뒤 사건 {n}건 일치", file=sys.stderr)

    def test_restart_flat(self):
        k, n = self._run_restart(holding=False)
        print(f"\n[T10-RESTART] flat k={k} 재시작 뒤 사건 {n}건 일치", file=sys.stderr)

    def test_engine_continuous_matches_reference(self):
        """덧시험: 엔진 경로(감사·DB 저장 포함) 연속 실행 판정 = 원본 기준값(같은 앞 N_BARS 봉으로 자른 비교)."""
        bars, log, _ = self.continuous()
        exp = load_expected(FIXTURE, "base")
        eb, es = expected_lists(exp)
        cut = ms(bars[-1].ts)
        idx = {ms(b.ts): i for i, b in enumerate(bars)}
        # 원본 목록은 전체 배열 기준 — 앞 N_BARS 봉 안 사건만 (마지막 봉 매수 신호는 양쪽에서 뺌)
        eb = [(idx[x[0]], "BUY", x[3], x[2]) for x in eb if x[1] <= cut]
        es = [(idx[x[0]], "SELL", x[1], x[2]) for x in es if x[0] <= cut]
        ref = sorted(eb + es, key=lambda x: (x[0], x[1] != "SELL"))
        self.assertEqual(log, ref, f"첫 차이 {first_diff(log, ref)}")
        self.assertGreater(len(ref), 20)

    def test_restart_recent_window_diff_recorded(self):
        """F16: 실서버처럼 최근 required_bars+1 봉만으로 재시드(EMA 시드 시작점이 다름) → 판정 차이 봉 수를 기록만 한다."""
        bars, full_log, states = self.continuous()
        rb = pbp.required_bars(pb_cfg())
        out = {}
        for holding in (True, False):
            k = self.pick(states, holding)
            eng = self.new_engine()
            head = []
            with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
                self.feed(eng, bars, 0, k + 1, head, save_from=k - 5)
                eng2, res = self.restart(eng, frame(bars[k + 1 - (rb + 1):k + 1]))
                tail = []
                self.feed(eng2, bars, k + 1, len(bars), tail, save_from=len(bars))
            want = [x for x in full_log if x[0] > k]
            a, b = set(tail), set(want)
            diff_bars = sorted({x[0] for x in a ^ b})
            out["holding" if holding else "flat"] = (k, res["reason"], len(diff_bars), len(want), len(tail))
        for name, (k, reason, nd, nw, nt) in out.items():
            print(f"\n[T10-RESTART-RECENT] {name} k={k} 재시드 봉={rb + 1} 복원={reason} "
                  f"판정 차이 봉={nd} (처음부터 {nw}건 / 최근 창 {nt}건)", file=sys.stderr)
        self.assertEqual(set(out), {"holding", "flat"})


class TestRecentWindowScan(unittest.TestCase):
    def test_restart_recent_window_scan_recorded(self):
        """F16 덧측정(기록만): 전략 단위로 세 세트(base) 전체에서 1000봉마다 재시작 — 최근 required_bars+1 봉 재시드 +
        보유 중이면 거래 칸(SPLIT_TRADE_KEYS)을 저장값으로(엔진 복원 규칙과 같음). 처음부터 넣은 판정과 다른 봉 수.
        (수정 1회차: upbit_c 만 → a·b·c. 지점 = k 1000, 2000, … (봉 수 − 1000 미만))"""
        from tests.regressions.test_r_2026_10_28_p3_t10_parity import FIXTURES, run_strategy
        for name in FIXTURES:
            fx = load_fixture(name)
            unit = int(fx["meta"]["unit_min"])
            params = py_params(js_cfg("base"), fx)
            rb = pbp.required_bars(params)
            bars = bars_of(fx)
            with _Quiet():
                fb, fs, _, _ = run_strategy(params, bars, interval_min=unit)
            full = {("B",) + x for x in fb} | {("S",) + x for x in fs}
            per_k = []
            for k in range(1000, len(bars) - 1000, 1000):
                with _Quiet():
                    b1, s1, st, fill = run_strategy(params, bars, stop=k + 1, interval_min=unit)
                    st2 = sp.IncrementalPullbackStrategy("t10", params["ticker"], params, unit)
                    for b in bars[k - rb:k + 1]:
                        sp._feed_bar(st2.indicators, st2.ring, st2, b, st2.replay_bar)
                    cur = st2.export_split_state()
                    if st.entry_count > 0:
                        cur.update({x: getattr(st, x) for x in sp.SPLIT_TRADE_KEYS})
                    st2.restore_split_state(cur)
                    b2, s2, _, _ = run_strategy(params, bars, st=st2, fill=fill, start=k + 1, interval_min=unit)
                got = {("B",) + x for x in b1 + b2} | {("S",) + x for x in s1 + s2}
                per_k.append((k, len({x[1] for x in got ^ full})))
            print(f"\n[T10-RESTART-SCAN] {name} 재시드 봉={rb + 1} 지점 {len(per_k)}곳 "
                  f"판정 차이 봉 합={sum(d for _, d in per_k)} 최대={max(d for _, d in per_k)} "
                  f"차이 있는 지점={sum(1 for _, d in per_k if d)} | {per_k}", file=sys.stderr)
            self.assertGreater(len(per_k), 5, name)


if __name__ == "__main__":
    unittest.main()
