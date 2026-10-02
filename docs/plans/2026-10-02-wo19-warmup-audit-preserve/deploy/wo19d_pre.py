# WO-19 배포 0단계 (서버, 읽기 전용): 포지션 부재 확인 + 기준 행 기록
# Upbit 은 GET /v1/accounts 만 호출한다 (주문 생성·취소 없음)
import os, sys, uuid, json, sqlite3, jwt, requests
from datetime import datetime
from zoneinfo import ZoneInfo
os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")
if not ak:
    import tomllib
    s = tomllib.load(open(".streamlit/secrets.toml", "rb")); ak, sk = s["UPBIT_ACCESS"], s["UPBIT_SECRET"]
print("조회 시각", datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"))
tok = jwt.encode({"access_key": ak, "nonce": str(uuid.uuid4())}, sk)
r = requests.get("https://api.upbit.com/v1/accounts", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
print("Upbit /v1/accounts http", r.status_code)
data = r.json()
jto = [a for a in data if a.get("currency") == "JTO"] if isinstance(data, list) else data
print("Upbit JTO:", [{k: a.get(k) for k in ("currency", "balance", "locked", "avg_buy_price")} for a in jto] if isinstance(jto, list) else jto,
      "(행 없음 = 0)" if isinstance(jto, list) and not jto else "")

DB = "file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro"
c = sqlite3.connect(DB, uri=True)
print("account_positions KRW-JTO:",
      c.execute("select virtual_coin, virtual_coin_locked, entry_price, meta, updated_at from account_positions where ticker='KRW-JTO'").fetchall())
print("== 기준 행")
for rid in (75021, 75063):
    row = c.execute("select id, bar_time, timestamp, overall_ok, checks, notes from audit_buy_eval where id=?", (rid,)).fetchone()
    ck = json.loads(row[4]) if row[4] else {}
    print(f"id={row[0]} bar_time={row[1]} timestamp={row[2]} overall_ok={row[3]} checks.reason={ck.get('reason')} checks.status={ck.get('status')} notes={row[5]}")
