"""
2차 T11 수정 1회차: 검수 지적 반영 시험.

- 링크(심볼릭 링크)로 바깥 파일을 덮어쓰지 않음: 임시 파일은 임의 이름(O_EXCL), 링크 폴더·링크 요청은 건너뜀,
  폴더 권한(그룹·남 쓰기 가능)이면 건너뜀. 엔진 생존 파일(scripts/tradebot_boot.py)도 같은 도우미.
- 사용자당 한 번 훑을 때 1건, 강제 매수·강제 매도·엔진 정지는 같은 종류 30초 간격(too_frequent, 알림 1회).
- 형식이 맞지 않는 요청(깨진 파일·id 오류·사용자 불일치·링크)은 운영자 CRITICAL 1회(폴더 단위).
- 새 전략 강제 매수: 앞 매도(엔진 밖·강제 매도) 뒤 다음 봉 전이어도 지갑 대조로 1회차부터, 거절 뒤 링 armed 복원,
  판정 체결 대기(pending_fill)면 거부.
- 재시작: 엔진이 없으면 정지하지 않음, 시작 False 가 이미 실행·다른 모드면 그 코드, 정지 시간 초과로 관리자 표에서
  빠진 옛 스레드(이름)도 기다림. 엔진 시작은 몇 초 생존 확인. 실행 시작 뒤 120초 상한(결과 미확인).
- 준비 Event·세대: 다른 시작의 Event 는 쓰지 않음, 멈춤 중이면 세우지 않음, 끝나면 실행 중 표에서 지움.
- 엔진 없을 때 전략 결정·새 전략 적용본만, 지정 전략 예외 때 되돌림, 상수 같음, live_loop 제어 함수 몸체 lint.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p4_t11_control_fix1 -v
"""
from __future__ import annotations

import ast
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import engine_control as ec  # noqa: E402
import engine.engine_manager as engine_manager  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions import test_r_2026_10_28_p4_t11_control as t11  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import USER, bar  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t6_split_position import T6Case  # noqa: E402


def _bad_alerts(notify):
    return [c for c in notify.call_args_list if c.args and c.args[0] == "CRITICAL"
            and str(c.kwargs.get("dedupe_key", "")).startswith("v2_control_bad:")]


