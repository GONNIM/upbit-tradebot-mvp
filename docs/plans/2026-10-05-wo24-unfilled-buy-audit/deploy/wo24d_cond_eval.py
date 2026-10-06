# WO-24 배포 2(b) (서버, 읽기 전용): 운영 conditions JSON → 엔진과 같은 식으로 미체결 전환 켬/끔·허용 % 계산
#   - 파일은 읽기만 한다 (open 'rb'). config.py 는 import 하지 않고 ast 로 상수만 읽는다 (secrets 로드 등 부작용 없음).
#   - 엔진의 식 (core/strategy_engine.py convert_unfilled_limit_buy):
#       cond = engine.strategy.buy_conditions          # = _load_trade_conditions(...)["buy"] (engine/live_loop.py:803, :536)
#       enabled = bool(cond.get("fixed_price_unfilled_to_market", UNFILLED_TO_MARKET_DEFAULT))
#       max_gap = float(cond.get("fixed_price_convert_max_gap_pct", UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT))
#   - 경로 우선순위도 엔진과 같다: {user}_{EMA}_buy_sell_conditions.json → 없으면 {user}_buy_sell_conditions.json
import ast, hashlib, json, os
from datetime import datetime

R = "/root/upbit-tradebot-mvp"
os.chdir(R)


def fstat(p):
    b = open(p, "rb").read()
    return hashlib.sha256(b).hexdigest(), datetime.fromtimestamp(os.path.getmtime(p)).isoformat(sep=" "), len(b), b


consts = {}
for node in ast.parse(open("config.py", encoding="utf-8").read()).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        n = node.targets[0].id
        if n in ("UNFILLED_TO_MARKET_DEFAULT", "UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT"):
            consts[n] = ast.literal_eval(node.value)
print("config.py 상수 (ast):", consts)

main_path, legacy_path = "mcmax33_EMA_buy_sell_conditions.json", "mcmax33_buy_sell_conditions.json"
path = main_path if os.path.exists(main_path) else legacy_path
h0, m0, sz, raw = fstat(path)
print(f"사용 파일: {path} | sha256={h0} mtime={m0} size={sz}")
buy = (json.loads(raw.decode("utf-8")).get("buy", {}) or {})
print("buy 키 목록:", sorted(buy.keys()))
print("  fixed_price_unfilled_to_market 키 존재:", "fixed_price_unfilled_to_market" in buy,
      "| fixed_price_convert_max_gap_pct 키 존재:", "fixed_price_convert_max_gap_pct" in buy)

enabled = bool(buy.get("fixed_price_unfilled_to_market", consts["UNFILLED_TO_MARKET_DEFAULT"]))
max_gap = float(buy.get("fixed_price_convert_max_gap_pct", consts["UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT"]))
print(f"계산 결과: 미체결 시 시장가 전환 = {enabled} | 전환 허용 가격 차이 % = {max_gap}")
print("기대값 일치:", enabled is False and max_gap == 0.3)

h1, m1, _, _ = fstat(path)
print(f"실행 뒤 파일: sha256={h1} mtime={m1} | 변경 없음: {h0 == h1 and m0 == m1}")
