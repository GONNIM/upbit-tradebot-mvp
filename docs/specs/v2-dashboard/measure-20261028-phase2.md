# 2차 구현 착수 전 실측 — 정지선 · 1단계 (plan-phase2.md 3·4절)

- 작성: 2026-10-27 22시대 (파일 이름은 계획서가 정한 `measure-20261028-phase2.md` 그대로 씀)
- 범위: 계획서 3절 정지선 Step 1~4, 4절 1-1~1-4. 코드 변경은 1-3 생성기(시험 파일)뿐이고 엔진은 바꾸지 않았다.

## 정지선

### Step 1 로컬 (10/27 22시대)
- `git rev-parse HEAD` = `7bdcf468587ab97bda884bd038302afffc7a8651` (= `origin/main`, fetch 뒤 확인). 계획 기대 「`12ec5a4` 또는 그 뒤 문서 커밋」과 맞음 — `7bdcf46` 은 `12ec5a4` 다음 문서 커밋(2차 계획 승인).
- `git log --oneline -3`: `7bdcf46` docs(v2) 2차 계획 승인 (…1752 → …2138) / `12ec5a4` docs(v2) 1차 배포 완료 보고 / `1747fcc` feat(v2) Task 4-0b.
- `git status`(Step 1 실행 시점): 추적 변경은 `docs/specs/v2-dashboard/HANDOFF.md` 1건(1027-18 완료 표시 2줄 — 직전 세션이 커밋 뒤 고친 것). 그 뒤 이 세션이 HANDOFF 표에 1027-19~21 행을 더 고쳤다. 미추적은 HANDOFF 0절이 적은 기존 목록(`.superpowers/`, krw-jto 분석 4, `tests/test_*.py` 7, `__pycache__`)과 같음.

### Step 2 서버 (SSH 읽기 전용 — 사용자 「1027-20 승인」, 10/27 22:32 KST)
- 서버 HEAD `1747fcc96c37f2d7409fcc8b25507e44c209ed39` (계획 기대 `1747fcc…` 와 같음). 서버 `git log` 맨 위 `1747fcc` — 문서 커밋 `12ec5a4`·`7bdcf46` 은 서버에 pull 하지 않음(HANDOFF 0절의 의도된 차이).
- tradebot `ExecMainStartTimestamp=Mon 2026-10-26 00:25:22 KST`, `NRestarts=0`. tradebot-v2 `Tue 2026-10-27 16:47:19 KST`.
- 서버 `pages/dashboard.py:495` 버전 `v1.2026.10.27.1522`.
- `mcmax33_active_strategy.txt` = `EMA`. `mcmax33_latest_params_PULLBACK.json` = `-rw------- root root 0` (0바이트·600, F17·F18 기대와 같음).

### Step 3 표식 (최근 1시간)
- `journalctl -u tradebot --since "1 hour ago" | grep -c "\[V2-CANDLES\]"` = 0.
- `journalctl -u tradebot-v2 --since "1 hour ago" | grep -c "status=429"` = 0.

### Step 4 판정
- 계획서 전제(서버 1747fcc·버전 1522·활성 전략 EMA·PULLBACK 파일 0바이트 600)와 모두 같다. 멈추지 않는다.

## 1-1 운용자산(`users.virtual_krw`) 갱신 경로 전수 — D10 근거

명령(로컬): `grep -rn "save_user(" --include='*.py' . | grep -v "^./tests"`, `grep -rn "virtual_krw" --include='*.py' app.py pages services engine core`, `grep -rn "UPDATE users" --include='*.py' services`.

| 곳 | 쓰기/읽기/전달 | 모드 | 내용 |
|---|---|---|---|
| `services/auto_verify.py:84` | 쓰기 | LIVE | 자동 검증 `save_user(user_id, name, krw_balance)` |
| `app.py:394` | 쓰기 | LIVE | 수동 계정 검증 `save_user(username, name, krw_balance)` (392 에서 세션 값도 덮음) |
| `app.py:521` | 쓰기 | TEST | 운용자산 직접 입력 `save_user(…, st.session_state.virtual_krw)` (517 `cash`) |
| `services/db.py:69-92` | 쓰기(함수) | — | `save_user` — `UPDATE users` 는 이 함수 한 곳뿐(`services/db.py:77`) |
| `app.py:307-315`, `app.py:487-489` | 읽기 | 둘 다 | DB 값으로 세션 복원 |
| `pages/set_config.py:412-429` | 전달 | 둘 다 | `params.cash` 또는 `accounts` 값을 `navigate_to` 인자로만 넘김 — `users` 에 쓰지 않음 |
| `pages/dashboard.py:685,2472,2606,2767`, `pages/audit_viewer.py:226`, `pages/set_buy_sell_conditions.py:388`, `pages/confirm_init_db.py:92,102` | 전달 | 둘 다 | URL·세션 전달만 |

