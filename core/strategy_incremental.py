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
        user_id: str,
        ticker: str,
        macd_threshold: float = 0.0,
        take_profit: float = 0.03,
        stop_loss: float = 0.01,
        macd_crossover_threshold: float = 0.0,
        min_holding_period: int = 0,
        trailing_stop_pct: Optional[float] = None,
        buy_conditions: Optional[Dict[str, bool]] = None,  # ✅ 조건 파일 설정 (BUY)
        sell_conditions: Optional[Dict[str, bool]] = None,  # ✅ 조건 파일 설정 (SELL)
    ):
        """
        Args:
            user_id: 사용자 ID
            ticker: 거래 티커 (예: KRW-SUI)
            macd_threshold: MACD 임계값 (매수 시 MACD가 이 값 이상이어야 함)
            take_profit: 익절 비율 (예: 0.03 = 3%)
            stop_loss: 손절 비율 (예: 0.01 = 1%)
            macd_crossover_threshold: 크로스오버 추가 조건 (예: 0.0)
            min_holding_period: 최소 보유 기간 (bar 수)
            trailing_stop_pct: Trailing Stop 비율 (예: 0.02 = 2%)
            buy_conditions: 매수 조건 ON/OFF 설정 (buy_sell_conditions.json의 buy 섹션)
            sell_conditions: 매도 조건 ON/OFF 설정 (buy_sell_conditions.json의 sell 섹션)
        """
        self.user_id = user_id
        self.ticker = ticker
        self.macd_threshold = macd_threshold
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.macd_crossover_threshold = macd_crossover_threshold
        self.min_holding_period = min_holding_period
        self.trailing_stop_pct = trailing_stop_pct

        # ✅ BUY 조건 파일 설정 (기본값: 모두 True)
        self.buy_conditions = buy_conditions or {}
        self.enable_golden_cross = self.buy_conditions.get("golden_cross", True)
        self.enable_macd_positive = self.buy_conditions.get("macd_positive", True)
        self.enable_signal_positive = self.buy_conditions.get("signal_positive", True)
        self.enable_bullish_candle = self.buy_conditions.get("bullish_candle", True)
        self.enable_macd_trending_up = self.buy_conditions.get("macd_trending_up", True)
        self.enable_above_ma20 = self.buy_conditions.get("above_ma20", True)
        self.enable_above_ma60 = self.buy_conditions.get("above_ma60", True)

        logger.info(
            f"[MACD Strategy] Buy conditions: "
            f"golden_cross={self.enable_golden_cross}, "
            f"macd_positive={self.enable_macd_positive}, "
            f"signal_positive={self.enable_signal_positive}, "
            f"bullish_candle={self.enable_bullish_candle}, "
            f"macd_trending_up={self.enable_macd_trending_up}, "
            f"above_ma20={self.enable_above_ma20}, "
            f"above_ma60={self.enable_above_ma60}"
        )

        # ✅ SELL 조건 파일 설정 (기본값: 모두 True)
        self.sell_conditions = sell_conditions or {}
        self.enable_stop_loss = self.sell_conditions.get("stop_loss", True)
        self.enable_take_profit = self.sell_conditions.get("take_profit", True)
        self.enable_trailing_stop = self.sell_conditions.get("trailing_stop", True)
        self.enable_dead_cross = self.sell_conditions.get("dead_cross", True)

        logger.info(
            f"[MACD Strategy] Sell conditions: "
            f"stop_loss={self.enable_stop_loss}, "
            f"take_profit={self.enable_take_profit}, "
            f"trailing_stop={self.enable_trailing_stop}, "
            f"dead_cross={self.enable_dead_cross}"
        )

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
            # ✅ Golden Cross 체크 (조건 파일에서 ON일 때만)
            if self.enable_golden_cross:
                if not golden_cross:
                    logger.info(f"⏭️ Golden Cross not detected")
                    return Action.HOLD
                if macd < self.macd_threshold:
                    logger.info(
                        f"⏭️ MACD below threshold | macd={macd:.6f} threshold={self.macd_threshold:.6f}"
                    )
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Golden Cross disabled")

            # ✅ MACD Positive 체크 (조건 파일에서 ON일 때만)
            if self.enable_macd_positive:
                if macd <= 0:
                    logger.info(f"⏭️ MACD not positive | macd={macd:.6f}")
                    return Action.HOLD
            else:
                logger.info(f"⏭️ MACD Positive disabled")

            # ✅ Signal Positive 체크 (조건 파일에서 ON일 때만)
            if self.enable_signal_positive:
                if signal <= 0:
                    logger.info(f"⏭️ Signal not positive | signal={signal:.6f}")
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Signal Positive disabled")

            # ✅ Bullish Candle 체크 (조건 파일에서 ON일 때만)
            if self.enable_bullish_candle:
                if bar.close <= bar.open:
                    logger.info(
                        f"⏭️ Not bullish candle | close={bar.close:.2f} open={bar.open:.2f}"
                    )
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Bullish Candle disabled")

            # ✅ MACD Trending Up 체크 (조건 파일에서 ON일 때만)
            if self.enable_macd_trending_up:
                if prev_macd is not None and macd <= prev_macd:
                    logger.info(
                        f"⏭️ MACD not trending up | macd={macd:.6f} prev={prev_macd:.6f}"
                    )
                    return Action.HOLD
            else:
                logger.info(f"⏭️ MACD Trending Up disabled")

            # ✅ Above MA20 체크 (조건 파일에서 ON일 때만)
            if self.enable_above_ma20:
                ma20 = indicators.get("ma20")
                if ma20 is not None and bar.close <= ma20:
                    logger.info(f"⏭️ Not above MA20 | close={bar.close:.2f} ma20={ma20:.2f}")
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Above MA20 disabled")

            # ✅ Above MA60 체크 (조건 파일에서 ON일 때만)
            if self.enable_above_ma60:
                ma60 = indicators.get("ma60")
                if ma60 is not None and bar.close <= ma60:
                    logger.info(f"⏭️ Not above MA60 | close={bar.close:.2f} ma60={ma60:.2f}")
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Above MA60 disabled")

            # 모든 조건 통과 시 매수
            logger.info(
                f"🔔 MACD Buy Signal | macd={macd:.6f} signal={signal:.6f} "
                f"threshold={self.macd_threshold:.6f}"
            )
            return Action.BUY

        # ========================================
        # SELL 조건 (포지션 있을 때)
        # ========================================
        else:
            current_price = bar.close

            # 🔍 TRACE: SELL 블록 진입 확인
            logger.info(f"🔥 [SELL_BLOCK_ENTRY] MACD Strategy sell evaluation started | bar_idx={current_bar_idx}")

            # 최소 보유 기간 체크
            bars_held = position.get_bars_held(current_bar_idx)

            # ✅ bars_held 음수 보정: 봇 재시작으로 인한 entry_bar 불일치 해결
            if bars_held <= 0:
                from services.db import estimate_bars_held_from_audit
                bars_held_from_audit = estimate_bars_held_from_audit(self.user_id, self.ticker)
                logger.warning(
                    f"⚠️ [MACD] bars_held={bars_held} (음수/0) 감지 → DB 감사로그 기준으로 보정: {bars_held_from_audit}"
                )
                bars_held = bars_held_from_audit

            logger.info(
                f"🔍 [MIN_HOLDING_CHECK] bars_held={bars_held}, min_required={self.min_holding_period}, "
                f"will_skip={bars_held < self.min_holding_period}"
            )
            if bars_held < self.min_holding_period:
                logger.info(
                    f"⏳ Min holding period not met | held={bars_held} required={self.min_holding_period} → SKIP"
                )
                return Action.HOLD

            # Highest Price 갱신 (Trailing Stop용)
            position.update_highest_price(current_price)

            # ✅ Stop Loss 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Stop Loss 조건 및 활성화 상태 로그 추가
            pnl_pct = position.get_pnl_pct(current_price)
            stop_loss_triggered = pnl_pct is not None and pnl_pct <= -self.stop_loss

            logger.info(
                f"🔍 DEBUG [STOP_LOSS_CHECK] "
                f"enable_stop_loss={self.enable_stop_loss}, "
                f"stop_loss_triggered={stop_loss_triggered}, "
                f"pnl_pct={pnl_pct:.2%} if pnl_pct else 'None', "
                f"threshold=-{self.stop_loss:.2%}, "
                f"current_price={current_price}"
            )

            if self.enable_stop_loss:
                if stop_loss_triggered:
                    logger.info(
                        f"🛡️ Stop Loss triggered | pnl={pnl_pct:.2%} sl={self.stop_loss:.2%}"
                    )
                    return Action.SELL
            else:
                if stop_loss_triggered:
                    logger.info(f"⏭️ Stop Loss disabled but condition met | pnl={pnl_pct:.2%}")

            # ✅ Take Profit 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Take Profit 조건 및 활성화 상태 로그 추가
            take_profit_triggered = pnl_pct is not None and pnl_pct >= self.take_profit

            logger.info(
                f"🔍 DEBUG [TAKE_PROFIT_CHECK] "
                f"enable_take_profit={self.enable_take_profit}, "
                f"take_profit_triggered={take_profit_triggered}, "
                f"pnl_pct={pnl_pct:.2%} if pnl_pct else 'None', "
                f"threshold={self.take_profit:.2%}, "
                f"current_price={current_price}"
            )

            if self.enable_take_profit:
                if take_profit_triggered:
                    logger.info(
                        f"🎯 Take Profit triggered | pnl={pnl_pct:.2%} tp={self.take_profit:.2%}"
                    )
                    return Action.SELL
            else:
                if take_profit_triggered:
                    logger.info(f"⏭️ Take Profit disabled but condition met | pnl={pnl_pct:.2%}")

            # ✅ Trailing Stop 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Trailing Stop 조건 및 활성화 상태 로그 추가
            highest_price = position.highest_price
            trailing_stop_triggered = False
            if self.trailing_stop_pct is not None:
                trailing_stop_triggered = position.arm_trailing_stop(self.trailing_stop_pct, current_price)

            logger.info(
                f"🔍 DEBUG [TRAILING_STOP_CHECK] "
                f"enable_trailing_stop={self.enable_trailing_stop}, "
                f"trailing_stop_triggered={trailing_stop_triggered}, "
                f"trailing_stop_pct={self.trailing_stop_pct:.2%} if self.trailing_stop_pct else 'None', "
                f"highest_price={highest_price}, "
                f"current_price={current_price}"
            )

            if self.enable_trailing_stop:
                if trailing_stop_triggered:
                    logger.info(
                        f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
                    )
                    return Action.SELL
            else:
                if trailing_stop_triggered:
                    logger.info(f"⏭️ Trailing Stop disabled but condition met")

            # ✅ Dead Cross 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Dead Cross 조건 및 활성화 상태 로그 추가
            logger.info(
                f"🔍 DEBUG [DEAD_CROSS_CHECK] "
                f"enable_dead_cross={self.enable_dead_cross}, "
                f"dead_cross={dead_cross}, "
                f"macd={macd:.6f}, "
                f"signal={signal:.6f}"
            )

            if self.enable_dead_cross:
                if dead_cross:
                    logger.info(
                        f"🔻 MACD Dead Cross | macd={macd:.6f} signal={signal:.6f}"
                    )
                    return Action.SELL
            else:
                if dead_cross:
                    logger.info(f"⏭️ Dead Cross disabled | macd={macd:.6f} signal={signal:.6f}")

        return Action.HOLD


