"""
라이브 트레이딩 루프 - 증분 처리 기반 (Backtest 제거)
"""
import threading
import queue
import logging
import sys
import time
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# 새로운 증분 처리 모듈
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_incremental import IncrementalMACDStrategy, IncrementalEMAStrategy
from core.strategy_engine import StrategyEngine

# 🚀 REST Reconcile 모듈
from core.candle_clock import CandleClock
from core.rest_reconcile import safe_fetch_rest, reconcile_series, fetch_confirmed_candle
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


def _seed_entry_price_from_db(ticker: str, user_id: str) -> Optional[Dict[str, Any]]:
    """DB에서 최근 completed BUY의 체결가와 entry_bar를 복구"""
    try:
        raw = get_last_open_buy_order(ticker, user_id)
        logger.info(f"[SEED] raw_last_open={raw}")
        if not raw:
            logger.info("[SEED] result=None (no data)")
            return None

        result = {}
        price = raw.get("price")
        entry_bar = raw.get("entry_bar")

        if price is not None:
            result["price"] = float(price)
        if entry_bar is not None:
            result["entry_bar"] = int(entry_bar)

        if not result:
            logger.info("[SEED] result=None (no price or entry_bar)")
            return None

        logger.info(f"🔁 Seed from DB: price={result.get('price')} entry_bar={result.get('entry_bar')}")
        return result
    except Exception as e:
        logger.warning(f"[SEED] failed: {e}")
        return None


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


