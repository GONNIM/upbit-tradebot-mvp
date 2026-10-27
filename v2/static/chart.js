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
export function toMarkers(markers) {
  return markers
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
export function maLines(closes, periods) {
  const out = {};
  for (const p of periods) out[p] = sma(closes, p);
  return out;
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
  // 선 색(그림 2-나): 60선 주황, 200선 보라. 시리즈는 기간별로 하나씩 만든다.
  const LINE_COLORS = { 60: "#f59e0b", 200: "#7c3aed" };
  const lineSeries = {};
  function seriesFor(p) {
    if (!lineSeries[p]) {
      lineSeries[p] = chart.addLineSeries({
        color: LINE_COLORS[p] || "#6b7280", lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
      });
    }
    return lineSeries[p];
  }
  return {
    ok: true,
    chart,
    // periods: 이동평균 기간 목록, unitSec: 봉 길이(초)
    update(candles, markers, periods = [60, 200], unitSec) {
      const data = toChartCandles(candles);
      candleSeries.setData(data);
      const closes = data.map((d) => d.close);
      const line = (arr) => arr
        .map((v, i) => (v === null ? null : { time: data[i].time, value: v }))
        .filter(Boolean);
      const shown = visiblePeriods(data.length, periods);
      const lines = maLines(closes, shown);
      for (const p of periods) {
        seriesFor(p).setData(shown.includes(p) ? line(lines[p]) : []);
      }
      const all = toMarkers(markers || []);
      candleSeries.setMarkers(data.length
        ? clipMarkers(all, data[0].time, data[data.length - 1].time, unitSec || 60) : []);
    },
    destroy() { chart.remove(); },
  };
}
