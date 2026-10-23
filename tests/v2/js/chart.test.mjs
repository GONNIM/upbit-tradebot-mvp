import { test } from "node:test";
import assert from "node:assert/strict";
import {
  upbitCandlesUrl, toAscending, createPoller, markFormingCandle, sma, toMarkers, maLines,
  createRateGate, parseFailedKeys, kstHm, kstMdHm, kstTick, clipMarkers, intervalToMinutes,
} from "../../../v2/static/chart.js";

test("upbitCandlesUrl", () => {
  assert.equal(
    upbitCandlesUrl("KRW-JTO", 3),
    "https://api.upbit.com/v1/candles/minutes/3?market=KRW-JTO&count=200");
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

test("pullback period 60 draws one line", () => {
  const closes = Array.from({ length: 70 }, (_, i) => i + 1);
  const same = maLines(closes, 60);
  assert.equal(same.pullback, null);
  assert.equal(same.ma60.length, 70);
  assert.equal(same.label, "MA60 (눌림목 MA 기본값과 같음)");
  const other = maLines(closes, 20);
  assert.equal(other.pullback.length, 70);
});

test("rate gate skips second call within 10s", () => {
  let now = 1000;
  const g = createRateGate(10000, () => now);
  assert.equal(g.allow(), true);
  now += 9999;
  assert.equal(g.allow(), false);
  now += 1;
  assert.equal(g.allow(), true);
});

test("rate gate msUntilOpen reports remaining time", () => {
  let now = 5000;
  const g = createRateGate(10000, () => now);
  assert.equal(g.msUntilOpen(), 0);
  g.allow();
  now += 3000;
  assert.equal(g.msUntilOpen(), 7000);
  now += 7000;
  assert.equal(g.msUntilOpen(), 0);
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
