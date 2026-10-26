# 신버전 1차 화면 — 승인 요청서 v2 그림과 같게 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 신버전 대시보드의 모든 화면(홈·차트·백테스터·로그·운용·설정 저장 확인 창·구버전 입장 버튼)을 투자자 승인 요청서 v2 의 그림과 같은 배치·문구·순서로 바꾼다. 모바일·PC 공통(PC 는 휴대폰 화면 그대로).

**Architecture:** 화면은 지금처럼 `v2/static/index.html`(Alpine 한 페이지, 홈·차트·로그·운용 탭)과 `v2/static/backtester.html`(별도 페이지, 원본 계산 `backtester.js` 바이트 그대로)로 둔다. 두 페이지 모두 같은 머리 막대·같은 아래 메뉴(홈·차트·백테스터·로그·운용)를 쓰고, 탭 이동은 `/v2/#<tab>` 주소로 한다. 업비트 시세는 브라우저가 직접 받고(서버 호출 0, D8), 두 페이지가 localStorage 로 10초 문을 함께 쓴다.

**Tech Stack:** Alpine 3.14.1, lightweight-charts 4.2.0(vendor), Tornado(v2 서버), node --test, unittest, Streamlit(구버전 입장 버튼).

**Spec:** `docs/specs/v2-dashboard/investor-approval-20261021-v2.html`(=PDF) 1·2·5절 그림이 화면 기준이다. 결정 1026-19(2026-10-26, 사용자): 1 가(1차 화면을 그림과 같게) · 2 가(백테스터 업비트 데이터 = 브라우저 직접) · 3 가(PC = 휴대폰 화면 그대로) · 4 가(입장 한 번 누르기, 다음 엔진 재시작 때 반영) · 5 나(운용 단추는 「2차 공개 때 열림」 표시만). 결정 근거: `docs/fable/2026-10-26-proposal-match-scope-1.md`. 사용자 지시 「기존 요구사항은 모두 폐기」 — 폐기: 1025-18, 1025-19(홈 매매 중지 블록), 1026-08(PC 차트 확대), E4(차트 200선 제외), R7(1차는 Binance 만). 2차(새 전략 실매매·전환·운용 단추 동작)는 이 계획 범위 밖이며 다음 계획으로 이어 간다(사용자: 「승인 요청서 내용은 구현이 되어야 한다」).

## Global Constraints

- `v2/static/backtester.js` 는 원본(`docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html` 143-938행)과 바이트 동일 유지 — parity 시험 그대로 통과.
- v2 서버는 업비트를 부르지 않는다(D8). 업비트 호출은 브라우저만, Origin 요청 10초당 1회 → 모든 업비트 호출은 공유 문(`createSharedRateGate(10000)`)을 지난다.
- 엔진 매매 경로(`core/ engine/ services/ config.py scripts/tradebot_boot.py`)는 바꾸지 않는다. 구버전 쪽 변경은 `ui/v2_entry.py` 하나.
- 화면 문구는 그림 문구를 그대로 쓴다(아래 각 Task 의 「문구」). 시각은 KST.
- 색: 매수·이익 빨강, 매도·손실 파랑(그림과 국내 관례). 머리 막대 짙은 남색 `#1f2937`, 강조 파랑 `#2563eb`, 실행 단추 빨강 `#ef4444`.
- 폭: 모든 화면 최대 480px 가운데(창이 넓어도 같음). 412·360px 에서 가로 넘침 0.
- 여러 줄 텍스트는 파일 도구로만 쓴다(heredoc 금지). 커밋은 마지막에 한 번, 사용자 승인 뒤, `pages/dashboard.py` 버전 갱신 포함.

- 그림 속 숫자·이름은 승인 요청서가 「예시 값」이라고 밝혔다(0절 「그림 속 숫자는 예시 값」). 따라서 개수·종목·봉 단위는 실제 값으로 보인다(접힌 입력 「11개」, 업비트 기본 봉 단위 = 엔진 봉 단위, 표시 이름 = `users.display_name`). 1차에는 새 전략이 없으므로 거래 구분의 회차(「매수 2회」)와 분할 회차는 「매수」·「—」로 보인다.
- backtester.js 의 `let` 전역(`sweepRows`·`lastResults`·`lastCfgBase` 등)은 맨이름으로만 읽는다(`window.` 로 읽으면 undefined). 함수(`run`·`fetchKlines` 등)는 `window.` 로 감쌀 수 있다.

## 사용자에게 사라지거나 옮겨지는 것 (project-rules 1-A 2 — 보고에 그대로 싣는다)
| 지금 | 바뀐 뒤 |
|---|---|
| 홈 위 기본 블록(제목·모드 안내·현재 시각·상태 로그·엔진 상태·「매매 중지/재개」·「로그아웃」·자산 3칸) | 삭제. 엔진 상태·모드·일시정지는 홈 배지로, 매매 중지는 구버전에서만(운용 탭 「일시정지」는 2차) |
| 홈 「상태」·「자산」(KRW 잠김·코인 잠김·현재가 기록 시각)·「포지션」·최신 신호 20건 | 그림 2-가 카드(자산·보유·최신 신호 1건)로 바뀜. 잠김 수량·기록 시각은 사라짐 |
| PC 차트 탭 창 전체 크기(1026-08) | 휴대폰과 같은 크기 |
| 백테스터 결과 표(요약·분할 단계·주간·월간)·스윕 설정·차트·전략 설명 | 「자세한 결과」·「스윕 범위」 접힘 안으로 이동(내용 보존) |
| 백테스터 위 기본 블록(PC) | 삭제 |
| 운용 탭 「엔진 시작」·「운용 설정」 단추 | 그림 2-마 배치(엔진 시작 단추 없음, 운용 설정은 글 카드) |
| 「구버전으로 돌아가면 다시 로그인해야 합니다」 안내 | 머리 막대에서 지움(그림에 없음). 「구버전으로」는 지금처럼 구버전 로그인 화면으로 간다(Streamlit 세션이 따로라서) — 보고에 적음 |
| 백테스터 기본값 3분·바이낸스 | 업비트·엔진 봉 단위(지금 서버 1분)·30일 — 첫 실행 약 36분(216회×10초). 기간을 줄이면 빨라짐 |

