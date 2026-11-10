// 1110-01: 눌림목 추적 손절(트레일링 스톱) — 백테스터 simulate 의 세 번째 차이(fixtures/ver2_patches.json, 1110-01).
// 꺼짐(기본)이면 Ver2 원문(+1105-06 두 곳) simulate 와 결과가 같고, 켜짐이면 구버전(EMA) 규칙과 같은 식으로 판다:
//   무장 = 종가 수익률 ≥ 이 거래 TP% (익절가에서 팔지 않음) · 최고가 = 무장 뒤 종가 최댓값
//   비율 = (최고가 − 종가) / (최고가 − 평단) ≥ 폭% · 고정폭 = 종가 ≤ 최고가 − (무장 종가 − 평단) × 폭%
//   순서: 데드크로스 → 손절(저가) → 추적 손절(종가, 체결가 = 종가). 무장 중에는 추가 매수 안 함(㉢).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { ROOT, PATCHES, ver2Script } from "./ver2_source.mjs";

function load(scriptText) {
  const el = () => ({ value: "", textContent: "", innerHTML: "", style: {}, addEventListener() {}, checked: false });
  const ctx = {
    document: { getElementById: el, createElement: el, addEventListener() {}, querySelectorAll: () => [] },
    setTimeout: (fn) => { fn(); return 0; },
    console,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(scriptText, ctx);
  return ctx;
}
// 비교 기준 = Ver2 원문 + 1110-01 이 아닌 차이(1105-06 두 곳)만 적용한 스크립트
function baseScript() {
  let s = ver2Script();
  for (const p of PATCHES.patches) if (!p.why.includes("1110-01")) s = s.replace(p.find, () => p.replace);
  return s;
}
const ORIG = load(baseScript());
const PORT = load(fs.readFileSync(path.join(ROOT, "v2/static/backtester.js"), "utf8"));

const BASE_CFG = {
  maType: "ema", ma60p: 60, ma200p: 200, pullbackP: 60, slopeLB: 20,
  gcMaxGapPct: 0, ma60MinSlope: 0, ma60SlopeDrop: 0,
  slStreakPause: 0, slStreakCooldownHours: 6,
  episodePullbackCap: 0, episodeTpDecayPct: 50, episodeTpFloorPct: 0.3,
  buyOnGoldenCross: false, maxSplits: 3, maxPullbackBuys: 5,
  tp: 2, sl: 3, capital: 10000, fee: 0.05, deadcross: "no", compounding: "no",
};

function sim(ctx, ohlc, arrays, cfg) {
  const bars = ohlc.map((b, i) => ({ t: 1_700_000_000_000 + i * 60000, o: b[0], h: b[1], l: b[2], c: b[3] }));
  ctx.__args = { bars, ...arrays, cfg: { ...BASE_CFG, ...cfg } };
  const r = vm.runInContext("simulate(__args.bars,__args.maTrend,__args.ma200,__args.slope60,__args.maPullback,__args.cfg)", ctx);
  return JSON.parse(JSON.stringify(r));   // vm realm 밖으로
}
const fill = (n, v) => Array.from({ length: n }, () => v);
const flat = (n) => ({ maTrend: fill(n, 110), ma200: fill(n, 100), slope60: fill(n, 1), maPullback: fill(n, 100) });

// 결정적 의사 난수(시드 고정) 봉
function randomBars(n, seed) {
  let s = seed >>> 0;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const out = [];
  let p = 100;
  for (let i = 0; i < n; i++) {
    const o = p;
    const c = Math.max(1, o * (1 + (rnd() - 0.5) * 0.04));
    const h = Math.max(o, c) * (1 + rnd() * 0.01);
    const l = Math.min(o, c) * (1 - rnd() * 0.01);
    out.push([o, h, l, c]);
    p = c;
  }
  return out;
}
function randomArrays(P, seed) {
  let s = (seed * 7919) >>> 0;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const n = P.length;
  const maPullback = P.map((b) => b[3] * (1 + (rnd() - 0.5) * 0.02));
  const maTrend = Array.from({ length: n }, (_, i) => (Math.floor(i / 40) % 5 === 4 ? 90 : 110));
  return { maTrend, ma200: fill(n, 100), slope60: fill(n, 1), maPullback };
}

test("꺼짐(기본·no·키 없음)이면 기준(Ver2 원문 + 1105-06 차이) simulate 와 거래·손익이 같다", () => {
  for (let seed = 1; seed <= 25; seed++) {
    const P = randomBars(400, seed);
    const A = randomArrays(P, seed);
    const o = sim(ORIG, P, A, {});
    for (const extra of [{}, { trailingStop: "no", trailingMode: "fixed", trailingPct: 50 }]) {
      const p = sim(PORT, P, A, extra);
      assert.deepStrictEqual(p.trades, o.trades, `seed ${seed}`);
      assert.equal(p.equity, o.equity);
      assert.deepStrictEqual(p.mark, o.mark);
    }
  }
});

// 공통 시나리오: 1봉 눌림목 신호 → 2봉 시가 100 체결(평단 100). TP 2%.
const OPEN = [[100, 100.5, 99, 100.5], [100, 100.3, 100, 100.2]];   // 1봉 저가 100 = 기준선(미만 아님) → 추가 매수 없음

test("켜짐·비율: 익절가를 넘어도 팔지 않고, 최고가 대비 수익의 폭%를 잃으면 종가에 판다", () => {
  const P = [...OPEN,
    [100.2, 103.5, 100.2, 103],   // 2 종가 3% ≥ 2% → 무장, 최고 103
    [103, 106.5, 103, 106],       // 3 최고 106 (수익 6)
    [106, 106, 103.5, 104],       // 4 잃은 몫 2/6 = 33% < 50%
    [104, 104, 102.5, 102.9],     // 5 3.1/6 = 51.7% ≥ 50% → 판다 @102.9
    [103, 103, 103, 103]];
  const off = sim(PORT, P, flat(P.length), {});
  assert.equal(off.trades[0].exitType, "TP");
  assert.equal(off.trades[0].exit, 102);
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "ratio", trailingPct: 50 });
  assert.equal(on.trades.length, 1);
  assert.equal(on.trades[0].exitType, "TS");
  assert.equal(on.trades[0].exit, 102.9);
  assert.equal(on.trades[0].exitTime, new Date(1_700_000_000_000 + 5 * 60000).toISOString());
});

