"""WO-2 재적용 회귀 (2026-09-02): 유효성 확인은 판단이 아니므로 봉당 1회 원칙을
깨지 않는다.

_resolve_pending_buy 는 이전 봉의 대기 항목을 처리하는 별도 훅이며,
_register_evaluated_bar 를 호출하지 않는다. 이로써 같은 봉에 대해 감사 행이
1건만 유지된다.
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder, PendingOrderQueue


class TestOneEvaluationPerBarWithPending(unittest.TestCase):
    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub'
        engine.ticker = 'KRW-JTO'
        engine._evaluated_bar_ts = OrderedDict()
        engine._pending_orders = PendingOrderQueue()
        engine.buffer = MagicMock()
        engine._execute_buy = MagicMock()
        return engine

    def test_resolve_hook_does_not_register_evaluated_bar(self):
        """재판정 훅이 _register_evaluated_bar 를 호출하지 않는지 확인."""
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()
        engine._register_evaluated_bar = MagicMock()

        # 이전 봉의 대기 매수 등록
        prev_ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        engine._pending_orders.register(PendingOrder(
            bar_ts=prev_ts,
            decision='BUY',
            signal_condition='EMA_GC',
            tentative_close=100.0,
            ema_fast_prev=99.5,
            ema_slow_prev=99.0,
            ema_fast_alpha=2 / 21,
            ema_slow_alpha=2 / 201,
            context={'ind_ema_fast': 99.5, 'ind_ema_slow': 99.0},
            created_at=prev_ts,
        ))

        # 새 봉이 재판정 훅에 진입 (다른 봉 시각)
        new_ts = datetime(2026, 9, 2, 10, 1, 0, tzinfo=timezone.utc)
        new_bar = Bar(
            ts=new_ts, open=100, high=100, low=100, close=100, volume=1,
            is_closed=True, is_confirmed=True,
        )

        # buffer 에 이전 봉의 확정 종가가 존재하도록 mock
        prev_bar = Bar(
            ts=prev_ts, open=100, high=100, low=100, close=101, volume=1,
            is_closed=True, is_confirmed=True,
        )
        engine.buffer = [prev_bar]

        # _audit_wo2_resolution 는 DB 접근이므로 우회
        engine._audit_wo2_resolution = MagicMock()

        StrategyEngine._resolve_pending_buy(engine, new_bar)

        # 유효성 통과·불통과 무관하게 _register_evaluated_bar 는 호출되면 안 된다
        engine._register_evaluated_bar.assert_not_called()

    def test_resolve_hook_skips_when_same_bar_as_pending(self):
        """대기 봉과 같은 봉이면 재판정 대상이 아니다."""
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()

        ts = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        engine._pending_orders.register(PendingOrder(
            bar_ts=ts,
            decision='BUY',
            signal_condition='EMA_GC',
            tentative_close=100.0,
            ema_fast_prev=99.5,
            ema_slow_prev=99.0,
            ema_fast_alpha=2 / 21,
            ema_slow_alpha=2 / 201,
            context={},
            created_at=ts,
        ))
        same_bar = Bar(
            ts=ts, open=100, high=100, low=100, close=100, volume=1,
            is_closed=True, is_confirmed=True,
        )
        engine._audit_wo2_resolution = MagicMock()
        StrategyEngine._resolve_pending_buy(engine, same_bar)
        # 큐가 그대로 유지 (재판정 안 함)
        self.assertFalse(engine._pending_orders.is_empty())
        self.assertEqual(engine._pending_orders.current.bar_ts, ts)


if __name__ == '__main__':
    unittest.main()
