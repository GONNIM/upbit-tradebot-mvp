# WO-20 배포 2(c) (서버): 배포된 새 코드의 get_last_open_buy_order 호출 — SELECT 만 수행하는 함수.
# 함수 안의 "[DB] last BUY (with status filter=True) => …" 로그로 청산 검사 전 선택 행을 함께 본다.
import logging, sys
sys.path.insert(0, "/root/upbit-tradebot-mvp")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s", stream=sys.stdout)
from services.db import get_last_open_buy_order
import inspect
src = inspect.getsource(get_last_open_buy_order)
print("배포 코드 정렬 식:", "COALESCE" in src and "order_keys = [c for c in (\"executed_at\", \"updated_at\", \"timestamp\")" in src)
r = get_last_open_buy_order("KRW-JTO", "mcmax33")
print("get_last_open_buy_order(KRW-JTO) =", r)
