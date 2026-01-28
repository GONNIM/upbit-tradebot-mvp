import threading
import queue
import logging
import time

try:
    import streamlit as st
except Exception:
    class _Dummy: session_state = {}
    st = _Dummy()

from engine.params import load_params
from engine.live_loop import run_live_loop
from engine.lock_manager import get_user_lock
from engine.global_state import (
    add_engine_thread,
    remove_engine_thread,
    update_engine_status,
    update_event_time,
)
from core.trader import UpbitTrader
from services.db import (
    set_engine_status,
    set_thread_status,
    insert_log,
)
from config import MIN_FEE_RATIO, PARAMS_JSON_FILENAME, DEFAULT_USER_ID
from utils.logging_util import log_to_file

from engine.reconciler_singleton import get_reconciler
from services.db import fetch_inflight_orders


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


MODE_TEST = "TEST"
MODE_LIVE = "LIVE"


def current_mode() -> str:
    """세션에 저장된 모드를 전역에서 참조 (기본 TEST)."""
    m = str(st.session_state.get("mode", MODE_TEST)).upper()
    return m if m in (MODE_TEST, MODE_LIVE) else MODE_TEST


def is_live_mode() -> bool:
    return current_mode() == MODE_LIVE


def _user_key(user_id: str, captured_mode: str) -> str:
    """
    user_id 기준으로 엔진 키를 만든다.

    ⚠️ 현재 구현에서는 TEST/LIVE 동시 실행을 허용하지 않고
    "유저당 엔진 1개"를 강제하기 위해 모드를 키에 포함하지 않는다.
    (동시 실행을 분리하고 싶다면 아래 주석을 다시 살리면 됨)

    # return f"{user_id}:{captured_mode}"
    """
    return user_id


