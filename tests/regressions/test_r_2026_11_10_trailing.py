"""
1110-01 눌림목 추적 손절(트레일링 스톱) — 사용자 결정 「㉠ 한 묶음 · ㉡ 늘 팜 · ㉢ 막음」(11/10),
계획 docs/fable/2026-11-10-pullback-trailing-plan-1.md (verifier V1~V11 · Fable 권고 1~5).

본다:
  1. 식: IncrementalPullbackStrategy.trailing_advance 가 구버전 TrailingStopFilter(비율·고정폭)와 같은 봉에서 판다(무작위 종가 열).
  2. 판정: 이 거래가 켬으로 열렸을 때만 — 익절가에서 팔지 않고 무장, 손절(저가) 먼저, 추적 손절(종가) 매도 사유 TRAILING_STOP.
     꺼짐으로 연 거래는 지금과 같은 TP. 시간 밖 「익절 막음」이어도 추적 손절은 판다(㉡). 무장 중 추가 매수 안 함(㉢ TS_ARMED).
  3. 거래 시작 때 설정 고정: 보유 중 설정이 바뀌어도 이 거래는 연 때 값, 다음 거래부터 새 값(V5). 매수 되돌리기는 칸도 되돌림.
  4. 저장: pullback_state 5칸 저장·읽기·청산 초기화, 엔진 저장 사전·복원 사전, 재시작 따라잡기(Fable 권고 2).
  5. 설정 파일: TRAILING_KEYS 는 있을 때만 결과에 들어가고(꺼짐 = 옛 모양), 일부만 있거나 틀리면 거부. 운용 설정 4키와 무관.
  6. 거래 칸 목록: live_loop._PULLBACK_TRADE_KEYS == strategy_pullback.SPLIT_TRADE_KEYS(추적 손절 5칸 포함).

실행: python3 -m unittest tests.regressions.test_r_2026_11_10_trailing -v
"""
from __future__ import annotations

import os
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import strategy_pullback as sp  # noqa: E402
from core import strategy_engine as se  # noqa: E402
from core.filters.sell_filters import TrailingStopFilter  # noqa: E402
from core.position_state import PositionState  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from engine import pullback_apply as pa  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import BASE_PARAMS, V, make_strategy, ts_at  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import bar as sbar  # noqa: E402

TS_ON = {"ts_on": True, "ts_mode": "ratio", "ts_pct": 50.0}
# 보유(평단 100, 첫 체결 봉 0). tp 5% → 무장 종가 ≥ 105, sl 3% → 저가 ≤ 97
HOLD = {"entry_count": 1, "pullback_count": 1, "first_entry_ts": ts_at(0), "first_entry_reason": "PULLBACK",
        "fill_n": 1, "inv_sum": 1 / 100.0, "trade_origin": "replay", "prev_golden": True, "last_ts": ts_at(0),
        "trade_tp_pct": 5.0}


def holding(values, *, mode="ratio", pct=50.0, ts_on=True, **over):
    st = make_strategy(values, **({"ts_on": ts_on, "ts_mode": mode, "ts_pct": pct} if ts_on else {}), **over)
    st.restore_split_state({**HOLD, "trade_ts_mode": (mode if ts_on else None), "trade_ts_pct": (pct if ts_on else None)})
    return st


# ================================================================ 1. 식 = 구버전 TrailingStopFilter
def _ema_first_sell(closes, avg, tp_frac, pct_frac, fixed):
    """구버전 경로(strategy_incremental 의 SELL 블록 순서): update_highest_price(종가) → TrailingStopFilter.evaluate(종가)."""
    pos = PositionState()
    pos.apply_entry(1.0, avg, 0, pd.Timestamp("2026-10-01", tz="UTC"), "test")
    f = TrailingStopFilter(trailing_stop_pct=pct_frac, take_profit_pct=tp_frac, use_fixed_mode=fixed)
    for i, c in enumerate(closes):
        pos.update_highest_price(c)
        r = f.evaluate(position=pos, current_price=c)
        if r.should_block:
            return i
    return None


