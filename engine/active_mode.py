"""
1109 눌림목 실계좌 열기 — 작업 A: 활성 전략 옆 「모드 표식」 파일.

`<user>_active_strategy_mode.txt` 한 줄: `LIVE`(실계좌에서 켠 눌림목) 또는 `TEST`(모의).
  - 파일 없음  = TEST (지금까지 서버의 눌림목 활성은 모두 모의에서 만들어졌다. 모의 사용자 기동을 막지 않는다)
  - `LIVE`     = 실계좌
  - 그 밖(빈 파일·이상한 내용·읽기 실패) = UNKNOWN → 실계좌 기동은 거부 + CRITICAL
표식은 활성 전략이 PULLBACK 일 때만 읽는다(활성이 EMA·MACD 면 어떤 판정에도 쓰이지 않는다).
쓰기는 새 전환(EMA·MACD → PULLBACK)에서만, 활성 파일을 쓰기 전에. 원자 쓰기(임시 파일 → 교체)라 쓰다 만 빈 파일이 남지 않는다.
"""
from __future__ import annotations

import logging
import os
from typing import Tuple

logger = logging.getLogger(__name__)

_TAG = "[MODE-MARKER]"
VALID = ("TEST", "LIVE")

PULLBACK_MODE_REFUSE_MSG = ("이 계정의 새 전략은 다른 모드(모의/실계좌)에서 켜졌거나 모드 표식을 읽지 못해 "
                            "이 모드에서는 시작하지 않습니다")


def marker_path(user_id: str) -> str:
    return f"{user_id}_active_strategy_mode.txt"


def read_marker(user_id: str) -> str:
    """'TEST'(파일 없음) | 'LIVE' | 'UNKNOWN'(읽기 실패·이상한 내용)."""
    path = marker_path(user_id)
    if not os.path.exists(path):
        return "TEST"
    try:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    except Exception as e:  # noqa: BLE001
        logger.error(f"{_TAG} 읽기 실패 | user={user_id} | {type(e).__name__}")
        return "UNKNOWN"
    value = body.strip()
    if value in VALID and body in (value, value + "\n"):
        return value
    logger.error(f"{_TAG} 표식 내용 이상 | user={user_id} len={len(body)}")
    return "UNKNOWN"


def write_marker(user_id: str, mode: str) -> None:
    """원자 쓰기 + 다시 읽어 확인. 실패하면 예외(호출자가 활성 파일을 바꾸지 않는다)."""
    if mode not in VALID:
        raise ValueError(mode)
    from engine.pullback_params import _atomic_write
    _atomic_write(marker_path(user_id), (mode + "\n").encode("utf-8"))
    if read_marker(user_id) != mode:
        raise OSError("marker readback mismatch")


def _active_is_pullback(user_id: str) -> bool:
    from engine.params import load_active_strategy
    return load_active_strategy(user_id, include_engine_only=True) == "PULLBACK"


def pullback_boot_allowed(user_id: str, boot_mode: str, *, engine_is_pullback: bool = False) -> Tuple[bool, str]:
    """활성 전략이 PULLBACK 일 때 부팅 모드(TEST|LIVE)가 표식과 같고 UNKNOWN 이 아니면 (True, "").
    활성이 PULLBACK 이 아니면 표식을 보지 않고 (True, "").
    engine_is_pullback=True: 이미 눌림목 엔진을 띄우는 자리(엔진 관리자·매매 루프) — 활성 파일과 상관없이 표식을 본다."""
    if not engine_is_pullback and not _active_is_pullback(user_id):
        return True, ""
    marker = read_marker(user_id)
    if marker == "UNKNOWN":
        return False, "marker_unknown"
    if marker != boot_mode:
        return False, "marker_mismatch"
    return True, ""


def marker_mismatch_for_request(user_id: str, req_mode: str) -> bool:
    """전환·복귀·적용 요청용: 활성이 PULLBACK 이고 요청 모드 ≠ 표식(또는 UNKNOWN)이면 True."""
    ok, _why = pullback_boot_allowed(user_id, req_mode)
    return not ok
