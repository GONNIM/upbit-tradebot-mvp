# 앱 추가매수 직후 정체 매도 고치기 — 계획 (1102-01)

- 작성: 2026-11-02 0시대 · 상태: **계획 승인됨 (11/02 · 사용자 「1102-01 1~3 권고대로」)** — 방향 (나) · 구현은 1101-13 배포 뒤 · 저장 위치 이 파일. 구현 전.
- 검증: verifier 3회(1·2회 「고친 뒤 재검증」 → 3회 「승인 요청 가능」), Fable `docs/fable/2026-11-02-1102-01-plan-1.md` 「진행」(권고 4건 반영).
- 근거 조사: 1101-14 (HANDOFF 0-1 표 1101-14 행), 서버 읽기 스크립트 `r1101_14.sh`·`r1102_01.sh` 출력(11/02 세션, 사용자 `!` 실행)

## 1. 확인한 사실

| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| F1 | 11/01 00:51 봇 매수(EMA_GC 509) 뒤 정체 판정 111회는 max_gain 0.39%(최고 511) ≥ 0.30% 라 매도 없음 | 확인 | journal 00:50~12:50 `STALE_POSITION_CHECK` |
| F2 | 13:11:39 앱 추가매수 감지(`HTS_BUY_ADD`, 508.10→968.59개) 때 `_on_hts_detect` 가 highest_since_entry 511 을 None 으로 지우고 entry_ts(00:51:12)는 그대로 둠 | 확인 | journal 13:11:39 `[HTS-DETECT-CALLBACK]`, `core/strategy_engine.py:441-451` |
| F3 | 다음 봉 13:12:05 정체 판정: elapsed 12.30h, highest_since_entry=506(그 봉 종가), 새 평단 507.57 → max_gain −0.31% < 0.30% → 전량 968.587 시장가 매도 @505 | 확인 | journal 13:12:05, audit_trades 1470 |
| F4 | 지우는 코드는 e182230(07/27) P2-3. 계획서 4.3 은 지우는 필드에 highest_since_entry 를 적었지만 이유는 트레일링(새 평단 기준 재추적)뿐이고 정체 판정 영향은 언급 없음 | 확인(문서), 의도 밖이라는 판단은 추정 | `docs/plans/2026-07-27-phase1-defense-hardening/plan.md:57·113` |
| F5 | 앱 매수 표시(`hts_buy`)는 매도 판정에 쓰지 않고 진단 로그에만 쓴다(Policy P-3). Issue #17 의 손절 건너뛰기도 P-3 으로 없어져 지금 앱 매수분 보호 장치는 없다 | 확인 | `core/filters/sell_filters.py:42-43·96-108` |
| F6 | 새 진입(`apply_entry`)은 highest_since_entry 를 평단으로 초기화한다. 지운 뒤(None)에는 다음 봉 종가가 최고가가 된다. 목표가 0보다 크면 None·평단 어느 쪽이든 결과는 같고, 이번 원인은 「511 을 잃음」+「시계를 그대로 둠」이다 | 확인 | `core/position_state.py:263-265·551-552·561-564` |
| F7 | 재시작 때 entry_ts: boot_seed 는 마지막 **봇** 매수 주문 체결 시각(orders `entry_ts_iso`), 그것을 못 구하면 wallet_sync 의 기동 시각. 앱 추가매수 시각은 보지 않는다. highest_since_entry 는 어느 경우든 평단으로 초기화(정체용 최고가는 재시작 때 되살리지 않음 — 트레일링만 WO-21 로 되살림) | 확인 | `engine/live_loop.py:700-744`·`749-752`, `core/strategy_engine.py:792-803`, `core/position_state.py:263-265`, `core/trailing_restore.py:7-11` |
| F13 | 그래서 정체 시간이 지난 보유 중에 재시작하면 정체용 최고가가 평단으로 돌아가, 첫 봉 종가가 평단+목표 미만이면 바로 정체 매도될 수 있다(이번 사고와 같은 모양, 앱 매수와 무관한 기존 틈 — HANDOFF 1102-02) | 추정(코드 읽기 — 실제 사례는 찾지 않음. journal 에서 기동 직후 첫 판정 STALE_POSITION 을 찾으면 확인됨) | 위 F7 근거 |
| F8 | 사용자가 11/01 19:55 설정 화면에서 정체 매도를 껐다(settings_history 229, 조건 파일 mtime 19:55:07). 지금 서버 조건 파일 stale_position_check=False | 확인 | `r1102_01.sh` 1·2절 |
| F9 | 엔진은 그 조건 파일을 1분마다 다시 읽는다(`[COND] loaded` 매분). 핫 리로드가 stale_position_check 를 전략에 반영하고 필터를 다시 만드는 코드 경로가 있다 | 확인(로그·코드). 꺼짐 반영도 확인 — journal 11/01 19:55:08 `[HOT-RELOAD] strategy 갱신 완료 | enable_stale_position: True→False`(11/02 15:40 서버 읽기). 14:21 이후 `STALE_POSITION_CHECK` 0줄은 꺼짐의 증거가 아님(그 뒤 보유 24분뿐) | journal, `core/strategy_incremental.py:861-868` |
| F10 | 11/02 0시 기준 JTO 보유 0 (22:57 EMA_GC 매수 → 23:21 TRAILING_STOP_FIXED 매도 @506) | 확인 | audit_trades 1471·1472 |
| F11 | `core/strategy_engine.py` 는 실계좌 EMA 경로 바이트 고정 8개 파일에 들어 있다 — 고치면 고정 기준을 다뤄야 한다 — 바이트 비교 외에 AST·git diff 비교까지 세 기준(3절 3) | 확인 | `tests/regressions/baseline_commits.py:40-49`, `test_r_2026_10_29_p4_t13_apply.py:45` |
| F12 | 1101-13 배포 정지선은 로컬 HEAD = ee874a2 = origin/main, 추적 변경 0 을 기대한다 — 그 전에 코드를 고치거나 커밋하면 정지선이 어긋난다. (지금 HANDOFF.md 수정 1건이 이미 「추적 변경 0」과 글자로 다르다 — 1101-13 정지선에서 따로 다룸) | 확인 | `deploy-request-20261101-overlap-guard.md:52`, `git status` |

