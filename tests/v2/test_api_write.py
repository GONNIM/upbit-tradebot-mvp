"""v2 「저장만 하기」 API 시험 (Task 8). 임시 폴더만 사용한다."""
import ast
import hashlib
import json
import os
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

from v2 import db, params_schema
from v2.server import DEFAULT_ORIGIN
from tests.v2 import test_api_read as base

ROOT = Path(__file__).resolve().parents[2]
ORIG_HTML = ROOT / "docs" / "specs" / "MA60_200_GoldenCross_Pullback_Backtester_2610201820.html"
SAVE_URL = "/v2/api/params/save"
CURRENT_URL = "/v2/api/params/current"

VALID = {
    "symbol": "jtousdt", "maType": "ema", "src": "3m", "days": 30,
    "ma60p": 60, "ma200p": 200, "pullbackP": 60, "slopeLB": 20,
    "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": "yes",
    "maxSplits": 5, "maxPullbackBuys": 5, "tp": 1.0, "sl": 1.5,
    "capital": 10000, "fee": 0.05, "deadcross": "yes", "compounding": "no",
}
FILE_KEYS = ["ticker", "interval", "maType", "ma60p", "ma200p", "pullbackP",
             "slopeLB", "minSlope", "slopeDrop", "buyOnGoldenCross", "maxSplits",
             "maxPullbackBuys", "tp", "sl", "deadcross", "compounding",
             "capital", "fee"]
INITIAL_FILE = '{"ticker": "KRW-OLD", "interval": "minute1"}\n'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class WriteBase(base.ApiBase):
    def setUp(self):
        super().setUp()
        self.make_live_db()
        self.set_strategy("EMA", "KRW-ZRO", "minute3")
        self.pb = db.pullback_params_path(self.USER)
        self.pb.write_text(INITIAL_FILE, encoding="utf-8")

    def headers(self, origin=DEFAULT_ORIGIN, **kw):
        h = dict(self.cookie(**kw))
        h["Content-Type"] = "application/json"
        if origin is not None:
            h["Origin"] = origin
        return h

    def post(self, body, raw=False, **kw):
        data = body if raw else json.dumps({"params": body, "source": "binance"})
        return self.fetch(SAVE_URL, method="POST", body=data, headers=self.headers(**kw))

    def post_json(self, body, **kw):
        r = self.fetch(SAVE_URL, method="POST", body=json.dumps(body),
                       headers=self.headers(**kw))
        return r

    def hist_rows(self):
        p = db.v2hist_path(self.USER)
        if not p.exists():
            return []
        conn = sqlite3.connect(p)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM v2_settings_history ORDER BY id")]
        finally:
            conn.close()

    def body(self, r):
        return json.loads(r.body.decode())

    def snap(self):
        st = self.pb.stat()
        return self.pb.read_bytes(), st.st_mtime_ns


