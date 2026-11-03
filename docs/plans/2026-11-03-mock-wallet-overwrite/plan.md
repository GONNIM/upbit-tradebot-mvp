# 1029-12 계획 — 실계좌 동기화가 모의 지갑을 덮어쓰는 문제 (배포 ②) · 2026-11-03 (3판)

- 결정 근거: 1103-01 「권고대로」(배포 ② = 1029-12, 통보는 모든 수정 뒤 한 번).
- 이력: 1판 verifier 「고친 뒤 재검증」(지적 13) → 2판 verifier 「고친 뒤 재검증」(지적 A~G) → 3판 verifier 꼭 고칠 것 2 → 고친 줄 대조 「사용자 결정 요청 가능」(verifier 4회 모두 11/03 이 세션 대화 안에서 받음, 파일 없음 — 지적은 이 판에 모두 반영) → Fable `docs/fable/2026-11-03-1029-12-plan-1.md` 「진행」(권고 4 반영) → 사용자 결정(7절) → 구현.
- 함께 하는 것: 1101-08 에서 찾은 「실시간 재판정」 문구 정리(BUY·SELL).
- **사용자 결정 (11/03): 「1029-12 권고대로」 — 7절 D1~D8 모두 권고안.**

## 1. 문제

`accounts`(원화)·`account_positions`(코인별 수량·평단)는 모드 칸이 없는 한 표이다. 두 역할을 함께 한다.
- 모의(TEST) 거래기의 지갑: `core/trader.py` `_krw_balance`(:323-330)·`_coin_balance`(:375-388)·`_simulate_buy`/`_simulate_sell`(:1622·1643).
- 실계좌 잔고 캐시: 로그인 검증(`services/auto_verify.py:93-99` — 호출처 `app.py:331-336` 자동, `pages/set_config.py:144-146`; `app.py:420-428` 검증 단추), 실계좌 엔진 1분 동기화(`engine/order_reconciler.py:802·907·910`, DB 에만 있는 코인은 0 — `services/db.py:2512`), 실주문 끝 처리(:595-596).

또 새 전략(PULLBACK) 매수 금액 기준은 매수 때마다 읽는 운용자산 `users.virtual_krw` 이다(`core/strategy_engine.py:1712-1725` `_pullback_read_sizing_base`). 로그인 검증은 새 전략 보유·예약이 없으면 이 값을 실원화로 바꾼다(D10, `auto_verify.py:84-91`).

모의 새 전략 중 덮이면 (`core/strategy_engine.py:1393` `_pullback_wallet_check`)
- 코인이 0 이면 `wallet_zero` 로 분할 상태 초기화(:1427-1431),
- 실제 수량이면 0.1% 넘게 달라 `desync=1` → 추가 분할매수 멈춤(:1440); 판정 회차 0 에 실보유면 POS_DESYNC 로 매수 신호 안 냄(`core/strategy_pullback.py:679·690`),
- 지갑 원화가 실잔고로, 또는 운용자산이 실원화로 바뀌면 첫 회차 금액(운용자산 ÷ 분할 수)이 모의 원화와 맞지 않아 잔고 부족 실패나 모의 운용자산 밖의 금액 매수.
실자산 영향은 없다(모의 주문은 실주문을 내지 않는다).

## 2. 덮어쓰는 경로

