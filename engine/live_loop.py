import threading, queue, logging, sys, time, json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from core.strategy_v2 import (
    MACDStrategy,
    EMAStrategy,
    get_strategy_class,
)
from core.data_feed import stream_candles
from core.trader import UpbitTrader
from engine.params import LiveParams
from backtesting import Backtest
from services.db import (
    get_last_open_buy_order,
    insert_buy_eval,
)
from config import (
    TP_WITH_TS,
    CONDITIONS_JSON_FILENAME,
    DEFAULT_STRATEGY_TYPE,
)

from engine.reconciler_singleton import get_reconciler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 공통 유틸
# ============================================================
def _normalize_asset(ticker: str) -> str:
    return ticker.split("-")[-1].strip().upper() if ticker else ticker


def _wallet_has_position(trader: UpbitTrader, ticker: str) -> bool:
    sym = _normalize_asset(ticker)
    try:
        return trader._coin_balance(sym) >= 1e-6
    except Exception:
        return False


def _wallet_balance(trader: UpbitTrader, ticker: str) -> float:
    sym = _normalize_asset(ticker)
    try:
        return float(trader._coin_balance(sym))
    except Exception:
        return 0.0


def _seed_entry_price_from_db(ticker: str, user_id: str) -> Optional[float]:
    """DB에서 최근 completed BUY의 체결가를 복구. raw와 결과를 INFO로 항상 남김."""
    try:
        raw = get_last_open_buy_order(ticker, user_id)  # {'price': float} | None
        logger.info(f"[SEED] raw_last_open={raw}")
        price = (raw or {}).get("price")
        if price is None:
            logger.info("[SEED] result=None (no price)")
            return None
        p = float(price)
        logger.info(f"🔁 Seed entry_price from DB: {p}")
        return p
    except Exception as e:
        logger.warning(f"[SEED] failed: {e}")
        return None


def detect_position_and_seed_entry(
    trader: UpbitTrader,
    ticker: str,
    user_id: str,
    entry_price: Optional[float],
) -> Tuple[bool, Optional[float]]:
    """
    지갑 잔고로 실제 포지션 유무를 판단하고, 엔트리 가격이 없으면 DB에서 1회 시드.
    - in_position: 잔고(코인) > 0 이면 True
    - entry_price: 없으면 get_last_open_buy_order()로 복구
    """
    bal = _wallet_balance(trader, ticker)
    inpos = bal >= 1e-6

    if inpos and entry_price is None:
        seed = get_last_open_buy_order(ticker, user_id)  # {"price": float} | None
        ep = (seed or {}).get("price")
        if ep is not None:
            entry_price = float(ep)
            logger.info(f"[POS] inpos=True, entry_price seeded={entry_price}")
        else:
            logger.info("[POS] inpos=True, but no entry price in DB")

    if (not inpos) and (entry_price is not None):
        logger.info("[POS] inpos=False → entry_price reset")
        entry_price = None

    return inpos, entry_price


# ============================================================
# 조건 파일 경로 & 로드
# ============================================================
def _strategy_tag(strategy_type: str) -> str:
    """
    strategy_type 문자열을 MACD / EMA 형태로 정규화.
    (DEFAULT_STRATEGY_TYPE 폴백)
    """
    if not strategy_type:
        return DEFAULT_STRATEGY_TYPE.upper()
    return strategy_type.upper().strip()


def _conditions_path_for(user_id: str, strategy_type: str) -> Tuple[Path, Optional[Path]]:
    """
    전략에서 사용하는 조건 JSON과 같은 규칙으로 파일 경로를 계산한다.
    - 주요 경로: {user_id}_{STRATEGY}_{CONDITIONS_JSON_FILENAME}
        예: mcmax33_MACD_buy_sell_conditions.json
    - 레거시 폴백: {user_id}_buy_sell_conditions.json
    """
    tag = _strategy_tag(strategy_type)
    main = Path(f"{user_id}_{tag}_{CONDITIONS_JSON_FILENAME}")
    legacy = Path(f"{user_id}_{CONDITIONS_JSON_FILENAME}")
    return main, (legacy if legacy.exists() and not main.exists() else None)


