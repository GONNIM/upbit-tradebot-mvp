"""
WO-12 (2026-09-30): 서비스 기동 시 엔진 자동 재개 + 기동 시점 마이그레이션.

문제: 엔진 자동 재개([AUTO-RESUME])와 스키마 마이그레이션이 대시보드 첫 접속 때만 실행됐다.
      재시작 뒤 사람이 접속할 때까지 손절을 포함한 매매가 멈췄다 (09-18 46분, 09-30 5·6분).

방식 (계획서 §2.2 D안): scripts/tradebot_boot.py 가 같은 프로세스 안에서 이 모듈의
      boot_resume_all() 을 기동 스레드로 실행한 뒤 Streamlit 서버를 띄운다.
      엔진 스레드와 대시보드가 같은 engine_manager 를 공유한다.

원칙:
- 대상은 "직전에 LIVE 로 실행 중이던 사용자"만 (engine_status=실행 중 + last_mode=LIVE).
- 안전 조건(세션 대신 기동 시점 실측): Upbit 키 조회 성공 + 운용자산 > 0.
- 실패·보류 시 DB 상태를 바꾸지 않는다 (대시보드 첫 접속 경로가 기존대로 판단).
- trading_paused 는 건드리지 않는다. 매매 판정 로직 무변경.
- 결과는 텔레그램으로 알린다 (성공 INFO / 실패 CRITICAL).
"""
from __future__ import annotations

import glob
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# user_id → {"result": "success"|"skip"|"fail", "reason": str, "at": iso}
_STATE: dict[str, dict[str, Any]] = {}
_STATE_LOCK = threading.Lock()


def get_boot_resume_state(user_id: str) -> Optional[dict]:
    """기동 재개 결과 (대시보드 [AUTO-RESUME] skip 판단·로그용). 없으면 None."""
    with _STATE_LOCK:
        s = _STATE.get(user_id)
        return dict(s) if s else None


def _set_state(user_id: str, result: str, reason: str = "") -> None:
    with _STATE_LOCK:
        _STATE[user_id] = {"result": result, "reason": reason, "at": datetime.now(KST).isoformat()}


def list_known_users() -> list[str]:
    """DB 디렉터리의 tradebot_<user>.db 파일에서 사용자 목록 (빈 user_id 파일 제외)."""
    from services.init_db import DB_DIR, DB_PREFIX
    users = []
    for path in sorted(glob.glob(os.path.join(DB_DIR, f"{DB_PREFIX}_*.db"))):
        name = os.path.basename(path)[len(DB_PREFIX) + 1:-3]
        if name and os.path.getsize(path) > 0:
            users.append(name)
    return users


def list_resume_targets(users: Optional[list[str]] = None) -> list[str]:
    """직전에 LIVE 로 실행 중이던 사용자 (engine_status=True + last_mode='LIVE')."""
    from services.db import get_engine_status, get_last_engine_mode
    targets = []
    for uid in (users if users is not None else list_known_users()):
        try:
            if get_engine_status(uid) and str(get_last_engine_mode(uid) or "").upper() == "LIVE":
                targets.append(uid)
        except Exception as e:
            logger.warning(f"[BOOT-RESUME] 대상 판정 실패 (제외): user={uid} err={e}")
    return targets


def verify_live_account() -> tuple[bool, str, float]:
    """
    LIVE 안전 조건 실측 (조회 전용).
    Returns: (ok, reason, capital_krw) — capital = KRW(가용+묶임) + 코인(가용+묶임)×평균매수가
    """
    try:
        import pyupbit
        from config import ACCESS, SECRET
        balances = pyupbit.Upbit(ACCESS, SECRET).get_balances()
    except Exception as e:
        return False, f"키 조회 예외: {type(e).__name__}: {e}", 0.0
    if not isinstance(balances, list):
        return False, f"키 조회 실패: {balances!r}"[:200], 0.0
    capital = 0.0
    for b in balances:
        try:
            qty = float(b.get("balance") or 0) + float(b.get("locked") or 0)
            if str(b.get("currency", "")).upper() == "KRW":
                capital += qty
            else:
                capital += qty * float(b.get("avg_buy_price") or 0)
        except Exception:
            continue
    if capital <= 0:
        return False, "운용자산 0", capital
    return True, "ok", capital


