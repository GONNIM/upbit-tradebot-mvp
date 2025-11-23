import pyupbit
from config import ACCESS, SECRET

uuid = "여기에_로그에서_본_UUID_붙여넣기"  # 예: "674784a0-fab9-40d5-b0ae-a41fe02a3669"

up = pyupbit.Upbit(ACCESS, SECRET)

info = up.get_order(uuid)   # 📌 uuid로 바로 조회
print("=== RAW ORDER INFO ===")
print(info)

if info:
    print("state :", info.get("state"))             # wait / done / cancel
    print("side  :", info.get("side"))              # bid / ask
    print("ord_type:", info.get("ord_type"))        # price / market / limit
    print("vol   :", info.get("volume"))
    print("exec  :", info.get("executed_volume"))
    print("avg_px:", info.get("avg_price"))
    print("paid_fee:", info.get("paid_fee"))
