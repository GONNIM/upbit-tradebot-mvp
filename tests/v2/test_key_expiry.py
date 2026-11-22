"""1122-01 업비트 키 만료 미리 알림 시험 (계획 docs/plans/2026-11-22-key-expiry-alert/plan.md 4절).

바깥 연결 없음 — requests·notifier 는 가짜. 키·토큰은 시험용 가짜 문자열.
"""
import ast
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import jwt

from v2 import key_expiry as ke

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import key_expiry_check as chk  # noqa: E402

from tests.v2.test_api_read import ApiBase  # noqa: E402

KST = ke.KST
EXP_S = "2027-11-19T12:21:56+09:00"
EXP = ke.parse_time(EXP_S)
FAKE_ACCESS = "test-access-1"
FAKE_SECRET = "test-secret-2"
FAKE_TOKEN = "000:test-token-3"


def at(days_before: int, hour=9, minute=5) -> datetime:
    """만료 날짜 기준 N일 전 그날 09:05 KST."""
    d = EXP.date() - timedelta(days=days_before)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=KST)


# ---------------- 계산 함수 ----------------
class TimeCalc(unittest.TestCase):
    def test_parse_requires_timezone(self):
        self.assertIsNone(ke.parse_time("2027-11-19T12:21:56"))
        self.assertIsNone(ke.parse_time(""))
        self.assertIsNone(ke.parse_time(None))
        self.assertIsNone(ke.parse_time("nope"))
        self.assertEqual(ke.parse_time("2027-11-19T03:21:56+00:00"), EXP)
        # 끝 값은 시간대를 바꿀 때 OverflowError — None 으로(홈 상태 응답이 500 이 되지 않게)
        self.assertIsNone(ke.parse_time("0001-01-01T00:00:00+09:00"))

    def test_days_left_calendar(self):
        self.assertEqual(ke.days_left(EXP, at(30)), 30)
        self.assertEqual(ke.days_left(EXP, at(0, 23, 59)), 0)
        self.assertEqual(ke.days_left(EXP, at(1, 23, 59)), 1)

    def test_due_step_boundaries(self):
        self.assertIsNone(ke.due_step(EXP, at(31), []))
        self.assertEqual(ke.due_step(EXP, at(30), []), 30)
        self.assertIsNone(ke.due_step(EXP, at(29), [30]))
        self.assertEqual(ke.due_step(EXP, at(14), [30]), 14)
        self.assertEqual(ke.due_step(EXP, at(0), [30, 14, 7, 3, 1]), 0)

    def test_skipped_days(self):
        self.assertEqual(ke.due_step(EXP, at(29), []), 30)       # 31 → 29: 30일 단계 1번
        self.assertEqual(ke.due_step(EXP, at(6), [30, 14]), 7)    # 15 → 6: 7일 단계 1번만
        self.assertIsNone(ke.due_step(EXP, at(5), [30, 14, 7]))

    def test_expired_has_no_step(self):
        self.assertIsNone(ke.due_step(EXP, EXP + timedelta(seconds=1), []))


class BadgeCalc(unittest.TestCase):
    def st(self, now, last_ok_delta=timedelta(hours=1), exp=EXP_S):
        return {"expire_at": exp, "last_ok_at": ke.iso(now - last_ok_delta) if last_ok_delta is not None else None}

    def test_levels(self):
        for days, level in ((31, "ok"), (30, "warn"), (8, "warn"), (7, "danger"), (0, "danger")):
            now = at(days)
            b = ke.badge(self.st(now), now)
            self.assertEqual(b["level"], level, days)
            self.assertEqual(b["days_left"], days)
        b = ke.badge(self.st(at(362)), at(362))
        self.assertEqual(b["label"], "업비트 키 · 2027-11-19 만료 (362일 남음)")
        self.assertIn("오늘 만료", ke.badge(self.st(at(0)), at(0))["label"])

    def test_order_expired_before_stale(self):
        now = EXP + timedelta(days=3)
        b = ke.badge(self.st(now, last_ok_delta=timedelta(days=4)), now)
        self.assertEqual(b["label"], "업비트 키 만료됨 — 새 키 필요")
        self.assertEqual(b["level"], "danger")

    def test_stale(self):
        now = at(100)
        b = ke.badge(self.st(now, last_ok_delta=timedelta(days=2, minutes=1)), now)
        self.assertEqual(b["level"], "danger")
        self.assertTrue(b["label"].startswith("업비트 키 만료일 확인 안 됨"))
        b = ke.badge(self.st(now, last_ok_delta=timedelta(days=1, hours=23)), now)
        self.assertEqual(b["level"], "ok")
        b = ke.badge({"expire_at": None, "last_ok_at": None}, now)
        self.assertEqual(b["label"], "업비트 키 만료일 확인 안 됨")
        self.assertIsNone(ke.badge("x", now))


