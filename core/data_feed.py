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

from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)


# --------- 시간/경계 유틸 (KST naive로 일관) ---------
_IV_MIN = {
    "minute1": 1,
    "minute3": 3,
    "minute5": 5,
    "minute10": 10,
    "minute15": 15,
    "minute30": 30,
    "minute60": 60,
    "day": 1440,
}


# 디터미니즘 체크 로그 헬퍼
def log_det(df: pd.DataFrame, tag: str):
    """
    df가 현재 동일한 봉 집합인지 빠르게 검증하기 위한 로그.
    - rows/first/last + OHLCV 체크섬을 남긴다.
    - tag: 호출 지점 구분용(ex: PRE_INIT, LOOP_MERGED, ONCE_BEFORE_RETURN)
    """
    if df is None or df.empty:
        logger.info(f"[DET] {tag} | rows=0 (empty)")
        return
    try:
        rows = len(df)
        first_i, last_i = df.index[0], df.index[-1]
        # OHLCV만 사용, 소수 8자리 반올림 후 문자열 → 해시
        payload = df[["Open","High","Low","Close","Volume"]].round(8).to_csv(index=True, header=False)
        checksum = hash(payload)  # 파이썬 내장 해시(세션마다 달라질 수 있음, 같은 프로세스 비교용)
        logger.info(f"[DET] {tag} | rows={rows} | first={first_i} | last={last_i} | checksum={checksum}")
    except Exception as e:
        logger.warning(f"[DET] {tag} | logging failed: {e}")


def _iv_min(interval: str) -> int:
    return _IV_MIN.get(interval, 10)

