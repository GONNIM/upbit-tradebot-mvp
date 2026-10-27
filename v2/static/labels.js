// 사유·실패 조건 한글 표 (홈 최근 거래·최신 신호, 로그 화면 공용).
// 서버 v2/api_read.py 의 REASON_LABELS·FAILED_KEY_LABELS 와 같아야 한다(시험이 대조).
// 아래 두 객체는 JSON 문법으로만 적는다(시험이 정규식으로 잘라 json.loads 한다).
export const REASON_LABELS = {
  "EMA_GC": "골든크로스",
  "MACD_GC": "골든크로스",
  "GOLDEN": "골든크로스",
  "PULLBACK": "눌림목",
  "TAKE_PROFIT": "익절",
  "TP": "익절",
  "STOP_LOSS": "손절",
  "SL": "손절",
  "EMA_DC": "데드크로스",
  "MACD_DC": "데드크로스",
  "DEADCROSS": "데드크로스",
  "TRAILING_STOP": "추적 손절",
  "TRAILING_STOP_FIXED": "추적 손절",
  "TRAILING_STOP_RATIO": "추적 손절",
  "STALE_POSITION": "정체 청산",
  "HTS_BUY": "외부 매수",
  "HTS_BUY_ADD": "외부 매수",
  "HTS_SELL": "외부 매도",
  "FORCE_BUY": "강제 매수",
  "FORCE_LIQUIDATE": "강제 매도",
  "BUY_FAILED_API": "주문 실패"
};

export const FAILED_KEY_LABELS = {
  "NO_SIGNAL": "신호 없음",
  "SURGE_FILTER": "급등 필터",
  "WARMUP_IN_PROGRESS": "준비 중",
  "WEAK_ENTRY_FILTER": "약한 진입 필터",
  "COOLDOWN": "대기 시간"
};

// 사유 코드 -> 한글. 대소문자 무시, TRAILING_STOP* 접두 일치, 모르는 값은 원래 값.
export function reasonLabel(code) {
  if (code == null || code === "") return "";
  const up = String(code).toUpperCase();
  if (Object.prototype.hasOwnProperty.call(REASON_LABELS, up)) return REASON_LABELS[up];
  if (up.startsWith("TRAILING_STOP")) return REASON_LABELS.TRAILING_STOP;
  return String(code);
}

// failed_keys(JSON 배열 문자열·배열·원문) -> "신호 없음, 급등 필터". 모르는 키는 원래 값.
export function failedKeysText(raw) {
  if (raw == null || raw === "") return "";
  let keys = null;
  if (Array.isArray(raw)) {
    keys = raw;
  } else {
    try {
      const v = JSON.parse(raw);
      if (Array.isArray(v)) keys = v;
    } catch (e) { /* 원문 유지 */ }
  }
  if (keys === null) return String(raw);
  return keys.map((k) => {
    const up = String(k).toUpperCase();
    return Object.prototype.hasOwnProperty.call(FAILED_KEY_LABELS, up) ? FAILED_KEY_LABELS[up] : String(k);
  }).join(", ");
}