# ================================================================ 1. 링크로 바깥 파일 덮어쓰기 막음
class TestSymlinkSafety(t11.CtlCase):
    def setUp(self):
        super().setUp()
        self.outside = Path(self.tmp.name) / "outside"
        self.outside.mkdir()
        self.victim = self.outside / "victim.txt"
        self.victim.write_text("KEEP", encoding="utf-8")

    def assert_victim(self):
        self.assertEqual(self.victim.read_text(encoding="utf-8"), "KEEP")

    def test_result_tmp_symlink_not_followed(self):
        rid = self.req()
        d = self.base / "alice"
        os.symlink(self.victim, d / f".res-{rid}.json.tmp")          # 옛 고정 임시 이름 자리에 링크
        self.ctl.scan_once()
        self.assert_victim()
        p = d / f"res-{rid}.json"
        self.assertFalse(p.is_symlink())
        self.assertEqual(stat.S_IMODE(p.lstat().st_mode), 0o600)
        self.assertEqual(json.loads(p.read_text())["id"], rid)

    def test_rest_mark_symlinks_not_followed(self):
        os.symlink(self.victim, self.data / ".engine_restart.json.tmp")
        os.symlink(self.victim, self.data / ".engine_restart.json")
        self.ctl.write_rest_mark("alice")
        self.assert_victim()
        p = self.data / ".engine_restart.json"
        self.assertFalse(p.is_symlink())
        self.assertEqual(json.loads(p.read_text())["user"], "alice")

    def test_engine_alive_tmp_symlink_not_followed(self):
        boot = t11.load_boot()
        path = self.data / ".engine_alive.json"
        os.symlink(self.victim, str(path) + ".tmp")
        boot._write_engine_alive(str(path), {"alice": True}, {"alice": 1})
        self.assert_victim()
        self.assertFalse(path.is_symlink())
        self.assertEqual(stat.S_IMODE(path.lstat().st_mode), 0o600)
        self.assertEqual(json.loads(path.read_text())["running"], {"alice": True})
        # 생존 파일 이름·칸은 그대로(임시 파일 남지 않음 — 미리 둔 링크만 남음)
        left = sorted(n for n in os.listdir(self.data) if n.startswith(".engine_alive"))
        self.assertEqual(left, [".engine_alive.json", ".engine_alive.json.tmp"])

    def test_symlink_user_dir_skipped(self):
        rid = self.req()
        real = self.outside / "alice"
        os.rename(self.base / "alice", real)
        os.symlink(real, self.base / "alice")
        self.ctl.scan_once()
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(sorted(p.name for p in real.iterdir()), [f"req-{rid}.json"])   # 지우지도 쓰지도 않음
        self.assertEqual(len(_bad_alerts(self.notify)), 1)
        self.ctl.scan_once()
        self.assertEqual(len(_bad_alerts(self.notify)), 1)                             # 폴더당 1회

    def test_symlink_base_dir_skipped(self):
        rid = self.req()
        real = self.outside / "v2c"
        os.rename(self.base, real)
        os.symlink(real, self.base)
        self.ctl.scan_once()
        self.assertEqual(self.mgr.calls, [])
        self.assertTrue((real / "alice" / f"req-{rid}.json").exists())
        self.assertEqual(len(_bad_alerts(self.notify)), 1)

    def test_symlink_req_skipped(self):
        rid = self.req()
        d = self.base / "alice"
        target = self.outside / "req.json"
        os.rename(d / f"req-{rid}.json", target)
        before = target.read_text()
        os.symlink(target, d / f"req-{rid}.json")
        self.ctl.scan_once()
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(target.read_text(), before)                                    # 바깥 파일 그대로
        self.assertIsNone(self.result(rid))
        self.assertEqual(len(_bad_alerts(self.notify)), 1)

    def test_dir_mode_checked(self):
        rid = self.req()
        d = self.base / "alice"
        os.chmod(d, 0o770)                                                              # 그룹 쓰기 가능 → 건너뜀
        self.ctl.scan_once()
        self.assertEqual(self.mgr.calls, [])
        self.assertIsNone(self.result(rid))
        self.assertEqual(len(_bad_alerts(self.notify)), 1)
        os.chmod(d, 0o755)                         # 수정 2회차(N2): 읽기만 열려도 자동 chmod 없이 거부(권한 그대로)
        self.ctl.scan_once()
        self.assertIsNone(self.result(rid))
        self.assertEqual(stat.S_IMODE(d.lstat().st_mode), 0o755)
        os.chmod(d, 0o700)
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["status"], "done")


# ================================================================ 2. 사용자당 1건·30초 간격
class TestRateLimit(t11.CtlCase):
    def test_force_buy_ten_files_one_order(self):
        rids = [self.req("force_buy") for _ in range(10)]
        for _ in range(12):
            self.ctl.scan_once()
            self.clock.sleep(2)
        self.assertEqual([f[0] for f in self.forced], ["buy"])
        codes = [self.result(r)["code"] for r in rids]
        self.assertEqual(codes[0], "ok")
        self.assertEqual(codes[1:], ["too_frequent"] * 9)
        freq = [c for c in self.notify.call_args_list if cr.CODE_TEXT["too_frequent"] in c.args[2]]
        self.assertEqual(len(freq), 1)                                                  # 알림 1회
        for word in ("too_frequent", "T11", "force_"):
            self.assertNotIn(word, freq[0].args[1] + freq[0].args[2])

    def test_interval_30s_per_kind(self):
        self.req("force_buy")
        self.ctl.scan_once()
        self.req("force_sell")                                                          # 다른 종류는 막지 않음
        self.ctl.scan_once()
        self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        self.req("force_buy")
        self.ctl.scan_once()
        self.assertEqual([f[0] for f in self.forced], ["buy", "sell", "buy"])

    def test_one_per_user_per_scan(self):
        a1 = self.req("apply_params", created=self.clock.t - 3)
        a2 = self.req("apply_params", created=self.clock.t - 2)
        b1 = self.req("apply_params", user="bob", created=self.clock.t - 1)
        self.ctl.scan_once()
        self.assertIsNotNone(self.result(a1))
        self.assertIsNotNone(self.result(b1, user="bob"))
        self.assertIsNone(self.result(a2))                                              # 다음 회차
        self.assertTrue((self.base / "alice" / f"req-{a2}.json").exists())
        self.ctl.scan_once()
        self.assertIsNotNone(self.result(a2))


