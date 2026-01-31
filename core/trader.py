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
    insert_log,
)

import math


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
        """
        주어진 ticker(예: 'KRW-PEPE' 또는 'PEPE')에 대한 코인 잔고 반환.
        - LIVE  : Upbit API get_balances()에서 currency=심볼 기준으로 조회
        - TEST  : DB(account_positions 등)에 저장된 ticker 그대로 조회
        """
        # 심볼은 LIVE용 (Upbit get_balances()에서 currency 필드와 매칭)
        symbol = ticker.split("-")[-1].strip().upper() if ticker else ticker

        if self.test_mode:
            try:
                # ✅ TEST 모드는 DB에 'KRW-PEPE' 같은 market 문자열로 저장하므로
                # symbol(PEPE)이 아니라 ticker 그대로 조회해야 한다.
                return float(get_coin_balance(self.user_id, ticker) or 0.0)
            except Exception:
                return 0.0

        try:
            # LIVE 모드에서는 free + locked 합계를 '보유량'으로 인식
            for b in self.upbit.get_balances():
                if b.get("currency", "").upper() == symbol:
                    free_bal = float(b.get("balance", 0.0) or 0.0)
                    locked_bal = float(b.get("locked", 0.0) or 0.0)
                    return free_bal + locked_bal
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
            interval = meta.get("interval", 60)  # ✅ 기본값을 숫자로 (60초 = 1분봉)
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
                timestamp=None,  # ✅ 실시간 체결 시각 (now_kst() 자동)
                bar_time=meta.get("bar_time")  # ✅ 해당 봉의 시각
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
        avail = self._krw_balance()
        if avail <= 0:
            logger.warning(f"[BUY] 주문 불가: 잔고={avail:.4f}")
            return {}

        # 🔧 위험비율 적용 + 2% 안전마진 + 원 단위 내림
        krw_to_use = math.floor(avail * self.risk_pct * 0.98)

        if krw_to_use < 5000:
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

            # ✅ meta에서 entry_bar 추출
            entry_bar = (meta or {}).get("bar") if meta else None

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
                entry_bar=entry_bar,  # ✅ bars_held 추적용
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

            return {
                "time": ts,
                "side": "BUY",
                "qty": qty,
                "price": price,
                "used_krw": krw_to_use,
            }

        try:
            # 🟢 LIVE: KRW 금액 기준 시장가 매수, 수량/평단은 Reconciler가 나중에 확정
            res = self.upbit.buy_market_order(ticker, krw_to_use)
            logger.info(f"[BUY-LIVE] raw response: {res}")

            if not res or not isinstance(res, dict):
                msg = f"[BUY-LIVE] invalid response from Upbit (res={res})"
                logger.error(msg)
                insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매수 응답 비정상: {res}")
                return {}

            if "error" in res:
                err = res["error"]
                err_msg = err.get("message") if isinstance(err, dict) else str(err)
                logger.error(f"[BUY-LIVE] Upbit error response: {err}")
                insert_log(
                    self.user_id,
                    "ERROR",
                    f"❌ 업비트 시장가 매수 실패: {err_msg}",
                )
                return {}
        
            uuid = (res or {}).get("uuid")
            if not uuid:
                msg = f"[BUY-LIVE] no uuid in response: {res}"
                logger.error(msg)
                insert_log(
                    self.user_id,
                    "ERROR",
                    "❌ 업비트 시장가 매수 응답에 uuid 없음 → 주문 추적 불가",
                )
                return {}
            
            # ✅ meta에서 entry_bar 추출
            entry_bar = (meta or {}).get("bar") if meta else None

            # ✅ meta를 JSON 문자열로 변환
            import json
            meta_json = json.dumps(meta) if meta else None

            insert_order(
                self.user_id,
                ticker,
                "BUY",
                price,
                0,
                "requested",
                provider_uuid=uuid,
                state="REQUESTED",
                requested_at=now_kst(),
                entry_bar=entry_bar,  # ✅ bars_held 추적용
                meta=meta_json,  # ✅ 전략 컨텍스트 저장
            )

            # ❌ LIVE 모드에서는 reconciler가 체결 후 audit 기록 담당
            # (중복 방지: trader 요청 시 + reconciler 체결 시 = 2번 기록 문제 해결)
            # self._audit_trade(
            #     side="BUY",
            #     ticker=ticker,
            #     price=price,
            #     qty=None,
            #     status_note="market buy(live-req)",
            #     ts=ts,
            #     meta=(meta or {}),
            #     balances_before=(self._krw_balance(), self._coin_balance(ticker)),
            #     balances_after=(None, None),
            #     fee_ratio=MIN_FEE_RATIO,
            #     risk_pct=self.risk_pct,
            # )

            insert_log(
                self.user_id,
                "INFO",
                (
                    f"🚨 [LIVE] 시장가 매수 요청 전송: {ticker} "
                    f"(예상가≈{price:,.2f} KRW, 사용 KRW ≈ {krw_to_use:,.0f}, uuid={uuid})"
                ),
            )

            # ✅ OrderReconciler에 추적 등록
            try:
                from engine.reconciler_singleton import get_reconciler
                get_reconciler().enqueue(uuid, user_id=self.user_id, ticker=ticker, side="BUY", meta=meta)
            except Exception as e:
                logger.error(f"⚠️ reconciler enqueue 실패: {e}")

            return {
                "time": ts,
                "side": "BUY",
                "qty": 0.0,
                "price": float(price),
                "uuid": uuid,
                "raw": res,
                "used_krw": float(krw_to_use),
            }
        except Exception as e:
            logger.error(f"[실거래] 매수 주문 실패: {e}")
            insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매수 예외: {e}")
            return {}

    def sell_market(self, qty: float, ticker: str, price: float, ts=None, meta: Optional[Dict[str, Any]] = None) -> dict:
        """
        시장가 매도
        - TEST: 즉시 체결
        - LIVE: Upbit에 수량 기준 시장가 주문 → orders에는 'REQUESTED' + uuid 기록
                실제 체결 결과(최종 수량/평단/수수료)는 OrderReconciler가 update_order_*()로 채움
        """
        # 🔧 FIX: position.qty가 0일 때 실제 지갑 잔고 확인
        if qty <= 0:
            actual_balance = self._coin_balance(ticker)
            if actual_balance > 0:
                logger.warning(
                    f"[SELL] ⚠️ position.qty={qty} but wallet has {actual_balance:.6f} {ticker} "
                    f"- using actual wallet balance to recover position sync"
                )
                qty = actual_balance
            else:
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

            return {
                "time": ts,
                "side": "SELL",
                "qty": qty,
                "price": price,
            }

        try:
            # 🟢 LIVE: 수량 기준 시장가 매도, 실제 avg_price/fee는 Reconciler에서
            res = self.upbit.sell_market_order(ticker, qty)
            logger.info(f"[SELL-LIVE] raw response: {res}") 

            if not res or not isinstance(res, dict):
                msg = f"[SELL-LIVE] invalid response from Upbit (res={res})"
                logger.error(msg)
                insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매도 응답 비정상: {res}")
                return {}
            
            if "error" in res:
                err = res["error"]
                err_msg = err.get("message") if isinstance(err, dict) else str(err)
                logger.error(f"[SELL-LIVE] Upbit error response: {err}")
                insert_log(
                    self.user_id,
                    "ERROR",
                    f"❌ 업비트 시장가 매도 실패: {err_msg}",
                )
                return {}
            
            uuid = (res or {}).get("uuid")
            if not uuid:
                msg = f"[SELL-LIVE] no uuid in response: {res}"
                logger.error(msg)
                insert_log(
                    self.user_id,
                    "ERROR",
                    "❌ 업비트 시장가 매도 응답에 uuid 없음 → 주문 추적 불가",
                )
                return {}


            # ✅ meta를 JSON 문자열로 변환
            import json
            meta_json = json.dumps(meta) if meta else None

            insert_order(
                self.user_id,
                ticker,
                "SELL",
                price,
                qty,
                "requested",
                provider_uuid=uuid,
                state="REQUESTED",
                requested_at=now_kst(),
                meta=meta_json,  # ✅ 전략 컨텍스트 저장
            )

            # ❌ LIVE 모드에서는 reconciler가 체결 후 audit 기록 담당
            # (중복 방지: trader 요청 시 + reconciler 체결 시 = 2번 기록 문제 해결)
            # self._audit_trade(
            #     side="SELL",
            #     ticker=ticker,
            #     price=price,
            #     qty=qty,
            #     status_note="market sell(live-req)",
            #     ts=ts,
            #     meta=(meta or {}),
            #     balances_before=(self._krw_balance(), self._coin_balance(ticker)),
            #     balances_after=(None, None),
            #     fee_ratio=MIN_FEE_RATIO,
            #     risk_pct=self.risk_pct,
            # )

            insert_log(
                self.user_id,
                "INFO",
                (
                    f"🚨 [LIVE] 시장가 매도 요청 전송: {ticker} "
                    f"(예상가≈{price:,.2f} KRW, 수량≈{qty:.6f}, uuid={uuid})"
                ),
            )

            # ✅ OrderReconciler에 추적 등록
            try:
                from engine.reconciler_singleton import get_reconciler
                get_reconciler().enqueue(uuid, user_id=self.user_id, ticker=ticker, side="SELL", meta=meta)
            except Exception as e:
                logger.error(f"⚠️ reconciler enqueue 실패: {e}")

            return {
                "time": ts,
                "side": "SELL",
                "qty": float(qty),
                "price": float(price),
                "uuid": uuid,
                "raw": res,
            }
        except Exception as e:
            logger.error(f"[실거래] 매도 주문 실패: {e}")
            insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매도 예외: {e}")
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
