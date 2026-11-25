"""업비트 키 만료일 점검 — 하루 2번(09:05 · 21:05) cron 이 돈다 (1122-01, 계획 docs/plans/2026-11-22-key-expiry-alert/plan.md 3-2).

- 업비트 GET /v1/api_keys 로 지금 키의 expire_at 만 받아 services/data/.key_expiry.json(600)에 남긴다.
- 키 읽기 순서는 config.py 와 같다: secrets.toml 최상위 UPBIT_ACCESS/UPBIT_SECRET → 없으면 .env.
  config 는 import 하지 않는다(작업 폴더에 secrets 가 없으면 StreamlitSecretNotFoundError 로 죽는다).
- 텔레그램 값은 .env 를 직접 읽는다(scripts/v2/notify_operator_test.py 와 같은 이유).
- core.trader·pyupbit·config 를 import 하지 않는다. 주문 경로와 무관하다.
- 키 값·토큰·응답 원문은 출력·파일·로그 어디에도 남기지 않는다. 출력은 상태 한 줄뿐이다.

- (1122-01 ㉠) .env 에 TELEGRAM_CHAT_ID_INVESTOR 가 있으면 단계·만료 알림을 투자자 채팅에도 보낸다(발송 기록 따로).
- (1122-01 ②, 2026-11-23) 그 밖의 모든 알림도 notifier 가 투자자 사본을 보낸다. 단계·만료 알림은 위 직접 발송이 이미
  보내므로 사본을 끄고(investor_copy=False), 점검 실패 글이 든 알림은 운영자 글 그대로 사본이 간다(2026-11-24 사용자 지시:
  가공·수정 없음). same_channel 로 단계 알림에 점검 실패가 합쳐진 경우 투자자는 단계 문구를 직접 발송과 사본으로 두 번 본다.
  출력 줄의 copy= 칸: on · off:<사유> · fail:<코드> (이 스크립트는 notifier 로그를 끄므로 사본 상태를 여기서 본다).
  등록: scripts/telegram_investor_register.py · 시험 알림: `venv/bin/python scripts/key_expiry_check.py --test-investor`

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


INVESTOR_CHAT_KEY = "TELEGRAM_CHAT_ID_INVESTOR"
TELEGRAM_API = "https://api.telegram.org"


def investor_chat(notifier):
    """투자자 채팅(1122-01 ㉠). .env 의 TELEGRAM_CHAT_ID_INVESTOR 만 본다(다른 채팅으로 대체하지 않음).
    기본·등급 채널과 같은 채팅이면 이미 그쪽으로 받으므로 None(두 번 보내지 않음). 값은 비교만 하고 남기지 않는다."""
    chat = os.environ.get(INVESTOR_CHAT_KEY)
    if not chat:
        return None
    try:
        for level in ("WARNING", "CRITICAL"):
            _t, c = notifier._get_credentials(level=level)
            if c and str(c) == str(chat):
                return None
    except Exception:
        pass
    return str(chat)


def send_direct(chat: str, level: str, title: str, body: str, notifier, post=None) -> bool:
    """투자자 채팅으로 한 건 보낸다. 토큰이 든 주소·응답 원문·예외 글은 남기지 않는다."""
    return send_direct_why(chat, level, title, body, notifier, post=post) == "ok"


def send_direct_why(chat: str, level: str, title: str, body: str, notifier, post=None) -> str:
    """보낸 결과 코드: ok · no_token · http_<코드> · 예외 종류 이름. 토큰·주소·예외 글은 돌려주지 않는다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not chat:
        return "no_token"
    try:
        if post is None:
            import requests
            post = requests.post
        text = notifier._format_message(level, title, body)
        r = post(TELEGRAM_API + "/bot" + token + "/sendMessage",
                 data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": "true"},
                 timeout=TIMEOUT)
        code = getattr(r, "status_code", None)
        return "ok" if code == 200 else "http_" + str(code)
    except Exception as e:
        return type(e).__name__


def send_investor_test(root: Path = ROOT, notifier=None, post=None) -> int:
    """투자자 채팅 등록 뒤 시험 알림 한 건(결과 파일·업비트 조회는 건드리지 않음). 출력: investor_test ok|fail|off."""
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if notifier is None:
        load_telegram_env(root)
        from services import notifier
        quiet_notifier_log()
    chat = investor_chat(notifier)
    if chat is None:
        print("investor_test off")
        return 1
    why = send_direct_why(chat, "INFO", "자동매매 알림 등록 시험",
                          "이 알림이 보이면 등록이 끝났습니다. 앞으로 자동매매 봇의 알림(매매·운영·업비트 키 만료)을 "
                          "이 대화방으로 함께 보내 드립니다. 답장은 하지 않으셔도 됩니다.", notifier, post=post)
    print("investor_test " + ("ok" if why == "ok" else "fail " + why))
    return 0 if why == "ok" else 1


def run(root: Path = ROOT, now: datetime | None = None, http=None, notifier=None, post=None) -> int:
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
            if a.get("audience") == "operator" or a.get("fail_part"):
                kw = {}   # 점검 실패 글이 든 알림은 운영자가 받는 글 그대로 투자자 사본이 간다
            else:
                kw = {"investor_copy": False}   # 단계·만료 알림은 아래 직접 발송이 투자자에게 보냄(두 번 안 감)
            ok = bool(notifier.send(a["level"], a["title"], a["body"], audience=a["audience"], **kw))
        except Exception:
            ok = False
        if ok:
            ke.apply_marks(state, a["marks"])
            sent += 1

    inv = investor_chat(notifier)
    if inv is None:
        inv_s = "off"
    else:
        inv_alerts = ke.plan_investor_alerts(state, now)
        inv_sent = 0
        for a in inv_alerts:
            if send_direct(inv, a["level"], a["title"], a["body"], notifier, post=post):
                ke.apply_marks(state, a["marks"])
                inv_sent += 1
        inv_s = str(inv_sent) + "/" + str(len(inv_alerts))

    ke.write_state(path, state)
    exp = ke.parse_time(state.get("expire_at"))
    d = ke.days_left(exp, now) if exp else None
    print("key_expiry " + ("ok" if err is None else "fail") + " days_left=" + str(d)
          + " alerts=" + str(sent) + "/" + str(len(alerts)) + " investor=" + inv_s
          + " copy=" + copy_field(notifier) + " err=" + str(err))
    return 0 if err is None else 1


def copy_field(notifier) -> str:
    """1122-01: 투자자 사본 상태 한 칸 — on · off:<사유> · fail:<코드>. 대기 줄을 최대 3초 기다려 보낸 뒤 본다.
    가짜 notifier(시험)처럼 사본 기능이 없으면 off."""
    st = getattr(notifier, "copy_state", None)
    if not callable(st):
        return "off"
    try:
        fl = getattr(notifier, "flush_copies", None)
        if callable(fl):
            fl(3.0)
        on, why = st()
        if not on:
            return "off:" + str(why)
        from services import investor_copy as ic
        last = str(getattr(ic, "last_result", "none"))
        return last if last.startswith("fail:") else "on"
    except Exception:
        return "off:오류"


if __name__ == "__main__":
    os.chdir(ROOT)
    if sys.argv[1:] == ["--test-investor"]:
        sys.exit(send_investor_test())
    sys.exit(run())
