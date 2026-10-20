"""WO-26 배포 2(b): 기동 [WARMUP] 의 '직전 D/C' 시각을 Upbit 공개 캔들로 독립 재계산 (읽기 전용, 키 불필요).

사용: python3 wo26d_dc_verify.py "<마지막 확정 봉 KST YYYY-MM-DD HH:MM>" <봉 분> <fast> <slow> [긴 기준 봉 수=2000]
- 확정 봉(마지막 봉까지)만 사용. to = UTC 'Z', 봉 시작 시각 기준 배타(WO-16 실측).
- A (봇 재현): 마지막 800봉 → IndicatorState.seed_long_history(timestamps) → last_dead_cross_ts (봇과 같은 함수)
- B (장기 기준): 긴 기준 봉 수 → seed_from_closes(처음 200) + 봉마다 update_incremental 후 매도 스냅샷으로 D/C 판정
  (strategy_incremental.on_bar 의 ema_dead_cross 와 같은 식) → 마지막 D/C, 그리고 마지막 800봉 창 안의 D/C 전부
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from core.indicator_state import IndicatorState  # noqa: E402

KST = timezone(timedelta(hours=9))
last_kst = datetime.strptime(sys.argv[1], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
unit, fast, slow = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
N = int(sys.argv[5]) if len(sys.argv) > 5 else 2000

bars, to = {}, (last_kst + timedelta(minutes=unit)).astimezone(timezone.utc)
calls = 0
while len(bars) < N:
    url = f"https://api.upbit.com/v1/candles/minutes/{unit}?market=KRW-JTO&count=200&to=" + to.strftime("%Y-%m-%dT%H:%M:%SZ")
    for attempt in range(6):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"accept": "application/json"}), timeout=15))
            break
        except Exception:
            time.sleep(1.0 + attempt)
    else:
        raise RuntimeError(url)
    calls += 1
    if not d:
        break
    for c in d:
        bars[c["candle_date_time_kst"]] = float(c["trade_price"])
    to = min(datetime.strptime(c["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S") for c in d).replace(tzinfo=timezone.utc)
    time.sleep(0.12)
keys = sorted(k for k in bars if k <= last_kst.strftime("%Y-%m-%dT%H:%M:%S"))[-N:]
ts = [datetime.strptime(k, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=KST) for k in keys]
cl = [bars[k] for k in keys]
print(f"봉 minute{unit} EMA {fast}/{slow} | 수집 {len(keys)}봉 ({calls}회) {keys[0]} ~ {keys[-1]}")


def mk():
    return IndicatorState(macd_fast=fast, macd_slow=slow, macd_signal=9, ema_fast=fast, ema_slow=slow, base_ema=200,
                          use_separate_ema=True, ema_fast_buy=fast, ema_slow_buy=slow, ema_fast_sell=fast, ema_slow_sell=slow)


a = mk()
assert a.seed_long_history(cl[-800:], base_len=200, timestamps=ts[-800:])
print(f"A 봇 재현 (800봉 seed_long_history): last_dead_cross_ts = {a.last_dead_cross_ts.strftime('%Y-%m-%d %H:%M') if a.last_dead_cross_ts else None} KST | "
      f"ema_fast={a.ema_fast_buy:.4f} ema_slow={a.ema_slow_buy:.4f}")

b = mk()
b.seed_from_closes(cl[:200], quiet=True)
dcs, gcs = [], []
for t, c in zip(ts[200:], cl[200:]):
    b.update_incremental(c)
    s = b.get_snapshot(is_buy_eval=False)
    if s["prev_ema_fast"] >= s["prev_ema_slow"] and s["ema_fast"] < s["ema_slow"]:
        dcs.append(t)
    if s["prev_ema_fast"] <= s["prev_ema_slow"] and s["ema_fast"] > s["ema_slow"]:
        gcs.append(t)
w0 = ts[-800]
print(f"B 장기 기준 ({len(keys)}봉 증분): 마지막 D/C = {dcs[-1].strftime('%Y-%m-%d %H:%M') if dcs else None} KST | "
      f"ema_fast={b.ema_fast_sell:.4f} ema_slow={b.ema_slow_sell:.4f}")
print(f"   800봉 창({w0:%m-%d %H:%M} ~) 안 D/C: {[t.strftime('%m-%d %H:%M') for t in dcs if t >= w0]}")
print(f"   800봉 창 안 G/C: {[t.strftime('%m-%d %H:%M') for t in gcs if t >= w0]}")
