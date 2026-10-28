"""
2차 T9: 거래 시간 제한 (결정 D5) — PULLBACK 에서만, 기본 꺼짐.

계획 `docs/specs/v2-dashboard/plan-phase2.md` 「### T9:」:
- 시간 밖(KST, trading_start_time ~ trading_end_time, 자정 넘김 허용)에도 지표·armed·prev_golden 은 갱신하고
  주문만 막는다. 매도는 allow_sell_during_off_hours=True 이면 허용. 막힌 매수는 감사 failed_keys=["OFF_HOURS"].
- 결정 13-7 (가): 시간 밖에 매수 조건이 맞은 봉에서도 armed 유지 → 시간이 열린 첫 봉에서 조건이 맞으면 매수.
  시간 밖 골든크로스는 놓친 것으로 두고 다시 사지 않는다. 회차는 늘리지 않는다.
- 판정 시각 = 봉 마감 시각(봉 시작 + 봉 단위, KST) — 원본 체결 시각(다음 봉 시가)과 같은 순간.
- EMA·MACD 는 거래 시간 설정을 쓰지 않는다(F5) — 동작 무변경.

시험 봉 시각: ts_at(i) = 2026-10-01 00:00 UTC + 3i 분 = 09:00 KST + 3i 분, 마감 = 09:03 + 3i 분 (KST).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t9_trading_hours -v
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import strategy_engine as se  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import (  # noqa: E402
    DEAD, ScriptedIndicators, V, make_strategy, run, ts_at,
)
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import bar as sbar  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    CALM, DIP, EngineCase, FakeTrader, bar,
)

BASE_COMMIT = "ebe4605"  # 2차 T8 커밋 — T9 전 원본(EMA 경로 비교 기준)
KST = "Asia/Seoul"


def hours(start, end, allow_sell=True):
    return {"enable_trading_hours": True, "trading_start_time": start, "trading_end_time": end,
            "allow_sell_during_off_hours": allow_sell}


# 봉 0(마감 09:03)·봉 1(09:06) 시간 밖, 봉 2(09:09)부터 시간 안 — 자정 넘김 구간
OPEN_AT_BAR2 = hours("09:09", "02:00")
# 봉 0(09:03) 안, 봉 1(09:06)·봉 2(09:09) 밖, 봉 3(09:12)부터 안
OFF_BAR1_2 = hours("09:12", "09:06")


def buy_eval_failed(eng_mod=se):
    return [c.kwargs.get("failed_keys") for c in eng_mod.insert_buy_eval.call_args_list]


# ================================================================ 계획 T9 시험
class TestBlocksOrdersOnly(EngineCase):
    def test_trading_hours_blocks_orders_only(self):
        """시간 밖 눌림 신호 → 주문 0, 지표 갱신은 됨, armed 유지(결정 13-7 가), 회차 불변, 감사 OFF_HOURS."""
        self.make(**OPEN_AT_BAR2)
        ind = self.eng.pullback_indicators
        before = ind.update_count
        self.assertIs(self.feed(bar(0, **DIP)), Action.HOLD)
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual(self.trader.rejects, [])           # 주문 전 차단 감사(BUY_REJECTED)도 없음 — 주문 시도 자체가 없음
        self.assertEqual(ind.update_count, before + 1)       # 지표는 이 봉을 받음
        self.assertTrue(self.strat.armed)                    # 매수 조건이 맞았지만 막힌 봉 → armed 유지
        self.assertEqual((self.strat.entry_count, self.strat.pullback_count, self.strat.pending_fill), (0, 0, False))
        self.assertTrue(self.strat.prev_golden)              # prev_golden 도 갱신
        self.assertEqual(buy_eval_failed()[-1], ["OFF_HOURS"])
        ck = se.insert_buy_eval.call_args_list[-1].kwargs["checks"]
        self.assertEqual(ck["off_hours"], 1)
        self.assertEqual(ck["blocked_signal"], "BUY:PULLBACK")
        self.assertIsNone(ck["buy_reason"])
        self.assertEqual(ck["round"], 0)
        # 같은 시간 밖 다음 봉도 주문 없음
        self.feed(bar(1, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        # 텔레그램 알림 없음(봉마다 소음 방지). 시험 환경의 분할 상태 저장 실패 알림(임시 DB 없음)은 이 시험 대상 밖
        others = [c for c in self.notify.call_args_list
                  if not str(c.kwargs.get("dedupe_key", "")).startswith("pullback_state_save:")]
        self.assertEqual(others, [])

    def test_off_hours_armed_buys_when_open(self):
        """시간이 열린 첫 봉에서 close > maPullback → 매수 1 (새 눌림을 기다리지 않음)."""
        self.make(**OPEN_AT_BAR2)
        self.feed(bar(0, **DIP), bar(1, **CALM))             # 1: 시간 밖, 눌림 없음(low 52 ≥ 50) → armed 그대로
        self.assertTrue(self.strat.armed)
        self.assertEqual(self.trader.buy_calls, [])
        self.assertIs(self.feed(bar(2, **CALM)), Action.BUY)  # 열린 첫 봉: armed + close 55 > 50
        self.assertEqual(len(self.trader.buy_calls), 1)
        m = self.trader.buy_calls[0]["meta"]
        self.assertEqual((m["reason"], m["split_round"], m["pullback_round"]), ("PULLBACK", 1, 1))

    def test_off_hours_missed_golden_not_rebought(self):
        """시간 밖 골든크로스 → 열린 뒤 사유 GOLDEN 매수 0 (그 다음은 눌림목 경로)."""
        vals = [V(**DEAD), V(), V(), V(), V()]
        st = make_strategy(vals, **OPEN_AT_BAR2)
        calm = dict(o=60, h=61, l=55, c=60)                  # low 55 ≥ maPullback 50 → armed 안 됨
        res = run(st, [sbar(0, **calm), sbar(1, **calm), sbar(2, **calm), sbar(3, **calm)])
        # 0: 데드(시간 밖) 1: 골든 전환(시간 밖) → 놓침 2·3: 시간 안, 골든 유지 → GOLDEN 매수 없음
        self.assertEqual([a.value for a, _ in res], ["HOLD", "HOLD", "HOLD", "HOLD"])
        self.assertEqual(st.entry_count, 0)
        self.assertEqual(st.last_eval["just_crossed"], False)
        # 그 다음은 눌림목 경로
        a = st.on_bar(sbar(4, o=60, h=61, l=40, c=60), {}, None, 0)
        self.assertIs(a, Action.BUY)
        self.assertEqual(st.last_buy_reason, "PULLBACK")

    def test_golden_in_hours_still_bought(self):
        """대조: 같은 배열에서 골든크로스가 시간 안이면 GOLDEN 매수(원본 그대로)."""
        vals = [V(**DEAD), V(), V()]
        st = make_strategy(vals, **hours("09:00", "02:00"))
        res = run(st, [sbar(0), sbar(1), sbar(2)])
        self.assertEqual(res[1], (Action.BUY, "GOLDEN"))

    def test_trading_hours_cross_midnight(self):
        """09:00~02:00: 01:59 안·02:00 밖, 08:59 밖·09:00 안, 23:59·00:00 안."""
        def at(hhmm):
            return pd.Timestamp(f"2026-10-02 {hhmm}", tz=KST)
        f = sp.is_trading_time
        self.assertTrue(f(at("01:59"), "09:00", "02:00"))
        self.assertFalse(f(at("02:00"), "09:00", "02:00"))
        self.assertFalse(f(at("08:59"), "09:00", "02:00"))
        self.assertTrue(f(at("09:00"), "09:00", "02:00"))
        self.assertTrue(f(at("23:59"), "09:00", "02:00"))
        self.assertTrue(f(at("00:00"), "09:00", "02:00"))
        # 같은 날 구간 09:00~18:00
        self.assertTrue(f(at("17:59"), "09:00", "18:00"))
        self.assertFalse(f(at("18:00"), "09:00", "18:00"))
        self.assertFalse(f(at("01:00"), "09:00", "18:00"))
        # KST 명시(Issue #2): UTC 16:59 = KST 01:59 안, UTC 17:00 = KST 02:00 밖
        self.assertTrue(f(pd.Timestamp("2026-10-01 16:59", tz="UTC"), "09:00", "02:00"))
        self.assertFalse(f(pd.Timestamp("2026-10-01 17:00", tz="UTC"), "09:00", "02:00"))
        # 판정 시각 = 봉 마감(봉 시작 + 봉 단위): 3분봉 01:56 시작(마감 01:59) 안, 01:57 시작(마감 02:00) 밖
        st = make_strategy(None, **hours("09:00", "02:00"))
        self.assertFalse(st._off_hours(pd.Timestamp("2026-10-01 16:56", tz="UTC")))
        self.assertTrue(st._off_hours(pd.Timestamp("2026-10-01 16:57", tz="UTC")))
        # 시작 == 끝 은 하루 종일 안(기존 live_loop_old._is_trading_hours 와 같음)
        self.assertTrue(f(at("05:00"), "09:00", "09:00"))

    def test_sell_allowed_off_hours(self):
        """시간 밖 TP: 허용(기본) → 매도, 막음 → 매도 0·보유·회차 유지 후 열린 첫 봉에서 매도."""
        tp_bar = dict(o=55, h=60, l=54, c=58)                # 평단 55 × 1.05 = 57.75 ≤ high 60
        for allow in (True, False):
            with self.subTest(allow=allow):
                self.make(**hours("09:12", "09:06", allow_sell=allow))
                self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)   # 봉 0 시간 안 → 1회차
                self.assertTrue(self.eng.position.has_position)
                a = self.feed(bar(1, **CALM))                          # 체결 봉(시간 밖) — TP 평가 안 함
                a = self.feed(bar(2, **tp_bar))                        # 시간 밖 TP
                if allow:
                    self.assertIs(a, Action.SELL)
                    self.assertEqual(len(self.trader.sell_calls), 1)
                else:
                    self.assertIsNot(a, Action.SELL)
                    self.assertEqual(self.trader.sell_calls, [])
                    self.assertTrue(self.eng.position.has_position)
                    self.assertEqual(self.strat.entry_count, 1)        # 거래 그대로(정리 안 함)
                    ck = se.insert_sell_eval.call_args_list[-1].kwargs["checks"]
                    self.assertEqual(ck["failed_keys"], ["OFF_HOURS"])
                    self.assertEqual(ck["blocked_signal"], "SELL:TP")
                    self.assertFalse(se.insert_sell_eval.call_args_list[-1].kwargs["triggered"])
                    self.assertIs(self.feed(bar(3, **tp_bar)), Action.SELL)  # 열린 첫 봉에서 매도
                    self.assertEqual(len(self.trader.sell_calls), 1)

    def test_sell_default_allowed_when_key_missing(self):
        """거래 시간을 켜고 allow_sell_during_off_hours 키를 아예 뺀 설정 → 기본 허용: 시간 밖 손절·데드크로스 봉 SELL."""
        win = {"enable_trading_hours": True, "trading_start_time": "09:30", "trading_end_time": "02:00"}
        holding = {"entry_count": 1, "pullback_count": 1, "first_entry_ts": ts_at(0),
                   "first_entry_reason": "PULLBACK", "fill_n": 1, "inv_sum": 1 / 100.0,
                   "trade_origin": "replay", "prev_golden": True, "last_ts": ts_at(0)}
        # 손절: 평단 100, sl 3% → 97. 봉 1(마감 09:06) 시간 밖, low 96
        st = make_strategy([V()], **win)
        self.assertNotIn("allow_sell_during_off_hours", win)      # 키 없음 → 전략 기본값으로 판정
        st.restore_split_state(dict(holding))
        self.assertTrue(st._off_hours(ts_at(1)))
        self.assertIs(st.on_bar(sbar(1, o=99, h=99, l=96, c=98), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "SL")
        # 데드크로스: 봉 1 시간 밖, 60선 ≤ 200선
        st = make_strategy([V(**DEAD)], **win)
        st.restore_split_state(dict(holding))
        self.assertIs(st.on_bar(sbar(1, o=100, h=101, l=99, c=100), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "DEADCROSS")

    def test_is_trading_time_naive_is_utc(self):
        """Issue #2: 시간대 없는 값은 UTC 로 본다 — 16:59(=KST 01:59) 안, 17:00(=KST 02:00) 밖 (09:00~02:00).
        봉 시작·판정 시각 변환 없이 is_trading_time 을 직접 부른다."""
        self.assertTrue(sp.is_trading_time(pd.Timestamp("2026-10-01 16:59"), "09:00", "02:00"))
        self.assertFalse(sp.is_trading_time(pd.Timestamp("2026-10-01 17:00"), "09:00", "02:00"))

    def test_off_hours_blocks_add_split_while_holding(self):
        """보유 중 시간 밖 추가 분할 매수도 막음 — 회차 불변, 열리면 armed 로 매수."""
        self.make(**OFF_BAR1_2)
        self.feed(bar(0, **DIP))                                       # 1회차(시간 안)
        self.feed(bar(1, **CALM))                                      # 체결 봉
        self.feed(bar(2, **DIP))                                       # 시간 밖 눌림 → 막음
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual(self.strat.entry_count, 1)
        self.assertTrue(self.strat.armed)
        self.assertIs(self.feed(bar(3, **CALM)), Action.BUY)           # 열린 첫 봉 → 2회차
        self.assertEqual([c["meta"]["split_round"] for c in self.trader.buy_calls], [1, 2])

    def test_ema_ignores_trading_hours(self):
        """EMA 동작 무변경: (1) 시간 밖 봉에서도 EMA 매수 주문 그대로 (2) 엔진의 PULLBACK 밖 함수·EMA 전략 파일이
        T8 커밋 원본과 같다 (3) 거래 시간 판정 함수는 PULLBACK 전략 파일에서만 쓴다."""
        self.make(strategy_type="EMA", **OPEN_AT_BAR2)
        self.eng.strategy = SimpleNamespace(last_buy_reason="EMA_GC", buy_conditions={}, last_weak_entry=None)
        self.eng._execute_buy(bar(0), {"ema_fast": 1, "ema_slow": 2})   # 봉 0 = PULLBACK 기준 시간 밖
        self.assertEqual(len(self.trader.buy_calls), 1)

        def funcs(src):
            tree = ast.parse(src)
            out = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "pullback" not in node.name.lower():
                    out[node.name] = ast.dump(node)
            return out

        for rel in ("core/strategy_engine.py", "core/strategy_incremental.py", "engine/params.py"):
            try:
                base = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{rel}"],
                                      capture_output=True, check=True, text=True).stdout
            except Exception:
                self.skipTest("git 원본 없음")
            now = (ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(funcs(now), funcs(base), rel)

        users = []
        for p in list((ROOT / "core").glob("*.py")) + list((ROOT / "engine").glob("*.py")):
            if "is_trading_time" in p.read_text(encoding="utf-8") or "OFF_HOURS" in p.read_text(encoding="utf-8"):
                users.append(p.name)
        self.assertEqual(sorted(users), ["strategy_pullback.py"])

    def test_default_off(self):
        """선택 4키가 없으면 꺼짐 — 어느 시각이든 막지 않음. 로더 기본값도 꺼짐."""
        d = pbp.validate({k: v for k, v in {
            "ticker": "KRW-TEST", "interval": "minute3", "maType": "ema", "ma60p": 3, "ma200p": 10,
            "pullbackP": 5, "slopeLB": 2, "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": False,
            "maxSplits": 5, "maxPullbackBuys": 3, "tp": 5, "sl": 90, "deadcross": True,
            "compounding": False, "capital": 1_000_000, "fee": 0.05}.items()})
        self.assertIs(d["enable_trading_hours"], False)
        self.make()
        self.assertFalse(self.strat.cfg["enable_trading_hours"])
        for i in range(3):
            self.assertFalse(self.strat._off_hours(ts_at(i)))
        self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)
        # 선택 4키가 하나도 없는 원 설정 dict(로더를 거치지 않음)도 꺼짐 — 하루 24시각 모두 시간 밖 아님
        st = make_strategy(None)
        self.assertFalse(st.cfg["enable_trading_hours"])
        for hh in range(24):
            self.assertFalse(st._off_hours(pd.Timestamp(f"2026-10-01 {hh:02d}:00", tz="UTC")))


# ================================================================ 재생 경로 = 실시간 경로 (BACKFILL·워밍업)
class TestReplayParity(unittest.TestCase):
    def test_replay_state_matches_live_off_hours(self):
        """주문을 내지 않는 재생(replay_bar)도 시간 밖 규칙을 같게 적용 → 판정 상태가 실시간(가상 보유)과 같다."""
        vals = [V(**DEAD), V(), V(), V(), V(), V(), V()]
        bars = [sbar(0), sbar(1), sbar(2, o=60, h=61, l=40, c=60), sbar(3, o=60, h=61, l=55, c=60),
                sbar(4, o=60, h=61, l=55, c=60), sbar(5, o=60, h=61, l=40, c=60), sbar(6)]
        win = hours("09:12", "02:00")   # 봉 0~2(마감 09:03~09:09) 밖, 봉 3 부터 안
        live = make_strategy(vals, **win)
        rep = make_strategy(vals, **win)
        keys = ("armed", "prev_golden", "entry_count", "pullback_count", "first_entry_reason", "pending_fill")
        signals = []
        for i, b in enumerate(bars):
            live.on_bar(b, {}, None, 0)
            rep.replay_bar(b, rep.indicators.update(b.close))
            self.assertEqual({k: getattr(live, k) for k in keys}, {k: getattr(rep, k) for k in keys}, b.ts)
            if live.last_eval.get("signal"):
                signals.append((i, live.last_eval["signal"], live.last_eval["reason"]))
            self.assertEqual(rep.last_eval.get("replay_signal"),
                             f"{live.last_eval['signal']}:{live.last_eval['reason']}" if live.last_eval.get("signal")
                             else None)
        # 시간 밖 골든(봉 1)은 놓침, 봉 2 눌림은 막힘 → 봉 3(열린 첫 봉)에서 눌림목 1회차
        self.assertEqual(signals[0], (3, "BUY", "PULLBACK"))
        self.assertEqual(rep.last_eval["failed_keys"], ["REPLAY"])

    def test_backfill_replay_off_hours_no_orders(self):
        """BACKFILL 재생(pullback_backfill)도 시간 밖 규칙 — 재생 뒤 armed·회차가 처음부터 넣은 것과 같다."""
        # 봉 9~18(마감 09:30~09:57) 시간 밖, 봉 19(마감 10:00)부터 안
        p = dict(hours("10:00", "09:30"), buyOnGoldenCross=False, tp=50)
        closes = [100.0 + i for i in range(30)]           # 오름세 → 감시 구간
        idx = [ts_at(i) for i in range(30)]
        df = pd.DataFrame({"Open": closes, "High": [c + 0.5 for c in closes], "Low": [c - 0.5 for c in closes],
                           "Close": closes, "Volume": [1.0] * 30}, index=pd.DatetimeIndex(idx))
        df.iloc[16, df.columns.get_loc("Low")] = 50.0    # 봉 16 눌림(시간 밖) → 막힘, armed 유지

        def fresh():
            st = make_strategy(None, **p)
            eng = SimpleNamespace(strategy=st, pullback_indicators=st.indicators, pullback_ring=st.ring,
                                  user_id="u1", ticker="KRW-TEST", interval_sec=180, bar_count=0, position=None)
            return st, eng

        st_a, eng_a = fresh()
        for ts, row in df.iterrows():
            sp.feed_confirmed_bar(eng_a, sp.bar_from_row(ts, row))
        st_b, eng_b = fresh()
        for ts, row in df.iterrows():
            sp.feed_confirmed_bar(eng_b, sp.bar_from_row(ts, row))
        res = sp.pullback_backfill(eng_b, first_ts=ts_at(12), series=df, until_ts=ts_at(29),
                                   audit_fn=lambda *a: None)
        self.assertTrue(res["restored"])
        keys = ("armed", "prev_golden", "entry_count", "pullback_count", "pending_fill", "first_entry_ts")
        self.assertEqual({k: getattr(st_a, k) for k in keys}, {k: getattr(st_b, k) for k in keys})
        # 시간 밖 봉 16 눌림은 막힘 → 열린 첫 봉 19 신호, 체결 = 봉 20 시가(가상)
        self.assertEqual((st_a.entry_count, st_a.first_entry_ts), (1, ts_at(20)))


# ================================================================ 감사 칸·용어
class TestAuditLabel(unittest.TestCase):
    def test_off_hours_label_in_terminology(self):
        from services.terminology import PULLBACK_STATE_LABEL, pullback_eval_text
        self.assertIn("OFF_HOURS", PULLBACK_STATE_LABEL)
        txt = pullback_eval_text(["OFF_HOURS"], {"round": 0, "blocked_signal": "BUY:PULLBACK"})
        self.assertIn("거래 시간 밖", txt)
        self.assertIn("눌림목 매수", txt)
        txt = pullback_eval_text(["OFF_HOURS"], {"round": 1, "blocked_signal": "SELL:TP"})
        self.assertIn("거래 시간 밖", txt)
        self.assertIn("익절", txt)
        doc = (ROOT / "docs/operations/terminology.md").read_text(encoding="utf-8")
        self.assertIn("`OFF_HOURS`", doc)

    def test_audit_view_off_hours_key(self):
        st = make_strategy([V(**DEAD), V()], **OPEN_AT_BAR2)
        st.on_bar(sbar(0), {}, None, 0)
        st.on_bar(sbar(1, o=60, h=61, l=40, c=60), {}, None, 0)   # 시간 밖 눌림 → 막음
        failed, checks = st.audit_view()
        self.assertEqual(failed, ["OFF_HOURS"])
        self.assertEqual(checks["off_hours"], 1)
        self.assertEqual(checks["armed"], 1)
        self.assertIsNone(checks["buy_reason"])

    def test_off_hours_no_signal_keeps_wait_key(self):
        """시간 밖이라도 막힌 신호가 없는 봉은 원래 대기 사유 + checks.off_hours=1 (막힌 매수만 OFF_HOURS)."""
        st = make_strategy([V(), V()], **OPEN_AT_BAR2)
        st.on_bar(sbar(0), {}, None, 0)                            # 골든 전환(시간 밖) → 놓침
        self.assertEqual(st.audit_view()[1]["blocked_signal"], "BUY:GOLDEN")
        st.on_bar(sbar(1, o=60, h=61, l=55, c=60), {}, None, 0)   # 신호 없음
        failed, checks = st.audit_view()
        self.assertEqual(failed, ["WAIT_PULLBACK"])
        self.assertEqual(checks["off_hours"], 1)


if __name__ == "__main__":
    unittest.main()
