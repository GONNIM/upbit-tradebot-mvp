"""
1029-12 (2026-11-03, 사용자 「1029-12 권고대로」 D1~D8): 실계좌 동기화가 모의 지갑을 덮어쓰지 않게.

계획: docs/plans/2026-11-03-mock-wallet-overwrite/plan.md (3판)
- W  ui/pullback_lock.keeps_wallet: 새 전략 켜짐 또는 keeps_capital(보유·예약·예약 읽기 실패)
- C1 OrderReconciler.register_user(test_mode=True) → unregister_user (예외 종료로 남은 실계좌 사용자 빼기)
- C2 로그인 검증(auto_verify·app.py 단추): W 참이면 지갑 표·운용자산을 쓰지 않음, 화면 문구
- C3 services/db.py 워밍업 자리표시자 갱신 로그 문구(BUY·SELL)
- C4 pages/dashboard.py 모의 현금 쓰기 조건 = 잠김 and W (화면 동작은 t15_old_ui 시험)
시험은 바깥 연결 없이(가짜 업비트·임시 DB).
"""
from __future__ import annotations

import json
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.regressions.test_r_2026_10_29_p4_t15_old_ui import _Base, USER  # noqa: E402
from tests.regressions.test_r_2026_10_02_wo19_warmup_audit_preserve import _DbCase  # noqa: E402


# ============================================================ W
class TestKeepsWallet(unittest.TestCase):
    def kw(self, **st):
        from ui.pullback_lock import keeps_wallet
        base = {"pullback": False, "holding": False, "reservation": None, "reservation_error": False}
        base.update(st)
        return keeps_wallet(base)

    def test_pullback_on_flat(self):
        self.assertTrue(self.kw(pullback=True))

    def test_holding_reserved_read_error(self):
        self.assertTrue(self.kw(holding=True))
        self.assertTrue(self.kw(reservation={"id": 1}))
        self.assertTrue(self.kw(reservation_error=True))

    def test_ema_nothing(self):
        self.assertFalse(self.kw())


class TestKeepsWalletOnVerify(_Base):
    def test_pullback_flat_true(self):
        self.pullback(entry=0, qty=0.0)
        from services.auto_verify import keeps_wallet_on_verify
        self.assertTrue(keeps_wallet_on_verify(USER))

    def test_ema_false(self):
        self.ema()
        from services.auto_verify import keeps_wallet_on_verify
        self.assertFalse(keeps_wallet_on_verify(USER))

    def test_exception_keeps(self):
        from services.auto_verify import keeps_wallet_on_verify
        with patch("ui.pullback_lock.lock_state", side_effect=RuntimeError("x")):
            self.assertTrue(keeps_wallet_on_verify(USER))


# ============================================================ C2
class TestAutoVerifyWallet(_Base):
    def verify(self):
        import config
        import services.upbit_api as ua
        accounts = [{"currency": "KRW", "balance": "5555555"},
                    {"currency": "ZRO", "balance": "3", "locked": "0", "avg_buy_price": "100"}]
        self.acc = MagicMock()
        self.pos = MagicMock()
        with patch.object(config, "ACCESS", "a"), patch.object(config, "SECRET", "b"), \
                patch.object(ua, "validate_upbit_keys", MagicMock(return_value=(True, accounts))), \
                patch("services.db.update_account_from_balances", self.acc), \
                patch("services.db.update_position_from_balances", self.pos):
            from services.auto_verify import run_live_auto_verify
            return run_live_auto_verify(USER, "새이름")

    def test_pullback_flat_skips_wallet_and_capital(self):
        self.pullback(entry=0, qty=0.0)
        r = self.verify()
        self.assertTrue(r["wallet_kept"])
        self.assertTrue(r["capital_kept"])
        self.acc.assert_not_called()
        self.pos.assert_not_called()

    def test_pullback_holding_skips(self):
        self.pullback(entry=1, qty=5.0)
        r = self.verify()
        self.assertTrue(r["wallet_kept"])
        self.acc.assert_not_called()

    def test_reserved_skips(self):
        self.ema()
        self.reserve("TEST")
        r = self.verify()
        self.assertTrue(r["wallet_kept"])
        self.acc.assert_not_called()

    def test_ema_syncs(self):
        self.ema()
        r = self.verify()
        self.assertFalse(r["wallet_kept"])
        self.acc.assert_called_once()
        self.pos.assert_called_once()

    def test_no_user_row_still_keeps_wallet(self):
        """users 행이 없어 운용자산은 새로 저장해도(save_user), 지갑 표 판정은 따로 — 지킴."""
        self.pullback(entry=1, qty=5.0)
        self.sql("DELETE FROM users")
        r = self.verify()
        self.assertFalse(r["capital_kept"])
        self.assertTrue(r["wallet_kept"])
        self.acc.assert_not_called()