class AlertPlan(unittest.TestCase):
    def base(self, now):
        s = {}
        ke.record_success(s, EXP_S, now)
        return s

    def run_days(self, state, days_list, err=None, same=True):
        sent = []
        for days in days_list:
            now = at(days) if isinstance(days, int) else days
            if err:
                ke.record_failure(state, err, now)
            for a in ke.plan_alerts(state, now, err, same):
                ke.apply_marks(state, a["marks"])
                sent.append((days, a["audience"], a["title"]))
        return sent

    def test_steps_once_each(self):
        s = self.base(at(40))
        sent = self.run_days(s, list(range(40, -1, -1)))
        self.assertEqual([d for d, _a, _t in sent], [30, 14, 7, 3, 1, 0])
        self.assertTrue(all(a is None for _d, a, _t in sent))

    def test_key_change_resets(self):
        s = self.base(at(10))
        self.run_days(s, [10, 7])
        self.assertEqual([a[1] for a in s["alerts"]], [14, 7])
        new = "2028-11-18T10:00:00+09:00"
        ke.record_success(s, new, at(6))
        self.assertEqual(s["alerts"], [])
        self.assertIsNone(s["last_alert_date"])
        d = ke.parse_time(new).date() - timedelta(days=30)
        now = datetime(d.year, d.month, d.day, 9, 5, tzinfo=KST)
        out = ke.plan_alerts(s, now, None, True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["marks"]["alert"], [new, 30])

    def test_expired_with_failures_one_alert_per_day(self):
        for err in ("http_401", "http_500", "timeout", "network"):
            s = self.base(at(1))
            s["alerts"] = [[EXP_S, x] for x in (30, 14, 7, 3, 1, 0)]
            days = [EXP + timedelta(days=k, hours=-3) for k in (1, 2, 3)]
            sent = self.run_days(s, days, err=err, same=True)
            per_day = {}
            for d, _a, _t in sent:
                per_day[d.date()] = per_day.get(d.date(), 0) + 1
            self.assertEqual(sorted(per_day.values()), [1, 1, 1], err)
            self.assertEqual(sent[0][2], "업비트 키 만료됨", err)

    def test_expiry_day_twice_daily(self):
        # 만료 당일 09:05 「오늘 만료」 → 21:05 「만료됨」(같은 날) → 다음 날 09:05 「만료됨」 → 21:05 없음
        s = self.base(at(1))
        s["alerts"] = [[EXP_S, x] for x in (30, 14, 7, 3, 1)]
        times = [at(0, 9, 5), at(0, 21, 5), at(-1, 9, 5), at(-1, 21, 5)]
        sent = self.run_days(s, times, err=None, same=True)
        self.assertEqual([(d, t) for d, _a, t in sent],
                         [(times[0], "업비트 키 만료 오늘"), (times[1], "업비트 키 만료됨"),
                          (times[2], "업비트 키 만료됨")])

    def test_401_separate_channel_daily(self):
        s = self.base(at(1))
        s["alerts"] = [[EXP_S, x] for x in (30, 14, 7, 3, 1, 0)]
        days = [EXP + timedelta(days=k, hours=-3) for k in (1, 2, 3)]
        sent = self.run_days(s, days, err="http_401", same=False)
        self.assertEqual(len(sent), 6)
        self.assertEqual(sum(1 for _d, a, _t in sent if a == "operator"), 3)

    def test_step_alert_during_failure(self):
        s = self.base(at(20))
        sent = self.run_days(s, [15, 14], err="http_500", same=False)
        self.assertIn((14, None, "업비트 키 만료 14일 전"), sent)

    def test_non401_failure_operator_after_two_days(self):
        s = self.base(at(100))
        sent = self.run_days(s, [90, 89], err="network", same=False)
        self.assertEqual(sent, [])
        sent = self.run_days(s, [88, 88], err="network", same=False)
        self.assertEqual([a for _d, a, _t in sent], ["operator"])

    def test_401_same_day_operator(self):
        s = self.base(at(100))
        sent = self.run_days(s, [90], err="http_401", same=False)
        self.assertEqual([a for _d, a, _t in sent], ["operator"])

    def test_merge_when_same_channel(self):
        s = self.base(at(20))
        ke.record_failure(s, "http_401", at(14))
        out = ke.plan_alerts(s, at(14), "http_401", True)
        self.assertEqual(len(out), 1)
        self.assertIn("(운영자)", out[0]["body"])
        self.assertIn("last_fail_alert_date", out[0]["marks"])

    def test_message_says_investor_issues(self):
        s = self.base(at(40))
        out = ke.plan_alerts(s, at(30), None, True)
        self.assertIn("투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요", out[0]["body"])
        self.assertIn("2027-11-19 12:21", out[0]["body"])