# v1.2025.10.18.2031
def _now_kst_naive() -> datetime:
    """
    ✅ 시스템 로컬타임(UTC 등)에 의존하지 않고 KST 시각을 tz-aware로 만든 뒤 tz 제거.
    - 모든 바 경계 계산을 'KST-naive'로 통일하기 위함.
    """
    kst_now = datetime.now(tz=ZoneInfo("Asia/Seoul"))
    return kst_now.replace(second=0, microsecond=0).replace(tzinfo=None)

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
    user_id: str = None,  # Phase 2: 캐시 사용을 위한 user_id
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

        before_count = len(df)
        _log("INFO", f"[standardize] 입력 데이터: {before_count}개, index type={type(df.index)}, tz={getattr(df.index, 'tz', 'N/A')}")

        df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
        if "value" in df.columns:
            df = df.drop(columns=["value"])

        # 인덱스 tz 정규화: UTC → KST naive로 통일
        idx = pd.to_datetime(df.index)
        try:
            # ✅ 수정: 조건을 반대로 (tz가 None이면 = naive이면)
            if getattr(idx, "tz", None) is None:
                # tz-naive라면 UTC로 간주하고 localize
                idx = idx.tz_localize("UTC")
                _log("INFO", f"[standardize] tz-naive 감지 → UTC로 localize")
            else:
                _log("INFO", f"[standardize] 이미 tz-aware (tz={idx.tz})")

            # KST로 변환 후 tz 제거하여 전체 파이프라인을 'KST-naive'로 통일
            idx = idx.tz_convert("Asia/Seoul").tz_localize(None)
            _log("INFO", f"[standardize] KST naive로 변환 완료")
        except Exception as e:
            # 예외 발생 시 상세 로그
            _log("ERROR", f"[standardize] 타임존 변환 실패: {e}")
            # 변환 실패 시에도 최소한 정렬은 수행할 수 있도록 idx 그대로 사용

        df.index = idx

        # dropna 전 NaN 개수 확인
        na_counts = df.isna().sum()
        if na_counts.any():
            _log("WARN", f"[standardize] NaN 발견: {na_counts[na_counts > 0].to_dict()}")

        # 정렬 후 중복 제거 (dropna는 나중에)
        df = df.sort_index()
        before_dedup = len(df)
        df = df.loc[~df.index.duplicated(keep="last")]
        after_dedup = len(df)

        if before_dedup > after_dedup:
            _log("WARN", f"[standardize] 중복 제거: {before_dedup - after_dedup}개 삭제 ({before_dedup} → {after_dedup})")

        # NaN 제거
        df = df.dropna()
        after_dropna = len(df)

        if after_dedup > after_dropna:
            _log("WARN", f"[standardize] NaN 제거: {after_dedup - after_dropna}개 삭제 ({after_dedup} → {after_dropna})")

        _log("INFO", f"[standardize] 최종 출력: {after_dropna}개 (손실: {before_count - after_dropna}개, {100*(before_count-after_dropna)/before_count:.1f}%)")

        return df

    # ★ 초기 히스토리 수집용 헬퍼
    def _fetch_initial_history(to_param: str) -> pd.DataFrame:
        """
        Upbit는 분봉 기준 한 번에 최대 200개만 반환하므로,
        max_length가 200을 넘는 경우 여러 번 나눠서 과거 히스토리를 모은다.
        - MACD/EMA를 HTS 수준으로 맞추기 위한 긴 히스토리(예: 3분봉 1500~2000개) 확보용.
        """
        iv_min = _iv_min(interval)
        remaining = max_length
        current_to = to_param
        chunks: list[pd.DataFrame] = []
        base_delay_local = retry_wait
        total_requested = max_length
        api_calls = 0

        _log("INFO", f"[초기-multi] 히스토리 수집 시작: max_length={max_length}, interval={interval}")

        while remaining > 0:
            if stop_event and stop_event.is_set():
                collected = sum(len(c) for c in chunks)
                _log("WARN", f"[초기-multi] stop_event 감지 → 수집 중단 (collected={collected}/{total_requested})")
                break

            per_call = min(200, remaining)  # Upbit 분봉 최대 200개
            df_part = None
            api_calls += 1

            for attempt in range(1, max_retry + 1):
                try:
                    _log("INFO", f"[초기-multi] API 호출 #{api_calls}: count={per_call}, to={current_to}")
                    df_part = pyupbit.get_ohlcv(
                        ticker,
                        interval=interval,
                        count=per_call,
                        to=current_to,
                    )
                    if df_part is not None and not df_part.empty:
                        _log("INFO", f"[초기-multi] API 응답 성공: {len(df_part)}개 수신")
                        break
                    else:
                        _log("WARN", f"[초기-multi] API 응답이 비어있음 (attempt {attempt}/{max_retry})")
                except Exception as e:
                    _log("ERROR", f"[초기-multi] API 예외 발생: {e} (attempt {attempt}/{max_retry})")

                # Upbit API rate limit 대응: 호출 간 최소 0.1초 딜레이
                delay = min(base_delay_local * (2 ** (attempt - 1)), 60) + random.uniform(0.1, 1.0)
                _log("WARN", f"[초기-multi] API 재시도 대기: {delay:.1f}초")
                time.sleep(delay)
            else:
                # max_retry 실패 시 - 부분 수집 데이터라도 반환하도록 개선
                collected = sum(len(c) for c in chunks)
                _log("ERROR", f"[초기-multi] API 연속 실패 (collected={collected}/{total_requested})")
                # break 대신 경고만 남기고 수집된 데이터 반환
                break

            if df_part is None or df_part.empty:
                collected = sum(len(c) for c in chunks)
                _log("WARN", f"[초기-multi] 빈 응답으로 수집 종료 (collected={collected}/{total_requested})")
                break

            chunks.append(df_part)
            got = len(df_part)
            remaining -= got

            collected_so_far = sum(len(c) for c in chunks)
            _log("INFO", f"[초기-multi] 진행: {collected_so_far}/{total_requested} ({100*collected_so_far/total_requested:.1f}%)")

            if got < per_call:
                # Upbit API가 요청량보다 적게 반환 = 더 이상 과거 데이터 없음
                _log("WARN", f"[초기-multi] API가 요청량보다 적게 반환 (got={got}, requested={per_call}) → 과거 데이터 소진")
                break

            # 다음 요청용 'to'는 이번 기준시간에서 got*interval 만큼 과거로 이동
            try:
                dt_to = datetime.strptime(current_to, "%Y-%m-%d %H:%M:%S")
                dt_to -= timedelta(minutes=iv_min * got)
                current_to = _fmt_to_param(dt_to)
            except Exception as e:
                # 파싱 실패 시 추가 페이징은 하지 않고 종료
                collected = sum(len(c) for c in chunks)
                _log("ERROR", f"[초기-multi] 날짜 파싱 실패: {e} (collected={collected}/{total_requested})")
                break

            # API rate limit 준수: 호출 간 0.1초 딜레이
            time.sleep(0.1)

        if not chunks:
            _log("ERROR", f"[초기-multi] 수집 실패: 데이터 없음")
            return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])

        raw = pd.concat(chunks)
        final_count = len(raw)
        success_rate = 100 * final_count / total_requested if total_requested > 0 else 0
        _log("INFO", f"[초기-multi] 수집 완료: {final_count}/{total_requested} ({success_rate:.1f}%), API 호출 {api_calls}회")

        return raw
    
    # ---- 초기 로드: 막 닫힌 경계까지 ----
    base_delay = retry_wait
    df = None
    now = _now_kst_naive()
    bar_close = _floor_boundary(now, interval)
    to_param = _fmt_to_param(bar_close)

    # ★ Phase 2: DB 캐시 우선 확인
    cache_used = False
    if user_id:
        try:
            from services.db import load_candle_cache
            cached_df = load_candle_cache(user_id, ticker, interval, max_length)

            if cached_df is not None and len(cached_df) >= max_length * 0.9:  # 90% 이상이면 사용
                df = cached_df
                cache_used = True
                _log("INFO", f"[CACHE-HIT] {len(df)} candles loaded from DB cache (skip API)")
            elif cached_df is not None:
                _log("INFO", f"[CACHE-PARTIAL] {len(cached_df)} candles in cache (insufficient, will fetch from API)")
        except Exception as e:
            _log("WARN", f"[CACHE] Load failed, will use API: {e}")

    # ★ 캐시 미스 또는 부족: API 호출
    if df is None:
        _log("INFO", f"[초기] 데이터 수집 시작: ticker={ticker}, interval={interval}, max_length={max_length}")

        if max_length <= 200:
            for attempt in range(1, max_retry + 1):
                if stop_event and stop_event.is_set():
                    _log("WARN", "stream_candles 중단됨: 초기 수집 중 stop_event 감지")
                    return
                try:
                    _log("INFO", f"[초기] API 단일 호출: count={max_length}, to={to_param}")
                    df = pyupbit.get_ohlcv(ticker, interval=interval, count=max_length, to=to_param)
                    if df is not None and not df.empty:
                        _log("INFO", f"[초기] API 응답 성공: {len(df)}개 수신")
                        break
                except Exception as e:
                    _log("ERROR", f"[초기] API 예외 발생: {e}")

                delay = min(base_delay * (2 ** (attempt - 1)), 60) + random.uniform(0, 5)
                _log("WARN", f"[초기] API 실패 ({attempt}/{max_retry}), {delay:.1f}초 후 재시도")
                time.sleep(delay)
        else:
            # ★ MACD/EMA 안정화를 위해 긴 히스토리(max_length) 확보
            _log("INFO", f"[초기] max_length > 200 → multi-fetch 모드 사용")
            df = _fetch_initial_history(to_param)

        # ★ Phase 2: API 호출 후 DB에 저장
        if user_id and df is not None and not df.empty:
            try:
                from services.db import save_candle_cache
                save_candle_cache(user_id, ticker, interval, df)
            except Exception as e:
                _log("WARN", f"[CACHE] Save failed (ignored): {e}")

    if df is None or df.empty:
        _log("ERROR", "[초기] 데이터 수집 실패, 빈 DataFrame으로 시작")
        df = pd.DataFrame(columns=["Open","High","Low","Close","Volume"])
        df.index = pd.to_datetime([])
    else:
        _log("INFO", f"[초기] 수집된 원본 데이터: {len(df)}개")

    df = standardize_ohlcv(df).drop_duplicates()
    final_len = len(df)
    _log("INFO", f"[초기] standardize 후 최종 데이터: {final_len}개 (요청: {max_length}개, 달성률: {100*final_len/max_length if max_length > 0 else 0:.1f}%)")

    if final_len < max_length * 0.8:
        _log("WARN", f"⚠️ 데이터 부족: {final_len}/{max_length} ({100*final_len/max_length:.1f}%) - Upbit API 제약 또는 과거 데이터 부족 가능성")

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

        # 중복/정렬은 _optimize_dataframe_memory 내부에서 처리되지만
        # 혹시 남은 중복에 대해 최신 값 우선으로 한 번 더 보정
        # df = _optimize_dataframe_memory(df, new, max_length).loc[~_optimize_dataframe_memory(df, new, max_length).index.duplicated(keep="last")].sort_index()
        # ✅ 한 번만 계산한 결과를 재사용하여 중복 호출/레이스 위험 제거
        tmp = _optimize_dataframe_memory(df, new, max_length)
        df = tmp.loc[~tmp.index.duplicated(keep="last")].sort_index()
        del tmp

        # 실시간 병합 후 DET 로깅 (로컬/서버 비교 핵심 지점)
        log_det(df, "LOOP_MERGED")

        # ★ Phase 2: 실시간 데이터도 DB에 저장 (점진적 히스토리 누적)
        if user_id and not new.empty:
            try:
                from services.db import save_candle_cache
                save_candle_cache(user_id, ticker, interval, new)
            except Exception as e:
                # 로그만 남기고 메인 루프는 계속 진행
                pass

        last_open = df.index[-1]
        # 사용자 혼란 방지용 동기화 로그 (bar_open / bar_close 명시)
        if q:
            last_close = last_open + timedelta(minutes=iv)
            # run_at = datetime.now()
            run_at = _now_kst_naive()  # ✅ KST-naive로 기록 통일
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

# get_ohlcv_once() 주석 및 인덱스 정규화 수정
def get_ohlcv_once(ticker: str, interval_code: str, count: int = 500) -> pd.DataFrame:
    """
    대시보드용 원샷 OHLCV.
    ✅ 반환: columns = [Open, High, Low, Close, Volume], DatetimeIndex = 'KST-naive' (stream과 동일 기준)
    """
    interval = _INTERVAL_MAP.get(interval_code, "minute1")
    df = pyupbit.get_ohlcv(ticker=ticker, interval=interval, count=count)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])

    # pyupbit 인덱스가 tz-naive(=UTC)일 가능성 높음 → KST-naive로 통일
    if isinstance(df.index, pd.DatetimeIndex):
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is None:
            idx = idx.tz_localize("UTC")
        idx = idx.tz_convert("Asia/Seoul").tz_localize(None)
        df.index = idx

    out = df[["open","high","low","close","volume"]].rename(
        columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}
    )

    try:
        log_det(out, "ONCE_BEFORE_RETURN")
    except Exception:
        pass

    return out
