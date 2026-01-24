"""
증분 기반 전략 구현 (Backtesting 라이브러리 미사용)
- IncrementalMACDStrategy: MACD 기반 전략
- IncrementalEMAStrategy: EMA 기반 전략
"""
from core.strategy_action import Action
from core.candle_buffer import Bar
from core.position_state import PositionState
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class IncrementalMACDStrategy:
    """
    증분 기반 MACD 전략
    - Backtesting 라이브러리 없이 순수하게 on_bar() 기반으로 동작
    - IndicatorState와 PositionState를 받아서 액션 반환
    """

    def __init__(
        self,
        macd_threshold: float = 0.0,
        take_profit: float = 0.03,
        stop_loss: float = 0.01,
        macd_crossover_threshold: float = 0.0,
        min_holding_period: int = 0,
        trailing_stop_pct: Optional[float] = None,
    ):
        """
        Args:
            macd_threshold: MACD 임계값 (매수 시 MACD가 이 값 이상이어야 함)
            take_profit: 익절 비율 (예: 0.03 = 3%)
            stop_loss: 손절 비율 (예: 0.01 = 1%)
            macd_crossover_threshold: 크로스오버 추가 조건 (예: 0.0)
            min_holding_period: 최소 보유 기간 (bar 수)
            trailing_stop_pct: Trailing Stop 비율 (예: 0.02 = 2%)
        """
        self.macd_threshold = macd_threshold
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.macd_crossover_threshold = macd_crossover_threshold
        self.min_holding_period = min_holding_period
        self.trailing_stop_pct = trailing_stop_pct

    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        position: PositionState,
        current_bar_idx: int,
    ) -> Action:
        """
        새 봉 1개 기준으로 전략 평가

        Args:
            bar: 확정된 봉 (is_closed=True)
            indicators: IndicatorState.get_snapshot() 결과
            position: PositionState 객체
            current_bar_idx: 현재 bar index

        Returns:
            Action: BUY/SELL/HOLD
        """
        macd = indicators["macd"]
        signal = indicators["signal"]
        prev_macd = indicators["prev_macd"]
        prev_signal = indicators["prev_signal"]

        # 골든크로스 판정
        golden_cross = (
            prev_macd is not None
            and prev_signal is not None
            and prev_macd <= prev_signal
            and macd > signal
        )

        # 데드크로스 판정
        dead_cross = (
            prev_macd is not None
            and prev_signal is not None
            and prev_macd >= prev_signal
            and macd < signal
        )

        # ========================================
        # BUY 조건 (포지션 없을 때)
        # ========================================
        if not position.has_position:
            if golden_cross and macd >= self.macd_threshold:
                logger.info(
                    f"🔔 MACD Golden Cross | macd={macd:.6f} signal={signal:.6f} "
                    f"threshold={self.macd_threshold:.6f}"
                )
                return Action.BUY

        # ========================================
        # SELL 조건 (포지션 있을 때)
        # ========================================
        else:
            current_price = bar.close

            # 최소 보유 기간 체크
            bars_held = position.get_bars_held(current_bar_idx)
            if bars_held < self.min_holding_period:
                logger.debug(
                    f"⏳ Min holding period | held={bars_held} required={self.min_holding_period}"
                )
                return Action.HOLD

            # Highest Price 갱신 (Trailing Stop용)
            position.update_highest_price(current_price)

            # Stop Loss 체크
            pnl_pct = position.get_pnl_pct(current_price)
            if pnl_pct is not None and pnl_pct <= -self.stop_loss:
                logger.info(
                    f"🛡️ Stop Loss triggered | pnl={pnl_pct:.2%} sl={self.stop_loss:.2%}"
                )
                return Action.SELL

            # Take Profit 체크
            if pnl_pct is not None and pnl_pct >= self.take_profit:
                logger.info(
                    f"🎯 Take Profit triggered | pnl={pnl_pct:.2%} tp={self.take_profit:.2%}"
                )
                return Action.SELL

            # Trailing Stop 체크
            if self.trailing_stop_pct is not None:
                if position.arm_trailing_stop(self.trailing_stop_pct, current_price):
                    logger.info(
                        f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
                    )
                    return Action.SELL

            # Dead Cross 체크
            if dead_cross:
                logger.info(
                    f"🔻 MACD Dead Cross | macd={macd:.6f} signal={signal:.6f}"
                )
                return Action.SELL

        return Action.HOLD


