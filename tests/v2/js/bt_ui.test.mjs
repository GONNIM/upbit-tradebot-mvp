// bt_ui.js(백테스터 화면: 출처 토글·업비트 서버 수집·요약·스윕 요약·중복 실행 막기) 시험.
// 브라우저·네트워크 없이 vm + 가짜 fetch/시계. 업비트 주소는 어디서도 부르지 않는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { parseDefaults } from "./harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
const STATIC = path.join(ROOT, "v2/static");
const BT_SRC = fs.readFileSync(path.join(STATIC, "bt_ui.js"), "utf8");
const HTML = fs.readFileSync(path.join(STATIC, "backtester.html"), "utf8");

function load() {
  const ctx = { globalThis: null, document: undefined, window: undefined, console };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(BT_SRC, ctx);
  return ctx.__v2bt;
}
const B = load();

const J = (x) => JSON.parse(JSON.stringify(x));   // vm 컨텍스트 값은 prototype 이 달라 deepStrictEqual 전에 평탄화
const res = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });

// 가짜 시계: sleep 이 시간을 앞으로 보낸다
function clock() {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; }, get t() { return t; } };
}

// 경로별 응답 대기열 가짜 fetch
function router(routes) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, opts });
    const key = String(url).split("?")[0];
    const q = routes[key];
    if (!q || !q.length) throw new Error("가짜 fetch: 응답 없음 " + url);
    const r = q.length > 1 ? q.shift() : q[0];
    if (r instanceof Error) throw r;
    return r;
  };
  fn.calls = calls;
  return fn;
}

const CANDLES = "/v2/api/candles";
const PROGRESS = "/v2/api/candles/progress";
const BARS = [[1000, 1, 2, 0.5, 1.5], [2000, 1.5, 2.5, 1, 2]];

test("(a) upbitCallCount: 1m·30일=216, 3m=72", () => {
  assert.equal(B.upbitCallCount("1m", 30), 216);
  assert.equal(B.upbitCallCount("3m", 30), 72);
  assert.equal(B.upbitCallCount("5m", 30), 44);
  assert.equal(B.upbitCallCount("1h", 30), 4);
});

test("(b) 200 -> [t,o,h,l,c] 가 {t,o,h,l,c} 로, 같은 출처 주소·credentials same-origin", async () => {
  const f = router({ [CANDLES]: [res(200, { bars: BARS })] });
  const c = clock();
  const out = await B.fetchUpbitKlines("KRW-JTO", "1m", 30, { fetchFn: f, sleepFn: c.sleep, nowFn: c.now });
  assert.deepEqual(J(out), [{ t: 1000, o: 1, h: 2, l: 0.5, c: 1.5 }, { t: 2000, o: 1.5, h: 2.5, l: 1, c: 2 }]);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].url, "/v2/api/candles?market=KRW-JTO&unit=1&days=30");
  assert.equal(f.calls[0].opts.credentials, "same-origin");
  assert.ok(f.calls.every((x) => !String(x.url).includes("api.upbit.com")));
});

test("(b2) 봉 단위 -> unit: 3m=3, 5m=5, 1h=60", async () => {
  for (const [src, unit] of [["3m", 3], ["5m", 5], ["1h", 60]]) {
    const f = router({ [CANDLES]: [res(200, { bars: [] })] });
    const c = clock();
    await B.fetchUpbitKlines("KRW-JTO", src, 7, { fetchFn: f, sleepFn: c.sleep, nowFn: c.now });
    assert.equal(f.calls[0].url, `/v2/api/candles?market=KRW-JTO&unit=${unit}&days=7`);
  }
});

