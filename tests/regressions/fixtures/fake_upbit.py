"""
✅ [Phase 2] Fake Upbit API — 회귀 테스트용 mock.

목적: 실 Upbit API 호출 없이 5건 결함 재현 시나리오를 자동화.
- 잔고 응답 시퀀스 주입 (get_balances)
- 주문 상태 조회 mock (get_order)
- avg_buy_price 없음 / 있음 스위칭 (F5 재현)
"""
from typing import List, Dict, Any, Optional


class FakeUpbit:
    """Upbit pyupbit.Upbit 를 흉내내는 최소 mock. LIVE 모드 회귀 테스트용."""

    def __init__(self, balances_seq: Optional[List[List[Dict[str, Any]]]] = None):
        """
        Args:
            balances_seq: get_balances() 호출마다 순차 반환할 응답 목록.
                          [] 는 잔고 없음. 시퀀스 소진 후 마지막 응답 반복.
        """
        self._balances_seq = balances_seq or [[]]
        self._balances_call_count = 0
        self._orders: Dict[str, Dict[str, Any]] = {}  # uuid → order state

    def get_balances(self) -> List[Dict[str, Any]]:
        """호출 순서대로 balances_seq 에서 반환. 소진 시 마지막 응답 반복."""
        idx = min(self._balances_call_count, len(self._balances_seq) - 1)
        self._balances_call_count += 1
        return self._balances_seq[idx]

    def set_balances(self, balances: List[Dict[str, Any]]) -> None:
        """다음 호출부터 이 응답 사용 (테스트 중간 시나리오 전환용)."""
        self._balances_seq = [balances]
        self._balances_call_count = 0

    def get_order(self, uuid: str) -> Optional[Dict[str, Any]]:
        return self._orders.get(uuid)

    def add_order(self, uuid: str, state: str, executed_volume: float = 0,
                  avg_price: float = 0) -> None:
        """테스트 시나리오용 주문 삽입 (예: FILLED, CANCELED)."""
        self._orders[uuid] = {
            "uuid": uuid,
            "state": state,
            "executed_volume": str(executed_volume),
            "price": str(avg_price),
            "fee": "0",
        }


# ─────────────────────────────────────────────────────────────
# 시나리오 헬퍼 (자주 쓰는 잔고 응답)
# ─────────────────────────────────────────────────────────────

def balances_krw_only(krw: float) -> List[Dict[str, Any]]:
    """KRW 만 있는 상태."""
    return [{
        "currency": "KRW",
        "balance": str(krw),
        "locked": "0",
        "avg_buy_price": "0",
        "avg_buy_price_modified": True,
        "unit_currency": "KRW",
    }]


def balances_with_coin(ticker: str, qty: float, avg_buy_price: float = 0,
                      krw: float = 0) -> List[Dict[str, Any]]:
    """KRW + 지정 코인 보유 상태. avg_buy_price=0 은 F5 재현용 (HTS 매수 직후 캐시 없음)."""
    sym = ticker.split("-")[-1].upper() if "-" in ticker else ticker.upper()
    return [
        {
            "currency": "KRW",
            "balance": str(krw),
            "locked": "0",
            "avg_buy_price": "0",
            "avg_buy_price_modified": True,
            "unit_currency": "KRW",
        },
        {
            "currency": sym,
            "balance": str(qty),
            "locked": "0",
            "avg_buy_price": str(avg_buy_price),
            "avg_buy_price_modified": False,
            "unit_currency": "KRW",
        },
    ]