| # | 경로 | 모의 중 생기는 때 | 지금 막힘 |
|---|---|---|---|
| P1 | 로그인 검증 3곳 — 지갑 표 | 엔진 없이도, 실계좌 화면 세션이 열릴 때마다 | 안 막힘 |
| P1′ | 로그인 검증 — 운용자산(users.virtual_krw) | 같음 | D10 `keeps_capital`(보유·예약, `ui/pullback_lock.py:202-204`)만. 새 전략 켜짐·보유 없음(전환 직후~첫 매수)은 덮임 — 2차 T15 시험 t15_old_ui.py:800-804 가 고정한 동작 |
| P2 | 1분 동기화 | 정상 정지 뒤에는 안 생김 — `stop_engine` 이 실계좌 사용자를 빼고 비면 Reconciler 를 멈춤(`engine/engine_manager.py:553-561`), 모의 시작은 Reconciler 를 켜지 않음(:454-456 은 LIVE 분기). 생기는 때: ① 실계좌 엔진 예외 종료 뒤 모의 시작(R2) ② 같은 프로세스의 다른 실계좌 사용자 ③ 정지 직후 한 번(`_run` :249-267, 그때 모의 지갑은 아직 실계좌 캐시라 영향 없음) | `unregister_user`(:85) 운영 코드 호출 0 |
| P3 | 실주문 끝 처리 :595-596 | R2 + 남은 실주문 | 안 막힘(R4) |
| P4 | 실계좌 → 모의 모드 바꾸는 순간 | 모의 지갑 = 마지막 실계좌 캐시 | 절차(6절) |
| P5 | 모의 대시보드 원화 쓰기 `pages/dashboard.py:172-185` | 세션 `virtual_krw`(URL → 세션 → DB, :105-135)가 `accounts` 와 다르면 `update_account`. 같은 세션에서 실계좌 검증을 거쳤으면 세션 값이 실원화(auto_verify.py:180) | `_pb_keep_cash = _pb_locked and keeps_capital`(:158) — 새 전략 켜짐·보유 없음은 덮임 |

## 3. 바꿀 것 (권고안)

### 공용 판정 W — 「모의 지갑을 지킬 때」 한 곳 정의
- `ui/pullback_lock.py` 에 `keeps_wallet(state) = bool(state.get("pullback")) or keeps_capital(state)`.
- 읽기 실패 범위: 예약·보유 읽기 실패는 지킴(lock_state :163-174). 활성 파일 읽기 실패는 `load_active_strategy` 가 None(`engine/params.py:492-494`)이라 `pullback` 거짓 — 막지 못함(엔진도 같은 함수로 읽어 엔진·화면 판정은 어긋나지 않음). 판정 함수 자체 예외는 지킴(참).
- 실계좌 영향: 참이 되는 때(새 전략 켜짐·모의 예약·모의 보유)는 실계좌 엔진이 시작할 수 없다 — 활성 파일 PULLBACK 이면 엔진 전략이 PULLBACK(engine_manager.py:128-132) → 실계좌 시작 거부(:~650, live_loop.py:1076, 신버전 단추 control_requests.py:877 도 같은 함수). 실계좌 화면도 멈춤(dashboard.py:161-164). 예약은 모의에서만 생김. 겹침은 보유·예약 읽기 실패 때뿐(추정).

### C1. 모의 엔진 시작 때 그 사용자를 1분 동기화에서 뺀다 (P2 ①②)
- `engine/order_reconciler.py` `register_user(test_mode=True)` 분기(:78-80)에서 `self.unregister_user(user_id)` + `[OR] TEST 모드 — 잔고 동기화에서 뺌` 로그. 실계좌 분기 그대로.
- `unregister_user` 는 그 사용자의 체결·HTS 콜백을 지우고 `_pending` 은 그대로 둔다(:85-99). live_loop.py:1201 `register_user` 가 :1311 StrategyEngine 생성(콜백 등록 strategy_engine.py:379-381)보다 먼저라 새 모의 엔진 콜백은 안 지워짐 — 시험으로 묶음.

### C2. 로그인 검증 — W 가 참이면 지갑 표와 운용자산을 쓰지 않는다 (P1·P1′)
- `services/auto_verify.py`:
  - `keep_capital_on_verify` 판정을 `keeps_capital` → `keeps_wallet` 으로(D7). users 행이 없으면 지금처럼 `save_user`(새 사용자).
  - 새 함수 `keeps_wallet_on_verify(user_id) -> bool`(lock_state + keeps_wallet, 예외는 참). `run_live_auto_verify`(:93-99)는 참이면 두 동기화 함수를 부르지 않고 `[AUTO-VERIFY] 새 전략 모의 지갑 그대로 — 잔고 동기화 건너뜀` 로그, 결과 dict `wallet_kept: True`. 자동·설정 화면 두 호출처가 함께 막힘.