지금 실매매 위험: 정체 매도가 꺼져 있어(F8) 같은 일이 다시 일어날 경로는 지금 없다(F9 반영 미확인 부분은 다음 서버 읽기로 확인). **고치기 전까지 조심할 점:** 정체 매도를 다시 켠 상태에서 정체 시간을 넘긴 봇 보유에 앱 추가매수를 하면 다음 봉에 전량 매도될 수 있고, 같은 상태에서 재시작해도 첫 봉에 매도될 수 있다(F13).

## 2. 고칠 방향 (비교)

| | (가) 최고가를 지우지 않음 | (나) 추가매수 때 정체 시계를 다시 시작 (**승인**) | (다) 그대로 둠 |
|---|---|---|---|
| 바꾸는 것 | HTS_BUY_ADD 때 트레일링 필드만 지우고 highest_since_entry 는 둠 | HTS_BUY_ADD 때 entry_ts = 감지 시각, highest_since_entry = 새 평단 (apply_entry·재시작과 같은 초기화). 트레일링 리셋은 그대로 | 없음 |
| 이번 사고에서 | max_gain (511−507.57)/507.57 = 0.68% ≥ 0.30% → 안 팖 | 감지 뒤 3시간 동안 정체 매도 없음 → 안 팖 | 같은 일 반복 |
| 남는 틈 | ① 평단을 **올리는** 추가매수(예: 최고 511 에서 530 에 더 사 평단 520)는 옛 최고가 < 새 평단이라 max_gain 음수 → 3시간 지났으면 바로 정체 매도. 평단을 낮춘 경우만 막음 ② 봇 매수 뒤 3시간 직전 앱 추가매수 → 원래 시계로 몇 분 뒤 앱분까지 정체 매도 가능 | ① 앱 추가매수를 할 때마다 정체 매도가 3시간 미뤄짐 ② 콜백이 불리지 않는 경우(avg_buy_price 0, 봇 매수 뒤 30초 안 앱 매수는 봇 매수로 봄)는 시계가 안 바뀌어 지금과 같음 ③ HTS_BUY_ADD 오감지(WO-9·10 으로 줄였지만 남음) 때는 정체 매도가 3시간 미뤄짐. 손절·트레일링·데드크로스·익절은 그대로 | — |
| 화면·감사 | 변화 없음 | 감지 직후 1~2봉은 감사 칸 stale_elapsed_hours 가 음수(봉 시작 시각 < 감지 시각, 표시 전용·매도 무관). system_health 의 진입 시각은 앱 매수 시각, bars_held 는 봇 매수 기준이라 어긋나 보임 | — |
| 일관성 | 새 진입(F6)과 다름 | 새 진입(F6)과 같음. 재시작(F7)은 봇 매수 시각으로 되돌아가므로 boot_seed 도 맞춰야 함(3절 2) | — |
| entry_bar·bars_held | 그대로 | 그대로(최소 보유 봉·화면 표시 무관) | — |

