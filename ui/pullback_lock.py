"""
2차 T15 (2026-10-29): 구버전 화면 잠금·배지 판정 — 읽기 전용 도우미.

결정 D7·D10, 사용자 결정 1029-10 (C2 나·C3 ①+②), PO 결정 C1-a·C1-b·C4 (docs/fable/2026-10-29-phase2-t15-decision-1.md).

lock_state(user_id) -> dict
  locked : 구버전 설정 저장·전략 변경·수동 엔진 시작을 잠그는가
  why    : "pullback"(활성 파일 PULLBACK) | "reserved"(전환·복귀 예약 있음, 모든 모드) | "unknown"(예약 읽기 실패) | None
  active : 활성 전략 파일 값(엔진 전용 PULLBACK 포함) 또는 None
  pullback : 활성 파일이 PULLBACK 인가 (PULLBACK 표시 경로는 이때만 — 결정 1029-03-3)
  reservation : 가장 최근 예약 1행(모든 모드) 또는 None
  holding : 새 전략 TEST 행이 보유 중(qty>0 · 회차>0 · 체결 대기). 읽기 실패도 보유로 본다(fail closed)
  ticker · round · max_round · strategy_label : 「상태 (보기만)」 표시값 (PULLBACK 일 때)

규칙:
  - 예약은 모드를 가리지 않고 본다(C3 ①: 활성 파일·EMA 설정 파일이 모드 공용 — D4).
  - strategy_switch 표가 없으면 「예약 없음」, 그 밖의 읽기 예외는 「잠김(unknown)」(C3 ②, fail closed).
    화면 경로에서는 표 없음 알림을 보내지 않는다(Fable 권고 7 — 운영자 알림은 T12 엔진 경로가 보낸다).
  - DB 파일이 없으면(처음 들어온 사용자) 예약·보유 없음.
  - 이 모듈은 DB·파일에 쓰지 않는다. 단, keep_capital_update_display_name 은 D10 의 「display_name 만 갱신」 쓰기다.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PULLBACK = "PULLBACK"
PULLBACK_LABEL = "눌림목 분할매수"   # engine/strategy_switch.PULLBACK_LABEL 과 같은 글자(시험이 비교)
SWITCH_TABLE = "strategy_switch"
STATE_TABLE = "pullback_state"

BADGE_PULLBACK = "새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다"
BADGE_RESERVED = "전환 예약 중 — 설정은 신버전에서 관리합니다"
BADGE_UNKNOWN = "전환 예약 상태를 확인하지 못해 설정 저장을 잠시 막습니다"
NEW_STRATEGY_TABLE_TEXT = "새 전략 조건은 신버전에서 확인합니다"
FORCE_BUY_PULLBACK_TEXT = "구버전 강제 매수는 새 전략 회차 밖 매수입니다(추가 분할매수가 멈춥니다)."
FORCE_BUY_RESERVED_TEXT = "전환 예약은 그대로이며 이번 매수분을 지금 전략이 판 뒤 바뀝니다."
LOCKED_SUFFIX = " (잠김)"
# 사용자 결정 1029-11 A (나): 실계좌 화면 + 활성 새 전략 → 이 안내 뒤 멈춤
LIVE_PULLBACK_STOP_TEXT = ("새 전략은 모의 투자에서만 씁니다. 모의 투자로 들어오시거나 신버전에서 전략을 되돌려 주세요. "
                           "모의 엔진이 실행 중이면 모의 투자로 들어오세요.")


class ReservationReadError(Exception):
    """예약 표를 읽지 못함(표 없음과 구분)."""


def _db_path(user_id: str) -> str:
    from services import db as _db  # 시험이 services.db.get_db_path 를 바꿀 수 있게 호출 때 찾는다
    return _db.get_db_path(user_id)


def _connect_ro(user_id: str) -> Optional[sqlite3.Connection]:
    """읽기 연결(PRAGMA query_only). DB 파일이 없으면 None — 만들지 않는다."""
    path = _db_path(user_id)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path, timeout=3)
    try:
        conn.execute("PRAGMA busy_timeout=3000;")
        conn.execute("PRAGMA query_only=ON;")
    except Exception:
        conn.close()  # verifier 지적 10: PRAGMA 실패 때 연결을 남기지 않는다
        raise
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def reservation_any_mode(user_id: str) -> Optional[Dict[str, Any]]:
    """모든 모드의 예약(kind SWITCH/REVERT, state RESERVED) 가장 최근 1행 또는 None.
    DB 파일·표가 없으면 None. 그 밖의 읽기 실패는 ReservationReadError."""
    try:
        conn = _connect_ro(user_id)
    except Exception as e:  # noqa: BLE001
        raise ReservationReadError(f"{type(e).__name__}") from e
    if conn is None:
        return None
    try:
        if not _table_exists(conn, SWITCH_TABLE):
            return None
        r = conn.execute(
            f"SELECT id, mode, kind, from_strategy, to_strategy FROM {SWITCH_TABLE} WHERE user_id=? "
            f"AND kind IN ('SWITCH','REVERT') AND state='RESERVED' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        return dict(r) if r is not None else None
    except Exception as e:  # noqa: BLE001
        raise ReservationReadError(f"{type(e).__name__}") from e
    finally:
        conn.close()


def pullback_test_row(user_id: str) -> Optional[Dict[str, Any]]:
    """새 전략 TEST 행(entry_count·qty·pending_fill·ticker) 또는 None. 읽기 실패는 예외 그대로."""
    conn = _connect_ro(user_id)
    if conn is None:
        return None
    try:
        if not _table_exists(conn, STATE_TABLE):
            return None
        r = conn.execute(
            f"SELECT ticker, entry_count, qty, pending_fill FROM {STATE_TABLE} WHERE user_id=? AND mode='TEST' LIMIT 1",
            (user_id,)).fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def _row_holding(row: Optional[Dict[str, Any]]) -> bool:
    if not row:
        return False
    try:
        return (float(row.get("qty") or 0) > 0 or int(row.get("entry_count") or 0) > 0
                or int(row.get("pending_fill") or 0) != 0)
    except (TypeError, ValueError):
        return True


def active_strategy(user_id: str) -> Optional[str]:
    try:
        from engine.params import load_active_strategy
        v = load_active_strategy(user_id, include_engine_only=True)
        return str(v).upper() if v else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[T15-LOCK] 활성 전략 읽기 실패: {type(e).__name__}")
        return None


def read_applied(user_id: str) -> Optional[dict]:
    """적용본(없거나 깨지면 last_good) 검증본 dict 또는 None. 쓰지 않는다."""
    from engine import pullback_params as pbp
    for path in (pbp.applied_path(user_id), pbp.last_good_path(user_id)):
        try:
            return pbp.validate(pbp.read_json_strict(path))
        except Exception:  # noqa: BLE001
            continue
    return None


def eff_max_splits(cfg: Optional[dict]) -> Optional[int]:
    """engine/pullback_params.to_live_params 의 order_ratio 분모와 같은 값(max(1, maxSplits))."""
    if not cfg:
        return None
    try:
        return max(1, int(cfg["maxSplits"]))
    except (KeyError, TypeError, ValueError):
        return None


def lock_state(user_id: str) -> Dict[str, Any]:
    active = active_strategy(user_id)
    is_pb = active == PULLBACK
    out: Dict[str, Any] = {"locked": False, "why": None, "active": active, "pullback": is_pb,
                           "reservation": None, "reservation_error": False, "holding": False,
                           "holding_error": False, "ticker": None, "round": None, "max_round": None,
                           "strategy_label": PULLBACK_LABEL if is_pb else (active or None)}
    try:
        out["reservation"] = reservation_any_mode(user_id)
    except ReservationReadError as e:
        out["reservation_error"] = True
        logger.warning(f"[T15-LOCK] 예약 읽기 실패 → 잠금(fail closed) | user={user_id} | {e}")
    row = None
    try:
        row = pullback_test_row(user_id)
        out["holding"] = _row_holding(row)
    except Exception as e:  # noqa: BLE001
        out["holding"] = True
        out["holding_error"] = True
        logger.warning(f"[T15-LOCK] 새 전략 상태 읽기 실패 → 보유로 봄 | user={user_id} | {type(e).__name__}")
    if is_pb:
        out["why"] = "pullback"
        cfg = read_applied(user_id)
        out["ticker"] = (cfg or {}).get("ticker") or (row or {}).get("ticker")
        out["max_round"] = eff_max_splits(cfg)
        try:
            out["round"] = int((row or {}).get("entry_count") or 0)
        except (TypeError, ValueError):
            out["round"] = None
    elif out["reservation"] is not None:
        out["why"] = "reserved"
    elif out["reservation_error"]:
        out["why"] = "unknown"
    out["locked"] = out["why"] is not None
    return out


def badge_text(state: Dict[str, Any]) -> Optional[str]:
    return {"pullback": BADGE_PULLBACK, "reserved": BADGE_RESERVED, "unknown": BADGE_UNKNOWN}.get(state.get("why"))


def round_text(state: Dict[str, Any]) -> str:
    r, m = state.get("round"), state.get("max_round")
    return f"{r if r is not None else '-'} / {m if m is not None else '-'}회"


def keeps_capital(state: Dict[str, Any]) -> bool:
    """D10·C1-a: 새 전략 보유 중(TEST 행, 읽기 실패 포함)이거나 예약 중(읽기 실패 포함)이면 운용자산·현금을 덮어쓰지 않는다."""
    return bool(state.get("holding") or state.get("reservation") is not None or state.get("reservation_error"))


def keep_capital_update_display_name(username: str, display_name: str) -> bool:
    """D10: virtual_krw 는 두고 display_name 만 갱신. 행이 없으면 False(호출자가 기존 save_user 로)."""
    from services.db import get_db, now_kst
    with get_db(username) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET display_name = ?, updated_at = ? WHERE username = ?",
                    (display_name, now_kst(), username))
        conn.commit()
        return cur.rowcount > 0


def kept_capital(username: str) -> Optional[float]:
    try:
        from services.db import get_initial_krw
        v = get_initial_krw(username)
        return float(v) if v is not None else None
    except Exception:  # noqa: BLE001
        return None
