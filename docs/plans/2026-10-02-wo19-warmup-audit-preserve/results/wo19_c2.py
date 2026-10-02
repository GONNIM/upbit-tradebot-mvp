import sqlite3
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
U, T = "mcmax33", "KRW-JTO"
print("JTO BUY filled with executed_at set:",
      c.execute("select count(*), max(id) from orders where user_id=? and ticker=? and side='BUY' and executed_at is not null", (U, T)).fetchone())
print("JTO BUY filled executed_at null:",
      c.execute("select count(*) from orders where user_id=? and ticker=? and side='BUY' and executed_at is null and (state in ('completed','filled','FILLED') or (state='CANCELED' and executed_volume>0))", (U, T)).fetchone())
# exact replica of get_last_open_buy_order sql1 (services/db.py:1943)
sql1 = ("SELECT COALESCE(avg_price, price) as price, entry_bar, executed_at FROM orders "
        "WHERE user_id = ? AND ticker = ? AND side = 'BUY' AND (state IN ('completed', 'filled', 'FILLED') "
        "OR (state = 'CANCELED' AND executed_volume > 0)) ORDER BY executed_at , timestamp DESC, ROWID DESC LIMIT 1")
print("sql1 result:", c.execute(sql1, (U, T)).fetchone())
print("buy maxrowid / sell maxrowid:",
      c.execute("select max(rowid) from orders where user_id=? and ticker=? and side='BUY' and state in ('completed','filled','FILLED')", (U, T)).fetchone(),
      c.execute("select max(rowid) from orders where user_id=? and ticker=? and side='SELL' and state in ('completed','filled','FILLED')", (U, T)).fetchone())
