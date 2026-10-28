"""
2차 T7 (2026-10-28): 거래 행 전략 칸(strategy_type) 해석 — 읽기 전용 도우미.

분류 규칙 (plan-phase2.md T7 「분류 규칙」, NULL 해석은 마이그레이션 전 행으로만):
  - 'EMA'·'MACD'                                   → 그 전략 (구버전 이력·손익에 보임)
  - 'PULLBACK'                                     → 새 전략 (구버전 이력·손익에서 뺌)
  - NULL, id ≤ 표식(legacy_max_id)                 → 옛 EMA/MACD (보임)
  - NULL, 되돌림 구간 revert_from < id ≤ revert_to → 옛 EMA/MACD (보임)
  - NULL, 그 밖                                    → 분류 불명 (뺌, 기동 때 운영 로그·텔레그램 — 결정 1028-06)
칸이 없는 DB(마이그레이션 전·실패)는 모든 행이 옛 행이다 — 조회는 지금과 같다.
이 모듈은 DB 에 쓰지 않는다. 쓰기는 services/init_db.ensure_trade_strategy_columns 와 scripts/v2/mark_revert.py 뿐.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.init_db import STRATEGY_COLUMN, strategy_mark_name, _table_exists, _column_exists

logger = logging.getLogger(__name__)

OLD_STRATEGIES = ("EMA", "MACD")
_OLD_IN_SQL = ", ".join(f"'{s}'" for s in OLD_STRATEGIES)  # 상수에서 만든 SQL IN 목록 (사용자 입력 아님)

_MARK_MISSING_WARNED: set = set()  # (DB 파일, 표) — 표식 없음 WARNING 1회

LEGACY = "LEGACY"     # NULL 이지만 옛 EMA/MACD 행
UNKNOWN = "UNKNOWN"   # 분류 불명


def normalize(strategy_type) -> Optional[str]:
    """services.db 의 기록 쪽 정리(_norm_strategy_type)와 같은 함수."""
    from services.db import _norm_strategy_type
    return _norm_strategy_type(strategy_type)


def _db_file(conn) -> str:
    try:
        for row in conn.execute("PRAGMA database_list").fetchall():
            if row[1] == "main":
                return row[2] or ""
    except Exception:
        pass
    return ""


def read_bounds(conn, table: str) -> Optional[dict]:
    """
    표의 해석 기준. None = strategy_type 칸 없음(모든 행이 옛 행).
    {"mark": int, "rv_from": int|None, "rv_to": int|None} — 구간은 revert_from·revert_to 가 둘 다 있을 때만.
    표식이 없으면(마이그레이션이 아직 못 고침) D3 정의로 읽기만 해서 계산한다.
    """
    if not _table_exists(conn, table) or not _column_exists(conn, table, STRATEGY_COLUMN):
        return None
    marks: dict = {}
    if _table_exists(conn, "schema_marks"):
        prefix = f"{table}.{STRATEGY_COLUMN}."
        for name, value in conn.execute(
            "SELECT name, value FROM schema_marks WHERE substr(name, 1, ?) = ?", (len(prefix), prefix)
        ).fetchall():
            marks[name] = value
    mark = marks.get(strategy_mark_name(table, "legacy_max_id"))
    if mark is None:
        row = conn.execute(
            f"SELECT COALESCE((SELECT MIN(id) FROM {table} WHERE {STRATEGY_COLUMN} IS NOT NULL) - 1, "
            f"(SELECT MAX(id) FROM {table}), 0)"
        ).fetchone()
        mark = row[0] if row else 0
        key = (_db_file(conn), table)
        if key not in _MARK_MISSING_WARNED:
            _MARK_MISSING_WARNED.add(key)
            logger.warning(f"[STRATEGY-COL] {table} 표식 없음 — 읽기 계산값 {mark} 사용 (마이그레이션 확인)")
    rv_from = marks.get(strategy_mark_name(table, "revert_from"))
    rv_to = marks.get(strategy_mark_name(table, "revert_to"))
    if rv_from is None or rv_to is None:
        rv_from = rv_to = None
    return {"mark": int(mark), "rv_from": rv_from, "rv_to": rv_to}


def old_history_sql(bounds: Optional[dict]) -> tuple[str, list]:
    """구버전 이력·손익 WHERE 에 덧붙일 조건(' AND (...)')과 인자. 칸 없는 DB 는 ('', [])."""
    if bounds is None:
        return "", []
    frag = (
        f" AND (strategy_type IN ({_OLD_IN_SQL}) OR (strategy_type IS NULL AND "
        "(id <= ? OR (? IS NOT NULL AND id > ? AND id <= ?))))"
    )
    return frag, [bounds["mark"], bounds["rv_from"], bounds["rv_from"], bounds["rv_to"]]


def classify(strategy_type, row_id: int, bounds: Optional[dict]) -> str:
    """한 행의 분류: 'EMA'|'MACD'|'PULLBACK'|그 밖 대문자 값|LEGACY|UNKNOWN."""
    st = normalize(strategy_type)
    if st is not None:
        return st
    if bounds is None or row_id <= bounds["mark"]:
        return LEGACY
    if bounds["rv_from"] is not None and bounds["rv_from"] < row_id <= bounds["rv_to"]:
        return LEGACY
    return UNKNOWN


def count_unknown_rows(user_id: str, table: str = "audit_trades") -> int:
    """분류 불명(NULL·표식 뒤·되돌림 구간 밖) 행 수. 칸 없음·오류 = 0."""
    try:
        from services.db import get_db
        with get_db(user_id) as conn:
            b = read_bounds(conn, table)
            if b is None:
                return 0
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE strategy_type IS NULL AND id > ? "
                f"AND NOT (? IS NOT NULL AND id > ? AND id <= ?)",
                (b["mark"], b["rv_from"], b["rv_from"], b["rv_to"]),
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception as e:
        logger.warning(f"[STRATEGY-COL] 분류 불명 행 수 조회 실패: {e}")
        return 0


def report_unknown_rows(user_id: str) -> tuple[int, int]:
    """
    분류 불명 행 수를 세어 운영자에게만 알린다(사용자 결정 1028-06 — 화면 경고 대신 운영 로그·텔레그램).
    엔진 기동 마이그레이션(engine/boot_resume.py) 뒤 사용자별 1회 부른다.
    n>0 이면 WARNING `[STRATEGY-UNKNOWN] user=… audit_trades=n orders=m` + 텔레그램 WARNING 1회(dedupe 24시간).
    예외는 올리지 않는다. 반환 (audit_trades 수, orders 수).
    """
    n = count_unknown_rows(user_id, "audit_trades")
    m = count_unknown_rows(user_id, "orders")
    if n or m:
        logger.warning(f"[STRATEGY-UNKNOWN] user={user_id} audit_trades={n} orders={m}")
        try:
            from services.notifier import send, LEVEL_WARNING
            # 경고 채널은 투자자에게도 갈 수 있다(수정 3회차): 쉬운 말만. 표 이름·로그 태그·사용자 ID 는 위 WARNING 로그에만.
            send(
                LEVEL_WARNING,
                "거래 기록 전략 구분 확인 필요",
                (f"거래 기록 {n + m}건의 전략 구분이 비어 옛 화면 이력·손익에서 빠졌습니다.\n"
                 f"운영자가 확인합니다. 투자자님이 따로 하실 일은 없습니다."),
                dedupe_key=f"strategy_unknown:{user_id}",
                dedupe_ttl=86400,
            )
        except Exception as e:
            logger.warning(f"[STRATEGY-UNKNOWN] 알림 실패: {e}")
    return n, m


def active_strategy(user_id: str) -> Optional[str]:
    """활성 전략 파일(엔진 전용 PULLBACK 포함). 없음·오류 = None."""
    try:
        from engine.params import load_active_strategy
        return normalize(load_active_strategy(user_id, include_engine_only=True))
    except Exception as e:
        logger.warning(f"[STRATEGY-COL] 활성 전략 읽기 실패: {e}")
        return None


def force_trade_strategy_type(user_id: str, fallback) -> Optional[str]:
    """
    구버전 강제 매수·매도 trader 의 전략(X5): PULLBACK 운용 중(활성 전략 파일 PULLBACK)이면 PULLBACK,
    아니면 대시보드가 쓰는 전략(fallback = params_obj.strategy_type).
    """
    if active_strategy(user_id) == "PULLBACK":
        return "PULLBACK"
    return normalize(fallback)
