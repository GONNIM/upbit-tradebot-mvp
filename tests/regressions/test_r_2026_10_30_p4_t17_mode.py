"""
2차 T17 (결정 D4): TEST/LIVE 분리 — 분할 상태·예약·요청의 모드 칸.

T17 은 코드를 바꾸지 않는다(정지선 보고 · Fable `docs/fable/2026-10-30-phase2-t17-decision-1.md` ·
사용자 결정 1030-04 U1·U2 (가)). 이미 T6·T11~T14 에 든 모드 거름을 시험으로 고정한다.
- 분할 상태(pullback_state)는 PK(user_id, mode) — 엔진 모드(trader.test_mode)의 행만 복원한다.
- 예약(strategy_switch)은 엔진·신버전 경로가 mode 로 거른다. 의도한 예외 2곳은 모든 모드를 본다:
  구버전 잠금 `ui/pullback_lock.reservation_any_mode`(결정 1029-10 C3 ①)와 그 값을 쓰는 D10
  `services/auto_verify.keep_capital_on_verify`.
  `strategy_switch.switching_rows(user_id)` 도 mode 로 거르지 않는다(Fable 권고 2) — 호출처
  `Monitor.recover_all`·`settle_switching` 이 TEST 행만 고른다.
- 요청 모드(신버전 세션 입장 모드) ≠ 실행 중 엔진 모드 → 엔진을 건드리는 8종은 거절(엔진 호출 0건).
  TEST 실행 중 LIVE 요청은 switch·revert 가 `live_not_supported`, apply_params·ops_settings 가
  `apply_live_not_supported` 로 먼저 거절된다(실계좌 거절이 모드 검사보다 앞 — 같은 거절·엔진 무접촉).
  예약 취소는 예외(U1 가): 엔진을 건드리지 않으므로 다른 모드 엔진이 돌아도 처리한다(Fable 권고 3).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_30_p4_t17_mode -v
"""
from __future__ import annotations

import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import engine_control as ec  # noqa: E402
from engine import params as eparams  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from engine import strategy_switch as ss  # noqa: E402
from services import pullback_state as ps  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import FakeTrader, USER  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t6_split_position import (  # noqa: E402
    B950, B1000, C950, C1000, P990, T6Case, bar,
)
from tests.regressions.test_r_2026_10_28_p4_t11_control import FakeThread  # noqa: E402
from tests.regressions.test_r_2026_10_29_p4_t12_switch import FakeEng, SwitchCase  # noqa: E402
from tests.regressions.test_r_2026_10_29_p4_t14_ops import KEYS_ON, OpsCase  # noqa: E402
from v2 import control as v2control  # noqa: E402
from v2 import db as v2db  # noqa: E402

ENGINE_KINDS = ("engine_start", "engine_stop", "force_buy", "force_sell", "switch", "revert",
                "apply_params", "ops_settings")


# ================================================================ 1. 분할 상태
class TestStateSeparatedByMode(T6Case):
    def _test_row_round2(self):
        """TEST 엔진으로 2회차·armed 까지 진행해 TEST 행을 만든다(회차 2·qty>0)."""
        self.make(values=P990)
        self.feed(bar(0, **B1000), bar(1, **C1000), bar(2, **B950), bar(3, **C950))
        r = ps.load(USER, "TEST")
        self.assertEqual(r["entry_count"], 2)
        self.assertGreater(r["qty"], 0)
        return self.trader.coin

    def _rows(self):
        return self.q("SELECT * FROM pullback_state ORDER BY mode")

    def test_state_separated_by_mode(self):
        """TEST 행(회차 2·qty>0)은 LIVE 엔진 복원에 안 섞이고, LIVE 행은 TEST 엔진 복원에 안 섞인다."""
        coin = self._test_row_round2()
        before = self._rows()
        self.assertEqual(len(before), 1)

        # (1) LIVE trader 엔진 복원 → LIVE 행 없음 = 워밍업 그대로, TEST 행 불변
        tr = FakeTrader(test_mode=False)
        tr.coin = coin
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        self.assertEqual(self.eng._pullback_mode(), "LIVE")
        res = self.eng.pullback_restore_on_boot(None)
        self.assertEqual((res["loaded"], res["restored"], res["reason"]), (False, False, "no_state"))
        self.assertEqual((self.strat.entry_count, self.strat.armed), (0, False))
        self.assertIsNone(ps.load(USER, "LIVE"))
        self.assertEqual(self._rows(), before)

        # (2) 반대 방향: 그 행을 LIVE 로 옮기면 TEST 엔진 복원에도 안 섞이고 LIVE 행은 불변
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE pullback_state SET mode='LIVE' WHERE mode='TEST'")
        conn.commit()
        conn.close()
        moved = self._rows()
        tr = FakeTrader(test_mode=True)
        tr.coin = coin
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        self.assertEqual(self.eng._pullback_mode(), "TEST")
        res = self.eng.pullback_restore_on_boot(None)
        self.assertEqual((res["loaded"], res["restored"], res["reason"]), (False, False, "no_state"))
        self.assertEqual(self.strat.entry_count, 0)
        self.assertIsNone(ps.load(USER, "TEST"))
        self.assertEqual(self._rows(), moved)

    def test_same_mode_still_restores(self):
        """대조군: 같은 모드(TEST)면 복원된다 — 위 시험이 「복원이 아예 안 되는 것」을 잡지 않게."""
        coin = self._test_row_round2()
        tr = FakeTrader(test_mode=True)
        tr.coin = coin
        self.make(values=[V(p=945.0)] * 10, trader=tr)
        res = self.eng.pullback_restore_on_boot(None)
        self.assertTrue(res["restored"])
        self.assertEqual(self.strat.entry_count, 2)


