// 1121-03 A1 시험: 백테스터를 마지막 저장값으로 열기(GET /v2/api/params/last-saved) — 이력 있음(업비트·바이낸스) · 없음 · 깨짐 ·
// 상태 응답이 늦게/먼저 와도 봉 단위는 이력 값 · 「다름」 문구 · 실패·시간 초과 = 지금 동작 · 기다리는 사이 칸 고침·실행 중 = 채우지 않음 ·
// 이력 종목 = 기본 업비트 종목이고 엔진 종목은 다름 → 종목 칸은 이력 값, engineTicker 만 엔진 값.
// 바깥 연결 0: vm 안에 실제 fetch 가 없고, 같은 출처 v2 주소 두 개만 가짜로 답한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { parseDefaults } from "./harness.mjs";
import { makeEl } from "./fut_harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");
const BT_JS = fs.readFileSync(path.join(STATIC, "backtester.js"), "utf8");
const UI_JS = fs.readFileSync(path.join(STATIC, "bt_ui.js"), "utf8");
const HTML = fs.readFileSync(path.join(STATIC, "backtester.html"), "utf8");
const DEFAULTS = parseDefaults(HTML);

function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const flush = async () => { for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r)); };

const STATUS = { mode_engine: "TEST", ticker: "KRW-ZRO", interval: "minute1" };
const SAVED_PARAMS = {
  symbol: "KRW-JTO", maType: "sma", src: "5m", days: 45, ma60p: 50, ma200p: 180, pullbackP: 40, slopeLB: 15,
  gcMaxGapPct: "1.5", ma60MinSlope: 0.6, ma60SlopeDrop: 0.2, slStreakPause: 2, slStreakCooldownHours: 3,
  episodePullbackCap: 1, episodeTpDecayPct: 40, episodeTpFloorPct: 0.4, buyOnGoldenCross: "no",
  maxSplits: 3, maxPullbackBuys: 2, tp: 1.5, sl: 5, capital: 20000, fee: 0.04, deadcross: "yes", compounding: "yes",
};
const SAVED = { exists: true, saved_at: "2026-11-24T05:08:27+09:00", saved_at_text: "26.11.24 05:08", source: "upbit",
  params: SAVED_PARAMS, trailing: { ts_on: true, ts_mode: "fixed", ts_pct: 30 }, differs_from_applied: false };

// 화면(backtester.js + bt_ui.js)을 연다. 두 주소의 응답은 시험이 정한 약속(deferred)으로 준다.
function page(opts = {}) {
  const els = {};
  const getEl = (id) => {
    if (!els[id]) {
      const e = makeEl(DEFAULTS[id] ? DEFAULTS[id].value : "", DEFAULTS[id]?.selectedText ?? "");
      const h = {};
      e.className = ""; e.hidden = false; e.disabled = false;
      e.addEventListener = (ev, fn) => { (h[ev] = h[ev] || []).push(fn); };
      e.click = () => (h.click || []).forEach((fn) => fn({ preventDefault() {} }));
      els[id] = e;
    }
    return els[id];
  };
  const docH = {};
  const timers = [];
  const status = deferred(), saved = deferred();
  const urls = [];
  const ctx = {
    document: { readyState: "complete", getElementById: getEl, createElement: () => makeEl(""),
      addEventListener: (ev, fn) => { (docH[ev] = docH[ev] || []).push(fn); }, querySelectorAll: () => [] },
    fetch: (url) => {
      urls.push(String(url));
      if (String(url).startsWith("/v2/api/status")) return status.promise;
      if (String(url).startsWith("/v2/api/params/last-saved")) return saved.promise;
      return Promise.reject(new Error("모르는 주소 " + url));
    },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout() {},
    devicePixelRatio: 1, Blob: class {}, URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} }, console,
    Promise,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  ctx.addEventListener = () => {};
  vm.createContext(ctx);
  vm.runInContext(BT_JS, ctx);
  if (opts.hangSweep) ctx.runSweep = () => new Promise(() => {});   // 스윕이 끝나지 않음(실행 중 상태)
  vm.runInContext(UI_JS, ctx);
  return {
    ctx, el: getEl, urls, status, saved,
    fire: (ev) => (docH[ev] || []).forEach((fn) => fn({})),
    runTimeouts: () => timers.filter((t) => t.ms === 5000).forEach((t) => t.fn()),
    v: (name) => vm.runInContext(name, ctx),
  };
}

