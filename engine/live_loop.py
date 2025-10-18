import threading, queue, logging, sys, time, json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from core.strategy_v2 import MACDStrategy
from core.data_feed import stream_candles
from core.trader import UpbitTrader
from engine.params import LiveParams
from backtesting import Backtest
from services.db import get_last_open_buy_order, insert_buy_eval
from config import TP_WITH_TS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_trade_conditions(user_id: str):
    path = Path(f"{user_id}_buy_sell_conditions.json")
    if not path.exists():
        return {"buy": {}, "sell": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_buy_conditions(evt, df, conds, threshold: float):
    def safe(col):
        # 길이 체크 버그 수정
        return df[col].iloc[-2] if col in df and len(df[col]) >= 2 else None

    checks = []

    if conds.get("golden_cross"):
        checks.append("golden_cross" if "golden" in (evt.get("reason", "").lower()) else None)

    if conds.get("macd_positive"):
        macd = evt.get("macd")
        checks.append("macd_positive" if (macd is not None and macd > threshold) else None)

    if conds.get("signal_positive"):
        sig = evt.get("signal")
        checks.append("signal_positive" if (sig is not None and sig > threshold) else None)

    if conds.get("bullish_candle"):
        open_, close_ = safe("Open"), safe("Close")
        checks.append("bullish_candle" if (open_ is not None and close_ is not None and close_ > open_) else None)

    if conds.get("macd_trending_up") and "MACD" in df and len(df["MACD"]) >= 4:
        a, b, c = df["MACD"].iloc[-4], df["MACD"].iloc[-3], df["MACD"].iloc[-2]
        checks.append("macd_trending_up" if (a < b < c) else None)

    if conds.get("above_ma20") and all(k in df for k in ["Close", "MA20"]):
        price, ma20 = safe("Close"), safe("MA20")
        checks.append("above_ma20" if (price is not None and ma20 is not None and price > ma20) else None)

    if conds.get("above_ma60") and all(k in df for k in ["Close", "MA60"]):
        price, ma60 = safe("Close"), safe("MA60")
        checks.append("above_ma60" if (price is not None and ma60 is not None and price > ma60) else None)

    enabled = [k for k, v in conds.items() if v]
    passed = [c for c in checks if c]
    return len(passed) == len(enabled), passed


def check_sell_conditions(evt, conds):
    reason = evt.get("reason", "").lower()
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


# =========================
# 잔고 조회 정규화 유틸
#  - Upbit 잔고 키가 'KRW-WLFI'가 아니라 'WLFI'로 관리되는 경우를 처리
#  - 포지션 감지 오류(in_position=False로 오판) 방지
# =========================
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
    

# --- 포지션 감지 & 엔트리 시드 유틸 ---
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


def run_live_loop(
    params: LiveParams,
    q: queue.Queue,
    trader: UpbitTrader,
    stop_event: threading.Event,
    test_mode: bool,
    user_id: str,
) -> None:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
    add_script_run_ctx(threading.current_thread())

    trade_conditions = load_trade_conditions(user_id)
    # =========================
    # 시작 in_position 판정은 "지갑 기준"으로만
    #  - DB 시드만으로 in_position=True로 시작하던 문제 제거
    # =========================
    in_position: bool = _wallet_has_position(trader, params.upbit_ticker)
    entry_price: Optional[float] = None
    # 신규 이벤트 중복 전송 방지 (bar, type)
    seen_signals = set()

    # 지갑에 포지션이 있을 때만 DB에서 엔트리 가격 보조 시드
    if in_position:
        entry_price = _seed_entry_price_from_db(params.upbit_ticker, user_id)

    # 전략 클래스 생성 (훅 포함)
    strategy_cls = type(
        "LiveStrategy",
        (MACDStrategy,),
        {
            "fast_period": params.fast_period,
            "slow_period": params.slow_period,
            "signal_period": params.signal_period,
            "take_profit": params.take_profit,
            "stop_loss": params.stop_loss,
            "macd_threshold": params.macd_threshold,
            "min_holding_period": params.min_holding_period,
            "macd_crossover_threshold": params.macd_crossover_threshold,
            "macd_exit_enabled": params.macd_exit_enabled,
            "signal_confirm_enabled": params.signal_confirm_enabled,
            "user_id": user_id,
            "ticker": params.upbit_ticker,
            # 포지션 감지 훅도 정규화 기반으로 일원화
            "has_wallet_position": staticmethod(lambda t: _wallet_has_position(trader, t)),
            # (ticker, user_id) 시그니처 그대로, float 또는 None 반환
            "get_wallet_entry_price": staticmethod(lambda t: (get_last_open_buy_order(t, user_id) or {}).get("price")),
        },
    )

    try:
        while not stop_event.is_set():
            for df in stream_candles(params.upbit_ticker, params.interval, q, stop_event=stop_event):
                if stop_event.is_set():
                    break

                if df is None or df.empty:
                    logger.info("❌ 데이터프레임 비어있음 → 5초 후 재시도")
                    time.sleep(5)
                    continue

                if len(df) < 3:
                    time.sleep(1)
                    continue

                MACDStrategy.log_events = []
                MACDStrategy.trade_events = []

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

                log_events = MACDStrategy.log_events
                trade_events = MACDStrategy.trade_events

                latest_bar_bt = len(df_bt) - 1
                latest_index_live = df.index[-1]
                latest_price_live = float(df.Close.iloc[-1])

                # --- 지갑 기준 포지션/엔트리 확정 ---
                in_position, entry_price = detect_position_and_seed_entry(trader, params.upbit_ticker, user_id, entry_price)
                logger.info(f"[POS] resolved → in_position={in_position}, entry_price={entry_price}")

                # 최신 LOG만 전송
                cross_log = macd_log = signal_log = price_log = None
                for event in reversed(log_events):
                    if event[1] == "LOG" and event[0] == latest_bar_bt:
                        bar_idx, _, cross_log, macd_log, signal_log, price_log = event
                        msg = (
                            f"{df_bt.index[bar_idx]} | price={price_log:.2f} | "
                            f"cross={cross_log} | macd={macd_log:.5f} | signal={signal_log:.5f} | bar={bar_idx}"
                        )
                        q.put((df.index[bar_idx], "LOG", msg))
                        break

                # -----------------------------
                # 월렛 가드: SL/TP 즉시 매도
                # -----------------------------
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
                                q.put((latest_index_live, "SELL", result["qty"], result["price"], reason, None, None))
                                entry_price = None
                                in_position = False
                                continue
                    else:
                        if coin_balance_live < 1e-6:
                            logger.info("[WG] skip: coin_balance_live == 0")
                        if entry_price is None:
                            logger.info("[WG] skip: entry_price is None (DB 시드 실패)")
                except Exception as e:
                    logger.warning(f"[WG] wallet-guard check skipped: {e}")

                # -----------------------------
                # 전략 이벤트 처리
                # -----------------------------
                events_on_latest = [e for e in trade_events if e.get("bar") == latest_bar_bt]
                evt = events_on_latest[-1] if events_on_latest else None
                if not evt:
                    logger.info(f"↩️ 최신 bar 신호 없음 | in_position={in_position} entry={entry_price}")
                    logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                    continue

                ebar = evt.get("bar")
                etype = evt.get("type")
                if ebar is None or etype not in ("BUY", "SELL"):
                    logger.warning(f"[EVENT] skip invalid event: {evt}")
                    continue

                key = (ebar, etype)
                if key in seen_signals:
                    logger.info(f"[EVENT] duplicate skip: {key}")
                    logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                    continue
                seen_signals.add(key)

                cross_e = evt.get("reason")
                macd_e = evt.get("macd")
                signal_e = evt.get("signal")

                coin_balance = _wallet_balance(trader, params.upbit_ticker)
                logger.info(f"📊 현재 잔고: {coin_balance:.8f}")

                if not in_position:
                    # 포지션 없으면 BUY만 허용
                    if etype != "BUY":
                        logger.info("⛔ 포지션 없음 → SELL 무시")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    ok, passed = check_buy_conditions(evt, df_bt, trade_conditions.get("buy", {}), params.macd_threshold)
                    if not ok:
                        logger.info(f"⛔ BUY 조건 미충족({passed}) → 차단")
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
                        logger.info(f"✅ BUY 체결 완료({passed}) {result}")
                        q.put((latest_index_live, "BUY", result["qty"], result["price"], cross_e, macd_e, signal_e))
                        in_position = True
                        entry_price = result["price"]

                        # === 체결 직후 BUY 평가 스냅샷 남기기 (리포트 1:1 매칭용) ===
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
                                checks={"reason": cross_e, "snapshot": "BUY_EXECUTED"},
                                # 스키마 변경 없이 링크키 보관(ts_live, bar_bt)
                                notes=f"EXECUTED ts_live={latest_index_live} bar_bt={latest_bar_bt}"
                            )
                            logger.info(
                                f"[AUDIT-LINK] BUY EXEC snap | ts_live={latest_index_live} "
                                f"bar_bt={latest_bar_bt} price={float(result['price']):.6f}"
                            )
                        except Exception as e:
                            logger.warning(f"[AUDIT-LINK] insert_buy_eval (EXECUTED) failed: {e}")
                else:
                    # 포지션 있으면 SELL만 허용
                    if etype != "SELL":
                        logger.info("⛔ 포지션 있음 → BUY 무시")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    if not check_sell_conditions(evt, trade_conditions.get("sell", {})):
                        logger.info(f"⛔ SELL 조건 미충족({cross_e}) → 차단 | evt={evt}")
                        logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                        continue

                    tp_p = entry_price * (1 + params.take_profit) if entry_price is not None else None
                    sl_p = entry_price * (1 - params.stop_loss) if entry_price is not None else None

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
                        logger.info(f"✅ SELL 체결 완료({cross_e}) {result}")
                        q.put((latest_index_live, "SELL", result["qty"], result["price"], cross_e, macd_e, signal_e))
                        in_position = False
                        entry_price = None

                logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
    except Exception:
        logger.exception("❌ run_live_loop 예외 발생:")
        q.put(("EXCEPTION", *sys.exc_info()))
    finally:
        logger.info("🧹 run_live_loop 종료 완료 → stop_event set")
        stop_event.set()
