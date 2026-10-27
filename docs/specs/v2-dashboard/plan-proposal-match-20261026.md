# 신버전 1차 화면 — 승인 요청서 v2 그림과 같게 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 신버전 대시보드의 모든 화면(홈·차트·백테스터·로그·운용·설정 저장 확인 창·구버전 입장 버튼)을 투자자 승인 요청서 v2 의 그림과 같은 배치·문구·순서로 바꾼다. 모바일·PC 공통(PC 는 휴대폰 화면 그대로).

**Architecture:** 화면은 지금처럼 `v2/static/index.html`(Alpine 한 페이지, 홈·차트·로그·운용 탭)과 `v2/static/backtester.html`(별도 페이지, 원본 계산 `backtester.js` 바이트 그대로)로 둔다. 두 페이지 모두 같은 머리 막대·같은 아래 메뉴(홈·차트·백테스터·로그·운용)를 쓰고, 탭 이동은 `/v2/#<tab>` 주소로 한다. 차트 탭의 업비트 시세는 브라우저가 직접 받는다(10초 문, 창끼리 localStorage 로 공유). 백테스터의 업비트 데이터는 v2 서버가 업비트 공개 시세를 대신 받아 보관하고 넘긴다(새 `v2/candles.py`, `GET /v2/api/candles` — 결정 1026-23 2 가). 브라우저 요청(Origin 머리)은 업비트가 10초당 1회로 묶어 1분봉 30일(216회)이 약 36분 걸리지만, 서버 요청은 초당 10회(IP 공유) 한도라 실측 44초(10/26, 재제안서 B-1).

**Tech Stack:** Alpine 3.14.1, lightweight-charts 4.2.0(vendor), Tornado(v2 서버), node --test, unittest, Streamlit(구버전 입장 버튼).

**Spec:** `docs/specs/v2-dashboard/investor-approval-20261021-v2.html`(=PDF) 1·2·5절 그림이 화면 기준이다. 결정 1026-19(2026-10-26, 사용자): 1 가(1차 화면을 그림과 같게) · 2 가(백테스터 업비트 데이터 = 브라우저 직접) · 3 가(PC = 휴대폰 화면 그대로) · 4 가(입장 한 번 누르기, 다음 엔진 재시작 때 반영) · 5 나(운용 단추는 「2차 공개 때 열림」 표시만). 결정 근거: `docs/fable/2026-10-26-proposal-match-scope-1.md`. 사용자 지시 「기존 요구사항은 모두 폐기」 — 폐기: 1025-18, 1025-19 의 홈 기본 블록 배치(매매 중지/재개 단추 자체는 결정 1026-23 1 가로 남김), 1026-08(PC 차트 확대), E4(차트 200선 제외), R7(1차는 Binance 만). 2차(새 전략 실매매·전환·운용 단추 동작)는 이 계획 범위 밖이며 다음 계획으로 이어 간다(사용자: 「승인 요청서 내용은 구현이 되어야 한다」).
**결정 1026-23(2026-10-27, 사용자 「1026-23 1 가, 2 가」):** 1 가 — 홈은 그림 2-가 배치·색을 따르되 원화·코인 잠김 수량과 기록 시각, 매매 중지/재개 단추, 로그아웃을 남긴다. 2 가 — 백테스터 업비트 데이터는 v2 서버가 받아 보관한다(목표: 1분·30일 1분 이내). 이에 따라 D8 은 「신버전 서버는 업비트 공개 시세(캔들)만 아래 상한·멈춤 조건으로 부른다. 계좌·주문 API 는 계속 부르지 않는다」로 바뀐다. 1026-19 2 가(업비트 = 브라우저 직접)는 차트 탭에만 남는다. 재제안서: scratchpad `proposal-home-backtester-20261026.md`, 근거 `docs/fable/2026-10-26-home-backtester-reproposal-1.md`(Fable 「진행」).

## Global Constraints

- `v2/static/backtester.js` 는 원본(`docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html` 143-938행)과 바이트 동일 유지 — parity 시험 그대로 통과.
- v2 서버의 업비트 호출은 `v2/candles.py` 한 곳, 주소 `https://api.upbit.com/v1/candles/minutes/{unit}` 하나뿐이다(결정 1026-23 2 가). 계좌·주문·인증 머리(`Authorization`·JWT)는 없다 — 시험으로 고정한다. 엔진·구버전 대시보드와 같은 서버 IP 의 `candle` 그룹 한도(초당 10회)를 나눠 쓰므로 Task 4-0 의 상한·멈춤 규칙을 지킨다. 브라우저의 업비트 호출(차트 탭)은 공유 문(`createSharedRateGate(10000)`)을 지난다.
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
| 홈 위 기본 블록(제목·안내 문장 「Upbit Trade Bot v1 상태 모니터링 페이지입니다.」·모드 안내·현재 시각·상태 로그·「트레이딩 엔진 상태 Running」 줄·자산 3칸) | 삭제. 엔진 상태·모드·일시정지는 홈 배지로, 자산은 자산 카드로 |
| 기본 블록의 「⏸️ 매매 중지/▶️ 매매 재개」·「로그아웃」 | 남김(결정 1026-23 1 가). 매매 중지는 배지 줄 바로 아래, 로그아웃은 머리 막대 오른쪽 |
| 홈 「상태」·「자산」·「포지션」·최신 신호 20건 | 그림 2-가 카드(자산·보유·최신 신호 1건)로 바뀜. 원화 잠김·코인 잠김·기록 시각·현재가 엔진 기록 시각은 자산 카드 아래 2줄로 남김(결정 1026-23 1 가) |
| PC 차트 탭 창 전체 크기(1026-08) | 휴대폰과 같은 크기 |
| 백테스터 결과 표(요약·분할 단계·주간·월간)·스윕 설정·차트·전략 설명 | 「자세한 결과」·「스윕 범위」 접힘 안으로 이동(내용 보존) |
| 백테스터 위 기본 블록(PC) | 삭제 |
| 운용 탭 「엔진 시작」·「운용 설정」 단추 | 그림 2-마 배치(엔진 시작 단추 없음, 운용 설정은 글 카드) |
| 「구버전으로 돌아가면 다시 로그인해야 합니다」 안내 | 머리 막대에서 지움(그림에 없음). 「구버전으로」는 지금처럼 구버전 로그인 화면으로 간다(Streamlit 세션이 따로라서) — 보고에 적음 |
| 백테스터 기본값 3분·바이낸스 | 업비트·엔진 봉 단위(지금 서버 1분)·30일. 엔진 종목은 서버가 미리 받아 둔 데이터라 수 초, 다른 종목은 첫 실행 데이터 약 44~55초(엔진 호출과 겹치면 늘어남) + 계산 시간. 다시 실행하면 새 봉만 받음 |

## Review Focus

