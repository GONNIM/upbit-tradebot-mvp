"""
REST Reconcile - Upbit 공식 차트 정합성 보장 (리스크 헷지 최우선)

핵심 리스크 헷지:
1. REST 200개 제한 → 다중 호출로 400~500개 확보
2. REST 장애 → 재시도 3회 + fallback (local 유지)
3. 성능 → 캐싱 (동일 요청 1초 내 중복 금지)
"""
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
import logging
import time

from core.time_utils import now_utc, kst_to_utc, format_kst
from core.candle_clock import CandleClock

logger = logging.getLogger(__name__)


# ============================================================
# P0-1.3: REST 200개 제한 대응 - 다중 호출
# ============================================================

def fetch_candles_rest_full(
    market: str,
    timeframe: str,
    end_ts: datetime,
    total_count: int = 400
) -> pd.DataFrame:
    """
    Upbit REST API로 캔들 조회 (200개 제한 대응 다중 호출)

    🔒 리스크 헷지:
    - Upbit API 최대 200개 제한
    - EMA200 안정 계산 위해 400~500개 필요
    - 다중 호출로 확보 (3회 호출 → 600개 가능)

    Args:
        market: "KRW-SUI"
        timeframe: "minute1", "minute3", etc.
        end_ts: 조회 종료 시각 (UTC)
        total_count: 조회할 총 캔들 개수 (기본 400)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        Index: timestamp (UTC timezone aware)

    Example:
        >>> df = fetch_candles_rest_full("KRW-SUI", "minute1", now_utc(), 400)
        >>> len(df)
        400  # 200개 제한 우회
    """
    interval_sec = CandleClock.TIMEFRAME_SEC.get(timeframe)
    if interval_sec is None:
        logger.error(f"[REST] Unknown timeframe: {timeframe}")
        return pd.DataFrame()

    remain = total_count
    to = end_ts
    dfs = []
    batch_num = 0

    logger.info(
        f"[REST] 다중 호출 시작 | market={market} timeframe={timeframe} "
        f"total_count={total_count} end={format_kst(end_ts)}"
    )

    while remain > 0:
        batch_num += 1
        batch_size = min(200, remain)  # Upbit 최대 200개

        try:
            # Upbit API는 KST 문자열 입력
            to_kst_str = end_ts.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

            logger.debug(
                f"[REST] Batch #{batch_num} | count={batch_size} to={to_kst_str}"
            )

            df = pyupbit.get_ohlcv(
                ticker=market,
                interval=timeframe,
                to=to_kst_str,
                count=batch_size
            )

            if df is None or df.empty:
                logger.warning(
                    f"[REST] Batch #{batch_num} 응답 없음 | "
                    f"remain={remain} (이전 batch까지만 사용)"
                )
                break

            # ✅ 컬럼명 표준화 (pyupbit는 소문자 반환)
            # 대문자로 통일 (기존 코드와 호환)
            df.columns = [col.capitalize() for col in df.columns]

            # ✅ Timezone 변환: KST → UTC
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize("Asia/Seoul")

            df.index = df.index.tz_convert("UTC")

            # ✅ 표준화 (필요한 컬럼만 선택)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

            logger.debug(
                f"[REST] Batch #{batch_num} 성공 | received={len(df)} | "
                f"{format_kst(df.index[0])} ~ {format_kst(df.index[-1])}"
            )

            dfs.append(df)

            # 다음 조회 종료 시점 (가장 오래된 봉 - 1 interval)
            to = df.index[0] - timedelta(seconds=interval_sec)
            remain -= len(df)

            # API Rate Limit 보호 (0.1초 대기)
            if remain > 0:
                time.sleep(0.1)

        except Exception as e:
            logger.error(
                f"[REST] Batch #{batch_num} 실패 | {e} | "
                f"(이전 batch까지만 사용)"
            )
            break

    if not dfs:
        logger.error(f"[REST] 모든 batch 실패 | market={market}")
        return pd.DataFrame()

    # ✅ 병합 및 정렬
    result = pd.concat(dfs).sort_index()

    # ✅ 중복 제거 (혹시 모를 overlap)
    result = result[~result.index.duplicated(keep='first')]

    logger.info(
        f"[REST] 다중 호출 완료 | total={len(result)} batches={len(dfs)} | "
        f"{format_kst(result.index[0])} ~ {format_kst(result.index[-1])}"
    )

    return result


