// 2차 T16: 신버전 홈·차트 새 전략 채움 시험(그림 2-가·2-나). homeView·signalSentence·tradeRow·chartLines + chart.js.
// app.js 는 일반 script — home.test.mjs 와 같은 방식으로 전역에 올려 읽는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { ema, sma, maLines, normalizeLines, toMarkers, MARKER_TYPES } from "../../../v2/static/chart.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");

globalThis.window = globalThis;
globalThis.document = { hidden: false, addEventListener() {} };
const labels = await import(path.join(STATIC, "labels.js"));
globalThis.v2Labels = labels;
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "app.js"), "utf8"));

const NOW = Date.parse("2026-10-30T11:00:00+09:00");
const PB = { ma60p: 60, ma200p: 200, pullbackP: 60, maType: "ema", tp: 5, sl: 3, max_splits: 5 };
const EMA_ST = { mode_engine: "TEST", paused: 0, strategy: { value: "EMA" }, ticker: "KRW-ZRO", engine: { level: "ok" } };
const PB_ST = { ...EMA_ST, strategy: { value: "PULLBACK" }, pullback: PB };
const BASIC = { engine_running: true };
const HOLD = { krw: 50000, krw_locked: 0, coin: 1, coin_locked: 0, price: 1010, entry_price: 1000,
  tp_price: 1050, sl_price: 970, round: { entry: 2, max: 5, desync: false } };

// ---- 홈 배지·보유 카드 ----
test("예약 없으면 배지 4개 그대로, 예약 있으면 전략 배지 뒤에 노란 예약 배지", () => {
  assert.equal(homeView(PB_ST, HOLD, BASIC, NOW).badges.length, 4);
  assert.equal(homeView(PB_ST, HOLD, BASIC, NOW, { reservation: null }).badges.length, 4);
  const b = homeView(EMA_ST, HOLD, BASIC, NOW, { reservation: { kind: "SWITCH" } }).badges;
  assert.equal(b.length, 5);
  assert.deepEqual([b[0].id, b[2].id, b[3].id, b[4].id], ["mode-badge", "strategy-badge", "reserve-badge", "pause-badge"]);
  assert.equal(b[3].text, "전환 예약 중");
  assert.equal(b[3].cls, "p-warn");
  const r = homeView(PB_ST, HOLD, BASIC, NOW, { reservation: { kind: "REVERT" } }).badges;
  assert.equal(r[3].text, "복귀 예약 중");
});

test("분할 회차 「2 / 5회」, 회차 없으면(EMA) 「—」", () => {
  assert.equal(homeView(PB_ST, HOLD, BASIC, NOW).holding.round, "2 / 5회");
  assert.equal(homeView(EMA_ST, { ...HOLD, round: null }, BASIC, NOW).holding.round, "—");
});

test("익절·손절 라벨: 새 전략은 적용본 %(+5%·-3%), EMA 는 1차 계산 그대로", () => {
  const h = homeView(PB_ST, HOLD, BASIC, NOW).holding;
  assert.equal(h.tp.label, "익절 가격 (+5%)");
  assert.equal(h.sl.label, "손절 가격 (-3%)");
  assert.equal(h.tp.price, "1,050원");
  const e = homeView(EMA_ST, { ...HOLD, round: null }, BASIC, NOW).holding;
  assert.equal(e.tp.label, "익절 가격 (+5.0%)");
  assert.equal(e.sl.label, "손절 가격 (-3.0%)");
  const f = homeView({ ...PB_ST, pullback: { ...PB, tp: 1.5 } }, HOLD, BASIC, NOW).holding;
  assert.equal(f.tp.label, "익절 가격 (+1.5%)");
});

// ---- 최신 신호 문장 ----
const ctx = (over) => ({ pb: PB, round: { entry: 2, max: 5, desync: false }, reservation: null, holding: false, ...over });
const buyRow = (pb, over) => ({ kind: "buy", bar_time: "2026-10-30T10:42:00+09:00", overall_ok: 0, failed_keys: [pb.state], pb, ...over });

test("눌림 상태(armed) 문장", () => {
  const s = signalSentence(buyRow({ state: "WAIT_PULLBACK", round: 2, armed: 1, active: 1, holding: 0 }), ctx());
  assert.equal(s.text, "눌림 대기 중 — 가격이 60선 아래로 내려옴. 다시 위에서 마감하면 3회차 매수");
  assert.equal(s.title, "최신 신호 · 10:42 봉");
});

test("눌림 상태(armed) 문장도 기준선 기간(pullbackP)을 쓴다", () => {
  const s = signalSentence(buyRow({ state: "WAIT_PULLBACK", round: 1, armed: 1, active: 1, holding: 0 }),
    ctx({ pb: { ...PB, pullbackP: 40 } }));
  assert.equal(s.text, "눌림 대기 중 — 가격이 40선 아래로 내려옴. 다시 위에서 마감하면 2회차 매수");
});

