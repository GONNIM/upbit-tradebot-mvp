# 1분봉 전환 점검 A1 (서버, 읽기 전용): settings_history 10-03 21:03:47 전후 행과 바뀐 항목
import sqlite3, json
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
cols = [r[1] for r in c.execute("pragma table_info(settings_history)")]
print("settings_history 열:", cols)
rows = c.execute("select * from settings_history order by id desc limit 8").fetchall()
rows = [dict(zip(cols, r)) for r in rows][::-1]
for r in rows:
    short = {k: (v if not (isinstance(v, str) and len(v) > 80) else v[:80] + "…") for k, v in r.items()}
    print("--", short)


def flat(prefix, v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            flat(f"{prefix}.{k}" if prefix else k, x, out)
    else:
        out[prefix] = v


def parse(r):
    out = {}
    for k, v in r.items():
        if isinstance(v, str) and v[:1] in "{[":
            try:
                flat(k, json.loads(v), out)
                continue
            except Exception:
                pass
        out[k] = v
    return out


print("\n== 연속 행 사이 바뀐 항목 (id·시각 열 제외)")
skip = {"id", "created_at", "timestamp", "ts", "recorded_at", "valid_from", "valid_to", "snapshot_at"}
for a, b in zip(rows, rows[1:]):
    pa, pb = parse(a), parse(b)
    diff = {k: (pa.get(k), pb.get(k)) for k in sorted(set(pa) | set(pb)) if k not in skip and pa.get(k) != pb.get(k)}
    print(f"id {a.get('id')} → {b.get('id')}: {diff}")
