"""
2차 T11 (결정 D3): 엔진 제어 요청 통로 — 엔진 쪽 시험.

- 감시 스레드(engine/control_requests.py): 중복·만료·한 번에 하나·예외 격리·결과 600·사용자 검사·종류별 알림.
- 세션 없는 엔진 경로(engine/engine_manager.py): start_engine(…, mode, strategy)·stop_engine(…, mode)·mode_conflict.
- 재시작(restart_engine): 쉼 표식 → stop → 옛 스레드 끝 대기(30초) → start → 준비 신호 대기(180초) — 가짜 시계.
- 엔진 제어 큐(core/engine_control.py): 엔진 스레드가 메인 루프 맨 앞에서 실행. 교착 없음은 실제 threading 으로.
- EMA 경로 무변경: 기준 커밋(baseline_commits.EMA_BASELINE_COMMIT) 원본과 비교(AST·같은 호출 흔적), WO-12 시험 전부.
- PULLBACK LIVE 기동 거부는 그대로.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p4_t11_control -v
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import queue
import stat
import sys
import tempfile
import threading
import time as _time
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import engine_control as ec  # noqa: E402
from core import strategy_engine as se  # noqa: E402
from core.candle_buffer import Bar  # noqa: E402
import engine.engine_manager as engine_manager  # noqa: E402
import engine.live_loop as live_loop  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from tests.regressions import baseline_commits as bc  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    DIP, EngineCase, FakeTrader, InTmpCwd, TICKER, USER, bar, boot, cfg, rising_df, run_engine_runner,
)
from tests.regressions.test_r_2026_10_28_p3_t6_split_position import LiveFakeTrader, T6Case  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
T0 = 1_800_000_000.0


# ================================================================ 도우미
class FakeClock:
    def __init__(self, t=T0):
        self.t = t
        self.hooks = []
        self.slept = 0.0

    def now(self):
        return self.t

    def mono(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept += s
        for h in list(self.hooks):
            h(self.t)


class FakeThread:
    """is_alive 가 가짜 시계 기준 dies_at 전까지 참."""

    def __init__(self, clock, dies_at):
        self.clock, self.dies_at = clock, dies_at

    def is_alive(self):
        return self.dies_at is None or self.clock.t < self.dies_at


class FakeMgr:
    """engine_manager 대역(감시 스레드가 부르는 면만)."""

    def __init__(self, clock=None, mode=None):
        self.clock = clock
        self.mode = mode
        self.calls = []
        self._threads = {}
        self._ready = {}
        self._no_recover = set()
        self.on_start = None
        self.on_stop = None
        self.start_ok = True
        self.start_raises = None

    def get_running_mode(self, u):
        return self.mode

    def start_engine(self, u, *, mode, strategy=None):
        self.calls.append(("start", u, mode, strategy))
        if self.start_raises is not None:
            raise self.start_raises
        if self.start_ok:   # 수정 1회차: 엔진 시작 생존 확인용 — 기본은 살아 있는 엔진 스레드(on_start 가 바꿀 수 있음)
            self._threads[u] = FakeThread(self.clock, None)
        if self.on_start:
            self.on_start(u, mode, strategy)
        if self.start_ok:
            self.mode = mode
        return self.start_ok

    def stop_engine(self, u, *, mode=None):
        self.calls.append(("stop", u, mode))
        if self.on_stop:
            self.on_stop(u, mode)
        self.mode = None


def kst_iso(t):
    return datetime.fromtimestamp(t, KST).isoformat()


class CtlCase(unittest.TestCase):
    """임시 폴더·가짜 시계·가짜 관리자로 Controller 를 만든다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "services" / "data"
        self.data.mkdir(parents=True)
        self.base = self.data / "v2_control"
        self.base.mkdir(mode=0o700)       # 수정 2회차: 신버전처럼 700(권한이 다르면 감시가 거부 — 자동 chmod 없음)
        os.chmod(self.base, 0o700)
        self.clock = FakeClock()
        self.notify = mock.MagicMock(return_value=True)
        self.mgr = FakeMgr(self.clock)
        self.forced = []
        # 저장소 실제 파일(활성 전략·설정)을 읽지 않게
        for name, value in (("_active_strategy", "EMA"), ("_ticker_and_interval", (TICKER, 60))):
            p = mock.patch.object(cr, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.ctl = self.make()
        self._n = 0

    def make(self, **kw):
        opts = dict(base_dir=self.base, alive_dir=self.data, manager=self.mgr, notify=self.notify,
                    now=self.clock.now, monotonic=self.clock.mono, sleep=self.clock.sleep,
                    trader_factory=lambda u, mode, strategy: SimpleNamespace(tag="standalone", user=u, mode=mode),
                    force_sell_fn=lambda u, trader, ticker, **k: self.forced.append(("sell", trader)) or "[TEST] ok",
                    force_buy_fn=lambda u, trader, ticker, **k: self.forced.append(("buy", trader)) or "[TEST] ok")
        opts.update(kw)
        return cr.Controller(**opts)

    def req(self, kind="engine_start", user="alice", body_user=None, mode="TEST", payload=None,
            created=None, rid=None, fname=None):
        self._n += 1
        created = self.clock.t if created is None else created
        rid = rid or (datetime.fromtimestamp(created, KST).strftime("%Y%m%d%H%M%S") + "-%08x" % self._n)
        d = self.base / user
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not d.is_symlink():
            os.chmod(d, 0o700)
        body = {"v": 1, "id": rid, "user_id": body_user or user, "mode": mode, "kind": kind,
                "payload": payload or {}, "created_at": kst_iso(created), "expires_at": kst_iso(created + 60)}
        p = d / (fname or f"req-{rid}.json")
        p.write_text(json.dumps(body), encoding="utf-8")
        return rid

    def result(self, rid, user="alice"):
        p = self.base / user / f"res-{rid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def starts(self):
        return [c for c in self.mgr.calls if c[0] == "start"]


# ================================================================ 감시 스레드: 파일 규칙
class TestControlFiles(CtlCase):
    def test_control_duplicate_ignored(self):
        rid = self.req(fname="req-a.json")
        self.req(rid=rid, fname="req-b.json")
        self.ctl.scan_once()
        self.ctl.scan_once()
        self.assertEqual(len(self.starts()), 1)
        self.assertEqual(self.result(rid)["status"], "done")
        self.assertEqual(sorted(p.name for p in (self.base / "alice").iterdir()), [f"res-{rid}.json"])
        # 결과가 남은 id 를 다시 보내도 실행 0
        self.req(rid=rid, fname="req-c.json")
        self.ctl.scan_once()
        self.assertEqual(len(self.starts()), 1)

    def test_control_expired_60s(self):
        rid = self.req(created=self.clock.t - 61)
        self.ctl.scan_once()
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.result(rid)["status"], "expired")
        # 본문의 expires_at 을 늘려도 created_at + 60초가 상한
        rid2 = self.req(created=self.clock.t - 61)
        p = self.base / "alice" / f"req-{rid2}.json"
        body = json.loads(p.read_text())
        body["expires_at"] = kst_iso(self.clock.t + 3600)
        p.write_text(json.dumps(body))
        self.ctl.scan_once()
        self.assertEqual(self.result(rid2)["status"], "expired")
        self.assertEqual(self.starts(), [])

    def test_control_one_at_a_time(self):
        """두 요청 → created_at 순으로 1건씩. 두 스레드가 동시에 훑어도 동시 실행 0."""
        active, peak, order = [0], [0], []
        lock = threading.Lock()

        def on_start(u, mode, strategy):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            _time.sleep(0.05)
            with lock:
                active[0] -= 1

        ctl = self.make(now=_time.time, monotonic=_time.monotonic, sleep=_time.sleep, start_check=0.0)
        self.mgr.on_start = on_start
        self.mgr.on_stop = lambda u, m: order.append("stop")
        later = self.req("engine_start", created=_time.time() - 1)
        first = self.req("engine_stop", created=_time.time() - 2)
        self.mgr.mode = "TEST"
        ts = [threading.Thread(target=ctl.scan_once) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=5)
        self.assertEqual(peak[0], 1)
        self.assertEqual([c[0] for c in self.mgr.calls], ["stop", "start"])   # 먼저 만든 요청부터
        self.assertEqual(self.result(first)["status"], "done")
        self.assertEqual(self.result(later)["status"], "done")
        self.assertIs(cr.Controller._GLOBAL_LOCK, ctl._GLOBAL_LOCK)

    def test_control_thread_exception_isolated(self):
        self.mgr.start_raises = RuntimeError("boom")
        bad = self.req("engine_start", created=self.clock.t - 2)
        ok = self.req("engine_stop", created=self.clock.t - 1)
        self.mgr.mode = None
        orig = self.mgr.start_engine

        def start_once(*a, **k):
            try:
                return orig(*a, **k)
            finally:
                self.mgr.start_raises = None
        self.mgr.start_engine = start_once
        self.ctl.scan_once()
        self.ctl.scan_once()            # 수정 1회차: 한 번 훑을 때 사용자당 1건 — 다음 요청은 다음 회차
        self.assertEqual(self.result(bad)["status"], "error")
        self.assertEqual(self.result(bad)["code"], "exception")
        self.assertNotIn("boom", json.dumps(self.result(bad)))     # 예외 문자열은 결과에 넣지 않음
        self.assertIn(self.result(ok)["status"], ("done", "rejected"))  # 다음 요청은 정상 처리

    def test_control_loop_survives_scan_exception(self):
        stop = threading.Event()
        calls = {"n": 0}

        class Boom(cr.Controller):
            def scan_once(self_inner):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("scan broken")
                stop.set()
                return []
        ctl = Boom(base_dir=self.base, alive_dir=self.data, manager=self.mgr, notify=self.notify,
                   now=self.clock.now, monotonic=self.clock.mono, sleep=self.clock.sleep)
        with self.assertLogs("engine.control_requests", "ERROR") as cm:
            cr.control_loop(stop=stop, controller=ctl, wait=lambda s: self.clock.sleep(s) or stop.is_set())
        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(cm.records), 1)
        self.assertGreaterEqual(self.clock.slept, cr.LOOP_ERROR_SLEEP_SEC)

    def test_control_result_file_600(self):
        old = os.umask(0o022)
        try:
            rid = self.req()          # 폴더는 700(수정 2회차: 755 폴더는 거부) — 엔진 UMask 0022 에서도 결과 600
            self.ctl.scan_once()
        finally:
            os.umask(old)
        p = self.base / "alice" / f"res-{rid}.json"
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertFalse(any(n.name.startswith(".") for n in (self.base / "alice").iterdir()))
        src = (ROOT / "core" / "safe_file.py").read_text(encoding="utf-8")   # 수정 1회차: 쓰기 도우미로 옮김
        self.assertIn("0o600", src)
        self.assertIn("os.fchmod", src)

    def test_results_keep_last_50(self):
        for i in range(55):
            rid = self.req(created=self.clock.t)
            self.ctl.scan_once()
            self.clock.t += 1
        names = [p.name for p in (self.base / "alice").iterdir()]
        self.assertEqual(len(names), 50)
        self.assertTrue(all(n.startswith("res-") for n in names))
        self.assertIn(f"res-{rid}.json", names)

    def test_control_user_mismatch_rejected(self):
        rid = self.req(user="alice", body_user="bob")
        self.ctl.scan_once()
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.result(rid)["code"], "user_mismatch")
        # 정규식 밖 폴더는 읽지도 쓰지도 않음
        bad = self.base / "a-b"
        bad.mkdir(parents=True)
        (bad / "req-x.json").write_text(json.dumps({"user_id": "a-b", "kind": "engine_start"}))
        self.ctl.scan_once()
        self.assertEqual(self.starts(), [])
        self.assertEqual(sorted(p.name for p in bad.iterdir()), ["req-x.json"])
        # 깨진 파일 → bad_request, 실행 0
        d = self.base / "alice"
        (d / "req-broken.json").write_text("{nope")
        self.ctl.scan_once()
        self.assertEqual(self.starts(), [])
        self.assertFalse((d / "req-broken.json").exists())

    def test_control_mode_conflict(self):
        self.mgr.mode = "TEST"
        rid = self.req("engine_start", mode="LIVE")
        self.ctl.scan_once()
        self.assertEqual(self.starts(), [])
        r = self.result(rid)
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"))
        rid = self.req("force_sell", mode="LIVE")
        self.ctl.scan_once()
        self.assertEqual(self.forced, [])
        self.assertEqual(self.result(rid)["code"], "mode_conflict")

    def test_unknown_and_later_task_kinds(self):
        rid = self.req("rm_rf")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "bad_request")
        for kind in ("switch", "revert", "cancel_reservation", "apply_params", "ops_settings"):
            rid = self.req(kind)
            self.ctl.scan_once()
            self.assertEqual((self.result(rid)["status"], self.result(rid)["code"]), ("rejected", "not_ready"), kind)
        self.assertEqual(self.mgr.calls, [])