class IncrementalEMAStrategy:
    """
    증분 기반 EMA 전략
    - Fast EMA / Slow EMA 크로스 기반
    """

    def __init__(
        self,
        user_id: str,
        ticker: str,
        take_profit: float = 0.03,
        stop_loss: float = 0.01,
        min_holding_period: int = 0,
        trailing_stop_pct: Optional[float] = None,
        use_base_ema: bool = True,  # 기준선 사용 여부
        buy_conditions: Optional[Dict[str, bool]] = None,  # ✅ 조건 파일 설정 (BUY)
        sell_conditions: Optional[Dict[str, bool]] = None,  # ✅ 조건 파일 설정 (SELL)
    ):
        """
        Args:
            user_id: 사용자 ID
            ticker: 거래 티커 (예: KRW-SUI)
            take_profit: 익절 비율
            stop_loss: 손절 비율
            min_holding_period: 최소 보유 기간
            trailing_stop_pct: Trailing Stop 비율
            use_base_ema: 기준선(base_ema) 사용 여부
            buy_conditions: 매수 조건 ON/OFF 설정 (buy_sell_conditions.json의 buy 섹션)
            sell_conditions: 매도 조건 ON/OFF 설정 (buy_sell_conditions.json의 sell 섹션)
        """
        self.user_id = user_id
        self.ticker = ticker
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.min_holding_period = min_holding_period
        self.trailing_stop_pct = trailing_stop_pct
        self.use_base_ema = use_base_ema

        # ✅ BUY 조건 파일 설정 (기본값: 모두 True)
        self.buy_conditions = buy_conditions or {}
        self.enable_ema_gc = self.buy_conditions.get("ema_gc", True)
        self.enable_above_base_ema = self.buy_conditions.get("above_base_ema", True)
        self.enable_bullish_candle = self.buy_conditions.get("bullish_candle", True)

        logger.info(
            f"[EMA Strategy] Buy conditions: "
            f"ema_gc={self.enable_ema_gc}, "
            f"above_base_ema={self.enable_above_base_ema}, "
            f"bullish_candle={self.enable_bullish_candle}"
        )

        # ✅ SELL 조건 파일 설정 (기본값: 모두 True)
        self.sell_conditions = sell_conditions or {}
        self.enable_stop_loss = self.sell_conditions.get("stop_loss", True)
        self.enable_take_profit = self.sell_conditions.get("take_profit", True)
        self.enable_trailing_stop = self.sell_conditions.get("trailing_stop", True)
        self.enable_dead_cross = self.sell_conditions.get("ema_dc", True)  # EMA는 "ema_dc" 키 사용

        logger.info(
            f"[EMA Strategy] Sell conditions: "
            f"stop_loss={self.enable_stop_loss}, "
            f"take_profit={self.enable_take_profit}, "
            f"trailing_stop={self.enable_trailing_stop}, "
            f"ema_dc={self.enable_dead_cross}"
        )

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
            # ✅ EMA Golden Cross 체크 (조건 파일에서 ON일 때만)
            if self.enable_ema_gc:
                if not ema_golden_cross:
                    logger.info(f"⏭️ EMA Golden Cross not detected")
                    return Action.HOLD
            else:
                logger.info(f"⏭️ EMA Golden Cross disabled")

            # ✅ Above Base EMA 체크 (조건 파일에서 ON일 때만)
            if self.enable_above_base_ema:
                if ema_base is not None and bar.close <= ema_base:
                    logger.info(
                        f"⏭️ Not above base EMA | close={bar.close:.2f} base={ema_base:.2f}"
                    )
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Above Base EMA disabled")

            # ✅ Bullish Candle 체크 (조건 파일에서 ON일 때만)
            if self.enable_bullish_candle:
                if bar.close <= bar.open:
                    logger.info(
                        f"⏭️ Not bullish candle | close={bar.close:.2f} open={bar.open:.2f}"
                    )
                    return Action.HOLD
            else:
                logger.info(f"⏭️ Bullish Candle disabled")

            # 모든 조건 통과 시 매수
            logger.info(
                f"🔔 EMA Buy Signal | fast={ema_fast:.2f} slow={ema_slow:.2f}"
            )
            return Action.BUY

        # ========================================
        # SELL 조건
        # ========================================
        else:
            current_price = bar.close

            # 🔍 TRACE: SELL 블록 진입 확인
            logger.info(f"🔥 [SELL_BLOCK_ENTRY] EMA Strategy sell evaluation started | bar_idx={current_bar_idx}")

            # 최소 보유 기간 체크
            bars_held = position.get_bars_held(current_bar_idx)

            # ✅ bars_held 음수 보정: 봇 재시작으로 인한 entry_bar 불일치 해결
            if bars_held <= 0:
                from services.db import estimate_bars_held_from_audit
                bars_held_from_audit = estimate_bars_held_from_audit(self.user_id, self.ticker)
                logger.warning(
                    f"⚠️ [EMA] bars_held={bars_held} (음수/0) 감지 → DB 감사로그 기준으로 보정: {bars_held_from_audit}"
                )
                bars_held = bars_held_from_audit

            logger.info(
                f"🔍 [MIN_HOLDING_CHECK] bars_held={bars_held}, min_required={self.min_holding_period}, "
                f"will_skip={bars_held < self.min_holding_period}"
            )
            if bars_held < self.min_holding_period:
                logger.info(
                    f"⏳ Min holding period not met | held={bars_held} required={self.min_holding_period} → SKIP"
                )
                return Action.HOLD

            # Highest Price 갱신
            position.update_highest_price(current_price)

            # ✅ Stop Loss 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Stop Loss 조건 및 활성화 상태 로그 추가
            pnl_pct = position.get_pnl_pct(current_price)
            stop_loss_triggered = pnl_pct is not None and pnl_pct <= -self.stop_loss

            logger.info(
                f"🔍 DEBUG [STOP_LOSS_CHECK] "
                f"enable_stop_loss={self.enable_stop_loss}, "
                f"stop_loss_triggered={stop_loss_triggered}, "
                f"pnl_pct={pnl_pct:.2%} if pnl_pct else 'None', "
                f"threshold=-{self.stop_loss:.2%}, "
                f"current_price={current_price}"
            )

            if self.enable_stop_loss:
                if stop_loss_triggered:
                    logger.info(
                        f"🛡️ Stop Loss triggered | pnl={pnl_pct:.2%} sl={self.stop_loss:.2%}"
                    )
                    return Action.SELL
            else:
                if stop_loss_triggered:
                    logger.info(f"⏭️ Stop Loss disabled but condition met | pnl={pnl_pct:.2%}")

            # ✅ Take Profit 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Take Profit 조건 및 활성화 상태 로그 추가
            take_profit_triggered = pnl_pct is not None and pnl_pct >= self.take_profit

            logger.info(
                f"🔍 DEBUG [TAKE_PROFIT_CHECK] "
                f"enable_take_profit={self.enable_take_profit}, "
                f"take_profit_triggered={take_profit_triggered}, "
                f"pnl_pct={pnl_pct:.2%} if pnl_pct else 'None', "
                f"threshold={self.take_profit:.2%}, "
                f"current_price={current_price}"
            )

            if self.enable_take_profit:
                if take_profit_triggered:
                    logger.info(
                        f"🎯 Take Profit triggered | pnl={pnl_pct:.2%} tp={self.take_profit:.2%}"
                    )
                    return Action.SELL
            else:
                if take_profit_triggered:
                    logger.info(f"⏭️ Take Profit disabled but condition met | pnl={pnl_pct:.2%}")

            # ✅ Trailing Stop 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Trailing Stop 조건 및 활성화 상태 로그 추가
            highest_price = position.highest_price
            trailing_stop_triggered = False
            if self.trailing_stop_pct is not None:
                trailing_stop_triggered = position.arm_trailing_stop(self.trailing_stop_pct, current_price)

            logger.info(
                f"🔍 DEBUG [TRAILING_STOP_CHECK] "
                f"enable_trailing_stop={self.enable_trailing_stop}, "
                f"trailing_stop_triggered={trailing_stop_triggered}, "
                f"trailing_stop_pct={self.trailing_stop_pct:.2%} if self.trailing_stop_pct else 'None', "
                f"highest_price={highest_price}, "
                f"current_price={current_price}"
            )

            if self.enable_trailing_stop:
                if trailing_stop_triggered:
                    logger.info(
                        f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
                    )
                    return Action.SELL
            else:
                if trailing_stop_triggered:
                    logger.info(f"⏭️ Trailing Stop disabled but condition met")

            # ✅ EMA Dead Cross 체크 (조건 파일에서 ON일 때만)
            # 🔍 DEBUG: Dead Cross 조건 및 활성화 상태 로그 추가
            logger.info(
                f"🔍 DEBUG [DEAD_CROSS_CHECK] "
                f"enable_dead_cross={self.enable_dead_cross}, "
                f"ema_dead_cross={ema_dead_cross}, "
                f"prev_fast={prev_ema_fast}, prev_slow={prev_ema_slow}, "
                f"curr_fast={ema_fast:.2f}, curr_slow={ema_slow:.2f}"
            )

            if self.enable_dead_cross:
                if ema_dead_cross:
                    logger.info(
                        f"🔻 EMA Dead Cross | fast={ema_fast:.2f} slow={ema_slow:.2f}"
                    )
                    return Action.SELL
            else:
                if ema_dead_cross:
                    logger.info(f"⏭️ EMA Dead Cross disabled | fast={ema_fast:.2f} slow={ema_slow:.2f}")

        return Action.HOLD
