import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tornado.testing import AsyncHTTPTestCase

from utils import v2_entry_token as et
from v2 import api_read, auth, db
from v2.server import make_app

ROOT = Path(__file__).resolve().parents[2]
INIT_DB = ROOT / "services" / "init_db.py"

# services/init_db.py 원문(주석 제거)을 옮긴 픽스처. 엔진 모듈은 import 하지 않는다.
# test_fixture_ddl_matches_init_db 가 init_db.py 를 텍스트로 읽어 대조한다.
CREATE_STATEMENTS = [
    """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            display_name TEXT,
            virtual_krw INTEGER,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            level TEXT,
            message TEXT
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            virtual_krw INTEGER DEFAULT 1000000,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS account_positions (
            user_id TEXT,
            ticker TEXT,
            virtual_coin REAL DEFAULT 0,
            updated_at TEXT DEFAULT (DATETIME('now', 'localtime')),
            PRIMARY KEY (user_id, ticker)
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS engine_status (
            user_id TEXT PRIMARY KEY,
            is_running INTEGER DEFAULT 0,
            last_heartbeat TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS audit_buy_eval (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            bar_time TEXT,
            ticker TEXT,
            interval_sec INTEGER,
            bar INTEGER,
            price REAL,
            macd REAL,
            signal REAL,
            have_position INTEGER,
            overall_ok INTEGER,
            failed_keys TEXT,
            checks TEXT,
            notes TEXT
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS audit_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (DATETIME('now', 'localtime')),
            bar_time TEXT,
            ticker TEXT,
            interval_sec INTEGER,
            bar INTEGER,
            type TEXT,
            reason TEXT,
            price REAL,
            macd REAL,
            signal REAL,
            entry_price REAL,
            entry_bar INTEGER,
            bars_held INTEGER,
            tp REAL,
            sl REAL,
            highest REAL,
            ts_pct REAL,
            ts_armed INTEGER
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS audit_sell_eval (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT DEFAULT (DATETIME('now', 'localtime')),
            bar_time    TEXT,
            ticker      TEXT,
            interval_sec INTEGER,
            bar         INTEGER,
            price       REAL,
            macd        REAL,
            signal      REAL,
            tp_price    REAL,
            sl_price    REAL,
            highest     REAL,
            ts_pct      REAL,
            ts_armed    INTEGER,
            bars_held   INTEGER,
            checks      TEXT,
            triggered   INTEGER,
            trigger_key TEXT,
            notes       TEXT
        );
    """,
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_logs_user_ts ON logs(user_id, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_buy_eval_ts ON audit_buy_eval(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_buy_eval_ticker_ts ON audit_buy_eval(ticker, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_trades_ts ON audit_trades(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_trades_ticker_ts ON audit_trades(ticker, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_sell_eval_ts ON audit_sell_eval(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_sell_eval_ticker_ts ON audit_sell_eval(ticker, timestamp);",
]

# init_db.py 의 마이그레이션 순서(737,826,842,928,942,955,968,981,996-998).
# 827-828, 843-844 의 인덱스는 해당 ALTER 바로 뒤에 둔다.
ALTER_STATEMENTS = [
    "ALTER TABLE audit_trades ADD COLUMN bar_time TEXT",
    "ALTER TABLE audit_buy_eval ADD COLUMN bar_time TEXT",
    "CREATE INDEX IF NOT EXISTS idx_audit_buy_eval_bar_time ON audit_buy_eval(bar_time)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_buy_eval_unique ON audit_buy_eval(ticker, bar_time)",
    "ALTER TABLE audit_sell_eval ADD COLUMN bar_time TEXT",
    "CREATE INDEX IF NOT EXISTS idx_audit_sell_eval_bar_time ON audit_sell_eval(bar_time)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_sell_eval_unique ON audit_sell_eval(ticker, bar_time)",
    "ALTER TABLE accounts ADD COLUMN virtual_krw_locked INTEGER DEFAULT 0",
    "ALTER TABLE account_positions ADD COLUMN virtual_coin_locked REAL DEFAULT 0",
    "ALTER TABLE account_positions ADD COLUMN entry_price REAL DEFAULT 0",
    "ALTER TABLE engine_status ADD COLUMN last_mode TEXT",
    "ALTER TABLE users ADD COLUMN trading_paused INTEGER DEFAULT 0",
    "ALTER TABLE audit_trades ADD COLUMN qty REAL",
    "ALTER TABLE audit_trades ADD COLUMN note TEXT",
    "ALTER TABLE audit_trades ADD COLUMN meta TEXT",
]


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def create_schema(conn: sqlite3.Connection) -> None:
    for s in CREATE_STATEMENTS:
        conn.execute(s)
    for s in INDEX_STATEMENTS:
        conn.execute(s)
    for s in ALTER_STATEMENTS:
        try:
            conn.execute(s)
        except sqlite3.OperationalError as e:  # init_db._safe_alter 와 같이 중복 열은 무시
            if "duplicate column" not in str(e):
                raise
    conn.commit()


class ApiBase(AsyncHTTPTestCase):
    USER = "alice"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.static = self.dir / "static"
        self.static.mkdir()
        self.root = self.dir / "root"
        self.data = self.root / "services" / "data"
        self.data.mkdir(parents=True)
        self.secret = self.dir / "secret"
        self.allow = self.dir / "allow"
        self.secret.write_bytes(os.urandom(48))
        os.chmod(self.secret, 0o600)
        self.allow.write_text("alice\n", encoding="utf-8")
        self._old_et = (et.SECRET_PATH, et.ALLOWLIST_PATH)
        self._old_db = (db.REPO_ROOT, db.DATA_DIR)
        et.SECRET_PATH = self.secret
        et.ALLOWLIST_PATH = self.allow
        db.REPO_ROOT = self.root
        db.DATA_DIR = self.data
        self.addCleanup(self._restore)
        super().setUp()

    def _restore(self):
        et.SECRET_PATH, et.ALLOWLIST_PATH = self._old_et
        db.REPO_ROOT, db.DATA_DIR = self._old_db

    def get_app(self):
        return make_app(static_dir=self.static)

    # ---- 픽스처 도우미 ----
    def make_live_db(self, user=None):
        user = user or self.USER
        p = self.data / f"tradebot_{user}.db"
        conn = sqlite3.connect(p)
        create_schema(conn)
        conn.commit()
        self.conn = conn
        self.addCleanup(conn.close)
        return conn

    def set_strategy(self, strategy="EMA", ticker="KRW-ZRO", interval="minute3",
                     user=None):
        user = user or self.USER
        (self.root / f"{user}_active_strategy.txt").write_text(strategy + "\n",
                                                               encoding="utf-8")
        (self.root / f"{user}_latest_params_{strategy}.json").write_text(
            json.dumps({"ticker": ticker, "interval": interval}), encoding="utf-8")

    def cookie(self, user="alice", mode="TEST"):
        return {"Cookie": "%s=%s" % (auth.SESSION_COOKIE,
                                     auth.make_session(user, mode))}

    def get_json(self, path, mode="TEST", user="alice"):
        r = self.fetch(path, headers=self.cookie(user, mode))
        return r.code, json.loads(r.body.decode())

    def ins_eval(self, table, ticker, ts, price, **kw):
        cols = {"timestamp": ts, "ticker": ticker, "price": price}
        cols.update(kw)
        names = ",".join(cols)
        qs = ",".join("?" * len(cols))
        self.conn.execute(f"INSERT INTO {table}({names}) VALUES ({qs})",
                          tuple(cols.values()))
        self.conn.commit()


class TestAuthOnRoutes(ApiBase):
    PATHS = ["/v2/api/status", "/v2/api/assets", "/v2/api/trades",
             "/v2/api/signals", "/v2/api/logs", "/v2/api/markers"]

    def test_routes_without_session_401(self):
        for p in self.PATHS:
            r = self.fetch(p)
            self.assertEqual(r.code, 401, p)
            self.assertEqual(r.headers["Cache-Control"], "no-store", p)

    def test_routes_not_allowlisted_403(self):
        h = self.cookie("alice")
        self.allow.write_text("bob\n", encoding="utf-8")
        for p in self.PATHS:
            r = self.fetch(p, headers=h)
            self.assertEqual(r.code, 403, p)

    def test_url_user_id_is_ignored(self):
        # 다른 사용자 이름을 쿼리로 줘도 세션 user_id 만 쓴다(bob DB 가 없어도 alice 로 동작)
        self.make_live_db("alice")
        self.set_strategy()
        code, body = self.get_json("/v2/api/status?user_id=bob")
        self.assertEqual(code, 200)
        self.assertEqual(body["ticker"], "KRW-ZRO")

    def test_no_db_returns_404_json(self):
        code, body = self.get_json("/v2/api/assets")
        self.assertEqual(code, 404)
        self.assertEqual(body["error"], "no_data")


class TestStatus(ApiBase):
    def test_status_shape_and_mode_mismatch(self):
        c = self.make_live_db()
        self.set_strategy()
        c.execute("INSERT INTO engine_status(user_id,is_running,last_mode) "
                  "VALUES ('alice',1,'LIVE')")
        c.execute("INSERT INTO users(username,trading_paused) VALUES ('alice',1)")
        c.commit()
        code, body = self.get_json("/v2/api/status", mode="TEST")
        self.assertEqual(code, 200)
        self.assertEqual(set(body), {"engine", "mode_engine", "mode_entry",
                                     "mode_mismatch", "strategy", "ticker",
                                     "interval", "paused"})
        self.assertEqual(body["mode_engine"], "LIVE")
        self.assertEqual(body["mode_entry"], "TEST")
        self.assertTrue(body["mode_mismatch"])
        self.assertTrue(body["paused"])
        self.assertEqual(body["ticker"], "KRW-ZRO")
        self.assertEqual(body["interval"], "minute3")
        self.assertEqual(body["strategy"]["value"], "EMA")
        self.assertTrue(body["strategy"]["mtime"])
        self.assertEqual(set(body["engine"]), {"level", "ago_sec", "basis"})
        self.assertEqual(body["engine"]["level"], "unknown")  # 판단 기록 없음

    def test_status_mode_engine_none(self):
        self.make_live_db()
        self.set_strategy()
        code, body = self.get_json("/v2/api/status", mode="LIVE")
        self.assertEqual(code, 200)
        self.assertIsNone(body["mode_engine"])
        self.assertFalse(body["mode_mismatch"])
        self.assertFalse(body["paused"])

    def test_status_engine_ok_from_eval(self):
        from datetime import datetime
        c = self.make_live_db()
        self.set_strategy()
        now = datetime.now(db.KST).replace(microsecond=0)
        self.ins_eval("audit_buy_eval", "KRW-ZRO", now.isoformat(), 100.0)
        code, body = self.get_json("/v2/api/status")
        self.assertEqual(body["engine"]["level"], "ok")
        self.assertEqual(body["engine"]["basis"], "eval")

    def test_status_live_secondary_accounts(self):
        from datetime import datetime, timedelta
        c = self.make_live_db()
        self.set_strategy()
        now = datetime.now(db.KST).replace(microsecond=0)
        self.ins_eval("audit_buy_eval", "KRW-ZRO",
                      (now - timedelta(seconds=4000)).isoformat(), 100.0)
        c.execute("INSERT INTO accounts(user_id,virtual_krw,updated_at) "
                  "VALUES ('alice',1000,?)",
                  (now.strftime("%Y-%m-%d %H:%M:%S"),))  # 공백 형식도 KST
        c.commit()
        code, body = self.get_json("/v2/api/status", mode="LIVE")
        self.assertEqual(body["engine"]["level"], "delay")
        self.assertEqual(body["engine"]["basis"], "accounts")
        code, body = self.get_json("/v2/api/status", mode="TEST")
        self.assertEqual(body["engine"]["level"], "unknown")


class TestAssets(ApiBase):
    def _holding(self, c, coin=2.0, entry=100.0, locked=0.5):
        c.execute("INSERT INTO accounts(user_id,virtual_krw,virtual_krw_locked,updated_at) "
                  "VALUES ('alice',50000,1200,'2026-10-23 11:00:00')")
        c.execute("INSERT INTO account_positions(user_id,ticker,virtual_coin,"
                  "virtual_coin_locked,entry_price,updated_at) "
                  "VALUES ('alice','KRW-ZRO',?,?,?,'2026-10-23 11:00:01')",
                  (coin, locked, entry))
        c.commit()

    def test_assets_keys_and_values(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:30:00+09:00",
                      110.0, tp_price=120.0, sl_price=95.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(code, 200)
        self.assertEqual(set(b), {"krw", "krw_locked", "coin", "coin_locked",
                                  "entry_price", "price", "price_at", "pnl",
                                  "tp_price", "sl_price", "round", "updated_at"})
        self.assertEqual(b["krw"], 50000)
        self.assertEqual(b["krw_locked"], 1200)
        self.assertEqual(b["coin"], 2.0)
        self.assertEqual(b["coin_locked"], 0.5)
        self.assertEqual(b["entry_price"], 100.0)
        self.assertAlmostEqual(b["pnl"], 0.10)
        self.assertEqual(b["tp_price"], 120.0)
        self.assertEqual(b["sl_price"], 95.0)

    def test_assets_price_from_latest_eval_for_ticker(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        # 다른 종목이 더 최신이어도 쓰지 않는다
        self.ins_eval("audit_buy_eval", "KRW-ZRO", "2026-10-23T11:00:00+09:00", 101.0)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:10:00+09:00", 103.0)
        self.ins_eval("audit_buy_eval", "KRW-ZRO", "2026-10-23T11:05:00+09:00", 102.0)
        self.ins_eval("audit_buy_eval", "KRW-OTHER", "2026-10-23T12:00:00+09:00", 999.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["price"], 103.0)  # 두 테이블 중 더 최신(sell 11:10)
        self.assertEqual(b["price_at"], "2026-10-23T11:10:00+09:00")
        self.ins_eval("audit_buy_eval", "KRW-ZRO", "2026-10-23T11:20:00+09:00", 104.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["price"], 104.0)

    def test_assets_tp_sl_from_latest_sell_eval(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:00:00+09:00",
                      100.0, tp_price=150.0, sl_price=90.0)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:30:00+09:00",
                      100.0, tp_price=0, sl_price=None)
        code, b = self.get_json("/v2/api/assets")
        self.assertIsNone(b["tp_price"])
        self.assertIsNone(b["sl_price"])

    def test_assets_fully_locked_still_holding(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c, coin=0, entry=100.0, locked=2.0)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:30:00+09:00",
                      110.0, tp_price=120.0, sl_price=95.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["coin"], 0)
        self.assertEqual(b["coin_locked"], 2.0)
        self.assertAlmostEqual(b["pnl"], 0.10)
        self.assertEqual(b["tp_price"], 120.0)
        self.assertEqual(b["sl_price"], 95.0)

    def test_assets_tp_sl_null_when_sell_eval_older_than_latest_buy(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T10:00:00+09:00",
                      110.0, tp_price=120.0, sl_price=95.0)  # 이전 포지션의 행
        c.execute("INSERT INTO audit_trades(timestamp,ticker,type,price) VALUES "
                  "('2026-10-23 10:30:00','KRW-ZRO','BUY',100.0)")
        c.commit()
        code, b = self.get_json("/v2/api/assets")
        self.assertIsNone(b["tp_price"])
        self.assertIsNone(b["sl_price"])
        # 최신 BUY 이후의 행이면 쓴다
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T10:40:00+09:00",
                      110.0, tp_price=121.0, sl_price=96.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["tp_price"], 121.0)
        self.assertEqual(b["sl_price"], 96.0)
        # 다른 종목 BUY 나 SELL 체결은 기준이 아니다
        c.execute("INSERT INTO audit_trades(timestamp,ticker,type,price) VALUES "
                  "('2026-10-23 11:00:00','KRW-OTHER','BUY',1.0)")
        c.execute("INSERT INTO audit_trades(timestamp,ticker,type,price) VALUES "
                  "('2026-10-23 11:00:00','KRW-ZRO','SELL',1.0)")
        c.commit()
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["tp_price"], 121.0)

    def test_assets_round_null_in_phase1(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        code, b = self.get_json("/v2/api/assets")
        self.assertIn("round", b)
        self.assertIsNone(b["round"])

    def test_assets_not_holding(self):
        c = self.make_live_db()
        self.set_strategy()
        c.execute("INSERT INTO accounts(user_id,virtual_krw) VALUES ('alice',777)")
        c.commit()
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-23T11:30:00+09:00",
                      100.0, tp_price=150.0, sl_price=90.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["krw"], 777)
        self.assertEqual(b["coin"], 0)
        self.assertIsNone(b["pnl"])
        self.assertIsNone(b["tp_price"])
        self.assertIsNone(b["sl_price"])
        self.assertEqual(b["price"], 100.0)

    def test_mixed_timestamp_formats(self):
        c = self.make_live_db()
        self.set_strategy()
        self._holding(c)
        self.ins_eval("audit_buy_eval", "KRW-ZRO", "2026-10-23 11:40:00", 105.0)
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(b["price_at"], "2026-10-23T11:40:00+09:00")
        self.assertEqual(b["updated_at"], "2026-10-23T11:00:00+09:00")  # accounts.updated_at
        # 로그·체결 시각도 KST ISO 로 통일
        c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES "
                  "('alice','2026-10-23 10:00:00','INFO','a')")
        c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES "
                  "('alice','2026-10-23T09:00:00+09:00','INFO','b')")
        c.commit()
        code, b = self.get_json("/v2/api/logs")
        stamps = {x["message"]: x["timestamp"] for x in b["logs"]}
        self.assertEqual(stamps["a"], "2026-10-23T10:00:00+09:00")
        self.assertEqual(stamps["b"], "2026-10-23T09:00:00+09:00")
        # 알려진 한계: 같은 날짜 안에서 'T' 형식이 공백 형식보다 문자열상 뒤라 먼저(최신으로) 나온다
        self.assertEqual([x["message"] for x in b["logs"]], ["b", "a"])


class TestListsAndPaging(ApiBase):
    def _trades(self, n, ticker="KRW-ZRO"):
        for i in range(n):
            self.conn.execute(
                "INSERT INTO audit_trades(timestamp,bar_time,ticker,type,reason,price,qty) "
                "VALUES (?,?,?,?,?,?,?)",
                ("2026-10-23 10:%02d:00" % (i % 60), "2026-10-23 10:%02d:00" % (i % 60),
                 ticker, "BUY" if i % 2 == 0 else "SELL", "r%d" % i, 100.0 + i, 1.5))
        self.conn.commit()

    def test_trades_limit_default_and_cap(self):
        self.make_live_db()
        self.set_strategy()
        self._trades(60)
        code, b = self.get_json("/v2/api/trades")
        self.assertEqual(len(b["trades"]), 10)
        code, b = self.get_json("/v2/api/trades?limit=50")
        self.assertEqual(len(b["trades"]), 50)
        code, b = self.get_json("/v2/api/trades?limit=51")
        self.assertEqual(len(b["trades"]), 50)
        code, b = self.get_json("/v2/api/trades?limit=1000000")
        self.assertEqual(len(b["trades"]), 50)
        code, b = self.get_json("/v2/api/trades?limit=1")
        self.assertEqual(len(b["trades"]), 1)
        self.assertEqual(set(b["trades"][0]),
                         {"id", "timestamp", "bar_time", "ticker", "type", "reason",
                          "price", "qty", "entry_price", "note"})

    def test_trades_only_current_ticker(self):
        self.make_live_db()
        self.set_strategy()
        self._trades(3)
        self._trades(4, ticker="KRW-OTHER")
        code, b = self.get_json("/v2/api/trades")
        self.assertEqual(len(b["trades"]), 3)

    SIG_KEYS = {"id", "kind", "timestamp", "bar_time", "ticker", "price", "macd",
                "signal", "have_position", "overall_ok", "failed_keys",
                "triggered", "trigger_key"}

    def _buy(self, ts, price=100.0, ticker="KRW-ZRO", bar=None):
        self.ins_eval("audit_buy_eval", ticker, ts, price, bar_time=bar or ts,
                      have_position=0, overall_ok=1, failed_keys="[]")

    def _sell(self, ts, price=200.0, ticker="KRW-ZRO", bar=None, **kw):
        self.ins_eval("audit_sell_eval", ticker, ts, price, bar_time=bar or ts, **kw)

    def test_signals_default_20(self):
        self.make_live_db()
        self.set_strategy()
        for i in range(30):
            self._buy("2026-10-23 10:%02d:00" % i, 100.0 + i)
        for i in range(3):
            self._sell("2026-10-23 10:%02d:30" % (30 + i), 300.0 + i)
        code, b = self.get_json("/v2/api/signals")
        self.assertEqual(len(b["signals"]), 20)
        self.assertEqual(b["signals"][0]["price"], 302.0)  # 최신 먼저(매도 판단)
        kinds = [s["kind"] for s in b["signals"]]
        self.assertEqual(kinds.count("sell"), 3)
        self.assertEqual(kinds.count("buy"), 17)
        code, b = self.get_json("/v2/api/signals?limit=50")
        self.assertEqual(len(b["signals"]), 33)

    def test_signals_merge_buy_and_sell_by_time(self):
        self.make_live_db()
        self.set_strategy()
        self._buy("2026-10-23 10:00:00", 1.0)
        self._sell("2026-10-23 10:01:00", 2.0)
        self._buy("2026-10-23 10:02:00", 3.0)
        self._sell("2026-10-23 10:03:00", 4.0)
        code, b = self.get_json("/v2/api/signals")
        self.assertEqual([s["price"] for s in b["signals"]], [4.0, 3.0, 2.0, 1.0])
        self.assertEqual([s["kind"] for s in b["signals"]],
                         ["sell", "buy", "sell", "buy"])

    def test_signals_same_time_same_kind_larger_id_first(self):
        self.make_live_db()
        self.set_strategy()
        self._sell("2026-10-23 10:00:00", 1.0, bar="s1")
        self._sell("2026-10-23 10:00:00", 2.0, bar="s2")
        code, b = self.get_json("/v2/api/signals")
        sells = [s for s in b["signals"] if s["kind"] == "sell"]
        self.assertEqual(len(sells), 2)
        self.assertGreater(sells[0]["id"], sells[1]["id"])
        self.assertEqual([s["price"] for s in sells], [2.0, 1.0])

    def test_signals_mixed_timestamp_formats_merge(self):
        self.make_live_db()
        self.set_strategy()
        self._buy("2026-10-23T10:05:00+09:00", 5.0, bar="b1")
        self._sell("2026-10-23 10:04:00", 4.0, bar="b2")
        self._buy("2026-10-23 10:06:00", 6.0, bar="b3")
        self._sell("2026-10-23T10:03:00+09:00", 3.0, bar="b4")
        code, b = self.get_json("/v2/api/signals")
        self.assertEqual([s["price"] for s in b["signals"]], [6.0, 5.0, 4.0, 3.0])
        for s in b["signals"]:
            self.assertTrue(s["timestamp"].endswith("+09:00"), s["timestamp"])

    def test_signals_same_time_sell_first_and_broken_timestamps_last(self):
        self.make_live_db()
        self.set_strategy()
        self._buy("2026-10-23 10:00:00", 1.0)
        self._sell("2026-10-23 10:00:00", 2.0)
        self._buy("garbage", 8.0, bar="g1")
        self._sell("not-a-time", 9.0, bar="g2")
        code, b = self.get_json("/v2/api/signals")
        self.assertEqual(code, 200)
        self.assertEqual([s["price"] for s in b["signals"]], [2.0, 1.0, 9.0, 8.0])

    def test_signals_kind_and_key_set(self):
        self.make_live_db()
        self.set_strategy()
        self._buy("2026-10-23 10:00:00", 1.0)
        self._sell("2026-10-23 10:01:00", 2.0, triggered=1, trigger_key="Stop Loss")
        self._sell("2026-10-23 10:02:00", 3.0, triggered=0)
        code, b = self.get_json("/v2/api/signals")
        sig = b["signals"]
        for s in sig:
            self.assertEqual(set(s), self.SIG_KEYS)
        sells = [s for s in sig if s["kind"] == "sell"]
        buy = [s for s in sig if s["kind"] == "buy"][0]
        self.assertEqual(sells[1]["triggered"], 1)
        self.assertEqual(sells[1]["trigger_key"], "Stop Loss")
        self.assertEqual(sells[0]["triggered"], 0)
        for s in sells:
            self.assertEqual(s["have_position"], 1)  # 고정값: 엔진은 보유 중에만 매도 판단 기록
            self.assertIsNone(s["overall_ok"])
            self.assertIsNone(s["failed_keys"])
        self.assertIsNone(buy["triggered"])
        self.assertIsNone(buy["trigger_key"])
        self.assertEqual(buy["have_position"], 0)

    def test_signals_holding_shows_sell(self):
        self.make_live_db()
        self.set_strategy()
        self._buy("2026-10-23 10:00:00", 1.0)
        self._sell("2026-10-23 10:05:00", 2.0)
        self._sell("2026-10-23 10:06:00", 3.0)
        code, b = self.get_json("/v2/api/signals?limit=1")
        self.assertEqual(b["signals"][0]["kind"], "sell")
        self.assertEqual(b["signals"][0]["price"], 3.0)

    def test_signals_all_tickers_when_no_strategy(self):
        self.make_live_db()  # 전략 파일 없음 -> 종목 없음 경로
        self._buy("2026-10-23 10:00:00", 1.0, ticker="KRW-AAA")
        self._sell("2026-10-23 10:01:00", 2.0, ticker="KRW-BBB")
        code, b = self.get_json("/v2/api/signals")
        self.assertEqual(code, 200)
        self.assertEqual([s["kind"] for s in b["signals"]], ["sell", "buy"])
        self.assertEqual({s["ticker"] for s in b["signals"]}, {"KRW-AAA", "KRW-BBB"})

    def test_bad_limit_and_page_400(self):
        self.make_live_db()
        self.set_strategy()
        for p in ("/v2/api/trades?limit=0", "/v2/api/trades?limit=-1",
                  "/v2/api/trades?limit=abc", "/v2/api/trades?limit=1.5",
                  "/v2/api/trades?limit=", "/v2/api/signals?limit=0",
                  "/v2/api/signals?limit=x", "/v2/api/logs?page=0",
                  "/v2/api/logs?page=-3", "/v2/api/logs?page=abc"):
            r = self.fetch(p, headers=self.cookie())
            self.assertEqual(r.code, 400, p)
            self.assertEqual(r.headers["Content-Type"].split(";")[0],
                             "application/json", p)
            self.assertIn("error", json.loads(r.body.decode()), p)

    def test_logs_paginated_50(self):
        c = self.make_live_db()
        self.set_strategy()
        for i in range(120):
            c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES (?,?,?,?)",
                      ("alice", "2026-10-23T%02d:%02d:00+09:00" % (i // 60 + 8, i % 60),
                       "INFO", "m%03d" % i))
        c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES "
                  "('bob','2026-10-24T00:00:00+09:00','INFO','others')")
        c.commit()
        code, p1 = self.get_json("/v2/api/logs")
        code, p2 = self.get_json("/v2/api/logs?page=2")
        code, p3 = self.get_json("/v2/api/logs?page=3")
        code, p4 = self.get_json("/v2/api/logs?page=4")
        self.assertEqual([len(p["logs"]) for p in (p1, p2, p3, p4)], [50, 50, 20, 0])
        self.assertEqual(p1["page"], 1)
        self.assertEqual(p2["page"], 2)
        self.assertEqual(p1["logs"][0]["message"], "m119")
        self.assertEqual(p2["logs"][0]["message"], "m069")
        self.assertNotIn("others", [x["message"] for p in (p1, p2, p3) for x in p["logs"]])
        self.assertEqual(set(p1["logs"][0]), {"id", "timestamp", "level", "message"})

    def test_same_timestamp_ties_ordered_by_id_desc(self):
        c = self.make_live_db()
        self.set_strategy()
        for i in range(3):
            c.execute("INSERT INTO audit_trades(timestamp,ticker,type,price,reason) "
                      "VALUES ('2026-10-23 10:00:00','KRW-ZRO','BUY',?,?)",
                      (100.0 + i, "t%d" % i))
            c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES "
                      "('alice','2026-10-23 10:00:00','INFO',?)", ("l%d" % i,))
        c.commit()
        code, b = self.get_json("/v2/api/trades")
        self.assertEqual([t["reason"] for t in b["trades"]], ["t2", "t1", "t0"])
        code, b = self.get_json("/v2/api/logs")
        self.assertEqual([t["message"] for t in b["logs"]], ["l2", "l1", "l0"])
        code, b = self.get_json("/v2/api/markers")
        self.assertEqual([m["price"] for m in b["markers"]], [102.0, 101.0, 100.0])

    def test_markers_current_ticker_max_200(self):
        self.make_live_db()
        self.set_strategy()
        self._trades(250)
        self._trades(5, ticker="KRW-OTHER")
        code, b = self.get_json("/v2/api/markers")
        self.assertEqual(len(b["markers"]), 200)
        self.assertEqual(set(b["markers"][0]), {"type", "price", "bar_time"})


