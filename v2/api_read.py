"""신버전 대시보드 읽기 API (GET /v2/api/*).

- 모든 응답은 세션의 user_id 로만 만든다(URL 로 받은 user_id 는 보지 않는다).
- 실매매 DB 는 v2.db.query() 로만 읽는다(읽기 전용·LIMIT 필수·2초 상한).
- 시각은 모두 KST ISO(+09:00) 로 돌려준다(DB 에는 ISO 와 'YYYY-MM-DD HH:MM:SS' 가 섞여 있음).
"""
import json
import re
import sqlite3
from datetime import datetime
from typing import Optional

from v2 import db
from v2.handlers import ApiHandler
from v2.status import engine_alive_running, engine_state, interval_sec, mode_state

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
SQL_SIGNALS_SELL_TICKER = (
    "SELECT id, timestamp, bar_time, ticker, price, macd, signal, triggered, "
    "trigger_key FROM audit_sell_eval WHERE ticker=? "
    "ORDER BY timestamp DESC, id DESC LIMIT ?")
SQL_SIGNALS_SELL_ALL = (
    "SELECT id, timestamp, bar_time, ticker, price, macd, signal, triggered, "
    "trigger_key FROM audit_sell_eval ORDER BY id DESC LIMIT ?")
SQL_LOGS = ("SELECT id, timestamp, level, message FROM logs "
            "WHERE user_id=? ORDER BY timestamp DESC, id DESC LIMIT 50 OFFSET ?")
SQL_MARKERS = ("SELECT type, price, bar_time FROM audit_trades "
               "WHERE ticker=? ORDER BY timestamp DESC, id DESC LIMIT 200")

# ---- 기본 기능 블록(GET /v2/api/basic) ----
# 최종 상태 로그: services/db.py get_last_status_log_from_db 와 같은 조건(이모지 접두 9종).
# user_id 만 바인딩, 접두는 문자 그대로. 서버 EXPLAIN: idx_logs_user_ts 사용.
SQL_LAST_STATUS_LOG = (
    "SELECT timestamp, message FROM logs WHERE user_id=? "
    "AND level IN ('INFO','BUY','SELL') "
    "AND (message LIKE '🚀%' OR message LIKE '🔌%' OR message LIKE '🛑%' "
    "OR message LIKE '✅%' OR message LIKE '⚠️%' OR message LIKE '📡%' "
    "OR message LIKE '🔄%' OR message LIKE '❌%' OR message LIKE '🚨%') "
    "ORDER BY timestamp DESC LIMIT 1")
# 진입가: 구버전 get_last_open_buy_order(services/db.py:1844-2042)의 3단계를 종목 단위로 직접 조회한다.
# 정렬은 id(구버전은 COALESCE(executed_at, updated_at, timestamp)) — 계획서 1-1 「알려진 차이」.
SQL_ORDERS_LAST_BUY_FILLED = (
    "SELECT id, COALESCE(avg_price, price) AS price, COALESCE(executed_at, updated_at) AS ts "
    "FROM orders WHERE user_id=? AND ticker=? AND side='BUY' "
    "AND (state IN ('completed','filled','FILLED') OR (state='CANCELED' AND executed_volume>0)) "
    "ORDER BY id DESC LIMIT 1")
SQL_ORDERS_LAST_BUY_ANY = (
    "SELECT id, COALESCE(avg_price, price) AS price, COALESCE(executed_at, updated_at) AS ts "
    "FROM orders WHERE user_id=? AND ticker=? AND side='BUY' ORDER BY id DESC LIMIT 1")
SQL_ORDERS_MAX_BUY_ID = (
    "SELECT MAX(id) AS m FROM orders WHERE user_id=? AND ticker=? AND side='BUY' "
    "AND state IN ('completed','filled','FILLED') LIMIT 1")
SQL_ORDERS_MAX_SELL_ID = (
    "SELECT MAX(id) AS m FROM orders WHERE user_id=? AND ticker=? AND side='SELL' "
    "AND state IN ('completed','filled','FILLED') LIMIT 1")
SQL_HTS_SELL_AFTER = ("SELECT id, timestamp FROM audit_trades "
                      "WHERE ticker=? AND type='HTS_SELL' AND timestamp > ? "
                      "ORDER BY timestamp LIMIT 1")