# ================================================================ 종류별 알림 (S1)
class TestNotify(CtlCase):
    def test_request_notify_per_kind(self):
        sensitive = ("force_buy", "force_sell", "switch", "revert", "engine_stop")
        ids = {}
        for kind in sensitive:
            self.notify.reset_mock()
            rid = ids[kind] = self.req(kind)
            self.ctl.scan_once()
            self.assertEqual(self.notify.call_count, 1, kind)
            c = self.notify.call_args
            self.assertEqual(c.kwargs["dedupe_key"], f"v2_control:{rid}")
            title, body = c.args[1], c.args[2]
            self.assertIn(cr.KIND_LABEL[kind], title)
            self.assertIn("직접 요청하지 않으셨다면", body)
            for word in ("T11", "D3", "force_", "rejected", "done", "PULLBACK", "engine_"):
                self.assertNotIn(word, title + body, (kind, word))
        # 같은 요청 id 는 다시 알리지 않음(결과 파일이 있어 실행·알림 0)
        self.notify.reset_mock()
        self.req("force_sell", rid=ids["force_sell"], fname="req-again.json")
        self.ctl.scan_once()
        self.notify.assert_not_called()
        # 그 밖 종류는 결과 알림 1회, 할 일 없음 끝맺음
        for kind in ("engine_start", "apply_params", "ops_settings", "cancel_reservation"):
            self.notify.reset_mock()
            self.mgr.mode = None
            self.req(kind)
            self.ctl.scan_once()
            self.assertEqual(self.notify.call_count, 1, kind)
            self.assertTrue(self.notify.call_args.args[2].endswith(se.NO_ACTION_TEXT), kind)

    def test_expired_and_rejected_still_notify_once(self):
        self.req("force_buy", created=self.clock.t - 120)
        self.ctl.scan_once()
        self.assertEqual(self.notify.call_count, 1)
        self.assertIn("시간이 지나", self.notify.call_args.args[2])


