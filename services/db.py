import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import contextmanager
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import threading
from functools import wraps

# SQLAlchemy imports
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, SQLAlchemyError
import backoff

# 환경 변수
DB_URL = os.getenv("DB_URL", "sqlite:///tradebot_default.db")
DB_PREFIX = os.getenv("DB_PREFIX", "tradebot")

# 로거 설정
logger = logging.getLogger(__name__)

# DB 연결 풀 설정
class DatabaseManager:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = None
        self.SessionLocal = None
        self.session_factory = None
        self._local = threading.local()
        self._init_engine()
    
    def _init_engine(self):
        """DB 엔진 초기화"""
        if self.db_url.startswith("sqlite"):
            # SQLite 설정
            self.engine = create_engine(
                self.db_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,
                connect_args={"check_same_thread": False}
            )
        elif self.db_url.startswith("mysql"):
            # MySQL 설정
            self.engine = create_engine(
                self.db_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True,
                connect_args={
                    "charset": "utf8mb4",
                    "connect_timeout": 10
                }
            )
        else:
            raise ValueError(f"지원하지 않는 DB 스킴: {self.db_url}")
        
        # 세션 팩토리 설정
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False
        )
        self.SessionLocal = scoped_session(self.session_factory)
        
        # 이벤트 리스너 설정
        event.listen(self.engine, "engine_connect", self._on_connect)
        event.listen(self.engine, "engine_disconnect", self._on_disconnect)
    
    def _on_connect(self, connection, branch):
        """연결 성공 시 로깅"""
        logger.debug(f"DB 연결 성공: {self.db_url}")
    
    def _on_disconnect(self, connection, branch):
        """연결 해제 시 로깅"""
        logger.debug(f"DB 연결 해제: {self.db_url}")
    
    @contextmanager
    def get_session(self):
        """세션 컨텍스트 매니저"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB 세션 오류: {e}")
            raise
        finally:
            session.close()
    
    @contextmanager
    def get_connection(self):
        """직접 연결 컨텍스트 매니저"""
        connection = self.engine.connect()
        try:
            yield connection
        except Exception as e:
            logger.error(f"DB 연결 오류: {e}")
            raise
        finally:
            connection.close()
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None):
        """쿼리 실행 헬퍼"""
        with self.get_connection() as conn:
            result = conn.execute(text(query), params or {})
            return result.fetchall()
    
    def execute_update(self, query: str, params: Optional[Dict[str, Any]] = None):
        """업데이트 쿼리 실행 헬퍼"""
        with self.get_connection() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result.rowcount
    
    def health_check(self) -> bool:
        """DB 헬스 체크"""
        try:
            with self.get_connection() as conn:
                conn.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"DB 헬스 체크 실패: {e}")
            return False
    
    def close(self):
        """연결 풀 종료"""
        if self.engine:
            self.engine.dispose()
            self.engine = None

# 재시도 데코레이터
def retry_on_db_failure(max_tries=3, delay=1, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        @backoff.on_exception(
            backoff.expo,
            (OperationalError, SQLAlchemyError),
            max_tries=max_tries,
            base_delay=delay,
            factor=backoff_factor
        )
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"DB 작업 재시도 실패: {func.__name__}, 오류: {e}")
                raise
        return wrapper
    return decorator

# 전역 DB 매니저 인스턴스
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """DB 매니저 인스턴스 가져오기"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(DB_URL)
    return _db_manager

# 시간 생성 함수 (KST 기준)
def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()

