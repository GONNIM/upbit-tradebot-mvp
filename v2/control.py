"""신버전 → 엔진 제어 요청 (2차 T11, 결정 D3) — 신버전 쪽: 요청 파일 쓰기·결과 읽기. 표준 라이브러리 + v2.db 만.

- 요청: <db.DATA_DIR>/v2_control/<user>/req-<id>.json (파일 600·폴더 700). id = KST yyyymmddHHMMSS-nonce8.
  본문 {"v":1,"id","user_id","mode","kind","payload","created_at","expires_at"}, expires_at = created_at + 60초.
  같은 폴더 임시 파일(점으로 시작)에 쓴 뒤 os.replace — 엔진 감시 스레드는 다 쓴 파일만 본다.
- 결과: 엔진이 res-<id>.json(600)을 쓴다. 신버전은 읽기만 한다.
- 엔진 모듈(engine·core·services)·실매매 DB 쓰기·업비트 호출이 없다(A11·A19). 금액은 요청에 넣지 않는다(엔진이 정함).
"""
import json
import os
import re
import secrets
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


def reservation(user_id: str) -> Optional[dict]:
    """예약 상태(DB strategy_switch, 읽기 전용). 테이블은 T12 가 만든다 — 그 전에는 None."""
    return None


def state(user_id: str) -> dict:
    return {"pending": pending_id(user_id), "reservation": reservation(user_id)}
