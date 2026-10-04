# 1분봉 전환 점검 (서버, 읽기 전용): 같은 봉 CLOCK-CLOSE 중복의 처리 결과 (Bar# 중복 = 지표 이중 갱신 여부)
import re, subprocess
from datetime import datetime, timedelta

periods = [("2026-10-03 21:03:46", "2026-10-04 10:22:33"), ("2026-10-04 10:22:33", None),
           ("2026-10-02 10:03:18", "2026-10-03 21:02:34")]
for since, until in periods:
    cmd = ["journalctl", "-u", "tradebot", "--since", since, "--no-pager"] + (["--until", until] if until else [])
    lines = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
    close, bar, nt, clk = {}, {}, {}, {}
    for l in lines:
        m = re.search(r"\[CLOCK-CLOSE\] 봉 확정 감지 \| ts=(\d{4}-\d\d-\d\d \d\d:\d\d)", l)
        if m:
            close[m.group(1)] = close.get(m.group(1), 0) + 1
        m = re.search(r"\[CLOCK\] 봉 확정 \| closed=(\d{4}-\d\d-\d\d \d\d:\d\d)", l)
        if m:
            clk[m.group(1)] = clk.get(m.group(1), 0) + 1
        m = re.search(r"Bar#\d+ \| ts=(\d{4}-\d\d-\d\d \d\d:\d\d):00\+00:00", l)
        if m:
            k = (datetime.strptime(m.group(1), "%Y-%m-%d %H:%M") + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
            bar[k] = bar.get(k, 0) + 1
        m = re.search(r"\[CONFIRMED-NO-TRADE\] closed_ts=(\d{4}-\d\d-\d\d \d\d:\d\d)", l)
        if m:
            nt[m.group(1)] = nt.get(m.group(1), 0) + 1
    dups = sorted(k for k, v in close.items() if v > 1)
    print(f"== {since} ~ {until or '지금'}: 고유 봉 {len(close)}, 중복 봉 {len(dups)}, Bar# 2회 이상 봉 {sum(1 for v in bar.values() if v > 1)}")
    for k in dups:
        print(f"   {k}: CLOCK-CLOSE {close[k]} / [CLOCK] 봉 확정 {clk.get(k, 0)} / Bar# {bar.get(k, 0)} / NO-TRADE {nt.get(k, 0)}")
    for k, v in sorted(bar.items()):
        if v > 1:
            print(f"   !! Bar# 중복 {k}: {v}")
