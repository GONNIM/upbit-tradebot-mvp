"""엔진 동작 3단계 판정과 모드 비교 (표준 라이브러리만 사용).

판정 규칙 (사용자 결정 1022-06 안 다):
- 비교는 「초과」. delay_sec = bar_sec * DELAY_FACTOR.
- ago_sec 은 항상 판단 기록(last_eval_ts) 기준. 기록이 없으면 None.
- 계좌 갱신 시각(accounts_ts)은 LIVE 에서만 보조로 쓰고, ok 까지 올리지 않는다.
- 판단 불가 기준 = max(UNKNOWN_SEC 1800, 봉 초 × DELAY_FACTOR × UNKNOWN_FACTOR) — 사용자 결정 1023-01 결정 3 나.
"""
import re
from datetime import datetime
from typing import Optional

DELAY_FACTOR = 3
UNKNOWN_SEC = 1800  # 하한
UNKNOWN_FACTOR = 2

_MINUTE_RE = re.compile(r"minute(\d+)")
_FIXED = {"day": 86400, "week": 604800}


def interval_sec(interval: str) -> int:
    """'minute3' -> 180, 'day' -> 86400. 알 수 없는 값은 ValueError."""
    if isinstance(interval, str):
        if interval in _FIXED:
            return _FIXED[interval]
        m = _MINUTE_RE.fullmatch(interval)
        if m and int(m.group(1)) > 0:
            return int(m.group(1)) * 60
    raise ValueError("invalid interval")


def unknown_sec(bar_sec: int) -> int:
    return max(UNKNOWN_SEC, bar_sec * DELAY_FACTOR * UNKNOWN_FACTOR)


def engine_state(last_eval_ts: Optional[datetime], accounts_ts: Optional[datetime],
                 mode: str, bar_sec: int, now: datetime) -> dict:
    delay_sec = bar_sec * DELAY_FACTOR
    live = (mode == "LIVE")
    accounts_recent = (live and accounts_ts is not None
                       and (now - accounts_ts).total_seconds() <= delay_sec)

    if last_eval_ts is None:
        if accounts_recent:
            return {"level": "delay", "ago_sec": None, "basis": "accounts"}
        return {"level": "unknown", "ago_sec": None, "basis": "none"}

    raw = max(0.0, (now - last_eval_ts).total_seconds())
    ago = int(raw)
    if raw <= delay_sec:
        return {"level": "ok", "ago_sec": ago, "basis": "eval"}
    if raw <= unknown_sec(bar_sec):
        return {"level": "delay", "ago_sec": ago, "basis": "eval"}
    if accounts_recent:
        return {"level": "delay", "ago_sec": ago, "basis": "accounts"}
    return {"level": "unknown", "ago_sec": ago, "basis": "eval"}


def mode_state(engine_mode: Optional[str], entry_mode: str) -> dict:
    if not engine_mode:
        return {"mode_engine": None, "mode_entry": entry_mode,
                "mode_mismatch": False}
    return {"mode_engine": engine_mode, "mode_entry": entry_mode,
            "mode_mismatch": engine_mode != entry_mode}


ENGINE_ALIVE_FRESH_SEC = 15  # .engine_alive.json 의 at 이 이 초 안이어야 Running (스펙: 15초)


def engine_alive_running(data, user_id: str, now: datetime) -> bool:
    """기본 기능 블록의 「트레이딩 엔진 상태」. 엔진 프로세스가 5초마다 쓰는 스레드 생존값 기준.

    Running = at 이 15초 이내 그리고 running[user_id] 가 True. 그 밖(파일 없음·깨짐·오래됨·키 없음)은 Stopped.
    """
    if not isinstance(data, dict):
        return False
    running = data.get("running")
    at = data.get("at")
    if not isinstance(running, dict) or not isinstance(at, str):
        return False
    try:
        t = datetime.fromisoformat(at.strip())
    except ValueError:
        return False
    if t.tzinfo is None:
        return False
    delta = (now - t).total_seconds()
    if delta > ENGINE_ALIVE_FRESH_SEC or delta < -ENGINE_ALIVE_FRESH_SEC:
        return False
    return running.get(user_id) is True
