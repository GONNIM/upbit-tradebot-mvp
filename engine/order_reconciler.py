import threading, time, logging
from typing import Dict, Optional, Any
import pyupbit


logger = logging.getLogger(__name__)


class OrderReconciler:
    def __init__(self, upbit: pyupbit.Upbit, *, poll_interval=2.0):
        self.upbit = upbit
        self.poll_interval = poll_interval
        self._pending: Dict[str, Dict[str, Any]] = {}  # uuid -> meta
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None

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

    def enqueue(self, uuid: str, *, user_id: str, ticker: str, side: str):
        if not uuid:
            return
        with self._lock:
            self._pending[uuid] = {"user_id": user_id, "ticker": ticker, "side": side, "last": None}
        logger.info(f"[OR] enqueued: {uuid} side={side} {ticker}")

    def load_inflight_from_db(self, fetch_func):
        """
        서버 재시작 등으로 유실된 pending 복구:
        fetch_func() -> [{'uuid':..., 'user_id':..., 'ticker':..., 'side':...}, ...]
        """
        rows = fetch_func() or []
        with self._lock:
            for r in rows:
                u = r.get("uuid")
                if u and u not in self._pending:
                    self._pending[u] = {"user_id": r["user_id"], "ticker": r["ticker"], "side": r["side"], "last": None}
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
                    info = self.upbit.get_order(uuid)
                    self._handle(uuid, info)
                except Exception as e:
                    logger.warning(f"[OR] get_order failed uuid={uuid}: {e}")
                time.sleep(self.poll_interval)  # rate limit 보호

            # 대기 (pending 없을 땐 좀 더 길게)
            if not uuids:
                time.sleep(1.0)

    def _handle(self, uuid: str, info: dict):
        """
        Upbit get_order 응답 예시:
        {
          "uuid": "...",
          "side": "bid"|"ask",
          "ord_type": "price"|"market"|"limit",
          "state": "wait"|"done"|"cancel",
          "price": "10000.0",
          "avg_price": "9988.0",
          "volume": "0.001",
          "executed_volume": "0.001",
          "paid_fee": "12.345",
          "trades": [
              {"price":"...","volume":"...","funds":"...","fee":"..."},
              ...
          ],
          ...
        }
        """
        if not info:
            return
        state = info.get("state")
        trades = info.get("trades") or []
        avg_price = float(info.get("avg_price") or 0.0)
        exec_volume = float(info.get("executed_volume") or 0.0)
        paid_fee = float(info.get("paid_fee") or 0.0)

        # 부분체결 누적 계산(Upbit가 avg_price/paid_fee를 제공하긴 함)
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

        # === 상태 반영 로직 ===
        if state in ("wait",):  # 대기/진행중(부분체결 포함)
            # 옵션: 부분체결 중간 스냅샷을 DB에 업데이트(체결수량/평단/수수료)
            self._update_order_progress(uuid, user_id, ticker, side, exec_volume, avg_price, paid_fee, state)
            return

        if state in ("done", "cancel"):  # 최종 상태
            self._finalize_order(uuid, user_id, ticker, side, exec_volume, avg_price, paid_fee, state)
            with self._lock:
                self._pending.pop(uuid, None)

    # === 아래 두 함수는 DB 연동 부분 ===
    def _update_order_progress(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
        try:
            # TODO: update_order_progress(uuid, exec_vol, avg_px, fee, state)
            pass
        except Exception as e:
            logger.warning(f"[OR] progress update failed uuid={uuid}: {e}")

    def _finalize_order(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
        try:
            # 1) 주문 레코드 상태 변경 + 체결결과 저장
            #    update_order_completed(uuid, avg_px, exec_vol, fee, state)

            # 2) 실거래 잔고/포지션 갱신 (가능하면 Upbit에서 최신 잔고 fetch)
            #    balances = self.upbit.get_balances()
            #    update_account_from_balances(user_id, balances)
            #    update_position_from_balances(user_id, ticker, balances)

            # 3) 감사 로그
            logger.info(f"[OR] final {state} uuid={uuid} side={side} vol={exec_vol} avg={avg_px} fee={fee}")
        except Exception as e:
            logger.error(f"[OR] finalize failed uuid={uuid}: {e}")
