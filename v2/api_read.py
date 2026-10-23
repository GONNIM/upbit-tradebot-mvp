"""신버전 대시보드 읽기 API (GET /v2/api/*).

- 모든 응답은 세션의 user_id 로만 만든다(URL 로 받은 user_id 는 보지 않는다).
- 실매매 DB 는 v2.db.query() 로만 읽는다(읽기 전용·LIMIT 필수·2초 상한).
- 시각은 모두 KST ISO(+09:00) 로 돌려준다(DB 에는 ISO 와 'YYYY-MM-DD HH:MM:SS' 가 섞여 있음).
"""
import re
import sqlite3
from datetime import datetime
from typing import Optional

from v2 import db
from v2.handlers import ApiHandler
from v2.status import engine_state, interval_sec, mode_state

# ---- SQL (모듈 상수; 시험이 SQL_ 로 시작하는 상수 전부를 검사한다) ----
# 종목 조건이 있으면 `WHERE ticker=? ORDER BY timestamp DESC`(idx_*_ticker_ts),
# 없으면 `ORDER BY id DESC`. `WHERE ticker=? ORDER BY id DESC` 조합은 쓰지 않는다.
SQL_ENGINE_STATUS = "SELECT last_mode FROM engine_status WHERE user_id=? LIMIT 1"
SQL_PAUSED = "SELECT trading_paused FROM users WHERE username = ? LIMIT 1"
SQL_ACCOUNT = ("SELECT virtual_krw, virtual_krw_locked, updated_at "
               "FROM accounts WHERE user_id=? LIMIT 1")
SQL_POSITION = ("SELECT virtual_coin, virtual_coin_locked, entry_price, updated_at "
                "FROM account_positions WHERE user_id=? AND ticker=? LIMIT 1")
SQL_BUY_EVAL_LATEST = ("SELECT timestamp, price FROM audit_buy_eval "
                       "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT 1")
SQL_SELL_EVAL_LATEST = ("SELECT timestamp, price, tp_price, sl_price FROM audit_sell_eval "
                        "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT 1")
# 엔진의 매수 표기는 audit_trades.type='BUY' (services/db.py:795,2062)
SQL_LAST_BUY = ("SELECT timestamp FROM audit_trades "
                "WHERE ticker=? AND type='BUY' ORDER BY timestamp DESC, id DESC LIMIT 1")
SQL_TRADES_TICKER = ("SELECT id, timestamp, bar_time, ticker, type, reason, price, qty, "
                     "entry_price, note FROM audit_trades "
                     "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT ?")
SQL_TRADES_ALL = ("SELECT id, timestamp, bar_time, ticker, type, reason, price, qty, "
                  "entry_price, note FROM audit_trades ORDER BY id DESC LIMIT ?")
SQL_SIGNALS_TICKER = ("SELECT id, timestamp, bar_time, ticker, price, macd, signal, "
                      "have_position, overall_ok, failed_keys FROM audit_buy_eval "
                      "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT ?")
SQL_SIGNALS_ALL = ("SELECT id, timestamp, bar_time, ticker, price, macd, signal, "
                   "have_position, overall_ok, failed_keys FROM audit_buy_eval "
                   "ORDER BY id DESC LIMIT ?")
SQL_LOGS = ("SELECT id, timestamp, level, message FROM logs "
            "WHERE user_id=? ORDER BY timestamp DESC, id DESC LIMIT 50 OFFSET ?")
SQL_MARKERS = ("SELECT type, price, bar_time FROM audit_trades "
               "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT 200")

ALL_SQL = [v for k, v in sorted(globals().items())
           if k.startswith("SQL_") and isinstance(v, str)]

DEFAULT_BAR_SEC = 180
MAX_LIMIT = 50
LOGS_PAGE_SIZE = 50
MAX_PAGE = 100000
_DIGITS = re.compile(r"[0-9]+")


def _iso(s) -> Optional[str]:
    if s is None:
        return None
    try:
        return db.parse_ts(str(s)).isoformat()
    except (ValueError, TypeError):
        return str(s)


