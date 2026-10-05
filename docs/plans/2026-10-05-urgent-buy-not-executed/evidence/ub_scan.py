# 긴급 조사 (서버, 읽기 전용): audit_buy_eval overall_ok=1 (2026-10-02 ~ 지금) 전수 + 체결 분류 + 매수 없는 행 journal ±3분
import json, re, sqlite3, subprocess, csv, sys
from datetime import datetime, timedelta

DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
T = "KRW-JTO"
rows = c.execute("select id, bar_time, timestamp, interval_sec, price, checks, notes from audit_buy_eval "
                 "where ticker=? and overall_ok=1 and bar_time >= '2026-10-02T00:00' order by bar_time", (T,)).fetchall()
out = []
for rid, bt, ts, iv, price, ck, notes in rows:
    try:
        reason = (json.loads(ck) or {}).get("reason") if ck else None
    except Exception:
        reason = "?"
    iv = int(iv or 300)
    b0 = datetime.fromisoformat(bt)
    lo, hi = b0.isoformat(), (b0 + timedelta(seconds=iv * 3)).isoformat()   # 봉 시작 ~ 뒤 2봉 마감
    od = c.execute("select id, timestamp, state, executed_volume, avg_price, executed_at, canceled_at from orders "
                   "where ticker=? and side='BUY' and timestamp >= ? and timestamp <= ? order by id", (T, lo, hi)).fetchall()
    at = c.execute("select id, timestamp, price, reason from audit_trades where ticker=? and type='BUY' and timestamp >= ? and timestamp <= ? order by id",
                   (T, lo, hi)).fetchall()
    if any(o[2] == "FILLED" for o in od) or at:
        cls = "체결"
    elif od:
        cls = "요청 후 취소" if all(o[2] == "CANCELED" for o in od) else "요청(" + ",".join(o[2] or "?" for o in od) + ")"
    else:
        cls = "요청 없음"
    out.append(dict(id=rid, bar_time=bt, eval_ts=ts, interval_sec=iv, price=price, reason=reason, notes=notes,
                    orders=";".join(f"{o[0]}:{o[2]}:{o[1][11:19]}" for o in od), audit_buy=";".join(f"{a[0]}:{a[3]}:{a[1][11:19]}" for a in at), cls=cls))

w = csv.DictWriter(sys.stdout, fieldnames=list(out[0].keys()) if out else ["id"])
print("=== CSV ===")
w.writeheader()
for r in out:
    w.writerow(r)
print("=== 요약 ===")
from collections import Counter
print("전체", len(out), dict(Counter(r["cls"] for r in out)))
d4 = [r for r in out if r["bar_time"].startswith("2026-10-04")]
print("10-04", len(d4), dict(Counter(r["cls"] for r in d4)))

PAT = (r"EMA Buy Signal|action=BUY|급등|surge|Surge|SlowEmaSurge|BUY_FILTER|Buy Filter|매수 차단|KRW|주문 비율|order_ratio|buy_amount|가용|"
       r"FIXED-PRICE|현재가 매수|BUY-LIMIT|UPBIT-ORDER|LIMIT-FILL|취소|cancel|REJECT|insufficient|has_position|pos=True|pos=False|"
       r"PENDING|pending|매수 미실행|매수 스킵|skip|SKIP|HTS-DETECT|POSITION-SYNC|Bar#|CONFIRMED|BUY")
print("=== 매수 없는 행 journal ±3분 ===")
for r in out:
    if r["cls"] == "체결":
        continue
    t = datetime.fromisoformat(r["eval_ts"])
    s, e = (t - timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S"), (t + timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
    j = subprocess.run(["journalctl", "-u", "tradebot", "--since", s, "--until", e, "--no-pager", "-o", "short-iso", "-g", PAT],
                       capture_output=True, text=True).stdout.splitlines()
    print(f"##### id={r['id']} bar_time={r['bar_time']} eval={r['eval_ts']} cls={r['cls']} notes={r['notes']}")
    for l in j:
        l2 = re.sub(r"^.*(python|streamlit)\[[0-9]+\]: ", "", l)
        if "sync_all_positions cleared" in l2 or "ensure_settings_history" in l2 or "REST]" in l2 or "REST-SAFE" in l2:
            continue
        print("   ", l2[:260])