# ================================================================ 2. 예약
class TestReservationSeparatedByMode(SwitchCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(v2db, "DATA_DIR", Path(self.tmp.name))   # 신버전 읽기 = 같은 임시 DB
        p.start()
        self.addCleanup(p.stop)

    def test_reservation_separated_by_mode(self):
        """TEST 예약은 LIVE 조회(엔진 reservation·신버전 reservation·LIVE gate_decision)에 안 보인다."""
        rid = self.add_row(mode="TEST")
        # 대조: TEST 조회에는 보임
        self.assertEqual(ss.reservation(USER, "TEST")["id"], rid)
        self.assertEqual(v2control.reservation(USER, "TEST")["id"], rid)
        self.assertEqual(ss.gate_decision(USER, "TEST", "EMA"), (True, "switch_reserved"))
        # LIVE 조회에는 안 보임
        self.assertIsNone(ss.reservation(USER, "LIVE"))
        self.assertIsNone(v2control.reservation(USER, "LIVE"))
        self.assertEqual(ss.gate_decision(USER, "LIVE", "EMA"), (False, None))
        self.assertIsNone(ss.last_done_switch(USER, "LIVE"))

    def test_intended_cross_mode_readers(self):
        """의도한 예외 2곳: 구버전 잠금(reservation_any_mode, C3 ①)과 D10(keep_capital_on_verify)은 모든 모드를 본다."""
        import ui.pullback_lock as pl
        from services.auto_verify import keep_capital_on_verify
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR IGNORE INTO users (username, display_name, virtual_krw) VALUES (?, ?, ?)",
                     (USER, "이름", 1_000_000))
        conn.commit()
        conn.close()
        self.assertIsNone(pl.reservation_any_mode(USER))
        self.assertEqual(keep_capital_on_verify(USER, "이름"), (False, None, None))
        rid = self.add_row(mode="LIVE")               # 엔진 경로로는 생기지 않는 LIVE 행 — 모드를 안 거르는지만 본다
        self.assertEqual(pl.reservation_any_mode(USER)["id"], rid)
        st = pl.lock_state(USER)
        self.assertEqual((st["why"], st["locked"]), ("reserved", True))
        self.assertTrue(pl.keeps_capital(st))
        self.assertTrue(keep_capital_on_verify(USER, "이름")[0])

    def test_switching_rows_unfiltered_callers_pick_test_only(self):
        """switching_rows(user_id) 는 mode 로 거르지 않는다(두 모드 행 모두). 호출처가 TEST 만 고른다:
        recover_all 은 LIVE 행을 skipped(행 그대로), settle_switching 은 LIVE 행을 정리하지 않는다."""
        live_id = self.add_row(mode="LIVE", note=ss.NOTE_SWITCHING)
        rows = ss.switching_rows(USER)
        self.assertEqual([(r["id"], r["mode"]) for r in rows], [(live_id, "LIVE")])

        mon = ss.Monitor()
        self.assertEqual(mon.recover_all(self.ctl, users=[USER]), [(USER, live_id, "skipped")])
        self.assertEqual(self.mgr.calls, [])
        r = ss.fetch_row(USER, live_id)
        self.assertEqual((r["state"], r["note"]), ("RESERVED", ss.NOTE_SWITCHING))

        # settle: TEST 엔진 실행 + 준비 + 활성 = 대상 + 엔진 전략 = 대상. TEST 행은 정리, LIVE 행은 그대로
        test_id = self.add_row(mode="TEST", note=ss.NOTE_SWITCHING)
        self.assertEqual({r["mode"] for r in ss.switching_rows(USER)}, {"TEST", "LIVE"})
        eparams.save_active_strategy(USER, "PULLBACK")
        eng = FakeEng("PULLBACK")
        ec.attach(eng, USER, threading.Event())
        self.mgr.mode = "TEST"
        self.mgr._threads[USER] = FakeThread(self.clock, None)
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        self.assertEqual(mon.settle_switching(self.ctl, USER), [test_id])
        self.assertEqual(ss.fetch_row(USER, test_id)["state"], "DONE")
        r = ss.fetch_row(USER, live_id)
        self.assertEqual((r["state"], r["note"]), ("RESERVED", ss.NOTE_SWITCHING))


