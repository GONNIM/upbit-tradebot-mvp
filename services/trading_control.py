from services.db import fetch_logs, insert_log, fetch_latest_log_signal, fetch_latest_log_signal_ema
from datetime import datetime
from core.trader import UpbitTrader
from engine.reconciler_singleton import get_reconciler
import logging

logger = logging.getLogger(__name__)


def get_current_price_from_upbit(ticker: str) -> float | None:
    """
    Upbit API로 실시간 현재가 조회
    - 가장 안전하고 정확한 방법
    - 로그 파싱 실패 시 대체용
    """
    try:
        import pyupbit
        current = pyupbit.get_current_price(ticker)
        if current and current > 0:
            logger.info(f"[PRICE] Upbit API 조회 성공: {ticker} = {current:,.2f}")
            return float(current)
        logger.warning(f"[PRICE] Upbit API 응답 이상: {ticker} = {current}")
    except Exception as e:
        logger.warning(f"[PRICE] Upbit API 조회 실패: {e}")
    return None


def get_last_price_from_logs(user_id: str) -> float:
    """
    로그 테이블에서 가장 최근 가격을 추출 (price=... 포함된 로그 메시지에서 추출)
    예시 로그 메시지: '2025-06-30 18:00:00 | price=225.3 | cross=Neutral | macd=...'
    """
    logs = fetch_logs(user_id, limit=30)
    for log in logs:
        msg = log[2]
        if "price=" in msg:
            try:
                # 'price=' 다음 숫자만 추출
                price_part = msg.split("price=")[1].split("|")[0].strip()
                return float(price_part.replace(",", ""))
            except Exception:
                continue
    return 0.0 # fallback


def force_liquidate(user_id: str, trader: UpbitTrader, ticker: str, interval_sec: int = 60) -> str:
    """
    보유 코인을 강제청산 (시장가 매도).
    - TEST: 즉시 체결
    - LIVE: 주문만 보내고, 실제 체결/수량/평단은 Reconciler가 orders 테이블에 반영
    """
    qty = trader._coin_balance(ticker)
    if qty <= 0:
        msg = f"⚠️ 강제청산 실패: 보유 코인이 없습니다. (ticker={ticker})"
        insert_log(user_id, "INFO", msg)
        return msg

    # ✅ 가격 조회 우선순위:
    # 1) MACD 로그 → 2) EMA 로그 → 3) 일반 로그 파싱 → 4) Upbit API 실시간 조회
    price = None

    # 1. MACD 로그 시도
    log_summary = fetch_latest_log_signal(user_id, ticker)
    if log_summary:
        try:
            price = float(log_summary.get("price"))
            logger.info(f"[PRICE] MACD 로그에서 조회: {price:,.2f}")
        except (TypeError, ValueError):
            pass

    # 2. EMA 로그 시도
    if price is None or price <= 0:
        log_summary_ema = fetch_latest_log_signal_ema(user_id, ticker)
        if log_summary_ema:
            try:
                price = float(log_summary_ema.get("price"))
                logger.info(f"[PRICE] EMA 로그에서 조회: {price:,.2f}")
            except (TypeError, ValueError):
                pass

    # 3. 일반 로그 파싱 시도
    if price is None or price <= 0:
        price = get_last_price_from_logs(user_id)
        if price > 0:
            logger.info(f"[PRICE] 일반 로그 파싱에서 조회: {price:,.2f}")

    # 4. Upbit API 실시간 조회 (최후의 수단)
    if price is None or price <= 0:
        price = get_current_price_from_upbit(ticker)

    # 모든 방법 실패
    if price is None or price <= 0:
        msg = f"❌ 강제청산 실패: 모든 가격 조회 실패 (MACD 로그, EMA 로그, 일반 로그, Upbit API 모두 실패)"
        insert_log(user_id, "ERROR", msg)
        return msg

    ts = datetime.now()
    meta = {
        "interval": interval_sec,  # ✅ interval_sec 전달
        "reason": "force_liquidate",
        "src": "manual",
        "price_ref": price,
        "bar_time": None,  # ✅ 강제 청산은 봉 시각 없음
    }

    result = trader.sell_market(qty, ticker, price, ts=ts, meta=meta)
    if not result:
        msg = "❌ 강제청산 실패: 거래 처리 중 오류 발생"
        insert_log(user_id, "ERROR", msg)
        return msg

    if trader.test_mode:
        insert_log(
            user_id,
            "SELL",
            f"🚨 [TEST] 강제청산 실행됨: {result['qty']:.6f} {ticker} @ {result['price']:,f} KRW",
        )
        return f"[TEST] {ticker} 강제청산 완료: {result['qty']:.6f} @ {result['price']:,f}"

    uuid = result.get("uuid")
    if not uuid:
        msg = (
            f"❌ [LIVE] 강제청산 요청 실패: Upbit 응답에 uuid가 없습니다. "
            f"(qty≈{qty:.6f}, raw={result.get('raw')})"
        )
        insert_log(user_id, "ERROR", msg)
        return msg
    
    msg = (
        f"🚨 [LIVE] 강제청산 요청 전송: {ticker} 시장가, "
        f"예상가≈{price:,.2f} KRW, 수량≈{qty:.6f} (uuid={uuid})"
    )
    insert_log(user_id, "SELL", msg)

    try:
        get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="SELL")
    except Exception as e:
        insert_log(user_id, "ERROR", f"⚠️ 강제청산 reconciler enqueue 실패: {e}")

    return f"[LIVE] {ticker} 강제청산 요청 완료 (uuid={uuid})"


