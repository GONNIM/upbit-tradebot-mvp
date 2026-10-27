"""
라이브 트레이딩 루프 - 증분 처리 기반 (Backtest 제거)
"""
import threading
import queue
import logging
import os
import sys
import time
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
# ✅ WO-2 옵션 C (2026-09-02): 모듈 스코프 datetime/timedelta/ZoneInfo — 회귀 patch 대응
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 새로운 증분 처리 모듈
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_incremental import IncrementalMACDStrategy, IncrementalEMAStrategy
from core.strategy_engine import StrategyEngine

# 🚀 REST Reconcile 모듈
from core.candle_clock import CandleClock
from core.rest_reconcile import safe_fetch_rest, reconcile_series, fetch_confirmed_candle, verify_past_candles_with_upbit, NO_TRADE
from core.time_utils import now_utc, format_kst, floor_to_interval
from core.candle_validator import CandleValidator

# 기존 모듈
from core.data_feed import stream_candles, fill_gaps_sync, JITTER_BY_INTERVAL
from core.trader import UpbitTrader
from engine.params import LiveParams
from services.db import (
    get_last_open_buy_order,
    insert_buy_eval,
    insert_sell_eval,
    insert_settings_snapshot,
    now_kst_minute,
)
from config import (
    TP_WITH_TS,
    CONDITIONS_JSON_FILENAME,
    DEFAULT_STRATEGY_TYPE,
    ENGINE_EXEC_MODE,
    TRAILING_STOP_PERCENT,
    # 🚀 REST Reconcile 설정
    RUN_MODE,
    CANDLE_TRUTH,
    WS_ROLE,
    RECONCILE_ON_EVERY_CLOSE,
    RECONCILE_LOOKBACK_BARS,
    ALLOW_SYNTHETIC_BARS,
)
from utils.logging_util import log_to_file

from engine.reconciler_singleton import get_reconciler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 히스토리 길이 설정 (MACD/EMA 안정화용)
# ============================================================

WARMUP_LEN_BY_INTERVAL_MACD: Dict[str, int] = {
    "minute1": 600,
    "minute3": 600,
    "minute5": 500,
    "minute10": 400,
    "minute15": 300,
    "minute30": 300,
    "minute60": 300,
    "day": 200,
}

WARMUP_LEN_BY_INTERVAL_EMA: Dict[str, int] = {
    "minute1": 200,
    "minute3": 200,
    "minute5": 200,
    "minute10": 200,
    "minute15": 200,
    "minute30": 200,
    "minute60": 200,
    "day": 200,
}


def _lookup_tentative_close(
    ticker: str,
    local_series: 'pd.DataFrame',
    closed_ts,
    max_ws_age_sec: int = 10,
) -> Optional[Tuple[float, str, 'pd.Timestamp']]:
    """
    WO-2 옵션 C: 잠정 종가 우선순위 조회.

    우선순위:
      1) `pyupbit.get_current_price(verbose=True)` 응답의 `trade_timestamp`.
         체결 시각이 대상 봉 구간 `[closed_ts, closed_ts+1min)` 안이거나
         봉 마감 후 `max_ws_age_sec` 초 이내일 때만 채택.
      2) `local_series` 의 직전 봉 close (인덱스 순회 fallback).
      3) 실패 시 None.

    반환: `(close, source, source_ts_kst)` 또는 `None`.
    source: `'WS_FRESH'` | `'PREV_CLOSE'`.
    """
    KST = ZoneInfo("Asia/Seoul")
    now = datetime.now(KST)

    # closed_ts 정규화
    if hasattr(closed_ts, 'tzinfo') and closed_ts.tzinfo is not None:
        closed_ts_kst = closed_ts.astimezone(KST)
    else:
        closed_ts_kst = pd.Timestamp(closed_ts).tz_localize(KST)

    # 1순위: pyupbit ticker (신선도 조건)
    try:
        import pyupbit
        r = pyupbit.get_current_price(ticker, verbose=True)
        if isinstance(r, list) and r:
            r = r[0]
        if isinstance(r, dict):
            trade_ts_ms = r.get('trade_timestamp')
            trade_price = r.get('trade_price')
            if trade_ts_ms is not None and trade_price is not None:
                trade_ts_kst = pd.Timestamp(trade_ts_ms, unit='ms', tz='UTC').tz_convert(KST)
                bar_end = closed_ts_kst + timedelta(minutes=1)
                age_from_close = (now - closed_ts_kst).total_seconds()
                in_bar_window = closed_ts_kst <= trade_ts_kst < bar_end
                within_grace = 0 <= age_from_close <= max_ws_age_sec
                if in_bar_window or within_grace:
                    logger.info(
                        f"[WO2-C-TENTATIVE-SOURCE] ts={format_kst(closed_ts)} "
                        f"close={float(trade_price)} source=WS_FRESH "
                        f"trade_ts={trade_ts_kst.isoformat()} "
                        f"(in_window={in_bar_window}, age_from_close={age_from_close:.0f}s)"
                    )
                    return float(trade_price), 'WS_FRESH', trade_ts_kst
                else:
                    logger.info(
                        f"[WO2-C-TENTATIVE-SOURCE] WS 스킵 (신선도 조건 불충족) | "
                        f"trade_ts={trade_ts_kst.isoformat()} closed_ts={closed_ts_kst.isoformat()} "
                        f"age_from_close={age_from_close:.0f}s > {max_ws_age_sec}s"
                    )
    except Exception as _e:
        logger.warning(f"[WO2-C-TENTATIVE-SOURCE] WS 조회 예외 무시: {_e}")

    # 2순위: local_series 직전 봉 close
    try:
        for offset in range(1, 5):
            candidate = closed_ts_kst - timedelta(minutes=offset)
            for idx in local_series.index:
                idx_ts = pd.Timestamp(idx)
                if idx_ts.tzinfo is None:
                    idx_kst = idx_ts.tz_localize(KST)
                else:
                    idx_kst = idx_ts.tz_convert(KST)
                if idx_kst == candidate:
                    close_val = float(local_series.loc[idx, 'Close'])
                    logger.info(
                        f"[WO2-C-TENTATIVE-SOURCE] ts={format_kst(closed_ts)} "
                        f"close={close_val} source=PREV_CLOSE prev_ts={candidate.isoformat()}"
                    )
                    return close_val, 'PREV_CLOSE', candidate
    except Exception as _e:
        logger.warning(f"[WO2-C-TENTATIVE-SOURCE] PREV_CLOSE 조회 예외 무시: {_e}")

    logger.error(
        f"[WO2-C-TENTATIVE-SOURCE] ts={format_kst(closed_ts)} source=NONE — 잠정 종가 확보 실패"
    )
    return None


def _warmup_trim_forming(initial_df: pd.DataFrame, interval_sec: int, now: datetime, min_hist: int):
    """
    ✅ WO-16 (W) (2026-10-01): 워밍업 마지막 봉이 형성 중(마지막 봉 시각 + 봉 간격 > 지금)이면 제거.
    기존에는 "받은 봉 수 > min_hist" 일 때만 제거했는데, REST to 결함으로 늘 200(=min_hist)만 받아
    형성 중 봉이 지표 시드에 들어갔다(WO-15: 13회 중 7회). 확정 봉은 버리지 않는다.
    안전장치(F2): 제거하면 min_hist 미만이 될 때는 제거하지 않는다(WO-16 (R) 없이도 기동 오류 없음).
    반환: (df, action, 마지막 봉 시각, 봉 시작 뒤 경과 초)
      action = "dropped" | "kept_confirmed" | "kept_insufficient"
    """
    last_ts = initial_df.index[-1]
    elapsed = int((pd.Timestamp(now) - pd.Timestamp(last_ts)).total_seconds())
    if elapsed >= interval_sec:
        return initial_df, "kept_confirmed", last_ts, elapsed
    if len(initial_df) - 1 >= min_hist:
        return initial_df.iloc[:-1], "dropped", last_ts, elapsed
    return initial_df, "kept_insufficient", last_ts, elapsed


LONG_SEED_BARS = 800  # ✅ WO-17 (S) G3: 긴 이력 시드 봉 수 (EMA200 잔차 약 0.25%, G4 측정상 장기 기준과 0.02원 이내)


def _seed_warmup_indicators(indicators, initial_df: pd.DataFrame, long_bars: int, min_hist: int):
    """
    ✅ WO-17 (S) (2026-10-01): 워밍업 지표 시드 방식 선택.
    - 확정 봉이 long_bars 이상이면 최근 long_bars 봉으로 긴 이력 증분 시드(첫 min_hist 봉 SMA → 나머지 증분).
    - 부족하면 현행 200봉 SMA 시드(seed_from_closes — 각 EMA 는 마지막 p개 SMA 이므로 받은 봉 전체를 넘겨도 같음).
    버퍼·local_series 용 df 는 최근 min_hist 봉만 (WO-14 (b) 로컬 시작 기준 연동).
    단, 폴백이면서 받은 봉이 min_hist + 1 이하이면 받은 그대로(현행 동작과 완전 동일).
    반환: (ok, mode, reason, df_for_buffer)  mode = "long_history" | "sma200"
    """
    closes = initial_df["Close"].tolist()
    if len(closes) >= long_bars:
        # ✅ WO-26: 봉 시각도 넘겨 재생 중 마지막 D/C 시각을 찾는다 (폴백 시드는 None = 직전 D/C 모름)
        if indicators.seed_long_history(closes[-long_bars:], base_len=min_hist,
                                        timestamps=list(initial_df.index[-long_bars:])):
            return True, "long_history", "", initial_df.iloc[-min_hist:]
        reason = "long_seed_failed"
    else:
        reason = f"insufficient_bars({len(closes)}<{long_bars})"
    ok = indicators.seed_from_closes(closes)
    df_buf = initial_df if len(initial_df) <= min_hist + 1 else initial_df.iloc[-min_hist:]
    return ok, "sma200", reason, df_buf


# ============================================================
# 2차 T3: PULLBACK 전용 워밍업·BACKFILL 도우미 (EMA·MACD 경로는 부르지 않는다)
# ============================================================
PULLBACK_BUFFER_BARS = 500  # CandleBuffer(maxlen=500) 과 같은 값 — 버퍼·local_series 에 넘기는 봉 수


def _pullback_warmup_bars(pullback_cfg: dict) -> Tuple[int, int]:
    """PULLBACK 워밍업 (min_hist, _long_bars). min_hist = required_bars, _long_bars = max(LONG_SEED_BARS, required+1) (D8).
    run_live_loop 의 `warmup_request` 식은 그대로라 1회째 _long_bars+1, 재시도 required_bars+1 을 요청한다(F5)."""
    from engine.pullback_params import required_bars
    rb = int(required_bars(pullback_cfg))
    return rb, max(LONG_SEED_BARS, rb + 1)


def _pullback_warmup_check(received: int, required: int, *, holding: bool, user_id: str, ticker: str,
                           notify=None) -> bool:
    """받은 봉 < required_bars 이면 PULLBACK 기동 거부 + CRITICAL. 200봉 SMA 폴백은 쓰지 않는다."""
    if received >= required:
        return True
    logger.error(f"[PULLBACK-WARMUP] 봉 부족 → 기동 거부 | received={received} required={required} holding={holding}")
    title = f"🚨 새 전략 워밍업 봉 부족 (받은 {received} / 필요 {required}) — {ticker}"
    if holding:
        body = ("보유 중 새 전략 워밍업 봉이 부족해 기동하지 않았습니다 — 운영자 확인 필요.\n"
                "운영자 절차: 수동 청산 또는 활성 전략 파일을 직전 전략으로 되돌리기(배포 절 되돌리기 ①).")
    else:
        body = "새 전략 워밍업 봉이 부족해 기동하지 않았습니다. 업비트 응답·네트워크를 확인한 뒤 다시 시작해 주세요."
    try:
        if notify is None:
            from services.notifier import send as notify  # noqa: F811
        notify("CRITICAL", title, body, dedupe_key=f"pullback_warmup_short:{user_id}:{ticker}", dedupe_ttl=3600)
    except Exception as e:
        logger.warning(f"[PULLBACK-WARMUP] 알림 실패 | {type(e).__name__}")
    return False


def _pullback_holding(position, boot_seed_recover_qty) -> bool:
    """워밍업 시점 보유 판정. sync_from_wallet()(run_live_loop 앞부분) 뒤의 has_position 에 더해,
    봇 주문 기준 진입가가 없어 has_position 을 False 로 되돌리고 워밍업 뒤 지갑 기준 복원을 기다리는
    경우(boot_seed_recover_qty > 0, WO-12 C7)도 보유로 본다."""
    if bool(getattr(position, "has_position", False)):
        return True
    try:
        return boot_seed_recover_qty is not None and float(boot_seed_recover_qty) > 0
    except (TypeError, ValueError):
        return False


def _pullback_warmup_gate(initial_df: pd.DataFrame, wu_action: str, required: int, *, holding: bool,
                          user_id: str, ticker: str, notify=None) -> Optional[pd.DataFrame]:
    """PULLBACK 워밍업 관문(Issue #8): `_warmup_trim_forming` 이 봉 수 부족으로 형성 중 봉을 남겼으면
    (kept_insufficient) 늘 빼고 개수를 다시 본다. 모자라면 CRITICAL 뒤 None(기동 거부). EMA·MACD 는 부르지 않는다."""
    if wu_action == "kept_insufficient":
        logger.warning(f"[PULLBACK-WARMUP] 형성 중 봉 제거 (봉 수 부족이어도 지표에 넣지 않음) | ts={format_kst(initial_df.index[-1])}")
        initial_df = initial_df.iloc[:-1]
    if not _pullback_warmup_check(len(initial_df), required, holding=holding, user_id=user_id,
                                  ticker=ticker, notify=notify):
        return None
    return initial_df


PULLBACK_LIVE_REFUSE_MSG = "새 전략은 실계좌(LIVE)에서 아직 쓸 수 없습니다 (분할 체결 반영 작업 뒤 엽니다)"


def _pullback_seed_warmup(engine, initial_df: pd.DataFrame, pullback_cfg: dict, candle_validator=None):
    """PULLBACK 지표·링 버퍼를 워밍업 확정 봉으로 증분 시드(주문 없음). IndicatorState 200봉 SMA 폴백은 쓰지 않는다.
    봉 거르기는 BACKFILL 재생과 같은 `iter_valid_rows(…, candle_validator)` (F6: 거래량 0 봉 제외).
    반환: (ok, "pullback", reason, 버퍼·local_series 용 df(최근 PULLBACK_BUFFER_BARS 봉))"""
    from core.strategy_pullback import PullbackIndicators, PullbackSnapshotRing, RING_CAPACITY
    from core.strategy_pullback import bar_from_row, feed_confirmed_bar, iter_valid_rows
    c = pullback_cfg
    engine.pullback_indicators = PullbackIndicators(c["ma60p"], c["ma200p"], c["pullbackP"], c["slopeLB"], c["maType"])
    engine.pullback_ring = PullbackSnapshotRing(RING_CAPACITY)
    # 2차 T5: 전략이 시드와 같은 지표·링을 쓰게 먼저 묶는다(실시간 on_bar 가 이 객체로 이어 감)
    _bind = getattr(getattr(engine, "strategy", None), "bind", None)
    if callable(_bind):
        _bind(engine.pullback_indicators, engine.pullback_ring)
    for ts, row in iter_valid_rows(initial_df, candle_validator, tag="[PULLBACK-WARMUP]"):
        feed_confirmed_bar(engine, bar_from_row(ts, row, source="REST_WARMUP"))
    v = engine.pullback_indicators.last_values
    logger.info(
        f"[WARMUP] 시드 방식=pullback bars={len(initial_df)} fed={engine.pullback_indicators.n} "
        f"ring={len(engine.pullback_ring)} "
        f"maTrend={v['maTrend']} ma200={v['ma200']} maPullback={v['maPullback']} slope200={v['slope200']}"
    )
    return True, "pullback", "", initial_df.iloc[-PULLBACK_BUFFER_BARS:]


