# WO-26 배포 0단계 (서버, 읽기 전용): KRW-JTO 포지션 두 곳 · 조건 파일 weak_entry 키·해시·mtime · settings_history · 봉 간격·EMA · 매수 가능 KRW
# Upbit 은 GET /v1/accounts 만 호출 (주문 생성·취소 없음). DB 는 mode=ro. 키 값 미출력.
# 사용: ssh root@orionhunter7.cafe24.com "cd /root/upbit-tradebot-mvp && python3 -" < wo26d_pre.py
import hashlib, json, os, sqlite3, uuid as _uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import jwt
import requests

os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")
KST = ZoneInfo("Asia/Seoul")
COND = "mcmax33_EMA_buy_sell_conditions.json"

print("조회 시각", datetime.now(KST).isoformat(timespec="seconds"))
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)

print("== KRW-JTO 포지션")
print("   account_positions (virtual_coin, locked, entry_price, meta, updated_at):",
      c.execute("select virtual_coin, virtual_coin_locked, entry_price, meta, updated_at from account_positions where ticker='KRW-JTO'").fetchall())
payload = {"access_key": ak, "nonce": str(_uuid.uuid4())}
r = requests.get("https://api.upbit.com/v1/accounts", headers={"Authorization": f"Bearer {jwt.encode(payload, sk)}"}, timeout=10)
data = r.json()
jto = [{k: a.get(k) for k in ("currency", "balance", "locked", "avg_buy_price")} for a in data if a.get("currency") == "JTO"] if isinstance(data, list) else data
krw = [{k: a.get(k) for k in ("currency", "balance", "locked")} for a in data if a.get("currency") == "KRW"] if isinstance(data, list) else data
print(f"   Upbit /v1/accounts http {r.status_code} JTO: {jto}" + (" (행 없음 = 0)" if jto == [] else ""))
print(f"   Upbit /v1/accounts KRW (매수 가능 = balance): {krw}")

print("== 조건 파일")
raw = open(COND, "rb").read()
st = os.stat(COND)
cond = json.loads(raw)
print(f"   {COND} sha256={hashlib.sha256(raw).hexdigest()} mtime={datetime.fromtimestamp(st.st_mtime, KST).isoformat(timespec='seconds')} size={st.st_size}")
wk = [k for k in list(cond.get("buy", {})) + list(cond.get("sell", {})) if k.startswith("weak_entry")]
print(f"   weak_entry 키: {wk if wk else '없음'}")
print(f"   buy: {cond.get('buy')}")

print("== settings_history")
print("   행 수 / 마지막 id:", c.execute("select count(*), max(id) from settings_history").fetchone())
last = c.execute("select id, saved_at, applied_at, source_page, json_extract(params_json,'$.interval'), json_extract(params_json,'$.fast_buy'), "
                 "json_extract(params_json,'$.slow_buy'), json_extract(params_json,'$.fast_sell'), json_extract(params_json,'$.slow_sell'), "
                 "json_extract(params_json,'$.order_ratio') from settings_history order by id desc limit 1").fetchone()
print("   마지막 행 (id, saved_at, applied_at, source, interval, fast_buy, slow_buy, fast_sell, slow_sell, order_ratio):", last)
try:
    p = json.load(open("mcmax33_latest_params_EMA.json", encoding="utf-8"))
    print(f"   params JSON: interval={p.get('interval')} fast_buy={p.get('fast_buy')} slow_buy={p.get('slow_buy')} fast_sell={p.get('fast_sell')} slow_sell={p.get('slow_sell')} order_ratio={p.get('order_ratio')}")
except Exception as e:
    print(f"   params JSON 읽기 실패 ({type(e).__name__})")

print("== 진행 중 주문 (orders REQUESTED/PARTIALLY_FILLED)")
print("  ", c.execute("select id, timestamp, ticker, side, state from orders where state in ('REQUESTED','PARTIALLY_FILLED') order by id").fetchall())
print("== 마지막 orders / audit_trades")
print("  ", c.execute("select id, timestamp, ticker, side, state from orders order by id desc limit 1").fetchone())
print("  ", c.execute("select id, timestamp, ticker, type, reason from audit_trades order by id desc limit 2").fetchall())