function assertFilledFromSaved(p, source) {
  assert.equal(p.el("dataSource").value, source);
  for (const [k, v] of Object.entries(SAVED_PARAMS)) {
    if (source === "binance" && k === "symbol") continue;
    assert.equal(p.el(k).value, String(v), k);
  }
  assert.equal(p.el("trailingStop").value, "yes");
  assert.equal(p.el("trailingMode").value, "fixed");
  assert.equal(p.el("trailingPct").value, "30");
}

test("이력 있음(업비트) · 상태가 먼저 와도 봉 단위·종목은 이력 값 · 시작 문구", async () => {
  const p = page();
  assert.deepEqual(p.urls, ["/v2/api/status", "/v2/api/params/last-saved"]);   // 같은 출처 두 주소뿐
  p.status.resolve(ok(STATUS));
  await flush();
  assert.equal(p.el("src").value, "3m");                 // 저장값을 아직 기다린다 — 상태로 먼저 채우지 않음
  p.saved.resolve(ok(SAVED));
  await flush();
  assertFilledFromSaved(p, "upbit");
  assert.equal(p.el("symbol").value, "KRW-JTO");        // 이력 종목 = 기본 업비트 종목 → 엔진 종목(KRW-ZRO)으로 덮어쓰지 않음
  assert.equal(p.el("src").value, "5m");                // status 의 minute1 이 아님
  assert.equal(p.el("btLoaded").textContent, "불러온 설정: 마지막 저장 26.11.24 05:08");
  assert.equal(p.el("btMode").textContent, "TEST");
  // engineTicker 는 엔진 값: 바이낸스로 갔다가 업비트를 다시 누르면 엔진 종목
  p.el("btSrcBinance").click();
  p.el("btSrcUpbit").click();
  assert.equal(p.el("symbol").value, "KRW-ZRO");
});

test("이력 있음(업비트) · 저장값이 먼저 오고 상태가 늦게 와도 같은 결과", async () => {
  const p = page();
  p.saved.resolve(ok(SAVED));
  await flush();
  p.status.resolve(ok(STATUS));
  await flush();
  assertFilledFromSaved(p, "upbit");
  assert.equal(p.el("src").value, "5m");
});

test("이력 있음(바이낸스) → 바이낸스 출처·이력 종목으로 열림", async () => {
  const p = page();
  p.status.resolve(ok(STATUS));
  p.saved.resolve(ok({ ...SAVED, source: "binance", params: { ...SAVED_PARAMS, symbol: "SOLUSDT" } }));
  await flush();
  assertFilledFromSaved(p, "binance");
  assert.equal(p.el("symbol").value, "SOLUSDT");
  assert.equal(p.el("btFutBtn").disabled, false);
});

test("지금 운용 값과 다르면 「다름」 문구 · 추적 손절 끔이면 방식·폭 칸은 기본값", async () => {
  const p = page();
  p.status.resolve(ok(STATUS));
  p.saved.resolve(ok({ ...SAVED, trailing: { ts_on: false }, differs_from_applied: true }));
  await flush();
  assert.equal(p.el("btLoaded").textContent,
    "불러온 설정: 마지막 저장 26.11.24 05:08 (지금 운용 값과 다름 — 저장만 하고 적용하지 않음)");
  assert.equal(p.el("trailingStop").value, "no");
  assert.equal(p.el("trailingMode").value, "ratio");
  assert.equal(p.el("trailingPct").value, "50");
  // differs null(적용본 없음·깨짐)이면 문구 없음
  const q = page();
  q.status.resolve(ok(STATUS));
  q.saved.resolve(ok({ ...SAVED, differs_from_applied: null }));
  await flush();
  assert.equal(q.el("btLoaded").textContent, "불러온 설정: 마지막 저장 26.11.24 05:08");
});

// 지금 동작(이력 없음·깨짐·실패·시간 초과): 엔진 종목(기본값일 때만)·봉 단위로 채우고 「기본 설정」
function assertCurrentBehavior(p) {
  assert.equal(p.el("dataSource").value, "upbit");
  assert.equal(p.el("symbol").value, "KRW-ZRO");
  assert.equal(p.el("src").value, "1m");
  assert.equal(p.el("tp").value, DEFAULTS.tp.value);
  assert.equal(p.el("trailingStop").value, "no");
  assert.equal(p.el("btLoaded").textContent, "기본 설정");
}