class TestAppSource(unittest.TestCase):
    SRC = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_manual_verify_uses_fresh_judgement(self):
        i = self.SRC.index("_wallet_kept = keeps_wallet_on_verify(username)")
        j = self.SRC.index("update_account_from_balances(username, data)")
        self.assertLess(i, j)
        block = self.SRC[i:j]
        self.assertIn("if _wallet_kept:", block)
        self.assertNotIn("_capital_kept_in_live", block)

    def test_manual_verify_info_line(self):
        i = self.SRC.index('st.success("Upbit 계정 검증 성공! 잔고 정보를 표로 표시합니다.")')
        self.assertIn('if _wallet_kept:\n                            st.info(WALLET_KEPT_LINE.lstrip("- "))',
                      self.SRC[i:i + 300])

    def test_auto_verify_line(self):
        self.assertIn('WALLET_KEPT_LINE if _verify_result.get("wallet_kept") else "- DB 동기화: 완료"', self.SRC)
        from services.auto_verify import WALLET_KEPT_LINE
        self.assertEqual(WALLET_KEPT_LINE, "- DB 동기화: 새 전략 모의 지갑을 지키려고 건너뜀")


# ============================================================ C4
class TestDashboardSource(unittest.TestCase):
    def test_keep_cash_uses_wallet(self):
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("_pb_keep_cash = _pb_locked and _pb_keeps_wallet(_pb_lock)", src)


class TestDashboardFlatKeepsCash(_Base):
    """새 전략 켜짐·보유 없음 → 모의 현금 그대로(t15 test_c1a_overwrite_when_pullback_flat 과 같은 뜻), EMA 는 덮어씀."""
    def test_ema_overwrites(self):
        self.ema()
        self.cash(800_000)
        self.dash()
        from services.db import get_account
        self.assertEqual(get_account(USER), 1_000_000)


# ============================================================ C1
class _FakeUpbit:
    def __init__(self, balances):
        self.balances = balances

    def get_balances(self):
        return self.balances


