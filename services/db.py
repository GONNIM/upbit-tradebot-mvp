import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import contextmanager

import json
from typing import Optional, Dict, Any
from services.init_db import get_db_path, ensure_orders_extended_schema

from config import DEFAULT_USER_ID


def ensure_schema(user_id: str):
    ensure_orders_extended_schema(user_id)


DB_PREFIX = "tradebot"


@contextmanager
def get_db(user_id):
    # DB_PATH = f"{DB_PREFIX}_{user_id}.db"
    # conn = sqlite3.connect(DB_PATH)
    DB_PATH = get_db_path(user_id)  # ⬅️ 절대경로 통일!
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    try:
        # 🔧 동시성/안정화
        conn.execute("PRAGMA journal_mode=WAL;")     # 동시 읽기/쓰기 개선
        conn.execute("PRAGMA synchronous=NORMAL;")   # 성능/안정 균형
        conn.execute("PRAGMA busy_timeout=3000;")    # ms, 잠금 시 대기
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
    finally:
        conn.close()


# ✅ 시간 생성 함수 (KST 기준)
def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def now_kst_minute() -> str:
    """
    분 단위로 절삭된 KST timestamp 반환
    - 초와 마이크로초를 0으로 설정하여 동일한 분 내 모든 호출이 같은 값 반환
    - 설정 스냅샷 감사로그의 1분당 1개 보장을 위해 사용
    예: 2026-01-15T21:16:04.934888+09:00 → 2026-01-15T21:16:00+09:00
    """
    dt = datetime.now(ZoneInfo("Asia/Seoul"))
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


# ✅ 사용자 정보
def save_user(username: str, display_name: str, virtual_krw: int):
    now = now_kst()

    with get_db(username) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE users
               SET display_name = ?,
                   virtual_krw   = ?,
                   updated_at    = ?
             WHERE username = ?
            """,
            (display_name, virtual_krw, now, username),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO users (username, display_name, virtual_krw, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, display_name, virtual_krw, now),
            )

        conn.commit()


def get_user(username: str):
    with get_db(username) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT display_name, virtual_krw, updated_at FROM users WHERE username=?",
            (username,),
        )
        return cursor.fetchone()


# ✅ 주문
def insert_order(
    user_id,
    ticker,
    side,
    price,
    volume,
    status,
    current_krw=None,
    current_coin=None,
    profit_krw=None,
    *,
    provider_uuid: str | None = None,
    state: str | None = None,
    requested_at: str | None = None,
    executed_at: str | None = None,
    canceled_at: str | None = None,
    executed_volume: float | None = None,
    avg_price: float | None = None,
    paid_fee: float | None = None,
):
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (
                user_id, timestamp, ticker, side, price, volume, status,
                current_krw, current_coin, profit_krw,
                provider_uuid, state, requested_at, executed_at, canceled_at,
                executed_volume, avg_price, paid_fee, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                now_kst(),
                ticker,
                side,
                price,
                volume,
                status,
                current_krw,
                current_coin,
                profit_krw,
                provider_uuid,
                state,
                requested_at or (now_kst() if state == "REQUESTED" else None),
                executed_at,
                canceled_at,
                executed_volume,
                avg_price,
                paid_fee,
                now_kst(),
            ),
        )
        conn.commit()


def fetch_recent_orders(user_id, limit=10):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, ticker, side, price, volume, status, current_krw, current_coin
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """,
            (user_id, limit),
        )
        return cursor.fetchall()


def fetch_latest_order_by_ticker(user_id: str, ticker: str):
    """
    특정 ticker의 가장 최신 주문 1건 조회
    - timestamp 기준 최신순 정렬
    - 해당 ticker만 필터링
    """
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, ticker, side, price, volume, status, current_krw, current_coin
            FROM orders
            WHERE user_id = ? AND ticker = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (user_id, ticker),
        )
        return cursor.fetchone()


def delete_orders(user_id):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
        deleted = cursor.rowcount
        conn.commit()
    print(f"🧹 Deleted {deleted} rows from orders table for user={user_id}.")


# ✅ 로그
def insert_log(user_id: str, level: str, message: str):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO logs (user_id, timestamp, level, message)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, now_kst(), level, message),
        )
        conn.commit()