# ================================================================ 14. 형식 오류 요청 → 운영자 CRITICAL 1회(폴더 단위)
class TestBadRequestAlert(t11.CtlCase):
    def test_bad_files_alert_once_per_dir(self):
        d = self.base / "alice"
        d.mkdir(parents=True, mode=0o700)
        (d / "req-broken.json").write_text("{nope")
        self.ctl.scan_once()
        alerts = _bad_alerts(self.notify)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].kwargs["dedupe_key"], "v2_control_bad:alice")
        title, body = alerts[0].args[1], alerts[0].args[2]
        for word in ("T11", "D3", "user_mismatch", "bad_request", "req-", "json"):
            self.assertNotIn(word, title + body, word)
        self.assertIn("운영자", title + body)
        # 같은 폴더의 id 오류·사용자 불일치는 다시 알리지 않음, 다른 폴더는 알림
        self.req(rid="bad-id", fname="req-badid.json")
        rid = self.req(body_user="bob")
        self.ctl.scan_once()
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "user_mismatch")
        self.assertEqual(len(_bad_alerts(self.notify)), 1)
        e = self.base / "carol"
        e.mkdir(mode=0o700)
        (e / "req-x.json").write_text("[1]")
        self.ctl.scan_once()
        self.assertEqual([c.kwargs["dedupe_key"] for c in _bad_alerts(self.notify)],
                         ["v2_control_bad:alice", "v2_control_bad:carol"])

    def test_user_mismatch_alerts(self):
        self.req(body_user="bob")
        self.ctl.scan_once()
        self.assertEqual(len(_bad_alerts(self.notify)), 1)
        self.assertEqual(self.starts(), [])


# ================================================================ 8. 엔진 시작 생존 확인
class TestEngineStartAlive(t11.CtlCase):
    def test_thread_dies_soon_start_failed(self):
        def on_start(u, mode, strategy):
            self.mgr._threads[u] = t11.FakeThread(self.clock, self.clock.t + 1)
        self.mgr.on_start = on_start
        rid = self.req("engine_start")
        self.ctl.scan_once()
        r = self.result(rid)
        self.assertEqual(r["code"], "start_failed")
        self.assertIn("시작하지 못했습니다", r["message"])
        self.assertGreaterEqual(self.clock.t - t11.T0, 1)

    def test_thread_alive_started_after_check(self):
        rid = self.req("engine_start")
        t0 = self.clock.t
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "started")
        self.assertGreaterEqual(self.clock.t - t0, cr.START_CHECK_SEC)

    def test_start_false_returns_running_code(self):
        self.mgr.start_ok = False

        def on_start(u, mode, strategy):
            self.mgr.mode = "LIVE"                                                       # 그 사이 다른 모드가 뜸
        self.mgr.on_start = on_start
        rid = self.req("engine_start", mode="TEST")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "mode_conflict")
        self.assertEqual([c[0] for c in self.mgr.calls], ["start"])                     # 끄지 않음


