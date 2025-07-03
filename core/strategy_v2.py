from backtesting import Strategy
import pandas as pd
import logging
from config import MIN_FEE_RATIO, MACD_EXIT_ENABLED, SIGNAL_CROSS_ENTRY_ENABLED


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
    take_profit = 0.05  # 5% 익절
    stop_loss = 0.01  # 1% 손절
    macd_threshold = 0.0  # MACD 진입 기준
    min_holding_period = 1  # 최소 보유 기간
    macd_exit_enabled = MACD_EXIT_ENABLED  # Dead Cross 매도 허용 여부
    signal_cross_entry_enabled = (
        SIGNAL_CROSS_ENTRY_ENABLED  # Signal 통과 시 매수 진입 허용 여부
    )

    def init(self):
        logger.info("전략 초기화")
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

    def _is_gold_cross(self):
        return (
            self.macd_line[-2] <= self.signal_line[-2]
            and self.macd_line[-1] > self.signal_line[-1]
        )

    def _is_dead_cross(self):
        return (
            self.macd_line[-2] >= self.signal_line[-2]
            and self.macd_line[-1] < self.signal_line[-1]
        )

    def _is_signal_cross_up(self):
        return (
            self.macd_line[-2] < self.signal_line[-2]
            and self.macd_line[-1] >= self.signal_line[-1]
        )

    def next(self):
        current_bar = len(self.data) - 1
        current_price = self.data.Close[-1]
        macd_val = float(self.macd_line[-1])
        signal_val = float(self.signal_line[-1])

        # 중복 시그널 방지
        if self.last_signal_bar == current_bar:
            return

        # 교차 판단
        cross = (
            "Gold"
            if self._is_gold_cross()
            else "Dead" if self._is_dead_cross() else "Neutral"
        )
        MACDStrategy.signal_events.append(
            (current_bar, "LOG", cross, macd_val, signal_val, current_price)
        )

        # 매도 조건: TP / SL
        if self.position:
            bars_held = current_bar - self.entry_bar
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

            # 옵션: MACD Dead Cross 시 매도
            if self.macd_exit_enabled and bars_held >= self.min_holding_period:
                if self._is_dead_cross() and macd_val >= self.macd_threshold:
                    self.position.close()
                    MACDStrategy.signal_events.append(
                        (current_bar, "SELL", "MACD_EXIT", macd_val, signal_val)
                    )
                    self._reset_entry()
                    self.last_signal_bar = current_bar
                    return

        # 매수 조건: Gold Cross or Signal 통과, + MACD 기준 만족
        else:
            gold_cross_cond = self._is_gold_cross() and macd_val >= self.macd_threshold
            signal_cross_cond = (
                self.signal_cross_entry_enabled
                and self._is_signal_cross_up()
                and macd_val >= self.macd_threshold
            )

            if gold_cross_cond or signal_cross_cond:
                self.buy()
                MACDStrategy.signal_events.append(
                    (current_bar, "BUY", "Gold", macd_val, signal_val)
                )
                self.entry_price = current_price
                self.entry_bar = current_bar
                self.last_signal_bar = current_bar
