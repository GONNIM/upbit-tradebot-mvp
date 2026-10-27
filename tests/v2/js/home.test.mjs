// 홈(그림 2-가) 순수 함수 시험: homeView·signalSentence·tradeRow + labels.js.
// app.js 는 일반 script — 시험은 전역에 올려 읽는다(tabFromHash 시험과 같은 방식).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, "../../../v2/static");

globalThis.window = globalThis;
globalThis.document = { hidden: false, addEventListener() {} };
const labels = await import(path.join(STATIC, "labels.js"));
globalThis.v2Labels = labels;
vm.runInThisContext(fs.readFileSync(path.join(STATIC, "app.js"), "utf8"));

const { reasonLabel, failedKeysText } = labels;
// 기준 시각: 2026-10-27 10:00 KST = 01:00 UTC
const NOW = Date.parse("2026-10-27T10:00:00+09:00");

const STATUS = { mode_engine: "LIVE", paused: 0, strategy: { value: "EMA" }, ticker: "KRW-ZRO",
  interval: "minute1", engine: { level: "ok", ago_sec: 10 } };
const BASIC = { engine_running: true };
const ASSETS = { krw: 1800000, krw_locked: 0, coin: 1242.6, coin_locked: 0, price: 1000,
  price_at: null, updated_at: null, entry_price: 965.7, tp_price: 1050, sl_price: 930, round: null };

test("(a) 배지 4개: 모드·엔진·전략·일시정지", () => {
  const v = homeView(STATUS, ASSETS, BASIC, NOW);
  assert.deepEqual(v.badges.map((b) => b.text), ["LIVE", "엔진 동작 중", "전략: EMA (기존)", "일시정지 아님"]);
});

test("엔진 배지: 글자와 색이 함께 바뀐다", () => {
  const eng = (st, basic) => homeView(st, ASSETS, basic, NOW).badges[1];
  const ok = eng(STATUS, BASIC);
  assert.equal(ok.cls, "p-run");
  const delay = eng({ ...STATUS, engine: { level: "delay" } }, BASIC);
  assert.equal(delay.text, "엔진 동작 중 · 판단 지연");
  assert.equal(delay.cls, "p-warn");
  const unk = eng({ ...STATUS, engine: { level: "unknown" } }, BASIC);
  assert.equal(unk.text, "엔진 동작 중 · 판단 보류");
  assert.equal(unk.cls, "p-off");
  // 엔진이 멈췄으면 level 이 ok 여도 초록이 아니다
  const stopped = eng(STATUS, { engine_running: false });
  assert.equal(stopped.text, "엔진 멈춤");
  assert.equal(stopped.cls, "p-off");
  const unknownBasic = eng(STATUS, null);
  assert.equal(unknownBasic.text, "엔진 확인 중");
  assert.equal(unknownBasic.cls, "p-off");
});

test("전략 이름·일시정지 배지", () => {
  const b = (strategy, paused) => homeView({ ...STATUS, strategy: { value: strategy }, paused }, ASSETS, BASIC, NOW).badges;
  assert.equal(b("MACD", 0)[2].text, "전략: MACD (기존)");
  assert.equal(b("PULLBACK", 0)[2].text, "전략: 눌림목 분할매수");
  assert.equal(b("EMA", 1)[3].text, "일시정지 중");
  assert.equal(b("EMA", 1)[3].cls, "p-warn");
  assert.equal(b("EMA", 0)[3].cls, "p-off");
});

test("(b) 평가 합계·원화/코인·평가손익", () => {
  const v = homeView(STATUS, ASSETS, BASIC, NOW);
  assert.equal(v.total, "3,042,600원");
  assert.equal(v.krwCoin, "1,800,000 / 1,242,600");
  assert.equal(v.pnl.cls, "up");
  assert.match(v.pnl.text, /^\+[\d,]+ \(\+3\.6%\)$/);
  const loss = homeView(STATUS, { ...ASSETS, price: 900 }, BASIC, NOW);
  assert.equal(loss.pnl.cls, "dn");
  assert.match(loss.pnl.text, /^-[\d,]+ \(-6\.8%\)$/);
});

