"""
✅ WO-16 (R) 회귀: REST 다중 조회 `to` UTC + 첫 배치 end_ts(a-2) + 배치 경계 (2026-10-01)

원 결함 (WO-15):
- fetch_candles_rest_full 두 번째 배치 `to` 를 시간대 없는 KST 문자열로 전달 → pyupbit 0.2.34 무변환 →
  Upbit 는 UTC 로 해석 → 9시간 뒤 조회, 첫 배치와 겹쳐 400→293~337, 201→200, 220→200.
- 첫 배치는 end_ts 를 무시(`to` 없음) → 형성 중 봉 포함 (조정·VERIFY).
- 다음 배치 `to = 가장 오래된 봉 − 봉 간격` → Upbit `to` 배타라 경계마다 1봉 누락.

모의 Upbit: 실 API 실측(2026-10-01, plan.md §3 P1~P7)과 같은 규칙 —
  `to` 는 시간대 없는 UTC, 봉 시작 시각 기준 배타. `to=None` 이면 지금까지(형성 중 봉 포함).
실 API 확인은 별도(api_check.csv).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo16r_rest_to_utc -v
"""
from __future__ import annotations

import inspect
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import core.rest_reconcile as rr  # noqa: E402

KST = "Asia/Seoul"
STEP = pd.Timedelta(minutes=5)


