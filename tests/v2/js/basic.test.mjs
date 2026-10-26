// basic.js(기본 기능 블록) 순수 로직·컨트롤러 시험 + PC 넘김 스크립트 시험. 브라우저 없이 vm 으로 돌린다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
const STATIC = path.join(ROOT, "v2/static");
const INDEX = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
const BT = fs.readFileSync(path.join(STATIC, "backtester.html"), "utf8");

function load() {
  const ctx = { globalThis: null, document: undefined, window: undefined, console };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(STATIC, "basic.js"), "utf8"), ctx);
  return ctx.__v2basic;
}
const B = load();
// vm 안에서 만든 객체는 다른 realm 이라 deepStrictEqual 이 어긋난다 — 값만 비교하도록 복사해 돌려준다
for (const k of ["assetCells", "pnlCell", "modeNotice"]) {
  const f = B[k];
  B[k] = (...a) => { const r = f(...a); return r == null ? r : JSON.parse(JSON.stringify(r)); };
}

const STATUS = {
  engine: { level: "ok", ago_sec: 30 }, mode_engine: "LIVE", mode_entry: "LIVE", mode_mismatch: false,
  strategy: { value: "EMA", mtime: null }, ticker: "KRW-JTO", interval: "minute3", paused: false,
};
const ASSETS = { krw: 1234567.4, krw_locked: 0, coin: 10.5, coin_locked: 0, price: 1000, price_at: "x" };
const BASIC = {
  version: "v1.2026.10.25.1729", account: "mcmax33", last_status_log: "[2026-10-25 10:00:00] ✅ 엔진 시작",
  engine_running: true, pnl_kind: "unrealized", pnl_pct: 1.234,
};
const clone = (o) => JSON.parse(JSON.stringify(o));

// ---- fetch 대역 ----
function makeFetch(routes) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, method: (opts && opts.method) || "GET", body: opts && opts.body });
    const r = routes[url];
    const res = typeof r === "function" ? r(opts) : r;
    if (res instanceof Error) throw res;
    return { status: res.status, ok: res.status >= 200 && res.status < 300, json: async () => res.body };
  };
  fn.calls = calls;
  return fn;
}
const READ_OK = () => ({
  "/v2/api/status": { status: 200, body: clone(STATUS) },
  "/v2/api/assets": { status: 200, body: clone(ASSETS) },
  "/v2/api/basic": { status: 200, body: clone(BASIC) },
});

function makeCtl(over = {}) {
  const views = [];
  const nav = [];
  const state = { hidden: false, visible: true, now: 1_000_000_000_000, confirm: true, confirms: [] };
  const fetchFn = over.fetchFn || makeFetch(READ_OK());
  const ctl = B.createController({
    fetchFn,
    confirmFn: (t) => { state.confirms.push(t); return state.confirm; },
    nowFn: () => state.now,
    isHidden: () => state.hidden,
    isVisible: () => state.visible,
    render: (v) => views.push(v),
    navigate: (u) => nav.push(u),
  });
  return { ctl, views, nav, state, fetchFn, last: () => views[views.length - 1] };
}

test("kstClock: UTC+9 표기 YYYY-MM-DD HH:MM:SS", () => {
  assert.equal(B.kstClock(Date.UTC(2026, 9, 25, 3, 4, 5)), "2026-10-25 12:04:05");
  assert.equal(B.kstClock(Date.UTC(2026, 9, 25, 15, 0, 0)), "2026-10-26 00:00:00");
});

test("모드 안내: TEST 경고·LIVE 안내 문구가 구버전과 같다", () => {
  const t = B.modeNotice("TEST");
  assert.equal(t.kind, "warn");
  assert.equal(t.lead + t.rest,
    "🧪 TEST 모드 — 모든 매매는 시뮬레이션입니다. 실제 거래소 주문은 발생하지 않습니다. " +
    "audit_trades/orders에 기록되는 BUY/SELL은 가상 거래 결과입니다.");
  const l = B.modeNotice("live");
  assert.equal(l.kind, "info");
  assert.equal(l.lead + l.rest, "🔴 LIVE 모드 — 실제 Upbit 거래소에 주문이 전송됩니다.");
  assert.equal(B.modeNotice(null), null);
  assert.equal(B.modeNotice("X"), null);
});

