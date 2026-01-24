"""
전략 액션 타입
Backtesting 라이브러리와 무관한 순수한 액션 정의
"""
from enum import Enum


class Action(Enum):
    """전략 평가 결과 액션"""
    BUY = "BUY"       # 매수
    SELL = "SELL"     # 매도
    CLOSE = "CLOSE"   # 청산 (SELL과 동일하지만 의미 구분)
    HOLD = "HOLD"     # 홀드 (아무 것도 하지 않음)
    NOOP = "NOOP"     # No Operation (평가 건너뜀)

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value
