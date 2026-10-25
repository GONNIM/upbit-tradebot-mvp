// save.js 순수 함수 시험: 값 모으기·응답 문구. 브라우저 없이 globalThis.__v2save 로 접근한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { parseDefaults } from "./harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
const SAVE_JS = path.join(ROOT, "v2/static/save.js");
const HTML = fs.readFileSync(path.join(ROOT, "v2/static/backtester.html"), "utf8");

function load() {
  const ctx = { globalThis: null, document: undefined, window: undefined, console };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(SAVE_JS, "utf8"), ctx);
  return ctx.__v2save;
}

const IDS = ["symbol", "maType", "src", "days", "ma60p", "ma200p", "pullbackP", "slopeLB",
  "minSlope", "slopeDrop", "buyOnGoldenCross", "maxSplits", "maxPullbackBuys", "tp", "sl",
  "capital", "fee", "deadcross", "compounding"];

test("collectParams: 19 keys, number->Number, empty number->null, select string", () => {
  const S = load();
  const d = parseDefaults(HTML);
  const els = {};
  for (const id of IDS) els[id] = { value: d[id].value };
  els.days.value = "";
  els.tp.value = "1.5";
  const out = S.collectParams((id) => els[id]);
  assert.deepEqual([...Object.keys(out)], IDS);
  assert.equal(out.days, null);
  assert.equal(out.tp, 1.5);
  assert.equal(out.ma60p, 60);
  assert.equal(out.maType, "ema");
  assert.equal(out.symbol, "JTOUSDT");
  assert.equal(typeof out.buyOnGoldenCross, "string");
  assert.equal(out.compounding, "no");
  assert.deepEqual([...S.NUMBER_IDS, ...S.TEXT_IDS].sort(), IDS.slice().sort());
});

test("saveMessage: 응답별 문구", () => {
  const S = load();
  assert.match(S.saveMessage(200, { ok: true, saved_at: "2026-10-24T10:00:00+09:00", history_id: 7 }), /저장했습니다.*7/);
  assert.match(S.saveMessage(200, { ok: true, saved_at: null, history_id: 7 }), /저장했습니다/);
  assert.match(S.saveMessage(400, { error: "invalid_param", field: "tp" }), /입력값 확인: tp/);
  assert.match(S.saveMessage(401, {}), /신버전 대시보드/);
  assert.match(S.saveMessage(403, {}), /권한 없음/);
  assert.match(S.saveMessage(409, { error: "engine_ticker_unknown" }), /엔진 종목을 알 수 없어 저장하지 않았습니다/);
  assert.match(S.saveMessage(404, { error: "no_data" }), /상태를 읽지 못했습니다/);
  assert.match(S.saveMessage(500, { error: "file_changed" }), /관리자 확인 필요/);
  for (const e of ["file_write_failed", "history_failed", "pullback_file_missing"]) {
    assert.match(S.saveMessage(500, { error: e }), /파일은 바뀌지 않았거나 되돌렸습니다/);
  }
});

test("engineLabel: 정상/지연/판단 불가, 「정지」 없음", () => {
  const S = load();
  assert.match(S.engineLabel({ level: "ok", ago_sec: 120 }), /^정상/);
  assert.match(S.engineLabel({ level: "delay", ago_sec: 600 }), /^지연/);
  assert.match(S.engineLabel({ level: "unknown" }), /^판단 불가/);
  assert.match(S.engineLabel(null), /판단 불가/);
  for (const e of [{ level: "ok" }, { level: "delay" }, { level: "x" }, null]) {
    assert.doesNotMatch(S.engineLabel(e), /정지/);
  }
});

test("saveButtonDisabled: 미리 읽기 전·종목 없음·저장 중·저장 성공 뒤 모두 비활성", () => {
  const S = load();
  const ok = { preloaded: true, hasTicker: true, saving: false, saved: false };
  assert.equal(S.saveButtonDisabled(ok), false);
  for (const k of ["preloaded", "hasTicker"]) assert.equal(S.saveButtonDisabled({ ...ok, [k]: false }), true, k);
  for (const k of ["saving", "saved"]) assert.equal(S.saveButtonDisabled({ ...ok, [k]: true }), true, k);
});

test("lastSavedText: 응답 saved_at 우선, 없으면 current, 둘 다 없으면 기록 없음", () => {
  const S = load();
  const cur = { exists: true, broken: false, mtime: "2026-10-24T09:00:00+09:00" };
  assert.equal(S.lastSavedText("2026-10-24T10:00:00+09:00", cur), "2026-10-24 10:00:00");
  assert.equal(S.lastSavedText(null, cur), "2026-10-24 09:00:00");
  assert.equal(S.lastSavedText(null, { exists: true, broken: true, mtime: "x" }), "저장 기록 없음");
  assert.equal(S.lastSavedText(null, { exists: false }), "저장 기록 없음");
  assert.equal(S.lastSavedText(null, null), "저장 기록 없음");
});

