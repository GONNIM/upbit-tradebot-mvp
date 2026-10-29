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
    TRADEBOT_V2_CONTROL=0 이면 신버전 엔진 제어 요청 감시 스레드(2차 T11)를 띄우지 않는다 (기본 켜짐)

엔진 생존 파일 (2026-10-25, 신버전 대시보드 「트레이딩 엔진 상태」):
    데몬 스레드 engine_alive 가 5초마다 services/data/.engine_alive.json 에
    {"pid", "at"(KST ISO), "running": {계정: 엔진 스레드가 살아 있는가}} 를 쓴다(임시 파일 → os.replace, 600).
    읽기·파일 쓰기만 한다. 이 스레드가 실패해도 엔진·서버는 영향이 없고 신버전은 Stopped 로 보인다.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("tradebot_boot")

BOOT_STARTED_AT = time.time()

ENGINE_ALIVE_PATH = os.path.join(ROOT, "services", "data", ".engine_alive.json")
ENGINE_ALIVE_INTERVAL_SEC = 5
_KST = ZoneInfo("Asia/Seoul")


def _boot_resume_thread() -> None:
    try:
        time.sleep(float(os.environ.get("TRADEBOT_BOOT_DELAY", "3")))
        from engine.boot_resume import boot_resume_all
        boot_resume_all(boot_started_at=BOOT_STARTED_AT)
    except Exception as e:  # 기동 재개 실패가 서버 기동을 막으면 안 된다
        logging.getLogger("engine.boot_resume").error(f"[BOOT-RESUME] 기동 스레드 예외: {type(e).__name__}: {e}")
    finally:
        # 2차 T12 (PO 결정): 기동 재개 완료 신호 — 감시 스레드가 이 뒤에 처리 중 전환 행을 복구한다.
        # (engine/boot_resume.py 는 바이트 고정이라 여기서 세운다. 신호가 없으면 감시 시작 60초 뒤 예비 규칙.)
        try:
            from core.engine_control import BOOT_RESUME_DONE
            BOOT_RESUME_DONE.set()
        except Exception as e:
            logger.error(f"[BOOT-RESUME] 완료 신호 실패(60초 예비 규칙으로) | {type(e).__name__}")


def _write_engine_alive(path: str, running: dict, gen: dict = None) -> None:
    """임시 파일에 쓴 뒤 os.replace(원자적). 권한 600.
    2차 T11: "gen" = {계정: 엔진 시작 세대} — 같은 pid 안 재시작(복구 래퍼 포함)을 신버전 캔들 수집이 알아챈다."""
    body = {"pid": os.getpid(), "at": datetime.now(_KST).isoformat(), "running": running, "gen": gen or {}}
    # 2차 T11 수정 1회차: 고정 임시 이름(.engine_alive.json.tmp)+O_TRUNC 는 그 자리의 링크를 따라가 바깥 파일을
    # 덮어쓴다 → 임의 이름 임시 파일(O_EXCL 600) 뒤 os.replace. 파일 이름·내용·주기는 그대로.
    from core.safe_file import atomic_write_600
    atomic_write_600(path, json.dumps(body))


STALE_TMP_SEC = 600
STALE_TMP_PREFIXES = (".engine_alive.json", ".engine_restart.json")


def _clean_stale_tmp() -> list:
    """2차 T11 수정 2회차(N7): 기동 때 생존 파일·쉼 표식 폴더(services/data)의 10분 넘은 우리 임시 파일
    (`.engine_alive.json…tmp`·`.engine_restart.json…tmp`)만 지운다. 링크·다른 모듈 파일은 건드리지 않는다."""
    from core.safe_file import clean_stale_tmp
    removed = clean_stale_tmp(os.path.dirname(ENGINE_ALIVE_PATH), STALE_TMP_PREFIXES, STALE_TMP_SEC)
    if removed:
        logger.info(f"[ENGINE-ALIVE] 오래된 임시 파일 정리 {len(removed)}개")
    return removed


def engine_alive_tick(manager, path: str = None) -> dict:
    """한 번 기록한다: 엔진 스레드 목록의 계정별 「get_running_mode(계정) is not None」.
    (구버전 대시보드 is_running 과 같은 _threads[계정].is_alive() — 세션 참조 없음)"""
    running = {}
    for uid in manager.get_active_user_ids():
        running[str(uid)] = manager.get_running_mode(uid) is not None
    gen = {}
    try:
        _gm = getattr(manager, "gen_map", None)
        if callable(_gm):
            gen = {str(k): int(v) for k, v in (_gm() or {}).items()}
    except Exception:  # 세대 값을 못 읽어도 생존 기록은 쓴다
        gen = {}
    _write_engine_alive(path or ENGINE_ALIVE_PATH, running, gen)
    return running


