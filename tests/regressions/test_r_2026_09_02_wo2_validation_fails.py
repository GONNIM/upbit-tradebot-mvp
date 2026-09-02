"""WO-2 재적용 회귀 (2026-09-02): 확정 종가 재계산 시 유효성 불성립이면 취소."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder


def _make(ema_fast_prev, ema_slow_prev, close):
    return PendingOrder(
        bar_ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
        decision='BUY',
        signal_condition='EMA_GC',
        tentative_close=close,
        ema_fast_prev=ema_fast_prev,
        ema_slow_prev=ema_slow_prev,
        ema_fast_alpha=2 / 21,   # fast_buy = 20
        ema_slow_alpha=2 / 201,  # slow_buy = 200
        context={},
        created_at=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
    )


class TestValidationFails(unittest.TestCase):
    def test_confirmed_close_drops_signal_inverts(self):
        """평가 시점에는 golden cross 였는데 확정 종가가 크게 낮으면 신호 반전."""
        # ema_fast_prev 가 ema_slow_prev 보다 살짝 위 (평가 시점 근접)
        # 확정 종가가 매우 낮게 오면 fast_alpha 가 크므로 fast 가 slow 아래로 떨어진다.
        pending = _make(ema_fast_prev=100.05, ema_slow_prev=100.0, close=100.5)
        # 확정 종가 80: fast_new ≈ 100.05 + (2/21)*(80-100.05) ≈ 100.05 - 1.91 ≈ 98.14
        #               slow_new ≈ 100.0  + (2/201)*(80-100.0)  ≈ 100.0  - 0.199 ≈ 99.80
        # → fast(98.14) < slow(99.80) : 불성립
        self.assertFalse(pending.revalidate(confirmed_close=80.0))

    def test_unknown_signal_condition_raises(self):
        pending = PendingOrder(
            bar_ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
            decision='BUY',
            signal_condition='UNKNOWN',
            tentative_close=100.0,
            ema_fast_prev=99.5,
            ema_slow_prev=99.0,
            ema_fast_alpha=0.1,
            ema_slow_alpha=0.01,
            context={},
            created_at=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            pending.revalidate(confirmed_close=100.0)


if __name__ == '__main__':
    unittest.main()
