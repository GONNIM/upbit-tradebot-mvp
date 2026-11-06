"""
1104-02 (2026-11-06, 사용자 「1104-02 ㉠ 가, ㉡ 저장」 · 「1104-02 구현 승인」): 모의 지갑이 덮일 수 있는 좁은 틈 3가지.

계획: docs/plans/2026-11-06-mock-wallet-gaps/plan.md (2판 · 5-1 Fable 권고)
- G1   OrderReconciler: 실계좌 엔진이 살아 있지 않고 W(keeps_wallet) 참이면 마감 처리·1분 동기화가 표를 쓰지 않음.
       판정은 core.engine_control.alive_engine_threads(…_LIVE) → W(예외는 지킴). 운영 Reconciler 만 켬(guard_mock_wallet).
- G1-m 건너뛸 때 진입가 캐시만 0 (마감: 그 종목 · 1분 동기화: 캐시 > 0 이고 업비트 평단과 다른 종목) → 실계좌 기동 때 업비트 평단.
- G3 가 사람이 누르는 실계좌 시작만 막음(구버전 단추·신버전 요청). 자동 재개·start_engine 은 그대로.
- G4 keeps_wallet 설명 정정.
시험은 바깥 연결 없이(가짜 업비트·임시 DB).
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.regressions.test_r_2026_10_29_p4_t15_old_ui import _Base, USER  # noqa: E402


def _bal(avg="150", qty="3", krw="5555555"):
    return [{"currency": "KRW", "balance": krw, "locked": "0"},
            {"currency": "ZRO", "balance": qty, "locked": "0", "avg_buy_price": avg}]


class _FakeUpbit:
    def __init__(self, balances=None, exc=None):
        self.balances = balances or []
        self.exc = exc
        self.calls = 0

    def get_balances(self):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.balances


def _rec(balances=None, guard=True):
    from engine.order_reconciler import OrderReconciler
    r = OrderReconciler(_FakeUpbit(balances or _bal()), balance_sync_interval=0.0)
    r.guard_mock_wallet = guard
    return r


class _LiveThread:
    """이름이 run_live_loop_<user>_LIVE 인 살아 있는 스레드(실계좌 매매 루프 흉내)."""

    def __init__(self, user, mode="LIVE"):
        self.ev = threading.Event()
        self.th = threading.Thread(target=self.ev.wait, name=f"run_live_loop_{user}_{mode}", daemon=True)

    def __enter__(self):
        self.th.start()
        return self

    def __exit__(self, *a):
        self.ev.set()
        self.th.join(2)


def _w(value=True, exc=None):
    """W 판정 가짜: lock_state 호출 횟수를 센다."""
    ls = MagicMock(return_value={}) if exc is None else MagicMock(side_effect=exc)
    return (patch("ui.pullback_lock.lock_state", ls),
            patch("ui.pullback_lock.keeps_wallet", MagicMock(return_value=value)), ls)


# ============================================================ G1 판정
class TestG1Judgement(unittest.TestCase):
    def test_guard_off_is_current_behavior(self):
        r = _rec(guard=False)
        p1, p2, ls = _w(True)
        with p1, p2:
            self.assertFalse(r._keeps_mock_wallet("u1"))
        ls.assert_not_called()

    def test_default_is_off(self):
        from engine.order_reconciler import OrderReconciler
        self.assertFalse(OrderReconciler(_FakeUpbit()).guard_mock_wallet)

    def test_live_alive_no_w_call(self):
        r = _rec()
        p1, p2, ls = _w(True)
        with p1, p2, _LiveThread("u1"):
            self.assertFalse(r._keeps_mock_wallet("u1"))
        ls.assert_not_called()

    def test_test_thread_is_not_live(self):
        r = _rec()
        p1, p2, ls = _w(True)
        with p1, p2, _LiveThread("u1", mode="TEST"):
            self.assertTrue(r._keeps_mock_wallet("u1"))
        ls.assert_called_once()

    def test_other_user_live_thread_does_not_count(self):
        r = _rec()
        p1, p2, _ = _w(True)
        with p1, p2, _LiveThread("u2"):
            self.assertTrue(r._keeps_mock_wallet("u1"))

    def test_w_true_false(self):
        r = _rec()
        p1, p2, _ = _w(True)
        with p1, p2:
            self.assertTrue(r._keeps_mock_wallet("u1"))
        p1, p2, _ = _w(False)
        with p1, p2:
            self.assertFalse(r._keeps_mock_wallet("u1"))

    def test_w_exception_keeps(self):
        r = _rec()
        p1, p2, _ = _w(exc=RuntimeError("x"))
        with p1, p2:
            self.assertTrue(r._keeps_mock_wallet("u1"))

    def test_w_outside_reconciler_lock(self):
        r = _rec()
        seen = []
        with patch("ui.pullback_lock.lock_state", side_effect=lambda u: seen.append(r._lock.locked()) or {}), \
                patch("ui.pullback_lock.keeps_wallet", return_value=True):
            r._keeps_mock_wallet("u1")
        self.assertEqual(seen, [False])

    def test_import_does_not_load_engine_manager(self):
        """5-1: order_reconciler 를 불러와도 engine_manager 는 불러오지 않는다(순환 불러오기 없음)."""
        code = "import sys; import engine.order_reconciler; print('engine.engine_manager' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False", out.stderr[-2000:])

    def test_singleton_turns_guard_on(self):
        src = (ROOT / "engine" / "reconciler_singleton.py").read_text(encoding="utf-8")
        i = src.index("_reconciler = OrderReconciler(")
        j = src.index("_reconciler.guard_mock_wallet = True", i)
        k = src.index("_reconciler.start()", i)
        self.assertLess(j, k)

    def test_log_first_info_then_debug(self):
        r = _rec()
        with self.assertLogs("engine.order_reconciler", level="DEBUG") as cm:
            r._log_guard("u1", "sync")
            r._log_guard("u1", "sync")
            r._log_guard("u1", "finalize")
        lv = [(x.levelname, "where=sync" in x.getMessage()) for x in cm.records]
        self.assertEqual(lv, [("INFO", True), ("DEBUG", True), ("INFO", False)])
        self.assertIn("[OR] 모의 지갑 지킴 — 실계좌 잔고 반영 건너뜀 | user=u1 where=sync", cm.records[0].getMessage())


# ============================================================ G1 마감 처리
class TestG1Finalize(unittest.TestCase):
    def fin(self, r):
        self.acc, self.pos, self.audit = MagicMock(), MagicMock(), MagicMock()
        with patch("engine.order_reconciler.update_order_completed"), \
                patch("engine.order_reconciler.insert_trade_audit", self.audit), \
                patch("engine.order_reconciler.update_account_from_balances", self.acc), \
                patch("engine.order_reconciler.update_position_from_balances", self.pos), \
                patch.object(r, "_order_strategy_type", return_value="EMA"), \
                patch.object(r, "_clear_entry_price") as self.clr:
            r._finalize_order("uuid-1", "u1", "KRW-ZRO", "BUY", 1.0, 150.0, 0.1, "FILLED")

    def test_skip_when_no_live_engine_and_w(self):
        r = _rec()
        p1, p2, _ = _w(True)
        with p1, p2:
            self.fin(r)
        self.acc.assert_not_called()
        self.pos.assert_not_called()
        self.clr.assert_called_once_with("u1", "KRW-ZRO")
        self.audit.assert_called_once()               # 감사 기록은 그대로

    def test_live_engine_writes(self):
        r = _rec()
        p1, p2, ls = _w(True)
        with p1, p2, _LiveThread("u1"):
            self.fin(r)
        self.acc.assert_called_once()
        self.pos.assert_called_once()
        self.clr.assert_not_called()
        ls.assert_not_called()

    def test_w_false_writes(self):
        r = _rec()
        p1, p2, _ = _w(False)
        with p1, p2:
            self.fin(r)
        self.acc.assert_called_once()
        self.clr.assert_not_called()

    def test_guard_off_same_calls(self):
        r = _rec(guard=False)
        p1, p2, ls = _w(True)
        with p1, p2:
            self.fin(r)
        self.acc.assert_called_once()
        self.pos.assert_called_once()
        ls.assert_not_called()

    def test_w_exception_skips(self):
        r = _rec()
        p1, p2, _ = _w(exc=RuntimeError("db"))
        with p1, p2:
            self.fin(r)
        self.acc.assert_not_called()
        self.clr.assert_called_once()


# ============================================================ G1 1분 동기화
class TestG1Sync(unittest.TestCase):
    def sync(self, r):
        self.acc, self.pos, self.all = MagicMock(), MagicMock(), MagicMock()
        self.total = MagicMock(return_value=3.0)
        with patch("engine.order_reconciler.update_account_from_balances", self.acc), \
                patch("engine.order_reconciler.update_position_from_balances", self.pos), \
                patch("engine.order_reconciler.sync_all_positions_from_balances", self.all), \
                patch("services.db.get_position_total_qty", self.total), \
                patch.object(r, "_clear_changed_entry_prices") as self.clr:
            r._periodic_balance_sync()

    def test_w_true_skips_everything(self):
        r = _rec(_bal() + [{"currency": "JTO", "balance": "1", "locked": "0", "avg_buy_price": "9"}])
        r.register_user("u1")
        p1, p2, ls = _w(True)
        with p1, p2:
            self.sync(r)
        for m in (self.acc, self.pos, self.all, self.total):
            m.assert_not_called()                      # 원화·HTS 감지·포지션 모두
        self.clr.assert_called_once()
        self.assertEqual(ls.call_count, 1)             # 사용자당 W 1번(종목 2개여도)

    def test_enqueue_path_user_skipped(self):
        """F11: 엔진 없는 강제 매매로 enqueue 된 사용자도 지킴."""
        r = _rec()
        r.enqueue("uuid-9", user_id="u1", ticker="KRW-ZRO", side="BUY")
        p1, p2, _ = _w(True)
        with p1, p2:
            self.sync(r)
        self.acc.assert_not_called()

    def test_stopped_user_left_in_set_skipped(self):
        """F12: 정지 뒤 명단에 남은 사용자(엔진 스레드 없음) — 명단 정리는 하지 않고 건너뜀."""
        r = _rec()
        r.register_user("u1")
        p1, p2, _ = _w(True)
        with p1, p2:
            self.sync(r)
        self.assertIn("u1", r._live_user_ids)
        self.acc.assert_not_called()

    def test_live_alive_syncs_without_w(self):
        r = _rec()
        r.register_user("u1")
        p1, p2, ls = _w(True)
        with p1, p2, _LiveThread("u1"):
            self.sync(r)
        self.acc.assert_called_once()
        self.all.assert_called_once()
        ls.assert_not_called()

    def test_two_users_only_kept_one_skipped(self):
        r = _rec()
        r.register_user("u1")
        r.register_user("u2")
        with patch("ui.pullback_lock.lock_state", side_effect=lambda u: {"u": u}), \
                patch("ui.pullback_lock.keeps_wallet", side_effect=lambda st: st["u"] == "u1"):
            self.sync(r)
        self.assertEqual([c.args[0] for c in self.acc.call_args_list], ["u2"])

    def test_upbit_called_once(self):
        r = _rec()
        r.register_user("u1")
        p1, p2, _ = _w(True)
        with p1, p2:
            self.sync(r)
        self.assertEqual(r.upbit.calls, 1)


# ============================================================ G1-m 실제 DB
class TestG1mDb(_Base):
    def setUp(self):
        super().setUp()
        self.pullback(entry=0, qty=0.0)                # W 참(새 전략 켜짐) — 진짜 lock_state
        from services.db import update_coin_position, create_or_init_account
        create_or_init_account(USER, 1_000_000)
        update_coin_position(USER, "KRW-ZRO", 3.0, 0.0, entry_price=100.0)

    def ep(self, t="KRW-ZRO"):
        rows = self.sql("SELECT entry_price, virtual_coin FROM account_positions WHERE user_id=? AND ticker=?", (USER, t))
        return rows[0] if rows else None

    def hist(self):
        return self.sql("SELECT COUNT(*) FROM position_history")[0][0]

    def fin(self, r):
        with patch("engine.order_reconciler.update_order_completed"), \
                patch("engine.order_reconciler.insert_trade_audit"), \
                patch.object(r, "_order_strategy_type", return_value="EMA"):
            r._finalize_order("uuid-1", USER, "KRW-ZRO", "BUY", 1.0, 150.0, 0.1, "FILLED")

    def ps(self, balances, exc=None):
        from core.position_state import PositionState
        tr = SimpleNamespace(test_mode=False, user_id=USER, _coin_balance=lambda t: 3.0,
                             upbit=_FakeUpbit(balances, exc=exc))
        p = PositionState(tr, "KRW-ZRO")
        p.sync_from_wallet()
        return p

    def test_finalize_skip_clears_entry_only(self):
        from services.db import get_account
        h0, acc0 = self.hist(), get_account(USER)
        self.fin(_rec(_bal(avg="150", qty="9", krw="7777777")))
        ep, qty = self.ep()
        self.assertEqual(ep, 0)
        self.assertEqual(qty, 3.0)                     # 모의 수량 그대로
        self.assertEqual(get_account(USER), acc0)      # 모의 원화 그대로
        self.assertEqual(self.hist(), h0)              # position_history 행 추가 없음

    def test_then_live_start_uses_upbit_avg(self):
        self.fin(_rec())
        p = self.ps(_bal(avg="150"))
        self.assertEqual(p.avg_price, 150.0)           # 1순위 캐시(0) 건너뛰고 2순위 업비트 평단
        p2 = self.ps(_bal(avg="150"))                  # 프로세스 재시작 흉내(새 PositionState)
        self.assertEqual(p2.avg_price, 150.0)

    def test_without_clear_cache_wins(self):
        """대조: 캐시를 비우지 않으면 1순위 낡은 캐시(100)가 쓰인다 — G1-m 이 필요한 이유."""
        p = self.ps(_bal(avg="150"))
        self.assertEqual(p.avg_price, 100.0)

    def test_short_ticker_form_cleared(self):
        self.sql("UPDATE account_positions SET ticker='ZRO' WHERE user_id=?", (USER,))
        _rec()._clear_entry_price(USER, "KRW-ZRO")
        self.assertEqual(self.ep("ZRO")[0], 0)

    def test_sync_skip_clears_changed_avg_then_live_start(self):
        """건너뛰는 동안 업비트 앱 매수로 평단 100 → 120 → 캐시 0 → 실계좌 기동은 120."""
        r = _rec(_bal(avg="120"))
        r.register_user(USER)
        r._periodic_balance_sync()
        self.assertEqual(self.ep()[0], 0)
        self.assertEqual(self.ep()[1], 3.0)
        self.assertEqual(self.ps(_bal(avg="120")).avg_price, 120.0)

    def test_sync_skip_same_avg_no_write(self):
        r = _rec(_bal(avg="100.0000000000001"))       # 자릿수만 다름(상대 1e-9 안)
        r.register_user(USER)
        with patch.object(r, "_clear_entry_price") as clr:
            r._periodic_balance_sync()
        clr.assert_not_called()
        self.assertEqual(self.ep()[0], 100.0)

    def test_sync_skip_zero_or_no_row_no_write(self):
        self.sql("UPDATE account_positions SET entry_price=0 WHERE user_id=?", (USER,))
        r = _rec(_bal(avg="120") + [{"currency": "JTO", "balance": "1", "locked": "0", "avg_buy_price": "9"}])
        r.register_user(USER)
        with patch.object(r, "_clear_entry_price") as clr:
            r._periodic_balance_sync()
        clr.assert_not_called()

    def test_sync_cache_read_error_clears(self):
        from engine.order_reconciler import OrderReconciler
        r = _rec(_bal(avg="100"))
        r.register_user(USER)
        with patch.object(OrderReconciler, "_cached_entry_price", side_effect=sqlite3.OperationalError("x")), \
                patch.object(r, "_clear_entry_price") as clr:
            r._periodic_balance_sync()
        clr.assert_called_once_with(USER, "KRW-ZRO")

    def test_r7_cache_zero_and_upbit_fails_critical(self):
        self.fin(_rec())
        p = self.ps([], exc=RuntimeError("net"))
        self.assertIsNone(p.avg_price)
        self.assertTrue(any("avg_price 복구 실패" in str(c.args[1]) for c in self.notify.call_args_list))


# ============================================================ R1
class TestR1FirstSyncAfterSkip(_Base):
    def test_skipped_buy_then_live_first_sync_marks_hts_add(self):
        """R1: 건너뛴 강제 매수로 표는 모의 수량(3) — 실계좌 엔진이 켜진 뒤 첫 동기화는 증가(→5)를 앱 추가매수로 본다."""
        self.ema()
        from services.db import update_coin_position
        update_coin_position(USER, "KRW-ZRO", 3.0, 0.0, entry_price=10000.0)
        r = _rec(_bal(avg="10000", qty="5"))
        r.register_user(USER)
        mark = MagicMock()
        with _LiveThread(USER), patch("services.db.mark_position_as_hts_buy", mark), \
                patch("services.db.has_recent_bot_buy_for_ticker", return_value=False), \
                patch("engine.order_reconciler.insert_trade_audit"), \
                patch.object(r, "_engine_strategy_type", return_value="EMA"):
            r._periodic_balance_sync()
        mark.assert_called_once_with(USER, "KRW-ZRO")


# ============================================================ G3 신버전 요청
class _Mgr:
    def __init__(self, running=None):
        self.running = running
        self.starts = []

    def get_running_mode(self, user):
        return self.running

    def start_engine(self, user, mode=None):
        self.starts.append((user, mode))
        return False

    def last_start_reject(self, user, mode=None):
        return None


class TestG3Control(unittest.TestCase):
    def ctl(self, mgr):
        from engine import control_requests
        return control_requests.Controller(base_dir=ROOT / "nonexistent_1104_02_dir", manager=mgr,
                                           notify=lambda *a, **k: None)

    def test_live_reserved_rejected(self):
        m = _Mgr()
        with patch("ui.pullback_lock.live_start_reserved", return_value=True):
            r = self.ctl(m)._engine_start({"user_id": "u1", "mode": "LIVE"})
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_reserved"))
        self.assertEqual(m.starts, [])

    def test_live_read_error_rejected(self):
        import ui.pullback_lock as pl
        m = _Mgr()
        with patch.object(pl, "reservation_any_mode", side_effect=pl.ReservationReadError("x")):
            r = self.ctl(m)._engine_start({"user_id": "u1", "mode": "LIVE"})
        self.assertEqual(r["code"], "live_reserved")
        self.assertEqual(m.starts, [])

    def test_live_no_reservation_starts(self):
        m = _Mgr()
        with patch("ui.pullback_lock.reservation_any_mode", return_value=None):
            self.ctl(m)._engine_start({"user_id": "u1", "mode": "LIVE"})
        self.assertEqual(m.starts, [("u1", "LIVE")])

    def test_test_mode_not_checked(self):
        m = _Mgr()
        chk = MagicMock(return_value=True)
        with patch("ui.pullback_lock.live_start_reserved", chk):
            self.ctl(m)._engine_start({"user_id": "u1", "mode": "TEST"})
        self.assertEqual(m.starts, [("u1", "TEST")])
        chk.assert_not_called()

    def test_existing_codes_come_first(self):
        with patch("ui.pullback_lock.live_start_reserved", return_value=True):
            self.assertEqual(self.ctl(_Mgr("LIVE"))._engine_start({"user_id": "u1", "mode": "LIVE"})["code"],
                             "already_running")
            self.assertEqual(self.ctl(_Mgr("TEST"))._engine_start({"user_id": "u1", "mode": "LIVE"})["code"],
                             "mode_conflict")
            with _LiveThread("u1"):
                self.assertEqual(self.ctl(_Mgr())._engine_start({"user_id": "u1", "mode": "LIVE"})["code"],
                                 "old_engine_alive")

    def test_text_same_as_old_ui(self):
        from engine.control_requests import CODE_TEXT
        from ui.pullback_lock import LIVE_RESERVED_START_TEXT
        self.assertEqual(CODE_TEXT["live_reserved"], LIVE_RESERVED_START_TEXT)

    def test_reject_is_not_attempt(self):
        """시도가 아닌 거절 — 요청 횟수 제한·알림 묶음은 다른 거절과 같다."""
        from engine.control_requests import ATTEMPTED_CODES
        self.assertNotIn("live_reserved", ATTEMPTED_CODES)


class TestG3AutoResumeUnchanged(unittest.TestCase):
    def test_auto_paths_do_not_check(self):
        for rel in ("engine/boot_resume.py", "engine/engine_manager.py", "scripts/tradebot_boot.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("live_start_reserved", src, rel)
            self.assertNotIn("live_reserved", src, rel)

    def test_old_ui_auto_resume_block_unchanged(self):
        """구버전 화면 자동 재개는 예약을 보지 않는다(시작 단추 검사만 고침)."""
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("_pb_live_start_reserved("), 1)   # 호출 1 — 시작 단추 안에서만
        i = src.index("_pb_click_reserved = _pb_live_start_reserved(user_id)")
        j = src.index('key="btn_start_engine"')
        self.assertLess(j, i)


class TestG3Helper(unittest.TestCase):
    def test_live_start_reserved(self):
        import ui.pullback_lock as pl
        with patch.object(pl, "reservation_any_mode", return_value={"id": 1}):
            self.assertTrue(pl.live_start_reserved("u1"))
        with patch.object(pl, "reservation_any_mode", return_value=None):
            self.assertFalse(pl.live_start_reserved("u1"))
        with patch.object(pl, "reservation_any_mode", side_effect=RuntimeError("x")):
            self.assertTrue(pl.live_start_reserved("u1"))


# ============================================================ G4
class TestG4Docstring(unittest.TestCase):
    def test_keeps_wallet_doc(self):
        from ui.pullback_lock import keeps_wallet
        doc = keeps_wallet.__doc__
        self.assertIn("예약 중(읽기 실패 포함)이면 사람이 누르는 실계좌 시작은 막히나 자동 재개는 된다", doc)
        self.assertNotIn("이때 실계좌 엔진은 시작할 수 없다", doc)


if __name__ == "__main__":
    unittest.main()
