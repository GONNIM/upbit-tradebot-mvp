"""
REST Reconcile - Upbit 공식 차트 정합성 보장 (리스크 헷지 최우선)

핵심 리스크 헷지:
1. REST 200개 제한 → 다중 호출로 400~500개 확보
2. REST 장애 → 재시도 3회 + fallback (local 유지)
3. 성능 → 캐싱 (동일 요청 1초 내 중복 금지)
"""
import pyupbit
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, List, Union, Any
import logging
import time

from core.time_utils import now_utc, kst_to_utc, format_kst
from core.candle_clock import CandleClock

logger = logging.getLogger(__name__)

# ✅ 2026-08-05 P4: fetch_confirmed_candle 연속 실패 카운터.
# 매 봉 REST 실패 시 로그 레벨을 INFO 로 낮추되(정상 fallback 흐름), 5회 이상
# 누적 실패는 지속 이슈 신호이므로 Telegram CRITICAL 알림.
_confirmed_fetch_consecutive_failures: Dict[str, int] = {}
_CONFIRMED_FETCH_CRITICAL_THRESHOLD = 5

# ✅ WO-6 (2026-08-25): 무거래 봉 센티널.
# Upbit 는 무거래 분에 봉을 만들지 않는다. 가짜 봉을 합성하면 지표가 차트와
# 어긋나므로, 별도 표지로 반환하여 호출부가 그 봉을 건너뛰도록 한다.
class _NoTradeMarker:
    """무거래 봉 표지 (센티널). 절대 pd.Series 로 다뤄서는 안 됨."""
    def __repr__(self) -> str:
        return "NO_TRADE"

NO_TRADE: Any = _NoTradeMarker()

# ✅ WO-6 (2026-08-25): 케이스 B (다음 봉 미존재) 안정화 확인 상태.
# 키: (ticker, closed_ts), 값: (first_check_ts, first_close)
# 5초 뒤 재조회에서 종가가 같으면 확정, 다르면 다음 조회의 케이스로 재판정.
_case_b_state: Dict[Tuple[str, datetime], Tuple[datetime, float]] = {}
_CASE_B_STABILIZATION_SEC = 5
_CASE_B_STATE_MAX_AGE_SEC = 1800  # 30분. 오래된 항목 자동 삭제 상한 (안전장치).


def _case_b_state_gc(now: datetime) -> None:
    """오래된 _case_b_state 항목을 자동 삭제 (안전장치).

    함수 이상 종료 등으로 정리되지 못한 항목이 전역 dict 에 누적되는 것을
    방지한다. closed_ts 가 30 분 이전인 항목은 삭제한다.
    """
    threshold = now - timedelta(seconds=_CASE_B_STATE_MAX_AGE_SEC)
    stale_keys = [
        key for key, (_, _) in list(_case_b_state.items())
        if key[1] < threshold
    ]
    for key in stale_keys:
        _case_b_state.pop(key, None)
    if stale_keys:
        logger.debug(f"[RECONCILE] _case_b_state GC: {len(stale_keys)}개 항목 삭제")


def _has_trades_in_minute(ticker: str, closed_ts: datetime) -> Optional[bool]:
    """✅ WO-6 보완 F1b (2026-08-29): 특정 분에 체결이 있었는지 ticks API 로 확인.

    /v1/trades/ticks 는 당일 UTC 기준 최근 체결만 반환한다. 재시도 소진 시점의
    closed_ts 는 수십초~수분 전 봉이므로 당일 데이터로 충분히 판별 가능.

    Args:
        ticker: 예 'KRW-JTO'
        closed_ts: 대상 봉 시작 시각 (UTC, timezone-aware)

    Returns:
        True  → 체결 존재
        False → 체결 0건
        None  → API 실패 등 판별 불가 (호출부는 보수적으로 None 취급)
    """
    try:
        # to 파라미터: 대상 봉 종료 후 1초 (UTC HH:mm:ss)
        boundary_utc = closed_ts + timedelta(seconds=60)
        to_str = boundary_utc.strftime('%H:%M:%S')
        r = requests.get(
            'https://api.upbit.com/v1/trades/ticks',
            params={'market': ticker, 'count': 500, 'to': to_str},
            timeout=3,
        )
        if r.status_code != 200:
            logger.debug(f"[RECONCILE] ticks API HTTP {r.status_code}")
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        # 대상 분 필터: trade_time_utc 이 closed_ts 와 같은 분
        minute_prefix_utc = closed_ts.strftime('%H:%M:')
        for t in data:
            tt = t.get('trade_time_utc', '')
            if tt.startswith(minute_prefix_utc):
                return True
        return False
    except Exception as e:
        logger.debug(f"[RECONCILE] ticks API 예외: {e}")
        return None


