import sqlite3
import os


DB_PREFIX = "tradebot"


def get_db_path(user_id):
    return f"{DB_PREFIX}_{user_id}.db"


def init_db_if_needed(user_id):
    if not os.path.exists(get_db_path(user_id)):
        print(f"✅ intialize_db : {get_db_path(user_id)}")
        initialize_db(user_id)


def reset_db(user_id):
    """기존 DB를 초기화하고 테이블을 재생성"""
    conn = sqlite3.connect(get_db_path(user_id))
    cursor = conn.cursor()

    # ✅ 기존 테이블 삭제
    cursor.execute("DROP TABLE IF EXISTS users;")
    cursor.execute("DROP TABLE IF EXISTS orders;")
    cursor.execute("DROP TABLE IF EXISTS logs;")
    cursor.execute("DROP TABLE IF EXISTS accounts;")
    cursor.execute("DROP TABLE IF EXISTS account_positions;")
    cursor.execute("DROP TABLE IF EXISTS account_history;")
    cursor.execute("DROP TABLE IF EXISTS position_history;")
    cursor.execute("DROP TABLE IF EXISTS engine_status;")
    cursor.execute("DROP TABLE IF EXISTS thread_status;")

    conn.commit()
    conn.close()

    print("🧹 모든 테이블 삭제 완료.")
    initialize_db(user_id)


def initialize_db(user_id):
    """DB 테이블 초기 생성"""
    conn = sqlite3.connect(get_db_path(user_id))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            display_name TEXT,
            virtual_krw INTEGER,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker TEXT,
            side TEXT,
            price REAL,
            volume REAL,
            status TEXT,
            current_krw INTEGER DEFAULT 0,      -- ✅ 현재 KRW 잔고
            current_coin REAL DEFAULT 0.0,      -- ✅ 현재 보유 코인
            profit_krw INTEGER DEFAULT 0        -- ✅ 매도 수익 (매수 시 0)
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            level TEXT,
            message TEXT
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            virtual_krw INTEGER DEFAULT 1000000,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS account_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            virtual_krw INTEGER
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS account_positions (
            user_id TEXT,
            ticker TEXT,
            virtual_coin REAL DEFAULT 0,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime')),
            PRIMARY KEY (user_id, ticker)
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS position_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker TEXT,
            virtual_coin REAL
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS engine_status (
            user_id TEXT PRIMARY KEY,
            is_running INTEGER DEFAULT 0,
            last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_status (
            user_id TEXT PRIMARY KEY,
            is_thread_running INTEGER DEFAULT 0,
            last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
        """
    )

    conn.commit()
    conn.close()

    print(f"✅ DB 초기화 완료: {get_db_path(user_id)}")
