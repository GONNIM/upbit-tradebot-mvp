import pyupbit
from typing import Optional
from engine.order_reconciler import OrderReconciler
from config import ACCESS, SECRET

_reconciler: Optional[OrderReconciler] = None

def get_reconciler() -> OrderReconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = OrderReconciler(pyupbit.Upbit(ACCESS, SECRET))
    return _reconciler
