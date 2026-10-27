import { test } from "node:test";
import assert from "node:assert/strict";
import {
  upbitCandlesUrl, toAscending, createPoller, markFormingCandle, sma, toMarkers, maLines,
  createSharedRateGate, mergeCandles, visiblePeriods, zoom,
  parseFailedKeys, kstHm, kstMdHm, kstTick, clipMarkers, intervalToMinutes,
} from "../../../v2/static/chart.js";

test("upbitCandlesUrl", () => {
  assert.equal(
    upbitCandlesUrl("KRW-JTO", 3),
    "https://api.upbit.com/v1/candles/minutes/3?market=KRW-JTO&count=200");
});

test("upbitCandlesUrl appends encoded to=", () => {
  const u = upbitCandlesUrl("KRW-BTC", 1, "2026-10-26T00:00:00Z");
  assert.ok(u.includes("&to=2026-10-26T00%3A00%3A00Z"), u);
  assert.ok(u.includes("market=KRW-BTC") && u.includes("count=200"));
});

function memStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => { m.set(k, String(v)); } };
}

test("shared gate: two gates on one storage share the 10s window", () => {
  let now = 1_000_000;
  const st = memStorage();
  const a = createSharedRateGate(10000, st, "k", () => now);
  const b = createSharedRateGate(10000, st, "k", () => now);
  assert.equal(a.allow(), true);
  assert.equal(b.allow(), false);
  assert.equal(b.msUntilOpen(), 10000);
  now += 9999;
  assert.equal(b.allow(), false);
  now += 1;
  assert.equal(b.allow(), true);
  assert.equal(a.allow(), false);   // b 가 방금 열었다
});

test("shared gate: default key and works when storage throws", () => {
  let now = 5000;
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  const g = createSharedRateGate(10000, bad, undefined, () => now);
  assert.equal(g.allow(), true);
  assert.equal(g.allow(), false);
  now += 10000;
  assert.equal(g.allow(), true);
  const none = createSharedRateGate(10000, null, "k", () => now);   // 저장소 없음
  assert.equal(none.allow(), true);
  assert.equal(none.allow(), false);
});

test("shared gate: default key is v2.upbitGateAt; future/garbage stamps do not lock", () => {
  let now = 100_000;
  const st = memStorage();
  const g = createSharedRateGate(10000, st, undefined, () => now);
  g.allow();
  assert.equal(st.getItem("v2.upbitGateAt"), "100000");
  st.setItem("x", "garbage");
  const h = createSharedRateGate(10000, st, "x", () => now);
  assert.equal(h.allow(), true);
  st.setItem("y", String(now + 999_999));   // 시계가 되감긴 경우 영구 잠금 방지
  const i = createSharedRateGate(10000, st, "y", () => now);
  assert.equal(i.allow(), true);
});

test("mergeCandles: ascending, one per time, newer wins", () => {
  const c = (t, p) => ({ candle_date_time_utc: t, trade_price: p });
  const older = [c("2026-10-23T03:00:00", 1), c("2026-10-23T03:01:00", 2)];
  const newer = [c("2026-10-23T03:01:00", 9), c("2026-10-23T03:02:00", 3)];
  const out = mergeCandles(older, newer);
  assert.deepEqual(out.map((x) => x.candle_date_time_utc),
    ["2026-10-23T03:00:00", "2026-10-23T03:01:00", "2026-10-23T03:02:00"]);
  assert.equal(out[1].trade_price, 9);
  assert.equal(older[1].trade_price, 2);   // 입력은 바뀌지 않는다
  assert.deepEqual(mergeCandles(newer, older).map((x) => x.candle_date_time_utc),
    ["2026-10-23T03:00:00", "2026-10-23T03:01:00", "2026-10-23T03:02:00"]);
});

test("maLines: 60 and 200 on 400 closes", () => {
  const closes = Array.from({ length: 400 }, (_, i) => i + 1);
  const out = maLines(closes, [60, 200]);
  assert.equal(out[60].length, 400);
  assert.equal(out[200].length, 400);
  assert.ok(out[200].slice(0, 199).every((v) => v === null));
  assert.equal(out[200][199], 100.5);
  assert.ok(out[60].slice(0, 59).every((v) => v === null));
  assert.equal(out[60][59], 30.5);
});

test("visiblePeriods: 200 line waits until 400 candles", () => {
  assert.deepEqual(visiblePeriods(200, [60, 200]), [60]);
  assert.deepEqual(visiblePeriods(399, [60, 200]), [60]);
  assert.deepEqual(visiblePeriods(400, [60, 200]), [60, 200]);
  assert.deepEqual(visiblePeriods(400, [60]), [60]);
});

test("zoom scales visible logical range around its centre", () => {
  let set = null;
  const view = { ok: true, chart: { timeScale: () => ({
    getVisibleLogicalRange: () => ({ from: 100, to: 200 }),
    setVisibleLogicalRange: (r) => { set = r; },
  }) } };
  zoom(view, 2);   // 확대: 폭이 절반
  assert.deepEqual(set, { from: 125, to: 175 });
  zoom(view, 0.5); // 축소: 폭이 두 배
  assert.deepEqual(set, { from: 50, to: 250 });
  assert.doesNotThrow(() => zoom({ ok: false }, 2));
});

