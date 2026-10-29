"""
2차 T12 (요청서 6절): 전략 전환·예약·복귀·예약 취소 — 엔진 쪽 시험.

사용자 결정 1029-03(「권고대로」)·PO 결정에 따른 구조를 고정한다(계획 T12 「구현 메모」):
- 예약 중 매수 차단 = 엔진 바깥 래퍼(engine/strategy_switch.install_buy_gate) — 모의(TEST) 엔진에만, 실계좌 엔진은 없음.
  막는 것 = 봇 자동 매수(execute BUY·WO-2 지연 매수 _execute_buy), 사용자 강제 매수는 허용.
- 예약 조회는 처음부터 mode 로 거름. 조회 실패·테이블 없음 규칙(계획 132행).
- D4 유지: LIVE switch 는 엔진 무접촉 거절, 다른 모드 엔진이 돌면 mode_conflict(restart_engine 앞).
- 흐름 5: 「지갑 0 + 미체결 봇 매수 없음(F8)」을 본 봉 다음 봉에 전환, 활성 파일 쓰기 직전 다시 확인.
- 기동 때 처리 중 행 복구: 기동 재개 완료 Event(tradebot_boot finally) 또는 60초 예비 규칙.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_29_p4_t12_switch -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import engine_control as ec  # noqa: E402
from core import strategy_engine as se  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from engine import params as eparams  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from engine import strategy_switch as ss  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    CFG, DIP, EngineCase, FakeTrader, TICKER, USER, bar,
)
from tests.regressions.test_r_2026_10_28_p4_t11_control import FakeClock, FakeMgr, FakeThread  # noqa: E402

EMA_TICKER = "KRW-JTO"
EMA_IV = "minute3"
REAL_PENDING_BUY = ss._pending_buy      # SwitchCase 가 바꾸기 전 원본(fix round 1 항목 5 시험용)
REAL_WALLET_QTY = ss._wallet_qty


# ================================================================ 도우미
class SwitchMgr(FakeMgr):
    """정지하면 엔진 스레드가 끝나고, 시작하면 준비 신호를 세운다(fail 에 든 전략은 세우지 않음)."""

    def __init__(self, clock):
        super().__init__(clock)
        self.fail = set()

    def start_engine(self, u, *, mode, strategy=None):
        ok = super().start_engine(u, mode=mode, strategy=strategy)
        ev = threading.Event()
        if strategy not in self.fail:
            ev.set()
        self._ready[u] = ev
        return ok

    def stop_engine(self, u, *, mode=None):
        th = self._threads.get(u)
        if th is not None:
            th.dies_at = self.clock.t
        super().stop_engine(u, mode=mode)


class FakeEng:
    """감시 스레드 보유 확인용 엔진 대역(제어 큐는 attach 가 붙임)."""

    def __init__(self, strategy_type="EMA"):
        self.user_id, self.ticker, self.strategy_type = USER, EMA_TICKER, strategy_type
        self.trader = SimpleNamespace(test_mode=True)
        self.position = SimpleNamespace(has_position=False, pending_order=False)
        self.last_bar_ts = "bar-A"
        self._pending_split = None
        self._pending_orders = None

    def execute(self, *a, **k):
        return None

    def _execute_buy(self, *a, **k):
        return None


class SwitchCase(EngineCase):
    """임시 폴더(cwd — 활성 파일·저장본·적용본)·임시 DB(strategy_switch 포함)·가짜 시계·가짜 관리자."""

    def setUp(self):
        super().setUp()
        self._cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self._cwd)
        self.db_path = os.path.join(self.tmp.name, f"tradebot_{USER}.db")
        for target in ("services.init_db.get_db_path", "services.db.get_db_path"):
            p = mock.patch(target, return_value=self.db_path)
            p.start()
            self.addCleanup(p.stop)
        import services.init_db as idb
        idb.initialize_db(USER)
        idb.ensure_all_schemas(USER)
        ss._TABLE_ALERTED.clear()
        ec._RUNNING.clear()
        self.addCleanup(ec._RUNNING.clear)
        ec.BOOT_RESUME_DONE.clear()
        self.addCleanup(ec.BOOT_RESUME_DONE.clear)
        # 지갑·미체결 매수(F8)·logs — 시험 값
        self.wallet, self.pending, self.logs = 0.0, False, []
        self.wallet_reads = 0

        def wallet(u, t, tr):
            self.wallet_reads += 1
            return self.wallet() if callable(self.wallet) else self.wallet
        for name, fn in (("_wallet_qty", wallet), ("_pending_buy", lambda u, t: self.pending),
                         ("_insert_log", lambda u, lvl, msg: self.logs.append((lvl, msg)))):
            p = mock.patch.object(ss, name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)
        self.ema_ti = (EMA_TICKER, EMA_IV)
        real_ti = ss.strategy_ticker_interval
        p = mock.patch.object(ss, "strategy_ticker_interval",
                              side_effect=lambda u, s: real_ti(u, s) if s == "PULLBACK" else self.ema_ti)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(cr, "_ticker_and_interval", return_value=(EMA_TICKER, 180))  # 엔진 없는 강제 매매
        p.start()
        self.addCleanup(p.stop)
        # 저장본(새 전략)·활성 파일 EMA
        self.write_saved(CFG)
        eparams.save_active_strategy(USER, "EMA")
        self.clock = FakeClock()
        self.mgr = SwitchMgr(self.clock)
        self.ctl_notify = mock.MagicMock(return_value=True)
        base = Path(self.tmp.name) / "v2_control"
        base.mkdir(mode=0o700)
        os.chmod(base, 0o700)
        self.base = base
        self.ctl = cr.Controller(base_dir=base, alive_dir=Path(self.tmp.name), manager=self.mgr,
                                 notify=self.ctl_notify, now=self.clock.now, monotonic=self.clock.mono,
                                 sleep=self.clock.sleep, start_check=0.0,
                                 trader_factory=lambda u, m, s: SimpleNamespace(test_mode=(m == "TEST")),
                                 force_buy_fn=lambda u, trader, ticker, **k: "[TEST] 강제 매수 완료",
                                 force_sell_fn=lambda u, trader, ticker, **k: "[TEST] 강제 매도 완료")
        for p in (mock.patch.dict(cr._EXTRA_HANDLERS, {"switch": ss.handle_switch, "revert": ss.handle_revert,
                                                       "cancel_reservation": ss.handle_cancel}),
                  mock.patch.object(cr, "_POST_HOOKS", [ss.post_force_buy]),
                  mock.patch.object(cr, "_TICK_HOOKS", [])):
            p.start()
            self.addCleanup(p.stop)
        self._n = 0

    # ------------------------------------------------------------ 파일·요청
    def write_saved(self, d):
        Path(pbp.saved_path(USER)).write_text(json.dumps(d), encoding="utf-8")
        self.sha = pbp.sha256_of(pbp.saved_path(USER))

    def run_engine(self, strategy_type="EMA"):
        """엔진이 TEST 로 도는 상태: 대역 엔진을 attach 하고 가짜 시계가 잘 때마다 엔진 스레드처럼 제어 큐를 비운다."""
        self.eng = FakeEng(strategy_type)
        ec.attach(self.eng, USER, threading.Event())
        self.mgr.mode = "TEST"
        self.mgr._threads[USER] = FakeThread(self.clock, None)
        self.clock.hooks.append(lambda t: ec.drain_control_queue(self.eng))
        return self.eng

    def req(self, kind, mode="TEST", payload=None):
        self._n += 1
        return {"id": "20261029000000-%08x" % self._n, "user_id": USER, "mode": mode, "kind": kind,
                "payload": dict(payload or {})}

    def switch(self, mode="TEST", sha=None):
        return self.ctl.execute(self.req("switch", mode, {"saved_sha256": sha or self.sha}))

    def rows(self, kind=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            q = "SELECT * FROM strategy_switch" + (" WHERE kind=?" if kind else "") + " ORDER BY id"
            return [dict(r) for r in conn.execute(q, (kind,) if kind else ())]
        finally:
            conn.close()

    def add_row(self, **kw):
        d = dict(mode="TEST", kind="SWITCH", from_strategy="EMA", to_strategy="PULLBACK", from_ticker=EMA_TICKER,
                 from_interval=EMA_IV, to_ticker=TICKER, to_interval="minute3", params_sha256=self.sha,
                 state="RESERVED", note=None)
        d.update(kw)
        return ss.insert_row(USER, **d)

    def active(self):
        return eparams.load_active_strategy(USER, include_engine_only=True)

    def starts(self, strategy=None):
        return [c for c in self.mgr.calls if c[0] == "start" and (strategy is None or c[3] == strategy)]

    def bodies(self, level=None):
        return [c.args[2] for c in self.ctl_notify.call_args_list if level is None or c.args[0] == level]

    def audit_count(self):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM audit_trades").fetchone()[0]
        finally:
            conn.close()

    # ------------------------------------------------------------ 엔진(실제 StrategyEngine)
    def ema_engine(self, trader=None):
        eng = self.make(trader=trader or FakeTrader(), strategy_type="EMA")
        eng.strategy = SimpleNamespace(last_buy_reason="EMA_GC", buy_conditions={}, last_weak_entry=None,
                                       on_bar=lambda *a, **k: Action.BUY)
        eng._log_bar_evaluation = lambda *a, **k: None    # 로그 문자열만(시드 전 EMA 값 None 형식화) — 판정·주문 무관
        return eng


def tick(case, n=1):
    mon = getattr(case, "_mon", None) or ss.Monitor()
    case._mon = mon
    out = []
    for _ in range(n):
        mon.boot_done = True
        out.append([mon.check_user(case.ctl, u) for u in mon._running_users()])
    return out


# ================================================================ 1. 매수 차단 래퍼
class TestBuyGate(SwitchCase):
    def test_wrapper_absent_on_live(self):
        """실계좌 엔진: attach 해도 execute·_execute_buy 는 클래스 함수 그대로(인스턴스 속성 없음)."""
        eng = self.ema_engine(FakeTrader(test_mode=False))
        ec.attach(eng, USER, threading.Event())
        self.assertNotIn("execute", eng.__dict__)
        self.assertNotIn("_execute_buy", eng.__dict__)
        self.assertIs(eng.execute.__func__, se.StrategyEngine.execute)
        self.assertIs(eng._execute_buy.__func__, se.StrategyEngine._execute_buy)
        self.assertFalse(ss.install_buy_gate(eng, USER))
        # LIVE 는 예약이 있어도(있을 수 없지만) 막지 않음 — 조회 자체를 하지 않는다
        self.add_row(mode="LIVE")
        with mock.patch.object(ss, "reservation", side_effect=AssertionError("LIVE 는 조회 안 함")):
            eng.execute(Action.BUY, bar(1), {"ema_fast": 1, "ema_slow": 2})
        self.assertEqual(len(eng.trader.buy_calls), 1)

    def test_wrapper_present_on_test(self):
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        self.assertIn("execute", eng.__dict__)
        self.assertIn("_execute_buy", eng.__dict__)
        self.assertTrue(eng._switch_gate_installed)

    def test_reserved_blocks_bot_buys(self):
        """예약 중 EMA 골든크로스(on_new_bar → execute) → 주문 0, 감사 switch_reserved. 매도는 계속."""
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        self.add_row()
        eng.on_new_bar(bar(1))
        self.assertEqual(eng.trader.buy_calls, [])
        self.assertEqual([r["code"] for r in eng.trader.rejects], ["switch_reserved"])
        # 매도 경로는 래퍼가 건드리지 않음
        eng.position.open_position(1.0, 55.0, 0, bar(0).ts)
        eng.trader.coin = 1.0
        eng.execute(Action.SELL, bar(2), {"ema_fast": 1, "ema_slow": 2})
        self.assertEqual(len(eng.trader.sell_calls), 1)

    def test_reserved_blocks_wo2_delayed_buy(self):
        """WO-2 지연 매수 재판정(_resolve_pending_buy → _execute_buy, execute 밖)도 예약 중이면 주문 0."""
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        eng.buffer.append(bar(0))
        pending = SimpleNamespace(bar_ts=bar(0).ts, is_expired=lambda now: False, revalidate=lambda c: True,
                                  context={})
        eng._pending_orders = mock.MagicMock(current=pending)
        self.add_row()
        eng._resolve_pending_buy(bar(1))
        self.assertEqual(eng.trader.buy_calls, [])
        self.assertIn("switch_reserved", [r["code"] for r in eng.trader.rejects])
        # 예약이 없으면 같은 경로로 매수 1
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE strategy_switch SET state='CANCELED'")
        conn.commit()
        conn.close()
        eng._resolve_pending_buy(bar(1))
        self.assertEqual(len(eng.trader.buy_calls), 1)

    def test_reserved_blocks_pullback_round_buy(self):
        """복귀 예약 중 PULLBACK 회차 매수(눌림 신호)도 주문 0, 회차 되돌림."""
        eng = self.make(values=[V()] * 40)
        ec.attach(eng, USER, threading.Event())
        self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        self.assertEqual(self.strat.entry_count, 0)
        self.assertIn("switch_reserved", [r["code"] for r in self.trader.rejects])

    def test_no_reservation_ema_buy_unchanged(self):
        """예약 없음 → EMA 골든크로스 매수 지금과 같음(래퍼 없는 엔진과 같은 주문)."""
        base = self.ema_engine()
        base.on_new_bar(bar(1))
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        eng.on_new_bar(bar(1))
        self.assertEqual(len(eng.trader.buy_calls), 1)
        self.assertEqual(eng.trader.buy_calls, base.trader.buy_calls)

    def test_no_reservation_test_trace_equals_base(self):
        """예약 없음: 래퍼를 붙인 모의 엔진과 붙이지 않은 엔진의 trader 호출 흔적이 같다(매수·지연 매수·매도·거절)."""
        def run(gated):
            eng = self.ema_engine()
            if gated:
                ec.attach(eng, USER, threading.Event())
                self.assertIn("execute", eng.__dict__)
            eng.on_new_bar(bar(1))                                   # 골든크로스 매수
            eng.on_new_bar(bar(2))                                   # 보유 중 → already_holding
            eng.trader.coin = eng.position.qty
            eng.execute(Action.SELL, bar(3), {"ema_fast": 1, "ema_slow": 2})
            eng.buffer.append(bar(3))
            eng._pending_orders = mock.MagicMock(current=SimpleNamespace(
                bar_ts=bar(3).ts, is_expired=lambda now: False, revalidate=lambda c: True, context={}))
            eng._resolve_pending_buy(bar(4))                         # WO-2 지연 매수
            t = eng.trader
            strip = lambda calls: [{k: v for k, v in c.items() if k != "ts"} for c in calls]  # noqa: E731
            return strip(t.buy_calls), strip(t.sell_calls), [r["code"] for r in t.rejects]
        self.assertEqual(run(True), run(False))

    def test_mode_filtered_lookup(self):
        """예약 조회는 mode 로 거름: LIVE 행은 TEST 엔진을 막지 않고, TEST 행은 LIVE 조회에 안 보임."""
        self.add_row(mode="LIVE")
        self.assertIsNone(ss.reservation(USER, "TEST"))
        self.assertEqual(ss.gate_decision(USER, "TEST", "EMA"), (False, None))
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        eng.on_new_bar(bar(1))
        self.assertEqual(len(eng.trader.buy_calls), 1)
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM strategy_switch")
        conn.commit()
        conn.close()
        self.add_row(mode="TEST")
        self.assertIsNone(ss.reservation(USER, "LIVE"))
        self.assertIsNotNone(ss.reservation(USER, "TEST"))

    def test_params_rows_ignored_by_reservation(self):
        self.add_row(kind="PARAMS", from_strategy="PULLBACK", to_strategy="PULLBACK", state="DONE")
        self.add_row(kind="PARAMS", from_strategy="PULLBACK", to_strategy="PULLBACK", state="RESERVED")
        self.assertIsNone(ss.reservation(USER, "TEST"))
        self.assertEqual(ss.gate_decision(USER, "TEST", "EMA"), (False, None))

    def test_reservation_read_failure_blocks_buy_only(self):
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        with mock.patch.object(ss, "reservation", side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertLogs("engine.strategy_switch", "WARNING") as cm:
                eng.on_new_bar(bar(1))
            self.assertEqual(eng.trader.buy_calls, [])
            self.assertEqual([r["code"] for r in eng.trader.rejects], ["switch_state_unknown"])
            self.assertTrue(any("[SWITCH-STATE] read failed" in m for m in cm.output))
            eng.position.open_position(1.0, 55.0, 0, bar(0).ts)
            eng.trader.coin = 1.0
            eng.execute(Action.SELL, bar(2), {"ema_fast": 1, "ema_slow": 2})
            self.assertEqual(len(eng.trader.sell_calls), 1)

    def test_switch_table_missing_ema_buys_and_alerts(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP TABLE strategy_switch")
        conn.commit()
        conn.close()
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        eng.on_new_bar(bar(1))
        self.assertEqual(len(eng.trader.buy_calls), 1)
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL" and "테이블 없음" in c.args[1]]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0].kwargs.get("audience"), "operator")          # 운영자 전용(항목 8)
        self.assertEqual(crit[0].kwargs.get("dedupe_key"), f"switch_table_missing:{USER}")
        # 같은 날 두 번째 매수 시도 → CRITICAL 다시 안 보냄(1시간 dedupe)
        eng.position.close_position(ts=None, reason="test")
        eng.trader.coin = 0.0
        eng.on_new_bar(bar(2))
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL" and "테이블 없음" in c.args[1]]
        self.assertEqual(len(crit), 1)
        self.assertEqual(len(eng.trader.buy_calls), 2)
        # 테이블 없음 + 활성 PULLBACK → 매수 차단
        self.assertEqual(ss.gate_decision(USER, "TEST", "PULLBACK"), (True, "switch_state_unknown"))

    def test_force_buy_allowed_during_reservation(self):
        """결정 3: 예약 중 사용자 강제 매수는 허용 — PULLBACK 엔진 강제 매수(_pullback_force_buy)는 래퍼를 지나지 않는다."""
        eng = self.make(values=[V()] * 40)
        self.feed(bar(0))
        ec.attach(eng, USER, threading.Event())
        self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        r = eng._pullback_force_buy()
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual(self.trader.buy_calls[0]["meta"]["reason"], "FORCE")
        # 구버전·엔진 없는 강제 매수(services.trading_control.force_buy_in)는 엔진 execute·_execute_buy 를 부르지 않는다
        src = (ROOT / "services" / "trading_control.py").read_text(encoding="utf-8")
        self.assertNotIn(".execute(", src)
        self.assertNotIn("_execute_buy(", src)
        self.assertIsNotNone(ss.reservation(USER, "TEST"))          # 예약 유지

    def test_force_buy_result_keeps_reservation_message(self):
        """신버전 강제 매수(엔진 없음 경로) 결과 문구에 「예약 그대로」 1회, 예약 행 그대로, 알림 1회."""
        self.add_row()
        d = self.base / USER
        d.mkdir(mode=0o700)
        os.chmod(d, 0o700)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        rid = "20261029000000-000000ff"
        body = {"v": 1, "id": rid, "user_id": USER, "mode": "TEST", "kind": "force_buy", "payload": {},
                "created_at": datetime.fromtimestamp(self.clock.t, kst).isoformat(),
                "expires_at": datetime.fromtimestamp(self.clock.t + 60, kst).isoformat()}
        (d / f"req-{rid}.json").write_text(json.dumps(body), encoding="utf-8")
        self.ctl.scan_once()
        res = json.loads((d / f"res-{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(res["status"], "done")
        self.assertIn(ss.RESERVATION_KEPT_TEXT, res["message"])
        self.assertEqual(self.ctl_notify.call_count, 1)
        self.assertIn(ss.RESERVATION_KEPT_TEXT, self.ctl_notify.call_args.args[2])
        self.assertEqual([r["state"] for r in self.rows()], ["RESERVED"])


# ================================================================ 2. 요청: 전환·예약·LIVE·mode_conflict
class TestSwitchRequest(SwitchCase):
    def test_switch_request_flat_immediate(self):
        r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(self.active(), "PULLBACK")
        self.assertEqual(pbp.sha256_of(pbp.applied_path(USER)), self.sha)
        self.assertEqual(len(self.starts("PULLBACK")), 1)
        rows = self.rows()
        self.assertEqual([(x["kind"], x["state"]) for x in rows], [("SWITCH", "DONE")])
        self.assertEqual((rows[0]["from_strategy"], rows[0]["from_ticker"], rows[0]["from_interval"]),
                         ("EMA", EMA_TICKER, EMA_IV))
        self.assertTrue(rows[0]["requested_at"].endswith("+09:00"))
        self.assertTrue(rows[0]["done_at"].endswith("+09:00"))

    def test_logs_switch_done_line(self):
        self.switch()
        self.assertTrue(any("전략 전환 완료 → 눌림목 분할매수" in m for _, m in self.logs), self.logs)

    def test_switch_reserved_while_holding(self):
        self.wallet = 3.0
        r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("done", "reserved"))
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.starts(), [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])
        self.assertFalse(os.path.exists(pbp.applied_path(USER)))

    def test_switch_rejects_sha_mismatch(self):
        r = self.switch(sha="0" * 64)
        self.assertEqual((r["status"], r["code"]), ("rejected", "sha_mismatch"))
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])

    def test_switch_rejects_saved_invalid(self):
        Path(pbp.saved_path(USER)).write_text("", encoding="utf-8")
        r = self.switch(sha="a" * 64)
        self.assertEqual(r["code"], "saved_invalid")
        self.assertEqual(self.mgr.calls, [])

    def test_live_switch_rejected_without_engine_touch(self):
        self.mgr.mode = "LIVE"
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_supported"))
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.ctl.execute(self.req("revert", "LIVE"))["code"], "live_not_supported")
        self.assertEqual(self.mgr.calls, [])

    def test_mode_conflict_rejected(self):
        """다른 모드(LIVE) 엔진이 돌면 TEST 전환·복귀는 restart_engine 전에 mode_conflict — 엔진 무접촉."""
        self.mgr.mode = "LIVE"
        r = self.switch(mode="TEST")
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"))
        self.assertEqual(r["detail"]["running"], "LIVE")
        eparams.save_active_strategy(USER, "PULLBACK")
        self.assertEqual(self.ctl.execute(self.req("revert"))["code"], "mode_conflict")
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.rows(), [])

    def test_switch_with_open_buy_order(self):
        """미보유 + 미체결 봇 지정가 BUY(F8) → 예약. 체결되면 보유 관리(전환 없음), 취소되면 다음 봉 전환."""
        self.run_engine()
        self.pending = True
        r = self.switch()
        self.assertEqual(r["code"], "reserved")
        # 체결: 지갑 > 0 → 여러 봉 지나도 전환 없음
        self.pending, self.wallet = False, 2.0
        for b in ("bar-B", "bar-C"):
            self.eng.last_bar_ts = b
            tick(self)
        self.assertEqual(self.starts(), [])
        # 매도·취소 뒤 지갑 0: 본 봉 → 다음 봉에서 전환
        self.wallet = 0.0
        self.eng.last_bar_ts = "bar-D"
        self.assertEqual(tick(self), [["flat_seen"]])
        self.eng.last_bar_ts = "bar-E"
        self.assertEqual(tick(self), [["ok"]])
        self.assertEqual(self.active(), "PULLBACK")
        self.assertEqual(len(self.starts("PULLBACK")), 1)

    def test_switch_open_buy_order_engine_stopped(self):
        """엔진이 멈춘 때도(엔진 없는 보유 판정) 미체결 봇 매수(F8)가 있으면 즉시 전환하지 않고 예약."""
        self.pending = True
        r = self.switch()
        self.assertEqual(r["code"], "reserved")
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])

    def test_switch_start_failure_rolls_back(self):
        """PULLBACK 기동 실패(준비 안 됨) → 행 FAILED, 활성 파일 EMA, EMA 재기동 1회, CRITICAL 1."""
        self.run_engine()
        self.mgr.fail.add("PULLBACK")
        r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("error", "switch_failed"))
        self.assertEqual([x["state"] for x in self.rows()], ["FAILED"])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(len(self.starts("EMA")), 1)
        self.assertEqual(len(self.bodies("CRITICAL")), 1)

    def test_switch_done_only_after_ready(self):
        """_ready 를 세우지 않는 엔진 → DONE 0, FAILED 1, 활성 파일 EMA 로 되돌림."""
        self.mgr.fail.add("PULLBACK")
        self.switch()
        states = [x["state"] for x in self.rows()]
        self.assertEqual(states.count("DONE"), 0)
        self.assertEqual(states.count("FAILED"), 1)
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.starts("EMA"), [])     # 전환 전에 엔진이 없었으면 직전 전략을 새로 띄우지 않음

    def test_recheck_before_active_file_write(self):
        """활성 파일 쓰기 직전 재확인: 첫 확인 뒤 매수가 끼어들면(지갑 > 0) 예약 유지, 활성 파일·엔진 그대로."""
        seq = iter([0.0, 5.0])
        self.wallet = lambda: next(seq, 5.0)
        r = self.switch()
        self.assertEqual(r["code"], "reserved")
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.wallet_reads, 2)

    def test_already_reserved_and_already_pullback(self):
        self.wallet = 1.0
        self.switch()
        self.assertEqual(self.switch()["code"], "already_reserved")
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE strategy_switch SET state='CANCELED'")
        conn.commit()
        conn.close()
        eparams.save_active_strategy(USER, "PULLBACK")
        self.assertEqual(self.switch()["code"], "already_pullback")

    def test_switch_events_notify_no_action_needed(self):
        for k, v in ss.TEXT.items():
            self.assertTrue(v.endswith(ss.NO_ACTION_TEXT), k)
        self.switch()                                    # 즉시 전환
        self.wallet = 1.0
        eparams.save_active_strategy(USER, "EMA")
        self.switch()                                    # 예약
        self.ctl.execute(self.req("cancel_reservation"))  # 취소
        bodies = self.bodies()
        self.assertEqual(len(bodies), 3)
        for b in bodies:
            self.assertIn(ss.NO_ACTION_TEXT, b)
        # 요청에서 생긴 전환 사건은 S1 줄(모르는 요청이면 알려 달라)을 사건 문구 뒤에
        self.assertTrue(bodies[0].endswith(ss.UNKNOWN_REQUEST_TEXT))
        self.assertTrue(bodies[2].endswith(ss.NO_ACTION_TEXT))

    def test_switch_request_file_one_notify(self):
        """요청 파일 경로(scan_once): 전환 사건 알림 1회만(요청 알림은 사건 알림으로 갈음), 결과 파일 done/ok."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        d = self.base / USER
        d.mkdir(mode=0o700)
        os.chmod(d, 0o700)
        rid = "20261029000000-000000aa"
        body = {"v": 1, "id": rid, "user_id": USER, "mode": "TEST", "kind": "switch",
                "payload": {"saved_sha256": self.sha},
                "created_at": datetime.fromtimestamp(self.clock.t, kst).isoformat(),
                "expires_at": datetime.fromtimestamp(self.clock.t + 60, kst).isoformat()}
        (d / f"req-{rid}.json").write_text(json.dumps(body), encoding="utf-8")
        self.ctl.scan_once()
        res = json.loads((d / f"res-{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual((res["status"], res["code"]), ("done", "ok"))
        self.assertEqual(self.ctl_notify.call_count, 1)
        self.assertIn("전략 전환 완료", self.ctl_notify.call_args.args[2])

    def test_switch_events_not_in_pnl(self):
        before = self.audit_count()
        self.switch()
        self.wallet = 1.0
        eparams.save_active_strategy(USER, "EMA")
        self.switch()
        self.ctl.execute(self.req("cancel_reservation"))
        self.assertEqual(self.audit_count(), before)


# ================================================================ 3. 예약 → 매도 완료 → 다음 봉 전환
class TestReservedCompletion(SwitchCase):
    def reserve(self):
        self.run_engine()
        self.wallet = 4.0
        self.eng.position.has_position = True
        r = self.switch()
        self.assertEqual(r["code"], "reserved")
        return self.rows()[0]["id"]

    def flat_after(self, *, has_position=False):
        self.wallet = 0.0
        self.eng.position.has_position = has_position

    def test_reserved_switch_on_next_bar_after_flat(self):
        self.reserve()
        self.flat_after()
        self.assertEqual(tick(self), [["flat_seen"]])
        self.assertEqual(tick(self), [["wait_next_bar"]])    # 같은 봉 — 아직
        self.assertEqual(self.starts(), [])
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])
        self.assertEqual(self.active(), "PULLBACK")
        self.assertEqual([x["state"] for x in self.rows()], ["DONE"])
        self.assertTrue(any("전환 예약 완료" in b for b in self.bodies()))

    def test_flat_by_engine_sell(self):
        self.reserve()
        self.flat_after()
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])

    def test_flat_by_v2_force_sell(self):
        self.reserve()
        self.mgr.mode = None                                 # 신버전 강제 매도(엔진 밖 경로 — 엔진 안 경로는 T11 시험)
        r = self.ctl.execute(self.req("force_sell"))
        self.mgr.mode = "TEST"
        self.assertEqual(r["status"], "done")
        self.flat_after()
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])

    def test_flat_by_old_force_sell(self):
        self.reserve()
        self.flat_after()                                    # 구버전 force_liquidate 뒤 지갑 0
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])

    def test_flat_by_app_sell(self):
        """앱 매도: 지갑 0 이지만 엔진 포지션은 다음 봉 지갑 대조 전까지 보유 → 그 뒤 봉에서 본 뒤 다음 봉 전환."""
        self.reserve()
        self.flat_after(has_position=True)
        self.assertEqual(tick(self), [["holding"]])
        self.eng.position.has_position = False              # 다음 봉 _reconcile_position_with_wallet
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["flat_seen"]])
        self.eng.last_bar_ts = "bar-C"
        self.assertEqual(tick(self), [["ok"]])

    def test_partial_sell_keeps_reservation(self):
        self.reserve()
        self.wallet = 1.5
        for b in ("bar-B", "bar-C", "bar-D"):
            self.eng.last_bar_ts = b
            self.assertEqual(tick(self), [["holding"]])
        self.assertEqual([x["state"] for x in self.rows()], ["RESERVED"])
        self.assertEqual(self.starts(), [])

    def test_sell_reject_repeat_keeps_reservation_and_notifies(self):
        self.reserve()
        tick(self)                                           # 기준 id 기록
        conn = sqlite3.connect(self.db_path)
        for _ in range(2):
            conn.execute("INSERT INTO audit_trades (ticker, interval_sec, bar, type, reason, price) "
                         "VALUES (?, 180, 1, 'SELL_REJECTED', 'STOP_LOSS', 50.0)", (EMA_TICKER,))
        conn.commit()
        conn.close()
        tick(self, 3)
        notes = [b for b in self.bodies("WARNING") if ss.SELL_REJECT_TEXT in b]
        self.assertEqual(len(notes), 1)
        self.assertEqual([x["state"] for x in self.rows()], ["RESERVED"])

    def test_f8_pending_buy_keeps_reservation(self):
        """흐름 5: 지갑 0 이어도 미체결 봇 매수(has_pending_bot_limit_buy)가 있으면 예약 유지."""
        self.reserve()
        self.flat_after()
        self.pending = True
        for b in ("bar-B", "bar-C"):
            self.eng.last_bar_ts = b
            self.assertEqual(tick(self), [["holding"]])
        self.assertEqual(self.starts(), [])
        self.pending = False
        self.eng.last_bar_ts = "bar-D"
        tick(self)
        self.eng.last_bar_ts = "bar-E"
        self.assertEqual(tick(self), [["ok"]])

    def test_recheck_before_file_write_in_monitor(self):
        """감시 스레드: 다음 봉 판정 뒤 활성 파일 쓰기 직전 재확인에서 매수가 보이면 예약 유지."""
        self.reserve()
        self.flat_after()
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        calls = {"n": 0}

        def w():
            calls["n"] += 1
            return 0.0 if calls["n"] == 1 else 2.0          # 판정 때 0, 쓰기 직전 2(강제 매수 끼어듦)
        self.wallet = w
        self.assertEqual(tick(self), [["reserved"]])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])
        self.assertEqual(self.starts(), [])

    def test_reservation_survives_restart(self):
        """예약은 DB 에 있다: 새 엔진(재시작 뒤)의 래퍼도 막고, 새 감시(Monitor)도 이어서 전환한다."""
        self.reserve()
        eng2 = self.ema_engine()
        ec.attach(eng2, USER, threading.Event())
        eng2.on_new_bar(bar(1))
        self.assertEqual(eng2.trader.buy_calls, [])
        ec.attach(self.eng, USER, threading.Event())
        self._mon = ss.Monitor()
        self.flat_after()
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])

    def test_cancel_reservation(self):
        self.reserve()
        r = self.ctl.execute(self.req("cancel_reservation"))
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))
        self.assertEqual([x["state"] for x in self.rows()], ["CANCELED"])
        self.assertIsNone(ss.reservation(USER, "TEST"))
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        eng.on_new_bar(bar(1))
        self.assertEqual(len(eng.trader.buy_calls), 1)      # 매수 차단 해제
        self.assertEqual(self.ctl.execute(self.req("cancel_reservation"))["code"], "no_reservation")

    def test_saved_changed_during_reservation(self):
        self.reserve()
        d = dict(CFG)
        d["tp"] = 4
        self.write_saved(d)
        self.flat_after()
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["saved_changed"]])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual([x["state"] for x in self.rows()], ["FAILED"])


