from services.db import fetch_logs, insert_log, fetch_latest_log_signal
from datetime import datetime
from core.trader import UpbitTrader
from engine.reconciler_singleton import get_reconciler


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
    return 0.0  # fallback


def force_liquidate(user_id: str, trader: UpbitTrader, ticker: str) -> str:
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

    log_summary = fetch_latest_log_signal(user_id, ticker)
    price_raw = log_summary.get("price") if log_summary else None

    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        msg = f"❌ 강제청산 실패: 가격 파싱 오류 → price={price_raw}"
        insert_log(user_id, "ERROR", msg)
        return msg

    if price <= 0:
        msg = "❌ 강제청산 실패: 최근 가격을 가져올 수 없습니다."
        insert_log(user_id, "ERROR", msg)
        return msg

    ts = datetime.now()
    meta = {
        "reason": "force_liquidate",
        "src": "manual",
        "price_ref": price,
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
        f"[LIVE] {ticker} 강제청산 요청 전송: "
        f"시장가(예상가≈{price:,.2f} KRW, 수량≈{qty:.6f})\n"
        f" → 주문 UUID: {uuid}\n"
        f" → 실제 체결 여부는 '실시간 주문 상태' 영역에서 확인하세요."
    )
    insert_log(user_id, "SELL", f"🚨 {msg}")

    try:
        get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="SELL")
    except Exception as e:
        insert_log(user_id, "ERROR", f"⚠️ 강제청산 reconciler enqueue 실패: {e}")

    return f"[LIVE] {ticker} 강제청산 요청 완료 (uuid={uuid})"


def force_buy_in(user_id: str, trader: UpbitTrader, ticker: str) -> str:
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

    log_summary = fetch_latest_log_signal(user_id, ticker)
    price_raw = log_summary.get("price") if log_summary else None

    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        msg = f"❌ 강제매수 실패: 가격 파싱 오류 → price={price_raw}"
        insert_log(user_id, "ERROR", msg)
        return msg

    if price <= 0:
        msg = "❌ 강제매수 실패: 최근 가격을 가져올 수 없습니다."
        insert_log(user_id, "ERROR", msg)
        return msg

    ts = datetime.now()
    meta = {
        "reason": "force_buy",
        "src": "manual",
        "price_ref": price,
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
