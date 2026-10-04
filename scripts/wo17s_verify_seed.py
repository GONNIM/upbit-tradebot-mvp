# 인자: <기동 [WARMUP] 시각 KST "YYYY-MM-DD HH:MM:SS"> <로그 ema_fast> <로그 ema_slow> [장기 기준 봉 수, 기본 1200]
#       [--interval minute1|minute5|…|숫자(분)] [--params <params JSON 경로>]
# 실행 예: python3 scripts/wo17s_verify_seed.py "2026-10-01 20:11:02" 734.9141 736.1272 1200 --interval minute5
# 판정 기준: 장기 기준 대비 EMA60·EMA200 차이 모두 0.1원 이내, fast−slow 부호가 같으면 통과 (WO-17 (S) 배포 검증)
"""WO-17 (S) 배포 검증용: 기동 시각 기준 장기 기준(확정 봉 1,200봉 이상) EMA60/EMA200 재계산.
사용: python3 wo17s_verify_seed.py "2026-10-0X HH:MM:SS"(기동 [WARMUP] 시각, KST) <log_fast> <log_slow> [bars=1200]
                                   [--interval minute5] [--params mcmax33_latest_params_EMA.json]
- 봉 간격: --interval 이 있으면 그 값, 없으면 params JSON 의 "interval" (기본 경로: 저장소 루트의
  mcmax33_latest_params_EMA.json). 읽은 값과 출처를 출력 첫 줄에 적는다.
  (2026-10-04: 운영이 1분봉으로 바뀌어 5분봉 고정 대조가 무효였던 사례로 인자화)
- Upbit 공개 캔들 API(키 불필요), to = UTC 'Z', 봉 시작 시각 기준 배타.
- 확정 봉(봉 시작 + 봉 간격 <= 기동 시각)만. 첫 200봉 SMA → 나머지 증분(구현과 같은 식).
- 같은 시각 800봉(구현 재현)도 함께 계산해 로그 값과 비교.
"""
import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DEFAULT_PARAMS = Path(__file__).resolve().parent.parent / "mcmax33_latest_params_EMA.json"

ap = argparse.ArgumentParser(description="WO-17 (S) 긴 이력 시드 검증")
ap.add_argument("boot", help='기동 [WARMUP] 시각 KST "YYYY-MM-DD HH:MM:SS"')
ap.add_argument("log_fast", type=float)
ap.add_argument("log_slow", type=float)
ap.add_argument("bars", type=int, nargs="?", default=1200, help="장기 기준 봉 수 (기본 1200)")
ap.add_argument("--interval", help="봉 간격: minute1 / minute5 / … 또는 분 단위 숫자")
ap.add_argument("--params", help=f"--interval 이 없을 때 읽을 params JSON (기본 {DEFAULT_PARAMS.name})")
args = ap.parse_args()


def _minutes(v) -> int:
    s = str(v).strip().lower()
    if s.startswith("minute"):
        s = s[len("minute"):]
    m = int(s)
    if m not in (1, 3, 5, 10, 15, 30, 60, 240):
        raise SystemExit(f"지원하지 않는 봉 간격: {v}")
    return m


if args.interval:
    MIN, src = _minutes(args.interval), "--interval 인자"
else:
    p = Path(args.params) if args.params else DEFAULT_PARAMS
    try:
        MIN, src = _minutes(json.load(open(p, encoding="utf-8"))["interval"]), f"params JSON {p}"
    except Exception as e:
        raise SystemExit(f"봉 간격을 정하지 못함 (--interval 로 지정하라): {p} → {e}")
print(f"봉 간격: minute{MIN} (출처: {src})")

boot = datetime.strptime(args.boot, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
log_fast, log_slow = args.log_fast, args.log_slow
N = args.bars

bars, to = {}, boot.astimezone(timezone.utc)
while len(bars) < N + 50:
    url = (f"https://api.upbit.com/v1/candles/minutes/{MIN}?market=KRW-JTO&count=200&to=" + to.strftime("%Y-%m-%dT%H:%M:%SZ"))
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"accept": "application/json"}), timeout=15))
    if not d:
        break
    for c in d:
        t = datetime.strptime(c["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        bars[t] = float(c["trade_price"])
    to = min(bars)
    time.sleep(0.15)
conf = [(t, c) for t, c in sorted(bars.items()) if t + timedelta(minutes=MIN) <= boot]


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
