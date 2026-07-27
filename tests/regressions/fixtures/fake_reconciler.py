"""
✅ [Phase 2] Fake OrderReconciler — 회귀 테스트용 mock.

목적: 폴링 없이 이벤트를 즉시 발화 (fill_callback, hts-detect callback).
Fix 4 (HTS-DETECT 콜백) 회귀 테스트에 필수.
"""
from typing import Dict, Any, Callable, Optional


class FakeReconciler:
    """OrderReconciler 최소 mock. 콜백 등록/발화만 지원."""

    def __init__(self):
        self._fill_callbacks: Dict[tuple, Callable] = {}
        self._hts_callbacks: Dict[tuple, Callable] = {}
        self._registered_users: set = set()

    def register_user(self, user_id: str, test_mode: bool = False):
        self._registered_users.add(user_id)

    def unregister_user(self, user_id: str):
        self._registered_users.discard(user_id)
        # fill callback 정리
        to_remove = [k for k in self._fill_callbacks.keys() if k[0] == user_id]
        for k in to_remove:
            self._fill_callbacks.pop(k, None)
        # hts callback 정리 (Phase 1 P2-2 검증 대상)
        to_remove_hts = [k for k in self._hts_callbacks.keys() if k[0] == user_id]
        for k in to_remove_hts:
            self._hts_callbacks.pop(k, None)

    def register_fill_callback(self, user_id: str, ticker: str, callback: Callable):
        self._fill_callbacks[(user_id, ticker)] = callback

    def register_hts_detect_callback(self, user_id: str, ticker: str, callback: Callable):
        self._hts_callbacks[(user_id, ticker)] = callback

    def _fire_fill_callback(self, user_id: str, ticker: str, **kwargs):
        """수동으로 fill 콜백 발화 (테스트용)."""
        cb = self._fill_callbacks.get((user_id, ticker))
        if cb:
            cb(**kwargs)

    def fire_hts_detect(self, user_id: str, ticker: str, *,
                        avg_price: float, qty: float, reason: str) -> bool:
        """
        수동으로 HTS-DETECT 콜백 발화 (테스트용).

        Returns:
            bool: 콜백이 있어서 발화됐으면 True, 없으면 False.
        """
        cb = self._hts_callbacks.get((user_id, ticker))
        if cb is None:
            return False
        cb(avg_price=avg_price, qty=qty, reason=reason)
        return True

    def has_fill_callback(self, user_id: str, ticker: str) -> bool:
        return (user_id, ticker) in self._fill_callbacks

    def has_hts_callback(self, user_id: str, ticker: str) -> bool:
        return (user_id, ticker) in self._hts_callbacks
