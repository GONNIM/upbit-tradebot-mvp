import threading, queue, logging, sys, time, json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from core.strategy_v2 import MACDStrategy
from core.data_feed import stream_candles
from core.trader import UpbitTrader
from engine.params import LiveParams
from backtesting import Backtest
from services.db import insert_trade_audit, get_last_open_buy_order
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
    in_position: bool = False
    entry_price: Optional[float] = None
    # 신규 이벤트 중복 전송 방지 (bar, type)
    seen_signals = set()

    # ⛳️ 1) 시작 시 무조건 DB 시드 시도 (잔고 여부와 무관하게)
    entry_price = _seed_entry_price_from_db(params.upbit_ticker, user_id)
    if entry_price is not None:
        in_position = True

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
            "has_wallet_position": staticmethod(lambda t: trader._coin_balance(t) >= 1e-6),
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

                # ⛳️ 2) 루프마다 무조건 재시드 시도 (INFO 로그로 결과 출력)
                if entry_price is None:
                    entry_price = _seed_entry_price_from_db(params.upbit_ticker, user_id)
                    if entry_price is not None:
                        in_position = True

                # -----------------------------
                # 월렛 가드: SL/TP 즉시 매도
                # -----------------------------
                try:
                    coin_balance_live = trader._coin_balance(params.upbit_ticker)
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
                new_events = [e for e in trade_events if (e.get("bar"), e.get("type")) not in seen_signals]
                if not new_events:
                    logger.info("↩️ 신규 이벤트 없음 (모두 처리됨)")
                    logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
                    continue

                for evt in new_events:
                    ebar, etype = evt.get("bar"), evt.get("type")
                    if ebar is None or etype not in ("BUY", "SELL"):
                        logger.warning(f"[EVENT] skip invalid event: {evt}")
                        continue

                    key = (ebar, etype)
                    if key in seen_signals:
                        logger.info(f"[EVENT] duplicate skip: {key}")
                        continue
                    seen_signals.add(key)

                    cross_e = evt.get("reason")
                    macd_e = evt.get("macd")
                    signal_e = evt.get("signal")

                    coin_balance = trader._coin_balance(params.upbit_ticker)
                    logger.info(f"📊 현재 잔고: {coin_balance:.8f}")

                    # BUY
                    if etype == "BUY" and coin_balance < 1e-6:
                        ok, passed = check_buy_conditions(evt, df_bt, trade_conditions.get("buy", {}), params.macd_threshold)
                        if not ok:
                            logger.info(f"⛔ BUY 조건 미충족({passed}) → 차단")
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
                    # SELL
                    elif etype == "SELL" and coin_balance >= 1e-6:
                        if not check_sell_conditions(evt, trade_conditions.get("sell", {})):
                            logger.info(f"⛔ SELL 조건 미충족({cross_e}) → 차단 | evt={evt}")
                            continue

                        meta = {
                            "interval": params.interval,
                            "bar": ebar,
                            "reason": evt.get("reason", ""),
                            "macd": evt.get("macd"),
                            "signal": evt.get("signal"),
                            "entry_price": entry_price,
                            "entry_bar": ebar,                # 없으면 0
                            "bars_held": evt.get("bars_held", 0),
                            "tp": evt.get("tp"),
                            "sl": evt.get("sl"),
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
