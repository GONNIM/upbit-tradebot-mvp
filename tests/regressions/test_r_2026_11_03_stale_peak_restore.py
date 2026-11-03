"""
✅ 1102-02 회귀: 재시작 때 정체 판정용 최고가(highest_since_entry)를 진입 시각 뒤 확정 봉 종가로 다시 잡기 (2026-11-03)

틈 (1102-01 계획 F13, 코드 읽기로 찾음 — 관측 사례 없음): 재시작 복원(apply_entry)이 highest_since_entry 를 평단으로
초기화해, 정체 시간이 지난 보유 중 재시작하면 이미 목표 수익을 넘긴 적이 있어도 첫 봉에서 정체 매도될 수 있었다.
처방: core/trailing_restore.restore_stale_peak_on_boot — 워밍업 봉에서 position.entry_ts 뒤 확정 봉 종가 최댓값(평단 이상).
restore_trailing_on_boot 맨 앞에서 부른다(live_loop 무변경).

실행 (게이트 안에서): python3 -m unittest tests.regressions.test_r_2026_11_03_stale_peak_restore -v
바깥 연결 없음.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

KST = ZoneInfo("Asia/Seoul")
STEP = 180
NOW = datetime(2026, 11, 3, 15, 0, 30, tzinfo=KST)


def _df(start_kst: datetime, closes):
    t0 = pd.Timestamp(start_kst).tz_convert("UTC")
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(seconds=STEP * i) for i in range(len(closes))])
    return pd.DataFrame({"Close": [float(c) for c in closes]}, index=idx)


def _pos(avg=509.0, entry_ts=datetime(2026, 11, 3, 2, 51, 12, tzinfo=KST)):
    from core.position_state import PositionState
    p = PositionState()
    p.apply_entry(qty=500.0, avg_price=avg, entry_bar=10, entry_ts=entry_ts, source="boot_seed")
    return p


def _stale(p, price, at=NOW):
    from core.filters.sell_filters import StalePositionFilter
    return StalePositionFilter(stale_hours=3.0, stale_threshold_pct=0.003).evaluate(
        position=p, current_price=price, current_time=at).reason


class TestStalePeakRestore(unittest.TestCase):

    def test_s1_peak_restored_prevents_restart_stale_sell(self):
        """S1: 진입 뒤 511 까지 오른 적 있는 보유 — 재계산하면 정체 매도 아님. 재계산 전(평단)은 매도(재현)."""
        from core.trailing_restore import restore_stale_peak_on_boot
        df = _df(datetime(2026, 11, 3, 0, 0, tzinfo=KST), [505.0] * 60 + [511.0] + [507.0] * 140)
        old = _pos()
        self.assertEqual(old.highest_since_entry, 509.0)
        self.assertEqual(_stale(old, 506.0), "STALE_POSITION")

        p = _pos()
        r = restore_stale_peak_on_boot(p, interval_sec=STEP, warmup_df=df, now=NOW)
        self.assertEqual(r["status"], "restored")
        self.assertEqual(p.highest_since_entry, 511.0)
        self.assertFalse(r["partial"])
        self.assertEqual(_stale(p, 506.0), "STALE_OK")

    def test_s2_never_reached_target_still_stale(self):
        """S2: 진입 뒤 평단을 넘은 적이 없으면 최고가 = 평단, 정체 매도 그대로(기능 유지)."""
        from core.trailing_restore import restore_stale_peak_on_boot
        df = _df(datetime(2026, 11, 3, 0, 0, tzinfo=KST), [505.0] * 200)
        p = _pos()
        restore_stale_peak_on_boot(p, interval_sec=STEP, warmup_df=df, now=NOW)
        self.assertEqual(p.highest_since_entry, 509.0)
        self.assertEqual(_stale(p, 506.0), "STALE_POSITION")

    def test_s3_bars_before_entry_and_unconfirmed_bar_ignored(self):
        """S3: 진입 전 봉·형성 중 봉(마감 > 지금)은 넣지 않음."""
        from core.trailing_restore import restore_stale_peak_on_boot
        entry = datetime(2026, 11, 3, 14, 0, 10, tzinfo=KST)
        # 13:54·13:57 봉(마감 ≤ 진입) 은 600, 14:00~14:57 봉 은 510, 15:00 봉(형성 중) 은 700
        df = _df(datetime(2026, 11, 3, 13, 54, tzinfo=KST), [600.0, 600.0] + [510.0] * 20 + [700.0])
        p = _pos(entry_ts=entry)
        r = restore_stale_peak_on_boot(p, interval_sec=STEP, warmup_df=df, now=NOW)
        self.assertEqual(p.highest_since_entry, 510.0)
        self.assertEqual(r["bars"], 20)   # 13:54(마감 13:57)·13:57(마감 14:00) ≤ 진입 → 제외, 15:00(마감 15:03 > 지금) 제외

    def test_s4_partial_when_entry_before_warmup(self):
        """S4: 진입이 워밍업 첫 봉보다 앞 — 있는 봉만으로 잡고 partial=True, 평단보다 작아지지 않음."""
        from core.trailing_restore import restore_stale_peak_on_boot
        df = _df(datetime(2026, 11, 3, 10, 0, tzinfo=KST), [500.0] * 50)
        p = _pos(entry_ts=datetime(2026, 11, 2, 20, 0, tzinfo=KST))
        r = restore_stale_peak_on_boot(p, interval_sec=STEP, warmup_df=df, now=NOW)
        self.assertTrue(r["partial"])
        self.assertEqual(p.highest_since_entry, 509.0)

    def test_s5_skip_without_avg_or_entry_or_position(self):
        from core.trailing_restore import restore_stale_peak_on_boot
        from core.position_state import PositionState
        df = _df(datetime(2026, 11, 3, 0, 0, tzinfo=KST), [600.0] * 10)
        self.assertEqual(restore_stale_peak_on_boot(PositionState(), interval_sec=STEP, warmup_df=df, now=NOW)["status"], "skip")
        p = _pos()
        p.entry_ts = None
        p.highest_since_entry = 509.0
        self.assertEqual(restore_stale_peak_on_boot(p, interval_sec=STEP, warmup_df=df, now=NOW)["status"], "skip")
        self.assertEqual(p.highest_since_entry, 509.0)
        r = restore_stale_peak_on_boot(_pos(), interval_sec=STEP, warmup_df=None, now=NOW)
        self.assertTrue(r["partial"])

    def test_s6_called_from_trailing_restore_even_without_trailing_filter(self):
        """S6: restore_trailing_on_boot 맨 앞에서 부름 — trailing 필터가 없어 trailing 은 초기화돼도 정체 최고가는 잡힘."""
        from core.trailing_restore import restore_trailing_on_boot
        df = _df(datetime(2026, 11, 3, 0, 0, tzinfo=KST), [505.0] * 60 + [511.0] + [507.0] * 140)
        p = _pos()
        strat = SimpleNamespace(sell_filter_manager=SimpleNamespace(filters=[]), min_holding_period=1)
        r = restore_trailing_on_boot(p, strat, user_id="u", ticker="KRW-JTO", timeframe="minute3",
                                     interval_sec=STEP, warmup_df=df, now=NOW, last_buy={"timestamp": None})
        self.assertEqual(r["status"], "reset")
        self.assertEqual(p.highest_since_entry, 511.0)
        self.assertEqual(p.highest_price, 509.0)   # trailing 은 초기 상태(평단)

    def test_s7_stale_peak_exception_does_not_block_trailing(self):
        """S7: 정체 최고가 재계산이 예외여도 trailing 복원은 그대로 진행."""
        from core import trailing_restore as tr
        p = _pos()
        strat = SimpleNamespace(sell_filter_manager=SimpleNamespace(filters=[]), min_holding_period=1)
        with patch.object(tr, "restore_stale_peak_on_boot", side_effect=RuntimeError("boom")), \
                self.assertLogs("core.trailing_restore", level="WARNING") as cm:
            r = tr.restore_trailing_on_boot(p, strat, user_id="u", ticker="KRW-JTO", timeframe="minute3",
                                            interval_sec=STEP, warmup_df=None, now=NOW, last_buy={"timestamp": None})
        self.assertEqual(r["status"], "reset")
        self.assertTrue(any("[STALE-PEAK]" in m for m in cm.output))
        self.assertEqual(p.highest_since_entry, 509.0)


if __name__ == "__main__":
    unittest.main()
