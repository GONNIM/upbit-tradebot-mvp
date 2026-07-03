"""
페이지 진입·이동 표준 헬퍼 — SP-NAV-1 (Page Navigation Hardening).

원칙 (docs/plans/page-navigation-hardening/plan.md §4):
  P1  이동 방식 단일화 — st.switch_page + st.query_params.update
  P2  컨텍스트 이중 소유 — session_state + URL query_params 함께 세팅
  P3  세션 유실 시 자동 로그인 리다이렉트
  P4  페이지 진입 헬퍼 통합 — bootstrap_page_context
  P5  페이지 이동 헬퍼 통합 — navigate_to

Streamlit 대상 버전: 1.46.0 (서버) / 1.41.1 (로컬) — 두 버전 모두 필요 API 완전 지원.

교훈:
- 교훈 #25 (Streamlit 위젯 규칙): navigate_to 는 위젯 인스턴스화 이전 또는 이벤트 콜백 안에서만 호출.
- 교훈 #14 (session_state 동기화 누락): URL 만 세팅 or 세션만 세팅은 결함 근원 → 이중 저장 강제.
- 교훈 #19 (편협적 수정 금지): 각 페이지 진입 로직을 개별 구현하지 말고 본 헬퍼로 통일.
"""
from __future__ import annotations

from typing import Iterable
import logging

import streamlit as st

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 페이지 컨텍스트 표준 키
# ─────────────────────────────────────────────────────────────────

#: 페이지 이동·진입 시 URL query_params 로 함께 전달할 표준 키.
CONTEXT_KEYS_DEFAULT: tuple[str, ...] = (
    "user_id",
    "mode",
    "strategy_type",
    "virtual_krw",
    "verified",
)

#: 필수 컨텍스트 (없으면 로그인 리다이렉트).
REQUIRED_KEYS_DEFAULT: tuple[str, ...] = ("user_id",)

#: 로그인 페이지 (진입점).
LOGIN_PAGE: str = "app.py"


# ─────────────────────────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────────────────────────


def _get_param(qp, key: str, default=None):
    """
    st.query_params 값 획득 헬퍼.

    Streamlit 1.46 은 스칼라 반환이지만 1.30 초기 버전은 list 를 반환한 이력이
    있어 방어 코드를 유지한다 (교훈 #13: 버전별 차이 회피).
    """
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v


def _normalize_value(key: str, value):
    """도메인 규약 정규화 (예: mode 는 대문자, verified 는 bool-like)."""
    if value is None:
        return value
    if key == "mode" and value:
        return str(value).upper()
    return value


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────


def bootstrap_page_context(
    required: Iterable[str] = REQUIRED_KEYS_DEFAULT,
    keys: Iterable[str] = CONTEXT_KEYS_DEFAULT,
    login_page: str = LOGIN_PAGE,
) -> dict:
    """
    페이지 진입 헤더에서 호출 — 컨텍스트 획득·검증·세션 이중 저장·유실 시 리다이렉트.

    획득 우선순위: URL query_params → session_state → 기본값(빈 문자열).

    Args:
        required: 반드시 존재해야 하는 키 (없으면 login_page 리다이렉트).
        keys: 획득 대상 전체 키 (query_params + session_state 이중 저장).
        login_page: 리다이렉트 대상 페이지 경로.

    Returns:
        dict: 획득된 컨텍스트 값들.

    Notes:
        - 반드시 페이지 최상단, 어떠한 위젯 인스턴스화보다 이전에 호출 (교훈 #25).
        - st.switch_page 는 NoReturn 이므로 필수 검증 실패 시 함수는 반환하지 않는다.
    """
    qp = st.query_params
    ctx: dict = {}

    # 1) 획득 (URL 우선, session_state fallback)
    for k in keys:
        default = st.session_state.get(k, "")
        v = _get_param(qp, k, default)
        ctx[k] = _normalize_value(k, v)

    # 2) 필수 검증 — 없으면 로그인 리다이렉트
    missing = [k for k in required if not ctx.get(k)]
    if missing:
        logger.warning(
            f"[PageContext] 필수 컨텍스트 부재 → 로그인 리다이렉트 | missing={missing}"
        )
        st.warning("⏱️ 세션이 만료되었습니다. 로그인 페이지로 이동합니다.")
        st.switch_page(login_page)
        # NoReturn 이지만 방어적으로 stop
        st.stop()

    # 3) 이중 저장 (session_state)
    for k, v in ctx.items():
        st.session_state[k] = v

    return ctx


def navigate_to(target_page: str, **params) -> None:
    """
    페이지 이동 표준 — session_state + query_params 이중 세팅 후 switch_page.

    Args:
        target_page: 대상 페이지 경로 (예: "pages/dashboard.py").
        **params: 함께 전달할 컨텍스트 (user_id, mode, ...).

    Notes:
        - params 값은 문자열로 자동 변환 (query_params 는 str 요구).
        - None 및 빈 값은 제외 (URL 오염 방지).
        - Streamlit `switch_page` 는 NoReturn — 호출 후 스크립트 종료.
        - 위젯 인스턴스화 이후 호출은 안전 (session_state[key] 는 위젯 key 와
          충돌하지 않는 컨텍스트 키만 사용 — 교훈 #25).
    """
    # 필터: None / 빈 문자열만 제외 (0 은 유효값 — 예: virtual_krw=0)
    clean = {
        k: str(v) for k, v in params.items()
        if v is not None and v != ""
    }

    # 1) session_state 이중 저장
    for k, v in clean.items():
        st.session_state[k] = v

    # 2) URL query_params 세팅 (뒤로가기 시 복원용)
    if clean:
        st.query_params.update(clean)

    # 3) Streamlit native switch_page (NoReturn)
    st.switch_page(target_page)


def build_context_params(exclude: Iterable[str] = ()) -> dict:
    """
    현재 세션의 표준 컨텍스트 키를 dict 로 추출 — navigate_to 호출 시 편의용.

    Args:
        exclude: 제외할 키 목록.

    Returns:
        dict: session_state 에서 추출한 표준 컨텍스트 (빈 값 제외).

    Usage:
        navigate_to("pages/dashboard.py", **build_context_params())
    """
    excluded = set(exclude)
    result = {}
    for k in CONTEXT_KEYS_DEFAULT:
        if k in excluded:
            continue
        v = st.session_state.get(k)
        # 0 은 유효값 (예: virtual_krw=0) — None / 빈 문자열만 제외
        if v is not None and v != "":
            result[k] = v
    return result