# ================================================================ 5·6·7. 재시작
class TestRestartFix(t11.CtlCase):
    def setUp(self):
        super().setUp()

        def on_start(u, mode, strategy):
            ev = threading.Event()
            ev.set()
            self.mgr._ready[u] = ev
            self.mgr._threads[u] = t11.FakeThread(self.clock, None)
        self.mgr.on_start = on_start

    def test_no_stop_when_engine_absent(self):
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual(r["status"], "done", r)
        self.assertEqual([c[0] for c in self.mgr.calls], ["start"])

    def test_fail_start_does_not_stop_absent_engine(self):
        self.mgr.start_ok = False
        self.mgr.on_start = None
        r = self.ctl.restart_engine(USER, "LIVE", "EMA")
        self.assertEqual(r["code"], "start_failed")
        self.assertEqual([c[0] for c in self.mgr.calls], ["start"])                     # LIVE 수 깎는 정지 없음
        self.assertIn(USER, self.mgr._no_recover)

    def test_start_false_already_running_returned(self):
        self.mgr.start_ok = False

        def on_start(u, mode, strategy):
            self.mgr.mode = mode
        self.mgr.on_start = on_start
        r = self.ctl.restart_engine(USER, "TEST", "EMA")
        self.assertEqual((r["status"], r["code"]), ("rejected", "already_running"))
        self.assertEqual([c[0] for c in self.mgr.calls], ["start"])
        self.assertNotIn(USER, self.mgr._no_recover)

    def test_waits_stale_thread_by_name(self):
        """정지 시간 초과로 관리자 표에서 빠진 옛 엔진 스레드(이름)·매매 루프 스레드도 끝날 때까지 기다린다."""
        for name in (f"engine_runner_{USER}_TEST", f"run_live_loop_{USER}_TEST"):
            release = threading.Event()
            th = threading.Thread(target=release.wait, name=name, daemon=True)
            th.start()
            self.addCleanup(th.join, 2)
            self.addCleanup(release.set)
            self.mgr.calls.clear()
            r = self.ctl.restart_engine(USER, "TEST", "EMA")
            self.assertEqual(r["code"], "old_thread_alive", name)
            self.assertEqual(self.starts(), [])
            release.set()
            th.join(2)
        # 다른 사용자 이름(접두만 같음)은 기다리지 않음
        release = threading.Event()
        th = threading.Thread(target=release.wait, name=f"engine_runner_{USER}_x_TEST", daemon=True)
        th.start()
        self.addCleanup(release.set)
        r = self.ctl.restart_engine(USER, "TEST", "EMA")
        self.assertEqual(r["status"], "done")
        release.set()

    def test_engine_start_refused_while_stale_thread(self):
        release = threading.Event()
        th = threading.Thread(target=release.wait, name=f"engine_runner_{USER}_LIVE", daemon=True)
        th.start()
        self.addCleanup(release.set)
        rid = self.req("engine_start", user=USER)
        self.ctl.scan_once()
        self.assertEqual(self.result(rid, user=USER)["code"], "old_engine_alive")
        self.assertEqual(self.starts(), [])


# ================================================================ 11. 실행 시작 뒤 120초 상한
class TestExecWaitCap(t11.CtlCase):
    def test_started_never_done_result_unknown(self):
        class StartQ:
            def put(self_q, item):
                with item.lock:
                    item.started = True                                                 # 엔진이 꺼냈지만 끝나지 않음
        eng = SimpleNamespace(control_queue=StartQ())
        self.mgr.mode = "TEST"
        with mock.patch.object(ec, "running_engine", return_value=eng):
            rid = self.req("force_sell")
            t0 = self.clock.t
            self.ctl.scan_once()
        r = self.result(rid)
        self.assertEqual((r["status"], r["code"]), ("error", "result_unknown"))
        self.assertGreaterEqual(self.clock.t - t0, cr.EXEC_WAIT_SEC)
        self.assertLess(self.clock.t - t0, cr.EXEC_WAIT_SEC + 30)


