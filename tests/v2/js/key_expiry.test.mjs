// 1122-01 업비트 키 만료 배지: 맨 끝 · 글·색. app.js 는 일반 script — home.test.mjs 와 같은 방식으로 읽는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");

globalThis.window = globalThis;
globalThis.document = { hidden: false, addEventListener() {} };
globalThis.v2Labels = await import(path.join(STATIC, "labels.js"));
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "kst_time.js"), "utf8"));
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "app.js"), "utf8"));

const NOW = Date.parse("2026-11-22T10:00:00+09:00");
const STATUS = { mode_engine: "LIVE", paused: 0, strategy: { value: "EMA" }, ticker: "KRW-ZRO",
  interval: "minute1", engine: { level: "ok", ago_sec: 10 } };
const BASIC = { engine_running: true };
const KE = (level, label) => ({ expire_at: "2027-11-19T12:21:56+09:00", days_left: 362, last_ok_at: null, level, label });

test("키 만료 칸이 없으면 배지 4개 그대로", () => {
  const v = homeView(STATUS, {}, BASIC, NOW);
  assert.equal(v.badges.length, 4);
  assert.ok(!v.badges.some((b) => b.id === "key-expiry-badge"));
});

test("키 만료 배지는 맨 끝(연속 손절 배지 뒤)", () => {
  const assets = { pause_until: "2026-11-22T12:00:00+09:00" };
  const v = homeView({ ...STATUS, key_expiry: KE("ok", "업비트 키 · 2027-11-19 만료 (362일 남음)") }, assets, BASIC, NOW,
    { reservation: null });
  const last = v.badges[v.badges.length - 1];
  assert.equal(last.id, "key-expiry-badge");
  assert.equal(last.text, "업비트 키 · 2027-11-19 만료 (362일 남음)");
  assert.equal(v.badges[v.badges.length - 2].id, "sl-pause-badge");
});

test("단계별 색: 보통·경고·위험", () => {
  const cls = (level) => keyExpiryBadge(KE(level, "x")).cls;
  assert.equal(cls("ok"), "p-off");
  assert.equal(cls("warn"), "p-warn");
  assert.equal(cls("danger"), "p-bad");
  assert.equal(cls("이상한값"), "p-bad");
});

test("글이 없거나 모양이 틀리면 배지 없음", () => {
  assert.equal(keyExpiryBadge(null), null);
  assert.equal(keyExpiryBadge({ level: "ok" }), null);
  assert.equal(keyExpiryBadge({ level: "ok", label: "" }), null);
  assert.equal(keyExpiryBadge("x"), null);
});

test("위험색 클래스가 style.css 에 있다", () => {
  const css = fs.readFileSync(path.join(STATIC, "style.css"), "utf8");
  assert.match(css, /\.p-bad\s*\{/);
});
