import pyupbit
import pandas as pd
import time
import streamlit as st
import logging


secs = {
    "minute1": 10,
    # "minute1": 60,
    "minute3": 180,
    "minute5": 300,
    "minute10": 600,
    "minute15": 900,
    "minute30": 1800,
    "minute60": 3600,
    "day": 86400,
}

logger = logging.getLogger(__name__)


def stream_candles(
    ticker: str,
    interval: str,
    q=None,
    max_retry: int = 5,
    retry_wait: int = 3,
    stop_event=None,
    max_length: int = 500,
):
    def standardize_ohlcv(df):
        if df is None or df.empty:
            raise ValueError(f"OHLCV 데이터 수집 실패: {ticker}, {interval}")
        df = df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        if "value" in df.columns:
            df = df.drop(columns=["value"])
        df.index = pd.to_datetime(df.index)
        return df.dropna().sort_index()

    def log_warning(msg):
        logger.warning(msg)
        if q:
            q.put(("WARNING", msg))

    def log_error(msg):
        logger.error(msg)
        if q:
            q.put(("ERROR", msg))

    # ✅ 최초 수집
    retry_cnt = 0
    df = None
    while retry_cnt < max_retry:
        if stop_event and stop_event.is_set():
            log_warning("stream_candles 중단됨: 초기 수집 중 stop_event 감지")
            return
        df = pyupbit.get_ohlcv(ticker, interval=interval, count=max_length)
        if df is not None and not df.empty:
            break
        retry_cnt += 1
        log_warning(f"[초기] pyupbit.get_ohlcv 실패 ({retry_cnt}/{max_retry})")
        time.sleep(retry_wait)
    else:
        log_error("[초기] pyupbit.get_ohlcv 최종 실패")
        return

    df = standardize_ohlcv(df)
    df = df.drop_duplicates()
    yield df

    last_candle_time = df.index[-1]

    # ✅ 실시간 루프
    while not (stop_event and stop_event.is_set()):
        time.sleep(max(secs[interval] // 3, 3))

        retry_cnt = 0
        new = None
        while retry_cnt < max_retry:
            if stop_event and stop_event.is_set():
                log_warning("stream_candles 중단됨: 실시간 루프 중 stop_event 감지")
                return
            new = pyupbit.get_ohlcv(ticker, interval=interval, count=1)
            if new is not None and not new.empty:
                break
            retry_cnt += 1
            log_warning(f"[실시간] pyupbit.get_ohlcv 실패 ({retry_cnt}/{max_retry})")
            time.sleep(retry_wait)
        else:
            log_error("[실시간] pyupbit.get_ohlcv 최종 실패")
            return

        new = standardize_ohlcv(new)
        new = new.drop_duplicates()
        new_candle_time = new.index[-1]

        if new_candle_time == last_candle_time:
            continue  # 아직 새 캔들 생성 안 됨

        last_candle_time = new_candle_time
        df = pd.concat([df, new]).drop_duplicates().sort_index().iloc[-max_length:]
        yield df
