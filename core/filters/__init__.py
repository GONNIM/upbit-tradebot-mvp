"""
필터 시스템 - 매수/매도 필터 관리자
"""
from typing import List, Optional
import logging

from .base import BaseFilter, FilterResult, FilterCategory

logger = logging.getLogger(__name__)


class BuyFilterManager:
    """
    매수 필터 관리자

    등록된 모든 매수 필터를 순차적으로 실행하여
    하나라도 차단 조건이 감지되면 매수를 차단함.
    """

    def __init__(self):
        self.filters: List[BaseFilter] = []

    def register(self, filter_instance: BaseFilter):
        """필터 등록"""
        self.filters.append(filter_instance)
        logger.info(f"✅ Buy Filter registered: {filter_instance.get_name()}")

    def evaluate_all(self, **kwargs) -> Optional[FilterResult]:
        """
        모든 활성화된 매수 필터 평가

        Args:
            **kwargs: 필터 평가에 필요한 파라미터

        Returns:
            Optional[FilterResult]: 차단 필터가 있으면 해당 FilterResult 반환,
                                    모든 필터 통과 시 None 반환
        """
        for filter_instance in self.filters:
            if not filter_instance.is_enabled():
                continue

            result = filter_instance.evaluate(**kwargs)
            if result.should_block:
                logger.warning(
                    f"🚫 Buy blocked by {filter_instance.get_name()}: {result.reason}"
                )
                if result.details:
                    logger.info(f"   └─ {result.details}")
                return result

        return None  # 모든 필터 통과


class SellFilterManager:
    """
    매도 필터 관리자

    등록된 모든 매도 필터를 카테고리 순서대로 실행.
    실행 순서: CORE_STRATEGY → SELL_AUXILIARY

    핵심 전략 필터가 먼저 실행되고, 보조 필터는 나중에 실행됨.
    """

    def __init__(self):
        self.filters: List[BaseFilter] = []

    def register(self, filter_instance: BaseFilter):
        """필터 등록 (카테고리별 자동 정렬)"""
        self.filters.append(filter_instance)
        # 카테고리 우선순위에 따라 정렬
        self.filters.sort(key=lambda f: f.category.value)
        logger.info(f"✅ Sell Filter registered: {filter_instance.get_name()} (Category: {filter_instance.category.name})")

    def evaluate_all(self, **kwargs) -> Optional[FilterResult]:
        """
        모든 활성화된 매도 필터 평가 (카테고리 순서대로)

        Args:
            **kwargs: 필터 평가에 필요한 파라미터

        Returns:
            Optional[FilterResult]: 매도 조건이 감지되면 해당 FilterResult 반환,
                                    모든 필터 통과 시 None 반환
        """
        for filter_instance in self.filters:
            if not filter_instance.is_enabled():
                continue

            result = filter_instance.evaluate(**kwargs)
            if result.should_block:
                logger.info(
                    f"✅ Sell triggered by {filter_instance.get_name()}: {result.reason}"
                )
                if result.details:
                    logger.info(f"   └─ {result.details}")
                return result

        return None  # 모든 필터 통과 (매도 조건 없음)


# Export
__all__ = [
    'BaseFilter',
    'FilterResult',
    'FilterCategory',
    'BuyFilterManager',
    'SellFilterManager',
]