# ============================================================
# P0-1.4: REST 장애 대비 재시도 + fallback
# ============================================================

def safe_fetch_rest(
    market: str,
    timeframe: str,
    end_ts: datetime,
    total_count: int = 400
) -> Optional[pd.DataFrame]:
    """
    REST 조회 with 재시도 + fallback (리스크 헷지)

    🔒 리스크 헷지:
    - 네트워크 장애/API 오류 대비
    - 3회 재시도 (지수 백오프: 1초, 2초, 4초)
    - 최종 실패 시 None 반환 → caller가 local 유지

    Args:
        market: "KRW-SUI"
        timeframe: "minute1"
        end_ts: 조회 종료 시각 (UTC)
        total_count: 조회할 총 캔들 개수

    Returns:
        DataFrame 또는 None (3회 실패 시)

    Policy:
        - 1~3회 실패: 재시도
        - 최종 실패: None 반환 (local 유지)
        - caller는 다음 봉에서 반드시 재시도
    """
    max_retry = 3

    for attempt in range(1, max_retry + 1):
        try:
            logger.info(
                f"[REST-SAFE] 시도 #{attempt}/{max_retry} | "
                f"market={market} timeframe={timeframe}"
            )

            df = fetch_candles_rest_full(market, timeframe, end_ts, total_count)

            if not df.empty:
                logger.info(
                    f"[REST-SAFE] 성공 #{attempt}/{max_retry} | "
                    f"received={len(df)} bars"
                )
                return df
            else:
                logger.warning(
                    f"[REST-SAFE] 빈 응답 #{attempt}/{max_retry} | "
                    f"(재시도 예정)"
                )

        except Exception as e:
            logger.error(
                f"[REST-SAFE] 예외 발생 #{attempt}/{max_retry} | {e} | "
                f"(재시도 예정)"
            )

        # 재시도 대기 (지수 백오프)
        if attempt < max_retry:
            wait_sec = 2 ** (attempt - 1)  # 1초, 2초, 4초
            logger.info(f"[REST-SAFE] {wait_sec}초 후 재시도...")
            time.sleep(wait_sec)

    # ❌ 3회 모두 실패
    logger.error(
        f"[REST-SAFE] ❌ 최종 실패 ({max_retry}회) | "
        f"market={market} timeframe={timeframe} | "
        f"→ fallback: local 시계열 유지"
    )

    return None  # ✅ None 반환 → caller가 local 유지


# ============================================================
# P0-1.5: Reconcile (REST 기준 덮어쓰기)
# ============================================================

