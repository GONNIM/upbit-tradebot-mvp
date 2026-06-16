import threading
import queue
import traceback
import logging

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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def process_engine_event(user_id: str, event: tuple, ticker: str, order_ratio: float):
    try:
        event_type = event[1]

        if event_type == "LOG":
            _, _, log_msg = event
            insert_log(user_id, "LOG", log_msg)
            log_to_file(log_msg, user_id)
            return

        elif event_type in ("BUY", "SELL"):
            ts, _, qty, price, cross, macd, signal = event[:7]
            amount = qty * price
            fee = amount * MIN_FEE_RATIO
            msg = f"{event_type} signal: {qty:.6f} @ {price:,.2f} = {amount:,.2f} (fee={fee:,.2f})"
            insert_log(user_id, event_type, msg)
            log_to_file(msg, user_id)
            msg = f"{event_type} signal: cross={cross} macd={macd} signal={signal}"
            insert_log(user_id, event_type, msg)
            log_to_file(msg, user_id)
            update_event_time(user_id)

        elif event_type == "EXCEPTION":
            _, exc_type, exc_value, tb = event
            err_msg = f"❌ 예외 발생: {exc_type.__name__}: {exc_value}"
            insert_log(user_id, "ERROR", err_msg)
            log_to_file(err_msg, user_id)

        else:
            insert_log(user_id, "WARN", f"처리 불가능한 이벤트: {event}")
            log_to_file(f"⚠️ 알 수 없는 이벤트 무시됨: {event}", user_id)

    except Exception as e:
        err_msg = f"❌ process_engine_event() 예외: {e} | event={event}"
        insert_log(user_id, "ERROR", err_msg)
        log_to_file(err_msg, user_id)


def engine_runner_main(
    user_id=DEFAULT_USER_ID, stop_event: threading.Event = None, test_mode=True
):
    logger.info(f"[DEBUG] engine_runner_main 시작됨 → user_id={user_id}")

    user_lock = get_user_lock(user_id)
    if not user_lock.acquire(blocking=False):
        msg = f"⚠️ 이미 실행 중인 트레이딩 엔진: {user_id} (Lock으로 차단됨)"
        insert_log(user_id, "INFO", msg)
        log_to_file(msg, user_id)
        return

    q = queue.Queue()
    stop_event = stop_event or threading.Event()

    try:
        # ✅ 파라미터 및 트레이더 설정
        params = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}")
        trader = UpbitTrader(
            user_id, risk_pct=params.order_ratio, test_mode=test_mode,
            strategy_type=getattr(params, "strategy_type", None),  # ✅ P1
        )

        # ✅ 엔진 상태 등록
        update_engine_status(user_id, "running")
        set_engine_status(user_id, True)
        set_thread_status(user_id, True)

        # ✅ run_live_loop 스레드 정의
        worker = threading.Thread(
            target=run_live_loop,
            args=(params, q, trader, stop_event, test_mode, user_id),
            daemon=True,
            name=f"run_live_loop_{user_id}",
        )

        # ✅ Streamlit ScriptRunContext 주입 (예외 무시 가능)
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx

            add_script_run_ctx(worker)
        except Exception:
            logger.warning(
                f"⚠️ ScriptRunContext 주입 실패 (bare mode or not running in Streamlit context)"
            )

        # ✅ 스레드 실행 및 상태 등록
        worker.start()
        add_engine_thread(user_id, worker, stop_event)

        msg = f"🚀 트레이딩 엔진 시작됨: user_id={user_id}"
        log_to_file(msg, user_id)
        insert_log(user_id, "INFO", msg)

        # ✅ 이벤트 루프
        while not stop_event.is_set():
            try:
                event = q.get(timeout=0.5)
                process_engine_event(
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

    finally:
        # ✅ 안전하게 stop 처리
        stop_event.set()
        set_engine_status(user_id, False)
        set_thread_status(user_id, False)
        update_engine_status(user_id, "stopped")
        remove_engine_thread(user_id)

        msg = f"🛑 트레이딩 엔진 종료됨: user_id={user_id}"
        log_to_file(msg, user_id)
        insert_log(user_id, "INFO", msg)

        user_lock.release()


def stop_engine(user_id: str):
    from engine.global_state import get_engine_threads

    threads = get_engine_threads()
    info = threads.get(user_id)
    if info:
        info["stop_event"].set()
        info["thread"].join(timeout=2)  # ✅ 스레드가 완전히 종료되도록 기다림
        remove_engine_thread(user_id)  # ✅ 메모리 상태 정리
        log_to_file(f"🔌 엔진 종료 요청됨: user_id={user_id}", user_id)
    else:
        log_to_file(f"⚠️ 실행 중인 엔진이 없습니다: {user_id}", user_id)

    set_engine_status(user_id, False)
    set_thread_status(user_id, False)
    update_engine_status(user_id, "stopped")
    remove_engine_thread(user_id)  # ✅ 메모리 상태 정리


def is_engine_running(user_id: str) -> bool:
    from engine.global_state import is_engine_really_running

    return is_engine_really_running(user_id)
