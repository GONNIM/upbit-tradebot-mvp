"""
WO-12 (2026-09-30): tradebot 서비스 기동 스크립트.

`streamlit run app.py --server.port=8501 --server.address=0.0.0.0` 와 같은 서버를 같은 프로세스에서 띄우고,
그 전에 기동 재개 스레드(engine/boot_resume.py)를 시작한다. 엔진 스레드와 대시보드가 같은
engine_manager 를 공유하므로, 사람이 대시보드에 접속하지 않아도 직전 LIVE 엔진이 다시 돈다.

systemd:
    ExecStart=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py

환경변수:
    TRADEBOT_PORT (기본 8501), TRADEBOT_ADDRESS (기본 0.0.0.0),
    TRADEBOT_BOOT_DELAY (기본 3초 — 서버 기동 로그가 먼저 찍히도록 두는 짧은 지연)
    TRADEBOT_BOOT_RESUME=0 이면 기동 재개를 끈다 (서버만 기동, 기존 첫 접속 재개와 같음)
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("tradebot_boot")

BOOT_STARTED_AT = time.time()


def _boot_resume_thread() -> None:
    try:
        time.sleep(float(os.environ.get("TRADEBOT_BOOT_DELAY", "3")))
        from engine.boot_resume import boot_resume_all
        boot_resume_all(boot_started_at=BOOT_STARTED_AT)
    except Exception as e:  # 기동 재개 실패가 서버 기동을 막으면 안 된다
        logging.getLogger("engine.boot_resume").error(f"[BOOT-RESUME] 기동 스레드 예외: {type(e).__name__}: {e}")


def main() -> None:
    from streamlit import config as _config
    from streamlit.web import bootstrap

    main_script = os.path.join(ROOT, "app.py")
    flag_options = {
        "server_port": int(os.environ.get("TRADEBOT_PORT", "8501")),
        "server_address": os.environ.get("TRADEBOT_ADDRESS", "0.0.0.0"),
    }
    # `streamlit run` (streamlit.web.cli._main_run) 과 같은 순서
    _config._main_script_path = os.path.abspath(main_script)
    bootstrap.load_config_options(flag_options=flag_options)

    # 로깅: streamlit 로거 설정 이후 앱 모듈 로거가 journal 에 찍히도록 기본 핸들러 보장
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )  # core/trader.py·engine/engine_manager.py 등과 같은 형식

    if os.environ.get("TRADEBOT_BOOT_RESUME", "1") != "0":
        threading.Thread(target=_boot_resume_thread, name="boot_resume", daemon=True).start()

    bootstrap.run(main_script, False, [], flag_options)


if __name__ == "__main__":
    main()
