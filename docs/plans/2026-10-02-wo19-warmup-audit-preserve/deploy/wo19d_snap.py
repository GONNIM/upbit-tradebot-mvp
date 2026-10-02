# WO-19 배포 (서버, 읽기 전용): 최근 bar_time 기준 audit_buy_eval / audit_sell_eval 스냅샷 (TSV)
import sqlite3, json
DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
for t, okcol in (("audit_buy_eval", "overall_ok"), ("audit_sell_eval", "triggered")):
    for rid, bt, ts, ok, ck, notes in c.execute(
            f"select id, bar_time, timestamp, {okcol}, checks, notes from {t} "
            f"where ticker='KRW-JTO' and bar_time >= '2026-10-01T16:00' order by bar_time"):
        try:
            st = (json.loads(ck) or {}).get("status") if ck else None
        except Exception:
            st = "?"
        print("\t".join(str(x) for x in (t, rid, bt, ts, ok, st, (notes or "").replace("\t", " ")[:60])))
