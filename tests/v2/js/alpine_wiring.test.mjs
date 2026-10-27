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
// go() 가 history.replaceState 로 남기는 주소 #탭 — 시험용 대역
globalThis.location = { hash: "" };
globalThis.history = { replaceState(_s, _t, url) { globalThis.location.hash = url; } };
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

  const upbitResponses = [200, 200, 429, 200];
  const upbitUrls = [];
  let upbitCalls = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.startsWith("https://api.upbit.com/")) {
      upbitUrls.push(u);
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
    assert.deepEqual(watched, [], "차트 높이 맞춤 감시 없음");
    await flush(); await flush();
    assert.equal(d.status.ticker, "KRW-ZRO");

    // (1) 첫 차트 열림: 업비트 응답 1건 -> 그려진다
    d.go("chart");
    await flush(); await flush();
    assert.equal(upbitCalls, 1);
    assert.ok(setDataCalls >= 1, "첫 응답이 그려지지 않음");
    assert.equal(chartEl.style.height, undefined, "inline 높이를 넣지 않는다(CSS 높이만)");
    // 머리 막대 제목은 봉 원문(minute3)이 아니라 단추 줄 첫 칸과 같은 「3분」 (최종 검수 수정 2026-10-27)
    assert.equal(d.chartUnitLabel, "3분");
    assert.equal(d.tabTitle, "차트 · KRW-ZRO · 3분");

    // (1-2) 공유 문이 열린 뒤(10초) 더 오래된 200봉을 받는다: to= 가 가장 오래된 봉 시각
    assert.ok(!upbitUrls[0].includes("&to="));
    const olderRetry = timeouts.filter((t) => t.ms > 0 && t.ms <= 10_100).pop();
    assert.ok(olderRetry, "오래된 봉 요청 타이머 없음");
    nowMs += 11_000;
    olderRetry.fn();
    await flush(); await flush();
    assert.equal(upbitCalls, 2);
    assert.ok(upbitUrls[1].includes("&to=2026-10-23T03%3A00%3A00Z"), upbitUrls[1]);

    // (2) 30초 뒤 429 -> 「갱신 실패 · HH:MM:SS」, 마지막 데이터 유지
    const before = setDataCalls;
    nowMs += 31_000;
    const thirty = intervals.filter((i) => i.ms === 30000).pop();
    thirty.fn();
    await flush(); await flush();
    assert.equal(upbitCalls, 3);
    assert.match(d.chartFail, /^갱신 실패 · \d\d:\d\d:\d\d$/);
    assert.equal(setDataCalls, before);

    // (3) 탭을 바로 오가면 10초 게이트에 막히고, 게이트가 열린 뒤 재시도로 1건 더 나간다
    d.go("home");
    d.go("chart");
    await flush(); await flush();
    assert.equal(upbitCalls, 3, "게이트 안에서 요청이 나감");
    const retry = timeouts.filter((t) => t.ms > 0 && t.ms <= 10_100).pop();
    assert.ok(retry, "재시도 타이머 없음");
    nowMs += 11_000;
    retry.fn();
    await flush(); await flush();
    assert.equal(upbitCalls, 4);
    assert.ok(!upbitUrls[3].includes("&to="), "오래된 봉을 모두 받은 뒤에는 최신 200봉만");

    // (4) PC 에서도 휴대폰과 같은 크기 — 높이 맞춤 함수가 없고, go() 는 주소 #탭을 남긴다
    assert.equal(d.fitChart, undefined);
    assert.equal(chartEl.style.height, undefined);
    d.go("logs");
    assert.equal(globalThis.location.hash, "#logs");
  } finally {
    Date.now = realNow;
    globalThis.setTimeout = realST;
    globalThis.setInterval = realSI;
    globalThis.clearTimeout = realCT;
    globalThis.clearInterval = realCI;
  }
});

