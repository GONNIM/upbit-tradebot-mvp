import os
import json as _json
import hashlib as _hashlib
import uuid as _uuid
from urllib.parse import urlencode as _urlencode, unquote as _unquote

import jwt as _jwt
import pyupbit
import requests as _requests
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


# ---------------------------------------------------------------------------
# Upbit 주문 직접 호출 helper
#   pyupbit `buy_market_order`/`sell_market_order`는 모든 예외를 try/except로
#   삼키고 stdout으로 클래스명만 print한 뒤 None을 반환한다(swallow). 그 결과
#   `insufficient_funds_bid` 같은 명확한 400 에러조차 호출자가 받아볼 수 없다.
#   본 helper는 동일한 REST 엔드포인트를 직접 호출하여 HTTP status·body·에러
#   name/message·네트워크 예외까지 모두 로깅·반환한다. API 키/JWT는 절대 로깅
#   하지 않는다.
# ---------------------------------------------------------------------------

_UPBIT_ORDERS_URL = "https://api.upbit.com/v1/orders"
_UPBIT_HTTP_TIMEOUT = 10  # seconds

# Upbit 400 에러 중 재시도해도 의미 없는 사유들 (pyupbit/errors.py 기준)
_NON_RETRIABLE_BUY_ERRORS = frozenset({
    "insufficient_funds_bid",      # 잔고 부족
    "under_min_total_bid",         # 최소 주문금액 미만
    "over_max_total_price_bid",    # 최대 주문금액(10억) 초과
    "create_bid_error",            # 주문 요청 정보 오류
    "validation_error",            # 잘못된 API 요청
    "invalid_query_payload",       # JWT 페이로드 오류
    "jwt_verification",            # JWT 검증 실패
    "expired_access_key",          # API 키 만료
    "no_authorization_i_p",        # 허용 안 된 IP
    "out_of_scope",                # 허용 안 된 기능
    "invalid_access_key",          # 잘못된 액세스 키
    "thirdparty_agreement_required",  # 신규 코인 별도 동의 필요
})
_NON_RETRIABLE_SELL_ERRORS = frozenset({
    "insufficient_funds_ask",
    "under_min_total_ask",
    "create_ask_error",
    "validation_error",
    "invalid_query_payload",
    "jwt_verification",
    "expired_access_key",
    "no_authorization_i_p",
    "out_of_scope",
    "invalid_access_key",
    "thirdparty_agreement_required",
})


def _build_auth_headers(payload: Dict[str, Any]) -> Dict[str, str]:
    query = _unquote(_urlencode(payload, doseq=True))
    query_hash = _hashlib.sha512(query.encode("utf-8")).hexdigest()
    token = _jwt.encode(
        {
            "access_key": ACCESS,
            "nonce": str(_uuid.uuid4()),
            "query_hash": query_hash,
            "query_hash_alg": "SHA512",
        },
        SECRET,
    )
    return {"Authorization": f"Bearer {token}"}