1. 엔진 보호 — v2 서버 수집이 엔진의 확정 봉 조회와 같은 IP 한도(`candle` 그룹 초당 10회)를 쓴다. 엔진에는 429·418 처리가 없고 pyupbit 가 429 를 삼켜 None 을 돌려준다. 그래서 v2 는 초당 5회 상한, 응답 `Remaining-Req` 의 `sec` 가 4 이하이면 다음 초까지 쉼, 429 1회면 60초 멈춤, 418 이면 운영자가 풀 때까지 정지(파일로 남아 재시작 뒤에도 유지), 업비트 요청 매번 직전에 엔진 생존 파일 pid 를 읽어 바뀌면 그 자리에서 멈추고 5분 쉼, 수집은 서버 전체에서 동시에 1건만. Task 4-0 시험 + Task 9 Step 6 배포 관찰(엔진 「응답 없음」 4종·`[V2-CANDLES]` 배포 전후 건수). *(Task 4-0b 로 바뀜, 2026-10-27: 사용자 초당 4회, 429 1회 600초·24시간 안 2회째 정지, 엔진 봉 경계 −2~+20초 창)*
2. 백테스터 수집 중 「데이터 가져오기」를 또 누르거나 다른 탭으로 가는 경우 — 두 번째 실행은 막는다. 다른 탭 이동은 막지 않는다(서버가 끝까지 받아 보관하므로 돌아와 다시 누르면 보관분을 쓴다). Task 4 시험.
2-2. 차트 탭이 열린 창이 여럿인 경우 — 공유 문으로 합쳐 브라우저 업비트 호출이 10초 1회를 넘지 않아야 한다. Task 3 시험.
3. 보유가 없거나 거래 기록이 0건인 새 계정 — 홈 「보유」는 「없음」, 최근 거래는 「거래 기록이 없습니다」, 오류 없이 그려져야 한다. Task 2 시험.
4. 업비트 출처로 시험한 종목이 엔진 종목과 다른 채 「설정 저장」 — 확인 창에 다르다는 경고를 보이고 저장은 엔진 종목 기준(서버 기존 동작). Task 5 시험.
5. 로그 쪽 번호가 전체 쪽 수보다 큰 주소·빈 로그 — 마지막 쪽으로 맞추고 「기록이 없습니다」. Task 6 시험.

---

### Task 1: 공통 틀 — 머리 막대·아래 메뉴 순서·PC 휴대폰 폭·기본 블록 제거

**Files:**
- Modify: `v2/static/index.html`(머리 `header.top`, `#basic` → `#pause-row`, `nav.bottom`; `basic.css`·`basic.js` 링크는 유지)
- Modify: `v2/static/style.css`(641px 이상 PC 규칙 전부, `body.tab-chart` 규칙 삭제 → 모든 폭 480px 가운데)
- Modify: `v2/static/app.js`(`fitChart`·resize·`$watch` 제거, 주소 `#tab` 읽기·쓰기)
- Modify: `v2/static/chart.js`(`fitChartHeight` 삭제)
- Modify: `v2/static/basic.js`(기본 블록 그리기 삭제, 매매 중지/재개·로그아웃 제어만 남김 — 아래), `v2/static/basic.css`(남는 단추·알림 띠 규칙만), `tests/v2/js/basic.test.mjs`(사라진 칸 시험 삭제, pause·logout·확인 창 시험 유지)
- Test: `tests/v2/js/alpine_wiring.test.mjs`, `tests/v2/test_static_lint.py`, `tests/v2/js/basic.test.mjs`

**Interfaces:**
- Produces: `tabFromHash(hash: string) -> "home"|"chart"|"logs"|"ops"`(app.js, 모르는 값·`#backtester` 는 `"home"`); 아래 메뉴 마크업 순서 홈·차트·백테스터·로그·운용(백테스터는 `<a href="/v2/static/backtester.html">`, 나머지는 `go(tab)`); `go(tab)` 는 `history.replaceState(null, "", "#" + tab)`.
- 머리 막대: 홈 = 왼쪽 「신버전 대시보드」, 오른쪽 「<표시 이름>님 · 구버전으로 · 로그아웃」(구버전으로 = `href="/"` 링크, 로그아웃 = `<button id="logout-btn">`, 누르면 basic.js `logout()` — POST `/v2/api/logout` 뒤 `/` 로 이동, 지금 동작 그대로). 다른 탭 = 왼쪽 탭 제목(「차트 · <종목> · <봉>」「로그」「운용」), 오른쪽 모드(LIVE/TEST). 표시 이름: `/v2/api/basic` 응답에 `"display_name"` 키를 더한다(`SELECT display_name FROM users WHERE username=? LIMIT 1`, 비었으면 user_id).
- `/v2/api/basic` 은 남긴다(Task 2 배지가 `engine_running` 을 읽는다). `/v2/api/pause`·`/v2/api/logout` 도 남기고 홈 화면에서 부른다(서버 변경 없음, 기존 test_basic_pause 유지).
- basic.js 가 남기는 것(결정 1026-23 1 가): `confirmText`·`togglePause`(확인 창 → POST `/v2/api/pause` → status 다시 읽기, 실패 문구 GUIDE/BUSY/FAIL 그대로)·`logout`·`PAUSED_BANNER`. 그리는 곳은 두 군데뿐: 홈 배지 줄 바로 아래 `<div id="pause-row">`(단추 「⏸️ 매매 중지」 / 일시정지 중이면 「▶️ 매매 재개」, 응답 전 비활성, 실패 문구, 일시정지 알림 띠)와 머리 막대 `#logout-btn`. 알림 띠 문구의 「아래 '▶️ 매매 재개' 버튼」은 「위 '▶️ 매매 재개' 단추」로 고친다(띠가 단추 아래에 놓이므로). 지우는 것: `INFO_TEXT`·`kstClock` 현재 시각·`modeNotice`·상태 로그·엔진 상태 줄·`assetCells`·`pnlCell` 과 그 그리기. 갱신 주기(7초, 숨김이면 쉼)는 그대로.
- 바꿀 기존 시험(이유: 사용자 지시 「기존 요구 폐기」): `tests/v2/test_static_lint.py` 의 `OWN` 목록에 bt_ui.js(외부 주소 없음 — 업비트는 서버 경로로 받음)·labels.js(외부 주소 없음)를 넣음(basic.js 는 남김), `tests/v2/js/basic.test.mjs` 는 시험 이름 기준으로 — 삭제: 「제목·안내·최종 상태 로그·엔진 상태 문구」(94행)·「엔진 상태: engine_running false → Stopped 🔴」(107행)·「모드 불일치 경고와 엔진 모드가 제목에 쓰인다」(116행)·「일부 읽기 실패는 안내만 하고 나머지는 그대로 보인다」(237행 — basic 500·title·assets 단언, status 만 읽게 되므로 「status 읽기 실패 → 단추 비활성·안내 문구」 새 시험으로 바꿈)·「kstClock」(76행)·「모드 안내」(81행)·「자산 3칸」(291행)·「가용 0 + 묶임 > 0」(304행)·「💹 칸」(311행)·「현재가 없음이면 평가 0원」(326행) / 새 단언으로 바꿈: 「index.html: 홈 탭 맨 위 블록 자리」(356행 → 배지 줄 아래 `#pause-row`·머리 막대 `#logout-btn`·basic.css·basic.js 연결, 운용 탭 안내 「매매 중지/재개는 홈 화면 위 단추로 합니다.」 유지), 「backtester.html: h1 앞 블록 자리」(368행 → backtester.html 에 `id="basic"`·basic.js·basic.css 없음), 「PC 넘김 없음」(344행 → `tab-chart` 바인딩 단언 삭제, 넘김 스크립트 없음 단언 유지), 「PC 넘김 가드가 없다」(415행 → `getElementById("basic")` 대신 `pause-row`), 「401·403 이면 블록 자리에…」(223행 → `#pause-row` 자리) / 유지: 중지 배너와 단추 문구 전환(126행, 띠 문구만 새 문구), 확인 창 3개(141·151·162행), busy(191), 실패 문구(207), 숨김 tick(247), 7초 tick(267 — 「시계만 갱신」 부분 삭제), 로그아웃(280), 로딩 중(331 — 「모드 확인 불가」 문구 단언 삭제), 외부 주소 없음(381), 읽기 진행 중 강제 읽기(391). basic.js 의 7초 읽기는 `/v2/api/status` 하나로 줄인다(assets·basic 은 app.js 가 읽음 — 같은 DB 두 번 읽기 방지), `test_no_stop_word_in_engine_badge` 는 needle(「정상」·「지연 · 마지막 판단」·「판단 불가」)을 새 배지 글자(「엔진 동작 중」·「판단 지연」·「판단 보류」·「엔진 멈춤」·「엔진 확인 중」)로 바꾸고 「정지」 낱말 금지 단언은 유지, `test_signal_key_uses_kind`·`test_backtester_menu_link` 는 새 마크업에 맞춰 대상 선택자만 고침(단언 뜻 유지); `tests/v2/js/chart.test.mjs` 의 `fitChartHeight` 시험 삭제; `tests/v2/test_api_read.py` 의 basic 응답 키 시험에 display_name 추가.

