"""v2 기본 기능 블록 서버 시험: GET /v2/api/basic, POST /v2/api/pause, POST /v2/api/logout,
set_paused 쓰기 범위 lint, 구버전(services/db.py) 계산과의 비교. 임시 폴더만 사용한다.

구버전 비교 시험만 services 를 import 한다(시험 코드에서만 허용 — v2 코드는 services 를 import 하지 않는다).
"""
import ast
import json
import re
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from v2 import api_read, db, status
from v2.server import DEFAULT_ORIGIN
from tests.v2 import test_api_read as base

ROOT = Path(__file__).resolve().parents[2]
V2_DIR = ROOT / "v2"
T = "KRW-ZRO"
ISO_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+09:00$")


def iso(minutes_ago: int) -> str:
    return (datetime.now(db.KST) - timedelta(minutes=minutes_ago)).replace(microsecond=0).isoformat()


class BasicBase(base.ApiBase):
    def setUp(self):
        super().setUp()
        self.make_live_db()
        self.set_strategy("EMA", T, "minute3")
        (self.root / "pages").mkdir()
        (self.root / "pages" / "dashboard.py").write_text('v = "v1.2026.10.25.1729"\n', encoding="utf-8")

    # ---- 픽스처 도우미 ----
    def order(self, side, price, state="completed", ticker=T, minutes_ago=10, avg=None,
              vol=1.0, user=None):
        ts = iso(minutes_ago)
        self.conn.execute(
            "INSERT INTO orders(user_id, timestamp, ticker, side, price, volume, status, state, "
            "avg_price, executed_volume, executed_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user or self.USER, ts, ticker, side, price, vol, state, state, avg, vol, ts, ts))
        self.conn.commit()

    def hts_sell(self, minutes_ago):
        self.conn.execute("INSERT INTO audit_trades(timestamp, ticker, type, price) VALUES (?,?,?,?)",
                          (iso(minutes_ago), T, "HTS_SELL", 1.0))
        self.conn.commit()

    def position(self, coin, locked=0.0):
        self.conn.execute("INSERT OR REPLACE INTO account_positions(user_id, ticker, virtual_coin, "
                          "virtual_coin_locked, entry_price, updated_at) VALUES (?,?,?,?,?,?)",
                          (self.USER, T, coin, locked, 0, iso(0)))
        self.conn.commit()

    def price(self, p, minutes_ago=1):
        self.ins_eval("audit_buy_eval", T, iso(minutes_ago), p)

    def basic(self):
        code, body = self.get_json("/v2/api/basic")
        self.assertEqual(code, 200)
        return body

    def post(self, path, body, origin=DEFAULT_ORIGIN, cookie=True, raw=None):
        h = dict(self.cookie()) if cookie else {}
        h["Content-Type"] = "application/json"
        if origin is not None:
            h["Origin"] = origin
        data = raw if raw is not None else json.dumps(body)
        return self.fetch(path, method="POST", body=data, headers=h)

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class TestBasicCalc(BasicBase):
    def test_shape(self):
        b = self.basic()
        self.assertEqual(set(b), {"version", "account", "display_name", "last_status_log",
                                  "engine_running", "pnl_kind", "pnl_pct"})
        self.assertEqual(b["version"], "v1.2026.10.25.1729")
        self.assertEqual(b["account"], "alice")
        self.assertEqual(b["display_name"], "alice")   # users 행이 없으면 user_id
        self.assertEqual(b["pnl_kind"], "realized")
        self.assertIsNone(b["pnl_pct"])

    def test_display_name_from_users(self):
        self.conn.execute("INSERT INTO users(username, display_name) VALUES (?,?)",
                          (self.USER, "Dev User"))
        self.conn.commit()
        self.assertEqual(self.basic()["display_name"], "Dev User")

    def test_display_name_blank_falls_back_to_user_id(self):
        self.conn.execute("INSERT INTO users(username, display_name) VALUES (?,?)",
                          (self.USER, "  "))
        self.conn.commit()
        self.assertEqual(self.basic()["display_name"], self.USER)

    def test_unrealized_open_position(self):
        self.position(10.0)
        self.order("BUY", 100.0, avg=100.0)
        self.price(110.0)
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "unrealized")
        self.assertAlmostEqual(b["pnl_pct"], 10.0)

    def test_unrealized_uses_avg_price_over_price(self):
        self.position(10.0)
        self.order("BUY", 100.0, avg=50.0)
        self.price(110.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], 120.0)

    def test_unrealized_canceled_with_executed_volume_counts(self):
        self.position(10.0)
        self.order("BUY", 100.0, state="CANCELED", vol=3.0)
        self.price(90.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], -10.0)

    def test_unrealized_closed_by_later_sell_is_none(self):
        self.position(10.0)
        self.order("BUY", 100.0, minutes_ago=20)
        self.order("SELL", 105.0, minutes_ago=10)
        self.price(110.0)
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "unrealized")
        self.assertIsNone(b["pnl_pct"])

    def test_unrealized_after_sell_new_buy_is_open(self):
        self.position(10.0)
        self.order("BUY", 100.0, minutes_ago=30)
        self.order("SELL", 105.0, minutes_ago=20)
        self.order("BUY", 200.0, minutes_ago=10)
        self.price(210.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], 5.0)

    def test_unrealized_closed_by_hts_sell_is_none(self):
        self.position(10.0)
        self.order("BUY", 100.0, minutes_ago=20)
        self.hts_sell(10)
        self.price(110.0)
        self.assertIsNone(self.basic()["pnl_pct"])

    def test_unrealized_hts_sell_before_buy_is_open(self):
        self.position(10.0)
        self.hts_sell(30)
        self.order("BUY", 100.0, minutes_ago=20)
        self.price(110.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], 10.0)

    def test_unrealized_no_filled_buy_falls_back_to_any_state(self):
        # 체결 조건 결과 없음 → 상태 조건 없이 재조회(구버전 2단계)
        self.position(10.0)
        self.order("BUY", 100.0, state="open", vol=0.0)
        self.price(110.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], 10.0)

    def test_unrealized_fallback_then_hts_sell_is_none(self):
        self.position(10.0)
        self.order("BUY", 100.0, state="open", vol=0.0, minutes_ago=20)
        self.hts_sell(10)
        self.price(110.0)
        self.assertIsNone(self.basic()["pnl_pct"])

    def test_unrealized_fallback_then_later_filled_sell_is_none(self):
        # MAX 비교는 체결 상태 BUY·SELL 만 센다: 체결 BUY 가 없으면 청산으로 보지 않는다(구버전과 같음)
        self.position(10.0)
        self.order("BUY", 100.0, state="open", vol=0.0, minutes_ago=20)
        self.order("SELL", 105.0, minutes_ago=10)
        self.price(110.0)
        self.assertAlmostEqual(self.basic()["pnl_pct"], 10.0)

    def test_unrealized_no_orders_or_no_price_is_none(self):
        self.position(10.0)
        self.price(110.0)
        self.assertIsNone(self.basic()["pnl_pct"])
        self.order("BUY", 100.0)
        self.conn.execute("DELETE FROM audit_buy_eval")
        self.conn.commit()
        self.assertIsNone(self.basic()["pnl_pct"])

    def test_realized_uses_price_column(self):
        self.order("BUY", 100.0, avg=50.0, minutes_ago=30)
        self.order("SELL", 110.0, avg=999.0, minutes_ago=20)
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "realized")
        self.assertAlmostEqual(b["pnl_pct"], 10.0)

    def test_realized_uses_latest_sell_and_nearest_older_buy(self):
        self.order("BUY", 50.0, minutes_ago=60)
        self.order("SELL", 60.0, minutes_ago=50)
        self.order("BUY", 100.0, minutes_ago=40)
        self.order("BUY", 200.0, minutes_ago=30)
        self.order("SELL", 190.0, minutes_ago=20)
        self.assertAlmostEqual(self.basic()["pnl_pct"], -5.0)

    def test_realized_outside_recent_50_is_na(self):
        self.order("SELL", 110.0, minutes_ago=500)
        self.order("BUY", 100.0, minutes_ago=600)
        for i in range(50):
            self.order("BUY", 1.0, ticker="KRW-OTHER", minutes_ago=400 - i)
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "realized")
        self.assertIsNone(b["pnl_pct"])

    def test_realized_sell_without_older_buy_is_none(self):
        self.order("SELL", 110.0)
        self.assertIsNone(self.basic()["pnl_pct"])

    def test_realized_when_only_locked_coin(self):
        # 가용 0 + 묶임 > 0 → 구버전과 같이 실현 칸(qty > 0 만 미실현)
        self.position(0.0, locked=5.0)
        self.order("BUY", 100.0, minutes_ago=30)
        self.order("SELL", 90.0, minutes_ago=20)
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "realized")
        self.assertAlmostEqual(b["pnl_pct"], -10.0)

    def test_other_users_orders_ignored(self):
        self.order("BUY", 100.0, minutes_ago=30, user="bob")
        self.order("SELL", 200.0, minutes_ago=20, user="bob")
        self.assertIsNone(self.basic()["pnl_pct"])

    def test_no_ticker_means_no_pnl(self):
        (self.root / "alice_active_strategy.txt").unlink()
        b = self.basic()
        self.assertEqual(b["pnl_kind"], "realized")
        self.assertIsNone(b["pnl_pct"])


