"""WO-2 옵션 C 회귀 (2026-09-02): _lookup_tentative_close 우선순위.

우선순위 순서:
  1) WS_FRESH (pyupbit trade_timestamp 신선도 조건 통과)
  2) PREV_CLOSE (local_series 직전 봉)
  3) None (실패)
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.live_loop import _lookup_tentative_close


def _make_local_series_with_prev(closed_ts_kst: pd.Timestamp, prev_close: float) -> pd.DataFrame:
    """closed_ts_kst 직전 봉이 존재하는 최소 local_series 생성."""
    prev_ts = closed_ts_kst - pd.Timedelta(minutes=1)
    return pd.DataFrame(
        {'Open': [prev_close], 'High': [prev_close], 'Low': [prev_close],
         'Close': [prev_close], 'Volume': [1.0]},
        index=[prev_ts],
    )


class TestTentativeCloseSourcePriority(unittest.TestCase):
    def test_ws_fresh_selected_when_in_bar_window(self):
        """WS 체결이 대상 봉 구간 내면 WS_FRESH 채택."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        # WS trade_timestamp: 구간 [03:22:00, 03:23:00) 안
        trade_ts_kst = closed_ts + pd.Timedelta(seconds=25)
        trade_ts_ms = int(trade_ts_kst.tz_convert('UTC').timestamp() * 1000)

        fake_response = [{
            'trade_price': 810.0,
            'trade_timestamp': trade_ts_ms,
        }]
        local_series = _make_local_series_with_prev(closed_ts, 800.0)
        with patch('pyupbit.get_current_price', return_value=fake_response):
            with patch('engine.live_loop.datetime') as mock_dt:
                mock_dt.now.return_value = closed_ts.tz_convert(KST).to_pydatetime()
                result = _lookup_tentative_close('KRW-JTO', local_series, closed_ts)
        self.assertIsNotNone(result)
        close, source, source_ts = result
        self.assertEqual(source, 'WS_FRESH')
        self.assertEqual(close, 810.0)

    def test_prev_close_used_when_ws_missing(self):
        """WS 응답 실패 시 PREV_CLOSE 로 폴백."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        local_series = _make_local_series_with_prev(closed_ts, 800.0)
        with patch('pyupbit.get_current_price', side_effect=Exception('network')):
            result = _lookup_tentative_close('KRW-JTO', local_series, closed_ts)
        self.assertIsNotNone(result)
        close, source, source_ts = result
        self.assertEqual(source, 'PREV_CLOSE')
        self.assertEqual(close, 800.0)

    def test_none_when_ws_missing_and_no_prev(self):
        """WS 실패 + local_series 직전 봉 없음 → None."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        empty = pd.DataFrame({'Open': [], 'High': [], 'Low': [], 'Close': [], 'Volume': []},
                             index=pd.DatetimeIndex([]))
        with patch('pyupbit.get_current_price', side_effect=Exception('network')):
            result = _lookup_tentative_close('KRW-JTO', empty, closed_ts)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