def load_trade_conditions(user_id: str, strategy_type: str) -> Tuple[Dict[str, Any], Path, Optional[float]]:
    """
    매수/매도 조건 JSON 로드.
    - 우선순위:
        1) {user_id}_{STRATEGY}_{CONDITIONS_JSON_FILENAME}
        2) (없을 경우) {user_id}_{CONDITIONS_JSON_FILENAME}
    - 반환: (conditions_dict, 사용된_path, mtime | None)
    """
    main_path, legacy_path = _conditions_path_for(user_id, strategy_type)

    path_to_use = None
    if main_path.exists():
        path_to_use = main_path
    elif legacy_path is not None and legacy_path.exists():
        path_to_use = legacy_path

    if path_to_use is None:
        logger.warning(
            f"[COND] condition file not found for user={user_id}, strategy={strategy_type} "
            f"(expected: {main_path} or legacy)"
        )
        return {"buy": {}, "sell": {}}, main_path, None

    try:
        with path_to_use.open("r", encoding="utf-8") as f:
            conds = json.load(f)
        mtime = path_to_use.stat().st_mtime
        logger.info(f"[COND] loaded: {path_to_use} (mtime={mtime})")
        return conds, path_to_use, mtime
    except Exception as e:
        logger.warning(f"[COND] failed to load {path_to_use}: {e}")
        return {"buy": {}, "sell": {}}, path_to_use, None


# ============================================================
# 조건 체크 (MACD / EMA 공통 인터페이스)
# ============================================================
def _as_num(x):
    try:
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None
    

def check_buy_conditions(
    strategy_type: str,
    evt: Dict[str, Any],
    df, 
    conds: Dict[str, bool],
    threshold: float,
    macd_ref=None,
    signal_ref=None
) -> Tuple[bool, list[str], list[str], Dict[str, Any]]:
    """
    BUY 조건 검증.
    - MACD: 기존 detailed 체크 유지
    - EMA: 전략 내부에서 이미 조건 검사 후 이벤트를 발생시키므로,
           여기서는 추가로 막지 않는다 (ok=True, 로그 구조만 맞춤)
    """
    st = _strategy_tag(strategy_type)

    # =====================================
    # EMA: 전략이 이미 조건 검사 → 통과만 시켜줌
    # =====================================
    if st == "EMA":
        # evt["reason"]에 ema_gc / above_base_ema / bullish_candle 등이 포함되어 있음
        reasons = str(evt.get("reason") or "")
        enabled = [k for k, v in conds.items() if v]
        # 로그 형식만 맞춰주고 실제 차단은 하지 않는다.
        report = {
            k: {
                "enabled": 1 if conds.get(k) else 0,
                "pass": 1 if (k in reasons) else 0,
                "value": None,
            }
            for k in enabled
        }
        failed = [k for k in enabled if report[k]["pass"] == 0]
        overall_ok = True  # EMA에서는 전략 쪽 판정이 진실이므로 여기서 막지 않는다.
        return overall_ok, enabled, failed, report
    
    # =====================================
    # MACD: 기존 로직 유지
    # =====================================
    def safe(col):
        return df[col].iloc[-2] if col in df and len(df[col]) >= 2 else None

    # 경계/부동소수 오차 보정용
    EPS = 1e-12

    # 판정에 사용할 값: LOG 기준값 우선 → evt 값 폴백
    macd_val = _as_num(macd_ref if macd_ref is not None else evt.get("macd"))
    signal_val = _as_num(signal_ref if signal_ref is not None else evt.get("signal"))

    passed, failed, details = [], [], {}

    if conds.get("golden_cross"):
        ok = "golden" in (evt.get("reason", "").lower())
        (passed if ok else failed).append("golden_cross")
        details["golden_cross"] = {"ok": ok, "reason": evt.get("reason")}

    if conds.get("macd_positive"):
        ok = (macd_val is not None and macd_val >= (threshold - EPS))
        (passed if ok else failed).append("macd_positive")
        details["macd_positive"] = {"ok": ok, "macd": macd_val, "thr": threshold}

    if conds.get("signal_positive"):
        ok = (signal_val is not None and signal_val >= (threshold - EPS))
        (passed if ok else failed).append("signal_positive")
        details["signal_positive"] = {"ok": ok, "signal": signal_val, "thr": threshold}

    if conds.get("bullish_candle"):
        open_, close_ = safe("Open"), safe("Close")
        ok = (open_ is not None and close_ is not None and close_ > open_)
        (passed if ok else failed).append("bullish_candle")
        details["bullish_candle"] = {"ok": ok, "open": open_, "close": close_}

    if conds.get("macd_trending_up") and "MACD" in df and len(df["MACD"]) >= 4:
        a, b, c = df["MACD"].iloc[-4], df["MACD"].iloc[-3], df["MACD"].iloc[-2]
        ok = (a < b < c)
        (passed if ok else failed).append("macd_trending_up")
        details["macd_trending_up"] = {"ok": ok, "a": a, "b": b, "c": c}

    if conds.get("above_ma20") and all(k in df for k in ["Close", "MA20"]):
        price, ma20 = safe("Close"), safe("MA20")
        ok = (price is not None and ma20 is not None and price > ma20)
        (passed if ok else failed).append("above_ma20")
        details["above_ma20"] = {"ok": ok, "price": price, "ma20": ma20}

    if conds.get("above_ma60") and all(k in df for k in ["Close", "MA60"]):
        price, ma60 = safe("Close"), safe("MA60")
        ok = (price is not None and ma60 is not None and price > ma60)
        (passed if ok else failed).append("above_ma60")
        details["above_ma60"] = {"ok": ok, "price": price, "ma60": ma60}

    enabled = [k for k, v in conds.items() if v]
    passed_enabled = [k for k in passed if k in enabled]
    failed_enabled = [k for k in enabled if k not in passed_enabled]
    overall_ok = (len(failed_enabled) == 0)

    return overall_ok, passed_enabled, failed_enabled, details


