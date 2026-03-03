from __future__ import annotations
import pyupbit
import pandas as pd
import time
import logging
import random
import gc
import psutil
import os
import math
from datetime import datetime, timedelta
from typing import Tuple, Optional
from zoneinfo import ZoneInfo

# Phase 2: Redis & WebSocket 통합
try:
    from core.redis_cache import get_redis_cache
    from core.websocket_feed import get_websocket_aggregator
    from config import REDIS_ENABLED, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
    from config import WEBSOCKET_ENABLED, CANDLE_CACHE_TTL
    PHASE2_AVAILABLE = True
except ImportError as e:
    PHASE2_AVAILABLE = False
    logging.warning(f"⚠️ [PHASE2] Redis/WebSocket 기능 비활성화: {e}")

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

# --------- JITTER 값 (interval별 차등 적용) ---------
# 봉 종가 확정 후 추가 대기 시간 (초)
# ⚠️ 중요: Upbit API는 봉 종가 확정 후 데이터 준비까지 시간이 걸림
# - 실제 테스트 결과: 웹사이트에는 데이터가 있지만 API는 4~5초 지연
# - 너무 짧으면: 데이터 누락 → 백필 실패 → 영구 누락 (치명적!)
# - 권장: 1분봉 3초, 3분봉 6초, 장기봉 8~15초
# - 실시간성보다 안정성 우선 (누락 방지가 최우선)
# - 백필 로직(5회 재시도)이 추가 안전장치 역할
JITTER_BY_INTERVAL = {
    "minute1": 15.0,  # 1분봉: 종가 확정 대기 (5.0 → 8.0 → 15.0) - REST API 지연 대응
    "minute3": 15.0,  # 3분봉: 종가 확정 대기 (8.0 → 15.0) - 임시 종가 회피
    "minute5": 15.0,  # 5분봉: 종가 확정 대기 (8.0 → 15.0) - 임시 종가 회피
    "minute10": 15.0, # 10분봉: 종가 확정 대기 (10.0 → 15.0) - 임시 종가 회피
    "minute15": 15.0, # 15분봉: 안정성 최우선 (8.0 → 10.0)
    "minute30": 15.0, # 30분봉: 안정성 최우선 (10.0 → 12.0)
    "minute60": 15.0, # 60분봉: 안정성 최우선 (10.0 → 12.0)
    "day": 15.0,      # 일봉: 실시간성보다 안정성 우선 (유지)
}

# --------- 필수 데이터 개수 정의 (목표치) ---------
# ⚠️ 주의: Upbit API는 과거 데이터 제약으로 목표치를 못 채울 수 있음
# → 절대 최소량(ABSOLUTE_MIN_CANDLES)만 충족하면 전략 실행 허용
REQUIRED_CANDLES = {
    "minute1": 2000,   # 1분봉: 2000개 (목표, Upbit 실제 제약: ~800개)
    "minute3": 1500,   # 3분봉: 1500개 (목표)
    "minute5": 1200,   # 5분봉: 1200개 (목표)
    "minute10": 1000,  # 10분봉: 1000개 (목표)
    "minute15": 800,   # 15분봉: 800개 (목표)
    "minute30": 600,   # 30분봉: 600개 (목표)
    "minute60": 500,   # 60분봉: 500개 (목표)
    "day": 400,        # 일봉: 400개 (목표)
}

# 절대 최소 캔들 개수 (이 값 미만이면 전략 시작 불가)
# - 전략별로 다른 최소값 적용
# ⚠️ Upbit API 제한: 최대 200개만 조회 가능
# - EMA 전략: 200개로 시작 (불완전하지만 실시간으로 데이터 축적)
ABSOLUTE_MIN_CANDLES = {
    "MACD": 600,  # MACD: 최대 파라미터 × 3
    "EMA": 195,   # EMA: Upbit API 제한 (200개 수집 → dropna/중복제거로 195개 이상, 실시간 축적)
}
ABSOLUTE_MIN_CANDLES_DEFAULT = 600  # 전략 미지정 시 기본값

# 목표 대비 경고 비율 (이 비율 미만이면 경고만 표시)
WARNING_RATIO = 0.5  # 50%


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


def _forward_fill_missing_candles(df, expected_last, interval_min, _log):
    """
    누락된 봉을 이전 봉 값으로 임시 채움 (최후의 수단).
    ⚠️ 주의: 이는 실제 시장 데이터가 아니며, 감사 로그에 명시적으로 표시됨.

    Args:
        df: 현재 DataFrame
        expected_last: 기대하는 마지막 봉의 타임스탬프
        interval_min: 봉 간격 (분)
        _log: 로그 함수

    Returns:
        pd.DataFrame: Forward Fill이 적용된 DataFrame
    """
    if df is None or df.empty:
        return df

    # 예상 인덱스 생성
    last_index = df.index[-1]

    try:
        expected_index_range = pd.date_range(
            start=last_index,
            end=expected_last,
            freq=f'{interval_min}min'
        )[1:]  # 첫 번째는 이미 있으므로 제외
    except Exception as e:
        _log("ERROR", f"[FORWARD-FILL] date_range 생성 실패: {e}")
        return df

    # 누락된 인덱스 찾기
    missing_indices = expected_index_range.difference(df.index)

    if len(missing_indices) == 0:
        return df

    _log("WARN",
        f"⚠️ [FORWARD-FILL] {len(missing_indices)}개 봉을 이전 봉 값으로 임시 채움 "
        f"(실제 시장 데이터 아님! 감사 로그 확인 필요)"
    )

    # 이전 봉 값으로 새 행 생성
    last_row = df.iloc[-1]
    filled_rows = []

    for idx in missing_indices:
        new_row = last_row.copy()
        new_row.name = idx
        filled_rows.append(new_row)

        # 감사 로그에 기록 (매매 전략에서 걸러낼 수 있도록)
        _log("WARN", f"[FORWARD-FILL] {idx} | OHLCV={last_row['Close']:.2f} (⚠️ 복제 데이터)")

    if filled_rows:
        filled_df = pd.DataFrame(filled_rows)
        df = pd.concat([df, filled_df]).sort_index()

    return df