class StateFile(unittest.TestCase):
    def test_write_600_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ke.RESULT_NAME
            ke.write_state(p, {"a": 1})
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            self.assertEqual(ke.read_state(p), {"a": 1})
            self.assertEqual([x.name for x in Path(d).iterdir()], [ke.RESULT_NAME])
            p.write_text("{bad", encoding="utf-8")
            self.assertIsNone(ke.read_state(p))
            p.write_text("[1]", encoding="utf-8")
            self.assertIsNone(ke.read_state(p))
            self.assertIsNone(ke.read_state(Path(d) / "none.json"))


# ---------------- 점검 스크립트 ----------------
class FakeResp:
    def __init__(self, code, data=None, bad_json=False):
        self.status_code = code
        self._data = data
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("bad")
        return self._data


class Timeout(Exception):
    pass


class FakeHttp:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls, self.access = resp, exc, 0, []

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        assert url == chk.API_URL and timeout == chk.TIMEOUT
        tok = headers["Authorization"].split(" ", 1)[1]
        self.access.append(jwt.decode(tok, options={"verify_signature": False})["access_key"])
        if self.exc:
            raise self.exc
        return self.resp


class FakeNotifier:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    def send(self, level, title, body="", audience=None, **kw):
        self.sent.append((level, title, body, audience))
        return self.ok

    def _get_credentials(self, level=None):
        return FAKE_TOKEN, "100"

    def _get_operator_credentials(self):
        return FAKE_TOKEN, "100"

    def _format_message(self, level, title, body):
        return title + "\n" + body


class ScriptRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "services" / "data").mkdir(parents=True)
        (self.root / ".env").write_text(
            f"UPBIT_ACCESS={FAKE_ACCESS}\nUPBIT_SECRET={FAKE_SECRET}\nTELEGRAM_BOT_TOKEN={FAKE_TOKEN}\n",
            encoding="utf-8")
        self.path = self.root / "services" / "data" / ke.RESULT_NAME

    def run_chk(self, http, now=None, notifier=None):
        n = notifier or FakeNotifier()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = chk.run(root=self.root, now=now or at(30), http=http, notifier=n)
        return rc, buf.getvalue(), n

    def ok_list(self, extra=()):
        return [{"access_key": FAKE_ACCESS, "expire_at": EXP_S},
                {"access_key": "OTHER", "expire_at": "2026-11-18T23:08:39+09:00"}] + list(extra)

    def test_success_writes_state_and_alerts(self):
        http = FakeHttp(FakeResp(200, self.ok_list()))
        rc, out, n = self.run_chk(http)
        self.assertEqual(rc, 0)
        self.assertEqual(http.calls, 1)
        st = ke.read_state(self.path)
        self.assertEqual(st["expire_at"], EXP_S)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(len(n.sent), 1)
        self.assertEqual(out.strip(), "key_expiry ok days_left=30 alerts=1/1 investor=off err=None")
        # 같은 날 다시 돌아도 중복 없음
        _rc, _o, n2 = self.run_chk(FakeHttp(FakeResp(200, self.ok_list())))
        self.assertEqual(n2.sent, [])

    def test_failed_send_not_marked(self):
        self.run_chk(FakeHttp(FakeResp(200, self.ok_list())), notifier=FakeNotifier(ok=False))
        self.assertEqual(ke.read_state(self.path)["alerts"], [])

    def test_response_shapes(self):
        cases = [
            (FakeResp(200, {"error": {}}), "not_list"),
            (FakeResp(200, []), "key_not_found"),
            (FakeResp(200, [{"access_key": "OTHER", "expire_at": EXP_S}]), "key_not_found"),
            (FakeResp(200, self.ok_list([{"access_key": FAKE_ACCESS, "expire_at": EXP_S}])), "key_duplicate"),
            (FakeResp(200, [{"access_key": FAKE_ACCESS, "expire_at": "2027-11-19T12:21:56"}]), "bad_expire_at"),
            (FakeResp(200, bad_json=True), "bad_json"),
            (FakeResp(500), "http_500"),
            (FakeResp(401, {"error": {"name": "anything"}}), "http_401"),
        ]
        for resp, code in cases:
            self.assertEqual(chk.fetch_expire_at(FAKE_ACCESS, FAKE_SECRET, http=FakeHttp(resp)), (None, code))
        self.assertEqual(chk.fetch_expire_at(FAKE_ACCESS, FAKE_SECRET, http=FakeHttp(exc=Timeout())),
                         (None, "timeout"))
        self.assertEqual(chk.fetch_expire_at(FAKE_ACCESS, FAKE_SECRET, http=FakeHttp(exc=OSError())),
                         (None, "network"))

    def test_failure_keeps_last_expire_at(self):
        self.run_chk(FakeHttp(FakeResp(200, self.ok_list())), now=at(40))
        rc, out, _n = self.run_chk(FakeHttp(FakeResp(500)), now=at(39))
        self.assertEqual(rc, 1)
        st = ke.read_state(self.path)
        self.assertEqual(st["expire_at"], EXP_S)
        self.assertEqual(st["error_code"], "http_500")
        self.assertIn("err=http_500", out)

    def test_key_source_order(self):
        http = FakeHttp(FakeResp(200, []))
        self.run_chk(http)
        self.assertEqual(http.access, [FAKE_ACCESS])          # secrets.toml 없음 → .env
        sec = self.root / ".streamlit"
        sec.mkdir()
        (sec / "secrets.toml").write_text('[secrets]\nUPBIT_ACCESS = "NESTED"\n', encoding="utf-8")
        http = FakeHttp(FakeResp(200, []))
        self.run_chk(http)
        self.assertEqual(http.access, [FAKE_ACCESS])          # 최상위에 없으면 .env (서버 실측 모양)
        (sec / "secrets.toml").write_text('UPBIT_ACCESS = "TOPLEVELACCESS"\nUPBIT_SECRET = "TOPSECRET"\n',
                                          encoding="utf-8")
        http = FakeHttp(FakeResp(200, []))
        self.run_chk(http)
        self.assertEqual(http.access, ["TOPLEVELACCESS"])     # 최상위에 있으면 그것(config.py 와 같은 순서)

    def test_no_keys(self):
        (self.root / ".env").write_text("", encoding="utf-8")
        http = FakeHttp(FakeResp(200, []))
        rc, out, _n = self.run_chk(http)
        self.assertEqual((rc, http.calls), (1, 0))
        self.assertIn("err=no_keys", out)

    def test_no_secret_in_output_or_file(self):
        n = FakeNotifier()
        for resp in (FakeResp(200, self.ok_list()), FakeResp(401), FakeResp(200, [])):
            _rc, out, _ = self.run_chk(FakeHttp(resp), notifier=n)
            text = out + self.path.read_text(encoding="utf-8") + json.dumps(n.sent, ensure_ascii=False)
            for s in (FAKE_ACCESS, FAKE_SECRET, FAKE_TOKEN, "OTHER"):
                self.assertNotIn(s, text)


class SameChannel(unittest.TestCase):
    """합치기는 WARNING·CRITICAL 등급 채널이 모두 운영자 채팅과 같을 때만."""

    class N:
        def __init__(self, chats, op):
            self.chats, self.op = chats, op

        def _get_credentials(self, level=None):
            return FAKE_TOKEN, self.chats.get(level, self.chats.get(None))

        def _get_operator_credentials(self):
            return FAKE_TOKEN, self.op

    def test_all_same(self):
        self.assertTrue(chk._same_channel(self.N({None: "100"}, "100")))

    def test_critical_differs(self):
        self.assertFalse(chk._same_channel(self.N({None: "100", "CRITICAL": "200"}, "100")))

    def test_no_operator(self):
        self.assertFalse(chk._same_channel(self.N({None: "100"}, None)))


