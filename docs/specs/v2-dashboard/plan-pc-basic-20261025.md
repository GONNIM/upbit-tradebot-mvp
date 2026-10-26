# 신버전 PC 화면·기본 기능 블록 계획서 (2026-10-25, 2판)

**한 줄:** PC(641px 이상)는 「기본 기능 블록 + 원본 백테스터 구역」 한 페이지로 바꾸고, 모바일은 지금 화면 그대로 두되 홈 맨 위에 같은 기본 기능 블록을 넣는다. 「매매 중지/재개」는 구버전과 같이 실제로 동작한다.

- 2판 보완(10/25): verifier 2차 지적 반영 — 미실현은 창 제한 없는 종목 단위 직접 조회(구버전 2단계 포함, 서버 EXPLAIN TEMP B-TREE 없음), 실현은 구버전과 같은 50건, 탐침 9→10 연동 파일 3개.
- 2판(10/25): verifier 1차 「승인 요청 불가」 지적 반영 — 엔진 상태 표기(E17 충돌 → 사용자 결정 항목), 미실현 계산식 확정, 확인 창 문구, 모드 기준, logs 시각 형식, 쓰기 트랜잭션, spec 수정 목록·수용 기준 추가, 되돌리기 때 중지 상태 확인, 시험 목록 보강.

## 0. 근거 (사용자 결정)
| # | 결정 | 원문 요지 |
|---|---|---|
| 1025-14 | 버튼 숨김(18:41:55 완료) | 「1 숨김」 |
| 1025-18 | 모바일 그대로, PC 는 원본 백테스터 HTML 구역만 + 구버전 기본 기능 | 「PC 화면은 MA60_200_GoldenCross_Pullback_Backtester_2610201820.html 나오는 구역만 구현… 기존 누락 구버전 구역은 제외… 단 기본적인 기능 … 위 기능은 동일하게 제공한다. 즉 신버전 대시보드에서도 실제 사용자가 쉽게 진행할 수 있도록」 |
| 1025-19 | 1 가(매매 중지/재개 구버전과 같이 동작), 2 나(모바일 홈 위에도 기본 블록) | 「1025-19 1 가, 2 나」 |
- Fable 질의: `docs/fable/2026-10-25-pc-layout-2.md`·`-3.md`·`-4.md`(모두 「진행」).
- 투자자 승인 문서와의 관계: 승인 요청서 383행 「1차 공개 동안 운용 메뉴는 표시만 하거나 숨깁니다」와 달라진다(매매 중지/재개가 1차에 동작). 투자자 통보 문안 A 를 고쳐 알린다(6절).

## 1. 기본 기능 블록 (구버전과 같은 항목)
| # | 항목 | 구버전 근거 | 신버전 출처 |
|---|---|---|---|
| B1 | 제목 `📊 Dashboard (모드) : 계정님 --- v1.…` | dashboard.py:495 | 모드는 **엔진 실제 모드**(status `mode_engine`, spec 4.3), 계정은 세션, 버전은 `v2/db.py app_version()`(서버 `pages/dashboard.py` 버전 줄을 요청 때 읽음) |
| B2 | 모드 안내: TEST 경고 / LIVE 안내 문구 | dashboard.py:518-524 (문구 그대로) | status `mode_engine`. 입장 모드와 다르면 기존 불일치 경고도 함께 |
| B3 | 일시중지 배너(중지 중일 때만, 문구 그대로) | dashboard.py:529-532 | status `paused` |
| B4 | 🕒 현재 시각 `YYYY-MM-DD HH:MM:SS`(1초 갱신) | dashboard.py:538 | 브라우저 시계, Asia/Seoul 표기(구버전은 서버 시각) |
| B5 | 안내 「Upbit Trade Bot v1 상태 모니터링 페이지입니다.」 + 최종 상태 로그 `[시각] 메시지` | dashboard.py:545·568, services/db.py:296-326 | 새 API — 같은 SQL 을 `SQL_LAST_STATUS_LOG` 상수로(이모지 접두 9종, `level IN ('INFO','BUY','SELL')`, `ORDER BY timestamp DESC LIMIT 1`, idx_logs_user_ts 사용 — 서버 EXPLAIN 확인) |
| B6 | 트레이딩 엔진 상태 | dashboard.py:571-575 (Running 🟢 / Stopped 🔴) | status `engine`(E17: ok/delay/unknown). **표기는 사용자 결정 D-1**(아래 8절) |
| B7 | ⏸️ 매매 중지 / ▶️ 매매 재개 단추 | dashboard.py:694-714 | 새 쓰기 API(2절) |
| B8 | 🚪 로그아웃 | dashboard.py:716-719 | 새 API 로 신버전 세션 쿠키 `v2s` 삭제 → 구버전 첫 화면(`/`) 이동 |
| B9 | 💰 자산 현황 3칸 | dashboard.py:833-931 | 아래 1-1 |