test("켜짐·고정폭: 무장 순간 수익 × 폭% 를 금액으로 고정하고 최고가에서 그만큼 내리면 판다", () => {
  const P = [...OPEN,
    [100.2, 104.5, 100.2, 104],   // 2 무장: 고정 = (104−100)×50% = 2, 최고 104
    [104, 108.5, 104, 108],       // 3 최고 108 → 판매선 106
    [108, 108, 106.2, 106.5],     // 4 106.5 > 106 유지
    [106.5, 106.5, 105.5, 106],   // 5 106 ≤ 106 → 판다
    [106, 106, 106, 106]];
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "fixed", trailingPct: 50 });
  assert.equal(on.trades.length, 1);
  assert.equal(on.trades[0].exitType, "TS");
  assert.equal(on.trades[0].exit, 106);
});

test("켜짐: 고가만 익절가를 스치고 종가가 못 미치면 무장하지 않는다 (익절도 안 함)", () => {
  const P = [...OPEN,
    [100.2, 103, 100.2, 101],     // 고가 103 ≥ 102, 종가 1% < 2% → 그대로
    [101, 101.2, 96.5, 97],       // 저가 96.5 ≤ 97 → 손절 @97
    [97, 97, 97, 97]];
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "ratio", trailingPct: 50 });
  assert.equal(on.trades[0].exitType, "SL");
  assert.equal(on.trades[0].exit, 97);
  const off = sim(PORT, P, flat(P.length), {});
  assert.equal(off.trades[0].exitType, "TP");
});

test("켜짐: 같은 봉에서 손절가(저가)가 닿으면 손절이 먼저다", () => {
  const P = [...OPEN,
    [100.2, 103.5, 100.2, 103],   // 무장
    [103, 103, 96, 102],          // 저가 96 ≤ 97 → 손절 @97 (추적 손절 판정 전)
    [102, 102, 102, 102]];
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "ratio", trailingPct: 10 });
  assert.equal(on.trades[0].exitType, "SL");
  assert.equal(on.trades[0].exit, 97);
});

test("㉢ 켜짐: 무장 중에는 눌림목 추가 매수를 하지 않는다(꺼짐이면 산다)", () => {
  // 3봉에서 무장 뒤 4봉이 눌림(저가 < 기준선) → 재돌파(종가 > 기준선) 조건
  const P = [...OPEN,
    [100.2, 103.5, 100.2, 103],   // 2 무장 (꺼짐이면 고가 103.5 ≥ 102 → 익절)
    [103, 104, 103, 103.8],       // 3
    [103.8, 104, 103.5, 103.9],   // 4
    [104, 104, 104, 104]];
  const A = flat(P.length);
  A.maPullback = [100, 100, 100, 100, 103.6, 100];   // 4봉: 저가 103.5 < 103.6, 종가 103.9 > 103.6
  const on = sim(PORT, P, A, { trailingStop: "yes", trailingMode: "ratio", trailingPct: 90 });
  assert.equal(on.trades.length, 0);
  assert.equal(on.mark.entries, 1);
  // 무장 없이 같은 눌림목이면 산다(대조): TP 를 아주 높여 무장·익절 모두 없게
  const noArm = sim(PORT, P, A, { trailingStop: "yes", trailingMode: "ratio", trailingPct: 90, tp: 50 });
  assert.equal(noArm.mark.entries, 2);
});

test("켜짐: 구간 TP 감소가 있으면 이 거래의 TP% 로 무장한다", () => {
  // 횟수 0(끔)과 같은 경로를 쓰는지만 본다 — 이 거래 TP = 설정 TP
  const P = [...OPEN, [100.2, 102.5, 100.2, 102.1], [102.1, 102.1, 100.9, 101], [101, 101, 101, 101]];
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "ratio", trailingPct: 50 });
  assert.equal(on.trades[0].exitType, "TS");   // 2.1% ≥ 2% 무장 → 2봉 뒤 51% 잃음
  assert.equal(on.trades[0].tpUsedPct, 2);
});

test("통계: 추적 손절 청산 횟수를 센다", () => {
  const P = [...OPEN, [100.2, 103.5, 100.2, 103], [103, 103, 101, 101.4], [101, 101, 101, 101]];
  const on = sim(PORT, P, flat(P.length), { trailingStop: "yes", trailingMode: "ratio", trailingPct: 50 });
  PORT.__res = on;
  PORT.__cfg = { ...BASE_CFG, trailingStop: "yes" };
  const s = JSON.parse(JSON.stringify(vm.runInContext("stats(__res,__cfg)", PORT)));
  assert.equal(s.ts, 1);
  assert.equal(s.tp, 0);
  assert.equal(vm.runInContext('exitLabel("TS")', PORT), "추적 손절");
});
