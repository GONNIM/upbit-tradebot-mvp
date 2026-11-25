"""1122-01 (2026-11-23 사용자 지시) 모든 알림 투자자 사본 — 계획 docs/plans/2026-11-23-investor-all-alerts/plan.md 6절.

바깥 연결 없음: requests.post 는 가짜(notifier._requests 바꿔 끼움), 셸은 가짜 curl. 토큰·채팅 번호는 가짜 값뿐이다.
"""
from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "regressions"))
sys.path.insert(0, str(ROOT / "scripts"))

from services import notifier, investor_copy as ic  # noqa: E402

TOKEN = "123456:FAKE-token-for-tests-only"
OP = "111"          # 기본·등급 = 운영자 채팅 (서버와 같은 모양)
INV = "222"

# 2026-11-24 사용자 지시: 「투자자도 내(개발자)가 받는 알림 그대로 받으면 된다. 가공하거나 수정할 필요가 전혀 없다.」
# → 사본 글 == 운영자 글(바이트 그대로). 아래 본문 예는 경로·명령·오류 원문·HTML 특수문자를 일부러 섞었다.
RAW_BODIES = (
    "본문 한 줄",
    "경로 /root/upbit-tradebot-mvp/x.log 줄\nsystemctl restart tradebot\nerr: ConnectionError: boom\n사람 줄",
    "risk_pct=0.5 · avg_price=None · has_position=True\n────────\nTraceback (most recent call last):",
    "<b>꺾쇠</b> & 앰퍼샌드 \"따옴표\"",
    "",
)

_FAKE_CURL = """#!/bin/bash
# 시험용 가짜 curl — 인자와 표준입력 설정(-K -)을 기록만 한다. 바깥 연결 없음.
{
  echo "@@CALL"
  for a in "$@"; do echo "ARG:$(printf "%s" "$a" | base64 | tr -d "\\n")"; done
  echo "@@STDIN"
  cat
  echo "@@END"
} >> "$FAKE_CURL_LOG"
exit 0
"""


def run_shell(title, body, *, inv_chat=INV, op_chat=OP, copy_switch=None, off=False, lc_all=None):
    """notify_telegram.sh 를 가짜 curl 로 한 번 돌리고 [(argv 목록, stdin 글)] 을 돌려준다."""
    import base64
    d = Path(tempfile.mkdtemp(prefix="nt_"))
    bin_dir = d / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(_FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    env_file = d / ".env"
    lines = [f"TELEGRAM_BOT_TOKEN={TOKEN}", f"TELEGRAM_CHAT_ID={op_chat}"]
    if inv_chat:
        lines.append(f"TELEGRAM_CHAT_ID_INVESTOR={inv_chat}")
    if copy_switch is not None:
        lines.append(f"TELEGRAM_INVESTOR_COPY={copy_switch}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    off_file = d / ".investor_copy_off"
    if off:
        off_file.write_text("", encoding="utf-8")
    log = d / "curl.log"
    e = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(d), "FAKE_CURL_LOG": str(log),
         "NOTIFY_ENV_FILE": str(env_file), "NOTIFY_COPY_OFF_FILE": str(off_file)}
    if lc_all:
        e["LC_ALL"] = lc_all
    subprocess.run(["bash", str(ROOT / "scripts" / "server" / "notify_telegram.sh"), title, body],
                   env=e, timeout=20, check=True)
    calls = []
    if log.exists():
        for chunk in log.read_text(encoding="utf-8").split("@@CALL\n")[1:]:
            head, rest = chunk.split("@@STDIN\n", 1)
            stdin = rest.split("@@END\n", 1)[0]
            argv = [base64.b64decode(x[4:]).decode("utf-8") for x in head.splitlines() if x.startswith("ARG:")]
            calls.append((argv, stdin))
    return calls


def shell_text(call) -> str:
    """가짜 curl 호출 하나에서 text= 값(HTML)만."""
    for a in call[0]:
        if a.startswith("text="):
            return a[5:]
    return ""

class FakePost:
    """chat_id 별로 (status) 를 돌려주는 가짜 post. 호출 기록: (chat, text, 스레드 이름)."""

    def __init__(self, codes=None, exc_for=None, sleep=0.0, retry_after=None):
        self.codes = codes or {}
        self.exc_for = exc_for or {}
        self.sleep = sleep
        self.retry_after = retry_after
        self.calls = []
        self.lock = threading.Lock()

    def post(self, url, data=None, timeout=None):
        chat = data["chat_id"]
        with self.lock:
            self.calls.append((chat, data["text"], threading.current_thread().name))
        if self.sleep:
            time.sleep(self.sleep)
        if chat in self.exc_for:
            raise self.exc_for[chat]
        code = self.codes.get(chat, 200)
        ra = self.retry_after
        return SimpleNamespace(status_code=code, text=f"{url} raw body",
                               json=lambda: {"error_code": code, "parameters": {"retry_after": ra} if ra else {}})

    def to(self, chat):
        return [c for c in self.calls if c[0] == chat]


def env(**kw):
    base = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": OP, "TELEGRAM_CHAT_ID_OPERATOR": OP,
            "TELEGRAM_CHAT_ID_INVESTOR": INV, "TELEGRAM_INVESTOR_COPY": "",
            "TELEGRAM_CHAT_ID_CRITICAL": "", "TELEGRAM_CHAT_ID_WARNING": "", "TELEGRAM_CHAT_ID_INFO": "",
            "WO6_DRY_RUN": ""}
    base.update(kw)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        ic._reset_for_tests()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.off = Path(self.tmp.name) / ".investor_copy_off"
        p = mock.patch.object(ic, "OFF_FILE", self.off)
        p.start()
        self.addCleanup(p.stop)
        notifier._dedupe_state.clear()
        self.addCleanup(ic._reset_for_tests)

    def send(self, fake, environ=None, **kw):
        args = dict(level="WARNING", title="⚠️ 시험 알림", body="본문 한 줄")
        args.update(kw)
        with mock.patch.dict(os.environ, environ or env()), mock.patch.object(notifier, "_requests", fake):
            ok = notifier.send(**args)
            ic.flush(3)
        return ok


