from services.db import (
    insert_order,
    delete_orders,
)


def test_buy():
    # 테스트용 데이터
    user_id = "gon1972"
    ticker = "KRW-DOGE"
    price = 110.50  # 테스트용 매도 가격
    volume = 123.456  # 매도 수량
    status = "completed"  # 상태

    try:
        insert_order(
            user_id=user_id,
            ticker=ticker,
            side="BUY",
            price=price,
            volume=volume,
            status=status,
        )
        print(f"✅ test_sell: {ticker} 매도 주문 기록 성공 ({volume} @ {price})")
    except Exception as e:
        print(f"❌ test_sell 실패: {e}")


def test_sell():
    # 테스트용 데이터
    user_id = "gon1972"
    ticker = "KRW-DOGE"
    price = 110.50  # 테스트용 매도 가격
    volume = 123.456  # 매도 수량
    status = "completed"  # 상태

    try:
        insert_order(
            user_id=user_id,
            ticker=ticker,
            side="SELL",
            price=price,
            volume=volume,
            status=status,
        )
        print(f"✅ test_sell: {ticker} 매도 주문 기록 성공 ({volume} @ {price})")
    except Exception as e:
        print(f"❌ test_sell 실패: {e}")


def test_delete():
    delete_orders()
