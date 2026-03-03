"""
CandleClock - 시간 기반 봉 확정 관리 (UTC 기준)

핵심 원칙:
- WS 수신 여부와 무관하게 시간만으로 확정 판단
- 내부 계산은 모두 UTC 기준
"""
from datetime import datetime, timedelta
import logging
from core.time_utils import now_utc, floor_to_interval, format_kst

logger = logging.getLogger(__name__)


class CandleClock:
    """시간 기반 봉 확정 관리 (UTC 기준)"""

    TIMEFRAME_SEC = {
        "minute1": 60,
        "minute3": 180,
        "minute5": 300,
        "minute10": 600,
        "minute15": 900,
        "minute30": 1800,
        "minute60": 3600,
        "day": 86400,
    }

    def __init__(self, timeframe: str):
        """
        Args:
            timeframe: "minute1", "minute3", etc.
        """
        if timeframe not in self.TIMEFRAME_SEC:
            raise ValueError(f"Unknown timeframe: {timeframe}")

        self.timeframe = timeframe
        self.interval_sec = self.TIMEFRAME_SEC[timeframe]
        self.last_close_ts = None

        logger.info(
            f"[CLOCK] Initialized | timeframe={timeframe} interval={self.interval_sec}sec"
        )

    def should_close(self, now: datetime, tolerance_sec: int = 5) -> bool:
        """
        현재 시각이 봉 확정 시각인가 (UTC 기준, tolerance 포함)

        Args:
            now: 현재 시각 (UTC)
            tolerance_sec: 확정 시각 허용 오차 (초, 기본 5초)

        Returns:
            bool: True면 봉 확정 이벤트 발생

        Example:
            >>> clock = CandleClock("minute1")
            >>> now = datetime(2026, 2, 28, 9, 5, 0, tzinfo=UTC)  # 정각
            >>> clock.should_close(now)
            True
            >>> now = datetime(2026, 2, 28, 9, 5, 3, tzinfo=UTC)  # 3초 지남
            >>> clock.should_close(now, tolerance=5)
            True  # tolerance 내에 있음
            >>> now = datetime(2026, 2, 28, 9, 5, 30, tzinfo=UTC)  # 30초
            >>> clock.should_close(now)
            False
        """
        epoch = int(now.timestamp())
        last_close_epoch = (epoch // self.interval_sec) * self.interval_sec

        # 마지막 확정 시점부터 현재까지 경과 시간
        elapsed = epoch - last_close_epoch

        # ✅ Medium-Risk Fix: tolerance 내에 있으면 확정으로 간주
        is_close_time = elapsed <= tolerance_sec

        if is_close_time and elapsed > 0:
            logger.debug(f"[CLOCK] 봉 확정 시각 감지 (tolerance={tolerance_sec}s) | {format_kst(now)} | elapsed={elapsed}s")

        return is_close_time

    def get_closed_ts(self, now: datetime) -> datetime:
        """
        방금 확정된 봉의 timestamp (UTC 기준)

        Args:
            now: 현재 시각 (UTC)

        Returns:
            datetime: 확정된 봉의 시작 시각 (UTC)

        Example:
            >>> clock = CandleClock("minute1")
            >>> now = datetime(2026, 2, 28, 9, 5, 42, tzinfo=UTC)
            >>> closed = clock.get_closed_ts(now)
            >>> closed
            datetime(2026, 2, 28, 9, 5, 0, tzinfo=UTC)
        """
        closed_ts = floor_to_interval(now, self.interval_sec)

        logger.info(
            f"[CLOCK] 봉 확정 | closed={format_kst(closed_ts)} (UTC: {closed_ts.isoformat()})"
        )

        return closed_ts

    def next_close_time(self, now: datetime) -> datetime:
        """
        다음 확정 시각 계산 (UTC 기준)

        Args:
            now: 현재 시각 (UTC)

        Returns:
            datetime: 다음 봉 확정 시각 (UTC)

        Example:
            >>> clock = CandleClock("minute1")
            >>> now = datetime(2026, 2, 28, 9, 5, 42, tzinfo=UTC)
            >>> next_close = clock.next_close_time(now)
            >>> next_close
            datetime(2026, 2, 28, 9, 6, 0, tzinfo=UTC)
        """
        current_close = floor_to_interval(now, self.interval_sec)
        next_close = current_close + timedelta(seconds=self.interval_sec)

        return next_close

    def wait_seconds_until_close(self, now: datetime) -> float:
        """
        다음 확정까지 남은 시간 (초)

        Args:
            now: 현재 시각 (UTC)

        Returns:
            float: 남은 시간 (초)
        """
        next_close = self.next_close_time(now)
        remaining = (next_close - now).total_seconds()

        return max(0.0, remaining)

    def is_duplicate_close(self, closed_ts: datetime) -> bool:
        """
        이미 처리한 확정 봉인지 확인 (중복 방지)

        Args:
            closed_ts: 확정된 봉의 timestamp

        Returns:
            bool: True면 중복 (skip 필요)
        """
        if self.last_close_ts is None:
            self.last_close_ts = closed_ts
            return False

        if closed_ts == self.last_close_ts:
            logger.warning(f"[CLOCK] 중복 확정 감지 (skip) | {format_kst(closed_ts)}")
            return True

        if closed_ts < self.last_close_ts:
            logger.error(
                f"[CLOCK] 과거 봉 확정 시도 (skip) | "
                f"closed={format_kst(closed_ts)} last={format_kst(self.last_close_ts)}"
            )
            return True

        self.last_close_ts = closed_ts
        return False
