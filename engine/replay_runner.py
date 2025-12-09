import pyupbit
from engine.params import load_params
from engine.live_loop import run_replay_on_dataframe

USER_ID = "mcmax33"

# LiveParams 그대로 가져옴 (실 운용이랑 같은 조건)
params = load_params(f"{USER_ID}_params.json")

# 과거 OHLCV (예: 5분봉 500개)
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute5", count=500)

result = run_replay_on_dataframe(
    params=params,
    df=df,
    user_id=USER_ID,
    strategy_type=params.strategy_type,   # 또는 "MACD" / "EMA" 문자열
)

trade_events = result["trade_events"]
df_bt = result["df_bt"]

# 여기서 df_bt.index[event["bar"]] 로 실제 봉 타임스탬프 찍어서
# 업비트 차트랑 1:1로 비교 가능
for evt in trade_events:
    ts = df_bt.index[evt["bar"]]
    print(ts, evt["type"], evt.get("reason"), evt.get("price"))