def _pullback_critical(title: str, body: str, key: str) -> None:
    """2차 T5: PULLBACK 기동·오염 CRITICAL (1시간 dedupe). 알림 실패는 매매 흐름을 막지 않는다."""
    try:
        from services.notifier import send as _notify, LEVEL_CRITICAL
        _notify(LEVEL_CRITICAL, title, body, dedupe_key=key, dedupe_ttl=3600)
    except Exception as e:
        logger.warning(f"[PULLBACK] 알림 실패 | {type(e).__name__}")


def _pullback_mark_polluted(engine, user_id: str, why: str) -> None:
    """지표 오염 표식 + CRITICAL. 신규 매수만 막히고(엔진·전략 게이트) 매도는 계속. 해제는 재시작 워밍업."""
    ind = getattr(engine, "pullback_indicators", None)
    if ind is not None:
        ind.state_polluted = True
    logger.error(f"[PULLBACK-POLLUTED] {why} → 신규 매수 중지(매도 계속), 재시작으로만 해제")
    _pullback_critical(
        f"🚨 새 전략 지표 오염 — {getattr(engine, 'ticker', '')}",
        (f"새 전략(PULLBACK) 지표를 바로잡지 못했습니다: {why}\n"
         "신규 매수를 멈췄고 익절·손절·데드크로스 매도는 계속합니다.\n"
         "조치: 봇 재시작(워밍업 재시드)으로만 해제됩니다."),
        f"pullback_polluted:{user_id}:{getattr(engine, 'ticker', '')}",
    )


# BACKFILL·catch-up 재생이 실보유 중에 바꾸지 않는 판정 칸 (실제 주문이 정한 회차·첫 체결·가상 평단)
_PULLBACK_TRADE_KEYS = ("entry_count", "pullback_count", "first_entry_ts", "first_entry_reason",
                        "pending_fill", "fill_n", "inv_sum", "trade_origin")


def _pullback_backfill_step(engine, backfill_ts_list, local_series: pd.DataFrame, closed_ts, user_id: str,
                            candle_validator, *, tag: str = "[PULLBACK-BACKFILL]", catchup: bool = False) -> list:
    """PULLBACK BACKFILL: 봉별 루프 대신 링 버퍼 재생 1회(F15). 돌려주는 빈 목록으로 봉별 루프를 건너뛴다(두 번 넣지 않음).
    2차 T5: (a) pullback_backfill 예외를 감싸 오염 표식 + CRITICAL (T3 넘김)
            (b) 실보유 중이면 재생은 지표·armed·prev_golden 만 바로잡고 회차 칸(_PULLBACK_TRADE_KEYS)은 재생 전 값 유지
                (T4 넘김 5 — 재생은 주문을 내지 않으므로 가상 회차가 실주문 회차를 덮지 않게. EMA 의 WO-14 E1 과 같은 원칙)
            (c) catchup=True(빠진 봉 채우기)에서 링 밖이면 그 봉이 지표에 영영 빠지므로 오염 표식"""
    from core import strategy_pullback as _sp
    past = local_series.index[local_series.index < closed_ts]
    if len(past) == 0:
        logger.warning(f"{tag} 직전 확정 봉 없음 → 재생 안 함 | closed_ts={format_kst(closed_ts)}")
        return []
    strategy = getattr(engine, "strategy", None)
    holding = bool(getattr(getattr(engine, "position", None), "has_position", False))
    kept = None
    if holding and hasattr(strategy, "export_split_state"):
        _st = strategy.export_split_state()
        kept = {k: _st.get(k) for k in _PULLBACK_TRADE_KEYS}
    msg = f"🔄 {tag} {len(backfill_ts_list)}개 봉 → 링 버퍼 재생 시작"
    logger.info(msg)
    log_to_file(msg, user_id)
    try:
        res = _sp.pullback_backfill(
            engine, first_ts=min(backfill_ts_list), series=local_series, until_ts=past.max(),
            changed_ts=list(backfill_ts_list), validator=candle_validator,
        )
    except Exception as e:
        logger.error(f"{tag} 재생 예외 | {type(e).__name__}: {e}", exc_info=True)
        _pullback_mark_polluted(engine, user_id, f"BACKFILL 재생 예외 {type(e).__name__}")
        return []
    if kept is not None and res.get("restored"):
        strategy.restore_split_state({**strategy.export_split_state(), **kept})
        ring = getattr(engine, "pullback_ring", None)
        if ring is not None and getattr(strategy, "last_ts", None) is not None:
            ring.amend_last_split(strategy.last_ts, strategy)
        logger.info(f"{tag} 실보유 중 → 회차 칸 재생 전 값 유지 | 회차={kept['entry_count']} armed={strategy.armed}")
    _from = f" from={format_kst(res['from_ts'])}" if res.get("from_ts") is not None else ""
    msg = (f"✅ {tag} 재생 완료 | restored={res['restored']} replayed={res['replayed']} "
           f"audited={res['audited']}{_from} until={format_kst(past.max())}"
           + (f" reason={res['reason']}" if res["reason"] else ""))
    logger.info(msg)
    log_to_file(msg, user_id)
    if res.get("reason") in ("restore_failed", "replay_failed"):
        _pullback_mark_polluted(engine, user_id, f"BACKFILL {res['reason']}")
    elif catchup and res.get("reason") in ("out_of_ring", "restore_rejected"):
        _pullback_mark_polluted(engine, user_id, f"빠진 봉을 채우지 못함({res['reason']})")
    return []


def _pullback_catchup_step(engine, local_series: pd.DataFrame, closed_ts, user_id: str, candle_validator) -> None:
    """2차 T5 (T4 넘김 2): 전략이 마지막으로 본 봉(strategy.last_ts)과 이번 확정 봉(closed_ts) 사이에
    local_series 에 있는 봉(잠정 봉·VERIFY 실패·봉 검증 실패로 엔진에 안 들어간 봉)을 링 재생으로 채운다.
    봉 검증 실패 봉은 재생에서도 같은 규칙으로 빠진다(시드와 같음, F6). 주문 없음."""
    if local_series is None or local_series.empty:
        return
    last = getattr(getattr(engine, "strategy", None), "last_ts", None)
    if last is None:
        return
    idx = local_series.index
    gap = list(idx[(idx > last) & (idx < closed_ts)])
    if not gap:
        return
    logger.warning(f"[PULLBACK-CATCHUP] 지표에 안 들어간 확정 봉 {len(gap)}개 → 링 재생 | "
                   f"last={format_kst(last)} first_gap={format_kst(gap[0])} closed={format_kst(closed_ts)}")
    _pullback_backfill_step(engine, gap, local_series, closed_ts, user_id, candle_validator,
                            tag="[PULLBACK-CATCHUP]", catchup=True)


def _pullback_do_snapshot(engine, params, user_id: str, current_minute):
    """2차 T5: PULLBACK 1분 설정 스냅샷 — 조건 파일 안 읽음. tp·sl = 적용본(전략 객체 tp/100·sl/100),
    조건 dict 는 빈 값, ts_pct·signal_gate·threshold 는 None·False·0."""
    st = getattr(engine, "strategy", None)
    tp = getattr(st, "take_profit", None)
    sl = getattr(st, "stop_loss", None)
    insert_settings_snapshot(
        user_id=user_id,
        ticker=params.upbit_ticker,
        interval_sec=getattr(params, "interval_sec", 60),
        tp=tp if tp is not None else params.take_profit,
        sl=sl if sl is not None else params.stop_loss,
        ts_pct=None,
        signal_gate=False,
        threshold=0.0,
        buy_dict={},
        sell_dict={},
        bar_time=current_minute,
    )
    return {"buy": {}, "sell": {}}


def _pullback_warmup_progress(engine, required: int, buffer_len: int) -> str:
    """워밍업 감사 문구: 버퍼 500봉 기준이 아니라 지표에 넣은 봉 수 기준 (T3 넘김)."""
    ind = getattr(engine, "pullback_indicators", None)
    n = getattr(ind, "n", 0)
    return f"(지표 {n}/{required} · 버퍼 {buffer_len})"


def _min_history_bars_for(params: LiveParams, strategy_type: str) -> int:
    """
    전략 실행/매매를 시작하기 위한 최소 웜업 바 수

    ✅ WO-2026-001: 다중 호출로 200개 이상 조회 가능
    - rest_reconcile.py가 자동으로 다중 batch 처리
    - EMA slow=200 → 400개 요청 → Batch 1 (200) + Batch 2 (200)
    """
    iv = getattr(params, "interval", None)
    strategy_tag = strategy_type.upper()

    if strategy_tag == "EMA":
        warmup_table = WARMUP_LEN_BY_INTERVAL_EMA
    else:
        warmup_table = WARMUP_LEN_BY_INTERVAL_MACD

    if isinstance(iv, str) and iv in warmup_table:
        base = warmup_table[iv]
    else:
        base = 300

    # ============================================================
    # ✅ FIX-2026-003-14: Indicator seed 실제 요구량과 정확히 일치
    # - indicator_state.py:119-133의 required 계산 로직 적용
    # - max(macd_slow, ema_slow, base_ema)
    # ============================================================

    # 1. MACD slow period (MACD 전략 또는 EMA 전략에서도 사용)
    macd_slow = getattr(params, "macd_slow_period", 26) or 26

    # 2. EMA slow period (use_separate_ema 고려)
    if strategy_tag == "EMA" and getattr(params, "use_separate_ema", False):
        slow_buy = getattr(params, "slow_buy", None) or params.slow_period
        slow_sell = getattr(params, "slow_sell", None) or params.slow_period
        ema_slow = max(slow_buy, slow_sell)
    else:
        ema_slow = getattr(params, "slow_period", 26) or 26

    # 3. Base EMA period (EMA 전략만)
    if strategy_tag == "EMA":
        base_ema = getattr(params, "base_ema_period", 200)
    else:
        base_ema = 0

    # ✅ Seed 최소 요구량 (indicator_state.py와 동일)
    # - 이전: slow * 2 (안정화 목표, 과도함)
    # - 수정: max(periods) (실제 seed 요구량)
    logical_min = max(macd_slow, ema_slow, base_ema)

    # ✅ 최종 요청량 (base, logical_min, 200 중 최대값)
    # - 주의: Upbit API는 200개 제한이지만 rest_reconcile.py가 다중 호출 처리
    # - 하지만 실제로는 200개 이상 받지 못하는 경우 발생 (데이터 부족, API 제한)
    requested = max(base, logical_min, 200)

    return requested


# ============================================================
# 유틸 함수 (기존 유지)
# ============================================================

def _wallet_has_position(trader: UpbitTrader, ticker: str) -> bool:
    """지갑 잔고로 포지션 확인"""
    try:
        bal = float(trader._coin_balance(ticker))
        logger.info(f"[WALLET-HAS-POS] ticker={ticker} coin_bal={bal}")
        return bal >= 1e-6
    except Exception as e:
        logger.warning(f"[WALLET-HAS-POS] _coin_balance({ticker}) failed: {e}")
        return False


def _wallet_balance(trader: UpbitTrader, ticker: str) -> float:
    """지갑 잔고 확인"""
    try:
        bal = float(trader._coin_balance(ticker))
        logger.info(f"[WALLET-BAL] ticker={ticker} coin_bal={bal}")
        return bal
    except Exception as e:
        logger.warning(f"[WALLET-BAL] _coin_balance({ticker}) failed: {e}")
        return 0.0


def _boot_seed_recover_from_wallet(engine, ticker: str, user_id: str, wallet_qty: float) -> bool:
    """
    ✅ WO-12 C7 (2026-09-30): 부팅 복원이 봇 주문을 못 찾았을 때(앱에서 산 외부 매수 포지션),
    첫 봉 [POSITION-SYNC] 와 **같은 함수**(StrategyEngine._reconcile_position_with_wallet)·같은 출처
    (account_positions.entry_price = 업비트 avg_buy_price 캐시 → 봇 미청산 BUY)로 워밍업 직후 즉시 복원한다.
    새 판정 논리 없음. 실패 시 기존 CRITICAL + 알림 유지.

    근거: 2026-09-30 18:02:07 KRW-JTO 1,340.436268 — [SEED] raw_last_open=None → CRITICAL,
          18:10:11 첫 봉에서야 복구 (약 8분 매도 평가 공백).
    """
    source = None
    try:
        source = engine._reconcile_position_with_wallet()
    except Exception as e:
        logger.error(f"[BOOT-SEED] 지갑 기준 복원 호출 실패: {e}")
    if source and engine.position.has_position:
        logger.info(
            f"[BOOT-SEED] source={source} entry={engine.position.avg_price} "
            f"qty={engine.position.qty:.6f} entry_bar={engine.position.entry_bar}"
        )
        engine._boot_seed_verify = {"source": source}
        return True

    logger.critical(
        f"❌ 지갑에 코인({wallet_qty:.6f}) 있으나 DB 진입가 seed 실패 "
        f"→ has_position=False 유지 (봇 매매 스킵). "
        f"수동 정리 또는 force_liquidate 필요."
    )
    try:
        from services.notifier import send as _notify_send, LEVEL_CRITICAL
        _notify_send(
            LEVEL_CRITICAL,
            f"🚨 포지션 seed 실패 — {ticker}",
            (
                f"봇 부팅 시 지갑에 코인({wallet_qty:.6f}) 있으나 진입가 복원 불가.\n"
                f"봇 매매 정지 상태 유지 (잘못된 매도 방지).\n"
                f"HTS 수동 매도 or force_liquidate 필요."
            ),
            dedupe_key=f"boot_seed_fail:{ticker}",
            dedupe_ttl=600,
        )
    except Exception:
        pass
    return False


def _seed_entry_price_from_db(ticker: str, user_id: str) -> Optional[Dict[str, Any]]:
    """DB에서 최근 completed BUY의 체결가·entry_bar·entry_ts를 복구.

    ✅ SP-PI-1: entry_ts_iso 도 함께 반환 (P3 boot seed 에서 원 시각 복원용).
    """
    try:
        raw = get_last_open_buy_order(ticker, user_id)
        logger.info(f"[SEED] raw_last_open={raw}")
        if not raw:
            logger.info("[SEED] result=None (no data)")
            return None

        result = {}
        price = raw.get("price")
        entry_bar = raw.get("entry_bar")
        entry_ts_iso = raw.get("entry_ts_iso")

        if price is not None:
            result["price"] = float(price)
        if entry_bar is not None:
            result["entry_bar"] = int(entry_bar)
        if entry_ts_iso:
            result["entry_ts_iso"] = str(entry_ts_iso)

        if not result:
            logger.info("[SEED] result=None (no price or entry_bar)")
            return None

        logger.info(
            f"🔁 Seed from DB: price={result.get('price')} "
            f"entry_bar={result.get('entry_bar')} entry_ts={result.get('entry_ts_iso')}"
        )
        return result
    except Exception as e:
        logger.warning(f"[SEED] failed: {e}")
        return None


def _restore_weak_entry_safe(position, source: str):
    """✅ WO-26: 약매수 표식 복원 (예외는 삼키고 ERROR 1줄 — 복원 실패 시 일반 익절 기준)."""
    try:
        from core.weak_entry import restore_weak_entry
        return restore_weak_entry(position, source=source)
    except Exception as e:
        logger.error(f"[WEAK-ENTRY] {source} 복원 실패: {e}")
        return None


