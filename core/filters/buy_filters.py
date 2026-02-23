"""
매수 필터 구현
"""
import logging
from typing import Optional

from .base import BaseFilter, FilterResult, FilterCategory
from core.candle_buffer import Bar

logger = logging.getLogger(__name__)


class SlowEmaSurgeFilter(BaseFilter):
    """
    Slow EMA 급등 차단 필터

    현재가가 Slow EMA 대비 일정 비율 이상 급등했을 때 매수를 차단함.
    급등 후 매수는 고점 매수 리스크가 높으므로 차단.
    """

    def __init__(self, threshold_pct: float = 0.01):
        """
        Args:
            threshold_pct: 급등 임계값 (기본 1% = 0.01)
        """
        super().__init__(FilterCategory.BUY_FILTER)
        self.threshold_pct = threshold_pct

    def get_name(self) -> str:
        return "SlowEmaSurgeFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            bar (Bar): 현재 캔들
            ema_slow (float): Slow EMA 값

        Returns:
            FilterResult: 급등 시 차단
        """
        bar: Bar = kwargs.get('bar')
        ema_slow: Optional[float] = kwargs.get('ema_slow')

        if bar is None:
            return FilterResult(
                should_block=False,
                reason="NO_BAR",
                details="Bar data not provided"
            )

        if ema_slow is None or ema_slow <= 0:
            logger.warning(f"⚠️ Slow EMA not available for surge filter, allowing trade")
            return FilterResult(
                should_block=False,
                reason="NO_EMA",
                details="Slow EMA not available"
            )

        # 급등률 계산
        surge_pct = (bar.close - ema_slow) / ema_slow

        if surge_pct > self.threshold_pct:
            return FilterResult(
                should_block=True,
                reason="SURGE_FILTER",
                details=f"Price surge detected: {surge_pct*100:.2f}% above Slow EMA (threshold: {self.threshold_pct*100:.1f}%)",
                metadata={
                    'surge_pct': surge_pct,
                    'threshold_pct': self.threshold_pct,
                    'price': bar.close,
                    'ema_slow': ema_slow
                }
            )

        return FilterResult(
            should_block=False,
            reason="SURGE_OK",
            details=f"Surge check passed: {surge_pct*100:.2f}%"
        )

    def update_threshold(self, threshold_pct: float):
        """급등 임계값 업데이트"""
        self.threshold_pct = threshold_pct
        logger.info(f"📊 SlowEmaSurgeFilter threshold updated: {threshold_pct*100:.1f}%")
