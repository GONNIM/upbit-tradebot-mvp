"""
라이브 트레이딩 루프 - 증분 처리 기반 (Backtest 제거)
"""
import threading
import queue
import logging
import sys
import time
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# 새로운 증분 처리 모듈
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_incremental import IncrementalMACDStrategy, IncrementalEMAStrategy
from core.strategy_engine import StrategyEngine

# 기존 모듈
from core.data_feed import stream_candles, fill_gaps_sync
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

    ⚠️ Upbit API 제한: 최대 200개 봉만 조회 가능
    - slow_buy=200 같은 긴 기간 설정 시, 초기에는 불완전한 이동평균으로 시작
    - 실시간 데이터가 쌓이면서 점진적으로 정확도 향상
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

    # ✅ EMA 전략: use_separate_ema일 때는 slow_buy, slow_sell 중 최대값 사용
    # base_ema_period는 선택적 필터이므로 WARMUP 계산에서 제외
    if strategy_tag == "EMA" and getattr(params, "use_separate_ema", False):
        slow_buy = getattr(params, "slow_buy", None) or params.slow_period
        slow_sell = getattr(params, "slow_sell", None) or params.slow_period
        slow = max(slow_buy, slow_sell)
    else:
        slow = getattr(params, "slow_period", 26) or 26

    # ✅ EMA 계산은 period * 2배면 충분히 안정화됨
    # base_ema_period는 WARMUP 계산에서 제외 (선택적 필터)
    logical_min = slow * 2

    # ⚠️ Upbit API 제한: 최대 200개만 조회 가능
    # - slow=200인 경우: logical_min=400이지만 200개로 제한
    # - 초기에는 불완전하지만 실시간으로 데이터 축적하면서 정확도 향상
    UPBIT_API_LIMIT = 200
    requested = max(base, logical_min, 200)

    if requested > UPBIT_API_LIMIT:
        logger.warning(
            f"⚠️  [WARMUP] Upbit API 제한으로 인한 조정: "
            f"{requested}개 요청 → {UPBIT_API_LIMIT}개로 제한"
        )
        logger.warning(
            f"⚠️  [WARMUP] slow={slow} 설정에 최적 데이터 수는 {logical_min}개이지만, "
            f"초기에는 {UPBIT_API_LIMIT}개로 시작합니다."
        )
        logger.warning(
            f"⚠️  [WARMUP] 실시간 데이터가 쌓이면서 점진적으로 정확도가 향상됩니다. "
            f"완전한 {slow}일 이동평균은 약 {slow}분 후 계산됩니다."
        )
        requested = UPBIT_API_LIMIT

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

        strategy = IncrementalEMAStrategy(
            user_id=user_id,
            ticker=params.upbit_ticker,
            take_profit=params.take_profit,
            stop_loss=params.stop_loss,
            min_holding_period=getattr(params, "min_holding_period", 0),
            trailing_stop_pct=getattr(params, "trailing_stop_pct", TRAILING_STOP_PERCENT),
            use_base_ema=use_base_ema_filter,  # ✅ 파라미터 설정 반영
            base_ema_gap_diff=getattr(params, "base_ema_gap_diff", -0.005),  # ✅ Base EMA GAP 임계값
            buy_conditions=buy_conditions,  # ✅ 조건 파일 전달 (BUY)
            sell_conditions=sell_conditions,  # ✅ 조건 파일 전달 (SELL)
        )

        logger.info(f"[EMA 전략] use_base_ema={use_base_ema_filter}")
    else:
        raise ValueError(f"Unknown strategy type: {strategy_tag}")

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

    try:
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

            # ★ 워밍업 단계: 지표 초기 시드
            if not warmup_complete:
                if len(df) >= min_hist:
                    closes = df['Close'].tolist()
                    if indicators.seed_from_closes(closes):
                        warmup_complete = True
                        logger.info(f"✅ Warmup 완료 | bars={len(df)}")

                        # 버퍼에 과거 데이터 채우기 (시드용)
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

                        # ✅ bar_count 초기화 (버퍼 길이와 동기화)
                        engine.bar_count = len(buffer)
                        engine.last_bar_ts = buffer.get_last_bar().ts if buffer.get_last_bar() else None

                        logger.info(f"✅ Buffer seeded | buffer_len={len(buffer)} | bar_count={engine.bar_count}")
                else:
                    logger.info(f"[WARMUP] {len(df)}/{min_hist} bars...")
                    time.sleep(1)
                    continue

            # ★ 최신 봉 추출 (증분 처리)
            latest_idx = df.index[-1]
            latest_row = df.iloc[-1]
            bar = Bar(
                ts=latest_idx,
                open=latest_row['Open'],
                high=latest_row['High'],
                low=latest_row['Low'],
                close=latest_row['Close'],
                volume=latest_row['Volume'],
                is_closed=True  # stream_candles는 닫힌 봉만 제공
            )

            # ★★★ 핵심: 엔진에 새 봉 전달 (Backtest 없음!) ★★★
            engine.on_new_bar(bar)

    except Exception:
        logger.exception(f"❌ run_live_loop 예외 발생 ({mode_tag})")
        ts = time.time()
        exc_type, exc_value, tb = sys.exc_info()
        q.put((ts, "EXCEPTION", exc_type, exc_value, tb))
    finally:
        logger.info(f"🧹 run_live_loop 종료 ({mode_tag}) → stop_event set")
        stop_event.set()
