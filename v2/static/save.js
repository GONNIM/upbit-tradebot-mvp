// 「저장만 하기」 확인 창 (Task 8). backtester.js 는 원본과 바이트 동일이라 건드리지 않고,
// 이 파일이 saveArea 안의 버튼·확인 창만 다룬다. 서버가 값을 검증한다(화면은 막지 않음).
(function () {
  "use strict";

  var GUIDE_TEXT = "구버전 입장 화면에서 『신버전 대시보드』를 다시 눌러 주세요";
  // 1105-09 (Ver2): 200선 기울기 2칸을 빼고 새 8칸을 넣었다(19 → 25). gcMaxGapPct 는 select 라 문자열로 보낸다.
  var NUMBER_IDS = ["days", "ma60p", "ma200p", "pullbackP", "slopeLB",
    "ma60MinSlope", "ma60SlopeDrop", "slStreakPause", "slStreakCooldownHours",
    "episodePullbackCap", "episodeTpDecayPct", "episodeTpFloorPct",
    "maxSplits", "maxPullbackBuys", "tp", "sl", "capital", "fee"];
  var TEXT_IDS = ["symbol", "maType", "src", "gcMaxGapPct", "buyOnGoldenCross", "deadcross", "compounding"];
  // 서버가 받는 순서(화면 입력 25개 — v2/params_schema.PARAM_FIELDS 와 같음)
  var ORDER = ["symbol", "maType", "src", "days", "ma60p", "ma200p", "pullbackP", "slopeLB",
    "gcMaxGapPct", "ma60MinSlope", "ma60SlopeDrop", "slStreakPause", "slStreakCooldownHours",
    "episodePullbackCap", "episodeTpDecayPct", "episodeTpFloorPct",
    "buyOnGoldenCross", "maxSplits", "maxPullbackBuys", "tp", "sl",
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

  // 화면 시각 표기(1112-01): kst_time.js 의 kstStamp 사본. 백테스터 화면(backtester.html)은 kst_time.js 를
  // 읽지 않아 사본을 둔다 — 시험(time.test.mjs)이 두 함수 글자가 그대로 같은지 본다. 고칠 때는 둘 다 고친다.
  function kstStamp(v) {
    var t = v instanceof Date ? v.getTime() : (typeof v === "number" ? v : (typeof v === "string" && v ? Date.parse(v) : NaN));
    if (!Number.isFinite(t)) return null;
    var d = new Date(t + 9 * 3600 * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getUTCFullYear() % 100) + "." + p(d.getUTCMonth() + 1) + "." + p(d.getUTCDate()) + " " +
      p(d.getUTCHours()) + ":" + p(d.getUTCMinutes());
  }

  // 「YY.MM.DD HH:MM」, 해석 못 하면 원문 그대로(옛 표기와 같은 빈 값 규칙)
  function fmtTime(s) {
    return kstStamp(String(s)) || String(s);
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

  // 창을 열 때 25개 값을 한 번 모은 스냅샷. 저장 POST 는 이 스냅샷을 그대로 보낸다.
  function makeSnapshot(getById) {
    var ds = getById("dataSource");
    var snap = { params: collectParams(getById), source: ds && ds.value === "upbit" ? "upbit" : "binance" };
    var ts = collectTrailing(getById);
    if (ts) snap.trailing = ts;
    return snap;
  }

  // 1110-01: 백테스터의 추적 손절 3칸(trailingStop·trailingMode·trailingPct) → 서버 선택 필드 trailing.
  // 칸이 없는 화면이면 null(요청에 싣지 않음 → 서버는 기존 저장값 보존). 값 검증은 서버(params_schema.valid_trailing).
  function collectTrailing(getById) {
    var on = getById("trailingStop"), mode = getById("trailingMode"), pct = getById("trailingPct");
    if (!on || !mode || !pct) return null;
    return { ts_on: on.value === "yes", ts_mode: String(mode.value), ts_pct: pct.value === "" ? null : Number(pct.value) };
  }

  // 「추적 손절: 끔」 / 「추적 손절: 켬 · 비율 50% (다음 거래부터)」
  function trailingText(snap) {
    var t = snap && snap.trailing;
    if (!t) return "";
    if (!t.ts_on) return "추적 손절: 끔 (익절가에서 매도)";
    return "추적 손절: 켬 · " + (t.ts_mode === "fixed" ? "고정폭 " : "비율 ") + t.ts_pct + "% (다음 거래부터 적용)";
  }

  // ---- 확인 창 문구 (그림 5-가·5-나) ----
  function sourceName(source) { return source === "upbit" ? "업비트" : "바이낸스"; }

  // 「시험한 데이터: 업비트 · KRW-XXX · 1분」
  function testedText(snap) {
    var p = snap.params;
    return "시험한 데이터: " + sourceName(snap.source) + " · " + p.symbol + " · " +
      (Object.prototype.hasOwnProperty.call(SRC_LABEL, p.src) ? SRC_LABEL[p.src] : String(p.src));
  }

  // 「지금 상태」 4행. 전략 EMA 는 「EMA (기존)」, 엔진은 생존 파일 기준 동작 중/멈춤(basic 을 못 읽었으면 확인 불가).
  function stateRows(status, assets, basic, ticker) {
    var strat = status && status.strategy && status.strategy.value;
    var qty = ((assets && assets.coin) || 0) + ((assets && assets.coin_locked) || 0);
    return [
      ["모드", (status && status.mode_engine) || "확인 불가"],
      ["동작 중인 전략", strat ? (strat === "EMA" ? "EMA (기존)" : strat) : "알 수 없음"],
      ["엔진", !basic ? "확인 불가" : basic.engine_running ? "동작 중" : "멈춤"],
      ["보유", qty > 0 ? (ticker || "종목 미상") + " " + qty : "없음"],
    ];
  }

  // 확인 창 미리 읽기 4건. 엔진 표시용 /v2/api/basic 실패는 null 로 받아 저장을 막지 않는다.
  function preloadAll(get) {
    return Promise.all([get("/v2/api/status"), get("/v2/api/assets"),
      get("/v2/api/params/current"), get("/v2/api/basic").catch(function () { return null; })]);
  }

  function runBtnLabel(source) {
    return source === "upbit" ? "이 설정으로 동작" : "이 설정으로 동작 (사용 불가)";
  }

  function runNote(source) {
    return source === "upbit"
      ? "「이 설정으로 동작」을 누르면 저장한 뒤, 지금 전략이 기존 방식(EMA·MACD)이면 전환 확인으로 넘어가고 " +
        "새 전략이면 바로 적용합니다."
      : "바이낸스 데이터 결과는 참고용입니다. 실제 매매에 쓰시려면 업비트 데이터로 다시 시험해 주십시오.";
  }

  // ---- 2차 T13: 「이 설정으로 동작」 (결정 D9) ----
  var SWITCH_CONFIRM = "지금 보유분이 있으면 기존 방식으로 판 뒤 바뀝니다. 전환할까요?";
  // 1109: 실계좌는 예약이 없다 — 보유 중·미체결이 있으면 전환되지 않고, 미보유일 때만 바로 바뀐다
  var SWITCH_CONFIRM_LIVE = "실계좌는 지금 보유 중이거나 미체결 주문이 있으면 전환되지 않습니다(예약도 없습니다). " +
    "미보유일 때만 바로 바뀝니다. 전환할까요?";
  function switchConfirmText(mode) {
    return String(mode).toUpperCase() === "LIVE" ? SWITCH_CONFIRM_LIVE : SWITCH_CONFIRM;
  }
  var START_CONFIRM = "엔진이 멈춰 있습니다. 엔진을 시작할까요?";
  var NO_RESPONSE_TEXT = "엔진이 응답하지 않습니다 — 잠시 뒤 결과를 다시 확인해 주세요";
  var POLL_STEP_MS = 2000;
  var POLL_MAX_MS = 60000;

  // 누르면 할 일: 바이낸스·전략 모름 → "disabled", EMA·MACD → "switch"(전환 확인 창),
  // 새 전략 + 엔진 멈춤 → "ask_start"(「엔진을 시작할까요?」), 새 전략 + 엔진 동작(또는 확인 불가) → "apply"
  function runPlan(status, basic, source) {
    if (source !== "upbit") return "disabled";
    var strat = status && status.strategy && status.strategy.value;
    if (strat === "EMA" || strat === "MACD") return "switch";
    if (strat !== "PULLBACK") return "disabled";
    if (basic && basic.engine_running === false) return "ask_start";
    return "apply";
  }

  function runButtonDisabled(s) {
    return !s.preloaded || !s.hasTicker || !!s.saving || !!s.running || !!s.ran || s.plan === "disabled";
  }

  // 엔진 결과(GET /v2/api/control/result) → 화면 한 줄. 결과 파일 message 는 엔진이 쓴 투자자용 문구다.
  function runResultText(res) {
    if (!res || res.status === "pending") return NO_RESPONSE_TEXT;
    if (res.message) return String(res.message);
    return res.status === "done" ? "요청대로 처리했습니다." : "처리하지 못했습니다.";
  }

  // 요청 POST 실패 문구
  function controlPostText(status, body) {
    body = body || {};
    if (status === 409) return "앞 요청을 처리하는 중입니다. 잠시 뒤 다시 눌러 주세요.";
    if (status === 400 && body.error === "source_not_upbit") {
      return "바이낸스 데이터 결과는 참고용이라 적용할 수 없습니다. 업비트 데이터로 다시 시험해 저장해 주세요.";
    }
    if (status === 401) return GUIDE_TEXT;
    if (status === 403) return "권한 없음";
    return "요청을 보내지 못했습니다";
  }

  // 결과를 2초마다 60초까지 읽는다. get(url) → Promise<json>, wait(ms) → Promise. 끝나면 결과(못 받으면 null).
  function pollResult(get, wait, id, stepMs, maxMs) {
    var step = stepMs == null ? POLL_STEP_MS : stepMs;
    var max = maxMs == null ? POLL_MAX_MS : maxMs;
    var spent = 0;
    function once() {
      return get("/v2/api/control/result?id=" + encodeURIComponent(id)).then(function (r) {
        if (r && r.status && r.status !== "pending") return r;
        return null;
      }, function () { return null; }).then(function (r) {
        if (r) return r;
        if (spent >= max) return null;
        spent += step;
        return wait(step).then(once);
      });
    }
    return once();
  }

  // 업비트로 시험한 종목이 엔진 종목과 다를 때의 경고(같거나 비교 불가면 null). 저장은 엔진 종목 기준.
  function symbolWarning(snap, engineTicker) {
    if (snap.source !== "upbit" || !engineTicker) return null;
    var sym = String(snap.params.symbol || "").trim().toUpperCase();
    if (sym === engineTicker) return null;
    return "시험한 종목(" + sym + ")이 엔진 종목(" + engineTicker + ")과 다릅니다 — 저장은 엔진 종목 기준입니다";
  }

  // 1105-09 (2-1): 구간 초과 TP 하한이 익절 TP 보다 크면 경고만(Ver2 도 막지 않음). 그 밖 null
  function floorWarning(params) {
    var p = params || {};
    var cap = Number(p.episodePullbackCap), floor = Number(p.episodeTpFloorPct), tp = Number(p.tp);
    if (!(cap > 0) || !Number.isFinite(floor) || !Number.isFinite(tp) || !(floor > tp)) return null;
    return "구간 초과 TP 하한(" + floor + "%)이 익절 TP(" + tp + "%)보다 큽니다 — 눌림목 돌파 횟수(" + cap +
      "회)를 넘은 거래는 익절 목표가 기본 TP 보다 높아집니다";
  }

  function snapshotBody(snap) {
    return JSON.stringify(snap);
  }

  // ---- 1109 눌림목 실계좌 열기: 눌림목 전용 「투자 비율(%)」 칸 (저장 확인 창에만 — backtester.js 는 건드리지 않는다) ----
  // 서버 규칙(v2/params_schema.valid_ratio)과 같다: 0.1~100, 소수 첫째 자리까지. 비우면 null(실계좌는 비율이 있어야 동작).
  var RATIO_LABEL = "투자 비율 (%)";
  var RATIO_RANGE_TEXT = "투자 비율은 0.1~100 사이, 소수 첫째 자리까지 입력해 주세요";
  var ENGINE_FEE_RATE = 0.0005;     // config.MIN_FEE_RATIO 와 같은 값(엔진이 수수료 몫을 빼고 배분 기준을 정한다)
  var MIN_ORDER_KRW = 5000;

  function ratioParse(text) {
    var t = String(text == null ? "" : text).trim();
    if (t === "") return { ok: true, value: null };
    if (!/^\d+(\.\d)?$/.test(t)) return { ok: false, text: RATIO_RANGE_TEXT };
    var v = Number(t);
    if (!(v >= 0.1 && v <= 100)) return { ok: false, text: RATIO_RANGE_TEXT };
    return { ok: true, value: v };
  }

  function ratioHint(mode) {
    return String(mode).toUpperCase() === "LIVE"
      ? "새 거래 1회차 시작 때 가용 원화의 %"
      : "새 거래 1회차 시작 때 운용자산의 % (비우면 100%)";
  }

  function ratioEmptyNote(mode) {
    return String(mode).toUpperCase() === "LIVE"
      ? "실계좌는 투자 비율을 먼저 입력해야 「이 설정으로 동작」이 됩니다." : "";
  }

  function _won(n) { return Math.floor(Number(n)).toLocaleString("ko-KR"); }

  // 엔진(core/strategy_engine._pullback_new_trade_base)과 같은 식. 실계좌: floor(원화×비율÷100÷(1+수수료)), 모의: 운용자산×비율(없으면 100%).
  // 1회 금액 = floor(기준 ÷ 분할 횟수(0 은 1회)). 실계좌에서 비율이 비었거나 원화를 모르면 null.
  function ratioPreview(o) {
    var live = String(o.mode).toUpperCase() === "LIVE";
    var krw = Number(o.krw);
    if (o.krw == null || !(krw > 0) || !Number.isFinite(krw)) return null;
    var ratio = o.ratio;
    if (live && (ratio == null)) return null;
    var pct = ratio == null ? 100 : Number(ratio);
    var base = live ? Math.floor(krw * pct / 100 / (1 + ENGINE_FEE_RATE)) : Math.floor(krw * pct / 100);
    var eff = Math.max(1, Math.floor(Number(o.maxSplits) || 0));
    var per = Math.floor(base / eff);
    return { base: base, perBuy: per, splits: eff, pct: pct, belowMin: per < MIN_ORDER_KRW };
  }

  function ratioPreviewText(o) {
    var p = ratioPreview(o);
    if (!p) {
      if (o.krw == null || !(Number(o.krw) > 0)) return "지금 원화를 읽지 못해 미리 보기를 계산하지 못했습니다";
      return "";
    }
    var live = String(o.mode).toUpperCase() === "LIVE";
    var s = "지금 " + (live ? "원화 " : "운용자산 ") + _won(o.krw) + "원 · 비율 " + p.pct + "% · 1회 금액 약 " +
      _won(p.perBuy) + "원 (" + p.splits + "회 분할)";
    if (p.belowMin) s += " — 1회 금액이 5,000원보다 작아 주문을 건너뜁니다";
    return s;
  }

  // 저장 요청 본문: 비율 칸을 건드렸을 때만 investRatioPct(숫자 또는 null=지움)를 싣는다. 안 건드렸으면 기존 저장값이 남는다.
  function bodyWithRatio(snap, ratioState) {
    var out = {};
    for (var k in snap) { if (Object.prototype.hasOwnProperty.call(snap, k)) out[k] = snap[k]; }
    if (ratioState && ratioState.dirty) out.investRatioPct = ratioState.value == null ? null : ratioState.value;
    return JSON.stringify(out);
  }

  // GET /v2/api/params/current 응답에서 입장 모드의 저장된 비율(없으면 null)
  function savedRatio(current, mode) {
    if (!current || !current.exists || current.broken || !current.params) return null;
    var key = String(mode).toUpperCase() === "LIVE" ? "invest_ratio_pct_live" : "invest_ratio_pct_test";
    var v = current.params[key];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  }

  function saveMessage(status, body) {
    body = body || {};
    if (status === 200 && body.ok) {
      return "저장했습니다 · " + (body.saved_at ? fmtTime(body.saved_at) : "시각 확인 불가") +
        " · 이력 번호 " + body.history_id +
        " · " + (body.ticker || "종목 미상") + " · " + intervalText(body.interval);
    }
    if (status === 400 && body.error === "invest_ratio_pct") return RATIO_RANGE_TEXT;
    if (status === 400 && body.field === "trailing") return "추적 손절 폭은 1~100 사이, 소수 첫째 자리까지 입력해 주세요";   // 1110-01
    if (status === 400) return "입력값 확인: " + (body.field || "요청 형식");
    if (status === 401) return GUIDE_TEXT;
    if (status === 403) return "권한 없음";
    if (status === 409) return "엔진 종목을 알 수 없어 저장하지 않았습니다";
    if (status === 404 || status === 503) return "상태를 읽지 못했습니다";
    if (body.error === "file_changed") return "저장 실패 — 관리자 확인 필요";
    return "저장 실패 — 파일은 바뀌지 않았거나 되돌렸습니다";
  }

  // 화면 src → 파일 interval. 서버(params_schema._INTERVAL)와 같아야 하며 시험이 대조한다.
  // 1105-09 (Ver2 R7): 10·15·30분 추가
  var SRC_INTERVAL = { "1m": "minute1", "3m": "minute3", "5m": "minute5", "10m": "minute10", "15m": "minute15",
    "30m": "minute30", "1h": "minute60" };
  var SRC_LABEL = { "1m": "1분", "3m": "3분", "5m": "5분", "10m": "10분", "15m": "15분", "30m": "30분", "1h": "60분" };

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
    collectTrailing: collectTrailing, trailingText: trailingText,
    collectParams: collectParams, saveMessage: saveMessage, engineLabel: engineLabel,
    NUMBER_IDS: NUMBER_IDS, TEXT_IDS: TEXT_IDS, GUIDE_TEXT: GUIDE_TEXT,
    testedText: testedText, stateRows: stateRows, runBtnLabel: runBtnLabel, runNote: runNote,
    symbolWarning: symbolWarning, floorWarning: floorWarning, preloadAll: preloadAll,
    runPlan: runPlan, runButtonDisabled: runButtonDisabled, runResultText: runResultText,
    controlPostText: controlPostText, pollResult: pollResult,
    RATIO_LABEL: RATIO_LABEL, RATIO_RANGE_TEXT: RATIO_RANGE_TEXT, ratioParse: ratioParse, ratioHint: ratioHint,
    ratioEmptyNote: ratioEmptyNote, ratioPreview: ratioPreview, ratioPreviewText: ratioPreviewText,
    bodyWithRatio: bodyWithRatio, savedRatio: savedRatio,
    SWITCH_CONFIRM: SWITCH_CONFIRM, SWITCH_CONFIRM_LIVE: SWITCH_CONFIRM_LIVE, switchConfirmText: switchConfirmText,
    START_CONFIRM: START_CONFIRM, NO_RESPONSE_TEXT: NO_RESPONSE_TEXT,
  };

  if (typeof document === "undefined") return;   // node 시험용

  var openBtn = null, dialog = null, infoBox = null, msgBox = null, doBtn = null, closeBtn = null;
  var preloaded = false, saving = false, saved = false, hasTicker = false;
  var lastSavedSpan = null, snapshot = null, testedBox = null, runBtn = null, runNoteBox = null;
  var gate = makeGate();
  // 2차 T13: 「이 설정으로 동작」 상태
  var plan = "disabled", running = false, ran = false, lastSave = null;
  // 1109: 투자 비율 칸(저장 창 안에서 만든다) · 입장 모드 · 마지막으로 읽은 원화(미리 보기용)
  var ratioInput = null, ratioHintBox = null, ratioPreviewBox = null, ratioErrBox = null;
  var ratioState = { dirty: false, value: null };
  var entryMode = "", lastKrw = null, lastNote = "";

  function setMsg(text) { msgBox.textContent = text; }

  function refreshButton() {
    doBtn.disabled = saveButtonDisabled({
      preloaded: preloaded, hasTicker: hasTicker, saving: saving, saved: saved });
    if (runBtn) {
      runBtn.disabled = runButtonDisabled({ preloaded: preloaded, hasTicker: hasTicker, saving: saving,
        running: running, ran: ran, plan: plan });
    }
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

  // 그림 5: 「지금 상태」 4행(표) 아래에 저장될 종목·봉·경고·마지막 저장을 작은 글씨로 남긴다.
  function addKv(label, value) {
    var row = document.createElement("div");
    row.className = "kv";
    var a = document.createElement("span");
    a.textContent = label;
    var b = document.createElement("b");
    b.textContent = value;
    row.appendChild(a);
    row.appendChild(b);
    infoBox.appendChild(row);
  }

  function addSmall(label, value) {
    var row = document.createElement("div");
    row.className = "sm";
    var span = document.createElement("span");
    span.textContent = value;
    row.appendChild(document.createTextNode(label + ": "));
    row.appendChild(span);
    infoBox.appendChild(row);
    return span;
  }

  // ---- 1109: 투자 비율 칸 ----
  function buildRatioField() {
    var wrap = document.createElement("div");
    wrap.id = "saveRatioWrap";
    wrap.style.cssText = "margin:10px 0";
    var lab = document.createElement("label");
    lab.setAttribute("for", "saveRatio");
    lab.style.cssText = "display:block;font-weight:bold;margin-bottom:4px";
    lab.textContent = RATIO_LABEL;
    ratioInput = document.createElement("input");
    ratioInput.id = "saveRatio";
    ratioInput.type = "number";
    ratioInput.step = "0.1";
    ratioInput.min = "0.1";
    ratioInput.max = "100";
    ratioInput.setAttribute("inputmode", "decimal");
    ratioInput.style.cssText = "width:100%;box-sizing:border-box;padding:8px;font-size:16px;border:1px solid var(--line);" +
      "border-radius:8px;background:var(--card);color:var(--fg)";
    ratioHintBox = document.createElement("div");
    ratioHintBox.className = "small";
    ratioPreviewBox = document.createElement("div");
    ratioPreviewBox.className = "small";
    ratioPreviewBox.style.wordBreak = "break-word";
    ratioErrBox = document.createElement("div");
    ratioErrBox.className = "small";
    ratioErrBox.style.cssText = "color:#dc2626;word-break:break-word";
    wrap.appendChild(lab);
    wrap.appendChild(ratioInput);
    wrap.appendChild(ratioHintBox);
    wrap.appendChild(ratioPreviewBox);
    wrap.appendChild(ratioErrBox);
    msgBox.parentNode.insertBefore(wrap, msgBox);
    ratioInput.addEventListener("input", function () {
      ratioState.dirty = true;
      refreshRatio();
    });
  }

  function currentMaxSplits() {
    var p = snapshot && snapshot.params;
    return p ? p.maxSplits : null;
  }

  // 입력 → 해석 + 안내·미리 보기·적용 단추 옆 안내(칸이 비면 실계좌 경고)
  function refreshRatio() {
    if (!ratioInput) return;
    var parsed = ratioParse(ratioInput.value);
    ratioErrBox.textContent = parsed.ok ? "" : parsed.text;
    ratioState.value = parsed.ok ? parsed.value : null;
    ratioHintBox.textContent = ratioHint(entryMode);
    ratioPreviewBox.textContent = parsed.ok ? ratioPreviewText({
      krw: lastKrw, ratio: parsed.value, maxSplits: currentMaxSplits(), mode: entryMode }) : "";
    var note = parsed.ok && parsed.value == null ? ratioEmptyNote(entryMode) : "";
    runNoteBox.textContent = runNote(snapshot ? snapshot.source : "") + (note ? " " + note : "");
    lastNote = note;
  }

  function render(status, assets, current, basic) {
    entryMode = String(status.mode_entry || status.mode_engine || "").toUpperCase();
    lastKrw = assets && assets.krw != null ? Number(assets.krw) : null;
    if (ratioInput && !ratioState.dirty) {
      var sv = savedRatio(current, entryMode);
      ratioInput.value = sv == null ? "" : String(sv);
    }
    refreshRatio();
    infoBox.textContent = "";
    var rows = stateRows(status, assets, basic, status.ticker);
    for (var i = 0; i < rows.length; i++) addKv(rows[i][0], rows[i][1]);
    if (status.mode_mismatch) {
      addSmall("경고", "입장 모드(" + (status.mode_entry || "?") + ")와 엔진 모드(" +
        (status.mode_engine || "?") + ")가 다릅니다.");
    }
    if (status.ticker) {
      addSmall("저장될 종목", status.ticker + " (엔진 현재 종목)");
    }
    var snapSrc = snapshot.params.src;
    addSmall("저장될 봉", srcText(snapSrc));
    var warn = intervalWarning(snapSrc, status.interval);
    if (warn) addSmall("경고", warn);
    var sw = symbolWarning(snapshot, status.ticker);
    if (sw) addSmall("경고", sw);
    var fw = floorWarning(snapshot.params);
    if (fw) addSmall("경고", fw);
    lastSavedSpan = addSmall("마지막 저장", lastSavedText(null, current));
    hasTicker = !!status.ticker;
    plan = runPlan(status, basic, snapshot.source);
    setMsg(hasTicker ? "" : "엔진 종목을 알 수 없어 저장할 수 없습니다");
    refreshButton();
  }

  function openDialog() {
    var g = gate.next();
    // 창을 여는 순간의 25개 값을 한 번 모은다(닫았다 다시 열면 새로 모음)
    snapshot = makeSnapshot(function (id) { return document.getElementById(id); });
    ratioState = { dirty: false, value: null };          // 창을 열 때마다 저장된 값을 다시 읽는다
    if (ratioInput) { ratioInput.value = ""; ratioErrBox.textContent = ""; ratioPreviewBox.textContent = ""; }
    dialog.hidden = false;
    var _tt = trailingText(snapshot);   // 1110-01: 저장될 추적 손절 설정도 함께 보인다
    testedBox.textContent = testedText(snapshot) + (_tt ? " · " + _tt : "");
    runBtn.textContent = runBtnLabel(snapshot.source);
    runNoteBox.textContent = runNote(snapshot.source);
    infoBox.textContent = "";
    setMsg("상태를 읽는 중…");
    preloaded = false;
    hasTicker = false;
    saved = false;
    lastSavedSpan = null;
    plan = "disabled";
    running = false;
    ran = false;
    lastSave = null;
    refreshButton();
    preloadAll(getJson).then(function (r) {
      if (!gate.isCurrent(g)) return;   // 더 최근에 연 미리 읽기가 있으면 버린다
      preloaded = true;
      render(r[0], r[1], r[2], r[3]);
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

  // 저장 성공이면 응답 본문, 아니면 null 로 끝나는 Promise. 이미 저장했으면 그 응답.
  function doSave() {
    if (saved && lastSave) return Promise.resolve(lastSave);
    if (saving || !preloaded || !hasTicker || saved || !snapshot) return Promise.resolve(null);
    // 1109: 투자 비율 칸이 형식에 맞지 않으면 보내지 않는다(서버도 같은 규칙으로 400 을 돌려준다)
    var rp = ratioInput ? ratioParse(ratioInput.value) : { ok: true, value: null };
    if (!rp.ok) { setMsg(rp.text); return Promise.resolve(null); }
    saving = true;
    refreshButton();
    setMsg("저장 중…");
    var status = 0;   // 25개 값은 창을 열 때 모은 스냅샷 그대로(투자 비율은 칸을 건드렸을 때만 더한다)
    var out = null;
    return fetch("/v2/api/params/save", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: bodyWithRatio(snapshot, { dirty: ratioState.dirty, value: rp.value }),
    }).then(function (r) {
      status = r.status;
      return r.json().catch(function () { return {}; });
    }).then(function (body) {
      setMsg(saveMessage(status, body));
      if (status === 200 && body.ok) {
        saved = true;   // 창을 닫을 때까지 다시 저장하지 못하게 한다(이력 중복 방지)
        ratioState.dirty = false;   // 입력한 비율은 저장됐다(창 안의 값은 그대로 보인다)
        lastSave = body;
        out = body;
        updateLastSaved(body);
      }
    }).catch(function () {
      setMsg("저장 결과를 확인하지 못했습니다 — 마지막 저장 시각을 다시 확인하세요");
    }).then(function () {
      saving = false;
      refreshButton();
      return out;
    });
  }

  function wait(ms) { return new Promise(function (res) { setTimeout(res, ms); }); }

  // 엔진 제어 요청 1건 → 결과(못 받으면 null). POST 실패는 문구를 띄우고 null.
  function sendControl(kind, payload) {
    var status = 0;
    return fetch("/v2/api/control", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind, payload: payload || {} }),
    }).then(function (r) {
      status = r.status;
      return r.json().catch(function () { return {}; });
    }).then(function (body) {
      if (status !== 202 || !body.id) { setMsg(controlPostText(status, body)); return null; }
      setMsg("엔진에 요청했습니다 — 결과를 기다리는 중…");
      return pollResult(getJson, wait, body.id).then(function (res) {
        setMsg(runResultText(res));
        return res ? { id: body.id, res: res } : null;
      });
    }).catch(function () { setMsg("요청을 보내지 못했습니다"); return null; });
  }

  function markApplied(save, sent) {
    if (!save || !sent || !sent.res || sent.res.status !== "done") return;
    fetch("/v2/api/params/applied", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history_id: save.history_id, request_id: sent.id }),
    }).catch(function () {});
  }

  function applyNow(save) {
    return sendControl("apply_params", { saved_sha256: save.saved_sha256 }).then(function (sent) {
      markApplied(save, sent);
    });
  }

  function doRun() {
    if (running || ran || plan === "disabled" || !snapshot || snapshot.source !== "upbit") return;
    running = true;
    refreshButton();
    doSave().then(function (save) {
      if (!save || !save.saved_sha256) return null;
      if (plan === "switch") {
        if (!window.confirm(switchConfirmText(entryMode))) { setMsg("저장만 했습니다. 전환하지 않았습니다."); return null; }
        return sendControl("switch", { saved_sha256: save.saved_sha256 });
      }
      if (plan === "ask_start") {
        if (!window.confirm(START_CONFIRM)) {
          setMsg("저장만 했습니다. 엔진을 시작한 뒤 다시 눌러 주세요.");
          return null;
        }
        return sendControl("engine_start", {}).then(function (sent) {
          if (sent && sent.res && sent.res.status === "done") return applyNow(save);
          return null;
        });
      }
      return applyNow(save);
    }).then(function () {
      ran = true;      // 창을 닫을 때까지 다시 보내지 않는다(겹친 요청 방지)
    }, function () {
      setMsg("결과를 확인하지 못했습니다");
    }).then(function () {
      running = false;
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
    testedBox = document.getElementById("saveTested");
    runBtn = document.getElementById("saveRunBtn");
    runNoteBox = document.getElementById("saveRunNote");
    if (!openBtn || !dialog || !infoBox || !msgBox || !doBtn || !closeBtn ||
        !testedBox || !runBtn || !runNoteBox) return;
    buildRatioField();
    openBtn.addEventListener("click", openDialog);
    closeBtn.addEventListener("click", closeDialog);
    doBtn.addEventListener("click", function () { doSave(); });
    runBtn.addEventListener("click", doRun);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