- [ ] **Step 1: 실패 시험** — `alpine_wiring.test.mjs` 에 추가: `nav.bottom` 의 글자 순서가 `["홈","차트","백테스터","로그","운용"]`; `index.html` 에 `id="basic"` 없음, `id="pause-row"` 1개(홈 탭 안, `<details>` 밖 — project-rules 1-B), 머리 막대에 `id="logout-btn"` 1개; `basic.test.mjs`: 알림 띠 문구에 「위 '▶️ 매매 재개' 단추」, 그린 결과에 「Upbit Trade Bot v1」 없음; `tabFromHash("#logs")==="logs"`, `tabFromHash("#backtester")==="home"`, `tabFromHash("")==="home"`. `test_static_lint.py` 에 추가: `style.css` 에 `min-width: 641px` 없음, `body` 최대 폭 `480px`. `test_api_read.py`: basic 응답에 `display_name`(가짜 DB "Dev User").
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
- Consumes: `/v2/api/status`(`mode_engine`, `paused`, `strategy.value`, `ticker`, `interval`), `/v2/api/assets`(`krw`, `krw_locked`, `coin`, `coin_locked`, `price`, `price_at`, `updated_at`, `entry_price`, `tp_price`, `sl_price`, `round`), `/v2/api/basic`(엔진 Running 여부), `/v2/api/signals?limit=1`, `/v2/api/trades?limit=10`.
- Produces (app.js, 순수 함수로 export 해 시험): `homeView(status, assets, basic) -> {badges:[{text,cls}], total, krwCoin, pnl:{text,cls}, holding:null|{ticker, round, avg, tp:{label,price}, sl:{label,price}}}`, `signalSentence(row) -> {title:"최신 신호 · HH:MM 봉", text}`, `tradeRow(t, nowMs) -> {time, kind, kindCls, reason, amount}`.

문구·계산(그림 2-가):
- 배지 4개 순서: 모드(`LIVE`/`TEST`, 빨강 테두리) · 엔진 배지 — `basic.engine_running` 이 true 이고 `status.engine.level` 이 ok 면 「엔진 동작 중」(초록), running true·level delay 면 「엔진 동작 중 · 판단 지연」(노랑), running true·level unknown(`v2/status.py:46·56`) 이면 「엔진 동작 중 · 판단 보류」(회색), running false 면 「엔진 멈춤」(회색), basic 을 못 읽으면 「엔진 확인 중」(회색) · 「전략: <이름>」(파랑, EMA→「EMA (기존)」, MACD→「MACD (기존)」, PULLBACK→「눌림목 분할매수」) · 「일시정지 아님」 또는 「일시정지 중」(회색/노랑).
- 배지 줄 바로 아래: `#pause-row`(Task 1, basic.js 가 그림).
- 자산 카드: 「평가 합계」 = krw + coin×price, 원 단위 「3,042,600원」. 「원화 / 코인」 = `krw / coin×price`. 「평가손익」 = (price−entry)×coin 과 (price/entry−1)×100 → `+42,600 (+3.5%)`, 양수 빨강·음수 파랑, 보유 없으면 「—」. 그 아래 남기는 2줄(결정 1026-23 1 가): 「원화 잠김 / 코인 잠김」 = `krw_locked`(원) / `coin_locked`(코인 수량, 지금 `num()` 표기), 작은 글씨 「기록 시각 <updated_at> · 현재가 <price_at> 엔진 기록」(KST `HH:MM:SS`, 오늘이 아니면 `MM-DD HH:MM`, 값 없으면 「—」). 평가 합계는 지금처럼 잠김을 더하지 않은 값이며(그림과 같음), 잠김이 0 이 아니면 잠김 줄을 노랑으로 보인다.
- 보유 카드 제목 「보유 · <종목>」: 「분할 회차」 = 1차는 「—」 고정(`/v2/api/assets` round 는 1차에 항상 null — `api_read.py:260`, 최대 횟수는 2차에서 PULLBACK 설정으로 채움) · 「평균 매수가」 · 「익절 가격 (+N%)」(N = (tp/entry−1)×100, 소수 1자리, 빨강) · 「손절 가격 (−N%)」(파랑). 코인 0 이면 카드 본문 「보유 없음」.
- 최신 신호 카드: 제목 「최신 신호 · HH:MM 봉」, 본문 한 문장 — 매수 판단 통과 「매수 조건 충족」, 미통과 「매수 대기 — <실패 조건>」, 매도 발동 「매도 — <사유>」, 미발동 「보유 유지 — 익절·손절 가격 안」. 기록 없으면 「신호 기록이 없습니다」.
- 최근 거래 표: 머리 「시각 · 구분 · 사유 · 금액」. 시각 = 오늘이면 HH:MM, 어제면 「어제」, 그 전은 MM-DD(모두 KST). 구분 = type 별: `BUY` 「매수」(빨강) · `SELL` 「매도」(파랑) · `*_REJECTED` 「거절」(회색) · `HTS_SELL` 「외부 매도」 · `BUY_CANCELED` 「매수 취소」(`services/db.py:1659-1664`). 사유 = `reasonLabel`(대소문자 무시, 아래 표에 없으면 원래 값): `EMA_GC|MACD_GC|GOLDEN`→골든크로스, `PULLBACK`→눌림목, `TAKE_PROFIT|TP`→익절, `STOP_LOSS|SL`→손절, `EMA_DC|MACD_DC|DEADCROSS`→데드크로스, `TRAILING_STOP*`(접두 일치: `_FIXED`·`_RATIO`)→추적 손절, `STALE_POSITION`→정체 청산, `HTS_BUY|HTS_BUY_ADD`→외부 매수, `HTS_SELL`→외부 매도, `FORCE_BUY`→강제 매수, `FORCE_LIQUIDATE`→강제 매도, `BUY_FAILED_API`→주문 실패. 표는 서버 실제 값(2026-10-26 `SELECT reason, COUNT(*) FROM audit_trades GROUP BY reason`: HTS_BUY_ADD·HTS_BUY·EMA_GC·STOP_LOSS·TRAILING_STOP_FIXED·STALE_POSITION·force_buy·EMA_DC·force_liquidate·TAKE_PROFIT·BUY_FAILED_API·HTS_SELL·TRAILING_STOP_RATIO)을 모두 덮는다. 금액 = price×qty 반올림 원 단위, price 나 qty 가 없거나 0 이면 「—」(HTS_SELL 은 가격 없음). 이 표는 `v2/static/labels.js`(새 파일, 홈·로그 공용, export)와 서버 `v2/api_read.py` 의 `REASON_LABELS`·`FAILED_KEY_LABELS` 에 같은 값으로 두고, 두 표가 같은지 시험한다.
- 실패 조건 한글(`FAILED_KEY_LABELS`, 홈 최신 신호·감사 로그 공용): `NO_SIGNAL`→신호 없음, `SURGE_FILTER`→급등 필터, `WARMUP_IN_PROGRESS`→준비 중, `WEAK_ENTRY_FILTER`→약한 진입 필터, `COOLDOWN`→대기 시간, 그 밖은 원래 값(서버 2026-10-26 미통과 failed_keys 실제 값 4종 포함).

