"""WO-2 옵션 C 회귀 (2026-09-02): 재시도 소진 시 미확정 Bar 로 엔진 진입.

_execute_buy_or_defer 는 bar.is_confirmed=False 이면 PendingOrderQueue.register 로
분기한다. 잠정 종가와 이전 봉의 매수용 EMA 쌍이 있으면 큐 등록이 성공한다.
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.pending_order import PendingOrderQueue


class TestOptionCTentativeEntry(unittest.TestCase):
    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub'
        engine.ticker = 'KRW-JTO'
        engine.strategy_type = 'EMA'
        engine.bar_count = 100
        engine._pending_orders = PendingOrderQueue()
        engine._execute_buy = MagicMock()
        engine._audit_wo2_resolution = MagicMock()

        engine.indicators = MagicMock()
        engine.indicators.use_separate_ema = True
        engine.indicators.alpha_ema_fast_buy = 2 / 21
        engine.indicators.alpha_ema_slow_buy = 2 / 201
        engine.indicators.alpha_ema_fast = 2 / 21
        engine.indicators.alpha_ema_slow = 2 / 201
        return engine

    def test_unconfirmed_bar_routes_to_pending_queue(self):
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
        indicators = {
            'prev_ema_fast': 799.5,
            'prev_ema_slow': 799.0,
            'ema_fast': 799.8,
            'ema_slow': 799.1,
        }

        StrategyEngine._execute_buy_or_defer(engine, bar, indicators)

        # 큐에 등록됐고 즉시 발주는 없음
        self.assertFalse(engine._pending_orders.is_empty())
        self.assertEqual(engine._pending_orders.current.bar_ts, bar.ts)
        self.assertEqual(engine._pending_orders.current.tentative_close, tentative_close)
        engine._execute_buy.assert_not_called()

    def test_confirmed_bar_routes_to_immediate_buy(self):
        from core.strategy_engine import StrategyEngine, Bar
        engine = self._make_engine_stub()
        bar = Bar(
            ts=datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc),
            open=800, high=800, low=800, close=800, volume=1.0,
            is_closed=True, is_confirmed=True,
            source='REST_RECONCILED',
        )
        indicators = {'prev_ema_fast': 799.5, 'prev_ema_slow': 799.0}
        StrategyEngine._execute_buy_or_defer(engine, bar, indicators)
        # 큐 미등록, 즉시 _execute_buy 호출
        self.assertTrue(engine._pending_orders.is_empty())
        engine._execute_buy.assert_called_once()


if __name__ == '__main__':
    unittest.main()
