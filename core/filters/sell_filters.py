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
        손절 평가.

        ✅ Policy P-3: hts_buy 플래그는 매도 결정에 영향을 주지 않는다.
           (Issue #17 SL 스킵 로직 제거 — 외부/봇 매수 출처와 무관하게 동일 평가)
        ✅ MAX_LOSS_OVERRIDE(5%)는 보존: 어떤 상황에서도 절대 안전망.

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

        # ✅ 절대 최대 손실 안전장치 (5%) — Policy P-3와 무관하게 보존
        MAX_LOSS_OVERRIDE = 0.05
        if pnl_pct <= -MAX_LOSS_OVERRIDE:
            logger.warning(
                f"🚨 [STOP_LOSS] 절대 최대 손실 도달 | "
                f"pnl={pnl_pct:.2%} > {MAX_LOSS_OVERRIDE:.2%}"
            )
            return FilterResult(
                should_block=True,
                reason="MAX_LOSS_OVERRIDE",
                details=f"Absolute max loss reached: {pnl_pct:.2%} (threshold: -{MAX_LOSS_OVERRIDE:.2%})",
                metadata={
                    'pnl_pct': pnl_pct,
                    'threshold': -MAX_LOSS_OVERRIDE,
                    'current_price': current_price,
                    'override': True
                }
            )

        # 추적용 로그: hts_buy는 의사결정에 영향 X (Policy P-3), 진단 목적
        is_hts_buy = position.metadata.get('hts_buy', False)

        stop_loss_triggered = pnl_pct <= -self.stop_loss_pct

        logger.info(
            f"🔍 DEBUG [STOP_LOSS_CHECK] "
            f"enable=True, "
            f"stop_loss_triggered={stop_loss_triggered}, "
            f"pnl_pct={pnl_pct:.2%}, "
            f"threshold=-{self.stop_loss_pct:.2%}, "
            f"current_price={current_price}, "
            f"hts_buy={is_hts_buy}"
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
        ✅ 변경: trailing_armed 상태면 체크 스킵

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

        # ✅ NEW: Trailing Stop 활성화 상태면 Take Profit 체크 스킵
        if position.trailing_armed:
            logger.info("⏭️ Take Profit 스킵 (Trailing Stop 활성화 상태)")
            return FilterResult(
                should_block=False,
                reason="TP_SKIPPED_TS_ARMED",
                details="Take profit skipped: Trailing stop is armed"
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
    트레일링 스톱 (Trailing Stop) 필터 - 수익 기반

    ✅ 변경: Take Profit 도달 후 활성화되며, 벌어들인 수익의 N%가 사라지면 매도.
    """

    def __init__(self, trailing_stop_pct: Optional[float] = 0.10,
                 take_profit_pct: Optional[float] = 0.03,
                 use_fixed_mode: bool = False):
        """
        Args:
            trailing_stop_pct: 수익 손실률 임계값 (기본 10% = 0.10)
            take_profit_pct: 활성화 트리거 임계값 (기본 3% = 0.03)
            use_fixed_mode: 고정폭 모드 활성화 (기본 False = 비율 기반)
        """
        super().__init__(FilterCategory.CORE_STRATEGY)
        self.trailing_stop_pct = trailing_stop_pct
        self.take_profit_pct = take_profit_pct
        self.use_fixed_mode = use_fixed_mode

    def get_name(self) -> str:
        return "TrailingStopFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        ✅ 변경: 수익 기반 Trailing Stop
        1. Take Profit 도달 체크 → trailing_armed 활성화
        2. trailing_armed 상태에서 수익 기반 하락률 체크

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

        # ✅ STEP 1: Take Profit 도달 체크 (trailing_armed 활성화 트리거)
        if not position.trailing_armed:
            pnl_pct = position.get_pnl_pct(current_price)

            if pnl_pct is not None and pnl_pct >= self.take_profit_pct:
                # Take Profit 도달 → Trailing Stop 활성화
                position.activate_trailing_stop(current_price)

                # ✅ 고정폭 모드: 활성화 시점 1회 계산
                if self.use_fixed_mode:
                    activation_profit = current_price - position.avg_price
                    position.trailing_fixed_amount = activation_profit * self.trailing_stop_pct
                    position.trailing_activation_price = current_price
                    logger.info(
                        f"🔒 고정 금액 폭 설정 | "
                        f"활성화 수익=₩{activation_profit:,.0f} × {self.trailing_stop_pct:.0%} "
                        f"= ₩{position.trailing_fixed_amount:,.0f}"
                    )

                mode_str = "고정폭" if self.use_fixed_mode else "비율"
                logger.info(
                    f"🔄 AUTO-SWITCH: Take Profit 도달 ({pnl_pct:.2%}) "
                    f"→ Trailing Stop 활성화 ({mode_str}) | "
                    f"진입가=₩{position.avg_price:,.0f} 현재가=₩{current_price:,.0f}"
                )
            else:
                # 아직 Take Profit 미도달 → Trailing Stop 미작동
                return FilterResult(should_block=False, reason="TS_NOT_ARMED")

        # ✅ STEP 2: 신고가 갱신
        if current_price > position.highest_price:
            position.highest_price = current_price

        # ✅ STEP 3: Trailing Stop 체크 (모드별 분기)
        if self.use_fixed_mode:
            # ✅ 고정 금액 폭 방식
            stop_price = position.highest_price - position.trailing_fixed_amount
            triggered = current_price <= stop_price

            logger.info(
                f"🔍 DEBUG [TRAILING_STOP_FIXED] "
                f"highest=₩{position.highest_price:,.0f}, "
                f"fixed_amount=₩{position.trailing_fixed_amount:,.0f}, "
                f"stop_price=₩{stop_price:,.0f}, "
                f"current=₩{current_price:,.0f}, "
                f"triggered={triggered}"
            )

            if triggered:
                return FilterResult(
                    should_block=True,
                    reason="TRAILING_STOP_FIXED",
                    details=f"Fixed-amount trailing stop: ₩{current_price:,.0f} <= ₩{stop_price:,.0f}",
                    metadata={
                        'mode': 'fixed',
                        'highest_price': position.highest_price,
                        'fixed_amount': position.trailing_fixed_amount,
                        'stop_price': stop_price,
                        'current_price': current_price
                    }
                )
        else:
            # ✅ 기존 비율 방식 (변경 없음)
            max_profit = position.highest_price - position.avg_price
            profit_drop = position.highest_price - current_price
            profit_drop_pct = profit_drop / max_profit if max_profit > 0 else 0
            triggered = profit_drop_pct >= self.trailing_stop_pct

            logger.info(
                f"🔍 DEBUG [TRAILING_STOP_RATIO] "
                f"highest=₩{position.highest_price:,.0f}, "
                f"current=₩{current_price:,.0f}, "
                f"max_profit=₩{max_profit:,.0f}, "
                f"profit_drop=₩{profit_drop:,.0f} ({profit_drop_pct:.2%}), "
                f"threshold={self.trailing_stop_pct:.2%}, "
                f"triggered={triggered}"
            )

            if triggered:
                return FilterResult(
                    should_block=True,
                    reason="TRAILING_STOP_RATIO",
                    details=f"Ratio-based trailing stop: {profit_drop_pct:.2%} >= {self.trailing_stop_pct:.2%}",
                    metadata={
                        'mode': 'ratio',
                        'highest_price': position.highest_price,
                        'current_price': current_price,
                        'max_profit': max_profit,
                        'profit_drop': profit_drop,
                        'profit_drop_pct': profit_drop_pct
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
            current_time (datetime): 현재 시각 (timezone-aware)

        Returns:
            FilterResult: 정체 포지션 조건 충족 시 매도 신호
        """
        from datetime import datetime, timedelta

        position: PositionState = kwargs.get('position')
        current_price: float = kwargs.get('current_price')
        current_time: datetime = kwargs.get('current_time')

        if position is None or current_price is None:
            return FilterResult(
                should_block=False,
                reason="NO_DATA",
                details="Position or price data not provided"
            )

        if not position.has_position or position.entry_ts is None:
            return FilterResult(
                should_block=False,
                reason="NO_POSITION",
                details="No active position"
            )

        if current_time is None:
            logger.warning("⚠️ [STALE_POSITION] current_time not provided, skipping check")
            return FilterResult(
                should_block=False,
                reason="NO_TIME",
                details="Current time not provided"
            )

        # ✅ 실제 경과 시간 계산 (시간 기반)
        elapsed = current_time - position.entry_ts
        elapsed_hours = elapsed.total_seconds() / 3600

        # 진입 이후 최고가 갱신
        position.update_highest_since_entry(current_price)

        # 조건 체크: 시간 경과 AND 목표 수익률 미달
        if elapsed_hours >= self.stale_hours:
            max_gain = position.get_max_gain_from_entry()

            logger.info(
                f"🔍 DEBUG [STALE_POSITION_CHECK] "
                f"enable=True, "
                f"elapsed_hours={elapsed_hours:.2f}h, required_hours={self.stale_hours}h, "
                f"max_gain={max_gain:.2%} if max_gain else 'None', "
                f"threshold={self.stale_threshold_pct:.2%}, "
                f"entry_price={position.avg_price:.2f}, "
                f"entry_time={position.entry_ts}, "
                f"current_time={current_time}, "
                f"highest_since_entry={position.highest_since_entry:.2f} if position.highest_since_entry else 'None', "
                f"current_price={current_price:.2f}"
            )

            if max_gain is not None and max_gain < self.stale_threshold_pct:
                logger.info(
                    f"💤 Stale Position 감지 | "
                    f"보유시간={elapsed_hours:.2f}h (목표={self.stale_hours}h), "
                    f"최고수익률={max_gain:.2%} (목표={self.stale_threshold_pct:.2%}) | "
                    f"진입가=₩{position.avg_price:,.0f}, "
                    f"최고가=₩{position.highest_since_entry:,.0f}, "
                    f"현재가=₩{current_price:,.0f}"
                )
                return FilterResult(
                    should_block=True,
                    reason="STALE_POSITION",
                    details=f"Stale position detected: held {elapsed_hours:.2f}h (>= {self.stale_hours}h), max gain {max_gain:.2%} < {self.stale_threshold_pct:.2%}",
                    metadata={
                        'elapsed_hours': elapsed_hours,
                        'required_hours': self.stale_hours,
                        'max_gain': max_gain,
                        'threshold': self.stale_threshold_pct,
                        'entry_price': position.avg_price,
                        'entry_time': str(position.entry_ts),
                        'current_time': str(current_time),
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
