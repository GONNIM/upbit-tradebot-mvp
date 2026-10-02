# WO-20 (서버, 읽기 전용): orders · account_positions 두 테이블만 SQL 로 표준출력 (mode=ro)
import sqlite3
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
for t in ("orders", "account_positions"):
    print(c.execute("select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()[0] + ";")
    cols = [r[1] for r in c.execute(f"pragma table_info({t})")]
    for row in c.execute(f"select * from {t}"):
        vals = []
        for v in row:
            if v is None:
                vals.append("NULL")
            elif isinstance(v, (int, float)):
                vals.append(repr(v))
            else:
                vals.append("'" + str(v).replace("'", "''") + "'")
        print(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(vals)});")
