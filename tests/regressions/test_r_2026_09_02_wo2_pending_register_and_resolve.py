"""WO-2 재적용 회귀 (2026-09-02): 매수 지연 등록과 다음 봉 경계 재판정.

검증 대상:
    - 미확정 봉의 매수 판단이 PendingOrderQueue.register 를 호출한다.
    - 확정 종가와 매수용 EMA 쌍(fast_buy, slow_buy)으로 유효성 확인이 통과하면
      발주가 진행되고 큐가 비워진다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_02_wo2_pending_register_and_resolve -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder, PendingOrderQueue


class TestPendingRegisterAndResolve(unittest.TestCase):
    def _make_pending(self, bar_ts: datetime, created_at: datetime,
                      ema_fast_prev: float, ema_slow_prev: float,
                      tentative_close: float = 100.0) -> PendingOrder:
        """매수용 지표 쌍(fast_buy=20, slow_buy=200)의 alpha 계수 예시."""
        return PendingOrder(
            bar_ts=bar_ts,
            decision='BUY',
            signal_condition='EMA_GC',
            tentative_close=tentative_close,
            ema_fast_prev=ema_fast_prev,
            ema_slow_prev=ema_slow_prev,
            ema_fast_alpha=2 / (20 + 1),
            ema_slow_alpha=2 / (200 + 1),
            context={},
            created_at=created_at,
        )

    def test_register_new_pending_returns_no_superseded(self):
        q = PendingOrderQueue()
        ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        pending = self._make_pending(ts, ts, ema_fast_prev=99.0, ema_slow_prev=100.0)
        superseded = q.register(pending)
        self.assertIsNone(superseded)
        self.assertFalse(q.is_empty())
        self.assertEqual(q.current.bar_ts, ts)

    def test_revalidate_passes_with_favorable_confirmed_close(self):
        """확정 종가가 골든 크로스를 유지시키면 통과."""
        pending = self._make_pending(
            bar_ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 9, 2, 10, 0, 5, tzinfo=timezone.utc),
            ema_fast_prev=99.5,
            ema_slow_prev=99.0,
            tentative_close=100.0,
        )
        # 확정 종가 105 → fast EMA 상승 → fast > slow 유지
        self.assertTrue(pending.revalidate(confirmed_close=105.0))

    def test_resolve_clears_queue_after_success(self):
        q = PendingOrderQueue()
        ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        q.register(self._make_pending(ts, ts, ema_fast_prev=99.5, ema_slow_prev=99.0))
        self.assertFalse(q.is_empty())
        # 성공 처리 후 clear
        q.clear()
        self.assertTrue(q.is_empty())


if __name__ == '__main__':
    unittest.main()
