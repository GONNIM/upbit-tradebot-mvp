"""Task 4-0: 서버 업비트 시세 중계·보관(v2/candles.py) 시험.

업비트를 실제로 부르지 않는다. 가짜 fetch(업비트 응답 모양 200개·최신순)·가짜 시계·가짜 sleep 만 쓴다.
"""
import asyncio
import gzip
import json
import os
import re
import stat
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import tornado.httpclient
from tornado.testing import AsyncHTTPTestCase

from utils import v2_entry_token as et
from v2 import auth, candles, db
from v2.server import make_app

ROOT = Path(__file__).resolve().parents[2]
MIN = 60_000
DAY = 86_400
# 2026-10-26 00:00:30 UTC (봉 경계 + 30초)
T0 = datetime(2026, 10, 26, 0, 0, 30, tzinfo=timezone.utc).timestamp()


class FakeResp:
    def __init__(self, code, body=b"[]", headers=None):
        self.code = code
        self.body = body
        self.headers = headers or {}


class FakeUpbit:
    """업비트 캔들 응답 흉내: to(제외) 직전 200개 봉, 모든 칸에 체결 있음, 최신순."""

    def __init__(self, clock, sec=9):
        self.clock = clock
        self.sec = sec
        self.calls = []          # (url, kwargs)
        self.statuses = []       # 앞에서부터 하나씩 꺼내 쓰는 상태 코드
        self.hook = None         # 호출 직후 실행(n 번째 호출 번호를 받음)
        self.raise_exc = None
        self.close = 105.0

    async def fetch(self, url, **kw):
        self.calls.append((url, kw))
        if self.hook:
            self.hook(len(self.calls))
        await asyncio.sleep(0)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.statuses:
            code = self.statuses.pop(0)
            if code != 200:
                return FakeResp(code, b'{"error":{"name":"too_many"}}')
        q = parse_qs(urlparse(url).query)
        unit = int(re.search(r"/minutes/(\d+)", url).group(1))
        count = int(q["count"][0])
        to = datetime.strptime(q["to"][0], "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1000
        u = unit * MIN
        first = (int(to) // u) * u
        if first == to:
            first -= u
        rows = []
        for k in range(count):
            t = first - k * u
            dt = datetime.fromtimestamp(t / 1000, timezone.utc)
            rows.append({
                "market": q["market"][0],
                "candle_date_time_utc": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "opening_price": 100.0, "high_price": 110.0, "low_price": 90.0,
                "trade_price": self.close, "unit": unit,
            })
        hdr = {"Remaining-Req": "group=candles; min=600; sec=%d" % self.sec}
        return FakeResp(200, json.dumps(rows).encode(), hdr)


class Clock:
    def __init__(self, t=T0):
        self.t = t
        self.sleeps = []

    def now(self):
        return self.t

    async def sleep(self, dt):
        self.sleeps.append(dt)
        self.t += dt
        await asyncio.sleep(0)


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "services" / "data"
        self.data.mkdir(parents=True)
        # 허용 목록·설정 파일은 임시 폴더만 본다(저장소 실제 파일을 읽지 않게)
        self.allow = self.root / "allow"
        self.allow.write_text("", encoding="utf-8")
        old = (et.ALLOWLIST_PATH, db.REPO_ROOT)
        et.ALLOWLIST_PATH = self.allow
        db.REPO_ROOT = self.root
        self.addCleanup(lambda: (setattr(et, "ALLOWLIST_PATH", old[0]),
                                 setattr(db, "REPO_ROOT", old[1])))
        self.clock = Clock()
        self.up = FakeUpbit(self.clock)
        self.c = self.make()

    def make(self):
        return candles.Collector(fetch=self.up.fetch, sleep=self.clock.sleep,
                                 now=self.clock.now, data_dir_fn=lambda: self.data)

    def store(self, market="KRW-JTO", unit=1):
        return self.data / "v2_candles" / f"{market}_{unit}.json"

    def write_alive(self, pid, running=True, user="alice"):
        at = datetime.fromtimestamp(self.clock.t, db.KST).isoformat()
        (self.data / ".engine_alive.json").write_text(
            json.dumps({"at": at, "running": {user: running}, "pid": pid}), encoding="utf-8")

    async def drain(self, job):
        if job is not None and job.task is not None:
            await job.task


class TestValidate(unittest.TestCase):
    # (a)
    def test_bad_inputs(self):
        for args, field in ((("KRW-../x", "1", "30"), "market"),
                            (("BTCUSDT", "1", "30"), "market"),
                            (("KRW-JTO", "2", "30"), "unit"),
                            (("KRW-JTO", "1", "31"), "days"),
                            (("KRW-JTO", "1", "0"), "days"),
                            (("KRW-JTO", "x", "1"), "unit"),
                            ((None, "1", "1"), "market")):
            with self.assertRaises(candles.BadRequest) as cm:
                candles.validate(*args)
            self.assertEqual(cm.exception.field, field, args)

    def test_good_inputs(self):
        self.assertEqual(candles.validate(" krw-jto ", "240", "1"), ("KRW-JTO", 240, 1))


class TestCollect(Base):
    # (b)
    async def test_empty_30_days_216_requests(self):
        now_ms = self.clock.t * 1000
        bars, n = await self.c.collect("KRW-JTO", 1, 30)
        self.assertEqual(n, 216)
        self.assertEqual(len(self.up.calls), 216)
        self.assertLessEqual(len(bars), 43200)
        ts = [b[0] for b in bars]
        self.assertEqual(ts, sorted(set(ts)))
        self.assertTrue(all(t + MIN <= now_ms for t in ts))           # 형성 중 봉 제외
        self.assertTrue(all(t >= now_ms - 30 * DAY * 1000 for t in ts))
        self.assertEqual(bars[-1][1:], [100.0, 110.0, 90.0, 105.0])

    # (d)
    async def test_low_remaining_sec_sleeps_one_second(self):
        self.up.sec = 3
        await self.c.collect("KRW-JTO", 1, 1)
        self.assertTrue(any(s >= 1.0 for s in self.clock.sleeps), self.clock.sleeps)

    async def test_rate_spacing(self):
        await self.c.collect("KRW-JTO", 1, 1, rate=5.0)
        self.assertTrue(self.clock.sleeps)
        self.assertTrue(all(s <= 0.2 + 1e-6 for s in self.clock.sleeps))
        # 실제 요청 간격이 1/rate 이상(가짜 시계 기준)
        self.assertGreaterEqual(self.clock.t - T0, 0.2 * (len(self.up.calls) - 1) - 1e-6)

    # (e)
    async def test_429_cooldown_60(self):
        self.up.statuses = [429]
        with self.assertLogs("v2.candles", "WARNING") as lg:
            with self.assertRaises(candles.UpbitLimit) as cm:
                await self.c.collect("KRW-JTO", 1, 1)
        self.assertIn("[V2-CANDLES] status=429 market=KRW-JTO unit=1", "\n".join(lg.output))
        self.assertEqual(cm.exception.retry_after, 60)
        n = len(self.up.calls)
        self.clock.t += 30
        with self.assertRaises(candles.UpbitLimit) as cm:
            await self.c.collect("KRW-JTO", 1, 1)
        self.assertEqual(len(self.up.calls), n)
        self.assertEqual(cm.exception.retry_after, 30)
        self.clock.t += 31
        await self.c.collect("KRW-JTO", 1, 1)
        self.assertGreater(len(self.up.calls), n)

    # (f)
    async def test_418_halt_file_persists(self):
        self.up.statuses = [418]
        with self.assertLogs("v2.candles", "ERROR") as lg:
            with self.assertRaises(candles.UpbitBlocked):
                await self.c.collect("KRW-JTO", 1, 1)
        self.assertIn("[V2-CANDLES] status=418 HALT", "\n".join(lg.output))
        halt = self.data / "v2_candles" / ".halt.json"
        self.assertTrue(halt.exists())
        self.assertEqual(stat.S_IMODE(halt.stat().st_mode), 0o600)
        info = json.loads(halt.read_text(encoding="utf-8"))
        self.assertEqual(info["status"], 418)
        self.assertIn("at", info)
        self.assertLessEqual(len(info["body"]), 200)
        # 재시작 흉내: 새 Collector, 시간이 많이 흘러도 정지 유지
        self.clock.t += 7 * DAY
        c2 = self.make()
        n = len(self.up.calls)
        with self.assertRaises(candles.UpbitBlocked):
            await c2.collect("KRW-JTO", 1, 1)
        with self.assertRaises(candles.UpbitBlocked):
            await c2.serve("KRW-JTO", 1, 1)
        self.assertEqual(len(self.up.calls), n)
        halt.unlink()   # 운영자 해제
        await c2.collect("KRW-JTO", 1, 1)
        self.assertGreater(len(self.up.calls), n)

    # (g)
    async def test_pid_change_mid_collection(self):
        self.write_alive(100)
        await self.c.collect("KRW-JTO", 1, 1)   # 처음 값은 기준만
        self.assertEqual(len(self.up.calls), 8)
        self.clock.t += 2 * DAY
        self.write_alive(100)

        def hook(i):
            if i == 8 + 3:
                self.write_alive(200)
        self.up.hook = hook
        with self.assertRaises(candles.UpbitLimit) as cm:
            await self.c.collect("KRW-JTO", 1, 2)
        self.assertEqual(len(self.up.calls), 11)       # 바뀐 뒤 다음 fetch 0회
        self.assertEqual(cm.exception.retry_after, 300)
        saved = json.loads(self.store().read_text(encoding="utf-8"))["bars"]
        newest = max(b[0] for b in saved)
        self.assertGreaterEqual(newest, (self.clock.t - 3600) * 1000)  # 받은 봉 보관
        self.clock.t += 100
        with self.assertRaises(candles.UpbitLimit):
            await self.c.collect("KRW-JTO", 1, 2)
        self.assertEqual(len(self.up.calls), 11)
        self.clock.t += 201
        bars, _n = await self.c.collect("KRW-JTO", 1, 2)
        self.assertGreater(len(self.up.calls), 11)
        ts = [b[0] for b in bars]
        self.assertEqual(ts, sorted(set(ts)))
        self.assertGreater(len(bars), 2 * 1440 - 10)   # 빈 곳 없이 이어 받음

    async def test_pid_missing_or_broken_no_rest(self):
        (self.data / ".engine_alive.json").write_text("{broken", encoding="utf-8")
        await self.c.collect("KRW-JTO", 1, 1)
        (self.data / ".engine_alive.json").unlink()
        self.clock.t += DAY
        await self.c.collect("KRW-JTO", 1, 1)
        self.assertGreater(len(self.up.calls), 8)

    async def test_prefetch_loop_detects_pid_change(self):
        self.clock.t += 400
        self.write_alive(100)
        await self.c.prefetch_once()     # 기준(대상 없음: 허용 목록 비어 있음)
        self.write_alive(300)
        await self.c.prefetch_once()     # 변경 발견 → 쉼
        self.clock.t += 299
        n = len(self.up.calls)
        with self.assertRaises(candles.UpbitLimit) as cm:
            await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual(len(self.up.calls), n)
        self.assertEqual(cm.exception.retry_after, 1)

    # (j)
    async def test_store_permissions_eviction_trim(self):
        self.c.prefetch_targets = {("KRW-TGT", 1)}
        for m in ("KRW-TGT", "KRW-AAA", "KRW-BBB", "KRW-CCC"):
            await self.c.collect(m, 1, 1)
            self.clock.t += 10
        folder = self.data / "v2_candles"
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode) & 0o077, 0)
        for p in folder.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600, p.name)
        self.assertFalse(list(folder.glob("*.tmp")))
        await self.c.collect("KRW-DDD", 1, 1)
        names = sorted(p.name for p in folder.glob("KRW-*.json"))
        self.assertEqual(names, ["KRW-BBB_1.json", "KRW-CCC_1.json",
                                 "KRW-DDD_1.json", "KRW-TGT_1.json"])
        # 쓰기만이 아니라 「쓴(읽은)」 것도 최근으로 친다: BBB 를 다시 쓰면 CCC 가 가장 오래됨
        self.clock.t += 10
        await self.c.serve("KRW-BBB", 1, 1)
        self.clock.t += 10
        await self.c.collect("KRW-EEE", 1, 1)
        names = sorted(p.name for p in folder.glob("KRW-*.json"))
        self.assertEqual(names, ["KRW-BBB_1.json", "KRW-DDD_1.json",
                                 "KRW-EEE_1.json", "KRW-TGT_1.json"])

    async def test_trim_older_than_30_days(self):
        await self.c.collect("KRW-JTO", 1, 30)
        self.clock.t += 2 * DAY
        n = len(self.up.calls)
        await self.c.collect("KRW-JTO", 1, 30)
        self.assertLessEqual(len(self.up.calls) - n, 16)   # 새 봉 2일치만
        saved = json.loads(self.store().read_text(encoding="utf-8"))
        self.assertEqual((saved["market"], saved["unit"]), ("KRW-JTO", 1))
        self.assertGreaterEqual(min(b[0] for b in saved["bars"]),
                                (self.clock.t - 30 * DAY) * 1000 - MIN)

    # (k)
    async def test_request_headers_and_url(self):
        await self.c.collect("KRW-JTO", 3, 1)
        url, kw = self.up.calls[0]
        self.assertTrue(url.startswith(candles.UPBIT_URL.format(unit=3) + "?"))
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["market"], ["KRW-JTO"])
        self.assertEqual(q["count"], ["200"])
        self.assertTrue(q["to"][0].endswith("Z"))
        hdr = {k.lower(): v for k, v in kw.get("headers", {}).items()}
        self.assertEqual(hdr.get("accept"), "application/json")
        self.assertNotIn("origin", hdr)
        self.assertNotIn("authorization", hdr)
        self.assertEqual(kw.get("request_timeout"), 10)
        self.assertIs(kw.get("raise_error"), False)

    # (n)
    async def test_store_follows_db_data_dir(self):
        old = db.DATA_DIR
        self.addCleanup(setattr, db, "DATA_DIR", old)
        c = candles.Collector(fetch=self.up.fetch, sleep=self.clock.sleep, now=self.clock.now)
        a, b = self.root / "a", self.root / "b"
        a.mkdir()
        b.mkdir()
        db.DATA_DIR = a
        await c.collect("KRW-JTO", 1, 1)
        db.DATA_DIR = b
        await c.collect("KRW-JTO", 1, 1)
        self.assertTrue((a / "v2_candles" / "KRW-JTO_1.json").exists())
        self.assertTrue((b / "v2_candles" / "KRW-JTO_1.json").exists())


