import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import contextmanager

import json
from typing import Optional, Dict, Any
from services.init_db import (
    get_db_path,
    ensure_orders_extended_schema,
    ensure_accounts_locked,
    ensure_account_positions_locked,
    ensure_account_positions_entry_price,
    ensure_engine_status_last_mode,
    ensure_settings_history_schema,  # ✅ P1
)

from config import DEFAULT_USER_ID


def ensure_schema(user_id: str):
    ensure_orders_extended_schema(user_id)
    ensure_accounts_locked(user_id)
    ensure_account_positions_locked(user_id)
    ensure_account_positions_entry_price(user_id)
    ensure_engine_status_last_mode(user_id)
    # ✅ P1 — 설정 정보 History (docs/plans/settings-history)
    ensure_settings_history_schema(user_id)


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
    entry_bar: int | None = None,  # ✅ bars_held 추적용
    meta: str | None = None,  # ✅ 전략 컨텍스트 (JSON)
    settings_history_id: int | None = None,  # ✅ P1 — 거래 → 설정 라벨링
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
                executed_volume, avg_price, paid_fee, updated_at, entry_bar, meta,
                settings_history_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                entry_bar,  # ✅ entry_bar 저장
                meta,  # ✅ 전략 컨텍스트 저장 (JSON)
                settings_history_id,  # ✅ P1 — 거래 → 설정 라벨링
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
                  AND level IN ('INFO', 'BUY', 'SELL', 'WARNING', 'ERROR')
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


def fetch_latest_buy_eval(user_id: str, ticker: str) -> dict | None:
    """
    특정 ticker의 가장 최신 BUY 평가 감사로그 조회
    - audit_buy_eval 테이블에서 timestamp 기준 최신순
    - ✅ WO-1: 옵션 B 컬럼(backfill_*, prev_close) 포함
    """
    query = """
        SELECT timestamp, ticker, interval_sec, bar, price, macd, signal,
               have_position, overall_ok, failed_keys, checks, notes,
               backfill_close, backfill_reason, backfill_at, backfill_type, prev_close
        FROM audit_buy_eval
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            if row:
                return {
                    "timestamp": row[0],
                    "ticker": row[1],
                    "interval_sec": row[2],
                    "bar": row[3],
                    "price": row[4],
                    "macd": row[5],  # EMA 전략에서는 ema_fast
                    "signal": row[6],  # EMA 전략에서는 ema_slow
                    "have_position": row[7],
                    "overall_ok": row[8],
                    "failed_keys": row[9],
                    "checks": row[10],
                    "notes": row[11],
                    # ✅ WO-1 옵션 B
                    "backfill_close": row[12],
                    "backfill_reason": row[13],
                    "backfill_at": row[14],
                    "backfill_type": row[15],
                    "prev_close": row[16],
                }
            return None
    except Exception as e:
        logger.error(f"fetch_latest_buy_eval failed: {e}")
        return None


def fetch_latest_sell_eval(user_id: str, ticker: str) -> dict | None:
    """
    특정 ticker의 가장 최신 SELL 평가 감사로그 조회
    - audit_sell_eval 테이블에서 timestamp 기준 최신순
    - ✅ WO-1: 옵션 B 컬럼(backfill_*, prev_close) 포함
    """
    query = """
        SELECT timestamp, ticker, interval_sec, bar, price, macd, signal,
               tp_price, sl_price, highest, ts_pct, ts_armed, bars_held,
               checks, triggered, trigger_key, notes,
               backfill_close, backfill_reason, backfill_at, backfill_type, prev_close
        FROM audit_sell_eval
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            if row:
                return {
                    "timestamp": row[0],
                    "ticker": row[1],
                    "interval_sec": row[2],
                    "bar": row[3],
                    "price": row[4],
                    "macd": row[5],  # EMA 전략에서는 ema_fast
                    "signal": row[6],  # EMA 전략에서는 ema_slow
                    "tp_price": row[7],
                    "sl_price": row[8],
                    "highest": row[9],
                    "ts_pct": row[10],
                    "ts_armed": row[11],
                    "bars_held": row[12],
                    "checks": row[13],
                    "triggered": row[14],
                    "trigger_key": row[15],
                    "notes": row[16],
                    # ✅ WO-1 옵션 B
                    "backfill_close": row[17],
                    "backfill_reason": row[18],
                    "backfill_at": row[19],
                    "backfill_type": row[20],
                    "prev_close": row[21],
                }
            return None
    except Exception as e:
        logger.error(f"fetch_latest_sell_eval failed: {e}")
        return None


