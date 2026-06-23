"""
설정 정보 History (P1).

사용자가 명시 저장한 시점의 설정 스냅샷을 누적 보관하고,
거래(orders, audit_trades)와 매핑할 active_settings_id 를 제공한다.

상세: docs/plans/settings-history/{plan.md, schema-spec.md, module-contract.md}
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Any

from config import PARAMS_JSON_FILENAME, CONDITIONS_JSON_FILENAME
from services.db import get_db, now_kst

logger = logging.getLogger(__name__)


# ============================================================
# 예외
# ============================================================
class RecordError(Exception):
    """settings_history 적재 실패. 사용자 파일 저장 자체는 별도 트랜잭션이므로
    이 예외는 호출자에서 토스트/로그/Telegram 으로 처리."""


class RestoreError(Exception):
    """restore_snapshot 실패 (스냅샷 부재, 안전 장치 차단, 파일 쓰기 실패)."""


# ============================================================
# 내부 헬퍼
# ============================================================
_SOURCE_PAGES = frozenset({
    "set_config", "set_buy_sell_conditions",
    "initial_seed", "restore", "auto_pre_restore",
    "strategy_init",  # ✅ SP2 — strategy 객체 재초기화 시점 자동 row
})
_STRATEGY_TYPES = frozenset({"MACD", "EMA"})

_APP_VERSION_RE = re.compile(r"v1\.\d{4}\.\d{2}\.\d{2}\.\d{4}")
_DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "pages" / "dashboard.py"


def _scoped_params_path(user_id: str, strategy_type: str) -> Path:
    """engine.params._scoped_path 와 동일 규칙으로 사용자/전략별 params 파일 경로."""
    base = f"{user_id}_{PARAMS_JSON_FILENAME}"
    p = Path(base)
    return Path(str(p.with_name(f"{p.stem}_{strategy_type}{p.suffix}")))


def _scoped_conditions_path(user_id: str, strategy_type: str) -> Path:
    """set_buy_sell_conditions 패턴: {user_id}_{STRATEGY}_{CONDITIONS_JSON_FILENAME}"""
    return Path(f"{user_id}_{strategy_type}_{CONDITIONS_JSON_FILENAME}")


def _read_file_as_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[settings_history] read fail {path}: {e}")
        return None


def _read_params_json(user_id: str, strategy_type: str) -> Optional[str]:
    return _read_file_as_text(_scoped_params_path(user_id, strategy_type))


def _read_conditions_json(user_id: str, strategy_type: str) -> Optional[str]:
    return _read_file_as_text(_scoped_conditions_path(user_id, strategy_type))


def _resolve_app_version() -> Optional[str]:
    """pages/dashboard.py 에서 v1.YYYY.MM.DD.HHMM 패턴을 best-effort 로 추출.
    실패 시 None (DM3)."""
    try:
        if not _DASHBOARD_PATH.exists():
            return None
        with _DASHBOARD_PATH.open("r", encoding="utf-8") as f:
            content = f.read()
        m = _APP_VERSION_RE.search(content)
        return m.group(0) if m else None
    except Exception:
        return None


def _validate(source_page: str, strategy_type: str) -> None:
    if source_page not in _SOURCE_PAGES:
        raise ValueError(f"invalid source_page: {source_page!r}")
    if strategy_type not in _STRATEGY_TYPES:
        raise ValueError(f"invalid strategy_type: {strategy_type!r}")


# ============================================================
# 공개 API
# ============================================================
def record_snapshot(
    user_id: str,
    source_page: str,
    strategy_type: str,
    *,
    note: Optional[str] = None,
    app_version: Optional[str] = None,
) -> int:
    """
    현 사용자/전략 설정 파일을 읽어 settings_history 에 한 행으로 적재.

    Returns:
        새 row id.

    Raises:
        RecordError: 두 파일 모두 읽기 실패 또는 DB INSERT 실패.
        ValueError: source_page / strategy_type 화이트리스트 미준수.
    """
    _validate(source_page, strategy_type)

    params_json = _read_params_json(user_id, strategy_type)
    conditions_json = _read_conditions_json(user_id, strategy_type)

    if params_json is None and conditions_json is None:
        raise RecordError(
            f"params/conditions 두 파일 모두 읽기 실패: user_id={user_id} "
            f"strategy_type={strategy_type}"
        )

    if app_version is None:
        app_version = _resolve_app_version()

    saved_at = now_kst()

    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO settings_history
                    (user_id, saved_at, source_page, strategy_type,
                     params_json, conditions_json, app_version, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, saved_at, source_page, strategy_type,
                 params_json, conditions_json, app_version, note),
            )
            conn.commit()
            new_id = cur.lastrowid
    except Exception as e:
        raise RecordError(f"INSERT 실패: {e}") from e

    logger.info(
        f"[settings_history] recorded id={new_id} user_id={user_id} "
        f"source_page={source_page} strategy_type={strategy_type} "
        f"params={'Y' if params_json else 'N'} "
        f"conditions={'Y' if conditions_json else 'N'} "
        f"app_version={app_version} note={note!r}"
    )
    return new_id


def record_strategy_init(
    user_id: str,
    strategy_type: str,
    *,
    note: Optional[str] = None,
) -> Optional[int]:
    """
    ✅ SP2 — strategy 객체가 재초기화되어 새 conditions 를 적용한 시점에 호출.

    동작:
        1. source_page='strategy_init' 로 record_snapshot 호출 (현재 파일 상태 캡처)
        2. 새로 생성된 row 의 applied_at 을 NOW 로 설정 (자기 자신 즉시 적용)
        3. 이 strategy_type 의 이전 applied_at IS NULL row 들도 NOW 로 일괄 UPDATE
           → "사용자 저장 시점 ~ 엔진 적용 시점" 격차를 시계열로 추적 가능

    Returns:
        새 strategy_init row id. 실패 시 None.
    """
    try:
        new_id = record_snapshot(
            user_id, "strategy_init", strategy_type,
            note=note or "strategy 객체 재초기화 — 활성 운영 conditions 기록",
        )
    except (RecordError, ValueError) as e:
        logger.warning(f"[settings_history] record_strategy_init 실패: {e}")
        return None

    now_str = now_kst()
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            # 새 row 자신의 applied_at
            cur.execute(
                "UPDATE settings_history SET applied_at = ? WHERE id = ?",
                (now_str, int(new_id)),
            )
            # 같은 (user, strategy) 의 이전 NULL row 들도 일괄 UPDATE
            cur.execute(
                "UPDATE settings_history SET applied_at = ? "
                "WHERE user_id = ? AND strategy_type = ? "
                "AND applied_at IS NULL AND id <> ?",
                (now_str, user_id, strategy_type, int(new_id)),
            )
            affected = cur.rowcount
            conn.commit()
        logger.info(
            f"[settings_history] strategy_init id={new_id} applied_at={now_str[:19]} "
            f"+ 이전 {affected} row 일괄 applied_at 채움"
        )
    except Exception as e:
        logger.warning(f"[settings_history] applied_at UPDATE 실패: {e}")
    return new_id


def seed_initial_snapshot(user_id: str, strategy_type: str) -> Optional[int]:
    """
    settings_history 가 비어있는 (user_id, strategy_type) 조합에
    시드 row 1개 적재. 이미 있으면 None (idempotent).
    """
    _validate("initial_seed", strategy_type)

    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM settings_history "
            "WHERE user_id=? AND strategy_type=? LIMIT 1",
            (user_id, strategy_type),
        )
        if cur.fetchone() is not None:
            logger.debug(
                f"[settings_history] seed skip (already exists) "
                f"user_id={user_id} strategy_type={strategy_type}"
            )
            return None

    try:
        return record_snapshot(
            user_id, "initial_seed", strategy_type,
            note="P1 자동 시드",
        )
    except RecordError as e:
        logger.warning(f"[settings_history] seed RecordError: {e}")
        return None


def get_active_settings_id(user_id: str, strategy_type: str) -> Optional[int]:
    """
    (user_id, strategy_type) 의 가장 최신 settings_history.id.
    비어있으면 None.
    """
    if strategy_type not in _STRATEGY_TYPES:
        return None
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM settings_history "
                "WHERE user_id=? AND strategy_type=? "
                "ORDER BY id DESC LIMIT 1",
                (user_id, strategy_type),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception as e:
        logger.warning(f"[settings_history] get_active_settings_id fail: {e}")
        return None


def fetch_history(
    user_id: str,
    *,
    strategy_type: Optional[str] = None,
    source_page: Optional[str] = None,
    since_ts: Optional[str] = None,
    until_ts: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """필터 기반 시계열 조회 (saved_at DESC)."""
    where = ["user_id = ?"]
    params: list[Any] = [user_id]
    if strategy_type:
        where.append("strategy_type = ?")
        params.append(strategy_type)
    if source_page:
        where.append("source_page = ?")
        params.append(source_page)
    if since_ts:
        where.append("saved_at >= ?")
        params.append(since_ts)
    if until_ts:
        where.append("saved_at <= ?")
        params.append(until_ts)

    sql = (
        "SELECT id, user_id, saved_at, source_page, strategy_type, "
        "       params_json, conditions_json, app_version, note, applied_at "
        "FROM settings_history "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY saved_at DESC, id DESC "
        "LIMIT ? OFFSET ?"
    )
    params.extend([int(limit), int(offset)])

    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

    cols = ["id", "user_id", "saved_at", "source_page", "strategy_type",
            "params_json", "conditions_json", "app_version", "note", "applied_at"]
    return [dict(zip(cols, r)) for r in rows]


def fetch_snapshot(user_id: str, snapshot_id: int) -> Optional[dict]:
    """단일 row 상세 조회."""
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, saved_at, source_page, strategy_type, "
            "       params_json, conditions_json, app_version, note, applied_at "
            "FROM settings_history WHERE id = ? AND user_id = ?",
            (int(snapshot_id), user_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    cols = ["id", "user_id", "saved_at", "source_page", "strategy_type",
            "params_json", "conditions_json", "app_version", "note", "applied_at"]
    return dict(zip(cols, row))


def diff_against_previous(user_id: str, snapshot_id: int) -> dict:
    """
    직전 동일 (user_id, strategy_type) 스냅샷과 컬럼별 변경분.

    Returns:
        {
            "params":     {"key": {"before": ..., "after": ...}, ...},
            "conditions": {"key": {"before": ..., "after": ...}, ...},
            "no_previous": bool,
        }
    """
    target = fetch_snapshot(user_id, snapshot_id)
    if target is None:
        raise ValueError(f"snapshot_id={snapshot_id} not found")

    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, params_json, conditions_json "
            "FROM settings_history "
            "WHERE user_id=? AND strategy_type=? AND id < ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id, target["strategy_type"], int(snapshot_id)),
        )
        prev_row = cur.fetchone()

    if prev_row is None:
        return {"params": {}, "conditions": {}, "no_previous": True}

    def _safe_load(s):
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}

    prev_params = _safe_load(prev_row[1])
    prev_cond = _safe_load(prev_row[2])
    cur_params = _safe_load(target["params_json"])
    cur_cond = _safe_load(target["conditions_json"])

    def _diff(before: dict, after: dict) -> dict:
        keys = set(before.keys()) | set(after.keys())
        out = {}
        for k in keys:
            b = before.get(k)
            a = after.get(k)
            if b != a:
                out[k] = {"before": b, "after": a}
        return out

    return {
        "params": _diff(prev_params, cur_params),
        "conditions": _diff(prev_cond, cur_cond),
        "no_previous": False,
    }


# ============================================================
# P3 — 복원 (restore)
# ============================================================
def _has_open_position(user_id: str) -> bool:
    """account_positions 에 잔량 > 0 인 row 가 있으면 True."""
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM account_positions "
                "WHERE user_id=? AND quantity > 0",
                (user_id,),
            )
            row = cur.fetchone()
            return bool(row and row[0] > 0)
    except Exception as e:
        logger.warning(f"[settings_history] open_position check fail: {e}")
        return False


def _resolve_active_strategy(user_id: str) -> Optional[str]:
    """현재 활성 전략을 settings_history 최신 row 에서 추정."""
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT strategy_type FROM settings_history "
            "WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def restore_snapshot(
    snapshot_id: int,
    *,
    user_id: str,
    actor: str = "user",
    require_strategy_match: bool = True,
    require_no_open_position: bool = True,
) -> dict:
    """
    snapshot_id 의 params/conditions 를 현재 파일에 덮어쓰고
    안전 스냅샷 + 복원 이벤트 row 적재 + active 갱신.

    상세 흐름: docs/plans/settings-history/plan.md §10-11-3
    """
    warnings: list[str] = []

    target = fetch_snapshot(user_id, int(snapshot_id))
    if target is None:
        raise RestoreError(f"snapshot_id={snapshot_id} 가 user_id={user_id} 에 없음")

    strategy_type = target["strategy_type"]
    params_json = target.get("params_json")
    conditions_json = target.get("conditions_json")

    if not params_json and not conditions_json:
        raise RestoreError("복원 대상 row 의 params/conditions 가 모두 NULL — 복원 불가")

    # 안전 장치 ① 전략 불일치 (D13)
    current_strategy = _resolve_active_strategy(user_id)
    if current_strategy and current_strategy != strategy_type:
        msg = (
            f"현재 활성 전략({current_strategy}) ≠ 복원 대상 전략({strategy_type}). "
            f"전략까지 전환됩니다."
        )
        if require_strategy_match:
            raise RestoreError(msg)
        warnings.append(msg)

    # 안전 장치 ② 활성 포지션 (D12)
    if _has_open_position(user_id):
        msg = "활성 포지션 보유 중 — TP/SL 변경 시 즉시 영향."
        if require_no_open_position:
            raise RestoreError(msg)
        warnings.append(msg)

    # ① 자동 사전 스냅샷 (현재 파일 상태 — 복원 직전 상태 보존)
    try:
        pre_id = record_snapshot(
            user_id, "auto_pre_restore", strategy_type,
            note=f"actor={actor} before_restore_id={snapshot_id}",
        )
    except RecordError as e:
        raise RestoreError(f"사전 스냅샷 적재 실패: {e}") from e

    # ② 파일 덮어쓰기
    try:
        if params_json:
            _scoped_params_path(user_id, strategy_type).write_text(
                params_json, encoding="utf-8"
            )
        if conditions_json:
            _scoped_conditions_path(user_id, strategy_type).write_text(
                conditions_json, encoding="utf-8"
            )
    except Exception as e:
        raise RestoreError(f"파일 덮어쓰기 실패: {e}") from e

    # ③ 복원 이벤트 row 적재 → 새 active id
    try:
        new_active_id = record_snapshot(
            user_id, "restore", strategy_type,
            note=f"actor={actor} restored_from_id={snapshot_id} pre_id={pre_id}",
        )
    except RecordError as e:
        raise RestoreError(f"복원 이벤트 row 적재 실패: {e}") from e

    # diff 계산
    try:
        diff = diff_against_previous(user_id, int(new_active_id))
    except Exception:
        diff = {"params": {}, "conditions": {}, "no_previous": True}

    # ④ Telegram CRITICAL 알림 (실패 시 무시)
    try:
        from services.notifier import send as _notify, LEVEL_CRITICAL
        _notify(
            LEVEL_CRITICAL,
            f"🔄 [설정 복원] {user_id}",
            (
                f"actor={actor}\n"
                f"snapshot_id={snapshot_id} → new_active_id={new_active_id}\n"
                f"pre_snapshot_id={pre_id}\n"
                f"strategy={strategy_type}\n"
                f"changes: params {len(diff['params'])} / conditions {len(diff['conditions'])}\n"
                + ("\n".join(f"⚠️ {w}" for w in warnings) if warnings else "")
            ),
            dedupe_key=f"settings_restore:{user_id}:{new_active_id}",
            dedupe_ttl=60,
        )
    except Exception:
        pass

    logger.info(
        f"[settings_history] restored user_id={user_id} from_id={snapshot_id} "
        f"pre_id={pre_id} new_active_id={new_active_id} "
        f"changes=p{len(diff['params'])}/c{len(diff['conditions'])} warnings={warnings}"
    )

    return {
        "pre_snapshot_id": pre_id,
        "restored_from_id": int(snapshot_id),
        "new_active_id": new_active_id,
        "diff": diff,
        "warnings": warnings,
    }


# ============================================================
# P4 — PnL 통합
# ============================================================
def _format_interval(start_ts: str, end_ts: Optional[str]) -> str:
    """saved_at 두 시각 차이를 '1h 23m' / '12분' / '5초' 등으로 포맷."""
    try:
        from datetime import datetime as _dt
        s = _dt.fromisoformat(start_ts)
        e = _dt.fromisoformat(end_ts) if end_ts else _dt.now(s.tzinfo)
        sec = int((e - s).total_seconds())
        if sec < 0:
            return "-"
        if sec < 60:
            return f"{sec}초"
        m, _ = divmod(sec, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        out = []
        if d:
            out.append(f"{d}일")
        if h:
            out.append(f"{h}h")
        if m or (not d and not h):
            out.append(f"{m}m")
        return " ".join(out) + (" (활성)" if end_ts is None else "")
    except Exception:
        return "-"


def _interval_bounds(user_id: str, snapshot_id: int) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    스냅샷의 유효 구간 (start_ts, end_ts) 반환.
    end_ts 는 같은 (user, strategy) 의 더 최신 row 의 saved_at. 없으면 None (현재 활성).
    같이 strategy_type 도 반환.
    """
    snap = fetch_snapshot(user_id, snapshot_id)
    if not snap:
        return None, None, None
    start_ts = snap["saved_at"]
    strategy_type = snap["strategy_type"]
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT saved_at FROM settings_history "
            "WHERE user_id=? AND strategy_type=? AND id > ? "
            "ORDER BY id ASC LIMIT 1",
            (user_id, strategy_type, snapshot_id),
        )
        row = cur.fetchone()
        end_ts = row[0] if row else None
    return start_ts, end_ts, strategy_type