# ================================================================ 4. 복귀
class TestRevert(SwitchCase):
    def pullback_active(self, *, with_record=True):
        if with_record:
            self.add_row(state="DONE")
        pbp.apply_saved(USER, self.sha)
        eparams.save_active_strategy(USER, "PULLBACK")

    def test_revert_to_previous(self):
        self.pullback_active()
        r = self.ctl.execute(self.req("revert"))
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(len(self.starts("EMA")), 1)
        rv = self.rows("REVERT")[0]
        self.assertEqual((rv["state"], rv["to_strategy"], rv["to_ticker"], rv["to_interval"]),
                         ("DONE", "EMA", EMA_TICKER, EMA_IV))
        self.assertTrue(any("기존 전략으로 복귀 → EMA (KRW-JTO · 3분봉)" in b for b in self.bodies()))

    def test_revert_to_previous_macd(self):
        self.add_row(state="DONE", from_strategy="MACD")
        pbp.apply_saved(USER, self.sha)
        eparams.save_active_strategy(USER, "PULLBACK")
        r = self.ctl.execute(self.req("revert"))
        self.assertEqual(r["code"], "ok")
        self.assertEqual(self.active(), "MACD")
        self.assertEqual(len(self.starts("MACD")), 1)

    def test_revert_without_record_requires_choice(self):
        self.pullback_active(with_record=False)
        r = self.ctl.execute(self.req("revert"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "choose_strategy"))
        self.assertEqual(self.mgr.calls, [])
        r = self.ctl.execute(self.req("revert", payload={"strategy": "MACD"}))
        self.assertEqual(r["code"], "ok")
        self.assertEqual(self.active(), "MACD")

    def test_revert_not_pullback(self):
        self.assertEqual(self.ctl.execute(self.req("revert"))["code"], "not_pullback")

    def test_revert_reserved_uses_pullback_exit_rules(self):
        """PULLBACK 보유 중 복귀 예약 → 눌림 신호 주문 0, TP 매도 1, 다음 봉 복귀."""
        self.pullback_active()
        self.run_engine("PULLBACK")
        self.wallet = 5.0
        r = self.ctl.execute(self.req("revert"))
        self.assertEqual(r["code"], "reserved")
        self.assertEqual(self.active(), "PULLBACK")
        # 엔진(실제 PULLBACK StrategyEngine): 눌림 신호 → 주문 0, TP → 매도 1
        eng = self.make(values=[V()] * 40)
        ec.attach(eng, USER, threading.Event())
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls, [])
        eng.position.open_position(1000.0, 100.0, 0, bar(0).ts)
        self.trader.coin = 1000.0
        self.strat.restore_split_state({"entry_count": 1, "pullback_count": 1, "first_entry_ts": bar(0).ts,
                                        "first_entry_reason": "PULLBACK", "trade_origin": "live",
                                        "last_ts": bar(0).ts})
        self.assertIs(self.feed(bar(1, o=100, h=106, l=99, c=104)), Action.SELL)
        self.assertEqual(len(self.trader.sell_calls), 1)
        # 감시: 지갑 0 본 봉 → 다음 봉에 복귀
        ec.attach(self.eng, USER, threading.Event())
        self.wallet = 0.0
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual([x["state"] for x in self.rows("REVERT")], ["DONE"])