test("(c) 202 -> progress 3회(마지막 active false) -> 같은 GET 다시 -> 200, onProgress 3회", async () => {
  const f = router({
    [CANDLES]: [res(202, { job: "running", progress: { market: "KRW-JTO", unit: 1, done: 0, total: 216 } }), res(200, { bars: BARS })],
    [PROGRESS]: [
      res(200, { active: true, kind: "user", market: "KRW-JTO", unit: 1, done: 50, total: 216, error: null }),
      res(200, { active: true, kind: "user", market: "KRW-JTO", unit: 1, done: 150, total: 216, error: null }),
      res(200, { active: false, kind: "user", market: "KRW-JTO", unit: 1, done: 216, total: 216, error: null }),
    ],
  });
  const c = clock();
  const seen = [];
  const out = await B.fetchUpbitKlines("KRW-JTO", "1m", 30, {
    fetchFn: f, sleepFn: c.sleep, nowFn: c.now, pollMs: 2000, onProgress: (d, t) => seen.push([d, t]),
  });
  assert.equal(out.length, 2);
  assert.deepEqual(seen, [[50, 216], [150, 216], [216, 216]]);
  assert.equal(f.calls.filter((x) => String(x.url).startsWith(CANDLES + "?")).length, 2);
  assert.equal(f.calls.filter((x) => x.url === PROGRESS).length, 3);
  assert.equal(c.t, 6000);
});

test("(c2) progress 가 미리 받기(prefetch)·다른 종목이면 기다리지 않고 같은 GET 다시", async () => {
  for (const prog of [
    { active: true, kind: "prefetch", market: "KRW-JTO", unit: 1, done: 10, total: 216, error: null },
    { active: true, kind: "user", market: "KRW-XRP", unit: 1, done: 10, total: 216, error: null },
    { active: true, kind: "user", market: "KRW-JTO", unit: 3, done: 10, total: 72, error: null },
  ]) {
    const f = router({
      [CANDLES]: [res(202, { job: "running" }), res(200, { bars: BARS })],
      [PROGRESS]: [res(200, prog)],
    });
    const c = clock();
    const seen = [];
    const out = await B.fetchUpbitKlines("KRW-JTO", "1m", 30, {
      fetchFn: f, sleepFn: c.sleep, nowFn: c.now, onProgress: (d, t) => seen.push([d, t]),
    });
    assert.equal(out.length, 2);
    assert.equal(f.calls.filter((x) => x.url === PROGRESS).length, 1);
    assert.deepEqual(seen, []);   // 내 작업이 아니면 진행 표시를 안 함
  }
});

const M_BUSY = "다른 업비트 데이터 수집이 진행 중입니다 (12 / 216회). 끝난 뒤 다시 눌러 주세요";
const M_LIMIT = "업비트 요청 한도 — 약 60초 뒤 다시 시도해 주세요";
const M_BLOCK = "업비트가 요청을 막았습니다. 운영자 확인이 필요합니다(바이낸스 데이터는 쓸 수 있습니다)";
const M_ERR = "업비트 데이터를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요";
const M_AUTH = "구버전에서 다시 들어와 주세요";

test("(d) 상태별 문구로 멈춤", async () => {
  const cases = [
    [res(409, { error: "busy", progress: { market: "KRW-XRP", unit: 1, done: 12, total: 216 } }), M_BUSY],
    [res(429, { error: "upbit_limit", retry_after: 60 }), M_LIMIT],
    [res(503, { error: "upbit_blocked" }), M_BLOCK],
    [res(503, { error: "db_unavailable" }), M_ERR],
    [res(502, { error: "upbit_error" }), M_ERR],
    [res(504, {}), M_ERR],
    [res(401, {}), M_AUTH],
    [res(403, {}), M_AUTH],
    [new Error("network"), M_ERR],
  ];
  for (const [r, msg] of cases) {
    const f = router({ [CANDLES]: [r] });
    const c = clock();
    await assert.rejects(
      B.fetchUpbitKlines("KRW-JTO", "1m", 30, { fetchFn: f, sleepFn: c.sleep, nowFn: c.now }),
      (e) => { assert.equal(e.message, msg); return true; },
    );
    assert.equal(f.calls.length, 1);   // 브라우저는 다시 시도하지 않음
  }
});