def fetch_trades_for_snapshot(user_id: str, snapshot_id: int) -> list[dict]:
    """
    스냅샷 구간 내에 발생한 audit_trades 행 반환.
    settings_history_id 라벨 매칭을 1차로 시도, 없으면 시각 범위로 보조 매칭.
    """
    start_ts, end_ts, strategy_type = _interval_bounds(user_id, snapshot_id)
    if not start_ts:
        return []

    where = ["(settings_history_id = ?"]
    params: list = [int(snapshot_id)]
    # 보조 매칭: 라벨 NULL 인 거래는 시각 범위로 묶음
    where.append("OR (settings_history_id IS NULL AND timestamp >= ?")
    params.append(start_ts)
    if end_ts:
        where.append("AND timestamp < ?))")
        params.append(end_ts)
    else:
        where.append("))")

    sql = (
        "SELECT id, timestamp, ticker, type, reason, price, "
        "       entry_price, bars_held, settings_history_id "
        "FROM audit_trades "
        f"WHERE {' '.join(where)} "
        "ORDER BY id DESC"  # ✅ 최신 거래가 상위
    )
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    cols = ["id", "timestamp", "ticker", "type", "reason", "price",
            "entry_price", "bars_held", "settings_history_id"]
    return [dict(zip(cols, r)) for r in rows]


