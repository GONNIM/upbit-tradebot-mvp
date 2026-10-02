import sqlite3, glob, json
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
T = "KRW-JTO"
cols = [r[1] for r in c.execute("pragma table_info(account_positions)")]
r = c.execute("select * from account_positions where ticker=?", (T,)).fetchone()
print("account_positions", dict(zip(cols, r)) if r else None)
print("last sell_eval", c.execute(
    "select id,bar_time,price,tp_price,sl_price,highest,ts_pct,ts_armed,bars_held,notes from audit_sell_eval "
    "where ticker=? order by id desc limit 2", (T,)).fetchall())
for f in sorted(glob.glob("/root/upbit-tradebot-mvp/**/*mcmax33*buy_sell*EMA*.json", recursive=True)):
    try:
        d = json.load(open(f))
        s = d.get("sell", d)
        print(f, {k: s.get(k) for k in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "stale_position_check", "stale_hours", "stale_threshold_pct")})
    except Exception as e:
        print(f, "err", e)
