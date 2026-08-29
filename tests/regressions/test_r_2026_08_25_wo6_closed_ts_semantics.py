"""WO-6 회귀 테스트 — get_closed_ts 반환값 의미 재정의 확인.

배경:
    2026-08-25 WO-6 개편 전에는 get_closed_ts 가 "현재 시각을 봉 간격으로 내림한
    값"(즉 진행 중 봉의 시작 시각)을 반환했다. 이는 함수명과 달라 오프바이원
    결함의 근원이었고, WO-2 v3 3차 배포 실패 모두 이 문제와 연관됐다.

    WO-6 개편 후에는 "방금 확정된 봉의 시작 시각"(진행 중 봉의 이전 봉 시작
    시각)을 반환한다. 이 값은 Upbit REST API 가 반환하는 봉 시각과 일치한다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_25_wo6_closed_ts_semantics -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.candle_clock import CandleClock


class TestGetClosedTsSemantics(unittest.TestCase):
    """WO-6: get_closed_ts 는 방금 확정된 봉의 시작 시각을 반환해야 한다."""

    def test_minute1_returns_previous_bar_start(self):
        clock = CandleClock("minute1")
        now = datetime(2026, 8, 25, 9, 5, 42, tzinfo=timezone.utc)
        # 09:05:42 → boundary 09:05:00 → closed 09:04:00 (방금 확정된 봉)
        closed = clock.get_closed_ts(now)
        expected = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(closed, expected)

    def test_minute1_exact_boundary_returns_previous_bar(self):
        """봉 경계 시각에도 이전 봉이 확정된 봉이다."""
        clock = CandleClock("minute1")
        now = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)
        closed = clock.get_closed_ts(now)
        expected = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(closed, expected)

    def test_minute3_returns_previous_bar_start(self):
        clock = CandleClock("minute3")
        now = datetime(2026, 8, 25, 9, 7, 30, tzinfo=timezone.utc)
        # 3분봉 경계: 09:06:00 → closed = 09:03:00 (이전 봉)
        closed = clock.get_closed_ts(now)
        expected = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(closed, expected)

    def test_returned_value_matches_upbit_previous_bar(self):
        """반환값은 Upbit REST API 의 봉 시작 시각과 개념 일치한다.

        Upbit 봉 시각은 봉의 시작을 나타내며, 09:05:00 시점에 완료된 봉은
        09:04:00 시각의 봉이다.
        """
        clock = CandleClock("minute1")
        for second in [1, 15, 30, 45, 59]:
            now = datetime(2026, 8, 25, 9, 5, second, tzinfo=timezone.utc)
            closed = clock.get_closed_ts(now)
            # 어떤 초에 호출되든 09:04:00 이 반환되어야 함
            self.assertEqual(
                closed,
                datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc),
                f"9:5:{second} 시점 closed_ts 오류: {closed}",
            )


if __name__ == "__main__":
    unittest.main()
