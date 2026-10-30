// v2 화면 (Alpine). 일반 script 로 읽고 alpine:init 에서 등록한다.
// 차트 이동평균선(그림 2-나): 60선·200선. 200선은 봉 400개가 모인 뒤 그린다(chart.js visiblePeriods).
const CHART_PERIODS = [60, 200];
const CHART_TARGET_CANDLES = 400;   // 처음 그릴 때 200봉 2회로 모으는 목표(기본 60·200 선)
const CHART_TARGET_MAX = 2000;      // 2차 T16 (결정 1030-02 U1): 2 × 가장 긴 기간, 최대 2000봉(요청 최대 10회)
const EMA_LINE_NOTE = "지수이동평균(EMA) 선은 화면에 받은 봉으로 계산해 엔진 값과 조금 다를 수 있습니다.";

function _posInt(v, d) { return Number.isInteger(v) && v > 0 ? v : d; }

// 2차 T16: 차트 선 설정(순수 함수). 새 전략(status.pullback)이면 적용본 기간·방식, 그 밖은 1차 그대로(60·200 단순).
// pullbackP 가 60선 기간과 다를 때만 기준선(pull)을 하나 더(U3). target = 받을 봉 수(U1).
function chartLines(status) {
  const pb = status && status.pullback;
  if (!pb) {
    return { lines: CHART_PERIODS.slice(), maType: "sma", target: CHART_TARGET_CANDLES, legend: null, note: "",
      caption: "", sig: "base" };
  }
  const a = _posInt(pb.ma60p, 60), b = _posInt(pb.ma200p, 200), p = _posInt(pb.pullbackP, a);
  const lines = [{ period: a, slot: "trend" }, { period: b, slot: "long" }];
  if (p !== a) lines.push({ period: p, slot: "pull" });
  const maType = pb.maType === "ema" ? "ema" : "sma";
  const longest = Math.max(...lines.map((l) => l.period));
  const target = Math.min(CHART_TARGET_MAX, Math.max(CHART_TARGET_CANDLES, 2 * longest));
  return { lines, maType, target, legend: { a: a + "선", b: b + "선", pull: p !== a ? p + "선(기준선)" : "" },
    note: maType === "ema" ? EMA_LINE_NOTE : "",
    caption: "캔들, " + a + "선·" + b + "선" + (p !== a ? ", " + p + "선(눌림목 기준선)" : "(눌림목 기준선)") +
      ", 봇이 실제로 사고판 자리. 손가락으로 확대·이동합니다.",
    sig: [a, b, p, maType].join(",") };
}

// 2차 T16: 퍼센트 표기(5 → 「5」, 1.5 → 「1.5」)
function _pct(v) { return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 2 }); }

// 2차 T16: 예약 배지 문구(운용 탭 ops.js reservationText 와 같은 구분 — 복귀 예약은 「복귀 예약 중」)
function reservationBadgeText(res) {
  if (!res) return "";
  return res.kind === "REVERT" ? "복귀 예약 중" : "전환 예약 중";
}
const GATE_KEY = "v2.upbitGateAt";

// localStorage 접근이 막힌 환경(시크릿 창 등)에서도 오류 없이 — 없으면 null(문은 메모리로 대신)
function safeLocalStorage() {
  try { return window.localStorage || null; } catch (e) { return null; }
}

