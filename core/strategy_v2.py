from backtesting import Strategy
import pandas as pd
import logging
from config import MIN_FEE_RATIO


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MACDStrategy(Strategy):
    fast_period = 12
    slow_period = 26
    signal_period = 7
    take_profit = 0.05  # 5%
    stop_loss = 0.01  # 1%
    macd_threshold = 0.0
    min_holding_period = 1
    macd_crossover_threshold = 0.0

    def init(self):
        logger.info("전략 초기화 시작")
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

        MACDStrategy.signal_events = []
        logger.info(
            f"init: MACDStrategy.signal_events id={id(MACDStrategy.signal_events)}"
        )

    def _calculate_macd(self, series, fast, slow):
        series = pd.Series(series)
        return (series.ewm(span=fast).mean() - series.ewm(span=slow).mean()).values

    def _calculate_signal(self, macd, period):
        return pd.Series(macd).ewm(span=period).mean().values

    def _reset_entry(self):
        self.entry_price = None
        self.entry_bar = None

    def next(self):
        current_bar = len(self.data) - 1
        current_price = self.data.Close[-1]
        macd_val = float(self.macd_line[-1])
        signal_val = float(self.signal_line[-1])

        if self.last_signal_bar == current_bar:
            return

        cross = (
            "Gold"
            if self.macd_line[-2] <= self.signal_line[-2]
            and self.macd_line[-1] > self.signal_line[-1]
            else (
                "Dead"
                if self.macd_line[-2] >= self.signal_line[-2]
                and self.macd_line[-1] < self.signal_line[-1]
                else "Neutral"
            )
        )

        # 로그 기록
        MACDStrategy.signal_events.append(
            (current_bar, "LOG", cross, macd_val, signal_val, current_price)
        )

        if self.position:
            bars_since_entry = current_bar - self.entry_bar
            tp_price = self.entry_price * (1 + self.take_profit + 2 * MIN_FEE_RATIO)
            sl_price = self.entry_price * (1 - self.stop_loss - 2 * MIN_FEE_RATIO)

            if current_price >= tp_price:
                self.position.close()
                MACDStrategy.signal_events.append(
                    (current_bar, "SELL", "TP", macd_val, signal_val)
                )
                self._reset_entry()
                self.last_signal_bar = current_bar
                return

            if current_price <= sl_price:
                self.position.close()
                MACDStrategy.signal_events.append(
                    (current_bar, "SELL", "SL", macd_val, signal_val)
                )
                self._reset_entry()
                self.last_signal_bar = current_bar
                return

            if bars_since_entry < self.min_holding_period:
                return

            if (
                macd_val - signal_val < -self.macd_crossover_threshold
                and self.macd_line[-2] >= self.signal_line[-2]
                and macd_val >= self.macd_threshold
            ):
                self.position.close()
                MACDStrategy.signal_events.append(
                    (current_bar, "SELL", cross, macd_val, signal_val)
                )
                self._reset_entry()
                self.last_signal_bar = current_bar

        else:
            if (
                macd_val - signal_val > self.macd_crossover_threshold
                and self.macd_line[-2] <= self.signal_line[-2]
                and macd_val >= self.macd_threshold
            ):
                self.buy()
                MACDStrategy.signal_events.append(
                    (current_bar, "BUY", cross, macd_val, signal_val)
                )
                self.entry_price = current_price
                self.entry_bar = current_bar
                self.last_signal_bar = current_bar
