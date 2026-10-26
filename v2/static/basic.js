// 기본 기능 블록 (구버전 pages/dashboard.py 의 기본 항목을 신버전에서 그대로 제공).
// 모바일 홈 맨 위(index.html)와 PC 백테스터 위(backtester.html)에 같은 블록을 둔다.
// 읽기: GET /v2/api/status·assets·basic. 쓰기: POST /v2/api/pause·logout (서버가 세션·Origin 확인).
// 업비트는 부르지 않는다. 원본 백테스터 스크립트(backtester.js)·입력 칸은 건드리지 않는다.
(function () {
  "use strict";

  var GUIDE_TEXT = "구버전에서 다시 들어와 주세요";
  var INFO_TEXT = "Upbit Trade Bot v1 상태 모니터링 페이지입니다.";
  var NET_TEXT = "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다.";
  var BUSY_TEXT = "잠시 뒤 다시 시도해 주세요";
  var FAIL_TEXT = "처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
  var PAUSED_BANNER = "⏸️ 매매 일시중지 상태 — 엔진과 지표는 정상 작동하지만 실주문(BUY/SELL)은 " +
    "실행되지 않습니다. 재개하려면 아래 '▶️ 매매 재개' 버튼을 클릭하세요.";
  var REFRESH_MS = 7000;

  function pad(n) { return String(n).padStart(2, "0"); }

  // 브라우저 시계를 Asia/Seoul(UTC+9) 로 표기: YYYY-MM-DD HH:MM:SS
  function kstClock(ms) {
    var d = new Date(ms + 9 * 3600 * 1000);
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + " " +
      pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + ":" + pad(d.getUTCSeconds());
  }

  function fmtFixed(v, digits) {
    var n = Number(v);
    if (!isFinite(n)) n = 0;
    return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  // 수익률 표기: 구버전 f"{x:+.2f}%" / delta 문구와 같게
  function pctValue(p) { return (p < 0 ? "" : "+") + p.toFixed(2) + "%"; }
  function pctDelta(p, tag) {
    if (p > 0) return "+" + p.toFixed(2) + "% (" + tag + ")";
    if (p < 0) return p.toFixed(2) + "% (" + tag + ")";
    return "보합 (" + tag + ")";
  }

  function modeNotice(mode) {
    var m = String(mode || "").toUpperCase();
    if (m === "TEST") {
      return { kind: "warn", lead: "🧪 TEST 모드",
        rest: " — 모든 매매는 시뮬레이션입니다. 실제 거래소 주문은 발생하지 않습니다. " +
          "audit_trades/orders에 기록되는 BUY/SELL은 가상 거래 결과입니다." };
    }
    if (m === "LIVE") {
      return { kind: "info", lead: "🔴 LIVE 모드", rest: " — 실제 Upbit 거래소에 주문이 전송됩니다." };
    }
    return null;
  }

  function mismatchText(status) {
    return "경고: 입장 모드(" + (status.mode_entry || "?") + ")와 엔진 모드(" +
      (status.mode_engine || "?") + ")가 다릅니다.";
  }

  function confirmText(pausing, mode) {
    if (!pausing) return "매매를 재개합니다.";
    return "매매를 중지합니다(모드: " + (mode || "확인 불가") + "). " +
      "중지 중에는 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. " +
      "이미 걸려 있는 주문은 취소되지 않고, 미체결 지정가 매수가 시장가로 바뀌는 처리는 계속될 수 있습니다.";
  }

  // 💹 칸. 구버전: 가용 수량 > 0 이면 현재 포지션(미실현), 아니면 최근 거래(실현)
  function pnlCell(basic) {
    var unreal = basic.pnl_kind === "unrealized";
    var label = unreal ? "💹 현재 포지션" : "💹 최근 거래";
    var tag = unreal ? "미실현" : "실현";
    var p = basic.pnl_pct;
    if (p === null || p === undefined || !isFinite(Number(p))) {
      return { label: label, value: "N/A", delta: unreal ? "정보 없음" : "거래 없음" };
    }
    p = Number(p);
    return { label: label, value: pctValue(p), delta: pctDelta(p, tag) };
  }

  function assetCells(status, assets, basic) {
    var krw = Number(assets.krw) || 0, krwLock = Number(assets.krw_locked) || 0;
    var qty = Number(assets.coin) || 0, lockQty = Number(assets.coin_locked) || 0;
    var price = assets.price == null ? null : Number(assets.price);
    var coinVal = price != null && isFinite(price) ? qty * price : 0;
    var coinDelta = lockQty > 0
      ? "🔒 Lock: " + fmtFixed(lockQty, 6) + " · 평가 " + fmtFixed(coinVal, 0) + " KRW"
      : "평가 " + fmtFixed(coinVal, 0) + " KRW";
    var caption = (qty <= 0 && lockQty > 0)
      ? "⛔ 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 (" + fmtFixed(lockQty, 6) +
        "개). 평가액은 가용 수량 기준이라 0원으로 보입니다."
      : "";
    return {
      krw: { label: "보유 KRW", value: fmtFixed(krw, 0) + " KRW",
        delta: krwLock > 0 ? "🔒 Lock: " + fmtFixed(krwLock, 0) + " KRW" : "" },
      coin: { label: (status.ticker || "—") + " 보유량", value: fmtFixed(qty, 6), delta: coinDelta, caption: caption },
      pnl: pnlCell(basic),
    };
  }

  // 화면에 그릴 값 전부(문자열). DOM 을 만지지 않는 순수 함수라 node 시험에서 검사한다.
  function buildView(s, nowMs) {
    var view = { clock: "🕒 현재 시각: " + kstClock(nowMs), info: INFO_TEXT };
    if (s.auth) {
      view.auth = GUIDE_TEXT;
      return view;
    }
    var st = s.status, as = s.assets, bs = s.basic;
    view.error = s.err || "";
    if (!st) {
      view.loading = true;
      return view;
    }
    var mode = st.mode_engine || "확인 불가";
    view.title = "📊 Dashboard (" + mode + ") : " + ((bs && bs.account) || "") + "님 --- " +
      ((bs && bs.version) || "버전 확인 불가");
    view.notice = modeNotice(st.mode_engine);
    view.mismatch = st.mode_mismatch ? mismatchText(st) : "";
    view.pausedBanner = st.paused ? PAUSED_BANNER : "";
    view.log = bs ? bs.last_status_log : "";
    var running = !!(bs && bs.engine_running);
    view.engine = { label: "트레이딩 엔진 상태", value: running ? "Running 🟢" : "Stopped 🔴", running: running };
    view.pauseBtn = { label: st.paused ? "▶️ 매매 재개" : "⏸️ 매매 중지", disabled: !!s.busy };
    view.pauseMsg = s.pauseMsg || "";
    view.assets = (as && bs) ? assetCells(st, as, bs) : null;
    return view;
  }

  // 상태 보관·읽기·쓰기. deps: fetchFn, confirmFn, nowFn, isHidden, isVisible, render, navigate
  function createController(deps) {
    var s = { status: null, assets: null, basic: null, auth: false, err: "", busy: false, pauseMsg: "" };
    var inflight = null;      // 진행 중인 읽기(Promise)
    var again = false;        // 진행 중에 강제 읽기가 들어오면 끝난 뒤 한 번 더 읽는다
    var lastRefresh = -Infinity;
    var lastVisible = false;

    function draw() { deps.render(buildView(s, deps.nowFn())); }

    function getJson(path) {
      return deps.fetchFn(path, { credentials: "same-origin", cache: "no-store" }).then(function (r) {
        if (r.status === 401 || r.status === 403) { var e = new Error("auth"); e.auth = true; throw e; }
        if (!r.ok) throw new Error("http " + r.status);
        return r.json();
      });
    }

    function active() { return !deps.isHidden() && deps.isVisible(); }

    function refresh(force) {
      if (inflight) {
        if (!force) return Promise.resolve();
        // 매매 중지/재개 응답 뒤의 강제 읽기는 버리지 않는다 — 진행 중인 읽기가 끝나면 다시 읽는다
        again = true;
        return inflight;
      }
      if (!force && !active()) return Promise.resolve();
      lastRefresh = deps.nowFn();
      var jobs = [["/v2/api/status", "status"], ["/v2/api/assets", "assets"], ["/v2/api/basic", "basic"]];
      var failed = 0, auth = false;
      inflight = Promise.all(jobs.map(function (j) {
        return getJson(j[0]).then(function (d) { s[j[1]] = d; }, function (e) {
          failed += 1;
          if (e && e.auth) auth = true;
        });
      })).then(function () {
        inflight = null;
        s.auth = auth;
        s.err = (failed && !auth) ? NET_TEXT : "";
        draw();
        if (again) { again = false; return refresh(true); }
      });
      return inflight;
    }

    // 1초마다: 시계 갱신. 7초마다(그리고 숨김→보임으로 바뀔 때) 다시 읽는다. 숨겨졌으면 읽지 않는다.
    function tick() {
      var vis = active();
      var becameVisible = vis && !lastVisible;
      lastVisible = vis;
      draw();
      if (vis && (becameVisible || deps.nowFn() - lastRefresh >= REFRESH_MS)) return refresh(false);
      return Promise.resolve();
    }

    function togglePause() {
      if (s.busy || !s.status) return Promise.resolve();
      var pausing = !s.status.paused;
      if (!deps.confirmFn(confirmText(pausing, s.status.mode_engine))) return Promise.resolve();
      s.busy = true;
      s.pauseMsg = "";
      draw();
      var status = 0;
      return deps.fetchFn("/v2/api/pause", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused: pausing }),
      }).then(function (r) {
        status = r.status;
        return r.json().catch(function () { return {}; });
      }).then(function (body) {
        if (status === 200 && body && body.ok) { s.pauseMsg = ""; return; }
        if (status === 401 || status === 403) s.pauseMsg = GUIDE_TEXT;
        else if (status === 503) s.pauseMsg = BUSY_TEXT;
        else s.pauseMsg = FAIL_TEXT;
      }, function () {
        s.pauseMsg = BUSY_TEXT;
      }).then(function () {
        s.busy = false;
        draw();
        return refresh(true);   // 응답 뒤 status 를 다시 읽어 표시한다
      });
    }

    function logout() {
      var go = function () { deps.navigate("/"); };
      return deps.fetchFn("/v2/api/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }).then(go, go);
    }

    return { state: s, refresh: refresh, tick: tick, togglePause: togglePause, logout: logout, draw: draw };
  }

  globalThis.__v2basic = {
    GUIDE_TEXT: GUIDE_TEXT, INFO_TEXT: INFO_TEXT, REFRESH_MS: REFRESH_MS,
    kstClock: kstClock, fmtFixed: fmtFixed, modeNotice: modeNotice, confirmText: confirmText,
    pnlCell: pnlCell, assetCells: assetCells, buildView: buildView, createController: createController,
  };

  if (typeof document === "undefined") return;   // node 시험용

  // ---- DOM (값은 모두 textContent 로 넣는다) ----
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function mount(root) {
    var title = el("h3", "bx-title");
    var notice = el("div", "bx-notice"), noticeLead = el("b"), noticeRest = el("span");
    notice.appendChild(noticeLead); notice.appendChild(noticeRest);
    var mismatch = el("div", "bx-warn");
    var banner = el("div", "bx-banner");
    var clock = el("div", "bx-clock");
    var info = el("div", "bx-info");
    var log = el("div", "bx-log");
    var engine = el("div", "bx-engine"), engineLabel = el("span"), engineValue = el("b");
    engine.appendChild(engineLabel); engine.appendChild(document.createTextNode(" ")); engine.appendChild(engineValue);
    var actions = el("div", "bx-actions");
    var pauseBtn = el("button", "bx-btn"); pauseBtn.type = "button";
    var logoutBtn = el("button", "bx-btn", "🚪 로그아웃"); logoutBtn.type = "button";
    actions.appendChild(pauseBtn); actions.appendChild(logoutBtn);
    var pauseMsg = el("div", "bx-warn");
    var grid = el("div", "bx-grid");
    var cells = {};
    ["krw", "coin", "pnl"].forEach(function (k) {
      var box = el("div", "bx-cell");
      cells[k] = { label: el("div", "bx-small"), value: el("div", "bx-value"),
        delta: el("div", "bx-small"), caption: el("div", "bx-small") };
      box.appendChild(cells[k].label); box.appendChild(cells[k].value);
      box.appendChild(cells[k].delta); box.appendChild(cells[k].caption);
      grid.appendChild(box);
    });
    var auth = el("div", "bx-warn");
    var err = el("div", "bx-small");
    [title, notice, mismatch, banner, clock, info, log, engine, actions, pauseMsg, grid, auth, err]
      .forEach(function (n) { root.appendChild(n); });

    function show(node, on) { node.hidden = !on; }

    function render(v) {
      clock.textContent = v.clock;
      info.textContent = v.info;
      show(auth, !!v.auth);
      auth.textContent = v.auth || "";
      var ok = !v.auth && !v.loading;
      [title, notice, mismatch, banner, log, engine, actions, pauseMsg, grid].forEach(function (n) {
        if (!ok) show(n, false);
      });
      err.textContent = v.error || "";
      show(err, !!v.error);
      if (!ok) return;
      title.textContent = v.title; show(title, true);
      if (v.notice) {
        noticeLead.textContent = v.notice.lead; noticeRest.textContent = v.notice.rest;
        notice.className = "bx-notice bx-" + v.notice.kind;
      }
      show(notice, !!v.notice);
      mismatch.textContent = v.mismatch; show(mismatch, !!v.mismatch);
      banner.textContent = v.pausedBanner; show(banner, !!v.pausedBanner);
      log.textContent = v.log; show(log, true);
      engineLabel.textContent = v.engine.label; engineValue.textContent = v.engine.value;
      engine.className = "bx-engine " + (v.engine.running ? "bx-on" : "bx-off"); show(engine, true);
      pauseBtn.textContent = v.pauseBtn.label; pauseBtn.disabled = v.pauseBtn.disabled; show(actions, true);
      pauseMsg.textContent = v.pauseMsg; show(pauseMsg, !!v.pauseMsg);
      show(grid, !!v.assets);
      if (v.assets) {
        ["krw", "coin", "pnl"].forEach(function (k) {
          var c = v.assets[k];
          cells[k].label.textContent = c.label; cells[k].value.textContent = c.value;
          cells[k].delta.textContent = c.delta || " ";
          cells[k].caption.textContent = c.caption || ""; show(cells[k].caption, !!c.caption);
        });
      }
    }

    var ctl = createController({
      fetchFn: function (u, o) { return fetch(u, o); },
      confirmFn: function (t) { return window.confirm(t); },
      nowFn: function () { return Date.now(); },
      isHidden: function () { return document.hidden; },
      isVisible: function () { return root.getClientRects().length > 0; },
      render: render,
      navigate: function (u) { window.location.href = u; },
    });
    pauseBtn.addEventListener("click", function () { ctl.togglePause(); });
    logoutBtn.addEventListener("click", function () { ctl.logout(); });
    ctl.draw();
    setInterval(function () { ctl.tick(); }, 1000);
    ctl.tick();
  }

  function init() {
    var root = document.getElementById("basic");
    if (!root) return;
    mount(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