def _dt(s) -> Optional[datetime]:
    if s is None:
        return None
    try:
        return db.parse_ts(str(s))
    except (ValueError, TypeError):
        return None


def _nonzero(v):
    return None if v is None or v == 0 else v


def _num(v, default=0):
    return default if v is None else v


class ReadHandler(ApiHandler):
    """읽기 API 공통: 세션 user_id·현재 전략/종목 해석, DB 오류 응답."""

    def _int_arg(self, name: str, default: int) -> Optional[int]:
        """양의 정수 인자. 잘못되면 400 을 보내고 None."""
        raw = self.get_argument(name, None)
        if raw is None:
            return default
        if not _DIGITS.fullmatch(raw) or int(raw) <= 0:
            self.send_json({"error": "bad_request", "field": name}, 400)
            return None
        return int(raw)

    def _context(self):
        user_id = self.current_user["user_id"]
        value, mtime = db.active_strategy(user_id)
        params = {}
        if value:
            try:
                params = db.strategy_params(user_id, value)
            except ValueError:
                params = {}
        ticker = params.get("ticker") if isinstance(params.get("ticker"), str) else None
        interval = params.get("interval") if isinstance(params.get("interval"), str) else None
        return user_id, value, mtime, ticker, interval

    def _guard(self, fn):
        try:
            fn()
        except FileNotFoundError:
            self.send_json({"error": "no_data"}, 404)
        except sqlite3.Error:
            self.send_json({"error": "db_unavailable"}, 503)


class StatusHandler(ReadHandler):
    def get(self):
        self._guard(self._get)

    def _get(self):
        user_id, value, mtime, ticker, interval = self._context()
        entry_mode = self.current_user["mode"]
        now = datetime.now(db.KST)

        st = db.query(user_id, SQL_ENGINE_STATUS, (user_id,))
        engine_mode = st[0]["last_mode"] if st else None
        mode = mode_state(engine_mode, entry_mode)

        pr = db.query(user_id, SQL_PAUSED, (user_id,))
        paused = bool(pr and pr[0]["trading_paused"])

        acc = db.query(user_id, SQL_ACCOUNT, (user_id,))
        accounts_ts = _dt(acc[0]["updated_at"]) if acc else None

        last_eval = None
        if ticker:
            for sql in (SQL_BUY_EVAL_LATEST, SQL_SELL_EVAL_LATEST):
                rows = db.query(user_id, sql, (ticker,))
                t = _dt(rows[0]["timestamp"]) if rows else None
                if t is not None and (last_eval is None or t > last_eval):
                    last_eval = t

        try:
            bar_sec = interval_sec(interval)
        except ValueError:
            bar_sec = DEFAULT_BAR_SEC
        eng = engine_state(last_eval, accounts_ts, engine_mode or entry_mode,
                           bar_sec, now)

        body = {"engine": eng}
        body.update(mode)
        body.update({"strategy": {"value": value, "mtime": mtime},
                     "ticker": ticker, "interval": interval, "paused": paused})
        self.send_json(body)


