// v2 화면 (Alpine). 일반 script 로 읽고 alpine:init 에서 등록한다.
// 눌림목 MA 기간: 원본 백테스터 기본값(MA60 과 동일 기간). PULLBACK 설정 파일 값 반영은 2차 이후.
const DEFAULT_PULLBACK_MA = 60;

document.addEventListener("alpine:init", () => {
  Alpine.data("dash", () => {
    // 차트 관련 상태는 반응형 밖(클로저)에 둔다. Alpine 은 x-data 객체에서 꺼낸 값을
    // 반응형 프록시로 감싸 돌려주므로, 거기 넣은 객체를 `===` 로 비교하면 항상 어긋난다.
    // 콜백이 아직 유효한지는 원시값 세대 번호(gen)로 확인한다.
    const C = { gen: 0, poller: null, view: null, key: "", cache: null, gate: null, retryTimer: null };
    return {
    tab: "home",
    status: null, assets: null, trades: [], signals: [],
    logs: [], logsPage: 1,
    authError: false, netError: "", chartFail: "", chartNote: "",
    _cardTimer: null, _cardsBusy: false,

    // ---- 시작·갱신 ---- (Alpine 이 x-data 의 init 을 자동 호출한다)
    init() {
      this.refreshCards();
      // PC 차트 탭 높이: 창 크기·차트 위 문구가 바뀌면 다시 잰다(결정 1026-08)
      window.addEventListener("resize", () => this.fitChart());
      for (const k of ["chartFail", "chartNote", "netError", "authError", "status"]) {
        // x-show 반영이 nextTick 뒤에 오므로 한 프레임 더 기다린다
        this.$watch(k, () => this.$nextTick(() => requestAnimationFrame(() => this.fitChart())));
      }
      // 업비트는 브라우저 요청을 10초당 1회로 제한 — poller 가 바뀌어도 간격을 지킨다
      C.gate = window.v2Chart ? window.v2Chart.createRateGate(10000) : null;
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
        const key = st && st.ticker ? st.ticker + "|" + unit : "";
        // poller 가 없거나 종목·봉 단위가 바뀌었으면 다시 시작
        if (!C.poller || (key && key !== C.key)) this.startChart();
      }
    },

    async _refreshCards() {
      const jobs = [
        ["/v2/api/status", (d) => { this.status = d; }],
        ["/v2/api/assets", (d) => { this.assets = d; }],
        ["/v2/api/trades?limit=10", (d) => { this.trades = d.trades || []; }],
        ["/v2/api/signals?limit=20", (d) => { this.signals = d.signals || []; }],
      ];
      let failed = 0;
      await Promise.all(jobs.map(async ([path, apply]) => {
        try { apply(await this.getJson(path)); } catch (e) { failed += 1; }
      }));
      this.netError = (failed && !this.authError) ? "일부 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도합니다." : "";
    },

    // ---- 탭 ----
    go(name) {
      this.tab = name;
      if (name === "chart") this.startChart(); else this.stopChart();
      if (name === "logs") this.loadLogs(1);
      // 탭을 바꾼 직후에는 차트 칸이 아직 숨어 있다 — 그려진 뒤에 잰다
      if (name === "chart") this.$nextTick(() => requestAnimationFrame(() => this.fitChart()));
    },

    // PC(641px 이상) 차트 탭: 차트 칸을 창 높이에 맞춘다. 그 밖에는 inline 높이를 지워 CSS(360/300px)로 돌린다.
    fitChart() {
      const el = document.getElementById("chart");
      if (!el) return;
      const mod = window.v2Chart;
      const wide = window.matchMedia && window.matchMedia("(min-width: 641px)").matches;
      if (!wide || this.tab !== "chart" || !mod || !mod.fitChartHeight) { el.style.height = ""; return; }
      const box = el.getBoundingClientRect();
      const card = el.closest(".card");
      const below = card ? card.getBoundingClientRect().bottom - box.bottom : 0;   // 안내 문구 + 카드 아래 패딩·테두리
      const cardMargin = card ? parseFloat(getComputedStyle(card).marginBottom) || 0 : 0;
      const bodyPad = parseFloat(getComputedStyle(document.body).paddingBottom) || 0;
      const nav = document.querySelector(".bottom");
      const reserved = below + cardMargin + Math.max(bodyPad, nav ? nav.offsetHeight : 0);
      // 위치는 문서 기준(go() 는 스크롤을 되돌리지 않는다)
      el.style.height = mod.fitChartHeight(window.innerHeight, box.top + window.scrollY, reserved, 360) + "px";
    },

    async loadLogs(page) {
      if (page < 1) return;
      try {
        const d = await this.getJson("/v2/api/logs?page=" + page);
        this.logs = d.logs || [];
        this.logsPage = d.page || page;
      } catch (e) { /* authError 또는 네트워크 — 머리말에 표시됨 */ }
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
      const key = st.ticker + "|" + unitMin;
      if (C.key !== key || !C.view) {
        if (C.view) { C.view.destroy(); C.view = null; }
        document.getElementById("chart").innerHTML = "";
        C.view = mod.createChartView(document.getElementById("chart"));
        C.key = key;
      }
      if (!C.view.ok) return;   // 라이브러리 없음: 화면에 안내 문구가 이미 있다
      const markersPath = "/v2/api/markers";
      if (!C.gate && mod.createRateGate) C.gate = mod.createRateGate(10000);
      const gen = ++C.gen;
      const draw = (d) => {
        const asc = mod.markFormingCandle(mod.toAscending(d.candles), Date.now(), unitMin * 60);
        C.view.update(asc, d.markers, DEFAULT_PULLBACK_MA, unitMin * 60);
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
          const r = await fetch(mod.upbitCandlesUrl(st.ticker, unitMin));
          if (!r.ok) { const e = new Error("upbit " + r.status); e.status = r.status; throw e; }
          const candles = await r.json();
          let markers = [];
          try { markers = (await this.getJson(markersPath)).markers || []; } catch (e) { /* 표식 실패는 차트 실패가 아님 */ }
          return { candles, markers };
        },
        intervalMs: 30000,
        isHidden: () => document.hidden,
        onData: (data) => {
          if (!data) return;   // 게이트에 막혀 건너뜀
          C.cache = { key, candles: data.candles, markers: data.markers };   // 교체된 poller 의 응답도 보관
          if (C.gen !== gen || C.key !== key) return;   // 그리기만 막는다
          draw(C.cache);
          this.chartFail = "";
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
    get chartLegend() {
      return DEFAULT_PULLBACK_MA === 60
        ? "MA60 (눌림목 MA 기본값과 같음)"
        : "MA60 · 눌림목 MA" + DEFAULT_PULLBACK_MA;
    },
    get engineText() {
      const e = this.status && this.status.engine;
      if (!e) return "확인 중";
      const ago = e.ago_sec == null ? "" : " · 마지막 판단 " + Math.floor(e.ago_sec / 60) + "분 전";
      if (e.level === "ok") return "정상" + ago;
      if (e.level === "delay") {
        return e.ago_sec == null ? "지연 · 계좌 갱신 기준"
          : "지연 · 마지막 판단 " + Math.floor(e.ago_sec / 60) + "분 전";
      }
      return "판단 불가" + ago;
    },
    get engineClass() {
      const e = this.status && this.status.engine;
      if (!e) return "b-gray";
      return e.level === "ok" ? "b-ok" : (e.level === "delay" ? "b-warn" : "b-gray");
    },
    get engineIcon() {
      const e = this.status && this.status.engine;
      if (!e) return "…";
      return e.level === "ok" ? "●" : (e.level === "delay" ? "▲" : "?");
    },
    get modeText() {
      const s = this.status;
      if (!s) return "모드 —";
      return "모드 " + (s.mode_engine || "확인 불가");
    },
    get modeClass() {
      return this.status && this.status.mode_mismatch ? "m-warn" : "";
    },
    get mismatchText() {
      const s = this.status || {};
      return "경고: 입장 모드(" + (s.mode_entry || "?") + ")와 엔진 모드(" + (s.mode_engine || "?") + ")가 다릅니다.";
    },
    get pnlText() {
      const a = this.assets;
      if (!a || a.pnl == null) return "—";
      const pct = a.pnl * 100;
      return (pct > 0 ? "▲ +" : (pct < 0 ? "▼ " : "")) + pct.toFixed(2) + "%";
    },
    get pnlClass() {
      const a = this.assets;
      if (!a || a.pnl == null || a.pnl === 0) return "";
      return a.pnl > 0 ? "up" : "down";
    },

    signalText(row) {
      if (row.kind === "sell") {
        return "매도 판단 · " + (row.triggered ? "발동" + (row.trigger_key ? " (" + row.trigger_key + ")" : "") : "미발동");
      }
      return "매수 판단 · " + (row.overall_ok ? "통과" : "미통과" + (row.failed_keys ? " (" + this.failedKeys(row.failed_keys) + ")" : ""));
    },
    failedKeys(raw) {
      const mod = window.v2Chart;
      return mod ? mod.parseFailedKeys(raw) : String(raw);
    },
    // 색은 국내 관례(매수 빨강·매도 파랑). 글자(매수/매도·발동)도 함께 나온다.
    signalClass(row) {
      if (row.kind === "sell") return row.triggered ? "sell strong" : "muted";
      return row.overall_ok ? "buy" : "muted";
    },

    num(v) {
      if (v == null || v === "") return "—";
      const n = Number(v);
      if (!Number.isFinite(n)) return "—";
      return n.toLocaleString("ko-KR", { maximumFractionDigits: 8 });
    },
    orDash(v) {
      return v == null || v === "" ? "—" : this.num(v);
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
