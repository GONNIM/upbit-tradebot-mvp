"""
PULLBACK 전용 설정 로더 (2차 T2, 결정 D9).

파일 3개 (저장소 루트, 프로세스는 ROOT 로 chdir 한 상태를 전제):
- 저장본  {user}_latest_params_PULLBACK.json        신버전이 쓴다. 엔진은 적용 요청 때 복사 원본으로만 읽는다.
- 적용본  {user}_applied_params_PULLBACK.json       엔진만 쓴다. 600.
- 사본    {user}_applied_params_PULLBACK.last_good.json  엔진만 쓴다. 600. (결정 13-2 보완안:
          새 적용본을 쓰고 다시 읽어 검증한 뒤 같은 바이트를 사본에도 쓴다.)

표준 라이브러리 + engine.params.LiveParams + config 상수만 쓴다. v2/* 를 import 하지 않는다
(범위표는 v2/params_schema.py 와 같은 값을 다시 적고, 시험이 두 표를 비교한다).
EMA·MACD 경로는 이 모듈을 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile

from config import MIN_CASH, MIN_FEE_RATIO
from pydantic import ValidationError

from engine.params import LiveParams

logger = logging.getLogger(__name__)

_TAG = "[PULLBACK-PARAMS]"

PULLBACK_KEYS = (
    "ticker", "interval", "maType", "ma60p", "ma200p", "pullbackP", "slopeLB",
    "minSlope", "slopeDrop", "buyOnGoldenCross", "maxSplits", "maxPullbackBuys",
    "tp", "sl", "deadcross", "compounding", "capital", "fee",
)
OPTIONAL_KEYS = {
    "enable_trading_hours": False,
    "trading_start_time": "09:00",
    "trading_end_time": "02:00",
    "allow_sell_during_off_hours": True,
}

# v2/params_schema.py PARAM_FIELDS·SERVER_EXTRA_LIMITS·INTEGER_FIELDS 와 같은 값 (시험이 비교)
RANGES = {
    "ma60p": (2, 500),
    "ma200p": (10, 1000),
    "pullbackP": (2, 500),
    "slopeLB": (1, 500),
    "slopeDrop": (0, None),
    "maxSplits": (0, 10),
    "maxPullbackBuys": (1, 5),
}
NUMBER_KEYS = (
    "ma60p", "ma200p", "pullbackP", "slopeLB", "minSlope", "slopeDrop",
    "maxSplits", "maxPullbackBuys", "tp", "sl", "capital", "fee",
)
INTEGER_KEYS = ("ma60p", "ma200p", "pullbackP", "slopeLB", "maxSplits", "maxPullbackBuys")
EXTRA_LIMITS = {"tp": ("gt", 0), "sl": ("gt", 0), "capital": ("gt", 0), "fee": ("ge", 0)}
BOOL_KEYS = ("buyOnGoldenCross", "deadcross", "compounding")
MA_TYPES = ("ema", "sma")
INTERVALS = ("minute1", "minute3", "minute5", "minute60")

# engine.params.LiveParams._validate_ticker 보다 좁은 규칙: KRW- 접두·대문자 영문자만(숫자 든 종목은 거부)
_TICKER_RE = re.compile(r"^KRW-[A-Z]{1,15}$")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PullbackParamsError(Exception):
    """설정 검증·읽기 실패. field 는 실패한 키 이름 또는 empty|missing|json|type|sha_mismatch|..."""

    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


# ---------------------------------------------------------------- 경로
def saved_path(user_id: str) -> str:
    return f"{user_id}_latest_params_PULLBACK.json"


def applied_path(user_id: str) -> str:
    return f"{user_id}_applied_params_PULLBACK.json"


def last_good_path(user_id: str) -> str:
    return f"{user_id}_applied_params_PULLBACK.last_good.json"


# ---------------------------------------------------------------- 알림
def _notify_critical(title: str, body: str, key: str) -> None:
    """기존 텔레그램 알림(services.notifier)으로 CRITICAL 1건. 실패해도 기동 판단을 막지 않는다."""
    try:
        from services.notifier import send, LEVEL_CRITICAL
        send(LEVEL_CRITICAL, title, body, dedupe_key=key, dedupe_ttl=3600)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{_TAG} notify failed: {type(e).__name__}")


# ---------------------------------------------------------------- 읽기
def _parse_bytes(data: bytes) -> dict:
    if not data or not data.strip():
        raise PullbackParamsError("empty")
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise PullbackParamsError("json")
    if not isinstance(obj, dict):
        raise PullbackParamsError("type")
    return obj


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise PullbackParamsError("missing")
    except OSError:
        raise PullbackParamsError("io")


def read_json_strict(path: str) -> dict:
    """0바이트·빈 문자열 -> "empty", JSON 깨짐(반쯤 쓴 파일 포함) -> "json", dict 아님 -> "type"."""
    return _parse_bytes(_read_bytes(path))


def sha256_of(path: str) -> str:
    """파일 바이트 그대로의 sha256 (hex)."""
    return hashlib.sha256(_read_bytes(path)).hexdigest()


# ---------------------------------------------------------------- 검증
def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PullbackParamsError(name)
    try:
        if not math.isfinite(float(v)):
            raise PullbackParamsError(name)
    except OverflowError:
        raise PullbackParamsError(name)
    return v


def validate(d: dict) -> dict:
    """18키 정확히(+선택 4키). 통과하면 정규화한 새 dict(선택 키는 기본값으로 채움)를 돌려준다."""
    if not isinstance(d, dict):
        raise PullbackParamsError("type")
    allowed = set(PULLBACK_KEYS) | set(OPTIONAL_KEYS)
    for k in PULLBACK_KEYS:
        if k not in d:
            raise PullbackParamsError(k)
    for k in d:
        if k not in allowed:
            raise PullbackParamsError(k)

    out: dict = {}
    t = d["ticker"]
    if not isinstance(t, str) or not _TICKER_RE.fullmatch(t):
        raise PullbackParamsError("ticker")
    out["ticker"] = t
    if not isinstance(d["interval"], str) or d["interval"] not in INTERVALS:
        raise PullbackParamsError("interval")
    out["interval"] = d["interval"]
    if not isinstance(d["maType"], str) or d["maType"] not in MA_TYPES:
        raise PullbackParamsError("maType")
    out["maType"] = d["maType"]

    for k in NUMBER_KEYS:
        v = _num(d[k], k)
        lo, hi = RANGES.get(k, (None, None))
        if lo is not None and v < lo:
            raise PullbackParamsError(k)
        if hi is not None and v > hi:
            raise PullbackParamsError(k)
        lim = EXTRA_LIMITS.get(k)
        if lim is not None:
            op, bound = lim
            if (op == "gt" and not v > bound) or (op == "ge" and not v >= bound):
                raise PullbackParamsError(k)
        if k in INTEGER_KEYS:
            if v != int(v):
                raise PullbackParamsError(k)
            v = int(v)
        out[k] = v

    for k in BOOL_KEYS:
        if not isinstance(d[k], bool):
            raise PullbackParamsError(k)
        out[k] = d[k]

    if out["maxSplits"] == 0 and not out["buyOnGoldenCross"]:
        raise PullbackParamsError("maxSplits")

    for k, default in OPTIONAL_KEYS.items():
        v = d.get(k, default)
        if isinstance(default, bool):
            if not isinstance(v, bool):
                raise PullbackParamsError(k)
        elif not isinstance(v, str) or not _HHMM_RE.fullmatch(v):
            raise PullbackParamsError(k)
        out[k] = v

    # 키 순서: 18키 -> 선택 4키
    return {k: out[k] for k in (*PULLBACK_KEYS, *OPTIONAL_KEYS)}


def _reason_of(e: PullbackParamsError) -> str:
    if e.field in ("empty", "missing"):
        return "missing"
    if e.field in ("json", "type", "io"):
        return e.field
    return "field"


def _load_valid(path: str) -> dict:
    return validate(read_json_strict(path))


# ---------------------------------------------------------------- 기동
def load_for_boot(user_id: str, *, holding: bool) -> tuple[dict | None, str]:
    """(params, source). source: "applied" | "last_good" | "none". 경우별 표 1~11."""
    a_path, lg_path = applied_path(user_id), last_good_path(user_id)

    try:
        params = _load_valid(a_path)
    except PullbackParamsError as e_applied:
        reason = _reason_of(e_applied)
        try:
            params = _load_valid(lg_path)
        except PullbackParamsError as e_last:
            msg = (
                f"{_TAG} no usable params user={user_id} holding={holding} "
                f"applied={_reason_of(e_applied)} last_good={_reason_of(e_last)}"
            )
            logger.error(msg)
            if holding:
                title = "보유 중 새 전략 설정 없음 — 운영자 확인 필요"
                body = (
                    "적용본과 직전 정상 사본이 모두 없거나 깨졌습니다. PULLBACK 기동을 거부했습니다.\n"
                    "운영자 절차: 수동 청산 또는 활성 전략 파일을 직전 전략으로 되돌립니다."
                )
            else:
                title = "새 전략 설정이 없습니다 — 신버전에서 설정을 다시 적용해 주세요"
                body = "적용본과 직전 정상 사본이 모두 없거나 깨졌습니다. PULLBACK 기동을 거부했습니다."
            _notify_critical(title, body, f"pullback_params_none:{user_id}:{int(bool(holding))}")
            return None, "none"
        logger.critical(
            f"{_TAG} fallback reason={reason} user={user_id} holding={holding} -> last_good"
        )
        _notify_critical(
            "설정 파일 이상 — 직전 정상 설정으로 동작 중",
            f"PULLBACK 적용본이 비정상({reason})이라 직전 정상 사본으로 동작합니다. 신버전에서 설정을 다시 적용해 주세요.",
            f"pullback_params_fallback:{user_id}",
        )
        return params, "last_good"

    # 적용본 정상: 사본이 있는데 깨졌으면 WARNING 만 (경우 11)
    if os.path.exists(lg_path):
        try:
            _load_valid(lg_path)
        except PullbackParamsError:
            logger.warning(f"{_TAG} last_good invalid user={user_id} (다음 적용 때 갱신됨)")
    logger.info(f"{_TAG} source=applied user={user_id} holding={holding}")
    return params, "applied"


def reload_applied(user_id: str, current: dict) -> dict:
    """운용 중 다시 읽기 (경우 12). 적용본이 깨졌으면 이전 값(current)을 그대로 돌려준다."""
    try:
        return _load_valid(applied_path(user_id))
    except PullbackParamsError as e:
        logger.warning(f"{_TAG} reload rejected reason={_reason_of(e)} field={e.field} user={user_id}")
        return current


# ---------------------------------------------------------------- 적용
def _atomic_write(path: str, data: bytes) -> None:
    """같은 폴더에 고유 임시 파일(600) -> fsync -> os.replace -> 폴더 fsync. 실패하면 임시 파일을 지운다."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            view = memoryview(data)
            while view:
                n = f.write(view)
                view = view[n:]
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    try:  # 폴더 기록 (실패해도 파일은 이미 교체됨)
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _verify_applied(user_id: str, expected: bytes) -> dict:
    path = applied_path(user_id)
    data = _read_bytes(path)
    if data != expected:
        raise PullbackParamsError("verify")
    return validate(_parse_bytes(data))


