"""
1105-09 Ver2 2단계(엔진·저장) 회귀 시험 — plan.md(docs/plans/2026-11-05-ver2-backtester/plan.md) 3절 2-2~2-6.

- R4 연속 손절 중단: 봇 매도 접수 성공(손절)에서만 +1, 다른 청산은 0, 임계값에 닿으면 손절 봉 시각부터
  지속 시간만큼 새 매수 막음, 끝 시각 봉부터 해제(연속 손절 수 0). 매도가 접수되지 않으면 세지 않음.
- 재생(워밍업·BACKFILL)은 중단 시작 전 봉을 막지 않는다(시작 ≤ 봉 < 끝 만 막음).
- 저장 행 → 엔진 칸 복원(미보유 재시작에도 중단 유지), 저장 dict 에 새 6칸.
- R5 구간 순번: 주문이 나가지 않으면 되돌림. 강제 매수는 순번 없음·설정 TP, 중단 중에도 허용(결정 8-D, 표식).
- 2-3′ 보유 중 tp 바꿈 → 이번 거래 TP% 재계산(감소 횟수·감소율·하한은 이전 값).
- 2-4 봉 단위 10·15·30분 확정 봉 재시도(Issue #8).
- 2-6 감사 문구(SL_PAUSE·GC_GAP·60선 기울기 사유).

실행:
    python3 -m unittest tests.regressions.test_r_2026_11_05_ver2_stage2 -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import rest_reconcile  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from engine import pullback_apply as pa  # noqa: E402
from services import terminology  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V, ts_at  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    CALM, DIP, EngineCase, FakeTrader, bar,
)

KST = "Asia/Seoul"
SLB = dict(o=55, h=55, l=50, c=52)      # 체결가 55 → 손절가 55 × 0.97 = 53.35, low 50 → 손절
TPB = dict(o=55, h=60, l=55, c=58)      # 익절가 55 × 1.05 = 57.75, high 60 → 익절


class NoSellTrader(FakeTrader):
    """매도 주문이 접수되지 않는 trader(빈 결과)."""

    def sell_market(self, qty, ticker, price, ts=None, meta=None):
        self.sell_calls.append({"qty": qty, "price": price, "meta": dict(meta or {})})
        return {}


def kst(i):
    return ts_at(i).tz_convert(KST)


class PauseCase(EngineCase):
    def make_pause(self, n=1, hours=0.15, trader=None, **over):
        # 0.15시간 = 9분 = 3분봉 3개. 화면 단위(0.5)는 화면에서만 쓰는 값이고 엔진 범위는 0 이상이다.
        return self.make(trader=trader, sl=3, tp=5, slStreakPause=n, slStreakCooldownHours=hours, **over)

    def buy_then_sl(self, start):
        """start 봉 눌림 매수 → start+1 체결 봉 → start+2 손절 봉."""
        self.assertIs(self.feed(bar(start, **DIP)), Action.BUY)
        self.feed(bar(start + 1, **CALM))
        return self.feed(bar(start + 2, **SLB))


class TestSlStreakPause(PauseCase):
    def test_sl_starts_pause_and_blocks_then_releases(self):
        self.make_pause(n=1)
        self.assertIs(self.buy_then_sl(0), Action.SELL)
        self.assertEqual(self.strat.last_sell_reason, "SL")
        self.assertEqual(self.eng._pb_sl_streak, 1)
        self.assertEqual(self.eng._pb_pause_start, kst(2))
        self.assertEqual(self.eng._pb_pause_end, kst(2) + pd.Timedelta(minutes=9))
        # 봉 3·4 = 중단 중 → 눌림이어도 매수 없음, 사유 SL_PAUSE(끝 시각 함께)
        self.assertIsNot(self.feed(bar(3, **DIP)), Action.BUY)
        fk, ck = self.strat.audit_view()
        self.assertEqual(fk, ["SL_PAUSE"])
        self.assertEqual(ck["pause_end"], (kst(2) + pd.Timedelta(minutes=9)).isoformat())
        self.assertIsNot(self.feed(bar(4, **DIP)), Action.BUY)
        self.assertEqual(len(self.trader.buy_calls), 1)
        # 봉 5 = 끝 시각(시작 + 9분) → 해제·연속 손절 0 → 매수
        self.assertIs(self.feed(bar(5, **DIP)), Action.BUY)
        self.assertEqual((self.eng._pb_sl_streak, self.eng._pb_pause_start, self.eng._pb_pause_end), (0, None, None))
        self.assertEqual(len(self.trader.buy_calls), 2)

    def test_threshold_two_and_non_sl_exit_resets(self):
        self.make_pause(n=2, hours=6)
        self.buy_then_sl(0)
        self.assertEqual((self.eng._pb_sl_streak, self.eng._pb_pause_end), (1, None))   # 임계값 전 → 중단 없음
        self.assertIs(self.feed(bar(3, **DIP)), Action.BUY)
        self.feed(bar(4, **CALM))
        self.assertIs(self.feed(bar(5, **TPB)), Action.SELL)
        self.assertEqual(self.strat.last_sell_reason, "TP")
        self.assertEqual(self.eng._pb_sl_streak, 0)                                     # 익절 → 0
        self.buy_then_sl(6)
        self.assertEqual((self.eng._pb_sl_streak, self.eng._pb_pause_end), (1, None))

    def test_manual_sell_wallet_zero_resets_streak(self):
        """plan 2-3: 사용자 수동 매도(services/trading_control.py 강제청산 — trader.sell_market 직접 호출)는
        엔진을 거치지 않고 지갑 0 으로 보인다 → _pullback_wallet_check 의 wallet_zero 청산 → 연속 손절 수 0."""
        from core import strategy_engine as se
        self.make_pause(n=2, hours=6)
        self.buy_then_sl(0)
        self.assertEqual(self.eng._pb_sl_streak, 1)
        self.assertIs(self.feed(bar(3, **DIP)), Action.BUY)
        self.feed(bar(4, **CALM))
        self.trader.coin = 0.0                         # 사용자 강제청산(봇 밖 매도)
        with mock.patch.object(se.StrategyEngine, "_record_external_sell", lambda *a, **k: None):
            self.feed(bar(5, **CALM))
        self.assertFalse(self.eng.position.has_position)
        self.assertEqual((self.eng._pb_sl_streak, self.eng._pb_pause_end), (0, None))
        self.assertEqual(self.eng._pullback_state_dict()["sl_streak"], 0)

    def test_not_accepted_sell_does_not_count(self):
        self.make_pause(n=1, trader=NoSellTrader())
        self.buy_then_sl(0)
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertEqual((self.eng._pb_sl_streak, self.eng._pb_pause_end), (0, None))

    def test_pause_off_when_threshold_zero(self):
        self.make_pause(n=0)
        self.buy_then_sl(0)
        self.assertEqual(self.eng._pb_sl_streak, 1)
        self.assertIsNone(self.eng._pb_pause_end)
        self.assertIs(self.feed(bar(3, **DIP)), Action.BUY)

    def test_state_dict_has_six_new_fields(self):
        self.make_pause(n=1)
        self.buy_then_sl(0)
        d = self.eng._pullback_state_dict()
        self.assertEqual(d["sl_streak"], 1)
        self.assertEqual((d["pause_start_ts"], d["pause_end_ts"]), (kst(2), kst(2) + pd.Timedelta(minutes=9)))
        for k in ("episode_idx", "trade_episode_idx", "trade_tp_pct"):
            self.assertIn(k, d)

    def test_saved_row_restores_pause_for_flat_restart(self):
        """미보유 재시작: 저장 행의 중단 칸을 엔진·전략 표식에 넣는다(복원의 flat 반환보다 먼저 부르는 함수)."""
        self.make_pause(n=1)
        self.eng._pullback_apply_pause_row({"sl_streak": 1, "pause_start_ts": kst(2).isoformat(),
                                            "pause_end_ts": (kst(2) + pd.Timedelta(minutes=9)).isoformat()})
        self.assertEqual(self.eng._pb_pause_end, kst(2) + pd.Timedelta(minutes=9))
        self.assertEqual(self.strat.pause_end, self.eng._pb_pause_end)
        self.assertIsNot(self.feed(bar(3, **DIP)), Action.BUY)
        self.assertEqual(self.trader.buy_calls, [])
        # 한쪽만 있는 행은 쓰지 않는다
        self.eng._pb_pause_start = self.eng._pb_pause_end = None
        self.eng._pullback_apply_pause_row({"sl_streak": 1, "pause_start_ts": None,
                                            "pause_end_ts": kst(9).isoformat()})
        self.assertEqual((self.eng._pb_pause_start, self.eng._pb_pause_end), (None, None))

    def test_force_buy_allowed_during_pause_with_mark(self):
        self.make_pause(n=1, hours=6)
        self.buy_then_sl(0)
        self.feed(bar(3, **CALM))
        r = self.eng._pullback_force_buy()
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(r["detail"]["paused_until"], (kst(2) + pd.Timedelta(hours=6)).isoformat())
        self.assertEqual(self.trader.buy_calls[-1]["meta"]["reason"], "FORCE")
        self.assertIsNone(self.strat.trade_episode_idx)                 # 강제 매수로 연 거래 = 순번 없음
        self.assertEqual(self.strat.trade_tp_pct, 5.0)                  # 설정 tp


class TestBootPauseOrderAndWalletZero(unittest.TestCase):
    """verifier 지적(1105-09 2단계 검증):
    (1) 기동 복원에서 「저장 회차는 있는데 지갑 0」 갈래도 연속 손절 수를 0 으로 한다(plan 2-3 봇 밖 청산).
    (2) 워밍업 재생 전에 중단 칸을 먼저 읽는 순서(engine/live_loop.py _pullback_seed_warmup)를 지킨다."""

    def test_restore_wallet_zero_resets_streak(self):
        from tests.regressions.test_r_2026_10_28_p3_t6_split_position import P990, T6Case, TestRestart
        from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V as V6
        from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import FakeTrader as FT

        class Case(T6Case):
            _two_rounds_armed = TestRestart._two_rounds_armed

            def runTest(self):
                self._two_rounds_armed()
                self.q_exec("UPDATE pullback_state SET sl_streak=1")
                tr = FT()
                tr.coin = 0.0                                    # 꺼져 있는 동안 앱·수동 매도
                self.make(values=[V6(p=945.0)] * 10, trader=tr)
                res = self.eng.pullback_restore_on_boot(None)
                self.assertEqual(res["reason"], "wallet_zero")
                self.assertEqual(self.eng._pb_sl_streak, 0)
                self.eng._pullback_persist()
                self.assertEqual(self.row()["sl_streak"], 0)

            def q_exec(self, sql):
                import sqlite3
                c = sqlite3.connect(self.db_path)
                try:
                    c.execute(sql)
                    c.commit()
                finally:
                    c.close()

        self.assertIsNotNone(P990)
        r = unittest.TestResult()
        Case().run(r)
        self.assertEqual((r.failures, r.errors), ([], []), (r.failures, r.errors))
        self.assertEqual(r.testsRun, 1)

    def test_preload_pause_before_warmup_replay(self):
        from types import SimpleNamespace
        from engine import live_loop
        order = []
        eng = SimpleNamespace(strategy=None, pullback_preload_pause=lambda: order.append("preload"))
        idx = pd.date_range("2026-11-05 09:00", periods=3, freq="3min", tz=KST)
        df = pd.DataFrame({"Open": [10.0] * 3, "High": [11.0] * 3, "Low": [9.0] * 3, "Close": [10.0] * 3,
                           "Volume": [1.0] * 3}, index=idx)   # 워밍업 df 는 대문자 칸(bar_from_row)
        cfg = {"ma60p": 3, "ma200p": 5, "pullbackP": 2, "slopeLB": 1, "maType": "ema"}
        real_feed = sp.feed_confirmed_bar

        def feed(engine, b):
            order.append("replay")              # 재생 순서만 본다(지표 계산은 다른 시험이 맡음)

        with mock.patch.object(sp, "feed_confirmed_bar", side_effect=feed):
            ok, *_ = live_loop._pullback_seed_warmup(eng, df, cfg)
        self.assertIs(sp.feed_confirmed_bar, real_feed)
        self.assertTrue(ok)
        self.assertEqual(order[0], "preload")
        self.assertEqual(order.count("preload"), 1)
        self.assertEqual(order.count("replay"), 3)


P = {"ticker": "KRW-TEST", "interval": "minute3", "maType": "ema", "ma60p": 3, "ma200p": 5,
     "pullbackP": 2, "slopeLB": 1, "buyOnGoldenCross": False, "maxSplits": 3, "maxPullbackBuys": 3,
     "tp": 50, "sl": 50, "deadcross": True, "compounding": False, "capital": 1_000_000, "fee": 0.05}


class TestStrategyPauseMarks(unittest.TestCase):
    def test_is_paused_window_start_inclusive_end_exclusive(self):
        st = sp.IncrementalPullbackStrategy("u", "KRW-TEST", P, 3)
        self.assertFalse(st.is_paused(ts_at(3)))
        st.pause_start, st.pause_end = kst(3), kst(6)
        self.assertFalse(st.is_paused(ts_at(2)))      # 시작 전 봉(재생의 과거 봉) — 막지 않음
        self.assertTrue(st.is_paused(ts_at(3)))
        self.assertTrue(st.is_paused(ts_at(5)))
        self.assertFalse(st.is_paused(ts_at(6)))
        self.assertTrue(st.is_paused(ts_at(4).tz_localize(None)))   # 시간대 없는 봉 시각 = UTC

    def test_replay_does_not_block_bars_before_pause_start(self):
        """재생도 같은 표식을 읽기만 한다 — 시작 전 봉은 가상 매수, 중단 중 봉은 가상 매수 없음."""
        p = P
        from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import ScriptedIndicators
        st = sp.IncrementalPullbackStrategy("u", "KRW-TEST", p, 3)
        st.bind(ScriptedIndicators([V()] * 10), None)
        st.pause_start, st.pause_end = kst(2), kst(4)
        acts = []
        for i in range(5):
            acts.append(st.on_bar(bar(i, **DIP), {}, None, 0))
        self.assertIs(acts[0], Action.BUY)                       # 시작 전
        self.assertNotIn(Action.BUY, acts[2:4])                  # 중단 중(2·3)
        self.assertIs(acts[4], Action.BUY)                       # 끝 시각 봉
        self.assertEqual((st.pause_start, st.pause_end), (kst(2), kst(4)))   # 재생은 표식을 바꾸지 않음


class TestEpisodeIndex(EngineCase):
    def test_order_failure_rolls_back_episode_fields(self):
        self.make(trader=FakeTrader(buy_ok=False), episodePullbackCap=1)
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls.__len__(), 1)
        self.assertEqual((self.strat.entry_count, self.strat.episode_idx, self.strat.trade_episode_idx,
                          self.strat.trade_tp_pct), (0, 0, None, None))

    def test_episode_tp_after_cap(self):
        self.make(episodePullbackCap=1, episodeTpDecayPct=50, episodeTpFloorPct=0.3, tp=5)
        st = self.strat
        self.assertEqual(st.episode_tp(None), 5)
        self.assertEqual(st.episode_tp(1), 5)
        self.assertEqual(st.episode_tp(2), 2.5)
        self.assertEqual(st.episode_tp(3), 1.25)
        self.assertEqual(st.episode_tp(10), 0.3)     # 하한

    def test_trade_tp_pct_used_for_tp_price(self):
        self.make(episodePullbackCap=1, episodeTpDecayPct=50, tp=5, sl=90)
        st = self.strat
        st.prev_golden = True                         # 이미 골든크로스 구간 안(첫 봉이 「막 골든」 이면 순번 0 으로 리셋)
        st.episode_idx = 1                            # 이번 구간에서 이미 눌림 거래 1번
        self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)
        self.assertEqual((st.episode_idx, st.trade_episode_idx, st.trade_tp_pct), (2, 2, 2.5))
        self.feed(bar(1, **CALM))
        # 익절가 55 × 1.025 = 56.375 — 설정 tp 5% 였다면 57.75 라 high 57 로는 팔리지 않는다
        self.assertIs(self.feed(bar(2, o=55, h=57, l=55, c=56)), Action.SELL)
        self.assertEqual(self.strat.last_sell_reason, "TP")


class TestApplyTpRecalc(unittest.TestCase):
    def test_trade_tp_after_change(self):
        old = {"episodePullbackCap": 1, "episodeTpDecayPct": 50, "episodeTpFloorPct": 0.3}
        self.assertEqual(pa.trade_tp_after_change(old, 4.0, None), 4.0)    # 골든크로스 1차·강제 매수
        self.assertEqual(pa.trade_tp_after_change(old, 4.0, 1), 4.0)       # 횟수 이하
        self.assertEqual(pa.trade_tp_after_change(old, 4.0, 3), 1.0)       # 4 × 0.5²
        self.assertEqual(pa.trade_tp_after_change(old, 1.0, 5), 0.3)       # 하한
        self.assertEqual(pa.trade_tp_after_change({"episodePullbackCap": 0}, 4.0, 7), 4.0)   # 꺼짐

    def test_row_clear_lists_six_new_columns(self):
        self.assertEqual(pa._ROW_CLEAR_V2, ("sl_streak", "pause_start_ts", "pause_end_ts", "episode_idx",
                                            "trade_episode_idx", "trade_tp_pct"))
        self.assertEqual(pa._ts_text(None), None)
        self.assertEqual(pa._ts_text("2026-11-05T10:00:00+09:00"), "2026-11-05T10:00:00+09:00")
        self.assertEqual(pa._ts_text(pd.Timestamp("2026-11-05 01:00", tz="UTC")), "2026-11-05T10:00:00+09:00")


class TestConfirmedCandleNewUnits(unittest.TestCase):
    """2-4: 10·15·30분 봉에서도 확정 봉 재시도(Issue #8)가 돈다 — 재시도 횟수는 봉 길이로 정해진다."""

    def setUp(self):
        rest_reconcile._case_b_state.clear()
        rest_reconcile._confirmed_fetch_consecutive_failures.clear()

    @staticmethod
    def df(rows):
        idx = [t.astimezone(timezone(timedelta(hours=9))).replace(tzinfo=None) for t, _ in rows]
        d = pd.DataFrame({"open": [c for _, c in rows], "high": [c for _, c in rows], "low": [c for _, c in rows],
                          "close": [c for _, c in rows], "volume": [1.0] * len(rows)}, index=pd.DatetimeIndex(idx))
        return d

    def test_retry_then_confirmed(self):
        for tf, minutes in (("minute10", 10), ("minute15", 15), ("minute30", 30)):
            with self.subTest(tf):
                self.setUp()
                closed = datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)
                lag = self.df([(closed - timedelta(minutes=minutes), 99.0)])
                ok = self.df([(closed, 100.0), (closed + timedelta(minutes=minutes), 101.0)])
                calls = []

                def fake(ticker, interval, count):
                    calls.append(interval)
                    return lag if len(calls) == 1 else ok
                with mock.patch.object(rest_reconcile.pyupbit, "get_ohlcv", side_effect=fake), \
                        mock.patch.object(rest_reconcile.time, "sleep", return_value=None):
                    r = rest_reconcile.fetch_confirmed_candle("KRW-JTO", tf, closed)
                self.assertIsNotNone(r)
                self.assertEqual(float(r["Close"]), 100.0)
                self.assertEqual(calls, [tf, tf])

    def test_auto_retry_count_by_unit(self):
        """재시도 횟수 = (봉 초 − 5) × 50% ÷ 5. 조회 횟수는 그 수 + 1(끝난 뒤 한 번 더 보는 조회 — 1분봉도 같음).
        새 단위가 기본값(60초 → 5회)으로 떨어지지 않는지 본다."""
        for tf, sec in (("minute1", 60), ("minute10", 600), ("minute15", 900), ("minute30", 1800)):
            with self.subTest(tf):
                self.setUp()
                closed = datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)
                lag = self.df([(closed - timedelta(seconds=sec), 99.0)])
                resp = mock.MagicMock(status_code=200)
                resp.json.return_value = [{"trade_time_utc": "01:00:15", "trade_price": 100.0, "trade_volume": 1.0}]
                with mock.patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=lag) as g, \
                        mock.patch.object(rest_reconcile.requests, "get", return_value=resp), \
                        mock.patch.object(rest_reconcile.time, "sleep", return_value=None):
                    rest_reconcile.fetch_confirmed_candle("KRW-JTO", tf, closed)
                self.assertEqual(g.call_count, max(1, int((sec - 5) * 0.5 / 5)) + 1)


class TestAuditTexts(unittest.TestCase):
    def test_pullback_eval_text_new_keys(self):
        self.assertEqual(terminology.pullback_eval_text(["SL_PAUSE"], {"pause_end": "2026-11-05T16:42:00+09:00"}),
                         "연속 손절로 매수 중단 중 — 11-05 16:42 까지")
        self.assertEqual(terminology.pullback_eval_text(["SL_PAUSE"], {}), "연속 손절로 매수 중단 중")
        self.assertEqual(terminology.pullback_eval_text(["GC_GAP"], {"gap200_pct": 1.234}),
                         "상승폭 제한 — 1차 매수 건너뜀(장기선 대비 +1.23%)")
        self.assertEqual(terminology.pullback_eval_text(["NOT_ACTIVE"], {"inactive_reason": "ma60_slope_low"}),
                         "감시 구간 밖(60선 기울기 낮음)")
        self.assertEqual(terminology.pullback_eval_text(["NOT_ACTIVE"], {"inactive_reason": "slope_drop"}),
                         "감시 구간 밖(200선 기울기 둔화)")   # 옛 감사 행


if __name__ == "__main__":
    unittest.main()
