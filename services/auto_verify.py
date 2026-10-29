"""
LIVE 자동 계좌검증 공통 헬퍼.

app.py / set_config.py / dashboard.py 등에서 공통으로 사용.
- run_live_auto_verify: Upbit API 키 검증 + DB 동기화 (순수 데이터 반환, side-effects는 DB 한정)
- apply_verify_to_session: 결과를 streamlit session_state에 반영 (별도 함수)

순수 데이터 vs Streamlit 의존성 분리로 호출 측에서 UI/세션 처리 자율성 확보.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _extract_krw_balance(accounts) -> float:
    """validate_upbit_keys 응답에서 KRW balance(활성)만 추출."""
    if not accounts:
        return 0.0
    for acc in accounts:
        if acc.get("currency") == "KRW":
            try:
                return float(acc.get("balance", "0"))
            except (ValueError, TypeError):
                return 0.0
    return 0.0


def run_live_auto_verify(user_id: str, name: str) -> dict[str, Any]:
    """
    LIVE Upbit 자동 검증 + DB 동기화.

    Side effects:
        - save_user (users 테이블)
        - update_account_from_balances (accounts 테이블, active/locked 분리)
        - update_position_from_balances (account_positions 테이블, ticker별)

    Returns:
        {
            'ok': bool,
            'krw_balance': float,    # KRW 활성 잔고
            'accounts': list,        # Upbit get_balances 응답
            'error': str | None,
        }
    """
    from config import ACCESS, SECRET
    from services.upbit_api import validate_upbit_keys
    from services.db import (
        save_user,
        update_account_from_balances,
        update_position_from_balances,
    )

    ak, sk = ACCESS, SECRET
    if not ak or not sk:
        return {
            "ok": False,
            "krw_balance": 0.0,
            "accounts": [],
            "error": "config/secrets에 ACCESS/SECRET 없음",
        }

    try:
        ok, data = validate_upbit_keys(ak, sk)
    except Exception as e:
        logger.error(f"[AUTO-VERIFY] validate_upbit_keys 예외: {e}")
        return {"ok": False, "krw_balance": 0.0, "accounts": [], "error": str(e)}

    if not ok:
        return {
            "ok": False,
            "krw_balance": 0.0,
            "accounts": [],
            "error": str(data),
        }

    krw_balance = _extract_krw_balance(data)

    # ✅ 2차 T15 (D10, R6): 새 전략 보유 중(TEST 행)·예약 중이면 운용자산(users.virtual_krw)을 덮어쓰지 않고
    #   display_name 만 갱신한다. 아니면 지금처럼 원화 잔고로 갱신.
    capital_kept, capital_krw, capital_reason = keep_capital_on_verify(user_id, name)

    # DB 저장 + 동기화 (개별 실패는 로그만, 전체 결과는 ok 유지)
    if not capital_kept:
        try:
            save_user(user_id, name, krw_balance)
        except Exception as e:
            logger.warning(f"[AUTO-VERIFY] save_user 실패: {e}")

    try:
        update_account_from_balances(user_id, data)
        for bal in (data or []):
            currency = bal.get("currency", "").upper()
            if currency and currency != "KRW":
                ticker = f"KRW-{currency}"
                update_position_from_balances(user_id, ticker, data)
        logger.info(f"✅ [AUTO-VERIFY] DB 잔고 동기화 완료: user={user_id}")
    except Exception as e:
        logger.error(f"⚠️ [AUTO-VERIFY] DB 잔고 동기화 실패: {e}")

    return {
        "ok": True,
        "krw_balance": krw_balance,
        "accounts": data or [],
        "error": None,
        "capital_kept": capital_kept,                                   # ✅ 2차 T15 (D10)
        "capital_krw": capital_krw if capital_kept else krw_balance,
        "capital_reason": capital_reason,
    }


KEEP_TRADING = "trading"   # 새 전략 보유 중(TEST 행) 또는 예약 중
KEEP_UNKNOWN = "unknown"   # 예약·보유 상태를 읽지 못함(fail closed)


def keep_capital_on_verify(user_id: str, name: str) -> tuple[bool, float | None, str | None]:
    """D10: 새 전략 보유·예약 중이면 display_name 만 갱신하고 (True, 지금 운용자산, 이유). 아니면 (False, None, None).
    이유 = KEEP_TRADING | KEEP_UNKNOWN(판정 실패 — 예약·보유 읽기 실패 포함, 덮어쓰지 않는 쪽).
    운용자산은 DB(users.virtual_krw)에서 다시 읽은 값이고, 못 읽으면 None(화면은 금액 없이 보인다).
    users 행이 없으면 (False, None, None) — 기존 save_user 로."""
    from ui.pullback_lock import kept_capital
    reason = KEEP_TRADING
    try:
        from ui.pullback_lock import lock_state, keeps_capital
        state = lock_state(user_id)
        if not keeps_capital(state):
            return False, None, None
        if state.get("reservation_error") or state.get("holding_error"):
            reason = KEEP_UNKNOWN
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[AUTO-VERIFY] 새 전략 상태 판정 실패 → 운용자산 그대로: {type(e).__name__}")
        return True, kept_capital(user_id), KEEP_UNKNOWN
    try:
        from ui.pullback_lock import keep_capital_update_display_name
        if not keep_capital_update_display_name(user_id, name):
            return False, None, None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[AUTO-VERIFY] display_name 갱신 실패 → 운용자산 그대로: {type(e).__name__}")
    logger.info(f"[AUTO-VERIFY] 운용자산 그대로 (user={user_id}, reason={reason})")
    return True, kept_capital(user_id), reason


def capital_kept_text(capital_krw, reason) -> str:
    """로그인 화면 문구(합니다체·내부 코드 없음). 금액을 모르면 금액을 빼고 보인다."""
    if reason == KEEP_UNKNOWN:
        tail = "상태를 확인하지 못해 운용자산을 바꾸지 않았습니다"
    else:
        tail = "새 전략 거래 중이라 그대로 둡니다"
    try:
        amount = float(capital_krw) if capital_krw is not None else None
    except (TypeError, ValueError):
        amount = None
    if amount is None:
        return f"운용자산: {tail}"
    return f"운용자산: {amount:,.0f} KRW ({tail})"


def apply_verify_to_session(st, result: dict[str, Any]) -> None:
    """
    run_live_auto_verify 결과를 Streamlit session_state에 반영.

    Args:
        st: streamlit module
        result: run_live_auto_verify 반환 dict
    """
    if result.get("ok"):
        st.session_state.upbit_verified = True
        st.session_state.upbit_accounts = result.get("accounts") or []
        st.session_state.live_krw_balance = float(result.get("krw_balance") or 0.0)
        if result.get("capital_kept"):
            # ✅ 2차 T15 (D10): 새 전략 거래 중 — 세션 운용자산도 DB 값 그대로
            st.session_state.virtual_krw = float(
                result.get("capital_krw") or st.session_state.get("virtual_krw") or 0.0)
            # 금액을 못 읽어 0 이어도 자동 검증을 다시 돌리지 않게(app.py need_auto_verify)
            st.session_state["_capital_kept_in_live"] = True
        else:
            st.session_state.virtual_krw = float(result.get("krw_balance") or 0.0)
        st.session_state.live_capital_set = True
        st.session_state.virtual_over = True
        st.session_state["_auto_checked_in_live"] = True
    else:
        st.session_state.upbit_verified = False
        st.session_state.upbit_accounts = []
        st.session_state.live_krw_balance = 0.0
        st.session_state.live_capital_set = False
