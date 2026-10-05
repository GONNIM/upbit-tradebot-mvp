# WO-21 조사 (서버, 읽기 전용): A2 저장 실태 + B1~B3 재시작·보유·trailing 매도
import re, sqlite3, subprocess, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
T = "KRW-JTO"

print("== A2. account_positions 열과 meta 예시")
cols = [r[1] for r in c.execute("pragma table_info(account_positions)")]
print("   열:", cols)
for r in c.execute("select * from account_positions where ticker in ('KRW-JTO','KRW-ANKR','KRW-USDT') order by ticker"):
    print("   ", dict(zip(cols, r)))
print("   meta 값 종류(전체):", c.execute("select meta, count(*) from account_positions group by meta order by 2 desc limit 6").fetchall())
print("== A2. audit_sell_eval 의 trailing 관련 열 (10-02 08:00~09:30 보유 구간, 09:30 TRAILING_STOP_FIXED 매도)")
for r in c.execute("select id, bar_time, price, highest, ts_pct, ts_armed, triggered, trigger_key from audit_sell_eval "
                   "where ticker=? and bar_time between '2026-10-02T08:50' and '2026-10-02T09:26' order by bar_time", (T,)):
    print("   ", r)
print("   ts_armed 값 분포(전체):", c.execute("select ts_armed, count(*) from audit_sell_eval group by ts_armed").fetchall())
try:
    print("== A2. invariant_snapshots (system_health 표시용)")
    print("   행 수·기간:", c.execute("select count(*), min(timestamp), max(timestamp) from invariant_snapshots").fetchone())
    print("   trailing_armed=1 행 수:", c.execute("select count(*) from invariant_snapshots where trailing_armed=1").fetchone()[0])
    for r in c.execute("select timestamp, ticker, has_position, avg_price, trailing_armed, highest_price from invariant_snapshots "
                       "where trailing_armed=1 order by id desc limit 3"):
        print("   ", r)
except Exception as e:
    print("   invariant_snapshots 조회 실패:", e)

print("\n== B1. 최근 30일 엔진 기동 (journal) 과 KRW-JTO 보유 여부")
since = (datetime.now(KST) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
j = subprocess.run(["journalctl", "-u", "tradebot", "--since", since, "--no-pager", "-o", "short-iso",
                    "-g", r"run_live_loop start|BOOT-RESUME\] success|AUTO-RESUME\] (start|resume|success)|run_live_loop 종료"],
                   capture_output=True, text=True).stdout.splitlines()
first = subprocess.run(["journalctl", "-u", "tradebot", "--no-pager", "-o", "short-iso", "-n", "1", "-r", "--since", since, "--until", since[:10] + " 23:59:59"],
                       capture_output=True, text=True).stdout
jstart = subprocess.run(["bash", "-c", "journalctl -u tradebot --no-pager -o short-iso | head -1"], capture_output=True, text=True).stdout.strip()
print("   30일 기준:", since, "| journal 보존 시작:", jstart[:25])
starts = []
for l in j:
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", l)
    if not m:
        continue
    ts = datetime.fromisoformat(m.group(1)).replace(tzinfo=KST)
    kind = "run_live_loop start" if "run_live_loop start" in l else ("종료" if "종료" in l else ("BOOT-RESUME" if "BOOT-RESUME" in l else "AUTO-RESUME"))
    starts.append((ts, kind, l[l.find("|") + 2:][:80] if "|" in l else ""))
trades = c.execute("select timestamp, type, reason, price from audit_trades where ticker=? and timestamp >= ? order by timestamp",
                   (T, (datetime.now(KST) - timedelta(days=40)).isoformat())).fetchall()


def holding_at(ts):
    last = None
    for t, typ, reason, price in trades:
        if datetime.fromisoformat(t) <= ts and typ in ("BUY", "SELL"):
            last = (t, typ, reason, price)
    return last


restarts = [s for s in starts if s[1] == "run_live_loop start"]
print(f"   엔진 기동(run_live_loop start) {len(restarts)}회")
held = []
for ts, kind, _ in restarts:
    last = holding_at(ts)
    h = bool(last and last[1] == "BUY")
    if h:
        held.append((ts, last))
    print(f"   {ts:%Y-%m-%d %H:%M:%S} | 직전 JTO 거래: {last[0][:19] + ' ' + last[1] + ' ' + str(last[2]) if last else '없음'} | 보유: {'예' if h else '아니오'}")
print(f"   보유 중 기동: {len(held)}회")

print("\n== B3. 최근 30일 TRAILING_STOP 계열 매도와 재시작 여부")
tsells = c.execute("select timestamp, reason, price from audit_trades where ticker=? and type='SELL' and reason like 'TRAILING%' and timestamp >= ? order by timestamp",
                   (T, (datetime.now(KST) - timedelta(days=30)).isoformat())).fetchall()
n_sell = c.execute("select count(*) from audit_trades where ticker=? and type='SELL' and timestamp >= ?",
                   (T, (datetime.now(KST) - timedelta(days=30)).isoformat())).fetchone()[0]
print(f"   TRAILING 매도 {len(tsells)}건 (전체 SELL {n_sell}건)")
n_after_restart = 0
for t, reason, price in tsells:
    st = datetime.fromisoformat(t)
    buy = None
    for bt, typ, r, p in trades:
        if typ == "BUY" and datetime.fromisoformat(bt) <= st:
            buy = (bt, r, p)
    rs = [ts for ts, _, _ in restarts if buy and datetime.fromisoformat(buy[0]) < ts < st]
    if rs:
        n_after_restart += 1
    print(f"   {t[:19]} {reason} @{price} | 매수 {buy[0][:19] if buy else '?'} {buy[1] if buy else ''} @{buy[2] if buy else ''} | 사이 재시작: {[x.strftime('%m-%d %H:%M') for x in rs] or '없음'}")
print(f"   재시작 뒤 같은 포지션에서 나온 TRAILING 매도: {n_after_restart}건")
print("\n== (B2 용) 보유 중 기동 목록 원자료")
for ts, last in held:
    print("   ", ts.isoformat(), last)
