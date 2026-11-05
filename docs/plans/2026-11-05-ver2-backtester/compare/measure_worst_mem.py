"""1105-09 · 검증 지적 2: 1분봉 90일이 빈 칸 없이 가득 찬 최악의 경우(129,600봉) 메모리를 잰다.
바깥 연결 없음 — 가짜 업비트 응답(모든 칸에 봉)과 가짜 시계로 collect → serve → 처리기와 같은
JSON 직렬화(send_json compact)까지 한 프로세스에서 돌리고 최대 RSS 를 적는다.
실행: python3 docs/plans/2026-11-05-ver2-backtester/compare/measure_worst_mem.py
"""
import asyncio
import gc
import json
import resource
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from v2 import candles  # noqa: E402

MIN = 60_000
T0 = 1_793_865_600      # 2026-11-05 08:00 UTC(가짜 시계 시작)


def rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 1)   # macOS: 바이트


class Resp:
    def __init__(self, body):
        self.code = 200
        self.body = body
        self.headers = {"Remaining-Req": "group=candles; min=600; sec=9"}


class Clock:
    t = T0

    def now(self):
        return self.t

    async def sleep(self, dt):
        self.t += dt
        await asyncio.sleep(0)


async def fake_fetch(url, **kw):
    q = parse_qs(urlparse(url).query)
    count = int(q["count"][0])
    to = datetime.strptime(q["to"][0], "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1000
    first = (int(to) // MIN) * MIN
    if first == to:
        first -= MIN
    rows = []
    for k in range(count):
        t = first - k * MIN
        rows.append({"market": q["market"][0],
                     "candle_date_time_utc": datetime.fromtimestamp(t / 1000, timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%S"),
                     "opening_price": 1234.5, "high_price": 1240.25, "low_price": 1220.75,
                     "trade_price": 1236.125, "unit": 1})
    return Resp(json.dumps(rows).encode())


async def main():
    clock = Clock()
    with tempfile.TemporaryDirectory() as tmp:
        c = candles.Collector(fetch=fake_fetch, sleep=clock.sleep, now=clock.now,
                              data_dir_fn=lambda: tmp)
        out = {"maxrss_start_mb": rss_mb()}
        bars, n = await c.collect("KRW-JTO", 1, 90)
        out.update(requests=n, bars=len(bars), maxrss_after_collect_mb=rss_mb())
        del bars
        gc.collect()
        f = Path(tmp) / candles.STORE_DIR / "KRW-JTO_1.json"
        out["file_bytes"] = f.stat().st_size
        out["bytes_per_bar"] = round(out["file_bytes"] / max(1, out["bars"]), 1)
        kind, body = await c.serve("KRW-JTO", 1, 90)
        out.update(serve_kind=kind, serve_requests=body.get("requests"),
                   serve_bars=len(body.get("bars", [])), maxrss_after_serve_mb=rss_mb())
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))   # send_json compact
        out.update(response_bytes=len(text.encode("utf-8")), maxrss_after_encode_mb=rss_mb())
        print(json.dumps(out, ensure_ascii=False, indent=1))
        (Path(__file__).parent / "measure_worst_mem.json").write_text(json.dumps(out, indent=1),
                                                                      encoding="utf-8")


asyncio.run(main())