class TestStatusLog(BasicBase):
    def log(self, level, message, ts, user=None):
        self.conn.execute("INSERT INTO logs(user_id, timestamp, level, message) VALUES (?,?,?,?)",
                          (user or self.USER, ts, level, message))
        self.conn.commit()

    def test_none(self):
        self.assertEqual(self.basic()["last_status_log"], "❌ 상태 로그 없음")

    def test_latest_status_prefix_only(self):
        self.log("INFO", "✅ 엔진 시작", "2026-10-25T10:00:00+09:00")
        self.log("INFO", "🚀 새 시작", "2026-10-25T11:00:00+09:00")
        self.log("INFO", "접두 없는 로그", "2026-10-25T12:00:00+09:00")
        self.log("ERROR", "❌ 오류 레벨은 제외", "2026-10-25T13:00:00+09:00")
        self.log("INFO", "⚠️ 경고 접두", "2026-10-25T10:30:00+09:00", user="bob")
        self.assertEqual(self.basic()["last_status_log"], "[2026-10-25 11:00:00] 🚀 새 시작")

    def test_all_nine_prefixes_match_legacy(self):
        for i, p in enumerate(("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄", "❌", "🚨")):
            self.conn.execute("DELETE FROM logs")
            self.conn.commit()
            self.log("INFO", p + " 메시지", "2026-10-25T10:0%d:00+09:00" % i)
            self.assertIn(p + " 메시지", self.basic()["last_status_log"], p)

    def test_buy_sell_levels_included(self):
        self.log("BUY", "✅ 매수", "2026-10-25T10:00:00+09:00")
        self.assertIn("✅ 매수", self.basic()["last_status_log"])

    def test_iso_timestamp_formatted_like_legacy(self):
        self.log("INFO", "✅ 시각", "2026-10-25T10:00:05.123456+09:00")
        self.assertEqual(self.basic()["last_status_log"], "[2026-10-25 10:00:05] ✅ 시각")


