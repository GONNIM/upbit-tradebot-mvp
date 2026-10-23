// 백테스터 스크립트를 vm 컨텍스트에서 돌리는 공용 하네스.
// 원본 HTML+스크립트와 이식본(backtester.html+backtester.js)에 같은 하네스를 쓴다.
import vm from "node:vm";

function attrOf(tag, name) {
  const m = new RegExp("\\s" + name + "=\"([^\"]*)\"").exec(tag);
  return m ? m[1] : null;
}

// HTML 에서 id 별 기본값을 읽는다. <input> 은 value 속성, <select> 는 selected 옵션(없으면 첫 옵션).
export function parseDefaults(htmlText) {
  const out = {};
  const selRe = /<select\b([^>]*)>([\s\S]*?)<\/select>/g;
  let m;
  while ((m = selRe.exec(htmlText))) {
    const id = attrOf("<select" + m[1] + ">", "id");
    if (!id) continue;
    const opts = [...m[2].matchAll(/<option\b([^>]*)>/g)].map((o) => ({
      value: attrOf("<option" + o[1] + ">", "value") ?? "",
      selected: /\sselected(\s|=|$)/.test(o[1] + " "),
      disabled: /\sdisabled(\s|=|$)/.test(o[1] + " "),
    }));
    const sel = opts.find((o) => o.selected) || opts[0];
    const texts = [...m[2].matchAll(/<option\b[^>]*>([\s\S]*?)<\/option>/g)].map((o) => o[1]);
    const idx = opts.indexOf(sel);
    out[id] = {
      tag: "select",
      value: sel ? sel.value : "",
      options: opts.map((o) => o.value),
      selectedText: idx >= 0 ? texts[idx] : "",
    };
  }
  const inRe = /<input\b([^>]*)>/g;
  while ((m = inRe.exec(htmlText))) {
    const tag = "<input" + m[1] + ">";
    const id = attrOf(tag, "id");
    if (!id) continue;
    out[id] = {
      tag: "input",
      value: attrOf(tag, "value") ?? "",
      min: attrOf(tag, "min"),
      max: attrOf(tag, "max"),
      step: attrOf(tag, "step"),
      type: attrOf(tag, "type"),
    };
  }
  return out;
}

function makeEl(value, record, selectedText = "") {
  const el = {
    value,
    selectedOptions: [{ textContent: selectedText, value }],
    innerHTML: "",
    textContent: "",
    style: {},
    href: "",
    download: "",
    addEventListener(name) { record.push(name); },
    getBoundingClientRect() { return { width: 800, height: 400, left: 0, top: 0 }; },
    click() {},
    getContext() {
      const fn = () => proxy;
      const proxy = new Proxy(fn, {
        get: (_t, k) => (k === Symbol.toPrimitive ? () => 0 : proxy),
        set: () => true,
        apply: () => proxy,
      });
      return proxy;
    },
  };
  return el;
}

export async function runInHarness(scriptText, htmlText, fixture) {
  const defaults = parseDefaults(htmlText);
  const listeners = [];
  const els = {};
  const getEl = (id) => {
    if (!els[id]) els[id] = makeEl(defaults[id] ? defaults[id].value : "", listeners, defaults[id]?.selectedText ?? "");
    return els[id];
  };
  getEl("symbol").value = fixture.symbol;
  getEl("src").value = fixture.interval;
  getEl("days").value = String(fixture.days);

  const fetchCalls = [];
  const fakeFetch = async (url) => {
    const i = fetchCalls.length;
    fetchCalls.push(url);
    if (i >= fixture.pages.length) {
      throw new Error(`harness: 고정 입력에 ${i}번째 요청 페이지가 없음 (pages=${fixture.pages.length}), url=${url}`);
    }
    if (fixture.pages[i].url !== url) {
      throw new Error(`harness: ${i}번째 요청 URL 불일치\n  기대 ${fixture.pages[i].url}\n  실제 ${url}`);
    }
    const data = fixture.pages[i].data;
    return { ok: true, status: 200, json: async () => data };
  };

  const RealDate = Date;
  class FixedDate extends RealDate {
    static now() { return fixture.fetched_at_ms; }
  }
  const blobs = [];
  const urls = [];
  const ctx = {
    document: { getElementById: getEl, createElement: () => makeEl("", listeners), addEventListener() {} },
    fetch: fakeFetch,
    Date: FixedDate,
    setTimeout: (fn) => { fn(); return 0; },
    devicePixelRatio: 1,
    Blob: class { constructor(parts, opts) { blobs.push({ parts, opts }); } },
    URL: { createObjectURL: (b) => { urls.push(b); return "blob:harness"; }, revokeObjectURL() {} },
    console,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(scriptText, ctx);
  await ctx.run();
  // runSweep 은 원본 618행 일반(동기) 함수. 비동기여도 await 로 흡수한다.
  await ctx.runSweep();
  const csv = (name) => vm.runInContext(`csv(${name})`, ctx);
  return {
    trades: csv("tradeRows"),
    weekly: csv("weeklyRows"),
    monthly: csv("monthlyRows"),
    sweep: csv("sweepRows"),
    fetchCalls,
    barCount: vm.runInContext("lastBars?lastBars.length:0", ctx),
    chartHint: getEl("chartHint").textContent,
    status: getEl("status").textContent,
  };
}