def reconcile_series(
    local_series: pd.DataFrame,
    rest_series: Optional[pd.DataFrame]
) -> Tuple[pd.DataFrame, Dict]:
    """
    로컬 시계열 vs REST 시계열 비교 후 병합 (REST 우선)

    🔒 리스크 헷지:
    - REST 실패 시 local 유지 (매매 중단 방지)
    - 변경 timestamp 추적 (부분 재계산용)

    Args:
        local_series: 봇 메모리의 캔들 시계열
        rest_series: REST에서 가져온 캔들 (None 가능)

    Returns:
        (merged_series, diff_summary)

        merged_series: REST 기준으로 덮어쓴 최종 시계열
        diff_summary: {
            "changed_count": 변경된 봉 개수,
            "changed_ts": 변경된 timestamp 리스트,
            "inserted_count": 새로 추가된 봉 개수,
            "rest_failed": REST 실패 여부 (bool)
        }

    Policy:
        - rest_series=None → local 그대로 유지
        - rest_series 있음 → REST 기준으로 덮어쓰기
        - 변경 발생 → changed_ts 반환 (재계산 트리거용)
    """
    # ✅ REST 실패 시 local 유지 (fallback)
    if rest_series is None:
        logger.warning(
            "[RECONCILE] REST 실패 → local 시계열 유지 (fallback)"
        )
        return local_series, {
            "changed_count": 0,
            "changed_ts": [],
            "inserted_count": 0,
            "rest_failed": True  # ✅ 중요: REST 실패 플래그
        }

    if rest_series.empty:
        logger.warning(
            "[RECONCILE] REST 빈 응답 → local 시계열 유지"
        )
        return local_series, {
            "changed_count": 0,
            "changed_ts": [],
            "inserted_count": 0,
            "rest_failed": True
        }

    # ✅ 변경 감지 (상대 오차 기준)
    PRICE_DIFF_THRESHOLD_PCT = 0.0001  # 0.01% 상대 오차
    changed_ts = []
    inserted_ts = []

    for ts in rest_series.index:
        if ts not in local_series.index:
            # 새로 추가된 봉
            inserted_ts.append(ts)
            changed_ts.append(ts)  # 재계산에 포함
        else:
            # 기존 봉 값 비교 (상대 오차 사용)
            rest_close = rest_series.loc[ts, 'Close']
            local_close = local_series.loc[ts, 'Close']

            # ✅ High-Risk Fix: 상대 오차(%) 사용 (저가/고가 코인 모두 대응)
            if local_close > 0:
                diff_pct = abs(rest_close - local_close) / local_close
                if diff_pct > PRICE_DIFF_THRESHOLD_PCT:
                    changed_ts.append(ts)
                    logger.debug(
                        f"[RECONCILE] 값 변경 감지 | {format_kst(ts)} | "
                        f"local={local_close:.2f} → rest={rest_close:.2f} (diff={diff_pct*100:.4f}%)"
                    )

    # ✅ REST 기준으로 병합 (REST 우선)
    merged = rest_series.copy()

    # ✅ Summary
    diff_summary = {
        "changed_count": len(changed_ts),
        "changed_ts": sorted(changed_ts),
        "inserted_count": len(inserted_ts),
        "rest_failed": False
    }

    if changed_ts:
        logger.warning(
            f"[RECONCILE] 변경 감지! | changed={len(changed_ts)} "
            f"inserted={len(inserted_ts)} | "
            f"범위: {format_kst(min(changed_ts))} ~ {format_kst(max(changed_ts))}"
        )
    else:
        logger.info(
            f"[RECONCILE] 변경 없음 | local={len(local_series)} rest={len(rest_series)}"
        )

    return merged, diff_summary


# ============================================================
# 캐싱 (성능 최적화)
# ============================================================

_rest_cache: Dict[str, Tuple[datetime, pd.DataFrame]] = {}
_cache_ttl_sec = 1.0  # 1초 캐시 (동일 요청 중복 방지)


def fetch_candles_rest_cached(
    market: str,
    timeframe: str,
    end_ts: datetime,
    total_count: int = 400
) -> Optional[pd.DataFrame]:
    """
    REST 조회 with 캐싱 (성능 최적화)

    Policy:
        - 동일 요청이 1초 내 발생 시 캐시 반환
        - 1초 초과 시 재조회
    """
    cache_key = f"{market}:{timeframe}:{end_ts.isoformat()}:{total_count}"

    # 캐시 확인
    if cache_key in _rest_cache:
        cached_time, cached_df = _rest_cache[cache_key]
        age = (now_utc() - cached_time).total_seconds()

        if age < _cache_ttl_sec:
            logger.debug(f"[REST-CACHE] HIT | age={age:.2f}s")
            return cached_df.copy()

    # 캐시 미스 → 조회
    logger.debug(f"[REST-CACHE] MISS | fetching...")
    df = safe_fetch_rest(market, timeframe, end_ts, total_count)

    if df is not None and not df.empty:
        _rest_cache[cache_key] = (now_utc(), df)

    return df


# ============================================================
# Import 수정 (zoneinfo 누락 방지)
# ============================================================

from zoneinfo import ZoneInfo
