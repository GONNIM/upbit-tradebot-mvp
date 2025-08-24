import pyupbit
import pandas as pd
import time
import streamlit as st
import logging
import random
import gc
import psutil
import os


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

def _optimize_dataframe_memory(old_df, new_data, max_length):
    """
    🧠 24시간 운영: 메모리 효율적 DataFrame 관리
    """
    try:
        # 🔄 기존 방식보다 메모리 효율적인 병합
        if len(old_df) >= max_length:
            # 오래된 데이터 제거 (메모리 절약)
            old_df = old_df.iloc[-(max_length-10):].copy()
        
        # 🔗 효율적 병합
        combined = pd.concat([old_df, new_data], ignore_index=False)
        result = combined.drop_duplicates().sort_index().iloc[-max_length:]
        
        # 📊 메모리 사용량 모니터링
        memory_usage_mb = result.memory_usage(deep=True).sum() / 1024 / 1024
        if memory_usage_mb > 10:  # 10MB 초과 시 경고
            logger.warning(f"⚠️ DataFrame 메모리 사용량 과다: {memory_usage_mb:.2f}MB")
            
        return result
        
    except Exception as e:
        logger.error(f"❌ DataFrame 최적화 실패: {e}")
        # 폴백: 기존 방식 사용
        return pd.concat([old_df, new_data]).drop_duplicates().sort_index().iloc[-max_length:]


def _force_memory_cleanup():
    """
    🧹 24시간 운영: 강제 메모리 정리
    """
    try:
        # Python GC 강제 실행
        collected = gc.collect()
        
        # 시스템 메모리 사용량 체크
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        logger.info(f"🧹 메모리 정리 완료: 객체 {collected}개 수집, 현재 메모리: {memory_mb:.1f}MB")
        
        # 메모리 사용량이 500MB 초과 시 경고
        if memory_mb > 500:
            logger.warning(f"⚠️ 메모리 사용량 높음: {memory_mb:.1f}MB - 시스템 모니터링 필요")
            
    except Exception as e:
        logger.error(f"❌ 메모리 정리 실패: {e}")


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

    # ✅ 초기 데이터 수집 (지수 백오프 전략 적용)
    retry_cnt = 0
    df = None
    base_delay = retry_wait
    
    while retry_cnt < max_retry:
        if stop_event and stop_event.is_set():
            log_warning("stream_candles 중단됨: 초기 수집 중 stop_event 감지")
            return
            
        try:
            df = pyupbit.get_ohlcv(ticker, interval=interval, count=max_length)
            if df is not None and not df.empty:
                break
        except Exception as e:
            log_error(f"[초기] API 예외 발생: {e}")
            
        retry_cnt += 1
        # 🔄 지수 백오프: 3초, 6초, 12초, 24초, 48초...
        delay = min(base_delay * (2 ** (retry_cnt - 1)), 60) + random.uniform(0, 5)
        log_warning(f"[초기] API 실패 ({retry_cnt}/{max_retry}), {delay:.1f}초 후 재시도")
        time.sleep(delay)
        
    if df is None or df.empty:
        # 🔄 초기 실패 시 빈 DataFrame으로 시작 (엔진 중단 방지)
        log_error("[초기] 데이터 수집 실패, 빈 DataFrame으로 시작")
        df = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        df.index = pd.to_datetime([])

    df = standardize_ohlcv(df)
    df = df.drop_duplicates()
    yield df

    last_candle_time = df.index[-1]

    # ✅ 실시간 루프
    while not (stop_event and stop_event.is_set()):
        time.sleep(max(secs[interval] // 3, 3))

        retry_cnt = 0
        new = None
        base_delay = retry_wait
        
        while retry_cnt < max_retry:
            if stop_event and stop_event.is_set():
                log_warning("stream_candles 중단됨: 실시간 루프 중 stop_event 감지")
                return
                
            try:
                new = pyupbit.get_ohlcv(ticker, interval=interval, count=1)
                if new is not None and not new.empty:
                    break
            except Exception as e:
                log_error(f"[실시간] API 예외: {e}")
                
            retry_cnt += 1
            # 🔄 지수 백오프 적용
            delay = min(base_delay * (2 ** (retry_cnt - 1)), 30) + random.uniform(0, 2)
            log_warning(f"[실시간] API 실패 ({retry_cnt}/{max_retry}), {delay:.1f}초 후 재시도")
            time.sleep(delay)
        else:
            # 🔄 24시간 운영: API 실패 시 엔진 중단 방지
            # 지수 백오프 전략으로 대기 후 재시도
            backoff_delay = min(30 + random.uniform(0, 10), 300)  # 30~300초 대기
            log_error(f"[실시간] API 연결 실패, {backoff_delay:.1f}초 후 재시도...")
            time.sleep(backoff_delay)
            continue  # return 대신 continue로 엔진 유지

        new = standardize_ohlcv(new)
        new = new.drop_duplicates()
        new_candle_time = new.index[-1]

        if new_candle_time == last_candle_time:
            continue  # 아직 새 캔들 생성 안 됨

        last_candle_time = new_candle_time
        
        # 📊 24시간 운영: 메모리 효율적 DataFrame 관리
        old_df = df
        df = _optimize_dataframe_memory(df, new, max_length)
        
        # 🗑️ 이전 DataFrame 명시적 삭제
        del old_df
        
        # 🔄 주기적 메모리 정리 (5분마다)
        if hasattr(_optimize_dataframe_memory, 'last_gc_time'):
            if time.time() - _optimize_dataframe_memory.last_gc_time > 300:
                _force_memory_cleanup()
                _optimize_dataframe_memory.last_gc_time = time.time()
        else:
            _optimize_dataframe_memory.last_gc_time = time.time()
        
        yield df
