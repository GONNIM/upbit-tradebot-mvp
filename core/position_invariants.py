"""
✅ [Phase 1-A] 포지션 상태 Invariant 검증 헬퍼

목적: has_position=True 상태에서 avg_price/entry_ts/entry_bar/qty 등이 결손된
      invariant 위반 조합을 한 곳에서 감지하고 명시적 CRITICAL 로그 + 알림 + safe fallback.

배경 (2026-07-24 사건 및 후속 감사):
- 4e2bc3e Fix 2 는 EMA/MACD SELL 진입부에 avg_price 검증만 인라인 구현
- 감사 결과 (2026-07-27):
  · P1-1: `entry_ts=None` 인데 StalePositionFilter 가 silent NO_POSITION return
  · P1-4: 부팅 seed 실패 후 avg_price 잔존 상태
  · Fix 2 코드 중복 (EMA + MACD 각각 40줄) → 헬퍼로 통합
- 이 파일은 관찰/알림/스킵만 담당. 매매 임계값(TP/SL/TS)은 절대 변경하지 않음.
"""
from typing import Optional, TYPE_CHECKING, Tuple
import logging

if TYPE_CHECKING:
    from core.position_state import PositionState

logger = logging.getLogger(__name__)


# ============================================================
# Invariant 위반 코드 (dedupe_key + 사용자 알림용)
# ============================================================
INVARIANT_CODES = {
    "I1_AVG_PRICE_MISSING": "has_position=True 인데 avg_price None/0",
    "I2_QTY_ZERO_WITH_POSITION": "has_position=True 인데 qty <= 0",
    "I3_ENTRY_TS_MISSING": "has_position=True 인데 entry_ts=None",
    "I4_ENTRY_BAR_MISSING": "has_position=True 인데 entry_bar=None (audit fallback 대상)",
    "I5_STALE_AVG_PRICE": "avg_price>0 인데 qty<=0 (memory 잔재)",
    "I6_TRAILING_ARMED_NO_HIGHEST": "trailing_armed=True 인데 highest_price=None",
}


def check_position_invariants(
    position: "PositionState",
    *,
    context: str = "unknown",
) -> Optional[Tuple[str, str, dict]]:
    """
    ✅ [Phase 1-A] 포지션 상태 invariant 검증.

    Args:
        position: PositionState 인스턴스
        context: 호출 지점 식별용 (예: "EMA_SELL_ENTRY", "MACD_SELL_ENTRY", "on_hts_detect")

    Returns:
        위반 없으면 None.
        위반 시 (code, message, details_dict) 3-tuple. 호출자는 raise_invariant_violation()
        으로 로그/알림/스킵 처리.

    검사 순서 (심각도 순):
        I1: has_position + avg_price None/0  → SELL 필터 무력화 위험 (07-24 사건)
        I2: has_position + qty<=0            → memory 왜곡
        I3: has_position + entry_ts=None     → Stale filter silent skip (P1-1)
        I5: !has_position + avg_price>0      → 잔재 (안전, WARN 만)
        I6: trailing_armed + highest=None    → TS 오작동
    """
    if position is None:
        return ("I0_POSITION_NONE", "position 객체 자체가 None", {})

    has_pos = bool(position.has_position)
    avg = position.avg_price
    qty = position.qty
    entry_ts = position.entry_ts

    # I1: has_position + avg_price 결손 (최우선)
    if has_pos and (avg is None or avg <= 0):
        return (
            "I1_AVG_PRICE_MISSING",
            f"has_position=True 인데 avg_price={avg} (None/0). SL/TP/TS 무력화 위험.",
            {"has_position": has_pos, "avg_price": avg, "qty": qty, "context": context},
        )

    # I2: has_position + qty 결손
    if has_pos and (qty is None or qty <= 1e-9):
        return (
            "I2_QTY_ZERO_WITH_POSITION",
            f"has_position=True 인데 qty={qty} (<=0). memory 왜곡.",
            {"has_position": has_pos, "avg_price": avg, "qty": qty, "context": context},
        )

    # I3: has_position + entry_ts 결손 (P1-1 근본)
    if has_pos and entry_ts is None:
        return (
            "I3_ENTRY_TS_MISSING",
            f"has_position=True 인데 entry_ts=None. Stale filter silent skip 위험.",
            {"has_position": has_pos, "avg_price": avg, "qty": qty,
             "entry_ts": entry_ts, "context": context},
        )

    # I5: 잔재 상태 (안전하지만 WARN)
    if (not has_pos) and (avg is not None) and (avg > 0):
        return (
            "I5_STALE_AVG_PRICE",
            f"has_position=False 인데 avg_price={avg}. memory 잔재.",
            {"has_position": has_pos, "avg_price": avg, "qty": qty, "context": context},
        )

    # I6: TS armed 인데 highest 없음
    if getattr(position, "trailing_armed", False) and (
        getattr(position, "highest_price", None) is None
    ):
        return (
            "I6_TRAILING_ARMED_NO_HIGHEST",
            "trailing_armed=True 인데 highest_price=None. TS 오작동 위험.",
            {"context": context},
        )

    return None


def raise_invariant_violation(
    violation: Tuple[str, str, dict],
    *,
    user_id: Optional[str] = None,
    ticker: Optional[str] = None,
    strategy_tag: str = "EMA",
) -> None:
    """
    ✅ [Phase 1-A] Invariant 위반 시 통합 대응.
    - CRITICAL 로그
    - insert_log(ERROR) — DB 감사 트레일
    - notifier.send(LEVEL_CRITICAL) — 사용자 텔레그램 즉시 알림
    각 sub-action 은 에러 격리 (하나 실패해도 나머지 진행).

    dedupe_key: 코드+ticker (동일 상태 반복 알림 억제, 600초).

    호출자 관례: 이 함수 호출 후 SELL 평가는 Action.HOLD 로 스킵.
    """
    code, msg, details = violation

    # 1. logger.critical
    logger.critical(
        f"🚨 [INVARIANT-{code}] {msg} | user={user_id} ticker={ticker} "
        f"strategy={strategy_tag} details={details}"
    )

    # 2. insert_log (DB 감사)
    if user_id:
        try:
            from services.db import insert_log
            insert_log(
                user_id, "ERROR",
                f"🚨 [{strategy_tag}] Invariant {code}: {msg} | ticker={ticker}"
            )
        except Exception as e:
            logger.warning(f"[INVARIANT] insert_log 실패: {e}")

    # 3. notifier (사용자 즉시 알림)
    if ticker:
        try:
            from services.notifier import send as _notify_send, LEVEL_CRITICAL
            _notify_send(
                LEVEL_CRITICAL,
                f"🚨 포지션 무결성 결손 — {ticker}",
                (
                    f"코드: {code}\n"
                    f"사유: {msg}\n\n"
                    f"strategy={strategy_tag}\n"
                    f"context={details.get('context', '-')}\n"
                    f"avg_price={details.get('avg_price', '-')}\n"
                    f"qty={details.get('qty', '-')}\n\n"
                    f"봇 SELL 평가 스킵 상태 (안전 fallback).\n"
                    f"수동 정리 or force_liquidate 검토 필요."
                ),
                dedupe_key=f"invariant:{code}:{ticker}",
                dedupe_ttl=600,
            )
        except Exception as e:
            logger.warning(f"[INVARIANT] notifier 발송 실패: {e}")
