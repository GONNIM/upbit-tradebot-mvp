// 백테스터 화면 보조 (그림 2-다). backtester.js(원본 계산, 바이트 동일)는 건드리지 않고
// 이 파일이 출처 토글·업비트 서버 수집·요약 카드·스윕 요약·중복 실행 막기를 맡는다.
// 업비트 시세는 같은 출처의 v2 서버(/v2/api/candles)만 부른다 — 브라우저가 업비트를 직접 부르지 않는다.
(function () {
  "use strict";

  var SRC_UNIT = { "1m": 1, "3m": 3, "5m": 5, "1h": 60 };
  var MAX_WAIT_MS = 300000;   // 서버 수집을 기다리는 전체 상한 5분
  var UPBIT_MARKET_RE = /^KRW-[A-Z0-9]+$/;

  var MSG_ERR = "업비트 데이터를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요";
  var MSG_BLOCK = "업비트가 요청을 막았습니다. 운영자 확인이 필요합니다(바이낸스 데이터는 쓸 수 있습니다)";
  var MSG_AUTH = "구버전에서 다시 들어와 주세요";

  // 엔진 봉 단위(minute1·3·5·60) -> 화면 봉 단위. 그 밖은 3분.
  function srcFromInterval(iv) {
    var m = { minute1: "1m", minute3: "3m", minute5: "5m", minute60: "1h" };
    return Object.prototype.hasOwnProperty.call(m, iv) ? m[iv] : "3m";
  }

  // 업비트 요청 횟수(200개씩): 1m·30일 = 216
  function upbitCallCount(src, days) {
    var unit = SRC_UNIT[src] || 3;
    return Math.ceil(days * 1440 / unit / 200);
  }

  function limitMsg(retryAfter) {
    var n = Number(retryAfter);
    return "업비트 요청 한도 — 약 " + (isFinite(n) && n > 0 ? Math.ceil(n) : 60) + "초 뒤 다시 시도해 주세요";
  }
  function busyMsg(p) {
    var d = p && isFinite(Number(p.done)) ? Number(p.done) : 0;
    var t = p && isFinite(Number(p.total)) ? Number(p.total) : 0;
    return "다른 업비트 데이터 수집이 진행 중입니다 (" + d + " / " + t + "회). 끝난 뒤 다시 눌러 주세요";
  }
  // progress.error 코드 -> 문구
  function errorCodeMsg(code, retryAfter) {
    if (code === "upbit_limit") return limitMsg(retryAfter);
    if (code === "upbit_blocked") return MSG_BLOCK;
    return MSG_ERR;
  }
  // HTTP 상태 + 본문 -> 문구
  function statusMsg(status, body) {
    if (status === 401 || status === 403) return MSG_AUTH;
    if (status === 409) return busyMsg(body && body.progress);
    if (status === 429) return limitMsg(body && body.retry_after);
    if (status === 503 && body && body.error === "upbit_blocked") return MSG_BLOCK;
    return MSG_ERR;
  }

  async function readJson(r) {
    try { return await r.json(); } catch (e) { return {}; }
  }

  function toBars(bars) {
    var out = [];
    for (var i = 0; i < bars.length; i++) {
      var x = bars[i];
      out.push({ t: +x[0], o: +x[1], h: +x[2], l: +x[3], c: +x[4] });
    }
    return out;
  }

  // 서버가 보관한 업비트 봉을 받는다. 200 이면 바로, 202 면 진행을 읽다가 끝나면 같은 GET 을 다시 부른다.
  async function fetchUpbitKlines(market, src, days, opts) {
    opts = opts || {};
    var fetchFn = opts.fetchFn || function (u, o) { return fetch(u, o); };
    var sleepFn = opts.sleepFn || function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var nowFn = opts.nowFn || function () { return Date.now(); };
    var pollMs = opts.pollMs == null ? 2000 : opts.pollMs;
    var unit = SRC_UNIT[src];
    var url = "/v2/api/candles?market=" + encodeURIComponent(market) + "&unit=" + unit + "&days=" + days;
    var deadline = nowFn() + MAX_WAIT_MS;

    async function get(u) {
      try {
        return await fetchFn(u, { credentials: "same-origin" });
      } catch (e) {
        throw new Error(MSG_ERR);
      }
    }

    // 202 뒤: 내 사용자 작업이 끝났다고 보일 때까지 progress 를 읽는다. 오류면 문구로 멈춘다.
    async function waitJob() {
      for (;;) {
        if (nowFn() >= deadline) throw new Error(MSG_ERR);
        await sleepFn(pollMs);
        var r = await get("/v2/api/candles/progress");
        if (r.status !== 200) throw new Error(statusMsg(r.status, await readJson(r)));
        var p = await readJson(r);
        var mine = p.kind === "user" && p.market === market && Number(p.unit) === unit;
        if (!mine && p.active) return;          // 미리 받기·다른 종목 작업이 보임: 내 작업은 끝났다고 보고 다시 GET
        if (mine) {
          if (p.error) throw new Error(errorCodeMsg(p.error, p.retry_after));
          if (opts.onProgress) opts.onProgress(p.done, p.total);
          if (!p.active) return;
        } else if (p.error && p.market === market && Number(p.unit) === unit) {
          throw new Error(errorCodeMsg(p.error, p.retry_after));
        } else {
          return;                                // 작업 없음
        }
      }
    }

    for (;;) {
      if (nowFn() >= deadline) throw new Error(MSG_ERR);
      var r = await get(url);
      if (r.status === 200) {
        var body = await readJson(r);
        return toBars(Array.isArray(body.bars) ? body.bars : []);
      }
      if (r.status === 202) {
        await waitJob();
        continue;
      }
      throw new Error(statusMsg(r.status, await readJson(r)));
    }
  }

  // ---- 요약 ----
  function pct(n, signed) {
    var v = Number(n);
    if (!isFinite(v)) return "—";
    var s = Math.abs(v).toFixed(1);
    if (v > 0 && s !== "0.0") return (signed ? "+" : "") + s + "%";
    if (v < 0 && s !== "0.0") return "-" + s + "%";
    return "0.0%";
  }

  // stats() 결과 -> 카드 3줄
  function briefSummary(s) {
    var ret = Number(s.ret);
    var retCls = ret > 0 ? "up" : (ret < 0 ? "dn" : "");
    var wr = isFinite(Number(s.winRate)) ? Math.round(Number(s.winRate)) : 0;
    var mdd = Number(s.mdd);
    var mddText = isFinite(mdd) && mdd > 0 && Math.abs(mdd).toFixed(1) !== "0.0" ? "-" + mdd.toFixed(1) + "%" : "0.0%";
    return [
      { label: "총 수익률", value: pct(ret, true), cls: retCls },
      { label: "거래 수 / 승률", value: (Number(s.trades) || 0) + "회 / " + wr + "%", cls: "" },
      { label: "최대 낙폭", value: mddText, cls: mddText === "0.0%" ? "" : "dn" },
    ];
  }

  // 스윕 결과(이미 정렬됨) 상위 n
  function sweepBrief(rows, n) {
    var k = n == null ? 5 : n;
    var out = [];
    for (var i = 0; i < rows.length && i < k; i++) {
      var r = rows[i];
      out.push({ tp: r.tp, sl: r.sl, maxSplits: r.maxSplits, ret: r.returnPct });
    }
    return out;
  }

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function num(n) { return String(+Number(n).toFixed(2)); }

  function briefHtml(rows) {
    if (!rows) return '<div class="empty">결과 없음</div>';
    var h = "";
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      h += '<div class="kv"><span>' + esc(r.label) + '</span><span' + (r.cls ? ' class="' + r.cls + '"' : "") + ">" + esc(r.value) + "</span></div>";
    }
    return h;
  }

  function sweepHtml(rows) {
    if (!rows || !rows.length) return '<div class="empty">스윕을 실행하면 상위 5개가 여기에 보입니다</div>';
    var h = '<table class="mt"><tr><th>TP</th><th>SL</th><th>분할</th><th class="r">수익률</th></tr>';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var v = Number(r.ret);
      h += "<tr><td>" + num(r.tp) + "</td><td>" + num(r.sl) + "</td><td>" + esc(r.maxSplits) +
        '</td><td class="r ' + (v > 0 ? "up" : (v < 0 ? "dn" : "")) + '">' + pct(v, true) + "</td></tr>";
    }
    return h + "</table>";
  }

  // ---- window 의 fetchKlines·run·runSweep 감싸기 ----
  // o: { win, getEl(id), getState() -> {lastResults,lastCfgBase,sweepRows}, statsFn(res,cfg), fetchFn, sleepFn, nowFn }
  function install(o) {
    var win = o.win;
    var el = o.getEl;
    var origFetchKlines = win.fetchKlines;
    var origRun = win.run;
    var origSweep = win.runSweep;
    var running = false;

    win.fetchKlines = async function (symbol, interval, days) {
      if (el("dataSource").value !== "upbit") return origFetchKlines.apply(win, arguments);
      var market = String(symbol || "").trim().toUpperCase();
      if (!UPBIT_MARKET_RE.test(market)) throw new Error("업비트 종목은 KRW-XXX 형식입니다");
      if (!(Number.isInteger(days) && days >= 1 && days <= 30)) throw new Error("업비트 데이터는 최대 30일까지 받을 수 있습니다");
      var note = el("btNote");
      el("status").textContent = "업비트 데이터 확인 중…";
      try {
        var bars = await fetchUpbitKlines(market, interval, days, {
          fetchFn: o.fetchFn, sleepFn: o.sleepFn, nowFn: o.nowFn,
          onProgress: function (done, total) {
            var t = total > 0 ? total : upbitCallCount(interval, days);
            el("status").textContent = "업비트 데이터 받는 중… " + done + " / " + t + "회";
            note.hidden = false;
          },
        });
        el("status").textContent = "계산 중…";
        return bars;
      } finally {
        note.hidden = true;
      }
    };

    win.run = async function () {
      if (running) return;
      running = true;
      var runBtn = el("btRunBtn");
      runBtn.disabled = true;
      var before = o.getState().lastResults;
      try {
        await origRun.apply(win, arguments);
      } finally {
        running = false;
        runBtn.disabled = false;
      }
      var st = o.getState();
      if (st.lastResults && st.lastResults !== before) {
        el("btBrief").innerHTML = briefHtml(briefSummary(o.statsFn(st.lastResults, st.lastCfgBase)));
      } else {
        el("btBrief").innerHTML = briefHtml(null);
      }
    };

    win.runSweep = function () {
      var r = origSweep.apply(win, arguments);
      el("sweepBrief").innerHTML = sweepHtml(sweepBrief(o.getState().sweepRows));
      return r;
    };
  }

  // ---- 브라우저 연결 ----
  var dummy = {};
  function byId(id) { return document.getElementById(id) || dummy; }

  function setSegment(source) {
    byId("dataSource").value = source;
    byId("btSrcUpbit").className = "seg-b" + (source === "upbit" ? " on" : "");
    byId("btSrcBinance").className = "seg-b" + (source === "binance" ? " on" : "");
  }

  function mountPage() {
    var binanceSymbol = byId("symbol").value || "JTOUSDT";     // 정적 기본값(바이낸스 종목)
    var upbitSymbol = "KRW-" + binanceSymbol.replace(/USDT$/, "");
    var engineTicker = null;

    function choose(source) {
      setSegment(source);
      byId("symbol").value = source === "upbit" ? (engineTicker || upbitSymbol) : binanceSymbol;
    }
    byId("btSrcUpbit").addEventListener("click", function () { choose("upbit"); });
    byId("btSrcBinance").addEventListener("click", function () { choose("binance"); });
    choose("upbit");

    install({
      win: window,
      getEl: byId,
      getState: function () { return { lastResults: lastResults, lastCfgBase: lastCfgBase, sweepRows: sweepRows }; },
      statsFn: function (res, cfg) { return stats(res, cfg); },
    });
    byId("btBrief").innerHTML = briefHtml(null);
    byId("sweepBrief").innerHTML = sweepHtml([]);

    // 엔진 상태: 머리 막대 모드, 엔진 종목·봉 단위 기본값
    fetch("/v2/api/status", { credentials: "same-origin" }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (st) {
      if (!st) return;
      var m = String(st.mode_engine || "").toUpperCase();
      byId("btMode").textContent = m === "LIVE" || m === "TEST" ? m : "";
      var sym = byId("symbol");
      if (st.ticker && UPBIT_MARKET_RE.test(String(st.ticker))) {
        engineTicker = String(st.ticker);
        if (byId("dataSource").value === "upbit" && sym.value === upbitSymbol) sym.value = engineTicker;
      }
      byId("src").value = srcFromInterval(st.interval);
    }).catch(function () { /* 상태를 못 읽어도 기본값으로 쓴다 */ });
  }

  var api = {
    upbitCallCount: upbitCallCount, fetchUpbitKlines: fetchUpbitKlines, briefSummary: briefSummary,
    sweepBrief: sweepBrief, briefHtml: briefHtml, sweepHtml: sweepHtml, srcFromInterval: srcFromInterval,
    install: install,
  };
  globalThis.__v2bt = api;

  if (typeof document !== "undefined" && document && typeof window !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", mountPage);
    } else {
      mountPage();
    }
  }
})();
