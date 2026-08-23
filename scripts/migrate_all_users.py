#!/usr/bin/env python3
"""
WO-2 (JTO-Claim-20260821-001): systemd ExecStartPre 마이그레이션 CLI.

목적:
    Streamlit 세션 진입 이전 (서비스 기동 전) 모든 사용자 DB의 스키마를 최신화.
    2026-08-22 WO-1 배포 후 51분 트레이딩 공백 사고 재발 방지.

동작:
    services/data/ 하위 tradebot_<user_id>.db 파일을 스캔하여
    각 user_id 에 대해 ensure_all_schemas(user_id) 실행.
    _safe_alter 의 멱등 특성으로 재실행 안전 (ALTER ADD 는 이미 있으면 skip).

사용:
    /root/upbit-tradebot-mvp/venv/bin/python3 /root/upbit-tradebot-mvp/scripts/migrate_all_users.py

exit code:
    0: 모든 사용자 마이그레이션 성공
    비정상 종료 시에도 서비스 기동은 유지 (systemd ExecStartPre 는 실패해도
    ExecStart 진행됨 — 기존 절차와 동일 fail-safe).
"""
import glob
import os
import re
import sys
import logging

# 프로젝트 루트를 sys.path 에 추가
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("migrate_all_users")


def _extract_user_id(db_filename: str) -> str | None:
    """tradebot_<user_id>.db 에서 user_id 추출. backup 접미사 등은 제외."""
    m = re.match(r"^tradebot_(.+)\.db$", db_filename)
    if not m:
        return None
    uid = m.group(1)
    # backup·임시 파일 제외
    if not uid or ".backup" in uid or ".tmp" in uid or uid.startswith("_"):
        return None
    return uid


def main() -> int:
    from services.init_db import get_db_path, ensure_all_schemas

    # DB 디렉토리 위치 파악
    _stub_path = get_db_path("_stub_")
    db_dir = os.path.dirname(_stub_path)
    logger.info(f"[MIGRATE-CLI] DB dir: {db_dir}")

    pattern = os.path.join(db_dir, "tradebot_*.db")
    files = sorted(glob.glob(pattern))
    logger.info(f"[MIGRATE-CLI] 발견 파일 {len(files)}개")

    ok, fail = 0, 0
    for path in files:
        fname = os.path.basename(path)
        uid = _extract_user_id(fname)
        if uid is None:
            logger.info(f"[MIGRATE-CLI] skip {fname} (user_id 추출 불가)")
            continue
        try:
            logger.info(f"[MIGRATE-CLI] ensure_all_schemas(user_id={uid!r}) 실행")
            ensure_all_schemas(uid)
            ok += 1
        except Exception as e:
            logger.error(f"[MIGRATE-CLI] ❌ 실패 user_id={uid!r}: {e}", exc_info=True)
            fail += 1

    logger.info(f"[MIGRATE-CLI] 완료 ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
