"""
WO-2 재적용: 매수 지연 발주 큐

설계 근거: docs/plans/2026-08-30-audit-gap-investigation-and-wo2-redesign.md 2부.

원칙 요약:
- 매수 결정이 나온 봉의 확정이 완료될 때까지 발주를 지연한다.
- 지연 상한은 60초(1개 봉 간격). 초과 시 취소 + 감사 기록.
- 대기 매수는 한 번에 1건만 유지한다. 새 결정이 오면 기존 항목을
  SUPERSEDED 사유로 취소하고 교체한다. 더 최신 정보로 내린 결정이 우선이다.
- 매도 경로는 이 큐를 사용하지 않는다. register(decision='SELL')은
  ValueError. 보호성 매도가 지연되는 실수를 런타임에서 물리 차단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class PendingOrder:
    """
    대기 중인 매수 발주 1건.

    유효성 확인은 판단이 아니다. confirmed_close 만 새로 받아 아래 값들로
    한 번만 재계산한다. 관문(POLLUTED, 재사용 대기, 포지션 제한, 필터)은
    재실행하지 않는다.

    use_separate_ema=True 환경에서는 매수용 지표 쌍(fast_buy, slow_buy)만
    사용한다. 매도용 쌍(fast_sell, slow_sell)은 여기에 저장하지 않는다.
    유효성 확인의 재계산도 매수용 쌍으로만 한다.
    """

    bar_ts: datetime                  # 대상 봉 시각
    decision: str                     # 항상 'BUY' (SELL 은 큐를 우회)
    signal_condition: str             # 재확인할 신호 이름 (예: 'EMA_GC')
    tentative_close: float            # 평가 시점 종가 (미확정 가능)
    ema_fast_prev: float              # 직전 봉의 매수용 fast EMA 값 (fast_buy 기간)
    ema_slow_prev: float              # 직전 봉의 매수용 slow EMA 값 (slow_buy 기간)
    ema_fast_alpha: float             # 매수용 fast 스무딩 계수 (2 / (fast_buy + 1))
    ema_slow_alpha: float             # 매수용 slow 스무딩 계수 (2 / (slow_buy + 1))
    context: Dict[str, Any]           # 관문 스냅샷(참고용)
    created_at: datetime              # 등록 시각
    max_wait_sec: int = 60            # 지연 상한 (설계 문서 §2.2)

    def is_expired(self, now: datetime) -> bool:
        return (now - self.created_at) >= timedelta(seconds=self.max_wait_sec)

    def revalidate(self, confirmed_close: float) -> bool:
        """
        확정 종가로 신호 조건을 한 번만 재계산한다.

        현재 매수용 신호는 EMA Golden Cross(fast > slow)만 지원한다.
        신설 신호가 필요하면 이 메서드에 분기를 명시적으로 추가한다.
        """
        ema_fast = self.ema_fast_prev + self.ema_fast_alpha * (
            confirmed_close - self.ema_fast_prev
        )
        ema_slow = self.ema_slow_prev + self.ema_slow_alpha * (
            confirmed_close - self.ema_slow_prev
        )
        if self.signal_condition == 'EMA_GC':
            return ema_fast > ema_slow
        raise ValueError(
            f"Unsupported signal_condition: {self.signal_condition}"
        )


@dataclass
class CancelReport:
    """취소 사유를 감사에 남기기 위한 간단 보고."""

    bar_ts: datetime
    reason: str                       # 'SUPERSEDED' | 'MAX_WAIT_EXCEEDED' | 'SIGNAL_INVERTED'
    at: datetime


class PendingOrderQueue:
    """
    대기 매수는 한 번에 1건만 유지한다.

    register 는 항상 최신 결정으로 교체한다. 기존 항목이 있으면
    CancelReport(reason='SUPERSEDED')를 반환한다. 호출자는 이 보고를
    감사에 반영한다.
    """

    def __init__(self) -> None:
        self._current: Optional[PendingOrder] = None
        self._cancelled: List[CancelReport] = []  # 최근 취소 이력 (감사 지연 반영용)

    @property
    def current(self) -> Optional[PendingOrder]:
        return self._current

    def is_empty(self) -> bool:
        return self._current is None

    def register(self, order: PendingOrder) -> Optional[CancelReport]:
        if order.decision != 'BUY':
            raise ValueError(
                f"PendingOrderQueue는 매수만 지원한다. decision={order.decision}"
            )
        superseded: Optional[CancelReport] = None
        if self._current is not None:
            superseded = CancelReport(
                bar_ts=self._current.bar_ts,
                reason='SUPERSEDED',
                at=order.created_at,
            )
            self._cancelled.append(superseded)
        self._current = order
        return superseded

    def clear(self) -> None:
        self._current = None

    def cancel_current(self, reason: str, at: datetime) -> Optional[CancelReport]:
        """상한 초과나 유효성 불성립으로 현재 항목을 취소한다."""
        if self._current is None:
            return None
        report = CancelReport(bar_ts=self._current.bar_ts, reason=reason, at=at)
        self._cancelled.append(report)
        self._current = None
        return report

    def drain_cancelled(self) -> List[CancelReport]:
        """취소 이력을 감사에 반영한 뒤 큐 내부에서 비운다."""
        out = list(self._cancelled)
        self._cancelled.clear()
        return out