test("(d2) progress error 칸 -> 문구, 5분 상한 -> 일반 오류", async () => {
  for (const [err, msg] of [["upbit_limit", M_LIMIT], ["upbit_blocked", M_BLOCK], ["upbit_error", M_ERR]]) {
    const f = router({
      [CANDLES]: [res(202, { job: "running" })],
      [PROGRESS]: [res(200, { active: false, kind: "user", market: "KRW-JTO", unit: 1, done: 3, total: 216, error: err, retry_after: 60 })],
    });
    const c = clock();
    await assert.rejects(
      B.fetchUpbitKlines("KRW-JTO", "1m", 30, { fetchFn: f, sleepFn: c.sleep, nowFn: c.now }),
      (e) => { assert.equal(e.message, msg); return true; },
    );
  }
  const f = router({
    [CANDLES]: [res(202, { job: "running" })],
    [PROGRESS]: [res(200, { active: true, kind: "user", market: "KRW-JTO", unit: 1, done: 1, total: 216, error: null })],
  });
  const c = clock();
  await assert.rejects(
    B.fetchUpbitKlines("KRW-JTO", "1m", 30, { fetchFn: f, sleepFn: c.sleep, nowFn: c.now }),
    (e) => { assert.equal(e.message, M_ERR); return true; },
  );
  assert.ok(c.t >= 300000 && c.t <= 304000, String(c.t));
});

test("(e) briefSummary: 총 수익률·거래 수 / 승률·최대 낙폭", () => {
  const rows = B.briefSummary({ ret: 6.2, trades: 14, winRate: 64.3, mdd: 4.1 });
  assert.deepEqual(J(rows.map((r) => r.label)), ["총 수익률", "거래 수 / 승률", "최대 낙폭"]);
  assert.deepEqual(J(rows.map((r) => r.value)), ["+6.2%", "14회 / 64%", "-4.1%"]);
  assert.equal(rows[0].cls, "up");
  assert.equal(rows[2].cls, "dn");
  const neg = B.briefSummary({ ret: -3.04, trades: 0, winRate: 0, mdd: 0 });
  assert.equal(neg[0].value, "-3.0%");
  assert.equal(neg[0].cls, "dn");
  assert.equal(neg[1].value, "0회 / 0%");
  assert.equal(neg[2].value, "0.0%");
});

test("sweepBrief: 상위 n 개 {tp,sl,maxSplits,ret}, 기본 5", () => {
  const rows = [];
  for (let i = 0; i < 8; i++) rows.push({ tp: i, sl: 3, maxSplits: 5, trades: 1, returnPct: 8 - i, mdd: 1 });
  const out = B.sweepBrief(rows);
  assert.equal(out.length, 5);
  assert.deepEqual(J(out[0]), { tp: 0, sl: 3, maxSplits: 5, ret: 8 });
  assert.equal(B.sweepBrief(rows, 2).length, 2);
  assert.deepEqual(J(B.sweepBrief([])), []);
});

test("briefHtml·sweepHtml: 결과 없음·표", () => {
  assert.match(B.briefHtml(null), /결과 없음/);
  const h = B.briefHtml(B.briefSummary({ ret: 6.2, trades: 14, winRate: 64.3, mdd: 4.1 }));
  assert.match(h, /총 수익률/);
  assert.match(h, /class="up">\+6\.2%/);
  assert.match(B.sweepHtml([]), /스윕을 실행/);
  const t = B.sweepHtml([{ tp: 5, sl: 3, maxSplits: 5, ret: 6.2 }]);
  assert.match(t, /<th>TP<\/th><th>SL<\/th><th>분할<\/th>/);
  assert.match(t, /\+6\.2%/);
});