class TestQueries(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _params(self, sql):
        return tuple(1 for _ in range(sql.count("?")))

    def test_queries_registered(self):
        self.assertGreaterEqual(len(api_read.ALL_SQL), 10)
        consts = {k: v for k, v in vars(api_read).items()
                  if k.startswith("SQL_") and isinstance(v, str)}
        self.assertEqual(sorted(consts.values()), sorted(api_read.ALL_SQL))

    def test_queries_all_have_limit(self):
        for sql in api_read.ALL_SQL:
            self.assertRegex(sql, r"(?i)\blimit\s+(\d+|\?)(\s+offset\s+(\d+|\?))?\s*$", sql)
            self.assertNotIn("--", sql)
            self.assertNotIn("/*", sql)

    def test_queries_use_index(self):
        self.assertGreaterEqual(
            sqlite3.sqlite_version_info, (3, 36, 0),
            "sqlite %s: 3.36 미만이면 계획 문구가 달라 이 시험을 신뢰할 수 없다"
            % sqlite3.sqlite_version)
        ok = re.compile(r"USING (COVERING )?INDEX|USING INTEGER PRIMARY KEY|"
                        r"USING PRIMARY KEY|autoindex")
        for sql in api_read.ALL_SQL:
            plan = self.conn.execute("EXPLAIN QUERY PLAN " + sql,
                                     self._params(sql)).fetchall()
            details = [r[3] for r in plan]
            for d in details:
                self.assertNotIn("USE TEMP B-TREE", d, (sql, details))
                if re.fullmatch(r"SCAN \w+", d):
                    self.assertRegex(sql, r"ORDER BY id DESC LIMIT", (sql, details))
                else:
                    self.assertRegex(d, ok, (sql, details))

    def test_no_where_ticker_order_by_id(self):
        for sql in api_read.ALL_SQL:
            self.assertNotRegex(sql, r"WHERE ticker=\? ORDER BY id DESC", sql)
            self.assertNotIn("ORDER BY bar_time", sql)


class TestLint(unittest.TestCase):
    def test_fixture_ddl_matches_init_db(self):
        text = _squash(_strip_comments(INIT_DB.read_text(encoding="utf-8")))
        # CREATE TABLE 8개, CREATE INDEX 7개, ALTER/인덱스 15개를 모두 원문과 대조한다
        self.assertEqual(len(CREATE_STATEMENTS), 8)
        self.assertEqual(len(INDEX_STATEMENTS), 7)
        # 문장 끝까지 일치: 원문은 따옴표(""" 또는 ")로 감싸여 있으므로 감싼 채 비교한다
        groups = ((CREATE_STATEMENTS, '"""'), (INDEX_STATEMENTS, '"'),
                  (ALTER_STATEMENTS, '"'))
        for stmts, q in groups:
            last_pos = -1
            for s in stmts:
                sq = _squash(_strip_comments(s))
                self.assertTrue(sq)
                needle = q + sq + q
                pos = text.find(needle)
                self.assertGreaterEqual(pos, 0, s)
                # init_db.py 안의 순서와 같아야 한다(위치가 커지는 순서)
                self.assertGreater(pos, last_pos, s)
                last_pos = pos
        # 문장 끝이 잘린 사본은 통과하지 못해야 한다
        cut = _squash(ALTER_STATEMENTS[0])[:-3]
        self.assertNotIn('"' + cut + '"', text)

    def test_lint_detects_drift(self):
        text = _squash(_strip_comments(INIT_DB.read_text(encoding="utf-8")))
        drifted = _squash(CREATE_STATEMENTS[1].replace("message TEXT", "message BLOB"))
        self.assertNotIn(drifted, text)

    def test_api_read_imports(self):
        src = (ROOT / "v2" / "api_read.py").read_text(encoding="utf-8")
        self.assertNotIn("v2.server", src)
        self.assertNotIn("from v2 import server", src)
        self.assertNotIn("open_live_ro", src)
        for bad in ("pyupbit", "streamlit", "services.", "engine.", "api.upbit.com"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
