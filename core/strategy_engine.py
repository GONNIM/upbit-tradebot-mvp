"""
전략 엔진 - Backtest 없이 증분 처리 기반
핵심: 새 봉 1개씩 처리하며 전략 평가 → 주문 실행
"""
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_action import Action
from core.filters.buy_filters import WEAK_ENTRY_FILTER_REASON, weak_entry_note, weak_position_note  # ✅ WO-26
from core.trader import UpbitTrader
from services.db import insert_buy_eval, insert_sell_eval, estimate_bars_held_from_audit, get_trading_paused, annotate_buy_eval_blocked
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo
from collections import OrderedDict
from datetime import datetime
import logging
import queue
import threading  # ✅ Issue #10: 스레드 락 추가

logger = logging.getLogger(__name__)


# ============================================================
# ✅ WO-8b (2026-09-18): 활성 엔진 레지스트리 + force_buy uuid 등록 헬퍼
# 강제 매수 지정가 발주 후 반환 uuid를 StrategyEngine._pending_buy_uuid 에 등록해
# _on_limit_fill 콜백의 uuid 매칭이 성공하도록 한다. 등록 없으면 apply_entry 가
# skip되어 [POSITION-SYNC] 자동 복구 방어망에 의존하게 된다 (관문 우회).
# ============================================================
_active_engines: "Dict[tuple, 'StrategyEngine']" = {}
_active_engines_lock = threading.Lock()

# ✅ 2차 T5: PULLBACK 매수 주문 실패 뒤 다시 주문하지 않는 봉 수 (T4 넘김 7 — 실보유 없이 주문이 계속
#   실패하면 정리 → 재신호가 반복되어 주문·알림이 쌓이는 것을 막는다). 지나면 다시 시도한다.
#   결정 1028-03(다): 3봉. 의미: 실패 봉 포함 3봉 — 실패 봉 #F ~ #F+2 동안 재주문 안 함, #F+3 부터 다시 주문
#   (bar_count - F < 3). 들어가는 것: trader 단계 주문 실패(업비트 거절·오류)·trader strict 거절(잔고 부족 경쟁·
#   잔고 조회 실패). 엔진 사전 검사 건너뜀(최소 미만·잔고 부족·잔고 조회 실패)은 넣지 않는다.
#   해제: 봇 매도 체결(close_position reason="bot_sell")만. 앱 매도 지갑 0 동기화·회차 0 정리로는 풀지 않는다.
#   고지: 시작 때 텔레그램 WARNING 1회 + 감사 BUY_REJECTED(split_order_cooldown) 1행. 끝·해제 알림은 보내지 않는다.
PULLBACK_BUY_FAIL_COOLDOWN_BARS = 3
PULLBACK_MIN_ORDER_KRW = 5000
# ✅ 2차 T6: LIVE 분할 주문 체결 대기 봉 수(넘으면 WARNING [PULLBACK-SYNC] fill pending 후 지갑 기준으로 맞춤)
#   · 지갑·분할 상태 수량 차이 허용 비율(최소 단위 0.1% — 넘으면 지갑 우선 + desync=1)
PULLBACK_FILL_WAIT_BARS = 3
PULLBACK_SYNC_TOL = 0.001
# ✅ 2차 T8: PULLBACK 매도 평가 감사 trigger_key (EMA·MACD 의 이름과 같은 꼴)
PULLBACK_SELL_TRIGGER_KEY = {"TP": "Take Profit", "SL": "Stop Loss", "DEADCROSS": "Dead Cross"}
NO_ACTION_TEXT = "투자자님이 따로 하실 일은 없습니다."  # 2차 T8: 새 전략 텔레그램 끝맺음(할 일이 없을 때)


def _fmt_price(x) -> str:
    """2차 T8 알림·화면용 가격 표기(업비트 호가 단위 대략 — 끝자리 0 은 지움)."""
    from services.terminology import format_price
    return format_price(x)


def register_pending_buy_uuid(user_id: str, ticker: str, uuid: str, wait_bars: int) -> bool:
    """
    force_buy 지정가 발주 후 uuid를 StrategyEngine._pending_buy_uuid 에 등록 (비원자적).

    ⚠️ Race condition 주의:
        buy_limit 반환 후 이 함수 호출 사이에 reconciler 순회로 fill callback 이
        먼저 발동될 수 있다. 발주-등록 원자화가 필요하면 execute_force_buy_limit_atomic
        를 사용하라. 본 함수는 TEST 및 하위 호환용으로만 유지한다.

    Thread safety:
        - _active_engines_lock: 엔진 인스턴스 조회 원자성
        - engine._execution_lock: pending 상태 세팅 원자성 (기존 봉 처리 스레드와 배타)

    Returns:
        True: 엔진 인스턴스 발견 + 등록 성공
        False: 엔진 미가동 or 미등록 (TEST/dry-run) — 무해 skip
    """
    with _active_engines_lock:
        engine = _active_engines.get((user_id, ticker))
    if engine is None:
        logger.debug(
            f"[FORCE-BUY-PENDING] 엔진 미가동 or 미등록 — skip | "
            f"user={user_id} ticker={ticker}"
        )
        return False
    wait_bars_clamped = int(max(1, min(5, wait_bars)))
    with engine._execution_lock:
        engine._pending_buy_uuid = uuid
        engine._pending_buy_bar = engine.bar_count
        engine._pending_buy_wait_bars = wait_bars_clamped
        try:
            engine.position.set_pending(True)
        except Exception:
            pass
    logger.info(
        f"🎯 [FORCE-BUY-PENDING] uuid 등록 완료 | user={user_id} ticker={ticker} "
        f"uuid={uuid} bar={engine.bar_count} wait_bars={wait_bars_clamped}"
    )
    return True


def execute_force_buy_limit_atomic(
    *,
    user_id: str,
    ticker: str,
    trader,
    price: float,
    ts,
    meta: "Dict[str, Any]",
    interval_sec: int,
    wait_bars: int,
) -> "Optional[Dict[str, Any]]":
    """
    ✅ WO-8b 원자화 (2026-09-18): 발주-등록 경합 봉쇄.

    engine._execution_lock 아래에서 trader.buy_limit 호출 + uuid 등록을 원자적으로 수행.
    reconciler 스레드가 발생시키는 fill callback 은 이 락 획득까지 대기하므로
    등록 완료 후에만 _on_limit_fill 이 진입해 uuid 매칭이 성공한다.

    엔진 미가동 (TEST/dry-run) 시에는 fill callback 이 애초에 등록되지 않으므로
    락 없이 buy_limit 만 호출한다 (경합 대상 부재).

    Race 시나리오 (수정 전):
        T=x   trader.buy_limit → reconciler.enqueue(uuid)  (락 밖)
        T=x+ε reconciler 스레드가 이 uuid 로 get_order 시작
        T=x+δ _on_limit_fill 이 engine._execution_lock 획득 → _pending_buy_uuid=None mismatch
        T=x+τ register_pending_buy_uuid 뒤늦게 락 획득 → 이미 apply_entry skip

    본 함수 (수정 후):
        with engine._execution_lock:
            trader.buy_limit → reconciler.enqueue        (락 안)
            _pending_buy_uuid = uuid, _pending_buy_bar = bar_count
        (락 해제 후) _on_limit_fill 락 획득 → uuid 매칭 성공

    Returns:
        trader.buy_limit 의 반환 dict (limit_pending=True 시 apply_entry 는
        후속 fill callback 에서 처리)
    """
    with _active_engines_lock:
        engine = _active_engines.get((user_id, ticker))

    if engine is None:
        # 엔진 미가동: fill callback 미등록이라 경합 대상 자체 없음.
        logger.debug(
            f"[FORCE-BUY-ATOMIC] 엔진 미가동 — 락 없이 buy_limit 실행 | "
            f"user={user_id} ticker={ticker}"
        )
        return trader.buy_limit(
            price, ticker, ts=ts, meta=meta, interval_sec=interval_sec
        )

    wait_bars_clamped = int(max(1, min(5, wait_bars)))
    with engine._execution_lock:
        # buy_limit 내부의 reconciler.enqueue 도 이 락 아래에서 발생.
        # 이후 fill callback (_on_limit_fill) 은 이 락 획득까지 대기.
        result = trader.buy_limit(
            price, ticker, ts=ts, meta=meta, interval_sec=interval_sec
        )
        if result and result.get("limit_pending") and result.get("uuid"):
            engine._pending_buy_uuid = result["uuid"]
            engine._pending_buy_bar = engine.bar_count
            engine._pending_buy_wait_bars = wait_bars_clamped
            try:
                engine.position.set_pending(True)
            except Exception:
                pass
            logger.info(
                f"🎯 [FORCE-BUY-ATOMIC] uuid 원자 등록 완료 | user={user_id} "
                f"ticker={ticker} uuid={result['uuid']} bar={engine.bar_count} "
                f"wait_bars={wait_bars_clamped}"
            )
    return result


def convert_unfilled_limit_buy(
    *,
    user_id: str,
    ticker: str,
    limit_price: float,
    remaining_qty: float,
    executed_qty: float,
    executed_avg: float,
    orig_uuid: str,
    meta: "Dict[str, Any]",
    price_fetcher=None,
) -> "Dict[str, Any]":
    """
    ✅ WO-24 (2026-10-05): 현재가 매수가 대기 봉 안에 체결되지 않아 취소 확정됐을 때 "미체결 시 시장가 전환".

    - 옵션: buy_conditions.fixed_price_unfilled_to_market (없으면 config.UNFILLED_TO_MARKET_DEFAULT),
            buy_conditions.fixed_price_convert_max_gap_pct (없으면 config.UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT, %)
    - 현재가 ≤ 주문가 × (1 + 허용 %) 일 때만 남은 수량을 기존 시장가 매수(trader.buy_market, KRW = 남은 수량 × 현재가)로 산다.
    - 엔진 실행 락 아래에서 발주 + apply_entry(source="bot_market_convert") (WO-8b 원자 경로와 같은 락).
      부분 체결분이 있으면 (부분 체결 + 전환) 가중 평균가·합계 수량으로 등록한다.
    반환: {"enabled", "converted", "reason", "current_price", "gap_pct", "max_gap_pct", "result"}
    """
    from config import UNFILLED_TO_MARKET_DEFAULT, UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT
    with _active_engines_lock:
        engine = _active_engines.get((user_id, ticker))
    if engine is None:
        return {"enabled": False, "converted": False, "reason": "엔진 미가동"}

    cond = getattr(engine.strategy, "buy_conditions", None) or {}
    enabled = bool(cond.get("fixed_price_unfilled_to_market", UNFILLED_TO_MARKET_DEFAULT))
    max_gap = float(cond.get("fixed_price_convert_max_gap_pct", UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT))
    out = {"enabled": enabled, "converted": False, "reason": "", "current_price": None, "gap_pct": None, "max_gap_pct": max_gap}
    if not enabled:
        out["reason"] = "미체결 시 시장가 전환 꺼짐"
        return out

    if price_fetcher is None:
        from services.trading_control import get_current_price_from_upbit as price_fetcher
    cur = price_fetcher(ticker)
    if not cur or not limit_price:
        out["reason"] = "현재가 조회 실패"
        return out
    gap = (float(cur) / float(limit_price) - 1.0) * 100.0
    out.update(current_price=float(cur), gap_pct=gap)
    if gap > max_gap:
        out["reason"] = f"가격 차이 {gap:.2f}% > 허용 {max_gap:.2f}%"
        logger.info(f"[UNFILLED-CONVERT] 전환 안 함 | uuid={orig_uuid} {out['reason']} 주문가={limit_price} 현재가={cur}")
        return out

    from zoneinfo import ZoneInfo as _ZI
    now = datetime.now(_ZI("Asia/Seoul"))
    conv_meta = {**(meta or {}), "unfilled_convert": True, "converted_from": orig_uuid}
    for k in ("is_fixed_price_buy", "fixed_price_buy", "limit_price"):
        conv_meta.pop(k, None)
    with engine._execution_lock:
        if engine.position.has_position and executed_qty <= 0:
            out["reason"] = "이미 포지션 보유"
            return out
        result = engine.trader.buy_market(float(cur), ticker, ts=now, meta=conv_meta,
                                          krw_amount=float(remaining_qty) * float(cur))
        if not result:
            out["reason"] = "시장가 매수 실패 (trader.buy_market 빈 결과)"
            logger.warning(f"[UNFILLED-CONVERT] 시장가 매수 실패 | uuid={orig_uuid}")
            return out
        mqty, mprice = float(result.get("qty") or 0.0), float(result.get("price") or cur)
        total = float(executed_qty) + mqty
        avg = ((float(executed_qty) * float(executed_avg)) + mqty * mprice) / total if total > 0 else mprice
        engine.position.apply_entry(qty=total, avg_price=avg, entry_bar=engine.bar_count, entry_ts=now,
                                    source="bot_market_convert")
        # ✅ WO-26: 미체결 시장가 전환 확정 — 원 주문 meta 의 약매수 표식을 전환 주문 uuid 로 옮긴다
        if conv_meta.get("weak_entry"):
            from core.weak_entry import record_weak_entry
            record_weak_entry(engine.position, conv_meta["weak_entry"], result.get("uuid"), conv_meta.get("bar_time"),
                              user_id=user_id, ticker=ticker)
        engine._pending_buy_weak = None
        engine._pending_buy_uuid = None
        engine._pending_buy_bar = None
        engine._pending_buy_wait_bars = 3
        try:
            engine.position.set_pending(False)
        except Exception:
            pass
    out.update(converted=True, reason="전환", result={"uuid": result.get("uuid"), "qty": mqty, "price": mprice})
    logger.info(
        f"✅ [UNFILLED-CONVERT] 시장가 전환 | from={orig_uuid} to={result.get('uuid')} 주문가={limit_price} 현재가={cur} "
        f"차이={gap:.2f}% ≤ 허용 {max_gap:.2f}% | 시장가 qty={mqty:.6f} + 부분 체결 {executed_qty:.6f} → 진입 {total:.6f}@{avg:.4f}"
    )
    return out


