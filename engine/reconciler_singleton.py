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
        _reconciler.start()
        logger.info("✅ [RECONCILER] Auto-started on first access")
    return _reconciler
