# WO-20 (로컬, 메모리 DB): get_last_open_buy_order 의 ORDER BY 가 executed_at 를 오름차순으로 정렬하는지,
# (가)만 적용됐을 때 어떤 행을 고르는지 재현한다. services/db.py:1889~1891 · 1943 과 같은 SQL 을 쓴다.
import sqlite3

cols = ("executed_at", "created_at", "ts", "timestamp")
table_cols = {"id", "user_id", "ticker", "side", "price", "avg_price", "entry_bar", "state",
              "executed_volume", "executed_at", "timestamp", "updated_at"}
order_keys = [c for c in cols if c in table_cols]
order_sql = " , ".join(order_keys) + " DESC, ROWID DESC"          # services/db.py:1891 그대로
ts_col_pick = next(c for c in cols if c in table_cols)            # services/db.py:1907~1910
sql1 = (f"SELECT COALESCE(avg_price, price) as price, entry_bar, {ts_col_pick} FROM orders "
        "WHERE user_id = ? AND ticker = ? AND side = 'BUY' AND (state IN ('completed', 'filled', 'FILLED') "
        f"OR (state = 'CANCELED' AND executed_volume > 0)) ORDER BY {order_sql} LIMIT 1")
print("ORDER BY 절:", order_sql)


def run(label, rows):
    c = sqlite3.connect(":memory:")
    c.execute("create table orders (id integer primary key, user_id, ticker, side, price, avg_price, entry_bar, "
              "state, executed_volume, executed_at, timestamp, updated_at)")
    c.executemany("insert into orders (user_id, ticker, side, price, avg_price, entry_bar, state, executed_volume, "
                  "executed_at, timestamp, updated_at) values ('u','KRW-JTO','BUY',?,?,?,'FILLED',1,?,?,?)", rows)
    print(f"[{label}] 결과 =", c.execute(sql1, ("u", "KRW-JTO")).fetchone())


old = [(700, 700, 100, None, "2026-09-01T10:00:00+09:00", "2026-09-01T10:00:02+09:00"),
       (710, 710, 200, None, "2026-09-15T10:00:00+09:00", "2026-09-15T10:00:02+09:00")]
new = (734, 734, 330, "2026-10-02T08:00:12+09:00", "2026-10-02T08:00:12+09:00", "2026-10-02T08:00:14+09:00")
run("현재: 전부 NULL, 최신=710", old)
run("(가)만: 최신 행만 executed_at 채움 (기대 734)", old + [new])
run("(가)+과거 보정: 전부 채움 (기대 734)", [(p, a, b, t, t, u) for (p, a, b, _, t, u) in old] + [new])
