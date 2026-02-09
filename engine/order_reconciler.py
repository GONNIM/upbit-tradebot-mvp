import threading, time, logging
from typing import Dict, Optional, Any
import pyupbit
from services.db import (
    update_order_progress,
    update_order_completed,
    update_account_from_balances,
    update_position_from_balances,
    insert_trade_audit,  # ✅ LIVE 모드 체결 로그 추가
)


logger = logging.getLogger(__name__)


class OrderReconciler:
    def __init__(self, upbit: pyupbit.Upbit, *, poll_interval=2.0, balance_sync_interval=300.0):
        self.upbit = upbit
        self.poll_interval = poll_interval
        self.balance_sync_interval = balance_sync_interval  # ✅ 주기적 잔고 동기화 간격 (초, 기본 5분)
        self._pending: Dict[str, Dict[str, Any]] = {}  # uuid -> meta
        self._user_ids: set = set()  # ✅ 추적 중인 사용자 ID들 (잔고 동기화용)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._last_balance_sync = 0.0  # ✅ 마지막 잔고 동기화 시각 (time.time())

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
        - meta: interval, bar, reason, macd, signal, entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed
        """
        if not uuid:
            return
        with self._lock:
            self._pending[uuid] = {
                "user_id": user_id,
                "ticker": ticker,
                "side": side,
                "last": None,
                "meta": meta or {}  # ✅ 전략 컨텍스트 저장
            }
            self._user_ids.add(user_id)  # ✅ 잔고 동기화 대상 사용자 추가
        logger.info(f"[OR] enqueued: {uuid} side={side} {ticker}")

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
                        "meta": meta_dict  # ✅ 전략 컨텍스트 복구
                    }
                    self._user_ids.add(user_id)  # ✅ 잔고 동기화 대상 사용자 추가
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

            # ✅ 주기적 잔고 동기화 (5분마다)
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
            update_order_completed(
                user_id,
                uuid,
                final_state=state,
                executed_volume=exec_vol,
                avg_price=avg_px or None,
                paid_fee=fee or None,
            )
            logger.info(
                f"[OR] final {state} uuid={uuid} user={user_id} side={side} "
                f"vol={exec_vol} avg={avg_px} fee={fee}"
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

            balances = self.upbit.get_balances()
            update_account_from_balances(user_id, balances)
            update_position_from_balances(user_id, ticker, balances)
        except Exception as e:
            logger.error(f"[OR] finalize failed uuid={uuid}: {e}")

    def _periodic_balance_sync(self):
        """
        주기적 잔고 동기화 (기본 5분마다)
        - 주문 없이 외부 입출금 발생 시에도 자동 반영
        - LIVE 모드에서만 동작 (Upbit API 호출)
        """
        now = time.time()
        elapsed = now - self._last_balance_sync

        # ✅ 동기화 주기 체크
        if elapsed < self.balance_sync_interval:
            return

        # ✅ 추적 중인 사용자 ID 복사 (thread-safe)
        with self._lock:
            user_ids = list(self._user_ids)

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
                            update_position_from_balances(user_id, ticker, balances)

                    logger.info(f"[OR] periodic sync: user={user_id} updated")
                except Exception as e:
                    logger.error(f"[OR] periodic sync failed for user={user_id}: {e}")

            # ✅ 마지막 동기화 시각 갱신
            self._last_balance_sync = now
            logger.info(f"[OR] periodic sync completed: {len(user_ids)} user(s), interval={self.balance_sync_interval}s")

        except Exception as e:
            logger.error(f"[OR] periodic sync failed: {e}")
            # 실패해도 다음 주기에 재시도하도록 시각 갱신
            self._last_balance_sync = now