class StrategyEngine:
    """
    증분 기반 전략 엔진 (Backtest 없음)

    동작 흐름:
    1. 새 봉 확정 시 on_new_bar() 호출
    2. 버퍼에 추가
    3. 지표 증분 갱신
    4. 전략 평가
    5. 주문 실행 (중복 방지)
    """

    def __init__(
        self,
        buffer: CandleBuffer,
        indicators: IndicatorState,
        position: PositionState,
        strategy,  # IncrementalMACDStrategy 또는 IncrementalEMAStrategy
        trader: UpbitTrader,
        user_id: str,
        ticker: str,
        strategy_type: str = "MACD",
        q: Optional[queue.Queue] = None,  # 이벤트 큐 (Streamlit용)
        interval_sec: int = 60,  # 봉 간격 (초)
        take_profit: float = 0.03,  # 익절 비율
        stop_loss: float = 0.01,  # 손절 비율
        trailing_stop_pct: Optional[float] = None,  # Trailing Stop 비율
    ):
        """
        Args:
            buffer: CandleBuffer 인스턴스
            indicators: IndicatorState 인스턴스
            position: PositionState 인스턴스
            strategy: 증분 전략 객체
            trader: UpbitTrader 인스턴스
            user_id: 사용자 ID
            ticker: 티커 (예: KRW-PEPE)
            strategy_type: 전략 타입 (MACD/EMA)
            q: 이벤트 큐 (선택)
            interval_sec: 봉 간격 (초)
            take_profit: 익절 비율
            stop_loss: 손절 비율
            trailing_stop_pct: Trailing Stop 비율
        """
        self.buffer = buffer
        self.indicators = indicators
        self.position = position
        self.strategy = strategy
        self.trader = trader
        # ✅ SP4 — trader 에 strategy 참조 주입 (audit_trades sl/tp/ts_pct 적재용)
        try:
            if hasattr(self.trader, "set_strategy_ref"):
                self.trader.set_strategy_ref(strategy)
        except Exception:
            pass
        self.user_id = user_id
        self.ticker = ticker
        self.strategy_type = strategy_type.upper()
        self.q = q
        self.interval_sec = interval_sec
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.trailing_stop_pct = trailing_stop_pct

        self.last_bar_ts = None
        self.bar_count = 0

        # ✅ Issue #10: 스레드 락 (audit 로깅 ~ execution 원자적 보장)
        self._execution_lock = threading.Lock()

        # ✅ WO-8b (2026-09-18): 활성 엔진 레지스트리 등록 (force_buy uuid 등록용)
        with _active_engines_lock:
            _active_engines[(self.user_id, self.ticker)] = self

        # ✅ WO-6 (2026-08-25): 봉당 매매 판단 1회 강제.
        # 실시간 평가(backfill_mode=False)가 매매 판단을 실행한 봉의 ts 이력.
        # BACKFILL 재평가는 등록하지 않아 순서가 꼬여도 실시간 평가가 차단되지 않음.
        # OrderedDict 로 등록 순서를 유지하고, 상한 초과 시 popitem(last=False)로 정리.
        self._evaluated_bar_ts: "OrderedDict[datetime, None]" = OrderedDict()

        # ✅ WO-2 (2026-09-02): 매수 지연 발주 큐. 매도 경로는 이 큐를 우회한다.
        # 한 번에 1건만 유지 (동시성 정책). 새 매수 결정이 오면 SUPERSEDED 로 교체.
        from core.pending_order import PendingOrderQueue
        self._pending_orders = PendingOrderQueue()

        # ✅ 고정가 매수(Limit) 미체결 추적 — 봉 경계 통과 시 pending 자동 해제용.
        # Reconciler가 봉 간격 초과 미체결을 cancel 처리하므로 다음 봉에서 풀어준다.
        self._pending_buy_uuid: Optional[str] = None
        self._pending_buy_bar: Optional[int] = None
        # ✅ SP6 — 대기 봉 수 (사용자 conditions, 기본 3)
        self._pending_buy_wait_bars: int = 3
        # ✅ WO-26: 지정가 매수 대기 중 약매수 표식 (weak_entry dict, bar_time) — 체결 확정 때 기록
        self._pending_buy_weak = None

        # ✅ 2차 T5: PULLBACK 전용 상태 (EMA·MACD 는 읽지 않는다)
        self.pullback_indicators = None   # live_loop._pullback_seed_warmup 이 채움
        self.pullback_ring = None
        self._pullback_sizing_base: Optional[float] = None  # 이 거래 배분 기준(1회차 때 고정, T6: pullback_state 에 저장)
        self._pullback_buy_fail_bar: Optional[int] = None
        self._pullback_buy_placed = False
        self._pullback_pending_set = False  # 검수 반영: 이 판정에서 set_pending(True) 를 켰는지(예외 시 되돌림용)
        self._pullback_polluted_notified = False
        # ✅ 2차 T6: 분할 상태(pullback_state)·체결 반영(F2)·지갑 대조 — EMA·MACD 는 읽지 않는다
        self._pending_split: Optional[Dict[str, Any]] = None  # LIVE 분할 주문 체결 대기 {uuid·round·bar·base_qty·base_cost…}
        self._pb_qty: float = 0.0              # 이 전략 분할 체결 수량 합(지갑 대조 기준)
        self._pb_cost: float = 0.0             # 분할 체결 원가 합(수수료 제외) — 평단 = cost/qty
        self._pullback_desync = False          # 지갑·분할 상태 어긋남 → 추가 분할매수 멈춤(청산·지갑 0 으로 해제)
        self._pullback_realized_pnl: float = 0.0  # 전환 뒤 이 전략 실현 손익 합(복리 배분 기준)
        self._pullback_buy_fail_ts = None      # 쿨다운 실패 봉 시각(재시작 복원용, 결정 1028-03 다)
        self._pullback_params_sha: Optional[str] = None
        self._pullback_state_err_notified = False
        self._pullback_persist_blocked = False  # 수정 1회차: 복원 읽기 오류·other_market → 저장 행 보존
        self.pullback_restore_result: Optional[Dict[str, Any]] = None

        # ✅ SP-PI-2: OrderReconciler LIMIT BUY 전량 체결 콜백 등록
        # LIVE 모드 한정 — TEST 모드는 reconciler 미가동
        try:
            from engine.reconciler_singleton import get_reconciler
            reconciler = get_reconciler()
            reconciler.register_fill_callback(self.user_id, self.ticker, self._on_limit_fill)
            # ✅ [Fix 4] HTS 매수 감지 콜백 등록 — Reconciler → position_state.avg_price 즉시 동기화
            reconciler.register_hts_detect_callback(self.user_id, self.ticker, self._on_hts_detect)
        except Exception as e:
            # ✅ [Phase 1-F/P2-5] 콜백 등록 실패는 HTS 즉시 동기화 무력화 → CRITICAL 승격
            err_msg = (
                f"❌ [ENGINE] Reconciler callback 등록 실패: {e} | "
                f"HTS-DETECT 즉시 동기화 무력화 상태. sync_from_wallet Fix 1 만 방어."
            )
            logger.critical(err_msg)
            try:
                from services.db import insert_log
                insert_log(self.user_id, "ERROR", err_msg)
            except Exception:
                pass
            try:
                from services.notifier import send as _notify_send, LEVEL_CRITICAL
                _notify_send(
                    LEVEL_CRITICAL,
                    f"🚨 Reconciler 콜백 등록 실패 — {self.ticker}",
                    (
                        f"에러: {e}\n\n"
                        f"HTS 매수 발생 시 즉시 동기화 불가.\n"
                        f"봉 단위 sync_from_wallet 만 방어.\n"
                        f"엔진 재시작 검토 필요."
                    ),
                    dedupe_key=f"reconciler_reg_fail:{self.ticker}",
                    dedupe_ttl=600,
                )
            except Exception:
                pass

    def _on_hts_detect(self, *, avg_price: float, qty: float, reason: str) -> None:
        """
        ✅ [Fix 4] OrderReconciler → StrategyEngine HTS-DETECT callback.

        HTS 매수 감지 시 Reconciler 스레드에서 호출. position_state.avg_price 를
        즉시 세팅하여 다음 SELL 평가에서 SL/TP/TS 필터가 정상 작동하도록 보장.

        2026-07-24 사건 근본 원인: HTS 매수 후 avg_price=None 인 상태로 방치 →
        모든 SELL 필터가 pnl_pct=None 로 조기 return → 2일 반 동안 매도 무력화.

        Thread safety:
            - `_execution_lock` 사용으로 봉 처리 스레드와 원자성 보장
            - 이미 avg_price 세팅되어 있으면 덮어쓰기 (Upbit avg_buy_price 가 진실의 소스)
        """
        with self._execution_lock:
            if getattr(self, "strategy_type", None) == "PULLBACK" and getattr(self, "_pending_split", None) is not None:
                # ✅ 2차 T6 (F1): 30초 창을 넘겨 늦게 보인 지갑 증가라도 분할 주문 체결 대기 중이면 앱 매수로 보지 않는다
                #   (평단·수량은 체결 콜백 또는 체결 대기 시간 초과 때 지갑 기준으로 맞춤)
                logger.warning(
                    f"[PULLBACK-SYNC] 분할 체결 대기 중 → 앱 매수 감지 무시 | reason={reason} qty={qty} "
                    f"avg={avg_price} pending_uuid={self._pending_split.get('uuid')}"
                )
                return
            try:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                old_avg = self.position.avg_price
                # 최신 Upbit avg_buy_price 로 갱신 (HTS_BUY_ADD 시에도 반영)
                self.position.avg_price = float(avg_price)
                self.position.qty = float(qty)
                # entry_ts / entry_bar 는 최초 감지 시점만 세팅 (이미 있으면 유지)
                if self.position.entry_ts is None:
                    self.position.entry_ts = datetime.now(ZoneInfo("Asia/Seoul"))
                if self.position.entry_bar is None:
                    self.position.entry_bar = self.bar_count
                # ✅ [Phase 1-F/P2-3] HTS_BUY_ADD 시 highest 재계산 (avg 변경으로 옛 highest 무의미)
                if str(reason).upper() == "HTS_BUY_ADD":
                    old_highest = self.position.highest_price
                    old_since_entry = self.position.highest_since_entry
                    self.position.highest_price = None
                    self.position.highest_since_entry = None
                    self.position.trailing_armed = False
                    self.position.trailing_fixed_amount = None
                    self.position.trailing_activation_price = None
                    logger.warning(
                        f"🔄 [HTS-DETECT-CALLBACK] HTS_BUY_ADD 로 avg 변경 → Trailing 상태 리셋 | "
                        f"old_highest={old_highest} old_since_entry={old_since_entry} "
                        f"→ 모두 None. 다음 봉부터 새 avg 기준 추적 재개."
                    )
                    # ✅ WO-26: 같은 정책 — 섞인 평균가 포지션에는 약매수 축소 익절을 적용하지 않는다
                    self.position.clear_weak_entry(reason="hts_buy_add")
                logger.warning(
                    f"✅ [HTS-DETECT-CALLBACK] position_state.avg_price 동기화 완료 | "
                    f"reason={reason} | old_avg={old_avg} → new_avg={avg_price:.6f} | "
                    f"qty={qty:.6f} | ticker={self.ticker}"
                )
            except Exception as e:
                logger.error(f"[HTS-DETECT-CALLBACK] position 동기화 실패: {e}", exc_info=True)

    def _on_limit_fill(self, *, uuid: str, executed_price: float,
                       executed_qty: float, executed_ts, state: str = "FILLED") -> None:
        """
        ✅ SP-PI-2: OrderReconciler → StrategyEngine fill callback.

        LIMIT BUY 전량 체결(FILLED) 시 OrderReconciler 스레드에서 호출.
        _pending_buy_uuid 와 일치하는 경우에만 apply_entry(source="bot_limit_fill")
        발동. buy_market 등 다른 경로의 uuid 는 자동 스킵.

        ✅ 2차 T6: reconciler 가 state(FILLED | 체결량 있는 CANCELED)를 넘긴다.
          - uuid 가 PULLBACK 분할 주문(_pending_split)이면 FILLED·CANCELED 둘 다 체결 실수량·평단으로 분할 반영.
          - 그 밖은 state == "FILLED" 일 때만 아래 지금 경로(EMA 지정가 부분 체결 뒤 CANCELED 는 처리 안 함 — D6 그대로).

        Thread safety:
            - `_execution_lock` 사용으로 봉 처리 스레드와 원자성 보장
            - position.apply_entry 는 attribute set 만 수행 (부작용 없음)
        """
        if getattr(self, "strategy_type", None) == "PULLBACK":  # 최소 stub 엔진(__new__) 호환
            # 수정 1회차: 락을 먼저 잡고 그 안에서 판정 — 콜백이 _pending_split 등록(봉 처리 락 안) 전에 와도
            # 락을 기다렸다가 등록 뒤에 반영된다(경합으로 체결을 잃지 않음).
            with self._execution_lock:
                _sp = getattr(self, "_pending_split", None)
                if _sp is not None and uuid == _sp.get("uuid"):
                    self._pullback_apply_fill(uuid=uuid, executed_price=executed_price,
                                              executed_qty=executed_qty, executed_ts=executed_ts, state=state)
                    return
        if state != "FILLED":
            logger.debug(f"[LIMIT-FILL] state={state} → 지정가 경로 아님(부분 체결 미처리 D6) | uuid={uuid}")
            return
        with self._execution_lock:
            if self._pending_buy_uuid is None or uuid != self._pending_buy_uuid:
                logger.debug(
                    f"[LIMIT-FILL] uuid mismatch → skip | pending={self._pending_buy_uuid} "
                    f"received={uuid}"
                )
                return

            try:
                self.position.apply_entry(
                    qty=executed_qty,
                    avg_price=executed_price,
                    entry_bar=self.bar_count,
                    entry_ts=executed_ts,
                    source="bot_limit_fill",
                )
                ts_iso = (
                    executed_ts.isoformat()
                    if hasattr(executed_ts, "isoformat") else str(executed_ts)
                )
                logger.info(
                    f"✅ [LIMIT-FILL] apply_entry 완료 | uuid={uuid} qty={executed_qty:.6f} "
                    f"price={executed_price:.2f} entry_bar={self.bar_count} ts={ts_iso}"
                )
            except Exception as e:
                logger.error(f"[LIMIT-FILL] apply_entry 실패 uuid={uuid}: {e}", exc_info=True)
                return

            # ✅ WO-26: 지정가 체결 확정 — 약매수면 override + 포지션 meta
            _pw = getattr(self, "_pending_buy_weak", None)
            if _pw:
                try:
                    from core.weak_entry import record_weak_entry
                    record_weak_entry(self.position, _pw[0], uuid, _pw[1], user_id=self.user_id, ticker=self.ticker)
                except Exception as e:
                    logger.error(f"[WEAK-ENTRY] 지정가 체결 기록 실패 uuid={uuid}: {e}", exc_info=True)
            self._pending_buy_weak = None

            # ✅ pending 해제 — _maybe_release_limit_pending 이 다시 발동하지 않도록
            self._pending_buy_uuid = None
            self._pending_buy_bar = None
            self._pending_buy_wait_bars = 3
            try:
                self.position.set_pending(False)
            except Exception:
                pass

            # ✅ 이벤트 큐 BUY 전송 (미체결 시점엔 미전송, 여기서 최종 전송)
            if self.q is not None:
                try:
                    self.q.put((
                        executed_ts,
                        "BUY",
                        {
                            "uuid": uuid,
                            "price": executed_price,
                            "qty": executed_qty,
                            "source": "bot_limit_fill",
                        },
                    ))
                except Exception as e:
                    logger.warning(f"[LIMIT-FILL] event queue put 실패: {e}")

    def is_new_bar(self, bar: Bar) -> bool:
        """
        중복 봉 방지

        Args:
            bar: 체크할 봉

        Returns:
            bool: 새 봉이면 True
        """
        return bar.ts != self.last_bar_ts

    def _maybe_release_limit_pending(self):
        """
        고정가 매수(Limit) 미체결 timeout 자동 해제.

        - buy_limit 성공 시 _pending_buy_uuid/_pending_buy_bar 저장.
        - 새 봉 진입(bar_count 증가)에서 시작 봉을 넘긴 경우, Reconciler가
          봉 마감 시점에 cancel 처리했을 것이므로 pending_order=False 로 풀고
          다음 봉 시그널 재평가를 허용한다.
        - 봉 같은 사이클 안에서는 풀지 않는다(체결/취소 polling 진행 중).
        """
        if self._pending_buy_uuid is None or self._pending_buy_bar is None:
            return
        # ✅ SP6 — wait_bars 만큼 봉 경과 후 해제 (기본 3봉)
        if self.bar_count > self._pending_buy_bar + (self._pending_buy_wait_bars - 1):
            logger.info(
                f"🎯 LIMIT BUY pending 자동 해제 | uuid={self._pending_buy_uuid} "
                f"start_bar={self._pending_buy_bar} now_bar={self.bar_count} "
                f"wait_bars={self._pending_buy_wait_bars} "
                f"(Reconciler가 봉 마감 시점 cancel 처리한 것으로 간주)"
            )
            try:
                self.position.set_pending(False)
            except Exception as e:
                logger.warning(f"[ENGINE] LIMIT pending 해제 실패: {e}")
            self._pending_buy_uuid = None
            self._pending_buy_bar = None
            self._pending_buy_wait_bars = 3  # 다음 매수를 위해 기본값 복원

    def _record_invariant_snapshot(self, *, context: str = "unknown") -> None:
        """
        ✅ [Phase 3-F] 매 봉 상태 스냅샷 기록 (system_health 페이지 데이터 소스).

        - 매매 흐름 절대 방해 X: 전체 try/except 로 감쌈.
        - check_position_invariants() 결과가 있으면 violation_code/msg 도 기록.
        - wallet 실측값 (qty, avg) 도 함께 기록해 memory 와 대비 가능.
        """
        try:
            from services.invariant_monitor import record_snapshot
            from core.position_invariants import check_position_invariants

            # wallet 실측 (LIVE 만; TEST 는 None)
            wallet_qty = None
            wallet_avg = None
            if not getattr(self.trader, "test_mode", True):
                try:
                    wallet_qty = float(self.trader._coin_balance(self.ticker))
                    # avg_buy_price 실측 시도 (실패 시 None)
                    for b in (self.trader.upbit.get_balances() or []):
                        sym = self.ticker.split("-")[-1].upper() if "-" in self.ticker else self.ticker.upper()
                        if str(b.get("currency", "")).upper() == sym:
                            _v = float(b.get("avg_buy_price") or 0.0)
                            if _v > 0:
                                wallet_avg = _v
                            break
                except Exception:
                    pass

            # invariant 검증
            violation = check_position_invariants(self.position, context=context)
            v_code = violation[0] if violation else None
            v_msg = violation[1] if violation else None

            record_snapshot(
                self.position,
                user_id=self.user_id,
                ticker=self.ticker,
                wallet_qty=wallet_qty,
                wallet_avg=wallet_avg,
                violation_code=v_code,
                violation_msg=v_msg,
            )
        except Exception as e:
            # 무해 (관찰 계층은 절대 매매 흐름 방해 X)
            logger.debug(f"[ENGINE] invariant snapshot 기록 실패 (무해): {e}")

    def _fetch_upbit_avg_buy_price(self) -> Optional[float]:
        """✅ WO-22: Upbit 잔고의 avg_buy_price 직접 조회 (LIVE 만, 실패 시 None — 기존 sync_from_wallet 2순위와 같은 방식)."""
        if getattr(self.trader, "test_mode", True):
            return None
        try:
            sym = self.ticker.split("-")[-1].strip().upper() if self.ticker else self.ticker
            for b in (self.trader.upbit.get_balances() or []):
                if str(b.get("currency", "")).upper() == sym:
                    v = float(b.get("avg_buy_price") or 0.0)
                    return v if v > 0 else None
        except Exception as e:
            logger.warning(f"[POSITION-SYNC] Upbit avg_buy_price 조회 실패: {e}")
        return None

    def _record_external_sell(self, qty, entry_price) -> None:
        """
        ✅ WO-22: 지갑 0 으로 포지션을 닫을 때 외부 매도 1행 (audit_trades type='HTS_SELL', 화면 "외부 매도").
        가격은 알 수 없어 비워 둔다. type 이 'SELL' 이 아니므로 손익 집계(type='SELL')에는 들어가지 않는다.
        """
        try:
            from services.db import insert_trade_audit
            insert_trade_audit(
                user_id=self.user_id, ticker=self.ticker, interval_sec=self.interval_sec, bar=self.bar_count,
                kind="HTS_SELL", reason="HTS_SELL", price=None, macd=None, signal=None,
                entry_price=float(entry_price) if entry_price is not None else None,
                entry_bar=self.position.entry_bar, bars_held=None, tp=None, sl=None, highest=None,
                ts_pct=None, ts_armed=None, qty=float(qty) if qty is not None else None,
                note="외부 매도 — 지갑 잔고 0 감지 (앱 매도 등). 체결 가격은 알 수 없음",
                strategy_type=getattr(self, "strategy_type", None),  # ✅ 2차 T7: 그때 엔진 활성 전략
            )
            logger.info(f"[POSITION-SYNC] 외부 매도 기록 (audit_trades HTS_SELL) | qty={qty} entry={entry_price}")
        except Exception as e:
            logger.error(f"[POSITION-SYNC] 외부 매도 기록 실패: {e}")

    def _reconcile_position_with_wallet(self) -> Optional[str]:
        """
        지갑 잔고 기반 PositionState 동기화

        - 지갑과 메모리 상태 불일치 감지 시 강제 동기화
        - force_liquidate, 수동 거래 등 외부 요인에 대응
        - 매 봉마다 호출되어 방어적으로 상태 일관성 유지

        Returns (WO-12 C7, WO-22 이름 변경): 외부 매수 복구 성공 시 진입가 출처("upbit_avg" / "account_positions" / "orders"),
            그 외 None. 기존 호출부는 반환값을 쓰지 않는다 (동작 무변경).
        """
        try:
            # 1. 실제 지갑 잔고 조회
            actual_balance = float(self.trader._coin_balance(self.ticker))
            has_coins_in_wallet = actual_balance >= 1e-6

            # 2. 메모리 상태
            memory_has_position = self.position.has_position

            # ✅ WO-12 C7: 부팅 복원([BOOT-SEED])으로 이미 맞춘 상태면 첫 봉에서 1회 "이미 일치 → 스킵" 기록
            _bsv = getattr(self, "_boot_seed_verify", None)
            if _bsv and has_coins_in_wallet == memory_has_position:
                logger.info(
                    f"[POSITION-SYNC] 이미 일치 → 스킵 (boot_seed source={_bsv.get('source')}) | "
                    f"qty={self.position.qty:.6f} entry={self.position.avg_price} wallet={actual_balance:.6f}"
                )
                self._boot_seed_verify = None

            # 3. 불일치 감지 및 처리
            if has_coins_in_wallet != memory_has_position:
                logger.warning(
                    f"🔄 [POSITION-SYNC] Wallet-Memory 불일치 감지! "
                    f"wallet_has_coins={has_coins_in_wallet} (balance={actual_balance:.6f}), "
                    f"memory_has_position={memory_has_position}"
                )

                # Case 1: 지갑에 코인 없지만 메모리는 포지션 있다고 판단
                # → 강제 청산(force_liquidate) 또는 외부 매도로 인한 불일치
                if not has_coins_in_wallet and memory_has_position:
                    logger.warning(
                        f"🚨 [POSITION-SYNC] 강제 포지션 종료 실행: "
                        f"지갑 잔고={actual_balance:.6f} (거의 0) "
                        f"but memory shows has_position=True (qty={self.position.qty:.6f})"
                    )
                    # ✅ WO-22: 외부 매도(앱 매도 등) 기록 — 가격은 알 수 없어 비워 둔다.
                    #   get_last_open_buy_order / get_last_open_buy_trade 가 이 행을 보고 옛 봇 BUY 를 청산된 것으로 본다.
                    self._record_external_sell(self.position.qty, self.position.avg_price)
                    # PositionState 강제 리셋 (매도 완료 처리)
                    self.position.close_position(ts=None, reason="position_sync_wallet_zero")  # ts는 None (정확한 시각 불명), WO-18 플래그 해제 사유
                    logger.info(
                        f"✅ [POSITION-SYNC] PositionState 리셋 완료 → has_position=False"
                    )

                # Case 2: 지갑에 코인 있지만 메모리는 포지션 없다고 판단
                # → 외부 매수(force_buy, HTS 매수) 또는 엔진 재시작 후 복구 실패
                elif has_coins_in_wallet and not memory_has_position:
                    logger.warning(
                        f"⚠️ [POSITION-SYNC] 외부 매수 감지: "
                        f"지갑 잔고={actual_balance:.6f} "
                        f"but memory shows has_position=False. "
                        f"진입가 복구 시도 (1순위: Upbit avg_buy_price 캐시)..."
                    )

                    # ✅ WO-22 (2026-10-05): 진입가 우선순위
                    #   1) Upbit avg_buy_price 직접 조회 (지금 지갑의 실제 평균가)
                    #   2) account_positions.entry_price (Reconciler 가 1분마다 채우는 캐시 — 직전 매수면 아직 0 일 수 있음)
                    #   3) orders 마지막 봇 BUY (마지막 수단) — 그 BUY 의 체결 수량이 지갑 수량과 같을 때만
                    #   근거: 2026-10-05 10:59:05 앱 재매수(766) 를 앱 매도로 이미 청산된 봇 BUY(777) 로 복원 → STOP_LOSS 오매도
                    try:
                        from services.db import get_position_entry_price, get_last_open_buy_order

                        entry_price = None
                        entry_bar = None
                        source = None

                        # 1순위: Upbit avg_buy_price 직접 조회 (LIVE 만)
                        upbit_avg = self._fetch_upbit_avg_buy_price()
                        if upbit_avg is not None and upbit_avg > 0:
                            entry_price = float(upbit_avg)
                            source = "upbit_avg"

                        # 2순위: Reconciler 가 캐시한 account_positions.entry_price
                        if entry_price is None:
                            cached_avg = get_position_entry_price(self.user_id, self.ticker)
                            if cached_avg is not None and cached_avg > 0:
                                entry_price = float(cached_avg)
                                source = "account_positions"

                        # 3순위(마지막 수단): 봇의 마지막 미청산 BUY — 체결 수량이 지갑 수량과 같을 때만
                        if entry_price is None:
                            db_result = get_last_open_buy_order(self.ticker, self.user_id)
                            if db_result:
                                ep = db_result.get("avg_price") or db_result.get("price")
                                buy_qty = db_result.get("executed_volume")
                                if ep is not None and buy_qty is not None and abs(float(buy_qty) - actual_balance) <= max(1e-6, actual_balance * 1e-6):
                                    entry_price = float(ep)
                                    entry_bar = db_result.get("entry_bar")
                                    source = "orders"
                                elif ep is not None:
                                    logger.warning(
                                        f"[POSITION-SYNC] orders 마지막 봇 BUY 수량 불일치 → 진입가로 쓰지 않음 | "
                                        f"buy_qty={buy_qty} wallet={actual_balance:.6f} price={ep}"
                                    )

                        if entry_price is not None:
                            logger.info(f"[POSITION-SYNC] entry_price={entry_price} (출처: {source})")

                        if entry_price is not None and entry_price > 0:
                            # ✅ SP-PI-1: P2 자동 복구 — apply_entry 통합 API 사용
                            # D2 결정: wallet_sync 는 now_kst() 를 entry_ts 로 사용
                            # (매 봉 sync 이므로 실시각과 큰 차이 없음. P1 정상 매수 시엔 이 경로가
                            #  더 이상 상시 발동하지 않음 — SP-PI-2 fill callback 이 P1 상당 처리 수행)
                            from datetime import datetime
                            from zoneinfo import ZoneInfo
                            _p2_entry_ts = datetime.now(ZoneInfo("Asia/Seoul"))
                            self.position.apply_entry(
                                qty=actual_balance,
                                avg_price=float(entry_price),
                                entry_bar=int(entry_bar) if entry_bar is not None else self.bar_count,
                                entry_ts=_p2_entry_ts,
                                source="wallet_sync",
                            )
                            # ✅ WO-26: 약매수 표식 복원 (마지막 봇 BUY uuid 일치 시만, 불일치면 삭제·WARNING)
                            try:
                                from core.weak_entry import restore_weak_entry
                                restore_weak_entry(self.position, source="wallet_sync",
                                                   user_id=self.user_id, ticker=self.ticker)
                            except Exception as _we:
                                logger.error(f"[WEAK-ENTRY] wallet_sync 복원 실패: {_we}")
                            logger.info(
                                f"✅ [POSITION-SYNC] 자동 복구 성공 (source={source}, api=apply_entry): "
                                f"qty={actual_balance:.6f}, entry_price={entry_price:.2f}, "
                                f"entry_bar={self.position.entry_bar}, entry_ts={_p2_entry_ts.isoformat()}"
                            )
                            return source
                        else:
                            # 신뢰 가능한 진입가 없음 → SELL 발동 금지 (HOLD 유지). 봇 의사결정 차단.
                            logger.error(
                                f"❌ [POSITION-SYNC] 신뢰 가능한 진입가 없음 "
                                f"(avg_buy_price 캐시 부재 + 미청산 BUY 부재). "
                                f"자동 매도 방지를 위해 has_position=False 유지. "
                                f"수동 정리 또는 LIVE 모드 재진입(검증) 필요."
                            )
                    except Exception as e:
                        logger.error(f"❌ [POSITION-SYNC] 자동 복구 실패: {e}")

        except Exception as e:
            logger.error(f"[POSITION-SYNC] 동기화 실패: {e}")

    def on_new_bar(self, bar: Bar):
        """
        새 봉 확정 시 처리 (핵심 로직)

        절대 규칙:
        1. 버퍼에 추가
        2. 지표 증분 갱신
        3. 전략 평가
        4. 주문 실행

        Args:
            bar: 확정된 봉 (is_closed=True)
        """
        # ✅ 2차 T5: PULLBACK 은 형성 중 봉 경로(WS·LEGACY_LOCAL)에서 판정하지 않는다 (NOOP, 지표·버퍼 불변)
        if self.strategy_type == "PULLBACK":
            logger.debug(f"[PULLBACK] on_new_bar 경로는 판정 안 함 (확정 봉 마감에서만) | ts={bar.ts}")
            return

        # ✅ 확정 봉만 처리
        if not bar.is_closed:
            logger.warning(f"⚠️ 미확정 봉 무시: {bar.ts}")
            return

        # ✅ 중복 방지
        if not self.is_new_bar(bar):
            logger.debug(f"⏭️ 중복 봉 무시: {bar.ts}")
            return

        # ✅ [Phase 1-C/P1-2] Position-Wallet 동기화를 execution_lock 안으로 이동
        # 감사 결과: 락 밖 실행 시 Reconciler HTS-DETECT 콜백(_on_hts_detect, 락 획득)과
        # race → apply_entry 가 콜백 최신 avg 를 DB 캐시값으로 덮어써 Trailing Stop 오작동.
        with self._execution_lock:
            # ✅ Position-Wallet 동기화 체크 (전략 평가 전)
            # force_liquidate, 수동 거래 등으로 인한 불일치 자동 해결
            self._reconcile_position_with_wallet()

        # 1. 버퍼 추가
        self.buffer.append(bar)
        self.last_bar_ts = bar.ts
        self.bar_count += 1

        # ✅ 봉 경계 통과 시 고정가 매수 미체결 pending 자동 해제 (Reconciler가 cancel 처리)
        self._maybe_release_limit_pending()

        # 2. 지표 증분 갱신 ★ 핵심: 전체 재계산 없음
        self.indicators.update_incremental(bar.close, bar.ts)  # ✅ WO-26: 봉 시각 → 마지막 D/C 시각

        # 3. 전략 평가 및 실행 (스레드 락으로 원자적 보장)
        # ✅ Issue #10: audit 로깅과 execution 사이 position 상태 변경 방지
        with self._execution_lock:
            # ✅ 포지션 상태 동기화 (평가 직전)
            logger.debug(f"[ENGINE] 평가 시작 전 포지션 상태 동기화 | bar={self.bar_count}")
            self.position.sync_from_wallet()
            has_position_before_eval = self.position.has_position

            # ✅ [Phase 3-F] Invariant 스냅샷 기록 (매 봉 관찰 계층)
            # 매매 흐름 절대 방해 X (실패 시 무해). system_health 페이지 조회용.
            self._record_invariant_snapshot(context="pre_eval")

            # 포지션 유무에 따라 적절한 EMA 값 전달
            is_buy_eval = not self.position.has_position
            ind_snapshot = self.indicators.get_snapshot(is_buy_eval=is_buy_eval)
            action = self.strategy.on_bar(bar, ind_snapshot, self.position, self.bar_count)

            # 로그 출력
            self._log_bar_evaluation(bar, ind_snapshot, action)

            # 이벤트 큐에 LOG 전송 (Streamlit용)
            if self.q is not None:
                self._send_log_event(bar, ind_snapshot)

            # ✅ 포지션 상태 재확인 (audit 로깅 직전)
            logger.debug(f"[ENGINE] Audit 로깅 전 포지션 상태 재확인 | bar={self.bar_count}")
            self.position.sync_from_wallet()
            has_position_before_audit = self.position.has_position

            if has_position_before_eval != has_position_before_audit:
                logger.error(
                    f"🚨 [ENGINE] 포지션 상태 불일치 감지 (평가~Audit) | "
                    f"before_eval={has_position_before_eval} → before_audit={has_position_before_audit} | "
                    f"bar={self.bar_count}"
                )

            # 감사 로그 기록 (매 봉마다)
            self._record_audit_log(bar, ind_snapshot, action)

            # 4. 주문 실행
            # ✅ 포지션 상태 최종 확인 (execution 직전)
            logger.debug(f"[ENGINE] Execution 전 포지션 상태 최종 확인 | bar={self.bar_count}")
            self.position.sync_from_wallet()
            has_position_before_exec = self.position.has_position

            if has_position_before_audit != has_position_before_exec:
                logger.error(
                    f"🚨 [ENGINE] 포지션 상태 불일치 감지 (Audit~Exec) | "
                    f"before_audit={has_position_before_audit} → before_exec={has_position_before_exec} | "
                    f"bar={self.bar_count}"
                )

            self.execute(action, bar, ind_snapshot)

            # ✅ 디버그: 최종 포지션 상태 로깅
            logger.debug(
                f"[ENGINE] 평가/실행 완료 | bar={self.bar_count} | "
                f"final_has_position={self.position.has_position} | "
                f"action={action.value if action else 'NONE'}"
            )

    def on_new_bar_confirmed(
        self,
        bar: Bar,
        full_series: 'pd.DataFrame',
        diff_summary: Dict
    ):
        """
        REST 확정 봉 처리 (Reconcile 기반)

        🔒 리스크 헷지:
        - REST 실패 시 local 유지
        - changed_ts 있어도 지표는 증분만 (WO-17 (P): 부분 재계산 제거)
        - 확정 봉으로만 매매 판단

        Args:
            bar: REST 확정된 봉
            full_series: REST 전체 시계열
            diff_summary: Reconcile 결과 {changed_count, changed_ts, rest_failed}
        """
        # ✅ 2차 T5: PULLBACK 은 전용 경로 (EMA·MACD 아래 본문은 그대로)
        if self.strategy_type == "PULLBACK":
            return self._on_new_bar_confirmed_pullback(bar, full_series, diff_summary)

        # ✅ 확정 봉 검증
        if not bar.is_closed:
            logger.error(f"[ENGINE] 미확정 봉 거부 | {bar.ts}")
            return

        # ✅ 중복 방지 (BACKFILL 모드는 제외)
        # Issue #9: BACKFILL은 이미 처리된 봉을 재평가하여 audit 로그를 UPDATE하므로
        # 중복 체크를 우회해야 함
        backfill_mode = diff_summary.get("backfill_mode", False)

        # ✅ WO-6 감사 누락 수정 (2026-08-30): 엔진 입구 진단 로그.
        # last_bar_ts 갱신 순서와 조기 반환 지점을 관측·재발 감지용으로 남긴다.
        logger.info(
            f"[ENGINE-ENTRY] on_new_bar_confirmed | bar.ts={bar.ts} | "
            f"last_bar_ts={self.last_bar_ts} | backfill_mode={backfill_mode}"
        )

        if not backfill_mode and not self.is_new_bar(bar):
            # ✅ WO-6 감사 누락 수정 (2026-08-30): debug → info 승격.
            # 이 조기 반환이 실측에서 얼마나 자주 발생하는지 관측.
            logger.info(
                f"[ENGINE-SKIP-DUP] 중복 봉 무시 (is_new_bar False) | "
                f"bar.ts={bar.ts} == last_bar_ts={self.last_bar_ts}"
            )
            return

        # ✅ [Phase 1-C/P1-2] Position-Wallet 동기화를 execution_lock 안으로 이동
        # (동일 이유: Reconciler HTS-DETECT 콜백과 race 방지)
        with self._execution_lock:
            self._reconcile_position_with_wallet()

        # 1. 버퍼 추가 (BACKFILL 모드는 제외)
        # Issue #9: BACKFILL은 과거 봉 재평가이므로 버퍼 추가/bar_count 증가 불필요
        # ✅ WO-6 감사 누락 수정 (2026-08-30): last_bar_ts 갱신은 판단·감사 완료
        # 이후로 이동 (아래 라인 720 부근). 여기서는 버퍼 추가와 bar_count 증가만.
        if not backfill_mode:
            self.buffer.append(bar)
            self.bar_count += 1
            # ✅ 봉 경계 통과 시 고정가 매수 미체결 pending 자동 해제 (Reconciler가 cancel 처리)
            self._maybe_release_limit_pending()
        else:
            logger.info(f"[BACKFILL] 버퍼 추가 스킵 (재평가 모드) | ts={bar.ts} | close={bar.close:.0f}")

        # 2. Reconcile 변경 처리
        rest_failed = diff_summary.get("rest_failed", False)
        changed_count = diff_summary.get("changed_count", 0)
        changed_ts = diff_summary.get("changed_ts", [])

        if rest_failed:
            # ❌ REST 실패 → local 유지 (fallback)
            logger.warning(
                f"[ENGINE] REST 실패 → local 지표 유지 (증분만) | "
                f"bar_count={self.bar_count}"
            )
            # 증분 업데이트만
            self.indicators.update_incremental(bar.close, bar.ts)  # ✅ WO-26: 봉 시각 → 마지막 D/C 시각

        elif changed_count > 0:
            # ✅ WO-17 (P) P1 (2026-10-01): 재시드 없이 증분만.
            # 기존 recompute_from_changed_ts 는 바뀐 봉 이후 꼬리(늘 1~3봉)로 시드를 시도해
            # "Not enough data for seed" 로 실패(보존 기간 성공 0 / 실패 8,199)하면서 "완료" 로그만 남겼고,
            # 꼬리가 시드 필요 수 이상이면 SMA 재시드 + 현재 봉 이중 반영이 일어날 수 있었다 → 호출 제거.
            logger.info(
                f"[ENGINE] Reconcile 변경 감지 (지표는 증분만, 재시드 없음) | "
                f"changed={changed_count} | "
                f"range: {min(changed_ts)} ~ {max(changed_ts)}"
            )
            self.indicators.update_incremental(bar.close, bar.ts)  # ✅ WO-26: 봉 시각 → 마지막 D/C 시각

        else:
            # ✅ 변경 없음 → 증분 업데이트만
            logger.debug(f"[ENGINE] 변경 없음 → 증분 업데이트 | bar_count={self.bar_count}")
            self.indicators.update_incremental(bar.close, bar.ts)  # ✅ WO-26: 봉 시각 → 마지막 D/C 시각

        # 3. 전략 평가 및 실행 (스레드 락으로 원자적 보장)
        # ✅ Issue #10: audit 로깅과 execution 사이 position 상태 변경 방지
        with self._execution_lock:
            # ✅ 포지션 상태 동기화 (평가 직전)
            logger.debug(f"[ENGINE] 평가 시작 전 포지션 상태 동기화 | bar={self.bar_count}")
            self.position.sync_from_wallet()
            has_position_before_eval = self.position.has_position

            # ✅ [Phase 3-F] Invariant 스냅샷 기록 (매 봉 관찰 계층)
            # 매매 흐름 절대 방해 X (실패 시 무해). system_health 페이지 조회용.
            self._record_invariant_snapshot(context="pre_eval_confirmed")

            is_buy_eval = not self.position.has_position
            ind_snapshot = self.indicators.get_snapshot(is_buy_eval=is_buy_eval)

            # ✅ WO-6 (2026-08-25): 봉당 매매 판단 1회 강제 (매매 판단 직전 검사).
            # - 실시간(backfill_mode=False)이 이미 판단한 봉의 재진입은 스킵.
            # - BACKFILL 재평가(backfill_mode=True)는 검사에서 제외 (audit UPDATE 목적).
            # - 지표 갱신·재평가 기록(WO-1 별도 컬럼)은 위에서 이미 완료됨.
            if (not backfill_mode) and (bar.ts in self._evaluated_bar_ts):
                logger.info(
                    f"[ENGINE] 봉당 매매 판단 1회 규칙 적용 (실시간 재진입 스킵) | ts={bar.ts} "
                    f"(지표 갱신은 이미 완료. VERIFY 후속 부분 재계산 등)"
                )
                return

            action = self.strategy.on_bar(bar, ind_snapshot, self.position, self.bar_count)

            # 로그 출력
            self._log_bar_evaluation(bar, ind_snapshot, action)

            # 이벤트 큐
            if self.q is not None:
                self._send_log_event(bar, ind_snapshot)

            # ✅ 포지션 상태 재확인 (audit 로깅 직전)
            logger.debug(f"[ENGINE] Audit 로깅 전 포지션 상태 재확인 | bar={self.bar_count}")
            self.position.sync_from_wallet()
            has_position_before_audit = self.position.has_position

            if has_position_before_eval != has_position_before_audit:
                logger.error(
                    f"🚨 [ENGINE] 포지션 상태 불일치 감지 (평가~Audit) | "
                    f"before_eval={has_position_before_eval} → before_audit={has_position_before_audit} | "
                    f"bar={self.bar_count}"
                )

            # 감사 로그 (BACKFILL 재평가 경로면 checks.via_backfill=True로 기록)
            self._record_audit_log(bar, ind_snapshot, action, is_backfill=backfill_mode)

            # ✅ WO-2 (2026-09-02): 매수 지연 재판정 훅.
            # 이전 봉에서 등록된 매수 대기 항목이 있으면, 이 봉이 새 확정 정보를
            # 제공하는 시점에 유효성 확인을 수행한다. 이 훅은 판단이 아니므로
            # _register_evaluated_bar 를 호출하지 않고 봉당 감사 판단 1회 원칙을
            # 유지한다. 재판정은 backfill_mode 와 무관하게 실행 (감사 기록도 UPDATE).
            self._resolve_pending_buy(bar)

            # 4. 주문 실행
            # ✅ Backfill 모드일 때는 감사 로그만 기록하고 실제 주문은 건너뜀
            backfill_mode = diff_summary.get("backfill_mode", False)
            if not backfill_mode:
                # ✅ 포지션 상태 최종 확인 (execution 직전)
                logger.debug(f"[ENGINE] Execution 전 포지션 상태 최종 확인 | bar={self.bar_count}")
                self.position.sync_from_wallet()
                has_position_before_exec = self.position.has_position

                if has_position_before_audit != has_position_before_exec:
                    logger.error(
                        f"🚨 [ENGINE] 포지션 상태 불일치 감지 (Audit~Exec) | "
                        f"before_audit={has_position_before_audit} → before_exec={has_position_before_exec} | "
                        f"bar={self.bar_count}"
                    )

                self.execute(action, bar, ind_snapshot)
            else:
                logger.debug(f"[BACKFILL] 실제 주문 건너뜀 (감사 로그만 기록) | ts={bar.ts}")

            # ✅ 디버그: 최종 포지션 상태 로깅
            logger.debug(
                f"[ENGINE] 평가/실행 완료 | bar={self.bar_count} | "
                f"final_has_position={self.position.has_position} | "
                f"action={action.value if action else 'NONE'}"
            )

            # ✅ WO-6 (2026-08-25): 실시간 평가만 이력에 등록.
            # BACKFILL 은 등록하지 않음 (순서 꼬여도 실시간 평가가 차단되지 않도록).
            if not backfill_mode:
                self._register_evaluated_bar(bar.ts)
                # ✅ WO-6 감사 누락 수정 (2026-08-30): last_bar_ts 는 판단·감사·주문
                # 실행이 모두 완료된 후에만 갱신한다. 이전에는 라인 595(버퍼 추가 직후)
                # 와 live_loop.py:1265(엔진 반환 뒤) 두 곳에서 갱신되어, 케이스 B 안정화
                # 확정 봉이 두 번 진입할 때 두 번째 진입에서 is_new_bar=False 로 조기
                # 반환되고 audit 저장이 스킵되는 결함이 있었다.
                self.last_bar_ts = bar.ts

    # ✅ WO-6 (2026-08-25): 봉당 매매 판단 1회 이력 관리 헬퍼
    _EVAL_HISTORY_MAX = 1000  # 최근 1000봉 (분봉 기준 약 16시간 분량)

    def _register_evaluated_bar(self, ts) -> None:
        """실시간 평가가 매매 판단을 실행한 봉의 ts 를 이력에 등록.

        OrderedDict 로 등록 순서를 유지하고, 상한 초과 시 오래된 항목부터 제거.
        """
        self._evaluated_bar_ts[ts] = None
        while len(self._evaluated_bar_ts) > self._EVAL_HISTORY_MAX:
            self._evaluated_bar_ts.popitem(last=False)

    # ============================================================
    # 2차 T5: PULLBACK 전용 경로 (strategy_type == "PULLBACK" 일 때만 부른다)
    # ============================================================
    def _on_new_bar_confirmed_pullback(self, bar: Bar, full_series, diff_summary: Dict):
        """
        PULLBACK 확정 봉 처리. EMA·MACD 의 on_new_bar_confirmed 본문을 타지 않는다.
        - 지표·링은 strategy.on_bar 로만 들어간다(feed_confirmed_bar 를 따로 부르지 않음 — 두 번 넣지 않기).
        - IndicatorState(EMA/MACD) 갱신·WO-2 지연 큐 재판정은 하지 않는다.
        - BACKFILL 은 live_loop 의 pullback_backfill 1회가 맡는다(T3). 여기로 backfill_mode 가 오면 무시.
        - 실시간 호출은 늘 엔진 position 을 넘긴다. position 이 없으면 경고·NOOP(T4 넘김 3).
        """
        if diff_summary.get("backfill_mode", False):
            logger.warning(f"[PULLBACK] backfill_mode 봉은 링 재생이 맡음 → 무시 | ts={bar.ts}")
            return
        if not bar.is_closed:
            logger.error(f"[ENGINE] 미확정 봉 거부 | {bar.ts}")
            return
        if self.position is None:
            logger.warning(f"[PULLBACK] position 없음 → 판정 안 함(NOOP) | ts={bar.ts}")
            return
        logger.info(
            f"[ENGINE-ENTRY] on_new_bar_confirmed(PULLBACK) | bar.ts={bar.ts} | "
            f"last_bar_ts={self.last_bar_ts} | confirmed={getattr(bar, 'is_confirmed', False)}"
        )
        if not self.is_new_bar(bar):
            logger.info(f"[ENGINE-SKIP-DUP] 중복 봉 무시 (is_new_bar False) | bar.ts={bar.ts}")
            return

        with self._execution_lock:
            self._reconcile_position_with_wallet()
            self._pullback_wallet_check(bar)  # ✅ 2차 T6: 지갑 ↔ 분할 상태 대조(체결 대기·desync·지갑 0)

        self.buffer.append(bar)
        self.bar_count += 1

        with self._execution_lock:
            self.position.sync_from_wallet()
            self._record_invariant_snapshot(context="pre_eval_confirmed")
            if bar.ts in self._evaluated_bar_ts:
                logger.info(f"[ENGINE] 봉당 매매 판단 1회 규칙 적용 (PULLBACK) | ts={bar.ts}")
                return

            # ✅ 2차 T6: 판정 직전 엔진 표식 — 체결 대기(미보유여도 회차 유지)·어긋남(추가 분할매수 멈춤)
            if hasattr(self.strategy, "fill_wait"):
                self.strategy.fill_wait = self._pending_split is not None
                self.strategy.split_desync = bool(self._pullback_desync)
            action = self.strategy.on_bar(bar, {}, self.position, self.bar_count)
            ev = getattr(self.strategy, "last_eval", {}) or {}
            logger.info(
                f"📊 Bar#{self.bar_count} | ts={bar.ts} | close={bar.close:.2f} | PULLBACK "
                f"maTrend={ev.get('maTrend')} ma200={ev.get('ma200')} maPullback={ev.get('maPullback')} "
                f"armed={ev.get('armed')} 회차={ev.get('entry_count')} | action={action.value} | "
                f"pos={self.position.has_position} | failed={ev.get('failed_keys')}"
            )
            if self.q is not None:
                self.q.put((bar.ts, "LOG",
                            f"{bar.ts} | price={bar.close:.2f} | PULLBACK golden={ev.get('golden')} "
                            f"active={ev.get('active')} armed={ev.get('armed')} | bar={self.bar_count}"))

            if getattr(self.pullback_indicators, "state_polluted", False):
                self._pullback_notify_polluted()

            self.position.sync_from_wallet()
            self._record_pullback_audit(bar, action)

            self._pullback_buy_placed = False
            self._pullback_pending_set = False
            self.position.sync_from_wallet()
            ind = self._pullback_ind_dict()
            _raised = True
            try:
                self.execute(action, bar, ind)
                _raised = False
            finally:
                if action == Action.BUY and not self._pullback_buy_placed:
                    # 건너뜀·일시정지·주문 진행 중·오염·주문 실패·예외 — 주문이 나가지 않았으면 회차를 되돌린다(F12)
                    if _raised and self._pullback_pending_set:
                        self.position.set_pending(False)
                        logger.error(f"[PULLBACK] 매수 실행 중 예외 — 주문 없음으로 보고 pending 해제 | ts={bar.ts}")
                    if hasattr(self.strategy, "rollback_last_buy") and self.strategy.rollback_last_buy():
                        logger.info(f"[PULLBACK-SKIP] 주문 없음 → 회차 되돌림·armed 해제 | ts={bar.ts}")
                self._pullback_pending_set = False

            self._register_evaluated_bar(bar.ts)
            self.last_bar_ts = bar.ts
            self._pullback_persist()  # ✅ 2차 T6: 봉 판정 끝 — 분할 상태 1행 저장(한 문장 UPSERT)

    # ============================================================
    # 2차 T6: 분할 상태 저장·복원·체결 반영·지갑 대조 (PULLBACK 만 부른다)
    # ============================================================
    def _pullback_mode(self) -> str:
        return "TEST" if getattr(self.trader, "test_mode", True) else "LIVE"

    def _pullback_state_dict(self) -> Dict[str, Any]:
        st = self.strategy
        ex = st.export_split_state() if hasattr(st, "export_split_state") else {}
        qty = float(self._pb_qty or 0.0)
        cost = float(self._pb_cost or 0.0)
        return {
            "ticker": self.ticker,
            "interval": f"minute{int(getattr(st, 'interval_min', 1) or 1)}",
            "entry_count": ex.get("entry_count", 0), "pullback_count": ex.get("pullback_count", 0),
            "first_entry_ts": ex.get("first_entry_ts"), "first_entry_reason": ex.get("first_entry_reason"),
            "armed": ex.get("armed"), "prev_golden": ex.get("prev_golden"),
            "trade_origin": ex.get("trade_origin"), "pending_fill": ex.get("pending_fill"),
            "fill_n": ex.get("fill_n", 0), "inv_sum": ex.get("inv_sum", 0.0),
            "sizing_base_krw": self._pullback_sizing_base,
            "realized_pnl_krw": self._pullback_realized_pnl,
            "qty": qty, "cost_krw": cost, "avg_price": (cost / qty) if qty > 0 else None,
            "desync": self._pullback_desync,
            "buy_fail_bar_ts": self._pullback_buy_fail_ts,
            "params_sha256": self._pullback_params_sha,
            "last_bar_ts": ex.get("last_ts"),
        }

    def _pullback_persist(self) -> bool:
        """분할 상태를 pullback_state 에 1행 저장. 실패는 매매를 멈추지 않는다 — CRITICAL 로그 + (DB 가 있으면) 알림 1회.
        수정 1회차: 복원에서 읽기 오류·other_market 이면 이 엔진 수명 동안 저장을 막는다(저장 행 보존)."""
        if getattr(self, "_pullback_persist_blocked", False):
            return False
        try:
            from services import pullback_state as pbs
            ok = pbs.save(self.user_id, self._pullback_mode(), self._pullback_state_dict())
        except Exception as e:
            logger.error(f"[PULLBACK-STATE] 저장 예외 | {type(e).__name__}: {e}")
            ok = False
        if not ok and not self._pullback_state_err_notified:
            self._pullback_state_err_notified = True
            logger.critical(f"🚨 [PULLBACK-STATE] 분할 상태 저장 실패 — 재시작하면 회차를 잃을 수 있음 | "
                            f"user={self.user_id} ticker={self.ticker} (이 엔진 수명에서 1회만 남김)")
            try:
                from services import db as _db
                import os as _os
                if _os.path.exists(_db.get_db_path(self.user_id)):
                    from services.notifier import send as _notify, LEVEL_CRITICAL
                    _notify(
                        LEVEL_CRITICAL,
                        f"🚨 새 전략 기록 저장 실패 — {self.ticker}",
                        ("새 전략의 회차·평단 기록을 남기지 못했습니다.\n"
                         "매매는 계속하지만 재시작하면 분할 회차를 잃을 수 있습니다. 운영자가 확인합니다.\n"
                         f"{NO_ACTION_TEXT}"),
                        dedupe_key=f"pullback_state_save:{self.user_id}:{self.ticker}",
                        dedupe_ttl=3600,
                    )
            except Exception:
                pass
        return ok

    _PERSIST_BLOCK_HEAD = {
        "read_error": "저장된 새 전략 기록(회차·평단)을 읽지 못했습니다.",
        "other_market": "저장된 새 전략 기록이 지금 종목·봉 단위와 다릅니다.",
        "restore_exception": "재시작 때 새 전략 기록을 되살리다 오류가 났습니다.",
    }

    def _pullback_block_persist(self, why: str, kind: Optional[str] = None, *, notify: bool = True) -> None:
        """수정 1회차: 저장 행을 덮어쓰지 않도록 이 엔진 수명 동안 저장·청산 초기화를 막는다. CRITICAL 로그 1줄.
        2차 T8 (T6 LIVE 거부 해제 전 조건 8): 막음을 시작할 때 텔레그램 CRITICAL 1회(원인 원문은 로그에만).
        notify=False: 호출부가 저장 멈춤 사실을 자기 알림 본문에 함께 적는다(복원 예외 — live_loop)."""
        if getattr(self, "_pullback_persist_blocked", False):
            return
        self._pullback_persist_blocked = True
        logger.critical(f"🚨 [PULLBACK-STATE] 저장 막음 — {why} | 저장 행은 그대로 둠(재시작·T12 정리 전까지) "
                        f"| user={self.user_id} ticker={self.ticker} mode={self._pullback_mode()}")
        if kind is None:
            kind = "restore_exception" if why == "restore_exception" else "read_error"
        if not notify:
            return
        try:
            from services.notifier import send as _notify, LEVEL_CRITICAL
            _notify(
                LEVEL_CRITICAL,
                f"🚨 새 전략 기록 저장 멈춤 — {self.ticker}",
                (f"{self._PERSIST_BLOCK_HEAD.get(kind, self._PERSIST_BLOCK_HEAD['read_error'])}\n"
                 "기존 기록을 지키려고 이번 실행 동안 기록 저장을 멈췄습니다. 매매는 계속합니다.\n"
                 "재시작하면 이번 실행의 회차·실현 손익이 이어지지 않을 수 있습니다. 운영자가 확인합니다.\n"
                 f"{NO_ACTION_TEXT}"),
                dedupe_key=f"pullback_persist_block:{self.user_id}:{self.ticker}",
                dedupe_ttl=3600,
            )
        except Exception:
            pass

    def _pullback_set_pb_from_position(self) -> None:
        p = self.position
        self._pb_qty = float(p.qty or 0.0) if p.has_position else 0.0
        self._pb_cost = self._pb_qty * float(p.avg_price or 0.0)

    def _pullback_record_sync(self, *, wallet: float, state_qty: float, cls: str, note: str) -> None:
        """[PULLBACK-SYNC] WARNING + 감사 1행(audit_trades type='PULLBACK_SYNC' — 손익 집계(type='SELL')·봇 BUY 판정(type='BUY') 밖)."""
        logger.warning(f"⚠️ [PULLBACK-SYNC] wallet={wallet:.8f} state={state_qty:.8f} class={cls} | {note}")
        try:
            import json as _json
            from services.db import insert_trade_audit
            insert_trade_audit(
                user_id=self.user_id, ticker=self.ticker, interval_sec=self.interval_sec, bar=self.bar_count,
                kind="PULLBACK_SYNC", reason=cls, price=None, macd=None, signal=None,
                entry_price=self.position.avg_price, entry_bar=self.position.entry_bar, bars_held=None,
                tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None, qty=float(wallet), note=note,
                meta=_json.dumps({"wallet_qty": wallet, "state_qty": state_qty, "class": cls,
                                  "strategy_type": "PULLBACK"}, ensure_ascii=False),
                strategy_type="PULLBACK",  # ✅ 2차 T7: 거래 행 전략 칸
            )
        except Exception as e:
            logger.error(f"[PULLBACK-SYNC] 감사 기록 실패: {e}")
        # 2차 T8 (T6 넘김): 동기화 알림 — 어긋남이 시작될 때 1회(호출부가 바뀔 때만 부른다) + 같은 사유 1시간 dedupe
        try:
            from services.notifier import send as _notify, LEVEL_WARNING
            head = {
                "wallet_more": "업비트 지갑의 보유 수량이 새 전략 기록보다 많습니다(앱에서 직접 산 주문 등).",
                "wallet_less": "업비트 지갑의 보유 수량이 새 전략 기록보다 적습니다(앱에서 직접 판 주문 등).",
                "restart_mismatch": "재시작 때 업비트 지갑의 보유 수량이 새 전략 기록과 달랐습니다.",
            }.get(cls, "업비트 지갑의 보유 수량이 새 전략 기록과 다릅니다.")
            _notify(
                LEVEL_WARNING,
                f"⚠️ 새 전략 보유 수량 맞춤 — {self.ticker}",
                (f"{head}\n지갑 수량 {float(wallet):,.8g}개 기준으로 맞추고 추가 분할 매수를 멈췄습니다.\n"
                 f"익절·손절·데드크로스 매도는 계속합니다.\n{NO_ACTION_TEXT}"),
                dedupe_key=f"pullback_sync:{self.user_id}:{self.ticker}:{cls}",
                dedupe_ttl=3600,
            )
        except Exception:
            pass

    def _pullback_on_exit(self, realized_pnl: float, *, reason: str) -> None:
        """청산(봇 매도 체결·지갑 0) 뒤: 실현 손익 누적, 분할 수량·원가·어긋남·배분 기준 초기화(pullback spec 3절 5).
        쿨다운은 여기서 풀지 않는다(봇 매도만 — _execute_sell)."""
        self._pullback_realized_pnl = float(self._pullback_realized_pnl or 0.0) + float(realized_pnl or 0.0)
        try:
            from services import pullback_state as pbs
            if not getattr(self, "_pullback_persist_blocked", False):  # 수정 1회차: 저장 막음이면 행 보존
                pbs.reset_after_exit(self.user_id, self._pullback_mode(), float(realized_pnl or 0.0))
        except Exception as e:
            logger.error(f"[PULLBACK-STATE] 청산 초기화 실패: {e}")
        logger.info(f"[PULLBACK-STATE] 청산 → 분할 상태 초기화 | reason={reason} realized={realized_pnl:,.2f} "
                    f"누적={self._pullback_realized_pnl:,.2f}")
        self._pb_qty = 0.0
        self._pb_cost = 0.0
        self._pullback_desync = False
        self._pullback_sizing_base = None
        self._pending_split = None

    def _pullback_wallet_check(self, bar: Bar) -> None:
        """
        봉마다(판정 전) 지갑 수량과 분할 상태 수량(_pb_qty) 대조.
          - 체결 대기(_pending_split) 중에는 desync 판정 안 함. PULLBACK_FILL_WAIT_BARS 봉을 넘으면
            WARNING [PULLBACK-SYNC] fill pending 후 지갑 기준(수량·LIVE 평단)으로 맞춘다.
          - 지갑 0 + 분할 보유 → 청산(앱 매도 등) — 분할 상태 초기화(손익 0: 앱 주문 손익은 넣지 않음, spec 3절).
          - 차이 > 0.1% → 지갑 우선, desync=1(바뀔 때 WARNING + 감사 1행). 추가 분할매수 멈춤, 매도는 계속(D11 b).
        """
        try:
            wallet = float(self.trader._coin_balance(self.ticker) or 0.0)
        except Exception as e:
            logger.warning(f"[PULLBACK-SYNC] 지갑 조회 실패 → 대조 건너뜀: {e}")
            return
        sp = self._pending_split
        if sp is not None:
            waited = (self.bar_count + 1) - int(sp.get("bar", self.bar_count))
            if waited <= PULLBACK_FILL_WAIT_BARS:
                return
            logger.warning(
                f"⚠️ [PULLBACK-SYNC] fill pending {waited}봉 > {PULLBACK_FILL_WAIT_BARS} | uuid={sp.get('uuid')} "
                f"{sp.get('round')}회차 → 지갑 기준으로 맞춤 | wallet={wallet:.8f} state={self._pb_qty:.8f}"
            )
            self._pending_split = None
            self.position.set_pending(False)
            if wallet >= 1e-6:
                avg = self._fetch_upbit_avg_buy_price() or self.position.avg_price
                if self.position.has_position:
                    self.position.qty = wallet
                    if avg:
                        self.position.avg_price = float(avg)
                self._pb_qty = wallet
                if avg:
                    self._pb_cost = wallet * float(avg)
            return
        if wallet < 1e-6:
            if self._pb_qty > 0 or self._pullback_desync:
                logger.warning(f"[PULLBACK-SYNC] wallet=0 state={self._pb_qty:.8f} class=wallet_zero "
                               f"→ 청산으로 보고 분할 상태 초기화(앱 매도 등)")
                self._pullback_on_exit(0.0, reason="wallet_zero")
            return
        if self._pb_qty <= 0:
            return  # 이 전략이 연 거래가 아님(앱 매수) — 전략 ⑥ POS_DESYNC 가 매수를 막는다
        diff = wallet - self._pb_qty
        if abs(diff) <= max(1e-8, self._pb_qty * PULLBACK_SYNC_TOL):
            return
        cls = "wallet_more" if diff > 0 else "wallet_less"
        if not self._pullback_desync:
            self._pullback_desync = True
            self._pullback_record_sync(
                wallet=wallet, state_qty=self._pb_qty, cls=cls,
                note=("새 전략 보유 수량이 지갑과 다름(앱 매수·매도 등) — 지갑 수량 기준으로 맞추고 "
                      "추가 분할매수를 멈춤(익절·손절·데드크로스 매도는 계속)"),
            )
        avg = self._fetch_upbit_avg_buy_price()  # LIVE 만 값 — TEST 는 지금 평단 유지
        if avg:
            self.position.avg_price = float(avg)
        if self.position.has_position:
            self.position.qty = wallet
        self._pb_qty = wallet
        self._pb_cost = wallet * float(self.position.avg_price or 0.0)

    def _pullback_apply_fill(self, *, uuid: str, executed_price: float, executed_qty: float,
                             executed_ts, state: str) -> None:
        """LIVE 분할 주문 체결(F2) — 체결 실수량·평단으로 분할 반영. 호출부가 _execution_lock 을 쥔다."""
        sp = self._pending_split
        if sp is None or sp.get("uuid") != uuid:
            logger.info(f"[PULLBACK-FILL] 체결 대기 없음(이미 반영·청산·시간 초과) → 무시 | uuid={uuid}")
            return
        try:
            if not (float(executed_qty) > 0 and float(executed_price) > 0):
                raise ValueError(f"체결 수량·가격 없음 qty={executed_qty} price={executed_price}")
            self.position.apply_split_entry(
                float(executed_qty), float(executed_price), executed_ts, source="pullback_split_fill",
                base_qty=sp.get("base_qty", 0.0), base_cost=sp.get("base_cost", 0.0),
                entry_bar=sp.get("bar", self.bar_count),
            )
        except Exception as e:
            logger.error(f"[PULLBACK-FILL] 분할 반영 실패 uuid={uuid}: {e}", exc_info=True)
            return
        self._pending_split = None
        self.position.set_pending(False)
        self._pullback_set_pb_from_position()
        logger.info(
            f"✅ [SPLIT-FILL] applied | {sp.get('round')}회차 체결 반영 | state={state} uuid={uuid} "
            f"체결 qty={float(executed_qty):.8f} price={float(executed_price):.4f} → "
            f"보유 qty={self._pb_qty:.8f} 평단={self.position.avg_price:.4f}"
        )
        self._pullback_persist()
        self._pullback_notify_buy(int(sp.get("round") or 1), sp.get("reason"), self.position.avg_price,
                                  sp.get("per_buy"), str(uuid))

    def pullback_restore_on_boot(self, series=None, validator=None) -> Dict[str, Any]:
        """
        재시작·기동 재개(WO-12) 복원 — 워밍업 시드(지표·링·가상 판정 상태) 뒤 1회.
          1. pullback_state 행(같은 모드)을 읽는다. 없으면 워밍업 결과 그대로(미보유면 가상 회차는 첫 봉 ① 정리, spec 4.3).
          2. 종목·봉 단위가 다르면 쓰지 않는다(전환은 T12).
          3. 쿨다운(실패 봉 시각)·실현 손익 합은 거래와 무관하게 되살린다.
          4. 열린 거래인데 지갑 0 → 분할 상태 초기화(앱 매도 등).
          5. 지갑 ≈ 저장 수량이면 포지션을 저장 평단으로 맞춘다(LIVE 부팅 seed 의 마지막 BUY 평단 대신 분할 평단).
             다르면 지갑 우선 + desync=1.
          6. 판정 상태: 저장 봉(last_bar_ts)이 워밍업 링 안이면 그 봉 상태로 되살려 DB 값을 넣고 뒤 봉을 주문 없이 재생,
             재생 뒤 거래 칸(SPLIT_TRADE_KEYS)은 DB 값 유지(보유 중 BACKFILL 규칙). 링 밖·재생 없음이면 DB 값을 바로 넣는다.
        """
        res: Dict[str, Any] = {"loaded": False, "restored": False, "replayed": 0, "reason": ""}
        from services import pullback_state as pbs
        from core import strategy_pullback as _sp
        mode = self._pullback_mode()
        try:
            row = pbs.load(self.user_id, mode)
        except pbs.PullbackStateReadError as e:
            # 수정 1회차: 읽기 오류를 「행 없음」으로 보면 첫 봉 저장이 기존 행을 덮어쓴다 → 저장 막음
            res["reason"] = "read_error"
            self._pullback_block_persist(f"복원 읽기 오류({e})", kind="read_error")
            self.pullback_restore_result = res
            return res
        if row is None:
            res["reason"] = "no_state"
            logger.info(f"[PULLBACK-RESTORE] 저장된 분할 상태 없음 | mode={mode}")
            self.pullback_restore_result = res
            return res
        res["loaded"] = True
        st = self.strategy
        interval = f"minute{int(getattr(st, 'interval_min', 1) or 1)}"
        if row.get("ticker") != self.ticker or row.get("interval") != interval:
            res["reason"] = "other_market"
            logger.warning(f"[PULLBACK-RESTORE] 저장 종목·봉 단위가 다름 → 쓰지 않음 | saved={row.get('ticker')}/"
                           f"{row.get('interval')} now={self.ticker}/{interval}")
            # 수정 1회차: 다른 종목·봉 단위의 행을 이 엔진이 덮어쓰지 않게 저장 막음(정리는 T12)
            self._pullback_block_persist(f"저장 행 종목·봉 단위 다름({row.get('ticker')}/{row.get('interval')})",
                                         kind="other_market")
            self.pullback_restore_result = res
            return res
        if row.get("params_sha256") and self._pullback_params_sha and row["params_sha256"] != self._pullback_params_sha:
            logger.warning("[PULLBACK-RESTORE] 적용본이 저장 때와 다름 — 진행 중 거래의 회차·평단은 그대로 이어 감")

        self._pullback_realized_pnl = float(row.get("realized_pnl_krw") or 0.0)
        fail_ts = _sp._to_ts(row.get("buy_fail_bar_ts")) if row.get("buy_fail_bar_ts") else None
        if fail_ts is not None and self.last_bar_ts is not None:
            elapsed = int(round((_sp._to_ts(self.last_bar_ts) - fail_ts).total_seconds() / max(1, int(self.interval_sec))))
            if 0 <= elapsed < PULLBACK_BUY_FAIL_COOLDOWN_BARS:
                self._pullback_buy_fail_bar = self.bar_count - elapsed
                self._pullback_buy_fail_ts = fail_ts
                logger.warning(f"[PULLBACK-RESTORE] 매수 쉼(쿨다운) 이어 감 | 실패 봉={fail_ts} 지난 봉={elapsed}")

        open_trade = int(row.get("entry_count") or 0) > 0 or float(row.get("qty") or 0.0) > 0
        if not open_trade:
            res["reason"] = "flat"
            self.pullback_restore_result = res
            return res
        try:
            wallet = float(self.trader._coin_balance(self.ticker) or 0.0)
        except Exception as e:
            logger.error(f"[PULLBACK-RESTORE] 지갑 조회 실패 → 복원 안 함(매수는 POS_DESYNC 로 막힘): {e}")
            res["reason"] = "wallet_unknown"
            self.pullback_restore_result = res
            return res
        if wallet < 1e-6:
            logger.warning(f"[PULLBACK-RESTORE] 저장 회차 {row.get('entry_count')} 인데 지갑 0 → 분할 상태 초기화"
                           f"(꺼져 있는 동안 앱 매도 등)")
            pbs.reset_after_exit(self.user_id, mode, 0.0)
            res["reason"] = "wallet_zero"
            self.pullback_restore_result = res
            return res

        db_qty = float(row.get("qty") or 0.0)
        db_avg = float(row["avg_price"]) if row.get("avg_price") else None
        first_ts = _sp._to_ts(row.get("first_entry_ts")) if row.get("first_entry_ts") else None
        match = db_qty > 0 and abs(wallet - db_qty) <= max(1e-8, db_qty * PULLBACK_SYNC_TOL)
        avg = db_avg if (match and db_avg) else (self._fetch_upbit_avg_buy_price() or db_avg or self.position.avg_price)
        if avg:
            if self.position.has_position:
                self.position.qty = wallet
                self.position.avg_price = float(avg)
            else:
                from datetime import datetime as _dt
                self.position.apply_entry(qty=wallet, avg_price=float(avg), entry_bar=self.bar_count,
                                          entry_ts=first_ts if first_ts is not None else _dt.now(ZoneInfo("Asia/Seoul")),
                                          source="pullback_state")
        self._pb_qty = wallet
        self._pb_cost = wallet * float(avg or 0.0)
        self._pullback_sizing_base = float(row["sizing_base_krw"]) if row.get("sizing_base_krw") else None
        self._pullback_desync = bool(row.get("desync"))
        if not match:
            if not self._pullback_desync:
                self._pullback_record_sync(wallet=wallet, state_qty=db_qty, cls="restart_mismatch",
                                           note="재시작 — 지갑 수량이 저장된 분할 상태와 다름: 지갑 기준, 추가 분할매수 멈춤")
            self._pullback_desync = True

        saved = {
            "entry_count": int(row.get("entry_count") or 0), "pullback_count": int(row.get("pullback_count") or 0),
            "first_entry_ts": first_ts, "first_entry_reason": row.get("first_entry_reason"),
            "armed": bool(row.get("armed")), "trade_origin": row.get("trade_origin") or "live",
            "pending_fill": False, "fill_n": int(row.get("fill_n") or 0), "inv_sum": float(row.get("inv_sum") or 0.0),
        }
        if row.get("prev_golden") is not None:
            saved["prev_golden"] = bool(row["prev_golden"])
        last_saved = _sp._to_ts(row.get("last_bar_ts")) if row.get("last_bar_ts") else None
        ring, ind = self.pullback_ring, self.pullback_indicators
        st_last = getattr(st, "last_ts", None)
        replay_rows = None
        snap = None
        if (series is not None and ring is not None and ind is not None and last_saved is not None
                and st_last is not None and last_saved < st_last):
            replay_rows = series[(series.index > last_saved) & (series.index <= st_last)]
            if len(replay_rows):
                try:
                    snap = ring.snapshot_before(replay_rows.index[0])
                except Exception:
                    snap = None
                if snap is not None and snap.bar_ts != last_saved:
                    snap = None  # 저장 봉 자체의 기록이 없으면(검증 실패 봉 등) 재생하지 않고 바로 넣는다
        if snap is not None:
            try:
                ring.restore(snap, ind, st)
                st.restore_split_state({**st.export_split_state(), **saved})
                ring.amend_last_split(snap.bar_ts, st)
                n = 0
                for ts, r in _sp.iter_valid_rows(replay_rows, validator, tag="[PULLBACK-RESTORE]"):
                    _sp.feed_confirmed_bar(self, _sp.bar_from_row(ts, r, source="REST_WARMUP"))
                    n += 1
                res["replayed"] = n
            except Exception as e:
                logger.error(f"[PULLBACK-RESTORE] 재생 실패 → 지표 오염 표식, DB 회차는 넣음 | {e}", exc_info=True)
                ind.state_polluted = True
        cur = st.export_split_state()
        if snap is None:
            cur.update(saved)  # 재생 없음: 판정 상태(armed·prev_golden 포함) = DB 값
        else:
            cur.update({k: saved[k] for k in _sp.SPLIT_TRADE_KEYS})  # 재생 뒤: 거래 칸만 DB 값(armed 는 재생 결과)
        st.restore_split_state(cur)
        if ring is not None and getattr(st, "last_ts", None) is not None:
            ring.amend_last_split(st.last_ts, st)
        res["restored"] = True
        res["reason"] = "restored"
        logger.info(
            f"✅ [PULLBACK-RESTORE] 분할 상태 복원 | 회차={st.entry_count} 눌림목={st.pullback_count} armed={st.armed} "
            f"첫 체결={st.first_entry_ts} 배분 기준={self._pullback_sizing_base} 보유={wallet:.8f} 평단={avg} "
            f"desync={self._pullback_desync} 재생={res['replayed']}봉"
        )
        self.pullback_restore_result = res
        self._pullback_persist()
        return res

    def _pullback_ind_dict(self) -> Dict[str, Any]:
        """감사·이벤트용 지표 dict (EMA 칸은 비움)."""
        ev = getattr(self.strategy, "last_eval", {}) or {}
        d = {k: ev.get(k) for k in ("maTrend", "ma200", "maPullback", "slope200", "slope200_lb")}
        d.update({"macd": None, "signal": None, "ema_fast": None, "ema_slow": None})
        return d

    def _record_pullback_audit(self, bar: Bar, action: Action) -> None:
        """
        PULLBACK 봉 판정 감사 (2차 T8 칸 모양 — 스키마 변경 없음, X10).
          - 미보유: audit_buy_eval 1행(checks = 전략 audit_view, failed_keys = 매수 대기 사유).
          - 보유: audit_sell_eval 1행(tp/sl = 평단 × (1 ± %), trigger_key ∈ Take Profit|Stop Loss|Dead Cross).
            보유 중 분할 매수 신호 봉은 audit_buy_eval(have_position=1)도 1행.
          - macd/signal 칸은 비운다(EMA·MACD 칸 — 새 전략 지표는 checks 에).
        """
        try:
            from services.terminology import pullback_eval_text
            st = self.strategy
            if hasattr(st, "audit_view"):
                failed, checks = st.audit_view()
            else:
                ev = dict(getattr(st, "last_eval", {}) or {})
                failed, checks = list(ev.get("failed_keys") or []), {**ev, "strategy": "PULLBACK"}
            checks.update({"price": float(bar.close), "via_backfill": False,
                           "via_tentative": not bool(getattr(bar, "is_confirmed", True))})
            bar_time = bar.ts.astimezone(ZoneInfo("Asia/Seoul")).isoformat()
            notes = f"새 전략 · {pullback_eval_text(failed, checks)}"
            holding = bool(self.position.has_position)
            if not holding or action == Action.BUY:
                insert_buy_eval(
                    user_id=self.user_id, ticker=self.ticker, interval_sec=self.interval_sec,
                    bar=self.bar_count, price=float(bar.close), macd=None, signal=None,
                    have_position=holding, overall_ok=(action == Action.BUY), failed_keys=failed,
                    checks=checks, notes=notes, bar_time=bar_time,
                )
            if holding:
                _sell = action in (Action.SELL, Action.CLOSE)
                insert_sell_eval(
                    user_id=self.user_id, ticker=self.ticker, interval_sec=self.interval_sec,
                    bar=self.bar_count, price=float(bar.close), macd=None, signal=None,
                    tp_price=checks.get("tp_price") or 0, sl_price=checks.get("sl_price") or 0,
                    highest=None, ts_pct=None, ts_armed=False,
                    bars_held=self.position.get_bars_held(self.bar_count),
                    checks=checks, triggered=_sell,
                    trigger_key=(PULLBACK_SELL_TRIGGER_KEY.get(checks.get("sell_reason")) if _sell else None),
                    notes=notes, bar_time=bar_time,
                )
        except Exception as e:
            logger.warning(f"[PULLBACK-AUDIT] 판정 감사 기록 실패(무해): {e}")

    def _pullback_notify_polluted(self) -> None:
        """T4 넘김 6: 오염 상태 — CRITICAL 1회(엔진 수명 동안) + 재시작 안내. 매도(데드크로스·익절·손절)는 계속."""
        if self._pullback_polluted_notified:
            return
        self._pullback_polluted_notified = True
        logger.error(
            f"🚫 [PULLBACK-POLLUTED] 새 전략 지표 오염 상태 — 신규 매수 중지, 매도는 계속 | "
            f"ticker={self.ticker} | 해제: 재시작(워밍업 재시드)"
        )
        try:
            from services.notifier import send as _notify, LEVEL_CRITICAL
            _notify(
                LEVEL_CRITICAL,
                f"🚨 새 전략 지표 오염 — {self.ticker}",
                (
                    "새 전략 지표 값을 믿을 수 없어 새 매수를 멈췄습니다.\n"
                    "익절·손절·데드크로스 매도는 계속합니다.\n"
                    "운영자가 봇을 재시작하면 풀립니다(재시작 때 지표를 다시 계산합니다).\n"
                    f"{NO_ACTION_TEXT}"
                ),
                dedupe_key=f"pullback_polluted:{self.user_id}:{self.ticker}",
                dedupe_ttl=3600,
            )
        except Exception:
            pass

    def _pullback_read_sizing_base(self) -> Optional[float]:
        """이 거래 배분 기준 = 운용자산 users.virtual_krw (D10). T6 분할 상태 테이블이 생기면 거기서 읽는다.
        복리(전환 뒤 실현 손익 합 더하기)는 T6 의 realized_pnl_krw 로 넣는다 — 지금은 운용자산만."""
        try:
            from services.db import get_initial_krw
            v = get_initial_krw(self.user_id)
            v = float(v) if v is not None else None
            # ✅ 2차 T6: 복리(compounding=true)면 전환 뒤 실현 손익 합을 더한다
            if v is not None and getattr(self.strategy, "cfg", {}).get("compounding"):
                v = v + float(self._pullback_realized_pnl or 0.0)
            return v if v is not None and v > 0 else None
        except Exception as e:
            logger.warning(f"[PULLBACK-SPLIT] 운용자산 조회 실패: {e}")
            return None

    def _pullback_skip(self, bar: Bar, indicators, *, code: str, note: str, ctx: Dict[str, Any]) -> None:
        """분할 매수 건너뜀: 감사 BUY_REJECTED 1행 + 알림(같은 거래·같은 사유 1회). 회차는 늘리지 않는다(호출부가 되돌림)."""
        logger.warning(f"⏭️ [PULLBACK-SKIP] {code} | {note}")
        self._pullback_last_skip_code = code  # 2차 T11: 신버전 강제 매수 결과 사유(_pullback_force_buy)
        self._audit_buy_blocked(bar.ts, indicators, price=bar.close, code=code, note=note, extra=ctx)
        try:
            from services.notifier import send as _notify, LEVEL_WARNING
            _fe = getattr(self.strategy, "first_entry_ts", None)
            trade_key = _fe.isoformat() if hasattr(_fe, "isoformat") else "flat"
            title, body = self._pullback_skip_text(code, ctx)
            # 2차 T8 dedupe(F12): 같은 거래·같은 사유는 1시간에 1회
            _notify(
                LEVEL_WARNING, title, body,
                dedupe_key=f"pullback_skip:{self.user_id}:{trade_key}:{code}",
                dedupe_ttl=3600,
            )
        except Exception:
            pass

    # 2차 T8: 회차 건너뜀 알림 — (제목 끝 원인, 본문). 투자자가 받는다(내부 코드·표 이름 없음).
    from services.terminology import PULLBACK_SKIP_CAUSE as _PULLBACK_SKIP_CAUSE  # 감사 화면과 같은 원인 표

    def _pullback_skip_text(self, code: str, ctx: Dict[str, Any]) -> tuple:
        n = int(ctx.get("split_round") or 1)
        per_buy = ctx.get("per_buy")
        per_txt = f"회당 {int(per_buy):,}원" if per_buy is not None else "회당 매수 금액"
        cause = self._PULLBACK_SKIP_CAUSE.get(code, "주문 전 확인 실패")
        title = f"⚠️ 새 전략 {n}회차 건너뜀 — {cause}"
        head = f"{self.ticker} 새 전략 {n}회차 매수를 건너뛰었습니다."
        if code == "split_krw_short":
            body = (f"{head}\n{per_txt}과 수수료를 낼 원화가 모자랍니다. 금액을 줄여 사지 않습니다.\n"
                    "업비트 앱의 미체결 주문·출금을 확인해 주세요.")
        elif code == "split_below_min":
            body = (f"{head}\n{per_txt}이 업비트 최소 주문금액 5,000원보다 작습니다.\n"
                    f"운영자가 운용 금액과 분할 횟수를 확인합니다. {NO_ACTION_TEXT}")
        elif code == "split_krw_unknown":
            body = (f"{head}\n업비트에서 원화 잔고 조회 실패로 이번 회차는 주문하지 않았습니다.\n"
                    f"다음 신호에서 다시 확인합니다. {NO_ACTION_TEXT}")
        elif code == "split_no_capital":
            body = f"{head}\n운용 금액이 정해지지 않았습니다. 운영자가 확인합니다. {NO_ACTION_TEXT}"
        else:
            body = f"{head}\n봉 마감이 확인되지 않아 다음 마감 봉에서 다시 판단합니다. {NO_ACTION_TEXT}"
        return title, body

    _PULLBACK_REJECT_TEXT = {
        "split_krw_short": ("원화 잔고 부족 — 회당 금액을 줄여 사지 않았습니다.\n"
                            "업비트 앱에서 직접 넣은 외부 미체결 주문이 원화를 묶고 있을 수 있습니다."),
        "split_krw_unknown": "원화 잔고 조회 실패 — 업비트 응답이 없어 주문하지 않았습니다.",
    }

    def _pullback_start_cooldown(self, bar: Bar, indicators, round_n: int, *, code: Optional[str],
                                 err: Optional[str], ctx: Dict[str, Any]) -> None:
        """결정 1028-03(다) 고지: 쿨다운 시작 때 감사 BUY_REJECTED(split_order_cooldown) 1행 + 텔레그램 WARNING 1회.
        dedupe 키 = 거래·실패 봉. 쿨다운이 끝나거나 봇 매도로 풀릴 때는 알림을 보내지 않는다(감사 note 에 끝나는 봉 시각)."""
        n = PULLBACK_BUY_FAIL_COOLDOWN_BARS
        fail_bar = self.bar_count
        iv = int(self.interval_sec or 60)
        from datetime import timedelta
        resume_ts = bar.ts + timedelta(seconds=iv * n)          # 다시 주문하는 봉의 시작 시각
        resume_kst = resume_ts.astimezone(ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M")
        # 2차 T8 (T5 넘김): 주문은 봉 마감 때 나간다 — 고지 시각은 그 봉의 마감 시각
        resume_close_kst = (resume_ts + timedelta(seconds=iv)).astimezone(ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M")
        minutes = iv * n / 60
        minutes_txt = f"{minutes:.0f}" if float(minutes).is_integer() else f"{minutes:.1f}"
        if code:
            reason = self._PULLBACK_REJECT_TEXT.get(code, "주문 전 확인에서 멈춤")
        elif err:
            from services.error_messages import format_error_block, error_code_of
            import re as _re
            _label, _raw = format_error_block(str(err))
            _ecode = error_code_of(str(err))
            if _ecode == "unknown":   # 알려진 표에 없는 코드는 원문 「[code]」 에서 코드만
                _m = _re.search(r"\[([a-z][a-z0-9_]{2,})\]", str(err))
                _ecode = _m.group(1) if _m else "unknown"
            if _label == "알 수 없음":
                _label = "거래소가 주문을 받지 않음"
            reason = f"{_label} (거래소 응답: {_ecode})"   # 원문은 위 WARNING·감사 note 에만
        else:
            reason = "주문 전 확인에서 멈춤"
        note = (f"매수 주문 실패({code or err or 'preorder_reject'}) → 새 매수 {n}봉(약 {minutes_txt}분) 쉼 "
                f"— 실패 봉 #{fail_bar} 포함 #{fail_bar}~#{fail_bar + n - 1}, 끝나는 봉 #{fail_bar + n} "
                f"({resume_kst} KST 시작) {resume_close_kst} KST 마감 때부터 재주문(봇 매도 체결 시 바로 해제) "
                f"— {round_n}회차")
        logger.warning(f"⏸️ [PULLBACK-COOLDOWN] {note}")
        self._audit_buy_blocked(bar.ts, indicators, price=bar.close, code="split_order_cooldown", note=note,
                                extra={**ctx, "cooldown_bars": n, "fail_bar": fail_bar,
                                       "resume_bar": fail_bar + n, "resume_ts": resume_ts.isoformat(),
                                       "fail_code": code, "fail_error": err})
        try:
            from services.notifier import send as _notify, LEVEL_WARNING
            _fe = getattr(self.strategy, "first_entry_ts", None)
            trade_key = _fe.isoformat() if hasattr(_fe, "isoformat") else "flat"
            _notify(
                LEVEL_WARNING,
                f"⏸️ 새 전략 매수 잠시 쉼 — {self.ticker}",
                (f"{round_n}회차 매수 주문이 실패했습니다.\n"
                 f"사유: {reason}\n"
                 f"새 매수를 {n}봉(약 {minutes_txt}분) 쉽니다 — {resume_close_kst} 봉 마감 때부터 다시 주문합니다.\n"
                 f"매도(익절·손절·데드크로스)는 계속합니다.\n"
                 f"할 일: 업비트 앱에서 원화 잔고와 미체결 주문(앱에서 넣은 외부 주문)을 확인해 주세요."),
                dedupe_key=f"pullback_cooldown:{self.user_id}:{self.ticker}:{trade_key}:{bar.ts.isoformat()}",
                dedupe_ttl=3600,
            )
        except Exception:
            pass

    def _pullback_notify_buy(self, round_n: int, reason: Optional[str], avg_price, per_buy: Optional[int],
                             key: str, *, dry_run: bool = False) -> None:
        """2차 T8: 분할 매수 체결 알림(INFO) — 「🟢 새 전략 매수 n회차 · <사유> — <종목> 평단 <x>원」.
        TEST·dry-run 은 주문 직후, LIVE 는 체결 반영(_pullback_apply_fill) 때. dedupe = 주문 uuid."""
        try:
            from services.notifier import send as _notify, LEVEL_INFO
            from services.terminology import PULLBACK_REASON_LABEL
            label = PULLBACK_REASON_LABEL.get(str(reason or "").upper(), PULLBACK_REASON_LABEL["PULLBACK"])
            max_n = int(getattr(self.strategy, "cfg", {}).get("eff_max_splits") or 0)
            per_txt = f"회당 {int(per_buy):,}원, " if per_buy else ""
            what = ("모의 실행(실제 주문 없음)으로 반영됐습니다" if dry_run else "체결됐습니다")
            _notify(
                LEVEL_INFO,
                f"🟢 새 전략 매수 {round_n}회차 · {label} — {self.ticker} 평단 {_fmt_price(avg_price)}원",
                (f"새 전략(눌림목 분할매수) {round_n}회차 매수가 {what}({per_txt}최대 {max_n}회).\n"
                 f"{NO_ACTION_TEXT}"),
                dedupe_key=f"pullback_buy:{self.user_id}:{key}",
                dedupe_ttl=3600,
            )
        except Exception as e:
            logger.warning(f"[PULLBACK-NOTIFY] 매수 알림 실패(무해) | {type(e).__name__}")

    def _pullback_force_buy(self) -> Dict[str, Any]:
        """
        2차 T11 (D6): 신버전 「강제 매수」 — 엔진 스레드(core.engine_control.drain_control_queue)에서만 부른다.
        회당 금액 1회·회차 +1·사유 FORCE. _execution_lock 안에서 _execute_pullback_buy 를 부른다(시장가 엄격 금액 —
        안에서 잠금을 다시 잡지 않음, 체결 콜백 _on_limit_fill 과 분할 상태 갱신이 겹치지 않게).
        주문이 나가지 않으면(건너뜀·실패) 올린 회차를 되돌린다(봉 판정의 F12 와 같음). armed 는 바꾸지 않는다(링 기록도).
        수정 1회차: 먼저 봉 판정과 같은 지갑 대조(지갑 0 → 분할 상태·판정 회차 정리), 판정 체결 대기(pending_fill)면 거부.
        반환: {"status": "done"|"rejected", "code", "detail"}
        """
        with self._execution_lock:
            st = self.strategy
            c = getattr(st, "cfg", {}) or {}
            if self._pending_split is not None:
                return {"status": "rejected", "code": "fill_pending", "detail": {}}
            last = self.buffer.get_last_bar() if self.buffer is not None else None
            if last is None or not float(getattr(last, "close", 0) or 0) > 0:
                return {"status": "rejected", "code": "no_price", "detail": {}}
            px = float(last.close)
            bar = Bar(ts=self.last_bar_ts or last.ts, open=px, high=px, low=px, close=px, volume=0.0,
                      is_closed=True, is_confirmed=True, source="FORCE")
            # 수정 1회차: 봉 판정과 같은 지갑 대조를 먼저 — 강제 매도(엔진 밖 체결) 뒤 다음 봉 전이어도 옛 회차·옛 수량으로
            # 사지 않게. 지갑 0 이면 _pullback_wallet_check 가 분할 상태를 정리하고, 판정 회차는 여기서 0 으로 맞춘다
            # (봉 판정의 「실보유 없음 + 판정 회차」 정리와 같음 — 실시간 거래라 armed 해제).
            self._reconcile_position_with_wallet()
            self._pullback_wallet_check(bar)
            if not self.position.has_position and int(getattr(st, "entry_count", 0) or 0) > 0 \
                    and self._pending_split is None:
                logger.warning(f"[PULLBACK-FORCE] 실보유 없음 + 판정 회차 {st.entry_count} → 회차 0 으로 맞춘 뒤 강제 매수")
                st._reset_trade()
                if st.ring is not None and st.last_ts is not None:
                    st.ring.amend_last_split(st.last_ts, st)
            if getattr(st, "pending_fill", False):
                # 판정 체결 대기(이 봉에 이미 매수 — 다음 봉 판정이 풀어 줌): 겹쳐 사면 회차·체결 반영이 꼬인다
                return {"status": "rejected", "code": "fill_pending", "detail": {}}
            if self._pullback_desync:
                return {"status": "rejected", "code": "desync", "detail": {}}
            max_n = int(c.get("eff_max_splits") or 0)
            if int(getattr(st, "entry_count", 0) or 0) >= max_n:
                return {"status": "rejected", "code": "splits_full", "detail": {"max_splits": max_n}}
            armed = getattr(st, "armed", False)
            st._save_buy_undo(True)
            if int(st.entry_count or 0) == 0:
                st.first_entry_reason = "FORCE"
            st.entry_count = int(st.entry_count or 0) + 1
            st.trade_origin = "live"
            st.pending_fill = True
            st.last_buy_reason = "FORCE"
            round_n = st.entry_count
            self._pullback_buy_placed = False
            self._pullback_pending_set = False
            self._pullback_last_skip_code = None
            _fb = self._pullback_buy_fail_bar
            cooling = _fb is not None and self.bar_count - _fb < PULLBACK_BUY_FAIL_COOLDOWN_BARS
            _raised = True
            try:
                self._execute_pullback_buy(bar, self._pullback_ind_dict())
                _raised = False
            finally:
                placed = self._pullback_buy_placed
                if not placed:
                    if _raised and self._pullback_pending_set:
                        self.position.set_pending(False)
                    st.rollback_last_buy()
                    st.armed = armed
                    if st.ring is not None and st.last_ts is not None:   # 수정 1회차: 링 기록도 armed 복원
                        st.ring.amend_last_split(st.last_ts, st)
                self._pullback_pending_set = False
            self._pullback_persist()
        if placed:
            logger.info(f"[PULLBACK-FORCE] 강제 매수 {round_n}회차 주문 | user={self.user_id} ticker={self.ticker}")
            return {"status": "done", "code": "ok", "detail": {"round": round_n}}
        code = self._pullback_last_skip_code or ("split_order_cooldown" if cooling else "order_failed")
        logger.warning(f"[PULLBACK-FORCE] 강제 매수 주문 없음 | code={code} user={self.user_id}")
        return {"status": "rejected", "code": code, "detail": {"round": round_n}}

    def _execute_pullback_buy(self, bar: Bar, indicators: Dict[str, Any]) -> None:
        """
        PULLBACK 분할 매수 1회 (계획 T5 _execute_pullback_buy).
          1. 회당 금액 per_buy = floor(sizing_base / effMaxSplits). sizing_base 는 1회차 때 운용자산을 읽어 고정.
          2. per_buy < 5,000 → 건너뜀(split_below_min)
          3. 가용 KRW < per_buy × (1+수수료) → 건너뜀(split_krw_short)
          4. 직전 주문 실패 뒤 PULLBACK_BUY_FAIL_COOLDOWN_BARS 봉 안 → 건너뜀(split_order_cooldown)
          5. trader.buy_market(krw_amount=per_buy, strict_amount=True) — 늘 시장가, 지정가·지연 큐 없음
        """
        st = self.strategy
        holding = bool(self.position.has_position)
        round_n = max(1, int(getattr(st, "entry_count", 0) or 0))
        ctx = {
            "strategy_type": "PULLBACK",
            "split_round": round_n,
            "pullback_round": int(getattr(st, "pullback_count", 0) or 0),
        }
        if not (getattr(bar, "is_closed", False) and getattr(bar, "is_confirmed", False)):
            self._pullback_skip(bar, indicators, code="split_unconfirmed_bar",
                                note=f"확정 봉 아님 — 분할 매수는 확정 봉 마감에서만 — {round_n}회차 건너뜀", ctx=ctx)
            return

        if round_n <= 1 and not holding:
            self._pullback_sizing_base = self._pullback_read_sizing_base()
        elif self._pullback_sizing_base is None:
            self._pullback_sizing_base = self._pullback_read_sizing_base()
            logger.warning(f"[PULLBACK-SPLIT] {round_n}회차인데 배분 기준 없음(재시작 등) → 지금 운용자산으로 고정 "
                           f"| base={self._pullback_sizing_base} (T6 분할 상태 복원 전 임시)")
        base = self._pullback_sizing_base
        ctx["sizing_base"] = base
        if base is None:
            self._pullback_skip(bar, indicators, code="split_no_capital",
                                note=f"운용자산(users.virtual_krw) 없음 — {round_n}회차 건너뜀", ctx=ctx)
            return

        import math
        from config import MIN_FEE_RATIO
        eff = max(1, int(st.cfg["eff_max_splits"]))
        per_buy = int(math.floor(base / eff))
        ctx["per_buy"] = per_buy
        if per_buy < PULLBACK_MIN_ORDER_KRW:
            self._pullback_skip(bar, indicators, code="split_below_min",
                                note=f"1회 매수 금액 {per_buy:,}원 < 최소 5,000원 — {round_n}회차 건너뜀", ctx=ctx)
            return
        _checked = getattr(self.trader, "krw_balance_checked", None)
        if callable(_checked):
            # ✅ 2차 T6 (T5 넘김): 조회 성공 여부를 반환값으로 받는다(공유 표식 경합 없음)
            avail, _bal_ok = _checked()
            avail = float(avail or 0.0)
        else:
            avail = float(self.trader._krw_balance() or 0.0)
            _bal_ok = getattr(self.trader, "last_krw_balance_ok", True)
        ctx["avail_krw"] = avail
        if not _bal_ok:
            # 검수 반영: 조회 실패(0.0)를 잔고 부족과 구분 (_krw_balance 시그니처는 EMA 공용이라 그대로)
            self._pullback_skip(bar, indicators, code="split_krw_unknown",
                                note=f"원화 잔고 조회 실패 — 업비트 응답 확인 필요 — {round_n}회차 건너뜀", ctx=ctx)
            return
        if avail < per_buy * (1 + MIN_FEE_RATIO):
            self._pullback_skip(bar, indicators, code="split_krw_short",
                                note=(f"원화 잔고 부족 (가용 {avail:,.0f}원 < 회당 {per_buy:,}원+수수료) "
                                      f"— {round_n}회차 건너뜀"), ctx=ctx)
            return
        fail_bar = self._pullback_buy_fail_bar
        if fail_bar is not None and self.bar_count - fail_bar < PULLBACK_BUY_FAIL_COOLDOWN_BARS:
            # 시작 때 감사 1행·알림 1회로 고지했으므로 봉마다 감사 행·알림을 쌓지 않는다(로그만)
            logger.warning(
                f"⏭️ [PULLBACK-SKIP] split_order_cooldown | 매수 쉬는 중(실패 봉 #{fail_bar} 포함 "
                f"{PULLBACK_BUY_FAIL_COOLDOWN_BARS}봉, #{fail_bar + PULLBACK_BUY_FAIL_COOLDOWN_BARS} 부터 재주문) "
                f"— {round_n}회차 건너뜀 | 지금 #{self.bar_count}"
            )
            return

        # 주문 전 분할 수량·원가(기준) — 체결 반영(엔진)과 체결 감사 행 평단(trader·reconciler, 2차 T8)이 같은 값을 쓴다
        base_qty = float(self._pb_qty or 0.0) if holding else 0.0
        base_cost = float(self._pb_cost or 0.0) if holding else 0.0
        meta = {
            "bar": self.bar_count,
            "reason": getattr(st, "last_buy_reason", None) or "PULLBACK",
            "bar_time": bar.ts.astimezone(ZoneInfo("Asia/Seoul")).isoformat(),
            "interval_sec": self.interval_sec,
            "interval": self.interval_sec,   # 수정 1회차: trader·reconciler 체결 행이 읽는 키(PULLBACK 만)
            "split_round": round_n,
            "pullback_round": ctx["pullback_round"],
            "sizing_base": base,
            "per_buy": per_buy,
            "strategy_type": "PULLBACK",
            "base_qty": base_qty,      # 2차 T8: 체결 행 avg_after 계산용
            "base_cost": base_cost,
        }
        self.position.set_pending(True)
        self._pullback_pending_set = True
        _err_before = getattr(self.trader, "last_buy_error", None)
        result = self.trader.buy_market(bar.close, self.ticker, ts=bar.ts, meta=meta,
                                        krw_amount=per_buy, strict_amount=True)
        if not result:
            self.position.set_pending(False)
            self._pullback_buy_fail_bar = self.bar_count
            self._pullback_buy_fail_ts = bar.ts  # ✅ 2차 T6: 재시작 뒤에도 쿨다운 이어 가도록 봉 시각 저장
            _err = getattr(self.trader, "last_buy_error", None)
            _code = getattr(self.trader, "last_strict_reject_code", None)
            logger.warning(f"❌ [PULLBACK] {round_n}회차 매수 실패 → 실패 봉 포함 {PULLBACK_BUY_FAIL_COOLDOWN_BARS}봉 "
                           f"재주문 안 함 | err={_err} strict_code={_code}")
            # 결정 1028-03(다): 쿨다운 시작 고지 — 알림 1회 + 감사 1행 (trader 주문 전 거절도 포함)
            self._pullback_start_cooldown(bar, indicators, round_n, code=_code, err=_err, ctx=ctx)
            return

        self._pullback_buy_placed = True
        self._pullback_buy_fail_bar = None
        self._pullback_buy_fail_ts = None
        qty, price = float(result.get("qty") or 0.0), float(result.get("price") or bar.close)
        if qty <= 0 and result.get("uuid") == "DRY_RUN":
            # 수정 1회차: dry-run 은 실주문·체결 콜백이 없다 → 체결 대기로 두지 않고 주문 금액/가격 추정 수량으로 바로 반영
            qty = float(per_buy) / price if price > 0 else 0.0
            logger.info(f"[DRY-RUN] [PULLBACK] {round_n}회차 실주문 없음 → 추정 수량 {qty:.8f} 바로 반영")
        if qty <= 0 and result.get("uuid"):
            # ✅ 2차 T6 (F2): LIVE 시장가 — 체결 수량은 콜백(_on_limit_fill → _pullback_apply_fill)에서 반영.
            # 주문 시점 포지션은 건드리지 않고 기준(주문 전 분할 수량·원가)만 저장한다. pending 은 체결까지 유지.
            self._pending_split = {
                "uuid": result.get("uuid"), "round": round_n, "per_buy": per_buy, "bar": self.bar_count,
                "bar_ts": bar.ts, "base_qty": base_qty, "base_cost": base_cost, "reason": meta["reason"],
            }
            self._pullback_pending_set = False  # 봉 끝에서 pending 을 풀지 않는다(체결 콜백이 푼다)
            logger.info(f"🕐 [PULLBACK] {round_n}회차 시장가 주문 접수 | 회당 {per_buy:,}원 uuid={result.get('uuid')} "
                        f"→ 체결 반영 대기(최대 {PULLBACK_FILL_WAIT_BARS}봉)")
        else:
            self.position.apply_split_entry(qty, price, bar.ts, source="pullback_split",
                                            base_qty=base_qty, base_cost=base_cost, entry_bar=self.bar_count)
            self._pullback_set_pb_from_position()
            logger.info(f"✅ [PULLBACK] {round_n}회차 매수 | 회당 {per_buy:,}원 qty={qty:.6f} price={price:.2f} "
                        f"| 보유 qty={self.position.qty:.6f} avg={self.position.avg_price:.2f}")
            _uuid = result.get("uuid")
            _dry = _uuid == "DRY_RUN"
            # dry-run 은 uuid 가 늘 「DRY_RUN」 — 회차·봉 시각을 키에 넣어 회차마다 알림(1시간 dedupe 에 묶이지 않게)
            _key = (f"DRY_RUN-{round_n}-{bar.ts.isoformat()}" if _dry
                    else (_uuid or f"test-{bar.ts.isoformat()}-{round_n}"))
            self._pullback_notify_buy(round_n, meta["reason"], self.position.avg_price, per_buy, _key, dry_run=_dry)
        if self.q is not None:
            self.q.put((bar.ts, "BUY", qty, price, meta["reason"], None, None))

    def execute(self, action: Action, bar: Bar, indicators: Dict[str, Any]):
        """
        주문 실행 (중복 방지 포함)

        Args:
            action: 전략이 반환한 액션
            bar: 현재 봉
            indicators: 지표 스냅샷

        ✅ WO-2 (2026-09-02) execute 검사 순서 재정비:
          - PAUSE-1 게이트는 매수·매도 모두 차단이 원 의도이므로 최상단 유지.
            근거: docs/plans/2026-07-16-trading-pause/plan.md 라인 13, 41.
          - position.pending_order 검사는 매수 분기 안으로만 이동. 이전에는
            공용 위치에서 매도까지 차단되어 부분 체결 포지션에서 급락 손절이
            막히는 구조였다. 매도 앞에는 매도를 멈출 수 있는 공용 검사가 없다.
        """
        if action == Action.HOLD or action == Action.NOOP:
            return

        # PAUSE-1: 매매 일시중지 게이트 (BUY + SELL 모두 스킵, 감사로그·지표는 유지)
        # 근거: docs/plans/2026-07-16-trading-pause/plan.md ("BUY + SELL 모두 중지")
        if get_trading_paused(self.user_id):
            logger.info(f"⏸️  [PAUSE] 실주문 스킵 (감사로그·지표는 유지) | action={action.value}")
            if action == Action.BUY:
                self._audit_buy_blocked(  # ✅ WO-25
                    bar.ts, indicators, price=bar.close, code="trading_paused",
                    note="매매 일시중지 상태 — 매수 주문 전 차단",
                )
            return

        if action == Action.BUY:
            # ✅ WO-2: 매수 경로에서만 pending_order 검사. 매도는 이 검사를 건너뛴다.
            if self.position.pending_order:
                logger.warning("⏳ 주문 진행 중 → 매수 액션 대기 (매도 경로는 별도 검사 없음)")
                self._audit_buy_blocked(  # ✅ WO-25
                    bar.ts, indicators, price=bar.close, code="order_in_progress",
                    note="앞선 매수 주문이 진행 중(체결 대기) — 새 매수 주문 전 차단",
                    extra={"pending_buy_uuid": getattr(self, "_pending_buy_uuid", None)},
                )
                return

            # ✅ 2차 T5: PULLBACK — 지표 오염(PULLBACK 지표) 게이트 뒤 분할 매수 (지연 큐·지정가·already_holding 없음)
            if self.strategy_type == "PULLBACK":
                if getattr(self.pullback_indicators, "state_polluted", False):
                    self._pullback_notify_polluted()
                    self._audit_buy_blocked(
                        bar.ts, indicators, price=bar.close, code="state_polluted",
                        note="새 전략 지표 오염 상태(재시작 전까지 신규 매수 금지) — 매수 주문 전 차단",
                    )
                    return
                self._execute_pullback_buy(bar, indicators)
                return

            # ✅ WO-1 선행 1: state_polluted 게이트 — 신규 매수만 차단, 매도 경로는 계속 실행
            # Issue #11 백업/복원 실패로 지표 오염 상태(state_polluted=True)에서는
            # 크로스 판정 자체를 신뢰할 수 없으므로 신규 매수를 차단한다.
            # 해제 조건: 봇 재시작 (WARMUP 재시드). 자동 해제 없음.
            if getattr(self.indicators, 'state_polluted', False):
                logger.error(
                    f"🚫 [POLLUTED] 지표 오염 상태 — 신규 매수 차단 | "
                    f"ticker={self.ticker} bar={self.bar_count} | 재시작(WARMUP 재시드)으로만 해제 가능"
                )
                try:
                    from zoneinfo import ZoneInfo
                    _bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                    annotate_buy_eval_blocked(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        bar_time=_bar_ts_kst.isoformat(),
                        block_reason="STATE_POLLUTED",
                    )
                except Exception as _annotate_exc:
                    logger.warning(f"[POLLUTED] audit annotate 예외 무시: {_annotate_exc}")
                self._audit_buy_blocked(  # ✅ WO-25
                    bar.ts, indicators, price=bar.close, code="state_polluted",
                    note="지표 오염 상태(재시작 전까지 신규 매수 금지) — 매수 주문 전 차단",
                )
                return  # 매수 미실행
            self._execute_buy_or_defer(bar, indicators)
        elif action == Action.SELL or action == Action.CLOSE:
            # ✅ WO-2: 보호성 매도는 PendingOrderQueue 를 우회. 즉시 집행.
            # 매도 앞에는 매도를 멈출 수 있는 공용 검사가 없어야 한다 (급락 손절 보장).
            self._execute_sell(bar, indicators)

    def _execute_buy_or_defer(self, bar: Bar, indicators: Dict[str, Any]):
        """
        WO-2 재적용: 확정 여부에 따라 즉시 발주 또는 지연 큐 등록.

        - bar.is_confirmed=True: 즉시 _execute_buy 위임 (기존 경로).
        - bar.is_confirmed=False: PendingOrderQueue 에 등록하고 다음 봉 재판정
          시점까지 대기. 최대 지연 60초.

        유효성 확인 재계산은 매수용 지표 쌍(fast_buy, slow_buy)만 사용한다.
        use_separate_ema=False 인 경우 공통 EMA 로 폴백.
        """
        # ✅ 2차 T5 (X6): PULLBACK 은 지연 큐를 타지 않는다 (미확정 봉은 _execute_pullback_buy 가 거절)
        if self.strategy_type == "PULLBACK":
            self._execute_pullback_buy(bar, indicators)
            return
        if getattr(bar, 'is_confirmed', False):
            self._execute_buy(bar, indicators)
            return

        from core.pending_order import PendingOrder
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        prev_ema_fast = indicators.get('prev_ema_fast')
        prev_ema_slow = indicators.get('prev_ema_slow')
        if prev_ema_fast is None or prev_ema_slow is None:
            logger.warning(
                f"[PENDING-REGISTER] 매수용 직전 EMA 값 없음 → 지연 등록 스킵, 즉시 발주 위임 | "
                f"bar.ts={bar.ts}"
            )
            self._execute_buy(bar, indicators)
            return

        # 매수용 alpha 계수: use_separate_ema 이면 매수용 쌍, 아니면 공통.
        if getattr(self.indicators, 'use_separate_ema', False):
            alpha_fast = self.indicators.alpha_ema_fast_buy
            alpha_slow = self.indicators.alpha_ema_slow_buy
        else:
            alpha_fast = self.indicators.alpha_ema_fast
            alpha_slow = self.indicators.alpha_ema_slow

        signal_condition = 'EMA_GC' if self.strategy_type == 'EMA' else 'EMA_GC'
        now = _dt.now(ZoneInfo("Asia/Seoul"))
        pending = PendingOrder(
            bar_ts=bar.ts,
            decision='BUY',
            signal_condition=signal_condition,
            tentative_close=float(bar.close),
            ema_fast_prev=float(prev_ema_fast),
            ema_slow_prev=float(prev_ema_slow),
            ema_fast_alpha=float(alpha_fast),
            ema_slow_alpha=float(alpha_slow),
            context={
                'bar_count': self.bar_count,
                'ind_ema_fast': indicators.get('ema_fast'),
                'ind_ema_slow': indicators.get('ema_slow'),
            },
            created_at=now,
        )
        superseded = self._pending_orders.register(pending)
        if superseded is not None:
            logger.info(
                f"[PENDING-SUPERSEDE] 기존 대기 매수 취소 (새 결정으로 교체) | "
                f"old_bar_ts={superseded.bar_ts} → new_bar_ts={bar.ts}"
            )
            self._audit_wo2_resolution(
                bar_ts=superseded.bar_ts,
                validation_passed=0,
                validation_reason='SUPERSEDED',
                confirmed_close=None,
                resolved_at=now,
            )
        logger.info(
            f"[PENDING-REGISTER] 매수 지연 등록 | bar.ts={bar.ts} | "
            f"tentative_close={bar.close} | max_wait={pending.max_wait_sec}s"
        )

    def _resolve_pending_buy(self, bar: Bar) -> None:
        """
        WO-2 재적용: 이전 봉의 대기 매수 항목을 확정 재판정한다.

        이 훅은 새 봉의 실시간 평가 흐름과 별개다. 봉당 판단 1회 원칙을 지키기
        위해 _register_evaluated_bar 를 호출하지 않고 감사도 UPDATE 만 한다.
        """
        pending = self._pending_orders.current
        if pending is None:
            return

        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo
        now = _dt.now(ZoneInfo("Asia/Seoul"))

        # 대기 대상은 이전 봉이어야 한다. 같은 봉이면 아직 재판정 대상이 아니다.
        if pending.bar_ts == bar.ts:
            return

        # 지연 상한 확인. 초과 시 즉시 취소.
        if pending.is_expired(now):
            logger.warning(
                f"[PENDING-EXPIRE] 지연 상한 초과 → 취소 | pending_bar_ts={pending.bar_ts} | "
                f"created_at={pending.created_at} | max_wait={pending.max_wait_sec}s"
            )
            self._pending_orders.cancel_current(reason='MAX_WAIT_EXCEEDED', at=now)
            self._audit_wo2_resolution(
                bar_ts=pending.bar_ts,
                validation_passed=0,
                validation_reason='MAX_WAIT_EXCEEDED',
                confirmed_close=None,
                resolved_at=now,
            )
            return

        # 확정 종가 조회. 지금 봉이 pending 봉 다음 봉이면 pending 봉이 확정된 것으로
        # 간주하고, 그 확정 종가는 이전 봉의 종가로 삼는다. 실제 확정 종가는
        # rest_reconcile.fetch_confirmed_candle 로 재조회하는 것이 더 안전하나,
        # 여기서는 이미 이 봉 처리 흐름에서 확정된 정보를 활용한다.
        confirmed_close = self._lookup_confirmed_close(pending.bar_ts)
        if confirmed_close is None:
            logger.warning(
                f"[PENDING-RESOLVE] 확정 종가 조회 실패 → 다음 봉까지 재대기 | "
                f"pending_bar_ts={pending.bar_ts}"
            )
            return

        try:
            passed = pending.revalidate(confirmed_close)
        except Exception as e:
            logger.error(
                f"[PENDING-RESOLVE] 유효성 확인 예외 → 취소 | {e}", exc_info=True
            )
            self._pending_orders.cancel_current(reason='SIGNAL_INVERTED', at=now)
            self._audit_wo2_resolution(
                bar_ts=pending.bar_ts,
                validation_passed=0,
                validation_reason='SIGNAL_INVERTED',
                confirmed_close=confirmed_close,
                resolved_at=now,
            )
            return

        if not passed:
            logger.info(
                f"[PENDING-RESOLVE] 유효성 불성립 → 취소 | pending_bar_ts={pending.bar_ts} | "
                f"confirmed_close={confirmed_close}"
            )
            self._pending_orders.cancel_current(reason='SIGNAL_INVERTED', at=now)
            self._audit_wo2_resolution(
                bar_ts=pending.bar_ts,
                validation_passed=0,
                validation_reason='SIGNAL_INVERTED',
                confirmed_close=confirmed_close,
                resolved_at=now,
            )
            return

        # 유효성 성립 → 발주. 발주 후 큐 비우고 감사 UPDATE.
        logger.info(
            f"[PENDING-RESOLVE] 유효성 통과 → 발주 진행 | pending_bar_ts={pending.bar_ts} | "
            f"confirmed_close={confirmed_close}"
        )
        # 발주는 원래 판단 봉(pending.bar_ts)의 종가로 진행하는 것이 원칙이나,
        # 발주 인터페이스는 현재 봉 객체를 요구하므로 confirmed_close 를 포함한
        # 임시 Bar 로 재구성한다.
        _confirmed_bar = Bar(
            ts=pending.bar_ts,
            open=confirmed_close,
            high=confirmed_close,
            low=confirmed_close,
            close=confirmed_close,
            volume=0.0,
            is_closed=True,
            is_confirmed=True,
            source='WO2_PENDING_RESOLVE',
        )
        _resolved_indicators = {
            'ema_fast': pending.context.get('ind_ema_fast'),
            'ema_slow': pending.context.get('ind_ema_slow'),
            'macd': None,
            'signal': None,
        }
        self._pending_orders.clear()
        self._audit_wo2_resolution(
            bar_ts=pending.bar_ts,
            validation_passed=1,
            validation_reason=None,
            confirmed_close=confirmed_close,
            resolved_at=now,
        )
        self._execute_buy(_confirmed_bar, _resolved_indicators)

    def _lookup_confirmed_close(self, bar_ts) -> Optional[float]:
        """대상 봉의 확정 종가를 buffer 에서 조회. 없으면 None."""
        for _bar in reversed(self.buffer):
            if _bar.ts == bar_ts:
                return float(_bar.close)
        return None

    # ✅ WO-25 (2026-10-06): WO-2 지연 매수가 발주 없이 끝난 사유 → 사람이 읽는 문구
    _WO2_BLOCK_NOTES = {
        "SUPERSEDED": "지연 매수 대기 중 새 매수 신호로 교체 — 이전 신호의 매수 주문 전 취소",
        "MAX_WAIT_EXCEEDED": "지연 매수 대기 시간 초과 — 매수 주문 전 취소",
        "SIGNAL_INVERTED": "확정 종가로 다시 확인한 결과 매수 신호 불성립 — 매수 주문 전 취소",
    }

    def _audit_buy_blocked(
        self,
        bar_ts,
        indicators: Optional[Dict[str, Any]],
        *,
        code: str,
        note: str,
        price: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        ✅ WO-25 (2026-10-06): BUY 평가 통과(action=BUY) 뒤 주문 요청 전에 엔진이 매수를 막은 경우
        audit_trades type='BUY_REJECTED' 1행 (감사 로그 ⛔ 매수 거절). 판정·발주 흐름은 바꾸지 않는다.
        meta 는 _execute_buy 와 같은 모양 (bar·reason·bar_time·지표). 기록 실패는 삼킨다.
        """
        try:
            from zoneinfo import ZoneInfo
            ind = indicators or {}
            buy_reason = getattr(self.strategy, "last_buy_reason", None) or (
                "GOLDEN_CROSS" if self.strategy_type == "MACD" else "EMA_GC"
            )
            meta = {
                "bar": self.bar_count,
                "reason": buy_reason,
                "bar_time": bar_ts.astimezone(ZoneInfo("Asia/Seoul")).isoformat() if bar_ts is not None else None,
                "macd": ind.get("macd"),
                "signal": ind.get("signal"),
                "ema_fast": ind.get("ema_fast"),
                "ema_slow": ind.get("ema_slow"),
                "interval_sec": self.interval_sec,
            }
            self.trader._audit_preorder_reject(
                ticker=self.ticker, price=price, meta=meta, code=code, note=note, extra=extra,
            )
        except Exception as e:
            logger.warning(f"[AUDIT-REJECT] 엔진 주문 전 차단 기록 예외 무시: {e} | code={code}")

    def _audit_wo2_resolution(
        self,
        bar_ts,
        validation_passed: Optional[int],
        validation_reason: Optional[str],
        confirmed_close: Optional[float],
        resolved_at,
    ) -> None:
        """WO-2 재판정 결과를 audit_buy_eval 에 UPDATE 반영."""
        # ✅ WO-25: 발주 없이 끝난 지연 매수(취소·교체·불성립)는 audit_trades BUY_REJECTED 로도 남긴다.
        if validation_passed == 0:
            _code = str(validation_reason or "UNKNOWN")
            self._audit_buy_blocked(
                bar_ts, None, price=confirmed_close, code=f"wo2_{_code.lower()}",
                note=self._WO2_BLOCK_NOTES.get(_code, f"지연 매수 취소 ({_code}) — 매수 주문 전 취소"),
            )
        try:
            from zoneinfo import ZoneInfo
            from services.db import update_buy_eval_wo2_resolution
            bar_ts_kst = bar_ts.astimezone(ZoneInfo("Asia/Seoul"))
            resolved_at_str = (
                resolved_at.astimezone(ZoneInfo("Asia/Seoul")).isoformat()
                if hasattr(resolved_at, 'astimezone') else str(resolved_at)
            )
            update_buy_eval_wo2_resolution(
                user_id=self.user_id,
                ticker=self.ticker,
                bar_time=bar_ts_kst.isoformat(),
                validation_passed=validation_passed,
                validation_reason=validation_reason,
                confirmed_close=confirmed_close,
                resolved_at=resolved_at_str,
            )
        except Exception as e:
            logger.warning(f"[AUDIT-UPDATE] WO-2 resolution 예외 무시: {e}")

    def _execute_buy(self, bar: Bar, indicators: Dict[str, Any]):
        """
        매수 실행

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        # ✅ 2차 T5: PULLBACK 은 보유 중에도 분할 매수 — already_holding 차단을 지나지 않는다
        if self.strategy_type == "PULLBACK":
            self._execute_pullback_buy(bar, indicators)
            return
        if self.position.has_position:
            logger.warning("⛔ 이미 포지션 보유 중 → BUY 무시")
            self._audit_buy_blocked(  # ✅ WO-25
                bar.ts, indicators, price=bar.close, code="already_holding",
                note="이미 포지션 보유 중 — 매수 주문 전 차단",
            )
            return

        # 매수 실행
        self.position.set_pending(True)

        # ✅ 전략이 판정한 실제 reason 사용 (fallback: 조건 키 대문자)
        buy_reason = getattr(self.strategy, "last_buy_reason", None) or (
            "GOLDEN_CROSS" if self.strategy_type == "MACD" else "EMA_GC"
        )

        # bar.ts를 KST로 변환
        from zoneinfo import ZoneInfo
        # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
        bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))

        meta = {
            "bar": self.bar_count,
            "reason": buy_reason,  # ✅ 동적 reason
            "bar_time": bar_ts_kst.isoformat(),  # ✅ 봉 시각
            "macd": indicators.get("macd"),
            "signal": indicators.get("signal"),
            "ema_fast": indicators.get("ema_fast"),
            "ema_slow": indicators.get("ema_slow"),
        }

        # ✅ WO-26: 약매수 진입(익절 기준 축소) — orders.meta 에 함께 저장, 체결 확정 시 override·포지션 meta 로 옮긴다
        _weak = getattr(self.strategy, "last_weak_entry", None)
        if _weak:
            meta["weak_entry"] = dict(_weak)
            meta["audit_note"] = weak_entry_note(_weak["tp"])  # 매수 행 비고 (audit_trades.note)

        # ✅ 고정가 매수 분기: LIVE 모드 + buy_conditions.fixed_price_buy_enabled
        _buy_cond = getattr(self.strategy, "buy_conditions", None) or {}
        fixed_price_mode = (
            (not self.trader.test_mode)
            and bool(_buy_cond.get("fixed_price_buy_enabled", False))
        )

        if fixed_price_mode:
            meta["fixed_price_buy"] = True
            # ✅ SP6 — 대기 봉 수 (사용자 conditions, 기본 3)
            wait_bars = int(_buy_cond.get("fixed_price_buy_wait_bars", 3) or 3)
            wait_bars = max(1, min(5, wait_bars))  # 안전 클램프 1~5
            meta["wait_bars"] = wait_bars  # ✅ WO-24: 미체결 취소 기록용 (주문 meta)
            effective_interval_sec = self.interval_sec * wait_bars
            logger.info(
                f"🎯 [FIXED-PRICE] 고정가 매수 모드 진입 | "
                f"close={bar.close} ticker={self.ticker} "
                f"wait_bars={wait_bars} effective_timeout≈{effective_interval_sec-5}s"
            )
            result = self.trader.buy_limit(
                bar.close,
                self.ticker,
                ts=bar.ts,
                meta=meta,
                interval_sec=effective_interval_sec,  # ✅ SP6 — wait_bars 곱셈된 값 전달
            )
        else:
            result = self.trader.buy_market(
                bar.close,
                self.ticker,
                ts=bar.ts,
                meta=meta
            )

        if result:
            # ✅ LIMIT 미체결 — position.open_position 보류, pending_order=True 유지.
            # 봉 마감 시 Reconciler가 cancel → wait_bars 봉 진입 시 _maybe_release_limit_pending 에서 해제.
            if result.get("limit_pending"):
                self._pending_buy_uuid = result.get("uuid")
                self._pending_buy_bar = self.bar_count
                # ✅ SP6 — 대기 봉 수 기록 (pending 해제 시점 판단용)
                self._pending_buy_wait_bars = int(_buy_cond.get("fixed_price_buy_wait_bars", 3) or 3)
                self._pending_buy_wait_bars = max(1, min(5, self._pending_buy_wait_bars))
                # ✅ WO-26: 체결 확정(_on_limit_fill) 때 약매수 표식을 옮기기 위해 보관
                self._pending_buy_weak = (dict(meta["weak_entry"]), meta.get("bar_time")) if meta.get("weak_entry") else None
                logger.info(
                    f"🎯 LIMIT BUY 등록(체결 대기) | price={result['price']:.4f} "
                    f"uuid={result.get('uuid')} bar={self.bar_count} "
                    f"wait_bars={self._pending_buy_wait_bars}"
                )
                # 이벤트 큐 BUY 전송은 reconciler 가 체결 확정 시점에 별도 처리.
                return

            self.position.open_position(
                result["qty"],
                result["price"],
                self.bar_count,
                bar.ts
            )
            # ✅ WO-26: 시장가 체결 확정 — 약매수면 override + 포지션 meta
            if meta.get("weak_entry"):
                from core.weak_entry import record_weak_entry
                record_weak_entry(self.position, meta["weak_entry"], result.get("uuid"), meta.get("bar_time"),
                                  user_id=self.user_id, ticker=self.ticker)
            logger.info(
                f"✅ BUY 체결 | qty={result['qty']:.6f} price={result['price']:.2f} "
                f"bar={self.bar_count}"
            )

            # 이벤트 큐에 BUY 전송
            if self.q is not None:
                self.q.put((
                    bar.ts,
                    "BUY",
                    result["qty"],
                    result["price"],
                    meta.get("reason", "BUY"),
                    indicators.get("macd"),
                    indicators.get("signal"),
                ))
        else:
            self.position.set_pending(False)
            logger.warning("❌ BUY 실패")

    def _execute_sell(self, bar: Bar, indicators: Dict[str, Any]):
        """
        매도 실행

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if not self.position.has_position:
            logger.warning("⛔ 포지션 없음 → SELL 무시")
            return

        # 매도 실행
        self.position.set_pending(True)

        pnl_pct = self.position.get_pnl_pct(bar.close)
        bars_held = self.position.get_bars_held(self.bar_count)

        # ✅ 전략이 판정한 실제 reason 사용 (fallback: 조건 키 대문자)
        sell_reason = getattr(self.strategy, "last_sell_reason", None) or (
            "DEAD_CROSS" if self.strategy_type == "MACD" else "EMA_DC"
        )

        # ✅ bar_time: 해당 봉의 시각 (KST)
        # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
        bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))

        meta = {
            "bar": self.bar_count,
            "reason": sell_reason,  # ✅ 동적 reason (TP/SL/TS/DC 구분)
            "bar_time": bar_ts_kst.isoformat(),  # ✅ 해당 봉의 시각
            "entry_bar": self.position.entry_bar,
            "entry_price": self.position.avg_price,
            "bars_held": bars_held,
            "pnl_pct": pnl_pct,
            "macd": indicators.get("macd"),
            "signal": indicators.get("signal"),
        }
        # ✅ WO-26: 약매수 포지션 매도 행 비고
        if self.position.take_profit_override is not None:
            meta["audit_note"] = weak_position_note(self.position.take_profit_override)
        if self.strategy_type == "PULLBACK":
            # ✅ 2차 T8: 매도 체결 행 meta — 판정가(TP·SL 가격 또는 데드크로스 판정 봉 종가)·판정 사유·회차
            #   (요청서 8절 「익절 판정인데 손해」 관찰용. 체결가는 trader·reconciler 가 fill_price 로 더한다)
            _ev = getattr(self.strategy, "last_eval", {}) or {}
            _jr = str(sell_reason or "").upper()
            _jp = {"TP": _ev.get("tp_price"), "SL": _ev.get("sl_price")}.get(_jr, float(bar.close))
            meta.update({
                "strategy_type": "PULLBACK",
                "interval": self.interval_sec,   # 수정 1회차: 체결 행 봉 단위(EMA meta 는 그대로)
                "split_round": int(_ev.get("exit_round") or 0),
                "pullback_round": int(_ev.get("exit_pullback_round") or 0),
                "judged_reason": _jr or None,
                "judged_price": (float(_jp) if _jp is not None else float(bar.close)),
            })

        result = self.trader.sell_market(
            self.position.qty,
            self.ticker,
            bar.close,
            ts=bar.ts,
            meta=meta
        )

        if result:
            logger.info(
                f"✅ SELL 체결 | qty={result['qty']:.6f} price={result['price']:.2f} "
                f"pnl={pnl_pct:.2%} bars_held={bars_held}"
            )

            # 이벤트 큐에 SELL 전송
            if self.q is not None:
                self.q.put((
                    bar.ts,
                    "SELL",
                    result["qty"],
                    result["price"],
                    meta.get("reason", "SELL"),
                    indicators.get("macd"),
                    indicators.get("signal"),
                ))

            if self.strategy_type == "PULLBACK":
                # ✅ 2차 T6: 실현 손익(수수료 포함, 매도 추정가 기준) 누적 + 분할 상태 초기화 — close_position 전에 원가를 읽는다
                from config import MIN_FEE_RATIO
                _held = float(self.position.qty or 0.0)
                _rq = float(result.get("qty") or _held)
                _rp = float(result.get("price") or bar.close)
                _cost = float(self._pb_cost or 0.0) or _held * float(self.position.avg_price or 0.0)
                _realized = _rq * _rp * (1 - MIN_FEE_RATIO) - _cost * (1 + MIN_FEE_RATIO)
                self._pullback_on_exit(_realized, reason="bot_sell")
                self._pullback_buy_fail_ts = None
            self.position.close_position(bar.ts, reason="bot_sell")  # ✅ WO-18: hts_buy 해제 사유
            if self.strategy_type == "PULLBACK" and self._pullback_buy_fail_bar is not None:
                # 결정 1028-03(다): 봇 매도 체결 → 매수 쿨다운 해제(알림 없음)
                logger.info(f"[PULLBACK-COOLDOWN] 봇 매도 체결 → 매수 쉼 해제 | 실패 봉 #{self._pullback_buy_fail_bar}")
                self._pullback_buy_fail_bar = None
        else:
            self.position.set_pending(False)
            logger.warning("❌ SELL 실패")

    def _log_bar_evaluation(self, bar: Bar, indicators: Dict[str, Any], action: Action):
        """
        봉 평가 로그 출력

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
            action: 전략 액션
        """
        if self.strategy_type == "MACD":
            logger.info(
                f"📊 Bar#{self.bar_count} | ts={bar.ts} | close={bar.close:.2f} | "
                f"macd={indicators['macd']:.5f} | signal={indicators['signal']:.5f} | "
                f"action={action.value} | pos={self.position.has_position}"
            )
        elif self.strategy_type == "EMA":
            logger.info(
                f"📊 Bar#{self.bar_count} | ts={bar.ts} | close={bar.close:.2f} | "
                f"ema_fast={indicators['ema_fast']:.2f} | ema_slow={indicators['ema_slow']:.2f} | "
                f"ema_base={indicators['ema_base']:.2f} | "
                f"action={action.value} | pos={self.position.has_position}"
            )

    def _send_log_event(self, bar: Bar, indicators: Dict[str, Any]):
        """
        LOG 이벤트 전송 (Streamlit용)

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
        """
        if self.q is None:
            return

        if self.strategy_type == "MACD":
            cross_status = "Neutral"
            if indicators["macd"] > indicators["signal"]:
                cross_status = "Golden"
            elif indicators["macd"] < indicators["signal"]:
                cross_status = "Dead"

            msg = (
                f"{bar.ts} | price={bar.close:.2f} | "
                f"cross={cross_status} | macd={indicators['macd']:.5f} | signal={indicators['signal']:.5f} | "
                f"bar={self.bar_count}"
            )
        else:  # EMA
            cross_status = "Neutral"
            if indicators["ema_fast"] > indicators["ema_slow"]:
                cross_status = "Golden"
            elif indicators["ema_fast"] < indicators["ema_slow"]:
                cross_status = "Dead"

            msg = (
                f"{bar.ts} | price={bar.close:.2f} | "
                f"cross={cross_status} | ema_fast={indicators['ema_fast']:.2f} | "
                f"ema_slow={indicators['ema_slow']:.2f} | ema_base={indicators['ema_base']:.2f} | "
                f"bar={self.bar_count}"
            )

        self.q.put((bar.ts, "LOG", msg))

    def record_warmup_log(self, bar: Bar, warmup_progress: str):
        """
        WARMUP 구간 평가 로그 기록

        Args:
            bar: 현재 봉
            warmup_progress: WARMUP 진행 상황 (예: "(150/200)" 또는 "(완료 200/200)")
        """
        try:
            current_price = bar.close

            # WARMUP 중에는 지표 값이 없으므로 None 처리
            macd = None
            signal = None

            # 전략 타입에 따라 checks 구성
            if self.strategy_type == "EMA":
                checks = {
                    "status": "WARMUP",
                    "progress": warmup_progress,
                    "reason": "WARMUP_IN_PROGRESS",
                    "ema_fast": None,
                    "ema_slow": None,
                    "ema_base": None,
                    "price": float(current_price) if current_price is not None else None,
                }

                # ✅ Base EMA GAP 전략 모드 감지 (enable_base_ema_gap 속성 우선 확인)
                if hasattr(self.strategy, 'enable_base_ema_gap') and self.strategy.enable_base_ema_gap:
                    checks["strategy_mode"] = "BASE_EMA_GAP"
                else:
                    checks["strategy_mode"] = "EMA"  # ✅ 일반 EMA 전략
            else:  # MACD
                checks = {
                    "status": "WARMUP",
                    "progress": warmup_progress,
                    "reason": "WARMUP_IN_PROGRESS",
                    "macd": None,
                    "signal": None,
                    "price": float(current_price) if current_price is not None else None,
                    "strategy_mode": "MACD",  # ✅ MACD 전략
                }

            # ✅ 2차 T5: PULLBACK 은 EMA·MACD 칸이 아닌 자기 라벨 (진행 문구는 live_loop 가 지표 봉 수로 넘김)
            if self.strategy_type == "PULLBACK":
                checks = {
                    "status": "WARMUP",
                    "progress": warmup_progress,
                    "reason": "WARMUP_IN_PROGRESS",
                    "strategy": "PULLBACK",
                    "strategy_mode": "PULLBACK",
                    "price": float(current_price) if current_price is not None else None,
                }

            notes = f"⏳ WARMUP 진행 중 {warmup_progress}"
            if self.strategy_type == "PULLBACK":
                checks["failed_keys"] = ["WARMUP"]
                notes = f"새 전략 · 준비 중(지표 계산) {warmup_progress}"

            # 포지션 없을 때: BUY 평가 로그 기록
            if not self.position.has_position:
                # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                # ✅ WO-19: warmup_placeholder=True — 실제 판정 행은 보존, 결과("kept"/"inserted"/"updated_placeholder") 반환
                return insert_buy_eval(
                    user_id=self.user_id,
                    ticker=self.ticker,
                    interval_sec=self.interval_sec,
                    bar=self.bar_count,
                    price=current_price,
                    macd=macd,
                    signal=signal,
                    have_position=False,
                    overall_ok=False,
                    # ✅ 2차 T8: PULLBACK 은 감사 failed_keys 목록의 WARMUP (EMA·MACD 는 그대로)
                    failed_keys=(["WARMUP"] if self.strategy_type == "PULLBACK" else ["WARMUP_IN_PROGRESS"]),
                    checks=checks,
                    notes=notes,
                    bar_time=bar_ts_kst.isoformat(),
                    warmup_placeholder=True,
                )
            else:
                # 포지션 있을 때: SELL 평가 로그 기록
                # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                return insert_sell_eval(
                    user_id=self.user_id,
                    ticker=self.ticker,
                    interval_sec=self.interval_sec,
                    bar=self.bar_count,
                    price=current_price,
                    macd=macd,
                    signal=signal,
                    tp_price=0,
                    sl_price=0,
                    highest=None,
                    ts_pct=None,
                    ts_armed=bool(getattr(self.position, "trailing_armed", False)),  # ✅ WO-21: 실제 무장 여부 (이전 False 고정)
                    bars_held=0,
                    checks=checks,
                    triggered=False,
                    trigger_key=None,
                    notes=notes,
                    bar_time=bar_ts_kst.isoformat(),
                    warmup_placeholder=True,  # ✅ WO-19
                )
        except Exception as e:
            logger.error(f"❌ WARMUP 로그 기록 실패: {e}")
            return None

    def _record_audit_log(self, bar: Bar, indicators: Dict[str, Any], action: Action, is_backfill: bool = False):
        """
        감사 로그 기록 (매 봉마다)

        Args:
            bar: 현재 봉
            indicators: 지표 스냅샷
            action: 전략 액션
            is_backfill: BACKFILL 재평가 경로 여부 (True면 실주문 미실행)
        """
        try:
            current_price = bar.close

            # ✅ 전략 타입에 따라 지표 값 및 checks 구성
            if self.strategy_type == "MACD":
                # MACD 전략: macd, signal 컬럼 사용
                macd = indicators.get("macd")
                signal = indicators.get("signal")

                # checks 필드도 MACD 기준 (JSON 직렬화를 위해 float 변환)
                base_checks = {
                    "reason": None,  # 나중에 설정
                    "macd": float(macd) if macd is not None else None,
                    "signal": float(signal) if signal is not None else None,
                    "price": float(current_price) if current_price is not None else None,
                    "strategy_mode": "MACD",  # ✅ MACD 전략
                    "via_backfill": bool(is_backfill),  # BACKFILL 재평가 경로 여부 (실주문 미실행 케이스 구분)
                    # ✅ WO-2 옵션 C (2026-09-02): 미확정 봉 평가 표식.
                    # bar.is_confirmed=False 인 잠정 봉을 감사에서 구분할 수 있게 한다.
                    "via_tentative": not bool(getattr(bar, 'is_confirmed', True)),
                }
            else:  # EMA
                # EMA 전략: macd 컬럼에 ema_fast, signal 컬럼에 ema_slow 저장
                # (audit_viewer.py에서 delta 계산 및 컬럼명 변경에 사용)
                macd = indicators.get("ema_fast")
                signal = indicators.get("ema_slow")

                # ✅ 매수/매도 별도 EMA 정보 추출
                use_separate_ema = indicators.get("use_separate_ema", False)
                ema_fast_buy = indicators.get("ema_fast_buy")
                ema_slow_buy = indicators.get("ema_slow_buy")
                ema_fast_sell = indicators.get("ema_fast_sell")
                ema_slow_sell = indicators.get("ema_slow_sell")

                # checks 필드는 EMA 지표 기준 (JSON 직렬화를 위해 float 변환)
                base_checks = {
                    "reason": None,  # 나중에 설정
                    "ema_fast": float(indicators.get("ema_fast")) if indicators.get("ema_fast") is not None else None,
                    "ema_slow": float(indicators.get("ema_slow")) if indicators.get("ema_slow") is not None else None,
                    "ema_base": float(indicators.get("ema_base")) if indicators.get("ema_base") is not None else None,
                    "price": float(current_price) if current_price is not None else None,
                    # ✅ 매수/매도 별도 EMA 기록
                    "use_separate_ema": bool(use_separate_ema),
                    "ema_fast_buy": float(ema_fast_buy) if ema_fast_buy is not None else None,
                    "ema_slow_buy": float(ema_slow_buy) if ema_slow_buy is not None else None,
                    "ema_fast_sell": float(ema_fast_sell) if ema_fast_sell is not None else None,
                    "ema_slow_sell": float(ema_slow_sell) if ema_slow_sell is not None else None,
                    "via_backfill": bool(is_backfill),  # BACKFILL 재평가 경로 여부 (실주문 미실행 케이스 구분)
                    # ✅ WO-2 옵션 C (2026-09-02): 미확정 봉 평가 표식.
                    "via_tentative": not bool(getattr(bar, 'is_confirmed', True)),
                }

                # ✅ Base EMA GAP 전략 모드 감지 (enable_base_ema_gap 속성 우선 확인)
                if hasattr(self.strategy, 'enable_base_ema_gap') and self.strategy.enable_base_ema_gap:
                    base_checks["strategy_mode"] = "BASE_EMA_GAP"
                else:
                    base_checks["strategy_mode"] = "EMA"  # ✅ 일반 EMA 전략

            # 포지션 없을 때: BUY 평가 로그
            if not self.position.has_position:
                # ✅ Base EMA GAP 전략 특별 처리
                gap_details = getattr(self.strategy, "gap_details", None)

                if gap_details and gap_details.get("strategy_mode") == "BASE_EMA_GAP":
                    # Base EMA GAP 전략 전용 로그
                    gap_pct = gap_details.get("gap_pct", 0)
                    gap_threshold = gap_details.get("gap_threshold", 0)
                    gap_to_target = gap_details.get("gap_to_target", 0)
                    price_needed = gap_details.get("price_needed", 0)
                    condition_met = gap_details.get("condition_met", False)
                    reason = gap_details.get("reason", "GAP_INSUFFICIENT")

                    # Cross status 설정
                    if condition_met:
                        if abs(gap_pct) > abs(gap_threshold * 2):
                            cross_status = "🔥 GAP_EXCEEDED"
                        else:
                            cross_status = "✅ GAP_MET"
                    else:
                        cross_status = "📉 GAP_WATCH"

                    # Checks 필드 구성
                    buy_checks = gap_details.copy()
                    buy_checks["cross_status"] = cross_status
                    buy_checks["via_backfill"] = bool(is_backfill)  # BACKFILL 재평가 경로 여부

                    # Notes 구성
                    if condition_met:
                        if cross_status == "🔥 GAP_EXCEEDED":
                            notes = f"🔥 급락 감지! Base EMA GAP: {gap_pct:.2%} (목표: {gap_threshold:.2%}, 초과: {abs(gap_to_target):.2%}p) | Base: ₩{gap_details.get('base_ema', 0):,.0f}"
                        else:
                            notes = f"✅ Base EMA GAP 매수 조건 충족! {gap_pct:.2%} (목표: {gap_threshold:.2%}, 초과: {abs(gap_to_target):.2%}p) | Base: ₩{gap_details.get('base_ema', 0):,.0f}"
                    else:
                        notes = f"📉 Base EMA GAP: {gap_pct:.2%} (목표: {gap_threshold:.2%}, 부족: {abs(gap_to_target):.2%}p) | 매수가: ₩{price_needed:,.0f} | Base: ₩{gap_details.get('base_ema', 0):,.0f}"

                    # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                    # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                    bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                    insert_buy_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        have_position=False,
                        overall_ok=condition_met,
                        failed_keys=[] if condition_met else [reason],
                        checks=buy_checks,
                        notes=notes,
                        bar_time=bar_ts_kst.isoformat(),
                        is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
                    )
                else:
                    # 일반 EMA/MACD 전략 로그 (기존 로직)
                    # Cross 상태 판단
                    cross_status = "Neutral"
                    if self.strategy_type == "EMA":
                        ema_fast = indicators.get("ema_fast")
                        ema_slow = indicators.get("ema_slow")
                        if ema_fast and ema_slow:
                            if ema_fast > ema_slow:
                                cross_status = "Golden"
                            elif ema_fast < ema_slow:
                                cross_status = "Dead"
                    elif self.strategy_type == "MACD":
                        macd_val = indicators.get("macd")
                        signal_val = indicators.get("signal")
                        if macd_val and signal_val:
                            if macd_val > signal_val:
                                cross_status = "Golden"
                            elif macd_val < signal_val:
                                cross_status = "Dead"

                    if action == Action.HOLD or action == Action.NOOP:
                        # 신호 없음
                        buy_checks = base_checks.copy()
                        buy_checks["reason"] = "NO_BUY_SIGNAL"
                        buy_checks["cross_status"] = cross_status

                        # ✅ 필터 결과 추가 (감사로그 상세 정보)
                        failed_keys_list = ["NO_SIGNAL"]
                        if hasattr(self.strategy, 'last_buy_filter_result') and self.strategy.last_buy_filter_result:
                            filter_res = self.strategy.last_buy_filter_result
                            buy_checks["filter_blocked"] = filter_res.should_block
                            buy_checks["filter_reason"] = filter_res.reason
                            buy_checks["filter_details"] = filter_res.details
                            if filter_res.metadata:
                                buy_checks["filter_metadata"] = filter_res.metadata
                            # ✅ 필터가 차단한 경우 failed_keys 업데이트
                            if filter_res.should_block:
                                failed_keys_list = [filter_res.reason]

                        # ✅ WO-26: 약매수 차단은 메모에 사유 문구 ("약매수 차단 (D/C 뒤 n분, 기준 h시간)")
                        _hold_note = "NO_SIGNAL"
                        if failed_keys_list == [WEAK_ENTRY_FILTER_REASON]:
                            _hold_note = self.strategy.last_buy_filter_result.details or WEAK_ENTRY_FILTER_REASON

                        # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                        # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                        bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                        insert_buy_eval(
                            user_id=self.user_id,
                            ticker=self.ticker,
                            interval_sec=self.interval_sec,
                            bar=self.bar_count,
                            price=current_price,
                            macd=macd,
                            signal=signal,
                            have_position=False,
                            overall_ok=False,
                            failed_keys=failed_keys_list,
                            checks=buy_checks,
                            notes=f"{cross_status} | {_hold_note} | bar={self.bar_count}",
                            bar_time=bar_ts_kst.isoformat(),
                            is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
                        )
                    elif action == Action.BUY:
                        # BUY 신호 발생
                        buy_checks = base_checks.copy()
                        buy_checks["reason"] = "BUY_SIGNAL"
                        buy_checks["cross_status"] = cross_status

                        # ✅ 필터 결과 추가 (통과 정보)
                        if hasattr(self.strategy, 'last_buy_filter_result') and self.strategy.last_buy_filter_result:
                            filter_res = self.strategy.last_buy_filter_result
                            buy_checks["filter_blocked"] = False  # 통과
                            buy_checks["filter_reason"] = filter_res.reason
                            buy_checks["filter_details"] = filter_res.details
                            if filter_res.metadata:
                                buy_checks["filter_metadata"] = filter_res.metadata

                        # ✅ WO-26: 약매수 진입(익절 기준 축소) 비고
                        _buy_note = ""
                        _weak = getattr(self.strategy, "last_weak_entry", None)
                        if _weak:
                            buy_checks["weak_entry"] = dict(_weak)
                            _buy_note = f" | {weak_entry_note(_weak['tp'])}"

                        # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                        # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                        bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                        insert_buy_eval(
                            user_id=self.user_id,
                            ticker=self.ticker,
                            interval_sec=self.interval_sec,
                            bar=self.bar_count,
                            price=current_price,
                            macd=macd,
                            signal=signal,
                            have_position=False,
                            overall_ok=True,
                            failed_keys=[],
                            checks=buy_checks,
                            notes=f"🟢 BUY | {cross_status} | bar={self.bar_count}{_buy_note}",
                            bar_time=bar_ts_kst.isoformat(),
                            is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
                        )

            # 포지션 있을 때: SELL 평가 로그
            else:
                entry_price = self.position.avg_price
                # ✅ WO-9 (d) (2026-09-30): 감사 기록 임계값은 실제 필터가 쓰는 strategy 값에서 읽는다.
                #   self.stop_loss/take_profit 는 엔진 생성 시 params 로 한 번만 정해지고, 조건 파일
                #   hot reload(engine/live_loop.py:365-392)는 strategy·필터만 갱신 → 감사 행이 옛 임계
                #   (예: 1.5%)로 남던 결함 (2026-09-30 KRW-JTO: 실제 필터 3.0%, 감사 sl_price 755.495).
                #   기록 전용 — 매매 판정은 이 값을 쓰지 않는다.
                _audit_tp = getattr(self.strategy, "take_profit", None)
                _audit_sl = getattr(self.strategy, "stop_loss", None)
                if not isinstance(_audit_tp, (int, float)):
                    _audit_tp = self.take_profit
                if not isinstance(_audit_sl, (int, float)):
                    _audit_sl = self.stop_loss
                # ✅ WO-26: 약매수 포지션이면 실제 필터가 쓰는 축소 익절 기준으로 기록
                if self.position.take_profit_override is not None:
                    _audit_tp = self.position.take_profit_override
                tp_price = entry_price * (1 + _audit_tp) if entry_price else None
                sl_price = entry_price * (1 - _audit_sl) if entry_price else None
                bars_held = self.position.get_bars_held(self.bar_count)

                # ✅ bars_held가 0 이하일 때 대안: SELL 평가 개수 세기 (간단!)
                if bars_held <= 0:
                    bars_held = estimate_bars_held_from_audit(self.user_id, self.ticker)

                # ✅ SELL 평가 상세 정보 계산
                pnl_pct = self.position.get_pnl_pct(current_price) if entry_price else 0.0

                # Cross 상태 판단 (EMA 전략용)
                cross_status = "Neutral"
                if self.strategy_type == "EMA":
                    ema_fast = indicators.get("ema_fast")
                    ema_slow = indicators.get("ema_slow")
                    if ema_fast and ema_slow:
                        if ema_fast > ema_slow:
                            cross_status = "Golden"
                        elif ema_fast < ema_slow:
                            cross_status = "Dead"
                elif self.strategy_type == "MACD":
                    macd_val = indicators.get("macd")
                    signal_val = indicators.get("signal")
                    if macd_val and signal_val:
                        if macd_val > signal_val:
                            cross_status = "Golden"
                        elif macd_val < signal_val:
                            cross_status = "Dead"

                # 매도 조건 체크
                tp_hit = bool((tp_price is not None) and (current_price >= tp_price))
                sl_hit = bool((sl_price is not None) and (current_price <= sl_price))

                # ✅ Dead Cross 조건 체크 추가
                ema_fast = indicators.get("ema_fast")
                ema_slow = indicators.get("ema_slow")
                prev_ema_fast = indicators.get("prev_ema_fast")
                prev_ema_slow = indicators.get("prev_ema_slow")

                ema_dead_cross = (
                    prev_ema_fast is not None and prev_ema_slow is not None
                    and prev_ema_fast >= prev_ema_slow
                    and ema_fast is not None and ema_slow is not None
                    and ema_fast < ema_slow
                )

                if action == Action.HOLD or action == Action.NOOP:
                    # 신호 없음
                    sell_checks = base_checks.copy()
                    sell_checks["reason"] = "NO_SELL_SIGNAL"
                    sell_checks["entry_price"] = float(entry_price) if entry_price else None
                    sell_checks["pnl_pct"] = float(pnl_pct)
                    sell_checks["cross_status"] = cross_status
                    sell_checks["tp_hit"] = int(tp_hit)  # ✅ bool → int
                    sell_checks["sl_hit"] = int(sl_hit)  # ✅ bool → int
                    sell_checks["bars_held"] = int(bars_held)
                    sell_checks["ema_dc_detected"] = int(ema_dead_cross)  # ✅ Dead Cross 조건 추가 (bool → int)

                    # ✅ Stale Position 상태 추가 (시간 기반)
                    if hasattr(self.strategy, 'enable_stale_position') and self.strategy.enable_stale_position:
                        max_gain = self.position.get_max_gain_from_entry() or 0.0
                        required_hours = self.strategy.stale_hours

                        # ✅ 실제 경과 시간 계산
                        elapsed_hours = 0.0
                        if self.position.entry_ts:
                            elapsed = bar.ts - self.position.entry_ts
                            elapsed_hours = elapsed.total_seconds() / 3600

                        sell_checks["stale_enabled"] = True
                        sell_checks["stale_elapsed_hours"] = float(elapsed_hours)
                        sell_checks["stale_required_hours"] = float(required_hours)
                        sell_checks["stale_max_gain_pct"] = float(max_gain)
                        sell_checks["stale_threshold_pct"] = float(self.strategy.stale_threshold_pct)
                        sell_checks["stale_triggered"] = int(
                            elapsed_hours >= required_hours and max_gain < self.strategy.stale_threshold_pct
                        )

                    # ✅ 필터 결과 추가 (감사로그 상세 정보 - 매도 신호 없음)
                    if hasattr(self.strategy, 'last_sell_filter_result') and self.strategy.last_sell_filter_result:
                        filter_res = self.strategy.last_sell_filter_result
                        sell_checks["filter_evaluated"] = True
                        sell_checks["filter_reason"] = filter_res.reason
                        sell_checks["filter_details"] = filter_res.details
                        if filter_res.metadata:
                            sell_checks["filter_metadata"] = filter_res.metadata

                    # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                    # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                    bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                    insert_sell_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        highest=self.position.highest_price,
                        ts_pct=self.trailing_stop_pct,
                        ts_armed=bool(getattr(self.position, "trailing_armed", False)),  # ✅ WO-21: 실제 무장 여부 (이전 False 고정)
                        bars_held=bars_held,
                        checks=sell_checks,
                        triggered=False,
                        trigger_key=None,
                        notes=f"{cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}",
                        bar_time=bar_ts_kst.isoformat(),
                        is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
                    )
                elif action == Action.SELL or action == Action.CLOSE:
                    # SELL 신호 발생 - 구체적인 트리거 원인 판단
                    trigger_reason = "STRATEGY_SIGNAL"
                    # ✅ WO-9 (d): 전략이 실제로 정한 사유(발주 meta 와 동일)를 우선 기록.
                    #   없을 때만 기존 추정(sl_hit → tp_hit → cross → stale) 사용.
                    _actual_reason = getattr(self.strategy, "last_sell_reason", None)
                    if isinstance(_actual_reason, str) and _actual_reason:
                        trigger_reason = _actual_reason
                    elif sl_hit:
                        trigger_reason = "STOP_LOSS"
                    elif tp_hit:
                        trigger_reason = "TAKE_PROFIT"
                    elif cross_status == "Dead":
                        trigger_reason = "DEAD_CROSS"
                    # ✅ Stale Position 트리거 확인
                    elif hasattr(self.strategy, 'last_sell_reason') and self.strategy.last_sell_reason == "STALE_POSITION":
                        trigger_reason = "STALE_POSITION"

                    sell_checks = base_checks.copy()
                    sell_checks["reason"] = "SELL_SIGNAL"
                    sell_checks["entry_price"] = float(entry_price) if entry_price else None
                    sell_checks["pnl_pct"] = float(pnl_pct)
                    sell_checks["cross_status"] = cross_status
                    sell_checks["tp_hit"] = int(tp_hit)  # ✅ bool → int
                    sell_checks["sl_hit"] = int(sl_hit)  # ✅ bool → int
                    sell_checks["bars_held"] = int(bars_held)
                    sell_checks["trigger_reason"] = trigger_reason
                    sell_checks["ema_dc_detected"] = int(ema_dead_cross)  # ✅ Dead Cross 조건 추가 (bool → int)

                    # ✅ Stale Position 상태 추가 (시간 기반)
                    if hasattr(self.strategy, 'enable_stale_position') and self.strategy.enable_stale_position:
                        max_gain = self.position.get_max_gain_from_entry() or 0.0
                        required_hours = self.strategy.stale_hours

                        # ✅ 실제 경과 시간 계산
                        elapsed_hours = 0.0
                        if self.position.entry_ts:
                            elapsed = bar.ts - self.position.entry_ts
                            elapsed_hours = elapsed.total_seconds() / 3600

                        sell_checks["stale_enabled"] = True
                        sell_checks["stale_elapsed_hours"] = float(elapsed_hours)
                        sell_checks["stale_required_hours"] = float(required_hours)
                        sell_checks["stale_max_gain_pct"] = float(max_gain)
                        sell_checks["stale_threshold_pct"] = float(self.strategy.stale_threshold_pct)
                        sell_checks["stale_triggered"] = int(trigger_reason == "STALE_POSITION")

                    # ✅ 필터 결과 추가 (감사로그 상세 정보 - 매도 트리거)
                    if hasattr(self.strategy, 'last_sell_filter_result') and self.strategy.last_sell_filter_result:
                        filter_res = self.strategy.last_sell_filter_result
                        sell_checks["filter_evaluated"] = True
                        sell_checks["filter_triggered"] = filter_res.should_block
                        sell_checks["filter_reason"] = filter_res.reason
                        sell_checks["filter_details"] = filter_res.details
                        if filter_res.metadata:
                            sell_checks["filter_metadata"] = filter_res.metadata

                    # ✅ bar.ts는 UTC timezone-aware → KST로 변환
                    # ✅ UTC → KST 변환 (replace가 아닌 astimezone 사용)
                    bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
                    insert_sell_eval(
                        user_id=self.user_id,
                        ticker=self.ticker,
                        interval_sec=self.interval_sec,
                        bar=self.bar_count,
                        price=current_price,
                        macd=macd,
                        signal=signal,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        highest=self.position.highest_price,
                        ts_pct=self.trailing_stop_pct,
                        ts_armed=bool(getattr(self.position, "trailing_armed", False)),  # ✅ WO-21: 실제 무장 여부 (이전 False 고정)
                        bars_held=bars_held,
                        checks=sell_checks,
                        triggered=True,
                        trigger_key=trigger_reason,
                        notes=f"🔴 SELL | {trigger_reason} | {cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}",
                        bar_time=bar_ts_kst.isoformat(),
                        is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
                    )

        except Exception as e:
            logger.warning(f"[AUDIT] 감사 로그 기록 실패: {e}")