class EngineManager:
    def __init__(self):
        self._locks = {}
        self._threads = {}
        self._events = {}
        self._global_lock = threading.Lock()
        self._restart_counts = {}
        self._live_engine_count = 0
        # user_key(_user_key) → 마지막으로 실행된 모드(TEST/LIVE)
        self._engine_mode: dict[str, str] = {}

    def _ensure_user_resources(self, user_id, captured_mode: str):
        key = _user_key(user_id, captured_mode)
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            if key not in self._events:
                self._events[key] = threading.Event()

    def is_running(self, user_id):
        """
        현재 UI에 세팅된 모드 기준으로 엔진 실행 여부 확인.

        ⚠️ _user_key가 user_id만 쓰고 있기 때문에,
        실질적으로는 "해당 유저에 대해 어떤 모드든 엔진이 도는지" 체크하는 셈이다.
        """
        m = current_mode()
        key = _user_key(user_id, m)
        t = self._threads.get(key)
        return t is not None and t.is_alive()

    def start_engine(
        self,
        user_id: str,
        test_mode: bool | None = None,
        restart_count: int = 0,
    ) -> bool:
        """
        UI에서 설정된 모드를 캡처해서 엔진을 시작한다.

        - captured_mode: 버튼을 누른 시점의 모드(TEST/LIVE)
        - test_mode:
            * 명시되면 그 값 우선
            * None이면 captured_mode가 LIVE면 False, 그 외에는 True
        """
        captured_mode = current_mode()
        tm = (test_mode if test_mode is not None else (captured_mode != MODE_LIVE))

        # LIVE 모드 Reconciler 기동 및 미체결 로딩
        if captured_mode == MODE_LIVE:
            rec = get_reconciler()
            rec.start()  # Idempotent: 이미 실행 중이면 자동 스킵
            if self._live_engine_count == 0:
                rec.load_inflight_from_db(fetch_inflight_orders)
            self._live_engine_count += 1  # ✅ FIX: SET → INCREMENT

        return self._start_engine_internal(user_id, tm, restart_count, captured_mode)
    
    def _start_engine_internal(
        self,
        user_id: str,
        test_mode: bool,
        restart_count: int,
        captured_mode: str,
    ) -> bool:
        self._ensure_user_resources(user_id, captured_mode)

        key = _user_key(user_id, captured_mode)
        if self._threads.get(key) and self._threads[key].is_alive():
            # 이미 해당 유저에 대한 엔진이 동작 중
            return False

        with self._locks[key]:
            if self._threads.get(key) and self._threads[key].is_alive():
                return False

            stop_event = self._events[key] = threading.Event()
            self._restart_counts[key] = restart_count

            # 현재 user_key가 어느 모드로 실행 중인지 기록
            self._engine_mode[key] = captured_mode
            
            thread = threading.Thread(
                target=self._engine_runner_with_recovery,
                kwargs=dict(
                    user_id=user_id,
                    stop_event=stop_event,
                    test_mode=test_mode,
                    restart_count=restart_count,
                    captured_mode=captured_mode,
                ),
                daemon=True,
                name=f"engine_runner_{user_id}_{captured_mode}",
            )
            thread.start()
            self._threads[key] = thread
            return True

    def stop_engine(self, user_id):
        """
        현재 UI 모드 기준으로 엔진을 정지.
        (_user_key가 user_id만 쓰므로, 사실상 "해당 유저의 엔진 전부"를 의미)
        """
        ui_mode = current_mode()
        key = _user_key(user_id, ui_mode)

        # 실제 실행 중이던 모드 (TEST/LIVE) 복원
        running_mode = self._engine_mode.get(key, ui_mode)

        if key in self._events:
            self._events[key].set()
        if key in self._threads:
            self._threads[key].join(timeout=10)  # ✅ 2초 → 10초 (warmup 백테스트 완료 대기)

        # 내부 상태 정리
        self._locks.pop(key, None)
        self._threads.pop(key, None)
        self._events.pop(key, None)
        self._restart_counts.pop(key, None)
        self._engine_mode.pop(key, None)

        # 상태 DB / 글로벌 스테이트 업데이트
        set_engine_status(user_id, False)
        set_thread_status(user_id, False)
        update_engine_status(user_id, "stopped")
        remove_engine_thread(user_id)

        msg = f"🔌 엔진 종료 요청됨: user_id={user_id}, mode={running_mode}"
        log_to_file(msg, user_id)
        insert_log(user_id, "INFO", msg)

        # LIVE 엔진 카운트 / Reconciler 중지 처리
        if running_mode == MODE_LIVE:
            self._live_engine_count = max(0, self._live_engine_count - 1)
            if self._live_engine_count == 0:
                try:
                    get_reconciler().stop()
                except Exception:
                    pass

    def _engine_runner_with_recovery(
        self,
        user_id: str,
        stop_event: threading.Event,
        test_mode: bool,
        restart_count: int,
        captured_mode: str,
    ):
        """
        🔄 24시간 안정성: 예외 발생 시 자동 재시작 메커니즘
        최대 3회까지 재시도 (1분, 5분, 15분 간격)
        """
        MAX_RESTART_ATTEMPTS = 3
        RESTART_DELAYS = [60, 300, 900]  # 1분, 5분, 15분
        
        try:
            self._engine_runner(user_id, stop_event, test_mode, captured_mode)
        except Exception as e:
            key = _user_key(user_id, captured_mode)
            if restart_count < MAX_RESTART_ATTEMPTS and not stop_event.is_set():
                delay = (
                    RESTART_DELAYS[restart_count]
                    if restart_count < len(RESTART_DELAYS)
                    else 900
                )
                msg = (
                    f"🔄 엔진 예외 발생, {delay}초 후 재시작 "
                    f"({restart_count + 1}/{MAX_RESTART_ATTEMPTS}): {e}"
                )
                logger.error(msg)
                insert_log(user_id, "ERROR", msg)
                log_to_file(msg, user_id)
                
                time.sleep(delay)
                if not stop_event.is_set():
                    self._start_engine_internal(
                        user_id=user_id,
                        test_mode=test_mode,
                        restart_count=restart_count + 1,
                        captured_mode=captured_mode,
                    )
            else:
                msg = f"❌ 엔진 최종 실패: 재시작 횟수 초과 또는 사용자 중단 요청"
                logger.critical(msg)
                insert_log(user_id, "CRITICAL", msg)
                log_to_file(msg, user_id)

    def _engine_runner(
        self,
        user_id: str,
        stop_event: threading.Event,
        test_mode: bool,
        captured_mode: str,
    ):
        logger.info(f"[DEBUG] engine_runner 시작 → user_id={user_id}, mode={captured_mode}")

        lock_id = _user_key(user_id, captured_mode)
        user_lock = get_user_lock(lock_id)
        if not user_lock.acquire(blocking=False):
            msg = f"⚠️ 이미 실행 중: {lock_id} (Lock 차단)"
            insert_log(user_id, "INFO", msg)
            log_to_file(msg, user_id)
            return

        q: queue.Queue = queue.Queue()
        try:
            # ✅ 전략 타입 결정 우선순위:
            #    1) 세션에 저장된 strategy_type
            #    2) 활성 전략 파일 ({user_id}_active_strategy.txt)
            #    3) EMA/MACD 파일 중 최신 파일의 strategy_type
            #    4) DEFAULT_STRATEGY_TYPE (MACD)
            from config import DEFAULT_STRATEGY_TYPE
            from engine.params import load_active_strategy
            import os
            from pathlib import Path

            session_strategy = st.session_state.get("strategy_type", None)

            if session_strategy:
                # 1) 세션에 있으면 그것 사용
                strategy_type = str(session_strategy).upper().strip()
                logger.info(f"[ENGINE] Using strategy from session: {strategy_type}")
            else:
                # 2) 활성 전략 파일 확인
                active_strategy = load_active_strategy(user_id)
                if active_strategy:
                    strategy_type = active_strategy
                    logger.info(f"[ENGINE] Using strategy from active strategy file: {strategy_type}")
                else:
                    # 3) 세션에도 없고 활성 전략 파일도 없으면 파일 mtime 기반 결정
                    base_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
                    ema_path = f"{user_id}_latest_params_EMA.json"
                    macd_path = f"{user_id}_latest_params_MACD.json"

                    ema_exists = os.path.exists(ema_path)
                    macd_exists = os.path.exists(macd_path)

                    if ema_exists and macd_exists:
                        # 둘 다 있으면 최신 파일 사용
                        ema_mtime = os.path.getmtime(ema_path)
                        macd_mtime = os.path.getmtime(macd_path)
                        strategy_type = "EMA" if ema_mtime > macd_mtime else "MACD"
                        logger.info(f"[ENGINE] Both files exist, using latest by mtime: {strategy_type}")
                    elif ema_exists:
                        strategy_type = "EMA"
                        logger.info(f"[ENGINE] Only EMA file exists, using EMA")
                    elif macd_exists:
                        strategy_type = "MACD"
                        logger.info(f"[ENGINE] Only MACD file exists, using MACD")
                    else:
                        # 4) 둘 다 없으면 기본값 사용
                        strategy_type = DEFAULT_STRATEGY_TYPE
                        logger.info(f"[ENGINE] No strategy files, using default: {strategy_type}")

            # ✅ 전략 타입을 전달하여 올바른 파일 로드
            params = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}", strategy_type=strategy_type)

            if params is None:
                msg = f"❌ 파라미터 로드 실패: {user_id}, strategy={strategy_type}"
                logger.error(msg)
                insert_log(user_id, "ERROR", msg)
                return

            logger.info(f"[ENGINE] Loaded params: strategy_type={params.strategy_type}")

            trader = UpbitTrader(
                user_id, risk_pct=params.order_ratio, test_mode=test_mode
            )

            update_engine_status(user_id, "running")
            set_engine_status(user_id, True)
            set_thread_status(user_id, True)

            # 실제 매매 루프 (MACD/EMA 공통) 실행 스레드
            worker = threading.Thread(
                target=run_live_loop,
                args=(params, q, trader, stop_event, test_mode, user_id),
                daemon=True,
                name=f"run_live_loop_{user_id}_{captured_mode}",
            )

            # Streamlit 컨텍스트 부여 (UI 연동용)
            try:
                from streamlit.runtime.scriptrunner import add_script_run_ctx
                add_script_run_ctx(worker)
            except Exception:
                logger.warning(f"⚠️ ScriptRunContext 주입 실패: {user_id}")

            worker.start()
            add_engine_thread(user_id, worker, stop_event)

            insert_log(user_id, "INFO", f"🚀 엔진 시작: user_id={user_id}, mode={captured_mode}")
            log_to_file(f"🚀 엔진 시작: user_id={user_id}, mode={captured_mode}", user_id)

            # run_live_loop → q 로 들어오는 이벤트 처리 루프
            while not stop_event.is_set():
                try:
                    event = q.get(timeout=0.5)
                    self._process_event(
                        user_id,
                        event,
                        params.upbit_ticker,
                        params.order_ratio,
                        captured_mode
                    )
                except queue.Empty:
                    continue
                except Exception as e:
                    msg = f"이벤트 처리 예외(mode={captured_mode}): {e}"
                    insert_log(user_id, "ERROR", msg)
                    log_to_file(msg, user_id)
        except Exception as e:
            msg = f"❌ 엔진 예외(mode={captured_mode}): {e}"
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

            msg = f"🛑 엔진 종료: user_id={user_id}, mode={captured_mode}"
            log_to_file(msg, user_id)
            insert_log(user_id, "INFO", msg)

    def _process_event(
        self,
        user_id: str,
        event,
        ticker: str,
        order_ratio: float,
        captured_mode: str
    ):
        """
        run_live_loop → q.put(...) 으로 넘어온 이벤트를 처리.
        - LOG
        - BUY / SELL
        - EXCEPTION
        """
        try:
            event_type = event[1]

            if event_type == "LOG":
                _, _, log_msg = event
                insert_log(user_id, "LOG", f"{log_msg}")
                log_to_file(f"{log_msg}", user_id)
            elif event_type in ("BUY", "SELL"):
                ts, _, qty, price, cross, macd, signal = event[:7]
                amount = qty * price
                fee = amount * MIN_FEE_RATIO
                insert_log(
                    user_id,
                    event_type,
                    f"{event_type}: {qty:.6f} @ {price:,.2f} = {amount:,.2f} (fee={fee:,.2f})",
                )
                insert_log(
                    user_id,
                    event_type,
                    f"detail: cross={cross} macd={macd} signal={signal}",
                )
                update_event_time(user_id)
            elif event_type == "EXCEPTION":
                _, _, exc_type, exc_value, tb = event
                msg = f"❌ 예외: {exc_type.__name__}: {exc_value}"
                insert_log(user_id, "ERROR", msg)
                log_to_file(msg, user_id)
            else:
                msg = f"⚠️ 알 수 없는 이벤트: {event}"
                insert_log(user_id, "WARN", msg)
                log_to_file(msg, user_id)
        except Exception as e:
            msg = f"❌ process_event 예외: {e} | event={event}"
            insert_log(user_id, "ERROR", msg)
            log_to_file(msg, user_id)

    def get_active_user_ids(self):
        """
        현재 엔진이 돌아가는 user_key 목록 반환.
        (_user_key가 user_id만 사용하므로, 실질적으로 active user_id 리스트)
        """
        return list(self._threads.keys())


# ✅ 전역 인스턴스
engine_manager = EngineManager()
