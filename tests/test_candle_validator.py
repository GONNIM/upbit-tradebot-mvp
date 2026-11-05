"""
WO-2026-001 Task 2-A: CandleValidator 단위 테스트

테스트 커버리지:
1. OHLC 논리 검증 (low ≤ open, close ≤ high)
2. 스파이크 감지 (경고만, 차단 안 함)
3. 유령 봉 차단 (거래량 0)
4. 필수 키 누락 처리
5. 대소문자 구분 없는 키 처리
"""

import unittest
import pandas as pd
from core.candle_validator import CandleValidator


class TestCandleValidator(unittest.TestCase):
    """CandleValidator 클래스 단위 테스트"""

    def setUp(self):
        """각 테스트 전 초기화"""
        self.validator = CandleValidator(max_spike_ratio=0.05)

    def tearDown(self):
        """각 테스트 후 정리"""
        self.validator.reset()

    # ============================================================
    # 1. OHLC 논리 검증 테스트
    # ============================================================

    def test_valid_candle_basic(self):
        """정상 봉 데이터 - 검증 통과"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    def test_invalid_low_greater_than_high(self):
        """저가 > 고가 - 검증 실패"""
        candle = pd.Series({
            'open': 100.0,
            'high': 98.0,  # ❌ 저가보다 낮음
            'low': 105.0,
            'close': 102.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("OHLC 논리 오류", reason)

    def test_invalid_open_greater_than_high(self):
        """시가 > 고가 - 검증 실패"""
        candle = pd.Series({
            'open': 110.0,  # ❌ 고가보다 높음
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("OHLC 논리 오류", reason)

    def test_invalid_open_less_than_low(self):
        """시가 < 저가 - 검증 실패"""
        candle = pd.Series({
            'open': 95.0,  # ❌ 저가보다 낮음
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("OHLC 논리 오류", reason)

    def test_invalid_close_greater_than_high(self):
        """종가 > 고가 - 검증 실패"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 110.0,  # ❌ 고가보다 높음
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("OHLC 논리 오류", reason)

    def test_invalid_close_less_than_low(self):
        """종가 < 저가 - 검증 실패"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 95.0,  # ❌ 저가보다 낮음
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("OHLC 논리 오류", reason)

    def test_valid_candle_equal_ohlc(self):
        """OHLC 모두 동일 (도지 캔들) - 검증 통과"""
        candle = pd.Series({
            'open': 100.0,
            'high': 100.0,
            'low': 100.0,
            'close': 100.0,
            'volume': 500.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    # ============================================================
    # 2. 스파이크 감지 테스트 (경고만, 차단 안 함)
    # ============================================================

    def test_spike_detection_warning_only(self):
        """스파이크 감지 - 경고만 하고 검증 통과"""
        # 첫 번째 봉: prev_close 설정
        candle1 = pd.Series({
            'open': 1000.0,
            'high': 1050.0,
            'low': 980.0,
            'close': 1000.0,
            'volume': 1000.0
        })
        valid1, _ = self.validator.validate(candle1)
        self.assertTrue(valid1)

        # 두 번째 봉: 10% 급등 (5% 임계값 초과)
        candle2 = pd.Series({
            'open': 1100.0,
            'high': 1150.0,
            'low': 1080.0,
            'close': 1100.0,  # 1000 → 1100 (10% 상승)
            'volume': 2000.0
        })
        valid2, reason2 = self.validator.validate(candle2)
        # ✅ 경고만 하고 검증은 통과해야 함
        self.assertTrue(valid2)
        self.assertEqual(reason2, "OK")

    def test_no_spike_under_threshold(self):
        """스파이크 미만 변동 - 정상 통과"""
        candle1 = pd.Series({
            'open': 1000.0,
            'high': 1050.0,
            'low': 980.0,
            'close': 1000.0,
            'volume': 1000.0
        })
        valid1, _ = self.validator.validate(candle1)
        self.assertTrue(valid1)

        # 3% 변동 (5% 미만)
        candle2 = pd.Series({
            'open': 1030.0,
            'high': 1050.0,
            'low': 1020.0,
            'close': 1030.0,  # 1000 → 1030 (3% 상승)
            'volume': 1500.0
        })
        valid2, reason2 = self.validator.validate(candle2)
        self.assertTrue(valid2)
        self.assertEqual(reason2, "OK")

    def test_first_candle_no_spike_check(self):
        """첫 번째 봉 - 스파이크 체크 없음"""
        candle = pd.Series({
            'open': 1000.0,
            'high': 1050.0,
            'low': 980.0,
            'close': 1000.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")
        self.assertEqual(self.validator.prev_close, 1000.0)

    # ============================================================
    # 3. 유령 봉 차단 테스트
    # ============================================================

    def test_ghost_candle_volume_zero(self):
        """거래량 0 - 유령 봉 차단"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 0.0  # ❌ 거래량 0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("거래량 0", reason)
        self.assertIn("유령 봉", reason)

    def test_valid_candle_with_low_volume(self):
        """거래량 > 0 (낮은 값) - 정상 통과"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 0.01  # ✅ 거래량 > 0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    # ============================================================
    # 4. 필수 키 누락 테스트
    # ============================================================

    def test_missing_key_open(self):
        """필수 키 누락 - open"""
        candle = pd.Series({
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("필수 키 누락", reason)
        self.assertIn("open", reason)

    def test_missing_key_volume(self):
        """필수 키 누락 - volume"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertFalse(valid)
        self.assertIn("필수 키 누락", reason)
        self.assertIn("volume", reason)

    # ============================================================
    # 5. 대소문자 구분 없는 키 처리 테스트
    # ============================================================

    def test_capitalized_keys(self):
        """대문자 시작 키 - 정상 처리"""
        candle = pd.Series({
            'Open': 100.0,   # Capitalized
            'High': 105.0,
            'Low': 98.0,
            'Close': 102.0,
            'Volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    def test_uppercase_keys(self):
        """전체 대문자 키 - 정상 처리"""
        candle = pd.Series({
            'OPEN': 100.0,   # UPPERCASE
            'HIGH': 105.0,
            'LOW': 98.0,
            'CLOSE': 102.0,
            'VOLUME': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    def test_mixed_case_keys(self):
        """혼합 대소문자 키 - 정상 처리"""
        candle = pd.Series({
            'open': 100.0,   # lowercase
            'High': 105.0,   # Capitalized
            'LOW': 98.0,     # UPPERCASE
            'close': 102.0,  # lowercase
            'Volume': 1000.0 # Capitalized
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    # ============================================================
    # 6. Validator 상태 관리 테스트
    # ============================================================

    def test_reset_clears_prev_close(self):
        """reset() 호출 시 prev_close 초기화"""
        candle = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        self.validator.validate(candle)
        self.assertEqual(self.validator.prev_close, 102.0)

        self.validator.reset()
        self.assertIsNone(self.validator.prev_close)

    def test_prev_close_updated_after_validation(self):
        """검증 통과 시 prev_close 업데이트"""
        candle1 = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        self.validator.validate(candle1)
        self.assertEqual(self.validator.prev_close, 102.0)

        candle2 = pd.Series({
            'open': 102.0,
            'high': 108.0,
            'low': 101.0,
            'close': 105.0,
            'volume': 1500.0
        })
        self.validator.validate(candle2)
        self.assertEqual(self.validator.prev_close, 105.0)

    def test_prev_close_not_updated_on_failure(self):
        """검증 실패 시 prev_close 업데이트 안 됨"""
        candle1 = pd.Series({
            'open': 100.0,
            'high': 105.0,
            'low': 98.0,
            'close': 102.0,
            'volume': 1000.0
        })
        self.validator.validate(candle1)
        self.assertEqual(self.validator.prev_close, 102.0)

        # 유령 봉 (검증 실패)
        candle2 = pd.Series({
            'open': 102.0,
            'high': 108.0,
            'low': 101.0,
            'close': 105.0,
            'volume': 0.0  # ❌ 거래량 0
        })
        valid, _ = self.validator.validate(candle2)
        self.assertFalse(valid)
        # prev_close는 이전 값 유지
        self.assertEqual(self.validator.prev_close, 102.0)

    # ============================================================
    # 7. 엣지 케이스 테스트
    # ============================================================

    def test_negative_price_values(self):
        """음수 가격 - OHLC 논리 통과 (음수 자체는 허용)"""
        # OHLC 논리만 검증하므로, 음수여도 low ≤ open, close ≤ high면 통과
        candle = pd.Series({
            'open': -100.0,
            'high': -95.0,
            'low': -105.0,
            'close': -98.0,
            'volume': 1000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    def test_very_large_price_values(self):
        """매우 큰 가격 값 - 정상 처리"""
        candle = pd.Series({
            'open': 1_000_000.0,
            'high': 1_050_000.0,
            'low': 980_000.0,
            'close': 1_020_000.0,
            'volume': 10_000.0
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")

    def test_decimal_price_values(self):
        """소수점 가격 값 - 정상 처리"""
        candle = pd.Series({
            'open': 100.123,
            'high': 105.456,
            'low': 98.789,
            'close': 102.345,
            'volume': 1000.678
        })
        valid, reason = self.validator.validate(candle)
        self.assertTrue(valid)
        self.assertEqual(reason, "OK")


if __name__ == '__main__':
    unittest.main()
