// PULLBACK 기준값 생성기(2차 계획 1-3 · T10): 원본 백테스터 스크립트의 simulate() 를 그대로 불러
// 매수·매도 목록을 JSON 으로 낸다. 원본 HTML 143~938행을 바이트 그대로 vm 에 넣는다(parity.test.mjs 와 같은 자르기).
// 사용: node tests/v2/js/pullback_reference.mjs <fixture.json> <cfg.json>
//   fixture: {pages:[{url,data}], symbol, interval, days, fetched_at_ms} (Binance 고정 입력 — 원본 fetchKlines 로 봉을 만듦)
//            또는 {bars:[{t,o,h,l,c}]} (업비트 확정 봉 — 그대로 씀)
//   cfg: 원본 run() 543-556행과 같은 모양(buyOnGoldenCross 는 bool, deadcross·compounding 은 "yes"|"no")
// 출력: {"buys":[{signal_bar_t,fill_bar_t,round,trigger}], "sells":[{bar_t,type,entries}]}
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
export const ORIG = path.join(ROOT, "docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html");

export function originalScript() {
  const html = fs.readFileSync(ORIG, "utf8");
  return html.split("\n").slice(142, 938).join("\n") + "\n";
}

function stubEl() {
  return { value: "", textContent: "", innerHTML: "", style: {}, addEventListener() {} };
}

function makeContext(fixture) {
  const els = {};
  const RealDate = Date;
  class FixedDate extends RealDate {
    static now() { return fixture.fetched_at_ms ?? RealDate.now(); }
  }
  const pages = fixture.pages || [];
  let n = 0;
  const fakeFetch = async (url) => {
    const i = n++;
    if (i >= pages.length) throw new Error(`reference: ${i}번째 요청 페이지가 없음 (pages=${pages.length}), url=${url}`);
    if (pages[i].url !== url) throw new Error(`reference: ${i}번째 요청 URL 불일치\n  기대 ${pages[i].url}\n  실제 ${url}`);
    const data = pages[i].data;
    return { ok: true, status: 200, json: async () => data };
  };
  const ctx = {
    document: {
      getElementById: (id) => (els[id] ??= stubEl()),
      createElement: () => stubEl(),
      addEventListener() {},
    },
    fetch: fakeFetch,
    Date: FixedDate,
    setTimeout: (fn) => { fn(); return 0; },
    devicePixelRatio: 1,
    console,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(originalScript(), ctx);
  return ctx;
}

export async function reference(fixture, cfg) {
  const ctx = makeContext(fixture);
  ctx.__cfg = cfg;
  if (fixture.bars) {
    ctx.__bars = fixture.bars;
  } else {
    ctx.__bars = await vm.runInContext(
      `fetchKlines(${JSON.stringify(fixture.symbol)}, ${JSON.stringify(fixture.interval)}, ${Number(fixture.days)})`, ctx);
  }
  const res = vm.runInContext(`(() => {
    const bars = __bars, cfg = __cfg;
    const maTrend = computeMA(bars, cfg.ma60p, cfg.maType);
    const ma200 = computeMA(bars, cfg.ma200p, cfg.maType);
    const maPullback = computeMA(bars, cfg.pullbackP, cfg.maType);
    const slope200 = computeSlope(ma200, cfg.slopeLB);
    return simulate(bars, maTrend, ma200, slope200, maPullback, cfg);
  })()`, ctx);
  const bars = ctx.__bars;
  const idx = new Map(bars.map((b, i) => [b.t, i]));
  const buys = res.entries.map((e) => ({
    signal_bar_t: bars[idx.get(e.time) - 1].t,
    fill_bar_t: e.time,
    round: e.splitIndex,
    trigger: e.trigger,
  }));
  const sells = res.trades.map((t) => ({
    bar_t: new Date(t.exitTime).getTime(),
    type: t.exitType,
    entries: t.entries,
  }));
  return { bar_count: bars.length, buys, sells };
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const [fixturePath, cfgPath] = process.argv.slice(2);
  if (!fixturePath || !cfgPath) {
    console.error("사용: node tests/v2/js/pullback_reference.mjs <fixture.json> <cfg.json>");
    process.exit(2);
  }
  const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
  const out = await reference(fixture, cfg);
  process.stdout.write(JSON.stringify({ buys: out.buys, sells: out.sells }, null, 1) + "\n");
}