# 실현: 구버전 fetch_recent_orders(user_id, limit=50) 와 같은 최근 50건
SQL_ORDERS_RECENT = ("SELECT ticker, side, price FROM orders WHERE user_id=? "
                     "ORDER BY id DESC LIMIT 50")

ALL_SQL = [v for k, v in sorted(globals().items())
           if k.startswith("SQL_") and isinstance(v, str)]

DEFAULT_BAR_SEC = 180
ENGINE_ALIVE_FILE = ".engine_alive.json"   # 엔진 프로세스(scripts/tradebot_boot.py)가 services/data 에 5초마다 씀
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
        ticker = db.normalize_ticker(params.get("ticker"))   # 'JTO' → 'KRW-JTO' (엔진과 같은 규칙)
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
    """최신 신호 = 매수 판단 + 매도 판단을 시각순으로 합친 목록 (사용자 결정 1023-01 결정 2 나)."""
    KEY = "signals"
    DEFAULT_LIMIT = 20

    def _get(self, limit):
        user_id, _v, _m, ticker, _i = self._context()
        if ticker:
            buys = db.query(user_id, SQL_SIGNALS_TICKER, (ticker, limit))
            sells = db.query(user_id, SQL_SIGNALS_SELL_TICKER, (ticker, limit))
        else:
            buys = db.query(user_id, SQL_SIGNALS_ALL, (limit,))
            sells = db.query(user_id, SQL_SIGNALS_SELL_ALL, (limit,))

        items = []
        for r in buys:
            items.append((_dt(r["timestamp"]), 1, r["id"], {
                "id": r["id"], "kind": "buy",
                "timestamp": _iso(r["timestamp"]), "bar_time": _iso(r["bar_time"]),
                "ticker": r["ticker"], "price": r["price"], "macd": r["macd"],
                "signal": r["signal"], "have_position": r["have_position"],
                "overall_ok": r["overall_ok"], "failed_keys": r["failed_keys"],
                "triggered": None, "trigger_key": None}))
        for r in sells:
            items.append((_dt(r["timestamp"]), 0, r["id"], {
                "id": r["id"], "kind": "sell",
                "timestamp": _iso(r["timestamp"]), "bar_time": _iso(r["bar_time"]),
                "ticker": r["ticker"], "price": r["price"], "macd": r["macd"],
                "signal": r["signal"],
                # audit_sell_eval 에는 보유 열이 없다(services/init_db.py:346-368).
                # 엔진은 보유 중에만 매도 판단을 기록하므로 고정값 1.
                "have_position": 1,
                "overall_ok": None, "failed_keys": None,
                "triggered": r["triggered"], "trigger_key": r["trigger_key"]}))

        # 최신순; 시각 같으면 매도 먼저(0), 같은 종류는 id 큰 것 먼저. 파싱 실패(None)는 맨 뒤.
        # 두 표의 id 는 서로 비교하지 않는다(같은 종류 안에서만 의미 있음: kind 가 먼저 갈림).
        def key(it):
            ts, kind_rank, rid, _row = it
            return (ts is None, -(ts.timestamp() if ts is not None else 0.0),
                    kind_rank, -(rid or 0))

        items.sort(key=key)
        self.send_json({self.KEY: [it[3] for it in items[:limit]]})


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


def entry_price_open(user_id: str, ticker: str) -> Optional[float]:
    """미실현 💹 칸의 진입가. 구버전 get_last_open_buy_order 와 같은 3단계(계획서 1-1).

    1) 체결 BUY 최신 1건 → 2) 있으면 이후 SELL·HTS_SELL 이 있는지 보고 청산이면 None
    3) 없으면 상태 조건 없이 같은 조회 → 같은 두 검사. 가격 열이 비면 None.
    """
    def closed(row) -> bool:
        b = db.query(user_id, SQL_ORDERS_MAX_BUY_ID, (user_id, ticker))
        s = db.query(user_id, SQL_ORDERS_MAX_SELL_ID, (user_id, ticker))
        buy_id = b[0]["m"] if b else None
        sell_id = s[0]["m"] if s else None
        if buy_id is not None and sell_id is not None and sell_id > buy_id:
            return True
        ts = row.get("ts")
        if ts:
            hts = db.query(user_id, SQL_HTS_SELL_AFTER, (ticker, ts))
            if hts:
                return True
        return False

    for sql in (SQL_ORDERS_LAST_BUY_FILLED, SQL_ORDERS_LAST_BUY_ANY):
        rows = db.query(user_id, sql, (user_id, ticker))
        if not rows:
            continue
        row = rows[0]
        if closed(row):
            return None
        price = row.get("price")
        return float(price) if price else None
    return None


