from services.db import fetch_logs, insert_log, fetch_latest_log_signal
from datetime import datetime
from core.trader import UpbitTrader


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
    보유 코인을 강제청산 (시장가 매도)하며 로그를 남김.
    가격은 가장 최근 logs 테이블에서 가져옴.
    """
    qty = trader._coin_balance(ticker)
    if qty <= 0:
        msg = "⚠️ 강제청산 실패: 보유 코인이 없습니다."
        insert_log(user_id, "INFO", msg)
        return msg

    # ⛳ 최근 가격 로그에서 가져오기
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

    result = trader.sell_market(qty, ticker, price)
    if result:
        # 💡 trader.sell_market 내에서 insert_order 이미 수행됨!
        insert_log(
            user_id,
            "SELL",
            f"🚨 강제청산 실행됨: {result["qty"]:f} {ticker} @ {result["price"]:,f} KRW",
        )
        return f"{ticker} 강제청산 완료: {result["qty"]:f} @ {result["price"]:,f}"


def force_buy_in(user_id: str, trader: UpbitTrader, ticker: str) -> str:
    """
    사용자의 보유 KRW를 기준으로 시장가로 코인을 강제 매수함.
    최근 로그로부터 가격을 추출하고, 최대 주문 가능 수량을 계산하여 매수 처리.
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

    qty = krw / price
    if qty <= 0:
        msg = "❌ 강제매수 실패: 계산된 수량이 0 이하입니다."
        insert_log(user_id, "ERROR", msg)
        return msg

    result = trader.buy_market(price, ticker)
    if result:
        insert_log(
            user_id,
            "BUY",
            f"🚨 강제매수 실행됨: {result["qty"]:f} {ticker} @ {result["price"]:,f} KRW",
        )
        return f"{ticker} 강제매수 완료: {result["qty"]:f} @ {result["price"]:,f}"
    else:
        msg = "❌ 강제매수 실패: 거래 처리 중 오류 발생"
        insert_log(user_id, "ERROR", msg)
        return msg
