from backtesting import Strategy
import pandas as pd
from common.logger import logger
from config import MIN_FEE_RATIO


class MACDStrategy(Strategy):
    # MACD 설정
    fast_period = 12
    slow_period = 26
    signal_period = 7

    # 전략 설정
    take_profit = 0.05  # 5% 수익 목표
    stop_loss = 0.01  # 1% 손절 기준
    macd_threshold = 0.0  # MACD가 이 값 이상일 때 진입
    min_holding_period = 1  # 최소 보유 기간
    macd_exit_enabled = False  # Dead Cross 매도 허용 여부 (기본 비활성화)

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

    def next(self):
        current_bar = len(self.data) - 1
        current_price = self.data.Close[-1]
        macd_val = float(self.macd_line[-1])
        signal_val = float(self.signal_line[-1])

        # 중복 방지
        if self.last_signal_bar == current_bar:
            return

        # 교차 판별
        cross = (
            "Gold"
            if self._is_gold_cross()
            else "Dead" if self._is_dead_cross() else "Neutral"
        )
        MACDStrategy.signal_events.append(
            (current_bar, "LOG", cross, macd_val, signal_val, current_price)
        )

        # 매도 조건: TP 또는 SL 도달 시
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

            # MACD 기반 매도는 옵션에 따라 처리
            if self.macd_exit_enabled and bars_held >= self.min_holding_period:
                if self._is_dead_cross() and macd_val >= self.macd_threshold:
                    self.position.close()
                    MACDStrategy.signal_events.append(
                        (current_bar, "SELL", "MACD_EXIT", macd_val, signal_val)
                    )
                    self._reset_entry()
                    self.last_signal_bar = current_bar
                    return

        # 매수 조건: Gold Cross + MACD 기준값 이상
        else:
            if self._is_gold_cross() and macd_val >= self.macd_threshold:
                self.buy()
                MACDStrategy.signal_events.append(
                    (current_bar, "BUY", "Gold", macd_val, signal_val)
                )
                self.entry_price = current_price
                self.entry_bar = current_bar
                self.last_signal_bar = current_bar
