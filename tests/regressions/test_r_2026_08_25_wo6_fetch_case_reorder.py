"""WO-6 회귀 테스트 — fetch_confirmed_candle 케이스 재배치와 NO_TRADE 표지.

배경:
    WO-6 개편 전에는 fetch_confirmed_candle 이 다음 순서로 판정했다.
    - 케이스 1 (latest_ts == closed_ts) 즉시 확정
    - 케이스 2 (latest_ts < closed_ts) 재시도
    - 케이스 3 (latest_ts > closed_ts) df 에서 closed_ts 추출, 없으면 None
    이 순서는 다음 봉이 이미 있는데도 케이스 1 이 먼저 매칭되고, 무거래 봉을
    유실로 처리하는 문제가 있었다.

    WO-6 개편 후:
    - 케이스 A (latest_ts > closed_ts) 다음 봉 존재 → 즉시 확정
    - 케이스 A 하위 (closed_ts not in df.index) 무거래 봉 → NO_TRADE 표지
    - 케이스 C (latest_ts < closed_ts) API 지연 → 재시도
    - 케이스 B (latest_ts == closed_ts) 다음 봉 미존재 → 5초 안정화 1회
      - 첫 진입: 5초 뒤 재조회 예약
      - 재조회: 종가 같으면 확정, 다르면 다음 조회 케이스로 재판정
    - 재시도 초과 → None (호출부 재조정 계속 진행)

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_25_wo6_fetch_case_reorder -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd

from core import rest_reconcile
from core.rest_reconcile import fetch_confirmed_candle, NO_TRADE, _case_b_state


def _make_df(rows):
    """rows: [(ts_utc, close), ...] → OHLCV DataFrame (KST tz-naive index)."""
    if not rows:
        return pd.DataFrame()
    index = [ts.astimezone(timezone(timedelta(hours=9))).replace(tzinfo=None) for ts, _ in rows]
    data = {
        "Open": [c for _, c in rows],
        "High": [c for _, c in rows],
        "Low": [c for _, c in rows],
        "Close": [c for _, c in rows],
        "Volume": [1.0 for _ in rows],
    }
    df = pd.DataFrame(data, index=pd.DatetimeIndex(index))
    # rest_reconcile 코드는 컬럼을 capitalize 후 KST→UTC 변환.
    # pyupbit 모사: 소문자 컬럼으로 반환.
    df.columns = [c.lower() for c in df.columns]
    return df


class TestFetchConfirmedCandleCases(unittest.TestCase):
    """WO-6: 케이스 A/B/C/D 재배치와 NO_TRADE 표지 동작 확인."""

    def setUp(self):
        # 테스트 격리: _case_b_state 초기화
        _case_b_state.clear()
        rest_reconcile._confirmed_fetch_consecutive_failures.clear()

    def test_case_a_next_bar_exists_returns_confirmed(self):
        """케이스 A: 다음 봉 존재 + 대상 봉 있음 → 즉시 확정 (pd.Series 반환)."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        next_ts = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)
        df = _make_df([(closed_ts, 100.0), (next_ts, 101.0)])
        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=1)
        self.assertIsNotNone(result)
        self.assertIsNot(result, NO_TRADE)
        self.assertEqual(float(result["Close"]), 100.0)

    def test_case_a_no_trade_bar_returns_marker(self):
        """케이스 A 하위 (무거래 봉): 다음 봉만 있고 대상 봉 없음 → NO_TRADE 반환."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        next_ts = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)
        # 대상 봉 (9:04) 은 응답에 없음. 다음 봉 (9:05) 만 있음.
        df = _make_df([(next_ts, 101.0)])
        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=1)
        self.assertIs(result, NO_TRADE, "무거래 봉은 NO_TRADE 표지를 반환해야 함")
        # 실패 계수 리셋 확인 (정상 흐름이지 실패가 아님)
        self.assertEqual(
            rest_reconcile._confirmed_fetch_consecutive_failures.get("KRW-JTO", 0), 0
        )

    def test_case_c_api_lag_retries(self):
        """케이스 C: latest_ts < closed_ts (API 지연) → 재시도 후 실패 시 None.

        F1b(ticks 보조)는 체결 존재로 mock 해서 None 유지 (기존 실패 흐름 확인).
        """
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        df = _make_df([(earlier_ts, 99.0)])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"trade_time_utc": "09:04:15", "trade_price": 100.0, "trade_volume": 1.0},
        ]
        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.requests, "get", return_value=mock_resp), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)
        # 두 번 재시도 후에도 latest_ts < closed_ts → F1b 체결 있음 → None 반환
        self.assertIsNone(result)

    def test_case_b_stabilization_first_entry_then_confirm(self):
        """케이스 B: 첫 진입 시 상태 저장, 5초 뒤 재조회 시 같은 종가면 확정.

        시뮬레이션: 첫 조회와 두 번째 조회에서 같은 종가 반환.
        """
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        df = _make_df([(closed_ts, 100.0)])  # latest == closed
        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=3)
        # 두 번째 조회에서 종가 같음 → 안정화 확정
        self.assertIsNotNone(result)
        self.assertIsNot(result, NO_TRADE)
        self.assertEqual(float(result["Close"]), 100.0)
        # 상태 정리 확인
        self.assertNotIn(("KRW-JTO", closed_ts), _case_b_state)

    def test_case_b_close_changes_re_evaluates(self):
        """케이스 B: 5초 뒤 종가 변경 → 상태 갱신 후 다음 조회로 재판정."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        # 3회 조회: 100 → 101(변경) → 102(변경) → 102(안정화)
        dfs = [
            _make_df([(closed_ts, 100.0)]),
            _make_df([(closed_ts, 101.0)]),
            _make_df([(closed_ts, 102.0)]),
            _make_df([(closed_ts, 102.0)]),
        ]
        call_iter = iter(dfs)

        def _fake_get(*args, **kwargs):
            return next(call_iter, dfs[-1])

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", side_effect=_fake_get), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=5)
        # 최종 안정화 종가 102 확정
        self.assertIsNotNone(result)
        self.assertIsNot(result, NO_TRADE)
        self.assertEqual(float(result["Close"]), 102.0)

    def test_max_retry_exhaustion_returns_none(self):
        """모든 재시도 실패 시 None 반환 (호출부는 재조정 계속 진행).

        F1b ticks 는 체결 존재로 mock 해서 None 유지.
        """
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        df = _make_df([(earlier_ts, 99.0)])  # 항상 케이스 C (지연)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"trade_time_utc": "09:04:15", "trade_price": 100.0, "trade_volume": 1.0},
        ]
        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.requests, "get", return_value=mock_resp), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=3)
        self.assertIsNone(result)


