"""WO-2 옵션 C 회귀 (2026-09-02): 미확정 평가의 감사 checks JSON 에
via_tentative=True 플래그 포함.

_record_audit_log 는 bar.is_confirmed=False 이면 checks JSON 에
via_tentative=True 를 넣는다. 확정 봉은 False.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestAuditViaTentativeFlag(unittest.TestCase):
    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub'
        engine.ticker = 'KRW-JTO'
        engine.strategy_type = 'EMA'
        engine.bar_count = 100
        engine.interval_sec = 60
        engine.position = MagicMock()
        engine.position.has_position = False
        engine.strategy = MagicMock()
        engine.strategy.enable_base_ema_gap = False
        engine.strategy.gap_details = None
        engine.strategy.last_buy_reason = None
        return engine

    def _make_indicators(self):
        return {
            'ema_fast': 100.0, 'ema_slow': 99.5, 'ema_base': 99.0,
            'macd': None, 'signal': None,
            'use_separate_ema': True,
            'ema_fast_buy': 100.0, 'ema_slow_buy': 99.5,
            'ema_fast_sell': 100.0, 'ema_slow_sell': 99.5,
            'prev_ema_fast': 99.8, 'prev_ema_slow': 99.4,
        }

    def test_tentative_bar_sets_via_tentative_true(self):
        """미확정 봉(is_confirmed=False) 감사의 checks 에 via_tentative=True."""
        from core.strategy_engine import StrategyEngine, Bar
        from core.strategy_action import Action
        engine = self._make_engine_stub()

        bar = Bar(
            ts=datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc),
            open=800, high=800, low=800, close=800, volume=0.0,
            is_closed=True, is_confirmed=False,
            source='WO2_OPTION_C_TENTATIVE:WS_FRESH',
        )
        captured = {}

        def fake_insert_buy_eval(**kwargs):
            captured.update(kwargs)

        with patch('core.strategy_engine.insert_buy_eval', side_effect=fake_insert_buy_eval):
            StrategyEngine._record_audit_log(engine, bar, self._make_indicators(), Action.HOLD)

        checks = captured.get('checks') or {}
        self.assertIn('via_tentative', checks)
        self.assertTrue(checks['via_tentative'])
        self.assertFalse(checks.get('via_backfill', True))

    def test_confirmed_bar_sets_via_tentative_false(self):
        """확정 봉 감사의 checks 에 via_tentative=False."""
        from core.strategy_engine import StrategyEngine, Bar
        from core.strategy_action import Action
        engine = self._make_engine_stub()

        bar = Bar(
            ts=datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc),
            open=800, high=800, low=800, close=800, volume=1.0,
            is_closed=True, is_confirmed=True,
            source='REST_RECONCILED',
        )
        captured = {}

        def fake_insert_buy_eval(**kwargs):
            captured.update(kwargs)

        with patch('core.strategy_engine.insert_buy_eval', side_effect=fake_insert_buy_eval):
            StrategyEngine._record_audit_log(engine, bar, self._make_indicators(), Action.HOLD)

        checks = captured.get('checks') or {}
        self.assertIn('via_tentative', checks)
        self.assertFalse(checks['via_tentative'])


if __name__ == '__main__':
    unittest.main()
