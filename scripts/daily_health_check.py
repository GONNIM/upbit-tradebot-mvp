"""일일 자동 점검 스크립트.

전일 24시간 구간의 다음 항목을 집계한다.
  (a) 빠진 봉 수와 시각 규칙성 (Upbit 원본에 있으나 감사에 없는 봉).
  (b) 봉당 판단 위반 수 (audit_buy_eval / audit_sell_eval 봉당 2건 이상).
  (c) 옵션 C 발동 수와 잠정·확정 편차 (checks JSON via_tentative=True 인 감사 행).
  (d) 오류 로그 수 (journalctl 의 Traceback / CRITICAL / POLLUTED).

이상이 있을 때만 services.notifier 로 요약 알림을 전송한다. 전부 정상이면
로그 한 줄만 남기고 조용히 종료한다.

사용법:
    python3 -m scripts.daily_health_check --user-id mcmax33 --ticker KRW-JTO \
        [--date 2026-09-03]   # 미지정 시 어제 날짜

주의:
    - 이 스크립트는 서버에서 실행하도록 설계됐다. 감사 DB 는
      services/data/tradebot_<user_id>.db 를 읽기 전용으로 연다.
    - Upbit 조회는 pyupbit.get_ohlcv 이며 interval 은 audit 의
      interval_sec 우세값으로 자동 결정한다 (60→minute1, 300→minute5).
    - 오류 로그는 서버 로컬에서 journalctl 명령을 실행해야 정확하다.
      원격 SSH 로도 실행 가능하나 이 스크립트는 로컬 실행을 전제한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# 프로젝트 루트 임포트 경로 확보
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_health_check")

KST = ZoneInfo("Asia/Seoul")


def _resolve_target_date(arg_date: str | None) -> date:
    """--date 미지정 시 어제 KST 기준."""
    if arg_date:
        return date.fromisoformat(arg_date)
    return (datetime.now(KST) - timedelta(days=1)).date()


def _kst_bounds(day: date) -> tuple[str, str]:
    """구간 [00:00:00, 23:59:00] KST ISO 문자열 반환."""
    start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=KST)
    end = datetime(day.year, day.month, day.day, 23, 59, 0, tzinfo=KST)
    return start.isoformat(), end.isoformat()


def _db_path(user_id: str) -> Path:
    return Path(__file__).resolve().parent.parent / "services" / "data" / f"tradebot_{user_id}.db"


def _open_db(user_id: str) -> sqlite3.Connection:
    p = _db_path(user_id)
    if not p.exists():
        raise SystemExit(f"감사 DB 없음: {p}")
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def _dominant_interval_sec(conn: sqlite3.Connection, ticker: str,
                           start: str, end: str) -> int | None:
    """audit_buy_eval 의 다수 interval_sec 반환. 없으면 None."""
    cur = conn.cursor()
    cur.execute(
        "SELECT interval_sec, COUNT(*) FROM audit_buy_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ? "
        "GROUP BY interval_sec ORDER BY 2 DESC LIMIT 1",
        (ticker, start, end),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _audit_union_bars(conn: sqlite3.Connection, ticker: str,
                      start: str, end: str, interval_sec: int) -> set[datetime]:
    """audit_buy_eval + audit_sell_eval 합집합 (WARMUP 제외, interval_sec 일치)."""
    cur = conn.cursor()
    q = (
        "SELECT DISTINCT bar_time FROM audit_buy_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ? AND price IS NOT NULL "
        "AND interval_sec=? AND (notes IS NULL OR notes NOT LIKE '%WARMUP%') "
        "UNION "
        "SELECT DISTINCT bar_time FROM audit_sell_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ? AND price IS NOT NULL "
        "AND interval_sec=?"
    )
    cur.execute(q, (ticker, start, end, interval_sec, ticker, start, end, interval_sec))
    return {datetime.fromisoformat(r[0]) for r in cur.fetchall()}


def _per_bar_violations(conn: sqlite3.Connection, ticker: str,
                        start: str, end: str) -> tuple[int, int]:
    """봉당 2건 이상 위반 (buy, sell) 수."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM (SELECT bar_time FROM audit_buy_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ? "
        "GROUP BY bar_time HAVING COUNT(*) > 1)",
        (ticker, start, end),
    )
    v_buy = int(cur.fetchone()[0])
    cur.execute(
        "SELECT COUNT(*) FROM (SELECT bar_time FROM audit_sell_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ? "
        "GROUP BY bar_time HAVING COUNT(*) > 1)",
        (ticker, start, end),
    )
    v_sell = int(cur.fetchone()[0])
    return v_buy, v_sell


