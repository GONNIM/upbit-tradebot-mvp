"""WO-26 1단계 측정 (읽기 전용 자료만 사용, 코드·DB·설정 무변경).

사용: python3 wo26m1_measure.py <scratchpad 폴더> <출력 폴더>
입력(scratchpad): wo26_m5.csv · wo26_m3.csv · wo26_m1.csv (wo26m1_fetch.py), wo26_export.txt (wo26m1_export.sh)
출력: wo26_events.csv (D/C·G/C 사건 목록), wo26_gc_outcomes.csv (G/C 별 결과), 표준 출력 요약 표

지표 계산: core.indicator_state.IndicatorState 를 live_loop 와 같은 인자로 만들고
  seed_from_closes(처음 200봉, quiet=True) → update_incremental(봉마다) 로 재생한다
  (seed_long_history 내부와 같은 순서. 구간 시작 시점 상태를 seed_long_history(800봉) 결과와 대조해 동일함을 확인).
교차 판정: strategy_incremental.EmaStrategy.on_bar 의 식 그대로 —
  G/C = 매수 스냅샷(get_snapshot(True)) prev_fast <= prev_slow and fast > slow
  D/C = 매도 스냅샷(get_snapshot(False)) prev_fast >= prev_slow and fast < slow
구간(설정 이력 settings_history 의 strategy_init 시각 기준, 운영 실제값):
  S1 minute5 60/200  ~ 2026-10-03 21:03:47
  S2 minute1 60/200  2026-10-03 21:03:47 ~ 2026-10-14 18:31:28
  S3 minute3 60/200  2026-10-14 18:31:28 ~ 2026-10-20 02:46:15
  S4 minute3 20/200  2026-10-20 02:46:15 ~ 수집 끝
  측정 창은 2026-09-20 00:00 이후 봉. 각 구간은 시작 전 1,000봉(200 SMA + 800 증분)으로 워밍업하고,
  워밍업 안의 D/C 도 "직전 D/C" 로 쓴다(구현안 B3 와 같은 범위: 워밍업 800봉).
  구간 안의 재기동(800봉 재시드)은 연속 계산으로 근사한다(800봉 시드는 장기 기준과 0.02원 이내, WO-17 G4).
결과("매수했다면"): 진입 = G/C 봉 종가.
  - 2시간 최고 수익률: 종가 기준(같은 봉 간격 종가, 봇 TP·TS 판정과 같은 기준)과 고가 기준(1분봉 고가) 두 가지
  - 0.5%·1.5% 도달: 2시간 안, 종가 기준 / 고가 기준
  - 다음 D/C 시점 수익률: 다음 D/C 봉 종가 (같은 구간 안에 없으면 공란)
  - 단순 모의(약매수 익절 축소): 봉 종가마다 손절(그 시각 적용 SL) → 익절 0.5% → D/C 순으로 확인, 먼저 걸린 것으로 청산
봇 실매수: audit_trades BUY EMA_GC 의 bar_time = G/C 봉 시각. 매도 = 그 다음 SELL/HTS_SELL 행.
"""
import bisect
import csv
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, ROOT)
from core.indicator_state import IndicatorState  # noqa: E402