# ================================================================ 5. 기동 때 처리 중 행 복구 (흐름 9)
class TestBootRecovery(SwitchCase):
    def switching_row(self):
        return self.add_row(note=ss.NOTE_SWITCHING)

    def test_boot_recovers_switching_row_done(self):
        self.switching_row()
        eparams.save_active_strategy(USER, "PULLBACK")
        self.mgr.mode = "TEST"
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        out = ss.Monitor().recover_all(self.ctl, [USER])
        self.assertEqual([o[2] for o in out], ["recovered"])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("DONE", "recovered")])
        self.assertTrue(any("재시작 뒤 확인" in b for b in self.bodies()))

    def test_boot_recovers_switching_row_failed_reverts_file(self):
        self.switching_row()
        eparams.save_active_strategy(USER, "PULLBACK")
        out = ss.Monitor().recover_all(self.ctl, [USER])
        self.assertEqual([o[2] for o in out], ["failed"])
        self.assertEqual([x["state"] for x in self.rows()], ["FAILED"])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(len(self.starts("EMA")), 1)
        self.assertEqual(len(self.bodies("CRITICAL")), 1)

    def test_boot_recovers_switching_row_aborted(self):
        self.switching_row()                              # 활성 파일 = EMA(from) — 파일 쓰기 전에 죽음
        out = ss.Monitor().recover_all(self.ctl, [USER])
        self.assertEqual([o[2] for o in out], ["aborted"])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("FAILED", "aborted_before_switch")])
        self.assertEqual(self.mgr.calls, [])
        self.assertTrue(any(ss.ABORTED_TEXT in b for b in self.bodies()))

    def test_boot_keeps_holding_reservation(self):
        self.add_row(note=None)
        self.assertEqual(ss.Monitor().recover_all(self.ctl, [USER]), [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])

    def test_boot_recovery_waits_for_boot_event_or_60s(self):
        self.switching_row()
        mon = ss.Monitor()
        with mock.patch.object(ss.Monitor, "_db_users", staticmethod(lambda: [USER])):
            mon(self.ctl)
            self.assertEqual(self.rows()[0]["state"], "RESERVED")      # 신호 없음 + 60초 전
            ec.BOOT_RESUME_DONE.set()
            mon(self.ctl)
            self.assertEqual(self.rows()[0]["state"], "FAILED")        # 신호 뒤 1회
        # 신호 없이 60초 예비 규칙
        ec.BOOT_RESUME_DONE.clear()
        self.switching_row()
        mon2 = ss.Monitor()
        with mock.patch.object(ss.Monitor, "_db_users", staticmethod(lambda: [USER])):
            mon2(self.ctl)
            self.assertEqual(self.rows()[1]["state"], "RESERVED")
            self.clock.sleep(ss.BOOT_FALLBACK_SEC)
            mon2(self.ctl)
            self.assertEqual(self.rows()[1]["state"], "FAILED")

    def test_tradebot_boot_sets_event_in_finally(self):
        from tests.regressions.test_r_2026_10_28_p4_t11_control import load_boot
        boot = load_boot()
        with mock.patch.dict(os.environ, {"TRADEBOT_BOOT_DELAY": "0"}), \
                mock.patch("engine.boot_resume.boot_resume_all", side_effect=RuntimeError("boom")):
            boot._boot_resume_thread()
        self.assertTrue(ec.BOOT_RESUME_DONE.is_set())
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        body = src.split("def _boot_resume_thread")[1].split("\ndef ")[0]
        self.assertIn("finally:", body)
        self.assertIn("BOOT_RESUME_DONE.set()", body.split("finally:")[1])


