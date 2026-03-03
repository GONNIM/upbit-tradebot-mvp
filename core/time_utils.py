"""
시간 처리 유틸리티 (UTC 기준 통일)

핵심 원칙:
- 내부 저장/계산: 모두 UTC
- 표시/로깅: KST 변환
- Upbit API: KST → UTC 변환
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# 타임존 상수
UTC = timezone.utc
KST = ZoneInfo("Asia/Seoul")


def now_utc() -> datetime:
    """
    현재 시각 (UTC 기준)

    Returns:
        datetime: UTC timezone aware
    """
    return datetime.now(UTC)


def now_kst() -> datetime:
    """
    현재 시각 (KST 기준, 표시용)

    Returns:
        datetime: KST timezone aware
    """
    return datetime.now(KST)


def kst_to_utc(dt: datetime) -> datetime:
    """
    KST → UTC 변환

    Args:
        dt: KST datetime (aware or naive)

    Returns:
        datetime: UTC timezone aware
    """
    if dt.tzinfo is None:
        # naive → KST로 가정
        dt = dt.replace(tzinfo=KST)

    return dt.astimezone(UTC)


def utc_to_kst(dt: datetime) -> datetime:
    """
    UTC → KST 변환 (표시용)

    Args:
        dt: UTC datetime

    Returns:
        datetime: KST timezone aware
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(KST)


def format_kst(dt: datetime) -> str:
    """
    datetime을 KST 문자열로 표시

    Args:
        dt: datetime (UTC 또는 KST)

    Returns:
        str: "2026-02-28 18:30:00 KST"
    """
    kst_dt = utc_to_kst(dt)
    return kst_dt.strftime("%Y-%m-%d %H:%M:%S KST")


def parse_upbit_timestamp(ts_str: str) -> datetime:
    """
    Upbit API timestamp 파싱 (KST → UTC)

    Args:
        ts_str: "2026-02-28 18:30:00" (KST 기준)

    Returns:
        datetime: UTC timezone aware
    """
    # Upbit는 KST 문자열 반환
    kst_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    kst_dt = kst_dt.replace(tzinfo=KST)

    return kst_to_utc(kst_dt)


def floor_to_interval(dt: datetime, interval_sec: int) -> datetime:
    """
    주어진 interval로 내림 (UTC 기준)

    Args:
        dt: datetime (UTC)
        interval_sec: 봉 간격 (초)

    Returns:
        datetime: interval로 내림된 UTC datetime

    Example:
        >>> dt = datetime(2026, 2, 28, 9, 5, 42, tzinfo=UTC)
        >>> floor_to_interval(dt, 60)
        datetime(2026, 2, 28, 9, 5, 0, tzinfo=UTC)
    """
    epoch = int(dt.timestamp())
    floored_epoch = (epoch // interval_sec) * interval_sec
    return datetime.fromtimestamp(floored_epoch, tz=UTC)


def ceil_to_interval(dt: datetime, interval_sec: int) -> datetime:
    """
    주어진 interval로 올림 (UTC 기준)

    Args:
        dt: datetime (UTC)
        interval_sec: 봉 간격 (초)

    Returns:
        datetime: interval로 올림된 UTC datetime
    """
    epoch = int(dt.timestamp())
    ceiled_epoch = ((epoch + interval_sec - 1) // interval_sec) * interval_sec
    return datetime.fromtimestamp(ceiled_epoch, tz=UTC)
