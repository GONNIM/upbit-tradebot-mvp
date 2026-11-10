// 백테스터 이식 동등성 시험 (1105-09 · Ver2): 투자자 최종판 Ver2 HTML+스크립트 vs v2/static/backtester.{html,js}.
// backtester.js = Ver2 인라인 스크립트 + 정해진 차이 2곳(fixtures/ver2_patches.json, 1105-06 Q3 ② · 결정 ③).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runInHarness, parseDefaults } from "./harness.mjs";
import { ROOT, PATCHES, ver2Html, ver2Script, patchedScript, countOf } from "./ver2_source.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT_HTML = path.join(ROOT, "v2/static/backtester.html");
const PORT_JS = path.join(ROOT, "v2/static/backtester.js");
const VER2_SHA = "dbe285f8b846540f0071c3ed70c46b9ae864488c36d9046be11f3c5e26134ae8";

const origHtml = ver2Html();
const origScript = ver2Script();
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex");

test("Ver2 기준 파일이 바뀌지 않았다", () => {
  assert.equal(sha(Buffer.from(origHtml, "utf8")), VER2_SHA);
  assert.ok(origScript.startsWith("let tradeRows=[]"), "스크립트 시작 줄");
  assert.ok(origScript.trimEnd().endsWith("attachSteppers();"), "스크립트 끝 줄");
});

test("script = Ver2 원문 + 정해진 차이(1105-06 두 곳 · 1110-01 추적 손절) (바이트 동일)", () => {
  assert.equal(PATCHES.patches.filter((p) => !p.why.includes("1110-01")).length, 2);
  assert.equal(PATCHES.patches.filter((p) => p.why.includes("1110-01")).length, 8);
  for (const p of PATCHES.patches) {
    assert.equal(countOf(origScript, p.find), 1, p.why);
    assert.ok(/기준 파일과 다름 — 1105-06|기준 파일과 다름 — 1110-01/.test(p.replace), "차이 자리 주석");
  }
  const port = fs.readFileSync(PORT_JS);
  assert.equal(sha(port), sha(Buffer.from(patchedScript(), "utf8")));
});

test("defaults identical to Ver2", () => {
  const o = parseDefaults(origHtml);
  const p = parseDefaults(fs.readFileSync(PORT_HTML, "utf8"));
  const ids = Object.keys(o);
  assert.equal(ids.filter((i) => o[i].tag === "input").length, 34);
  assert.equal(ids.filter((i) => o[i].tag === "select").length, 7);
  assert.equal(ids.length, 41);
  for (const id of ids) assert.deepStrictEqual(p[id], o[id], id);
  // 1110-01: 원문에 없는 칸은 추적 손절 3칸뿐
  assert.deepStrictEqual(Object.keys(p).filter((i) => i !== "dataSource" && !(i in o)).sort(),
    ["trailingMode", "trailingPct", "trailingStop"]);
  // 옛 200선 기울기 칸은 없다 (1105-06 결정 ②)
  assert.equal(p.minSlope, undefined);
  assert.equal(p.slopeDrop, undefined);
  assert.equal(p.dataSource.tag, "select");
  assert.equal(Object.keys(p).filter((i) => i !== "dataSource").length, 44);
  const portHtml = fs.readFileSync(PORT_HTML, "utf8");
  // R7 폐기(결정 1026-23 2 가): 업비트 출처는 서버 경로. select 는 숨겨 값만 맞춘다.
  assert.match(portHtml, /<select id="dataSource" hidden>/);
  assert.deepStrictEqual(p.dataSource.options, ["binance", "upbit"]);
});

// 거래 CSV 에서 한 칸 빼기 (헤더 기준)
function dropColumn(csvText, col) {
  const lines = csvText.split("\n");
  const head = lines[0].split(",");
  const k = head.indexOf(col);
  if (k < 0) return csvText;
  return lines.map((l) => { const c = l.split(","); c.splice(k, 1); return c.join(","); }).join("\n");
}

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

  // 기본값(구간 횟수 0 · 상승폭 0)에서는 매매가 같다. 차이 1(Q3 ②)은 거래 기록의 구간 순번 칸만 바꾼다.
  test(`set ${set}: trades/weekly/monthly/sweep CSV identical (구간 순번 칸 제외)`, async () => {
    const [o, p] = await get();
    for (const k of ["trades", "weekly", "monthly", "sweep"]) {
      assert.ok(o[k].length > 0, `${k} CSV 가 비어 있음 — 비교 무의미`);
      if (k === "trades") {
        assert.ok(o[k].split("\n")[0].includes("episodeBreakoutIndex"), "Ver2 거래 CSV 에 구간 순번 칸");
        assert.equal(dropColumn(p[k], "episodeBreakoutIndex"), dropColumn(o[k], "episodeBreakoutIndex"), k);
      } else {
        assert.equal(p[k], o[k], k);
      }
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
