"""
실거래 포지션 상태 관리
Backtesting 라이브러리의 self.position과 완전히 분리
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PositionState:
    """
    실거래 포지션 상태
    - Backtesting 라이브러리와 무관
    - 실제 지갑 잔고 기반으로 관리
    """

    def __init__(self):
        self.has_position: bool = False           # 포지션 보유 여부
        self.qty: float = 0.0                     # 보유 수량
        self.avg_price: Optional[float] = None    # 평균 단가
        self.entry_bar: Optional[int] = None      # 진입 시점 bar index
        self.entry_ts = None                       # 진입 시점 타임스탬프
        self.pending_order: bool = False           # 주문 진행 중 여부
        self.last_action_ts = None                 # 마지막 액션 타임스탬프

        # 추가: Trailing Stop / Highest Price 추적용
        self.highest_price: Optional[float] = None
        self.trailing_armed: bool = False

    def open_position(self, qty: float, price: float, bar_idx: int, ts):
        """
        매수 완료 (포지션 오픈)

        Args:
            qty: 매수 수량
            price: 매수 단가
            bar_idx: 진입 bar index
            ts: 진입 타임스탬프
        """
        self.has_position = True
        self.qty = qty
        self.avg_price = price
        self.entry_bar = bar_idx
        self.entry_ts = ts
        self.last_action_ts = ts
        self.pending_order = False

        # Trailing Stop 초기화
        self.highest_price = price
        self.trailing_armed = False

        logger.info(
            f"✅ Position OPEN | qty={qty:.6f} price={price:.2f} bar={bar_idx}"
        )

    def close_position(self, ts):
        """
        매도 완료 (포지션 청산)

        Args:
            ts: 청산 타임스탬프
        """
        logger.info(
            f"✅ Position CLOSE | qty={self.qty:.6f} entry={self.avg_price:.2f}"
        )

        self.has_position = False
        self.qty = 0.0
        self.avg_price = None
        self.entry_bar = None
        self.entry_ts = None
        self.last_action_ts = ts
        self.pending_order = False

        # Trailing Stop 초기화
        self.highest_price = None
        self.trailing_armed = False

    def set_pending(self, pending: bool):
        """
        주문 진행 중 플래그 설정

        Args:
            pending: True면 주문 진행 중, False면 완료/취소
        """
        self.pending_order = pending
        if pending:
            logger.debug("⏳ Order pending...")
        else:
            logger.debug("✅ Order completed/cancelled")

    def update_highest_price(self, current_price: float):
        """
        Trailing Stop용 최고가 갱신

        Args:
            current_price: 현재 가격
        """
        if not self.has_position:
            return

        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price

    def arm_trailing_stop(self, threshold_pct: float, current_price: float) -> bool:
        """
        Trailing Stop 발동 조건 체크

        Args:
            threshold_pct: 최고가 대비 하락률 임계값 (예: 0.02 = 2%)
            current_price: 현재 가격

        Returns:
            bool: Trailing Stop 발동 여부
        """
        if not self.has_position or self.highest_price is None:
            return False

        drop_pct = (self.highest_price - current_price) / self.highest_price

        if drop_pct >= threshold_pct:
            logger.warning(
                f"🚨 Trailing Stop TRIGGERED | "
                f"highest={self.highest_price:.2f} curr={current_price:.2f} "
                f"drop={drop_pct:.2%} (threshold={threshold_pct:.2%})"
            )
            return True

        return False

    def get_pnl_pct(self, current_price: float) -> Optional[float]:
        """
        현재 손익률 계산

        Args:
            current_price: 현재 가격

        Returns:
            float or None: 손익률 (예: 0.05 = 5%)
        """
        if not self.has_position or self.avg_price is None:
            return None

        return (current_price - self.avg_price) / self.avg_price

    def get_bars_held(self, current_bar: int) -> int:
        """
        보유 기간 (bar 수)

        Args:
            current_bar: 현재 bar index

        Returns:
            int: 보유한 bar 수
        """
        if not self.has_position or self.entry_bar is None:
            return 0

        return current_bar - self.entry_bar

    def __repr__(self):
        return (
            f"PositionState(has_pos={self.has_position}, qty={self.qty:.6f}, "
            f"avg={self.avg_price}, pending={self.pending_order})"
        )
