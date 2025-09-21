from backtesting import Strategy
import pandas as pd
import logging
from config import (
    CONDITIONS_JSON_FILENAME,
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
        self.trailing_arm = False
        self.golden_cross_pending = False
        self.last_cross_type = None
        self._last_sell_bar = None

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
                        "golden_cross",
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
        # logger.info(
        #     f"{position_color}[{state["timestamp"]}] 🧾 bar={state["bar"]} price={state["price"]} macd={state["macd"]:.5f} "
        #     f"signal={state["signal"]:.5f} vol={state["volatility"]:.5f} cross={self.last_cross_type}"
        # )

    # ★ BUY 체크 정의
    def _buy_check_defs(self, state, buy_cond):
        return [
            ("golden_cross",    buy_cond.get("golden_cross", False),
             lambda: self.golden_cross_pending and self.last_cross_type == "Golden"),
            ("macd_positive",   buy_cond.get("macd_positive", False),
             lambda: state["macd"] > 0),
            ("signal_positive", buy_cond.get("signal_positive", False),
             lambda: state["signal"] > 0),
            ("bullish_candle",  buy_cond.get("bullish_candle", False),
             self._is_bullish_candle),
            ("macd_trending_up",buy_cond.get("macd_trending_up", False),
             self._is_macd_trending_up),
            ("above_ma20",      buy_cond.get("above_ma20", False),
             self._is_above_ma20),
            ("above_ma60",      buy_cond.get("above_ma60", False),
             self._is_above_ma60),
        ]

    # ★ BUY 체크 실행 (enabled된 것만 평가 → 통과/실패/세부 결과 반환)
    def _run_buy_checks(self, state, buy_cond):
        passed, failed, details = [], [], {}
        for name, enabled, fn in self._buy_check_defs(state, buy_cond):
            if not enabled:
                continue
            try:
                ok = bool(fn()) if callable(fn) else bool(fn)
            except Exception as e:
                logger.error(f"❌ BUY 체크 '{name}' 실행 오류: {e}")
                ok = False
            details[name] = ok
            logger.info(f"🧪 BUY 체크 '{name}': enabled=True -> {'PASS' if ok else 'FAIL'}")
            (passed if ok else failed).append(name)

        # ★ 옵션 게이트: signal_confirm (전역 플래그)
        if self.signal_confirm_enabled:
            ok = state["signal"] >= self.macd_threshold
            details["signal_confirm"] = ok
            logger.info(
                f"🧪 BUY 체크 'signal_confirm': enabled=True -> {'PASS' if ok else 'FAIL'} "
                f"(signal={state['signal']:.5f}, threshold={self.macd_threshold:.5f})"
            )
            (passed if ok else failed).append("signal_confirm")

        overall_ok = (len(failed) == 0)
        return overall_ok, passed, failed, details

    def _evaluate_buy(self):
        if self.position and not self.golden_cross_pending:
            return

        state = self._current_state()
        buy_cond = self.conditions.get("buy", {})

        overall_ok, passed, failed, details = self._run_buy_checks(state, buy_cond)
        if not overall_ok:
            # 실패 이유를 로그로 남겨 추적 용이
            if failed:
                logger.info(f"⏸️ BUY 보류 | 실패 조건: {failed}")
            return

        # ★ 모든 enabled 조건 통과 → BUY 실행 (사유 리스트/세부정보 전달)
        self._buy_action(state, reasons=passed, details=details)
    
    def _buy_action(self, state, reasons: list[str], details: dict | None = None):
        """BUY 체결 + 상태 갱신 + 이벤트 기록 (중복 방지 포함)"""
        # ★ 같은 bar 중복 BUY 방지
        if getattr(self, "_last_buy_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUP BUY SKIP | bar={state['bar']} reasons={' + '.join(reasons) if reasons else ''}")
            return

        self.buy()

        # ★ 엔트리/피크/트레일링 상태 초기화
        self.entry_price = state["price"]
        self.entry_bar = state["bar"]
        self.highest_price = self.entry_price
        self.trailing_armed = False
        self.golden_cross_pending = False

        # ★ reason을 'golden_cross + macd_positive + ...' 형태로 전달 (하위호환 tuple 유지)
        reason_str = "+".join(reasons) if reasons else "BUY"
        self._emit_trade("BUY", state, reason=reason_str)
        # MACDStrategy.trade_events.append(
        #     (state["bar"], "BUY", reason_str, state["macd"], state["signal"], state["price"])
        # )
        # logger.info(
        #     "✅ BUY | reasons=%s price=%.2f macd=%.5f signal=%.5f bar=%d",
        #     reason_str, state["price"], state["macd"], state["signal"], state["bar"]
        # )
        # if details:
        #     logger.info("🧾 BUY details: %s", {k: v for k, v in details.items()})

        self._last_buy_bar = state["bar"]

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

        # logger.info(
        #     f"[{state["timestamp"]}] 📈 현재 보유중 | 진입가={self.entry_price:.2f} | 현재가={state["price"]} | TP={tp_price} | SL={sl_price}"
        # )

        bars_held = state["bar"] - self.entry_bar

        # logger.info(
        #     f"🔎 SELL EVAL | bar={state['bar']} price={state['price']:.2f} entry={self.entry_price:.2f} "
        #     f"TP={tp_price:.2f} SL={sl_price:.2f} held={bars_held} armed={self.trailing_armed} "
        #     f"high={self.highest_price if self.highest_price is not None else float('nan')}"
        # )

        # Stop Loss
        if sell_cond.get("stop_loss", False) and state["price"] <= sl_price:
            logger.info("🛑 SL HIT → SELL")
            self._sell_action(state, "Stop Loss")
            return

        # Trailing Stop
        if sell_cond.get("trailing_stop", False):
            # TP 도달 시점에 TS 무장
            if not self.trailing_arm and state["price"] >= tp_price:
                self.trailing_arm = True
                self.highest_price = max(self.highest_price or state["price"], state["price"])
                logger.info(
                    f"🟢 TS ARMED at {state['price']:.2f} (TP reached) | high={self.highest_price:.2f}"
                )
                
            # TS 무장 후엔 Peak 갱신 및 하락폭 체크
            if self.trailing_arm:
                if self.highest_price is None or state["price"] > self.highest_price:
                    self.highest_price = state["price"]
                
                trailing_limit = self.highest_price * (1 - self.trailing_stop_pct)
                logger.info(
                    f"🔧 TS CHECK | price={state['price']:.2f} high={self.highest_price:.2f} "
                    f"limit={trailing_limit:.2f} pct={self.trailing_stop_pct:.3f}"
                )

                if bars_held >= self.min_holding_period and state["price"] <= trailing_limit:
                    logger.info("🛑 TS HIT → SELL")
                    self._sell_action(state, "Trailing Stop")
                    return

        # Take Profit
        if sell_cond.get("take_profit", False) and state["price"] >= tp_price:
            # TS가 비활성화인 경우에만 TP로 매도
            if not sell_cond.get("trailing_stop", False):
                if bars_held >= self.min_holding_period:
                    logger.info("💰 TP HIT (no TS) → SELL")
                    self._sell_action(state, "Take Profit")
                    return
                else:
                    # TS가 켜져있으면 위에서 무장만 하고 여기서는 매도하지 않음
                    logger.info("💡 TP reached but TS enabled → armed only")

        # MACD Exit
        if sell_cond.get("macd_exit", False) and bars_held >= self.min_holding_period and self._is_dead_cross():
            logger.info("📉 MACD EXIT → SELL")  # ★ LOG
            self._sell_action(state, "MACD Exit")
            return

    def _sell_action(self, state, reason):
        # 중복 방지: 같은 bar에서 두번 SELL 호출되면 무시
        if getattr(self, "_last_sell_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUP SELL SKIP | bar={state['bar']} reason={reason}")
            return
        self._last_sell_bar = state["bar"]
        
        self.position.close()

        self._emit_trade("SELL", state, reason=reason)
        # MACDStrategy.trade_events.append(
        #     (
        #         state["bar"],
        #         "SELL",
        #         reason,
        #         state["macd"],
        #         state["signal"],
        #         state["price"],
        #     )
        # )
        # logger.info(
        #     f"[{state["timestamp"]}] ✅ 매도 ({reason}) : bar={state["bar"]} | price={state["price"]} | macd={state["macd"]} | signal={state["signal"]}"
        # )
        self._reset_entry()

    def _reset_entry(self):
        self.entry_price = None
        self.entry_bar = None
        self.highest_price = None
        self.trailing_arm = False
        self.golden_cross_pending = False

    # 공통 이벤트 헬퍼 (BUY/SELL 모두에 사용)
    def _emit_trade(self, kind: str, state: dict, reason: str = ""):
        evt = {
            "bar": state["bar"],
            "type": kind,                    # "BUY" / "SELL"
            "reason": reason,                # 매도 사유(예: "Take Profit", "Trailing Stop")
            "timestamp": state["timestamp"],

            # 상태 스냅샷
            "price": state["price"],
            "macd": state["macd"],
            "signal": state["signal"],

            # 포지션 관련
            "entry_price": self.entry_price,
            "entry_bar": self.entry_bar,
            "bars_held": state["bar"] - (self.entry_bar if self.entry_bar is not None else state["bar"]),

            # 리스크 파라미터
            "tp": (self.entry_price * (1 + self.take_profit)) if self.entry_price else None,
            "sl": (self.entry_price * (1 - self.stop_loss)) if self.entry_price else None,

            # 트레일링 상태
            "highest": self.highest_price,
            "ts_pct": getattr(self, "trailing_stop_pct", None),
            "ts_armed": getattr(self, "trailing_armed", False),
        }
        MACDStrategy.trade_events.append(evt)