# ================================================================ 3-3 상황별 사본 · 반환값
class CopyMatrix(Base):
    def test_sent_both(self):
        f = FakePost()
        self.assertTrue(self.send(f))
        self.assertEqual(len(f.to(OP)), 1)
        self.assertEqual(len(f.to(INV)), 1)

    def test_operator_text_unchanged(self):
        f = FakePost()
        self.send(f, body="경로 /root/x.log 줄\n사람 줄")
        self.assertEqual(f.to(OP)[0][1], notifier._format_message("WARNING", "⚠️ 시험 알림", "경로 /root/x.log 줄\n사람 줄"))
        self.assertEqual(f.to(INV)[0][1], f.to(OP)[0][1])   # 사본 == 운영자 글

    def test_dry_run(self):
        f = FakePost()
        self.assertFalse(self.send(f, environ=env(WO6_DRY_RUN="1")))
        self.assertEqual(f.calls, [])

    def test_dedupe(self):
        f = FakePost()
        self.send(f, dedupe_key="k1")
        self.assertFalse(self.send(f, dedupe_key="k1"))
        self.assertEqual((len(f.to(OP)), len(f.to(INV))), (1, 1))

    def test_no_op_chat_still_copies(self):
        f = FakePost()
        self.assertFalse(self.send(f, environ=env(TELEGRAM_CHAT_ID_OPERATOR=""), audience="operator"))
        self.assertEqual((len(f.to(OP)), len(f.to(INV))), (0, 1))

    def test_no_chat_still_copies(self):
        f = FakePost()
        self.assertFalse(self.send(f, environ=env(TELEGRAM_CHAT_ID="")))
        self.assertEqual((len(f.to(OP)), len(f.to(INV))), (0, 1))

    def test_no_token_no_copy(self):
        f = FakePost()
        with mock.patch.object(notifier, "_token_only", return_value=None), \
                mock.patch.object(ic, "_copy_token", return_value=None):
            self.assertFalse(self.send(f, environ=env(TELEGRAM_BOT_TOKEN="")))
        self.assertEqual(f.calls, [])

    def test_status_split(self):
        with mock.patch.dict(os.environ, env(TELEGRAM_CHAT_ID="")):
            st, _c = notifier._send_core("WARNING", "t", "b", None, 300, None)
            self.assertEqual(st, "no_chat")
        with mock.patch.dict(os.environ, env(TELEGRAM_CHAT_ID="", TELEGRAM_BOT_TOKEN="")), \
                mock.patch.object(notifier, "_token_only", return_value=None):
            st, _c = notifier._send_core("WARNING", "t", "b", None, 300, None)
            self.assertEqual(st, "no_token")

    def test_no_requests_no_copy(self):
        with mock.patch.dict(os.environ, env()), mock.patch.object(notifier, "_requests", None):
            self.assertFalse(notifier.send("WARNING", "t", "b"))
            ic.flush(1)
        self.assertEqual(ic.last_result, "none")

    def test_operator_fail_still_copies(self):
        f = FakePost(codes={OP: 500})
        self.assertFalse(self.send(f))
        self.assertEqual(len(f.to(INV)), 1)
        f2 = FakePost(exc_for={OP: ConnectionError("boom")})
        self.assertFalse(self.send(f2, dedupe_key=None))
        self.assertEqual(len(f2.to(INV)), 1)

    def test_operator_audience_copies(self):
        f = FakePost()
        self.assertTrue(self.send(f, audience="operator", title="🚨 [운영자] 새 전략 테이블 없음 — 마이그레이션 확인",
                                  body="services/init_db.ensure_pullback_tables 마이그레이션을 확인해 주세요."))
        self.assertEqual(f.to(INV)[0][1], f.to(OP)[0][1])   # 운영자 전용 알림도 글 그대로

    def test_same_chat_no_copy(self):
        f = FakePost()
        self.send(f, environ=env(TELEGRAM_CHAT_ID_INVESTOR=OP))
        self.assertEqual(len(f.calls), 1)

    def test_investor_missing(self):
        f = FakePost()
        self.send(f, environ=env(TELEGRAM_CHAT_ID_INVESTOR=""))
        self.assertEqual(len(f.calls), 1)

    def test_env_switch_off(self):
        f = FakePost()
        self.send(f, environ=env(TELEGRAM_INVESTOR_COPY="0"))
        self.assertEqual(len(f.calls), 1)

    def test_off_file_then_removed(self):
        f = FakePost()
        self.off.write_text("")
        self.send(f)
        self.assertEqual(len(f.to(INV)), 0)
        self.assertEqual(ic.last_result, "off:파일")
        self.off.unlink()
        self.send(f)
        self.assertEqual(len(f.to(INV)), 1)

    def test_investor_copy_false(self):
        f = FakePost()
        self.send(f, investor_copy=False)
        self.assertEqual(len(f.to(INV)), 0)

    def test_return_values_same_as_before(self):
        """옛 send() 반환값(고정값): 200 만 True, 나머지 모두 False — 사본 결과와 무관."""
        cases = [(env(), {}, True), (env(), {INV: 500}, True), (env(), {OP: 500}, False),
                 (env(TELEGRAM_CHAT_ID=""), {}, False), (env(WO6_DRY_RUN="1"), {}, False)]
        for environ, codes, want in cases:
            notifier._dedupe_state.clear()
            ic._reset_for_tests()
            self.assertIs(self.send(FakePost(codes=codes), environ=environ), want)

    def test_copy_failures_do_not_touch_operator(self):
        for f in (FakePost(codes={INV: 500}), FakePost(exc_for={INV: RuntimeError("x")}),
                  FakePost(codes={INV: 403}), FakePost(codes={INV: 429})):
            ic._reset_for_tests()
            notifier._dedupe_state.clear()
            self.assertTrue(self.send(f))
            self.assertEqual(len(f.to(OP)) >= 1, True)


