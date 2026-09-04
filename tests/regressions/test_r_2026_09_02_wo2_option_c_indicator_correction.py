"""WO-2 옵션 C 회귀 (2026-09-02, 보완 1): 지표 교정 경로 증명.

미확정 평가에서 잠정 종가로 update_incremental(bar.close=800) 이 실행된 뒤,
확정 종가(802)가 도착하면 BACKFILL 재평가 경로 (changed_count > 0) 를 통해
recompute_from_changed_ts + update_incremental(802) 가 실행되어 지표가 802
기준으로 교정된다.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestIndicatorCorrection(unittest.TestCase):
    def test_backfill_reentry_triggers_recompute_and_update(self):
        """미확정 평가로 잠정 종가가 반영된 뒤, 확정 종가 BACKFILL 진입이
        recompute_from_changed_ts + update_incremental(확정) 를 호출한다.
        """
        from core.strategy_engine import StrategyEngine, Bar
        from core.pending_order import PendingOrderQueue
        from collections import OrderedDict
        from datetime import datetime, timezone

        engine = StrategyEngine.__new__(StrategyEngine)
        engine.user_id = 'stub'
        engine.ticker = 'KRW-JTO'
        engine.strategy_type = 'EMA'
        engine.bar_count = 100
        engine.interval_sec = 60
        engine.last_bar_ts = None
        engine._evaluated_bar_ts = OrderedDict()
        engine._pending_orders = PendingOrderQueue()
        engine._execution_lock = MagicMock()
        engine._execution_lock.__enter__ = MagicMock(return_value=None)
        engine._execution_lock.__exit__ = MagicMock(return_value=False)

        engine.buffer = []
        engine.indicators = MagicMock()
        engine.indicators.recompute_from_changed_ts = MagicMock()
        engine.indicators.update_incremental = MagicMock()
        engine.indicators.get_snapshot = MagicMock(return_value={
            'ema_fast': 802.0, 'ema_slow': 799.0, 'ema_base': 800.0,
            'macd': None, 'signal': None,
            'use_separate_ema': True,
            'ema_fast_buy': 802.0, 'ema_slow_buy': 799.0,
            'ema_fast_sell': 802.0, 'ema_slow_sell': 799.0,
            'prev_ema_fast': 800.0, 'prev_ema_slow': 798.5,
        })
        engine.position = MagicMock()
        engine.position.has_position = False
        engine.position.pending_order = False
        engine.position.sync_from_wallet = MagicMock()
        engine.strategy = MagicMock()
        engine.strategy.on_bar = MagicMock(return_value=None)  # HOLD
        engine.strategy.enable_base_ema_gap = False
        engine.strategy.last_buy_reason = None
        engine.strategy.gap_details = None
        engine._reconcile_position_with_wallet = MagicMock()
        engine._maybe_release_limit_pending = MagicMock()
        engine._record_invariant_snapshot = MagicMock()
        engine._log_bar_evaluation = MagicMock()
        engine._send_log_event = MagicMock()
        engine._record_audit_log = MagicMock()
        engine._resolve_pending_buy = MagicMock()
        engine.execute = MagicMock()
        engine.q = None

        # 확정 종가 802 로 BACKFILL 재진입
        confirmed_bar = Bar(
            ts=datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc),
            open=802, high=802, low=802, close=802, volume=1.0,
            is_closed=True, is_confirmed=True, source='REST_RECONCILED',
        )
        # diff_summary: BACKFILL 모드 + changed_count > 0 (같은 봉이 변경됨)
        diff_summary = {
            'backfill_mode': True,
            'changed_count': 1,
            'changed_ts': [confirmed_bar.ts],
            'rest_failed': False,
        }
        import pandas as pd
        full_series = pd.DataFrame({'Close': [802.0]}, index=[confirmed_bar.ts])

        StrategyEngine.on_new_bar_confirmed(engine, confirmed_bar, full_series, diff_summary)

        # 지표 교정 호출 검증
        engine.indicators.recompute_from_changed_ts.assert_called_once()
        engine.indicators.update_incremental.assert_called_with(802.0)


if __name__ == '__main__':
    unittest.main()
