# WO-20 배포 0단계 (서버, 읽기 전용): 이력 요약 · 포지션 · 정렬 비교
# Upbit 은 GET /v1/accounts 만 호출 (주문 생성·취소 없음). DB 는 mode=ro.
import os, uuid, sqlite3, jwt, requests
from datetime import datetime
from zoneinfo import ZoneInfo

os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")
print("조회 시각", datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"))
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)

print("== 10-02 14:15 봇 매도(id 557) 이후 orders")
rows = c.execute("select id, timestamp, ticker, side, state, executed_volume, avg_price, executed_at, canceled_at "
                 "from orders where id > 557 order by id").fetchall()
print(f"   건수: {len(rows)}")
by = {}
for r in rows:
    by[(r[2], r[3], r[4])] = by.get((r[2], r[3], r[4]), 0) + 1
for k in sorted(by):
    print(f"   {k}: {by[k]}")
for r in rows[-5:]:
    print("   ", r)
last = c.execute("select id, timestamp, ticker, side, state from orders order by id desc limit 1").fetchone()
print("   마지막 주문:", last)
print("== 10-02 14:15 이후 audit_trades")
for r in c.execute("select id, timestamp, ticker, type, price, reason from audit_trades "
                   "where timestamp > '2026-10-02T14:15:14.1' order by id"):
    print("   ", r)

print("== KRW-JTO 포지션")
print("   account_positions:", c.execute(
    "select virtual_coin, virtual_coin_locked, entry_price, meta, updated_at from account_positions "
    "where ticker='KRW-JTO'").fetchall())
tok = jwt.encode({"access_key": ak, "nonce": str(uuid.uuid4())}, sk)
r = requests.get("https://api.upbit.com/v1/accounts", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
data = r.json()
jto = [{k: a.get(k) for k in ("currency", "balance", "locked", "avg_buy_price")} for a in data if a.get("currency") == "JTO"] \
    if isinstance(data, list) else data
print(f"   Upbit /v1/accounts http {r.status_code} JTO: {jto}" + (" (행 없음 = 0)" if jto == [] else ""))

print("== 정렬 비교 (KRW-JTO BUY, get_last_open_buy_order 와 같은 WHERE)")
W = ("user_id='mcmax33' AND ticker='KRW-JTO' AND side='BUY' AND "
     "(state IN ('completed','filled','FILLED') OR (state='CANCELED' AND executed_volume > 0))")
old = c.execute(f"SELECT id, COALESCE(avg_price, price), entry_bar, executed_at, timestamp FROM orders WHERE {W} "
                "ORDER BY executed_at , timestamp DESC, ROWID DESC LIMIT 1").fetchone()
new = c.execute(f"SELECT id, COALESCE(avg_price, price), entry_bar, COALESCE(executed_at, updated_at), timestamp FROM orders "
                f"WHERE {W} ORDER BY COALESCE(executed_at, updated_at, timestamp) DESC, ROWID DESC LIMIT 1").fetchone()
print("   옛 정렬:", old)
print("   새 정렬:", new)
print("   같은 id:", old[0] == new[0])
print("   executed_at 채워진 행 수(전체 orders):", c.execute("select count(*) from orders where executed_at is not null").fetchone()[0])
b = c.execute("select max(rowid) from orders where user_id='mcmax33' and ticker='KRW-JTO' and side='BUY' and state in ('completed','filled','FILLED')").fetchone()[0]
s = c.execute("select max(rowid) from orders where user_id='mcmax33' and ticker='KRW-JTO' and side='SELL' and state in ('completed','filled','FILLED')").fetchone()[0]
print(f"   청산 검사(B1): 마지막 BUY rowid={b} SELL rowid={s} → get_last_open_buy_order 반환 {'None (청산됨)' if s and b and s > b else '위 행'}")