## Review Focus

1. 업비트 1분·30일 백테스트(216회 × 10초 ≈ 36분) 중 「데이터 가져오기」를 또 누르거나 아래 메뉴로 다른 탭에 가려는 경우 — 두 번째 실행은 막고, 수집 중 다른 탭 이동은 확인 창(「업비트 데이터 수집이 멈춥니다. 이동할까요?」 + `beforeunload`)으로 묻는다. 별도 페이지라 이동하면 수집은 끊긴다(이어 받기 없음). Task 4 시험.
2. 차트 탭이 열린 다른 창과 백테스터가 동시에 업비트를 부르는 경우 — 공유 문으로 합쳐 10초 1회를 넘지 않아야 한다. Task 3 시험.
3. 보유가 없거나 거래 기록이 0건인 새 계정 — 홈 「보유」는 「없음」, 최근 거래는 「거래 기록이 없습니다」, 오류 없이 그려져야 한다. Task 2 시험.
4. 업비트 출처로 시험한 종목이 엔진 종목과 다른 채 「설정 저장」 — 확인 창에 다르다는 경고를 보이고 저장은 엔진 종목 기준(서버 기존 동작). Task 5 시험.
5. 로그 쪽 번호가 전체 쪽 수보다 큰 주소·빈 로그 — 마지막 쪽으로 맞추고 「기록이 없습니다」. Task 6 시험.

---

### Task 1: 공통 틀 — 머리 막대·아래 메뉴 순서·PC 휴대폰 폭·기본 블록 제거

**Files:**
- Modify: `v2/static/index.html`(머리 `header.top`, `#basic`, `nav.bottom`, `basic.css`·`basic.js` 링크)
- Modify: `v2/static/style.css`(641px 이상 PC 규칙 전부, `body.tab-chart` 규칙 삭제 → 모든 폭 480px 가운데)
- Modify: `v2/static/app.js`(`fitChart`·resize·`$watch` 제거, 주소 `#tab` 읽기·쓰기)
- Modify: `v2/static/chart.js`(`fitChartHeight` 삭제)
- Delete: `v2/static/basic.js`, `v2/static/basic.css`, `tests/v2/js/basic.test.mjs`
- Test: `tests/v2/js/alpine_wiring.test.mjs`, `tests/v2/test_static_lint.py`

**Interfaces:**
- Produces: `tabFromHash(hash: string) -> "home"|"chart"|"logs"|"ops"`(app.js, 모르는 값·`#backtester` 는 `"home"`); 아래 메뉴 마크업 순서 홈·차트·백테스터·로그·운용(백테스터는 `<a href="/v2/static/backtester.html">`, 나머지는 `go(tab)`); `go(tab)` 는 `history.replaceState(null, "", "#" + tab)`.
- 머리 막대: 홈 = 왼쪽 「신버전 대시보드」, 오른쪽 「<표시 이름>님 · 구버전으로」(구버전으로 = `href="/"` 링크). 다른 탭 = 왼쪽 탭 제목(「차트 · <종목> · <봉>」「로그」「운용」), 오른쪽 모드(LIVE/TEST). 표시 이름: `/v2/api/basic` 응답에 `"display_name"` 키를 더한다(`SELECT display_name FROM users WHERE username=? LIMIT 1`, 비었으면 user_id).
- `/v2/api/basic` 은 남긴다(Task 2 배지가 `engine_running` 을 읽는다). `/v2/api/pause` 도 남긴다(2차 운용 단추용, 화면에서는 부르지 않음, 기존 test_basic_pause 유지).
- 바꿀 기존 시험(이유: 사용자 지시 「기존 요구 폐기」): `tests/v2/test_static_lint.py` 의 `OWN` 목록에서 basic.js 를 빼고 bt_ui.js(허용 외부 주소 `api.upbit.com`)·labels.js(외부 주소 없음)를 넣음, `test_no_stop_word_in_engine_badge` 는 needle(「정상」·「지연 · 마지막 판단」·「판단 불가」)을 새 배지 글자(「엔진 동작 중」·「판단 지연」·「엔진 멈춤」·「엔진 확인 중」)로 바꾸고 「정지」 낱말 금지 단언은 유지, `test_signal_key_uses_kind`·`test_backtester_menu_link` 는 새 마크업에 맞춰 대상 선택자만 고침(단언 뜻 유지); `tests/v2/js/chart.test.mjs` 의 `fitChartHeight` 시험 삭제; `tests/v2/test_api_read.py` 의 basic 응답 키 시험에 display_name 추가.

