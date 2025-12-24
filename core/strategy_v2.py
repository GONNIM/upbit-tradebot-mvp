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
    TP_WITH_TS,
    DEFAULT_STRATEGY_TYPE,
)
import json
from pathlib import Path

# Audit
from services.db import insert_buy_eval, insert_sell_eval, insert_settings_snapshot, has_open_by_orders
from services.init_db import get_db_path

import inspect, os, math


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 공통 유틸
# ============================================================

def _get_strategy_tag(obj) -> str:
    """
    전략 타입 문자열을 가져온다.
    - Strategy 인스턴스에 strategy_type 속성이 있으면 그걸 사용
    - 없으면 DEFAULT_STRATEGY_TYPE (현재 MACD) 사용
    """
    try:
        st = getattr(obj, "strategy_type", None)
        if not st:
            return DEFAULT_STRATEGY_TYPE
        return str(st).upper().strip()
    except Exception:
        return DEFAULT_STRATEGY_TYPE


def _make_conditions_path(obj, uid: str) -> Path:
    """
    user_id + strategy_type + CONDITIONS_JSON_FILENAME 조합으로
    컨디션 파일 경로 생성.
    예: mcmax33_MACD_buy_sell_conditions.json
        mcmax33_EMA_buy_sell_conditions.json
    """
    st = _get_strategy_tag(obj)
    return Path(f"{uid}_{st}_{CONDITIONS_JSON_FILENAME}")


