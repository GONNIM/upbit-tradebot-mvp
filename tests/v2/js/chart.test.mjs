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

// ---- 1125-01 A: 백테스터 차트 기능 ----
import {
  markerSideText, kstCompact, sidePrice, labelHideLimit, labelsHidden, countVisibleMarkers,
  decorateMarkers, barInfoText, targetBars, normalizeBarChoice, limitBars, BAR_CHOICES,
  createChartView, COLOR_UP, COLOR_DOWN, CHART_BG, sideMask, textWidthPx,
} from "../../../v2/static/chart.js";

test("1125-01 A1: 옆 글 = 「매수 YYMMDD_HHMM · 가격」 KST, 표식 자료의 text 는 그대로", () => {
  const out = toMarkers([{ type: "BUY", price: 330, bar_time: "2026-11-24T15:09:00+09:00" },
    { type: "SELL", price: 1234.5, bar_time: "2026-11-24T16:00:00+09:00" }]);
  assert.deepEqual(out.map((m) => m.text), ["매수", "매도"]);          // 자료는 그대로
  assert.equal(kstCompact(out[0].time), "261124_1509");
  assert.equal(markerSideText(out[0]), "매수 261124_1509 · 330");
  assert.equal(markerSideText(out[1]), "매도 261124_1600 · 1,235");
  assert.equal(sidePrice(0.1234), "0.1234");
  // 가격이 없으면 시각만
  assert.equal(markerSideText({ text: "매수", time: out[0].time, price: NaN }), "매수 261124_1509");
  const on = decorateMarkers(out, true), off = decorateMarkers(out, false);
  assert.equal(on[0].text, "매수 261124_1509 · 330");
  assert.equal(off[0].text, "매수");
  assert.ok(!("price" in on[0]), "LW 에 price 를 넘기지 않는다");
  assert.equal(out[0].color, COLOR_UP);
  assert.equal(out[1].color, COLOR_DOWN);
});

test("1125-01 A1: 숨김 기준 = 보이는 표식 수 > max(40, 폭/9)", () => {
  assert.equal(labelHideLimit(360), 40);
  assert.equal(labelHideLimit(900), 100);
  assert.equal(labelsHidden(40, 360), false);
  assert.equal(labelsHidden(41, 360), true);
  assert.equal(labelsHidden(100, 900), false);
  assert.equal(labelsHidden(101, 900), true);
  const ms = [{ time: 100 }, { time: 200 }, { time: 300 }];
  assert.equal(countVisibleMarkers(ms, 150, 301), 2);
});

test("1125-01 A2: 봉 정보 글(시각 KST·시고저종·선 값)", () => {
  const t = Date.parse("2026-11-25T06:09:00Z") / 1000;   // KST 15:09
  const s = barInfoText({ time: t, open: 330, high: 335, low: 328, close: 331 },
    [{ label: "60선", value: 330.5 }, { label: "200선", value: undefined }]);
  assert.equal(s, "26.11.25 15:09 시 330 · 고 335 · 저 328 · 종 331 · 60선 330.5");
  assert.equal(barInfoText(null, []), "");
});

test("1125-01 A4: 봉 수 = max(고른 값, 전략 목표), 줄이면 최근 N개만", () => {
  assert.deepEqual(BAR_CHOICES, [400, 1000, 2000]);
  assert.equal(targetBars(400, 400), 400);
  assert.equal(targetBars(400, 1200), 1200);   // 전략이 더 크면 전략 목표
  assert.equal(targetBars(1000, 400), 1000);
  assert.equal(targetBars(2000, 1200), 2000);
  assert.equal(targetBars(123, 400), 400);      // 이상한 값은 400
  assert.equal(normalizeBarChoice("1000"), 1000);
  const arr = [1, 2, 3, 4, 5];
  assert.deepEqual(limitBars(arr, 3), [3, 4, 5]);
  assert.deepEqual(limitBars(arr, 10), arr);
});

// 가짜 LW: 보이는 범위·표식 호출 수를 센다
function fakeLW(state) {
  const series = { setData() {}, setMarkers(m) { state.markerCalls.push(m); } };
  return {
    createChart: (el, o) => {
      state.opts = o;
      return {
        addCandlestickSeries: () => series,
        addLineSeries: () => ({ setData() {} }),
        timeScale: () => ({
          getVisibleLogicalRange: () => state.range,
          subscribeVisibleLogicalRangeChange: (fn) => { state.rangeFn = fn; },
          fitContent() { state.fit = (state.fit || 0) + 1; },
        }),
        subscribeCrosshairMove: (fn) => { state.crossFn = fn; },
        remove() {},
      };
    },
  };
}
function mkCandles(n, t0 = Date.parse("2026-11-24T00:00:00Z")) {
  return Array.from({ length: n }, (_, i) => ({
    candle_date_time_utc: new Date(t0 + i * 180000).toISOString().slice(0, 19),
    opening_price: 100, high_price: 110, low_price: 90, trade_price: 100 + (i % 7), forming: false,
  }));
}