class TestSave(WriteBase):
    def test_save_writes_only_pullback_file(self):
        other = [self.root / f"{self.USER}_latest_params_EMA.json",
                 self.root / f"{self.USER}_active_strategy.txt"]
        (self.root / f"{self.USER}_latest_params_MACD.json").write_text(
            '{"ticker": "KRW-X"}', encoding="utf-8")
        other.append(self.root / f"{self.USER}_latest_params_MACD.json")
        before = [sha(p) for p in other]
        r = self.post(VALID)
        self.assertEqual(r.code, 200, r.body)
        self.assertEqual([sha(p) for p in other], before)
        data = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertEqual(list(data.keys()), FILE_KEYS)
        self.assertEqual(data, {
            "ticker": "KRW-ZRO", "interval": "minute3", "maType": "ema",
            "ma60p": 60, "ma200p": 200, "pullbackP": 60, "slopeLB": 20,
            "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": True,
            "maxSplits": 5, "maxPullbackBuys": 5, "tp": 1.0, "sl": 1.5,
            "deadcross": True, "compounding": False, "capital": 10000, "fee": 0.05})
        self.assertNotIn("days", data)
        self.assertNotIn("symbol", data)
        # 같은 디렉터리에 다른 파일이 생기지 않았다(임시 파일+rename 금지)
        names = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(names, sorted([
            "services", f"{self.USER}_active_strategy.txt",
            f"{self.USER}_latest_params_EMA.json",
            f"{self.USER}_latest_params_MACD.json",
            f"{self.USER}_latest_params_PULLBACK.json"]))

    def test_save_inserts_v2hist_row(self):
        r = self.post(VALID)
        self.assertEqual(r.code, 200)
        b = self.body(r)
        rows = self.hist_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source_page"], "v2_backtester")
        self.assertEqual(row["strategy_type"], "PULLBACK")
        self.assertEqual(row["note"], "source=binance")
        self.assertEqual(row["user_id"], self.USER)
        self.assertEqual(row["saved_at"], b["saved_at"])
        self.assertEqual(row["id"], b["history_id"])
        expect = dict(VALID, symbol="JTOUSDT")
        self.assertEqual(json.loads(row["params_json"]), expect)
        self.assertEqual(list(json.loads(row["params_json"]).keys()),
                         list(params_schema.PARAM_FIELDS.keys()))
        self.assertEqual(b["ticker"], "KRW-ZRO")
        self.assertEqual(b["interval"], "minute3")
        self.assertTrue(b["ok"])

    def test_invalid_param_400_and_file_unchanged(self):
        cases = [
            ("days", 4), ("days", 366), ("ma60p", 1), ("maxSplits", 11),
            ("maxPullbackBuys", 0), ("slopeDrop", -0.1),
            ("tp", None), ("sl", True), ("fee", "0.05"), ("capital", float("nan")),
            ("capital", float("inf")),
            ("days", 30.5), ("slopeLB", 1.5),
            ("maType", "wma"), ("src", "15m"), ("deadcross", "maybe"), ("compounding", 1),
            ("symbol", "A"), ("symbol", "BTC-USDT"), ("symbol", "x" * 21), ("symbol", 5),
            ("tp", 10 ** 400), ("days", 10 ** 400),
            # 결정 1024-03 가: 서버 추가 하한
            ("tp", 0), ("sl", 0), ("capital", 0),
            ("tp", -1), ("sl", -3), ("capital", -5), ("fee", -1),
        ]
        before = self.snap()
        for field, val in cases:
            p = dict(VALID)
            p[field] = val
            raw = json.dumps({"params": p, "source": "binance"})
            r = self.fetch(SAVE_URL, method="POST", body=raw, headers=self.headers())
            self.assertEqual(r.code, 400, (field, val, r.body))
            b = self.body(r)
            self.assertEqual(b, {"error": "invalid_param", "field": field}, (field, val))
            self.assertEqual(self.snap(), before, (field, val))
            self.assertEqual(self.hist_rows(), [], (field, val))

    def test_integer_float_accepted(self):
        p = dict(VALID, days=30.0, ma60p=60.0)
        r = self.post(p)
        self.assertEqual(r.code, 200, r.body)
        data = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertIsInstance(data["ma60p"], int)
        # 양끝 포함
        r = self.post(dict(VALID, days=5, ma60p=500, maxSplits=0))
        self.assertEqual(r.code, 200)

    def test_server_extra_limits_boundaries(self):
        self.assertEqual(params_schema.SERVER_EXTRA_LIMITS, {
            "tp": ("gt", 0), "sl": ("gt", 0), "capital": ("gt", 0), "fee": ("ge", 0)})
        r = self.post(dict(VALID, fee=0, tp=0.1))
        self.assertEqual(r.code, 200, r.body)
        data = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertEqual(data["fee"], 0)
        self.assertEqual(data["tp"], 0.1)
        # 0 이하 경계: 순수 함수 수준
        for name, val, ok in (("tp", 0, False), ("sl", 0, False), ("capital", 0, False),
                              ("fee", 0, True), ("tp", -0.01, False), ("fee", -0.01, False),
                              ("sl", 0.01, True), ("capital", 1, True)):
            p = dict(VALID, **{name: val})
            if ok:
                params_schema.validate_params(p)
            else:
                with self.assertRaises(ValueError) as cm:
                    params_schema.validate_params(p)
                self.assertEqual(str(cm.exception), name)

    def test_unknown_key_400(self):
        before = self.snap()
        extra = dict(VALID, extra=1)
        missing = {k: v for k, v in VALID.items() if k != "fee"}
        for p in (extra, missing, {}):
            r = self.post(p)
            self.assertEqual(r.code, 400)
            self.assertEqual(self.body(r), {"error": "invalid_param", "field": "keys"})
            self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_save_bad_origin_403(self):
        before = self.snap()
        for origin in (None, "https://evil.example"):
            r = self.fetch(SAVE_URL, method="POST",
                           body=json.dumps({"params": VALID, "source": "binance"}),
                           headers=self.headers(origin=origin))
            self.assertEqual(r.code, 403)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_missing_pullback_file_500_no_create(self):
        self.pb.unlink()
        r = self.post(VALID)
        self.assertEqual(r.code, 500)
        b = self.body(r)
        self.assertEqual(b["error"], "pullback_file_missing")
        self.assertFalse(self.pb.exists())
        self.assertEqual(self.hist_rows(), [])

    def test_save_does_not_touch_live_db(self):
        live = db.live_db_path(self.USER)
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings_history(id INTEGER)")
        self.conn.commit()

        def state():
            st = live.stat()
            n = self.conn.execute("SELECT COUNT(*) FROM settings_history").fetchone()[0]
            return st.st_mtime_ns, st.st_size, sha(live), n

        before = state()
        r = self.post(VALID)
        self.assertEqual(r.code, 200)
        self.assertEqual(state(), before)

    def test_engine_ticker_from_active_strategy(self):
        self.set_strategy("MACD", "KRW-JTO", "minute1")
        r = self.post(VALID)
        self.assertEqual(r.code, 200)
        data = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertEqual(data["ticker"], "KRW-JTO")
        self.assertNotIn("JTOUSDT", self.pb.read_text(encoding="utf-8"))
        self.assertNotIn("symbol", data)

    def test_engine_ticker_unknown_409_file_unchanged(self):
        user = self.USER
        strat = self.root / f"{user}_active_strategy.txt"
        params = self.root / f"{user}_latest_params_EMA.json"
        cases = {
            "no strategy file": lambda: strat.unlink(),
            "no ticker": lambda: params.write_text('{"interval": "minute3"}'),
            "bad ticker": lambda: params.write_text('{"ticker": "BTC-KRW"}'),
            "ticker not str": lambda: params.write_text('{"ticker": 5}'),
            "strategy params missing": lambda: params.unlink(),
            "bad strategy name": lambda: strat.write_text("bad name!\n"),
        }
        for label, mutate in cases.items():
            self.set_strategy("EMA", "KRW-ZRO", "minute3")
            mutate()
            before = self.snap()
            r = self.post(VALID)
            self.assertEqual(r.code, 409, label)
            self.assertEqual(self.body(r), {"error": "engine_ticker_unknown"}, label)
            self.assertEqual(self.snap(), before, label)
            self.assertEqual(self.hist_rows(), [], label)

    def test_interval_and_bool_mapping(self):
        for src, iv in (("1m", "minute1"), ("3m", "minute3"),
                        ("5m", "minute5"), ("1h", "minute60")):
            r = self.post(dict(VALID, src=src))
            self.assertEqual(r.code, 200)
            self.assertEqual(json.loads(self.pb.read_text())["interval"], iv)
            self.assertEqual(self.body(r)["interval"], iv)
        for yes, no in (("yes", "no"), ("no", "yes")):
            r = self.post(dict(VALID, buyOnGoldenCross=yes, deadcross=no, compounding=yes))
            self.assertEqual(r.code, 200)
            d = json.loads(self.pb.read_text())
            self.assertIs(d["buyOnGoldenCross"], yes == "yes")
            self.assertIs(d["deadcross"], no == "yes")
            self.assertIs(d["compounding"], yes == "yes")

    def test_file_write_failure_500_file_unchanged(self):
        before = self.snap()
        # (가) open 실패
        with mock.patch("v2.api_write.open", side_effect=PermissionError(), create=True):
            r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_write_failed"})
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])
        # (가-2) 읽기 실패: 파일이 UTF-8 이 아님
        self.pb.write_bytes(b"\xff\xfe\x00bad")
        bad = self.snap()
        r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_write_failed"})
        self.assertEqual(self.snap(), bad)
        self.pb.write_text(INITIAL_FILE, encoding="utf-8")
        before = self.snap()
        # (나) fsync 첫 호출만 실패 → 되쓰기 성공
        real = os.fsync
        with mock.patch("v2.api_write.os.fsync", side_effect=OSError()) as m:
            # 첫 호출만 실패, 이후는 진짜 fsync 를 부르도록 함수로 대체
            calls = {"n": 0}

            def flaky(fd):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("boom")
                return real(fd)
            m.side_effect = flaky
            r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_write_failed"})
        self.assertEqual(self.pb.read_bytes(), before[0])
        self.assertEqual(self.hist_rows(), [])
        # (나-2) write 단계 실패
        calls = {"n": 0}
        real_open = open

        class FlakyFile:
            def __init__(self, f):
                self._f = f

            def write(self, s):
                calls["n"] += 1
                if calls["n"] == 1:
                    self._f.write(s[:5])  # 일부만 쓰고 실패
                    raise OSError("disk")
                return self._f.write(s)

            def __getattr__(self, k):
                return getattr(self._f, k)

            def __enter__(self):
                self._f.__enter__()
                return self

            def __exit__(self, *a):
                return self._f.__exit__(*a)

        with mock.patch("v2.api_write.open",
                        side_effect=lambda *a, **k: FlakyFile(real_open(*a, **k)),
                        create=True):
            r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_write_failed"})
        self.assertEqual(self.pb.read_bytes(), before[0])
        self.assertEqual(self.hist_rows(), [])
        # (다) 되쓰기까지 실패 → file_changed + 경고 로그, 이력 없음
        with mock.patch("v2.api_write.os.fsync", side_effect=OSError("always")):
            with self.assertLogs("v2.api_write", level="WARNING") as cm:
                r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_changed"})
        self.assertEqual(len(cm.records), 1)
        text = cm.records[0].getMessage()
        self.assertIn(self.USER, text)
        self.assertNotIn("KRW-ZRO", text)
        self.assertEqual(self.hist_rows(), [])

    def test_saved_at_lookup_failure_still_200(self):
        real = db.open_v2hist
        calls = {"n": 0}

        def flaky(user):
            calls["n"] += 1
            if calls["n"] == 1:
                return real(user)
            raise sqlite3.OperationalError("lookup")

        with mock.patch("v2.db.open_v2hist", side_effect=flaky):
            r = self.post(VALID)
        self.assertEqual(r.code, 200)
        b = self.body(r)
        self.assertIsNone(b["saved_at"])
        self.assertTrue(b["ok"])
        self.assertEqual(len(self.hist_rows()), 1)
        self.assertEqual(b["history_id"], self.hist_rows()[0]["id"])
        self.assertEqual(json.loads(self.pb.read_text())["ticker"], "KRW-ZRO")

    def test_body_too_large_400(self):
        before = self.snap()
        big = json.dumps({"params": VALID, "source": "binance", "pad": "x" * 70000})
        r = self.post(big, raw=True)
        self.assertEqual(r.code, 400)
        self.assertEqual(self.body(r), {"error": "bad_request"})
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_file_removed_between_read_and_write_500_no_create(self):
        from v2 import api_write
        real = api_write._write_in_place

        def vanish(path, text):
            Path(path).unlink()
            return real(path, text)   # open 이 FileNotFoundError

        with mock.patch("v2.api_write._write_in_place", side_effect=vanish) as m:
            r = self.post(VALID)
        self.assertEqual(m.call_count, 1)   # 되쓰기를 시도하지 않음
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r)["error"], "pullback_file_missing")
        self.assertFalse(self.pb.exists())
        self.assertEqual(self.hist_rows(), [])

    def test_deeply_nested_json_400(self):
        before = self.snap()
        raw = "[" * 60000
        self.assertLess(len(raw), 64 * 1024)
        r = self.post(raw, raw=True)
        self.assertEqual(r.code, 400)
        self.assertEqual(self.body(r), {"error": "bad_request"})
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_history_failure_restores_file(self):
        before = self.snap()
        with mock.patch("v2.db.insert_history", side_effect=sqlite3.OperationalError("x")):
            r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "history_failed"})
        self.assertEqual(self.pb.read_bytes(), before[0])
        self.assertEqual(self.hist_rows(), [])

    def test_history_failure_and_restore_failure_file_changed(self):
        real = os.fsync
        calls = {"n": 0}

        def flaky(fd):
            calls["n"] += 1
            if calls["n"] >= 2:  # 첫 번째(저장)는 성공, 되쓰기는 실패
                raise OSError("x")
            return real(fd)

        with mock.patch("v2.db.insert_history", side_effect=RuntimeError("x")), \
                mock.patch("v2.api_write.os.fsync", side_effect=flaky):
            with self.assertLogs("v2.api_write", level="WARNING") as cm:
                r = self.post(VALID)
        self.assertEqual(r.code, 500)
        self.assertEqual(self.body(r), {"error": "file_changed"})
        self.assertEqual(len(cm.records), 1)

    def test_no_live_db_404_file_unchanged(self):
        db.live_db_path(self.USER).unlink()
        before = self.snap()
        r = self.post(VALID)
        self.assertEqual(r.code, 404)
        self.assertEqual(self.body(r), {"error": "no_data"})
        self.assertEqual(self.snap(), before)
        self.assertFalse(db.v2hist_path(self.USER).exists())

    def test_source_not_binance_400(self):
        before = self.snap()
        for src in ("upbit", None, 1):
            r = self.post_json({"params": VALID, "source": src})
            self.assertEqual(r.code, 400)
            self.assertEqual(self.body(r), {"error": "bad_request"})
        r = self.post_json({"params": VALID})
        self.assertEqual(r.code, 400)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_bad_json_400(self):
        before = self.snap()
        for raw in ("{not json", "[]", "5", '"x"', "", "null"):
            r = self.post(raw, raw=True)
            self.assertEqual(r.code, 400, raw)
            self.assertEqual(self.body(r), {"error": "bad_request"})
        r = self.post_json({"params": [1, 2], "source": "binance"})
        self.assertEqual(r.code, 400)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_save_requires_session_401(self):
        before = self.snap()
        h = {"Content-Type": "application/json", "Origin": DEFAULT_ORIGIN}
        r = self.fetch(SAVE_URL, method="POST", headers=h,
                       body=json.dumps({"params": VALID, "source": "binance"}))
        self.assertEqual(r.code, 401)
        r = self.fetch(CURRENT_URL, headers={})
        self.assertEqual(r.code, 401)
        self.assertEqual(self.snap(), before)

    def test_save_not_allowed_403(self):
        before = self.snap()
        r = self.post(VALID, user="bob")
        self.assertEqual(r.code, 403)
        r = self.fetch(CURRENT_URL, headers=self.cookie(user="bob"))
        self.assertEqual(r.code, 403)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.hist_rows(), [])

    def test_two_saves_two_history_rows(self):
        a = self.body(self.post(VALID))
        b = self.body(self.post(dict(VALID, tp=2.0)))
        self.assertLess(a["history_id"], b["history_id"])
        self.assertEqual(len(self.hist_rows()), 2)


