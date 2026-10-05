# WO-21 B2 (서버, 읽기 전용): 보유 중 기동 2회(09-30 18:02:06, 19:44:28) 전후 trailing 상태
import sqlite3, subprocess
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
T = "KRW-JTO"
print("== 포지션 경과 (audit_trades 09-30 16:00 ~ 10-01 00:00)")
for r in c.execute("select id, timestamp, type, price, reason from audit_trades where ticker=? and timestamp between '2026-09-30T16:00' and '2026-10-01T00:00' order by id", (T,)):
    print("   ", r)
print("== audit_sell_eval (17:40~18:20, 19:30~20:05) — highest·ts_armed")
for a, b in (("2026-09-30T17:40", "2026-09-30T18:20"), ("2026-09-30T19:30", "2026-09-30T20:05")):
    for r in c.execute("select id, bar_time, timestamp, price, highest, ts_armed, triggered, trigger_key, substr(notes,1,60) from audit_sell_eval "
                       "where ticker=? and bar_time between ? and ? order by bar_time", (T, a, b)):
        print("   ", r)
    print("   --")
print("== invariant_snapshots (기동 전후 trailing_armed·highest_price)")
for a, b in (("2026-09-30 17:45", "2026-09-30 18:15"), ("2026-09-30 19:30", "2026-09-30 20:00")):
    for r in c.execute("select timestamp, has_position, qty, avg_price, entry_ts, trailing_armed, highest_price from invariant_snapshots "
                       "where ticker=? and timestamp between ? and ? order by id", (T, a, b)):
        print("   ", r)
    print("   --")
print("== journal: trailing·기동 관련 줄 (16:47 ~ 20:05)")
j = subprocess.run(["journalctl", "-u", "tradebot", "--since", "2026-09-30 16:47:00", "--until", "2026-09-30 20:05:00", "--no-pager", "-o", "short-iso",
                    "-g", r"Trailing Stop ACTIVATED|AUTO-SWITCH|TRAILING_STOP_(FIXED|RATIO)\]|고정 금액 폭|run_live_loop (start|종료)|BOOT-RESUME|POSITION-APPLY|POS-SYNC\] (avg_price|entry_ts)|BOOT-SEED|boot_seed_recover|HTS-DETECT\] HTS_BUY|TRAILING_STOP_CHECK|STOP_LOSS_CHECK"],
                   capture_output=True, text=True).stdout.splitlines()
import re
seen = {}
for l in j:
    s = re.sub(r"^.*(python|streamlit)\[[0-9]+\]: ", "", l)[:220]
    key = re.sub(r"[0-9]", "", s[20:90])
    seen[key] = seen.get(key, 0) + 1
    if seen[key] <= 3 or any(k in s for k in ("run_live_loop", "BOOT", "POSITION-APPLY", "ACTIVATED", "AUTO-SWITCH")):
        print("   ", s)
print("   (같은 형태 4번째부터 생략) 형태별 건수:", {k[:40]: v for k, v in seen.items() if v > 3})