- **판단:** `users.virtual_krw` 쓰기 경로는 계획 기대와 같다(LIVE 2곳 + TEST 1곳). 다른 쓰기 경로가 없으므로 T15 D10 범위는 계획대로 「로그인 화면의 LIVE 검증 2곳」이다. TEST 직접 입력(`app.py:521`)은 계획대로 막지 않는다.
- **참고(별도 테이블, D10 범위 밖):** `accounts.virtual_krw` 는 다른 경로로 쓰인다 — `pages/dashboard.py:154·157`(`create_or_init_account`·`update_account`), `pages/set_config.py:192`, `services/db.py:2295 update_account_from_balances`(호출: `app.py:399`, `services/auto_verify.py:89`, `engine/order_reconciler.py:534·741`). 엔진 TEST 잔고는 `accounts` 를 읽는다(`core/trader.py:246·322`). 계획 T5 의 `sizing_base` 는 `users.virtual_krw` 를 읽으므로(계획 540행) 이 경로는 D10 과 겹치지 않는다. T5 착수 때 「TEST 모드 sizing 기준 = users, 주문 가능 잔고 = accounts」 구분을 시험 이름에 남긴다.

## 1-2 서버 journal — 무거래 봉 빈도, 워밍업 (SSH 읽기 전용 — 사용자 확인 후)
- 실행: 10/27 22:3x KST, 사용자 「1027-20 승인」. 서버 DB 는 열지 않았다.
- **창 변경:** 계획서 창 「2026-10-27 00:00 ~ 2026-10-28 00:00」 은 실행 시점에 끝나지 않아 `--since '2026-10-26 22:32' --until '2026-10-27 22:32'`(끝난 24시간)로 셌다. 이 창 안에 tradebot 재시작 없음(기동 10/26 00:25:22).
- 무거래 봉: `grep -c 'CONFIRMED-NO-TRADE'` = 164줄, `closed_ts` 고유 158봉(같은 봉 줄이 6번 겹침). 실제 줄: `⏭ [CONFIRMED-NO-TRADE] closed_ts=2026-10-26 22:54:00 KST 무거래 봉 → Reconcile 계속 (지표 미반영, 봉 건너뜀)`.
- 처리 봉: `grep -c '\[CONFIRMED\] 봉 처리 완료'` = 322 (고유 `ts=` 322).
- 검색어 `\[CONFIRMED\] 봉 처리 완료` 는 재조회 경로 문자열 `[CONFIRMED] 재조회 후 봉 처리 완료`(`engine/live_loop.py:1763`)를 세지 않는다. 합이 480 으로 맞으므로 이 창의 재조회 처리 봉은 0 이다.
- 합 158 + 322 = 480 = 3분봉 하루 480봉. **무거래 봉 비율 158/480 = 32.9%** (KRW-JTO 3분).
- 워밍업(마지막 엔진 기동 10/26 00:25):
  - `[BOOT-RESUME] start` 00:25:27 → `success … elapsed=6.8s` 00:25:29.
  - `[WARMUP] REST 초기 데이터 요청 (attempt 1/5) | count=801` 00:25:30 → `REST 데이터 로드 완료 | bars=801` 00:25:31 (약 1초).
  - 그 사이 `[REST] 다중 호출 시작` 1줄(=요청 묶음 1개, `total_count=801`). 묶음 안 요청은 200봉씩(`core/rest_reconcile.py:245`) 5회.
  - `[WARMUP] 시드 방식=long_history bars=800`.
- 묶음 안 요청 사이에 0.1초 대기가 있다(`core/rest_reconcile.py:325-327` `if remain > 0: time.sleep(0.1)`). 대기만으로 초당 10회 이하이고, 실측은 5회·약 1초(≈ 초당 5회)다.
- **판단(D8):** PULLBACK 워밍업 최대 2,012봉(`_long_bars + 1`)이면 200봉씩 11회, 약 2~3초·묶음 1개로 추정한다. 신버전 캔들 중계(초당 4회)와 같은 초에 겹치면 9~10회에 닿을 수 있다. 이것은 spec D8 본문(`docs/specs/v2-dashboard/spec.md:47`)이 이미 적은 알려진 틈이다. 그래서 T3 에서는 새 시험·코드를 더하지 않고 Step 메모와 배포 관찰 항목(429·418 0)으로 둔다. 실측 뒤 필요하면 보정안을 사용자에게 올린다(Fable 질문 4).
- **커밋 버전:** 계획 4절 머리말의 「문서만 커밋, 버전 유지」는 따르지 않는다. 계획의 규칙 체크리스트와 project-rules 의 「버전 미갱신 커밋 금지」에 따라 커밋마다 `pages/dashboard.py` 버전을 갱신한다(Fable 질문 2).
- **T3 참고:** 엔진은 무거래 봉을 지표에 넣지 않고(위 줄), 업비트 fixture 도 빈 봉을 채우지 않는다(F6). 그래서 같은 봉 배열을 쓰는 T10 일치 시험에서는 양쪽이 같은 봉만 본다. 다만 무거래 봉이 32.9% 이므로 MA200 등 N봉 창이 덮는 실제 시간은 「N × 3분」보다 약 1.5배 길다(480/322). 이 점은 판정 차이가 아니라 해석 차이로 T3 주석에만 남긴다. 이 해석은 검수에서 확인받는다(미확인).