class TestServe(Base):
    # (c) 판정 부분
    async def test_recent_store_answers_inline(self):
        await self.c.collect("KRW-JTO", 1, 30)
        self.clock.t += 600
        n = len(self.up.calls)
        kind, body = await self.c.serve("KRW-JTO", 1, 30)
        self.assertEqual(kind, "ok")
        self.assertEqual(body["requests"], 1)
        self.assertEqual(len(self.up.calls), n + 1)
        self.assertEqual((body["market"], body["unit"], body["days"]), ("KRW-JTO", 1, 30))

    async def test_empty_store_starts_job(self):
        kind, body = await self.c.serve("KRW-JTO", 1, 30)
        self.assertEqual(kind, "running")
        self.assertEqual(body["job"], "running")
        self.assertEqual(body["progress"]["total"], 216)
        await self.drain(self.c.job)
        p = self.c.progress()
        self.assertFalse(p["active"])
        self.assertIsNone(p["error"])
        self.assertEqual((p["done"], p["total"]), (216, 216))
        kind, body = await self.c.serve("KRW-JTO", 1, 30)
        self.assertEqual(kind, "ok")

    # (h)
    async def test_busy_other_market_same_market_joins(self):
        kind, _ = await self.c.serve("KRW-AAA", 1, 30)
        self.assertEqual(kind, "running")
        job = self.c.job
        with self.assertRaises(candles.Busy) as cm:
            await self.c.serve("KRW-BBB", 1, 30)
        self.assertEqual(cm.exception.progress["market"], "KRW-AAA")
        kind, body = await self.c.serve("KRW-AAA", 1, 30)
        self.assertEqual(kind, "running")
        self.assertIs(self.c.job, job)
        await self.drain(job)

    # (i)
    async def test_user_preempts_prefetch(self):
        pre = self.c.start_job("KRW-AAA", 1, 30, kind="prefetch", rate=1.0)
        for _ in range(20):
            await asyncio.sleep(0)
        kind, _ = await self.c.serve("KRW-BBB", 1, 30)
        self.assertEqual(kind, "running")
        self.assertTrue(pre.task.done())
        aaa_calls = [u for u, _k in self.up.calls if "KRW-AAA" in u]
        self.assertGreater(len(aaa_calls), 0)
        self.assertLess(len(aaa_calls), 216)
        self.assertTrue(self.store("KRW-AAA").exists())          # 받은 부분 보관
        user = self.c.job
        self.assertEqual((user.kind, user.market), ("user", "KRW-BBB"))
        await self.drain(user)
        self.assertEqual(len([u for u, _k in self.up.calls if "KRW-AAA" in u]), len(aaa_calls))
        self.assertIsNone(self.c.progress()["error"])
        self.assertEqual(len([u for u, _k in self.up.calls if "KRW-BBB" in u]), 216)

    async def test_same_market_prefetch_switches_to_user_rate(self):
        pre = self.c.start_job("KRW-AAA", 1, 30, kind="prefetch", rate=1.0)
        for _ in range(10):
            await asyncio.sleep(0)
        kind, body = await self.c.serve("KRW-AAA", 1, 30)
        self.assertEqual(kind, "running")
        self.assertIs(self.c.job, pre)
        self.assertEqual(pre.rate, 5.0)
        self.assertEqual(pre.kind, "user")
        await self.drain(pre)

    # (l) 배경 작업 예외
    async def test_job_errors_into_progress(self):
        for exc in (OSError("down"), tornado.httpclient.HTTPClientError(599)):
            c = self.make()
            self.up.raise_exc = exc
            kind, _ = await c.serve("KRW-JTO", 1, 30)
            await self.drain(c.job)
            p = c.progress()
            self.assertFalse(p["active"])
            self.assertEqual(p["error"], "upbit_error", exc)
        self.up.raise_exc = None

    async def test_job_429_into_progress(self):
        self.up.statuses = [200, 429]
        await self.c.serve("KRW-JTO", 1, 30)
        await self.drain(self.c.job)
        p = self.c.progress()
        self.assertEqual((p["error"], p["retry_after"]), ("upbit_limit", 60))

    # (m)
    async def _prefetch_setup(self, running=True):
        self.allow.write_text("alice\n", encoding="utf-8")
        (self.root / "alice_active_strategy.txt").write_text("EMA\n", encoding="utf-8")
        (self.root / "alice_latest_params_EMA.json").write_text(
            json.dumps({"ticker": "ZRO", "interval": "minute1"}), encoding="utf-8")
        self.write_alive(100, running=running)

    async def test_prefetch_waits_300_seconds_after_start(self):
        await self._prefetch_setup()
        self.clock.t += 299
        self.write_alive(100)
        await self.c.prefetch_once()
        self.assertEqual(len(self.up.calls), 0)

    async def test_prefetch_needs_engine_alive(self):
        self.clock.t += 400
        await self._prefetch_setup(running=False)
        await self.c.prefetch_once()
        self.assertEqual(len(self.up.calls), 0)

    async def test_prefetch_runs_at_one_per_second(self):
        self.clock.t += 400
        await self._prefetch_setup()
        await self.c.prefetch_once()
        self.assertEqual(self.c.prefetch_targets, {("KRW-ZRO", 1)})
        self.assertEqual(len(self.up.calls), 216)
        self.assertTrue(all("market=KRW-ZRO" in u for u, _k in self.up.calls))
        self.assertTrue(any(abs(s - 1.0) < 1e-6 for s in self.clock.sleeps))
        last = self.c.progress()
        self.assertEqual((last["kind"], last["error"]), ("prefetch", None))
        # 다음 회는 새 봉만
        self.clock.t += 60
        self.write_alive(100)
        await self.c.prefetch_once()
        self.assertEqual(len(self.up.calls), 217)

    # ---- fix round 1 ----
    async def test_418_halt_file_write_fails_still_blocks(self):
        self.up.statuses = [418]
        with mock.patch.object(candles, "_atomic_write", side_effect=OSError("disk")):
            with self.assertLogs("v2.candles", "ERROR") as lg:
                with self.assertRaises(candles.UpbitBlocked):
                    await self.c.collect("KRW-JTO", 1, 1)
        text = "\n".join(lg.output)
        self.assertIn("[V2-CANDLES] status=418 HALT", text)
        self.assertIn("halt file write failed", text)
        self.assertFalse((self.data / "v2_candles" / ".halt.json").exists())
        n = len(self.up.calls)
        self.clock.t += DAY
        with self.assertRaises(candles.UpbitBlocked):
            await self.c.collect("KRW-JTO", 1, 1)
        with self.assertRaises(candles.UpbitBlocked):
            await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual(len(self.up.calls), n)

    async def test_overlap_overwrites_unconfirmed_close(self):
        await self.c.collect("KRW-JTO", 1, 1)
        saved = json.loads(self.store().read_text(encoding="utf-8"))["bars"]
        last_t = max(b[0] for b in saved)
        self.assertEqual(saved[-1][4], 105.0)
        self.up.close = 777.0                 # 확정 종가가 달라졌다고 흉내
        # 새 봉이 정확히 200개면 겹침 없이는 to=보관끝+200봉 1회가 [보관끝, …) 만 받아 마지막 봉을 다시 안 받는다
        self.clock.t += 200 * 60
        kind, body = await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual(kind, "ok")
        self.assertEqual(body["requests"], 2)
        saved = {b[0]: b for b in json.loads(self.store().read_text(encoding="utf-8"))["bars"]}
        self.assertEqual(saved[last_t][4], 777.0)
        self.assertEqual(saved[last_t - MIN][4], 777.0)

    async def test_overlap_same_request_count_for_few_new_bars(self):
        await self.c.collect("KRW-JTO", 1, 1)
        last_t = max(b[0] for b in json.loads(self.store().read_text(encoding="utf-8"))["bars"])
        self.up.close = 777.0
        self.clock.t += 60
        kind, body = await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual((kind, body["requests"]), ("ok", 1))   # 요청 수는 늘지 않음
        saved = {b[0]: b for b in json.loads(self.store().read_text(encoding="utf-8"))["bars"]}
        self.assertEqual(saved[last_t][4], 777.0)

    async def test_prefetch_loop_fills_targets_before_first_sleep(self):
        await self._prefetch_setup()
        await self.c.collect("KRW-ZRO", 1, 1)       # 엔진 종목 파일(가장 오래됨)
        self.clock.t += 10
        blocked = asyncio.get_running_loop().create_future()

        async def sleep(dt):
            if dt >= candles.PREFETCH_DELAY:
                await blocked                         # 루프는 첫 sleep 에서 멈춰 둔다
            else:
                await self.clock.sleep(dt)
        self.c.sleep = sleep
        task = asyncio.ensure_future(self.c.prefetch_loop())
        self.addCleanup(task.cancel)
        await asyncio.sleep(0)
        self.assertEqual(self.c.prefetch_targets, {("KRW-ZRO", 1)})
        for m in ("KRW-AAA", "KRW-BBB", "KRW-CCC", "KRW-DDD"):
            await self.c.collect(m, 1, 1)
            self.clock.t += 10
        folder = self.data / "v2_candles"
        self.assertTrue((folder / "KRW-ZRO_1.json").exists())
        self.assertFalse((folder / "KRW-AAA_1.json").exists())
        task.cancel()

    async def test_size_limit_never_deletes_prefetch_target(self):
        self.c.prefetch_targets = {("KRW-TGT", 1)}
        with mock.patch.object(candles, "MAX_TOTAL_BYTES", 1):
            for m in ("KRW-TGT", "KRW-AAA", "KRW-BBB"):
                await self.c.collect(m, 1, 1)
                self.clock.t += 10
        folder = self.data / "v2_candles"
        names = sorted(p.name for p in folder.glob("KRW-*.json"))
        self.assertEqual(names, ["KRW-BBB_1.json", "KRW-TGT_1.json"])

    # ---- 최종 검수 수정 2026-10-27 ----
    async def test_cached_only_served_during_cooldown(self):
        # 보관분이 기간을 덮어 업비트 요청이 0회면 쉼(엔진 재시작 300초·429 60초) 중에도 200
        await self.c.collect("KRW-JTO", 1, 1)
        n = len(self.up.calls)
        for until in (self.clock.t + candles.COOLDOWN_PID, self.clock.t + candles.COOLDOWN_429):
            self.c.cooldown_until = until
            kind, body = await self.c.serve("KRW-JTO", 1, 1)
            self.assertEqual((kind, body["requests"]), ("ok", 0))
            self.assertEqual((body["market"], body["unit"], body["days"]), ("KRW-JTO", 1, 1))
            ts = [b[0] for b in body["bars"]]
            self.assertEqual(ts, sorted(set(ts)))
            self.assertGreater(len(ts), 1400)
        self.assertEqual(len(self.up.calls), n)
        # 업비트를 불러야 하는 요청(새 봉 1개)은 여전히 429
        self.c.cooldown_until = self.clock.t + candles.COOLDOWN_PID
        self.clock.t += 60
        with self.assertRaises(candles.UpbitLimit):
            await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual(len(self.up.calls), n)

    async def test_cached_only_after_pid_change_but_not_during_halt(self):
        await self.c.collect("KRW-JTO", 1, 1)
        self.write_alive(100)
        self.c._observe_pid()
        self.write_alive(200)
        self.assertTrue(self.c._observe_pid())           # 300초 쉼
        kind, body = await self.c.serve("KRW-JTO", 1, 1)
        self.assertEqual((kind, body["requests"]), ("ok", 0))
        folder = self.data / "v2_candles"
        (folder / ".halt.json").write_text('{"status":418}', encoding="utf-8")
        with self.assertRaises(candles.UpbitBlocked):    # 418 정지 중에는 보관분도 내주지 않는다
            await self.c.serve("KRW-JTO", 1, 1)

    def test_load_reuses_parsed_rows(self):
        row = [1, 2, 3, 4, 5]
        data = {"covered": [0, 10], "bars": [row]}
        with mock.patch.object(candles.Path, "read_text", return_value="x"), \
                mock.patch.object(candles.json, "loads", return_value=data):
            bars, cov = self.c._load("KRW-JTO", 1)
        self.assertIs(bars[1], row)                      # 새 목록을 만들지 않는다
        self.assertEqual(row, [1, 2.0, 3.0, 4.0, 5.0])
        self.assertIsInstance(row[1], float)
        self.assertEqual(cov, [0, 10])
        for bad in ([[1, 2, 3]], [{"t": 1}], [[1, 2, 3, 4, "x"]]):
            with mock.patch.object(candles.Path, "read_text", return_value="x"), \
                    mock.patch.object(candles.json, "loads",
                                      return_value={"covered": [0, 10], "bars": bad}):
                self.assertEqual(self.c._load("KRW-JTO", 1), ({}, None), bad)

    async def test_prefetch_loop_first_at_300_then_every_600(self):
        # verifier 수정 2026-10-27: 첫 미리 받기는 기동 300초 뒤, 그 뒤 600초마다
        calls = []
        done = asyncio.get_running_loop().create_future()

        async def once():
            calls.append(self.clock.t - T0)
            if len(calls) == 3:
                done.set_result(None)
                await asyncio.Future()                # 루프를 여기서 멈춰 둔다
        self.c.prefetch_once = once
        task = asyncio.ensure_future(self.c.prefetch_loop())
        self.addCleanup(task.cancel)
        await asyncio.wait_for(done, 5)
        task.cancel()
        self.assertEqual(calls, [300, 900, 1500])

    def test_prefetch_every_600(self):
        self.assertEqual(candles.PREFETCH_EVERY, 600)
        self.assertEqual(candles.PREFETCH_DELAY, 300)

    async def test_prefetch_skips_when_halt_file_exists(self):
        self.clock.t += 400
        await self._prefetch_setup()
        folder = self.data / "v2_candles"
        folder.mkdir()
        (folder / ".halt.json").write_text('{"status":418}', encoding="utf-8")
        await self.c.prefetch_once()
        self.assertEqual(len(self.up.calls), 0)
        self.assertIsNone(self.c.job)


