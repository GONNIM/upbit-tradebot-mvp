"""신버전 → 엔진 제어 요청 (2차 T11, 결정 D3) — 신버전 쪽: 요청 파일 쓰기·결과 읽기. 표준 라이브러리 + v2.db 만.

- 요청: <db.DATA_DIR>/v2_control/<user>/req-<id>.json (파일 600·폴더 700). id = KST yyyymmddHHMMSS-nonce8.
  본문 {"v":1,"id","user_id","mode","kind","payload","created_at","expires_at"}, expires_at = created_at + 60초.
  같은 폴더 임시 파일(점으로 시작)에 쓴 뒤 os.replace — 엔진 감시 스레드는 다 쓴 파일만 본다.
- 결과: 엔진이 res-<id>.json(600)을 쓴다. 신버전은 읽기만 한다.
- 엔진 모듈(engine·core·services)·실매매 DB 쓰기·업비트 호출이 없다(A11·A19). 금액은 요청에 넣지 않는다(엔진이 정함).
"""
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from v2 import db

CONTROL_DIRNAME = "v2_control"
REQUEST_TTL_SEC = 60
KINDS = ("engine_start", "engine_stop", "switch", "revert", "cancel_reservation",
         "apply_params", "force_buy", "force_sell", "ops_settings")
# 요청에 값을 싣지 않는 종류(강제 매매 금액은 엔진이 정한다 — S1)
EMPTY_PAYLOAD_KINDS = ("engine_start", "engine_stop", "force_buy", "force_sell", "cancel_reservation")
MAX_PAYLOAD_BYTES = 4096
MODES = ("TEST", "LIVE")
ID_RE = re.compile(r"^[0-9]{14}-[0-9a-f]{8}$")


class Busy(Exception):
    """진행 중 요청이 있음(한 번에 하나)."""

    def __init__(self, pending):
        super().__init__(pending)
        self.pending = pending


def control_dir(user_id: str) -> Path:
    if not db.valid_user_id(user_id):
        raise ValueError("user")
    return Path(db.DATA_DIR) / CONTROL_DIRNAME / user_id


def _ensure_dir(d: Path) -> None:
    """폴더 700. 링크(바깥을 가리킴)면 쓰지 않는다 — 엔진 감시도 링크 폴더는 건너뛴다(T11 수정 1회차)."""
    for p in (d.parent, d):
        try:
            p.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if p.is_symlink() or not p.is_dir():
            raise OSError("control dir is not a plain directory")
        os.chmod(p, 0o700)


def _validate(user_id, mode, kind, payload) -> None:
    if not db.valid_user_id(user_id):
        raise ValueError("user")
    if mode not in MODES:
        raise ValueError("mode")
    if kind not in KINDS:
        raise ValueError("kind")
    if not isinstance(payload, dict):
        raise ValueError("payload")
    if kind in EMPTY_PAYLOAD_KINDS and payload:
        raise ValueError("payload")
    # 바이트로 잰다(한글 1자 = 3바이트). 요청 파일 전체가 엔진 읽기 상한(8KB) 안에 들도록(T11 수정 3회차).
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload")


def _now(now: Optional[datetime]) -> datetime:
    return now if now is not None else datetime.now(db.KST)


def _req_body(path: Path) -> Optional[dict]:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def pending_id(user_id: str, now: Optional[datetime] = None) -> Optional[str]:
    """결과가 아직 없고 만료 전인 요청 id(가장 오래된 것). 없으면 None."""
    d = control_dir(user_id)
    t = _now(now)
    found = []
    try:
        names = sorted(p.name for p in d.glob("req-*.json"))
    except OSError:
        return None
    for name in names:
        body = _req_body(d / name)
        if body is None:
            continue
        rid = body.get("id")
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid) or (d / f"res-{rid}.json").exists():
            continue
        try:
            exp = datetime.fromisoformat(str(body.get("expires_at")))
        except ValueError:
            continue
        if exp.tzinfo is None or t > exp:
            continue
        found.append(rid)
    return found[0] if found else None


def write_request(user_id: str, mode: str, kind: str, payload: dict,
                  now: Optional[datetime] = None) -> str:
    """요청 파일을 쓰고 id 를 돌려준다. 형식 오류 ValueError, 진행 중 요청이 있으면 Busy."""
    _validate(user_id, mode, kind, payload)
    d = control_dir(user_id)
    t = _now(now)
    _ensure_dir(d)
    busy = pending_id(user_id, now=t)
    if busy is not None:
        raise Busy(busy)
    rid = t.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    body = {"v": 1, "id": rid, "user_id": user_id, "mode": mode, "kind": kind, "payload": payload,
            "created_at": t.isoformat(), "expires_at": (t + timedelta(seconds=REQUEST_TTL_SEC)).isoformat()}
    final = d / f"req-{rid}.json"
    tmp = d / f".req-{rid}.tmp"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(body, ensure_ascii=False))
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(final))
    except BaseException:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
    return rid


