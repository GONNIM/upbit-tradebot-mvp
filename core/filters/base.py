"""
필터 시스템 기본 클래스 및 인터페이스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class FilterCategory(Enum):
    """필터 카테고리 - 실행 우선순위 결정"""
    CORE_STRATEGY = 1    # 핵심 전략 (SL/TP/TS/DC) - 최우선
    BUY_FILTER = 2       # 매수 필터 (급등 차단 등)
    SELL_AUXILIARY = 3   # 매도 보조 필터 (정체 포지션 등) - 최후


@dataclass
class FilterResult:
    """필터 실행 결과"""
    should_block: bool           # True면 매수/매도 차단
    reason: str                  # 차단 사유 (예: "STALE_POSITION", "SURGE_FILTER")
    details: Optional[str] = None  # 상세 정보 (로깅용)
    metadata: Optional[Dict[str, Any]] = None  # 추가 메타데이터


class BaseFilter(ABC):
    """
    필터 기본 클래스

    모든 필터는 이 클래스를 상속받아 evaluate() 메서드를 구현해야 함.
    """

    def __init__(self, category: FilterCategory):
        self.category = category
        self.enabled = False

    @abstractmethod
    def evaluate(self, **kwargs) -> FilterResult:
        """
        필터 평가 로직

        Args:
            **kwargs: 필터 평가에 필요한 파라미터
                - bar: 현재 캔들 데이터
                - position: 포지션 정보 (매도 필터용)
                - ema_fast, ema_slow, ema_base: EMA 값들
                - 기타 필터별 필요한 데이터

        Returns:
            FilterResult: 필터 실행 결과
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """필터 이름 반환 (로깅 및 디버깅용)"""
        pass

    def is_enabled(self) -> bool:
        """필터 활성화 여부"""
        return self.enabled

    def set_enabled(self, enabled: bool):
        """필터 활성화/비활성화"""
        self.enabled = enabled
