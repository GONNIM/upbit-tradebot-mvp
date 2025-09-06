-- 업비트 트레이드봇 v2 DB 스키마 초기화
-- 버전: 0001
-- 설명: 핵심 테이블 생성 및 인덱스 설정

-- 사용자 정보 테이블
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    virtual_krw INTEGER DEFAULT 1000000,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 사용자별 계정 정보 테이블
CREATE TABLE IF NOT EXISTS accounts (
    user_id TEXT PRIMARY KEY,
    virtual_krw INTEGER DEFAULT 1000000 NOT NULL,
    initial_krw INTEGER DEFAULT 1000000 NOT NULL,
    total_profit_krw INTEGER DEFAULT 0,
    total_profit_rate REAL DEFAULT 0.0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 주문 정보 테이블
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    price REAL NOT NULL,
    volume REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    order_type TEXT DEFAULT 'MARKET',
    current_krw INTEGER DEFAULT 0,
    current_coin REAL DEFAULT 0.0,
    profit_krw INTEGER DEFAULT 0,
    profit_rate REAL DEFAULT 0.0,
    fee_krw INTEGER DEFAULT 0,
    fee_rate REAL DEFAULT 0.0005,
    executed_price REAL,
    executed_volume REAL,
    error_message TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 포지션 정보 테이블
CREATE TABLE IF NOT EXISTS account_positions (
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    virtual_coin REAL DEFAULT 0.0 NOT NULL,
    avg_buy_price REAL DEFAULT 0.0,
    total_buy_krw INTEGER DEFAULT 0,
    total_sell_krw INTEGER DEFAULT 0,
    unrealized_profit_krw INTEGER DEFAULT 0,
    unrealized_profit_rate REAL DEFAULT 0.0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- 제약조건
    PRIMARY KEY (user_id, ticker),
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 로그 정보 테이블
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'BUY', 'SELL')),
    message TEXT NOT NULL,
    ticker TEXT,
    price REAL,
    volume REAL,
    additional_data TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 계정 히스토리 테이블
CREATE TABLE IF NOT EXISTS account_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    virtual_krw INTEGER NOT NULL,
    total_profit_krw INTEGER DEFAULT 0,
    total_profit_rate REAL DEFAULT 0.0,
    event_type TEXT DEFAULT 'UPDATE',
    event_details TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 포지션 히스토리 테이블
CREATE TABLE IF NOT EXISTS position_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    virtual_coin REAL NOT NULL,
    avg_buy_price REAL DEFAULT 0.0,
    total_buy_krw INTEGER DEFAULT 0,
    total_sell_krw INTEGER DEFAULT 0,
    unrealized_profit_krw INTEGER DEFAULT 0,
    event_type TEXT DEFAULT 'UPDATE',
    event_details TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 엔진 상태 테이블
CREATE TABLE IF NOT EXISTS engine_status (
    user_id TEXT PRIMARY KEY,
    is_running INTEGER DEFAULT 0 CHECK (is_running IN (0, 1)),
    last_heartbeat TEXT DEFAULT CURRENT_TIMESTAMP,
    start_time TEXT,
    total_uptime INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error_message TEXT,
    last_restart_time TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 스레드 상태 테이블
CREATE TABLE IF NOT EXISTS thread_status (
    user_id TEXT PRIMARY KEY,
    is_thread_running INTEGER DEFAULT 0 CHECK (is_thread_running IN (0, 1)),
    last_heartbeat TEXT DEFAULT CURRENT_TIMESTAMP,
    thread_name TEXT,
    thread_id TEXT,
    last_activity_time TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 신호 정보 테이블 (전략 시그널 저장)
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    signal_strength REAL DEFAULT 0.0,
    price REAL,
    macd REAL,
    signal_line REAL,
    histogram REAL,
    rsi REAL,
    volume REAL,
    additional_indicators TEXT,
    confidence_score REAL DEFAULT 0.0,
    executed INTEGER DEFAULT 0,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 거래 통계 테이블
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    trade_type TEXT NOT NULL CHECK (trade_type IN ('LONG', 'SHORT')),
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    volume REAL NOT NULL,
    profit_krw INTEGER DEFAULT 0,
    profit_rate REAL DEFAULT 0.0,
    holding_period INTEGER DEFAULT 0,
    max_profit_rate REAL DEFAULT 0.0,
    max_loss_rate REAL DEFAULT 0.0,
    fees_krw INTEGER DEFAULT 0,
    strategy_params TEXT,
    
    -- 제약조건
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);

-- 캔들 데이터 테이블 (선택적 - 기술적 분석용)
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    interval TEXT NOT NULL CHECK (interval IN ('1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d')),
    timestamp TEXT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    ma20 REAL,
    ma60 REAL,
    macd REAL,
    signal_line REAL,
    histogram REAL,
    rsi REAL,
    
    -- 제약조건
    UNIQUE(ticker, interval, timestamp)
);

-- 시스템 설정 테이블
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);

-- 인덱스 생성

-- 사용자 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name);

-- 주문 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_timestamp ON orders(user_id, timestamp DESC);

-- 포지션 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_account_positions_user_id ON account_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_account_positions_ticker ON account_positions(ticker);

-- 로그 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_user_timestamp ON logs(user_id, timestamp DESC);

-- 히스토리 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_account_history_user_id ON account_history(user_id);
CREATE INDEX IF NOT EXISTS idx_account_history_timestamp ON account_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_position_history_user_id ON position_history(user_id);
CREATE INDEX IF NOT EXISTS idx_position_history_timestamp ON position_history(timestamp);