def _option_c_events(conn: sqlite3.Connection, ticker: str,
                     start: str, end: str) -> tuple[int, list[tuple[float, float]]]:
    """옵션 C via_tentative=True 감사 행 수와 (잠정, 확정) 편차 목록.

    checks JSON 에 via_tentative=True 인 audit_buy_eval 행을 카운트하고,
    tentative_close 와 confirmed_close 가 모두 있는 행의 편차를 반환한다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT checks, tentative_close, confirmed_close FROM audit_buy_eval "
        "WHERE ticker=? AND bar_time >= ? AND bar_time <= ?",
        (ticker, start, end),
    )
    total = 0
    diffs: list[tuple[float, float]] = []
    for checks_str, tc, cc in cur.fetchall():
        if not checks_str:
            continue
        try:
            checks = json.loads(checks_str)
        except Exception:
            continue
        if checks.get("via_tentative"):
            total += 1
            if tc is not None and cc is not None:
                diffs.append((float(tc), float(cc)))
    return total, diffs


def _fetch_upbit_bars(ticker: str, interval: str, start_kst: datetime,
                      end_kst: datetime) -> set[datetime]:
    """pyupbit 로 구간 거래 봉 조회. UTC to 파라미터 사용."""
    import pyupbit  # 지연 임포트
    frames = []
    cursor_kst = end_kst + timedelta(minutes=(1 if interval == "minute1" else 5))
    for _ in range(30):
        to_utc = cursor_kst.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
        df = None
        for _a in range(3):
            df = pyupbit.get_ohlcv(ticker, interval=interval, count=200, to=to_utc)
            if df is not None and not df.empty:
                break
            time.sleep(1.0)
        if df is None or df.empty:
            break
        import pandas as pd
        df.index = pd.to_datetime(df.index).tz_localize(KST) if df.index.tz is None else df.index.tz_convert(KST)
        frames.append(df)
        if df.index.min() < start_kst:
            break
        cursor_kst = df.index.min()
        time.sleep(0.25)
    if not frames:
        return set()
    import pandas as pd
    full = pd.concat(frames).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    mask = (full.index >= start_kst) & (full.index <= end_kst)
    return set(full[mask].index.to_pydatetime())


def _journalctl_error_counts(target_day: date) -> dict[str, int]:
    """서버 로컬 실행 전제. journalctl 로 하루 오류 시그니처 카운트."""
    since = f"{target_day.isoformat()} 00:00:00"
    until = f"{target_day.isoformat()} 23:59:59"
    counts: dict[str, int] = {}
    for kw in ("Traceback", "CRITICAL", "POLLUTED"):
        try:
            r = subprocess.run(
                ["bash", "-c",
                 f"journalctl -u tradebot --since '{since}' --until '{until}' --no-pager | grep -c {kw}"],
                capture_output=True, text=True, timeout=60,
            )
            counts[kw] = int(r.stdout.strip() or 0)
        except Exception as e:
            logger.warning(f"journalctl {kw} 조회 예외: {e}")
            counts[kw] = -1
    return counts


def _notify_if_abnormal(user_id: str, target_day: date, summary: dict) -> None:
    """이상이 하나라도 있으면 notifier 로 발송. 정상이면 조용히 지나감."""
    missing = int(summary.get("missing_bars", 0))
    violations = int(summary.get("violations_buy", 0)) + int(summary.get("violations_sell", 0))
    errors = sum(v for v in summary.get("errors", {}).values() if v > 0)
    abnormal = missing > 0 or violations > 0 or errors > 0

    if not abnormal:
        logger.info(f"[DAILY-HEALTH] {target_day} 정상 · 알림 없음")
        return

    try:
        from services.notifier import send as _notify, LEVEL_WARNING
        body_lines = [
            f"대상일: {target_day.isoformat()} (KST)",
            f"빠진 봉: {missing}",
            f"봉당 판단 위반 (buy/sell): {summary.get('violations_buy', 0)} / {summary.get('violations_sell', 0)}",
            f"옵션 C 발동: {summary.get('option_c_events', 0)}",
            f"오류 로그 (Traceback/CRITICAL/POLLUTED): "
            f"{summary.get('errors', {}).get('Traceback', 0)} / "
            f"{summary.get('errors', {}).get('CRITICAL', 0)} / "
            f"{summary.get('errors', {}).get('POLLUTED', 0)}",
        ]
        _notify(
            LEVEL_WARNING,
            f"⚠️ 일일 자동 점검 이상 감지 — {user_id}",
            "\n".join(body_lines),
            dedupe_key=f"daily_health:{target_day.isoformat()}",
            dedupe_ttl=86400,
        )
        logger.warning(f"[DAILY-HEALTH] {target_day} 이상 감지 · notifier 발송 완료")
    except Exception as e:
        logger.error(f"[DAILY-HEALTH] notifier 발송 실패: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="일일 자동 점검")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (미지정 시 어제 KST)")
    parser.add_argument("--skip-errors", action="store_true",
                        help="journalctl 접근 불가 환경에서 오류 카운트 스킵")
    args = parser.parse_args()

    target_day = _resolve_target_date(args.date)
    start_iso, end_iso = _kst_bounds(target_day)
    logger.info(f"[DAILY-HEALTH] 대상 {target_day} 구간 [{start_iso}, {end_iso}]")

    conn = _open_db(args.user_id)
    interval_sec = _dominant_interval_sec(conn, args.ticker, start_iso, end_iso)
    if interval_sec not in (60, 300):
        logger.warning(f"interval_sec 판별 실패({interval_sec}) · 분모 계산 스킵")
        summary: dict = {"missing_bars": 0}
    else:
        interval_str = "minute1" if interval_sec == 60 else "minute5"
        audit_union = _audit_union_bars(conn, args.ticker, start_iso, end_iso, interval_sec)
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
        upbit_bars = _fetch_upbit_bars(args.ticker, interval_str, start_dt, end_dt)
        missing = sorted(upbit_bars - audit_union)
        summary = {"missing_bars": len(missing), "interval_sec": interval_sec}
        if missing:
            hours = Counter(b.astimezone(KST).strftime("%H") for b in missing)
            summary["missing_hour_dist"] = dict(hours)

    v_buy, v_sell = _per_bar_violations(conn, args.ticker, start_iso, end_iso)
    summary["violations_buy"] = v_buy
    summary["violations_sell"] = v_sell

    opt_c_count, opt_c_diffs = _option_c_events(conn, args.ticker, start_iso, end_iso)
    summary["option_c_events"] = opt_c_count
    if opt_c_diffs:
        abs_diffs = [abs(cc - tc) for tc, cc in opt_c_diffs]
        summary["option_c_diff_max"] = max(abs_diffs)
        summary["option_c_diff_avg"] = sum(abs_diffs) / len(abs_diffs)

    if args.skip_errors:
        summary["errors"] = {"Traceback": -1, "CRITICAL": -1, "POLLUTED": -1}
    else:
        summary["errors"] = _journalctl_error_counts(target_day)

    conn.close()
    logger.info(f"[DAILY-HEALTH] 요약: {summary}")
    _notify_if_abnormal(args.user_id, target_day, summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