- [ ] **Step 1: 실패 시험** — `home.test.mjs`: (a) LIVE·running·EMA·paused=0 → 배지 글자 `["LIVE","엔진 동작 중","전략: EMA (기존)","일시정지 아님"]`; (b) krw 1,800,000·coin 1242.6·price 1000·entry 965.7 → total `"3,042,600원"`, pnl.cls `"up"`; (c) coin 0 → holding null; (d) `reasonLabel("TAKE_PROFIT")==="익절"`, `reasonLabel("TRAILING_STOP_FIXED")==="추적 손절"`, `reasonLabel("HTS_BUY_ADD")==="외부 매수"`, `reasonLabel("force_buy")==="강제 매수"`, `reasonLabel("XYZ")==="XYZ"`, `tradeRow({type:"HTS_SELL",price:null,qty:5})` 금액 「—」·구분 「외부 매도」, 매수 미통과 `["NO_SIGNAL"]` → `signalSentence` 「매수 대기 — 신호 없음」; (e) 어제 23:00 거래·지금 오늘 10:00 → time `"어제"`; (f) 빈 trades·빈 signals → 오류 없이 빈 문구; (g) krw_locked 5000·coin_locked 0 → 잠김 줄 글자 `"5,000 / 0"`·노랑 클래스, 둘 다 0 → 노랑 아님; updated_at 오늘 10:42:05 KST → 「기록 시각 10:42:05」, price_at null → 「현재가 — 엔진 기록」.
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

### Task 4-0: 서버 업비트 시세 중계·보관 (결정 1026-23 2 가)

**Files:**
- Create: `v2/candles.py`(수집기·보관·미리 받기), `tests/v2/test_candles.py`
- Modify: `v2/api_read.py`(`CandlesHandler`·`CandlesProgressHandler`, ROUTES), `v2/server.py`(`compress_response=True`, `_serve()` 에서 미리 받기 작업 시작), `tests/v2/test_basic_pause.py:525-532`·`tests/v2/test_server.py:230-244`(아래 「바꿀 기존 시험」)

**Interfaces:**
- 긴 수집은 배경 작업으로 돌리고 요청은 바로 답한다(nginx `/v2/` 의 기본 `proxy_read_timeout` 60초를 넘지 않게 — 서버 설정 변경 없음. verifier 2회 지적 4, PO 선택).
- `GET /v2/api/candles?market=KRW-JTO&unit=1&days=30` (로그인 세션 필요, `ReadHandler` 상속, 처리 함수는 `async def get` — `_guard` 는 동기라 쓰지 않고 아래 표로 직접 바꾼다).
  - 입력 검사: market `^KRW-[A-Z0-9]{1,15}$`(`.strip().upper()` 뒤), unit ∈ {1,3,5,15,60,240}, days 1~30 정수. 어긋나면 400 `{"error":"bad_request","field":…}`.
  - 보관분이 요청 기간을 덮고 새 봉이 2회 요청 안에 채워지면 그 자리에서 받아 200 `{"market","unit","days","bars":[[t_ms,o,h,l,c], …], "requests": n}` — bars 오름차순·시각 중복 없음·형성 중 봉 제외(봉 시작+unit분 > 지금이면 뺌), 요청 기간(지금−days일) 안의 봉만. `requests` = 이번에 업비트를 부른 횟수(0~2).
  - 그보다 많이 받아야 하면 배경 작업을 시작(같은 종목·봉 단위 작업이 이미 있으면 그것을 씀)하고 202 `{"job":"running","progress":{"market","unit","done","total"}}`. 화면은 progress 를 2초마다 읽다가 `active:false` 이고 `error` 가 없으면 같은 GET 을 다시 불러 200 을 받는다.
  - 409 `{"error":"busy","progress":{…}}` — 다른 종목·봉 단위의 **사용자** 작업이 진행 중. 미리 받기 작업이 진행 중이면 409 를 내지 않고, 미리 받기는 지금 요청까지 받은 봉을 보관하고 멈춘 뒤 사용자 작업이 시작된다(같은 종목·봉 단위면 미리 받기 작업을 사용자 속도 5회/초로 바꿔 이어 받는다). *(Task 4-0b 로 바뀜, 2026-10-27: 사용자 속도 = 초당 4회)*
  - 429 `{"error":"upbit_limit","retry_after":초}` — 429 뒤 60초 멈춤 또는 엔진 재시작 쉼 중. *(최종 검수 수정 2026-10-27: 보관분이 기간을 덮어 업비트 요청이 0회인 요청은 쉼 확인보다 먼저 보관분으로 200 `requests: 0` — 쉼은 업비트를 부르는 경로에만 건다. 418 정지 중에는 보관분도 내주지 않고 503.)* 503 `{"error":"upbit_blocked"}` — 418 정지 중(운영자 해제 전까지). 502 `{"error":"upbit_error"}` — 그 밖의 업비트 오류. *(Task 4-0b 로 바뀜, 2026-10-27: 사용자 초당 4회, 429 1회 600초·24시간 안 2회째 정지, 엔진 봉 경계 −2~+20초 창)*
  - 예외 → 응답 표: `UpbitLimit` → 429, `UpbitBlocked` → 503, `tornado.httpclient.HTTPClientError`(599 시간 초과 포함)·`OSError`·`ValueError`(응답 JSON 깨짐) → 502, `BadRequest` → 400, `sqlite3.Error`(설정 읽기) → 503 `db_unavailable`. 배경 작업 안의 예외는 progress 의 `error` 칸(`"upbit_limit"|"upbit_blocked"|"upbit_error"`)과 `retry_after` 로 전한다.