def fetch_logs(user_id, level="LOG", limit=20):
    with get_db(user_id) as conn:
        cursor = conn.cursor()

        if level == "BUY":
            cursor.execute(
                """
                SELECT timestamp, level, message
                FROM logs
                WHERE user_id = ?
                  AND (
                      level = 'BUY'
                      OR (level = 'INFO' AND message LIKE '%강제매수%')
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        elif level == "SELL":
            cursor.execute(
                """
                SELECT timestamp, level, message
                FROM logs
                WHERE user_id = ?
                  AND (
                      level = 'SELL'
                      OR (level = 'INFO' AND message LIKE '%강제청산%')
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        elif level == "INFO":
            cursor.execute(
                """
                SELECT timestamp, level, message
                FROM logs
                WHERE user_id = ?
                  AND (
                      (level = 'INFO' OR level = 'BUY' OR level = 'SELL')
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT timestamp, level, message
                FROM logs
                WHERE user_id = ?
                  AND level = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, level, limit),
            )

        return cursor.fetchall()


def get_last_status_log_from_db(user_id: str) -> str:
    status_prefixes = ("🚀","🔌","🛑","✅","⚠️","📡","🔄","❌","🚨")
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        emoji_conditions = " OR ".join(["message LIKE ?"] * len(status_prefixes))
        params = [user_id] + [f"{p}%" for p in status_prefixes]
        try:
            cursor.execute(
                f"""
                SELECT timestamp, message FROM logs
                WHERE user_id = ?
                  AND (level IN ('INFO','BUY','SELL'))
                  AND ({emoji_conditions})
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
            if row:
                ts, message = row
                try:
                    formatted_ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    formatted_ts = ts
                return f"[{formatted_ts}] {message}"
            else:
                return "❌ 상태 로그 없음"
        except Exception as e:
            return f"❌ DB 조회 오류: {e}"


def delete_old_logs(user_id):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM logs
            WHERE user_id = ?
              AND timestamp < DATETIME('now', 'start of day', 'localtime');
            """,
            (user_id,),
        )
        deleted = cursor.rowcount
        conn.commit()
    print(f"🧹 Deleted {deleted} old logs for user={user_id}.")


def fetch_latest_log_signal_ema(user_id: str, ticker: str) -> dict | None:
    """
    EMA 전략의 가장 최신 'LOG' 레벨 로그 파싱
    - message 예시: "[LIVE] 2025-12-21 15:30:45 | price=0.02 | cross=Golden |
      ema_fast_buy=0.0236 | ema_slow_buy=0.0228 | ema_fast_sell=0.0240 | ema_slow_sell=0.0237 | ema_base=0.0220 | bar=495"
    """
    query = """
        SELECT message, timestamp
        FROM logs
        WHERE user_id = ? AND level = 'LOG' AND message LIKE '%ema_fast_buy=%'
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if row:
                message, db_timestamp = row[0], row[1]
                try:
                    parts = message.split(" | ")
                    # parts[0]: "[LIVE/TEST] timestamp"
                    import re
                    time_str = parts[0].strip()
                    clean_timestamp = re.sub(r'^\[(TEST|LIVE)\]\s*', '', time_str)

                    # 나머지 파라미터 파싱
                    params_dict = {}
                    for part in parts[1:]:
                        if "=" in part:
                            key, val = part.split("=", 1)
                            params_dict[key.strip()] = val.strip()

                    return {
                        "시간": db_timestamp,  # DB 기록 시간
                        "Ticker": ticker,
                        "price": params_dict.get("price", "-"),
                        "cross": params_dict.get("cross", "-"),
                        "ema_fast_buy": params_dict.get("ema_fast_buy", "-"),
                        "ema_slow_buy": params_dict.get("ema_slow_buy", "-"),
                        "ema_fast_sell": params_dict.get("ema_fast_sell", "-"),
                        "ema_slow_sell": params_dict.get("ema_slow_sell", "-"),
                        "ema_base": params_dict.get("ema_base", "-"),
                    }
                except Exception as e:
                    logger.error(f"[EMA] log parsing failed: {e} | message={message}")
                    return None
    except Exception as e:
        logger.error(f"[EMA] fetch_latest_log_signal_ema failed: {e}")
    return None


def fetch_latest_log_signal(user_id: str, ticker: str) -> dict | None:
    """
    MACD 전략의 가장 최신 'LOG' 레벨 로그 파싱
    - message 예시: "[LIVE] 2025-07-01 20:47:00 | price=220.5 | cross=Neutral | macd=0.02563 | signal=0.03851 | bar=495"
    """
    query = """
        SELECT message, timestamp
        FROM logs
        WHERE user_id = ? AND level = 'LOG' AND message LIKE '%price=%' AND message LIKE '%macd=%'
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if row:
                message, db_timestamp = row[0], row[1]
                try:
                    parts = message.split(" | ")
                    time_str = parts[0].strip()
                    import re
                    clean_timestamp = re.sub(r'^\[(TEST|LIVE)\]\s*', '', time_str)
                    price = parts[1].split("=")[1].strip()
                    cross = parts[2].split("=")[1].strip()
                    macd = parts[3].split("=")[1].strip()
                    signal = parts[4].split("=")[1].strip()

                    return {
                        "시간": db_timestamp,  # DB 기록 시간
                        "Ticker": ticker,
                        "price": price,
                        "cross": cross,
                        "macd": macd,
                        "signal": signal,
                    }
                except Exception:
                    return None
            return None
    except Exception:
        return None


# ✅ 계정 정보
def get_account(user_id):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT virtual_krw FROM accounts WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def create_or_init_account(user_id, init_krw=1_000_000):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO accounts (user_id, virtual_krw) VALUES (?, ?)",
            (user_id, init_krw),
        )
        conn.commit()


def update_account(user_id, virtual_krw):
    virtual_krw = int(virtual_krw)  # ✅ 정수로 변환

    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE accounts
            SET virtual_krw = ?, updated_at = ?
            WHERE user_id = ?
        """,
            (virtual_krw, now_kst(), user_id),
        )
        conn.commit()
    insert_account_history(user_id, virtual_krw)


# ✅ 포지션 정보
def get_coin_balance(user_id, ticker):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        # 'WLFI'로 오더가 와도 'KRW-WLFI' 행을 집계할 수 있게 심볼/마켓코드 모두 조회
        sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
        mkt = f"KRW-{sym}"

        cursor.execute(
            """
            SELECT COALESCE(SUM(virtual_coin), 0.0)
            FROM account_positions
            WHERE user_id = ?
            AND UPPER(ticker) IN (?, ?)
        """,
            (user_id, sym, mkt),
        )
        row = cursor.fetchone()
        return row[0] if row else 0.0


def update_coin_position(user_id, ticker, virtual_coin):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO account_positions (user_id, ticker, virtual_coin, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, ticker) DO UPDATE SET
                virtual_coin = excluded.virtual_coin,
                updated_at = excluded.updated_at
        """,
            (user_id, ticker, virtual_coin, now_kst()),
        )
        conn.commit()
    insert_position_history(user_id, ticker, virtual_coin)


# ✅ 히스토리 누적
def insert_account_history(user_id: str, virtual_krw: int):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO account_history (user_id, timestamp, virtual_krw)
            VALUES (?, ?, ?)
        """,
            (user_id, now_kst(), virtual_krw),
        )
        conn.commit()


def insert_position_history(user_id: str, ticker: str, virtual_coin: float):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO position_history (user_id, timestamp, ticker, virtual_coin)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, now_kst(), ticker, virtual_coin),
        )
        conn.commit()


