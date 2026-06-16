"""Upbit 에러 코드 → 한국어 라벨 변환.

Telegram 알림·UI 노출용 공통 사람-친화 메시지. 원본 err_summary는
디버깅용으로 별도 노출하고, 본 모듈이 반환하는 라벨을 운영자에게 먼저 표시.

매핑 출처: pyupbit/errors.py 기반 + Upbit Open API 공식 에러 코드.
"""
from __future__ import annotations


_UPBIT_ERROR_LABELS: dict[str, str] = {
    # 인증/권한
    "jwt_verification": "JWT 검증 실패 (키 만료 또는 IP 미등록)",
    "expired_access_key": "API 키 만료",
    "invalid_access_key": "잘못된 API 키",
    "no_authorization_i_p": "허용되지 않은 IP (화이트리스트 등록 필요)",
    "out_of_scope": "허용되지 않은 API 권한 범위",
    "thirdparty_agreement_required": "신규 코인 별도 약관 동의 필요 (Upbit 콘솔)",
    "invalid_query_payload": "JWT payload 형식 오류",

    # 주문 — 잔고
    "insufficient_funds_bid": "매수 가능 KRW 부족",
    "insufficient_funds_ask": "매도 가능 수량 부족",

    # 주문 — 한도
    "under_min_total_bid": "최소 매수 금액 미만 (5,000 KRW)",
    "under_min_total_ask": "최소 매도 금액 미만",
    "over_max_total_price_bid": "최대 매수 금액 초과 (10억 KRW)",
    "out_of_capacity": "주문 수량/금액 한도 초과",

    # 주문 — 형식
    "create_bid_error": "매수 주문 형식 오류",
    "create_ask_error": "매도 주문 형식 오류",
    "validation_error": "요청 검증 실패",

    # API 호출 제한
    "request_throttling": "API 호출 제한 초과 (Rate Limit)",

    # 일반 네트워크/예외
    "exception": "내부 예외 발생",
    "invalid response": "Upbit 응답 형식 오류",
}


def label_for_upbit_error(err_summary: str | None) -> str:
    """err_summary 내에서 알려진 Upbit 에러 코드를 찾아 한국어 라벨 반환.

    매치 없거나 err_summary가 비어 있으면 빈 문자열.
    다중 매치 시 정의 순서에 따라 첫 매치 반환 (인증 > 잔고 > 형식 순).
    """
    if not err_summary:
        return ""
    low = err_summary.lower()
    for code, label in _UPBIT_ERROR_LABELS.items():
        if code in low:
            return label
    return ""


def format_error_block(err_summary: str | None, max_raw_len: int = 200) -> tuple[str, str]:
    """한국어 라벨과 원본 err를 분리해 반환.

    Returns:
        (label, raw) — label은 한국어 사유(없으면 "알 수 없음"),
        raw는 원본 err_summary를 max_raw_len으로 자른 문자열.
    """
    label = label_for_upbit_error(err_summary) or "알 수 없음"
    raw = (err_summary or "").strip()
    if len(raw) > max_raw_len:
        raw = raw[:max_raw_len] + "…"
    return label, raw
