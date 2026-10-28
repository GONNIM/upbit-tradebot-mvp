"""
2차 T8 (2026-10-28): 새 전략(PULLBACK) 체결 감사 행 칸 — trader(TEST)·reconciler(LIVE) 공용.

모듈 맨 위는 표준 라이브러리만 쓴다(EMA·MACD 체결 기록 경로가 이 모듈 import 때문에 깨지지 않게).
매도 거절 문구 함수만 안에서 services.error_messages·services.terminology 를 부른다.
발주 meta 에 strategy_type=PULLBACK 과 split_round 가 있을 때만 값을 돌려준다. 그 밖은 None —
호출부는 None 이면 지금(T7)과 같은 인자로 insert_trade_audit 를 부른다(EMA·MACD 행 무변경).
"""
from __future__ import annotations

import json
from typing import Optional


def split_trade_audit(order_meta: Optional[dict], *, side: str, fill_price, fill_qty) -> Optional[tuple]:
    """
    (meta JSON 문자열, entry_price) 또는 None.
      BUY : {"split_round","pullback_round","avg_after","reason","per_buy"}, entry_price = 체결 뒤 평단
            = (발주 때 기준 원가 + 체결 수량×체결가) / (기준 수량 + 체결 수량) — 엔진 apply_split_entry 와 같은 식.
      SELL: {"split_round","pullback_round","judged_reason","judged_price","fill_price"},
            entry_price = 발주 meta 값(매도 전 평단 — 지금과 같음).
    """
    m = order_meta or {}
    if str(m.get("strategy_type") or "").upper() != "PULLBACK" or m.get("split_round") is None:
        return None
    s = str(side or "").upper()
    if s == "BUY":
        q = float(fill_qty or 0.0)
        px = float(fill_price or 0.0)
        bq = float(m.get("base_qty") or 0.0)
        bc = float(m.get("base_cost") or 0.0)
        avg = (bc + q * px) / (bq + q) if (bq + q) > 0 else None
        body = {"split_round": m.get("split_round"), "pullback_round": m.get("pullback_round"),
                "avg_after": avg, "reason": m.get("reason"), "per_buy": m.get("per_buy")}
        return json.dumps(body, ensure_ascii=False), avg
    if s == "SELL":
        body = {"split_round": m.get("split_round"), "pullback_round": m.get("pullback_round"),
                "judged_reason": m.get("judged_reason"), "judged_price": m.get("judged_price"),
                "fill_price": (float(fill_price) if fill_price is not None else None)}
        return json.dumps(body, ensure_ascii=False), m.get("entry_price")
    return None


def pullback_sell_reject_text(ticker: str, reason, qty, label: str, err_summary) -> tuple:
    """새 전략 매도 거절 텔레그램 (제목, 본문). 거절 코드와 할 일을 함께 적는다(외부 주문 공존 규칙).
    insufficient_funds_ask(수량 묶임)는 외부 미체결 매도 주문 확인을 할 일로 적는다."""
    from services.error_messages import error_code_of
    from services.terminology import PULLBACK_REASON_LABEL   # 매도 사유 화면 용어는 한 곳(terminology)에만
    code = error_code_of(err_summary)
    _r = str(reason or "").upper()
    what = PULLBACK_REASON_LABEL.get(_r, "매도") if _r in ("TP", "SL", "DEADCROSS") else "매도"
    if code == "insufficient_funds_ask":
        todo = ("할 일: 업비트 앱에서 외부 미체결 매도 주문을 확인해 주세요. "
                "앱에서 직접 넣은 매도 주문이 수량을 묶고 있으면 봇 매도가 거절됩니다.")
    else:
        todo = "할 일: 업비트 앱에서 보유 수량과 미체결 주문을 확인해 주세요."
    try:
        qty_txt = f"{float(qty):,.8g}"
    except (TypeError, ValueError):
        qty_txt = "-"
    title = f"❌ 새 전략 매도 거절 — {ticker}"
    body = (f"{what} 매도 주문({qty_txt}개)을 거래소가 받지 않았습니다.\n"
            f"사유: {label} (거래소 응답: {code})\n"
            "보유 수량은 그대로이고, 다음 봉에서 매도 조건을 다시 확인합니다.\n"
            f"{todo}")
    return title, body