def check_saved_for_switch(user_id: str) -> str:
    """전환·적용 요청용: 저장본이 0바이트·깨짐·검증 실패면 "saved_invalid". 통과하면 저장본 sha256."""
    try:
        data = _read_bytes(saved_path(user_id))
        validate(_parse_bytes(data))
    except PullbackParamsError:
        raise PullbackParamsError("saved_invalid")
    return hashlib.sha256(data).hexdigest()


def apply_saved(user_id: str, expected_sha: str) -> dict:
    """저장본 -> 적용본(600) -> 다시 읽어 검증 -> 같은 바이트를 사본(600)에도.

    돌려주는 값: {"sha", "params", "last_good": bool}. 재검증이 실패하면 이전 적용본 바이트로
    되돌리고(없었으면 지움) PullbackParamsError("verify"). 사본 쓰기 실패는 WARNING 만 남기고 적용은 성공.
    """
    data = _read_bytes(saved_path(user_id))  # 해시와 검증이 같은 바이트를 보게 한 번만 읽는다
    sha = hashlib.sha256(data).hexdigest()
    if sha != expected_sha:
        raise PullbackParamsError("sha_mismatch")
    validated = validate(_parse_bytes(data))
    to_live_params(validated, MIN_CASH)  # LiveParams 가 받아 주는지 쓰기 전에 시험

    a_path, lg_path = applied_path(user_id), last_good_path(user_id)
    try:
        previous = _read_bytes(a_path)
    except PullbackParamsError:
        previous = None

    _atomic_write(a_path, data)
    try:
        params = _verify_applied(user_id, data)
    except PullbackParamsError:
        _rollback(a_path, previous)
        raise PullbackParamsError("verify")

    last_good_ok = True
    try:
        _atomic_write(lg_path, data)
        if _read_bytes(lg_path) != data:
            raise OSError("last_good readback mismatch")
    except (OSError, PullbackParamsError) as e:
        last_good_ok = False
        logger.warning(f"{_TAG} last_good write failed user={user_id} err={type(e).__name__}")
    logger.info(f"{_TAG} applied user={user_id} sha={sha[:12]}")
    return {"sha": sha, "params": params, "last_good": last_good_ok}


