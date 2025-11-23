import pyupbit
import logging
from typing import Optional, Dict, Any, Tuple

from config import ACCESS, SECRET, MIN_FEE_RATIO
from services.db import (
    get_account,
    get_coin_balance,
    create_or_init_account,
    now_kst,
    update_account,
    update_coin_position,
    insert_account_history,
    insert_position_history,
    insert_order,  # ✅ 거래 기록 추가
    insert_trade_audit,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class UpbitTrader:
    """
    실거래 또는 테스트모드에서 가상거래를 수행하는 트레이더 클래스.
    - test_mode=True  : 모든 잔고/포지션/체결은 로컬 DB(accounts, account_positions, orders)에만 반영
    - test_mode=False : 실제 Upbit API 호출 + orders 테이블에는 '요청/체결상태'만 기록
                         (실제 체결 세부정보는 OrderReconciler가 채움)
    """

    def __init__(self, user_id: str, risk_pct: float = 0.1, test_mode: bool = True):
        self.user_id = user_id
        self.risk_pct = risk_pct
        self.test_mode = test_mode
        self.upbit = None if test_mode else pyupbit.Upbit(ACCESS, SECRET)

        if test_mode and get_account(user_id) is None:
            create_or_init_account(user_id)

    def _krw_balance(self) -> float:
        if self.test_mode:
            try:
                bal = get_account(self.user_id)
                return float(bal or 0.0)
            except Exception:
                return 0.0

        try:
            balance = self.upbit.get_balance(ticker="KRW")
            return float(balance) if balance else 0.0
        except Exception as e:
            logger.error(f"[실거래] KRW 잔고 조회 실패: {e}")
            return 0.0

    def _coin_balance(self, ticker: str) -> float:
        symbol = ticker.split("-")[-1].strip().upper() if ticker else ticker

        if self.test_mode:
            try:
                return float(get_coin_balance(self.user_id, symbol) or 0.0)
            except Exception:
                return 0.0

        try:
            for b in self.upbit.get_balances():
                if b.get("currency", "").upper() == symbol:
                    return float(b.get("balance", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"[실거래] 코인 잔고 조회 실패: {e}")
            return 0.0

    # ---------------------------
    # 공통 감사 헬퍼
    # ---------------------------
    def _audit_trade(
        self,
        *,
        side: str,
        ticker: str,
        price: Optional[float],
        qty: Optional[float],
        status_note: str,
        ts=None,
        meta: Optional[Dict[str, Any]] = None,
        balances_before: Tuple[Optional[float], Optional[float]] = (None, None),
        balances_after: Tuple[Optional[float], Optional[float]] = (None, None),
        fee_ratio: Optional[float] = None,
        risk_pct: Optional[float] = None,
    ):
        """
        insert_trade_audit 를 '풍부한 컨텍스트'로 호출하는 공통 헬퍼.
        - interval/bar/reason/macd/signal/entry_price/bars_held/tp/sl/highest/ts_* 는 meta 로 선택 적용
        - 금액, 수수료, 잔고, 위험비율 등 운영정보를 로그로 함께 기록
        """
        meta = meta or {}
        try:
            interval = meta.get("interval", "minute1")
            bar = meta.get("bar", 0)
            reason = meta.get("reason")
            macd = meta.get("macd")
            signal = meta.get("signal")
            entry_price = meta.get("entry_price")
            entry_bar = meta.get("entry_bar", 0)
            bars_held = meta.get("bars_held", 0)
            tp_price = meta.get("tp")
            sl_price = meta.get("sl")
            highest = meta.get("highest")
            ts_pct = meta.get("ts_pct")
            ts_armed = meta.get("ts_armed")

            krw_before, coin_before = balances_before
            krw_after, coin_after = balances_after
            px = price or 0.0
            q = qty or 0.0
            amount = q * px
            fee = amount * (fee_ratio or 0.0)

            # DB 감사 기록
            insert_trade_audit(
                self.user_id,
                ticker,
                interval,
                bar,
                side,
                (reason or status_note),
                px,
                macd,
                signal,
                entry_price,
                entry_bar,
                bars_held,
                tp_price,
                sl_price,
                highest,
                ts_pct,
                ts_armed,
            )

            # 운영 로그
            logger.info(
                f"[AUDIT] {side} | px={px} qty={q} amt={amount} fee={fee} risk_pct={risk_pct} "
                f"| krw {krw_before}->{krw_after} coin {coin_before}->{coin_after} "
                f"| note={status_note} meta={meta}"
            )
        except Exception as e:
            logger.error(f"[AUDIT] insert_trade_audit failed: {e} | side={side} meta={meta}")

    # ---------------------------
    # 매수 / 매도
    # ---------------------------
    def buy_market(self, price: float, ticker: str, ts=None, meta: Optional[Dict[str, Any]] = None) -> dict:
        """
        시장가 매수
        - TEST 모드: 즉시 체결 + DB에 completed 기록
        - LIVE 모드 : Upbit에 KRW 금액 기준 시장가 주문 → orders에는 'REQUESTED' + uuid만 기록
                      실제 체결 결과는 OrderReconciler가 update_order_*()로 업데이트
        """
        krw_to_use = self._krw_balance() * self.risk_pct
        if krw_to_use <= 0:
            logger.warning(f"[BUY] 주문 불가: krw_to_use={krw_to_use:.4f}")
            return {}
        
        if not self.test_mode and krw_to_use < 5000:
            logger.warning(f"[BUY] 실거래 최소 주문금액 미만: {krw_to_use:.2f} KRW")
            return {}
        
        qty = round(krw_to_use / (price * (1 + MIN_FEE_RATIO)), 8)
        logger.info(f"[BUY] plan krw_to_use={krw_to_use:.4f} price={price:.8f} fee={MIN_FEE_RATIO} -> qty={qty}")

        if self.test_mode:
            current_krw = self._krw_balance()
            current_coin = self._coin_balance(ticker)

            self._simulate_buy(ticker, qty, price, current_krw, current_coin)

            raw_total = qty * price * (1 + MIN_FEE_RATIO)
            new_krw = max(current_krw - raw_total, 0.0)
            new_coin = current_coin + qty

            insert_order(
                self.user_id,
                ticker,
                "BUY",
                price,
                qty,
                "completed",
                current_krw=new_krw,
                current_coin=new_coin,
                profit_krw=0,
            )

            self._audit_trade(
                side="BUY",
                ticker=ticker,
                price=price,
                qty=qty,
                status_note="market buy(test_mode)",
                ts=ts,
                meta=(meta or {}),
                balances_before=(current_krw, current_coin),
                balances_after=(new_krw, new_coin),
                fee_ratio=MIN_FEE_RATIO,
                risk_pct=self.risk_pct,
            )

            return {"time": ts, "side": "BUY", "qty": qty, "price": price, "used_krw": krw_to_use}

        try:
            # 🟢 LIVE: KRW 금액 기준 시장가 매수, 수량/평단은 Reconciler가 나중에 확정
            res = self.upbit.buy_market_order(ticker, krw_to_use)
            uuid = (res or {}).get("uuid")

            insert_order(
                self.user_id, 
                ticker, 
                "BUY", 
                price, 
                0, 
                "requested", 
                provider_uuid=uuid, 
                state="REQUESTED", 
                requested_at=now_kst()
            )
            
            self._audit_trade(
                side="BUY",
                ticker=ticker,
                price=price,
                qty=None,
                status_note="market buy(live-req)",
                ts=ts,
                meta=(meta or {}),
                balances_before=(self._krw_balance(), self._coin_balance(ticker)),
                balances_after=(None, None),
                fee_ratio=MIN_FEE_RATIO,
                risk_pct=self.risk_pct,
            )

            return {
                "time": ts,
                "side": "BUY",
                "qty": 0.0,
                "price": float(price),
                "uuid": uuid,
                "raw": res
            }
        except Exception as e:
            logger.error(f"[실거래] 매수 주문 실패: {e}")
            return {}

    def sell_market(self, qty: float, ticker: str, price: float, ts=None, meta: Optional[Dict[str, Any]] = None) -> dict:
        """
        시장가 매도
        - TEST: 즉시 체결
        - LIVE: Upbit에 수량 기준 시장가 주문 → orders에는 'REQUESTED' + uuid 기록
                실제 체결 결과(최종 수량/평단/수수료)는 OrderReconciler가 update_order_*()로 채움
        """
        if qty <= 0:
            logger.warning("[SELL] 수량이 0 이하입니다. 매도 생략")
            return {}
        
        logger.info(f"[SELL] plan qty={qty} price={price:.8f} fee={MIN_FEE_RATIO}")

        if self.test_mode:
            current_krw = self._krw_balance()
            current_coin = self._coin_balance(ticker)

            self._simulate_sell(ticker, qty, price, current_krw, current_coin)

            raw_gain = qty * price
            fee = raw_gain * MIN_FEE_RATIO
            total_gain = raw_gain - fee

            new_krw = current_krw + total_gain
            new_coin = max(current_coin - qty, 0.0)

            insert_order(
                self.user_id,
                ticker,
                "SELL",
                price,
                qty,
                "completed",
                current_krw=new_krw,
                current_coin=new_coin,
                profit_krw=total_gain,
            )

            self._audit_trade(
                side="SELL",
                ticker=ticker,
                price=price,
                qty=qty,
                status_note="market sell(test_mode)",
                ts=ts,
                meta=(meta or {}),
                balances_before=(current_krw, current_coin),
                balances_after=(new_krw, new_coin),
                fee_ratio=MIN_FEE_RATIO,
                risk_pct=self.risk_pct,
            )

            return {"time": ts, "side": "SELL", "qty": qty, "price": price}

        try:
            # 🟢 LIVE: 수량 기준 시장가 매도, 실제 avg_price/fee는 Reconciler에서
            res = self.upbit.sell_market_order(ticker, qty)
            uuid = (res or {}).get("uuid")

            insert_order(
                self.user_id, 
                ticker, 
                "SELL", 
                price, 
                qty, 
                "requested", 
                provider_uuid=uuid,
                state="REQUESTED",
                requested_at=now_kst()
            )

            self._audit_trade(
                side="SELL",
                ticker=ticker,
                price=price,
                qty=qty,
                status_note="market sell(live-req)",
                ts=ts,
                meta=(meta or {}),
                balances_before=(self._krw_balance(), self._coin_balance(ticker)),
                balances_after=(None, None),
                fee_ratio=MIN_FEE_RATIO,
                risk_pct=self.risk_pct,
            )

            return {
                "time": ts,
                "side": "SELL",
                "qty": float(qty),
                "price": float(price),
                "uuid": uuid,
                "raw": res
            }
        except Exception as e:
            logger.error(f"[실거래] 매도 주문 실패: {e}")
            return {}

    def _simulate_buy(
        self,
        ticker: str,
        qty: float,
        price: float,
        current_krw: float,
        current_coin: float,
    ):
        amount = qty * price
        fee = amount * MIN_FEE_RATIO
        total_spent = amount + fee

        new_krw = max(current_krw - total_spent, 0.0)
        new_coin = current_coin + qty

        update_account(self.user_id, new_krw)
        update_coin_position(self.user_id, ticker, new_coin)

        insert_account_history(self.user_id, new_krw)
        insert_position_history(self.user_id, ticker, new_coin)

    def _simulate_sell(
        self,
        ticker: str,
        qty: float,
        price: float,
        current_krw: float,
        current_coin: float,
    ):
        amount = qty * price
        fee = amount * MIN_FEE_RATIO
        total_gain = amount - fee

        new_krw = current_krw + total_gain
        new_coin = max(current_coin - qty, 0.0)

        update_account(self.user_id, new_krw)
        update_coin_position(self.user_id, ticker, new_coin)

        insert_account_history(self.user_id, new_krw)
        insert_position_history(self.user_id, ticker, new_coin)