-- 신호 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_signals_user_id ON signals(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);

-- 거래 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_type ON trades(trade_type);

-- 캔들 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_candles_ticker ON candles(ticker);
CREATE INDEX IF NOT EXISTS idx_candles_interval ON candles(interval);
CREATE INDEX IF NOT EXISTS idx_candles_timestamp ON candles(timestamp);
CREATE INDEX IF NOT EXISTS idx_candles_ticker_interval ON candles(ticker, interval);

-- 엔진 상태 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_engine_status_user_id ON engine_status(user_id);
CREATE INDEX IF NOT EXISTS idx_engine_status_running ON engine_status(is_running);
CREATE INDEX IF NOT EXISTS idx_engine_status_heartbeat ON engine_status(last_heartbeat);

-- 스레드 상태 관련 인덱스
CREATE INDEX IF NOT EXISTS idx_thread_status_user_id ON thread_status(user_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_running ON thread_status(is_thread_running);

-- 기본 설정 데이터 삽입
INSERT OR IGNORE INTO system_settings (key, value, description) VALUES 
('version', '0001', 'DB 스키마 버전'),
('min_order_amount', '5000', '최소 주문 금액 (KRW)'),
('max_position_size', '500000', '최대 포지션 크기 (KRW)'),
('default_commission_rate', '0.0005', '기본 수수료율 (0.05%)'),
('max_loss_rate', '0.02', '최대 손실률 (2%)'),
('take_profit_rate', '0.03', '익절률 (3%)'),
('trailing_stop_rate', '0.02', '트레일링 스톱률 (2%)'),
('min_holding_period', '5', '최소 보유 기간 (분)'),
('max_daily_trades', '10', '일 최대 거래 횟수'),
('data_retention_days', '90', '데이터 보존 기간 (일)');

-- 트리거 생성 (SQLite용)

-- 로그 데이터 자동 정리 트리거
CREATE TRIGGER IF NOT EXISTS cleanup_old_logs
AFTER INSERT ON logs
BEGIN
    DELETE FROM logs 
    WHERE timestamp < datetime('now', '-' || (SELECT value FROM system_settings WHERE key = 'data_retention_days') || ' days');
END;

-- 오래된 캔들 데이터 정리 트리거
CREATE TRIGGER IF NOT EXISTS cleanup_old_candles
AFTER INSERT ON candles
BEGIN
    DELETE FROM candles 
    WHERE timestamp < datetime('now', '-30 days');
END;

-- 주문 상태 자동 업데이트 트리거
CREATE TRIGGER IF NOT EXISTS update_order_status
AFTER UPDATE OF executed_price, executed_volume ON orders
WHEN NEW.executed_price IS NOT NULL AND NEW.executed_volume IS NOT NULL
BEGIN
    UPDATE orders 
    SET status = 'FILLED',
        updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- 포지션 수익률 자동 계산 트리거
CREATE TRIGGER IF NOT EXISTS update_position_profit
AFTER UPDATE OF virtual_coin ON account_positions
FOR EACH ROW
BEGIN
    UPDATE account_positions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id AND ticker = NEW.ticker;
END;

-- 뷰 생성

-- 사용자 포트폴리오 뷰
CREATE VIEW IF NOT EXISTS user_portfolio_view AS
SELECT 
    u.user_id,
    u.virtual_krw,
    COALESCE(SUM(p.virtual_coin * p.avg_buy_price), 0) as total_coin_value,
    COALESCE(SUM(p.unrealized_profit_krw), 0) as total_unrealized_profit,
    (COALESCE(SUM(p.unrealized_profit_krw), 0) * 100.0 / NULLIF(u.virtual_krw, 0)) as total_profit_rate,
    COUNT(p.ticker) as position_count,
    u.updated_at
FROM accounts u
LEFT JOIN account_positions p ON u.user_id = p.user_id
GROUP BY u.user_id, u.virtual_krw, u.updated_at;

-- 거래 통계 뷰
CREATE VIEW IF NOT EXISTS trading_stats_view AS
SELECT 
    user_id,
    COUNT(*) as total_trades,
    COUNT(CASE WHEN profit_krw > 0 THEN 1 END) as winning_trades,
    COUNT(CASE WHEN profit_krw < 0 THEN 1 END) as losing_trades,
    SUM(profit_krw) as total_profit,
    AVG(profit_krw) as avg_profit,
    AVG(holding_period) as avg_holding_period,
    MAX(profit_rate) as max_profit_rate,
    MIN(profit_rate) as min_loss_rate,
    (COUNT(CASE WHEN profit_krw > 0 THEN 1 END) * 100.0 / COUNT(*)) as win_rate
FROM trades
GROUP BY user_id;

-- 일일 거래 요약 뷰
CREATE VIEW IF NOT EXISTS daily_summary_view AS
SELECT 
    user_id,
    DATE(timestamp) as trade_date,
    COUNT(*) as trade_count,
    SUM(profit_krw) as daily_profit,
    AVG(profit_rate) as avg_profit_rate,
    SUM(CASE WHEN side = 'BUY' THEN volume ELSE 0 END) as buy_volume,
    SUM(CASE WHEN side = 'SELL' THEN volume ELSE 0 END) as sell_volume
FROM orders
WHERE status = 'FILLED'
GROUP BY user_id, DATE(timestamp)
ORDER BY trade_date DESC;

-- 초기화 완료 메시지 (주석 처리)
-- DB 스키마 버전 0001 초기화 완료