### 1-1. B9 자산 현황 계산 (구버전과 같은 식)
- 보유 KRW: `virtual_krw`, 묶임이 있으면 「🔒 Lock: N KRW」(dashboard.py:835-836).
- `{종목} 보유량`: 가용 수량(소수 6자리), 「평가 N KRW」, 묶임이 있으면 「🔒 Lock: 수량 · 평가」. 가용 0 + 묶임 > 0 이면 「⛔ 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 (N개). 평가액은 가용 수량 기준이라 0원으로 보입니다.」(dashboard.py:838-855, WO-9).
- 💹 칸: **가용 수량 > 0 이면** 「💹 현재 포지션」 미실현 %, 아니면 「💹 최근 거래」 실현 %(dashboard.py:863 기준과 같음).
  - 미실현: (현재가 − 진입가)/진입가 × 100. 진입가는 구버전 `get_last_open_buy_order`(services/db.py:1844-2042)와 같은 단계로 구한다. 창(최근 N건) 제한 없이 종목 단위로 직접 조회한다.
    1. `SELECT id, COALESCE(avg_price, price), COALESCE(executed_at, updated_at) FROM orders WHERE user_id=? AND ticker=? AND side='BUY' AND (state IN ('completed','filled','FILLED') OR (state='CANCELED' AND executed_volume>0)) ORDER BY id DESC LIMIT 1`
    2. 1 의 결과가 있으면: 같은 종목 체결 SELL 의 `MAX(id)` 가 체결 BUY 의 `MAX(id)` 보다 크면 청산(구버전 `_last_buy_closed_by_later_sell`), 또는 `audit_trades` 에 그 BUY 시각 뒤 `type='HTS_SELL'` 이 있으면 청산(구버전 `_closed_by_external_sell`) → 「정보 없음」.
    3. 1 의 결과가 없으면 상태 조건 없이 같은 조회를 다시 하고(구버전 2단계, :2019-2032), 2 의 두 검사(이후 SELL·HTS_SELL)를 모두 적용.
    - 서버 대조(verifier 3차, 읽기 전용): 이 3단계 방식과 구버전 규칙이 서버 모든 종목 8개에서 결과가 같음(diff 0).
    - 서버 EXPLAIN(10/25 읽기 전용): 1·3·MAX 조회는 `idx_orders_user_ticker (user_id=? AND ticker=?)`, HTS_SELL 은 `idx_audit_trades_ticker_ts`, TEMP B-TREE 없음.
    - 알려진 차이 1개: 구버전의 정렬 키는 `COALESCE(executed_at, updated_at, timestamp)`, 신버전은 `id`. 서버 실측에서 모든 종목 BUY 인접 278쌍의 순서 뒤집힘 0건(verifier). 구현 때 서버 모든 종목에서 구버전 함수와 결과를 비교해 다시 확인하고, 시험에 고정한다.
  - 실현: 구버전과 같이 `SELECT ticker, side, price FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50`(idx_orders_user_id)에서 같은 종목의 가장 최근 SELL 과 그보다 이전의 가장 가까운 BUY 의 `price` 열(avg_price 아님)로 (SELL−BUY)/BUY × 100(dashboard.py:888-907). 50건 안에 그 종목 SELL 이 없으면 「N/A · 거래 없음」(구버전과 같음). 서버 값으로 다시 계산하면 −0.34%(사용자가 붙인 값과 같음, verifier 확인).
  - 현재가는 엔진 기록 가격과 기록 시각(E5). 구버전은 업비트 시세를 불러 값이 조금 다를 수 있다. 신버전 서버는 업비트를 부르지 않는다(D8).