def apply_ops_keys(user_id: str, keys: dict) -> dict:
    """2차 T14 (운용 설정, 결정 13-6 권고 가): 지금 적용본에 선택 4키(거래 시간)만 합쳐 새 적용본(600) -> 다시 읽어 검증 ->
    같은 바이트를 사본(600)에도. 저장본의 다른 키는 적용하지 않는다(저장본은 읽지 않음).

    keys: OPTIONAL_KEYS 의 4키 정확히. 돌려주는 값: {"sha", "params", "prev": 이전 적용본 dict, "last_good": bool}.
    적용본이 없거나 깨졌으면 PullbackParamsError("applied_invalid"), 키가 맞지 않으면 그 키 이름.
    재검증이 실패하면 이전 적용본 바이트로 되돌리고 PullbackParamsError("verify").
    """
    if not isinstance(keys, dict) or set(keys) != set(OPTIONAL_KEYS):
        raise PullbackParamsError("keys")
    a_path, lg_path = applied_path(user_id), last_good_path(user_id)
    try:
        previous = _read_bytes(a_path)
        prev = validate(_parse_bytes(previous))
    except PullbackParamsError:
        raise PullbackParamsError("applied_invalid")
    merged = dict(prev)
    merged.update({k: keys[k] for k in OPTIONAL_KEYS})
    validated = validate(merged)             # 4키 형식(참·거짓, HH:MM) 검사
    to_live_params(validated, MIN_CASH)
    data = (json.dumps(validated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    _atomic_write(a_path, data)
    try:
        params = _verify_applied(user_id, data)
    except PullbackParamsError:
        _rollback(a_path, previous)
        raise PullbackParamsError("verify")

    last_good_ok = True
    try:
        _atomic_write(lg_path, data)
        if _read_bytes(lg_path) != data:
            raise OSError("last_good readback mismatch")
    except (OSError, PullbackParamsError) as e:
        last_good_ok = False
        logger.warning(f"{_TAG} last_good write failed user={user_id} err={type(e).__name__}")
    sha = hashlib.sha256(data).hexdigest()
    logger.info(f"{_TAG} ops keys applied user={user_id} sha={sha[:12]}")
    return {"sha": sha, "params": params, "prev": prev, "last_good": last_good_ok}


def _rollback(path: str, previous: bytes | None) -> None:
    try:
        if previous is None:
            os.remove(path)
        else:
            _atomic_write(path, previous)
    except OSError as e:
        logger.error(f"{_TAG} rollback failed path={path} err={type(e).__name__}")


# ---------------------------------------------------------------- 파생값
def required_bars(d: dict) -> int:
    return max(d["ma60p"], d["ma200p"], d["pullbackP"]) + d["slopeLB"] * 2 + 10


def to_live_params(d: dict, capital_krw: float) -> LiveParams:
    """validate 를 통과한 dict(선택 4키 포함)를 LiveParams 로. 실패는 PullbackParamsError."""
    if isinstance(capital_krw, bool) or not isinstance(capital_krw, (int, float)):
        raise PullbackParamsError("capital_krw")
    try:
        if not math.isfinite(float(capital_krw)) or capital_krw <= 0:
            raise PullbackParamsError("capital_krw")
        eff_max_splits = max(1, int(d["maxSplits"]))
        return LiveParams(
            ticker=d["ticker"],
            interval=d["interval"],
            strategy_type="PULLBACK",
            take_profit=d["tp"] / 100,
            stop_loss=d["sl"] / 100,
            cash=max(MIN_CASH, int(capital_krw)),
            commission=MIN_FEE_RATIO,
            order_ratio=1 / eff_max_splits,
            enable_trading_hours=d["enable_trading_hours"],
            trading_start_time=d["trading_start_time"],
            trading_end_time=d["trading_end_time"],
            allow_sell_during_off_hours=d["allow_sell_during_off_hours"],
        )
    except (ValidationError, OverflowError, ValueError, KeyError):
        raise PullbackParamsError("live_params")