# ================================================================ 403 · 429 · 연속 실패 쉼
class Backoff(Base):
    def test_403_pauses_hour_and_tells_operator_once(self):
        f = FakePost(codes={INV: 403})
        self.send(f)
        self.assertEqual(ic.last_result, "fail:http_403")
        self.send(f, title="다른 알림")
        ic.flush(3)
        self.assertEqual(ic.last_result, "paused")
        self.assertEqual(len(f.to(INV)), 1)
        pause_msgs = [c for c in f.to(OP) if "사본 잠시 멈춤" in c[1]]
        self.assertEqual(len(pause_msgs), 1)       # 쉼 알림은 운영자에게만, 사본 없음
        self.assertGreater(ic._pause_until - time.monotonic(), 3000)

    def test_429_uses_retry_after(self):
        f = FakePost(codes={INV: 429}, retry_after=17)
        self.send(f)
        left = ic._pause_until - time.monotonic()
        self.assertTrue(10 < left <= 17, left)

    def test_429_default_60(self):
        f = FakePost(codes={INV: 429})
        self.send(f)
        left = ic._pause_until - time.monotonic()
        self.assertTrue(50 < left <= 60, left)

    def test_five_failures_pause(self):
        f = FakePost(codes={INV: 500})
        for i in range(5):
            self.send(f, title=f"t{i}")
        self.assertGreater(ic._pause_until - time.monotonic(), 1700)
        self.assertEqual(len([c for c in f.to(OP) if "사본 잠시 멈춤" in c[1]]), 1)