# ✅ 엔진 상태
def set_engine_status(user_id, is_running: bool):
    now = now_kst()
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO engine_status (user_id, is_running, last_heartbeat)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                is_running = excluded.is_running,
                last_heartbeat = excluded.last_heartbeat
        """,
            (user_id, int(is_running), now),
        )
        conn.commit()


def get_engine_status(user_id) -> bool:
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_running FROM engine_status WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])


# ✅ Thread 상태
def set_thread_status(user_id, is_thread_running: bool):
    now = now_kst()
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO thread_status (user_id, is_thread_running, last_heartbeat)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                is_thread_running = excluded.is_thread_running,
                last_heartbeat = excluded.last_heartbeat
        """,
            (user_id, int(is_thread_running), now),
        )
        conn.commit()


def get_thread_status(user_id) -> bool:
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_thread_running FROM thread_status WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])


def get_initial_krw(user_id: str) -> float:
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT virtual_krw FROM users WHERE username = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def insert_buy_eval(
    user_id: str,
    ticker: str,
    interval_sec: int,
    bar: int,
    price: float,
    macd: float,
    signal: float,
    have_position: bool,
    overall_ok: bool,
    failed_keys: list | None,
    checks: dict | None,
    notes: str = "",
    timestamp: str | None = None  # ✅ 봉 시각 파라미터 (기본값: 현재 시각)
):
    """
    BUY 평가 감사로그 기록 (UPSERT 방식)
    - 같은 (ticker, timestamp)에 대해 기존 레코드가 있으면 UPDATE
    - 없으면 INSERT
    - 목적: NO_SIGNAL 기록 후 상세 평가 기록 시 중복 방지
    """
    ts = timestamp if timestamp is not None else now_kst()

    with get_db(user_id) as conn:
        cur = conn.cursor()

        # 1. 기존 레코드 확인 (같은 ticker, timestamp)
        cur.execute(
            """
            SELECT id FROM audit_buy_eval
            WHERE ticker=? AND timestamp=?
            """,
            (ticker, ts)
        )
        existing = cur.fetchone()

        if existing:
            # 2-1. UPDATE: 기존 레코드 갱신 (나중 평가가 이전 기록 덮어씀)
            cur.execute(
                """
                UPDATE audit_buy_eval
                SET interval_sec=?, bar=?, price=?, macd=?, signal=?,
                    have_position=?, overall_ok=?, failed_keys=?, checks=?, notes=?
                WHERE id=?
                """,
                (
                    interval_sec, bar, price, macd, signal,
                    int(bool(have_position)), int(bool(overall_ok)),
                    json.dumps(failed_keys, ensure_ascii=False) if failed_keys else None,
                    json.dumps(checks, ensure_ascii=False) if checks else None,
                    notes,
                    existing[0]
                )
            )
        else:
            # 2-2. INSERT: 새 레코드 생성
            cur.execute(
                """
                INSERT INTO audit_buy_eval
                (timestamp, ticker, interval_sec, bar, price, macd, signal,
                 have_position, overall_ok, failed_keys, checks, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, ticker, interval_sec, bar, price, macd, signal,
                    int(bool(have_position)), int(bool(overall_ok)),
                    json.dumps(failed_keys, ensure_ascii=False) if failed_keys else None,
                    json.dumps(checks, ensure_ascii=False) if checks else None,
                    notes
                )
            )

        conn.commit()


def insert_sell_eval(
    user_id: str,
    ticker: str,
    interval_sec: int,
    bar: int,
    price: float,
    macd: float,
    signal: float,
    tp_price: float,
    sl_price: float,
    highest: float | None,
    ts_pct: float | None,
    ts_armed: bool,
    bars_held: int,
    checks: dict,
    triggered: bool,
    trigger_key: str | None,
    notes: str = "",
    timestamp: str | None = None  # ✅ 봉 시각 파라미터 (기본값: 현재 시각)
):
    """
    SELL 평가 감사로그 기록 (UPSERT 방식)
    - 같은 (ticker, timestamp)에 대해 기존 레코드가 있으면 UPDATE
    - 없으면 INSERT
    - 목적: NO_SIGNAL 기록 후 상세 평가 기록 시 중복 방지
    """
    ts = timestamp if timestamp is not None else now_kst()

    with get_db(user_id) as conn:
        cur = conn.cursor()

        # 1. 기존 레코드 확인 (같은 ticker, timestamp)
        cur.execute(
            """
            SELECT id FROM audit_sell_eval
            WHERE ticker=? AND timestamp=?
            """,
            (ticker, ts)
        )
        existing = cur.fetchone()

        if existing:
            # 2-1. UPDATE: 기존 레코드 갱신 (나중 평가가 이전 기록 덮어씀)
            cur.execute(
                """
                UPDATE audit_sell_eval
                SET interval_sec=?, bar=?, price=?, macd=?, signal=?,
                    tp_price=?, sl_price=?, highest=?, ts_pct=?, ts_armed=?,
                    bars_held=?, checks=?, triggered=?, trigger_key=?, notes=?
                WHERE id=?
                """,
                (
                    interval_sec, bar, price, macd, signal,
                    tp_price, sl_price, highest, ts_pct, int(bool(ts_armed)),
                    bars_held,
                    json.dumps(checks, ensure_ascii=False) if checks else None,
                    int(bool(triggered)), trigger_key, notes,
                    existing[0]
                )
            )
        else:
            # 2-2. INSERT: 새 레코드 생성
            cur.execute(
                """
                INSERT INTO audit_sell_eval
                (timestamp, ticker, interval_sec, bar, price, macd, signal,
                 tp_price, sl_price, highest, ts_pct, ts_armed, bars_held,
                 checks, triggered, trigger_key, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, ticker, interval_sec, bar, price, macd, signal,
                    tp_price, sl_price, highest, ts_pct,
                    int(bool(ts_armed)), bars_held,
                    json.dumps(checks, ensure_ascii=False) if checks else None,
                    int(bool(triggered)), trigger_key, notes
                )
            )

        conn.commit()


