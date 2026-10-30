// v2 차트 도우미 (ES 모듈). 모듈 최상위에서 브라우저 전역을 쓰지 않는다 (node 시험이 import 한다).

// toIso 가 있으면 그 시각 이전 200봉(업비트 to= 는 해당 시각 미포함)
export function upbitCandlesUrl(market, unitMin, toIso) {
  return "https://api.upbit.com/v1/candles/minutes/" + encodeURIComponent(unitMin) +
    "?market=" + encodeURIComponent(market) + "&count=200" +
    (toIso ? "&to=" + encodeURIComponent(toIso) : "");
}

// 오름차순 두 목록을 합친다: 시각(candle_date_time_utc) 중복은 newer 가 이긴다(입력은 바뀌지 않는다).
export function mergeCandles(older, newer) {
  const byTime = new Map();
  for (const c of older) byTime.set(c.candle_date_time_utc, c);
  for (const c of newer) byTime.set(c.candle_date_time_utc, c);
  return Array.from(byTime.values())
    .sort((a, b) => Date.parse(a.candle_date_time_utc + "Z") - Date.parse(b.candle_date_time_utc + "Z"));
}

// 업비트 응답은 최신순 → 오래된 순으로 바꾼다 (입력 배열은 바꾸지 않는다).
export function toAscending(candles) {
  return candles.slice().reverse();
}

export function candleStartMs(candle) {
  return Date.parse(candle.candle_date_time_utc + "Z");
}

// 마지막 봉만 forming(형성 중) 표시. 아직 닫히지 않았을 때만 true (Issue #8).
export function markFormingCandle(candles, nowMs, unitSec) {
  const last = candles.length - 1;
  return candles.map((c, i) => {
    const forming = i === last && nowMs < candleStartMs(c) + unitSec * 1000;
    return Object.assign({}, c, { forming });
  });
}

export function sma(values, period) {
  const out = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// 2차 T16: 지수이동평균(새 전략 maType "ema"). 첫 값 = 앞 period 개 단순평균, 그 뒤 α = 2/(period+1).
// 화면에 받은 봉으로만 계산하므로 더 오래 쌓은 엔진 값과 조금 다를 수 있다(화면 안내 1줄).
export function ema(values, period) {
  const out = new Array(values.length).fill(null);
  if (!(period > 0) || values.length < period) return out;
  const a = 2 / (period + 1);
  let prev = 0;
  for (let i = 0; i < period; i++) prev += values[i];
  prev /= period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = prev + a * (values[i] - prev);
    out[i] = prev;
  }
  return out;
}

// 요청 간격 문(창끼리 공유): 마지막 허용 시각을 storage(localStorage)에 두어 같은 브라우저의 여러 창이
// 업비트 10초당 1회 한도를 함께 지킨다. storage 가 없거나 오류면 이 창의 메모리로 대신한다.
export function createSharedRateGate(minIntervalMs, storage, key = "v2.upbitGateAt", nowFn = Date.now) {
  let mem = null;
  function lastAt(now) {
    let last = mem;
    try {
      const raw = storage ? storage.getItem(key) : null;
      const n = raw == null ? NaN : Number(raw);
      if (Number.isFinite(n) && (last === null || n > last)) last = n;
    } catch (e) { /* 저장소 오류: 메모리 값 사용 */ }
    // 시계가 되감겨 미래 시각이 남은 경우 영구히 막지 않는다
    if (last !== null && last - now > minIntervalMs) return null;
    return last;
  }
  return {
    allow() {
      const now = nowFn();
      const last = lastAt(now);
      if (last !== null && now - last < minIntervalMs) return false;
      mem = now;
      try { if (storage) storage.setItem(key, String(now)); } catch (e) { /* 메모리로 대신 */ }
      return true;
    },
    // 문이 열릴 때까지 남은 ms (이미 열려 있으면 0)
    msUntilOpen() {
      const now = nowFn();
      const last = lastAt(now);
      if (last === null) return 0;
      return Math.max(0, minIntervalMs - (now - last));
    },
  };
}

