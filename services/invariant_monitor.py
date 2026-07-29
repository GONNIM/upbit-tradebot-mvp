"""
✅ [Phase 3-A] Invariant Monitor — 실시간 포지션 상태 스냅샷 SQLite 적재.

목적:
- 매 봉 처리 시점의 wallet vs memory 정합성 스냅샷 기록.
- pages/system_health.py 대시보드가 이 데이터를 조회하여 헬스 배지 표시.
- 사건 감지 시간을 (2.5일 최대) → (수 분) 단축.

원칙:
- 매매 로직 절대 불변. 순수 관찰 계층.
- 실패 시 봇 매매 흐름 절대 방해 금지 (try/except 전체 감쌈).
- 스냅샷은 append-only. 조회는 최근 N개만.

스키마:
- invariant_snapshots(
    id, timestamp, user_id, ticker,
    has_position, qty, avg_price, entry_ts, entry_bar,
    wallet_qty, wallet_avg,
    trailing_armed, highest_price,
    violation_code, violation_msg
  )
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from core.position_state import PositionState

logger = logging.getLogger(__name__)


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_ENSURED_USERS: set[str] = set()


# 헬스 판정 임계값
HEALTHY_MAX_VIOLATIONS_1H = 0    # 1시간 내 위반 0건 → 초록
DEGRADED_MAX_VIOLATIONS_1H = 3   # 1시간 내 위반 3건 이하 → 노랑 (그 이상 빨강)


def _ensure_snapshot_schema(user_id: str) -> None:
    """스키마 확보 (idempotent). user별 1회 캐시."""
    if user_id in _SCHEMA_ENSURED_USERS:
        return
    with _SCHEMA_LOCK:
        if user_id in _SCHEMA_ENSURED_USERS:
            return
        try:
            from services.db import get_db, ensure_schema
            ensure_schema(user_id)
            with get_db(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invariant_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
                        user_id TEXT,
                        ticker TEXT,
                        has_position INTEGER,
                        qty REAL,
                        avg_price REAL,
                        entry_ts TEXT,
                        entry_bar INTEGER,
                        wallet_qty REAL,
                        wallet_avg REAL,
                        trailing_armed INTEGER,
                        highest_price REAL,
                        violation_code TEXT,
                        violation_msg TEXT
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_invariant_snapshots_user_ts
                    ON invariant_snapshots(user_id, timestamp)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_invariant_snapshots_violation
                    ON invariant_snapshots(violation_code, timestamp)
                """)
                conn.commit()
            _SCHEMA_ENSURED_USERS.add(user_id)
        except Exception as e:
            logger.warning(f"[INVARIANT_MONITOR] 스키마 확보 실패 (무해): {e}")


def record_snapshot(
    position: "PositionState",
    *,
    user_id: str,
    ticker: str,
    wallet_qty: Optional[float] = None,
    wallet_avg: Optional[float] = None,
    violation_code: Optional[str] = None,
    violation_msg: Optional[str] = None,
) -> None:
    """
    포지션 상태 스냅샷 1건 기록.

    ✅ 원칙:
    - 실패 시 절대 예외 상위로 전파 안 함 (봇 매매 흐름 보호).
    - 매 봉마다 호출되는 hot path — 가벼운 INSERT 만.
    - 클리닝은 별도 유틸 (retention_cleanup) 에서.

    Args:
        position: PositionState 인스턴스
        user_id, ticker: 식별자
        wallet_qty, wallet_avg: 실제 wallet 값 (memory와 대비용)
        violation_code, violation_msg: check_position_invariants 결과 (없으면 None)
    """
    try:
        _ensure_snapshot_schema(user_id)
        from services.db import get_db
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            entry_ts_str = (
                position.entry_ts.isoformat()
                if position.entry_ts is not None else None
            )
            cursor.execute("""
                INSERT INTO invariant_snapshots
                (user_id, ticker, has_position, qty, avg_price, entry_ts, entry_bar,
                 wallet_qty, wallet_avg, trailing_armed, highest_price,
                 violation_code, violation_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, ticker,
                int(bool(position.has_position)),
                float(position.qty) if position.qty is not None else None,
                float(position.avg_price) if position.avg_price is not None else None,
                entry_ts_str,
                position.entry_bar,
                wallet_qty,
                wallet_avg,
                int(bool(getattr(position, "trailing_armed", False))),
                (
                    float(position.highest_price)
                    if getattr(position, "highest_price", None) is not None else None
                ),
                violation_code,
                violation_msg,
            ))
            conn.commit()
    except Exception as e:
        # 절대 예외 상위로 전파 금지 (Phase 3 원칙 — 관찰 계층은 매매 흐름 방해 X)
        logger.warning(f"[INVARIANT_MONITOR] snapshot 기록 실패 (무해): {e}")


def get_latest_snapshot(user_id: str, ticker: str) -> Optional[dict]:
    """가장 최근 스냅샷 1건 조회. system_health 페이지용."""
    try:
        _ensure_snapshot_schema(user_id)
        from services.db import get_db
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, has_position, qty, avg_price, entry_ts, entry_bar,
                       wallet_qty, wallet_avg, trailing_armed, highest_price,
                       violation_code, violation_msg
                FROM invariant_snapshots
                WHERE user_id=? AND ticker=?
                ORDER BY id DESC LIMIT 1
            """, (user_id, ticker))
            row = cursor.fetchone()
            if not row:
                return None
            cols = ["timestamp", "has_position", "qty", "avg_price", "entry_ts", "entry_bar",
                    "wallet_qty", "wallet_avg", "trailing_armed", "highest_price",
                    "violation_code", "violation_msg"]
            return dict(zip(cols, row))
    except Exception as e:
        logger.warning(f"[INVARIANT_MONITOR] 조회 실패: {e}")
        return None


