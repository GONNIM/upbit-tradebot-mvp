"""
1109 눌림목 실계좌 열기 — 작업 C·D: 시간 상한이 있는 조회 도우미.

pyupbit 의 get_balances·get_balance 는 요청 시간 상한이 없어 업비트가 응답하지 않으면 엔진 락 안에서 끝없이 기다릴 수 있다.
`with ThreadPoolExecutor` 는 블록을 나갈 때 작업 종료를 기다려 상한이 무력해지므로 쓰지 않는다. 대신 데몬 스레드 1개를 띄워
Event 로 timeout 초만 기다리고, 시간이 지나면 결과를 기다리지 않고 버린다(스레드는 호출이 끝나면 스스로 끝남).
같은 guard 로 이전 조회가 아직 끝나지 않았으면 새 스레드를 만들지 않고 실패로 돌려 스레드가 쌓이지 않게 한다
(guard 가 STALE_SEC 보다 오래되면 멈춘 것으로 보고 새 조회 허용).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

DEFAULT_TIMEOUT_S = 8.0
STALE_SEC = 60.0


def bounded_call(fn: Callable[[], Any], timeout: float = DEFAULT_TIMEOUT_S,
                 guard: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, Optional[BaseException]]:
    """fn() 을 별도 스레드에서 실행한다. 반환 (끝남, 값, 예외).
    - 끝남=False, 예외=None: 시간 초과(또는 guard 때문에 시작하지 않음). 값은 없다.
    - 끝남=True, 예외 있음: fn 이 예외로 끝남."""
    if guard is not None:
        started = guard.get("started")
        if started is not None and time.monotonic() - started < STALE_SEC and guard.get("running"):
            return False, None, None
        guard["running"] = True
        guard["started"] = time.monotonic()
    box: Dict[str, Any] = {}
    done = threading.Event()

    def runner():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - 호출자가 예외를 받아 실패로 처리한다
            box["error"] = e
        finally:
            if guard is not None:
                guard["running"] = False
            done.set()

    t = threading.Thread(target=runner, name="bounded-call", daemon=True)
    t.start()
    if not done.wait(timeout):
        return False, None, None
    err = box.get("error")
    return True, box.get("value"), err
