import pyupbit
import logging
from config import ACCESS, SECRET, MIN_FEE_RATIO
from services.db import (
    get_account,
    get_coin_balance,
    create_or_init_account,
    update_account,
    update_coin_position,
    insert_account_history,
    insert_position_history,
    insert_order,  # ✅ 거래 기록 추가
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
            return get_account(self.user_id)

        try:
            balance = self.upbit.get_balance(ticker="KRW")
            return float(balance) if balance else 0.0
        except Exception as e:
            logger.error(f"[실거래] KRW 잔고 조회 실패: {e}")
            return 0.0

    def _coin_balance(self, ticker: str) -> float:
        if self.test_mode:
            return get_coin_balance(self.user_id, ticker)

        try:
            cur = ticker.split("-")[1]
            for b in self.upbit.get_balances():
                if b["currency"] == cur:
                    return float(b["balance"])
            return 0.0
        except Exception as e:
            logger.error(f"[실거래] 코인 잔고 조회 실패: {e}")
            return 0.0

    def buy_market(self, price: float, ticker: str, ts=None) -> dict:
        krw_to_use = self._krw_balance() * self.risk_pct
        # ✅ 수수료 포함한 실제 지불 가능 수량 계산
        qty = round(krw_to_use / (price * (1 + MIN_FEE_RATIO)), 8)

        if qty <= 0:
            logger.warning(f"[BUY] 주문 수량이 0 이하입니다. qty={qty}")
            return {}

        if self.test_mode:
            current_krw = self._krw_balance()
            current_coin = self._coin_balance(ticker)

            self._simulate_buy(ticker, qty, price, current_krw, current_coin)

            # ✅ 음수 -0 방지 및 정수 변환
            raw_total = qty * price * (1 + MIN_FEE_RATIO)
            new_krw = max(int(current_krw - raw_total + 1e-8), 0)
            new_coin = current_coin + qty

            # insert_order(self.user_id, ticker, "BUY", price, qty, "completed")
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

            return {"time": ts, "side": "BUY", "qty": qty, "price": price}

        try:
            res = self.upbit.buy_market_order(ticker, qty)
            insert_order(self.user_id, ticker, "BUY", price, qty, "requested")
            return res
        except Exception as e:
            logger.error(f"[실거래] 매수 주문 실패: {e}")
            return {}

    def sell_market(self, qty: float, ticker: str, price: float, ts=None) -> dict:
        if qty <= 0:
            logger.warning("[SELL] 수량이 0 이하입니다. 매도 생략")
            return {}

        if self.test_mode:
            current_krw = self._krw_balance()
            current_coin = self._coin_balance(ticker)

            self._simulate_sell(ticker, qty, price, current_krw, current_coin)

            # ✅ 수익 계산 및 정수 변환 (음수 방지)
            raw_gain = qty * price
            fee = raw_gain * MIN_FEE_RATIO
            total_gain = max(int(raw_gain - fee + 1e-8), 0)

            new_krw = current_krw + total_gain
            new_coin = max(current_coin - qty, 0.0)

            # insert_order(self.user_id, ticker, "SELL", price, qty, "completed")
            insert_order(
                self.user_id,
                ticker,
                "SELL",
                price,
                qty,
                "completed",
                current_krw=new_krw,
                current_coin=new_coin,
                profit_krw=total_gain,  # 매도 수익
            )

            return {"time": ts, "side": "SELL", "qty": qty, "price": price}

        try:
            res = self.upbit.sell_market_order(ticker, qty)
            insert_order(self.user_id, ticker, "SELL", price, qty, "requested")
            return res
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
        """코인 매수 처리: 수수료는 외부에서 고려된 qty 기준으로 계산"""
        amount = qty * price
        fee = amount * MIN_FEE_RATIO
        total_spent = amount + fee

        # 이미 fee 포함 qty로 계산했기 때문에 잔고 과차감 방지
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
        """코인 매도 처리: qty 기준 수수료 차감"""
        amount = qty * price
        fee = amount * MIN_FEE_RATIO
        total_gain = amount - fee

        new_krw = current_krw + total_gain
        new_coin = max(current_coin - qty, 0.0)

        update_account(self.user_id, new_krw)
        update_coin_position(self.user_id, ticker, new_coin)

        insert_account_history(self.user_id, new_krw)
        insert_position_history(self.user_id, ticker, new_coin)
