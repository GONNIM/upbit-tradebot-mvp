// 2차 T14 운용 탭 순수 함수 시험(v2/static/ops.js) — 브라우저 없이 globalThis.__v2ops 로 접근한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "../../..");
const OPS_JS = path.join(ROOT, "v2/static/ops.js");

function load() {
  const ctx = { console };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(OPS_JS, "utf8"), ctx);
  return ctx.__v2ops;
}

const O = load();
const plain = (v) => JSON.parse(JSON.stringify(v));   // vm 안 객체(다른 프로토타입) → 이 쪽 객체
const base = { opsLoaded: true, reservation: null, reservationError: false, savedOk: true, engineRunning: true,
  holding: false, round: null, busy: false };
const enabledSet = (ctx) => {
  const s = O.buttonStates({ ...base, ...ctx });
  return Object.keys(s).filter((k) => s[k].enabled).sort();
};

test("EMA 운용 중 복귀 단추: 글자 「(지금은 해당 없음)」 · 비활성 (그림 2-마)", () => {
  const s = O.buttonStates({ ...base, strategy: "EMA" });
  assert.equal(s.revert.label, "기존 전략으로 복귀 (지금은 해당 없음)");
  assert.equal(s.revert.enabled, false);
  const p = O.buttonStates({ ...base, strategy: "PULLBACK" });
  assert.equal(p.revert.label, "기존 전략으로 복귀");
  assert.equal(p.revert.enabled, true);
});

test("상태별 활성 단추 집합: EMA 미보유 / EMA 보유 / 예약 중 / PULLBACK 보유 / 엔진 멈춤", () => {
  assert.deepEqual(enabledSet({ strategy: "EMA" }), ["forceBuy", "pause", "stop", "switch"].sort());
  assert.deepEqual(enabledSet({ strategy: "EMA", holding: true }), ["forceSell", "pause", "stop", "switch"].sort());
  assert.deepEqual(enabledSet({ strategy: "EMA", holding: true, reservation: { kind: "SWITCH" } }),
    ["cancel", "forceSell", "pause", "stop"].sort());
  // PULLBACK 보유 · 회차 남음(2/5) → 강제 매수도 열림, 운용 설정 저장 열림
  assert.deepEqual(enabledSet({ strategy: "PULLBACK", holding: true, round: { entry: 2, max: 5 } }),
    ["forceBuy", "forceSell", "opsSave", "pause", "revert", "stop"].sort());
  // PULLBACK 보유 · 회차 다 참(5/5) → 강제 매수 닫힘
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", holding: true, round: { entry: 5, max: 5 } }).forceBuy.enabled,
    false);
  // 엔진 멈춤 → 엔진 시작만 열리고 정지 닫힘
  assert.deepEqual(enabledSet({ strategy: "EMA", engineRunning: false }), ["forceBuy", "pause", "start", "switch"].sort());
  // 엔진 확인 중(undefined) → 시작·정지 모두 닫힘
  const u = O.buttonStates({ ...base, strategy: "EMA", engineRunning: undefined });
  assert.equal(u.start.enabled || u.stop.enabled, false);
});

test("전환 단추: 저장본 정상·예약 없음·예약 확인 가능일 때만, 요청 처리 중이면 모두 닫힘(일시정지 포함)", () => {
  assert.equal(O.buttonStates({ ...base, strategy: "EMA", savedOk: false }).switch.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "EMA", reservationError: true }).switch.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "EMA", opsLoaded: false }).switch.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "MACD" }).switch.enabled, true);
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK" }).switch.enabled, false);
  assert.deepEqual(enabledSet({ strategy: "EMA", busy: true }), []);
});

test("전환 확인 창 문구", () => {
  assert.equal(O.CONFIRM.switch, "지금 보유분이 있으면 기존 방식으로 판 뒤 바뀝니다. 전환할까요?");
});

test("복귀 확인: 기록 있음 → 「EMA · 종목 · 봉 으로 돌아갑니다」, 기록 없음 → null(전략 고르기)", () => {
  const t = O.revertConfirmText({ strategy: "EMA", ticker: "KRW-ZRO", interval: "minute3" });
  assert.ok(t.startsWith("EMA · KRW-ZRO · 3분봉 으로 돌아갑니다"), t);
  assert.equal(O.revertConfirmText(null), null);
  assert.equal(O.revertConfirmText({ strategy: "PULLBACK" }), null);
  assert.ok(O.CONFIRM.chooseStrategy.includes("골라 주세요"));
});

