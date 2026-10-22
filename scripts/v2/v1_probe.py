"""Task 0 Step 2 (V1) 서버 실측 — 실매매 DB 읽기 전용. 쓰기·PRAGMA journal_mode 없음."""
import os
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DB = "/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db"
ROW_CAP = 50000
DAYS = 7


def parse(ts):
    if not ts:
        return None
    s = ts.strip()
    try:
        if "T" in s:
            d = datetime.fromisoformat(s)
            return d.astimezone(KST) if d.tzinfo else d.replace(tzinfo=KST)
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:
        return None


def gaps(times):
    t = sorted(times)
    g = [(b - a).total_seconds() for a, b in zip(t, t[1:])]
    if not g:
        return "n=0"
    g.sort()
    p95 = g[min(len(g) - 1, int(len(g) * 0.95))]
    return f"rows={len(t)} gaps={len(g)} median={statistics.median(g):.0f}s p95={p95:.0f}s max={g[-1]:.0f}s"


def main():
    if not os.path.exists(DB):
        print("DB 없음 — 중단")
        sys.exit(1)
    print("wal_exists_before", os.path.exists(DB + "-wal"), "shm_exists_before", os.path.exists(DB + "-shm"))
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=3)
    con.execute("PRAGMA busy_timeout=3000")
    deadline = [0.0]
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline[0] else 0, 10000)

    def q(sql, args=()):
        deadline[0] = time.monotonic() + 2.0
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.OperationalError as e:
            print("query_failed", repr(e), "sql", sql)
            return []

    try:
        probe(q)
    finally:
        con.close()
        print("wal_exists_after", os.path.exists(DB + "-wal"), "shm_exists_after", os.path.exists(DB + "-shm"))


def probe(q):
    print("sqlite_version", sqlite3.sqlite_version)
    now = datetime.now(KST)
    cutoff = now - timedelta(days=DAYS)
    print("now", now.isoformat(timespec="seconds"), "cutoff", cutoff.isoformat(timespec="seconds"))

    combined = []
    for table in ("audit_buy_eval", "audit_sell_eval"):
        rows = q(f"SELECT timestamp FROM {table} ORDER BY id DESC LIMIT {ROW_CAP}")
        ts = [p for p in (parse(r[0]) for r in rows) if p and p >= cutoff]
        unparsed = sum(1 for r in rows if parse(r[0]) is None)
        print(table, gaps(ts), "unparsed", unparsed, "capped", len(rows) == ROW_CAP,
              "latest", max(ts).isoformat(timespec="seconds") if ts else None)
        combined += ts
    print("combined", gaps(combined))

    for r in q("SELECT user_id, updated_at FROM accounts LIMIT 20"):
        print("accounts", r[0], r[1])
    for r in q("SELECT * FROM engine_status LIMIT 20"):
        print("engine_status", r)
    for r in q("SELECT name, tbl_name FROM sqlite_master WHERE type='index' LIMIT 200"):
        print("index", r[0], r[1])


if __name__ == "__main__":
    main()