def compute_pnl_for_snapshot(user_id: str, snapshot_id: int) -> dict:
    """
    스냅샷 구간의 PnL/통계.

    Returns:
        {
            "realized_pnl_krw": float | None,
            "trades_bs": (buy_count, sell_count),
            "win": int, "loss": int, "flat": int,
            "avg_bars_held": float | None,
            "interval_label": str,
        }
    """
    start_ts, end_ts, strategy_type = _interval_bounds(user_id, snapshot_id)
    interval_label = _format_interval(start_ts, end_ts) if start_ts else "-"

    trades = fetch_trades_for_snapshot(user_id, snapshot_id)
    buys = [t for t in trades if t["type"] == "BUY"]
    sells = [t for t in trades if t["type"] == "SELL"]

    win = loss = flat = 0
    pnl_sum = 0.0
    pnl_known = False
    bars_held_vals = []

    # orders 와 시각 매칭으로 volume·paid_fee 보충 (best-effort)
    # SELL audit_trades 의 timestamp 와 가장 가까운 orders.executed_at (±60s) 매칭
    orders_by_id = {}
    if sells:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ticker, side, executed_volume, avg_price, paid_fee, "
                "       executed_at, timestamp, state "
                "FROM orders WHERE user_id=? AND side='SELL' "
                "AND state IN ('FILLED','PARTIALLY_FILLED') "
                "AND (executed_at >= ? OR timestamp >= ?)",
                (user_id, start_ts, start_ts),
            )
            for r in cur.fetchall():
                orders_by_id[r[0]] = {
                    "ticker": r[1], "side": r[2],
                    "executed_volume": r[3], "avg_price": r[4],
                    "paid_fee": r[5] or 0.0,
                    "executed_at": r[6], "timestamp": r[7],
                }

    def _match_order(sell_trade):
        """가장 가까운 SELL order (같은 ticker, ±60s) 찾기."""
        from datetime import datetime as _dt
        try:
            t_ts = _dt.fromisoformat(sell_trade["timestamp"])
        except Exception:
            return None
        best = None
        best_delta = None
        for oid, o in orders_by_id.items():
            if o["ticker"] != sell_trade["ticker"]:
                continue
            try:
                o_ts = _dt.fromisoformat(o["executed_at"] or o["timestamp"])
            except Exception:
                continue
            delta = abs((o_ts - t_ts).total_seconds())
            if delta > 60:
                continue
            if best_delta is None or delta < best_delta:
                best, best_delta = o, delta
        return best

    for s in sells:
        if s.get("bars_held") is not None:
            bars_held_vals.append(s["bars_held"])

        sp = s.get("price")
        ep = s.get("entry_price")
        if sp is None or ep is None:
            continue
        if sp > ep:
            win += 1
        elif sp < ep:
            loss += 1
        else:
            flat += 1

        order = _match_order(s)
        if order and order.get("executed_volume"):
            vol = float(order["executed_volume"])
            fee = float(order.get("paid_fee") or 0.0)
            pnl_sum += (sp - ep) * vol - fee
            pnl_known = True

    avg_bars = (sum(bars_held_vals) / len(bars_held_vals)) if bars_held_vals else None

    return {
        "realized_pnl_krw": (pnl_sum if pnl_known else None),
        "trades_bs": (len(buys), len(sells)),
        "win": win, "loss": loss, "flat": flat,
        "avg_bars_held": avg_bars,
        "interval_label": interval_label,
    }