def realized_pct(user_id: str, ticker: str) -> Optional[float]:
    """최근 50건 주문에서 이 종목의 가장 최근 SELL 과 그보다 오래된 가장 가까운 BUY 의 price 열 수익률(%).
    구버전 pages/dashboard.py 888-907 과 같은 순회. 50건 안에 없으면 None."""
    orders = db.query(user_id, SQL_ORDERS_RECENT, (user_id,))
    for i, o in enumerate(orders):
        if o["ticker"] != ticker or o["side"] != "SELL":
            continue
        try:
            sell = float(o["price"])
        except (TypeError, ValueError):
            return None
        for p in orders[i + 1:]:
            if p["ticker"] == ticker and p["side"] == "BUY":
                try:
                    buy = float(p["price"])
                except (TypeError, ValueError):
                    return None
                return (sell - buy) / buy * 100.0 if buy else None
        return None   # 가장 최근 SELL 만 본다
    return None


def status_log_text(row) -> str:
    """구버전 get_last_status_log_from_db 와 같은 표기."""
    if not row:
        return "❌ 상태 로그 없음"
    ts = row["timestamp"]
    try:
        shown = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        shown = ts
    return "[%s] %s" % (shown, row["message"])


class BasicHandler(ReadHandler):
    """기본 기능 블록용: 버전·최종 상태 로그·엔진 생존·💹 칸 계산(구버전 같은 식).

    모드·일시중지·자산 숫자는 기존 /status·/assets 가 준다(basic.js 가 세 개를 함께 읽는다).
    """

    def get(self):
        self._guard(self._get)

    def _get(self):
        user_id, _v, _m, ticker, _i = self._context()
        now = datetime.now(db.KST)

        logs = db.query(user_id, SQL_LAST_STATUS_LOG, (user_id,))
        last_log = status_log_text(logs[0] if logs else None)

        try:
            with open(db.DATA_DIR / ENGINE_ALIVE_FILE, "rb") as f:
                alive_data = json.loads(f.read(65536).decode("utf-8"))
        except (OSError, ValueError):
            alive_data = None
        engine_running = engine_alive_running(alive_data, user_id, now)

        # 💹 칸: 가용 수량 > 0 이면 미실현, 아니면 실현 (dashboard.py:863)
        pnl_kind, pnl_pct = "realized", None
        coin = 0.0
        price = None
        if ticker:
            pos = db.query(user_id, SQL_POSITION, (user_id, ticker))
            coin = _num(pos[0].get("virtual_coin") if pos else 0, 0)
            best = None
            for sql in (SQL_BUY_EVAL_LATEST, SQL_SELL_EVAL_LATEST):
                rows = db.query(user_id, sql, (ticker,))
                t = _dt(rows[0]["timestamp"]) if rows else None
                if t is not None and (best is None or t > best):
                    best, price = t, rows[0]["price"]
            if coin > 0:
                pnl_kind = "unrealized"
                entry = entry_price_open(user_id, ticker)
                if entry and price:
                    pnl_pct = (float(price) - entry) / entry * 100.0
            else:
                pnl_pct = realized_pct(user_id, ticker)

        self.send_json({
            "version": db.app_version(),
            "account": user_id,
            "last_status_log": last_log,
            "engine_running": engine_running,
            "pnl_kind": pnl_kind,
            "pnl_pct": pnl_pct,
        })


ROUTES = [
    (r"/v2/api/basic", BasicHandler),
    (r"/v2/api/status", StatusHandler),
    (r"/v2/api/assets", AssetsHandler),
    (r"/v2/api/trades", TradesHandler),
    (r"/v2/api/signals", SignalsHandler),
    (r"/v2/api/logs", LogsHandler),
    (r"/v2/api/markers", MarkersHandler),
]
