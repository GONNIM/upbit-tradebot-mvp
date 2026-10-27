// basic.js(매매 중지/재개·로그아웃 제어) 순수 로직·컨트롤러 시험 + index.html 자리·연결 시험. 브라우저 없이 vm 으로 돌린다.
// 결정 1026-23: 옛 기본 블록(제목·안내·상태 로그·엔진 상태·자산 3칸)은 삭제 — 홈 배지/자산 카드(app.js)가 대신한다.
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

const STATUS = {
  engine: { level: "ok", ago_sec: 30 }, mode_engine: "LIVE", mode_entry: "LIVE", mode_mismatch: false,
  strategy: { value: "EMA", mtime: null }, ticker: "KRW-JTO", interval: "minute3", paused: false,
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
// 7초 읽기는 status 하나뿐(assets·basic 은 app.js 가 읽는다)
const READ_OK = () => ({
  "/v2/api/status": { status: 200, body: clone(STATUS) },
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

test("옛 기본 블록 표시는 남지 않았다(안내 문장·현재 시각·상태 로그·자산 3칸)", async () => {
  const { ctl, last } = makeCtl();
  await ctl.refresh(true);
  const v = last();
  assert.doesNotMatch(JSON.stringify(v), /Upbit Trade Bot v1/);
  for (const k of ["clock", "info", "title", "notice", "log", "engine", "assets", "mismatch"]) {
    assert.equal(k in v, false, k);
  }
  const js = fs.readFileSync(path.join(STATIC, "basic.js"), "utf8");
  assert.doesNotMatch(js, /Upbit Trade Bot v1|kstClock|modeNotice|assetCells|pnlCell/);
});

test("중지 배너 문구는 「위 '▶️ 매매 재개' 단추」, 단추 문구 전환(중지 ↔ 재개)", async () => {
  const routes = READ_OK();
  routes["/v2/api/status"] = { status: 200, body: { ...clone(STATUS), paused: true } };
  const { ctl, last } = makeCtl({ fetchFn: makeFetch(routes) });
  await ctl.refresh(true);
  assert.equal(last().pausedBanner,
    "⏸️ 매매 일시중지 상태 — 엔진과 지표는 정상 작동하지만 실주문(BUY/SELL)은 실행되지 않습니다. " +
    "재개하려면 위 '▶️ 매매 재개' 단추를 클릭하세요.");
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

test("401·403 이면 #pause-row 자리에 「구버전에서 다시 들어와 주세요」", async () => {
  for (const code of [401, 403]) {
    const f = makeFetch({ "/v2/api/status": { status: code, body: {} } });
    const m = makeCtl({ fetchFn: f });
    await m.ctl.refresh(true);
    assert.equal(m.last().auth, "구버전에서 다시 들어와 주세요");
    assert.equal(m.last().pauseBtn, undefined);
  }
});

test("status 읽기 실패 → 단추 비활성·안내 문구", async () => {
  const m = makeCtl({ fetchFn: makeFetch({ "/v2/api/status": { status: 500, body: {} } }) });
  await m.ctl.refresh(true);
  assert.equal(m.last().error, "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다.");
  assert.equal(m.last().pauseBtn.disabled, true);
  // 누르더라도 요청이 없다
  await m.ctl.togglePause();
  assert.equal(m.fetchFn.calls.filter((c) => c.method === "POST").length, 0);
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
  assert.equal(m.fetchFn.calls.length, 1, "보임으로 바뀌면 status 1건");
  m.state.hidden = true;
  m.state.now += 60_000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 1, "문서 숨김이면 호출 정지");
  m.state.hidden = false;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, 2);
});

test("tick: 7초 안에는 다시 읽지 않는다", async () => {
  const m = makeCtl();
  await m.ctl.tick();
  const n = m.fetchFn.calls.length;
  m.state.now += 3000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, n);
  m.state.now += 5000;
  await m.ctl.tick();
  assert.equal(m.fetchFn.calls.length, n + 1);
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

test("로딩 중(status 없음)은 단추 비활성", async () => {
  const m = makeCtl();
  m.ctl.draw();
  assert.equal(m.last().loading, true);
  assert.equal(m.last().pauseBtn.disabled, true);
});

// ---- 배치 (결정 1026-19 3 가: PC 도 휴대폰과 같은 index.html) ----
test("PC 넘김 없음: index.html head 에 인라인 넘김 스크립트·backtester.html replace 가 없다", () => {
  const head = INDEX.slice(INDEX.indexOf("<head>"), INDEX.indexOf("</head>"));
  assert.doesNotMatch(head, /<script>/);
  assert.doesNotMatch(INDEX, /location\.replace/);
  assert.doesNotMatch(INDEX, /__v2toPC/);
  // 백테스터는 아래 메뉴 링크로 들어간다
  assert.match(INDEX, /<a [^>]*href="\/v2\/static\/backtester\.html"[^>]*>백테스터<\/a>/);
  // 차트 탭만 넓히는 body 바인딩은 없다
  assert.doesNotMatch(INDEX, /tab-chart/);
});

// ---- 자리·연결 ----
test("index.html: 홈 탭 배지 줄 아래 #pause-row, 머리 막대 #logout-btn, basic.css·basic.js 연결", () => {
  const home = INDEX.indexOf("tab === 'home'");
  const badge = INDEX.indexOf('id="home-badges"');
  const pause = INDEX.indexOf('id="pause-row"');
  const statusCard = INDEX.indexOf("<h2>자산</h2>");
  assert.ok(home > 0 && badge > home && pause > badge && pause < statusCard, "배지 줄 아래, 첫 카드 앞");
  assert.equal(INDEX.match(/id="pause-row"/g).length, 1);
  assert.equal(INDEX.match(/id="logout-btn"/g).length, 1);
  assert.doesNotMatch(INDEX, /id="basic"/);
  const bar = INDEX.slice(INDEX.indexOf('<header class="bar"'), INDEX.indexOf("</header>"));
  assert.match(bar, /id="logout-btn"/);
  assert.match(INDEX, /<link rel="stylesheet" href="\/v2\/static\/basic\.css">/);
  assert.match(INDEX, /<script defer src="\/v2\/static\/basic\.js"><\/script>/);
  assert.match(INDEX, /운용 단추는 2차 공개 때 열립니다\. 매매 중지\/재개는 홈 화면 위 단추로 합니다\./);
  assert.doesNotMatch(INDEX, /이 화면은 읽기 전용입니다/);
  // 접힘(<details>) 밖 — 자주 쓰는 단추는 top-level (project-rules 1-B)
  const before = INDEX.slice(home, pause);
  assert.doesNotMatch(before, /<details/);
});

test("backtester.html: 옛 기본 블록 자리·basic.js·basic.css 없음", () => {
  assert.doesNotMatch(BT, /id="basic"/);
  assert.doesNotMatch(BT, /basic\.js/);
  assert.doesNotMatch(BT, /basic\.css/);
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

test("PC 넘김 가드가 없다 — PC 에서도 홈(app.js)·단추(basic.js)가 읽기를 시작한다", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  assert.doesNotMatch(html, /window\.stop/);
  const app = fs.readFileSync(path.join(STATIC, "app.js"), "utf8");
  assert.doesNotMatch(app, /__v2toPC/);
  const js = fs.readFileSync(path.join(STATIC, "basic.js"), "utf8");
  assert.doesNotMatch(js, /__v2toPC/);
  assert.match(js, /function init\(\) \{\s*var root = document\.getElementById\("pause-row"\);/);
});