def fetch_latest_trade_audit(user_id: str, ticker: str) -> dict | None:
    """
    특정 ticker의 가장 최신 체결 감사로그 조회
    - audit_trades 테이블에서 timestamp 기준 최신순
    """
    query = """
        SELECT timestamp, ticker, interval_sec, bar, type, reason, price,
               macd, signal, entry_price, entry_bar, bars_held,
               tp, sl, highest, ts_pct, ts_armed
        FROM audit_trades
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            if row:
                return {
                    "timestamp": row[0],
                    "ticker": row[1],
                    "interval_sec": row[2],
                    "bar": row[3],
                    "type": row[4],  # BUY / SELL
                    "reason": row[5],
                    "price": row[6],
                    "macd": row[7],  # EMA 전략에서는 ema_fast
                    "signal": row[8],  # EMA 전략에서는 ema_slow
                    "entry_price": row[9],
                    "entry_bar": row[10],
                    "bars_held": row[11],
                    "tp": row[12],
                    "sl": row[13],
                    "highest": row[14],
                    "ts_pct": row[15],
                    "ts_armed": row[16],
                }
            return None
    except Exception as e:
        logger.error(f"fetch_latest_trade_audit failed: {e}")
        return None


# ✅ 계정 정보
def get_account(user_id):
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT virtual_krw FROM accounts WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_account_locked(user_id):
    """
    accounts.virtual_krw_locked 조회 (Upbit KRW 잠긴 금액).
    스키마가 없거나 행이 없으면 0 반환.
    """
    try:
        ensure_schema(user_id)
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT virtual_krw_locked FROM accounts WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
    except Exception:
        return 0


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
    """
    활성(가용) 코인 수량 조회 — 봇 의사결정 기준.
    locked 수량은 get_coin_balance_locked()로 별도 조회.
    """
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


def get_coin_balance_locked(user_id, ticker):
    """
    잠긴 코인 수량 조회 (미체결 매도 주문 등 참고용 표시).
    스키마/행 부재 시 0 반환.
    """
    try:
        ensure_schema(user_id)
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
            mkt = f"KRW-{sym}"
            cursor.execute(
                """
                SELECT COALESCE(SUM(virtual_coin_locked), 0.0)
                FROM account_positions
                WHERE user_id = ?
                AND UPPER(ticker) IN (?, ?)
            """,
                (user_id, sym, mkt),
            )
            row = cursor.fetchone()
            return row[0] if row else 0.0
    except Exception:
        return 0.0


def update_coin_position(user_id, ticker, virtual_coin, virtual_coin_locked=0.0, entry_price=None):
    """
    포지션 업데이트.
    - virtual_coin: 활성(가용) 코인 — 봇 의사결정 기준
    - virtual_coin_locked: 잠긴 코인 (미체결 매도 주문 등, 참고용)
    - entry_price: Upbit avg_buy_price 캐시 (LIVE 전용). None이면 기존 값 유지.
    TEST 모드는 locked 개념이 없으므로 기본값 0으로 호출하면 됨.
    """
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        if entry_price is None:
            # 기존 entry_price 유지 (잔량만 업데이트)
            cursor.execute(
                """
                INSERT INTO account_positions (user_id, ticker, virtual_coin, virtual_coin_locked, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, ticker) DO UPDATE SET
                    virtual_coin = excluded.virtual_coin,
                    virtual_coin_locked = excluded.virtual_coin_locked,
                    updated_at = excluded.updated_at
            """,
                (user_id, ticker, virtual_coin, virtual_coin_locked, now_kst()),
            )
        else:
            cursor.execute(
                """
                INSERT INTO account_positions (user_id, ticker, virtual_coin, virtual_coin_locked, entry_price, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, ticker) DO UPDATE SET
                    virtual_coin = excluded.virtual_coin,
                    virtual_coin_locked = excluded.virtual_coin_locked,
                    entry_price = excluded.entry_price,
                    updated_at = excluded.updated_at
            """,
                (user_id, ticker, virtual_coin, virtual_coin_locked, float(entry_price), now_kst()),
            )
        conn.commit()
    insert_position_history(user_id, ticker, virtual_coin)


def has_pending_bot_limit_buy(user_id, ticker) -> bool:
    """
    ✅ SP-PI-3: orders 테이블에 미체결 봇 LIMIT BUY 존재 여부.

    D4 결정: state IN ('REQUESTED', 'PARTIALLY_FILLED') 기반.
    schema 상 state / status 컬럼 어느 쪽 존재하든 대응. 어느 쪽도 없으면 False.

    Returns:
        True 면 봇의 LIMIT BUY 가 pending 상태 (미체결) — HTS 오판정 방지 목적으로 사용.
    """
    try:
        import sqlite3 as _sqlite3
        dbp = get_db_path(user_id)
        conn = _sqlite3.connect(dbp)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(orders)")
            cols = {row[1] for row in cur.fetchall()}
            status_col = "state" if "state" in cols else ("status" if "status" in cols else None)
            if status_col is None:
                # 스키마 상 상태 컬럼 없음 → 보수적으로 False (기존 audit_trades 시각 fallback)
                return False
            cur.execute(
                f"SELECT 1 FROM orders "
                f"WHERE user_id=? AND ticker=? AND side='BUY' "
                f"AND {status_col} IN ('REQUESTED','PARTIALLY_FILLED') LIMIT 1",
                (user_id, ticker),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[DB] has_pending_bot_limit_buy failed: {e}")
        return False


def has_recent_bot_buy_for_ticker(user_id, ticker, within_seconds=30):
    """
    B3-잔여: audit_trades에 최근 within_seconds 내 BUY 기록이 있는지 검사.
    HTS 매수 감지 시 봇 BUY와 충돌 방지용.

    ✅ SP-PI-3 (2단 정합성):
        1) orders 테이블 pending LIMIT BUY 있으면 즉시 True — SP6 5봉 대기가
           30초 window 넘어도 봇 매수를 HTS 로 오판정하지 않도록.
        2) 그 외에는 audit_trades 최근 BUY row 를 within_seconds 로 확인 (기존).

    Returns:
        bool: True면 봇 BUY 활동 존재 (pending 또는 최근 체결) → HTS_BUY 마킹 스킵
    """
    # 1) pending LIMIT BUY 확인 (SP6 대응)
    if has_pending_bot_limit_buy(user_id, ticker):
        return True

    # 2) audit_trades 최근 BUY 시각 확인 (체결 완료 후 window)
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT timestamp FROM audit_trades WHERE ticker=? AND type='BUY' ORDER BY id DESC LIMIT 1",
                (ticker,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return False
            from datetime import datetime
            from zoneinfo import ZoneInfo
            ts = datetime.fromisoformat(str(row[0]))
            now = datetime.now(ZoneInfo("Asia/Seoul"))
            return 0 <= (now - ts).total_seconds() <= within_seconds
    except Exception as e:
        logger.warning(f"[DB] has_recent_bot_buy_for_ticker failed: {e}")
        return False


def get_position_entry_price(user_id, ticker):
    """
    account_positions.entry_price (Upbit avg_buy_price 캐시) 조회.
    LIVE Reconciler가 채운 값 → POSITION-SYNC 자동 복구 시 1순위 사용.
    스키마/행 부재 또는 0이면 None 반환.
    """
    try:
        ensure_schema(user_id)
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
            mkt = f"KRW-{sym}"
            cursor.execute(
                """
                SELECT entry_price FROM account_positions
                WHERE user_id = ? AND UPPER(ticker) IN (?, ?)
                LIMIT 1
            """,
                (user_id, sym, mkt),
            )
            row = cursor.fetchone()
            if row and row[0] is not None and float(row[0]) > 0:
                return float(row[0])
            return None
    except Exception:
        return None


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
def set_engine_status(user_id, is_running: bool, last_mode: str | None = None):
    """
    엔진 상태 저장.
    - is_running: 현재 실행 여부
    - last_mode: 마지막 start_engine 시 captured_mode (TEST/LIVE). None이면 기존 값 유지.
    """
    now = now_kst()
    ensure_schema(user_id)
    with get_db(user_id) as conn:
        cursor = conn.cursor()
        if last_mode is None:
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
        else:
            cursor.execute(
                """
                INSERT INTO engine_status (user_id, is_running, last_heartbeat, last_mode)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    is_running = excluded.is_running,
                    last_heartbeat = excluded.last_heartbeat,
                    last_mode = excluded.last_mode
            """,
                (user_id, int(is_running), now, str(last_mode).upper()),
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


def get_trading_paused(user_id: str) -> bool:
    """
    PAUSE-1: users.trading_paused 조회.
    - 컬럼 부재 등 예외 시 False 로 안전 처리 (엔진 정상 매매 유지가 default).
    """
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute("SELECT trading_paused FROM users WHERE username = ?", (user_id,))
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def set_trading_paused(user_id: str, paused: bool) -> None:
    """
    PAUSE-1: users.trading_paused 갱신.
    - users 행이 없으면 INSERT (username 만 채움, 나머지 컬럼은 NULL/기본값).
    """
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, trading_paused)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET trading_paused = excluded.trading_paused
            """,
            (user_id, int(bool(paused))),
        )
        conn.commit()