class AssetsHandler(ReadHandler):
    def get(self):
        self._guard(self._get)

    def _get(self):
        user_id, _value, _mtime, ticker, _interval = self._context()
        acc = db.query(user_id, SQL_ACCOUNT, (user_id,))
        acc = acc[0] if acc else {}
        pos, buy, sell = {}, None, None
        if ticker:
            rows = db.query(user_id, SQL_POSITION, (user_id, ticker))
            pos = rows[0] if rows else {}
            rows = db.query(user_id, SQL_BUY_EVAL_LATEST, (ticker,))
            buy = rows[0] if rows else None
            rows = db.query(user_id, SQL_SELL_EVAL_LATEST, (ticker,))
            sell = rows[0] if rows else None

        # 현재가: 매수/매도 판단 기록 중 더 최신 행(E5)
        price, price_at = None, None
        best = None
        for row in (buy, sell):
            if row is None:
                continue
            t = _dt(row["timestamp"])
            if t is not None and (best is None or t > best):
                best, price, price_at = t, row["price"], _iso(row["timestamp"])

        coin = _num(pos.get("virtual_coin"), 0)
        coin_locked = _num(pos.get("virtual_coin_locked"), 0)
        # 보유 판단은 엔진 정의(services/db.py:697-701, 2696-2703)와 같게 가용+묶임 합
        holding = (coin + coin_locked) > 0
        entry = _nonzero(pos.get("entry_price"))
        pnl = None
        if holding and entry and price:
            pnl = price / entry - 1.0
        tp = sl = None
        if holding and sell is not None:
            # 이번 포지션의 판단 행만 쓴다: 최신 BUY 체결보다 이른 행은 이전 포지션 값
            last_buy = None
            if ticker:
                rows = db.query(user_id, SQL_LAST_BUY, (ticker,))
                last_buy = _dt(rows[0]["timestamp"]) if rows else None
            sell_t = _dt(sell["timestamp"])
            if not (last_buy is not None and sell_t is not None and sell_t < last_buy):
                tp, sl = _nonzero(sell["tp_price"]), _nonzero(sell["sl_price"])

        upd = acc.get("updated_at") or pos.get("updated_at")
        self.send_json({
            "krw": _num(acc.get("virtual_krw"), 0),
            "krw_locked": _num(acc.get("virtual_krw_locked"), 0),
            "coin": coin,
            "coin_locked": coin_locked,
            "entry_price": entry,
            "price": price,
            "price_at": price_at,
            "pnl": pnl,
            "tp_price": tp,
            "sl_price": sl,
            "round": None,  # 회차는 PULLBACK(P3) 개념 — 1차는 항상 null
            "updated_at": _iso(upd),
        })


class _ListHandler(ReadHandler):
    SQL_TICKER = ""
    SQL_ALL = ""
    KEY = ""
    DEFAULT_LIMIT = 10

    def get(self):
        limit = self._int_arg("limit", self.DEFAULT_LIMIT)
        if limit is None:
            return
        limit = min(limit, MAX_LIMIT)
        self._guard(lambda: self._get(limit))

    def _get(self, limit):
        user_id, _v, _m, ticker, _i = self._context()
        if ticker:
            rows = db.query(user_id, self.SQL_TICKER, (ticker, limit))
        else:
            rows = db.query(user_id, self.SQL_ALL, (limit,))
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
            r["bar_time"] = _iso(r["bar_time"])
        self.send_json({self.KEY: rows})


class TradesHandler(_ListHandler):
    SQL_TICKER = SQL_TRADES_TICKER
    SQL_ALL = SQL_TRADES_ALL
    KEY = "trades"
    DEFAULT_LIMIT = 10


class SignalsHandler(_ListHandler):
    SQL_TICKER = SQL_SIGNALS_TICKER
    SQL_ALL = SQL_SIGNALS_ALL
    KEY = "signals"
    DEFAULT_LIMIT = 20


class LogsHandler(ReadHandler):
    def get(self):
        page = self._int_arg("page", 1)
        if page is None:
            return
        page = min(page, MAX_PAGE)
        self._guard(lambda: self._get(page))

    def _get(self, page):
        user_id = self.current_user["user_id"]
        rows = db.query(user_id, SQL_LOGS,
                        (user_id, (page - 1) * LOGS_PAGE_SIZE))
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
        self.send_json({"logs": rows, "page": page})


class MarkersHandler(ReadHandler):
    def get(self):
        self._guard(self._get)

    def _get(self):
        user_id, _v, _m, ticker, _i = self._context()
        rows = []
        if ticker:
            rows = db.query(user_id, SQL_MARKERS, (ticker,))
            for r in rows:
                r["bar_time"] = _iso(r["bar_time"])
        self.send_json({"markers": rows})


ROUTES = [
    (r"/v2/api/status", StatusHandler),
    (r"/v2/api/assets", AssetsHandler),
    (r"/v2/api/trades", TradesHandler),
    (r"/v2/api/signals", SignalsHandler),
    (r"/v2/api/logs", LogsHandler),
    (r"/v2/api/markers", MarkersHandler),
]