def _engine_alive_manager():
    from engine.engine_manager import engine_manager  # 스레드 안에서 지연 import (기동을 막지 않는다)
    return engine_manager


def _engine_alive_loop(path: str = None, interval: float = ENGINE_ALIVE_INTERVAL_SEC,
                       get_manager=_engine_alive_manager, stop: threading.Event = None,
                       start_delay: float = 0.0) -> None:
    stop = stop or threading.Event()
    # 기동 직후 boot_resume·대시보드와 engine_manager 를 동시에 import 하지 않도록 먼저 기다린다
    if start_delay > 0 and stop.wait(start_delay):
        return
    try:
        manager = get_manager()
    except Exception as e:  # 감시 스레드 실패는 서버·엔진에 영향이 없다(신버전은 Stopped 로 보임)
        logger.error(f"[ENGINE-ALIVE] 시작 실패: {type(e).__name__}: {e}")
        return
    failed = False
    while not stop.is_set():
        try:
            engine_alive_tick(manager, path)
            failed = False
        except Exception as e:  # 한 번 실패해도 계속 시도한다. 같은 오류는 처음 한 번만 남긴다
            if not failed:
                logger.error(f"[ENGINE-ALIVE] 기록 실패: {type(e).__name__}: {e}")
            failed = True
        stop.wait(interval)


def _engine_alive_thread() -> None:
    try:
        # boot_resume(TRADEBOT_BOOT_DELAY 뒤 import)보다 늦게 시작한다
        _engine_alive_loop(start_delay=float(os.environ.get("TRADEBOT_BOOT_DELAY", "3")) + 2.0)
    except Exception as e:
        logger.error(f"[ENGINE-ALIVE] 스레드 예외: {type(e).__name__}: {e}")


def _control_thread() -> None:
    """2차 T11 (결정 D3): 신버전 엔진 제어 요청 감시(2초 주기) — 엔진 스레드 밖 데몬. 엔진이 멈춰 있어도 「엔진 시작」 처리.
    실패해도 서버·엔진은 영향이 없다(신버전 요청만 처리되지 않음 — 화면 「엔진이 응답하지 않습니다」)."""
    try:
        time.sleep(float(os.environ.get("TRADEBOT_BOOT_DELAY", "3")) + 2.0)
        from engine.control_requests import control_loop
        try:
            # 2차 T12: 전환·예약·복귀·예약 취소 처리와 예약 완료 tick 을 붙인다. 실패해도 T11 요청 처리는 그대로.
            from engine.strategy_switch import install as _install_switch
            _install_switch()
        except Exception as e:
            logger.error(f"[CONTROL] 전환 처리 설치 실패(전환 요청은 not_ready) | {type(e).__name__}: {e}")
        control_loop()
    except Exception as e:
        logger.error(f"[CONTROL] 감시 스레드 예외: {type(e).__name__}: {e}")


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

    try:
        _clean_stale_tmp()
    except Exception as e:  # 정리 실패가 기동을 막으면 안 된다
        logger.error(f"[ENGINE-ALIVE] 임시 파일 정리 실패: {type(e).__name__}: {e}")

    if os.environ.get("TRADEBOT_BOOT_RESUME", "1") != "0":
        threading.Thread(target=_boot_resume_thread, name="boot_resume", daemon=True).start()

    try:
        threading.Thread(target=_engine_alive_thread, name="engine_alive", daemon=True).start()
    except Exception as e:  # 스레드를 못 띄워도 서버(bootstrap.run)는 반드시 기동한다
        logger.error(f"[ENGINE-ALIVE] 스레드 시작 실패: {type(e).__name__}: {e}")

    if os.environ.get("TRADEBOT_V2_CONTROL", "1") != "0":
        try:
            threading.Thread(target=_control_thread, name="v2_control", daemon=True).start()
        except Exception as e:  # 스레드를 못 띄워도 서버(bootstrap.run)는 반드시 기동한다
            logger.error(f"[CONTROL] 스레드 시작 실패: {type(e).__name__}: {e}")

    bootstrap.run(main_script, False, [], flag_options)


if __name__ == "__main__":
    main()