// 폴러: 진행 중이면 새 요청 없음, 숨김이면 건너뜀, 실패면 마지막 데이터 유지 + onError(Date).
export function createPoller({ fetchFn, intervalMs = 30000, onData, onError, isHidden }) {
  let inflight = null;
  let timer = null;

  function tick() {
    if (inflight) return inflight;
    if (isHidden && isHidden()) return Promise.resolve();
    inflight = (async () => {
      try {
        const data = await fetchFn();
        onData(data);
      } catch (e) {
        onError(new Date(), e);
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  }

  return {
    tick,
    start() {
      if (timer !== null) return;
      tick();
      timer = setInterval(tick, intervalMs);
    },
    stop() {
      if (timer !== null) { clearInterval(timer); timer = null; }
    },
  };
}

// markers API 행 → Lightweight Charts 표식. 시간 오름차순, time 은 UTC epoch 초.
// 2차 T16 (결정 1030-02 U2): 실제 체결(BUY·SELL)만 — 거절·취소 등 다른 유형은 그리지 않는다(서버도 같은 조건).
// 외부 매수·매도 행은 bar_time 이 없어 표식이 없다(4e86afb 와 같음 — 아래 time NaN 거르기).
export const MARKER_TYPES = ["BUY", "SELL"];
export function toMarkers(markers) {
  return markers
    .filter((m) => MARKER_TYPES.includes(String(m && m.type).toUpperCase()))
    .map((m) => {
      const buy = String(m.type).toUpperCase() === "BUY";
      return {
        time: Math.floor(Date.parse(m.bar_time) / 1000),
        position: buy ? "belowBar" : "aboveBar",
        color: buy ? "#cf222e" : "#0969da",   // 국내 관례: 매수 빨강, 매도 파랑
        shape: buy ? "arrowUp" : "arrowDown",
        text: buy ? "매수" : "매도",
      };
    })
    .filter((m) => Number.isFinite(m.time))
    .sort((a, b) => a.time - b.time);
}

// 캔들 범위 [firstTime, lastTime + unitSec) 밖 표식은 버린다(LW 가 맨 왼쪽 봉에 몰아 그리는 것을 막는다).
export function clipMarkers(markers, firstTime, lastTime, unitSec) {
  return markers.filter((m) => m.time >= firstTime && m.time < lastTime + unitSec);
}

// failed_keys: JSON 배열 문자열이면 「a, b」, 파싱 실패·배열 아님이면 원문 그대로.
export function parseFailedKeys(raw) {
  if (raw == null || raw === "") return "";
  if (Array.isArray(raw)) return raw.join(", ");
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return v.map(String).join(", ");
  } catch (e) { /* 원문 유지 */ }
  return String(raw);
}

const _p2 = (n) => String(n).padStart(2, "0");

// 차트 시각(UTC epoch 초) -> KST 표시. 데이터 time 은 UTC 그대로 두고 표시만 +9시간.
export function kstHm(sec) {
  const d = new Date((sec + 9 * 3600) * 1000);
  return _p2(d.getUTCHours()) + ":" + _p2(d.getUTCMinutes());
}
export function kstMdHm(sec) {
  const d = new Date((sec + 9 * 3600) * 1000);
  return _p2(d.getUTCMonth() + 1) + "-" + _p2(d.getUTCDate()) + " " + kstHm(sec);
}
// tickMarkType: 0 연, 1 월, 2 일, 3 시각, 4 초 포함 시각
export function kstTick(sec, tickMarkType) {
  return tickMarkType >= 3 ? kstHm(sec) : kstMdHm(sec).slice(0, 5);
}

// 이동평균 선 계산(순수 함수): {기간: 값 배열(앞쪽은 null)}
// maType(2차 T16): "ema" 면 지수이동평균, 그 밖은 단순이동평균(1차 그대로)
export function maLines(closes, periods, maType) {
  const out = {};
  const f = maType === "ema" ? ema : sma;
  for (const p of periods) out[p] = f(closes, p);
  return out;
}

// 2차 T16: 선 목록 정리. 숫자 배열(1차 [60, 200])은 앞 = trend, 뒤 = long 칸으로 본다.
// 칸(slot)마다 색이 정해져 있다: trend 주황, long 보라, pull(눌림 기준선) 청록 점선.
export function normalizeLines(lines) {
  const arr = Array.isArray(lines) ? lines : [60, 200];
  return arr.map((l, i) => (typeof l === "number"
    ? { period: l, slot: i === 0 ? "trend" : (i === 1 ? "long" : "extra" + i) }
    : { period: Number(l.period), slot: String(l.slot) }))
    .filter((l) => Number.isInteger(l.period) && l.period > 0);
}

// 그릴 선: 가장 긴 선(200)은 봉이 그 두 배(400) 모인 뒤에만 그린다. 그 전에는 짧은 선만.
export function visiblePeriods(candleCount, periods) {
  if (periods.length < 2) return periods.slice();
  const longest = Math.max(...periods);
  return periods.filter((p) => p !== longest || candleCount >= 2 * longest);
}

// 보이는 범위를 가운데 기준으로 factor 배 확대(>1)·축소(<1). 차트가 없으면 아무 일도 없다.
export function zoom(view, factor) {
  if (!view || !view.ok || !view.chart || !(factor > 0)) return;
  const ts = view.chart.timeScale();
  const r = ts.getVisibleLogicalRange();
  if (!r) return;
  const center = (r.from + r.to) / 2;
  const half = (r.to - r.from) / 2 / factor;
  ts.setVisibleLogicalRange({ from: center - half, to: center + half });
}

// ---- 브라우저 전용 (함수 안에서만 전역 사용) ----

export function intervalToMinutes(interval) {
  const m = /^minute(\d+)$/.exec(interval || "");
  const n = m ? parseInt(m[1], 10) : 0;
  return [1, 3, 5, 10, 15, 30, 60, 240].includes(n) ? n : null;   // null = 1차 차트 미지원 단위
}

export function toChartCandles(candles) {
  return candles.map((c) => ({
    time: Math.floor(candleStartMs(c) / 1000),
    open: c.opening_price, high: c.high_price, low: c.low_price, close: c.trade_price,
    // 형성 중 봉은 회색으로 구분
    ...(c.forming ? { color: "#b0b7c0", borderColor: "#b0b7c0", wickColor: "#b0b7c0" } : {}),
  }));
}

export function pad2(n) { return String(n).padStart(2, "0"); }

// KST(UTC+9) 시각 문자열 HH:MM:SS
export function kstTime(date) {
  const d = new Date(date.getTime() + 9 * 3600 * 1000);
  return pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":" + pad2(d.getUTCSeconds());
}

// 차트 생성. el: 컨테이너. 반환: {ok, chart, update(candles, markers, periods, unitSec), destroy()}
export function createChartView(el) {
  const LW = window.LightweightCharts;
  if (!LW || typeof LW.createChart !== "function") {
    el.textContent = "차트 라이브러리를 불러오지 못했습니다";
    return { ok: false, update() {}, destroy() {} };
  }
  const chart = LW.createChart(el, {
    autoSize: true,
    layout: { background: { color: "#ffffff" }, textColor: "#333" },
    localization: { timeFormatter: (t) => (typeof t === "number" ? kstMdHm(t) : String(t)) },
    timeScale: {
      timeVisible: true, secondsVisible: false,
      tickMarkFormatter: (t, type) => (typeof t === "number" ? kstTick(t, type) : String(t)),
    },
  });
  const candleSeries = chart.addCandlestickSeries({
    upColor: "#cf222e", downColor: "#0969da", borderVisible: false,
    wickUpColor: "#cf222e", wickDownColor: "#0969da",
  });
  // 선 색(그림 2-나): 60선(trend) 주황, 200선(long) 보라. 2차 T16: 칸(slot)별 시리즈 — 새 전략은 기간이
  // 설정값이라 칸에 색을 묶는다. 눌림 기준선(pull, 60선과 기간이 다를 때만 — U3)은 청록 점선.
  const SLOT_STYLE = { trend: { color: "#f59e0b" }, long: { color: "#7c3aed" }, pull: { color: "#0d9488", lineStyle: 2 } };
  const lineSeries = {};
  function seriesFor(slot) {
    if (!lineSeries[slot]) {
      const st = SLOT_STYLE[slot] || { color: "#6b7280" };
      lineSeries[slot] = chart.addLineSeries(Object.assign({
        lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
      }, st));
    }
    return lineSeries[slot];
  }
  return {
    ok: true,
    chart,
    // lines: 이동평균 선 목록([60, 200] 또는 [{period, slot}]), unitSec: 봉 길이(초), maType: "ema"|"sma"
    update(candles, markers, lines = [60, 200], unitSec, maType) {
      const data = toChartCandles(candles);
      candleSeries.setData(data);
      const closes = data.map((d) => d.close);
      const line = (arr) => arr
        .map((v, i) => (v === null ? null : { time: data[i].time, value: v }))
        .filter(Boolean);
      const specs = normalizeLines(lines);
      const periods = specs.map((s) => s.period);
      const shown = visiblePeriods(data.length, periods);
      const vals = maLines(closes, shown, maType);
      const used = new Set();
      for (const s of specs) {
        used.add(s.slot);
        seriesFor(s.slot).setData(shown.includes(s.period) ? line(vals[s.period]) : []);
      }
      // 설정이 바뀌어 없어진 칸(예: 기준선이 60선과 같아짐)은 비운다
      for (const slot of Object.keys(lineSeries)) if (!used.has(slot)) lineSeries[slot].setData([]);
      const all = toMarkers(markers || []);
      candleSeries.setMarkers(data.length
        ? clipMarkers(all, data[0].time, data[data.length - 1].time, unitSec || 60) : []);
    },
    destroy() { chart.remove(); },
  };
}
