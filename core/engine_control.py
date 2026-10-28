"""
2차 T11 (결정 D3): 엔진 제어 큐 — 엔진 스레드 쪽.

신버전 요청을 엔진 프로세스의 감시 스레드(engine/control_requests.py)가 읽는다. 엔진이 돌고 있으면 감시 스레드는
엔진 잠금을 잡지 않고 이 큐에 ControlItem 을 넣고 기다린다. 엔진 스레드(engine/live_loop.py 메인 루프 맨 앞)가
drain_control_queue(engine) 로 꺼내 봉 처리와 같은 스레드에서 차례로 실행한다(봉 처리 도중 끼어들지 않음).

- force_sell → services.trading_control.force_liquidate(엔진 trader, 시장가 — 엔진 잠금 안 잡음)
- force_buy  → PULLBACK: engine._pullback_force_buy()(회당 금액 1회·회차 +1·사유 FORCE, 그 함수가 잠금 안에서)
               EMA·MACD: services.trading_control.force_buy_in(엔진 trader) — 잠금 밖(지정가 경로가 안에서 잠금을 잡음)
- 큐가 비어 있으면 아무 일도 하지 않는다(EMA·MACD 봉 판정·주문 무변경).

엔진 인스턴스 칸을 StrategyEngine.__init__ 에 두지 않고 attach() 로 붙인다(공용 생성자·EMA 경로 무변경 — T11 메모).
기동 준비 신호(engine_manager._ready)도 여기 사전(READY)을 함께 쓴다(live_loop 가 engine_manager 를 import 하지 않게).
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 사용자 → 기동 준비 Event(engine_manager._start_engine_internal 이 시작마다 새로 만든다). 실패 사유는 Event.fail_reason.
READY: Dict[str, threading.Event] = {}
# 사용자 → (engine, stop_event) — 지금 실행 중인 엔진(live_loop 가 엔진을 만든 직후 attach)
_RUNNING: Dict[str, tuple] = {}
_RUNNING_LOCK = threading.Lock()

FORCE_KINDS = ("force_buy", "force_sell")


class ControlItem:
    """감시 스레드 → 엔진 스레드 요청 1건. lock 으로 「취소」와 「실행 시작」을 배타로 둔다."""

    def __init__(self, kind: str, payload: Optional[dict] = None, req_id: Optional[str] = None):
        self.kind = kind
        self.payload = dict(payload or {})
        self.req_id = req_id
        self.done = threading.Event()
        self.result: Optional[Dict[str, Any]] = None
        self.cancelled = False
        self.started = False
        self.lock = threading.Lock()

    def try_cancel(self) -> bool:
        """아직 실행이 시작되지 않았으면 취소하고 True. 이미 시작됐으면 False(끝날 때까지 기다려야 함)."""
        with self.lock:
            if self.started:
                return False
            self.cancelled = True
            return True


def attach(engine, user_id: str, stop_event: Optional[threading.Event] = None) -> None:
    """엔진에 제어 큐를 붙이고 실행 중 엔진으로 등록한다. 그 시작의 준비 Event 를 함께 잡아 둔다.
    수정 1회차: engine_manager 는 Event 에 그 시작의 stop_event 를 적어 둔다(ev.stop_event). 다른 시작(늦게 붙은
    옛 엔진 등)의 Event 면 잡지 않는다 — 옛 엔진이 새 시작의 준비 신호를 세우지 않게."""
    if getattr(engine, "control_queue", None) is None:
        engine.control_queue = queue.Queue()
    ev = READY.get(user_id)
    owner = getattr(ev, "stop_event", None) if ev is not None else None
    if owner is not None and owner is not stop_event:
        logger.warning(f"[CONTROL] 준비 신호가 다른 시작의 것 → 잡지 않음 | user={user_id}")
        ev = None
    engine._control_ready_event = ev
    engine._control_stop_event = stop_event
    with _RUNNING_LOCK:
        _RUNNING[user_id] = (engine, stop_event)


def detach(user_id: str, stop_event: Optional[threading.Event]) -> None:
    """엔진이 끝날 때(engine_manager._engine_runner finally) 자기 항목만 지운다(새 엔진 항목은 그대로)."""
    with _RUNNING_LOCK:
        ent = _RUNNING.get(user_id)
        if ent is not None and ent[1] is stop_event:
            _RUNNING.pop(user_id, None)


def running_engine(user_id: str):
    """실행 중으로 등록된 엔진(멈춤 신호가 켜진 옛 엔진은 None — 그 항목은 지운다)."""
    with _RUNNING_LOCK:
        ent = _RUNNING.get(user_id)
        if not ent:
            return None
        engine, stop_event = ent
        if stop_event is not None and stop_event.is_set():
            _RUNNING.pop(user_id, None)
            return None
    return engine


def mark_ready(engine, user_id: str) -> bool:
    """메인 루프 진입 직전 1회. PULLBACK 은 분할 상태 복원이 예외로 끝났으면 세우지 않고 실패 사유만 남긴다.
    멈춤 신호가 켜진 엔진(정지 중)은 세우지 않는다."""
    ev = getattr(engine, "_control_ready_event", None)
    if ev is None:
        return False
    stop = getattr(engine, "_control_stop_event", None)
    if stop is not None and stop.is_set():
        logger.info(f"[CONTROL] 기동 준비 신호 안 세움 — 정지 중 | user={user_id}")
        return False
    if getattr(engine, "strategy_type", "") == "PULLBACK" and getattr(engine, "_pullback_restore_ok", True) is False:
        ev.fail_reason = "restore_failed"
        logger.error(f"[CONTROL] 기동 준비 신호 안 세움 — 분할 상태 복원 실패 | user={user_id}")
        return False
    ev.set()
    logger.info(f"[CONTROL] 기동 준비 끝(메인 루프 진입) | user={user_id} strategy={getattr(engine, 'strategy_type', '')}")
    return True


def drain_control_queue(engine) -> int:
    """엔진 스레드 메인 루프 맨 앞. 큐의 항목을 모두 실행하고 실행한 수를 돌려준다(비었으면 0, 아무 일 없음)."""
    q = getattr(engine, "control_queue", None)
    if q is None:
        return 0
    n = 0
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        with item.lock:
            if item.cancelled:
                logger.info(f"[CONTROL] 취소된 요청 버림 | kind={item.kind} id={item.req_id}")
                continue
            item.started = True
        try:
            item.result = _execute(engine, item)
        except Exception as e:
            logger.error(f"[CONTROL] 엔진 안 실행 예외 | kind={item.kind} id={item.req_id} | {type(e).__name__}: {e}")
            item.result = {"status": "error", "code": "exception", "detail": {"error": type(e).__name__}}
        finally:
            item.done.set()
        n += 1
    return n


def _msg_result(msg: str, fail_code: str) -> Dict[str, Any]:
    """trading_control 의 반환 문장 → 결과. 「❌」·「⚠️」 로 시작하면 거부(주문 없음 또는 실패)."""
    text = str(msg or "")
    if text.startswith("⚠️"):
        # 수정 2회차(N5): 「⚠️」는 주문 전 거절(보유 코인·원화 없음 — services.trading_control) — 주문 시도 아님
        return {"status": "rejected", "code": "no_balance", "detail": {"engine_message": text}}
    if text.startswith("❌"):
        return {"status": "rejected", "code": fail_code, "detail": {"engine_message": text}}
    return {"status": "done", "code": "ok", "detail": {"engine_message": text}}


def _execute(engine, item: ControlItem) -> Dict[str, Any]:
    from services import trading_control as tc
    if item.kind == "force_sell":
        msg = tc.force_liquidate(engine.user_id, engine.trader, engine.ticker,
                                 interval_sec=getattr(engine, "interval_sec", 60))
        return _msg_result(msg, "order_failed")
    if item.kind == "force_buy":
        if getattr(engine, "strategy_type", "") == "PULLBACK":
            return engine._pullback_force_buy()
        # D11 a: EMA·MACD — 잠금 밖에서 부른다(지정가 경로 execute_force_buy_limit_atomic 가 안에서 잠금을 잡음)
        msg = tc.force_buy_in(engine.user_id, engine.trader, engine.ticker,
                              interval_sec=getattr(engine, "interval_sec", 60),
                              strategy_type=getattr(engine, "strategy_type", None))
        return _msg_result(msg, "order_failed")
    return {"status": "rejected", "code": "unsupported_kind", "detail": {}}