S, OUTD = sys.argv[1], sys.argv[2]
FMT = "%Y-%m-%dT%H:%M:%S"
WIN0 = datetime(2026, 9, 20, 0, 0)
SEGS = [
    ("S1", 5, 60, 200, datetime(2026, 9, 18, 17, 26, 34), datetime(2026, 10, 3, 21, 3, 47)),
    ("S2", 1, 60, 200, datetime(2026, 10, 3, 21, 3, 47), datetime(2026, 10, 14, 18, 31, 28)),
    ("S3", 3, 60, 200, datetime(2026, 10, 14, 18, 31, 28), datetime(2026, 10, 20, 2, 46, 15)),
    ("S4", 3, 20, 200, datetime(2026, 10, 20, 2, 46, 15), datetime(2026, 10, 21, 0, 0, 0)),
]
# 손절 % (settings_history saved_at 기준 — 조건 저장은 SP5 hot reload 로 즉시 반영된다. 단순 모의용)
#   근거: 09-30 11:15 매수가 −2.73% 에서 손절(09-28 저장 3%), 10-19 매수 2건이 −1.2·−1.5% 손절(10-17 저장 1%).
#   applied_at(재기동 시각)으로 두면 이 실매매와 맞지 않는다.
SL_HIST = [
    (datetime(2026, 9, 18, 17, 26), 0.01), (datetime(2026, 9, 25, 12, 38), 0.015), (datetime(2026, 9, 28, 5, 16), 0.03),
    (datetime(2026, 9, 30, 15, 37), 0.007), (datetime(2026, 10, 1, 15, 10), 0.01), (datetime(2026, 10, 14, 18, 30), 0.03),
    (datetime(2026, 10, 17, 6, 16), 0.01), (datetime(2026, 10, 20, 2, 46), 0.005),
]
SIM_TPS = (0.003, 0.005, 0.01, 0.015)
WEAK_TP = 0.005
BINS = [(0, 0.5, "≤0.5h"), (0.5, 1, "0.5~1h"), (1, 2, "1~2h"), (2, 3, "2~3h"), (3, 6, "3~6h"), (6, 1e9, ">6h")]


