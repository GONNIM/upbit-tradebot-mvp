// 백테스터 이식 동등성 시험: 원본 HTML+스크립트 vs v2/static/backtester.{html,js}.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runInHarness, parseDefaults } from "./harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
const ORIG = path.join(ROOT, "docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html");
const PORT_HTML = path.join(ROOT, "v2/static/backtester.html");
const PORT_JS = path.join(ROOT, "v2/static/backtester.js");

const origHtml = fs.readFileSync(ORIG, "utf8");
// 인라인 스크립트 본문: 143행 ~ 938행 (1-기반, 양끝 포함), 줄 끝 \n 포함.
const origScript = origHtml.split("\n").slice(142, 938).join("\n") + "\n";
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex");

test("script body byte-identical to original", () => {
  const port = fs.readFileSync(PORT_JS);
  assert.equal(sha(port), sha(Buffer.from(origScript, "utf8")));
});

test("defaults identical", () => {
  const o = parseDefaults(origHtml);
  const p = parseDefaults(fs.readFileSync(PORT_HTML, "utf8"));
  const ids = Object.keys(o);
  assert.equal(ids.filter((i) => o[i].tag === "input").length, 24);
  assert.equal(ids.filter((i) => o[i].tag === "select").length, 6);
  assert.equal(ids.length, 30);
  for (const id of ids) assert.deepStrictEqual(p[id], o[id], id);
  assert.equal(p.dataSource.tag, "select");
  assert.deepStrictEqual(p.dataSource.options.length, 2);
  assert.equal(Object.keys(p).filter((i) => i !== "dataSource").length, 30);
  const portHtml = fs.readFileSync(PORT_HTML, "utf8");
  // R7 폐기(결정 1026-23 2 가): 업비트 출처는 서버 경로. select 는 숨겨 값만 맞춘다.
  assert.match(portHtml, /<select id="dataSource" hidden>/);
  assert.deepStrictEqual(p.dataSource.options, ["binance", "upbit"]);
});

for (const set of ["a", "b", "c"]) {
  const fixture = JSON.parse(fs.readFileSync(path.join(here, `fixtures/klines_${set}.json`), "utf8"));
  const urls = fixture.pages.map((p) => p.url);
  const pageBars = fixture.pages.reduce((s, p) => s + p.data.length, 0);
  let both;
  const get = async () => {
    if (!both) {
      both = Promise.all([
        runInHarness(origScript, origHtml, fixture),
        runInHarness(fs.readFileSync(PORT_JS, "utf8"), fs.readFileSync(PORT_HTML, "utf8"), fixture),
      ]);
    }
    return both;
  };

  test(`set ${set}: trades/weekly/monthly/sweep CSV identical`, async () => {
    const [o, p] = await get();
    for (const k of ["trades", "weekly", "monthly", "sweep"]) {
      assert.ok(o[k].length > 0, `${k} CSV 가 비어 있음 — 비교 무의미`);
      assert.equal(p[k], o[k], k);
    }
  });

  test(`set ${set}: request count and bar count identical`, async () => {
    const [o, p] = await get();
    assert.deepStrictEqual(o.fetchCalls, urls);
    assert.deepStrictEqual(p.fetchCalls, urls);
    assert.equal(p.barCount, o.barCount);
    assert.equal(o.barCount, pageBars);
  });

  test(`set ${set}: chart path no error`, async () => {
    const [o, p] = await get();
    for (const r of [o, p]) {
      assert.ok(!r.chartHint.includes("차트 렌더링 오류"), r.chartHint);
      assert.ok(!r.status.includes("오류"), r.status);
    }
  });
}