class ImportBoundary(unittest.TestCase):
    BANNED = ("core", "pyupbit", "config", "engine", "streamlit")

    def imports(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        return names

    def test_no_order_path_imports(self):
        for p in (ROOT / "scripts" / "key_expiry_check.py", ROOT / "v2" / "key_expiry.py"):
            self.assertFalse(self.imports(p) & set(self.BANNED), p.name)
        self.assertNotIn("/v1/orders", (ROOT / "scripts" / "key_expiry_check.py").read_text(encoding="utf-8"))

    def test_v2_module_stdlib_only(self):
        self.assertLessEqual(self.imports(ROOT / "v2" / "key_expiry.py"),
                             {"json", "os", "tempfile", "datetime", "pathlib", "typing", "zoneinfo"})


class CronFile(unittest.TestCase):
    def test_cron_line(self):
        lines = [ln for ln in (ROOT / "deploy" / "key-expiry.cron").read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        self.assertEqual(len(lines), 1)
        ln = lines[0]
        self.assertTrue(ln.startswith("5 9,21 * * * cd /root/upbit-tradebot-mvp && "))
        for part in ("umask 077", "flock -n ", "timeout 60 ", "venv/bin/python scripts/key_expiry_check.py"):
            self.assertIn(part, ln)
        self.assertNotIn("%", ln)


# ---------------- 1122-01 ㉠ 투자자 채팅 ----------------
class FakePost:
    def __init__(self, code=200, exc=None):
        self.code, self.exc, self.calls = code, exc, []

    def __call__(self, url, data=None, timeout=None):
        self.calls.append((url, dict(data or {})))
        if self.exc:
            raise self.exc
        return FakeResp(self.code)


class InvestorPlan(unittest.TestCase):
    def test_steps_once_each_and_separate_marks(self):
        s = {}
        ke.record_success(s, EXP_S, at(40))
        got = []
        for d in range(40, -1, -1):
            for a in ke.plan_investor_alerts(s, at(d)):
                ke.apply_marks(s, a["marks"])
                got.append(d)
        self.assertEqual(got, [30, 14, 7, 3, 1, 0])
        self.assertEqual(s.get("alerts"), [])          # 운영자 쪽 기록은 건드리지 않음
        self.assertEqual(len(s["investor_alerts"]), 6)

    def test_expired_once_per_day(self):
        s = {}
        ke.record_success(s, EXP_S, at(1))
        after = EXP + timedelta(hours=9)
        a = ke.plan_investor_alerts(s, after)
        self.assertEqual([x["title"] for x in a], ["업비트 키 만료됨"])
        ke.apply_marks(s, a[0]["marks"])
        self.assertEqual(ke.plan_investor_alerts(s, after + timedelta(hours=1)), [])
        self.assertEqual(len(ke.plan_investor_alerts(s, after + timedelta(days=1))), 1)

    def test_key_change_resets(self):
        s = {}
        ke.record_success(s, EXP_S, at(30))
        ke.apply_marks(s, ke.plan_investor_alerts(s, at(30))[0]["marks"])
        ke.record_success(s, "2028-11-19T12:00:00+09:00", at(29))
        self.assertEqual(s["investor_alerts"], [])
        self.assertIsNone(s["last_investor_expired_date"])

    def test_body_warns_no_key_in_messenger(self):
        s = {}
        ke.record_success(s, EXP_S, at(30))
        self.assertIn("키 값은 메신저에 적지 마세요", ke.plan_investor_alerts(s, at(30))[0]["body"])

    def test_no_expire_no_alert(self):
        self.assertEqual(ke.plan_investor_alerts({}, at(3)), [])


class InvestorRun(unittest.TestCase):
    setUp = ScriptRun.setUp
    ok_list = ScriptRun.ok_list
    ENV = {"TELEGRAM_BOT_TOKEN": FAKE_TOKEN, "TELEGRAM_CHAT_ID_INVESTOR": "777"}

    def run_inv(self, now, post, notifier=None, env=None):
        n = notifier or FakeNotifier()
        buf = io.StringIO()
        from unittest import mock
        with mock.patch.dict(os.environ, env if env is not None else self.ENV), redirect_stdout(buf):
            rc = chk.run(root=self.root, now=now, http=FakeHttp(FakeResp(200, self.ok_list())), notifier=n, post=post)
        return rc, buf.getvalue(), n

    def test_both_channels_once(self):
        p = FakePost()
        _rc, out, n = self.run_inv(at(30), p)
        self.assertIn("alerts=1/1 investor=1/1", out)
        self.assertEqual(len(n.sent), 1)
        self.assertEqual(len(p.calls), 1)
        self.assertEqual(p.calls[0][1]["chat_id"], "777")
        _rc, out2, n2 = self.run_inv(at(30), FakePost())
        self.assertIn("alerts=0/0 investor=0/0", out2)

    def test_investor_fail_retries_without_operator_resend(self):
        self.run_inv(at(30), FakePost(code=403))
        st = ke.read_state(self.path)
        self.assertEqual(len(st["alerts"]), 1)
        self.assertEqual(st.get("investor_alerts") or [], [])
        p = FakePost()
        _rc, out, n = self.run_inv(at(29), p)
        self.assertIn("alerts=0/0 investor=1/1", out)
        self.assertEqual(n.sent, [])

    def test_exception_in_post_is_quiet(self):
        _rc, out, _n = self.run_inv(at(30), FakePost(exc=RuntimeError("https://x/bot" + FAKE_TOKEN)))
        self.assertIn("investor=0/1", out)
        self.assertNotIn(FAKE_TOKEN, out)

    def test_off_when_not_set_or_same_as_default(self):
        _rc, out, _n = self.run_inv(at(30), FakePost(), env={"TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
                                                               "TELEGRAM_CHAT_ID_INVESTOR": ""})
        self.assertIn("investor=off", out)
        p = FakePost()
        _rc, out, _n = self.run_inv(at(29), p, env={"TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
                                                    "TELEGRAM_CHAT_ID_INVESTOR": "100"})
        self.assertIn("investor=off", out)       # 기본 채널(100)과 같으면 두 번 보내지 않음
        self.assertEqual(p.calls, [])

    def test_investor_test_message(self):
        from unittest import mock
        p, buf = FakePost(), io.StringIO()
        with mock.patch.dict(os.environ, self.ENV), redirect_stdout(buf):
            rc = chk.send_investor_test(root=self.root, notifier=FakeNotifier(), post=p)
        self.assertEqual((rc, buf.getvalue().strip()), (0, "investor_test ok"))
        self.assertEqual(p.calls[0][1]["chat_id"], "777")
        self.assertFalse(self.path.exists())     # 결과 파일·업비트 조회는 건드리지 않음
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID_INVESTOR": ""}), redirect_stdout(buf):
            rc = chk.send_investor_test(root=self.root, notifier=FakeNotifier(), post=FakePost())
        self.assertEqual((rc, buf.getvalue().strip()), (1, "investor_test off"))
        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.ENV), redirect_stdout(buf):
            rc = chk.send_investor_test(root=self.root, notifier=FakeNotifier(), post=FakePost(code=403))
        self.assertEqual((rc, buf.getvalue().strip()), (1, "investor_test fail http_403"))
        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.ENV), redirect_stdout(buf):
            chk.send_investor_test(root=self.root, notifier=FakeNotifier(),
                                   post=FakePost(exc=RuntimeError("https://x/bot" + FAKE_TOKEN)))
        self.assertEqual(buf.getvalue().strip(), "investor_test fail RuntimeError")


