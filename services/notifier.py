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


AUDIENCE_OPERATOR = "operator"
_OPERATOR_CHAT_KEY = "TELEGRAM_CHAT_ID_OPERATOR"


def _get_operator_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    ✅ 1028-15 (나): 운영자 전용 채널. 투자자도 보는 기본·등급 채널로 **넘어가지 않는다**.

    - 토큰: 기존과 같이 환경변수 TELEGRAM_BOT_TOKEN → streamlit secrets.
    - 채팅 ID: TELEGRAM_CHAT_ID_OPERATOR 만 환경변수 → streamlit secrets 에서 찾는다.
      없으면 채팅 ID 는 None (TELEGRAM_CHAT_ID·TELEGRAM_CHAT_ID_<LEVEL> 로 대체하지 않음).
    - _get_credentials(level="OPERATOR") 를 쓰지 않는다: 그 함수는 등급 키가 없으면 기본 채널로 넘어간다.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get(_OPERATOR_CHAT_KEY)
    if not token or not chat:
        try:
            import streamlit as _st  # type: ignore
            if not token:
                token = _st.secrets.get("TELEGRAM_BOT_TOKEN")
            if not chat:
                chat = _st.secrets.get(_OPERATOR_CHAT_KEY)
        except Exception:
            pass
    return (str(token) if token else None), (str(chat) if chat else None)


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


def _token_only() -> Optional[str]:
    """토큰만 찾는다(환경변수 → streamlit secrets). 채팅이 없을 때 상태를 no_token/no_chat 으로 나누는 데만 쓴다."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok
    try:
        import streamlit as _st  # type: ignore
        tok = _st.secrets.get("TELEGRAM_BOT_TOKEN")
    except Exception:
        tok = None
    return str(tok) if tok else None


def _error_code_of(resp) -> str:
    """Telegram 실패 응답에서 error_code 숫자만(응답 원문은 남기지 않는다 — 1122-01)."""
    try:
        code = (resp.json() or {}).get("error_code")
        return str(int(code)) if code is not None else "-"
    except Exception:
        return "-"


# _send_core 상태 (1122-01 계획 3-1): 분기·순서는 옛 send() 와 같고 return 값만 상태다.
# dry_run · dedupe · no_op_chat · no_token · no_chat · no_requests · sent · http_fail · exception
_COPY_STATUSES = ("no_op_chat", "no_chat", "sent", "http_fail", "exception")


def _send_core(level, title, body, dedupe_key, dedupe_ttl, audience) -> Tuple[str, Optional[str]]:
    """운영자 쪽 판정·발송. (상태, 이번에 쓴 채팅 — 사본이 같은 채팅이면 보내지 않으려고만 씀)."""
    chat = None
    try:
        # ✅ WO-6 보완 F2 (2026-08-26): dry-run 모드에서는 실제 발송 억제.
        # scripts/live_dry_run.py 가 os.environ['WO6_DRY_RUN']='1' 을 세팅한다.
        # 운영 채널이 검증 소음으로 오염되어 진짜 경보를 놓치는 것을 방지.
        if os.environ.get("WO6_DRY_RUN") == "1":
            logger.info(
                f"[NOTIFY-DRY-RUN] 실 발송 억제 | level={level} title={title!r} "
                f"body_len={len(body or '')}"
            )
            return "dry_run", None

        if _should_skip_by_dedupe(dedupe_key, dedupe_ttl):
            return "dedupe", None
        if audience == AUDIENCE_OPERATOR:
            # ✅ 1028-15: 운영자 전용 — 기본·등급 채널로 대체하지 않는다
            token, chat = _get_operator_credentials()
            if not chat:
                logger.info("[NOTIFY] operator 채널 없음 — 로그만")
                return "no_op_chat", None
        else:
            # ✅ [Phase 3-C] level 기반 채널 라우팅
            token, chat = _get_credentials(level=level)
        if not token or not chat:
            if audience == AUDIENCE_OPERATOR:
                return "no_token", chat
            return ("no_chat" if _token_only() else "no_token"), None
        if _requests is None:
            logger.warning("[NOTIFY] requests 미설치 — 스킵")
            return "no_requests", chat
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
            # ✅ WO-24 (2026-10-05): 발송 성공 1줄 — 토큰·채팅 ID 는 적지 않는다
            logger.info(f"[NOTIFY] sent | kind={level} dedupe={dedupe_key}")
            return "sent", chat
        # ✅ 1122-01: 응답 원문 대신 상태 숫자와 error_code 숫자만
        logger.warning(
            f"[NOTIFY] Telegram sendMessage 실패 status={resp.status_code} "
            f"error_code={_error_code_of(resp)}"
        )
        return "http_fail", chat
    except Exception as e:
        # 본업을 절대 차단하지 않는다. ✅ 1122-01: 예외 글에는 토큰 든 주소가 섞일 수 있어 종류 이름만 남긴다.
        logger.warning(f"[NOTIFY] send() 예외 흡수: {type(e).__name__}")
        return "exception", chat


def send(
    level: str,
    title: str,
    body: str = "",
    dedupe_key: Optional[str] = None,
    dedupe_ttl: int = _DEFAULT_DEDUPE_TTL,
    audience: Optional[str] = None,
    investor_copy: bool = True,
) -> bool:
    """
    Telegram으로 알림 1건 전송.

    - audience=None(기본): 지금과 같은 등급별 채널(_get_credentials).
    - audience="operator" (1028-15): 운영자 전용 채널만(_get_operator_credentials). 운영자 채팅 ID 가 없으면
      보내지 않고 `[NOTIFY] operator 채널 없음 — 로그만` 1줄만 남긴다(기본·등급 채널로 넘어가지 않음).
    - 투자자 사본 (1122-01, 2026-11-23 사용자 지시): 운영자 쪽 판정·발송이 끝난 뒤 투자자 채팅
      (TELEGRAM_CHAT_ID_INVESTOR)으로 사본 1건을 대기 줄에 넣는다(services/investor_copy.py 일꾼 스레드가 보냄).
      사본 글은 운영자가 받는 글 그대로다(가공·수정 없음 — 2026-11-24 사용자 지시). 운영자 전용 알림도 사본이 간다.
      investor_copy=False 면 넣지 않는다. 운영자 쪽 글·채널·dedupe·반환값은 바뀌지 않는다.

    Returns:
        True  — sendMessage 200 응답
        False — 자격증명 없음 / dedupe로 스킵 / 네트워크 오류 등 / dry-run 억제
    """
    status, used_chat = _send_core(level, title, body, dedupe_key, dedupe_ttl, audience)
    ok = (status == "sent")
    if investor_copy and status in _COPY_STATUSES:
        try:
            from services import investor_copy as _ic
            _ic.enqueue(level, title, body, used_chat)
        except Exception:
            pass
    return ok


def copy_state() -> Tuple[bool, str]:
    """투자자 사본 켜짐 여부와 사유 (cron 출력용)."""
    try:
        from services import investor_copy as _ic
        return _ic.state()
    except Exception:
        return False, "오류"


def flush_copies(timeout: float = 3.0) -> bool:
    """한 번 돌고 끝나는 프로세스(cron)용 — 대기 줄의 사본을 최대 timeout 초 기다려 보낸다."""
    try:
        from services import investor_copy as _ic
        return _ic.flush(timeout)
    except Exception:
        return False