test("눌림 전(armed 0) 문장은 pullbackP 기간을 쓴다", () => {
  const s = signalSentence(buyRow({ state: "WAIT_PULLBACK", round: 0, armed: 0, active: 1, holding: 0 }),
    ctx({ pb: { ...PB, pullbackP: 40 } }));
  assert.equal(s.text, "매수 대기 — 가격이 40선 위. 40선 아래로 내려왔다가 다시 위에서 마감하면 1회차 매수");
});

test("감시 구간 밖: 미보유는 사유(기간 반영), 보유는 보유 유지", () => {
  const row = buyRow({ state: "NOT_ACTIVE", round: 0, armed: 0, active: 0, holding: 0, inactive_reason: "not_golden" });
  assert.equal(signalSentence(row, ctx({ pb: { ...PB, ma60p: 50, ma200p: 150 } })).text,
    "매수 대기 — 감시 구간 아님 (50선 ≤ 150선)");
  assert.equal(signalSentence({ ...row, kind: "sell", pb: { ...row.pb, holding: 1 } }, ctx({ holding: true })).text,
    "보유 유지 — 감시 구간 밖. 익절·손절 가격 안");
});

test("회차 다 참·어긋남·예약 문장과 우선순위", () => {
  const full = { kind: "sell", bar_time: "2026-10-30T10:42:00+09:00", triggered: 0,
    pb: { state: "SPLITS_FULL", round: 5, armed: 1, active: 1, holding: 1 } };
  assert.equal(signalSentence(full, ctx({ holding: true, round: { entry: 5, max: 5, desync: false } })).text,
    "보유 유지 — 분할 5 / 5회 모두 매수함. 익절·손절 가격 안");
  assert.equal(signalSentence(full, ctx({ holding: true, round: { entry: 5, max: 5, desync: true } })).text,
    "보유 유지 — 앱 주문이 섞여 추가 매수를 멈췄습니다. 익절·손절은 그대로");
  assert.equal(signalSentence(full, ctx({ holding: true, reservation: { kind: "REVERT" } })).text,
    "복귀 예약 중 — 봇 추가 매수 안 함");
  // 매도 발동이 가장 앞
  assert.equal(signalSentence({ ...full, triggered: 1, trigger_key: "TP" }, ctx({ reservation: { kind: "REVERT" } })).text,
    "매도 — " + labels.reasonLabel("TP"));
});

test("EMA 사용자: 예약 중이면 예약 문장, 아니면 1차 문장 그대로", () => {
  const row = { kind: "buy", bar_time: "2026-10-30T10:42:00+09:00", overall_ok: 0, failed_keys: ["NO_SIGNAL"] };
  assert.equal(signalSentence(row, { reservation: { kind: "SWITCH" } }).text, "전환 예약 중 — 봇 추가 매수 안 함");
  assert.equal(signalSentence(row, { reservation: null }).text, signalSentence(row).text);
  assert.equal(signalSentence(row).text, "매수 대기 — " + labels.failedKeysText(["NO_SIGNAL"]));
});

test("투자자 문장에 내부 코드가 나오지 않는다", () => {
  // services/terminology.py PULLBACK_STATE_LABEL 16키(labels.js 표와 같음 — test_labels_match_server)
  const states = ["NOT_ACTIVE", "WAIT_PULLBACK", "WAIT_GOLDEN", "SPLITS_FULL", "PULLBACK_CAP", "DESYNC",
    "SWITCH_RESERVED", "WARMUP", "REPLAY", "BACKFILL", "PENDING_FILL", "STATE_POLLUTED", "TENTATIVE",
    "UNCONFIRMED", "DUPLICATE", "OFF_HOURS"];
  for (const st of states) assert.ok(labels.FAILED_KEY_LABELS[st], st);
  for (const st of states) {
    for (const armed of [0, 1]) {
      const t = signalSentence(buyRow({ state: st, round: 1, armed, active: 1, holding: 0, inactive_reason: "slope_low" }), ctx()).text;
      assert.doesNotMatch(t, /[A-Z_]{4,}|armed|slope_/, t);
    }
  }
});

// ---- 최근 거래 ----
test("회차 매수 「매수 2회」·건너뜀 사유, EMA 행은 1차 그대로", () => {
  const t = tradeRow({ type: "BUY", round: 2, reason: "PULLBACK", price: 1000, qty: 1, timestamp: "2026-10-30T10:15:00+09:00" }, NOW);
  assert.equal(t.kind, "매수 2회");
  assert.equal(t.kindCls, "up");
  const s = tradeRow({ type: "BUY_REJECTED", reason: "PULLBACK", skip_reason: "원화 잔고 부족", timestamp: "2026-10-30T10:20:00+09:00" }, NOW);
  assert.equal(s.kind, "거절");
  assert.equal(s.reason, "원화 잔고 부족");
  const e = tradeRow({ type: "BUY", reason: "EMA_GC", price: 1000, qty: 1, timestamp: "2026-10-30T10:15:00+09:00" }, NOW);
  assert.equal(e.kind, "매수");
  assert.equal(e.reason, labels.reasonLabel("EMA_GC"));
});

// ---- 차트 선 설정(U1·U3) ----
test("chartLines: EMA 사용자는 1차 그대로(60·200 단순, 400봉, 범례 없음)", () => {
  assert.deepEqual(chartLines(EMA_ST), { lines: [60, 200], maType: "sma", target: 400, legend: null, note: "", caption: "", sig: "base" });
  assert.deepEqual(chartLines(null).lines, [60, 200]);
});