def _pb_first_sell(closes, avg, tp_pct, pct, mode):
    st = make_strategy(None)
    st.trade_ts_mode, st.trade_ts_pct = mode, pct
    for i, c in enumerate(closes):
        if st.trailing_advance(c, avg, tp_pct):
            return i
    return None


class TestFormulaSameAsOldFilter(unittest.TestCase):
    def test_random_paths_same_sell_bar(self):
        rnd = random.Random(1110)
        n_sold = 0
        for case in range(400):
            avg = rnd.choice([100.0, 431.0, 3_160_000.0, 0.0123])
            tp = rnd.choice([0.5, 1.0, 2.0, 3.0])
            pct = rnd.choice([10.0, 30.0, 50.0, 70.0, 90.0])
            p = avg
            closes = []
            for _ in range(rnd.randint(5, 80)):
                p = max(avg * 0.5, p * (1 + rnd.gauss(0.002, 0.01)))
                closes.append(p)
            for mode in ("ratio", "fixed"):
                with self.subTest(case=case, mode=mode):
                    a = _ema_first_sell(closes, avg, tp / 100, pct / 100, mode == "fixed")
                    b = _pb_first_sell(closes, avg, tp, pct, mode)
                    self.assertEqual(a, b)
                    n_sold += a is not None
        self.assertGreater(n_sold, 100)   # 매도까지 간 경우가 충분히 있음


