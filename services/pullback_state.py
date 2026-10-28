"""
2차 T6: 새 전략(PULLBACK) 분할 상태 저장소 — 테이블 pullback_state (services/init_db.ensure_pullback_tables).

- 사용자·모드(TEST/LIVE)마다 1행. 쓰기는 save() 한 곳(UPSERT 1문 = 한 트랜잭션), 청산 초기화는 reset_after_exit().
- 시각 칸은 늘 KST ISO(+09:00)로 쓴다. 시간대 없는 시각은 받지 않는다(ValueError → 저장 안 함).
  이유: 전략의 _to_ts 는 시간대 없는 값을 KST 로, _kst_iso 는 UTC 로 본다 — 오프셋 없이 쓰면 9시간 어긋날 수 있다(Issue #2).
- 테이블을 만들지 않는다(마이그레이션 함수만 만든다). DB 파일이 없으면 만들지 않는다(sqlite connect 가 빈 파일을 만드는 것 방지).
  테이블이 없는 기존 DB 에서는 load → None, save·reset_after_exit → False (예외 없음).
"""
from __future__ import annotations

import logging
import math
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TABLE = "pullback_state"
MODES = ("TEST", "LIVE")
_KST = ZoneInfo("Asia/Seoul")
_TS_COLS = ("first_entry_ts", "buy_fail_bar_ts", "last_bar_ts")
_COLS = (
    "user_id", "mode", "ticker", "interval", "entry_count", "pullback_count", "first_entry_ts",
    "first_entry_reason", "armed", "prev_golden", "trade_origin", "pending_fill", "fill_n", "inv_sum",
    "sizing_base_krw", "realized_pnl_krw", "qty", "cost_krw", "avg_price", "desync", "buy_fail_bar_ts",
    "params_sha256", "last_bar_ts", "updated_at",
)
_INT_COLS = ("entry_count", "pullback_count", "fill_n")
_BOOL_COLS = ("armed", "pending_fill", "desync")
_REAL_COLS = ("inv_sum", "realized_pnl_krw", "qty", "cost_krw")
_OPT_REAL_COLS = ("sizing_base_krw", "avg_price")


def now_kst_iso() -> str:
    return datetime.now(_KST).isoformat()


def to_kst_iso(v) -> Optional[str]:
    """시각 → KST ISO(+09:00). None → None. 시간대 없는 값(문자열 포함)은 ValueError."""
    if v is None:
        return None
    if isinstance(v, str):
        if not v:
            return None
        v = datetime.fromisoformat(v)
    if hasattr(v, "to_pydatetime"):  # pandas.Timestamp
        v = v.to_pydatetime()
    if not isinstance(v, datetime):
        raise ValueError(f"시각 형식 아님: {type(v).__name__}")
    if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
        raise ValueError(f"시간대 없는 시각은 저장하지 않는다: {v!r}")
    return v.astimezone(_KST).isoformat()


def _db_path(user_id: str) -> str:
    from services import db as _db  # 시험이 services.db.get_db_path 를 바꿀 수 있게 호출 때 찾는다
    return _db.get_db_path(user_id)


def _connect(user_id: str) -> Optional[sqlite3.Connection]:
    path = _db_path(user_id)
    if not os.path.exists(path):
        logger.error(f"[PULLBACK-STATE] DB 파일 없음 → 읽기·쓰기 안 함 | user={user_id}")
        return None
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=3000;")
    return conn


def _table_exists(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None


def _check_mode(mode: str) -> str:
    m = str(mode).upper()
    if m not in MODES:
        raise ValueError(f"mode 는 TEST/LIVE: {mode!r}")
    return m


def _num(v, default=0.0) -> float:
    if v is None:
        return default
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"유한한 수 아님: {v!r}")
    return f


def _opt_num(v) -> Optional[float]:
    return None if v is None else _num(v)


def _row_values(user_id: str, mode: str, state: dict) -> dict:
    out: dict[str, Any] = {"user_id": user_id, "mode": mode}
    out["ticker"] = str(state["ticker"])
    out["interval"] = str(state["interval"])
    for c in _INT_COLS:
        out[c] = int(state.get(c) or 0)
    for c in _BOOL_COLS:
        out[c] = 1 if state.get(c) else 0
    for c in _REAL_COLS:
        out[c] = _num(state.get(c))
    for c in _OPT_REAL_COLS:
        out[c] = _opt_num(state.get(c))
    pg = state.get("prev_golden")
    out["prev_golden"] = None if pg is None else (1 if pg else 0)
    for c in ("first_entry_reason", "trade_origin", "params_sha256"):
        v = state.get(c)
        out[c] = None if v is None else str(v)
    for c in _TS_COLS:
        out[c] = to_kst_iso(state.get(c))
    out["updated_at"] = now_kst_iso()
    return out