def _notify(level: str, title: str, body: str, key: str) -> None:
    try:
        from services.notifier import send
        send(level, title, body, dedupe_key=key, dedupe_ttl=600)
    except Exception:
        pass


def boot_resume_all(
    *,
    boot_started_at: Optional[float] = None,
    users: Optional[list[str]] = None,
    verify: Callable[[], tuple[bool, str, float]] = verify_live_account,
    start: Optional[Callable[[str], bool]] = None,
) -> dict[str, str]:
    """
    서비스 기동 시 1회 실행. 사용자별 결과 {user_id: "success"|"skip"|"fail"} 반환.
    verify/start 는 테스트 주입용.
    """
    t0 = boot_started_at or time.time()
    results: dict[str, str] = {}

    known = users if users is not None else list_known_users()

    # 1) 기동 시점 마이그레이션 (대상 여부와 무관하게 알려진 사용자 전부)
    try:
        from services.init_db import ensure_all_schemas
        for uid in known:
            try:
                ensure_all_schemas(uid)
            except Exception as e:
                logger.error(f"[BOOT-RESUME] 마이그레이션 실패: user={uid} err={e}")
    except Exception as e:
        logger.error(f"[BOOT-RESUME] 마이그레이션 모듈 로드 실패: {e}")

    targets = list_resume_targets(known)
    logger.info(f"[BOOT-RESUME] start | known={known} targets={targets}")
    if not targets:
        return results

    if start is None:
        from engine.engine_manager import engine_manager

        def start(uid: str) -> bool:
            return engine_manager.start_engine(uid, test_mode=False, mode="LIVE")

    ok, reason, capital = verify()
    for uid in targets:
        if not ok:
            results[uid] = "fail"
            _set_state(uid, "fail", reason)
            logger.error(f"[BOOT-RESUME] fail user={uid} reason={reason} (DB 상태 무변경, 첫 접속 경로에 맡김)")
            _notify(
                "CRITICAL",
                f"🚨 서비스 기동 — LIVE 엔진 자동 재개 실패 ({uid})",
                f"사유: {reason}\n\n💡 대시보드 접속 시 키·운용자산을 확인하고 수동으로 시작하세요.",
                f"boot_resume:{uid}:fail",
            )
            continue
        try:
            started = start(uid)
        except Exception as e:
            started = False
            reason = f"start_engine 예외: {type(e).__name__}: {e}"
        if started:
            elapsed = time.time() - t0
            results[uid] = "success"
            _set_state(uid, "success", f"capital≈{capital:,.0f}")
            logger.info(f"[BOOT-RESUME] success user={uid} mode=LIVE elapsed={elapsed:.1f}s capital≈{capital:,.0f}")
            _notify(
                "INFO",
                f"🔄 서비스 기동 — LIVE 엔진 자동 재개 ({uid})",
                f"기동 → 재개: {elapsed:.0f}초\n운용자산: 약 {capital:,.0f} KRW\n(매매 일시정지 설정은 그대로 유지)",
                f"boot_resume:{uid}:success",
            )
        else:
            from engine.engine_manager import engine_manager as _em
            if _em.get_running_mode(uid) == "LIVE":
                results[uid] = "skip"
                _set_state(uid, "skip", "이미 실행 중")
                logger.info(f"[BOOT-RESUME] skip user={uid} reason=이미 실행 중")
            else:
                results[uid] = "fail"
                _set_state(uid, "fail", reason if reason != "ok" else "start_engine=False")
                logger.error(f"[BOOT-RESUME] fail user={uid} reason={_STATE[uid]['reason']}")
                _notify(
                    "CRITICAL",
                    f"🚨 서비스 기동 — LIVE 엔진 자동 재개 실패 ({uid})",
                    f"사유: {_STATE[uid]['reason']}\n\n💡 대시보드 접속 시 수동으로 시작하세요.",
                    f"boot_resume:{uid}:fail",
                )
    return results
