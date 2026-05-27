import os
import pyupbit
import logging
import time as _time
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

# ✅ B11: LIVE BUY 재시도 정책 — 지수 백오프 1s/2s/4s
LIVE_BUY_MAX_RETRIES = 3
LIVE_BUY_BACKOFF_SECONDS = [1.0, 2.0, 4.0]

# ✅ B14: pyupbit HTTP 로거 — env 변수로 DEBUG 토글
#   기본: INFO (응답 형식/타입 기록)
#   디버깅 운영: PYUPBIT_HTTP_DEBUG=1 → DEBUG (요청/응답 본문 전체)
#   24~48시간 한정 운영용. 디스크/로그 부담 고려.
_pyupbit_http_logger = logging.getLogger("pyupbit.http")
if os.environ.get("PYUPBIT_HTTP_DEBUG", "").strip() in ("1", "true", "True", "yes"):
    _pyupbit_http_logger.setLevel(logging.DEBUG)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)
    logging.info("[BOOT] pyupbit.http logger=DEBUG (PYUPBIT_HTTP_DEBUG=1) — 디버깅 운영 모드")
else:
    _pyupbit_http_logger.setLevel(logging.INFO)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


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

        # 🔧 위험비율 적용 + 원 단위 내림
        krw_to_use = math.floor(avail * self.risk_pct)

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

        # 🟢 LIVE: KRW 금액 기준 시장가 매수, 수량/평단은 Reconciler가 나중에 확정.
        # ✅ B11/B14/B15: 재시도 + 지수 백오프 + 매 시도 직전 활성 KRW 재확인 + 응답 상세 로깅.
        res = None
        last_err: Optional[str] = None
        non_retriable = False

        for attempt in range(1, LIVE_BUY_MAX_RETRIES + 1):
            # ✅ B15: 매 시도 직전 활성 KRW 재확인 (사용자 동시 거래 대응)
            try:
                current_krw = self._krw_balance()
            except Exception as e:
                current_krw = krw_to_use  # 조회 실패 시 기존 값 유지
                logger.warning(f"[BUY-LIVE] attempt #{attempt} 활성 KRW 재조회 실패: {e}")

            if current_krw < krw_to_use:
                adjusted = math.floor(current_krw * self.risk_pct)
                if adjusted < 5000:
                    last_err = (
                        f"활성 KRW 부족: 현재={current_krw:.0f} 요청={krw_to_use:.0f} "
                        f"→ 조정={adjusted} (최소 5,000원 미만)"
                    )
                    logger.warning(
                        f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} 잔고 부족 중단 → {last_err}"
                    )
                    non_retriable = True
                    break
                logger.warning(
                    f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} 잔고 변동 감지 "
                    f"— krw_to_use {krw_to_use:.0f} → {adjusted:.0f}"
                )
                krw_to_use = adjusted

            try:
                res = self.upbit.buy_market_order(ticker, krw_to_use)
                # ✅ B14: type/repr 포함 상세 로깅
                logger.info(
                    f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} "
                    f"raw response type={type(res).__name__} repr={res!r}"
                )

                # 성공 케이스
                if isinstance(res, dict) and "uuid" in res and "error" not in res:
                    last_err = None
                    break

                # error 분기 — 비재시도 케이스 식별
                if isinstance(res, dict) and "error" in res:
                    err = res["error"]
                    err_msg = err.get("message") if isinstance(err, dict) else str(err)
                    last_err = f"Upbit error: {err_msg}"
                    err_low = str(err_msg or "").lower()
                    if (
                        "insufficient" in err_low
                        or "잔액" in str(err_msg)
                        or "잔고" in str(err_msg)
                        or "under_min_total" in err_low
                        or "invalid" in err_low
                    ):
                        logger.error(f"[BUY-LIVE] non-retriable error: {err_msg}")
                        non_retriable = True
                        break
                else:
                    last_err = f"invalid response (type={type(res).__name__} repr={res!r})"

                logger.warning(
                    f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} failed → {last_err}"
                )
            except Exception as e:
                last_err = f"exception: {e}"
                logger.warning(
                    f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} exception: {e}"
                )

            # 마지막 시도가 아니면 백오프 후 재시도
            if attempt < LIVE_BUY_MAX_RETRIES:
                _time.sleep(LIVE_BUY_BACKOFF_SECONDS[attempt - 1])

        # ✅ B12: 최종 실패 처리 — audit/orders/log 모두 기록
        success = (
            isinstance(res, dict)
            and "uuid" in res
            and "error" not in res
            and res.get("uuid")
        )
        if not success:
            err_summary = last_err or f"unknown (type={type(res).__name__} repr={res!r})"
            attempts_used = 1 if non_retriable else LIVE_BUY_MAX_RETRIES
            logger.error(
                f"[BUY-LIVE] FINAL FAILURE after attempts={attempts_used} | last_err={err_summary}"
            )
            insert_log(
                self.user_id,
                "ERROR",
                (
                    f"❌ Upbit 시장가 매수 실패 (attempts={attempts_used}, "
                    f"non_retriable={non_retriable}): {err_summary}"
                ),
            )
            # audit_trades에 실패도 명시 기록 (사용자 추적용)
            try:
                bal_after_krw = self._krw_balance()
            except Exception:
                bal_after_krw = None
            try:
                bal_after_coin = self._coin_balance(ticker)
            except Exception:
                bal_after_coin = None
            try:
                self._audit_trade(
                    side="BUY",
                    ticker=ticker,
                    price=price,
                    qty=None,
                    status_note=f"market buy(FAILED: {err_summary})",
                    ts=ts,
                    meta={**(meta or {}), "reason": "BUY_FAILED_API",
                          "last_err": err_summary, "attempts": attempts_used,
                          "non_retriable": non_retriable},
                    balances_before=(bal_after_krw, bal_after_coin),
                    balances_after=(bal_after_krw, bal_after_coin),
                    fee_ratio=MIN_FEE_RATIO,
                    risk_pct=self.risk_pct,
                )
            except Exception as e:
                logger.warning(f"[BUY-LIVE] _audit_trade(FAILED) 실패: {e}")
            # orders 테이블에 FAILED 상태로 기록
            try:
                _entry_bar = (meta or {}).get("bar") if meta else None
                insert_order(
                    self.user_id, ticker, "BUY",
                    price, 0.0, "FAILED",
                    state="FAILED",
                    requested_at=now_kst(),
                    entry_bar=_entry_bar,
                )
            except Exception as e:
                logger.warning(f"[BUY-LIVE] insert_order(FAILED) 실패: {e}")
            return {}

        # ✅ 성공 — 기존 흐름 진입
        try:
            uuid = res.get("uuid")
            
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