# ================================================================ 일꾼
class Worker(Base):
    def test_state_runs_in_worker_thread(self):
        seen = []
        real = ic.state

        def spy(*a, **k):
            seen.append(threading.current_thread().name)
            return real(*a, **k)
        with mock.patch.object(ic, "state", spy):
            self.send(FakePost())
        self.assertEqual(seen, ["notify-copy"])

    def test_full_queue_does_not_block(self):
        f = FakePost(sleep=0.3)
        with mock.patch.dict(os.environ, env()), mock.patch.object(notifier, "_requests", f):
            t0 = time.monotonic()
            for i in range(40):
                ic.enqueue("INFO", f"t{i}", "b", OP)
            self.assertLess(time.monotonic() - t0, 0.5)
            ic.flush(0.1)
        ic._reset_for_tests()

    def test_send_returns_fast_while_copy_slow(self):
        f = FakePost(sleep=1.0)
        with mock.patch.dict(os.environ, env()), mock.patch.object(notifier, "_requests", f):
            orig = f.post

            def post(url, data=None, timeout=None):
                if data["chat_id"] == OP:
                    return SimpleNamespace(status_code=200, text="", json=lambda: {})
                return orig(url, data=data, timeout=timeout)
            f.post = post
            t0 = time.monotonic()
            self.assertTrue(notifier.send("INFO", "t", "b"))
            self.assertLess(time.monotonic() - t0, 0.3)
            ic.flush(3)

    def test_worker_restarts_when_dead(self):
        dead = threading.Thread(target=lambda: None)
        dead.start()
        dead.join()
        with mock.patch.object(ic, "_worker", dead):
            f = FakePost()
            self.send(f)
            self.assertEqual(len(f.to(INV)), 1)
            self.assertTrue(ic._worker.is_alive())

    def test_worker_swallows_exceptions(self):
        with mock.patch.object(ic, "_copy_token", side_effect=RuntimeError("x")):
            self.send(FakePost())
        f = FakePost()
        self.send(f, title="다음")
        self.assertEqual(len(f.to(INV)), 1)

    def test_two_threads_start_one_worker(self):
        ic._reset_for_tests()
        started = []
        real = threading.Thread

        class CountThread(real):
            def start(self_inner):
                started.append(1)
                return super().start()
        with mock.patch.object(ic, "_worker", None), mock.patch.object(ic.threading, "Thread", CountThread):
            ts = [real(target=ic._ensure_worker) for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(len(started), 1)

    def test_thread_start_failure_absorbed(self):
        class Boom:
            def __init__(self, *a, **k):
                raise RuntimeError("no threads")
        with mock.patch.object(ic, "_worker", None), mock.patch.object(ic.threading, "Thread", Boom), \
                mock.patch.dict(os.environ, env()), self.assertLogs("services.investor_copy", "WARNING") as cm:
            ic._ensure_worker()
        self.assertTrue(any("일꾼 시작 실패" in m for m in cm.output))

    def test_static_put_nowait_only(self):
        src = (ROOT / "services" / "investor_copy.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"\.put\(")
        self.assertNotRegex(src, r"put\(block")
        self.assertIn("put_nowait", src)

    def test_static_send_does_not_touch_off_file(self):
        src = (ROOT / "services" / "notifier.py").read_text(encoding="utf-8")
        m = re.search(r"\ndef send\(.*?\n(?=def )", src, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("OFF_FILE", m.group(0))

    def test_atexit_flush_subprocess(self):
        """정상 종료: atexit flush 로 사본이 나간다. SIGTERM(timeout 60) 은 atexit 를 건너뛰어 유실(알려진 한계, 계획 3-2)."""
        code = ("import os,sys,time\nsys.path.insert(0, %r)\n"
                "from types import SimpleNamespace\nfrom services import notifier\n"
                "def post(url, data=None, timeout=None):\n"
                "    time.sleep(0.2)\n    print('POST', data['chat_id'], flush=True)\n"
                "    return SimpleNamespace(status_code=200, text='', json=lambda: {})\n"
                "notifier._requests = SimpleNamespace(post=post)\n"
                "notifier.send('INFO', 't', 'b')\n") % str(ROOT)
        e = dict(os.environ, **env())
        out = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True, timeout=30).stdout
        self.assertIn("POST " + OP, out)
        self.assertIn("POST " + INV, out)


# ================================================================ 로그에 토큰 없음
class TokenSafeLogs(Base):
    def test_exception_log_has_no_token(self):
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        f = FakePost(exc_for={OP: ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: {url}"),
                              INV: ConnectionError(f"failed {url}")})
        with self.assertLogs(level="DEBUG") as cm:
            self.send(f)
            logging.getLogger("x").warning("end")
        joined = "\n".join(cm.output)
        self.assertNotIn(TOKEN, joined)
        self.assertNotIn("/bot", joined)
        self.assertIn("ConnectionError", joined)

    def test_http_fail_log_has_no_body(self):
        f = FakePost(codes={OP: 400, INV: 400})
        with self.assertLogs(level="DEBUG") as cm:
            self.send(f)
            logging.getLogger("x").warning("end")
        joined = "\n".join(cm.output)
        self.assertNotIn(TOKEN, joined)
        self.assertNotIn("raw body", joined)
        self.assertIn("error_code=400", joined)

    def test_no_chat_values_in_logs(self):
        f = FakePost()
        with self.assertLogs(level="DEBUG") as cm:
            self.send(f)
            logging.getLogger("x").warning("end")
        for line in cm.output:
            self.assertNotRegex(line, rf"\b{INV}\b")


# ================================================================ 사본 == 운영자 글 (2026-11-24 사용자 지시)
class RawCopy(Base):
    def test_copy_text_equals_operator_text(self):
        for level in ("INFO", "WARNING", "CRITICAL"):
            for body in RAW_BODIES:
                notifier._dedupe_state.clear()
                f = FakePost()
                title = "🚨 [운영자] [HOT-RELOAD] 운영 중 conditions 변경 — KRW-ZRO"
                self.send(f, level=level, title=title, body=body)
                self.assertEqual(len(f.to(OP)), 1)
                self.assertEqual(len(f.to(INV)), 1)
                self.assertEqual(f.to(INV)[0][1], f.to(OP)[0][1], (level, body))
                self.assertEqual(f.to(OP)[0][1], notifier._format_message(level, title, body))

    def test_copy_text_equals_when_operator_fails(self):
        """운영자 발송이 실패해도 사본 글은 운영자가 받았어야 할 글과 같다."""
        f = FakePost(codes={OP: 500})
        self.send(f, body=RAW_BODIES[1])
        self.assertEqual(f.to(INV)[0][1], notifier._format_message("WARNING", "⚠️ 시험 알림", RAW_BODIES[1]))

    def test_no_rewriting_code_left(self):
        src = (ROOT / "services" / "investor_copy.py").read_text(encoding="utf-8")
        for word in ("def sanitize", "SITE_TEXTS", "_WORDS", "_BANNED_LINE"):
            self.assertNotIn(word, src)
        self.assertIn("notifier._format_message(level, title, body)", src)
        self.assertNotIn("investor_title", (ROOT / "services" / "notifier.py").read_text(encoding="utf-8"))


# ================================================================ 호출 위치 수 (새 호출·빠진 호출을 알아채려고)
_IMPORT = re.compile(r"from services\.notifier import (.*)|from services import notifier")
_SCAN_TOPS = ("core", "engine", "services", "pages", "scripts", "v2")
_SKIP = ("services/notifier.py", "services/investor_copy.py")

# 2026-11-24 기준 파일별 notifier send 호출 식 수(합 62). 모두 운영자 글 그대로 사본이 간다
# (investor_copy=False 인 곳: scripts/key_expiry_check.py 단계 알림 · scripts/v2/notify_operator_test.py · 쉼 알림).
EXPECTED_CALLS = {
    "core/position_invariants.py": 1, "core/position_state.py": 1, "core/rest_reconcile.py": 1,
    "core/strategy_engine.py": 12, "core/strategy_incremental.py": 8, "core/trader.py": 11,
    "engine/boot_resume.py": 1, "engine/control_requests.py": 1, "engine/engine_manager.py": 2,
    "engine/live_loop.py": 8, "engine/order_reconciler.py": 2, "engine/pullback_params.py": 1,
    "engine/strategy_switch.py": 2, "pages/confirm_init_db.py": 1, "pages/dashboard.py": 5,
    "scripts/daily_health_check.py": 1, "scripts/key_expiry_check.py": 1, "scripts/v2/notify_operator_test.py": 1,
    "services/settings_history.py": 1, "services/trade_strategy.py": 1,
}
SHELL_SCRIPTS = ("monitor_tradebot_memory.sh", "watchdog_tradebot_engine.sh", "daily_digest_tradebot.sh",
                 "weekly_digest_tradebot.sh", "cleanup_tradebot_db.sh")


def _py_files():
    for top in _SCAN_TOPS:
        for p in sorted((ROOT / top).rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            if rel not in _SKIP:
                yield rel, p


def notify_call_counts() -> dict:
    """파일별 notifier send 호출 식의 수 (verifier 1122-01: import 줄이 아니라 실제 호출 식을 센다).

    그 파일이 import 한 이름(send · send as _notify · _notify_send · notify · notifier.send)마다
    `이름(` 이 나오는 줄을 센다(import 줄·def 줄 제외, 속성 호출 x.send( 는 notifier.send 만)."""
    out = {}
    for rel, p in _py_files():
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        names = set()
        for ln in lines:
            m = _IMPORT.search(ln)
            if not m:
                continue
            if m.group(1) is None:
                names.add("notifier.send")
                continue
            for part in m.group(1).split(","):
                part = part.split("#")[0].strip()
                mm = re.match(r"send(?:\s+as\s+(\w+))?$", part)
                if mm:
                    names.add(mm.group(1) or "send")
        if not names:
            continue
        pats = [re.compile(r"notifier\.send\s*\(") if n == "notifier.send"
                else re.compile(r"(?<![\w.])" + re.escape(n) + r"\s*\(") for n in names]
        n = 0
        for ln in lines:
            if "import" in ln or re.match(r"\s*def ", ln):
                continue
            if any(pt.search(ln) for pt in pats):
                n += 1
        if n:
            out[rel] = n
    return out


class CallSites(unittest.TestCase):
    def test_call_sites_unchanged(self):
        found = notify_call_counts()
        self.assertEqual(found, EXPECTED_CALLS)
        self.assertEqual(sum(found.values()), 62)

    def test_counter_sees_the_four_missed_calls(self):
        found = notify_call_counts()
        self.assertEqual(found["core/trader.py"], 11)                 # 948·1567 인증 실패 포함
        self.assertEqual(found["core/strategy_incremental.py"], 8)    # 1276 첫 봉 방어·1293 무결성 포함
        self.assertEqual(found["scripts/key_expiry_check.py"], 1)

    def test_shell_scripts_use_notifier(self):
        n = 0
        for name in SHELL_SCRIPTS:
            src = (ROOT / "scripts" / "server" / name).read_text(encoding="utf-8")
            c = src.count('"$NOTIFIER" "')
            self.assertGreaterEqual(c, 1, name)
            n += c
        self.assertEqual(n, 7)


# ================================================================ 키 만료 중복 막기 (3-4)
import key_expiry_check as chk  # noqa: E402
from v2 import key_expiry as ke  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

KST = ke.KST
EXP = datetime(2027, 11, 19, 12, 21, tzinfo=KST)


class KwNotifier:
    def __init__(self):
        self.sent = []

    def send(self, level, title, body="", audience=None, **kw):
        self.sent.append(dict(level=level, title=title, body=body, audience=audience, **kw))
        return True

    def _get_credentials(self, level=None):
        return TOKEN, OP

    def _get_operator_credentials(self):
        return TOKEN, OP

    def _format_message(self, level, title, body):
        return title + "\n" + body


class _Http401:
    def get(self, url, headers=None, timeout=None):
        return SimpleNamespace(status_code=401, json=lambda: {})


class KeyExpiryCopy(Base):
    def _root(self):
        tmp = Path(self.tmp.name) / "root"
        (tmp / "services" / "data").mkdir(parents=True, exist_ok=True)
        (tmp / ".env").write_text("UPBIT_ACCESS=netguard-access\nUPBIT_SECRET=netguard-secret-value-123456\n",
                                  encoding="utf-8")
        return tmp

    def test_plan_alerts_fail_part(self):
        st = {"expire_at": ke.iso(EXP), "first_fail_at": ke.iso(EXP - timedelta(days=40))}
        now = EXP - timedelta(days=14)
        merged = ke.plan_alerts(dict(st), now, "http_401", True)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0].get("fail_part"))
        sep = ke.plan_alerts(dict(st), now, "http_401", False)
        self.assertEqual([a["audience"] for a in sep], [None, "operator"])
        self.assertNotIn("fail_part", sep[0])
        plain = ke.plan_alerts(dict(st), now, None, True)
        self.assertNotIn("fail_part", plain[0])
        self.assertFalse(hasattr(ke, "FAIL_COPY_BODY"))

    def test_check_script_kwargs(self):
        src = (ROOT / "scripts" / "key_expiry_check.py").read_text(encoding="utf-8")
        self.assertIn('kw = {"investor_copy": False}', src)
        self.assertIn('a.get("audience") == "operator" or a.get("fail_part")', src)
        self.assertNotIn("investor_body", src)

    def test_stage_alert_not_copied(self):
        """단계 알림은 직접 발송(plan_investor_alerts)이 투자자에게 보내므로 사본은 없다."""
        kw = KwNotifier()
        with redirect_stdout(io.StringIO()):
            chk.run(root=self._root(), now=EXP - timedelta(days=14), http=SimpleNamespace(
                get=lambda url, headers=None, timeout=None: SimpleNamespace(
                    status_code=200, json=lambda: [{"access_key": "netguard-access", "expire_at": ke.iso(EXP)}])),
                notifier=kw)
        stage = [s for s in kw.sent if s["title"].startswith("업비트 키 만료")]
        self.assertTrue(stage)
        for s in stage:
            self.assertIs(s.get("investor_copy"), False)

    def test_fail_alert_copied_raw_separate(self):
        f = FakePost(codes={})
        with mock.patch.dict(os.environ, env()), \
                mock.patch.object(notifier, "_requests", f):
            with redirect_stdout(io.StringIO()):
                chk.run(root=self._root(), now=datetime(2026, 11, 24, 9, 5, tzinfo=KST), http=_Http401(),
                        notifier=notifier)
            ic.flush(3)
        op = [c for c in f.to(OP) if "키 만료일 점검 실패" in c[1]]
        inv = [c for c in f.to(INV) if "키 만료일 점검 실패" in c[1]]
        self.assertEqual(len(op), 1)
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0][1], op[0][1])          # 운영자 글 그대로(401·허용 IP 안내 포함)
        self.assertIn("401", inv[0][1])

    def test_operator_fail_repeats_copy_per_run(self):
        """한계(3-3): 운영자 발송이 계속 실패하면 점검마다 사본이 다시 간다 — 하루 2번 점검이면 최대 2번."""
        tmp = self._root()
        f = FakePost(codes={OP: 500})
        day = datetime(2026, 11, 24, 9, 5, tzinfo=KST)
        with mock.patch.dict(os.environ, env()), mock.patch.object(notifier, "_requests", f):
            for now in (day, day.replace(hour=21)):
                with redirect_stdout(io.StringIO()):
                    chk.run(root=tmp, now=now, http=_Http401(), notifier=notifier)
                ic.flush(3)
        self.assertEqual(len([c for c in f.to(INV) if "키 만료일 점검 실패" in c[1]]), 2)

    def test_output_copy_field(self):
        self.assertEqual(chk.copy_field(KwNotifier()), "off")
        with mock.patch.dict(os.environ, env()):
            self.assertEqual(chk.copy_field(notifier), "on")
        with mock.patch.dict(os.environ, env(TELEGRAM_CHAT_ID_INVESTOR="")):
            self.assertEqual(chk.copy_field(notifier), "off:채팅없음")
        self.off.write_text("")
        with mock.patch.dict(os.environ, env()):
            self.assertEqual(chk.copy_field(notifier), "off:파일")

    def test_test_investor_wording(self):
        src = (ROOT / "scripts" / "key_expiry_check.py").read_text(encoding="utf-8")
        self.assertNotIn("업비트 키 만료가 다가오면 이 대화방으로 알려 드립니다", src)
        self.assertIn("자동매매 알림 등록 시험", src)