def _call_upbit_order(side: str, market: str, **payload: Any) -> Dict[str, Any]:
    """
    Upbit POST /v1/orders 직접 호출.
    Returns dict:
      ok: bool                — 2xx + uuid 포함이면 True
      status: int | None      — HTTP status, 네트워크 예외 시 None
      body: dict | str | None — 응답 본문(가능하면 dict, 아니면 raw text)
      error_name: str | None  — Upbit 에러 name (예: insufficient_funds_bid)
      error_message: str|None — Upbit 에러 message
      exception: str | None   — 네트워크/파싱 예외 발생 시 클래스명+메시지
      data: dict | None       — 성공 시 주문 정보 (uuid 포함)
    """
    data = {"market": market, "side": side, **payload}
    headers = _build_auth_headers(data)

    # 요청 로그(JWT 제외)
    logger.info(f"[UPBIT-ORDER] → POST /v1/orders payload={data}")

    try:
        resp = _requests.post(
            _UPBIT_ORDERS_URL, json=data, headers=headers, timeout=_UPBIT_HTTP_TIMEOUT
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        logger.error(f"[UPBIT-ORDER] ← network/raise exception: {msg}")
        return {
            "ok": False,
            "status": None,
            "body": None,
            "error_name": "network_exception",
            "error_message": msg,
            "exception": msg,
            "data": None,
        }

    status = resp.status_code
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text

    logger.info(f"[UPBIT-ORDER] ← status={status} body={body!r}")

    error_name = None
    error_message = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            error_name = err.get("name")
            error_message = err.get("message")

    success = (
        200 <= status < 300
        and isinstance(body, dict)
        and "error" not in body
        and bool(body.get("uuid"))
    )

    return {
        "ok": success,
        "status": status,
        "body": body,
        "error_name": error_name,
        "error_message": error_message,
        "exception": None,
        "data": body if success else None,
    }


def _upbit_buy_market(market: str, krw: int) -> Dict[str, Any]:
    """시장가 매수(KRW 금액 기준). ord_type=price."""
    return _call_upbit_order("bid", market, price=str(krw), ord_type="price")


def _upbit_sell_market(market: str, volume: float) -> Dict[str, Any]:
    """시장가 매도(수량 기준). ord_type=market."""
    return _call_upbit_order("ask", market, volume=str(volume), ord_type="market")


def _upbit_buy_limit(market: str, price: float, volume: float) -> Dict[str, Any]:
    """지정가 매수. ord_type=limit, price + volume 모두 필요."""
    return _call_upbit_order(
        "bid", market, price=str(price), volume=str(volume), ord_type="limit"
    )


def _round_price_to_tick(price: float) -> float:
    """
    Upbit KRW 마켓 호가 단위에 맞춰 가장 가까운 tick으로 라운딩.
    pyupbit.get_tick_size(method="round") 사용. 봉 종가가 부동소수점 잔여
    오차로 invalid_price 거부되는 경우를 사전 차단한다.
    """
    return pyupbit.get_tick_size(price, method="round")


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
        # 마지막 LIVE 주문 실패의 정확한 사유(B안) — UI 노출용
        self.last_buy_error: Optional[str] = None
        self.last_sell_error: Optional[str] = None

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

        # 🔧 위험비율 적용 + 원 단위 내림 (수수료 차감 후에도 잔고 부족이 안 되도록
        #    매수 수수료(MIN_FEE_RATIO)만큼 미리 깎는다 — risk_pct=1.0 전액 매수에서
        #    Upbit `insufficient_funds_bid` 거부 방지)
        krw_to_use = math.floor(avail * self.risk_pct / (1 + MIN_FEE_RATIO))

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
                # 수수료 차감 후에도 안전한 금액으로 재조정 (A안과 동일 공식)
                adjusted = math.floor(current_krw * self.risk_pct / (1 + MIN_FEE_RATIO))
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

            # B안: pyupbit swallow 우회 — 직접 호출 helper 사용
            call = _upbit_buy_market(ticker, krw_to_use)
            logger.info(
                f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} "
                f"ok={call['ok']} status={call['status']} "
                f"error_name={call['error_name']} error_message={call['error_message']}"
            )

            if call["ok"]:
                res = call["data"]
                last_err = None
                break

            # 명시적 사유로 last_err 채우기
            if call["error_name"]:
                last_err = (
                    f"Upbit error [{call['error_name']}]: {call['error_message']}"
                )
                if call["error_name"] in _NON_RETRIABLE_BUY_ERRORS:
                    logger.error(
                        f"[BUY-LIVE] non-retriable error: {call['error_name']}"
                    )
                    non_retriable = True
                    break
            elif call["exception"]:
                last_err = f"exception: {call['exception']}"
            else:
                last_err = (
                    f"invalid response (status={call['status']} "
                    f"body={call['body']!r})"
                )

            logger.warning(
                f"[BUY-LIVE] attempt #{attempt}/{LIVE_BUY_MAX_RETRIES} failed → {last_err}"
            )

            # 마지막 시도가 아니면 백오프 후 재시도
            if attempt < LIVE_BUY_MAX_RETRIES:
                _time.sleep(LIVE_BUY_BACKOFF_SECONDS[attempt - 1])

        # ✅ B12: 최종 실패 처리 — audit/orders/log 모두 기록
        success = isinstance(res, dict) and bool(res.get("uuid"))
        if not success:
            err_summary = last_err or f"unknown (type={type(res).__name__} repr={res!r})"
            attempts_used = 1 if non_retriable else LIVE_BUY_MAX_RETRIES
            self.last_buy_error = err_summary  # UI 노출용 (trading_control이 읽음)
            logger.error(
                f"[BUY-LIVE] FINAL FAILURE after attempts={attempts_used} | last_err={err_summary}"
            )
            # Critical #3 + #6 알림: 매수 실패 + API 인증 실패 분리 (v2 — 한국어 라벨)
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                from services.error_messages import format_error_block
                _label, _raw = format_error_block(err_summary)
                _notify(
                    LEVEL_CRITICAL,
                    f"❌ 매수 실패 — {ticker}",
                    (
                        f"사유: {_label}\n"
                        f"재시도: {attempts_used}회 모두 실패\n\n"
                        f"💡 KRW 잔고 또는 risk_pct 점검\n"
                        f"─────\n"
                        f"err: {_raw}"
                    ),
                    dedupe_key=f"buy_fail:{ticker}:{err_summary}",
                    dedupe_ttl=60,
                )
                _low = (err_summary or "").lower()
                if any(k in _low for k in (
                    "jwt_verification", "expired_access_key",
                    "no_authorization_i_p", "invalid_access_key",
                    "invalid_query_payload",
                )):
                    _notify(
                        LEVEL_CRITICAL,
                        "🔑 Upbit API 인증 실패",
                        (
                            f"사유: {_label}\n\n"
                            f"💡 즉시 확인:\n"
                            f"  1. Upbit 콘솔 → API 키 만료일\n"
                            f"  2. 서버 IP 화이트리스트\n"
                            f"  3. .env 의 UPBIT_ACCESS / UPBIT_SECRET\n"
                            f"─────\n"
                            f"err: {_raw}"
                        ),
                        dedupe_key=f"api_auth:{err_summary}",
                        dedupe_ttl=600,
                    )
            except Exception:
                pass
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
        self.last_buy_error = None
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

            # Critical #1 알림: LIVE BUY 요청 전송 성공 (v2 — 친화 표현)
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                _notify(
                    LEVEL_CRITICAL,
                    f"🟢 매수 요청 — {ticker}",
                    (
                        f"가격: {price:,.2f} KRW\n"
                        f"금액: {krw_to_use:,.0f} KRW\n\n"
                        f"수분 내 체결 확정 대기\n"
                        f"─────\n"
                        f"uuid: {uuid}"
                    ),
                    dedupe_key=f"buy_req:{uuid}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass

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

    def buy_limit(
        self,
        price: float,
        ticker: str,
        ts=None,
        meta: Optional[Dict[str, Any]] = None,
        interval_sec: int = 60,
    ) -> dict:
        """
        고정가 매수 — 봉 종가를 가격으로 지정한 Upbit 지정가(Limit Order) 매수.

        - LIVE 모드 전용. test_mode=True 면 buy_market으로 폴백.
        - 재시도 없음(단일 시도). 미체결 시 OrderReconciler가 봉 간격 초과분을
          취소하고, 다음 봉에서 시그널 재평가가 자연스러운 재시도 역할을 한다.
        - 반환 dict에 `limit_pending=True` 포함 → 호출자(strategy_engine)는
          체결 확정 전이므로 position.open_position 을 호출하지 않고
          pending_order=True 만 유지한다.
        """
        # ✅ 사용자 결정사항: 고정가 매수는 LIVE 모드 한정. TEST 모드는 시장가로 폴백.
        if self.test_mode:
            logger.info("[BUY-LIMIT] TEST 모드 — buy_market으로 폴백")
            return self.buy_market(price, ticker, ts=ts, meta=meta)

        # 호가 라운딩 + sanity check
        try:
            rounded_price = float(_round_price_to_tick(float(price)))
        except Exception as e:
            logger.error(f"[BUY-LIMIT] 호가 라운딩 실패: {e}")
            return {}

        if rounded_price <= 0 or abs(rounded_price - float(price)) / max(float(price), 1e-9) > 0.005:
            err = f"호가 라운딩 비정상: 원가={price} 조정가={rounded_price}"
            logger.error(f"[BUY-LIMIT] {err}")
            self.last_buy_error = err
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                _notify(
                    LEVEL_CRITICAL,
                    f"❌ 고정가 매수 거부 — {ticker}",
                    (
                        f"사유: 호가 단위 이탈 (0.5% 초과)\n"
                        f"요청가: {price:,.4f} → 조정가: {rounded_price:,.2f}\n\n"
                        f"💡 신호 정확성 확인 — 비정상 가격 의심"
                    ),
                    dedupe_key=f"fixed_buy_tick:{ticker}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass
            insert_log(
                self.user_id,
                "ERROR",
                f"❌ 고정가 매수 거부 ({ticker}): {err}",
            )
            return {}

        # KRW 잔고 + 금액 계산 (buy_market 과 동일 공식)
        avail = self._krw_balance()
        if avail <= 0:
            err = "활성 KRW 잔고 0 — 고정가 매수 불가"
            logger.warning(f"[BUY-LIMIT] {err}")
            self.last_buy_error = err
            try:
                from services.notifier import send as _notify, LEVEL_WARNING
                _notify(
                    LEVEL_WARNING,
                    f"⚠️ 고정가 매수 보류 — {ticker}",
                    (
                        "사유: KRW 잔고 0원\n\n"
                        "💡 입금 또는 risk_pct 조정"
                    ),
                    dedupe_key=f"fixed_buy_balance_zero:{ticker}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass
            insert_log(
                self.user_id,
                "WARNING",
                f"❌ 고정가 매수 잔고 부족 ({ticker}): 가용 KRW=0",
            )
            return {}

        krw_to_use = math.floor(avail * self.risk_pct / (1 + MIN_FEE_RATIO))
        if krw_to_use < 5000:
            err = f"활성 KRW 부족: 가용={avail:.0f} 계산={krw_to_use:.0f} (최소 5,000 미만)"
            logger.warning(f"[BUY-LIMIT] {err}")
            self.last_buy_error = err
            try:
                from services.notifier import send as _notify, LEVEL_WARNING
                _notify(
                    LEVEL_WARNING,
                    f"⚠️ 고정가 매수 보류 — {ticker}",
                    (
                        f"사유: KRW 잔고 부족\n"
                        f"가용: {avail:,.0f} KRW (최소 5,000 필요)\n\n"
                        f"💡 입금 또는 risk_pct 조정"
                    ),
                    dedupe_key=f"fixed_buy_balance:{ticker}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass
            insert_log(
                self.user_id,
                "WARNING",
                f"❌ 고정가 매수 잔고 부족 ({ticker}): {err}",
            )
            return {}

        qty = round(krw_to_use / (rounded_price * (1 + MIN_FEE_RATIO)), 8)
        if qty <= 0:
            logger.warning(f"[BUY-LIMIT] 계산된 수량 0 — price={rounded_price} krw={krw_to_use}")
            return {}

        logger.info(
            f"[BUY-LIMIT] plan close={price} rounded={rounded_price} "
            f"krw_to_use={krw_to_use} qty={qty}"
        )

        # 지정가 주문 호출 (재시도 없음)
        call = _upbit_buy_limit(ticker, rounded_price, qty)
        logger.info(
            f"[BUY-LIMIT] ok={call['ok']} status={call['status']} "
            f"error_name={call['error_name']} error_message={call['error_message']}"
        )

        if not call["ok"]:
            if call["error_name"]:
                err_summary = (
                    f"Upbit error [{call['error_name']}]: {call['error_message']}"
                )
            elif call["exception"]:
                err_summary = f"exception: {call['exception']}"
            else:
                err_summary = (
                    f"invalid response (status={call['status']} body={call['body']!r})"
                )
            self.last_buy_error = err_summary
            logger.error(f"[BUY-LIMIT] FAILURE → {err_summary}")
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                from services.error_messages import format_error_block
                _label, _raw = format_error_block(err_summary)
                _notify(
                    LEVEL_CRITICAL,
                    f"❌ 고정가 매수 거부 — {ticker}",
                    (
                        f"사유: {_label}\n"
                        f"가격: {rounded_price:,.2f}  수량: {qty}\n\n"
                        f"💡 Upbit 응답 코드 확인\n"
                        f"─────\n"
                        f"err: {_raw}"
                    ),
                    dedupe_key=f"fixed_buy_fail:{ticker}:{err_summary[:80]}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass
            insert_log(
                self.user_id,
                "ERROR",
                f"❌ 고정가 매수 실패 ({ticker}): {err_summary}",
            )
            try:
                insert_order(
                    self.user_id, ticker, "BUY",
                    rounded_price, 0.0, "FAILED",
                    state="FAILED",
                    requested_at=now_kst(),
                    entry_bar=(meta or {}).get("bar"),
                )
            except Exception as e:
                logger.warning(f"[BUY-LIMIT] insert_order(FAILED) 실패: {e}")
            return {}

        # ✅ 성공 — 주문 등록 + Reconciler enqueue + 알림
        self.last_buy_error = None
        res = call["data"]
        try:
            uuid = res.get("uuid")

            # ✅ meta에 고정가 매수 표식 + 봉 간격 추가 (Reconciler timeout 계산용)
            enriched_meta = {
                **(meta or {}),
                "is_fixed_price_buy": True,
                "interval_sec": int(interval_sec or 60),
                "limit_price": rounded_price,
            }
            import json as _local_json
            meta_json = _local_json.dumps(enriched_meta)

            insert_order(
                self.user_id, ticker, "BUY",
                rounded_price, 0, "requested",
                provider_uuid=uuid,
                state="REQUESTED",
                requested_at=now_kst(),
                entry_bar=enriched_meta.get("bar"),
                meta=meta_json,
            )

            insert_log(
                self.user_id,
                "INFO",
                (
                    f"🎯 [LIVE 고정가] 지정가 매수 요청: {ticker} "
                    f"price={rounded_price} qty={qty} uuid={uuid}"
                ),
            )

            # 중요 알림: 고정가 매수 주문 등록 (v2 — 친화 표현)
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                _notify(
                    LEVEL_CRITICAL,
                    f"🎯 고정가 매수 요청 — {ticker}",
                    (
                        f"지정가: {rounded_price:,.4f} KRW\n"
                        f"수량: {qty}\n"
                        f"미체결 시 자동 취소: 다음 봉 (~{interval_sec}초)\n"
                        f"─────\n"
                        f"uuid: {uuid}"
                    ),
                    dedupe_key=f"fixed_buy_req:{uuid}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass

            # OrderReconciler 추적 큐에 등록 (체결 polling + timeout cancel)
            try:
                from engine.reconciler_singleton import get_reconciler
                get_reconciler().enqueue(
                    uuid,
                    user_id=self.user_id,
                    ticker=ticker,
                    side="BUY",
                    meta=enriched_meta,
                )
            except Exception as e:
                logger.error(f"[BUY-LIMIT] reconciler enqueue 실패: {e}")

            return {
                "time": ts,
                "side": "BUY",
                "qty": 0.0,
                "price": float(rounded_price),
                "uuid": uuid,
                "raw": res,
                "used_krw": float(krw_to_use),
                "ord_type": "limit",
                "limit_pending": True,  # ✅ 체결 확정 전 표식 — strategy_engine 이 open_position 호출 보류
            }
        except Exception as e:
            logger.error(f"[BUY-LIMIT] 주문 후처리 실패: {e}")
            insert_log(self.user_id, "ERROR", f"❌ 고정가 매수 후처리 예외: {e}")
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
            # B안: pyupbit swallow 우회 — 직접 호출 helper 사용
            call = _upbit_sell_market(ticker, qty)
            logger.info(
                f"[SELL-LIVE] ok={call['ok']} status={call['status']} "
                f"error_name={call['error_name']} error_message={call['error_message']}"
            )

            if not call["ok"]:
                if call["error_name"]:
                    err_summary = (
                        f"Upbit error [{call['error_name']}]: {call['error_message']}"
                    )
                elif call["exception"]:
                    err_summary = f"exception: {call['exception']}"
                else:
                    err_summary = (
                        f"invalid response (status={call['status']} "
                        f"body={call['body']!r})"
                    )
                self.last_sell_error = err_summary
                logger.error(f"[SELL-LIVE] FAILURE → {err_summary}")
                insert_log(
                    self.user_id,
                    "ERROR",
                    f"❌ 업비트 시장가 매도 실패: {err_summary}",
                )
                # Critical #3 + #6 알림: 매도 실패 + API 인증 실패 분리 (v2 — 한국어 라벨)
                try:
                    from services.notifier import send as _notify, LEVEL_CRITICAL
                    from services.error_messages import format_error_block
                    _label, _raw = format_error_block(err_summary)
                    _notify(
                        LEVEL_CRITICAL,
                        f"❌ 매도 실패 — {ticker}",
                        (
                            f"사유: {_label}\n"
                            f"수량: {qty:.6f}\n\n"
                            f"💡 보유 수량 또는 API 권한 점검\n"
                            f"─────\n"
                            f"err: {_raw}"
                        ),
                        dedupe_key=f"sell_fail:{ticker}:{err_summary}",
                        dedupe_ttl=60,
                    )
                    _low = (err_summary or "").lower()
                    if any(k in _low for k in (
                        "jwt_verification", "expired_access_key",
                        "no_authorization_i_p", "invalid_access_key",
                        "invalid_query_payload",
                    )):
                        _notify(
                            LEVEL_CRITICAL,
                            "🔑 Upbit API 인증 실패",
                            (
                                f"사유: {_label}\n\n"
                                f"💡 즉시 확인:\n"
                                f"  1. Upbit 콘솔 → API 키 만료일\n"
                                f"  2. 서버 IP 화이트리스트\n"
                                f"  3. .env 의 UPBIT_ACCESS / UPBIT_SECRET\n"
                                f"─────\n"
                                f"err: {_raw}"
                            ),
                            dedupe_key=f"api_auth:{err_summary}",
                            dedupe_ttl=600,
                        )
                except Exception:
                    pass
                return {}

            res = call["data"]
            self.last_sell_error = None
            uuid = res.get("uuid")
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

            # Critical #2 알림: LIVE SELL 요청 전송 성공 (v2 — 친화 표현)
            try:
                from services.notifier import send as _notify, LEVEL_CRITICAL
                _notify(
                    LEVEL_CRITICAL,
                    f"🔴 매도 요청 — {ticker}",
                    (
                        f"가격: {price:,.2f} KRW\n"
                        f"수량: {qty:.6f}\n\n"
                        f"수분 내 체결 확정 대기\n"
                        f"─────\n"
                        f"uuid: {uuid}"
                    ),
                    dedupe_key=f"sell_req:{uuid}",
                    dedupe_ttl=60,
                )
            except Exception:
                pass

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
