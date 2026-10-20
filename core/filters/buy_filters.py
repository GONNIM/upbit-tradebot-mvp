"""
매수 필터 구현
"""
import logging
from typing import Optional

from .base import BaseFilter, FilterResult, FilterCategory
from core.candle_buffer import Bar

logger = logging.getLogger(__name__)


class SlowEmaSurgeFilter(BaseFilter):
    """
    Slow EMA 급등 차단 필터

    현재가가 Slow EMA 대비 일정 비율 이상 급등했을 때 매수를 차단함.
    급등 후 매수는 고점 매수 리스크가 높으므로 차단.
    """

    def __init__(self, threshold_pct: float = 0.01):
        """
        Args:
            threshold_pct: 급등 임계값 (기본 1% = 0.01)
        """
        super().__init__(FilterCategory.BUY_FILTER)
        self.threshold_pct = threshold_pct

    def get_name(self) -> str:
        return "SlowEmaSurgeFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            bar (Bar): 현재 캔들
            ema_slow (float): Slow EMA 값

        Returns:
            FilterResult: 급등 시 차단
        """
        bar: Bar = kwargs.get('bar')
        ema_slow: Optional[float] = kwargs.get('ema_slow')

        if bar is None:
            return FilterResult(
                should_block=False,
                reason="NO_BAR",
                details="Bar data not provided"
            )

        if ema_slow is None or ema_slow <= 0:
            logger.warning(f"⚠️ Slow EMA not available for surge filter, allowing trade")
            return FilterResult(
                should_block=False,
                reason="NO_EMA",
                details="Slow EMA not available"
            )

        # 급등률 계산
        surge_pct = (bar.close - ema_slow) / ema_slow

        if surge_pct > self.threshold_pct:
            return FilterResult(
                should_block=True,
                reason="SURGE_FILTER",
                details=f"Price surge detected: {surge_pct*100:.2f}% above Slow EMA (threshold: {self.threshold_pct*100:.1f}%)",
                metadata={
                    'surge_pct': surge_pct,
                    'threshold_pct': self.threshold_pct,
                    'price': bar.close,
                    'ema_slow': ema_slow
                }
            )

        return FilterResult(
            should_block=False,
            reason="SURGE_OK",
            details=f"Surge check passed: {surge_pct*100:.2f}%"
        )

    def update_threshold(self, threshold_pct: float):
        """급등 임계값 업데이트"""
        self.threshold_pct = threshold_pct
        logger.info(f"📊 SlowEmaSurgeFilter threshold updated: {threshold_pct*100:.1f}%")


WEAK_ENTRY_FILTER_REASON = "WEAK_ENTRY_FILTER"  # ✅ WO-26: audit_buy_eval.failed_keys 값 (약매수 차단)
WEAK_ENTRY_REASON = "WEAK_ENTRY"                # ✅ WO-26: 약매수 진입(익절 기준 축소) — 차단 아님
WEAK_ENTRY_MODES = ("block", "reduce_tp")


class WeakEntryFilter(BaseFilter):
    """
    ✅ WO-26 (2026-10-20): 약매수 차단 필터.

    직전 데드크로스(매도 EMA 쌍) 봉 시각부터 현재 봉 시각까지가 window_hours 이내이면 약매수로 본다.
    - mode="block": 매수 안 함 (should_block=True, reason=WEAK_ENTRY_FILTER)
    - mode="reduce_tp": 매수하되 그 포지션의 익절·수익 추적 무장 기준을 weak_tp_pct 로 낮춘다
      (should_block=False, reason=WEAK_ENTRY, metadata.tp)
    last_dead_cross_ts 가 None(직전 D/C 모름) 이거나 window_hours<=0 이면 일반 매수.

    BuyFilterManager 에 등록하지 않는다. G/C 등 모든 매수 조건을 통과한 직후 전략이 직접 부른다
    (매 봉 차단 기록 방지 + 통과 결과 metadata 보존 — WO-26 설계 B-1).
    """

    def __init__(self, window_hours: float = 2.0, mode: str = "block", weak_tp_pct: float = 0.005):
        super().__init__(FilterCategory.BUY_FILTER)
        self.window_hours = float(window_hours or 0.0)
        self.mode = mode if mode in WEAK_ENTRY_MODES else "block"
        self.weak_tp_pct = float(weak_tp_pct)

    def get_name(self) -> str:
        return "WeakEntryFilter"

    def evaluate(self, **kwargs) -> FilterResult:
        """
        Args:
            bar_ts: 현재 봉 시각 (tz-aware)
            last_dead_cross_ts: 마지막 D/C 봉 시각 (tz-aware 또는 None)
        """
        bar_ts = kwargs.get("bar_ts")
        last_dc = kwargs.get("last_dead_cross_ts")
        if self.window_hours <= 0:
            return FilterResult(should_block=False, reason="WEAK_OFF", details="허용 시간 0 — 약매수 판정 안 함")
        if bar_ts is None or last_dc is None:
            return FilterResult(should_block=False, reason="WEAK_UNKNOWN", details="직전 D/C 알 수 없음 — 일반 매수")
        try:
            elapsed_min = (bar_ts - last_dc).total_seconds() / 60.0
        except Exception as e:  # tz 혼합 등 — 판단 불가는 일반 매수
            logger.warning(f"⚠️ [WEAK-ENTRY] 경과 시간 계산 실패 → 일반 매수 | bar_ts={bar_ts} last_dc={last_dc} | {e}")
            return FilterResult(should_block=False, reason="WEAK_UNKNOWN", details=f"경과 시간 계산 실패: {e}")
        if elapsed_min < 0 or elapsed_min > self.window_hours * 60.0:
            return FilterResult(
                should_block=False, reason="WEAK_OK",
                details=f"D/C 뒤 {elapsed_min:.0f}분 (기준 {self.window_hours:g}시간) — 일반 매수",
            )
        n = int(round(elapsed_min))
        meta = {"weak_entry": True, "mode": self.mode, "elapsed_min": n, "window_h": self.window_hours}
        if self.mode == "block":
            return FilterResult(
                should_block=True, reason=WEAK_ENTRY_FILTER_REASON,
                details=f"약매수 차단 (D/C 뒤 {n}분, 기준 {self.window_hours:g}시간)", metadata=meta,
            )
        meta["tp"] = self.weak_tp_pct
        return FilterResult(
            should_block=False, reason=WEAK_ENTRY_REASON,
            details=f"{weak_entry_note(self.weak_tp_pct)} (D/C 뒤 {n}분, 기준 {self.window_hours:g}시간)", metadata=meta,
        )


def _pct_text(pct: float) -> str:
    return f"{float(pct) * 100:.1f}".rstrip("0").rstrip(".") + "%"


def weak_entry_note(tp: float) -> str:
    """✅ WO-26: 약매수 진입 비고 (BUY 평가·매수 행)."""
    return f"약매수 진입 · 익절 {_pct_text(tp)}"


def weak_position_note(tp: float) -> str:
    """✅ WO-26: 약매수 포지션 매도 행 비고."""
    return f"약매수 포지션 · 기준 {_pct_text(tp)}"
