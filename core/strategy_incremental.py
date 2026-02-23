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

# ✅ 필터 시스템 import
from core.filters import BuyFilterManager, SellFilterManager
from core.filters.buy_filters import SlowEmaSurgeFilter
from core.filters.sell_filters import (
    StopLossFilter,
    TakeProfitFilter,
    TrailingStopFilter,
    DeadCrossFilter,
    StalePositionFilter
)

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

        # ✅ 마지막 BUY/SELL reason 추적용
        self.last_buy_reason: Optional[str] = None
        self.last_sell_reason: Optional[str] = None

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
            # ✅ 활성화된 조건들을 조합하여 reason 생성
            active_conditions = []
            if self.enable_golden_cross:
                active_conditions.append("golden_cross")
            if self.enable_macd_positive:
                active_conditions.append("macd_positive")
            if self.enable_signal_positive:
                active_conditions.append("signal_positive")
            if self.enable_bullish_candle:
                active_conditions.append("bullish_candle")
            if self.enable_macd_trending_up:
                active_conditions.append("macd_trending_up")
            if self.enable_above_ma20:
                active_conditions.append("above_ma20")
            if self.enable_above_ma60:
                active_conditions.append("above_ma60")

            self.last_buy_reason = "+".join(active_conditions).upper() if active_conditions else "GOLDEN_CROSS"
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
                    self.last_sell_reason = "stop_loss".upper()  # ✅ 조건 키를 대문자로
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
                    self.last_sell_reason = "take_profit".upper()  # ✅ 조건 키를 대문자로
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

            ts_pct_str = f"{self.trailing_stop_pct:.2%}" if self.trailing_stop_pct is not None else "None"
            logger.info(
                f"🔍 DEBUG [TRAILING_STOP_CHECK] "
                f"enable_trailing_stop={self.enable_trailing_stop}, "
                f"trailing_stop_triggered={trailing_stop_triggered}, "
                f"trailing_stop_pct={ts_pct_str}, "
                f"highest_price={highest_price}, "
                f"current_price={current_price}"
            )

            if self.enable_trailing_stop:
                if trailing_stop_triggered:
                    logger.info(
                        f"📉 Trailing Stop triggered | ts={self.trailing_stop_pct:.2%}"
                    )
                    self.last_sell_reason = "trailing_stop".upper()  # ✅ 조건 키를 대문자로
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
                    self.last_sell_reason = "dead_cross".upper()  # ✅ 조건 키를 대문자로
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
        base_ema_gap_enabled: bool = False,  # ✅ Base EMA GAP 전략 활성화
        base_ema_gap_diff: float = -0.005,  # ✅ Base EMA GAP 임계값
        ema_surge_filter_enabled: bool = False,  # ✅ 급등 필터 활성화
        ema_surge_threshold_pct: float = 0.01,   # ✅ 급등 임계값 (1%)
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
            base_ema_gap_diff: Base EMA GAP 임계값 (예: -0.005 = -0.5%)
            ema_surge_filter_enabled: Slow EMA 급등 필터 활성화
            ema_surge_threshold_pct: 급등 임계값 (예: 0.01 = 1%, Slow EMA 대비 1% 이상 상승 시 매수 금지)
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
        self.enable_base_ema_gap = base_ema_gap_enabled  # ✅ params에서 직접 받음
        self.base_ema_gap_diff = base_ema_gap_diff

        # ✅ BUY 조건 파일 설정 (기본값: 모두 True)
        self.buy_conditions = buy_conditions or {}
        self.enable_ema_gc = self.buy_conditions.get("ema_gc", True)
        self.enable_above_base_ema = self.buy_conditions.get("above_base_ema", True)
        self.enable_bullish_candle = self.buy_conditions.get("bullish_candle", True)

        # ✅ Surge Filter: buy_conditions 우선, 없으면 params fallback
        if "surge_filter_enabled" in self.buy_conditions:
            self.ema_surge_filter_enabled = self.buy_conditions.get("surge_filter_enabled", False)
            self.ema_surge_threshold_pct = self.buy_conditions.get("surge_threshold_pct", 0.01)
            logger.info(f"[EMA Strategy] Surge Filter from buy_sell_conditions.json")
        else:
            self.ema_surge_filter_enabled = ema_surge_filter_enabled
            self.ema_surge_threshold_pct = ema_surge_threshold_pct
            logger.info(f"[EMA Strategy] Surge Filter from params.json (backward compatibility)")

        logger.info(
            f"[EMA Strategy] Buy conditions: "
            f"ema_gc={self.enable_ema_gc}, "
            f"above_base_ema={self.enable_above_base_ema}, "
            f"bullish_candle={self.enable_bullish_candle}, "
            f"base_ema_gap={self.enable_base_ema_gap} (threshold={base_ema_gap_diff:.2%})"
        )

        logger.info(
            f"[EMA Strategy] Surge Filter: "
            f"enabled={self.ema_surge_filter_enabled}, "
            f"threshold={self.ema_surge_threshold_pct:.2%} (Slow EMA 대비)"
        )

        # ✅ SELL 조건 파일 설정 (기본값: 모두 True)
        self.sell_conditions = sell_conditions or {}
        self.enable_stop_loss = self.sell_conditions.get("stop_loss", True)
        self.enable_take_profit = self.sell_conditions.get("take_profit", True)
        self.enable_trailing_stop = self.sell_conditions.get("trailing_stop", True)
        self.enable_dead_cross = self.sell_conditions.get("ema_dc", True)  # EMA는 "ema_dc" 키 사용

        # ✅ Stale Position Check 설정
        self.enable_stale_position = self.sell_conditions.get("stale_position_check", False)
        self.stale_hours = self.sell_conditions.get("stale_hours", 1.0)
        self.stale_threshold_pct = self.sell_conditions.get("stale_threshold_pct", 0.01)

        logger.info(
            f"[EMA Strategy] Sell conditions: "
            f"stop_loss={self.enable_stop_loss}, "
            f"take_profit={self.enable_take_profit}, "
            f"trailing_stop={self.enable_trailing_stop}, "
            f"ema_dc={self.enable_dead_cross}, "
            f"stale_position={self.enable_stale_position} "
            f"(hours={self.stale_hours}h, threshold={self.stale_threshold_pct:.2%})"
        )

        # ✅ 마지막 BUY/SELL reason 추적용
        self.last_buy_reason: Optional[str] = None
        self.last_sell_reason: Optional[str] = None

        # ✅ Base EMA GAP 전략 상세 정보 (감사로그용)
        self.gap_details: Optional[Dict[str, Any]] = None

        # ✅ interval_min 저장 (live_loop에서 전달)
        self.interval_min: int = 1  # 기본값

        # ✅ 필터 시스템 초기화
        self.buy_filter_manager = BuyFilterManager()
        self.sell_filter_manager = SellFilterManager()
        self._register_buy_filters()
        self._register_sell_filters()

    def _register_buy_filters(self):
        """매수 필터 등록"""
        # Slow EMA 급등 차단 필터
        surge_filter = SlowEmaSurgeFilter(threshold_pct=self.ema_surge_threshold_pct)
        surge_filter.set_enabled(self.ema_surge_filter_enabled)
        self.buy_filter_manager.register(surge_filter)

    def _register_sell_filters(self):
        """매도 필터 등록 (카테고리 순서대로 실행됨)"""
        # 핵심 전략 필터 (CORE_STRATEGY)
        stop_loss_filter = StopLossFilter(stop_loss_pct=self.stop_loss)
        stop_loss_filter.set_enabled(self.enable_stop_loss)
        self.sell_filter_manager.register(stop_loss_filter)

        take_profit_filter = TakeProfitFilter(take_profit_pct=self.take_profit)
        take_profit_filter.set_enabled(self.enable_take_profit)
        self.sell_filter_manager.register(take_profit_filter)

        trailing_stop_filter = TrailingStopFilter(trailing_stop_pct=self.trailing_stop_pct)
        trailing_stop_filter.set_enabled(self.enable_trailing_stop)
        self.sell_filter_manager.register(trailing_stop_filter)

        dead_cross_filter = DeadCrossFilter()
        dead_cross_filter.set_enabled(self.enable_dead_cross)
        self.sell_filter_manager.register(dead_cross_filter)

        # 보조 필터 (SELL_AUXILIARY)
        stale_position_filter = StalePositionFilter(
            stale_hours=self.stale_hours,
            stale_threshold_pct=self.stale_threshold_pct
        )
        stale_position_filter.set_enabled(self.enable_stale_position)
        self.sell_filter_manager.register(stale_position_filter)

    def set_interval_min(self, interval_min: int):
        """
        봉 간격 (분 단위) 설정 - live_loop에서 호출

        Args:
            interval_min: 봉 간격 (예: 1분봉=1, 3분봉=3)
        """
        self.interval_min = interval_min
        logger.info(f"[EMA Strategy] Interval set to {interval_min} minutes")

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
            # ✅ 매수 필터 체크 (Surge Filter 등)
            # ⚠️ 중요: Base EMA GAP 전략은 급락 매수 전략이므로 필터 미적용
            if not self.enable_base_ema_gap:
                filter_result = self.buy_filter_manager.evaluate_all(
                    bar=bar,
                    ema_slow=ema_slow
                )
                if filter_result is not None and filter_result.should_block:
                    # 필터가 매수 차단
                    return Action.HOLD

            # ✅ Base EMA GAP 조건이 활성화되면 다른 조건 무시하고 GAP만 체크
            if self.enable_base_ema_gap:
                if ema_base is None or ema_base <= 0:
                    logger.info(f"⏭️ Base EMA not available")
                    self.gap_details = None
                    return Action.HOLD

                # GAP 계산
                gap_pct = (bar.close - ema_base) / ema_base
                gap_to_target = gap_pct - self.base_ema_gap_diff  # 음수면 부족, 양수면 충족
                price_needed = ema_base * (1 + self.base_ema_gap_diff)  # 매수 조건 달성 가격

                # 조건 충족 여부
                condition_met = gap_pct <= self.base_ema_gap_diff

                # ✅ 상세 정보 저장 (감사로그용)
                self.gap_details = {
                    "strategy_mode": "BASE_EMA_GAP",
                    "base_ema_gap_enabled": True,
                    "price": float(bar.close),
                    "base_ema": float(ema_base),
                    "gap_pct": float(gap_pct),
                    "gap_threshold": float(self.base_ema_gap_diff),
                    "gap_to_target": float(gap_to_target),
                    "price_needed": float(price_needed),
                    "condition_met": bool(condition_met),  # 🔧 numpy.bool_ → Python bool 변환
                    "ema_fast": float(ema_fast) if ema_fast else None,
                    "ema_slow": float(ema_slow) if ema_slow else None,
                }

                if condition_met:
                    # GAP 초과 여부 판단
                    gap_exceeded = gap_pct < (self.base_ema_gap_diff * 2)  # 목표의 2배 이상 하락

                    if gap_exceeded:
                        # 급락 감지
                        logger.info(
                            f"🔥 Base EMA GAP 급락 감지! | "
                            f"gap={gap_pct:.2%} (목표: {self.base_ema_gap_diff:.2%}, 초과: {abs(gap_to_target):.2%}p) | "
                            f"close={bar.close:.2f} base_ema={ema_base:.2f}"
                        )
                        self.gap_details["reason"] = "GAP_EXCEEDED"
                    else:
                        # 일반 매수 조건 충족
                        logger.info(
                            f"✅ Base EMA GAP 매수 조건 충족 | "
                            f"gap={gap_pct:.2%} (목표: {self.base_ema_gap_diff:.2%}, 초과: {abs(gap_to_target):.2%}p) | "
                            f"close={bar.close:.2f} base_ema={ema_base:.2f}"
                        )
                        self.gap_details["reason"] = "GAP_MET"

                    self.last_buy_reason = "BASE_EMA_GAP"
                    return Action.BUY
                else:
                    # 조건 미충족
                    logger.info(
                        f"📉 Base EMA GAP 대기 중 | "
                        f"gap={gap_pct:.2%} (목표: {self.base_ema_gap_diff:.2%}, 부족: {abs(gap_to_target):.2%}p) | "
                        f"매수가: ₩{price_needed:,.0f} | base_ema: ₩{ema_base:,.0f}"
                    )
                    self.gap_details["reason"] = "GAP_INSUFFICIENT"
                    return Action.HOLD

            # ✅ 기존 EMA 조건들 (GAP 조건이 비활성화일 때만 실행)
            # Base EMA GAP이 아닌 경우 gap_details 초기화
            self.gap_details = None

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
            # ✅ 활성화된 조건들을 조합하여 reason 생성
            active_conditions = []
            if self.enable_ema_gc:
                active_conditions.append("ema_gc")
            if self.enable_above_base_ema:
                active_conditions.append("above_base_ema")
            if self.enable_bullish_candle:
                active_conditions.append("bullish_candle")

            self.last_buy_reason = "+".join(active_conditions).upper() if active_conditions else "EMA_GC"
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

            # ✅ 매도 필터 시스템 (CORE_STRATEGY → SELL_AUXILIARY 순서로 실행)
            filter_result = self.sell_filter_manager.evaluate_all(
                position=position,
                current_price=current_price,
                bars_held=bars_held,
                interval_min=self.interval_min,
                ema_dead_cross=ema_dead_cross,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                prev_ema_fast=prev_ema_fast,
                prev_ema_slow=prev_ema_slow
            )

            if filter_result is not None and filter_result.should_block:
                # 필터가 매도 신호 발생
                self.last_sell_reason = filter_result.reason
                return Action.SELL

        return Action.HOLD