def read_result(user_id: str, req_id: str, now: Optional[datetime] = None) -> Optional[dict]:
    """결과 dict, 아직이면 {"status":"pending","overdue":bool}, 요청도 결과도 없으면 None. id 형식 오류 ValueError."""
    if not isinstance(req_id, str) or not ID_RE.fullmatch(req_id):
        raise ValueError("id")
    d = control_dir(user_id)
    res = _req_body(d / f"res-{req_id}.json")
    if res is not None:
        return res
    for p in d.glob("req-*.json") if d.exists() else []:
        body = _req_body(p)
        if body is not None and body.get("id") == req_id:
            overdue = False
            try:
                overdue = _now(now) > datetime.fromisoformat(str(body.get("expires_at")))
            except (TypeError, ValueError):
                pass
            return {"id": req_id, "status": "pending", "overdue": overdue}
    return None


SQL_RESERVATION = ("SELECT id, kind, from_strategy, to_strategy, note FROM strategy_switch WHERE user_id=? AND mode=? "
                   "AND kind IN ('SWITCH','REVERT') AND state='RESERVED' ORDER BY id DESC LIMIT 1")
SQL_LAST_SWITCH = ("SELECT from_strategy, from_ticker, from_interval FROM strategy_switch WHERE user_id=? AND mode=? "
                   "AND kind='SWITCH' AND state='DONE' ORDER BY id DESC LIMIT 1")
SQL_PULLBACK_STATE = ("SELECT entry_count, sizing_base_krw, realized_pnl_krw FROM pullback_state "
                      "WHERE user_id=? AND mode=? LIMIT 1")
SQL_CAPITAL = "SELECT virtual_krw FROM users WHERE username=? LIMIT 1"
OLD_STRATEGIES = ("EMA", "MACD")
OPS_KEYS = ("enable_trading_hours", "trading_start_time", "trading_end_time", "allow_sell_during_off_hours")
OPS_DEFAULTS = {"enable_trading_hours": False, "trading_start_time": "09:00", "trading_end_time": "02:00",
                "allow_sell_during_off_hours": True}   # engine/pullback_params.OPTIONAL_KEYS 와 같은 값(시험이 비교)
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# engine/pullback_params.PULLBACK_KEYS 와 같은 18키(시험이 비교) — 「저장본 정상」 화면 판정용(엔진이 다시 검증)
SAVED_KEYS = ("ticker", "interval", "maType", "ma60p", "ma200p", "pullbackP", "slopeLB", "minSlope", "slopeDrop",
              "buyOnGoldenCross", "maxSplits", "maxPullbackBuys", "tp", "sl", "deadcross", "compounding",
              "capital", "fee")


def _row(user_id: str, sql: str, args: tuple) -> Optional[dict]:
    rows = db.query(user_id, sql, args)
    return rows[0] if rows else None


def reservation(user_id: str, mode: Optional[str] = None) -> Optional[dict]:
    """예약 상태(DB strategy_switch, 읽기 전용 — 2차 T14 에서 채움). 그 모드의 RESERVED 전환·복귀 가장 최근 1행 또는 None.
    mode 가 없거나 DB·표가 없으면 None. 읽기 오류는 그대로 올린다(호출자가 「확인 불가」로)."""
    if mode not in MODES:
        return None
    if not db.live_db_path(user_id).exists():
        return None
    r = _row(user_id, SQL_RESERVATION, (user_id, mode))
    if r is None:
        return None
    return {"id": r["id"], "kind": r["kind"], "from_strategy": r["from_strategy"], "to_strategy": r["to_strategy"],
            "switching": r["note"] == "switching"}


def state(user_id: str, mode: Optional[str] = None) -> dict:
    try:
        res = reservation(user_id, mode)
    except sqlite3.Error:
        res = None
    return {"pending": pending_id(user_id), "reservation": res}