# ================================================================ 6. 설치·고정 파일
class TestInstallAndFixed(unittest.TestCase):
    def test_install_registers_handlers_and_hooks(self):
        with mock.patch.dict(cr._EXTRA_HANDLERS, {}, clear=True), \
                mock.patch.object(cr, "_POST_HOOKS", []), mock.patch.object(cr, "_TICK_HOOKS", []), \
                mock.patch.dict(ss._INSTALLED, {"done": False}):
            ss.install()
            ss.install()
            self.assertEqual(set(cr._EXTRA_HANDLERS), {"switch", "revert", "cancel_reservation"})
            self.assertEqual(cr._POST_HOOKS, [ss.post_force_buy])
            self.assertEqual(len(cr._TICK_HOOKS), 1)
            self.assertIsInstance(cr._TICK_HOOKS[0], ss.Monitor)

    def test_boot_script_installs_before_control_loop(self):
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        body = src.split("def _control_thread")[1].split("\ndef ")[0]
        self.assertLess(body.index("_install_switch()"), body.index("control_loop()"))

    def test_gate_installed_only_from_attach(self):
        """래퍼는 core.engine_control.attach(=live_loop._control_attach 안) 한 곳에서만 붙인다 — EMA 함수 파일 밖."""
        users = []
        for p in list((ROOT / "core").glob("*.py")) + list((ROOT / "engine").glob("*.py")):
            if "install_buy_gate(" in p.read_text(encoding="utf-8"):
                users.append(p.relative_to(ROOT).as_posix())
        self.assertEqual(sorted(users), ["core/engine_control.py", "engine/strategy_switch.py"])


