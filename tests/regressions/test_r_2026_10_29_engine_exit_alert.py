"""
1028-15 (나): 엔진 예외 종료 경보(운영자 채널) · 조용한 멈춤(D4) 제거 · LIVE 사용자 집합 멱등 — 진짜 runner 경유 시험.

계획: docs/plans/2026-10-28-engine-recovery-fix/plan.md 4장 (S1~S12, S3-b) + 구현 수정 1회차 S13(준비 신호 소유).

- 진짜: EngineManager.start_engine / _start_engine_internal / _engine_runner_with_recovery / _engine_runner /
  _run_live_loop_guarded(작업 스레드 감싸기) / stop_engine, core.engine_control.
- 가짜: DB 기록·파일 로그·params·trader·run_live_loop 본문(S8-b 만 진짜)·Reconciler·텔레그램 발송.
- 실제 텔레그램 발송은 일어나지 않는다: services.notifier.send 를 가짜로 바꾸거나(S1~S11),
  진짜 send 를 쓸 때는 notifier._requests 를 가짜로 바꾼다(S9·S12). 토큰·채널은 시험 안의 가짜 값뿐이다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_29_engine_exit_alert -v
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
import engine.engine_manager as engine_manager  # noqa: E402
import services.notifier as notifier  # noqa: E402

U = "exit_alert_u1"
U2 = "exit_alert_u2"
TICKER = "KRW-EXITTEST"
EXIT_KEY = "engine_exit_exception:"
_sleep = time.sleep


def _params(strategy="EMA"):
    return SimpleNamespace(strategy_type=strategy, order_ratio=0.1, upbit_ticker=TICKER)


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _wait(cond, timeout):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        _sleep(0.01)
    return cond()


class Rig:
    """engine_manager 의 바깥 입출력만 가짜로 바꾼 틀."""

    def __init__(self, live_loop=None, trader_exc=None, strategy="EMA", real_run_live_loop=False,
                 real_notifier=False, send_exc=None, slow_events=None, boot_params=None):
        self.em = engine_manager.EngineManager()
        self.insert_logs = []      # (user, level, msg)
        self.files = []            # msg
        self.status = []           # (user, running)
        self.sends = []            # dict
        self.runs = []             # (user, n)
        self.thread_excs = []      # 스레드 밖으로 샌 예외의 스레드 이름
        self.locks = {}
        self.rec = mock.MagicMock(name="reconciler")
        self.live_loop = live_loop or self.wait_until_stop
        self.trader_exc = trader_exc
        self.strategy = strategy
        self.send_exc = send_exc
        self.slow_events = slow_events or {}   # LOG 문구 → 처리 지연(초)
        self.log_handler = _ListHandler()
        em = self.em
        real_process = em._process_event

        def process(user_id, event, *a, **k):
            try:
                if event[1] == "LOG" and event[2] in self.slow_events:
                    _sleep(self.slow_events[event[2]])
                elif event[1] == "LOG" and "*" in self.slow_events:
                    _sleep(self.slow_events["*"])
            except Exception:
                pass
            return real_process(user_id, event, *a, **k)

        def trader(*a, **k):
            if self.trader_exc is not None:
                raise self.trader_exc
            return SimpleNamespace(test_mode=k.get("test_mode", True))

        def run(params, q, trader_obj, stop_event, test_mode, user_id, **kw):
            n = sum(1 for r in self.runs if r[0] == user_id) + 1
            self.runs.append((user_id, n))
            return self.live_loop(self, n, params, q, stop_event, user_id)

        def send(level, title, body="", dedupe_key=None, dedupe_ttl=300, **kw):
            self.sends.append(dict(level=level, title=title, body=body, dedupe_key=dedupe_key, **kw))
            if self.send_exc is not None:
                raise self.send_exc
            return True

        def get_lock(lock_id):
            return self.locks.setdefault(lock_id, threading.Lock())

        self.patches = [
            mock.patch.object(engine_manager, "st", SimpleNamespace(session_state={"mode": "TEST"})),
            mock.patch.object(engine_manager, "insert_log",
                              side_effect=lambda u, lv, m: self.insert_logs.append((u, lv, m))),
            mock.patch.object(engine_manager, "log_to_file", side_effect=lambda m, u=None: self.files.append(m)),
            mock.patch.object(engine_manager, "set_engine_status",
                              side_effect=lambda u, r, last_mode=None: self.status.append((u, r))),
            mock.patch.object(engine_manager, "set_thread_status"),
            mock.patch.object(engine_manager, "update_engine_status"),
            mock.patch.object(engine_manager, "add_engine_thread"),
            mock.patch.object(engine_manager, "remove_engine_thread"),
            mock.patch.object(engine_manager, "_decide_strategy_type", return_value=strategy),
            mock.patch.object(engine_manager, "load_params", return_value=_params(strategy)),
            mock.patch.object(engine_manager, "scoped_params_path", return_value=None),
            mock.patch.object(engine_manager, "UpbitTrader", side_effect=trader),
            mock.patch.object(engine_manager, "get_reconciler", return_value=self.rec),
            mock.patch.object(engine_manager, "get_user_lock", side_effect=get_lock),
            mock.patch("services.db.set_engine_status"),
            mock.patch.object(em, "_process_event", side_effect=process),
            mock.patch.object(threading, "excepthook",
                              side_effect=lambda args: self.thread_excs.append(args.thread.name if args.thread else "")),
        ]
        if not real_run_live_loop:
            self.patches.append(mock.patch.object(engine_manager, "run_live_loop", side_effect=run))
        if boot_params is not None:
            self.patches.append(mock.patch.object(engine_manager, "_pullback_boot_params", return_value=boot_params))
        if not real_notifier:
            self.patches.append(mock.patch("services.notifier.send", side_effect=send))

    # ---------------------------------------------------------------- 가짜 run_live_loop 본보기
    @staticmethod
    def wait_until_stop(rig, n, params, q, stop_event, user_id):
        while not stop_event.is_set():
            _sleep(0.005)

    @staticmethod
    def set_ready(rig, user_id):
        ev = rig.em._ready.get(user_id)
        if ev is not None:
            ev.set()

    def __enter__(self):
        for p in self.patches:
            p.start()
        lg = logging.getLogger("engine.engine_manager")
        lg.addHandler(self.log_handler)
        return self

    def __exit__(self, *exc):
        # 남은 엔진을 모두 멈추고 스레드가 끝난 뒤에 가짜를 푼다(가짜가 풀린 뒤 진짜 DB 를 건드리지 않게).
        try:
            for ev in list(self.em._events.values()):
                ev.set()
            for th in list(self.em._threads.values()):
                th.join(timeout=40)
            for th in threading.enumerate():
                if th.name.startswith(("engine_runner_exit_alert", "run_live_loop_exit_alert")):
                    th.join(timeout=40)
        finally:
            logging.getLogger("engine.engine_manager").removeHandler(self.log_handler)
            for p in reversed(self.patches):
                p.stop()
        return False

    # ---------------------------------------------------------------- 조회
    def start(self, user=U, mode="TEST"):
        return self.em.start_engine(user, mode=mode)

    def thread(self, user=U):
        return self.em._threads.get(user)

    def wait_end(self, user=U, timeout=5.0):
        th = self.thread(user)
        if th is not None:
            th.join(timeout=timeout)
        return th is None or not th.is_alive()

    def wait_runs(self, user, n, timeout=5.0):
        return _wait(lambda: sum(1 for r in self.runs if r[0] == user) >= n, timeout)

    def exit_sends(self, user=None):
        return [s for s in self.sends if str(s.get("dedupe_key") or "").startswith(EXIT_KEY)
                and (user is None or s["dedupe_key"] == EXIT_KEY + user)]

    def critical_db(self, user=None):
        return [m for (u, lv, m) in self.insert_logs if lv == "CRITICAL" and (user is None or u == user)]

    def critical_logger(self):
        return [r.getMessage() for r in self.log_handler.records if r.levelno >= logging.CRITICAL]

    def last_status(self, user=U):
        vals = [r for (u, r) in self.status if u == user]
        return vals[-1] if vals else None


# ================================================================ 가짜 run_live_loop 모양들
def _loop_trading_exception(rig, n, params, q, stop_event, user_id):
    """준비 신호 뒤 메인 루프 안 예외(진짜 끝부분 2442–2450 모양). 앞에 처리가 느린 LOG 를 하나 넣어
    관리 루프가 그것을 처리하는 동안 EXCEPTION 이 큐에 남게 한다(큐 비우기만 그것을 기록할 수 있음)."""
    Rig.set_ready(rig, user_id)
    q.put((time.time(), "LOG", "SLOW"))
    _sleep(0.05)
    try:
        raise RuntimeError("boom-trading-SECRET")
    except Exception:
        exc = sys.exc_info()
        q.put((time.time(), "EXCEPTION", exc[0], exc[1], exc[2]))
        raise
    finally:
        stop_event.set()


def _loop_pre_main_try_exception(rig, n, params, q, stop_event, user_id):
    """D4: 메인 try(1460) 이전에서 죽는 모양 — q 에도 넣지 않고 stop_event 도 켜지 않는다."""
    _sleep(0.05)
    raise RuntimeError("boom-before-main-try")


# ================================================================ S1 사용자 정지
class TestS1UserStop(unittest.TestCase):
    def test_s1_user_stop_no_alert_and_quick_restart(self):
        def loop(rig, n, params, q, stop_event, user_id):
            Rig.set_ready(rig, user_id)
            if n == 1:
                for i in range(500):          # 정지 시점에 큐에 많이 남게
                    q.put((time.time(), "LOG", f"bulk-{i}"))
            while not stop_event.is_set():
                _sleep(0.005)

        with Rig(live_loop=loop, slow_events={"*": 0.05}) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_runs(U, 1))
            _sleep(0.3)
            th = rig.thread()
            t0 = time.monotonic()
            rig.em.stop_engine(U, mode="TEST")
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 10.0, "stop_engine 이 10초 안에 반환")
            self.assertTrue(_wait(lambda: not th.is_alive(), 0.5), "관리 스레드가 끝남(Lock 풀림)")
            self.assertEqual(rig.critical_db(), [])
            self.assertEqual(rig.critical_logger(), [])
            self.assertEqual(rig.sends, [])
            self.assertIs(rig.last_status(), False)
            self.assertFalse(rig.em.is_running(U))
            # 바로 다시 시작: Lock 차단 없음 + 두 번째 runner 가 실제로 돎
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_runs(U, 2), "두 번째 runner 가 돎")
            self.assertFalse(any("Lock 차단" in m for (_u, _lv, m) in rig.insert_logs))
            rig.em.stop_engine(U, mode="TEST")


# ================================================================ S2 runner 본문 예외
class TestS2RunnerException(unittest.TestCase):
    def test_s2_boot_exception_one_critical(self):
        with Rig(trader_exc=RuntimeError("boom-trader-SECRET")) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            sends = rig.exit_sends(U)
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["level"], notifier.LEVEL_CRITICAL)
            self.assertEqual(sends[0]["title"], engine_manager.ENGINE_EXIT_TITLE_BOOT)
            self.assertEqual(sends[0].get("audience"), "operator")
            self.assertEqual(len(rig.critical_db(U)), 1)
            self.assertEqual(len([m for m in rig.critical_logger() if "[ENGINE-EXIT]" in m]), 1)
            self.assertTrue(any("phase=boot" in m for m in rig.critical_logger()))
            self.assertIs(rig.last_status(), False)


# ================================================================ S3 작업 스레드 메인 루프 안 예외
class TestS3WorkerException(unittest.TestCase):
    def test_s3_trading_exception_one_critical_and_drained(self):
        with Rig(live_loop=_loop_trading_exception, slow_events={"SLOW": 0.3}) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            sends = rig.exit_sends(U)
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["title"], engine_manager.ENGINE_EXIT_TITLE_TRADING)
            self.assertTrue(any("phase=trading" in m for m in rig.critical_logger()))
            self.assertEqual(len(rig.critical_db(U)), 1)
            self.assertIs(rig.last_status(), False)
            self.assertTrue(any(lv == "ERROR" and "❌ 예외: RuntimeError: boom-trading-SECRET" in m
                                for (_u, lv, m) in rig.insert_logs), "큐에 남은 EXCEPTION 이 기록됨")
            # 작업 스레드 예외에는 runner 의 「❌ 엔진 예외」 원문 줄을 화면(logs)에 새로 더하지 않는다(결정 ③)
            self.assertEqual([m for (_u, _lv, m) in rig.insert_logs if "❌ 엔진 예외" in m], [])
            # 감싸기 함수는 예외를 다시 raise 한다 → 작업 스레드 excepthook 로 traceback 이 journal 에 남음
            self.assertTrue(any(n.startswith("run_live_loop_") for n in rig.thread_excs), rig.thread_excs)

    def test_s3b_event_after_stop_is_drained(self):
        """stop 이 켜진 뒤에 들어온 마지막 이벤트 — 「루프 종료 → join → 큐 비우기」 순서일 때만 기록된다.
        넣기 전 0.7초를 쉬는 것은 관리 루프의 q.get(timeout=0.5)이 먼저 끝나게 해서(루프가 그 이벤트를 우연히
        먼저 받아 처리하는 경합을 없앰), 오직 큐 비우기만 그 이벤트를 기록할 수 있게 하려는 것이다."""
        def loop(rig, n, params, q, stop_event, user_id):
            Rig.set_ready(rig, user_id)
            while not stop_event.is_set():
                _sleep(0.005)
            _sleep(0.7)
            q.put((time.time(), "LOG", "LAST-EVENT"))
            _sleep(0.2)

        with Rig(live_loop=loop) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_runs(U, 1))
            _sleep(0.1)
            rig.em.stop_engine(U, mode="TEST")
            self.assertTrue(rig.wait_end())
            self.assertTrue(any(m == "LAST-EVENT" for (_u, _lv, m) in rig.insert_logs))
            self.assertEqual(rig.critical_db(), [])
            self.assertEqual(rig.sends, [])


# ================================================================ S4 D4 조용한 멈춤
class TestS4PreMainTry(unittest.TestCase):
    def test_s4_zombie_gone(self):
        with Rig(live_loop=_loop_pre_main_try_exception) as rig:
            self.assertTrue(rig.start())
            th = rig.thread()
            self.assertTrue(rig.wait_end(timeout=3.0), "관리 루프가 3초 안에 끝남")
            self.assertFalse(th.is_alive())
            sends = rig.exit_sends(U)
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["title"], engine_manager.ENGINE_EXIT_TITLE_BOOT)
            self.assertEqual(len(rig.critical_db(U)), 1)
            self.assertIs(rig.last_status(), False)
            self.assertFalse(rig.em.is_running(U))
            self.assertTrue(any(n.startswith("run_live_loop_") for n in rig.thread_excs), rig.thread_excs)


# ================================================================ S13 준비 신호 소유 확인(문구 고르기)
class TestS13ReadyOwnership(unittest.TestCase):
    def test_s13_other_start_ready_event_does_not_make_trading(self):
        """준비 Event 가 이 시작의 것(ev.stop_event is 이 시도 stop_event)일 때만 「매매 중 멈춤」.
        다른 시작의 Event(이미 set)로 바뀌어 있으면 「기동 중 실패」 문구."""
        def loop(rig, n, params, q, stop_event, user_id):
            other = threading.Event()
            other.stop_event = threading.Event()   # 다른 시작의 stop_event
            other.set()
            rig.em._ready[user_id] = other
            _sleep(0.05)
            raise RuntimeError("boom-before-main-try")

        with Rig(live_loop=loop) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            sends = rig.exit_sends(U)
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["title"], engine_manager.ENGINE_EXIT_TITLE_BOOT)


# ================================================================ S5 재시작 0회
class TestS5NoRestart(unittest.TestCase):
    def _case(self, **kw):
        with Rig(**kw) as rig:
            self.assertTrue(rig.start())
            calls = []
            real = rig.em._start_engine_internal

            def spy(*a, **k):
                calls.append(k.get("restart_count"))
                return real(*a, **k)
            rig.em._start_engine_internal = spy
            th = rig.thread()
            self.assertTrue(rig.wait_end())
            _sleep(0.2)
            self.assertEqual(calls, [], "자동 재시작 호출 0")
            self.assertEqual(rig.em.get_gen(U), 1)
            self.assertIs(rig.thread(), th, "새 엔진 스레드 0")
            self.assertEqual(len(rig.exit_sends(U)), 1)

    def test_s5_boot_exception(self):
        self._case(trader_exc=RuntimeError("boom-trader"))

    def test_s5_trading_exception(self):
        self._case(live_loop=_loop_trading_exception, slow_events={"SLOW": 0.05})

    def test_s5_pre_main_try(self):
        self._case(live_loop=_loop_pre_main_try_exception)


# ================================================================ S6·S7 LIVE 사용자 집합
class TestS6S7LiveUsers(unittest.TestCase):
    def test_s6_double_stop_keeps_other_user(self):
        with Rig() as rig:
            self.assertTrue(rig.start(U, "LIVE"))
            self.assertTrue(rig.start(U2, "LIVE"))
            self.assertTrue(rig.wait_runs(U, 1))
            self.assertTrue(rig.wait_runs(U2, 1))
            self.assertEqual(rig.em._live_users, {U, U2})
            self.assertEqual(rig.em._live_engine_count, 2)
            rig.em.stop_engine(U, mode="LIVE")
            rig.em.stop_engine(U, mode="LIVE")      # 두 번째 정지(이미 꺼진 엔진)
            self.assertEqual(rig.em._live_users, {U2})
            self.assertEqual(rig.em._live_engine_count, 1)
            self.assertEqual(rig.rec.stop.call_count, 0, "다른 사용자의 Reconciler 유지")
            rig.em.stop_engine(U2, mode="LIVE")
            self.assertEqual(rig.em._live_users, set())
            self.assertEqual(rig.rec.stop.call_count, 1)

    def test_s7_exception_exit_restart_stop(self):
        def loop(rig, n, params, q, stop_event, user_id):
            if n == 1:
                return _loop_trading_exception(rig, n, params, q, stop_event, user_id)
            Rig.set_ready(rig, user_id)
            while not stop_event.is_set():
                _sleep(0.005)

        with Rig(live_loop=loop, slow_events={"SLOW": 0.05}) as rig:
            self.assertTrue(rig.start(U, "LIVE"))
            self.assertTrue(rig.wait_end())
            self.assertEqual(rig.em._live_users, {U}, "예외 종료는 집합에서 빼지 않음")
            self.assertEqual(rig.rec.load_inflight_from_db.call_count, 1)
            self.assertEqual(rig.rec.stop.call_count, 0)
            self.assertTrue(rig.start(U, "LIVE"))
            self.assertTrue(rig.wait_runs(U, 2))
            self.assertEqual(rig.em._live_users, {U})
            self.assertEqual(rig.rec.load_inflight_from_db.call_count, 1)
            rig.em.stop_engine(U, mode="LIVE")
            self.assertEqual(rig.em._live_users, set())
            self.assertEqual(rig.rec.stop.call_count, 1, "정지 뒤 Reconciler 가 멈춤")


# ================================================================ S8 PULLBACK 거부는 기존 알림 그대로
class TestS8PullbackRefusal(unittest.TestCase):
    def _assert_only(self, rig, prefix):
        self.assertTrue(rig.wait_end())
        self.assertEqual(rig.exit_sends(), [])
        self.assertEqual(len(rig.sends), 1, rig.sends)
        self.assertTrue(str(rig.sends[0]["dedupe_key"]).startswith(prefix))
        self.assertEqual([m for m in rig.critical_logger() if "[ENGINE-EXIT]" in m], [])
        self.assertEqual(rig.critical_db(), [])

    def test_s8a_live_runner_refusal(self):
        with Rig(strategy="PULLBACK") as rig:
            self.assertTrue(rig.start(U, "LIVE"))
            self._assert_only(rig, "pullback_live_refused:")
            self.assertEqual(rig.runs, [])

    def test_s8b_live_loop_refusal_real_run_live_loop(self):
        """runner 를 지나 진짜 run_live_loop(1051–1073)가 거부하게: TEST + _pullback_boot_params → (params, None).
        (None, None) 이면 runner 533–537 이 먼저 막아 live_loop 에 닿지 않는다."""
        with Rig(strategy="PULLBACK", real_run_live_loop=True,
                 boot_params=(_params("PULLBACK"), None)) as rig:
            self.assertTrue(rig.start(U, "TEST"))
            self._assert_only(rig, "pullback_boot_refused:")


# ================================================================ S9 dedupe 사용자별
class TestS9Dedupe(unittest.TestCase):
    def test_s9_dedupe_per_user(self):
        post = mock.MagicMock(name="post", return_value=SimpleNamespace(status_code=200, text=""))
        env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_")}
        env.update({"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID_OPERATOR": "op-chat"})
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.dict(sys.modules, {"streamlit": SimpleNamespace(secrets={})}), \
                mock.patch.object(notifier, "_requests", SimpleNamespace(post=post)), \
                mock.patch.dict(notifier._dedupe_state, {}, clear=True):
            with Rig(trader_exc=RuntimeError("boom"), real_notifier=True) as rig:
                for user in (U, U, U2):
                    self.assertTrue(rig.start(user))
                    self.assertTrue(rig.wait_end(user))
                self.assertEqual(len(rig.critical_db()), 3)
        self.assertEqual(post.call_count, 2, "같은 사용자 1시간 1건, 다른 사용자는 따로")
        self.assertEqual({c.kwargs["data"]["chat_id"] for c in post.call_args_list}, {"op-chat"})


# ================================================================ S10 발송 예외
class TestS10SendException(unittest.TestCase):
    def test_s10_send_raises(self):
        with Rig(trader_exc=RuntimeError("boom"), send_exc=RuntimeError("telegram down")) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            self.assertEqual(len(rig.exit_sends(U)), 1)
            self.assertIs(rig.last_status(), False)
            self.assertFalse([n for n in rig.thread_excs if n.startswith("engine_runner_")],
                             "관리 스레드 밖으로 예외가 새지 않음")


# ================================================================ S11 예외 원문 노출
class TestS11NoRawText(unittest.TestCase):
    def _check(self, rig, secret):
        sends = rig.exit_sends(U)
        self.assertEqual(len(sends), 1)
        text = sends[0]["title"] + "\n" + sends[0]["body"]
        self.assertNotIn(secret, text)
        self.assertNotIn(TICKER, text)
        self.assertNotIn("EMA", text)
        self.assertNotIn("투자자님이 따로 하실 일은 없습니다", text)   # 운영자 문구(결정 ①)
        crit = rig.critical_db(U)
        self.assertEqual(crit, [engine_manager.ENGINE_EXIT_INVESTOR_LOG])
        self.assertTrue(any("[ENGINE-EXIT]" in m and secret in m for m in rig.critical_logger()))
        self.assertTrue(any("[ENGINE-EXIT]" in m and secret in m for m in rig.files))

    def test_s11_boot(self):
        with Rig(trader_exc=RuntimeError("boom-trader-SECRET")) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            self._check(rig, "boom-trader-SECRET")

    def test_s11_trading(self):
        with Rig(live_loop=_loop_trading_exception, slow_events={"SLOW": 0.05}) as rig:
            self.assertTrue(rig.start())
            self.assertTrue(rig.wait_end())
            self._check(rig, "boom-trading-SECRET")
            # 작업 스레드 예외: runner 의 「❌ 엔진 예외 …{e}」 원문 줄 0건(화면에 원문을 새로 더하지 않음)
            self.assertEqual([m for (_u, _lv, m) in rig.insert_logs if "❌ 엔진 예외" in m], [])


# ================================================================ S12 운영자 채널 대체 금지
class TestS12OperatorChannel(unittest.TestCase):
    """7가지 모두 시험 안에서 가짜 토큰을 넣는다(실행 명령이 토큰을 비우므로 — 없으면 V-k 가 살아남음)."""

    def _send(self, env_extra, secrets, audience):
        post = mock.MagicMock(name="post", return_value=SimpleNamespace(status_code=200, text=""))
        env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_")}
        env.update(env_extra)
        kw = {} if audience is None else {"audience": audience}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.dict(sys.modules, {"streamlit": SimpleNamespace(secrets=dict(secrets))}), \
                mock.patch.object(notifier, "_requests", SimpleNamespace(post=post)), \
                mock.patch.dict(notifier._dedupe_state, {}, clear=True), \
                self.assertLogs("services.notifier", level="INFO") as cm:
            notifier.logger.info("[S12] start")
            notifier.send(notifier.LEVEL_CRITICAL, "t", "b", **kw)
        chats = [c.kwargs["data"]["chat_id"] for c in post.call_args_list]
        return chats, cm.output

    BASE_ENV = {"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "default-chat",
                "TELEGRAM_CHAT_ID_CRITICAL": "critical-chat"}
    BASE_SECRETS = {"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "default-chat",
                    "TELEGRAM_CHAT_ID_CRITICAL": "critical-chat"}

    def _no_operator(self, chats, out):
        self.assertEqual(chats, [], "운영자 키가 없으면 post 0건(투자자 채널로 넘어가지 않음)")
        self.assertTrue(any("[NOTIFY] operator 채널 없음 — 로그만" in o for o in out))

    def test_s12_env_1_no_operator_key(self):
        self._no_operator(*self._send(self.BASE_ENV, {}, "operator"))

    def test_s12_env_2_operator_key(self):
        chats, _ = self._send({**self.BASE_ENV, "TELEGRAM_CHAT_ID_OPERATOR": "op-chat"}, {}, "operator")
        self.assertEqual(chats, ["op-chat"])

    def test_s12_env_3_default_audience(self):
        chats, _ = self._send({**self.BASE_ENV, "TELEGRAM_CHAT_ID_OPERATOR": "op-chat"}, {}, None)
        self.assertEqual(chats, ["critical-chat"])

    def test_s12_secrets_1_no_operator_key(self):
        self._no_operator(*self._send({}, self.BASE_SECRETS, "operator"))

    def test_s12_secrets_2_operator_key(self):
        chats, _ = self._send({}, {**self.BASE_SECRETS, "TELEGRAM_CHAT_ID_OPERATOR": "op-chat"}, "operator")
        self.assertEqual(chats, ["op-chat"])

    def test_s12_secrets_3_default_audience(self):
        chats, _ = self._send({}, {**self.BASE_SECRETS, "TELEGRAM_CHAT_ID_OPERATOR": "op-chat"}, None)
        self.assertEqual(chats, ["critical-chat"])

    def test_s12_mixed_4_env_token_secrets_operator(self):
        chats, _ = self._send({"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "default-chat"},
                              {"TELEGRAM_CHAT_ID_OPERATOR": "op-chat"}, "operator")
        self.assertEqual(chats, ["op-chat"])


if __name__ == "__main__":
    unittest.main()