- 구버전의 헬스 배지·데이터 수집 진행률·엔진 실행하기·파라미터 설정 단추는 사용자가 붙인 목록에 없어 넣지 않는다.

## 2. 매매 중지/재개 (1025-19 1 가)
- 동작: 단추 → 확인 창 → `POST /v2/api/pause {"paused": true|false}`(응답 전까지 단추 비활성) → 응답 뒤 status 를 다시 읽어 표시. 503 이면 「잠시 뒤 다시 시도해 주세요」.
- 확인 창 문구(중지): 「매매를 중지합니다(모드: 엔진 실제 모드). 중지 중에는 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. **이미 걸려 있는 주문은 취소되지 않고, 미체결 지정가 매수가 시장가로 바뀌는 처리는 계속될 수 있습니다.**」 재개: 「매매를 재개합니다.」
  - 근거: 엔진 게이트 core/strategy_engine.py:1086-1095(BUY·SELL 실주문 건너뜀). 게이트를 거치지 않는 경로: engine/order_reconciler.py:383-390 → core/strategy_engine.py:147 `convert_unfilled_limit_buy`(WO-24). 구버전 배너 문구도 같은 한계가 있다(사용자 보고 사항, 엔진은 이번에 바꾸지 않음).
- 서버: 실매매 DB 쓰기는 `v2/db.py set_paused(user, paused)` 한 함수에만 둔다.
  - `BEGIN IMMEDIATE` → `INSERT INTO users (username, trading_paused) VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET trading_paused = excluded.trading_paused`(services/db.py:933-942 와 같음, users.username UNIQUE 확인) → `INSERT INTO logs (user_id, timestamp, level, message) VALUES (?, ?, 'INFO', ?)`(services/db.py:221-231 insert_log 와 같은 열, timestamp 는 `db.now_kst_iso()` — services `now_kst()` 와 같은 KST ISO 형식, 문구 「⏸️ 매매 일시중지 (사용자 요청)」·「▶️ 매매 재개 (사용자 요청)」) → `COMMIT`, 실패하면 `ROLLBACK` 후 503.
  - busy_timeout 3000. 그동안 v2 응답이 최대 3초 멈출 수 있다(엔진 영향 없음, 7절).
  - 그 밖의 실매매 DB 쓰기는 계속 금지. lint 로 「쓰기 SQL 은 이 두 문장뿐, 테이블은 users·logs 뿐, 쓰기 연결은 set_paused 안에서만」을 고정한다.
- 보호: 기존 Origin 검사(handlers.py:29-34, POST 에 Origin 없거나 다르면 403)·세션·허용 목록(매 요청)·본문은 bool 만(아니면 400).
- 알림: 구버전 단추는 알림을 보내지 않는다(dashboard.py:693-714). 신버전도 보내지 않는다.

