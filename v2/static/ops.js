// 운용 탭 단추 (2차 T14, 요청서 2-마, 결정 D6·D11). DOM 을 만지지 않는 순수 함수만 둔다 — app.js 가 부르고 node 시험이 검사한다.
// 읽기: GET /v2/api/ops(예약·복귀 대상·저장본·회차·회당 금액·주문 비율·거래 시간), 홈과 같은 status·assets·basic.
// 쓰기: POST /v2/api/control(엔진 제어 요청) · POST /v2/api/pause(일시정지 — 홈 단추와 같은 동작). 결과는 2초마다 60초까지 읽는다.
(function () {
  "use strict";

  var OLD = ["EMA", "MACD"];
  var NAMES = { EMA: "EMA", MACD: "MACD", PULLBACK: "눌림목 분할매수" };
  var POLL_STEP_MS = 2000;
  var POLL_MAX_MS = 60000;
  var NO_RESPONSE_TEXT = "엔진이 응답하지 않습니다 — 잠시 뒤 결과를 다시 확인해 주세요";

  // 단추 글자(화면 순서와 같음 — alpine_wiring 시험이 순서를 본다)
  var LABELS = {
    switch: "백테스터 규칙으로 전환",
    revert: "기존 전략으로 복귀",
    revertNA: "기존 전략으로 복귀 (지금은 해당 없음)",
    cancel: "예약 취소",
    pause: "일시정지",
    stop: "엔진 정지",
    start: "엔진 시작",
    forceBuy: "강제 매수",
    forceSell: "강제 매도",
    opsSave: "운용 설정 저장",
  };

  var CONFIRM = {
    switch: "지금 보유분이 있으면 기존 방식으로 판 뒤 바뀝니다. 전환할까요?",
    cancel: "전환(복귀) 예약을 취소하고 지금 전략을 그대로 쓸까요?",
    stop: "엔진을 멈출까요? 멈춘 동안에는 봇이 사고팔지 않습니다.",
    forceSell: "지금 보유분을 시장가로 모두 팔까요?",
    pause: "매매를 일시정지합니다. 일시정지 중에는 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. " +
      "재개는 홈 화면 위 단추로 합니다.",
    opsSave: "거래 시간 설정을 저장하고 지금 엔진에 바로 적용할까요? (다음 봉부터 적용됩니다)",
    chooseStrategy: "돌아갈 전략 기록이 없습니다. 돌아갈 전략을 골라 주세요.",
  };

  // 결과 code → 화면 문구(엔진 결과 파일의 message 가 있으면 그것을 먼저 쓴다 — 아래 표는 message 가 없을 때·화면 쪽 사유)
  var CODE_TEXT = {
    busy: "앞 요청을 처리하는 중입니다. 잠시 뒤 다시 눌러 주세요.",
    mode_conflict: "다른 모드(모의/실계좌) 엔진이 돌고 있어 처리하지 않았습니다.",
    saved_invalid: "저장한 새 전략 설정을 읽지 못했거나 값이 맞지 않아 처리하지 않았습니다. 백테스터에서 다시 저장해 주세요.",
    sha_mismatch: "다른 저장이 끼어들었습니다. 다시 저장해 주세요.",
    choose_strategy: "돌아갈 전략 기록이 없습니다. EMA 또는 MACD 를 골라 주세요.",
    expired: "요청 뒤 1분이 지나 처리하지 않았습니다. 다시 눌러 주세요.",
    error: "처리하지 못했습니다. 운영자가 확인합니다.",
  };

  function _won(n) { return Math.floor(Number(n)).toLocaleString("ko-KR"); }

  function _intervalText(iv) {
    var m = /^minute(\d+)$/.exec(String(iv || ""));
    return m ? m[1] + "분봉" : String(iv || "—");
  }

  function _upper(v) { return String(v == null ? "" : v).toUpperCase(); }

  // 화면 상태 한 덩어리 → 단추별 {enabled, label}. ctx 는 app.js 가 status·assets·basic·ops(GET /v2/api/ops)로 만든다.
  //   strategy: "EMA"|"MACD"|"PULLBACK"|"" · reservation: {kind,…}|null · reservationError · savedOk
  //   engineRunning: true|false|undefined(확인 중) · holding: bool · round: {entry,max}|null · busy: 요청 처리 중
  function buttonStates(ctx) {
    ctx = ctx || {};
    var st = _upper(ctx.strategy);
    var old = OLD.indexOf(st) >= 0;
    var pb = st === "PULLBACK";
    var known = ctx.reservationError !== true && ctx.opsLoaded === true;
    var reserved = !!ctx.reservation;
    var busy = !!ctx.busy;
    var running = ctx.engineRunning;
    var holding = !!ctx.holding;
    var r = ctx.round;
    var roundsLeft = !!(r && Number(r.max) > 0 && Number(r.entry) < Number(r.max));
    var on = function (cond) { return !busy && !!cond; };
    // fix 1 (PO 결정 3): 실계좌(LIVE) 입장에서는 전환·복귀·운용 설정 저장을 닫는다(엔진도 거절). 강제 매매·엔진 시작/정지는 그대로.
    var live = _upper(ctx.mode) === "LIVE";
    return {
      switch: { label: LABELS.switch, enabled: on(!live && old && known && !reserved && ctx.savedOk === true) },
      revert: { label: old ? LABELS.revertNA : LABELS.revert, enabled: on(!live && pb && known && !reserved) },
      cancel: { label: LABELS.cancel, enabled: on(known && reserved) },
      pause: { label: LABELS.pause, enabled: !busy },
      stop: { label: LABELS.stop, enabled: on(running === true) },
      start: { label: LABELS.start, enabled: on(running === false) },
      forceBuy: { label: LABELS.forceBuy, enabled: on(!holding || (pb && roundsLeft)) },
      forceSell: { label: LABELS.forceSell, enabled: on(holding) },
      // fix 1 (PO 결정 2): 새 전략 운용 중 + 예약 상태를 읽었고 예약이 없을 때만(서버도 같은 조건으로 거절)
      opsSave: { label: LABELS.opsSave, enabled: on(!live && pb && known && !reserved) },
    };
  }

  var LIVE_NOTE = "실계좌(LIVE)에서는 아직 할 수 없습니다";
  // 실계좌 입장일 때 전환·복귀·운용 설정 옆 한 줄(아니면 "")
  function liveNote(mode) { return _upper(mode) === "LIVE" ? LIVE_NOTE : ""; }

  // fix 1 (PO 결정 1): 「시간 밖에도 매도」는 아직 바꿀 수 없다(시간 밖 손절 처리 결정 뒤 열림) — 보기만
  var SELL_OFF_NOTE = "이 항목은 아직 바꿀 수 없습니다(시간 밖 손절 처리 결정 뒤 열립니다)";

  // 복귀 확인 문구: 기록이 있으면 「<EMA> · <종목> · <봉> 으로 돌아갑니다」, 없으면 null(전략을 고르게 함)
  function revertConfirmText(target) {
    if (!target || OLD.indexOf(_upper(target.strategy)) < 0) return null;
    return NAMES[_upper(target.strategy)] + " · " + (target.ticker || "—") + " · " + _intervalText(target.interval) +
      " 으로 돌아갑니다. 지금 보유분이 있으면 새 전략 매도 규칙으로 판 뒤 바뀝니다. 진행할까요?";
  }

  // 강제 매수 확인 문구(금액 표시): PULLBACK = 회당 금액, EMA·MACD = 원화 잔고 × 주문 비율. 금액은 엔진이 다시 정한다.
  function forceBuyConfirmText(ctx) {
    ctx = ctx || {};
    var st = _upper(ctx.strategy);
    var tail = ". 시장가로 삽니다. 실제 금액은 주문 때 엔진이 다시 계산합니다. 진행할까요?";
    if (st === "PULLBACK") {
      var r = ctx.round || {};
      var amt = Number(ctx.perBuy) > 0 ? "회당 금액 약 " + _won(ctx.perBuy) + "원" : "회당 금액 확인 불가";
      var nth = r.max ? " (" + (Number(r.entry || 0) + 1) + " / " + r.max + "회차)" : "";
      return "새 전략 강제 매수: " + amt + nth + tail;
    }
    // fix 1 (막음 5): EMA·MACD 강제 매수는 매수 조건 설정에 따라 시장가 또는 현재가 지정가로 나간다
    var oldTail = ". 주문 방식(시장가 또는 현재가 지정가)은 지금 매수 조건 설정을 따릅니다. " +
      "실제 금액은 주문 때 엔진이 다시 계산합니다. 진행할까요?";
    var krw = Number(ctx.krw), ratio = Number(ctx.orderRatio);
    if (krw > 0 && ratio > 0) {
      return "강제 매수: 원화 잔고 " + _won(krw) + "원 × 주문 비율 " + Math.round(ratio * 1000) / 10 + "% = 약 " +
        _won(krw * ratio) + "원" + oldTail;
    }
    return "강제 매수: 원화 잔고 × 주문 비율 금액 확인 불가" + oldTail;
  }

  // 엔진 결과(GET /v2/api/control/result) → 화면 한 줄. 결과 파일 message 는 엔진이 쓴 투자자용 문구다.
  function resultText(res) {
    if (!res || res.status === "pending") return NO_RESPONSE_TEXT;
    if (res.message) return String(res.message);
    if (res.code && CODE_TEXT[res.code]) return CODE_TEXT[res.code];
    if (res.status === "expired") return CODE_TEXT.expired;
    if (res.status === "error") return CODE_TEXT.error;
    return res.status === "done" ? "요청대로 처리했습니다." : "처리하지 못했습니다.";
  }

  // 요청 POST 실패 문구
  function postErrorText(status, body) {
    body = body || {};
    if (status === 409 && body.error === "reserved") {
      return "전환(복귀) 예약 중이라 운용 설정을 바꾸지 않았습니다. 예약이 끝난 뒤 다시 눌러 주세요.";
    }
    if (status === 409 && body.error === "live_not_supported") return LIVE_NOTE + ".";
    if (status === 400 && body.error === "sell_off_locked") return "이 항목(시간 밖에도 매도)은 아직 바꿀 수 없습니다.";
    if (status === 409 && body.error === "not_pullback") {
      return "운용 설정은 새 전략 운용 중에만 바꿀 수 있습니다.";
    }
    if (status === 503 && body.error === "reservation_unknown") {
      return "예약 상태를 읽지 못해 보내지 않았습니다. 잠시 뒤 다시 눌러 주세요.";
    }
    if (status === 409) return CODE_TEXT.busy;
    if (status === 401 || status === 403) return "구버전에서 다시 들어와 주세요.";
    if (status === 400 && body.error === "source_not_upbit") {
      return "바이낸스 데이터 결과는 참고용이라 적용할 수 없습니다. 업비트 데이터로 다시 시험해 저장해 주세요.";
    }
    if (status === 400) return "요청 형식이 맞지 않아 보내지 않았습니다.";
    return "요청을 보내지 못했습니다. 잠시 뒤 다시 눌러 주세요.";
  }

  // 결과를 2초마다 60초까지 읽는다. get(url) → Promise<json>, wait(ms) → Promise. 끝나면 결과(못 받으면 null).
  function pollResult(get, wait, id, stepMs, maxMs) {
    var step = stepMs == null ? POLL_STEP_MS : stepMs;
    var max = maxMs == null ? POLL_MAX_MS : maxMs;
    var spent = 0;
    function once() {
      return get("/v2/api/control/result?id=" + encodeURIComponent(id)).then(function (r) {
        return r && r.status && r.status !== "pending" ? r : null;
      }, function () { return null; }).then(function (r) {
        if (r) return r;
        if (spent >= max) return null;
        spent += step;
        return wait(step).then(once);
      });
    }
    return once();
  }

  // 운용 설정 입력 → 요청 payload {"keys": 4키}. 형식이 틀리면 null(보내지 않음).
  // fix 1 (PO 결정 1): 「시간 밖에도 매도」는 입력 칸 값이 아니라 지금 적용본 값(hours)을 그대로 보낸다 — 바꾼 값은 보내지 않음.
  var HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
  function opsPayload(form, hours) {
    form = form || {};
    var sellOff = opsForm(hours).sellOff;
    if (typeof form.enable !== "boolean") return null;
    if (!HHMM.test(String(form.start || "")) || !HHMM.test(String(form.end || ""))) return null;
    return { keys: { enable_trading_hours: form.enable, trading_start_time: form.start,
      trading_end_time: form.end, allow_sell_during_off_hours: sellOff } };
  }

  // 지금 적용본 4키 → 입력 칸 값(없으면 엔진 기본값)
  function opsForm(hours) {
    var h = hours || {};
    return { enable: h.enable_trading_hours === true, start: h.trading_start_time || "09:00",
      end: h.trading_end_time || "02:00", sellOff: h.allow_sell_during_off_hours !== false };
  }

  // 지금 예약 한 줄(없으면 "")
  function reservationText(res, error) {
    if (error) return "예약 상태를 읽지 못했습니다. 전환·복귀 단추는 잠시 막아 둡니다.";
    if (!res) return "";
    if (res.switching) return "전환을 처리하는 중입니다.";
    return res.kind === "REVERT" ? "복귀 예약 중 — 지금 보유분을 판 뒤 기존 전략으로 돌아갑니다."
      : "전환 예약 중 — 지금 보유분을 판 뒤 새 전략으로 바뀝니다.";
  }

  globalThis.__v2ops = {
    LABELS: LABELS, CONFIRM: CONFIRM, CODE_TEXT: CODE_TEXT, NO_RESPONSE_TEXT: NO_RESPONSE_TEXT,
    POLL_STEP_MS: POLL_STEP_MS, POLL_MAX_MS: POLL_MAX_MS,
    buttonStates: buttonStates, revertConfirmText: revertConfirmText, forceBuyConfirmText: forceBuyConfirmText,
    resultText: resultText, postErrorText: postErrorText, pollResult: pollResult, opsPayload: opsPayload,
    opsForm: opsForm, reservationText: reservationText, liveNote: liveNote, LIVE_NOTE: LIVE_NOTE,
    SELL_OFF_NOTE: SELL_OFF_NOTE,
  };
})();