def _classify_no_trade_after_exhaustion(
    ticker: str, timeframe: str, closed_ts: datetime
) -> Optional[Any]:
    """✅ WO-6 보완 F1 (2026-08-26) + F1b (2026-08-29): 재시도 소진 후 무거래 판별.

    무거래 봉인데 다음 봉조차 아직 반영 안 된 경우, 케이스 B/C 재시도가 모두
    소진되어 None 이 반환되고 실패 계수가 쌓인다. 조용한 시간대에는 이것이
    거짓 CRITICAL 알림으로 이어진다.

    ## F1 판별 (get_ohlcv 기반)
    - latest_ts > closed_ts + closed_ts not in df.index → NO_TRADE (확정)
    - latest_ts >= closed_ts + closed_ts in df.index → None (거래 있음)
    - latest_ts < closed_ts → F1b 로 보조 판별

    ## F1b 판별 (trades/ticks 보조)
    - 연속 무거래 시작 지점(latest_ts < closed_ts)에서 ticks API 로 체결 여부 확인.
    - 체결 0건 → NO_TRADE 반환 (실패 계수 미가산)
    - 체결 존재 → None 유지 (기존 실패 흐름)
    - ticks 실패 → None 유지 (보수적)

    Returns:
        NO_TRADE 센티널 → 확정적으로 무거래
        None → 거래 있음 or 판별 불가 (호출부는 기존 실패 흐름으로 진행)
    """
    try:
        df = pyupbit.get_ohlcv(ticker=ticker, interval=timeframe, count=10)
        if df is None or df.empty:
            # F1b 보조: 응답 자체가 없어도 ticks 로 확인
            has_trade = _has_trades_in_minute(ticker, closed_ts)
            if has_trade is False:
                return NO_TRADE
            return None
        df.columns = [c.capitalize() for c in df.columns]
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("Asia/Seoul")
        df.index = df.index.tz_convert("UTC")

        latest_ts = df.index[-1]
        if latest_ts < closed_ts:
            # F1b: REST 반영 아직 안 됨 → ticks 로 체결 여부 확인
            has_trade = _has_trades_in_minute(ticker, closed_ts)
            if has_trade is False:
                logger.info(
                    f"[RECONCILE] F1b ticks 체결 0건 확인 → NO_TRADE | "
                    f"ts={format_kst(closed_ts)}"
                )
                return NO_TRADE
            # has_trade True 또는 None → None 유지
            return None

        # latest_ts >= closed_ts: 다음 봉(또는 대상 봉)이 응답에 있음
        if closed_ts in df.index:
            # 거래 있었음 → 기존 실패 흐름 유지
            return None
        # 다음 봉 존재하는데 대상 봉 없음 → 무거래 확정
        return NO_TRADE
    except Exception as e:
        logger.warning(f"[RECONCILE] 소진 후 무거래 판별 예외: {e}")
        return None


# ============================================================
# P0-1.3: REST 200개 제한 대응 - 다중 호출
# ============================================================