test("이력 없음 · 깨진 행 · 출처 없는 행(broken) → 지금 동작", async () => {
  for (const body of [{ exists: false }, { exists: false, broken: true }, { ...SAVED, source: null },
    { ...SAVED, broken: true }, { ...SAVED, params: null }]) {
    const p = page();
    p.status.resolve(ok(STATUS));
    p.saved.resolve(ok(body));
    await flush();
    assertCurrentBehavior(p);
  }
});

test("저장값 읽기 실패(503·네트워크 오류) → 지금 동작", async () => {
  const p = page();
  p.status.resolve(ok(STATUS));
  p.saved.resolve({ ok: false, status: 503, json: async () => ({ error: "db_unavailable" }) });
  await flush();
  assertCurrentBehavior(p);
  const q = page();
  q.status.resolve(ok(STATUS));
  q.saved.reject(new Error("network"));
  await flush();
  assertCurrentBehavior(q);
});

test("상태 응답이 5초 뒤에 와도 머리 막대 모드는 채움 · 종목·봉 단위 자동 채움은 하지 않음", async () => {
  const p = page();
  p.runTimeouts();                         // 둘 다 5초 안에 안 옴
  await flush();
  assert.equal(p.el("btLoaded").textContent, "기본 설정");
  p.status.resolve(ok(STATUS));           // 늦게 온 상태
  await flush();
  assert.equal(p.el("btMode").textContent, "TEST");
  assert.equal(p.el("src").value, "3m");
  assert.equal(p.el("symbol").value, "KRW-JTO");
});

test("저장값 시간 초과(5초) → 지금 동작, 늦게 와도 덮어쓰지 않음", async () => {
  const p = page();
  p.status.resolve(ok(STATUS));
  await flush();
  p.runTimeouts();
  await flush();
  assertCurrentBehavior(p);
  p.saved.resolve(ok(SAVED));
  await flush();
  assertCurrentBehavior(p);
});

test("기다리는 사이 칸을 고쳤거나 출처를 눌렀으면 채우지 않음(건너뜀 한 줄) · 상태로도 덮어쓰지 않음", async () => {
  for (const act of ["input", "change", "click"]) {
    const p = page();
    if (act === "click") p.el("btSrcBinance").click(); else { p.el("tp").value = "9"; p.fire(act); }
    p.status.resolve(ok(STATUS));
    p.saved.resolve(ok(SAVED));
    await flush();
    assert.equal(p.el("btLoaded").textContent, "저장값 불러오기 건너뜀 — 그사이 칸을 고쳤거나 실행 중입니다", act);
    assert.equal(p.el("src").value, "3m", act);
    assert.notEqual(p.el("ma60p").value, "50", act);
    if (act !== "click") assert.equal(p.el("tp").value, "9");
    else assert.equal(p.el("dataSource").value, "binance");
  }
});

test("실행 중(busyCount>0)이면 채우지 않음", async () => {
  const p = page({ hangSweep: true });
  p.ctx.runSweep();                       // 끝나지 않는 스윕 — 실행 중
  p.status.resolve(ok(STATUS));
  p.saved.resolve(ok(SAVED));
  await flush();
  assert.equal(p.el("btLoaded").textContent, "저장값 불러오기 건너뜀 — 그사이 칸을 고쳤거나 실행 중입니다");
  assert.equal(p.el("ma60p").value, DEFAULTS.ma60p.value);
});

test("순수 함수: startValues · loadedText", () => {
  const B = (() => {
    const c = { globalThis: null, document: undefined, window: undefined, console };
    c.globalThis = c;
    vm.createContext(c);
    vm.runInContext(UI_JS, c);
    return c.__v2bt;
  })();
  assert.equal(B.startValues(null), null);
  assert.equal(B.startValues({ exists: false }), null);
  assert.equal(B.startValues({ ...SAVED, source: "x" }), null);
  assert.equal(B.startValues(SAVED).source, "upbit");
  assert.equal(B.loadedText({ saved_at_text: "26.11.24 05:08", differs_from_applied: true }),
    "불러온 설정: 마지막 저장 26.11.24 05:08 (지금 운용 값과 다름 — 저장만 하고 적용하지 않음)");
});