def ops_keys_or_none(keys) -> Optional[dict]:
    """운용 설정 4키 정확히(켜기·시간 밖 매도 = 참/거짓, 시작·끝 = HH:MM). 아니면 None. 엔진도 같은 규칙으로 다시 본다."""
    if not isinstance(keys, dict) or set(keys) != set(OPS_KEYS):
        return None
    for k, default in OPS_DEFAULTS.items():
        v = keys[k]
        if isinstance(default, bool):
            if not isinstance(v, bool):
                return None
        elif not isinstance(v, str) or not _HHMM_RE.fullmatch(v):
            return None
    return {k: keys[k] for k in OPS_KEYS}


def _saved_state(user_id: str) -> dict:
    """저장본(신버전이 쓰는 파일) 형식 확인 + 해시. 전환 요청 payload 의 saved_sha256(엔진이 다시 본다)."""
    p = db.pullback_params_path(user_id)
    try:
        raw = p.read_bytes()
        d = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {"ok": False, "sha256": None}
    ok = isinstance(d, dict) and all(k in d for k in SAVED_KEYS)
    return {"ok": ok, "sha256": hashlib.sha256(raw).hexdigest() if ok else None}


def _eff_max_splits(p: dict) -> Optional[int]:
    """core/strategy_pullback 의 eff_max_splits 와 같은 규칙: 골든크로스만(maxSplits 0 + buyOnGoldenCross) = 1, 그 밖 maxSplits."""
    try:
        n = int(p.get("maxSplits"))
    except (TypeError, ValueError):
        return None
    if n == 0 and p.get("buyOnGoldenCross") in (True, "true", "on"):
        return 1
    return n if n > 0 else None


def ops_info(user_id: str, mode: Optional[str]) -> dict:
    """운용 탭 단추 판정에 쓰는 값(읽기만). GET /v2/api/ops.
    - reservation·reservation_error, revert_target(마지막 전환 기록의 전략 + 그 전략 설정 파일의 종목·봉 — 엔진 복귀와 같은 값)
    - saved(저장본 형식·해시), PULLBACK 이면 round(회차·한도)·per_buy(회당 금액 추정 = 엔진 floor(배분 기준 / 한도))·hours(적용본 4키)
    - EMA·MACD 이면 order_ratio(강제 매수 금액 = 원화 잔고 × 이 값, 화면이 곱함)."""
    strategy, _mt = db.active_strategy(user_id)
    out = {"pending": pending_id(user_id), "mode": mode, "strategy": strategy, "reservation": None,
           "reservation_error": False, "revert_target": None, "saved": _saved_state(user_id),
           "round": None, "per_buy": None, "order_ratio": None, "hours": None}
    has_db = db.live_db_path(user_id).exists()
    try:
        out["reservation"] = reservation(user_id, mode)
    except sqlite3.Error:
        out["reservation_error"] = True
    if strategy == "PULLBACK":
        applied = db.active_params(user_id, "PULLBACK")
        if applied:
            out["hours"] = {k: applied.get(k, OPS_DEFAULTS[k]) for k in OPS_KEYS}
        eff = _eff_max_splits(applied) if applied else None
        st = None
        if has_db and mode in MODES:
            try:
                st = _row(user_id, SQL_PULLBACK_STATE, (user_id, mode))
            except sqlite3.Error:
                st = None
        entry = int((st or {}).get("entry_count") or 0)
        if eff is not None:
            out["round"] = {"entry": entry, "max": eff}
        base = (st or {}).get("sizing_base_krw") if entry > 0 else None
        if base is None and has_db:
            try:
                cap = _row(user_id, SQL_CAPITAL, (user_id,))
                base = float(cap["virtual_krw"]) if cap and cap.get("virtual_krw") is not None else None
            except (sqlite3.Error, TypeError, ValueError):
                base = None
            if base is not None and applied.get("compounding") is True:
                base += float((st or {}).get("realized_pnl_krw") or 0.0)
        if base and eff:
            out["per_buy"] = int(math.floor(float(base) / eff))
        if has_db and mode in MODES:
            try:
                last = _row(user_id, SQL_LAST_SWITCH, (user_id, mode))
            except sqlite3.Error:
                last = None
            if last and last.get("from_strategy") in OLD_STRATEGIES:
                tgt = last["from_strategy"]
                sp = db.strategy_params(user_id, tgt)
                out["revert_target"] = {
                    "strategy": tgt,
                    "ticker": db.normalize_ticker(sp.get("ticker")) or last.get("from_ticker"),
                    "interval": sp.get("interval") or last.get("from_interval")}
    elif strategy in OLD_STRATEGIES:
        sp = db.strategy_params(user_id, strategy)
        try:
            r = float(sp.get("order_ratio"))
            out["order_ratio"] = r if 0 < r <= 1 else None
        except (TypeError, ValueError):
            out["order_ratio"] = None
    return out