- `app.py:420-428` 검증 단추: `keeps_wallet_on_verify` 로 판정(세션 값 `_capital_kept_in_live` 안 씀 — 한 번 참이면 남음, app.py:412).
- 화면 문구(UI 1-A): 건너뛸 때 `app.py:349-354` 「- DB 동기화: 완료」 → 「- DB 동기화: 새 전략 모의 지갑을 지키려고 건너뜀」, 검증 단추 쪽도 같은 한 줄(st.info). 운용자산 줄은 기존 `capital_kept_text`(「새 전략 거래 중이라 그대로 둡니다」).
- 시험 변경: t15_old_ui.py:800-804 `test_auto_verify_updates_capital_when_flat` 은 「새 전략 꺼짐·보유 없음이면 갱신」으로 바꾸고 「새 전략 켜짐·보유 없음이면 그대로」 시험을 더함(2차 T15 결정 D10 의 범위를 넓힘 — D7 사용자 승인).

### C4. 모의 대시보드 원화 쓰기 — 같은 W (P5, D8)
- `pages/dashboard.py:158` `_pb_keep_cash = _pb_locked and _pb_keeps_capital(_pb_lock)` → `_pb_locked and _pb_keeps_wallet(_pb_lock)`(앞 조건 유지 — 보유 읽기 실패만 있는 EMA 사용자의 현금 동기화는 지금처럼). 계정 생성 분기 그대로. 화면 배치·문구 변경 없음.
- `pages/dashboard.py` 는 바이트 고정 목록(t15:1165-1166, t13:45-46)에 없다. EMA 화면 비교(t15:188-199·231-237)는 EMA 사용자라 같다(추정 — 게이트로 확인). **t15_old_ui.py:598-603 `test_c1a_overwrite_when_pullback_flat`(새 전략 켜짐·보유 없음 → 덮어씀)은 깨지므로 「그대로 둠」으로 바꾼다** — 2차 T15 PO 결정 C1-a 범위를 넓힘(D8).

### C3. 「실시간 재판정」 문구 (1101-08)
- `services/db.py` BUY(:1201-1207)·SELL(:1423-1428) 실시간 UPDATE 분기: `warmup_placeholder=True` 갱신이면 `[AUDIT-UPDATE] BUY 워밍업 자리표시자 갱신 | …`(SELL 같음), 아니면 지금 문구. INFO 유지(D3). SQL·반환값 무변경. 호출부 strategy_engine.py:2807·2833.

### 손대지 않는 것
- 표 나누기(모드 칸·새 캐시 표) — 읽기 호출 60줄·14파일, 기본 키 변경, T10 되돌리기 시험(D1 (나)).
- 매매 판정·주문 크기 계산식·손절·익절·트레일링·정체·데드크로스, `core/trader.py`, `engine/live_loop.py`.

## 4. 남은 위험 (기록)

