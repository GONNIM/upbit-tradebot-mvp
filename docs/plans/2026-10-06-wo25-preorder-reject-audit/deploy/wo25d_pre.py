# WO-25 배포 0단계 (서버, 읽기 전용): 10-05 16:44:46 이후 이력 · KRW-JTO 포지션 · 사후 확인 9 선행 대조
# Upbit 은 GET /v1/accounts, GET /v1/order 만 호출 (주문 생성·취소 없음). DB 는 mode=ro. 키 값 미출력.
import os, uuid as _uuid, hashlib, sqlite3, time, jwt, requests
from datetime import datetime
from urllib.parse import urlencode, unquote
from zoneinfo import ZoneInfo

os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")


def get(path, params=None):
    payload = {"access_key": ak, "nonce": str(_uuid.uuid4())}
    if params:
        q = unquote(urlencode(params)).encode()
        payload.update({"query_hash": hashlib.sha512(q).hexdigest(), "query_hash_alg": "SHA512"})
    r = requests.get("https://api.upbit.com" + path, params=params,
                     headers={"Authorization": f"Bearer {jwt.encode(payload, sk)}"}, timeout=10)
    return r.status_code, r.json()


print("조회 시각", datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"))
c = sqlite3.connect("file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro", uri=True)
S0 = "2026-10-05T16:44:46"
print(f"== 10-05 16:44:46 이후 orders")
rows = c.execute("select id, timestamp, ticker, side, state, executed_volume, avg_price, executed_at, canceled_at, updated_at, provider_uuid "
                 "from orders where timestamp >= ? order by id", (S0,)).fetchall()
print(f"   건수: {len(rows)}")
for r in rows:
    print("   ", r[:10])
last = c.execute("select id, timestamp, ticker, side, state from orders order by id desc limit 1").fetchone()
print("   마지막 주문:", last)
print("== 10-05 16:44:46 이후 audit_trades")
for r in c.execute("select id, timestamp, ticker, type, price, reason from audit_trades where timestamp >= ? order by id", (S0,)):
    print("   ", r)

print("== settings_history")
print("   행 수 / 마지막 id:", c.execute("select count(*), max(id) from settings_history").fetchone())
print("   마지막 행:", c.execute("select id, created_at from settings_history order by id desc limit 1").fetchone() if "created_at" in [x[1] for x in c.execute("pragma table_info(settings_history)")] else c.execute("pragma table_info(settings_history)").fetchall())

print("== KRW-JTO 포지션")
print("   account_positions:", c.execute("select virtual_coin, virtual_coin_locked, entry_price, meta, updated_at from account_positions where ticker='KRW-JTO'").fetchall())
code, data = get("/v1/accounts")
jto = [{k: a.get(k) for k in ("currency", "balance", "locked", "avg_buy_price")} for a in data if a.get("currency") == "JTO"] if isinstance(data, list) else data
# ✅ WO-25 0단계: 매수 가능 KRW (balance = 가용, locked = 미체결 주문에 묶임)
krw = [{k: a.get(k) for k in ("currency", "balance", "locked")} for a in data if a.get("currency") == "KRW"] if isinstance(data, list) else data
print(f"   Upbit /v1/accounts KRW: {krw}")
try:
    _ratio = __import__("json").load(open("mcmax33_latest_params_EMA.json", encoding="utf-8")).get("order_ratio")
except Exception as _e:
    _ratio = f"읽기 실패 ({type(_e).__name__})"
print(f"   params order_ratio: {_ratio}")
print(f"   Upbit /v1/accounts http {code} JTO: {jto}" + (" (행 없음 = 0)" if jto == [] else ""))

print("== 사후 확인 9 선행 대조 (10-05 16:44:46 이후 확정 주문)")
done = [r for r in rows if r[4] in ("FILLED", "CANCELED")]
if not done:
    print("   해당 사건 없음")
for r in done:
    oid, ts, tk, side, st, vol, avg, ex, ca, upd, u = r
    code, info = get("/v1/order", {"uuid": u})
    time.sleep(0.15)
    tr = info.get("trades") or [] if isinstance(info, dict) else []
    lst = max((t.get("created_at") for t in tr if t.get("created_at")), default=None)
    diff = None
    if ex and lst:
        diff = (datetime.fromisoformat(ex) - datetime.fromisoformat(lst)).total_seconds()
    print(f"   id={oid} {side} {st} executed_at={ex} canceled_at={ca} | Upbit 마지막 체결={lst} (trades {len(tr)}) | 차이={diff}초")
