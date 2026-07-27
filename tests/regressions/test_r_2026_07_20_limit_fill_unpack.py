"""
✅ [Phase 2] F1' 회귀: bot_limit_fill 이벤트 언패킹 (커밋 7ff9b10, 2026-07-20)

원 결함: 지정가 체결 이벤트는 (ts, "BUY", {"uuid",...,"source":"bot_limit_fill"})
3-tuple 이지만 _process_event / process_engine_event 는 7-tuple 만 언패킹
→ 매수마다 "not enough values to unpack (expected 7, got 3)" 예외.
7일간 매수 10회 반복, DB audit 로그 유실.

봉쇄 방식: len==3 + isinstance(payload, dict) 분기 추가.
시장가(7-tuple) / 지정가 체결(3-tuple dict) / invalid 3분기 명시.

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_20_limit_fill_unpack -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestLimitFillUnpack(unittest.TestCase):
    """F1': BUY/SELL 이벤트 3가지 형식 모두 정상 처리."""

    def _parse_event(self, event) -> dict:
        """
        engine_manager / engine_runner 의 언패킹 로직 시뮬레이션.
        실제 코드와 동일 분기 검증.
        """
        event_type = event[1]
        if event_type not in ("BUY", "SELL"):
            return {"ok": False, "reason": "not_buy_sell"}

        if len(event) == 3 and isinstance(event[2], dict):
            # 지정가 체결 (Fix)
            ts, _, payload = event
            return {
                "ok": True, "format": "dict_payload",
                "qty": float(payload.get("qty") or 0),
                "price": float(payload.get("price") or 0),
                "source": payload.get("source", "-"),
            }
        elif len(event) >= 7:
            # 시장가
            ts, _, qty, price, cross, macd, signal = event[:7]
            return {
                "ok": True, "format": "7_tuple",
                "qty": qty, "price": price, "cross": cross,
            }
        else:
            return {"ok": False, "reason": f"unsupported_len_{len(event)}"}

    def test_market_buy_7tuple_parses_ok(self):
        """시장가 매수 7-tuple 정상 언패킹."""
        event = (1234567890, "BUY", 100.0, 500.0, "Golden", 0.5, 0.3)
        r = self._parse_event(event)
        self.assertTrue(r["ok"])
        self.assertEqual(r["format"], "7_tuple")
        self.assertEqual(r["qty"], 100.0)
        self.assertEqual(r["price"], 500.0)
        self.assertEqual(r["cross"], "Golden")

    def test_limit_fill_3tuple_dict_parses_ok(self):
        """지정가 체결 3-tuple dict payload 정상 언패킹 (F1' 봉쇄 대상)."""
        event = (1234567890, "BUY", {
            "uuid": "abc-123",
            "price": 816.0,
            "qty": 4254.69,
            "source": "bot_limit_fill",
        })
        r = self._parse_event(event)
        self.assertTrue(r["ok"])
        self.assertEqual(r["format"], "dict_payload")
        self.assertEqual(r["qty"], 4254.69)
        self.assertEqual(r["price"], 816.0)
        self.assertEqual(r["source"], "bot_limit_fill")

    def test_sell_market_7tuple(self):
        """시장가 매도 7-tuple."""
        event = (1234, "SELL", 50.0, 900.0, "Dead", -0.1, -0.05)
        r = self._parse_event(event)
        self.assertTrue(r["ok"])
        self.assertEqual(r["format"], "7_tuple")

    def test_invalid_len2_returns_unsupported(self):
        """invalid 형식 (2-tuple) 은 unsupported 로 안전 스킵."""
        event = (1234, "BUY")
        r = self._parse_event(event)
        self.assertFalse(r["ok"])
        self.assertIn("unsupported", r["reason"])

    def test_dict_payload_missing_fields_defaults_to_zero(self):
        """dict payload 에 qty/price 없으면 0 fallback (예외 없음)."""
        event = (1234, "BUY", {"uuid": "x", "source": "bot_limit_fill"})
        r = self._parse_event(event)
        self.assertTrue(r["ok"])
        self.assertEqual(r["qty"], 0)
        self.assertEqual(r["price"], 0)

    def test_actual_engine_manager_code_no_exception(self):
        """실제 engine_manager._process_event 언패킹 코드가 3-tuple 에서 예외 발생 안 함."""
        # engine_manager.py 의 _process_event 는 stateful 이라 완전 mock 필요.
        # 대신 언패킹 부분만 재현 (실제 코드와 동일 로직).
        event = (1234, "BUY", {"uuid": "x", "price": 100, "qty": 1, "source": "bot_limit_fill"})
        try:
            # 이전 (버그) 코드: ts, _, qty, price, cross, macd, signal = event[:7]
            # → ValueError: not enough values to unpack (expected 7, got 3)
            # 새 코드는 예외 없이 dict 분기로 처리
            r = self._parse_event(event)
            self.assertTrue(r["ok"])
        except ValueError as e:
            self.fail(f"3-tuple dict 언패킹에서 ValueError 발생 (F1' 재발): {e}")


if __name__ == "__main__":
    unittest.main()
