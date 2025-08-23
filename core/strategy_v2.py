from backtesting import Strategy
import pandas as pd
import logging
from config import (
    CONDITIONS_JSON_FILENAME,
    MACD_EXIT_ENABLED,
    SIGNAL_CONFIRM_ENABLED,
    TRAILING_STOP_PERCENT,
)
import json
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MACDStrategy(Strategy):
    fast_period = 12
    slow_period = 26
    signal_period = 9
    take_profit = 0.03
    stop_loss = 0.01
    macd_threshold = 0.0
    min_holding_period = 5  # 🕒 최소 보유 기간
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
        self.highest_price = None
        self.trailing_stop_pct = TRAILING_STOP_PERCENT
        self.golden_cross_pending = False
        self.last_cross_type = None

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

        self.conditions = self._load_conditions()
        self._log_conditions()

    # -------------------
    # --- Helper Methods
    # -------------------
    def _load_conditions(self):
        path = Path(f"{self.user_id}_{CONDITIONS_JSON_FILENAME}")
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                conditions = json.load(f)
                logger.info(f"📂 Condition 파일 로드 완료: {path}")
                return conditions
        else:
            logger.warning(f"⚠️ Condition 파일 없음. 기본값 사용: {path}")
            return {
                "buy": dict.fromkeys(
                    [
                        "macd_positive",
                        "signal_positive",
                        "bullish_candle",
                        "macd_trending_up",
                        "above_ma20",
                        "above_ma60",
                    ],
                    False,
                ),
                "sell": dict.fromkeys(
                    ["take_profit", "stop_loss", "macd_exit", "trailing_stop"], False
                ),
            }

    def _log_conditions(self):
        logger.info("📋 매수/매도 전략 Condition 상태:")
        for key, conds in self.conditions.items():
            for cond, value in conds.items():
                status = "✅ ON" if value else "❌ OFF"
                logger.info(f" - {key}.{cond}: {status}")

    def _calculate_macd(self, series, fast, slow):
        return (
            pd.Series(series).ewm(span=fast).mean()
            - pd.Series(series).ewm(span=slow).mean()
        ).values

    def _calculate_signal(self, macd, period):
        return pd.Series(macd).ewm(span=period).mean().values

    def _calculate_volatility(self, high, low):
        return pd.Series(high - low).rolling(self.volatility_window).mean().values

    def _current_state(self):
        idx = len(self.data) - 1
        return {
            "bar": idx,
            "price": float(self.data.Close[-1]),
            "macd": float(self.macd_line[-1]),
            "signal": float(self.signal_line[-1]),
            "volatility": float(self.volatility[-1]),
            "timestamp": self.data.index[-1],
        }

    # -------------------
    # --- Cross Detection
    # -------------------
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

    # -------------------
    # --- Candle & Trend
    # -------------------
    def _is_bullish_candle(self):
        return self.data.Close[-1] > self.data.Open[-1]

    def _is_macd_trending_up(self):
        return self.macd_line[-3] < self.macd_line[-2] < self.macd_line[-1]

    def _is_above_ma20(self):
        return self.data.Close[-1] > self.ma20[-1]

    def _is_above_ma60(self):
        return self.data.Close[-1] > self.ma60[-1]

    # -------------------
    # --- Buy/Sell Logic
    # -------------------
    def next(self):
        self._update_cross_state()
        self._evaluate_sell()
        self._evaluate_buy()

    def _update_cross_state(self):
        state = self._current_state()
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
                state["bar"],
                "LOG",
                self.last_cross_type,
                state["macd"],
                state["signal"],
                state["price"],
            )
        )
        logger.info(
            f"{position_color}[{state["timestamp"]}] 🧾 bar={state["bar"]} price={state["price"]} macd={state["macd"]:.5f} "
            f"signal={state["signal"]:.5f} vol={state["volatility"]:.5f} cross={self.last_cross_type}"
        )

    def _evaluate_buy(self):
        if self.position and not self.golden_cross_pending:
            return

        state = self._current_state()
        buy_cond = self.conditions.get("buy", {})

        checks = [
            (
                buy_cond.get("macd_positive", False),
                lambda: state["macd"] > 0,
                "macd_positive",
            ),
            (
                buy_cond.get("signal_positive", False),
                lambda: state["signal"] > 0,
                "signal_positive",
            ),
            (
                buy_cond.get("bullish_candle", False),
                self._is_bullish_candle,
                "bullish_candle",
            ),
            (
                buy_cond.get("macd_trending_up", False),
                self._is_macd_trending_up,
                "macd_trending_up",
            ),
            (buy_cond.get("above_ma20", False), self._is_above_ma20, "above_ma20"),
            (buy_cond.get("above_ma60", False), self._is_above_ma60, "above_ma60"),
        ]

        for enabled, fn, name in checks:
            if enabled and not fn():
                return

        if self.signal_confirm_enabled and state["signal"] < self.macd_threshold:
            logger.info(
                f"🟡 매수 보류 | signal({state["signal"]:.5f}) < macd_threshold({self.macd_threshold:.5f})"
            )
            return

        self.buy()
        self.entry_price = state["price"]
        self.entry_bar = state["bar"]
        self.golden_cross_pending = False
        MACDStrategy.trade_events.append(
            (
                state["bar"],
                "BUY",
                "Golden",
                state["macd"],
                state["signal"],
                state["price"],
            )
        )
        logger.info(
            f"[{state["timestamp"]}] ✅ 매수 : bar={state["bar"]} | price={state["price"]} | macd={state["macd"]} | signal={state["signal"]}"
        )

    def _evaluate_sell(self):
        if not self.position:
            return

        state = self._current_state()
        sell_cond = self.conditions.get("sell", {})

        if self.entry_price is None:
            logger.warning(f"entry_price is None. Jump TP / SL Calculation.")
            return

        tp_price = self.entry_price * (1 + self.take_profit)
        sl_price = self.entry_price * (1 - self.stop_loss)

        logger.info(
            f"[{state["timestamp"]}] 📈 현재 보유중 | 진입가={self.entry_price:.2f} | 현재가={state["price"]} | TP={tp_price} | SL={sl_price}"
        )

        bars_held = state["bar"] - self.entry_bar
        if bars_held < self.min_holding_period:
            return

        # Take Profit
        if sell_cond.get("take_profit", False) and state["price"] >= tp_price:
            self._sell_action(state, "Take Profit")
            return

        # Stop Loss
        if sell_cond.get("stop_loss", False) and state["price"] <= sl_price:
            self._sell_action(state, "Stop Loss")
            return

        # MACD Exit
        if sell_cond.get("macd_exit", False) and self._is_dead_cross():
            self._sell_action(state, "MACD Exit")
            return

        # Trailing Stop
        if sell_cond.get("trailing_stop", False) and self.entry_price is not None:
            if self.highest_price is None or state["price"] > self.highest_price:
                self.highest_price = state["price"]

            trailing_limit = (
                self.highest_price
                - (self.highest_price - self.entry_price) * self.trailing_stop_pct
            )
            if state["price"] <= trailing_limit:
                self._sell_action(state, "Trailing Stop")
                return

    def _sell_action(self, state, reason):
        self.position.close()
        self.sell()
        MACDStrategy.trade_events.append(
            (
                state["bar"],
                "SELL",
                reason,
                state["macd"],
                state["signal"],
                state["price"],
            )
        )
        logger.info(
            f"[{state["timestamp"]}] ✅ 매도 ({reason}) : bar={state["bar"]} | price={state["price"]} | macd={state["macd"]} | signal={state["signal"]}"
        )

    def _reset_entry(self):
        self.entry_price = None
        self.entry_bar = None
        self.highest_price = None
        self.golden_cross_pending = False
