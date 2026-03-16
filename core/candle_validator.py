"""
WO-2026-001 Task 2-A: CandleValidator - 봉 데이터 유효성 검증

🔒 방어 레이어:
1. OHLC 논리 검증 (low ≤ open, close ≤ high)
2. 스파이크 감지 (임계값 5%, 경고만)
3. 유령 봉 차단 (거래량 0)
"""
import logging
import pandas as pd
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class CandleValidator:
    """
    봉 데이터 유효성 검증 클래스

    Features:
    - OHLC 논리 검증: low ≤ open, close ≤ high
    - 스파이크 감지: 전 봉 대비 급등/급락 (경고만, 차단 안 함)
    - 유령 봉 차단: 거래량 0인 봉 차단

    Example:
        >>> validator = CandleValidator(max_spike_ratio=0.05)
        >>> candle = pd.Series({"open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000})
        >>> valid, reason = validator.validate(candle)
        >>> if valid:
        ...     print("Valid candle")
        ... else:
        ...     print(f"Invalid: {reason}")
    """

    def __init__(self, max_spike_ratio: float = 0.05, continuity_tolerance_pct: float = 0.01):
        """
        Args:
            max_spike_ratio: 스파이크 감지 임계값 (기본 5%)
                           전 봉 대비 5% 이상 변동 시 경고
            continuity_tolerance_pct: 연속 봉 일관성 허용 오차 (기본 1%)
                                     open[n]과 close[n-1]의 차이가 1% 초과 시 경고
        """
        self.max_spike_ratio = max_spike_ratio
        self.continuity_tolerance_pct = continuity_tolerance_pct
        self.prev_close: Optional[float] = None

    def validate(self, candle: pd.Series) -> Tuple[bool, str]:
        """
        봉 데이터 유효성 검증

        Args:
            candle: 봉 데이터 (Series with keys: open, high, low, close, volume)

        Returns:
            (True, "OK") 또는 (False, "실패 사유")

        Validation Rules:
            1. OHLC 논리: low ≤ open ≤ high AND low ≤ close ≤ high
            2. 스파이크: abs(close - prev_close) / prev_close > max_spike_ratio (경고만)
            3. 유령 봉: volume == 0 (차단)
        """
        try:
            # 필수 키 확인 (대소문자 구분 없이)
            required_keys = ['open', 'high', 'low', 'close', 'volume']
            missing_keys = []
            for key in required_keys:
                # 소문자, Capitalized, UPPERCASE 모두 시도
                if (key not in candle.index and
                    key.capitalize() not in candle.index and
                    key.upper() not in candle.index):
                    missing_keys.append(key)

            if missing_keys:
                return False, f"필수 키 누락: {missing_keys}"

            # 값 추출 (대소문자 구분 없이)
            close = self._get_value(candle, 'close')
            high = self._get_value(candle, 'high')
            low = self._get_value(candle, 'low')
            open_ = self._get_value(candle, 'open')
            volume = self._get_value(candle, 'volume')

            # ============================================================
            # 1. OHLC 논리 검증
            # ============================================================
            if not (low <= open_ <= high and low <= close <= high):
                return False, (
                    f"OHLC 논리 오류: O={open_:.2f} H={high:.2f} L={low:.2f} C={close:.2f}"
                )

            # ============================================================
            # 2. 연속 봉 일관성 검증 (경고만)
            # ============================================================
            # open[n]과 close[n-1]이 일치해야 함 (갭 거래 제외)
            if self.prev_close is not None and self.prev_close > 0:
                continuity_diff_pct = abs(open_ - self.prev_close) / self.prev_close

                if continuity_diff_pct > self.continuity_tolerance_pct:
                    logger.warning(
                        f"[VALIDATOR] 봉 불연속 감지 ⚠️ | "
                        f"close[n-1]={self.prev_close:.0f} vs open[n]={open_:.0f} | "
                        f"차이={continuity_diff_pct:.2%} (허용={self.continuity_tolerance_pct:.2%}) | "
                        f"(경고만, 봉 스킵하지 않음)"
                    )
                    # ⚠️ 중요: 경고만 하고 검증은 통과 (갭 거래, API 지연 등 정상적인 불연속 존재)

            # ============================================================
            # 3. 스파이크 감지 (경고만, 스킵하지 않음)
            # ============================================================
            if self.prev_close is not None and self.prev_close > 0:
                ratio = abs(close - self.prev_close) / self.prev_close

                if ratio > self.max_spike_ratio:
                    logger.warning(
                        f"[VALIDATOR] 종가 급변 감지 ⚠️ | "
                        f"변화율={ratio:.2%} | prev={self.prev_close:.0f} | close={close:.0f} | "
                        f"(경고만, 봉 스킵하지 않음)"
                    )
                    # ⚠️ 중요: 경고만 하고 검증은 통과

            # ============================================================
            # 4. 유령 봉 차단
            # ============================================================
            if volume == 0:
                return False, "거래량 0 — 유령 봉"

            # ✅ 모든 검증 통과
            self.prev_close = close
            return True, "OK"

        except Exception as e:
            logger.error(f"[VALIDATOR] 예외 발생: {e}")
            return False, f"검증 예외: {e}"

    def _get_value(self, series: pd.Series, key: str) -> float:
        """
        대소문자 구분 없이 값 추출

        Args:
            series: pd.Series
            key: 키 (예: 'close')

        Returns:
            float 값

        Raises:
            KeyError: 키가 없을 경우
        """
        # 소문자 시도
        if key in series.index:
            return float(series[key])

        # 대문자 시도
        key_cap = key.capitalize()
        if key_cap in series.index:
            return float(series[key_cap])

        # 대문자만 시도
        key_upper = key.upper()
        if key_upper in series.index:
            return float(series[key_upper])

        # 모두 실패 → KeyError
        raise KeyError(f"Key not found: {key} (tried: {key}, {key_cap}, {key_upper})")

    def reset(self):
        """이전 종가 초기화 (새로운 검증 세션 시작)"""
        self.prev_close = None
        logger.info("[VALIDATOR] 초기화 완료")
