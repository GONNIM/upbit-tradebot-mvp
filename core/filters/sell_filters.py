"""
매도 필터 구현
"""
import logging
from typing import Optional

from .base import BaseFilter, FilterResult, FilterCategory
from core.candle_buffer import Bar
from core.position_state import PositionState

logger = logging.getLogger(__name__)


class StopLossFilter(BaseFilter):
    """
    손절 (Stop Loss) 필터

    현재 수익률이 손절 임계값 이하로 떨어지면 매도 신호 발생.
    """

    def __init__(self, stop_loss_pct: float = 0.02):
        """
        Args:
            stop_loss_pct: 손절 임계값 (기본 2% = 0.02)
        """
        super().__init__(FilterCategory.CORE_STRATEGY)
        self.stop_loss_pct = stop_loss_pct

    def get_name(self) -> str:
        return "StopLossFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            position (PositionState): 현재 포지션
            current_price (float): 현재가

        Returns:
            FilterResult: 손절 조건 충족 시 매도 신호
        """
        position: PositionState = kwargs.get('position')
        current_price: float = kwargs.get('current_price')

        if position is None or current_price is None:
            return FilterResult(
                should_block=False,
                reason="NO_DATA",
                details="Position or price data not provided"
            )

        pnl_pct = position.get_pnl_pct(current_price)
        if pnl_pct is None:
            return FilterResult(
                should_block=False,
                reason="NO_PNL",
                details="PnL calculation failed"
            )

        stop_loss_triggered = pnl_pct <= -self.stop_loss_pct

        logger.info(
            f"🔍 DEBUG [STOP_LOSS_CHECK] "
            f"enable=True, "
            f"stop_loss_triggered={stop_loss_triggered}, "
            f"pnl_pct={pnl_pct:.2%}, "
            f"threshold=-{self.stop_loss_pct:.2%}, "
            f"current_price={current_price}"
        )

        if stop_loss_triggered:
            logger.info(
                f"🛡️ Stop Loss triggered | pnl={pnl_pct:.2%} sl={self.stop_loss_pct:.2%}"
            )
            return FilterResult(
                should_block=True,
                reason="STOP_LOSS",
                details=f"Stop loss triggered: {pnl_pct:.2%} (threshold: -{self.stop_loss_pct:.2%})",
                metadata={
                    'pnl_pct': pnl_pct,
                    'threshold': -self.stop_loss_pct,
                    'current_price': current_price
                }
            )

        return FilterResult(
            should_block=False,
            reason="SL_OK"
        )


class TakeProfitFilter(BaseFilter):
    """
    익절 (Take Profit) 필터

    현재 수익률이 익절 임계값 이상이면 매도 신호 발생.
    """

    def __init__(self, take_profit_pct: float = 0.03):
        """
        Args:
            take_profit_pct: 익절 임계값 (기본 3% = 0.03)
        """
        super().__init__(FilterCategory.CORE_STRATEGY)
        self.take_profit_pct = take_profit_pct

    def get_name(self) -> str:
        return "TakeProfitFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            position (PositionState): 현재 포지션
            current_price (float): 현재가

        Returns:
            FilterResult: 익절 조건 충족 시 매도 신호
        """
        position: PositionState = kwargs.get('position')
        current_price: float = kwargs.get('current_price')

        if position is None or current_price is None:
            return FilterResult(
                should_block=False,
                reason="NO_DATA",
                details="Position or price data not provided"
            )

        pnl_pct = position.get_pnl_pct(current_price)
        if pnl_pct is None:
            return FilterResult(
                should_block=False,
                reason="NO_PNL",
                details="PnL calculation failed"
            )

        take_profit_triggered = pnl_pct >= self.take_profit_pct

        logger.info(
            f"🔍 DEBUG [TAKE_PROFIT_CHECK] "
            f"enable_take_profit=True, "
            f"take_profit_triggered={take_profit_triggered}, "
            f"pnl_pct={pnl_pct:.2%}, "
            f"threshold={self.take_profit_pct:.2%}, "
            f"current_price={current_price}"
        )

        if take_profit_triggered:
            logger.info(
                f"🎯 Take Profit triggered | pnl={pnl_pct:.2%} tp={self.take_profit_pct:.2%}"
            )
            return FilterResult(
                should_block=True,
                reason="TAKE_PROFIT",
                details=f"Take profit triggered: {pnl_pct:.2%} (threshold: {self.take_profit_pct:.2%})",
                metadata={
                    'pnl_pct': pnl_pct,
                    'threshold': self.take_profit_pct,
                    'current_price': current_price
                }
            )

        return FilterResult(
            should_block=False,
            reason="TP_OK"
        )


