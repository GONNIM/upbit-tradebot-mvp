"""WO-6 병행 검증용 dry-run 실행 스크립트.

사용법:
    python -m scripts.live_dry_run --ticker KRW-JTO --strategy EMA \\
        --user-id mcmax33_dry --source-user mcmax33

동작:
    - UpbitTrader 를 dry_run=True 로 초기화하여 실 주문을 억제한다.
    - 매매 판단 로직, 지표 계산, 감사 로그는 정상 실행된다.
    - 감사 데이터베이스는 --user-id 로 서버 운영 계정과 분리한다.
    - params JSON 은 --source-user 의 파일(<source>_latest_params_<STRATEGY>.json)
      을 재사용한다. --ticker 로 대상 종목을 override 할 수 있다.
    - 서버 실행 봇과 나란히 실행하여 [CLOCK-CLOSE], [CONFIRMED], 매매 판단
      로그를 시각별로 비교한다.

주의:
    - 이 스크립트는 서버 운영 봇을 대체하지 않는다. 로컬에서만 사용한다.
    - 반드시 서버 운영 계정과 다른 user_id 로 실행해야 감사 로그 충돌을 피한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import shutil
import sys
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_params_json(source_user: str, strategy: str) -> dict:
    """{source_user}_latest_params_{STRATEGY}.json 을 dict 로 로드."""
    fname = f"{source_user}_latest_params_{strategy}.json"
    if not os.path.exists(fname):
        raise SystemExit(
            f"params 파일 없음: {fname}\n"
            f"서버 params 파일을 로컬로 복사한 후 재실행하세요."
        )
    with open(fname, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dry_schema(user_id: str) -> None:
    """dry 계정의 감사 DB 스키마를 초기화한다. 다른 계정 DB 는 건드리지 않는다.

    services.init_db.ensure_all_schemas 는 user_id 별 DB 파일을 생성하고
    필요한 테이블을 모두 마이그레이션한다.
    """
    from services.init_db import ensure_all_schemas

    logger.info(f"[DRY-RUN] 스키마 초기화 시작 | user_id={user_id}")
    ensure_all_schemas(user_id)
    logger.info(f"[DRY-RUN] 스키마 초기화 완료 | user_id={user_id}")


def _ensure_dry_conditions_file(source_user: str, dry_user: str, strategy: str) -> None:
    """원본 계정의 조건 파일을 dry 계정 이름으로 복사한다.

    이미 dry 계정 파일이 있으면 덮어쓰지 않고 그대로 사용한다.
    복사 여부와 사용 여부를 로그로 남긴다.
    """
    src = f"{source_user}_{strategy}_buy_sell_conditions.json"
    dst = f"{dry_user}_{strategy}_buy_sell_conditions.json"

    if os.path.exists(dst):
        logger.info(f"[DRY-RUN] 조건 파일 기존 사용 | dst={dst} (덮어쓰지 않음)")
        return

    if not os.path.exists(src):
        logger.warning(
            f"[DRY-RUN] 조건 파일 원본 없음 | src={src} — 조건 로딩 실패 가능. "
            f"서버의 원본 조건 파일을 로컬로 복사한 후 재실행하세요."
        )
        return

    shutil.copy2(src, dst)
    logger.info(f"[DRY-RUN] 조건 파일 복사 | src={src} → dst={dst}")


def _ensure_dry_params_file(source_user: str, dry_user: str, strategy: str) -> None:
    """✅ WO-6 (2026-08-26): 원본 계정의 전략 파라미터 파일을 dry 계정 이름으로 복사.

    조건 파일과 동일하게 이미 dry 계정 파일이 있으면 덮어쓰지 않는다.
    복사 여부와 사용 여부를 로그로 남긴다. 파라미터 불일치로 EMA 대조가
    무효화되는 사고(2026-08-26) 재발 방지.
    """
    src = f"{source_user}_latest_params_{strategy}.json"
    dst = f"{dry_user}_latest_params_{strategy}.json"

    if os.path.exists(dst):
        logger.info(f"[DRY-RUN] 전략 파라미터 파일 기존 사용 | dst={dst} (덮어쓰지 않음)")
        return

    if not os.path.exists(src):
        logger.warning(
            f"[DRY-RUN] 전략 파라미터 파일 원본 없음 | src={src} — LiveParams 로딩 실패."
        )
        return

    shutil.copy2(src, dst)
    logger.info(f"[DRY-RUN] 전략 파라미터 파일 복사 | src={src} → dst={dst}")


def main() -> int:
    parser = argparse.ArgumentParser(description="WO-6 dry-run live loop")
    parser.add_argument("--ticker", required=True, help="예: KRW-JTO (또는 JTO)")
    parser.add_argument("--strategy", required=True, choices=["EMA", "MACD"], help="전략 타입")
    parser.add_argument("--user-id", required=True, help="감사 DB 격리용 user_id (운영 계정과 달라야 함)")
    parser.add_argument("--source-user", default=None, help="params JSON 원본 계정 (미지정 시 user-id에서 _dry 제거)")
    parser.add_argument("--interval", default="minute1", help="기본 minute1")
    args = parser.parse_args()

    if not args.user_id.endswith("_dry"):
        logger.warning(
            f"[DRY-RUN] user_id 가 '{args.user_id}' 입니다. 감사 DB 충돌을 피하려면 '_dry' 접미사 사용 권장."
        )

    # ✅ WO-6 보완 F2 (2026-08-26): notifier 실 발송 억제 (운영 채널 소음 방지).
    os.environ["WO6_DRY_RUN"] = "1"
    logger.info("[DRY-RUN] WO6_DRY_RUN=1 세팅 — notifier 실 발송 억제")

    source_user = args.source_user or args.user_id.replace("_dry", "")
    logger.info(
        f"[DRY-RUN] 시작 | ticker={args.ticker} strategy={args.strategy} "
        f"user_id={args.user_id} source_user={source_user} interval={args.interval}"
    )

    # ✅ 사전 준비: 스키마 초기화 + 조건 파일 복사 + 전략 파라미터 파일 복사
    _ensure_dry_schema(args.user_id)
    _ensure_dry_conditions_file(source_user, args.user_id, args.strategy)
    _ensure_dry_params_file(source_user, args.user_id, args.strategy)

    # 지연 import: 실행 시점에만 무거운 의존성 로드
    from core.trader import UpbitTrader
    from engine.live_loop import run_live_loop
    from engine.params import LiveParams

    # ✅ WO-6 (2026-08-26): dry 계정 전용 params 파일에서 로드 (원본에서 복사됨).
    # 서버 원본 파라미터와 완전 일치 확인용.
    params_data = _load_params_json(args.user_id, args.strategy)
    # ticker 는 심볼(JTO) 또는 KRW-JTO 모두 허용. 내부 로직에서 정규화.
    ticker_raw = args.ticker.upper()
    ticker_symbol = ticker_raw.replace("KRW-", "")
    params_data["ticker"] = ticker_symbol
    params_data["interval"] = args.interval

    params = LiveParams(**params_data)
    logger.info(
        f"[DRY-RUN] LiveParams 로드 | ticker={params.ticker} interval={params.interval} "
        f"fast_period={params.fast_period} slow_period={params.slow_period} "
        f"use_separate_ema={getattr(params, 'use_separate_ema', None)} "
        f"fast_buy={getattr(params, 'fast_buy', None)} slow_buy={getattr(params, 'slow_buy', None)} "
        f"order_ratio={params.order_ratio}"
    )

    # ✅ WO-6 (2026-08-26): dry 계정 params 파일 경로 (원본이 아니라 dry 파일 사용)
    params_file_path = f"{args.user_id}_latest_params_{args.strategy}.json"
    trader = UpbitTrader(
        user_id=args.user_id,
        risk_pct=params.order_ratio,
        test_mode=False,               # LIVE 코드 경로 그대로 사용
        strategy_type=args.strategy,
        params_file=params_file_path,  # RATIO-HR 지원
        dry_run=True,                  # 실 주문만 억제
    )

    q: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    logger.info("[DRY-RUN] run_live_loop 호출 (Ctrl+C 로 중단)")
    try:
        run_live_loop(
            params=params,
            q=q,
            trader=trader,
            stop_event=stop_event,
            test_mode=False,
            user_id=args.user_id,
        )
    except KeyboardInterrupt:
        logger.info("[DRY-RUN] KeyboardInterrupt — stop_event set")
        stop_event.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
