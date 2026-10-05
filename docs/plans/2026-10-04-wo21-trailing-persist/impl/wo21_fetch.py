# WO-21: Upbit 공개 캔들(키 불필요) 조회 → JSON 저장. 사용: python3 wo21_fetch.py <unit분> <시작 KST> <끝 KST> <출력 경로>
import json, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
unit, start, end, out = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
s = datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
e = datetime.strptime(end, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
bars, to = {}, e.astimezone(timezone.utc)
while True:
    url = f"https://api.upbit.com/v1/candles/minutes/{unit}?market=KRW-JTO&count=200&to=" + to.strftime("%Y-%m-%dT%H:%M:%SZ")
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"accept": "application/json"}), timeout=15))
    if not d:
        break
    for c in d:
        t = datetime.strptime(c["candle_date_time_kst"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=KST)
        if s <= t < e:
            bars[t.isoformat()] = {"open": c["opening_price"], "high": c["high_price"], "low": c["low_price"],
                                   "close": c["trade_price"], "volume": c["candle_acc_trade_volume"]}
    oldest = min(datetime.strptime(c["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) for c in d)
    if oldest.astimezone(KST) <= s:
        break
    to = oldest
    time.sleep(0.15)
rows = [{"ts_kst": k, **v} for k, v in sorted(bars.items())]
json.dump({"market": "KRW-JTO", "unit_min": unit, "start_kst": start, "end_kst": end,
           "source": "GET https://api.upbit.com/v1/candles/minutes/{unit} (공개, 키 불필요)",
           "fetched_at": datetime.now(KST).isoformat(timespec="seconds"), "bars": rows},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(rows)}봉 → {out}  첫 {rows[0]['ts_kst'] if rows else '-'}  끝 {rows[-1]['ts_kst'] if rows else '-'}")
