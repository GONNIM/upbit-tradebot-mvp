// 백테스터 화면 보조 (그림 2-다). backtester.js(Ver9 원문 + 정해진 차이 10곳 — tests/v2/js/fixtures/ver2_patches.json)는 건드리지 않고
// 이 파일이 출처 토글·업비트 서버 수집·요약 카드·스윕 요약·중복 실행 막기를 맡는다.
// 업비트 시세는 같은 출처의 v2 서버(/v2/api/candles)만 부른다 — 브라우저가 업비트를 직접 부르지 않는다.
(function () {
  "use strict";

  var SRC_UNIT = { "1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "1h": 60 };
  var MAX_WAIT_MS = 600000;   // 서버 수집을 기다리는 전체 상한 10분 (1분봉 90일 ≈ 4.3분 이상, 1105-09)
  var UPBIT_MAX_DAYS = 90;    // 1105-06 결정 ④
  var UPBIT_MARKET_RE = /^KRW-[A-Z0-9]+$/;

  var MSG_ERR = "업비트 데이터를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요";
  var MSG_BLOCK = "업비트가 요청을 막았습니다. 운영자 확인이 필요합니다(바이낸스 데이터는 쓸 수 있습니다)";
  var MSG_AUTH = "구버전에서 다시 들어와 주세요";
  var MSG_SIZE = "요청한 데이터가 너무 큽니다. 기간을 줄이거나 봉 단위를 키워 주세요";

  // 엔진 봉 단위(minute1·3·5·60) -> 화면 봉 단위. 그 밖은 3분.
  function srcFromInterval(iv) {
    var m = { minute1: "1m", minute3: "3m", minute5: "5m", minute10: "10m", minute15: "15m", minute30: "30m", minute60: "1h" };
    return Object.prototype.hasOwnProperty.call(m, iv) ? m[iv] : "3m";
  }

  // 업비트 요청 횟수(200개씩): 1m·30일 = 216, 1m·90일 = 648, 3m·90일 = 216
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
    if (status === 400 && body && body.field === "size") return MSG_SIZE;
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

  var MSG_FUT_UPBIT = "선물은 바이낸스 출처에서만 됩니다";
  var MSG_SRC_BUSY = "실행 중에는 출처를 바꿀 수 없습니다. 끝난 뒤 바꿔 주세요";
  // 실행 · 선물 실행 · 스윕이 도는 동안의 개수. 도는 중에 출처를 바꾸면 끝난 결과가 새 출처 화면에 다시 채워지므로 막는다(1111-01).
  var busyCount = 0;
  var MSG_WAIT_SWEEP = "스윕이 끝난 뒤 실행해 주세요";
  var MSG_WAIT_RUN = "실행이 끝난 뒤 스윕해 주세요";

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
      out.push({ tp: r.tp, sl: r.sl, maxSplits: r.maxSplits, slope: r.ma60MinSlope, drop: r.ma60SlopeDrop, ret: r.returnPct });
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

  // 1111-01: 스윕 줄이 TP·SL·분할만으로는 구분되지 않는다(분할 1 · 기울기 11 · 둔화 5 → 같은 TP·SL 이 55줄) — 60선 기울기·둔화 허용치 칸을 더한다
  function sweepHtml(rows) {
    if (!rows || !rows.length) return '<div class="empty">스윕을 실행하면 상위 5개가 여기에 보입니다</div>';
    var h = '<table class="mt"><tr><th>TP</th><th>SL</th><th>분할</th><th>60선 기울기</th><th>둔화 허용치</th><th class="r">수익률</th></tr>';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var v = Number(r.ret);
      h += "<tr><td>" + num(r.tp) + "</td><td>" + num(r.sl) + "</td><td>" + esc(r.maxSplits) +
        "</td><td>" + (r.slope == null ? "—" : num(r.slope)) + "</td><td>" + (r.drop == null ? "—" : num(r.drop)) +
        '</td><td class="r ' + (v > 0 ? "up" : (v < 0 ? "dn" : "")) + '">' + pct(v, true) + "</td></tr>";
    }
    return h + "</table>";
  }

  // 카드 위 한 줄: 무엇으로 계산한 결과인지(현물 · 선물, 출처)
  function modeLabel(mode, source, cfg) {
    if (mode === "futures") {
      return "선물(롱+숏) · 바이낸스 USDT 선물 시세 · 방식 " + esc((cfg && cfg.futMode) || "A") + " · 화면 계산만";
    }
    return "현물 · " + (source === "upbit" ? "업비트(KRW)" : "바이낸스");
  }

  // 1125-01 B2: 스윕 결과 안의 긴 설명 문단(p.small)을 접기 상자(details)로 감싼다. backtester.js 는 그대로 두고 여기서만 한다.
  // querySelectorAll 이 없는 요소(시험용 가짜)에서는 아무 일도 하지 않는다. 이미 감싼 문단은 다시 감싸지 않는다. 감싼 수를 돌려준다.
  function foldSweepNotes(box) {
    if (!box || typeof box.querySelectorAll !== "function") return 0;
    var n = 0;
    var list = Array.prototype.slice.call(box.querySelectorAll("p.small"));
    for (var i = 0; i < list.length; i++) {
      var p = list[i];
      var par = p.parentNode;
      if (par && par.classList && typeof par.classList.contains === "function" && par.classList.contains("sweep-fold")) continue;
      if (typeof p.closest === "function" && p.closest(".sweep-fold")) continue;
      if (typeof p.outerHTML !== "string") continue;
      p.outerHTML = '<details class="bt-more sweep-fold"><summary>설명 펼치기 / 접기</summary>' + p.outerHTML + "</details>";
      n++;
    }
    return n;
  }

  // ---- window 의 fetchKlines·run·runSweep 감싸기 ----
  // o: { win, getEl(id), getState() -> {lastResults,lastCfgBase,sweepRows}, statsFn(res,cfg), fetchFn, sleepFn, nowFn }
  function install(o) {
    var win = o.win;
    var el = o.getEl;
    var origFetchKlines = win.fetchKlines;
    var origRun = win.run;
    var origSweep = win.runSweep;
    var origFutures = win.runFutures;
    var running = false;

    win.fetchKlines = async function (symbol, interval, days, market) {
      // 선물(1111-01): 업비트 현물 봉이 선물 계산에 들어가지 않게 막는다. 바이낸스면 원래 함수에 그대로 넘긴다.
      if (market === "futures") {
        if (el("dataSource").value === "upbit") throw new Error(MSG_FUT_UPBIT);
        return origFetchKlines.apply(win, arguments);
      }
      if (el("dataSource").value !== "upbit") return origFetchKlines.apply(win, arguments);
      var market = String(symbol || "").trim().toUpperCase();
      if (!UPBIT_MARKET_RE.test(market)) throw new Error("업비트 종목은 KRW-XXX 형식입니다");
      if (!(Number.isInteger(days) && days >= 1 && days <= UPBIT_MAX_DAYS)) throw new Error("업비트 데이터는 최대 " + UPBIT_MAX_DAYS + "일까지 받을 수 있습니다");
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
      if (busyCount > 0) { el("status").textContent = MSG_WAIT_SWEEP; return; }   // 스윕이 도는 중이면 결과가 섞이므로 막는다(1111-01)
      running = true;
      var runBtn = el("btRunBtn");
      runBtn.disabled = true;
      var before = o.getState().lastResults;
      busyCount++;
      try {
        await origRun.apply(win, arguments);
      } finally {
        running = false;
        busyCount--;
        runBtn.disabled = false;
      }
      // 기준 원문(Ver9)은 출처와 상관없이 「바이낸스에서 새로 조회함」을 붙인다 — 업비트면 바로잡는다.
      // 업비트는 서버 저장분에 새 봉만 이어 받으므로 「전부 새로 받음」으로 읽히지 않게 쓴다(1106-01 ㉠).
      if (el("dataSource").value === "upbit") {
        var stEl = el("status");
        stEl.textContent = String(stEl.textContent || "").replace("[바이낸스에서 새로 조회함]", "[업비트: 서버 저장분 + 새 봉 이어 받음]");
      }
      refreshBrief(before);
    };

    // 요약 카드(현물 · 선물 공통): 새 결과가 있으면 3줄 카드, 없으면 「결과 없음」
    function refreshBrief(before) {
      var st = o.getState();
      var mode = st.lastMode === "futures" ? "futures" : "spot";
      if (st.lastResults && st.lastResults !== before) {
        el("btBrief").innerHTML = briefHtml(briefSummary(o.statsFn(st.lastResults, st.lastCfgBase)));
        el("btBriefMode").textContent = modeLabel(mode, el("dataSource").value, st.lastCfgBase);
      } else {
        el("btBrief").innerHTML = briefHtml(null);
        el("btBriefMode").textContent = "";
      }
    }

    // 선물 백테스트(1111-01): 업비트 출처면 바깥 요청 없이 막고, run 과 같은 겹침 막기, await 로 끝난 뒤 카드를 갱신한다.
    if (typeof origFutures === "function") {
      win.runFutures = async function () {
        if (running) return;
        if (busyCount > 0) { el("status").textContent = MSG_WAIT_SWEEP; return; }
        if (el("dataSource").value === "upbit") {
          el("status").textContent = "오류: " + MSG_FUT_UPBIT;
          return;
        }
        running = true;
        var runBtn = el("btRunBtn");
        var futBtn = el("btFutBtn");
        runBtn.disabled = true;
        futBtn.disabled = true;
        var before = o.getState().lastResults;
        busyCount++;
        try {
          await origFutures.apply(win, arguments);
        } finally {
          running = false;
          busyCount--;
          runBtn.disabled = false;
          futBtn.disabled = el("dataSource").value === "upbit";
        }
        refreshBrief(before);
      };
    }

    // 스윕은 비동기다. 끝나기 전에 sweepRows 를 읽으면 늘 빈 목록이므로 await 한 뒤 카드를 그린다(1111-01).
    win.runSweep = async function () {
      if (running) { el("sweepStatus").textContent = MSG_WAIT_RUN; return; }   // 실행 · 선물 실행 중에는 스윕을 시작하지 않는다(1111-01)
      busyCount++;
      try {
        return await origSweep.apply(win, arguments);
      } finally {
        busyCount--;
        var st = o.getState();
        el("sweepBrief").innerHTML = sweepHtml(sweepBrief(st.sweepRows));
        el("sweepBriefMode").textContent = st.sweepRows && st.sweepRows.length
          ? modeLabel(st.lastMode === "futures" ? "futures" : "spot", el("dataSource").value, st.lastCfgBase) : "";
        try { foldSweepNotes(el("sweepResult")); } catch (e) { /* 접기 실패는 스윕 결과에 영향 없음 */ }
      }
    };
  }

  // ---- 브라우저 연결 ----
  function clearDataCache() {
    try { if (typeof dataCache !== "undefined") dataCache = null; } catch (e) { /* 캐시가 없으면 할 일 없음 */ }
    try { if (typeof futCache !== "undefined") futCache = null; } catch (e) { /* 선물 캐시(Ver9)도 출처를 키에 넣지 않는다 */ }
  }
  // 직전 결과 변수(Ver9 스크립트의 let)를 처음 상태로 돌린다. 저장 창은 「창을 열 때 고른 출처」를 쓰므로,
  // 바이낸스 선물 결과가 남은 채 업비트로 바꿔 저장하는 틈을 막는다(1111-01). 각 줄은 따로 감싸 하나가 실패해도 나머지를 비운다.
  function clearResultVars() {
    try { lastBars = null; lastMaTrend = null; lastMa200 = null; lastSlope60 = null; lastMaPullback = null; lastCfgBase = null; lastResults = null; } catch (e) { /* 변수 없음 */ }
    try { tradeRows = []; weeklyRows = []; monthlyRows = []; } catch (e) { /* 변수 없음 */ }
    try { sweepRows = []; sweepSlopeRows = []; sweepDropRows = []; sweepMonthRows = []; sweepWeekRows = []; } catch (e) { /* 변수 없음 */ }
    try { lastMode = "spot"; lastFundings = []; } catch (e) { /* 변수 없음 */ }
    try { chartState = null; chartViewStart = null; } catch (e) { /* 변수 없음 */ }
  }
  var dummy = {};
  function byId(id) { return document.getElementById(id) || dummy; }

  function setSegment(source) {
    byId("dataSource").value = source;
    byId("btSrcUpbit").className = "seg-b" + (source === "upbit" ? " on" : "");
    byId("btSrcBinance").className = "seg-b" + (source === "binance" ? " on" : "");
  }

  function mountPage() {
    // 처음 상태 문구(출처를 바꿀 때 화면을 이 상태로 돌린다)
    var initial = {
      status: byId("status").textContent, sweepHint: byId("sweepHint").textContent, chartHint: byId("chartHint").textContent,
      chartInfo: byId("chartInfo").textContent,
    };
    function clearCanvas(id) {
      var cv = byId(id);
      try { var g = cv.getContext && cv.getContext("2d"); if (g) g.clearRect(0, 0, cv.width, cv.height); } catch (e) { /* 캔버스 없음 */ }
    }
    // 화면에 보이는 결과를 처음 상태로: 카드 · 자세한 결과 · 스윕 · 차트
    function resetView() {
      clearResultVars();
      byId("btBrief").innerHTML = briefHtml(null);
      byId("btBriefMode").textContent = "";
      byId("sweepBrief").innerHTML = sweepHtml([]);
      byId("sweepBriefMode").textContent = "";
      ["summary", "depth", "weekly", "monthly", "sweepResult", "chartLegend"].forEach(function (id) { byId(id).innerHTML = ""; });
      byId("sweepStatus").textContent = "";
      byId("status").textContent = initial.status;
      byId("sweepHint").textContent = initial.sweepHint;
      byId("chartHint").textContent = initial.chartHint;
      byId("chartInfo").textContent = initial.chartInfo;
      clearCanvas("chartCanvas");
      clearCanvas("chartOverlay");
    }
    // 선물 단추: 업비트 출처면 막고 안내, 바이낸스면 푼다
    function syncFutButton(source) {
      byId("btFutBtn").disabled = source === "upbit";
      byId("btFutNote").hidden = source !== "upbit";
    }
    var binanceSymbol = byId("symbol").value || "JTOUSDT";     // 정적 기본값(바이낸스 종목)
    var upbitSymbol = "KRW-" + binanceSymbol.replace(/USDT$/, "");
    var engineTicker = null;

    function choose(source) {
      // 기준 원문(Ver9) 캐시(dataCache)는 출처를 키에 넣지 않는다 — 출처를 바꾸면 비워 섞이지 않게 한다.
      if (byId("dataSource").value !== source && busyCount > 0) { byId("status").textContent = MSG_SRC_BUSY; return; }
      if (byId("dataSource").value !== source) { clearDataCache(); resetView(); }
      setSegment(source);
      syncFutButton(source);
      byId("symbol").value = source === "upbit" ? (engineTicker || upbitSymbol) : binanceSymbol;
    }
    var touched = false;   // 1121-03 A1: 시작값을 기다리는 사이 사용자가 칸·출처를 고쳤는지
    byId("btSrcUpbit").addEventListener("click", function () { touched = true; choose("upbit"); });
    byId("btSrcBinance").addEventListener("click", function () { touched = true; choose("binance"); });
    choose("upbit");

    install({
      win: window,
      getEl: byId,
      getState: function () { return { lastResults: lastResults, lastCfgBase: lastCfgBase, sweepRows: sweepRows, lastMode: lastMode }; },
      statsFn: function (res, cfg) { return stats(res, cfg); },
    });
    byId("btBrief").innerHTML = briefHtml(null);
    byId("sweepBrief").innerHTML = sweepHtml([]);

    // 1121-03 A1: 기다리는 사이 사용자가 칸을 고쳤으면 저장값으로 덮어쓰지 않는다
    try {
      document.addEventListener("input", function () { touched = true; }, true);
      document.addEventListener("change", function () { touched = true; }, true);
    } catch (e) { /* 이벤트를 못 달면 고침 표시 없이 진행 */ }

    function getJson(url) {
      return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; });
    }
    function inTime(p) {
      return Promise.race([p, new Promise(function (res) { setTimeout(function () { res(null); }, START_WAIT_MS); })]);
    }

    // 엔진 상태(머리 막대 모드·엔진 종목·봉 단위)와 마지막 저장값(1121-03 A1)을 함께 기다린 뒤 채운다.
    // 머리 막대 모드는 5초 상한과 상관없이 상태 응답이 오면 채운다(예전 동작). 종목·봉 단위 자동 채움만 5초 규칙.
    var statusP = getJson("/v2/api/status");
    statusP.then(setMode, function () { /* 상태를 못 읽으면 모드 칸은 비워 둔다 */ });
    Promise.allSettled([inTime(statusP), inTime(getJson("/v2/api/params/last-saved"))]).then(function (got) {
      var st = got[0].status === "fulfilled" ? got[0].value : null;
      var ls = got[1].status === "fulfilled" ? got[1].value : null;
      applyStart(st, ls);
    });

    function setMode(st) {
      if (!st) return;
      var m = String(st.mode_engine || "").toUpperCase();
      byId("btMode").textContent = m === "LIVE" || m === "TEST" ? m : "";
    }
    function applyStart(st, ls) {
      if (st) {
        if (st.ticker && UPBIT_MARKET_RE.test(String(st.ticker))) engineTicker = String(st.ticker);
      }
      var saved = startValues(ls);
      if (saved && (touched || busyCount > 0)) {
        byId("btLoaded").textContent = MSG_LOAD_SKIP;
        return;
      }
      if (saved) {
        // 이력으로 채움: 출처 단추 → 화면 값 25칸 → 추적 손절 3칸. 엔진 상태로는 engineTicker 만 정한다(위)
        choose(saved.source);
        Object.keys(saved.params).forEach(function (k) {
          var e = byId(k);
          if (e !== dummy) e.value = String(saved.params[k]);
        });
        var ts = saved.trailing || {};
        byId("trailingStop").value = ts.ts_on === true ? "yes" : "no";
        if (ts.ts_on === true) {
          byId("trailingMode").value = ts.ts_mode === "fixed" ? "fixed" : "ratio";
          byId("trailingPct").value = String(ts.ts_pct);
        }
        byId("btLoaded").textContent = loadedText(ls);
        return;
      }
      // 이력 없음·깨짐·실패·시간 초과: 지금까지와 같게 엔진 종목(기본값일 때만)·봉 단위로 채운다
      byId("btLoaded").textContent = "기본 설정";
      if (!st || touched) return;
      var sym = byId("symbol");
      if (engineTicker && byId("dataSource").value === "upbit" && sym.value === upbitSymbol) sym.value = engineTicker;
      byId("src").value = srcFromInterval(st.interval);
    }
  }

  var START_WAIT_MS = 5000;   // 1121-03 A1: 시작 때 상태·저장값을 기다리는 상한
  var MSG_LOAD_SKIP = "저장값 불러오기 건너뜀 — 그사이 칸을 고쳤거나 실행 중입니다";

  // GET /v2/api/params/last-saved 응답 → {source, params, trailing} 또는 null(이력 없음·깨짐·모양이 다름)
  function startValues(ls) {
    if (!ls || ls.exists !== true || ls.broken === true) return null;
    if (ls.source !== "upbit" && ls.source !== "binance") return null;
    if (!ls.params || typeof ls.params !== "object") return null;
    return { source: ls.source, params: ls.params, trailing: ls.trailing || null };
  }
  // 화면 위 한 줄: 「불러온 설정: 마지막 저장 25.11.24 05:08」 + 다르면 「(지금 운용 값과 다름 — 저장만 하고 적용하지 않음)」
  function loadedText(ls) {
    return "불러온 설정: 마지막 저장 " + (ls.saved_at_text || "—") +
      (ls.differs_from_applied === true ? " (지금 운용 값과 다름 — 저장만 하고 적용하지 않음)" : "");
  }

  var api = {
    upbitCallCount: upbitCallCount, fetchUpbitKlines: fetchUpbitKlines, briefSummary: briefSummary,
    sweepBrief: sweepBrief, briefHtml: briefHtml, sweepHtml: sweepHtml, srcFromInterval: srcFromInterval,
    startValues: startValues, loadedText: loadedText,
    install: install, foldSweepNotes: foldSweepNotes,
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