def get_last_engine_mode(user_id) -> str | None:
    """
    마지막 start_engine 시 captured_mode 조회 (TEST/LIVE).
    스키마/행 부재 시 None 반환.
    """
    try:
        ensure_schema(user_id)
        with get_db(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_mode FROM engine_status WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return str(row[0]).upper()
            return None
    except Exception:
        return None


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
    bar_time: str | None = None,  # ✅ 봉 시각 파라미터 (필수)
    is_backfill: bool = False,    # ✅ WO-1: BACKFILL 재평가 경로 여부
):
    """
    BUY 평가 감사로그 기록.

    WO-1 (JTO-Claim-20260821-001) 옵션 B: 실시간 판정과 BACKFILL 재평가를 컬럼 분리:
      - is_backfill=False (실시간): 실시간 컬럼(price/macd/signal/overall_ok/failed_keys/checks/notes)
        만 INSERT 또는 UPDATE. backfill_* 컬럼은 절대 건드리지 않음 → 실시간 판정 이력 완전 보존.
      - is_backfill=True (BACKFILL 재평가):
          * 기존 레코드 있음 (changed_close 케이스): backfill_close/backfill_reason/backfill_at/
            backfill_type='changed_close'/prev_close 만 UPDATE. 실시간 컬럼은 절대 덮어쓰지 않음.
            → 실시간 매수 시도(action=BUY/overall_ok=1) 흔적 소거 결함(F1) 봉쇄.
          * 기존 레코드 없음 (missing_bar 케이스): 실시간 컬럼 NULL 유지,
            backfill_* 컬럼에만 값 + backfill_type='missing_bar' INSERT.
          * 재-BACKFILL(2회 이상, 옵션 B 보완 1): 컬럼 무한 증식 금지 — 최신값만 유지,
            [AUDIT-UPDATE] 로그에 prev_backfill_close 남김 (관측성 보존).
          * F6 표기(옵션 B 보완 2): backfill_type 으로 변경형/누락형 구분 → audit 뷰어 오독 방지.

    파라미터:
        is_backfill: True 면 BACKFILL 경로, False 면 실시간 경로.
        checks 안의 'reason' 필드는 BACKFILL 경로에서 backfill_reason 컬럼으로 복사됨.
    """
    if bar_time is None:
        raise ValueError("bar_time is required for audit_buy_eval")

    timestamp_now = now_kst()
    import logging
    logger = logging.getLogger(__name__)

    # BACKFILL 경로에서 backfill_reason 계산: checks.reason 우선, 없으면 notes 사용
    _backfill_reason: str | None = None
    if is_backfill:
        if isinstance(checks, dict):
            _backfill_reason = checks.get("reason") or None
        if not _backfill_reason and notes:
            _backfill_reason = notes

    with get_db(user_id) as conn:
        cur = conn.cursor()

        # 1. 기존 레코드 확인 (같은 ticker, bar_time)
        cur.execute(
            """
            SELECT id, price, backfill_close FROM audit_buy_eval
            WHERE ticker=? AND bar_time=?
            """,
            (ticker, bar_time)
        )
        existing = cur.fetchone()

        if is_backfill:
            # ─── BACKFILL 경로 (via_backfill=True) ────────────────────────────
            if existing:
                # (A) changed_close 케이스: 실시간 레코드 존재 → backfill_* 컬럼만 UPDATE
                existing_id, existing_realtime_price, existing_backfill_close = existing
                # prev_close 는 첫 재평가 시만 실시간 price 로 백업 (이후 재-BACKFILL 은 유지)
                cur.execute(
                    "SELECT prev_close FROM audit_buy_eval WHERE id=?", (existing_id,)
                )
                _prev_close_row = cur.fetchone()
                _prev_close_saved = _prev_close_row[0] if _prev_close_row else None
                _new_prev_close = (
                    _prev_close_saved
                    if _prev_close_saved is not None
                    else existing_realtime_price
                )

                # 재-BACKFILL 감지: 기존 backfill_close 가 이미 있으면 관측성 로그
                if existing_backfill_close is not None:
                    logger.info(
                        f"[AUDIT-UPDATE] BUY BACKFILL 재평가 2회+ | ticker={ticker} | "
                        f"bar_time={bar_time} | prev_backfill_close={existing_backfill_close:.4f} | "
                        f"new_backfill_close={price:.4f} | realtime_price={existing_realtime_price}"
                    )
                else:
                    logger.info(
                        f"[AUDIT-UPDATE] BUY BACKFILL 재평가 (changed_close) | ticker={ticker} | "
                        f"bar_time={bar_time} | realtime_price={existing_realtime_price} | "
                        f"backfill_close={price:.4f} | reason={_backfill_reason}"
                    )
                cur.execute(
                    """
                    UPDATE audit_buy_eval
                    SET backfill_close=?, backfill_reason=?, backfill_at=?,
                        backfill_type='changed_close', prev_close=?
                    WHERE id=?
                    """,
                    (price, _backfill_reason, timestamp_now, _new_prev_close, existing_id),
                )
            else:
                # (B) missing_bar 케이스: 실시간 레코드 없음 → 실시간 컬럼 NULL 유지, backfill_* 만 INSERT
                logger.info(
                    f"[AUDIT-INSERT] BUY BACKFILL only (missing_bar) | ticker={ticker} | "
                    f"bar_time={bar_time} | backfill_close={price:.4f} | reason={_backfill_reason}"
                )
                cur.execute(
                    """
                    INSERT INTO audit_buy_eval
                    (timestamp, bar_time, ticker, interval_sec, bar,
                     backfill_close, backfill_reason, backfill_at, backfill_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'missing_bar')
                    """,
                    (timestamp_now, bar_time, ticker, interval_sec, bar,
                     price, _backfill_reason, timestamp_now),
                )
        else:
            # ─── 실시간 경로 (via_backfill=False) ────────────────────────────
            if existing:
                # 실시간 재판정 (예: Progressive Retry 성공 후) → 실시간 컬럼만 UPDATE
                existing_id = existing[0]
                logger.info(
                    f"[AUDIT-UPDATE] BUY 실시간 재판정 | ticker={ticker} | bar_time={bar_time} | "
                    f"old_id={existing_id} | new_price={price:.0f}"
                )
                cur.execute(
                    """
                    UPDATE audit_buy_eval
                    SET timestamp=?, interval_sec=?, bar=?, price=?, macd=?, signal=?,
                        have_position=?, overall_ok=?, failed_keys=?, checks=?, notes=?
                    WHERE id=?
                    """,
                    (
                        timestamp_now, interval_sec, bar, price, macd, signal,
                        int(bool(have_position)), int(bool(overall_ok)),
                        json.dumps(failed_keys, ensure_ascii=False) if failed_keys else None,
                        json.dumps(checks, ensure_ascii=False) if checks else None,
                        notes,
                        existing_id,
                    ),
                )
            else:
                # 실시간 최초 INSERT
                logger.debug(
                    f"[AUDIT-INSERT] BUY 실시간 INSERT | ticker={ticker} | bar_time={bar_time} | "
                    f"price={price:.0f}"
                )
                cur.execute(
                    """
                    INSERT INTO audit_buy_eval
                    (timestamp, bar_time, ticker, interval_sec, bar, price, macd, signal,
                     have_position, overall_ok, failed_keys, checks, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp_now, bar_time, ticker, interval_sec, bar, price, macd, signal,
                        int(bool(have_position)), int(bool(overall_ok)),
                        json.dumps(failed_keys, ensure_ascii=False) if failed_keys else None,
                        json.dumps(checks, ensure_ascii=False) if checks else None,
                        notes,
                    ),
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
    bar_time: str | None = None,  # ✅ 봉 시각 파라미터 (필수)
    is_backfill: bool = False,    # ✅ WO-1: BACKFILL 재평가 경로 여부
):
    """
    SELL 평가 감사로그 기록.

    WO-1 옵션 B: 실시간/BACKFILL 컬럼 분리. `insert_buy_eval` 와 동일 정책.
      - is_backfill=False: 실시간 컬럼(price/macd/.../checks/notes) 만 UPSERT.
      - is_backfill=True + 기존 있음: backfill_* 컬럼만 UPDATE (실시간 SELL 판정 보존).
      - is_backfill=True + 기존 없음: missing_bar 케이스 INSERT.
    """
    if bar_time is None:
        raise ValueError("bar_time is required for audit_sell_eval")

    timestamp_now = now_kst()
    import logging
    logger = logging.getLogger(__name__)

    _backfill_reason: str | None = None
    if is_backfill:
        if isinstance(checks, dict):
            _backfill_reason = checks.get("reason") or None
        if not _backfill_reason and notes:
            _backfill_reason = notes

    with get_db(user_id) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, price, backfill_close FROM audit_sell_eval
            WHERE ticker=? AND bar_time=?
            """,
            (ticker, bar_time)
        )
        existing = cur.fetchone()

        if is_backfill:
            if existing:
                existing_id, existing_realtime_price, existing_backfill_close = existing
                cur.execute(
                    "SELECT prev_close FROM audit_sell_eval WHERE id=?", (existing_id,)
                )
                _prev_close_row = cur.fetchone()
                _prev_close_saved = _prev_close_row[0] if _prev_close_row else None
                _new_prev_close = (
                    _prev_close_saved
                    if _prev_close_saved is not None
                    else existing_realtime_price
                )

                if existing_backfill_close is not None:
                    logger.info(
                        f"[AUDIT-UPDATE] SELL BACKFILL 재평가 2회+ | ticker={ticker} | "
                        f"bar_time={bar_time} | prev_backfill_close={existing_backfill_close:.4f} | "
                        f"new_backfill_close={price:.4f} | realtime_price={existing_realtime_price}"
                    )
                else:
                    logger.info(
                        f"[AUDIT-UPDATE] SELL BACKFILL 재평가 (changed_close) | ticker={ticker} | "
                        f"bar_time={bar_time} | realtime_price={existing_realtime_price} | "
                        f"backfill_close={price:.4f} | reason={_backfill_reason}"
                    )
                cur.execute(
                    """
                    UPDATE audit_sell_eval
                    SET backfill_close=?, backfill_reason=?, backfill_at=?,
                        backfill_type='changed_close', prev_close=?
                    WHERE id=?
                    """,
                    (price, _backfill_reason, timestamp_now, _new_prev_close, existing_id),
                )
            else:
                logger.info(
                    f"[AUDIT-INSERT] SELL BACKFILL only (missing_bar) | ticker={ticker} | "
                    f"bar_time={bar_time} | backfill_close={price:.4f} | reason={_backfill_reason}"
                )
                cur.execute(
                    """
                    INSERT INTO audit_sell_eval
                    (timestamp, bar_time, ticker, interval_sec, bar,
                     backfill_close, backfill_reason, backfill_at, backfill_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'missing_bar')
                    """,
                    (timestamp_now, bar_time, ticker, interval_sec, bar,
                     price, _backfill_reason, timestamp_now),
                )
        else:
            if existing:
                existing_id = existing[0]
                logger.info(
                    f"[AUDIT-UPDATE] SELL 실시간 재판정 | ticker={ticker} | bar_time={bar_time} | "
                    f"old_id={existing_id} | new_price={price:.0f}"
                )
                cur.execute(
                    """
                    UPDATE audit_sell_eval
                    SET timestamp=?, interval_sec=?, bar=?, price=?, macd=?, signal=?,
                        tp_price=?, sl_price=?, highest=?, ts_pct=?, ts_armed=?,
                        bars_held=?, checks=?, triggered=?, trigger_key=?, notes=?
                    WHERE id=?
                    """,
                    (
                        timestamp_now, interval_sec, bar, price, macd, signal,
                        tp_price, sl_price, highest, ts_pct, int(bool(ts_armed)),
                        bars_held,
                        json.dumps(checks, ensure_ascii=False) if checks else None,
                        int(bool(triggered)), trigger_key, notes,
                        existing_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO audit_sell_eval
                    (timestamp, bar_time, ticker, interval_sec, bar, price, macd, signal,
                     tp_price, sl_price, highest, ts_pct, ts_armed, bars_held,
                     checks, triggered, trigger_key, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp_now, bar_time, ticker, interval_sec, bar, price, macd, signal,
                        tp_price, sl_price, highest, ts_pct,
                        int(bool(ts_armed)), bars_held,
                        json.dumps(checks, ensure_ascii=False) if checks else None,
                        int(bool(triggered)), trigger_key, notes,
                    ),
                )

        conn.commit()


def annotate_buy_eval_blocked(
    user_id: str,
    ticker: str,
    bar_time: str,
    block_reason: str,
) -> bool:
    """
    WO-1 선행 1: 매수 게이트 차단 시 audit_buy_eval 의 checks JSON 에 blocked 정보를 추가한다.

    실시간 판정 컬럼(price/overall_ok/failed_keys/notes 등)은 그대로 보존하고,
    checks 안에만 `blocked=True`, `block_reason=<사유>`, `blocked_at=<ISO>` 필드를 추가한다.
    옵션 B 정신(실시간 판정 이력 보존) 준수.

    반환: 대상 행이 있고 UPDATE 성공 시 True, 대상 행 부재 시 False.
    """
    timestamp_now = now_kst()
    import logging
    _logger = logging.getLogger(__name__)

    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, checks FROM audit_buy_eval WHERE ticker=? AND bar_time=?",
                (ticker, bar_time),
            )
            row = cur.fetchone()
            if not row:
                _logger.warning(
                    f"[POLLUTED-AUDIT] 대상 행 없음 (annotate 스킵) | "
                    f"ticker={ticker} bar_time={bar_time}"
                )
                return False
            existing_id, existing_checks_raw = row
            try:
                checks_dict = json.loads(existing_checks_raw) if existing_checks_raw else {}
            except Exception:
                checks_dict = {}
            if not isinstance(checks_dict, dict):
                checks_dict = {}
            checks_dict["blocked"] = True
            checks_dict["block_reason"] = block_reason
            checks_dict["blocked_at"] = timestamp_now
            cur.execute(
                "UPDATE audit_buy_eval SET checks=? WHERE id=?",
                (json.dumps(checks_dict, ensure_ascii=False), existing_id),
            )
            conn.commit()
            _logger.info(
                f"[POLLUTED-AUDIT] annotate OK | ticker={ticker} bar_time={bar_time} "
                f"reason={block_reason} id={existing_id}"
            )
            return True
    except Exception as e:
        _logger.warning(f"[POLLUTED-AUDIT] annotate 실패 | {e}")
        return False


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
    bar_time: str | None = None,   # ✅ 해당 봉의 시각 (전략 신호 발생 봉)
    settings_history_id: int | None = None,  # ✅ P1 — 거래 → 설정 라벨링
):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_trades
            (timestamp, bar_time, ticker, interval_sec, bar, type, reason, price, macd, signal,
             entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed,
             settings_history_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp if timestamp is not None else now_kst(),  # ✅ 실시간 체결 시각
                bar_time,  # ✅ 봉 시각 (None 가능)
                ticker, interval_sec, bar, kind, reason, price, macd, signal,
                entry_price, entry_bar, bars_held, tp, sl, highest,
                ts_pct, (int(ts_armed) if ts_armed is not None else None),
                settings_history_id,  # ✅ P1
            )
        )
        conn.commit()