# ================================================================ 강제 매매 — 엔진이 없을 때
class TestForceNoEngine(CtlCase):
    def setUp(self):
        super().setUp()
        self.active = "EMA"
        p = mock.patch.object(cr, "_active_strategy", side_effect=lambda u: self.active)
        p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch.object(cr, "_ticker_and_interval", return_value=(TICKER, 60))
        p2.start()
        self.addCleanup(p2.stop)

    def test_force_sell_without_engine_uses_new_trader(self):
        rid = self.req("force_sell")
        self.ctl.scan_once()
        self.assertEqual([f[0] for f in self.forced], ["sell"])
        self.assertEqual(self.forced[0][1].tag, "standalone")
        self.assertEqual(self.result(rid)["status"], "done")

    def test_pullback_force_buy_requires_engine(self):
        self.active = "PULLBACK"
        rid = self.req("force_buy")
        self.ctl.scan_once()
        self.assertEqual(self.forced, [])
        self.assertEqual(self.result(rid)["code"], "engine_required")


# ================================================================ 엔진 제어 큐 (엔진 스레드에서 실행)
class EngineLoop:
    """엔진 메인 루프 대역: 맨 앞에서 drain_control_queue, 그다음 「봉 처리」(실행 잠금 안, 지연 선택)."""

    def __init__(self, engine, bar_delay=0.0, log=None):
        self.engine = engine
        self.bar_delay = bar_delay
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.bars = 0
        self.log = log if log is not None else []
        self.thread = threading.Thread(target=self.run, name="engine_loop_fake", daemon=True)

    def run(self):
        while not self.stop.is_set():
            if self.paused.is_set():
                _time.sleep(0.005)
                continue
            ec.drain_control_queue(self.engine)
            with self.engine._execution_lock:
                self.log.append(("bar_start", _time.monotonic()))
                if self.bar_delay:
                    _time.sleep(self.bar_delay)
                self.bars += 1
                self.log.append(("bar_end", _time.monotonic()))
            _time.sleep(0.002)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.thread.join(timeout=5)


class CountingLock:
    def __init__(self):
        self._l = threading.Lock()
        self.acquired_by = []

    def acquire(self, *a, **k):
        ok = self._l.acquire(*a, **k)
        if ok:
            self.acquired_by.append(threading.current_thread().name)
        return ok

    def release(self):
        self._l.release()

    def locked(self):
        return self._l.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *a):
        self.release()


class RatioTrader(FakeTrader):
    """EMA 강제 매수용: risk_pct(= order_ratio) 를 들고, 지정가는 uuid 를 돌려준다."""

    def __init__(self, test_mode=True, risk_pct=0.3, limit_delay=0.0):
        super().__init__(test_mode=test_mode)
        self.risk_pct = risk_pct
        self.limit_delay = limit_delay
        self.in_buy_limit = threading.Event()
        self.threads = []

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        self.threads.append(threading.current_thread().name)
        return super().buy_market(price, ticker, ts=ts, meta=meta, krw_amount=krw_amount, strict_amount=strict_amount)

    def buy_limit(self, price, ticker, ts=None, meta=None, interval_sec=None):
        self.limit_calls.append({"price": price, "meta": dict(meta or {})})
        self.threads.append(threading.current_thread().name)
        self.in_buy_limit.set()
        if self.limit_delay:
            _time.sleep(self.limit_delay)
        return {"limit_pending": True, "uuid": "LIM1", "qty": 0.0, "price": price, "used_krw": 1000.0}


class QueueCase(EngineCase):
    """실제 StrategyEngine + 가짜 trader. services.trading_control 의 DB 조회는 막는다."""

    def setUp(self):
        super().setUp()
        self.conds = {"buy": {}}
        tc_patches = [
            mock.patch("services.trading_control.fetch_latest_log_signal", return_value={"price": 100.0}),
            mock.patch("services.trading_control.fetch_latest_log_signal_ema", return_value=None),
            mock.patch("services.trading_control.fetch_latest_sell_eval", return_value=None),
            mock.patch("services.trading_control.fetch_latest_buy_eval", return_value=None),
            mock.patch("services.trading_control.insert_log"),
            mock.patch("services.trading_control.get_reconciler", return_value=mock.MagicMock()),
            mock.patch("services.trading_control._load_force_buy_conditions", side_effect=lambda u, s: self.conds),
        ]
        for p in tc_patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.mgr = FakeMgr()
        self.notify_ctl = mock.MagicMock()
        ec._RUNNING.clear()
        self.addCleanup(ec._RUNNING.clear)

    def ctl(self, **kw):
        opts = dict(base_dir=self.data / "v2_control", alive_dir=self.data, manager=self.mgr,
                    notify=self.notify_ctl)
        opts.update(kw)
        return cr.Controller(**opts)

    def ema_engine(self, trader):
        eng = self.make(trader=trader, strategy_type="EMA")
        eng.buffer.append(bar(0))
        stop = threading.Event()
        ec.attach(eng, USER, stop)
        self.mgr.mode = "TEST" if trader.test_mode else "LIVE"
        return eng

    def run_req(self, ctl, kind, mode=None):
        mode = mode or self.mgr.mode
        return ctl.execute({"id": "20261028000000-0000000a", "user_id": USER, "mode": mode,
                            "kind": kind, "payload": {}})