- R1 모의 → 실계좌 복귀 첫 동기화 HTS 오감지(기존 동작). W 가 참이면 실계좌 엔진이 시작하지 않아 C2 로 늘지 않음. 새 전략을 끄고 복귀하면(보유 0 필요, strategy_switch.py:693-697) W 거짓 → 지금처럼 다시 채움. 보유·예약 읽기 실패로 참이 남는 경우만 조금 늘어남. 감지는 끄지 않음(Issue #17, D2).
- R2 실계좌 엔진 예외 종료 뒤 모의 시작: C1 이 막음.
- R3 W 참 동안 실계좌 화면 캐시 표시(dashboard.py:258-264)는 모의 값 — 새 전략이 켜져 있으면 실계좌 화면은 멈춤이라 예약 중일 때만(표시만).
- R4 R2 + 남은 실주문: 끝 처리가 모의 지갑을 한 번 덮음. 막지 않고 기록.
- R5 활성 파일 읽기 실패 때 W 거짓(fail open) — 엔진도 같은 값으로 새 전략이 아님으로 보므로 판정 어긋남 없음.
- R6 P4 전환 순간 초기값: 6절 운영자 절차.
- R7 (구현 검증 지적 5) 정상 정지한 사용자도 Reconciler `_live_user_ids` 에 남는다(stop_engine 은 Reconciler 를 멈출 뿐 비우지 않음). 같은 프로세스에 다른 실계좌 사용자가 있어 동기화가 돌면, 그 사용자가 모의 엔진을 켜기 전(모의 전환 뒤 저장~모의 시작 사이)에 지갑이 덮일 수 있다. 실행 중인 동기화가 목록을 먼저 복사했으면 unregister 직후 한 번 더 쓸 수 있다. 단일 사용자 운영이면 해당 없음(추정 — 서버 사용자 DB 수로 확인). 기록만.
- 문구 확인(구현 Fable 권고 4): 운용자산 줄 `capital_kept_text`(auto_verify.py) 「새 전략 거래 중이라 그대로 둡니다」는 D7 뒤 새 전략 켜짐·보유 없음에도 보인다. 입회 때 브라우저로 보고 「새 전략을 켜 둔 동안 그대로 둡니다」로 바꿀지 정한다(이번 커밋에는 넣지 않음).
- 로그 집계 주의: 옛 분석 스크립트(docs/plans/2026-10-02-wo19-warmup-audit-preserve/results/wo19_a2.py)는 「실시간 재판정」만 찾는다. 배포 뒤 집계는 「워밍업 자리표시자 갱신」도 함께 찾는다.

## 5. 시험·고정 파일·버전

- 새 회귀 `tests/regressions/test_r_2026_11_03_mock_wallet.py`:
  - W: 켜짐·보유 없음 / 보유 / 예약 / 보유·예약 읽기 실패 → 참; 꺼짐·없음 → 거짓; 판정 예외 → 참.
  - C1: 실계좌 등록 → 모의 등록 뒤 `_live_user_ids` 없음·콜백 정리·`_pending` 유지·1분 동기화가 그 사용자 표를 안 씀. R2 재현(stop 없이 모의 등록 → 동기화 0). register → StrategyEngine 순서(live_loop 소스 순서). 정상 정지 뒤 Reconciler 멈춤 고정.
  - C2: W 참 → 동기화 두 함수·save_user 안 부름, `wallet_kept`·`capital_kept`; 거짓 → 부름. users 행 없음 → save_user. app.py 검증 단추가 `keeps_wallet_on_verify` 를 부르고 세션 값을 조건으로 안 씀(소스). 화면 문구 둘.
  - C4: 새 전략 켜짐·보유 없음 + 세션 값 ≠ DB → `update_account` 안 부름; 꺼짐 → 부름.
  - C3: 자리표시자 갱신 문구(BUY·SELL), 실판정 재판정 문구 그대로, 반환값 그대로.
- 고칠 시험(1101-05·1102-01 선례 방식):
  - `engine/order_reconciler.py`: t11_control.py:1266-1269 EMA 비교 목록에서 빼고 FIXED_FILES_COMMIT 비교로.
  - `services/db.py`: t15_old_ui.py:1164-1177 `FIXED` → `TO_FIXED_COMMIT`. t13_apply.py:45-46·654-660, t14_ops.py:297 은 FIXED_FILES_COMMIT 비교 그대로.
  - 코드 커밋 A 뒤 커밋 B 에서 `FIXED_FILES_COMMIT` 만 A 로(EMA_BASELINE 그대로) — D4.
  - t15_old_ui.py:800-804 (C2·D7), t15_old_ui.py:598-603 (C4·D8), t15 소스 순서 시험(:826-839·:1062-1077 — 깨지지 않게 넣음, 실행으로 확인).
  - 안 깨질 것으로 보는 시험(게이트로 확인): T8 `test_live_fill_ema_call_same_as_base`(t8_pullback_audit.py:307-317, EMA_BASELINE 원본의 `_finalize` 호출만 비교 — C1 은 `register_user`), wo11 용어 시험(wo11_terminology.py:37-46, `logger.*` 인자 제외 — C1 로그는 `logger.info`). T10 은 REVERT_OLD_CODE_COMMIT 옛 db.py 를 쓰므로 무관.
- 게이트 `scripts/regression_gate.sh` 전체 + NETGUARD 0. 백테스팅 해당 없음.
- `pages/dashboard.py` 버전 v1.2026.11.03.1532 → 커밋 A 시각. 보고에 「버전: 구 → 신」.
- 배포 뒤 브라우저 확인(UI 1-A): 실계좌 검증 화면 문구 2개 — 마지막 입회 확인 때.

## 6. 첫 모의 전환 운영자 절차 (D6, 코드 변경 없음 · 통보에 넣지 않음)

**새 전략으로 바꾸기 전에만 할 수 있다**(새 전략이 켜지거나 예약되면 설정 저장이 잠김 — set_config.py:245-246·305-308, sidebar.py:388-391).
1. 실계좌 엔진 정지 → **로그인 화면(app.py)의 「로그아웃하기」 단추 또는 브라우저 새로고침으로 새 세션**(app.py:610-615) → 모의 모드로 로그인. 대시보드의 로그아웃(dashboard.py:779-782 `st.switch_page`)은 세션을 남겨 주문총액이 실계좌 값으로 남으므로 쓰지 않는다(set_config.py:209-210). 새 세션이 됐는지는 대시보드 주문총액 표시로 확인(추정 — 입회 때 확인).
2. 설정 화면에서 **값을 바꾸지 않고** 모의 저장 1회. 저장이 하는 일: 원화 = 세션 주문총액(`params.cash`, :347), 코인 표 전부 비움(:352). 부수로 EMA 설정 파일(`{user}_latest_params_EMA.json`, 실계좌와 같은 파일, save_params :320)·base order_ratio(:324)·설정 이력 1행(record_snapshot :330)·활성 파일(save_active_strategy :365)을 씀 — 값을 안 바꾸면 같은 내용.
3. 대시보드에서 모의 원화·운용자산 두 값과 코인 0 을 확인. 다르면 전환하지 않고 멈춘 뒤 서버 읽기 전용으로 두 표를 본다.
4. 설정 이력 새 행이 이전 행과 같은 값인지 확인.
5. 모의 EMA 시작 → 새 전략 전환.

## 7. 정해 주실 것 (권고안)

| # | 결정 | 권고 | 다른 안 |
|---|---|---|---|
| D1 | 범위 | (가) W + C1~C4 — 덮어쓰는 길만 막음 | (나) 실계좌 캐시를 새 표로 나눔(큰 변경) |
| D2 | R1 복귀 첫 동기화 | 그대로(감지 유지) | 복귀 때 감지 없이 캐시만 맞춤(앱 매수 놓칠 위험) |
| D3 | C3 로그 수준 | INFO·문구만 | DEBUG |
| D4 | C1 을 하고 고정 파일 비교를 옮김 | 예 — order_reconciler.py·db.py 를 FIXED_FILES 비교로 옮기고 FIXED_FILES_COMMIT 만 올림 | C1 을 빼고 R2 는 기록만 — 그때 order_reconciler.py 는 옮기지 않음. db.py 는 C3 때문에 어느 안에서도 옮김 |
| D5 | 지갑 표 지키는 조건 | W(새 전략 켜짐 또는 보유·예약) | 보유·예약만 / 모의 엔진 도는 동안 늘 |
| D7 | 운용자산(매수 금액 기준)도 W 로 지킴 | 예 — 2차 T15 D10 범위 넓힘(새 전략 켜짐·보유 없음에도 그대로) | 아니오 — 그대로, 문서에 밝힘 |
| D8 | 모의 대시보드 원화 쓰기(P5)도 W | 예 — 2차 T15 PO 결정 C1-a 범위 넓힘(새 전략 켜짐·보유 없음에도 모의 현금 그대로) | 기록만 |
| D6 | 전환 순간 초기화 | 6절 운영자 절차(통보 안 함) | 초기화 단추 신설(범위 확대) |

배포는 구현·verifier·Fable 뒤 배포 ① 과 같은 서버 대기 스크립트로 따로 승인.

통보 문구(1101-04 에 넣음, D1·D5·D7·D8 권고대로일 때만): 「새 전략을 켜 두신 동안에는 실계좌 화면을 열거나 계좌를 다시 확인해도 모의 현금·코인과 새 전략 운용자산이 실계좌 값으로 바뀌지 않습니다.」
