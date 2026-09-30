"""
WO-11 (2026-09-30): 사용자 노출 용어 통일 — 표시층 변환.

확정 용어 (docs/operations/terminology.md):
- 매수 방식: "시장가 매수" / "현재가 매수"
- 매도 방식: "시장가 매도" (옵션 없음)
- 앱 주문: "앱 지정가 주문" (업비트 앱에서 직접 가격을 정한 주문)
- 폐기: "고정가", 봇 옵션명으로서의 "지정가"

과거 DB 행(logs.message 등)은 수정하지 않는다. 화면에 보여줄 때만 이 모듈로
옛 문구를 새 문구로 바꾼다. 코드 키(fixed_price_buy_enabled)와 로그 태그
([FIXED-PRICE], BUY-LIMIT)는 대상이 아니다.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# 앱 지정가 주문 문맥("앱 지정가", "직접 넣은 지정가")은 폐기 대상이 아니다 — 변환 제외.
_NOT_APP = r"(?<!앱 )(?<!직접 넣은 )"

# (패턴, 치환) — 위에서부터 순서대로 적용 (긴 문구 우선)
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\[LIVE 고정가\] 지정가 매수 요청"), "[LIVE] 현재가 매수 주문 요청"),
    (re.compile(_NOT_APP + r"강제 매수 지정가"), "강제 매수(현재가)"),
    (re.compile(r"고정가 강제 매수"), "현재가 강제 매수"),
    (re.compile(_NOT_APP + r"지정가 매수"), "현재가 매수"),
    (re.compile(r"고정가 매수"), "현재가 매수"),
    (re.compile(r"고정가"), "현재가 매수"),
]

# 폐기 용어 검사용: "고정가" 전부 + 앱 주문 문맥이 아닌 "지정가"
DEPRECATED_PATTERN = re.compile(r"고정가|" + _NOT_APP + r"지정가")


def display_text(text: Any) -> Any:
    """옛 용어를 새 용어로 바꾼 문자열. 문자열이 아니면 그대로 반환."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pat, rep in _RULES:
        out = pat.sub(rep, out)
    return out


def display_rows(rows: Iterable[Any] | None) -> list:
    """(…, message) 튜플 목록의 마지막 문자열 칸을 변환 (logs 조회 결과용)."""
    result = []
    for row in rows or []:
        if isinstance(row, (tuple, list)) and row and isinstance(row[-1], str):
            row = type(row)(list(row[:-1]) + [display_text(row[-1])])
        result.append(row)
    return result


def display_df(df):
    """DataFrame 의 문자열 칸 전체에 display_text 적용 (원본은 바꾸지 않고 사본 반환)."""
    try:
        out = df.copy()
        for col in out.columns:
            if out[col].dtype == object:
                out[col] = out[col].map(display_text)
        return out
    except Exception:
        return df


def find_deprecated(text: str) -> list[str]:
    """문자열 안의 폐기 용어 위치 목록 (검증용)."""
    return [m.group(0) for m in DEPRECATED_PATTERN.finditer(text or "")]
