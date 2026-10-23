"""신버전 대시보드용 경량 DB·설정 모듈 (표준 라이브러리만 사용).

- 실매매 DB 는 읽기 전용 URI 로만 연다(파일 생성·쓰기 불가).
- 신버전 전용 이력 DB(v2hist)만 쓰기 가능하며 실매매 DB 와 파일이 다르다.
"""
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = REPO_ROOT / "services" / "data"

KST = ZoneInfo("Asia/Seoul")
BUSY_TIMEOUT_MS = 3000
QUERY_TIME_LIMIT_SEC = 2.0

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
_VERSION_RE = re.compile(r"v1\.\d{4}\.\d{2}\.\d{2}\.\d{4}")
# SQL 끝이 LIMIT <정수|?> [OFFSET <정수|?>] 이어야 한다(공백·; 허용)
_LIMIT_RE = re.compile(
    r"\blimit\s+(\d+|\?)(\s+offset\s+(\d+|\?))?\s*;*\s*$", re.IGNORECASE)

_HIST_DDL = (
    "CREATE TABLE IF NOT EXISTS v2_settings_history("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
    "saved_at TEXT NOT NULL, source_page TEXT NOT NULL, "
    "strategy_type TEXT NOT NULL, params_json TEXT, conditions_json TEXT, "
    "app_version TEXT, note TEXT, applied_at TEXT)"
)


def valid_user_id(user_id: str) -> bool:
    return isinstance(user_id, str) and bool(_USER_ID_RE.match(user_id))


def _require_user(user_id: str) -> None:
    if not valid_user_id(user_id):
        raise ValueError("invalid user_id")


def live_db_path(user_id: str) -> Path:
    _require_user(user_id)
    return DATA_DIR / f"tradebot_{user_id}.db"


def v2hist_path(user_id: str) -> Path:
    _require_user(user_id)
    return DATA_DIR / f"v2hist_{user_id}.db"  # tradebot_ 접두사 금지(boot_resume 이 tradebot_*.db 를 사용자로 읽음)


def _uri(path: Path, mode: str) -> str:
    p = path.as_posix().replace("%", "%25").replace("?", "%3f").replace("#", "%23")
    return f"file:{p}?mode={mode}"


def open_live_ro(user_id: str) -> sqlite3.Connection:
    """실매매 DB 읽기 전용 연결. 없으면 FileNotFoundError(파일을 만들지 않음)."""
    p = live_db_path(user_id)
    if not p.exists():
        raise FileNotFoundError(str(p))
    conn = sqlite3.connect(_uri(p, "ro"), uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + QUERY_TIME_LIMIT_SEC

    def _cb():
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_cb, 1000)
    return conn


def query(user_id: str, sql: str, params: tuple = ()) -> "list[dict]":
    # 주석은 LIMIT 위장에 쓰일 수 있어 거부
    if "--" in sql or "/*" in sql or not _LIMIT_RE.search(sql):
        raise ValueError("query requires LIMIT")
    conn = open_live_ro(user_id)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def open_v2hist(user_id: str) -> sqlite3.Connection:
    """신버전 이력 DB. 실매매 DB 가 없으면 만들지 않는다."""
    p = v2hist_path(user_id)
    if not p.exists():
        if not live_db_path(user_id).exists():
            raise FileNotFoundError(str(live_db_path(user_id)))
        # 600 으로 먼저 만들어 넓은 권한 순간을 없앤다
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            pass
    conn = sqlite3.connect(_uri(p, "rw"), uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute(_HIST_DDL)
        conn.commit()
        os.chmod(p, 0o600)
    except Exception:
        conn.close()
        raise
    return conn


def app_version() -> Optional[str]:
    try:
        text = (REPO_ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
    except Exception:
        return None
    m = _VERSION_RE.search(text)
    return m.group(0) if m else None


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat()


def parse_ts(s: str) -> datetime:
    """ISO(+09:00 포함) 또는 'YYYY-MM-DD HH:MM:SS'(KST 로 간주)."""
    dt = datetime.fromisoformat(s.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def insert_history(user_id: str, params_json: str, note: Optional[str]) -> int:
    conn = open_v2hist(user_id)
    try:
        cur = conn.execute(
            "INSERT INTO v2_settings_history(user_id, saved_at, source_page, "
            "strategy_type, params_json, conditions_json, app_version, note, applied_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, now_kst_iso(), "v2_backtester", "PULLBACK", params_json,
             None, app_version(), note, None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def active_strategy(user_id: str) -> "tuple[Optional[str], Optional[str]]":
    """(전략 이름, 파일 수정 시각 ISO). 파일이 없으면 (None, None)."""
    _require_user(user_id)
    p = REPO_ROOT / f"{user_id}_active_strategy.txt"
    try:
        val = p.read_text(encoding="utf-8").strip() or None
        ts = datetime.fromtimestamp(p.stat().st_mtime, KST).isoformat()
    except OSError:
        return (None, None)
    return (val, ts)


def strategy_params(user_id: str, strategy: str) -> dict:
    """엔진의 전략 파라미터 파일을 읽기만 한다. 없거나 깨지면 {}."""
    _require_user(user_id)
    if not re.match(r"^[A-Za-z0-9_]{1,32}$", strategy or ""):
        raise ValueError("invalid strategy")
    p = REPO_ROOT / f"{user_id}_latest_params_{strategy}.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pullback_params_path(user_id: str) -> Path:
    _require_user(user_id)
    return REPO_ROOT / f"{user_id}_latest_params_PULLBACK.json"
