# 인자: <기동 [WARMUP] 시각 KST "YYYY-MM-DD HH:MM:SS"> <로그 ema_fast> <로그 ema_slow> [장기 기준 봉 수, 기본 1200]
# 실행 예: python3 scripts/wo17s_verify_seed.py "2026-10-01 20:11:02" 734.9141 736.1272 1200
# 판정 기준: 장기 기준 대비 EMA60·EMA200 차이 모두 0.1원 이내, fast−slow 부호가 같으면 통과 (WO-17 (S) 배포 검증)
"""WO-17 (S) 배포 검증용: 기동 시각 기준 장기 기준(확정 봉 1,200봉 이상) EMA60/EMA200 재계산.
사용: python3 wo17s_verify_seed.py "2026-10-0X HH:MM:SS"(기동 [WARMUP] 시각, KST) <log_fast> <log_slow> [bars=1200]
- Upbit 공개 캔들 API(키 불필요), to = UTC 'Z', 봉 시작 시각 기준 배타.
- 확정 봉(봉 시작 + 5분 <= 기동 시각)만. 첫 200봉 SMA → 나머지 증분(구현과 같은 식).
- 같은 시각 800봉(구현 재현)도 함께 계산해 로그 값과 비교.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
boot = datetime.strptime(sys.argv[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
log_fast, log_slow = float(sys.argv[2]), float(sys.argv[3])
N = int(sys.argv[4]) if len(sys.argv) > 4 else 1200

bars, to = {}, boot.astimezone(timezone.utc)
while len(bars) < N + 50:
    url = ("https://api.upbit.com/v1/candles/minutes/1?market=KRW-JTO&count=200&to=" + to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"accept": "application/json"}), timeout=15))
    if not d:
        break
    for c in d:
        t = datetime.strptime(c["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        bars[t] = float(c["trade_price"])
    to = min(bars)
    time.sleep(0.15)
conf = [(t, c) for t, c in sorted(bars.items()) if t + timedelta(minutes=1) <= boot]


def seed(closes, base=200):
    out = {}
    for p in (60, 200):
        a = 2 / (p + 1)
        e = sum(closes[base - p:base]) / p          # seed_from_closes(first 200): 마지막 p개 SMA
        for c in closes[base:]:
            e = a * c + (1 - a) * e
        out[p] = e
    return out


long_ = seed([c for _, c in conf[-N:]])
s800 = seed([c for _, c in conf[-800:]])
print(f"마지막 확정 봉 KST: {conf[-1][0].astimezone(KST):%Y-%m-%d %H:%M}  bars_long={len(conf[-N:])}")
print(f"로그        fast={log_fast:.4f} slow={log_slow:.4f}")
print(f"800 재현    fast={s800[60]:.4f} slow={s800[200]:.4f}  (로그와 차이 {s800[60]-log_fast:+.4f} / {s800[200]-log_slow:+.4f})")
print(f"{N} 기준  fast={long_[60]:.4f} slow={long_[200]:.4f}  (로그와 차이 {long_[60]-log_fast:+.4f} / {long_[200]-log_slow:+.4f})")
