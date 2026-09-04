"""WO-2 옵션 C 회귀 (2026-09-02): 미확정 봉의 매도 판단 즉시 집행.

execute() 는 매도 판단에서 지연 큐를 우회하고 _execute_sell 을 즉시 호출한다.
잠정 봉(bar.is_confirmed=False)에서도 동일하다.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrderQueue
from core.strategy_action import Action


class TestOptionCSellImmediateOnTentative(unittest.TestCase):
    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub'
        engine.ticker = 'KRW-JTO'
        engine.bar_count = 100
        engine.strategy_type = 'EMA'
        engine.indicators = MagicMock()
        engine.indicators.state_polluted = False
        engine.position = MagicMock()
        engine.position.pending_order = False
        engine._pending_orders = PendingOrderQueue()
        engine._execute_buy_or_defer = MagicMock()
        engine._execute_sell = MagicMock()
        return engine

    def test_sell_on_tentative_bar_executes_immediately(self):
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()
        tentative_close = 800.0
        bar = Bar(
            ts=datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc),
            open=tentative_close, high=tentative_close, low=tentative_close,
            close=tentative_close, volume=0.0,
            is_closed=True, is_confirmed=False,  # ← 옵션 C 미확정
            source='WO2_OPTION_C_TENTATIVE:WS_FRESH',
        )
        with patch('core.strategy_engine.get_trading_paused', return_value=False):
            StrategyEngine.execute(engine, Action.SELL, bar, {})
        engine._execute_sell.assert_called_once()
        engine._execute_buy_or_defer.assert_not_called()
        # 큐도 그대로 비어있어야 함
        self.assertTrue(engine._pending_orders.is_empty())


if __name__ == '__main__':
    unittest.main()
