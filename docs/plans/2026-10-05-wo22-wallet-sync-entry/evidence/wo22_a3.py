# WO-22 A3 (서버, 읽기 전용): 최근 30일 지갑 0 닫힘(Case 1)·지갑 동기화 외부 매수 복원(Case 2) 사건과 진입가 출처
import re, sqlite3, subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
since = (datetime.now(KST) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
j = subprocess.run(["journalctl", "-u", "tradebot", "--since", since, "--no-pager", "-o", "short-iso", "-g",
                    r"POSITION-SYNC\] (강제 포지션 종료|외부 매수 감지|자동 복구 성공|신뢰 가능한 진입가 없음)|HTS-DETECT\] HTS_BUY|Sell triggered by|\[SELL\] plan"],
                   capture_output=True, text=True).stdout.splitlines()
jstart = subprocess.run(["bash", "-c", "journalctl -u tradebot --no-pager -o short-iso | head -1"], capture_output=True, text=True).stdout[:25]
print(f"기간: {since} ~ (journal 보존 시작 {jstart})")
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
ev = []
for l in j:
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", l)
    if not m:
        continue
    t = m.group(1).replace("T", " ")
    s = re.sub(r"^.*(python|streamlit)\[[0-9]+\]: ", "", l)
    if "강제 포지션 종료" in s:
        q = re.search(r"qty=([0-9.]+)", s)
        ev.append((t, "지갑0 닫힘(Case1)", q.group(1) if q else ""))
    elif "자동 복구 성공" in s:
        src = re.search(r"source=([a-z_]+)", s); q = re.search(r"qty=([0-9.]+)", s); ep = re.search(r"entry_price=([0-9.]+)", s)
        ev.append((t, f"외부 매수 복원(Case2) source={src.group(1) if src else '?'}", f"qty={q.group(1) if q else ''} entry={ep.group(1) if ep else ''}"))
    elif "신뢰 가능한 진입가 없음" in s:
        ev.append((t, "외부 매수 복원 실패(진입가 없음)", ""))
    elif "HTS-DETECT] HTS_BUY" in s and "KRW-JTO" in s:
        a = re.search(r"avg_price=([0-9.]+)", s); d = re.search(r"Δ=([0-9.]+)", s)
        ev.append((t, "HTS 감지(OR)", f"Δ={d.group(1) if d else ''} avg={a.group(1) if a else ''}"))
    elif "Sell triggered by" in s:
        ev.append((t, "봇 매도 신호", s.split("Sell triggered by", 1)[1].strip()[:60]))
print("== 사건 목록 (KRW-JTO 엔진 로그)")
for e in ev:
    print("  ", " | ".join(e))
print("\n== Case2 복원 전후 audit_trades (각 복원 시각 ±3시간)")
for t, kind, info in ev:
    if kind.startswith("외부 매수 복원(Case2)"):
        ts = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        rows = c.execute("select id, timestamp, type, price, reason from audit_trades where ticker='KRW-JTO' and timestamp between ? and ? order by id",
                         ((ts - timedelta(hours=3)).isoformat(), (ts + timedelta(minutes=10)).isoformat())).fetchall()
        print(f"  [{t}] {kind} {info}")
        for r in rows:
            print("      ", r)
