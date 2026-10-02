"""WO-19 A2 (서버에서 실행, 읽기 전용): 최근 7일 audit_buy_eval/audit_sell_eval 의 WARMUP 행 중
'실제 판정 행이 덮인 것' 판정.
판정 근거 (journal):
  - 실시간 판정 존재: '[CONFIRMED] 봉 처리 완료 | ts=<KST>' (실시간 경로만 찍힘, BACKFILL 은 안 찍힘)
  - 덮어쓰기: '[AUDIT-UPDATE] {BUY|SELL} 실시간 재판정 | ... | bar_time=<ISO>' 가 그 실시간 판정보다 뒤에 있음
실행: ssh root@... 'python3 -' < wo19_a2.py
"""
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta

SINCE = "2026-09-25 00:00:00"
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"

j = subprocess.run(
    ["journalctl", "-u", "tradebot", "--since", SINCE, "--no-pager", "-o", "short-iso",
     "-g", r"CONFIRMED\] 봉 처리 완료|AUDIT-UPDATE\] (BUY|SELL) 실시간 재판정"],
    capture_output=True, text=True).stdout.splitlines()

confirmed = {}          # bar KST 'YYYY-mm-dd HH:MM' -> first realtime confirm log time
updates = {"BUY": {}, "SELL": {}}   # bar KST -> [log times]
re_c = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) .*\[CONFIRMED\] 봉 처리 완료 \| ts=(\d{4}-\d\d-\d\d \d\d:\d\d)")
re_u = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) .*\[AUDIT-UPDATE\] (BUY|SELL) 실시간 재판정 \| ticker=KRW-JTO \| bar_time=(\d{4}-\d\d-\d\dT\d\d:\d\d)")
for line in j:
    m = re_c.search(line)
    if m:
        confirmed.setdefault(m.group(2), m.group(1))
        continue
    m = re_u.search(line)
    if m:
        updates[m.group(2)].setdefault(m.group(3).replace("T", " "), []).append(m.group(1))

con = sqlite3.connect(DB, uri=True)
cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
for side, table in (("BUY", "audit_buy_eval"), ("SELL", "audit_sell_eval")):
    rows = con.execute(
        f"SELECT id, bar_time, timestamp, checks FROM {table} WHERE ticker='KRW-JTO' AND bar_time >= ? "
        f"AND checks LIKE '%\"status\": \"WARMUP\"%' ORDER BY bar_time", (cutoff,)).fetchall()
    total_7d = con.execute(f"SELECT COUNT(*) FROM {table} WHERE ticker='KRW-JTO' AND bar_time >= ?", (cutoff,)).fetchone()[0]
    overwritten, examples = 0, []
    for rid, bt, ts, _ in rows:
        k = bt[:16].replace("T", " ")
        c = confirmed.get(k)
        ups = updates[side].get(k, [])
        if c and any(u > c for u in ups):
            overwritten += 1
            if len(examples) < 5:
                examples.append((rid, k, c, [u for u in ups if u > c][0]))
    print(f"== {table} (KRW-JTO, bar_time >= {cutoff})")
    print(f"   전체 행 {total_7d} / checks.status=WARMUP {len(rows)} / 그중 실시간 판정 뒤 덮인 것(journal 확인) {overwritten}")
    for e in examples:
        print(f"   예: id={e[0]} bar={e[1]} 실시간 판정 {e[2]} → 워밍업 덮어쓰기 {e[3]}")
print(f"journal 범위 {SINCE} ~ / CONFIRMED 봉 {len(confirmed)} / BUY 재판정 봉 {len(updates['BUY'])} / SELL 재판정 봉 {len(updates['SELL'])}")