class TestReconcilerTestModeUnregister(unittest.TestCase):
    def rec(self):
        from engine.order_reconciler import OrderReconciler
        return OrderReconciler(_FakeUpbit([{"currency": "KRW", "balance": "5555555", "locked": "0"}]),
                               balance_sync_interval=0.0)

    def test_test_register_removes_live_user(self):
        r = self.rec()
        r.register_user("u1", test_mode=False)
        r._fill_callbacks[("u1", "KRW-ZRO")] = object()
        r._pending["uuid-1"] = {"user_id": "u1", "ticker": "KRW-ZRO", "side": "buy", "last": None, "meta": {}}
        r.register_user("u1", test_mode=True)
        self.assertNotIn("u1", r._live_user_ids)
        self.assertNotIn(("u1", "KRW-ZRO"), r._fill_callbacks)
        self.assertIn("uuid-1", r._pending)            # 남은 실주문 끝 처리는 그대로(R4)

    def test_other_user_kept(self):
        r = self.rec()
        r.register_user("u1", test_mode=False)
        r.register_user("u2", test_mode=False)
        r.register_user("u1", test_mode=True)
        self.assertEqual(r._live_user_ids, {"u2"})

    def test_r2_periodic_sync_skips_test_user(self):
        """R2: 실계좌 등록 뒤 stop 없이(예외 종료) 모의 등록 → 1분 동기화가 그 사용자 표를 쓰지 않음."""
        r = self.rec()
        r.register_user("u1", test_mode=False)
        r.register_user("u1", test_mode=True)
        with patch("engine.order_reconciler.update_account_from_balances") as acc, \
                patch("engine.order_reconciler.sync_all_positions_from_balances") as sync_all:
            r._periodic_balance_sync()
        acc.assert_not_called()
        sync_all.assert_not_called()

    def test_live_register_still_syncs(self):
        r = self.rec()
        r.register_user("u1", test_mode=False)
        with patch("engine.order_reconciler.update_account_from_balances") as acc, \
                patch("engine.order_reconciler.sync_all_positions_from_balances"), \
                patch("engine.order_reconciler.update_position_from_balances"), \
                patch("services.db.get_position_total_qty", return_value=0.0):
            r._periodic_balance_sync()
        acc.assert_called_once()

    def test_register_before_engine_callbacks(self):
        """live_loop: register_user 가 StrategyEngine 생성(콜백 등록)보다 먼저 — 새 모의 엔진 콜백은 지워지지 않음."""
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        i = src.index("reconciler.register_user(user_id, test_mode=test_mode)")
        j = src.index("engine = StrategyEngine(", i)
        self.assertLess(i, j)

    def test_normal_stop_stops_reconciler(self):
        """정상 정지: LIVE 사용자 집합에서 빼고 비면 Reconciler 정지 (P2 의 전제 — 1029-12 계획 2절)."""
        src = (ROOT / "engine" / "engine_manager.py").read_text(encoding="utf-8")
        i = src.index("def stop_engine(")
        body = src[i:i + 4000]
        k = body.index("if running_mode == MODE_LIVE:")
        tail = body[k:k + 400]
        self.assertIn("self._live_users.discard(key)", tail)
        self.assertIn("get_reconciler().stop()", tail)


# ============================================================ C3
class TestPlaceholderLogText(_DbCase):
    def test_buy_placeholder_update_text(self):
        eng = self._engine()
        self.assertEqual(eng.record_warmup_log(self._bar(), "(완료 10/200)"), "inserted")
        with self.assertLogs("services.db", level="INFO") as cm:
            res = eng.record_warmup_log(self._bar(750.0), "(완료 129/200)")
        self.assertEqual(res, "updated_placeholder")
        text = "\n".join(cm.output)
        self.assertIn("[AUDIT-UPDATE] BUY 워밍업 자리표시자 갱신", text)
        self.assertNotIn("실시간 재판정", text)

    def test_buy_realtime_rejudge_text_unchanged(self):
        self._real_buy()
        with self.assertLogs("services.db", level="INFO") as cm:
            self._real_buy(price=751.0)
        self.assertIn("[AUDIT-UPDATE] BUY 실시간 재판정", "\n".join(cm.output))

    def test_both_kinds_keep_rejudge_text(self):
        """BUY·SELL 두 분기 모두 실판정 재판정 문구를 그대로 둔다(문구만 나눔)."""
        src = (ROOT / "services" / "db.py").read_text(encoding="utf-8")
        line = '_upd_kind = "워밍업 자리표시자 갱신" if warmup_placeholder else "실시간 재판정"'
        self.assertEqual(src.count(line), 2)
        self.assertIn('f"[AUDIT-UPDATE] BUY {_upd_kind}', src)
        self.assertIn('f"[AUDIT-UPDATE] SELL {_upd_kind}', src)

    def test_sell_placeholder_update_text(self):
        eng = self._engine(has_position=True)
        eng.position = MagicMock(has_position=True, avg_price=700.0, highest_price=None, entry_bar=None,
                                 trailing_armed=False)
        first = eng.record_warmup_log(self._bar(), "(완료 10/200)")
        self.assertEqual(first, "inserted")
        with self.assertLogs("services.db", level="INFO") as cm:
            res = eng.record_warmup_log(self._bar(750.0), "(완료 129/200)")
        self.assertEqual(res, "updated_placeholder")
        text = "\n".join(cm.output)
        self.assertIn("[AUDIT-UPDATE] SELL 워밍업 자리표시자 갱신", text)
        self.assertNotIn("실시간 재판정", text)


if __name__ == "__main__":
    unittest.main()
