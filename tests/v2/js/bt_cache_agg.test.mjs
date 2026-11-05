// 1105-09 검증 지적 6: Ver2 10분봉 합성(aggregateBars)과 출처를 바꿀 때 Ver2 캐시(dataCache) 비우기.
// 실행: node --test tests/v2/js/bt_cache_agg.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");
const BT_JS = fs.readFileSync(path.join(STATIC, "backtester.js"), "utf8");
const UI_JS = fs.readFileSync(path.join(STATIC, "bt_ui.js"), "utf8");

// 요소 흉내: click 처리기를 모아 두고 click() 으로 부른다
function makeDoc() {
  const els = {};
  const el = (id) => {
    if (!els[id]) {
      const h = {};
      els[id] = {
        id, value: "", textContent: "", innerHTML: "", className: "", hidden: false, disabled: false,
        checked: false, style: {}, dataset: {}, children: [],
        addEventListener: (ev, fn) => { (h[ev] = h[ev] || []).push(fn); },
        click: () => (h.click || []).forEach((fn) => fn({ preventDefault() {} })),
        appendChild() {}, setAttribute() {}, getContext: () => null,
      };
    }
    return els[id];
  };
  const doc = {
    readyState: "complete", getElementById: el, createElement: () => el("_tmp"),
    addEventListener() {}, querySelectorAll: () => [],
  };
  return { doc, el };
}

function context(withUi) {
  const { doc, el } = makeDoc();
  el("symbol").value = "JTOUSDT";
  el("dataSource").value = "binance";
  const ctx = {
    document: doc, console, devicePixelRatio: 1,
    setTimeout: () => 0,
    fetch: () => Promise.reject(new Error("시험: 바깥 연결 없음")),
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(BT_JS, ctx);
  if (withUi) vm.runInContext(UI_JS, ctx);
  return { ctx, el };
}

const M5 = 300000;
const T = Date.UTC(2026, 10, 5, 0, 0, 0);   // 10분 경계
const bar = (k, o, h, l, c) => ({ t: T + k * M5, o, h, l, c });

test("aggregateBars: 5분봉 2개를 10분 경계로 묶고, 짝이 없는 앞뒤 묶음은 버린다", () => {
  const { ctx } = context(false);
  const bars = [
    bar(-1, 9, 9, 9, 9),                       // 앞 묶음의 두 번째 칸만 있음 → 버림
    bar(0, 10, 12, 9, 11), bar(1, 11, 15, 10, 14),
    bar(2, 14, 14, 8, 9), bar(3, 9, 10, 7, 8),
    bar(4, 8, 9, 8, 9),                        // 마지막 묶음 미완성 → 버림
  ];
  ctx.__in = bars;
  const out = Array.from(vm.runInContext("aggregateBars(__in, 600000, 300000)", ctx), (b) => ({ ...b }));
  assert.deepStrictEqual(out, [
    { t: T, o: 10, h: 15, l: 9, c: 14 },
    { t: T + 2 * M5, o: 14, h: 14, l: 7, c: 8 },
  ]);
});

test("fetchKlines 10m: 5분봉을 받아 합성한다(다른 봉은 그대로)", async () => {
  const { ctx } = context(false);
  const seen = [];
  ctx.__raw = async (s, i, d) => { seen.push([s, i, d]); return [bar(0, 1, 2, 0, 1), bar(1, 1, 3, 1, 2)]; };
  vm.runInContext("fetchKlinesRaw = __raw", ctx);
  const ten = Array.from(await vm.runInContext('fetchKlines("JTOUSDT","10m",90)', ctx), (b) => ({ ...b }));
  assert.deepStrictEqual(ten, [{ t: T, o: 1, h: 3, l: 0, c: 2 }]);
  const three = await vm.runInContext('fetchKlines("JTOUSDT","3m",90)', ctx);
  assert.equal(three.length, 2);
  assert.deepStrictEqual(seen, [["JTOUSDT", "5m", 90], ["JTOUSDT", "3m", 90]]);
});

test("출처를 바꾸면 Ver2 dataCache 를 비우고, 같은 출처를 다시 누르면 그대로 둔다", () => {
  const { ctx, el } = context(true);
  // 화면이 열리면 업비트가 기본 — 이 시점 캐시는 비어 있다
  assert.equal(el("dataSource").value, "upbit");
  vm.runInContext('dataCache = {symbol:"KRW-JTO",interval:"3m",days:30,bars:[],fetchedAt:1}', ctx);
  el("btSrcUpbit").click();                              // 같은 출처
  assert.notEqual(vm.runInContext("dataCache", ctx), null);
  el("btSrcBinance").click();                            // 출처 바뀜
  assert.equal(vm.runInContext("dataCache", ctx), null);
  assert.equal(el("symbol").value, "JTOUSDT");
  vm.runInContext('dataCache = {symbol:"JTOUSDT",interval:"3m",days:30,bars:[],fetchedAt:1}', ctx);
  el("btSrcUpbit").click();
  assert.equal(vm.runInContext("dataCache", ctx), null);
  assert.equal(el("symbol").value, "KRW-JTO");
});