# 사용자별 DB 경로/세션 가져오기
@contextmanager
def get_db(user_id: str):
    """사용자별 DB 컨텍스트 매니저"""
    db_manager = get_db_manager()
    
    if DB_URL.startswith("sqlite"):
        # SQLite의 경우 사용자별 파일 관리
        db_path = f"{DB_PREFIX}_{user_id}.db"
        if not os.path.exists(db_path):
            # 새로운 사용자 DB 파일 생성
            user_db_url = f"sqlite:///{db_path}"
            user_db_manager = DatabaseManager(user_db_url)
            with user_db_manager.get_connection() as conn:
                # 초기 스키마 실행
                with open("migrations/0001_init.sql", "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                conn.execute(text(schema_sql))
                conn.commit()
            user_db_manager.close()
        
        # 사용자별 DB 매니저 생성
        user_db_url = f"sqlite:///{db_path}"
        user_db_manager = DatabaseManager(user_db_url)
        try:
            with user_db_manager.get_session() as session:
                yield session
        finally:
            user_db_manager.close()
    else:
        # MySQL의 경우 동일 DB에서 user_id로 분리
        try:
            with db_manager.get_session() as session:
                yield session
        except Exception as e:
            logger.error(f"DB 세션获取 실패: {e}")
            raise

# 사용자 정보 관리
@retry_on_db_failure()
def save_user(username: str, display_name: str, virtual_krw: int):
    with get_db(username) as session:
        session.execute(
            text("""
                INSERT INTO users (username, display_name, virtual_krw, updated_at)
                VALUES (:username, :display_name, :virtual_krw, :updated_at)
                ON CONFLICT(username) DO UPDATE SET
                    display_name = excluded.display_name,
                    virtual_krw = excluded.virtual_krw,
                    updated_at = excluded.updated_at
            """),
            {
                "username": username,
                "display_name": display_name,
                "virtual_krw": virtual_krw,
                "updated_at": now_kst()
            }
        )

@retry_on_db_failure()
def get_user(username: str) -> Optional[Dict[str, Any]]:
    with get_db(username) as session:
        result = session.execute(
            text("SELECT display_name, virtual_krw, updated_at FROM users WHERE username = :username"),
            {"username": username}
        ).fetchone()
        return dict(result._mapping) if result else None

# 주문 관리
@retry_on_db_failure()
def insert_order(user_id: str, ticker: str, side: str, price: float, volume: float, 
                status: str, current_krw: Optional[int] = None, 
                current_coin: Optional[float] = None, profit_krw: Optional[int] = None):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO orders (
                    user_id, timestamp, ticker, side, price, volume, status,
                    current_krw, current_coin, profit_krw
                )
                VALUES (:user_id, :timestamp, :ticker, :side, :price, :volume, :status,
                        :current_krw, :current_coin, :profit_krw)
            """),
            {
                "user_id": user_id,
                "timestamp": now_kst(),
                "ticker": ticker,
                "side": side,
                "price": price,
                "volume": volume,
                "status": status,
                "current_krw": current_krw,
                "current_coin": current_coin,
                "profit_krw": profit_krw
            }
        )

@retry_on_db_failure()
def fetch_recent_orders(user_id: str, limit: int = 10) -> list:
    with get_db(user_id) as session:
        result = session.execute(
            text("""
                SELECT timestamp, ticker, side, price, volume, status, current_krw, current_coin
                FROM orders
                WHERE user_id = :user_id
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit}
        ).fetchall()
        return [dict(row._mapping) for row in result]

# 로그 관리
@retry_on_db_failure()
def insert_log(user_id: str, level: str, message: str):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO logs (user_id, timestamp, level, message)
                VALUES (:user_id, :timestamp, :level, :message)
            """),
            {
                "user_id": user_id,
                "timestamp": now_kst(),
                "level": level,
                "message": message
            }
        )

@retry_on_db_failure()
def fetch_logs(user_id: str, level: str = "LOG", limit: int = 20) -> list:
    with get_db(user_id) as session:
        if level == "BUY":
            result = session.execute(
                text("""
                    SELECT timestamp, level, message
                    FROM logs
                    WHERE user_id = :user_id
                      AND (
                          level = 'BUY'
                          OR (level = 'INFO' AND message LIKE '%강제매수%')
                      )
                    ORDER BY id DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "limit": limit}
            ).fetchall()
        elif level == "SELL":
            result = session.execute(
                text("""
                    SELECT timestamp, level, message
                    FROM logs
                    WHERE user_id = :user_id
                      AND (
                          level = 'SELL'
                          OR (level = 'INFO' AND message LIKE '%강제청산%')
                      )
                    ORDER BY id DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "limit": limit}
            ).fetchall()
        elif level == "INFO":
            result = session.execute(
                text("""
                    SELECT timestamp, level, message
                    FROM logs
                    WHERE user_id = :user_id
                      AND (
                          (level = 'INFO' OR level = 'BUY' OR level = 'SELL')
                      )
                    ORDER BY id DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "limit": limit}
            ).fetchall()
        else:
            result = session.execute(
                text("""
                    SELECT timestamp, level, message
                    FROM logs
                    WHERE user_id = :user_id AND level = :level
                    ORDER BY id DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "level": level, "limit": limit}
            ).fetchall()
        
        return [dict(row._mapping) for row in result]

# 계정 관리
@retry_on_db_failure()
def get_account(user_id: str) -> Optional[int]:
    with get_db(user_id) as session:
        result = session.execute(
            text("SELECT virtual_krw FROM accounts WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        return result[0] if result else None

@retry_on_db_failure()
def create_or_init_account(user_id: str, init_krw: int = 1_000_000):
    with get_db(user_id) as session:
        session.execute(
            text("INSERT OR IGNORE INTO accounts (user_id, virtual_krw) VALUES (:user_id, :virtual_krw)"),
            {"user_id": user_id, "virtual_krw": init_krw}
        )

@retry_on_db_failure()
def update_account(user_id: str, virtual_krw: int):
    virtual_krw = int(virtual_krw)
    with get_db(user_id) as session:
        session.execute(
            text("""
                UPDATE accounts
                SET virtual_krw = :virtual_krw, updated_at = :updated_at
                WHERE user_id = :user_id
            """),
            {
                "virtual_krw": virtual_krw,
                "updated_at": now_kst(),
                "user_id": user_id
            }
        )
    insert_account_history(user_id, virtual_krw)

# 포지션 관리
@retry_on_db_failure()
def get_coin_balance(user_id: str, ticker: str) -> float:
    with get_db(user_id) as session:
        result = session.execute(
            text("""
                SELECT virtual_coin
                FROM account_positions
                WHERE user_id = :user_id AND ticker = :ticker
            """),
            {"user_id": user_id, "ticker": ticker}
        ).fetchone()
        return result[0] if result else 0.0

@retry_on_db_failure()
def update_coin_position(user_id: str, ticker: str, virtual_coin: float):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO account_positions (user_id, ticker, virtual_coin, updated_at)
                VALUES (:user_id, :ticker, :virtual_coin, :updated_at)
                ON CONFLICT(user_id, ticker) DO UPDATE SET
                    virtual_coin = excluded.virtual_coin,
                    updated_at = excluded.updated_at
            """),
            {
                "user_id": user_id,
                "ticker": ticker,
                "virtual_coin": virtual_coin,
                "updated_at": now_kst()
            }
        )
    insert_position_history(user_id, ticker, virtual_coin)