class IncrementalEMAStrategy:
    """
    증분 기반 EMA 전략
    - Fast EMA / Slow EMA 크로스 기반
    """

    def __init__(
        self,
        take_profit: float = 0.03,
        stop_loss: float = 0.01,
        min_holding_period: int = 0,
        trailing_stop_pct: Optional[float] = None,
        use_base_ema: bool = True,  # 기준선 사용 여부
    ):
        """
        Args:
            take_profit: 익절 비율
            stop_loss: 손절 비율
            min_holding_period: 최소 보유 기간
            trailing_stop_pct: Trailing Stop 비율
            use_base_ema: 기준선(base_ema) 사용 여부
        """
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.min_holding_period = min_holding_period
        self.trailing_stop_pct = trailing_stop_pct
        self.use_base_ema = use_base_ema

    def on_bar(
        self,
        bar: Bar,
        indicators: Dict[str, Any],
        position: PositionState,
        current_bar_idx: int,
    ) -> Action:
        """
        새 봉 1개 기준으로 EMA 전략 평가

        Args:
            bar: 확정된 봉
            indicators: IndicatorState.get_snapshot()
            position: PositionState
            current_bar_idx: 현재 bar index

        Returns:
            Action: BUY/SELL/HOLD
        """
        ema_fast = indicators["ema_fast"]
        ema_slow = indicators["ema_slow"]
        ema_base = indicators["ema_base"]
        prev_ema_fast = indicators["prev_ema_fast"]
        prev_ema_slow = indicators["prev_ema_slow"]

        # EMA 골든크로스 판정
        ema_golden_cross = (
            prev_ema_fast is not None
            and prev_ema_slow is not None
            and prev_ema_fast <= prev_ema_slow
            and ema_fast > ema_slow
        )

        # EMA 데드크로스 판정
        ema_dead_cross = (
            prev_ema_fast is not None
            and prev_ema_slow is not None
            and prev_ema_fast >= prev_ema_slow
            and ema_fast < ema_slow
        )

        # ========================================
        # BUY 조건
        # ========================================
        if not position.has_position:
            buy_signal = ema_golden_cross

            # 기준선 조건 추가
            if self.use_base_ema and ema_base is not None:
                above_base = bar.close > ema_base
                if not above_base:
                    logger.debug(
                        f"⛔ EMA GC but below base_ema | close={bar.close:.2f} base={ema_base:.2f}"
                    )
                    return Action.HOLD
                buy_signal = buy_signal and above_base

            if buy_signal:
                logger.info(
                    f"🔔 EMA Golden Cross | fast={ema_fast:.2f} slow={ema_slow:.2f}"
                )
                return Action.BUY

        # ========================================
        # SELL 조건
        # ========================================
        else:
            current_price = bar.close

            # 최소 보유 기간 체크
            bars_held = position.get_bars_held(current_bar_idx)
            if bars_held < self.min_holding_period:
                logger.debug(
                    f"⏳ Min holding period | held={bars_held} required={self.min_holding_period}"
                )
                return Action.HOLD

            # Highest Price 갱신
            position.update_highest_price(current_price)

            # Stop Loss 체크
            pnl_pct = position.get_pnl_pct(current_price)
            if pnl_pct is not None and pnl_pct <= -self.stop_loss:
                logger.info(
                    f"🛡️ Stop Loss triggered | pnl={pnl_pct:.2%} sl={self.stop_loss:.2%}"
                )
                return Action.SELL

            # Take Profit 체크
            if pnl_pct is not None and pnl_pct >= self.take_profit:
                logger.info(
                    f"🎯 Take Profit triggered | pnl={pnl_pct:.2%} tp={self.take_profit:.2%}"
                )
                return Action.SELL

            # Trailing Stop 체크
            if self.trailing_stop_pct is not None:
                if position.arm_trailing_stop(self.trailing_stop_pct, current_price):
                    logger.info(
                        f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
                    )
                    return Action.SELL

            # EMA Dead Cross 체크
            if ema_dead_cross:
                logger.info(
                    f"🔻 EMA Dead Cross | fast={ema_fast:.2f} slow={ema_slow:.2f}"
                )
                return Action.SELL

        return Action.HOLD
