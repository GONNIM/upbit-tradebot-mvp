from __future__ import annotations
import pyupbit
import pandas as pd
import time
import logging
import random
import gc
import psutil
import os
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


# --------- 시간/경계 유틸 (KST naive로 일관) ---------
_IV_MIN = {
    "minute1": 1, "minute3": 3, "minute5": 5, "minute10": 10, "minute15": 15,
    "minute30": 30, "minute60": 60, "day": 1440,
}

def _iv_min(interval: str) -> int:
    return _IV_MIN.get(interval, 10)

def _now_kst_naive() -> datetime:
    # KST 타임존 시각을 tz-naive로 반환 (벽시계)
    # 시스템이 KST가 아니라도, 'KST로 동작'한다고 가정할 때 적절
    # (진짜 KST 변환이 필요하면 pytz/zoneinfo로 변환 후 tz 제거)
    return datetime.now().replace(second=datetime.now().second, microsecond=0)

def _floor_boundary(dt: datetime, interval: str) -> datetime:
    if interval == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    iv = _iv_min(interval)
    m = (dt.minute // iv) * iv
    return dt.replace(minute=m, second=0, microsecond=0)

def _next_boundary(dt: datetime, interval: str) -> datetime:
    if interval == "day":
        nxt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        if dt >= nxt:
            nxt += timedelta(days=1)
        return nxt
    iv = _iv_min(interval)
    m = (dt.minute // iv + 1) * iv
    add_h = m // 60
    m = m % 60
    h = (dt.hour + add_h) % 24
    nxt = dt.replace(hour=h, minute=m, second=0, microsecond=0)
    if dt.hour + add_h >= 24:
        nxt += timedelta(days=1)
    return nxt

def _fmt_to_param(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --------- 메모리 유틸 ---------
def _optimize_dataframe_memory(old_df, new_data, max_length):
    try:
        if len(old_df) >= max_length:
            old_df = old_df.iloc[-(max_length - 10):].copy()
        combined = pd.concat([old_df, new_data], ignore_index=False)
        result = combined.drop_duplicates().sort_index().iloc[-max_length:]
        memory_usage_mb = result.memory_usage(deep=True).sum() / 1024 / 1024
        if memory_usage_mb > 10:
            logger.warning(f"⚠️ DataFrame 메모리 사용량 과다: {memory_usage_mb:.2f}MB")
        return result
    except Exception as e:
        logger.error(f"❌ DataFrame 최적화 실패: {e}")
        return pd.concat([old_df, new_data]).drop_duplicates().sort_index().iloc[-max_length:]

def _force_memory_cleanup():
    try:
        collected = gc.collect()
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        logger.info(f"🧹 메모리 정리 완료: 객체 {collected}개 수집, 현재 메모리: {memory_mb:.1f}MB")
        if memory_mb > 500:
            logger.warning(f"⚠️ 메모리 사용량 높음: {memory_mb:.1f}MB - 시스템 모니터링 필요")
    except Exception as e:
        logger.error(f"❌ 메모리 정리 실패: {e}")


# --------- 메인 스트림 ---------
def stream_candles(
    ticker: str,
    interval: str,
    q=None,
    max_retry: int = 5,
    retry_wait: int = 3,
    stop_event=None,
    max_length: int = 500,
):
    def _log(level: str, msg: str):
        (logger.warning if level == "WARN" else logger.error if level == "ERROR" else logger.info)(msg)
        if q:
            # 항상 3-튜플 유지
            prefix = "⚠️" if level == "WARN" else "❌" if level == "ERROR" else "ℹ️"
            q.put((time.time(), "LOG", f"{prefix} {msg}"))

    def standardize_ohlcv(df):
        if df is None or df.empty:
            raise ValueError(f"OHLCV 데이터 수집 실패: {ticker}, {interval}")
        df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
        if "value" in df.columns:
            df = df.drop(columns=["value"])
        # tz-aware가 오면 tz 제거하여 naive로 일관
        idx = pd.to_datetime(df.index)
        try:
            # pandas >=2: DatetimeIndex.tz is property
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_convert(None)
        except Exception:
            pass
        df.index = idx
        return df.dropna().sort_index()

    # ---- 초기 로드: 막 닫힌 경계까지 ----
    base_delay = retry_wait
    df = None
    now = _now_kst_naive()
    bar_close = _floor_boundary(now, interval)
    to_param = _fmt_to_param(bar_close)

    for attempt in range(1, max_retry + 1):
        if stop_event and stop_event.is_set():
            _log("WARN", "stream_candles 중단됨: 초기 수집 중 stop_event 감지")
            return
        try:
            df = pyupbit.get_ohlcv(ticker, interval=interval, count=max_length, to=to_param)
            if df is not None and not df.empty:
                break
        except Exception as e:
            _log("ERROR", f"[초기] API 예외 발생: {e}")

        delay = min(base_delay * (2 ** (attempt - 1)), 60) + random.uniform(0, 5)
        _log("WARN", f"[초기] API 실패 ({attempt}/{max_retry}), {delay:.1f}초 후 재시도")
        time.sleep(delay)

    if df is None or df.empty:
        _log("ERROR", "[초기] 데이터 수집 실패, 빈 DataFrame으로 시작")
        df = pd.DataFrame(columns=["Open","High","Low","Close","Volume"])
        df.index = pd.to_datetime([])

    df = standardize_ohlcv(df).drop_duplicates()
    yield df

    last_open = df.index[-1]  # 우리가 가진 마지막 bar_open (tz-naive)

    # ---- 실시간 루프: 경계 동기화 → 닫힌 봉 조회 → 갭 백필 ----
    JITTER = 0.7
    while not (stop_event and stop_event.is_set()):
        now = _now_kst_naive()
        next_close = _next_boundary(now, interval)
        sleep_sec = max(0.0, (next_close - now).total_seconds() + JITTER)
        time.sleep(sleep_sec)

        # 막 닫힌 봉의 open
        iv = _iv_min(interval)
        boundary_open = next_close - timedelta(minutes=iv)  # 둘 다 tz-naive

        # 중간 누락분 계산(분 단위)
        gap = int((boundary_open - last_open).total_seconds() // (iv * 60))
        need = max(1, min(gap, 200))

        # 재시도 루프
        new = None
        for attempt in range(1, max_retry + 1):
            if stop_event and stop_event.is_set():
                _log("WARN", "stream_candles 중단됨: 실시간 루프 중 stop_event 감지")
                return
            try:
                new = pyupbit.get_ohlcv(ticker, interval=interval, count=need, to=_fmt_to_param(next_close))
                if new is not None and not new.empty:
                    break
            except Exception as e:
                _log("ERROR", f"[실시간] API 예외: {e}")
            delay = min(base_delay * (2 ** (attempt - 1)), 30) + random.uniform(0, 2)
            _log("WARN", f"[실시간] API 실패 ({attempt}/{max_retry}), {delay:.1f}초 후 재시도")
            time.sleep(delay)
        else:
            backoff = min(30 + random.uniform(0, 10), 300)
            _log("ERROR", f"[실시간] API 연결 실패, {backoff:.1f}초 후 재시도...")
            time.sleep(backoff)
            continue

        new = standardize_ohlcv(new).drop_duplicates()
        # 우리가 가진 마지막 이후 것만
        new = new[new.index > last_open]
        if new.empty:
            continue

        old_df = df
        df = _optimize_dataframe_memory(df, new, max_length)
        del old_df

        last_open = df.index[-1]
        # 사용자 혼란 방지용 동기화 로그 (bar_open / bar_close 명시)
        if q:
            last_close = last_open + timedelta(minutes=iv)
            run_at = datetime.now()
            q.put((
                time.time(),
                "LOG",
                f"⏱ run_at={run_at:%Y-%m-%d %H:%M:%S} | bar_open={last_open} | bar_close={last_close} "
            ))

        # 주기적 GC
        if hasattr(_optimize_dataframe_memory, "last_gc_time"):
            if time.time() - _optimize_dataframe_memory.last_gc_time > 300:
                _force_memory_cleanup()
                _optimize_dataframe_memory.last_gc_time = time.time()
        else:
            _optimize_dataframe_memory.last_gc_time = time.time()

        yield df


_INTERVAL_MAP = {
    "minute1": "minute1",
    "minute3": "minute3",
    "minute5": "minute5",
    "minute10": "minute10",
    "minute15": "minute15",
    "minute30": "minute30",
    "minute60": "minute60",
    "minute240": "minute240",
    "day": "day",
    "week": "week",
}

def get_ohlcv_once(ticker: str, interval_code: str, count: int = 500) -> pd.DataFrame:
    """
    대시보드용 원샷 OHLCV.
    반환: columns = [Open, High, Low, Close, Volume], DatetimeIndex(UTC 기준으로 tz-aware)
    """
    interval = _INTERVAL_MAP.get(interval_code, "minute1")
    df = pyupbit.get_ohlcv(ticker=ticker, interval=interval, count=count)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])
    # pyupbit는 보통 tz-naive → UTC로 가정 후 tz-aware로 변환
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open","high","low","close","volume"]].rename(
        columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}
    )