# 히스토리 관리
@retry_on_db_failure()
def insert_account_history(user_id: str, virtual_krw: int):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO account_history (user_id, timestamp, virtual_krw)
                VALUES (:user_id, :timestamp, :virtual_krw)
            """),
            {
                "user_id": user_id,
                "timestamp": now_kst(),
                "virtual_krw": virtual_krw
            }
        )

@retry_on_db_failure()
def insert_position_history(user_id: str, ticker: str, virtual_coin: float):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO position_history (user_id, timestamp, ticker, virtual_coin)
                VALUES (:user_id, :timestamp, :ticker, :virtual_coin)
            """),
            {
                "user_id": user_id,
                "timestamp": now_kst(),
                "ticker": ticker,
                "virtual_coin": virtual_coin
            }
        )

# 엔진 상태 관리
@retry_on_db_failure()
def set_engine_status(user_id: str, is_running: bool):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO engine_status (user_id, is_running, last_heartbeat)
                VALUES (:user_id, :is_running, :last_heartbeat)
                ON CONFLICT(user_id) DO UPDATE SET
                    is_running = excluded.is_running,
                    last_heartbeat = excluded.last_heartbeat
            """),
            {
                "user_id": user_id,
                "is_running": int(is_running),
                "last_heartbeat": now_kst()
            }
        )

@retry_on_db_failure()
def get_engine_status(user_id: str) -> bool:
    with get_db(user_id) as session:
        result = session.execute(
            text("SELECT is_running FROM engine_status WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        return bool(result and result[0])

# 스레드 상태 관리
@retry_on_db_failure()
def set_thread_status(user_id: str, is_thread_running: bool):
    with get_db(user_id) as session:
        session.execute(
            text("""
                INSERT INTO thread_status (user_id, is_thread_running, last_heartbeat)
                VALUES (:user_id, :is_thread_running, :last_heartbeat)
                ON CONFLICT(user_id) DO UPDATE SET
                    is_thread_running = excluded.is_thread_running,
                    last_heartbeat = excluded.last_heartbeat
            """),
            {
                "user_id": user_id,
                "is_thread_running": int(is_thread_running),
                "last_heartbeat": now_kst()
            }
        )

@retry_on_db_failure()
def get_thread_status(user_id: str) -> bool:
    with get_db(user_id) as session:
        result = session.execute(
            text("SELECT is_thread_running FROM thread_status WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        return bool(result and result[0])

# 초기 KRW 가져오기
@retry_on_db_failure()
def get_initial_krw(user_id: str) -> Optional[float]:
    with get_db(user_id) as session:
        result = session.execute(
            text("SELECT virtual_krw FROM users WHERE username = :username"),
            {"username": user_id}
        ).fetchone()
        return result[0] if result else None

# DB 초기화 함수 (호환성 유지)
def get_db_path(user_id: str) -> str:
    """기존 호환성을 위한 DB 경로 반환"""
    return f"{DB_PREFIX}_{user_id}.db"

def init_db_if_needed(user_id: str):
    """DB 초기화 필요시 초기화"""
    if DB_URL.startswith("sqlite"):
        db_path = get_db_path(user_id)
        if not os.path.exists(db_path):
            from services.init_db import initialize_db
            initialize_db(user_id)

# DB 매니저 종료 함수
def close_db_connections():
    """모든 DB 연결 종료"""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None