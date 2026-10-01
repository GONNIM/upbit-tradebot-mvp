"""WO-2 옵션 C 회귀 (2026-09-02, 보완 1): 확정 종가 재진입 시 지표 경로.

미확정 평가에서 잠정 종가로 update_incremental(bar.close=800) 이 실행된 뒤,
확정 종가(802)가 도착하면 BACKFILL 재평가 경로 (changed_count > 0) 로 들어온다.

✅ WO-17 (P) (2026-10-01) 개정: 원래 이 테스트는 recompute_from_changed_ts 호출로 "802 기준 교정" 을
증명한다고 적었으나, 실제 운영에서 그 호출은 꼬리 1봉 < 시드 필요 수(200)로 늘 실패해 무동작이었다
(journal 보존분 성공 0 / 실패 8,199). 실효 동작은 update_incremental(802) 1회뿐이었다.
WO-17 (P)에서 부분 재계산 경로를 제거했으므로, 이 테스트는 이제 "재시드 없이 확정 종가로
update_incremental 1회" 를 고정한다.
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
        재시드 없이 update_incremental(확정) 1회만 호출한다 (WO-17 (P) 개정).
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

        # ✅ WO-17 (P): 재시드(부분 재계산) 없음, 확정 종가로 증분 1회
        engine.indicators.recompute_from_changed_ts.assert_not_called()
        engine.indicators.update_incremental.assert_called_once_with(802.0)


if __name__ == '__main__':
    unittest.main()