# ================================================================ 7. fix round 1 (verifier 「수정 후 승인」)
def _crit_ops(case):
    return [c for c in case.notify.call_args_list if c.args[0] == "CRITICAL" and c.kwargs.get("audience") == "operator"]


class TestFixRound1LiveRace(SwitchCase):
    """항목 1: 전환 도중 다른 모드(실계좌) 엔진이 뜨면 손대지 않는다 — 파일 쓰기·재시작·FAILED 없음."""

    def test_live_engine_started_mid_switch_before_active_write(self):
        """즉시 전환: 재확인(보유 판정) 뒤 활성 파일 쓰기 직전에 LIVE 엔진 → mode_conflict 거절, 활성 EMA, 엔진 호출 0."""
        n = {"i": 0}

        def w():
            n["i"] += 1
            if n["i"] == 2:                      # 쓰기 직전 재확인 = 두 번째 보유 판정 — 그 순간 LIVE 엔진이 뜸
                self.mgr.mode = "LIVE"
            return 0.0
        self.wallet = w
        r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"), r)
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("CANCELED", "mode_conflict")])
        self.assertEqual(self.bodies("CRITICAL"), [])
        self.assertIsNone(ss.reservation(USER, "TEST"))      # 거절한 요청이 매수를 막아 두지 않음

    def test_live_engine_started_mid_switch_before_restart(self):
        """즉시 전환: 활성 파일을 쓴 뒤 restart_engine 직전에 LIVE 엔진 → 활성 파일만 EMA 로 되돌림, 재시작·FAILED 없음."""
        real_write = ss._write_active
        writes = []

        def write(u, s):
            writes.append(s)
            ok = real_write(u, s)
            if s == "PULLBACK":
                self.mgr.mode = "LIVE"
            return ok
        with mock.patch.object(ss, "_write_active", side_effect=write):
            r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"), r)
        self.assertEqual(writes, ["PULLBACK", "EMA"])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])
        self.assertNotIn("FAILED", [x["state"] for x in self.rows()])
        self.assertEqual(self.bodies("CRITICAL"), [])

    def test_live_engine_started_mid_switch_monitor_keeps_reservation(self):
        """예약 완료 경로(감시): 재시작 직전 LIVE 엔진 → 예약 유지(note 없음), 활성 EMA, 재시작 0."""
        self.run_engine()
        self.wallet = 4.0
        self.assertEqual(self.switch()["code"], "reserved")
        self.wallet = 0.0
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        real_write = ss._write_active

        def write(u, s):
            ok = real_write(u, s)
            if s == "PULLBACK":
                self.mgr.mode = "LIVE"
            return ok
        with mock.patch.object(ss, "_write_active", side_effect=write):
            self.assertEqual(tick(self), [["mode_conflict"]])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.starts(), [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])

    def test_live_engine_started_mid_switch_monitor_before_write(self):
        """예약 완료 경로(감시): 쓰기 직전 재확인 보유 판정 중 LIVE 엔진 → 활성 파일을 쓰지 않음, 예약 유지."""
        self.run_engine()
        self.wallet = 4.0
        self.switch()
        self.wallet = 0.0
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        n = {"i": 0}

        def w():
            n["i"] += 1
            if n["i"] == 2:
                self.mgr.mode = "LIVE"
            return 0.0
        self.wallet = w
        with mock.patch.object(ss, "_write_active", side_effect=AssertionError("쓰지 않아야 함")):
            self.assertEqual(tick(self), [["mode_conflict"]])
        self.assertEqual(self.starts(), [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])

    def test_flat_check_not_sent_to_non_test_engine(self):
        """보유 확인 항목은 모의(TEST) 엔진 큐에만 — LIVE 엔진(또는 요청 mode 와 다른 엔진)이면 넣지 않고 보유 중."""
        self.run_engine()
        self.clock.hooks.clear()
        self.mgr.mode = "LIVE"
        self.assertIsNone(ss.flat_state(self.ctl, USER, "TEST", "EMA", EMA_TICKER))
        self.assertTrue(self.eng.control_queue.empty())
        self.mgr.mode = "TEST"
        self.assertIsNone(ss.flat_state(self.ctl, USER, "LIVE", "EMA", EMA_TICKER))
        self.assertTrue(self.eng.control_queue.empty())
        self.assertEqual(self.wallet_reads, 0)


