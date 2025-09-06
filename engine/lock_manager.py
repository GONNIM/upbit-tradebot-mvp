# FINAL CODE
# engine/lock_manager.py

import threading
import time
import logging
from typing import Dict, Optional, Set
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

from services.logger import get_logger
from services.db import insert_log, get_db_manager
from config import DEFAULT_USER_ID
from utils.logging_util import log_to_file

# 로거 설정
logger = get_logger(__name__)

# 락 타입 열거형
class LockType(Enum):
    ENGINE = "engine"        # 엔진 실행 락
    TRADING = "trading"      # 거래 실행 락
    DATABASE = "database"     # DB 접근 락
    FEED = "feed"           # 피드 데이터 락
    STRATEGY = "strategy"   # 전략 실행 락
    RESOURCE = "resource"   # 리소스 접근 락

# 락 상태 열거형
class LockStatus(Enum):
    FREE = "free"           # 사용 가능
    ACQUIRED = "acquired"   # 획득됨
    WAITING = "waiting"     # 대기 중
    TIMEOUT = "timeout"     # 타임아웃
    ERROR = "error"         # 에러 상태

@dataclass
class LockInfo:
    """락 정보 데이터 클래스"""
    user_id: str
    lock_type: LockType
    status: LockStatus
    acquired_by: Optional[str] = None
    acquired_time: Optional[float] = None
    timeout: float = 30.0
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    last_access: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.acquired_time is None and self.status == LockStatus.ACQUIRED:
            self.acquired_time = time.time()

@dataclass
class LockConfig:
    """락 관리자 설정"""
    default_timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 0.1
    cleanup_interval: float = 300.0  # 5분
    enable_monitoring: bool = True
    log_lock_operations: bool = True
    deadlock_detection: bool = True
    priority_mode: bool = True