def force_buy_in(user_id: str, trader: UpbitTrader, ticker: str, interval_sec: int = 60) -> str:
    """
    강제매수 (시장가).
    - TEST: 즉시 체결
    - LIVE: 주문만 보내고, 실제 체결/수량/평단은 Reconciler가 orders 테이블에 반영
    - 실제 주문금액은 UpbitTrader.risk_pct * 현재 KRW 잔고
    """
    krw = trader._krw_balance()
    if krw <= 0:
        msg = "⚠️ 강제매수 실패: 보유 KRW가 없습니다."
        insert_log(user_id, "INFO", msg)
        return msg

    # ✅ 가격 조회 우선순위:
    # 1) MACD 로그 → 2) EMA 로그 → 3) 일반 로그 파싱 → 4) Upbit API 실시간 조회
    price = None

    # 1. MACD 로그 시도
    log_summary = fetch_latest_log_signal(user_id, ticker)
    if log_summary:
        try:
            price = float(log_summary.get("price"))
            logger.info(f"[PRICE] MACD 로그에서 조회: {price:,.2f}")
        except (TypeError, ValueError):
            pass

    # 2. EMA 로그 시도
    if price is None or price <= 0:
        log_summary_ema = fetch_latest_log_signal_ema(user_id, ticker)
        if log_summary_ema:
            try:
                price = float(log_summary_ema.get("price"))
                logger.info(f"[PRICE] EMA 로그에서 조회: {price:,.2f}")
            except (TypeError, ValueError):
                pass

    # 3. 일반 로그 파싱 시도
    if price is None or price <= 0:
        price = get_last_price_from_logs(user_id)
        if price > 0:
            logger.info(f"[PRICE] 일반 로그 파싱에서 조회: {price:,.2f}")

    # 4. Upbit API 실시간 조회 (최후의 수단)
    if price is None or price <= 0:
        price = get_current_price_from_upbit(ticker)

    # 모든 방법 실패
    if price is None or price <= 0:
        msg = f"❌ 강제매수 실패: 모든 가격 조회 실패 (MACD 로그, EMA 로그, 일반 로그, Upbit API 모두 실패)"
        insert_log(user_id, "ERROR", msg)
        return msg

    ts = datetime.now()
    meta = {
        "interval": interval_sec,  # ✅ interval_sec 전달
        "reason": "force_buy",
        "src": "manual",
        "price_ref": price,
        "bar_time": None,  # ✅ 강제 매수는 봉 시각 없음
    }

    result = trader.buy_market(price, ticker, ts=ts, meta=meta)
    if not result:
        msg = "❌ 강제매수 실패: 주문 생성 실패 (잔고 부족 또는 최소 주문금액 미만일 수 있음)"
        insert_log(user_id, "ERROR", msg)
        return msg

    used_krw = result.get("used_krw")
    # 🔹 방어 로직: used_krw가 없으면 현재 잔고 * risk_pct로 추정
    if used_krw is None:
        try:
            used_krw = trader._krw_balance() * trader.risk_pct
        except Exception:
            used_krw = 0.0

    if trader.test_mode:
        insert_log(
            user_id,
            "BUY",
            f"🚨 [TEST] 강제매수 실행됨: {result['qty']:.6f} {ticker} @ {result['price']:,f} KRW "
            f"(사용 KRW ≈ {used_krw:,.0f})",
        )
        return f"[TEST] {ticker} 강제매수 완료: {result['qty']:.6f} @ {result['price']:,f}"

    uuid = result.get("uuid")
    if not uuid:
        msg = (
            f"❌ [LIVE] 강제매수 요청 실패: Upbit 응답에 uuid가 없습니다. "
            f"(사용 KRW ≈ {used_krw:,.0f}, raw={result.get('raw')})"
        )
        insert_log(user_id, "ERROR", msg)
        return msg

    insert_log(
        user_id,
        "BUY",
        f"🚨 [LIVE] 강제매수 요청 전송: {ticker} 시장가, 예상가≈{price:,.2f} KRW "
        f"(사용 KRW ≈ {used_krw:,.0f}, uuid={uuid})",
    )

    try:
        get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="BUY")
    except Exception as e:
        insert_log(user_id, "ERROR", f"⚠️ 강제매수 reconciler enqueue 실패: {e}")

    return f"[LIVE] {ticker} 강제매수 요청 완료 (uuid={uuid})"
