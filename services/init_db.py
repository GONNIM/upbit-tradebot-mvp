import sqlite3
import os


# 모듈 파일 기준으로 고정 (CWD 변동 영향 제거)
from pathlib import Path
APP_ROOT = Path(__file__).resolve().parent  # services.init_db.py 파일이 있는 폴더
DB_DIR = (APP_ROOT / "data").as_posix()


os.makedirs(DB_DIR, exist_ok=True)

DB_PREFIX = "tradebot"


def get_db_path(user_id):
    path = os.path.join(DB_DIR, f"{DB_PREFIX}_{user_id}.db")
    return path


def reset_db(user_id):
    db_path = get_db_path(user_id)

    # 엔진/스레드 정지는 기존 로직 유지
    # 1) 체크포인트
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()
    except Exception:
        pass

    # [FIX] DB 파일 자체 삭제 (WAL/SHM 포함)
    for f in (db_path, f"{db_path}-wal", f"{db_path}-shm"):
        try:
            if os.path.exists(f):
                os.remove(f)
                print(f"🧹 removed: {f}")
        except Exception as e:
            print(f"⚠️ remove failed({f}): {e}")

    # [FIX] 깨끗한 새 파일로 스키마 생성
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

    # ✅ 데이터 수집 상태 추적 테이블
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_collection_status (
            user_id TEXT PRIMARY KEY,
            is_collecting INTEGER DEFAULT 0,
            collected INTEGER DEFAULT 0,
            target INTEGER DEFAULT 0,
            progress REAL DEFAULT 0.0,
            estimated_time REAL DEFAULT 0.0,
            message TEXT,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
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


def _connect(user_id: str):
    conn = sqlite3.connect(get_db_path(user_id), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=3000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _safe_alter(conn, sql: str):
    try:
        conn.execute(sql)
    except Exception:
        # 이미 존재/타입불일치 등은 조용히 무시 (idempotent)
        pass


def ensure_orders_extended_schema(user_id: str | None):
    """
    orders 테이블에 확장 칼럼/인덱스 보강:
      - provider_uuid (거래소 주문 ID)
      - state (REQUESTED/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED/...)
      - executed_volume / avg_price / paid_fee
      - requested_at / executed_at / canceled_at / updated_at
    """
    # user_id가 아직 없을 수 있는 진입(예: 전역 보강) 대비: 안전한 기본 파일로 연결
    uid = user_id or "default"
    conn = _connect(uid)
    cur = conn.cursor()

    # orders 테이블 없으면 생성(기존 스키마 유지)
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

    # 확장 칼럼(조건부)
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN provider_uuid TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN state TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN executed_volume REAL")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN avg_price REAL")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN paid_fee REAL")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN requested_at TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN executed_at TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN canceled_at TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN updated_at TEXT")
    _safe_alter(conn, "ALTER TABLE orders ADD COLUMN entry_bar INTEGER")  # ✅ bars_held 추적용

    # 인덱스(조건부)
    _safe_alter(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_uuid ON orders(provider_uuid)")
    _safe_alter(conn, "CREATE INDEX IF NOT EXISTS idx_orders_user_ticker ON orders(user_id, ticker)")
    _safe_alter(conn, "CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state)")
    _safe_alter(conn, "CREATE INDEX IF NOT EXISTS idx_orders_user_state ON orders(user_id, state)")
    _safe_alter(conn, "CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(timestamp)")

    conn.commit()
    conn.close()

    # ✅ 자동 마이그레이션: audit 테이블의 bool → int 변환
    _migrate_audit_checks_bool_to_int(uid)


def ensure_core_tables(user_id: str):
    conn = _connect(user_id)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        display_name TEXT,
        virtual_krw INTEGER,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
    );""")
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
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        level TEXT,
        message TEXT
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        user_id TEXT PRIMARY KEY,
        virtual_krw INTEGER DEFAULT 1000000,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        virtual_krw INTEGER
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_positions (
        user_id TEXT,
        ticker TEXT,
        virtual_coin REAL DEFAULT 0,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime')),
        PRIMARY KEY (user_id, ticker)
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS position_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
        ticker TEXT,
        virtual_coin REAL
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS engine_status (
        user_id TEXT PRIMARY KEY,
        is_running INTEGER DEFAULT 0,
        last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS thread_status (
        user_id TEXT PRIMARY KEY,
        is_thread_running INTEGER DEFAULT 0,
        last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
    );""")

    # ✅ 데이터 수집 상태 추적 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS data_collection_status (
        user_id TEXT PRIMARY KEY,
        is_collecting INTEGER DEFAULT 0,
        collected INTEGER DEFAULT 0,
        target INTEGER DEFAULT 0,
        progress REAL DEFAULT 0.0,
        estimated_time REAL DEFAULT 0.0,
        message TEXT,
        updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
    );""")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_ts ON orders(user_id, timestamp);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_ts ON logs(user_id, timestamp);")

    conn.commit()
    conn.close()


def ensure_audit_trades_bar_time(user_id: str):
    """
    audit_trades 테이블에 bar_time 컬럼 추가:
      - timestamp: 실제 체결 발생 시각 (실시간 현재 시각)
      - bar_time: 해당 봉의 시각 (전략 신호가 발생한 봉의 시각)
    """
    conn = _connect(user_id)
    _safe_alter(conn, "ALTER TABLE audit_trades ADD COLUMN bar_time TEXT")
    conn.commit()
    conn.close()


def ensure_audit_settings_bar_time(user_id: str):
    """
    audit_settings 테이블에 bar_time 컬럼 추가:
      - timestamp: 실시간 로그 기록 시각
      - bar_time: 해당 봉의 시각 (전략이 분석한 봉의 시각)
    """
    conn = _connect(user_id)
    _safe_alter(conn, "ALTER TABLE audit_settings ADD COLUMN bar_time TEXT")
    conn.commit()
    conn.close()


def ensure_audit_settings_unique(user_id: str):
    """
    audit_settings 테이블에 UNIQUE 인덱스 추가:
      - (ticker, interval_sec, bar_time) 조합으로 중복 방지
      - bar_time 기준 = "1개의 봉마다 1개" 보장
      - UNIQUE INDEX는 DB 레벨에서 중복을 원천 차단
      - INSERT OR IGNORE와 함께 사용하여 중복 시도 시 조용히 무시
    """
    conn = _connect(user_id)
    try:
        # 🔥 기존 인덱스 삭제 (timestamp 기준 → bar_time 기준으로 변경)
        conn.execute("DROP INDEX IF EXISTS idx_audit_settings_unique")

        # ✅ UNIQUE 인덱스 재생성 - bar_time 기준
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_settings_unique
            ON audit_settings(ticker, interval_sec, bar_time)
        """)
        conn.commit()
    except Exception as e:
        # 이미 존재하면 무시
        pass
    finally:
        conn.close()


