// 1111-01 투자자 Ver9 반영 시험: 기본값(N7) · 업비트 출처 선물 막기(N4) · 출처 바꿀 때 비우기(N5) ·
// 카드 줄 구분(N9) · 선물 뒤 저장 창(N10) · 요약 카드 await(N8) · 실행 중 출처 바꾸기 막기(N11) · 스윕 · 실행 겹침 막기(N12).
// 바깥 연결 0: vm 에 실제 fetch 가 없고 가짜 서버(fut_harness.fakeServer, 합성 고정 자료)만 있다. 실제 바이낸스·업비트 호출 없음.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { parseDefaults } from "./harness.mjs";
import { makeEl, fakeServer, FUT_KLINES, NARROW_SWEEP } from "./fut_harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");
const BT_JS = fs.readFileSync(path.join(STATIC, "backtester.js"), "utf8");
const UI_JS = fs.readFileSync(path.join(STATIC, "bt_ui.js"), "utf8");
const SAVE_JS = fs.readFileSync(path.join(STATIC, "save.js"), "utf8");
const HTML = fs.readFileSync(path.join(STATIC, "backtester.html"), "utf8");
const DEFAULTS = parseDefaults(HTML);

// bt_ui.js 순수 함수(문서 없이)
const B = (() => {
  const ctx = { globalThis: null, document: undefined, window: undefined, console };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(UI_JS, ctx);
  return ctx.__v2bt;
})();
const J = (x) => JSON.parse(JSON.stringify(x));