test("tabFromHash: 알려진 탭만 인정, 모르는 값·#backtester 는 home", () => {
  const f = globalThis.tabFromHash;
  assert.equal(typeof f, "function");
  assert.equal(f("#logs"), "logs");
  assert.equal(f("#chart"), "chart");
  assert.equal(f("#ops"), "ops");
  assert.equal(f("#home"), "home");
  assert.equal(f("#backtester"), "home");
  assert.equal(f("#nope"), "home");
  assert.equal(f(""), "home");
  assert.equal(f(undefined), "home");
});

test("index.html 아래 메뉴 순서: 홈·차트·백테스터·로그·운용, 백테스터만 링크", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  const nav = html.slice(html.indexOf('<nav class="bottom"'), html.indexOf("</nav>"));
  const labels = [...nav.matchAll(/<(?:button|a)\b[^>]*>([^<]+)<\/(?:button|a)>/g)].map((m) => m[1].trim());
  assert.deepEqual(labels, ["홈", "차트", "백테스터", "로그", "운용"]);
  assert.match(nav, /<a [^>]*href="\/v2\/static\/backtester\.html"[^>]*>백테스터<\/a>/);
  assert.equal((nav.match(/<button\b/g) || []).length, 4);
});

test("index.html: 옛 #basic 자리 없음, #pause-row 1개, 머리 막대 #logout-btn 1개", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  assert.equal((html.match(/id="basic"/g) || []).length, 0);
  assert.equal((html.match(/id="pause-row"/g) || []).length, 1);
  assert.equal((html.match(/id="logout-btn"/g) || []).length, 1);
  assert.match(html, /<header class="bar"/);
  assert.match(html, /신버전 대시보드/);
  // 머리 막대에서 「다시 로그인」 안내를 지운다(운용 탭 구버전 카드의 문장은 Task 5 몫)
  const head = html.slice(html.indexOf("<body"), html.indexOf("<main>"));
  assert.doesNotMatch(head, /다시 로그인해야 합니다/);
  assert.doesNotMatch(head, /class="top-row"/);
  // 그림 2-가 「투자자님 · 구버전으로 · 로그아웃」: 세 항목 사이 「·」 2개, 이름 없으면 첫 「·」 숨김 (최종 검수 수정 2026-10-27)
  const right = head.slice(head.indexOf('class="bar-right"'), head.indexOf('id="logout-btn"'));
  const seps = right.match(/<span class="bar-sep"[^>]*>·<\/span>/g) || [];
  assert.equal(seps.length, 2);
  assert.match(seps[0], /x-show="displayName"/);
  assert.match(seps[0], /aria-hidden="true"/);
  assert.ok(right.indexOf("님'") < right.indexOf("bar-sep"));
  assert.ok(right.lastIndexOf("bar-sep") > right.indexOf("구버전으로"));
});

test("index.html 운용 탭: 그림 2-마 카드 4개·단추 6개 모두 disabled·안내 한 줄·구버전 카드 없음", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  const s = html.indexOf("tab === 'ops'");
  const e = html.indexOf("</main>", s);
  const block = html.slice(s, e);
  const btns = [...block.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)];
  assert.deepEqual(btns.map((m) => m[2].replace(/<[^>]+>/g, "").trim()),
    ["백테스터 규칙으로 전환", "기존 전략으로 복귀 (지금은 해당 없음)", "일시정지", "엔진 정지", "강제 매수", "강제 매도"]);
  for (const m of btns) assert.match(m[1], /\bdisabled\b/);
  assert.equal((block.match(/2차 공개 때 열립니다/g) || []).length, 1);
  assert.equal((block.match(/매매 중지\/재개는 홈 화면 위 단추로 합니다/g) || []).length, 1);
  for (const h of ["매매 전략", "엔진", "긴급 개입", "운용 설정"]) assert.match(block, new RegExp("<h2>" + h + "</h2>"));
  assert.match(block, /거래 시간 제한 등 \(새 전략 운용 중일 때 여기서 바꿉니다\)/);
  assert.match(block, /지금 전략/);
  assert.doesNotMatch(block, /<h2>구버전<\/h2>/);
  assert.doesNotMatch(block, /다시 로그인해야 합니다/);
});