def ensure_all_schemas(user_id: str):
    """
    코어 + 감사 + orders 확장 스키마를 한 번에 보장
    """
    ensure_core_tables(user_id)
    add_audit_tables(user_id)
    ensure_orders_extended_schema(user_id)
    ensure_audit_trades_bar_time(user_id)
    ensure_audit_settings_bar_time(user_id)  # ✅ bar_time 컬럼 추가
    ensure_audit_settings_unique(user_id)    # ✅ UNIQUE 인덱스 (bar_time 기준)


def init_db_if_needed(user_id):
    """
    기존 코드를 대체: 신규/기존 관계없이 항상 스키마를 최신으로 보강
    """
    db_path = get_db_path(user_id)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    ensure_all_schemas(user_id)


def init_db_if_needed_old(user_id):
    db_path = get_db_path(user_id)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # ✅ 신규/기존 구분 없이, 항상 코어 테이블 + 감사 테이블 보강
    ensure_core_tables(user_id)
    add_audit_tables(user_id)
    # print(f"✅ Schema ensured: {db_path}")


def _migrate_audit_checks_bool_to_int(user_id: str):
    """
    audit_sell_eval, audit_buy_eval 테이블의 checks JSON 필드에서
    bool 값을 int로 자동 변환 (PyArrow 호환성)

    - 최초 1회 실행 시 모든 레코드 변환
    - 이후 실행 시 이미 변환된 레코드는 스킵 (성능 최적화)
    """
    import json

    def convert_bool_recursive(obj):
        """재귀적으로 dict/list 내 bool 값을 int로 변환"""
        if isinstance(obj, bool):
            return int(obj)
        elif isinstance(obj, dict):
            return {k: convert_bool_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_bool_recursive(item) for item in obj]
        else:
            return obj

    def convert_json(json_str):
        """JSON 문자열 내 모든 bool 값을 int로 변환"""
        if not json_str:
            return json_str
        try:
            data = json.loads(json_str)
            converted = convert_bool_recursive(data)
            return json.dumps(converted, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return json_str

    conn = _connect(user_id)
    cur = conn.cursor()

    tables = ['audit_sell_eval', 'audit_buy_eval']

    for table in tables:
        # 테이블 존재 확인
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            continue

        # checks 필드가 있는 레코드 조회 (전체)
        cur.execute(f"SELECT id, checks FROM {table} WHERE checks IS NOT NULL")
        rows = cur.fetchall()

        converted_count = 0
        for row_id, checks_json in rows:
            original = checks_json
            converted = convert_json(checks_json)

            # 변환이 발생한 경우에만 업데이트
            if original != converted:
                cur.execute(f"UPDATE {table} SET checks = ? WHERE id = ?", (converted, row_id))
                converted_count += 1

        if converted_count > 0:
            conn.commit()
            # print(f"✅ Migrated {converted_count} records in {table}")

    conn.close()
