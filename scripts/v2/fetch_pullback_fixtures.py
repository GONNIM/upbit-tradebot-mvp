"""새 전략(PULLBACK) 원본 일치 시험용 업비트 확정 분봉을 받아 tests/fixtures/pullback/upbit_<이름>.json 으로 저장한다.

2차 T10 Step 0 (사용자 승인 1028-12). 로컬 맥에서만 실행한다. 업비트 공개 시세 조회(키 없음), 초당 2회 이하.
- 봉마다 {t,o,h,l,c,v}. t = 봉 시작 시각 = candle_date_time_utc 를 UTC 로 읽은 ms. timestamp 칸(마지막 체결 시각)은 쓰지 않는다.
- 페이지 경계 중복은 t 기준으로 하나만 남기고 오름차순 정렬. 형성 중(마지막) 봉은 뺀다. 빈 봉은 채우지 않는다(F6).
- 끝에 세트별 봉 수·고유 t 수·간격이 봉 단위 배수가 아닌 곳 수·KST−UTC 차(9h 여야 함)를 출력한다.
사용: python3 scripts/v2/fetch_pullback_fixtures.py <이름> <종목> <분 단위> <일수>
  예: python3 scripts/v2/fetch_pullback_fixtures.py a KRW-JTO 3 30
종료 코드: 0 저장함 · 1 오류 · 3 검사 실패(저장 안 함)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT_DIR = os.path.join(ROOT, "tests", "fixtures", "pullback")
BASE = "https://api.upbit.com/v1/candles/minutes/{unit}"
MIN_GAP_SEC = 0.5      # 초당 2회 이하
RETRIES = 3


def _utc_ms(s: str) -> int:
    # 업비트 시각 문자열에는 시간대 표시가 없다 → UTC 를 직접 붙인다(Issue #2)
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _get(url: str) -> list:
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < RETRIES - 1:
                time.sleep(2.0 * (i + 1))
                continue
            raise
        except urllib.error.URLError:
            if i < RETRIES - 1:
                time.sleep(2.0 * (i + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def fetch(market: str, unit: int, days: int) -> tuple[list[dict], dict]:
    now_ms = int(time.time() * 1000)
    step = unit * 60_000
    start_ms = now_ms - days * 86_400_000
    bars: dict[int, dict] = {}
    kst_diff_h = None
    to = None
    requests = 0
    raw_rows = 0
    last = 0.0
    while True:
        q = {"market": market, "count": 200}
        if to:
            q["to"] = to
        url = BASE.format(unit=unit) + "?" + urllib.parse.urlencode(q)
        wait = MIN_GAP_SEC - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        page = _get(url)
        requests += 1
        if not page:
            break
        oldest = None
        for x in page:
            t = _utc_ms(x["candle_date_time_utc"])
            if kst_diff_h is None:
                kst_diff_h = (_utc_ms(x["candle_date_time_kst"]) - t) / 3_600_000
            if t + step > now_ms:      # 형성 중 봉
                continue
            if t >= start_ms:
                raw_rows += 1          # 페이지 경계 중복 포함 행 수 — unique_t 와 다르면 중복이 있었음
                bars[t] = {"t": t, "o": float(x["opening_price"]), "h": float(x["high_price"]),
                           "l": float(x["low_price"]), "c": float(x["trade_price"]),
                           "v": float(x["candle_acc_trade_volume"])}
            oldest = t if oldest is None else min(oldest, t)
        if oldest is None or oldest < start_ms:
            break
        to = datetime.fromtimestamp(oldest / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = [bars[k] for k in sorted(bars)]
    gaps_bad = sum(1 for a, b in zip(out, out[1:]) if (b["t"] - a["t"]) % step != 0 or b["t"] <= a["t"])
    gaps_missing = sum(1 for a, b in zip(out, out[1:]) if b["t"] - a["t"] > step)
    stats = {"requests": requests, "raw_rows": raw_rows, "bar_count": len(out), "unique_t": len(bars),
             "gap_not_multiple": gaps_bad, "gap_missing_bars": gaps_missing, "kst_minus_utc_h": kst_diff_h}
    return out, stats


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__)
        return 1
    name, market, unit, days = argv[1], argv[2], int(argv[3]), int(argv[4])
    bars, st = fetch(market, unit, days)
    # 중복 행(raw_rows > unique_t)은 t 기준으로 하나만 남겼으므로 실패로 보지 않고 수만 출력한다
    print(f"[FIXTURE] {name} {market} {unit}m {days}d requests={st['requests']} raw_rows={st['raw_rows']} bars={st['bar_count']} "
          f"unique_t={st['unique_t']} gap_not_multiple={st['gap_not_multiple']} "
          f"gap_missing_bars={st['gap_missing_bars']} kst_minus_utc_h={st['kst_minus_utc_h']}")
    if st["gap_not_multiple"] != 0 or st["kst_minus_utc_h"] != 9 or not bars:
        print("[FIXTURE] 검사 실패 — 저장하지 않음")
        return 3
    os.makedirs(OUT_DIR, exist_ok=True)
    doc = {
        "meta": {
            "source": "upbit public candles (no key)",
            "url": BASE.format(unit=unit) + f"?market={market}&count=200&to=...",
            "market": market, "unit_min": unit, "days": days,
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fields": "t=봉 시작 UTC ms(candle_date_time_utc), o,h,l,c, v=candle_acc_trade_volume",
            "note": "형성 중 봉 제외, 빈 봉 채우지 않음, t 기준 중복 제거·오름차순",
            **st,
        },
        "bars": bars,
    }
    path = os.path.join(OUT_DIR, f"upbit_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[FIXTURE] saved {os.path.relpath(path, ROOT)} bytes={os.path.getsize(path)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as e:  # noqa: BLE001
        print(f"[FIXTURE] 오류 {type(e).__name__}: {e}")
        sys.exit(1)
