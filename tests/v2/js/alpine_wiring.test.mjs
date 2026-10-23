// app.js 연결부를 실제 Alpine 반응형(Alpine.reactive) 아래에서 돌리는 시험.
// 반응형 프록시 때문에 `this._poller === poller` 같은 객체 동일성 비교가 어긋나던 결함을 막는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");

// ---- 최소 브라우저 대체물 ----
const listeners = {};
const chartEl = { innerHTML: "", textContent: "" };
globalThis.window = globalThis;
for (const n of ["Element", "Node", "HTMLElement", "HTMLTemplateElement", "SVGElement"]) {
  globalThis[n] = class {};
}
globalThis.MutationObserver = class { observe() {} disconnect() {} takeRecords() { return []; } };
globalThis.document = {
  hidden: false,
  body: {},
  addEventListener(name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
  dispatchEvent() {},
  getElementById() { return chartEl; },
  createElement() { return { style: {}, setAttribute() {}, appendChild() {}, classList: { add() {} } }; },
  createTextNode() { return {}; },
};

// Alpine 은 로드 직후 microtask 로 start() 한다 — 시험에서는 시작하지 않는다.
const realQM = globalThis.queueMicrotask;
globalThis.queueMicrotask = () => {};
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "vendor/alpine-3.14.1.min.js"), "utf8"));
globalThis.queueMicrotask = realQM;
const RealAlpine = globalThis.Alpine;

// app.js 는 Alpine.data("dash", factory) 로 등록한다 — 등록만 가로챈다.
let dashFactory = null;
globalThis.Alpine = { data(name, f) { if (name === "dash") dashFactory = f; } };
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "app.js"), "utf8"));
for (const fn of listeners["alpine:init"]) fn();
globalThis.Alpine = RealAlpine;
const chartMod = await import(path.join(STATIC, "chart.js"));
globalThis.v2Chart = chartMod;

const flush = () => new Promise((r) => setImmediate(r));

function candles() {
  return [
    { candle_date_time_utc: "2026-10-23T03:03:00", opening_price: 2, high_price: 3, low_price: 1, trade_price: 2 },
    { candle_date_time_utc: "2026-10-23T03:00:00", opening_price: 1, high_price: 2, low_price: 1, trade_price: 2 },
  ];
}

test("chart draws, shows failure, and retries after gate under Alpine.reactive", async () => {
  let nowMs = 1_000_000;
  const realNow = Date.now;
  Date.now = () => nowMs;
  const realST = globalThis.setTimeout;
  const realSI = globalThis.setInterval;
  const timeouts = [];
  const intervals = [];
  globalThis.setTimeout = (fn, ms) => { timeouts.push({ fn, ms }); return timeouts.length; };
  globalThis.clearTimeout = () => {};
  globalThis.setInterval = (fn, ms) => { intervals.push({ fn, ms }); return intervals.length; };

  let setDataCalls = 0;
  const series = { setData() { setDataCalls += 1; }, setMarkers() {}, };
  globalThis.LightweightCharts = {
    createChart: () => ({
      addCandlestickSeries: () => series,
      addLineSeries: () => ({ setData() {} }),
      remove() {},
    }),
  };

  const upbitResponses = [200, 429, 200];
  let upbitCalls = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.startsWith("https://api.upbit.com/")) {
      const code = upbitResponses[upbitCalls++];
      return { ok: code === 200, status: code, json: async () => candles() };
    }
    let body = {};
    if (u.includes("/v2/api/status")) {
      body = { engine: { level: "ok", ago_sec: 10 }, ticker: "KRW-ZRO", interval: "minute3",
               strategy: { value: "EMA" }, paused: false };
    } else if (u.includes("/v2/api/markers")) {
      body = { markers: [] };
    }
    return { ok: true, status: 200, json: async () => body };
  };

  try {
    const d = RealAlpine.reactive(dashFactory());
    d.init();
    await flush(); await flush();
    assert.equal(d.status.ticker, "KRW-ZRO");

    // (1) 첫 차트 열림: 업비트 응답 1건 -> 그려진다
    d.go("chart");
    await flush(); await flush();
    assert.equal(upbitCalls, 1);
    assert.ok(setDataCalls >= 1, "첫 응답이 그려지지 않음");

    // (2) 30초 뒤 429 -> 「갱신 실패 · HH:MM:SS」, 마지막 데이터 유지
    const before = setDataCalls;
    nowMs += 31_000;
    const thirty = intervals.filter((i) => i.ms === 30000).pop();
    thirty.fn();
    await flush(); await flush();
    assert.equal(upbitCalls, 2);
    assert.match(d.chartFail, /^갱신 실패 · \d\d:\d\d:\d\d$/);
    assert.equal(setDataCalls, before);

    // (3) 탭을 바로 오가면 10초 게이트에 막히고, 게이트가 열린 뒤 재시도로 1건 더 나간다
    d.go("home");
    d.go("chart");
    await flush(); await flush();
    assert.equal(upbitCalls, 2, "게이트 안에서 요청이 나감");
    const retry = timeouts.filter((t) => t.ms > 0 && t.ms <= 10_100).pop();
    assert.ok(retry, "재시도 타이머 없음");
    nowMs += 11_000;
    retry.fn();
    await flush(); await flush();
    assert.equal(upbitCalls, 3);
  } finally {
    Date.now = realNow;
    globalThis.setTimeout = realST;
    globalThis.setInterval = realSI;
  }
});
