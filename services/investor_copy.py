"""투자자 채팅 알림 사본 (1122-01 ②~④, 계획 docs/plans/2026-11-23-investor-all-alerts/plan.md).

- services.notifier.send() 가 운영자 쪽 판정·발송을 끝낸 뒤 enqueue() 로 사본 1건을 대기 줄에 넣는다.
  호출한 스레드(매매 스레드 포함)는 put_nowait 한 번만 한다. 끄는 파일 확인·발송은
  일꾼 스레드(이름 notify-copy) 안에서 한다. 대기 줄이 차면 새 사본을 버린다(매매 스레드는 기다리지 않음).
- 사본 글 = 운영자가 받는 글 그대로(notifier._format_message 같은 결과 · 가공·수정 없음 — 2026-11-24 사용자 지시
  「투자자도 내(개발자)가 받는 알림 그대로 받으면 된다. 가공하거나 수정할 필요가 전혀 없다.」).
- 투자자 채팅: 환경변수 TELEGRAM_CHAT_ID_INVESTOR(.env). 이번 운영자·등급 채팅과 같으면 보내지 않는다.
- 끄는 법: services/data/.investor_copy_off 파일(재시작 없이 바로) · TELEGRAM_INVESTOR_COPY=0 · INVESTOR 줄 삭제.
- 토큰·채팅 번호·요청 주소·예외 글은 어떤 로그에도 남기지 않는다. 로그 태그: [NOTIFY-COPY].
- 403(투자자가 봇을 막음) 1시간 쉼 · 429 retry_after(없으면 60초) 쉼 · 연속 실패 5번 30분 쉼.
  쉼이 시작되면 운영자에게 하루 1건(investor_copy=False — 사본의 사본 없음).
"""
from __future__ import annotations

import atexit
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

INVESTOR_CHAT_KEY = "TELEGRAM_CHAT_ID_INVESTOR"
COPY_SWITCH_KEY = "TELEGRAM_INVESTOR_COPY"
ROOT = Path(__file__).resolve().parent.parent
OFF_FILE = ROOT / "services" / "data" / ".investor_copy_off"

QUEUE_MAX = 16
FLUSH_TIMEOUT = 3.0
HTTP_TIMEOUT = 5
PAUSE_403_SEC = 3600
PAUSE_429_DEFAULT_SEC = 60
FAIL_STREAK_LIMIT = 5
PAUSE_STREAK_SEC = 1800

_q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
_worker: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_state_lock = threading.Lock()
_pause_until = 0.0
_fail_streak = 0
_last_full_log = 0.0
_atexit_done = False
last_result = "none"   # none · sent · off:<사유> · fail:<코드> · paused · dropped


# ================================================================ 켜짐/꺼짐
def env_state() -> Tuple[bool, str]:
    """호출 스레드에서 보는 가벼운 판정(환경변수만). (켜짐 여부, 사유)."""
    if os.environ.get(COPY_SWITCH_KEY, "").strip() == "0":
        return False, "env끔"
    if not (os.environ.get(INVESTOR_CHAT_KEY) or "").strip():
        return False, "채팅없음"
    return True, "켜짐"


def state(off_file: Optional[Path] = None) -> Tuple[bool, str]:
    """끄는 파일까지 본 판정 (일꾼·기동 로그·cron 출력용)."""
    ok, why = env_state()
    if not ok:
        return ok, why
    try:
        if (off_file or OFF_FILE).exists():
            return False, "파일"
    except Exception:
        return False, "파일"
    return True, "켜짐"


def log_state() -> None:
    """프로세스 기동 때 1줄: [NOTIFY-COPY] on|off reason=<파일|env끔|채팅없음|켜짐> (값 없음)."""
    ok, why = state()
    logger.info(f"[NOTIFY-COPY] {'on' if ok else 'off'} reason={why}")


# ================================================================ 대기 줄·일꾼
def enqueue(level: str, title: str, body: str, used_chat: Optional[str]) -> bool:
    """호출 스레드용 — 환경변수 판정과 put_nowait 만. 막히지 않는다. 넣었으면 True."""
    global _last_full_log
    ok, _why = env_state()
    if not ok:
        return False
    _ensure_worker()
    try:
        _q.put_nowait((level, title, body, used_chat))
        return True
    except queue.Full:
        now = time.monotonic()
        if now - _last_full_log >= 60:
            _last_full_log = now
            logger.warning("[NOTIFY-COPY] 대기 줄 가득 — 새 사본 버림")
        return False