# 향상된 락 클래스
class EnhancedLock:
    """향상된 기능을 가진 락 클래스"""
    
    def __init__(self, lock_type: LockType, user_id: str, config: LockConfig):
        self.lock_type = lock_type
        self.user_id = user_id
        self.config = config
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._info = LockInfo(
            user_id=user_id,
            lock_type=lock_type,
            status=LockStatus.FREE,
            timeout=config.default_timeout
        )
        self._wait_queue = []
        self._access_history = []
        self._lock_acquires = 0
        self._lock_releases = 0
        
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None, 
                priority: int = 0) -> bool:
        """락 획득"""
        if timeout is None:
            timeout = self.config.default_timeout
            
        start_time = time.time()
        acquired = False
        
        try:
            with self._condition:
                if not blocking:
                    acquired = self._try_acquire(priority)
                else:
                    acquired = self._wait_for_acquire(timeout, priority)
                    
                if acquired:
                    self._update_acquired_info(priority)
                    self._log_operation("ACQUIRE", success=True)
                    
                return acquired
                
        except Exception as e:
            self._info.status = LockStatus.ERROR
            self._log_operation("ACQUIRE", success=False, error=e)
            logger.error(f"락 획득 실패: {self.user_id}, {self.lock_type.value}, {e}")
            return False
    
    def _try_acquire(self, priority: int) -> bool:
        """락 획득 시도"""
        if self._info.status == LockStatus.FREE:
            if self.config.priority_mode and self._wait_queue:
                # 우선순위 확인
                highest_priority = min(self._wait_queue, key=lambda x: x[1])
                if priority < highest_priority[1]:
                    return False
                    
            self._info.status = LockStatus.ACQUIRED
            self._info.acquired_by = f"thread_{threading.current_thread().ident}"
            return True
        return False
    
    def _wait_for_acquire(self, timeout: float, priority: int) -> bool:
        """락 획득 대기"""
        thread_id = threading.current_thread().ident
        self._wait_queue.append((thread_id, priority))
        
        try:
            end_time = time.time() + timeout
            while time.time() < end_time:
                if self._try_acquire(priority):
                    return True
                    
                # 우선순위별 대기 시간 조정
                wait_time = self.config.retry_delay * (1 + priority * 0.1)
                self._condition.wait(wait_time)
                
                # 데드락 감지
                if self.config.deadlock_detection and self._detect_deadlock():
                    logger.warning(f"데드락 감지: {self.user_id}, {self.lock_type.value}")
                    break
                    
            self._info.status = LockStatus.TIMEOUT
            return False
            
        finally:
            self._wait_queue.remove((thread_id, priority))
    
    def _detect_deadlock(self) -> bool:
        """데드락 감지"""
        # 간단한 데드락 감지 로직
        if len(self._wait_queue) > 5:  # 대기 큐가 너무 길면 의심
            wait_time = time.time() - min(
                item[2] for item in self._wait_queue if len(item) > 2
            ) if self._wait_queue and len(self._wait_queue[0]) > 2 else 0
            return wait_time > self.config.default_timeout * 2
        return False
    
    def release(self) -> bool:
        """락 해제"""
        try:
            with self._condition:
                if self._info.status == LockStatus.ACQUIRED:
                    self._info.status = LockStatus.FREE
                    self._info.acquired_by = None
                    self._info.acquired_time = None
                    self._lock_releases += 1
                    self._log_operation("RELEASE", success=True)
                    self._condition.notify_all()
                    return True
                else:
                    logger.warning(f"락이 획득 상태가 아님: {self.user_id}, {self.lock_type.value}")
                    return False
                    
        except Exception as e:
            self._log_operation("RELEASE", success=False, error=e)
            logger.error(f"락 해제 실패: {self.user_id}, {self.lock_type.value}, {e}")
            return False
    
    def _update_acquired_info(self, priority: int):
        """락 획득 정보 업데이트"""
        self._info.acquired_time = time.time()
        self._info.priority = priority
        self._info.retry_count = 0
        self._lock_acquires += 1
        self._access_history.append({
            'timestamp': time.time(),
            'operation': 'acquire',
            'thread_id': threading.current_thread().ident,
            'priority': priority
        })
    
    def _log_operation(self, operation: str, success: bool, error: Optional[Exception] = None):
        """락 작업 로깅"""
        if self.config.log_lock_operations:
            log_msg = (
                f"Lock {operation}: {self.user_id}, {self.lock_type.value}, "
                f"thread={threading.current_thread().ident}, "
                f"success={success}"
            )
            if error:
                log_msg += f", error={error}"
                
            logger.info(log_msg)
            
            # DB 로깅
            try:
                insert_log(self.user_id, "LOCK", log_msg)
                log_to_file(log_msg, self.user_id)
            except Exception:
                pass
    
    def locked(self) -> bool:
        """락 상태 확인"""
        return self._info.status == LockStatus.ACQUIRED
    
    def get_info(self) -> Dict[str, any]:
        """락 정보 반환"""
        return {
            'user_id': self.user_id,
            'lock_type': self.lock_type.value,
            'status': self._info.status.value,
            'acquired_by': self._info.acquired_by,
            'acquired_time': self._info.acquired_time,
            'timeout': self._info.timeout,
            'priority': self._info.priority,
            'retry_count': self._info.retry_count,
            'queue_size': len(self._wait_queue),
            'acquires': self._lock_acquires,
            'releases': self._lock_releases,
            'last_access': self._info.last_access
        }
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# 락 관리자 클래스
class LockManager:
    """종합적인 락 관리 시스템"""
    
    def __init__(self, config: Optional[LockConfig] = None):
        self.config = config or LockConfig()
        self._locks: Dict[str, Dict[LockType, EnhancedLock]] = {}
        self._global_lock = threading.RLock()
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        
        # 모니터링 시작
        if self.config.enable_monitoring:
            self._start_monitoring()
            
        logger.info("락 관리자 초기화 완료")
    
    def get_lock(self, user_id: str, lock_type: LockType) -> EnhancedLock:
        """사용자별 락 가져오기"""
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = {}
                
            if lock_type not in self._locks[user_id]:
                self._locks[user_id][lock_type] = EnhancedLock(
                    lock_type, user_id, self.config
                )
                
            return self._locks[user_id][lock_type]
    
    def acquire_lock(self, user_id: str, lock_type: LockType, 
                    blocking: bool = True, timeout: Optional[float] = None,
                    priority: int = 0) -> bool:
        """락 획득"""
        lock = self.get_lock(user_id, lock_type)
        return lock.acquire(blocking, timeout, priority)
    
    def release_lock(self, user_id: str, lock_type: LockType) -> bool:
        """락 해제"""
        with self._global_lock:
            if user_id in self._locks and lock_type in self._locks[user_id]:
                return self._locks[user_id][lock_type].release()
            return False
    
    def is_locked(self, user_id: str, lock_type: LockType) -> bool:
        """락 상태 확인"""
        with self._global_lock:
            if user_id in self._locks and lock_type in self._locks[user_id]:
                return self._locks[user_id][lock_type].locked()
            return False
    
    def get_lock_info(self, user_id: str, lock_type: LockType) -> Optional[Dict[str, any]]:
        """락 정보 가져오기"""
        with self._global_lock:
            if user_id in self._locks and lock_type in self._locks[user_id]:
                return self._locks[user_id][lock_type].get_info()
            return None
    
    def get_all_locks_info(self) -> Dict[str, Dict[str, Dict[str, any]]]:
        """모든 락 정보 가져오기"""
        with self._global_lock:
            result = {}
            for user_id, locks in self._locks.items():
                result[user_id] = {
                    lock_type.value: lock.get_info() 
                    for lock_type, lock in locks.items()
                }
            return result
    
    def release_all_locks(self, user_id: str) -> int:
        """사용자의 모든 락 해제"""
        with self._global_lock:
            if user_id not in self._locks:
                return 0
                
            released_count = 0
            for lock in self._locks[user_id].values():
                if lock.locked():
                    lock.release()
                    released_count += 1
                    
            return released_count
    
    def cleanup_expired_locks(self):
        """만료된 락 정리"""
        with self._global_lock:
            current_time = time.time()
            cleaned_count = 0
            
            for user_id, locks in list(self._locks.items()):
                for lock_type, lock in list(locks.items()):
                    info = lock.get_info()
                    
                    # 타임아웃된 락 정리
                    if (info['status'] == 'acquired' and 
                        info['acquired_time'] and 
                        current_time - info['acquired_time'] > info['timeout']):
                        lock.release()
                        cleaned_count += 1
                        
                    # 오랫동안 사용되지 않은 락 정리
                    elif (info['status'] == 'free' and 
                          current_time - info['last_access'] > self.config.cleanup_interval):
                        del locks[lock_type]
                        cleaned_count += 1
                        
                # 빈 사용자 락 딕셔너리 정리
                if not locks:
                    del self._locks[user_id]
                    
            if cleaned_count > 0:
                logger.info(f"락 정리 완료: {cleaned_count}개 락 정리됨")
                
            return cleaned_count
    
    def _start_monitoring(self):
        """모니터링 스레드 시작"""
        def cleanup_worker():
            while not self._stop_cleanup.wait(self.config.cleanup_interval):
                try:
                    self.cleanup_expired_locks()
                except Exception as e:
                    logger.error(f"락 정리 중 에러: {e}")
                    
        self._cleanup_thread = threading.Thread(
            target=cleanup_worker,
            daemon=True,
            name="lock_cleanup"
        )
        self._cleanup_thread.start()
    
    def stop_monitoring(self):
        """모니터링 중지"""
        if self._cleanup_thread:
            self._stop_cleanup.set()
            self._cleanup_thread.join(timeout=5)
    
    def __del__(self):
        """소멸자"""
        self.stop_monitoring()