class TestFixRound1MonitorGuards(SwitchCase):
    """항목 2·3·7: 감시 tick 의 TEST 가드, DONE 기록 실패 처리, 짧은 큐 대기."""

    def test_monitor_skips_non_test_engine_with_one_warning(self):
        self.run_engine()
        self.clock.hooks.clear()
        self.mgr.mode = "LIVE"
        self.add_row(mode="LIVE")
        mon = ss.Monitor()
        with self.assertLogs("engine.strategy_switch", "WARNING") as cm:
            self.assertIsNone(mon.check_user(self.ctl, USER))
            self.assertIsNone(mon.check_user(self.ctl, USER))
        self.assertEqual(sum("모의가 아닌 엔진(예약 확인)" in m for m in cm.output), 1)
        self.assertTrue(self.eng.control_queue.empty())
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", None)])

    def test_recover_skips_live_switching_row(self):
        self.add_row(mode="LIVE", note=ss.NOTE_SWITCHING)
        eparams.save_active_strategy(USER, "PULLBACK")
        mon = ss.Monitor()
        with self.assertLogs("engine.strategy_switch", "WARNING") as cm:
            self.assertEqual([o[2] for o in mon.recover_all(self.ctl, [USER])], ["skipped"])
            self.assertEqual(mon.recover_row(self.ctl, USER, self.rows()[0]), "skipped")
        self.assertEqual(sum("처리 중 행(기동 복구)" in m for m in cm.output), 1)
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", ss.NOTE_SWITCHING)])
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.active(), "PULLBACK")

    def _failing_done(self, fail_times):
        real = ss.update_row
        n = {"i": 0}

        def upd(u, rid, **kw):
            if kw.get("state") == "DONE" and n["i"] < fail_times:
                n["i"] += 1
                raise sqlite3.OperationalError("database is locked")
            return real(u, rid, **kw)
        return mock.patch.object(ss, "update_row", side_effect=upd)

    def test_done_record_failure_retries_and_alerts_operator(self):
        """재시작 뒤 DONE 기록 1회 실패 → 운영자 CRITICAL 1 + 다시 시도해 DONE."""
        self.run_engine()
        with self._failing_done(1):
            r = self.switch()
        self.assertEqual(r["code"], "ok")
        self.assertNotIn("done_record_pending", r["detail"])
        self.assertEqual([x["state"] for x in self.rows()], ["DONE"])
        self.assertEqual(len(_crit_ops(self)), 1)
        self.assertEqual(self.active(), "PULLBACK")

    def test_done_record_failure_settled_by_monitor_tick(self):
        """DONE 기록이 끝내 실패 → 행 RESERVED·switching 으로 남고, 감시 tick 이 「활성 = 대상 + 엔진 준비」로 DONE 정리."""
        self.run_engine()
        with self._failing_done(99):
            r = self.switch()
        self.assertEqual(r["code"], "ok")
        self.assertTrue(r["detail"]["done_record_pending"])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", ss.NOTE_SWITCHING)])
        self.assertEqual(len(_crit_ops(self)), 1)                 # 시도마다가 아니라 1회
        self.eng.strategy_type = "PULLBACK"                    # 재시작된 엔진 = 대상 전략
        mon = ss.Monitor()
        mon.boot_done = True
        mon(self.ctl)
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("DONE", "settled")])

    def test_settle_needs_active_target_and_ready(self):
        self.run_engine("PULLBACK")
        rid = self.add_row(note=ss.NOTE_SWITCHING)            # 활성 파일 EMA(≠ PULLBACK)
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        mon = ss.Monitor()
        self.assertEqual(mon.settle_switching(self.ctl, USER), [])
        eparams.save_active_strategy(USER, "PULLBACK")
        ev.clear()                                             # 엔진 준비 전
        self.assertEqual(mon.settle_switching(self.ctl, USER), [])
        ev.set()
        self.assertEqual(mon.settle_switching(self.ctl, USER), [rid])

    def test_settle_needs_running_engine_strategy_equal_target(self):
        """fix round 2-1: 활성 파일 = 대상 + 준비여도 실행 중 엔진의 전략이 대상이 아니면(옛 EMA 엔진) 정리하지 않음."""
        self.run_engine("EMA")
        rid = self.add_row(note=ss.NOTE_SWITCHING)
        eparams.save_active_strategy(USER, "PULLBACK")
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        mon = ss.Monitor()
        self.assertEqual(mon.settle_switching(self.ctl, USER), [])
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", ss.NOTE_SWITCHING)])
        self.eng.strategy_type = "PULLBACK"
        self.assertEqual(mon.settle_switching(self.ctl, USER), [rid])

    def test_settle_not_before_boot_recovery(self):
        """N09: 기동 복구 전 tick 에서는 정리하지 않는다(정리 0행) — 처리 중 행은 기동 복구가 먼저 본다."""
        self.run_engine("PULLBACK")
        self.add_row(note=ss.NOTE_SWITCHING)
        eparams.save_active_strategy(USER, "PULLBACK")
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        mon = ss.Monitor()
        settled = []
        real = mon.settle_switching
        mon.settle_switching = lambda c, u: settled.append(real(c, u)) or settled[-1]
        with mock.patch.object(ss.Monitor, "_db_users", staticmethod(lambda: [])):
            mon(self.ctl)                                      # 신호 없음 + 60초 전 = 기동 복구 전
        self.assertFalse(mon.boot_done)
        self.assertEqual(sum(len(s) for s in settled), 0)
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", ss.NOTE_SWITCHING)])

    def test_monitor_flat_check_short_queue_wait(self):
        """전역 잠금을 쥔 감시 tick 의 보유 확인은 3초만 기다린다(요청 처리 기본 20초 아님) → 보유 중."""
        self.run_engine()
        self.clock.hooks.clear()                               # 엔진이 큐를 비우지 않음(바쁨)
        self.add_row()
        t0 = self.clock.t
        self.assertEqual(tick(self), [["holding"]])
        waited = self.clock.t - t0
        self.assertGreaterEqual(waited, ss.MONITOR_QUEUE_WAIT_SEC)
        self.assertLess(waited, ss.MONITOR_QUEUE_WAIT_SEC + 1.0)
        self.assertLess(ss.MONITOR_QUEUE_WAIT_SEC, self.ctl.queue_wait)

    def test_monitor_holds_global_lock(self):
        """V13: 감시 tick 은 요청 처리와 같은 전역 잠금 안에서만 돈다(잠금을 쥐고 있으면 기다림)."""
        entered = threading.Event()

        def users():
            entered.set()
            return []
        mon = ss.Monitor()
        mon.boot_done = True
        with mock.patch.object(ss.Monitor, "_running_users", staticmethod(users)):
            self.ctl._GLOBAL_LOCK.acquire()
            try:
                th = threading.Thread(target=mon, args=(self.ctl,), daemon=True)
                th.start()
                self.assertFalse(entered.wait(0.3))
            finally:
                self.ctl._GLOBAL_LOCK.release()
            self.assertTrue(entered.wait(5))
            th.join(5)
        self.assertFalse(th.is_alive())