class TestCurrent(WriteBase):
    def get(self):
        r = self.fetch(CURRENT_URL, headers=self.cookie())
        return r.code, json.loads(r.body.decode())

    def test_params_current(self):
        # 정상
        self.pb.write_text('{"ticker": "KRW-ZRO", "tp": 1.0}\n', encoding="utf-8")
        code, b = self.get()
        self.assertEqual(code, 200)
        self.assertTrue(b["exists"])
        self.assertFalse(b["broken"])
        self.assertEqual(b["params"], {"ticker": "KRW-ZRO", "tp": 1.0})
        self.assertRegex(b["mtime"], r"\+09:00$")
        # 깨짐: JSON 아님 / dict 아님 / 빈 파일
        for content in ("{oops", "[1,2]", ""):
            self.pb.write_text(content, encoding="utf-8")
            code, b = self.get()
            self.assertEqual(code, 200)
            self.assertTrue(b["exists"])
            self.assertTrue(b["broken"])
            self.assertIsNone(b["params"])
        # 없음
        self.pb.unlink()
        code, b = self.get()
        self.assertEqual(code, 200)
        self.assertFalse(b["exists"])
        self.assertIsNone(b["params"])
        self.assertIsNone(b["mtime"])
        self.assertFalse(b["broken"])
        self.assertFalse(self.pb.exists())

    def test_current_after_save_roundtrip(self):
        self.assertEqual(self.post(VALID).code, 200)
        code, b = self.get()
        self.assertEqual(b["params"]["ticker"], "KRW-ZRO")
        self.assertEqual(list(b["params"].keys()), FILE_KEYS)


