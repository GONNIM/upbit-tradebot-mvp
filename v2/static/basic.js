// 매매 중지/재개·로그아웃 제어 (구버전 pages/dashboard.py 의 해당 단추를 신버전 홈에서 그대로 제공).
// 그리는 곳은 두 군데: 홈 배지 줄 아래 #pause-row(중지/재개 단추·실패 문구·일시정지 알림 띠)와 머리 막대 #logout-btn.
// 읽기: GET /v2/api/status 하나(자산·기본 정보는 app.js 가 읽는다). 쓰기: POST /v2/api/pause·logout (서버가 세션·Origin 확인).
// 업비트는 부르지 않는다. 원본 백테스터 스크립트(backtester.js)·입력 칸은 건드리지 않는다.
(function () {
  "use strict";

  var GUIDE_TEXT = "구버전에서 다시 들어와 주세요";
  var NET_TEXT = "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다.";
  var BUSY_TEXT = "잠시 뒤 다시 시도해 주세요";
  var FAIL_TEXT = "처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
  // 알림 띠는 단추 아래에 놓이므로 「위」 단추를 가리킨다
  var PAUSED_BANNER = "⏸️ 매매 일시중지 상태 — 엔진과 지표는 정상 작동하지만 실주문(BUY/SELL)은 " +
    "실행되지 않습니다. 재개하려면 위 '▶️ 매매 재개' 단추를 클릭하세요.";
  var REFRESH_MS = 7000;

  function confirmText(pausing, mode) {
    if (!pausing) return "매매를 재개합니다.";
    return "매매를 중지합니다(모드: " + (mode || "확인 불가") + "). " +
      "중지 중에는 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. " +
      "이미 걸려 있는 주문은 취소되지 않고, 미체결 지정가 매수가 시장가로 바뀌는 처리는 계속될 수 있습니다.";
  }

  // 화면에 그릴 값 전부(문자열). DOM 을 만지지 않는 순수 함수라 node 시험에서 검사한다.
  function buildView(s) {
    var view = {};
    if (s.auth) {
      view.auth = GUIDE_TEXT;
      return view;
    }
    view.error = s.err || "";
    var st = s.status;
    if (!st) {
      view.loading = true;
      view.pauseBtn = { label: "⏸️ 매매 중지", disabled: true };   // 상태를 모르면 누를 수 없다
      view.pauseMsg = s.pauseMsg || "";
      view.pausedBanner = "";
      return view;
    }
    view.pausedBanner = st.paused ? PAUSED_BANNER : "";
    view.pauseBtn = { label: st.paused ? "▶️ 매매 재개" : "⏸️ 매매 중지", disabled: !!s.busy };
    view.pauseMsg = s.pauseMsg || "";
    return view;
  }

  // 상태 보관·읽기·쓰기. deps: fetchFn, confirmFn, nowFn, isHidden, isVisible, render, navigate
  function createController(deps) {
    var s = { status: null, auth: false, err: "", busy: false, pauseMsg: "" };
    var inflight = null;      // 진행 중인 읽기(Promise)
    var again = false;        // 진행 중에 강제 읽기가 들어오면 끝난 뒤 한 번 더 읽는다
    var lastRefresh = -Infinity;
    var lastVisible = false;

    function draw() { deps.render(buildView(s)); }

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
      var failed = false, auth = false;
      inflight = getJson("/v2/api/status").then(function (d) { s.status = d; }, function (e) {
        failed = true;
        if (e && e.auth) auth = true;
      }).then(function () {
        inflight = null;
        s.auth = auth;
        s.err = (failed && !auth) ? NET_TEXT : "";
        draw();
        if (again) { again = false; return refresh(true); }
      });
      return inflight;
    }

    // 1초마다 호출. 7초마다(그리고 숨김→보임으로 바뀔 때) 다시 읽는다. 숨겨졌으면 읽지 않는다.
    function tick() {
      var vis = active();
      var becameVisible = vis && !lastVisible;
      lastVisible = vis;
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
    GUIDE_TEXT: GUIDE_TEXT, REFRESH_MS: REFRESH_MS, PAUSED_BANNER: PAUSED_BANNER,
    confirmText: confirmText, buildView: buildView, createController: createController,
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
    var auth = el("div", "bx-warn");
    var pauseBtn = el("button", "bx-btn"); pauseBtn.type = "button";
    var pauseMsg = el("div", "bx-warn");
    var banner = el("div", "bx-banner");
    var err = el("div", "bx-small");
    [auth, pauseBtn, pauseMsg, banner, err].forEach(function (n) { root.appendChild(n); });

    function show(node, on) { node.hidden = !on; }

    function render(v) {
      show(auth, !!v.auth);
      auth.textContent = v.auth || "";
      err.textContent = v.error || "";
      show(err, !!v.error);
      var ok = !v.auth;
      show(pauseBtn, ok); show(pauseMsg, ok && !!v.pauseMsg); show(banner, ok && !!v.pausedBanner);
      if (!ok) return;
      pauseBtn.textContent = v.pauseBtn.label; pauseBtn.disabled = v.pauseBtn.disabled;
      pauseMsg.textContent = v.pauseMsg;
      banner.textContent = v.pausedBanner;
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
    var logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) logoutBtn.addEventListener("click", function () { ctl.logout(); });
    ctl.draw();
    setInterval(function () { ctl.tick(); }, 1000);
    ctl.tick();
  }

  function init() {
    var root = document.getElementById("pause-row");
    if (!root) return;
    mount(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