class PullbackStateReadError(Exception):
    """수정 1회차: 행이 있을 수 있는데 읽지 못함(잠금·I/O·칸 오류). 「행 없음」(None)과 구분한다 —
    호출부가 None 으로 보고 저장하면 기존 행을 덮어쓰기 때문."""


def load(user_id: str, mode: str) -> Optional[dict]:
    """(user_id, mode) 행 dict. 행·테이블·DB 파일이 없으면 None(덮어쓸 행이 없음).
    읽기 오류(연결·SELECT 실패)는 PullbackStateReadError 를 던진다."""
    m = _check_mode(mode)
    try:
        conn = _connect(user_id)
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 읽기 연결 실패 | user={user_id} mode={m} | {type(e).__name__}: {e}")
        raise PullbackStateReadError(f"{type(e).__name__}: {e}") from e
    if conn is None:
        return None
    try:
        if not _table_exists(conn):
            logger.warning(f"[PULLBACK-STATE] 테이블 없음(마이그레이션 확인) → 복원 안 함 | user={user_id}")
            return None
        cur = conn.execute(f"SELECT {', '.join(_COLS)} FROM {TABLE} WHERE user_id=? AND mode=?", (user_id, m))
        row = cur.fetchone()
        return dict(zip(_COLS, row)) if row else None
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 읽기 실패 | user={user_id} mode={m} | {type(e).__name__}: {e}")
        raise PullbackStateReadError(f"{type(e).__name__}: {e}") from e
    finally:
        conn.close()


def save(user_id: str, mode: str, state: dict) -> bool:
    """state(칸 이름 dict)를 한 문장 UPSERT 로 저장. 성공 True. 시각 오프셋 없음·테이블 없음·DB 없음은 False(로그)."""
    try:
        m = _check_mode(mode)
        vals = _row_values(user_id, m, state)
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 저장 거부(값 오류) | user={user_id} mode={mode} | {type(e).__name__}: {e}")
        return False
    conn = _connect(user_id)
    if conn is None:
        return False
    try:
        if not _table_exists(conn):
            logger.error(f"[PULLBACK-STATE] 테이블 없음(마이그레이션 확인) → 저장 안 함 | user={user_id}")
            return False
        cols = list(_COLS)
        upd = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("user_id", "mode"))
        conn.execute(
            f"INSERT INTO {TABLE} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT(user_id, mode) DO UPDATE SET {upd}",
            [vals[c] for c in cols],
        )
        return True
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 저장 실패 | user={user_id} mode={m} | {type(e).__name__}: {e}")
        return False
    finally:
        conn.close()


def reset_after_exit(user_id: str, mode: str, realized_pnl: float = 0.0) -> bool:
    """청산 뒤(pullback spec 3절 5): 회차·눌림목 회차·첫 진입·armed·체결 수량·원가·평단·배분 기준·어긋남을 초기화하고
    realized_pnl_krw 에 이번 실현 손익을 더한다. prev_golden·last_bar_ts 는 판정 상태라 그대로 둔다. 행이 없으면 False."""
    try:
        m = _check_mode(mode)
        pnl = _num(realized_pnl)
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 초기화 거부(값 오류) | user={user_id} | {e}")
        return False
    conn = _connect(user_id)
    if conn is None:
        return False
    try:
        if not _table_exists(conn):
            logger.error(f"[PULLBACK-STATE] 테이블 없음(마이그레이션 확인) → 초기화 안 함 | user={user_id}")
            return False
        cur = conn.execute(
            f"UPDATE {TABLE} SET entry_count=0, pullback_count=0, first_entry_ts=NULL, first_entry_reason=NULL, "
            f"armed=0, trade_origin=NULL, pending_fill=0, fill_n=0, inv_sum=0, sizing_base_krw=NULL, "
            f"qty=0, cost_krw=0, avg_price=NULL, desync=0, realized_pnl_krw=realized_pnl_krw + ?, updated_at=? "
            f"WHERE user_id=? AND mode=?",
            (pnl, now_kst_iso(), user_id, m),
        )
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"[PULLBACK-STATE] 초기화 실패 | user={user_id} mode={m} | {type(e).__name__}: {e}")
        return False
    finally:
        conn.close()
