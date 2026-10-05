# 긴급 조사 보강 (서버, 읽기 전용): ① 76229 취소 로그·KRW·포지션 ② journal 매수 신호 전수와 감사 행 대조 ③ BUY 표시 행 전수
import json, re, sqlite3, subprocess
from datetime import datetime, timedelta

DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
T = "KRW-JTO"


def J(since, until, pat):
    return [re.sub(r"^.*(python|streamlit)\[[0-9]+\]: ", "", l) for l in subprocess.run(
        ["journalctl", "-u", "tradebot", "--since", since, "--until", until, "--no-pager", "-o", "short-iso", "-g", pat],
        capture_output=True, text=True).stdout.splitlines()]


print("== ① id 76229 / orders 559 취소 경위 (14:16 ~ 14:23)")
for l in J("2026-10-04 14:16:00", "2026-10-04 14:23:00",
           r"취소|cancel|CANCEL|FIXED-PRICE|LIMIT|timeout|미체결|final|Bar#33[2-9]|action=|has_position|PENDING|pending"):
    if "progress uuid" in l:
        continue
    print("   ", l[:250])
print("   orders 559:", c.execute("select id, timestamp, price, volume, state, executed_volume, canceled_at, updated_at, meta from orders where id=559").fetchone())
print("   직전 KRW 잔고(orders.current_krw 최근):", c.execute("select id, timestamp, side, current_krw, current_coin from orders where timestamp < '2026-10-04T14:16' and current_krw is not null order by id desc limit 1").fetchone())
print("   14:00~14:20 audit_trades:", c.execute("select id, timestamp, ticker, type, price, reason from audit_trades where timestamp between '2026-10-04T13:50' and '2026-10-04T14:25' order by id").fetchall())

print("\n== ② journal 'EMA Buy Signal' 전수 (2026-10-02 ~ 지금) ↔ audit_buy_eval")
sigs = J("2026-10-02 00:00:00", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), r"EMA Buy Signal|action=BUY")
for l in sigs:
    print("   ", l[:200])
print("\n== ③ audit_buy_eval 중 notes 에 'BUY' 가 들어간 행 / backfill 판정 (2026-10-02 ~)")
cols = [r[1] for r in c.execute("pragma table_info(audit_buy_eval)")]
print("   열:", cols)
bf = [x for x in ("backfill_overall_ok", "backfill_notes") if x in cols]
q = "select id, bar_time, timestamp, overall_ok, notes" + ("".join(", " + x for x in bf)) + \
    " from audit_buy_eval where ticker=? and bar_time >= '2026-10-02' and (notes like '%BUY%'" + \
    (" or backfill_overall_ok=1" if "backfill_overall_ok" in cols else "") + ") order by bar_time"
for r in c.execute(q, (T,)):
    print("   ", r)
print("   10-04 audit_buy_eval 행 수:", c.execute("select count(*), sum(overall_ok) from audit_buy_eval where ticker=? and bar_time between '2026-10-04' and '2026-10-05'", (T,)).fetchone())