test("봉 단위 기본값: 엔진 interval -> 1m·3m·5m·1h, 그 밖은 3m", () => {
  assert.equal(B.srcFromInterval("minute1"), "1m");
  assert.equal(B.srcFromInterval("minute3"), "3m");
  assert.equal(B.srcFromInterval("minute5"), "5m");
  assert.equal(B.srcFromInterval("minute60"), "1h");
  assert.equal(B.srcFromInterval("minute15"), "3m");
  assert.equal(B.srcFromInterval(undefined), "3m");
});

// ---- install: window 의 fetchKlines·run·runSweep 감싸기 (가짜 window·요소) ----
function fakeEnv(opts = {}) {
  const els = {};
  const el = (id) => (els[id] = els[id] || { value: "", textContent: "", innerHTML: "", hidden: false, disabled: false });
  el("dataSource").value = opts.source || "upbit";
  el("symbol").value = opts.symbol || "KRW-JTO";
  el("src").value = "1m";
  el("days").value = "30";
  const state = { lastResults: null, lastCfgBase: { capital: 100 }, sweepRows: [] };
  const calls = { orig: 0, run: 0, sweep: 0 };
  let release;
  const win = {
    fetchKlines: async () => { calls.orig++; return "BINANCE"; },
    run: async () => { calls.run++; if (opts.onRun) await opts.onRun(state); },
    runSweep: () => { calls.sweep++; if (opts.onSweep) opts.onSweep(state); },
  };
  return { els, el, state, calls, win, release: () => release && release() };
}

function installOn(env, extra = {}) {
  const c = clock();
  const f = extra.fetchFn || router({ [CANDLES]: [res(200, { bars: BARS })] });
  B.install({
    win: env.win, getEl: env.el, getState: () => env.state,
    statsFn: (r) => ({ ret: r.ret, trades: r.trades, winRate: r.winRate, mdd: r.mdd }),
    fetchFn: f, sleepFn: c.sleep, nowFn: c.now,
  });
  return f;
}

test("install: 출처 업비트면 서버 경로, 바이낸스면 원래 fetchKlines", async () => {
  const env = fakeEnv();
  const f = installOn(env);
  const bars = await env.win.fetchKlines("KRW-JTO", "1m", 30);
  assert.equal(bars.length, 2);
  assert.equal(f.calls[0].url, "/v2/api/candles?market=KRW-JTO&unit=1&days=30");
  assert.equal(env.calls.orig, 0);
  assert.match(env.els.status.textContent, /계산 중/);

  const env2 = fakeEnv({ source: "binance", symbol: "JTOUSDT" });
  const f2 = installOn(env2);
  assert.equal(await env2.win.fetchKlines("JTOUSDT", "3m", 30), "BINANCE");
  assert.equal(f2.calls.length, 0);
  assert.equal(env2.calls.orig, 1);
});

test("install: 업비트 종목 형식 아니면 멈춤, 기간 30일 초과도 멈춤(서버 호출 없음)", async () => {
  const env = fakeEnv({ symbol: "JTOUSDT" });
  const f = installOn(env);
  await assert.rejects(env.win.fetchKlines("JTOUSDT", "1m", 30), /업비트 종목은 KRW-XXX 형식입니다/);
  await assert.rejects(env.win.fetchKlines("KRW-JTO", "1m", 31), /30일/);
  assert.equal(f.calls.length, 0);
});

test("install: 업비트 기간이 정수가 아니면(7.5) 서버 호출 없이 30일 문구로 멈춤", async () => {
  const env = fakeEnv();
  const f = installOn(env);
  await assert.rejects(env.win.fetchKlines("KRW-JTO", "1m", 7.5), /최대 30일/);
  await assert.rejects(env.win.fetchKlines("KRW-JTO", "1m", 0), /최대 30일/);
  assert.equal(f.calls.length, 0);
});

