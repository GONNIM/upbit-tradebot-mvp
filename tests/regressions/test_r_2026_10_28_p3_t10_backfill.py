"""
2차 T10: BACKFILL 시험 — 업비트 확정 봉(upbit_c)으로 엔진을 보유 중까지 돌린 뒤, 과거 봉 j(j < 마지막−5)의
종가가 바뀐 것으로 BACKFILL 을 일으킨다.

계획 T10 「BACKFILL 시험」:
- 재생 중 주문 0, 실제 회차·수량·평단 불변(Issue #11 — 실제 상태 무오염).
- 재생 뒤 지표·armed(·prev_golden)는 바뀐 배열로 처음부터 넣은 것과 같다.
- 바뀐 봉은 재평가된다(Issue #9 — 재평가 ≠ 중복, 감사 backfill 행).
- 경로: live_loop 의 PULLBACK BACKFILL(`_pullback_backfill_step` → 링 재생 1회, 봉별 backfill_mode 루프 대신).
  봉별 루프의 `backfill_mode=True` 봉이 엔진에 와도 무시된다(주문 0)는 것도 함께 본다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t10_backfill -v
"""
from __future__ import annotations

import copy
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import strategy_pullback as sp  # noqa: E402
from core.candle_buffer import Bar  # noqa: E402
from core.strategy_action import Action  # noqa: E402
import engine.live_loop as live_loop  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import USER  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t10_parity import _Quiet, bars_of, load_fixture  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t10_restart import (  # noqa: E402
    FIXTURE, T10EngineCase, frame, pb_cfg,
)

N_BARS = 1600
TRADE_KEYS = ("entry_count", "pullback_count", "first_entry_ts", "first_entry_reason", "fill_n", "inv_sum",
              "trade_origin", "pending_fill")


