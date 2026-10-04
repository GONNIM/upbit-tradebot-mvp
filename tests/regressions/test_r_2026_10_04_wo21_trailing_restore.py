"""
✅ WO-21 회귀: 재시작 때 trailing 상태(무장·최고가·고정폭·활성화 가격)를 봉 종가로 다시 계산 (2026-10-04)

원 결함/위험 (조사 보고 docs/plans/2026-10-04-wo21-trailing-persist/report.md):
- trailing 상태는 PositionState 메모리에만 있고, 재시작 복원(boot_seed / wallet_sync)은 apply_entry 로 초기화한다.
  보유 중 재시작이면 수익이 익절 기준에 다시 닿을 때까지 trailing 매도가 나오지 않는다.
- 정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다 → 예방 조치.
- audit_sell_eval.ts_armed 가 항상 0 으로 기록되었다 (strategy_engine 3곳 False 고정).

처방 (나): core/trailing_restore.py — 마지막 BUY 뒤 확정 봉 종가를 TrailingStopFilter.advance_state 와
PositionState.update_highest_price 로 재생. 실데이터 봉은 Upbit 공개 캔들 조회 결과를 tests/regressions/fixtures/
wo21_jto_5m_*.json 로 고정 (네트워크 비의존).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_04_wo21_trailing_restore -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures"
KST = ZoneInfo("Asia/Seoul")
T = "KRW-JTO"


def _df_from_fixture(name):
    d = json.load(open(FIX / name, encoding="utf-8"))
    idx = pd.DatetimeIndex([pd.Timestamp(b["ts_kst"]).tz_convert("UTC") for b in d["bars"]])
    return pd.DataFrame({"Close": [float(b["close"]) for b in d["bars"]]}, index=idx)


def _df(start_kst, closes, step_min=5):
    t0 = pd.Timestamp(start_kst).tz_convert("UTC")
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=step_min * i) for i in range(len(closes))])
    return pd.DataFrame({"Close": [float(c) for c in closes]}, index=idx)


def _filter(tp, ts=0.30, fixed=True):
    from core.filters.sell_filters import TrailingStopFilter
    f = TrailingStopFilter(trailing_stop_pct=ts, take_profit_pct=tp, use_fixed_mode=fixed)
    f.set_enabled(True)
    return f


def _strategy(f, min_hold=1):
    return SimpleNamespace(sell_filter_manager=SimpleNamespace(filters=[f]), min_holding_period=min_hold)


def _position(avg, qty=100.0, entry_ts="2026-10-02T08:00:14+09:00", source="boot_seed"):
    from core.position_state import PositionState
    p = PositionState()
    p.apply_entry(qty=qty, avg_price=avg, entry_bar=330, entry_ts=datetime.fromisoformat(entry_ts), source=source)
    return p


def _state(p):
    r = lambda v: None if v is None else round(float(v), 6)
    return (bool(p.trailing_armed), r(p.highest_price), r(p.trailing_fixed_amount), r(p.trailing_activation_price))


def _restore(p, f, df, buy_ts, now_kst, interval_sec=300, reason="EMA_GC", fetch=None, min_hold=1):
    from core.trailing_restore import restore_trailing_on_boot
    return restore_trailing_on_boot(
        p, _strategy(f, min_hold), user_id="u", ticker=T, timeframe="minute5", interval_sec=interval_sec,
        warmup_df=df, now=pd.Timestamp(now_kst), last_buy={"timestamp": buy_ts, "reason": reason, "price": p.avg_price},
        fetch=fetch,
    )


class TestWo21TrailingRestore(unittest.TestCase):

    def setUp(self):
        # 시험은 네트워크에 의존하지 않는다: 기본 REST 조회가 불리면 실패
        self._net = patch("core.rest_reconcile.safe_fetch_rest",
                          MagicMock(side_effect=AssertionError("시험 중 실제 REST 조회 금지")))
        self._net.start()

    def tearDown(self):
        self._net.stop()

    def test_1_synthetic_replay_equals_realtime(self):
        """(1) 합성 종가 열: 실시간 경로(update_highest_price → evaluate)와 재계산 결과가 봉마다 같다.
        구간: 무장 전(100.5·101.0) → 무장(102) → 무장 뒤 하락(101.8·101.6) → 신고가(103) → 하락(102.7)."""
        from core.trailing_restore import replay_trailing
        closes = [100.5, 101.0, 102.0, 101.8, 101.6, 103.0, 102.7]
        live, f_live = _position(100.0), _filter(0.015)
        for k in range(1, len(closes) + 1):
            c = closes[k - 1]
            live.update_highest_price(c)                       # strategy_incremental SELL 블록
            f_live.evaluate(position=live, current_price=c)    # 필터 (STEP 3 판정은 상태를 바꾸지 않음)
            replay = _position(100.0)
            n = replay_trailing(replay, _filter(0.015), [(None, x) for x in closes[:k]], 1)
            self.assertEqual(n, k)
            self.assertEqual(_state(replay), _state(live), f"봉 {k} ({c}) 에서 불일치")
        self.assertEqual(_state(live), (True, 103.0, 0.6, 102.0))

    def test_2_real_A_20261002(self):
        """(2) 실데이터 A: 10-02 08:00:14 봇 매수(734) ~ 09:30 매도. 무장은 09:15:11 실시간 평가(BACKFILL 없음).
        스냅샷은 봉 평가 직전 기록 → 09:20:11 스냅샷 = 09:10 봉까지, 09:30:11 = 09:20 봉까지.
        invariant_snapshots: 09:20:11 armed=1 peak 747 / 09:30:11 armed=1 peak 747. journal 고정폭 ₩13 × 30%."""
        df = _df_from_fixture("wo21_jto_5m_20261002.json")
        buy = "2026-10-02T08:00:14.048381+09:00"
        for now, expect in (("2026-10-02T09:19:59+09:00", (True, 747.0, 3.9, 747.0)),
                            ("2026-10-02T09:29:59+09:00", (True, 747.0, 3.9, 747.0))):
            p = _position(734.0)
            with self.assertLogs("core.trailing_restore", level="INFO") as cm:
                r = _restore(p, _filter(0.015), df, buy, now)
            self.assertEqual(r["status"], "restored")
            self.assertEqual(_state(p), expect, now)
            self.assertTrue(any("[TRAILING-RESTORE] armed=True peak=747.0000 fixed=3.9000 activation=747.0000" in m
                                and f"시작={buy}" in m for m in cm.output))

    def test_3_real_B_20260930_no_pre_buy_bars(self):
        """(3) 실데이터 B: 09-30 16:47:09 앱 매수(761) 포지션을 19:44:28 재시작 시점에서 재계산 → 미무장.
        매수 뒤 5분봉 종가 최고 762(+0.13%) < 익절 기준 1.0% (당시 설정). 시작점(마지막 BUY) 이전 봉은 쓰지 않는다.
        09-30 19:25 스냅샷 armed=1·peak 774 는 BACKFILL 결함(WO-13/14)으로 매수 전 봉(09-29 18:50 종가 772)이
        재평가된 오염값이다 — 그 값을 재현하지 않는 것이 맞다. (구 코드와 결과 상태가 같아도 된다)"""
        df = _df_from_fixture("wo21_jto_5m_20260930.json")
        p = _position(761.0, entry_ts="2026-09-30T19:44:40+09:00", source="wallet_sync")
        r = _restore(p, _filter(0.010), df, "2026-09-30T16:47:09.091707+09:00", "2026-09-30T19:44:28+09:00",
                     reason="HTS_BUY")
        self.assertEqual(r["status"], "restored")
        self.assertEqual(_state(p), (False, 761.0, None, None))
        self.assertEqual(r["bars"], 35)   # 16:45 ~ 19:35 봉 35개 (마감 > 16:47:09, 마감 ≤ 19:44:28)

    def test_3c_real_C_20261003(self):
        """(3-C) 실데이터 C: 10-03 09:18:47 앱 매수(710) → 20:05 TRAILING_STOP_FIXED 매도. 전 구간 5분봉.
        무장은 18:55:11 실시간 평가(BACKFILL·재시작 없음). invariant_snapshots: 19:00:11 armed=1 peak 722 (18:50 봉까지),
        20:05:11 armed=1 peak 734 (19:55 봉까지). journal 고정폭 ₩12 × 30%."""
        df = _df_from_fixture("wo21_jto_5m_20261003.json")
        buy = "2026-10-03T09:18:47.815714+09:00"
        for now, expect in (("2026-10-03T18:59:59+09:00", (True, 722.0, 3.6, 722.0)),
                            ("2026-10-03T20:04:59+09:00", (True, 734.0, 3.6, 722.0))):
            p = _position(710.0, entry_ts="2026-10-03T09:18:47+09:00", source="wallet_sync")
            r = _restore(p, _filter(0.015), df, buy, now, reason="HTS_BUY")
            self.assertEqual(r["status"], "restored")
            self.assertEqual(_state(p), expect, now)

    def test_4_hts_buy_add_uses_bars_after_add_and_wallet_avg(self):
        """(4) 앱 추가 매수가 섞인 포지션: 마지막 HTS_BUY_ADD 뒤 봉만 쓰고 평균가는 지갑 값(105)을 그대로 쓴다.
        추가 매수 전 고가(110)가 들어가면 무장되지만, 뒤 봉(105.5~106)만이면 미무장이어야 한다."""
        df = _df("2026-10-04T09:00:00+09:00", [100, 104, 110, 108, 105.5, 106, 105.8])  # 09:00 ~ 09:30
        p = _position(105.0)
        r = _restore(p, _filter(0.015), df, "2026-10-04T09:21:00+09:00", "2026-10-04T09:40:00+09:00",
                     reason="HTS_BUY_ADD")
        self.assertEqual(r["bars"], 3)     # 09:20(마감 09:25 > 09:21)·09:25·09:30
        self.assertEqual(p.avg_price, 105.0)
        self.assertEqual(_state(p), (False, 105.0, None, None))

    def test_5_rest_extra_fetch_limit_and_failure(self):
        """(5) 시작점이 워밍업 봉 밖: 추가 REST 1회(필요 봉 수·end_ts) → 계산. 10회(2000봉) 초과·조회 실패 → 초기화 + WARNING 1줄."""
        warm = _df("2026-10-02T10:00:00+09:00", [740, 741, 742])
        older = _df("2026-10-02T08:00:00+09:00", [735] * 9 + [747] + [745] * 14)   # 08:00 ~ 09:55 (24봉)
        fetch = MagicMock(return_value=older)
        p = _position(734.0)
        r = _restore(p, _filter(0.015), warm, "2026-10-02T08:00:14+09:00", "2026-10-02T10:15:30+09:00", fetch=fetch)
        fetch.assert_called_once()
        kw = fetch.call_args.kwargs
        self.assertEqual(kw["total_count"], 24)
        self.assertEqual(pd.Timestamp(kw["end_ts"]), pd.Timestamp("2026-10-02T09:55:00+09:00"))
        self.assertEqual((r["status"], r["extra"]), ("restored", 24))
        self.assertEqual(_state(p), (True, 747.0, 3.9, 747.0))

        for buy, ret, word in (("2026-09-25T00:00:00+09:00", older, "조회 한도 초과"),
                               ("2026-10-02T08:00:14+09:00", None, "REST 조회 실패")):
            fetch = MagicMock(return_value=ret)
            p = _position(734.0)
            p.trailing_armed, p.highest_price = True, 999.0   # 재계산 전 값이 남아 있어도 초기화되는지
            with self.assertLogs("core.trailing_restore", level="WARNING") as cm:
                r = _restore(p, _filter(0.015), warm, buy, "2026-10-02T10:15:30+09:00", fetch=fetch)
            self.assertEqual(r["status"], "reset")
            self.assertEqual(_state(p), (False, 734.0, None, None))
            self.assertEqual(len(cm.output), 1)
            self.assertIn("[TRAILING-RESTORE] 재계산 불가 → 초기화 | 사유=" + word, cm.output[0])
            if word == "조회 한도 초과":
                fetch.assert_not_called()

    def test_6_unconfirmed_last_bar_excluded(self):
        """(6) 끝의 미확정(형성 중) 봉은 제외: 형성 중 봉 종가(110)는 무장 조건이지만 마감 전이면 쓰지 않는다."""
        df = _df("2026-10-02T09:00:00+09:00", [100.5, 101, 110])   # 09:00, 09:05, 09:10(형성 중)
        p = _position(100.0)
        r = _restore(p, _filter(0.015), df, "2026-10-02T09:00:30+09:00", "2026-10-02T09:12:00+09:00")
        self.assertEqual((r["bars"], _state(p)), (2, (False, 100.0, None, None)))
        p2 = _position(100.0)
        r2 = _restore(p2, _filter(0.015), df, "2026-10-02T09:00:30+09:00", "2026-10-02T09:15:00+09:00")
        self.assertEqual((r2["bars"], _state(p2)[0]), (3, True))

    def test_7_audit_ts_armed_records_real_value(self):
        """(7) audit_sell_eval.ts_armed: 무장 봉 1(True), 비무장 봉 0(False). 구 코드는 항상 False."""
        from core.strategy_engine import StrategyEngine
        from core.strategy_incremental import Action
        from core.candle_buffer import Bar
        e = StrategyEngine.__new__(StrategyEngine)
        e.user_id, e.ticker, e.interval_sec, e.bar_count = "u", T, 300, 340
        e.strategy_type = "EMA"
        e.stop_loss, e.take_profit, e.trailing_stop_pct = 0.01, 0.015, 0.30
        e.strategy = MagicMock(enable_stale_position=False, last_sell_filter_result=None, last_sell_reason=None,
                               stop_loss=0.01, take_profit=0.015)
        e.position = _position(734.0)
        bar = Bar(ts=datetime(2026, 10, 2, 0, 15, tzinfo=timezone.utc), open=745, high=745, low=745, close=745,
                  volume=1.0, is_closed=True)
        ind = {"ema_fast": 736.0, "ema_slow": 734.0, "ema_base": 734.0, "prev_ema_fast": 735.9, "prev_ema_slow": 734.0}
        seen = []
        with patch("core.strategy_engine.insert_sell_eval", side_effect=lambda **kw: seen.append(kw["ts_armed"])), \
                patch("core.strategy_engine.estimate_bars_held_from_audit", return_value=3):
            e._record_audit_log(bar, ind, Action.HOLD)
            e.position.trailing_armed, e.position.highest_price = True, 747.0   # 무장 상태 (구 코드에도 있는 필드)
            e._record_audit_log(bar, ind, Action.HOLD)
        self.assertEqual(seen, [False, True])


if __name__ == "__main__":
    unittest.main()
