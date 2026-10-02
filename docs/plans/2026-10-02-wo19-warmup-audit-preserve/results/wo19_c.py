import sqlite3, json
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
T = "KRW-JTO"
b = c.execute("select id,timestamp,price,qty from audit_trades where ticker=? and type='BUY' order by id desc limit 1", (T,)).fetchone()
print("last_buy_audit_trades", b)
print("sell_eval_since_buy(count,min_bar,max_bar)",
      c.execute("select count(*),min(bar_time),max(bar_time) from audit_sell_eval where ticker=? and timestamp>=?", (T, b[1])).fetchone())
cols = [r[1] for r in c.execute("pragma table_info(orders)")]
print("orders_cols", cols)
r = c.execute("select * from orders where ticker=? and side='BUY' order by id desc limit 1", (T,)).fetchone()
print("last_buy_order", dict(zip(cols, r)) if r else None)
try:
    m = c.execute("select meta from account_positions where ticker=?", (T,)).fetchall()
    print("account_positions.meta", m)
except Exception as e:
    print("account_positions err", e)