- `GET /v2/api/candles/progress` → `{"active":bool,"kind":"user"|"prefetch"|null,"market","unit","done","total","error":null|…,"retry_after":null|초}`. 단위는 모두 「요청 횟수」(화면 「n / N회」).
- `v2/candles.py`:
  - `UPBIT_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"` — 이 파일의 유일한 외부 주소. 요청 머리에 `Accept: application/json` 을 주고 `Origin`·`Authorization` 은 붙이지 않는다(Tornado 기본 머리 `Host`·`User-Agent`·`Accept-Encoding` 은 그대로). `tornado.httpclient.AsyncHTTPClient().fetch(…, request_timeout=10, raise_error=False)` 를 try/except 로 감싼다(599·연결 오류는 `raise_error=False` 여도 예외).
  - 경로는 호출할 때마다 `db.DATA_DIR` 을 읽는다(import 때 고정 금지 — `scripts/v2/dev_server.py:128-141` 의 임시 폴더 돌리기를 그대로 따르게).
  - `class Collector(fetch, sleep, now, data_dir_fn)` — 시험에서 가짜 fetch·sleep·시계를 넣는다. `async collect(market, unit, days, rate=5.0, kind="user") -> (bars, requests)`.
  - 상한(엔진 보호, 재제안서 B-3): 서버 전체에서 수집은 `asyncio.Lock` 하나로 동시에 1건. 요청 사이 최소 간격 1/rate 초(사용자 5회/초, 미리 받기 1회/초). 응답 머리 `Remaining-Req` 의 `sec` 가 4 이하이면 다음 요청 전 1초 쉰다. *(Task 4-0b 로 바뀜, 2026-10-27: 사용자 초당 4회, 429 1회 600초·24시간 안 2회째 정지, 엔진 봉 경계 −2~+20초 창)*
  - 429: 즉시 멈추고 `cooldown_until = now+60`. `WARNING` 로그 `[V2-CANDLES] status=429 market=… unit=…`.
  - 418: 즉시 멈추고 정지 파일 `<data_dir>/v2_candles/.halt.json`(600, 원자적 쓰기, `{"at","status":418,"body":응답 첫 200자}`)을 남긴다. 이 파일이 있으면 v2 를 재시작해도 수집하지 않고 `UpbitBlocked`. 해제는 운영자가 파일을 지울 때만(runbook 에 절차). `ERROR` 로그 `[V2-CANDLES] status=418 HALT`. (verifier 2회 지적 2, PO 선택 — 엔진과 IP 를 공유하므로 자동 재개하지 않는다.)
  - 엔진 재시작 쉼(Fable 권고 3·verifier 2회 지적 1·7): 업비트 요청 **매번 직전**에 `services/data/.engine_alive.json` 의 `pid` 를 읽는다. 처음 읽은 값은 기준으로만 둔다(쉬지 않음). 값이 바뀌면 진행 중 작업을 그 자리에서 멈추고(받은 봉은 보관) `cooldown_until = 그 pid 를 처음 본 시각+300`. 미리 받기 루프(~~60초~~ 600초, 최종 검수 수정 2026-10-27)도 매 회 pid 를 읽고, 바뀐 것을 발견하면 같은 규칙으로 쉼을 건다(수집이 없을 때 엔진이 재시작해도 그 뒤 300초 안의 사용자 요청은 429 — 업비트를 불러야 하는 요청만, 최종 검수 수정 2026-10-27). 파일이 없거나 깨지면 쉬지 않는다(엔진 멈춤 상태에서도 백테스트는 가능). 같은 pid 안에서 엔진 스레드만 다시 뜨는 경우는 감지하지 못한다(알려진 한계, 보고에 적음).
  - 보관: `<data_dir>/v2_candles/<market>_<unit>.json`(폴더는 처음 쓸 때 `mkdir(mode=0o700, exist_ok=True)`, 파일은 UMask 0077 로 600). 내용 `{"market","unit","bars":[[t,o,h,l,c],…]}`. 임시 파일(`.tmp`)에 쓴 뒤 `os.replace`. 30일보다 오래된 봉은 쓸 때 잘라낸다. 다시 받을 때는 지금부터 과거로 `to=` 200개씩 받다가 보관분의 마지막 봉 시각에 닿으면 멈추고 합친다(보관분 사이에 빈 곳이 있으면 그 구간도 받는다). 보관 파일은 미리 받기 대상 + 최근 쓴 3개까지(지금 허용 목록 1명이라 4개), 넘으면 미리 받기 대상이 아닌 것 가운데 가장 오래 안 쓴 것부터 지운다(미리 받기 대상 파일은 지우지 않는다). 파일 합계 30MB 초과면 오래된 것을 먼저 지운다. 파일 이름은 검사를 통과한 market·unit 으로만 만든다(경로 탈출 차단). 엔진 glob(`tradebot_*.db`, engine/boot_resume.py:54)과 겹치지 않는다.
  - 메모리: 업비트 응답 JSON 은 받는 즉시 `[t,o,h,l,c]` 로 바꾸고 원래 dict 는 버린다. 한 번에 한 종목만 메모리에 둔다.
  - 시각: `candle_date_time_utc` 에 Z 를 붙여 UTC 로 읽고(Issue #2) t 는 UTC 밀리초.
  - 미리 받기 `async prefetch_loop()`: `_serve()` 가 시작(dev_server 는 `_serve()` 를 쓰지 않으므로 로컬에서는 돌지 않는다 — 미리 받기는 단위 시험과 배포 관찰로 확인). v2 기동 300초 뒤부터 ~~60초마다~~ **600초마다** 한 번 돈다 *(최종 검수 수정 2026-10-27: 처리기 안 2회 요청이 1분봉 약 6시간치 빈 곳을 덮으므로 「엔진 종목 수 초」가 유지된다)*. 대상은 `.v2_allowlist` 사용자들의 현재 전략 설정(`db.active_strategy`·`db.strategy_params`, `ReadHandler._context` 와 같은 규칙)의 종목·봉 단위 가운데 unit 이 위 집합인 것. 엔진 생존 파일이 정상(`engine_alive_running` 이 그 사용자에 True)일 때만, 1회/초로 30일치를 채우고 그 뒤에는 새 봉만. 사용자 요청이 오면 위 409 규칙대로 내준다.
- 바꿀 기존 시험(결정 1026-23 2 가 — D8 변경): `test_basic_pause.py` 의 `test_v2_code_has_no_upbit_or_engine_imports` 는 `api.upbit.com` 금지를 `candles.py` 만 예외로 하고(나머지 금지어 `pyupbit`·`urllib.request`·`http.client`·`httpx`·`aiohttp`·`requests` import 은 candles.py 에도 유지), `test_server.py` 의 `test_server_code_has_no_upbit_host` 도 candles.py 만 예외. 새 단언: candles.py 의 `https://` 주소는 `UPBIT_URL` 하나, 파일에 `Authorization`·`jwt`·`/v1/accounts`·`/v1/orders`·`access_key` 문자열 없음. `test_server_import_graph_clean` 에 `v2.candles` 추가.

- [ ] **Step 1: 실패 시험** — `test_candles.py`(가짜 fetch 가 업비트 응답 모양 200개씩·최신순, 가짜 시계·sleep): (a) 입력 검사 — `KRW-../x`·`BTCUSDT`·unit 2·days 31 → 400; (b) 1분·30일 빈 보관 → fetch 216회, bars 43,200 이하·오름차순·중복 없음, 형성 중 봉 제외; (c) 보관분 마지막 봉이 10분 전 → 처리기가 그 자리에서 200·`requests` 1; 빈 보관 → 202 와 배경 작업, 끝난 뒤 다시 GET → 200; (d) 응답 머리 `sec=3` → 다음 요청 전 sleep(≥1초) 기록; (e) 429 → 그 뒤 60초 안 collect 는 fetch 0회·retry_after 60; (f) 418 → `.halt.json` 생김(600), 새 Collector(재시작 흉내)도 fetch 0회·503, 파일을 지우면 다시 받음; (g) pid — 처음 값은 쉬지 않음, 수집 도중 pid 가 바뀌면 다음 fetch 0회·받은 봉 보관·300초 뒤 재개, 수집이 없을 때 미리 받기 루프가 pid 변경을 발견하면 그 뒤 300초 안의 사용자 요청 429; (h) 다른 종목 사용자 작업 중 두 번째 요청 → 409, 같은 종목 → 같은 작업; (i) 미리 받기 진행 중 다른 종목 사용자 요청 → 미리 받기 fetch 멈춤·받은 부분 보관·사용자 작업 완료, 같은 종목이면 rate 가 5.0 으로 바뀜; (j) 보관 파일 600, `.tmp` 남지 않음, 5번째 종목 쓰면 미리 받기 대상이 아닌 것 가운데 가장 오래 안 쓴 파일 삭제(미리 받기 대상 파일은 남음), 30일 넘는 봉 잘림; (k) 요청 머리에 Origin·Authorization 없음; (l) 처리기: 세션 없음 401, 정상 200 응답 gzip — 시험 클라이언트는 `decompress_response=False` 로 요청해야 `Content-Encoding: gzip` 을 볼 수 있다(tornado http1connection.py:717-721); fetch 가 599·OSError 를 올리면 progress error `upbit_error`; (m) 미리 받기 — 기동 300초 전 0회, 엔진 생존 아님 0회, 정상이면 rate 1.0 으로 호출; (n) `db.DATA_DIR` 을 바꾸면 보관 폴더도 따라감. 바꾼 기존 시험 2건 통과.
- [ ] **Step 2: 실행 → 실패 확인** — `python3 -m unittest tests.v2.test_candles tests.v2.test_basic_pause tests.v2.test_server`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 실행 → 통과 확인** (같은 명령 + `python3 -m unittest discover -s tests/v2`)

### Task 4-0b: IP 차단(418)이 생기지 않게 — 엔진 경계 창 피하기·429 즉시 장기 멈춤 (사용자 결정 1027-05 4, 2026-10-27)

근거: 서버 journal(10/27 10시대, Fable 24시간 재집계) — 엔진은 3분 봉 경계 뒤 5초부터 5초마다 HTTP 1회로 확정 봉을 폴링하고, 봉이 보이는 눈금에서 확정 조회 1회 + `[REST] 다중 호출` 2회×배치 2 = **5회를 0.4초 안에** 보낸다. 24시간 「다중 호출 시작」 오프셋(180초 나머지): 5~11초 740건, 15~16초 8건, **20~92초 224건(90~92초 156건 — 무거래 봉)**, 92초 뒤 0. 경계 창만으로는 묶음의 약 76% 만 피한다. 또 겹쳐서 생긴 429 가 **엔진 요청**에 떨어지면 v2 는 자기 응답이 200 이라 모르고 계속 부를 수 있다(pyupbit 가 429 를 None 으로 삼키고 엔진은 1·2·4·5초 뒤 재시도). 업비트 418 은 429 뒤 요청이 이어질 때 생긴다(spec D8 의 공식 rate-limits 인용). 그래서 (0) v2 상한을 관측된 엔진 몰림과 합쳐 한도 아래가 되도록 낮춰 겹침을 줄이고(4 + 관측 묶음 5 = 9 ≤ 10 (관측값 기준이며 코드 상한이 아니다 — 구버전 화면 새로고침(캔들 3회)·엔진 기동(801봉, 5회 이상)·여러 엔진 동시 묶음이 같은 1초에 겹치면 10 을 넘을 수 있어, 보장이 아니라 창·쉼·429 멈춤으로 겹침을 줄이는 장치다. verifier 2026-10-27)), (가) 엔진 몰림이 가장 많은 구간을 피하고, (나) v2 쪽 429 가 쌓일 수 없게 한다.

**Files:** Modify `v2/candles.py`, `tests/v2/test_candles.py`, `docs/operations/v2-runbook.md`(96행 「초당 5회·429 → 60초」, 101행 「약 1분」, 429 정지 해제 절차), `docs/specs/v2-dashboard/spec.md`(D8 의 「초당 5회」와 「429 1회면 60초 멈춤」 둘 다), `docs/specs/v2-dashboard/deploy-request-20261027-proposal-match.md`(58행 「5회/초 약 45초+」, 89행 「최대 5회/초」·「429 60초」, 3절 정지 해제에 429 정지 추가).
**바꿀 기존 시험(상수 변경 때문 — 동작 회귀와 구분):** `tests/v2/test_candles.py:172-177` `test_rate_spacing`(rate 5.0·sleep ≤0.2 → `USER_RATE`·≤0.25), `:399-406` `test_same_market_prefetch_switches_to_user_rate`(`pre.rate == 5.0` → `USER_RATE`), `:549` 부근 `COOLDOWN_429` 를 쓰는 쉼 시험(60 → 600 에서도 뜻 유지). 끝난 뒤 `grep -rn "5회/초\|초당 5회\|429 → 60\|429 60초"` 를 위 문서 3개에 돌려 이력 문장 외 0건.

**Interfaces:**
- (0) 상한: `USER_RATE = 4.0`(요청 간격 ≥ 0.25초), `PREFETCH_RATE = 1.0` 그대로. v2 4 + 관측된 엔진 묶음 5 = 9 ≤ 10 (관측값 기준이며 코드 상한이 아니다 — 구버전 화면 새로고침(캔들 3회)·엔진 기동(801봉, 5회 이상)·여러 엔진 동시 묶음이 같은 1초에 겹치면 10 을 넘을 수 있어, 보장이 아니라 창·쉼·429 멈춤으로 겹침을 줄이는 장치다. verifier 2026-10-27). 로컬 실측 216회 54.1초는 이미 약 4회/초(응답 지연에 묶임)라 체감 비용은 작다.
- (가) 엔진 경계 창: `ENGINE_WINDOW_BEFORE = 2`, `ENGINE_WINDOW_AFTER = 20`(초, 15~16초 재판정 묶음 포함). 창 길이 기준 봉 단위 = 미리 받기 대상의 엔진 봉 단위들 — 매 요청마다 `_targets()`(DB·파일 읽기)를 부르지 말고 `prefetch_loop` 가 갱신하는 `self.prefetch_targets` 의 unit 집합을 쓴다. 대상이 없거나 읽을 수 없으면 1분(가장 보수적). 여러 단위면 모든 단위의 경계를 피한다. 경계 = UTC 에포크 초가 `unit*60` 의 배수인 시각. `_request` 가 업비트를 부르기 직전(pid 확인과 같은 자리) `now` 가 어느 경계의 `[b−2, b+20)` 안이면 창이 끝날 때까지 `sleep` 한 뒤 pid·쉼을 다시 확인하고 부른다. 사용자 수집·미리 받기 모두 적용. 진행률 응답은 그대로(기다림은 done 이 늘지 않을 뿐). *(Task 4-0b fix round 1 로 대체: 창 기준 = `.engine_alive.json` running 사용자 전원의 봉 단위(`self.window_units`), 못 읽으면 1분. `prefetch_targets` 는 정리 보호용)*
- (나) 429: 첫 429 → `COOLDOWN_429 = 600`(10분) 멈춤, `WARNING [V2-CANDLES] status=429`. 24시간 안 두 번째 429 → 418 과 같은 처리(메모리 정지 + `.halt.json` `{"at","status":429,"reason":"second 429 in 24h"}`, `ERROR [V2-CANDLES] status=429 HALT`) — 운영자 해제(파일 삭제 + tradebot-v2 재시작). 10분 멈춤과 24시간 셈이 v2 재시작으로 사라지지 않도록 `.halt.json` 과 같은 폴더의 `.cooldown.json` `{"until": epoch, "last_429": epoch}`(600, 원자적 쓰기)에 남기고 기동 때 읽는다.
- 체감(impl-report 에 적음): 1분 폴백(대상 없음·params 못 읽음 — `_targets()` 조건)은 60초마다 22초를 막아 다른 종목 첫 실행이 늘 창을 만난다. 처리기 안 2회 요청(엔진 종목 보관분 + 새 봉) 경로도 창 대기(최대 약 22초)에 걸릴 수 있다(nginx 60초 안). *(Task 4-0b fix round 1 로 대체: 창 기준 = `.engine_alive.json` running 사용자 전원의 봉 단위(`self.window_units`), 못 읽으면 1분. `prefetch_targets` 는 정리 보호용)*
- 기존 장치(PREFETCH_RATE 1, sec≤4 쉼, 동시 1건, pid 변경 300초, 418 정지, 보관분이면 쉼 중 200)는 바꾸지 않는다. USER_RATE 는 (0), 429 처리는 (나)로 바꾼다. 보관분만으로 답하는 경로(업비트 0회)는 창·쉼과 무관하게 지금처럼 200.
- 화면: 429 정지(.halt.json status 429)도 503 `upbit_blocked` 로 보인다(문구 그대로 「운영자 확인이 필요합니다」).

- [ ] **Step 1: 실패 시험** — (0) 사용자 수집의 연속 fetch 간격 ≥ 0.25초(가짜 시계); (a) unit 3, now = 경계+5초 → fetch 전에 sleep(≥15초) 기록, 그 뒤 fetch; 경계+25초 → sleep 없이 fetch; 경계−1초 → 창 끝(+20)까지 sleep; (b) 대상 없음 → 1분 창 적용; 대상 unit 1·3 둘 → 두 경계 모두 피함; (c) 첫 429 → retry_after 600, 그 뒤 600초 안 fetch 0; 새 Collector(재시작 흉내) 도 `.cooldown.json` 으로 600초 안 fetch 0; (d) 24시간 안 두 번째 429 → `.halt.json`(status 429)·UpbitBlocked·새 Collector 도 fetch 0, 파일 삭제 뒤 재개; 첫 429 뒤 24시간 넘어 두 번째 → 다시 10분만; 첫 429 → 새 Collector(재시작 흉내, `.cooldown.json` 의 last_429 읽음) → 10분 뒤 두 번째 429 → HALT; (e) 창 대기 중 pid 가 바뀌면 깨어난 뒤 fetch 0·쉼 300; (f) 보관분만 경로는 창 안에서도 200 즉시.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과(`python3 -m unittest tests.v2.test_candles`, v2 전체, JS 전체, regression_gate).
- [ ] **Step 5: 로컬 실측(맥 IP, dev 서버)** — 다른 종목(KRW-BTC) 1분·30일 첫 실행 시간과 429 수를 다시 잰다(가짜 계정 엔진 봉 단위 3분). 1분을 넘으면 넘는 그대로 보고한다. **75초(사용자가 결정 1027-05 때 본 숫자)를 넘으면 커밋 승인 전에 사용자에게 따로 묻는다.**

### Task 4: 백테스터 — 그림 2-다 (업비트/바이낸스, 접힘, 요약)

**Files:**
- Modify: `v2/static/backtester.html`(배치 전체, 입력 id·기본값은 그대로. 위 기본 블록 `<div id="basic">`(40행)과 `basic.css` 링크(37행)·`basic.js` 링크(160행)는 지운다 — 백테스터에는 매매 중지 단추를 두지 않음, 「사라지는 것」 표 「백테스터 위 기본 블록(PC) 삭제」)
- Create: `v2/static/bt_ui.js`(출처 토글·업비트 수집·요약·스윕 요약·중복 실행 막기)
- Test: `tests/v2/js/bt_ui.test.mjs`(새), `tests/v2/js/parity.test.mjs`(기본값 30개 시험이 새 배치에서도 통과하는지)

**Interfaces:**
- Consumes: `backtester.js` 전역 `run`, `fetchKlines`, `runSweep`, `stats`, `lastResults`, `lastCfgBase`, `sweepRows`, `downloadTrades`(이름으로 덮어쓰기·감싸기만, 파일은 안 바꿈); Task 4-0 `GET /v2/api/candles`·`/v2/api/candles/progress`.
- Produces (bt_ui.js, export 해 시험): `fetchUpbitKlines(market, src, days, {fetchFn, sleepFn, onProgress, pollMs=2000}) -> Promise<{t,o,h,l,c}[]>`(src `1m|3m|5m|1h` → unit 1·3·5·60, 같은 출처 `/v2/api/candles?market=&unit=&days=` 요청 — `credentials:"same-origin"`. 200 이면 바로 씀. 202 면 `/v2/api/candles/progress` 를 pollMs 마다 읽어 onProgress(done,total), `active:false` 이거나 `kind!=="user"` 이거나 market·unit 이 내 요청과 다르면(내 작업은 끝났고 미리 받기 등 다른 작업이 보이는 것) error 가 없는 한 같은 GET 을 다시 불러 200 을 받음(다시 202 면 이어서 기다림, 전체 상한 5분). 응답 bars `[t,o,h,l,c]` 를 `{t,o,h,l,c}` 로 바꿈); `upbitCallCount(src, days) -> number`(1m·30 → 216, 진행 줄 「전체」 표시용); `briefSummary(stats) -> [{label,value,cls}]`; `sweepBrief(sweepRows, n=5) -> [{tp,sl,maxSplits,ret}]`. bt_ui.js 는 `api.upbit.com` 을 부르지 않는다(시험).
- `window.fetchKlines` 를 감싼다: 출처가 업비트면 `fetchUpbitKlines`, 바이낸스면 원래 함수. `window.run` 을 감싼다: 실행 중이면 무시. 실행 전 `lastResults` 참조를 기억했다가 실행 뒤 다른 객체로 바뀌었을 때만 요약을 그린다(run 은 오류를 삼키고 이전 결과를 남기므로, 실패 때 이전 요약을 지우고 「결과 없음」).
- 업비트 종목 형식 `^KRW-[A-Z0-9]+$` 아니면 「업비트 종목은 KRW-XXX 형식입니다」 로 멈춤.
- 업비트 시각: 서버가 UTC 밀리초로 준다(Task 4-0).
- 실패 처리(서버 응답·progress error 기준, 브라우저는 다시 시도하지 않음): 409 → 「다른 업비트 데이터 수집이 진행 중입니다 (n / N회). 끝난 뒤 다시 눌러 주세요」, 429·error `upbit_limit` → 「업비트 요청 한도 — 약 N초 뒤 다시 시도해 주세요」(retry_after), 503 `upbit_blocked`·error `upbit_blocked` → 「업비트가 요청을 막았습니다. 운영자 확인이 필요합니다(바이낸스 데이터는 쓸 수 있습니다)」, 502·504·503 `db_unavailable`·error `upbit_error`·네트워크 오류·5분 상한 → 「업비트 데이터를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요」(503 은 body 의 error 값으로 가름), 401·403 → 「구버전에서 다시 들어와 주세요」. 멈출 때 이유를 #status 에 보인다.
- 기본값: 출처 업비트, 봉 단위 = 엔진 봉 단위(`status.interval` 이 minute1·3·5·60 이면 그 값, 아니면 3분), 기간 30일. 원래 `backtester.html` 의 정적 기본값(3m·30·JTOUSDT)은 그대로 두고 bt_ui.js 가 열릴 때 바꾼다(parity 기본값 시험은 정적 값을 본다).
- 바꿀 기존 시험: `parity.test.mjs:38-39`(binance selected·upbit disabled 문자열 단언) → 「#dataSource select 에 binance·upbit 두 option 이 있고 숨김」으로 바꿈(R7 폐기, 결정 1026-23 2 가 — 업비트 출처는 서버 경로).
- 수집 중 이동: 막지 않는다(서버가 끝까지 받아 보관하므로 돌아와 다시 누르면 보관분을 쓴다). 진행 줄 아래 「다른 화면으로 가도 서버가 계속 받아 둡니다」 한 줄.

화면(그림 2-다, 위에서 아래로): 머리 막대 「백테스터」 + 모드 · 카드 「데이터 출처」 2칸 토글 `[업비트 (KRW)] [바이낸스]`(업비트 기본, 고르면 종목칸이 엔진 종목/`JTOUSDT` 로 바뀜, 원래 `#dataSource` select 는 숨겨 값만 맞춤) · 2열 칸 6개: 「종목」(#symbol) · 「봉 단위 · 기간」(#src + #days) · 「60선 / 200선」(#ma60p / #ma200p) · 「분할 최대 횟수」(#maxSplits) · 「익절 TP %」(#tp) · 「손절 SL %」(#sl) · `<details>` 「… 그 밖의 입력 11개(접힘)」(maType·pullbackP·slopeLB·minSlope·slopeDrop·buyOnGoldenCross·maxPullbackBuys·capital·fee·deadcross·compounding) · 빨간 큰 단추 「데이터 가져오기 + 백테스트」 · 진행 줄(#status, 업비트일 때 「업비트 데이터 받는 중… n / N회」, 보관분만 쓰면 바로 「계산 중…」) · 카드 「결과 요약」(「총 수익률」·「거래 수 / 승률」 `14회 / 64%`·「최대 낙폭」 `-4.1%`) · 카드 「여러 설정 비교 (파라미터 스윕)」(스윕 범위 입력은 `<details>` 접힘 + 「스윕 실행」, 결과 표 「TP · SL · 분할 · 수익률」 상위 5) · `<details>` 「자세한 결과」(원래 #summary·#depth·#weekly·#monthly·#sweepResult·차트 구역·주간·월간·스윕 CSV) · 아래 단추 2개 `[CSV 받기](downloadTrades) [설정 저장](파랑)` · 아래 메뉴(백테스터 선택됨).
- 전략 로직 설명 `<details class="note">` 는 「자세한 결과」 아래로 옮긴다(그림에 없음, 내용 보존).

- [ ] **Step 1: 실패 시험** — `bt_ui.test.mjs`: (a) `upbitCallCount("1m",30)===216`, `("3m",30)===72`; (b) 가짜 fetch 가 `/v2/api/candles?market=KRW-JTO&unit=1&days=30` 에 200 → bars `[[t,o,h,l,c],…]` → `{t,o,h,l,c}` 배열, `api.upbit.com` 호출 0; (c) 202 → progress 3회(done 50·150·216, 마지막 active false) 뒤 같은 GET 다시 → 200, onProgress 3회; progress 가 `active:true, kind:"prefetch"`(또는 다른 market) 이면 기다리지 않고 같은 GET 다시; (d) 409·429(retry_after 60)·503 upbit_blocked·502·504·401·progress error upbit_limit 각각 위 문구로 멈춤, 5분 상한(가짜 시계) 넘으면 멈춤; (e) `briefSummary({ret:6.2,trades:14,winRate:64.3,mdd:4.1})` → `["+6.2%","14회 / 64%","-4.1%"]`, ret 클래스 up; (f) 실행 중 `run()` 두 번째 호출은 원래 run 을 다시 부르지 않음; (g) bt_ui.js 원문에 `api.upbit.com` 없음; (h) 원래 run 이 lastResults 를 바꾸지 않으면 요약 「결과 없음」. parity: `backtester.js` sha 같음, 기본값 30개 같음.
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

- 화면(위에서 아래로 카드 4개): 「매매 전략」 — 「지금 전략」 오른쪽 굵게 `<이름> (기존)`, 파란 큰 단추 「백테스터 규칙으로 전환」, 회색 단추 「기존 전략으로 복귀 (지금은 해당 없음)」 · 「엔진」 — 2칸 「일시정지」·「엔진 정지」 · 「긴급 개입」 — 2칸 「강제 매수」·「강제 매도」(빨강 테두리) · 「운용 설정」 — 본문 「거래 시간 제한 등 (새 전략 운용 중일 때 여기서 바꿉니다)」. 모든 단추 `disabled`, 카드 묶음 위 한 줄 「운용 단추는 2차 공개 때 열립니다. 매매 중지/재개는 홈 화면 위 단추로 합니다.」(결정 1026-19 5 나, 1026-23 1 가 — 꺼진 「일시정지」 단추를 보고 중지할 수 없다고 오해하지 않게).

- 바꿀 기존 시험: `test_static_lint.py` 의 `test_operation_buttons_disabled`(8단추·「2차 공개 때 열림」) → 아래 6단추·문구로 바꿈.

- [ ] **Step 1: 실패 시험** — 운용 탭 단추 글자 순서 `["백테스터 규칙으로 전환","기존 전략으로 복귀 (지금은 해당 없음)","일시정지","엔진 정지","강제 매수","강제 매도"]`, 모두 disabled, 「2차 공개 때 열립니다」 1회, 「매매 중지/재개는 홈 화면 위 단추로 합니다」 1회.
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
- [ ] **Step 3: 업비트 백테스트 실측(로컬 개발 서버, 로컬 맥 IP — 서버 IP 에서 재지 않음)** — (a) 빈 보관 상태에서 업비트 1분·30일·KRW-BTC 를 「데이터 가져오기 + 백테스트」로 실행해 단추 누름부터 결과 요약까지 시간을 잰다(목표: 데이터 ≤55초, 전체 60초 이내 — 넘으면 계산 시간·전송 시간을 나눠 보고). (b) 같은 조건 다시 실행 → 바로 200, 응답 `requests` ≤2, 데이터 수 초. (c) 개발 서버 로그에 업비트 429 0건, 첫 실행의 progress `total` 216·`done` 216. (d) 수집 중 v2 프로세스 최대 메모리(`resource.getrusage(RUSAGE_SELF).ru_maxrss` — macOS 는 바이트, Linux 는 KB 단위, 또는 `/usr/bin/time -l`) 기록 — 150MB 의 절반 아래여야 함. (e) 차트 탭 다른 창을 함께 열어 브라우저 업비트 응답 429 0건.
- [ ] **Step 3-2: 구버전 입장 버튼 실측** — 로컬 Streamlit(`streamlit run app.py`, TEST 가짜 계정·허용 목록)에서 버튼 글자·위치(입장하기 아래)·한 번 누르면 `/v2/` 로 들어가는지 확인. 안 되면 원인과 함께 보고.
- [ ] **Step 4: 보고** — `docs/specs/v2-dashboard/impl-report-20261026-proposal-match.md`(그림 대조표·「사라지거나 옮겨지는 것」 표·바꾼 기존 시험 목록과 이유·시험 출력·캡처 목록) + Fable 번들 zip. 대조표에는 그림과 다른 곳을 근거와 함께 적는다: 그림 5-가 업비트 안내(「전환 확인(6절)으로 넘어갑니다」 → 5절 표 「1차는 저장만, 2차 공개 때 엽니다」), 운용 탭 「2차 공개 때 열립니다」 한 줄(결정 5 나), 예시 숫자(11개·종목·봉 단위).
- [ ] **Step 5: 문서 갱신** — `docs/specs/v2-dashboard/spec.md` 에 폐기 결정(E4·R7·1025-18·1026-08)과 결정 1026-23(D8 47행·100행 고침: 공개 캔들만·상한·멈춤 조건, 계좌·주문 0 / 234행 수용 기준 A14: 「`v2/candles.py` 의 `UPBIT_URL` 1곳만 예외, `pyupbit`·계좌·주문 경로 0」 / 145행 Upbit 출처 = 서버 중계·보관 / basic.js 는 매매 중지·로그아웃만 남김)·125행 차트 줄(60선·200선)을 반영하고, `docs/operations/v2-runbook.md` 에 `services/data/v2_candles/` 폴더(600, 지워도 다시 받음)와 `[V2-CANDLES]` 로그 확인 줄, 418 정지 해제 절차(원인 확인 → `services/data/v2_candles/.halt.json` 삭제, 엔진 시세 조회 정상 확인 뒤), 끄는 방법(`systemctl stop tradebot-v2` — 엔진 영향 없음, 또는 보관 폴더 유지한 채 tradebot-v2 이전 커밋으로 되돌림)을 더하고, `ui/v2_entry.py` docstring 의 「1차 배포 뒤 동결 파일」 문구를 이번 변경 사실로 고친다. 커밋은 사용자 승인 뒤. verifier → Fable → 사용자 보고. 커밋은 사용자 승인 뒤(`pages/dashboard.py` 버전 갱신 포함, 보고에 「버전: 구 → 신」).
- [ ] **Step 6: 배포 뒤 관찰(배포 요청서에 그대로 옮김 — 배포는 따로 승인)** — 출처는 `journalctl -u tradebot`(엔진)·`journalctl -u tradebot-v2`(v2). (a) 배포 전 24시간과 배포 뒤 24시간의 엔진 「응답 없음」 4종 건수를 비교한다: `[REST] Batch … 응답 없음`(core/rest_reconcile.py:280-284), `[실시간 API] 응답 없음`(core/data_feed.py:1068), `[백필] API 응답 없음`(:1239), `[SYNC-FILL] API 응답 없음`(:284). 배포 뒤가 배포 전보다 늘면 tradebot-v2 를 멈추고 보고한다. (b) `[V2-CANDLES]` 건수·status 별 수(429·418 은 0 이어야 함). (c) 미리 받기 확인: 기동 약 5분 뒤 수집 시작, 1회/초 216회라 `services/data/v2_candles/` 의 엔진 종목 파일(600)은 기동 약 9분 뒤 생김(verifier 수정 2026-10-27), 그 뒤 운영자 계정으로 엔진 종목 1분·30일 백테스트를 눌러 데이터가 수 초 안에 오는지(브라우저 네트워크 기록의 `/v2/api/candles` 응답 시간). (d) 엔진 종목이 아닌 종목으로 1분·30일 수집을 하는 동안 `systemctl show tradebot-v2 -p MemoryCurrent` 를 1초마다 읽어 최대값을 기록(서버 systemd 249 에는 MemoryPeak·memory.peak 가 없음, 150M 의 절반 아래여야 함). 같은 때 `/sys/fs/cgroup/system.slice/tradebot-v2.service/memory.stat` 의 `anon` 과 `file` 을 따로 기록한다(MemoryCurrent 에는 페이지 캐시가 들어 있다) *(최종 검수 수정 2026-10-27)*. (e) project-rules 1-A 3층: 운영자에게 브라우저 새로고침을 요청해 홈 화면 문구·단추 위치를 확인받는다. (f) 배포 완료 보고에 3점(로컬·서버 HEAD·버전, ExecMainStartTimestamp)과 「버전: 구 → 신」.