권고 (나): 정체 매도의 뜻(「들어간 뒤 N시간 안에 목표 수익을 못 보면 정리」)을 「사용자가 마지막으로 더 산 때부터」로 맞춘다. Policy P-3(앱 매수 표시를 매도 판정에 안 씀)은 그대로다 — 표시를 보는 것이 아니라 감지 순간 상태를 새 진입처럼 맞추는 것이다.

## 3. 구현 범위 ((나) 기준)

1. `core/strategy_engine.py` `_on_hts_detect` 의 `HTS_BUY_ADD` 갈래: `highest_since_entry = None` 대신 `= float(avg_price)`, `entry_ts = 감지 시각(Asia/Seoul)`. WARNING 줄의 「→ 모두 None」 문구를 실제 값으로 고치고 `stale_restart=entry_ts→…` 를 더한다. HTS_BUY(신규) 갈래·트레일링 리셋·weak entry 해제는 그대로.
2. 재시작 일관성: `engine/live_loop.py` `_apply_boot_seed` 의 entry_ts 를 「마지막 봇 매수 체결 시각과, 청산 없이 남은 마지막 BUY 가 HTS_BUY_ADD 일 때 그 시각 중 늦은 쪽」으로 (`services/db.get_last_open_buy_trade` 재사용 — 트레일링 복원이 이미 쓰는 함수, 단일 출처. 그 뒤 SELL·HTS_SELL 이 있으면 None → 지금 그대로). 두 시각은 문자열이 아니라 tz 있는 datetime 으로 바꿔 비교한다(audit 는 KST ISO, orders entry_ts_iso 는 COALESCE(executed_at, updated_at) 형식이 다를 수 있음). 조회 실패·파싱 실패면 지금 그대로(봇 매수 시각).
   - 제약: ① `_apply_boot_seed(position, db_result, actual_qty)` 호출 인자는 바꾸지 않는다(호출부 run_live_loop 가 T11 `_run_live_loop_norm` 비교 대상). ② user_id·ticker 는 `position.trader.user_id`·`position.ticker` 로 얻고, 둘 중 str 이 아니거나 None 이면 조회를 건너뛴다(기존 시험의 trader=None·MagicMock). ③ `get_last_open_buy_trade` 는 함수 안에서 import. ④ 새 로그 태그는 `[BOOT-SEED]` 가 아닌 `[STALE-CLOCK]` (wo20 test_6 은 `[BOOT-SEED]` 부재를 단언). ⑤ wo20·wo26 boot_seed 시험 그대로 통과.
   - F13(재시작 때 정체용 최고가 초기화)은 이번 범위에 넣지 않고 새 행 1102-02 로 따로 둔다(앱 매수와 무관한 기존 틈, 고치려면 정체용 최고가 재생 설계가 필요).
3. 고정 기준 처리 — 두 파일은 세 기준으로 비교된다(verifier 지적 1). 방식: 바뀐 두 함수만 비교에서 빼고, 그 두 함수는 새 커밋 A 와 따로 비교한다(1101-05 의 engine_manager 처리와 같은 방식, 비교 대상을 줄이지 않음).
   - ① 바이트 비교 `FIXED_FILES_COMMIT`(T13 `test_fixed_files_unchanged_since_t12`, T14 같은 이름): 코드 커밋 A 뒤 기준 커밋 B 에서 `bc694a4 → A` 로 올린다. 이력 주석 추가(`baseline_commits.py:40-44`).
   - ② AST 비교 `EMA_BASELINE_COMMIT`(T9 `test_ema_ignores_trading_hours` 의 strategy_engine, T11 `TestEmaBaseline` 의 strategy_engine·live_loop): T9 의 지역 함수 `funcs()`(`test_r_2026_10_28_p3_t9_trading_hours.py:222-228`)에는 제외 인자가 없으므로 skip 인자를 더한다(T11 `_funcs(src, skip=())` 는 이미 있음). 함수 비교에서 `_on_hts_detect`(strategy_engine)·`_apply_boot_seed`(live_loop)를 빼고, 그 두 함수 AST 가 `FIXED_FILES_COMMIT`(B 에서 A 로 올린 값, 새 상수 없음)과 같은지 따로 검사. T11 `new_funcs == {_control_attach,_control_ready,_control_drain}` 단언은 그대로 둔다 — 새 함수는 중첩 def·lambda 대입 포함 만들지 않고 두 함수 몸통의 문장으로만 쓴다(두 시험이 `ast.walk` 로 중첩 함수까지 이름으로 모음).
   - ③ `git diff --quiet OLD_UI_BASE_COMMIT`(T15 `TestFixedFiles` 7파일): strategy_engine·live_loop 를 7파일 목록에서 빼고 engine_manager 처럼 `FIXED_FILES_COMMIT` 과 비교하는 시험으로 옮긴다.
   - 커밋 메시지·보고에 「EMA 경로 변경: _on_hts_detect·_apply_boot_seed 두 함수(정체 시계), 매매 판정·주문 무변경」을 적는다(`baseline_commits.py:13-19` 규칙).
