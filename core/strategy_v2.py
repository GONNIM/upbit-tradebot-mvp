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

# Audit
from services.db import insert_buy_eval, insert_sell_eval, insert_settings_snapshot


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
        self.trailing_armed = False
        self.golden_cross_pending = False
        self.trailing_stop_pct = TRAILING_STOP_PERCENT
        self.last_cross_type = None
        self._last_sell_bar = None

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

        self.conditions = self._load_conditions()
        self._log_conditions()

        try:
            insert_settings_snapshot(
                user_id=self.user_id,
                ticker=getattr(self,"ticker","UNKNOWN"),
                interval_sec=getattr(self,"interval_sec",60),
                tp=self.take_profit, sl=self.stop_loss,
                ts_pct=getattr(self,"trailing_stop_pct", None),
                signal_gate=self.signal_confirm_enabled,
                threshold=self.macd_threshold,
                buy_dict=self.conditions.get("buy", {}),
                sell_dict=self.conditions.get("sell", {})
            )
        except Exception as e:
            logger.warning(f"[AUDIT] settings snapshot failed (ignored): {e}")


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
                    ["trailing_stop", "take_profit", "stop_loss", "macd_negative", "dead_cross"], False
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
        if len(self.macd_line) < 3:
            return False
        a, b, c = self.macd_line[-3], self.macd_line[-2], self.macd_line[-1]
        if pd.isna(a) or pd.isna(b) or pd.isna(c):
            return False
        return a < b < c

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

    # ★ BUY 체크 정의
    def _buy_check_defs(self, state, buy_cond):
        return [
            ("golden_cross", buy_cond.get("golden_cross", False),
             lambda: self.golden_cross_pending and self.last_cross_type == "Golden"),
            ("macd_positive", buy_cond.get("macd_positive", False),
             lambda: state["macd"] > 0),
            ("signal_positive", buy_cond.get("signal_positive", False),
             lambda: state["signal"] > 0),
            ("bullish_candle", buy_cond.get("bullish_candle", False),
             self._is_bullish_candle),
            ("macd_trending_up", buy_cond.get("macd_trending_up", False),
             self._is_macd_trending_up),
            ("above_ma20", buy_cond.get("above_ma20", False),
             self._is_above_ma20),
            ("above_ma60", buy_cond.get("above_ma60", False),
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
        if self.position:
            st = self._current_state()
            insert_buy_eval(
                user_id=self.user_id,
                ticker=getattr(self, "ticker", "UNKNOWN"),
                interval_sec=getattr(self, "interval_sec", 60),
                bar=st["bar"], price=st["price"], macd=st["macd"], signal=st["signal"],
                have_position=True, overall_ok=False,
                failed_keys=[], checks={"note":"have_position"}, notes="BUY_SKIP_POS"
            )
            return

        state = self._current_state()
        buy_cond = self.conditions.get("buy", {})

        # ★ 전 항목 리포트 생성
        report, enabled_keys, failed_keys, overall_ok = self._buy_checks_report(state, buy_cond)
        # 감사 적재
        insert_buy_eval(
            user_id=self.user_id,
            ticker=getattr(self, "ticker", "UNKNOWN"),
            interval_sec=getattr(self, "interval_sec", 60),
            bar=state["bar"], price=state["price"], macd=state["macd"], signal=state["signal"],
            have_position=False, overall_ok=overall_ok,
            failed_keys=failed_keys, checks=report,
            notes=("OK" if overall_ok else "FAILED")
        )

        overall_ok, passed, failed, details = self._run_buy_checks(state, buy_cond)
        if not overall_ok:
            if failed:
                logger.info(f"⏸️ BUY 보류 | 실패 조건: {failed}")
            return

        # ★ 모든 enabled 조건 통과 → BUY 실행 (사유 리스트/세부정보 전달)
        self._buy_action(state, reasons=passed, details=details)
    
    def _buy_action(self, state, reasons: list[str], details: dict | None = None):
        """BUY 체결 + 상태 갱신 + 이벤트 기록 (중복 방지 포함)"""
        # ★ 같은 bar 중복 BUY 방지
        if getattr(self, "_last_buy_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUPLICATE BUY SKIP | bar={state['bar']} reasons={' + '.join(reasons) if reasons else ''}")
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
        bars_held = state["bar"] - self.entry_bar if self.entry_bar is not None else 0

        # --- 전 항목 평가 (raw 값 포함) ---
        eps = 1e-8
        checks = {}

        def add(name, enabled, passed, raw=None):
            checks[name] = {"enabled": 1 if enabled else 0, "pass": 1 if passed else 0, "value": raw}

        # Stop Loss
        sl_enabled = sell_cond.get("stop_loss", False)
        sl_hit = state["price"] <= sl_price + eps
        add("stop_loss", sl_enabled, sl_hit, {"price":state["price"], "sl_price":sl_price})

        # Trailing Stop
        ts_enabled = sell_cond.get("trailing_stop", False)
        # 무장 상태/최고가/리밋 계산
        if ts_enabled:
            ts_armed = self.trailing_armed or (state["price"] >= tp_price - eps)
            # 무장 시 최고가 갱신
            highest = max(self.highest_price or state["price"], state["price"]) if ts_armed else (self.highest_price or None)
            trailing_limit = (highest * (1 - self.trailing_stop_pct)) if (ts_armed and highest) else None
            ts_hit = (ts_armed and trailing_limit is not None
                    and bars_held >= self.min_holding_period
                    and state["price"] <= trailing_limit + eps)
        else:
            ts_armed, highest, trailing_limit, ts_hit = False, self.highest_price, None, False

        add("trailing_stop", ts_enabled, ts_hit, {
            "armed": ts_armed, "highest": highest, "limit": trailing_limit,
            "pct": getattr(self,"trailing_stop_pct", None),
            "bars_held": bars_held, "min_hold": self.min_holding_period
        })

        # Take Profit  (TS 꺼져 있을 때만 즉시 매도 트리거)
        tp_enabled = sell_cond.get("take_profit", False)
        tp_hit = (state["price"] >= tp_price - eps) and (not ts_enabled)
        add("take_profit", tp_enabled, tp_hit, {"price":state["price"], "tp_price":tp_price, "ts_enabled":ts_enabled})

        # MACD Negative
        macdneg_enabled = sell_cond.get("macd_negative", False)
        macdneg_hit = state["macd"] < (self.macd_threshold - eps)
        add("macd_negative", macdneg_enabled, macdneg_hit, {"macd":state["macd"], "thr":self.macd_threshold})

        # Dead Cross
        dead_enabled = sell_cond.get("dead_cross", False)
        dead_hit = self._is_dead_cross()
        add("dead_cross", dead_enabled, dead_hit, {"macd":state["macd"], "signal":state["signal"]})

        # --- 감사 적재 (트리거 키는 실제 체결된 항목으로 세팅; 아래 로직과 동일한 우선순위) ---
        trigger_key = None
        # 전략의 실제 우선순위와 일치하도록 순서 유지
        if sl_enabled and sl_hit:
            trigger_key = "Stop Loss"
        elif ts_enabled and ts_hit:
            trigger_key = "Trailing Stop"
        elif tp_enabled and tp_hit:
            trigger_key = "Take Profit"
        elif macdneg_enabled and macdneg_hit:
            trigger_key = "MACD Negative"
        elif dead_enabled and dead_hit:
            trigger_key = "Dead Cross"

        insert_sell_eval(
            user_id=self.user_id,
            ticker=getattr(self,"ticker","UNKNOWN"),
            interval_sec=getattr(self,"interval_sec",60),
            bar=state["bar"], price=state["price"],
            macd=state["macd"], signal=state["signal"],
            tp_price=tp_price, sl_price=sl_price,
            highest=self.highest_price, ts_pct=getattr(self,"trailing_stop_pct", None),
            ts_armed=self.trailing_armed, bars_held=bars_held,
            checks=checks,
            triggered=(trigger_key is not None),
            trigger_key=trigger_key,
            notes=""
        )
        
        # Stop Loss
        if sl_enabled and sl_hit:
            logger.info("🛑 SL HIT → SELL")
            self._sell_action(state, "Stop Loss")
            return

        # Trailing Stop
        if ts_enabled:
            if not self.trailing_armed and state["price"] >= tp_price:
                self.trailing_armed = True
                self.highest_price = max(self.highest_price or state["price"], state["price"])
                logger.info(f"🟢 TS ARMED at {state['price']:.2f} (TP reached) | high={self.highest_price:.2f}")
                
            if self.trailing_armed:
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
        if tp_enabled and state["price"] >= tp_price:
            if not ts_enabled:
                logger.info("💰 TP HIT (no TS) → SELL")
                self._sell_action(state, "Take Profit")
                return
            else:
                logger.info("💡 TP reached but TS enabled → armed only")

        # MACD Negative
        if macdneg_enabled and state["macd"] < 0:
            logger.info("📉 MACD < threshold → SELL")  # ★ LOG
            self._sell_action(state, "MACD Negative")
            return
        
        # Dead Cross
        if dead_enabled and self._is_dead_cross():
            logger.info("🛑 Dead Cross → SELL")  # ★ LOG
            self._sell_action(state, "Dead Cross")
            return

    def _sell_action(self, state, reason):
        # 중복 방지: 같은 bar에서 두번 SELL 호출되면 무시
        if getattr(self, "_last_sell_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUPLICATE SELL SKIP | bar={state['bar']} reason={reason}")
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
        self.trailing_armed = False
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


    # Audit
    def _buy_checks_report(self, state, buy_cond):
        eps = 1e-8
        report = {}

        def add(name, enabled, passed, raw=None):
            report[name] = {"enabled": 1 if enabled else 0, "pass": 1 if passed else 0, "value": raw}

        # 각 항목 계산
        golden = self._is_golden_cross()
        macd_pos = state["macd"] >= (self.macd_threshold - eps)  # MACD > threshold
        signal_pos = state["signal"] >= (self.macd_threshold - eps)  # Signal > threshold
        bull = self._is_bullish_candle()
        trending = self._is_macd_trending_up()
        above20 = self._is_above_ma20()
        above60 = self._is_above_ma60()

        # 리포트 채우기 (ON/OFF 그대로 기록)
        add("golden_cross",   buy_cond.get("golden_cross", False),   golden,       {"macd":state["macd"], "signal":state["signal"]})
        add("macd_positive",  buy_cond.get("macd_positive", False),  macd_pos,     {"macd":state["macd"], "thr":self.macd_threshold})
        add("signal_positive",buy_cond.get("signal_positive", False),signal_pos,   {"signal":state["signal"], "thr":self.macd_threshold})
        add("bullish_candle", buy_cond.get("bullish_candle", False), bull,         {"open":float(self.data.Open[-1]), "close":state["price"]})
        add("macd_trending_up", buy_cond.get("macd_trending_up", False), trending, None)
        add("above_ma20",     buy_cond.get("above_ma20", False),     above20,      {"ma20": float(self.ma20[-1])})
        add("above_ma60",     buy_cond.get("above_ma60", False),     above60,      {"ma60": float(self.ma60[-1])})

        # 전역 게이트 (signal_confirm_enabled)
        if self.signal_confirm_enabled:
            gate_ok = state["signal"] >= (self.macd_threshold - eps)
            report["signal_confirm"] = {"enabled":1, "pass": 1 if gate_ok else 0, "value":{"signal":state["signal"], "thr":self.macd_threshold}}

        # 전체 통과 여부(ON인 항목이 모두 pass)
        enabled_keys = [k for k,v in report.items() if v["enabled"]==1]
        failed_keys  = [k for k in enabled_keys if report[k]["pass"]==0]
        overall_ok = (len(failed_keys)==0)

        return report, enabled_keys, failed_keys, overall_ok
