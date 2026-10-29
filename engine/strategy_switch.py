"""
2차 T12 (요청서 6절): 전략 전환·예약·복귀·예약 취소 — 엔진 프로세스 쪽.

사용자 결정 1029-03(「권고대로」)·PO 결정에 따른 구조 (계획 T12 「구현 메모」):
1. 예약 중 매수 차단 = 엔진 바깥 래퍼(install_buy_gate). 엔진을 붙일 때(core.engine_control.attach — live_loop._control_attach 가 부름) 모의(TEST) 엔진에만
   인스턴스 속성 execute·_execute_buy 를 「예약이 있을 때만 BUY 차단」으로 감싼다. 실계좌(LIVE) 엔진은 감싸지 않는다
   (실행·바이트 모두 지금과 같음). core/strategy_engine.py·core/strategy_incremental.py·engine/params.py 무변경.
   - 막는 것 = 봇 자동 매수: execute(BUY)(EMA·MACD 골든크로스·PULLBACK 회차) + _execute_buy(WO-2 지연 매수 재판정).
   - 막지 않는 것 = 사용자 강제 매수(구버전 force_buy_in·신버전 force_buy·PULLBACK _pullback_force_buy) — 결정 3.
   - 예약 조회는 처음부터 mode 로 거른다. 조회 실패 규칙(계획 분기 밖 표 132행):
       DB 읽기 예외 → BUY 차단 + WARNING [SWITCH-STATE] read failed (매도는 계속)
       테이블 없음 + 활성 EMA/MACD → 예약 없음(매수 계속) + CRITICAL 1회(1시간 dedupe)
       테이블 없음 + 활성 PULLBACK → BUY 차단
2. D4 유지(활성 전략 파일은 사용자당 1개): switch·revert 는 다른 모드 엔진이 없을 때만(mode_conflict — _engine_stop·_force
   와 같은 판정을 restart_engine 앞에서). LIVE switch·revert 는 엔진에 손대지 않고 거절(live_not_supported).
   복귀 = 직전 전략(EMA 또는 MACD)·그 종목·봉 단위.
3. 예약 중 사용자 강제 매수 허용: 예약은 그대로, 전환은 그 보유분이 팔린 뒤. 신버전 강제 매수 결과 문구에 1회 안내.
   흐름 5(「예약 있음 + 지갑 0」)는 F8(미체결 봇 매수 없음, services.db.has_pending_bot_limit_buy)도 본다.
   감시 스레드는 활성 파일을 쓰기 직전에 「지갑 0 + 미체결 매수 없음」을 다시 확인하고, 매수가 끼어들었으면 예약을 유지한다.

흐름(계획 T12):
- 즉시 전환(미보유): apply_saved → 행 RESERVED·note switching → 재확인 → 활성 파일 PULLBACK → restart_engine
  → 준비 신호(_ready) 뒤에만 DONE. 실패면 FAILED·활성 파일 되돌림·(전환 전에 엔진이 돌고 있었으면) 직전 전략 재기동 1회·CRITICAL.
- 예약(보유·미체결 매수): 행 RESERVED(note 없음). 감시 스레드(tick)가 엔진 제어 큐로 보유 확인 항목을 넣어(엔진 스레드에서
  지갑·포지션·미체결 판정) 「지갑 0 + 미체결 없음」을 본 봉 다음 봉에도 같으면 위 절차로 전환.
- 기동 때 처리 중 행 복구: 기동 재개 완료 Event(core.engine_control.BOOT_RESUME_DONE, scripts/tradebot_boot.py 가 finally 에서
  세움) 또는 감시 시작 60초 뒤 1회.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
TABLE = "strategy_switch"
TAG = "[SWITCH]"
STATE_TAG = "[SWITCH-STATE]"
NOTE_SWITCHING = "switching"
OLD_STRATEGIES = ("EMA", "MACD")
BOOT_FALLBACK_SEC = 60.0          # 기동 재개 완료 Event 가 없을 때 감시 시작 뒤 기다리는 시간
TABLE_MISSING_TTL = 3600          # 테이블 없음 CRITICAL dedupe(1시간)
SELL_REJECT_REPEAT = 2            # 예약 중 매도 거절이 이만큼 쌓이면 알림 1회
FLAT_EPS = 1e-6
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

NO_ACTION_TEXT = "투자자님이 따로 하실 일은 없습니다."
UNKNOWN_REQUEST_TEXT = "직접 요청하지 않으셨다면 운영자에게 바로 알려 주세요."
PULLBACK_LABEL = "눌림목 분할매수"

# 텔레그램·로그 문구(계획 T12 문구 표 — 결정 3 으로 「추가로 사지 않습니다」 → 「봇이 추가로 사지 않습니다」)
TEXT = {
    "switch_done": "🔁 전략 전환 완료 → 눌림목 분할매수 ({ticker} · {interval}). " + NO_ACTION_TEXT,
    "switch_reserved": ("⏳ 전환 예약 — 지금 보유분은 기존 방식으로 매도까지 관리합니다. "
                        "예약 중에는 봇이 추가로 사지 않습니다. " + NO_ACTION_TEXT),
    "switch_reserved_done": "🔁 전환 예약 완료 → 눌림목 분할매수. " + NO_ACTION_TEXT,
    "revert_done": "↩️ 기존 전략으로 복귀 → {strategy} ({ticker} · {interval}). " + NO_ACTION_TEXT,
    "revert_reserved": ("⏳ 복귀 예약 — 지금 보유분은 새 전략 매도 규칙(익절·손절·데드크로스)으로 판 뒤 {strategy} 로 "
                        "돌아갑니다. 예약 중에는 봇이 추가로 사지 않습니다. " + NO_ACTION_TEXT),
    "revert_reserved_done": "↩️ 복귀 예약 완료 → {strategy} ({ticker} · {interval}). " + NO_ACTION_TEXT,
    "cancel": "✖️ 전환 예약 취소 — 지금 전략을 그대로 씁니다. " + NO_ACTION_TEXT,
    "recovered_done": "🔁 전략 전환 완료(재시작 뒤 확인) → {label}. " + NO_ACTION_TEXT,
    "failed": "전략 전환에 실패해 기존 전략({strategy})으로 계속합니다. 운영자가 확인합니다. " + NO_ACTION_TEXT,
}
FAILED_TITLE = "🚨 전략 전환 실패 — 기존 전략으로 계속합니다"
ABORTED_TEXT = "⚠️ 전환이 끝나지 않았습니다 — 다시 눌러 주세요. 지금 전략은 그대로입니다."
SAVED_CHANGED_TEXT = ("⚠️ 예약한 뒤 새 전략 설정이 다시 저장되어 전환하지 않았습니다. 지금 전략을 그대로 씁니다. "
                      "전환하시려면 다시 눌러 주세요.")
SELL_REJECT_TEXT = "매도가 거절되고 있습니다 — 업비트 앱의 미체결 매도 주문을 확인해 주세요"
RESERVATION_KEPT_TEXT = ("전환 예약은 그대로입니다 — 이번에 산 보유분을 지금 전략이 매도까지 관리한 뒤 바뀝니다"
                         "(예약 중 봇 자동 매수는 계속 멈춤).")
# 아래 운영자 전용 문구(audience="operator", 1028-15 notifier 경로)는 투자자에게 가지 않아 내부 이름을 적는다.
TABLE_MISSING_TITLE = "🚨 [운영자] 새 전략 테이블 없음 — 마이그레이션 확인"
TABLE_MISSING_BODY = ("사용자 DB 에 strategy_switch 표가 없습니다(user={user}). 지금 전략(EMA/MACD)은 그대로 매수·매도합니다.\n"
                      "services/init_db.ensure_pullback_tables 마이그레이션을 확인해 주세요.")
DONE_RECORD_TITLE = "🚨 [운영자] 전략 전환 완료 기록 실패 — 감시가 다시 기록"
DONE_RECORD_BODY = ("전환은 끝났고 엔진은 {dst} 로 돕니다(user={user} row={row_id}). strategy_switch 행 DONE 기록이 실패해 "
                    "RESERVED·switching 으로 남았습니다. 감시 tick 이 「활성 파일 = 대상 + 엔진 준비」를 보면 DONE 으로 정리합니다.")
DONE_RECORD_RETRIES = 3           # DONE 기록 시도 횟수(실패 사이 0.5초)
MONITOR_QUEUE_WAIT_SEC = 3.0      # 전역 잠금을 쥔 감시 tick 의 보유 확인 큐 대기(요청 처리 지연을 짧게)


class SwitchTableMissing(Exception):
    """strategy_switch 테이블이 없음(마이그레이션 실패) — 읽기 예외와 구분."""


# ================================================================ 시각·표시
def kst_iso(t: Optional[float] = None) -> str:
    if t is None:
        return datetime.now(_KST).isoformat()
    return datetime.fromtimestamp(t, _KST).isoformat()


def interval_label(iv) -> str:
    m = re.fullmatch(r"minute(\d+)", str(iv or ""))
    return f"{m.group(1)}분봉" if m else str(iv or "")


def strategy_label(s) -> str:
    return PULLBACK_LABEL if s == "PULLBACK" else str(s or "")


# ================================================================ DB (사용자 DB 의 strategy_switch)
def _db_path(user_id: str) -> str:
    from services.init_db import get_db_path
    return get_db_path(user_id)


def _connect_ro(user_id: str) -> sqlite3.Connection:
    """읽기 연결(쓰기 금지 = PRAGMA query_only). DB 파일이 없으면 OperationalError(읽기 실패로 본다 — 몰래 만들지 않음).
    uri mode=ro 를 쓰지 않는 이유(fix round 1 항목 4): WAL DB 에 -shm 파일이 없으면 읽기 전용 연결은 -shm 을 만들지 못해
    「unable to open」으로 실패한다(엔진이 막 끝난 뒤 등). 그러면 예약 조회가 늘 실패해 매수 차단이 풀리지 않는다."""
    path = _db_path(user_id)
    if not os.path.exists(path):
        raise sqlite3.OperationalError("db missing")
    conn = sqlite3.connect(path, timeout=3)
    conn.execute("PRAGMA busy_timeout=3000;")
    conn.execute("PRAGMA query_only=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw(user_id: str) -> sqlite3.Connection:
    path = _db_path(user_id)
    if not os.path.exists(path):
        raise sqlite3.OperationalError("db missing")
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None


def reservation(user_id: str, mode: str) -> Optional[Dict[str, Any]]:
    """그 모드의 예약(kind SWITCH/REVERT, state RESERVED) 가장 최근 1행 또는 None.
    테이블 없음 → SwitchTableMissing, 그 밖 읽기 실패 → 예외 그대로(호출자가 안전 쪽으로)."""
    conn = _connect_ro(user_id)
    try:
        if not _table_exists(conn):
            raise SwitchTableMissing(TABLE)
        r = conn.execute(
            f"SELECT * FROM {TABLE} WHERE user_id=? AND mode=? AND kind IN ('SWITCH','REVERT') "
            f"AND state='RESERVED' ORDER BY id DESC LIMIT 1", (user_id, mode)).fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def last_done_switch(user_id: str, mode: str) -> Optional[Dict[str, Any]]:
    """복귀 대상 = 그 모드의 마지막 DONE SWITCH 행(from_*)."""
    conn = _connect_ro(user_id)
    try:
        if not _table_exists(conn):
            raise SwitchTableMissing(TABLE)
        r = conn.execute(
            f"SELECT * FROM {TABLE} WHERE user_id=? AND mode=? AND kind='SWITCH' AND state='DONE' "
            f"ORDER BY id DESC LIMIT 1", (user_id, mode)).fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def switching_rows(user_id: str) -> list:
    """처리 중(RESERVED·note switching)으로 남은 행 — 기동 때 복구 대상."""
    conn = _connect_ro(user_id)
    try:
        if not _table_exists(conn):
            return []
        rows = conn.execute(
            f"SELECT * FROM {TABLE} WHERE user_id=? AND kind IN ('SWITCH','REVERT') AND state='RESERVED' "
            f"AND note=? ORDER BY id", (user_id, NOTE_SWITCHING)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_row(user_id: str, row_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect_ro(user_id)
    try:
        r = conn.execute(f"SELECT * FROM {TABLE} WHERE id=?", (row_id,)).fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def insert_row(user_id: str, *, mode: str, kind: str, from_strategy: str, to_strategy: str,
               from_ticker=None, from_interval=None, to_ticker=None, to_interval=None,
               params_sha256=None, state: str = "RESERVED", request_id=None, note=None,
               requested_at: Optional[str] = None) -> int:
    conn = _connect_rw(user_id)
    try:
        if not _table_exists(conn):
            raise SwitchTableMissing(TABLE)
        cur = conn.execute(
            f"INSERT INTO {TABLE} (user_id, mode, kind, from_strategy, from_ticker, from_interval, to_strategy, "
            f"to_ticker, to_interval, params_sha256, state, requested_at, request_id, note) "
            f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, mode, kind, from_strategy, from_ticker, from_interval, to_strategy, to_ticker, to_interval,
             params_sha256, state, requested_at or kst_iso(), request_id, note))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


_KEEP = object()


def update_row(user_id: str, row_id: int, *, state=_KEEP, note=_KEEP, done_at=_KEEP) -> None:
    sets, args = [], []
    for col, v in (("state", state), ("note", note), ("done_at", done_at)):
        if v is not _KEEP:
            sets.append(f"{col}=?")
            args.append(v)
    if not sets:
        return
    conn = _connect_rw(user_id)
    try:
        conn.execute(f"UPDATE {TABLE} SET {', '.join(sets)} WHERE id=?", (*args, row_id))
        conn.commit()
    finally:
        conn.close()


def count_sell_rejects_after(user_id: str, base_id: int) -> int:
    conn = _connect_ro(user_id)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM audit_trades WHERE type='SELL_REJECTED' AND id>?",
                                (base_id,)).fetchone()[0])
    finally:
        conn.close()


def max_audit_id(user_id: str) -> int:
    conn = _connect_ro(user_id)
    try:
        return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_trades").fetchone()[0])
    finally:
        conn.close()


# ================================================================ 알림·로그 (시험에서 바꿈)
def _notify_default(level, title, body, *, dedupe_key=None, dedupe_ttl=3600):
    try:
        from services.notifier import send
        return send(level, title, body, dedupe_key=dedupe_key, dedupe_ttl=dedupe_ttl)
    except Exception as e:
        logger.warning(f"{TAG} 알림 실패(무해) | {type(e).__name__}")
        return False


def _notify_operator(level, title, body, *, dedupe_key=None, dedupe_ttl=3600):
    """운영자 전용 채널(1028-15 notifier audience="operator" — 운영자 채팅이 없으면 로그만, 투자자 채널로 넘어가지 않음)."""
    try:
        from services.notifier import send
        return send(level, title, body, dedupe_key=dedupe_key, dedupe_ttl=dedupe_ttl, audience="operator")
    except Exception as e:
        logger.warning(f"{TAG} 운영자 알림 실패(무해) | {type(e).__name__}")
        return False


def _insert_log(user_id: str, level: str, message: str) -> None:
    try:
        from services.db import insert_log
        insert_log(user_id, level, message)
    except Exception as e:
        logger.warning(f"{TAG} logs 기록 실패(무해) | {type(e).__name__}")


def _event(ctl, user_id: str, level: str, title: str, text: str, *, key: str, sensitive_request: bool = False):
    """사건 1건: logs 1줄 + 텔레그램 1회(dedupe = 사건 키). 요청에서 생긴 전환·복귀 사건은 S1 줄을 붙인다."""
    _insert_log(user_id, "ERROR" if level == "CRITICAL" else "INFO", f"{TAG} {text}")
    body = text + ("\n" + UNKNOWN_REQUEST_TEXT if sensitive_request else "")
    notify = getattr(ctl, "notify", None) or _notify_default
    try:
        notify(level, title, body, dedupe_key=f"strategy_switch:{user_id}:{key}", dedupe_ttl=86400)
    except Exception as e:
        logger.warning(f"{TAG} 알림 실패(무해) | {type(e).__name__}")


# ================================================================ 1. 매수 차단 래퍼 (모의 엔진만)
_TABLE_ALERTED: Dict[str, float] = {}
_ALERT_LOCK = threading.Lock()


def _alert_table_missing(user_id: str) -> None:
    import time
    now = time.monotonic()
    with _ALERT_LOCK:
        last = _TABLE_ALERTED.get(user_id)
        if last is not None and now - last < TABLE_MISSING_TTL:
            return
        _TABLE_ALERTED[user_id] = now
    logger.critical(f"{STATE_TAG} 테이블 없음 + 활성 EMA/MACD → 예약 없음으로 보고 매수 계속 | user={user_id}")
    _notify_operator("CRITICAL", TABLE_MISSING_TITLE, TABLE_MISSING_BODY.format(user=user_id),
                     dedupe_key=f"switch_table_missing:{user_id}", dedupe_ttl=TABLE_MISSING_TTL)


def gate_decision(user_id: str, mode: str, strategy_type: str):
    """(막음 여부, code). 예약 조회 실패 규칙은 계획 분기 밖 표 132행."""
    try:
        row = reservation(user_id, mode)
    except SwitchTableMissing:
        if strategy_type in OLD_STRATEGIES:
            _alert_table_missing(user_id)
            return False, None
        logger.warning(f"{STATE_TAG} 테이블 없음 + 활성 {strategy_type} → 매수 차단 | user={user_id}")
        return True, "switch_state_unknown"
    except Exception as e:
        logger.warning(f"{STATE_TAG} read failed → 매수 차단(매도는 계속) | user={user_id} mode={mode} | "
                       f"{type(e).__name__}")
        return True, "switch_state_unknown"
    if row is None:
        return False, None
    return True, "switch_reserved"


_BLOCK_NOTES = {
    "switch_reserved": "전략 전환(복귀) 예약 중 — 봇 자동 매수 차단(사용자 강제 매수는 허용)",
    "switch_state_unknown": "전략 전환 예약 상태를 읽지 못함 — 안전을 위해 봇 자동 매수 차단(매도는 계속)",
}


def install_buy_gate(engine, user_id: str, *, test_mode: Optional[bool] = None) -> bool:
    """모의(TEST) 엔진에만 execute·_execute_buy 인스턴스 속성을 감싼다. LIVE 면 아무것도 하지 않고 False."""
    tm = test_mode if test_mode is not None else getattr(getattr(engine, "trader", None), "test_mode", None)
    if tm is not True:
        logger.info(f"{TAG} 예약 매수 차단 래퍼 안 붙임(실계좌 엔진 — 지금과 같은 실행) | user={user_id}")
        return False
    if engine.__dict__.get("_switch_gate_installed"):
        return True
    from core.strategy_action import Action
    mode = "TEST"
    orig_execute = engine.execute
    orig_execute_buy = engine._execute_buy
    passed = {"in_execute": False}

    def _blocked(bar, indicators) -> bool:
        blocked, code = gate_decision(user_id, mode, getattr(engine, "strategy_type", ""))
        if not blocked:
            return False
        logger.info(f"⛔ {TAG} 봇 자동 매수 차단 | code={code} user={user_id} ts={getattr(bar, 'ts', None)}")
        try:
            engine._audit_buy_blocked(getattr(bar, "ts", None), indicators, price=getattr(bar, "close", None),
                                      code=code, note=_BLOCK_NOTES.get(code, code))
        except Exception as e:
            logger.warning(f"{TAG} 차단 기록 예외 무시 | {type(e).__name__}")
        return True

    def execute(action, bar, indicators):
        if action == Action.BUY:
            if _blocked(bar, indicators):
                return None
            passed["in_execute"] = True
            try:
                return orig_execute(action, bar, indicators)
            finally:
                passed["in_execute"] = False
        return orig_execute(action, bar, indicators)

    def _execute_buy(bar, indicators):
        # execute 안에서 이미 확인한 매수는 다시 읽지 않는다. WO-2 지연 매수 재판정(execute 밖)은 여기서 본다.
        if not passed["in_execute"] and _blocked(bar, indicators):
            return None
        return orig_execute_buy(bar, indicators)

    engine.execute = execute
    engine._execute_buy = _execute_buy
    engine._switch_gate_installed = True
    logger.info(f"{TAG} 예약 매수 차단 래퍼 붙임(모의 엔진 — 예약이 있을 때만 봇 자동 매수 차단) | user={user_id}")
    return True


# ================================================================ 보유 판정 (지갑 기준 + F8)
def _sym_mkt(ticker: str):
    sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
    return sym, f"KRW-{sym}"


def _locked_qty(user_id: str, ticker: str) -> float:
    """모의 잠김 수량. services.db.get_coin_balance_locked 는 예외 때 0 을 돌려주므로(fail-open — 그 함수 의미는 그대로 둠)
    여기서 직접 읽는다. 조회 예외는 그대로 올린다(호출자가 보유 중으로 봄). 잠김 칸이 없는 옛 스키마만 0."""
    conn = _connect_ro(user_id)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(account_positions)").fetchall()}
        if not cols:
            raise sqlite3.OperationalError("account_positions missing")
        if "virtual_coin_locked" not in cols:
            return 0.0
        sym, mkt = _sym_mkt(ticker)
        r = conn.execute("SELECT COALESCE(SUM(virtual_coin_locked), 0.0) FROM account_positions "
                         "WHERE user_id=? AND UPPER(ticker) IN (?, ?)", (user_id, sym, mkt)).fetchone()
        return float(r[0] if r and r[0] is not None else 0.0)
    finally:
        conn.close()


def _wallet_qty(user_id: str, ticker: str, trader) -> float:
    """모의: DB 가상 잔고(가용+잠김, 조회 예외는 그대로 올림 — 0 으로 보지 않음). 실계좌: trader._coin_balance."""
    if getattr(trader, "test_mode", False):
        from services.db import get_coin_balance
        return float(get_coin_balance(user_id, ticker) or 0.0) + _locked_qty(user_id, ticker)
    return float(trader._coin_balance(ticker))


def _pending_buy(user_id: str, ticker: str) -> bool:
    """F8 미체결 봇 매수. services.db.has_pending_bot_limit_buy 와 같은 판정(orders state/status IN REQUESTED·
    PARTIALLY_FILLED, 상태 칸이 없으면 없음)이지만 조회 예외는 「있음」(fail closed — 그 함수는 예외 때 False 라
    여기서 직접 읽는다. services/db.py 의미는 그대로)."""
    try:
        conn = _connect_ro(user_id)
    except Exception as e:
        logger.warning(f"{TAG} 미체결 매수 조회 실패 → 있음으로 봄 | user={user_id} | {type(e).__name__}")
        return True
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        status_col = "state" if "state" in cols else ("status" if "status" in cols else None)
        if status_col is None:
            return False
        r = conn.execute(f"SELECT 1 FROM orders WHERE user_id=? AND ticker=? AND side='BUY' "
                         f"AND {status_col} IN ('REQUESTED','PARTIALLY_FILLED') LIMIT 1", (user_id, ticker)).fetchone()
        return r is not None
    except Exception as e:
        logger.warning(f"{TAG} 미체결 매수 조회 실패 → 있음으로 봄 | user={user_id} | {type(e).__name__}")
        return True
    finally:
        conn.close()


def engine_flat_state(engine) -> Dict[str, Any]:
    """엔진 스레드에서(제어 큐) 부른다: 지갑·미체결 매수(F8)·포지션·직전 봉."""
    user, ticker = engine.user_id, engine.ticker
    qty = _wallet_qty(user, ticker, engine.trader)
    pending = []
    if _pending_buy(user, ticker):
        pending.append("limit_buy")
    pos = getattr(engine, "position", None)
    if getattr(pos, "pending_order", False):
        pending.append("pending_order")
    if getattr(engine, "_pending_split", None) is not None:
        pending.append("pending_split")
    if getattr(getattr(engine, "_pending_orders", None), "current", None) is not None:
        pending.append("wo2_pending")
    has_pos = bool(getattr(pos, "has_position", False))
    return {"wallet": qty, "pending": pending, "has_position": has_pos,
            "last_bar_ts": str(getattr(engine, "last_bar_ts", None)),
            "flat": qty < FLAT_EPS and not pending and not has_pos}


def standalone_flat_state(ctl, user_id: str, mode: str, strategy: str, ticker: str) -> Dict[str, Any]:
    """엔진이 없을 때: 지갑·미체결 매수만(봉 정보 없음)."""
    trader = ctl.trader_factory(user_id, mode, strategy) if mode != "TEST" else type("T", (), {"test_mode": True})()
    qty = _wallet_qty(user_id, ticker, trader)
    pending = ["limit_buy"] if _pending_buy(user_id, ticker) else []
    return {"wallet": qty, "pending": pending, "has_position": False, "last_bar_ts": None,
            "flat": qty < FLAT_EPS and not pending}


def flat_state(ctl, user_id: str, mode: str, strategy: str, ticker: str, *,
               queue_wait: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """보유 판정. 엔진이 돌면 엔진 스레드에서(제어 큐 — 감시 스레드는 엔진 잠금을 잡지 않음), 없으면 직접.
    판정 못 함(엔진 바쁨·예외) → None(보유 중으로 본다 — 안전 쪽).
    모의(TEST)가 아닌 엔진(또는 요청 mode 와 다른 엔진)의 큐에는 확인 항목을 넣지 않는다 → None (fix round 1 항목 1)."""
    from core import engine_control as ec
    try:
        running = ctl.manager.get_running_mode(user_id)
        if running is not None:
            if running != "TEST" or running != mode:
                logger.warning(f"{TAG} 보유 확인: 모의가 아닌(또는 다른 모드) 엔진 → 큐에 넣지 않고 보유 중으로 봄 | "
                               f"user={user_id} running={running} mode={mode}")
                return None
            engine = ec.running_engine(user_id)
            if engine is None:
                return None
            r = ctl._through_engine(engine, "switch_flat_check", {"id": None, "payload": {}}, queue_wait=queue_wait)
            if r.get("status") != "done":
                return None
            return dict(r.get("detail") or {})
        return standalone_flat_state(ctl, user_id, mode, strategy, ticker)
    except Exception as e:
        logger.warning(f"{TAG} 보유 판정 실패 → 보유 중으로 봄 | user={user_id} | {type(e).__name__}")
        return None


# ================================================================ 전략 정보 (시험에서 바꿈)
def _active(user_id: str) -> Optional[str]:
    from engine.control_requests import _active_strategy
    return _active_strategy(user_id)


def _active_file(user_id: str) -> Optional[str]:
    from engine.params import load_active_strategy
    return load_active_strategy(user_id, include_engine_only=True)


def _write_active(user_id: str, strategy: str) -> bool:
    """활성 전략 파일을 쓰고 다시 읽어 확인(save_active_strategy 는 실패를 로그로만 남김)."""
    from engine.params import save_active_strategy
    save_active_strategy(user_id, strategy)
    return _active_file(user_id) == strategy


def strategy_ticker_interval(user_id: str, strategy: str):
    """(종목, 봉 단위 문자열) — PULLBACK 은 적용본, EMA·MACD 는 그 전략 설정 파일. 못 읽으면 None."""
    import json
    if strategy == "PULLBACK":
        from engine import pullback_params as pbp
        try:
            with open(pbp.applied_path(user_id), "r", encoding="utf-8") as f:
                d = json.load(f)
            return d.get("ticker"), d.get("interval")
        except Exception:
            return None
    from config import PARAMS_JSON_FILENAME
    from engine.params import load_params
    p = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}", strategy_type=strategy)
    if p is None:
        return None
    return p.upbit_ticker, p.interval


def _saved_sha(user_id: str) -> str:
    from engine import pullback_params as pbp
    return pbp.check_saved_for_switch(user_id)


def _saved_ticker_interval(user_id: str):
    from engine import pullback_params as pbp
    d = pbp.read_json_strict(pbp.saved_path(user_id))
    return d.get("ticker"), d.get("interval")


def _apply_saved(user_id: str, sha: str) -> dict:
    from engine import pullback_params as pbp
    return pbp.apply_saved(user_id, sha)


# ================================================================ 2. 요청 처리 (감시 스레드, 전역 잠금 안)
def _r(status: str, code: str, detail: Optional[dict] = None) -> Dict[str, Any]:
    return {"status": status, "code": code, "detail": dict(detail or {})}


def _guard(ctl, req) -> Optional[Dict[str, Any]]:
    """공통 거절: LIVE(엔진 무접촉) → live_not_supported, 다른 모드 엔진 → mode_conflict(_engine_stop·_force 와 같은 판정)."""
    user, mode = req["user_id"], req["mode"]
    if mode == "LIVE":
        logger.info(f"{TAG} 실계좌 전환·복귀 요청 → 엔진 무접촉 거절 | user={user} kind={req.get('kind')}")
        return _r("rejected", "live_not_supported")
    running = ctl.manager.get_running_mode(user)
    if running is not None and running != mode:
        return _r("rejected", "mode_conflict", {"running": running})
    return None


def _reservation_or_result(user: str, mode: str):
    """(예약 행, None) 또는 (None, 거절 결과). 읽기 실패·테이블 없음은 처리 안 함."""
    try:
        return reservation(user, mode), None
    except SwitchTableMissing:
        return None, _r("rejected", "switch_table_missing")
    except Exception as e:
        logger.warning(f"{STATE_TAG} read failed (요청 처리) | user={user} | {type(e).__name__}")
        return None, _r("rejected", "reservation_unknown")


def handle_switch(ctl, req) -> Dict[str, Any]:
    """신버전 「백테스터 규칙으로 전환」 — payload {"saved_sha256"}."""
    g = _guard(ctl, req)
    if g is not None:
        return g
    user, mode, rid = req["user_id"], req["mode"], req.get("id")
    sha = (req.get("payload") or {}).get("saved_sha256")
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return _r("rejected", "bad_request")
    row, rej = _reservation_or_result(user, mode)
    if rej is not None:
        return rej
    if row is not None:
        return _r("rejected", "already_reserved", {"reservation_id": row["id"], "kind": row["kind"]})
    active = _active(user)
    if active == "PULLBACK" or _active_file(user) == "PULLBACK":
        return _r("rejected", "already_pullback")
    if active not in OLD_STRATEGIES:
        return _r("rejected", "params_missing")
    from engine.pullback_params import PullbackParamsError
    try:
        cur_sha = _saved_sha(user)
        to_ti = _saved_ticker_interval(user)
    except (PullbackParamsError, OSError):
        return _r("rejected", "saved_invalid")
    if cur_sha != sha:
        return _r("rejected", "sha_mismatch")
    from_ti = strategy_ticker_interval(user, active)
    if from_ti is None:
        return _r("rejected", "params_missing")
    was_running = ctl.manager.get_running_mode(user) is not None
    st = flat_state(ctl, user, mode, active, from_ti[0])
    common = dict(mode=mode, kind="SWITCH", from_strategy=active, from_ticker=from_ti[0], from_interval=from_ti[1],
                  to_strategy="PULLBACK", to_ticker=to_ti[0], to_interval=to_ti[1], params_sha256=sha,
                  request_id=rid, requested_at=kst_iso(ctl.now()))
    if st is None or not st.get("flat"):
        row_id = insert_row(user, state="RESERVED", note=None, **common)
        _event(ctl, user, "INFO", "⏳ 전환 예약", TEXT["switch_reserved"], key=f"{row_id}:reserved",
               sensitive_request=True)
        logger.info(f"{TAG} 보유·미체결 매수 → 예약 | user={user} row={row_id} state={st}")
        return _r("done", "reserved", {"reservation_id": row_id, "event_notified": True})
    try:
        _apply_saved(user, sha)
    except PullbackParamsError as e:
        return _r("rejected", "sha_mismatch" if getattr(e, "field", "") == "sha_mismatch" else "saved_invalid")
    except OSError:
        return _r("rejected", "saved_invalid")
    row_id = insert_row(user, state="RESERVED", note=NOTE_SWITCHING, **common)
    return execute_switch(ctl, user, mode, row_id, was_running=was_running, origin="request")


def handle_revert(ctl, req) -> Dict[str, Any]:
    """신버전 「기존 전략으로 복귀」 — 기록(마지막 DONE SWITCH 의 from_*)이 없으면 payload {"strategy": EMA|MACD} 필수."""
    g = _guard(ctl, req)
    if g is not None:
        return g
    user, mode, rid = req["user_id"], req["mode"], req.get("id")
    row, rej = _reservation_or_result(user, mode)
    if rej is not None:
        return rej
    if row is not None:
        return _r("rejected", "already_reserved", {"reservation_id": row["id"], "kind": row["kind"]})
    if _active_file(user) != "PULLBACK":
        return _r("rejected", "not_pullback")
    try:
        last = last_done_switch(user, mode)
    except Exception:
        last = None
    target = last["from_strategy"] if last and last.get("from_strategy") in OLD_STRATEGIES else None
    if target is None:
        choice = str((req.get("payload") or {}).get("strategy") or "").upper()
        if choice not in OLD_STRATEGIES:
            return _r("rejected", "choose_strategy")
        target = choice
    to_ti = strategy_ticker_interval(user, target)
    if to_ti is None:
        return _r("rejected", "params_missing")
    if last and (last.get("from_ticker"), last.get("from_interval")) != tuple(to_ti):
        logger.warning(f"{TAG} 복귀 대상 설정 파일의 종목·봉이 전환 전 기록과 다름 → 설정 파일 값으로 | user={user} "
                       f"record={last.get('from_ticker')}/{last.get('from_interval')} file={to_ti[0]}/{to_ti[1]}")
    from_ti = strategy_ticker_interval(user, "PULLBACK") or (None, None)
    was_running = ctl.manager.get_running_mode(user) is not None
    st = flat_state(ctl, user, mode, "PULLBACK", from_ti[0] or to_ti[0])
    common = dict(mode=mode, kind="REVERT", from_strategy="PULLBACK", from_ticker=from_ti[0],
                  from_interval=from_ti[1], to_strategy=target, to_ticker=to_ti[0], to_interval=to_ti[1],
                  request_id=rid, requested_at=kst_iso(ctl.now()))
    if st is None or not st.get("flat"):
        row_id = insert_row(user, state="RESERVED", note=None, **common)
        _event(ctl, user, "INFO", "⏳ 복귀 예약", TEXT["revert_reserved"].format(strategy=target),
               key=f"{row_id}:reserved", sensitive_request=True)
        return _r("done", "reserved", {"reservation_id": row_id, "event_notified": True})
    row_id = insert_row(user, state="RESERVED", note=NOTE_SWITCHING, **common)
    return execute_switch(ctl, user, mode, row_id, was_running=was_running, origin="request")


def handle_cancel(ctl, req) -> Dict[str, Any]:
    """예약 취소 → 행 CANCELED, 매수 차단 해제. 처리 중(switching) 행은 취소하지 않는다."""
    user, mode = req["user_id"], req["mode"]
    row, rej = _reservation_or_result(user, mode)
    if rej is not None:
        return rej
    if row is None:
        return _r("rejected", "no_reservation")
    if row.get("note") == NOTE_SWITCHING:
        return _r("rejected", "engine_busy")
    update_row(user, row["id"], state="CANCELED", done_at=kst_iso(ctl.now()))
    _event(ctl, user, "INFO", "✖️ 전환 예약 취소", TEXT["cancel"], key=f"{row['id']}:canceled")
    return _r("done", "ok", {"reservation_id": row["id"], "event_notified": True})


def post_force_buy(ctl, req, result: Dict[str, Any]) -> Dict[str, Any]:
    """결정 3: 예약 중 사용자 강제 매수는 허용. 주문이 나갔으면 결과 문구에 「예약은 그대로」 1회 안내."""
    if req.get("kind") != "force_buy" or result.get("status") != "done":
        return result
    try:
        row = reservation(req["user_id"], req["mode"])
    except Exception:
        return result
    if row is None:
        return result
    detail = dict(result.get("detail") or {})
    detail["reservation_kept"] = row["id"]
    detail["note_text"] = RESERVATION_KEPT_TEXT
    out = dict(result)
    out["detail"] = detail
    logger.info(f"{TAG} 예약 중 사용자 강제 매수 → 예약 유지 | user={req['user_id']} row={row['id']}")
    return out


# ================================================================ 3. 전환 실행 (즉시·예약 완료·공통)
def execute_switch(ctl, user: str, mode: str, row_id: int, *, was_running: bool, origin: str) -> Dict[str, Any]:
    """행(RESERVED·note switching)을 끝까지: 재확인 → 활성 파일 → restart_engine → 준비 뒤 DONE / 실패면 되돌림."""
    row = fetch_row(user, row_id)
    kind, src, dst = row["kind"], row["from_strategy"], row["to_strategy"]
    sensitive = origin == "request"
    # 활성 파일을 쓰기 직전 재확인(결정 3) — 그사이 매수가 들어왔으면 예약 유지
    ticker = row["from_ticker"] or row["to_ticker"]
    st = flat_state(ctl, user, mode, src, ticker,
                    queue_wait=MONITOR_QUEUE_WAIT_SEC if origin != "request" else None)
    if st is None or not st.get("flat"):
        update_row(user, row_id, note=None)
        logger.warning(f"{TAG} 활성 파일 쓰기 직전 재확인: 보유·미체결 매수 있음 → 예약 유지 | user={user} row={row_id} "
                       f"state={st}")
        if origin == "request":
            text = TEXT["switch_reserved"] if kind == "SWITCH" else TEXT["revert_reserved"].format(strategy=dst)
            _event(ctl, user, "INFO", "⏳ 전환 예약" if kind == "SWITCH" else "⏳ 복귀 예약", text,
                   key=f"{row_id}:reserved", sensitive_request=sensitive)
            return _r("done", "reserved", {"reservation_id": row_id, "event_notified": True})
        return _r("done", "reserved", {"reservation_id": row_id})
    # 재확인 ① 활성 파일 쓰기 직전(fix round 1 항목 1): 그사이 다른 모드(실계좌) 엔진이 떴으면 손대지 않는다
    running = ctl.manager.get_running_mode(user)
    if running not in (None, mode):
        return _mode_conflict_mid_switch(ctl, user, row, running, origin, wrote_active=False)
    if not _write_active(user, dst):
        return _fail(ctl, user, mode, row, "active_write_failed", was_running=was_running, restarted=False,
                     sensitive=sensitive)
    # 재확인 ② restart_engine 직전: 다른 모드 엔진이 떴으면 활성 파일만 직전 전략으로 되돌리고 멈춤(재시작·FAILED 없음)
    running = ctl.manager.get_running_mode(user)
    if running not in (None, mode):
        return _mode_conflict_mid_switch(ctl, user, row, running, origin, wrote_active=True)
    r = ctl.restart_engine(user, mode, dst)
    if r.get("status") != "done":
        return _fail(ctl, user, mode, row, r.get("code") or "start_failed", was_running=was_running,
                     restarted=True, sensitive=sensitive)
    recorded = _record_done(ctl, user, row_id, dst, note=None)
    if kind == "SWITCH":
        key = "switch_done" if origin == "request" else "switch_reserved_done"
        text = TEXT[key].format(ticker=row["to_ticker"], interval=interval_label(row["to_interval"]))
        title = "🔁 전략 전환 완료"
    else:
        key = "revert_done" if origin == "request" else "revert_reserved_done"
        text = TEXT[key].format(strategy=dst, ticker=row["to_ticker"], interval=interval_label(row["to_interval"]))
        title = "↩️ 기존 전략으로 복귀"
    _event(ctl, user, "INFO", title, text, key=f"{row_id}:done", sensitive_request=sensitive)
    logger.info(f"{TAG} 완료 | user={user} row={row_id} {src} → {dst} origin={origin}")
    detail = {"reservation_id": row_id, "strategy": dst, "event_notified": True}
    if not recorded:
        detail["done_record_pending"] = True
    return _r("done", "ok", detail)


def _record_done(ctl, user: str, row_id: int, dst: str, *, note) -> bool:
    """재시작이 끝난 뒤 DONE 기록. 실패하면 운영자 CRITICAL 1회 + 다시 시도(DONE_RECORD_RETRIES).
    끝내 실패하면 행은 RESERVED·switching 으로 남고, 감시 tick 이 「활성 = 대상 + 엔진 준비」로 정리한다(항목 3)."""
    alerted = False
    for i in range(DONE_RECORD_RETRIES):
        try:
            update_row(user, row_id, state="DONE", done_at=kst_iso(ctl.now()), note=note)
            return True
        except Exception as e:
            logger.critical(f"{TAG} DONE 기록 실패({i + 1}/{DONE_RECORD_RETRIES}) | user={user} row={row_id} | "
                            f"{type(e).__name__}")
            if not alerted:
                alerted = True
                _notify_operator("CRITICAL", DONE_RECORD_TITLE,
                                 DONE_RECORD_BODY.format(dst=dst, user=user, row_id=row_id),
                                 dedupe_key=f"strategy_switch:{user}:{row_id}:done_record", dedupe_ttl=3600)
            if i + 1 < DONE_RECORD_RETRIES:
                ctl.sleep(0.5)
    return False


def _mode_conflict_mid_switch(ctl, user, row, running, origin, *, wrote_active: bool):
    """전환 도중 다른 모드 엔진이 떴음(항목 1): 재시작·FAILED 없음. 활성 파일을 썼으면 직전 전략으로만 되돌린다.
    예약 완료(감시) 경로 → 예약 유지(note 지움, 다음 tick 에 다시). 즉시 요청 경로 → 행 CANCELED·mode_conflict 거절."""
    row_id, src = row["id"], row["from_strategy"]
    if wrote_active and not _write_active(user, src):
        logger.critical(f"{TAG} 전환 도중 다른 모드 엔진 — 활성 파일 되돌리기 실패 | user={user} row={row_id} → {src}")
    logger.warning(f"{TAG} 전환 도중 다른 모드 엔진({running}) → 손대지 않고 멈춤 | user={user} row={row_id} "
                   f"origin={origin} wrote_active={wrote_active}")
    if origin == "request":
        update_row(user, row_id, state="CANCELED", done_at=kst_iso(ctl.now()), note="mode_conflict")
        return _r("rejected", "mode_conflict", {"running": running})
    update_row(user, row_id, note=None)
    return _r("done", "mode_conflict", {"reservation_id": row_id, "running": running})


def _fail(ctl, user, mode, row, why, *, was_running: bool, restarted: bool, sensitive: bool):
    """FAILED·활성 파일 되돌림·(전환 전 엔진이 돌았고 이번에 재시작을 시도했으면) 직전 전략 재기동 1회·CRITICAL.
    restarted=False(활성 파일 쓰기 실패 — restart_engine 을 부르지 않음)면 엔진은 멈춘 적이 없으니 재시작하지 않는다(항목 9)."""
    row_id, src = row["id"], row["from_strategy"]
    update_row(user, row_id, state="FAILED", done_at=kst_iso(ctl.now()), note=str(why)[:64])
    if not _write_active(user, src):
        logger.critical(f"{TAG} 실패 뒤 활성 파일 되돌리기 실패 | user={user} row={row_id} → {src}")
    if was_running and restarted:
        running = ctl.manager.get_running_mode(user)
        if running is None or running == mode:
            rr = ctl.restart_engine(user, mode, src)
            logger.info(f"{TAG} 실패 뒤 직전 전략 재기동 1회 | user={user} {src} → {rr.get('status')}/{rr.get('code')}")
    logger.critical(f"{TAG} 전략 전환 실패 → 기존 전략으로 | user={user} row={row_id} why={why}")
    _event(ctl, user, "CRITICAL", FAILED_TITLE, TEXT["failed"].format(strategy=src), key=f"{row_id}:failed",
           sensitive_request=sensitive)
    return _r("error", "switch_failed", {"reservation_id": row_id, "why": str(why)[:64], "event_notified": True})


# ================================================================ 4. 감시 스레드 tick (예약 완료·기동 복구·매도 거절)
class Monitor:
    """control_loop 가 훑기 뒤 부른다. 전역 잠금(요청 처리와 한 번에 하나) 안에서 실행."""

    def __init__(self, boot_fallback_sec: float = BOOT_FALLBACK_SEC):
        self.boot_fallback_sec = boot_fallback_sec
        self.started = None
        self.boot_done = False
        self.flat_seen: Dict[tuple, str] = {}
        self.reject_base: Dict[tuple, int] = {}
        self.reject_notified: set = set()
        self.non_test_warned: set = set()

    def _warn_non_test(self, user: str, mode, where: str) -> None:
        """모의(TEST)가 아닌 행·엔진은 건너뛴다(항목 2). 같은 (사용자, 모드, 자리)는 WARNING 1회."""
        k = (user, mode, where)
        if k in self.non_test_warned:
            return
        self.non_test_warned.add(k)
        logger.warning(f"{TAG} 모의가 아닌 {where} 건너뜀(실계좌는 전환 미지원) | user={user} mode={mode}")

    def __call__(self, ctl) -> None:
        with ctl._GLOBAL_LOCK:
            if self.started is None:
                self.started = ctl.mono()
            if not self.boot_done and self._boot_ready(ctl):
                self.boot_done = True
                try:
                    self.recover_all(ctl)
                except Exception as e:
                    logger.error(f"{TAG} 기동 복구 예외 | {type(e).__name__}: {e}")
            for user in self._running_users():
                if self.boot_done:
                    try:
                        self.settle_switching(ctl, user)
                    except Exception as e:
                        logger.error(f"{TAG} 처리 중 행 정리 예외(다음 회차) | user={user} | {type(e).__name__}: {e}")
                try:
                    self.check_user(ctl, user)
                except Exception as e:
                    logger.error(f"{TAG} 예약 확인 예외(다음 회차) | user={user} | {type(e).__name__}: {e}")

    def _boot_ready(self, ctl) -> bool:
        from core import engine_control as ec
        return ec.BOOT_RESUME_DONE.is_set() or ctl.mono() - self.started >= self.boot_fallback_sec

    @staticmethod
    def _running_users() -> list:
        from core import engine_control as ec
        with ec._RUNNING_LOCK:
            return sorted(ec._RUNNING.keys())

    def settle_switching(self, ctl, user: str) -> list:
        """DONE 기록이 실패해 남은 처리 중 행 정리(항목 3): 그 모드 엔진이 돌고 준비 신호가 섰고 활성 파일 = 대상이고 실행 중 엔진의 전략 = 대상이면 DONE.
        요청 처리·전환 실행은 같은 전역 잠금 안이라, 여기서 보는 처리 중 행은 진행 중인 전환이 아니다(기동 복구 뒤에만 부름)."""
        mode = ctl.manager.get_running_mode(user)
        if mode is None:
            return []
        if mode != "TEST":
            self._warn_non_test(user, mode, "엔진(처리 중 행 정리)")
            return []
        ev = ctl.manager._ready.get(user)
        if ev is None or not ev.is_set():
            return []
        from core import engine_control as ec
        engine = ec.running_engine(user)
        running_strategy = getattr(engine, "strategy_type", None) if engine is not None else None
        out = []
        for row in switching_rows(user):
            if row.get("mode") != mode:
                continue
            if _active_file(user) != row["to_strategy"]:
                continue
            if running_strategy != row["to_strategy"]:      # 돌고 있는 엔진이 대상 전략이어야(fix round 2 항목 1)
                continue
            update_row(user, row["id"], state="DONE", done_at=kst_iso(ctl.now()), note="settled")
            logger.warning(f"{TAG} 처리 중으로 남은 행 DONE 정리(활성 = 대상 + 엔진 준비) | user={user} row={row['id']}")
            out.append(row["id"])
        return out

    def check_user(self, ctl, user: str) -> Optional[str]:
        mode = ctl.manager.get_running_mode(user)
        if mode is None:
            return None
        if mode != "TEST":
            self._warn_non_test(user, mode, "엔진(예약 확인)")
            return None
        try:
            row = reservation(user, mode)        # 처음부터 mode 로 거름
        except Exception:
            return None
        if row is None or row.get("note") == NOTE_SWITCHING:
            return None
        if row.get("mode") != "TEST":
            self._warn_non_test(user, row.get("mode"), "예약 행")
            return None
        key = (user, row["id"])
        src = row["from_strategy"]
        st = flat_state(ctl, user, mode, src, row["from_ticker"] or row["to_ticker"],
                        queue_wait=MONITOR_QUEUE_WAIT_SEC)
        if st is None or not st.get("flat"):
            self.flat_seen.pop(key, None)
            self._check_sell_rejects(ctl, user, row)
            return "holding"
        seen = self.flat_seen.get(key)
        if seen is None:
            self.flat_seen[key] = st.get("last_bar_ts")
            return "flat_seen"
        if st.get("last_bar_ts") == seen:
            return "wait_next_bar"
        self.flat_seen.pop(key, None)
        return self.complete(ctl, user, mode, row)

    def complete(self, ctl, user: str, mode: str, row: dict) -> str:
        """매도 완료 다음 봉: 예약 → 전환(또는 복귀)."""
        row_id = row["id"]
        if row["kind"] == "SWITCH":
            from engine.pullback_params import PullbackParamsError
            try:
                _apply_saved(user, row["params_sha256"])
            except (PullbackParamsError, OSError) as e:
                update_row(user, row_id, state="FAILED", done_at=kst_iso(ctl.now()),
                           note=f"saved_changed:{getattr(e, 'field', type(e).__name__)}"[:64])
                _event(ctl, user, "WARNING", "⚠️ 전환 예약 끝냄 — 설정이 바뀜", SAVED_CHANGED_TEXT,
                       key=f"{row_id}:saved_changed")
                return "saved_changed"
        update_row(user, row_id, note=NOTE_SWITCHING)
        r = execute_switch(ctl, user, mode, row_id, was_running=True, origin="reserved")
        return r.get("code")

    def _check_sell_rejects(self, ctl, user: str, row: dict) -> None:
        key = (user, row["id"])
        try:
            if key not in self.reject_base:
                self.reject_base[key] = max_audit_id(user)
                return
            if key in self.reject_notified:
                return
            n = count_sell_rejects_after(user, self.reject_base[key])
        except Exception:
            return
        if n >= SELL_REJECT_REPEAT:
            self.reject_notified.add(key)
            _insert_log(user, "WARNING", f"{TAG} 예약 중 {SELL_REJECT_TEXT} (거절 {n}건)")
            notify = getattr(ctl, "notify", None) or _notify_default
            try:
                notify("WARNING", "⚠️ 매도 거절 반복 — 전환 예약 유지", SELL_REJECT_TEXT + ". 전환 예약은 그대로입니다.",
                       dedupe_key=f"strategy_switch:{user}:{row['id']}:sell_reject", dedupe_ttl=3600)
            except Exception as e:
                logger.warning(f"{TAG} 알림 실패(무해) | {type(e).__name__}")

    # ------------------------------------------------------------ 기동 때 처리 중 행 복구 (흐름 9)
    @staticmethod
    def _db_users() -> list:
        from services.init_db import DB_DIR, DB_PREFIX
        out = []
        for p in sorted(glob.glob(os.path.join(DB_DIR, f"{DB_PREFIX}_*.db"))):
            name = os.path.basename(p)[len(DB_PREFIX) + 1:-3]
            if re.fullmatch(r"[A-Za-z0-9_]{1,32}", name):
                out.append(name)
        return out

    def recover_all(self, ctl, users: Optional[list] = None) -> list:
        done = []
        for user in (users if users is not None else self._db_users()):
            try:
                rows = switching_rows(user)
            except Exception:
                continue
            for row in rows:
                if row.get("mode") != "TEST":
                    self._warn_non_test(user, row.get("mode"), "처리 중 행(기동 복구)")
                    done.append((user, row["id"], "skipped"))
                    continue
                done.append((user, row["id"], self.recover_row(ctl, user, row)))
        return done

    def recover_row(self, ctl, user: str, row: dict) -> str:
        row_id, mode, src, dst = row["id"], row["mode"], row["from_strategy"], row["to_strategy"]
        if mode != "TEST":
            self._warn_non_test(user, mode, "처리 중 행(기동 복구)")
            return "skipped"
        active = _active_file(user)
        if active != dst:
            update_row(user, row_id, state="FAILED", done_at=kst_iso(ctl.now()), note="aborted_before_switch")
            _event(ctl, user, "WARNING", "⚠️ 전략 전환 미완료", ABORTED_TEXT, key=f"{row_id}:aborted")
            return "aborted"
        m = ctl.manager
        t0 = ctl.mono()
        while True:
            ev = m._ready.get(user)
            running = m.get_running_mode(user)
            if running == mode and ev is not None and ev.is_set():
                update_row(user, row_id, state="DONE", done_at=kst_iso(ctl.now()), note="recovered")
                _event(ctl, user, "INFO", "🔁 전략 전환 완료(재시작 뒤 확인)",
                       TEXT["recovered_done"].format(label=strategy_label(dst)), key=f"{row_id}:recovered")
                return "recovered"
            if running != mode or ctl.mono() - t0 >= ctl.ready_wait:
                break
            ctl.sleep(0.5)
        update_row(user, row_id, state="FAILED", done_at=kst_iso(ctl.now()), note="boot_not_ready")
        _write_active(user, src)
        running = m.get_running_mode(user)
        if running is None or running == mode:
            ctl.restart_engine(user, mode, src)
        logger.critical(f"{TAG} 기동 복구: 전환 엔진이 뜨지 않음 → 직전 전략으로 | user={user} row={row_id}")
        _event(ctl, user, "CRITICAL", FAILED_TITLE, TEXT["failed"].format(strategy=src), key=f"{row_id}:failed")
        return "failed"


# ================================================================ 5. 설치 (scripts/tradebot_boot._control_thread 가 1회)
_INSTALLED = {"done": False}


def install() -> None:
    """감시 스레드에 switch·revert·cancel_reservation 처리, 강제 매수 결과 안내, tick(Monitor)을 붙인다."""
    from engine import control_requests as cr
    if _INSTALLED["done"]:
        return
    cr.register_handler("switch", handle_switch)
    cr.register_handler("revert", handle_revert)
    cr.register_handler("cancel_reservation", handle_cancel)
    cr.register_post_hook(post_force_buy)
    cr.register_tick_hook(Monitor())
    _INSTALLED["done"] = True
    logger.info(f"{TAG} 전환·예약·복귀 처리 설치")
