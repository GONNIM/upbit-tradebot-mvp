"""WO-2 재적용 회귀 (2026-09-02, 보정 2): 대기 매수는 한 번에 1건만 유지한다.

새 매수 결정이 도착하면 기존 항목을 SUPERSEDED 사유로 취소하고 새 결정으로
교체한다. 더 최신 정보로 내린 결정이 우선이라는 정책의 회귀 테스트.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder, PendingOrderQueue


def _make(ts, close=100.0):
    return PendingOrder(
        bar_ts=ts,
        decision='BUY',
        signal_condition='EMA_GC',
        tentative_close=close,
        ema_fast_prev=99.5,
        ema_slow_prev=99.0,
        ema_fast_alpha=2 / 21,
        ema_slow_alpha=2 / 201,
        context={},
        created_at=ts,
    )


class TestSupersededReplacement(unittest.TestCase):
    def test_second_register_returns_supersede_report(self):
        q = PendingOrderQueue()
        first_ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        second_ts = first_ts + timedelta(minutes=1)
        q.register(_make(first_ts))
        report = q.register(_make(second_ts))
        self.assertIsNotNone(report)
        self.assertEqual(report.reason, 'SUPERSEDED')
        self.assertEqual(report.bar_ts, first_ts)
        # 큐에는 두 번째 결정만 남는다
        self.assertEqual(q.current.bar_ts, second_ts)
        self.assertFalse(q.is_empty())

    def test_supersede_report_appears_in_drain(self):
        q = PendingOrderQueue()
        first_ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        second_ts = first_ts + timedelta(minutes=1)
        q.register(_make(first_ts))
        q.register(_make(second_ts))
        cancelled = q.drain_cancelled()
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0].reason, 'SUPERSEDED')
        # drain 이후에는 비어야 한다
        self.assertEqual(q.drain_cancelled(), [])


if __name__ == '__main__':
    unittest.main()
