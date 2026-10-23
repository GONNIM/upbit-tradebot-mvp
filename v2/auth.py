"""신버전 입장 토큰 소비(NonceStore)와 세션 쿠키 값 생성·검증.

쿠키 속성(HttpOnly·Secure·SameSite·path)은 서버(Task 3)가 설정한다.
"""
import threading
import time
from typing import Optional

from utils import v2_entry_token as et

SESSION_COOKIE = "v2s"
SESSION_TTL_SEC = 43200
_SESSION_TYP = "session"
_SESSION_KEYS = frozenset({"typ", "user_id", "mode", "exp"})


class NonceStore:
    """1회용 nonce 저장소(프로세스 메모리). 처리 때 만료 항목을 정리한다."""

    def __init__(self):
        self._seen = {}
        self._lock = threading.Lock()

    def consume(self, nonce: str, exp: float,
                now: Optional[float] = None) -> bool:
        t = time.time() if now is None else now
        with self._lock:
            for k in [k for k, e in self._seen.items() if e < t]:
                del self._seen[k]
            if nonce in self._seen:
                return False
            self._seen[nonce] = exp
            return True

    def __len__(self):
        with self._lock:
            return len(self._seen)


def make_session(user_id, mode, now: Optional[float] = None) -> str:
    if not et.valid_user_id(user_id):
        raise ValueError("invalid user_id")
    if mode not in ("TEST", "LIVE"):
        raise ValueError("invalid mode")
    t = time.time() if now is None else now
    return et.sign_payload({"typ": _SESSION_TYP, "user_id": user_id,
                            "mode": mode, "exp": t + SESSION_TTL_SEC})


def read_session(value, now: Optional[float] = None) -> Optional[dict]:
    try:
        p = et.unsign_payload(value)
    except (et.TokenInvalid, et.TokenUnavailable):
        return None
    if p.get("typ") != _SESSION_TYP or set(p) != _SESSION_KEYS:
        return None
    exp = p["exp"]
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    if not et.valid_user_id(p["user_id"]) or p["mode"] not in ("TEST", "LIVE"):
        return None
    t = time.time() if now is None else now
    if t > exp:
        return None
    return p