// 화면 전체(backtester.js + bt_ui.js)를 가짜 문서·가짜 서버로 연다. 화면이 열리면 업비트가 기본 출처다.
function page(overrides = {}) {
  const els = {};
  const getEl = (id) => {
    if (!els[id]) {
      const e = makeEl(DEFAULTS[id] ? DEFAULTS[id].value : "", DEFAULTS[id]?.selectedText ?? "");
      const h = {};
      e.className = ""; e.hidden = false; e.disabled = false;
      const m = new RegExp(`id="${id}"[^>]*>([^<]*)<`).exec(HTML);   // 화면이 열린 때의 문구(html 에 적힌 글)
      if (m) e.textContent = m[1];
      e.addEventListener = (ev, fn) => { (h[ev] = h[ev] || []).push(fn); };
      e.click = () => (h.click || []).forEach((fn) => fn({ preventDefault() {} }));
      els[id] = e;
    }
    return els[id];
  };
  const urls = [];
  const RealDate = Date;
  class FixedDate extends RealDate { static now() { return FUT_KLINES.fetched_at_ms; } }
  const ctx = {
    document: { readyState: "complete", getElementById: getEl, createElement: () => makeEl(""), addEventListener() {}, querySelectorAll: () => [] },
    fetch: fakeServer(urls),
    Date: FixedDate,
    setTimeout: (fn) => { fn(); return 0; },
    devicePixelRatio: 1,
    Blob: class {},
    URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
    console,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  ctx.addEventListener = () => {};
  getEl("days").value = String(FUT_KLINES.days);
  getEl("src").value = FUT_KLINES.interval;
  for (const [k, v] of Object.entries(overrides)) getEl(k).value = String(v);
  vm.createContext(ctx);
  vm.runInContext(BT_JS, ctx);
  vm.runInContext(UI_JS, ctx);
  // mountPage 가 부르는 /v2/api/status · /v2/api/params/last-saved(1121-03 A1)는 가짜 서버가 거절한다(화면은 기본값) —
  // 시험이 세는 바깥 요청에서 뺀다(둘 다 같은 출처 v2 서버 주소)
  const outer = () => urls.filter((u) => !String(u).startsWith("/v2/api/status") && !String(u).startsWith("/v2/api/params/last-saved"));
  return { ctx, el: getEl, urls, outer, v: (name) => vm.runInContext(name, ctx) };
}

test("N7 기본값 고정: 분할 1 · 익절 3 · 손절 3 · 스윕 범위는 Ver9 값 · 둔화 허용치 축", () => {
  const d = DEFAULTS;
  assert.equal(d.maxSplits.value, "1");
  assert.equal(d.tp.value, "3");
  assert.equal(d.sl.value, "3");
  assert.deepEqual([d.sw_slFrom.value, d.sw_slTo.value], ["1", "5"]);
  assert.deepEqual([d.sw_spFrom.value, d.sw_spTo.value, d.sw_spStep.value], ["1", "1", "1"]);
  assert.deepEqual([d.sw_ma60From.value, d.sw_ma60To.value], ["0", "1"]);
  assert.deepEqual([d.sw_dropFrom.value, d.sw_dropTo.value, d.sw_dropStep.value], ["0", "0.4", "0.1"]);
  assert.deepEqual([d.futMode.value, d.cUseSl.value, d.useFunding.value], ["A", "no", "yes"]);
  assert.deepEqual(d.futMode.options, ["A", "B", "C"]);
  assert.match(HTML, /선물 백테스트\(롱\+숏\)/);
  assert.match(HTML, /바이낸스 USDT 무기한 선물 시세와 펀딩비로 계산합니다\. 업비트 원화 시세가 아닙니다\. 추적 손절은 현물에만 적용됩니다/);
  assert.match(HTML, /<h3>스윕 결과 \(상위 10\)<\/h3>/);
  assert.match(HTML, /최대 20,000개 조합/);
  for (const id of ["chartBox", "fsBtn", "chartWrap"]) assert.ok(HTML.includes(`id="${id}"`), id);
  assert.match(HTML, /#chartBox\.fs\{position:fixed/);
  assert.match(HTML, /body\.chart-fs\{overflow:hidden\}/);
  assert.match(HTML, /id="chartWrap" style="overflow:hidden/);
  assert.match(HTML, /touch-action:pan-y/);
  // 지키는 것: 요약 카드 · 저장 창 · 스크립트 순서 · −/+ 단추 36px
  assert.match(HTML, /\.stepper \.stepBtn\{display:block;width:36px/);
  assert.ok(HTML.includes('id="saveArea"'));
});

test("N4 업비트 출처에서는 선물이 막힌다: 바깥 요청 0건 · 오류 문구 · 단추 disabled", async () => {
  const p = page();
  assert.equal(p.el("dataSource").value, "upbit");
  assert.equal(p.el("btFutBtn").disabled, true);
  assert.equal(p.el("btFutNote").hidden, false);
  assert.match(p.el("btFutNote").textContent, /선물은 바이낸스 출처에서만 됩니다/);
  await p.ctx.runFutures();
  assert.match(p.el("status").textContent, /선물은 바이낸스 출처에서만 됩니다/);
  await assert.rejects(p.ctx.fetchKlines("KRW-JTO", "3m", 9, "futures"), /선물은 바이낸스 출처에서만 됩니다/);
  assert.deepEqual(p.outer(), []);
  // 바이낸스로 바꾸면 풀린다
  p.el("btSrcBinance").click();
  assert.equal(p.el("btFutBtn").disabled, false);
  assert.equal(p.el("btFutNote").hidden, true);
  p.el("btSrcUpbit").click();
  assert.equal(p.el("btFutBtn").disabled, true);
});

async function binanceFutures(p, overrides = NARROW_SWEEP) {
  p.el("btSrcBinance").click();
  for (const [k, v] of Object.entries(overrides)) p.el(k).value = String(v);
  await p.ctx.runFutures();
}

test("N8 비동기 선물 · 스윕이 끝난 뒤 요약 카드가 실제 결과로 그려진다(현물/선물 표시 포함)", async () => {
  const p = page();
  await binanceFutures(p);
  assert.ok(!p.el("status").textContent.includes("오류"), p.el("status").textContent);
  assert.match(p.el("btBrief").innerHTML, /총 수익률/);
  assert.doesNotMatch(p.el("btBrief").innerHTML, /결과 없음/);
  assert.match(p.el("btBriefMode").textContent, /선물\(롱\+숏\) · 바이낸스 USDT/);
  assert.equal(p.v("lastMode"), "futures");
  assert.equal(p.el("btRunBtn").disabled, false);
  assert.equal(p.el("btFutBtn").disabled, false);
  // 스윕: 끝나기 전에는 카드가 비어 있고, await 로 끝난 뒤 목록으로 그려진다
  const pending = p.ctx.runSweep();
  assert.equal(p.v("sweepRows.length"), 0, "스윕 시작 직후 sweepRows 는 비어 있음(옛 동기 읽기가 놓치던 자리)");
  await pending;
  assert.equal(p.v("sweepRows.length"), 36);
  const h = p.el("sweepBrief").innerHTML;
  assert.equal((h.match(/<tr><td>/g) || []).length, 5);
  assert.match(h, /60선 기울기/);
  assert.match(p.el("sweepBriefMode").textContent, /선물/);
  // 현물 실행도 같은 카드
  p.el("btSrcUpbit").click();
  p.el("btSrcBinance").click();
  await p.ctx.run();
  assert.equal(p.v("lastMode"), "spot");
  assert.match(p.el("btBriefMode").textContent, /^현물 · 바이낸스$/);
  assert.match(p.el("btBrief").innerHTML, /총 수익률/);
});

test("N5 출처를 바꾸면 선물 캐시 · 직전 결과 · 화면 결과가 처음 상태로 돌아간다", async () => {
  const p = page();
  const hint0 = p.el("sweepHint").textContent;
  const chart0 = p.el("chartHint").textContent;
  await binanceFutures(p);
  await p.ctx.runSweep();
  assert.notEqual(p.v("futCache"), null);
  assert.notEqual(p.v("lastBars"), null);
  assert.ok(p.v("sweepRows.length") > 0);
  assert.notEqual(p.el("chartHint").textContent, chart0);   // 차트가 그려졌다

  p.el("btSrcUpbit").click();                                 // 출처 바뀜
  assert.equal(p.v("futCache"), null);
  assert.equal(p.v("dataCache"), null);
  assert.equal(p.v("lastBars"), null);
  assert.equal(p.v("lastResults"), null);
  assert.equal(p.v("sweepRows.length"), 0);
  assert.equal(p.v("tradeRows.length"), 0);
  assert.equal(p.v("lastMode"), "spot");
  assert.match(p.el("btBrief").innerHTML, /결과 없음/);
  assert.equal(p.el("btBriefMode").textContent, "");
  assert.match(p.el("sweepBrief").innerHTML, /스윕을 실행/);
  for (const id of ["summary", "depth", "weekly", "monthly", "sweepResult"]) assert.equal(p.el(id).innerHTML, "", id);
  assert.equal(p.el("sweepHint").textContent, hint0);   // 「먼저 … 실행」 안내
  assert.equal(p.el("chartHint").textContent, chart0);  // 차트를 처음 상태로
  assert.equal(p.el("status").textContent, "준비되었습니다.");

  // 같은 출처를 다시 누르면 지우지 않는다
  p.ctx.run = p.ctx.run;
  vm.runInContext('lastBars = [1]; sweepRows = [{tp:1}];', p.ctx);
  p.el("btSrcUpbit").click();
  assert.equal(p.v("lastBars.length"), 1);
});

test("N10 선물을 돌린 뒤 업비트로 바꾸면 저장 창은 업비트 출처 현재 입력값만 보이고 화면 결과는 비어 있다", async () => {
  const p = page();
  await binanceFutures(p);
  p.el("btSrcUpbit").click();
  // 화면 결과는 비워져 있다
  assert.equal(p.v("lastResults"), null);
  assert.match(p.el("btBrief").innerHTML, /결과 없음/);
  // 저장 창이 모으는 값(창을 열 때 고른 출처 + 현재 입력칸)
  const sctx = { globalThis: null, document: undefined, window: undefined, console };
  sctx.globalThis = sctx;
  vm.createContext(sctx);
  vm.runInContext(SAVE_JS, sctx);
  const S = sctx.__v2save;
  const snap = S.makeSnapshot((id) => p.el(id));
  assert.equal(snap.source, "upbit");
  assert.equal(snap.params.symbol, "KRW-JTO");
  assert.match(S.testedText(snap), /^시험한 데이터: 업비트 · KRW-JTO/);
  assert.equal(S.runBtnLabel(snap.source), "이 설정으로 동작");
  // 선물 3칸은 저장 본문에 실리지 않는다
  const body = JSON.parse(S.snapshotBody(snap));
  for (const k of ["futMode", "cUseSl", "useFunding"]) assert.ok(!(k in body.params), k);
});

test("N9 스윕 카드: TP · SL · 분할이 같고 기울기(또는 둔화)만 다른 두 줄은 글자가 다르다", () => {
  const rows = [
    { tp: 3, sl: 3, maxSplits: 1, ma60MinSlope: 0.1, ma60SlopeDrop: 0, returnPct: 5 },
    { tp: 3, sl: 3, maxSplits: 1, ma60MinSlope: 0.2, ma60SlopeDrop: 0, returnPct: 5 },
    { tp: 3, sl: 3, maxSplits: 1, ma60MinSlope: 0.2, ma60SlopeDrop: 0.3, returnPct: 5 },
  ];
  const html = B.sweepHtml(B.sweepBrief(rows, 3).map((r) => J(r)));
  const trs = html.split("</tr>").filter((x) => x.includes("<td>")).map((x) => x.replace(/^.*<tr>/, ""));
  assert.equal(trs.length, 3);
  assert.equal(new Set(trs).size, 3, trs.join("\n"));
  assert.match(html, /<th>60선 기울기<\/th><th>둔화 허용치<\/th>/);
});

test("N11 실행 · 선물 · 스윕이 도는 동안에는 출처를 바꾸지 않는다(끝난 결과가 새 출처 화면에 다시 채워지는 틈 막기)", async () => {
  const p = page();
  const info0 = p.el("chartInfo").textContent;
  p.el("btSrcBinance").click();
  for (const [k, v] of Object.entries(NARROW_SWEEP)) p.el(k).value = String(v);
  // 선물 실행 중 업비트 누름 → 바뀌지 않고 안내
  const fut = p.ctx.runFutures();
  p.el("btSrcUpbit").click();
  assert.equal(p.el("dataSource").value, "binance");
  assert.match(p.el("status").textContent, /실행 중에는 출처를 바꿀 수 없습니다/);
  await fut;
  assert.equal(p.v("lastMode"), "futures");
  assert.match(p.el("btBriefMode").textContent, /선물\(롱\+숏\) · 바이낸스 USDT/);
  // 스윕 중 업비트 누름 → 바뀌지 않고 스윕이 끝까지 돈다
  const sw = p.ctx.runSweep();
  p.el("btSrcUpbit").click();
  assert.equal(p.el("dataSource").value, "binance");
  await sw;
  assert.equal(p.v("sweepRows.length"), 36);
  // 현물 실행 중도 같다
  const sp = p.ctx.run();
  p.el("btSrcUpbit").click();
  assert.equal(p.el("dataSource").value, "binance");
  await sp;
  // 모두 끝난 뒤에는 바뀌고 결과가 비워진다
  p.el("btSrcUpbit").click();
  assert.equal(p.el("dataSource").value, "upbit");
  assert.equal(p.v("lastResults"), null);
  assert.match(p.el("btBrief").innerHTML, /결과 없음/);
  assert.equal(p.el("chartInfo").textContent, info0);   // 차트 정보 줄도 처음 문구로
});

test("N12 스윕이 도는 동안 실행 · 선물은 시작하지 않고, 실행 중에는 스윕을 시작하지 않는다(현물 · 선물 결과 섞임 막기)", async () => {
  const p = page();
  await binanceFutures(p);
  const sw = p.ctx.runSweep();
  const n0 = p.urls.length;
  // 사이에 await 를 두면 가짜 타이머라 스윕이 먼저 끝나 버린다 — 스윕이 도는 같은 순간에 부른다
  const before = p.v("lastResults");
  const r1 = p.ctx.run();          // 스윕 중 → 바로 돌아옴
  const r2 = p.ctx.runFutures();   // 스윕 중 → 바로 돌아옴
  assert.equal(p.el("status").textContent, "스윕이 끝난 뒤 실행해 주세요");
  await Promise.all([r1, r2]);
  assert.equal(p.urls.length, n0, "스윕 중에는 새 요청이 없다");
  assert.equal(p.v("lastResults"), before, "스윕 중 실행 · 선물이 결과를 바꾸지 않았다");
  await sw;
  assert.equal(p.v("sweepRows.length"), 36);
  assert.equal(p.v("lastMode"), "futures");
  // 선물 실행 중 스윕 → 바로 돌아오고 sweepRows 는 그대로
  vm.runInContext("sweepRows = [];", p.ctx);
  const fut = p.ctx.runFutures();
  await p.ctx.runSweep();
  assert.equal(p.v("sweepRows.length"), 0);
  assert.equal(p.el("sweepStatus").textContent, "실행이 끝난 뒤 스윕해 주세요");
  await fut;
});