test("강제 매수 금액 표시 2종: PULLBACK = 회당 금액, EMA·MACD = 잔고 × 주문 비율", () => {
  const p = O.forceBuyConfirmText({ strategy: "PULLBACK", perBuy: 600000, round: { entry: 2, max: 5 } });
  assert.ok(p.includes("회당 금액 약 600,000원"), p);
  assert.ok(p.includes("(3 / 5회차)"), p);
  const e = O.forceBuyConfirmText({ strategy: "EMA", krw: 1000000, orderRatio: 0.3 });
  assert.ok(e.includes("원화 잔고 1,000,000원 × 주문 비율 30% = 약 300,000원"), e);
  const x = O.forceBuyConfirmText({ strategy: "EMA", krw: null, orderRatio: 0.3 });
  assert.ok(x.includes("확인 불가"), x);
});

test("결과 문구 7종(busy·mode_conflict·saved_invalid·sha_mismatch·choose_strategy·expired·error)", () => {
  assert.equal(O.postErrorText(409, { error: "busy" }), O.CODE_TEXT.busy);
  for (const code of ["mode_conflict", "saved_invalid", "sha_mismatch", "choose_strategy"]) {
    assert.equal(O.resultText({ status: "rejected", code }), O.CODE_TEXT[code], code);
  }
  assert.equal(O.resultText({ status: "expired", code: "expired" }), O.CODE_TEXT.expired);
  assert.equal(O.resultText({ status: "error", code: "start_failed" }), O.CODE_TEXT.error);
  assert.equal(Object.keys(O.CODE_TEXT).length, 7);
  // 엔진이 쓴 message 가 있으면 그것을 쓴다
  assert.equal(O.resultText({ status: "done", code: "ok", message: "엔진을 시작했습니다." }), "엔진을 시작했습니다.");
  // 내부 코드·영문 상태가 문구에 없다
  for (const v of Object.values(O.CODE_TEXT)) assert.doesNotMatch(v, /[a-z_]{4,}/, v);
});

test("60초 넘으면 「엔진이 응답하지 않습니다」 (2초 간격 31회 읽기)", async () => {
  let n = 0, waited = 0;
  const get = async () => { n += 1; return { status: "pending" }; };
  const wait = async (ms) => { waited += ms; };
  const r = await O.pollResult(get, wait, "20261029000000-0000abcd");
  assert.equal(r, null);
  assert.equal(waited, 60000);
  assert.equal(n, 31);
  assert.ok(O.resultText(r).startsWith("엔진이 응답하지 않습니다"));
  // 중간에 결과가 오면 그 결과
  let k = 0;
  const get2 = async () => (++k >= 3 ? { status: "done", code: "ok" } : { status: "pending" });
  assert.deepEqual(await O.pollResult(get2, wait, "20261029000000-0000abcd"), { status: "done", code: "ok" });
});

test("운용 설정 입력 → 4키 payload, 형식 틀리면 null, 적용본 값 → 입력 칸", () => {
  const hoursOff = { allow_sell_during_off_hours: false };
  assert.deepEqual(plain(O.opsPayload({ enable: true, start: "09:00", end: "02:00", sellOff: false }, hoursOff)),
    { keys: { enable_trading_hours: true, trading_start_time: "09:00", trading_end_time: "02:00",
      allow_sell_during_off_hours: false } });
  assert.equal(O.opsPayload({ enable: true, start: "9:00", end: "02:00", sellOff: true }), null);
  assert.equal(O.opsPayload({ enable: "on", start: "09:00", end: "02:00", sellOff: true }), null);
  assert.deepEqual(plain(O.opsForm(null)), { enable: false, start: "09:00", end: "02:00", sellOff: true });
  assert.deepEqual(plain(O.opsForm({ enable_trading_hours: true, trading_start_time: "10:00", trading_end_time: "23:00",
    allow_sell_during_off_hours: false })), { enable: true, start: "10:00", end: "23:00", sellOff: false });
});

test("예약 한 줄 문구", () => {
  assert.equal(O.reservationText(null, false), "");
  assert.ok(O.reservationText({ kind: "SWITCH" }, false).startsWith("전환 예약 중"));
  assert.ok(O.reservationText({ kind: "REVERT" }, false).startsWith("복귀 예약 중"));
  assert.ok(O.reservationText(null, true).includes("읽지 못했습니다"));
});