test("제목·안내·최종 상태 로그·엔진 상태 문구", async () => {
  const { ctl, last } = makeCtl();
  await ctl.refresh(true);
  const v = last();
  assert.equal(v.title, "📊 Dashboard (LIVE) : mcmax33님 --- v1.2026.10.25.1729");
  assert.equal(v.info, "Upbit Trade Bot v1 상태 모니터링 페이지입니다.");
  assert.equal(v.log, "[2026-10-25 10:00:00] ✅ 엔진 시작");
  assert.equal(v.engine.label + " " + v.engine.value, "트레이딩 엔진 상태 Running 🟢");
  assert.match(v.clock, /^🕒 현재 시각: \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
  assert.equal(v.mismatch, "");
  assert.equal(v.pausedBanner, "");
});

test("엔진 상태: engine_running false → Stopped 🔴", async () => {
  const routes = READ_OK();
  routes["/v2/api/basic"] = { status: 200, body: { ...clone(BASIC), engine_running: false } };
  const { ctl, last } = makeCtl({ fetchFn: makeFetch(routes) });
  await ctl.refresh(true);
  assert.equal(last().engine.value, "Stopped 🔴");
  assert.equal(last().engine.running, false);
});

test("모드 불일치 경고와 엔진 모드가 제목에 쓰인다", async () => {
  const routes = READ_OK();
  routes["/v2/api/status"] = { status: 200, body: { ...clone(STATUS), mode_engine: "TEST", mode_entry: "LIVE", mode_mismatch: true } };
  const { ctl, last } = makeCtl({ fetchFn: makeFetch(routes) });
  await ctl.refresh(true);
  assert.match(last().title, /Dashboard \(TEST\)/);
  assert.equal(last().mismatch, "경고: 입장 모드(LIVE)와 엔진 모드(TEST)가 다릅니다.");
  assert.equal(last().notice.kind, "warn");
});

test("중지 배너와 단추 문구 전환(중지 ↔ 재개)", async () => {
  const routes = READ_OK();
  routes["/v2/api/status"] = { status: 200, body: { ...clone(STATUS), paused: true } };
  const { ctl, last } = makeCtl({ fetchFn: makeFetch(routes) });
  await ctl.refresh(true);
  assert.equal(last().pausedBanner,
    "⏸️ 매매 일시중지 상태 — 엔진과 지표는 정상 작동하지만 실주문(BUY/SELL)은 실행되지 않습니다. " +
    "재개하려면 아래 '▶️ 매매 재개' 버튼을 클릭하세요.");
  assert.equal(last().pauseBtn.label, "▶️ 매매 재개");
  const b = makeCtl();
  await b.ctl.refresh(true);
  assert.equal(b.last().pauseBtn.label, "⏸️ 매매 중지");
  assert.equal(b.last().pausedBanner, "");
});

test("확인 창 취소 시 요청이 없다", async () => {
  const m = makeCtl();
  await m.ctl.refresh(true);
  const before = m.fetchFn.calls.length;
  m.state.confirm = false;
  await m.ctl.togglePause();
  assert.equal(m.fetchFn.calls.length, before);
  assert.equal(m.state.confirms.length, 1);
});

test("확인 창 문구: 중지(모드·한계 명시)·재개", async () => {
  const m = makeCtl();
  await m.ctl.refresh(true);
  m.state.confirm = false;
  await m.ctl.togglePause();
  assert.equal(m.state.confirms[0],
    "매매를 중지합니다(모드: LIVE). 중지 중에는 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. " +
    "이미 걸려 있는 주문은 취소되지 않고, 미체결 지정가 매수가 시장가로 바뀌는 처리는 계속될 수 있습니다.");
  assert.equal(B.confirmText(false, "LIVE"), "매매를 재개합니다.");
});

test("중지 확인 → POST {paused:true}, 응답 전 단추 비활성, 응답 뒤 상태를 다시 읽는다", async () => {
  let paused = false;
  let release;
  const gate = new Promise((r) => { release = r; });
  const routes = {
    "/v2/api/status": () => ({ status: 200, body: { ...clone(STATUS), paused } }),
    "/v2/api/assets": { status: 200, body: clone(ASSETS) },
    "/v2/api/basic": { status: 200, body: clone(BASIC) },
    "/v2/api/pause": () => { paused = true; return { status: 200, body: { ok: true, paused: true } }; },
  };
  const f = makeFetch(routes);
  const slow = async (url, opts) => { if (url === "/v2/api/pause") await gate; return f(url, opts); };
  slow.calls = f.calls;
  const m = makeCtl({ fetchFn: slow });
  await m.ctl.refresh(true);
  const p = m.ctl.togglePause();
  await new Promise((r) => setImmediate(r));
  assert.equal(m.last().pauseBtn.disabled, true, "응답 전 비활성");
  release();
  await p;
  const post = f.calls.find((c) => c.method === "POST");
  assert.equal(post.url, "/v2/api/pause");
  assert.deepEqual(JSON.parse(post.body), { paused: true });
  assert.equal(m.last().pauseBtn.disabled, false);
  assert.equal(m.last().pauseBtn.label, "▶️ 매매 재개");   // 응답 뒤 status 를 다시 읽음
  assert.equal(m.last().pauseMsg, "");
  assert.ok(m.last().pausedBanner.startsWith("⏸️ 매매 일시중지 상태"));
});

test("busy 중에는 두 번째 누름이 요청을 만들지 않는다", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const f = makeFetch({ ...READ_OK(), "/v2/api/pause": { status: 200, body: { ok: true } } });
  const slow = async (url, opts) => { if (url === "/v2/api/pause") await gate; return f(url, opts); };
  slow.calls = f.calls;
  const m = makeCtl({ fetchFn: slow });
  await m.ctl.refresh(true);
  const p1 = m.ctl.togglePause();
  await new Promise((r) => setImmediate(r));
  await m.ctl.togglePause();
  release();
  await p1;
  assert.equal(f.calls.filter((c) => c.method === "POST").length, 1);
});