- [ ] **Step 1: 실패 시험** — `alpine_wiring.test.mjs` 에 추가: `nav.bottom` 의 글자 순서가 `["홈","차트","백테스터","로그","운용"]`; `index.html` 에 `basic.js`·`basic.css`·`id="basic"` 없음; `tabFromHash("#logs")==="logs"`, `tabFromHash("#backtester")==="home"`, `tabFromHash("")==="home"`. `test_static_lint.py` 에 추가: `style.css` 에 `min-width: 641px` 없음, `body` 최대 폭 `480px`. `test_api_read.py`: basic 응답에 `display_name`(가짜 DB "Dev User").
- [ ] **Step 2: 실행 → 실패 확인** — `node --test tests/v2/js/*.test.mjs` · `python3 -m unittest tests.v2.test_static_lint`
- [ ] **Step 3: 구현** — 위 Interfaces 대로. 머리 막대 마크업은 `header.bar > .bar-title + .bar-right`. 모드 불일치 경고·세션 없음 안내·네트워크 안내 문구(지금 `header.top` 안 `p.warn`)는 막대 아래 그대로 둔다. 「구버전으로 돌아가면 다시 로그인해야 합니다」 안내는 지운다(그림에 없음).
- [ ] **Step 4: 실행 → 통과 확인** (같은 명령)

### Task 2: 홈 — 그림 2-가

**Files:**
- Modify: `v2/static/index.html`(홈 `div[x-show="tab === 'home'"]` 전체 교체, `labels.js` 를 기존 chart.js 와 같은 `<script type="module">` 에서 import 해 `window.v2Labels` 로 둠)
- Create: `v2/static/labels.js`(`export const REASON_LABELS = {…}`, `export const FAILED_KEY_LABELS = {…}` — 객체는 JSON 문법으로만 적는다, `export function reasonLabel(code)`, `export function failedKeysText(raw)`)
- Modify: `v2/static/app.js`(표시 도우미 추가, 사유·실패 조건 글자는 `window.v2Labels` 를 쓴다)
- Test: `tests/v2/js/home.test.mjs`(새 파일, `harness.mjs` 방식), `tests/v2/test_static_lint.py`(`OWN` 에 `labels.js` 추가, `test_labels_match_server`: labels.js 의 두 `export const … = {…}` 블록을 정규식으로 잘라 `json.loads` 한 뒤 `v2.api_read.REASON_LABELS`·`FAILED_KEY_LABELS` 와 `assertEqual`)

**Interfaces:**
- Consumes: `/v2/api/status`(`mode_engine`, `paused`, `strategy.value`, `ticker`, `interval`), `/v2/api/assets`(`krw`, `coin`, `price`, `entry_price`, `tp_price`, `sl_price`, `round`), `/v2/api/basic`(엔진 Running 여부), `/v2/api/signals?limit=1`, `/v2/api/trades?limit=10`.
- Produces (app.js, 순수 함수로 export 해 시험): `homeView(status, assets, basic) -> {badges:[{text,cls}], total, krwCoin, pnl:{text,cls}, holding:null|{ticker, round, avg, tp:{label,price}, sl:{label,price}}}`, `signalSentence(row) -> {title:"최신 신호 · HH:MM 봉", text}`, `tradeRow(t, nowMs) -> {time, kind, kindCls, reason, amount}`.

문구·계산(그림 2-가):
- 배지 4개 순서: 모드(`LIVE`/`TEST`, 빨강 테두리) · 엔진 배지 — `basic.engine_running` 이 true 이고 `status.engine.level` 이 ok 면 「엔진 동작 중」(초록), running true·level delay 면 「엔진 동작 중 · 판단 지연」(노랑), running true·level unknown(`v2/status.py:46·56`) 이면 「엔진 동작 중 · 판단 보류」(회색), running false 면 「엔진 멈춤」(회색), basic 을 못 읽으면 「엔진 확인 중」(회색) · 「전략: <이름>」(파랑, EMA→「EMA (기존)」, MACD→「MACD (기존)」, PULLBACK→「눌림목 분할매수」) · 「일시정지 아님」 또는 「일시정지 중」(회색/노랑).
- 자산 카드: 「평가 합계」 = krw + coin×price, 원 단위 「3,042,600원」. 「원화 / 코인」 = `krw / coin×price`. 「평가손익」 = (price−entry)×coin 과 (price/entry−1)×100 → `+42,600 (+3.5%)`, 양수 빨강·음수 파랑, 보유 없으면 「—」.
- 보유 카드 제목 「보유 · <종목>」: 「분할 회차」 = 1차는 「—」 고정(`/v2/api/assets` round 는 1차에 항상 null — `api_read.py:260`, 최대 횟수는 2차에서 PULLBACK 설정으로 채움) · 「평균 매수가」 · 「익절 가격 (+N%)」(N = (tp/entry−1)×100, 소수 1자리, 빨강) · 「손절 가격 (−N%)」(파랑). 코인 0 이면 카드 본문 「보유 없음」.
- 최신 신호 카드: 제목 「최신 신호 · HH:MM 봉」, 본문 한 문장 — 매수 판단 통과 「매수 조건 충족」, 미통과 「매수 대기 — <실패 조건>」, 매도 발동 「매도 — <사유>」, 미발동 「보유 유지 — 익절·손절 가격 안」. 기록 없으면 「신호 기록이 없습니다」.
- 최근 거래 표: 머리 「시각 · 구분 · 사유 · 금액」. 시각 = 오늘이면 HH:MM, 어제면 「어제」, 그 전은 MM-DD(모두 KST). 구분 = type 별: `BUY` 「매수」(빨강) · `SELL` 「매도」(파랑) · `*_REJECTED` 「거절」(회색) · `HTS_SELL` 「외부 매도」 · `BUY_CANCELED` 「매수 취소」(`services/db.py:1659-1664`). 사유 = `reasonLabel`(대소문자 무시, 아래 표에 없으면 원래 값): `EMA_GC|MACD_GC|GOLDEN`→골든크로스, `PULLBACK`→눌림목, `TAKE_PROFIT|TP`→익절, `STOP_LOSS|SL`→손절, `EMA_DC|MACD_DC|DEADCROSS`→데드크로스, `TRAILING_STOP*`(접두 일치: `_FIXED`·`_RATIO`)→추적 손절, `STALE_POSITION`→정체 청산, `HTS_BUY|HTS_BUY_ADD`→외부 매수, `HTS_SELL`→외부 매도, `FORCE_BUY`→강제 매수, `FORCE_LIQUIDATE`→강제 매도, `BUY_FAILED_API`→주문 실패. 표는 서버 실제 값(2026-10-26 `SELECT reason, COUNT(*) FROM audit_trades GROUP BY reason`: HTS_BUY_ADD·HTS_BUY·EMA_GC·STOP_LOSS·TRAILING_STOP_FIXED·STALE_POSITION·force_buy·EMA_DC·force_liquidate·TAKE_PROFIT·BUY_FAILED_API·HTS_SELL·TRAILING_STOP_RATIO)을 모두 덮는다. 금액 = price×qty 반올림 원 단위, price 나 qty 가 없거나 0 이면 「—」(HTS_SELL 은 가격 없음). 이 표는 `v2/static/labels.js`(새 파일, 홈·로그 공용, export)와 서버 `v2/api_read.py` 의 `REASON_LABELS`·`FAILED_KEY_LABELS` 에 같은 값으로 두고, 두 표가 같은지 시험한다.
- 실패 조건 한글(`FAILED_KEY_LABELS`, 홈 최신 신호·감사 로그 공용): `NO_SIGNAL`→신호 없음, `SURGE_FILTER`→급등 필터, `WARMUP_IN_PROGRESS`→준비 중, `WEAK_ENTRY_FILTER`→약한 진입 필터, `COOLDOWN`→대기 시간, 그 밖은 원래 값(서버 2026-10-26 미통과 failed_keys 실제 값 4종 포함).