def load(path):
    out = []
    for r in csv.DictReader(open(path)):
        out.append((datetime.strptime(r["ts_kst"], FMT), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out


BARS = {5: load(f"{S}/wo26_m5.csv"), 3: load(f"{S}/wo26_m3.csv"), 1: load(f"{S}/wo26_m1.csv")}
M1_TS = [b[0] for b in BARS[1]]

# ---- 서버 추출 ----
JBAR, TRADES, BUYEVAL, mode = {}, [], {}, None
for line in open(f"{S}/wo26_export.txt", encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("##"):
        mode = line[2:]
        continue
    if mode == "BAR":
        m = re.search(r"ts=(\S+ \S+)\+00:00 \| close=([\d.]+) \| ema_fast=([\d.]+) \| ema_slow=([\d.]+)", line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") + timedelta(hours=9)
            JBAR.setdefault(ts, []).append((float(m.group(3)), float(m.group(4))))
    elif mode == "TRADES":
        p = line.split("|")
        if len(p) >= 8:
            TRADES.append({"id": int(p[0]), "ts": datetime.strptime(p[1][:19], FMT), "bar_time": p[2][:19],
                           "type": p[3], "reason": p[4], "price": float(p[5]) if p[5] else None,
                           "entry": float(p[6]) if p[6] else None})
    elif mode == "BUYEVAL":
        p = line.split("|")
        if len(p) >= 7 and p[2]:
            BUYEVAL.setdefault(p[2][:19], []).append((p[3], p[4], p[5]))

# 포지션 보유 구간 (봇·앱 매수 모두): 열림 = BUY, 닫힘 = SELL/HTS_SELL
POS = []
open_ts = None
for t in TRADES:
    if t["type"] == "BUY" and open_ts is None:
        open_ts = t["ts"]
    elif t["type"] in ("SELL", "HTS_SELL") and open_ts is not None:
        POS.append((open_ts, t["ts"]))
        open_ts = None
if open_ts is not None:
    POS.append((open_ts, datetime(2100, 1, 1)))


def sl_at(t):
    v = SL_HIST[0][1]
    for ts, s in SL_HIST:
        if t >= ts:
            v = s
    return v


def make_state(fast, slow):
    # live_loop.py:730 과 같은 인자 (fast_period/slow_period = MACD 기간, ema_* = 매수·매도 별도)
    return IndicatorState(macd_fast=fast, macd_slow=slow, macd_signal=9, ema_fast=fast, ema_slow=slow, base_ema=200,
                          use_separate_ema=True, ema_fast_buy=fast, ema_slow_buy=slow, ema_fast_sell=fast, ema_slow_sell=slow)


def cross_flags(st):
    b, s = st.get_snapshot(is_buy_eval=True), st.get_snapshot(is_buy_eval=False)
    gc = (b["prev_ema_fast"] is not None and b["prev_ema_slow"] is not None
          and b["prev_ema_fast"] <= b["prev_ema_slow"] and b["ema_fast"] > b["ema_slow"])
    dc = (s["prev_ema_fast"] is not None and s["prev_ema_slow"] is not None
          and s["prev_ema_fast"] >= s["prev_ema_slow"] and s["ema_fast"] < s["ema_slow"])
    return gc, dc, b["ema_fast"], b["ema_slow"]


events, seg_rows, repro = [], {}, {}
for name, unit, fp, sp, t0, t1 in SEGS:
    step = timedelta(minutes=unit)
    bars = BARS[unit]
    pre = [b for b in bars if b[0] + step <= t0]
    stream = [b for b in bars if t0 < b[0] + step <= t1]
    warm = pre[-1000:]
    st = make_state(fp, sp)
    assert st.seed_from_closes([b[4] for b in warm[:200]], quiet=True)
    rows = []
    for k, b in enumerate(warm[200:] + stream):
        st.update_incremental(b[4])
        gc, dc, f, s_ = cross_flags(st)
        in_seg = b[0] + step > t0
        if not in_seg and k == len(warm) - 201:
            # 구간 시작 시점: seed_long_history(마지막 800봉) 와 같은지 대조
            chk = make_state(fp, sp)
            assert chk.seed_long_history([x[4] for x in warm[-800:]], base_len=200)
            repro[name + "_seed800_vs_1000"] = (round(st.ema_fast_buy - chk.ema_fast_buy, 4), round(st.ema_slow_buy - chk.ema_slow_buy, 4))
        rows.append((b, f, s_, gc, dc, in_seg))
        if gc or dc:
            events.append({"seg": name, "interval": f"minute{unit}", "periods": f"{fp}/{sp}", "ts": b[0],
                           "kind": "GC" if gc else "DC", "close": b[4], "fast": f, "slow": s_, "phase": "구간" if in_seg else "워밍업"})
    # journal Bar# 재현 대조 (구간 안, 0.03원 이내)
    n = ok = 0
    bad = []
    for b, f, s_, *_ in rows:
        if b[0] in JBAR and b[0] + step > t0:
            n += 1
            hit = any(abs(f - jf) <= 0.03 and abs(s_ - js) <= 0.03 for jf, js in JBAR[b[0]])
            ok += hit
            if not hit:
                bad.append(b[0])
    repro[name + "_barlog"] = f"{ok}/{n}"
    if bad:
        repro[name + "_barlog_mismatch_range"] = f"{bad[0]:%m-%d %H:%M} ~ {bad[-1]:%m-%d %H:%M}"
        repro[name + "_barlog_mismatch_after_10-01_20:11"] = sum(1 for t in bad if t >= datetime(2026, 10, 1, 20, 11))
    seg_rows[name] = (unit, rows)

events.sort(key=lambda e: (e["seg"], e["ts"]))


def hyp(seg, unit, rows, idx):
    """G/C 봉(rows[idx]) 종가 진입 '매수했다면' 결과."""
    step = timedelta(minutes=unit)
    b0 = rows[idx][0]
    entry, tclose = b0[4], b0[0] + step
    horizon = tclose + timedelta(hours=2)
    later = [r for r in rows[idx + 1:] if r[5]]
    win = [r for r in later if r[0][0] + step <= horizon]
    mx_close = max([(r[0][4] / entry - 1) for r in win], default=0.0)
    i0 = bisect.bisect_left(M1_TS, tclose)
    i1 = bisect.bisect_left(M1_TS, horizon)
    mx_high = max([(BARS[1][i][2] / entry - 1) for i in range(i0, i1)], default=0.0)
    nxt = next((r for r in later if r[4]), None)
    dc_ret = (nxt[0][4] / entry - 1) if nxt else None
    dc_ts = nxt[0][0] if nxt else None
    # 단순 모의: 손절 → 익절 tp → D/C (봉 종가)
    sl = sl_at(tclose)

    def sim_tp(tp):
        for r in later:
            c = r[0][4]
            if c <= entry * (1 - sl):
                return c / entry - 1, "SL"
            if c >= entry * (1 + tp):
                return c / entry - 1, f"TP{tp * 100:g}"
            if r[4]:
                return c / entry - 1, "DC"
        return None, "구간 끝"

    sims = {tp: sim_tp(tp) for tp in SIM_TPS}
    sim, sim_reason = sims[WEAK_TP]
    return {"entry": entry, "mx_close": mx_close, "mx_high": mx_high, "dc_ret": dc_ret, "dc_ts": dc_ts,
            "sl": sl, "sim": sim, "sim_reason": sim_reason, "sims": sims,
            "complete2h": bool(win) and horizon <= rows[-1][0][0] + step}


def bot_result(gc_ts, next_cross_ts=None):
    """정확히 같은 봉의 봇 G/C 매수. 없으면 다음 교차 전(최대 30분) 늦은 봇 G/C 매수를 '시드 차이' 로 붙인다
    (WO-17 (S) 배포 2026-10-01 20:11 전에는 200봉 SMA 시드라 봇 교차 봉이 장기 기준과 달랐다)."""
    key = gc_ts.strftime(FMT)
    gc_buys = [t for t in TRADES if t["reason"] == "EMA_GC" and t["type"] in ("BUY", "BUY_REJECTED")]
    buy = next((t for t in gc_buys if t["bar_time"] == key), None)
    late = None
    if not buy:
        lim = gc_ts + timedelta(minutes=30)
        if next_cross_ts is not None:
            lim = min(lim, next_cross_ts)
        buy = next((t for t in gc_buys if t["bar_time"] and gc_ts < datetime.strptime(t["bar_time"], FMT) < lim
                    and t["bar_time"] not in GC_KEYS), None)
        if buy:
            late = buy["bar_time"][11:16]
    if not buy:
        return None
    if buy["type"] == "BUY_REJECTED":
        return {"kind": "BUY_REJECTED", "id": buy["id"], "buy": buy["price"]}
    sell = next((t for t in TRADES if t["id"] > buy["id"] and t["type"] in ("SELL", "HTS_SELL")), None)
    adds = [t for t in TRADES if buy["id"] < t["id"] < (sell["id"] if sell else 10 ** 9) and t["reason"] == "HTS_BUY_ADD"]
    res = {"kind": f"BUY(시드 차이, 봇 교차 봉 {late})" if late else "BUY", "id": buy["id"], "buy": buy["price"], "adds": len(adds)}
    if sell:
        ent = sell["entry"] or buy["price"]
        res.update({"sell_id": sell["id"], "sell_reason": sell["reason"], "sell": sell["price"],
                    "ret": (sell["price"] / ent - 1) if sell["price"] else None,
                    "hold_min": round((sell["ts"] - buy["ts"]).total_seconds() / 60, 1)})
    return res


def why_no_buy(gc_ts, unit):
    key = gc_ts.strftime(FMT)
    ev = BUYEVAL.get(key)
    held = any(a <= gc_ts + timedelta(minutes=unit) <= b for a, b in POS)
    if ev:
        lab = {'["SURGE_FILTER"]': "급등 차단 필터", '["WARMUP_IN_PROGRESS"]': "워밍업 재생 중 평가(봇 미가동·기동 직후)",
               '["NO_SIGNAL"]': "NO_SIGNAL(봇 교차 봉 다름)"}
        keys = sorted({("평가 통과·주문 기록 없음(WO-25 전 주문 전 차단 추정)" if x[1] == "1" else lab.get(x[2], x[2])) for x in ev})
        return ",".join(keys) + (" / 포지션 보유" if held else "")
    return "포지션 보유(BUY 평가 없음)" if held else "BUY 평가 기록 없음"


GC_KEYS = {e["ts"].strftime(FMT) for e in events if e["kind"] == "GC" and e["phase"] == "구간"}
out = []
for name, unit, fp, sp, t0, t1 in SEGS:
    rows = seg_rows[name][1]
    last_dc = None
    for idx, (b, f, s_, gc, dc, in_seg) in enumerate(rows):
        if dc:
            last_dc = b[0]
        if not gc or not in_seg or b[0] < WIN0:
            continue
        el = (b[0] - last_dc).total_seconds() / 3600 if last_dc else None
        h = hyp(name, unit, rows, idx)
        br = bot_result(b[0], h["dc_ts"])
        out.append({
            "seg": name, "interval": f"minute{unit}", "periods": f"{fp}/{sp}", "gc_ts": b[0].strftime("%Y-%m-%d %H:%M"),
            "prev_dc_ts": last_dc.strftime("%Y-%m-%d %H:%M") if last_dc else "",
            "elapsed_h": round(el, 3) if el is not None else "",
            "bin": next(lbl for lo, hi, lbl in BINS if el is not None and lo < el <= hi) if el is not None and el > 0 else ("" if el is None else "≤0.5h"),
            "gap_fast_slow": round(f - s_, 4), "entry_close": h["entry"],
            "max2h_close_pct": round(h["mx_close"] * 100, 3), "max2h_high_pct": round(h["mx_high"] * 100, 3),
            "hit0.5_close": int(h["mx_close"] >= 0.005), "hit1.5_close": int(h["mx_close"] >= 0.015),
            "hit0.5_high": int(h["mx_high"] >= 0.005), "hit1.5_high": int(h["mx_high"] >= 0.015),
            "next_dc_ts": h["dc_ts"].strftime("%Y-%m-%d %H:%M") if h["dc_ts"] else "",
            "next_dc_ret_pct": round(h["dc_ret"] * 100, 3) if h["dc_ret"] is not None else "",
            "sim_sl_pct": h["sl"] * 100, "sim_weak_tp0.5_exit": h["sim_reason"],
            "sim_weak_tp0.5_ret_pct": round(h["sim"] * 100, 3) if h["sim"] is not None else "",
            **{f"sim_tp{tp * 100:g}_ret_pct": (round(h["sims"][tp][0] * 100, 3) if h["sims"][tp][0] is not None else "")
               for tp in SIM_TPS if tp != WEAK_TP},
            "window_2h_complete": int(h["complete2h"]),
            "bot": (br or {}).get("kind", "없음"), "bot_buy_id": (br or {}).get("id", ""), "bot_buy_price": (br or {}).get("buy", ""),
            "bot_sell_reason": (br or {}).get("sell_reason", ""), "bot_sell_price": round((br or {}).get("sell") or 0, 3) or "",
            "bot_ret_pct": round(br["ret"] * 100, 3) if br and br.get("ret") is not None else "",
            "bot_hold_min": (br or {}).get("hold_min", ""), "bot_hts_adds": (br or {}).get("adds", ""),
            "no_buy_reason": ("" if br and br["kind"].startswith("BUY") and br["kind"] != "BUY_REJECTED"
                              else "주문 전 차단(KRW 부족, audit BUY_REJECTED)" if br else why_no_buy(b[0], unit)),
        })

with open(f"{OUTD}/wo26_events.csv", "w", newline="") as fo:
    w = csv.writer(fo)
    w.writerow(["seg", "interval", "periods", "bar_ts_kst", "kind", "close", "ema_fast", "ema_slow", "fast_minus_slow", "phase"])
    for e in events:
        w.writerow([e["seg"], e["interval"], e["periods"], e["ts"].strftime("%Y-%m-%d %H:%M"), e["kind"], e["close"],
                    round(e["fast"], 4), round(e["slow"], 4), round(e["fast"] - e["slow"], 4), e["phase"]])
with open(f"{OUTD}/wo26_gc_outcomes.csv", "w", newline="") as fo:
    w = csv.DictWriter(fo, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

# ---- 요약 ----
print("재현:", json.dumps(repro, ensure_ascii=False))
print("사건 수(구간 안·측정 창):", {n: sum(1 for e in events if e["seg"] == n and e["phase"] == "구간" and e["ts"] >= WIN0) for n, *_ in SEGS},
      "G/C:", len(out))


def summ(rs, label):
    if not rs:
        print(f"{label}: 0건")
        return
    mc = [r["max2h_close_pct"] for r in rs]
    mh = [r["max2h_high_pct"] for r in rs]
    dcr = [r["next_dc_ret_pct"] for r in rs if r["next_dc_ret_pct"] != ""]
    sim = [r["sim_weak_tp0.5_ret_pct"] for r in rs if r["sim_weak_tp0.5_ret_pct"] != ""]
    bot = [r["bot_ret_pct"] for r in rs if r["bot_ret_pct"] != ""]
    f = lambda xs: f"{statistics.mean(xs):+.3f}/{statistics.median(xs):+.3f}" if xs else "-"
    print(f"{label}: n={len(rs)} | 2h최고(종가) 평균/중앙 {f(mc)} | 2h최고(고가) {f(mh)} | "
          f"0.5%도달 종가 {sum(r['hit0.5_close'] for r in rs)}/{len(rs)} 고가 {sum(r['hit0.5_high'] for r in rs)}/{len(rs)} | "
          f"1.5%도달 종가 {sum(r['hit1.5_close'] for r in rs)}/{len(rs)} 고가 {sum(r['hit1.5_high'] for r in rs)}/{len(rs)} | "
          f"다음DC {f(dcr)} (n={len(dcr)}) | 모의TP0.5 {f(sim)} (n={len(sim)}) | 봇실매수 {f(bot)} (n={len(bot)})")


print("\n[구간별 경과 시간 분포]")
for name, *_ in SEGS:
    rs = [r for r in out if r["seg"] == name]
    print(name, {lbl: sum(1 for r in rs if r["bin"] == lbl) for *_, lbl in BINS}, "직전DC없음", sum(1 for r in rs if r["bin"] == ""))
print("전체", {lbl: sum(1 for r in out if r["bin"] == lbl) for *_, lbl in BINS})

print("\n[2시간 기준 비교]")
for name in ("ALL", "S1", "S2", "S3", "S4"):
    rs = out if name == "ALL" else [r for r in out if r["seg"] == name]
    summ([r for r in rs if r["elapsed_h"] != "" and r["elapsed_h"] <= 2], f"{name} ≤2h")
    summ([r for r in rs if r["elapsed_h"] == "" or r["elapsed_h"] > 2], f"{name} >2h")

print("\n[경과 구간별]")
for lo, hi, lbl in BINS:
    summ([r for r in out if r["bin"] == lbl], lbl)

print("\n[단순 모의 — 익절 % 별 (손절 → 익절 → D/C, 봉 종가). '매수 안 함' = 0]")
for lbl, rs in (("≤2h", [r for r in out if r["elapsed_h"] != "" and r["elapsed_h"] <= 2]),
                (">2h", [r for r in out if r["elapsed_h"] == "" or r["elapsed_h"] > 2])):
    parts = []
    for tp in SIM_TPS:
        k = "sim_weak_tp0.5_ret_pct" if tp == WEAK_TP else f"sim_tp{tp * 100:g}_ret_pct"
        xs = [r[k] for r in rs if r[k] != ""]
        wins = sum(1 for x in xs if x > 0)
        parts.append(f"TP{tp * 100:g}%: 합 {sum(xs):+.2f} 평균 {statistics.mean(xs):+.3f} 중앙 {statistics.median(xs):+.3f} 이익 {wins}/{len(xs)}")
    print(lbl, " | ".join(parts))

print("\n[기준 시간 민감도 (이내 / 밖)]")
for th in (0.5, 1, 2, 3, 6):
    summ([r for r in out if r["elapsed_h"] != "" and r["elapsed_h"] <= th], f"≤{th}h")
    summ([r for r in out if r["elapsed_h"] == "" or r["elapsed_h"] > th], f">{th}h")
