import os
import logging
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import shutil

from services.db import get_db_manager, DB_URL, DB_PREFIX

# 로거 설정
logger = logging.getLogger(__name__)

# 시간 생성 함수 (KST 기준)
def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()

def get_db_path(user_id: str) -> str:
    """사용자별 DB 경로 반환"""
    if DB_URL.startswith("sqlite"):
        return f"{DB_PREFIX}_{user_id}.db"
    else:
        return DB_URL

def get_migration_files() -> dict:
    """마이그레이션 파일 목록 가져오기"""
    migrations = {}
    migrations_dir = "migrations"
    
    if not os.path.exists(migrations_dir):
        logger.warning(f"마이그레이션 디렉토리가 존재하지 않습니다: {migrations_dir}")
        return migrations
    
    for filename in sorted(os.listdir(migrations_dir)):
        if filename.endswith("_init.sql"):
            version = filename.split("_")[0]
            migrations[version] = {
                "init": os.path.join(migrations_dir, filename),
                "rollback": os.path.join(migrations_dir, f"{version}_rollback.sql")
            }
    
    return migrations

def execute_sql_file(db_manager, file_path: str) -> bool:
    """SQL 파일 실행"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            sql_content = f.read()
        
        with db_manager.get_connection() as conn:
            # SQL을 여러 문장으로 분리하여 실행
            statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
            
            for statement in statements:
                if statement:
                    conn.execute(statement)
            
            conn.commit()
        
        logger.info(f"SQL 파일 실행 성공: {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"SQL 파일 실행 실패: {file_path}, 오류: {e}")
        return False

def init_db_if_needed(user_id: str) -> bool:
    """DB 초기화 필요시 초기화"""
    try:
        if DB_URL.startswith("sqlite"):
            db_path = get_db_path(user_id)
            if not os.path.exists(db_path):
                logger.info(f"새로운 사용자 DB 초기화: {db_path}")
                return initialize_db(user_id)
            else:
                logger.info(f"기존 DB 존재: {db_path}")
                return True
        else:
            # MySQL의 경우 테이블 존재 여부 확인
            db_manager = get_db_manager()
            try:
                with db_manager.get_connection() as conn:
                    result = conn.execute("SHOW TABLES LIKE 'users'")
                    if not result.fetchone():
                        logger.info(f"MySQL 테이블 초기화: {user_id}")
                        return initialize_db(user_id)
                    else:
                        logger.info(f"기존 MySQL 테이블 존재: {user_id}")
                        return True
            except Exception as e:
                logger.error(f"MySQL 테이블 확인 실패: {e}")
                return False
    except Exception as e:
        logger.error(f"DB 초기화 확인 실패: {e}")
        return False

def initialize_db(user_id: str) -> bool:
    """DB 초기화 및 마이그레이션 적용"""
    try:
        if DB_URL.startswith("sqlite"):
            # SQLite 사용자별 DB 생성
            db_path = get_db_path(user_id)
            user_db_url = f"sqlite:///{db_path}"
            db_manager = get_db_manager().__class__(user_db_url)
        else:
            # MySQL 공유 DB 사용
            db_manager = get_db_manager()
        
        # 마이그레이션 파일 가져오기
        migrations = get_migration_files()
        
        if not migrations:
            logger.error("마이그레이션 파일을 찾을 수 없습니다")
            return False
        
        # 마이그레이션 순차적 실행
        for version in sorted(migrations.keys()):
            init_file = migrations[version]["init"]
            
            if not os.path.exists(init_file):
                logger.error(f"마이그레이션 파일이 존재하지 않습니다: {init_file}")
                continue
            
            # 마이그레이션 실행
            if not execute_sql_file(db_manager, init_file):
                logger.error(f"마이그레이션 실행 실패: {init_file}")
                return False
        
        # 기본 사용자 데이터 초기화
        init_default_data(db_manager, user_id)
        
        # DB 매니저 종료 (SQLite인 경우만)
        if DB_URL.startswith("sqlite"):
            db_manager.close()
        
        logger.info(f"DB 초기화 완료: {user_id}")
        return True
    
    except Exception as e:
        logger.error(f"DB 초기화 실패: {e}")
        return False

def init_default_data(db_manager, user_id: str):
    """기본 사용자 데이터 초기화"""
    try:
        with db_manager.get_connection() as conn:
            # 기본 계정 생성
            conn.execute("""
                INSERT OR IGNORE INTO accounts (user_id, virtual_krw, updated_at)
                VALUES (:user_id, 1000000, :updated_at)
            """, {"user_id": user_id, "updated_at": now_kst()})
            
            # 기본 엔진 상태 설정
            conn.execute("""
                INSERT OR IGNORE INTO engine_status (user_id, is_running, last_heartbeat)
                VALUES (:user_id, 0, :updated_at)
            """, {"user_id": user_id, "updated_at": now_kst()})
            
            # 기본 스레드 상태 설정
            conn.execute("""
                INSERT OR IGNORE INTO thread_status (user_id, is_thread_running, last_heartbeat)
                VALUES (:user_id, 0, :updated_at)
            """, {"user_id": user_id, "updated_at": now_kst()})
            
            conn.commit()
        
        logger.info(f"기본 데이터 초기화 완료: {user_id}")
    
    except Exception as e:
        logger.error(f"기본 데이터 초기화 실패: {e}")
        raise

def reset_db(user_id: str) -> bool:
    """DB 초기화 및 재생성"""
    try:
        if DB_URL.startswith("sqlite"):
            # SQLite 파일 삭제 후 재생성
            db_path = get_db_path(user_id)
            
            if os.path.exists(db_path):
                # 백업 생성
                backup_path = f"{db_path}.backup.{int(datetime.now().timestamp())}"
                shutil.copy2(db_path, backup_path)
                logger.info(f"DB 백업 생성: {backup_path}")
                
                # 기존 파일 삭제
                os.remove(db_path)
                logger.info(f"기존 DB 삭제: {db_path}")
            
            # 새로 초기화
            return initialize_db(user_id)
        
        else:
            # MySQL 테이블 초기화
            db_manager = get_db_manager()
            
            # 롤백 마이그레이션 실행
            migrations = get_migration_files()
            for version in sorted(migrations.keys(), reverse=True):
                rollback_file = migrations[version].get("rollback")
                if rollback_file and os.path.exists(rollback_file):
                    execute_sql_file(db_manager, rollback_file)
            
            # 다시 초기화
            return initialize_db(user_id)
    
    except Exception as e:
        logger.error(f"DB 리셋 실패: {e}")
        return False

def run_migration(user_id: str, target_version: Optional[str] = None) -> bool:
    """특정 버전까지 마이그레이션 실행"""
    try:
        if DB_URL.startswith("sqlite"):
            db_path = get_db_path(user_id)
            user_db_url = f"sqlite:///{db_path}"
            db_manager = get_db_manager().__class__(user_db_url)
        else:
            db_manager = get_db_manager()
        
        migrations = get_migration_files()
        
        if target_version:
            # 특정 버전까지만 실행
            target_migrations = {k: v for k, v in migrations.items() if k <= target_version}
        else:
            # 모든 마이그레이션 실행
            target_migrations = migrations
        
        for version in sorted(target_migrations.keys()):
            init_file = target_migrations[version]["init"]
            if os.path.exists(init_file):
                if not execute_sql_file(db_manager, init_file):
                    logger.error(f"마이그레이션 실행 실패: {init_file}")
                    return False
        
        if DB_URL.startswith("sqlite"):
            db_manager.close()
        
        logger.info(f"마이그레이션 실행 완료: {user_id} (버전: {target_version or '최신'})")
        return True
    
    except Exception as e:
        logger.error(f"마이그레이션 실행 실패: {e}")
        return False

def rollback_migration(user_id: str, target_version: Optional[str] = None) -> bool:
    """마이그레이션 롤백"""
    try:
        if DB_URL.startswith("sqlite"):
            db_path = get_db_path(user_id)
            user_db_url = f"sqlite:///{db_path}"
            db_manager = get_db_manager().__class__(user_db_url)
        else:
            db_manager = get_db_manager()
        
        migrations = get_migration_files()
        
        # 역순으로 롤백 실행
        for version in sorted(migrations.keys(), reverse=True):
            if target_version and version <= target_version:
                break
                
            rollback_file = migrations[version].get("rollback")
            if rollback_file and os.path.exists(rollback_file):
                if not execute_sql_file(db_manager, rollback_file):
                    logger.error(f"롤백 실행 실패: {rollback_file}")
                    return False
        
        if DB_URL.startswith("sqlite"):
            db_manager.close()
        
        logger.info(f"마이그레이션 롤백 완료: {user_id} (버전: {target_version or '초기'})")
        return True
    
    except Exception as e:
        logger.error(f"마이그레이션 롤백 실패: {e}")
        return False

def check_db_health(user_id: str) -> bool:
    """DB 헬스 체크"""
    try:
        if DB_URL.startswith("sqlite"):
            db_path = get_db_path(user_id)
            if not os.path.exists(db_path):
                logger.warning(f"DB 파일이 존재하지 않습니다: {db_path}")
                return False
            
            user_db_url = f"sqlite:///{db_path}"
            db_manager = get_db_manager().__class__(user_db_url)
        else:
            db_manager = get_db_manager()
        
        # 기본 헬스 체크
        health_ok = db_manager.health_check()
        
        # 테이블 존재 확인
        if health_ok:
            try:
                with db_manager.get_connection() as conn:
                    result = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in result.fetchall()]
                    
                    required_tables = ['users', 'accounts', 'orders', 'logs', 'account_positions']
                    missing_tables = [table for table in required_tables if table not in tables]
                    
                    if missing_tables:
                        logger.warning(f"필요한 테이블이 누락되었습니다: {missing_tables}")
                        health_ok = False
            except Exception as e:
                logger.error(f"테이블 확인 실패: {e}")
                health_ok = False
        
        if DB_URL.startswith("sqlite"):
            db_manager.close()
        
        return health_ok
    
    except Exception as e:
        logger.error(f"DB 헬스 체크 실패: {e}")
        return False

def get_db_info(user_id: str) -> dict:
    """DB 정보 가져오기"""
    try:
        db_path = get_db_path(user_id)
        info = {
            "user_id": user_id,
            "db_path": db_path,
            "db_type": "sqlite" if DB_URL.startswith("sqlite") else "mysql",
            "db_exists": os.path.exists(db_path) if DB_URL.startswith("sqlite") else True,
            "db_size": 0
        }
        
        if info["db_exists"] and DB_URL.startswith("sqlite"):
            info["db_size"] = os.path.getsize(db_path)
        
        return info
    
    except Exception as e:
        logger.error(f"DB 정보 가져오기 실패: {e}")
        return {"error": str(e)}

# 호환성 유지를 위한 기존 함수들
def reset_db_legacy(user_id: str):
    """기존 호환성을 위한 리셋 함수"""
    reset_db(user_id)

def initialize_db_legacy(user_id: str):
    """기존 호환성을 위한 초기화 함수"""
    initialize_db(user_id)