def get_recent_violations(user_id: str, ticker: str, hours: int = 24, limit: int = 50) -> list[dict]:
    """
    최근 N시간 내 violation 스냅샷 조회 (violation_code IS NOT NULL).
    system_health 페이지 CRITICAL 이력 표시용.
    """
    try:
        _ensure_snapshot_schema(user_id)
        from services.db import get_db
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, violation_code, violation_msg,
                       has_position, qty, avg_price, entry_ts, wallet_qty, wallet_avg
                FROM invariant_snapshots
                WHERE user_id=? AND ticker=? AND violation_code IS NOT NULL
                  AND datetime(timestamp) >= datetime('now', 'localtime', ?)
                ORDER BY id DESC LIMIT ?
            """, (user_id, ticker, f"-{hours} hours", limit))
            rows = cursor.fetchall()
            cols = ["timestamp", "violation_code", "violation_msg",
                    "has_position", "qty", "avg_price", "entry_ts",
                    "wallet_qty", "wallet_avg"]
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.warning(f"[INVARIANT_MONITOR] violations 조회 실패: {e}")
        return []


def get_health_status(user_id: str, ticker: str) -> dict:
    """
    시스템 헬스 판정 (초록/노랑/빨강).
    dashboard 상단 배지 + system_health 페이지 상단 헤더용.

    Returns:
        {
            "status": "healthy" | "degraded" | "critical",
            "color": "green" | "yellow" | "red",
            "reason": "설명 문자열",
            "violation_count_1h": int,
            "latest_snapshot_ts": str or None,
        }
    """
    try:
        _ensure_snapshot_schema(user_id)
        from services.db import get_db
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            # 최근 1시간 위반 카운트
            cursor.execute("""
                SELECT COUNT(*) FROM invariant_snapshots
                WHERE user_id=? AND ticker=? AND violation_code IS NOT NULL
                  AND datetime(timestamp) >= datetime('now', 'localtime', '-1 hour')
            """, (user_id, ticker))
            violation_cnt = cursor.fetchone()[0] or 0

            # 최근 스냅샷 시각
            cursor.execute("""
                SELECT timestamp FROM invariant_snapshots
                WHERE user_id=? AND ticker=?
                ORDER BY id DESC LIMIT 1
            """, (user_id, ticker))
            row = cursor.fetchone()
            latest_ts = row[0] if row else None

        if violation_cnt <= HEALTHY_MAX_VIOLATIONS_1H:
            return {
                "status": "healthy",
                "color": "green",
                "reason": "invariant 위반 없음 (최근 1시간)",
                "violation_count_1h": violation_cnt,
                "latest_snapshot_ts": latest_ts,
            }
        elif violation_cnt <= DEGRADED_MAX_VIOLATIONS_1H:
            return {
                "status": "degraded",
                "color": "yellow",
                "reason": f"invariant 위반 {violation_cnt}건 (최근 1시간)",
                "violation_count_1h": violation_cnt,
                "latest_snapshot_ts": latest_ts,
            }
        else:
            return {
                "status": "critical",
                "color": "red",
                "reason": f"⚠️ invariant 위반 {violation_cnt}건 다발 (최근 1시간)",
                "violation_count_1h": violation_cnt,
                "latest_snapshot_ts": latest_ts,
            }
    except Exception as e:
        logger.warning(f"[INVARIANT_MONITOR] health 판정 실패: {e}")
        return {
            "status": "unknown",
            "color": "gray",
            "reason": f"헬스 조회 실패 ({e})",
            "violation_count_1h": -1,
            "latest_snapshot_ts": None,
        }


def cleanup_old_snapshots(user_id: str, retention_days: int = 7) -> int:
    """
    N일 이전 스냅샷 정리 (수동 실행 or 주기 실행용).

    Returns:
        삭제된 행 수. 실패 시 -1.
    """
    try:
        _ensure_snapshot_schema(user_id)
        from services.db import get_db
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM invariant_snapshots
                WHERE user_id=? AND datetime(timestamp) < datetime('now', 'localtime', ?)
            """, (user_id, f"-{retention_days} days"))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
    except Exception as e:
        logger.warning(f"[INVARIANT_MONITOR] cleanup 실패: {e}")
        return -1