class TestSchema(unittest.TestCase):
    def test_param_fields_match_original_html(self):
        html = ORIG_HTML.read_text(encoding="utf-8")
        found = {}
        for m in re.finditer(r"<select\b([^>]*)>(.*?)</select>", html, re.S):
            idm = re.search(r'\bid="([^"]+)"', m.group(1))
            if idm:
                found[idm.group(1)] = (
                    "select",
                    re.findall(r'<option\b[^>]*\bvalue="([^"]*)"', m.group(2)))
        for m in re.finditer(r"<input\b([^>]*)>", html):
            idm = re.search(r'\bid="([^"]+)"', m.group(1))
            if not idm:
                continue
            attrs = {k: v for k, v in re.findall(r'\b(min|max|step|type)="([^"]*)"', m.group(1))}
            found[idm.group(1)] = ("input", attrs)
        self.assertEqual(len(params_schema.PARAM_FIELDS), 19)
        for name, spec in params_schema.PARAM_FIELDS.items():
            self.assertIn(name, found, name)
            kind, info = found[name]
            if spec["type"] == "select":
                self.assertEqual(kind, "select", name)
                self.assertEqual(spec["options"], info, name)
            elif spec["type"] == "number":
                self.assertEqual(kind, "input", name)
                self.assertEqual(info.get("type"), "number", name)
                for k in ("min", "max", "step"):
                    if k in spec:
                        self.assertIn(k, info, (name, k))
                        self.assertEqual(float(info[k]), float(spec[k]), (name, k))
                    else:
                        self.assertNotIn(k, info, (name, k))
            else:
                self.assertEqual(kind, "input", name)
                self.assertNotIn("type", info)
                self.assertEqual(name, "symbol")
        expect_int = [n for n, s in params_schema.PARAM_FIELDS.items()
                      if s["type"] == "number" and "step" not in s]
        self.assertEqual(sorted(expect_int), sorted(params_schema.INTEGER_FIELDS))

    def test_validate_params_basics(self):
        out = params_schema.validate_params(dict(reversed(list(VALID.items()))))
        self.assertEqual(list(out.keys()), list(params_schema.PARAM_FIELDS.keys()))
        self.assertEqual(out["symbol"], "JTOUSDT")
        with self.assertRaises(ValueError) as cm:
            params_schema.validate_params([])
        self.assertEqual(str(cm.exception), "keys")

    def test_api_write_imports(self):
        allowed_v2 = {"v2.handlers", "v2.db", "v2.params_schema", "v2"}
        std = sys.stdlib_module_names
        for name in ("api_write.py", "params_schema.py"):
            tree = ast.parse((ROOT / "v2" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                    if node.module == "v2":
                        for a in node.names:
                            self.assertIn(a.name, {"db", "params_schema"}, name)
                for mod in mods:
                    top = mod.split(".")[0]
                    self.assertTrue(top in std or mod in allowed_v2, (name, mod))
            src = (ROOT / "v2" / name).read_text(encoding="utf-8")
            self.assertNotIn("v2.server", src)
            self.assertNotIn("open_live_ro", src)


if __name__ == "__main__":
    unittest.main()