test("(c) 코인 0 이면 보유 없음 · 평가손익 —", () => {
  const v = homeView(STATUS, { ...ASSETS, coin: 0, entry_price: null, tp_price: null, sl_price: null }, BASIC, NOW);
  assert.equal(v.holding, null);
  assert.equal(v.pnl.text, "—");
  assert.equal(v.total, "1,800,000원");
});

test("보유 카드: 익절·손절 퍼센트, 회차 —", () => {
  const h = homeView(STATUS, ASSETS, BASIC, NOW).holding;
  assert.equal(h.ticker, "KRW-ZRO");
  assert.equal(h.round, "—");
  assert.equal(h.avg, "965.7원");
  assert.deepEqual(h.tp, { label: "익절 가격 (+8.7%)", price: "1,050원" });
  assert.deepEqual(h.sl, { label: "손절 가격 (-3.7%)", price: "930.0원" });
});

test("값이 없는 새 계정(assets·status 없음)도 오류 없이", () => {
  const v = homeView(null, null, null, NOW);
  assert.equal(v.holding, null);
  assert.equal(v.total, "—");
  assert.equal(v.pnl.text, "—");
  assert.ok(Array.isArray(v.badges));
});

test("(d) reasonLabel", () => {
  assert.equal(reasonLabel("TAKE_PROFIT"), "익절");
  assert.equal(reasonLabel("TRAILING_STOP_FIXED"), "추적 손절");
  assert.equal(reasonLabel("TRAILING_STOP_XYZ"), "추적 손절");
  assert.equal(reasonLabel("HTS_BUY_ADD"), "외부 매수");
  assert.equal(reasonLabel("force_buy"), "강제 매수");
  assert.equal(reasonLabel("force_liquidate"), "강제 매도");
  assert.equal(reasonLabel("EMA_GC"), "골든크로스");
  assert.equal(reasonLabel("STALE_POSITION"), "정체 청산");
  assert.equal(reasonLabel("BUY_FAILED_API"), "주문 실패");
  assert.equal(reasonLabel("XYZ"), "XYZ");
});

test("(d) tradeRow: 외부 매도·금액 없음, 구분 색", () => {
  const r = tradeRow({ type: "HTS_SELL", price: null, qty: 5, reason: "HTS_SELL", timestamp: "2026-10-27T09:31:00+09:00" }, NOW);
  assert.equal(r.amount, "—");
  assert.equal(r.kind, "외부 매도");
  assert.equal(r.reason, "외부 매도");
  const buy = tradeRow({ type: "BUY", price: 1000, qty: 600.4, reason: "EMA_GC", timestamp: "2026-10-27T09:31:00+09:00" }, NOW);
  assert.deepEqual([buy.time, buy.kind, buy.kindCls, buy.reason, buy.amount], ["09:31", "매수", "up", "골든크로스", "600,400"]);
  const sell = tradeRow({ type: "SELL", price: 1, qty: 1, reason: "TP", timestamp: "2026-10-27T09:31:00+09:00" }, NOW);
  assert.deepEqual([sell.kind, sell.kindCls], ["매도", "dn"]);
  const rej = tradeRow({ type: "BUY_REJECTED", price: 1, qty: 1, timestamp: "2026-10-27T09:31:00+09:00" }, NOW);
  assert.deepEqual([rej.kind, rej.kindCls], ["거절", "muted"]);
  assert.equal(tradeRow({ type: "BUY_CANCELED", timestamp: null }, NOW).kind, "매수 취소");
  assert.equal(tradeRow({ type: "BUY", price: 0, qty: 3, timestamp: null }, NOW).amount, "—");
});

test("(d) signalSentence", () => {
  const miss = signalSentence({ kind: "buy", overall_ok: 0, failed_keys: '["NO_SIGNAL"]', bar_time: "2026-10-27T10:42:00+09:00" });
  assert.equal(miss.title, "최신 신호 · 10:42 봉");
  assert.equal(miss.text, "매수 대기 — 신호 없음");
  assert.equal(signalSentence({ kind: "buy", overall_ok: 1, bar_time: "2026-10-27T10:42:00+09:00" }).text, "매수 조건 충족");
  assert.equal(signalSentence({ kind: "sell", triggered: 1, trigger_key: "TAKE_PROFIT", bar_time: "2026-10-27T10:42:00+09:00" }).text, "매도 — 익절");
  assert.equal(signalSentence({ kind: "sell", triggered: 0, bar_time: "2026-10-27T10:42:00+09:00" }).text, "보유 유지 — 익절·손절 가격 안");
});