// ---- T14 fix 1 ----

test("「시간 밖에도 매도」는 화면에서 못 바꾼다: 입력 칸을 바꿔도 적용본 값 그대로 보낸다", () => {
  for (const applied of [true, false]) {
    const hours = { enable_trading_hours: false, trading_start_time: "09:00", trading_end_time: "02:00",
      allow_sell_during_off_hours: applied };
    const p = O.opsPayload({ enable: true, start: "10:00", end: "23:00", sellOff: !applied }, hours);
    assert.equal(p.keys.allow_sell_during_off_hours, applied);
    assert.equal(p.keys.enable_trading_hours, true);
  }
  // 입력 칸 sellOff 가 형식 밖이어도 보내는 값은 적용본 값
  const q = O.opsPayload({ enable: true, start: "09:00", end: "02:00", sellOff: "x" },
    { allow_sell_during_off_hours: false });
  assert.equal(q.keys.allow_sell_during_off_hours, false);
  assert.equal(O.SELL_OFF_NOTE, "이 항목은 아직 바꿀 수 없습니다(시간 밖 손절 처리 결정 뒤 열립니다)");
});

test("운용 설정 저장 단추: 새 전략 운용 중 + 예약 확인 가능 + 예약 없음일 때만", () => {
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK" }).opsSave.enabled, true);
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", reservation: { kind: "REVERT" } }).opsSave.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", reservationError: true }).opsSave.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", opsLoaded: false }).opsSave.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "EMA" }).opsSave.enabled, false);
  // 서버 거절 문구(합니다체, 내부 코드 없음)
  for (const [st, err] of [[409, "reserved"], [409, "not_pullback"], [409, "live_not_supported"], [503, "reservation_unknown"]]) {
    const t = O.postErrorText(st, { error: err });
    assert.notEqual(t, O.CODE_TEXT.busy, err);
    assert.doesNotMatch(t, /[a-z_]{4,}/, t);
    assert.match(t, /(니다|주세요)\.$/, t);
  }
});

test("복귀 단추: 새 전략 운용 중이라도 예약 중이면 닫힘 (V08b)", () => {
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", reservation: { kind: "REVERT" } }).revert.enabled, false);
  assert.equal(O.buttonStates({ ...base, strategy: "PULLBACK", reservation: { kind: "REVERT" } }).cancel.enabled, true);
});

test("실계좌(LIVE) 입장: 전환·복귀·운용 설정 저장 닫힘, 강제 매매·엔진 시작/정지는 그대로", () => {
  const live = enabledSet({ strategy: "EMA", mode: "LIVE" });
  assert.deepEqual(live, ["forceBuy", "pause", "stop"].sort());
  assert.deepEqual(enabledSet({ strategy: "EMA", mode: "TEST" }), ["forceBuy", "pause", "stop", "switch"].sort());
  assert.deepEqual(enabledSet({ strategy: "PULLBACK", mode: "live", holding: true, round: { entry: 1, max: 5 } }),
    ["forceBuy", "forceSell", "pause", "stop"].sort());
  assert.deepEqual(enabledSet({ strategy: "EMA", mode: "LIVE", engineRunning: false }), ["forceBuy", "pause", "start"].sort());
  assert.equal(O.liveNote("LIVE"), "실계좌(LIVE)에서는 아직 할 수 없습니다");
  assert.equal(O.liveNote("TEST"), "");
});

test("EMA·MACD 강제 매수 확인: 주문 방식은 매수 조건 설정을 따른다(시장가 단정 없음), PULLBACK 은 그대로", () => {
  for (const st of ["EMA", "MACD"]) {
    for (const ctx of [{ strategy: st, krw: 1000000, orderRatio: 0.3 }, { strategy: st }]) {
      const t = O.forceBuyConfirmText(ctx);
      assert.ok(t.includes("주문 방식(시장가 또는 현재가 지정가)은 지금 매수 조건 설정을 따릅니다"), t);
      assert.ok(!t.includes("시장가로 삽니다"), t);
    }
  }
  const p = O.forceBuyConfirmText({ strategy: "PULLBACK", perBuy: 600000, round: { entry: 0, max: 5 } });
  assert.ok(p.includes("시장가로 삽니다"), p);
});