# ================================================================ 2. 판정
class TestStep(unittest.TestCase):
    def test_tp_bar_arms_not_sells_then_drop_sells(self):
        st = holding([V(), V(), V()])
        self.assertIsNot(st.on_bar(sbar(1, o=104, h=107, l=103, c=106), {}, None, 0), Action.SELL)   # 종가 6% → 무장
        self.assertTrue(st.ts_armed)
        self.assertEqual(st.ts_peak, 106)
        self.assertEqual(st.entry_count, 1)
        self.assertIn("TS_ARMED", st.last_eval["failed_keys"])
        self.assertIsNot(st.on_bar(sbar(2, o=106, h=110, l=106, c=110), {}, None, 0), Action.SELL)  # 최고 110
        self.assertEqual(st.ts_peak, 110)
        # 수익 10 의 50% = 105 이하면 판다 → 104.9
        self.assertIs(st.on_bar(sbar(3, o=110, h=110, l=104.5, c=104.9), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TRAILING_STOP")
        self.assertEqual(st.last_eval["exit_round"], 1)
        self.assertEqual(st.entry_count, 0)
        self.assertEqual((st.trade_ts_mode, st.ts_armed, st.ts_peak, st.ts_fixed), (None, False, None, None))
        failed, checks = st.audit_view()
        self.assertEqual(checks["sell_reason"], "TRAILING_STOP")

    def test_sl_before_trailing_same_bar(self):
        st = holding([V(), V()])
        st.on_bar(sbar(1, o=104, h=107, l=103, c=106), {}, None, 0)
        self.assertIs(st.on_bar(sbar(2, o=106, h=106, l=96, c=99), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "SL")

    def test_sl_boundary_equal_low_sells_in_trailing_branch(self):
        """Fable 권고 1(11/10): 추적 손절 가지 안의 손절 비교(<=)는 AST 고정 시험이 걷어 내므로 행동으로 고정한다.
        저가가 손절가(97)와 정확히 같으면 판다 — `<` 로 바뀌면 이 시험이 깨진다."""
        for mode in ("ratio", "fixed"):
            with self.subTest(mode=mode):
                st = holding([V()], mode=mode)
                self.assertIs(st.on_bar(sbar(1, o=99, h=99, l=97.0, c=98), {}, None, 0), Action.SELL)  # 평단 100 · sl 3%
                self.assertEqual(st.last_sell_reason, "SL")

    def test_high_touch_without_close_does_not_arm_or_tp(self):
        st = holding([V()])
        self.assertIsNot(st.on_bar(sbar(1, o=100, h=108, l=100, c=104), {}, None, 0), Action.SELL)
        self.assertFalse(st.ts_armed)
        self.assertEqual(st.entry_count, 1)

    def test_trade_opened_off_keeps_tp_even_if_setting_now_on(self):
        st = holding([V()], ts_on=False)
        st.cfg = pa.build_cfg("u1", {**BASE_PARAMS, **TS_ON})     # 보유 중 설정을 켬(즉시 반영)
        self.assertIs(st.on_bar(sbar(1, o=104, h=106, l=103, c=105), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TP")

    def test_setting_off_mid_trade_keeps_trailing_for_this_trade(self):
        st = holding([V(), V()])
        st.cfg = pa.build_cfg("u1", dict(BASE_PARAMS))           # 보유 중 끔 → 이 거래는 그대로 추적 손절
        self.assertIsNot(st.on_bar(sbar(1, o=104, h=107, l=103, c=106), {}, None, 0), Action.SELL)
        self.assertTrue(st.ts_armed)

    def test_off_hours_tp_block_does_not_block_trailing(self):
        """㉡: 시간 밖 「익절 막음」이어도 추적 손절은 판다."""
        hours = {"enable_trading_hours": True, "trading_start_time": "09:30", "trading_end_time": "02:00",
                 "allow_sell_during_off_hours": False}
        st = holding([V(), V()], **hours)
        self.assertTrue(st._off_hours(ts_at(1)))
        st.on_bar(sbar(1, o=104, h=107, l=103, c=106), {}, None, 0)
        self.assertTrue(st.ts_armed)
        self.assertIs(st.on_bar(sbar(2, o=106, h=106, l=102.5, c=102.9), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TRAILING_STOP")
        self.assertIsNone(st.last_eval["blocked_signal"])

    def test_no_add_buy_while_armed_then_buys_when_not(self):
        """㉢: 무장 중에는 눌림목 재돌파여도 사지 않는다(눌림목 대기 armed 도 그대로)."""
        st = holding([V(p=105.5), V(p=105.5)])
        st.on_bar(sbar(1, o=104, h=107, l=103, c=106), {}, None, 0)      # 무장 + 저가 103 < 105.5 → 눌림목 대기 판정 자리
        self.assertTrue(st.ts_armed)
        a = st.on_bar(sbar(2, o=106, h=107, l=105, c=106.5), {}, None, 0)  # 저가 105 < 105.5, 종가 > 105.5 = 재돌파
        self.assertIsNot(a, Action.BUY)
        self.assertEqual(st.entry_count, 1)
        self.assertIn("TS_ARMED", st.last_eval["failed_keys"])
        # 같은 봉을 무장 없는 거래로 보면 산다(대조)
        st2 = holding([V(p=105.5)], ts_on=False)
        st2.trade_tp_pct = 50.0          # 익절가를 멀리 둬 이 봉에서 팔지 않게
        self.assertIs(st2.on_bar(sbar(1, o=106, h=107, l=105, c=106.5), {}, None, 0), Action.BUY)

    def test_new_trade_fixes_setting_and_undo_restores(self):
        st = make_strategy([V(p=50)], **TS_ON, buyOnGoldenCross=False)
        st.restore_split_state({"prev_golden": True})
        self.assertIs(st.on_bar(sbar(0, o=52, h=52, l=49, c=51), {}, None, 0), Action.BUY)   # 새 거래 = 눌림목 1차
        self.assertEqual((st.trade_ts_mode, st.trade_ts_pct, st.ts_armed), ("ratio", 50.0, False))
        self.assertTrue(st.rollback_last_buy())                                             # 주문 없이 끝남 → 되돌림
        self.assertEqual((st.entry_count, st.trade_ts_mode, st.trade_ts_pct), (0, None, None))

    def test_off_params_identical_eval_keys_none(self):
        st = make_strategy([V(p=50)], buyOnGoldenCross=False)
        st.restore_split_state({"prev_golden": True})
        st.on_bar(sbar(0, o=52, h=52, l=49, c=51), {}, None, 0)
        self.assertIsNone(st.trade_ts_mode)
        self.assertFalse(st.cfg["ts_on"])


# ================================================================ 3. 저장·복원
class TestPersist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ts1110_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = os.path.join(self.tmp, "tradebot_tsu.db")
        for t in ("services.init_db.get_db_path", "services.db.get_db_path"):
            p = mock.patch(t, return_value=self.db)
            p.start()
            self.addCleanup(p.stop)
        from services import init_db
        init_db.initialize_db("tsu")
        init_db.ensure_all_schemas("tsu")

    def test_roundtrip_and_reset(self):
        from services import pullback_state as ps
        state = {"ticker": "KRW-JTO", "interval": "minute3", "entry_count": 1, "qty": 3.0, "cost_krw": 300.0,
                 "trade_ts_mode": "fixed", "trade_ts_pct": 90.0, "ts_armed": True, "ts_peak": 120.5, "ts_fixed": 4.5}
        self.assertTrue(ps.save("tsu", "LIVE", state))
        row = ps.load("tsu", "LIVE")
        self.assertEqual({k: row[k] for k in sp.TRAIL_KEYS},
                         {"trade_ts_mode": "fixed", "trade_ts_pct": 90.0, "ts_armed": 1, "ts_peak": 120.5, "ts_fixed": 4.5})
        self.assertEqual(se._pullback_trail_saved(row),
                         {"trade_ts_mode": "fixed", "trade_ts_pct": 90.0, "ts_armed": True, "ts_peak": 120.5, "ts_fixed": 4.5})
        self.assertTrue(ps.reset_after_exit("tsu", "LIVE", 0.0))
        row = ps.load("tsu", "LIVE")
        self.assertEqual({k: row[k] for k in sp.TRAIL_KEYS},
                         {"trade_ts_mode": None, "trade_ts_pct": None, "ts_armed": 0, "ts_peak": None, "ts_fixed": None})


class TestSavedAndCatchup(unittest.TestCase):
    def test_saved_off_or_broken(self):
        off = {"trade_ts_mode": None, "trade_ts_pct": None, "ts_armed": False, "ts_peak": None, "ts_fixed": None}
        self.assertEqual(se._pullback_trail_saved({}), off)                                     # 옛 행(칸 없음)
        self.assertEqual(se._pullback_trail_saved({"trade_ts_mode": "x", "trade_ts_pct": 5}), off)
        self.assertEqual(se._pullback_trail_saved({"trade_ts_mode": "ratio", "trade_ts_pct": None}), off)
        r = se._pullback_trail_saved({"trade_ts_mode": "fixed", "trade_ts_pct": 50, "ts_armed": 1, "ts_peak": 110,
                                      "ts_fixed": None})
        self.assertEqual((r["trade_ts_mode"], r["ts_armed"], r["ts_peak"]), ("fixed", False, None))   # 깨진 무장 → 무장 전

    def test_engine_state_dict_has_trail_fields(self):
        st = holding([V()])
        st.ts_armed, st.ts_peak = True, 111.0
        eng = SimpleNamespace(strategy=st, ticker="KRW-TEST", _pb_qty=1.0, _pb_cost=100.0, _pullback_sizing_base=None,
                              _pullback_realized_pnl=0.0, _pullback_desync=False, _pullback_buy_fail_ts=None,
                              _pullback_params_sha=None, _pb_sl_streak=0, _pb_pause_start=None, _pb_pause_end=None)
        d = se.StrategyEngine._pullback_state_dict(eng)
        self.assertEqual((d["trade_ts_mode"], d["trade_ts_pct"], d["ts_armed"], d["ts_peak"]), ("ratio", 50.0, True, 111.0))

    def _series(self, closes, start=1):
        idx = [ts_at(i) for i in range(start, start + len(closes))]
        return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0}, index=idx)

    def test_catchup_arms_and_raises_peak_from_missed_bars(self):
        st = holding([V()])
        st.last_ts = ts_at(6)
        series = self._series([101, 106, 109, 107, 108, 103], start=1)   # 봉 1~6
        res = {}
        se.StrategyEngine._pullback_trail_catchup(st, series, ts_at(0), ts_at(6), 100.0, 1.0, None, res)
        self.assertEqual(res["trail_catchup"], 6)
        self.assertTrue(st.ts_armed)
        self.assertEqual(st.ts_peak, 109)           # 종가 최댓값(팔 판정은 다음 실시간 봉)
        self.assertEqual(st.entry_count, 1)

    def test_catchup_noop_when_trade_off_or_no_wallet(self):
        for st_args, wallet in (({"ts_on": False}, 1.0), ({}, 0.0)):
            st = holding([V()], **st_args)
            res = {}
            se.StrategyEngine._pullback_trail_catchup(st, self._series([110, 111]), ts_at(0), ts_at(2), 100.0, wallet,
                                                      None, res)
            self.assertEqual(res["trail_catchup"], 0)
            self.assertFalse(st.ts_armed)


# ================================================================ 4. 설정 파일
class TestParamsFile(unittest.TestCase):
    def base(self):
        return {**{k: BASE_PARAMS[k] for k in BASE_PARAMS}, "ma60p": 60, "ma200p": 200, "pullbackP": 60, "slopeLB": 20,
                "gcMaxGapPct": 0.0, "slStreakPause": 0,
                "slStreakCooldownHours": 6, "episodePullbackCap": 0, "episodeTpDecayPct": 50, "episodeTpFloorPct": 0.3}

    def test_absent_means_off_and_not_in_output(self):
        out = pbp.validate(self.base())
        for k in pbp.TRAILING_KEYS:
            self.assertNotIn(k, out)
        self.assertFalse(sp.IncrementalPullbackStrategy("u", "KRW-TEST", out, 3).cfg["ts_on"])

    def test_present_kept_in_order(self):
        out = pbp.validate({**self.base(), "ts_on": True, "ts_mode": "fixed", "ts_pct": 90})
        self.assertEqual(list(out)[-3:], ["ts_on", "ts_mode", "ts_pct"])
        cfg = sp.IncrementalPullbackStrategy("u", "KRW-TEST", out, 3).cfg
        self.assertEqual((cfg["ts_on"], cfg["ts_mode"], cfg["ts_pct"]), (True, "fixed", 90.0))

    def test_partial_or_bad_rejected(self):
        for bad in ({"ts_on": True}, {"ts_on": True, "ts_mode": "ratio"}, {"ts_on": "yes", "ts_mode": "ratio", "ts_pct": 5},
                    {"ts_on": True, "ts_mode": "peak", "ts_pct": 5}, {"ts_on": True, "ts_mode": "ratio", "ts_pct": 0},
                    {"ts_on": True, "ts_mode": "ratio", "ts_pct": 101}, {"ts_on": True, "ts_mode": "ratio", "ts_pct": 1.25}):
            with self.subTest(bad=bad):
                with self.assertRaises(pbp.PullbackParamsError):
                    pbp.validate({**self.base(), **bad})

    def test_ops_keys_unchanged(self):
        self.assertEqual(tuple(pbp.OPTIONAL_KEYS), ("enable_trading_hours", "trading_start_time", "trading_end_time",
                                                    "allow_sell_during_off_hours"))
        self.assertEqual(pa.OPS_KEYS, tuple(pbp.OPTIONAL_KEYS))
        for k in pbp.TRAILING_KEYS:
            self.assertIn(k, pa.ALL_KEYS)


class TestTradeKeyLists(unittest.TestCase):
    def test_live_loop_trade_keys_match(self):
        from engine import live_loop
        self.assertEqual(tuple(live_loop._PULLBACK_TRADE_KEYS), tuple(sp.SPLIT_TRADE_KEYS))
        for k in sp.TRAIL_KEYS:
            self.assertIn(k, sp.SPLIT_TRADE_KEYS)
            self.assertIn(k, sp.IncrementalPullbackStrategy._UNDO_KEYS)

    def test_labels(self):
        from services.terminology import PULLBACK_REASON_LABEL, PULLBACK_STATE_LABEL
        from v2 import api_read
        self.assertEqual(PULLBACK_REASON_LABEL["TRAILING_STOP"], "추적 손절")
        self.assertEqual(api_read.REASON_LABELS["TRAILING_STOP"], "추적 손절")
        self.assertEqual(PULLBACK_STATE_LABEL["TS_ARMED"], api_read.FAILED_KEY_LABELS["TS_ARMED"])
        self.assertEqual(se.PULLBACK_SELL_TRIGGER_KEY["TRAILING_STOP"], "Trailing Stop")


if __name__ == "__main__":
    unittest.main()
