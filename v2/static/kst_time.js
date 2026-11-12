// 화면 시각 표기 한 곳 (1112-01): 「YY.MM.DD HH:MM」 한국 시간(KST). 예) 2026-11-12 15:18 KST → 「26.11.12 15:18」(11/12 사용자 「㉠ 권고대로」 — 첫 배포의 YYMMDD:HH:MM 이 눈에 익지 않아 바꿈).
// 오늘·어제 분기 없음, 초 없음. 받는 값: ISO 문자열 · Date · epoch 밀리초(숫자). 해석 못 하면 null(빈 값 규칙은 부르는 쪽).
// 일반 script(index.html)로도, 모듈 import(chart.js)로도 읽는다 — globalThis.kstStamp 하나만 올린다.
// save.js(백테스터 화면 — index.html 을 읽지 않음)에 같은 함수 사본이 있고 시험(time.test.mjs)이 글자 그대로 같은지 본다.
(function (g) {
  "use strict";
  function kstStamp(v) {
    var t = v instanceof Date ? v.getTime() : (typeof v === "number" ? v : (typeof v === "string" && v ? Date.parse(v) : NaN));
    if (!Number.isFinite(t)) return null;
    var d = new Date(t + 9 * 3600 * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getUTCFullYear() % 100) + "." + p(d.getUTCMonth() + 1) + "." + p(d.getUTCDate()) + " " +
      p(d.getUTCHours()) + ":" + p(d.getUTCMinutes());
  }
  g.kstStamp = kstStamp;
})(globalThis);