## 3. 화면 배치
### 3-1. PC (641px 이상) — 한 페이지
- `/v2/` 입장 뒤 넓은 화면이면 `index.html` 이 `backtester.html` 로 넘긴다. `<head>` 맨 앞 인라인 스크립트에서 `matchMedia('(min-width: 641px)')` 판정 뒤 `location.replace`(app.js·Alpine·차트 라이브러리를 불러오기 전 — PC 에서 홈 API 호출 0). 입장 302·쿠키 path `/v2/` 와 충돌 없음(verifier 확인).
- `backtester.html` 의 h1 앞에 `<div id="basic"></div>`, `</style>` 뒤에 `basic.css` 링크, 끝에 `basic.js`. 원본 style 7~36행·`backtester.js`(원본 143-938행과 같은 바이트)·입력 30개는 바꾸지 않는다. parity 시험(backtester.js 해시·입력 기본값 30개·실행 결과)을 그대로 통과해야 한다. 블록 안에는 id 붙은 input·select 를 정적 HTML 로 두지 않는다.
- 블록 모양은 원본 규칙(Arial·`.section`·`.grid` 4열·`.small`)을 따른다.
- backtester.html 은 세션 없이도 열리므로 basic.js 는 401·403 이면 「구버전에서 다시 들어와 주세요」를 블록 자리에 표시한다.
### 3-2. 모바일 (640px 이하)
- 홈 탭 맨 위(상태 카드 앞)에 같은 블록(모바일 카드 모양). 그 밖의 홈·차트·로그·운용·아래 탭은 그대로.
- 모바일에서 백테스터 페이지를 열면 블록은 숨긴다(CSS) — 지금 백테스터 화면 그대로.
- 운용 탭: 「일시정지·재개」 단추는 비활성 그대로 두고 옆 문구를 「홈 화면 위에서 할 수 있습니다」로, 「이 화면은 읽기 전용입니다」(index.html:139)는 「매매 중지/재개는 홈 화면 위 단추로 합니다. 그 밖의 기능은 2차 공개 때 열립니다.」로 고친다(test_static_lint 55-69 의 단추 8개·문구 조건 유지).
- 탭이 숨겨지면 호출을 멈추는 기존 규칙(spec 4.3)을 블록에도 적용한다.