// 주소 #탭 → 탭 이름. 모르는 값·#backtester(별도 페이지)는 home.
function tabFromHash(hash) {
  const name = String(hash || "").replace(/^#/, "");
  return ["home", "chart", "logs", "ops"].includes(name) ? name : "home";
}

// ---- 홈 표시 계산 (그림 2-가). DOM 을 만지지 않는 순수 함수 — node 시험이 검사한다 ----
const _KST_MS = 9 * 3600 * 1000;
const _p2 = (n) => String(n).padStart(2, "0");
const _won = (n) => Math.round(n).toLocaleString("ko-KR");   // 원화 금액(평가 합계·원화·손익)은 정수
// 코인 가격 표기: 크기별 고정 소수 자리(100원 미만 종목도 값이 보이게), 천 단위 쉼표
function priceText(p) {
  const a = Math.abs(p);
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4;
  return Number(p).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
}
// 현재가 시각: 오늘이면 HH:MM, 아니면 MM-DD HH:MM, 없으면 ""
function _priceTime(iso, nowMs) {
  const p = iso ? _kstParts(iso) : null;
  if (!p) return "";
  return p.day === _kstDay(nowMs) ? p.h + ":" + p.mi : p.mo + "-" + p.da + " " + p.h + ":" + p.mi;
}
// 사유·실패 조건 표는 labels.js(모듈) — index.html 이 window.v2Labels 로 올린다
function _labels() {
  return window.v2Labels || { reasonLabel: (c) => String(c == null ? "" : c), failedKeysText: (r) => String(r == null ? "" : r) };
}
// ISO -> KST 부품. 해석 못 하면 null.
function _kstParts(iso) {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  const d = new Date(t + _KST_MS);
  return { day: Math.floor((t + _KST_MS) / 86400000), mo: _p2(d.getUTCMonth() + 1), da: _p2(d.getUTCDate()),
    h: _p2(d.getUTCHours()), mi: _p2(d.getUTCMinutes()), s: _p2(d.getUTCSeconds()) };
}
function _kstDay(ms) { return Math.floor((ms + _KST_MS) / 86400000); }
// 오늘이면 HH:MM:SS, 아니면 MM-DD HH:MM, 값 없으면 —
function _recordTime(iso, nowMs) {
  const p = iso ? _kstParts(iso) : null;
  if (!p) return "—";
  return p.day === _kstDay(nowMs) ? p.h + ":" + p.mi + ":" + p.s : p.mo + "-" + p.da + " " + p.h + ":" + p.mi;
}

const _STRATEGY_NAMES = { EMA: "EMA (기존)", MACD: "MACD (기존)", PULLBACK: "눌림목 분할매수" };

// 엔진 배지: 글자와 색을 한 곳에서 정한다(멈춘 엔진이 초록으로 보이지 않게).
function engineBadge(status, basic) {
  const running = basic ? basic.engine_running : undefined;
  if (running === false) return { id: "engine-badge", text: "엔진 멈춤", cls: "p-off" };
  if (running !== true) return { id: "engine-badge", text: "엔진 확인 중", cls: "p-off" };
  const level = status && status.engine ? status.engine.level : undefined;
  if (level === "ok") return { id: "engine-badge", text: "엔진 동작 중", cls: "p-run" };
  if (level === "delay") return { id: "engine-badge", text: "엔진 동작 중 · 판단 지연", cls: "p-warn" };
  return { id: "engine-badge", text: "엔진 동작 중 · 판단 보류", cls: "p-off" };
}

function homeView(status, assets, basic, nowMs, ctl) {
  nowMs = nowMs == null ? Date.now() : nowMs;
  const st = status || {};
  const a = assets || {};
  const mode = String(st.mode_engine || "").toUpperCase();
  const strat = String(st.strategy && st.strategy.value || "").toUpperCase();
  const badges = [
    mode === "LIVE" || mode === "TEST" ? { id: "mode-badge", text: mode, cls: "p-live" }
      : { id: "mode-badge", text: "모드 확인 불가", cls: "p-off" },
    engineBadge(status, basic),
    { id: "strategy-badge", text: "전략: " + (_STRATEGY_NAMES[strat] || strat || "—"), cls: "p-st" },
    st.paused ? { id: "pause-badge", text: "일시정지 중", cls: "p-warn" }
      : { id: "pause-badge", text: "일시정지 아님", cls: "p-off" },
  ];
  // 2차 T16: 예약이 있을 때만 「전환 예약 중」(노랑) — 전략 배지 바로 뒤. 예약 없으면 배지 4개 그대로
  const res = ctl && ctl.reservation;
  if (res) badges.splice(3, 0, { id: "reserve-badge", text: reservationBadgeText(res), cls: "p-warn" });
  const pb = st.pullback || null;

  const krw = Number(a.krw), coin = Number(a.coin), price = Number(a.price), entry = Number(a.entry_price);
  const hasKrw = assets && a.krw != null && Number.isFinite(krw);
  const coinVal = Number.isFinite(coin) && Number.isFinite(price) && a.price != null ? coin * price : null;
  const total = hasKrw ? _won(krw + (coinVal || 0)) + "원" : "—";
  const krwCoin = hasKrw ? _won(krw) + " / " + _won(coinVal || 0) : "—";

  let pnl = { text: "—", cls: "" };
  if (coin > 0 && entry > 0 && price > 0) {
    const amt = (price - entry) * coin;
    const pct = (price / entry - 1) * 100;
    const sign = amt > 0 ? "+" : (amt < 0 ? "-" : "");
    const psign = pct > 0 ? "+" : (pct < 0 ? "-" : "");
    pnl = { text: sign + _won(Math.abs(amt)) + " (" + psign + Math.abs(pct).toFixed(1) + "%)",
      cls: amt > 0 ? "up" : (amt < 0 ? "dn" : "") };
  }

  const kl = Number(a.krw_locked) || 0, cl = Number(a.coin_locked) || 0;
  const num8 = (v) => Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 8 });
  const locked = { text: _won(kl) + " / " + num8(cl), warn: kl !== 0 || cl !== 0 };
  const pt = _priceTime(a.price_at, nowMs);
  const recorded = "기록 시각 " + _recordTime(a.updated_at, nowMs) + " · 현재가 " +
    (a.price != null && price > 0 ? priceText(price) + "원" : "—") + (pt ? " " + pt : "") + " 엔진 기록";

  let holding = null;
  if (coin > 0 || cl > 0) {
    const pctText = (p) => {
      if (!(entry > 0) || !(p > 0)) return "";
      const v = (p / entry - 1) * 100;
      return " (" + (v > 0 ? "+" : (v < 0 ? "-" : "")) + Math.abs(v).toFixed(1) + "%)";
    };
    const won = (p) => (p > 0 ? priceText(p) + "원" : "—");
    // 2차 T16: 분할 회차 「2 / 5회」(새 전략), EMA·MACD 는 「—」. 익절·손절 % 는 새 전략 적용본 값(그림 2-가)
    const r = a.round;
    const roundText = r && typeof r === "object" && Number.isInteger(r.entry) && Number.isInteger(r.max)
      ? r.entry + " / " + r.max + "회" : "—";
    const pbPct = (v, sign) => (pb && Number.isFinite(Number(v)) && v !== null ? " (" + sign + _pct(v) + "%)" : null);
    const tpL = pbPct(pb && pb.tp, "+"), slL = pbPct(pb && pb.sl, "-");
    holding = {
      ticker: st.ticker || "—",
      round: roundText,
      avg: won(entry),
      tp: { label: "익절 가격" + (tpL !== null ? tpL : pctText(Number(a.tp_price))), price: won(Number(a.tp_price)) },
      sl: { label: "손절 가격" + (slL !== null ? slL : pctText(Number(a.sl_price))), price: won(Number(a.sl_price)) },
    };
  }
  return { badges, total, krwCoin, pnl, locked, recorded, holding };
}

