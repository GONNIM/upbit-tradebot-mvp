// Ver2 기준 파일과 일부러 다르게 만든 2곳의 시험 (1105-06 Q3 ② · 결정 ③, plan.md 1절).
// 같은 입력을 Ver2 원문 simulate 와 이식본(backtester.js) simulate 에 넣어 차이가 정해진 대로인지 본다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { ROOT, ver2Script } from "./ver2_source.mjs";

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
const ORIG = load(ver2Script());
const PORT = load(fs.readFileSync(path.join(ROOT, "v2/static/backtester.js"), "utf8"));

const BASE_CFG = {
  maType: "ema", ma60p: 60, ma200p: 200, pullbackP: 60, slopeLB: 20,
  gcMaxGapPct: 0, ma60MinSlope: 0, ma60SlopeDrop: 0,
  slStreakPause: 0, slStreakCooldownHours: 6,
  episodePullbackCap: 0, episodeTpDecayPct: 50, episodeTpFloorPct: 0.3,
  buyOnGoldenCross: false, maxSplits: 3, maxPullbackBuys: 5,
  tp: 2.5, sl: 3, capital: 10000, fee: 0.05, deadcross: "no", compounding: "no",
};

function sim(ctx, ohlc, arrays, cfg) {
  const bars = ohlc.map((b, i) => ({ t: 1_700_000_000_000 + i * 60000, o: b[0], h: b[1], l: b[2], c: b[3] }));
  ctx.__args = { bars, ...arrays, cfg: { ...BASE_CFG, ...cfg } };
  return vm.runInContext("simulate(__args.bars,__args.maTrend,__args.ma200,__args.slope60,__args.maPullback,__args.cfg)", ctx);
}
const fill = (n, v) => Array.from({ length: n }, () => v);

// 질문 PDF 예시: 횟수 2 · 감소율 50 · TP 2.5. 첫 거래에서 눌림목으로 3번 사고 익절, 같은 구간 둘째 거래.
// Ver2 원문(추가 분할도 셈): 둘째 거래 = 4번째 → TP 0.625%. 우리(Q3 ②): 2번째 → TP 2.5%.
test("Q3 ②: 같은 거래의 추가 분할매수는 구간 순번에 세지 않는다 (질문 PDF 예시)", () => {
  const P = [
    [100, 101, 99, 101],     // 0 눌림 → 재돌파: 1차 매수(1봉 시가)
    [100, 100.5, 100, 100.2],
    [100, 100.5, 99, 101],   // 2 → 2차 매수(3봉)
    [100, 100.5, 100, 100.2],
    [100, 100.5, 99, 101],   // 4 → 3차 매수(5봉)
    [100, 100.5, 100, 100.2],
    [100, 103, 100, 102],    // 6 익절(평단 100 → 102.5)
    [100, 100.5, 99, 101],   // 7 새 거래 눌림목 매수(8봉)
    [100, 100.2, 100, 100.1],
    [100, 103, 100, 102],    // 9 둘째 거래 익절
    [100, 100.1, 100, 100],
  ];
  const n = P.length;
  const arrays = { maTrend: fill(n, 110), ma200: fill(n, 100), slope60: fill(n, 1), maPullback: fill(n, 100) };
  const cfg = { episodePullbackCap: 2, episodeTpDecayPct: 50, tp: 2.5 };
  const o = sim(ORIG, P, arrays, cfg);
  const p = sim(PORT, P, arrays, cfg);
  assert.equal(o.trades.length, 2);
  assert.equal(p.trades.length, 2);
  assert.equal(o.trades[0].entries, 3);
  assert.equal(o.trades[1].episodeBreakoutIndex, 4);
  assert.equal(o.trades[1].tpUsedPct, 0.625);
  assert.equal(p.trades[0].episodeBreakoutIndex, 1);
  assert.equal(p.trades[1].episodeBreakoutIndex, 2);
  assert.equal(p.trades[1].tpUsedPct, 2.5);
});

test("Q3 ②: 횟수를 넘은 새 거래는 TP 를 줄이고 하한 밑으로는 줄이지 않는다", () => {
  // 한 구간에서 새 거래 4번(각 1번 매수 후 익절). 횟수 1 · 감소율 90 · 하한 0.3 · TP 2.5
  const one = [[100, 101, 99, 101], [100, 100.2, 100, 100.1], [100, 103, 100, 102]];
  const P = [...one, ...one, ...one, ...one, [100, 100.1, 100, 100]];
  const n = P.length;
  const arrays = { maTrend: fill(n, 110), ma200: fill(n, 100), slope60: fill(n, 1), maPullback: fill(n, 100) };
  const p = sim(PORT, P, arrays, { episodePullbackCap: 1, episodeTpDecayPct: 90, episodeTpFloorPct: 0.3, maxSplits: 1 });
  assert.deepStrictEqual(Array.from(p.trades, (t) => t.episodeBreakoutIndex), [1, 2, 3, 4]);   // vm 배열은 다른 realm
  const tps = Array.from(p.trades, (t) => +t.tpUsedPct.toFixed(6));
  assert.deepStrictEqual(tps, [2.5, 0.3, 0.3, 0.3]);   // 2번째 = max(0.3, 2.5×0.1=0.25)
});

// 결정 ③: 상승폭 때문에 건너뛴 골든크로스는 실제로 살 수 있었던 때만 센다.
function gcCase(slope) {
  const P = [[100, 100, 100, 100], [100, 105, 100, 105], [105, 105, 105, 105], [105, 105, 105, 105]];
  const arrays = {
    maTrend: [90, 110, 110, 110], ma200: fill(4, 100), slope60: [1, slope, slope, slope], maPullback: fill(4, 200),
  };
  const cfg = { buyOnGoldenCross: true, gcMaxGapPct: 2 };
  return { o: sim(ORIG, P, arrays, cfg), p: sim(PORT, P, arrays, cfg) };
}

test("결정 ③: 감시가 꺼진 골든크로스(60선 하락)는 건너뜀 횟수에 넣지 않는다", () => {
  const { o, p } = gcCase(-1);
  assert.equal(o.gcGapBlocked, 1);   // Ver2 원문은 셈
  assert.equal(p.gcGapBlocked, 0);   // 우리는 세지 않음
  assert.equal(o.trades.length + (o.mark ? 1 : 0), 0);
  assert.equal(p.trades.length + (p.mark ? 1 : 0), 0);
});

test("결정 ③: 살 수 있었는데 상승폭 때문에 막힌 골든크로스는 둘 다 센다", () => {
  const { o, p } = gcCase(1);
  assert.equal(o.gcGapBlocked, 1);
  assert.equal(p.gcGapBlocked, 1);
  assert.equal(p.mark, null);   // 1차 매수 안 함, 눌림목 기준선 200 이라 눌림목 매수도 없음
});
