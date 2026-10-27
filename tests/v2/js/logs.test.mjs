// 로그 탭(그림 2-라) 시험: 시각 열 문구(logTime) + Alpine 연결(종류 토글·쪽 이동) + index.html 문구.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");

globalThis.window = globalThis;
globalThis.document = { hidden: false, addEventListener() {}, getElementById() { return {}; } };
globalThis.location = { hash: "" };
globalThis.history = { replaceState(_s, _t, url) { globalThis.location.hash = url; } };
globalThis.addEventListener = () => {};
let dashFactory = null;
const listeners = [];
globalThis.document.addEventListener = (n, fn) => { if (n === "alpine:init") listeners.push(fn); };
globalThis.Alpine = { data(name, f) { if (name === "dash") dashFactory = f; } };
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "app.js"), "utf8"));
for (const fn of listeners) fn();

// 기준 시각: 2026-10-27 10:00 KST
const NOW = Date.parse("2026-10-27T10:00:00+09:00");

test("logTime: 오늘 HH:MM, 어제 「어제」, 그 전 MM-DD, 값 없음 —", () => {
  const f = globalThis.logTime;
  assert.equal(typeof f, "function");
  assert.equal(f("2026-10-27T09:31:42+09:00", NOW), "09:31");
  assert.equal(f("2026-10-26T23:59:00+09:00", NOW), "어제");
  assert.equal(f("2026-10-25T10:00:00+09:00", NOW), "10-25");
  assert.equal(f(null, NOW), "—");
  assert.equal(f("엉터리", NOW), "—");
  // KST 자정 경계: UTC 로는 어제 15:30 이어도 KST 로는 오늘 00:30
  assert.equal(f("2026-10-26T15:30:00Z", NOW), "00:30");
});

function makeDash(handler) {
  const d = dashFactory();
  const calls = [];
  d.getJson = async (p) => { calls.push(p); return handler(p); };
  return { d, calls };
}

test("loadLogs: kind·page 를 주소에 싣고 rows·pages 를 반영, 기본은 감사 로그", async () => {
  const { d, calls } = makeDash(() => ({
    kind: "audit", page: 1, pages: 3,
    rows: [{ id: "t1", timestamp: "2026-10-27T09:31:00+09:00", text: "매수 체결 · 골든크로스", cls: "buy" }],
  }));
  assert.equal(d.logsKind, "audit");
  await d.loadLogs(1);
  assert.deepEqual(calls, ["/v2/api/logs?kind=audit&page=1"]);
  assert.equal(d.logsPages, 3);
  assert.equal(d.logsPage, 1);
  assert.equal(d.logRows.length, 1);
  assert.equal(d.logRows[0].text, "매수 체결 · 골든크로스");
  assert.equal(d.logRows[0].cls, "buy");
  assert.match(d.logRows[0].time, /^(\d\d:\d\d|어제|\d\d-\d\d)$/);
  assert.equal(d.logsLoaded, true);
});

test("setLogsKind: 종류를 바꾸면 1쪽부터 다시 읽는다", async () => {
  const { d, calls } = makeDash((p) => ({ kind: "engine", page: 1, pages: 1, rows: [] }));
  d.logsPage = 4;
  await d.setLogsKind("engine");
  assert.equal(d.logsKind, "engine");
  assert.deepEqual(calls, ["/v2/api/logs?kind=engine&page=1"]);
  await d.setLogsKind("error");
  assert.equal(calls[1], "/v2/api/logs?kind=error&page=1");
  // 모르는 종류는 무시
  await d.setLogsKind("x");
  assert.equal(d.logsKind, "error");
  assert.equal(calls.length, 2);
});

test("쪽 이동: 첫 쪽·마지막 쪽 밖으로는 나가지 않고, 서버가 맞춘 쪽 번호를 따른다", async () => {
  const { d, calls } = makeDash((p) => ({ kind: "audit", page: 2, pages: 2, rows: [] }));
  d.logsPage = 1; d.logsPages = 2;
  await d.loadLogs(0);
  await d.loadLogs(3);
  assert.equal(calls.length, 0, "범위 밖은 요청하지 않음");
  await d.loadLogs(2);
  assert.equal(d.logsPage, 2);
  assert.equal(d.logsRange, "2 / 2");
  assert.equal(d.logsEmpty, true);
});

test("more 가 true 면 쪽 표기는 「p / 100+」", async () => {
  const { d } = makeDash(() => ({ kind: "engine", page: 1, pages: 100, more: true, rows: [] }));
  await d.loadLogs(1);
  assert.equal(d.logsRange, "1 / 100+");
  const e = makeDash(() => ({ kind: "engine", page: 1, pages: 100, more: false, rows: [] }));
  await e.d.loadLogs(1);
  assert.equal(e.d.logsRange, "1 / 100");
});

test("종류를 바꾸면 이전 행을 비우고 불러오는 중으로 둔다", async () => {
  let release;
  const d = dashFactory();
  d.logRows = [{ id: 1, time: "09:00", text: "예전 행", cls: "" }];
  d.logsLoaded = true;
  d.getJson = () => new Promise((res) => { release = res; });
  const p = d.setLogsKind("engine");
  assert.deepEqual(d.logRows, [], "응답 전에 이미 비어 있음");
  assert.equal(d.logsLoaded, false);
  assert.equal(d.logsEmpty, false, "불러오는 중에는 「기록이 없습니다」를 보이지 않음");
  release({ kind: "engine", page: 1, pages: 1, rows: [] });
  await p;
  assert.equal(d.logsEmpty, true);
});

test("느리게 도착한 이전 종류의 응답은 버린다", async () => {
  const pending = [];
  const d = dashFactory();
  d.getJson = (p) => new Promise((res) => pending.push({ p, res }));
  const a = d.setLogsKind("engine");
  const b = d.setLogsKind("error");
  pending[1].res({ kind: "error", page: 1, pages: 1, rows: [{ id: 2, timestamp: null, text: "[ERROR] e", cls: "err" }] });
  await b;
  pending[0].res({ kind: "engine", page: 1, pages: 9, rows: [{ id: 1, timestamp: null, text: "[INFO] i", cls: "" }] });
  await a;
  assert.equal(d.logsKind, "error");
  assert.equal(d.logsPages, 1);
  assert.equal(d.logRows[0].text, "[ERROR] e");
});

test("index.html: 그림 2-라 문구·토글·표 머리·쪽 이동·설명 카드", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  for (const s of ["감사 로그", "엔진", "오류", "시각", "내용", "이전", "다음",
    "이 화면에서 보는 것",
    "봇이 왜 샀는지, 왜 안 샀는지, 언제 전환했는지. 기존 감사 로그와 같은 기록을 요약해 보여 드립니다.",
    "기록이 없습니다"]) {
    assert.ok(html.includes(s), s);
  }
  assert.ok(html.includes("setLogsKind('audit')"));
  assert.ok(html.includes("setLogsKind('engine')"));
  assert.ok(html.includes("setLogsKind('error')"));
  assert.ok(!html.includes("'페이지 '"), "옛 「페이지 N」 머리 제거");
});