def _ensure_worker() -> None:
    global _worker, _atexit_done
    w = _worker
    if w is not None and w.is_alive():
        return
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        try:
            t = threading.Thread(target=_run, name="notify-copy", daemon=True)
            t.start()
            _worker = t
        except Exception:
            logger.warning("[NOTIFY-COPY] 일꾼 시작 실패")
            return
        if not _atexit_done:
            _atexit_done = True
            try:
                atexit.register(flush)
            except Exception:
                pass


def _run() -> None:
    while True:
        try:
            item = _q.get()
        except Exception:
            continue
        try:
            _process(item)
        except Exception:
            pass
        finally:
            try:
                _q.task_done()
            except Exception:
                pass


def flush(timeout: float = FLUSH_TIMEOUT) -> bool:
    """대기 줄이 빌 때까지 최대 timeout 초 기다린다. 다 보냈으면 True."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    while time.monotonic() < deadline:
        if _q.unfinished_tasks == 0:
            return True
        time.sleep(0.02)
    return _q.unfinished_tasks == 0


def _copy_token() -> Optional[str]:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok
    try:
        import streamlit as _st  # type: ignore
        tok = _st.secrets.get("TELEGRAM_BOT_TOKEN")
    except Exception:
        tok = None
    return str(tok) if tok else None


def _pause(sec: float, why: str) -> None:
    global _pause_until
    with _state_lock:
        _pause_until = time.monotonic() + float(sec)
    logger.warning(f"[NOTIFY-COPY] 쉼 {int(sec)}초 reason={why}")
    try:
        from services import notifier
        notifier.send(notifier.LEVEL_WARNING, "투자자 알림 사본 잠시 멈춤",
                      f"투자자 채팅으로 보내는 알림 사본이 {why} 때문에 약 {max(1, int(sec) // 60)}분 멈췄습니다. "
                      "운영자 알림은 그대로 나갑니다.",
                      dedupe_key="investor_copy_pause", dedupe_ttl=86400, investor_copy=False)
    except Exception:
        pass


def _process(item) -> None:
    global _fail_streak, last_result
    level, title, body, used_chat = item
    ok, why = state()
    if not ok:
        last_result = "off:" + why
        return
    chat = (os.environ.get(INVESTOR_CHAT_KEY) or "").strip()
    if not chat or (used_chat is not None and str(used_chat) == chat):
        last_result = "off:같은채팅" if chat else "off:채팅없음"
        return
    with _state_lock:
        paused = time.monotonic() < _pause_until
    if paused:
        last_result = "paused"
        return
    token = _copy_token()
    if not token:
        last_result = "fail:no_token"
        return
    from services import notifier
    req = notifier._requests
    if req is None:
        last_result = "fail:no_requests"
        return
    err = "-"
    resp = None
    try:
        resp = req.post(
            f"{notifier._TELEGRAM_API_BASE}/bot{token}/sendMessage",
            data={"chat_id": chat, "text": notifier._format_message(level, title, body),
                  "parse_mode": "HTML", "disable_web_page_preview": "true"},
            timeout=HTTP_TIMEOUT,
        )
        code = getattr(resp, "status_code", None)
    except Exception as e:
        code = None
        err = type(e).__name__
    if code == 200:
        _fail_streak = 0
        last_result = "sent"
        logger.info(f"[NOTIFY-COPY] sent | kind={level}")
        return
    if code is None:
        last_result = "fail:" + err
        logger.warning(f"[NOTIFY-COPY] 발송 예외 {err}")
    else:
        last_result = "fail:http_" + str(code)
        logger.warning(f"[NOTIFY-COPY] 발송 실패 status={code}")
    if code == 403:
        _fail_streak = 0
        _pause(PAUSE_403_SEC, "투자자가 봇을 막음(403)")
        return
    if code == 429:
        ra = PAUSE_429_DEFAULT_SEC
        try:
            ra = int((resp.json() or {}).get("parameters", {}).get("retry_after") or PAUSE_429_DEFAULT_SEC)
        except Exception:
            ra = PAUSE_429_DEFAULT_SEC
        _fail_streak = 0
        _pause(ra, "보내기 제한(429)")
        return
    _fail_streak += 1
    if _fail_streak >= FAIL_STREAK_LIMIT:
        _fail_streak = 0
        _pause(PAUSE_STREAK_SEC, f"연속 실패 {FAIL_STREAK_LIMIT}번")


def _reset_for_tests() -> None:
    """시험 전용: 쉼·연속 실패·결과를 처음 상태로."""
    global _pause_until, _fail_streak, last_result, _last_full_log
    flush(1.0)
    with _state_lock:
        _pause_until = 0.0
    _fail_streak = 0
    _last_full_log = 0.0
    last_result = "none"