test("makeGate: 최신 세대만 유효", () => {
  const S = load();
  const g = S.makeGate();
  const a = g.next();
  const b = g.next();
  assert.equal(g.isCurrent(a), false);
  assert.equal(g.isCurrent(b), true);
  g.next();   // 닫기도 세대를 올린다
  assert.equal(g.isCurrent(b), false);
});

test("srcToInterval: 4종 매핑·매핑 밖은 null, 문구·경고", () => {
  const S = load();
  assert.equal(S.srcToInterval("1m"), "minute1");
  assert.equal(S.srcToInterval("3m"), "minute3");
  assert.equal(S.srcToInterval("5m"), "minute5");
  assert.equal(S.srcToInterval("1h"), "minute60");
  for (const bad of ["15m", "", "toString", "__proto__", undefined, null]) assert.equal(S.srcToInterval(bad), null, String(bad));
  assert.equal(S.srcText("1h"), "60분 (minute60)");
  assert.equal(S.srcText("zz"), "알 수 없음");
  assert.equal(S.intervalWarning("1h", "minute3"),
    "백테스트 봉(60분)이 엔진 현재 봉(minute3)과 다릅니다 — 저장만 하며 엔진은 바뀌지 않습니다");
  assert.equal(S.intervalWarning("3m", "minute3"), null);
  assert.equal(S.intervalWarning("zz", "minute3"), null);
  assert.equal(S.intervalWarning("1h", null), null);
});

test("save.js 매핑이 params_schema._INTERVAL 과 같다", () => {
  const S = load();
  const py = fs.readFileSync(path.join(ROOT, "v2/params_schema.py"), "utf8");
  const block = py.match(/_INTERVAL\s*=\s*\{([^}]*)\}/)[1];
  const pyMap = {};
  for (const m of block.matchAll(/"([^"]+)":\s*"([^"]+)"/g)) pyMap[m[1]] = m[2];
  assert.deepEqual({ ...S.SRC_INTERVAL }, pyMap);
  assert.equal(Object.keys(pyMap).length, 4);
});

test("스냅샷: 원본 입력이 바뀌어도 보낼 본문은 스냅샷 그대로", () => {
  const S = load();
  const d = parseDefaults(HTML);
  const els = {};
  for (const id of IDS) els[id] = { value: d[id].value };
  const snap = S.makeSnapshot((id) => els[id]);
  const body1 = S.snapshotBody(snap);
  els.src.value = "1h";
  els.tp.value = "9";
  assert.equal(S.snapshotBody(snap), body1);
  const parsed = JSON.parse(body1);
  assert.equal(parsed.params.src, "3m");
  assert.equal(parsed.params.tp, 1);
  assert.equal(parsed.source, "binance");
  assert.deepEqual(Object.keys(parsed.params), IDS);
  // 다시 열면 새로 모은다
  assert.equal(S.makeSnapshot((id) => els[id]).params.src, "1h");
});

test("성공 문구에 응답의 ticker·interval 이 들어간다", () => {
  const S = load();
  const m = S.saveMessage(200, { ok: true, saved_at: "2026-10-24T10:00:00+09:00",
    history_id: 7, ticker: "KRW-ZRO", interval: "minute60" });
  assert.match(m, /이력 번호 7/);
  assert.match(m, /KRW-ZRO/);
  assert.match(m, /60분 \(minute60\)/);
  assert.equal(S.intervalText("minute3"), "3분 (minute3)");
  assert.equal(S.intervalText("weird"), "weird");
});

test("backtester.html: saveArea 안에 버튼·확인 창, save.js 가 backtester.js 뒤", () => {
  assert.match(HTML, /<div id="saveArea"[^>]*>[\s\S]*<button[^>]*id="saveOpenBtn"/);
  assert.match(HTML, /id="saveDialog"[^>]*hidden/);
  const iJs = HTML.indexOf('<script src="backtester.js"></script>');
  const iSave = HTML.indexOf('<script src="save.js"></script>');
  const iArea = HTML.indexOf('id="saveArea"');
  assert.ok(iJs >= 0 && iSave > iJs && iSave > iArea);
  const saveArea = HTML.slice(iArea, HTML.indexOf("</body>"));
  assert.doesNotMatch(saveArea, /<input|<select/);
  assert.doesNotMatch(saveArea, /이 설정으로 동작/);
});
