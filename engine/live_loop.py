import string, threading, queue, logging, sys, time, json

from pathlib import Path
from core.strategy_v2 import MACDStrategy
from core.data_feed import stream_candles
from core.trader import UpbitTrader
from engine.params import LiveParams
from backtesting import Backtest
from services.db import insert_trade_audit


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_trade_conditions(user_id: str):
    path = Path(f"data/{user_id}_buy_sell_conditions.json")
    if not path.exists():
        return {"buy": {}, "sell": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_buy_conditions(evt, df, conds):
    def safe(col): return df[col].iloc[-2] if col in df else None
    checks = []

    if conds.get("golden_cross"):
        checks.append("golden_cross" if "golden" in evt.get("reason", "").lower() else None)

    if conds.get("macd_positive"):
        macd = evt.get("macd"); checks.append("macd_positive" if macd and macd > 0 else None)

    if conds.get("signal_positive"):
        sig = evt.get("signal"); checks.append("signal_positive" if sig and sig > 0 else None)

    if conds.get("bullish_candle"):
        open_, close_ = safe("Open"), safe("Close")
        checks.append("bullish_candle" if close_ > open_ else None)

    if conds.get("macd_trending_up") and "MACD" in df:
        macd_prev, macd_now = df["MACD"].iloc[-3:-1]
        checks.append("macd_trending_up" if macd_now > macd_prev else None)

    if conds.get("above_ma20") and "MA20" in df:
        price, ma20 = safe("Close"), safe("MA20")
        checks.append("above_ma20" if price > ma20 else None)

    if conds.get("above_ma60") and "MA60" in df:
        price, ma60 = safe("Close"), safe("MA60")
        checks.append("above_ma60" if price > ma60 else None)

    enabled = [k for k, v in conds.items() if v]
    passed = [c for c in checks if c]
    return len(passed) == len(enabled), passed


def check_sell_conditions(evt, conds):
    reason = evt.get("reason", "").lower()
    if "trailing" in reason and conds.get("trailing_stop"): return True
    if "take profit" in reason and conds.get("take_profit"): return True
    if "stop loss" in reason and conds.get("stop_loss"): return True
    if "macd negative" in reason and conds.get("macd_negative"): return True
    if "dead cross" in reason and conds.get("dead_cross"): return True
    return False


def run_live_loop(
    params: LiveParams,
    q: queue.Queue,
    trader: UpbitTrader,
    stop_event: threading.Event,
    test_mode: bool,
    user_id: string
) -> None:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
    add_script_run_ctx(threading.current_thread())

    trade_conditions = load_trade_conditions(user_id)
    in_position = False
    entry_price = None
    # ★ dict/tuple 이벤트 중복 전송 방지용 (bar, type) 키 저장
    seen_signals = set()

    # 전략 클래스 생성
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
            "ticker": params.upbit_ticker
        },
    )

    try:
        while not stop_event.is_set():
            for df in stream_candles(
                params.upbit_ticker, params.interval, q, stop_event=stop_event
            ):
                if stop_event.is_set():
                    break

                if df is None or df.empty:
                    logger.warning("❌ 데이터프레임 비어있음 → 5초 후 재시도")
                    time.sleep(5)
                    continue

                if len(df) < 3:
                    time.sleep(1)
                    continue
                df_bt = df.iloc[:-1].copy()
                bt = Backtest(
                    # df,
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

                latest_index_bt = df_bt.index[-1]
                latest_bar_bt = len(df_bt) - 1
                latest_index_live = df.index[-1]
                latest_price_live = float(df.Close.iloc[-1])

                # 🔹 최신 LOG만 전송 (UI 모니터링)
                cross_log = None
                macd_log = None
                signal_log = None
                price_log = None
                for event in reversed(log_events):
                    if event[1] == "LOG" and event[0] == latest_bar_bt:
                        bar_idx, _, cross_log, macd_log, signal_log, price_log = event
                        msg = f"{df_bt.index[bar_idx]} | price={price_log:.2f} | cross={cross_log} | macd={macd_log:.5f} | signal={signal_log:.5f} | bar={bar_idx}"
                        q.put((df.index[bar_idx], "LOG", msg))
                        break

                if not trade_events:
                    logger.info("🔍 최근 BUY/SELL 시그널 없음")
                    continue

                evt = trade_events[-1]
                ebar, etype = evt.get("bar"), evt.get("type")
                if (ebar, etype) in seen_signals:
                    logger.debug("↩️ 중복 신호 스킵: %s", (ebar, etype))
                    continue
                seen_signals.add((ebar, etype))

                cross_e = evt.get("reason")
                macd_e = evt.get("macd")
                signal_e = evt.get("signal")

                coin_balance = trader._coin_balance(params.upbit_ticker)
                logger.info(f"📊 현재 잔고: {coin_balance:.8f}")

                # 🔹 매수 로직
                if etype == "BUY" and coin_balance < 1e-6:
                    ok, passed = check_buy_conditions(evt, df_bt, trade_conditions.get("buy", {}))
                    if not ok:
                        logger.warning(f"⛔ BUY 조건 미충족({passed}) → 차단")
                        continue

                    result = trader.buy_market(latest_price_live, params.upbit_ticker, ts=latest_index_live)
                    if result:
                        logger.info(f"✅ BUY 체결 완료({passed}) {result}")
                        q.put((latest_index_live, "BUY", result["qty"], result["price"], cross_e, macd_e, signal_e))
                        in_position = True
                        entry_price = result["price"]
                        try:
                            insert_trade_audit(user_id, params.upbit_ticker, params.interval, ebar, "BUY", evt.get("reason", ""), result["price"], evt.get("macd"), evt.get("signal"), result["price"], ebar, 0, None, None, None, None, None, None)
                        except Exception as e:
                            logger.error(f"[AUDIT-TRADES] insert failed(BUY): {e}")
                # 🔹 매도 로직
                elif etype == "SELL" and coin_balance >= 1e-6:
                    if not check_sell_conditions(evt, trade_conditions.get("sell", {})):
                        logger.warning(f"⛔ SELL 조건 미충족({cross_e}) → 차단 | evt={evt}")
                        continue

                    result = trader.sell_market(coin_balance, params.upbit_ticker, latest_price_live, ts=latest_index_live)
                    if result:
                        logger.info(f"✅ SELL 체결 완료({cross_e}) {result}")
                        q.put((latest_index_live, "SELL", result["qty"], result["price"], cross_e, macd_e, signal_e))
                        in_position = False
                        try:
                            insert_trade_audit(user_id, params.upbit_ticker, params.interval, ebar, "SELL", evt.get("reason", ""), result["price"], evt.get("macd"), evt.get("signal"), entry_price, ebar, evt.get("bars_held"), evt.get("tp"), evt.get("sl"), evt.get("highest"), evt.get("ts_pct"), evt.get("ts_armed"))
                        except Exception as e:
                            logger.error(f"[AUDIT-TRADES] insert failed(SELL): {e}")
                        entry_price = None

                logger.info(f"💡 상태: in_position={in_position} | entry_price={entry_price}")
    except Exception:
        logger.exception("❌ run_live_loop 예외 발생:")
        q.put(("EXCEPTION", *sys.exc_info()))

    finally:
        logger.info("🧹 run_live_loop 종료 완료 → stop_event set")
        stop_event.set()
