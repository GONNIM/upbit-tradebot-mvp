"""운영자 텔레그램 채널 시험 알림 1건 — 손으로 1회 돌리는 도구 (1101-06, 계획 2026-11-01-engine-start-overlap-guard 4절).

서버의 tradebot 은 systemd EnvironmentFile 로 `.env` 를 환경 변수로 받는다. 이 도구는 systemd 밖에서 돌므로
저장소 루트의 `.env` 를 직접 읽는다. `import config` 는 쓰지 않는다 — config.py 는 secrets.toml 에 UPBIT_ACCESS 가
있으면 load_dotenv() 를 부르지 않아, 서버에서는 운영자 키를 못 찾는다.

출력은 있음/없음·보냄/못 보냄뿐이다. 키 값은 어디에도 출력하지 않는다.
외부 발송(텔레그램)이므로 운영자 입회·승인 뒤에만 실행한다.

사용(저장소 루트에서): python3 scripts/v2/notify_operator_test.py
종료 코드: 0 보냄 · 1 못 보냄(원인은 출력하지 않음) · 2 키·.env 없음 · 3 드라이런 · 4 .env 읽기 예외
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TITLE = "운영자 채널 시험"
BODY = "운영자 채널 발송 확인용 시험 알림입니다(1101-06). 할 일은 없습니다."


def load_env(root: Path = ROOT) -> int:
    """`.env` 를 읽어 환경 변수에 더한다(이미 있는 값은 덮지 않음). 0 읽음 · 2 없음 · 4 예외."""
    env = root / ".env"
    if not env.is_file():
        print(".env 없음")
        return 2
    try:
        from dotenv import load_dotenv
        loaded = load_dotenv(env, override=False)
    except Exception as e:
        print(f".env 읽기 실패: {type(e).__name__}")
        return 4
    if not loaded:
        print(".env 에 읽을 줄 없음")
        return 2
    return 0


def quiet_notifier_log() -> None:
    """notifier 의 발송 예외 경고(`… {e}`)에는 토큰이 든 URL 이 섞일 수 있다 — 이 도구에서는 그 로그를 끈다.
    결과는 send 의 True/False 와 이 도구의 출력(있음/없음·보냄/못 보냄)으로만 본다."""
    import logging
    lg = logging.getLogger("services.notifier")
    lg.handlers[:] = [logging.NullHandler()]
    lg.propagate = False


def main(root: Path = ROOT) -> int:
    rc = load_env(root)
    if rc:
        return rc
    sys.path.insert(0, str(root))
    from services import notifier
    quiet_notifier_log()
    token, chat = notifier._get_operator_credentials()
    print(f"토큰: {'있음' if token else '없음'} · 운영자 채팅 ID: {'있음' if chat else '없음'}")
    if not (token and chat):
        print("키 없음 — 보내지 않음")
        return 2
    if os.environ.get("WO6_DRY_RUN") == "1":   # 키 확인까지만 하고 발송 직전에서 멈춤
        print("드라이런 — 보내지 않음")
        return 3
    ok = notifier.send(notifier.LEVEL_INFO, TITLE, BODY, dedupe_key="operator_channel_test",
                       audience=notifier.AUDIENCE_OPERATOR)
    print("보냄" if ok else "못 보냄 — 원인은 출력하지 않음(토큰 보호). 운영자와 수신 여부 확인")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
