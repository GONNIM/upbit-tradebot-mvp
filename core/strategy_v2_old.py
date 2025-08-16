from backtesting import Strategy
import pandas as pd
import logging
from config import (
    MIN_FEE_RATIO,
    MACD_EXIT_ENABLED,
    SIGNAL_CONFIRM_ENABLED,
    TRAILING_STOP_PERCENT,
    MACD_POSITIVE_ENABLED,
    SIGNAL_POSITIVE_ENABLED,
    BULLISH_CANDLE_ENABLED,
    MACD_TRENDING_UP_ENABLED,
    ABOVE_MA_20_ENABLED,
    ABOVE_MA_60_ENABLED,
)


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
    signal_period = 9
    # 전략 설정
    take_profit = 0.03
    stop_loss = 0.01
    macd_threshold = 0.0
    min_holding_period = 5  # 🕒 최소 보유 기간
    macd_exit_enabled = MACD_EXIT_ENABLED  # Default: True
    signal_confirm_enabled = SIGNAL_CONFIRM_ENABLED  # Default: False
    volatility_window = 20

    def init(self):
        logger.info("MACDStrategy init")
        close = self.data.Close

        self.macd_line = self.I(
            self._calculate_macd, close, self.fast_period, self.slow_period
        )
        self.signal_line = self.I(
            self._calculate_signal, self.macd_line, self.signal_period
        )
        self.ma20 = self.I(lambda x: pd.Series(x).rolling(20).mean().values, close)
        self.ma60 = self.I(lambda x: pd.Series(x).rolling(60).mean().values, close)
        self.volatility = self.I(
            self._calculate_volatility, self.data.High, self.data.Low
        )

        self.entry_price = None
        self.entry_bar = None
        self.last_signal_bar = None
        self.last_cross_type = None
        self.golden_cross_pending = False

        # Trailing Stop
        self.highest_price = None
        self.trailing_stop_pct = TRAILING_STOP_PERCENT

        # MA 기울기
        self.ma20_slope = None

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

    def _calculate_macd(self, series, fast, slow):
        return (
            pd.Series(series).ewm(span=fast).mean()
            - pd.Series(series).ewm(span=slow).mean()
        ).values

    def _calculate_signal(self, macd, period):
        return pd.Series(macd).ewm(span=period).mean().values

    def _calculate_volatility(self, high, low):
        return pd.Series(high - low).rolling(self.volatility_window).mean().values

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

    def _is_bullish_candle(self):
        return self.data.Close[-1] > self.data.Open[-1]

    def _is_macd_trending_up(self):
        return self.macd_line[-3] < self.macd_line[-2] < self.macd_line[-1]

    def _is_above_ma20(self):
        return self.data.Close[-1] > self.ma20[-1]

    def _is_above_ma60(self):
        return self.data.Close[-1] > self.ma60[-1]

    def next(self):
        current_bar = len(self.data) - 1
        current_price = self.data.Close[-1]
        macd_val = float(self.macd_line[-1])
        signal_val = float(self.signal_line[-1])
        volatility = float(self.volatility[-1])
        timestamp = self.data.index[-1]

        # 골든/데드 크로스 탐지
        if self._is_golden_cross():
            self.golden_cross_pending = True
            self.last_cross_type = "Golden"
            position_color = "🟢"
        elif self._is_dead_cross():
            self.golden_cross_pending = False
            self.last_cross_type = "Dead"
            position_color = "🛑"
        elif self.golden_cross_pending:
            self.last_cross_type = "Pending"
            position_color = "🔵"
        else:
            self.last_cross_type = "Neutral"
            position_color = "⚪"

        # 로그 기록
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

        logger.info(
            f"{position_color}[{timestamp}] 🧾 bar={current_bar} price={current_price} macd={macd_val:.5f} "
            f"signal={signal_val:.5f} vol={volatility:.4f} cross={self.last_cross_type}"
        )

        # 매도 조건
        if self.position:
            bars_held = current_bar - self.entry_bar

            # entry_price가 None이 아니어야 TP와 SL 계산 가능
            if self.entry_price is None:
                logger.warning(f"진입가가 None입니다. TP 및 SL 계산을 건너뜁니다.")
                return  # entry_price가 None인 경우 매도 조건을 건너뛰고 바로 리턴

            # Take Profit (TP) 및 Stop Loss (SL) 조건
            tp_price = self.entry_price * (
                1 + self.take_profit
            )  # take_profit 상승 시 매도
            sl_price = self.entry_price * (1 - self.stop_loss)  # stop_loss 하락 시 매도

            logger.info(
                f"[{timestamp}] 📈 현재 보유중 | 진입가={self.entry_price:.2f} | 현재가={current_price:.2f} | TP={tp_price:.2f} | SL={sl_price:.2f}"
            )

            # 1. Trailing Stop 우선 적용
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price  # 가격 상승 시 최고 가격 갱신

            trailing_stop_price = self.highest_price * (1 - self.trailing_stop_pct)

            if current_price <= trailing_stop_price:
                self.position.close()
                self._reset_entry()
                self.last_signal_bar = current_bar
                MACDStrategy.trade_events.append(
                    (
                        current_bar,
                        "SELL",
                        "Trailing Stop",
                        macd_val,
                        signal_val,
                        current_price,
                    )
                )
                logger.info(
                    f"[{timestamp}] ✅ 매도 실행 (Trailing Stop): bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )
                return

            # 2. Take Profit (TP) 매도
            if current_price >= tp_price:
                self.position.close()
                self._reset_entry()
                self.last_signal_bar = current_bar
                MACDStrategy.trade_events.append(
                    (
                        current_bar,
                        "SELL",
                        "TP",
                        macd_val,
                        signal_val,
                        current_price,
                    )
                )
                logger.info(
                    f"[{timestamp}] ✅ 매도 실행 (Take Profit): bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )
                return

            # 3. Stop Loss (SL) 매도
            elif current_price <= sl_price:
                self.position.close()
                self._reset_entry()
                self.last_signal_bar = current_bar
                MACDStrategy.trade_events.append(
                    (
                        current_bar,
                        "SELL",
                        "SL",
                        macd_val,
                        signal_val,
                        current_price,
                    )
                )
                logger.info(
                    f"[{timestamp}] ✅ 매도 실행 (Stop Loss): bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )
                return

            # 4. MACD Exit 조건 (상승 추세 반전 후 매도)
            if self.macd_exit_enabled and bars_held >= self.min_holding_period:
                if (
                    self._is_dead_cross() or macd_val <= self.macd_threshold
                ):  # OR 조건 중요
                    self.position.close()
                    self._reset_entry()
                    self.last_signal_bar = current_bar
                    MACDStrategy.trade_events.append(
                        (
                            current_bar,
                            "SELL",
                            "MACD EXIT",
                            macd_val,
                            signal_val,
                            current_price,
                        )
                    )
                    logger.info(
                        f"[{timestamp}] ✅ 매도 실행 (MACD EXIT): bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                    )
                    return

            # 5. 이동 평균선(MA20) 기울기 꺾임 (기울기 변화 속도 체크)
            ma20_current = self.ma20[-1]
            ma20_previous = self.ma20[-2]
            ma20_slope = ma20_current - ma20_previous

            if ma20_slope <= 0:
                self.position.close()
                self._reset_entry()
                self.last_signal_bar = current_bar
                MACDStrategy.trade_events.append(
                    (
                        current_bar,
                        "SELL",
                        "MA Slope Exit",
                        macd_val,
                        signal_val,
                        current_price,
                    )
                )
                logger.info(
                    f"[{timestamp}] ✅ 매도 실행 (MA Slope Exit): bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )

        # 매수 조건
        if not self.position and self.golden_cross_pending:
            buy_conditions = []

            if (
                macd_val > 0
                and signal_val > 0
                and self._is_bullish_candle()
                and self._is_macd_trending_up()
                and self._is_above_ma20()
                and self._is_above_ma60()
                and macd_val > self.macd_line[-2]
            ):
                if self.signal_confirm_enabled and signal_val < self.macd_threshold:
                    logger.info(
                        f"🟡 매수 보류 | signal({signal_val:.5f}) < macd_threshold({self.macd_threshold:.5f})"
                    )
                    return

                self.buy()
                self.entry_price = current_price
                self.entry_bar = current_bar
                self.last_signal_bar = current_bar
                self.golden_cross_pending = False
                MACDStrategy.trade_events.append(
                    (
                        current_bar,
                        "BUY",
                        "Golden",
                        macd_val,
                        signal_val,
                        current_price,
                    )
                )
                logger.info(
                    f"[{timestamp}] ✅ 매수 실행: bar={current_bar} | price={current_price} | macd={macd_val} | signal={signal_val}"
                )
