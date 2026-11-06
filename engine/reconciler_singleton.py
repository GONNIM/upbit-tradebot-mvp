import pyupbit
import logging
from typing import Optional
from engine.order_reconciler import OrderReconciler
from config import ACCESS, SECRET

_reconciler: Optional[OrderReconciler] = None
logger = logging.getLogger(__name__)

def get_reconciler() -> OrderReconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = OrderReconciler(pyupbit.Upbit(ACCESS, SECRET))
        # ✅ 1104-02 G1 (11/06): 운영 Reconciler 는 모의 지갑 지킴을 켠다(실계좌 엔진이 없을 때만 동작).
        _reconciler.guard_mock_wallet = True
        _reconciler.start()
        logger.info("✅ [RECONCILER] Auto-started on first access")
    return _reconciler
