import threading, time, logging
from typing import Dict, Optional, Any
import pyupbit
from services.db import (
    update_order_progress,
    update_order_completed,
    update_account_from_balances,
    update_position_from_balances,
    sync_all_positions_from_balances,  # ✅ Issue #18: 전체 포트폴리오 동기화
    insert_trade_audit,  # ✅ LIVE 모드 체결 로그 추가
)


logger = logging.getLogger(__name__)

# ✅ WO-10 (b) (2026-09-30): HTS 매수 감지 최소 금액 (업비트 최소 주문 금액과 같음).
#   이보다 작은 잔고 증가(소수점 잔량 변화 등)는 사람이 넣은 주문일 수 없다 → 감지하지 않는다.
#   (2026-09-11 id 990: Δ=9e-8개 가 HTS_BUY_ADD 로 기록되어 Trailing 리셋 경로 진입)
HTS_DETECT_MIN_KRW = 5000.0


class OrderReconciler:
    def __init__(self, upbit: pyupbit.Upbit, *, poll_interval=2.0, balance_sync_interval=60.0):
        self.upbit = upbit
        self.poll_interval = poll_interval
        self.balance_sync_interval = balance_sync_interval  # ✅ 주기적 잔고 동기화 간격 (초, 기본 1분) - Issue #17
        self._pending: Dict[str, Dict[str, Any]] = {}  # uuid -> meta
        # ✅ Policy P-1: LIVE 모드 사용자만 잔고 동기화. TEST 사용자는 등록 안 함.
        self._live_user_ids: set = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._last_balance_sync = 0.0  # ✅ 마지막 잔고 동기화 시각 (time.time())
        # ✅ SP-PI-2: LIMIT BUY 전량 체결 시 발화되는 콜백 — (user_id, ticker) → callable
        self._fill_callbacks: Dict[tuple, Any] = {}

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True, name="OrderReconciler")
        self._thr.start()
        logger.info("[OR] started")

    def stop(self, timeout: float = 3.0):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=timeout)
        logger.info("[OR] stopped")

    def enqueue(self, uuid: str, *, user_id: str, ticker: str, side: str, meta: Optional[Dict[str, Any]] = None):
        """
        주문 추적 큐에 추가 (체결 완료 시 audit_trades 기록용 meta 포함)
        실거래 주문은 LIVE에서만 발생하므로 _live_user_ids에 등록.

        ✅ enqueued_at 저장: 고정가 매수(LIMIT) 미체결 timeout 계산용.
        """
        if not uuid:
            return
        with self._lock:
            self._pending[uuid] = {
                "user_id": user_id,
                "ticker": ticker,
                "side": side,
                "last": None,
                "meta": meta or {},
                "enqueued_at": time.time(),  # ✅ LIMIT timeout 기준 시각
            }
            self._live_user_ids.add(user_id)  # 실거래 발생 = LIVE 사용자
        logger.info(f"[OR] enqueued: {uuid} side={side} {ticker}")

    def register_user(self, user_id: str, test_mode: bool = False):
        """
        ✅ Issue #17 Hotfix: HTS 매수 감지용 사용자 등록
        ✅ Policy P-1: TEST 모드 사용자는 등록 스킵 (지갑 조회 금지)
        """
        if test_mode:
            logger.info(f"[OR] TEST 모드 사용자 등록 스킵 (Policy P-1): {user_id}")
            return
        with self._lock:
            self._live_user_ids.add(user_id)
        logger.info(f"[OR] LIVE user registered for balance monitoring: {user_id}")

    def unregister_user(self, user_id: str):
        """엔진 정지 시 사용자 제거 (모드 변경 후 재시작에도 안전)."""
        with self._lock:
            self._live_user_ids.discard(user_id)
            # ✅ SP-PI-2: fill callback 도 함께 정리
            to_remove = [k for k in self._fill_callbacks.keys() if k[0] == user_id]
            for k in to_remove:
                self._fill_callbacks.pop(k, None)
            # ✅ [Phase 1-F/P2-2] hts-detect callback 도 함께 정리 (stale reference 방지)
            hts_cbs = getattr(self, "_hts_callbacks", None)
            if hts_cbs:
                to_remove_hts = [k for k in hts_cbs.keys() if k[0] == user_id]
                for k in to_remove_hts:
                    hts_cbs.pop(k, None)
        logger.info(f"[OR] user unregistered: {user_id}")

    def register_fill_callback(self, user_id: str, ticker: str, callback):
        """
        ✅ SP-PI-2: LIMIT BUY 전량 체결 시 발화되는 콜백 등록.

        callback signature:
            callback(uuid: str, executed_price: float, executed_qty: float, executed_ts: datetime)

        - (user_id, ticker) 조합당 하나만 유지 (중복 등록 시 덮어씀)
        - StrategyEngine._on_limit_fill 등록 예정
        - 호출은 OrderReconciler 스레드 컨텍스트 (콜백에서 락 사용 권장)
        """
        with self._lock:
            self._fill_callbacks[(user_id, ticker)] = callback
        logger.info(f"[OR] fill callback registered | user={user_id} ticker={ticker}")

    def register_hts_detect_callback(self, user_id: str, ticker: str, callback):
        """
        ✅ [Fix 4] HTS 매수 감지 시 발화되는 콜백 등록.

        callback signature:
            callback(avg_price: float, qty: float, reason: str)

        - reason: "HTS_BUY" (신규) 또는 "HTS_BUY_ADD" (추가 매수)
        - StrategyEngine._on_hts_detect 등록. position_state.avg_price 즉시 동기화용.
        - 2026-07-24 사건: Reconciler 가 DB 만 업데이트하고 position_state 는 그대로 → SL 미발동 근본 원인.
        """
        if not hasattr(self, "_hts_callbacks"):
            self._hts_callbacks: Dict[tuple, Any] = {}
        with self._lock:
            self._hts_callbacks[(user_id, ticker)] = callback
        logger.info(f"[OR] hts-detect callback registered | user={user_id} ticker={ticker}")

    def _fire_hts_detect_callback(self, user_id: str, ticker: str, avg_price: float, qty: float, reason: str):
        """[Fix 4] HTS 매수 감지 시 등록된 콜백 발화 (에러 격리)."""
        cbs = getattr(self, "_hts_callbacks", None)
        if not cbs:
            return
        with self._lock:
            cb = cbs.get((user_id, ticker))
        if cb is None:
            return
        try:
            cb(avg_price=float(avg_price), qty=float(qty), reason=str(reason))
            logger.info(f"[OR] hts-detect callback fired | user={user_id} ticker={ticker} reason={reason}")
        except Exception as _e:
            logger.error(f"[OR] hts-detect callback error | user={user_id} ticker={ticker}: {_e}")

    def _fire_fill_callback(self, user_id: str, ticker: str, uuid: str,
                            exec_price: float, exec_qty: float, exec_ts_iso):
        """FILLED BUY 감지 시 등록된 fill callback 발화 (에러 격리)."""
        with self._lock:
            cb = self._fill_callbacks.get((user_id, ticker))
        if cb is None:
            logger.debug(f"[OR] fill callback none | user={user_id} ticker={ticker} uuid={uuid}")
            return
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            if isinstance(exec_ts_iso, str) and exec_ts_iso:
                try:
                    exec_ts = datetime.fromisoformat(exec_ts_iso)
                    if exec_ts.tzinfo is None:
                        exec_ts = exec_ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))
                except Exception:
                    exec_ts = datetime.now(ZoneInfo("Asia/Seoul"))
            else:
                exec_ts = datetime.now(ZoneInfo("Asia/Seoul"))
            cb(uuid=uuid, executed_price=float(exec_price), executed_qty=float(exec_qty),
               executed_ts=exec_ts)
            logger.info(
                f"[OR] fill callback fired | user={user_id} ticker={ticker} uuid={uuid} "
                f"price={exec_price} qty={exec_qty} ts={exec_ts.isoformat()}"
            )
        except Exception as e:
            logger.error(f"[OR] fill callback 실행 실패 uuid={uuid}: {e}", exc_info=True)

    def load_inflight_from_db(self, fetch_func):
        rows = fetch_func() or []
        with self._lock:
            for r in rows:
                u = r.get("uuid")
                if u and u not in self._pending:
                    # ✅ meta 복구 (JSON 파싱)
                    meta_str = r.get("meta")
                    meta_dict = {}
                    if meta_str:
                        try:
                            import json
                            meta_dict = json.loads(meta_str)
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(f"[OR] meta parsing failed for uuid={u}: {e}")

                    user_id = r["user_id"]
                    self._pending[u] = {
                        "user_id": user_id,
                        "ticker": r["ticker"],
                        "side": r["side"],
                        "last": None,
                        "meta": meta_dict,  # ✅ 전략 컨텍스트 복구
                        "enqueued_at": time.time(),  # ✅ 복구 시점부터 timeout 시작(보수적 fallback)
                    }
                    # 미체결 주문이 있다는 것은 LIVE 거래 = LIVE 사용자
                    self._live_user_ids.add(user_id)
        logger.info(f"[OR] recovered pending: {len(rows)}")

    def _run(self):
        while not self._stop.is_set():
            uuids = []
            with self._lock:
                uuids = list(self._pending.keys())

            for uuid in uuids:
                if self._stop.is_set():
                    break
                try:
                    logger.debug(f"[OR] polling uuid={uuid}")
                    info = self.upbit.get_order(uuid)
                    logger.debug(f"[OR] get_order uuid={uuid} -> {type(info)} {info}")
                    self._handle(uuid, info)
                except Exception as e:
                    logger.warning(f"[OR] get_order failed uuid={uuid}: {e}")
                time.sleep(self.poll_interval)

            # ✅ 주기적 잔고 동기화 (1분마다) - Issue #17: HTS 매수 감지
            self._periodic_balance_sync()

            if not uuids:
                time.sleep(1.0)

    def _handle(self, uuid: str, info: dict):
        if not info:
            logger.warning(f"[OR] empty info from get_order uuid={uuid} → Upbit 응답 없음 또는 파싱 실패")
            return
        
        if isinstance(info, dict) and "error" in info:
            logger.error(f"[OR] Upbit error for uuid={uuid}: {info['error']}")
            # 필요하면 여기서 DB state를 'REJECTED' 등으로 박아도 됨
            return
    
        state = info.get("state") # 'wait', 'done', 'cancel'
        trades = info.get("trades") or []
        avg_price = float(info.get("avg_price") or 0.0)
        exec_volume = float(info.get("executed_volume") or 0.0)
        paid_fee = float(info.get("paid_fee") or 0.0)

        logger.debug(
            f"[OR] handle uuid={uuid} state={state} exec_vol={exec_volume} "
            f"avg={avg_price} fee={paid_fee}"
        )

        if (not avg_price or not exec_volume) and trades:
            total_funds = sum(float(t.get("funds") or 0.0) for t in trades)
            total_vol = sum(float(t.get("volume") or 0.0) for t in trades)
            avg_price = (total_funds / total_vol) if total_vol > 0 else 0.0
            paid_fee = sum(float(t.get("fee") or 0.0) for t in trades)
            exec_volume = total_vol

        with self._lock:
            meta = self._pending.get(uuid)

        if not meta:
            return

        user_id = meta["user_id"]
        ticker = meta["ticker"]
        side = meta["side"]

        # 🔹 진행 중 (부분체결 포함)
        if state in ("wait",):
            # exec_volume > 0이면 PARTIALLY_FILLED, 0이면 REQUESTED 유지
            db_state = "PARTIALLY_FILLED" if exec_volume > 0 else "REQUESTED"
            self._update_order_progress(
                uuid=uuid,
                user_id=user_id,
                ticker=ticker,
                side=side,
                exec_vol=exec_volume,
                avg_px=avg_price,
                fee=paid_fee,
                state=db_state
            )
            # ✅ 고정가 매수 timeout 체크 — 봉 간격 초과 미체결 자동 cancel
            self._maybe_cancel_fixed_price_buy(uuid)
            return

        # 🔹 최종 상태
        if state in ("done", "cancel"):
            if state == "done":
                db_state = "FILLED" if exec_volume > 0 else "CANCELED"
            else:  # 'cancel'
                db_state = "CANCELED"

            self._finalize_order(
                uuid=uuid,
                user_id=user_id,
                ticker=ticker,
                side=side,
                exec_vol=exec_volume,
                avg_px=avg_price,
                fee=paid_fee,
                state=db_state
            )

            # ✅ SP-PI-2: LIMIT BUY 전량 체결(FILLED) 감지 시 fill callback 발화
            # D6 결정: 부분 체결(CANCELED + exec_vol > 0)은 처리하지 않음. FILLED 만 대상.
            if db_state == "FILLED" and side == "BUY" and exec_volume > 0 and avg_price > 0:
                # 최종 체결 시각: trades 최상단(가장 최근) 또는 order created_at fallback
                exec_ts_iso = None
                if trades:
                    try:
                        exec_ts_iso = trades[-1].get("created_at") or trades[0].get("created_at")
                    except Exception:
                        exec_ts_iso = None
                if not exec_ts_iso:
                    exec_ts_iso = info.get("created_at")
                self._fire_fill_callback(
                    user_id=user_id, ticker=ticker, uuid=uuid,
                    exec_price=avg_price, exec_qty=exec_volume,
                    exec_ts_iso=exec_ts_iso,
                )

            with self._lock:
                self._pending.pop(uuid, None)

    def _update_order_progress(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
        """
        부분체결 진행 상황을 orders 테이블에 반영.
        - state: 'REQUESTED' | 'PARTIALLY_FILLED'
        """
        try:
            update_order_progress(
                user_id,
                uuid,
                executed_volume=exec_vol,
                avg_price=avg_px or None,
                paid_fee=fee or None,
                state=state
            )
            logger.info(
                f"[OR] progress uuid={uuid} user={user_id} side={side} "
                f"vol={exec_vol} avg={avg_px} fee={fee} state={state}"
            )
        except Exception as e:
            logger.warning(f"[OR] progress update failed uuid={uuid}: {e}")

    def _finalize_order(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
        """
        최종 체결/취소 결과를 orders 테이블에 반영.
        - state: 'FILLED' | 'CANCELED' | (필요 시 'REJECTED' 등 확장)
        """
        try:
            # ✅ 잔고 조회 (대시보드 표시용 current_krw, current_coin 저장)
            balances = self.upbit.get_balances()

            # ✅ KRW 잔고 추출
            current_krw = None
            for bal in balances:
                if bal.get("currency", "").upper() == "KRW":
                    current_krw = float(bal.get("balance", 0.0))
                    break

            # ✅ 해당 ticker의 코인 보유량 추출 (예: KRW-BTC → BTC)
            current_coin = None
            coin_currency = ticker.split("-")[-1].upper() if "-" in ticker else None
            if coin_currency:
                for bal in balances:
                    if bal.get("currency", "").upper() == coin_currency:
                        current_coin = float(bal.get("balance", 0.0))
                        break

            update_order_completed(
                user_id,
                uuid,
                final_state=state,
                executed_volume=exec_vol,
                avg_price=avg_px or None,
                paid_fee=fee or None,
                current_krw=current_krw,  # ✅ 체결 후 KRW 잔고
                current_coin=current_coin,  # ✅ 체결 후 코인 보유량
            )
            logger.info(
                f"[OR] final {state} uuid={uuid} user={user_id} side={side} "
                f"vol={exec_vol} avg={avg_px} fee={fee} krw={current_krw} coin={current_coin}"
            )

            # ✅ LIVE 모드 체결 로그 기록
            # FILLED 또는 CANCELED이지만 실제 체결량이 있는 경우 모두 기록
            # (Upbit API는 즉시 체결된 시장가 주문을 'cancel' 상태로 반환하기도 함)
            if exec_vol > 0:
                with self._lock:
                    meta = self._pending.get(uuid, {}).get("meta", {})

                try:
                    insert_trade_audit(
                        user_id=user_id,
                        ticker=ticker,
                        interval_sec=meta.get("interval", 60),
                        bar=meta.get("bar", 0),
                        kind=side,  # "BUY" or "SELL"
                        reason=meta.get("reason", f"{side}_LIVE"),
                        price=avg_px or 0.0,
                        macd=meta.get("macd"),
                        signal=meta.get("signal"),
                        entry_price=meta.get("entry_price"),
                        entry_bar=meta.get("entry_bar"),
                        bars_held=meta.get("bars_held"),
                        tp=meta.get("tp"),
                        sl=meta.get("sl"),
                        highest=meta.get("highest"),
                        ts_pct=meta.get("ts_pct"),
                        ts_armed=meta.get("ts_armed"),
                        timestamp=None,  # ✅ 실시간 체결 시각 (now_kst())
                        bar_time=meta.get("bar_time")  # ✅ 해당 봉의 시각 (전략 신호 발생 봉)
                    )
                    logger.info(f"[OR] audit_trades inserted: uuid={uuid} side={side} px={avg_px} vol={exec_vol}")
                except Exception as e:
                    logger.error(f"[OR] insert_trade_audit failed uuid={uuid}: {e}")

            update_account_from_balances(user_id, balances)
            update_position_from_balances(user_id, ticker, balances)
        except Exception as e:
            logger.error(f"[OR] finalize failed uuid={uuid}: {e}")

    def _maybe_cancel_fixed_price_buy(self, uuid: str):
        """
        고정가 매수(LIMIT) 미체결 자동 취소.

        - meta.is_fixed_price_buy=True 인 주문만 대상.
        - meta.interval_sec(기본 60s) 의 (interval_sec - 5)초 경과 시 cancel.
          → 다음 봉 시작 직전 타이밍에 미체결 정리.
        - cancel 후 polling 이 'cancel' 상태를 받아 _finalize_order 로 정상 처리.
        """
        with self._lock:
            info = self._pending.get(uuid)
        if not info:
            return

        meta = info.get("meta") or {}
        if not meta.get("is_fixed_price_buy"):
            return

        interval_sec = int(meta.get("interval_sec", 60) or 60)
        # 다음 봉 시작 직전 (최소 5초 보장)
        timeout_sec = max(5, interval_sec - 5)
        enqueued_at = float(info.get("enqueued_at") or time.time())
        elapsed = time.time() - enqueued_at

        if elapsed < timeout_sec:
            return

        ticker = info.get("ticker")
        user_id = info.get("user_id")
        logger.warning(
            f"⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도 | uuid={uuid} "
            f"elapsed={elapsed:.1f}s timeout={timeout_sec}s ticker={ticker}"
        )

        try:
            cancel_resp = self.upbit.cancel_order(uuid)
            logger.info(f"[OR] cancel_order resp uuid={uuid}: {cancel_resp}")
        except Exception as e:
            logger.error(f"[OR] cancel_order 실패 uuid={uuid}: {e}")
            return

        # ✅ WO-8 (2026-09-12): reason=force_buy 구분 표기
        _is_force = (meta.get("reason") == "force_buy")
        _title_prefix = "⏱ [FORCE] 강제 매수(현재가) 미체결 → 자동 취소" if _is_force else "⏱ 현재가 매수 미체결 → 자동 취소"
        _next_action = "→ 사용자 강제 매수 요청 취소됨. 필요 시 재발주" if _is_force else "→ 다음 봉 시그널에서 재평가"

        # 중요 알림: 미체결 취소 (v2 — 친화 표현)
        try:
            from services.notifier import send as _notify, LEVEL_WARNING
            _notify(
                LEVEL_WARNING,
                f"{_title_prefix} — {ticker}",
                (
                    f"주문가: {meta.get('limit_price', 'n/a')}\n"
                    f"경과: {elapsed:.1f}초 (봉 간격 도달)\n\n"
                    f"{_next_action}\n"
                    f"─────\n"
                    f"uuid: {uuid}"
                ),
                dedupe_key=f"fixed_buy_timeout:{uuid}",
                dedupe_ttl=60,
            )
        except Exception:
            pass

        # 사용자 로그
        try:
            from services.db import insert_log
            _log_prefix = "[FORCE] " if _is_force else ""
            insert_log(
                user_id,
                "INFO",
                f"⏱ {_log_prefix}현재가 매수 미체결 취소 ({ticker}): elapsed={elapsed:.1f}s uuid={uuid}",
            )
        except Exception:
            pass

    @staticmethod
    def _current_price(ticker: str) -> Optional[float]:
        """최근 체결가 (공개 시세). 실패 시 None."""
        try:
            p = pyupbit.get_current_price(ticker)
            return float(p) if p else None
        except Exception:
            return None

    def _hts_delta_krw(self, ticker: str, qty_delta: float, avg_buy_price: float):
        """
        ✅ WO-10 (b): HTS 감지 후보 증가량의 원화 환산값과 기준가 출처.

        기준가 순서: ① 업비트 잔고 응답 avg_buy_price → ② 현재가(최근 체결가) → ③ 없음.
        ③ 이면 (None, "unknown") — 호출부는 기존대로 감지한다 (실제 매수를 놓치지 않음).
        """
        if avg_buy_price and avg_buy_price > 0:
            return qty_delta * avg_buy_price, "avg_buy_price"
        cur = self._current_price(ticker)
        if cur and cur > 0:
            return qty_delta * cur, "current_price"
        return None, "unknown"

    def _has_pending_sell(self, user_id: str, ticker: str) -> bool:
        """봇 자신의 매도 주문이 추적 중인지 (봇 매도 체결 대기 중 묶임은 경고 대상 아님)."""
        with self._lock:
            return any(
                p.get("user_id") == user_id and p.get("ticker") == ticker
                and str(p.get("side", "")).upper() == "SELL"
                for p in self._pending.values()
            )

    def _check_locked_state(self, user_id: str, ticker: str, avail: float, locked: float) -> None:
        """
        ✅ WO-9 (b) (2026-09-30): 매도 불가 상태(가용 0 + 묶임 > 0) 전환 시 WARNING 1회.

        2026-09-30 KRW-JTO: 외부 지정가 매도 주문이 전량을 묶어 봇 매도가 거절될 상태였으나
        사용자에게 알릴 경로가 없었다. 판정·발주 로직은 건드리지 않는다 (알림·표시만).

        - 대상: 봇 엔진이 감시 중인 종목 (hts-detect 콜백 등록 종목)만 — 외부 전용 코인 소음 방지
        - 1회 보장: account_positions.meta.locked_warned (재시작 후에도 유지), 해제 시 삭제
        - 봇 자신의 매도 주문 체결 대기 중인 순간 묶임은 제외
        """
        try:
            cbs = getattr(self, "_hts_callbacks", None) or {}
            if (user_id, ticker) not in cbs:
                return
            from services.db import get_position_meta, update_position_meta
            meta = get_position_meta(user_id, ticker) or {}
            is_locked_only = avail <= 1e-12 and locked > 1e-12
            if is_locked_only:
                if meta.get("locked_warned"):
                    return
                if self._has_pending_sell(user_id, ticker):
                    return
                logger.warning(
                    f"⛔ [LOCKED-QTY] 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 | "
                    f"ticker={ticker} 가용={avail:.6f} 묶임={locked:.6f}"
                )
                try:
                    from services.notifier import send as _notify, LEVEL_WARNING
                    _notify(
                        LEVEL_WARNING,
                        f"⛔ 매도 불가 — {ticker} 앱 지정가 매도 주문으로 수량 묶임 ({locked:,.6f}개)",
                        (
                            f"묶임: {locked:,.6f}\n"
                            f"가용: {avail:,.6f}\n\n"
                            f"봇 매도 신호가 나도 거래소가 거절합니다.\n"
                            f"💡 업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요."
                        ),
                        dedupe_key=f"locked_qty:{ticker}",
                        dedupe_ttl=3600,
                    )
                except Exception:
                    pass
                meta["locked_warned"] = True
                update_position_meta(user_id, ticker, meta)
            elif meta.get("locked_warned") and avail > 1e-12:
                logger.info(
                    f"✅ [LOCKED-QTY] 묶임 해제 — 가용 회복 | ticker={ticker} "
                    f"가용={avail:.6f} 묶임={locked:.6f}"
                )
                meta.pop("locked_warned", None)
                update_position_meta(user_id, ticker, meta)
        except Exception as e:
            logger.warning(f"[LOCKED-QTY] 상태 점검 실패 (무시): {e}")

    def _periodic_balance_sync(self):
        """
        주기적 잔고 동기화 (기본 1분마다) - Issue #17
        - 주문 없이 외부 입출금 발생 시에도 자동 반영
        - HTS 매수 감지 (수량 0→양수 변화 시 hts_buy 플래그 설정 + audit_trades 기록)
        - LIVE 모드에서만 동작 (Upbit API 호출)
        """
        now = time.time()
        elapsed = now - self._last_balance_sync

        # ✅ 동기화 주기 체크
        if elapsed < self.balance_sync_interval:
            return

        # ✅ 추적 중인 사용자 ID 복사 (thread-safe)
        with self._lock:
            user_ids = list(self._live_user_ids)

        if not user_ids:
            # 추적 중인 사용자가 없으면 동기화 불필요
            self._last_balance_sync = now
            return

        try:
            # ✅ Upbit API 호출: 잔고 조회
            balances = self.upbit.get_balances()
            if not balances:
                logger.warning("[OR] periodic sync: get_balances() returned empty")
                return

            # ✅ 모든 추적 중인 사용자의 잔고/포지션 업데이트
            for user_id in user_ids:
                try:
                    update_account_from_balances(user_id, balances)

                    # 모든 코인 포지션 동기화 (balances에 있는 모든 ticker)
                    for bal in balances:
                        currency = bal.get("currency", "").upper()
                        if currency and currency != "KRW":
                            ticker = f"KRW-{currency}"

                            # ✅ Issue #17 + B3-잔여: HTS 매수 감지 (잔고 증가 일반화)
                            #   - prev_total == 0  → 신규 HTS 매수 (HTS_BUY)
                            #   - prev_total >  0  → 추가 HTS 매수 (HTS_BUY_ADD)
                            #   - 봇 BUY 직후 자연스러운 잔고 증가는 audit_trades 최근 30초 BUY 기록으로 식별 → 스킵
                            # ✅ WO-9 (c) (2026-09-30): 비교 기준을 가용 단독 → 가용+묶임 합계로 정정.
                            #   외부 미체결 매도 주문 취소는 묶임 → 가용 이동일 뿐 합계 불변 → 매수 아님.
                            #   (KRW-JTO audit_trades id=1158 오기록, HTS_BUY_ADD 오인 시 Trailing 리셋 유발)
                            from services.db import (
                                get_position_total_qty, mark_position_as_hts_buy,
                                has_recent_bot_buy_for_ticker,
                            )
                            prev_total = get_position_total_qty(user_id, ticker)
                            curr_qty = float(bal.get("balance", 0.0) or 0.0)       # 가용 (콜백 전달용, 의미 무변경)
                            curr_locked = float(bal.get("locked", 0.0) or 0.0)
                            curr_total = curr_qty + curr_locked
                            qty_delta = curr_total - prev_total

                            # 합계 증가 감지 (1e-8 임계 — float 노이즈 회피)
                            if qty_delta > 1e-8:
                                avg_buy_price = float(bal.get("avg_buy_price", 0.0))

                                # ✅ WO-10 (b): 증가량의 원화 환산이 최소 금액 미만이면 감지하지 않음
                                _delta_krw, _basis = self._hts_delta_krw(ticker, qty_delta, avg_buy_price)
                                if _delta_krw is not None and _delta_krw < HTS_DETECT_MIN_KRW:
                                    logger.debug(
                                        f"[HTS-DETECT] 최소 금액 미만 증가 → 감지 제외 | ticker={ticker} "
                                        f"Δ={qty_delta:.8f} ≈ {_delta_krw:,.2f} KRW (기준가={_basis}) "
                                        f"< {HTS_DETECT_MIN_KRW:,.0f}"
                                    )
                                # 봇 BUY 직후 자연 증가인지 식별
                                elif has_recent_bot_buy_for_ticker(user_id, ticker, within_seconds=30):
                                    logger.debug(
                                        f"[HTS-DETECT] 잔고 증가 감지되었으나 최근 봇 BUY 기록 존재 → "
                                        f"봇 BUY로 간주, HTS 마킹 스킵 | ticker={ticker} "
                                        f"prev_total={prev_total:.6f} curr_total={curr_total:.6f}"
                                    )
                                else:
                                    is_add = prev_total > 0
                                    reason_str = "HTS_BUY_ADD" if is_add else "HTS_BUY"
                                    logger.warning(
                                        f"🔔 [HTS-DETECT] {reason_str} 감지 | "
                                        f"ticker={ticker} | total(가용+묶임): {prev_total:.6f} → {curr_total:.6f} "
                                        f"(Δ={qty_delta:.6f}) | 가용={curr_qty:.6f} 묶임={curr_locked:.6f} "
                                        f"| avg_price={avg_buy_price}"
                                    )

                                    # HTS 매수 플래그 설정 (신규/추가 공통)
                                    mark_position_as_hts_buy(user_id, ticker)

                                    # audit_trades 감사 로그 기록
                                    insert_trade_audit(
                                        user_id=user_id,
                                        ticker=ticker,
                                        interval_sec=60,
                                        bar=0,
                                        kind="BUY",
                                        reason=reason_str,
                                        price=avg_buy_price if avg_buy_price > 0 else None,
                                        macd=None,
                                        signal=None,
                                        entry_price=avg_buy_price if avg_buy_price > 0 else None,
                                        entry_bar=None,
                                        bars_held=None,
                                        tp=None,
                                        sl=None,
                                        highest=None,
                                        ts_pct=None,
                                        ts_armed=None,
                                        timestamp=None,
                                        bar_time=None,
                                    )
                                    logger.info(
                                        f"✅ [HTS-DETECT] audit_trades 기록 완료 | "
                                        f"ticker={ticker} | reason={reason_str} | price={avg_buy_price}"
                                    )

                                    # ✅ [Fix 4] strategy_engine 에 즉시 통보 (position_state.avg_price 동기화)
                                    # 2026-07-24 사건: Reconciler 가 DB 만 업데이트하고 position_state 는 그대로
                                    # → sync_from_wallet 이 avg_price=None 유지 → SL 무력화
                                    if avg_buy_price > 0:
                                        self._fire_hts_detect_callback(
                                            user_id=user_id,
                                            ticker=ticker,
                                            avg_price=avg_buy_price,
                                            qty=curr_qty,
                                            reason=reason_str,
                                        )

                            # ✅ WO-9 (b): 봇 감시 종목이 "가용 0 + 묶임 > 0" 으로 바뀌면 WARNING 1회
                            #   (bal 에서 직접 읽음 — WO-9c 커밋의 지역 변수에 의존하지 않아 각 커밋 단독 revert 가능)
                            self._check_locked_state(
                                user_id, ticker,
                                float(bal.get("balance", 0.0) or 0.0),
                                float(bal.get("locked", 0.0) or 0.0),
                            )

                            update_position_from_balances(user_id, ticker, balances)

                    # ✅ Issue #18 Enhancement: 1분 주기 전체 포트폴리오 동기화 (HTS 매도 실시간 반영)
                    sync_all_positions_from_balances(user_id, balances)
                    logger.info(f"[OR] periodic sync: user={user_id} updated (full portfolio sync included)")
                except Exception as e:
                    logger.error(f"[OR] periodic sync failed for user={user_id}: {e}")

            # ✅ 마지막 동기화 시각 갱신
            self._last_balance_sync = now
            logger.info(f"[OR] periodic sync completed: {len(user_ids)} user(s), interval={self.balance_sync_interval:.0f}s (HTS 매수 감지 포함)")

        except Exception as e:
            logger.error(f"[OR] periodic sync failed: {e}")
            # 실패해도 다음 주기에 재시도하도록 시각 갱신
            self._last_balance_sync = now
