# 조회 전용: GET /v1/orders/closed (KRW-JTO, 10-05 09:30~11:10) — 주문 생성·취소 없음, 키 값 미출력
import os, uuid, hashlib, jwt, requests
from urllib.parse import urlencode, unquote
os.chdir("/root/upbit-tradebot-mvp")
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
ak, sk = os.getenv("UPBIT_ACCESS"), os.getenv("UPBIT_SECRET")


def get(path, params):
    q = unquote(urlencode(params, doseq=True)).encode()
    payload = {"access_key": ak, "nonce": str(uuid.uuid4()), "query_hash": hashlib.sha512(q).hexdigest(), "query_hash_alg": "SHA512"}
    r = requests.get("https://api.upbit.com" + path, params=params,
                     headers={"Authorization": f"Bearer {jwt.encode(payload, sk)}"}, timeout=10)
    return r.status_code, r.json()


for st in (["done"], ["cancel"]):
    code, data = get("/v1/orders/closed", {"market": "KRW-JTO", "states[]": st, "start_time": "2026-10-05T09:30:00+09:00",
                                            "end_time": "2026-10-05T11:10:00+09:00", "limit": 100, "order_by": "asc"})
    print("== state", st, "http", code)
    for o in (data if isinstance(data, list) else []):
        print("  ", o.get("created_at"), o.get("side"), o.get("ord_type"), "price", o.get("price"), "vol", o.get("volume"),
              "exec", o.get("executed_volume"), "funds?", o.get("executed_funds"), o.get("state"), o.get("uuid"))
    if not isinstance(data, list):
        print("  ", data)
