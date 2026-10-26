// v2 차트 도우미 (ES 모듈). 모듈 최상위에서 브라우저 전역을 쓰지 않는다 (node 시험이 import 한다).

export function upbitCandlesUrl(market, unitMin) {
  return "https://api.upbit.com/v1/candles/minutes/" + encodeURIComponent(unitMin) +
    "?market=" + encodeURIComponent(market) + "&count=200";
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

// 요청 간격 문: 마지막으로 허용한 시각에서 minIntervalMs 안이면 false(건너뜀), 아니면 true 로 시각을 갱신.
export function createRateGate(minIntervalMs, nowFn = Date.now) {
  let last = null;
  return {
    allow() {
      const now = nowFn();
      if (last !== null && now - last < minIntervalMs) return false;
      last = now;
      return true;
    },
    // 게이트가 열릴 때까지 남은 ms (이미 열려 있으면 0)
    msUntilOpen() {
      if (last === null) return 0;
      return Math.max(0, minIntervalMs - (nowFn() - last));
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

// 이동평균 선 계산(순수 함수). 눌림목 MA 기간이 60 이면 MA60 과 같으므로 두 번째 선은 없다(null).
export function maLines(closes, pullbackPeriod) {
  const ma60 = sma(closes, 60);
  const same = pullbackPeriod === 60;
  return {
    ma60,
    pullback: same ? null : sma(closes, pullbackPeriod),
    label: same
      ? "MA60 (눌림목 MA 기본값과 같음)"
      : "MA60 · 눌림목 MA" + pullbackPeriod,
  };
}

// PC 차트 탭 높이(결정 1026-08): 창 높이 - 차트 칸의 문서 기준 위치 - 아래 예약 높이. 최소 minPx(낮은 창은 스크롤 허용).
export function fitChartHeight(viewportH, chartTop, reservedPx, minPx) {
  const h = Math.floor(viewportH - chartTop - reservedPx);
  return Number.isFinite(h) && h > minPx ? h : minPx;
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

// 차트 생성. el: 컨테이너. 반환: {update(candles, markers, pullbackPeriod), destroy()}
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
  const ma60 = chart.addLineSeries({ color: "#bf8700", lineWidth: 2, priceLineVisible: false });
  const maPull = chart.addLineSeries({ color: "#8250df", lineWidth: 1, priceLineVisible: false });
  return {
    ok: true,
    update(candles, markers, pullbackPeriod, unitSec) {
      const data = toChartCandles(candles);
      candleSeries.setData(data);
      const closes = data.map((d) => d.close);
      const line = (arr) => arr
        .map((v, i) => (v === null ? null : { time: data[i].time, value: v }))
        .filter(Boolean);
      const lines = maLines(closes, pullbackPeriod || 60);
      ma60.setData(line(lines.ma60));
      maPull.setData(lines.pullback ? line(lines.pullback) : []);
      const all = toMarkers(markers || []);
      candleSeries.setMarkers(data.length
        ? clipMarkers(all, data[0].time, data[data.length - 1].time, unitSec || 60) : []);
    },
    destroy() { chart.remove(); },
  };
}
