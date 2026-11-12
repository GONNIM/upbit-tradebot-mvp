// 1112-01 화면 시각 공용 표기 「YYMMDD:HH:MM」(KST) 시험: kst_time.js · save.js 사본 · chart.js 십자선 · index.html 읽기 순서.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");
const read = (n) => fs.readFileSync(path.join(STATIC, n), "utf8");

// kst_time.js 를 따로 된 vm 문맥에서 돌려 kstStamp 를 꺼낸다(다른 시험의 globalThis 와 섞이지 않게)
const sandbox = { Date, Number, String };
sandbox.globalThis = sandbox;
vm.runInNewContext(read("kst_time.js"), sandbox);
const kstStamp = sandbox.kstStamp;

test("kstStamp: 오늘·어제·그 전 모두 같은 모양, 초는 버린다", () => {
  assert.equal(typeof kstStamp, "function");
  assert.equal(kstStamp("2026-11-12T15:18:59+09:00"), "261112:15:18");
  assert.equal(kstStamp("2026-11-11T23:00:00+09:00"), "261111:23:00");
  assert.equal(kstStamp("2026-10-25T09:05:00+09:00"), "261025:09:05");
});

test("kstStamp: KST 경계(UTC 14:59 / 15:00 = KST 23:59 / 00:00)와 연말 넘김", () => {
  assert.equal(kstStamp("2026-11-11T14:59:00Z"), "261111:23:59");
  assert.equal(kstStamp("2026-11-11T15:00:00Z"), "261112:00:00");
  assert.equal(kstStamp("2026-12-31T23:59:00+09:00"), "261231:23:59");
  assert.equal(kstStamp("2026-12-31T15:00:00Z"), "270101:00:00");
  assert.equal(kstStamp("2030-01-01T00:00:00+09:00"), "300101:00:00");
});

test("kstStamp: Date·epoch 밀리초도 받는다, 값 없음·엉터리는 null", () => {
  const ms = Date.parse("2026-11-12T06:18:00Z");
  assert.equal(kstStamp(ms), "261112:15:18");
  assert.equal(kstStamp(new Date(ms)), "261112:15:18");
  for (const v of [null, undefined, "", "엉터리", NaN, {}, new Date("x")]) assert.equal(kstStamp(v), null, String(v));
});

test("save.js 의 kstStamp 사본이 kst_time.js 와 글자 그대로 같다(한 곳에서 같은 로직)", () => {
  const body = (src) => {
    const i = src.indexOf("  function kstStamp(v) {");
    assert.ok(i >= 0);
    const j = src.indexOf("\n  }\n", i);
    return src.slice(i, j + 4);
  };
  assert.equal(body(read("save.js")), body(read("kst_time.js")));
});

test("chart.js: kst_time.js 를 import 하고 십자선 시각은 YYMMDD:HH:MM, 시간축 눈금은 그대로", async () => {
  assert.match(read("chart.js"), /import "\.\/kst_time\.js";/);
  const mod = await import(path.join(STATIC, "chart.js"));
  const sec = Date.parse("2026-11-12T06:18:00Z") / 1000;
  assert.equal(mod.crosshairTime(sec), "261112:15:18");
  assert.equal(mod.crosshairTime("2026-11-12"), "2026-11-12");
  assert.equal(mod.kstTick(sec, 3), "15:18");      // 범위 밖: 라이브러리 시간축 눈금
  assert.equal(mod.kstTime, undefined);             // 옛 HH:MM:SS 표기 함수는 없앴다
});

test("index.html: kst_time.js 를 app.js·ops.js 보다 먼저 읽는다", () => {
  const html = read("index.html");
  const k = html.indexOf('<script src="/v2/static/kst_time.js"></script>');
  assert.ok(k >= 0);
  assert.ok(k < html.indexOf("/v2/static/ops.js") && k < html.indexOf("/v2/static/app.js"));
});

test("app.js 에 옛 시각 분기(「어제」·MM-DD·HH:MM:SS) 글자가 남아 있지 않다", () => {
  const js = read("app.js");
  assert.doesNotMatch(js, /"어제"/);
  assert.doesNotMatch(js, /getUTCSeconds|getUTCHours|_kstParts|_kstDay/);
});
