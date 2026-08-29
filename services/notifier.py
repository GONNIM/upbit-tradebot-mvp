"""
Telegram 알림 모듈 — Upbit Tradebot 운영 이벤트 푸시.

설계 원칙:
- 단일 진입점 `send(level, title, body, dedupe_key=None)`.
- 환경변수(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)가 없으면 silent skip — 개발 환경에서 무해.
- 내부에서 모든 예외/타임아웃을 흡수 → 호출자(트레이더/엔진)의 본업을 절대 차단하지 않음.
- dedupe_key가 동일하면 dedupe_ttl(기본 300s) 동안 1회만 전송 — 스팸 방지.
- API 키/JWT/원문 토큰은 절대 메시지에 포함하지 않음.

호출 예시:
    from services.notifier import send, LEVEL_CRITICAL
    send(LEVEL_CRITICAL, "🟢 [LIVE BUY 체결] KRW-KITE",
         f"price≈{price:,.2f} KRW\\nuuid={uuid}")
"""
from __future__ import annotations

import html as _html
import logging
import os
import threading
import time
from typing import Optional, Tuple

try:
    import requests as _requests  # type: ignore
except ImportError:  # pragma: no cover
    _requests = None

logger = logging.getLogger(__name__)

LEVEL_CRITICAL = "CRITICAL"
LEVEL_WARNING = "WARNING"
LEVEL_INFO = "INFO"

_TELEGRAM_API_BASE = "https://api.telegram.org"
_HTTP_TIMEOUT = 5  # seconds
_DEFAULT_DEDUPE_TTL = 300  # 5 minutes

_LEVEL_PREFIX = {
    LEVEL_CRITICAL: "🚨",
    LEVEL_WARNING: "⚠️",
    LEVEL_INFO: "ℹ️",
}

# 단일 프로세스 dedupe 상태 (스레드 안전)
_dedupe_lock = threading.Lock()
_dedupe_state: dict = {}


def _get_credentials(level: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    환경변수 우선, 없으면 streamlit secrets 시도. 둘 다 없으면 (None, None).

    ✅ [Phase 3-C] 3-tier 채널 분리 (backward compatible):
    - level 이 주어지고 TELEGRAM_CHAT_ID_<LEVEL> 이 세팅되어 있으면 그 채널 사용.
    - 없으면 기본 TELEGRAM_CHAT_ID 사용 (기존 동작).
    - 실 자금 사용자는 CRITICAL 을 개인 폰, WARN 을 그룹 채널로 분리 가능.

    예시 환경변수:
        TELEGRAM_BOT_TOKEN=xxx
        TELEGRAM_CHAT_ID=default_chat        # 기본 (기존 유지)
        TELEGRAM_CHAT_ID_CRITICAL=personal   # CRITICAL 만 개인
        TELEGRAM_CHAT_ID_WARNING=group       # WARN 만 그룹
        TELEGRAM_CHAT_ID_INFO=archive        # INFO 만 아카이브
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    # ✅ 3-tier: level 별 채널 우선
    chat = None
    if level:
        level_upper = str(level).upper()
        chat = os.environ.get(f"TELEGRAM_CHAT_ID_{level_upper}")
    # tier 없으면 기본 채널
    if not chat:
        chat = os.environ.get("TELEGRAM_CHAT_ID")

    if token and chat:
        return token, chat

    try:
        import streamlit as _st  # type: ignore
        if not token:
            token = _st.secrets.get("TELEGRAM_BOT_TOKEN")
        if not chat and level:
            chat = _st.secrets.get(f"TELEGRAM_CHAT_ID_{str(level).upper()}")
        if not chat:
            chat = _st.secrets.get("TELEGRAM_CHAT_ID")
    except Exception:
        pass
    if not token or not chat:
        return None, None
    return str(token), str(chat)


def _should_skip_by_dedupe(key: Optional[str], ttl: int) -> bool:
    if not key:
        return False
    now = time.time()
    with _dedupe_lock:
        last = _dedupe_state.get(key, 0)
        if now - last < ttl:
            return True
        _dedupe_state[key] = now
        # 누적 상한 (오래된 키 정리)
        if len(_dedupe_state) > 256:
            cutoff = now - ttl * 4
            for k in list(_dedupe_state.keys()):
                if _dedupe_state[k] < cutoff:
                    _dedupe_state.pop(k, None)
        return False


def _format_message(level: str, title: str, body: str) -> str:
    prefix = _LEVEL_PREFIX.get(level, "")
    safe_title = _html.escape(title or "")
    safe_body = _html.escape(body or "")
    if safe_body:
        return f"<b>{prefix} {safe_title}</b>\n<pre>{safe_body}</pre>"
    return f"<b>{prefix} {safe_title}</b>"


def send(
    level: str,
    title: str,
    body: str = "",
    dedupe_key: Optional[str] = None,
    dedupe_ttl: int = _DEFAULT_DEDUPE_TTL,
) -> bool:
    """
    Telegram으로 알림 1건 전송.

    Returns:
        True  — sendMessage 200 응답
        False — 자격증명 없음 / dedupe로 스킵 / 네트워크 오류 등 / dry-run 억제
    """
    try:
        # ✅ WO-6 보완 F2 (2026-08-26): dry-run 모드에서는 실제 발송 억제.
        # scripts/live_dry_run.py 가 os.environ['WO6_DRY_RUN']='1' 을 세팅한다.
        # 운영 채널이 검증 소음으로 오염되어 진짜 경보를 놓치는 것을 방지.
        if os.environ.get("WO6_DRY_RUN") == "1":
            logger.info(
                f"[NOTIFY-DRY-RUN] 실 발송 억제 | level={level} title={title!r} "
                f"body_len={len(body or '')}"
            )
            return False

        if _should_skip_by_dedupe(dedupe_key, dedupe_ttl):
            return False
        # ✅ [Phase 3-C] level 기반 채널 라우팅
        token, chat = _get_credentials(level=level)
        if not token or not chat:
            return False
        if _requests is None:
            logger.warning("[NOTIFY] requests 미설치 — 스킵")
            return False
        text = _format_message(level, title, body)
        resp = _requests.post(
            f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage",
            data={
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            return True
        logger.warning(
            f"[NOTIFY] Telegram sendMessage 실패 status={resp.status_code} "
            f"body={resp.text[:200]}"
        )
        return False
    except Exception as e:
        # 본업을 절대 차단하지 않는다
        logger.warning(f"[NOTIFY] send() 예외 흡수: {type(e).__name__}: {e}")
        return False