def insert_trade_audit(
    user_id: str,
    ticker: str,
    interval_sec: int,
    bar: int,
    kind: str,           # "BUY" | "SELL"
    reason: str,
    price: float,
    macd: float,
    signal: float,
    entry_price: float | None,
    entry_bar: int | None,
    bars_held: int | None,
    tp: float | None,
    sl: float | None,
    highest: float | None,
    ts_pct: float | None,
    ts_armed: bool | None,
    timestamp: str | None = None,  # ✅ 체결 발생 시각 (실시간 현재 시각)
    bar_time: str | None = None    # ✅ 해당 봉의 시각 (전략 신호 발생 봉)
):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_trades
            (timestamp, bar_time, ticker, interval_sec, bar, type, reason, price, macd, signal,
             entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp if timestamp is not None else now_kst(),  # ✅ 실시간 체결 시각
                bar_time,  # ✅ 봉 시각 (None 가능)
                ticker, interval_sec, bar, kind, reason, price, macd, signal,
                entry_price, entry_bar, bars_held, tp, sl, highest,
                ts_pct, (int(ts_armed) if ts_armed is not None else None)
            )
        )
        conn.commit()


# (선택) 실행 시점 설정 스냅샷
def insert_settings_snapshot(
    user_id: str,
    ticker: str,
    interval_sec: int,
    tp: float, sl: float, ts_pct: float | None,
    signal_gate: bool, threshold: float,
    buy_dict: dict, sell_dict: dict,
    bar_time: str | None = None  # ✅ 해당 봉의 시각
):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO audit_settings
            (timestamp, ticker, interval_sec, tp, sl, ts_pct, signal_gate, threshold, buy_json, sell_json, bar_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_kst(), ticker, interval_sec, tp, sl, ts_pct,
                int(bool(signal_gate)), threshold,
                json.dumps(buy_dict, ensure_ascii=False),
                json.dumps(sell_dict, ensure_ascii=False),
                bar_time
            )
        )
        conn.commit()