test("1125-01 A1: 숨김 상태가 바뀔 때만 setMarkers 를 다시 부른다", () => {
  const state = { markerCalls: [], range: { from: 0, to: 99 } };
  globalThis.window = globalThis;
  globalThis.LightweightCharts = fakeLW(state);
  const view = createChartView({ clientWidth: 360 }, {});
  assert.equal(state.opts.layout.background.color, CHART_BG);
  const cs = mkCandles(100);
  const base = Date.parse("2026-11-24T00:00:00Z");
  // 표식 60개(40 초과) → 모두 보이는 범위에서는 옆 글이 숨는다
  const rows = Array.from({ length: 60 }, (_, i) => ({
    type: i % 2 ? "SELL" : "BUY", price: 100 + i, bar_time: new Date(base + i * 180000).toISOString(),
  }));
  view.update(cs, rows, [60, 200], 180, "sma", { limit: 100 });
  assert.equal(state.markerCalls.length, 1, "자료를 그릴 때 1번");
  assert.equal(state.markerCalls[0][0].text, "매수", "많으면 옆 글 숨김");
  // 같은 상태로 화면을 옮김 → 다시 그리지 않음
  state.rangeFn(); state.rangeFn();
  assert.equal(state.markerCalls.length, 1);
  // 확대해 보이는 표식이 적어지면(0~19봉 → 표식 20개) 옆 글이 보이고 1번만 다시 그림
  state.range = { from: 0, to: 19 };
  state.rangeFn(); state.rangeFn();
  assert.equal(state.markerCalls.length, 2);
  assert.match(state.markerCalls[1][0].text, /^매수 \d{6}_\d{4} · 100$/);
  // 사용자가 옆 글을 끔 → 1번, 같은 값 다시 끄면 안 부름
  view.setLabels(false); view.setLabels(false);
  assert.equal(state.markerCalls.length, 3);
  assert.equal(state.markerCalls[2][0].text, "매수");
  view.setLabels(true);
  assert.equal(state.markerCalls.length, 4);
  // 새 자료는 늘 다시 그림
  view.update(cs, rows, [60, 200], 180, "sma", { limit: 100 });
  assert.equal(state.markerCalls.length, 5);
});

test("1125-01 A2·A4·A5: 봉 정보 글 콜백·최근 N개만·전체 봉 보기", () => {
  const state = { markerCalls: [], range: { from: 0, to: 49 } };
  globalThis.window = globalThis;
  globalThis.LightweightCharts = fakeLW(state);
  const infos = [];
  const view = createChartView({ clientWidth: 360 }, { onInfo: (t) => infos.push(t) });
  const cs = mkCandles(100);
  view.update(cs, [], [60, 200], 180, "sma", { limit: 50 });
  const lastT = Math.floor(Date.parse(cs[99].candle_date_time_utc + "Z") / 1000);
  state.crossFn({ time: lastT });
  assert.match(infos[0], /^26\.11\.\d\d \d\d:\d\d 시 100 · 고 110 · 저 90 · 종 \d+ · 60선 /);
  const firstShown = Math.floor(Date.parse(cs[50].candle_date_time_utc + "Z") / 1000);
  state.crossFn({ time: firstShown });
  assert.ok(infos[1].startsWith("26.11."));
  const hidden = Math.floor(Date.parse(cs[0].candle_date_time_utc + "Z") / 1000);
  state.crossFn({ time: hidden });          // 줄여서 안 그리는 봉
  assert.equal(infos[2], "");
  state.crossFn({});                        // 봉 밖
  assert.equal(infos[3], "");
  view.fit();
  assert.equal(state.fit, 1);
});

test("1125-01 ㉠: 이웃 옆 글과 겹치면 앞(왼쪽) 표식의 시각·가격만 숨김", () => {
  const txt = "매수 261125_1750 · 400";          // 한글 2자 + 나머지 → 약 24 + 19*7
  const w = textWidthPx(txt);
  assert.ok(w > 100 && w < 200);
  // 멀리 떨어짐 → 둘 다 보임
  assert.deepEqual(sideMask([10, 10 + w + 20], [txt, txt]), [true, true]);
  // 가까움 → 최근(오른쪽) 것만 보임
  assert.deepEqual(sideMask([100, 140], [txt, txt]), [false, true]);
  // 셋: 가운데가 최근 것과 겹치고, 맨 앞은 최근 것과 떨어짐
  assert.deepEqual(sideMask([0, 300, 330], [txt, txt, txt]), [true, false, true]);
  // 화면 밖(null)은 다른 글을 막지 않음
  assert.deepEqual(sideMask([100, null], [txt, txt]), [true, true]);
  // 배열 마스크로 decorate
  const ms = [{ time: 1, position: "belowBar", color: "#f00", shape: "arrowUp", text: "매수", price: 400 },
              { time: 2, position: "aboveBar", color: "#00f", shape: "arrowDown", text: "매도", price: 420 }];
  const d = decorateMarkers(ms, [false, true]);
  assert.equal(d[0].text, "매수");
  assert.ok(d[1].text.startsWith("매도 ") && d[1].text.endsWith("· 420"));
});