def _apply_boot_seed(position, db_result: Dict[str, Any], actual_qty: float) -> bool:
    """기동 시 봇 주문 기록으로 보유 포지션의 진입 시각·진입 봉을 복원 (P3 boot_seed).

    ✅ WO-20 (2026-10-02) 규칙:
    - 주문 기록에서는 entry_ts 와 entry_bar 만 가져온다.
      entry_ts 는 COALESCE(executed_at, updated_at) (services/db.py get_last_open_buy_order).
    - avg_price 는 직전 sync_from_wallet 이 정한 지갑 값(account_positions.entry_price 또는
      Upbit avg_buy_price)을 유지한다. 지갑 평균가를 구하지 못한 경우에만 주문 평균가를 쓴다.
      (봇 매수 뒤 앱 추가 매수가 섞인 포지션에서 단일 주문 평균가로 덮지 않기 위함)
    - entry_ts 가 없으면 apply_entry 를 부르지 않는다. 지갑 동기화 값(has_position=True,
      entry_ts=기동 시각)이 그대로 남으므로 WARNING 1줄로 사실대로 남긴다.

    Returns:
        bool: apply_entry(source="boot_seed") 를 불렀으면 True
    """
    order_price = db_result.get("price")
    entry_bar = db_result.get("entry_bar")
    entry_ts_iso = db_result.get("entry_ts_iso")

    entry_ts = None
    if entry_ts_iso:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            entry_ts = datetime.fromisoformat(str(entry_ts_iso))
            if entry_ts.tzinfo is None:
                entry_ts = entry_ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        except Exception as e:
            logger.warning(f"[SEED] entry_ts parse 실패: {e} → seed 시각 부재")
            entry_ts = None

    wallet_avg = position.avg_price if (position.avg_price is not None and position.avg_price > 0) else None
    if wallet_avg is not None:
        avg_price, avg_src = float(wallet_avg), "wallet"
    elif order_price is not None:
        avg_price, avg_src = float(order_price), "order"
    else:
        avg_price, avg_src = None, None

    if entry_ts is not None and avg_price is not None:
        position.apply_entry(
            qty=actual_qty,
            avg_price=avg_price,
            entry_bar=int(entry_bar) if entry_bar is not None else 0,
            entry_ts=entry_ts,
            source="boot_seed",
        )
        # ✅ WO-26: 약매수 표식 복원 (마지막 봇 BUY uuid 일치 시만) — restore_trailing_on_boot 보다 앞
        _restore_weak_entry_safe(position, "boot_seed")
        logger.info(
            f"🔁 Position recovered | avg_price={avg_price} (출처: {avg_src}) order_price={order_price} "
            f"qty={actual_qty:.6f} entry_bar={entry_bar} entry_ts={entry_ts.isoformat()}"
        )
        return True

    # entry_ts(또는 평균가) 를 정하지 못함 — apply_entry 미호출, 지갑 동기화 값 유지
    _ts = position.entry_ts.isoformat() if hasattr(position.entry_ts, "isoformat") else position.entry_ts
    logger.warning(
        f"⚠️ [BOOT-SEED] 봇 주문의 체결 시각 없음 → boot_seed 미적용, 지갑 동기화 값 유지 | "
        f"has_position={position.has_position} qty={actual_qty:.6f} avg_price={position.avg_price} (출처: 지갑) "
        f"entry_ts={_ts} (기동 시각) | 정체 포지션 판정은 기동 시각부터 다시 센다 | "
        f"order_price={order_price} entry_ts_iso={entry_ts_iso}"
    )
    return False


def detect_position_and_seed_entry(
    trader: UpbitTrader,
    ticker: str,
    user_id: str,
    entry_price: Optional[float],
) -> Tuple[bool, Optional[float]]:
    """
    지갑 잔고로 실제 포지션 유무를 판단하고, 엔트리 가격이 없으면 DB에서 1회 시드
    """
    bal = _wallet_balance(trader, ticker)
    inpos = bal >= 1e-6

    if inpos and entry_price is None:
        seed = get_last_open_buy_order(ticker, user_id)
        ep = (seed or {}).get("price")
        if ep is not None:
            entry_price = float(ep)
            logger.info(f"[POS] inpos=True, entry_price seeded={entry_price}")
        else:
            logger.info("[POS] inpos=True, but no entry price in DB")

    if (not inpos) and (entry_price is not None):
        logger.info("[POS] inpos=False → entry_price reset")
        entry_price = None

    return inpos, entry_price


def _trim_rest_before_local_start(local_series: pd.DataFrame, rest_df: Optional[pd.DataFrame]):
    """
    ✅ WO-14 (b) (2026-10-01): 조정 조회 결과에서 로컬 시계열 시작보다 이른 봉을 뺀다.
    기동 때 로컬은 워밍업 200봉뿐인데 조정은 400봉을 요청(298 수신)해, 엔진이 처리한 적 없는
    과거 봉이 inserted → BACKFILL 로 재평가됐다(기동마다 92~116봉, WO-13 (b)).
    로컬이 비었거나 REST 가 없으면 그대로 둔다(기존 동작).
    반환: (rest_df, 뺀 봉 수)
    """
    if rest_df is None or local_series is None or local_series.empty:
        return rest_df, 0
    local_start = local_series.index[0]
    kept = rest_df[rest_df.index >= local_start]
    return kept, len(rest_df) - len(kept)


def _strategy_tag(strategy_type: str) -> str:
    """전략 타입 정규화"""
    if not strategy_type:
        return DEFAULT_STRATEGY_TYPE.upper()
    return strategy_type.upper().strip()


def _get_trade_conditions_path(user_id: str, strategy_type: str):
    """조건 파일의 실제 경로 반환 (없으면 None). _load_trade_conditions와 동일 우선순위."""
    strategy_tag = _strategy_tag(strategy_type)
    main_path = Path(f"{user_id}_{strategy_tag}_{CONDITIONS_JSON_FILENAME}")
    legacy_path = Path(f"{user_id}_{CONDITIONS_JSON_FILENAME}")
    if main_path.exists():
        return str(main_path)
    if legacy_path.exists():
        return str(legacy_path)
    return None


def _maybe_reload_params(*, user_id, params_ref, strategy, cond_path, mtime_state):
    """
    ✅ B7: 조건 파일(buy_sell_conditions.json) mtime 감지 후 strategy 인스턴스에 무중단 반영.

    - 안전 영역만 갱신: take_profit, stop_loss, trailing_stop_pct, buy/sell_conditions, 필터 임계값
    - params.json(지표 구조 = EMA 기간/base_ema 등)은 본 경로에서 추적하지 않음.
      해당 항목 변경은 엔진 재시작 필요 정책이며, live_loop 내부 스코프에
      json_path 변수가 정의되어 있지 않아 회귀 버그(NameError) 유발했음.

    Returns:
        갱신된 mtime_state dict
    """
    new_state = dict(mtime_state)

    # 1) sell/buy 조건 파일 mtime 체크 (실시간 반영 우선순위)
    try:
        if cond_path and os.path.exists(cond_path):
            cur = os.path.getmtime(cond_path)
            if cur > new_state.get("conditions", 0.0):
                conditions = _load_trade_conditions(user_id, params_ref.strategy_type) or {}
                buy_c = conditions.get("buy", {}) or {}
                sell_c = conditions.get("sell", {}) or {}
                # strategy의 안전 영역 갱신
                if "take_profit_pct" in sell_c:
                    strategy.take_profit = float(sell_c["take_profit_pct"]) / 100.0
                if "stop_loss_pct" in sell_c:
                    strategy.stop_loss = float(sell_c["stop_loss_pct"]) / 100.0
                if "trailing_stop_threshold_pct" in sell_c:
                    strategy.trailing_stop_pct = float(sell_c["trailing_stop_threshold_pct"]) / 100.0
                    strategy.trailing_stop_activation_pct = strategy.take_profit
                if "use_fixed_trailing" in sell_c:
                    strategy.use_fixed_trailing = bool(sell_c.get("use_fixed_trailing", False))
                strategy.buy_conditions = buy_c
                strategy.sell_conditions = sell_c
                # ✅ WO-26: 약매수 필터도 같은 조건으로 다시 만든다 (보유 포지션의 익절 덮어쓰기는 유지)
                if hasattr(strategy, "_apply_weak_entry_conditions"):
                    strategy._apply_weak_entry_conditions(buy_c)

                # 필터 인스턴스 임계값 갱신 (sell_filter_manager.filters 순회)
                try:
                    mgr = getattr(strategy, "sell_filter_manager", None)
                    if mgr is not None:
                        for f in getattr(mgr, "filters", []) or []:
                            name = type(f).__name__
                            if name == "StopLossFilter":
                                f.stop_loss_pct = strategy.stop_loss
                            elif name == "TakeProfitFilter":
                                f.take_profit_pct = strategy.take_profit
                            elif name == "TrailingStopFilter":
                                f.trailing_stop_pct = strategy.trailing_stop_pct
                                f.take_profit_pct = strategy.take_profit
                                f.use_fixed_mode = getattr(strategy, "use_fixed_trailing", False)
                except Exception as e:
                    logger.warning(f"[PARAMS-RELOAD] filter update failed: {e}")

                logger.info(
                    f"🔄 [PARAMS-RELOAD] 조건 파일 변경 반영 완료 | "
                    f"tp={strategy.take_profit:.2%} sl={strategy.stop_loss:.2%} "
                    f"ts={strategy.trailing_stop_pct} use_fixed={getattr(strategy, 'use_fixed_trailing', False)}"
                )
                try:
                    from services.db import insert_log
                    insert_log(user_id, "INFO", f"[PARAMS-RELOAD] 조건 파일 변경 반영")
                except Exception:
                    pass
                new_state["conditions"] = cur
    except Exception as e:
        logger.warning(f"[PARAMS-RELOAD] conditions reload failed: {e}")

    return new_state


def _drop_unconfirmed_backfill_ts(backfill_ts_list, closed_ts):
    """
    ✅ WO-14 (a) (2026-10-01): 확정 대상 봉(closed_ts)보다 늦은 봉은 아직 닫히지 않은 봉이므로
    BACKFILL 대상에서 뺀다. 조정 조회 첫 배치가 end_ts 없이 조회해 형성 중 봉을 받아 오고,
    그 봉이 inserted → BACKFILL 로 미확정 종가 평가됐다(2026-09-30 16:50:05, 20:10:05, WO-13 (a)).
    다음 주기에 그 봉이 확정 대상 봉이 되면 정상 실시간 평가된다.
    반환: (남긴 목록, 뺀 목록)
    """
    kept = [ts for ts in backfill_ts_list if ts <= closed_ts]
    dropped = [ts for ts in backfill_ts_list if ts > closed_ts]
    return kept, dropped


def _load_trade_conditions(user_id: str, strategy_type: str) -> Dict[str, Any]:
    """
    매수/매도 조건 JSON 로드
    - 우선순위:
        1) {user_id}_{STRATEGY}_{CONDITIONS_JSON_FILENAME}
        2) (없을 경우) {user_id}_{CONDITIONS_JSON_FILENAME}
    """
    strategy_tag = _strategy_tag(strategy_type)
    main_path = Path(f"{user_id}_{strategy_tag}_{CONDITIONS_JSON_FILENAME}")
    legacy_path = Path(f"{user_id}_{CONDITIONS_JSON_FILENAME}")

    path_to_use = None
    if main_path.exists():
        path_to_use = main_path
    elif legacy_path.exists():
        path_to_use = legacy_path

    if path_to_use is None:
        logger.warning(
            f"[COND] condition file not found for user={user_id}, strategy={strategy_tag}"
        )
        return {"buy": {}, "sell": {}}

    try:
        with path_to_use.open("r", encoding="utf-8") as f:
            conds = json.load(f)
        logger.info(f"[COND] loaded: {path_to_use}")
        return conds
    except Exception as e:
        logger.warning(f"[COND] failed to load {path_to_use}: {e}")
        return {"buy": {}, "sell": {}}


_BACKFILL_TRAILING_FIELDS = (
    "highest_price",
    "highest_since_entry",
    "trailing_armed",
    "trailing_fixed_amount",
    "trailing_activation_price",
)


def _config_applied_line(buy_conditions: Optional[dict], sell_conditions: Optional[dict]) -> str:
    """
    ✅ WO-26 (2026-10-20, 백로그 "기동 시 설정 키·적용값 로그"): 조건 파일 키와 config 기본값으로 채운 키를
    한 줄로 만든다. 표기: 키=값 (파일에 없어 기본값을 쓴 키는 키=값*). 값은 엔진이 쓰는 해석과 같다.
    """
    from config import UNFILLED_TO_MARKET_DEFAULT, UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT
    from core.strategy_incremental import IncrementalEMAStrategy
    bc = dict(buy_conditions or {})
    sc = dict(sell_conditions or {})
    weak_applied = IncrementalEMAStrategy.weak_entry_settings(bc)
    defaults = {
        "fixed_price_unfilled_to_market": UNFILLED_TO_MARKET_DEFAULT,
        "fixed_price_convert_max_gap_pct": UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT,
        **IncrementalEMAStrategy.weak_entry_settings({}),
    }
    parts = []
    for k in sorted(set(bc) | set(defaults)):
        v = weak_applied[k] if k in weak_applied else bc.get(k, defaults.get(k))
        parts.append(f"{k}={v}{'' if k in bc else '*'}")
    sell_parts = [f"{k}={sc[k]}" for k in sorted(sc)]
    return f"[CONFIG] 적용값 (*=기본값) | buy: {' '.join(parts)} | sell: {' '.join(sell_parts)}"


def _backup_dead_cross_ts(indicators) -> Dict[str, Any]:
    """
    ✅ WO-26 (2026-10-20): BACKFILL 전 마지막 D/C 시각 백업 (Issue #11 지표 백업 dict 에 합친다).
    재평가 봉에서 난 D/C 가 실시간 약매수 판정을 오염시키지 않게 한다.
    """
    return {"last_dead_cross_ts": getattr(indicators, "last_dead_cross_ts", None)}


def _restore_dead_cross_ts(indicators, saved: Dict[str, Any]) -> None:
    """✅ WO-26: BACKFILL 뒤 마지막 D/C 시각 복원 (지표 복원 try 안에서 함께 — 실패하면 지표 오염 상태와 같은 처리)."""
    indicators.last_dead_cross_ts = saved["last_dead_cross_ts"]


def _backup_trailing_state(position) -> Dict[str, Any]:
    """
    ✅ WO-14 E1 (2026-10-01): BACKFILL 전 Trailing 상태 백업.
    정책: BACKFILL 재평가는 지표를 바로잡는 작업이며 포지션 상태를 바꾸지 않는다.
    과거 누락 봉의 가격은 실시간에 보지 못한 가격이므로 Trailing 고점에 반영하지 않는다.
    """
    saved = {f: getattr(position, f, None) for f in _BACKFILL_TRAILING_FIELDS}
    saved["has_position"] = getattr(position, "has_position", False)
    return saved


def _restore_trailing_state(position, saved: Dict[str, Any]):
    """
    ✅ WO-14 E1: BACKFILL 뒤 Trailing 상태 복원. 바뀐 필드만 되돌린다.
    BACKFILL 중 보유 여부가 바뀌었으면(별도 스레드 체결 반영 등) 새 포지션 상태를 덮어쓰지 않도록 건너뛴다.
    반환: {필드: (BACKFILL 뒤 값, 되돌린 값)} — 건너뛰면 None
    """
    if getattr(position, "has_position", False) != saved.get("has_position"):
        return None
    changed = {}
    for f in _BACKFILL_TRAILING_FIELDS:
        cur = getattr(position, f, None)
        if cur != saved[f]:
            changed[f] = (cur, saved[f])
            setattr(position, f, saved[f])
    return changed


