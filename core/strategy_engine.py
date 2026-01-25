"""
전략 엔진 - Backtest 없이 증분 처리 기반
핵심: 새 봉 1개씩 처리하며 전략 평가 → 주문 실행
"""
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_action import Action
from core.trader import UpbitTrader
from services.db import insert_buy_eval, insert_sell_eval, estimate_entry_bar_from_audit
from typing import Optional, Dict, Any
import logging
import queue

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    증분 기반 전략 엔진 (Backtest 없음)

    동작 흐름:
    1. 새 봉 확정 시 on_new_bar() 호출
    2. 버퍼에 추가
    3. 지표 증분 갱신
    4. 전략 평가
    5. 주문 실행 (중복 방지)
    """

    def __init__(
        self,
        buffer: CandleBuffer,
        indicators: IndicatorState,
        position: PositionState,
        strategy,  # IncrementalMACDStrategy 또는 IncrementalEMAStrategy
        trader: UpbitTrader,
        user_id: str,
        ticker: str,
        strategy_type: str = "MACD",
        q: Optional[queue.Queue] = None,  # 이벤트 큐 (Streamlit용)
        interval_sec: int = 60,  # 봉 간격 (초)
        take_profit: float = 0.03,  # 익절 비율
        stop_loss: float = 0.01,  # 손절 비율
        trailing_stop_pct: Optional[float] = None,  # Trailing Stop 비율
    ):
        """
        Args:
            buffer: CandleBuffer 인스턴스
            indicators: IndicatorState 인스턴스
            position: PositionState 인스턴스
            strategy: 증분 전략 객체
            trader: UpbitTrader 인스턴스
            user_id: 사용자 ID
            ticker: 티커 (예: KRW-PEPE)
            strategy_type: 전략 타입 (MACD/EMA)
            q: 이벤트 큐 (선택)
            interval_sec: 봉 간격 (초)
            take_profit: 익절 비율
            stop_loss: 손절 비율
            trailing_stop_pct: Trailing Stop 비율
        """
        self.buffer = buffer
        self.indicators = indicators
        self.position = position
        self.strategy = strategy
        self.trader = trader
        self.user_id = user_id
        self.ticker = ticker
        self.strategy_type = strategy_type.upper()
        self.q = q
        self.interval_sec = interval_sec
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.trailing_stop_pct = trailing_stop_pct

        self.last_bar_ts = None
        self.bar_count = 0

    def is_new_bar(self, bar: Bar) -> bool:
        """
        중복 봉 방지

        Args:
            bar: 체크할 봉

        Returns:
            bool: 새 봉이면 True
        """
        return bar.ts != self.last_bar_ts

    def on_new_bar(self, bar: Bar):
        """
        새 봉 확정 시 처리 (핵심 로직)

        절대 규칙:
        1. 버퍼에 추가
        2. 지표 증분 갱신
        3. 전략 평가
        4. 주문 실행

        Args:
            bar: 확정된 봉 (is_closed=True)
        """
        # ✅ 확정 봉만 처리
        if not bar.is_closed:
            logger.warning(f"⚠️ 미확정 봉 무시: {bar.ts}")
            return

        # ✅ 중복 방지
        if not self.is_new_bar(bar):
            logger.debug(f"⏭️ 중복 봉 무시: {bar.ts}")
            return

        # 1. 버퍼 추가
        self.buffer.append(bar)
        self.last_bar_ts = bar.ts
        self.bar_count += 1

        # 2. 지표 증분 갱신 ★ 핵심: 전체 재계산 없음
        self.indicators.update_incremental(bar.close)

        # 3. 전략 평가
        ind_snapshot = self.indicators.get_snapshot()
        action = self.strategy.on_bar(bar, ind_snapshot, self.position, self.bar_count)

        # 로그 출력
        self._log_bar_evaluation(bar, ind_snapshot, action)

        # 이벤트 큐에 LOG 전송 (Streamlit용)
        if self.q is not None:
            self._send_log_event(bar, ind_snapshot)

        # ✅ 감사 로그 기록 (매 봉마다)
        self._record_audit_log(bar, ind_snapshot, action)

        # 4. 주문 실행
        self.execute(action, bar, ind_snapshot)

    def execute(self, action: Action, bar: Bar, indicators: Dict[str, Any]):
        """
        주문 실행 (중복 방지 포함)

        Args:
            action: 전략이 반환한 액션
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if action == Action.HOLD or action == Action.NOOP:
            return

        # 주문 진행 중이면 대기
        if self.position.pending_order:
            logger.warning("⏳ 주문 진행 중 → 신규 액션 대기")
            return

        if action == Action.BUY:
            self._execute_buy(bar, indicators)
        elif action == Action.SELL or action == Action.CLOSE:
            self._execute_sell(bar, indicators)

    def _execute_buy(self, bar: Bar, indicators: Dict[str, Any]):
        """
        매수 실행

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if self.position.has_position:
            logger.warning("⛔ 이미 포지션 보유 중 → BUY 무시")
            return

        # 매수 실행
        self.position.set_pending(True)

        meta = {
            "bar": self.bar_count,
            "reason": "GoldenCross" if self.strategy_type == "MACD" else "EMA_GC",
            "macd": indicators.get("macd"),
            "signal": indicators.get("signal"),
            "ema_fast": indicators.get("ema_fast"),
            "ema_slow": indicators.get("ema_slow"),
        }

        result = self.trader.buy_market(
            bar.close,
            self.ticker,
            ts=bar.ts,
            meta=meta
        )

        if result:
            self.position.open_position(
                result["qty"],
                result["price"],
                self.bar_count,
                bar.ts
            )
            logger.info(
                f"✅ BUY 체결 | qty={result['qty']:.6f} price={result['price']:.2f} "
                f"bar={self.bar_count}"
            )

            # 이벤트 큐에 BUY 전송
            if self.q is not None:
                self.q.put((
                    bar.ts,
                    "BUY",
                    result["qty"],
                    result["price"],
                    meta.get("reason", "BUY"),
                    indicators.get("macd"),
                    indicators.get("signal"),
                ))
        else:
            self.position.set_pending(False)
            logger.warning("❌ BUY 실패")

    def _execute_sell(self, bar: Bar, indicators: Dict[str, Any]):
        """
        매도 실행

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if not self.position.has_position:
            logger.warning("⛔ 포지션 없음 → SELL 무시")
            return

        # 매도 실행
        self.position.set_pending(True)

        pnl_pct = self.position.get_pnl_pct(bar.close)
        bars_held = self.position.get_bars_held(self.bar_count)

        meta = {
            "bar": self.bar_count,
            "reason": "DeadCross",
            "entry_bar": self.position.entry_bar,
            "entry_price": self.position.avg_price,
            "bars_held": bars_held,
            "pnl_pct": pnl_pct,
            "macd": indicators.get("macd"),
            "signal": indicators.get("signal"),
        }

        result = self.trader.sell_market(
            self.position.qty,
            self.ticker,
            bar.close,
            ts=bar.ts,
            meta=meta
        )

        if result:
            logger.info(
                f"✅ SELL 체결 | qty={result['qty']:.6f} price={result['price']:.2f} "
                f"pnl={pnl_pct:.2%} bars_held={bars_held}"
            )

            # 이벤트 큐에 SELL 전송
            if self.q is not None:
                self.q.put((
                    bar.ts,
                    "SELL",
                    result["qty"],
                    result["price"],
                    meta.get("reason", "SELL"),
                    indicators.get("macd"),
                    indicators.get("signal"),
                ))

            self.position.close_position(bar.ts)
        else:
            self.position.set_pending(False)
            logger.warning("❌ SELL 실패")

    def _log_bar_evaluation(self, bar: Bar, indicators: Dict[str, Any], action: Action):
        """
        봉 평가 로그 출력

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
            action: 전략 액션
        """
        if self.strategy_type == "MACD":
            logger.info(
                f"📊 Bar#{self.bar_count} | ts={bar.ts} | close={bar.close:.2f} | "
                f"macd={indicators['macd']:.5f} | signal={indicators['signal']:.5f} | "
                f"action={action.value} | pos={self.position.has_position}"
            )
        elif self.strategy_type == "EMA":
            logger.info(
                f"📊 Bar#{self.bar_count} | ts={bar.ts} | close={bar.close:.2f} | "
                f"ema_fast={indicators['ema_fast']:.2f} | ema_slow={indicators['ema_slow']:.2f} | "
                f"ema_base={indicators['ema_base']:.2f} | "
                f"action={action.value} | pos={self.position.has_position}"
            )

    def _send_log_event(self, bar: Bar, indicators: Dict[str, Any]):
        """
        LOG 이벤트 전송 (Streamlit용)

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if self.q is None:
            return

        if self.strategy_type == "MACD":
            cross_status = "Neutral"
            if indicators["macd"] > indicators["signal"]:
                cross_status = "Golden"
            elif indicators["macd"] < indicators["signal"]:
                cross_status = "Dead"

            msg = (
                f"{bar.ts} | price={bar.close:.2f} | "
                f"cross={cross_status} | macd={indicators['macd']:.5f} | signal={indicators['signal']:.5f} | "
                f"bar={self.bar_count}"
            )
        else:  # EMA
            cross_status = "Neutral"
            if indicators["ema_fast"] > indicators["ema_slow"]:
                cross_status = "Golden"
            elif indicators["ema_fast"] < indicators["ema_slow"]:
                cross_status = "Dead"

            msg = (
                f"{bar.ts} | price={bar.close:.2f} | "
                f"cross={cross_status} | ema_fast={indicators['ema_fast']:.2f} | "
                f"ema_slow={indicators['ema_slow']:.2f} | ema_base={indicators['ema_base']:.2f} | "
                f"bar={self.bar_count}"
            )

        self.q.put((bar.ts, "LOG", msg))

    def _record_audit_log(self, bar: Bar, indicators: Dict[str, Any], action: Action):
        """
        감사 로그 기록 (매 봉마다)

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
            action: 전략 액션
        """
        try:
            current_price = bar.close

            # ✅ 전략 타입에 따라 지표 값 및 checks 구성
            if self.strategy_type == "MACD":
                # MACD 전략: macd, signal 컬럼 사용
                macd = indicators.get("macd")
                signal = indicators.get("signal")

                # checks 필드도 MACD 기준 (JSON 직렬화를 위해 float 변환)
                base_checks = {
                    "reason": None,  # 나중에 설정
                    "macd": float(macd) if macd is not None else None,
                    "signal": float(signal) if signal is not None else None,
                    "price": float(current_price) if current_price is not None else None,
                }
            else:  # EMA
                # EMA 전략: macd 컬럼에 ema_fast, signal 컬럼에 ema_slow 저장
                # (audit_viewer.py에서 delta 계산 및 컬럼명 변경에 사용)
                macd = indicators.get("ema_fast")
                signal = indicators.get("ema_slow")

                # checks 필드는 EMA 지표 기준 (JSON 직렬화를 위해 float 변환)
                base_checks = {
                    "reason": None,  # 나중에 설정
                    "ema_fast": float(indicators.get("ema_fast")) if indicators.get("ema_fast") is not None else None,
                    "ema_slow": float(indicators.get("ema_slow")) if indicators.get("ema_slow") is not None else None,
                    "ema_base": float(indicators.get("ema_base")) if indicators.get("ema_base") is not None else None,
                    "price": float(current_price) if current_price is not None else None,
                }

            # 포지션 없을 때: BUY 평가 로그
            if not self.position.has_position:
                # ✅ BUY 평가 상세 정보 계산
                # Cross 상태 판단
                cross_status = "Neutral"
                if self.strategy_type == "EMA":
                    ema_fast = indicators.get("ema_fast")
                    ema_slow = indicators.get("ema_slow")
                    if ema_fast and ema_slow:
                        if ema_fast > ema_slow:
                            cross_status = "Golden"
                        elif ema_fast < ema_slow:
                            cross_status = "Dead"
                elif self.strategy_type == "MACD":
                    macd_val = indicators.get("macd")
                    signal_val = indicators.get("signal")
                    if macd_val and signal_val:
                        if macd_val > signal_val:
                            cross_status = "Golden"
                        elif macd_val < signal_val:
                            cross_status = "Dead"

                if action == Action.HOLD or action == Action.NOOP:
                    # 신호 없음
                    buy_checks = base_checks.copy()
                    buy_checks["reason"] = "NO_BUY_SIGNAL"
                    buy_checks["cross_status"] = cross_status

                    insert_buy_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        have_position=False,
                        overall_ok=False,
                        failed_keys=["NO_SIGNAL"],
                        checks=buy_checks,
                        notes=f"{cross_status} | NO_SIGNAL | bar={self.bar_count}"
                        # ✅ timestamp 제거 → 자동으로 now_kst() 사용
                    )
                elif action == Action.BUY:
                    # BUY 신호 발생
                    buy_checks = base_checks.copy()
                    buy_checks["reason"] = "BUY_SIGNAL"
                    buy_checks["cross_status"] = cross_status

                    insert_buy_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        have_position=False,
                        overall_ok=True,
                        failed_keys=[],
                        checks=buy_checks,
                        notes=f"🟢 BUY | {cross_status} | bar={self.bar_count}"
                        # ✅ timestamp 제거 → 자동으로 now_kst() 사용
                    )

            # 포지션 있을 때: SELL 평가 로그
            else:
                entry_price = self.position.avg_price
                tp_price = entry_price * (1 + self.take_profit) if entry_price else None
                sl_price = entry_price * (1 - self.stop_loss) if entry_price else None
                bars_held = self.position.get_bars_held(self.bar_count)

                # ✅ bars_held가 0 이하일 때 대안: audit_trades 기반 추정
                if bars_held <= 0:
                    estimated_entry_bar = estimate_entry_bar_from_audit(self.user_id, self.ticker)
                    if estimated_entry_bar is not None and estimated_entry_bar <= self.bar_count:
                        bars_held = self.bar_count - estimated_entry_bar
                        logger.info(f"[BARS_HELD] 추정 성공: entry_bar={estimated_entry_bar}, current_bar={self.bar_count}, bars_held={bars_held}")
                    else:
                        # 추정 불가 시 0으로 설정
                        bars_held = 0
                        if estimated_entry_bar is not None:
                            logger.warning(f"[BARS_HELD] 추정 실패: entry_bar={estimated_entry_bar} > current_bar={self.bar_count} (이전 세션 데이터) → bars_held=0")
                        else:
                            logger.warning(f"[BARS_HELD] 추정 불가: audit_trades에 데이터 없음 → bars_held=0")

                # ✅ SELL 평가 상세 정보 계산
                pnl_pct = self.position.get_pnl_pct(current_price) if entry_price else 0.0

                # Cross 상태 판단 (EMA 전략용)
                cross_status = "Neutral"
                if self.strategy_type == "EMA":
                    ema_fast = indicators.get("ema_fast")
                    ema_slow = indicators.get("ema_slow")
                    if ema_fast and ema_slow:
                        if ema_fast > ema_slow:
                            cross_status = "Golden"
                        elif ema_fast < ema_slow:
                            cross_status = "Dead"
                elif self.strategy_type == "MACD":
                    macd_val = indicators.get("macd")
                    signal_val = indicators.get("signal")
                    if macd_val and signal_val:
                        if macd_val > signal_val:
                            cross_status = "Golden"
                        elif macd_val < signal_val:
                            cross_status = "Dead"

                # 매도 조건 체크
                tp_hit = bool((tp_price is not None) and (current_price >= tp_price))
                sl_hit = bool((sl_price is not None) and (current_price <= sl_price))

                if action == Action.HOLD or action == Action.NOOP:
                    # 신호 없음
                    sell_checks = base_checks.copy()
                    sell_checks["reason"] = "NO_SELL_SIGNAL"
                    sell_checks["entry_price"] = float(entry_price) if entry_price else None
                    sell_checks["pnl_pct"] = float(pnl_pct)
                    sell_checks["cross_status"] = cross_status
                    sell_checks["tp_hit"] = tp_hit
                    sell_checks["sl_hit"] = sl_hit
                    sell_checks["bars_held"] = int(bars_held)

                    insert_sell_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        highest=self.position.highest_price,
                        ts_pct=self.trailing_stop_pct,
                        ts_armed=False,
                        bars_held=bars_held,
                        checks=sell_checks,
                        triggered=False,
                        trigger_key=None,
                        notes=f"{cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}"
                        # ✅ timestamp 제거 → 자동으로 now_kst() 사용
                    )
                elif action == Action.SELL or action == Action.CLOSE:
                    # SELL 신호 발생 - 구체적인 트리거 원인 판단
                    trigger_reason = "STRATEGY_SIGNAL"
                    if sl_hit:
                        trigger_reason = "STOP_LOSS"
                    elif tp_hit:
                        trigger_reason = "TAKE_PROFIT"
                    elif cross_status == "Dead":
                        trigger_reason = "DEAD_CROSS"

                    sell_checks = base_checks.copy()
                    sell_checks["reason"] = "SELL_SIGNAL"
                    sell_checks["entry_price"] = float(entry_price) if entry_price else None
                    sell_checks["pnl_pct"] = float(pnl_pct)
                    sell_checks["cross_status"] = cross_status
                    sell_checks["tp_hit"] = tp_hit
                    sell_checks["sl_hit"] = sl_hit
                    sell_checks["bars_held"] = int(bars_held)
                    sell_checks["trigger_reason"] = trigger_reason

                    insert_sell_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        highest=self.position.highest_price,
                        ts_pct=self.trailing_stop_pct,
                        ts_armed=False,
                        bars_held=bars_held,
                        checks=sell_checks,
                        triggered=True,
                        trigger_key=trigger_reason,
                        notes=f"🔴 SELL | {trigger_reason} | {cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}"
                        # ✅ timestamp 제거 → 자동으로 now_kst() 사용
                    )

        except Exception as e:
            logger.warning(f"[AUDIT] 감사 로그 기록 실패: {e}")
