"""엔진 동작 3단계 판정과 모드 비교 (표준 라이브러리만 사용).

판정 규칙 (사용자 결정 1022-06 안 다):
- 비교는 「초과」. delay_sec = bar_sec * DELAY_FACTOR.
- ago_sec 은 항상 판단 기록(last_eval_ts) 기준. 기록이 없으면 None.
- 계좌 갱신 시각(accounts_ts)은 LIVE 에서만 보조로 쓰고, ok 까지 올리지 않는다.
"""
import re
from datetime import datetime
from typing import Optional

DELAY_FACTOR = 3
UNKNOWN_SEC = 1800

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
    if raw <= UNKNOWN_SEC:
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