- [ ] **Step 1: 실패 시험** — `home.test.mjs`: (a) LIVE·running·EMA·paused=0 → 배지 글자 `["LIVE","엔진 동작 중","전략: EMA (기존)","일시정지 아님"]`; (b) krw 1,800,000·coin 1242.6·price 1000·entry 965.7 → total `"3,042,600원"`, pnl.cls `"up"`; (c) coin 0 → holding null; (d) `reasonLabel("TAKE_PROFIT")==="익절"`, `reasonLabel("TRAILING_STOP_FIXED")==="추적 손절"`, `reasonLabel("HTS_BUY_ADD")==="외부 매수"`, `reasonLabel("force_buy")==="강제 매수"`, `reasonLabel("XYZ")==="XYZ"`, `tradeRow({type:"HTS_SELL",price:null,qty:5})` 금액 「—」·구분 「외부 매도」, 매수 미통과 `["NO_SIGNAL"]` → `signalSentence` 「매수 대기 — 신호 없음」; (e) 어제 23:00 거래·지금 오늘 10:00 → time `"어제"`; (f) 빈 trades·빈 signals → 오류 없이 빈 문구.
- [ ] **Step 2: 실행 → 실패 확인** — `node --test tests/v2/js/home.test.mjs`
- [ ] **Step 3: 구현** — 위 Interfaces·문구대로. 7초 갱신 `_refreshCards` 의 signals 요청은 `limit=1`, `/v2/api/basic` 을 함께 읽는다.
- [ ] **Step 4: 실행 → 통과 확인**

### Task 3: 차트 — 그림 2-나 (60선·200선, 단추 줄, 공유 10초 문)

**Files:**
- Modify: `v2/static/chart.js`, `v2/static/app.js`(`startChart`), `v2/static/index.html`(차트 탭)
- Test: `tests/v2/js/chart.test.mjs`

**Interfaces:**
- Produces (chart.js): `createSharedRateGate(minIntervalMs, storage, key="v2.upbitGateAt", nowFn=Date.now) -> {allow(): boolean, msUntilOpen(): number}`(localStorage 에 마지막 허용 시각, 저장소 오류면 메모리로 대신); `upbitCandlesUrl(market, unitMin, toIso?)`(`&to=` 붙임); `mergeCandles(older, newer) -> ascending, 시각 중복 제거`; `maLines(closes, periods:number[]) -> {[period]: values}`; `createChartView(el).update(candles, markers, periods=[60,200], unitSec)`; `zoom(view, factor)`.
- 처음 그릴 때 200봉 2회(두 번째는 `to=` 가장 오래된 봉 시각, 문을 지나 10초 뒤) → 400봉, 이후 30초마다 최신 200봉 1회를 합친다. 400봉이 모이기 전에는 60선만 그리고 200선은 모인 뒤 그린다.
- 화면(그림 2-나): 머리 막대 「차트 · <종목> · <봉>」 + 모드. 단추 줄 4칸 `[<봉 단위>] [최근 200봉](선택됨) [확대 +] [축소 −]`(앞 두 칸은 표시용). 범례 「— 60선 · — 200선 · ▲ 매수 · ▼ 매도」(60선 주황, 200선 보라). 아래 카드 제목 「이 화면에서 보는 것」, 본문 「캔들, 60선·200선(눌림목 기준선), 봇이 실제로 사고판 자리. 손가락으로 확대·이동합니다.」 형성 중 봉 회색 표시는 유지(문구는 없앰). 차트 높이 300px.

- `createChartView.update` 인자가 바뀌므로 `app.js` 의 호출(`C.view.update(asc, d.markers, DEFAULT_PULLBACK_MA, unitMin * 60)`)도 함께 고친다. 바꿀 기존 시험: `test_static_lint.py` 의 `test_no_ma200` 삭제(E4 폐기).
- 업비트 응답이 429 이면 그 회는 실패로 두고 다음 30초 차례에 다시 한다(차트는 지금처럼 「갱신 실패 · 시각」).

