from backtesting import Strategy
import pandas as pd
import logging
from config import (
    CONDITIONS_JSON_FILENAME,
    SIGNAL_CONFIRM_ENABLED,
    TRAILING_STOP_PERCENT,
    AUDIT_LOG_SKIP_POS,
    AUDIT_SKIP_POS_SAMPLE_N,
    AUDIT_DEDUP_PER_BAR,
    TP_WITH_TS
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

    ignore_db_gate = False
    ignore_wallet_gate = False

    _seen_buy_audits = set()
    _seen_sell_audits = set()

    # =========================
    # 업비트 티커 정규화 유틸 추가
    #  - "KRW-WLFI" → "WLFI" 로 변환하여 월렛 조회 훅에 전달
    #  - 지갑 보유를 정확히 감지하지 못해 BUY 평가가 계속 도는 문제 방지
    # =========================
    @staticmethod
    def _norm_ticker(ticker: str) -> str:
        try:
            return (ticker or "").split("-")[-1].strip().upper()
        except Exception:
            return ticker

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

        # --- 감사 로그 제어 상태
        self._last_buy_audit_bar = None
        self._last_skippos_audit_bar = None
        self._last_sell_sig = None
        self._sell_sample_n = 60
        self._boot_start_bar = len(self.data) - 1
        self._last_buy_sig = None      # BUY 상태 시그니처(변화 감지용)
        self._buy_sample_n = 60        # 샘플링 주기(원하면 0/None으로 끔)

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
        uid = getattr(self, 'user_id', 'UNKNOWN')
        path = Path(f"{uid}_{CONDITIONS_JSON_FILENAME}")
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
            pd.Series(series).ewm(span=fast, adjust=False).mean()
            - pd.Series(series).ewm(span=slow, adjust=False).mean()
        ).values

    def _calculate_signal(self, macd, period):
        return pd.Series(macd).ewm(span=period, adjust=False).mean().values

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
                    # 월렛 훅 호출 시 티커 정규화
                    has_wallet_pos = bool(self.has_wallet_position(self._norm_ticker(self.ticker)))
                if has_wallet_pos is None or has_wallet_pos is False:
                    logger.warning("🧹 고아 엔트리 정리: 포지션/지갑에 보유 없음 → entry 리셋")
                    self._reset_entry()
        except Exception as e:
            logger.debug(f"[reconcile] skip ({e})")

    # -------------------
    # --- Buy/Sell Logic
    # -------------------
    def next(self):
        self._reconcile_entry_with_wallet()

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

    # --- 주문 이력 기반 Flat 판정 (옵션 훅) ---
    def _is_flat_by_history(self) -> bool | None:
        """
        True  : 최근 주문 이력이 '완료된 SELL'로 끝났거나, 주문이력이 없어서 Flat로 간주
        False : 최근 주문 이력이 '완료된 BUY'로 끝남 (보유 가정)
        None  : 판단 불가(훅 미제공/포맷 불명) → 기존 게이트만 사용
        기대 포맷: [{'side':'BUY'|'SELL', 'state':'completed'|'cancelled'|..., 'timestamp': ...}, ...]
        최신이 앞쪽에 오도록 정렬되어 있다고 가정(아닐 경우 정렬 시도)
        """
        try:
            if not hasattr(self, "fetch_orders") or not callable(self.fetch_orders):
                return None
            orders = self.fetch_orders(self.user_id, getattr(self, "ticker", "UNKNOWN"), limit=100) or []
            if not isinstance(orders, list):
                return None
            if len(orders) == 0:
                return True  # 이력이 없으면 Flat로 간주

            # 정렬 시도(옵셔널)
            try:
                orders = sorted(
                    orders,
                    key=lambda o: o.get("timestamp") or o.get("created_at") or 0,
                    reverse=True
                )
            except Exception:
                pass

            for o in orders:
                side = str(o.get("side", "")).upper()
                state = str(o.get("state") or o.get("status") or "").lower()
                if state == "completed":
                    if side == "SELL":
                        return True
                    if side == "BUY":
                        return False
                    # 다른 side 값은 무시하고 다음으로
            # 완료된 주문이 하나도 없으면 Flat로 보수적 간주
            return True
        except Exception as e:
            logger.debug(f"[HIST] flat-by-history check skipped: {e}")
            return None
        
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

        # --- 0) 실제 포지션: 엔진이 말하는 게 진실 ---
        inpos = bool(getattr(getattr(self, "position", None), "size", 0) > 0)

        # --- 1) 참고 정보 (오류 나면 False로) ---
        try:
            db_open = has_open_by_orders(self.user_id, ticker)
        except Exception as e:
            logger.error(f"[BUY-GATE] has_open_by_orders 실패: {e}")
            db_open = False

        wallet_open = None
        if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
            try:
                # 월렛 훅 호출 시 정규화된 티커 사용
                wallet_open = bool(self.has_wallet_position(self._norm_ticker(ticker)))
            except Exception:
                wallet_open = None      

        hist_flat = self._is_flat_by_history()  # True/False/None

        # --- 2) 보유 차단 여부 결정 ---
        # 지갑이 보유(True)면 BUY 평가를 확실히 차단하도록 반영
        blocked = inpos or (False if self.ignore_wallet_gate else bool(wallet_open)) or (False if self.ignore_db_gate else bool(db_open))

        state = self._current_state()
        # logger.info(
        #     "[BUY-GATE] inpos=%s db_open=%s wallet_open=%s hist_flat=%s "
        #     "ignore_db=%s ignore_wallet=%s entry_price=%s -> blocked=%s",
        #     inpos, db_open, wallet_open, hist_flat,
        #     self.ignore_db_gate, self.ignore_wallet_gate,
        #     getattr(self, 'entry_price', None), blocked
        # )

        # --- 3) 고아 엔트리 정리 ---
        if (not blocked) and (getattr(self, "entry_price", None) is not None) and (not inpos):
            self._reset_entry()
            logger.info("🧹 고아 엔트리 정리: 엔진은 미보유 → entry 리셋")

        # --- 4) 보유로 차단되면 감사만 적재하고 스킵 ---
        if blocked:
            if AUDIT_LOG_SKIP_POS:
                if not (AUDIT_DEDUP_PER_BAR and self._last_skippos_audit_bar == state["bar"]):
                    if (AUDIT_SKIP_POS_SAMPLE_N is None) or (AUDIT_SKIP_POS_SAMPLE_N <= 0) or (state["bar"] % AUDIT_SKIP_POS_SAMPLE_N == 0):
                        try:
                            insert_buy_eval(
                                user_id=self.user_id,
                                ticker=ticker,
                                interval_sec=getattr(self,"interval_sec",60),
                                bar=state["bar"], price=state["price"],
                                macd=state["macd"], signal=state["signal"],
                                have_position=True, overall_ok=False,
                                failed_keys=[], checks={"note":"blocked_by_position"},
                                notes="BUY_SKIP_POS" + f" | ts_bt={state['timestamp']} bar_bt={state['bar']}"
                            )
                            self._last_skippos_audit_bar = state["bar"]
                            # logger.info(f"[AUDIT-BUY] inserted | bar={state['bar']} note=BUY_SKIP_POS")
                        except Exception as e:
                            logger.error(f"[AUDIT-BUY] insert failed(SKIP_POS): {e} | bar={state['bar']}")
            logger.debug(f"[BUY] SKIP (보유 차단) | bar={state['bar']} price={state['price']:.6f}")
            return

        # 정상 BUY 평가/체결
        state = self._current_state()
        # ✅ 부팅 재생 바 스킵
        if state["bar"] < getattr(self, "_boot_start_bar", 0):
            return
        
        buy_cond = self.conditions.get("buy", {})
        report, enabled_keys, failed_keys, overall_ok = self._buy_checks_report(state, buy_cond)

        # BUY 조건이 하나도 켜져 있지 않으면 감사기록 자체를 생략 (노이즈 컷)
        if len(enabled_keys) == 0:
            return

        # ✅ 프로세스 내 동일 바 dedup
        key = (self.user_id, ticker, getattr(self,"interval_sec",60), state["bar"])
        if key in MACDStrategy._seen_buy_audits:
            return
        
        # ✅ BUY 상태 서명: 활성 조건들의 pass 맵 + 크로스 상태만 사용(숫자값 제외)
        import hashlib
        pass_map = {k: 1 if report.get(k, {}).get("pass", 0) == 1 else 0 for k in enabled_keys}
        buy_sig = hashlib.md5(json.dumps({
            "pass_map": pass_map,
            "golden_pending": bool(self.golden_cross_pending),
            "last_cross": self.last_cross_type,
        }, sort_keys=True, default=str).encode()).hexdigest()

        # ✅ 상태변화면 즉시 기록, 그 외엔 N-바마다 1회만 기록
        should_insert = False
        if (self._last_buy_sig is None) or (buy_sig != self._last_buy_sig):
            should_insert = True
        elif self._buy_sample_n and (state["bar"] % self._buy_sample_n == 0):
            should_insert = True
            
        # 감사 적재(바 중복 방지)
        if AUDIT_DEDUP_PER_BAR and self._last_buy_audit_bar == state["bar"]:
            logger.info(f"[AUDIT-BUY] DUP SKIP | bar={state['bar']}")
        else:
            if should_insert:
                try:
                    insert_buy_eval(
                        user_id=self.user_id,
                        ticker=ticker,
                        interval_sec=getattr(self,"interval_sec",60),
                        bar=state["bar"],
                        price=state["price"],
                        macd=state["macd"],
                        signal=state["signal"],
                        have_position=False,
                        overall_ok=overall_ok,
                        failed_keys=failed_keys,
                        checks=report,
                        notes=("OK" if overall_ok else "FAILED") + f" | ts_bt={state['timestamp']} bar_bt={state['bar']}"
                    )
                    MACDStrategy._seen_buy_audits.add(key)
                    self._last_buy_audit_bar = state["bar"]
                    # logger.info(f"[AUDIT-BUY] inserted | bar={state['bar']} overall_ok={overall_ok}")
                except Exception as e:
                    logger.error(f"[AUDIT-BUY] insert failed: {e} | bar={state['bar']}")

        if not overall_ok:
            # if failed_keys:
            #     logger.info(f"⏸️ BUY 보류 | 실패 조건: {failed_keys}")
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
        # ✅ 트레일링 스탑을 사용한다면 진입 즉시 ARM (TP 대기 없이 작동)
        try:
            sell_cond = self.conditions.get("sell", {}) if hasattr(self, "conditions") else {}
            self.trailing_armed = bool(sell_cond.get("trailing_stop", False))
        except Exception:
            self.trailing_armed = False
        self.golden_cross_pending = False

        reason_str = "+".join(reasons) if reasons else "BUY"
        self._emit_trade("BUY", state, reason=reason_str)
        self._last_buy_bar = state["bar"]

    def _evaluate_sell(self):
        ticker = getattr(self, "ticker", "UNKNOWN")
        if not self.position:
            try:
                if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
                    # 월렛 훅 호출 시 정규화된 티커 사용 (보유 시 SELL 평가가 돌도록)
                    if not self.has_wallet_position(self._norm_ticker(ticker)):
                        return
            except Exception:
                return

        state = self._current_state()
        if state["bar"] < getattr(self, "_boot_start_bar", 0):
            return
        
        sell_cond = self.conditions.get("sell", {})

        # =========================
        # 엔트리 하이드레이션:
        #  - 월렛/DB로 보유가 확인되었는데 entry_price가 None이면
        #    엔진이 넘겨준 훅(get_wallet_entry_price)으로 복구
        # =========================
        if self.entry_price is None:
            try:
                if hasattr(self, "get_wallet_entry_price") and callable(self.get_wallet_entry_price):
                    ep = self.get_wallet_entry_price(self._norm_ticker(ticker))
                    if ep is None:
                        ep = self.get_wallet_entry_price(ticker)
                    if ep is not None:
                        self.entry_price = float(ep)
                        # bars_held 계산을 위해 최소한의 entry_bar 세팅
                        if self.entry_bar is None:
                            self.entry_bar = state["bar"]
            except Exception:
                logger.debug(f"[SELL] entry hydrate skipped: {e}")

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
            # ✅ 진입 직후 ARM 가능: self.trailing_armed는 BUY 시점에 세팅됨
            ts_armed = bool(self.trailing_armed)
            # ✅ 최고가는 항상 갱신
            if (self.highest_price is None) or (state["price"] > self.highest_price):
                self.highest_price = state["price"]
            highest = self.highest_price
            trailing_limit = (highest * (1 - self.trailing_stop_pct)) if highest is not None else None
            ts_hit = (
                ts_armed
                and (trailing_limit is not None)
                and (bars_held >= self.min_holding_period)
                and (state["price"] <= trailing_limit + eps)
            )
        else:
            ts_armed, highest, trailing_limit, ts_hit = False, self.highest_price, None, False

        add("trailing_stop", ts_enabled, ts_hit, {
            "armed": ts_armed, "highest": highest, "limit": trailing_limit,
            "pct": getattr(self,"trailing_stop_pct", None),
            "bars_held": bars_held, "min_hold": self.min_holding_period
        })

        # Take Profit (TS 꺼져 있을 때만 즉시 매도)
        tp_enabled = sell_cond.get("take_profit", False)
        # tp_hit = (state["price"] >= tp_price - eps) and (not ts_enabled)
        tp_hit = (state["price"] >= tp_price - eps) and (TP_WITH_TS or (not ts_enabled))
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
        # ✅ bars_held는 해시에서 제외 (매 바 증가로 인한 과도한 적재 방지)
        sig = hashlib.md5(json.dumps({
            "armed": ts_armed,
            "highest": round((self.highest_price or 0.0), 6),
            "pass_map": {k:v["pass"] for k,v in checks.items() if v.get("enabled")==1}
        }, sort_keys=True, default=str).encode()).hexdigest()

        should_insert = (trigger_key is not None)
        if not should_insert:
            # 상태 변화시에만 적재, 그 외에는 샘플링 주기로만 적재
            if sig != self._last_sell_sig:
                should_insert = True
            elif self._sell_sample_n and (state["bar"] % self._sell_sample_n == 0):
                should_insert = True

        # --- SELL 감사 적재 직전 ---
        audit_key = (
            self.user_id,
            getattr(self, "ticker", "UNKNOWN"),
            getattr(self, "interval_sec", 60),
            state["bar"],
            sig,  # 상태 해시 사용(권장). 단순 바만 쓰려면 sig를 빼면 됨.
        )

        if audit_key in MACDStrategy._seen_sell_audits:
            should_insert = False  # 이미 같은 상태를 같은 바에서 기록했음 → 스킵
            
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
                MACDStrategy._seen_sell_audits.add(audit_key)
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
            if self.trailing_armed and (self.highest_price is not None):
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
        # ✅ 활성화된(ON) 조건이 하나도 없으면 매수 성공으로 보지 않는다.
        overall_ok = (len(enabled_keys) > 0) and (len(failed_keys)==0)

        return report, enabled_keys, failed_keys, overall_ok