class HandlerTests(AsyncHTTPTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.static = d / "static"
        self.static.mkdir()
        self.data = d / "root" / "services" / "data"
        self.data.mkdir(parents=True)
        secret, allow = d / "secret", d / "allow"
        secret.write_bytes(os.urandom(48))
        allow.write_text("alice\n", encoding="utf-8")
        old = (et.SECRET_PATH, et.ALLOWLIST_PATH, db.REPO_ROOT, db.DATA_DIR)
        et.SECRET_PATH, et.ALLOWLIST_PATH = secret, allow
        db.REPO_ROOT, db.DATA_DIR = d / "root", self.data

        def restore():
            et.SECRET_PATH, et.ALLOWLIST_PATH, db.REPO_ROOT, db.DATA_DIR = old
        self.addCleanup(restore)
        self.clock = Clock()
        self.up = FakeUpbit(self.clock)
        super().setUp()

    def get_app(self):
        app = make_app(static_dir=self.static)
        self.col = candles.Collector(fetch=self.up.fetch, sleep=self.clock.sleep,
                                     now=self.clock.now)
        app.settings["candles"] = self.col
        return app

    def cookie(self):
        return {"Cookie": "%s=%s" % (auth.SESSION_COOKIE, auth.make_session("alice", "TEST"))}

    def get(self, path, **kw):
        headers = self.cookie()
        if kw.get("decompress_response") is False:
            # decompress_response=False 이면 시험 클라이언트가 Accept-Encoding 을 붙이지 않는다
            headers["Accept-Encoding"] = "gzip"
        r = self.fetch(path, headers=headers, **kw)
        return r

    def wait_job(self):
        job = self.col.job
        if job is not None:
            self.io_loop.run_sync(lambda: job.task)

    # (l)
    def test_no_session_401(self):
        r = self.fetch("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.assertEqual(r.code, 401)
        r = self.fetch("/v2/api/candles/progress")
        self.assertEqual(r.code, 401)
        self.assertEqual(self.up.calls, [])

    # (a) 처리기
    def test_bad_request_400(self):
        for q, field in (("market=KRW-../x&unit=1&days=1", "market"),
                         ("market=BTCUSDT&unit=1&days=1", "market"),
                         ("market=KRW-JTO&unit=2&days=1", "unit"),
                         ("market=KRW-JTO&unit=1&days=31", "days")):
            r = self.get("/v2/api/candles?" + q)
            self.assertEqual(r.code, 400, q)
            self.assertEqual(json.loads(r.body), {"error": "bad_request", "field": field})
        self.assertEqual(self.up.calls, [])

    # (c)
    def test_202_then_200_gzip(self):
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=30")
        self.assertEqual(r.code, 202)
        body = json.loads(r.body)
        self.assertEqual(body["job"], "running")
        self.assertEqual(body["progress"]["market"], "KRW-JTO")
        r = self.get("/v2/api/candles/progress")
        p = json.loads(r.body)
        self.assertEqual(set(p), {"active", "kind", "market", "unit", "done", "total",
                                  "error", "retry_after"})
        self.wait_job()
        p = json.loads(self.get("/v2/api/candles/progress").body)
        self.assertEqual((p["active"], p["error"]), (False, None))
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=30",
                     decompress_response=False)
        self.assertEqual(r.code, 200)
        self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
        body = json.loads(gzip.decompress(r.body))
        self.assertEqual(set(body), {"market", "unit", "days", "bars", "requests"})
        self.assertLessEqual(body["requests"], 2)
        ts = [b[0] for b in body["bars"]]
        self.assertEqual(ts, sorted(set(ts)))
        raw = gzip.decompress(r.body)
        self.assertFalse(b", " in raw)                   # 캔들 본문은 빈칸 없는 구분자
        self.assertFalse(b": " in raw)

    def test_busy_409(self):
        r = self.get("/v2/api/candles?market=KRW-AAA&unit=1&days=30")
        self.assertEqual(r.code, 202)
        r = self.get("/v2/api/candles?market=KRW-BBB&unit=1&days=30")
        self.assertEqual(r.code, 409)
        body = json.loads(r.body)
        self.assertEqual(body["error"], "busy")
        self.assertEqual(body["progress"]["market"], "KRW-AAA")
        self.wait_job()

    def test_429_and_503(self):
        self.up.statuses = [429]
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.wait_job()
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.assertEqual(r.code, 429)
        self.assertEqual(json.loads(r.body), {"error": "upbit_limit", "retry_after": 60})
        self.clock.t += 61
        self.up.statuses = [418]
        self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.wait_job()
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.assertEqual(r.code, 503)
        self.assertEqual(json.loads(r.body), {"error": "upbit_blocked"})

    def test_inline_upbit_error_502(self):
        # 보관분이 최근이면 처리기 안에서 바로 부른다 → 그때 오류는 502
        self.io_loop.run_sync(lambda: self.col.collect("KRW-JTO", 1, 1))
        self.clock.t += 120
        self.up.raise_exc = OSError("down")
        r = self.get("/v2/api/candles?market=KRW-JTO&unit=1&days=1")
        self.assertEqual(r.code, 502)
        self.assertEqual(json.loads(r.body), {"error": "upbit_error"})


class TestSourceRules(unittest.TestCase):
    def test_only_upbit_candle_url_and_no_auth(self):
        text = (ROOT / "v2" / "candles.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"https://[^\s\"']+", text),
                         ["https://api.upbit.com/v1/candles/minutes/{unit}"])
        self.assertIn('UPBIT_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"', text)
        for bad in ("Authorization", "/v1/accounts", "/v1/orders", "access_key"):
            self.assertNotIn(bad, text)
        self.assertNotIn("jwt", text.lower())

    def test_server_starts_prefetch_and_gzip(self):
        text = (ROOT / "v2" / "server.py").read_text(encoding="utf-8")
        serve = text.split("async def _serve")[1].split("\ndef ")[0]
        self.assertIn("prefetch_loop", serve)
        self.assertTrue(make_app().settings.get("compress_response"))


if __name__ == "__main__":
    unittest.main()
