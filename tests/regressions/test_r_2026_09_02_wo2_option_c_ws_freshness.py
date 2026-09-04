"""WO-2 옵션 C 회귀 (2026-09-02, 보완 3): WS 체결가 신선도 조건.

_lookup_tentative_close 는 WS trade_timestamp 가
  - 대상 봉 구간 [closed_ts, closed_ts+1min) 안이거나
  - 봉 마감 후 max_ws_age_sec(10초) 이내
일 때만 채택한다. 그렇지 않으면 PREV_CLOSE 로 폴백.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.live_loop import _lookup_tentative_close


def _make_local_series_with_prev(closed_ts_kst: pd.Timestamp, prev_close: float) -> pd.DataFrame:
    prev_ts = closed_ts_kst - pd.Timedelta(minutes=1)
    return pd.DataFrame(
        {'Open': [prev_close], 'High': [prev_close], 'Low': [prev_close],
         'Close': [prev_close], 'Volume': [1.0]},
        index=[prev_ts],
    )


class TestWSFreshness(unittest.TestCase):
    def test_ws_within_bar_window_accepted(self):
        """WS 체결이 대상 봉 구간 안 → WS_FRESH 채택."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        trade_ts_kst = closed_ts + pd.Timedelta(seconds=30)  # 구간 안
        trade_ts_ms = int(trade_ts_kst.tz_convert('UTC').timestamp() * 1000)
        fake = [{'trade_price': 810.0, 'trade_timestamp': trade_ts_ms}]
        local_series = _make_local_series_with_prev(closed_ts, 800.0)

        with patch('pyupbit.get_current_price', return_value=fake):
            with patch('engine.live_loop.datetime') as mock_dt:
                mock_dt.now.return_value = (closed_ts + pd.Timedelta(seconds=5)).to_pydatetime()
                result = _lookup_tentative_close('KRW-JTO', local_series, closed_ts)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], 'WS_FRESH')

    def test_ws_within_grace_after_close_accepted(self):
        """WS 체결이 대상 봉 구간 밖이지만 마감 후 10초 이내 → 채택."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        trade_ts_kst = closed_ts - pd.Timedelta(seconds=5)  # 구간 이전 (마감 이전)
        trade_ts_ms = int(trade_ts_kst.tz_convert('UTC').timestamp() * 1000)
        fake = [{'trade_price': 809.0, 'trade_timestamp': trade_ts_ms}]
        local_series = _make_local_series_with_prev(closed_ts, 800.0)

        with patch('pyupbit.get_current_price', return_value=fake):
            with patch('engine.live_loop.datetime') as mock_dt:
                # now: 마감 후 8초 (grace 10초 안) → age_from_close=8
                mock_dt.now.return_value = (closed_ts + pd.Timedelta(seconds=8)).to_pydatetime()
                result = _lookup_tentative_close('KRW-JTO', local_series, closed_ts)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], 'WS_FRESH')

    def test_ws_stale_skipped_and_fallback_prev_close(self):
        """WS 체결이 구간 이전이고 grace 지남 → 스킵 후 PREV_CLOSE."""
        KST = 'Asia/Seoul'
        closed_ts = pd.Timestamp('2026-09-03 03:22:00', tz=KST)
        trade_ts_kst = closed_ts - pd.Timedelta(minutes=5)  # 아주 오래된 체결
        trade_ts_ms = int(trade_ts_kst.tz_convert('UTC').timestamp() * 1000)
        fake = [{'trade_price': 810.0, 'trade_timestamp': trade_ts_ms}]
        local_series = _make_local_series_with_prev(closed_ts, 800.0)

        with patch('pyupbit.get_current_price', return_value=fake):
            with patch('engine.live_loop.datetime') as mock_dt:
                # now: 마감 후 30초 (grace 10초 초과)
                mock_dt.now.return_value = (closed_ts + pd.Timedelta(seconds=30)).to_pydatetime()
                result = _lookup_tentative_close('KRW-JTO', local_series, closed_ts)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], 'PREV_CLOSE')
        self.assertEqual(result[0], 800.0)


if __name__ == '__main__':
    unittest.main()