# (선택) 실행 시점 설정 스냅샷
def fetch_latest_audit_settings(user_id: str, ticker: str | None = None) -> Optional[Dict[str, Any]]:
    """
    ✅ SP1 — 엔진이 실시간으로 사용 중인 conditions 의 최신 스냅샷 1건 조회.

    audit_settings 는 1분당 1회 strategy 객체의 현재 임계값을 적재하므로
    이 row 가 "엔진이 실제 적용 중인 conditions" 를 반영.
    """
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            if ticker:
                cur.execute(
                    "SELECT timestamp, ticker, interval_sec, tp, sl, ts_pct, "
                    "       signal_gate, threshold, buy_json, sell_json, bar_time "
                    "FROM audit_settings "
                    "WHERE ticker=? "
                    "ORDER BY id DESC LIMIT 1",
                    (ticker,),
                )
            else:
                cur.execute(
                    "SELECT timestamp, ticker, interval_sec, tp, sl, ts_pct, "
                    "       signal_gate, threshold, buy_json, sell_json, bar_time "
                    "FROM audit_settings "
                    "ORDER BY id DESC LIMIT 1"
                )
            row = cur.fetchone()
        if not row:
            return None
        cols = ["timestamp", "ticker", "interval_sec", "tp", "sl", "ts_pct",
                "signal_gate", "threshold", "buy_json", "sell_json", "bar_time"]
        result = dict(zip(cols, row))
        # JSON 파싱
        for k in ("buy_json", "sell_json"):
            v = result.get(k)
            if isinstance(v, str):
                try:
                    result[k] = json.loads(v)
                except Exception:
                    pass
        return result
    except Exception:
        return None