def fetch_candles_rest_full(
    market: str,
    timeframe: str,
    end_ts: Optional[datetime],
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
        end_ts: 조회 종료 시각 (UTC) - None이면 to 파라미터 없이 최신 확정 봉만 조회
        total_count: 조회할 총 캔들 개수 (기본 400)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        Index: timestamp (UTC timezone aware)

    Example:
        >>> df = fetch_candles_rest_full("KRW-SUI", "minute1", now_utc(), 400)
        >>> len(df)
        400  # 200개 제한 우회
        >>> df = fetch_candles_rest_full("KRW-SUI", "minute1", None, 200)
        >>> # to 파라미터 없음 → 확정 봉만 반환
    """
    interval_sec = CandleClock.TIMEFRAME_SEC.get(timeframe)
    if interval_sec is None:
        logger.error(f"[REST] Unknown timeframe: {timeframe}")
        return pd.DataFrame()

    remain = total_count
    to = end_ts
    dfs = []
    batch_num = 0

    end_str = format_kst(end_ts) if end_ts else "None (최신 확정 봉)"
    logger.info(
        f"[REST] 다중 호출 시작 | market={market} timeframe={timeframe} "
        f"total_count={total_count} end={end_str}"
    )

    while remain > 0:
        batch_num += 1
        batch_size = min(200, remain)  # Upbit 최대 200개

        try:
            # ============================================================
            # WO-2026-001 Task 1-A: 최신 batch만 to 없이 조회 (확정 종가 보장)
            # ============================================================
            if batch_num == 1:
                # ✅ 첫 번째 batch: to 파라미터 없음 → Upbit 확정 봉만 반환
                logger.debug(
                    f"[REST] Batch #{batch_num} (최신 확정 봉) | count={batch_size} | to=None"
                )

                df = pyupbit.get_ohlcv(
                    ticker=market,
                    interval=timeframe,
                    count=batch_size
                )
            else:
                # 나머지 batch: 과거 데이터는 to 사용 (이미 확정됨)
                to_kst_str = to.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

                logger.debug(
                    f"[REST] Batch #{batch_num} (과거 확정 봉) | count={batch_size} | to={to_kst_str}"
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

            # ============================================================
            # WO-2026-001 Task 1-C: 종가 검증 로그 추가
            # ============================================================
            if batch_num == 1:
                # 최신 봉 상세 로그 (Upbit 차트와 비교 가능)
                latest_row = df.iloc[-1]
                logger.info(
                    f"[REST] 최신 확정 봉 ✅ | ts={format_kst(df.index[-1])} | "
                    f"close={latest_row['Close']:.0f} | high={latest_row['High']:.0f} | "
                    f"low={latest_row['Low']:.0f} | volume={latest_row['Volume']:.2f}"
                )

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
    end_ts: Optional[datetime],
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
        end_ts: 조회 종료 시각 (UTC) - None이면 to 파라미터 없이 최신 확정 봉만 조회
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
    # 🔧 Fix: Local을 기반으로 REST로 덮어쓰기 (이전 데이터 유지)
    # Before: merged = rest_series.copy()  # ← REST 400개만 복사 (이전 100개 버려짐)
    # After: Local 기반으로 REST 범위만 덮어쓰기
    if local_series.empty:
        # Local이 비어있으면 REST를 그대로 사용
        merged = rest_series.copy()
    else:
        # Local을 복사한 후 REST 데이터로 덮어쓰기
        merged = local_series.copy()
        # REST 범위의 봉들을 덮어쓰기 (같은 timestamp의 모든 컬럼 업데이트)
        for ts in rest_series.index:
            merged.loc[ts] = rest_series.loc[ts]

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


# ============================================================
# WO-2026-001 Task 1-A: 확정 종가 보장 함수
# ============================================================

def fetch_confirmed_candle(
    ticker: str,
    timeframe: str,
    closed_ts: datetime,
    max_retry: int = None
) -> Union[pd.Series, None, Any]:
    """
    확정 종가만 반환. to 파라미터 없이 최신 봉 조회.

    🔒 WO-2026-001 Task 1-A + Issue #8 강화:
    - to 파라미터 완전 제거 → Upbit가 확정한 최신 봉만 반환
    - closed_ts 일치 여부 검증
    - Progressive Retry → interval의 50% 시간까지만 대기
    - 최대 재시도 초과 시 None 반환 → BACKFILL로 처리

    ✅ WO-6 (2026-08-25) 개편:
    - 케이스 처리 순서: A(다음 봉 존재) → C(API 지연) → B(다음 봉 미존재)
    - 무거래 봉은 NO_TRADE 표지 반환 (가짜 봉 합성 금지)
    - 케이스 B는 5초 안정화 1회 (재시도 스케줄 강등 대신)
    - closed_ts 는 Upbit 봉 시작 시각과 일치 (candle_clock.get_closed_ts 재정의 이후)

    Args:
        ticker: 종목 코드 (예: KRW-BTC)
        timeframe: "minute1", "minute3", etc.
        closed_ts: 방금 확정된 봉의 시작 timestamp (UTC, timezone-aware,
                   Upbit 봉 시작 시각과 일치)
        max_retry: 최대 재시도 횟수 (None이면 interval에 따라 자동 계산)

    Returns:
        pd.Series: 확정 봉 row (케이스 A 거래 있음, 케이스 B 안정화 확정)
        NO_TRADE (센티널): 대상 봉 자체가 무거래 (케이스 A 하위, 봉 자체 없음)
        None: 재시도 초과 실패 (호출부가 재조정 계속 진행)

    Example:
        >>> from datetime import datetime, timezone
        >>> closed_ts = datetime(2026, 3, 14, 7, 5, 0, tzinfo=timezone.utc)
        >>> result = fetch_confirmed_candle("KRW-BTC", "minute1", closed_ts)
        >>> if result is None:
        ...     print("재시도 초과, 재조정 계속 진행")
        >>> elif result is NO_TRADE:
        ...     print("무거래 봉, 건너뛰기")
        >>> else:
        ...     print(f"확정 종가: {result['Close']:.0f}")
    """
    # Interval별 재시도 횟수 계산 (interval의 50% 시간만 사용)
    # - 1분봉: (60초 - 5초 JITTER) * 50% = 27초 → 5회
    # - 3분봉: (180초 - 5초 JITTER) * 50% = 87초 → 17회
    if max_retry is None:
        interval_sec = CandleClock.TIMEFRAME_SEC.get(timeframe, 60)
        jitter = 5  # JITTER_BY_INTERVAL 기본값
        available_time = (interval_sec - jitter) * 0.5  # 50%만 사용
        max_retry = max(1, int(available_time / 5))  # 5초 간격
        logger.debug(
            f"[RECONCILE] 자동 계산된 재시도 | interval={timeframe} "
            f"interval_sec={interval_sec} max_retry={max_retry} "
            f"max_wait={max_retry * 5}초"
        )

    WAIT_SCHEDULE = [5] * max_retry  # 5초씩 max_retry회
    state_key = (ticker, closed_ts)

    # ✅ WO-6 안전장치: 함수 진입 시마다 오래된 _case_b_state 항목 GC
    _case_b_state_gc(datetime.now(timezone.utc))

    for attempt in range(max_retry):
        try:
            # ✅ to 파라미터 없음 → Upbit가 확정한 최신 봉만 반환
            logger.debug(
                f"[RECONCILE] 확정 봉 조회 시도 {attempt+1}/{max_retry} | "
                f"ticker={ticker} timeframe={timeframe}"
            )

            df = pyupbit.get_ohlcv(
                ticker=ticker,
                interval=timeframe,
                count=10  # 최신 10개 조회 (closed_ts 포함 여부 확인용)
            )

            if df is None or df.empty:
                wait = WAIT_SCHEDULE[attempt] if attempt < len(WAIT_SCHEDULE) else 12
                logger.warning(
                    f"[RECONCILE] 빈 응답 | 재시도 {attempt+1}/{max_retry} | {wait}초 대기"
                )
                time.sleep(wait)
                continue

            # ✅ 컬럼명 표준화
            df.columns = [col.capitalize() for col in df.columns]

            # ✅ Timezone 변환: KST → UTC
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize("Asia/Seoul")
            df.index = df.index.tz_convert("UTC")

            # ✅ 최신 봉 timestamp 추출
            latest_ts = df.index[-1]

            # ============================================================
            # WO-6 개편: 케이스 A → C → B 순서로 판정
            # ============================================================

            # 케이스 A: 다음 봉 존재 → 즉시 확정 (다음 봉 거래 = 이전 봉 마감 확실)
            if latest_ts > closed_ts:
                _case_b_state.pop(state_key, None)  # 이전 안정화 상태 정리
                if closed_ts in df.index:
                    # 거래 있음: 정상 확정
                    close_price = df.loc[closed_ts, "Close"]
                    logger.info(
                        f"[RECONCILE] 확정 종가 (다음 봉 존재) ✅ | ts={format_kst(closed_ts)} | "
                        f"close={close_price:.0f} | high={df.loc[closed_ts, 'High']:.0f} | "
                        f"low={df.loc[closed_ts, 'Low']:.0f} | volume={df.loc[closed_ts, 'Volume']:.2f}"
                    )
                    _confirmed_fetch_consecutive_failures[ticker] = 0
                    return df.loc[closed_ts]
                else:
                    # 무거래 봉: NO_TRADE 표지 (가짜 봉 합성 없음, 실패 아님)
                    logger.info(
                        f"[RECONCILE] 무거래 봉 감지 (NO_TRADE, 건너뜀) | "
                        f"ts={format_kst(closed_ts)} | df_range={format_kst(df.index[0])}~{format_kst(df.index[-1])}"
                    )
                    _confirmed_fetch_consecutive_failures[ticker] = 0  # 실패 계수 리셋 (정상 흐름)
                    return NO_TRADE

            # 케이스 C: latest_ts < closed_ts → API 지연, 재시도
            elif latest_ts < closed_ts:
                _case_b_state.pop(state_key, None)  # 상태 정리
                wait = WAIT_SCHEDULE[attempt] if attempt < len(WAIT_SCHEDULE) else 12
                logger.warning(
                    f"[RECONCILE] 봉 미반영 | 기대={format_kst(closed_ts)} "
                    f"실제={format_kst(latest_ts)} | {wait}초 대기 (시도 {attempt+1}/{max_retry})"
                )
                time.sleep(wait)

            # 케이스 B: latest_ts == closed_ts → 다음 봉 미존재, 5초 안정화 1회
            else:
                current_close = float(df.iloc[-1]["Close"])
                now_ts = datetime.now(timezone.utc)

                if state_key not in _case_b_state:
                    # 첫 진입: 5초 뒤 재조회 예약 (안정화 대기)
                    _case_b_state[state_key] = (now_ts, current_close)
                    logger.info(
                        f"[RECONCILE] 케이스 B 첫 진입 (5초 안정화 대기) | "
                        f"ts={format_kst(closed_ts)} | close={current_close:.0f}"
                    )
                    time.sleep(_CASE_B_STABILIZATION_SEC)
                    continue

                first_ts, first_close = _case_b_state[state_key]
                if current_close == first_close:
                    # 안정화 확인 → 확정 (5초간 종가 불변)
                    _case_b_state.pop(state_key, None)
                    logger.info(
                        f"[RECONCILE] 케이스 B 안정화 확정 ✅ | ts={format_kst(closed_ts)} | "
                        f"close={current_close:.0f} | 안정화 대기={_CASE_B_STABILIZATION_SEC}s"
                    )
                    _confirmed_fetch_consecutive_failures[ticker] = 0
                    return df.iloc[-1]
                else:
                    # 종가 변경 → 다음 조회의 케이스로 재판정 (한 번만 더 대기)
                    _case_b_state[state_key] = (now_ts, current_close)
                    logger.info(
                        f"[RECONCILE] 케이스 B 종가 변경 (재판정 대기) | ts={format_kst(closed_ts)} | "
                        f"old_close={first_close:.0f} → new_close={current_close:.0f}"
                    )
                    time.sleep(_CASE_B_STABILIZATION_SEC)
                    continue

        except Exception as e:
            # ✅ WO-6: 예외 발생 시에도 상태 정리 (재시도 흐름을 초기화)
            _case_b_state.pop(state_key, None)
            wait = WAIT_SCHEDULE[attempt] if attempt < len(WAIT_SCHEDULE) else 12
            logger.error(
                f"[RECONCILE] 예외 발생 | {e} | 재시도 {attempt+1}/{max_retry} | {wait}초 대기"
            )
            time.sleep(wait)

    # 재시도 초과 → 상태 정리
    _case_b_state.pop(state_key, None)

    # ✅ WO-6 보완 F1 (2026-08-26): 재시도 소진 후 무거래 여부 최종 판별.
    # 무거래 봉이 확인되면 NO_TRADE 반환 (실패 계수 미가산, 거짓 CRITICAL 방지).
    _verdict = _classify_no_trade_after_exhaustion(ticker, timeframe, closed_ts)
    if _verdict is NO_TRADE:
        logger.info(
            f"[RECONCILE] 재시도 소진 후 무거래 확정 (NO_TRADE, 건너뜀) | "
            f"ts={format_kst(closed_ts)} — 실패 계수 미가산"
        )
        _confirmed_fetch_consecutive_failures[ticker] = 0  # 실패 계수 리셋
        return NO_TRADE

    # ❌ 최대 재시도 초과 → BACKFILL fallback (정상 설계 흐름이므로 INFO 레벨)
    total_wait = sum(WAIT_SCHEDULE[:max_retry])
    # ✅ P4: 연속 실패 카운터 증가 + 임계 초과 시 CRITICAL notify
    _fails = _confirmed_fetch_consecutive_failures.get(ticker, 0) + 1
    _confirmed_fetch_consecutive_failures[ticker] = _fails

    if _fails >= _CONFIRMED_FETCH_CRITICAL_THRESHOLD:
        # 지속 실패 = REST 자체 이슈 or Upbit rate-limit → CRITICAL notify
        logger.warning(
            f"🚨 [RECONCILE] 연속 {_fails}회 실패 (임계 {_CONFIRMED_FETCH_CRITICAL_THRESHOLD} 초과) | "
            f"ticker={ticker} ts={format_kst(closed_ts)} | Upbit rate-limit or 네트워크 지속 이슈 의심"
        )
        try:
            from services.notifier import send as _notify, LEVEL_CRITICAL
            _notify(
                LEVEL_CRITICAL,
                f"🚨 [REST-RECONCILE] {ticker} 연속 {_fails}회 실패",
                (
                    f"fetch_confirmed_candle 이 연속 {_fails}회 실패 (임계 "
                    f"{_CONFIRMED_FETCH_CRITICAL_THRESHOLD} 초과).\n"
                    f"ticker: {ticker}\n"
                    f"봉 시각: {format_kst(closed_ts)}\n\n"
                    f"💡 Upbit API rate-limit 또는 네트워크 지속 이슈 확인 필요.\n"
                    f"BACKFILL 로 자동 fallback 되나 매매 정확성 저하 위험."
                ),
                dedupe_key=f"rest_reconcile_fail:{ticker}",
                dedupe_ttl=300,  # 5분 dedupe (연속 실패 지속 시 5분마다 재알림)
            )
        except Exception:
            pass
    else:
        # 임계 미만: 정상 fallback 흐름 (BACKFILL 로 흡수됨) → INFO 레벨
        logger.info(
            f"[RECONCILE] 재시도 초과 → BACKFILL fallback ({_fails}/{_CONFIRMED_FETCH_CRITICAL_THRESHOLD}) | "
            f"({max_retry}회, {total_wait}초) | ts={format_kst(closed_ts)}"
        )
    return None


# ============================================================
# Issue #8: 과거 봉 최종종가 검증 시스템
# ============================================================

def verify_past_candles_with_upbit(
    ticker: str,
    timeframe: str,
    past_series: pd.DataFrame,
    tolerance: float = 1.0
) -> bool:
    """
    과거 봉들이 Upbit 차트와 일치하는지 검증

    🎯 목적:
    - 이전 봉들(n-1, n-2, ...)은 반드시 Upbit 차트와 동일해야 함
    - 현재 봉(n)은 미확정 허용 (즉시 매매 유지)

    🔒 검증 프로세스:
    1. Upbit REST API에서 동일 시각 봉 조회
    2. 종가 비교 (±tolerance 이내)
    3. 불일치 발견 시:
       - 5초 간격 3회 재조회
       - 재조회 실패 → False 반환 (봉 스킵)
    4. 모두 일치 → True 반환

    Args:
        ticker: 종목 코드 (예: KRW-BTC)
        timeframe: "minute1", "minute3", etc.
        past_series: 과거 봉 DataFrame (현재 봉 제외)
        tolerance: 허용 오차 (기본 ±1원)

    Returns:
        True: 모든 과거 봉이 Upbit와 일치
        False: 불일치 발견 또는 조회 실패

    Example:
        >>> past_series = local_series[local_series.index < closed_ts]
        >>> ok = verify_past_candles_with_upbit("KRW-BTC", "minute1", past_series.tail(200))
        >>> if not ok:
        ...     logger.error("과거 봉 검증 실패 → 봉 스킵")
    """
    if past_series.empty:
        logger.info("[VERIFY] 과거 봉 없음 → 검증 스킵")
        return True

    timestamps = past_series.index.tolist()
    logger.info(
        f"[VERIFY] 과거 봉 검증 시작 | count={len(timestamps)} | "
        f"range={format_kst(timestamps[0])} ~ {format_kst(timestamps[-1])}"
    )

    # ============================================================
    # Step 1: Upbit에서 동일 시각 봉 조회
    # ============================================================
    try:
        # 과거 봉 범위 조회 (가장 오래된 ~ 가장 최신)
        start_ts = timestamps[0]
        end_ts = timestamps[-1]

        # 필요한 봉 개수 (+10% 여유분)
        required_count = int(len(timestamps) * 1.1)

        logger.debug(
            f"[VERIFY] Upbit REST API 호출 | "
            f"start={format_kst(start_ts)} end={format_kst(end_ts)} count={required_count}"
        )

        upbit_df = safe_fetch_rest(
            market=ticker,
            timeframe=timeframe,
            end_ts=end_ts,
            total_count=required_count
        )

        if upbit_df is None or upbit_df.empty:
            logger.error("[VERIFY] ❌ Upbit 조회 실패 → 검증 실패")
            return False

        logger.debug(
            f"[VERIFY] Upbit 조회 성공 | received={len(upbit_df)} | "
            f"range={format_kst(upbit_df.index[0])} ~ {format_kst(upbit_df.index[-1])}"
        )

    except Exception as e:
        logger.error(f"[VERIFY] ❌ Upbit 조회 예외 | {e} → 검증 실패")
        return False

    # ============================================================
    # Step 2: 종가 비교
    # ============================================================
    mismatch_count = 0
    fixed_count = 0

    for ts in timestamps:
        if ts not in upbit_df.index:
            logger.warning(f"[VERIFY] ⚠️ Upbit에 없는 timestamp | ts={format_kst(ts)} (스킵)")
            continue

        local_close = past_series.loc[ts, 'Close']
        upbit_close = upbit_df.loc[ts, 'Close']
        diff = abs(local_close - upbit_close)

        if diff > tolerance:
            mismatch_count += 1
            logger.warning(
                f"[VERIFY] 불일치 발견 | ts={format_kst(ts)} | "
                f"local={local_close:.0f} upbit={upbit_close:.0f} diff={diff:.0f}"
            )

            # ============================================================
            # Step 3: 재조회 3회
            # ============================================================
            retry_success = False
            for retry_num in range(1, 4):
                logger.info(f"[VERIFY-RETRY] {retry_num}/3회 재조회 | ts={format_kst(ts)}")
                time.sleep(5)

                try:
                    retry_candle = fetch_confirmed_candle(
                        ticker=ticker,
                        timeframe=timeframe,
                        closed_ts=ts,
                        max_retry=1  # 단일 재시도
                    )

                    if retry_candle is not None:
                        retry_close = retry_candle['Close']
                        retry_diff = abs(local_close - retry_close)

                        if retry_diff <= tolerance:
                            logger.info(
                                f"[VERIFY-RETRY] ✅ 재조회 성공 ({retry_num}/3) | "
                                f"ts={format_kst(ts)} | close={retry_close:.0f}"
                            )
                            retry_success = True
                            fixed_count += 1
                            break
                        else:
                            logger.warning(
                                f"[VERIFY-RETRY] 여전히 불일치 ({retry_num}/3) | "
                                f"diff={retry_diff:.0f}"
                            )
                    else:
                        logger.warning(f"[VERIFY-RETRY] 조회 실패 ({retry_num}/3)")

                except Exception as e:
                    logger.error(f"[VERIFY-RETRY] 예외 ({retry_num}/3) | {e}")

            if not retry_success:
                logger.error(
                    f"[VERIFY] ❌ 재조회 모두 실패 | ts={format_kst(ts)} | "
                    f"local={local_close:.0f} upbit={upbit_close:.0f} | "
                    f"→ 검증 실패"
                )
                return False

    # ============================================================
    # Step 4: 검증 완료
    # ============================================================
    if mismatch_count == 0:
        logger.info(
            f"[VERIFY] ✅ 모든 과거 봉 일치 | count={len(timestamps)} | "
            f"tolerance=±{tolerance:.0f}원"
        )
    else:
        logger.info(
            f"[VERIFY] ✅ 검증 통과 (재조회 보정) | "
            f"total={len(timestamps)} mismatch={mismatch_count} fixed={fixed_count}"
        )

    return True
