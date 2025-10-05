from backtesting import Strategy
import pandas as pd
import logging
from config import (
    CONDITIONS_JSON_FILENAME,
    SIGNAL_CONFIRM_ENABLED,
    TRAILING_STOP_PERCENT,
    AUDIT_LOG_SKIP_POS,             # ← 사용
    AUDIT_SKIP_POS_SAMPLE_N,        # ← 사용
    AUDIT_DEDUP_PER_BAR             # ← 사용
)
import json
from pathlib import Path

# Audit
from services.db import insert_buy_eval, insert_sell_eval, insert_settings_snapshot, has_open_by_orders
from services.init_db import get_db_path

import inspect, os


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
        logger.info(f"[BOOT] strategy_file={os.path.abspath(inspect.getfile(self.__class__))}")
        logger.info(f"[BOOT] __name__={__name__} __package__={__package__}")

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

        # --- 감사 로그 제어 상태 (최소 수정)
        self._last_buy_audit_bar = None
        self._last_skippos_audit_bar = None
        self._last_sell_sig = None
        self._sell_sample_n = 60   # 필요시 config로 치환 가능

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

        self._cond_path = Path(f"{getattr(self, 'user_id', 'UNKNOWN')}_{CONDITIONS_JSON_FILENAME}")
        self._cond_mtime = self._cond_path.stat().st_mtime if self._cond_path.exists() else None

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

        try:
            _uid = getattr(self, "user_id", None)
            _dbp = get_db_path(_uid if _uid else "UNKNOWN")
            p = Path(_dbp)
            logger.info(f"[AUDIT-PATH] user_id={_uid} → db={_dbp} (exists={p.exists()} size={p.stat().st_size if p.exists() else 'NA'})")
        except Exception as e:
            logger.warning(f"[AUDIT-PATH] failed to resolve db path: {e}")

    def _maybe_reload_conditions(self):
        try:
            if self._cond_path and self._cond_path.exists():
                mtime = self._cond_path.stat().st_mtime
                if self._cond_mtime != mtime:
                    with self._cond_path.open("r", encoding="utf-8") as f:
                        self.conditions = json.load(f)
                    self._cond_mtime = mtime
                    logger.info(f"🔄 Condition reloaded: {self._cond_path}")
                    self._log_conditions()
        except Exception as e:
            logger.warning(f"⚠️ Condition hot-reload failed (ignored): {e}")

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
        if len(self.macd_line) < 2 or len(self.signal_line) < 2:
            return False
        return (
            self.macd_line[-2] <= self.signal_line[-2]
            and self.macd_line[-1] > self.signal_line[-1]
        )

    def _is_dead_cross(self):
        if len(self.macd_line) < 2 or len(self.signal_line) < 2:
            return False
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

    def _check_macd_pos(self, state, eps=1e-8) -> bool:
        return state["macd"] >= (self.macd_threshold - eps)

    def _check_signal_pos(self, state, eps=1e-8) -> bool:
        return state["signal"] >= (self.macd_threshold - eps)
    
    def _reconcile_entry_with_wallet(self):
        """지갑/포지션과 불일치할 때 고아 엔트리를 정리한다(선택적)."""
        try:
            sz = getattr(getattr(self, "position", None), "size", 0) or 0
            if sz == 0 and self.entry_price is not None:
                has_wallet_pos = None
                if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
                    has_wallet_pos = bool(self.has_wallet_position(self.ticker))
                if has_wallet_pos is None or has_wallet_pos is False:
                    logger.warning("🧹 고아 엔트리 정리: 포지션/지갑에 보유 없음 → entry 리셋")
                    self._reset_entry()
        except Exception as e:
            logger.debug(f"[reconcile] skip ({e})")

    # -------------------
    # --- Buy/Sell Logic
    # -------------------
    def next(self):
        self._maybe_reload_conditions()

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
             lambda: self._check_macd_pos(state)),
            ("signal_positive", buy_cond.get("signal_positive", False),
             lambda: self._check_signal_pos(state)),
            ("bullish_candle", buy_cond.get("bullish_candle", False),
             self._is_bullish_candle),
            ("macd_trending_up", buy_cond.get("macd_trending_up", False),
             self._is_macd_trending_up),
            ("above_ma20", buy_cond.get("above_ma20", False),
             self._is_above_ma20),
            ("above_ma60", buy_cond.get("above_ma60", False),
             self._is_above_ma60),
        ]

    # ★ BUY 체크 실행
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
        ticker = getattr(self, "ticker", "UNKNOWN")

        # A. 데이터 소스 3중 게이트
        try:
            db_open = has_open_by_orders(self.user_id, ticker)
        except Exception as e:
            logger.error(f"[BUY-GATE] has_open_by_orders 실패: {e}")
            db_open = None

        pos_sz = int(getattr(getattr(self, "position", None), "size", 0) or 0)
        wallet_open = None
        if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
            wallet_open = bool(self.has_wallet_position(ticker))

        have_open_gate = (bool(db_open) is True) or (pos_sz > 0) or (wallet_open is True)

        state = self._current_state()
        logger.info(f"[BUY-GATE] db_open={db_open} pos_size={pos_sz} wallet_open={wallet_open} entry_price={getattr(self,'entry_price',None)}")

        # B. 고아 엔트리 리셋 (모두 없음일 때만)
        if (not have_open_gate) and (getattr(self, "entry_price", None) is not None):
            self._reset_entry()
            logger.info("🧹 고아 엔트리 정리: 모든 소스에서 포지션 없음 → entry 리셋")

        # C. 보유 중이면 BUY 스킵 (+ 필요 시 샘플링 감사)
        if have_open_gate:
            if AUDIT_LOG_SKIP_POS:
                if not (AUDIT_DEDUP_PER_BAR and self._last_skippos_audit_bar == state["bar"]):
                    if (AUDIT_SKIP_POS_SAMPLE_N is None) or (AUDIT_SKIP_POS_SAMPLE_N <= 0) or (state["bar"] % AUDIT_SKIP_POS_SAMPLE_N == 0):
                        try:
                            insert_buy_eval(
                                user_id=self.user_id,
                                ticker=ticker,
                                interval_sec=getattr(self,"interval_sec",60),
                                bar=state["bar"], price=state["price"], macd=state["macd"], signal=state["signal"],
                                have_position=True, overall_ok=False,
                                failed_keys=[], checks={"note":"have_position"},
                                notes="BUY_SKIP_POS"
                            )
                            self._last_skippos_audit_bar = state["bar"]
                            logger.info(f"[AUDIT-BUY] inserted | bar={state['bar']} note=BUY_SKIP_POS")
                        except Exception as e:
                            logger.error(f"[AUDIT-BUY] insert failed(SKIP_POS): {e} | bar={state['bar']}")
            logger.debug(f"[BUY] SKIP (이미 보유) | bar={state['bar']} price={state['price']:.6f}")
            return

        # D. 정상 BUY 평가/체결
        state = self._current_state()
        buy_cond = self.conditions.get("buy", {})
        report, enabled_keys, failed_keys, overall_ok = self._buy_checks_report(state, buy_cond)

        # 감사 적재(바 중복 방지)
        if AUDIT_DEDUP_PER_BAR and self._last_buy_audit_bar == state["bar"]:
            logger.info(f"[AUDIT-BUY] DUP SKIP | bar={state['bar']}")
        else:
            try:
                insert_buy_eval(
                    user_id=self.user_id,
                    ticker=ticker,
                    interval_sec=getattr(self,"interval_sec",60),
                    bar=state["bar"], price=state["price"], macd=state["macd"], signal=state["signal"],
                    have_position=False, overall_ok=overall_ok,
                    failed_keys=failed_keys, checks=report,
                    notes=("OK" if overall_ok else "FAILED")
                )
                self._last_buy_audit_bar = state["bar"]
                logger.info(f"[AUDIT-BUY] inserted | bar={state['bar']} overall_ok={overall_ok}")
            except Exception as e:
                logger.error(f"[AUDIT-BUY] insert failed: {e} | bar={state['bar']}")

        if not overall_ok:
            if failed_keys:
                logger.info(f"⏸️ BUY 보류 | 실패 조건: {failed_keys}")
            return

        reasons = [k for k in enabled_keys if report[k]["pass"] == 1]
        self._buy_action(state, reasons=reasons, details=report)
    
    def _buy_action(self, state, reasons: list[str], details: dict | None = None):
        # 같은 bar 중복 BUY 방지
        if getattr(self, "_last_buy_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUPLICATE BUY SKIP | bar={state['bar']} reasons={' + '.join(reasons) if reasons else ''}")
            return

        self.buy()

        # 엔트리/피크/트레일링 상태 초기화
        self.entry_price = state["price"]
        self.entry_bar = state["bar"]
        self.highest_price = self.entry_price
        self.trailing_armed = False
        self.golden_cross_pending = False

        reason_str = "+".join(reasons) if reasons else "BUY"
        self._emit_trade("BUY", state, reason=reason_str)
        self._last_buy_bar = state["bar"]

    def _evaluate_sell(self):
        if not self.position:
            return

        state = self._current_state()
        sell_cond = self.conditions.get("sell", {})

        if self.entry_price is None:
            logger.debug("entry_price is None. Jump TP / SL Calculation.")  # ← 경고→디버그로 완화
            return

        tp_price = self.entry_price * (1 + self.take_profit)
        sl_price = self.entry_price * (1 - self.stop_loss)
        bars_held = state["bar"] - self.entry_bar if self.entry_bar is not None else 0

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
        if ts_enabled:
            ts_armed = self.trailing_armed or (state["price"] >= tp_price - eps)
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

        # Take Profit (TS 꺼져 있을 때만 즉시 매도)
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

        # 트리거 판단 (전략 우선순위 유지)
        trigger_key = None
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

        # --- SELL 감사 적재: 트리거/상태변화/샘플링일 때만 ---
        import hashlib, json
        sig = hashlib.md5(json.dumps({
            "armed": ts_armed,
            "highest": round((self.highest_price or 0.0), 6),
            "bars_held": bars_held,
            "pass_map": {k:v["pass"] for k,v in checks.items() if v.get("enabled")==1}
        }, sort_keys=True, default=str).encode()).hexdigest()

        should_insert = (trigger_key is not None)
        if not should_insert:
            if sig != self._last_sell_sig:
                should_insert = True
            elif self._sell_sample_n and (state["bar"] % self._sell_sample_n == 0):
                should_insert = True

        if should_insert:
            try:
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
                self._last_sell_sig = sig
                logger.info(f"[AUDIT-SELL] inserted | uid={getattr(self,'user_id',None)} bar={state['bar']} trigger={trigger_key}")
            except Exception as e:
                logger.error(f"[AUDIT-SELL] insert failed: {e} | uid={getattr(self,'user_id',None)} bar={state['bar']} checks_keys={list(checks.keys())}")

        # Stop Loss
        if sl_enabled and sl_hit:
            logger.info("🛑 SL HIT → SELL")
            self._sell_action(state, "Stop Loss")
            return

        # Trailing Stop
        if ts_enabled:
            if not self.trailing_armed and state["price"] >= tp_price - eps:
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

                if bars_held >= self.min_holding_period and state["price"] <= trailing_limit + eps:
                    logger.info("🛑 TS HIT → SELL")
                    self._sell_action(state, "Trailing Stop")
                    return

        # Take Profit
        if tp_enabled and tp_hit:
            logger.info("💰 TP HIT (no TS) → SELL")
            self._sell_action(state, "Take Profit")
            return

        # MACD Negative
        if macdneg_enabled and macdneg_hit:
            logger.info("📉 MACD < threshold → SELL")
            self._sell_action(state, "MACD Negative")
            return
        
        # Dead Cross
        if dead_enabled and self._is_dead_cross():
            logger.info("🛑 Dead Cross → SELL")
            self._sell_action(state, "Dead Cross")
            return

    def _sell_action(self, state, reason):
        if getattr(self, "_last_sell_bar", None) == state["bar"]:
            logger.info(f"⏹️ DUPLICATE SELL SKIP | bar={state['bar']} reason={reason}")
            return
        self._last_sell_bar = state["bar"]
        
        self.position.close()
        self._emit_trade("SELL", state, reason=reason)
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
            "type": kind,
            "reason": reason,
            "timestamp": state["timestamp"],
            "price": state["price"],
            "macd": state["macd"],
            "signal": state["signal"],
            "entry_price": self.entry_price,
            "entry_bar": self.entry_bar,
            "bars_held": state["bar"] - (self.entry_bar if self.entry_bar is not None else state["bar"]),
            "tp": (self.entry_price * (1 + self.take_profit)) if self.entry_price else None,
            "sl": (self.entry_price * (1 - self.stop_loss)) if self.entry_price else None,
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

        golden = self._is_golden_cross()
        macd_pos = self._check_macd_pos(state, eps)
        signal_pos = self._check_signal_pos(state, eps)
        bull = self._is_bullish_candle()
        trending = self._is_macd_trending_up()
        above20 = self._is_above_ma20()
        above60 = self._is_above_ma60()

        add("golden_cross",   buy_cond.get("golden_cross", False),   golden,       {"macd":state["macd"], "signal":state["signal"]})
        add("macd_positive",  buy_cond.get("macd_positive", False),  macd_pos,     {"macd":state["macd"], "thr":self.macd_threshold})
        add("signal_positive",buy_cond.get("signal_positive", False),signal_pos,   {"signal":state["signal"], "thr":self.macd_threshold})
        add("bullish_candle", buy_cond.get("bullish_candle", False), bull,         {"open":float(self.data.Open[-1]), "close":state["price"]})
        add("macd_trending_up", buy_cond.get("macd_trending_up", False), trending, None)
        add("above_ma20",     buy_cond.get("above_ma20", False),     above20,      {"ma20": float(self.ma20[-1])})
        add("above_ma60",     buy_cond.get("above_ma60", False),     above60,      {"ma60": float(self.ma60[-1])})

        if self.signal_confirm_enabled:
            gate_ok = state["signal"] >= (self.macd_threshold - eps)
            report["signal_confirm"] = {"enabled":1, "pass": 1 if gate_ok else 0, "value":{"signal":state["signal"], "thr":self.macd_threshold}}

        enabled_keys = [k for k,v in report.items() if v["enabled"]==1]
        failed_keys  = [k for k in enabled_keys if report[k]["pass"]==0]
        overall_ok = (len(failed_keys)==0)

        return report, enabled_keys, failed_keys, overall_ok