# 컨텍스트 매니저
@contextmanager
def acquire_locks(lock_manager: LockManager, user_id: str, 
                 lock_types: List[LockType], timeout: Optional[float] = None):
    """여러 락을 안전하게 획득하는 컨텍스트 매니저"""
    acquired_locks = []
    
    try:
        # 락 획득
        for lock_type in lock_types:
            if lock_manager.acquire_lock(user_id, lock_type, timeout=timeout):
                acquired_locks.append(lock_type)
            else:
                # 실패 시 이미 획득한 락 해제
                for acquired_type in acquired_locks:
                    lock_manager.release_lock(user_id, acquired_type)
                raise RuntimeError(f"락 획득 실패: {lock_type.value}")
                
        yield acquired_locks
        
    finally:
        # 락 해제
        for lock_type in acquired_locks:
            lock_manager.release_lock(user_id, lock_type)

# 전역 락 관리자 인스턴스
_global_lock_manager = None

def get_lock_manager() -> LockManager:
    """전역 락 관리자 인스턴스 가져오기"""
    global _global_lock_manager
    if _global_lock_manager is None:
        _global_lock_manager = LockManager()
    return _global_lock_manager

# 호환성 함수 (기존 코드와의 호환을 위해)
def get_user_lock(user_id: str) -> EnhancedLock:
    """사용자 엔진 락 가져오기 (호환성)"""
    lock_manager = get_lock_manager()
    return lock_manager.get_lock(user_id, LockType.ENGINE)

def cleanup_all_locks():
    """모든 락 정리"""
    lock_manager = get_lock_manager()
    lock_manager.cleanup_expired_locks()

def get_locks_status() -> Dict[str, Dict[str, Dict[str, any]]]:
    """모든 락 상태 확인"""
    lock_manager = get_lock_manager()
    return lock_manager.get_all_locks_info()

# 데코레이터
def with_lock(lock_type: LockType, timeout: Optional[float] = None):
    """락을 적용하는 데코레이터"""
    def decorator(func):
        def wrapper(user_id: str, *args, **kwargs):
            lock_manager = get_lock_manager()
            try:
                if lock_manager.acquire_lock(user_id, lock_type, timeout=timeout):
                    result = func(user_id, *args, **kwargs)
                    return result
                else:
                    raise RuntimeError(f"락 획득 실패: {lock_type.value}")
            finally:
                lock_manager.release_lock(user_id, lock_type)
        return wrapper
    return decorator

# 사용 예제
if __name__ == "__main__":
    # 락 관리자 생성
    manager = LockManager()
    
    # 락 사용 예제
    user_id = "test_user"
    
    # 단일 락 사용
    if manager.acquire_lock(user_id, LockType.ENGINE):
        try:
            print("엔진 락 획득 성공")
            # 작업 수행
        finally:
            manager.release_lock(user_id, LockType.ENGINE)
    
    # 컨텍스트 매니저 사용
    with acquire_locks(manager, user_id, [LockType.TRADING, LockType.DATABASE]):
        print("트레이딩과 DB 락 획득 성공")
        # 작업 수행
    
    # 데코레이터 사용
    @with_lock(LockType.STRATEGY)
    def strategy_function(user_id: str, data: dict):
        print(f"전략 함수 실행: {user_id}")
        return {"result": "success"}
    
    result = strategy_function(user_id, {"data": "test"})
    print(result)