- [ ] **Step 1: 실패 시험** — `chart.test.mjs`: (a) 같은 storage 를 쓰는 문 두 개: 첫째 allow true 직후 둘째 allow false, 10,000ms 뒤 true; (b) storage.setItem 이 throw 해도 allow 동작; (c) `mergeCandles` 중복 시각 1개만·오름차순; (d) `maLines(closes 400개,[60,200])` 200선 첫 199개 null; (e) `upbitCandlesUrl("KRW-BTC",1,"2026-10-26T00:00:00Z")` 에 `to=2026-10-26T00%3A00%3A00Z`.
- [ ] **Step 2: 실행 → 실패 확인**
- [ ] **Step 3: 구현** — app.js 는 `C.gate = createSharedRateGate(10000, window.localStorage)`.
- [ ] **Step 4: 실행 → 통과 확인**

### Task 4: 백테스터 — 그림 2-다 (업비트/바이낸스, 접힘, 요약)

**Files:**
- Modify: `v2/static/backtester.html`(배치 전체, 입력 id·기본값은 그대로)
- Create: `v2/static/bt_ui.js`(출처 토글·업비트 수집·요약·스윕 요약·중복 실행 막기)
- Test: `tests/v2/js/bt_ui.test.mjs`(새), `tests/v2/js/parity.test.mjs`(기본값 30개 시험이 새 배치에서도 통과하는지)

