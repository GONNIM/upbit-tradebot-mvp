"""WO-2 재적용 회귀 (2026-09-02): 지연 상한(60초) 초과 시 취소."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder, PendingOrderQueue


def _make(ts, created, close=100.0):
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
        created_at=created,
    )


class TestMaxWaitExpired(unittest.TestCase):
    def test_is_expired_true_when_over_60_seconds(self):
        created = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        pending = _make(created, created)
        now = created + timedelta(seconds=61)
        self.assertTrue(pending.is_expired(now))

    def test_is_expired_false_within_60_seconds(self):
        created = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        pending = _make(created, created)
        now = created + timedelta(seconds=45)
        self.assertFalse(pending.is_expired(now))

    def test_cancel_current_records_reason_and_clears_queue(self):
        q = PendingOrderQueue()
        ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        q.register(_make(ts, ts))
        report = q.cancel_current(reason='MAX_WAIT_EXCEEDED', at=ts + timedelta(seconds=61))
        self.assertIsNotNone(report)
        self.assertEqual(report.reason, 'MAX_WAIT_EXCEEDED')
        self.assertTrue(q.is_empty())


if __name__ == '__main__':
    unittest.main()