# 조회 유틸(뷰/디버깅용)
def fetch_buy_eval(user_id: str, ticker: str | None = None, only_failed=False, limit=500):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        q = """
            SELECT timestamp, ticker, interval_sec, bar, price, macd, signal,
                   have_position, overall_ok, failed_keys, checks, notes
            FROM audit_buy_eval
            WHERE 1=1
        """
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        if only_failed:
            q += " AND overall_ok = 0"
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur.execute(q, params)
        return cur.fetchall()


def fetch_trades_audit(user_id: str, ticker: str | None = None, limit=500):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        q = """
            SELECT timestamp, ticker, interval_sec, bar, type, reason, price,
                   macd, signal, entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed
            FROM audit_trades
            WHERE 1=1
        """
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur.execute(q, params)
        return cur.fetchall()


def has_open_by_orders_volume(user_id: str, ticker: str) -> bool:
    """
    orders 테이블의 체결 레코드로 순포지션(매수-매도 체결 수량)을 계산.
    양수면 '열린 포지션'으로 간주.
    - 🔹 기존에는 status IN ('FILLED','PARTIALLY_FILLED') 로 필터했는데,
      이제 Reconciler가 state 컬럼에 'FILLED','PARTIALLY_FILLED' 를 기록하므로
      state 컬럼 기준으로 변경하는 것이 일관됨.
    """
    from services.init_db import get_db_path
    import sqlite3

    db_path = get_db_path(user_id)
    sql = """
        SELECT COALESCE(SUM(
            CASE WHEN side='BUY'  THEN volume
                 WHEN side='SELL' THEN -volume
                 ELSE 0 END
        ), 0) AS net_qty
        FROM orders
        WHERE user_id = ?
          AND ticker  = ?
          AND status IN ('FILLED','PARTIALLY_FILLED')
    """
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(sql, (user_id, ticker))
        net_qty = cur.fetchone()[0] or 0
        return net_qty > 0
    finally:
        con.close()


def has_open_by_orders(user_id: str, ticker: str) -> bool:
    """
    orders 체결 기록으로 순포지션(매수-매도)을 계산.
    - 수량/사이드/상태 컬럼 이름 편차 자동 감지
    - COALESCE 인자수 안전(항상 2개 이상)
    """
    from services.init_db import get_db_path
    import sqlite3

    def _coalesce_expr(cols: list[str], default: str) -> str:
        # cols가 1개여도 COALESCE(col, default)로 만들어 에러 방지
        if not cols:
            return f"'{default}'"
        if len(cols) == 1:
            return f"COALESCE({cols[0]}, {json.dumps(default)})"
        # 2개 이상이면 마지막에 default를 덧붙여 항상 값이 나오도록
        joined = ",".join(cols + [json.dumps(default)])
        return f"COALESCE({joined})"

    db_path = get_db_path(user_id)
    con = sqlite3.connect(db_path)
    try:
        cols = {r[1].lower() for r in con.execute("PRAGMA table_info(orders)")}

        # --- 수량 후보 (존재하는 것만)
        qty_candidates = [c for c in (
            "filled_qty", "executed_qty", "executed_volume",
            "volume", "qty", "quantity"
        ) if c in cols]
        if not qty_candidates:
            return False

        # 각 후보를 COALESCE(col,0)로 안전화 → 합산
        qty_terms = [f"COALESCE({c},0)" for c in qty_candidates]
        qty_expr = " + ".join(qty_terms)  # ex) COALESCE(volume,0) + COALESCE(filled_qty,0)

        # --- 사이드 컬럼
        side_cols = [c for c in ("side", "ord_side", "order_side", "type", "ord_type") if c in cols]
        side_expr = f"UPPER(TRIM({_coalesce_expr(side_cols, '')}))"

        # --- 상태 컬럼(옵션)
        st_cols = [c for c in ("status", "state") if c in cols]
        status_pred = "1=1"
        if st_cols:
            st_expr = f"UPPER(TRIM({_coalesce_expr(st_cols, '')}))"
            ok_status = ("'FILLED'", "'PARTIALLY_FILLED'", "'COMPLETED'", "'DONE'")
            status_pred = f"{st_expr} IN ({','.join(ok_status)})"

        buy_set  = ("'BUY'", "'BID'")
        sell_set = ("'SELL'", "'ASK'")

        sql = f"""
            SELECT COALESCE(SUM(
                CASE
                    WHEN {side_expr} IN ({','.join(buy_set)})  THEN ({qty_expr})
                    WHEN {side_expr} IN ({','.join(sell_set)}) THEN -({qty_expr})
                    ELSE 0
                END
            ), 0) AS net_qty
            FROM orders
            WHERE user_id = ?
              AND ticker  = ?
              AND {status_pred}
        """
        net_qty = (con.execute(sql, (user_id, ticker)).fetchone() or [0])[0] or 0
        return net_qty > 0
    finally:
        con.close()