test("503 → 「잠시 뒤 다시 시도해 주세요」, 401·403 → 구버전 안내, 네트워크 오류도 재시도 안내", async () => {
  for (const [res, text] of [
    [{ status: 503, body: { error: "db_unavailable" } }, "잠시 뒤 다시 시도해 주세요"],
    [{ status: 401, body: {} }, "구버전에서 다시 들어와 주세요"],
    [{ status: 403, body: {} }, "구버전에서 다시 들어와 주세요"],
    [{ status: 500, body: {} }, "처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요"],
    [new Error("net"), "잠시 뒤 다시 시도해 주세요"],
  ]) {
    const m = makeCtl({ fetchFn: makeFetch({ ...READ_OK(), "/v2/api/pause": res }) });
    await m.ctl.refresh(true);
    await m.ctl.togglePause();
    assert.equal(m.last().pauseMsg, text, JSON.stringify(res.status));
    assert.equal(m.last().pauseBtn.disabled, false);
  }
});

test("401·403 이면 블록 자리에 「구버전에서 다시 들어와 주세요」", async () => {
  for (const code of [401, 403]) {
    const f = makeFetch({
      "/v2/api/status": { status: code, body: {} },
      "/v2/api/assets": { status: code, body: {} },
      "/v2/api/basic": { status: code, body: {} },
    });
    const m = makeCtl({ fetchFn: f });
    await m.ctl.refresh(true);
    assert.equal(m.last().auth, "구버전에서 다시 들어와 주세요");
    assert.equal(m.last().title, undefined);
  }
});

test("일부 읽기 실패는 안내만 하고 나머지는 그대로 보인다", async () => {
  const routes = READ_OK();
  routes["/v2/api/basic"] = { status: 500, body: {} };
  const m = makeCtl({ fetchFn: makeFetch(routes) });
  await m.ctl.refresh(true);
  assert.equal(m.last().error, "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다.");
  assert.match(m.last().title, /Dashboard \(LIVE\)/);
  assert.equal(m.last().assets, null);   // basic 이 없으면 💹 계산을 못 하므로 자산 칸은 비운다
});

test("탭이 숨겨지면(visible=false·문서 숨김) tick 이 요청을 만들지 않고, 다시 보이면 곧바로 읽는다", async () => {
  const m = makeCtl();
  m.state.visible = false;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 0);
  m.state.now += 60_000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 0);
  m.state.visible = true;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 3, "보임으로 바뀌면 status·assets·basic 3건");
  m.state.hidden = true;
  m.state.now += 60_000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 3, "문서 숨김이면 호출 정지");
  m.state.hidden = false;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 6);
});

test("tick: 7초 안에는 다시 읽지 않고 시계만 갱신한다", async () => {
  const m = makeCtl();
  await m.ctl.tick();
  const n = m.fetchFn.calls.length;
  m.state.now += 3000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, n);
  assert.notEqual(m.views[m.views.length - 1].clock, m.views[0].clock);
  m.state.now += 5000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, n + 3);
});