class TestBackfill(T10EngineCase):
    def _fresh_virtual(self, bars):
        """바뀐 배열을 처음부터 넣은 기준(주문 없는 재생 경로 = 원본 가상 보유)."""
        st = sp.IncrementalPullbackStrategy(USER, "KRW-TEST", pb_cfg(), 3)
        for b in bars:
            sp._feed_bar(st.indicators, st.ring, st, b, st.replay_bar)
        return st

    def test_backfill_no_orders_no_contamination(self):
        bars = bars_of(load_fixture(FIXTURE))[:N_BARS]
        # 1) 연속 실행으로 1/2 지점 뒤 첫 「보유 중 + 이 봉·다음 봉 신호 없음」 봉 m 을 찾는다
        eng = self.new_engine()
        log = []
        m = None
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            for i in range(len(bars) - 1):
                self.feed(eng, bars, i, i + 1, log, save_from=len(bars))
                if (i >= len(bars) // 2 and eng.position.has_position and eng.strategy.entry_count > 0
                        and eng.strategy.last_action is Action.HOLD):
                    m = i
                    break
        self.assertIsNotNone(m, "보유 중 봉 없음")
        j = m - 10                                           # j < 마지막 − 5, 링(401봉) 안
        st = eng.strategy
        before_trade = {k: getattr(st, k) for k in TRADE_KEYS}
        before_pos = (eng.position.has_position, eng.position.qty, eng.position.avg_price)
        before_ind = eng.pullback_indicators.export_state()
        n_buy, n_sell = len(eng.trader.buy_calls), len(eng.trader.sell_calls)

        # 2) 봉 j 종가가 바뀜(REST 확정값이 달라진 경우) → 바뀐 배열
        changed = list(bars[:m + 1])
        bj = changed[j]
        new_c = bj.close * 1.03
        changed[j] = Bar(ts=bj.ts, open=bj.open, high=max(bj.high, new_c), low=bj.low, close=new_c,
                         volume=bj.volume, is_closed=True, is_confirmed=True, source="REST_BACKFILL")
        series = frame(changed)
        closed_ts = bars[m + 1].ts                           # 지금 닫히는 봉(아직 엔진에 안 들어감)

        # 3) 봉별 루프의 backfill_mode 봉은 엔진이 무시(주문 0, 상태 불변)
        with _Quiet():
            eng.on_new_bar_confirmed(changed[j], series, {"rest_failed": False, "changed_count": 1,
                                                          "changed_ts": [bj.ts], "backfill_mode": True})
        self.assertEqual({k: getattr(st, k) for k in TRADE_KEYS}, before_trade)
        self.assertEqual(eng.pullback_indicators.export_state(), before_ind)

        # 4) PULLBACK BACKFILL = 링 재생 1회
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"), \
                mock.patch.object(sp, "pullback_backfill", wraps=sp.pullback_backfill) as pbf:
            left = live_loop._pullback_backfill_step(eng, [bj.ts], series, closed_ts, USER, None)
        self.assertEqual(left, [])                           # 봉별 루프는 건너뜀(두 번 넣지 않음)
        self.assertEqual(pbf.call_count, 1)
        self.assertEqual(pbf.call_args.kwargs["first_ts"], bj.ts)
        # 재생 중 주문 0
        self.assertEqual((len(eng.trader.buy_calls), len(eng.trader.sell_calls)), (n_buy, n_sell))
        # 실제 회차·수량·평단 불변(보유 중 재생 규칙)
        self.assertEqual({k: getattr(st, k) for k in TRADE_KEYS}, before_trade)
        self.assertEqual((eng.position.has_position, eng.position.qty, eng.position.avg_price), before_pos)
        # 재생 뒤 지표·armed·prev_golden = 바뀐 배열로 처음부터 넣은 것
        ref = self._fresh_virtual(changed)
        after_ind = eng.pullback_indicators.export_state()
        self.assertNotEqual(after_ind, before_ind, "바뀐 종가가 지표에 반영되지 않음")
        self.assertEqual(after_ind, ref.indicators.export_state())
        self.assertEqual((st.armed, st.prev_golden, st.last_ts), (ref.armed, ref.prev_golden, ref.last_ts))
        self.assertFalse(eng.pullback_indicators.state_polluted)
        # Issue #9: 바뀐 봉 j 는 재평가(감사 backfill 행 1개)
        rows = self.q("SELECT backfill_close, backfill_reason FROM audit_buy_eval WHERE bar_time=?",
                      (sp._kst_iso(bj.ts),))
        self.assertEqual(len(rows), 1, rows)
        self.assertAlmostEqual(rows[0][0], new_c)
        self.assertEqual(rows[0][1], "PULLBACK_BACKFILL_REPLAY")

        # 5) 다음 확정 봉은 평소처럼 실시간 판정 — 기대 값 = 재생 뒤 상태(지표·판정)를 복사한 전략에 같은 봉을
        #    넣은 결과(엔진에 BACKFILL 흔적이 남아 판정을 바꾸지 않음). 수정 1회차: 「아무 Action」 단정을 좁힘.
        expect = self._expect_next(eng, bars[m + 1])
        n_buy, n_sell = len(eng.trader.buy_calls), len(eng.trader.sell_calls)
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            self.feed(eng, bars, m + 1, m + 2, log, save_from=len(bars))
        self.assertEqual(st.last_ts, bars[m + 1].ts)
        self.assertIs(st.last_action, expect)
        self.assertIs(expect, Action.HOLD)   # 이 fixture 지점의 실제 값(보유 중, 신호 없음)
        self.assertEqual((len(eng.trader.buy_calls), len(eng.trader.sell_calls)), (n_buy, n_sell))

    @staticmethod
    def _expect_next(eng, bar):
        clone = copy.deepcopy(eng.strategy)
        pos = SimpleNamespace(has_position=eng.position.has_position, avg_price=eng.position.avg_price)
        with _Quiet():
            return clone.on_bar(bar, {}, pos, 0)

    # ------------------------------------------------ 수정 1회차: 계획 12절 6항
    def _scan(self, bars):
        """연속 실행 봉별 기록: (holding, entry_count, pullback_count, armed, last_eval)."""
        eng = self.new_engine()
        out = []
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            for i in range(len(bars) - 1):
                self.feed(eng, bars, i, i + 1, [], save_from=len(bars))
                st = eng.strategy
                out.append((eng.position.has_position, st.entry_count, st.pullback_count, st.armed,
                            dict(st.last_eval), st.last_action))
        return out

    def _replay_only_buy(self, holding: bool):
        """재생에서만 생기는 매수: 연속 실행에서 봉 j 는 armed 인데 종가 ≤ maPullback 이라 매수 없음 →
        j 종가를 maPullback × 1.01 로 바꾸면 재생(가상)에서 BUY:PULLBACK 이 생긴다. m = j 뒤 6봉 이상, 같은 보유 상태."""
        bars = bars_of(load_fixture(FIXTURE))[:N_BARS]
        rec = self._scan(bars)
        eff = pb_cfg()["maxSplits"]
        for j in range(len(rec) // 2, len(rec) - 70):
            h, ec, pc, armed, ev, act = rec[j]
            if not (armed and act is Action.HOLD and ev.get("active") and ev.get("maPullback")
                    and bars[j].close <= ev["maPullback"] and h is holding and (ec > 0) is holding
                    and ec < eff and pc < pb_cfg()["maxPullbackBuys"] and not ev.get("failed_keys", [None])[0:1] == ["POS_DESYNC"]):
                continue
            m = next((x for x in range(j + 6, j + 60)
                      if rec[x][0] is holding and (rec[x][1] > 0) is holding and rec[x][5] is Action.HOLD), None)
            if m is None:
                continue
            changed = list(bars[:m + 1])
            bj = changed[j]
            new_c = ev["maPullback"] * 1.01
            changed[j] = Bar(ts=bj.ts, open=bj.open, high=max(bj.high, new_c), low=bj.low, close=new_c,
                             volume=bj.volume, is_closed=True, is_confirmed=True, source="REST_BACKFILL")
            ref, ref_ev = self._fresh_virtual_eval(changed)
            if ref_ev[j].get("replay_signal") == "BUY:PULLBACK":
                return bars, rec, j, m, changed, ref, ref_ev
        self.fail(f"재생에서만 생기는 매수 지점 없음 holding={holding}")

    def _fresh_virtual_eval(self, bars):
        st = sp.IncrementalPullbackStrategy(USER, "KRW-TEST", pb_cfg(), 3)
        evs = []
        for b in bars:
            sp._feed_bar(st.indicators, st.ring, st, b, st.replay_bar)
            evs.append(dict(st.last_eval))
        return st, evs

    def _run_replay_only_buy(self, holding: bool):
        bars, rec, j, m, changed, ref, ref_ev = self._replay_only_buy(holding)
        eng = self.new_engine()
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            self.feed(eng, bars, 0, m + 1, [], save_from=len(bars))
        st = eng.strategy
        before_trade = {k: getattr(st, k) for k in TRADE_KEYS}
        before_pos = (eng.position.has_position, eng.position.qty, eng.position.avg_price)
        n_buy, n_sell = len(eng.trader.buy_calls), len(eng.trader.sell_calls)
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            live_loop._pullback_backfill_step(eng, [changed[j].ts], frame(changed), bars[m + 1].ts, USER, None)
        # 재생 중 주문 0 · 실보유 불변 · 오염 없음
        self.assertEqual((len(eng.trader.buy_calls), len(eng.trader.sell_calls)), (n_buy, n_sell))
        self.assertEqual((eng.position.has_position, eng.position.qty, eng.position.avg_price), before_pos)
        self.assertFalse(eng.pullback_indicators.state_polluted)
        # 재생 뒤 지표·armed·prev_golden = 바뀐 배열을 처음부터 넣은 것 (재생 매수 봉에서 원본처럼 armed 해제)
        self.assertFalse(ref_ev[j]["armed"])
        self.assertEqual(ref_ev[j]["entry_count"], rec[j][1] + 1)     # 그 봉에서 가상 회차 +1(주문은 없음)
        self.assertEqual(eng.pullback_indicators.export_state(), ref.indicators.export_state())
        self.assertEqual((st.armed, st.prev_golden, st.last_ts), (ref.armed, ref.prev_golden, ref.last_ts))
        return eng, st, before_trade, ref, j, m, bars

    def test_backfill_replay_only_buy_holding(self):
        """보유 중: 재생에서만 생긴 매수 신호는 가상 — 실제 회차·첫 체결·가상 평단은 재생 전 값(실보유 중 재생 규칙)."""
        eng, st, before_trade, ref, j, m, bars = self._run_replay_only_buy(holding=True)
        self.assertEqual({k: getattr(st, k) for k in TRADE_KEYS}, before_trade)
        print(f"\n[T10-BACKFILL-REPLAY-BUY] holding j={j} m={m} 실제 회차={before_trade['entry_count']} "
              f"기준(처음부터 가상) 회차={ref.entry_count} armed={st.armed}", file=sys.stderr)

    def test_backfill_replay_only_buy_flat(self):
        """미보유: 재생 매수 신호는 가상 거래(trade_origin=replay)로만 남고 주문은 없다. 다음 실시간 봉에서
        실보유가 없으므로 회차를 0 으로 맞추고 armed 는 그대로 둔다(재생 가상 거래 규칙 — T4·spec 4.3)."""
        eng, st, before_trade, ref, j, m, bars = self._run_replay_only_buy(holding=False)
        self.assertEqual(before_trade["entry_count"], 0)
        self.assertEqual(st.entry_count, ref.entry_count)            # 미보유 → 거래 칸도 재생 결과
        self.assertGreaterEqual(st.entry_count, 1)                   # 재생 매수 신호가 실제로 생겼음
        self.assertEqual(st.trade_origin, "replay")
        self.assertEqual(ref.trade_origin, "replay")
        armed_before = st.armed
        expect = self._expect_next(eng, bars[m + 1])
        n_buy, n_sell = len(eng.trader.buy_calls), len(eng.trader.sell_calls)
        with _Quiet(), mock.patch.object(live_loop, "log_to_file"):
            self.feed(eng, bars, m + 1, m + 2, [], save_from=len(bars))
        self.assertIs(st.last_action, expect)
        self.assertEqual(len(eng.trader.sell_calls), n_sell)         # 가상 거래를 팔지 않음
        self.assertIsNot(st.last_action, Action.BUY)                 # 이 지점은 다음 봉 HOLD(fixture 고정)
        self.assertEqual(st.entry_count, 0)                          # 실보유 없음 → 회차 0
        self.assertTrue(st.armed)                                    # armed 는 그대로(재생 가상 거래 규칙)
        self.assertEqual(len(eng.trader.buy_calls), n_buy)
        print(f"\n[T10-BACKFILL-REPLAY-BUY] flat j={j} m={m} 재생 뒤 회차={ref.entry_count}(replay) "
              f"armed={armed_before} → 다음 봉 action={st.last_action.value} 회차={st.entry_count} "
              f"armed={st.armed}", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
