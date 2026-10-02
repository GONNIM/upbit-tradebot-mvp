# WO-20 B (서버, 읽기 전용): orders.executed_at 실태
# 사용자 DB 목록은 os.listdir 로 찾는다 (와일드카드 패턴 미사용)
import os, sqlite3, json
from datetime import datetime

DATA = "/root/upbit-tradebot-mvp/services/data"
names = sorted(n for n in os.listdir(DATA) if n.startswith("tradebot_") and n.endswith(".db"))
print("DB 파일:", names)


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


print("\n== B1 state=FILLED 행 수 / executed_at NULL 수 (side 별), 그 밖의 state 도 함께")
tot = {}
filled_with_exec = []
for n in names:
    c = ro(os.path.join(DATA, n))
    if not c.execute("select 1 from sqlite_master where type='table' and name='orders'").fetchone():
        print(f"  {n}: orders 테이블 없음")
        continue
    cols = [r[1] for r in c.execute("pragma table_info(orders)")]
    if "executed_at" not in cols:
        print(f"  {n}: executed_at 열 없음")
        continue
    print(f"  {n}: orders 전체 {c.execute('select count(*) from orders').fetchone()[0]}행")
    rows = c.execute(
        "select coalesce(state,'(NULL)'), side, count(*), sum(executed_at is null), sum(executed_at is not null) "
        "from orders group by 1,2 order by 1,2").fetchall()
    for st, side, cnt, nnull, nset in rows:
        print(f"  {n:34s} state={st:18s} side={side:4s} 행={cnt:5d} executed_at NULL={nnull:5d} 채워짐={nset}")
        k = (st, side)
        a = tot.setdefault(k, [0, 0, 0])
        a[0] += cnt; a[1] += nnull; a[2] += nset
    for r in c.execute("select id, user_id, ticker, side, state, status, requested_at, executed_at, updated_at, meta "
                       "from orders where executed_at is not null order by id"):
        filled_with_exec.append((n,) + tuple(r))
print("  -- 합계")
for (st, side), (cnt, nnull, nset) in sorted(tot.items()):
    print(f"  state={st:18s} side={side:4s} 행={cnt:5d} executed_at NULL={nnull:5d} 채워짐={nset}")

print("\n== B2 executed_at 이 채워진 행")
if not filled_with_exec:
    print("  전무")
for r in filled_with_exec[:30]:
    print("  ", r)

print("\n== B3 KRW-JTO (mcmax33) 매수: get_last_open_buy_order 와 같은 체결 필터 "
      "(state IN completed/filled/FILLED OR (CANCELED AND executed_volume>0))")
c = ro(os.path.join(DATA, "tradebot_mcmax33.db"))
FILT = ("user_id='mcmax33' and ticker='KRW-JTO' and side='BUY' and "
        "(state in ('completed','filled','FILLED') or (state='CANCELED' and executed_volume>0))")
print("  state 별:", c.execute(f"select state, count(*) from orders where {FILT} group by state").fetchall())
rows = c.execute(f"select id, requested_at, updated_at, timestamp, meta from orders where {FILT} order by id").fetchall()
print(f"  대상 행: {len(rows)}")
over, missing, deltas, no_iv = [], 0, [], 0
for oid, req, upd, ts, meta in rows:
    if not req or not upd:
        missing += 1
        continue
    d = (datetime.fromisoformat(upd) - datetime.fromisoformat(req)).total_seconds()
    deltas.append(d)
    try:
        m = json.loads(meta) if meta else {}
    except Exception:
        m = {}
    iv = m.get("interval_sec")
    if iv is None:
        no_iv += 1
        continue
    if d > float(iv):
        over.append((oid, req, upd, round(d, 1), iv, m.get("reason"), m.get("fixed_price_buy")))
print(f"  requested_at/updated_at 결측: {missing}  meta.interval_sec 없음: {no_iv}")
if deltas:
    s = sorted(deltas)
    q = lambda p: s[min(len(s) - 1, int(p * (len(s) - 1)))]
    print(f"  차이(초) 최소 {s[0]:.1f} / 중앙 {q(0.5):.1f} / 90% {q(0.9):.1f} / 99% {q(0.99):.1f} / 최대 {s[-1]:.1f}")
    for lim in (5, 10, 30, 60, 300):
        print(f"  차이 ≤ {lim}초: {sum(1 for x in s if x <= lim)}")
print(f"  차이 > interval_sec 인 행: {len(over)}")
for r in over[:20]:
    print("   ", r)
print("  meta.interval_sec 값 분포:",
      sorted({(json.loads(m).get('interval_sec') if m else None) for _, _, _, _, m in rows}, key=str))
print("  meta.fixed_price_buy 분포:",
      {k: sum(1 for *_, m in rows if (json.loads(m).get('fixed_price_buy') if m else None) == k) for k in (True, False, None)})