# ================================================================ 3. 요청 모드 = 실행 중 모드
class TestRequestModeMustMatchRunning(OpsCase):
    def setUp(self):
        super().setUp()
        self.forced = []
        self.ctl.force_buy_fn = lambda *a, **k: self.forced.append(("buy", a, k)) or "[TEST] 강제 매수 완료"
        self.ctl.force_sell_fn = lambda *a, **k: self.forced.append(("sell", a, k)) or "[TEST] 강제 매도 완료"

    def _payload(self, kind):
        if kind in ("switch", "apply_params"):
            return {"saved_sha256": self.sha}
        if kind == "revert":
            return {"strategy": "EMA"}
        if kind == "ops_settings":
            return {"keys": dict(KEYS_ON)}
        return {}

    def _snapshot(self):
        return (self.applied_bytes(), self.active(), Path(pbp.saved_path(USER)).read_bytes(), self.rows(),
                ps.load(USER, "TEST"), ps.load(USER, "LIVE"))

    def _attach_test_engine(self):
        eng = FakeEng("PULLBACK")
        ec.attach(eng, USER, threading.Event())
        self.mgr.mode = "TEST"
        self.mgr._threads[USER] = FakeThread(self.clock, None)
        return eng

    def test_request_mode_must_match_running(self):
        """엔진을 건드리는 8종: LIVE 실행 중 + TEST 요청 → mode_conflict, TEST 실행 중 + LIVE 요청 → 거절. 엔진 호출 0건."""
        reverse_code = {"switch": "live_not_supported", "revert": "live_not_supported",
                        "apply_params": "apply_live_not_supported", "ops_settings": "apply_live_not_supported"}
        for running, mode in (("LIVE", "TEST"), ("TEST", "LIVE")):
            for kind in ENGINE_KINDS:
                with self.subTest(running=running, kind=kind):
                    self.mgr.calls.clear()
                    self.forced.clear()
                    if running == "TEST":
                        eng = self._attach_test_engine()
                    else:
                        ec._RUNNING.clear()
                        eng = None
                        self.mgr.mode = "LIVE"
                    before = self._snapshot()
                    r = self.ctl.execute(self.req(kind, mode, self._payload(kind)))
                    want = "mode_conflict" if running == "LIVE" else reverse_code.get(kind, "mode_conflict")
                    self.assertEqual((r["status"], r["code"]), ("rejected", want))
                    if want == "mode_conflict":
                        self.assertEqual(r["detail"]["running"], running)
                    self.assertEqual(self.mgr.calls, [])                  # start·stop 0
                    self.assertEqual(self.forced, [])                     # 엔진 없는 강제 매매 0
                    if eng is not None:
                        self.assertTrue(eng.control_queue.empty())        # 엔진 제어 큐 0
                    self.assertEqual(self.mgr.mode, running)              # 실행 중 엔진 그대로
                    self.assertEqual(self._snapshot(), before)            # 적용본·활성·저장본·전환 기록·분할 상태 불변

    def test_same_mode_reaches_engine(self):
        """대조군: 같은 모드면 모드 검사를 지난다(위 시험이 「늘 거절」을 잡지 않게)."""
        self.mgr.mode = "TEST"
        r = self.ctl.execute(self.req("engine_stop", "TEST"))
        self.assertEqual((r["status"], r["code"]), ("done", "stopped"))
        self.assertEqual(self.mgr.calls, [("stop", USER, "TEST")])

    def test_cancel_reservation_allowed_with_other_mode_engine(self):
        """U1 (가): 예약 취소는 엔진을 건드리지 않으므로 다른 모드 엔진이 돌아도 done·ok, 엔진 호출 0건."""
        rid = self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA", mode="TEST")
        ec._RUNNING.clear()
        self.mgr.mode = "LIVE"
        before = (self.applied_bytes(), self.active())
        r = self.ctl.execute(self.req("cancel_reservation", "TEST"))
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))
        self.assertEqual(r["detail"]["reservation_id"], rid)
        self.assertEqual(ss.fetch_row(USER, rid)["state"], "CANCELED")
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.forced, [])
        self.assertEqual(self.mgr.mode, "LIVE")
        self.assertEqual((self.applied_bytes(), self.active()), before)

    def test_cancel_reservation_live_request_does_not_touch_test_row(self):
        """반대: TEST 엔진 실행 중 LIVE 취소 요청 → LIVE 예약 없음(no_reservation), TEST 예약 행 그대로, 엔진 호출 0건."""
        rid = self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA", mode="TEST")
        eng = self._attach_test_engine()
        r = self.ctl.execute(self.req("cancel_reservation", "LIVE"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "no_reservation"))
        self.assertEqual(ss.fetch_row(USER, rid)["state"], "RESERVED")
        self.assertEqual(self.mgr.calls, [])
        self.assertTrue(eng.control_queue.empty())


if __name__ == "__main__":
    unittest.main()
