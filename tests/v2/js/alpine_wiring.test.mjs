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
const chartEl = { innerHTML: "", textContent: "", style: {} };
globalThis.window = globalThis;
// PC 차트 높이 맞춤(fitChart)이 쓰는 창 API — 시험은 좁은 창(matchMedia 없음)으로 본다
globalThis.addEventListener = () => {};
globalThis.requestAnimationFrame = (fn) => fn();
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
  const realCT = globalThis.clearTimeout;
  const realCI = globalThis.clearInterval;
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
    // 컴포넌트 밖에서 돌리므로 Alpine 매직($watch·$nextTick)을 대신 넣는다
    const watched = [];
    d.$watch = (k) => { watched.push(k); };
    d.$nextTick = (fn) => fn();
    d.init();
    // 차트 위 문구·머리 경고가 바뀌면 PC 차트 높이를 다시 잰다
    assert.deepEqual(watched, ["chartFail", "chartNote", "netError", "authError", "status"]);
    await flush(); await flush();
    assert.equal(d.status.ticker, "KRW-ZRO");

    // (1) 첫 차트 열림: 업비트 응답 1건 -> 그려진다
    d.go("chart");
    await flush(); await flush();
    assert.equal(upbitCalls, 1);
    assert.ok(setDataCalls >= 1, "첫 응답이 그려지지 않음");
    assert.equal(chartEl.style.height, "", "좁은 창에서는 inline 높이를 넣지 않는다(모바일 CSS 그대로)");

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

    // (4) PC 넓은 창: 차트 칸 높이 = 창 높이 - 문서 기준 위치 - (차트 아래 + 카드 여백 + max(body 아래 패딩, 탭 막대))
    globalThis.matchMedia = (q) => ({ matches: q === "(min-width: 641px)" });
    globalThis.innerHeight = 900;
    globalThis.scrollY = 50;   // 스크롤된 상태에서도 문서 기준으로 잰다
    const card = { getBoundingClientRect: () => ({ bottom: 760 }), _mb: "8px" };
    chartEl.getBoundingClientRect = () => ({ top: 51, bottom: 700 });   // 문서 기준 top = 101
    chartEl.closest = () => card;
    globalThis.document.body.style = {};
    globalThis.getComputedStyle = (el) => (el === card ? { marginBottom: "8px" } : { paddingBottom: "72px" });
    globalThis.document.querySelector = () => ({ offsetHeight: 46 });
    d.fitChart();
    // 900 - 101 - (60 + 8 + max(72, 46)) = 659
    assert.equal(chartEl.style.height, "659px");
    // 차트 탭이 아니면 inline 높이를 지운다
    d.go("home");
    d.fitChart();
    assert.equal(chartEl.style.height, "");
    // 좁은 창(640 이하)이면 지운다
    d.go("chart");
    d.fitChart();
    assert.equal(chartEl.style.height, "659px");
    globalThis.matchMedia = () => ({ matches: false });
    d.fitChart();
    assert.equal(chartEl.style.height, "");
  } finally {
    Date.now = realNow;
    globalThis.setTimeout = realST;
    globalThis.setInterval = realSI;
    globalThis.clearTimeout = realCT;
    globalThis.clearInterval = realCI;
  }
});