class TestControlQueue(QueueCase):
    def test_control_queue_empty_no_effect(self):
        """큐가 비면 아무 일 없음: 엔진에 손대지 않음·0 반환. 큐가 없는 엔진(attach 전)도 0."""
        eng = mock.MagicMock(spec=["control_queue"])
        eng.control_queue = queue.Queue()
        self.assertEqual(ec.drain_control_queue(eng), 0)
        self.assertEqual(eng.mock_calls, [])
        self.assertEqual(ec.drain_control_queue(SimpleNamespace()), 0)
        # 실제 엔진: 빈 큐를 비운 뒤에도 봉 판정·주문 상태 그대로
        e1 = self.make(values=[V()] * 40)
        ec.attach(e1, USER, threading.Event())
        before = (e1.bar_count, e1.last_bar_ts, e1.position.has_position, list(e1.trader.buy_calls))
        self.assertEqual(ec.drain_control_queue(e1), 0)
        self.assertEqual(before, (e1.bar_count, e1.last_bar_ts, e1.position.has_position, list(e1.trader.buy_calls)))

    def test_control_force_sell(self):
        trader = RatioTrader()
        eng = self.ema_engine(trader)
        trader.coin = 5.0
        with mock.patch("services.trading_control.force_liquidate", return_value="[TEST] 강제청산 완료") as fl:
            with EngineLoop(eng):
                r = self.run_req(self.ctl(), "force_sell")
        self.assertEqual(r["status"], "done")
        fl.assert_called_once()
        self.assertIs(fl.call_args.args[1], eng.trader)            # 엔진 프로세스 trader
        self.assertEqual(fl.call_args.args[2], TICKER)

    def test_control_force_buy_ema_ratio(self):
        """EMA: 엔진 trader(risk_pct = order_ratio)로 시장가 1회 — 잔고 × order_ratio 는 trader 가 정한다(금액 인자 없음)."""
        trader = RatioTrader(risk_pct=0.3)
        eng = self.ema_engine(trader)
        with EngineLoop(eng):
            r = self.run_req(self.ctl(), "force_buy")
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(len(trader.buy_calls), 1)
        self.assertIsNone(trader.buy_calls[0]["krw_amount"])
        self.assertFalse(trader.buy_calls[0]["strict_amount"])
        self.assertEqual(trader.limit_calls, [])
        self.assertEqual(eng.trader.risk_pct, 0.3)
        self.assertEqual(trader.threads, ["engine_loop_fake"])       # 엔진 스레드에서

    def test_ema_force_buy_called_outside_lock(self):
        trader = RatioTrader()
        eng = self.ema_engine(trader)
        seen = []
        real = se.StrategyEngine  # noqa: F841
        import services.trading_control as tc
        orig = tc.force_buy_in

        def spy(*a, **k):
            seen.append(eng._execution_lock.locked())
            return orig(*a, **k)
        with mock.patch.object(tc, "force_buy_in", side_effect=spy):
            with EngineLoop(eng):
                self.run_req(self.ctl(), "force_buy")
        self.assertEqual(seen, [False])

    def test_control_queue_timeout_cancels(self):
        """엔진 루프를 멈춰 둠 → 20초(가짜 시계) 뒤 engine_busy, 그 뒤 루프를 풀어도 주문 0."""
        trader = RatioTrader()
        eng = self.ema_engine(trader)
        clock = FakeClock()
        ctl = self.ctl(now=clock.now, monotonic=clock.mono, sleep=clock.sleep)
        with EngineLoop(eng) as loop:
            loop.paused.set()
            r = self.run_req(ctl, "force_buy")
            self.assertEqual((r["status"], r["code"]), ("error", "engine_busy"))
            self.assertGreaterEqual(clock.slept, cr.QUEUE_WAIT_SEC)
            loop.paused.clear()
            _time.sleep(0.1)
        self.assertEqual(trader.buy_calls, [])
        self.assertEqual(eng.control_queue.qsize(), 0)

    def test_started_item_waits_until_finished(self):
        """실행이 시작된 항목은 취소하지 않고 끝날 때까지 기다린다(늦은 이중 주문 없음)."""
        item = ec.ControlItem("force_buy")
        self.assertTrue(item.try_cancel())
        item2 = ec.ControlItem("force_buy")
        item2.started = True
        self.assertFalse(item2.try_cancel())
        self.assertFalse(item2.cancelled)

    def test_engine_registered_but_not_attached_is_busy(self):
        """엔진 관리자는 실행 중인데 등록된 엔진이 없음(기동 중) → engine_busy, 주문 0."""
        self.mgr.mode = "TEST"
        r = self.run_req(self.ctl(), "force_sell", mode="TEST")
        self.assertEqual((r["status"], r["code"]), ("error", "engine_busy"))