def insert_settings_snapshot(
    user_id: str,
    ticker: str,
    interval_sec: int,
    tp: float, sl: float, ts_pct: float | None,
    signal_gate: bool, threshold: float,
    buy_dict: dict, sell_dict: dict,
    bar_time: str | None = None  # ✅ 해당 봉의 시각
):
    """
    ✅ 2026-08-05 UPSERT 전환:
    기존 INSERT OR IGNORE 로직은 같은 bar_time 에 이미 스냅샷이 있으면 새 값을 무시.
    그 결과 hot-reload 로 파일이 변경돼도 같은 분 안에는 audit_settings 가 이전 값
    으로 유지되어 대시보드가 최대 60초 동안 "엔진 ≠ UI 저장값" 어긋남 표시.
    UPSERT (ON CONFLICT DO UPDATE) 로 전환하여 hot-reload 즉시 스냅샷이 기존
    레코드를 갱신하도록 함 (bar_time 규약 유지).
    """
    with get_db(user_id) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_settings
            (timestamp, ticker, interval_sec, tp, sl, ts_pct, signal_gate, threshold, buy_json, sell_json, bar_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, interval_sec, bar_time) DO UPDATE SET
                timestamp = excluded.timestamp,
                tp = excluded.tp,
                sl = excluded.sl,
                ts_pct = excluded.ts_pct,
                signal_gate = excluded.signal_gate,
                threshold = excluded.threshold,
                buy_json = excluded.buy_json,
                sell_json = excluded.sell_json
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
    """
    B13: audit_buy_eval 조회.
    - 정렬 키를 timestamp → COALESCE(bar_time, timestamp)로 변경.
      timestamp는 INSERT/UPDATE 시각이라 BACKFILL 재평가로 흔들릴 수 있음.
      bar_time은 봉의 실제 시각으로 안정적 + UNIQUE(ticker, bar_time) 제약과 일관됨.
    - 동순위 tie-breaker는 id DESC (최신 UPDATE 우선).
    """
    with get_db(user_id) as conn:
        cur = conn.cursor()
        q = """
            SELECT timestamp, bar_time, ticker, interval_sec, bar, price, macd, signal,
                   have_position, overall_ok, failed_keys, checks, notes,
                   backfill_close, backfill_reason, backfill_at, backfill_type, prev_close
            FROM audit_buy_eval
            WHERE 1=1
        """
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        if only_failed:
            # B13 보강: BUY_SIGNAL(overall_ok=1)은 진단의 핵심 데이터이므로 항상 포함.
            #   only_failed=True는 "차단 사유 + 신호 발동 모두 표시"로 의미 통합.
            #   (이전엔 overall_ok=0만 반환하여 BUY_SIGNAL 14건이 사용자 화면에서 사라짐)
            q += " AND overall_ok IN (0, 1)"
        # B13: bar_time 기준 정렬 (UPDATE 시각 흔들림 방지, bar 번호 누락 가시화)
        q += " ORDER BY COALESCE(bar_time, timestamp) DESC, id DESC LIMIT ?"
        params.append(limit)
        cur.execute(q, params)
        return cur.fetchall()