test("(f) 빈 거래·빈 신호", () => {
  assert.equal(signalSentence(null).text, "신호 기록이 없습니다");
  assert.equal(signalSentence(undefined).title, "최신 신호");
  assert.equal(failedKeysText(null), "");
  assert.equal(failedKeysText("not json"), "not json");
  assert.equal(failedKeysText('["COOLDOWN","weird"]'), "대기 시간, weird");
  assert.equal(failedKeysText('["SURGE_FILTER","WARMUP_IN_PROGRESS","WEAK_ENTRY_FILTER"]'), "급등 필터, 준비 중, 약한 진입 필터");
});

test("(e) 어제 거래는 「어제」, 그 전은 MM-DD", () => {
  const t = (iso) => tradeRow({ type: "SELL", price: 1, qty: 1, timestamp: iso }, NOW).time;
  assert.equal(t("2026-10-26T23:00:00+09:00"), "어제");
  assert.equal(t("2026-10-27T00:05:00+09:00"), "00:05");
  assert.equal(t("2026-10-25T12:00:00+09:00"), "10-25");
  // UTC 표기도 KST 날짜로 판정: 10-26T15:30Z = 10-27 00:30 KST = 오늘
  assert.equal(t("2026-10-26T15:30:00+00:00"), "00:30");
});

test("(g) 잠김 줄·기록 시각", () => {
  const a = { ...ASSETS, krw_locked: 5000, coin_locked: 0, updated_at: "2026-10-27T10:42:05+09:00", price_at: null };
  const v = homeView(STATUS, a, BASIC, Date.parse("2026-10-27T11:00:00+09:00"));
  assert.equal(v.locked.text, "5,000 / 0");
  assert.equal(v.locked.warn, true);
  assert.equal(v.recorded, "기록 시각 10:42:05 · 현재가 1,000원 엔진 기록");
  const z = homeView(STATUS, { ...a, krw_locked: 0 }, BASIC, NOW);
  assert.equal(z.locked.text, "0 / 0");
  assert.equal(z.locked.warn, false);
  // 오늘이 아니면 MM-DD HH:MM
  const old = homeView(STATUS, { ...a, updated_at: "2026-10-25T10:42:05+09:00", price_at: "2026-10-26T09:01:30+09:00" }, BASIC, NOW);
  assert.equal(old.recorded, "기록 시각 10-25 10:42 · 현재가 1,000원 10-26 09:01 엔진 기록");
});

// verifier 수정 2026-10-27: 가격은 크기별 고정 소수 자리(100원 미만 종목), 원화 금액은 정수
test("priceText: 크기별 소수 자리·천 단위 쉼표, 보유 카드에 적용, 원화 금액은 정수", () => {
  assert.equal(priceText(0.001234), "0.0012");
  assert.equal(priceText(0.5), "0.5000");
  assert.equal(priceText(1.23456), "1.235");
  assert.equal(priceText(12.3456), "12.35");
  assert.equal(priceText(123.456), "123.5");
  assert.equal(priceText(1234.5), "1,235");
  assert.equal(priceText(1234567), "1,234,567");
  const pepe = { ...ASSETS, krw: 1000, coin: 1000000, price: 0.0015, entry_price: 0.001234, tp_price: 0.0016, sl_price: 0.0011 };
  const v = homeView(STATUS, pepe, BASIC, NOW);
  assert.equal(v.holding.avg, "0.0012원");
  assert.equal(v.holding.tp.price, "0.0016원");
  assert.equal(v.holding.sl.price, "0.0011원");
  assert.equal(v.total, "2,500원");
});

test("기록 시각 줄: 현재가 값·시각(오늘 HH:MM), 값 없으면 —", () => {
  const a = { ...ASSETS, price: 0.001234, updated_at: "2026-10-27T09:42:05+09:00", price_at: "2026-10-27T09:41:30+09:00" };
  assert.equal(homeView(STATUS, a, BASIC, NOW).recorded, "기록 시각 09:42:05 · 현재가 0.0012원 09:41 엔진 기록");
  const none = { ...a, price: null, price_at: null, updated_at: null };
  assert.equal(homeView(STATUS, none, BASIC, NOW).recorded, "기록 시각 — · 현재가 — 엔진 기록");
});