// 2차 T16: 새 전략 최신 신호 문장(그림 2-가). 우선순위: 매도 발동 > 예약 > 어긋남 > 회차 다 참 > 눌림(armed)
// > 감시 구간 안 > 감시 구간 밖 > 그 밖 판정 키. 「N선」 = 눌림은 pullbackP, 감시 구간은 ma60p·ma200p.
const _INACTIVE_TEXT = { not_golden: (a, b) => a + "선 ≤ " + b + "선", slope_low: (a, b) => b + "선 기울기 낮음",
  slope_drop: (a, b) => b + "선 기울기 둔화" };
function pullbackSentence(row, ctx) {
  const c = ctx || {};
  const cfg = c.pb || {};
  const s = row.pb || {};
  const L = _labels();
  const a = _posInt(cfg.ma60p, 60), b = _posInt(cfg.ma200p, 200), p = _posInt(cfg.pullbackP, a);
  const holding = c.holding === true || row.kind === "sell" || s.holding === 1;
  const rnd = c.round && typeof c.round === "object" ? c.round : null;
  const next = Number.isInteger(s.round) && s.round >= 0 ? s.round + 1 : (rnd && Number.isInteger(rnd.entry) ? rnd.entry + 1 : null);
  if (c.reservation) return (c.reservation.kind === "REVERT" ? "복귀 예약 중" : "전환 예약 중") + " — 봇 추가 매수 안 함";
  if (holding && rnd && rnd.desync) return "보유 유지 — 앱 주문이 섞여 추가 매수를 멈췄습니다. 익절·손절은 그대로";
  if (row.kind === "buy" && row.overall_ok) return "매수 조건 충족";
  const key = s.state;
  if (key === "SPLITS_FULL") {
    const n = rnd && Number.isInteger(rnd.max) ? rnd.max : (Number.isInteger(s.round) ? s.round : null);
    return "보유 유지 — 분할 " + (n === null ? "" : n + " / " + n + "회 ") + "모두 매수함. 익절·손절 가격 안";
  }
  if (key === "WAIT_PULLBACK" && next !== null) {
    if (s.armed === 1) return "눌림 대기 중 — 가격이 " + p + "선 아래로 내려옴. 다시 위에서 마감하면 " + next + "회차 매수";
    return "매수 대기 — 가격이 " + p + "선 위. " + p + "선 아래로 내려왔다가 다시 위에서 마감하면 " + next + "회차 매수";
  }
  if (key === "NOT_ACTIVE") {
    if (holding) return "보유 유지 — 감시 구간 밖. 익절·손절 가격 안";
    const why = _INACTIVE_TEXT[s.inactive_reason];
    return "매수 대기 — 감시 구간 아님" + (why ? " (" + why(a, b) + ")" : "");
  }
  const label = key ? L.failedKeysText([key]) : "";
  if (holding) return "보유 유지 — " + (label ? label + ". " : "") + "익절·손절 가격 안";
  return "매수 대기" + (label ? " — " + label : "");
}