class TrailingStopFilter(BaseFilter):
    """
    트레일링 스톱 (Trailing Stop) 필터

    최고가 대비 일정 비율 이상 하락 시 매도 신호 발생.
    """

    def __init__(self, trailing_stop_pct: Optional[float] = 0.02):
        """
        Args:
            trailing_stop_pct: 트레일링 스톱 비율 (기본 2% = 0.02)
        """
        super().__init__(FilterCategory.CORE_STRATEGY)
        self.trailing_stop_pct = trailing_stop_pct

    def get_name(self) -> str:
        return "TrailingStopFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            position (PositionState): 현재 포지션
            current_price (float): 현재가

        Returns:
            FilterResult: 트레일링 스톱 조건 충족 시 매도 신호
        """
        position: PositionState = kwargs.get('position')
        current_price: float = kwargs.get('current_price')

        if position is None or current_price is None:
            return FilterResult(
                should_block=False,
                reason="NO_DATA",
                details="Position or price data not provided"
            )

        if self.trailing_stop_pct is None:
            return FilterResult(
                should_block=False,
                reason="NO_TS_PCT",
                details="Trailing stop percentage not set"
            )

        highest_price = position.highest_price
        trailing_stop_triggered = position.arm_trailing_stop(self.trailing_stop_pct, current_price)

        ts_pct_str = f"{self.trailing_stop_pct:.2%}" if self.trailing_stop_pct is not None else "None"
        logger.info(
            f"🔍 DEBUG [TRAILING_STOP_CHECK] "
            f"enable_trailing_stop=True, "
            f"trailing_stop_triggered={trailing_stop_triggered}, "
            f"trailing_stop_pct={ts_pct_str}, "
            f"highest_price={highest_price}, "
            f"current_price={current_price}"
        )

        if trailing_stop_triggered:
            logger.info(
                f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
            )
            return FilterResult(
                should_block=True,
                reason="TRAILING_STOP",
                details=f"Trailing stop triggered: {self.trailing_stop_pct:.2%}",
                metadata={
                    'trailing_stop_pct': self.trailing_stop_pct,
                    'highest_price': highest_price,
                    'current_price': current_price
                }
            )

        return FilterResult(
            should_block=False,
            reason="TS_OK"
        )


class DeadCrossFilter(BaseFilter):
    """
    데드 크로스 (Dead Cross) 필터

    Fast EMA가 Slow EMA 아래로 하향 돌파 시 매도 신호 발생.
    """

    def __init__(self):
        super().__init__(FilterCategory.CORE_STRATEGY)

    def get_name(self) -> str:
        return "DeadCrossFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            ema_dead_cross (bool): 데드 크로스 발생 여부
            ema_fast (float): 현재 Fast EMA
            ema_slow (float): 현재 Slow EMA
            prev_ema_fast (float): 이전 Fast EMA
            prev_ema_slow (float): 이전 Slow EMA

        Returns:
            FilterResult: 데드 크로스 발생 시 매도 신호
        """
        ema_dead_cross: bool = kwargs.get('ema_dead_cross', False)
        ema_fast: Optional[float] = kwargs.get('ema_fast')
        ema_slow: Optional[float] = kwargs.get('ema_slow')
        prev_ema_fast: Optional[float] = kwargs.get('prev_ema_fast')
        prev_ema_slow: Optional[float] = kwargs.get('prev_ema_slow')

        curr_fast_str = f"{ema_fast:.2f}" if ema_fast is not None else "None"
        curr_slow_str = f"{ema_slow:.2f}" if ema_slow is not None else "None"
        logger.info(
            f"🔍 DEBUG [DEAD_CROSS_CHECK] "
            f"enable_dead_cross=True, "
            f"ema_dead_cross={ema_dead_cross}, "
            f"prev_fast={prev_ema_fast}, prev_slow={prev_ema_slow}, "
            f"curr_fast={curr_fast_str}, curr_slow={curr_slow_str}"
        )

        if ema_dead_cross:
            fast_str = f"{ema_fast:.2f}" if ema_fast is not None else "None"
            slow_str = f"{ema_slow:.2f}" if ema_slow is not None else "None"
            logger.info(
                f"🔻 EMA Dead Cross | fast={fast_str} slow={slow_str}"
            )
            return FilterResult(
                should_block=True,
                reason="EMA_DC",
                details=f"EMA Dead Cross detected",
                metadata={
                    'ema_fast': ema_fast,
                    'ema_slow': ema_slow,
                    'prev_ema_fast': prev_ema_fast,
                    'prev_ema_slow': prev_ema_slow
                }
            )

        return FilterResult(
            should_block=False,
            reason="DC_OK"
        )