# ============================================================
# MACD Strategy
# ============================================================
class MACDStrategy(Strategy):
    fast_period = 12
    slow_period = 26
    signal_period = 9
    take_profit = 0.03
    stop_loss = 0.01
    macd_threshold = 0.0
    min_holding_period = 0  # 🕒 최소 보유 기간
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
        self._last_sell_audit_bar = None
        self._last_sell_audit_ts = None
        self._sell_sample_n = 60
        self._boot_start_bar = len(self.data) - 1
        self._boot_start_ts = self.data.index[-1]
        self._last_buy_sig = None      # BUY 상태 시그니처(변화 감지용)
        self._buy_sample_n = 60        # 샘플링 주기(원하면 0/None으로 끔)

        MACDStrategy.log_events = []
        MACDStrategy.trade_events = []

        # ✅ 전략 타입까지 반영된 컨디션 파일 경로
        uid = getattr(self, 'user_id', 'UNKNOWN')
        self._cond_path = _make_conditions_path(self, uid)
        self._cond_mtime = self._cond_path.stat().st_mtime if self._cond_path.exists() else None

        self.conditions = self._load_conditions()
        self._log_conditions()

        try:
            insert_settings_snapshot(
                user_id=self.user_id,
                ticker=getattr(self, "ticker", "UNKNOWN"),
                interval_sec=getattr(self, "interval_sec", 60),
                tp=self.take_profit, sl=self.stop_loss,
                ts_pct=getattr(self, "trailing_stop_pct", None),
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
        path = _make_conditions_path(self, uid)
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
                    [
                        "trailing_stop",
                        "take_profit",
                        "stop_loss",
                        "macd_negative",
                        "signal_negative",
                        "dead_cross"
                    ],
                    False,
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
    @staticmethod
    def _is_finite(x):
        try:
            return math.isfinite(float(x))
        except Exception:
            return False
    
    @staticmethod
    def _cross_delta(delta_prev: float, delta_now: float, *, eps_abs: float, eps_rel: float = 0.0) -> tuple[bool, bool]:
        """
        반환: (is_golden, is_dead)
        - eps_abs: 절대 EPS
        - eps_rel: 상대 EPS (스케일 보정용: 기준은 max(|delta_prev|, |delta_now|))
        """
        scale = max(abs(delta_prev), abs(delta_now), 1.0)
        eps = max(eps_abs, eps_rel * scale) # 적응형 EPS
        is_golden = (delta_prev <= +eps) and (delta_now > +eps)
        is_dead = (delta_prev >= -eps) and (delta_now < -eps)
        return is_golden, is_dead

    def _is_golden_cross(self):
        # --- 안정성 가드 ---
        if len(self.macd_line) < 2 or len(self.signal_line) < 2:
            return False
        macd_prev, sig_prev = self.macd_line[-2], self.signal_line[-2]
        macd_now, sig_now = self.macd_line[-1], self.signal_line[-1]
        if not (self._is_finite(macd_prev) and self._is_finite(sig_prev) and self._is_finite(macd_now) and self._is_finite(sig_now)):
            return False

        # --- Δ 기반 판단 + 적응형 EPS ---
        delta_prev = macd_prev - sig_prev
        delta_now = macd_now - sig_now
        is_golden, _ = self._cross_delta(delta_prev, delta_now, eps_abs=1e-10, eps_rel=1e-6)

        if not is_golden:
            return False
        
        # --- 의미 필터 ---
        # 최소 분리도(교차 후 충분히 떨어졌는가)
        sep_min_abs = 0.0
        sep_min_rel = 0.0
        if abs(delta_now) < max(sep_min_abs, sep_min_rel * max(abs(delta_prev), 1.0)):
            return False
        
        # 최소 기울기(변화량이 충분한가)
        slope_min = 0.0
        if abs(delta_now - delta_prev) < slope_min:
            return False
        
        # 디바운스: 마지막 교차로부터 N봉 이상
        N = 0
        if getattr(self, "bars_since_cross", None) is not None and self.bars_since_cross < N:
            return False
        
        return True

    def _is_dead_cross(self):
        # --- 안정성 가드 ---
        if len(self.macd_line) < 2 or len(self.signal_line) < 2:
            return False
        macd_prev, sig_prev = self.macd_line[-2], self.signal_line[-2]
        macd_now,  sig_now  = self.macd_line[-1],  self.signal_line[-1]
        if not (self._is_finite(macd_prev) and self._is_finite(sig_prev) and self._is_finite(macd_now) and self._is_finite(sig_now)):
            return False

        # --- Δ 기반 판단 + 적응형 EPS ---
        delta_prev = macd_prev - sig_prev
        delta_now = macd_now - sig_now
        _, is_dead = self._cross_delta(delta_prev, delta_now, eps_abs=1e-10, eps_rel=1e-6)

        # --- 의미 필터 ---
        # 최소 분리도(교차 후 충분히 떨어졌는가)
        sep_min_abs = 0.0
        sep_min_rel = 0.0
        if abs(delta_now) < max(sep_min_abs, sep_min_rel * max(abs(delta_prev), 1.0)):
            return False
        
        # 최소 기울기(변화량이 충분한가)
        slope_min = 0.0
        if abs(delta_now - delta_prev) < slope_min:
            return False
        
        # 디바운스: 마지막 교차로부터 N봉 이상
        N = 0
        if getattr(self, "bars_since_cross", None) is not None and self.bars_since_cross < N:
            return False
        
        return is_dead

    # -------------------
    # --- Candle & Trend
    # -------------------
    def _is_bullish_candle(self):
        return (self._is_finite(self.data.Close[-1]) and self._is_finite(self.data.Open[-1])
                and self.data.Close[-1] > self.data.Open[-1])

    def _is_macd_trending_up(self):
        if len(self.macd_line) < 3:
            return False
        a, b, c = self.macd_line[-3], self.macd_line[-2], self.macd_line[-1]
        if pd.isna(a) or pd.isna(b) or pd.isna(c):
            return False
        return a < b < c

    def _is_above_ma20(self):
        return (self._is_finite(self.data.Close[-1]) and self._is_finite(self.ma20[-1])
                and self.data.Close[-1] > self.ma20[-1])

    def _is_above_ma60(self):
        return (self._is_finite(self.data.Close[-1]) and self._is_finite(self.ma60[-1])
                and self.data.Close[-1] > self.ma60[-1])

    def _check_macd_pos(self, state, eps=1e-8) -> bool:
        return state["macd"] >= (self.macd_threshold - eps)

    def _is_macd_cross_up(self, thr: float, eps_abs: float = 1e-10, eps_rel: float = 1e-6) -> bool:
        """
        MACD가 thr(=self.macd_threshold)을 '아래→위'로 돌파했는지 감지.
        내부의 _cross_delta를 재사용하여 노이즈에 강하게 판정.
        """
        if len(self.macd_line) < 2:
            return False
        macd_prev = self.macd_line[-2]
        macd_now  = self.macd_line[-1]
        if not (self._is_finite(macd_prev) and self._is_finite(macd_now)):
            return False

        # thr에 대한 상대 위치를 델타로 보고 상향 크로스만 True
        delta_prev = macd_prev - thr
        delta_now  = macd_now  - thr
        is_up, _ = self._cross_delta(delta_prev, delta_now, eps_abs=eps_abs, eps_rel=eps_rel)
        return is_up

    def _is_macd_cross_down(self, thr: float, eps_abs: float = 1e-10, eps_rel: float = 1e-6) -> bool:
        if len(self.macd_line) < 2:
            return False
        macd_prev = self.macd_line[-2]
        macd_now  = self.macd_line[-1]
        if not (self._is_finite(macd_prev) and self._is_finite(macd_now)):
            return False
        delta_prev = macd_prev - thr
        delta_now  = macd_now  - thr
        _, is_down = self._cross_delta(delta_prev, delta_now, eps_abs=eps_abs, eps_rel=eps_rel)
        return is_down

    def _check_signal_pos(self, state, eps=1e-8) -> bool:
        return state["signal"] >= (self.macd_threshold - eps)
    
    def _is_signal_cross_up(self, thr: float, eps_abs: float = 1e-10, eps_rel: float = 1e-6) -> bool:
        """
        Signal 라인이 thr(=self.macd_threshold)을 '아래→위'로 돌파했는지 감지.
        _cross_delta 재사용으로 노이즈 억제.
        """
        if len(self.signal_line) < 2:
            return False
        sig_prev = self.signal_line[-2]
        sig_now  = self.signal_line[-1]
        if not (self._is_finite(sig_prev) and self._is_finite(sig_now)):
            return False

        delta_prev = sig_prev - thr
        delta_now  = sig_now  - thr
        is_up, _ = self._cross_delta(delta_prev, delta_now, eps_abs=eps_abs, eps_rel=eps_rel)
        return is_up

    def _is_signal_cross_down(self, thr: float, eps_abs: float = 1e-10, eps_rel: float = 1e-6) -> bool:
        """
        Signal 라인이 thr(=self.macd_threshold)을 '위→아래'로 돌파했는지 감지.
        _cross_delta 재사용으로 노이즈 억제.
        """
        if len(self.signal_line) < 2:
            return False
        sig_prev = self.signal_line[-2]
        sig_now  = self.signal_line[-1]
        if not (self._is_finite(sig_prev) and self._is_finite(sig_now)):
            return False

        delta_prev = sig_prev - thr
        delta_now  = sig_now  - thr
        _, is_down = self._cross_delta(delta_prev, delta_now, eps_abs=eps_abs, eps_rel=eps_rel)
        return is_down

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
        self.bars_since_cross = getattr(self, "bars_since_cross", 1_000_000) + 1

        self._reconcile_entry_with_wallet()
        self._maybe_reload_conditions()
        self._update_cross_state()
        self._evaluate_sell()
        self._evaluate_buy()

    def _update_cross_state(self):
        state = self._current_state()
        if self._is_golden_cross():
            self.bars_since_cross = 0
            self.golden_cross_pending = True
            self.last_cross_type = "Golden"
            # position_color = "🟢"
        elif self._is_dead_cross():
            self.bars_since_cross = 0
            self.golden_cross_pending = False
            self.last_cross_type = "Dead"
            # position_color = "🛑"
        elif self.golden_cross_pending:
            self.last_cross_type = "Pending"
            # position_color = "🔵"
        else:
            self.last_cross_type = "Neutral"
            # position_color = "⚪"

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
             lambda: self._is_macd_cross_up(self.macd_threshold)),
            ("signal_positive", buy_cond.get("signal_positive", False),
             lambda: self._is_signal_cross_up(self.macd_threshold)),
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
            ok = self._is_signal_cross_up(self.macd_threshold)
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
                                bar=state["bar"],
                                price=state["price"],
                                macd=state["macd"],
                                signal=state["signal"],
                                have_position=True,
                                overall_ok=False,
                                failed_keys=[],
                                checks={"note":"blocked_by_position"},
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
        ts = pd.Timestamp(state["timestamp"])

        if getattr(self, "_boot_start_ts", None) is not None:
            if ts < self._boot_start_ts:
                # logger.info(f"[BUY] SKIP (boot replay) ts={ts} < boot_ts={self._boot_start_ts}")
                return
            
        logger.info(f"[BUY] BOOT FILTER LIFTED at ts={ts} (boot_ts={self._boot_start_ts})")
        self._boot_start_ts = None
        
        buy_cond = self.conditions.get("buy", {})
        report, enabled_keys, failed_keys, overall_ok = self._buy_checks_report(state, buy_cond)

        # BUY 조건이 하나도 켜져 있지 않으면 감사기록 자체를 생략 (노이즈 컷)
        if len(enabled_keys) == 0:
            return

        # ✅ 프로세스 내 동일 바 dedup
        # key = (self.user_id, ticker, getattr(self,"interval_sec",60), state["bar"])
        key = (self.user_id, ticker, getattr(self,"interval_sec",60), str(state["timestamp"]))
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
        # if AUDIT_DEDUP_PER_BAR and self._last_buy_audit_bar == state["bar"]:
        if AUDIT_DEDUP_PER_BAR and getattr(self, "_last_buy_audit_ts", None) == str(state["timestamp"]):
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
                    self._last_buy_audit_ts = str(state["timestamp"])
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
        # ✅ 수정: TP 달성 전까지는 TS 비활성화 (TP 도달 시 armed)
        self.trailing_armed = False
        self.golden_cross_pending = False

        reason_str = "+".join(reasons) if reasons else "BUY"
        self._emit_trade("BUY", state, reason=reason_str)
        self._last_buy_bar = state["bar"]

    def _evaluate_sell(self):
        ticker = getattr(self, "ticker", "UNKNOWN")

         # ★ 디버깅: 현재 상태 로깅
        logger.info(f"[SELL-DEBUG] ========== SELL EVALUATION START ==========")
        logger.info(f"[SELL-DEBUG] ticker={ticker}")
        logger.info(f"[SELL-DEBUG] self.position={getattr(self, 'position', None)}")
        logger.info(f"[SELL-DEBUG] self.entry_price={getattr(self, 'entry_price', None)}")
        logger.info(f"[SELL-DEBUG] self.entry_bar={getattr(self, 'entry_bar', None)}")

        # ★ 백테스트 포지션과 지갑 포지션을 모두 확인
        has_bt_position = bool(getattr(getattr(self, "position", None), "size", 0) > 0)
        has_wallet_pos = False

        try:
            if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
                has_wallet_pos = bool(self.has_wallet_position(self._norm_ticker(ticker)))
                logger.info(f"[SELL] wallet check: {has_wallet_pos}")
        except Exception as e:
            logger.warning(f"[SELL] wallet check failed: {e}")
            has_wallet_pos = False

        logger.info(f"[SELL] ENTRY CHECK | has_bt_position={has_bt_position}, has_wallet_pos={has_wallet_pos}")

        # ★ 둘 다 없을 때만 스킵 (OR 조건)
        if not has_bt_position and not has_wallet_pos:
            logger.info("[SELL] SKIP: no position in both BT and wallet")
            return

        # ★ 백테스트나 지갑 중 하나라도 보유 중이면 SELL 평가 진행
        logger.info("[SELL] PROCEED: position detected")

        state = self._current_state()
        if state["bar"] < getattr(self, "_boot_start_bar", 0):
            return
        
        bar_ts = str(state["timestamp"])
        
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
                        if self.entry_bar is None:
                            self.entry_bar = state["bar"]
                        logger.info(f"[SELL] ✅ entry_price recovered from wallet: {self.entry_price}")
            except Exception as e:
                logger.warning(f"[SELL] ⚠️ entry hydrate failed: {e}")

        # ★ 복구 실패 시 대체 로직 (CRITICAL FIX)
        if self.entry_price is None:
            logger.warning(f"[SELL] ⚠️ entry_price is None after recovery attempt")

            # 옵션 1: 현재가를 entry_price로 설정 (보수적)
            # 주의: TP/SL 계산이 부정확하므로 전략 기반 매도만 허용
            self.entry_price = state["price"]
            self.entry_bar = state["bar"]
            logger.warning(f"[SELL] 🔧 FALLBACK: entry_price set to current price: {self.entry_price}")

            # 옵션 2: TP/SL 없이 전략 기반 매도만 허용 (더 보수적)
            # logger.info("[SELL] Proceeding with strategy-based SELL only (no TP/SL)")
            # (이 경우 TP/SL 체크 부분을 건너뛰도록 아래 로직 수정 필요)

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

        # ✅ 수정: Take Profit 먼저 체크 (TS armed 트리거용)
        tp_enabled = sell_cond.get("take_profit", False)
        tp_reached = (state["price"] >= tp_price - eps)
        ts_enabled = sell_cond.get("trailing_stop", False)

        # TP 도달 시 TS armed 활성화 (TS가 ON일 때만)
        if tp_enabled and tp_reached and ts_enabled:
            if not self.trailing_armed:
                self.trailing_armed = True
                self.highest_price = state["price"]  # TP 도달 시점부터 최고가 추적 시작
                logger.info(f"🎯 TP 도달 → TS ARMED | tp_price={tp_price:.2f} current={state['price']:.2f}")

        # TP 매도 조건: TS가 OFF이거나 TP_WITH_TS=True일 때만 즉시 매도
        tp_hit = tp_reached and (TP_WITH_TS or (not ts_enabled))
        add("take_profit", tp_enabled, tp_hit, {
            "price": state["price"],
            "tp_price": tp_price,
            "ts_enabled": ts_enabled,
            "tp_reached": tp_reached,
            "will_sell": tp_hit
        })

        # Trailing Stop (TP 도달 후 armed 상태에서만 작동)
        if ts_enabled:
            ts_armed = bool(self.trailing_armed)

            # ✅ armed 상태일 때만 최고가 갱신
            if ts_armed:
                if (self.highest_price is None) or (state["price"] > self.highest_price):
                    self.highest_price = state["price"]

            highest = self.highest_price

            # ✅ TP 가격 보호: trailing_limit의 최소값을 TP 가격으로 설정
            if highest is not None:
                raw_limit = highest * (1 - self.trailing_stop_pct)
                trailing_limit = max(tp_price, raw_limit)  # TP 이상 보장
            else:
                trailing_limit = None

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

        # MACD Negative
        macdneg_enabled = sell_cond.get("macd_negative", False)
        macdneg_hit = self._is_macd_cross_down(self.macd_threshold)
        add("macd_negative", macdneg_enabled, macdneg_hit, {"macd":state["macd"], "thr":self.macd_threshold})

        # Signal Negative
        signalneg_enabled = sell_cond.get("signal_negative", False)
        signalneg_hit = self._is_signal_cross_down(self.macd_threshold)
        add("signal_negative", signalneg_enabled, signalneg_hit, {"signal":state["signal"], "thr":self.macd_threshold})

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
        elif signalneg_enabled and signalneg_hit:
            trigger_key = "Signal Negative"
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

        # ★ "매 바 1회" 강제 — 새 바가 열렸다면 최소 1회는 기록
        #   - 디버깅/모니터링 단계에서 SELL 평가가 '안 올라오는 것처럼' 보이는 현상 해소
        #   - 이전에 기록한 bar와 현재 bar가 다르면 이번 bar에서 1회 적재 허용
        if not should_insert:
            if getattr(self, "_last_sell_audit_ts", None) != bar_ts:
                should_insert = True

        # --- SELL 감사 적재 직전 ---
        audit_key = (
            self.user_id,
            getattr(self, "ticker", "UNKNOWN"),
            getattr(self, "interval_sec", 60),
            bar_ts,
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
                self._last_sell_audit_ts = bar_ts
                logger.info(f"[AUDIT-SELL] inserted | uid={getattr(self,'user_id',None)} ts={bar_ts} trigger={trigger_key}")
            except Exception as e:
                logger.error(f"[AUDIT-SELL] insert failed: {e} | uid={getattr(self,'user_id',None)} ts={bar_ts} checks_keys={list(checks.keys())}")

        # Stop Loss
        if sl_enabled and sl_hit:
            logger.info("🛑 SL HIT → SELL")
            self._sell_action(state, "Stop Loss")
            return

        # Trailing Stop (armed 상태일 때만 작동)
        if ts_enabled and self.trailing_armed:
            if self.highest_price is not None:
                # ✅ TP 가격 보호
                raw_limit = self.highest_price * (1 - self.trailing_stop_pct)
                trailing_limit = max(tp_price, raw_limit)
                logger.info(
                    f"🔧 TS CHECK | armed=True price={state['price']:.2f} high={self.highest_price:.2f} "
                    f"limit={trailing_limit:.2f} (raw={raw_limit:.2f}, tp={tp_price:.2f}) pct={self.trailing_stop_pct:.3f}"
                )
                if bars_held >= self.min_holding_period and state["price"] <= trailing_limit + eps:
                    logger.info("🛑 TS HIT → SELL")
                    self._sell_action(state, "Trailing Stop")
                    return

        # Take Profit (TS가 OFF이거나 TP_WITH_TS=True일 때만 즉시 매도)
        if tp_enabled and tp_hit:
            logger.info("💰 TP HIT (TS OFF or TP_WITH_TS=True) → SELL")
            self._sell_action(state, "Take Profit")
            return

        # MACD Negative
        if macdneg_enabled and macdneg_hit:
            logger.info("📉 MACD < threshold → SELL")
            self._sell_action(state, "MACD Negative")
            return
        
        # Signal Negative
        if signalneg_enabled and signalneg_hit:
            logger.info("📉 Signal < threshold → SELL")
            self._sell_action(state, "Signal Negative")
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
        macd_pos_cross = self._is_macd_cross_up(self.macd_threshold)
        signal_pos_cross = self._is_signal_cross_up(self.macd_threshold)
        bull = self._is_bullish_candle()
        trending = self._is_macd_trending_up()
        above20 = self._is_above_ma20()
        above60 = self._is_above_ma60()

        add("golden_cross",     buy_cond.get("golden_cross", False),        golden,             {"macd":state["macd"], "signal":state["signal"]})
        add("macd_positive",    buy_cond.get("macd_positive", False),       macd_pos_cross,     {"macd":state["macd"], "thr":self.macd_threshold})
        add("signal_positive",  buy_cond.get("signal_positive", False),     signal_pos_cross,   {"signal":state["signal"], "thr":self.macd_threshold})
        add("bullish_candle",   buy_cond.get("bullish_candle", False),      bull,               {"open":float(self.data.Open[-1]), "close":state["price"]})
        add("macd_trending_up", buy_cond.get("macd_trending_up", False),    trending,           None)
        add("above_ma20",       buy_cond.get("above_ma20", False),          above20,            {"ma20": float(self.ma20[-1])})
        add("above_ma60",       buy_cond.get("above_ma60", False),          above60,            {"ma60": float(self.ma60[-1])})

        if self.signal_confirm_enabled:
            gate_ok = self._is_signal_cross_up(self.macd_threshold)
            report["signal_confirm"] = {"enabled":1, "pass": 1 if gate_ok else 0, "value":{"signal":state["signal"], "thr":self.macd_threshold}}

        enabled_keys = [k for k,v in report.items() if v["enabled"]==1]
        failed_keys  = [k for k in enabled_keys if report[k]["pass"]==0]
        # ✅ 활성화된(ON) 조건이 하나도 없으면 매수 성공으로 보지 않는다.
        overall_ok = (len(enabled_keys) > 0) and (len(failed_keys)==0)

        return report, enabled_keys, failed_keys, overall_ok


# ============================================================
# EMA Strategy (간단 버전)
#  - 핵심: 단기/장기 EMA GC/DC + 기준 EMA 위/아래
#  - Audit/게이트 로직은 MACDStrategy 흐름을 최대한 재사용
# ============================================================
class EMAStrategy(Strategy):
    # 기본 파라미터 (필요 시 LiveParams에서 override)
    fast_period = 20
    slow_period = 200
    base_period = 200

    take_profit = 0.03
    stop_loss = 0.01
    min_holding_period = 5
    volatility_window = 20

    ignore_db_gate = False
    ignore_wallet_gate = False

    _seen_buy_audits = set()
    _seen_sell_audits = set()

    @staticmethod
    def _norm_ticker(ticker: str) -> str:
        try:
            return (ticker or "").split("-")[-1].strip().upper()
        except Exception:
            return ticker

    def _calculate_ma(self, series, period: int, ma_type: str):
        """
        이동평균 계산 통합 함수

        Args:
            series: 가격 데이터 (Close)
            period: 기간
            ma_type: "SMA" | "EMA" | "WMA"

        Returns:
            numpy array
        """
        import numpy as np
        s = pd.Series(series)

        if ma_type == "SMA":
            # ✅ 단순이동평균 (Simple Moving Average)
            # 공식: (P₁ + P₂ + ... + Pₙ) / n
            return s.rolling(window=period).mean().values

        elif ma_type == "EMA":
            # ✅ 지수이동평균 (Exponential Moving Average)
            # 공식: EMA(t) = α × P(t) + (1-α) × EMA(t-1)
            # where α = 2 / (period + 1)
            return s.ewm(span=period, adjust=False).mean().values

        elif ma_type == "WMA":
            # ✅ 가중이동평균 (Weighted Moving Average)
            # 공식: WMA = (n×P₁ + (n-1)×P₂ + ... + 1×Pₙ) / (n×(n+1)/2)
            def wma(x):
                if len(x) < period:
                    return np.nan
                weights = np.arange(1, period + 1)
                return np.dot(x[-period:], weights) / weights.sum()

            return s.rolling(window=period).apply(wma, raw=True).values

        else:
            # 폴백: SMA
            logger.warning(f"[EMA] Unknown ma_type={ma_type}, fallback to SMA")
            return s.rolling(window=period).mean().values

    def init(self):
        logger.info("EMAStrategy init")
        logger.info(f"[BOOT] strategy_file={os.path.abspath(inspect.getfile(self.__class__))}")
        logger.info(f"[BOOT] __name__={__name__} __package__={__package__}")

        close = self.data.Close

        # ========== 이동평균 계산 방식 결정 ==========
        ma_type = getattr(self, "ma_type", "SMA").upper()
        logger.info(f"[EMA] 이동평균 계산 방식: {ma_type}")
        # ✅ 차트 일치 검증 로그 추가
        logger.info(
            f"[EMA-CHART-SYNC] 전략={ma_type} | "
            f"차트도 동일하게 표시되어야 함 (dashboard.py 확인)"
        )

        # ========== EMA 파라미터 결정 ==========
        use_separate = getattr(self, "use_separate_ema", False)

        if use_separate:
            # 별도 설정 모드: 매수용/매도용 EMA 파라미터 분리
            fast_buy  = getattr(self, "fast_buy", None) or self.fast_period
            slow_buy  = getattr(self, "slow_buy", None) or self.slow_period
            fast_sell = getattr(self, "fast_sell", None) or self.fast_period
            slow_sell = getattr(self, "slow_sell", None) or self.slow_period

            logger.info(f"[EMA] 매수/매도 별도 EMA 사용")
            logger.info(f"[EMA] 매수: Fast={fast_buy}, Slow={slow_buy}")
            logger.info(f"[EMA] 매도: Fast={fast_sell}, Slow={slow_sell}")
        else:
            # 공통 설정 모드 (기존): 매수/매도 모두 동일한 EMA 사용
            fast_buy = fast_sell = self.fast_period
            slow_buy = slow_sell = self.slow_period

            logger.info(f"[EMA] 매수/매도 공통 EMA 사용: Fast={fast_buy}, Slow={slow_buy}")

        # ========== 이동평균 지표 계산 ==========
        # 매수용 MA
        self.ema_fast_buy = self.I(
            lambda s: self._calculate_ma(s, fast_buy, ma_type),
            close
        )
        self.ema_slow_buy = self.I(
            lambda s: self._calculate_ma(s, slow_buy, ma_type),
            close
        )

        # 매도용 MA
        self.ema_fast_sell = self.I(
            lambda s: self._calculate_ma(s, fast_sell, ma_type),
            close
        )
        self.ema_slow_sell = self.I(
            lambda s: self._calculate_ma(s, slow_sell, ma_type),
            close
        )

        # 기준 MA
        self.ema_base = self.I(
            lambda s: self._calculate_ma(s, self.base_period, ma_type),
            close
        )

        # 기존 지표 유지 (호환성)
        # ema_fast/ema_slow는 매도용으로 aliasing (차트 표시 등 기존 코드 호환성 유지)
        self.ema_fast = self.ema_fast_sell
        self.ema_slow = self.ema_slow_sell

        self.volatility = self.I(
            lambda h, l: pd.Series(h - l).rolling(self.volatility_window).mean().values,
            self.data.High, self.data.Low
        )

        self.entry_price = None
        self.entry_bar = None
        self.highest_price = None
        self.trailing_armed = False
        self._last_cross_type = None
        self._last_sell_bar = None
        self.trailing_stop_pct = TRAILING_STOP_PERCENT

        self._last_buy_audit_ts = None
        self._last_sell_audit_ts = None
        self._sell_sample_n = 60
        self._buy_sample_n = 60
        self._last_buy_sig = None
        self._last_sell_sig = None
        self._boot_start_bar = len(self.data) - 1
        self._boot_start_ts = self.data.index[-1]

        EMAStrategy.log_events = []
        EMAStrategy.trade_events = []

        uid = getattr(self, "user_id", "UNKNOWN")
        self._cond_path = _make_conditions_path(self, uid)
        self._cond_mtime = self._cond_path.stat().st_mtime if self._cond_path.exists() else None

        self.conditions = self._load_conditions()
        self._log_conditions()

        try:
            insert_settings_snapshot(
                user_id=self.user_id,
                ticker=getattr(self, "ticker", "UNKNOWN"),
                interval_sec=getattr(self, "interval_sec", 60),
                tp=self.take_profit, sl=self.stop_loss,
                ts_pct=getattr(self, "trailing_stop_pct", None),
                signal_gate=False,
                threshold=0.0,
                buy_dict=self.conditions.get("buy", {}),
                sell_dict=self.conditions.get("sell", {})
            )
        except Exception as e:
            logger.warning(f"[AUDIT][EMA] settings snapshot failed (ignored): {e}")

    def _maybe_reload_conditions(self):
        try:
            if self._cond_path and self._cond_path.exists():
                mtime = self._cond_path.stat().st_mtime
                if self._cond_mtime != mtime:
                    with self._cond_path.open("r", encoding="utf-8") as f:
                        self.conditions = json.load(f)
                    self._cond_mtime = mtime
                    logger.info(f"[EMA] 🔄 Condition reloaded: {self._cond_path}")
                    self._log_conditions()
        except Exception as e:
            logger.warning(f"[EMA] ⚠️ Condition hot-reload failed (ignored): {e}")

    def _load_conditions(self):
        uid = getattr(self, 'user_id', 'UNKNOWN')
        path = _make_conditions_path(self, uid)
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                conditions = json.load(f)
                logger.info(f"[EMA] 📂 Condition 파일 로드 완료: {path}")
                return conditions
        else:
            logger.warning(f"[EMA] ⚠️ Condition 파일 없음. 기본값 사용: {path}")
            return {
                "buy": dict.fromkeys(
                    [
                        "ema_gc",          # 단기/장기 EMA 골든크로스
                        "above_base_ema",  # 기준 EMA(200) 위
                        "bullish_candle",  # 양봉 필터
                    ],
                    False,
                ),
                "sell": dict.fromkeys(
                    [
                        "ema_dc",          # 단기/장기 EMA 데드크로스
                        "take_profit",
                        "stop_loss",
                        "trailing_stop",
                    ],
                    False,
                ),
            }

    def _log_conditions(self):
        logger.info("[EMA] 📋 매수/매도 전략 Condition 상태:")
        for key, conds in self.conditions.items():
            for cond, value in conds.items():
                status = "✅ ON" if value else "❌ OFF"
                logger.info(f"[EMA]  - {key}.{cond}: {status}")

    # -------------------
    # 상태 / 크로스
    # -------------------
    @staticmethod
    def _is_finite(x):
        try:
            return math.isfinite(float(x))
        except Exception:
            return False

    @staticmethod
    def _cross_delta(delta_prev: float, delta_now: float, *, eps_abs: float, eps_rel: float = 0.0) -> tuple[bool, bool]:
        scale = max(abs(delta_prev), abs(delta_now), 1.0)
        eps = max(eps_abs, eps_rel * scale)
        is_golden = (delta_prev <= +eps) and (delta_now > +eps)
        is_dead = (delta_prev >= -eps) and (delta_now < -eps)
        return is_golden, is_dead

    def _current_state(self):
        """현재 상태 반환 (로그/디버깅용)"""
        idx = len(self.data) - 1
        return {
            "bar": idx,
            "price": float(self.data.Close[-1]),
            # 매수용 EMA
            "ema_fast_buy": float(self.ema_fast_buy[-1]),
            "ema_slow_buy": float(self.ema_slow_buy[-1]),
            # 매도용 EMA
            "ema_fast_sell": float(self.ema_fast_sell[-1]),
            "ema_slow_sell": float(self.ema_slow_sell[-1]),
            # 기준 EMA 및 기타
            "ema_base": float(self.ema_base[-1]),
            "volatility": float(self.volatility[-1]),
            "timestamp": self.data.index[-1],
            # 기존 호환성을 위해 ema_fast/ema_slow도 포함 (매도용과 동일)
            "ema_fast": float(self.ema_fast[-1]),
            "ema_slow": float(self.ema_slow[-1]),
        }

    def _is_bullish_candle(self):
        return (self._is_finite(self.data.Close[-1]) and self._is_finite(self.data.Open[-1])
                and self.data.Close[-1] > self.data.Open[-1])

    def _is_ema_gc(self):
        """매수용 EMA로 골든크로스 판단"""
        if len(self.ema_fast_buy) < 2 or len(self.ema_slow_buy) < 2:
            return False
        # 이전 봉
        pf, ps = self.ema_fast_buy[-2], self.ema_slow_buy[-2]
        # 현재 봉
        cf, cs = self.ema_fast_buy[-1], self.ema_slow_buy[-1]
        if not (self._is_finite(pf) and self._is_finite(ps) and self._is_finite(cf) and self._is_finite(cs)):
            return False
        delta_prev = pf - ps
        delta_now  = cf - cs
        is_golden, _ = self._cross_delta(delta_prev, delta_now, eps_abs=1e-10, eps_rel=1e-6)
        return is_golden

    def _is_ema_dc(self):
        """매도용 EMA로 데드크로스 판단"""
        if len(self.ema_fast_sell) < 2 or len(self.ema_slow_sell) < 2:
            return False
        # 이전 봉
        pf, ps = self.ema_fast_sell[-2], self.ema_slow_sell[-2]
        # 현재 봉
        cf, cs = self.ema_fast_sell[-1], self.ema_slow_sell[-1]
        if not (self._is_finite(pf) and self._is_finite(ps) and self._is_finite(cf) and self._is_finite(cs)):
            return False
        delta_prev = pf - ps
        delta_now  = cf - cs
        _, is_dead = self._cross_delta(delta_prev, delta_now, eps_abs=1e-10, eps_rel=1e-6)
        return is_dead

    def _is_above_base_ema(self):
        return self._is_finite(self.data.Close[-1]) and self._is_finite(self.ema_base[-1]) and self.data.Close[-1] > self.ema_base[-1]

    def _reconcile_entry_with_wallet(self):
        try:
            sz = getattr(getattr(self, "position", None), "size", 0) or 0
            if sz == 0 and self.entry_price is not None:
                has_wallet_pos = None
                if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
                    has_wallet_pos = bool(self.has_wallet_position(self._norm_ticker(self.ticker)))
                if has_wallet_pos is None or has_wallet_pos is False:
                    logger.warning("[EMA] 🧹 고아 엔트리 정리: 포지션/지갑에 보유 없음 → entry 리셋")
                    self._reset_entry()
        except Exception as e:
            logger.debug(f"[EMA][reconcile] skip ({e})")

    # -------------------
    # MAIN LOOP
    # -------------------
    def next(self):
        self._reconcile_entry_with_wallet()
        self._maybe_reload_conditions()
        self._update_cross_state()
        self._evaluate_sell()
        self._evaluate_buy()

    def _update_cross_state(self):
        state = self._current_state()
        if self._is_ema_gc():
            self._last_cross_type = "Golden"
        elif self._is_ema_dc():
            self._last_cross_type = "Dead"
        else:
            self._last_cross_type = "Neutral"

        # ✅ EMA 확장 포맷: 매수/매도/기준 EMA 모두 포함
        EMAStrategy.log_events.append(
            (
                state["bar"],
                "LOG",
                self._last_cross_type,
                state["ema_fast_buy"],   # 매수용 Fast EMA
                state["ema_slow_buy"],   # 매수용 Slow EMA
                state["ema_fast_sell"],  # 매도용 Fast EMA
                state["ema_slow_sell"],  # 매도용 Slow EMA
                state["ema_base"],       # 기준 EMA
                state["price"],
            )
        )

    def _is_flat_by_history(self) -> bool | None:
        try:
            if not hasattr(self, "fetch_orders") or not callable(self.fetch_orders):
                return None
            orders = self.fetch_orders(self.user_id, getattr(self, "ticker", "UNKNOWN"), limit=100) or []
            if not isinstance(orders, list):
                return None
            if len(orders) == 0:
                return True

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
            return True
        except Exception as e:
            logger.debug(f"[EMA][HIST] flat-by-history check skipped: {e}")
            return None

    # -------------------
    # BUY
    # -------------------
    def _buy_checks_report(self, state, buy_cond):
        report = {}

        def add(name, enabled, passed, raw=None):
            report[name] = {"enabled": 1 if enabled else 0, "pass": 1 if passed else 0, "value": raw}

        gc = self._is_ema_gc()
        above = self._is_above_base_ema()
        bull = self._is_bullish_candle()

        add("ema_gc",         buy_cond.get("ema_gc", False),         gc,    {"ema_fast_buy": state["ema_fast_buy"], "ema_slow_buy": state["ema_slow_buy"]})
        add("above_base_ema", buy_cond.get("above_base_ema", False), above, {"price": state["price"], "ema_base": state["ema_base"]})
        add("bullish_candle", buy_cond.get("bullish_candle", False), bull,  {"open": float(self.data.Open[-1]), "close": state["price"]})

        enabled_keys = [k for k, v in report.items() if v["enabled"] == 1]
        failed_keys  = [k for k in enabled_keys if report[k]["pass"] == 0]
        overall_ok = (len(enabled_keys) > 0) and (len(failed_keys) == 0)
        return report, enabled_keys, failed_keys, overall_ok

    def _evaluate_buy(self):
        ticker = getattr(self, "ticker", "UNKNOWN")
        inpos = bool(getattr(getattr(self, "position", None), "size", 0) > 0)

        try:
            db_open = has_open_by_orders(self.user_id, ticker)
        except Exception as e:
            logger.error(f"[EMA][BUY-GATE] has_open_by_orders 실패: {e}")
            db_open = False

        wallet_open = None
        if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
            try:
                wallet_open = bool(self.has_wallet_position(self._norm_ticker(ticker)))
            except Exception:
                wallet_open = None      

        blocked = inpos or (False if self.ignore_wallet_gate else bool(wallet_open)) or (False if self.ignore_db_gate else bool(db_open))

        state = self._current_state()

        if (not blocked) and (getattr(self, "entry_price", None) is not None) and (not inpos):
            self._reset_entry()
            logger.info("[EMA] 🧹 고아 엔트리 정리: 엔진은 미보유 → entry 리셋")

        if blocked:
            if AUDIT_LOG_SKIP_POS:
                if not (AUDIT_DEDUP_PER_BAR and getattr(self, "_last_skippos_audit_bar", None) == state["bar"]):
                    if (AUDIT_SKIP_POS_SAMPLE_N is None) or (AUDIT_SKIP_POS_SAMPLE_N <= 0) or (state["bar"] % AUDIT_SKIP_POS_SAMPLE_N == 0):
                        try:
                            insert_buy_eval(
                                user_id=self.user_id,
                                ticker=ticker,
                                interval_sec=getattr(self, "interval_sec", 60),
                                bar=state["bar"],
                                price=state["price"],
                                macd=state["ema_fast_buy"],   # 매수용 EMA fast
                                signal=state["ema_slow_buy"],  # 매수용 EMA slow
                                have_position=True,
                                overall_ok=False,
                                failed_keys=[],
                                checks={"note": "blocked_by_position"},
                                notes="[EMA] BUY_SKIP_POS" + f" | ts_bt={state['timestamp']} bar_bt={state['bar']}"
                            )
                            self._last_skippos_audit_bar = state["bar"]
                        except Exception as e:
                            logger.error(f"[EMA][AUDIT-BUY] insert failed(SKIP_POS): {e} | bar={state['bar']}")
            logger.debug(f"[EMA][BUY] SKIP (보유 차단) | bar={state['bar']} price={state['price']:.6f}")
            return

        state = self._current_state()
        ts = pd.Timestamp(state["timestamp"])

        if getattr(self, "_boot_start_ts", None) is not None:
            if ts < self._boot_start_ts:
                return
            
        logger.info(f"[EMA][BUY] BOOT FILTER LIFTED at ts={ts} (boot_ts={self._boot_start_ts})")
        self._boot_start_ts = None
        
        buy_cond = self.conditions.get("buy", {})
        report, enabled_keys, failed_keys, overall_ok = self._buy_checks_report(state, buy_cond)

        if len(enabled_keys) == 0:
            return

        key = (self.user_id, ticker, getattr(self, "interval_sec", 60), str(state["timestamp"]))
        if key in EMAStrategy._seen_buy_audits:
            return
        
        import hashlib
        pass_map = {k: 1 if report.get(k, {}).get("pass", 0) == 1 else 0 for k in enabled_keys}
        buy_sig = hashlib.md5(json.dumps({
            "pass_map": pass_map,
            "cross": self._last_cross_type,
        }, sort_keys=True, default=str).encode()).hexdigest()

        should_insert = False
        if (self._last_buy_sig is None) or (buy_sig != self._last_buy_sig):
            should_insert = True
        elif self._buy_sample_n and (state["bar"] % self._buy_sample_n == 0):
            should_insert = True

        if AUDIT_DEDUP_PER_BAR and getattr(self, "_last_buy_audit_ts", None) == str(state["timestamp"]):
            logger.info(f"[EMA][AUDIT-BUY] DUP SKIP | bar={state['bar']}")
        else:
            if should_insert:
                try:
                    insert_buy_eval(
                        user_id=self.user_id,
                        ticker=ticker,
                        interval_sec=getattr(self, "interval_sec", 60),
                        bar=state["bar"],
                        price=state["price"],
                        macd=state["ema_fast_buy"],   # 매수용 EMA fast
                        signal=state["ema_slow_buy"],  # 매수용 EMA slow
                        have_position=False,
                        overall_ok=overall_ok,
                        failed_keys=failed_keys,
                        checks=report,
                        notes="[EMA] " + ("OK" if overall_ok else "FAILED") + f" | ts_bt={state['timestamp']} bar_bt={state['bar']}"
                    )
                    EMAStrategy._seen_buy_audits.add(key)
                    self._last_buy_audit_ts = str(state["timestamp"])
                    self._last_buy_sig = buy_sig
                except Exception as e:
                    logger.error(f"[EMA][AUDIT-BUY] insert failed: {e} | bar={state['bar']}")

        if not overall_ok:
            return

        reasons = [k for k in enabled_keys if report[k]["pass"] == 1]
        self._buy_action(state, reasons=reasons, details=report)

    def _buy_action(self, state, reasons, details=None):
        if getattr(self, "_last_buy_bar", None) == state["bar"]:
            logger.info(f"[EMA] ⏹️ DUPLICATE BUY SKIP | bar={state['bar']} reasons={' + '.join(reasons) if reasons else ''}")
            return

        self.buy()

        self.entry_price = state["price"]
        self.entry_bar = state["bar"]
        self.highest_price = self.entry_price
        # ✅ 수정: TP 달성 전까지는 TS 비활성화 (TP 도달 시 armed)
        self.trailing_armed = False

        reason_str = "+".join(reasons) if reasons else "BUY"
        self._emit_trade("BUY", state, reason=reason_str)
        self._last_buy_bar = state["bar"]

    # -------------------
    # SELL
    # -------------------
    def _evaluate_sell(self):
        ticker = getattr(self, "ticker", "UNKNOWN")

         # ★ 디버깅: 현재 상태 로깅
        logger.info(f"[SELL-DEBUG] ========== SELL EVALUATION START ==========")
        logger.info(f"[SELL-DEBUG] ticker={ticker}")
        logger.info(f"[SELL-DEBUG] self.position={getattr(self, 'position', None)}")
        logger.info(f"[SELL-DEBUG] self.entry_price={getattr(self, 'entry_price', None)}")
        logger.info(f"[SELL-DEBUG] self.entry_bar={getattr(self, 'entry_bar', None)}")

        # ★ 백테스트 포지션과 지갑 포지션을 모두 확인
        has_bt_position = bool(getattr(getattr(self, "position", None), "size", 0) > 0)
        has_wallet_pos = False

        try:
            if hasattr(self, "has_wallet_position") and callable(self.has_wallet_position):
                has_wallet_pos = bool(self.has_wallet_position(self._norm_ticker(ticker)))
                logger.info(f"[SELL] wallet check: {has_wallet_pos}")
        except Exception as e:
            logger.warning(f"[SELL] wallet check failed: {e}")
            has_wallet_pos = False

        logger.info(f"[SELL] ENTRY CHECK | has_bt_position={has_bt_position}, has_wallet_pos={has_wallet_pos}")

        # ★ 둘 다 없을 때만 스킵 (OR 조건)
        if not has_bt_position and not has_wallet_pos:
            logger.info("[SELL] SKIP: no position in both BT and wallet")
            return

        # ★ 백테스트나 지갑 중 하나라도 보유 중이면 SELL 평가 진행
        logger.info("[SELL] PROCEED: position detected")

        state = self._current_state()
        if state["bar"] < getattr(self, "_boot_start_bar", 0):
            return
        
        bar_ts = str(state["timestamp"])
        sell_cond = self.conditions.get("sell", {})

        if self.entry_price is None:
            try:
                if hasattr(self, "get_wallet_entry_price") and callable(self.get_wallet_entry_price):
                    ep = self.get_wallet_entry_price(self._norm_ticker(ticker))
                    if ep is None:
                        ep = self.get_wallet_entry_price(ticker)
                    if ep is not None:
                        self.entry_price = float(ep)
                        if self.entry_bar is None:
                            self.entry_bar = state["bar"]
                        logger.info(f"[SELL] ✅ entry_price recovered from wallet: {self.entry_price}")
            except Exception as e:
                logger.warning(f"[SELL] ⚠️ entry hydrate failed: {e}")

        # ★ 복구 실패 시 대체 로직 (CRITICAL FIX)
        if self.entry_price is None:
            logger.warning(f"[SELL] ⚠️ entry_price is None after recovery attempt")

            # 옵션 1: 현재가를 entry_price로 설정 (보수적)
            # 주의: TP/SL 계산이 부정확하므로 전략 기반 매도만 허용
            self.entry_price = state["price"]
            self.entry_bar = state["bar"]
            logger.warning(f"[SELL] 🔧 FALLBACK: entry_price set to current price: {self.entry_price}")

            # 옵션 2: TP/SL 없이 전략 기반 매도만 허용 (더 보수적)
            # logger.info("[SELL] Proceeding with strategy-based SELL only (no TP/SL)")
            # (이 경우 TP/SL 체크 부분을 건너뛰도록 아래 로직 수정 필요)

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
        add("stop_loss", sl_enabled, sl_hit, {"price": state["price"], "sl_price": sl_price})

        # ✅ 수정: Take Profit 먼저 체크 (TS armed 트리거용)
        tp_enabled = sell_cond.get("take_profit", False)
        tp_reached = (state["price"] >= tp_price - eps)
        ts_enabled = sell_cond.get("trailing_stop", False)

        # TP 도달 시 TS armed 활성화 (TS가 ON일 때만)
        if tp_enabled and tp_reached and ts_enabled:
            if not self.trailing_armed:
                self.trailing_armed = True
                self.highest_price = state["price"]  # TP 도달 시점부터 최고가 추적 시작
                logger.info(f"[EMA] 🎯 TP 도달 → TS ARMED | tp_price={tp_price:.2f} current={state['price']:.2f}")

        # TP 매도 조건: TS가 OFF이거나 TP_WITH_TS=True일 때만 즉시 매도
        tp_hit = tp_reached and (TP_WITH_TS or (not ts_enabled))
        add("take_profit", tp_enabled, tp_hit, {
            "price": state["price"],
            "tp_price": tp_price,
            "ts_enabled": ts_enabled,
            "tp_reached": tp_reached,
            "will_sell": tp_hit
        })

        # Trailing Stop (TP 도달 후 armed 상태에서만 작동)
        if ts_enabled:
            ts_armed = bool(self.trailing_armed)

            # ✅ armed 상태일 때만 최고가 갱신
            if ts_armed:
                if (self.highest_price is None) or (state["price"] > self.highest_price):
                    self.highest_price = state["price"]

            highest = self.highest_price

            # ✅ TP 가격 보호: trailing_limit의 최소값을 TP 가격으로 설정
            if highest is not None:
                raw_limit = highest * (1 - self.trailing_stop_pct)
                trailing_limit = max(tp_price, raw_limit)  # TP 이상 보장
            else:
                trailing_limit = None

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
            "pct": getattr(self, "trailing_stop_pct", None),
            "bars_held": bars_held, "min_hold": self.min_holding_period
        })

        # EMA Dead Cross
        ema_dc_enabled = sell_cond.get("ema_dc", False)
        ema_dc_hit = self._is_ema_dc()
        add("ema_dc", ema_dc_enabled, ema_dc_hit, {"ema_fast": state["ema_fast"], "ema_slow": state["ema_slow"]})

        trigger_key = None
        if sl_enabled and sl_hit:
            trigger_key = "Stop Loss"
        elif ts_enabled and ts_hit:
            trigger_key = "Trailing Stop"
        elif tp_enabled and tp_hit:
            trigger_key = "Take Profit"
        elif ema_dc_enabled and ema_dc_hit:
            trigger_key = "EMA Dead Cross"

        import hashlib
        sig = hashlib.md5(json.dumps({
            "armed": ts_armed,
            "highest": round((self.highest_price or 0.0), 6),
            "pass_map": {k: v["pass"] for k, v in checks.items() if v.get("enabled") == 1}
        }, sort_keys=True, default=str).encode()).hexdigest()

        should_insert = (trigger_key is not None)
        if not should_insert:
            if sig != self._last_sell_sig:
                should_insert = True
            elif self._sell_sample_n and (state["bar"] % self._sell_sample_n == 0):
                should_insert = True

        if not should_insert:
            if getattr(self, "_last_sell_audit_ts", None) != bar_ts:
                should_insert = True

        audit_key = (
            self.user_id,
            getattr(self, "ticker", "UNKNOWN"),
            getattr(self, "interval_sec", 60),
            bar_ts,
            sig,
        )

        if audit_key in EMAStrategy._seen_sell_audits:
            should_insert = False

        if should_insert:
            try:
                insert_sell_eval(
                    user_id=self.user_id,
                    ticker=getattr(self, "ticker", "UNKNOWN"),
                    interval_sec=getattr(self, "interval_sec", 60),
                    bar=state["bar"], price=state["price"],
                    macd=state["ema_fast_sell"],   # 매도용 EMA fast
                    signal=state["ema_slow_sell"],  # 매도용 EMA slow
                    tp_price=tp_price, sl_price=sl_price,
                    highest=self.highest_price, ts_pct=getattr(self, "trailing_stop_pct", None),
                    ts_armed=self.trailing_armed, bars_held=bars_held,
                    checks=checks,
                    triggered=(trigger_key is not None),
                    trigger_key=trigger_key,
                    notes="[EMA]"
                )
                EMAStrategy._seen_sell_audits.add(audit_key)
                self._last_sell_sig = sig
                self._last_sell_audit_ts = bar_ts
                logger.info(f"[EMA][AUDIT-SELL] inserted | uid={getattr(self, 'user_id', None)} ts={bar_ts} trigger={trigger_key}")
            except Exception as e:
                logger.error(f"[EMA][AUDIT-SELL] insert failed: {e} | uid={getattr(self, 'user_id', None)} ts={bar_ts} checks_keys={list(checks.keys())}")

        if sl_enabled and sl_hit:
            logger.info("[EMA] 🛑 SL HIT → SELL")
            self._sell_action(state, "Stop Loss")
            return

        # Trailing Stop (armed 상태일 때만 작동)
        if ts_enabled and self.trailing_armed:
            if self.highest_price is not None:
                # ✅ TP 가격 보호
                raw_limit = self.highest_price * (1 - self.trailing_stop_pct)
                trailing_limit = max(tp_price, raw_limit)
                logger.info(
                    f"[EMA] 🔧 TS CHECK | armed=True price={state['price']:.2f} high={self.highest_price:.2f} "
                    f"limit={trailing_limit:.2f} (raw={raw_limit:.2f}, tp={tp_price:.2f}) pct={self.trailing_stop_pct:.3f}"
                )
                if bars_held >= self.min_holding_period and state["price"] <= trailing_limit + eps:
                    logger.info("[EMA] 🛑 TS HIT → SELL")
                    self._sell_action(state, "Trailing Stop")
                    return

        # Take Profit (TS가 OFF이거나 TP_WITH_TS=True일 때만 즉시 매도)
        if tp_enabled and tp_hit:
            logger.info("[EMA] 💰 TP HIT (TS OFF or TP_WITH_TS=True) → SELL")
            self._sell_action(state, "Take Profit")
            return

        if ema_dc_enabled and ema_dc_hit:
            logger.info("[EMA] 🛑 EMA Dead Cross → SELL")
            self._sell_action(state, "EMA Dead Cross")
            return

    def _sell_action(self, state, reason):
        if getattr(self, "_last_sell_bar", None) == state["bar"]:
            logger.info(f"[EMA] ⏹️ DUPLICATE SELL SKIP | bar={state['bar']} reason={reason}")
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

    def _emit_trade(self, kind: str, state: dict, reason: str = ""):
        evt = {
            "bar": state["bar"],
            "type": kind,
            "reason": reason,
            "timestamp": state["timestamp"],
            "price": state["price"],
            "macd": state["ema_fast_sell"],   # 매도용 EMA (기존 호환성)
            "signal": state["ema_slow_sell"],  # 매도용 EMA (기존 호환성)
            "entry_price": self.entry_price,
            "entry_bar": self.entry_bar,
            "bars_held": state["bar"] - (self.entry_bar if self.entry_bar is not None else state["bar"]),
            "tp": (self.entry_price * (1 + self.take_profit)) if self.entry_price else None,
            "sl": (self.entry_price * (1 - self.stop_loss)) if self.entry_price else None,
            "highest": self.highest_price,
            "ts_pct": getattr(self, "trailing_stop_pct", None),
            "ts_armed": getattr(self, "trailing_armed", False),
        }
        EMAStrategy.trade_events.append(evt)


# ============================================================
# 전략 선택 팩토리
# ============================================================

def get_strategy_class(strategy_type: str):
    """
    params.strategy_type 값(MACD / EMA)에 따라 Strategy 클래스를 선택.
    """
    st = (strategy_type or DEFAULT_STRATEGY_TYPE).upper()
    if st == "EMA":
        return EMAStrategy
    return MACDStrategy