test("install: 진행 줄 «n / N회» 와 안내 한 줄", async () => {
  const env = fakeEnv();
  const f = router({
    [CANDLES]: [res(202, { job: "running" }), res(200, { bars: BARS })],
    [PROGRESS]: [res(200, { active: true, kind: "user", market: "KRW-JTO", unit: 1, done: 50, total: 216, error: null }),
      res(200, { active: false, kind: "user", market: "KRW-JTO", unit: 1, done: 216, total: 216, error: null })],
  });
  const seen = [];
  const c = clock();
  B.install({
    win: env.win, getEl: env.el, getState: () => env.state, statsFn: () => ({}),
    fetchFn: f, sleepFn: async (ms) => { seen.push(env.els.status.textContent + "|" + env.els.btNote.hidden); await c.sleep(ms); }, nowFn: c.now,
  });
  await env.win.fetchKlines("KRW-JTO", "1m", 30);
  assert.ok(seen.some((s) => /업비트 데이터 받는 중… 50 \/ 216회\|false/.test(s)), seen.join("\n"));
  assert.equal(env.els.btNote.hidden, true);
});

test("(f) 실행 중 run() 두 번째 호출은 원래 run 을 다시 부르지 않음", async () => {
  let go;
  const gate = new Promise((r) => { go = r; });
  const env = fakeEnv({ onRun: async () => { await gate; } });
  installOn(env);
  const p1 = env.win.run();
  const p2 = env.win.run();
  await p2;
  assert.equal(env.calls.run, 1);
  assert.equal(env.els.btRunBtn.disabled, true);
  go();
  await p1;
  assert.equal(env.els.btRunBtn.disabled, false);
  await env.win.run();   // 끝난 뒤에는 다시 실행됨
  assert.equal(env.calls.run, 2);
});

test("(h) run 이 lastResults 를 바꾸면 요약, 안 바꾸면 «결과 없음»", async () => {
  const env = fakeEnv({ onRun: (s) => { s.lastResults = { ret: 6.2, trades: 14, winRate: 64.3, mdd: 4.1 }; } });
  installOn(env);
  await env.win.run();
  assert.match(env.els.btBrief.innerHTML, /\+6\.2%/);
  assert.match(env.els.btBrief.innerHTML, /14회 \/ 64%/);

  // 같은 객체를 남기는 실패 실행(run 은 오류를 삼킴): 이전 요약을 지우고 결과 없음
  const env2 = fakeEnv({});
  env2.state.lastResults = { ret: 1, trades: 1, winRate: 100, mdd: 0 };
  installOn(env2);
  env2.el("btBrief").innerHTML = "OLD";
  await env2.win.run();
  assert.match(env2.els.btBrief.innerHTML, /결과 없음/);
  assert.doesNotMatch(env2.els.btBrief.innerHTML, /OLD/);
});

test("스윕 실행 뒤 상위 5개 요약", () => {
  const rows = [];
  for (let i = 0; i < 7; i++) rows.push({ tp: i + 1, sl: 3, maxSplits: 5, returnPct: 10 - i });
  const env = fakeEnv({ onSweep: (s) => { s.sweepRows = rows; } });
  installOn(env);
  env.win.runSweep();
  assert.equal(env.calls.sweep, 1);
  assert.equal((env.els.sweepBrief.innerHTML.match(/<tr><td>/g) || []).length, 5);
});