class OperatorTool(Base):
    def test_notify_operator_test_no_copy(self):
        src = (ROOT / "scripts" / "v2" / "notify_operator_test.py").read_text(encoding="utf-8")
        self.assertIn("investor_copy=False", src)
        f = FakePost()
        with mock.patch.dict(os.environ, env()), mock.patch.object(notifier, "_requests", f):
            notifier.send(notifier.LEVEL_INFO, "운영자 채널 시험", "b", dedupe_key="operator_channel_test",
                          audience=notifier.AUDIENCE_OPERATOR, investor_copy=False)
            ic.flush(2)
        self.assertEqual(len(f.to(INV)), 0)


class StateLog(Base):
    def test_log_state_reasons(self):
        for environ, want in ((env(), "on reason=켜짐"), (env(TELEGRAM_INVESTOR_COPY="0"), "off reason=env끔"),
                              (env(TELEGRAM_CHAT_ID_INVESTOR=""), "off reason=채팅없음")):
            with mock.patch.dict(os.environ, environ), self.assertLogs("services.investor_copy", "INFO") as cm:
                ic.log_state()
            self.assertIn(f"[NOTIFY-COPY] {want}", cm.output[0])
        self.off.write_text("")
        with mock.patch.dict(os.environ, env()), self.assertLogs("services.investor_copy", "INFO") as cm:
            ic.log_state()
        self.assertIn("[NOTIFY-COPY] off reason=파일", cm.output[0])
        self.assertNotIn(INV, cm.output[0])


