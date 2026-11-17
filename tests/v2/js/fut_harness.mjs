// 선물 시험용 하네스(1111-01): 투자자 Ver9 원문 스크립트와 이식본(backtester.js)을 같은 가짜 fetch 로 돌린다.
// 바깥 연결 0: vm 컨텍스트에 실제 fetch 가 없고, 가짜 fetch 만 있다. 가짜 서버는 합성 고정 자료(fixtures/fut_*.json)만 돌려준다.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { parseDefaults } from "./harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
export const FUT_KLINES = JSON.parse(fs.readFileSync(path.join(here, "fixtures/fut_klines_a.json"), "utf8"));
export const FUT_FUNDING = JSON.parse(fs.readFileSync(path.join(here, "fixtures/fut_funding_a.json"), "utf8")).rows;

export function makeEl(value, selectedText = "") {
  return {
    value, selectedOptions: [{ textContent: selectedText, value }], innerHTML: "", textContent: "", style: {}, href: "", download: "", checked: false,
    addEventListener() {},
    getBoundingClientRect() { return { width: 800, height: 400, left: 0, top: 0 }; },
    click() {},
    getContext() {
      const fn = () => proxy;
      const proxy = new Proxy(fn, { get: (_t, k) => (k === Symbol.toPrimitive ? () => 0 : proxy), set: () => true, apply: () => proxy });
      return proxy;
    },
  };
}

// 가짜 바이낸스 서버: /klines 는 startTime~endTime 봉을 limit 개까지, /fundingRate 는 합성 펀딩비를 돌려준다.
export function fakeServer(urls) {
  return async (url) => {
    urls.push(String(url));
    const u = new URL(url);
    const startTime = +u.searchParams.get("startTime");
    const endTime = +u.searchParams.get("endTime");
    const limit = +u.searchParams.get("limit") || 1000;
    let data;
    if (u.pathname.endsWith("/klines")) {
      data = FUT_KLINES.bars.filter((b) => b[0] >= startTime && b[0] <= endTime).slice(0, limit);
    } else if (u.pathname.endsWith("/fundingRate")) {
      data = FUT_FUNDING.filter((f) => f.fundingTime >= startTime && f.fundingTime <= endTime).slice(0, limit);
    } else {
      throw new Error("fake server: 모르는 주소 " + url);
    }
    return { ok: true, status: 200, headers: { get: () => null }, json: async () => data };
  };
}

// scriptText·htmlText: Ver9 원문이든 이식본이든 같은 방식. overrides: {id: value} 칸 덮어쓰기.
export function makeRun(scriptText, htmlText, overrides = {}) {
  const defaults = parseDefaults(htmlText);
  const els = {};
  const getEl = (id) => {
    if (!els[id]) els[id] = makeEl(defaults[id] ? defaults[id].value : "", defaults[id]?.selectedText ?? "");
    return els[id];
  };
  getEl("symbol").value = FUT_KLINES.symbol;
  getEl("src").value = FUT_KLINES.interval;
  getEl("days").value = String(FUT_KLINES.days);
  for (const [k, v] of Object.entries(overrides)) getEl(k).value = String(v);
  const urls = [];
  const RealDate = Date;
  class FixedDate extends RealDate { static now() { return FUT_KLINES.fetched_at_ms; } }
  const ctx = {
    document: { getElementById: getEl, createElement: () => makeEl(""), addEventListener() {}, querySelectorAll: () => [] },
    fetch: fakeServer(urls),
    Date: FixedDate,
    setTimeout: (fn) => { fn(); return 0; },
    devicePixelRatio: 1,
    Blob: class {},
    URL: { createObjectURL: () => "blob:harness", revokeObjectURL() {} },
    console,
  };
  ctx.window = ctx;
  ctx.addEventListener = () => {};
  vm.createContext(ctx);
  vm.runInContext(scriptText, ctx);
  const csv = (name) => vm.runInContext(`csv(${name})`, ctx);
  const sets = () => ({
    sweep: csv("sweepRows"), bySlope: csv("sweepSlopeRows"), byDrop: csv("sweepDropRows"),
    bestMonth: csv("sweepMonthRows"), bestWeek: csv("sweepWeekRows"),
  });
  return {
    ctx, urls, getEl,
    set(id, v) { getEl(id).value = String(v); },
    async runSpot() { await ctx.run(); },
    async runFut() { await ctx.runFutures(); },
    async sweep() { await ctx.runSweep(); return sets(); },
    snapshot() {
      return {
        trades: csv("tradeRows"), weekly: csv("weeklyRows"), monthly: csv("monthlyRows"),
        summary: getEl("summary").innerHTML, status: getEl("status").textContent,
        chartHint: getEl("chartHint").textContent,
        mode: vm.runInContext("lastMode", ctx),
      };
    },
  };
}

// 좁힌 스윕 범위(36조합): 기울기·둔화 값별 분석표와 월·주별 1등 표가 모두 생기게 한다.
export const NARROW_SWEEP = {
  sw_tpFrom: 2, sw_tpTo: 3, sw_tpStep: 1, sw_slFrom: 2, sw_slTo: 3, sw_slStep: 1,
  sw_spFrom: 1, sw_spTo: 1, sw_spStep: 1,
  sw_ma60From: 0, sw_ma60To: 0.2, sw_ma60Step: 0.1,
  sw_dropFrom: 0, sw_dropTo: 0.2, sw_dropStep: 0.1,
};