function signalSentence(row, ctx) {
  if (!row) return { title: "최신 신호", text: "신호 기록이 없습니다" };
  const p = _kstParts(row.bar_time || row.timestamp);
  const title = "최신 신호" + (p ? " · " + p.h + ":" + p.mi + " 봉" : "");
  const L = _labels();
  let text;
  if (row.kind === "sell" && row.triggered) {
    const why = L.reasonLabel(row.trigger_key);
    text = "매도" + (why ? " — " + why : "");
  } else if (row.pb) {
    text = pullbackSentence(row, ctx);
  } else if (ctx && ctx.reservation) {
    // 2차 T16: 예약 중(기존 전략 운용 중 전환 예약) — 봇 자동 매수 막힘(T12)
    text = (ctx.reservation.kind === "REVERT" ? "복귀 예약 중" : "전환 예약 중") + " — 봇 추가 매수 안 함";
  } else if (row.kind === "sell") {
    if (row.triggered) {
      const why = L.reasonLabel(row.trigger_key);
      text = "매도" + (why ? " — " + why : "");
    } else {
      text = "보유 유지 — 익절·손절 가격 안";
    }
  } else if (row.overall_ok) {
    text = "매수 조건 충족";
  } else {
    const why = L.failedKeysText(row.failed_keys);
    text = "매수 대기" + (why ? " — " + why : "");
  }
  return { title, text };
}

// 최근 거래·로그 표의 시각 열: 오늘 HH:MM, 어제 「어제」, 그 전 MM-DD, 해석 못 하면 —
function logTime(iso, nowMs) {
  nowMs = nowMs == null ? Date.now() : nowMs;
  const p = iso ? _kstParts(iso) : null;
  if (!p) return "—";
  const diff = _kstDay(nowMs) - p.day;
  return diff === 0 ? p.h + ":" + p.mi : (diff === 1 ? "어제" : p.mo + "-" + p.da);
}

function tradeRow(t, nowMs) {
  nowMs = nowMs == null ? Date.now() : nowMs;
  const type = String(t.type || "").toUpperCase();
  let kind, kindCls;
  if (type === "BUY") { kind = "매수"; kindCls = "up"; }
  else if (type === "SELL") { kind = "매도"; kindCls = "dn"; }
  else if (type.endsWith("_REJECTED")) { kind = "거절"; kindCls = "muted"; }
  else if (type === "HTS_SELL") { kind = "외부 매도"; kindCls = "dn"; }
  else if (type === "BUY_CANCELED") { kind = "매수 취소"; kindCls = "muted"; }
  else { kind = String(t.type || "—"); kindCls = "muted"; }
  // 2차 T16: 새 전략 회차 매수 「매수 2회」(그림 2-가), 회차 건너뜀은 사유에 원인(「원화 잔고 부족」)
  if (type === "BUY" && Number.isInteger(t.round)) kind = "매수 " + t.round + "회";
  const time = logTime(t.timestamp, nowMs);
  const price = Number(t.price), qty = Number(t.qty);
  const amount = price > 0 && qty > 0 ? _won(price * qty) : "—";
  const reason = t.skip_reason ? String(t.skip_reason) : _labels().reasonLabel(t.reason);
  return { time, kind, kindCls, reason, amount };
}

