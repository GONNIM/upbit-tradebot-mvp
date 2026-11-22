"""투자자 텔레그램 채팅 등록 (1122-01 ㉠) — 서버에서 운영자가 손으로 돌린다.

순서
1. 투자자가 텔레그램에서 @upbit_tradebot_bot 의 「시작」을 누른다(누른 뒤 24시간 안에 돌려야 보인다).
2. `venv/bin/python scripts/telegram_investor_register.py` → 봇 이름과 「시작」을 누른 개인 대화 목록(번호·이름·누른 시각)만 보인다.
3. `venv/bin/python scripts/telegram_investor_register.py --pick <번호>` → .env 에 TELEGRAM_CHAT_ID_INVESTOR 한 줄을 넣거나 바꾼다.
   .env 는 같은 폴더 임시 파일(600)에 쓴 뒤 바꿔 넣는다. 사본(.bak 등)은 만들지 않는다(project-rules 비밀 파일 규칙).
4. `venv/bin/python scripts/key_expiry_check.py --test-investor` 로 시험 알림을 보낸다.

- 토큰·채팅 번호·응답 원문은 출력하지 않는다. 예외는 종류 이름만 출력한다(주소에 토큰이 들어 있다).
- 엔진·tradebot-v2 는 이 값을 쓰지 않으므로 재시작하지 않는다. 키 만료 점검(cron)이 다음 실행부터 읽는다.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
KEY = "TELEGRAM_CHAT_ID_INVESTOR"
API = "https://api.telegram.org"
KST = ZoneInfo("Asia/Seoul")


def env_values(root: Path) -> dict:
    from dotenv import dotenv_values
    return dict(dotenv_values(root / ".env"))


def call(token: str, method: str, get=None):
    """텔레그램 API 결과(result) 또는 None. 실패 이유는 종류 이름만 돌려준다."""
    if get is None:
        import requests
        get = requests.get
    try:
        r = get(API + "/bot" + token + "/" + method, timeout=10)
        if getattr(r, "status_code", None) != 200:
            return None, "http_" + str(getattr(r, "status_code", None))
        data = r.json()
        if not isinstance(data, dict) or not data.get("ok"):
            return None, "not_ok"
        return data.get("result"), None
    except Exception as e:
        return None, type(e).__name__


def private_chats(updates) -> list:
    """「시작」(또는 글)을 보낸 개인 대화. 같은 사람은 마지막 것 하나. [{id, name, username, at, started}]"""
    out = {}
    for u in updates or []:
        m = u.get("message") if isinstance(u, dict) else None
        if not isinstance(m, dict):
            continue
        c = m.get("chat") or {}
        if c.get("type") != "private" or "id" not in c:
            continue
        out[c["id"]] = {
            "id": c["id"],
            "name": " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or "(이름 없음)",
            "username": c.get("username") or "",
            "at": datetime.fromtimestamp(int(m.get("date") or 0), KST).strftime("%m/%d %H:%M"),
            "started": (m.get("text") or "").startswith("/start"),
        }
    return list(out.values())


def write_env_key(root: Path, value: str) -> str:
    """KEY 줄을 넣거나 바꾼다. 다른 줄은 글자 그대로 둔다. 돌려주는 값: added | replaced."""
    env = root / ".env"
    lines = env.read_text(encoding="utf-8").splitlines(keepends=True)
    new_line = KEY + "=" + value + "\n"
    found = False
    for i, ln in enumerate(lines):
        if ln.split("=", 1)[0].strip().replace("export ", "") == KEY:
            lines[i] = new_line
            found = True
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)
    fd, tmp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(root))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(lines))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, env)
        os.chmod(env, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return "replaced" if found else "added"


def main(argv, root: Path = ROOT, get=None) -> int:
    env = env_values(root)
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("STOP: .env 에 TELEGRAM_BOT_TOKEN 없음")
        return 1
    me, err = call(token, "getMe", get)
    if me is None:
        print("STOP: getMe 실패 (" + str(err) + ")")
        return 1
    print("봇: @" + str(me.get("username")) + " · 이름 " + str(me.get("first_name")))
    ups, err = call(token, "getUpdates", get)
    if ups is None:
        print("STOP: getUpdates 실패 (" + str(err) + ") — 웹후크가 걸려 있으면 이 방법을 쓸 수 없음")
        return 1
    chats = private_chats(ups)
    if not chats:
        print("「시작」을 누른 개인 대화가 없습니다(누른 지 24시간이 지났으면 다시 눌러 달라고 하십시오).")
        return 1
    ops = {str(env.get(k)) for k in ("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID_OPERATOR", "TELEGRAM_CHAT_ID_WARNING",
                                     "TELEGRAM_CHAT_ID_CRITICAL") if env.get(k)}
    for i, c in enumerate(chats, 1):
        tag = " · 운영자 채팅" if str(c["id"]) in ops else ""
        cur = " · 지금 등록됨" if str(env.get(KEY) or "") == str(c["id"]) else ""
        print(f"{i}. {c['name']} {('@' + c['username']) if c['username'] else ''} · {c['at']} · "
              f"{'시작 누름' if c['started'] else '글 보냄'}{tag}{cur}")
    if len(argv) == 2 and argv[0] == "--pick":
        try:
            n = int(argv[1])
        except ValueError:
            print("STOP: --pick 뒤에 번호")
            return 1
        if not 1 <= n <= len(chats):
            print("STOP: 번호가 목록에 없음")
            return 1
        c = chats[n - 1]
        if str(c["id"]) in ops:
            print("STOP: 고른 대화가 운영자 채팅과 같음 — 투자자 대화를 고르십시오")
            return 1
        how = write_env_key(root, str(c["id"]))
        print("등록함: " + c["name"] + " (" + ("새로 넣음" if how == "added" else "바꿈") + ") · .env 권한 "
              + oct(os.stat(root / ".env").st_mode & 0o777))
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main(sys.argv[1:]))
