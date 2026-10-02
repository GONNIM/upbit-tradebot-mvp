import sqlite3
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
T = "KRW-JTO"
print("== audit_trades BUY (KRW-JTO, 2026-10-01 이후)")
buys = c.execute("select id,timestamp,price,reason from audit_trades where ticker=? and type='BUY' and timestamp>='2026-10-01' order by id", (T,)).fetchall()
for b in buys:
    print("  ", b)
print("== 매수 체결 봉의 audit_buy_eval 행")
for bt in ("2026-10-01T14:10:00+09:00", "2026-10-02T03:35:00+09:00", "2026-10-02T07:55:00+09:00"):
    for r in c.execute("select id,bar_time,timestamp,overall_ok,substr(checks,1,60),notes from audit_buy_eval where ticker=? and bar_time=?", (T, bt)):
        print("  ", r)
