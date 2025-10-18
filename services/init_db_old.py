import sqlite3
import os


APP_ROOT = os.path.abspath(os.getcwd())
DB_DIR = os.path.join(APP_ROOT, "data")

os.makedirs(DB_DIR, exist_ok=True)

DB_PREFIX = "tradebot"


def get_db_path(user_id):
    # return f"{DB_PREFIX}_{user_id}.db"
    return os.path.join(DB_DIR, f"{DB_PREFIX}_{user_id}.db")


# def init_db_if_needed(user_id):
#     if not os.path.exists(get_db_path(user_id)):
#         print(f"✅ intialize_db : {get_db_path(user_id)}")
#         initialize_db(user_id)
def init_db_if_needed(user_id):
    db_path = get_db_path(user_id)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # if not os.path.exists(db_path):
    #     print(f"✅ initialize_db : {db_path}")
    # else:
    #     print(f"ℹ️ DB exists: {db_path}")

    # ✅ 신규/기존 구분 없이, 항상 코어 테이블 + 감사 테이블 보강
    ensure_core_tables(user_id)
    add_audit_tables(user_id)
    # print(f"✅ Schema ensured: {db_path}")


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

    # orders 조회/정리용
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_ts ON orders(user_id, timestamp);")
    # logs 최근/상태 조회용
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_ts ON logs(user_id, timestamp);")

    conn.commit()
    conn.close()

    add_audit_tables(user_id)

    print(f"✅ DB 초기화 완료: {get_db_path(user_id)}")


def add_audit_tables(user_id):
    conn = sqlite3.connect(get_db_path(user_id))
    cursor = conn.cursor()

    # 1) 매수 평가 감사 (왜 못 샀는지)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_buy_eval (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker TEXT,
            interval_sec INTEGER,
            bar INTEGER,
            price REAL,
            macd REAL,
            signal REAL,
            have_position INTEGER,     -- 0/1
            overall_ok INTEGER,        -- 0/1
            failed_keys TEXT,          -- JSON string: ["signal_confirm",...]
            checks TEXT,               -- JSON string: {"signal_positive":true,...}
            notes TEXT
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_buy_eval_ts ON audit_buy_eval(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_buy_eval_ticker_ts ON audit_buy_eval(ticker, timestamp);")

    # 2) 체결 감사 (BUY/SELL 기록)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker TEXT,
            interval_sec INTEGER,
            bar INTEGER,
            type TEXT,                 -- 'BUY' | 'SELL'
            reason TEXT,
            price REAL,
            macd REAL,
            signal REAL,
            entry_price REAL,
            entry_bar INTEGER,
            bars_held INTEGER,
            tp REAL,
            sl REAL,
            highest REAL,
            ts_pct REAL,
            ts_armed INTEGER           -- 0/1/NULL
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_trades_ts ON audit_trades(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_trades_ticker_ts ON audit_trades(ticker, timestamp);")

    # (선택) 3) 실행 시점 설정 스냅샷
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker TEXT,
            interval_sec INTEGER,
            tp REAL, sl REAL, ts_pct REAL,
            signal_gate INTEGER,       -- 0/1
            threshold REAL,
            buy_json TEXT,             -- JSON string
            sell_json TEXT             -- JSON string
        );
        """
    )

    # 4) 매도 평가 감사 (전 조건 판정 + 트리거)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_sell_eval (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT DEFAULT (DATETIME('now', 'localtime')),
            ticker      TEXT,
            interval_sec INTEGER,
            bar         INTEGER,
            price       REAL,
            macd        REAL,
            signal      REAL,
            tp_price    REAL,
            sl_price    REAL,
            highest     REAL,
            ts_pct      REAL,
            ts_armed    INTEGER,          -- 0/1
            bars_held   INTEGER,
            checks      TEXT,             -- JSON: {"take_profit":{"enabled":1,"pass":0,"value":...}, ...}
            triggered   INTEGER,          -- 0/1
            trigger_key TEXT,             -- "Stop Loss" | "Trailing Stop" | ...
            notes       TEXT
        );
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_sell_eval_ts ON audit_sell_eval(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_sell_eval_ticker_ts ON audit_sell_eval(ticker, timestamp);")

    conn.commit()
    conn.close()
    # print(f"✅ Audit tables ready: {get_db_path(user_id)}")


def _connect(user_id):
    conn = sqlite3.connect(get_db_path(user_id))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=3000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def ensure_core_tables(user_id: str):
    conn = _connect(user_id)
    cur = conn.cursor()

    # ✅ 핵심 테이블들 (모두 IF NOT EXISTS)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        display_name TEXT,
        virtual_krw INTEGER,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        ticker TEXT,
        side TEXT,
        price REAL,
        volume REAL,
        status TEXT,
        current_krw INTEGER DEFAULT 0,
        current_coin REAL DEFAULT 0.0,
        profit_krw INTEGER DEFAULT 0
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        level TEXT,
        message TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        user_id TEXT PRIMARY KEY,
        virtual_krw INTEGER DEFAULT 1000000,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        virtual_krw INTEGER
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_positions (
        user_id TEXT,
        ticker TEXT,
        virtual_coin REAL DEFAULT 0,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime')),
        PRIMARY KEY (user_id, ticker)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS position_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        ticker TEXT,
        virtual_coin REAL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS engine_status (
        user_id TEXT PRIMARY KEY,
        is_running INTEGER DEFAULT 0,
        last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS thread_status (
        user_id TEXT PRIMARY KEY,
        is_thread_running INTEGER DEFAULT 0,
        last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
    );
    """)

    # 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_ts ON orders(user_id, timestamp);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_ts ON logs(user_id, timestamp);")

    conn.commit()
    conn.close()
