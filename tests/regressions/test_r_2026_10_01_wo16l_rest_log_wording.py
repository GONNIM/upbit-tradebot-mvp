"""
✅ WO-16 (L) 회귀: REST 첫 배치 로그·주석 문구 정정 (2026-10-01)

원 결함 (WO-15):
- `[REST] 최신 확정 봉 ✅` 가 첫 배치 마지막 봉을 늘 "확정" 으로 표시 — 형성 중 봉에도 찍힘
  (2026-10-01 11:50:12 VERIFY 조회의 11:50 봉).
- 주석·docstring "to 파라미터 없음 → Upbit 확정 봉만 반환" 은 사실과 다름(형성 중 봉 포함).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo16l_rest_log_wording -v
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import core.rest_reconcile as rr  # noqa: E402


def _stub_ohlcv(ticker="KRW-BTC", interval="day", count=200, to=None, period=0.1):
    idx = pd.date_range(end=pd.Timestamp("2026-10-01 12:00"), periods=count, freq="5min")   # KST naive
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0, "value": 1.0}, index=idx)


class TestRestLogWording(unittest.TestCase):

    def test_1_source_wording(self):
        """옛 문구가 fetch_candles_rest_full·safe_fetch_rest 에서 사라지고 새 문구가 있음."""
        for fn in (rr.fetch_candles_rest_full, rr.safe_fetch_rest):
            src = inspect.getsource(fn)
            self.assertNotIn("최신 확정 봉 ✅", src)
            self.assertNotIn("확정 봉만 반환", src)
            self.assertNotIn("최신 확정 봉만 조회", src)
        src = inspect.getsource(rr.fetch_candles_rest_full)
        self.assertIn("[REST] 첫 배치 마지막 봉 {_first_label}", src)

    def test_2_rendered_log_with_end_ts(self):
        """end_ts 있음 → '[REST] 첫 배치 마지막 봉 (end_ts 기준)' 렌더, 옛 문구 없음."""
        with patch.object(rr.pyupbit, "get_ohlcv", _stub_ohlcv), patch.object(rr.time, "sleep", lambda *_: None), \
             self.assertLogs("core.rest_reconcile", level="INFO") as cm:
            rr.fetch_candles_rest_full("KRW-JTO", "minute5", pd.Timestamp("2026-10-01 03:00", tz="UTC"), 10)
        self.assertTrue(any("[REST] 첫 배치 마지막 봉 (end_ts 기준) | ts=2026-10-01 12:00:00 KST" in m for m in cm.output), cm.output)
        self.assertFalse(any("최신 확정 봉" in m for m in cm.output))

    def test_3_rendered_log_without_end_ts(self):
        """end_ts=None(워밍업) → '(형성 중 포함 가능)' 렌더, 시작 로그도 정정."""
        with patch.object(rr.pyupbit, "get_ohlcv", _stub_ohlcv), patch.object(rr.time, "sleep", lambda *_: None), \
             self.assertLogs("core.rest_reconcile", level="INFO") as cm:
            rr.fetch_candles_rest_full("KRW-JTO", "minute5", None, 10)
        self.assertTrue(any("[REST] 첫 배치 마지막 봉 (형성 중 포함 가능) |" in m for m in cm.output), cm.output)
        self.assertTrue(any("end=None (to 없음, 형성 중 봉 포함 가능)" in m for m in cm.output), cm.output)
        self.assertFalse(any("최신 확정 봉" in m for m in cm.output))


if __name__ == "__main__":
    unittest.main()