test("로그아웃: POST 뒤 「/」 이동, 실패해도 이동", async () => {
  const a = makeCtl({ fetchFn: makeFetch({ "/v2/api/logout": { status: 200, body: { ok: true } } }) });
  await a.ctl.logout();
  assert.deepEqual(a.nav, ["/"]);
  assert.equal(a.fetchFn.calls[0].method, "POST");
  assert.equal(a.fetchFn.calls[0].url, "/v2/api/logout");
  const b = makeCtl({ fetchFn: makeFetch({ "/v2/api/logout": new Error("net") }) });
  await b.ctl.logout();
  assert.deepEqual(b.nav, ["/"]);
});

test("자산 3칸: 구버전 문구와 계산", () => {
  const c = B.assetCells(STATUS, ASSETS, BASIC);
  assert.deepEqual(c.krw, { label: "보유 KRW", value: "1,234,567 KRW", delta: "" });
  assert.equal(c.coin.label, "KRW-JTO 보유량");
  assert.equal(c.coin.value, "10.500000");
  assert.equal(c.coin.delta, "평가 10,500 KRW");
  assert.equal(c.coin.caption, "");
  assert.deepEqual(c.pnl, { label: "💹 현재 포지션", value: "+1.23%", delta: "+1.23% (미실현)" });
  const locked = B.assetCells(STATUS, { ...ASSETS, krw_locked: 5000, coin_locked: 2.5 }, BASIC);
  assert.equal(locked.krw.delta, "🔒 Lock: 5,000 KRW");
  assert.equal(locked.coin.delta, "🔒 Lock: 2.500000 · 평가 10,500 KRW");
});

test("가용 0 + 묶임 > 0: 매도 불가 문구, 평가 0원", () => {
  const c = B.assetCells(STATUS, { ...ASSETS, coin: 0, coin_locked: 3.25 }, { ...BASIC, pnl_kind: "realized", pnl_pct: -0.34 });
  assert.equal(c.coin.caption,
    "⛔ 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 (3.250000개). 평가액은 가용 수량 기준이라 0원으로 보입니다.");
  assert.equal(c.coin.delta, "🔒 Lock: 3.250000 · 평가 0 KRW");
});

test("💹 칸: 미실현·실현·N/A·보합", () => {
  assert.deepEqual(B.pnlCell({ pnl_kind: "unrealized", pnl_pct: -2 }),
    { label: "💹 현재 포지션", value: "-2.00%", delta: "-2.00% (미실현)" });
  assert.deepEqual(B.pnlCell({ pnl_kind: "unrealized", pnl_pct: 0 }),
    { label: "💹 현재 포지션", value: "+0.00%", delta: "보합 (미실현)" });
  assert.deepEqual(B.pnlCell({ pnl_kind: "unrealized", pnl_pct: null }),
    { label: "💹 현재 포지션", value: "N/A", delta: "정보 없음" });
  assert.deepEqual(B.pnlCell({ pnl_kind: "realized", pnl_pct: -0.34 }),
    { label: "💹 최근 거래", value: "-0.34%", delta: "-0.34% (실현)" });
  assert.deepEqual(B.pnlCell({ pnl_kind: "realized", pnl_pct: 5 }),
    { label: "💹 최근 거래", value: "+5.00%", delta: "+5.00% (실현)" });
  assert.deepEqual(B.pnlCell({ pnl_kind: "realized", pnl_pct: null }),
    { label: "💹 최근 거래", value: "N/A", delta: "거래 없음" });
});

test("현재가 없음이면 평가 0원", () => {
  const c = B.assetCells(STATUS, { ...ASSETS, price: null }, BASIC);
  assert.equal(c.coin.delta, "평가 0 KRW");
});

test("로딩 중(status 없음)과 모드 확인 불가", async () => {
  const m = makeCtl();
  m.ctl.draw();
  assert.equal(m.last().loading, true);
  const routes = READ_OK();
  routes["/v2/api/status"] = { status: 200, body: { ...clone(STATUS), mode_engine: null } };
  const n = makeCtl({ fetchFn: makeFetch(routes) });
  await n.ctl.refresh(true);
  assert.match(n.last().title, /Dashboard \(확인 불가\)/);
  assert.equal(n.last().notice, null);
});