# ================================================================ 3. 새 전략 강제 매수 고침
class TestPullbackForceFix(T6Case):
    def setUp(self):
        super().setUp()
        ec._RUNNING.clear()
        self.addCleanup(ec._RUNNING.clear)
        self.mgr = t11.FakeMgr(mode="TEST")
        self.tmpd = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpd.cleanup)
        self._n = 0

    def ctl(self):
        d = Path(self.tmpd.name)
        return cr.Controller(base_dir=d / "v2_control", alive_dir=d, manager=self.mgr, notify=mock.MagicMock())

    def req(self):
        self._n += 1
        return {"id": "20261028000000-%08x" % self._n, "user_id": USER, "mode": "TEST", "kind": "force_buy",
                "payload": {}}

    def force(self, eng):
        with t11.EngineLoop(eng):
            return self.ctl().execute(self.req())

    def test_sell_then_force_buy_before_next_bar(self):
        """강제 매도(엔진 밖 체결로 지갑 0) 뒤 다음 봉 전에 강제 매수 → 1회차·새 기준 수량·desync 없음."""
        trader = t11.RatioTrader()
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        ec.attach(eng, USER, threading.Event())
        r1 = self.force(eng)
        self.assertEqual((r1["status"], r1["detail"]["round"]), ("done", 1), r1)
        self.assertGreater(eng._pb_qty, 0)
        trader.coin = 0.0                                                               # 강제 매도 체결(다음 봉 전)
        before = len(trader.buy_calls)
        r2 = self.force(eng)
        self.assertEqual(r2["status"], "done", r2)
        self.assertEqual(r2["detail"]["round"], 1)
        self.assertEqual(eng.strategy.entry_count, 1)
        self.assertEqual(trader.buy_calls[before]["meta"]["split_round"], 1)
        self.assertFalse(eng._pullback_desync)
        self.assertAlmostEqual(eng._pb_qty, trader.coin)                                 # 새 매수 수량만

    def test_reject_restores_ring_armed(self):
        trader = t11.RatioTrader()
        trader.avail = 10                                                               # 잔고 부족 → 건너뜀
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        st = eng.strategy
        st.armed = True
        self.assertTrue(st.ring.amend_last_split(st.last_ts, st))
        ec.attach(eng, USER, threading.Event())
        r = self.force(eng)
        self.assertEqual(r["status"], "rejected")
        self.assertTrue(st.armed)
        self.assertTrue(st.ring._q[-1].split_state["armed"])                            # 링 기록도 armed 그대로

    def test_pending_fill_flag_rejects(self):
        trader = t11.RatioTrader()
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        eng.strategy.pending_fill = True
        ec.attach(eng, USER, threading.Event())
        r = self.force(eng)
        self.assertEqual(r["code"], "fill_pending")
        self.assertEqual(trader.buy_calls, [])


# ================================================================ 10. 준비 Event·세대·실행 중 표
class TestReadyBinding(unittest.TestCase):
    def setUp(self):
        ec._RUNNING.clear()
        self.addCleanup(ec._RUNNING.clear)
        self.addCleanup(ec.READY.pop, USER, None)

    def test_attach_ignores_event_of_other_start(self):
        mine, other = threading.Event(), threading.Event()
        ev = threading.Event()
        ev.stop_event = other
        ec.READY[USER] = ev
        eng = SimpleNamespace()
        ec.attach(eng, USER, mine)
        self.assertIsNone(eng._control_ready_event)
        ev.stop_event = mine
        eng2 = SimpleNamespace()
        ec.attach(eng2, USER, mine)
        self.assertIs(eng2._control_ready_event, ev)

    def test_mark_ready_skips_when_stopping(self):
        stop = threading.Event()
        ev = threading.Event()
        ev.stop_event = stop
        ec.READY[USER] = ev
        eng = SimpleNamespace(strategy_type="EMA")
        ec.attach(eng, USER, stop)
        stop.set()
        self.assertFalse(ec.mark_ready(eng, USER))
        self.assertFalse(ev.is_set())

    def test_detach_removes_own_entry_only(self):
        s1, s2 = threading.Event(), threading.Event()
        e1 = SimpleNamespace()
        ec.attach(e1, USER, s1)
        ec.detach(USER, s2)
        self.assertIs(ec.running_engine(USER), e1)
        ec.detach(USER, s1)
        self.assertNotIn(USER, ec._RUNNING)
        self.assertIsNone(ec.running_engine(USER))

    def test_runner_finally_detaches(self):
        src = (ROOT / "engine" / "engine_manager.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "_engine_runner")
        tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try) and n.finalbody]
        text = "\n".join(ast.unparse(s) for t in tries for s in t.finalbody)
        self.assertIn("detach(user_id, stop_event)", text)


