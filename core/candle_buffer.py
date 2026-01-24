"""
캔들 버퍼 - 최근 N개 봉만 유지하는 링 버퍼
Backtest 없이 증분 처리를 위한 핵심 데이터 구조
"""
from collections import deque
from typing import Optional, List
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Bar:
    """단일 봉 데이터"""

    def __init__(
        self,
        ts,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        is_closed: bool = True
    ):
        self.ts = ts
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.is_closed = is_closed

    def __repr__(self):
        return f"Bar(ts={self.ts}, O={self.open:.0f}, H={self.high:.0f}, L={self.low:.0f}, C={self.close:.0f}, closed={self.is_closed})"


class CandleBuffer:
    """
    최근 N개 봉만 유지하는 링 버퍼
    - 메모리 효율적 (deque 사용)
    - 중복 방지 (타임스탬프 기준)
    - 백워드 호환 (DataFrame 변환 지원)
    """

    def __init__(self, maxlen: int = 500):
        """
        Args:
            maxlen: 최대 유지할 봉 개수 (기본 500)
        """
        self.buffer = deque(maxlen=maxlen)
        self.last_ts = None
        self.maxlen = maxlen

    def append(self, bar: Bar) -> bool:
        """
        새 봉 추가 (중복 방지)

        Args:
            bar: 추가할 봉

        Returns:
            bool: 추가 성공 여부 (중복이면 False)
        """
        if self.last_ts == bar.ts:
            return False  # 중복

        self.buffer.append(bar)
        self.last_ts = bar.ts
        return True

    def last_close(self) -> Optional[float]:
        """마지막 봉의 종가"""
        return self.buffer[-1].close if self.buffer else None

    def last_n_closes(self, n: int) -> List[float]:
        """
        최근 N개 봉의 종가 리스트 (초기 EMA 시드용)

        Args:
            n: 가져올 개수

        Returns:
            List[float]: 종가 리스트 (부족하면 있는 만큼)
        """
        closes = [b.close for b in self.buffer]
        return closes[-n:] if len(closes) >= n else closes

    def __len__(self):
        """버퍼 길이"""
        return len(self.buffer)

    def __getitem__(self, idx):
        """인덱싱 지원"""
        return self.buffer[idx]

    def to_dataframe(self) -> pd.DataFrame:
        """
        백워드 호환용: DataFrame으로 변환
        (기존 로그/차트 시스템과의 호환성)
        """
        if not self.buffer:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

        data = [{
            'Open': b.open,
            'High': b.high,
            'Low': b.low,
            'Close': b.close,
            'Volume': b.volume
        } for b in self.buffer]

        return pd.DataFrame(data, index=[b.ts for b in self.buffer])

    def get_last_bar(self) -> Optional[Bar]:
        """마지막 봉 가져오기"""
        return self.buffer[-1] if self.buffer else None

    def clear(self):
        """버퍼 초기화"""
        self.buffer.clear()
        self.last_ts = None