def fetch_trades_audit(user_id: str, ticker: str | None = None, limit=500):
    with get_db(user_id) as conn:
        cur = conn.cursor()
        q = """
            SELECT timestamp, bar_time, ticker, interval_sec, bar, type, reason, price,
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

    def _fetch_one(conn, sql: str, params: tuple, cols: set) -> Optional[Dict[str, Any]]:
        """price, entry_bar, entry_ts_iso를 함께 조회 (SP-PI-1)"""
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None

            result = {}
            # SELECT 순서: price, [entry_bar], [entry_ts_iso]
            idx = 0
            if row[idx] is not None:
                result["price"] = float(row[idx])
            idx += 1
            if "entry_bar" in cols:
                if len(row) > idx and row[idx] is not None:
                    result["entry_bar"] = int(row[idx])
                idx += 1
            # ✅ SP-PI-1: 진입 시각 복원 — orders 테이블에서 timestamp 계열 컬럼 반환
            if len(row) > idx and row[idx] is not None:
                result["entry_ts_iso"] = str(row[idx])

            return result if result else None
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
        # ✅ LIVE 모드: state='CANCELED'이지만 executed_volume > 0인 경우 포함 (즉시 체결된 시장가 주문)
        status_col = None
        for cand in ("state", "status"):
            if cand in cols:
                status_col = cand
                break

        if status_col:
            # ✅ 실제 체결된 주문만 필터링:
            # 1) state/status IN ('completed', 'filled', 'FILLED')
            # 2) OR (state='CANCELED' AND executed_volume > 0)  ← Upbit 즉시 체결 케이스
            if "executed_volume" in cols:
                where.append(
                    f"({status_col} IN ('completed', 'filled', 'FILLED') "
                    f"OR ({status_col} = 'CANCELED' AND executed_volume > 0))"
                )
            else:
                where.append(f"{status_col} IN ('completed', 'filled', 'FILLED')")

        where_sql = " AND ".join(where)

        # --- ORDER BY 구성 ---
        order_keys = [c for c in ("executed_at", "created_at", "ts", "timestamp") if c in cols]
        if order_keys:
            order_sql = " , ".join(order_keys) + " DESC, ROWID DESC"
        else:
            order_sql = "ROWID DESC"

        # ✅ avg_price (실제 체결가) 우선, 없으면 price (주문 가격)
        # ✅ entry_bar 컬럼이 있으면 함께 조회
        if "avg_price" in cols:
            select_cols = "COALESCE(avg_price, price) as price"
        else:
            select_cols = "price"

        if "entry_bar" in cols:
            select_cols += ", entry_bar"

        # ✅ SP-PI-1: 진입 시각 복원 — 우선순위 executed_at > created_at > ts > timestamp
        ts_col_pick = None
        for cand in ("executed_at", "created_at", "ts", "timestamp"):
            if cand in cols:
                ts_col_pick = cand
                break
        if ts_col_pick:
            select_cols += f", {ts_col_pick}"

        # ✅ B1 해결: 청산 검증 헬퍼 — 마지막 BUY 이후 SELL이 있으면 청산된 것으로 간주
        def _last_buy_closed_by_later_sell() -> bool:
            try:
                cur = conn.cursor()
                if status_col:
                    state_filter = f"{status_col} IN ('completed','filled','FILLED')"
                    cur.execute(
                        f"SELECT MAX(ROWID) FROM orders WHERE user_id=? AND ticker=? AND side='BUY' AND {state_filter}",
                        (user_id, ticker),
                    )
                    buy_rowid = (cur.fetchone() or (None,))[0]
                    cur.execute(
                        f"SELECT MAX(ROWID) FROM orders WHERE user_id=? AND ticker=? AND side='SELL' AND {state_filter}",
                        (user_id, ticker),
                    )
                    sell_rowid = (cur.fetchone() or (None,))[0]
                else:
                    cur.execute("SELECT MAX(ROWID) FROM orders WHERE user_id=? AND ticker=? AND side='BUY'", (user_id, ticker))
                    buy_rowid = (cur.fetchone() or (None,))[0]
                    cur.execute("SELECT MAX(ROWID) FROM orders WHERE user_id=? AND ticker=? AND side='SELL'", (user_id, ticker))
                    sell_rowid = (cur.fetchone() or (None,))[0]
                return (buy_rowid is not None and sell_rowid is not None and sell_rowid > buy_rowid)
            except Exception as e:
                logger.warning(f"[DB] _last_buy_closed_by_later_sell check failed: {e}")
                # 검증 실패 시 보수적으로 청산되었다고 간주 → 가짜 진입가 차용 차단
                return True

        # 1) 상태 컬럼이 있으면 우선 해당 필터로 시도
        sql1 = f"SELECT {select_cols} FROM orders WHERE {where_sql} ORDER BY {order_sql} LIMIT 1"
        result = _fetch_one(conn, sql1, tuple(params), cols)
        logger.info(f"[DB] last BUY (with status filter={bool(status_col)}) => {result}")
        if result is not None:
            if _last_buy_closed_by_later_sell():
                logger.warning(
                    "[DB] last BUY already closed by later SELL → returning None "
                    "(B1: 가짜 진입가 차용 방지)"
                )
                conn.close()
                return None
            conn.close()
            return result

        # 2) 상태 컬럼 없거나 결과 없음 → 상태 필터 제외하고 재시도
        base_where = ["user_id = ?", "ticker = ?", "side = 'BUY'"]
        sql2 = f"SELECT {select_cols} FROM orders WHERE {' AND '.join(base_where)} ORDER BY {order_sql} LIMIT 1"
        result = _fetch_one(conn, sql2, (user_id, ticker), cols)
        logger.info(f"[DB] last BUY (any state) => {result}")

        if result is not None and _last_buy_closed_by_later_sell():
            logger.warning(
                "[DB] last BUY already closed by later SELL → returning None (B1)"
            )
            conn.close()
            return None
        conn.close()

        if result is not None:
            return result
        logger.info("[DB] no BUY candidate found")
        return None

    except Exception as e:
        logger.warning(f"[DB] get_last_open_buy_order failed: {e}")
        return None


def estimate_bars_held_from_audit(user_id: str, ticker: str) -> int:
    """
    bars_held 간단하게 계산: 최근 BUY 이후 SELL 평가 개수 세기

    로직 (간단하게):
    1. audit_trades에서 최근 BUY timestamp 조회
    2. audit_sell_eval에서 해당 시각 이후 레코드 개수 COUNT
    3. 그게 bars_held!

    Returns:
        bars_held 개수 (0 이상)
    """
    try:
        with get_db(user_id) as conn:
            cursor = conn.cursor()

            # 1. audit_trades에서 최근 BUY timestamp 조회
            cursor.execute("""
                SELECT timestamp FROM audit_trades
                WHERE ticker = ? AND type = 'BUY'
                ORDER BY id DESC LIMIT 1
            """, (ticker,))

            buy_row = cursor.fetchone()
            if not buy_row:
                logger.warning(f"[BARS_HELD] audit_trades에 BUY 기록 없음 → 0")
                return 0

            buy_timestamp = buy_row[0]

            # 2. BUY 이후 SELL 평가 개수 세기
            cursor.execute("""
                SELECT COUNT(*) FROM audit_sell_eval
                WHERE ticker = ? AND timestamp >= ?
            """, (ticker, buy_timestamp))

            count = cursor.fetchone()[0]
            logger.info(f"[BARS_HELD] BUY={buy_timestamp} 이후 SELL 평가 {count}개 → bars_held={count}")
            return count

    except Exception as e:
        logger.error(f"[BARS_HELD] 계산 실패: {e}")
        return 0


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
                SELECT id, user_id, ticker, side, provider_uuid, state, meta
                FROM orders
                WHERE user_id = ? AND provider_uuid IS NOT NULL
                  AND state IN ('REQUESTED','PARTIALLY_FILLED')
                ORDER BY id DESC
            """, (user_id,))
        else:
            cur.execute("""
                SELECT id, user_id, ticker, side, provider_uuid, state, meta
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
                "meta": r[6],  # ✅ 전략 컨텍스트 (JSON)
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
    current_krw: float | None = None,  # ✅ 체결 후 잔고 (대시보드 표시용)
    current_coin: float | None = None,  # ✅ 체결 후 코인 보유량 (대시보드 표시용)
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
                current_krw     = COALESCE(?, current_krw),
                current_coin    = COALESCE(?, current_coin),
                updated_at      = ?
            WHERE user_id = ? AND provider_uuid = ?
        """, (
            final_state,
            executed_volume,
            avg_price,
            paid_fee,
            executed_at,
            canceled_at,
            current_krw,
            current_coin,
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

    krw_active = 0.0
    krw_locked = 0.0
    try:
        for b in balances or []:
            if str(b.get("currency", "")).upper() == "KRW":
                krw_active = float(b.get("balance") or 0.0)
                krw_locked = float(b.get("locked") or 0.0)
                break
    except Exception as e:
        logger.warning(f"[DB] update_account_from_balances parse failed: {e}")

    with get_db(user_id) as conn:
        cur = conn.cursor()
        # 없으면 생성 (활성 KRW만 저장; locked는 별도 컬럼)
        cur.execute(
            "INSERT OR IGNORE INTO accounts (user_id, virtual_krw, virtual_krw_locked) VALUES (?, ?, ?)",
            (user_id, int(krw_active), int(krw_locked)),
        )
        # 항상 최신 값으로 덮어쓰기 (활성/Lock 분리)
        cur.execute(
            """
            UPDATE accounts
            SET virtual_krw = ?, virtual_krw_locked = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (int(krw_active), int(krw_locked), now_kst(), user_id),
        )
        conn.commit()

    # 히스토리는 총 KRW(active + locked) 기준으로 누적
    insert_account_history(user_id, int(krw_active + krw_locked))


def update_position_from_balances(user_id: str, ticker: str, balances: list[dict[str, Any]]):
    """
    Upbit.get_balances() 응답으로 특정 ticker의 보유 수량 + 평균매수가를
    account_positions에 반영.

    봇 철학: 활성/잠금 분리 + Upbit avg_buy_price를 진입가 캐시로 저장 (B1 해결).
    """
    ensure_schema(user_id)

    sym = (ticker.split("-")[1] if "-" in ticker else ticker).strip().upper()
    coin_active = 0.0
    coin_locked = 0.0
    avg_buy_price = 0.0

    try:
        for b in balances or []:
            if str(b.get("currency", "")).upper() == sym:
                coin_active = float(b.get("balance") or 0.0)
                coin_locked = float(b.get("locked") or 0.0)
                avg_buy_price = float(b.get("avg_buy_price") or 0.0)
                break
    except Exception as e:
        logger.warning(f"[DB] update_position_from_balances parse failed: {e}")

    market_code = f"KRW-{sym}"
    # 보유량이 0이면 진입가 무의미 → 0 저장. 양수면 avg_buy_price 캐시.
    ep = avg_buy_price if (coin_active + coin_locked) > 0 and avg_buy_price > 0 else 0.0
    update_coin_position(user_id, market_code, coin_active, coin_locked, entry_price=ep)


def sync_all_positions_from_balances(user_id: str, balances: list[dict[str, Any]]):
    """
    전체 포트폴리오를 Upbit API 응답과 동기화 (Issue #18 해결)
    - 실제 보유 코인: 수량 업데이트
    - DB에만 있는 코인: 0으로 설정
    - 5분마다 실행 권장 (Reconciler _periodic_balance_sync에서 호출)

    배경:
    - update_position_from_balances()는 특정 ticker만 업데이트
    - 매도 후 다른 코인 거래 시 이전 코인이 DB에 남아있는 문제 발생
    - KRW-PEPE 8억개가 매도 후에도 DB에 남아있던 사례 (2026-05-14)
    """
    ensure_schema(user_id)

    # 1. 실제 보유 코인 업데이트 — 활성/잠금 분리 저장
    real_currencies = set()
    try:
        for b in balances or []:
            currency = str(b.get("currency", "")).strip().upper()
            if currency == "KRW" or not currency:
                continue

            coin_active = float(b.get("balance", 0))
            coin_locked = float(b.get("locked", 0))
            avg_buy_price = float(b.get("avg_buy_price") or 0.0)

            ticker = f"KRW-{currency}"
            ep = avg_buy_price if (coin_active + coin_locked) > 0 and avg_buy_price > 0 else 0.0
            update_coin_position(user_id, ticker, coin_active, coin_locked, entry_price=ep)
            real_currencies.add(currency)

    except Exception as e:
        logger.warning(f"[DB] sync_all_positions real balances failed: {e}")

    # 2. DB에는 있지만 실제로는 없는 코인 → 활성/잠금 모두 0으로 설정
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT ticker FROM account_positions WHERE user_id = ?",
                (user_id,)
            )
            db_tickers = [row[0] for row in cur.fetchall()]

        for ticker in db_tickers:
            if not ticker or not ticker.startswith("KRW-"):
                continue

            # ticker에서 currency 추출 (KRW-PEPE → PEPE)
            parts = ticker.split("-")
            if len(parts) != 2:
                continue

            currency = parts[1].strip().upper()

            # 실제 보유하지 않으면 활성/잠금/진입가 모두 0으로 설정
            if currency not in real_currencies:
                update_coin_position(user_id, ticker, 0.0, 0.0, entry_price=0.0)
                logger.info(f"[DB] sync_all_positions cleared: {ticker} → active=0, locked=0, entry_price=0")

    except Exception as e:
        logger.warning(f"[DB] sync_all_positions clear stale positions failed: {e}")


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


# ============================================================================
# HTS 매수 감지 지원 함수 (Issue #17)
# ============================================================================

def get_position_qty(user_id: str, ticker: str) -> float:
    """
    특정 ticker의 현재 보유 수량 조회

    Returns:
        float: 보유 수량 (미보유 시 0.0)

    Usage:
        prev_qty = get_position_qty(user_id, "KRW-ZRO")
    """
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT virtual_coin
                FROM account_positions
                WHERE user_id = ? AND ticker = ?
                """,
                (user_id, ticker)
            )
            row = cur.fetchone()
            return float(row[0]) if row else 0.0
    except Exception as e:
        logger.warning(f"[HTS-DETECT] Failed to get position qty: {e}")
        return 0.0


def get_position_meta(user_id: str, ticker: str) -> Dict[str, Any]:
    """
    특정 ticker의 포지션 메타데이터 조회

    Returns:
        dict: 메타데이터 (없으면 빈 dict)

    Usage:
        meta = get_position_meta(user_id, "KRW-ZRO")
        is_hts = meta.get('hts_buy', False)
    """
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT meta
                FROM account_positions
                WHERE user_id = ? AND ticker = ?
                """,
                (user_id, ticker)
            )
            row = cur.fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return {}
    except Exception as e:
        logger.warning(f"[HTS-DETECT] Failed to get position meta: {e}")
        return {}


def update_position_meta(user_id: str, ticker: str, meta: Dict[str, Any]):
    """
    특정 ticker의 포지션 메타데이터 업데이트

    Args:
        meta: 메타데이터 dict (예: {"hts_buy": True})

    Usage:
        update_position_meta(user_id, "KRW-ZRO", {"hts_buy": True})
    """
    try:
        with get_db(user_id) as conn:
            cur = conn.cursor()
            meta_json = json.dumps(meta, ensure_ascii=False)

            # UPSERT: 레코드 없으면 INSERT, 있으면 UPDATE
            cur.execute(
                """
                INSERT INTO account_positions (user_id, ticker, virtual_coin, meta, updated_at)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(user_id, ticker) DO UPDATE SET
                    meta = excluded.meta,
                    updated_at = excluded.updated_at
                """,
                (user_id, ticker, meta_json, now_kst())
            )
            conn.commit()
    except Exception as e:
        logger.error(f"[HTS-DETECT] Failed to update position meta: {e}")


def mark_position_as_hts_buy(user_id: str, ticker: str):
    """
    포지션에 HTS 매수 플래그 설정

    Usage:
        mark_position_as_hts_buy(user_id, "KRW-ZRO")

    Note:
        - 기존 메타데이터에 hts_buy=True 추가
        - force_buy(사이트 수동매수)와 구분됨
    """
    try:
        # 기존 메타데이터 조회
        meta = get_position_meta(user_id, ticker)

        # hts_buy 플래그 추가
        meta['hts_buy'] = True

        # 업데이트
        update_position_meta(user_id, ticker, meta)

        logger.info(f"🔔 [HTS-DETECT] HTS 매수 플래그 설정 | ticker={ticker}")
    except Exception as e:
        logger.error(f"[HTS-DETECT] Failed to mark position as HTS buy: {e}")
