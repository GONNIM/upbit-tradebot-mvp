// 1105-09 · plan.md 1-5: 투자자 시험 조건으로 업비트 KRW-JTO ↔ 바이낸스 JTOUSDT 를 같은 Ver2 규칙(이식본 backtester.js)으로 돌린다.
// 공개 시세만 부른다(인증 없음). 업비트는 초당 4회 이하. 실행: node docs/plans/2026-11-05-ver2-backtester/compare/run_compare.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../../..");
const OUT = here;
const DAYS = 90;
const UNIT = 3;
const U_MS = UNIT * 60000;

// 투자자 시험 그림 1·2 (docs/new-version/20261105-ver2-test-01.png·-02.png) 25칸 — 다른 칸은 눌림목 기준선 60 / 120 뿐
const CFG = {
  maType: "ema", ma60p: 60, ma200p: 200, pullbackP: 60, slopeLB: 20,
  gcMaxGapPct: 2, ma60MinSlope: -0.05, ma60SlopeDrop: 0,
  slStreakPause: 0, slStreakCooldownHours: 6,
  episodePullbackCap: 0, episodeTpDecayPct: 50, episodeTpFloorPct: 0.3,
  buyOnGoldenCross: true, maxSplits: 1, maxPullbackBuys: 5,
  tp: 2.5, sl: 3, capital: 10000, fee: 0.05, deadcross: "no", compounding: "no",
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = [];
const note = (s) => { log.push(s); console.log(s); };

function loadEngine() {
  const el = () => ({ value: "", textContent: "", innerHTML: "", style: {}, addEventListener() {}, checked: false });
  const ctx = {
    document: { getElementById: el, createElement: el, addEventListener() {}, querySelectorAll: () => [] },
    fetch, setTimeout, console, Date, Map, Promise,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "v2/static/backtester.js"), "utf8"), ctx);
  return ctx;
}

async function upbitBars(endMs) {
  const startMs = endMs - DAYS * 86400000;
  const out = new Map();
  let to = endMs;
  let calls = 0;
  while (to > startMs) {
    const iso = new Date(to).toISOString().replace(/\.\d{3}Z$/, "Z");
    const url = `https://api.upbit.com/v1/candles/minutes/${UNIT}?market=KRW-JTO&count=200&to=${encodeURIComponent(iso)}`;
    let r;
    for (let a = 0; a < 5; a++) {
      r = await fetch(url, { headers: { accept: "application/json" } });
      if (r.status === 429) { await sleep(2000 * (a + 1)); continue; }
      break;
    }
    calls++;
    if (!r.ok) throw new Error(`upbit HTTP ${r.status}`);
    const rows = await r.json();
    if (!rows.length) break;
    for (const x of rows) {
      const t = Date.parse(x.candle_date_time_utc + "Z");
      if (t >= startMs && t < endMs) out.set(t, { t, o: +x.opening_price, h: +x.high_price, l: +x.low_price, c: +x.trade_price });
    }
    const oldest = Math.min(...rows.map((x) => Date.parse(x.candle_date_time_utc + "Z")));
    if (oldest >= to) break;
    to = oldest;
    await sleep(260);   // 초당 4회 이하
  }
  return { bars: [...out.values()].sort((a, b) => a.t - b.t), calls };
}

function runOne(ctx, bars, pullbackP) {
  const cfg = { ...CFG, pullbackP };
  ctx.__a = { bars, cfg };
  return vm.runInContext(`(function(){const b=__a.bars,c=__a.cfg;
    const ma60=computeMA(b,c.ma60p,c.maType),ma200=computeMA(b,c.ma200p,c.maType),mp=computeMA(b,c.pullbackP,c.maType);
    const s60=computeSlope(ma60,c.slopeLB);const res=simulate(b,ma60,ma200,s60,mp,c);
    return {s:stats(res,c),trades:res.trades};})()`, ctx);
}

function csv(rows) {
  if (!rows.length) return "";
  const h = Object.keys(rows[0]);
  return [h.join(","), ...rows.map((r) => h.map((k) => (r[k] == null ? "" : String(r[k]))).join(","))].join("\n") + "\n";
}

const ctx = loadEngine();
const endMs = Math.floor(Date.now() / U_MS) * U_MS;   // 형성 중 봉 제외, 두 거래소 같은 끝
note(`end(UTC)=${new Date(endMs).toISOString()} days=${DAYS} unit=${UNIT}m`);

const t0 = Date.now();
const up = await upbitBars(endMs);
note(`upbit KRW-JTO: requests=${up.calls} bars=${up.bars.length} first=${new Date(up.bars[0].t).toISOString()} last=${new Date(up.bars.at(-1).t).toISOString()} took=${((Date.now() - t0) / 1000).toFixed(1)}s`);

// 바이낸스: Ver2 원문 fetchKlinesRaw 와 같은 경로(이식본 함수) — Date.now 대신 같은 끝 시각을 쓰려고 직접 페이지를 넘긴다
const bnOut = new Map();
let cursor = endMs - DAYS * 86400000;
let bnCalls = 0;
while (cursor < endMs) {
  const data = await vm.runInContext(`fetchOneKlinesPage("JTOUSDT","3m",${cursor},${endMs - 1})`, ctx);
  bnCalls++;
  if (!Array.isArray(data) || !data.length) break;
  for (const x of data) bnOut.set(+x[0], { t: +x[0], o: +x[1], h: +x[2], l: +x[3], c: +x[4] });
  const next = +data[data.length - 1][0] + U_MS;
  if (next <= cursor) break;
  cursor = next;
  await sleep(200);
}
const bn = [...bnOut.values()].filter((b) => b.t < endMs).sort((a, b) => a.t - b.t);
note(`binance JTOUSDT: requests=${bnCalls} bars=${bn.length} first=${new Date(bn[0].t).toISOString()} last=${new Date(bn.at(-1).t).toISOString()}`);

const table = [];
for (const pb of [60, 120]) {
  for (const [name, bars] of [["upbit KRW-JTO", up.bars], ["binance JTOUSDT", bn]]) {
    const r = runOne(ctx, bars, pb);
    const s = r.s;
    table.push({
      source: name, pullbackP: pb, bars: bars.length, trades: s.trades, winRatePct: +s.winRate.toFixed(3),
      returnPct: +s.ret.toFixed(3), mddPct: +s.mdd.toFixed(3), pf: +Number(s.pf).toFixed(3),
      tp: s.tp, sl: s.sl, goldenStart: s.goldenStart, pullbackStart: s.pullbackStart, gcGapBlocked: s.gcGapBlocked,
      openAtEnd: s.mark ? "yes" : "no",
    });
    const tag = name.startsWith("upbit") ? "upbit" : "binance";
    fs.writeFileSync(path.join(OUT, `trades_${tag}_pb${pb}.csv`), csv(Array.from(r.trades, (t) => ({ ...t }))));
  }
}
fs.writeFileSync(path.join(OUT, "compare_table.csv"), csv(table));
fs.writeFileSync(path.join(OUT, "run_log.txt"), log.join("\n") + "\n");
console.table(table);
