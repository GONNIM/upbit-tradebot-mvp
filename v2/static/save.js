// 「저장만 하기」 확인 창 (Task 8). backtester.js 는 원본과 바이트 동일이라 건드리지 않고,
// 이 파일이 saveArea 안의 버튼·확인 창만 다룬다. 서버가 값을 검증한다(화면은 막지 않음).
(function () {
  "use strict";

  var GUIDE_TEXT = "구버전 입장 화면에서 『신버전 대시보드』를 다시 눌러 주세요";
  var NUMBER_IDS = ["days", "ma60p", "ma200p", "pullbackP", "slopeLB", "minSlope", "slopeDrop",
    "maxSplits", "maxPullbackBuys", "tp", "sl", "capital", "fee"];
  var TEXT_IDS = ["symbol", "maType", "src", "buyOnGoldenCross", "deadcross", "compounding"];
  // 서버가 받는 순서(화면 입력 19개)
  var ORDER = ["symbol", "maType", "src", "days", "ma60p", "ma200p", "pullbackP", "slopeLB",
    "minSlope", "slopeDrop", "buyOnGoldenCross", "maxSplits", "maxPullbackBuys", "tp", "sl",
    "capital", "fee", "deadcross", "compounding"];

  // number 칸은 빈 값이면 null, 아니면 Number. select·symbol 은 문자열 그대로.
  function collectParams(getById) {
    var out = {};
    for (var i = 0; i < ORDER.length; i++) {
      var id = ORDER[i];
      var el = getById(id);
      var v = el ? el.value : "";
      if (NUMBER_IDS.indexOf(id) >= 0) {
        out[id] = v === "" ? null : Number(v);
      } else {
        out[id] = String(v);
      }
    }
    return out;
  }

  // app.js 의 engineText 와 같은 낱말(정상 / 지연 / 판단 불가). 「정지」는 쓰지 않는다.
  function engineLabel(e) {
    if (!e) return "판단 불가";
    var ago = e.ago_sec == null ? "" : " · 마지막 판단 " + Math.floor(e.ago_sec / 60) + "분 전";
    if (e.level === "ok") return "정상" + ago;
    if (e.level === "delay") {
      return e.ago_sec == null ? "지연 · 계좌 갱신 기준"
        : "지연 · 마지막 판단 " + Math.floor(e.ago_sec / 60) + "분 전";
    }
    return "판단 불가" + ago;
  }

  function fmtTime(s) {
    return String(s).slice(0, 19).replace("T", " ");
  }

  // interval("minute60") → "60분 (minute60)", 모르는 값은 그대로
  function intervalText(iv) {
    for (var k in SRC_INTERVAL) {
      if (Object.prototype.hasOwnProperty.call(SRC_INTERVAL, k) && SRC_INTERVAL[k] === iv) {
        return SRC_LABEL[k] + " (" + iv + ")";
      }
    }
    return String(iv);
  }

  // 창을 열 때 19개 값을 한 번 모은 스냅샷. 저장 POST 는 이 스냅샷을 그대로 보낸다.
  function makeSnapshot(getById) {
    return { params: collectParams(getById), source: "binance" };
  }

  function snapshotBody(snap) {
    return JSON.stringify(snap);
  }

  function saveMessage(status, body) {
    body = body || {};
    if (status === 200 && body.ok) {
      return "저장했습니다 · " + (body.saved_at ? fmtTime(body.saved_at) : "시각 확인 불가") +
        " · 이력 번호 " + body.history_id +
        " · " + (body.ticker || "종목 미상") + " · " + intervalText(body.interval);
    }
    if (status === 400) return "입력값 확인: " + (body.field || "요청 형식");
    if (status === 401) return GUIDE_TEXT;
    if (status === 403) return "권한 없음";
    if (status === 409) return "엔진 종목을 알 수 없어 저장하지 않았습니다";
    if (status === 404 || status === 503) return "상태를 읽지 못했습니다";
    if (body.error === "file_changed") return "저장 실패 — 관리자 확인 필요";
    return "저장 실패 — 파일은 바뀌지 않았거나 되돌렸습니다";
  }

  // 화면 src → 파일 interval. 서버(params_schema._INTERVAL)와 같아야 하며 시험이 대조한다.
  var SRC_INTERVAL = { "1m": "minute1", "3m": "minute3", "5m": "minute5", "1h": "minute60" };
  var SRC_LABEL = { "1m": "1분", "3m": "3분", "5m": "5분", "1h": "60분" };

  function srcToInterval(src) {
    return Object.prototype.hasOwnProperty.call(SRC_INTERVAL, src) ? SRC_INTERVAL[src] : null;
  }

  // 「저장될 봉」 줄 문구: "60분 (minute60)", 매핑 밖이면 "알 수 없음"
  function srcText(src) {
    var iv = srcToInterval(src);
    return iv ? SRC_LABEL[src] + " (" + iv + ")" : "알 수 없음";
  }

  // 엔진 현재 봉과 다를 때의 경고 문구(같거나 비교 불가면 null). 저장은 막지 않는다.
  function intervalWarning(src, engineInterval) {
    var iv = srcToInterval(src);
    if (!iv || !engineInterval || iv === engineInterval) return null;
    return "백테스트 봉(" + SRC_LABEL[src] + ")이 엔진 현재 봉(" + engineInterval +
      ")과 다릅니다 — 저장만 하며 엔진은 바뀌지 않습니다";
  }

  // 「저장만 하기」 버튼 비활성 조건: 미리 읽기 전·종목 모름·저장 중·저장 성공 뒤(창을 닫을 때까지)
  function saveButtonDisabled(s) {
    return !s.preloaded || !s.hasTicker || !!s.saving || !!s.saved;
  }

  // 「마지막 저장」 줄: 저장 응답의 saved_at 이 있으면 그것, 없으면 current(다시 읽은 값)
  function lastSavedText(saved_at, current) {
    if (saved_at) return fmtTime(saved_at);
    if (current && current.exists && !current.broken && current.mtime) return fmtTime(current.mtime);
    return "저장 기록 없음";
  }

  // 미리 읽기 세대 번호: 가장 최근에 연 것의 응답만 반영한다
  function makeGate() {
    var n = 0;
    return {
      next: function () { n += 1; return n; },
      isCurrent: function (g) { return g === n; },
    };
  }

  globalThis.__v2save = {
    SRC_INTERVAL: SRC_INTERVAL, srcToInterval: srcToInterval, srcText: srcText,
    intervalWarning: intervalWarning, saveButtonDisabled: saveButtonDisabled, lastSavedText: lastSavedText, makeGate: makeGate,
    makeSnapshot: makeSnapshot, snapshotBody: snapshotBody, intervalText: intervalText,
    collectParams: collectParams, saveMessage: saveMessage, engineLabel: engineLabel,
    NUMBER_IDS: NUMBER_IDS, TEXT_IDS: TEXT_IDS, GUIDE_TEXT: GUIDE_TEXT,
  };

  if (typeof document === "undefined") return;   // node 시험용

  var openBtn = null, dialog = null, infoBox = null, msgBox = null, doBtn = null, closeBtn = null;
  var preloaded = false, saving = false, saved = false, hasTicker = false;
  var lastSavedSpan = null, snapshot = null;
  var gate = makeGate();

  function setMsg(text) { msgBox.textContent = text; }

  function refreshButton() {
    doBtn.disabled = saveButtonDisabled({
      preloaded: preloaded, hasTicker: hasTicker, saving: saving, saved: saved });
  }

  function addLine(label, value, big) {
    var row = document.createElement("div");
    row.style.cssText = "margin:4px 0;word-break:break-word";
    var b = document.createElement("b");
    b.textContent = label + ": ";
    var span = document.createElement("span");
    span.textContent = value;
    if (big) span.style.cssText = "font-size:20px;font-weight:bold";
    row.appendChild(b);
    row.appendChild(span);
    infoBox.appendChild(row);
    return span;
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) { var e = new Error("http"); e.status = r.status; throw e; }
      return r.json();
    });
  }

  function failText(err) {
    if (err && err.status === 401) return GUIDE_TEXT;
    if (err && err.status === 403) return "권한 없음";
    return "상태를 읽지 못했습니다";
  }

  function render(status, assets, current) {
    infoBox.textContent = "";
    var strat = status.strategy && status.strategy.value;
    addLine("현재 전략", strat || "알 수 없음");
    addLine("모드", status.mode_engine || "확인 불가", true);
    if (status.mode_mismatch) {
      addLine("경고", "입장 모드(" + (status.mode_entry || "?") + ")와 엔진 모드(" +
        (status.mode_engine || "?") + ")가 다릅니다.");
    }
    addLine("엔진 동작", engineLabel(status.engine));
    var held = (assets.coin || 0) + (assets.coin_locked || 0) > 0;
    addLine("보유 포지션", held
      ? "수량 " + assets.coin + (assets.coin_locked > 0 ? " (묶임 " + assets.coin_locked + ")" : "") +
        " · 평단 " + (assets.entry_price == null ? "—" : assets.entry_price)
      : "없음");
    if (status.ticker) {
      addLine("저장될 종목", status.ticker + " (엔진 현재 종목)");
    }
    var snapSrc = snapshot.params.src;
    addLine("저장될 봉", srcText(snapSrc));
    var warn = intervalWarning(snapSrc, status.interval);
    if (warn) addLine("경고", warn);
    lastSavedSpan = addLine("마지막 저장", lastSavedText(null, current));
    hasTicker = !!status.ticker;
    setMsg(hasTicker ? "" : "엔진 종목을 알 수 없어 저장할 수 없습니다");
    refreshButton();
  }

  function openDialog() {
    var g = gate.next();
    // 창을 여는 순간의 19개 값을 한 번 모은다(닫았다 다시 열면 새로 모음)
    snapshot = makeSnapshot(function (id) { return document.getElementById(id); });
    dialog.hidden = false;
    infoBox.textContent = "";
    setMsg("상태를 읽는 중…");
    preloaded = false;
    hasTicker = false;
    saved = false;
    lastSavedSpan = null;
    refreshButton();
    Promise.all([getJson("/v2/api/status"), getJson("/v2/api/assets"),
      getJson("/v2/api/params/current")]).then(function (r) {
      if (!gate.isCurrent(g)) return;   // 더 최근에 연 미리 읽기가 있으면 버린다
      preloaded = true;
      render(r[0], r[1], r[2]);
    }).catch(function (err) {
      if (!gate.isCurrent(g)) return;
      infoBox.textContent = "";
      setMsg(failText(err));
      preloaded = false;
      hasTicker = false;
      refreshButton();
    });
  }

  function closeDialog() {
    gate.next();   // 진행 중인 미리 읽기 응답을 무효화
    dialog.hidden = true;
  }

  // 저장 성공 뒤 「마지막 저장」 줄 갱신: 응답 saved_at, 없으면 current 를 다시 읽는다
  function updateLastSaved(body) {
    if (!lastSavedSpan) return;
    if (body.saved_at) {
      lastSavedSpan.textContent = lastSavedText(body.saved_at, null);
      return;
    }
    getJson("/v2/api/params/current").then(function (cur) {
      if (lastSavedSpan) lastSavedSpan.textContent = lastSavedText(null, cur);
    }).catch(function () {});
  }

  function doSave() {
    if (saving || !preloaded || !hasTicker || saved || !snapshot) return;
    saving = true;
    refreshButton();
    setMsg("저장 중…");
    var status = 0;   // 보내는 본문은 창을 열 때 모은 스냅샷 그대로
    fetch("/v2/api/params/save", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: snapshotBody(snapshot),
    }).then(function (r) {
      status = r.status;
      return r.json().catch(function () { return {}; });
    }).then(function (body) {
      setMsg(saveMessage(status, body));
      if (status === 200 && body.ok) {
        saved = true;   // 창을 닫을 때까지 다시 저장하지 못하게 한다(이력 중복 방지)
        updateLastSaved(body);
      }
    }).catch(function () {
      setMsg("저장 결과를 확인하지 못했습니다 — 마지막 저장 시각을 다시 확인하세요");
    }).then(function () {
      saving = false;
      refreshButton();
    });
  }

  function init() {
    openBtn = document.getElementById("saveOpenBtn");
    dialog = document.getElementById("saveDialog");
    infoBox = document.getElementById("saveInfo");
    msgBox = document.getElementById("saveMsg");
    doBtn = document.getElementById("saveDoBtn");
    closeBtn = document.getElementById("saveCloseBtn");
    if (!openBtn || !dialog || !infoBox || !msgBox || !doBtn || !closeBtn) return;
    openBtn.addEventListener("click", openDialog);
    closeBtn.addEventListener("click", closeDialog);
    doBtn.addEventListener("click", doSave);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