class TestFixRound1Reads(SwitchCase):
    """항목 4·5: WAL(-shm 없음) 읽기, F8·잠김 수량 조회 실패 = 보유 중(fail closed)."""

    def test_reservation_read_wal_without_shm(self):
        self.add_row()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        for s in ("-shm", "-wal"):
            if os.path.exists(self.db_path + s):
                os.remove(self.db_path + s)
        self.assertFalse(os.path.exists(self.db_path + "-shm"))
        self.assertIsNotNone(ss.reservation(USER, "TEST"))
        self.assertEqual(ss.gate_decision(USER, "TEST", "EMA"), (True, "switch_reserved"))
        # 읽기 연결은 쓰기 금지(query_only)
        c = ss._connect_ro(USER)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                c.execute("DELETE FROM strategy_switch")
        finally:
            c.close()

    def test_connect_ro_missing_db_does_not_create(self):
        os.remove(self.db_path)
        with self.assertRaises(sqlite3.OperationalError):
            ss.reservation(USER, "TEST")
        self.assertFalse(os.path.exists(self.db_path))

    def test_f8_pending_buy_direct_read_and_fail_closed(self):
        self.assertFalse(REAL_PENDING_BUY(USER, EMA_TICKER))
        conn = sqlite3.connect(self.db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
        status_col = "state" if "state" in cols else "status"
        conn.close()
        with mock.patch.object(ss, "_connect_ro", side_effect=sqlite3.OperationalError("locked")):
            self.assertTrue(REAL_PENDING_BUY(USER, EMA_TICKER))           # 연결 실패 → 있음
        bad = mock.MagicMock()
        bad.execute.side_effect = [mock.MagicMock(fetchall=lambda: [(0, status_col)]),
                                   sqlite3.OperationalError("disk I/O error")]
        with mock.patch.object(ss, "_connect_ro", return_value=bad):
            self.assertTrue(REAL_PENDING_BUY(USER, EMA_TICKER))           # 조회 실패 → 있음
        # services.db 원 함수는 그대로(예외 때 False — 의미 무변경)
        from services import db as sdb
        with mock.patch.object(sdb, "get_db_path", return_value="/nonexistent/dir/x.db"):
            self.assertFalse(sdb.has_pending_bot_limit_buy(USER, EMA_TICKER))

    def test_locked_qty_counted_and_fail_closed(self):
        from services import db as sdb
        sdb.update_coin_position(USER, EMA_TICKER, 0.0, 2.0)
        self.assertAlmostEqual(REAL_WALLET_QTY(USER, EMA_TICKER, SimpleNamespace(test_mode=True)), 2.0)
        with mock.patch.object(ss, "_connect_ro", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                REAL_WALLET_QTY(USER, EMA_TICKER, SimpleNamespace(test_mode=True))
        # 엔진 없는 보유 판정: 잠김 조회 실패 → None(보유 중)
        with mock.patch.object(ss, "_wallet_qty", side_effect=REAL_WALLET_QTY), \
                mock.patch.object(ss, "_locked_qty", side_effect=sqlite3.OperationalError("locked")):
            self.assertIsNone(ss.flat_state(self.ctl, USER, "TEST", "EMA", EMA_TICKER))


class TestFixRound1Gaps(SwitchCase):
    """항목 6(V01·V06·V16·V17)·8·9."""

    def test_force_buy_engine_path_ema_during_reservation(self):
        """V01: 엔진이 돌 때 제어 큐 EMA 강제 매수(force_buy_in)는 예약 중에도 나간다, 예약 유지·안내 1회."""
        self.run_engine()
        self.add_row()
        from services import trading_control as tc
        with mock.patch.object(tc, "force_buy_in", return_value="✅ [TEST] 강제 매수 완료") as fb:
            r = self.ctl.execute(self.req("force_buy"))
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(fb.call_count, 1)
        self.assertEqual(r["detail"]["note_text"], ss.RESERVATION_KEPT_TEXT)
        self.assertEqual([x["state"] for x in self.rows()], ["RESERVED"])

    def test_force_buy_engine_path_pullback_during_reservation(self):
        """V01: PULLBACK 엔진 제어 큐 강제 매수(_pullback_force_buy)도 복귀 예약 중에 나간다."""
        self.run_engine("PULLBACK")
        calls = []
        self.eng._pullback_force_buy = lambda: calls.append(1) or {"status": "done", "code": "ok", "detail": {}}
        self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        r = self.ctl.execute(self.req("force_buy"))
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(calls, [1])
        self.assertEqual([x["state"] for x in self.rows()], ["RESERVED"])

    def test_reserved_close_action_still_sells(self):
        """V04: 예약 중 청산(Action.CLOSE — SELL 과 같은 매도 경로)은 래퍼가 막지 않는다."""
        eng = self.ema_engine()
        ec.attach(eng, USER, threading.Event())
        self.add_row()
        eng.position.open_position(1.0, 55.0, 0, bar(0).ts)
        eng.trader.coin = 1.0
        with mock.patch.object(ss, "reservation", side_effect=AssertionError("매도는 예약을 읽지 않음")):
            eng.execute(Action.CLOSE, bar(2), {"ema_fast": 1, "ema_slow": 2})
        self.assertEqual(len(eng.trader.sell_calls), 1)

    def test_reservation_is_per_user(self):
        """V07: 같은 DB 의 다른 사용자 예약은 이 사용자의 매수를 막지 않는다(user_id 로 거름)."""
        ss.insert_row("other_user", mode="TEST", kind="SWITCH", from_strategy="EMA", to_strategy="PULLBACK")
        self.assertIsNone(ss.reservation(USER, "TEST"))
        self.assertEqual(ss.gate_decision(USER, "TEST", "EMA"), (False, None))
        self.assertIsNotNone(ss.reservation("other_user", "TEST"))

    def test_cancel_rejected_for_switching_row(self):
        """V06: 처리 중(switching) 행은 취소하지 않는다 → engine_busy, 행 그대로."""
        self.add_row(note=ss.NOTE_SWITCHING)
        r = self.ctl.execute(self.req("cancel_reservation"))
        self.assertEqual(r["code"], "engine_busy")
        self.assertEqual([(x["state"], x["note"]) for x in self.rows()], [("RESERVED", ss.NOTE_SWITCHING)])

    def test_single_sell_reject_no_notify(self):
        """V16: 매도 거절 1건은 알림 없음, 2건째에 1회."""
        self.run_engine()
        self.wallet = 4.0
        self.switch()
        tick(self)                                            # 기준 id
        conn = sqlite3.connect(self.db_path)
        ins = ("INSERT INTO audit_trades (ticker, interval_sec, bar, type, reason, price) "
               "VALUES (?, 180, 1, 'SELL_REJECTED', 'STOP_LOSS', 50.0)")
        conn.execute(ins, (EMA_TICKER,))
        conn.commit()
        tick(self, 2)
        self.assertEqual([b for b in self.bodies("WARNING") if ss.SELL_REJECT_TEXT in b], [])
        conn.execute(ins, (EMA_TICKER,))
        conn.commit()
        conn.close()
        tick(self)
        self.assertEqual(len([b for b in self.bodies("WARNING") if ss.SELL_REJECT_TEXT in b]), 1)

    def test_switch_from_macd(self):
        """V17: 활성 MACD 에서도 전환된다(from MACD), 복귀하면 MACD."""
        eparams.save_active_strategy(USER, "MACD")
        r = self.switch()
        self.assertEqual(r["code"], "ok", r)
        self.assertEqual(self.active(), "PULLBACK")
        self.assertEqual(self.rows("SWITCH")[0]["from_strategy"], "MACD")
        self.mgr.mode = None                                  # 엔진을 멈춘 뒤 복귀(엔진 없는 보유 판정 → 즉시)
        r = self.ctl.execute(self.req("revert"))
        self.assertEqual(r["code"], "ok", r)
        self.assertEqual(self.active(), "MACD")

    def test_active_write_failure_does_not_restart_unstopped_engine(self):
        """항목 9: 활성 파일 쓰기 실패(restart_engine 안 부름) → 엔진은 멈춘 적 없음 → 재시작·정지 0, FAILED·CRITICAL."""
        self.run_engine()
        real_write = ss._write_active
        with mock.patch.object(ss, "_write_active",
                               side_effect=lambda u, s: False if s == "PULLBACK" else real_write(u, s)):
            r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("error", "switch_failed"))
        self.assertEqual(r["detail"]["why"], "active_write_failed")
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual([x["state"] for x in self.rows()], ["FAILED"])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(len(self.bodies("CRITICAL")), 1)

    def test_investor_texts_have_no_internal_names(self):
        """항목 8: 투자자에게 가는 새 문구에 내부 코드·이름(snake_case·표 이름·sha 등)이 없다."""
        texts = list(ss.TEXT.values()) + [ss.FAILED_TITLE, ss.ABORTED_TEXT, ss.SAVED_CHANGED_TEXT, ss.SELL_REJECT_TEXT,
                                          ss.RESERVATION_KEPT_TEXT, *ss._BLOCK_NOTES.values()]
        t12_codes = ("reserved", "switch_failed", "live_not_supported", "already_reserved", "already_pullback",
                     "not_pullback", "saved_invalid", "sha_mismatch", "choose_strategy", "no_reservation",
                     "reservation_unknown", "switch_table_missing")
        texts += [cr.CODE_TEXT[c] for c in t12_codes]
        import re as _re
        for t in texts:
            self.assertIsNone(_re.search(r"[a-z]+_[a-z_]+|strategy_switch|PULLBACK|sha256|\bsha\b", t), t)
        # 운영자 전용 문구는 audience="operator" 로만 나간다(투자자 채널 아님)
        src = (ROOT / "engine" / "strategy_switch.py").read_text(encoding="utf-8")
        for name in ("TABLE_MISSING_TITLE", "DONE_RECORD_TITLE"):
            uses = [ln for ln in src.splitlines() if name in ln and "=" not in ln.split(name)[0][-3:]]
            self.assertTrue(uses, name)
            self.assertTrue(all("_notify_operator(" in ln or ln.strip().startswith(name) for ln in uses), uses)


if __name__ == "__main__":
    unittest.main()
