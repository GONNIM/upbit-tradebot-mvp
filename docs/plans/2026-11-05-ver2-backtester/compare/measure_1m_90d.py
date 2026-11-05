"""1105-09 · plan.md 1-3′: 캔들 서버(v2/candles.Collector) 로 업비트 KRW-JTO 1분봉 90일을 한 번 받아
시간·요청 수·보관 파일 크기·최대 메모리(RSS)를 잰다. 공개 시세만(인증 없음), 보관은 임시 폴더.
실행: python3 docs/plans/2026-11-05-ver2-backtester/compare/measure_1m_90d.py
"""
import asyncio
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from v2 import candles  # noqa: E402


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        c = candles.Collector(data_dir_fn=lambda: tmp)
        rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        t0 = time.time()
        bars, n = await c.collect("KRW-JTO", 1, 90)
        took = time.time() - t0
        rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        f = Path(tmp) / candles.STORE_DIR / "KRW-JTO_1.json"
        size = f.stat().st_size
        # 다시 읽기(serve) — 요청 0~2회로 끝나야 한다
        t1 = time.time()
        kind, body = await c.serve("KRW-JTO", 1, 90)
        took2 = time.time() - t1
        rss2 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out = {
            "requests": n, "bars": len(bars), "seconds": round(took, 1),
            "file_bytes": size, "bytes_per_bar": round(size / max(1, len(bars)), 1),
            "maxrss_before_mb": round(rss0 / 1048576, 1),      # macOS ru_maxrss 는 바이트
            "maxrss_after_collect_mb": round(rss1 / 1048576, 1),
            "reget_kind": kind, "reget_requests": body.get("requests"), "reget_seconds": round(took2, 2),
            "maxrss_after_reget_mb": round(rss2 / 1048576, 1),
            "first": bars[0][0] if bars else None, "last": bars[-1][0] if bars else None,
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
        (Path(__file__).parent / "measure_1m_90d.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


asyncio.run(main())