4. 회귀 시험 1파일 (`tests/regressions/test_r_2026_11_02_hts_add_stale.py`, 바깥 연결 0):
   - R1 이번 사고 재현: 00:51 진입 509·최고 511·3h/0.30% → 13:11:39 HTS_BUY_ADD(507.57, 968.587) → 봉 시작 13:09 종가 506 판정 = 매도 아님(경과 시간 음수, 감사 칸 음수 허용). 고치기 전 코드에서는 STALE_POSITION 이 나는지 함께 확인(재현 확인).
   - R1b 평단을 올리는 추가매수(511 최고 뒤 530 매수)도 감지 직후 매도 아님.
   - R2 정체 기능 유지: R1 뒤 감지+3h 지난 봉에서 최고 수익 < 0.30% 이면 STALE_POSITION.
   - R3 감지 뒤 3h 안에 수익이 0.30% 넘으면 그 뒤로 정체 매도 없음(기존 뜻).
   - R4 트레일링 리셋·weak entry 해제 그대로(wo9·wo10 기존 시험 통과 유지).
   - R5 HTS_BUY(신규 매수) 갈래 무변경.
   - R6 PULLBACK 분할 대기 중 무시 갈래 무변경.
   - R7 boot_seed: 봇 매수 뒤 HTS_BUY_ADD 가 있으면 entry_ts = HTS_BUY_ADD 시각, 없거나 그 뒤 SELL·HTS_SELL 이 있으면 봇 매수 시각(지금과 같음). 시각 형식이 다른 두 값(KST ISO 마이크로초 / 공백 구분·tz 없음)을 섞은 경우, 조회 실패 경우 포함.
   - 백테스팅: 해당 없음 — 매매 판정 규칙은 그대로이고 앱 추가매수 감지 때 정체 시계만 바뀌어 과거 봉 재생에 앱 매수 사건이 없다. R1~R7 로 갈음(project-rules 워크플로우 2단계 사유 기재).
5. 문서: 이 계획서 끝 「구현 기록」, HANDOFF 행.

## 4. 순서와 멈춤 조건

1. 계획 승인 · 저장 위치 승인 — **끝남 (11/02)**.
2. **구현·커밋은 1101-13 배포 뒤** (F12 — 배포 전 push 금지·정지선 HEAD 보존). 지금 정체 매도가 꺼져 있어(F8) 급하지 않다. 이 계획서 파일도 배포 뒤 문서 커밋에 묶는다(지금은 미추적).
3. 구현 → 고정 기준 시험 밖 게이트 → verifier → Fable → 커밋 승인(버전 갱신, `pages/dashboard.py`) → 커밋 A(코드·시험) → `baseline_commits.FIXED_FILES_COMMIT` 을 A 로 올림 → 전체 게이트(`scripts/regression_gate.sh`) → 커밋 B → A·B 함께 push(pre-push 게이트, 기준 커밋은 origin 에 있어야 함 `baseline_commits.py:20`). 1101-05 와 같은 순서(`deploy-request-20261101-overlap-guard.md:136`).
4. 배포는 따로 배포 요청서로 승인(tradebot 재시작 1회, 보유 0일 때).
- 멈춤: 고정 기준 시험(①②③)이 두 함수 밖 변경을 잡으면 / 기존 HTS 시험(`test_r_2026_09_30_wo9_hts_detect_locked_total`·`test_r_2026_09_30_wo10_hts_residuals`)이나 Policy P-3 시험이 하나라도 깨지면.

## 5. 투자자 통보

체감 변경(앱 추가매수 뒤 정체 매도가 3시간 미뤄짐)이므로 배포 때 1줄 통보 대상. 지금 정체 매도가 꺼져 있으면 통보 문안에 「정체 매도를 켜실 때 적용」으로 적는다. 클레임은 아직 없음 — 11/01 13:12 건은 클레임이 오면 답한다(투자자 연락 원칙).

## 6. 결정 (11/02 · 사용자 「1102-01 1~3 권고대로」)

1. 고칠 방향: (나) 추가매수 때 정체 시계 재시작
2. 구현 시점: 1101-13 배포 뒤
3. 저장 위치: `docs/plans/2026-11-02-hts-add-stale/plan.md` (이 파일)

## 구현 기록

(구현 전)