class StalePositionFilter(BaseFilter):
    """
    정체 포지션 강제매도 필터

    일정 시간 보유했지만 목표 수익률을 달성하지 못한 정체 포지션을 강제 매도.
    """

    def __init__(self, stale_hours: float = 2.0, stale_threshold_pct: float = 0.01):
        """
        Args:
            stale_hours: 정체 판단 기준 시간 (시간 단위)
            stale_threshold_pct: 최소 수익률 목표 (기본 1% = 0.01)
        """
        super().__init__(FilterCategory.SELL_AUXILIARY)
        self.stale_hours = stale_hours
        self.stale_threshold_pct = stale_threshold_pct

    def get_name(self) -> str:
        return "StalePositionFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            position (PositionState): 현재 포지션
            current_price (float): 현재가
            bars_held (int): 보유 봉 개수
            interval_min (int): 봉 간격 (분)

        Returns:
            FilterResult: 정체 포지션 조건 충족 시 매도 신호
        """
        position: PositionState = kwargs.get('position')
        current_price: float = kwargs.get('current_price')
        bars_held: int = kwargs.get('bars_held', 0)
        interval_min: int = kwargs.get('interval_min', 3)

        if position is None or current_price is None:
            return FilterResult(
                should_block=False,
                reason="NO_DATA",
                details="Position or price data not provided"
            )

        # 필요 봉 개수 계산 (예: 2시간 = 120분 / 3분봉 = 40개)
        required_bars = int(self.stale_hours * 60 / interval_min)

        # 진입 이후 최고가 갱신
        position.update_highest_since_entry(current_price)

        # 조건 체크: 시간 경과 AND 목표 수익률 미달
        if bars_held >= required_bars:
            max_gain = position.get_max_gain_from_entry()

            logger.info(
                f"🔍 DEBUG [STALE_POSITION_CHECK] "
                f"enable=True, "
                f"bars_held={bars_held}, required_bars={required_bars}, "
                f"max_gain={max_gain:.2%} if max_gain else 'None', "
                f"threshold={self.stale_threshold_pct:.2%}, "
                f"entry_price={position.avg_price:.2f}, "
                f"highest_since_entry={position.highest_since_entry:.2f} if position.highest_since_entry else 'None', "
                f"current_price={current_price:.2f}"
            )

            if max_gain is not None and max_gain < self.stale_threshold_pct:
                logger.info(
                    f"💤 Stale Position 감지 | "
                    f"보유시간={bars_held}봉 (목표={required_bars}봉, {self.stale_hours}h), "
                    f"최고수익률={max_gain:.2%} (목표={self.stale_threshold_pct:.2%}) | "
                    f"진입가=₩{position.avg_price:,.0f}, "
                    f"최고가=₩{position.highest_since_entry:,.0f}, "
                    f"현재가=₩{current_price:,.0f}"
                )
                return FilterResult(
                    should_block=True,
                    reason="STALE_POSITION",
                    details=f"Stale position detected: held {bars_held} bars ({self.stale_hours}h), max gain {max_gain:.2%} < {self.stale_threshold_pct:.2%}",
                    metadata={
                        'bars_held': bars_held,
                        'required_bars': required_bars,
                        'max_gain': max_gain,
                        'threshold': self.stale_threshold_pct,
                        'entry_price': position.avg_price,
                        'highest_since_entry': position.highest_since_entry,
                        'current_price': current_price
                    }
                )

        return FilterResult(
            should_block=False,
            reason="STALE_OK"
        )

    def update_params(self, stale_hours: float = None, stale_threshold_pct: float = None):
        """정체 포지션 파라미터 업데이트"""
        if stale_hours is not None:
            self.stale_hours = stale_hours
        if stale_threshold_pct is not None:
            self.stale_threshold_pct = stale_threshold_pct
        logger.info(
            f"📊 StalePositionFilter params updated: "
            f"hours={self.stale_hours}h, threshold={self.stale_threshold_pct:.2%}"
        )
