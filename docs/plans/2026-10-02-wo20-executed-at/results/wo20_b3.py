# WO-20 B3 보강 (서버, 읽기 전용): updated_at 과 Upbit 실제 체결 시각 비교
# Upbit 은 GET /v1/order?uuid= 만 호출한다 (주문 생성·취소 없음)
import os, uuid as _uuid, hashlib, sqlite3, json, time
from datetime import datetime
from urllib.parse import urlencode, unquote
import jwt, requests

os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")


def get_order(u):
    params = {"uuid": u}
    q = unquote(urlencode(params)).encode()
    payload = {"access_key": ak, "nonce": str(_uuid.uuid4()),
               "query_hash": hashlib.sha512(q).hexdigest(), "query_hash_alg": "SHA512"}
    r = requests.get("https://api.upbit.com/v1/order", params=params,
                     headers={"Authorization": f"Bearer {jwt.encode(payload, sk)}"}, timeout=10)
    return r.status_code, r.json()


c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
FILT = ("user_id='mcmax33' and ticker='KRW-JTO' and side='BUY' and "
        "(state in ('completed','filled','FILLED') or (state='CANCELED' and executed_volume>0))")
over_ids = (250, 306, 309, 384, 396, 409)
print("== 차이 > interval_sec 6행의 state·executed_volume·volume")
for r in c.execute(f"select id, state, executed_volume, volume, requested_at, updated_at from orders where id in {over_ids}"):
    print("  ", r)

sample = c.execute(f"select id, state, provider_uuid, requested_at, updated_at from orders where {FILT} "
                   f"and provider_uuid is not null order by id desc limit 12").fetchall()
sample += c.execute(f"select id, state, provider_uuid, requested_at, updated_at from orders where id in {over_ids}").fetchall()
print("\n== Upbit 체결 시각 대조 (최근 12건 + 위 6건)")
print("  id | state | requested_at | 첫 체결 | 마지막 체결 | updated_at | updated-마지막체결(초)")
for oid, st, u, req, upd in sample:
    code, info = get_order(u)
    time.sleep(0.15)
    if code != 200 or not isinstance(info, dict):
        print(f"  {oid} http={code} {str(info)[:80]}")
        continue
    tr = info.get("trades") or []
    ts = sorted(t.get("created_at") for t in tr if t.get("created_at"))
    first, last = (ts[0], ts[-1]) if ts else (None, None)
    lag = None
    if last:
        lag = round((datetime.fromisoformat(upd) - datetime.fromisoformat(last)).total_seconds(), 1)
    print(f"  {oid} | {st} | {req[11:19]} | {first} | {last} | {upd[11:19]} | {lag}  (upbit state={info.get('state')}, trades={len(tr)})")
