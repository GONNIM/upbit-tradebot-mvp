"""WO-26 1단계: Upbit 공개 캔들 API(키 불필요) 수집. to = UTC 'Z', 봉 시작 시각 기준 배타(WO-16 실측).
출력(인자 1 = 출력 폴더): wo26_m5.csv, wo26_m3.csv, wo26_m1.csv — 열: ts_kst, open, high, low, close, volume
  m5: 2026-09-15 00:00 ~ 2026-10-04 00:00 KST (5분봉 운영 구간 + 800봉 이상 워밍업)
  m3: 2026-10-12 00:00 ~ 끝 (3분봉 운영 구간 10-14 18:31~ + 워밍업)
  m1: 2026-09-15 00:00 ~ 끝 (1분봉 운영 구간 10-03 21:03~10-14 18:31 + 전 구간 결과 측정용)
끝 = 인자 2 (KST "YYYY-MM-DD HH:MM"), 형성 중 봉은 제외(봉 시작 + 간격 <= 끝).
"""
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
OUT = sys.argv[1]
END = datetime.strptime(sys.argv[2], "%Y-%m-%d %H:%M").replace(tzinfo=KST)


def fetch(unit, start_kst, end_kst, out):
    rows, to = {}, end_kst.astimezone(timezone.utc)
    stop = start_kst.astimezone(timezone.utc)
    calls = 0
    while to > stop:
        url = (f"https://api.upbit.com/v1/candles/minutes/{unit}?market=KRW-JTO&count=200&to="
               + to.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, headers={"accept": "application/json"})
                d = json.load(urllib.request.urlopen(req, timeout=15))
                break
            except Exception:  # 429 등
                time.sleep(1.0 + attempt)
        else:
            raise RuntimeError(url)
        calls += 1
        if not d:
            break
        for c in d:
            rows[c["candle_date_time_kst"]] = (c["opening_price"], c["high_price"], c["low_price"],
                                               c["trade_price"], c["candle_acc_trade_volume"])
        to = min(datetime.strptime(c["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S") for c in d).replace(tzinfo=timezone.utc)
        time.sleep(0.12)
    s0 = start_kst.strftime("%Y-%m-%dT%H:%M:%S")
    step = timedelta(minutes=unit)
    keep = [k for k in sorted(rows)
            if k >= s0 and datetime.strptime(k, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=KST) + step <= end_kst]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_kst", "open", "high", "low", "close", "volume"])
        for k in keep:
            w.writerow([k, *rows[k]])
    print(out, len(keep), "calls", calls, keep[0], keep[-1])


fetch(5, datetime(2026, 9, 15, 0, 0, tzinfo=KST), min(END, datetime(2026, 10, 4, 0, 0, tzinfo=KST)), f"{OUT}/wo26_m5.csv")
fetch(3, datetime(2026, 10, 12, 0, 0, tzinfo=KST), END, f"{OUT}/wo26_m3.csv")
fetch(1, datetime(2026, 9, 15, 0, 0, tzinfo=KST), END, f"{OUT}/wo26_m1.csv")