class TestEngineAlive(BasicBase):
    def write_alive(self, **kw):
        body = {"pid": 1, "at": datetime.now(db.KST).isoformat(), "running": {"alice": True}}
        body.update(kw)
        (self.data / ".engine_alive.json").write_text(json.dumps(body), encoding="utf-8")

    def test_missing_file_is_stopped(self):
        self.assertFalse(self.basic()["engine_running"])

    def test_fresh_and_running_is_running(self):
        self.write_alive()
        self.assertTrue(self.basic()["engine_running"])

    def test_stale_is_stopped(self):
        self.write_alive(at=(datetime.now(db.KST) - timedelta(seconds=20)).isoformat())
        self.assertFalse(self.basic()["engine_running"])

    def test_false_or_missing_key_is_stopped(self):
        self.write_alive(running={"alice": False})
        self.assertFalse(self.basic()["engine_running"])
        self.write_alive(running={"bob": True})
        self.assertFalse(self.basic()["engine_running"])

    def test_broken_json_is_stopped(self):
        (self.data / ".engine_alive.json").write_text("{broken", encoding="utf-8")
        self.assertFalse(self.basic()["engine_running"])
        (self.data / ".engine_alive.json").write_text("[]", encoding="utf-8")
        self.assertFalse(self.basic()["engine_running"])