class TestNoDeadlock(QueueCase):
    """교착 없음 증명 — 실제 threading, 각 시험은 join(timeout=5) 가 끝나는지로 판정."""

    def _run(self, fn):
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", fn()), name="control_watch_fake", daemon=True)
        t.start()
        t.join(timeout=5)
        self.assertFalse(t.is_alive(), "5초 안에 끝나지 않음(교착)")
        return out.get("r")

    def test_force_buy_fixed_price_no_deadlock(self):
        self.conds = {"buy": {"fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 3}}
        trader = RatioTrader(test_mode=False)
        eng = self.ema_engine(trader)
        lock = CountingLock()
        eng._execution_lock = lock
        inside = []
        orig = se.execute_force_buy_limit_atomic

        def spy(**k):
            n0 = len(lock.acquired_by)
            r = orig(**k)
            inside.append(len(lock.acquired_by) - n0)
            return r
        with mock.patch.object(se, "execute_force_buy_limit_atomic", side_effect=spy):
            with EngineLoop(eng) as loop:
                r = self._run(lambda: self.run_req(self.ctl(), "force_buy"))
                b0 = loop.bars
                _time.sleep(0.05)
                self.assertGreater(loop.bars, b0)                     # 엔진 루프가 다음 봉을 처리함
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(inside, [1])                                 # 지정가 원자 경로가 잠금을 1회 잡고 풂
        self.assertFalse(lock.locked())
        self.assertEqual(len(trader.limit_calls), 1)
        self.assertEqual(eng._pending_buy_uuid, "LIM1")

    def test_force_buy_with_concurrent_fill_callback(self):
        self.conds = {"buy": {"fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 3}}
        trader = RatioTrader(test_mode=False, limit_delay=0.2)
        eng = self.ema_engine(trader)
        fill = {}

        def reconciler():
            trader.in_buy_limit.wait(3)
            eng._on_limit_fill(uuid="LIM1", executed_price=100.0, executed_qty=10.0,
                               executed_ts=datetime.now(KST))
            fill["done"] = True
        rt = threading.Thread(target=reconciler, name="reconciler_fake", daemon=True)
        with EngineLoop(eng):
            rt.start()
            r = self._run(lambda: self.run_req(self.ctl(), "force_buy"))
            rt.join(timeout=5)
        self.assertFalse(rt.is_alive())
        self.assertEqual(r["status"], "done")
        self.assertTrue(fill.get("done"))
        self.assertTrue(eng.position.has_position)                   # uuid 매칭 성공(WO-8b 원자화 유지)
        self.assertAlmostEqual(eng.position.qty, 10.0)
        self.assertIsNone(eng._pending_buy_uuid)

    def test_force_sell_during_bar_processing_serialized(self):
        trader = RatioTrader()
        eng = self.ema_engine(trader)
        log = []

        def fake_liq(u, t, tk, **k):
            log.append(("sell_start", _time.monotonic()))
            log.append(("sell_end", _time.monotonic()))
            return "[TEST] ok"
        with mock.patch("services.trading_control.force_liquidate", side_effect=fake_liq):
            with EngineLoop(eng, bar_delay=1.0, log=log):
                _time.sleep(0.05)                                    # 봉 처리(1초) 도중에 요청
                r = self._run(lambda: self.run_req(self.ctl(), "force_sell"))
        self.assertEqual(r["status"], "done")
        names = [n for n, _ in log]
        i = names.index("sell_start")
        self.assertEqual(names[i - 1], "bar_end")                    # 봉 처리가 끝난 뒤 주문
        bars = [(log[k][1], log[k + 1][1]) for k in range(len(log) - 1)
                if log[k][0] == "bar_start" and log[k + 1][0] == "bar_end"]
        s = log[i][1]
        self.assertFalse(any(a < s < b for a, b in bars))            # 동시 실행 0

    def test_control_never_holds_execution_lock(self):
        tree = ast.parse((ROOT / "engine" / "control_requests.py").read_text(encoding="utf-8"))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn("_execution_lock", names)
        text = (ROOT / "engine" / "control_requests.py").read_text(encoding="utf-8")
        self.assertNotIn("_execution_lock", text)


# ================================================================ 강제 매수 — 새 전략(D6)
class TestPullbackForceBuy(T6Case):
    def setUp(self):
        super().setUp()
        ec._RUNNING.clear()
        self.addCleanup(ec._RUNNING.clear)
        self.mgr = FakeMgr(mode="TEST")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def ctl(self):
        d = Path(self.tmp.name)
        return cr.Controller(base_dir=d / "v2_control", alive_dir=d, manager=self.mgr, notify=mock.MagicMock())

    def req(self):
        return {"id": "20261028000000-0000000b", "user_id": USER, "mode": "TEST", "kind": "force_buy", "payload": {}}

    def test_control_force_buy_pullback_round(self):
        trader = RatioTrader()
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        ec.attach(eng, USER, threading.Event())
        per_buy = int(self.capital // eng.strategy.cfg["eff_max_splits"])
        with EngineLoop(eng):
            r = self.ctl().execute(self.req())
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(len(trader.buy_calls), 1)
        c = trader.buy_calls[0]
        self.assertEqual(c["krw_amount"], per_buy)
        self.assertTrue(c["strict_amount"])
        self.assertEqual(c["meta"]["reason"], "FORCE")
        self.assertEqual(c["meta"]["split_round"], 1)
        self.assertEqual(eng.strategy.entry_count, 1)
        self.assertEqual(eng.strategy.first_entry_reason, "FORCE")
        self.assertEqual(trader.threads, ["engine_loop_fake"])
        self.assertTrue(eng.position.has_position)
        # 같은 봉에서 다시 강제 매수 → 판정 체결 대기(pending_fill)라 거부(수정 1회차), 다음 봉 뒤 → 2회차
        with EngineLoop(eng):
            r_same = self.ctl().execute(dict(self.req(), id="20261028000000-0000000d"))
        self.assertEqual(r_same["code"], "fill_pending")
        self.feed(bar(1))
        self.assertFalse(eng.strategy.pending_fill)
        with EngineLoop(eng):
            r2 = self.ctl().execute(dict(self.req(), id="20261028000000-0000000c"))
        self.assertEqual(r2["detail"]["round"], 2)
        self.assertEqual(eng.strategy.entry_count, 2)

    def test_force_buy_pullback_not_placed_rolls_back(self):
        trader = RatioTrader()
        trader.avail = 10                                          # 잔고 부족 → 건너뜀
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        ec.attach(eng, USER, threading.Event())
        armed = eng.strategy.armed
        with EngineLoop(eng):
            r = self.ctl().execute(self.req())
        self.assertEqual((r["status"], r["code"]), ("rejected", "split_krw_short"))
        self.assertEqual(eng.strategy.entry_count, 0)
        self.assertEqual(eng.strategy.armed, armed)
        self.assertEqual(trader.buy_calls, [])

    def test_force_buy_pullback_rejected_while_fill_pending(self):
        """체결 대기(_pending_split) 중에는 거부 — 대기 칸이 하나뿐이라 덮어쓰면 앞 주문 체결을 잃는다(계획과 다른 점)."""
        eng = self.make(values=[V()] * 40, trader=LiveFakeTrader())
        self.feed(bar(0))
        eng._pending_split = {"uuid": "L0"}
        ec.attach(eng, USER, threading.Event())
        with EngineLoop(eng):
            r = self.ctl().execute(self.req())
        self.assertEqual(r["code"], "fill_pending")
        self.assertEqual(eng.trader.buy_calls, [])

    def test_force_buy_pullback_vs_fill_callback_serialized(self):
        """큐의 강제 매수가 잠금 안에서 _execute_pullback_buy 를 도는 동안 reconciler 가 _on_limit_fill → 겹치지 않음,
        분할 상태 qty = 두 체결 합(1회차 체결 + 강제 매수 2회차 체결)."""
        log = []

        class SlowLive(LiveFakeTrader):
            def buy_market(self_t, *a, **k):
                log.append(("buy_in", _time.monotonic()))
                _time.sleep(0.2)
                r = LiveFakeTrader.buy_market(self_t, *a, **k)
                log.append(("buy_out", _time.monotonic()))
                return r
        trader = SlowLive()
        eng = self.make(values=[V()] * 40, trader=trader)
        self.feed(bar(0))
        # 1회차(봉 판정)를 체결된 상태로 둔다
        eng.strategy.entry_count = 1
        eng.strategy.trade_origin = "live"
        eng._pending_split = {"uuid": "L0", "round": 1, "per_buy": 600_000, "bar": eng.bar_count, "bar_ts": bar(0).ts,
                              "base_qty": 0.0, "base_cost": 0.0, "reason": "PULLBACK"}
        trader.coin = 10.0
        eng._on_limit_fill(uuid="L0", executed_price=60_000.0, executed_qty=10.0, executed_ts=bar(0).ts)
        ec.attach(eng, USER, threading.Event())
        orig_fill = eng._pullback_apply_fill

        def spy_fill(**k):
            log.append(("fill_in", _time.monotonic()))
            r = orig_fill(**k)
            log.append(("fill_out", _time.monotonic()))
            return r
        eng._pullback_apply_fill = spy_fill

        def reconciler():
            while not any(n == "buy_out" for n, _ in log):
                _time.sleep(0.005)
            uuid = (eng._pending_split or {}).get("uuid") or "L2"
            trader.coin = 15.0
            eng._on_limit_fill(uuid=uuid, executed_price=60_000.0, executed_qty=5.0, executed_ts=bar(0).ts)
        rt = threading.Thread(target=reconciler, daemon=True)
        out = {}
        with EngineLoop(eng):
            rt.start()
            wt = threading.Thread(target=lambda: out.setdefault("r", self.ctl().execute(self.req())), daemon=True)
            wt.start()
            wt.join(timeout=5)
            rt.join(timeout=5)
        self.assertFalse(wt.is_alive() or rt.is_alive(), "교착")
        self.assertEqual(out["r"]["status"], "done", out)
        names = [n for n, _ in log]
        self.assertLess(names.index("buy_out"), names.index("fill_in"))   # 겹치지 않음
        self.assertAlmostEqual(eng._pb_qty, 15.0)
        self.assertEqual(eng.strategy.entry_count, 2)


# ================================================================ 세션 없는 엔진 경로 (engine_manager)
class MgrCase(unittest.TestCase):
    def setUp(self):
        self.em = engine_manager.EngineManager()
        self.stop_all = threading.Event()
        self.addCleanup(self.stop_all.set)
        self.runner_calls = []

        def fake_runner(user_id, stop_event, test_mode, captured_mode):
            self.runner_calls.append({"user": user_id, "test_mode": test_mode, "mode": captured_mode,
                                      "override": self.em._strategy_override.get(user_id)})
            while not stop_event.is_set() and not self.stop_all.is_set():
                _time.sleep(0.01)

        self.rec = mock.MagicMock()
        ps = [
            mock.patch.object(self.em, "_engine_runner", side_effect=fake_runner),
            mock.patch.object(engine_manager, "get_reconciler", return_value=self.rec),
            mock.patch("services.db.set_engine_status"),
            mock.patch.object(engine_manager, "set_engine_status"),
            mock.patch.object(engine_manager, "set_thread_status"),
            mock.patch.object(engine_manager, "update_engine_status"),
            mock.patch.object(engine_manager, "remove_engine_thread"),
            mock.patch.object(engine_manager, "insert_log"),
            mock.patch.object(engine_manager, "log_to_file"),
            mock.patch.object(engine_manager, "current_mode", side_effect=AssertionError("세션 모드 참조 금지")),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)

    def wait_runner(self, n=1):
        t0 = _time.time()
        while len(self.runner_calls) < n and _time.time() - t0 < 3:
            _time.sleep(0.005)


class TestSessionlessEngine(MgrCase):
    def test_control_engine_start_without_session(self):
        ok = self.em.start_engine(USER, mode="LIVE", strategy="PULLBACK")
        self.assertTrue(ok)
        self.wait_runner()
        self.assertEqual(self.runner_calls[0]["override"], "PULLBACK")
        self.assertEqual(self.runner_calls[0]["mode"], "LIVE")
        self.assertFalse(self.runner_calls[0]["test_mode"])
        self.assertEqual(self.em.get_running_mode(USER), "LIVE")
        self.em.stop_engine(USER, mode="LIVE")

    def test_control_engine_stop(self):
        self.em.start_engine(USER, mode="LIVE")
        self.wait_runner()
        t = self.em._threads[USER]
        self.em.stop_engine(USER, mode="LIVE")
        t.join(timeout=3)
        self.assertFalse(t.is_alive())
        self.assertIsNone(self.em.get_running_mode(USER))
        self.rec.stop.assert_called_once()                       # LIVE 카운트 0 → reconciler 정지

    def test_mode_lock_rejects_other_mode(self):
        self.em.start_engine(USER, mode="TEST")
        self.wait_runner()
        self.assertFalse(self.em.start_engine(USER, mode="LIVE", strategy="PULLBACK"))
        self.assertIsNone(self.em._strategy_override.get(USER))   # 거부된 시작은 지정 전략을 남기지 않음
        self.em.stop_engine(USER, mode="TEST")

    def test_override_cleared_by_plain_start(self):
        self.em.start_engine(USER, mode="TEST", strategy="PULLBACK")
        self.wait_runner()
        self.em.stop_engine(USER, mode="TEST")
        self.em.start_engine(USER, mode="TEST")
        self.wait_runner(2)
        self.assertIsNone(self.runner_calls[1]["override"])
        self.em.stop_engine(USER, mode="TEST")

    def test_gen_and_ready_per_internal_start(self):
        self.assertEqual(self.em.get_gen(USER), 0)
        self.em.start_engine(USER, mode="TEST")
        self.wait_runner()
        ev1 = self.em._ready[USER]
        self.assertEqual(self.em.get_gen(USER), 1)
        self.assertFalse(ev1.is_set())
        self.em.stop_engine(USER, mode="TEST")
        self.em.start_engine(USER, mode="TEST")
        self.wait_runner(2)
        self.assertEqual(self.em.gen_map(), {USER: 2})
        self.assertIsNot(self.em._ready[USER], ev1)
        self.assertIs(self.em._ready, ec.READY)
        self.em.stop_engine(USER, mode="TEST")


class TestRecovery(unittest.TestCase):
    def _run(self, mark: bool, mod=engine_manager):
        em = mod.EngineManager()
        internal = []
        real_internal = em._start_engine_internal

        def count_internal(**k):
            internal.append(k.get("restart_count"))
            return real_internal(**k)
        ps = [
            mock.patch.object(em, "_engine_runner", side_effect=RuntimeError("runner failed")),
            mock.patch.object(mod, "insert_log"),
            mock.patch.object(mod, "log_to_file"),
            mock.patch.object(mod.time, "sleep"),
            # 1028-15: 예외 종료가 이제 운영자 경보(services.notifier.send)를 탄다 — 실제 발송 시도 차단
            mock.patch("services.notifier.send", return_value=False),
        ]
        for p in ps:
            p.start()
        try:
            if mark:
                em._no_recover.add(USER)
            em._ensure_user_resources(USER, "TEST")
            with mock.patch.object(em, "_start_engine_internal", side_effect=count_internal):
                em._engine_runner_with_recovery(user_id=USER, stop_event=threading.Event(), test_mode=True,
                                                restart_count=0, captured_mode="TEST")
                waiter = threading.Event()   # time.sleep 은 가짜로 바꿔 두었으므로 Event 로 기다린다
                t0, stable_since, last_n = _time.monotonic(), _time.monotonic(), -1
                while _time.monotonic() - t0 < 3:
                    th = em._threads.get(USER)
                    if len(internal) != last_n or (th is not None and th.is_alive()):
                        last_n, stable_since = len(internal), _time.monotonic()
                    elif _time.monotonic() - stable_since > 0.2:
                        break
                    waiter.wait(0.01)
        finally:
            for p in reversed(ps):
                p.stop()
        return internal

    def test_failed_start_not_recovered(self):
        self.assertEqual(self._run(mark=True), [])                 # 실패 판정 표시 → 복구 래퍼 재시작 0
        # 1028-15 (나): 재시작 분기를 지웠다 — 표시가 없어도 재시작 0.
        # 이전에는 여기서 기준 커밋 원본과 같은 재시작 호출(첫 호출 restart_count=1)을 확인했으나, 그 호출은 가짜 runner
        # 라서만 보였다. 실제 _engine_runner 의 `finally: stop_event.set()`(D1)과 자기 스레드 판정(D3) 때문에 운영에서는
        # 한 번도 일어나지 않던 호출이었다(계획 docs/plans/2026-10-28-engine-recovery-fix/plan.md 1장).
        # 진짜 runner 를 거치는 재시작 0회 확인은 test_r_2026_10_29_engine_exit_alert.TestS5NoRestart 가 맡는다.
        self.assertEqual(self._run(mark=False), [])

    def test_start_engine_clears_no_recover(self):
        em = engine_manager.EngineManager()
        em._no_recover.add(USER)
        with mock.patch.object(em, "_start_engine_locked", return_value=True):
            em.start_engine(USER, mode="TEST")
        self.assertNotIn(USER, em._no_recover)


# ================================================================ 재시작 (가짜 시계)
class TestRestart(CtlCase):
    def setUp(self):
        super().setUp()
        self.mgr.mode = "TEST"
        self.mgr._threads[USER] = FakeThread(self.clock, None)
        self.order = []

        def on_stop(u, m):
            self.order.append(("stop", (self.data / ".engine_restart.json").exists()))
            th = self.mgr._threads.get(u)
            if getattr(th, "dies_on_stop", False):      # new_engine 이 띄운 가짜 엔진은 정지 요청에 바로 끝남
                th.dies_at = self.clock.t
        self.mgr.on_stop = on_stop

    def new_engine(self, ready_after=None, dies_after=None, fail=None):
        def on_start(u, mode, strategy):
            self.order.append(("start", strategy))
            ev = threading.Event()
            self.mgr._ready[u] = ev
            self.mgr._threads[u] = FakeThread(self.clock, None if dies_after is None else self.clock.t + dies_after)
            self.mgr._threads[u].dies_on_stop = True
            t_start = self.clock.t
            if ready_after is not None:
                self.clock.hooks.append(lambda t: ev.set() if t - t_start >= ready_after else None)
            if fail:
                ev.fail_reason = fail
        self.mgr.on_start = on_start

    def test_rest_mark_written_before_restart(self):
        self.mgr._threads[USER] = FakeThread(self.clock, self.clock.t)    # 옛 스레드 바로 끝남
        self.new_engine(ready_after=1)
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual(r["status"], "done", r)
        self.assertEqual(self.order, [("stop", True), ("start", "PULLBACK")])
        p = self.data / ".engine_restart.json"
        mark = json.loads(p.read_text())
        self.assertEqual(mark["user"], USER)
        self.assertEqual(mark["until"] - mark["at"], cr.REST_MARK_SEC)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_restart_waits_old_thread_exit(self):
        self.mgr._threads[USER] = FakeThread(self.clock, self.clock.t + 15)
        self.new_engine(ready_after=1)
        r = self.ctl.restart_engine(USER, "TEST", "EMA")
        self.assertEqual(r["status"], "done")
        self.assertEqual(len(self.starts()), 1)
        self.assertGreaterEqual(self.clock.t - T0, 15)
        # 40초 살아 있음 → start 0, old_thread_alive + CRITICAL
        self.mgr.calls.clear()
        self.mgr._threads[USER] = FakeThread(self.clock, self.clock.t + 40)
        self.notify.reset_mock()
        r = self.ctl.restart_engine(USER, "TEST", "EMA")
        self.assertEqual((r["status"], r["code"]), ("error", "old_thread_alive"))
        self.assertEqual(self.starts(), [])
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertEqual(len(crit), 1)
        self.assertIn("엔진 정지가 끝나지 않아 재시작을 멈췄습니다", crit[0].args[1] + crit[0].args[2])

    def test_restart_waits_ready_event(self):
        self.mgr._threads[USER] = FakeThread(self.clock, self.clock.t)
        self.new_engine(ready_after=10)
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual(r["status"], "done")
        self.assertEqual(self.mgr._no_recover, set())
        # 끝내 안 세움 → 180초(가짜 시계) 뒤 start_not_ready, 복구 금지 표시 뒤 정지
        self.mgr.calls.clear()
        self.new_engine(ready_after=None)
        t0 = self.clock.t
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual((r["status"], r["code"]), ("error", "start_not_ready"))
        self.assertGreaterEqual(self.clock.t - t0, cr.READY_WAIT_SEC)
        self.assertIn(USER, self.mgr._no_recover)
        self.assertEqual([c[0] for c in self.mgr.calls], ["stop", "start", "stop"])
        # 대기 중 스레드 죽음 → 바로 start_not_ready
        self.mgr.calls.clear()
        self.new_engine(ready_after=None, dies_after=3)
        t0 = self.clock.t
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual(r["code"], "start_not_ready")
        self.assertLess(self.clock.t - t0, 10)
        # 준비 실패 사유(분할 상태 복원 실패) → 바로 실패
        self.mgr.calls.clear()
        self.new_engine(ready_after=None, fail="restore_failed")
        t0 = self.clock.t
        r = self.ctl.restart_engine(USER, "TEST", "PULLBACK")
        self.assertEqual(r["code"], "start_not_ready")
        self.assertLess(self.clock.t - t0, 5)


class TestReadyOrder(InTmpCwd):
    def _boot(self, restore_raises=False):
        order = []
        ev = threading.Event()
        ec.READY[USER] = ev
        self.addCleanup(ec.READY.pop, USER, None)
        real_seed = live_loop._pullback_seed_warmup
        real_restore = live_loop._pullback_restore_split_state
        real_set = ev.set

        def seed(*a, **k):
            order.append("warmup_replay")
            return real_seed(*a, **k)

        def restore(engine, *a, **k):
            order.append("restore")
            if restore_raises:
                with mock.patch.object(engine, "pullback_restore_on_boot", side_effect=RuntimeError("x")):
                    return real_restore(engine, *a, **k)
            return real_restore(engine, *a, **k)

        def drain(engine):
            order.append("loop")
            return 0
        ev.set = lambda: (order.append("set"), real_set())
        with mock.patch.object(live_loop, "_pullback_seed_warmup", side_effect=seed), \
                mock.patch.object(live_loop, "_pullback_restore_split_state", side_effect=restore), \
                mock.patch.object(ec, "drain_control_queue", side_effect=drain):
            boot(self, cfg(), rising_df(300))
        return order, ev

    def test_ready_set_after_pullback_restore(self):
        order, ev = self._boot()
        self.assertEqual(order, ["warmup_replay", "restore", "set", "loop"])
        self.assertTrue(ev.is_set())

    def test_ready_not_set_when_restore_raises(self):
        order, ev = self._boot(restore_raises=True)
        self.assertNotIn("set", order)
        self.assertFalse(ev.is_set())
        self.assertEqual(getattr(ev, "fail_reason", None), "restore_failed")
        self.assertIn("loop", order)                               # 기동은 계속(T6 규칙)


# ================================================================ PULLBACK LIVE 기동 거부 유지
class TestLiveRefusalKept(InTmpCwd):
    def test_engine_manager_refuses_pullback_live_even_with_override(self):
        Path(f"{USER}_active_strategy.txt").write_text("EMA")
        em_cls = engine_manager.EngineManager
        real_init = em_cls.__init__

        def init_with_override(self_em):
            real_init(self_em)
            self_em._strategy_override[USER] = "PULLBACK"
        with mock.patch.object(em_cls, "__init__", init_with_override):
            got = run_engine_runner(self, session="EMA", test_mode=False)
        got["trader_cls"].assert_not_called()
        self.assertNotIn("run", got)
        crit = [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertTrue(crit)
        self.assertIn(live_loop.PULLBACK_LIVE_REFUSE_MSG, crit[0].args[1])

    def test_live_loop_refuses_pullback_live(self):
        params = pbp.to_live_params(cfg(), 1_000_000)
        stop = threading.Event()
        with mock.patch.object(live_loop, "RUN_MODE", "UPBIT_MATCH"), \
                mock.patch.object(live_loop, "get_reconciler") as rec:
            live_loop.run_live_loop(params, queue.Queue(), FakeTrader(test_mode=False), stop, False, USER,
                                    pullback_cfg=cfg())
        rec.assert_not_called()
        self.assertTrue(stop.is_set())
        self.assertTrue(any(c.args[0] == "CRITICAL" for c in self.notify.call_args_list))

    def test_refuse_texts_have_no_internal_codes(self):
        """기동 거부·워밍업 부족 알림: 「PULLBACK」·배포 절 표기 없음, 할 일 또는 「따로 하실 일 없음」으로 끝."""
        sent = []
        for holding in (True, False):
            live_loop._pullback_warmup_check(1, 10, holding=holding, user_id=USER, ticker=TICKER,
                                             notify=lambda *a, **k: sent.append(a))
        params = pbp.to_live_params(cfg(), 1_000_000)
        with mock.patch.object(live_loop, "RUN_MODE", "UPBIT_MATCH"), mock.patch.object(live_loop, "get_reconciler"):
            live_loop.run_live_loop(params, queue.Queue(), FakeTrader(test_mode=False), threading.Event(), False, USER,
                                    pullback_cfg=cfg())
        sent += [c.args for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]
        self.assertGreaterEqual(len(sent), 3)
        for a in sent:
            text = a[1] + "\n" + a[2]
            for w in ("PULLBACK", "배포 절", "①", "T11", "pullback_cfg"):
                self.assertNotIn(w, text, text)
        for a in sent:
            self.assertTrue(a[2].rstrip().endswith((se.NO_ACTION_TEXT, "요.")), a[2])


# ================================================================ EMA 경로 무변경 (기준 커밋 비교)
def _funcs(src, skip=()):
    out = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "pullback" not in node.name.lower() \
                and node.name not in skip:
            out[node.name] = ast.dump(node)
    return out


class _StripControl(ast.NodeTransformer):
    """T11 이 run_live_loop 에 더한 것만 걷어 낸다: _control_* 호출 줄, PULLBACK 전용 if 블록(문구 수정 포함)."""

    @staticmethod
    def _is_pullback_test(t):
        if isinstance(t, ast.BoolOp):
            t = t.values[0]
        return (isinstance(t, ast.Compare) and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value == "PULLBACK"
                and isinstance(t.ops[0], ast.Eq))

    def _body(self, stmts):
        out = []
        for s in stmts:
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name) \
                    and s.value.func.id.startswith("_control_"):
                continue
            if isinstance(s, ast.If) and self._is_pullback_test(s.test) and not s.orelse:
                continue
            out.append(self.visit(s))
        return out

    def generic_visit(self, node):
        for field in ("body", "orelse", "finalbody"):
            v = getattr(node, field, None)
            if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
                setattr(node, field, self._body(v))
        for h in getattr(node, "handlers", []) or []:
            h.body = self._body(h.body)
        return node


def _run_live_loop_norm(src):
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "run_live_loop")
    return ast.dump(_StripControl().visit(fn))


class TestEmaBaseline(unittest.TestCase):
    def base(self, rel):
        src = bc.git_show(rel)
        if src is None:
            self.skipTest("git 기준 원본 없음")
        return src

    def test_strategy_engine_non_pullback_unchanged(self):
        rel = "core/strategy_engine.py"
        self.assertEqual(_funcs((ROOT / rel).read_text(encoding="utf-8")), _funcs(self.base(rel)))

    def test_live_loop_ema_path_unchanged(self):
        rel = "engine/live_loop.py"
        now, base = (ROOT / rel).read_text(encoding="utf-8"), self.base(rel)
        skip = {"run_live_loop"}
        new_funcs = {k for k in _funcs(now) if k not in _funcs(base)}
        self.assertEqual(new_funcs, {"_control_attach", "_control_ready", "_control_drain"})
        self.assertEqual({k: v for k, v in _funcs(now, skip).items() if k not in new_funcs}, _funcs(base, skip))
        self.assertEqual(_run_live_loop_norm(now), _run_live_loop_norm(base))
        # 더한 호출은 정확히 3줄(엔진 생성 직후·메인 루프 진입 직전·메인 루프 맨 앞) — LEGACY_LOCAL 루프에는 없음
        fn = next(n for n in ast.walk(ast.parse(now)) if isinstance(n, ast.FunctionDef) and n.name == "run_live_loop")
        calls = [n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id.startswith("_control_")]
        self.assertEqual(sorted(calls), ["_control_attach", "_control_drain", "_control_ready"])

    def test_untouched_ema_files_same_as_base(self):
        for rel in ("engine/boot_resume.py", "services/trading_control.py", "core/trader.py",
                    "core/strategy_incremental.py", "core/position_state.py", "engine/order_reconciler.py"):
            self.assertEqual((ROOT / rel).read_text(encoding="utf-8"), self.base(rel), rel)

    def test_engine_manager_no_arg_calls_same_trace_as_base(self):
        """기준 커밋 engine_manager 원본과 지금 것을 같은 가짜 환경에서 인자 없이(구버전 흐름) 돌려 호출 흔적을 비교."""
        src = self.base("engine/engine_manager.py")
        old = types.ModuleType("engine_manager_base")
        old.__file__ = str(ROOT / "engine" / "engine_manager_base.py")
        exec(compile(src, old.__file__, "exec"), old.__dict__)
        self.assertEqual(_trace(old), _trace(engine_manager))


def _trace(mod):
    """세션 모드 TEST·전략 EMA 로 start_engine() → 실행 중 확인 → 같은 모드 다시 시작(False) → stop_engine() 흔적.
    (복구 래퍼 재시작 횟수는 TestRecovery 가 본다)"""
    rec = []
    stop_all = threading.Event()

    def note(name):
        return lambda *a, **k: rec.append((name, a, tuple(sorted(k.items()))))

    em = mod.EngineManager()
    runs = {"n": 0}

    def fake_run_live_loop(params, q, trader, stop_event, test_mode, user_id, **kw):
        rec.append(("run_live_loop", test_mode, user_id, tuple(sorted(kw))))
        runs["n"] += 1
        while not stop_event.is_set() and not stop_all.is_set():
            _time.sleep(0.005)

    params = SimpleNamespace(strategy_type="EMA", order_ratio=0.25, upbit_ticker=TICKER)
    calls_lp = []
    session = {"mode": "TEST", "strategy_type": "EMA"}
    tmp = tempfile.TemporaryDirectory()
    cwd = os.getcwd()
    os.chdir(tmp.name)
    lock = threading.Lock()
    patches = [
        mock.patch.object(mod, "st", SimpleNamespace(session_state=session)),
        mock.patch.object(mod, "load_params", side_effect=lambda *a, **k: calls_lp.append((a, k)) or params),
        mock.patch.object(mod, "UpbitTrader", side_effect=lambda *a, **k: rec.append(("trader", a, tuple(sorted(k.items())))) or SimpleNamespace()),
        mock.patch.object(mod, "run_live_loop", side_effect=fake_run_live_loop),
        mock.patch.object(mod, "get_user_lock", return_value=lock),
        mock.patch.object(mod, "get_reconciler", return_value=mock.MagicMock()),
        mock.patch.object(mod, "set_engine_status", side_effect=note("set_engine_status")),
        mock.patch.object(mod, "set_thread_status", side_effect=note("set_thread_status")),
        mock.patch.object(mod, "update_engine_status", side_effect=note("update_engine_status")),
        mock.patch.object(mod, "add_engine_thread", side_effect=lambda *a, **k: rec.append(("add_engine_thread", a[0]))),
        mock.patch.object(mod, "remove_engine_thread", side_effect=note("remove_engine_thread")),
        mock.patch.object(mod, "insert_log", side_effect=note("insert_log")),
        mock.patch.object(mod, "log_to_file", side_effect=note("log_to_file")),
        mock.patch("services.db.set_engine_status", side_effect=note("db.set_engine_status")),
    ]
    for p in patches:
        p.start()
    try:
        rec.append(("start", em.start_engine(USER)))
        t0 = _time.time()
        while runs["n"] < 1 and _time.time() - t0 < 3:
            _time.sleep(0.005)
        rec.append(("running", em.get_running_mode(USER), em.is_running(USER)))
        rec.append(("start_again", em.start_engine(USER)))
        em.stop_engine(USER)
        rec.append(("after_stop", em.get_running_mode(USER)))
    finally:
        stop_all.set()
        for p in reversed(patches):
            p.stop()
        os.chdir(cwd)
        tmp.cleanup()
    rec.append(("load_params", calls_lp))
    return sorted(repr(r) for r in rec)   # 스레드 사이 순서는 비교하지 않는다(같은 호출·같은 인자·같은 횟수)


class TestOldEngineBehaviour(unittest.TestCase):
    def test_old_engine_behaviour_unchanged(self):
        """WO-12 시험 전부 통과 + 모드 잠금 시험(tests/test_mode_lock.py) 통과."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName("tests.regressions.test_r_2026_09_30_wo12_boot_resume")
        res = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(suite)
        self.assertTrue(res.wasSuccessful(), [str(f[0]) for f in res.failures + res.errors])
        self.assertGreaterEqual(res.testsRun, 14)


# ================================================================ 기동 스크립트 (감시 스레드·gen)
def load_boot():
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("tradebot_boot_t11", ROOT / "scripts" / "tradebot_boot.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(cwd)


class TestBootScript(unittest.TestCase):
    def test_main_starts_control_thread_daemon_try_wrapped(self):
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        body = src.split("def main()")[1]
        self.assertIn('name="v2_control", daemon=True', body)
        self.assertLess(body.index('name="v2_control"'), body.index("bootstrap.run("))
        self.assertRegex(body, r"try:\n\s+threading\.Thread\(target=_control_thread[^\n]*\.start\(\)\n\s+except Exception")

    def test_alive_file_has_gen(self):
        mod = load_boot()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, ".engine_alive.json")

        class M:
            def get_active_user_ids(self):
                return ["u1"]

            def get_running_mode(self, u):
                return "TEST"

            def gen_map(self):
                return {"u1": 3}
        mod.engine_alive_tick(M(), path)
        body = json.loads(Path(path).read_text())
        self.assertEqual(body["gen"], {"u1": 3})


if __name__ == "__main__":
    unittest.main()
