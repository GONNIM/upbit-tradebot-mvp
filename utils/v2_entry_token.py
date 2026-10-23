"""신버전 입장 토큰 (표준 라이브러리만 사용, 1차 배포 뒤 동결).

형식: base64url(json) + "." + base64url(hmac_sha256(비밀키, base64url(json)))
비밀 키·허용 목록 파일은 호출 때마다 읽는다(재시작 없이 교체 가능).
예외 메시지에는 키·토큰 본문을 넣지 않는다.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Optional

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
SECRET_PATH: Path = REPO_ROOT / ".v2_secret"
ALLOWLIST_PATH: Path = REPO_ROOT / ".v2_allowlist"
TOKEN_TTL_SEC = 60
FORMAT_VERSION = 1
MIN_SECRET_BYTES = 32
_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_MODES = ("TEST", "LIVE")
_TOKEN_KEYS = frozenset({"v", "user_id", "mode", "nonce", "exp"})


class TokenUnavailable(Exception):
    """비밀 키를 쓸 수 없음(없음·짧음·읽기 실패)."""


class TokenInvalid(Exception):
    """토큰이 올바르지 않음(서명·형식·만료·버전)."""


def valid_user_id(user_id) -> bool:
    return (isinstance(user_id, str) and 1 <= len(user_id) <= 32
            and all(c in _ID_CHARS for c in user_id))


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    if "+" in text or "/" in text or "=" in text:
        raise ValueError("bad base64url")
    raw = base64.b64decode(text + "=" * (-len(text) % 4),
                           altchars=b"-_", validate=True)
    if b64e(raw) != text:
        raise ValueError("bad base64url")
    return raw


def read_secret() -> bytes:
    try:
        key = Path(SECRET_PATH).read_bytes()
    except OSError:
        raise TokenUnavailable("secret unavailable") from None
    if len(key) < MIN_SECRET_BYTES:
        raise TokenUnavailable("secret too short")
    return key


def sign_payload(payload: dict) -> str:
    key = read_secret()
    body = b64e(json.dumps(payload, separators=(",", ":"),
                           sort_keys=True).encode("utf-8"))
    sig = hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + b64e(sig)


def unsign_payload(value) -> dict:
    """서명 검증 후 페이로드(dict). 실패는 TokenInvalid, 키 문제는 TokenUnavailable."""
    key = read_secret()
    if not isinstance(value, str) or value.count(".") != 1:
        raise TokenInvalid("malformed")
    body, sig = value.split(".")
    try:
        got = b64d(sig)
        expect = hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()
        ok = hmac.compare_digest(got, expect)
        payload = json.loads(b64d(body).decode("utf-8")) if ok else None
    except (ValueError, UnicodeError):
        raise TokenInvalid("malformed") from None
    if not ok:
        raise TokenInvalid("bad signature")
    if not isinstance(payload, dict):
        raise TokenInvalid("malformed")
    return payload


def load_allowlist(path=None) -> frozenset:
    p = Path(ALLOWLIST_PATH if path is None else path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return frozenset()
    names = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line)
    return frozenset(names)


def is_allowed(user_id) -> bool:
    return valid_user_id(user_id) and user_id in load_allowlist()


def make_token(user_id, mode, now: Optional[float] = None) -> str:
    if not valid_user_id(user_id):
        raise ValueError("invalid user_id")
    if mode not in _MODES:
        raise ValueError("invalid mode")
    t = time.time() if now is None else now
    return sign_payload({
        "v": FORMAT_VERSION,
        "user_id": user_id,
        "mode": mode,
        "nonce": secrets.token_urlsafe(16),
        "exp": t + TOKEN_TTL_SEC,
    })


def verify_token(token, now: Optional[float] = None) -> dict:
    p = unsign_payload(token)
    if set(p) != _TOKEN_KEYS:
        raise TokenInvalid("bad fields")
    if p["v"] != FORMAT_VERSION or isinstance(p["v"], bool):
        raise TokenInvalid("bad version")
    if not valid_user_id(p["user_id"]) or p["mode"] not in _MODES:
        raise TokenInvalid("bad fields")
    if not isinstance(p["nonce"], str) or not p["nonce"]:
        raise TokenInvalid("bad fields")
    exp = p["exp"]
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise TokenInvalid("bad fields")
    t = time.time() if now is None else now
    if t > exp:
        raise TokenInvalid("expired")
    return p
