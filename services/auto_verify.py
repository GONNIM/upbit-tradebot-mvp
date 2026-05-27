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

    # DB 저장 + 동기화 (개별 실패는 로그만, 전체 결과는 ok 유지)
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
    }


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
        st.session_state.virtual_krw = float(result.get("krw_balance") or 0.0)
        st.session_state.live_capital_set = True
        st.session_state.virtual_over = True
        st.session_state["_auto_checked_in_live"] = True
    else:
        st.session_state.upbit_verified = False
        st.session_state.upbit_accounts = []
        st.session_state.live_krw_balance = 0.0
        st.session_state.live_capital_set = False