def check_sell_conditions(
    strategy_type: str,
    evt: Dict[str, Any],
    conds: Dict
) -> bool:
    """
    SELL 조건 검증.
    - MACD: reason 문자열과 conds 조합으로 필터
    - EMA: 전략 내부에서 이미 SELL 조건 검사 후 이벤트를 생성하므로,
           여기서는 추가로 막지 않는다 (True 반환)
    """
    st = _strategy_tag(strategy_type)
    reason = evt.get("reason", "").lower()

    # EMA: 전략 책임
    if st == "EMA":
        return True

    if "trailing" in reason and conds.get("trailing_stop"):
        return True
    if "take profit" in reason and conds.get("take_profit"):
        return True
    if "stop loss" in reason and conds.get("stop_loss"):
        return True
    if "macd negative" in reason and conds.get("macd_negative"):
        return True
    if "dead cross" in reason and conds.get("dead_cross"):
        return True
    
    return False


# ============================================================
# 메인 Live Loop
# ============================================================
def run_live_loop(
    params: LiveParams,
    q: queue.Queue,
    trader: UpbitTrader,
    stop_event: threading.Event,
    test_mode: bool,
    user_id: str,
) -> None:
    """
    실시간 운용 루프.
    - 전략 선택: params.strategy_type (MACD / EMA)
    - 공통 인터페이스:
        * base_cls.log_events / trade_events 에서 이벤트 읽기
        * Wallet 기반 포지션/엔트리 관리
        * 조건 JSON은 전략과 동일 규칙으로 로드
    """
    from streamlit.runtime.scriptrunner import add_script_run_ctx
    add_script_run_ctx(threading.current_thread())

    is_live = (not test_mode)
    mode_tag = "LIVE" if is_live else "TEST"
    strategy_tag = _strategy_tag(params.strategy_type)

    logger.info(f"[BOOT] run_live_loop start | mode={mode_tag} | strategy={strategy_tag}")

    # --- 조건 JSON 로드 & mtime 추적 ---
    trade_conditions, cond_path, cond_mtime = load_trade_conditions(user_id, strategy_tag)

    in_position: bool = _wallet_has_position(trader, params.upbit_ticker)
    entry_price: Optional[float] = None
    seen_signals = set()

    if in_position:
        entry_price = _seed_entry_price_from_db(params.upbit_ticker, user_id)

    # --- 전략 클래스 선택 & LiveStrategy 구성 ---
    base_cls = get_strategy_class(strategy_tag)

    # log_events / trade_events가 어디에 쌓일지 결정
    if issubclass(base_cls, EMAStrategy):
        events_cls = EMAStrategy
    elif issubclass(base_cls, MACDStrategy):
        events_cls = MACDStrategy
    else:
        raise RuntimeError(f"Unsupported base strategy class: {base_cls}")

    # 전략별 class-level 파라미터 오버라이드
    live_attrs = {
        # 공통 메타
        "user_id": user_id,
        "ticker": params.upbit_ticker,
        "strategy_type": strategy_tag,
        # Wallet 훅(티커 정규화 포함)
        "has_wallet_position": staticmethod(lambda t: _wallet_has_position(trader, t)),
        "get_wallet_entry_price": staticmethod(
            lambda t: (get_last_open_buy_order(t, user_id) or {}).get("price")
        ),
    }

    # MACD 전략일 경우 MACD 관련 파라미터 반영
    if issubclass(base_cls, MACDStrategy):
        live_attrs.update(
            fast_period=params.fast_period,
            slow_period=params.slow_period,
            signal_period=params.signal_period,
            take_profit=params.take_profit,
            stop_loss=params.stop_loss,
            macd_threshold=params.macd_threshold,
            min_holding_period=params.min_holding_period,
            macd_crossover_threshold=params.macd_crossover_threshold,
            macd_exit_enabled=params.macd_exit_enabled,
            signal_confirm_enabled=params.signal_confirm_enabled,
        )

    # EMA 전략은 현재 기본 period를 그대로 사용
    # (필요 시 LiveParams에 EMA용 파라미터 추가해서 여기서 매핑)

    strategy_cls = type("LiveStrategy", (base_cls,), live_attrs)

    logger.info(
        f"[BOOT] strategy_cls={strategy_cls.__name__} (base={base_cls.__name__}) "
        f"| ticker={params.upbit_ticker} | interval={params.interval}"
    )

    try:
        while not stop_event.is_set():
            for df in stream_candles(params.upbit_ticker, params.interval, q, stop_event=stop_event):
                if stop_event.is_set():
                    break

                # --- 조건 파일 hot reload (선택적) ---
                try:
                    if cond_path is not None and cond_path.exists():
                        mtime_now = cond_path.stat().st_mtime
                        if cond_mtime is not None and mtime_now != cond_mtime:
                            with cond_path.open("r", encoding="utf-8") as f:
                                trade_conditions = json.load(f)
                            cond_mtime = mtime_now
                            logger.info(f"[COND] reloaded: {cond_path} (mtime={mtime_now})")
                except Exception as e:
                    logger.warning(f"[COND] hot reload skipped: {e}")

                if df is None or df.empty:
                    logger.info("❌ 데이터프레임 비어있음 → 5초 후 재시도")
                    time.sleep(5)
                    continue

                if len(df) < 3:
                    time.sleep(1)
                    continue

                # --- 이벤트 버퍼 초기화 (전략별) ---
                events_cls.log_events = []
                events_cls.trade_events = []

                logger.info(
                    "[BOOT] thresholds check | macd_thr=%.6f | base_cls=%s",
                    float(getattr(params, "macd_threshold", 0.0)),
                    base_cls.__name__,
                )

                # 백테스트용 DF: 마지막 캔들은 "미완성"이므로 제외
                df_bt = df.iloc[:-1].copy()

                bt = Backtest(
                    df_bt,
                    strategy_cls,
                    cash=params.cash,
                    commission=params.commission,
                    exclusive_orders=True,
                )
                bt.run()
                logger.info("✅ LiveStrategy Backtest 실행 완료")

                log_events = events_cls.log_events
                trade_events = events_cls.trade_events

                latest_bar_bt = len(df_bt) - 1
                latest_index_live = df.index[-1]
                latest_price_live = float(df.Close.iloc[-1])

                # --- 지갑 기준 포지션/엔트리 확정 ---
                in_position, entry_price = detect_position_and_seed_entry(
                    trader, params.upbit_ticker, user_id, entry_price
                )
                logger.info(f"[POS] ({mode_tag}) in_position={in_position}, entry_price={entry_price}")

                # --- 최신 LOG 전송 (MACD / EMA 공통) ---
                cross_log = macd_log = signal_log = price_log = None
                for event in reversed(log_events):
                    if event[1] == "LOG" and event[0] == latest_bar_bt:
                        bar_idx, _, cross_log, macd_log, signal_log, price_log = event
                        msg = (
                            f"{df_bt.index[bar_idx]} | price={price_log:.2f} | "
                            f"cross={cross_log} | macd={macd_log:.5f} | signal={signal_log:.5f} | bar={bar_idx}"
                        )
                        q.put((df.index[bar_idx], "LOG", f"[{mode_tag}] {msg}"))
                        break

                # --- Wallet-Guard (SL/TP 즉시 매도) ---
                try:
                    coin_balance_live = _wallet_balance(trader, params.upbit_ticker)
                    logger.info(f"[WG] balance={coin_balance_live} entry_price={entry_price}")
                    if coin_balance_live >= 1e-6 and (entry_price is not None):
                        sell_cond = trade_conditions.get("sell", {})
                        sl_on = bool(sell_cond.get("stop_loss", False))
                        tp_on = bool(sell_cond.get("take_profit", False))
                        ts_on = bool(sell_cond.get("trailing_stop", False))

                        sl_price = entry_price * (1 - params.stop_loss)
                        tp_price = entry_price * (1 + params.take_profit)
                        tp_allowed = TP_WITH_TS or (not ts_on)

                        triggered: Optional[Tuple[str, float]] = None
                        if sl_on and (latest_price_live <= sl_price):
                            triggered = ("Stop Loss", sl_price)
                        elif tp_on and tp_allowed and (latest_price_live >= tp_price):
                            triggered = ("Take Profit", tp_price)

                        if triggered is not None:
                            reason, ref_price = triggered
                            logger.info(
                                f"🛡️ Wallet-Guard → SELL ({reason}) | live={latest_price_live:.4f} ref={ref_price:.4f}"
                            )

                            meta = {
                                "interval": params.interval,
                                "bar": len(df_bt) - 1,
                                "reason": reason,               # "Stop Loss" / "Take Profit"
                                "macd": macd_log,
                                "signal": signal_log,
                                "entry_price": entry_price,
                                "entry_bar": len(df_bt) - 1,    # 적어도 동기화 가능한 값
                                "bars_held": 0,
                                "tp": tp_price,
                                "sl": sl_price,
                                "highest": None,
                                "ts_pct": getattr(params, "trailing_stop_pct", None),
                                "ts_armed": False,
                            }
                            result = trader.sell_market(
                                coin_balance_live,
                                params.upbit_ticker,
                                latest_price_live,
                                ts=latest_index_live,
                                meta=meta
                            )
                            if result:
                                q.put(
                                    (
                                        latest_index_live,
                                        "SELL",
                                        result["qty"],
                                        result["price"],
                                        reason,
                                        None,
                                        None
                                    )
                                )
                                entry_price = None
                                in_position = False

                                if is_live and result.get("uuid"):
                                    get_reconciler().enqueue(
                                        result["uuid"],
                                        user_id=user_id,
                                        ticker=params.upbit_ticker,
                                        side="SELL"
                                    )
                                
                                # 월렛 가드는 SELL 후 바로 다음 루프로
                                continue
                    else:
                        if coin_balance_live < 1e-6:
                            logger.info("[WG] skip: coin_balance_live == 0")
                        if entry_price is None:
                            logger.info("[WG] skip: entry_price is None (DB 시드 실패)")
                except Exception as e:
                    logger.warning(f"[WG:{mode_tag}] wallet-guard skipped: {e}")

                # --- 전략 이벤트 처리 (MACD / EMA 공통 형식) ---
                events_on_latest = [e for e in trade_events if e.get("bar") == latest_bar_bt]
                evt = events_on_latest[-1] if events_on_latest else None
                if not evt:
                    logger.info(f"↩️ 최신 bar 신호 없음 ({mode_tag}) | in_position={in_position} entry={entry_price}")
                    continue

                ebar = evt.get("bar")
                etype = evt.get("type")
                if ebar is None or etype not in ("BUY", "SELL"):
                    logger.warning(f"[EVENT:{mode_tag}] skip invalid event: {evt}")
                    continue

                # dedup key는 "닫힌 봉의 실제 타임스탬프" 기준
                try:
                    closed_ts = df_bt.index[ebar]
                    key = (str(closed_ts), etype, mode_tag)
                except Exception as _e:
                    logger.warning(f"[EVENT:{mode_tag}] closed_ts resolve failed: {repr(_e)}; fallback to bar-num")
                    key = (int(ebar), etype, mode_tag)

                if key in seen_signals:
                    logger.info(f"[EVENT:{mode_tag}] duplicate skip: {key} | in_position={in_position} | entry_price={entry_price}")
                    continue
                seen_signals.add(key)

                cross_e = evt.get("reason")
                macd_e = evt.get("macd")
                signal_e = evt.get("signal")

                coin_balance = _wallet_balance(trader, params.upbit_ticker)
                logger.info(f"📊 [{mode_tag}] 현재 잔고: {coin_balance:.8f}")

                # ======================
                # BUY 처리 (포지션 없음)
                # ======================
                if not in_position:
                    if etype != "BUY":
                        logger.info(f"⛔ ({mode_tag}) 포지션 없음 → SELL 무시")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    ok, passed, failed, det = check_buy_conditions(
                        strategy_tag,
                        evt,
                        df_bt,
                        trade_conditions.get("buy", {}),
                        params.macd_threshold,
                        macd_ref=macd_log,
                        signal_ref=signal_log
                    )
                    if not ok:
                        try:
                            logger.info(
                                f"⛔ ({mode_tag}) BUY 조건 미충족 | failed=%s | values=%s | thr=%.6f | evt_reason=%s",
                                failed,
                                {k: det.get(k) for k in failed},
                                float(params.macd_threshold),
                                evt.get("reason"),
                            )
                        except Exception:
                            logger.info(f"⛔ ({mode_tag}) BUY 조건 미충족({failed})")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    meta = {
                        "interval": params.interval,
                        "bar": ebar,
                        "reason": evt.get("reason", ""),
                        "macd": evt.get("macd"),
                        "signal": evt.get("signal"),
                        "entry_price": None,       # BUY 직전엔 없음
                        "entry_bar": ebar,
                        "bars_held": 0,
                        "tp": None,
                        "sl": None,
                        "highest": None,
                        "ts_pct": getattr(params, "trailing_stop_pct", None),
                        "ts_armed": False,
                    }
                    result = trader.buy_market(
                        latest_price_live,
                        params.upbit_ticker,
                        ts=latest_index_live,
                        meta=meta
                    )
                    if result:
                        logger.info(f"✅ ({mode_tag}) BUY 체결 완료({passed}) {result}")
                        q.put(
                            (
                                latest_index_live,
                                "BUY",
                                result["qty"],
                                result["price"],
                                cross_e,
                                macd_e,
                                signal_e
                            )
                        )
                        in_position = True
                        entry_price = result["price"]

                        if is_live and result.get("uuid"):
                            get_reconciler().enqueue(
                                result["uuid"],
                                user_id=user_id,
                                ticker=params.upbit_ticker,
                                side="BUY"
                            )

                        # 체결 직후 BUY 평가 스냅샷 (리포트 1:1 매칭용)
                        try:
                            insert_buy_eval(
                                user_id=user_id,
                                ticker=params.upbit_ticker,
                                interval_sec=getattr(params, "interval_sec", 60),
                                bar=latest_bar_bt,                       # 이번 루프에서의 평가 기준 bar
                                price=float(result["price"]),            # 실제 체결가
                                macd=float(macd_e) if macd_e is not None else None,
                                signal=float(signal_e) if signal_e is not None else None,
                                have_position=True,
                                overall_ok=True,                         # 체결됐으니 평가 OK로 마킹
                                failed_keys=[],
                                checks={
                                    "reason": cross_e,
                                    "snapshot": f"BUY_EXECUTED_{mode_tag}"
                                },
                                notes=(
                                    f"EXECUTED({mode_tag}) "
                                    f"ts_live={latest_index_live} bar_bt={latest_bar_bt}"
                                ),
                            )
                            logger.info(
                                f"[AUDIT-LINK:{mode_tag}] BUY EXEC snap | ts_live={latest_index_live} "
                                f"bar_bt={latest_bar_bt} price={float(result['price']):.6f}"
                            )
                        except Exception as e:
                            logger.warning(f"[AUDIT-LINK:{mode_tag}] insert_buy_eval (EXECUTED) failed: {e}")
                # ======================
                # SELL 처리 (포지션 있음)
                # ======================
                else:
                    if etype != "SELL":
                        logger.info(f"⛔ ({mode_tag}) 포지션 있음 → BUY 무시")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    if not check_sell_conditions(evt, trade_conditions.get("sell", {})):
                        logger.info(f"⛔ ({mode_tag}) SELL 조건 미충족({cross_e}) → 차단 | evt={evt}")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    tp_p = (
                        entry_price * (1 + params.take_profit)
                        if entry_price is not None
                        else None
                    )
                    sl_p = (
                        entry_price * (1 - params.stop_loss)
                        if entry_price is not None
                        else None
                    )

                    meta = {
                        "interval": params.interval,
                        "bar": ebar,
                        "reason": evt.get("reason", ""),
                        "macd": evt.get("macd"),
                        "signal": evt.get("signal"),
                        "entry_price": entry_price,
                        "entry_bar": ebar,                # 없으면 0
                        "bars_held": evt.get("bars_held", 0),
                        "tp": tp_p,
                        "sl": sl_p,
                        "highest": evt.get("highest"),
                        "ts_pct": evt.get("ts_pct"),
                        "ts_armed": evt.get("ts_armed"),
                    }
                    result = trader.sell_market(
                        coin_balance,
                        params.upbit_ticker,
                        latest_price_live,
                        ts=latest_index_live,
                        meta=meta
                    )
                    if result:
                        logger.info(f"✅ ({mode_tag}) SELL 체결 완료({cross_e}) {result}")
                        q.put(
                            (
                                latest_index_live,
                                "SELL",
                                result["qty"],
                                result["price"],
                                cross_e,
                                macd_e,
                                signal_e
                            )
                        )
                        in_position = False
                        entry_price = None

                        if is_live and result.get("uuid"):
                            get_reconciler().enqueue(
                                result["uuid"],
                                user_id=user_id,
                                ticker=params.upbit_ticker,
                                side="SELL"
                            )

                logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
    except Exception:
        logger.exception(f"❌ run_live_loop 예외 발생 ({mode_tag})")
        ts = time.time()  # 또는 latest_index_live 사용 가능
        exc_type, exc_value, tb = sys.exc_info()
        q.put((ts, "EXCEPTION", exc_type, exc_value, tb))
    finally:
        logger.info(f"🧹 run_live_loop 종료 ({mode_tag}) → stop_event set")
        stop_event.set()