class TestEngineAliveRule(unittest.TestCase):
    NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=db.KST)

    def data(self, sec_ago, running=True, user="u"):
        return {"at": (self.NOW - timedelta(seconds=sec_ago)).isoformat(), "running": {user: running}}

    def test_boundary_15_seconds(self):
        self.assertTrue(status.engine_alive_running(self.data(15), "u", self.NOW))
        self.assertFalse(status.engine_alive_running(self.data(15.5), "u", self.NOW))
        self.assertTrue(status.engine_alive_running(self.data(0), "u", self.NOW))

    def test_not_true_values(self):
        for v in (False, None, 1, "true", 0):
            self.assertFalse(status.engine_alive_running(self.data(1, running=v), "u", self.NOW), v)

    def test_bad_shapes(self):
        for d in (None, [], "x", {}, {"at": "x", "running": {"u": True}},
                  {"at": self.NOW.isoformat(), "running": []},
                  {"at": 123, "running": {"u": True}},
                  {"at": "2026-10-25T12:00:00", "running": {"u": True}}):   # tz 없음
            self.assertFalse(status.engine_alive_running(d, "u", self.NOW), d)


class TestWriteAuth(BasicBase):
    def test_pause_without_session_401(self):
        r = self.post("/v2/api/pause", {"paused": True}, cookie=False)
        self.assertEqual(r.code, 401)

    def test_pause_not_allowlisted_403(self):
        self.allow.write_text("bob\n", encoding="utf-8")
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 403)

    def test_pause_origin_missing_or_other_403(self):
        for origin in (None, "https://evil.example.com", "http://orionhunter7.cafe24.com"):
            r = self.post("/v2/api/pause", {"paused": True}, origin=origin)
            self.assertEqual(r.code, 403, origin)
        self.assertEqual(self.count("logs"), 0)

    def test_logout_origin_and_session(self):
        self.assertEqual(self.post("/v2/api/logout", {}, origin=None).code, 403)
        self.assertEqual(self.post("/v2/api/logout", {}, origin="https://evil.example.com").code, 403)
        self.assertEqual(self.post("/v2/api/logout", {}, cookie=False).code, 401)
        self.allow.write_text("bob\n", encoding="utf-8")
        self.assertEqual(self.post("/v2/api/logout", {}).code, 403)

    def test_get_on_write_routes_not_allowed(self):
        for p in ("/v2/api/pause", "/v2/api/logout"):
            self.assertEqual(self.fetch(p, headers=self.cookie()).code, 405, p)