document.addEventListener("alpine:init", () => {
  Alpine.data("dash", () => {
    // 차트 관련 상태는 반응형 밖(클로저)에 둔다. Alpine 은 x-data 객체에서 꺼낸 값을
    // 반응형 프록시로 감싸 돌려주므로, 거기 넣은 객체를 `===` 로 비교하면 항상 어긋난다.
    // 콜백이 아직 유효한지는 원시값 세대 번호(gen)로 확인한다.
    const C = { gen: 0, poller: null, view: null, key: "", cache: null, store: null, gate: null, retryTimer: null };
    return {
    tab: "home",
    status: null, assets: null, basic: null, trades: [], signals: [],
    // 2차 T16: 예약 상태(GET /v2/api/control/state — 입장 모드로 거른 예약). 못 읽으면 null(배지 없음)
    ctl: null,
    // 로그 탭(그림 2-라): 종류 토글 · 12행씩 쪽 이동
    logsKind: "audit", logRows: [], logsPage: 1, logsPages: 1, logsMore: false, logsLoaded: false, _logsSeq: 0,
    authError: false, netError: "", chartFail: "", chartNote: "",
    _cardTimer: null, _cardsBusy: false,
    // 운용 탭(2차 T14): GET /v2/api/ops 값·요청 처리 중·결과 문구·복귀 전략 고르기·운용 설정 입력
    ops: null, opsBusy: false, opsMsg: "", opsChoose: false, opsDirty: false,
    opsForm: { enable: false, start: "09:00", end: "02:00", sellOff: true },

    // ---- 시작·갱신 ---- (Alpine 이 x-data 의 init 을 자동 호출한다)
    init() {
      this.refreshCards();
      // 주소 #탭 으로 들어오면 그 탭을 연다(백테스터 → 아래 메뉴로 돌아올 때)
      const first = tabFromHash(window.location && window.location.hash);
      if (first !== "home") this.go(first);
      window.addEventListener("hashchange", () => {
        const t = tabFromHash(window.location.hash);
        if (t !== this.tab) this.go(t);
      });
      // 업비트는 브라우저 요청을 10초당 1회로 제한 — poller 가 바뀌어도, 창이 여럿이어도 간격을 지킨다
      C.gate = window.v2Chart ? window.v2Chart.createSharedRateGate(10000, safeLocalStorage(), GATE_KEY) : null;
      this._cardTimer = setInterval(() => {
        if (!document.hidden) this.refreshCards();
      }, 7000);
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) this.refreshCards();
      });
    },

    async getJson(path) {
      const r = await fetch(path, { credentials: "same-origin", cache: "no-store" });
      if (r.status === 401 || r.status === 403) {
        this.authError = true;
        throw new Error("auth");
      }
      if (!r.ok) throw new Error("http " + r.status);
      this.authError = false;
      return r.json();
    },

    async refreshCards() {
      if (document.hidden || this._cardsBusy) return;
      this._cardsBusy = true;
      try { await this._refreshCards(); } finally { this._cardsBusy = false; }
      // status 가 늦게 도착했을 때 열려 있는 차트 탭을 그린다
      if (this.tab === "chart" && window.v2Chart) {
        const st = this.status;
        const unit = st && st.ticker ? window.v2Chart.intervalToMinutes(st.interval) : null;
        const key = st && st.ticker ? st.ticker + "|" + unit + "|" + chartLines(st).sig : "";
        // poller 가 없거나 종목·봉 단위가 바뀌었으면 다시 시작
        if (!C.poller || (key && key !== C.key)) this.startChart();
      }
    },

    async _refreshCards() {
      const jobs = [
        ["/v2/api/status", (d) => { this.status = d; }],
        ["/v2/api/assets", (d) => { this.assets = d; }],
        ["/v2/api/basic", (d) => { this.basic = d; }],
        ["/v2/api/trades?limit=10", (d) => { this.trades = d.trades || []; }],
        ["/v2/api/signals?limit=1", (d) => { this.signals = d.signals || []; }],
      ];
      if (this.tab === "ops") jobs.push(["/v2/api/ops", (d) => { this.setOps(d); }]);
      let failed = 0;
      // 2차 T16: 예약 배지·문장용. 실패해도 안내 띠(netError)는 띄우지 않고 배지만 뺀다
      const ctlJob = (async () => {
        try { this.ctl = await this.getJson("/v2/api/control/state"); } catch (e) { this.ctl = null; }
      })();
      await Promise.all(jobs.map(async ([path, apply]) => {
        try { apply(await this.getJson(path)); } catch (e) { failed += 1; }
      }).concat([ctlJob]));
      this.netError = (failed && !this.authError) ? "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다." : "";
    },

    // ---- 탭 ----
    go(name) {
      this.tab = name;
      if (name === "chart") this.startChart(); else this.stopChart();
      if (name === "logs") this.loadLogs(1);
      if (name === "ops") this.loadOps();
      // 주소에 탭을 남긴다(백테스터 페이지에서 메뉴로 돌아오거나 새로고침해도 같은 탭)
      try { history.replaceState(null, "", "#" + name); } catch (e) { /* 주소 갱신 실패는 화면에 영향 없음 */ }
    },

    async setLogsKind(kind) {
      if (!["audit", "engine", "error"].includes(kind)) return;
      this.logsKind = kind;
      // 이전 종류의 행이 새 토글 아래 남지 않게 비우고 불러오는 중으로 둔다
      this.logRows = [];
      this.logsLoaded = false;
      this.logsPage = 1;
      this.logsPages = 1;
      this.logsMore = false;
      await this.loadLogs(1);
    },

    async loadLogs(page) {
      if (page < 1 || page > Math.max(1, this.logsPages)) return;
      const kind = this.logsKind;
      const seq = ++this._logsSeq;
      try {
        const d = await this.getJson("/v2/api/logs?kind=" + kind + "&page=" + page);
        // 그 사이 종류·쪽이 또 바뀌었으면 이 응답은 버린다
        if (seq !== this._logsSeq) return;
        const now = Date.now();
        this.logRows = (d.rows || []).map((r) => ({
          id: r.id, time: logTime(r.timestamp, now), text: r.text, cls: r.cls || "" }));
        this.logsPage = d.page || page;
        this.logsPages = d.pages || 1;
        this.logsMore = d.more === true;
        this.logsLoaded = true;
      } catch (e) { /* authError 또는 네트워크 — 머리말에 표시됨 */ }
    },
    get logsRange() { return this.logsPage + " / " + this.logsPages + (this.logsMore ? "+" : ""); },
    get logsEmpty() { return this.logsLoaded && this.logRows.length === 0; },

    // ---- 운용 탭 (2차 T14) — 판정·문구는 ops.js(window.__v2ops) 순수 함수 ----
    setOps(d) {
      this.ops = d;
      // 입력 중이 아니면 지금 적용본 값으로 칸을 맞춘다
      if (!this.opsDirty && window.__v2ops) this.opsForm = window.__v2ops.opsForm(d && d.hours);
    },
    async loadOps() {
      try { this.setOps(await this.getJson("/v2/api/ops")); } catch (e) { /* 머리말에 표시됨 */ }
    },
    get opsCtx() {
      const st = this.status || {}, a = this.assets || {}, o = this.ops || {};
      const coin = Number(a.coin) || 0, cl = Number(a.coin_locked) || 0;
      return {
        strategy: String(st.strategy && st.strategy.value || o.strategy || "").toUpperCase(),
        opsLoaded: !!this.ops, reservation: o.reservation || null, reservationError: o.reservation_error === true,
        savedOk: !!(o.saved && o.saved.ok), engineRunning: this.basic ? this.basic.engine_running : undefined,
        holding: coin > 0 || cl > 0, round: o.round || null, perBuy: o.per_buy, orderRatio: o.order_ratio,
        krw: a.krw, busy: this.opsBusy || !!o.pending,
        // fix 1: 입장 모드(LIVE 이면 전환·복귀·운용 설정 저장을 닫음)
        mode: String(o.mode || st.mode_entry || "").toUpperCase(),
      };
    },
    get opsLiveNote() {
      const O = window.__v2ops;
      return O ? O.liveNote(this.opsCtx.mode) : "";
    },
    get opsView() {
      const O = window.__v2ops;
      if (!O) {
        const off = { enabled: false, label: "" };
        return { switch: off, revert: off, cancel: off, pause: off, stop: off, start: off, forceBuy: off,
          forceSell: off, opsSave: off };
      }
      return O.buttonStates(this.opsCtx);
    },
    get opsReservationText() {
      const O = window.__v2ops, o = this.ops || {};
      return O ? O.reservationText(o.reservation, o.reservation_error === true) : "";
    },
    async postJson(path, body) {
      const r = await fetch(path, { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      let data = {};
      try { data = await r.json(); } catch (e) { data = {}; }
      return { status: r.status, ok: r.ok, body: data };
    },
    // 엔진 제어 요청 1건: 보내기 → 2초마다 60초까지 결과 → 문구 → 상태 다시 읽기
    async opsSend(kind, payload) {
      const O = window.__v2ops;
      this.opsBusy = true;
      try {
        const r = await this.postJson("/v2/api/control", { kind, payload: payload || {} });
        if (!r.ok) { this.opsMsg = O.postErrorText(r.status, r.body); return null; }
        this.opsMsg = "요청을 보냈습니다. 엔진 결과를 기다립니다…";
        const wait = (ms) => new Promise((res) => setTimeout(res, ms));
        const res = await O.pollResult((p) => this.getJson(p), wait, r.body.id);
        this.opsMsg = O.resultText(res);
        if (res && res.code === "choose_strategy") this.opsChoose = true;
        if (kind === "ops_settings" && res && res.status === "done") this.opsDirty = false;
        return res;
      } catch (e) {
        this.opsMsg = O.postErrorText(0, {});
        return null;
      } finally {
        this.opsBusy = false;
        await this.loadOps();
        this.refreshCards();
      }
    },
    async opsAct(name) {
      const O = window.__v2ops;
      if (!O || this.opsBusy) return;
      const view = this.opsView[name];
      if (!view || !view.enabled) return;
      const o = this.ops || {};
      const ask = (text) => window.confirm(text);
      if (name === "switch") {
        if (!ask(O.CONFIRM.switch)) return;
        return this.opsSend("switch", { saved_sha256: o.saved && o.saved.sha256 });
      }
      if (name === "revert") {
        const text = O.revertConfirmText(o.revert_target);
        if (text === null) { this.opsChoose = true; this.opsMsg = O.CONFIRM.chooseStrategy; return; }
        if (!ask(text)) return;
        return this.opsSend("revert", {});
      }
      if (name === "cancel") { if (ask(O.CONFIRM.cancel)) return this.opsSend("cancel_reservation", {}); return; }
      if (name === "stop") { if (ask(O.CONFIRM.stop)) return this.opsSend("engine_stop", {}); return; }
      if (name === "start") {
        if (ask("엔진을 시작할까요? (모드: " + (this.modeLabel || "확인 불가") + ")")) return this.opsSend("engine_start", {});
        return;
      }
      if (name === "forceBuy") {
        if (ask(O.forceBuyConfirmText(this.opsCtx))) return this.opsSend("force_buy", {});
        return;
      }
      if (name === "forceSell") { if (ask(O.CONFIRM.forceSell)) return this.opsSend("force_sell", {}); return; }
      if (name === "opsSave") {
        // 1029-09: 「시간 밖에도 익절」도 입력 칸 값을 보낸다(형식이 틀리면 null)
        const payload = O.opsPayload(this.opsForm);
        if (payload === null) { this.opsMsg = "시작·끝 시각을 HH:MM 으로 넣어 주세요."; return; }
        if (ask(O.CONFIRM.opsSave)) return this.opsSend("ops_settings", payload);
        return;
      }
      if (name === "pause") {
        // 홈 단추와 같은 동작(POST /v2/api/pause). 이미 일시정지면 보내지 않는다(재개는 홈 화면 위 단추).
        if (this.status && this.status.paused) { this.opsMsg = "이미 일시정지 중입니다. 재개는 홈 화면 위 단추로 합니다."; return; }
        if (!ask(O.CONFIRM.pause)) return;
        this.opsBusy = true;
        try {
          const r = await this.postJson("/v2/api/pause", { paused: true });
          this.opsMsg = r.ok ? "매매를 일시정지했습니다." : O.postErrorText(r.status, r.body);
        } catch (e) {
          this.opsMsg = O.postErrorText(0, {});
        } finally {
          this.opsBusy = false;
          this.refreshCards();
        }
      }
    },
    async opsRevertTo(strategy) {
      const O = window.__v2ops;
      if (!O || this.opsBusy || !["EMA", "MACD"].includes(strategy)) return;
      if (!window.confirm(strategy + " 로 돌아갑니다. 지금 보유분이 있으면 새 전략 매도 규칙으로 판 뒤 바뀝니다. 진행할까요?")) return;
      this.opsChoose = false;
      return this.opsSend("revert", { strategy });
    },

    // ---- 차트 ----
    startChart() {
      const st = this.status;
      const mod = window.v2Chart;
      if (!mod || !st || !st.ticker) return;
      this.stopChart();
      const unitMin = mod.intervalToMinutes(st.interval);
      if (unitMin === null) {
        this.chartNote = "이 봉 단위는 1차 차트에서 지원하지 않습니다";
        return;
      }
      this.chartNote = "";
      const spec = chartLines(st);   // 2차 T16: 새 전략이면 적용본 기간·방식·받을 봉 수
      const key = st.ticker + "|" + unitMin + "|" + spec.sig;
      if (C.key !== key || !C.view) {
        if (C.view) { C.view.destroy(); C.view = null; }
        document.getElementById("chart").innerHTML = "";
        C.view = mod.createChartView(document.getElementById("chart"));
        C.key = key;
      }
      if (!C.view.ok) return;   // 라이브러리 없음: 화면에 안내 문구가 이미 있다
      const markersPath = "/v2/api/markers";
      if (!C.gate && mod.createSharedRateGate) C.gate = mod.createSharedRateGate(10000, safeLocalStorage(), GATE_KEY);
      // 종목·봉 단위별로 받은 봉(오름차순)을 모아 둔다 — 늦게 끝난 옛 요청은 옛 보관함에만 쓴다
      if (!C.store || C.store.key !== key) C.store = { key, candles: [], olderDone: false };
      const store = C.store;
      const gen = ++C.gen;
      const draw = (d) => {
        const asc = mod.markFormingCandle(d.candles, Date.now(), unitMin * 60);
        C.view.update(asc, d.markers, spec.lines, unitMin * 60, spec.maType);
      };
      // 보관한 같은 키의 데이터가 있으면 즉시 그린다
      if (C.cache && C.cache.key === key) draw(C.cache);
      const poller = mod.createPoller({
        fetchFn: async () => {
          if (C.gate && !C.gate.allow()) {
            // 10초 안: 게이트가 열릴 때 한 번 다시 시도(겹침·숨김은 poller.tick 이 처리)
            clearTimeout(C.retryTimer);
            C.retryTimer = setTimeout(() => {
              if (C.gen === gen) poller.tick();
            }, C.gate.msUntilOpen() + 50);
            return null;
          }
          // 최신 200봉 → 이어서 가장 오래된 봉 이전 200봉(to=)으로 400봉까지, 그 뒤엔 최신 200봉만
          const wantOlder = store.candles.length > 0 && store.candles.length < spec.target && !store.olderDone;
          const toIso = wantOlder ? store.candles[0].candle_date_time_utc + "Z" : undefined;
          const r = await fetch(mod.upbitCandlesUrl(st.ticker, unitMin, toIso));
          if (!r.ok) { const e = new Error("upbit " + r.status); e.status = r.status; throw e; }   // 429 도 이 회는 실패, 30초 뒤 다시
          const fetched = mod.toAscending(await r.json());
          const had = store.candles.length;
          store.candles = mod.mergeCandles(store.candles, fetched);
          if (wantOlder && store.candles.length === had) store.olderDone = true;   // 더 오래된 봉 없음(신규 상장 등)
          let markers = [];
          try { markers = (await this.getJson(markersPath)).markers || []; } catch (e) { /* 표식 실패는 차트 실패가 아님 */ }
          return {
            candles: store.candles.slice(), markers,
            more: store.candles.length < spec.target && !store.olderDone,
          };
        },
        intervalMs: 30000,
        isHidden: () => document.hidden,
        onData: (data) => {
          if (!data) return;   // 게이트에 막혀 건너뜀
          C.cache = { key, candles: data.candles, markers: data.markers };   // 교체된 poller 의 응답도 보관
          if (C.gen !== gen || C.key !== key) return;   // 그리기만 막는다
          draw(C.cache);
          this.chartFail = "";
          if (data.more && C.gate) {
            // 400봉이 덜 모였으면 문이 열릴 때(10초 뒤) 이어서 받는다
            clearTimeout(C.retryTimer);
            C.retryTimer = setTimeout(() => {
              if (C.gen === gen) poller.tick();
            }, C.gate.msUntilOpen() + 50);
          }
        },
        onError: (time) => {
          if (C.gen !== gen) return;
          this.chartFail = "갱신 실패 · " + mod.kstTime(time);
        },
      });
      C.poller = poller;
      poller.start();
    },

    stopChart() {
      clearTimeout(C.retryTimer);
      C.gen += 1;   // 멈춘 poller 의 늦은 콜백을 무효화
      if (C.poller) { C.poller.stop(); C.poller = null; }
    },

    // ---- 표시 도우미 ----
    // 차트 단추 줄 첫 칸(표시용): 엔진 봉 단위 「3분」
    get chartUnitLabel() {
      const m = window.v2Chart && this.status ? window.v2Chart.intervalToMinutes(this.status.interval) : null;
      return m === null || m === undefined ? "—" : m + "분";
    },
    // 확대(+)·축소(−): 보이는 범위를 1.5배 조절
    zoomChart(factor) {
      if (C.view && window.v2Chart) window.v2Chart.zoom(C.view, factor);
    },
    // 머리 막대: 홈 밖 탭 제목·오른쪽 모드, 홈의 표시 이름
    get tabTitle() {
      if (this.tab === "chart") {
        const s = this.status;
        // 봉 단위는 단추 줄 첫 칸과 같은 표기(「3분」)
        return "차트" + (s && s.ticker ? " · " + s.ticker + " · " + this.chartUnitLabel : "");
      }
      return this.tab === "logs" ? "로그" : (this.tab === "ops" ? "운용" : "신버전 대시보드");
    },
    get modeLabel() {
      const m = String(this.status && this.status.mode_engine || "").toUpperCase();
      return m === "LIVE" || m === "TEST" ? m : "";
    },
    get displayName() {
      return (this.basic && (this.basic.display_name || this.basic.account)) || "";
    },
    // 운용 탭 「지금 전략」 — 배지와 같은 이름표
    get strategyLabel() {
      const v = String(this.status && this.status.strategy && this.status.strategy.value || "").toUpperCase();
      return _STRATEGY_NAMES[v] || v || "—";
    },
    get modeText() {
      const s = this.status;
      if (!s) return "모드 —";
      return "모드 " + (s.mode_engine || "확인 불가");
    },
    // 홈 화면 한 덩어리 (배지·자산·보유). 계산은 위 homeView
    get home() { return homeView(this.status, this.assets, this.basic, undefined, this.ctl); },
    get signalCard() { return signalSentence(this.signals[0], this.signalCtx); },
    // 2차 T16: 최신 신호 문장 재료(새 전략 값·회차·예약·보유)
    get signalCtx() {
      const a = this.assets || {};
      return { pb: this.status && this.status.pullback, round: a.round || null,
        reservation: this.ctl && this.ctl.reservation, holding: (Number(a.coin) || 0) > 0 || (Number(a.coin_locked) || 0) > 0 };
    },
    // 2차 T16: 차트 범례·안내(새 전략일 때만 값, 아니면 1차 범례 그대로)
    get chartSpec() { return chartLines(this.status); },
    get tradeRows() { const now = Date.now(); return this.trades.map((t) => ({ id: t.id, ...tradeRow(t, now) })); },
    get mismatchText() {
      const s = this.status || {};
      return "경고: 입장 모드(" + (s.mode_entry || "?") + ")와 엔진 모드(" + (s.mode_engine || "?") + ")가 다릅니다.";
    },
    // KST(UTC+9) 표시: MM-DD HH:MM:SS
    kst(iso) {
      if (!iso) return "—";
      const t = Date.parse(iso);
      if (!Number.isFinite(t)) return String(iso);
      const d = new Date(t + 9 * 3600 * 1000);
      const p = (n) => String(n).padStart(2, "0");
      return p(d.getUTCMonth() + 1) + "-" + p(d.getUTCDate()) + " " +
        p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds());
    },
    };
  });
});
