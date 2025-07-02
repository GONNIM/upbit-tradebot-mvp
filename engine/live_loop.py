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
) -> None:
    """Live Trading Worker: Stream candles → Backtest → Process signal → Put events in queue."""
    from streamlit.runtime.scriptrunner import add_script_run_ctx

    add_script_run_ctx(threading.current_thread())

    # ✅ 전략 클래스 정의 (동적으로)
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

                # ✅ 전략 실행
                bt = Backtest(
                    df,
                    strategy_cls,
                    cash=params.cash,
                    commission=params.commission,
                    exclusive_orders=True,
                )
                bt.run()
                logger.info("LiveStrategy Backtest 실행 완료")

                signal_events = MACDStrategy.signal_events
                latest_index = df.index[-1]
                latest_price = df.Close.iloc[-1]

                # ✅ LOG 메시지 → Queue 전송
                for event in signal_events:
                    if event[1] == "LOG":
                        ts, _, cross, macd, signal, price = event
                        msg = f"{df.index[ts]} | price={price} | cross={cross} | macd={macd} | signal={signal} | bar={ts}"
                        q.put((df.index[ts], "LOG", msg))

                # ✅ 최근 시그널이 마지막 캔들에 있는지 확인
                trade_signal = None
                cross = macd = signal = None

                for event in reversed(signal_events):
                    if event[0] == len(df) - 1:
                        trade_signal = event[1]
                        cross, macd, signal = event[2], event[3], event[4]
                        break

                if trade_signal is None:
                    continue

                coin_balance = trader._coin_balance(params.upbit_ticker)

                if trade_signal == "BUY" and coin_balance == 0:
                    result = trader.buy_market(
                        latest_price, params.upbit_ticker, ts=latest_index
                    )
                    if result:
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

                elif trade_signal == "SELL" and coin_balance > 0:
                    result = trader.sell_market(
                        coin_balance,
                        ticker=params.upbit_ticker,
                        price=latest_price,
                        ts=latest_index,
                    )
                    if result:
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

    except Exception:
        logger.exception("❌ run_live_loop 예외 발생:")
        q.put(("EXCEPTION", *sys.exc_info()))

    finally:
        logger.info("🧹 run_live_loop 종료 완료 → stop_event set")
        stop_event.set()