import logging
logger = logging.getLogger(__name__)

def get_last_open_buy_order(ticker: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    'orders' 스키마가 환경마다 다른 문제를 회피하기 위해,
    실제 보유 컬럼을 PRAGMA로 확인한 뒤 동적으로 쿼리를 구성한다.
    우선순위:
      1) state/status 가 있으면 ('completed','filled') 필터
      2) 정렬키: executed_at > created_at > ts > timestamp > ROWID
    """
    dbp = get_db_path(user_id)

    def _get_columns(conn) -> set:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(orders)")
        cols = {row[1] for row in cur.fetchall()}
        return cols

    def _fetch_one(conn, sql: str, params: tuple) -> Optional[float]:
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            price = float(row[0]) if row and row[0] is not None else None
            return price
        except Exception as e:
            logger.warning(f"[DB] query failed: {e} | sql={sql} params={params}")
            return None

    try:
        conn = sqlite3.connect(dbp)
        cols = _get_columns(conn)
        logger.info(f"[DB] orders cols = {sorted(cols)}")

        # --- WHERE 절 구성 ---
        where = ["user_id = ?", "ticker = ?", "side = 'BUY'"]
        params = [user_id, ticker]

        # 상태 컬럼: state 또는 status 중 존재하는 것 사용
        status_col = None
        for cand in ("state", "status"):
            if cand in cols:
                status_col = cand
                break
        if status_col:
            where.append(f"{status_col} IN ('completed','filled')")

        where_sql = " AND ".join(where)

        # --- ORDER BY 구성 ---
        order_keys = [c for c in ("executed_at", "created_at", "ts", "timestamp") if c in cols]
        if order_keys:
            order_sql = " , ".join(order_keys) + " DESC, ROWID DESC"
        else:
            order_sql = "ROWID DESC"

        # 1) 상태 컬럼이 있으면 우선 해당 필터로 시도
        sql1 = f"SELECT price FROM orders WHERE {where_sql} ORDER BY {order_sql} LIMIT 1"
        p = _fetch_one(conn, sql1, tuple(params))
        logger.info(f"[DB] last BUY (with status filter={bool(status_col)}) => {p}")
        if p is not None:
            conn.close()
            return {"price": p}

        # 2) 상태 컬럼 없거나 결과 없음 → 상태 필터 제외하고 재시도
        base_where = ["user_id = ?", "ticker = ?", "side = 'BUY'"]
        sql2 = f"SELECT price FROM orders WHERE {' AND '.join(base_where)} ORDER BY {order_sql} LIMIT 1"
        p = _fetch_one(conn, sql2, (user_id, ticker))
        logger.info(f"[DB] last BUY (any state) => {p}")
        conn.close()

        if p is not None:
            return {"price": p}
        logger.info("[DB] no BUY candidate found")
        return None

    except Exception as e:
        logger.warning(f"[DB] get_last_open_buy_order failed: {e}")
        return None


def fetch_inflight_orders(user_id: str | None = None):
    """
    REQUESTED / PARTIALLY_FILLED 상태의 주문을 uuid 포함해서 리턴.
    user_id None이면 전체 조회.
    """
    ensure_schema(user_id or "")
    with get_db(user_id or DEFAULT_USER_ID) as conn:
        cur = conn.cursor()
        if user_id:
            cur.execute("""
                SELECT id, user_id, ticker, side, provider_uuid, state
                FROM orders
                WHERE user_id = ? AND provider_uuid IS NOT NULL
                  AND state IN ('REQUESTED','PARTIALLY_FILLED')
                ORDER BY id DESC
            """, (user_id,))
        else:
            cur.execute("""
                SELECT id, user_id, ticker, side, provider_uuid, state
                FROM orders
                WHERE provider_uuid IS NOT NULL
                  AND state IN ('REQUESTED','PARTIALLY_FILLED')
                ORDER BY id DESC
            """)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "user_id": r[1],
                "ticker": r[2],
                "side": r[3],
                "uuid": r[4],
                "state": r[5],
            } for r in rows
        ]


def update_order_progress(
    user_id: str,
    provider_uuid: str,
    *,
    executed_volume: float,
    avg_price: float | None,
    paid_fee: float | None,
    state: str,                # 'PARTIALLY_FILLED' 등
    executed_at: str | None = None,
):
    """
    부분체결 진행 상황 갱신. 누적 수량·평단·수수료·상태·시각 업데이트.
    """
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders
            SET executed_volume = ?,
                avg_price = ?,
                paid_fee = ?,
                state = ?,
                executed_at = COALESCE(executed_at, ?),
                updated_at = ?
            WHERE user_id = ? AND provider_uuid = ?
        """, (
            executed_volume,
            avg_price,
            paid_fee,
            state,
            executed_at,
            now_kst(),
            user_id,
            provider_uuid
        ))
        conn.commit()


