// 1111-01 선물 동등성 시험(N1·N2·N3·N6): 투자자 Ver9 원문 스크립트 vs 이식본(backtester.js)을 같은 가짜 바이낸스 서버로 돌린다.
// 한계: 두 쪽이 같은 선물 코드를 쓰므로 「정해진 차이 10곳이 선물로 새지 않았다」만 확인한다. 선물 규칙 자체가 옳은지는 확인하지 않는다(투자자 원문 그대로).
// 바깥 연결 0: vm 에 실제 fetch 가 없고 가짜 fetch 만 있다(fut_harness.mjs). 새 고정 자료 fixtures/fut_*.json 은 합성 자료다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { ROOT, ver2Html, ver2Script } from "./ver2_source.mjs";
import { makeRun, NARROW_SWEEP } from "./fut_harness.mjs";

const PORT_JS = fs.readFileSync(path.join(ROOT, "v2/static/backtester.js"), "utf8");
const PORT_HTML = fs.readFileSync(path.join(ROOT, "v2/static/backtester.html"), "utf8");
const ORIG_JS = ver2Script();
const ORIG_HTML = ver2Html();

const pair = (overrides = {}) => [makeRun(ORIG_JS, ORIG_HTML, overrides), makeRun(PORT_JS, PORT_HTML, overrides)];

function dropColumn(csvText, col) {
  const lines = csvText.split("\n");
  const k = lines[0].split(",").indexOf(col);
  if (k < 0) return csvText;
  return lines.map((l) => { const c = l.split(","); c.splice(k, 1); return c.join(","); }).join("\n");
}

test("N1 선물 동등성: 방식 A·B·C × 방식 C 손절 2 × 펀딩비 2 = 12가지 거래·주간·월간·요약이 원문과 같다", async () => {
  const [o, p] = pair();
  let nonEmpty = 0;
  for (const futMode of ["A", "B", "C"]) {
    for (const cUseSl of ["no", "yes"]) {
      for (const useFunding of ["yes", "no"]) {
        for (const r of [o, p]) { r.set("futMode", futMode); r.set("cUseSl", cUseSl); r.set("useFunding", useFunding); await r.runFut(); }
        const so = o.snapshot(), sp = p.snapshot();
        const tag = `${futMode}/${cUseSl}/${useFunding}`;
        assert.equal(so.mode, "futures", tag);
        assert.equal(sp.trades, so.trades, "거래 " + tag);
        assert.equal(sp.weekly, so.weekly, "주간 " + tag);
        assert.equal(sp.monthly, so.monthly, "월간 " + tag);
        assert.equal(sp.summary, so.summary, "요약 " + tag);
        assert.ok(!sp.status.includes("오류"), sp.status);
        assert.ok(!sp.chartHint.includes("차트 렌더링 오류"), sp.chartHint);
        if (so.trades.length > 0) nonEmpty++;
      }
    }
  }
  assert.ok(nonEmpty >= 6, `거래가 있는 경우가 너무 적음(${nonEmpty}) — 비교 무의미`);
});

test("N1 펀딩비 반영 여부가 거래 손익 칸에 실제로 영향을 준다(시험 자료 점검)", async () => {
  const [, p] = pair();
  p.set("useFunding", "yes"); await p.runFut(); const withF = p.snapshot().trades;
  p.set("useFunding", "no"); await p.runFut(); const noF = p.snapshot().trades;
  assert.notEqual(withF, noF);
});

test("N2 선물 스윕 동등성: 스윕·기울기별·둔화별·월별 1위·주별 1위 5개 CSV 가 원문과 같다", async () => {
  const [o, p] = pair(NARROW_SWEEP);
  for (const r of [o, p]) await r.runFut();
  const so = await o.sweep(), sp = await p.sweep();
  for (const k of Object.keys(so)) {
    assert.ok(so[k].length > 0, `${k} CSV 가 비어 있음 — 비교 무의미`);
    assert.equal(sp[k], so[k], k);
  }
  assert.equal(vm.runInContext("sweepRows.length", p.ctx), 36);
});

test("N3 현물 스윕 5개 CSV 동등성(좁힌 범위): 원문과 같다(거래 CSV 는 구간 순번 칸 제외)", async () => {
  const [o, p] = pair(NARROW_SWEEP);
  for (const r of [o, p]) await r.runSpot();
  assert.equal(dropColumn(p.snapshot().trades, "episodeBreakoutIndex"), dropColumn(o.snapshot().trades, "episodeBreakoutIndex"));
  const so = await o.sweep(), sp = await p.sweep();
  for (const k of Object.keys(so)) {
    assert.ok(so[k].length > 0, `${k} CSV 가 비어 있음 — 비교 무의미`);
    assert.equal(sp[k], so[k], k);
  }
});

test("N6 바깥 연결 0: vm 에 실제 fetch 가 없고, 선물은 가짜 서버(fapi 주소)만 불렀다", async () => {
  const [, p] = pair();
  assert.equal(vm.runInContext('typeof process + "|" + typeof require + "|" + typeof XMLHttpRequest', p.ctx), "undefined|undefined|undefined");
  await p.runFut();
  assert.ok(p.urls.length >= 2, "선물 봉 + 펀딩비 요청이 있어야 함");
  for (const u of p.urls) assert.ok(u.startsWith("https://fapi.binance.com/fapi/v1/"), u);
  assert.ok(p.urls.some((u) => u.includes("/klines?")));
  assert.ok(p.urls.some((u) => u.includes("/fundingRate?")));
});
