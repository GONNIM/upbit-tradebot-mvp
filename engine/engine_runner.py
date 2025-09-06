import threading
import queue
import traceback
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
import backoff
from circuitbreaker import circuit

from engine.params import load_params
from engine.live_loop import run_live_loop
from engine.lock_manager import get_user_lock, EngineLockManager
from engine.global_state import (
    add_engine_thread,
    remove_engine_thread,
    update_engine_status,
    update_event_time,
    get_engine_threads,
    is_engine_really_running
)
from core.trader import UpbitTrader
from services.db import (
    set_engine_status,
    set_thread_status,
    insert_log,
    get_db_manager
)
from services.logger import get_logger
from services.trading_control import TradingController, RiskManager
from config import MIN_FEE_RATIO, PARAMS_JSON_FILENAME, DEFAULT_USER_ID
from utils.logging_util import log_to_file


# 로거 설정
logger = get_logger(__name__)

# 데이터 클래스 정의
@dataclass
class EngineEvent:
    timestamp: float
    event_type: str
    data: Dict[str, Any]
    user_id: str
    ticker: str

@dataclass
class EngineConfig:
    user_id: str
    test_mode: bool = True
    max_retry_attempts: int = 3
    retry_delay: float = 1.0
    health_check_interval: float = 30.0
    circuit_breaker_timeout: float = 60.0
    rate_limit_requests: int = 10
    rate_limit_window: float = 1.0

