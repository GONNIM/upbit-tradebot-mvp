import sqlite3
import os


def init_db_if_needed(DB_PATH):
    if not os.path.exists(DB_PATH):
        print("✅ intialize_db.")
        initialize_db()


def reset_db():
    """기존 DB를 초기화하고 테이블을 재생성"""
    conn = sqlite3.connect("tradebot.db")
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
    initialize_db()


def initialize_db():
    """DB 테이블 초기 생성"""
    conn = sqlite3.connect("tradebot.db")
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
        status TEXT
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

    print("✅ DB 초기화 완료: tradebot.db")