test("chartLines: 새 전략은 적용본 기간·방식, 봉 수 = 2 × 가장 긴 기간(최대 2000)", () => {
  const c = chartLines(PB_ST);
  assert.deepEqual(c.lines, [{ period: 60, slot: "trend" }, { period: 200, slot: "long" }]);
  assert.equal(c.maType, "ema");
  assert.equal(c.target, 400);
  assert.deepEqual(c.legend, { a: "60선", b: "200선", pull: "" });
  assert.match(c.note, /엔진 값과 조금 다를 수 있습니다/);
  assert.equal(chartLines({ pullback: { ...PB, ma200p: 300 } }).target, 600);
  assert.equal(chartLines({ pullback: { ...PB, ma200p: 1500 } }).target, 2000);
  assert.equal(chartLines({ pullback: { ...PB, ma60p: 10, ma200p: 50 } }).target, 400);   // 기본 400 아래로는 안 줄임
  assert.equal(chartLines({ pullback: { ...PB, maType: "sma" } }).note, "");
});

test("chartLines: 기준선(pullbackP)이 60선 기간과 다를 때만 점선 하나 더(U3)", () => {
  const c = chartLines({ pullback: { ...PB, pullbackP: 40 } });
  assert.deepEqual(c.lines[2], { period: 40, slot: "pull" });
  assert.equal(c.legend.pull, "40선(기준선)");
  assert.equal(c.caption, "캔들, 60선·200선, 40선(눌림목 기준선), 봇이 실제로 사고판 자리. 손가락으로 확대·이동합니다.");
  // 기본값(60·200·60)이면 1차 화면 문장과 글자 하나까지 같다(그림 2-나)
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  assert.ok(html.includes(chartLines(PB_ST).caption));
  assert.equal(chartLines({ pullback: { ...PB, ma60p: 50, pullbackP: 50 } }).caption,
    "캔들, 50선·200선(눌림목 기준선), 봇이 실제로 사고판 자리. 손가락으로 확대·이동합니다.");
  assert.notEqual(c.sig, chartLines(PB_ST).sig);
  assert.equal(chartLines(PB_ST).lines.length, 2);
});

// ---- chart.js ----
test("ema: 첫 값 = 단순평균 시드, 이후 α=2/(p+1)", () => {
  const v = [1, 2, 3, 4, 5, 6];
  const e = ema(v, 3);
  assert.deepEqual(e.slice(0, 2), [null, null]);
  assert.equal(e[2], 2);
  assert.equal(e[3], 3);          // 2 + 0.5*(4-2)
  assert.equal(e[5], 5);
  assert.deepEqual(ema([1, 2], 3), [null, null]);
});

test("maLines: 방식에 따라 sma/ema", () => {
  const v = [5, 1, 9, 2, 8, 3, 7, 4, 6, 10];
  assert.notDeepEqual(ema(v, 3), sma(v, 3));
  assert.deepEqual(maLines(v, [3], "ema")[3], ema(v, 3));
  assert.deepEqual(maLines(v, [3])[3], sma(v, 3));
  assert.deepEqual(maLines(v, [3], "sma")[3], sma(v, 3));
});

test("normalizeLines: 숫자 배열(1차) → trend·long 칸, 객체는 그대로", () => {
  assert.deepEqual(normalizeLines([60, 200]), [{ period: 60, slot: "trend" }, { period: 200, slot: "long" }]);
  assert.deepEqual(normalizeLines(undefined), [{ period: 60, slot: "trend" }, { period: 200, slot: "long" }]);
  assert.deepEqual(normalizeLines([{ period: 40, slot: "pull" }, { period: 0, slot: "x" }]), [{ period: 40, slot: "pull" }]);
});

test("toMarkers(U2): BUY·SELL 만, 거절·취소 표식 없음, bar_time 없는 외부 매수·매도도 없음", () => {
  const rows = [
    { type: "BUY", bar_time: "2026-10-30T09:31:00+09:00" },
    { type: "BUY_REJECTED", bar_time: "2026-10-30T09:32:00+09:00" },
    { type: "BUY_CANCELED", bar_time: "2026-10-30T09:33:00+09:00" },
    { type: "SELL_REJECTED", bar_time: "2026-10-30T09:34:00+09:00" },
    { type: "HTS_SELL", bar_time: "2026-10-30T09:35:00+09:00" },
    { type: "SELL", bar_time: "2026-10-30T09:36:00+09:00" },
    { type: "HTS_SELL", bar_time: null },              // 실제 외부 매도 행(bar_time 없음)
    { type: "BUY", bar_time: null },                   // 실제 외부 매수 행(type BUY, bar_time 없음)
  ];
  const m = toMarkers(rows);
  assert.deepEqual(m.map((x) => x.text), ["매수", "매도"]);
  assert.deepEqual(m.map((x) => x.shape), ["arrowUp", "arrowDown"]);
  assert.deepEqual(MARKER_TYPES, ["BUY", "SELL"]);
});