def update_order_completed(
    user_id: str,
    provider_uuid: str,
    *,
    final_state: str,       # 'FILLED' | 'CANCELED' | 'REJECTED'
    executed_volume: float | None = None,
    avg_price: float | None = None,
    paid_fee: float | None = None,
    executed_at: str | None = None,
    canceled_at: str | None = None,
):
    """
    최종 완료/취소/거절로 전환. 필요 시 누적치도 함께 덮어씀.
    """
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders
            SET state = ?,
                executed_volume = COALESCE(?, executed_volume),
                avg_price       = COALESCE(?, avg_price),
                paid_fee        = COALESCE(?, paid_fee),
                executed_at     = COALESCE(executed_at, ?),
                canceled_at     = COALESCE(canceled_at, ?),
                updated_at      = ?
            WHERE user_id = ? AND provider_uuid = ?
        """, (
            final_state,
            executed_volume,
            avg_price,
            paid_fee,
            executed_at,
            canceled_at,
            now_kst(),
            user_id,
            provider_uuid
        ))
        conn.commit()


def fetch_recent_fills(user_id: str, limit: int = 20):
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT timestamp, ticker, side, state, executed_volume, avg_price, paid_fee, requested_at, executed_at
            FROM orders
            WHERE user_id = ?
              AND state IN ('FILLED','PARTIALLY_FILLED','CANCELED','REJECTED','REQUESTED')
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        return cur.fetchall()


# ✅ 최신 주문 상태 조회
def fetch_order_statuses(user_id: str, limit: int = 20, ticker: str | None = None):
    """
    UI/디버깅용 orders 최근 주문 상태 조회.
    [PATCH] ticker 옵션을 추가해서 특정 종목만 보이게 함.
    """
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cur = conn.cursor()

        q = """
            SELECT
                id, timestamp, ticker, side, state,
                status, volume, executed_volume, avg_price, paid_fee,
                provider_uuid, requested_at, executed_at, canceled_at
            FROM orders
            WHERE user_id = ?
        """
        params = [user_id]

        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)

        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur.execute(q, params)
        return cur.fetchall()


def update_account_from_balances(user_id: str, balances: list[dict[str, Any]]):
    """
    Upbit.get_balances() 응답을 기준으로 accounts / account_history 갱신
    - balances 예시:
      [
        {
          "currency": "KRW",
          "balance": "12345.0",
          "locked": "0.0",
          ...
        },
        ...
      ]
    """
    ensure_schema(user_id)

    krw_total = 0.0
    try:
        for b in balances or []:
            if str(b.get("currency", "")).upper() == "KRW":
                bal = float(b.get("balance") or 0.0)
                locked = float(b.get("locked") or 0.0)
                # 필요에 따라 locked 포함/제외 가능. 여기선 "전체 잔고" 기준으로.
                krw_total = bal + locked
                break
    except Exception as e:
        logger.warning(f"[DB] update_account_from_balances parse failed: {e}")

    with get_db(user_id) as conn:
        cur = conn.cursor()
        # 없으면 생성
        cur.execute(
            "INSERT OR IGNORE INTO accounts (user_id, virtual_krw) VALUES (?, ?)",
            (user_id, int(krw_total)),
        )
        # 항상 최신 값으로 덮어쓰기
        cur.execute(
            """
            UPDATE accounts
            SET virtual_krw = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (int(krw_total), now_kst(), user_id),
        )
        conn.commit()

    # 히스토리도 동일하게 누적
    insert_account_history(user_id, int(krw_total))


def update_position_from_balances(user_id: str, ticker: str, balances: list[dict[str, Any]]):
    """
    Upbit.get_balances() 응답으로 특정 ticker(KRW-WLFI 등)의 보유 수량을
    account_positions / position_history 에 반영.
    """
    ensure_schema(user_id)

    sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
    total_coin = 0.0

    try:
        for b in balances or []:
            if str(b.get("currency", "")).upper() == sym:
                bal = float(b.get("balance") or 0.0)
                locked = float(b.get("locked") or 0.0)
                total_coin = bal + locked
                break
    except Exception as e:
        logger.warning(f"[DB] update_position_from_balances parse failed: {e}")

    # 우리 쪽 DB에는 일관되게 'KRW-심볼' 형태로 저장
    market_code = f"KRW-{sym}"
    update_coin_position(user_id, market_code, total_coin)


# ============================================================
# Phase 2: 캔들 데이터 영속성 (Candle Cache)
# ============================================================

