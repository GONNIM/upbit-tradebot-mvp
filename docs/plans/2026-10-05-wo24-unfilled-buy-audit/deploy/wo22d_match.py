# 상설 관찰 항목 (서버, 읽기 전용): 창 안 BUY 평가 통과(overall_ok=1)·SELL 평가 발동(triggered=1) 행 ↔ orders 1:1 대조
# 사용: ssh … "python3 - '<START KST>' '<END KST>'" < wo22d_match.py
import sqlite3, sys
from datetime import datetime, timedelta

S0, E0 = sys.argv[1].replace(" ", "T"), sys.argv[2].replace(" ", "T")
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
T = "KRW-JTO"


def classify(side, bt, iv):
    b0 = datetime.fromisoformat(bt)
    lo, hi = b0.isoformat(), (b0 + timedelta(seconds=int(iv or 60) * 3)).isoformat()
    od = c.execute("select id, state, timestamp from orders where ticker=? and side=? and timestamp >= ? and timestamp <= ? order by id",
                   (T, side, lo, hi)).fetchall()
    if any(o[1] == "FILLED" for o in od):
        k = "체결"
    elif od and all(o[1] == "CANCELED" for o in od):
        k = "취소"
    elif od:
        k = "요청(" + ",".join(str(o[1]) for o in od) + ")"
    else:
        k = "미요청"
    return k, ";".join(f"{o[0]}:{o[1]}" for o in od)


print(f"== 창 {S0} ~ {E0}")
rows = []
for kind, q in (("BUY 평가 통과", "select id, bar_time, timestamp, interval_sec, notes from audit_buy_eval where ticker=? and overall_ok=1 and timestamp between ? and ? order by id"),
                ("SELL 평가 발동", "select id, bar_time, timestamp, interval_sec, notes from audit_sell_eval where ticker=? and triggered=1 and timestamp between ? and ? order by id")):
    for rid, bt, ts, iv, notes in c.execute(q, (T, S0, E0)):
        k, od = classify("BUY" if kind.startswith("BUY") else "SELL", bt, iv)
        rows.append((kind, rid, bt, ts, (notes or "")[:50], od, k))
for r in rows:
    print("   ", " | ".join(str(x) for x in r))
for kind in ("BUY 평가 통과", "SELL 평가 발동"):
    sub = [r for r in rows if r[0] == kind]
    print(f"   {kind}: {len(sub)}행 · 체결 {sum(r[6]=='체결' for r in sub)} · 취소 {sum(r[6]=='취소' for r in sub)} · 미요청 {sum(r[6]=='미요청' for r in sub)}")
od_all = c.execute("select id, side, state, timestamp from orders where ticker=? and timestamp between ? and ? order by id", (T, S0, E0)).fetchall()
print(f"   창 안 orders 전체 {len(od_all)}건: {od_all}")
