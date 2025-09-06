-- 업비트 트레이드봇 v2 DB 스키마 롤백
-- 버전: 0001
-- 설명: 모든 테이블, 인덱스, 뷰, 트리거 삭제

-- 뷰 삭제
DROP VIEW IF EXISTS user_portfolio_view;
DROP VIEW IF EXISTS trading_stats_view;
DROP VIEW IF EXISTS daily_summary_view;

-- 트리거 삭제
DROP TRIGGER IF EXISTS cleanup_old_logs;
DROP TRIGGER IF EXISTS cleanup_old_candles;
DROP TRIGGER IF EXISTS update_order_status;
DROP TRIGGER IF EXISTS update_position_profit;

-- 인덱스 삭제

-- 스레드 상태 관련 인덱스
DROP INDEX IF EXISTS idx_thread_status_running;
DROP INDEX IF EXISTS idx_thread_status_user_id;

-- 엔진 상태 관련 인덱스
DROP INDEX IF EXISTS idx_engine_status_heartbeat;
DROP INDEX IF EXISTS idx_engine_status_running;
DROP INDEX IF EXISTS idx_engine_status_user_id;

-- 캔들 관련 인덱스
DROP INDEX IF EXISTS idx_candles_ticker_interval;
DROP INDEX IF EXISTS idx_candles_timestamp;
DROP INDEX IF EXISTS idx_candles_interval;
DROP INDEX IF EXISTS idx_candles_ticker;

-- 거래 관련 인덱스
DROP INDEX IF EXISTS idx_trades_type;
DROP INDEX IF EXISTS idx_trades_ticker;
DROP INDEX IF EXISTS idx_trades_timestamp;
DROP INDEX IF EXISTS idx_trades_user_id;

-- 신호 관련 인덱스
DROP INDEX IF EXISTS idx_signals_type;
DROP INDEX IF EXISTS idx_signals_ticker;
DROP INDEX IF EXISTS idx_signals_timestamp;
DROP INDEX IF EXISTS idx_signals_user_id;

-- 히스토리 관련 인덱스
DROP INDEX IF EXISTS idx_position_history_timestamp;
DROP INDEX IF EXISTS idx_position_history_user_id;
DROP INDEX IF EXISTS idx_account_history_timestamp;
DROP INDEX IF EXISTS idx_account_history_user_id;

-- 로그 관련 인덱스
DROP INDEX IF EXISTS idx_logs_user_timestamp;
DROP INDEX IF EXISTS idx_logs_level;
DROP INDEX IF EXISTS idx_logs_timestamp;
DROP INDEX IF EXISTS idx_logs_user_id;

-- 포지션 관련 인덱스
DROP INDEX IF EXISTS idx_account_positions_ticker;
DROP INDEX IF EXISTS idx_account_positions_user_id;

-- 주문 관련 인덱스
DROP INDEX IF EXISTS idx_orders_user_timestamp;
DROP INDEX IF EXISTS idx_orders_status;
DROP INDEX IF EXISTS idx_orders_ticker;
DROP INDEX IF EXISTS idx_orders_timestamp;
DROP INDEX IF EXISTS idx_orders_user_id;

-- 사용자 관련 인덱스
DROP INDEX IF EXISTS idx_users_display_name;
DROP INDEX IF EXISTS idx_users_username;

-- 테이블 삭제 (외래 키 제약조건을 고려한 순서)

-- 시스템 설정 테이블
DROP TABLE IF EXISTS system_settings;

-- 캔들 데이터 테이블
DROP TABLE IF EXISTS candles;

-- 거래 통계 테이블
DROP TABLE IF EXISTS trades;

-- 신호 정보 테이블
DROP TABLE IF EXISTS signals;

-- 스레드 상태 테이블
DROP TABLE IF EXISTS thread_status;

-- 엔진 상태 테이블
DROP TABLE IF EXISTS engine_status;

-- 포지션 히스토리 테이블
DROP TABLE IF EXISTS position_history;

-- 계정 히스토리 테이블
DROP TABLE IF EXISTS account_history;

-- 로그 정보 테이블
DROP TABLE IF EXISTS logs;

-- 포지션 정보 테이블
DROP TABLE IF EXISTS account_positions;

-- 주문 정보 테이블
DROP TABLE IF EXISTS orders;

-- 계정 정보 테이블
DROP TABLE IF EXISTS accounts;

-- 사용자 정보 테이블
DROP TABLE IF EXISTS users;

-- 롤백 완료 확인
-- 모든 테이블, 인덱스, 뷰, 트리거가 삭제되었습니다.