"""WO-2 재적용 회귀 (2026-09-02): 보호성 매도가 지연 큐를 우회해 즉시 집행.

두 케이스를 함께 검증한다.
    1) 매도 판단 시 PendingOrderQueue.register 를 호출하지 않는다 (매도는 큐 자체가 없음).
    2) 대기 매수가 등록된 상태에서도 매도 판단은 execute() 안에서 즉시 _execute_sell
       로 진행되며 pending_order 존재 검사에 걸리지 않는다.
       (보정 1: pending_order 검사를 매수 분기 안으로 이동한 결과)
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrder, PendingOrderQueue
from core.strategy_action import Action


class TestSellCannotEnterQueue(unittest.TestCase):
    def test_register_sell_raises_value_error(self):
        q = PendingOrderQueue()
        sell_order = PendingOrder(
            bar_ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
            decision='SELL',  # 금지
            signal_condition='EMA_DC',
            tentative_close=100.0,
            ema_fast_prev=99.0,
            ema_slow_prev=99.5,
            ema_fast_alpha=2 / 21,
            ema_slow_alpha=2 / 201,
            context={},
            created_at=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            q.register(sell_order)


class TestSellImmediateWhilePendingBuyExists(unittest.TestCase):
    """대기 매수가 등록된 상태에서 매도 판단이 즉시 집행되어야 한다.

    execute() 함수는 pending_order 존재 검사를 매수 분기 안에서만 수행하므로,
    매도는 이 검사를 건너뛴다. 보정 1의 핵심 검증.
    """

    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub_user'
        engine.ticker = 'KRW-JTO'
        engine.bar_count = 0
        engine.strategy_type = 'EMA'
        engine.indicators = MagicMock()
        engine.indicators.state_polluted = False
        engine.position = MagicMock()
        engine.position.pending_order = True  # 대기 매수 등록 상황
        engine.trader = MagicMock()
        engine._pending_orders = PendingOrderQueue()
        engine._execute_buy_or_defer = MagicMock()
        engine._execute_sell = MagicMock()
        return engine

    def test_sell_action_bypasses_pending_order_gate(self):
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()
        bar = Bar(
            ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
            open=100, high=100, low=100, close=100, volume=1.0,
            is_closed=True, is_confirmed=True,
        )
        indicators = {'ema_fast': 99.0, 'ema_slow': 100.0}
        # PAUSE-1 우회
        with patch('core.strategy_engine.get_trading_paused', return_value=False):
            StrategyEngine.execute(engine, Action.SELL, bar, indicators)
        engine._execute_sell.assert_called_once()
        engine._execute_buy_or_defer.assert_not_called()

    def test_buy_action_blocked_by_pending_order_gate(self):
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()
        bar = Bar(
            ts=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
            open=100, high=100, low=100, close=100, volume=1.0,
            is_closed=True, is_confirmed=True,
        )
        indicators = {'ema_fast': 101.0, 'ema_slow': 100.0}
        with patch('core.strategy_engine.get_trading_paused', return_value=False):
            StrategyEngine.execute(engine, Action.BUY, bar, indicators)
        engine._execute_buy_or_defer.assert_not_called()
        engine._execute_sell.assert_not_called()


if __name__ == '__main__':
    unittest.main()
