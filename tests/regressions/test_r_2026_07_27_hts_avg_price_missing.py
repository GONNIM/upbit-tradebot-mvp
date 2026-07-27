"""
✅ [Phase 2] F5 회귀: HTS 매수 후 avg_price=None silent 무력화 (커밋 4e2bc3e + e182230, 2026-07-27)

원 결함: HTS 매수 후 sync_from_wallet 이 has_position=True 로 세팅하지만
avg_price 는 None 잔존 → SL/TP/TS/Stale 필터가 pnl_pct=None 조기 return
(로그 없음) → 2.5일간 시장 -6.8% 하락 방치, 재시작 후 SL 강제 발동.

봉쇄 방식 (4e2bc3e Fix 1~4 + e182230 Phase 1):
- Fix 1: sync_from_wallet 이 avg_price 복구 (DB 캐시 → Upbit API)
- Fix 2: SELL 진입부 invariant 검증 (has_position + avg_price=None → CRITICAL + HOLD)
- Fix 3: SELL 필터 pnl_pct=None WARN 로그 (silent skip 방지)
- Fix 4: Reconciler → strategy_engine _on_hts_detect 콜백 (즉시 동기화)
- Phase 1-B: entry_ts 도 함께 복구 (Stale filter entry_ts=None silent skip 방지)
- Phase 1-A: check_position_invariants() 헬퍼 (I3 커버)

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_27_hts_avg_price_missing -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.position_state import PositionState  # noqa: E402
from core.position_invariants import check_position_invariants, INVARIANT_CODES  # noqa: E402
from core.filters.sell_filters import StopLossFilter, TakeProfitFilter  # noqa: E402
from core.filters.base import FilterResult  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


class TestHtsAvgPriceRecovery(unittest.TestCase):
    """F5-Fix1: sync_from_wallet 이 avg_price 를 DB 캐시/Upbit API 로 복구."""

    def _make_position(self, wallet_qty=100, wallet_avg=0,
                        db_cache_entry_price=None):
        """
        PositionState 를 fake trader 로 구성.
        - wallet_qty: trader._coin_balance() 반환
        - wallet_avg: Upbit balance.avg_buy_price
        - db_cache_entry_price: get_position_entry_price() 반환
        """
        trader = MagicMock()
        trader.user_id = "test_user"
        trader.test_mode = False  # LIVE 모드
        trader._coin_balance = MagicMock(return_value=wallet_qty)
        trader.upbit = MagicMock()
        trader.upbit.get_balances = MagicMock(return_value=[{
            "currency": "TEST",
            "balance": str(wallet_qty),
            "avg_buy_price": str(wallet_avg),
        }])
        pos = PositionState(trader=trader, ticker="KRW-TEST")
        return pos, trader, db_cache_entry_price

    def test_avg_price_recovered_from_db_cache(self):
        """DB 캐시에 entry_price 있으면 1순위로 복구."""
        pos, trader, _ = self._make_position(wallet_qty=100, wallet_avg=921)
        with patch("services.db.get_position_entry_price", return_value=915.47), \
             patch("services.db.get_position_meta", return_value={}):
            pos.sync_from_wallet()
        self.assertEqual(pos.avg_price, 915.47,
                        "DB 캐시가 1순위여야 함 (Upbit API 값 921 아님)")
        self.assertTrue(pos.has_position)

    def test_avg_price_recovered_from_upbit_api(self):
        """DB 캐시 없으면 Upbit API 로 복구 (2순위)."""
        pos, trader, _ = self._make_position(wallet_qty=100, wallet_avg=921)
        with patch("services.db.get_position_entry_price", return_value=None), \
             patch("services.db.get_position_meta", return_value={}):
            pos.sync_from_wallet()
        self.assertEqual(pos.avg_price, 921.0)

    def test_entry_ts_recovered_alongside_avg_price(self):
        """
        [Phase 1-B] avg_price 복구 성공 시 entry_ts 도 함께 세팅.
        entry_ts=None 잔존이 Stale filter silent skip 유발 방지 (P1-1).
        """
        pos, trader, _ = self._make_position(wallet_qty=100, wallet_avg=921)
        self.assertIsNone(pos.entry_ts)  # 초기 상태
        with patch("services.db.get_position_entry_price", return_value=915.47), \
             patch("services.db.get_position_meta", return_value={}):
            pos.sync_from_wallet()
        self.assertIsNotNone(pos.entry_ts,
                             "avg_price 복구 시 entry_ts 도 함께 세팅되어야 함 (P1-1)")


class TestHtsInvariantEnforcement(unittest.TestCase):
    """F5-Fix2 / Phase 1-A: has_position=True + avg_price=None invariant 감지."""

    def _make_position(self, has_pos=True, avg=None, qty=100, entry_ts=None):
        pos = PositionState()
        pos._has_position = has_pos
        pos.avg_price = avg
        pos.qty = qty
        pos.entry_ts = entry_ts
        return pos

    def test_i1_avg_price_none_detected(self):
        """I1: has_position=True + avg_price=None → 감지."""
        pos = self._make_position(has_pos=True, avg=None, qty=100)
        v = check_position_invariants(pos, context="test")
        self.assertIsNotNone(v)
        self.assertEqual(v[0], "I1_AVG_PRICE_MISSING")

    def test_i1_avg_price_zero_detected(self):
        """I1: avg_price=0 도 감지."""
        pos = self._make_position(has_pos=True, avg=0, qty=100)
        v = check_position_invariants(pos, context="test")
        self.assertIsNotNone(v)
        self.assertEqual(v[0], "I1_AVG_PRICE_MISSING")

    def test_i3_entry_ts_none_detected(self):
        """I3: has_position=True + avg_price=OK + entry_ts=None → P1-1 커버."""
        pos = self._make_position(has_pos=True, avg=915.47, qty=100, entry_ts=None)
        v = check_position_invariants(pos, context="test")
        self.assertIsNotNone(v)
        self.assertEqual(v[0], "I3_ENTRY_TS_MISSING")

    def test_normal_state_no_violation(self):
        """정상 상태는 위반 없음."""
        pos = self._make_position(
            has_pos=True, avg=915.47, qty=100,
            entry_ts=datetime(2026, 7, 27, tzinfo=KST),
        )
        v = check_position_invariants(pos, context="test")
        self.assertIsNone(v)


class TestSellFilterPnlNoneLogging(unittest.TestCase):
    """F5-Fix3: SL/TP 필터의 pnl_pct=None 조기 return 시 WARN 로그 발생."""

    def _make_position_with_none_avg(self):
        pos = PositionState()
        pos._has_position = True
        pos.avg_price = None  # 결함 상태 재현
        pos.qty = 100
        return pos

    def test_stop_loss_filter_returns_no_pnl_when_avg_none(self):
        """StopLossFilter 는 avg_price=None 시 NO_PNL 반환 (should_block=False)."""
        filter_ = StopLossFilter(stop_loss_pct=0.03)
        pos = self._make_position_with_none_avg()
        result = filter_.evaluate(position=pos, current_price=900.0)
        self.assertFalse(result.should_block)
        self.assertEqual(result.reason, "NO_PNL")

    def test_take_profit_filter_returns_no_pnl_when_avg_none(self):
        """TakeProfitFilter 도 동일 방어."""
        filter_ = TakeProfitFilter(take_profit_pct=0.01)
        pos = self._make_position_with_none_avg()
        result = filter_.evaluate(position=pos, current_price=1000.0)
        self.assertFalse(result.should_block)
        self.assertEqual(result.reason, "NO_PNL")

    def test_stop_loss_logs_warn_when_avg_none(self):
        """avg_price=None 시 WARN 로그 발생 검증 (Fix 3, silent skip 방지)."""
        import logging
        filter_ = StopLossFilter(stop_loss_pct=0.03)
        pos = self._make_position_with_none_avg()

        with self.assertLogs("core.filters.sell_filters", level="WARNING") as cm:
            filter_.evaluate(position=pos, current_price=900.0)
        # WARN 로그에 avg_price 상태 명시
        joined = "\n".join(cm.output)
        self.assertIn("STOP_LOSS_CHECK", joined)
        self.assertIn("avg_price=None", joined)


class TestReconcilerHtsDetectCallback(unittest.TestCase):
    """F5-Fix4: Reconciler HTS-DETECT 콜백 등록 + 발화 검증."""

    def test_reconciler_supports_register_hts_detect_callback(self):
        """order_reconciler 에 register_hts_detect_callback 메서드 존재."""
        # 실제 클래스 import
        from engine.order_reconciler import OrderReconciler
        rec = OrderReconciler.__new__(OrderReconciler)
        # __init__ 없이 attribute 만 확인
        self.assertTrue(hasattr(OrderReconciler, "register_hts_detect_callback"),
                       "register_hts_detect_callback 메서드 없음 → Fix 4 미배포")
        self.assertTrue(hasattr(OrderReconciler, "_fire_hts_detect_callback"),
                       "_fire_hts_detect_callback 없음 → Fix 4 미배포")

    def test_fake_reconciler_fires_callback_correctly(self):
        """Fake Reconciler 로 콜백 발화 시나리오 검증."""
        from tests.regressions.fixtures.fake_reconciler import FakeReconciler
        rec = FakeReconciler()

        received = {}

        def _cb(*, avg_price, qty, reason):
            received["avg_price"] = avg_price
            received["qty"] = qty
            received["reason"] = reason

        rec.register_hts_detect_callback("user1", "KRW-TEST", _cb)
        fired = rec.fire_hts_detect("user1", "KRW-TEST",
                                    avg_price=921.0, qty=1820.0, reason="HTS_BUY")
        self.assertTrue(fired)
        self.assertEqual(received["avg_price"], 921.0)
        self.assertEqual(received["qty"], 1820.0)
        self.assertEqual(received["reason"], "HTS_BUY")

    def test_unregister_cleans_hts_callbacks(self):
        """[P2-2] unregister_user 시 _hts_callbacks 정리."""
        from tests.regressions.fixtures.fake_reconciler import FakeReconciler
        rec = FakeReconciler()
        rec.register_hts_detect_callback("user1", "KRW-TEST", lambda **kw: None)
        self.assertTrue(rec.has_hts_callback("user1", "KRW-TEST"))
        rec.unregister_user("user1")
        self.assertFalse(rec.has_hts_callback("user1", "KRW-TEST"),
                        "unregister_user 후 hts callback 잔존 → P2-2 재발")


if __name__ == "__main__":
    unittest.main()