class TestManagerBinding(t11.MgrCase):
    def test_ready_event_bound_to_stop_event(self):
        self.em.start_engine(USER, mode="TEST")
        self.wait_runner()
        self.assertIs(self.em._ready[USER].stop_event, self.em._events[USER])
        self.em.stop_engine(USER, mode="TEST")

    def test_override_restored_on_exception(self):
        self.em._strategy_override[USER] = "EMA"
        with mock.patch.object(self.em, "_start_engine_locked", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.em.start_engine(USER, mode="TEST", strategy="PULLBACK")
        self.assertEqual(self.em._strategy_override.get(USER), "EMA")


# ================================================================ 9. 엔진 없을 때 전략·종목
class TestNoEngineReads(unittest.TestCase):
    def test_active_strategy_uses_engine_rule(self):
        with mock.patch.object(engine_manager, "_decide_strategy_type", return_value="MACD") as d:
            self.assertEqual(cr._active_strategy("alice"), "MACD")
        d.assert_called_once_with("alice", None)

    def test_pullback_ticker_applied_only(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        applied, saved = Path(tmp.name) / "applied.json", Path(tmp.name) / "saved.json"
        saved.write_text(json.dumps({"ticker": "KRW-AAA", "interval": "minute3"}))
        with mock.patch.object(pbp, "applied_path", return_value=str(applied)), \
                mock.patch.object(pbp, "saved_path", return_value=str(saved)):
            self.assertIsNone(cr._ticker_and_interval("alice", "PULLBACK"))             # 저장본만 있으면 없음
            applied.write_text(json.dumps({"ticker": "KRW-BBB", "interval": "minute5"}))
            self.assertEqual(cr._ticker_and_interval("alice", "PULLBACK"), ("KRW-BBB", 300))


# ================================================================ 13·16. 용어·상수
class TestLabelsAndConstants(unittest.TestCase):
    def test_force_reason_label(self):
        from services import terminology as tm
        self.assertEqual(tm.PULLBACK_REASON_LABEL["FORCE"], "강제 매수")
        self.assertIn("강제 매수", tm.pullback_trade_text("BUY", "FORCE", {"split_round": 1}))

    def test_constants_same_in_both_modules(self):
        from v2 import candles as v2c
        from v2 import control as v2ctl
        self.assertEqual(cr.KINDS, v2ctl.KINDS)
        self.assertEqual(cr.REQUEST_TTL_SEC, v2ctl.REQUEST_TTL_SEC)
        self.assertEqual(cr.ID_RE.pattern, v2ctl.ID_RE.pattern)
        self.assertEqual(cr.MODES, v2ctl.MODES)
        self.assertEqual(cr.CONTROL_DIRNAME, v2ctl.CONTROL_DIRNAME)
        self.assertEqual(cr.REST_MARK_FILE, v2c.REST_MARK_FILE)
        self.assertEqual(cr.REST_MARK_SEC, v2c.COOLDOWN_PID)


# ================================================================ 4. live_loop 제어 함수 몸체 lint
EXPECTED_CONTROL_BODIES = {
    "_control_attach": (
        "try:\n    _engine_control.attach(engine, user_id, stop_event)\n"
        "except Exception as e:\n    logger.error(f'[CONTROL] 제어 큐 등록 실패(매매 무관) | {type(e).__name__}: {e}')\n"),
    "_control_ready": (
        "try:\n    _engine_control.mark_ready(engine, user_id)\n"
        "except Exception as e:\n    logger.error(f'[CONTROL] 준비 신호 실패(매매 무관) | {type(e).__name__}: {e}')\n"),
    "_control_drain": (
        "try:\n    _engine_control.drain_control_queue(engine)\n"
        "except Exception as e:\n    logger.error(f'[CONTROL] 제어 큐 처리 예외(매매 계속) | {type(e).__name__}: {e}')\n"),
}


class TestLiveLoopControlLint(unittest.TestCase):
    def test_control_function_bodies(self):
        tree = ast.parse((ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8"))
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("_control_")}
        self.assertEqual(set(fns), set(EXPECTED_CONTROL_BODIES))
        for name, fn in fns.items():
            body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                                   and isinstance(fn.body[0].value, ast.Constant)) else fn.body
            names = {getattr(n, "attr", None) for n in ast.walk(fn)} | {getattr(n, "id", None) for n in ast.walk(fn)}
            self.assertNotIn("_execution_lock", names, name)
            want = ast.parse(EXPECTED_CONTROL_BODIES[name]).body
            self.assertEqual([ast.dump(s) for s in body], [ast.dump(s) for s in want], name)


if __name__ == "__main__":
    unittest.main()
