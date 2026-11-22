"""업비트 키 만료일 점검 — 하루 2번(09:05 · 21:05) cron 이 돈다 (1122-01, 계획 docs/plans/2026-11-22-key-expiry-alert/plan.md 3-2).

- 업비트 GET /v1/api_keys 로 지금 키의 expire_at 만 받아 services/data/.key_expiry.json(600)에 남긴다.
- 키 읽기 순서는 config.py 와 같다: secrets.toml 최상위 UPBIT_ACCESS/UPBIT_SECRET → 없으면 .env.
  config 는 import 하지 않는다(작업 폴더에 secrets 가 없으면 StreamlitSecretNotFoundError 로 죽는다).
- 텔레그램 값은 .env 를 직접 읽는다(scripts/v2/notify_operator_test.py 와 같은 이유).
- core.trader·pyupbit·config 를 import 하지 않는다. 주문 경로와 무관하다.
- 키 값·토큰·응답 원문은 출력·파일·로그 어디에도 남기지 않는다. 출력은 상태 한 줄뿐이다.

사용(서버, cron): deploy/key-expiry.cron
종료 코드: 0 조회 성공 · 1 조회 실패(결과 파일·알림 판정은 그대로 함)
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.upbit.com/v1/api_keys"
TIMEOUT = 5


def load_upbit_keys(root: Path):
    """(access, secret) 또는 None. 값은 돌려주기만 하고 출력하지 않는다."""
    sec_file = root / ".streamlit" / "secrets.toml"
    if sec_file.is_file():
        try:
            import tomllib
            with open(sec_file, "rb") as f:
                d = tomllib.load(f)
            a, s = d.get("UPBIT_ACCESS"), d.get("UPBIT_SECRET")
            if isinstance(a, str) and isinstance(s, str) and a and s:
                return a, s
        except Exception:
            pass
    env_file = root / ".env"
    if env_file.is_file():
        try:
            from dotenv import dotenv_values
            d = dotenv_values(env_file)
            a, s = d.get("UPBIT_ACCESS"), d.get("UPBIT_SECRET")
            if a and s:
                return a, s
        except Exception:
            pass
    return None


def load_telegram_env(root: Path) -> None:
    env_file = root / ".env"
    if env_file.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except Exception:
            pass


def quiet_notifier_log() -> None:
    """notifier 의 발송 예외 경고에는 토큰이 든 URL 이 섞일 수 있다 — 이 스크립트에서는 그 로그를 끈다."""
    import logging
    lg = logging.getLogger("services.notifier")
    lg.handlers[:] = [logging.NullHandler()]
    lg.propagate = False


def _bearer(access: str, secret: str) -> str:
    import jwt
    tok = jwt.encode({"access_key": access, "nonce": str(uuid.uuid4())}, secret, algorithm="HS256")
    if isinstance(tok, bytes):
        tok = tok.decode()
    return "Bearer " + tok


def fetch_expire_at(access: str, secret: str, http=None):
    """(expire_at ISO 문자열, None) 또는 (None, 오류 코드). 응답 원문은 남기지 않는다."""
    from v2 import key_expiry as ke
    if http is None:
        import requests as http
    try:
        r = http.get(API_URL, headers={"Authorization": _bearer(access, secret)}, timeout=TIMEOUT)
    except Exception as e:
        return None, ("timeout" if "Timeout" in type(e).__name__ else "network")
    code = getattr(r, "status_code", None)
    if code == 401:
        return None, "http_401"
    if code != 200:
        return None, "http_" + str(code)
    try:
        data = r.json()
    except Exception:
        return None, "bad_json"
    if not isinstance(data, list):
        return None, "not_list"
    mine = [it for it in data if isinstance(it, dict) and it.get("access_key") == access]
    if not mine:
        return None, "key_not_found"
    if len(mine) > 1:
        return None, "key_duplicate"
    exp = ke.parse_time(mine[0].get("expire_at"))
    if exp is None:
        return None, "bad_expire_at"
    return ke.iso(exp), None


def _same_channel(notifier) -> bool:
    """기본 채널과 운영자 채널이 같은 채팅인지(값은 비교만 하고 남기지 않는다).
    합쳐 보내는 알림은 WARNING·CRITICAL 어느 등급이든 될 수 있으므로 두 등급 채널이 모두 운영자 채팅과 같을 때만 참."""
    try:
        _t2, op = notifier._get_operator_credentials()
        if not op:
            return False
        for level in ("WARNING", "CRITICAL"):
            _t1, c = notifier._get_credentials(level=level)
            if c != op:
                return False
        return True
    except Exception:
        return False


def run(root: Path = ROOT, now: datetime | None = None, http=None, notifier=None) -> int:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from v2 import key_expiry as ke
    now = now or datetime.now(ke.KST)
    path = root / "services" / "data" / ke.RESULT_NAME
    state = ke.read_state(path) or {}

    keys = load_upbit_keys(root)
    if keys is None:
        exp_s, err = None, "no_keys"
    else:
        exp_s, err = fetch_expire_at(keys[0], keys[1], http=http)
    keys = None
    state["checked_at"] = ke.iso(now)
    if err is None:
        ke.record_success(state, exp_s, now)
    else:
        ke.record_failure(state, err, now)

    if notifier is None:
        load_telegram_env(root)
        from services import notifier
        quiet_notifier_log()
    alerts = ke.plan_alerts(state, now, err, _same_channel(notifier))
    sent = 0
    for a in alerts:
        ok = False
        try:
            ok = bool(notifier.send(a["level"], a["title"], a["body"], audience=a["audience"]))
        except Exception:
            ok = False
        if ok:
            ke.apply_marks(state, a["marks"])
            sent += 1

    ke.write_state(path, state)
    exp = ke.parse_time(state.get("expire_at"))
    d = ke.days_left(exp, now) if exp else None
    print("key_expiry " + ("ok" if err is None else "fail") + " days_left=" + str(d)
          + " alerts=" + str(sent) + "/" + str(len(alerts)) + " err=" + str(err))
    return 0 if err is None else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(run())