// ---- PC 배치 (결정 1026-08: PC 도 휴대폰과 같은 index.html, 차트 탭만 넓게) ----
test("PC 넘김 없음: index.html head 에 인라인 넘김 스크립트·backtester.html replace 가 없다", () => {
  const head = INDEX.slice(INDEX.indexOf("<head>"), INDEX.indexOf("</head>"));
  assert.doesNotMatch(head, /<script>/);
  assert.doesNotMatch(INDEX, /location\.replace/);
  assert.doesNotMatch(INDEX, /__v2toPC/);
  // 백테스터는 아래 탭 막대 링크로 들어간다
  assert.match(INDEX, /<a href="\/v2\/static\/backtester\.html">백테스터<\/a>/);
  // 차트 탭에서만 body 에 tab-chart 를 붙인다
  assert.match(INDEX, /<body x-data="dash\(\)" x-cloak :class="\{ 'tab-chart': tab === 'chart' \}">/);
});

// ---- 자리·연결 ----
test("index.html: 홈 탭 맨 위(상태 카드 앞)에 블록 자리, basic.css·basic.js 연결", () => {
  const home = INDEX.indexOf("tab === 'home'");
  const basic = INDEX.indexOf('id="basic"');
  const statusCard = INDEX.indexOf("<h2>상태</h2>");
  assert.ok(home > 0 && basic > home && basic < statusCard);
  assert.match(INDEX, /<link rel="stylesheet" href="\/v2\/static\/basic\.css">/);
  assert.match(INDEX, /<script defer src="\/v2\/static\/basic\.js"><\/script>/);
  assert.match(INDEX, /홈 화면 위에서 할 수 있습니다/);
  assert.match(INDEX, /매매 중지\/재개는 홈 화면 위 단추로 합니다\. 그 밖의 기능은 2차 공개 때 열립니다\./);
  assert.doesNotMatch(INDEX, /이 화면은 읽기 전용입니다/);
});

test("backtester.html: h1 앞 블록 자리, </style> 뒤 basic.css, 끝에 basic.js, 블록 안 입력 없음", () => {
  const style = BT.indexOf("</style>");
  const css = BT.indexOf('href="/v2/static/basic.css"');
  const div = BT.indexOf('<div id="basic"');
  const h1 = BT.indexOf("<h1>");
  assert.ok(style > 0 && css > style && div > css && div < h1);
  assert.match(BT, /<div id="basic" class="section" data-page="backtester"><\/div>/);
  const lastScript = [...BT.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
  assert.equal(lastScript[lastScript.length - 1], "/v2/static/basic.js");
  const block = BT.slice(div, h1);
  assert.doesNotMatch(block, /<(input|select|textarea)\b/);
});

test("basic.js·basic.css: 업비트·외부 주소 없음, innerHTML 미사용", () => {
  for (const f of ["basic.js", "basic.css"]) {
    const t = fs.readFileSync(path.join(STATIC, f), "utf8");
    assert.doesNotMatch(t, /https?:\/\//, f);
    assert.doesNotMatch(t, /api\.upbit\.com|pyupbit/i, f);
  }
  const js = fs.readFileSync(path.join(STATIC, "basic.js"), "utf8");
  assert.doesNotMatch(js, /innerHTML|insertAdjacentHTML|document\.write/);
});

test("읽기 진행 중 강제 읽기(중지/재개 응답 뒤)는 버리지 않고, 끝난 뒤 한 번 더 읽는다", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  let first = true;
  const routes = READ_OK();
  const statusOk = routes["/v2/api/status"];
  const fetchFn = makeFetch(Object.assign(routes, {
    "/v2/api/status": () => statusOk,
  }));
  const slowFetch = async (url, opts) => {
    if (url === "/v2/api/status" && first) { first = false; await gate; }
    return fetchFn(url, opts);
  };
  slowFetch.calls = fetchFn.calls;
  const { ctl } = makeCtl({ fetchFn: slowFetch });
  const p1 = ctl.refresh(false);      // 진행 중
  const p2 = ctl.refresh(true);       // 강제 — 버리지 않음
  release();
  await p1; await p2;
  await new Promise((r) => setTimeout(r, 0));
  const statusGets = fetchFn.calls.filter((c) => c.url === "/v2/api/status").length;
  assert.equal(statusGets, 2);
});

test("PC 넘김 가드가 없다 — PC 에서도 홈(app.js)·블록(basic.js)이 읽기를 시작한다", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  assert.doesNotMatch(html, /window\.stop/);
  const app = fs.readFileSync(path.join(STATIC, "app.js"), "utf8");
  assert.doesNotMatch(app, /__v2toPC/);
  const js = fs.readFileSync(path.join(STATIC, "basic.js"), "utf8");
  assert.doesNotMatch(js, /__v2toPC/);
  assert.match(js, /function init\(\) \{\s*var root = document\.getElementById\("basic"\);/);
});
