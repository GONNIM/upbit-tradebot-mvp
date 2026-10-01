"""
✅ WO-16 (V) 회귀: reconcile_series 결과 시각 순 정렬 (2026-10-01)

원 결함 (WO-16 사전 측정 precheck §4):
- reconcile_series 가 `merged.loc[ts] = …` 로 새 시각을 끝에 덧붙이고 정렬하지 않음.
- VERIFY 대상 `local_series.tail(200)` 이 "최근 봉 + 덧붙은 봉" 을 고르고 범위가 역전
  (2026-09-25 12:50:34 range=09-25 03:45 ~ 09-24 19:50, 93봉 건너뜀).
- (R) 로 VERIFY 첫 배치가 end_ts=timestamps[-1] 을 따르면 정렬 깨짐 시 조회가 과거에서 끝나 최신 봉을 건너뜀.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo16v_reconcile_sorted -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.rest_reconcile import reconcile_series  # noqa: E402

STEP = pd.Timedelta(minutes=5)


def _bars(start_utc: str, n: int) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(start_utc, tz="UTC"), periods=n, freq="5min")
    close = [700.0 + (int(t.timestamp()) // 300) % 9 for t in idx]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1.0}, index=idx)


class TestReconcileSorted(unittest.TestCase):

    def setUp(self):
        self.full = _bars("2026-09-30 00:00", 300)
        self.closed = self.full.index[-1]

    def _verify_targets(self, local):
        """engine/live_loop.py VERIFY 대상 선정과 같은 식."""
        past = local[local.index < self.closed]
        return past.tail(min(200, len(past))).index.tolist()

    def test_1_inserted_older_bars_sorted(self):
        """로컬 시작 이전 봉(옛 WO-13 (b) 경우)을 넣어도 결과가 시각 순, VERIFY 범위 양끝 정상."""
        local = self.full.iloc[100:]          # 로컬 200봉
        rest = self.full                      # REST 가 그 이전 100봉까지 줌
        merged, _ = reconcile_series(local, rest)
        self.assertTrue(merged.index.is_monotonic_increasing)
        ts = self._verify_targets(merged)
        self.assertLess(ts[0], ts[-1])
        self.assertEqual(ts[-1], self.closed - STEP)
        self.assertEqual(ts, list(self.full.index[-201:-1]))     # 최근 200봉
        self.assertEqual(merged.index[0], self.full.index[0])    # 로컬 시작 = 가장 이른 봉

    def test_2_filled_missing_bars_inside_range_sorted(self):
        """로컬 범위 안 진짜 누락 봉(장애 뒤 메움)도 제자리로 정렬."""
        holes = self.full.index[[150, 151, 152, 260]]
        local = self.full.drop(index=holes)
        merged, diff = reconcile_series(local, self.full)
        self.assertEqual(sorted(diff["changed_ts"]), list(holes))
        self.assertTrue(merged.index.is_monotonic_increasing)
        self.assertEqual(list(merged.index), list(self.full.index))
        self.assertEqual(merged.tail(500).index[-1], self.closed)   # tail(500) 이 최신 봉 유지

    def test_3_unsorted_reproduced_without_sort(self):
        """(대조) 정렬하지 않으면 덧붙은 봉이 끝에 남아 VERIFY 범위가 역전 — 결함 재현."""
        local = self.full.iloc[100:]
        merged = local.copy()
        for t in self.full.index:
            merged.loc[t] = self.full.loc[t]
        self.assertFalse(merged.index.is_monotonic_increasing)
        past = merged[merged.index < self.closed]
        ts = past.tail(200).index.tolist()
        self.assertGreater(ts[0], ts[-1])


if __name__ == "__main__":
    unittest.main()