# ================================================================ 셸 (5절)
class Shell(unittest.TestCase):
    def test_two_calls_and_no_secret_in_argv(self):
        calls = run_shell("⚠️ 메모리 임계 초과 — tradebot", "현재: 1 MB\n/root/x.log 줄")
        self.assertEqual(len(calls), 2)
        for argv, stdin in calls:
            joined = "\n".join(argv)
            self.assertNotIn(TOKEN, joined)
            self.assertNotIn("chat_id=", joined)
            self.assertIn(TOKEN, stdin)
        self.assertIn(f"chat_id={OP}", calls[0][1])
        self.assertIn(f"chat_id={INV}", calls[1][1])

    def test_copy_text_equals_operator_text(self):
        for title, body in (("⚠️ 메모리 임계 초과 — tradebot", "현재: 1 MB\n/root/x.log 줄\nerr: boom"),
                            ("[STALE] tradebot 엔진", "last_line: Traceback\nsystemctl status tradebot"),
                            ("<꺾쇠> & 제목", ""),
                            ("🔄 tradebot 자동 재시작 완료", "사유: 메모리 임계 초과 (1 MB)\n\n→ Dashboard에서 엔진 재개 확인 권고")):
            calls = run_shell(title, body, lc_all="C")
            self.assertEqual(len(calls), 2, title)
            self.assertEqual(shell_text(calls[1]), shell_text(calls[0]), title)

    def test_operator_text_bytes_same_as_old(self):
        title, body = "🔄 tradebot 자동 재시작 완료", "사유: 메모리 임계 초과 (1 MB)\n\n→ Dashboard에서 엔진 재개 확인 권고"
        calls = run_shell(title, body, lc_all="C")
        self.assertEqual(shell_text(calls[0]), f"<b>{title}</b>\n<pre>{body}</pre>")

    def test_same_title_not_limited(self):
        """사본도 운영자와 같은 횟수로 간다(옛 30분 1번 제한 없앰)."""
        a = run_shell("⚠️ 메모리 임계 초과 — tradebot", "b")
        b = run_shell("⚠️ 메모리 임계 초과 — tradebot", "b")
        self.assertEqual((len(a), len(b)), (2, 2))

    def test_no_investor(self):
        self.assertEqual(len(run_shell("t", "b", inv_chat="")), 1)

    def test_switch_off_and_off_file(self):
        self.assertEqual(len(run_shell("t", "b", copy_switch="0")), 1)
        self.assertEqual(len(run_shell("t", "b", off=True)), 1)

    def test_same_chat(self):
        self.assertEqual(len(run_shell("t", "b", inv_chat=OP)), 1)


if __name__ == "__main__":
    unittest.main()
