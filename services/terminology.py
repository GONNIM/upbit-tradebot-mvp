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
import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

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


# ============================================================================
# 2차 T8 (2026-10-28): 새 전략(PULLBACK, 눌림목 분할매수) 용어 — 운영자 확인 대상(pullback spec 5절).
# 화면·텔레그램에만 쓴다. EMA·MACD 행의 표시는 바꾸지 않는다(새 전략 행이 있을 때만 칸을 더한다).
# ============================================================================
NEW_STRATEGY_LABEL = "새 전략"

PULLBACK_TERMS: dict[str, str] = {
    "strategy": "눌림목 분할매수",
    "buy_pullback": "눌림목 매수",
    "buy_golden": "골든크로스 매수",
    "split_round": "분할 n회차",
    "wait_pullback": "눌림 대기",
    "switch_reserved": "전환 예약",
    "switch_done": "전환 완료",
    "switch_back": "복귀",
    "round_skipped": "회차 건너뜀",
}

# 매수·매도 사유 코드 → 화면 용어
PULLBACK_REASON_LABEL: dict[str, str] = {
    "GOLDEN": PULLBACK_TERMS["buy_golden"],
    "PULLBACK": PULLBACK_TERMS["buy_pullback"],
    "TP": "익절",
    "SL": "손절",
    "DEADCROSS": "데드크로스",
}

# 감사 failed_keys(새 전략) → 화면 문구
PULLBACK_STATE_LABEL: dict[str, str] = {
    "NOT_ACTIVE": "감시 구간 밖",
    "WAIT_PULLBACK": PULLBACK_TERMS["wait_pullback"],
    "WAIT_GOLDEN": "골든크로스 대기",
    "SPLITS_FULL": "분할 회차 다 참",
    "PULLBACK_CAP": "눌림목 매수 한도 다 참",
    "DESYNC": "보유 수량 어긋남 — 추가 매수 멈춤",
    "SWITCH_RESERVED": PULLBACK_TERMS["switch_reserved"],
    "WARMUP": "준비 중(지표 계산)",
    "REPLAY": "재생(주문 없음)",
    "BACKFILL": "재평가(주문 없음)",
    "PENDING_FILL": "체결 대기",
    "STATE_POLLUTED": "지표 확인 필요 — 매수 멈춤",
    "TENTATIVE": "잠정 봉(판정 안 함)",
    "UNCONFIRMED": "확정 전 봉(판정 안 함)",
    "DUPLICATE": "이미 본 봉(판정 안 함)",
}

# 회차 건너뜀·주문 전 차단 원인(엔진 알림 제목·감사 체결 표 「새 전략 내용」 공용)
PULLBACK_SKIP_CAUSE: dict[str, str] = {
    "split_krw_short": "원화 잔고 부족",
    "split_below_min": "최소 주문금액 미만",
    "split_krw_unknown": "원화 잔고 조회 실패",
    "split_no_capital": "운용 금액 없음",
    "split_unconfirmed_bar": "봉 마감 확인 전",
}

# 지갑 대조(PULLBACK_SYNC) 사유 코드 → 화면 문구
PULLBACK_SYNC_CLASS_LABEL: dict[str, str] = {
    "wallet_more": "지갑 수량이 더 많음",
    "wallet_less": "지갑 수량이 더 적음",
    "restart_mismatch": "재시작 때 수량 다름",
}

_INACTIVE_LABEL = {"not_golden": "60선 ≤ 200선", "slope_low": "200선 기울기 낮음", "slope_drop": "200선 기울기 둔화"}

# 거래 행 분류(services.trade_strategy.classify) → 화면 라벨. 분류 불명은 경고 없이 「-」(결정 1028-06).
_STRATEGY_CLASS_LABEL = {"PULLBACK": NEW_STRATEGY_LABEL, "EMA": "EMA", "MACD": "MACD",
                         "LEGACY": "옛 기록(EMA/MACD)", "UNKNOWN": "-"}


def split_round_text(n) -> str:
    """「분할 n회차」."""
    return PULLBACK_TERMS["split_round"].replace("n", str(n))


