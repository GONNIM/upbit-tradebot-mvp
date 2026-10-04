"""
✅ WO-21 (2026-10-04): 재시작 때 trailing 상태(무장·최고가·고정폭·활성화 가격)를 봉 종가로 다시 계산한다.

배경: trailing 상태는 PositionState 메모리에만 있고, 재시작 복원(boot_seed / wallet_sync)은
apply_entry 로 초기화한다. 보유 중 재시작이면 수익이 익절 기준에 다시 닿을 때까지 trailing 매도가 없다.
처방 (나): 저장하지 않고, 마지막 BUY 뒤의 확정 봉 종가를 실시간 경로와 같은 함수로 재생한다.

규칙 (WO-21 구현 조건):
1. 시작점은 audit_trades 의 마지막 BUY(HTS_BUY_ADD 포함) 시각. 평균가는 지갑 동기화 값(position.avg_price).
   마지막 BUY 가 없으면 재계산하지 않고 초기 상태로 둔다.
2. 미확정(형성 중) 봉은 제외한다 (봉 시작 + 간격 > 지금 이면 제외, WO-16 (W) 규칙).
3. 워밍업 봉 안에 시작점이 있으면 추가 조회 없음. 밖이면 REST 로 더 받되 200봉 × 10회 한도.
   초과·실패 시 초기 상태로 두고 "[TRAILING-RESTORE] 재계산 불가 → 초기화 | 사유=…" WARNING 1줄.
4. 무장·최고가·고정폭은 TrailingStopFilter.advance_state 와 PositionState.update_highest_price 를 그대로 호출한다.
5. 결과는 "[TRAILING-RESTORE] armed=… peak=… fixed=… activation=… 기준 봉 n개 시작=…" 1줄.
7. PositionState 의 trailing 필드(highest_price, trailing_armed, trailing_fixed_amount,
   trailing_activation_price)만 바꾼다.

봉 선택: 실시간 경로에서 매수 뒤 첫 SELL 평가는 "봉 마감 시각(시작 + 간격) > 매수 시각" 인 첫 봉이다.
재생 순서: 봉마다 update_highest_price(종가) → advance_state(종가) (strategy_incremental 의 SELL 블록과 같은 순서).
근사(문서화): 재생은 손절 등 앞선 필터가 매도를 낸 봉도 trailing 상태를 전진시킨다. 실시간에서 그런 봉은
포지션이 청산되므로 지금도 보유 중인 포지션에서는 매도 거절 같은 드문 경우에만 차이가 난다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

MAX_REST_CALLS = 10
REST_BATCH = 200


def find_trailing_filter(strategy) -> Optional[Any]:
    """전략에 등록된 TrailingStopFilter 인스턴스 (없으면 None)."""
    mgr = getattr(strategy, "sell_filter_manager", None)
    for f in (getattr(mgr, "filters", None) or []):
        try:
            if f.get_name() == "TrailingStopFilter":
                return f
        except Exception:
            continue
    return None


def _to_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("Asia/Seoul")
    return t.tz_convert("UTC")


def reset_trailing(position) -> None:
    """apply_entry 직후와 같은 trailing 초기 상태 (highest=평균가, 미무장)."""
    position.highest_price = position.avg_price
    position.trailing_armed = False
    position.trailing_fixed_amount = None
    position.trailing_activation_price = None


def select_bars_after_buy(df: pd.DataFrame, buy_ts, interval_sec: int, now) -> List[Tuple[pd.Timestamp, float]]:
    """매수 뒤 SELL 평가 대상이었을 확정 봉 (시작 시각 UTC, 종가) 목록. 미확정 봉 제외."""
    if df is None or len(df) == 0:
        return []
    buy = _to_utc(buy_ts)
    now_utc = _to_utc(now)
    step = pd.Timedelta(seconds=int(interval_sec))
    out = []
    for ts, close in df["Close"].items():
        start = _to_utc(ts)
        end = start + step
        if end > buy and end <= now_utc:
            out.append((start, float(close)))
    out.sort(key=lambda x: x[0])
    return out


def replay_trailing(position, ts_filter, closes: List[Tuple[Any, float]], min_holding_period: int = 1) -> int:
    """
    초기 상태에서 종가를 하나씩 재생. 실시간 SELL 블록과 같은 함수·순서.
    min_holding_period: 실시간에서 bars_held < min 인 첫 봉들은 필터 전에 HOLD 로 끝나므로 같은 수만큼 건너뜀.
    반환: 재생한 봉 수
    """
    reset_trailing(position)
    skip = max(0, int(min_holding_period or 0) - 1)
    n = 0
    for i, (_, close) in enumerate(closes):
        if i < skip:
            continue
        position.update_highest_price(close)          # strategy_incremental SELL 블록과 같은 호출
        ts_filter.advance_state(position, close, log=False)  # TrailingStopFilter STEP 1·2
        n += 1
    return n


def _fail(position, reason: str) -> Dict[str, Any]:
    reset_trailing(position)
    logger.warning(f"[TRAILING-RESTORE] 재계산 불가 → 초기화 | 사유={reason}")
    return {"status": "reset", "reason": reason}


def restore_trailing_on_boot(
    position,
    strategy,
    *,
    user_id: str,
    ticker: str,
    timeframe: str,
    interval_sec: int,
    warmup_df: Optional[pd.DataFrame],
    now=None,
    last_buy: Optional[Dict[str, Any]] = None,
    fetch: Optional[Callable[..., Optional[pd.DataFrame]]] = None,
    max_calls: int = MAX_REST_CALLS,
) -> Dict[str, Any]:
    """
    재시작 복원(boot_seed / wallet_sync) 뒤, 첫 매도 평가 전에 1회 호출.
    반환: {"status": "restored"|"reset"|"skip", ...}
    """
    if not getattr(position, "has_position", False):
        return {"status": "skip", "reason": "no_position"}

    ts_filter = find_trailing_filter(strategy)
    if ts_filter is None:
        return _fail(position, "trailing 필터 없음")
    if hasattr(ts_filter, "is_enabled") and not ts_filter.is_enabled():
        reset_trailing(position)
        logger.info("[TRAILING-RESTORE] 건너뜀 | 사유=trailing 필터 꺼짐")
        return {"status": "skip", "reason": "filter_disabled"}
    if position.avg_price is None or position.avg_price <= 0:
        return _fail(position, "평균가 없음")

    if last_buy is None:
        from services.db import get_last_open_buy_trade
        last_buy = get_last_open_buy_trade(user_id, ticker)
    if not last_buy or not last_buy.get("timestamp"):
        return _fail(position, "마지막 BUY 없음")

    try:
        buy_utc = _to_utc(last_buy["timestamp"])
    except Exception as e:
        return _fail(position, f"마지막 BUY 시각 해석 실패 ({e})")
    now_utc = _to_utc(now if now is not None else datetime.now(timezone.utc))
    step = pd.Timedelta(seconds=int(interval_sec))
    needed_start = buy_utc.floor(f"{int(interval_sec)}s")  # 매수 시각을 포함하는 봉 (마감 > 매수 시각인 첫 봉)

    df = warmup_df if warmup_df is not None else pd.DataFrame(columns=["Close"])
    extra = 0
    if len(df) == 0 or _to_utc(df.index[0]) > needed_start:
        first_start = _to_utc(df.index[0]) if len(df) else now_utc.floor(f"{int(interval_sec)}s")
        slots = int((first_start - needed_start) / step)
        if slots > max_calls * REST_BATCH:
            return _fail(position, f"조회 한도 초과 (필요 {slots}봉 > {max_calls}회×{REST_BATCH}봉)")
        if fetch is None:
            from core.rest_reconcile import safe_fetch_rest as fetch
        try:
            older = fetch(market=ticker, timeframe=timeframe,
                          end_ts=(first_start - step).to_pydatetime(), total_count=max(slots, 1))
        except Exception as e:
            older = None
            logger.debug(f"[TRAILING-RESTORE] 추가 조회 예외: {e}")
        if older is None or len(older) == 0:
            return _fail(position, f"REST 조회 실패 (필요 {slots}봉)")
        extra = len(older)
        df = pd.concat([older[["Close"]], df[["Close"]]]) if len(df) else older[["Close"]]
        df = df[~df.index.duplicated(keep="last")].sort_index()

    closes = select_bars_after_buy(df, buy_utc, interval_sec, now_utc)
    try:
        n = replay_trailing(position, ts_filter, closes, getattr(strategy, "min_holding_period", 1))
    except Exception as e:
        return _fail(position, f"재생 실패 ({e})")

    def _f(v):
        return "None" if v is None else f"{float(v):.4f}"

    logger.info(
        f"[TRAILING-RESTORE] armed={position.trailing_armed} peak={_f(position.highest_price)} "
        f"fixed={_f(position.trailing_fixed_amount)} activation={_f(position.trailing_activation_price)} "
        f"기준 봉 {n}개 시작={last_buy['timestamp']} (사유={last_buy.get('reason')}, 평균가={position.avg_price}, "
        f"추가 조회 {extra}봉)"
    )
    return {"status": "restored", "armed": position.trailing_armed, "peak": position.highest_price,
            "fixed": position.trailing_fixed_amount, "activation": position.trailing_activation_price,
            "bars": n, "extra": extra, "start": last_buy["timestamp"]}