test("(g) bt_ui.js 원문에 api.upbit.com 없음", () => {
  assert.ok(!BT_SRC.includes("api.upbit.com"));
  assert.ok(!/https?:\/\//.test(BT_SRC));
});

// ---- backtester.html 배치 (그림 2-다) ----
test("backtester.html: 머리 막대·아래 메뉴·스크립트 순서", () => {
  assert.match(HTML, /<link rel="stylesheet" href="\/v2\/static\/style\.css">/);
  assert.match(HTML, /<header class="bar">[\s\S]*백테스터[\s\S]*<\/header>/);
  const nav = HTML.slice(HTML.indexOf('<nav class="bottom"'), HTML.indexOf("</nav>"));
  for (const [href, label] of [["/v2/#home", "홈"], ["/v2/#chart", "차트"], ["/v2/#logs", "로그"], ["/v2/#ops", "운용"]]) {
    assert.match(nav, new RegExp(`<a [^>]*href="${href}"[^>]*>${label}</a>`));
  }
  assert.match(nav, /<a [^>]*class="on"[^>]*>백테스터<\/a>/);
  const iJs = HTML.indexOf('<script src="backtester.js"></script>');
  const iUi = HTML.indexOf('<script src="bt_ui.js"></script>');
  const iSave = HTML.indexOf('<script src="save.js"></script>');
  assert.ok(iJs >= 0 && iUi > iJs && iSave > iUi);
});

test("backtester.html: 출처 토글·접힘 11개·카드·자세한 결과", () => {
  assert.match(HTML, /데이터 출처/);
  assert.match(HTML, /업비트 \(KRW\)/);
  assert.match(HTML, /바이낸스/);
  assert.match(HTML, /<select id="dataSource" hidden>/);
  assert.match(HTML, /<option value="binance" selected>/);
  assert.match(HTML, /<option value="upbit">/);
  for (const t of ["종목", "봉 단위 · 기간", "60선 / 200선", "분할 최대 횟수", "익절 TP %", "손절 SL %"]) {
    assert.ok(HTML.includes(t), t);
  }
  assert.match(HTML, /… 그 밖의 입력 11개\(접힘\)/);
  const m = /<details id="btMore"[^>]*>([\s\S]*?)<\/details>/.exec(HTML);
  assert.ok(m, "btMore");
  const inner = [...m[1].matchAll(/<(?:input|select)\b[^>]*\sid="([^"]+)"/g)].map((x) => x[1]).sort();
  assert.deepEqual(inner, ["buyOnGoldenCross", "capital", "deadcross", "compounding", "fee", "maType", "maxPullbackBuys", "minSlope", "pullbackP", "slopeDrop", "slopeLB"].sort());
  assert.match(HTML, /데이터 가져오기 \+ 백테스트/);
  assert.match(HTML, /id="btNote"[^>]*hidden/);
  assert.match(HTML, /다른 화면으로 가도 서버가 계속 받아 둡니다/);
  assert.match(HTML, /<h2>결과 요약<\/h2>/);
  assert.match(HTML, /여러 설정 비교 \(파라미터 스윕\)/);
  assert.match(HTML, /<details id="btDetail"[^>]*>/);
  assert.match(HTML, /자세한 결과/);
  assert.match(HTML, /CSV 받기/);
  assert.match(HTML, /설정 저장/);
  // 접힘 안으로 옮긴 원래 결과 구역이 id 그대로 남음
  for (const id of ["summary", "depth", "weekly", "monthly", "sweepResult", "chartWrap", "chartCanvas", "chartOverlay", "chartInfo", "chartLegend", "chartHint", "sweepHint", "sweepStatus"]) {
    assert.ok(HTML.includes(`id="${id}"`), id);
  }
  const detail = HTML.slice(HTML.indexOf('<details id="btDetail"'));
  for (const id of ["summary", "weekly", "monthly", "sweepResult", "chartWrap"]) {
    assert.ok(detail.indexOf(`id="${id}"`) > 0, id + " 가 자세한 결과 안");
  }
  assert.ok(HTML.includes("전략 로직 설명"));
  assert.ok(HTML.indexOf("전략 로직 설명") > HTML.indexOf('<details id="btDetail"'));
});

test("backtester.html: 입력 30개 id 가 모두 있고 기본값 그대로", () => {
  const p = parseDefaults(HTML);
  assert.equal(Object.keys(p).filter((i) => i !== "dataSource").length, 30);
  assert.equal(p.symbol.value, "JTOUSDT");
  assert.equal(p.src.value, "3m");
  assert.equal(p.days.value, "30");
});
