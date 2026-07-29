"""
✅ [Phase 3-B] Audit Logger — JSONL RotatingFileHandler.

목적:
- 매매 판정 이벤트를 구조화 JSONL 로 별도 파일에 기록.
- systemd journal 은 순차 스캔이라 grep/awk 로 사후 분석 어려움.
- 별도 파일 → 쉬운 검색 + rotation 으로 디스크 관리.

파일: {user_id}_audit.log (10MB × 20 rotation, 기본 200MB)
포맷: JSONL — 한 줄 = 한 이벤트, 필드는 구조화

이벤트 예시:
{"ts": "2026-07-29T00:00:00", "code": "SL_TRIG", "ticker": "KRW-JTO",
 "pnl_pct": -0.045, "threshold": -0.03, "context": {...}}

원칙:
- 매매 흐름 절대 방해 X (실패 시 무해 warning).
- lazy handler (파일 없으면 생성).
- Python 표준 logging 활용 (성능 검증됨).
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


_HANDLER_LOCK = threading.Lock()
_HANDLERS: dict[str, logging.Logger] = {}


def _get_audit_logger(user_id: str) -> logging.Logger:
    """
    사용자별 별도 audit logger 반환. 최초 호출 시 handler 초기화.
    파일: {user_id}_audit.log (프로젝트 루트 기준)
    """
    if user_id in _HANDLERS:
        return _HANDLERS[user_id]

    with _HANDLER_LOCK:
        if user_id in _HANDLERS:
            return _HANDLERS[user_id]

        # 별도 이름공간 (services.audit_logger 와 분리)
        lg = logging.getLogger(f"tradebot.audit.{user_id}")
        lg.setLevel(logging.INFO)
        lg.propagate = False  # 상위 logger 로 전파 X (systemd journal 중복 방지)

        try:
            log_path = f"{user_id}_audit.log"
            handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=20,              # 200MB 상한
                encoding="utf-8",
            )
            # 포맷 = raw JSON (message 는 이미 JSON string)
            handler.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(handler)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"[AUDIT_LOGGER] {user_id} handler 초기화 실패 (무해): {e}"
            )

        _HANDLERS[user_id] = lg
        return lg


def event(
    user_id: str,
    code: str,
    *,
    ticker: Optional[str] = None,
    level: str = "INFO",
    **context: Any,
) -> None:
    """
    audit 이벤트 1건 기록.

    Args:
        user_id: 사용자 ID (파일 분리 키)
        code: 이벤트 코드 (예: SL_TRIG, TP_TRIG, HTS_DETECT, INVARIANT_I1, ...)
        ticker: KRW-JTO 등 (없으면 생략)
        level: INFO / WARN / CRITICAL / ERROR
        **context: 임의 필드 (pnl_pct=..., threshold=..., avg_price=..., etc.)

    예시:
        event("mcmax33", "SL_TRIG", ticker="KRW-JTO",
              pnl_pct=-0.045, threshold=-0.03, current_price=872, avg_price=915)
    """
    try:
        payload = {
            "ts": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "level": level,
            "code": code,
            "user_id": user_id,
        }
        if ticker:
            payload["ticker"] = ticker
        # context 병합 (기본 필드 덮어쓰기 방지)
        for k, v in context.items():
            if k not in payload:
                payload[k] = _safe_serialize(v)

        lg = _get_audit_logger(user_id)
        lg.info(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        # 절대 예외 상위로 전파 금지
        logger.warning(f"[AUDIT_LOGGER] event 기록 실패 (무해) code={code}: {e}")


def _safe_serialize(v: Any) -> Any:
    """JSON 직렬화 가능한 형태로 변환."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _safe_serialize(vv) for k, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [_safe_serialize(x) for x in v]
    # fallback: str
    return str(v)


# 자주 쓰는 이벤트 헬퍼 (선택적 사용)

def sell_triggered(user_id: str, ticker: str, reason: str, pnl_pct: float,
                   avg_price: float, current_price: float, **extra) -> None:
    """SELL 발동 이벤트. 사후 분석 시 최우선 조회 대상."""
    event(user_id, "SELL_TRIGGERED", ticker=ticker, level="INFO",
          reason=reason, pnl_pct=pnl_pct, avg_price=avg_price,
          current_price=current_price, **extra)


def buy_triggered(user_id: str, ticker: str, reason: str, price: float,
                  qty: float, **extra) -> None:
    """BUY 발동 이벤트."""
    event(user_id, "BUY_TRIGGERED", ticker=ticker, level="INFO",
          reason=reason, price=price, qty=qty, **extra)


def invariant_violation(user_id: str, ticker: str, code: str, msg: str,
                        **details) -> None:
    """Invariant 위반 이벤트. CRITICAL 레벨로 기록."""
    event(user_id, f"INVARIANT_{code}", ticker=ticker, level="CRITICAL",
          msg=msg, **details)


def hts_detected(user_id: str, ticker: str, kind: str, avg_price: float,
                 qty: float, **extra) -> None:
    """HTS 매수/매도 감지 이벤트."""
    event(user_id, "HTS_DETECTED", ticker=ticker, level="INFO",
          kind=kind, avg_price=avg_price, qty=qty, **extra)