class TestExhaustionNoTradeClassification(unittest.TestCase):
    """WO-6 보완 F1 (2026-08-26): 재시도 소진 후 무거래 여부 최종 판별.

    무거래 봉인데 다음 봉조차 아직 반영 안 된 경우 케이스 B/C 재시도가 모두
    소진된다. 이때 실 소진 시점의 Upbit REST 조회로 대상 봉 존재 여부를
    한 번 더 확인하여 무거래이면 NO_TRADE 로, 거래가 있으면 None (기존 실패
    흐름) 으로 분류한다.
    """

    def setUp(self):
        _case_b_state.clear()
        rest_reconcile._confirmed_fetch_consecutive_failures.clear()

    def test_exhaustion_then_no_trade_returns_marker(self):
        """소진 후 판별에서 다음 봉 존재 + 대상 봉 미존재 → NO_TRADE 반환."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        next_ts = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)

        # 재시도 동안: 항상 케이스 C (latest < closed)
        # 소진 후 판별: 다음 봉 존재, 대상 봉 없음 → NO_TRADE
        retry_df = _make_df([(earlier_ts, 99.0)])
        exhaust_df = _make_df([(next_ts, 101.0)])  # 다음 봉만 있음

        call_count = {"n": 0}

        def _fake_get(*args, **kwargs):
            call_count["n"] += 1
            # 재시도 max_retry=2 회 동안은 지연 응답, 그 후 판별 호출은 exhaust_df
            if call_count["n"] <= 2:
                return retry_df
            return exhaust_df

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", side_effect=_fake_get), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)

        self.assertIs(result, NO_TRADE, "소진 후 무거래 확정은 NO_TRADE 를 반환해야 함")
        # 실패 계수는 리셋되어 있어야 함 (거짓 CRITICAL 방지)
        self.assertEqual(
            rest_reconcile._confirmed_fetch_consecutive_failures.get("KRW-JTO", 0),
            0,
            "무거래로 확정된 소진은 실패 계수에 가산되지 않아야 함",
        )

    def test_exhaustion_then_trade_returns_none(self):
        """소진 후 판별에서 대상 봉 존재 → None 반환 + 실패 계수 증가 (기존 흐름)."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        next_ts = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)

        # 재시도 동안: 케이스 C 지연
        # 소진 후 판별: 다음 봉 + 대상 봉 모두 있음 → 거래 있음 → None (실패로 카운트)
        retry_df = _make_df([(earlier_ts, 99.0)])
        exhaust_df = _make_df([(closed_ts, 100.0), (next_ts, 101.0)])

        call_count = {"n": 0}

        def _fake_get(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return retry_df
            return exhaust_df

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", side_effect=_fake_get), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)

        self.assertIsNone(result, "거래 있는 봉의 소진은 None (기존 실패 흐름) 을 반환해야 함")
        # 실패 계수 증가 확인
        self.assertGreaterEqual(
            rest_reconcile._confirmed_fetch_consecutive_failures.get("KRW-JTO", 0),
            1,
            "거래 있는 봉의 소진은 실패 계수에 가산되어야 함",
        )


class TestF1bTicksAssistedClassification(unittest.TestCase):
    """WO-6 보완 F1b (2026-08-29): 연속 무거래 시작 지점에서 ticks API 보조 판별.

    F1(get_ohlcv 기반)이 latest_ts < closed_ts 로 판별 불가한 경우에도,
    /v1/trades/ticks 로 그 분의 체결 여부를 확인해 NO_TRADE 로 확정한다.
    """

    def setUp(self):
        _case_b_state.clear()
        rest_reconcile._confirmed_fetch_consecutive_failures.clear()

    def test_undecidable_no_ticks_returns_no_trade(self):
        """판별 불가(latest_ts < closed_ts) + ticks 체결 0건 → NO_TRADE 반환."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)

        # 재시도와 소진 후 F1 판별 모두 케이스 C 응답 (판별 불가)
        df = _make_df([(earlier_ts, 99.0)])

        # ticks API 는 체결 0건 반환
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []  # 체결 0건

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.requests, "get", return_value=mock_resp), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)

        self.assertIs(result, NO_TRADE, "판별 불가 + 체결 0건은 NO_TRADE 를 반환해야 함")
        # 실패 계수 미가산 확인
        self.assertEqual(
            rest_reconcile._confirmed_fetch_consecutive_failures.get("KRW-JTO", 0),
            0,
            "F1b NO_TRADE 는 실패 계수에 가산되지 않아야 함",
        )

    def test_undecidable_with_ticks_returns_none(self):
        """판별 불가(latest_ts < closed_ts) + ticks 체결 존재 → None 반환 (기존 실패 흐름)."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)

        df = _make_df([(earlier_ts, 99.0)])

        # ticks API 는 대상 분(09:04 UTC) 체결 반환
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"trade_time_utc": "09:04:15", "trade_price": 100.0, "trade_volume": 1.0},
            {"trade_time_utc": "09:04:30", "trade_price": 100.5, "trade_volume": 2.0},
        ]

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.requests, "get", return_value=mock_resp), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)

        self.assertIsNone(result, "판별 불가 + 체결 존재는 None 을 반환해야 함")
        # 실패 계수 증가 확인
        self.assertGreaterEqual(
            rest_reconcile._confirmed_fetch_consecutive_failures.get("KRW-JTO", 0),
            1,
            "판별 불가 + 체결 존재는 실패 계수에 가산되어야 함",
        )

    def test_undecidable_ticks_api_fail_returns_none(self):
        """판별 불가 + ticks API 자체 실패 → None (보수적)."""
        closed_ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        earlier_ts = datetime(2026, 8, 25, 9, 3, 0, tzinfo=timezone.utc)
        df = _make_df([(earlier_ts, 99.0)])

        mock_resp = MagicMock()
        mock_resp.status_code = 500  # 서버 오류

        with patch.object(rest_reconcile.pyupbit, "get_ohlcv", return_value=df), \
             patch.object(rest_reconcile.requests, "get", return_value=mock_resp), \
             patch.object(rest_reconcile.time, "sleep", return_value=None):
            result = fetch_confirmed_candle("KRW-JTO", "minute1", closed_ts, max_retry=2)

        self.assertIsNone(result, "ticks API 실패 시 None 을 반환해야 함 (보수적)")


class TestNoTradeMarkerIdentity(unittest.TestCase):
    """WO-6: NO_TRADE 는 pd.Series 나 None 과 명확히 구분되는 센티널이다."""

    def test_no_trade_is_not_none(self):
        self.assertIsNotNone(NO_TRADE)

    def test_no_trade_is_not_series(self):
        self.assertNotIsInstance(NO_TRADE, pd.Series)

    def test_no_trade_repr(self):
        self.assertEqual(repr(NO_TRADE), "NO_TRADE")


if __name__ == "__main__":
    unittest.main()
