import threading
import queue
import logging
import time

from engine.params import load_params
from engine.live_loop import run_live_loop
from engine.lock_manager import get_user_lock
from engine.global_state import (
    add_engine_thread,
    remove_engine_thread,
    update_engine_status,
    update_event_time,
    get_engine_threads,
    is_engine_really_running,
)
from core.trader import UpbitTrader
from services.db import (
    set_engine_status,
    set_thread_status,
    insert_log,
)
from config import MIN_FEE_RATIO, PARAMS_JSON_FILENAME, DEFAULT_USER_ID
from utils.logging_util import log_to_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class EngineManager:
    def __init__(self):
        self._locks = {}
        self._threads = {}
        self._events = {}
        self._global_lock = threading.Lock()

    def _ensure_user_resources(self, user_id):
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            if user_id not in self._events:
                self._events[user_id] = threading.Event()

    def is_running(self, user_id):
        thread = self._threads.get(user_id)
        return thread is not None and thread.is_alive()

    def start_engine(self, user_id, test_mode=True, restart_count=0):
        self._ensure_user_resources(user_id)

        if self.is_running(user_id):
            return False

        with self._locks[user_id]:
            if self.is_running(user_id):
                return False

            stop_event = self._events[user_id] = threading.Event()
            
            # 🔄 재시작 카운터 추가
            if not hasattr(self, '_restart_counts'):
                self._restart_counts = {}
            self._restart_counts[user_id] = restart_count
            
            thread = threading.Thread(
                target=self._engine_runner_with_recovery,
                kwargs={
                    "user_id": user_id,
                    "stop_event": stop_event,
                    "test_mode": test_mode,
                    "restart_count": restart_count,
                },
                daemon=True,
                name=f"engine_runner_{user_id}",
            )
            thread.start()
            self._threads[user_id] = thread
            return True

    def stop_engine(self, user_id):
        if user_id in self._events:
            self._events[user_id].set()
        if user_id in self._threads:
            self._threads[user_id].join(timeout=2)

        self._locks.pop(user_id, None)
        self._threads.pop(user_id, None)
        self._events.pop(user_id, None)

        set_engine_status(user_id, False)
        set_thread_status(user_id, False)
        update_engine_status(user_id, "stopped")
        remove_engine_thread(user_id)
        log_to_file(f"🔌 엔진 종료 요청됨: user_id={user_id}", user_id)

    def _engine_runner_with_recovery(self, user_id, stop_event, test_mode=True, restart_count=0):
        """
        🔄 24시간 안정성: 예외 발생 시 자동 재시작 메커니즘
        최대 3회까지 재시도 (1분, 5분, 15분 간격)
        """
        MAX_RESTART_ATTEMPTS = 3
        RESTART_DELAYS = [60, 300, 900]  # 1분, 5분, 15분
        
        try:
            self._engine_runner(user_id, stop_event, test_mode)
        except Exception as e:
            if restart_count < MAX_RESTART_ATTEMPTS and not stop_event.is_set():
                delay = RESTART_DELAYS[restart_count] if restart_count < len(RESTART_DELAYS) else 900
                msg = f"🔄 엔진 예외 발생, {delay}초 후 재시작 ({restart_count + 1}/{MAX_RESTART_ATTEMPTS}): {e}"
                logger.error(msg)
                insert_log(user_id, "ERROR", msg)
                log_to_file(msg, user_id)
                
                # 지연 후 재시작
                time.sleep(delay)
                if not stop_event.is_set():
                    # 자기 자신을 재시작
                    self.start_engine(user_id, test_mode, restart_count + 1)
            else:
                msg = f"❌ 엔진 최종 실패: 재시작 횟수 초과 또는 사용자 중단 요청"
                logger.critical(msg)
                insert_log(user_id, "CRITICAL", msg)
                log_to_file(msg, user_id)

    def _engine_runner(self, user_id, stop_event, test_mode=True):
        logger.info(f"[DEBUG] engine_runner 시작됨 → user_id={user_id}")

        user_lock = get_user_lock(user_id)
        if not user_lock.acquire(blocking=False):
            msg = f"⚠️ 이미 실행 중인 트레이딩 엔진: {user_id} (Lock으로 차단됨)"
            insert_log(user_id, "INFO", msg)
            log_to_file(msg, user_id)
            return

        q = queue.Queue()
        try:
            params = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}")
            trader = UpbitTrader(
                user_id, risk_pct=params.order_ratio, test_mode=test_mode
            )

            update_engine_status(user_id, "running")
            set_engine_status(user_id, True)
            set_thread_status(user_id, True)

            worker = threading.Thread(
                target=run_live_loop,
                args=(params, q, trader, stop_event, test_mode, user_id),
                daemon=True,
                name=f"run_live_loop_{user_id}",
            )

            try:
                from streamlit.runtime.scriptrunner import add_script_run_ctx

                add_script_run_ctx(worker)
            except Exception:
                logger.warning(f"⚠️ ScriptRunContext 주입 실패: {user_id}")

            worker.start()
            add_engine_thread(user_id, worker, stop_event)

            insert_log(user_id, "INFO", f"🚀 트레이딩 엔진 시작됨: user_id={user_id}")
            log_to_file(f"🚀 트레이딩 엔진 시작됨: user_id={user_id}", user_id)

            while not stop_event.is_set():
                try:
                    event = q.get(timeout=0.5)
                    self._process_event(
                        user_id, event, params.upbit_ticker, params.order_ratio
                    )
                except queue.Empty:
                    continue
                except Exception as e:
                    msg = f"이벤트 처리 중 예외: {e}"
                    insert_log(user_id, "ERROR", msg)
                    log_to_file(msg, user_id)

        except Exception as e:
            msg = f"❌ 엔진 예외: {e}"
            logger.exception(msg)
            insert_log(user_id, "ERROR", msg)
            log_to_file(msg, user_id)
            update_engine_status(user_id, "error", note=msg)
            # 🔄 예외 상위로 전파 (재시작 메커니즘 활성화)
            raise

        finally:
            stop_event.set()
            set_engine_status(user_id, False)
            set_thread_status(user_id, False)
            update_engine_status(user_id, "stopped")
            remove_engine_thread(user_id)
            user_lock.release()

            msg = f"🛑 트레이딩 엔진 종료됨: user_id={user_id}"
            log_to_file(msg, user_id)
            insert_log(user_id, "INFO", msg)

    def _process_event(self, user_id, event, ticker, order_ratio):
        try:
            event_type = event[1]

            if event_type == "LOG":
                _, _, log_msg = event
                insert_log(user_id, "LOG", log_msg)
                log_to_file(log_msg, user_id)

            elif event_type in ("BUY", "SELL"):
                ts, _, qty, price, cross, macd, signal = event[:7]
                amount = qty * price
                fee = amount * MIN_FEE_RATIO
                insert_log(
                    user_id,
                    event_type,
                    f"{event_type} signal: {qty:.6f} @ {price:,.2f} = {amount:,.2f} (fee={fee:,.2f})",
                )
                insert_log(
                    user_id,
                    event_type,
                    f"{event_type} signal: cross={cross} macd={macd} signal={signal}",
                )
                update_event_time(user_id)

            elif event_type == "EXCEPTION":
                _, exc_type, exc_value, tb = event
                msg = f"❌ 예외 발생: {exc_type.__name__}: {exc_value}"
                insert_log(user_id, "ERROR", msg)
                log_to_file(msg, user_id)

            else:
                msg = f"⚠️ 알 수 없는 이벤트 무시됨: {event}"
                insert_log(user_id, "WARN", msg)
                log_to_file(msg, user_id)

        except Exception as e:
            msg = f"❌ process_event() 예외: {e} | event={event}"
            insert_log(user_id, "ERROR", msg)
            log_to_file(msg, user_id)

    def get_active_user_ids(self):
        return list(self._threads.keys())


# ✅ 전역 인스턴스
engine_manager = EngineManager()