class TestPause(BasicBase):
    def setUp(self):
        super().setUp()
        self.conn.execute("INSERT INTO users(username, display_name, virtual_krw, trading_paused) "
                          "VALUES ('alice','Alice',777,0)")
        self.conn.commit()

    def paused_value(self):
        row = self.conn.execute("SELECT trading_paused FROM users WHERE username='alice'").fetchone()
        return None if row is None else row[0]

    def table_counts(self):
        names = [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {n: self.count(n) for n in names}

    def test_bad_bodies_400(self):
        for body in ({"paused": "true"}, {"paused": 1}, {"paused": None}, {}, [], "x", {"paused": [True]}):
            r = self.post("/v2/api/pause", body)
            self.assertEqual(r.code, 400, body)
        for raw in ("", "not json", "{" * 5000):
            r = self.post("/v2/api/pause", None, raw=raw)
            self.assertEqual(r.code, 400, raw[:10])
        self.assertEqual(self.paused_value(), 0)
        self.assertEqual(self.count("logs"), 0)

    def test_pause_then_resume_changes_one_cell_and_one_log(self):
        before = self.table_counts()
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body), {"ok": True, "paused": True})
        self.assertEqual(self.paused_value(), 1)
        after = self.table_counts()
        for t, n in before.items():
            self.assertEqual(after[t], n + (1 if t == "logs" else 0), t)
        row = self.conn.execute("SELECT user_id, timestamp, level, message FROM logs").fetchone()
        self.assertEqual(row[0], "alice")
        self.assertRegex(row[1], ISO_RE)
        self.assertIn("T", row[1])
        self.assertTrue(row[1].endswith("+09:00"))
        self.assertEqual(row[2], "INFO")
        self.assertEqual(row[3], "⏸️ 매매 일시중지 (사용자 요청)")
        # 다른 열은 그대로
        u = self.conn.execute("SELECT display_name, virtual_krw FROM users WHERE username='alice'").fetchone()
        self.assertEqual(tuple(u), ("Alice", 777))

        r = self.post("/v2/api/pause", {"paused": False})
        self.assertEqual(r.code, 200)
        self.assertEqual(self.paused_value(), 0)
        msgs = [m[0] for m in self.conn.execute("SELECT message FROM logs ORDER BY id")]
        self.assertEqual(msgs[-1], "▶️ 매매 재개 (사용자 요청)")
        self.assertEqual(len(msgs), 2)

    def test_status_reflects_pause(self):
        self.post("/v2/api/pause", {"paused": True})
        code, body = self.get_json("/v2/api/status")
        self.assertTrue(body["paused"])

    def test_upsert_creates_user_row_when_missing(self):
        self.conn.execute("DELETE FROM users")
        self.conn.commit()
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 200)
        self.assertEqual(self.paused_value(), 1)
        self.assertEqual(self.count("users"), 1)

    def test_locked_database_503_and_nothing_written(self):
        other = sqlite3.connect(self.data / "tradebot_alice.db", isolation_level=None)
        self.addCleanup(other.close)
        other.execute("BEGIN IMMEDIATE")
        with mock.patch.object(db, "BUSY_TIMEOUT_MS", 100):
            r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 503)
        self.assertEqual(json.loads(r.body), {"error": "db_unavailable"})
        other.execute("ROLLBACK")
        self.assertEqual(self.paused_value(), 0)
        self.assertEqual(self.count("logs"), 0)
        # 잠금이 풀리면 다시 동작
        self.assertEqual(self.post("/v2/api/pause", {"paused": True}).code, 200)

    def test_failure_in_second_statement_rolls_back_first(self):
        self.conn.execute("CREATE TRIGGER no_log BEFORE INSERT ON logs "
                          "BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        self.conn.commit()
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 503)
        self.assertEqual(self.paused_value(), 0)   # users 쓰기도 되돌려졌다

    def test_no_live_db_404_and_no_file_created(self):
        for p in self.data.glob("tradebot_*.db"):
            p.unlink()
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertEqual(r.code, 404)
        self.assertEqual(list(self.data.glob("tradebot_*.db")), [])

    def test_error_body_has_no_internal_detail(self):
        for p in self.data.glob("tradebot_*.db"):
            p.unlink()
        r = self.post("/v2/api/pause", {"paused": True})
        self.assertNotIn(str(self.data), r.body.decode())


class TestLogout(BasicBase):
    def test_clears_cookie_and_redirect(self):
        r = self.post("/v2/api/logout", {})
        self.assertEqual(r.code, 200)
        self.assertEqual(json.loads(r.body), {"ok": True, "redirect": "/"})
        sc = r.headers.get_list("Set-Cookie")
        self.assertEqual(len(sc), 1)
        self.assertRegex(sc[0], r'^v2s=(""|);')
        self.assertIn("Path=/v2/", sc[0])
        self.assertRegex(sc[0], r"(?i)expires=")
        # 쿠키가 지워진 브라우저에서는 API 가 401
        self.assertEqual(self.fetch("/v2/api/status").code, 401)
        self.assertEqual(self.fetch("/v2/api/basic").code, 401)


