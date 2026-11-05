// PULLBACK 기준값 생성기(2차 계획 1-3 · T10): 원본 백테스터 스크립트의 simulate() 를 그대로 불러
// 매수·매도 목록을 JSON 으로 낸다. 원본 HTML 143~938행을 바이트 그대로 vm 에 넣는다(parity.test.mjs 와 같은 자르기).
// 사용: node tests/v2/js/pullback_reference.mjs <fixture.json> <cfg.json>
//   fixture: {pages:[{url,data}], symbol, interval, days, fetched_at_ms} (Binance 고정 입력 — 원본 fetchKlines 로 봉을 만듦)
//            또는 {bars:[{t,o,h,l,c}]} (업비트 확정 봉 — 그대로 씀)
//   cfg: 원본 run() 543-556행과 같은 모양(buyOnGoldenCross 는 bool, deadcross·compounding 은 "yes"|"no")
// 출력: {"buys":[{signal_bar_t,fill_bar_t,round,trigger}], "sells":[{bar_t,type,entries}]}
// 2차 T10: `node tests/v2/js/pullback_reference.mjs --write-expected` = 일치 시험 기준값(세트 × 조합)을 다시 만든다.
// 1105-09 (Ver2 2단계): 기준 원본을 옛 백테스터(2610201820 143~938행)에서 Ver2 인라인 스크립트 + 정해진 차이 2곳
// (ver2_source.patchedScript — Q3 ② 구간 순번·결정 ③ 건너뜀 횟수, 화면 이식본 backtester.js 와 같은 규칙)으로 바꿨다. 엔진은 Ver2 규칙(R1~R7)을 따르므로 옛 원본과는 더 이상 같을 수 없다.
// 옛 원본 기준값은 git 이력(커밋 f4a370f 이전 expected/)에 남아 있다.
import vm from "node:vm";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
import { VER2_HTML_PATH, patchedScript } from "./ver2_source.mjs";
export const ORIG = VER2_HTML_PATH;

// Ver2 인라인 스크립트(줄 범위 = fixtures/ver2_patches.json script_lines) + 정해진 차이 2곳. 엔진도 이 두 규칙을 따른다
// (Q3 ②: 새 거래를 연 눌림목만 구간 순번 +1, 결정 ③: 건너뜀 횟수 셈 — 매매 목록에는 영향 없음).
export function originalScript() {
  return patchedScript();
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
      querySelectorAll: () => [],   // 1105-09: Ver2 스크립트가 기동 때 숫자 칸 증감 버튼을 붙인다(attachSteppers)
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
    // Ver2 run() 709-714행과 같은 순서: 기울기는 60선(maTrend) 자체 기울기(R2)
    const maTrend = computeMA(bars, cfg.ma60p, cfg.maType);
    const ma200 = computeMA(bars, cfg.ma200p, cfg.maType);
    const maPullback = computeMA(bars, cfg.pullbackP, cfg.maType);
    const slope60 = computeSlope(maTrend, cfg.slopeLB);
    return simulate(bars, maTrend, ma200, slope60, maPullback, cfg);
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

// ---------------------------------------------------------------- 2차 T10: 일치 시험 고정 파일
// tests/fixtures/pullback/{upbit_*.json, cfgs.json, expected/<fixture>__<cfg>.json}
export const PB_DIR = path.join(ROOT, "tests/fixtures/pullback");

export function scriptSha256() {
  return crypto.createHash("sha256").update(Buffer.from(originalScript(), "utf8")).digest("hex");
}

export function loadCfgs() {
  return JSON.parse(fs.readFileSync(path.join(PB_DIR, "cfgs.json"), "utf8"));
}

/** cfgs.json 의 조합 이름 → 원본 run() 모양 cfg (base 에 덮어씀). */
export function cfgFor(cfgs, name) {
  if (!(name in cfgs.cfgs)) throw new Error(`cfgs.json 에 조합 없음: ${name}`);
  return { ...cfgs.base, ...cfgs.cfgs[name] };
}

export function expectedPath(fixtureName, cfgName) {
  return path.join(PB_DIR, "expected", `${fixtureName}__${cfgName}.json`);
}

/** 고정 파일 본문(문자열). 같은 입력이면 바이트까지 같다. */
export async function expectedText(fixtureName, cfgName, cfgs = loadCfgs(), fixture = null) {
  const fx = fixture || JSON.parse(fs.readFileSync(path.join(PB_DIR, `${fixtureName}.json`), "utf8"));
  const out = await reference(fx, cfgFor(cfgs, cfgName));
  const body = {
    meta: { fixture: fixtureName, cfg: cfgName, bar_count: out.bar_count, script_sha256: scriptSha256() },
    buys: out.buys,
    sells: out.sells,
  };
  return JSON.stringify(body, null, 1) + "\n";
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href && process.argv[2] === "--write-expected") {
  // 기준값 다시 만들기(원본 스크립트·fixture·조합이 바뀌었을 때만 — 사유를 커밋 메시지에 적음)
  const cfgs = loadCfgs();
  fs.mkdirSync(path.join(PB_DIR, "expected"), { recursive: true });
  for (const f of cfgs.meta.fixtures) {
    const fx = JSON.parse(fs.readFileSync(path.join(PB_DIR, `${f}.json`), "utf8"));
    for (const c of Object.keys(cfgs.cfgs)) {
      fs.writeFileSync(expectedPath(f, c), await expectedText(f, c, cfgs, fx));
      console.log(`wrote ${path.relative(ROOT, expectedPath(f, c))}`);
    }
  }
  process.exit(0);
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
