"""업비트 키 만료 미리 알림 계산 (1122-01, 계획 docs/plans/2026-11-22-key-expiry-alert/plan.md 3-1).

- 비밀을 읽지 않는다. 표준 라이브러리만 쓴다.
- 점검 스크립트(scripts/key_expiry_check.py)와 신버전 화면(v2/api_read.py)이 이 함수들을 같이 쓴다
  — 알림과 배지가 같은 날 서로 다른 「남은 날」을 보이지 않게 한다.
- 계획은 services/key_expiry.py 였으나 v2 는 services 를 import 하지 않는 규칙
  (tests/v2/test_server.py test_server_import_graph_clean)이 있어 v2 아래에 둔다.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
RESULT_NAME = ".key_expiry.json"        # services/data 아래 (점검 스크립트가 씀, v2 는 읽기만)
STEPS = (30, 14, 7, 3, 1, 0)            # 단계 알림: 남은 날이 이 값 이하로 처음 들어갈 때 한 번
STALE = timedelta(days=2)               # 마지막 성공 확인이 이보다 오래면 「확인 안 됨」
FAIL_ALERT_AFTER = timedelta(days=2)    # 401 이 아닌 조회 실패가 이만큼 이어지면 운영자 알림
DANGER_DAYS = 7
WARN_DAYS = 30


# ---- 시각 ----
def parse_time(s) -> Optional[datetime]:
    """시간대가 있는 ISO 문자열만 받는다(없으면 None). 결과는 KST."""
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None
        return dt.astimezone(KST)
    except (ValueError, OverflowError):  # 0001-01-01 같은 끝 값은 시간대 바꿀 때 OverflowError
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def is_expired(expire: datetime, now: datetime) -> bool:
    return now >= expire


def days_left(expire: datetime, now: datetime) -> int:
    """KST 달력 날짜 차(만료 날짜 − 오늘 날짜)."""
    return (expire.astimezone(KST).date() - now.astimezone(KST).date()).days


def due_step(expire: datetime, now: datetime, sent) -> Optional[int]:
    """보낼 단계. 「남은 날 ≤ 단계」 가운데 가장 작은 단계, 그 단계(또는 더 가까운 단계)를 아직 안 보냈을 때만.

    여러 단계를 한꺼번에 건너뛰면 가장 가까운 단계 1번만(15일 → 6일 = 7일 단계).
    만료 뒤는 단계가 아니라 「만료 뒤 하루 1번」으로 따로 다룬다.
    """
    if is_expired(expire, now):
        return None
    d = days_left(expire, now)
    cands = [s for s in STEPS if d <= s]
    if not cands:
        return None
    step = min(cands)
    if any(int(s) <= step for s in sent):
        return None
    return step


# ---- 화면 배지 ----
def badge(state: dict, now: datetime) -> Optional[dict]:
    """홈 배지 값. 판정 순서: 만료됨 → 확인 안 됨 → 7일 이하 → 30일 이하 → 보통."""
    if not isinstance(state, dict):
        return None
    exp = parse_time(state.get("expire_at"))
    last_ok = parse_time(state.get("last_ok_at"))
    stale = last_ok is None or (now - last_ok) > STALE
    out = {"expire_at": iso(exp) if exp else None, "days_left": None,
           "last_ok_at": iso(last_ok) if last_ok else None}
    if exp is not None and is_expired(exp, now):
        out.update(level="danger", label="업비트 키 만료됨 — 새 키 필요", days_left=days_left(exp, now))
        return out
    if exp is None:
        out.update(level="danger", label="업비트 키 만료일 확인 안 됨")
        return out
    d = days_left(exp, now)
    out["days_left"] = d
    day = exp.strftime("%Y-%m-%d")
    if stale:
        out.update(level="danger", label="업비트 키 만료일 확인 안 됨 (마지막으로 받은 만료일 " + day + ")")
        return out
    left = "오늘 만료" if d == 0 else str(d) + "일 남음"
    label = "업비트 키 · " + day + " 만료 (" + left + ")"
    level = "danger" if d <= DANGER_DAYS else ("warn" if d <= WARN_DAYS else "ok")
    out.update(level=level, label=label)
    return out


# ---- 알림 판정 (조회 응답이 아니라 저장된 expire_at 과 지금 시각으로) ----
def plan_alerts(state: dict, now: datetime, err: Optional[str], same_channel: bool) -> list:
    """보낼 알림 목록. 각 항목 {audience, level, title, body, marks}.

    - 단계 알림·만료 뒤 알림: 기본 채널(audience None). 만료 뒤는 하루 1번(last_expired_alert_date).
    - 조회 실패: 401 은 그날 바로, 그 밖은 first_fail_at 부터 2일 넘게 이어질 때 운영자 채널(하루 1번, last_fail_alert_date).
    - 두 채널이 같은 채팅이면(same_channel) 같은 날의 두 알림을 한 건으로 합친다.
    marks 는 보내기에 성공했을 때만 state 에 반영한다(apply_marks).
    """
    today = now.astimezone(KST).date().isoformat()
    exp_s = state.get("expire_at")
    exp = parse_time(exp_s)
    out = []
    if exp is not None:
        when = exp.strftime("%Y-%m-%d %H:%M")
        if is_expired(exp, now):
            # 만료 뒤 알림은 단계 알림과 따로 하루 1번(last_expired_alert_date) — 만료 당일 09:05 「오늘 만료」 뒤
            # 21:05 실행에서 「만료됨」이 같은 날 나갈 수 있게 한다.
            if state.get("last_expired_alert_date") != today:
                out.append({"audience": None, "level": "CRITICAL", "title": "업비트 키 만료됨",
                            "body": ("업비트 Open API 키가 만료되었습니다(" + when + "). 자동 매매 주문이 거절됩니다. "
                                     "투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요."),
                            "marks": {"last_expired_alert_date": today}})
        else:
            sent = [a[1] for a in state.get("alerts") or []
                    if isinstance(a, (list, tuple)) and len(a) == 2 and a[0] == exp_s]
            step = due_step(exp, now, sent)
            if step is not None:
                d = days_left(exp, now)
                left = "오늘 만료" if d == 0 else str(d) + "일 남음"
                out.append({"audience": None, "level": "CRITICAL" if step <= DANGER_DAYS else "WARNING",
                            "title": "업비트 키 만료 " + ("오늘" if d == 0 else str(d) + "일 전"),
                            "body": ("업비트 Open API 키가 " + when + " 에 만료됩니다(" + left + "). "
                                     "만료되면 자동 매매 주문이 거절됩니다. "
                                     "투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요."),
                            "marks": {"alert": [exp_s, step], "last_alert_date": today}})
    if err:
        first = parse_time(state.get("first_fail_at"))
        due = err == "http_401" or (first is not None and now - first >= FAIL_ALERT_AFTER)
        if due and state.get("last_fail_alert_date") != today:
            body = ("업비트 키 만료일 조회가 실패했습니다(코드 " + err + ", 첫 실패 "
                    + (first.strftime("%Y-%m-%d %H:%M") if first else "—") + "). "
                    "401 이면 키 만료나 허용 IP 를 확인하세요.")
            if same_channel and out:
                out[0]["body"] += "\n(운영자) " + body
                out[0]["marks"]["last_fail_alert_date"] = today
            else:
                out.append({"audience": "operator", "level": "WARNING", "title": "키 만료일 점검 실패",
                            "body": body, "marks": {"last_fail_alert_date": today}})
    return out


def plan_investor_alerts(state: dict, now: datetime) -> list:
    """투자자 채팅으로 보낼 키 만료 알림(1122-01 ㉠). 단계 알림·만료 뒤 알림만, 조회 실패 알림은 넣지 않는다.

    운영자 쪽과 같은 글을 쓰되 발송 기록은 따로 둔다(investor_alerts · last_investor_expired_date).
    한쪽 발송이 실패해도 다른 쪽이 다시 나가거나 막히지 않게 하려는 것이다.
    투자자 채팅이 등록되기 전에는 부르지 않는다(등록 뒤 가장 가까운 단계 하나만 나간다).
    """
    today = now.astimezone(KST).date().isoformat()
    exp_s = state.get("expire_at")
    exp = parse_time(exp_s)
    if exp is None:
        return []
    when = exp.strftime("%Y-%m-%d %H:%M")
    if is_expired(exp, now):
        if state.get("last_investor_expired_date") == today:
            return []
        return [{"level": "CRITICAL", "title": "업비트 키 만료됨",
                 "body": ("업비트 Open API 키가 만료되었습니다(" + when + "). 자동 매매 주문이 거절됩니다. "
                          "투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요. 키 값은 메신저에 적지 마세요."),
                 "marks": {"last_investor_expired_date": today}}]
    sent = [a[1] for a in state.get("investor_alerts") or []
            if isinstance(a, (list, tuple)) and len(a) == 2 and a[0] == exp_s]
    step = due_step(exp, now, sent)
    if step is None:
        return []
    d = days_left(exp, now)
    left = "오늘 만료" if d == 0 else str(d) + "일 남음"
    return [{"level": "CRITICAL" if step <= DANGER_DAYS else "WARNING",
             "title": "업비트 키 만료 " + ("오늘" if d == 0 else str(d) + "일 전"),
             "body": ("업비트 Open API 키가 " + when + " 에 만료됩니다(" + left + "). "
                      "만료되면 자동 매매 주문이 거절됩니다. "
                      "투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요. 키 값은 메신저에 적지 마세요."),
             "marks": {"investor_alert": [exp_s, step]}}]


def apply_marks(state: dict, marks: dict) -> None:
    for k, v in marks.items():
        if k in ("alert", "investor_alert"):
            field = "alerts" if k == "alert" else "investor_alerts"
            al = [a for a in state.get(field) or [] if isinstance(a, (list, tuple)) and len(a) == 2]
            al.append(list(v))
            state[field] = al
        else:
            state[k] = v


def record_success(state: dict, expire_at: str, now: datetime) -> None:
    """조회 성공. 만료일이 바뀌었으면(키 교체) 알림 기록·첫 실패 시각을 비운다."""
    if state.get("expire_at") != expire_at:
        state["alerts"] = []
        state["last_alert_date"] = None
        state["last_expired_alert_date"] = None
        state["last_fail_alert_date"] = None
        state["investor_alerts"] = []
        state["last_investor_expired_date"] = None
    state["expire_at"] = expire_at
    state["last_ok_at"] = iso(now)
    state["first_fail_at"] = None
    state["error_code"] = None


def record_failure(state: dict, err: str, now: datetime) -> None:
    """조회 실패. 마지막으로 성공한 expire_at 은 그대로 둔다."""
    state["error_code"] = err
    if not state.get("first_fail_at"):
        state["first_fail_at"] = iso(now)


# ---- 결과 파일 ----
def read_state(path: Path) -> Optional[dict]:
    """깨짐·없음·권한 오류는 None."""
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read(65536).decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def write_state(path: Path, state: dict) -> None:
    """임시 파일(600)에 쓴 뒤 os.replace 로 바꾼다."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".key_expiry.", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