**Interfaces:**
- Consumes: `backtester.js` 전역 `run`, `fetchKlines`, `runSweep`, `stats`, `lastResults`, `lastCfgBase`, `sweepRows`, `downloadTrades`(이름으로 덮어쓰기·감싸기만, 파일은 안 바꿈); chart.js `createSharedRateGate`, `upbitCandlesUrl`.
- Produces (bt_ui.js, export 해 시험): `fetchUpbitKlines(market, src, days, {gate, fetchFn, nowFn, onProgress}) -> Promise<{t,o,h,l,c}[]>`(src `1m|3m|5m|1h` → 1·3·5·60분, `to=` 로 과거로 200개씩, 오름차순, 형성 중 봉 제외); `upbitCallCount(src, days) -> number`(1m·30 → 216); `briefSummary(stats) -> [{label,value,cls}]`; `sweepBrief(sweepRows, n=5) -> [{tp,sl,maxSplits,ret}]`.
- `window.fetchKlines` 를 감싼다: 출처가 업비트면 `fetchUpbitKlines`, 바이낸스면 원래 함수. `window.run` 을 감싼다: 실행 중이면 무시. 실행 전 `lastResults` 참조를 기억했다가 실행 뒤 다른 객체로 바뀌었을 때만 요약을 그린다(run 은 오류를 삼키고 이전 결과를 남기므로, 실패 때 이전 요약을 지우고 「결과 없음」).
- 업비트 종목 형식 `^KRW-[A-Z0-9]+$` 아니면 「업비트 종목은 KRW-XXX 형식입니다」 로 멈춤.
- 업비트 시각: `candle_date_time_utc` 에는 Z 가 없으므로 `Date.parse(s + "Z")` 로 UTC 로 읽는다(Issue #2).
- 실패 처리: 응답 429 면 문이 열릴 때까지(최소 10초) 기다려 같은 요청을 다시, 연속 3회 429 면 「업비트 요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요」로 멈춤(429 가 쌓이면 418 차단이 되므로 더 하지 않는다). 네트워크 오류(fetch 예외 — 업비트는 제한을 넘으면 CORS 오류로 끊을 수 있어 429 를 읽지 못함)는 문 대기 뒤 1회만 다시 하고, 또 실패하면 멈춘다. 그 밖의 HTTP 오류는 바로 멈춘다. 멈출 때 이유를 #status 에 보인다. 진행 문구 옆에 「이 화면을 켜 두세요(화면이 꺼지거나 다른 앱으로 가면 느려지거나 멈춥니다)」.
- 기본값: 출처 업비트, 봉 단위 = 엔진 봉 단위(`status.interval` 이 minute1·3·5·60 이면 그 값, 아니면 3분), 기간 30일. 원래 `backtester.html` 의 정적 기본값(3m·30·JTOUSDT)은 그대로 두고 bt_ui.js 가 열릴 때 바꾼다(parity 기본값 시험은 정적 값을 본다).
- 바꿀 기존 시험: `parity.test.mjs:38-39`(binance selected·upbit disabled 문자열 단언) → 「#dataSource select 에 binance·upbit 두 option 이 있고 숨김」으로 바꿈(R7 폐기, 결정 1026-19 2 가).
- 수집 중 이동 막기: 아래 메뉴 링크 클릭 때 `confirm("업비트 데이터 수집이 멈춥니다. 이동할까요?")`, 창 닫기·새로고침에는 `beforeunload`.

화면(그림 2-다, 위에서 아래로): 머리 막대 「백테스터」 + 모드 · 카드 「데이터 출처」 2칸 토글 `[업비트 (KRW)] [바이낸스]`(업비트 기본, 고르면 종목칸이 엔진 종목/`JTOUSDT` 로 바뀜, 원래 `#dataSource` select 는 숨겨 값만 맞춤) · 2열 칸 6개: 「종목」(#symbol) · 「봉 단위 · 기간」(#src + #days) · 「60선 / 200선」(#ma60p / #ma200p) · 「분할 최대 횟수」(#maxSplits) · 「익절 TP %」(#tp) · 「손절 SL %」(#sl) · `<details>` 「… 그 밖의 입력 11개(접힘)」(maType·pullbackP·slopeLB·minSlope·slopeDrop·buyOnGoldenCross·maxPullbackBuys·capital·fee·deadcross·compounding) · 빨간 큰 단추 「데이터 가져오기 + 백테스트」 · 진행 줄(#status, 업비트일 때 「업비트 데이터 수집 중… n / N회 · 남은 약 M분」) · 카드 「결과 요약」(「총 수익률」·「거래 수 / 승률」 `14회 / 64%`·「최대 낙폭」 `-4.1%`) · 카드 「여러 설정 비교 (파라미터 스윕)」(스윕 범위 입력은 `<details>` 접힘 + 「스윕 실행」, 결과 표 「TP · SL · 분할 · 수익률」 상위 5) · `<details>` 「자세한 결과」(원래 #summary·#depth·#weekly·#monthly·#sweepResult·차트 구역·주간·월간·스윕 CSV) · 아래 단추 2개 `[CSV 받기](downloadTrades) [설정 저장](파랑)` · 아래 메뉴(백테스터 선택됨).
- 전략 로직 설명 `<details class="note">` 는 「자세한 결과」 아래로 옮긴다(그림에 없음, 내용 보존).

- [ ] **Step 1: 실패 시험** — `bt_ui.test.mjs`: (a) `upbitCallCount("1m",30)===216`, `("3m",30)===72`; (b) 가짜 fetch(200개씩 3회, 최신순) → 결과 오름차순·중복 없음·`to=` 가 매번 더 과거, `candle_date_time_utc:"2026-10-26T00:00:00"` → t `Date.UTC(2026,9,26,0,0)`; (c) 가짜 문이 막으면 `msUntilOpen` 만큼 기다린 뒤 부름(nowFn 가짜 시계); (d) 형성 중 봉 제외; (e) `briefSummary({ret:6.2,trades:14,winRate:64.3,mdd:4.1})` → `["+6.2%","14회 / 64%","-4.1%"]`, ret 클래스 up; (f) 실행 중 `run()` 두 번째 호출은 원래 run 을 다시 부르지 않음; (g) 429 두 번 뒤 200 → 성공·요청 3회, 429 세 번 → 「업비트 요청이 너무 많습니다」 오류, fetch 예외 1회 뒤 200 → 성공, 예외 2회 → 멈춤; (h) 원래 run 이 lastResults 를 바꾸지 않으면 요약 「결과 없음」. parity: `backtester.js` sha 같음, 기본값 30개 같음.
- [ ] **Step 2: 실행 → 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 실행 → 통과 확인** — `node --test tests/v2/js/*.test.mjs`

### Task 5: 설정 저장 확인 창 — 그림 5-가·5-나

**Files:**
- Modify: `v2/static/save.js`(확인 창 마크업·문구), `v2/api_write.py`(source 허용값), `v2/params_schema.py`(symbol 규칙), `v2/static/backtester.html`(#saveArea → 화면 아래 단추와 창)
- Test: `tests/v2/js/save.test.mjs`, `tests/v2/test_api_write.py`, `tests/v2/test_params_schema.py`(있으면 그 파일, 없으면 test_api_write 안)

**Interfaces:**
- 서버: `req["source"]` 가 `"binance"` 또는 `"upbit"` 이면 받고, 이력 메모는 `"source=" + source`. 그 밖은 400 `bad_request`(지금과 같음).
- `params_schema.validate_params(raw, source="binance")`: symbol 규칙을 source 로 나눈다 — binance `^[A-Za-z0-9]{2,20}$`(지금, `params_schema.py:45`), upbit `^KRW-[A-Z0-9]{1,15}$`(검사 전 `.strip().upper()`, 화면 bt_ui.js 도 입력을 대문자로 맞춤). 엔진 파일에는 symbol 이 들어가지 않는 것(지금 `to_engine_file`)은 그대로.
- 화면 스냅샷: `makeSnapshot(getById) -> {params, source}`, source = 출처 토글 값.
- 창 문구(그림 5): 제목 「설정 저장 확인」 · 「시험한 데이터: <업비트|바이낸스> · <종목> · <봉 단위 글자>」 · 소제목 「지금 상태」 표 4행 「모드」·「동작 중인 전략」(EMA→「EMA (기존)」)·「엔진」(「동작 중」/「멈춤」)·「보유」(「없음」 또는 `<종목> <수량>`) · 단추 「저장만 하기」(파랑) · 「이 설정으로 동작」(비활성; 바이낸스면 「이 설정으로 동작 (사용 불가)」) · 안내: 업비트면 「「이 설정으로 동작」은 2차 공개 때 열립니다.」, 바이낸스면 「바이낸스 데이터 결과는 참고용입니다. 실제 매매에 쓰시려면 업비트 데이터로 다시 시험해 주십시오.」 · 「취소」. 시험 종목이 엔진 종목과 다르면 기존 경고 문구 유지. 저장 결과 문구는 지금 save.js 문구 유지.

- [ ] **Step 1: 실패 시험** — `test_api_write.py`: source `"upbit"`·symbol `"KRW-JTO"` 200·이력 메모 `source=upbit`; source `"upbit"`·symbol `"JTOUSDT"` 400 invalid_param symbol; source `"binance"`·symbol `"KRW-JTO"` 400; source `"x"` 400. `save.test.mjs`: 업비트 스냅샷 source `"upbit"`; 바이낸스 창에 「(사용 불가)」·참고용 문구; 업비트 창에 「2차 공개 때 열립니다」; 「이 설정으로 동작」 disabled 둘 다.
- [ ] **Step 2: 실행 → 실패 확인** — `python3 -m unittest tests.v2.test_api_write` · `node --test tests/v2/js/save.test.mjs`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 실행 → 통과 확인**

### Task 6: 로그 — 그림 2-라 (감사 로그 · 엔진 · 오류)

**Files:**
- Modify: `v2/api_read.py`(`LogsHandler`, SQL 상수), `v2/static/index.html`(로그 탭), `v2/static/app.js`(`loadLogs`)
- Test: `tests/v2/test_api_read.py`, `tests/v2/js/alpine_wiring.test.mjs`

**Interfaces:**
- `GET /v2/api/logs?kind=audit|engine|error&page=N` → `{"kind", "page", "pages", "rows":[{"id","timestamp","text","cls"}]}`. 한 쪽 12행(그림 「1 / 12」 예시와 무관, 휴대폰 한 화면 기준). `kind` 없으면 `audit`. 모르는 kind 400. `page > pages` 이면 마지막 쪽.
- audit(그림 2-라 「왜 샀는지, 왜 안 샀는지」) = 아래 넷을 시각 내림차순으로 합친 것:
  - `audit_trades` BUY/SELL → 「매수 체결 · <사유> · 평단 <entry>」(빨강) / 「매도 체결 · <사유>」(파랑)
  - `audit_trades` `*_REJECTED` → 「매수 건너뜀 — <note>」/「매도 거절 — <note>」(회색), `HTS_SELL` → 「외부 매도 · <note>」, `BUY_CANCELED` → 「매수 취소 — <note>」
  - `audit_buy_eval` overall_ok=1 → 「매수 조건 충족」, overall_ok=0 → 「매수 대기 — <failed_keys 를 parseFailedKeys 와 같은 표로 바꾼 글>」
  - `audit_sell_eval` triggered=1 → 「매도 조건 발동 · <trigger_key>」(triggered=0 은 넣지 않음 — 보유 중 매 봉 기록이라 「왜 안 샀는지」와 무관)
- 「매수 대기」 묶기: audit_buy_eval 미통과는 봉마다 쌓이므로(1분봉 하루 약 1,440행) 시각 순으로 이어지는 같은 failed_keys 구간을 1행으로 묶는다(「매수 대기 — <조건> (N회, HH:MM~HH:MM)」, 시각은 구간의 마지막). 방법: 네 표를 각각 `ORDER BY timestamp DESC, id DESC LIMIT 1200` 으로 읽어 Python 에서 합치고 묶은 뒤 12행씩 나눈다(쪽 수 = 묶은 결과 기준, 상한 100쪽). 이때 아래 COUNT 서브쿼리는 engine·error 에만 쓴다.
- engine = `logs` 전체(`[level] message`). error = `logs` 중 level 이 `ERROR|WARNING|CRITICAL`. 모든 SQL 은 `LIMIT` 포함, `db.query()` 로만 읽는다. 쪽 수는 전체를 세지 않고 `SELECT COUNT(*) AS n FROM (SELECT 1 FROM … LIMIT 1201) LIMIT 1` 로 상한 100쪽(12×100+1)까지만 센다(바깥 `LIMIT 1` 필수 — `v2/db.py:24-26` `_LIMIT_RE` 는 SQL 끝이 LIMIT 이어야 통과). 네 표 읽기 SQL 은 `ORDER BY timestamp DESC, id DESC LIMIT 1200`. 1201 이면 「100+」 쪽으로 보인다. 사유 글자는 Task 2 `reasonLabel` 과 같은 표를 서버 상수 `REASON_LABELS` 로 둔다.
- 바꿀 기존 시험: `tests/v2/test_api_read.py:692-713`(logs 응답 키 `logs`·50행) → 새 응답 키 `rows`·12행으로 바꿈.
- 화면: 3칸 토글 `[감사 로그] [엔진] [오류]` · 표 머리 「시각 · 내용」(시각 = 오늘 HH:MM, 어제 「어제」, 그 전 MM-DD) · 쪽 이동 「‹ 이전 · p / N · 다음 ›」 · 카드 「이 화면에서 보는 것」 본문 「봇이 왜 샀는지, 왜 안 샀는지, 언제 전환했는지. 기존 감사 로그와 같은 기록을 요약해 보여 드립니다.」

- [ ] **Step 1: 실패 시험** — `test_api_read.py`(기존 가짜 DB 도우미 사용): audit 에 체결 1·거절 1·HTS_SELL 1·매수 통과 1·매수 미통과 1·매도 발동 1·매도 미발동 1 → rows 6개(매도 미발동 제외, 「외부 매도 · 」 행 포함), 시각 내림차순, 미통과 행 글자가 「매수 대기 — 」로 시작, 거절 행 「매수 건너뜀 — 」; 같은 failed_keys 미통과 30행 연속 + 체결 1행 → 「(30회, …)」 1행으로 묶여 체결 행과 함께 1쪽에 보임; error 는 INFO 제외; `kind=x` 400; page 999 → 마지막 쪽; 모든 SQL 상수에 `LIMIT` 포함(기존 ALL_SQL 시험이 새 상수도 덮는지).
- [ ] **Step 2: 실행 → 실패 확인** — `python3 -m unittest tests.v2.test_api_read`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 실행 → 통과 확인**

### Task 7: 운용 — 그림 2-마 (표시만)

**Files:**
- Modify: `v2/static/index.html`(운용 탭), `v2/static/style.css`
- Test: `tests/v2/js/alpine_wiring.test.mjs`

- 화면(위에서 아래로 카드 4개): 「매매 전략」 — 「지금 전략」 오른쪽 굵게 `<이름> (기존)`, 파란 큰 단추 「백테스터 규칙으로 전환」, 회색 단추 「기존 전략으로 복귀 (지금은 해당 없음)」 · 「엔진」 — 2칸 「일시정지」·「엔진 정지」 · 「긴급 개입」 — 2칸 「강제 매수」·「강제 매도」(빨강 테두리) · 「운용 설정」 — 본문 「거래 시간 제한 등 (새 전략 운용 중일 때 여기서 바꿉니다)」. 모든 단추 `disabled`, 카드 묶음 위 한 줄 「운용 단추는 2차 공개 때 열립니다.」(결정 1026-19 5 나).

- 바꿀 기존 시험: `test_static_lint.py` 의 `test_operation_buttons_disabled`(8단추·「2차 공개 때 열림」) → 아래 6단추·문구로 바꿈.

- [ ] **Step 1: 실패 시험** — 운용 탭 단추 글자 순서 `["백테스터 규칙으로 전환","기존 전략으로 복귀 (지금은 해당 없음)","일시정지","엔진 정지","강제 매수","강제 매도"]`, 모두 disabled, 「2차 공개 때 열립니다」 1회.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과 확인 (`node --test tests/v2/js/alpine_wiring.test.mjs`)

### Task 8: 구버전 입장 버튼 한 번 누르기 — 그림 1-나

**Files:**
- Modify: `ui/v2_entry.py`
- Test: `tests/test_v2_entry_button.py`(새, Streamlit 은 `unittest.mock` 으로 대신)

- 문구 `신버전 대시보드 입장 ({mode})`, `use_container_width=True`(위아래 구버전 단추와 같은 폭). 누르면 그때 토큰을 만들고 `st.markdown('<meta http-equiv="refresh" content="0; url=/v2/?t=<token>">', unsafe_allow_html=True)` 뒤 `st.stop()` — `app.py:550` 의 기존 이동 방식과 같다. 허용 목록 밖 계정은 지금처럼 안 보임. 위치는 지금 그대로(「입장하기」 아래, 「파라미터 설정하기」 위 — `app.py:557-558`).
- 반영 시점: 구버전 화면은 엔진(tradebot) 재시작 때만 바뀐다(결정 4 가). 배포 요청서에 적는다.

- 바꿀 기존 시험: `tests/regressions/test_r_2026_10_23_v2_entry_button.py:67-68`(「📱 신버전 대시보드 (베타)」·link_button 0 단언, `scripts/regression_gate.sh:182-183` 가 돌림) → 새 문구 `신버전 대시보드 입장 (` 와 meta refresh 이동으로 바꿈. 회귀 시험의 원래 뜻(허용 목록 밖 계정에게 안 보임)은 유지.

- [ ] **Step 1: 실패 시험** — 허용 계정·버튼 눌림(mock True) → `st.markdown` 인자에 `url=/v2/?t=` 와 토큰, `st.stop` 1회; 버튼 글자 `신버전 대시보드 입장 (LIVE)`; 허용 밖 → `st.button` 호출 0.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과 확인 (`python3 -m unittest tests.test_v2_entry_button`)

### Task 9: 전체 검증·그림 대조 보고

- [ ] **Step 1: 자동 시험 전부** — `node --test tests/v2/js/*.test.mjs` · `python3 -m unittest discover -s tests/v2` · `python3 -m unittest tests.test_v2_entry_button` · `bash scripts/regression_gate.sh` → 모두 0 실패.
- [ ] **Step 2: 브라우저 실측** — `scripts/v2/dev_server.py`, Chrome DevTools 412×915(모바일)·360×800·1440×900(PC). 탭 5개 + 확인 창 2종(업비트·바이낸스)을 찍고, 승인 요청서 렌더(`pdftoppm -r 80`) 그림과 나란히 둔 대조표(그림 요소 → 화면 요소, 같음/다름)를 만든다. 가로 넘침 0, PC 폭 480px 가운데, 콘솔 오류 0.
- [ ] **Step 3: 업비트 백테스트 실측** — 업비트 3분·1일(약 1분 소요)로 실제 실행해 결과 요약이 나오는지, 그동안 차트 탭(다른 창)과 함께 열어 업비트 응답 429 가 0인지 네트워크 기록으로 확인.
- [ ] **Step 3-2: 구버전 입장 버튼 실측** — 로컬 Streamlit(`streamlit run app.py`, TEST 가짜 계정·허용 목록)에서 버튼 글자·위치(입장하기 아래)·한 번 누르면 `/v2/` 로 들어가는지 확인. 안 되면 원인과 함께 보고.
- [ ] **Step 4: 보고** — `docs/specs/v2-dashboard/impl-report-20261026-proposal-match.md`(그림 대조표·「사라지거나 옮겨지는 것」 표·바꾼 기존 시험 목록과 이유·시험 출력·캡처 목록) + Fable 번들 zip. 대조표에는 그림과 다른 곳을 근거와 함께 적는다: 그림 5-가 업비트 안내(「전환 확인(6절)으로 넘어갑니다」 → 5절 표 「1차는 저장만, 2차 공개 때 엽니다」), 운용 탭 「2차 공개 때 열립니다」 한 줄(결정 5 나), 예시 숫자(11개·종목·봉 단위).
- [ ] **Step 5: 문서 갱신** — `docs/specs/v2-dashboard/spec.md` 에 폐기 결정(E4·E10 예외 1025-19·R7·1025-18·1026-08)과 basic.js 삭제·125행 차트 줄(60선·200선)을 반영하고, `ui/v2_entry.py` docstring 의 「1차 배포 뒤 동결 파일」 문구를 이번 변경 사실로 고친다. 커밋은 사용자 승인 뒤. verifier → Fable → 사용자 보고. 커밋은 사용자 승인 뒤(`pages/dashboard.py` 버전 갱신 포함).