test("orders oldest first", () => {
  const latestFirst = [
    { candle_date_time_utc: "2026-10-23T03:06:00" },
    { candle_date_time_utc: "2026-10-23T03:03:00" },
    { candle_date_time_utc: "2026-10-23T03:00:00" },
  ];
  const out = toAscending(latestFirst);
  assert.deepEqual(out.map((c) => c.candle_date_time_utc), [
    "2026-10-23T03:00:00", "2026-10-23T03:03:00", "2026-10-23T03:06:00"]);
  // 원본 배열은 바뀌지 않는다
  assert.equal(latestFirst[0].candle_date_time_utc, "2026-10-23T03:06:00");
});

test("keeps last data on 429", async () => {
  const data = [];
  const errors = [];
  let n = 0;
  const p = createPoller({
    fetchFn: async () => {
      n += 1;
      if (n === 1) return ["c1"];
      const e = new Error("Too Many Requests");
      e.status = 429;
      throw e;
    },
    onData: (d) => data.push(d),
    onError: (t) => errors.push(t),
    isHidden: () => false,
  });
  await p.tick();
  await p.tick();
  assert.deepEqual(data, [["c1"]]);   // 두 번째는 onData 없음 → 마지막 데이터 유지
  assert.equal(errors.length, 1);
  assert.ok(errors[0] instanceof Date);
});

test("single in-flight request", async () => {
  let calls = 0;
  let release;
  const gate = new Promise((r) => { release = r; });
  const p = createPoller({
    fetchFn: () => { calls += 1; return gate; },
    onData: () => {}, onError: () => {}, isHidden: () => false,
  });
  const a = p.tick();
  const b = p.tick();
  assert.equal(calls, 1);
  release(["x"]);
  await a; await b;
  await p.tick();
  assert.equal(calls, 2);   // 끝난 뒤에는 다시 요청한다
});

test("skips when hidden", async () => {
  let calls = 0;
  let hidden = true;
  const p = createPoller({
    fetchFn: async () => { calls += 1; return []; },
    onData: () => {}, onError: () => {}, isHidden: () => hidden,
  });
  await p.tick();
  assert.equal(calls, 0);
  hidden = false;
  await p.tick();
  assert.equal(calls, 1);
});

test("marks last candle forming", () => {
  const start = Date.parse("2026-10-23T03:06:00Z");
  const candles = [
    { candle_date_time_utc: "2026-10-23T03:03:00" },
    { candle_date_time_utc: "2026-10-23T03:06:00" },
  ];
  const mid = markFormingCandle(candles, start + 60 * 1000, 180);
  assert.equal(mid[0].forming, false);
  assert.equal(mid[1].forming, true);
  const after = markFormingCandle(candles, start + 180 * 1000, 180);
  assert.equal(after[1].forming, false);
  assert.equal(candles[1].forming, undefined);   // 입력은 바뀌지 않는다
});

// 고정 기대값 표: 값 1..70 의 sma60. i 번째(0부터, i>=59) = i - 28.5.
// 인덱스 59 ~ 69 의 손으로 적은 값.
const SMA60_TAIL = [30.5, 31.5, 32.5, 33.5, 34.5, 35.5, 36.5, 37.5, 38.5, 39.5, 40.5];

test("sma60 matches reference", () => {
  const values = Array.from({ length: 70 }, (_, i) => i + 1);
  const out = sma(values, 60);
  assert.equal(out.length, 70);
  assert.ok(out.slice(0, 59).every((v) => v === null));
  assert.deepEqual(out.slice(59), SMA60_TAIL);
});

test("parseFailedKeys parses json array else raw", () => {
  assert.equal(parseFailedKeys('["cooldown"]'), "cooldown");
  assert.equal(parseFailedKeys('["a","b"]'), "a, b");
  assert.equal(parseFailedKeys("not json"), "not json");
  assert.equal(parseFailedKeys('{"x":1}'), '{"x":1}');
  assert.equal(parseFailedKeys(null), "");
});

test("kst formatters add nine hours", () => {
  assert.equal(kstHm(0), "09:00");
  assert.equal(kstMdHm(0), "01-01 09:00");
  assert.equal(kstTick(0, 3), "09:00");
  assert.equal(kstTick(0, 2), "01-01");
});

test("clipMarkers drops markers outside candle range", () => {
  const ms = [{ time: 99 }, { time: 100 }, { time: 250 }, { time: 280 }, { time: 281 }];
  // 첫 봉 100, 마지막 봉 200, 봉 길이 80 -> [100, 280)
  assert.deepEqual(clipMarkers(ms, 100, 200, 80).map((m) => m.time), [100, 250]);
});

test("intervalToMinutes rejects non-minute units", () => {
  assert.equal(intervalToMinutes("minute3"), 3);
  assert.equal(intervalToMinutes("day"), null);
  assert.equal(intervalToMinutes(undefined), null);
});

test("toMarkers buy below sell above sorted", () => {
  const rows = [
    { type: "SELL", price: 1200, bar_time: "2026-10-23T12:09:00+09:00" },
    { type: "BUY", price: 1000, bar_time: "2026-10-23T12:03:00+09:00" },
  ];
  const out = toMarkers(rows);
  assert.equal(out.length, 2);
  assert.ok(out[0].time < out[1].time);
  assert.equal(out[0].time, Date.parse("2026-10-23T03:03:00Z") / 1000);
  assert.equal(out[0].position, "belowBar");
  assert.equal(out[0].shape, "arrowUp");
  assert.equal(out[1].position, "aboveBar");
  assert.equal(out[1].shape, "arrowDown");
  assert.ok(out[0].text && out[1].text);
  assert.notEqual(out[0].color, out[1].color);
});