## 4. 바뀌는 파일
| 파일 | 내용 |
|---|---|
| v2/api_read.py | GET `/v2/api/basic`(버전·최종 상태 로그·💹 칸 계산) — `SQL_` 상수 등록·LIMIT 규칙 |
| v2/api_write.py | POST `/v2/api/pause`, `/v2/api/logout` |
| v2/db.py | `set_paused` (유일한 실매매 DB 쓰기), `now_kst_iso` 사용 |
| v2/static/basic.js·basic.css | 기본 기능 블록 |
| v2/static/index.html·app.js·style.css | 모바일 홈 블록 자리, PC 넘김, 운용 탭 문구 |
| v2/static/backtester.html | 블록 자리·링크만 |
| scripts/v2/dev_server.py | 가짜 DB 에 orders 행 |
| scripts/v2/check_v2_unit_probe.py | 실매매 DB `BEGIN IMMEDIATE` → `ROLLBACK` 쓰기 가능 탐침(데이터 안 바뀜, 그 사이 잠금으로 엔진 쓰기가 밀리초 단위 대기할 수 있음 — 주석에 적음) — 탐침 9 → 10항목 |
| scripts/v2/check_v2_unit.sh | `EXPECTED_PROBE_LINES=9` → 10 |
| tests/v2/test_deploy_files.py | 탐침 개수 9 → 10(159행·262행 부근) |
| docs/operations/v2-runbook.md | 「탐침 9항목」 → 10항목, 새 항목 읽는 법 |
| tests/v2/*.py·tests/v2/js/*.mjs | 5절 |
| docs/specs/v2-dashboard/spec.md | 아래 목록 |
| pages/dashboard.py | 버전 줄만 |
- spec 수정: 4.1 99행(「실매매 DB 에는 1차에서 쓰지 않는다」 → 매매 중지 한 칸 예외), 4.3 운용 행(일시정지·재개는 1차에 홈 블록에서 동작), 4.3 디자인 기준(PC 641px 이상 배치), 4.7(일시중지는 요청 기록이 아니라 구버전과 같은 상태 직접 쓰기 — 엔진이 봉마다 읽음), 5절(P2 실매매 영향 없음 → 매매 중지는 영향 있음), E10·E15·E18 예외 1줄씩, E17(사용자 결정 D-1 결과), G2, 새 수용 기준 A19(쓰기 범위 users·logs 두 문장 — lint), A20(서버 유닛에서 쓰기 탐침 PASS), A21(PC 1440·모바일 412 실측, parity 통과).
- 엔진(core·engine·services·config.py) 변경 0. 구버전 화면 변경 0(버전 줄 제외).

## 5. 시험
- 새 API: 세션 없음 401, 허용 목록 밖 403, 다른 Origin·Origin 없음 403, pause 본문 bool 아님 400, pause 가 users.trading_paused 한 칸·logs 한 줄만 바꾸는지(임시 DB, 다른 테이블 행 수 불변), logs timestamp 형식(KST ISO, `T`·`+09:00`), 잠금 중 503·ROLLBACK, logout 이 쿠키를 지우는지·그 뒤 API 401.
- basic 계산: 미실현(보유·HTS_SELL 뒤·이후 SELL 뒤 = 정보 없음, 상태 조건 결과 없음 → 조건 없이 재조회 → HTS_SELL 뒤 = 정보 없음), 실현(price 열, 최근 50건 밖 = N/A), 가용 0 + 묶임(매도 불가 문구), 최종 상태 로그 없음. 구버전 함수(services/db.py)와 같은 고정 DB 에서 결과가 같은지 비교 시험(시험 코드에서만 services import).
- 고정 DB: test_api_read.py 의 CREATE 문에 orders(+idx_orders_user_id) 추가, 개수 시험(8·7) 갱신, 새 SQL 마다 TEMP B-TREE 금지 시험에 포함.
- lint: 실매매 DB 쓰기 SQL·테이블·연결 위치 고정, `services.*` import 금지 유지, 업비트 호출 0(D8), test_static_lint `OWN` 에 basic.js·basic.css 추가.
- JS: basic.js 표시(LIVE/TEST 문구, 중지 배너, 엔진 상태 표기, 단추 문구 전환, 확인 창 취소 시 요청 없음, 401·403 안내, 탭 숨김 시 호출 정지), PC 넘김 조건, alpine_wiring.
- parity 시험 그대로 통과. 게이트 `scripts/regression_gate.sh` exit 0.
- 브라우저 실측(로컬 dev_server 가짜 계정): PC 1440·1280, 모바일 412·360, 가로 스크롤 0, 단추 동작(가짜 DB trading_paused 바뀜), 로그아웃 뒤 API 401.

## 6. 배포 (별도 승인)
- 커밋·push → 서버 `git diff --stat` 이 v2/·scripts/v2/·tests/·문서·버전 줄뿐인지 확인 → pull(ff) → `systemctl restart tradebot-v2`(정적 파일 ETag 캐시 때문에 필수) → tradebot 기동 시각 그대로(엔진 재시작 없음 — 8-1 채택(결정 1025-21 가)으로 2차 배포 요청서 S3 에서 tradebot 1회 재시작) → check_v2_unit(쓰기 탐침 포함)·EXPLAIN(새 SQL 포함)·RSS → 허용 목록 복원(배포 요청서 단계 D7) → 사용자 PC·휴대폰 확인(강력 새로고침, 중지·재개 1회 시험은 사용자 결정) → 30분 관찰.
- 투자자 통보 문안 A 에 「PC 화면」·「매매 중지/재개 단추(손절·익절도 멈춤, 걸린 주문은 그대로)」 문장을 더해 운영자가 발송(체감 변경).
- 되돌리기: ① `sqlite3 -readonly …/tradebot_mcmax33.db "SELECT trading_paused FROM users WHERE username='mcmax33'"` 로 중지 상태 확인 — 1 이면 사용자에게 알리고 구버전 「매매 재개」로 풀게 한다(허용 목록을 비우면 신버전에서는 재개를 누를 수 없으므로 구버전 단추로만 해제 가능) ② 허용 목록 비우기(즉시) ③ 되돌리는 커밋·pull·v2 재시작.
- 투자자 통보는 배포 완료 확인 뒤 운영자가 발송하고 `docs/operations/investor-notice-log.md` 에 기록한다(project-rules 투자자 연락 원칙).

## 7. 위험
| 축 | 위험 | 막는 것 |
|---|---|---|
| 매매 | 중지 중 손절·익절도 멈춤, 걸린 주문은 그대로 | 확인 창 문구, 중지 배너 상시 표시 |
| 데이터 | 신버전 첫 실매매 DB 쓰기 | 함수 1개·SQL 2개 고정(lint), BEGIN IMMEDIATE, busy_timeout 3000, WAL |
| 데이터 | 쓰기 탐침이 잠깐 잠금을 잡음 | BEGIN IMMEDIATE → 바로 ROLLBACK(밀리초), 배포 점검 때 1회만 |
| 동시성 | 구·신버전 동시 누름 | UPSERT 한 칸 — 마지막 값이 남음, 응답 뒤 다시 읽음 |
| 응답 | 잠금 대기 최대 3초 동안 v2 응답 멈춤 | 엔진은 별도 프로세스라 영향 없음 |
| 모드 | 입장 모드와 엔진 모드가 다를 때 잘못 누름 | 제목·안내·확인 창 모두 엔진 실제 모드, 다르면 경고 |
| 보안 | 쓰기 API 위조 요청 | Origin 검사·SameSite=Lax·허용 목록 매 요청 |
| 세션 | 로그아웃은 이 브라우저 쿠키만 지움(서명 쿠키, 서버 폐기 없음) | TTL 12시간, 허용 목록 비우면 즉시 차단 |
| 화면 | PC 에 실시간 차트·로그 없음 — 2026-10-26 결정 1026-08 로 PC 도 차트·로그 있음(plan-pc-chart-20261026.md) | 사용자 결정(1025-18), 모바일에서 봄 |
| 되돌리기 | 중지 상태가 남은 채 되돌림 | 6절 ① |

## 8. 엔진 상태 판정 (D-1 다시 제안 — 사용자 지시 「구버전과 같은 동작이 정확하게 이루어져야 한다」)
- 구버전: 같은 프로세스 안 엔진 스레드의 `is_alive()`(engine_manager.py:98-108, dashboard.py:484 「실제 스레드 상태만 신뢰」) → Running 🟢 / Stopped 🔴.
  - 판정 대상은 바깥쪽 `_engine_runner_with_recovery` 스레드다(engine_manager.py:228-241). 이 스레드는 파라미터 로드·UpbitTrader 생성·이벤트 루프·예외 뒤 재시작 대기 sleep(60/300/900초, :319)까지 살아 있다.
  - 구버전은 화면을 열 때 자동 재개(dashboard.py:412-481)도 한다. 신버전은 **표시만** 같게 하고 자동 재개·DB 정정·알림은 하지 않는다(엔진 제어는 하지 않음).
- DB 기록(`thread_status`·`engine_status`)은 스레드 생존과 같지 않다(verifier 10/25): 1 은 스레드 시작 몇 초 뒤에 쓰이고(:240 → :426), 예외 뒤 재시작 대기 중에는 0 인데 스레드는 살아 있으며(:301-326·:474-477), 로그인 화면 「파라미터 설정하기」 → 저장은 엔진을 멈추지 않고 둘 다 0 으로 쓴다(pages/set_config.py:353-354, app.py:558-567). 그래서 DB 기록만으로는 구버전과 같게 만들 수 없다.

### 8-1. 제안 가 (권고) — 엔진 프로세스가 구버전 판정값을 직접 내보냄
- `scripts/tradebot_boot.py` 에 데몬 스레드 `engine_alive` 를 하나 더 둔다(boot_resume 스레드와 같은 방식 — 스레드 시작부를 try 로 감싸고 engine_manager import 는 스레드 안에서 지연 실행, 감시 스레드가 실패해도 `bootstrap.run` 은 반드시 호출됨을 시험으로 고정). 5초마다 같은 프로세스의 `engine_manager` 로 `_threads` 키(`get_active_user_ids()`) 사용자별 `get_running_mode(user) is not None`(키가 없는 계정은 false)(= 구버전 `is_running` 과 같은 `_threads[user].is_alive()`, 세션 참조 없음, engine_manager.py:110-123)을 계산해 `services/data/.engine_alive.json` 에 `{"pid":…, "at": KST ISO, "running": {"mcmax33": true, …}}` 로 쓴다(임시 파일 → os.replace, 권한 600).
- 신버전: **Running 🟢 = 파일의 `at` 이 15초 이내 그리고 `running[로그인 계정] == true`.** 그 밖(파일 없음·오래됨·false)은 Stopped 🔴.
- 구버전과의 차이: 최대 5초 + 화면 갱신 주기만큼 늦게 바뀐다. 감시 스레드가 멈추면 엔진이 돌아도 Stopped 로 보인다(안전한 쪽). 신버전 프로세스는 services/data 에 쓸 수 있어 이 파일을 바꿀 수 있으나 영향은 표시뿐이다(위험표). 그 밖의 모든 경우(시작 직후·재시작 대기·설정 저장 뒤·프로세스 사망)는 구버전과 같다 — 같은 스레드의 `is_alive()` 를 보기 때문. 프로세스가 죽으면 구버전 화면은 열리지 않고 신버전은 15초 뒤 Stopped.
- 매매 코드(core·engine 의 매매 경로)·DB 변경 없음. 바뀌는 것은 부팅 스크립트의 감시 스레드 1개(읽기·파일 쓰기만, 예외는 잡아 로그만). 이 스레드가 죽어도 엔진은 영향 없고 신버전은 Stopped 로 보인다.
- 반영하려면 **tradebot 1회 재시작**이 필요하다(배포 때 E1 조건 — 확정 봉 직후·미체결 0·경계 60초 전, BOOT-RESUME 확인).
- 시험: 감시 스레드 단위 시험(가짜 engine_manager — 살아 있음·죽음·예외 뒤 대기 중·사용자 2명·한 번도 시작 안 한 계정은 키 없음), 파일 원자 쓰기·권한, 감시 스레드 시작 실패에도 bootstrap.run 호출, 신버전 판정(15초 경계·파일 없음·깨진 JSON·키 없음 → Stopped).
- `.engine_alive.json` 은 서버 정리 스크립트(`/root/cleanup_tradebot_db.sh`)·cron·boot_resume 글롭(`tradebot_*.db`)의 대상이 아니다(서버 확인 10/25).
- 이 안을 고르면 배포 때 tradebot 재시작이 1회 들어간다(결정 1025-11 2 「엔진 재시작 없음」과 달라짐). 오늘 17:10:35 재시작과 같은 E1 조건으로 한다.

### 8-2. 제안 나 — 엔진 쪽 변경 없음 (DB 기록 + 프로세스 확인)
- Running = `thread_status.is_thread_running=1` 그리고 살아 있는 `tradebot_boot.py` 프로세스의 시작 시각 ≤ 그 기록 시각(`/proc` 읽기).
- 구버전과 다른 경우가 남는다: A 로그인 화면에서 파라미터 저장 뒤 엔진이 돌아도 Stopped(엔진 재시작까지 계속), B 예외 뒤 재시작 대기(최소 60초) 동안 Stopped, C 시작 직후 수 초 Stopped, F 서비스 실행 형식이 바뀌면 항상 Stopped.
- tradebot 재시작 불필요.

- 공통: 표시는 구버전 문구 그대로 「트레이딩 엔진 상태 Running 🟢 / Stopped 🔴」. E17(마지막 판단 시각) 배지는 모바일 홈 기존 자리에 그대로 둔다. spec E17 에 「기본 기능 블록 엔진 상태는 구버전과 같은 스레드 생존 기준」 한 줄, lint `test_no_stop_word_in_engine_badge` 는 기존 배지에만 적용.

## 9. 일정
- 계획 승인 → 구현·시험(약 반나절) → verifier·Fable → 구현 완료 보고·커밋 승인 → 배포 승인.
