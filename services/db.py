import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import contextmanager


DB_PATH = "tradebot.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


# ✅ 시간 생성 함수 (KST 기준)
def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


# ✅ 사용자 정보
def save_user(username: str, display_name: str, virtual_krw: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, display_name, virtual_krw, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                display_name = excluded.display_name,
                virtual_krw = excluded.virtual_krw,
                updated_at = excluded.updated_at;
        """,
            (username, display_name, virtual_krw, now_kst()),
        )
        conn.commit()


def get_user(username: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT display_name, virtual_krw, updated_at FROM users WHERE username=?",
            (username,),
        )
        return cursor.fetchone()


# ✅ 주문
def insert_order(user_id, ticker, side, price, volume, status):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (user_id, now_kst(), ticker, side, price, volume, status),
        )
        conn.commit()


def fetch_recent_orders(user_id, limit=10):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, ticker, side, price, volume, status
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """,
            (user_id, limit),
        )
        return cursor.fetchall()


def delete_orders():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM orders;
        """
        )
        deleted = cursor.rowcount
        conn.commit()

    print(f"🧹 Deleted {deleted} rows from orders table.")


# ✅ 로그
def insert_log(user_id: str, level: str, message: str):
    with get_db() as conn:
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
    with get_db() as conn:
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
    """
    logs 테이블에서 level='INFO'이고 이모지로 시작하는 상태 메시지 중 가장 최근 항목 1개 반환
    """
    status_prefixes = ("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄", "❌", "🚨")

    with get_db() as conn:
        cursor = conn.cursor()
        # 이모지로 시작하는 메시지만 필터링
        emoji_conditions = " OR ".join(
            [f"message LIKE '{prefix}%'" for prefix in status_prefixes]
        )
        try:
            # cursor.execute(
            #     f"""
            #     SELECT timestamp, message FROM logs
            #     WHERE user_id = ? AND level = 'INFO' AND ({emoji_conditions})
            #     ORDER BY timestamp DESC
            #     LIMIT 1
            #     """,
            #     (user_id,),
            # )
            cursor.execute(
                f"""
                SELECT timestamp, message FROM logs
                WHERE user_id = ? AND (level = 'INFO' OR level = 'BUY' OR level = 'SELL')
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                ts, message = row
                formatted_ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
                return f"[{formatted_ts}] {message}"
            else:
                return "❌ 상태 로그 없음"
        except Exception as e:
            return f"❌ DB 조회 오류: {e}"
        finally:
            conn.close()


def delete_old_logs():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM logs
            WHERE timestamp < DATETIME('now', 'start of day', 'localtime');
        """
        )
        deleted = cursor.rowcount
        conn.commit()

    print(f"🧹 Deleted {deleted} old logs.")


def fetch_latest_log_signal(user_id: str, ticker: str) -> dict | None:
    """
    가장 최신의 'LOG' 레벨 로그에서 price, cross, macd, signal 정보를 파싱해 반환
    - message 예시: "2025-07-01 20:47:00 | price=220.5 | cross=Neutral | macd=0.02563 | signal=0.03851 | bar=495"
    """
    query = """
        SELECT message
        FROM logs
        WHERE user_id = ? AND level = 'LOG' AND message LIKE '%price=%'
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if row:
                message = row[0]
                try:
                    parts = message.split(" | ")
                    time_str = parts[0].strip()
                    price = parts[1].split("=")[1].strip()
                    cross = parts[2].split("=")[1].strip()
                    macd = parts[3].split("=")[1].strip()
                    signal = parts[4].split("=")[1].strip()

                    return {
                        "시간": time_str,
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT virtual_krw FROM accounts WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def create_or_init_account(user_id, init_krw=1_000_000):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO accounts (user_id, virtual_krw) VALUES (?, ?)",
            (user_id, init_krw),
        )
        conn.commit()


def update_account(user_id, virtual_krw):
    virtual_krw = int(virtual_krw)  # ✅ 정수로 변환

    with get_db() as conn:
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT virtual_coin
            FROM account_positions
            WHERE user_id = ? AND ticker = ?
        """,
            (user_id, ticker),
        )
        row = cursor.fetchone()
        return row[0] if row else 0.0


def update_coin_position(user_id, ticker, virtual_coin):
    with get_db() as conn:
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
    with get_db() as conn:
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
    with get_db() as conn:
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
    with get_db() as conn:
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_running FROM engine_status WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])


# ✅ Thread 상태
def set_thread_status(user_id, is_thread_running: bool):
    now = now_kst()
    with get_db() as conn:
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_thread_running FROM thread_status WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])


def get_initial_krw(user_id: str) -> float:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT virtual_krw FROM users WHERE username = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None