def ensure_candle_cache_table(user_id: str):
    """
    캔들 데이터 캐시 테이블 생성
    - 재시작 시에도 기존 히스토리 활용
    - WARMUP 시간 단축 (600개 즉시 확보)
    """
    with get_db(user_id) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candle_cache (
                ticker TEXT NOT NULL,
                interval TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (ticker, interval, timestamp)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_candle_cache_ticker_interval
            ON candle_cache(ticker, interval, timestamp DESC)
        """)
        conn.commit()


def save_candle_cache(user_id: str, ticker: str, interval: str, df):
    """
    캔들 데이터를 DB에 저장 (upsert)
    - df: pandas DataFrame with datetime index
    - 중복 시 최신 데이터로 업데이트
    """
    if df is None or df.empty:
        return

    import logging
    logger = logging.getLogger(__name__)

    try:
        ensure_candle_cache_table(user_id)

        with get_db(user_id) as conn:
            created = now_kst()
            for idx, row in df.iterrows():
                # DataFrame index는 datetime
                ts = idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, "strftime") else str(idx)

                conn.execute("""
                    INSERT OR REPLACE INTO candle_cache
                    (ticker, interval, timestamp, open, high, low, close, volume, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticker, interval, ts,
                    float(row.get("Open", 0)),
                    float(row.get("High", 0)),
                    float(row.get("Low", 0)),
                    float(row.get("Close", 0)),
                    float(row.get("Volume", 0)),
                    created
                ))
            conn.commit()
            logger.info(f"[CACHE-SAVE] {len(df)} candles saved: {ticker}/{interval}")
    except Exception as e:
        logger.warning(f"[CACHE-SAVE] Failed to save candles: {e}")


def load_candle_cache(user_id: str, ticker: str, interval: str, max_length: int = 2000):
    """
    DB에서 캔들 데이터 로드
    - 최신 max_length개 반환
    - DataFrame으로 반환 (datetime index)
    """
    import logging
    import pandas as pd

    logger = logging.getLogger(__name__)

    try:
        ensure_candle_cache_table(user_id)

        with get_db(user_id) as conn:
            cursor = conn.execute("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_cache
                WHERE ticker = ? AND interval = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (ticker, interval, max_length))

            rows = cursor.fetchall()

            if not rows:
                logger.info(f"[CACHE-MISS] No cached data: {ticker}/{interval}")
                return None

            # DataFrame 생성
            df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()

            logger.info(f"[CACHE-HIT] Loaded {len(df)} candles: {ticker}/{interval} | "
                       f"range: {df.index[0]} ~ {df.index[-1]}")
            return df

    except Exception as e:
        logger.warning(f"[CACHE-LOAD] Failed to load candles: {e}")
        return None


# ============================================================
# 데이터 수집 상태 관리
# ============================================================
def update_data_collection_status(
    user_id: str,
    is_collecting: bool = False,
    collected: int = 0,
    target: int = 0,
    progress: float = 0.0,
    estimated_time: float = 0.0,
    message: str = ""
):
    """
    데이터 수집 진행 상황을 DB에 저장
    - is_collecting: 현재 수집 중 여부
    - collected: 수집된 데이터 개수
    - target: 목표 데이터 개수
    - progress: 진행률 (0.0 ~ 1.0)
    - estimated_time: 남은 예상 시간 (초)
    - message: 상태 메시지
    """
    try:
        with get_db(user_id) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO data_collection_status
                (user_id, is_collecting, collected, target, progress, estimated_time, message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME('now', 'localtime'))
                """,
                (user_id, int(is_collecting), collected, target, progress, estimated_time, message)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"[DATA-COLLECTION] Failed to update status: {e}")


def get_data_collection_status(user_id: str) -> Optional[Dict[str, Any]]:
    """
    데이터 수집 진행 상황을 DB에서 조회
    반환: {
        "is_collecting": bool,
        "collected": int,
        "target": int,
        "progress": float,
        "estimated_time": float,
        "message": str,
        "updated_at": str
    }
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.execute(
                """
                SELECT is_collecting, collected, target, progress, estimated_time, message, updated_at
                FROM data_collection_status
                WHERE user_id = ?
                """,
                (user_id,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "is_collecting": bool(row[0]),
                "collected": row[1],
                "target": row[2],
                "progress": row[3],
                "estimated_time": row[4],
                "message": row[5],
                "updated_at": row[6]
            }
    except Exception as e:
        logger.warning(f"[DATA-COLLECTION] Failed to get status: {e}")
        return None


def clear_data_collection_status(user_id: str):
    """
    데이터 수집 상태를 초기화 (수집 완료 시 호출)
    """
    try:
        with get_db(user_id) as conn:
            conn.execute(
                """
                UPDATE data_collection_status
                SET is_collecting = 0, collected = 0, target = 0, progress = 0.0,
                    estimated_time = 0.0, message = '', updated_at = DATETIME('now', 'localtime')
                WHERE user_id = ?
                """,
                (user_id,)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"[DATA-COLLECTION] Failed to clear status: {e}")