## 1-3 원본 `simulate()` Node 기준값 생성기
- 만든 파일: `tests/v2/js/pullback_reference.mjs`(생성기), `tests/v2/js/fixtures/pullback_cfg_base.json`(원본 HTML 기본값과 같은 cfg — `ema`, 60/200, 눌림 60, 기울기 20·0·0, 골든 매수 예, 분할 5, 눌림 5, TP 1.0, SL 1.5, 자본 10000, 수수료 0.05, 데드크로스 예, 복리 아니오).
- 원본 HTML 143~938행을 바이트 그대로 `vm` 에 넣고(`parity.test.mjs:17-18` 과 같은 자르기), 봉은 원본 `fetchKlines` 를 고정 입력 페이지로 돌려 만든다(업비트 fixture 는 `{bars:[…]}` 로 그대로 받음).
- 명령: `node tests/v2/js/pullback_reference.mjs tests/v2/js/fixtures/klines_a.json tests/v2/js/fixtures/pullback_cfg_base.json` → exit 0, `{"buys":[{signal_bar_t,fill_bar_t,round,trigger}…], "sells":[{bar_t,type,entries}…]}` 출력.
- 이식본 `run()`(harness) 거래 수와 생성기 매도 수:

| 세트 | 종목·봉 | 봉 수(생성기 / harness) | 매수(GOLDEN / PULLBACK) | 매도(TP / SL / DEADCROSS) | harness 거래 수 | 같음 |
|---|---|---|---|---|---|---|
| a | JTOUSDT 3m | 14,400 / 14,400 | 375 (29 / 346) | 136 (78 / 48 / 10) | 136 | 예 |
| b | BTCUSDT 5m | 17,280 / 17,280 | 280 (35 / 245) | 70 (25 / 9 / 36) | 70 | 예 |
| c | ETHUSDT 1m | 10,080 / 10,080 | 117 (21 / 96) | 30 (6 / 0 / 24) | 30 | 예 |

- 세 세트 모두 GOLDEN ≥ 1, PULLBACK ≥ 1, 매도 ≥ 1. 업비트 fixture 3세트는 T10 Step 0(사용자 확인 후 — 외부 내려받기)에서 받는다.

## 1-4 업비트 한도 재확인 (외부 문서 조회 — 사용자 「1027-20 승인」)
- 문서: `https://docs.upbit.com/kr/reference/rate-limits` (10/27 22시대 조회).
- 갱신일: `updatedAt: 2026-10-07T05:56:05.000Z` — v2 spec D8 의 「공식 문서 2026-10-07 확인」과 같은 판.
- 측정 단위: 시세 조회는 IP 단위(거래·자산은 포켓 단위). candle 그룹 **초당 최대 10회**.
- 429: 초당 한도 초과 — 다음 초 경계까지 기다린 뒤 재시도. 418: 429 반복 뒤 일시 차단(IP·포켓·연결 단위), 차단 시간은 응답에 담기고 반복 위반 시 점점 늘어남(고정 시간 없음).
- `Remaining-Req`: `sec` 가 남은 횟수, `min` 은 폐기 예정(쓰지 말 것).
- **판정:** spec D8 과 같다(IP 공유, candle 초당 10회, 418 조건). 바뀐 것 없음 — 멈추지 않는다.

## 1단계 종합
- 정지선: 서버·로컬 모두 계획 전제와 같음.
- 1-1: D10 범위 계획대로(LIVE 검증 2곳). `accounts` 테이블 경로는 범위 밖, T5 시험 이름에 구분을 남김.
- 1-2: 무거래 봉 32.9%, 워밍업 801봉 약 1초·5회 → 2,012봉 약 11회 추정.
- 1-3: 생성기 동작, 세 세트 모두 harness 거래 수와 같음.
- 1-4: 한도 바뀌지 않음.
- 다음: T1(전략 등록).