# 엔진 러너 클래스
class EngineRunner:
    def __init__(self, config: EngineConfig):
        self.config = config
        self.user_id = config.user_id
        self.stop_event = threading.Event()
        self.event_queue = queue.Queue(maxsize=1000)
        self.engine_lock = get_user_lock(self.user_id)
        self.trading_controller = TradingController(self.user_id)
        self.risk_manager = RiskManager(self.user_id)
        self.db_manager = get_db_manager()
        self.stats = {
            'total_events': 0,
            'processed_events': 0,
            'failed_events': 0,
            'last_heartbeat': time.time(),
            'start_time': time.time()
        }
        self.rate_limiter = RateLimiter(config.rate_limit_requests, config.rate_limit_window)
        
    def start(self) -> bool:
        """엔진 시작"""
        try:
            # 락 획득 시도
            if not self.engine_lock.acquire(blocking=False):
                msg = f"⚠️ 이미 실행 중인 트레이딩 엔진: {self.user_id}"
                logger.warning(msg)
                insert_log(self.user_id, "WARN", msg)
                return False

            # 파라미터 로드
            params = self._load_parameters()
            if not params:
                msg = f"❌ 파라미터 로드 실패: {self.user_id}"
                logger.error(msg)
                insert_log(self.user_id, "ERROR", msg)
                self.engine_lock.release()
                return False

            # 트레이더 초기화
            trader = self._initialize_trader(params)
            if not trader:
                msg = f"❌ 트레이더 초기화 실패: {self.user_id}"
                logger.error(msg)
                insert_log(self.user_id, "ERROR", msg)
                self.engine_lock.release()
                return False

            # 엔진 상태 설정
            self._setup_engine_status()

            # 라이브 루프 스레드 시작
            self._start_live_loop(params, trader)

            # 이벤트 처리 스레드 시작
            self._start_event_processor()

            # 헬스 체크 스레드 시작
            self._start_health_monitor()

            msg = f"🚀 트레이딩 엔진 시작됨: user_id={self.user_id}"
            logger.info(msg)
            insert_log(self.user_id, "INFO", msg)
            return True

        except Exception as e:
            msg = f"❌ 엔진 시작 실패: {e}"
            logger.error(msg, exc_info=True)
            insert_log(self.user_id, "ERROR", msg)
            self._cleanup()
            return False

    def stop(self) -> bool:
        """엔진 정지"""
        try:
            self.stop_event.set()
            
            # 상태 업데이트
            set_engine_status(self.user_id, False)
            set_thread_status(self.user_id, False)
            update_engine_status(self.user_id, "stopped")
            remove_engine_thread(self.user_id)

            # 락 해제
            if self.engine_lock.locked():
                self.engine_lock.release()

            msg = f"🛑 트레이딩 엔진 종료됨: user_id={self.user_id}"
            logger.info(msg)
            insert_log(self.user_id, "INFO", msg)
            return True

        except Exception as e:
            msg = f"❌ 엔진 종료 실패: {e}"
            logger.error(msg, exc_info=True)
            insert_log(self.user_id, "ERROR", msg)
            return False

    def _load_parameters(self):
        """파라미터 로드"""
        try:
            params = load_params(f"{self.user_id}_{PARAMS_JSON_FILENAME}")
            if not params:
                logger.warning(f"파라미터 파일 없음: {self.user_id}")
                return None
            logger.info(f"파라미터 로드 성공: {self.user_id}")
            return params
        except Exception as e:
            logger.error(f"파라미터 로드 실패: {e}")
            return None

    def _initialize_trader(self, params):
        """트레이더 초기화"""
        try:
            trader = UpbitTrader(
                self.user_id, 
                risk_pct=params.order_ratio, 
                test_mode=self.config.test_mode
            )
            logger.info(f"트레이더 초기화 성공: {self.user_id}")
            return trader
        except Exception as e:
            logger.error(f"트레이더 초기화 실패: {e}")
            return None

    def _setup_engine_status(self):
        """엔진 상태 설정"""
        update_engine_status(self.user_id, "running")
        set_engine_status(self.user_id, True)
        set_thread_status(self.user_id, True)

    def _start_live_loop(self, params, trader):
        """라이브 루프 스레드 시작"""
        worker = threading.Thread(
            target=self._run_live_loop_with_circuit_breaker,
            args=(params, trader),
            daemon=True,
            name=f"run_live_loop_{self.user_id}"
        )

        # Streamlit ScriptRunContext 주입
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(worker)
        except Exception:
            logger.warning("ScriptRunContext 주입 실패")

        worker.start()
        add_engine_thread(self.user_id, worker, self.stop_event)

    def _start_event_processor(self):
        """이벤트 처리 스레드 시작"""
        processor = threading.Thread(
            target=self._event_processor_loop,
            daemon=True,
            name=f"event_processor_{self.user_id}"
        )
        processor.start()

    def _start_health_monitor(self):
        """헬스 체크 스레드 시작"""
        monitor = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True,
            name=f"health_monitor_{self.user_id}"
        )
        monitor.start()

    @circuit(failure_threshold=5, recovery_timeout=60)
    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def _run_live_loop_with_circuit_breaker(self, params, trader):
        """서킷 브레이커가 적용된 라이브 루프"""
        try:
            run_live_loop(
                params=params,
                q=self.event_queue,
                trader=trader,
                stop_event=self.stop_event,
                test_mode=self.config.test_mode,
                user_id=self.user_id
            )
        except Exception as e:
            logger.error(f"라이브 루프 실행 실패: {e}")
            raise

    def _event_processor_loop(self):
        """이벤트 처리 루프"""
        while not self.stop_event.is_set():
            try:
                event = self.event_queue.get(timeout=0.5)
                self._process_event(event)
                self.event_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"이벤트 처리 중 예외: {e}")
                self.stats['failed_events'] += 1

    def _health_monitor_loop(self):
        """헬스 체크 루프"""
        while not self.stop_event.is_set():
            try:
                time.sleep(self.config.health_check_interval)
                self._perform_health_check()
            except Exception as e:
                logger.error(f"헬스 체크 실패: {e}")

    def _perform_health_check(self):
        """헬스 체크 수행"""
        try:
            # DB 연결 확인
            db_healthy = self.db_manager.health_check()
            
            # 트레이더 상태 확인
            trader_healthy = self.trading_controller.is_healthy()
            
            # 레이트 리밋 확인
            rate_healthy = self.rate_limiter.is_healthy()
            
            if not all([db_healthy, trader_healthy, rate_healthy]):
                logger.warning(f"헬스 체크 실패: DB={db_healthy}, Trader={trader_healthy}, Rate={rate_healthy}")
                self._handle_health_failure()
            
            # 하트비트 업데이트
            self.stats['last_heartbeat'] = time.time()
            
        except Exception as e:
            logger.error(f"헬스 체크 중 예외: {e}")

    def _handle_health_failure(self):
        """헬스 체크 실패 처리"""
        msg = f"⚠️ 헬스 체크 실패: {self.user_id}"
        logger.warning(msg)
        insert_log(self.user_id, "WARN", msg)
        
        # 심각한 경우 엔진 중지 고려
        if not self.risk_manager.is_system_healthy():
            logger.critical(f"시스템 상태 불량 - 엔진 중지: {self.user_id}")
            self.stop()

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def _process_event(self, event):
        """이벤트 처리"""
        try:
            self.stats['total_events'] += 1
            
            # 레이트 리밋 체크
            if not self.rate_limiter.can_proceed():
                logger.warning(f"레이트 리밋 초과: {self.user_id}")
                return

            # 이벤트 타입별 처리
            if event[1] == "LOG":
                self._handle_log_event(event)
            elif event[1] in ("BUY", "SELL"):
                self._handle_trading_event(event)
            elif event[1] == "EXCEPTION":
                self._handle_exception_event(event)
            else:
                logger.warning(f"알 수 없는 이벤트 타입: {event}")

            self.stats['processed_events'] += 1
            
        except Exception as e:
            logger.error(f"이벤트 처리 실패: {e}")
            self.stats['failed_events'] += 1
            raise

    def _handle_log_event(self, event):
        """로그 이벤트 처리"""
        _, _, log_msg = event
        insert_log(self.user_id, "LOG", log_msg)
        log_to_file(log_msg, self.user_id)

    def _handle_trading_event(self, event):
        """거래 이벤트 처리"""
        event_type = event[1]
        ts, _, qty, price, cross, macd, signal = event[:7]
        
        # 리스크 관리 체크
        if not self.risk_manager.can_execute_trade(event_type, qty, price):
            logger.warning(f"리스크 관리로 거래 거부: {event_type}")
            return

        # 거래 실행
        amount = qty * price
        fee = amount * MIN_FEE_RATIO
        msg = f"{event_type} signal: {qty:.6f} @ {price:,.2f} = {amount:,.2f} (fee={fee:,.2f})"
        
        insert_log(self.user_id, event_type, msg)
        log_to_file(msg, self.user_id)
        
        # 상세 로그
        detail_msg = f"{event_type} signal: cross={cross} macd={macd} signal={signal}"
        insert_log(self.user_id, event_type, detail_msg)
        log_to_file(detail_msg, self.user_id)
        
        update_event_time(self.user_id)

    def _handle_exception_event(self, event):
        """예외 이벤트 처리"""
        _, exc_type, exc_value, tb = event
        err_msg = f"❌ 예외 발생: {exc_type.__name__}: {exc_value}"
        logger.error(err_msg, exc_info=tb)
        insert_log(self.user_id, "ERROR", err_msg)
        log_to_file(err_msg, self.user_id)

    def _cleanup(self):
        """정리 작업"""
        try:
            self.stop_event.set()
            set_engine_status(self.user_id, False)
            set_thread_status(self.user_id, False)
            update_engine_status(self.user_id, "stopped")
            remove_engine_thread(self.user_id)
            
            if self.engine_lock.locked():
                self.engine_lock.release()
                
        except Exception as e:
            logger.error(f"정리 작업 중 예외: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """엔진 통계 정보 반환"""
        uptime = time.time() - self.stats['start_time']
        return {
            'user_id': self.user_id,
            'uptime': uptime,
            'total_events': self.stats['total_events'],
            'processed_events': self.stats['processed_events'],
            'failed_events': self.stats['failed_events'],
            'success_rate': (self.stats['processed_events'] / max(self.stats['total_events'], 1)) * 100,
            'last_heartbeat': self.stats['last_heartbeat'],
            'is_running': not self.stop_event.is_set()
        }

# 레이트 리미터 클래스
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []
        self.lock = threading.Lock()

    def can_proceed(self) -> bool:
        """요청 가능 여부 확인"""
        with self.lock:
            now = time.time()
            # 윈도우 내 요청만 유지
            self.requests = [req_time for req_time in self.requests if now - req_time < self.window_seconds]
            
            if len(self.requests) >= self.max_requests:
                return False
            
            self.requests.append(now)
            return True

    def is_healthy(self) -> bool:
        """레이트 리미터 상태 확인"""
        with self.lock:
            now = time.time()
            recent_requests = [req_time for req_time in self.requests if now - req_time < self.window_seconds]
            return len(recent_requests) < self.max_requests

# 전역 엔진 러너 인스턴스 관리
_engine_runners = {}

def get_engine_runner(user_id: str, config: EngineConfig) -> EngineRunner:
    """엔진 러너 인스턴스 가져오기"""
    if user_id not in _engine_runners:
        _engine_runners[user_id] = EngineRunner(config)
    return _engine_runners[user_id]

def remove_engine_runner(user_id: str):
    """엔진 러너 인스턴스 제거"""
    if user_id in _engine_runners:
        runner = _engine_runners[user_id]
        runner.stop()
        del _engine_runners[user_id]

# 기존 함수 호환성 유지
def engine_runner_main(user_id=DEFAULT_USER_ID, stop_event: threading.Event = None, test_mode=True):
    """기존 호환성을 위한 엔진 러너 메인 함수"""
    config = EngineConfig(user_id=user_id, test_mode=test_mode)
    runner = get_engine_runner(user_id, config)
    
    if stop_event:
        runner.stop_event = stop_event
    
    return runner.start()

def stop_engine(user_id: str):
    """엔진 중지"""
    try:
        # 전역 스레드 레지스트리에서 중지
        threads = get_engine_threads()
        info = threads.get(user_id)
        if info:
            info["stop_event"].set()
            info["thread"].join(timeout=5)
        
        # 엔진 러너 중지
        if user_id in _engine_runners:
            _engine_runners[user_id].stop()
        
        # 상태 업데이트
        set_engine_status(user_id, False)
        set_thread_status(user_id, False)
        update_engine_status(user_id, "stopped")
        remove_engine_thread(user_id)
        
        msg = f"🔌 엔진 종료 요청됨: user_id={user_id}"
        logger.info(msg)
        insert_log(user_id, "INFO", msg)
        log_to_file(msg, user_id)
        
    except Exception as e:
        msg = f"❌ 엔진 종료 실패: {e}"
        logger.error(msg, exc_info=True)
        insert_log(user_id, "ERROR", msg)

def is_engine_running(user_id: str) -> bool:
    """엔진 실행 상태 확인"""
    return is_engine_really_running(user_id)

def get_engine_stats(user_id: str) -> Optional[Dict[str, Any]]:
    """엔진 통계 정보 가져오기"""
    if user_id in _engine_runners:
        return _engine_runners[user_id].get_stats()
    return None

def cleanup_all_engines():
    """모든 엔진 정리"""
    for user_id in list(_engine_runners.keys()):
        stop_engine(user_id)
    _engine_runners.clear()