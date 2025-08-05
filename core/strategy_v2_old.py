from backtesting import Strategy
import pandas as pd
import logging
from config import MIN_FEE_RATIO, MACD_EXIT_ENABLED, SIGNAL_CONFIRM_ENABLED


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MACDStrategy(Strategy):
    # MACD 설정
    fast_period = 12
    slow_period = 26
    signal_period = 7

    # 전략 설정
    take_profit = 0.05
    stop_loss = 0.01
    macd_threshold = 0.0
    min_holding_period = 1
    macd_exit_enabled = MACD_EXIT_ENABLED
    signal_confirm_enabled = SIGNAL_CONFIRM_ENABLED

    def init(self):
        logger.info("전략 초기화")
        logger.info(f"📌 옵션: macd_exit_enabled = {self.macd_exit_enabled}")
        logger.info(f"📌 옵션: signal_confirm_enabled = {self.signal_confirm_enabled}")
        close = self.data.Close
        self.macd_line = self.I(
            self._calculate_macd, close, self.fast_period, self.slow_period
        )
        self.signal_line = self.I(
            self._calculate_signal, self.macd_line, self.signal_period
        )

        self.entry_price = None
        self.entry_bar = None
        self.last_signal_bar = None
        self.last_cross_type = None
        self.golden_cross_pending = False

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

    def _calculate_macd(self, series, fast, slow):
        return (
            pd.Series(series).ewm(span=fast).mean()
            - pd.Series(series).ewm(span=slow).mean()
        ).values

    def _calculate_signal(self, macd, period):
        return pd.Series(macd).ewm(span=period).mean().values

    def _reset_entry(self):
        self.entry_price = None
        self.entry_bar = None

    def _is_golden_cross(self):
        return (
            self.macd_line[-2] <= self.signal_line[-2]
            and self.macd_line[-1] > self.signal_line[-1]
        )

    def _is_dead_cross(self):
        return (
            self.macd_line[-2] >= self.signal_line[-2]
            and self.macd_line[-1] < self.signal_line[-1]
        )

    def next(self):
        current_bar = len(self.data) - 1
        current_price = self.data.Close[-1]
        macd_val = float(self.macd_line[-1])
        signal_val = float(self.signal_line[-1])

        # 골든/데드 크로스 감지 및 상태 업데이트
        if self._is_golden_cross():
            self.golden_cross_pending = True
            self.last_cross_type = "Golden"

        if self._is_dead_cross():
            self.last_cross_type = "Dead"
            self.golden_cross_pending = False

        MACDStrategy.log_events.append(
            (
                current_bar,
                "LOG",
                self.last_cross_type or "Neutral",
                macd_val,
                signal_val,
                current_price,
            )
        )
        timestamp = self.data.index[-1]
        position_color = ""
        if self.last_cross_type == "Golden":
            position_color = "🟢"
        elif self.last_cross_type == "Dead":
            position_color = "🛑"
        else:
            position_color = ""
        logger.info(
            f"{position_color}[{timestamp}] bar={current_bar} macd={macd_val} signal={signal_val} price={current_price}"
        )

        if self.last_signal_bar == current_bar and not self.position:
            logger.info(f"⛔️ 중복 매수 방지: current_bar={current_bar}, 이미 시도됨")
            return

        # 매도 조건
        if self.position:
            bars_held = current_bar - self.entry_bar
            tp_price = self.entry_price * (1 + self.take_profit + 2 * MIN_FEE_RATIO)
            sl_price = self.entry_price * (1 - self.stop_loss - 2 * MIN_FEE_RATIO)

            logger.info(
                f"[{timestamp}] {self.position} current={current_price} entry={self.entry_price} tp={tp_price} sl={sl_price}"
            )

            if current_price >= tp_price:
                self.position.close()
                MACDStrategy.trade_events.append(
                    (current_bar, "SELL", "TP", macd_val, signal_val, current_price)
                )
                self._reset_entry()
                self.last_signal_bar = current_bar
                return

            if current_price <= sl_price:
                self.position.close()
                MACDStrategy.trade_events.append(
                    (current_bar, "SELL", "SL", macd_val, signal_val, current_price)
                )
                self._reset_entry()
                self.last_signal_bar = current_bar
                return

            if self.macd_exit_enabled and bars_held >= self.min_holding_period:
                if self._is_dead_cross() and macd_val >= self.macd_threshold:
                    self.position.close()
                    MACDStrategy.trade_events.append(
                        (
                            current_bar,
                            "SELL",
                            "MACD_EXIT",
                            macd_val,
                            signal_val,
                            current_price,
                        )
                    )
                    self._reset_entry()
                    self.last_signal_bar = current_bar
                    return

        # 매수 조건 (방안 2)
        if not self.position and self.golden_cross_pending:
            if macd_val >= self.macd_threshold:
                if self.signal_confirm_enabled and signal_val < self.macd_threshold:
                    logger.info(
                        f"🟡 매수 보류: signal_confirm_enabled 활성화 중, signal_val({signal_val:.5f}) < macd_threshold({self.macd_threshold:.5f})"
                    )
                    return

                self.buy()
                MACDStrategy.trade_events.append(
                    (current_bar, "BUY", "Golden", macd_val, signal_val, current_price)
                )
                logger.info(
                    f"✅ 매수 실행: bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )
                self.entry_price = current_price
                self.entry_bar = current_bar
                self.last_signal_bar = current_bar
                self.golden_cross_pending = False