# ============================================================
# 메인 Live Loop (증분 처리 기반)
# ============================================================

def run_live_loop(
    params: LiveParams,
    q: queue.Queue,
    trader: UpbitTrader,
    stop_event: threading.Event,
    test_mode: bool,
    user_id: str,
    pullback_cfg: Optional[dict] = None,  # 2차 T3: PULLBACK 적용본 dict (T5 가 넘긴다). EMA·MACD 는 None
) -> None:
    """
    실시간 운용 루프 - 증분 처리 기반 (Backtest 제거)

    핵심 변경점:
    1. Backtest 엔진을 매 루프마다 실행하는 구조 완전 제거
    2. 새 봉 1개가 확정될 때마다만 처리
    3. 지표는 증분 업데이트만 수행 (전체 재계산 없음)
    4. 주문/포지션은 PositionState 기준으로 관리
    """
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx
        add_script_run_ctx(threading.current_thread())
    except Exception:
        logger.debug("[BOOT] Streamlit ScriptRunContext 바인딩 스킵")

    is_live = (not test_mode)
    mode_tag = "LIVE" if is_live else "TEST"
    strategy_tag = _strategy_tag(params.strategy_type)

    logger.info(f"[BOOT] run_live_loop start | mode={mode_tag} | strategy={strategy_tag}")

    # 2차 T5 (T1 거부 대체): PULLBACK 은 엔진 관리자가 적용본 로더(load_for_boot)로 읽은 pullback_cfg 가
    # 있을 때만 돈다. 없거나(None) PULLBACK 경로가 없는 LEGACY_LOCAL 이면 정합 검사·지갑 동기화·reconciler 등록보다
    # 먼저 거부 + CRITICAL, stop_event 를 켜서 엔진 관리 스레드가 정리(stopped·잠금 해제)하게 한다.
    # 검수 반영(10/28): LIVE(test_mode 아님)도 거부한다 — LIVE buy_market 은 qty=0.0 을 돌려주므로 2회차 이상 평단이
    # 1회차에 고정된다. 분할 체결 수량·평단 반영(T6) 전에는 실계좌에서 새 전략을 돌리지 않는다.
    if strategy_tag == "PULLBACK" and (pullback_cfg is None or RUN_MODE != "UPBIT_MATCH" or not test_mode):
        if pullback_cfg is None:
            _why = "pullback_cfg 없음(적용본 로더 미경유)"
        elif RUN_MODE != "UPBIT_MATCH":
            _why = f"RUN_MODE={RUN_MODE}"
        else:
            _why = PULLBACK_LIVE_REFUSE_MSG
        logger.error(f"[PULLBACK-PARAMS] 기동 거부 | {_why} | user_id={user_id}")
        _pullback_critical(
            f"🚨 새 전략 기동 거부 — {params.upbit_ticker}",
            f"새 전략(PULLBACK) 엔진을 시작하지 않았습니다.\n사유: {_why}\n운영자 확인 필요.",
            f"pullback_boot_refused:{user_id}",
        )
        stop_event.set()
        return

    logger.info("🚀 ★ 증분 처리 기반 엔진 (Backtest 없음) ★")

    # ✅ WO-18 (c): 기동 시 정합 검사 — 보유 0 인데 hts_buy 가 남은 행 정리 (LIVE 만, 과거 audit 무변경)
    if not test_mode:
        try:
            from services.db import clear_stale_hts_flags
            _hts_cleared = clear_stale_hts_flags(user_id)
            logger.info(f"[HTS-FLAG] 기동 정합 검사 완료 | user_id={user_id} cleared={_hts_cleared}")
        except Exception as e:
            logger.warning(f"[HTS-FLAG] 기동 정합 검사 실패 | user_id={user_id} | {e}")
        # ✅ WO-26: 보유 0 인데 약매수 표식(meta.weak_entry)이 남은 행 정리
        try:
            from services.db import clear_stale_weak_entries
            _weak_cleared = clear_stale_weak_entries(user_id)
            logger.info(f"[WEAK-ENTRY] 기동 정합 검사 완료 | user_id={user_id} cleared={_weak_cleared}")
        except Exception as e:
            logger.warning(f"[WEAK-ENTRY] 기동 정합 검사 실패 | user_id={user_id} | {e}")

    # ✅ P1 — 설정 History 시드 (idempotent). 사용자가 한 번도 명시 저장한 적 없는
    # 새 (user_id, strategy_tag) 조합에 첫 active_settings_id 를 확보.
    # PULLBACK 은 구버전 설정 이력을 쓰지 않는다(경고 반복 방지, 설정 기록은 v2hist — 결정 D1).
    if strategy_tag != "PULLBACK":
        try:
            from services.settings_history import seed_initial_snapshot, record_strategy_init
            seed_initial_snapshot(user_id, strategy_tag)
            # ✅ SP2 — strategy 객체 재초기화 시점 자동 row + applied_at 일괄 채움
            record_strategy_init(user_id, strategy_tag)
        except Exception as _seed_e:
            logger.warning(f"[settings_history] seed_initial_snapshot 실패: {_seed_e}")

    # ============================================================
    # 1단계: 핵심 데이터 구조 초기화 (프로세스 시작 시 1회만)
    # ============================================================

    # CandleBuffer 생성
    buffer = CandleBuffer(maxlen=500)

    # IndicatorState 생성
    indicators = IndicatorState(
        macd_fast=params.fast_period,
        macd_slow=params.slow_period,
        macd_signal=params.signal_period,
        ema_fast=getattr(params, "fast_period", 20),
        ema_slow=getattr(params, "slow_period", 60),
        base_ema=getattr(params, "base_ema_period", 200),  # ✅ 기본값 200 (200일선)
        # ✅ 매수/매도 별도 EMA 설정
        use_separate_ema=getattr(params, "use_separate_ema", True),
        ema_fast_buy=getattr(params, "fast_buy", None),
        ema_slow_buy=getattr(params, "slow_buy", None),
        ema_fast_sell=getattr(params, "fast_sell", None),
        ema_slow_sell=getattr(params, "slow_sell", None),
    )

    # PositionState 생성
    # ✅ Issue #10: trader와 ticker를 전달하여 실제 지갑/DB 잔고 기반 동기화 가능
    position = PositionState(trader=trader, ticker=params.upbit_ticker)

    # 기존 포지션 복구 (지갑 기준)
    # ✅ WO-12 C7: 봇 주문 기준 seed 실패 시 워밍업 뒤 지갑 기준 복원할 수량 (None = 해당 없음)
    boot_seed_recover_qty = None
    # ✅ sync_from_wallet()로 실제 잔고 동기화
    position.sync_from_wallet()
    has_pos = position.has_position
    if has_pos:
        # ✅ 실제 지갑 잔고로 qty 설정 (Single Source of Truth)
        actual_qty = _wallet_balance(trader, params.upbit_ticker)

        db_result = _seed_entry_price_from_db(params.upbit_ticker, user_id)
        if db_result:
            _apply_boot_seed(position, db_result, actual_qty)
        else:
            # ✅ SP-PI-5: avg_price=None 비상 모드 완전 제거.
            #   진입가·시각이 신뢰 가능하지 않은 상태로 has_position=True 를 유지하면
            #   SL/TP/Stale 계산 불가 (avg_price None 시 division 실패)·잘못된 매도 위험.
            #   → has_position=False 유지 + Telegram CRITICAL. 사용자 수동 개입 요청.
            # ✅ WO-12 C7: 봇 주문이 없을 뿐(외부 매수)일 수 있으므로 CRITICAL 은 워밍업 뒤
            #   _boot_seed_recover_from_wallet() 이 지갑 기준 복원까지 실패했을 때만 낸다.
            boot_seed_recover_qty = actual_qty
            logger.warning(
                f"[BOOT-SEED] 봇 주문 기준 진입가 없음 (외부 매수 가능) → 워밍업 뒤 지갑 기준 복원 시도 | "
                f"wallet={actual_qty:.6f}"
            )
            # ✅ [Phase 1-E/P1-4] sync_from_wallet 가 이미 True 세팅했을 수 있으므로 명시적 False 리셋.
            # 감사 결과: 이전엔 has_position + qty 만 리셋했으나 avg_price/entry_ts/entry_bar 는 잔존 →
            # 다음 sync_from_wallet 이 wallet 감지 시 Fix 1 조건 (avg_price is None) False 로 스킵되어
            # 옛 값 그대로 사용 → 위험 상태 지속. avg_price 등 관련 필드 모두 완전 리셋.
            position._has_position = False
            position.qty = 0.0
            position.avg_price = None
            position.entry_ts = None
            position.entry_bar = None
            position.highest_price = None
            position.highest_since_entry = None
            position.trailing_armed = False
            position.trailing_fixed_amount = None
            position.trailing_activation_price = None
            logger.warning(
                f"🔄 [BOOT-SEED] 완전 상태 리셋 완료 (avg_price/entry_ts/entry_bar/highest 모두 None). "
                f"사용자 개입 대기 상태."
            )

    # ✅ Issue #17 Hotfix + Policy P-1: TEST 사용자는 등록 스킵 (지갑 조회 금지)
    reconciler = get_reconciler()
    reconciler.register_user(user_id, test_mode=test_mode)
    if not test_mode:
        logger.info(f"✅ [HTS-DETECT] LIVE user {user_id} registered for periodic balance sync (interval=60s)")
    else:
        logger.info(f"[BOOT] TEST 모드 — Reconciler 잔고 동기화 비활성")

    # ✅ 조건 파일 로드 (매수/매도 조건)
    # 2차 T5 (F13·X13): PULLBACK 은 조건 파일을 읽지 않는다 (옛 공용 {user}_buy_sell_conditions.json 폴백 차단)
    conditions = {"buy": {}, "sell": {}} if strategy_tag == "PULLBACK" else _load_trade_conditions(user_id, params.strategy_type)
    buy_conditions = conditions.get("buy", {})  # ✅ 매수 조건 추출
    sell_conditions = conditions.get("sell", {})  # ✅ 매도 조건 추출

    # 🔍 DEBUG: 조건 파일 로딩 상태 상세 로그
    logger.info(f"🔍 DEBUG [CONDITIONS] Full conditions loaded: {conditions}")
    logger.info(f"[전략 초기화] Loaded buy conditions: {buy_conditions}")
    logger.info(f"[전략 초기화] Loaded sell conditions: {sell_conditions}")

    # ✅ 필수 매도 조건 검증
    if strategy_tag == "PULLBACK":
        logger.info("[COND] PULLBACK — 조건 파일 안 읽음 (적용본 tp·sl·deadcross 사용)")
    elif not sell_conditions:
        logger.error(f"⚠️ CRITICAL: 매도 조건이 비어있습니다! conditions={conditions}")
    else:
        required_sell_keys = ["ema_dc", "stop_loss", "take_profit", "trailing_stop"]
        missing_keys = [k for k in required_sell_keys if k not in sell_conditions]
        if missing_keys:
            logger.warning(f"⚠️ 누락된 매도 조건 키: {missing_keys}")
        else:
            logger.info(f"✅ 매도 조건 검증 완료: {list(sell_conditions.keys())}")

    # 전략 객체 생성 (1회만)
    if strategy_tag == "MACD":
        strategy = IncrementalMACDStrategy(
            user_id=user_id,
            ticker=params.upbit_ticker,
            macd_threshold=getattr(params, "macd_threshold", 0.0),
            take_profit=params.take_profit,
            stop_loss=params.stop_loss,
            macd_crossover_threshold=getattr(params, "macd_crossover_threshold", 0.0),
            min_holding_period=getattr(params, "min_holding_period", 0),
            trailing_stop_pct=getattr(params, "trailing_stop_pct", TRAILING_STOP_PERCENT),
            buy_conditions=buy_conditions,  # ✅ 조건 파일 전달 (BUY)
            sell_conditions=sell_conditions,  # ✅ 조건 파일 전달 (SELL)
        )
    elif strategy_tag == "EMA":
        # ✅ 조건 파일에서 use_base_ema 설정 읽기 (기본값: True, 하위호환성)
        use_base_ema_filter = getattr(params, "use_base_ema", True)

        # ✅ EMA SELL 조건 검증
        from services.validation import validate_ema_sell_conditions
        sell_conditions = validate_ema_sell_conditions(sell_conditions)
        logger.info(f"✅ [EMA] SELL 조건 검증 완료")

        strategy = IncrementalEMAStrategy(
            user_id=user_id,
            ticker=params.upbit_ticker,
            take_profit=params.take_profit,
            stop_loss=params.stop_loss,
            min_holding_period=getattr(params, "min_holding_period", 0),
            trailing_stop_pct=getattr(params, "trailing_stop_pct", TRAILING_STOP_PERCENT),
            use_base_ema=use_base_ema_filter,  # ✅ 파라미터 설정 반영
            base_ema_gap_enabled=getattr(params, "base_ema_gap_enabled", False),  # ✅ Base EMA GAP 전략 활성화
            base_ema_gap_diff=getattr(params, "base_ema_gap_diff", -0.005),  # ✅ Base EMA GAP 임계값
            ema_surge_filter_enabled=getattr(params, "ema_surge_filter_enabled", False),  # ✅ 급등 필터 활성화
            ema_surge_threshold_pct=getattr(params, "ema_surge_threshold_pct", 0.01),  # ✅ 급등 임계값
            buy_conditions=buy_conditions,  # ✅ 조건 파일 전달 (BUY)
            sell_conditions=sell_conditions,  # ✅ 조건 파일 전달 (SELL)
        )

        logger.info(f"[EMA 전략] use_base_ema={use_base_ema_filter}")
        # ✅ WO-26: 기동 시 설정 키와 적용값 1줄 (파일에 없는 키는 config 기본값, * 표시)
        try:
            logger.info(_config_applied_line(buy_conditions, sell_conditions))
        except Exception as e:
            logger.warning(f"[CONFIG] 적용값 로그 실패: {e}")
    elif strategy_tag == "PULLBACK":
        # 2차 T5: 적용본 dict 로 전략 생성. StrategyEngine(strategy=...) 로 넘어가므로 워밍업 시드(_pullback_seed_warmup)
        # 전에 engine.strategy 가 이 전략이다(T4 넘김 1 — 순서가 반대면 기동 첫 봉 GOLDEN 매수, 결정 13-4 위반).
        from core.strategy_pullback import IncrementalPullbackStrategy
        _pb_interval = params.interval
        strategy = IncrementalPullbackStrategy(
            user_id=user_id,
            ticker=params.upbit_ticker,
            params=pullback_cfg,
            interval_min=int(_pb_interval.replace("minute", "")) if _pb_interval.startswith("minute") else 1,
        )
        logger.info(
            "[PULLBACK-STRATEGY] 생성 | " + " ".join(
                f"{k}={pullback_cfg.get(k)}" for k in ("ticker", "interval", "maType", "ma60p", "ma200p",
                                                       "pullbackP", "maxSplits", "eff_max_splits", "tp", "sl")
            )
        )
    else:
        raise ValueError(f"Unknown strategy type: {strategy_tag}")

    # ✅ interval_min 계산 (minute1 → 1, minute3 → 3 등)
    interval_str = params.interval  # e.g., "minute1", "minute3"
    if interval_str.startswith("minute"):
        interval_min = int(interval_str.replace("minute", ""))
    else:
        # 다른 interval 형식 처리 (기본값 1분)
        logger.warning(f"Unknown interval format: {interval_str}, using default 1min")
        interval_min = 1

    # ✅ EMA 전략에 interval_min 전달
    if strategy_tag == "EMA" and hasattr(strategy, 'set_interval_min'):
        strategy.set_interval_min(interval_min)
        logger.info(f"[EMA Strategy] interval_min={interval_min} 전달 완료")

    # StrategyEngine 생성
    engine = StrategyEngine(
        buffer=buffer,
        indicators=indicators,
        position=position,
        strategy=strategy,
        trader=trader,
        user_id=user_id,
        ticker=params.upbit_ticker,
        strategy_type=strategy_tag,
        q=q,
        interval_sec=getattr(params, "interval_sec", 60),
        take_profit=params.take_profit,
        stop_loss=params.stop_loss,
        trailing_stop_pct=getattr(params, "trailing_stop_pct", TRAILING_STOP_PERCENT),
    )

    logger.info("✅ StrategyEngine 초기화 완료 (CandleBuffer + IndicatorState + PositionState)")

    # ============================================================
    # 2단계: 워밍업 (초기 시드)
    # ============================================================

    min_hist = _min_history_bars_for(params, strategy_tag)

    # ✅ Base EMA GAP 모드: period × 2 데이터 요청
    # - 200-period MA를 안정적으로 계산하려면 period × 2 필요
    if strategy_tag == "EMA" and getattr(params, "base_ema_gap_enabled", False):
        base_period = getattr(params, "base_ema_period", 200)
        min_hist = max(min_hist, base_period * 2)
        logger.info(f"[WARMUP] Base EMA GAP 모드: {base_period} × 2 = {min_hist}개 요청")

    # 2차 T3: PULLBACK 워밍업 봉 수 = required_bars (D8·F5). EMA·MACD 는 위 식 그대로.
    if strategy_tag == "PULLBACK":
        min_hist, _pb_long_bars = _pullback_warmup_bars(pullback_cfg)
        logger.info(f"[WARMUP] PULLBACK required_bars={min_hist} long_bars={_pb_long_bars}")

    warmup_complete = False

    logger.info(f"[WARMUP] Required bars: {min_hist}")

    # ✅ 설정 스냅샷 1분 타이머 (봉과 무관하게 독립 동작)
    # ✅ SP5 Hot Reload — conditions mtime 변경 감지 → strategy.reload_conditions 호출
    _hot_reload_state: Dict[str, Any] = {"last_mtime": None}

    def _settings_snapshot_timer():
        """
        1분마다 설정 스냅샷 기록 + conditions mtime 변경 감지 → strategy 핫리로드.

        ✅ 2026-08-05 재구성 (옵션 A+B):
        - mtime 감지는 5초 tick 마다 (기존 분당 1회 → 최대 5초 지연).
        - hot-reload 트리거 시 즉시 스냅샷 발행 (UPSERT 로 정기 스냅샷 갱신).
        - 정기 분 스냅샷은 기존과 동일 (기본 관찰성 유지).
        """
        last_minute: Optional[str] = None

        def _do_snapshot(current_minute):
            """스냅샷 실행 공용 헬퍼 — 정기 분 tick + hot-reload 직후 재사용."""
            if strategy_tag == "PULLBACK":  # 2차 T5: 조건 파일 안 읽음, tp·sl 은 적용본(전략 객체)
                return _pullback_do_snapshot(engine, params, user_id, current_minute)
            _trade_conditions = _load_trade_conditions(user_id, strategy_tag)
            # ✅ FIX(diag-1) — audit_settings 는 strategy 객체의 실제 운영 임계값을 적재.
            _eng_strat = getattr(engine, "strategy", None)
            _eng_tp = getattr(_eng_strat, "take_profit", None) if _eng_strat else None
            _eng_sl = getattr(_eng_strat, "stop_loss", None) if _eng_strat else None
            _eng_ts = getattr(_eng_strat, "trailing_stop_pct", None) if _eng_strat else None
            insert_settings_snapshot(
                user_id=user_id,
                ticker=params.upbit_ticker,
                interval_sec=getattr(params, "interval_sec", 60),
                tp=_eng_tp if _eng_tp is not None else params.take_profit,
                sl=_eng_sl if _eng_sl is not None else params.stop_loss,
                ts_pct=_eng_ts if _eng_ts is not None else getattr(params, "trailing_stop_pct", None),
                signal_gate=getattr(params, "signal_confirm_enabled", False),
                threshold=getattr(params, "macd_threshold", 0.0),
                buy_dict=_trade_conditions.get("buy", {}),
                sell_dict=_trade_conditions.get("sell", {}),
                bar_time=current_minute,
            )
            return _trade_conditions

        while not stop_event.is_set():
            try:
                current_minute = now_kst_minute()

                # ── 정기 분 tick 스냅샷 (기존 동작 유지) ──
                if last_minute != current_minute:
                    _do_snapshot(current_minute)
                    last_minute = current_minute
                    logger.info(f"[SETTINGS-SNAPSHOT] ✅ Recorded at {current_minute}")

                # ── ✅ 옵션 B: mtime 감지를 5초 tick 밖으로 이동 (분당 → 초당) ──
                # ── ✅ 옵션 A: mtime 변경 감지 시 즉시 스냅샷 (UPSERT 로 정기 갱신) ──
                try:
                    _cond_path = None if strategy_tag == "PULLBACK" else _get_trade_conditions_path(user_id, strategy_tag)  # 2차 T5: PULLBACK 핫 리로드 없음 (T13 적용본 감시가 대신)
                    if _cond_path and os.path.exists(_cond_path):
                        _mtime = os.path.getmtime(_cond_path)
                        _last_mtime = _hot_reload_state["last_mtime"]
                        if _last_mtime is None:
                            # 최초 호출 — strategy init 시점 mtime 으로 간주
                            _hot_reload_state["last_mtime"] = _mtime
                        elif _mtime != _last_mtime:
                            _hot_conditions = _load_trade_conditions(user_id, strategy_tag)
                            _hot_buy = _hot_conditions.get("buy", {}) or {}
                            _hot_sell = _hot_conditions.get("sell", {}) or {}
                            _reload_result = engine.strategy.reload_conditions(
                                _hot_buy, _hot_sell
                            )
                            if _reload_result.get("changed"):
                                _changes = _reload_result["changed"]
                                _change_summary = ", ".join(
                                    f"{k}: {v[0]!r}→{v[1]!r}" for k, v in _changes.items()
                                )
                                logger.warning(
                                    f"🔄 [HOT-RELOAD] strategy 갱신 완료 | {_change_summary}"
                                )
                                # 활성 포지션 보유 중 Telegram CRITICAL (D7 결정 ii)
                                _in_position = bool(
                                    getattr(engine.position, "has_position", False)
                                )
                                if _in_position:
                                    try:
                                        from services.notifier import send as _notify, LEVEL_CRITICAL
                                        _notify(
                                            LEVEL_CRITICAL,
                                            f"🚨 [HOT-RELOAD] 운영 중 conditions 변경 — {user_id}",
                                            (
                                                f"활성 포지션 보유 중 → TP/SL 즉시 새 임계로 적용됩니다.\n"
                                                f"변경 항목:\n{_change_summary}\n\n"
                                                f"의도하지 않은 변경이라면 대시보드에서 즉시 원복 저장 권장."
                                            ),
                                            dedupe_key=f"hot_reload:{user_id}:{int(_mtime)}",
                                            dedupe_ttl=60,
                                        )
                                    except Exception:
                                        pass
                            # ✅ 옵션 A: hot-reload 감지 시 changes 유무 무관 즉시 스냅샷
                            #    (파일 mtime 은 변경됐으므로 UI 저장 이벤트로 간주,
                            #     UPSERT 로 같은 분 정기 스냅샷을 새 값으로 갱신)
                            _do_snapshot(current_minute)
                            logger.info(
                                f"[SETTINGS-SNAPSHOT] ⚡ Hot-reload triggered snapshot at {current_minute}"
                            )
                            _hot_reload_state["last_mtime"] = _mtime
                except Exception as _hot_e:
                    logger.warning(f"[HOT-RELOAD] failed: {_hot_e}")
            except Exception as e:
                logger.warning(f"[SETTINGS-SNAPSHOT] ❌ Failed: {e}")

            time.sleep(5)

    snapshot_thread = threading.Thread(target=_settings_snapshot_timer, daemon=True)
    snapshot_thread.start()
    logger.info("✅ [SETTINGS-SNAPSHOT] Timer thread started")

    # ============================================================
    # 3단계: 라이브 루프 (증분 처리)
    # ============================================================

    # ✅ 이전 yield에서 처리한 마지막 봉의 timestamp 추적 (합성 봉 누락 방지)
    last_processed_ts = None

    # ✅ WARMUP 루프 동안 이전 yield의 마지막 봉 추적 (WARMUP 완료 시 새 봉 감지용)
    prev_warmup_last_ts = None

    # ✅ 중복 평가 방지: 이미 처리된 봉의 timestamp를 Set으로 추적
    # - DataFrame 재구성 시에도 중복 평가 방지
    # - DB 캐시 병합 후에도 안전
    processed_bar_timestamps = set()

    # 🚀 운영 모드 분기: UPBIT_MATCH vs LEGACY_LOCAL
    logger.info(f"🚀 [RUN_MODE] {RUN_MODE} | CANDLE_TRUTH={CANDLE_TRUTH} | WS_ROLE={WS_ROLE}")

    try:
        if RUN_MODE == "UPBIT_MATCH":
            # ========================================================
            # 🚀 Clock-based REST Reconcile Loop (UPBIT_MATCH 모드)
            # ========================================================
            logger.info("🚀 [UPBIT_MATCH] Clock-based REST Reconcile 모드 시작")

            # CandleClock 초기화
            clock = CandleClock(params.interval)
            logger.info(f"✅ CandleClock 초기화 | interval={params.interval} | interval_sec={clock.interval_sec}")

            # ============================================================
            # WO-2026-001 Task 2-A: CandleValidator 초기화
            # ============================================================
            candle_validator = CandleValidator(max_spike_ratio=0.05)
            logger.info("✅ CandleValidator 초기화 | max_spike_ratio=5%")

            # 로컬 시계열 (Reconcile 누적용)
            local_series = pd.DataFrame()

            # ============================================================
            # Warmup: 초기 REST 데이터 로드 (재시도 로직 포함)
            # ============================================================
            MAX_WARMUP_RETRIES = 5
            initial_df = None
            # ✅ WO-17 (S): 첫 시도는 긴 이력(LONG_SEED_BARS + 1) 요청. 실패하면 이후 시도는 현행(min_hist + 1)
            _long_bars = max(LONG_SEED_BARS, min_hist)
            if strategy_tag == "PULLBACK":
                _long_bars = _pb_long_bars
            _seed_fallback_reason = ""

            for attempt in range(1, MAX_WARMUP_RETRIES + 1):
                # WO-2026-001 Task 1-B: +1개 요청 후 마지막 봉 제거 (현재 진행 중 봉 방지)
                warmup_request = (_long_bars + 1) if attempt == 1 else (min_hist + 1)
                if attempt == 2 and not _seed_fallback_reason:
                    _seed_fallback_reason = "fetch_failed"
                logger.info(f"[WARMUP] REST 초기 데이터 요청 (attempt {attempt}/{MAX_WARMUP_RETRIES}) | count={warmup_request} (마지막 봉 제거 예정)...")
                initial_df = safe_fetch_rest(
                    market=params.upbit_ticker,
                    timeframe=params.interval,
                    end_ts=None,  # ✅ to 파라미터 없음
                    total_count=warmup_request
                )

                if initial_df is not None and not initial_df.empty:
                    logger.info(f"✅ [WARMUP] REST 데이터 로드 성공 (attempt {attempt}) | bars={len(initial_df)}")
                    break

                if attempt < MAX_WARMUP_RETRIES:
                    wait_sec = 2 ** attempt  # 2, 4, 8, 16, 32초
                    logger.warning(f"⚠️ [WARMUP] 실패, {wait_sec}초 후 재시도... ({attempt}/{MAX_WARMUP_RETRIES})")
                    time.sleep(wait_sec)
            else:
                # 5회 모두 실패 → 심각한 상황, 하지만 봇 전체 종료는 피함
                logger.error("❌ [WARMUP] 5회 연속 실패 → LEGACY_LOCAL 모드로 fallback 권장")
                logger.error("❌ [WARMUP] RUN_MODE를 'LEGACY_LOCAL'로 변경하거나 네트워크/API 상태를 확인하세요")
                raise RuntimeError("REST Warmup failed after 5 retries - cannot start UPBIT_MATCH mode")

            if initial_df is None or initial_df.empty:
                logger.error("❌ [WARMUP] REST 초기 데이터 로드 실패")
                raise RuntimeError("REST Warmup failed - cannot start without initial data")

            logger.info(f"✅ [WARMUP] REST 데이터 로드 완료 | bars={len(initial_df)}")

            # ============================================================
            # WO-2026-001 Task 1-B: 마지막 봉 제거 (현재 진행 중 봉 방지)
            # ✅ WO-16 (W): 개수 여유가 아니라 시각으로 판정 — 형성 중일 때만 제거, 확정 봉은 유지
            # ============================================================
            # ✅ 워밍업은 to 없이 조회하므로 현재 진행 중인 봉을 포함할 수 있음
            initial_df, _wu_action, _wu_last, _wu_elapsed = _warmup_trim_forming(
                initial_df,
                CandleClock.TIMEFRAME_SEC.get(params.interval, 60),
                now_utc(),
                min_hist,
            )
            if _wu_action == "dropped":
                logger.info(
                    f"[WARMUP] 형성 중 봉 제거 | ts={format_kst(_wu_last)} elapsed={_wu_elapsed}s | "
                    f"최종 봉 수={len(initial_df)} | "
                    f"최종 마지막 봉={format_kst(initial_df.index[-1])}"
                )
            elif _wu_action == "kept_confirmed":
                logger.info(
                    f"[WARMUP] 마지막 봉 확정 (유지) | ts={format_kst(_wu_last)} | 봉 수={len(initial_df)}"
                )
            else:
                logger.warning(
                    f"[WARMUP] 형성 중 봉 유지 (봉 수 부족) | ts={format_kst(_wu_last)} elapsed={_wu_elapsed}s | "
                    f"bars={len(initial_df)} min_hist={min_hist}"
                )
            # 2차 T3: PULLBACK 은 형성 중 봉을 늘 빼고, 받은 봉 < required_bars 이면 CRITICAL 뒤 기동 거부 (200봉 SMA 폴백 없음)
            if strategy_tag == "PULLBACK":
                _pb_received = len(initial_df)
                initial_df = _pullback_warmup_gate(
                    initial_df, _wu_action, min_hist,
                    holding=_pullback_holding(engine.position, boot_seed_recover_qty),
                    user_id=user_id, ticker=params.upbit_ticker,
                )
                if initial_df is None:
                    raise RuntimeError(f"PULLBACK warmup insufficient: received={_pb_received} required={min_hist}")
            if len(initial_df) < min_hist:
                # 부족하면 에러
                logger.error(
                    f"❌ [WARMUP] 데이터 부족 | "
                    f"received={len(initial_df)} < min_hist={min_hist}"
                )
                raise RuntimeError(f"Insufficient warmup data: {len(initial_df)} < {min_hist}")

            # ✅ WO-21: trailing 재계산용으로 워밍업 전체 봉(최대 800, 형성 중 봉 제거 뒤)을 보관 — 시드가 min_hist 로 자르기 전
            _wu_full_df = initial_df

            # 지표 시드
            # ✅ WO-17 (S): 긴 이력 증분 시드 (실패·부족 시 200봉 SMA 폴백), 버퍼·local_series 는 최근 min_hist 봉
            if strategy_tag == "PULLBACK":
                _seed_ok, _seed_mode, _reason, initial_df = _pullback_seed_warmup(
                    engine, initial_df, pullback_cfg, candle_validator
                )
            else:
                _seed_ok, _seed_mode, _reason, initial_df = _seed_warmup_indicators(
                    indicators, initial_df, _long_bars, min_hist
                )
            if _seed_ok and _seed_mode == "long_history":
                logger.info(
                    f"[WARMUP] 시드 방식=long_history bars={_long_bars} "
                    f"ema_fast={indicators.ema_fast_buy if indicators.use_separate_ema else indicators.ema_fast:.4f} "
                    f"ema_slow={indicators.ema_slow_buy if indicators.use_separate_ema else indicators.ema_slow:.4f} "
                    f"ema_base={indicators.ema_base:.4f} | 마지막 봉={format_kst(initial_df.index[-1])} | "
                    f"직전 D/C={format_kst(indicators.last_dead_cross_ts) if indicators.last_dead_cross_ts is not None else f'없음({_long_bars}봉 안)'}"
                )
            elif _seed_ok and _seed_mode != "pullback":  # 2차 T3: PULLBACK 시드는 폴백 경고 대상 아님
                _why = _seed_fallback_reason or _reason
                logger.warning(f"[WARMUP] 긴 이력 시드 실패 → 200봉 SMA 폴백 | 사유={_why}")
                logger.info(f"[WARMUP] 시드 방식=sma200 bars={len(initial_df)}"
                            f" | 직전 D/C 알 수 없음 → 약매수 판정 안 함(일반 매수)")  # ✅ WO-26 결정 3 (같은 줄)
                try:
                    from services.notifier import send as _notify, LEVEL_WARNING
                    _notify(
                        LEVEL_WARNING,
                        f"⚠️ 지표 시드 폴백 — {params.upbit_ticker}",
                        (
                            f"워밍업에서 긴 이력({_long_bars}봉) 시드를 쓰지 못해 200봉 SMA 시드로 시작했습니다.\n"
                            f"사유: {_why}\n"
                            f"매매는 정상 진행됩니다. 기동 직후 지표가 장기 기준과 다를 수 있습니다."
                        ),
                        dedupe_key=f"warmup_seed_fallback:{user_id}:{params.upbit_ticker}",
                        dedupe_ttl=3600,
                    )
                except Exception:
                    pass
            if _seed_ok:
                warmup_complete = True
                logger.info(f"✅ Warmup 완료 | bars={len(initial_df)}")

                # 버퍼 채우기
                _wu_audit = {}  # ✅ WO-19: 워밍업 감사 행 결과 집계 (kept / inserted / updated_placeholder)
                for idx, row in initial_df.iterrows():
                    bar = Bar(
                        ts=idx,
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume'],
                        is_closed=True
                    )
                    buffer.append(bar)
                    engine.bar_count = len(buffer)
                    current_count = min(len(buffer), min_hist)
                    _wu_progress = (_pullback_warmup_progress(engine, min_hist, len(buffer)) if strategy_tag == "PULLBACK"
                                    else f"(완료 {current_count}/{min_hist})")  # 2차 T5: PULLBACK 은 지표 봉 수 기준 문구
                    _wu_res = engine.record_warmup_log(bar, _wu_progress)
                    _wu_audit[_wu_res] = _wu_audit.get(_wu_res, 0) + 1  # ✅ WO-19 집계

                # ✅ WO-19: 기동마다 1줄 — 워밍업이 실제 판정 감사 행을 보존했는지
                logger.info(
                    f"[WARMUP] 감사 행 보존 | kept={_wu_audit.get('kept', 0)} "
                    f"inserted={_wu_audit.get('inserted', 0)} "
                    f"updated_placeholder={_wu_audit.get('updated_placeholder', 0)}"
                    + (f" failed={_wu_audit[None]}" if _wu_audit.get(None) else "")
                )

                engine.last_bar_ts = initial_df.index[-1]
                local_series = initial_df.copy()

                logger.info(f"✅ Buffer seeded | buffer_len={len(buffer)} | bar_count={engine.bar_count}")
                if strategy_tag == "PULLBACK":  # 2차 T5: 버퍼 500봉은 감사·대조용, 지표는 별도 deque
                    logger.info(f"[WARMUP] PULLBACK 지표 봉 {engine.pullback_indicators.n} (필요 {min_hist}) · "
                                f"링 {len(engine.pullback_ring)} · 버퍼 {len(buffer)}(감사·대조용, 지표 봉 수 아님)")
                # ✅ WO-12 C7: 워밍업(bar_count 확정) 직후 지갑 기준 즉시 복원 — 첫 봉 [POSITION-SYNC] 와 같은 시점 조건
                if boot_seed_recover_qty is not None:
                    _boot_seed_recover_from_wallet(engine, params.upbit_ticker, user_id, boot_seed_recover_qty)
                    boot_seed_recover_qty = None
                # ✅ WO-21: 복원 2경로(boot_seed / wallet_sync) 뒤, 첫 매도 평가 전 1회 — trailing 상태 재계산
                # 2차 T5: PULLBACK 은 트레일링 스톱을 쓰지 않으므로 건너뜀
                if engine.position.has_position and strategy_tag != "PULLBACK":
                    try:
                        from core.trailing_restore import restore_trailing_on_boot
                        restore_trailing_on_boot(
                            engine.position, engine.strategy,
                            user_id=user_id, ticker=params.upbit_ticker, timeframe=params.interval,
                            interval_sec=params.interval_sec, warmup_df=_wu_full_df,
                        )
                    except Exception as _tr_e:
                        logger.warning(f"[TRAILING-RESTORE] 재계산 불가 → 초기화 | 사유=예외 {_tr_e}")
            else:
                logger.error("❌ [WARMUP] Indicator seed 실패")
                raise RuntimeError("Indicator warmup failed")

            # ============================================================
            # Clock-based 폴링 루프
            # ============================================================
            logger.info("🚀 [CLOCK-LOOP] 시작 - 1초마다 폴링, 봉 확정 시 REST Reconcile")

            # ✅ B7: 조건 파일 mtime 추적 (set_config 변경 무중단 반영)
            # NOTE: params.json은 live_loop 스코프에 경로 변수가 없어 본 경로에서 추적 안 함.
            #       지표 구조 변경은 엔진 재시작 정책.
            _params_mtime = {"conditions": 0.0}
            try:
                _cond_path = None if strategy_tag == "PULLBACK" else _get_trade_conditions_path(user_id, params.strategy_type)  # 2차 T5: PULLBACK 은 _maybe_reload_params 무동작
                if _cond_path and os.path.exists(_cond_path):
                    _params_mtime["conditions"] = os.path.getmtime(_cond_path)
            except Exception:
                _cond_path = None

            while not stop_event.is_set():
                now = now_utc()

                if clock.should_close(now):
                    closed_ts = clock.get_closed_ts(now)

                    # ✅ B7: 봉 확정 시점에 조건 파일 mtime 확인 → 변경 시 무중단 reload 시도
                    try:
                        _params_mtime = _maybe_reload_params(
                            user_id=user_id,
                            params_ref=params,
                            strategy=strategy,
                            cond_path=_cond_path,
                            mtime_state=_params_mtime,
                        )
                    except Exception as _e:
                        logger.warning(f"[PARAMS-RELOAD] mtime check failed: {_e}")

                    # 이미 처리한 봉인지 확인 (중복 방지)
                    if closed_ts <= engine.last_bar_ts:
                        logger.debug(f"[CLOCK] 이미 처리된 봉 스킵 | closed={closed_ts} <= last={engine.last_bar_ts}")
                        time.sleep(1)
                        continue

                    logger.info(f"⏰ [CLOCK-CLOSE] 봉 확정 감지 | ts={format_kst(closed_ts)}")

                    # ✅ Upbit API finalization 대기 (data_feed.py와 동일한 Jitter 로직)
                    jitter = JITTER_BY_INTERVAL.get(params.interval, 8.0)
                    logger.debug(f"[JITTER] {jitter}초 대기 (Upbit API finalization)")
                    time.sleep(jitter)

                    # REST에서 최신 데이터 fetch (Reconcile용)
                    if RECONCILE_ON_EVERY_CLOSE:
                        logger.info(f"🔄 [REST-RECONCILE] Fetching {RECONCILE_LOOKBACK_BARS} bars from REST...")

                        # ✅ WO-2026-001 Task 1-A + Issue #8 강화: 최신 봉 확정 검증
                        # closed_ts 봉을 별도로 조회하여 확정 종가만 반환 보장
                        # Progressive Retry: interval의 50% 시간만 사용 (다음 봉 놓치지 않도록)
                        # - 1분봉: 최대 27초 (5회)
                        # - 3분봉: 최대 87초 (17회)
                        confirmed_row = fetch_confirmed_candle(
                            ticker=params.upbit_ticker,
                            timeframe=params.interval,
                            closed_ts=closed_ts
                            # max_retry는 자동 계산 (interval 기반)
                        )

                        # 과거 데이터는 safe_fetch_rest로 조회 (이미 확정됨)
                        rest_df = safe_fetch_rest(
                            market=params.upbit_ticker,
                            timeframe=params.interval,
                            end_ts=closed_ts,  # ✅ closed_ts 기준 (최신 봉 포함)
                            total_count=RECONCILE_LOOKBACK_BARS
                        )

                        # ✅ WO-6 (2026-08-25): 확정 봉 결과 분기
                        # - NO_TRADE 표지: 대상 봉 자체가 무거래. rest_df 그대로 유지, 지표 미반영, BACKFILL 위임 없음.
                        # - pd.Series: 정상 확정. rest_df 덮어쓰기.
                        # - None: 재시도 초과. Reconcile 계속 진행 (기존 흐름).
                        # ✅ WO-6 보완 F1 (2026-08-26): NO_TRADE 시 후속 RETRY 스킵 플래그.
                        no_trade_this_bar = False
                        if confirmed_row is NO_TRADE:
                            logger.info(
                                f"⏭ [CONFIRMED-NO-TRADE] closed_ts={format_kst(closed_ts)} "
                                f"무거래 봉 → Reconcile 계속 (지표 미반영, 봉 건너뜀)"
                            )
                            no_trade_this_bar = True
                            # rest_df 그대로 유지. 무거래 봉은 지표에 넣지 않음.
                        elif confirmed_row is not None and rest_df is not None:
                            if closed_ts in rest_df.index:
                                # rest_df의 closed_ts 봉을 fetch_confirmed_candle 결과로 덮어쓰기
                                original_close = rest_df.loc[closed_ts, 'Close']
                                rest_df.loc[closed_ts] = confirmed_row
                                new_close = rest_df.loc[closed_ts, 'Close']

                                if abs(original_close - new_close) > 0.01:
                                    logger.warning(
                                        f"[CONFIRMED-FIX] 최신 봉 종가 보정 | ts={format_kst(closed_ts)} | "
                                        f"미확정={original_close:.0f} → 확정={new_close:.0f}"
                                    )
                            else:
                                # rest_df에 closed_ts 없으면 추가
                                logger.warning(f"[CONFIRMED-ADD] closed_ts={format_kst(closed_ts)} 추가")
                                rest_df = pd.concat([rest_df, confirmed_row.to_frame().T]).sort_index()
                        elif confirmed_row is None:
                            logger.error(f"❌ [CONFIRMED] closed_ts={format_kst(closed_ts)} 조회 실패 → Reconcile 계속 (미확정 종가 사용 가능)")

                        # ✅ WO-14 (b): 로컬 시작 이전 봉은 누락 후보에서 제외
                        rest_df, _n_before_local = _trim_rest_before_local_start(local_series, rest_df)
                        if _n_before_local > 0:
                            logger.info(
                                f"[RECONCILE] 로컬 시작 이전 봉 제외 | n={_n_before_local} "
                                f"local_start={format_kst(local_series.index[0])}"
                            )

                        # Reconcile: REST vs Local
                        merged, diff_summary = reconcile_series(local_series, rest_df)

                        # ✅ High-Risk Fix: local_series 크기 제한 (메모리 누수 방지)
                        MAX_LOCAL_SERIES_LEN = 500
                        if len(merged) > MAX_LOCAL_SERIES_LEN:
                            local_series = merged.tail(MAX_LOCAL_SERIES_LEN)
                            logger.debug(f"[MEMORY] local_series 크기 제한 | {len(merged)} → {MAX_LOCAL_SERIES_LEN}")
                        else:
                            local_series = merged

                        rest_failed = diff_summary.get("rest_failed", False)
                        changed_count = diff_summary.get("changed_count", 0)

                        if rest_failed:
                            logger.warning(f"⚠️ [REST-RECONCILE] REST 실패 → Fallback to Local")
                        elif changed_count > 0:
                            msg = f"🔄 [REST-RECONCILE] {changed_count}개 봉 변경 감지 (지표는 증분만)"  # ✅ WO-17 (P)
                            logger.info(msg)
                            log_to_file(msg, user_id)

                            # 🔄 누락된 봉 backfill (새로 추가된 봉에 대해 감사 로그 기록)
                            changed_ts_list = diff_summary.get("changed_ts", [])
                            # 현재 봉은 제외하고 과거 봉만 backfill
                            # ✅ reconcile_series가 이미 local_series에 누락 봉을 병합했으므로
                            # changed_ts에 있는 모든 봉(누락+변경)을 처리해야 함
                            backfill_ts_list = [ts for ts in changed_ts_list if ts != closed_ts]
                            # ✅ WO-14 (a): 확정 대상 봉보다 늦은 봉(형성 중)은 제외
                            backfill_ts_list, _unconfirmed_ts = _drop_unconfirmed_backfill_ts(backfill_ts_list, closed_ts)
                            for _uts in _unconfirmed_ts:
                                logger.info(
                                    f"[BACKFILL] 미확정 봉 제외 | ts={format_kst(_uts)} "
                                    f"closed_ts={format_kst(closed_ts)}"
                                )

                            # 2차 T3 (F15): PULLBACK 은 봉별 루프 대신 링 버퍼 재생 1회. 빈 목록이 돌아와 아래 봉별 루프를 건너뛴다.
                            if strategy_tag == "PULLBACK" and backfill_ts_list:
                                backfill_ts_list = _pullback_backfill_step(
                                    engine, backfill_ts_list, local_series, closed_ts, user_id, candle_validator
                                )

                            if backfill_ts_list:
                                msg = f"🔄 [BACKFILL] {len(backfill_ts_list)}개 누락 봉 평가 시작"
                                logger.info(msg)
                                log_to_file(msg, user_id)

                                # ✅ WO-1 추가 C 설계 제약 #1: 백업 dict 생성은 try 밖에서 완성.
                                # 백업 도중 예외 발생 시 BACKFILL 자체가 중단되므로 (상위 while 의 except 로 이동)
                                # finally 진입 자체가 발생하지 않아 오염 상태 방지. saved_indicators 미정의 참조 위험 원천 봉쇄.
                                # Issue #11: BACKFILL 이 실시간 지표를 오염시키지 않도록 prev 상태 보존.
                                saved_indicators = {
                                    'ema_fast': engine.indicators.ema_fast,
                                    'ema_slow': engine.indicators.ema_slow,
                                    'ema_base': engine.indicators.ema_base,
                                    'prev_ema_fast': engine.indicators.prev_ema_fast,
                                    'prev_ema_slow': engine.indicators.prev_ema_slow,
                                    'macd': engine.indicators.macd,
                                    'signal': engine.indicators.signal,
                                    'hist': engine.indicators.hist,
                                    'prev_macd': engine.indicators.prev_macd,
                                    'prev_signal': engine.indicators.prev_signal,
                                }
                                if engine.indicators.use_separate_ema:
                                    saved_indicators.update({
                                        'ema_fast_buy': engine.indicators.ema_fast_buy,
                                        'ema_slow_buy': engine.indicators.ema_slow_buy,
                                        'ema_fast_sell': engine.indicators.ema_fast_sell,
                                        'ema_slow_sell': engine.indicators.ema_slow_sell,
                                        'prev_ema_fast_buy': engine.indicators.prev_ema_fast_buy,
                                        'prev_ema_slow_buy': engine.indicators.prev_ema_slow_buy,
                                        'prev_ema_fast_sell': engine.indicators.prev_ema_fast_sell,
                                        'prev_ema_slow_sell': engine.indicators.prev_ema_slow_sell,
                                    })
                                saved_indicators.update(_backup_dead_cross_ts(engine.indicators))  # ✅ WO-26

                                # ✅ WO-14 E1: Trailing 상태 백업 (BACKFILL 은 포지션 상태를 바꾸지 않음)
                                saved_trailing = _backup_trailing_state(engine.position)

                                # ✅ WO-1 추가 A: 백업 로그 debug → info 승격 (프로덕션 감시)
                                prev_fast_str = f"{saved_indicators['prev_ema_fast']:.2f}" if saved_indicators['prev_ema_fast'] is not None else "None"
                                prev_slow_str = f"{saved_indicators['prev_ema_slow']:.2f}" if saved_indicators['prev_ema_slow'] is not None else "None"
                                logger.info(
                                    f"[BACKFILL] 지표 상태 백업 | "
                                    f"prev_ema_fast={prev_fast_str} "
                                    f"prev_ema_slow={prev_slow_str}"
                                )

                                try:
                                    for ts in sorted(backfill_ts_list):
                                        try:
                                            row = local_series.loc[ts]

                                            # 봉 검증
                                            valid, reason = candle_validator.validate(row)
                                            if not valid:
                                                logger.warning(f"[BACKFILL] 봉 검증 실패 | ts={format_kst(ts)} | {reason}")
                                                continue

                                            # Bar 객체 생성
                                            bar = Bar(
                                                ts=ts,
                                                open=row['Open'],
                                                high=row['High'],
                                                low=row['Low'],
                                                close=row['Close'],
                                                volume=row['Volume'],
                                                is_closed=True,
                                                is_confirmed=True,
                                                source="REST_BACKFILL"
                                            )

                                            # 감사 로그만 기록 (실제 매매는 하지 않음)
                                            msg = f"🔄 [BACKFILL] 누락 봉 평가 | ts={format_kst(ts)} | close={bar.close:.0f}"
                                            logger.info(msg)
                                            log_to_file(msg, user_id)

                                            # backfill_mode 플래그 추가하여 전략 엔진에서 실제 매매를 하지 않도록 함
                                            backfill_diff_summary = {
                                                "rest_failed": False,
                                                "changed_count": 0,
                                                "changed_ts": [],
                                                "backfill_mode": True  # 실제 매매 금지 플래그
                                            }
                                            engine.on_new_bar_confirmed(bar, local_series, backfill_diff_summary)

                                        except Exception as e:
                                            logger.error(f"[BACKFILL] 봉 평가 실패 | ts={format_kst(ts)} | {e}")
                                            continue

                                    msg = f"✅ [BACKFILL] {len(backfill_ts_list)}개 누락 봉 평가 완료"
                                    logger.info(msg)
                                    log_to_file(msg, user_id)
                                finally:
                                    # ✅ WO-1 추가 C 설계 제약 #2: 복원은 finally 안, 자체 예외 처리 (silent continue 금지)
                                    # Issue #11: BACKFILL 처리 중 변경된 지표를 원래 상태로 복원 → 다음 실시간 봉 크로스 감지 보장
                                    # ✅ WO-14 E1: Trailing 상태 복원 (과거 누락 봉 가격은 고점에 반영하지 않음)
                                    try:
                                        _trail_changed = _restore_trailing_state(engine.position, saved_trailing)
                                        if _trail_changed is None:
                                            logger.warning(
                                                "[BACKFILL] trailing 상태 복원 건너뜀 | BACKFILL 중 보유 여부 변경"
                                            )
                                        elif _trail_changed:
                                            _hp = _trail_changed.get("highest_price")
                                            _head = f"highest {_hp[0]}→{_hp[1]} 되돌림" if _hp else "highest 변화 없음"
                                            _rest = " ".join(
                                                f"{k}={v[0]}→{v[1]}" for k, v in _trail_changed.items()
                                                if k != "highest_price"
                                            )
                                            logger.info(
                                                f"[BACKFILL] trailing 상태 복원 | {_head}"
                                                + (f" | {_rest}" if _rest else "")
                                            )
                                    except Exception as _trail_exc:
                                        logger.error(f"[BACKFILL] ❌ trailing 상태 복원 실패 | {_trail_exc}", exc_info=True)
                                    try:
                                        engine.indicators.ema_fast = saved_indicators['ema_fast']
                                        engine.indicators.ema_slow = saved_indicators['ema_slow']
                                        engine.indicators.ema_base = saved_indicators['ema_base']
                                        engine.indicators.prev_ema_fast = saved_indicators['prev_ema_fast']
                                        engine.indicators.prev_ema_slow = saved_indicators['prev_ema_slow']
                                        engine.indicators.macd = saved_indicators['macd']
                                        engine.indicators.signal = saved_indicators['signal']
                                        engine.indicators.hist = saved_indicators['hist']
                                        engine.indicators.prev_macd = saved_indicators['prev_macd']
                                        engine.indicators.prev_signal = saved_indicators['prev_signal']

                                        if engine.indicators.use_separate_ema:
                                            engine.indicators.ema_fast_buy = saved_indicators['ema_fast_buy']
                                            engine.indicators.ema_slow_buy = saved_indicators['ema_slow_buy']
                                            engine.indicators.ema_fast_sell = saved_indicators['ema_fast_sell']
                                            engine.indicators.ema_slow_sell = saved_indicators['ema_slow_sell']
                                            engine.indicators.prev_ema_fast_buy = saved_indicators['prev_ema_fast_buy']
                                            engine.indicators.prev_ema_slow_buy = saved_indicators['prev_ema_slow_buy']
                                            engine.indicators.prev_ema_fast_sell = saved_indicators['prev_ema_fast_sell']
                                            engine.indicators.prev_ema_slow_sell = saved_indicators['prev_ema_slow_sell']
                                        _restore_dead_cross_ts(engine.indicators, saved_indicators)  # ✅ WO-26

                                        # ✅ WO-1 추가 A + 추가 C 설계 제약 #3: 복원 성공 로그 (info 레벨, 백업 로그와 쌍)
                                        prev_fast_str = f"{engine.indicators.prev_ema_fast:.2f}" if engine.indicators.prev_ema_fast is not None else "None"
                                        prev_slow_str = f"{engine.indicators.prev_ema_slow:.2f}" if engine.indicators.prev_ema_slow is not None else "None"
                                        logger.info(
                                            f"[BACKFILL] 지표 상태 복원 완료 | "
                                            f"prev_ema_fast={prev_fast_str} "
                                            f"prev_ema_slow={prev_slow_str}"
                                        )
                                    except Exception as _restore_exc:
                                        # ✅ WO-1 추가 C 설계 제약 #2 + #3: 복원 실패 = 지표 오염 상태
                                        # silent continue 금지 → ERROR 로그 + 안전 플래그 + CRITICAL notifier
                                        logger.error(
                                            f"[BACKFILL] ❌ 지표 상태 복원 실패 = 지표 오염 상태 | "
                                            f"exception={_restore_exc}",
                                            exc_info=True,
                                        )
                                        try:
                                            # 안전 플래그: 후속 매매 억제 코드에서 이 플래그를 참조하여 신호 발생을 차단해야 함
                                            # (매매 억제 로직은 별도 후속 작업. 여기서는 플래그 세팅과 알림까지 책임)
                                            setattr(engine.indicators, 'state_polluted', True)
                                        except Exception:
                                            pass
                                        try:
                                            from services.notifier import send as _notify, LEVEL_CRITICAL
                                            _notify(
                                                LEVEL_CRITICAL,
                                                f"🚨 [BACKFILL] 지표 상태 복원 실패 — {user_id}",
                                                (
                                                    f"BACKFILL 처리 중 지표 상태 복원에 실패했습니다.\n"
                                                    f"엔진의 지표(EMA/MACD)가 오염된 상태로 남아 다음 봉 처리 시\n"
                                                    f"잘못된 크로스 판정이 발생할 위험이 있습니다.\n\n"
                                                    f"exception: {_restore_exc}\n"
                                                    f"권장 조치: 봇 재시작 (WARMUP 재시드) 검토."
                                                ),
                                                dedupe_key=f"backfill_restore_fail:{user_id}",
                                                dedupe_ttl=300,
                                            )
                                        except Exception:
                                            pass
                        else:
                            msg = f"✅ [REST-RECONCILE] 변경 없음 → 증분 업데이트"
                            logger.info(msg)
                            log_to_file(msg, user_id)
                    else:
                        # Reconcile 비활성화: 로컬 증분만
                        diff_summary = {"rest_failed": True, "changed_count": 0, "changed_ts": []}
                        logger.info(f"[NO-RECONCILE] 로컬 증분 업데이트만 수행")

                    # ============================================================
                    # Issue #8: 과거 봉 최종종가 검증 (현재 봉 처리 전)
                    # ============================================================
                    # 🎯 목적: 이전 봉들(n-1, n-2, ...)은 반드시 Upbit 차트와 동일
                    # 🔒 검증 실패 시: 현재 봉 스킵 (전략 평가 안 함)
                    past_series = local_series[local_series.index < closed_ts]

                    if not past_series.empty:
                        # 최근 200개 봉만 검증 (200일선 기준)
                        verify_count = min(200, len(past_series))
                        past_to_verify = past_series.tail(verify_count)

                        logger.info(
                            f"[VERIFY] 과거 봉 검증 시작 | count={verify_count} | "
                            f"현재 봉={format_kst(closed_ts)}"
                        )

                        verification_ok = verify_past_candles_with_upbit(
                            ticker=params.upbit_ticker,
                            timeframe=params.interval,
                            past_series=past_to_verify,
                            tolerance=1.0  # ±1원
                        )

                        if not verification_ok:
                            msg = (
                                f"❌ [VERIFY] 과거 봉 검증 실패 → 현재 봉 스킵 | "
                                f"ts={format_kst(closed_ts)} | "
                                f"→ 이전 봉들이 Upbit 차트와 불일치 (포지션 현상 유지)"
                            )
                            logger.error(msg)
                            log_to_file(msg, user_id)
                            time.sleep(1)
                            continue  # ← 현재 봉 처리 안 함

                        logger.info(
                            f"✅ [VERIFY] 과거 봉 검증 통과 | count={verify_count} | "
                            f"현재 봉 처리 진행"
                        )
                    else:
                        logger.info("[VERIFY] 과거 봉 없음 → 검증 스킵 (초기 봉)")

                    # 확정된 봉 추출
                    if closed_ts in local_series.index:
                        row = local_series.loc[closed_ts]

                        # WO-2026-001 Task 2-B: 🔒 봉 데이터 검증 가드
                        valid, reason = candle_validator.validate(row)
                        if not valid:
                            logger.error(
                                f"[STRATEGY] 봉 검증 실패 ❌ | {reason} | "
                                f"ts={format_kst(closed_ts)} | "
                                f"O={row['Open']:.0f} H={row['High']:.0f} "
                                f"L={row['Low']:.0f} C={row['Close']:.0f} V={row['Volume']:.2f} | "
                                f"→ 전략 실행 차단 (포지션 현상 유지)"
                            )
                            time.sleep(1)
                            continue

                        logger.debug(
                            f"[VALIDATOR] 봉 검증 통과 ✅ | ts={format_kst(closed_ts)} | "
                            f"C={row['Close']:.0f}"
                        )

                        bar = Bar(
                            ts=closed_ts,
                            open=row['Open'],
                            high=row['High'],
                            low=row['Low'],
                            close=row['Close'],
                            volume=row['Volume'],
                            is_closed=True,
                            is_confirmed=True,  # REST 확정
                            source="REST_RECONCILED"
                        )

                        # 엔진에 확정 봉 전달
                        # 2차 T5 (T4 넘김 2, 검수 반영 10/28): 잠정 봉·건너뛴 봉이 PULLBACK 지표에 빠졌으면 VERIFY 통과 뒤,
                        # 이 확정 봉을 넣기 바로 전에 링 재생으로 채운다(주문 없음, Issue #8). 못 채우면 오염 + CRITICAL.
                        if strategy_tag == "PULLBACK":
                            _pullback_catchup_step(engine, local_series, closed_ts, user_id, candle_validator)
                        engine.on_new_bar_confirmed(bar, local_series, diff_summary)

                        # ✅ WO-6 감사 누락 수정 (2026-08-30): last_bar_ts 갱신은
                        # strategy_engine 안의 판단·감사·주문 완료 직후에만 실행한다.
                        # 여기서 갱신하지 않아야 케이스 B 안정화 확정 봉의 audit 누락이
                        # 봉쇄된다. 중복 방지는 _evaluated_bar_ts 봉당 1회 검사가 담당.

                        logger.info(f"✅ [CONFIRMED] 봉 처리 완료 | ts={format_kst(closed_ts)} | close={bar.close}")
                    else:
                        # ✅ WO-6 보완 F1 (2026-08-26): NO_TRADE 확정 봉은 RETRY 무의미 → 스킵.
                        if no_trade_this_bar:
                            logger.info(
                                f"⏭ [CLOCK-CLOSE-NO-TRADE] closed_ts={format_kst(closed_ts)} "
                                f"무거래 확정 → RETRY 스킵, 다음 봉 대기"
                            )
                            continue

                        # ✅ Medium-Risk Fix: closed_ts 누락 시 재조회 (Progressive Retry)
                        logger.warning(f"⚠️ [CLOCK-CLOSE] closed_ts={format_kst(closed_ts)}가 local_series에 없음")

                        # 🔄 Progressive Retry: 최대 3회 재시도 (5초 → 8초 → 10초 대기)
                        retry_waits = [5, 8, 10]  # 초 단위 대기 시간 (점진적 증가)
                        retry_success = False

                        for retry_num, wait_sec in enumerate(retry_waits, start=1):
                            logger.info(f"🔄 [RETRY-{retry_num}/{len(retry_waits)}] {wait_sec}초 대기 후 재조회 시도...")
                            time.sleep(wait_sec)
                            logger.debug(f"[RETRY-JITTER] {wait_sec}초 추가 대기 완료")

                            retry_df = safe_fetch_rest(
                                market=params.upbit_ticker,
                                timeframe=params.interval,
                                end_ts=now_utc(),  # ✅ 현재 시각 기준 (추가 Jitter 후)
                                total_count=10  # 최근 10개만
                            )

                            if retry_df is not None and closed_ts in retry_df.index:
                                # 재조회 성공 → local_series 업데이트
                                local_series = pd.concat([local_series, retry_df]).sort_index()
                                local_series = local_series[~local_series.index.duplicated(keep='last')]
                                logger.info(f"✅ [RETRY-{retry_num}] 재조회 성공 | closed_ts={format_kst(closed_ts)} | wait={wait_sec}s")

                                # 이제 처리 가능
                                row = local_series.loc[closed_ts]
                                bar = Bar(
                                    ts=closed_ts,
                                    open=row['Open'],
                                    high=row['High'],
                                    low=row['Low'],
                                    close=row['Close'],
                                    volume=row['Volume'],
                                    is_closed=True,
                                    is_confirmed=True,
                                    source="REST_RECONCILED"
                                )

                                if strategy_tag == "PULLBACK":  # 2차 T5: catch-up 은 VERIFY 뒤·확정 봉 직전
                                    _pullback_catchup_step(engine, local_series, closed_ts, user_id, candle_validator)
                                engine.on_new_bar_confirmed(bar, local_series, diff_summary)
                                # ✅ WO-6 감사 누락 수정 (2026-08-30): last_bar_ts 갱신
                                # 은 strategy_engine 안의 판단·감사·주문 완료 직후에만.
                                # RETRY 경로도 동일하게 여기서 제거.
                                logger.info(f"✅ [CONFIRMED] 재조회 후 봉 처리 완료 | ts={format_kst(closed_ts)} | retry={retry_num}")
                                retry_success = True
                                break  # 성공 시 retry 루프 탈출
                            else:
                                logger.warning(f"⚠️ [RETRY-{retry_num}] 재조회 실패 | closed_ts={format_kst(closed_ts)} | wait={wait_sec}s")

                        # 모든 재시도 실패 시 처리
                        if not retry_success:
                            # ✅ WO-2 옵션 C (2026-09-02): 미확정 봉 진입 배선.
                            # 잠정 종가를 확보할 수 있으면 미확정 Bar 로 엔진에 전달하여
                            # 평가·감사·매수 지연·보호성 매도 즉시 집행 흐름을 진행한다.
                            # 확보 실패 시 기존 동작(봉 스킵)을 유지한다.
                            tentative_result = _lookup_tentative_close(
                                ticker=params.upbit_ticker,
                                local_series=local_series,
                                closed_ts=closed_ts,
                                max_ws_age_sec=10,
                            )
                            if tentative_result is not None:
                                tentative_close, source, source_ts_kst = tentative_result
                                logger.warning(
                                    f"⚠️ [RETRY-EXHAUSTED-TENTATIVE] closed_ts={format_kst(closed_ts)} "
                                    f"→ 미확정 봉 평가 진입 (WO-2 옵션 C) | source={source} "
                                    f"tentative_close={tentative_close} source_ts={source_ts_kst.isoformat()}"
                                )
                                tentative_bar = Bar(
                                    ts=closed_ts,
                                    open=tentative_close,
                                    high=tentative_close,
                                    low=tentative_close,
                                    close=tentative_close,
                                    volume=0.0,
                                    is_closed=True,
                                    is_confirmed=False,
                                    source=f"WO2_OPTION_C_TENTATIVE:{source}",
                                )
                                try:
                                    if strategy_tag == "PULLBACK":  # 2차 T5: 잠정 봉 앞에서도 빠진 봉을 먼저 채운다
                                        _pullback_catchup_step(engine, local_series, closed_ts, user_id, candle_validator)
                                    engine.on_new_bar_confirmed(tentative_bar, local_series, diff_summary)
                                    logger.info(
                                        f"✅ [WO2-OPTION-C] 미확정 봉 평가 진입 완료 | "
                                        f"ts={format_kst(closed_ts)} tentative_close={tentative_close} "
                                        f"source={source}"
                                    )
                                except Exception as _wo2c_exc:
                                    logger.error(
                                        f"❌ [WO2-OPTION-C] 미확정 봉 평가 실패 (예외 → 봉 스킵 fallback) | "
                                        f"{_wo2c_exc}",
                                        exc_info=True,
                                    )
                                # 옵션 C 처리 성공 여부와 무관하게 기존 재시도 실패 알림은
                                # 억제 (미확정 진입은 이미 상세 로그로 남긴다).
                                continue

                            logger.error(f"❌ [RETRY] 모든 재조회 실패 ({len(retry_waits)}회) → 봉 스킵 | closed_ts={format_kst(closed_ts)}")
                            logger.error(f"💡 [FALLBACK] Upbit REST API 지연 ({sum(retry_waits)}초 대기했으나 데이터 미수신, 잠정 종가 확보도 실패) → 다음 봉 대기")
                            # 중요 #10 알림: REST 연속 실패 (v2 — ticker + 영향 명시)
                            try:
                                from services.notifier import send as _notify, LEVEL_WARNING
                                _waits_str = "+".join(str(w) for w in retry_waits)
                                _notify(
                                    LEVEL_WARNING,
                                    f"⚠️ Upbit REST API 응답 지연 — {params.upbit_ticker}",
                                    (
                                        f"시점: {format_kst(closed_ts)} KST 봉\n"
                                        f"재시도: {len(retry_waits)}회 ({_waits_str}={sum(retry_waits)}초) 모두 실패\n"
                                        f"조치: 해당 봉 스킵, 다음 봉 정상 처리\n\n"
                                        f"💡 5분간 1회만 알림 — 같은 알림 재수신 시 Upbit status 확인"
                                    ),
                                    dedupe_key="rest_retry_exhausted",
                                    dedupe_ttl=300,
                                )
                            except Exception:
                                pass

                time.sleep(1)  # 1초마다 폴링

        else:
            # ========================================================
            # 🔄 Legacy WS-based Loop (LEGACY_LOCAL 모드)
            # ========================================================
            logger.info("🔄 [LEGACY_LOCAL] WS-based 스트리밍 모드 시작")

            for df in stream_candles(
                params.upbit_ticker,
                params.interval,
                q,
                stop_event=stop_event,
                max_length=500,
                user_id=user_id,
                strategy_type=strategy_tag,
            ):
                if stop_event.is_set():
                    break

                if df is None or df.empty:
                    logger.info("❌ 데이터프레임 비어있음 → 5초 후 재시도")
                    time.sleep(5)
                    continue

                # ✅ Base EMA GAP 모드: 누락된 타임스탬프를 이전 종가로 채우기
                if strategy_tag == "EMA" and getattr(params, "base_ema_gap_enabled", False):
                    # interval별 봉 간격 매핑
                    interval_map = {
                        "minute1": "1T",
                        "minute3": "3T",
                        "minute5": "5T",
                        "minute10": "10T",
                        "minute15": "15T",
                        "minute30": "30T",
                        "minute60": "60T",
                        "day": "D",
                    }
                    freq = interval_map.get(params.interval, "1T")

                    # 연속된 타임스탬프 생성
                    start_time = df.index.min()
                    end_time = df.index.max()
                    full_range = pd.date_range(start=start_time, end=end_time, freq=freq)

                    # 누락 봉 개수 체크
                    missing_count = len(full_range) - len(df)
                    if missing_count > 0:
                        logger.info(f"[ENGINE] Base EMA GAP: 누락 봉 {missing_count}개 감지, 이전 종가로 채움...")

                        # reindex로 누락 타임스탬프 추가 후 forward fill
                        df = df.reindex(full_range)

                        # 누락된 봉은 이전 종가로 OHLC 채우기 (Volume은 0)
                        df["Close"] = df["Close"].ffill()
                        df["Open"] = df["Open"].fillna(df["Close"])
                        df["High"] = df["High"].fillna(df["Close"])
                        df["Low"] = df["Low"].fillna(df["Close"])
                        df["Volume"] = df["Volume"].fillna(0)

                        logger.info(f"[ENGINE] Base EMA GAP: 누락 봉 채우기 완료, 최종 데이터: {len(df)}개")

                # ★ 워밍업 단계: 지표 초기 시드
                if not warmup_complete:
                    if len(df) >= min_hist:
                        closes = df['Close'].tolist()
                        if indicators.seed_from_closes(closes):
                            warmup_complete = True
                            logger.info(f"✅ Warmup 완료 | bars={len(df)}")

                            # 버퍼에 과거 데이터 채우기 + WARMUP 로그 기록
                            for idx, row in df.iterrows():
                                bar = Bar(
                                    ts=idx,
                                    open=row['Open'],
                                    high=row['High'],
                                    low=row['Low'],
                                    close=row['Close'],
                                    volume=row['Volume'],
                                    is_closed=True
                                )
                                buffer.append(bar)

                                # ✅ WARMUP 완료 시 모든 봉에 대해 평가 로그 기록
                                # ⚠️ min_hist 이하로만 표시 (초과분은 min_hist로 표시)
                                engine.bar_count = len(buffer)
                                current_count = min(len(buffer), min_hist)
                                engine.record_warmup_log(bar, f"(완료 {current_count}/{min_hist})")

                            # ✅ bar_count는 이미 루프에서 설정됨

                            # ★ 핵심: WARMUP 완료 시 버퍼의 마지막 봉을 기준점으로 설정
                            # WARMUP 완료 시 버퍼에 이미 모든 과거 봉이 추가되었으므로,
                            # 다음 yield부터 새 봉만 처리하도록 마지막 봉으로 설정
                            # 예: 버퍼에 BAR 1~200 추가 완료 → engine.last_bar_ts = BAR 200.ts
                            # → 다음 yield에서 BAR 201부터만 처리 (중복 평가 방지)
                            engine.last_bar_ts = df.index[-1]

                            # ✅ 중복 방지: 모든 WARMUP 봉을 processed_bar_timestamps에 추가
                            for idx in df.index:
                                processed_bar_timestamps.add(idx)

                            # ✅ last_processed_ts 즉시 초기화 (중복 방지 강화)
                            last_processed_ts = df.index[-1]

                            logger.info(f"✅ Buffer seeded | buffer_len={len(buffer)} | bar_count={engine.bar_count} | warmup_baseline={df.index[-1]}")
                            # ✅ WO-12 C7: 워밍업 직후 지갑 기준 즉시 복원 (위 CLOCK 경로와 동일)
                            if boot_seed_recover_qty is not None:
                                _boot_seed_recover_from_wallet(engine, params.upbit_ticker, user_id, boot_seed_recover_qty)
                                boot_seed_recover_qty = None
                            logger.info(f"✅ 중복 방지 초기화 | processed_timestamps={len(processed_bar_timestamps)}개 | last_processed={last_processed_ts}")
                    else:
                        # WARMUP 진행 중 - 새로 추가된 봉들에 대해 로그 기록
                        if prev_warmup_last_ts is not None:
                            # 이전 yield 이후 추가된 봉들만 추출
                            new_bars_df = df[df.index > prev_warmup_last_ts]
                        else:
                            # 첫 yield: 모든 봉 처리
                            new_bars_df = df

                        # 새 봉들에 대해 WARMUP 로그 기록
                        for idx, row in new_bars_df.iterrows():
                            bar = Bar(
                                ts=idx,
                                open=row['Open'],
                                high=row['High'],
                                low=row['Low'],
                                close=row['Close'],
                                volume=row['Volume'],
                                is_closed=True
                            )
                            engine.bar_count += 1
                            engine.record_warmup_log(bar, f"({len(df)}/{min_hist})")

                        prev_warmup_last_ts = df.index[-1] if not df.empty else None
                        logger.info(f"[WARMUP] {len(df)}/{min_hist} bars... | 새 봉 {len(new_bars_df)}개 로그 기록")
                        time.sleep(1)
                        continue

                # ★ 새로 추가된 모든 봉 처리 (합성 봉 누락 방지)
                if last_processed_ts is None:
                    # ★ 첫 yield: WARMUP 직후 새로 추가된 봉만 처리
                    # engine.last_bar_ts는 WARMUP 완료 시 버퍼의 마지막 봉 timestamp
                    if engine.last_bar_ts is not None:
                        # WARMUP 이후 새로 추가된 봉들만 추출 (합성 봉 포함)
                        new_bars_df = df[df.index > engine.last_bar_ts]
                        if not new_bars_df.empty:
                            logger.info(f"[첫 yield] WARMUP 이후 새 봉 {len(new_bars_df)}개 처리: {new_bars_df.index[0]} ~ {new_bars_df.index[-1]}")
                        else:
                            logger.info(f"[첫 yield] WARMUP 이후 새 봉 없음 (last_bar={engine.last_bar_ts})")
                    else:
                        # 안전장치: engine.last_bar_ts가 없는 경우 마지막 봉만 처리
                        new_bars_df = df.tail(1)
                        logger.warning(f"[첫 yield] engine.last_bar_ts=None → 마지막 봉만 처리: {df.index[-1]}")
                else:
                    # 이전 yield 이후 추가된 봉들만 추출
                    new_bars_df = df[df.index > last_processed_ts]
                    if not new_bars_df.empty:
                        logger.info(f"[새 봉 감지] {len(new_bars_df)}개 | {new_bars_df.index[0]} ~ {new_bars_df.index[-1]}")
                    else:
                        # 새 봉 없음 (드물지만 발생 가능)
                        logger.debug(f"[새 봉 없음] last_processed={last_processed_ts}, df_last={df.index[-1]}")

                # ✅ 중복 방지: 이미 처리된 봉 필터링
                # DataFrame 재구성 시에도 중복 평가 방지
                if not new_bars_df.empty:
                    before_filter = len(new_bars_df)
                    new_bars_df = new_bars_df[~new_bars_df.index.isin(processed_bar_timestamps)]
                    after_filter = len(new_bars_df)

                    if before_filter > after_filter:
                        filtered_count = before_filter - after_filter
                        logger.warning(
                            f"⚠️ [중복 방지] {filtered_count}개 봉이 이미 처리됨 (필터링됨) | "
                            f"before={before_filter}, after={after_filter}"
                        )

                # ✅ 중복 인덱스 제거: DataFrame에 같은 timestamp의 row가 여러 개 있는 경우
                # - Base EMA GAP reindex() 후 발생 가능
                # - 중복 timestamp가 있으면 iterrows()에서 같은 봉을 여러 번 처리
                # - keep='last': 가장 최신 데이터 유지
                if not new_bars_df.empty:
                    before_dedup = len(new_bars_df)
                    new_bars_df = new_bars_df[~new_bars_df.index.duplicated(keep='last')]
                    after_dedup = len(new_bars_df)

                    if before_dedup > after_dedup:
                        dedup_count = before_dedup - after_dedup
                        logger.warning(
                            f"⚠️ [중복 인덱스 제거] DataFrame에 {dedup_count}개 중복 timestamp 발견 및 제거 | "
                            f"before={before_dedup}, after={after_dedup}"
                        )

                # ★★★ 핵심: 새로 추가된 모든 봉을 엔진에 전달 ★★★
                for idx, row in new_bars_df.iterrows():
                    bar = Bar(
                        ts=idx,
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume'],
                        is_closed=True  # stream_candles는 닫힌 봉만 제공
                    )
                    engine.on_new_bar(bar)

                    # ✅ 처리 완료된 봉을 Set에 추가 (중복 방지)
                    processed_bar_timestamps.add(idx)

                # ✅ 마지막 처리 timestamp 업데이트
                if not new_bars_df.empty:
                    last_processed_ts = new_bars_df.index[-1]

    except Exception:
        logger.exception(f"❌ run_live_loop 예외 발생 ({mode_tag})")
        ts = time.time()
        exc_type, exc_value, tb = sys.exc_info()
        q.put((ts, "EXCEPTION", exc_type, exc_value, tb))
        raise  # ✅ CTO 승인: 자동 재시작 로직 활성화 (engine_manager.py:209-255)
    finally:
        logger.info(f"🧹 run_live_loop 종료 ({mode_tag}) → stop_event set")
        stop_event.set()