sys.path.insert(0, str(ROOT / "scripts"))
import telegram_investor_register as reg  # noqa: E402


class FakeGet:
    def __init__(self, updates):
        self.updates, self.urls = updates, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if url.endswith("/getMe"):
            return FakeResp(200, {"ok": True, "result": {"username": "upbit_tradebot_bot", "first_name": "알림"}})
        return FakeResp(200, {"ok": True, "result": self.updates})


class Register(unittest.TestCase):
    UPD = [{"message": {"chat": {"id": 100, "type": "private", "first_name": "운영"}, "date": 1795000000, "text": "/start"}},
           {"message": {"chat": {"id": 987654321, "type": "private", "first_name": "투자", "username": "inv"},
                        "date": 1795000100, "text": "/start"}},
           {"message": {"chat": {"id": -5, "type": "group", "title": "g"}, "date": 1795000200, "text": "x"}}]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = self.root / ".env"
        self.env.write_text(f'UPBIT_ACCESS={FAKE_ACCESS}\nTELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID=100\n'
                            'QUOTED="a b"', encoding="utf-8")
        os.chmod(self.env, 0o600)

    def main(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = reg.main(argv, root=self.root, get=FakeGet(self.UPD))
        return rc, buf.getvalue()

    def test_list_hides_ids_and_token(self):
        rc, out = self.main([])
        self.assertEqual(rc, 0)
        self.assertIn("봇: @upbit_tradebot_bot", out)
        self.assertIn("2. 투자 @inv", out)
        self.assertIn("운영자 채팅", out)
        self.assertNotIn("g", out.split("봇:")[1].split("\n", 1)[1].replace("@inv", ""))  # 그룹 대화는 빠짐
        for s in ("987654321", FAKE_TOKEN):
            self.assertNotIn(s, out)
        self.assertNotIn("TELEGRAM_CHAT_ID_INVESTOR", self.env.read_text(encoding="utf-8"))

    def test_pick_writes_env_600_and_keeps_lines(self):
        rc, out = self.main(["--pick", "2"])
        self.assertEqual(rc, 0)
        self.assertIn("등록함: 투자 (새로 넣음)", out)
        self.assertNotIn("987654321", out)
        text = self.env.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(f"UPBIT_ACCESS={FAKE_ACCESS}\nTELEGRAM_BOT_TOKEN={FAKE_TOKEN}\n"))
        self.assertIn('QUOTED="a b"\nTELEGRAM_CHAT_ID_INVESTOR=987654321\n', text)
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])   # 사본 없음
        rc, out = self.main(["--pick", "2"])
        self.assertIn("바꿈", out)
        self.assertEqual(self.env.read_text(encoding="utf-8").count("TELEGRAM_CHAT_ID_INVESTOR="), 1)

    def test_pick_operator_refused(self):
        rc, out = self.main(["--pick", "1"])
        self.assertEqual(rc, 1)
        self.assertIn("운영자 채팅과 같음", out)
        self.assertNotIn("TELEGRAM_CHAT_ID_INVESTOR", self.env.read_text(encoding="utf-8"))

    def test_bad_pick(self):
        self.assertEqual(self.main(["--pick", "9"])[0], 1)
        self.assertEqual(self.main(["--pick", "x"])[0], 1)

    def test_no_order_path_imports(self):
        names = ImportBoundary().imports(ROOT / "scripts" / "telegram_investor_register.py")
        self.assertFalse(names & set(ImportBoundary.BANNED))