def strategy_class_label(cls) -> str:
    return _STRATEGY_CLASS_LABEL.get(str(cls or "").upper(), str(cls or "-"))


def format_price(x) -> str:
    """가격 표기(업비트 호가 단위 대략 — 끝자리 0 은 지움). 숫자가 아니면 「-」."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    a = abs(v)
    dec = 0 if a >= 1000 else 1 if a >= 100 else 2 if a >= 10 else 3 if a >= 1 else 4
    s = f"{v:,.{dec}f}"
    if dec:
        s = s.rstrip("0").rstrip(".")
    return s


def pullback_eval_text(failed_keys, checks) -> str:
    """새 전략 판정 감사 행 1줄(BUY·SELL 평가 표 「새 전략 상태」, 감사 메모)."""
    ck = checks if isinstance(checks, dict) else {}
    keys = list(failed_keys or [])
    rnd = ck.get("round")
    if ck.get("sell_reason"):
        return f"매도 신호 · {PULLBACK_REASON_LABEL.get(ck['sell_reason'], ck['sell_reason'])}"
    if not keys and ck.get("buy_reason"):
        return f"{split_round_text(rnd)} · {PULLBACK_REASON_LABEL.get(ck['buy_reason'], ck['buy_reason'])}"
    if not keys:
        return "-"
    k = keys[0]
    text = PULLBACK_STATE_LABEL.get(k, k)
    if k == "WAIT_PULLBACK" and isinstance(rnd, int):
        text = f"{text} — {rnd + 1}회차 준비"
    elif k == "NOT_ACTIVE" and ck.get("inactive_reason") in _INACTIVE_LABEL:
        text = f"{text}({_INACTIVE_LABEL[ck['inactive_reason']]})"
    return text


def _is_pullback_checks(ck) -> bool:
    return isinstance(ck, dict) and (ck.get("strategy") == "PULLBACK" or ck.get("strategy_mode") == "PULLBACK")


def add_pullback_eval_columns(df):
    """
    감사 BUY·SELL 평가 표: 새 전략 행이 하나라도 있으면 「strategy_label」(새 전략)·「pullback_state」 칸을 더한
    사본을 돌려준다. 없으면 받은 df 를 그대로 돌려준다(EMA·MACD 화면 무변경).
    SELL 평가 표(audit_sell_eval)는 failed_keys 칸이 없다 — checks.failed_keys 로 채운다.
    """
    try:
        if df is None or "checks" not in df.columns:
            return df
        mask = [_is_pullback_checks(c) for c in df["checks"]]
        if not any(mask):
            return df
        out = df.copy()
        fks = out["failed_keys"].tolist() if "failed_keys" in out.columns else [None] * len(out)
        fks = [fk if fk else (ck.get("failed_keys") if isinstance(ck, dict) else None)
               for fk, ck in zip(fks, out["checks"])]
        out["strategy_label"] = [NEW_STRATEGY_LABEL if m else "" for m in mask]
        out["pullback_state"] = [pullback_eval_text(fk, ck) if m else ""
                                 for m, fk, ck in zip(mask, fks, out["checks"])]
        return out
    except Exception as e:
        logger.warning(f"[TERMS] 새 전략 평가 칸 만들기 실패 → 표 그대로: {type(e).__name__}: {e}")
        return df


def _meta_dict(meta) -> dict:
    if isinstance(meta, dict):
        return meta
    try:
        import json
        m = json.loads(meta) if isinstance(meta, str) and meta else {}
        return m if isinstance(m, dict) else {}
    except Exception as e:
        logger.warning(f"[TERMS] 체결 행 meta 읽기 실패 → 빈 값: {type(e).__name__}")
        return {}


def pullback_sync_reason_text(cls) -> str:
    """지갑 대조 사유 코드(wallet_more 등) → 화면 문구. 모르는 코드는 그대로."""
    return PULLBACK_SYNC_CLASS_LABEL.get(str(cls or ""), str(cls or ""))


def pullback_trade_text(trade_type, reason, meta) -> str:
    """새 전략 체결 행 1줄(체결 표 「새 전략 내용」). trade_type 은 DB 원래 유형(화면 문자열로 바꾸기 전)."""
    t = str(trade_type or "").upper()
    m = _meta_dict(meta)
    if t == "PULLBACK_SYNC":
        cls = m.get("class") or reason
        if cls in PULLBACK_SYNC_CLASS_LABEL:
            return f"보유 수량 맞춤(지갑 기준) — {PULLBACK_SYNC_CLASS_LABEL[cls]} · 추가 분할 매수 멈춤"
        return "보유 수량 맞춤(지갑 기준) — 추가 분할 매수 멈춤"
    if t == "BUY" and m.get("split_round") is not None:
        txt = f"{split_round_text(m['split_round'])} · {PULLBACK_REASON_LABEL.get(str(reason or '').upper(), PULLBACK_TERMS['buy_pullback'])}"
        if m.get("avg_after") is not None:
            txt += f" · 평단 {format_price(m['avg_after'])}원"
        return txt
    if t == "SELL" and m.get("judged_reason"):
        jr = str(m["judged_reason"]).upper()
        txt = f"{PULLBACK_REASON_LABEL.get(jr, jr)} 판정 {format_price(m.get('judged_price'))}원"
        if m.get("fill_price") is not None:
            txt += f" · 체결 {format_price(m['fill_price'])}원"
        if m.get("split_round"):
            txt += f" ({split_round_text(m['split_round'])}까지 정리)"
        return txt
    if t.endswith("_REJECTED"):
        # 주문 전 차단 행 meta 는 차단 코드를 error_name 에 둔다(trader._audit_preorder_reject)
        code = str(m.get("error_name") or m.get("fail_code") or "")
        if code == "split_order_cooldown":
            return "매수 잠시 쉼(주문 실패 뒤)"
        if code.startswith("split_") or m.get("split_round") is not None:
            head = (f"{split_round_text(m['split_round'])} 건너뜀" if m.get("split_round") is not None
                    else PULLBACK_TERMS["round_skipped"])
            cause = PULLBACK_SKIP_CAUSE.get(code)
            return f"{head} — {cause}" if cause else head
        return ""
    return ""


def add_pullback_trade_columns(df, classes, raw_types=None):
    """
    감사 체결 표: classes(행마다 services.trade_strategy.classify 결과)에 PULLBACK 이 하나라도 있으면
    「strategy_label」·「pullback_detail」 칸을 더한 사본, 없으면 받은 df 그대로(EMA·MACD 화면 무변경).
    raw_types = 화면 문자열로 바꾸기 전 DB 유형(없으면 df["type"]). 수량 맞춤 행의 사유 코드는 한글로 바꾼다.
    분류 불명은 「-」 — 화면 경고를 띄우지 않는다(결정 1028-06).
    """
    try:
        cls = [str(c or "").upper() for c in (classes or [])]
        if df is None or len(cls) != len(df) or "PULLBACK" not in cls:
            return df
        out = df.copy()
        types = list(raw_types) if raw_types is not None else out["type"].tolist()
        if len(types) != len(out):
            types = out["type"].tolist()
        metas = out["meta"].tolist() if "meta" in out.columns else [None] * len(out)
        reasons = out["reason"].tolist() if "reason" in out.columns else [None] * len(out)
        out["strategy_label"] = [strategy_class_label(c) for c in cls]
        out["pullback_detail"] = [pullback_trade_text(t, r, m) if c == "PULLBACK" else ""
                                  for c, t, r, m in zip(cls, types, reasons, metas)]
        if "reason" in out.columns:
            out["reason"] = [pullback_sync_reason_text(r) if str(t or "").upper() == "PULLBACK_SYNC" else r
                             for t, r in zip(types, reasons)]
        return out
    except Exception as e:
        logger.warning(f"[TERMS] 새 전략 체결 칸 만들기 실패 → 표 그대로: {type(e).__name__}: {e}")
        return df