class FakeUpbit:
    """pyupbit.get_ohlcv 대역. 봉 시작 시각(UTC) 목록 + '지금'(UTC)을 가진다."""

    def __init__(self, now_utc: pd.Timestamp, n_bars: int = 1200, gaps=()):
        self.now = now_utc
        forming_start = now_utc.floor("5min")
        starts = pd.date_range(end=forming_start, periods=n_bars, freq="5min", tz="UTC")
        starts = starts.delete([starts.get_loc(g) for g in gaps])
        price = [700.0 + (int(t.timestamp()) // 300) % 11 for t in starts]
        self.bars = pd.DataFrame(
            {"open": price, "high": [p + 2 for p in price], "low": [p - 2 for p in price],
             "close": price, "volume": [100.0] * len(starts), "value": [1.0] * len(starts)},
            index=starts,
        )
        self.forming_start = forming_start
        self.calls = []

    def get_ohlcv(self, ticker="KRW-BTC", interval="day", count=200, to=None, period=0.1):
        self.calls.append(to)
        if to is None:
            to_utc = self.now                                   # pyupbit: to=None → 현재 UTC
        else:
            t = pd.Timestamp(to)
            to_utc = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")  # 시간대 없음 = UTC
        sel = self.bars[(self.bars.index < to_utc) & (self.bars.index <= self.now)].tail(count)
        out = sel.copy()
        out.index = out.index.tz_convert(KST).tz_localize(None)   # pyupbit 는 KST naive 인덱스
        return out


def _closed_ts(fake: FakeUpbit) -> pd.Timestamp:
    return fake.forming_start - STEP


class _Base(unittest.TestCase):
    def setUp(self):
        # 형성 중 봉 시작 2분 뒤가 '지금'. 과거 깊숙이 무거래 구멍 3개(겹침 구간 밖)
        self.now = pd.Timestamp("2026-10-01 03:02:08", tz="UTC")
        forming = self.now.floor("5min")
        gaps = [forming - STEP * k for k in (700, 701, 950)]
        self.fake = FakeUpbit(self.now, gaps=gaps)
        self._p = [
            patch.object(rr.pyupbit, "get_ohlcv", self.fake.get_ohlcv),
            patch.object(rr.time, "sleep", lambda *_: None),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def _expected(self, end_ts, n):
        return list(self.fake.bars.index[self.fake.bars.index <= end_ts][-n:])


class TestRestToUtc(_Base):

    def test_1_400_requested_400_received_no_dup_no_gap(self):
        """① 400 요청 → 400 수신, 중복 0, 배치 경계 누락 0 (모의 Upbit 의 실제 봉과 일치)."""
        closed = _closed_ts(self.fake)
        df = rr.fetch_candles_rest_full("KRW-JTO", "minute5", closed.to_pydatetime(), 400)
        self.assertEqual(len(df), 400)
        self.assertFalse(df.index.duplicated().any())
        self.assertEqual(list(df.index), self._expected(closed, 400))
        # 두 번째 배치 to = 첫 배치 가장 오래된 봉 시작(UTC 문자열)
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.fake.calls[1], rr._upbit_to_str(df.index[200]))

    def test_2_last_bar_is_end_ts_and_no_forming(self):
        """② end_ts=closed_ts → 마지막 봉 == closed_ts, 형성 중 봉 미포함 (조정 경로)."""
        closed = _closed_ts(self.fake)
        df = rr.fetch_candles_rest_full("KRW-JTO", "minute5", closed.to_pydatetime(), 400)
        self.assertEqual(df.index[-1], closed)
        self.assertNotIn(self.fake.forming_start, df.index)
        self.assertEqual(self.fake.calls[0], rr._upbit_to_str(closed + STEP))

    def test_3_verify_range_covers_all_targets(self):
        """③ VERIFY: 응답 범위가 검증 대상 200봉을 전부 포함 → 건너뜀 0, 통과."""
        closed = _closed_ts(self.fake)
        idx = pd.DatetimeIndex(self._expected(closed - STEP, 200))   # 현재 봉 제외 과거 200봉
        past = pd.DataFrame({"Close": self.fake.bars.loc[idx, "close"].values}, index=idx)
        with self.assertLogs("core.rest_reconcile", level="INFO") as cm:
            ok = rr.verify_past_candles_with_upbit("KRW-JTO", "minute5", past, tolerance=1.0)
        self.assertTrue(ok)
        self.assertEqual([m for m in cm.output if "Upbit에 없는 timestamp" in m], [])
        self.assertTrue(any("모든 과거 봉 일치" in m for m in cm.output))

    def test_4_old_kst_to_reproduces_shortfall(self):
        """④ (대조) 옛 방식(첫 배치 to 없음 + KST 문자열 to) → 400 요청에 ~293 수신, 형성 중 봉 포함."""
        def _old_kst(ts):
            t = pd.Timestamp(ts)
            t = t.tz_localize("UTC") if t.tzinfo is None else t
            return t.tz_convert(KST).strftime("%Y-%m-%d %H:%M:%S")

        closed = _closed_ts(self.fake)
        with patch.object(rr, "_upbit_to_str", _old_kst), \
             patch.object(rr, "_first_batch_to_kwargs", lambda *_a, **_k: {}):
            df = rr.fetch_candles_rest_full("KRW-JTO", "minute5", closed.to_pydatetime(), 400)
        self.assertTrue(285 <= len(df) <= 300, len(df))   # 9시간(108칸) 겹침 → 400 − 108 = 292
        self.assertIn(self.fake.forming_start, df.index)

    def test_5_fetch_confirmed_candle_is_separate(self):
        """⑤ Issue #8 계열 고정: fetch_confirmed_candle 은 공용 다중 조회 함수를 부르지 않고
        pyupbit.get_ohlcv 를 to 없이 직접 부른다 (소스 검사)."""
        src = inspect.getsource(rr.fetch_confirmed_candle)
        for name in ("fetch_candles_rest_full", "safe_fetch_rest", "_first_batch_to_kwargs", "_upbit_to_str"):
            self.assertNotIn(name, src, f"fetch_confirmed_candle 이 {name} 를 부름")
        self.assertIn("pyupbit.get_ohlcv(", src)
        call = src[src.index("pyupbit.get_ohlcv("):]
        call = call[: call.index(")") + 1]
        self.assertNotIn("to=", call)


class TestUpbitToStr(unittest.TestCase):

    def test_to_str_is_utc(self):
        """KST 인식 시각 → UTC 문자열, 시간대 없는 입력은 UTC 로 간주."""
        self.assertEqual(rr._upbit_to_str(pd.Timestamp("2026-10-01 12:05", tz=KST)), "2026-10-01 03:05:00")
        self.assertEqual(rr._upbit_to_str(pd.Timestamp("2026-10-01 03:05")), "2026-10-01 03:05:00")
        self.assertEqual(rr._first_batch_to_kwargs(None, 300), {})
        self.assertEqual(
            rr._first_batch_to_kwargs(pd.Timestamp("2026-10-01 03:00", tz="UTC"), 300),
            {"to": "2026-10-01 03:05:00"},
        )


if __name__ == "__main__":
    unittest.main()
