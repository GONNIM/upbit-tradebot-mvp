import string
import threading
import queue
import logging
import sys
import time

from core.strategy_v2 import MACDStrategy
from core.data_feed import stream_candles
from core.trader import UpbitTrader
from engine.params import LiveParams
from backtesting import Backtest


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

    in_position = False
    entry_price = None

    try:
        # ★ dict/tuple 이벤트 중복 전송 방지용 (bar, type) 키 저장
        seen_signals = set()

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

                bt = Backtest(
                    df,
                    strategy_cls,
                    cash=params.cash,
                    commission=params.commission,
                    exclusive_orders=True,
                )
                bt.run()
                logger.info("✅ LiveStrategy Backtest 실행 완료")

                log_events = MACDStrategy.log_events
                trade_events = MACDStrategy.trade_events

                latest_index = df.index[-1]
                latest_price = df.Close.iloc[-1]
                latest_bar = len(df) - 1

                # 🔹 최신 LOG만 전송 (UI 모니터링)
                for event in reversed(log_events):
                    if event[1] == "LOG" and event[0] == latest_bar:
                        bar_idx, _, cross, macd, signal, price = event
                        msg = f"{df.index[bar_idx]} | price={price:.2f} | cross={cross} | macd={macd:.5f} | signal={signal:.5f} | bar={bar_idx}"
                        q.put((df.index[bar_idx], "LOG", msg))
                        break

                # 🔹 최근 bar 중 BUY/SELL 시그널 확인 (dict/tuple 모두 처리)  # ★
                trade_signal = None
                cross = macd = signal = None
                parsed_evt = None  # ★ dict 형태로 정규화

                for event in reversed(trade_events):
                    if isinstance(event, dict):  # ★ 새 포맷
                        bar_idx = event.get("bar")
                        etype = event.get("type")
                        if bar_idx is None or etype not in ("BUY", "SELL"):
                            continue
                        if bar_idx >= latest_bar - 2:
                            key = (bar_idx, etype)
                            if key in seen_signals:
                                continue
                            seen_signals.add(key)
                            trade_signal = etype
                            parsed_evt = event
                            macd = event.get("macd")
                            signal = event.get("signal")
                            cross = event.get("reason")  # ★ dict의 reason 사용
                            break
                    else:
                        # ★ 구 포맷 (bar, "BUY"/"SELL", reason, macd, signal, price)
                        try:
                            bar_idx = event[0]
                            etype = event[1]
                        except Exception:
                            continue
                        if bar_idx >= latest_bar - 2 and etype in ("BUY", "SELL"):
                            key = (bar_idx, etype)
                            if key in seen_signals:
                                continue
                            seen_signals.add(key)
                            trade_signal = etype
                            # tuple → dict로 정규화  # ★
                            parsed_evt = {
                                "bar": bar_idx,
                                "type": etype,
                                "reason": event[2] if len(event) > 2 else "",
                                "macd": event[3] if len(event) > 3 else None,
                                "signal": event[4] if len(event) > 4 else None,
                                "price": event[5] if len(event) > 5 else latest_price,
                                "timestamp": df.index[bar_idx] if bar_idx is not None else latest_index,
                                # 선택 필드 (없을 수 있음)
                                "entry_price": None, "entry_bar": None,
                                "bars_held": None, "tp": None, "sl": None,
                                "highest": None, "ts_pct": None, "ts_armed": None,
                            }
                            cross = parsed_evt["reason"]
                            macd = parsed_evt["macd"]
                            signal = parsed_evt["signal"]
                            break

                if not trade_signal:
                    logger.info(
                        f"🔍 최근 BUY/SELL 시그널 없음 → 패스, in_position={in_position}, entry_price={entry_price}"
                    )
                    continue

                # ★ 보기 좋은 설명 로그(시그널 요약) 전송
                evt = parsed_evt or {}
                desc = (
                    f"{evt.get('timestamp', latest_index)} | {evt.get('type', trade_signal)}"
                    f"{'(' + (evt.get('reason','') or '') + ')' if evt.get('reason') else ''} | "
                    f"price={evt.get('price', latest_price):,.2f} "
                    f"entry={evt.get('entry_price','-')} held={evt.get('bars_held','-')} "
                    f"macd={evt.get('macd','-')} signal={evt.get('signal','-')} "
                    f"TP={evt.get('tp','-')} SL={evt.get('sl','-')} "
                    f"TS={'ON' if evt.get('ts_armed') else 'OFF' if evt.get('ts_armed') is not None else '-'} "
                    f"high={evt.get('highest','-')}"
                )
                q.put((evt.get("timestamp", latest_index), "LOG", f"🧾 {desc}"))  # ★

                coin_balance = trader._coin_balance(params.upbit_ticker)
                logger.info(f"📊 현재 잔고: {coin_balance:.8f}")

                # 🔹 매수 로직
                if trade_signal == "BUY" and coin_balance < 1e-6:
                    result = trader.buy_market(
                        latest_price, params.upbit_ticker, ts=latest_index
                    )
                    if result:
                        logger.info(f"✅ 실매수 완료: {result}")
                        q.put(
                            (
                                latest_index,
                                "BUY",
                                result["qty"],
                                result["price"],
                                cross,
                                macd,
                                signal,
                            )
                        )
                        in_position = True
                        entry_price = result["price"]

                # 🔹 매도 로직
                elif trade_signal == "SELL" and coin_balance >= 1e-6:
                    result = trader.sell_market(
                        coin_balance,
                        ticker=params.upbit_ticker,
                        price=latest_price,
                        ts=latest_index,
                    )
                    if result:
                        logger.info(f"✅ 실매도 완료: {result}")
                        q.put(
                            (
                                latest_index,
                                "SELL",
                                result["qty"],
                                result["price"],
                                cross,
                                macd,
                                signal,
                            )
                        )
                        in_position = False
                        entry_price = None

                logger.info(
                    f"💡 실거래 포지션 상태: in_position={in_position} | entry_price={entry_price}"
                )
    except Exception:
        logger.exception("❌ run_live_loop 예외 발생:")
        q.put(("EXCEPTION", *sys.exc_info()))

    finally:
        logger.info("🧹 run_live_loop 종료 완료 → stop_event set")
        stop_event.set()