class TestWriteLint(unittest.TestCase):
    """실매매 DB 쓰기는 v2.db.set_paused 안의 두 문장(users·logs)뿐임을 소스로 고정한다."""

    WRITE_RE = re.compile(
        r"^\s*(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE\s|DELETE\s+FROM|REPLACE\s+INTO|CREATE\s|DROP\s|ALTER\s)", re.I)

    def _string_consts(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node.value

    def test_only_expected_write_statements_exist(self):
        found = []
        for p in sorted(V2_DIR.glob("*.py")):
            for s in self._string_consts(p):
                if self.WRITE_RE.match(s):
                    found.append((p.name, " ".join(s.split())[:60]))
        names = sorted(f"{n}:{s.split('(')[0].split(' VALUES')[0].strip()}" for n, s in found)
        self.assertEqual(names, sorted([
            "db.py:CREATE TABLE IF NOT EXISTS v2_settings_history",   # 신버전 전용 이력 DB
            "db.py:INSERT INTO v2_settings_history",
            # 2차 T13: 「이 설정으로 동작」 적용 시각 — 신버전 전용 이력 DB 의 applied_at 한 칸(실매매 DB 아님)
            "db.py:UPDATE v2_settings_history SET applied_at=? WHERE id=? AND u",
            "db.py:INSERT INTO users",
            "db.py:INSERT INTO logs",
        ]), found)

    def test_live_write_statements_touch_only_users_and_logs(self):
        self.assertRegex(db.WRITE_SQL_PAUSED, r"^INSERT INTO users \(username, trading_paused\) ")
        self.assertRegex(db.WRITE_SQL_LOG, r"^INSERT INTO logs \(user_id, timestamp, level, message\) ")
        for sql in (db.WRITE_SQL_PAUSED, db.WRITE_SQL_LOG):
            self.assertEqual(len(re.findall(r"(?i)\b(insert|update|delete)\b", sql)),
                             2 if sql is db.WRITE_SQL_PAUSED else 1)

    def test_write_sql_executed_only_inside_set_paused_and_hist_funcs(self):
        users = []
        for p in sorted(V2_DIR.glob("*.py")):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                src = ast.get_source_segment(p.read_text(encoding="utf-8"), fn)
                if "WRITE_SQL_" in src:
                    users.append((p.name, fn.name))
        self.assertEqual(users, [("db.py", "set_paused")])

    def test_rw_connections_only_in_set_paused_and_open_v2hist(self):
        src_all = {}
        for p in sorted(V2_DIR.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                seg = ast.get_source_segment(text, fn)
                if "sqlite3.connect(" in seg:
                    src_all[(p.name, fn.name)] = seg
        self.assertEqual(sorted(src_all), [("db.py", "open_live_ro"), ("db.py", "open_v2hist"),
                                           ("db.py", "set_paused")])
        self.assertIn('"ro"', src_all[("db.py", "open_live_ro")])
        hist = src_all[("db.py", "open_v2hist")]
        self.assertIn("v2hist_path", hist)
        self.assertNotIn("live_db_path(user_id)", hist.split("p = v2hist_path")[1].split("conn = ")[1])
        paused = src_all[("db.py", "set_paused")]
        self.assertIn("live_db_path(user_id)", paused)
        self.assertIn('"rw"', paused)
        self.assertIn("BEGIN IMMEDIATE", paused)
        self.assertIn("ROLLBACK", paused)
        self.assertEqual(paused.count("conn.execute(WRITE_SQL_"), 2)
        # api_write·api_read 는 sqlite 연결을 직접 열지 않는다
        for name in ("api_read.py", "api_write.py", "handlers.py", "server.py", "status.py", "auth.py"):
            self.assertNotIn("sqlite3.connect", (V2_DIR / name).read_text(encoding="utf-8"), name)

    def test_set_paused_called_only_from_pause_handler(self):
        callers = []
        for p in sorted(V2_DIR.glob("*.py")):
            if "set_paused(" in p.read_text(encoding="utf-8") and p.name != "db.py":
                callers.append(p.name)
        self.assertEqual(callers, ["api_write.py"])

    def test_v2_code_has_no_upbit_or_engine_imports(self):
        bad = ("pyupbit", "api.upbit.com", "urllib.request", "http.client",
               "httpx", "aiohttp", "streamlit")
        imp = re.compile(r"^\s*(from|import)\s+(requests|services|engine|core)\b", re.M)
        for p in sorted(V2_DIR.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for b in bad:
                # 결정 1026-23 2 가(D8 변경): 업비트 공개 시세 주소는 candles.py 한 곳만 허용
                if b == "api.upbit.com" and p.name == "candles.py":
                    continue
                self.assertNotIn(b, text, f"{p.name}: {b}")
            self.assertIsNone(imp.search(text), p.name)
        cand = (V2_DIR / "candles.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"https://[^\s\"']+", cand),
                         ["https://api.upbit.com/v1/candles/minutes/{unit}"])
        for b in ("Authorization", "/v1/accounts", "/v1/orders", "access_key"):
            self.assertNotIn(b, cand)
        self.assertNotIn("jwt", cand.lower())


class TestLegacyParity(BasicBase):
    """같은 고정 DB 에서 구버전 services/db.py 함수와 신버전 계산이 같은지 비교한다."""

    def setUp(self):
        super().setUp()
        from services import db as legacy
        self.legacy = legacy
        path = str(self.data / "tradebot_alice.db")
        patcher = mock.patch.object(legacy, "get_db_path", lambda user_id: path)
        patcher.start()
        self.addCleanup(patcher.stop)

    # 구버전 dashboard.py 888-907 의 순회를 fetch_recent_orders 위에서 그대로 옮긴 것
    def legacy_realized(self, ticker):
        recent = self.legacy.fetch_recent_orders(self.USER, limit=50)
        for i, order in enumerate(recent):
            _ts, tk, side, price, *_ = order
            if tk != ticker or side != "SELL":
                continue
            sell = float(price)
            for j in range(i + 1, len(recent)):
                _, tk2, side2, price2, *_ = recent[j]
                if tk2 == ticker and side2 == "BUY":
                    buy = float(price2)
                    return (sell - buy) / buy * 100.0
            break
        return None

    def legacy_entry(self, ticker):
        r = self.legacy.get_last_open_buy_order(ticker, self.USER)
        return None if not r else r.get("price")

    def check(self):
        a = api_read.entry_price_open(self.USER, T)
        b = self.legacy_entry(T)
        if b is None:
            self.assertIsNone(a)
        else:
            self.assertAlmostEqual(a, b)
        ra = api_read.realized_pct(self.USER, T)
        rb = self.legacy_realized(T)
        if rb is None:
            self.assertIsNone(ra)
        else:
            self.assertAlmostEqual(ra, rb)

    def test_scenarios(self):
        scenarios = {
            "empty": [],
            "open_buy": [("BUY", 100.0, "completed", 30, None)],
            "closed": [("BUY", 100.0, "completed", 30, None), ("SELL", 110.0, "completed", 20, None)],
            "reopened": [("BUY", 100.0, "completed", 30, None), ("SELL", 110.0, "completed", 20, None),
                         ("BUY", 120.0, "completed", 10, 119.0)],
            "canceled_exec": [("BUY", 100.0, "CANCELED", 30, None)],
            "fallback_open_state": [("BUY", 100.0, "open", 30, None)],
            "fallback_with_sell": [("BUY", 100.0, "open", 30, None), ("SELL", 105.0, "completed", 20, None)],
            "unfilled_sell_after": [("BUY", 100.0, "completed", 30, None), ("SELL", 105.0, "canceled", 20, None)],
            "avg_price": [("BUY", 100.0, "FILLED", 30, 98.5)],
            "two_buys": [("BUY", 100.0, "completed", 30, None), ("BUY", 130.0, "completed", 20, None)],
            "sell_only": [("SELL", 100.0, "completed", 30, None)],
        }
        for name, rows in scenarios.items():
            with self.subTest(name):
                self.conn.execute("DELETE FROM orders")
                self.conn.execute("DELETE FROM audit_trades")
                self.conn.commit()
                for side, price, state, ago, avg in rows:
                    self.order(side, price, state=state, minutes_ago=ago, avg=avg)
                self.check()

    def test_hts_sell_scenarios(self):
        for name, ago in (("after", 10), ("before", 40)):
            with self.subTest(name):
                self.conn.execute("DELETE FROM orders")
                self.conn.execute("DELETE FROM audit_trades")
                self.conn.commit()
                self.order("BUY", 100.0, minutes_ago=30)
                self.hts_sell(ago)
                self.check()

    def test_hts_sell_with_fallback_buy(self):
        self.order("BUY", 100.0, state="open", vol=0.0, minutes_ago=30)
        self.hts_sell(10)
        self.check()

    def test_realized_window_50(self):
        self.order("BUY", 100.0, minutes_ago=900)
        self.order("SELL", 120.0, minutes_ago=800)
        for i in range(49):
            self.order("BUY", 1.0, ticker="KRW-OTHER", minutes_ago=700 - i)
        self.check()    # 50건 안: 계산됨
        self.order("BUY", 1.0, ticker="KRW-OTHER", minutes_ago=100)
        self.check()    # 50건 밖: 둘 다 없음
        self.assertIsNone(api_read.realized_pct(self.USER, T))

    def test_status_log_text_same_as_legacy(self):
        self.conn.execute("INSERT INTO logs(user_id, timestamp, level, message) VALUES (?,?,?,?)",
                          (self.USER, "2026-10-25T10:00:05+09:00", "INFO", "🔌 연결"))
        self.conn.commit()
        self.assertEqual(self.basic()["last_status_log"],
                         self.legacy.get_last_status_log_from_db(self.USER))
        self.conn.execute("DELETE FROM logs")
        self.conn.commit()
        self.assertEqual(self.basic()["last_status_log"],
                         self.legacy.get_last_status_log_from_db(self.USER))


if __name__ == "__main__":
    unittest.main()