# ---------------- 신버전 status 응답 ----------------
class StatusKeyExpiry(ApiBase):
    def setUp(self):
        super().setUp()
        self.make_live_db()
        self.set_strategy()
        self.kf = self.data / ke.RESULT_NAME

    def test_no_file_no_field(self):
        code, body = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        self.assertNotIn("key_expiry", body)

    def test_field_present(self):
        now = datetime.now(KST)
        ke.write_state(self.kf, {"expire_at": ke.iso(now + timedelta(days=100)), "last_ok_at": ke.iso(now)})
        code, body = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        k = body["key_expiry"]
        self.assertEqual(k["level"], "ok")
        self.assertEqual(k["days_left"], 100)
        self.assertEqual(set(k), {"expire_at", "days_left", "last_ok_at", "level", "label"})

    def test_expired_first(self):
        now = datetime.now(KST)
        ke.write_state(self.kf, {"expire_at": ke.iso(now - timedelta(days=3)),
                                 "last_ok_at": ke.iso(now - timedelta(days=4))})
        _c, body = self.get_json("/v2/api/status")
        self.assertEqual(body["key_expiry"]["label"], "업비트 키 만료됨 — 새 키 필요")

    def test_broken_or_unreadable_file_still_200(self):
        self.kf.write_text("{broken", encoding="utf-8")
        code, body = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        self.assertNotIn("key_expiry", body)
        self.kf.write_text("{}", encoding="utf-8")
        os.chmod(self.kf, 0)
        self.addCleanup(os.chmod, self.kf, 0o600)
        code, body = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        if os.geteuid() != 0:
            self.assertNotIn("key_expiry", body)


if __name__ == "__main__":
    unittest.main()