def _strategy_tag(strategy_type: str) -> str:
    """전략 타입 정규화"""
    if not strategy_type:
        return DEFAULT_STRATEGY_TYPE.upper()
    return strategy_type.upper().strip()


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
    logger.info("🚀 ★ 증분 처리 기반 엔진 (Backtest 없음) ★")

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
    position = PositionState()

    # 기존 포지션 복구 (지갑 기준)
    has_pos = _wallet_has_position(trader, params.upbit_ticker)
    if has_pos:
        # ✅ 실제 지갑 잔고로 qty 설정 (Single Source of Truth)
        actual_qty = _wallet_balance(trader, params.upbit_ticker)

        db_result = _seed_entry_price_from_db(params.upbit_ticker, user_id)
        if db_result:
            entry_price = db_result.get("price")
            entry_bar = db_result.get("entry_bar")

            position.has_position = True
            position.avg_price = entry_price
            position.qty = actual_qty  # ✅ 매도 시 필수!
            if entry_bar is not None:
                position.entry_bar = entry_bar
            logger.info(f"🔁 Position recovered | entry={entry_price} qty={actual_qty:.6f} entry_bar={entry_bar}")
        else:
            # ⚠️ DB에서 진입가를 찾지 못했지만 지갑에 코인이 있는 경우
            logger.warning(
                f"⚠️ 지갑에 코인({actual_qty:.6f})이 있지만 DB에서 진입가를 찾을 수 없습니다. "
                f"포지션 복구 불가 - 수동 정리 또는 force_liquidate 필요"
            )
            # qty만이라도 설정해서 비상 매도는 가능하도록
            position.has_position = True
            position.qty = actual_qty
            position.avg_price = None  # 진입가 불명
            logger.warning(f"⚠️ 비상 모드: qty={actual_qty:.6f} 설정 완료, 진입가 없음")

    # ✅ 조건 파일 로드 (매수/매도 조건)
    conditions = _load_trade_conditions(user_id, params.strategy_type)
    buy_conditions = conditions.get("buy", {})  # ✅ 매수 조건 추출
    sell_conditions = conditions.get("sell", {})  # ✅ 매도 조건 추출

    # 🔍 DEBUG: 조건 파일 로딩 상태 상세 로그
    logger.info(f"🔍 DEBUG [CONDITIONS] Full conditions loaded: {conditions}")
    logger.info(f"[전략 초기화] Loaded buy conditions: {buy_conditions}")
    logger.info(f"[전략 초기화] Loaded sell conditions: {sell_conditions}")

    # ✅ 필수 매도 조건 검증
    if not sell_conditions:
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

    warmup_complete = False

    logger.info(f"[WARMUP] Required bars: {min_hist}")

    # ✅ 설정 스냅샷 1분 타이머 (봉과 무관하게 독립 동작)
    def _settings_snapshot_timer():
        """1분마다 설정 스냅샷 기록 (별도 스레드)"""
        last_minute: Optional[str] = None
        while not stop_event.is_set():
            try:
                current_minute = now_kst_minute()
                if last_minute != current_minute:
                    # 조건 파일 로드 (매번 최신 상태 반영)
                    trade_conditions = _load_trade_conditions(user_id, strategy_tag)

                    insert_settings_snapshot(
                        user_id=user_id,
                        ticker=params.upbit_ticker,
                        interval_sec=getattr(params, "interval_sec", 60),
                        tp=params.take_profit,
                        sl=params.stop_loss,
                        ts_pct=getattr(params, "trailing_stop_pct", None),
                        signal_gate=getattr(params, "signal_confirm_enabled", False),
                        threshold=getattr(params, "macd_threshold", 0.0),
                        buy_dict=trade_conditions.get("buy", {}),
                        sell_dict=trade_conditions.get("sell", {}),
                        bar_time=current_minute
                    )
                    last_minute = current_minute
                    logger.info(f"[SETTINGS-SNAPSHOT] ✅ Recorded at {current_minute}")
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

            for attempt in range(1, MAX_WARMUP_RETRIES + 1):
                # WO-2026-001 Task 1-B: +1개 요청 후 마지막 봉 제거 (현재 진행 중 봉 방지)
                warmup_request = min_hist + 1
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
            # ✅ FIX-2026-003-14: 조건부 제거 (데이터 부족 시 유지)
            # ============================================================
            # ✅ Upbit는 to 파라미터 없어도 현재 진행 중인 봉을 포함할 수 있음
            # ✅ 안전을 위해 마지막 봉 제거 (단, 여유분이 있을 때만)
            if len(initial_df) > min_hist:
                # 여유분이 있으면 마지막 봉 제거 (안전)
                last_ts_before = initial_df.index[-1]
                initial_df = initial_df.iloc[:-1]
                logger.info(
                    f"[WARMUP] 마지막 봉 제거 ✅ | "
                    f"removed_ts={format_kst(last_ts_before)} | "
                    f"최종 봉 수={len(initial_df)} | "
                    f"최종 마지막 봉={format_kst(initial_df.index[-1])}"
                )
            elif len(initial_df) == min_hist:
                # 정확히 필요한 만큼이면 그대로 사용 (마지막 봉 유지)
                logger.warning(
                    f"[WARMUP] 마지막 봉 유지 (여유분 없음) | "
                    f"bars={len(initial_df)} = min_hist={min_hist} | "
                    f"마지막 봉={format_kst(initial_df.index[-1])}"
                )
            else:
                # 부족하면 에러
                logger.error(
                    f"❌ [WARMUP] 데이터 부족 | "
                    f"received={len(initial_df)} < min_hist={min_hist}"
                )
                raise RuntimeError(f"Insufficient warmup data: {len(initial_df)} < {min_hist}")

            # 지표 시드
            closes = initial_df['Close'].tolist()
            if indicators.seed_from_closes(closes):
                warmup_complete = True
                logger.info(f"✅ Warmup 완료 | bars={len(initial_df)}")

                # 버퍼 채우기
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
                    engine.record_warmup_log(bar, f"(완료 {current_count}/{min_hist})")

                engine.last_bar_ts = initial_df.index[-1]
                local_series = initial_df.copy()

                logger.info(f"✅ Buffer seeded | buffer_len={len(buffer)} | bar_count={engine.bar_count}")
            else:
                logger.error("❌ [WARMUP] Indicator seed 실패")
                raise RuntimeError("Indicator warmup failed")

            # ============================================================
            # Clock-based 폴링 루프
            # ============================================================
            logger.info("🚀 [CLOCK-LOOP] 시작 - 1초마다 폴링, 봉 확정 시 REST Reconcile")

            while not stop_event.is_set():
                now = now_utc()

                if clock.should_close(now):
                    closed_ts = clock.get_closed_ts(now)

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
                        rest_df = safe_fetch_rest(
                            market=params.upbit_ticker,
                            timeframe=params.interval,
                            end_ts=now_utc(),  # ✅ 현재 시각 기준 (Jitter 후)
                            total_count=RECONCILE_LOOKBACK_BARS
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
                            logger.info(f"🔄 [REST-RECONCILE] {changed_count}개 봉 변경 감지 → 부분 재계산")
                        else:
                            logger.info(f"✅ [REST-RECONCILE] 변경 없음 → 증분 업데이트")
                    else:
                        # Reconcile 비활성화: 로컬 증분만
                        diff_summary = {"rest_failed": True, "changed_count": 0, "changed_ts": []}
                        logger.info(f"[NO-RECONCILE] 로컬 증분 업데이트만 수행")

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
                        engine.on_new_bar_confirmed(bar, local_series, diff_summary)

                        # ✅ Critical Fix: engine.last_bar_ts 업데이트 (중복 방지)
                        engine.last_bar_ts = closed_ts

                        logger.info(f"✅ [CONFIRMED] 봉 처리 완료 | ts={format_kst(closed_ts)} | close={bar.close}")
                    else:
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

                                engine.on_new_bar_confirmed(bar, local_series, diff_summary)
                                engine.last_bar_ts = closed_ts
                                logger.info(f"✅ [CONFIRMED] 재조회 후 봉 처리 완료 | ts={format_kst(closed_ts)} | retry={retry_num}")
                                retry_success = True
                                break  # 성공 시 retry 루프 탈출
                            else:
                                logger.warning(f"⚠️ [RETRY-{retry_num}] 재조회 실패 | closed_ts={format_kst(closed_ts)} | wait={wait_sec}s")

                        # 모든 재시도 실패 시 처리
                        if not retry_success:
                            logger.error(f"❌ [RETRY] 모든 재조회 실패 ({len(retry_waits)}회) → 봉 스킵 | closed_ts={format_kst(closed_ts)}")
                            logger.error(f"💡 [FALLBACK] Upbit REST API 지연 ({sum(retry_waits)}초 대기했으나 데이터 미수신) → 다음 봉 대기")

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