def fill_gaps_sync(
    ticker: str,
    interval: str,
    df: pd.DataFrame,
    gap_details: list,
    max_retry: int = 2,
    retry_sleep: float = 1.0
) -> Tuple[bool, pd.DataFrame]:
    """
    경미한 갭(1~2개 봉 누락)을 즉시 동기 백필로 복구.

    EMA Golden Cross 타이밍을 놓치지 않기 위해, 60초 지연 백필이 아닌
    즉시 동기 방식으로 누락된 과거 확정 봉을 조회하여 복구.

    Args:
        ticker: 티커 (예: "KRW-SUI")
        interval: 봉 간격 (예: "minute3")
        df: 현재 DataFrame
        gap_details: _validate_candle_continuity 결과
            각 항목: {'prev': datetime, 'current': datetime, 'gap_minutes': float, 'missing_bars': int}
        max_retry: 최대 재시도 횟수
        retry_sleep: 재시도 간 대기 시간(초)

    Returns:
        (success: bool, df: pd.DataFrame)
        - success: 모든 갭이 성공적으로 복구되었으면 True
        - df: 복구된 DataFrame (실패 시 원본 반환)
    """
    if not gap_details:
        return True, df

    logger.info(f"🔄 [SYNC-FILL] 즉시 동기 백필 시작: {len(gap_details)}개 갭 감지")

    original_df = df.copy()
    success_count = 0

    for gap in gap_details:
        prev_time = gap['prev']
        curr_time = gap['current']
        missing_bars = gap['missing_bars']

        logger.info(
            f"🔄 [SYNC-FILL] 갭 복구 시도 | "
            f"{prev_time} → {curr_time} | "
            f"누락: {missing_bars}개 봉"
        )

        # 누락 구간 복구 시도
        filled = False
        for attempt in range(1, max_retry + 1):
            try:
                # 누락된 구간 + 여유분(2개) 요청
                count = missing_bars + 2
                to_param = _fmt_to_param(curr_time)

                logger.info(
                    f"🔄 [SYNC-FILL] API 호출 ({attempt}/{max_retry}) | "
                    f"count={count}, to={to_param}"
                )

                gap_data = pyupbit.get_ohlcv(
                    ticker,
                    interval=interval,
                    count=count,
                    to=to_param
                )

                if gap_data is not None and not gap_data.empty:
                    # 표준화 (standardize_ohlcv와 동일한 로직)
                    gap_data = gap_data.rename(columns={
                        "open": "Open",
                        "high": "High",
                        "low": "Low",
                        "close": "Close",
                        "volume": "Volume"
                    })
                    if "value" in gap_data.columns:
                        gap_data = gap_data.drop(columns=["value"])

                    # 인덱스 KST naive로 통일
                    idx = pd.to_datetime(gap_data.index)
                    if getattr(idx, "tz", None) is not None:
                        idx = idx.tz_convert("Asia/Seoul").tz_localize(None)
                    gap_data.index = idx

                    gap_data = gap_data.sort_index().dropna()

                    # 실제 누락 구간만 추출 (기존 데이터 제외)
                    existing_indices = set(df.index)
                    gap_data_new = gap_data[~gap_data.index.isin(existing_indices)]
                    gap_data_new = gap_data_new[
                        (gap_data_new.index > prev_time) &
                        (gap_data_new.index <= curr_time)
                    ]

                    if not gap_data_new.empty:
                        # df에 병합
                        df = pd.concat([df, gap_data_new]).drop_duplicates().sort_index()

                        logger.info(
                            f"✅ [SYNC-FILL] 갭 복구 성공 | "
                            f"{len(gap_data_new)}개 봉 추가 | "
                            f"범위: {gap_data_new.index[0]} ~ {gap_data_new.index[-1]}"
                        )
                        filled = True
                        success_count += 1
                        break
                    else:
                        logger.warning(
                            f"⚠️ [SYNC-FILL] API 응답이 이미 보유 중인 봉만 포함 | "
                            f"attempt={attempt}/{max_retry}"
                        )
                else:
                    logger.warning(
                        f"⚠️ [SYNC-FILL] API 응답 없음 | "
                        f"attempt={attempt}/{max_retry}"
                    )

            except Exception as e:
                logger.warning(
                    f"⚠️ [SYNC-FILL] API 예외 | "
                    f"attempt={attempt}/{max_retry} | "
                    f"error={e}"
                )

            # 재시도 전 대기
            if attempt < max_retry:
                time.sleep(retry_sleep)

        if not filled:
            logger.error(
                f"❌ [SYNC-FILL] 갭 복구 실패 | "
                f"{prev_time} → {curr_time} | "
                f"최대 {max_retry}회 재시도 실패"
            )
            # 하나라도 실패하면 원본 반환
            return False, original_df

    if success_count == len(gap_details):
        logger.info(
            f"✅ [SYNC-FILL] 모든 갭 복구 완료 | "
            f"{success_count}/{len(gap_details)} 성공 | "
            f"최종 봉 개수: {len(original_df)} → {len(df)}"
        )
        return True, df
    else:
        logger.error(
            f"❌ [SYNC-FILL] 일부 갭 복구 실패 | "
            f"{success_count}/{len(gap_details)} 성공"
        )
        return False, original_df


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
        # ✅ 인덱스(timestamp) 기준 중복 제거 - OHLCV 값이 동일해도 시간이 다르면 유지
        result = combined[~combined.index.duplicated(keep='last')].sort_index().iloc[-max_length:]
        memory_usage_mb = result.memory_usage(deep=True).sum() / 1024 / 1024
        if memory_usage_mb > 10:
            logger.warning(f"⚠️ DataFrame 메모리 사용량 과다: {memory_usage_mb:.2f}MB")
        return result
    except Exception as e:
        logger.error(f"❌ DataFrame 최적화 실패: {e}")
        combined_fallback = pd.concat([old_df, new_data], ignore_index=False)
        return combined_fallback[~combined_fallback.index.duplicated(keep='last')].sort_index().iloc[-max_length:]

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
    strategy_type: str = None,  # 전략 타입 (MACD/EMA)
):
    # ✅ Phase 2: Redis & WebSocket 초기화
    redis_cache = None
    ws_aggregator = None

    if PHASE2_AVAILABLE:
        try:
            if REDIS_ENABLED:
                redis_cache = get_redis_cache(REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD)
                if redis_cache.enabled:
                    logger.info(f"✅ [PHASE2] Redis 캐시 활성화: {ticker}/{interval}")

            if WEBSOCKET_ENABLED and interval == "minute1":  # minute1만 WebSocket 지원
                ws_aggregator = get_websocket_aggregator(ticker, redis_cache)
                logger.info(f"✅ [PHASE2] WebSocket 집계기 활성화: {ticker}")
        except Exception as e:
            logger.warning(f"⚠️ [PHASE2] 초기화 실패 (REST API 전용 모드): {e}")

    # ✅ 데이터 수집 상태 업데이트 함수 import
    if user_id:
        try:
            from services.db import update_data_collection_status, clear_data_collection_status
        except ImportError:
            update_data_collection_status = None
            clear_data_collection_status = None
    else:
        update_data_collection_status = None
        clear_data_collection_status = None
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

        # 인덱스 tz 정규화: KST naive로 통일
        # ⚠️ 중요: pyupbit은 이미 KST 시간대로 tz-naive 데이터를 반환함
        idx = pd.to_datetime(df.index)
        try:
            if getattr(idx, "tz", None) is None:
                # ✅ pyupbit은 이미 KST naive로 반환하므로 그대로 사용
                _log("INFO", f"[standardize] tz-naive 감지 → pyupbit은 이미 KST이므로 그대로 사용")
            else:
                # tz-aware인 경우에만 KST로 변환 후 tz 제거
                _log("INFO", f"[standardize] tz-aware 감지 (tz={idx.tz}) → KST로 변환")
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
    def _fetch_initial_history(to_param: str, retry_full: int = 3) -> pd.DataFrame:
        """
        Upbit는 분봉 기준 한 번에 최대 200개만 반환하므로,
        max_length가 200을 넘는 경우 여러 번 나눠서 과거 히스토리를 모은다.
        - MACD/EMA를 HTS 수준으로 맞추기 위한 긴 히스토리(예: 3분봉 1500~2000개) 확보용.
        - retry_full: 전체 수집 실패 시 재시도 횟수
        """
        iv_min = _iv_min(interval)
        remaining = max_length
        current_to = to_param
        chunks: list[pd.DataFrame] = []
        base_delay_local = retry_wait
        total_requested = max_length
        api_calls = 0
        start_time = time.time()

        expected_calls = (max_length + 199) // 200  # 올림 계산
        expected_time = expected_calls * 0.15  # API 호출당 약 0.15초 (0.1초 딜레이 + 네트워크)
        _log("INFO", f"[초기-multi] 히스토리 수집 시작: max_length={max_length}, interval={interval}")
        _log("INFO", f"[초기-multi] 예상: API 호출 {expected_calls}회, 소요 시간 약 {expected_time:.1f}초")

        # ✅ 데이터 수집 시작 상태 저장
        if update_data_collection_status:
            update_data_collection_status(
                user_id=user_id,
                is_collecting=True,
                collected=0,
                target=max_length,
                progress=0.0,
                estimated_time=expected_time,
                message=f"데이터 수집 시작 ({interval}봉, 목표: {max_length}개)"
            )

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
                        # 🔍 PRICE-DEBUG: multi-fetch 마지막 호출의 원본 데이터 (api_calls==1일때만)
                        if api_calls == 1:
                            try:
                                last_3 = df_part.tail(3)
                                for idx, row in last_3.iterrows():
                                    _log("INFO", f"[PRICE-API-RAW-MULTI] {idx} | O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f}")
                            except Exception as e_log:
                                _log("WARN", f"[PRICE-API-RAW-MULTI] 로깅 실패: {e_log}")
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
            progress = collected_so_far / total_requested
            remaining_time = remaining * 0.15
            _log("INFO", f"[초기-multi] 진행: {collected_so_far}/{total_requested} ({100*progress:.1f}%)")

            # ✅ 진행 상황 업데이트
            if update_data_collection_status:
                update_data_collection_status(
                    user_id=user_id,
                    is_collecting=True,
                    collected=collected_so_far,
                    target=total_requested,
                    progress=progress,
                    estimated_time=remaining_time,
                    message=f"데이터 수집 중 ({collected_so_far}/{total_requested})"
                )

            if got < per_call:
                # Upbit API가 요청량보다 적게 반환 = 더 이상 과거 데이터 없음
                _log("WARN", f"[초기-multi] API가 요청량보다 적게 반환 (got={got}, requested={per_call}) → 과거 데이터 소진")
                break

            # ✅ FIX: 다음 요청용 'to'는 실제 받은 데이터의 첫 번째 봉 시간 기준으로 계산
            # 이전 방식(current_to 기준)은 중복 데이터 발생 가능
            try:
                # 실제 받은 데이터의 첫 번째 시간
                first_timestamp = df_part.index[0]
                # 1분(또는 interval) 전으로 설정하여 중복 방지
                dt_to = first_timestamp - timedelta(minutes=iv_min)
                current_to = _fmt_to_param(dt_to)
                _log("INFO", f"[초기-multi] 다음 요청 기준: {current_to} (이번 chunk 첫 봉: {first_timestamp})")
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
        elapsed_time = time.time() - start_time
        _log("INFO", f"[초기-multi] 수집 완료: {final_count}/{total_requested} ({success_rate:.1f}%), API 호출 {api_calls}회, 소요시간 {elapsed_time:.2f}초")

        # 🔍 PRICE-DEBUG: concat 후 최종 원본 데이터 (변환 전)
        try:
            last_3 = raw.tail(3)
            for idx, row in last_3.iterrows():
                _log("INFO", f"[PRICE-API-CONCAT] {idx} | O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f}")
        except Exception as e_log:
            _log("WARN", f"[PRICE-API-CONCAT] 로깅 실패: {e_log}")

        return raw
    
    # ---- 초기 로드: 막 닫힌 경계까지 ----
    base_delay = retry_wait
    df = None
    now = _now_kst_naive()
    bar_close = _floor_boundary(now, interval)
    to_param = _fmt_to_param(bar_close)

    # ★ Phase 2: DB 캐시 우선 확인 (타임존 검증 완료 - 활성화)
    if user_id:
        try:
            from services.db import load_candle_cache
            cached_df = load_candle_cache(user_id, ticker, interval, max_length)

            if cached_df is not None and len(cached_df) >= max_length:
                # ✅ 캐시에 충분한 데이터 존재 - 즉시 사용
                df = cached_df.tail(max_length)
                _log("INFO", f"[CACHE-HIT] {len(df)}개 로드 완료 (즉시 전략 시작 가능)")
            elif cached_df is not None and len(cached_df) > 0:
                # ✅ 캐시 부족 - API로 최신 데이터 수집하여 병합
                needed = max_length - len(cached_df)
                _log("INFO", f"[CACHE-PARTIAL] DB {len(cached_df)}개 존재, API로 최신 {needed}개 추가 수집")

                # API로 최신 데이터 수집
                api_df = pyupbit.get_ohlcv(ticker, interval=interval, count=needed)
                if api_df is not None and not api_df.empty:
                    # 컬럼명 통일
                    api_df = api_df.rename(columns={
                        "open": "Open", "high": "High", "low": "Low",
                        "close": "Close", "volume": "Volume"
                    })

                    # 병합 및 중복 제거
                    df = pd.concat([cached_df, api_df])
                    df = df[~df.index.duplicated(keep='last')].sort_index()
                    df = df.tail(max_length)
                    _log("INFO", f"[CACHE-MERGE] 병합 완료: 최종 {len(df)}개 (DB + API)")
                else:
                    # API 실패 시 캐시만 사용
                    df = cached_df
                    _log("WARN", f"[CACHE-MERGE] API 실패, 캐시 {len(df)}개만 사용")
            else:
                _log("INFO", f"[CACHE-MISS] 캐시 없음, API로 전체 수집")
        except Exception as e:
            _log("WARN", f"[CACHE] 캐시 로드 실패, API로 전체 수집: {e}")

    # ✅ 전략별 최소 캔들 개수 결정
    strategy_tag = (strategy_type or "MACD").upper().strip()
    absolute_min = ABSOLUTE_MIN_CANDLES.get(strategy_tag, ABSOLUTE_MIN_CANDLES_DEFAULT)
    _log("INFO", f"[초기] strategy={strategy_tag}, absolute_min_candles={absolute_min}")

    # ★ 캐시 미스 또는 부족: API 호출
    if df is None:
        _log("INFO", f"[초기] 데이터 수집 시작: ticker={ticker}, interval={interval}, max_length={max_length}")

        # ✅ pyupbit는 내부적으로 multi-fetch 지원 (200개씩 여러 번 호출)
        # - max_length=400 요청 시 자동으로 2번 호출하여 400개 반환
        # - 초기 수집 시간: 약 10초 소요 (200개: 2초 → 400개: 10초)
        effective_count = max_length
        _log("INFO", f"[초기] pyupbit multi-fetch 활성화: {effective_count}개 요청")

        if True:  # 항상 단일 호출 사용
            for attempt in range(1, max_retry + 1):
                if stop_event and stop_event.is_set():
                    _log("WARN", "stream_candles 중단됨: 초기 수집 중 stop_event 감지")
                    return
                try:
                    # ✅ FIX: to 파라미터 제거 - 확정된 최근 봉만 조회
                    _log("INFO", f"[초기] API 단일 호출: count={effective_count}")
                    df = pyupbit.get_ohlcv(ticker, interval=interval, count=effective_count)
                    if df is not None and not df.empty:
                        _log("INFO", f"[초기] API 응답 성공: {len(df)}개 수신")
                        # 🔍 PRICE-DEBUG: pyupbit 원본 데이터 (변환 전)
                        try:
                            last_3 = df.tail(3)
                            for idx, row in last_3.iterrows():
                                _log("INFO", f"[PRICE-API-RAW] {idx} | O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f}")
                        except Exception as e_log:
                            _log("WARN", f"[PRICE-API-RAW] 로깅 실패: {e_log}")
                        break
                except Exception as e:
                    _log("ERROR", f"[초기] API 예외 발생: {e}")

                delay = min(base_delay * (2 ** (attempt - 1)), 60) + random.uniform(0, 5)
                _log("WARN", f"[초기] API 실패 ({attempt}/{max_retry}), {delay:.1f}초 후 재시도")
                time.sleep(delay)
        else:
            # ★ MACD/EMA 안정화를 위해 긴 히스토리(max_length) 확보 + 재시도
            _log("INFO", f"[초기] max_length > 200 → multi-fetch 모드 사용 (최대 3회 재시도)")

            retry_count = 0
            max_full_retry = 3

            while retry_count < max_full_retry:
                df = _fetch_initial_history(to_param, retry_full=max_full_retry)

                if df is not None and not df.empty:
                    temp_len = len(df)
                    success_rate = 100 * temp_len / max_length if max_length > 0 else 0

                    # 절대 최소량 이상이면 성공 (Upbit API 제약 고려)
                    if temp_len >= absolute_min:
                        _log("INFO", f"[초기-재시도] 수집 성공: {temp_len}/{max_length} ({success_rate:.1f}%) - 절대 최소량({absolute_min}) 충족")
                        break
                    else:
                        retry_count += 1
                        if retry_count < max_full_retry:
                            retry_delay = 5 + random.uniform(0, 3)
                            _log("WARN", f"[초기-재시도] 절대 부족 ({temp_len}/{absolute_min}) - {retry_delay:.1f}초 후 전체 재시도 ({retry_count}/{max_full_retry})")
                            time.sleep(retry_delay)
                        else:
                            _log("ERROR", f"[초기-재시도] 최대 재시도 횟수 도달: {temp_len}/{absolute_min} (절대 최소량 미달)")
                else:
                    retry_count += 1
                    if retry_count < max_full_retry:
                        retry_delay = 5 + random.uniform(0, 3)
                        _log("ERROR", f"[초기-재시도] 수집 실패 - {retry_delay:.1f}초 후 전체 재시도 ({retry_count}/{max_full_retry})")
                        time.sleep(retry_delay)

        # ★ Phase 2: API 호출 후 DB에 저장
        if user_id and df is not None and not df.empty:
            try:
                from services.db import save_candle_cache
                save_candle_cache(user_id, ticker, interval, df)
            except Exception as e:
                _log("WARN", f"[CACHE] Save failed (ignored): {e}")

    if df is None or df.empty:
        raise ValueError(f"[초기] 데이터 수집 실패: ticker={ticker}, interval={interval}")

    _log("INFO", f"[초기] 수집된 원본 데이터: {len(df)}개")

    # 🔍 PRICE-DEBUG: standardize 전 데이터 (API 직후)
    try:
        last_3 = df.tail(3)
        for idx, row in last_3.iterrows():
            _log("INFO", f"[PRICE-BEFORE-STD] {idx} | O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f}")
    except Exception as e_log:
        _log("WARN", f"[PRICE-BEFORE-STD] 로깅 실패: {e_log}")

    df = standardize_ohlcv(df).drop_duplicates()
    final_len = len(df)

    # 🔍 PRICE-DEBUG: standardize 후 데이터
    try:
        last_3 = df.tail(3)
        for idx, row in last_3.iterrows():
            _log("INFO", f"[PRICE-AFTER-STD] {idx} | O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} C={row['Close']:.0f}")
    except Exception as e_log:
        _log("WARN", f"[PRICE-AFTER-STD] 로깅 실패: {e_log}")
    success_rate = 100 * final_len / max_length if max_length > 0 else 0

    _log("INFO", f"[초기] standardize 후 최종 데이터: {final_len}개 (목표: {max_length}개, 달성률: {success_rate:.1f}%)")

    # ★ 데이터 부족 경고 (엔진은 계속 실행하면서 실시간으로 데이터 축적)
    if final_len < absolute_min:
        _log("WARN", "")
        _log("WARN", "=" * 80)
        _log("WARN", f"⚠️  초기 데이터 부족: {final_len}/{absolute_min}개 (권장: {absolute_min}개)")
        _log("WARN", "=" * 80)
        _log("WARN", f"   - 현재 {final_len}개로 전략을 시작합니다.")
        _log("WARN", f"   - 지표가 초기에 불완전할 수 있습니다.")
        _log("WARN", f"   - 실시간으로 데이터를 수집하며 점진적으로 정확도가 향상됩니다.")
        _log("WARN", f"   - 약 {absolute_min - final_len}분 후 권장 데이터량 달성")
        _log("WARN", "=" * 80)
        _log("WARN", "")

    # 목표 대비 50% 미만이면 경고 (전략은 실행)
    if final_len < max_length * WARNING_RATIO:
        _log("WARN",
            f"⚠️ 목표 대비 {success_rate:.1f}% 달성 ({final_len}/{max_length}) - "
            f"Upbit API 제약으로 추정. 절대 최소량({absolute_min})은 충족하여 전략 실행"
        )

        # ⚠️ EMA 전략 + 200개 데이터 + 목표 > 200인 경우 추가 경고
        if strategy_tag == "EMA" and final_len <= 200 and max_length > 200:
            _log("WARN", "")
            _log("WARN", "=" * 80)
            _log("WARN", "⚠️  [EMA 전략] 초기 데이터 부족 안내")
            _log("WARN", "=" * 80)
            _log("WARN", f"   - Upbit API 제한으로 최대 200개 봉만 조회 가능합니다.")
            _log("WARN", f"   - 현재 {final_len}개 데이터로 전략을 시작합니다.")
            _log("WARN", f"   - 200일 이동평균 등 긴 기간 지표는 초기에 불완전합니다.")
            _log("WARN", f"   - 실시간 데이터가 쌓이면서 점진적으로 정확도가 향상됩니다.")
            _log("WARN", f"   - 완전한 지표 계산은 약 {max_length - final_len}분 후 가능합니다.")
            _log("WARN", "=" * 80)
            _log("WARN", "")

    # ✅ 데이터 수집 완료 - 상태 초기화
    if clear_data_collection_status:
        clear_data_collection_status(user_id)
        _log("INFO", f"[초기] 데이터 수집 완료! 엔진 시작합니다.")

    yield df

    last_open = df.index[-1]  # 우리가 가진 마지막 bar_open (tz-naive)

    # ---- 실시간 루프: 경계 동기화 → 닫힌 봉 조회 → 갭 백필 ----
    # ✅ interval별 JITTER 값 선택
    jitter = JITTER_BY_INTERVAL.get(interval, 0.7)
    _log("INFO", f"[실시간 루프] interval={interval}, jitter={jitter}초")

    while not (stop_event and stop_event.is_set()):
        # ✅ 지연된 백필 처리 (루프 초반 실행)
        # - 충분한 시간이 지난 후 과거 누락 구간을 안정적으로 재조회
        if hasattr(stream_candles, '_pending_backfill') and stream_candles._pending_backfill:
            current_time = time.time()
            completed_backfills = []

            for pending in stream_candles._pending_backfill[:]:  # 복사본으로 순회
                if current_time >= pending['retry_after']:
                    try:
                        _log("INFO",
                            f"[지연 백필 시도] {pending['missing_bars']}개 봉 | "
                            f"구간: {pending['start']} ~ {pending['end']}"
                        )

                        # 충분한 시간이 지났으므로 과거 구간 재조회
                        delayed_fill = pyupbit.get_ohlcv(
                            pending['ticker'],
                            interval=pending['interval'],
                            count=pending['missing_bars'] + 5,  # 여유분 추가
                            to=_fmt_to_param(pending['end'])
                        )

                        if delayed_fill is not None and not delayed_fill.empty:
                            delayed_fill = standardize_ohlcv(delayed_fill).drop_duplicates()

                            # 실제로 누락된 부분만 추출 (중복 방지)
                            existing_indices = set(df.index)
                            delayed_fill_new = delayed_fill[~delayed_fill.index.isin(existing_indices)]
                            delayed_fill_new = delayed_fill_new[
                                (delayed_fill_new.index > pending['start']) &
                                (delayed_fill_new.index <= pending['end'])
                            ]

                            if not delayed_fill_new.empty:
                                # df에 병합 (과거 구간이므로 안전하게 삽입 가능)
                                df = pd.concat([df, delayed_fill_new]).drop_duplicates().sort_index()

                                _log("INFO",
                                    f"✅ [지연 백필 성공] {len(delayed_fill_new)}개 봉 복구 완료 | "
                                    f"구간: {delayed_fill_new.index[0]} ~ {delayed_fill_new.index[-1]}"
                                )
                                completed_backfills.append(pending)
                            else:
                                _log("WARN", f"[지연 백필] 응답 데이터가 이미 보유 중인 봉만 포함 → 완료 처리")
                                completed_backfills.append(pending)
                        else:
                            # 재시도 실패 시 다시 30초 후로 연기 (최대 5회까지)
                            retry_count = pending.get('retry_count', 0) + 1
                            if retry_count < 5:
                                pending['retry_after'] = current_time + 30
                                pending['retry_count'] = retry_count
                                _log("WARN", f"[지연 백필] 재시도 실패 ({retry_count}/5) → 30초 후 재시도")
                            else:
                                _log("ERROR", f"[지연 백필] 최대 재시도 횟수 도달 ({retry_count}회) → 포기")
                                completed_backfills.append(pending)

                    except Exception as e:
                        _log("ERROR", f"[지연 백필 실패] {e}")
                        # 예외 발생 시에도 재시도 카운트 증가
                        retry_count = pending.get('retry_count', 0) + 1
                        if retry_count < 5:
                            pending['retry_after'] = current_time + 30
                            pending['retry_count'] = retry_count
                        else:
                            completed_backfills.append(pending)

            # 완료된 백필 항목 제거
            for completed in completed_backfills:
                if completed in stream_candles._pending_backfill:
                    stream_candles._pending_backfill.remove(completed)

        # 🔥 FIX: sleep 계산은 실제 시각(초 포함) 사용
        now_real = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
        now = _now_kst_naive()  # 경계 계산용 (초 제거)
        next_close = _next_boundary(now, interval)
        sleep_sec = max(0.0, (next_close - now_real).total_seconds() + jitter)

        # 🔍 DEBUG: 루프 진입 확인
        _log("INFO", f"[실시간 루프] sleep={sleep_sec:.1f}초 | now_real={now_real.strftime('%H:%M:%S')} | now={now} | next_close={next_close} | last_open={last_open}")
        time.sleep(sleep_sec)

        # 🔥 FIX: sleep 후 현재 시각 재계산 (next_close 재사용 금지!)
        # - sleep 중 시간이 흘렀으므로 현재 시각 기준으로 boundary 재계산 필요
        # - 특히 엔진 재시작 직후 짧은 sleep 시 필수!
        now_after_sleep = _now_kst_naive()
        next_close_after = _next_boundary(now_after_sleep, interval)

        # 막 닫힌 봉의 open
        iv = _iv_min(interval)
        boundary_open = next_close_after - timedelta(minutes=iv)

        # 🔍 DEBUG: sleep 전후 시각 비교 (버그 디버깅용)
        if next_close != next_close_after:
            _log("INFO",
                f"[시각 동기화] sleep 전: next_close={next_close} → "
                f"sleep 후: next_close_after={next_close_after} | "
                f"boundary_open={boundary_open}"
            )

        # 🔥 FIX: 중간 누락분 계산 (올림 처리로 1분 갭도 감지)
        # 기존: int() 절사 → 1분 갭이 0으로 계산되어 누락!
        # 개선: math.ceil() 올림 → 1분 갭도 1로 계산
        gap_seconds = (boundary_open - last_open).total_seconds()
        gap = math.ceil(gap_seconds / (iv * 60))  # 올림 처리

        # 🛡️ 안전장치: gap이 1 이하여도 최소 2개 봉 요청 (중복 제거)
        # - 이유: API 응답 지연으로 최신 봉이 누락될 수 있음
        # - 중복은 나중에 자동 제거되므로 안전
        need = max(2, min(gap + 1, 200))  # 최소 2개, gap+1개 요청

        # 🔍 DEBUG: API 호출 전 파라미터
        _log("INFO", f"[실시간 API] boundary_open={boundary_open} | gap={gap} | need={need} | last_open={last_open}")

        # 🔥 FIX: 응답 지연 재시도를 내부 루프로 구현 (continue 버그 수정)
        # 기존 문제: continue → while 처음 복귀 → sleep 다시 실행 → 재시도 무효화!
        # 해결: 내부 for 루프로 재시도 → API 호출만 반복 → sleep 건너뛰지 않음
        new = None
        max_delay_retry = 10  # ✅ CTO 승인: 5회 → 10회 (API 장애 대응 강화)

        for delay_retry_attempt in range(max_delay_retry):
            if stop_event and stop_event.is_set():
                _log("WARN", "stream_candles 중단됨: 실시간 루프 중 stop_event 감지")
                return

            # ✅ Phase 2: 다중 소스 조회 (Redis 캐시 → REST API)
            new = None
            cache_hit = False

            # 1단계: Redis 캐시 확인 (단일 봉 조회)
            if redis_cache and redis_cache.enabled and gap == 1:
                try:
                    cached_data = redis_cache.get_candle(ticker, interval, boundary_open)
                    if cached_data:
                        # 캐시 히트: DataFrame으로 변환
                        cached_ts = pd.to_datetime(cached_data["timestamp"])
                        new = pd.DataFrame([{
                            "Open": cached_data["Open"],
                            "High": cached_data["High"],
                            "Low": cached_data["Low"],
                            "Close": cached_data["Close"],
                            "Volume": cached_data["Volume"],
                        }], index=[cached_ts])
                        cache_hit = True
                        _log("INFO", f"✅ [REDIS-HIT] {boundary_open} | C={cached_data['Close']:.0f}")
                except Exception as e:
                    _log("WARN", f"⚠️ [REDIS] 조회 실패 (REST API로 대체): {e}")

            # 2단계: REST API 호출 (캐시 미스 또는 여러 봉 필요)
            if not cache_hit:
                for attempt in range(1, max_retry + 1):
                    if stop_event and stop_event.is_set():
                        return
                    try:
                        # ✅ to 파라미터 제거 - 항상 최신 확정 봉만 조회 (임시 종가 회피)
                        _log("INFO",
                            f"[실시간 API] 호출 #{delay_retry_attempt + 1}/{max_delay_retry} | "
                            f"count={need} (최신 확정 봉)"
                        )
                        new = pyupbit.get_ohlcv(ticker, interval=interval, count=need)
                        if new is not None and not new.empty:
                            # 🔍 PRICE-DEBUG: 실시간 API 원본 데이터
                            try:
                                last_3 = new.tail(min(3, len(new)))
                                for idx, row in last_3.iterrows():
                                    _log("INFO", f"[PRICE-REALTIME-RAW] {idx} | O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f}")
                            except Exception as e_log:
                                _log("WARN", f"[PRICE-REALTIME-RAW] 로깅 실패: {e_log}")
                            break
                    except Exception as e:
                        _log("ERROR", f"[실시간 API] 예외: {e} (attempt {attempt}/{max_retry})")

                    delay = min(base_delay * (2 ** (attempt - 1)), 30) + random.uniform(0, 2)
                    _log("WARN", f"[실시간 API] {delay:.1f}초 후 재시도 (연결 실패)")
                    time.sleep(delay)

            # API 연결 자체 실패 시 외부 while 루프로 (경계 재동기화)
            if new is None or new.empty:
                backoff = min(30 + random.uniform(0, 10), 300)
                _log("ERROR", f"[실시간 API] 연결 실패, {backoff:.1f}초 후 경계 재동기화")
                time.sleep(backoff)
                break  # 내부 루프 탈출 → while 처음으로 (경계 재계산)

            # 🛡️ 응답 검증: 기대한 봉을 받았는가?
            _log("INFO", f"[실시간 API 응답] rows={len(new)} | first={new.index[0]} | last={new.index[-1]}")

            expected_last = boundary_open
            actual_last = new.index[-1]
            time_gap = (expected_last - actual_last).total_seconds() / 60
            time_gap_bars = time_gap / iv

            # 🛡️ 응답 지연 감지: 0.5봉 이상 차이
            if time_gap_bars >= 0.5:
                _log("WARN",
                    f"[실시간 API] 응답 지연 감지! "
                    f"기대: {expected_last} | 실제: {actual_last} | "
                    f"갭: {time_gap:.1f}분 ({time_gap_bars:.1f}봉)"
                )

                # 최대 재시도 전이면 대기 후 재시도
                if delay_retry_attempt < max_delay_retry - 1:
                    retry_delays = [3, 5, 8, 12, 15]
                    retry_delay = retry_delays[min(delay_retry_attempt, len(retry_delays) - 1)]
                    retry_delay += random.uniform(0, 2)

                    _log("WARN",
                        f"[실시간 API] {retry_delay:.1f}초 후 재시도 "
                        f"({delay_retry_attempt + 1}/{max_delay_retry}) - 누락 방지!"
                    )
                    time.sleep(retry_delay)
                    # continue로 내부 for 루프 반복 (API 재호출)
                    continue
                else:
                    _log("ERROR",
                        f"[실시간 API] 최대 재시도 도달 ({max_delay_retry}회) - "
                        f"백필 로직으로 복구 시도"
                    )
                    # break로 내부 루프 탈출 → 백필 시도
                    break
            else:
                # 정상 응답: 내부 루프 탈출
                _log("INFO", f"[실시간 API] 정상 응답 확인 (갭: {time_gap_bars:.2f}봉)")
                break

        # API 응답 없음 시 다음 루프로
        if new is None or new.empty:
            _log("WARN", f"[실시간 API] 응답 없음 - last_open 유지하여 다음 루프에서 재시도")
            continue

        new = standardize_ohlcv(new).drop_duplicates()

        # ✅ Phase 2: Redis에 저장 (캐시 미스인 경우만)
        if not cache_hit and redis_cache and redis_cache.enabled and not new.empty:
            try:
                redis_cache.save_candles_bulk(ticker, interval, new, ttl=CANDLE_CACHE_TTL)
            except Exception as e:
                _log("WARN", f"⚠️ [REDIS-SAVE] 저장 실패 (무시): {e}")

        # 🔍 DEBUG: standardize 후 데이터
        _log("INFO", f"[실시간 표준화 후] rows={len(new)} | first={new.index[0]} | last={new.index[-1]}")

        # 🛡️ 방안 3: 강화된 누락 감지 및 강제 백필
        if not new.empty:
            new_last = new.index[-1]

            # 예상 범위 계산
            expected_last = boundary_open  # 방금 닫힌 봉

            # 🔥 FIX: 누락 감지 강화 (0.3봉 이상도 감지)
            # 기존: 0.5봉 이상만 감지 → 1분 갭의 33% 누락!
            # 개선: 0.3봉 이상 감지 + math.ceil로 올림
            time_gap_seconds = abs((expected_last - new_last).total_seconds())
            time_gap_bars = time_gap_seconds / (iv * 60)  # 봉 단위

            # 🛡️ 더 엄격한 누락 기준: 0.3봉 이상 (기존: 0.5봉)
            if time_gap_bars >= 0.3:  # 0.3봉 이상 차이나면 누락 의심
                missing_minutes = time_gap_seconds / 60
                # 🔥 FIX: 올림 처리로 1분 갭도 1봉으로 계산
                missing_bars = math.ceil(missing_minutes / iv)  # 기존: int(...)

                if missing_bars > 0:
                    _log("WARN",
                        f"⚠️ [누락 감지] 기대 마지막 봉: {expected_last} | "
                        f"실제 마지막 봉: {new_last} | "
                        f"누락: {missing_bars}개 봉 ({missing_minutes}분)"
                    )

                    # ✅ Interval 기반 백필 전략 (1분봉은 빠른 포기 필수!)
                    # ✅ CTO 승인: 재시도 횟수 증가로 API 장애 대응 강화
                    # - 1분봉: 최대 5회 (3→5), 간격 1~3초 → 다음 봉 전에 완료
                    # - 3분봉: 최대 8회 (5→8), 간격 2~5초
                    # - 5분 이상: 최대 10회 (8→10), 간격 2~20초
                    if iv == 1:
                        max_backfill_retry = 5  # 3 → 5
                        wait_times = [1, 2, 2, 3, 3]  # 총 11초 + API 호출 시간
                    elif iv <= 3:
                        max_backfill_retry = 8  # 5 → 8
                        wait_times = [2, 3, 4, 5, 6, 6, 7, 8]  # 총 41초
                    else:
                        max_backfill_retry = 10  # 8 → 10
                        wait_times = [2, 4, 6, 8, 10, 12, 15, 20, 20, 20]  # 총 117초

                    _log("DEBUG", f"[백필 전략] interval={iv}분 → max_retry={max_backfill_retry}")

                    backfill_success = False
                    for backfill_attempt in range(1, max_backfill_retry + 1):
                        try:
                            _log("INFO",
                                f"[백필 시도 {backfill_attempt}/{max_backfill_retry}] "
                                f"{new_last} ~ {expected_last} 구간 | "
                                f"누락: {missing_bars}개 봉"
                            )

                            # 🛡️ 누락된 구간 + 여유분(3개) 추가 요청 (기존: +2)
                            # - 여유분을 더 늘려서 API 응답 불안정 대응
                            backfill_count = missing_bars + 3
                            backfill = pyupbit.get_ohlcv(
                                ticker,
                                interval=interval,
                                count=backfill_count,
                                to=_fmt_to_param(expected_last)
                            )

                            if backfill is not None and not backfill.empty:
                                backfill = standardize_ohlcv(backfill).drop_duplicates()

                                # 🔥 FIX: 실제로 누락된 부분만 추출
                                # - new에 이미 있는 봉은 제외
                                # - last_open과 expected_last 사이만 추출 (미래 봉 차단)
                                existing_indices = set(new.index)
                                backfill_new = backfill[~backfill.index.isin(existing_indices)]
                                backfill_new = backfill_new[
                                    (backfill_new.index > last_open) &
                                    (backfill_new.index <= expected_last)
                                ]

                                if not backfill_new.empty:
                                    # new에 병합
                                    new = pd.concat([new, backfill_new]).drop_duplicates().sort_index()
                                    _log("INFO",
                                        f"✅ [백필 성공] {len(backfill_new)}개 봉 복구 완료 | "
                                        f"복구 범위: {backfill_new.index[0]} ~ {backfill_new.index[-1]}"
                                    )
                                    backfill_success = True
                                    break
                                else:
                                    _log("WARN", f"[백필] 응답 데이터가 이미 보유 중인 봉만 포함")
                            else:
                                _log("WARN", f"[백필] API 응답 없음 (attempt {backfill_attempt}/{max_backfill_retry})")

                        except Exception as e:
                            _log("ERROR", f"[백필 실패] {e} (attempt {backfill_attempt}/{max_backfill_retry})")

                        # ✅ 재시도 전 대기 (interval 기반 wait_times 사용)
                        if backfill_attempt < max_backfill_retry:
                            wait_time = wait_times[min(backfill_attempt - 1, len(wait_times) - 1)]
                            _log("INFO", f"[백필] {wait_time}초 후 재시도... (누락 방지 최우선)")
                            time.sleep(wait_time)

                    if not backfill_success:
                        _log("ERROR",
                            f"❌ [백필 포기] {missing_bars}개 봉 누락! | "
                            f"누락 구간: {new_last} ~ {expected_last} | "
                            f"최대 {max_backfill_retry}회 재시도 실패"
                        )

                        # ✅ Interval 기반 백필 포기 후 전략
                        if iv == 1:
                            # 1분봉: 합성 봉으로 즉시 대체 (아래 로직으로 처리됨)
                            _log("WARN", f"[백필 포기-1분봉] 합성 봉으로 대체 처리")
                            # new.empty가 아니므로 아래 `len(new) < expected_bars` 조건으로 합성 봉 생성됨
                        else:
                            # 3분 이상: 지연 백필 예약 (다음 루프에서 재시도 여유 있음)
                            _log("WARN", f"[백필 포기-{iv}분봉] 다음 루프에서 gap 계산으로 재시도 예정 (last_open 유지)")

                            # ✅ 지연된 백필: 누락 구간을 기록하여 다음 루프에서 재조회
                            if not hasattr(stream_candles, '_pending_backfill'):
                                stream_candles._pending_backfill = []

                            stream_candles._pending_backfill.append({
                                'start': new_last,
                                'end': expected_last,
                                'missing_bars': missing_bars,
                                'retry_after': time.time() + 30,  # 30초 후 재시도
                                'ticker': ticker,
                                'interval': interval,
                            })

                            _log("INFO", f"✅ [지연 백필 예약] {missing_bars}개 봉 | 30초 후 재시도 예정")

        # 🔍 PRICE-DEBUG: 실시간 standardize 후 데이터
        try:
            last_3 = new.tail(min(3, len(new)))
            for idx, row in last_3.iterrows():
                _log("INFO", f"[PRICE-REALTIME-STD] {idx} | O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} C={row['Close']:.0f}")
        except Exception as e_log:
            _log("WARN", f"[PRICE-REALTIME-STD] 로깅 실패: {e_log}")

        # 🔥 FIX: 예상 범위 내의 봉만 허용 (미래 봉 차단)
        # - last_open < index <= boundary_open
        # - boundary_open: 방금 닫힌 봉 (이번 루프에서 처리해야 할 최신 봉)
        # - 예: last_open=21:24, boundary_open=21:25 → 21:25만 허용, 21:26은 차단
        before_filter_count = len(new)
        new = new[(new.index > last_open) & (new.index <= boundary_open)]

        # ✅ 중복 제거 (같은 인덱스는 최신 값 유지)
        new = new.loc[~new.index.duplicated(keep='last')]

        # 🔍 DEBUG: 필터링 결과
        _log("INFO", f"[실시간 필터링] before={before_filter_count} | after={len(new)} | filter_condition: {last_open} < index <= {boundary_open}")

        # ✅ 중간 봉 누락 감지 (부분 데이터 반환 대응)
        elapsed_minutes = (boundary_open - last_open).total_seconds() / 60
        expected_bars = int(elapsed_minutes / iv)

        # 🛡️ 방안 3-2: 필터링 후 empty이거나 중간 봉 누락 시 보호
        if new.empty or len(new) < expected_bars:
            # API가 부분 데이터만 반환 (예: 18:49만 있고 18:48 없음) 또는 응답 없음
            _log("DEBUG", f"[누락 감지] expected={expected_bars}개 | actual={len(new)}개 | elapsed={elapsed_minutes:.2f}분")

            # 시간이 충분히 흘렀으면 합성 봉 생성
            if elapsed_minutes >= iv:
                # ✅ 거래가 없어도 이전 종가로 합성 봉 생성 (BUY 평가 기록용)
                if not df.empty:
                    last_close = float(df.iloc[-1]['Close'])

                    # 🔥 FIX: 중간에 누락된 모든 봉에 대해 합성 봉 생성 (BUY 평가 연속성 보장)
                    missing_bars_count = int(elapsed_minutes / iv)
                    _log("DEBUG", f"[합성 봉 디버그] last_open={last_open} | boundary_open={boundary_open} | elapsed_minutes={elapsed_minutes:.2f} | missing_bars_count={missing_bars_count}")

                    if missing_bars_count > 1:
                        _log("WARN",
                            f"[합성 봉 다중 생성] {missing_bars_count}개 봉 생성 필요 | "
                            f"구간: {last_open} ~ {boundary_open}"
                        )
                        synthetic_bars = []
                        synthetic_indices = []
                        for i in range(1, missing_bars_count + 1):
                            synthetic_time = last_open + timedelta(minutes=iv * i)
                            _log("DEBUG", f"[합성 봉 루프] i={i} | synthetic_time={synthetic_time} | boundary_open={boundary_open} | 조건={synthetic_time <= boundary_open}")
                            if synthetic_time <= boundary_open:
                                synthetic_bars.append({
                                    'Open': last_close,
                                    'High': last_close,
                                    'Low': last_close,
                                    'Close': last_close,
                                    'Volume': 0.0
                                })
                                synthetic_indices.append(synthetic_time)
                                _log("INFO", f"[합성 봉] {synthetic_time} | OHLC={last_close:.2f} (Volume=0)")

                        if synthetic_bars:
                            synthetic_df = pd.DataFrame(synthetic_bars, index=synthetic_indices)
                            # ✅ 기존 API 데이터와 병합 (API 데이터 우선, 중복 시 API 값 유지)
                            if not new.empty:
                                _log("DEBUG", f"[합성 봉 병합] synthetic={len(synthetic_df)}개 | api={len(new)}개")
                                combined = pd.concat([synthetic_df, new])
                                new = combined[~combined.index.duplicated(keep='last')].sort_index()
                                _log("INFO", f"✅ [합성 봉 생성+병합 완료] {len(new)}개 | 첫봉={new.index[0]} | 마지막={new.index[-1]}")
                            else:
                                new = synthetic_df
                                _log("INFO", f"✅ [합성 봉 생성 완료] {len(synthetic_bars)}개 | 첫봉={new.index[0]} | 마지막={new.index[-1]}")
                        else:
                            _log("ERROR", f"❌ [합성 봉 실패] synthetic_bars 리스트가 비어있음! (missing_bars_count={missing_bars_count})")
                    else:
                        # 단일 봉만 누락
                        _log("WARN",
                            f"[실시간 필터링] 새 데이터 없지만 시간 경과 → 합성 봉 생성 | "
                            f"time={boundary_open} | OHLC={last_close:.2f} (이전 종가)"
                        )
                        # 합성 봉: Open=High=Low=Close=이전종가, Volume=0
                        synthetic_bar = pd.DataFrame({
                            'Open': [last_close],
                            'High': [last_close],
                            'Low': [last_close],
                            'Close': [last_close],
                            'Volume': [0.0]
                        }, index=[boundary_open])

                        # ✅ 기존 API 데이터와 병합 (단일 봉도 동일 로직 적용)
                        if not new.empty:
                            _log("DEBUG", f"[합성 봉 병합-단일] synthetic=1개 | api={len(new)}개")
                            combined = pd.concat([synthetic_bar, new])
                            new = combined[~combined.index.duplicated(keep='last')].sort_index()
                        else:
                            new = synthetic_bar

                    # 🔥 중요: last_open은 나중에 df.index[-1]로 업데이트되므로 여기서는 변경 안 함
                    # yield 계속 진행 (아래 df 병합 로직으로)
                else:
                    _log("WARN",
                        f"[실시간 필터링] df가 비어있어 합성 봉 생성 불가 → last_open만 업데이트"
                    )
                    last_open = boundary_open
                    continue
            else:
                _log("INFO",
                    f"[실시간 필터링] 시간 경과 부족 ({elapsed_minutes:.1f}분 < {iv}분), "
                    f"last_open 유지: {last_open}"
                )
                continue

        # 🔍 MERGE-DEBUG: 병합 전 DataFrame 상태
        try:
            _log("DEBUG", f"[병합 전] df.shape={df.shape} | df 마지막 3개: {list(df.tail(3).index) if len(df) >= 3 else list(df.index)}")
            _log("DEBUG", f"[병합 전] new.shape={new.shape} | new.empty={new.empty}")
            if not new.empty:
                _log("DEBUG", f"[병합 전] new 인덱스: {list(new.index[:3])}...{list(new.index[-3:])} (총 {len(new)}개)")
        except Exception as e_merge_log:
            _log("WARN", f"[병합 전] 로깅 실패: {e_merge_log}")

        # 중복/정렬은 _optimize_dataframe_memory 내부에서 처리되지만
        # 혹시 남은 중복에 대해 최신 값 우선으로 한 번 더 보정
        # df = _optimize_dataframe_memory(df, new, max_length).loc[~_optimize_dataframe_memory(df, new, max_length).index.duplicated(keep="last")].sort_index()
        # ✅ 한 번만 계산한 결과를 재사용하여 중복 호출/레이스 위험 제거
        tmp = _optimize_dataframe_memory(df, new, max_length)
        df = tmp.loc[~tmp.index.duplicated(keep="last")].sort_index()
        del tmp

        # 🔍 MERGE-DEBUG: 병합 후 DataFrame 상태
        try:
            _log("DEBUG", f"[병합 후] df.shape={df.shape} | df 마지막 3개: {list(df.tail(3).index)}")
        except Exception as e_merge_log:
            _log("WARN", f"[병합 후] 로깅 실패: {e_merge_log}")

        # 실시간 병합 후 DET 로깅 (로컬/서버 비교 핵심 지점)
        log_det(df, "LOOP_MERGED")

        # 🔍 PRICE-DEBUG: 실시간 병합 후 최종 데이터
        try:
            last_3 = df.tail(3)
            for idx, row in last_3.iterrows():
                _log("INFO", f"[PRICE-REALTIME-MERGED] {idx} | O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} C={row['Close']:.0f}")
        except Exception as e_log:
            _log("WARN", f"[PRICE-REALTIME-MERGED] 로깅 실패: {e_log}")

        # ★ Phase 2: 실시간 데이터도 DB에 저장 (점진적 히스토리 누적)
        if user_id and not new.empty:
            try:
                from services.db import save_candle_cache
                save_candle_cache(user_id, ticker, interval, new)
            except Exception as e:
                # 로그만 남기고 메인 루프는 계속 진행
                pass

        # 🛡️ 방안 4: Yield 직전 최종 연속성 검증
        if len(df) > 1:
            # 1) 인덱스 연속성 체크 (interval 간격이어야 함)
            time_diffs = df.index.to_series().diff().dt.total_seconds() / 60
            gaps_in_df = time_diffs[time_diffs > iv * 1.5]  # 1.5배 이상 차이나면 갭

            if not gaps_in_df.empty:
                gap_details = []
                for gap_idx, gap_minutes in gaps_in_df.items():
                    prev_idx = df.index[df.index.get_loc(gap_idx) - 1]
                    gap_details.append(f"  - {prev_idx} → {gap_idx} (갭: {gap_minutes:.0f}분, {gap_minutes/iv:.1f}봉)")

                _log("ERROR",
                    f"❌ [연속성 오류] DataFrame에 {len(gaps_in_df)}개 갭 발견!\n" +
                    "\n".join(gap_details)
                )

                # 🔥 선택 1) 에러 발생 (엄격 모드) - 운영 환경에서는 주석 처리
                # raise ValueError("DataFrame 연속성 검증 실패 - 데이터 누락 감지")

                # 🔥 선택 2) 경고만 남기고 진행 (관대 모드)
                _log("WARN", "⚠️ 연속성 오류 감지되었으나 진행 (관대 모드)")

        # 2) 예상 시각과 실제 last_open 비교
        expected_last = boundary_open
        actual_last = df.index[-1]
        time_diff_seconds = abs((actual_last - expected_last).total_seconds())

        if time_diff_seconds > iv * 60 * 0.5:  # 0.5봉 이상 차이
            time_diff_minutes = time_diff_seconds / 60
            _log("WARN",
                f"⚠️ [시간 불일치] 기대 마지막 봉: {expected_last} | "
                f"실제 마지막 봉: {actual_last} | "
                f"차이: {time_diff_minutes:.1f}분 ({time_diff_minutes/iv:.2f}봉)"
            )

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

    # ⚠️ 중요: pyupbit 인덱스는 이미 KST tz-naive로 반환됨
    if isinstance(df.index, pd.DatetimeIndex):
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is None:
            # ✅ pyupbit은 이미 KST naive로 반환하므로 그대로 사용
            pass
        else:
            # tz-aware인 경우에만 KST로 변환 후 tz 제거
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
