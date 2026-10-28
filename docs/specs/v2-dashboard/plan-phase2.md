# 신버전 2차 공개(P3 새 전략 + P4 전환·운용) 구현 계획 — 4판 (2026-10-27, 사용자 승인)

**사용자 결정 1027-17 (2026-10-27 21시대): 「1027-17 권고대로 승인 (13-4 가, 13-5b 넣음)」 — 이 계획과 13절 결정 13-1~13-8 모두 권고안, 13-4 는 (가) 원본 백테스터와 같게, 13-5 의 손절 지연은 통보 문안 B 에 넣음.** 본문의 「결정 13-n 에 따름」은 모두 권고안으로 확정. 검증: verifier 4회(4회째 「사용자 승인 요청 가능」), Fable `docs/fable/2026-10-27-phase2-plan-1.md` 다시 묻기 「진행」. 목차: `docs/specs/v2-dashboard/plan-outline-phase2.md`(결정 1027-16). 구현은 저장소 폴더 새 세션에서 subagent-driven 으로 T1 부터(Task 마다 커밋 승인).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **실행 에이전트 금지 행위:** 서버 SSH, `pip install`, 외부 내려받기(업비트 fixture·문서 조회 포함), `git commit`·`push`, 서버 설정 변경, 서버 DB 열기는 직접 하지 않는다. 「사용자 확인 후」가 붙은 Step 과 모든 커밋은 PO 에게 돌려보내고, PO 가 사용자 승인을 받아 실행한다.

**Goal:** 엔진에 세 번째 전략 `PULLBACK`(눌림목 분할매수)을 넣고(P3), 신버전에서 전환·예약·복귀·「이 설정으로 동작」·운용 단추를 연다(P4). 둘을 한 번에 배포한다. 배포 직후 매매는 바뀌지 않는다(활성 전략 EMA 그대로). 투자자가 전환을 확인할 때만 바뀐다.

**Architecture:**
- 새 전략은 엔진 프로세스 안의 새 모듈 `core/strategy_pullback.py` 에 둔다. 공개 함수는 기존 전략과 같은 `on_bar`·`reload_conditions`·`set_interval_min` 이다.
- 엔진은 PULLBACK 설정을 **적용본**(`{user}_applied_params_PULLBACK.json`, 저장소 루트, 엔진만 씀)에서 읽는다. 신버전은 **저장본**(`{user}_latest_params_PULLBACK.json`, 지금 파일)에만 쓴다(결정 D9).
- 신버전 → 엔진 요청은 파일로 한다. 신버전이 `services/data/v2_control/<user>/` 에 요청 파일(600)을 쓰고, 엔진 프로세스의 감시 스레드(`scripts/tradebot_boot.py` 가 띄움, 엔진 스레드 밖)가 2초마다 읽어 실행하고 결과 파일(600)을 쓴다(결정 D3).
- 분할 상태·전환 기록은 실매매 DB 의 새 테이블에 둔다. 거래 행에는 전략 칸을 더한다(결정 D2). 모두 `services/init_db.py` 마이그레이션 함수로만 바꾼다.

**Tech Stack:** Python 3.12.8(서버)·3.11.9(로컬), unittest, Streamlit 1.46.0(구버전), tornado 6.5.1(신버전), Alpine 3.14.1, node 22 `node:test`(원본 `simulate()` 기준값).

**기준과 근거:**
- 기준(구현해야 하는 것): 투자자 승인 요청서 `docs/specs/v2-dashboard/investor-approval-20261021-v2.html` 2~9절. 사용자 지시 「승인 요청서 내용은 구현이 되어야 한다」(10/26).
- 목차: `docs/specs/v2-dashboard/plan-outline-phase2.md` 3판. 사용자 결정 1027-16(2026-10-27 19시대) 「1027-16 권고대로 승인」 — D1~D12 모두 권고안.
- 설계: `docs/specs/pullback-strategy/spec.md`(P3), `docs/specs/v2-dashboard/spec.md` 4.5·4.6·4.7·5·7절(P4).
- 규칙: `CLAUDE.md`, `.claude/context/project-rules.md`.

---

## 0. 목차와 다른 점 (계획 본문은 목차를 따른다 — 아래는 승인 때 함께 보아야 할 사실)

### 0-1. 1회째 검증 반영표 (verifier 1회째 「수정 필요」, 10/27 — `docs/specs/v2-dashboard/review-20261027-phase2-plan-verify1.md`)

| 지적 | 요지 | 고친 곳 |
|---|---|---|
| 반박 13 | `load_applied`/`load_for_boot` 이름 불일치 | T1 표 「엔진 관리자」 줄을 `load_for_boot` 로 통일 |
| 반박 18·F5 | 워밍업 2회째부터 `min_hist+1` 만 요청(`engine/live_loop.py:1140`) | T3 Interfaces 「워밍업」, 시험 `test_warmup_retry_uses_required_bars`·`test_warmup_short_refuses_start` |
| 반박 21·F3 | 원본은 감시 구간에서 골든크로스 없이도 눌림목 1회차를 삼(원본 HTML 343-357) | X11, 결정 13-4, T4 순서 5·시험 교체(`test_pullback_first_buy_without_golden`), 대응표 3절, 문안 B |
| 반박 22·F4 | 잠정 봉은 `on_new_bar_confirmed` 로 `is_confirmed=False`, O=H=L=C(`engine/live_loop.py:1787-1800`) | X12, 결정 13-5, T4 「잠정 봉」, 시험 `test_tentative_bar_not_in_indicators`·`test_confirmed_after_tentative_replays` |
| 반박 25·F1 | `register_pending_buy_uuid` 를 쓰면 `_on_limit_fill` 이 `apply_entry` 로 누적을 덮어씀. HTS 판정은 `has_recent_bot_buy_for_ticker`(30초) | T6 「봇 추가매수 오인 방지」 재작성, 시험 `test_bot_split_buy_not_hts_30s`·`test_limit_fill_callback_unchanged_for_ema` |
| 반박 32·F14 | LIVE 체결 행은 `engine/order_reconciler.py:506-529` 가 쓰고 meta 를 넣지 않음 | T8 Files·체결 행 칸 경로 |
| 반박 39·R5 | 1-2 날짜(실제 기동 2026-10-26 00:25:30, count=801 1회 성공) | 1-2 명령 시각 |
| 반박 40·R6 | 수동 검증(`app.py:394`)도 `save_user(krw_balance)` | T15 D10 범위에 수동 검증 포함(결정 D10 「로그인」의 해석 — 문안 B 문구와 맞춤), 시험 추가 |
| 반박 42·F13 | PULLBACK 조건 파일이 없으면 `{user}_buy_sell_conditions.json` 로 폴백(`engine/live_loop.py:616-646`) | T5 Interfaces 「조건 파일 안 읽음」, 시험 `test_pullback_does_not_load_conditions` |
| 반박 49·D2 | 되돌린 동안 쓴 행이 재배포 뒤 분류 불명 | T7 「재배포 규칙」, 시험 `test_redeploy_after_revert_marks_gap` |
| 반박 52·R7 | 없는 시험 이름 | 대응표·수용 기준의 이름을 기존 이름(`test_button_in_header_column_context`) 또는 정의한 이름으로 맞춤, `test_old_ui_locks_*` 9개 명시 |
| 오차 | computeSlope 216→218-227, 원본 루프 296, `main` 120, 요청 2,012 | 해당 줄 고침 |
| F2 | LIVE 분할 체결 실수량·평단 반영 경로 없음(`core/trader.py:594-595,819-833` 은 추정 수량) | T6 「체결 반영」, 시험 `test_split_fill_uses_executed_qty_avg`·`test_desync_ignores_pending_fill` |
| F6 | 운용 설정 저장이 `apply_params` 로 저장본 전체를 적용함 | 결정 13-6, T14 표 「운용 설정」·T11 kind `ops_settings`, 시험 `test_ops_settings_applies_only_4_keys` |
| F7 | `stop_engine` 은 10초 join 뒤 상태를 지움(`engine/engine_manager.py:255-268`) | T11 「재시작 절차」, 시험 `test_restart_waits_old_thread_exit` |
| F8 | 전환 때 미체결 매수 주문 확인 없음 | T12 흐름 2, 시험 `test_switch_with_open_buy_order` |
| F9 | 즉시 전환 기동 실패 처리 없음 | T12 흐름 3, 시험 `test_switch_start_failure_rolls_back` |
| F10 | 신버전 강제 매매가 엔진 `_execution_lock` 밖 | T11 「강제 매매」 — **2회째 1 로 재설계(엔진 제어 큐)**, 시험 `test_force_sell_during_bar_processing_serialized` |
| F11 | 프로세스 안 재시작은 pid 같고 세대 값은 5초 늦음 | T11 「쉼 표식」, 시험 `test_rest_mark_written_before_restart` |
| F12 | 회차 건너뜀 뒤 armed·알림 반복 | T5 「건너뜀 뒤」, T8 알림 dedupe, 시험 `test_skip_clears_armed_like_buy`·`test_skip_notify_dedupe` |
| F15 | BACKFILL 과 링 버퍼 연결 위치 | T3 「BACKFILL 연결」(`engine/live_loop.py:1427-1523`, `core/strategy_engine.py:894-1046`) |
| F16 | 재시작 시험 조건·실서버 차이 | T10 재시작 시험 조건, 12절·영향표 |
| S1 | 신버전 침해 시 요청 파일로 주문 유발 | 영향표 「자격증명·권한」 줄, T11 요청 종류별 알림 |
| D1 | 마이그레이션이 매 실행 BEGIN IMMEDIATE | T7 마이그레이션 「먼저 읽기」, 시험 `test_migration_no_write_when_done` |
| D3 | 「칸 있음·표식 없음」 보정 모호 | T7 에서 정의(표식 없으면 `strategy_type IS NOT NULL` 인 가장 작은 id − 1) |
| R1 | spec 4.6 「변경 사실과 적용 시점을 audit_settings 에」 | T13 규칙 — **2회째 6 으로 `strategy_switch` kind `PARAMS` 로 옮김(결정 13-8)**, 시험 `test_apply_writes_params_record` |
| R2 | Issue #17 `hts_buy` 처리 | T6 「hts_buy」, 시험 `test_pullback_hts_buy_stop_loss_applies` |
| R3 | 금지 행위 문구와 분기 밖 변경 | 금지 행위 고침 + 「분기 밖 변경 목록」 표, 예약 조회 실패 때 동작 |
| R4 | 결정 요청 절 없음 | 13절 신설 |
| R8 | 배포 전 로그 레벨·systemd 자동 재시작·비밀 파일 권한 | 배포 절 2 |
| R9 | 문안 B 누락 | 문안 B 에 구버전 잠금 범위·구버전 강제 매수 회차 밖·F3 결과(결정 13-4) |
| R10 | 대응표 누락 | 2-마 「(지금은 해당 없음)」, 8절 「익절 판정인데 손해」 줄 |
| R11 | PULLBACK trader 에 `params_file` 을 넘기면 order_ratio 자동 재읽기가 PULLBACK 파일을 읽음 | T5 Interfaces, 시험 `test_pullback_trader_no_params_file` |
| R12 | 이름·줄 오차 | 반영(위 「오차」 줄과 같음) |

### 0-1b. 2회째 검증 반영표 (verifier 2회째 「수정 필요」, 10/27 — `docs/specs/v2-dashboard/review-20261027-phase2-plan-verify2.md`, 이 판 = 3판)

| 지적 | 요지 | 고친 곳 |
|---|---|---|
| 1 (최상) | 강제 매수를 `_execution_lock`(재진입 불가 `threading.Lock`, `core/strategy_engine.py:305`) 안에서 `force_buy_in` 으로 부르면 지정가 경로 `execute_force_buy_limit_atomic`(`:125`)이 같은 잠금을 다시 잡아 교착 → 봉 처리·손절 정지(`services/trading_control.py:309-313`) | T11 「강제 매매」 전면 재설계: 감시 스레드는 잠금을 잡지 않고 **엔진 스레드의 제어 큐**에 넣는다. 엔진 스레드가 봉 사이에 꺼내 실행(봉 처리와 자연히 순서가 정해짐). (3회째 정정) `_execution_lock` 은 봉 처리에서도 잡힌다(`core/strategy_engine.py:790,808` `on_new_bar`, `:914,962` `on_new_bar_confirmed` 평가·실행, `:432` `_on_limit_fill`, 그 밖 `:59,102,125,201,382`). 그래서 감시 스레드가 잠금을 쥔 채 부르면 교착이고, 큐에서 엔진 스레드가 실행할 때도 지정가 경로(EMA `force_buy_in`)는 잠금 밖에서 부른다. 교착 없음 증명 시험 4개(`test_force_buy_fixed_price_no_deadlock` 외), lint `test_control_never_holds_execution_lock`. 분기 밖 변경 표에 위험 줄 |
| 2 (높음) | BACKFILL 루프는 `changed_ts` 봉만 넣음(`engine/live_loop.py:1427-1523`) | T3 「BACKFILL 연결」: 바뀐 첫 봉부터 직전 확정 봉까지 `local_series` 로 전부 재생. 시험 `test_backfill_replays_unchanged_tail`(바뀐 봉 1 + 뒤 봉 5) |
| 3 (높음) | `start_engine` 은 스레드만 띄우고 True — 전환 성공 판정 불가, 실패 때 복구 래퍼가 다시 띄움, 처리 중 죽은 행 | T11 `restart_engine` 에 워밍업 완료 Event·대기 상한·복구 금지 표시, T12 「기동 때 처리 중 행 복구」. 시험 3개 |
| 4 (중) | 마이그레이션 실패(`engine/boot_resume.py:131-133` 로그만) → `strategy_switch` 없음 → 예약 조회 실패로 EMA 매수가 계속 막힘 | 분기 밖 표 「예약 조회 실패」 줄과 T12: 테이블 없음 + 활성 EMA/MACD = 예약 없음 + CRITICAL. 시험 `test_switch_table_missing_ema_buys_and_alerts` |
| 5 (중) | 콜백에 상태 없음(`engine/order_reconciler.py:147-170`), 문구 「지정가 FILLED 만」 틀림(`:318` 은 주문 종류를 보지 않음), 실제 오인 방지 장치는 체결 확정 때 포지션 갱신(`:535`) | T6 「체결 반영」: 콜백에 `state` 인자, PULLBACK 아닌 경로는 `FILLED` 만. 문구 「BUY FILLED 전부」. 시험 `test_position_updated_on_fill_finalize` |
| 6 (중) | `audit_settings` 는 분 단위 UPSERT(`services/db.py:1572-1605`)로 정기 스냅샷(`engine/live_loop.py:1018-1022`)에 덮이고, `fetch_latest_audit_settings`(`:1527`)가 「엔진 적용 조건」으로 읽음 | T13 변경 기록을 `strategy_switch`(kind `PARAMS`)로 옮김, 결정 13-8 신설, 9절 spec 4.6 정정 |
| 7 (중) | 1분 스냅샷 `_do_snapshot`(`engine/live_loop.py:997-1015`)이 PULLBACK 에서도 옛 조건 파일을 읽음 | T5 「조건 파일 안 읽음」에 `_do_snapshot` 분기 추가, 시험 `test_pullback_snapshot_uses_applied_tp_sl_empty_conditions` |
| 8 (낮) | 되돌림 구간 조건이 조회 WHERE 에 없음, `mark_revert.py` 는 운영 DB 쓰기 | T7 WHERE 에 구간 조건, 배포 절 7 ③ 승인 범위 문구 |
| 9 (낮) | TEST 분할 반영 경로, 복구 대기 sleep 중 stop 무효, 복구 래퍼 재시작은 쉼 표식 없음 | T6 「TEST 체결」, T11 「알려진 한계」 |
| 10 (낮) | 13-2·13-3 승인 목차 문구 변경 표시, 13-5 매도 신호도 놓침 | 13절 표 |

### 0-1c. 3회째 검증 반영표 (verifier 3회째: 교착 해소·큐 설계 성립, 남은 수정 5건)

| 지적 | 요지 | 고친 곳 |
|---|---|---|
| 1 | 「`_execution_lock` 은 봉 처리에 쓰이지 않음」은 틀림 — `:432`·`:790,808`·`:914,962` 도 잡음 | 0-1b 1번 줄·T11 (ii) 문구 정정. 큐에서는 PULLBACK 강제 매수(`_execute_pullback_buy reason=FORCE`, 시장가라 재진입 없음)만 잠금 안, EMA `force_buy_in`·`force_sell` 은 잠금 밖. 시험 `test_force_buy_pullback_vs_fill_callback_serialized`·`test_ema_force_buy_called_outside_lock` |
| 2 | `_ready` 를 `:1243` 에서 세우면 PULLBACK 재생·복원 전 | 메인 루프 진입 직전(`:1310` 부근)으로 옮김, T11 Files·본문, 시험 `test_ready_set_after_pullback_restore` |
| 3 | BACKFILL 이 봉별 루프와 `pullback_backfill` 로 두 번 들어감 | PULLBACK 이면 `engine/live_loop.py:1427-1436` 봉별 루프를 건너뛰고 `pullback_backfill` 만 재생·감사 UPDATE, 시험 `test_backfill_no_double_feed` |
| 4 | 로그 문구에 `strategy_switch` kind 구분 없음 | T16 문구 표(PARAMS = 「설정 적용 · 바뀐 키 · 적용 시점」, SWITCH/REVERT 만 「전략 전환 완료」), 시험 `test_logs_params_row_not_switch`·`test_logs_switch_kinds_states` |
| 5 | 180초 넘는 워밍업·LEGACY_LOCAL 기재 | T11 알려진 한계 (c)(d), 12절 21·22번 |

### 0-1d. 4회째 검증·Fable (10/27)
- verifier 4회째: 「사용자 승인 요청 가능」. 문구 오류 2건(T11 (i) `_on_limit_fill` 432·`_on_hts_detect` 382, 12절 21번 대기 합 약 45초)은 PO 가 고침.
- Fable `docs/fable/2026-10-27-phase2-plan-1.md` 1회째 「수정 후 진행」: 12절 18번을 verifier 3회째 서버 실측(`fixed_price_buy_enabled` = true)으로 정정, 13-4 ⚠·재시작 효과 2줄, 13-5 요청서 8절 3 비교, 검증 원문 저장소 이동, 9절 85행 조건부 정정 — 모두 반영.
- 3회째·4회째 지적 원문은 파일로 남기지 않았다. 0-1c·0-1d 반영표가 기록이다.

### 0-2. 목차와 다른 사실

| # | 목차 내용 | 찾은 사실 | 근거 | 계획서에서 한 일 |
|---|---|---|---|---|
| X1 | T6·T7 의 스키마 변경 = 분할 상태 새 테이블 1개 + 거래 행 전략 칸 | 예약을 재시작 뒤에도 유지하고(요청서 6절), 복귀 대상(직전 전략·종목·봉 단위)을 남기려면 저장소가 필요하다. pullback spec 4.7 은 「전환 요청은 사용자 DB에 남긴다」. T7 의 「테이블별 최대 id 기록」도 둘 곳이 필요하다 | `docs/specs/pullback-strategy/spec.md:175,187`, 목차 T7 | 결정 13-1. 본문은 권고(같은 마이그레이션에 새 테이블 2개 `strategy_switch`·`schema_marks`)로 쓰고 배포 승인 「스키마 변경」 목록에 적는다 |
| X2 | T2 「엔진이 적용본을 쓸 때마다 **직전** 적용본을 마지막 정상 사본으로 남김」 | 글자 그대로면 첫 적용 직후에는 사본이 없다. 그 첫 거래 도중 적용본이 깨지면 「둘 다 없음 + 보유」가 되어 운영자 절차로 간다 | 목차 T2 | 결정 13-2. 본문은 보완안(권고) 「새 적용본을 쓰고 다시 읽어 검증한 뒤 같은 내용을 사본에도 쓴다」로 쓴다. 목차 문구대로 고르면 T2 `apply_saved` 순서만 바뀐다 |
| X3 | T2 「적용본 없음 = 설정 없음 → 미보유면 기동 거부」와 「적용본이 없거나 깨졌으면 사본으로 기동」 | 두 문장이 「적용본 없음 + 사본 있음 + 미보유」에서 겹친다 | 목차 T2 | 결정 13-3. 본문은 권고 「사본이 정상이면 보유 여부와 관계없이 사본으로 기동 + CRITICAL 알림」(T2 경우 5·7). 거부는 사본도 없을 때만이다 |
| X4 | D11(b) 「앱 매수(구버전 강제 매수 포함) — 미보유 중이든 보유분에 섞이든」 | 구버전 강제 매수 단추는 코인 평가액이 5,000원 미만일 때만 주문한다. 보유분에 섞이는 길은 업비트 앱 매수뿐이다 | `pages/dashboard.py:2398-2421` | T15 시험은 「미보유 + 구버전 강제 매수」와 「보유 + 앱 매수」로 나눈다. 규칙은 D11(b) 그대로다 |
| X5 | T7 「구버전 강제 매도 `:2428`」 전략 기록 | 구버전 강제 매수·매도는 `UpbitTrader` 를 `strategy_type` 없이 만든다. 지금 거래 행의 이력 id 도 늘 비어 있다 | `pages/dashboard.py:2400-2402,2429-2431`, `core/trader.py:311-312` | T7 에서 두 곳 모두 `strategy_type=` 인자를 넘긴다 |
| X6 | T5 「늘 시장가」 | 미확정 봉 매수는 WO-2 지연 큐로 가고, 이 큐는 EMA 직전 값으로 재판정한다 | `core/strategy_engine.py:1139-1210` | PULLBACK 매수는 지연 큐를 타지 않는다(확정 봉에서만 판정). T5 에 시험 추가 |
| X7 | F10 줄 번호 `core/trader.py:580-581` | 실제 `krw_amount` 축소 줄은 581-582 | `core/trader.py:581-582` | 계획은 실제 줄을 쓴다 |
| X8 | T13 「종목 변경 = 예약 전환」 | 지금 저장 경로는 종목을 늘 엔진 현재 전략 파일의 종목으로 쓴다. 저장으로 종목이 바뀌는 경우는 엔진 종목이 그사이 바뀐 때뿐이다(봉 단위는 화면 값으로 바뀜) | `v2/api_write.py:111-122`, `v2/params_schema.py:103-123` | 규칙은 목차대로 넣고, 시험은 봉 단위 변경으로 한다 |
| X9 | (목차에 없음) 종목 이름 규칙 | 엔진 `LiveParams` 는 종목에 숫자를 받지 않는다. 신버전 업비트 종목 검사는 숫자를 받는다 | `engine/params.py:180-189`, `v2/params_schema.py:46` | 범위를 늘리지 않는다. 적용 요청 때 엔진이 `LiveParams` 검증에 실패하면 거절 결과로 돌려준다(T13 시험 1건) |
| X10 | T8 감사 로그 칸 | 새 칸은 기존 JSON 칸(`audit_buy_eval.checks`, `audit_trades.meta`)에 넣으면 스키마 변경이 없다 | `services/init_db.py:276-292,987-1001` | T8 은 스키마를 바꾸지 않는다 |
| X11 | T4 「기동 직후 대기」, 요청서 3절 「켠 직후 이미 골든크로스 상태여도 바로 사지 않고 다음 골든크로스를 기다립니다」, pullback spec 85행 | 원본 `simulate()` 는 감시 구간(`active`)이면 골든크로스 순간이 아니어도 눌림목 조건으로 1회차를 산다. 「다음 골든크로스를 기다린다」는 골든크로스 1차 매수 경로에만 맞다 | 원본 HTML 343-357(`entryCount===0` 이면 `firstEntryTrigger="PULLBACK"`, 352행) | 결정 13-4. 본문은 권고(가) 「원본과 같게 — 켠 직후에도 감시 구간이면 눌림목 1회차 가능」으로 쓰고 문안 B 에 한 줄 |
| X12 | T4 「판정 = 확정 봉 마감」 | 확정 재시도가 다 실패하면 엔진이 잠정 봉(O=H=L=C=잠정 종가, `is_confirmed=False`)을 `on_new_bar_confirmed` 로 넣는다 | `engine/live_loop.py:1787-1800` | 결정 13-5. 본문은 권고(가) 「잠정 봉은 PULLBACK 지표에 넣지 않고, 확정값이 오면 그 봉부터 재생」 |
| X13 | T5 「기존 보호 장치 그대로」 | PULLBACK 조건 파일이 없으면 엔진은 옛 공용 조건 파일 `{user}_buy_sell_conditions.json` 으로 폴백한다(서버에 386B 파일 있음 — verifier 실측) | `engine/live_loop.py:616-646` | PULLBACK 은 조건 파일을 읽지 않는다(T5) |
| X14 | D10 「로그인 자동 검증」 | 수동 계정 검증(`app.py:386-394`)도 운용자산을 원화 잔고로 덮어쓴다 | `app.py:394` | D10 의 「로그인」을 로그인 화면의 두 검증 경로로 읽는다(결정 D10 취지 — 보유 중 회당 금액 고정). 문안 B 문구 「로그인해도」와 맞음 |

---

## Global Constraints

### 금지 행위 (목차 머리말 + 1차 계획)
- EMA·MACD 판정(매수·매도 신호와 그 사유)을 바꾸지 않는다. 판정 경로의 새 코드는 PULLBACK 분기(`if self.strategy_type == "PULLBACK"`) 안에 둔다. 분기 밖에서 바꾸는 곳은 아래 표에 있는 것뿐이고, 각각 「EMA·MACD 판정 불변」 시험을 둔다.

**분기 밖 변경 목록(EMA·MACD 에도 닿는 곳):**

| 곳 | Task | 바뀌는 것 | EMA·MACD 판정 | 시험 |
|---|---|---|---|---|
| 거래 행 `strategy_type` 기록(trader·reconciler·HTS·강제 매매) | T7 | 행에 칸 하나를 더 씀 | 불변(쓰기만) | `test_ema_rows_tagged_all_paths` |
| 구버전 이력 조회 WHERE | T7 | PULLBACK·분류 불명 행 제외 | 불변 | `test_a18_history_same_before_after` |
| `start_engine`·`stop_engine` 인자(`strategy`·`mode`) | T11 | 인자가 있을 때만 세션 대신 사용 | 불변(인자 없으면 지금 경로) | WO-12 시험 전부, `test_old_engine_behaviour_unchanged` |
| 예약 중 매수 차단(`execute` BUY 게이트) | T12 | 예약이 있으면 EMA·MACD BUY 도 차단 | 예약 중에만 바뀜(요청서 6절) | `test_reserved_blocks_all_buys`, `test_no_reservation_ema_buy_unchanged` |
| 예약 조회 실패 | T12 | DB 읽기 예외(잠금·디스크 등) → 「예약 있음」으로 보고 BUY 차단 + WARNING `[SWITCH-STATE] read failed`(안전 쪽). 매도는 계속. **단, `strategy_switch` 테이블이 없음(마이그레이션 실패 — `engine/boot_resume.py:131-133` 은 로그만 남김) + 활성 전략 EMA/MACD 이면 「예약 없음」으로 보고 매수 계속 + CRITICAL 1회(dedupe 1시간) 「새 전략 테이블 없음 — 마이그레이션 확인」.** 테이블 없음 + 활성 PULLBACK 은 BUY 차단(정상 경로에서는 생기지 않음) | 조회 실패 때만 매수 멈춤, 테이블 없음 + EMA/MACD 는 불변 | `test_reservation_read_failure_blocks_buy_only`, `test_switch_table_missing_ema_buys_and_alerts` |
| 구버전 화면 잠금·배지(`pages/*.py`, `app.py`) | T15 | PULLBACK·예약 중에만 잠김 | 엔진 판정 무관 | T15 시험 |
| reconciler 체결 콜백(분할 체결) | T6 | 콜백에 `state` 인자를 더하고, BUY·체결량 있는 `CANCELED` 도 부름. 엔진은 `_pending_split_uuid` 일치 때만 새 경로, 그 밖은 `state == "FILLED"` 일 때만 지금 경로 | 불변(지금도 `FILLED` BUY 에만 부름 — `engine/order_reconciler.py:318`) | `test_limit_fill_callback_unchanged_for_ema` |
| 엔진 제어 큐(강제 매매 실행 위치) | T11 | 엔진 스레드가 매 루프 앞에서 제어 큐를 비움(`engine/live_loop.py` 루프 1311) | 불변(큐가 비면 아무 일 없음) | `test_control_queue_empty_no_effect` |
| **위험: 잠금 재진입 교착** | T11 | 감시 스레드가 `_execution_lock` 을 쥔 채 `force_buy_in` 을 부르면 지정가 경로가 같은 잠금을 다시 잡아(`core/strategy_engine.py:125`) 교착 → 봉 처리·손절 정지 | — | 설계로 금지(감시 스레드는 잠금을 잡지 않음) + `test_control_never_holds_execution_lock`·`test_force_buy_fixed_price_no_deadlock` |
| 생존 파일 `gen` 칸 | T11 | 칸 하나 더 씀 | 무관 | `tests/v2/test_engine_alive.py` 기존 + gen |
- 지표 전체 재계산 금지. 증분 갱신과 BACKFILL 범위 재생만 쓴다(CLAUDE.md 금지 사항).
- 신버전 프로세스(`v2/*`)에서 엔진 함수(`start_engine`·`stop_engine`·`UpbitTrader` 등)를 부르지 않는다. `v2/*` 는 `engine.`·`core.`·`services.`·`config`·`pyupbit` 를 import 하지 않는다(기존 시험 `test_server_import_graph_clean` 유지).
- 실매매 DB 스키마 변경은 `services/init_db.py` 의 마이그레이션 함수로만 한다. 손으로 ALTER 하지 않는다.
- 세션(로컬·서버)에서 서버 DB 를 열지 않는다. 꼭 필요하면 「승인 받은 뒤 1회」로 표시하고 PO 가 따로 받는다.
- 서버 SSH, `pip install`, 외부 내려받기, `git commit`·`push`, 서버 설정 변경을 실행 에이전트가 하지 않는다.
- 여러 줄 텍스트·스크립트는 파일 도구로만 쓴다. 셸 heredoc 을 쓰지 않는다(빈 heredoc 도 금지).
- 키 값은 어떤 보고·로그·문서에도 쓰지 않는다.

### 규칙 체크리스트 (모든 Task 공통)
- [ ] 커밋마다 `pages/dashboard.py` 버전 갱신(`date '+%Y.%m.%d.%H%M'`, `grep -n "v1.2026" pages/dashboard.py`). 보고에 「버전: 구 → 신」.
- [ ] 새 시각 칸(첫 진입 시각·예약 시각·요청 시각·결과 시각)은 KST ISO(`+09:00`). `datetime.now(ZoneInfo("Asia/Seoul")).isoformat()` 만 쓴다(Issue #2).
- [ ] UI 1-A·1-B: 구버전 `pages/*.py` 와 **`app.py` 로그인 자동 검증 변경(D10)** 은 `bash scripts/regression_gate.sh`, UI diff 브리핑(사라짐·이동·접힘·잠김 목록), 배포 뒤 브라우저 실측 요청.
- [ ] 접힘 화이트리스트(감사로그 뷰어 열기·설정 페이지 이동·헬스 배지·강제 매수·매도)는 top-level 유지. 잠금은 `disabled=True` + 글자 「(잠김)」으로 하고 숨기지 않는다.
- [ ] `bash scripts/regression_gate.sh` 통과(v2 Python·v2 JS·회귀 전부).
- [ ] 투자자 통보는 배포 날 문안 B 1회, `docs/operations/investor-notice-log.md` 에 1줄.
- [ ] 서버 유닛·DB·서버 설정 변경은 배포 승인 요청서에 항목으로 적는다.
- [ ] push 전 `git status` 로 스테이징 확인. 명령을 `;` 로 묶지 않는다.
- [ ] 로그 집계 「0건」 보고 전 검색어가 실제 로그 문자열인지 확인.

### 실행 방식
- subagent-driven: Task 하나를 실행 에이전트 1명이 맡는다. Task 가 끝나면 PO 가 검수 에이전트 2종(spec 대조, 코드 품질)으로 확인한다. 「반박됨」·「누락」은 고친 뒤 다시 검수한다.
- 커밋은 Task 마다 1회, PO 가 사용자 승인을 받은 뒤 한다. 커밋 메시지 머리에 「(v1.구 → v1.신)」.
- P3 마지막(T10)과 P4 마지막(T18) 뒤에 verifier 검증 → Fable 질의 → 사용자 구현 완료 보고(번들 zip).
- 서버 배포는 따로 승인받는다(배포 절).

---

## 1. 승인 요청서 대응표 (요청서 절·그림 요소 → Task → 시험)

| 요청서 | 요소 | Task | 시험 |
|---|---|---|---|
| 1절 | 로그인·계정 검증은 지금과 같음 — D10 으로 「새 전략 보유·예약 중에는 운용자산을 덮어쓰지 않음」만 다름(통보 문안 B) | T15 | `test_auto_verify_keeps_capital_while_pullback_holding`, `test_auto_verify_updates_capital_when_flat` |
| 2-가 | 배지 「전략: 눌림목 분할매수」 | T16 | `home.test.mjs` 「PULLBACK 배지」 |
| 2-가 | 분할 회차 「2 / 5회」 | T6, T16 | `test_assets_round_from_pullback_state`, `home.test.mjs` 「분할 회차 n / 최대회」 |
| 2-가 | 평균 매수가, 익절 가격(+5%), 손절 가격(-3%) = 평단 × (1 ± tp/sl%) | T16 | `test_assets_tp_sl_from_pullback_params`, `home.test.mjs` 「익절·손절 가격」 |
| 2-가 | 최신 신호 「눌림 대기 중 — … 다시 위에서 마감하면 3회차 매수」 | T8, T16 | `home.test.mjs` 「PULLBACK 신호 문장 6종」 |
| 2-가 | 최근 거래 「매수 2회 · 눌림목」·「매수 1회 · 골든크로스」·「매도 · 익절」 | T8, T16 | `home.test.mjs` 「거래 구분 회차」, `test_trades_include_round` |
| 2-가 | 엔진 동작·모드·일시정지 배지 | 1차 완료 | 기존 `home.test.mjs` |
| 2-가 | 전환 예약 배지(v2 spec 4.3 표 「전환 예약」) | T16 | `home.test.mjs` 「전환 예약 배지」 |
| 2-나 | 60선·200선 = 새 전략 MA 설정(ma60p·ma200p·maType) | T16 | `chart.test.mjs` 「PULLBACK MA 설정으로 선」 |
| 2-나 | 매수·매도 자리(회차 매수 여러 개) | T16 | `test_markers_include_split_buys` |
| 2-다 | 백테스터 「설정 저장」 → 5절 확인 창 | T13 | 아래 5절 줄 |
| 2-라 | 「매수 대기 — 눌림 상태, n회차 준비」 | T8, T16 | `test_logs_pullback_wait_line` |
| 2-라 | 「매수 체결 n회차 · 눌림목 · 평단 …」·「매수 체결 1회차 · 골든크로스」 | T8, T16 | `test_logs_split_buy_lines` |
| 2-라 | 「골든크로스 발생 (60선 > 200선)」 | T8, T16 | `test_logs_golden_event_line` |
| 2-라 | 「전략 전환 완료 → 눌림목 분할매수」 | T12, T16 | `test_logs_switch_done_line` |
| 2-라 | 「매도 체결 · 익절」 | T16 | 기존 `test_api_read` 체결 행 + `test_logs_split_buy_lines` |
| 2-라 | 「매수 건너뜀 — 원화 잔고 부족」 | T5, T16 | `test_split_skip_krw_short_audit`, `test_logs_skip_krw_short_line` |
| 2-마 | 「백테스터 규칙으로 전환」·「기존 전략으로 복귀」 | T12, T14 | `test_switch_request_flat_immediate`, `ops.test.mjs` 「단추 활성 조건」 |
| 2-마 | 「기존 전략으로 복귀 (지금은 해당 없음)」 — EMA/MACD 운용 중 비활성 글자 | T14 | `ops.test.mjs` 「EMA 운용 중 복귀 단추 글자·비활성」 |
| 2-마 | 「일시정지」·「엔진 정지」 | T14 | `ops.test.mjs` 「일시정지는 pause API」, `test_control_engine_stop` |
| 2-마 | 「강제 매수」·「강제 매도」 | T11, T14 | `test_control_force_buy_pullback_round`, `test_control_force_buy_ema_ratio`, `test_control_force_sell` |
| 2-마 | 「운용 설정 — 거래 시간 제한 등」 | T9, T14 | `test_trading_hours_blocks_orders_only`, `ops.test.mjs` 「운용 설정 저장」 |
| 2-마 | 엔진 꺼짐 때 「엔진 시작」 | T11, T14 | `test_control_engine_start_without_session` |
| 3절 | 감시 구간(60선 > 200선, 200선 기울기 ≥ 기준, 둔화) | T3, T4 | 일치 시험 `test_parity_*`(slopeDrop>0 포함) |
| 3절 | 1차 매수 = 골든크로스 순간, 끄면 1차도 눌림목 | T4 | `test_parity_*_golden_yes`, `_golden_no` |
| 3절 | 눌림목 매수 = 기준선 아래 → 위에서 마감, 최대 횟수까지 | T4 | `test_parity_*`, `test_armed_kept_when_splits_full` |
| 3절 | 1회 금액 = 운용자산 ÷ 최대 횟수 | T5 | `test_split_amount_is_capital_div_splits` |
| 3절 | 매도 = TP·SL 전량, 데드크로스(설정 시) 전량 | T4 | `test_parity_*_deadcross_yes/no`, `test_tp_priority_same_bar` |
| 3절 | 판정 = 봉 마감, 바로 시장가 | T4, T5 | `test_pullback_always_market`, `test_pullback_skips_pending_queue` |
| 3절 | 켠 직후 이미 골든크로스여도 골든크로스 1차 매수는 다음 골든크로스까지 안 함. 눌림목 1회차는 감시 구간이면 가능(X11, 결정 13-4 권고 가 — 문안 B 한 줄) | T4 | `test_no_golden_buy_right_after_start`, `test_pullback_first_buy_without_golden` |
| 4절 | 손익은 평단 기준, 회차마다 평단 다시 계산 | T6 | `test_split_avg_recalc` |
| 4절 | 예시 금액(300만·5회 → 60만) | T5 | `test_split_amount_is_capital_div_splits`(3,000,000 / 5 = 600,000) |
| 5절 | 「저장만 하기」 = 파일·이력만, 매매 불변 | T13 | `test_save_only_does_not_change_applied`, `test_save_only_does_not_change_v2_reads` |
| 5절 | 「이 설정으로 동작」 EMA/MACD → 6절 전환 확인 | T13 | `save.test.mjs` 「EMA 면 전환 확인 창으로」 |
| 5절 | PULLBACK 이면 다음 봉부터, TP/SL 즉시, 분할 줄이면 추가 매수만 멈춤 | T13 | `test_apply_next_bar`, `test_apply_tp_sl_immediate_while_holding`, `test_apply_fewer_splits_stops_adds_only` |
| 5절 | 엔진 꺼짐이면 「엔진을 시작할까요?」 | T13 | `save.test.mjs` 「엔진 꺼짐 질문」 |
| 5절 | 바이낸스 결과 = 저장만 | T13 | `save.test.mjs` 「바이낸스 사용 불가 유지」, `test_apply_rejects_binance_source` |
| 6절 | 전환 단추 → 확인 창(한 번 더) | T12, T14 | `ops.test.mjs` 「전환 확인 창」 |
| 6절 | 보유 없음 즉시 전환 | T12 | `test_switch_request_flat_immediate` |
| 6절 | 보유 중 예약, 기존 방식이 매도까지 관리, 추가 매수 안 함, 취소 가능 | T12 | `test_switch_reserved_while_holding`, `test_reserved_blocks_all_buys`, `test_cancel_reservation` |
| 6절 | 매도 완료 다음 봉 자동 전환 | T12 | `test_reserved_switch_on_next_bar_after_flat` + 「매도 완료」 경우별 시험 |
| 6절 | 재시작 뒤 예약 유지 | T12 | `test_reservation_survives_restart` |
| 6절 | 복귀 = 직전 전략·종목·봉 단위, 보유 중이면 새 전략 매도 규칙으로 판 뒤 | T12 | `test_revert_to_previous`, `test_revert_reserved_uses_pullback_exit_rules` |
| 6절 | 복귀 기록 없으면 EMA·MACD 직접 고름 | T12, T14 | `test_revert_without_record_requires_choice`, `ops.test.mjs` 「복귀 선택」 |
| 6절 | 알림·기록(전환·예약·완료·복귀, 회차, 사유), 「따로 하실 일 없음」, 손익 집계 제외 | T8, T12 | `test_switch_events_notify_no_action_needed`, `test_switch_events_not_in_pnl` |
| 6-나 | 배지 「새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다」 | T15 | `test_old_dashboard_badge_pullback` |
| 6-나 | 상태(보기만) 전략·보유 n / 최대회 | T15 | `test_old_dashboard_status_round` |
| 6-나 | 설정 저장·전략 변경·엔진 시작 (잠김) | T15 | `test_old_ui_locks_*` 9개(T15 잠금 표 9줄과 1:1) |
| 6-나 | 강제 매도·엔진 정지 열림 | T15 | `test_old_force_sell_pullback_ticker`, `test_old_engine_stop_open` |
| 6-나 | 감사 로그 뷰어 열기 열림 | T15 | `tests/regressions/test_r_2026_08_05_audit_viewer_accessibility.py` 의 `test_button_in_header_column_context`(기존 회귀 유지) + PULLBACK 상태에서 같은 단언 `test_audit_viewer_button_top_level_pullback`(T15 새 시험) |
| 6-나 | 전환 예약 중에도 잠금 | T15 | `test_old_ui_locked_while_reserved` |
| 7절 | 기존 대시보드·기능 그대로(강제 매수·매도 그대로) | T15, T7 | `test_old_force_buy_pullback_ticker`, 회귀 게이트 |
| 7절 | 앱 주문 감지·매도 거절 안내·일시정지가 새 전략에도 | T5, T6 | `test_pullback_pause_blocks_orders`, `test_pullback_hts_buy_sync`, `test_pullback_sell_reject_visible`(T5 새 시험 — SELL 거절이 `*_REJECTED` 행·알림으로 남음) |
| 7절 | 신버전 문제가 엔진에 번지지 않음 | T11 | `test_control_thread_exception_isolated`, A2·A3 유지 |
| 8절 | 회당 금액 < 5,000원 또는 잔고 부족 → 그 회차 건너뜀 + 감사 사유 | T5 | `test_split_skip_below_min`, `test_split_skip_krw_short_audit`, `test_split_never_shrinks_amount` |
| 8절 | 한 봉에서 둘 다 닿으면 익절 | T4 | `test_tp_priority_same_bar` |
| 8절 | 봉 마감 판정이라 체결가가 다를 수 있음(관찰 항목) | T10 | 일치 시험의 「비교 제외」 기록 |
| 8절 | 「익절」로 판정됐는데 실제로는 손해일 수 있음(드묾) | T8, 배포 관찰 | 감사 체결 행 meta 에 `judged_price`(TP/SL 가격)·실체결 평단을 함께 남김(`test_sell_row_has_judged_and_fill_price`), 24시간 관찰 항목 「익절 판정·손해 체결 건수」 |
| 8절 | 바이낸스 결과는 참고용 | T13 | `test_apply_rejects_binance_source` |
| 9절 | 2차 공개 = 운용 메뉴의 전환·복귀·예약 취소, 「이 설정으로 동작」 | T12~T14 | 위 줄들 |
| 9절 | 공개하는 날 알림 | 배포 절 | 통보 문안 B, notice-log 1줄 |
| 9절 | 신버전을 즉시 닫을 수 있고 자동매매는 그대로 | 배포 절 | 되돌리기 ②(운영자 대행 복귀), `systemctl stop tradebot-v2` 뒤 A2 |

---

## 2. Review Focus

1. 「저장만 하기」가 매매·신버전 화면 종목·봉 경계 창·미리 받기 어느 것도 바꾸지 않아야 한다 → T13 `test_save_only_does_not_change_applied`·`test_save_only_does_not_change_v2_reads`.
2. 보유 중 적용본이 깨진 채 재시작해도 익절·손절·데드크로스가 멈추지 않아야 한다 → T2 `test_boot_holding_corrupt_applied_uses_last_good`.
3. 예약 중에는 어떤 매수도 나가면 안 된다(EMA 의 새 골든크로스 포함) → T12 `test_reserved_blocks_all_buys`.
4. 회당 금액이 모자라면 금액을 줄여 사지 않고 건너뛰어야 한다 → T5 `test_split_never_shrinks_amount`.
5. 신버전 요청이 엔진 프로세스 안에서만 실행되고, 같은 요청이 두 번 실행되지 않아야 한다 → T11 `test_control_duplicate_ignored`·`test_control_expired_60s`.
6. 새 전략 거래가 구버전 설정 이력 화면·손익에 섞이지 않고, EMA 거래는 계속 보여야 한다 → T7 `test_old_history_excludes_pullback_rows`·`test_ema_rows_tagged_all_paths`.
7. 봇 자신의 분할 추가매수를 앱 매수로 오인하지 않아야 한다 → T6 `test_bot_split_buy_not_hts_30s`·`test_split_fill_uses_executed_qty_avg`.

---

## 3. 착수 전 — 세션 재개 표준 정지선 (project-rules 「세션 재개 표준 정지선」)

- [ ] **Step 1: 로컬** — `git log --oneline -10`, `git rev-parse HEAD`, `git status`. 기대: HEAD `12ec5a4` 또는 그 뒤 문서 커밋.
- [ ] **Step 2: 서버 (사용자 확인 후 — SSH 읽기 전용)**
  - `ssh root@orionhunter7.cafe24.com "git -C /root/upbit-tradebot-mvp log --oneline -10"`
  - `ssh root@orionhunter7.cafe24.com "git -C /root/upbit-tradebot-mvp rev-parse HEAD"` — 기대 `1747fcc…`(버전 1522)
  - `ssh root@orionhunter7.cafe24.com "systemctl show tradebot -p ExecMainStartTimestamp"`
  - `ssh root@orionhunter7.cafe24.com "systemctl show tradebot-v2 -p ExecMainStartTimestamp"`
  - `ssh root@orionhunter7.cafe24.com "grep -n 'v1.2026' /root/upbit-tradebot-mvp/pages/dashboard.py | head -1"`
  - `ssh root@orionhunter7.cafe24.com "cat /root/upbit-tradebot-mvp/mcmax33_active_strategy.txt; ls -l /root/upbit-tradebot-mvp/mcmax33_latest_params_PULLBACK.json"` — 기대 `EMA`, 0바이트·600(F17·F18)
- [ ] **Step 3: 표식** — `journalctl -u tradebot --since "1 hour ago" | grep -c "\[V2-CANDLES\]"`(tradebot 쪽 0), `journalctl -u tradebot-v2 --since "1 hour ago" | grep -c "status=429"`(0).
- [ ] **Step 4: 불일치면 멈춘다** — 계획서가 전제한 상태(서버 1747fcc, 활성 전략 EMA)와 다르면 이 계획을 「현실 대조표」로 바꾸고 사용자에게 보고한다.
- 기록 위치: `docs/specs/v2-dashboard/measure-20261028-phase2.md` 「정지선」 절.

---

## 4. 1단계 — 코드 무변경 확인 (읽기 전용)

기록 위치: 모두 `docs/specs/v2-dashboard/measure-20261028-phase2.md`(새 파일, 문서만 커밋, 버전 유지).

### 1-1 운용자산(`users.virtual_krw`) 갱신 경로 전수 — D10 근거
- [ ] 명령(로컬):
  - `grep -rn "save_user(" --include='*.py' . | grep -v "^./tests"`
  - `grep -rn "virtual_krw" --include='*.py' app.py pages services engine core | grep -v "^.*#"`
  - `grep -rn "UPDATE users" --include='*.py' services`
- [ ] 기대 결과(지금 확인한 것): `services/auto_verify.py:84`(LIVE 자동 검증), `app.py:394`(수동 검증), `app.py:521`(TEST 운용자산 설정), `pages/set_config.py:412-429`(전달만 — 쓰는지 다시 확인), `pages/dashboard.py:685,2472,2606`(URL 전달). 각 경로를 「쓰기/읽기/전달」로 표에 적는다.
- [ ] 판단: D10 이 막는 경로는 **로그인 화면의 LIVE 검증 2곳**(자동 `services/auto_verify.py:84`, 수동 `app.py:394` 의 `save_user`)이다(X14). 다른 쓰기 경로가 나오면 PO 에게 보고하고 T15 범위를 정한다.

### 1-2 서버 journal — 3분봉 무거래 봉 빈도, 워밍업 시간·요청 수 (사용자 확인 후 — SSH 읽기 전용)
서버 DB 는 열지 않는다. journal 만 읽는다.
- [ ] 무거래 봉 빈도(최근 24시간):
  - `ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-10-27 00:00' --until '2026-10-28 00:00' --no-pager | grep -c 'CONFIRMED-NO-TRADE'"`
  - `ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-10-27 00:00' --until '2026-10-28 00:00' --no-pager | grep -c '\[CONFIRMED\] 봉 처리 완료'"`
  - 기록: 두 수와 비율. 3분봉 하루 480봉 대비.
- [ ] 워밍업(마지막 엔진 기동):
  - `ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-10-26 00:20' --until '2026-10-26 00:40' --no-pager | grep -E '\[WARMUP\]|\[REST\] 다중 호출 시작|BOOT-RESUME'"`
  - 기록: `REST 초기 데이터 요청` → `REST 데이터 로드 완료` 시각 차, 그 사이 `다중 호출` 줄 수(=요청 묶음 수), `시드 방식=long_history bars=`.
- [ ] 판단: D8(워밍업 요청 최대 2,012봉(`_long_bars + 1`, `engine/live_loop.py:1140`) ≈ 업비트 11회)의 시간·요청 증가를 이 값으로 추정해 T3 Step 에 적는다.

### 1-3 원본 `simulate()` Node 기준값 생성기 동작 확인
- [ ] T10 의 생성기 `tests/v2/js/pullback_reference.mjs` 를 먼저 만든다(이 Step 만 코드 추가, 엔진 무변경).
- [ ] 1차 Binance fixture 로 확인: `node tests/v2/js/pullback_reference.mjs tests/v2/js/fixtures/klines_a.json tests/v2/js/fixtures/pullback_cfg_base.json` → 매수 목록(봉 시각, 회차, 사유)·매도 목록(봉 시각, 사유) JSON 이 나오는지.
- [ ] 같은 fixture 로 이식본 `run()`(harness) 거래 수와 생성기 매도 수가 같은지.
- [ ] 업비트 fixture 3세트는 T10 Step 0 에서 받는다(사용자 확인 후 — 외부 내려받기).

### 1-4 업비트 한도 재확인 (사용자 확인 후 — 외부 문서 조회)
- [ ] 기준: v2 spec 3절 D8 「IP 단위 공유, candle 그룹 초당 10회(공식 문서 2026-10-07 확인)」.
- [ ] 업비트 공식 문서 rate-limits 쪽을 읽어 갱신일·candle 그룹 한도·418 조건이 같은지 적는다. 바뀌었으면 멈추고 보고한다(D8 워밍업 증가·전환 재시작의 한도 판단 근거).

---

## 5. Task 순서와 의존 관계

| Task | 앞선 Task | ★ 엔진 매매 경로 | 스키마 변경 |
|---|---|---|---|
| T1 전략 등록 | 1단계 | ★ | — |
| T2 PULLBACK 로더(적용본) | T1 | ★ | — |
| T3 증분 지표·버퍼·BACKFILL 링 | T2 | ★ | — |
| T4 `on_bar` 규칙 | T3 | ★ | — |
| T5 엔진 연결(분할 매수) | T4 | ★ | — |
| T6 분할 포지션·새 테이블 | T5 | ★ | ⚠ 있음 |
| T7 거래 행 전략 칸 | T1 (T6 과 병행 가능, 커밋은 T6 뒤) | ★ | ⚠ 있음 |
| T8 감사 칸·용어·알림 | T6 | ★ | 없음(X10) |
| T9 거래 시간 제한 | T5 | ★ | — |
| T10 시험 묶음 | T1~T9 | — | — |
| T11 엔진 제어 요청 통로 | T1, T10 | ★(관리 계층) | — |
| T12 전환·예약·복귀 | T6, T11 | ★ | (X1 `strategy_switch`) |
| T13 저장본/적용본 | T2, T11, T12 | ★ | — |
| T14 운용 탭 단추 | T11, T12 | — | — |
| T15 구버전 표시·잠금·D10 | T1, T6, T12 | ★(강제 매수·매도) | — |
| T16 신버전 화면 2차 | T6, T8, T13 | — | — |
| T17 TEST/LIVE 분리 | T6, T11, T12 | ★ | (모드 칸, T6 테이블 안) |
| T18 서버 점검 스크립트 | T11, T13 | — | — |
| 문서 | T1~T18 | — | — |

P3(T1~T10)가 모두 통과한 뒤 P4(T11~T18)를 시작한다. 배포는 P3+P4 한 번이다(spec 5절).

---

## 6. P3 — 새 전략 엔진 (★ 엔진 매매 경로)

### T1: 전략 등록 (결정 D1)

**Files:**
- Modify ★ `engine/params.py`(`_validate_strategy_type` 192-214, `load_active_strategy` 465-485)
- Modify ★ `engine/live_loop.py`(생성 분기 883-929, `record_strategy_init` 호출 775-778)
- Modify ★ `engine/engine_manager.py`(`_engine_runner` 전략 결정 364-395)
- Test: `tests/regressions/test_r_2026_10_28_p3_t1_strategy_registry.py`

**결정 D1 반영:** `config.STRATEGY_TYPES = ["MACD","EMA"]`(`config.py:38`)와 `DEFAULT_STRATEGY_TYPE`(`config.py:40`)은 바꾸지 않는다. 엔진 전용 목록 `ENGINE_STRATEGY_TYPES = ("MACD", "EMA", "PULLBACK")` 을 `engine/params.py` 에 둔다. 구버전 전략 선택 상자(`pages/set_config.py:273-275`)에는 PULLBACK 이 보이지 않는다.

**활성 전략을 읽는 곳 전체 표(F19)와 PULLBACK 일 때 동작:**

| 곳 | 줄 | 지금 | PULLBACK 일 때 (계획) | Task |
|---|---|---|---|---|
| 엔진 관리자 전략 결정 | `engine/engine_manager.py:364-395` | 세션 → 활성 파일 → mtime → MACD | 활성 파일이 PULLBACK 이거나 예약 중이면 세션보다 활성 파일 먼저 → `engine/pullback_params.load_for_boot` | T1, T11 |
| 엔진 생성 분기 | `engine/live_loop.py:883-929` | MACD·EMA, 그 밖 ValueError | `IncrementalPullbackStrategy` 분기 | T1, T5 |
| 기동 이력 기록 | `engine/live_loop.py:775-778` | `seed_initial_snapshot`·`record_strategy_init` | PULLBACK 이면 부르지 않음(경고 반복 방지). 설정 기록은 v2hist | T1, T7 |
| 구버전 dashboard | `pages/dashboard.py:584-592,729-738` | `load_active_strategy_with_conditions` → `load_params` → 없으면 `st.stop()` | PULLBACK 표시 경로로 갈라짐(멈추지 않음) | T15 |
| 구버전 로그인 이동 | `app.py:540,569` | `load_active_strategy(...) or DEFAULT` | `include_engine_only=True` 로 읽어 PULLBACK 이면 대시보드로(파라미터 설정 단추는 잠김) | T15 |
| 구버전 조건 화면 | `pages/set_buy_sell_conditions.py:65` | 활성 파일 → URL·세션 | PULLBACK 이면 배지 + 저장 잠금 | T15 |
| 신버전 전략·params | `v2/db.py:189-232` | 활성 파일·`{user}_latest_params_{S}.json` | PULLBACK 이면 적용본 경로 | T13 |
| 신버전 홈 | `v2/api_read.py:200` | `_context` | 적용본 기준 종목·봉 | T13 |
| 신버전 저장 종목 | `v2/api_write.py:111-115` | 현재 전략 파일 종목 | PULLBACK 이면 적용본 종목 | T13 |
| 신버전 봉 경계 창 | `v2/candles.py:272` | 활성 전략 params `interval` | 적용본 `interval` | T13 |
| 신버전 미리 받기 | `v2/candles.py:608-615` | 활성 전략 params 종목·봉 | 적용본 종목·봉 | T13 |

**Interfaces:**
- `ENGINE_STRATEGY_TYPES: tuple[str, ...]`
- `load_active_strategy(user_id, *, include_engine_only: bool = False) -> str | None` — 기본(False)은 지금과 같다(PULLBACK 이면 None, 경고 1줄). True 이면 PULLBACK 도 돌려준다.
- `LiveParams._validate_strategy_type`: `ENGINE_STRATEGY_TYPES` 기준. MACD·EMA 결과 무변경, 모르는 값 폴백 무변경.

- [ ] **Step 1: 실패 시험**
  - `test_strategy_types_unchanged`: `config.STRATEGY_TYPES == ["MACD","EMA"]`, `DEFAULT_STRATEGY_TYPE == "MACD"`.
  - `test_load_active_strategy_default_hides_pullback`: 파일 `PULLBACK` → 기본 호출 None.
  - `test_load_active_strategy_engine_only`: 같은 파일 → `include_engine_only=True` 이면 `"PULLBACK"`.
  - `test_live_params_accepts_pullback`: `LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="PULLBACK")` → `"PULLBACK"`; `"XYZ"` → `"MACD"` 폴백(지금과 같음).
  - `test_engine_manager_prefers_file_for_pullback`: 세션 `strategy_type="EMA"`, 활성 파일 `PULLBACK` → 결정값 `PULLBACK`. 활성 파일 `EMA`·세션 `MACD` → 지금처럼 `MACD`(세션 우선 유지).
  - `test_live_loop_no_strategy_init_for_pullback`: PULLBACK 기동 때 `record_strategy_init` 호출 0.
  - `test_set_config_selectbox_has_no_pullback`: `pages/set_config.py` 의 selectbox 인자가 `STRATEGY_TYPES`(ast).
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t1_strategy_registry -v`
- [ ] **Step 3: 구현** — 위 Interfaces. `_engine_runner` 의 전략 결정은 「활성 파일(`include_engine_only=True`)이 PULLBACK 이면 그것, 아니면 지금 순서」. 생성 분기의 PULLBACK 은 T5 에서 채우고, T1 에서는 `NotImplementedError` 가 아니라 「PULLBACK 로더 없음 → 기동 거부 + `[PULLBACK-PARAMS]` ERROR」로 둔다.
  - **(10/27 구현 반영 — T1 검수)** 거부 위치는 생성 분기가 아니다. ① `engine/engine_manager.py` `_engine_runner` 가 결정값(`_decide_strategy_type`)이 PULLBACK 이면 `load_params`·`UpbitTrader` 를 부르기 **전에** 거부한다(기존 `load_params` 는 신버전 저장 형식의 빠진 `strategy_type` 을 MACD 로 채워 MACD 로 매매하게 됨). ② `engine/live_loop.py` `run_live_loop` 는 `[BOOT]` 줄 바로 뒤(HTS 정합·지갑 동기화·reconciler 등록 전)에서 `stop_event.set()` 후 거부하는 방어선을 둔다. T2·T5 는 이 두 거부를 적용본 로더·전략 객체로 바꾼다.
  - **T1~T5 사이 틈:** 활성 파일이 PULLBACK 이면 엔진이 기동을 거부해 보유분 손절도 멈춘다. 그래서 **T5 완료 전까지 활성 파일에 PULLBACK 을 쓰는 경로를 만들지 않는다**(쓰는 곳은 T12). 거부 시 CRITICAL 알림·`boot_resume` 실패 판정·감사 화면 기록은 T2/T5 에서 넣는다.
- [ ] **Step 4: 통과·게이트** — 같은 명령 + `bash scripts/regression_gate.sh`(EMA·MACD 회귀 전부).
- [ ] **Step 5: 커밋 승인 요청** — 파일 목록·「버전: 구 → 신」.

### T2: PULLBACK 전용 로더 — 엔진은 적용본만 읽음 (결정 D9)

**Files:**
- Create ★ `engine/pullback_params.py`
- Test: `tests/regressions/test_r_2026_10_28_p3_t2_pullback_loader.py`

**파일 3개:**
- 저장본 `{user}_latest_params_PULLBACK.json` — 신버전이 쓴다(지금 파일, 제자리 쓰기 `v2/api_write.py:31-38`). 엔진은 전환·적용 요청 때 복사 원본으로만 읽는다.
- 적용본 `{user}_applied_params_PULLBACK.json` — 저장소 루트. 엔진만 쓴다. 신버전 유닛은 루트가 읽기 전용이라(`ProtectSystem=strict`·`ProtectHome=read-only`, `deploy/tradebot-v2.service:25-27`) 시스템이 쓰기를 막는다.
- 마지막 정상 사본 `{user}_applied_params_PULLBACK.last_good.json` — 엔진만 쓴다. 600.

**Interfaces:**
- `PULLBACK_KEYS = ("ticker","interval","maType","ma60p","ma200p","pullbackP","slopeLB","minSlope","slopeDrop","buyOnGoldenCross","maxSplits","maxPullbackBuys","tp","sl","deadcross","compounding","capital","fee")` — 18키(`v2/params_schema.py:103-123` 과 같은 순서).
- `OPTIONAL_KEYS = {"enable_trading_hours": False, "trading_start_time": "09:00", "trading_end_time": "02:00", "allow_sell_during_off_hours": True}`(T9).
- `validate(d: dict) -> dict` — 18키 정확히(+선택 4키), 범위는 `v2/params_schema.py` `PARAM_FIELDS`·`SERVER_EXTRA_LIMITS` 와 같은 값을 다시 적고(엔진은 v2 를 import 하지 않음) 두 표가 같은지 시험한다. bool 3칸은 bool 만. `interval ∈ {minute1, minute3, minute5, minute60}`. `maxSplits = 0 and not buyOnGoldenCross` 거부(pullback spec 3절). 실패 → `PullbackParamsError(field)`.
- `read_json_strict(path) -> dict` — 0바이트·빈 문자열·JSON 깨짐·dict 아님 → `PullbackParamsError("empty"|"json"|"type")`. 반쯤 쓴 파일은 JSON 깨짐으로 걸린다.
- `sha256_of(path) -> str`(파일 바이트 그대로).
- `load_for_boot(user_id, *, holding: bool) -> tuple[dict | None, str]` — (params, source). source ∈ `"applied"|"last_good"|"none"`. 아래 경우별 표대로.
- `apply_saved(user_id, expected_sha: str) -> dict` — 저장본을 읽어 해시가 `expected_sha` 와 다르면 `PullbackParamsError("sha_mismatch")`. 같으면 `validate` → 새 적용본을 임시 파일에 쓰고 `os.chmod(tmp, 0o600)` → `os.replace` → 다시 읽어 검증 → 검증이 통과하면 같은 바이트를 사본에도 쓴다(임시 파일 → `os.replace`, 600). 결정 13-2 에 따름(보완안 권고; 목차 문구안이면 「덮어쓰기 전 적용본 → 사본」을 맨 앞에 둠). 돌려주는 값: `{"sha": …, "params": …}`.
- `required_bars(d) -> int = max(d["ma60p"], d["ma200p"], d["pullbackP"]) + d["slopeLB"] * 2 + 10`(pullback spec 4.3, 최대 2,010).
- `to_live_params(d, capital_krw: float) -> LiveParams` — LiveParams 필수값 채우기(v2 spec 4.5 176행). 아래 표.

**LiveParams 채우기 규칙:**

| LiveParams 칸 | 값 | 이유 |
|---|---|---|
| `ticker`·`interval` | 파일 값 | 엔진 공통 경로(`upbit_ticker`·`interval_sec`) |
| `strategy_type` | `"PULLBACK"` | T1 |
| `take_profit`·`stop_loss` | `tp/100`·`sl/100` | 기존 화면·감사가 소수 비율을 씀 |
| `cash` | `max(MIN_CASH, int(capital_krw))`(`config.py:23` 10,000) | 운용자산(7.1). 백테스트 `capital` 은 쓰지 않음 |
| `commission` | `MIN_FEE_RATIO`(`config.py:24`) | 백테스트 `fee` 는 쓰지 않음(pullback spec 4.2) |
| `order_ratio` | `1 / effMaxSplits` | 구버전 강제 매수 금액 규칙(T15) |
| `enable_trading_hours` 외 3칸 | 선택 4키 | T9 |
| 나머지(MACD·EMA 칸) | LiveParams 기본값 | PULLBACK 은 읽지 않음 |

**경우별 표(기동 때 — 적용본 × 사본 × 보유):**

| # | 적용본 | 사본 | 보유 | 동작 | 로그·알림 |
|---|---|---|---|---|---|
| 1 | 정상 | 있음 | 미보유 | 적용본으로 기동 | `[PULLBACK-PARAMS] source=applied` INFO |
| 2 | 정상 | 있음 | 보유 | 적용본으로 기동 | 같음 |
| 3 | 정상 | 없음 | 미보유 | 적용본으로 기동 | 같음 |
| 4 | 정상 | 없음 | 보유 | 적용본으로 기동 | 같음 |
| 5 | 없음·0바이트 | 정상 | 미보유 | 사본으로 기동(결정 13-3 에 따름) | `[PULLBACK-PARAMS] fallback reason=missing` + CRITICAL 「설정 파일 이상 — 직전 정상 설정으로 동작 중」 |
| 6 | 없음·0바이트 | 정상 | 보유 | 사본으로 기동(익절·손절·데드크로스 계속) | 같음 |
| 7 | 깨짐 | 정상 | 미보유 | 사본으로 기동(결정 13-3 에 따름) | `fallback reason=json|type|field` + CRITICAL |
| 8 | 깨짐 | 정상 | 보유 | 사본으로 기동 | 같음 |
| 9 | 없음·깨짐 | 없음·깨짐 | 미보유 | PULLBACK 기동 거부, 엔진 시작 실패(`start_engine` False) | ERROR + CRITICAL 「새 전략 설정이 없습니다 — 신버전에서 설정을 다시 적용해 주세요」 |
| 10 | 없음·깨짐 | 없음·깨짐 | 보유 | PULLBACK 기동 거부 | CRITICAL 「보유 중 새 전략 설정 없음 — 운영자 확인 필요」 + 운영자 절차(배포 절 되돌리기 ①: 운영자 수동 청산 또는 활성 전략 파일을 직전 전략으로) |
| 11 | 정상 | 깨짐 | 둘 다 | 적용본으로 기동, 사본은 다음 적용 때 바뀜 | WARNING `last_good invalid` |
| 12 | 운용 중 적용본이 손으로 깨짐 | — | 둘 다 | 다시 읽기(T13) 거부, 이전 적용본 값 유지 | WARNING `reload rejected` |

보유 판정은 `PositionState.sync_from_wallet()`(`core/position_state.py:79`) 뒤의 `has_position`.

**전환 요청 거절 조건(저장본 기준):** 전환·적용 요청 때 저장본이 0바이트·깨짐·검증 실패이면 거절한다(결과 코드 `saved_invalid`). 전환 전 적용본이 없는 것은 정상이다(전환 때 저장본을 적용본으로 복사하므로).

- [ ] **Step 1: 실패 시험**
  - 경우별 표 12줄을 각각 시험(`test_boot_case_01` … `test_boot_case_12`). 6번은 이름 `test_boot_holding_corrupt_applied_uses_last_good`.
  - `test_read_empty_file_rejected`: 0바이트 → `PullbackParamsError("empty")`(서버 F18 상태).
  - `test_read_half_written_rejected`: `'{"ticker": "KRW-J'` → `"json"`.
  - `test_in_place_overwrite_read`: 저장본을 `v2.api_write._write_in_place` 방식(`r+`·`truncate`)으로 바꾼 직후 읽기 → 새 내용(제자리 덮어쓰기 읽기, 목차 0절).
  - `test_apply_saved_sha_mismatch`: 저장본 해시 ≠ 요청 해시 → 거절, 적용본 바이트 불변.
  - `test_apply_saved_writes_600_and_last_good`: 적용 1회 → 적용본 600, 사본 = 같은 내용(결정 13-2 보완안), 600. 적용 2회 → 사본 = 2회째 내용. 검증 실패를 흉내 내면 사본은 그대로. `.tmp` 남지 않음.
  - `test_switch_rejects_invalid_saved`: 저장본 0바이트 → `saved_invalid`.
  - `test_ranges_match_v2_schema`: 엔진 범위표 == `v2/params_schema.py` `PARAM_FIELDS`(파일을 텍스트로 읽어 ast 로 비교 — import 없이).
  - `test_golden_only_zero_splits_rule`: `maxSplits=0, buyOnGoldenCross=False` 거부, `True` 이면 통과(effMaxSplits 1).
  - `test_to_live_params_fill`: `tp=5, sl=3, maxSplits=5, capital_krw=3_000_000` → `take_profit 0.05`, `stop_loss 0.03`, `cash 3_000_000`, `order_ratio 0.2`, `commission 0.0005`.
  - `test_required_bars_max`: `ma200p=1000, slopeLB=500` → 2010.
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t2_pullback_loader -v`
- [ ] **Step 3: 구현** — 표준 라이브러리 + `engine.params.LiveParams` 만. 파일 경로는 저장소 루트 기준(`engine/params.py` 의 상대 경로 규칙과 같게 `os.chdir(ROOT)` 전제 — `scripts/tradebot_boot.py:30-31`).
  - **(10/27 구현 반영 — T2 검수)** 경우별 표 5~10 의 CRITICAL 은 `services.notifier.send` 를 함수 안에서 import 해 보낸다(엔진 기존 방식과 같음, `v2/*` import 그래프 무영향). `config` 상수(`MIN_CASH`·`MIN_FEE_RATIO`)는 LiveParams 가 이미 끌어오는 것이다. 계획 밖 진입점 `reload_applied`(T13 용)·`check_saved_for_switch`(T12 용)를 두었다. `apply_saved` 는 쓰기 전에 LiveParams 검증까지 해 거절하고(`live_params`), 재검증이 실패하면 이전 적용본으로 되돌린 뒤 `verify` 로 거절한다. 사본 쓰기 실패는 적용 성공 + `last_good: False` + WARNING 이다.
  - **T5·T11 로 넘김:** ① 경우 9·10 의 「엔진 시작 실패(`start_engine` False)」는 T11 의 기동 준비 신호와 `start_engine` 변경이 있어야 하므로 **T5+T11** 이 맡는다. `boot_resume` 실패 판정·감사 화면 기록도 같다. ② `holding` 은 `sync_from_wallet()` 뒤의 `has_position` 이다 — T1 거부는 지갑 동기화 **앞**이므로, T5 는 `load_for_boot` 를 동기화 뒤에 부르거나 경우 9·10 문구 판정만 동기화 뒤로 미룬다. ③ T5 기동 경로는 `to_live_params` 의 `PullbackParamsError` 를 경우 9·10 과 같은 거부·알림으로 처리한다(잡지 않으면 기동이 거부 절차 없이 죽음).
- [ ] **Step 4: 통과·게이트**
- [ ] **Step 5: 커밋 승인 요청**

### T3: 증분 지표 상태 + 버퍼 + BACKFILL 링 버퍼

**Files:**
- Create ★ `core/strategy_pullback.py`(`PullbackIndicators`, `PullbackSnapshotRing`)
- Modify ★ `engine/live_loop.py`(워밍업 봉 수 `_long_bars` 1136-1138, `CandleBuffer(maxlen=500)` 787 — PULLBACK 일 때만)
- Test: `tests/regressions/test_r_2026_10_28_p3_t3_pullback_indicators.py`

**Interfaces:**
- `class PullbackIndicators(ma60p, ma200p, pullbackP, slopeLB, maType)`:
  - `update(close: float) -> dict` — 한 봉 증분. 돌려주는 값 `{"maTrend","ma200","maPullback","slope200","slope200_lb"}`(없으면 None).
  - EMA: 첫 `period` 종가 단순평균으로 시드, 그 뒤 `prev + k*(c - prev)`, `k = 2/(period+1)`(원본 `computeEMA` 199-212행과 같은 식: `c*k + prev*(1-k)`). 부동소수 순서를 원본과 같게 `c*k + prev*(1-k)` 로 쓴다.
  - SMA: 합계 `sum` 과 `deque(maxlen=period)`. 원본 `computeSMA` 186-195행처럼 더한 뒤 뺀다.
  - `ma200` 이력 `deque(maxlen=slopeLB+1)`, `slope200` 이력 `deque(maxlen=slopeLB+1)`. `slope200 = (ma200 - ma200[-LB]) / abs(ma200[-LB]) * 100`, 분모 0 이면 None(원본 `computeSlope` 218-227행).
  - 전체 재계산 함수 없음(lint 시험).
- `class PullbackSnapshotRing(capacity: int)` — 봉마다 `(bar_ts, 지표 스칼라, SMA 합계, 분할 판정 상태(armed·prev_golden·가상 회차))` 를 담는다. 용량 = `RECONCILE_LOOKBACK_BARS + 1`(`config.py:124` 400 → 401). 종가 배열(길이 `max(period) + 401`)도 함께 두어 SMA deque 를 그 시점으로 되살린다.
  - `snapshot_before(ts) -> Snapshot | None`, `restore(snapshot)`.
- 워밍업: PULLBACK 이면 `_long_bars = max(LONG_SEED_BARS, required_bars(params) + 1)`(D8). EMA·MACD 는 지금 식 그대로(`engine/live_loop.py:1136`).
- 워밍업 재시도(F5): 지금은 2회째부터 `min_hist + 1` 만 요청한다(`engine/live_loop.py:1140`). PULLBACK 이면 `min_hist = required_bars(params)` 로 두어 재시도도 필요한 봉 수를 요청한다. 받은 봉이 `required_bars` 보다 적으면 PULLBACK 기동을 거부하고 CRITICAL 알림 「새 전략 워밍업 봉 부족 (받은 n / 필요 m)」 — 보유 중이면 T2 경우 10과 같은 운영자 절차. 200봉 SMA 폴백(`:1224`)은 PULLBACK 에 쓰지 않는다.
- **BACKFILL 연결(F15):** 누락 봉 BACKFILL 은 `engine/live_loop.py:1427-1523` 에서 봉마다 `engine.on_new_bar_confirmed(bar, …, {"backfill_mode": True})` 로 들어오고, 변경 봉 재평가는 `core/strategy_engine.py:894-1046` 의 `backfill_mode` 경로다. 이 루프는 `changed_ts` 에 든 봉(누락·변경)만 넣는다(`engine/live_loop.py:1433-1436` `backfill_ts_list`). 바뀌지 않은 뒤 봉은 다시 넣지 않으므로, PULLBACK 이 그 봉들만 재생하면 지표가 「바뀐 봉 + 옛 뒤 봉」 섞인 상태가 된다. 그래서 PULLBACK 이면 `engine/live_loop.py:1427-1436` 이하의 봉별 루프(봉마다 `on_new_bar_confirmed(…, backfill_mode=True)`)를 **건너뛰고**(3회째 — 두 번 넣지 않게), 그 자리에서 한 번 `engine.pullback_backfill(first_ts=min(backfill_ts_list), series=local_series, until_ts=closed_ts 직전 확정 봉)` 을 부른다: (1) `snapshot_before(first_ts)` 를 꺼내 `restore` (2) `local_series`(reconcile 이 이미 병합한 확정 봉 — 주석 `:1431-1432`)에서 `first_ts` 부터 직전 확정 봉까지 **바뀐 봉·안 바뀐 봉 모두** 차례로 넣으며 주문은 내지 않는다(Issue #9, 감사 행은 `pullback_backfill` 이 직접 `is_backfill=True` UPDATE — 봉별 루프의 감사 기록 역할을 대신함). (3) 끝나면 실시간 봉(`closed_ts`)으로 돌아간다. EMA·MACD 는 지금 봉별 루프 그대로. 스냅샷이 없으면(링 밖) 재생하지 않고 WARNING `[PULLBACK-BACKFILL] out of ring` — 그 봉의 지표는 지금 값 유지. EMA·MACD 의 지표 백업/복원(Issue #11, `_BACKFILL_TRAILING_FIELDS` `engine/live_loop.py:649`)은 바꾸지 않는다.
- 버퍼: PULLBACK 은 자기 deque 를 쓰므로 `CandleBuffer(maxlen=500)` 은 그대로 둔다. 「500 초과 허용」은 PULLBACK 지표 deque 길이(최대 1,000)로 충족한다.
- 무거래 봉(F6): 엔진이 건너뛰는 봉은 지표에 넣지 않는다(`engine/live_loop.py:1371-1377`). 원본·백테스터 업비트 출처도 빈 봉을 채우지 않으므로(`v2/candles.py:12-13`) 같은 봉 배열이 된다.

- [ ] **Step 1: 실패 시험**
  - `test_ema_matches_compute_ema`: 무작위 종가 1,200개 → 원본 식으로 만든 기준 배열과 모든 봉에서 `==`(같은 부동소수 순서) 또는 1e-12 이내.
  - `test_sma_matches_compute_sma`: 같은 방식.
  - `test_slope_none_when_zero_or_missing`.
  - `test_ring_capacity_401_and_restore`: 450봉 넣고 30봉 전 스냅샷으로 되살린 뒤 같은 30봉을 다시 넣으면 상태가 처음과 같음.
  - `test_no_full_recompute_function`: `core/strategy_pullback.py` 에 `pd.Series.ewm`·`rolling`·`talib` 문자열 0.
  - `test_warmup_bars_pullback_only`: PULLBACK `ma200p=1000, slopeLB=500` → 요청 2,012(`_long_bars`=2,011 + 1), EMA 는 지금 값.
  - `test_warmup_retry_uses_required_bars`: 1회째 실패 → 2회째 요청 수 = `required_bars + 1`(EMA 는 지금 `min_hist + 1`).
  - `test_warmup_short_refuses_start`: 받은 봉 < `required_bars` → 기동 거부·CRITICAL, 200봉 SMA 폴백 호출 0.
  - `test_backfill_restores_from_ring`: BACKFILL 봉 3개 → `restore` 1회, 재생 3봉, 주문 0.
  - `test_backfill_out_of_ring_warns`.
  - `test_backfill_replays_unchanged_tail`: 바뀐 봉 1개(j) + 뒤 바뀌지 않은 봉 5개 → 재생 봉 6개, 끝난 뒤 지표·armed = 바뀐 배열을 처음부터 넣은 값, 주문 0.
  - `test_backfill_no_double_feed`(3회째): PULLBACK BACKFILL 1회 → 봉별 루프의 `on_new_bar_confirmed(backfill_mode=True)` 호출 0, 각 봉이 지표에 정확히 1번 들어감(갱신 횟수 계측), 바뀐 봉의 감사 행 `backfill_*` UPDATE 1행씩.
  - `test_ema_backfill_loop_unchanged`: EMA 는 `changed_ts` 봉만 `on_new_bar_confirmed` 로 들어감(지금과 같음).
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트. 1-2 실측값으로 워밍업 시간 추정을 Step 메모에 적는다(업비트 11회).
  - **(10/27 구현 반영 — T3, 검수 반영)** 위치: `core/strategy_pullback.py` — `PullbackIndicators`·`PullbackSnapshotRing`(`RING_CAPACITY`=401)·`RingRestoreRejected`·`iter_valid_rows`·`feed_confirmed_bar`·`pullback_backfill`(엔진 메서드가 아니라 `pullback_backfill(engine, …)` 모듈 함수). 링은 봉마다 「넣은 뒤」 상태를 담고, SMA 창·ma200·slope 이력은 지표 객체의 긴 이력(최대 기간 + 401)에서 되살린다(`restore(snapshot, indicators, strategy)` — 링 뒤쪽 기록 수와 지표 n 이 맞는지 먼저 검사). `feed_confirmed_bar` 는 `replay_bar` 예외에도 링을 기록하고 `state_polluted` 를 켠 뒤 예외를 전파한다. `pullback_backfill` reason: `out_of_ring`·`restore_rejected`(되살리기 전 실패·시간대 비교 예외 — 상태 불변, 오염 아님)·`restore_failed`·`replay_failed`(오염). `engine/live_loop.py` — 도우미 6개 `_pullback_warmup_bars`·`_pullback_warmup_check`·`_pullback_holding`·`_pullback_warmup_gate`·`_pullback_seed_warmup`·`_pullback_backfill_step`(226~329행), `run_live_loop(…, pullback_cfg=None)`(837) 분기 5곳(1092 봉 수, 1257 `_long_bars` 덮어쓰기, 1321 관문 — 형성 중 봉은 `kept_insufficient` 여도 늘 빼고 다시 세어 모자라면 CRITICAL·거부(Issue #8), 1343 PULLBACK 시드, 1579 BACKFILL — 빈 목록을 돌려받아 봉별 루프를 건너뜀). 시드와 재생은 같은 `candle_validator` 규칙(F6 거래량 0 봉 제외)으로 거른다. `warmup_request` 식은 그대로 둬 1회째 `_long_bars+1`, 재시도 `required_bars+1` 이 된다. EMA·MACD 줄 변경은 시드 호출을 `else:` 아래로 들여 쓴 것과 폴백 경고 `elif` 에 `_seed_mode != "pullback"` 을 더한 것뿐(동작 불변). 감사는 바뀐 봉만 `insert_buy_eval(is_backfill=True)`(임시 DB 시험: backfill_* UPDATE 1행, 실시간 칸 불변, INSERT 0). 지표는 원본 JS(computeSMA·EMA·Slope)와 1,200봉에서 모두 `==`(node 로 1회 대조). 줄 번호는 10/28 커밋 시점 기준(T1 거부 862-865). 워밍업 거부 경로: `RuntimeError` → `run_live_loop` 바깥 except(2193-2198 근처)에서 재전파 → `engine_manager` 자동 재시작 최대 3회(`engine/engine_manager.py:351`) 뒤 정지, CRITICAL 알림은 1시간 dedupe — EMA 「Insufficient warmup data」와 같은 경로(Fable T3 권고 3).
  - **보유 판정 시점:** `_pullback_holding` = `sync_from_wallet()`(run_live_loop 앞부분) 뒤 `has_position` **또는** 봇 주문 진입가가 없어 False 로 되돌리고 워밍업 뒤 지갑 복원을 기다리는 `boot_seed_recover_qty > 0`(WO-12 C7). 앞의 것만 보면 외부 매수 보유를 미보유로 판정한다.
  - **링 밖 판정:** 되살리기는 전부 아니면 0 이다(일부 재생 없음). 기본 링 401·조회 400(closed_ts 제외 → 되돌림 최대 399봉)에서는 닿지 않고, 환경변수 `RECONCILE_LOOKBACK_BARS` 로 조회 수를 키울 때만 생긴다(링도 같이 커짐 — 경계 시험: 400봉 되돌림 일치, 401봉 out_of_ring).
  - **T4 로 넘김:** 실제 분할 판정 상태(armed·prev_golden·가상 회차)는 전략 훅 `replay_bar`·`export_split_state`·`restore_split_state` 로 담는 자리만 있다(시험은 대역 전략). **T4 조건: `replay_bar` 는 주문을 내지 않아야 한다**(워밍업·BACKFILL 재생 공용). 감사 칸 모양은 T8.
  - **T5 로 넘김:** `pullback_cfg` 를 넘기는 것 — PULLBACK 인데 `pullback_cfg=None` 이면 T5 에서 거부·CRITICAL. 실시간 확정 봉을 `feed_confirmed_bar` 로 넣는 것. `pullback_backfill` 호출 전체를 예외로 감싸기(지금 `_pullback_backfill_step` 은 바깥 루프 예외 처리에 맡김). `state_polluted` 때 매매 억제와 해제 조건(재시작 워밍업 재시드로만 해제 권고). `record_warmup_log` 의 PULLBACK 동작, 그리고 워밍업 버퍼 로그(`Buffer seeded`·`(완료 n/min_hist)`)가 PULLBACK 에서 버퍼 500봉 기준으로 찍혀 「지표 봉 수」로 오해될 수 있는 문구 정리.
  - **워밍업 시간 추정:** 2,012봉 = 업비트 200봉씩 약 11회 요청, 요청 사이 0.1초(`core/rest_reconcile.py:325-327`) → 대기 약 1초 + 응답 시간 = 약 1~3초(1-2 실측: 801봉 5회 약 1초).
- [ ] **Step 5: 커밋 승인 요청**

### T4: `IncrementalPullbackStrategy.on_bar` — 3절 순서

**Files:**
- Modify ★ `core/strategy_pullback.py`(`IncrementalPullbackStrategy`)
- Test: `tests/regressions/test_r_2026_10_28_p3_t4_pullback_rules.py`

**Interfaces:**
- `IncrementalPullbackStrategy(user_id, ticker, params: dict, interval_min: int)`
- `on_bar(bar, ind_snapshot, position, bar_count) -> Action` — 기존 전략과 같은 서명(`core/strategy_engine.py:821`). 내부 지표는 `PullbackIndicators` 를 쓰고 `ind_snapshot` 은 감사용으로만 받는다.
- 결과 속성: `last_buy_reason ∈ {"GOLDEN","PULLBACK"}`, `last_sell_reason ∈ {"DEADCROSS","TP","SL"}`, `last_eval: dict`(T8 감사 칸).
- `reload_conditions(buy, sell) -> dict` — PULLBACK 은 조건 파일을 쓰지 않으므로 빈 dict 를 돌려준다. `set_interval_min(n)`.
- 분할 판정 상태: `entry_count`, `pullback_count`, `first_entry_ts`, `armed`, `prev_golden`. 실제 값은 T6 분할 상태와 맞춘다.

**봉 하나의 평가 순서(원본 `simulate()` 296-363행, pullback spec 3절):**
1. `golden = maTrend>ma200`(둘 다 있을 때), `justCrossed = golden and not prev_golden`, `prev_golden = golden`(어느 경로로 빠지든 먼저 갱신).
2. 보유 + `deadcross` + `not golden`(둘 다 있음) → SELL `DEADCROSS`.
3. 보유 + `bar.ts > first_entry_ts` → `avg` 기준 `high ≥ avg×(1+tp/100)` 이면 `TP`, 아니면 `low ≤ avg×(1−sl/100)` 이면 `SL`(TP 우선).
4. `buyOnGoldenCross` + `justCrossed` + `entry_count == 0` + `active` + `entry_count < effMaxSplits` → BUY `GOLDEN`, armed 해제, 이 봉 끝.
5. `not goldenOnly` + `pullback_count < maxPullbackBuys` + `active` + `entry_count < effMaxSplits`:
   - `low < maPullback` 이면 armed.
   - armed + `close > maPullback` → BUY `PULLBACK`, armed 해제.
   - 그 밖(`not active` or goldenOnly or 눌림목 한도) → armed 해제. **전체 회차가 찬 경우는 armed 그대로**.
6. `active(i)`: 원본 `isFilterActive` 229-240행 그대로(과거 slope 없으면 둔화 조건 통과).
- 첫 체결 봉: 매수 판정 봉이 i 이면 `first_entry_ts` = i+1 봉 시각(실체결 봉). 따라서 TP/SL 은 i+2 봉부터다.
- 기동 직후(결정 13-4 에 따름 — 권고 가 「원본과 같게」): 워밍업 재생(T3)이 원본과 같은 상태를 만들므로 시작 시점에 이미 골든이어도 `justCrossed` 는 거짓이라 **골든크로스 1차 매수**는 다음 골든크로스까지 없다. 그러나 순서 5 의 눌림목 경로는 `entry_count == 0` 에서도 열려 있어(원본 343-357, 352행 `firstEntryTrigger="PULLBACK"`), 감시 구간이면 켠 직후에도 눌림목 1회차를 살 수 있다(X11). 결정이 (나)이면 「기동 뒤 첫 골든크로스 전 `entry_count == 0` 의 매수 금지」 플래그를 더하고 일치 시험 비교에서 기동 직후 구간을 뺀다. 워밍업 중 신호는 주문 없이 감사 `WARMUP`.
- 판정은 확정 봉 마감에만 한다(`on_new_bar_confirmed` 경로, `core/strategy_engine.py:867`). 실시간 형성 중 봉 경로(`on_new_bar` 764)에서는 PULLBACK 이 `Action.NOOP`.
- **잠정 봉(결정 13-5 에 따름 — 권고 가):** 확정 재시도가 다 실패하면 `engine/live_loop.py:1787-1800` 이 O=H=L=C=잠정 종가, `is_confirmed=False` 인 봉을 `on_new_bar_confirmed` 로 넣는다. PULLBACK 은 이 봉을 지표·판정 상태에 넣지 않고 `NOOP` + 감사 `failed_keys=["TENTATIVE"]` 만 남긴다. 그 봉의 확정값이 다음 REST Reconcile·BACKFILL 로 오면 그 봉부터 링 버퍼로 재생한다(T3 BACKFILL 연결). 그 사이 놓친 신호는 매수·매도(익절·손절·데드크로스) 모두 주문하지 않는다(재생 = 주문 없음). 매도는 다음 확정 봉에서 다시 조건이 맞을 때 나간다(결정 13-5 표).

- [ ] **Step 1: 실패 시험**(짧은 손 제작 봉 배열, 기대값을 손으로 적음)
  - `test_order_deadcross_before_tp`: 같은 봉에서 데드크로스와 TP → `DEADCROSS`.
  - `test_tp_priority_same_bar`: high ≥ TP, low ≤ SL → `TP`.
  - `test_tp_sl_from_signal_plus_two`: 신호 봉 i, i+1 봉이 TP 를 넘어도 매도 없음, i+2 봉에서 `TP`.
  - `test_golden_only_mode`: `maxSplits=0, buyOnGoldenCross=True` → 1회만, 눌림목 0.
  - `test_armed_kept_when_splits_full`: `maxSplits=2` 다 찬 뒤 `low<maPullback` 봉 → armed 유지(해제 안 됨).
  - `test_armed_cleared_when_inactive`.
  - `test_same_bar_arm_and_buy`: low < maPullback < close → 그 봉에서 armed 되고 바로 매수.
  - `test_no_golden_buy_right_after_start`: 처음부터 golden 인 배열 → 첫 골든크로스 전 사유 `GOLDEN` 매수 0.
  - `test_pullback_first_buy_without_golden`(결정 13-4 가): 처음부터 golden·active 인 배열에서 low < maPullback < 다음 close → 사유 `PULLBACK` 1회차 매수 1(원본 기준값과 같음). 결정 (나)이면 이 시험은 「매수 0」으로 바뀐다.
  - `test_unconfirmed_bar_noop`: 형성 중 봉(`on_new_bar`) → NOOP.
  - `test_tentative_bar_not_in_indicators`: `is_confirmed=False` 잠정 봉 → 지표·armed·prev_golden 불변, NOOP, 감사 `TENTATIVE`.
  - `test_confirmed_after_tentative_replays`: 잠정 봉 뒤 같은 ts 확정 봉이 BACKFILL 로 옴 → 그 봉부터 재생, 결과 지표 = 처음부터 확정 봉으로 넣은 것, 주문 0.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
  - **(10/28 구현 반영 — T4)** 위치: `core/strategy_pullback.py` 끝 `IncrementalPullbackStrategy`(`on_bar`·`replay_bar`·`export_split_state`·`restore_split_state`·`bind`·`reload_conditions`(빈 dict)·`set_interval_min`, 판정 `_step`·감시 구간 `_is_active`). T3 의 `feed_confirmed_bar` 본문은 공용 `_feed_bar(ind, ring, strategy, bar, step)` 로 옮겼다(동작 같음 — T3 시험 그대로 통과). 시험 `tests/regressions/test_r_2026_10_28_p3_t4_pullback_rules.py` 32건(계획 12건 + SL·눌림목 한도 armed 해제·slopeDrop 둔화·보유 중 2회차·워밍업 가상 회차 정리·중복 봉·훅 3·실보유 평단·원본 대조 2 + 검수 반영 8). 원본 대조: 원본 식 Python 기준(ema·sma × 골든 매수 켬·끔, 1,500봉) 과 node 로 원본 HTML `simulate()` 를 그대로 돌린 `pullback_reference.mjs` 1회(1,500봉) 모두 매수(신호 봉·사유)·매도(봉·사유) 목록 일치. 대조 일치 시험 묶음은 T10.
  - **상태:** `entry_count`·`pullback_count`·`first_entry_ts`·`first_entry_reason`·`armed`·`prev_golden`·`pending_fill`·가상 평단(`fill_n`·`inv_sum` — 회당 같은 금액이라 평단 = n/Σ(1/체결가), 원본 cost/qty)·`last_ts`. 신호 봉 i 에서 회차를 올리고 `pending_fill`, 다음 확정 봉 i+1 에서 그 봉 시가로 가상 체결·`first_entry_ts` = i+1 봉 시각(원본 `bars[i+1]`). 링은 봉마다 이 dict 를 담는다.
  - **보유 판정:** `on_bar` 에 `position` 이 있으면 실제 `has_position`, 없거나 재생이면 가상 보유(`entry_count > 0` = 원본 `qty>0`). TP/SL 평단은 실보유 `avg_price` 가 있으면 그것, 없으면 가상 평단.
  - **원본과 다르게 해석한 곳(원본에 없는 경우만):** ① 실보유 없음 + 판정 회차 > 0 → 회차 0 으로 맞춤, WARNING `[PULLBACK-RULE]`(이게 없으면 가상 회차가 남아 골든 매수가 막힘). armed 는 원본 closePosition 처럼 **해제**(앱 매도 직후 다음 봉 즉시 재매수 방지) — 단 그 거래가 워밍업·재생이 만든 가상 거래(`trade_origin="replay"`)면 armed 유지(결정 13-4 가 「켠 직후 감시 구간이면 눌림목 1회차」). 신호 봉 다음 봉(`pending_fill` 체결 대기, 실거래)에 실보유가 아직 안 보이면 정리를 한 봉 미룸(체결 지연). 미룸 봉에서는 매수를 막아(`failed_keys=["PENDING_FILL"]`) 새 신호가 `pending_fill` 을 다시 켜 미룸이 이어지지 않게 한다 — 미룸은 최대 1봉(시험 `test_pending_fill_defer_blocks_buy_at_most_one_bar`). ② 실보유인데 `first_entry_ts` 없음(앱 매수·재시작·매도 거절) → TP/SL 을 바로 평가(손절 보호 쪽). ③ GOLDEN 매수에 `not holding` 을 더함. ④ 원본의 `i+1<bars.length`·복리 `sizingBase>0` 조건은 뺐다(대조 시험은 마지막 봉 신호를 비교에서 뺌). ⑤ 실시간 TP/SL 은 실평단(`position.avg_price`), 원본은 다음 봉 시가 가상 평단 — **T10 일치 비교에서 실보유 구간 제외.** ⑥ 실보유 + 판정 회차 0(이 전략이 연 거래 아님 — 앱 매수·매도 거절) → GOLDEN·PULLBACK 매수 신호를 내지 않음(`failed_keys=["POS_DESYNC"]`, WARNING `[PULLBACK-RULE]`). 매도(②·데드크로스)는 계속 평가. T6 `test_pullback_hts_buy_sync` 방향.
  - **예외·오염(검수 반영):** `_guarded_step` — 판정 중 예외면 판정 상태를 봉 전으로 되돌리고 `last_ts` 만 그 봉으로 둔다(지표·링은 이미 그 봉을 받음 → 같은 봉 재투입은 `DUPLICATE` NOOP, 이중 반영 없음). `state_polluted` 이면 실시간 매수 판정을 건너뛰고 NOOP(`failed_keys=["STATE_POLLUTED"]`), 매도는 계속(엔진 게이트는 T5). `restore_split_state` 는 `first_entry_ts`·`last_ts` 문자열(T6 KST ISO)을 tz 있는 `pd.Timestamp` 로 바꾸고, 시간대 없는 값은 KST 로 본다(Issue #2). 시험은 검수 반영 후 32건.
  - **확정 봉만:** `is_closed`·`is_confirmed` 둘 다 참일 때만 판정. 아니면 NOOP, 지표·판정·링 불변. `source` 에 `TENTATIVE`(`WO2_OPTION_C_TENTATIVE:*`) 가 있으면 `last_eval.failed_keys=["TENTATIVE"]`, 형성 중 봉(WS)은 `["UNCONFIRMED"]`. `last_ts` 이하 봉은 NOOP `["DUPLICATE"]`(두 번 넣기 방지).
  - **T5 로 넘김:** 실시간 확정 봉은 `feed_confirmed_bar` 가 아니라 `strategy.on_bar` 로 넣는다(같은 `_feed_bar` 경로로 지표·링 갱신 — 둘 다 부르면 두 번 들어감). 엔진은 `_pullback_seed_warmup` 이 만든 지표·링을 `strategy.bind(engine.pullback_indicators, engine.pullback_ring)` 으로 넘기고 `engine.strategy` 를 이 전략으로 둔다. 회차 건너뜀(F12) 때 신호 봉에서 올린 `entry_count`·`pullback_count`·`pending_fill` 을 되돌리는 훅(armed 는 이미 해제)이 필요하다 — 지금은 다음 봉의 ① 정리가 실보유 없음으로 회차를 0 으로 맞추지만 보유 중 2회차 이상 건너뜀은 되돌려야 한다. SELL 주문 거절 시 전략은 이미 회차를 0 으로 둠 → 다음 봉은 ② 경로로 TP/SL·데드크로스 재평가, 매수는 ⑥ 으로 막힘. 형성 중 봉 경로(`on_new_bar`)에서 PULLBACK 은 부르지 않거나 NOOP 처리. 검수 추가: (1) `_pullback_seed_warmup` 을 부르기 **전에** `engine.strategy` 를 PULLBACK 전략으로 두어 시드가 판정 상태(prev_golden)까지 만들게 한다 — 순서가 반대면 기동 첫 확정 봉에 GOLDEN 매수(13-4 위반, verifier 재현). T5 시험 「기동 첫 봉 GOLDEN 0」, 가능하면 시드 봉 수와 전략 `last_ts` 일치 단언. (2) 잠정·건너뛴 봉이 다음 REST 대조에서 BACKFILL 대상에 반드시 들어가는지 시험, 안 되면 지표 오염 표식. (3) 실시간 호출은 늘 `position` 을 넘기고 None 이면 경고·NOOP(지금 `position=None` 은 가상 보유 판정 — 시험·재생용). (4) 매도 거절 시 분할 상태 처리(지금은 ⑥ 으로 매수만 막음) 재검토. (5) BACKFILL 재생에 실보유 여부를 넘길지. (6) 오염(`state_polluted`) 시 CRITICAL 알림·재시작 안내. 오염 중 데드크로스 매도는 유지(보호 쪽 — TP/SL 은 실평단·고가·저가라 지표 오염 영향 없음, 데드크로스는 오염 지표를 씀). 오염 해제는 재시작 워밍업으로만. (7) 실보유 없이 매수 주문이 계속 실패하면 2봉마다 BUY 신호가 반복됨(정리 → 재신호) — 엔진 쪽 건너뜀·알림 dedupe 로 막기.
  - **T6 로 넘김:** 재시작·보유 중 기동 때 분할 상태(회차·첫 체결 시각·평단 기준)를 T6 테이블에서 `restore_split_state` 로 되살리기. 실보유 + 판정 회차 0(앱 매수·매도 거절)은 ⑥(POS_DESYNC)으로 매수가 막힘 — T6 은 분할 상태 복원으로 매수 재개. BACKFILL 재생이 실거래 GOLDEN 을 다시 만들면 `trade_origin` 이 replay 로 바뀌는 경계(정리 때 armed 유지 여부가 달라짐) 확인. 분할 상태 저장 시각은 늘 오프셋 포함으로 쓴다(`_to_ts` 는 시간대 없는 값을 KST, `_kst_iso` 는 UTC 로 보는 규약 차이).
  - **T8 로 넘김:** `last_eval` 칸(지표 5개·active·golden·just_crossed·armed·holding·avg·tp/sl 가격·회차·split_round·failed_keys·재생이면 `mode=replay`·`replay_signal`) → 감사 칸 모양. 워밍업 신호 `WARMUP` 표시(재생은 워밍업·BACKFILL 을 구분하지 않고 `["REPLAY"]`). `POS_DESYNC`·`STATE_POLLUTED`·`TENTATIVE`·`UNCONFIRMED`·`DUPLICATE`·`PENDING_FILL` 라벨. `POS_DESYNC` 경고가 보유 중 봉마다 찍히므로 상태가 바뀔 때 1회로(dedupe). → **(10/28 T8 처리)** `audit_view()` 로 감사 칸 정리, 재생 `["REPLAY"]`·워밍업 `["WARMUP"]`, 라벨은 `services/terminology.PULLBACK_STATE_LABEL`, POS_DESYNC 경고 상태 바뀔 때 1회.
  - **T10 로 넘김:** node 원본 대조를 sma·golden-only(`maxSplits=0`)·deadcross 끔 구성까지 넓히기(T4 는 ema·골든 켬 1회).
- [ ] **Step 5: 커밋 승인 요청**

### T5: 엔진 연결 — 보유 중 매수 평가, 분할 매수, 늘 시장가, 회차 건너뜀

> **(10/28 T4 검수 — 필수)** T4 「구현 반영」 메모의 「T5 로 넘김」 (1)~(7) 전부를 이 Task 의 시험으로 만든다. 특히 (1) `_pullback_seed_warmup` 전에 `engine.strategy` 설정(어기면 기동 첫 봉 GOLDEN 매수 — 결정 13-4 위반), (7) 매수 주문이 계속 실패할 때 2봉마다 BUY 재신호 dedupe.

**Files:**
- Modify ★ `core/strategy_engine.py`(`is_buy_eval` 819·972, `execute` 1067-1137, `_execute_buy_or_defer` 1139, `_execute_buy` 1412-1540)
- Modify ★ `core/trader.py`(`buy_market` 541-600: 엄격 금액 인자)
- Modify ★ `engine/live_loop.py`(생성 분기에 PULLBACK, 1-2 의 `params` 를 `to_live_params` 로)
- Test: `tests/regressions/test_r_2026_10_28_p3_t5_pullback_engine.py`

**Interfaces:**
- `StrategyEngine`: `self.strategy_type == "PULLBACK"` 이면 보유 중에도 매수 평가(`is_buy_eval` 는 감사용으로만 쓰고 `on_bar` 는 매 봉 부름). EMA·MACD 는 지금처럼 미보유만.
- `_execute_buy`: PULLBACK 분기는 `already_holding` 차단(1420-1426)을 지나지 않는다. 대신 `_execute_pullback_buy(bar, indicators)`.
- `_execute_buy_or_defer`(1139): PULLBACK 이면 지연 큐 없이 `_execute_pullback_buy`(X6). 미확정 봉은 T4 에서 NOOP 이라 여기 오지 않지만 이중으로 막는다.
- `_execute_pullback_buy`:
  1. 회당 금액 `per_buy = floor(sizing_base / effMaxSplits)`. `sizing_base` 는 T6 분할 상태의 이 거래 배분 기준(1회차 때 운용자산 `users.virtual_krw` 를 읽어 고정 — D10, 복리면 + 전환 뒤 실현 손익 합).
  2. 가용 KRW `avail = trader._krw_balance()`(`core/trader.py:319`).
  3. `per_buy < 5000` → 건너뜀, `_audit_buy_blocked(code="split_below_min", note="1회 매수 금액 {per_buy:,}원 < 최소 5,000원 — n회차 건너뜀")`.
  4. `avail < per_buy * (1 + MIN_FEE_RATIO)` → 건너뜀, `code="split_krw_short"`, note 「원화 잔고 부족 (가용 {avail:,}원 < 회당 {per_buy:,}원+수수료) — n회차 건너뜀」.
  5. 통과 → `trader.buy_market(price, ticker, ts, meta, krw_amount=per_buy, strict_amount=True)`. 현재가·지정가(`fixed_price_buy`) 분기를 타지 않는다.
  6. meta: `reason`(GOLDEN|PULLBACK), `split_round = entry_count+1`, `pullback_round`, `sizing_base`, `per_buy`, `strategy_type="PULLBACK"`.
- `UpbitTrader.buy_market(..., krw_amount=None, strict_amount: bool = False)`: `strict_amount=True` 이면 `avail/(1+fee) < krw_amount` 일 때 줄이지 않고 `_audit_preorder_reject(code="split_krw_short")` 후 `{}`(`core/trader.py:581-582` 의 `min` 축소를 타지 않음). 기본 False 는 지금과 같다(WO-24 경로 무변경).
- **건너뜀 뒤(F12):** 건너뛴 회차는 원본의 「매수 직후」와 같게 armed 를 해제한다(같은 눌림에서 다음 봉마다 다시 건너뜀 알림이 쌓이지 않게). 회차·눌림목 회차는 늘리지 않는다. 알림은 T8 의 dedupe 키로 같은 거래·같은 사유에 1회. 건너뜀은 일치 시험 비교에서 뺀다(spec 6절).
- **조건 파일 안 읽음(F13, X13):** PULLBACK 이면 `_load_trade_conditions`(`engine/live_loop.py:616-646`)를 부르지 않고 `buy_conditions = sell_conditions = {}` 로 둔다. 옛 공용 파일 `{user}_buy_sell_conditions.json` 폴백이 PULLBACK 에 닿지 않는다. 조건 파일 mtime 감시(`_maybe_reload_params` 531)도 PULLBACK 에서는 건너뛴다(T13 의 적용본 감시가 대신함). 1분 설정 스냅샷 `_do_snapshot`(`engine/live_loop.py:997-1015`)도 지금은 `_load_trade_conditions` 를 부르므로, PULLBACK 이면 조건 dict 를 `{"buy": {}, "sell": {}}` 로 두고 `tp`·`sl` 은 전략 객체(적용본 `tp/100`·`sl/100`), `ts_pct`·`signal_gate`·`threshold` 는 None·0 으로 쓴다(지침 2회째 7).
- **trader `params_file`(R11):** 엔진 관리자는 trader 에 `params_file` 을 넘겨 매수마다 `order_ratio` 를 다시 읽게 한다(`engine/engine_manager.py:411-421`, `core/trader.py:249-286`). PULLBACK 이면 `params_file=None` 으로 만든다(PULLBACK 파일에 `order_ratio` 없음 — 엄격 금액 경로는 order_ratio 를 쓰지 않음). `risk_pct` 는 `to_live_params` 의 `1/effMaxSplits`.
- 기존 보호 장치 그대로: 일시정지 게이트(`core/strategy_engine.py:1086-1095`), WO-25 주문 전 차단 기록, WO-9 거절 가시화(`core/trader.py:449-540`), 묶인 수량, 앱 주문 감지(`_on_hts_detect` 368, `_reconcile_position_with_wallet` 615).

- [ ] **Step 1: 실패 시험**
  - `test_split_amount_is_capital_div_splits`: 운용자산 3,000,000·maxSplits 5 → `per_buy == 600_000`.
  - `test_split_skip_below_min`: 운용자산 20,000·maxSplits 5 → 4,000 → 주문 0, 감사 `split_below_min` 1행.
  - `test_split_skip_krw_short_audit`: 가용 500,000·회당 600,000 → 주문 0, 감사 `split_krw_short` 1행(note 에 「원화 잔고 부족」).
  - `test_split_never_shrinks_amount`: `strict_amount=True`·가용 부족 → `_upbit_buy_market` 호출 0(가짜 trader). `strict_amount=False` 는 지금처럼 줄여 삼(WO-24 회귀).
  - `test_pullback_always_market`: 조건 파일에 `fixed_price_buy_enabled=True` 가 있어도 `buy_limit` 호출 0, `buy_market` 1.
  - `test_pullback_skips_pending_queue`: 미확정 표시 봉이라도 `PendingOrderQueue.register` 호출 0.
  - `test_pullback_buy_eval_while_holding`: 보유 1회차 → 다음 눌림 봉에서 2회차 주문 1.
  - `test_ema_still_blocks_already_holding`: EMA 보유 중 BUY → `already_holding` 그대로.
  - `test_pullback_pause_blocks_orders`: `trading_paused=1` → 주문 0, 감사 `trading_paused`.
  - `test_skip_clears_armed_like_buy`: 잔고 부족 건너뜀 뒤 armed 0, 회차 불변, 같은 눌림 다음 봉 감사 건너뜀 행 0.
  - `test_pullback_does_not_load_conditions`: 옛 `{user}_buy_sell_conditions.json` 이 있어도 PULLBACK 기동 때 `_load_trade_conditions` 호출 0.
  - `test_pullback_snapshot_uses_applied_tp_sl_empty_conditions`: PULLBACK 1분 스냅샷 → `_load_trade_conditions` 호출 0, `audit_settings` 행 `tp=0.05`·`sl=0.03`(적용본 5·3), `buy_json`·`sell_json` = `{}`.
  - `test_pullback_trader_no_params_file`: PULLBACK trader `_params_file is None`, `_current_risk_pct() == 1/effMaxSplits`.
  - `test_pullback_sell_reject_visible`: 매도 `insufficient_funds_ask` 거절 → `SELL_REJECTED` 행(감사 로그 페이지 표) + 알림 본문에 「외부 미체결 매도 주문 확인」(외부 주문 공존 규칙).
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
  - **(10/28 구현 반영 — T5)** 위치: `core/strategy_engine.py` — `on_new_bar`(PULLBACK 미확정 봉 NOOP)·`on_new_bar_confirmed`(맨 앞에서 `_on_new_bar_confirmed_pullback` 로 분기, 포지션 늘 전달)·`execute` BUY(대기 주문 확인 뒤 PULLBACK 분기: 오염 차단 `state_polluted`+CRITICAL 1회, 아니면 `_execute_pullback_buy`)·`_execute_buy_or_defer`/`_execute_buy` 맨 앞 PULLBACK 가드, 새 메서드 `_execute_pullback_buy`·`_pullback_skip`·`_pullback_accumulate`·`_pullback_read_sizing_base`·`_record_pullback_audit`·`_pullback_notify_polluted`, 상수 `PULLBACK_BUY_FAIL_COOLDOWN_BARS=3`(결정 1028-03 (다))·`PULLBACK_MIN_ORDER_KRW=5000`. `core/trader.py` `buy_market(..., strict_amount=False)`·`_audit_strict_short`(재시도 루프에서도 줄이지 않음). `core/strategy_pullback.py` `rollback_last_buy`(주문이 나가지 않은 BUY 판정 → 회차를 신호 전 값으로 되돌림·armed 해제·링 갱신 `amend_last_split`)·`take_profit`/`stop_loss` 속성. `engine/live_loop.py` 전략 생성·바인딩(seed 전)·조건 파일 미사용·스냅샷 `_pullback_do_snapshot`·워밍업 진행 표기·`_pullback_backfill_step`(보유 중 회차 보존, 예외·복원 실패 → 오염+CRITICAL)·`_pullback_catchup_step`(잠정·건너뛴 봉 재생, 링 밖 → 오염). `engine/engine_manager.py` `_pullback_boot_params`(load_for_boot → `to_live_params`)·trader `params_file=None`·`pullback_cfg` 를 kwargs 로 전달. 시험 `tests/regressions/test_r_2026_10_28_p3_t5_pullback_engine.py` 51건(계획 14건 + T3·T4 넘김 항목 20건 + 검수 반영·결정 1028-03 반영 17건). 구현 전 실패 수(verifier 실측, HEAD + 새 시험 1차 34건): failures 16 · errors 12 · 통과 6.
  - T1 거부 처리: 무조건 거부를 로더 기반 기동으로 바꿨다. 적용본·last_good 없음, `to_live_params` 실패(virtual_krw 없음 등), `run_live_loop` 에 `pullback_cfg` 없음, `RUN_MODE != UPBIT_MATCH`, **LIVE(test_mode 아님 — 검수 반영)** 이면 지금처럼 기동 거부 + ERROR `[PULLBACK-PARAMS]` + CRITICAL 알림. 활성 파일에 PULLBACK 을 쓰거나 `apply_saved` 를 부르는 경로는 이번에도 없다(시험으로 고정, T12 에서 연다).
  - sizing_base 경계(T6 에서 교체): 1회차(미보유) 매수 때 `users.virtual_krw` 를 읽어 엔진 메모리 `_pullback_sizing_base` 에 고정한다. 재시작 뒤 2회차 이상에서 값이 없으면 지금 값을 읽고 WARNING. 실현 손익 복리 반영·영속화 없음. 2회차 이상 평단은 메모리 가중 평균(`_pullback_accumulate`). TEST 모드는 체결 수량으로 맞다. LIVE `buy_market` 은 qty=0.0 을 돌려주므로 가중 평균이 1회차 평단에 고정된다(추정 수량이 아님 — 정정). 그래서 T6 체결 반영 전까지 PULLBACK + LIVE 는 기동을 거부한다(엔진 관리자: trader 만들기 전, `run_live_loop`: 정합 검사 전, ERROR `[PULLBACK-PARAMS]` + CRITICAL 「새 전략 LIVE 는 분할 체결 반영(T6) 전 사용 불가」).
  - 회차 건너뜀·실패: 미확정 봉 `split_unconfirmed_bar`·자본 없음 `split_no_capital`·최소 미만 `split_below_min`·잔고 부족 `split_krw_short`·잔고 조회 실패 `split_krw_unknown`(검수 반영 — 엔진 첫 확인·trader 주문 전 조회·재시도 직전 재조회 모두. `_krw_balance` 반환·시그니처는 그대로 두고 `trader.last_krw_balance_ok` 표식으로 구분). 건너뜀 알림은 코드·거래별 1시간 dedupe.
  - 매수 쿨다운 — **결정 1028-03 (다)** (조건 「사용자에게 고지해야 하는 방안이 있어야 한다」, 질의 근거 `docs/fable/2026-10-28-phase2-t5-decision-1.md`): 봉 수 3 — 실패 봉 포함 3봉(#F~#F+2 재주문 안 함, #F+3 부터 재주문). 들어가는 것: trader 단계 주문 실패(업비트 거절·오류)와 trader strict 거절(잔고 부족 경쟁·잔고 조회 실패 — `trader.last_strict_reject_code`). 엔진 사전 검사 건너뜀(`split_below_min`·`split_krw_short`·`split_krw_unknown`)은 넣지 않는다. 해제: 봇 매도 체결(`_execute_sell` 의 `close_position(reason="bot_sell")` 뒤, PULLBACK 만)만. 앱 매도 지갑 0 동기화·회차 0 정리로는 풀지 않는다(3봉 뒤 저절로 끝남). 고지 방식(`_pullback_start_cooldown`): 쿨다운 시작 때 ① 텔레그램 WARNING 1회(제목 「새 전략 매수 잠시 쉼」, dedupe 키 `pullback_cooldown:{user}:{ticker}:{거래}:{실패 봉 시각}`, 본문: 실패 사유(코드·오류), 「새 매수를 3봉(약 N분 — 봉 간격×3) 쉽니다 — HH:MM 봉부터 다시 주문」, 「매도(익절·손절·데드크로스)는 계속합니다」, 할 일 「업비트 앱에서 원화 잔고와 미체결 주문 확인」) ② 감사 BUY_REJECTED 1행(`_audit_buy_blocked`, 코드 `split_order_cooldown`, note 에 쉬는 봉 수·끝나는 봉 번호와 KST 시각). 쿨다운 중 반복 매수 신호는 감사 행·알림을 쌓지 않고 로그만 남긴다. 쿨다운이 끝나거나 봇 매도로 풀릴 때 알림은 보내지 않는다(끝나는 시각은 감사 note 에 있음). trader 주문 전 거절 알림(직전 라운드의 `pullback_reject:`)은 이 고지로 합쳤다.
  - 검수 반영(10/28) 그 밖: catch-up 을 VERIFY 통과 뒤·`engine.on_new_bar_confirmed` 바로 앞(확정·재조회·잠정 3곳)으로 옮김(Issue #8 — VERIFY 실패 봉은 재생 안 함). `execute` 예외 시 주문이 안 나갔으면 `rollback_last_buy` + (이 판정에서 켠 경우) `set_pending(False)`(try/finally, 예외는 그대로 올림). 로그 태그 `[PULLBACK-STRATEGY]`, 적용본은 핵심 키만 INFO.
  - 넘김: T6 — 분할 상태 테이블·재시작 복원, `apply_split_entry`, LIVE 체결 수량 대조(F2), sizing_base 영속·복리, desync. T8 — 감사 열(지금은 `checks=last_eval` 최소 기록, macd/signal 칸에 maTrend/ma200 을 넣음 → 정리), 매도 거절 알림 문구(지금은 WO-9 기존 문구 「지정가 매도 주문이 있는지 확인」 유지 — 계획 시험 문구 「외부 미체결 매도 주문 확인」과 다름, EMA 문구를 건드리지 않으려 그대로), dedupe 키 정리. T11 — `start_engine` 거짓 반환·boot_resume 실패 판정·준비 이벤트, 기동 거부 시 감사 화면 기록, holding 판단(지금은 DB 캐시 추정 — locked 제외) → 지갑 동기화 뒤 판정. T11/T15 — URL `strategy_type` 세션 값을 `STRATEGY_TYPES` 로 거르기. T12 — 활성 파일 PULLBACK 쓰기·`apply_saved`. → **(10/28 T8 처리)** macd/signal 칸 비움(NULL)·지표는 checks 로, 새 전략 매도 거절 문구 「외부 미체결 매도 주문을 확인해 주세요」(EMA 문구 그대로), 쿨다운 알림은 봉 마감 시각, skip dedupe `pullback_skip:…`.
- [ ] **Step 5: 커밋 승인 요청**

### T6: 분할 포지션 — PositionState 누적·평단, 분할 상태 새 테이블 ⚠ 스키마 변경(배포 승인 대상)

**Files:**
- Modify ★ `core/position_state.py`(`apply_split_entry` 추가; `apply_entry` 223·`open_position` 273 무변경)
- Create ★ `services/pullback_state.py`
- Modify ★ `services/init_db.py`(`ensure_pullback_tables` 신설 → `ensure_all_schemas` 1003-1023 끝에 추가)
- Modify ★ `core/strategy_engine.py`(체결 반영·재시작 복원·지갑 대조)
- Test: `tests/regressions/test_r_2026_10_28_p3_t6_split_position.py`, `tests/regressions/test_r_2026_10_28_p3_t6_migration.py`

**새 테이블 `pullback_state`(초안):**
```
CREATE TABLE IF NOT EXISTS pullback_state (
    user_id            TEXT NOT NULL,
    mode               TEXT NOT NULL CHECK (mode IN ('TEST','LIVE')),
    ticker             TEXT NOT NULL,
    interval           TEXT NOT NULL,
    entry_count        INTEGER NOT NULL DEFAULT 0,   -- 회차
    pullback_count     INTEGER NOT NULL DEFAULT 0,   -- 눌림목 회차
    first_entry_ts     TEXT,                         -- 첫 체결 봉 시각, KST ISO
    first_entry_reason TEXT,                         -- GOLDEN|PULLBACK|FORCE|APP
    armed              INTEGER NOT NULL DEFAULT 0,
    prev_golden        INTEGER,                      -- 0/1/NULL
    sizing_base_krw    REAL,                         -- 이 거래 배분 기준(1회차 때 고정, D10)
    realized_pnl_krw   REAL NOT NULL DEFAULT 0,      -- 전환 뒤 실현 손익 합(복리)
    qty                REAL NOT NULL DEFAULT 0,
    cost_krw           REAL NOT NULL DEFAULT 0,
    avg_price          REAL,
    desync             INTEGER NOT NULL DEFAULT 0,   -- [PULLBACK-SYNC] 어긋남
    params_sha256      TEXT,                         -- 적용본 해시
    last_bar_ts        TEXT,                         -- 마지막 판정 봉, KST ISO
    updated_at         TEXT NOT NULL,                -- KST ISO
    PRIMARY KEY (user_id, mode)
);
```
- 모드 칸은 T17(D4).
- 쓰기는 `services/pullback_state.save(conn, state)` 한 곳. 봉 판정 끝·체결 반영·청산 때 한 트랜잭션.

**Interfaces:**
- `PositionState.apply_split_entry(qty, price, ts, source) -> None` — 수량·원가 누적, `avg = cost/qty`. PULLBACK 만 부른다.
- `services/pullback_state.load(user_id, mode) -> dict | None`, `save(user_id, mode, state)`, `reset_after_exit(user_id, mode, realized_pnl)`(회차·눌림목 회차·첫 진입·armed 초기화, `realized_pnl_krw` 누적, pullback spec 3절 5).
- 재시작·기동 재개(WO-12) 복원: 엔진 기동 → 워밍업으로 지표 재생 → DB 상태가 있고 `last_bar_ts` 가 워밍업 범위 안이면 그 시점의 판정 상태(회차·armed·첫 진입)를 DB 값으로 두고 그 뒤 봉을 주문 없이 이어 재생. 미보유이고 DB 상태가 없으면 워밍업 재생의 가상 회차는 넘기지 않는다(pullback spec 4.3).
- 지갑 대조(WO-22): 봉마다 `_reconcile_position_with_wallet`(615) 결과와 DB `qty` 를 비교. 차이가 최소 단위(0.1%) 넘으면 지갑 우선, `desync=1`, `[PULLBACK-SYNC] wallet=… state=… class=…` WARNING + 감사 1행. `desync=1` 이면 추가 분할매수 멈춤, TP/SL/DC 는 지갑 평단으로 계속(D11 b). 지갑 0 이 되면(앱 매도·청산) `reset_after_exit` 로 정상 상태.
- **체결 반영(F2):** LIVE 시장가 매수는 `orders` 에 추정 수량만 남기고(`core/trader.py:594-595,819-833`) 실제 체결은 reconciler 가 반영한다. PULLBACK 은 분할 주문 uuid 를 엔진의 새 칸 `_pending_split_uuid`(+ 회차·회당 금액)에 둔다. `register_pending_buy_uuid`(`core/strategy_engine.py:33`)는 쓰지 않는다 — 그 경로는 `_on_limit_fill` 이 `apply_entry`(이번 회차 값만)로 누적을 덮어쓴다(`core/strategy_engine.py:419-450`).
  - reconciler(`engine/order_reconciler.py:316-324`)는 지금 **BUY `FILLED` 전부**(주문 종류를 보지 않음 — `:318`)에서 콜백을 부르고, 콜백에는 상태를 넘기지 않는다(`_fire_fill_callback` `:147-170`). 바꿀 것: (1) `_fire_fill_callback(…, state=db_state)` 로 상태 인자를 더하고 콜백 서명도 `state: str = "FILLED"` 를 받는다 (2) 「BUY·`exec_volume > 0`·`db_state == "CANCELED"`(시장가는 cancel 로 오기도 함, `:502-503`)」 경로를 더해 `state="CANCELED"` 로 부른다.
  - 엔진 `_on_limit_fill` 은 `_execution_lock` 안에서 uuid 가 `_pending_split_uuid` 와 같으면(`FILLED`·`CANCELED` 둘 다) `apply_split_entry(executed_qty, executed_price, …)`(체결 실수량·평단)로 분할 상태를 고치고 `pullback_state` 를 저장한다. 다르면 **`state == "FILLED"` 일 때만** 지금 경로(`_pending_buy_uuid` 일치 → `apply_entry`). 그래서 EMA 지정가 부분 체결 뒤 `CANCELED` 가 와도 `apply_entry` 로 가지 않는다(D6 부분 체결 미처리 규칙 무변경).
  - **TEST 모드(2회째 9):** reconciler 가 없다. `buy_market` 이 TEST 에서 바로 체결 결과(`qty`·`price`)를 돌려주므로(`core/trader.py:597-640`) `_execute_pullback_buy` 가 그 값으로 바로 `apply_split_entry` 를 부른다. `_pending_split_uuid` 는 LIVE 에서만 둔다.
  - 체결 대기 중인 회차가 있으면 지갑 대조(아래)는 그 회차를 「대기」로 보고 `desync` 판정을 하지 않는다. 체결 대기가 3봉을 넘으면 WARNING `[PULLBACK-SYNC] fill pending` 후 지갑 기준으로 맞춘다.
- **봇 추가매수 오인 방지(F1):** 앱 매수 판정은 `has_recent_bot_buy_for_ticker(user, ticker, within_seconds=30)`(`engine/order_reconciler.py:776`, `services/db.py:773-800` — pending 지정가 또는 30초 안 `audit_trades` BUY)이 막는다. 분할 체결도 `audit_trades` BUY 행을 남기므로(reconciler 508) 30초 창 안에서 HTS 로 보지 않는다. 이 동작을 시험으로 고정한다. 실제 지갑 수량과 엔진 포지션을 맞추는 장치는 체결 확정 때의 포지션 갱신(`update_position_from_balances`, `engine/order_reconciler.py:535`)이다 — 이것도 시험에 함께 고정한다. 30초를 넘겨 늦게 보이는 지갑 증가는 `_pending_split_uuid` 가 남아 있으면 HTS 로 보지 않게 엔진 쪽 대조에서 한 번 더 거른다.
- **hts_buy(Issue #17, R2):** EMA 는 데드 상태 HTS 매수분에 STOP_LOSS 를 건너뛴다(`core/strategy_incremental.py:1245-1250`). PULLBACK 은 D11(b)(앱 매수분도 TP/SL·데드크로스 적용)를 따르므로 이 예외를 쓰지 않는다. `hts_buy` 플래그는 기록·화면 표시(「앱 주문이 섞임」)용으로만 남는다. EMA 쪽 예외는 바꾸지 않는다.

- [ ] **Step 1: 실패 시험**
  - `test_split_avg_recalc`: 600,000원 @1,000 → 600,000원 @950 → 평단 974.36…(원가/수량), 회차 2.
  - `test_apply_entry_unchanged`: 기존 `apply_entry`·`open_position` 결과 동일(EMA 회귀).
  - `test_state_survives_restart`: 2회차·armed=1 저장 → 새 엔진 객체로 복원 → 같은 값.
  - `test_boot_resume_restores_split_state`: WO-12 경로(`boot_resume_all` 가짜 start)로 복원.
  - `test_pullback_hts_buy_sync`: 지갑 수량이 상태보다 큼(앱 매수) → `desync=1`, 다음 눌림 신호 주문 0, TP 봉에서 매도 1.
  - `test_bot_split_buy_not_hts_30s`: 분할 체결 BUY 행 기록 뒤 30초 안 지갑 증가 → HTS_BUY_ADD 행 0, `desync=0`. 31초 뒤 같은 증가 + `_pending_split_uuid` 없음 → HTS_BUY_ADD 1(지금 동작 고정).
  - `test_split_fill_uses_executed_qty_avg`: 추정 수량 600,000/1,000 → 체결 콜백 실수량 598.8·평단 1,002 → 상태 qty·avg 가 체결값, 회차 1.
  - `test_split_fill_market_cancel_state`: 시장가 `CANCELED`+체결량 > 0 → 콜백 1회, 분할 반영.
  - `test_desync_ignores_pending_fill`: 체결 대기 회차가 있을 때 지갑 < 상태 → `desync=0`.
  - `test_limit_fill_callback_unchanged_for_ema`: EMA 지정가 `FILLED` → `apply_entry` 1회(지금과 같음). `_pending_buy_uuid` 와 같은 uuid 의 부분 체결 뒤 `CANCELED`(state 인자 `"CANCELED"`) → `apply_entry` 0.
  - `test_position_updated_on_fill_finalize`: 체결 확정 → `update_position_from_balances` 1회, `account_positions` 수량 = 지갑.
  - `test_split_fill_test_mode_direct`: TEST 분할 매수 → reconciler 없이 `apply_split_entry` 1회, 회차 1.
  - `test_pullback_hts_buy_stop_loss_applies`: PULLBACK 데드 상태 앱 매수 → SL 봉에서 매도 1(EMA 의 Issue #17 예외 미적용). EMA 같은 경우는 지금처럼 SL 건너뜀(회귀).
  - `test_app_sell_resets_state`: 지갑 0 → 상태 초기화, HTS_SELL 1행.
  - 마이그레이션(`test_r_..._t6_migration`): 새 DB·기존 DB(테이블 없음) 모두 `ensure_all_schemas` 2회 → 테이블 1개·오류 0, 기존 테이블 행 수 불변, `PRAGMA integrity_check == ok`.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
  - **(10/28 구현 반영 — T6)** 위치: `core/position_state.py` `apply_split_entry(qty, price, ts, source, *, base_qty=None, base_cost=None, entry_bar=None)`(기준 수량 0 이면 `apply_entry` 로 첫 진입, 아니면 기준+이번 체결 누적; `apply_entry`·`open_position`·`close_position`·`sync_from_wallet` 무변경 — 시험이 `0b04570` 원문과 비교). `services/pullback_state.py` `load`·`save`(UPSERT 한 문장)·`reset_after_exit`(회차·눌림목·첫 진입·armed·거래 칸·수량·원가·평단·desync·배분 기준 초기화, `realized_pnl_krw` 누적, `prev_golden`·`last_bar_ts` 유지)·`to_kst_iso`(naive 거부). DB 파일이 없으면 만들지 않고, 테이블이 없으면 읽기 None·쓰기 False(로그). `services/init_db.py` `ensure_pullback_tables` → `ensure_all_schemas` 마지막 줄. `core/strategy_engine.py` — `_on_limit_fill(..., state="FILLED")`(uuid 가 `_pending_split` 이면 FILLED·CANCELED 모두 `_pullback_apply_fill`, 아니면 `state != "FILLED"` 는 무시 후 지금 경로), `_on_hts_detect` 맨 앞 PULLBACK 가드(체결 대기 중 늦은 지갑 증가 무시), PULLBACK 봉 경로에 `_pullback_wallet_check`(지갑 0 → 초기화, 0.1% 넘게 차이 → 지갑 우선·desync·`[PULLBACK-SYNC] wallet=… state=… class=wallet_more|wallet_less` WARNING·감사 `PULLBACK_SYNC` 1행(바뀔 때 1회), 체결 대기 3봉 초과 → `[PULLBACK-SYNC] fill pending` 후 지갑 기준)·판정 끝 `_pullback_persist`, `_execute_pullback_buy`(TEST: 결과 qty 로 바로 `apply_split_entry` / LIVE: qty 0 + uuid → `_pending_split` 에 회차·회당 금액·주문 전 기준 수량·원가 저장, 포지션은 체결 콜백이 고침)·잔고는 `trader.krw_balance_checked()`·실패 봉 시각 저장, `_pullback_read_sizing_base`(복리 `compounding=true` 면 `virtual_krw + realized_pnl_krw`), `_execute_sell` PULLBACK 블록(실현 손익 = 매도 수량×가격×(1−수수료) − 원가×(1+수수료) → `_pullback_on_exit`), `pullback_restore_on_boot(series, validator)`. `core/strategy_pullback.py` `fill_wait`(체결 대기 중 미보유여도 ① 정리 미룸)·`split_desync`(보유 중 ⑥ POS_DESYNC 로 추가 매수 멈춤)·`cfg["compounding"]`·`SPLIT_TRADE_KEYS`. `core/trader.py` `last_krw_balance_ok` 를 스레드별 property 로, `krw_balance_checked()` 신설, `buy_market` 은 `strict_amount=True` 일 때만 그것을 씀(EMA·MACD 경로는 지금 코드 그대로). `engine/order_reconciler.py` `_fire_fill_callback(..., state=)`·BUY 체결량 > 0 인 CANCELED 도 `state="CANCELED"` 로 발화. `engine/live_loop.py` 워밍업·지갑 복원 뒤 PULLBACK 만 `_pullback_restore_split_state`(적용본 sha 기록 → `pullback_restore_on_boot`, 예외는 ERROR+CRITICAL, 기동은 계속), `_pullback_backfill_step` 은 미보유여도 `trade_origin=live`·회차>0 이면 거래 칸 유지. 시험 45건(split 38 · migration 7) — 수정 1회차 뒤 53건, 2회차 뒤 54건. 구현 전 실패 수: verifier 재현(HEAD 사본 + 시험 45건) failures 10 · errors 27 · 통과 8(그중 3건은 services namespace 혼입) — 실행자 보고 19/21/5 는 고치기 전 원본이 없어 미확인.
  - 스키마(초안 대비 더한 칸): `trade_origin TEXT`, `pending_fill INTEGER`, `fill_n INTEGER`, `inv_sum REAL`(T4 판정 상태 재생에 필요), `buy_fail_bar_ts TEXT`(쿨다운 재시작 유지). 인덱스는 PK(user_id, mode) 만. 기존 테이블·칸은 바꾸지 않는다.
  - 수정 1회차(검수 반영): `_on_limit_fill` 은 PULLBACK 엔진이면 `_execution_lock` 을 먼저 잡고 그 안에서 `_pending_split`·uuid 판정·반영(콜백이 등록 전에 와도 락을 기다렸다가 반영 — 경합 시험 1건). EMA·MACD 는 락 없이 지금 경로. 호출처 없던 `_pullback_accumulate` 삭제. `pullback_state.load` 는 행·테이블·DB 파일 없음 = None, 읽기 오류 = `PullbackStateReadError`. 복원에서 읽기 오류(`read_error`)·다른 종목/봉 단위(`other_market`)면 이 엔진 수명 동안 `_pullback_persist`·청산 초기화를 막고(`_pullback_persist_blocked`) CRITICAL `[PULLBACK-STATE] 저장 막음` 1줄 — 저장 행은 그대로 둔다. 저장 실패는 CRITICAL `[PULLBACK-STATE] 분할 상태 저장 실패` 1회 + 알림. 체결 반영 INFO 는 엔진 `[SPLIT-FILL] applied`, reconciler 의 CANCELED 발화 로그는 DEBUG(FILLED 발화 INFO 문구는 T6 전과 같음). DRY_RUN uuid 는 체결 대기로 두지 않고 회당 금액/가격 추정 수량으로 바로 반영(다음 봉 지갑 0 처리는 EMA dry-run 과 같은 공용 대조). 시험 53건(split 46 · migration 7). 수정 2회차: `engine/live_loop.py` `_pullback_restore_split_state` 의 복원 예외 경로에서도 `_pullback_block_persist("restore_exception")`(호출 자체도 try) — 시험 54건(split 47 · migration 7).
  - 서버 적용 절차(배포 승인 대상): ⓪ 배포 전 읽기 전용 확인: `which sqlite3`(백업 도구 있음), DB 경로·크기, `ls -l services/data/backups/` ① 배포 전 서버 DB 백업 — 기존 관례 `services/data/backups/`(`docs/operations/server-optimization.md` 정리 스크립트: `BACKUP_DIR=…/services/data/backups`, 7일 지난 백업 삭제)에 `sqlite3 <db> ".backup services/data/backups/tradebot_<user>.db.pre-t6_YYYYMMDD_HHMMSS"`, 백업 파일 권한 600 ② 배포 후 tradebot 재시작 때 `ensure_all_schemas`(boot_resume 기동 마이그레이션)가 `CREATE TABLE IF NOT EXISTS` 로 자동 생성 — 별도 SQL 실행 없음, 두 번 돌려도 안전 ③ 확인: `[migrate] ensure_pullback_tables OK` 로그·`PRAGMA table_info(pullback_state)` 24칸 ④ 되돌림: 코드만 되돌려도 남은 테이블은 아무도 읽지 않아 무해. 지우려면 `DROP TABLE pullback_state`(선택, 백업 뒤).
  - LIVE 거부 해제 조건 상태: 체결 반영(F2)·재시작 복원·지갑 대조는 구현·단위 시험 통과. 거부 문구 `PULLBACK_LIVE_REFUSE_MSG` 와 거부는 **그대로 둠**. 남은 조건: 업비트 실제 응답(시장가 cancel+체결량, 체결 지연 3봉 가정) 실측 없음 — 해제는 사용자 결정(T10 일치 시험·T17 TEST/LIVE 분리 뒤 권함).
  - LIVE 거부 해제 전 조건(수정 1회차 — 아래가 모두 끝나야 해제 검토):
    1. 실현 손익을 체결가로 계산 — 지금은 `sell_market` 반환 가격(LIVE 는 추정가일 수 있음)으로 `realized_pnl_krw` 를 쌓는다. 매도 체결 확정(reconciler) 값으로 바로잡기.
    2. 체결 대기 uuid 재시작 영속 — `_pending_split`(uuid·주문 전 기준 수량·원가)은 메모리에만 있고 저장하지 않는다(복원 때 `pending_fill` 은 False 로 둔다). 체결 대기 중 재시작하면 그 회차 체결이 지갑 대조로만 들어간다.
    3. 체결 대기 시간 초과 때 평단 없음 — 3봉 초과 시 업비트 평단(`_fetch_upbit_avg_buy_price`)을 못 읽으면 수량만 지갑으로 맞고 원가는 그대로라 수량·원가가 어긋난다.
    4. desync 해제 경로 — 지금은 청산(봇 매도·지갑 0)으로만 풀린다. 지갑이 다시 상태와 맞거나 운영자가 확인했을 때 푸는 경로가 없다.
    5. busy_timeout 맞춤 — `pullback_state._connect` 는 `timeout=30` 과 `PRAGMA busy_timeout=3000`(3초)이 섞여 있다. `services/db.py` 관례와 한 값으로 맞추기.
    6. `init_db_if_needed` 잠금 실패 화면 오류 — 기록만(이번 범위 밖, 화면 쪽에서 DB 잠금 시 오류가 보이는 경로 확인 필요).
    7. reconciler 단일 스레드 지연 — PULLBACK 체결 콜백은 `_execution_lock` 을 기다리는 동안 reconciler 스레드를 붙잡아 다른 사용자(EMA LIVE)의 주문 폴링·잔고 동기화가 늦어진다(교착 아님). 락 대기 시간 제한 또는 콜백을 큐에 넣고 엔진 스레드가 처리. (재검증 지적 1)
    8. 저장 막음 중 비영속·고지 — 막음(read_error·other_market·restore_exception) 동안 실현 손익 누적·쿨다운 실패 봉 시각은 메모리에만 있고, read_error 면 `realized_pnl_krw` 를 0 에서 시작해 복리 배분 기준이 작다. 막음 시작 때 텔레그램 CRITICAL 1회는 T8 알림 문구 작업에서 넣는다(지금은 CRITICAL 로그만). (재검증 지적 2) → **(10/28 T8 처리)** 막음 시작 때 텔레그램 CRITICAL 「새 전략 기록 저장 멈춤」 1회(`_pullback_block_persist`, dedupe `pullback_persist_block:{user}:{ticker}`).
    9. 경합 시험 결정화 — `test_fill_callback_before_pending_set_waits_lock` 의 0.2초 sleep 을 `threading.Event` 로(재검증 지적 3, 가짜 양성 쪽).
    10. (10/28 T10 수정 1회차 추가) pending_fill(체결 대기) 사이 재시작 시험 — T10 재시작 시험은 신호 없는 봉에서만 재시작한다. 신호 봉과 체결 봉 사이(LIVE 체결 대기 중)에서 재시작해도 회차·평단이 맞는지 시험한다(조건 2 와 같은 축).
  - 넘김: T7 — 거래 행 전략 칸(`PULLBACK_SYNC` 감사 행 포함). T8 — 감사 화면 라벨(`PULLBACK_SYNC`·`[POSITION-SPLIT]`·체결 행 회차·평단), 동기화 알림 문구. T11 — 준비 이벤트·holding 판정(복원 결과 `engine.pullback_restore_result` 활용). T12 — 전환 때 `realized_pnl_krw` 초기화·종목/봉 단위가 다른 저장 행 정리(지금은 `other_market` 이면 그 행을 쓰지도 덮어쓰지도 않고 이 엔진 수명 동안 저장을 막음 — 새 종목의 회차는 재시작하면 잃는다)·`strategy_switch`. T17 — 모드 칸은 이미 PK 에 있음(TEST/LIVE 행 분리 시험 1건). → **(10/28 T8 처리)** `PULLBACK_SYNC` 표시 「🔄 새 전략 수량 맞춤」, 체결 행 회차·평단(TEST·LIVE), 동기화 알림 「새 전략 보유 수량 맞춤」(WARNING, 종류마다 1회). `[POSITION-SPLIT]` 은 로그 전용 — 화면 라벨 불필요.
- [ ] **Step 5: 커밋 승인 요청** — 보고에 「⚠ 스키마 변경: `pullback_state` 신설」.

### T7: 설정 이력 — 거래 행 전략 칸 (결정 D2) ⚠ 스키마 변경(배포 승인 대상)

**Files:**
- Modify ★ `services/init_db.py`(`ensure_trade_strategy_columns` 신설 → `ensure_all_schemas` 끝)
- Modify ★ `services/db.py`(`insert_order` 109-170, `insert_trade_audit` 1474-1520: `strategy_type` 인자)
- Modify ★ `core/trader.py`(`insert_order` 호출 610·797·821·1123·1151·1270·1404, `_audit_trade` 366-447, `_audit_reject` 449, `_audit_preorder_reject` 514: `strategy_type=self.strategy_type`)
- Modify ★ `engine/order_reconciler.py`(`insert_trade_audit` 403·508·799: 주문 행 `orders.strategy_type` 을 그대로, HTS 감지 799 는 엔진 활성 전략)
- Modify ★ `core/strategy_engine.py`(`_record_external_sell` 596-613 HTS_SELL: 엔진 전략)
- Modify ★ `pages/dashboard.py`(강제 매수 2400-2402·강제 매도 2429-2431 의 `UpbitTrader(…, strategy_type=…)` — X5)
- Modify ★ `services/settings_history.py`(`fetch_trades_for_snapshot` 601-634, `compute_pnl_for_snapshot` 637 의 orders 조회)
- Modify `pages/audit_viewer.py`(분류 불명 경고)
- Test: `tests/regressions/test_r_2026_10_28_p3_t7_trade_strategy.py`

**마이그레이션(초안):**
```
-- schema_marks (X1 — 결정 13-1 에 따름): 한 번만 기록
CREATE TABLE IF NOT EXISTS schema_marks (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL,
    at    TEXT NOT NULL        -- KST ISO
);
BEGIN IMMEDIATE;
INSERT OR IGNORE INTO schema_marks(name, value, at)
    SELECT 'audit_trades.strategy_type.legacy_max_id', COALESCE(MAX(id),0), ? FROM audit_trades;
INSERT OR IGNORE INTO schema_marks(name, value, at)
    SELECT 'orders.strategy_type.legacy_max_id', COALESCE(MAX(id),0), ? FROM orders;
ALTER TABLE audit_trades ADD COLUMN strategy_type TEXT;   -- 이미 있으면 건너뜀(_ensure_column)
ALTER TABLE orders ADD COLUMN strategy_type TEXT;
COMMIT;
```
- **먼저 읽기(D1):** 함수는 쓰기 전에 `PRAGMA table_info(audit_trades)`·`PRAGMA table_info(orders)`·`SELECT name FROM schema_marks`(테이블이 있으면)로 상태를 본다. 칸 2개·표식 2개가 다 있으면 쓰기 없이 바로 끝낸다(`BEGIN IMMEDIATE` 도 열지 않음). 로그인·대시보드가 매번 부르므로(`app.py:281`, `pages/dashboard.py:723-724`) 엔진 쓰기와 잠금 경쟁을 만들지 않기 위해서다.
- 표식과 칸 추가는 위 트랜잭션 하나에 둔다(SQLite 의 `ALTER TABLE ADD COLUMN` 은 트랜잭션 안에서 함께 되돌려짐).
- **칸은 있고 표식이 없음(D3 — 정의):** 표식 = `COALESCE((SELECT MIN(id) FROM <표> WHERE strategy_type IS NOT NULL) - 1, (SELECT MAX(id) FROM <표>))`. 곧 「전략이 처음 기록된 행 바로 앞까지」를 옛 행으로 본다. WARNING `[migrate] strategy mark repaired`. 시험 `test_mark_repair_definition`.
- **되돌린 뒤 재배포(D2):** 되돌리기(배포 절 7 ③) 동안 옛 코드가 쓴 행은 `strategy_type` NULL 이고 id 는 표식보다 크다 → 재배포 뒤 「분류 불명」이 된다. 그래서 되돌리기 ③ 절차에 「되돌리기 직전 테이블별 MAX(id) 를 `schema_marks` 에 `…revert_from` 로 기록」을, 재배포 마이그레이션에 「`revert_from` 이 있고 `revert_to` 가 없으면 그때 MAX(id) 를 `revert_to` 로 기록하고, 그 구간(`revert_from` < id ≤ `revert_to`)의 NULL 행은 옛 EMA/MACD 로 분류」를 넣는다. 구간 기록은 운영자 명령 `python3 scripts/v2/mark_revert.py <user>`(파일로 작성)로 한다. 시험 `test_redeploy_after_revert_marks_gap`. **(수정 1회차)** `revert_to` 기록은 엔진 기동 마이그레이션(`engine/boot_resume.py` → `close_strategy_revert_gap`)에서만 한다. 로그인·대시보드(`init_db_if_needed` → `ensure_all_schemas` → `ensure_trade_strategy_columns`)는 칸·표식만 다루고 구간을 닫지 않는다 — 되돌리기 직전 화면 렌더가 구간을 먼저 닫아 옛 코드 행이 분류 불명이 되던 결함. 되돌리기 순서는 「tradebot 정지 → 백업 → `mark_revert.py` → `git revert` → tradebot 시작」(배포 절 7 ③). 시험 `test_render_after_mark_revert_does_not_close_gap`·`test_rv_sequence_render_during_revert_then_redeploy_no_unknown`.
- 인덱스는 더하지 않는다(조회는 기존 `idx_audit_trades_settings_history_id`·시각 인덱스 + 작은 범위).
- 마이그레이션은 서버에서 엔진 기동 때 먼저 돈다(`engine/boot_resume.py:126-135`). 로그인·대시보드 경로도 같은 함수라 두 번 돌아도 무해해야 한다.

**분류 규칙(NULL 해석은 마이그레이션 전 행으로만):**

| strategy_type | id ≤ 표식 | 분류 | 구버전 이력·손익 | 감사 뷰어 |
|---|---|---|---|---|
| `EMA`·`MACD` | — | 그 전략 | 보임 | 보임 |
| `PULLBACK` | — | 새 전략 | 뺌 | 보임(「새 전략」) |
| NULL | 예 | 옛 EMA/MACD | 보임(지금과 같음) | 보임 |
| NULL | 아니오, 단 되돌림 구간(`revert_from` < id ≤ `revert_to`) 안 | 옛 EMA/MACD | 보임 | 보임 |
| NULL | 아니오 | 분류 불명 | 뺌 | 보임(화면 경고 없음 — 결정 1028-06: 엔진 기동 때 운영 로그 WARNING `[STRATEGY-UNKNOWN]`·텔레그램 WARNING 1회) |

**기록 경로 전부(배포 뒤 체결 행을 쓰는 곳):**
- 발주 때 `orders.strategy_type` = trader 의 `strategy_type`. 엔진 trader 는 `engine/engine_manager.py:418-421` 에서 이미 전략을 받는다.
- reconciler 체결 감사(508)·미체결 취소(403)는 그 주문 행의 `strategy_type` 을 그대로 옮긴다(전환 뒤 늦은 체결도 발주 때 전략).
- HTS 감지(799)·HTS_SELL(`core/strategy_engine.py:605`)은 그때 엔진 활성 전략.
- 구버전 강제 매수(`force_buy_in` → trader)·강제 매도(`force_liquidate` → trader)는 대시보드가 넘긴 `strategy_type`(PULLBACK 운용 중이면 PULLBACK).
- PULLBACK 은 `settings_history_id` 를 쓰지 않는다(`get_active_settings_id` 가 None — `services/settings_history.py:252-260`). PULLBACK 설정 기록은 v2hist(적용 결과를 신버전이 v2hist `applied_at` 에 기록 — T13).

**구버전 이력 조회 변경:** `fetch_trades_for_snapshot` 의 WHERE 에 `AND (strategy_type IN ('EMA','MACD') OR (strategy_type IS NULL AND (id <= :mark OR (:rv_from IS NOT NULL AND id > :rv_from AND id <= :rv_to))))` 를 더한다. `:rv_from`·`:rv_to` 는 `schema_marks` 의 되돌림 구간(없으면 NULL — 구간 조건이 거짓이 됨, 2회째 8). 구간은 1개만 지원한다. 두 번째 되돌림 때는 `mark_revert.py` 가 먼저 이전 구간을 확인하고, **표식 뒤 ~ `revert_from` 사이에 NULL 행(분류 불명)이 없으면** 표식을 `revert_to` 로 올려 합친다(수정 1회차 — 「첫 PULLBACK 행보다 앞섬」 조건 삭제: 전략 칸이 있는 행은 표식과 무관하게 분류가 그대로이므로, 표식을 올려 분류가 바뀌는 행은 그 사이 NULL 행뿐). 합칠 수 없으면 쓰기 없이 종료 코드 4 — 운영자 판단 절차는 T7 메모 「서버 적용 절차 ④」. `compute_pnl_for_snapshot` 의 orders 조회도 같은 조건(orders 표식).

- [ ] **Step 1: 실패 시험**
  - `test_migration_marks_and_columns`: 기존 행 5개 DB → 표식 5, 칸 추가, 기존 행 값 불변, 2회 실행 무변경, `integrity_check ok`.
  - `test_old_history_excludes_pullback_rows`: PULLBACK 운용 중 LIVE 체결(reconciler 경로)·앱 매도(HTS_SELL)·구버전 강제 매도 행 → `fetch_trades_for_snapshot`·`compute_pnl_for_snapshot` 에 0건.
  - `test_ema_rows_tagged_all_paths`(반대 방향): 배포 뒤 EMA 운용 중 trader 시장가·지정가·거절·주문 전 차단·reconciler 체결·미체결 취소·HTS 매수·HTS_SELL·구버전 강제 매수·매도 → 모든 행 `strategy_type='EMA'`, 구버전 이력에 보임.
  - `test_late_fill_keeps_order_strategy`: EMA 로 발주 → 전환 → 체결 기록 → `EMA`.
  - `test_null_after_mark_is_unknown`: 표식 뒤 NULL 행 → 구버전 이력 0, 분류 불명 수 1(결정 1028-06 뒤 화면 경고 대신 `test_unknown_rows_logged_and_notified_once`).
  - `test_migration_no_write_when_done`: 다 된 DB 에서 함수 호출 → `total_changes` 0, `BEGIN IMMEDIATE` 0(연결 trace).
  - `test_mark_repair_definition`, `test_redeploy_after_revert_marks_gap`(되돌림 구간 NULL 행 3개 → 재배포 뒤 구버전 이력에 3개 보임, 구간 밖 표식 뒤 NULL 은 분류 불명).
  - `test_a18_history_same_before_after`(A18): 기존 행만 있는 DB 의 이력 화면 결과(스냅샷 목록·거래·손익)가 마이그레이션 전후·PULLBACK 거래 추가 전후로 같음.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
  - **(10/28 구현 반영 — T7)** 위치: `services/init_db.py` `STRATEGY_MARK_TABLES`·`strategy_mark_name(table, kind)`(kind = `legacy_max_id`|`revert_from`|`revert_to`, 이름 예 `audit_trades.strategy_type.legacy_max_id`)·`_trade_strategy_work(conn, *, close_revert_gap=False)`(읽기만 — 할 일 목록)·`ensure_trade_strategy_columns`(할 일 없으면 쓰기·BEGIN 없이 끝, 있으면 `BEGIN IMMEDIATE` → 다시 읽기(할 일이 없어졌으면 COMMIT 만) → `schema_marks` 생성·표식·`ALTER TABLE … ADD COLUMN strategy_type TEXT`·D3 복구(WARNING `[migrate] strategy mark repaired`) → COMMIT, 성공 첫 회 `[migrate] ensure_trade_strategy_columns OK`) → `ensure_all_schemas` 마지막 줄. 수정 1회차: `close_strategy_revert_gap`(같은 일 + D2 `revert_to`, WARNING `[migrate] strategy revert gap closed`) — `engine/boot_resume.py` 기동 마이그레이션에서 `ensure_all_schemas` 다음에만 부른다. `services/db.py` `insert_order(…, strategy_type=None)`·`insert_trade_audit(…, strategy_type=None)` → 공용 `_insert_with_strategy`(값이 있을 때만 칸을 더함, 대문자·공백 정리), `fetch_order_strategy_type(user_id, provider_uuid)`. 새 파일 `services/trade_strategy.py`(읽기 전용: `read_bounds`·`old_history_sql`·`classify`·`count_unknown_rows`·`unknown_warning_text`·`active_strategy`·`force_trade_strategy_type`). `core/trader.py` `insert_order` 7곳·`_audit_trade`·`_audit_reject`(주문 전 차단 `_audit_preorder_reject` 는 이것을 거침)에 `strategy_type=self.strategy_type`. `engine/order_reconciler.py` `_order_strategy_type`(체결 감사·미체결 취소 = 주문 행 전략)·`_engine_strategy_type`(HTS 감지 = HTS 콜백 주인 엔진의 `strategy_type`, 엔진 없으면 활성 전략 파일). `core/strategy_engine.py` HTS_SELL = 엔진 전략, PULLBACK_SYNC = `PULLBACK`. `pages/dashboard.py` 강제 매수·매도 `UpbitTrader(…, strategy_type=force_trade_strategy_type(user_id, params_obj.strategy_type))`(버전 줄 무변경). `services/settings_history.py` `fetch_trades_for_snapshot`·`compute_pnl_for_snapshot` orders 조회에 `old_history_sql(read_bounds(conn, 표))`. `pages/audit_viewer.py` — 처음 넣은 체결 절 경고는 수정 2회차(결정 1028-06)에 뺐다. 지금 `pages/audit_viewer.py` 는 T7 전 원문과 같다(`git diff` 비어 있음). 새 파일 `scripts/v2/mark_revert.py`. 시험 `tests/regressions/test_r_2026_10_28_p3_t7_trade_strategy.py` 24건(구현 전 실패 3·오류 21 → 구현 뒤 24 OK), T6 마이그레이션 시험 1건 수정(마지막 줄 단정 → 마지막 두 줄).
  - 계획과 다른 점: ① `ensure_trade_strategy_columns` 는 실패해도 예외를 올리지 않는다(ERROR `[migrate] ensure_trade_strategy_columns 실패 — 기동 계속`, False) — 다른 `ensure_*` 와 달리 로그인(`app.py:281`)·대시보드(`pages/dashboard.py:724`)가 깨지지 않게. ② `schema_marks` 생성을 초안의 BEGIN 앞이 아니라 트랜잭션 안에 둠(다 된 DB 에서 CREATE 문장도 0). ③ 칸이 없는 DB(마이그레이션 실패)에서 전략을 넘기면 WARNING `[STRATEGY-COL] … 칸 없음` 1회(표·프로세스당) 뒤 칸 없이 다시 넣음 — EMA 실매매 기록은 멈추지 않음. 표식이 없으면 읽을 때 D3 정의로 계산만 함(쓰기 없음, WARNING). ④ HTS 감지의 「엔진 활성 전략」= 그 종목 엔진(HTS 콜백 주인)의 `strategy_type`, 엔진이 없으면 활성 전략 파일. ⑤ 강제 매매 전략 = 활성 전략 파일이 PULLBACK 이면 PULLBACK, 아니면 화면 전략. 부수 효과: 강제 매매 trader 에 전략이 생겨 그 행의 `settings_history_id` 도 채워짐(전에는 NULL → 시각 범위로 같은 스냅샷에 묶였음, X5 「이력 id 늘 비어 있음」 해소). ⑥ 주문 행 전략이 NULL 인 늦은 체결(배포 전 발주·배포 뒤 체결)은 감사 행도 NULL → 분류 불명(WARNING `[OR] 주문 전략 없음`). 배포 절 3 「미체결 0」 조건이 막는다. ⑦ `mark_revert.py` 두 번째 되돌림 합치기 조건 = 「표식 뒤 ~ revert_from 사이 NULL 행 0」 하나(수정 1회차에 「첫 PULLBACK 행보다 앞섬」 조건을 뺐고 계획 본문도 고침). 종료 코드 0 기록·2 DB 없음/마이그레이션 전·3 revert_from 만 있음(재배포 기록 없음)·4 합칠 수 없음·1 오류, 2~4 는 쓰기 0. ⑧ 감사 뷰어 PULLBACK 행 「새 전략」 표시는 하지 않음(T8 감사 화면 라벨로 넘김). ⑩ **분류 불명 경고는 화면 대신 운영 로그·텔레그램(사용자 결정 1028-06)** — `services/trade_strategy.report_unknown_rows` 를 `engine/boot_resume.py` 에서 **전체 재개(start) 뒤**(재개 대상이 없으면 대상 판정 뒤) 사용자마다 try 로 1회: n>0 이면 WARNING `[STRATEGY-UNKNOWN] user=… audit_trades=n orders=m`(표 이름·사용자 ID 는 로그에만) + `notifier.send(LEVEL_WARNING, "거래 기록 전략 구분 확인 필요", "거래 기록 N건의 전략 구분이 비어 옛 화면 이력·손익에서 빠졌습니다. 운영자가 확인합니다. 투자자님이 따로 하실 일은 없습니다.", dedupe_key="strategy_unknown:<user>", dedupe_ttl=86400)`. 화면 경고·`unknown_warning_text` 는 지움. ⑨ 8절 `test_revert_old_code_ignores_new_schema` 는 「전략 인자 없는 호출 = 옛 코드와 같은 행(새 칸 NULL·반환 None)」 시험(`test_old_call_signature_unchanged`)으로만 — 배포 전 원본 파일을 돌리는 시험은 T10·B7 로 넘김.
  - 계획 목록 밖 시험: `test_new_db_marks_zero`·`test_registered_last_in_ensure_all_schemas`·`test_migration_failure_does_not_raise`·`test_render_after_mark_revert_does_not_close_gap`·`test_rv_sequence_render_during_revert_then_redeploy_no_unknown`·`test_revert_from_boundary_row`·`test_mark_revert_refuses_before_migration_and_twice`·`test_mark_revert_missing_db_does_not_create`·`test_mark_revert_connect_error_no_traceback`·`test_second_revert_merges_or_stops`·`test_second_revert_merges_with_pullback_before_gap`·`test_second_revert_stops_when_unknown_rows_before_gap`·`test_hts_detect_uses_engine_strategy`·`test_hts_detect_without_engine_uses_active_file`·`test_pullback_sync_row_tagged`·`test_pnl_orders_query_excludes_pullback_orders`·`test_insert_without_column_still_writes`·`test_old_call_signature_unchanged`·`test_strategy_normalized_upper`·`test_dashboard_force_traders_pass_strategy`·`test_unrelated_operational_error_reraised_no_retry`·`test_missing_column_warning_once`·`test_recheck_after_begin_finds_nothing`·`test_read_bounds_d3_when_marks_missing_warns_once`·`test_macd_rows_tagged_and_visible`·`test_live_sell_success_order_tagged`·`test_no_unknown_warning_on_screen`·`test_unknown_rows_logged_and_notified_once`·`test_no_unknown_rows_no_log_no_notify`·`test_empty_revert_gap_warns_distinctly`·`test_nonempty_revert_gap_no_empty_warning`·`test_one_side_empty_gap_no_empty_warning`·`test_slow_notify_does_not_delay_resume`·`test_report_exception_does_not_affect_other_users`·`test_report_runs_when_no_resume_targets`. (T7 시험 44건)
  - 넘김: T8 — 감사 화면 PULLBACK 행 「새 전략」 라벨·`classify` 결과 표시. T10·B7 — 운영 DB 사본 `ensure_all_schemas` 2회(표식 = 테이블별 MAX(id))·옛 코드 무해성 원본 시험. T12 — 전환 뒤 늦은 체결이 발주 때 전략으로 남는 것은 이 Task 에서 고정(`test_late_fill_keeps_order_strategy`). LIVE 거부(`PULLBACK_LIVE_REFUSE_MSG`)는 그대로. → **(10/28 T8 처리)** 감사 체결 표에 PULLBACK 행이 있을 때만 「전략」(`classify_rows` 결과)·「새 전략 내용」 칸. 분류 불명은 「-」, 화면 경고 없음.
  - 서버 적용 절차(배포 승인 대상, T6 와 한 번에): ⓪ 배포 전 읽기 전용 확인 — `which sqlite3`, DB 경로·크기, `ls -l services/data/backups/` ① 배포 전 백업 — `sqlite3 services/data/tradebot_<user>.db ".backup services/data/backups/tradebot_<user>.db.pre-t7_YYYYMMDD_HHMMSS"` 후 `chmod 600`(T6 백업과 같은 시각이면 1개로 갈음, 7일 지난 백업 삭제 관례 그대로) ② tradebot 재시작 → 기동 마이그레이션(`engine/boot_resume.py` 사용자별 try)이 칸·표식을 자동으로 만든다 — 별도 SQL 없음, 두 번 돌아도 쓰기 0 ⓪-2 배포 직전 읽기 전용 확인(「승인 받은 뒤 1회」) — `orders` 에서 `state IN ('REQUESTED','PARTIALLY_FILLED')` 0건(늦은 체결이 분류 불명이 되지 않게). ⓪-3 **⑨ 되돌리기 무해성 정식 시험(T10·B7)을 통과하기 전에는 배포하지 않는다.** ③ 확인 — journal `[migrate] added audit_trades.strategy_type`·`[migrate] added orders.strategy_type`·`[migrate] ensure_trade_strategy_columns OK`·`[migrate] close_strategy_revert_gap OK`, **`ensure_trade_strategy_columns 실패`·`close_strategy_revert_gap 실패` 0건 필수**(실패 줄이 있었으면 감사 로그 페이지 「전략 분류 불명 행」 수 또는 `count_unknown_rows` 를 확인 — 로그인·엔진·대시보드가 동시에 마이그레이션하다 한쪽이 실패하면 그 사이 쓴 행 1개가 분류 불명이 될 수 있음), DB 확인은 「승인 받은 뒤 1회」: `PRAGMA table_info(audit_trades)`·`PRAGMA table_info(orders)` 맨 끝에 `strategy_type`, `SELECT name, value FROM schema_marks` 2행(`…legacy_max_id` = 배포 직전 표별 MAX(id)), 배포 뒤 첫 EMA 체결 행 `strategy_type='EMA'` ④ 되돌림(배포 절 7 ③, 순서 고정) — `systemctl stop tradebot`(로그인·대시보드·엔진 모두 멈춤) → DB 백업 → `python3 scripts/v2/mark_revert.py <user>`(운영 DB 쓰기 1회, 되돌리기 승인 범위·사용자 확인 후) → 출력 `MARKED audit_trades revert_from=…`·`MARKED orders revert_from=…`·종료 코드 0 확인 → 코드 `git revert` → **시작 전 확인: `git -C /root/upbit-tradebot-mvp log -1 --oneline` 이 되돌린 커밋(revert 커밋)인지 확인** → `systemctl start tradebot`. **(B1) 실수로 새 코드인 채 시작했으면**(journal 에 `[migrate] close_strategy_revert_gap OK`·`strategy revert gap EMPTY — mark_revert 뒤 새 코드로 재시작했는지 확인` WARNING, 또는 `log -1` 이 revert 커밋이 아님): 바로 `systemctl stop tradebot` → `python3 scripts/v2/mark_revert.py <user>` 다시 실행(빈 구간이 닫혔으므로 합치기 경로 — 출력 `MERGED …`·`MARKED …`·종료 코드 0 확인) → 옛 코드인지 `log -1` 로 확인 → `systemctl start tradebot`. **(B2) 모르고 새 코드 시작 뒤 그대로 옛 코드로 바꿔 운영했으면**(구간이 이미 닫혀 옛 코드 행이 분류 불명으로 남음 — 재배포 뒤 `[STRATEGY-UNKNOWN]` 알림으로 드러남): 아래 종료 코드 4 절차 ㉠처럼 그 행을 「승인 받은 뒤 1회」 읽기로 확인하고, 사용자 승인 뒤 백업 → 행별 `UPDATE … SET strategy_type='EMA'(또는 'MACD')` 로 수동 정리. 종료 코드 3(revert_from 만 있음 = 앞 되돌림 뒤 재배포 기록 없음)·1(오류)이면 되돌리기를 멈추고 PO 에 보고. **종료 코드 4(구간 합칠 수 없음) 운영자 판단 절차:** (a) 출력 `STOP cannot-merge <표> legacy_max_id=M revert_from=F revert_to=T null_between=N` 의 숫자를 기록 (b) 「승인 받은 뒤 1회」 읽기 — `SELECT id, timestamp, type, reason, ticker FROM <표> WHERE strategy_type IS NULL AND id > M AND id <= F` 로 그 N 행을 본다(분류 불명 행: 배포 전 발주·배포 뒤 체결, 마이그레이션 실패 중 기록 등) (c) 그 행이 옛 EMA/MACD 거래인지(시각·종목·사유, 그 시각 활성 전략) 운영자가 판단해 사용자에게 보고 (d) 승인 뒤 할 수 있는 것은 둘 중 하나 — ㉠ 그 행들이 옛 EMA/MACD 이면 백업 뒤 `UPDATE <표> SET strategy_type='EMA'(또는 'MACD') WHERE id IN (…)` 로 행마다 전략을 적고 `mark_revert.py` 를 다시 돌린다(합쳐짐) ㉡ 판단할 수 없으면 그대로 두고 되돌리기를 진행하되 이번 구간은 기록하지 않는다(재배포 뒤 이번 되돌림 동안의 행은 분류 불명으로 남고 감사 로그 경고에 보임 — 사후에 ㉠과 같이 정리). 어느 쪽이든 UPDATE·재실행은 사용자 승인 후 1회. → 칸·`schema_marks` 는 남긴다(옛 코드는 칸 목록을 직접 적어 NULL 로 넣음 — 무해). 재배포 때 기동 마이그레이션이 `…revert_to` 를 적는다(WARNING `[migrate] strategy revert gap closed`).
  - **수정 1회차(검수 반영 — T7)** ① D2 구간 닫기(`revert_to`)를 `close_strategy_revert_gap` 으로 나눠 `engine/boot_resume.py` 기동 때만 부름 — 로그인·대시보드는 닫지 않음(되돌리기 순서 「정지 → 백업 → mark_revert → git revert → 시작」, 717행·배포 절 7 ③ 고침) ② `mark_revert.py` 합치기 조건 = `null_between == 0` 하나(738행 고침), 종료 코드 4 운영자 절차는 위 서버 적용 절차 ④ ③ `mark_revert.py` 연결도 try 안(오류 출력은 `ERROR <예외 이름>` 한 줄, 경로 없음) ④ `services/trade_strategy.py` — 표식 없음 WARNING 은 (DB 파일, 표) 당 1회, `_table_exists`·`_column_exists` 는 `services/init_db`, `normalize` 는 `services.db._norm_strategy_type` 재사용, SQL `IN` 목록은 `OLD_STRATEGIES` 상수에서 만듦 ⑤ 시험 추가(무관한 OperationalError 재던짐·재삽입 없음, 칸 없음 경고 1회, BEGIN 뒤 할 일 없어짐, revert_from 과 같은 id 경계, MACD 경로, LIVE 매도 성공 주문 행, 읽기 경로 D3·경고 1회, 연결 오류 출력, 렌더가 구간을 닫지 않음, rv 순서) — T7 시험 35건. 감사 뷰어 경고 문구는 그대로(투자자 화면 노출 여부 사용자 결정 중 — 수정 2회차에 결정 1028-06 으로 화면 경고 삭제). 지적의 재현 스크립트(`rv.py`)는 재배포를 `ensure_all_schemas` 로 흉내 내므로 이제 3이 나온다 — 재배포 = tradebot 재시작 = 기동 마이그레이션 경로로 돌리면 0(`test_rv_sequence_…`).
  - **수정 2회차(재검증 「코드 승인 가능, 문서 보완」 + 사용자 결정 1028-06 (가))** ① 감사 뷰어 분류 불명 경고 삭제(`pages/audit_viewer.py` 는 T7 전 원문과 같음) → `report_unknown_rows`(기동 때 사용자별 1회, WARNING `[STRATEGY-UNKNOWN]` + 텔레그램 WARNING dedupe 24시간) ② `close_strategy_revert_gap` 이 빈 구간(`revert_to == revert_from`)을 기록하면 WARNING `[migrate] strategy revert gap EMPTY — mark_revert 뒤 새 코드로 재시작했는지 확인`(일반 `gap closed` 와 구분), 서버 절차 ④ 에 시작 전 `git log -1` 확인·B1·B2 대처 ③ 계획 목록 밖 시험 목록 갱신 ④ 분류 규칙 표 감사 뷰어 칸·계획과 다른 점 ⑩. T7 시험 40건.
  - **수정 3회차(재확인 반박 2건 + 하 1건)** ① 재개 지연: 텔레그램 전송은 동기(`requests.post timeout=5`, 실측 5.03초 지연)라 `report_unknown_rows` 를 마이그레이션 루프에서 빼 `engine/boot_resume.py` `_report_unknown_strategy_rows(known)` 로 옮김 — 사용자별 재개 루프가 끝난 뒤(대상 없음이면 그 판정 뒤) 사용자마다 try, 예외는 그 사용자 ERROR 로그만(`test_slow_notify_does_not_delay_resume`: 가짜 send 0.5초에도 start 가 먼저·0.4초 안 / `test_report_exception_does_not_affect_other_users` / `test_report_runs_when_no_resume_targets`) ② 알림 문구: 경고 채널은 투자자에게도 갈 수 있어 제목 「거래 기록 전략 구분 확인 필요」·본문 「거래 기록 N건의 전략 구분이 비어 옛 화면 이력·손익에서 빠졌습니다. 운영자가 확인합니다. 투자자님이 따로 하실 일은 없습니다.」(N = 체결 기록 + 주문 행 합). 표 이름·로그 태그·사용자 ID 는 WARNING 로그에만 — 시험 금지 문자열에 `audit_trades`·`orders`·`[STRATEGY`·`[migrate]`·사용자 ID 추가 ③ 빈 구간 경고: 두 표 모두 빈 구간일 때만 EMPTY 1줄(두 표 값 함께), 한쪽이라도 행이 있으면 표마다 일반 `strategy revert gap closed | table=… revert_from=… revert_to=…`(로그는 COMMIT 뒤 `_log_revert_gaps`) — `test_one_side_empty_gap_no_empty_warning` 추가. T7 시험 44건.
  - 운영 메모(LIVE 거부 해제 조건 아님): 분류 불명 알림의 dedupe(`strategy_unknown:<user>`, 24시간)는 `services/notifier` 프로세스 메모리 기반이라 tradebot 재시작마다 초기화된다 — 분류 불명 행이 남아 있으면 재시작 1회당 1통이 갈 수 있다. 같은 알림이 재시작마다 오면 행을 정리(서버 절차 ④ ㉠)할 때까지 정상 동작이다.
- [ ] **Step 5: 커밋 승인 요청** — 「⚠ 스키마 변경: `audit_trades`·`orders` 칸 1개씩, `schema_marks` 신설」.

### T8: 감사 로그 칸·체결 행 회차·평단, 용어, 텔레그램 문구

**Files:**
- Modify ★ `core/strategy_engine.py`(`_record_audit_log` 1773-2215 의 PULLBACK 분기)
- Modify ★ `engine/order_reconciler.py`(LIVE 체결 행 506-529: 주문 `meta` 의 `split_round`·`pullback_round`·`judged_price` 를 `insert_trade_audit(meta=…)` 로 옮기고 `entry_price` = 체결 뒤 평단 — F14. 지금은 meta 를 넣지 않음)
- Modify `services/terminology.py`, `docs/operations/terminology.md`
- Modify `services/notifier.py` 호출 문구(새 함수 없음, `send` 사용)
- Test: `tests/regressions/test_r_2026_10_28_p3_t8_pullback_audit.py`

**감사 칸(스키마 변경 없음 — X10):**
- `audit_buy_eval.checks`(JSON)에 `{"strategy":"PULLBACK","round":n,"pullback_round":m,"armed":0|1,"active":0|1,"inactive_reason":"not_golden"|"slope_low"|"slope_drop"|null,"maTrend":…,"ma200":…,"maPullback":…,"slope200":…,"buy_reason":"GOLDEN"|"PULLBACK"|null,"golden_event":0|1}`. `failed_keys` 는 `["NOT_ACTIVE"]`·`["WAIT_PULLBACK"]`·`["SPLITS_FULL"]`·`["PULLBACK_CAP"]`·`["DESYNC"]`·`["SWITCH_RESERVED"]`·`["WARMUP"]` 중.
- `audit_trades.meta`(JSON)·`entry_price`: 체결 행에 `{"split_round":n,"pullback_round":m,"avg_after":…}`, `entry_price` = 체결 뒤 평단. 기록 경로: TEST 는 trader `_audit_trade`, LIVE 는 reconciler 506-529(위 Files). 둘 다 발주 때 `orders.meta` 에 넣은 회차 값을 쓴다. 평단은 T6 체결 콜백이 고친 분할 상태 값.
- 매도 체결 행 meta 에 `judged_price`(TP·SL 가격 또는 데드크로스 판정 봉 종가)와 `judged_reason` 을 남긴다(요청서 8절 「익절 판정인데 손해」 관찰용).
- 보유 중 매도 평가는 `audit_sell_eval`(`tp_price`·`sl_price` = 평단 × (1 ± %), `trigger_key` ∈ `Take Profit|Stop Loss|Dead Cross`).

**용어(운영자 확인 대상, pullback spec 5절):** 「눌림목 분할매수」, 「눌림목 매수」, 「골든크로스 매수」, 「분할 n회차」, 「눌림 대기」, 「전환 예약」, 「전환 완료」, 「복귀」, 「회차 건너뜀」.

**텔레그램 문구(모두 끝에 「투자자님이 따로 하실 일은 없습니다.」):**
- 분할 매수: 「🟢 새 전략 매수 n회차 · <사유> — <종목> 평단 <x>원」
- 회차 건너뜀: 「⚠️ 새 전략 n회차 건너뜀 — <원화 잔고 부족|최소 주문금액 미만>」(외부 주문 공존 규칙: 원인과 할 일 적기 — 잔고 부족이면 「업비트 앱의 미체결 주문·출금을 확인해 주세요」로 바꿔 끝맺음)
- 전환·예약·완료·복귀: T12.
- dedupe(F12): `notifier.send(…, dedupe_key=f"pullback_skip:{user}:{first_entry_ts or 'flat'}:{code}", dedupe_ttl=3600)` — 같은 거래·같은 사유는 1시간에 1회. 분할 매수 알림은 `pullback_buy:{user}:{uuid}`.

- [ ] **Step 1: 실패 시험** — `test_buy_eval_checks_pullback_fields`(키 전부), `test_trade_row_round_and_avg`(TEST trader 경로), `test_live_fill_row_round_and_avg`(reconciler 506-529 경로, 주문 meta → 체결 행 meta), `test_sell_row_has_judged_and_fill_price`, `test_terminology_has_pullback_terms`, `test_notify_text_no_action_needed`, `test_skip_notify_tells_what_to_check`, `test_skip_notify_dedupe`(같은 거래·같은 사유 3회 → send dedupe_key 같음).
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
- [ ] **Step 5: 커밋 승인 요청** — 용어 목록은 운영자 확인을 받아 확정(배포 전).
- **(10/28 구현 반영 — T8, 수정 1회차 반영)** 커밋 전(승인 대기). 시험 `tests/regressions/test_r_2026_10_28_p3_t8_pullback_audit.py` 47건 OK(T7 44건 OK), P3(T1~T8) 293건 OK, `regression_gate.sh` 643/643.
  - 위치: `core/strategy_pullback.py` `audit_view`·`_inactive_reason`·`_wait_key`, POS_DESYNC 1회(453·622), 매도 회차 `exit_round`(671). `core/pullback_audit.py` 신설(`split_trade_audit`·`pullback_sell_reject_text`). `core/strategy_engine.py` `_record_pullback_audit`(1635)·`_pullback_skip`/`_pullback_skip_text`(1719·1740)·`_pullback_start_cooldown`(1768)·`_pullback_notify_buy`(1824)·`_pullback_record_sync`(1331)·`_pullback_block_persist`(1292~)·매수 meta `interval`(1927)·dry-run 알림 키(1980)·매도 meta(2529)·`record_warmup_log`(2643). `core/trader.py` `_audit_trade`(460)·LIVE 매도 거절(1467). `engine/order_reconciler.py` 체결 행(559). `engine/live_loop.py` 복원 예외 알림 1건(362). `services/terminology.py` 새 전략 용어·칸 함수(123~). `services/db.py` `PULLBACK_SYNC` 표시(1718)·`fetch_trades_audit_with_strategy`(1793). `services/trade_strategy.py` `classify_rows`(103). `pages/audit_viewer.py` 전략·새 전략 상태/내용 칸(19·871·912). `docs/operations/terminology.md` 5절.
  - EMA·MACD: 감사 칸·텔레그램·화면 무변경. 기준 커밋 `2749080` 원본과 `insert_trade_audit` 호출·감사 화면 표를 비교하는 시험으로 고정(`test_ema_trade_row_call_same_as_base`·`test_live_fill_ema_call_same_as_base`·`test_ema_only_screen_same_as_base`·`test_ema_sell_reject_text_unchanged`·`test_warmup_audit_ema_unchanged`).
  - 사용자 관점 변화(감사 로그 페이지, 새 전략 행이 있을 때만): 매수·매도 평가 표에 「전략」·「새 전략 상태」, 체결 표에 「전략」·「새 전략 내용」 칸 추가 — **새 전략 행이 있을 때 그 뒤 칸들이 두 칸씩 오른쪽으로 밀림**. 수량 맞춤 행 유형 「🔄 새 전략 수량 맞춤」, 사유 칸 한글. 사라짐·접힘 없음.
  - 계획과 다른 점(16): ① failed_keys 에 `WAIT_GOLDEN` 추가, 원 전략 키 `POS_DESYNC` 는 감사에 `DESYNC`, `SWITCH_RESERVED` 는 라벨만(T12 전 미사용). ② checks 에 계획 키 외 golden·holding·avg·tp/sl 가격·split_round·max_splits·sell_reason·mode·bar_ts·failed_keys 등도 남김, `round` = 판정 뒤 매수 회차. ③ 지표 값이 비면 `inactive_reason` 은 판정된 쪽, 없으면 null. ④ 보유 중 BUY(추가 회차)도 `audit_buy_eval` 에 씀. ⑤ 계획 Files 의 `_record_audit_log` 대신 PULLBACK 전용 `_record_pullback_audit` 를 고침. ⑥ `services/notifier.py` 는 고치지 않음(호출부 문구만). ⑦ 기존 새 전략 문구(지표 오염·저장 실패·복원 실패·쿨다운·매도 거절)도 투자자용으로 다시 씀, 매도 거절 제목에 「새 전략」, T5 시험 2건 기대 문구 갱신. ⑧ 쿨다운 감사 메모 형식(시작·마감 시각 함께). ⑨ 매도 meta `split_round` = 정리 직전 회차, `judged_price` 데드크로스 = 판정 봉 종가. ⑩ 분류 불명 「-」, LEGACY 「옛 기록(EMA/MACD)」. ⑪ 새 파일 `core/pullback_audit.py`, 새 함수 `fetch_trades_audit_with_strategy`·`classify_rows`. ⑫ 쿨다운 알림 사유는 거래소 응답 코드만(원문은 로그·감사 note). ⑬ dry-run 매수 알림은 「모의 실행(실제 주문 없음)으로 반영」·키에 회차·봉 시각. ⑭ PULLBACK 매수·매도 meta 에 `interval` 추가(`interval_sec` 도 둠, EMA meta 무변경). ⑮ 복원 예외는 CRITICAL 1건(복원 실패 본문에 저장 멈춤 사실) — `_pullback_block_persist(notify=False)`. ⑯ T7 시험 2건 고침 — 재개 순서 시험의 0.4초 단언 삭제(표식 단언), 화면 소스 검사 범위를 경고 함수·행 수 조회·경고 문구로 좁힘(뷰어가 `classify_rows` 직접 import).
  - 넘김: T6 넘김의 `[POSITION-SPLIT]` 은 로그 전용 — 화면 라벨 불필요. T11 — 워밍업 봉 부족 기동 거부 알림(`[PULLBACK-WARMUP]` 등 내부 표기 남음). T12 — 전환·예약·완료·복귀 문구, `SWITCH_RESERVED` 기록. T16 — 신버전 화면 문장, **`v2/api_read.py:33` 라벨표에 새 failed_keys(NOT_ACTIVE·WAIT_PULLBACK·WAIT_GOLDEN·SPLITS_FULL·PULLBACK_CAP·DESYNC·WARMUP) 추가**. 배포 전 — 용어 운영자 확인. LIVE 거부(`PULLBACK_LIVE_REFUSE_MSG`)는 그대로.

### T9: 거래 시간 제한 (결정 D5)

**Files:**
- Modify ★ `core/strategy_pullback.py`, `core/strategy_engine.py`(PULLBACK 분기만)
- Test: `tests/regressions/test_r_2026_10_28_p3_t9_trading_hours.py`

**규칙:** PULLBACK 에서만 동작한다. 기본 꺼짐(`enable_trading_hours=False`). 시간 밖(KST, `trading_start_time`~`trading_end_time`, 자정 넘김 허용)에도 지표·armed·prev_golden 은 갱신하고 주문만 막는다. 매도는 `allow_sell_during_off_hours=True` 이면 허용. 막힌 매수는 감사 `failed_keys=["OFF_HOURS"]`.
- **시간 밖 신호의 판정 상태(결정 13-7 에 따름 — 권고 가):** 시간 밖에서 매수 조건이 맞은 봉은 「매수한 것처럼」 armed 를 해제하지 않고 원본 규칙 그대로 둔다 — 곧 armed 는 시간 밖에도 원본처럼 켜지고 꺼지며(매수 조건이 맞았지만 주문이 막힌 봉에서는 armed 유지), 시간이 다시 열린 뒤 첫 봉에서 조건이 맞으면 산다. 시간 밖에 일어난 골든크로스(`justCrossed`)는 놓친 것으로 두고 시간이 열린 뒤 다시 사지 않는다(그 다음은 눌림목 경로). 회차는 늘리지 않는다.
- EMA·MACD 는 지금처럼 쓰지 않는다(F5, `engine/params.py:129-144`). EMA 의 미사용은 운영자 백로그로 보고만 하고(D5) 투자자에게 알리지 않는다(D12).

- [ ] **Step 1: 실패 시험** — `test_trading_hours_blocks_orders_only`(시간 밖 눌림 신호 → 주문 0, 지표 갱신은 됨, armed 유지 — 결정 13-7 가), `test_off_hours_armed_buys_when_open`(시간이 열린 첫 봉에서 close > maPullback → 매수 1), `test_off_hours_missed_golden_not_rebought`(시간 밖 골든크로스 → 열린 뒤 사유 GOLDEN 매수 0), `test_trading_hours_cross_midnight`(09:00~02:00, 01:59 안·02:00 밖), `test_sell_allowed_off_hours`, `test_ema_ignores_trading_hours`(EMA 동작 무변경), `test_default_off`.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
- [ ] **Step 5: 커밋 승인 요청**
- **(10/28 구현 반영 — T9, 수정 1회차 반영)** 커밋 전(승인 대기). 시험 `tests/regressions/test_r_2026_10_28_p3_t9_trading_hours.py` 16건 OK(계획 7건 + 대조·보유 중 추가 분할·재생 일치·BACKFILL 재생·감사 칸·용어 7건 + 수정 1회차 2건: 매도 허용 키 없음 → 시간 밖 손절·데드크로스 SELL, 시간대 없는 시각 = UTC 단위 시험), P3(T1~T9) 309건 OK, `regression_gate.sh` 659/659.
  - 위치: `core/strategy_pullback.py` `_hhmm_minutes`·`is_trading_time`(402·412), 전략 cfg 선택 4키(478~486), `_off_hours`(610), `_step` 시간 밖 처리(727~766 — 매도 막음·놓친 골든·눌림목 매수 막음), `last_eval` `off_hours`·`blocked_signal`·`failed_keys=["OFF_HOURS"]`·`[PULLBACK-HOURS]` INFO 로그(793~803), `audit_view` 덧칸(888). 시간대 없는 값 규칙 주석: `_kst_iso`(289, 봉 시각 = UTC)·`_to_ts`(392, 저장값 복원 = KST)·`is_trading_time`(412, 봉 판정 시각 = UTC). `services/terminology.py` `PULLBACK_STATE_LABEL["OFF_HOURS"]`(120)·`pullback_eval_text`(182·191). `docs/operations/terminology.md` 감사 상태 문구 표 1행. 로더(`engine/pullback_params.py`)는 T2 에 4키 검증·기본값(꺼짐)이 이미 있어 그대로.
  - 판정 시각: **봉 마감 = 봉 시작(`bar.ts`) + 봉 단위, KST**(판정 = 확정 봉 마감 = 주문이 나가는 순간). 원본 백테스터에는 거래 시간 개념이 없다. 봉 마감 기준은 설계 선택이다(봉 누락이 없으면 다음 봉 시가 시각과 같다). 시작 포함·끝 제외, 분 단위. 09:00~02:00 이면 3분봉 01:56 시작(마감 01:59) 안·01:57 시작(마감 02:00) 밖. 시작 == 끝은 하루 종일 안(`live_loop_old._is_trading_hours` 와 같음).
  - 동작: 지표·prev_golden 은 늘 갱신, armed 는 원본대로 켜고 끔(막힌 매수 봉에서 유지 — 13-7 가). 단 매도가 막힌 봉(`allow_sell=False`)에서는 눌림목 판정을 건너뛰어 armed 가 그 봉에서 켜지지 않음, 회차·pending 불변, `_save_buy_undo` 안 부름(되돌림 대상 아님). 시간 밖 골든크로스는 `blocked_signal="BUY:GOLDEN"` 으로 남기고 같은 봉에서 눌림목 경로(armed 갱신)로 넘어감 — 열린 뒤 GOLDEN 다시 사지 않음. 매도는 `allow_sell_during_off_hours=False` 일 때만 막고 거래를 정리하지 않음(열린 첫 봉에서 다시 평가). 워밍업·BACKFILL 재생(`replay_bar`)도 같은 규칙 → 재생 뒤 판정 상태 = 실시간 경로(시험 고정). 텔레그램 알림 없음.
  - EMA·MACD: 무변경. `core/strategy_engine.py`·`core/strategy_incremental.py`·`engine/params.py` 의 PULLBACK 밖 함수가 T8 커밋(`ebe4605`) 원본과 AST 동일, `is_trading_time`·`OFF_HOURS` 사용처는 `core/strategy_pullback.py` 뿐, 시간 밖 봉에서 EMA 매수 주문 그대로(`test_ema_ignores_trading_hours`).
  - 계획과 다른 점: ① `core/strategy_engine.py` 는 고치지 않음 — 막음을 전략 판정 안에서 하므로 엔진은 신호가 없는 봉으로 받고, 감사는 T8 `_record_pullback_audit` 가 `audit_view` 그대로 기록. ② `failed_keys=["OFF_HOURS"]` 는 **막힌 신호가 있는 봉만**(매수·매도 둘 다, 매도 막음은 `audit_sell_eval.checks`). 신호 없는 시간 밖 봉은 원래 대기 사유 + `checks.off_hours=1`, 화면 문구 끝에 「 · 거래 시간 밖」. ③ checks 덧칸 `off_hours`·`blocked_signal`. ④ 시간 밖 골든 봉도 `OFF_HOURS`(`BUY:GOLDEN`) 로 남김. ⑤ 시간대 없는 시각은 UTC 로 봄(`_kst_iso` 와 같은 엔진 봉 시각 규칙).
  - 넘김: T14 — 운용 설정(`ops_settings`)으로 4키를 바꾸면 전략 `cfg` 의 4키도 바꿔야 함(지금은 생성 때만 읽음 → 재시작 전까지 옛 값). 강제 매수·매도(D11)는 거래 시간과 무관(운영자 수동 — 막지 않음, 결정 필요하면 T14 에서). T16 — `v2/api_read.py:33` 라벨표에 `OFF_HOURS` 추가. T10 — 일치 시험은 꺼짐 상태(기본)로. 운영자 백로그 — EMA 거래 시간 제한 미동작(F5, D5·D12) 그대로. T14 — `allow_sell=False` 일 때 손절·데드크로스도 막을지(권고: 손절·데드크로스는 늘 허용, 익절만 막음) — 운영 설정 화면에 키를 열 때 사용자 결정(지금 구현은 셋 다 막음). T10 — 기준 커밋에 고정된 원본 비교 시험 정리: `test_ema_ignores_trading_hours`(ebe4605), T8 원본 비교 5건(2749080), T6 원본 비교(0b04570). 공용 함수를 정당하게 고치면 게이트를 영구히 막으므로 기록용으로 옮기거나 기준 갱신 규칙을 정함.
  - 사용자 관점 변화(설정을 켰을 때만): 보유 중 추가 분할이 막힌 봉은 감사 로그 매도 평가 표에 「거래 시간 밖 — 매수 막음 · 눌림목 매수」로 보임. 막힌 신호가 없는 시간 밖 봉은 원래 문구 뒤에 「 · 거래 시간 밖」. 꺼짐(기본)이면 화면 변화 없음.

### T10: 시험 묶음 — 일치·재시작·BACKFILL·무변경·건너뜀·시장가

**Files:**
- Create `tests/v2/js/pullback_reference.mjs`(1-3 에서 만든 것), `tests/v2/js/pullback_reference.test.mjs`
- Create `tests/fixtures/pullback/upbit_{a,b,c}.json`(업비트 확정 봉), `tests/fixtures/pullback/cfgs.json`, `tests/fixtures/pullback/expected/<fixture>__<cfg>.json`
- Create `tests/regressions/test_r_2026_10_28_p3_t10_parity.py`, `..._t10_restart.py`, `..._t10_backfill.py`
- Modify `.gitignore`(`!tests/fixtures/pullback/**/*.json` 예외 — 전역 `*.json` 규칙, project-rules push 전 확인)

**일치 시험 설계:**
- **기준값 생성기**(`pullback_reference.mjs`): 1차 `harness.mjs` 방식대로 원본 HTML 143~938행 스크립트를 `vm` 컨텍스트에 넣는다(바이트 그대로, 바꾸지 않음 — `parity.test.mjs:17-18` 과 같은 자르기). `computeMA`·`computeSlope`·`simulate` 를 `vm.runInContext` 로 부른다. cfg 는 원본 `run()` 543-556행과 같은 모양(`buyOnGoldenCross` bool, `deadcross`·`compounding` 은 `"yes"|"no"` 문자열). 출력: `{"buys":[{"signal_bar_t","fill_bar_t","round","trigger"}], "sells":[{"bar_t","type","entries"}]}`. `signal_bar_t` = `entries[k].time` 의 앞 봉.
- **기준값 고정**: 생성기 출력을 `expected/*.json` 으로 커밋한다. `pullback_reference.test.mjs` 는 「새로 만든 출력 == 커밋된 파일」을 확인한다(node 없는 서버 게이트는 Python 쪽만 돈다 — `scripts/regression_gate.sh:163-178`).
- **업비트 fixture 3세트**(T10 Step 0, 사용자 확인 후 — 외부 내려받기, 로컬 맥 IP): `upbit_a` = KRW-JTO 3분 30일, `upbit_b` = KRW-BTC 1분 7일, `upbit_c` = 골든·데드·눌림이 모두 있는 다른 종목 3분 30일. 각 세트 봉 수 ≥ `required_bars` 최대 조합 + 500. 받은 시각·주소·봉 수를 파일 머리에 남긴다. 형성 중 봉은 뺀다. 빈 봉은 채우지 않는다(F6).
- **조합(spec 6절 전부, `cfgs.json`)**: `base`(ema, golden yes, maxSplits 5, maxPullbackBuys 5, slopeDrop 0, deadcross yes, compounding no) 에서 하나씩 바꿈 — `golden_no`, `golden_only`(maxSplits 0), `pb_lt_splits`(maxPullbackBuys 2 < maxSplits 5), `slope_drop`(0.3), `deadcross_no`, `compounding_yes`, `sma`, `splits_full_armed`(maxSplits 2) — 9개. 3세트 × 9 = 27 경우.
- **비교**: 같은 봉 배열을 `IncrementalPullbackStrategy` 에 첫 봉부터 한 봉씩 넣는다. 체결은 가짜 trader 가 다음 봉 시가로 `notional/px` 만큼 채운다(원본 `px = nb.o`, 평단 = 원본과 같음). 매수·매도 목록(봉 시각, 회차, 사유)이 **완전히 같아야** 한다.
- **비교에서 빼는 것(차이 기록만)**: 체결가, 수수료, 최소 주문금액·잔고 부족 건너뜀. 마지막 봉의 매수 신호(원본은 `i+1<bars.length` 일 때만 삼 — 원본 325·348행)는 양쪽에서 뺀다.
- **각 경우 사건 수 확인**: `base` 세 세트 모두 GOLDEN ≥ 1, PULLBACK ≥ 1, 매도 ≥ 1. 하나라도 0 이면 fixture 를 다시 고른다.
- **재시작 시험**: 같은 배열 가운데(봉 k = 1/2 지점, 보유 중인 지점 1곳 + 미보유 지점 1곳)에서 엔진 객체를 버리고, DB(`pullback_state`) + 워밍업(앞 봉들)으로 새로 만든 뒤 나머지를 넣는다 → 판정 목록이 처음부터 넣은 것과 같다.
  - **시험 조건(F16):** 워밍업 입력은 「배열 첫 봉부터 k 까지 전부」다(원본과 같은 시드 시작점). 실서버 재시작은 그때부터 최근 `_long_bars` 봉만 받아 다시 시드하므로 EMA 시드 시작점이 달라지고 잔차가 남는다(800봉 기준 EMA200 잔차 약 0.25% — `engine/live_loop.py:200` 주석). 이 차이로 실서버 재시작 직후 경계 근처 판정이 원본과 달라질 수 있다. 그래서 (1) 시험에 「최근 `required_bars+1` 봉만으로 재시드」 경우를 하나 더 두고 판정 차이 봉 수를 기록만 한다(`test_restart_recent_window_diff_recorded`), (2) 실서버 재시작 뒤 첫 판정 비교는 배포 관찰 항목으로 둔다(영향표 「수명주기」).
- **BACKFILL 시험**: 봉 j(j < 마지막−5)의 종가를 바꾼 배열로 BACKFILL 을 일으킨다(`backfill_mode=True` 경로) → 재생 중 주문 0, 실제 회차·수량·평단 불변, 재생 뒤 지표·armed 는 바뀐 배열로 처음부터 넣은 것과 같다. Issue #9(재평가 허용)·#11(실제 상태 무오염).
- **무변경**: EMA·MACD 회귀 시험 전부(`bash scripts/regression_gate.sh`).
- **회차 건너뜀·시장가 고정**: T5 시험을 이 묶음에서 다시 부른다.

- [ ] **Step 0: 업비트 fixture 받기(사용자 확인 후 — 외부 내려받기)** — 스크립트 `scripts/v2/fetch_pullback_fixtures.py`(파일로 작성, 초당 2회 이하, 로컬에서만).
- [ ] **Step 1: 실패 시험** — `test_parity_<fixture>_<cfg>` 27개, `test_restart_holding`, `test_restart_flat`, `test_backfill_no_orders_no_contamination`, `pullback_reference.test.mjs` 「기준값 고정 파일과 같음」·「원본 스크립트 sha 같음」.
- [ ] **Step 2: 실패 확인** — `python3 -m unittest discover -s tests/regressions -p "test_r_2026_10_28_p3_t10_*" -v` · `node --test tests/v2/js/pullback_reference.test.mjs`
- [ ] **Step 3: 구현 맞춤**(엔진 코드가 틀리면 T3~T6 로 돌아가 고친다)
- [ ] **Step 4: 통과·게이트** — `bash scripts/regression_gate.sh` 전부.
- [ ] **Step 5: 커밋 승인 요청** — `git check-ignore tests/fixtures/pullback/upbit_a.json` 출력 없음, `git status` 로 fixture·expected 스테이징 확인.
- [ ] **Step 6: P3 중간 검증** — verifier(주장별 판정표) → 반박·누락 고침 → 다시 검증.
- **(10/28 구현 반영 — T10)** 커밋 전(승인 대기). Step 0 fixture 는 PO 가 받음(사용자 승인 1028-12, `scripts/v2/fetch_pullback_fixtures.py` — 받은 뒤 PO 가 검사식만 정리: raw_rows 출력 추가·늘 참이던 unique_t 조건 삭제, 받은 데이터 무변경 — 커밋된 fixture meta 에는 raw_rows 없음). 엔진 코드 수정 없음(일치·재시작·BACKFILL 모두 첫 비교에서 같음). T10 Python 시험 45건 OK(일치 27 + 고정 파일·사건 수 4 + T5 다시 부르기 1 + 기준 커밋 2 + 재시작 6 + BACKFILL 3 + 되돌리기 2 — 수정 1회차에 재시작 1·BACKFILL 2 추가, 1회째 42건), node `pullback_reference.test.mjs` 8건 OK, `regression_gate.sh` 회귀 704/704(T9 때 659 + 45, 1회째 701)·v2 346 OK·v2 JS 123/123(새 시험 파일은 게이트의 `discover -s tests/regressions`·`tests/v2/js/*.test.mjs` 가 자동으로 포함 — 게이트 수정 없음).
  - 위치: `tests/fixtures/pullback/cfgs.json`(조합 9개 — base 를 파일 안에 적고 하나씩 덮어씀, 원본 스크립트 sha256 `4418dad6…2576`)·`expected/<fixture>__<cfg>.json` 27개(머리 `meta` = fixture·cfg·bar_count·script_sha256). `tests/v2/js/pullback_reference.mjs` 에 `PB_DIR`·`scriptSha256`·`loadCfgs`·`cfgFor`·`expectedPath`·`expectedText`·`--write-expected`(기준값 다시 만들기) 추가 — 기존 CLI(`<fixture> <cfg>`)·`reference()` 그대로. `tests/v2/js/pullback_reference.test.mjs`(「원본 스크립트 sha 같음」·조합 이름·세트별 「기준값 고정 파일과 같음」 9조합·base 사건 수). `tests/regressions/test_r_2026_10_28_p3_t10_parity.py` — `SimPosition`·`SimFill`(다음 봉 시가 체결, notional = 배분 기준/분할 수, 복리 = 원본 closePosition 손익 식)·`run_strategy`(on_bar 실시간 경로 + 실제 보유 객체)·`test_parity_<a|b|c>_<cfg>` 27개·`TestFixtures`(조합·고정 파일·사건 수·sha·봉 모양)·`TestT5Recall`·`TestBaselineSingleSource`. `…_t10_restart.py` — `NextOpenTrader`(TEST 매수를 다음 봉 시가로)·`T10EngineCase`(T6Case 임시 DB + 실제 PullbackIndicators 엔진)·`test_restart_holding`·`test_restart_holding_armed`(수정 1회차)·`test_restart_flat`·`test_engine_continuous_matches_reference`·`test_restart_recent_window_diff_recorded`·`test_restart_recent_window_scan_recorded`(수정 1회차에 세 세트). `…_t10_backfill.py` `test_backfill_no_orders_no_contamination`·`test_backfill_replay_only_buy_holding`·`test_backfill_replay_only_buy_flat`(수정 1회차). `…_t10_revert.py` + 실행기 `tests/regressions/revert_old_code_runner.py`. 기준 커밋 모음 `tests/regressions/baseline_commits.py`. `.gitignore` `!tests/fixtures/pullback/**/*.json`.
  - 일치 결과: 27건 모두 매수(신호 봉·체결 봉·회차·사유)·매도(봉·사유·회차) 완전 일치, 차이 0. 사건 수(GOLDEN/PULLBACK/매도): a base 32/237/103, b 30/121/38, c 43/187/57 — 27건 모두 매수·매도 ≥ 1. 관찰: `compounding_yes` 는 세 세트 모두 base 와 사건이 같음(복리는 금액만 바꿈 — 원본도 같음), `slope_drop`(0.3)은 b·c 에서 base 와 같음(기울기 값이 작아 둔화 조건이 안 걸림) — 이 두 조합은 해당 세트에서 판정 차이를 시험하지 못한다.
  - 재시작(upbit_c 앞 4000봉, 엔진 경로·임시 DB): 보유 중 k=2000(복원 `restored`)·미보유 k=2056(`flat`) 모두 재시작 뒤 판정(41·40건)이 처음부터 넣은 것과 같음. 엔진 경로 연속 실행 판정 = 원본 기준값(앞 4000봉 안). 최근 창 재시드(F16, `required_bars+1` = 251봉): 위 두 지점은 차이 봉 0. 덧측정(전략 단위, 세 세트 base, k = 1000·2000·…, 시험 `test_restart_recent_window_scan_recorded` 출력): a 10곳 중 차이 6곳·합 39·최대 12, b 9곳 중 6곳·합 37·최대 13, c 13곳 중 8곳·합 48·최대 12 — 실서버 재시작 뒤 첫 판정 비교(배포 관찰 항목)가 필요하다는 근거. (1회째 보고의 「a 97·b 73·c 115, 최대 27」은 시험이 아니라 scratchpad 스크립트 `recent_window_scan.py`(k = 1000부터 500봉 간격, 지점 a 20·b 17·c 25곳) 출력이었다 — 저장소 시험 수치로 정정.) 수정 1회차: 보유 중 + armed=True 지점 `test_restart_holding_armed`(k=2407, 뒤 사건 39건 같음) 추가 — 복원이 armed 를 버리는 변이(verifier `r3_armed_lost`)를 이 시험만 잡음.
  - BACKFILL(upbit_c 앞 1600봉, 보유 중 m 에서 j=m−10 종가 +3%): 봉별 `backfill_mode=True` 봉은 엔진이 무시(상태 불변) → `_pullback_backfill_step` 링 재생 1회(봉별 루프 빈 목록) → 주문 0, 회차·첫 체결·가상 평단·실보유 수량·평단 불변, 지표·armed·prev_golden·last_ts = 바뀐 배열을 처음부터 넣은 것, 오염 표식 없음, 봉 j 감사 행 `backfill_close`·`PULLBACK_BACKFILL_REPLAY` 1행(Issue #9), 다음 봉 실시간 판정 = 재생 뒤 상태를 복사한 전략에 같은 봉을 넣은 값(이 지점 HOLD, 주문 0 — 수정 1회차에 「아무 Action」 단정을 좁힘).
  - **재생에서만 생긴 매수 신호(12절 6항, 수정 1회차)**: 연속 실행에서 armed 인데 종가 ≤ maPullback 이라 매수가 없던 봉 j 의 종가를 maPullback × 1.01 로 바꿔 BACKFILL → 재생(가상)에서 그 봉에 `BUY:PULLBACK`(가상 회차 +1, 원본처럼 armed 해제), 주문 0, 실보유 수량·평단 불변, 재생 뒤 지표·armed·prev_golden·last_ts = 바뀐 배열을 처음부터 넣은 것. 동작: ⓐ 보유 중(`test_backfill_replay_only_buy_holding`, j=1079·m=1085) — 거래 칸(회차·첫 체결·가상 평단·trade_origin)은 재생 전 값 유지(실제 회차 2 그대로), armed 만 재생 결과(True). ⓑ 미보유(`test_backfill_replay_only_buy_flat`, j=1070·m=1076) — 거래 칸도 재생 결과라 가상 회차 1·`trade_origin=replay` 로 남고 주문은 없음, 다음 실시간 봉에서 실보유가 없으므로 회차 0 으로 맞추고 armed 는 그대로(True) — T4 「워밍업 가상 거래」 규칙과 같음, 매도 주문 없음. 변이로 확인: 링 되살리기 없앰(`r1_no_ring_restore`)은 BACKFILL 3건 모두, 보유 중 거래 칸 되돌림 없앰(`engine/live_loop.py` `restore_split_state({…, **kept})` → pass)은 「no_orders」·「holding」 2건이 잡음.
  - 되돌리기 무해성(8절, T7 넘김 ⑨): 옛 코드 = `1747fcc`(12ec5a4 배포 완료 보고의 서버 실행본 — **실제 서버 HEAD 와 같은지는 배포 정지선에서 SSH 로 대조**한다. 다르면 이 상수와 시험을 그 커밋으로 다시 돌린다). services/·config.py 는 2차 스키마 변경 직전 `0b04570` 과 같음(고정 이력끼리 비교 — 시험 `test_old_services_same_as_before_phase2_schema`). 지금 `config.py` 와는 실행기가 쓰는 상수 3개(`DEFAULT_USER_ID`·`PARAMS_JSON_FILENAME`·`CONDITIONS_JSON_FILENAME`)만 비교한다(수정 1회차 — 파일 전체 비교는 config.py 를 정당하게 고치면 게이트를 영구히 막으므로 뺌). `git show 1747fcc:services/{db,init_db,settings_history}.py` 를 임시 폴더에 꺼내 별도 프로세스에서 import(config 는 상수 3개만 글에서 꺼내 대역 — secrets 를 읽지 않음). 옛 코드로 DB 생성·행 기록 → 사본 둘 중 하나만 지금 기동 마이그레이션(`ensure_all_schemas` + `services.db.ensure_schema`) → 두 DB 에 옛 `insert_order` 3종·`insert_trade_audit` 4종·`fetch_trades_for_snapshot`·`compute_pnl_for_snapshot`(스냅샷 2개): 오류 0, 반환값·표 내용(strategy_type 칸 뺌) 같음, 옛 코드 행 strategy_type NULL, 표식(audit_trades 4·orders 3) 불변, `integrity_check ok`·`foreign_key_check` 빈 결과. 서버 적용 절차 ⓪-3 은 **T10 몫 충족** — ⓪-3 은 B7(운영 DB 사본 `scripts/v2/migration_dryrun.py`, 배포 전 별도 승인) 뒤 충족.
  - 기준 커밋 고정 시험 정리(T9 넘김, Fable 권고 방식): T6 `T5_COMMIT`(0b04570)·T8 `BASE_COMMIT`(2749080)·T9 `BASE_COMMIT`(ebe4605)를 `baseline_commits.EMA_BASELINE_COMMIT = "f4aac1f"`(T9 커밋, push 됨) 하나로 모음 — 각 시험 파일은 이 상수를 import 만 함(시험 본문·뜻 「기준 이후 EMA 경로 무변경」 그대로, 110건 OK). **기준을 올리는 규칙**(모듈 머리 주석): 공용 함수를 정당하게 고쳐 실패하면 ① 「EMA 경로 변경」으로 보고·EMA·MACD 회귀 전부 통과 ② 그 커밋으로 상수를 올림 ③ 커밋 메시지에 「EMA 기준 커밋 <옛> → <새>: <사유>」. 기준은 push 된 커밋. `TestBaselineSingleSource` 가 시험 파일 안 커밋 해시 직접 적기를 막고, 기준 커밋이 HEAD 조상인지 본다. 그 사이 T7(2749080)은 EMA 거래·주문 행에 `strategy_type='EMA'` 를 더함(의도된 변경, T7 시험·승인). 각 원래 기준(0b04570·2749080·ebe4605)으로 10/28 지금 트리를 돌려도 통과(T6 47·T8 47·T9 16건, 실패 0 — 수정 1회차 확인).
  - 계획과 다른 점: ① 시험 파일 하나 더(`…_t10_revert.py` + 실행기) — 8절 시험을 T10 에 둠. ② 8절 「지금(배포 전) 코드」를 「되돌리면 돌아갈 서버 실행본 1747fcc」로 읽음. ③ 재시작은 엔진 경로(StrategyEngine + 임시 DB `pullback_state` + `_pullback_seed_warmup` + `pullback_restore_on_boot`), 일치 27건은 전략 단위(계획 「IncrementalPullbackStrategy 에 넣는다」). 엔진 경로가 원본과 같다는 것은 덧시험 1건으로. ④ 재시작 시험의 봉마다 저장은 재시작 직전 6봉만 실제 DB(그 앞은 저장 생략 — 같은 1행 UPSERT, 봉당 sqlite 약 3ms). ⑤ 최근 창 차이는 엔진 2지점 + 전략 단위 세 세트 32지점(a 10·b 9·c 13) 덧측정(둘 다 기록만). ⑥ 「회차 건너뜀·시장가」 다시 부르기 = T5 시험 8건을 이름으로 묶어 한 시험에서 돌림. ⑦ 기준 커밋 정리 방식은 Fable 권고 그대로(더 나은 대안으로 「기준 AST·해시를 고정 파일로」도 있으나 git 이력 없이도 돌 뿐 갱신 규칙은 같아 택하지 않음).
  - 넘김: Step 5 커밋 — 새 파일 전부 스테이징 확인(`git check-ignore tests/fixtures/pullback/upbit_a.json` 출력 없음 확인함), dashboard 버전 갱신(이 Task 는 버전 줄 무변경). 배포 관찰 — 실서버 재시작 뒤 첫 판정 비교(최근 창 재시드 차이, 영향표 「수명주기」). B7 — 운영 DB 사본 `ensure_all_schemas` 2회. 2차 배포 뒤 `REVERT_OLD_CODE_COMMIT` 를 그 배포 직전 서버 실행본으로(사유 커밋 메시지). Step 6 P3 중간 검증. LIVE 거부(`PULLBACK_LIVE_REFUSE_MSG`)는 그대로. (수정 1회차 추가) ① 판정을 구별하는 조합은 22건 — 27건 중 `compounding_yes` 3건·`slope_drop` b·c 2건(모두 base 와 사건이 같음)을 뺀 수(27 − 5 = 22. 수정 지시문의 「23건」은 5건을 빼면 22 라 22 로 적음). ② 체결가·수수료 차이는 가짜 체결이라 0 — 실서버 체결가 비교는 배포 관찰 항목. ③ pending_fill(체결 대기) 사이 재시작 시험은 LIVE 거부 해제 전 조건(T6 메모 「LIVE 거부 해제 전 조건」 10번, 조건 2 와 같은 축). ④ 같은 봉 TP/SL 우선순위(익절 먼저)는 T4 단위 시험 `test_tp_priority_same_bar` 1건만 지킨다(일치 27건 안에서 같은 봉 TP·SL 동시 성립이 있었는지는 세지 않음).

---

## 7. P4 — 전환·운용 (★ 엔진 관리 계층 포함)

### T11: 엔진 제어 요청 통로 (결정 D3)

**Files:**
- Create ★ `engine/control_requests.py`(엔진 쪽 감시·실행)
- Modify ★ `scripts/tradebot_boot.py`(감시 스레드 시작 `main` 120-153, 생존 파일 `gen` 칸 `_write_engine_alive` 54-69·`engine_alive_tick` 72-79)
- Modify ★ `engine/engine_manager.py`(`start_engine(…, *, mode, strategy=None)` 125-159, `stop_engine(user_id, *, mode=None)` 244-284, 세대 값·`_ready` Event·`_no_recover` `_start_engine_internal` 204-242·`_engine_runner_with_recovery` 286-331, 전략 결정 364-395)
- Modify ★ `engine/live_loop.py`(메인 루프 진입 직전 `:1310` 부근에서 `_ready.set()` — PULLBACK 워밍업 재생·분할 상태 복원 뒤, 메인 루프 `:1311` 맨 앞 `engine.drain_control_queue()`)
- Modify ★ `core/strategy_engine.py`(`control_queue`·`drain_control_queue`)
- Create `v2/control.py`(신버전 쪽 요청 쓰기·결과 읽기 — 표준 라이브러리만)
- Modify `v2/api_write.py`·`v2/api_read.py`(ROUTES), `v2/candles.py`(세대 값 감지 — pid 감지 옆)
- Test: `tests/regressions/test_r_2026_10_28_p4_t11_control.py`, `tests/v2/test_control.py`, `tests/v2/test_candles.py`(세대 값)

**폴더·파일:**
- `services/data/v2_control/<user>/`(700, 신버전이 `mkdir(mode=0o700)`; 엔진도 없으면 만든다).
- 요청 `req-<KST yyyymmddHHMMSS>-<nonce8>.json`(신버전 `UMask=0077` 이라 600): `{"v":1,"id","user_id","mode","kind","payload","created_at","expires_at"}`. `expires_at = created_at + 60초`.
- 결과 `res-<id>.json`(엔진이 `os.open(…, 0o600)` + `os.chmod 0o600` — 엔진 UMask 0022 대비, F21): `{"id","status":"done"|"rejected"|"expired"|"error","code","message","at","detail"}`.
- 처리한 요청은 `req-…` 를 지우고 결과만 남긴다. 결과는 사용자당 최근 50개만 남긴다.

**kind:** `engine_start`, `engine_stop`, `switch`(EMA/MACD → PULLBACK), `revert`(PULLBACK → 직전 또는 고른 전략), `cancel_reservation`, `apply_params`(T13), `force_buy`, `force_sell`, `ops_settings`(T14 — 거래 시간 4키만 적용본에 합침, 결정 13-6). 일시정지는 지금 `POST /v2/api/pause` 그대로(v2 spec 4.7 예외).

**요청 종류별 알림(S1):** 신버전 프로세스가 침해되면 요청 파일만으로 엔진에 주문·전환을 시킬 수 있다(남는 위험 — 영향표). 그래서 엔진은 `force_buy`·`force_sell`·`switch`·`revert`·`engine_stop` 을 실행할 때마다 결과와 관계없이 텔레그램 1회 「신버전에서 <요청> 요청 — 결과 <done|rejected>」를 보낸다(투자자·운영자가 모르는 요청을 바로 알게). `apply_params`·`ops_settings`·`cancel_reservation`·`engine_start` 는 결과 알림 1회. dedupe 키 = 요청 id. 단 시도가 아닌 거절(no_balance·too_frequent 등)은 민감 종류도 (사용자, 종류, code) 60초에 1회로 줄인다(수정 4회차 — 첫 거절과 시도한 결과는 늘 알림).

**감시 스레드(`engine/control_requests.control_loop`):**
- `scripts/tradebot_boot.main` 이 엔진 생존 스레드처럼 데몬 스레드로 띄운다(엔진 스레드 밖 — 엔진이 멈춰 있어도 「엔진 시작」·예약 처리). 2초마다 돈다.
- 한 번에 하나: 전역 `threading.Lock`. 요청을 `created_at` 순으로 1건씩.
- 중복: 같은 `id` 의 결과 파일이 있으면 건너뜀. 만료: `now > expires_at` 이면 실행하지 않고 `expired`.
- 사용자 검사: 파일 경로의 `<user>` 와 본문 `user_id` 가 같고 정규식 `^[A-Za-z0-9_]{1,32}$` 일 때만.
- 예외 격리: 요청 하나의 예외는 `error` 결과로 남기고 루프는 계속. 루프 자체 예외는 로그 1줄 뒤 5초 쉬고 다시.
- 실행은 모두 엔진 프로세스 안의 `engine_manager`·`UpbitTrader` 로.

**세션 없는 엔진 경로(v2 spec 4.7):**
- `start_engine(user_id, *, mode, strategy=None)`: `mode` 는 이미 있음(WO-12, `engine/engine_manager.py:141-148`). `strategy` 가 주어지면 `_engine_runner` 가 세션 값 대신 그것을 쓴다.
- `stop_engine(user_id, *, mode=None)`: `mode` 가 주어지면 `current_mode()`(세션) 대신 그 값.
- 새 전략 운용·예약 중에는 활성 전략 파일을 세션 값보다 먼저 쓴다(T1 의 결정 규칙).
- 다른 모드 엔진이 이미 돌면 거부(`rejected`, `code="mode_conflict"`). Mode Lock Guard 판정은 엔진 프로세스 안에서(`get_running_mode`, 110-123).
- 구버전 EMA/MACD 동작 무변경: 인자가 없으면 지금처럼 세션 값.

**재시작 절차(F7):** `stop_engine` 은 스레드를 10초 join 한 뒤 끝났는지와 관계없이 상태를 지운다(`engine/engine_manager.py:255-268`). 그대로 `start_engine` 을 부르면 옛 스레드가 살아 있는 채 새 엔진이 떠 두 엔진이 될 수 있다(spec 실패 조건). 감시 스레드의 재시작은 `restart_engine(user, mode, strategy)`(새 함수, `engine/control_requests.py`)로만 한다: (1) 쉼 표식 쓰기(아래 F11) (2) `stop_engine(user, mode=mode)` (3) 옛 스레드 객체를 미리 잡아 두고 `is_alive()` 가 거짓이 될 때까지 최대 30초 더 기다림 (4) 거짓이면 `start_engine(user, mode=mode, strategy=strategy)` (5) 30초 넘게 살아 있으면 시작하지 않고 결과 `error code=old_thread_alive` + CRITICAL 「엔진 정지가 끝나지 않아 재시작을 멈췄습니다 — 운영자 확인」, 전환 행은 FAILED(T12).
- **기동 성공 판정(2회째 3):** `start_engine` 은 스레드를 띄우고 바로 True 를 돌려준다(`engine/engine_manager.py:240-242`). 그래서 `engine_manager._ready[user]`(`threading.Event`, `_start_engine_internal` 에서 새로 만듦)를 두고, `live_loop` 가 메인 루프에 들어가기 직전(`engine/live_loop.py:1310` 부근, `while not stop_event.is_set():` 1311 바로 앞)에서 `set()` 한다(3회째 정정 — `:1243` 의 `warmup_complete = True` 는 PULLBACK 워밍업 재생·분할 상태 복원(T6)보다 앞이라 「매매 준비 끝」이 아니다). PULLBACK 은 재생·복원이 끝난 뒤, EMA·MACD 는 지금 루프 진입 시점 그대로다. `restart_engine` 은 (6) `_ready[user].wait(timeout=READY_WAIT_SEC=180)`(워밍업 11회 요청 + 재시도 여유 — 1-2 실측으로 조정)를 기다린다. 기다리는 동안 스레드가 죽으면(`is_alive()` 거짓) 바로 실패. 시간을 넘기거나 죽으면 결과 `error code=start_not_ready`.
- **실패 때 복구 래퍼 금지(2회째 3):** 실패로 판정하면 `restart_engine` 은 `engine_manager._no_recover.add(key)` 를 먼저 두고 `stop_engine` 한다. `_engine_runner_with_recovery`(`engine/engine_manager.py:303-326`)는 예외 뒤 재시작 전에 `key in _no_recover` 이면 재시작하지 않는다. 다음 `start_engine` 때 표시를 지운다(기존 구버전 시작 흐름은 표시가 없으므로 무변경).
- **알려진 한계(2회째 9):** (a) 복구 래퍼가 60/300/900초 `time.sleep` 중이면(`engine/engine_manager.py:318`) `stop_event` 로 깨지 않는다. 이때 `restart_engine` 의 (3) 대기 30초가 지나 `old_thread_alive` 로 전환이 실패한다 — 엔진이 두 개 뜨지 않으므로 안전 쪽이고, 결과·CRITICAL 로 보인다. (b) 복구 래퍼가 스스로 하는 재시작(`:320-326`)은 쉼 표식을 쓰지 않는다. 신버전 캔들 수집은 세대 값(5초 늦음)으로만 알아챈다. 둘 다 위험으로만 기록하고 바꾸지 않는다(복구 래퍼는 EMA 경로이기도 함). *(10/28 수정 1회차 정정: 실제로는 복구 래퍼가 한 번도 재시작하지 않는다 — `_engine_runner` 의 `finally: stop_event.set()` 이 먼저 돌아 복구 래퍼의 `not stop_event.is_set()` 조건이 늘 거짓이다(기준 `f4aac1f`·`1747fcc` 포함 기존 결함). 그래서 (a)(b) 는 지금은 일어나지 않고, 기존 결함은 고치지 않는다 — 고칠지는 사용자 결정으로 별도 작업 후보.)* (c) (3회째) 워밍업이 180초를 넘기면 전환은 `start_not_ready` → FAILED → 활성 파일을 직전 전략으로 되돌림 → `restart_engine(직전)` 순서가 된다. 이때 느린 PULLBACK 옛 스레드가 30초 안에 끝나지 않으면 `old_thread_alive` 로 직전 전략도 띄우지 않아 **엔진이 없는 상태 + CRITICAL** 이 된다. 즉시 전환은 미보유일 때만 하므로 지갑에 코인이 없어 자산 영향은 없다(새 매수만 멈춤). 운영자가 엔진 시작으로 되살린다. (d) (3회째) `RUN_MODE=LEGACY_LOCAL`(롤백용, `config.py:110`) 루프에는 `drain_control_queue` 를 넣지 않으므로 그 모드에서 신버전 강제 매매는 늘 20초 뒤 `engine_busy`(주문 없음)다. 서버 기본은 `UPBIT_MATCH` 다.

**강제 매매 — 엔진 제어 큐(F10 재설계, 2회째 1):** 1회째 설계(감시 스레드가 엔진 `_execution_lock` 안에서 trader 호출)는 두 가지가 틀렸다. (i) `_execution_lock` 은 재진입이 안 되는 `threading.Lock`(`core/strategy_engine.py:305`)이고, 지정가 강제 매수 경로 `force_buy_in` → `execute_force_buy_limit_atomic`(`services/trading_control.py:309-313`, `core/strategy_engine.py:125`)이 같은 잠금을 다시 잡아 교착된다. 교착되면 그 엔진의 체결 콜백(`_on_limit_fill` 432·`_on_hts_detect` 382)과 봉 처리 뒤 주문이 모두 멈춘다. (ii) (3회째 정정) 이 잠금은 봉 처리에서도 잡힌다(`core/strategy_engine.py:790,808` `on_new_bar`, `:914,962` `on_new_bar_confirmed`, `:432` `_on_limit_fill`, `:59,102,125,201,382`). 그래서 다른 스레드가 잠금을 쥔 채 지정가 경로를 부르면 봉 처리·체결 콜백까지 멈춘다. 새 설계:
- 감시 스레드는 어떤 엔진 잠금도 잡지 않는다.
- 엔진이 실행 중이면 감시 스레드는 `engine.control_queue`(새 `queue.Queue`, 엔진 인스턴스 칸)에 `ControlItem(kind, payload, done: threading.Event, result, cancelled: bool)` 를 넣고 `done.wait(timeout=20)` 한다.
- 엔진 스레드는 메인 루프(`engine/live_loop.py:1311` `while not stop_event.is_set()`) 맨 앞에서 `engine.drain_control_queue()` 를 부른다. 이것은 봉 처리와 같은 스레드에서 차례로 돈다(봉 처리 도중 끼어들지 않음). 항목마다 `cancelled` 이면 버리고, 아니면 실행: `force_sell` → `force_liquidate(user, self.trader, ticker, …)`, `force_buy` → PULLBACK 이면 `with self._execution_lock: self._execute_pullback_buy(reason="FORCE")`(D6, 회차 +1 — 시장가 엄격 금액 경로라 안에서 잠금을 다시 잡지 않음, 체결 콜백 `_on_limit_fill`(`:432`)과 분할 상태 갱신이 겹치지 않게 잠금 안), EMA/MACD 이면 **잠금 밖에서** `force_buy_in(user, self.trader, ticker, …, strategy_type=…)`(D11 a — 지정가 경로가 안에서 잠금을 잡으므로). `drain_control_queue` 는 메인 루프 맨 앞(봉 처리 `on_new_bar_confirmed` 가 잠금을 잡기 전·푼 뒤)에서 돌므로 엔진 스레드는 이때 잠금을 쥐고 있지 않다. `force_sell` 도 잠금 밖(`force_liquidate` 는 시장가, 잠금 안 잡음).
- 20초 안에 `done` 이 안 오면(워밍업 중 등) 감시 스레드가 항목의 `cancelled = True`(항목 잠금으로 실행 시작과 배타) → 결과 `error code=engine_busy`. 이미 실행이 시작됐으면 끝날 때까지 기다린다(늦은 이중 주문 없음).
- 엔진이 없으면: `force_sell`·EMA/MACD `force_buy` 는 감시 스레드가 새 trader 로 바로 부른다(구버전 강제 매매와 같음, 엔진 잠금 없음). PULLBACK `force_buy`(D6)는 `rejected code=engine_required`.

**쉼 표식(F11):** 같은 pid 안 재시작은 생존 파일 `gen` 이 최대 5초 늦게 보인다(5초 주기, `scripts/tradebot_boot.py:42`). 그래서 `restart_engine` 은 stop 전에 생존 파일과 같은 폴더에 `.engine_restart.json` `{"user","at","until": at+300}`(600, 원자적 쓰기)을 먼저 쓴다. `v2/candles.py` 는 업비트 요청 직전 pid 확인 자리에서 이 파일도 읽고 `until` 전이면 쉰다. 엔진 재시작 세대 값(아래)은 보조 신호로 남긴다.

**엔진 재시작 세대 값:** `engine_manager._gen[user]` 를 `_start_engine_internal` 마다 1 올린다(같은 pid 안 `_engine_runner_with_recovery` 재시작 286-331 포함). 생존 파일에 `"gen": {user: n}` 을 더한다. `v2/candles.py` 는 pid 와 함께 gen 을 읽어, 바뀌면 지금 pid 변경과 같은 규칙(그 자리 멈춤·300초 쉼)을 걸고 `window_units` 를 바로 다시 읽는다.

**신버전 API:**
- `POST /v2/api/control` `{"kind","payload"}` → 검사(세션 user·mode, Origin) → 진행 중 요청이 있으면 409 `busy` → 요청 파일 쓰기 → 202 `{"id"}`.
- `GET /v2/api/control/result?id=` → 결과 또는 `{"status":"pending"}`. 60초 넘으면 화면 「엔진이 응답하지 않습니다」.
- `GET /v2/api/control/state` → `{"pending": id|null, "reservation": {…}|null}`(예약은 DB `strategy_switch` 읽기, ro).

- [ ] **Step 1: 실패 시험**
  - `test_control_duplicate_ignored`: 같은 id 두 파일 → 실행 1.
  - `test_control_expired_60s`: `created_at` 61초 전 → 실행 0, `expired`.
  - `test_control_one_at_a_time`: 두 요청 → 순서대로 1건씩, 동시 실행 0.
  - `test_control_thread_exception_isolated`: 실행 함수 예외 → `error` 결과, 다음 요청 정상.
  - `test_control_result_file_600`: 엔진 UMask 0022 아래에서도 결과 600.
  - `test_control_user_mismatch_rejected`: 경로 user ≠ 본문 user → 실행 0.
  - `test_control_engine_start_without_session`: `st.session_state` 없이 `start_engine(u, mode="LIVE", strategy="PULLBACK")` 성공(가짜 runner).
  - `test_control_engine_stop`: `stop_engine(u, mode="LIVE")` 세션 없이 동작.
  - `test_control_mode_conflict`: TEST 엔진 실행 중 LIVE 시작 요청 → `mode_conflict`.
  - `test_control_force_sell`: 엔진 프로세스 trader 로 `force_liquidate` 1회.
  - `test_control_force_buy_pullback_round`(D6): PULLBACK 운용 중 → 회당 금액 1회, 회차 +1, 사유 `FORCE`, 엔진 안에서.
  - `test_control_force_buy_ema_ratio`(D11 a): EMA 운용 중 → 잔고 × order_ratio, 시장가.
  - `test_v2_has_no_engine_import`: `v2/control.py` import 그래프에 `engine`·`core`·`services` 0(기존 `test_server_import_graph_clean` 에 `v2.control` 추가).
  - `test_old_engine_behaviour_unchanged`: WO-12 시험 `tests/regressions/test_r_2026_09_30_wo12_boot_resume.py` 전부 통과.
  - `test_gen_bumps_on_inner_restart`(candles): pid 같고 gen 바뀜 → 다음 fetch 0·쉼 300·`window_units` 다시 읽음.
  - `test_restart_waits_old_thread_exit`: 가짜 옛 스레드가 15초 뒤 끝남 → 그 뒤 start 1회; 40초 살아 있음 → start 0, `old_thread_alive`.
  - `test_restart_waits_ready_event`: 가짜 엔진이 10초 뒤 `_ready.set()` → 결과 done; 끝내 안 세움 → 180초(가짜 시계) 뒤 `start_not_ready`; 대기 중 스레드 죽음 → 바로 `start_not_ready`.
  - `test_ready_set_after_pullback_restore`: PULLBACK 기동에서 `_ready.set()` 호출 순서 = 워밍업 재생 → `pullback_state` 복원 → set → 메인 루프 첫 반복. 복원이 예외면 set 0.
  - `test_failed_start_not_recovered`: 실패 판정 뒤 엔진 runner 가 예외 → 복구 래퍼 재시작 0(`_no_recover`). 구버전 `start_engine` 흐름(표시 없음)은 지금처럼 최대 3회 재시작.
  - **교착 없음 증명(2회째 1)** — 모두 실제 `threading` 으로 돌리고 각 시험은 `join(timeout=5)` 가 끝나는지로 판정(타임아웃 = 실패):
    - `test_force_buy_fixed_price_no_deadlock`: 조건 파일 `fixed_price_buy_enabled=True`·LIVE 가짜 trader, 엔진 스레드 루프가 도는 중 감시 스레드가 `force_buy` → 5초 안에 결과 done, `execute_force_buy_limit_atomic` 이 `_execution_lock` 을 1회 잡고 풀었음(잠금 계측), 엔진 루프가 다음 봉을 처리함.
    - `test_force_buy_with_concurrent_fill_callback`: 위와 같은 때 reconciler 스레드가 `_on_limit_fill` 을 부름 → 둘 다 5초 안에 끝남, `_pending_buy_uuid` 매칭 성공(WO-8b 원자화 유지).
    - `test_force_sell_during_bar_processing_serialized`: 엔진 스레드가 봉 처리 중(가짜 지연 1초)에 `force_sell` → 봉 처리가 끝난 뒤 주문(실행 시각 순서 기록), 동시 실행 0.
    - `test_control_queue_timeout_cancels`: 엔진 루프를 멈춰 둠 → 20초(가짜) 뒤 `engine_busy`, 그 뒤 루프를 풀어도 주문 0(취소 확인).
    - `test_control_never_holds_execution_lock`(lint): `engine/control_requests.py` ast 에 `_execution_lock` 이름 0.
    - `test_force_buy_pullback_vs_fill_callback_serialized`(3회째): 큐의 PULLBACK 강제 매수가 잠금 안에서 `_execute_pullback_buy` 를 도는 동안 reconciler 스레드가 직전 분할 주문의 `_on_limit_fill` 을 부름 → 둘이 겹치지 않음(진입·퇴장 순서 기록), 둘 다 5초 안에 끝남, 분할 상태 qty = 두 체결 합.
    - `test_ema_force_buy_called_outside_lock`: EMA 강제 매수 실행 때 `force_buy_in` 호출 시점에 `_execution_lock.locked()` 가 거짓.
  - `test_control_queue_empty_no_effect`: EMA 엔진, 큐 비어 있음 → 봉 판정·주문 지금과 같음.
  - `test_rest_mark_written_before_restart`: `restart_engine` 호출 순서 = 표식 쓰기 → stop → start; candles 는 표식 `until` 전 fetch 0.
  - `test_request_notify_per_kind`: `force_buy`·`force_sell`·`switch`·`revert`·`engine_stop` 실행마다 send 1회(dedupe 키 = 요청 id).
  - `test_entry_does_not_switch`(A8): 입장·홈·운용 탭 읽기 API 만 부름 → 요청 파일 0, 활성 전략 파일 바이트 불변.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트(A11: 신버전 프로세스에 엔진 스레드 0).
- [ ] **Step 5: 커밋 승인 요청** — `scripts/tradebot_boot.py` 변경은 tradebot 재시작 대상(배포 절).
- **(10/28 구현 반영 — T11)** 커밋 전(승인 대기). 시험 `tests/regressions/test_r_2026_10_28_p4_t11_control.py` 51건 OK(3회 반복 OK, 약 10초), `tests/v2/test_control.py` 9건·`tests/v2/test_candles.py` +4·`tests/v2/test_engine_alive.py` +1 — `regression_gate.sh` 회귀 755/755(T10 704 + 51)·v2 360 OK(346 + 14)·v2 JS 123/123(게이트 약 131초). 빨간 단계: 엔진 쪽 51건 중 failures 6·errors 37(빈 틀 `engine/control_requests.py` 로 import 만 되게 한 뒤 — `core/engine_control.py`·`_pullback_force_buy` 는 시험보다 먼저 씀), v2 쪽 38건 중 failures 5·errors 3(`v2.control` 없음 1건 포함).
  - 위치: `engine/control_requests.py` 신설(감시 `Controller.scan_once`·`_process`·`_validate`·`_finish`·`_notify`·`execute`·`_force`·`_through_engine`·`restart_engine`·`_fail_start`, 모듈 `restart_engine`·`control_loop`·`register_handler`, 상수 POLL 2초·만료 60초·큐 대기 20초·옛 스레드 30초·준비 180초·쉼 300초·결과 50개). `core/engine_control.py` 신설(`ControlItem`·`attach`·`running_engine`·`mark_ready`·`drain_control_queue`·`READY`). `core/strategy_engine.py` `_pullback_force_buy`(1847~)·`_pullback_skip` 사유 기록 1줄(1722). `engine/engine_manager.py` `__init__` 칸 `_ready`·`_gen`·`_no_recover`·`_strategy_override`(195~198)·`get_gen`·`gen_map`(200~204), `start_engine(…, mode, strategy=None)`(255·268·288~298), `_start_engine_internal` 세대 +1·준비 Event(368~369), `stop_engine(user_id, *, mode=None)`(387), 복구 래퍼 `_no_recover`(449~470), `_engine_runner` 지정 전략(503). `engine/live_loop.py` `_control_attach`·`_control_ready`·`_control_drain`(295~318), 엔진 생성 직후 attach(1304)·메인 루프 진입 직전 ready(1687)·루프 맨 앞 drain(1689), `_pullback_restore_split_state` 의 `engine._pullback_restore_ok`(389·391). `scripts/tradebot_boot.py` 생존 파일 `gen` 칸(59·83)·`_control_thread`(129)·`main` 의 `v2_control` 데몬(171, `TRADEBOT_V2_CONTROL=0` 이면 안 띄움). `v2/control.py` 신설(`write_request`·`pending_id`·`read_result`·`state`·`Busy`). `v2/api_write.py` `ControlHandler`(193)·ROUTES(229). `v2/api_read.py` `ControlResultHandler`·`ControlStateHandler`(741·757)·ROUTES(768~769). `v2/candles.py` `_gen_of`·`_observe_rest_mark`(325·332)·`_request` 의 표식 확인(473).
  - EMA 경로 무변경 근거(기준 `EMA_BASELINE_COMMIT = f4aac1f` 그대로, 올리지 않음): ① `core/strategy_engine.py` 의 PULLBACK 이름이 아닌 함수 전부 기준과 AST 같음(새 함수도 없음 — T9 시험과 T11 시험 둘 다) ② `engine/live_loop.py` 는 PULLBACK 이름 아닌 함수가 기준과 같고, 새 함수는 `_control_*` 3개뿐, `run_live_loop` 은 `_control_*` 호출 3줄·PULLBACK 전용 if 블록을 걷어 내면 기준 AST 와 같음 ③ `engine/engine_manager.py` 는 기준 원본을 별도 모듈로 불러 같은 가짜 환경에서 인자 없이(세션 TEST·EMA) start → 다시 start → stop 한 호출 흔적이 지금 것과 같음, 복구 래퍼 재시작 호출도 기준과 같음 ④ `boot_resume`·`trading_control`·`trader`·`strategy_incremental`·`position_state`·`order_reconciler` 는 기준과 바이트 같음 ⑤ WO-12 시험 전부(`test_old_engine_behaviour_unchanged`) ⑥ `test_control_queue_empty_no_effect`.
  - 교착 없음: 실제 threading 4건(`test_force_buy_fixed_price_no_deadlock` — 지정가 원자 경로가 실행 잠금을 1회 잡고 풂·엔진 루프 다음 봉 처리, `test_force_buy_with_concurrent_fill_callback` — uuid 매칭 성공, `test_force_sell_during_bar_processing_serialized` — 봉 처리 1초가 끝난 뒤 주문, `test_force_buy_pullback_vs_fill_callback_serialized`) 모두 5초 안에 끝남. lint `test_control_never_holds_execution_lock`(감시 파일에 `_execution_lock` 0), `test_ema_force_buy_called_outside_lock`(호출 때 잠금 안 잡힘).
  - 계획과 다른 점: ① 제어 큐·`drain_control_queue` 를 `core/strategy_engine.py` 가 아니라 새 `core/engine_control.py` 에 둠 — `attach` 가 엔진 인스턴스에 `control_queue` 칸을 붙이고 live_loop 가 `_control_drain(engine)` 를 부른다. 근거: `StrategyEngine.__init__`·PULLBACK 밖 함수를 바꾸지 않아 T9 기준 비교가 그대로 통과(EMA 공용 함수 변경 0). ② `_ready` 는 `core.engine_control.READY` 사전을 `engine_manager._ready` 가 같이 씀(live_loop 가 engine_manager 를 import 하지 않게). 준비 실패 사유 `Event.fail_reason="restore_failed"`(분할 상태 복원 예외)면 `restart_engine` 이 180초를 기다리지 않고 바로 `start_not_ready`. ③ 지정 전략은 `_strategy_override[user]`(시작이 거부되면 이전 값 복원) — `_start_engine_internal`·`_start_engine_locked` 시그니처 무변경(WO-12 시험이 위치 인자 4개로 바꿔 끼움). ④ 새 전략 강제 매수는 `_pullback_force_buy()`(계획 `_execute_pullback_buy(reason="FORCE")` 대신): 실행 잠금 안에서 회차 +1·첫 진입 사유 FORCE·`pending_fill`·`last_buy_reason=FORCE` 를 두고 마지막 확정 봉 종가로 만든 봉으로 `_execute_pullback_buy` 를 부른다. 주문이 안 나가면 되돌림(armed 는 그대로). 체결 대기(`_pending_split`) 중·desync·회차 다 참은 거부(`fill_pending`·`desync`·`splits_full`) — 대기 칸이 하나라 덮어쓰면 앞 주문 체결을 잃는다. 그래서 `test_force_buy_pullback_vs_fill_callback_serialized` 는 「1회차 체결 뒤 강제 매수 2회차 주문 중 그 체결 콜백이 잠금을 기다림 → 수량 합 15」로 맞췄고, 거부를 `test_force_buy_pullback_rejected_while_fill_pending` 으로 고정. ⑤ switch·revert·cancel_reservation·apply_params·ops_settings 는 `register_handler` 자리만 — 그 전에는 `rejected not_ready`(T12~T14 가 채움). ⑥ `engine_start` 는 준비 신호를 기다리지 않음(스레드 시작 = done `started`). 준비 판정은 `restart_engine` 만. ⑦ 알림: 모든 처리 결과(만료·오류 포함) 1회(dedupe `v2_control:<id>`), 주문·전환·정지 5종은 WARNING·끝 줄 「직접 요청하지 않으셨다면 운영자에게 바로 알려 주세요」, 나머지는 INFO·「투자자님이 따로 하실 일은 없습니다」. 사용자 불일치는 알림 없이 WARNING 로그. ⑧ 엔진 없음 강제 매매는 활성 전략 파일 기준 새 trader(PULLBACK 매도는 적용본 종목). ⑨ v2 쪽 「진행 중」 = 결과가 없고 만료 전인 요청(엔진이 꺼져 있어도 409 가 영구히 남지 않게), 결과 조회에 `overdue` 칸, `reservation` 은 T12 전 늘 null. ⑩ 캔들 쉼 표식 상한 at+300초, 세대 값은 이미 본 사용자 값이 바뀔 때만 쉼(새 사용자 추가는 쉬지 않음). ⑪ 기존 시험 고침 3곳: `test_engine_alive` 키 집합에 gen(+ `TRADEBOT_V2_CONTROL=0` — 시험 프로세스에서 감시 스레드를 띄우지 않게), `test_server_import_graph_clean` 에 `v2.api_write`·`v2.control`, `test_api_write_imports` 허용 목록에 control. ⑫ 문구(T8 넘김): live_loop 기동 거부 본문(「새 전략(PULLBACK)」·내부 사유 원문은 로그에만), 워밍업 봉 부족 본문(「운영자 절차·배포 절 되돌리기 ①」 삭제, 보유 중이면 할 일 「급히 정리하셔야 하면 업비트 앱에서 직접 매도」), engine_manager LIVE 거부 본문. 제목은 그대로(T3 시험 문구).
  - 관찰(보고, 고치지 않음 — EMA 경로): 복구 래퍼(`_engine_runner_with_recovery`)는 실제로 한 번도 재시작하지 않는다. 사유는 `_engine_runner` 의 `finally: stop_event.set()` — 예외가 복구 래퍼로 올라올 때 이미 stop_event 가 켜져 있어 재시작 조건(`not stop_event.is_set()`)이 거짓이다(수정 1회차 정정 — 처음 메모의 「자기 스레드가 살아 있어 False」는 시험 가짜 runner 에서만 보인 모양). `TestRecovery` 는 가짜 runner 라 그 finally 를 거치지 않는다(시험 주석에 적음). 기존 결함(`f4aac1f`·`1747fcc` 포함)이라 고치지 않고, 고칠지는 사용자 결정.
- **(10/28 수정 1회차 반영 — T11)** 커밋 전(승인 대기). verifier 「수정 후 승인」·코드 품질 「막음 1」 반영. 새 시험 `tests/regressions/test_r_2026_10_28_p4_t11_control_fix1.py` 35건, v2 +3(`test_control` 링크 폴더·FORCE 용어, `test_candles` 미래 at).
  - 막음(링크): 결과·쉼 표식·엔진 생존 파일 쓰기를 새 `core/safe_file.py` `atomic_write_600`(mkstemp 임의 이름 O_EXCL 600 → fchmod → os.replace)로. 요청 읽기 `read_nofollow`(O_NOFOLLOW·일반 파일만·64KB). 폴더 `check_private_dir`(링크 아님·소유자 = 엔진 프로세스·그룹/남 쓰기면 건너뜀·읽기만 열렸으면 700 으로 맞춤 — 열 때 O_NOFOLLOW 로 fchmod). 링크 요청 파일은 링크만 지움. `scripts/tradebot_boot.py` `_write_engine_alive` 도 같은 도우미(이름·내용·주기 그대로). 신버전 `v2/control.py` `_ensure_dir` 도 링크 폴더면 OSError(바깥 폴더 chmod 0).
  - 사용자당 1건·간격: 한 번 훑을 때 사용자마다 가장 오래된 1건(빠른 버림 — 중복 id·id 오류·깨진 파일 — 은 셈에 넣지 않음). 강제 매수·강제 매도·엔진 정지는 **같은 사용자·같은 종류** 30초(`MIN_INTERVAL_SEC`) — 그 안은 `rejected too_frequent`, 알림은 같은 실행 뒤 처음 1회(수정 4회차에서 (사용자, 종류, code) 60초 1회로 바꿈). 종류별로 둔 근거: 강제 매수 직후 급한 강제 매도를 막지 않게.
  - 이상 요청 운영자 알림: 깨진 파일·id 형식 오류·사용자 불일치·링크·폴더 권한 → CRITICAL 1회(dedupe `v2_control_bad:<폴더>`, 1시간 — 감시 안에서도 같은 1시간 억제).
  - 새 전략 강제 매수: 잠금 안 맨 앞에서 `_reconcile_position_with_wallet` + `_pullback_wallet_check`(봉 판정과 같은 경로) → 지갑 0 이고 체결 대기가 없으면 판정 회차를 `_reset_trade`(armed 해제 — 실시간 거래 정리와 같음)·링 기록 고침. 그 뒤 `pending_fill` 참이면 `fill_pending` 거부(같은 봉 두 번째 강제 매수 포함 — T11 회차 시험을 「같은 봉 거부 → 다음 봉 뒤 2회차」로 바꿈). 거절 뒤 `st.armed = armed` 다음 `amend_last_split`.
  - 재시작·시작: 엔진이 있을 때만(`get_running_mode` 또는 관리자 표 스레드 생존) stop — `restart_engine`·`_fail_start` 둘 다. start 가 False 이고 그 사이 엔진이 떠 있으면 끄지 않고 `already_running`/`mode_conflict`. 옛 스레드 대기에 관리자 표에서 빠진 같은 이름(`engine_runner_<user>_<모드>`·`run_live_loop_<user>_<모드>`, 정확히 같은 이름만) 스레드 포함 — `stop_engine` 무변경. `engine_start` 도 그런 스레드가 살아 있으면 `old_engine_alive`. `engine_start` 는 4초(`START_CHECK_SEC`) 스레드 생존 확인 — 그 안에 끝나면 `error start_failed`(「엔진을 시작하지 못했습니다」, 새 전략 실계좌 거부도 여기로). 엔진 안 실행이 시작된 뒤 120초(`EXEC_WAIT_SEC`) 상한 → `error result_unknown`.
  - 준비 Event·세대: `_start_engine_internal` 이 Event 에 그 시작의 `stop_event` 를 적고(`ev.stop_event`), `attach` 는 다른 시작의 Event 면 잡지 않음. `mark_ready` 는 멈춤 신호가 켜졌으면 세우지 않음. `_engine_runner` finally 에서 `engine_control.detach(user_id, stop_event)`(자기 항목만), `running_engine` 도 멈춘 항목을 지움. `start_engine` 은 `_start_engine_locked` 를 try/finally 로 감싸 거부·예외 모두 이전 지정 전략으로 되돌림.
  - 엔진 없을 때: 전략은 `_decide_strategy_type(user, None)`(엔진 기동 규칙), 새 전략 종목·봉은 적용본만(없으면 `params_missing`).
  - 그 밖: 캔들 쉼 표식 `min(until, at+300, now+300)`. 용어 `FORCE` → 「강제 매수」(`services/terminology.PULLBACK_REASON_LABEL`·`v2/api_read.REASON_LABELS`·`v2/static/labels.js` — 감사·체결 행 기본 문구가 「눌림목」으로 잘못 나오던 것). 상수 같음 시험(KINDS·TTL·ID_RE·MODES·폴더 이름·쉼 표식 이름·300초). `_force` 중복 import·`_validate` 불필요 isinstance·`restart_engine` 중복 discard 걷어 냄. lint: live_loop `_control_*` 몸체가 정해진 AST 와 같고 `_execution_lock` 0.
  - 계획과 다른 점 추가: 엔진 감시는 `services/data/v2_control` 폴더를 만들지 않는다(없으면 할 일 없음 — 신버전이 첫 요청 때 700 으로 만든다. 엔진이 만들면 소유자·권한이 신버전 쪽 기대와 갈릴 수 있어서).
  - EMA 경로: 기준 `f4aac1f` 그대로. 바뀐 EMA 공용 함수는 `engine_manager.start_engine`(try/finally — 인자 없는 호출은 override 칸이 없어 결과 같음)·`_start_engine_internal`(Event 에 칸 하나)·`_engine_runner` finally(detach 1줄, 예외 무시)뿐 — 같은 호출 흔적 시험(`test_engine_manager_no_arg_calls_same_trace_as_base`)·WO-12 시험 통과. `core/strategy_engine.py` PULLBACK 밖 함수·`live_loop` EMA 경로는 AST 같음 그대로.
  - 넘김 추가: 강제 매매는 엔진 스레드에서 실행되므로 업비트 호출 시간만큼(시장가 1회 — 보통 1초 안팎, 지정가 원자 경로 포함) 그 사이 EMA·새 전략 봉 처리가 늦어진다 — **배포 관찰 항목**(journal `[CONTROL] 처리` 시각과 다음 봉 `[ENGINE-ENTRY]` 시각 차).
- **(10/28 수정 2회차 반영 — T11)** 커밋 전(승인 대기). verifier 2차 「커밋 조건부 승인, 배포 보류」의 N1~N7 반영. 새 시험 `tests/regressions/test_r_2026_10_28_p4_t11_control_fix2.py` 14건.
  - N1·N3 누적 상한: 묶음 둘 — 강제 주문(`force_buy`+`force_sell`)·엔진 시작/정지(`engine_start`+`engine_stop`) — 각각 사용자당 1시간 `HOURLY_CAP=6` 건(시도한 것만). 7번째부터 그 묶음을 1시간(`SUSPEND_SEC`) 멈춤 → `rejected control_suspended`, 운영자 CRITICAL 1회(dedupe `v2_control_suspend:<사용자>:<묶음>`), 멈춤 중 요청은 요청마다 알리지 않음. **엔진 정지는 멈춤 중에도 실행**(매매를 멈추는 안전한 쪽 — 반복 정지는 엔진이 멈춘 뒤 `not_running` 이라 효과 없고, 다시 켜는 시작은 묶음 상한에 걸린다). 상한 상태는 **감시 스레드 프로세스 메모리** — tradebot 재시작 때 비워진다(재시작 직후 다시 6건까지 가능). 시뮬레이션(2초마다 교대 3시간): 강제 주문 시간당 실행 6·6·6, 시작/정지는 시작이 3시간에 5건, 정지는 가짜 실행(늘 「멈췄습니다」)이라 시간당 112~118 — 실제로는 엔진이 멈춘 뒤의 정지는 `not_running`(시도 아님)이라 효과가 없다.
  - N2: 폴더 권한 자동 chmod 제거 — 링크를 따라가지 않고 연 폴더(fd)의 소유자·700 만 확인, 다르면 거부·운영자 알림(권한 그대로). 그 뒤 요청 목록·읽기·결과 쓰기·지우기·정리는 모두 그 fd 기준(`dir_fd`) — 확인 뒤 폴더를 바깥 링크로 바꿔치기해도 바깥을 건드리지 않음(시험 `test_swap_after_open_does_not_touch_outside`, verifier `v3/race` 모양 `test_verifier_race_layout_outside_untouched`). 남는 경로: `services/data` 자체와 그 위 경로는 경로로 연다(신버전은 `services/data` 안에만 쓸 수 있어 그 폴더를 바꿀 수 없음), 쉼 표식·생존 파일은 경로 기준이지만 마지막 이름 링크는 `os.replace` 가 따라가지 않음.
  - N4: `read_nofollow` 단위 시험(링크 경로·dir_fd 링크 → None, 바깥 내용 안 돌려줌, 상한·폴더·없음).
  - N5: 30초 창·시간당 수는 실제 시도 결과만(`ATTEMPTED_CODES` — ok·order_failed·result_unknown·exception·started·stopped·start_failed). `services.trading_control` 의 「⚠️」 반환(보유 코인·원화 없음 — 주문 전 거절)은 새 코드 `no_balance`(시도 아님). too_frequent 문구 끝 「30초 뒤 다시 눌러 주세요.」
  - N7: 기동 때(`scripts/tradebot_boot.py` `main` 의 `_clean_stale_tmp`, try 로 감쌈) `services/data` 의 10분 넘은 `.engine_alive.json…tmp`·`.engine_restart.json…tmp` 만 정리(링크·다른 모듈 임시 파일은 건드리지 않음 — `.*.tmp` 전부가 아니라 우리 접두만으로 좁힘). 사용자 폴더의 결과 임시 파일(죽은 쓰기 뒤 남는 `.res-…tmp`)은 정리하지 않음(넘김).
  - 테스트 바탕 폴더를 신버전처럼 700 으로 만듦(`CtlCase`) — 755 폴더는 이제 거부.
  - 넘김: 상한 값(6/시간)은 운영 관찰 뒤 조정 가능. 실계좌 화면에 강제 매매 단추를 여는 것은 T14. 사용자 폴더 결과 임시 파일 정리.
  - 넘김: T12 — `register_handler("switch"/"revert"/"cancel_reservation")`, 즉시 전환은 `control_requests.restart_engine` 만 씀, 실패 때 전환 행 FAILED·직전 전략 재시작, `v2.control.reservation`(strategy_switch 읽기), holding 판정(지갑 동기화 뒤 — T5 넘김 그대로). T13 — `apply_params`. T14 — `ops_settings`, 화면 60초 「엔진이 응답하지 않습니다」·단추 연결(`POST /v2/api/control`·`GET …/result`·`…/state`). T15 — URL `strategy_type` 세션 값 거르기(T5 넘김 그대로). T5 넘김 「start_engine 거짓 반환·boot_resume 실패 판정」은 `restart_engine` 의 준비 신호로만 처리 — `start_engine` 반환 의미·`boot_resume`(LIVE 만 재개, PULLBACK LIVE 는 거부 경로) 무변경, LIVE 거부 해제 때 다시 본다. `engine/pullback_params.py` 경우 10 알림의 「운영자 절차」 문구는 T8 넘김 범위 밖이라 그대로(T16 또는 PO). T18 — 서버 `services/data/v2_control`(신버전이 첫 요청 때 700 으로 만듦)·결과 파일 600 점검. 배포 — `scripts/tradebot_boot.py`·`engine/*`·`core/*` 변경은 **tradebot 재시작 대상**, `v2/*` 는 tradebot-v2 재시작 대상. LIVE 거부(`PULLBACK_LIVE_REFUSE_MSG`)는 그대로(`TestLiveRefusalKept` 3건).
- **(10/28 수정 3회차 반영 — T11)** 커밋 전(승인 대기). verifier 3차 「수정 후 승인」 반영. 새 시험 `tests/regressions/test_r_2026_10_28_p4_t11_control_fix3.py` 12건, fix2 의 교대 시험 1건은 아래 ③에 맞춰 고침.
  - ① 실행 중 예외도 시도로 셈: `_rate_checked` 가 `execute` 예외 때 30초 창·묶음 기록을 남긴 뒤 다시 던지고 `_process` 가 `error exception` 결과로 씀(엔진이 없을 때 강제 매도는 주문 뒤 기록 단계에서 실패할 수 있음). verifier `exc.py`(강제 매도·2초 간격 100건·200초) 재실행: 실행 7건(30초마다 1건) — ③ 으로 강제 매도는 멈춤 중에도 30초 창만 받기 때문. 같은 모양 강제 매수 1시간 1,800건: 실행 6건. 강제 매도 30초 안 15건: 실행 1건.
  - ② 요청 파일 상한: 사용자당 한 번 훑을 때 이름순 앞 `MAX_REQ_FILES=10` 개만 보고 나머지는 열지 않고 지움, 운영자 CRITICAL 1회(이상 요청과 같은 dedupe `v2_control_bad:<폴더>`). `MAX_REQ_BYTES` 64KB → 8KB. 신버전 `v2/control.py` 값 상한 4096 을 글자 수가 아니라 UTF-8 바이트로 잼(한글 1자 3바이트) — 머리 약 300바이트를 더해도 8KB 안. 실측: 2,000개 × 8KB 훑기 0.16초, tracemalloc 최고 244KB(시험 상한 5MB). verifier `dos.py 2000`(파일 1개 63KB): 0.15초, maxrss 그대로, 남은 파일 0.
  - ③ 강제 매도도 멈춤 중 실행(`ALWAYS_RUN_KINDS` = 엔진 정지·강제 매도, 30초 창은 그대로). 멈춤 중 매도도 묶음 시도로 셈 — 매도가 1시간에 6건 넘게 이어지면 매수 멈춤도 이어진다. 실제로는 보유가 0 이 된 뒤 매도는 `no_balance`(시도 아님).
  - ④ 모든 종류가 묶음에 듦: `_group_of(kind) = CAP_GROUPS.get(kind, "other")`, switch·revert 는 engine 묶음(T12 정지선 아래 한 줄).
  - ⑤ 시험 공백: 소유자 uid 다름 거부(가짜 `geteuid`·가짜 `fstat`), result_unknown 뒤 too_frequent.
  - ⑥ 멈춤 문구 묶음별 — 결과 code 는 `control_suspended` 그대로, detail `group` 으로 문구(`control_suspended_order/engine/other`)를 고르고 운영자 CRITICAL 본문도 같은 글(앞에 「신버전 대시보드에서 」).
  - 넘김(남는 위험): 신버전이 코드 실행 수준으로 침해되면 같은 root 라 tradebot 을 kill 해 메모리의 상한 상태를 비울 수 있다(재시작마다 다시 6건). 사용자 폴더의 `.res-…tmp`(엔진)·`.req-…tmp`(신버전) 임시 파일 정리는 하지 않음.
- **(10/28 수정 4회차 반영 — T11)** 커밋 전(승인 대기). verifier 4차 「수정 후 승인」 반영. 새 시험 `tests/regressions/test_r_2026_10_28_p4_t11_control_fix4.py` 6건.
  - 시험 보강: 강제 매도만 7번(31초 간격) 뒤 강제 매수 → `control_suspended`, 결과 `message` = 강제 매매 묶음 문구, 멈춤 동안 매도를 이어 넣으면 풀린 직후 다시 멈춤. 엔진 묶음 문구도 1건. 변이 m7(매도를 묶음 수에서 뺌)·m8(공용 문구로 되돌림)을 메모리에서 넣어 돌리면 실패(잡힘).
  - 거절 알림: 시도가 아닌 결과(no_balance·mode_conflict·params_missing·not_ready·expired·too_frequent 등)는 (사용자, 종류, code) 60초에 1회(`REJECT_NOTIFY_SEC`). 시도한 결과(`ATTEMPTED_CODES`)는 요청마다. too_frequent 의 「같은 실행 뒤 1회」 규칙은 이 규칙으로 갈음.
  - 배포 관찰 추가: 서버 python 판(3.9 이상 — 이 모듈과 기존 모듈이 `zoneinfo` 사용, 요청 3.8 이상 조건 포함), `systemctl show tradebot -p Restart -p MemoryMax`, `services/data/v2_control`·사용자 폴더 700, `systemctl show tradebot tradebot-v2 -p User -p UMask`(두 서비스 User 같음 — `check_dir_fd` 가 폴더 소유자 = 엔진 euid 를 요구).
  - 남는 위험(수정 4회차 추가): 강제 매도에는 시간당 상한이 없다(30초 창만) — 신버전이 침해되면 30초마다 보유분을 정리할 수 있다. 대신 매도를 시도로 세므로 그동안 강제 매수는 멈춘다.
  - 남는 위험(수정 4회차 추가): 실계좌에서 외부(HTS) 주문이 수량을 묶고 있으면 잔고가 0 이 되지 않아(`no_balance` 가 아님), 강제 매도는 거래소에서 거절될 주문을 30초마다 보낸다 — 자산 손실은 없고 기존 `force_liquidate` 동작 그대로.
  - 남는 위험(수정 4회차 추가): 훑기(2초)마다 넘친·깨진·링크·id 오류 요청 경고 로그가 남던 것을 같은 폴더·같은 사유 60초에 1줄(`WARN_LOG_SEC`)로 줄였다. 운영자 CRITICAL 은 그대로 폴더당 1시간 1회.
  - 시험 보강(verifier 5차): 같은 종류·다른 거절 code 두 건은 60초 안이어도 알림 2건(dedupe 키에 code 포함 — 변이 m12).

### T12: 전환·예약·복귀·예약 취소 (요청서 6절)

> **착수 전 정지선(10/27 T1 검수):** T12 는 활성 파일에 PULLBACK 을 쓰는 첫 경로다. 시작 전에 T5(엔진 연결)가 커밋돼 있고 T1 의 기동 거부(`_engine_runner`·`run_live_loop` 앞쪽)가 적용본 경로로 바뀌었는지 확인한다. 아니면 멈춘다.
>
> switch·revert 는 engine 묶음(시작·정지와 같은 상한)이다(T11 수정 3회차 — `CAP_GROUPS`).

**Files:**
- Create ★ `engine/strategy_switch.py`
- Modify ★ `services/init_db.py`(`strategy_switch` 테이블 — X1, 결정 13-1 에 따름, `ensure_pullback_tables` 안)
- Modify ★ `core/strategy_engine.py`(예약 중 매수 차단, 매도 완료 감지 → 전환 신호)
- Modify ★ `engine/control_requests.py`(switch·revert·cancel 실행)
- Test: `tests/regressions/test_r_2026_10_28_p4_t12_switch.py`

**새 테이블 `strategy_switch`(초안, X1 — 결정 13-1 에 따름):**
```
CREATE TABLE IF NOT EXISTS strategy_switch (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('TEST','LIVE')),
    kind          TEXT NOT NULL CHECK (kind IN ('SWITCH','REVERT','PARAMS')),  -- PARAMS = 적용본 변경 기록(결정 13-8)
    from_strategy TEXT NOT NULL, from_ticker TEXT, from_interval TEXT,
    to_strategy   TEXT NOT NULL, to_ticker   TEXT, to_interval   TEXT,
    params_sha256 TEXT,
    state         TEXT NOT NULL CHECK (state IN ('RESERVED','DONE','CANCELED','FAILED')),
    requested_at  TEXT NOT NULL,   -- KST ISO
    done_at       TEXT,            -- KST ISO
    request_id    TEXT,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_strategy_switch_user_state ON strategy_switch(user_id, mode, state);
```
- 이 테이블이 전환·복귀 감사 기록이다(손익 집계 밖 — `audit_trades` 에 넣지 않음). 신버전 로그 탭은 이 표도 읽는다(T16).
- 예약 조회(매수 차단·복귀 대상)는 `kind IN ('SWITCH','REVERT')` 행만 본다. `PARAMS` 행(결정 13-8)은 늘 `state='DONE'` 이고 예약 판정에 쓰지 않는다. 시험 `test_params_rows_ignored_by_reservation`.

**흐름:**
1. 신버전 「백테스터 규칙으로 전환」 → 확인 창(한 번 더, T14) → `switch` 요청 `{"saved_sha256"}`(D9).
2. 엔진: 저장본 검사(T2 거절 조건) → 해시 확인 → 보유 판정(지갑 기준) → **미체결 매수 주문 확인(F8):** `orders` 에 그 종목 BUY `REQUESTED`·`PARTIALLY_FILLED`(지정가 현재가 매수 대기 포함, `has_pending_bot_limit_buy` `services/db.py:787`)가 있으면 「보유 중」과 같게 예약으로 둔다. 예약 중 그 주문이 체결되면 기존 전략이 매도까지 관리하고, 취소되면(WO-24) 지갑 0 확인 뒤 전환한다.
3. **보유 없음 → 즉시 전환(F9):** `apply_saved` 로 적용본 만들기 → `strategy_switch` 1행(state `RESERVED`, note `switching`) → 활성 전략 파일 `PULLBACK`(`save_active_strategy`, `engine/params.py:447-460`) → `restart_engine(mode, strategy="PULLBACK")`(T11) → **기동 성공(`restart_engine` 결과 done = 워밍업 완료 Event `_ready` 가 180초 안에 세워짐, T11) 뒤에만** 행을 `DONE` → 알림·로그. 기동이 실패하면(T2 경우 9·10, 워밍업 부족, `old_thread_alive`, `start_not_ready`) 복구 래퍼가 다시 띄우지 않게 한 뒤(T11 `_no_recover`) 행을 `FAILED`, 활성 전략 파일을 직전 전략으로 되돌리고 직전 전략으로 `restart_engine` 을 한 번 시도, CRITICAL 「전략 전환 실패 — 기존 전략으로 계속합니다」.
4. **보유 중 → 예약:** `strategy_switch` 1행(RESERVED). 활성 전략은 그대로. 기존 전략이 매도까지 관리한다. 예약 중에는 모든 매수를 막는다(`execute` 의 BUY 를 `_audit_buy_blocked(code="switch_reserved")`) — EMA 의 새 골든크로스도 막힘. 재시작하면 DB 에서 다시 읽어 유지.
5. **매도 완료 → 다음 봉 자동 전환:** 엔진 스레드가 봉 시작 때 「예약 있음 + 지갑 0 확인」이면 전환 신호(메모리 큐)를 감시 스레드에 넘긴다(엔진 스레드가 자기를 멈추면 join 교착 — 그래서 감시 스레드가 실행). 감시 스레드가 3번 절차를 실행하고 행을 DONE.
6. **복귀:** `revert` 요청. 직전 전략·종목·봉 단위 = 마지막 DONE `SWITCH` 행의 `from_*`. 기록이 없으면 신버전이 EMA/MACD 선택을 받아 `{"strategy":…}` 로 보낸다(기본값으로 복귀하지 않음). 보유 중이면 예약(REVERT RESERVED) — PULLBACK 이 데드크로스(설정 시)·TP·SL 만 적용하고 추가 매수 안 함(pullback spec 4.7). 매도 완료 다음 봉에 활성 전략 파일 = 직전 전략, 그 전략 params 의 종목·봉 단위 확인 후 재시작.
7. **예약 취소:** `cancel_reservation` → 행 CANCELED, 매수 차단 해제.
8. 전환·예약·완료·복귀·취소마다: `logs` 1줄, `strategy_switch` 행, 텔레그램 1회(문구 표).
9. **기동 때 처리 중 행 복구(2회째 3):** 3번 도중 프로세스가 죽으면 `state='RESERVED'·note='switching'` 행이 남는다. 감시 스레드는 시작 때 기동 재개(`boot_resume`)가 끝난 뒤(`engine/boot_resume.py` 의 완료 Event — 새로 둠, 없으면 기동 뒤 60초) 이런 행을 찾아:
   - 활성 전략 파일 = `to_strategy` 이고 그 엔진의 `_ready` 가 180초 안에 세워짐 → `DONE`(note `recovered`) + 알림 「전환 완료(재시작 뒤 확인)」.
   - 활성 전략 파일 = `to_strategy` 인데 엔진이 안 뜸·`_ready` 시간 초과 → `FAILED`, 활성 파일을 `from_strategy` 로 되돌리고 `restart_engine(from)` 1회, CRITICAL.
   - 활성 전략 파일 = `from_strategy`(파일 쓰기 전에 죽음) → `FAILED`(note `aborted_before_switch`), 엔진은 그대로, 알림 「전환이 끝나지 않았습니다 — 다시 눌러 주세요」.
   - note 가 없는 RESERVED(보유 중 예약)는 그대로 둔다(예약 유지).

**「매도 완료」 경우별 표:**

| 매도 경로 | 감지 | 완료 판정 | 분할 상태 | 예약 | 기록 |
|---|---|---|---|---|---|
| 엔진 매도(TP/SL/DC/EMA 규칙) | `_execute_sell` 성공 → reconciler 체결 | 다음 봉 시작 때 지갑 0 확인 | 초기화(`reset_after_exit`) | 다음 봉 전환 | 체결 행 + 전환 DONE |
| 신버전 강제 매도 | `force_sell` 요청 결과 done + 체결 | 지갑 0 확인 | 초기화 | 다음 봉 전환 | 강제 매도 행(사유 `FORCE_LIQUIDATE`) |
| 구버전 강제 매도 | `force_liquidate`(`services/trading_control.py:80`) | 지갑 0 확인 | 초기화(T15 정리) | 다음 봉 전환 | 같음 |
| 앱 매도(HTS_SELL) | `_reconcile_position_with_wallet` 지갑 0(`core/strategy_engine.py:596-613`) | 지갑 0 확인 | 초기화 | 다음 봉 전환 | HTS_SELL 행 |
| 일부만 팔림 | 지갑 > 0 | 완료 아님 | 지갑 평단으로 유지 | 유지 | — |
| 매도 거절 반복(`*_REJECTED`) | WO-9 거절 행 | 완료 아님 | 유지 | 유지 + 알림 「매도가 거절되고 있습니다 — 업비트 앱의 미체결 매도 주문을 확인해 주세요」(외부 주문 공존 규칙) | 거절 행(감사 로그 페이지에 보임) |

**텔레그램·로그 문구:**

| 사건 | 문구 |
|---|---|
| 즉시 전환 | 「🔁 전략 전환 완료 → 눌림목 분할매수 (<종목> · <봉>). 투자자님이 따로 하실 일은 없습니다.」 |
| 예약 | 「⏳ 전환 예약 — 지금 보유분은 기존 방식으로 매도까지 관리합니다. 예약 중에는 추가로 사지 않습니다. 투자자님이 따로 하실 일은 없습니다.」 |
| 예약 뒤 완료 | 「🔁 전환 예약 완료 → 눌림목 분할매수. 투자자님이 따로 하실 일은 없습니다.」 |
| 복귀 | 「↩️ 기존 전략으로 복귀 → <EMA|MACD> (<종목> · <봉>). 투자자님이 따로 하실 일은 없습니다.」 |
| 예약 취소 | 「✖️ 전환 예약 취소 — 지금 전략을 그대로 씁니다. 투자자님이 따로 하실 일은 없습니다.」 |
| 매도 거절 반복 | 위 표 |

- [ ] **Step 1: 실패 시험**
  - `test_switch_request_flat_immediate`: 미보유 → 활성 파일 PULLBACK, 적용본 해시 = 요청 해시, 재시작 1회, 행 DONE.
  - `test_switch_reserved_while_holding`: 보유 → 행 RESERVED, 활성 파일 EMA 그대로.
  - `test_reserved_blocks_all_buys`: 예약 중 EMA 골든크로스 → 주문 0, 감사 `switch_reserved`.
  - `test_reserved_switch_on_next_bar_after_flat`: 매도 체결 → 다음 봉에서 전환, 그 봉 매수 0.
  - 「매도 완료」 표 6줄을 각각: `test_flat_by_engine_sell`, `test_flat_by_v2_force_sell`, `test_flat_by_old_force_sell`, `test_flat_by_app_sell`, `test_partial_sell_keeps_reservation`, `test_sell_reject_repeat_keeps_reservation_and_notifies`.
  - `test_reservation_survives_restart`.
  - `test_cancel_reservation`.
  - `test_revert_to_previous`: 직전 EMA·KRW-JTO·minute3 로 복귀.
  - `test_revert_reserved_uses_pullback_exit_rules`: PULLBACK 보유 중 복귀 예약 → 눌림 신호 주문 0, TP 매도 1, 다음 봉 복귀.
  - `test_revert_without_record_requires_choice`: 기록 없음 + 선택 없음 → `rejected code=choose_strategy`.
  - `test_switch_events_notify_no_action_needed`: 모든 문구 끝 「따로 하실 일은 없습니다」.
  - `test_switch_events_not_in_pnl`: 전환 사건이 `audit_trades` 0행, 구버전 손익 불변.
  - `test_switch_rejects_sha_mismatch`.
  - `test_switch_with_open_buy_order`: 미보유 + 미체결 지정가 BUY → 예약, 체결되면 기존 전략 보유 관리, 취소되면 다음 봉 전환.
  - `test_switch_start_failure_rolls_back`: PULLBACK 기동 실패(적용본 깨짐 흉내) → 행 FAILED, 활성 파일 EMA, EMA 재기동 1회, CRITICAL 1.
  - `test_no_reservation_ema_buy_unchanged`: 예약 없음 → EMA 골든크로스 매수 지금과 같음.
  - `test_reservation_read_failure_blocks_buy_only`: `strategy_switch` 읽기 예외 → BUY 차단·WARNING, SELL 정상.
  - `test_switch_table_missing_ema_buys_and_alerts`(2회째 4): 테이블 없음 + 활성 EMA → EMA 골든크로스 매수 1(지금과 같음), CRITICAL 1회(같은 날 두 번째 봉은 dedupe).
  - `test_switch_done_only_after_ready`: `_ready` 를 세우지 않는 가짜 엔진 → 행 DONE 0, FAILED 1, 활성 파일 EMA 로 되돌림.
  - `test_boot_recovers_switching_row_done`, `test_boot_recovers_switching_row_failed_reverts_file`, `test_boot_recovers_switching_row_aborted`, `test_boot_keeps_holding_reservation`(9번 네 경우).
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
- [ ] **Step 5: 커밋 승인 요청** — 「⚠ 스키마 변경: `strategy_switch` 신설(X1)」.

### T13: 「이 설정으로 동작」·「저장만 하기」 — 저장본/적용본 분리 (결정 D9, 요청서 5절)

> **(10/27 T2 검수 메모, Fable 정정 반영) 종목명 정규식 정리:** 엔진 로더는 `^KRW-[A-Z]{1,15}$` 이다(LiveParams `_validate_ticker` 보다 좁음 — `KRW-` 접두·대문자 필수). 신버전의 정규식 상수 `v2/params_schema.py` `_UPBIT_SYMBOL_RE`(`[A-Z0-9]{1,15}`, 백테스트 `symbol` 용)·`v2/api_write.py` `_TICKER_RE`(`[A-Z0-9]{1,20}`)는 더 느슨하지만, 실제 저장본의 `ticker` 는 `_engine_ticker` 가 `v2/db.py` `normalize_ticker`(영문자만, 아니면 None → 409 `engine_ticker_unknown`)로 만들므로 숫자 든 종목은 저장되지 않는다. 손으로 넣은 파일은 로더 `validate` 가 `ticker` 로 거절한다. T13 은 느슨한 상수를 엔진과 같게(`[A-Z]{1,15}`) 맞추는 정리만 한다 — 화면 체감 변경 없음, 통보 대상 아님. 엔진 쪽은 넓히지 않는다(EMA·MACD 검증 불변).
>
> **(T2 검수 메모) 예외 계약:** `apply_saved` 는 `PullbackParamsError` 외에 `OSError`(`_atomic_write` 의 `os.replace`·`fsync` 실패)를 그대로 올린다. T12·T13 의 호출자는 둘 다 잡아 결과 코드로 바꾼다.

**Files:**
- Modify ★ `engine/control_requests.py`(`apply_params`), `engine/live_loop.py`(PULLBACK 적용본 mtime 감시 — `_maybe_reload_params` 531 옆 새 함수 `_maybe_reload_pullback`)
- Modify ★ `core/strategy_pullback.py`(적용 규칙)
- Modify `v2/db.py`(`active_params(user)` 신설: PULLBACK 이면 적용본, 그 밖 지금 `strategy_params`), `v2/api_read.py:200`(`_context`), `v2/api_write.py:111-115`(`_engine_ticker`), `v2/candles.py:272,608-615`, `v2/params_schema.py`(선택 4키 보존)
- Modify `v2/static/save.js`, `v2/static/backtester.html`(확인 창)
- Test: `tests/v2/test_api_write.py`, `tests/v2/test_api_read.py`, `tests/v2/test_candles.py`, `tests/v2/js/save.test.mjs`, `tests/regressions/test_r_2026_10_28_p4_t13_apply.py`

**규칙:**
- 「저장만 하기」: 저장본·v2hist 만 쓴다(지금 그대로). 엔진 값·신버전 화면 종목·봉 경계 창·미리 받기 모두 불변.
- PULLBACK 일 때 신버전 읽기(F19 신버전 4곳)는 적용본이다. 저장본은 백테스터 입력 채움(`GET /v2/api/params/current`)에만 쓴다.
- 「이 설정으로 동작」(업비트 출처만):
  - 지금 전략 EMA/MACD → 6절 전환 확인 창(T12 `switch`)으로.
  - 지금 전략 PULLBACK → 저장 뒤 `apply_params {"saved_sha256"}`. 엔진이 해시 확인(사이에 다른 저장이 있으면 거절 `sha_mismatch`, 화면 「다른 저장이 끼어들었습니다. 다시 저장해 주세요」) → `apply_saved`(임시 파일 → rename, 600) → 결과. 신버전이 결과를 보고 v2hist 해당 행 `applied_at` 을 KST ISO 로 채운다.
  - 엔진 꺼짐 → 「엔진을 시작할까요?」 → 예 = `engine_start` 요청 뒤 적용.
  - 바이낸스 출처 → 「이 설정으로 동작 (사용 불가)」 그대로(서버도 `source != "upbit"` 이면 400).
- 엔진 적용 규칙(pullback spec 4.6):
  - 미보유: 다음 봉부터 새 값.
  - 보유 중 TP/SL·데드크로스: 즉시 새 값.
  - 분할 한도가 줄어 지금 회차 이상이면 추가 매수만 멈춤(파는 일 없음).
  - MA 기간·방식(`ma60p`·`ma200p`·`pullbackP`·`maType`·`slopeLB`) 변경: 지표 다시 시드(워밍업 재생, T3), 그동안 매수 없음(감사 `RESEED`).
  - 종목·봉 단위 변경: 예약 전환으로 다룸(보유 중이면 기존 종목·봉으로 청산 뒤 새 값, 미보유면 재시작) — X8.
- `params_schema.to_engine_file` 는 저장 때 저장본의 선택 4키(거래 시간)를 지우지 않고 보존한다(1차 「19키 정확히·전체 덮어쓰기」 규칙의 바뀌는 부분, `v2/params_schema.py:3`).
- **변경 기록(R1, 결정 13-8 에 따름 — 권고 가):** 엔진이 적용본을 바꿀 때마다(전환·`apply_params`·`ops_settings`) 바뀐 키·이전 값·새 값·적용 시점을 `strategy_switch` 에 kind `PARAMS`·state `DONE` 1행으로 남긴다(`note` = `{"changed":{키:[구,신]},"apply":"next_bar"|"immediate"|"reseed"|"reserved"}` JSON, `params_sha256` = 새 적용본 해시, `from_*`·`to_*` = 지금 전략·종목·봉 단위). `audit_settings` 에는 쓰지 않는다. 이유(2회째 6): `insert_settings_snapshot` 은 `(ticker, interval_sec, bar_time)` 분 단위 UPSERT 라(`services/db.py:1572-1605`) 1분 정기 스냅샷(`engine/live_loop.py:997-1022`)이 변경 기록을 덮어쓴다. 또 `fetch_latest_audit_settings`(`services/db.py:1527`)가 그 표를 「엔진이 실제 적용 중인 조건」으로 읽어 구버전 화면에 변경 기록 JSON 이 조건처럼 보일 수 있다. pullback spec 4.6 「`audit_settings` 에 남긴다」 문구는 9절에서 정정한다. 손익 집계와 무관하다. 1분 정기 스냅샷은 T5 대로 PULLBACK 값(적용본 TP/SL·빈 조건)으로 계속 남는다.

- [ ] **Step 1: 실패 시험**
  - `test_apply_writes_params_record`: TP 5→4 적용 → `strategy_switch` kind `PARAMS` 1행, note `changed.tp == [5,4]`, `apply == "immediate"`(보유 중). `audit_settings` 의 `buy_json` 에 `changed` 키 0.
  - `test_params_record_not_in_old_ui_conditions`: 위 뒤 `fetch_latest_audit_settings` 결과에 `changed` 없음.
  - `test_save_only_does_not_change_applied`: 저장 → 적용본 sha·mtime 불변, 엔진 값 불변.
  - `test_save_only_does_not_change_v2_reads`: PULLBACK 운용 중 저장본만 종목·봉 바뀜 → `/v2/api/status` 종목·봉, `Collector.window_units`, `_targets()` 모두 적용본 값.
  - `test_apply_next_bar`, `test_apply_tp_sl_immediate_while_holding`, `test_apply_fewer_splits_stops_adds_only`, `test_apply_ma_change_reseeds_no_buy`, `test_apply_interval_change_is_reserved_switch`.
  - `test_apply_sha_mismatch_rejected`: 요청 뒤 다른 저장 → 거절, 적용본 불변.
  - `test_applied_written_600_by_rename`: 적용본 600, inode 바뀜(rename), `.tmp` 0.
  - `test_apply_rejects_binance_source`.
  - `test_apply_liveparams_invalid_rejected`(X9): 숫자 섞인 종목 → `rejected code=invalid_ticker`.
  - `test_v2hist_applied_at_set`.
  - `test_save_keeps_trading_hours_keys`.
  - `save.test.mjs`: 업비트 + EMA → 「이 설정으로 동작」 활성, 누르면 전환 확인 창; 업비트 + PULLBACK → 적용 요청; 엔진 꺼짐 → 「엔진을 시작할까요?」; 바이낸스 → 「(사용 불가)」·참고용 문구 유지; 안내 「「이 설정으로 동작」→ 전환 확인(6절)으로 넘어갑니다.」.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
- [ ] **Step 5: 커밋 승인 요청**

### T14: 운용 탭 단추 (요청서 2-마, 결정 D6·D11)

**Files:**
- Modify `v2/static/index.html`(운용 탭), `v2/static/app.js`, Create `v2/static/ops.js`
- Test: `tests/v2/js/ops.test.mjs`, `tests/v2/js/alpine_wiring.test.mjs`, `tests/v2/test_static_lint.py`(`test_operation_buttons_disabled` → 새 단언)

**단추와 동작:**

| 카드 | 단추 | 활성 조건 | 누르면 |
|---|---|---|---|
| 매매 전략 | 백테스터 규칙으로 전환 | 전략 EMA/MACD, 예약 없음, 저장본 정상 | 확인 창 「지금 보유분이 있으면 기존 방식으로 판 뒤 바뀝니다. 전환할까요?」 → `switch` |
| 매매 전략 | 기존 전략으로 복귀 | 전략 PULLBACK, 예약 없음. EMA/MACD 운용 중에는 비활성 + 글자 「기존 전략으로 복귀 (지금은 해당 없음)」(그림 2-마) | 기록 있으면 「<EMA> · <종목> · <봉> 으로 돌아갑니다」 확인, 없으면 EMA/MACD 선택 → `revert` |
| 매매 전략 | 예약 취소 | 예약 있음 | 확인 → `cancel_reservation` |
| 엔진 | 일시정지 | 늘 | 지금 `POST /v2/api/pause`(홈 단추와 같은 동작) |
| 엔진 | 엔진 정지 | 엔진 동작 중 | 확인 → `engine_stop` |
| 엔진 | 엔진 시작 | 엔진 멈춤 | 확인 → `engine_start`(입장 모드) |
| 긴급 개입 | 강제 매수 | 미보유이거나 PULLBACK 회차 남음 | 확인(금액 표시: PULLBACK = 회당 금액, EMA/MACD = 잔고 × order_ratio) → `force_buy` |
| 긴급 개입 | 강제 매도 | 보유 | 확인 → `force_sell` |
| 운용 설정 | 거래 시간 제한(켜기·시작·끝·시간 밖 매도) | 전략 PULLBACK | 저장 → `ops_settings {"keys": 4키 값}` 요청(결정 13-6 에 따름 — 권고 가). 엔진은 **지금 적용본에 이 4키만 합쳐** 새 적용본을 쓴다(저장본의 다른 키는 적용하지 않음). 신버전은 저장본의 같은 4키도 맞춰 써서(백테스터 입력과 어긋나지 않게) 다음 「이 설정으로 동작」 때 지워지지 않게 한다 |

- 1차 안내 「운용 단추는 2차 공개 때 열립니다.」는 지운다. 「매매 중지/재개는 홈 화면 위 단추로 합니다.」는 남긴다.
- 요청 뒤 결과를 2초마다 60초까지 읽는다. 결과 문구는 code 별 표(`busy`·`mode_conflict`·`saved_invalid`·`sha_mismatch`·`choose_strategy`·`expired`·`error`).

- [ ] **Step 1: 실패 시험** — `test_ops_settings_applies_only_4_keys`(Python, T11 묶음): 저장본에 TP 4 를 「저장만」 → 운용 설정 저장 → 적용본 TP 는 그대로 5, 4키만 새 값(「저장만 한 값은 운용 설정 저장 뒤에도 적용본에 없음」). `ops.test.mjs`: 「EMA 운용 중 복귀 단추 글자·비활성」, 상태별 활성 단추 집합(EMA 미보유/EMA 보유/예약 중/PULLBACK 보유/엔진 멈춤), 전환 확인 창 문구, 복귀 선택(기록 없음), 강제 매수 금액 표시 2종, 결과 문구 7종, 60초 넘으면 「엔진이 응답하지 않습니다」. `alpine_wiring`: 단추 글자 순서 `["백테스터 규칙으로 전환","기존 전략으로 복귀","예약 취소","일시정지","엔진 정지","엔진 시작","강제 매수","강제 매도"]`.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과(`node --test tests/v2/js/*.test.mjs`).
- [ ] **Step 5: 커밋 승인 요청**

### T15: 구버전 — PULLBACK 표시 경로·배지·잠금·강제 매수/매도·D10 (요청서 6-나, 결정 D7·D10)

**Files:**
- Create `ui/pullback_lock.py`(`lock_state(user_id) -> {"locked": bool, "why": "pullback"|"reserved"|None, "ticker", "round", "max_round", "strategy_label"}` — 활성 파일 `include_engine_only=True` + `strategy_switch` RESERVED + `pullback_state`)
- Modify ★ `pages/dashboard.py`(584-592 전략 판정, 729-738 params, 자동 재개 412-461 의 두 곳, 엔진 시작 599, 파라미터 설정 646, 설정 History 2368, 강제 매수 2382-2421, 강제 매도 2422-2440, 시스템 초기화 2467, 설정 2601, 배지·상태 보기)
- Modify `pages/set_config.py`(전략 선택 273-275, 저장 304-354 의 `record_snapshot`·`save_active_strategy`·`set_engine_status(False)`, 엔진 시작 374·392)
- Modify `pages/set_buy_sell_conditions.py`(65, 저장 367·570-580·946)
- Modify `pages/settings_history.py`(복원 476-485), `pages/confirm_init_db.py`(51)
- Modify `app.py`(로그인 이동 540·569, 수동 검증 386-394 — D10), Modify ★ `services/auto_verify.py`(84 — D10)
- Test: `tests/regressions/test_r_2026_10_28_p4_t15_old_ui.py`, 기존 `tests/regressions/test_r_2026_08_05_audit_viewer_accessibility.py` 유지

**표시 경로(멈추지 않게):** PULLBACK 운용·예약 중이면 `pages/dashboard.py` 는 `load_params(…, "PULLBACK")`·`st.stop()`(736-738) 대신 `params_obj = engine.pullback_params.to_live_params(적용본, capital)` 을 쓴다. 종목 = 적용본 `ticker`, 회차 = `pullback_state.entry_count / effMaxSplits`.

**배지·상태(그림 6-나):** 맨 위 `st.info("새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다")`(예약 중이면 「전환 예약 중 — 설정은 신버전에서 관리합니다」). 「상태 (보기만)」: 전략 「눌림목 분할매수」, 보유 「n / 최대회」. `set_config.py`·`set_buy_sell_conditions.py` 상단에도 같은 배지(v2 spec 4.6 D3).

**잠금(결정 D7 — 요청서 3종 + 같은 효과를 내는 길):**

| 곳 | 줄 | 잠금 방식 |
|---|---|---|
| set_config 전략 선택 | `pages/set_config.py:273-275` | `disabled=True` |
| set_config 저장(`record_snapshot`·`save_active_strategy`·`set_engine_status(False)`) | `:304-354` | 저장 단추 `disabled`, 함수 진입에서도 `lock_state` 검사 후 돌아감 |
| set_config 엔진 시작 이동 | `:374,392` | `disabled` + 「엔진 시작 (잠김)」 |
| set_buy_sell_conditions 저장 3곳 | `pages/set_buy_sell_conditions.py:367,570-580,946` | `disabled` + 「설정 저장 (잠김)」 |
| dashboard 엔진 시작 | `pages/dashboard.py:599` | `disabled` + 「엔진 시작 (잠김)」 |
| dashboard 자동 재개 2곳 | `:412-461` | `lock_state.locked` 이면 자동 재개 안 함(엔진 시작과 같은 효과). 엔진 쪽 재개는 신버전·기동 재개가 맡음 |
| dashboard 파라미터 설정(엔진 자동 정지) | `:646` | `disabled` + 「파라미터 설정 (잠김)」(버튼은 top-level 유지 — 1-B) |
| dashboard 설정 History 복원 | `pages/settings_history.py:476-485` | 복원 단추 `disabled`(보기는 열림) |
| dashboard 시스템 초기화 | `:2467`, `pages/confirm_init_db.py:51` | `disabled` |
| dashboard 설정(조건 화면 이동) | `:2601` | 이동은 열림, 이동한 화면에서 저장 잠김 |
| 열림 | 강제 매수·강제 매도·엔진 정지·보기·감사 로그 뷰어 | 그대로(요청서 6-나·7절) |

**강제 매도:** 종목 = PULLBACK 종목. 체결 뒤 분할 상태 정리(엔진이 다음 봉 지갑 0 확인 → `reset_after_exit`, T12 표). `UpbitTrader(…, strategy_type="PULLBACK")`(T7).

**구버전 강제 매수(열림, D7):** 종목 = PULLBACK 종목. 금액 = 지금 규칙 그대로 `risk_pct × 현재 KRW`(`services/trading_control.py:195`)이고, `risk_pct = params_obj.order_ratio = 1 / effMaxSplits`(T2 채우기 규칙). 주문 방식 = 시장가(PULLBACK 은 조건 파일이 없어 `_load_force_buy_conditions` 가 빈 dict → `fixed_price_mode` 거짓, `services/trading_control.py:287-292`). 단추는 지금처럼 코인 평가액 5,000원 미만일 때만 주문한다(X4). 체결분은 D11(b) 규칙으로 엔진이 관리한다(지갑 평단 기준 TP/SL·데드크로스, `[PULLBACK-SYNC]` 로 추가 분할매수 멈춤, 팔리면 정상 상태). 화면 확인 문구 「구버전 강제 매수는 새 전략 회차 밖 매수입니다(추가 분할매수가 멈춥니다)」 — 신버전 강제 매수(D6)와 다름을 보인다.

**D10(로그인 화면의 두 검증 경로 — X14):** 자동 검증 `services/auto_verify.run_live_auto_verify` 의 `save_user(user_id, name, krw_balance)`(84)와 수동 계정 검증 `app.py:386-394` 의 `st.session_state.virtual_krw = krw_balance`·`save_user(username, name, krw_balance)` 두 곳 모두 그 전에 `lock_state` 를 본다(R6). TEST 운용자산 직접 입력(`app.py:517-521`)은 TEST 모드 사용자가 금액을 직접 정하는 것이라 막지 않는다(1-1 결과로 다시 확인). **새 전략이 보유 중(`pullback_state.qty>0`)이거나 예약 중이면** `virtual_krw` 를 덮어쓰지 않고 `display_name` 만 갱신한다(`UPDATE users SET display_name=?, updated_at=?`). 미보유면 지금처럼 원화 잔고로 갱신한다. 화면 문구(`app.py:328-335`): 보유·예약 중이면 「운용자산: x KRW (새 전략 거래 중이라 그대로 둡니다)」. 엔진의 회당 금액은 1회차 때 운용자산을 읽어 그 거래 동안 고정(T5·T6).

**UI 1-A 브리핑 목록(보고에 그대로):** 추가 = 배지 1·상태 보기 1·확인 문구 1. 잠김(보이지만 누를 수 없음) = 위 표 9곳. 사라짐·이동·접힘 = 0.

- [ ] **Step 1: 실패 시험**
  - `test_old_dashboard_no_stop_on_pullback`: 활성 PULLBACK·PULLBACK 파일 형식 → `st.stop` 0(AppTest 또는 mock).
  - `test_old_dashboard_badge_pullback`, `test_old_dashboard_status_round`("2 / 5회").
  - 잠금 9개(위 표 앞 9줄과 1:1): `test_old_ui_locks_set_config_strategy_select`, `test_old_ui_locks_set_config_save`, `test_old_ui_locks_set_config_engine_start`, `test_old_ui_locks_conditions_save`, `test_old_ui_locks_dashboard_engine_start`, `test_old_ui_locks_dashboard_auto_resume`, `test_old_ui_locks_dashboard_param_setting`, `test_old_ui_locks_history_restore`, `test_old_ui_locks_system_reset`. 그리고 `test_old_ui_locked_while_reserved`, `test_old_settings_nav_open`(설정 이동은 열림).
  - `test_old_force_sell_pullback_ticker`, `test_old_engine_stop_open`.
  - `test_old_force_buy_pullback_ticker`: 종목 PULLBACK, risk_pct 0.2(maxSplits 5), `buy_limit` 0, trader `strategy_type="PULLBACK"`.
  - `test_auto_verify_keeps_capital_while_pullback_holding`, `test_auto_verify_keeps_capital_while_reserved`, `test_auto_verify_updates_capital_when_flat`, `test_auto_verify_ema_unchanged`, `test_manual_verify_keeps_capital_while_pullback_holding`(`app.py:394` 경로).
  - `test_login_routes_pullback_to_dashboard`(`app.py:540`).
  - 1-B: `test_whitelist_buttons_top_level`(강제 매수·매도·감사로그 뷰어·설정 이동이 `st.expander` 밖), `test_audit_viewer_button_top_level_pullback`(기존 `test_button_in_header_column_context` 와 같은 단언을 PULLBACK 표시 경로에서).
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트(`regression_gate.sh` 의 UI import·typing 게이트 포함).
- [ ] **Step 5: UI diff 브리핑 준비 → 커밋 승인 요청** — `app.py`·`pages/*.py` 변경은 tradebot 재시작 대상.

### T16: 신버전 화면 2차 채움 — 문구 표

**Files:**
- Modify `v2/api_read.py`(assets `round`·tp/sl, trades 회차, logs PULLBACK 줄·`strategy_switch` 합치기, markers), `v2/static/app.js`, `v2/static/index.html`, `v2/static/chart.js`, `v2/static/labels.js`·`REASON_LABELS`(`GOLDEN`·`PULLBACK` 은 이미 있음 — `v2/static/labels.js:7-8`; `FORCE` 는 더함, 서버 표와 같은지 기존 시험), `v2/static/save.js`
- Test: `tests/v2/test_api_read.py`, `tests/v2/js/home.test.mjs`, `tests/v2/js/chart.test.mjs`, `tests/v2/js/logs.test.mjs`, `tests/v2/js/save.test.mjs`

**문구 표:**

| 화면 | 요소 | 조건 | 문구·값 |
|---|---|---|---|
| 홈 2-가 | 전략 배지 | PULLBACK | 「전략: 눌림목 분할매수」 |
| 홈 | 전환 예약 배지 | 예약 있음 | 「전환 예약 중」(노랑) |
| 홈 | 분할 회차 | PULLBACK 보유 | 「n / 최대회」(예 「2 / 5회」). EMA/MACD 는 「—」 |
| 홈 | 익절 가격 | PULLBACK 보유 | 「익절 가격 (+tp%)」 = 평단 × (1 + tp/100), 원 단위 |
| 홈 | 손절 가격 | PULLBACK 보유 | 「손절 가격 (−sl%)」 = 평단 × (1 − sl/100) |
| 홈 | 최신 신호 | 미보유·비활성 | 「매수 대기 — 감시 구간 아님 (<골든 아님|기울기 미달|기울기 둔화>)」 |
| 홈 | 최신 신호 | 활성·armed 아님 | 「매수 대기 — 가격이 60선 위. 60선 아래로 내려왔다가 다시 위에서 마감하면 n회차 매수」 |
| 홈 | 최신 신호 | armed | 「눌림 대기 중 — 가격이 60선 아래로 내려옴. 다시 위에서 마감하면 n회차 매수」 |
| 홈 | 최신 신호 | 회차 다 참 | 「보유 유지 — 분할 n / n회 모두 매수함. 익절·손절 가격 안」 |
| 홈 | 최신 신호 | 어긋남(`desync`) | 「보유 유지 — 앱 주문이 섞여 추가 매수를 멈췄습니다. 익절·손절은 그대로」 |
| 홈 | 최신 신호 | 예약 중 | 「전환 예약 중 — 추가 매수 안 함」 |
| 홈 | 최근 거래 구분 | PULLBACK 매수 | 「매수 n회」 + 사유 「골든크로스」·「눌림목」 |
| 차트 2-나 | 선 | PULLBACK | 적용본 `ma60p`·`ma200p`·`maType` 으로 계산(범례 「— <ma60p>선 · — <ma200p>선」). EMA/MACD 는 지금 60·200 |
| 차트 | 표시 | — | 회차 매수마다 ▲, 매도 ▼ |
| 로그 2-라 | 대기 | armed | 「매수 대기 — 눌림 상태, n회차 준비」 |
| 로그 | 체결 | PULLBACK 매수 | 「매수 체결 n회차 · 눌림목 · 평단 x」, 1회차 골든 「매수 체결 1회차 · 골든크로스」 |
| 로그 | 사건 | golden_event | 「골든크로스 발생 (60선 > 200선)」 |
| 로그 | 전환 | `strategy_switch` `kind IN ('SWITCH','REVERT')` | SWITCH DONE 「전략 전환 완료 → 눌림목 분할매수」, REVERT DONE 「기존 전략으로 복귀 → EMA」, RESERVED 「전환 예약」, CANCELED 「전환 예약 취소」, FAILED 「전략 전환 실패 — 기존 전략으로 계속」 |
| 로그 | 설정 적용 | `strategy_switch` `kind='PARAMS'`(결정 13-8) | 「설정 적용 · <바뀐 키 한글, 예 익절 TP 5→4%> · <다음 봉부터|즉시|다시 시드|예약 전환>」 — 「전략 전환 완료」로 보이지 않음 |
| 로그 | 매도 | 체결 | 「매도 체결 · 익절」(손절·데드크로스) |
| 로그 | 건너뜀 | `split_krw_short` | 「매수 건너뜀 — 원화 잔고 부족」, `split_below_min` 「매수 건너뜀 — 최소 주문금액 미만」 |
| 저장 확인 창 | 단추 | 업비트 | 「이 설정으로 동작」 활성, 안내 「「이 설정으로 동작」→ 전환 확인(6절)으로 넘어갑니다.」 |
| 저장 확인 창 | 단추 | 바이낸스 | 「이 설정으로 동작 (사용 불가)」 + 참고용 문구(1차 그대로) |

- 「60선」 글자는 `ma60p` 값으로 바꿔 쓴다(예 50 이면 「50선」). 그림 기본값이 60·200 이라 기본은 그림과 같다.

- [ ] **Step 1: 실패 시험** — `test_assets_round_from_pullback_state`, `test_assets_tp_sl_from_pullback_params`, `test_trades_include_round`, `test_markers_include_split_buys`, `test_logs_pullback_wait_line`, `test_logs_split_buy_lines`, `test_logs_golden_event_line`, `test_logs_switch_done_line`, `test_logs_params_row_not_switch`(3회째: PARAMS 행 → 「설정 적용 · 익절 TP 5→4% · 즉시」, 「전략 전환 완료」 0), `test_logs_switch_kinds_states`(SWITCH/REVERT × DONE/RESERVED/CANCELED/FAILED 문구), `test_logs_skip_krw_short_line`, `test_queries_all_have_limit`(새 SQL 포함), `test_queries_use_index`(`strategy_switch` 조회 인덱스); JS — 「PULLBACK 배지」, 「분할 회차 n / 최대회」, 「익절·손절 가격」, 「PULLBACK 신호 문장 6종」, 「거래 구분 회차」, 「전환 예약 배지」, 「PULLBACK MA 설정으로 선」.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과.
- [ ] **Step 5: 브라우저 실측(로컬 dev 서버, 412·360·1440)** — 그림 2-가·2-나·2-라·2-마·5-가와 나란히 둔 대조표.
- [ ] **Step 6: 커밋 승인 요청**

### T17: TEST/LIVE 분리 (결정 D4)

**Files:** Modify ★ `services/pullback_state.py`, `engine/strategy_switch.py`, `engine/control_requests.py`, `v2/control.py`; Test `tests/regressions/test_r_2026_10_28_p4_t17_mode.py`

**규칙:** 분할 상태·예약·요청에 모드 칸(T6·T12 테이블의 `mode`, 요청 본문 `mode`). 설정 파일(저장본·적용본)은 하나. v2 spec 4.5 의 `_dry_` 접두사 규칙은 코드에 없으므로 쓰지 않는다(문서 정정). 요청 모드는 신버전 세션의 입장 모드. 엔진은 요청 모드와 실행 중 모드가 다르면 `mode_conflict`.

- [ ] **Step 1: 실패 시험** — `test_state_separated_by_mode`(TEST 상태가 LIVE 복원에 안 섞임), `test_reservation_separated_by_mode`, `test_request_mode_must_match_running`.
- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과·게이트.
- [ ] **Step 5: 커밋 승인 요청**

### T18: 서버 점검 스크립트 항목 추가

**Files:** Modify `scripts/v2/check_v2_unit.sh`, `scripts/v2/check_v2_unit_probe.py`; Test `tests/v2/test_deploy_files.py`

**추가 항목(출력은 `PASS|FAIL|RESIDUAL <항목>` 만, 값 미출력):**
- `v2-control-dir-700`: `services/data/v2_control` 와 사용자 폴더 700·root.
- `v2-control-files-600`: 요청·결과 파일 600.
- `applied-600`: 적용본·사본 600.
- `applied-not-writable-by-v2`: 유닛 안에서 적용본 쓰기 열기 실패(EROFS 기대). 파일 내용은 열지 않는다(`os.access` 와 `open(…, "r+")` 시도만, 실패 기대).
- `saved-writable-by-v2`: 저장본 쓰기 가능(지금 항목 유지).
- 유닛 `ReadWritePaths` 는 바뀌지 않는다(D3·D9 권고안). 확인 줄 `unit-rw-paths-unchanged`.

- [ ] **Step 1~4:** 실패 시험(`test_check_script_has_phase2_items`, `test_check_script_outputs_status_only`) → 구현 → 통과.
- [ ] **Step 5: 커밋 승인 요청** — 스크립트 실행은 배포 때(사용자 확인 후).
- [ ] **Step 6: P4 최종 검증** — `bash scripts/regression_gate.sh`, `node --test tests/v2/js/*.test.mjs`, 로컬 dev 서버 + 로컬 Streamlit 으로 전환·예약·복귀·강제 매도 흐름을 TEST 가짜 계정으로 실측 → verifier → Fable → 구현 완료 보고(번들 zip, 「버전: 구 → 신」, UI diff 브리핑).

---

## 8. 마이그레이션 설계 요약 (T6·T7·T12)

| 변경 | 함수 | 대상 | 되돌리기(코드 revert) 때 |
|---|---|---|---|
| `pullback_state` 신설 | `ensure_pullback_tables` | 실매매 DB 사용자별 | 옛 코드는 이 테이블을 읽지 않음 — 무해 |
| `strategy_switch` 신설(X1) | 같은 함수 | 같음 | 무해 |
| `schema_marks` 신설(X1) | `ensure_trade_strategy_columns` | 같음 | 무해 |
| `audit_trades.strategy_type` 칸 | 같은 함수 | 같음 | 옛 `insert_trade_audit` 는 칸 목록을 직접 적으므로(`services/db.py:1499-1503`) NULL 로 들어감 — 무해 |
| `orders.strategy_type` 칸 | 같은 함수 | 같음 | 옛 `insert_order` 같음 — 무해 |

- 호출 위치: `ensure_all_schemas`(`services/init_db.py:1003-1023`) 맨 끝 두 줄. 서버는 엔진 기동 때(`engine/boot_resume.py:126-135`) 먼저 실행된다.
- **B7 무손실 시험(배포 전, 사용자 확인 후 1회):** 운영 DB 사본(서버에서 `sqlite3 … ".backup /root/backup/tradebot_mcmax33_<날짜>.db"` 로 만든 백업 파일을 로컬로 복사 — 원본 DB 는 열지 않음, 「승인 받은 뒤 1회」)에 `ensure_all_schemas` 2회 → 테이블별 행 수·마지막 id·`PRAGMA integrity_check`·`PRAGMA foreign_key_check` 가 전후 같음, 새 칸 NULL·표식 = 테이블별 MAX(id). 스크립트 `scripts/v2/migration_dryrun.py`(파일로 작성, 출력은 테이블 이름·수만).
- **되돌리기 무해성 시험**(`test_revert_old_code_ignores_new_schema`): 마이그레이션한 DB 에 지금(배포 전) 코드의 `insert_order`·`insert_trade_audit`·`fetch_trades_for_snapshot` 를 돌림 → 오류 0, 결과가 마이그레이션 전과 같음. 1차 선례 WO-9 「열 추가만 하므로 revert 후 구 코드는 이 열을 무시」(`services/init_db.py:991-993`).

---

## 9. 문서 (T1~T18 뒤, 사용자 승인 후 spec 반영)

- pullback spec 정정:
  - 100행 「대시보드 spec 4.5와 같은 형식」 뒤에 저장본/적용본 분리(D9) 한 줄.
  - 110·111행: 값 범위·다시 읽기는 「적용본 mtime 감시(새 경로)」로.
  - 121행 빈 봉: 「엔진은 무거래 봉을 건너뛴다(`fill_gaps_sync` 미사용). 백테스터 업비트 출처·fixture 도 채우지 않는다. 예외: EMA 기준선 간격 모드만 직전 종가로 채움」.
  - 4.5 160행 「그대로 적용하는 기존 장치: 거래 시간 제한 설정」 → 「PULLBACK 에서 새로 구현(D5), 기존 엔진은 미사용」.
  - 4.7 189행 `_dry_` → 「모드 칸(D4)」.
  - 4.6 171행 「변경 사실과 적용 시점을 `audit_settings` 에 남긴다」 → 「`strategy_switch`(kind `PARAMS`)에 남긴다(결정 13-8)」.
  - 7.1 운용자산 → D10(1회차 때 읽어 거래 동안 고정, 보유·예약 중 로그인 덮어쓰기 안 함).
  - (결정 13-4 가 (가) 이면) 3절 85행 「실엔진도 시작 직후에는 사지 않고 다음 골든크로스를 기다린다」 → 「골든크로스 1차 매수는 다음 골든크로스를 기다리고, 감시 구간이면 눌림목 1회차는 바로 살 수 있다(원본 352행)」.
- v2 spec 4.5: 177행 `_dry_` → 모드 칸, 「저장만 하기/이 설정으로 동작」에 저장본·적용본 분리, 4.7 에 요청 통로(D3) 확정 내용, 7절 A7~A11·A16·A18·A19 개정(아래 수용 기준).
- 결정 D1~D12 를 두 spec 의 결정 표에 날짜와 함께 적는다.
- `docs/operations/v2-runbook.md`: 요청 통로 폴더·결과 파일, 적용본·사본, 운영자 대행 복귀 절차(되돌리기 ②), 분류 불명 경고 대응.
- `docs/operations/terminology.md`: T8 용어.
- 운영자 백로그: EMA 거래 시간 제한 미동작(F5, D5·D12).

---

## 10. 배포 절 (P3+P4 한 번에 — 별도 승인 요청서의 순서, 이 계획의 Task 아님)

1. **정지선** — 3절과 같음. `git diff --stat 1747fcc <배포 HEAD>` 파일 목록을 승인 요청서에 싣는다(★ 엔진 파일 표시).
2. **배포 전**
   - 서버 DB 백업(스키마 변경): `sqlite3 services/data/tradebot_mcmax33.db ".backup /root/backup/tradebot_mcmax33_<YYYYMMDD>.db"` → `chmod 600`. (사용자 확인 후)
   - 운영 DB 사본 마이그레이션 무손실(B7, integrity_check) — 8절.
   - 지갑·엔진 미보유 확인(JTO 등): journal 의 마지막 `[POSITION-SYNC]`·`HTS_SELL` 과 업비트 앱 지갑(운영자 확인). 보유 중이면 배포는 하되 재시작 조건(아래 3)을 지킨다.
   - 승인 범위에 적을 것: 실매매 DB 스키마 변경(테이블 3·칸 2), tradebot 재시작 1회, tradebot-v2 재시작 1회, 점검 스크립트 실행, 유닛 변경 없음.
   - project-rules 「배포 전 확인」(R8, 사용자 확인 후 — SSH 읽기 전용):
     - 로그 레벨: `ssh … "grep -rn 'level=logging' /root/upbit-tradebot-mvp/scripts/tradebot_boot.py"`(INFO — `scripts/tradebot_boot.py:139-144`), 새 로그(`[PULLBACK-*]`·`[CONTROL]`)가 INFO 이하가 기본인지 코드로 확인.
     - systemd 자동 재시작: `ssh … "systemctl show tradebot -p Restart,RestartSec"`·`ssh … "systemctl show tradebot-v2 -p Restart,RestartSec,StartLimitBurst"`.
     - 비밀 파일 권한(정기 점검): `ssh … "ls -l /root/upbit-tradebot-mvp/.env /root/upbit-tradebot-mvp/.streamlit/secrets.toml /root/upbit-tradebot-mvp/.v2_secret /root/upbit-tradebot-mvp/.v2_allowlist"`(모두 600·root, 사본 없음), `server.enableStaticServing=False` 확인.
     - 감사 로그 백업(*.db) 존재 확인(위 백업).
3. **실행**
   - `git pull` → `tradebot` 재시작 1회(입장 단추 1027-04 반영 포함). 조건: 현재 봉 `✅ [CONFIRMED] 봉 처리 완료` 또는 `[CONFIRMED-NO-TRADE]` 확인, `orders` 미체결(`REQUESTED`·`PARTIALLY_FILLED`) 0(journal `[RECONCILER]` 로 확인 — DB 직접 조회는 「승인 받은 뒤 1회」), 다음 봉 경계까지 60초 이상.
   - `tradebot-v2` 재시작.
   - 확인: `[BOOT-RESUME] success`, `[migrate]` OK 줄, 워밍업 `[WARMUP] REST 데이터 로드 완료`, 확정 봉 누락 0(NO-TRADE 제외), `journalctl -u tradebot` 429·418 0, `journalctl -u tradebot-v2` `status=429` 0, 활성 전략 파일 `EMA` 그대로 → 전환 전까지 매매 무변경(`[CONFIG]`·`EMA_GC` 판정 줄이 배포 전과 같은 형식).
   - `check_v2_unit.sh mcmax33`(T18 항목 포함, 사용자 확인 후).
   - 3점 일치: 로컬·서버 HEAD·`dashboard.py` 버전, `ExecMainStartTimestamp`. 보고에 「버전: 구 → 신」.
4. **관찰** — 30분(첫 봉 10개: 판정 줄·429·418·누락) + 24시간(엔진 「응답 없음」 4종 건수 배포 전후 비교, 1차 Task 9 Step 6 (a)와 같은 출처). 출처는 `journalctl -u tradebot`·`journalctl -u tradebot-v2`.
5. **첫 전환은 운영자 입회 권고** — 투자자가 누를 때 운영자가 journal 을 함께 본다(`[PULLBACK-PARAMS] source=applied`, `[CONTROL] switch done`, 워밍업 봉 수 = `required_bars`+1, 첫 판정 줄).
6. **브라우저 실측(1-A 3층)** — 운영자에게 신버전·구버전 새로고침을 요청해 운용 탭 단추·구버전 배지·잠김 글자를 확인받는다.
7. **되돌리기(순서 고정)**
   - ① 새 전략 미보유 확인(지갑) 또는 운영자 수동 청산.
   - ② 활성 전략 파일을 `EMA`(직전 전략)로: 신버전 복귀 단추, 또는 신버전을 닫아야 할 때는 운영자가 `echo EMA > mcmax33_active_strategy.txt` 대신 파일 도구로 쓰고 `tradebot` 재시작(투자자 복귀 경로를 운영자가 대신 수행).
   - ③ 순서 고정(T7 수정 1회차): `systemctl stop tradebot` → DB 백업(배포 절 2 와 같은 명령) → `python3 scripts/v2/mark_revert.py mcmax33`(테이블별 MAX(id) 를 `schema_marks` 의 `…revert_from` 로 기록 — T7 D2, 종료 코드 0 확인, 3·4·1 이면 멈추고 T7 메모 ④ 절차) → 코드 `git revert` → `systemctl start tradebot` → `tradebot-v2` 재시작(3과 같은 점검). 정지 뒤에 기록하는 까닭: 새 코드가 떠 있는 동안 쓰인 행·화면 렌더가 구간 경계를 흐리지 않게. 구간을 닫는 `revert_to` 는 재배포 때 엔진 기동 마이그레이션만 적는다. **`mark_revert.py` 는 운영 DB 쓰기 1회(`schema_marks` 행 2개)라 되돌리기 승인 범위에 함께 적고 사용자 확인 후 실행한다(2회째 8).**
   - 새 테이블·칸은 남긴다(8절 무해성 시험).
8. **투자자 통보 문안 B**(별도 승인, 배포 날 1회) → `docs/operations/investor-notice-log.md` 1줄. Fable 번들 zip.

### 투자자 통보 문안 B 초안 (2차 공개)

> 투자자님, 신버전 대시보드 2차 공개를 오늘 마쳤습니다.
>
> 이제 신버전 운용 메뉴에서 「백테스터 규칙으로 전환」, 「기존 전략으로 복귀」, 「예약 취소」, 그리고 설정 저장 창의 「이 설정으로 동작」을 쓰실 수 있습니다. 승인 요청서 6절의 규칙(보유 중이면 기존 방식으로 판 뒤 전환)대로 동작합니다.
>
> 지금 매매 방식은 바뀌지 않았습니다. 투자자님이 전환을 확인하실 때만 새 전략 「눌림목 분할매수」가 시작됩니다.
>
> 승인 요청서와 다르게 정한 점이 세 가지 있습니다.
> - 새 전략으로 코인을 보유 중이거나 전환 예약 중일 때는, 로그인해도(자동·수동 계정 검증 모두) 운용자산이 바뀌지 않습니다. 1회 매수 금액(운용자산 ÷ 최대 횟수)이 거래 도중 바뀌지 않게 하기 위해서입니다. 보유가 없을 때는 지금처럼 로그인 때 원화 잔고로 다시 정해집니다.
> - 승인 요청서 3절에는 「켠 직후 이미 골든크로스 상태여도 다음 골든크로스를 기다린다」고 적었습니다. 백테스터를 다시 확인해 보니, 골든크로스 순간의 1차 매수는 그렇게 기다리지만, 60선이 200선 위에 있고 200선이 오르는 감시 구간이면 켠 직후에도 「가격이 60선 아래로 내려왔다가 다시 위에서 마감할 때」 1회차를 살 수 있습니다. 실제 매매도 백테스터와 똑같이 동작합니다. *(결정 13-4 가, 1027-17)*
> - 승인 요청서 8절에는 「1분봉이면 판정이 최대 1분 늦을 수 있다」고 적었습니다. 업비트에서 확정된 봉을 받지 못하는 드문 경우에는 그 봉을 판정에 쓰지 않으므로, 익절·손절 판정이 다음 확정 봉까지 더 늦어질 수 있습니다. *(결정 13-5 가·13-5b 넣음, 1027-17)*
>
> 새 전략 운용 중이거나 전환 예약 중에 기존 대시보드를 여시면 설정 저장·전략 변경·엔진 시작이 잠깁니다. 같은 효과를 내는 「파라미터 설정」·「설정 History 복원」·「시스템 초기화」와 자동 재개도 함께 잠깁니다. 강제 매수·매도, 엔진 정지, 감사 로그는 그대로 쓰실 수 있습니다. 기존 대시보드의 「강제 매수」는 새 전략의 회차 밖 매수로 다루어, 그 뒤 새 전략의 추가 분할매수가 멈추고 익절·손절만 적용됩니다(신버전 운용 메뉴의 「강제 매수」는 회차 1회로 셉니다).
>
> 투자자님이 따로 하실 일은 없습니다.

(D7·D11(b) 는 권고안이다. 잠금 범위와 구버전 강제 매수 처리는 요청서 7절 「강제 매수·매도 그대로」 범위 안이지만 투자자가 보는 동작이라 문안에 적었다(R9). 사용자가 다른 안을 고르면 이 자리를 고친다.)

---

## 11. 수용 기준

### pullback spec 8절

| # | 기준 | 확인 | Task | 담당 |
|---|---|---|---|---|
| B1 | 일치 시험(6절) 전 조합 통과 | `test_parity_*` 27개 | T10 | tester |
| B2 | 재시작·BACKFILL 시험 통과 | `test_restart_*`, `test_backfill_no_orders_no_contamination` | T6, T10 | tester |
| B3 | EMA·MACD 판정 무변경 | `regression_gate.sh` 전부, `test_ema_still_blocks_already_holding`, `test_ema_ignores_trading_hours` | 전체 | tester |
| B4 | 전환 예약 → 청산 후 전환, 재시작 뒤 예약 유지 | T12 시험 | T12 | tester |
| B5 | 기존 보호 장치가 PULLBACK 에서 동작 | `test_pullback_pause_blocks_orders`, `test_pullback_hts_buy_sync`, `test_split_skip_below_min`, `test_pullback_sell_reject_visible`(T5 새 시험 — SELL 거절이 `*_REJECTED` 행·알림으로 남음) | T5, T6 | tester |
| B6 | 감사 로그 새 칸·화면 용어 | T8 시험 + 감사 뷰어 실측 + 용어 운영자 확인 | T8, T16 | tester |
| B7 | 마이그레이션 무손실 | 운영 DB 사본 `migration_dryrun.py` | 8절, 배포 2 | db |

### v2 spec 7절 (개정 포함)

| # | 기준(개정) | 확인 | Task |
|---|---|---|---|
| A7 | 저장 시 저장본·이력·확인 창 동작. **(개정) 「저장만 하기」는 적용본·엔진 값·신버전 읽기(종목·봉 경계 창·미리 받기)를 바꾸지 않고, 「이 설정으로 동작」은 업비트 출처에서만 열림** | T13 시험 + 로컬 실측 | T13 |
| A8 | 입장만으로 전략이 바뀌지 않음(D1) | `test_entry_does_not_switch`(입장·화면 읽기만으로 요청 파일 0, 활성 파일 불변) | T11, T14 |
| A9 | 보유 중 전환이 「전환 예약」 → 청산 후 전환(D2) | T12 시험 | T12 |
| A10 | PULLBACK·예약 중 구버전 설정 저장·전략 변경·엔진 시작(같은 효과 경로 포함) 차단, 강제 매수·매도·엔진 정지 가능(D3·D7) | T15 시험 + 실측 | T15 |
| A11 | 신버전 엔진 제어 요청이 엔진 프로세스 안에서만 실행(신버전 프로세스 엔진 스레드 0), 구버전 동작 무변경 | T11 시험 + 회귀 + WO-12 시험 | T11 |
| A16 | 없는 user_id 로 DB 파일 미생성, 신버전은 EMA·MACD 파일 불변. **(개정) 신버전은 적용본·사본을 쓸 수 없음(유닛), 요청 폴더 밖에 쓰지 않음** | 기존 시험 + `applied-not-writable-by-v2` | T13, T18 |
| A18 | 구버전 설정 이력·복원·현재 전략 추정이 전후로 같음. **(개정) PULLBACK·분류 불명 행 제외, EMA 행은 모든 경로에서 EMA 로 기록되어 보임** | `test_a18_history_same_before_after`, `test_ema_rows_tagged_all_paths` | T7 |
| A19 | 신버전의 실매매 DB 쓰기는 `v2.db.set_paused` 한 함수뿐. **(개정) 2차에서도 신버전은 실매매 DB 에 새로 쓰지 않음 — 제어는 요청 파일, 예약 상태는 엔진이 씀** | 기존 lint 유지(`set_paused` 외 쓰기 0) | T11~T16 |

### 실매매 영향 축별 표

| 축 | 바뀌는 것 | 위험 | 막는 장치 | 확인 |
|---|---|---|---|---|
| 외부 한도(업비트) | PULLBACK 워밍업 최대 약 11회(D8), 전환·적용 때 엔진 재시작 1회 = 워밍업 1회 | 신버전 수집과 겹쳐 429 | 신버전 봉 경계 창·초당 4회·429 멈춤(그대로), 세대 값으로 엔진 재시작 쉼(T11), 1-4 재확인 | 배포 관찰 429·418 0 |
| 프로세스 | tradebot 안 감시 스레드 1개 추가(2초), 신버전은 파일만 씀 | 스레드 예외가 엔진에 번짐, 두 번째 엔진 | 예외 격리, 한 번에 하나, `get_running_mode` 검사, 신버전 엔진 import 0 | `test_control_thread_exception_isolated`, A11 |
| 수명주기 | 전환·복귀·적용(MA·봉 단위)·엔진 시작/정지가 엔진 재시작을 부름 | 재시작 중 봉 누락, 미체결 주문 고아, 옛 스레드가 남은 채 두 번째 엔진(F7), 실서버 재시드로 EMA 시드 시작점이 달라 경계 판정이 원본과 어긋남(F16) | `restart_engine`(옛 스레드 종료 확인 뒤 시작), 미체결 매수 있으면 예약(F8), 기동 실패 되돌림(F9), reconciler 재개(WO-12 경로 재사용) | 재시작 시험·`test_restart_recent_window_diff_recorded`, 배포 뒤 재시작 직후 첫 판정을 백테스터와 비교(관찰), 첫 전환 입회 |
| 데이터 | 실매매 DB 테이블 3·칸 2, 적용본·사본 파일, 요청·결과 파일 | 마이그레이션 실패·손실, 분류 오류 | `_ensure_column`·한 트랜잭션·표식, B7 사본 시험, 되돌리기 무해성 | B7, `test_revert_old_code_ignores_new_schema` |
| 자격증명·권한 | 키를 읽는 곳 추가 없음. 신버전이 요청 파일로 엔진에 주문·전환·정지를 시킬 수 있게 됨 | (1) 신버전이 엔진 키에 닿음 (2) **신버전 프로세스가 침해되면 요청 파일만으로 강제 매수·매도·전환·엔진 정지를 일으킬 수 있음(S1, 남는 위험)** | (1) 신버전은 요청 파일만, 유닛 `InaccessiblePaths` 그대로, 엔진만 trader 사용 (2) 요청은 세션 user·입장 모드·60초 만료·한 번에 하나, 강제 매수 금액은 엔진이 정함(요청에 금액 없음), 요청 종류별 텔레그램 알림(T11), 운영자는 `systemctl stop tradebot-v2` 로 즉시 끊음 | A14·A17 기존 탐침, `test_request_notify_per_kind`, T18 폴더 권한 |

---

## 12. 계획서를 쓰며 확인하지 못한 것

1. 서버 실측(F17 JTO 미보유·F18 PULLBACK 0바이트·F21 엔진 UMask)은 목차 기재를 옮겼고 이 계획 작성 중 다시 보지 않았다(서버 접속 금지). 정지선 Step 2 에서 확인한다.
2. 1-2 무거래 봉 빈도·워밍업 시간·요청 수 — 아직 없다. D8 의 「약 11회」는 2,012 ÷ 200 계산값이다. 지난 기동(2026-10-26 00:25:30)은 count=801 1회 성공이었다(verifier 실측 인용).
3. 1-4 업비트 공식 한도 문서의 현재 내용 — 다시 읽지 않았다.
4. 업비트 fixture 3세트가 9개 조합 모두에서 사건(골든·눌림·매도)을 갖는지는 받아 봐야 안다.
5. 원본과 엔진의 EMA 부동소수가 모든 봉에서 비트 단위로 같은지 — 식 순서를 맞추면 같다고 보나, 비교에서 `==` 가 깨지면 판정 경계(예: `maTrend > ma200` 이 거의 같을 때)가 달라질 수 있다. T3 시험에서 확인한다.
6. BACKFILL 재생 중 「재생에서만 생긴 매수 신호」 뒤 armed 처리 — 계획은 원본처럼 armed 를 해제하고 주문은 내지 않는다고 적었다. spec 4.3 은 이 경우를 명시하지 않는다. T10 BACKFILL 시험에서 고정하고 보고에 적는다.
7. (1회째 검증 뒤 고침) 분할 체결과 HTS 판정의 경쟁 — 판정은 `has_recent_bot_buy_for_ticker`(30초)가 막는다(`engine/order_reconciler.py:776`). 체결 BUY 행이 HTS 감지 순회보다 늦게 쓰이는 순서가 실제로 생기는지는 실측하지 않았다(T6 `test_bot_split_buy_not_hts_30s` 로 순서를 고정해 시험).
8. 구버전 `pages/dashboard.py` 의 다른 `load_params` 호출(729 외)이 PULLBACK 파일 형식에서 깨지는 곳이 더 있는지 — 전수 grep 은 T15 Step 1 에서 한다.
9. `pages/set_config.py:412-429` 가 `virtual_krw` 를 DB 에 쓰는지(1-1 에서 확인).
10. 신버전 결과 파일을 엔진이 600 으로 만든 뒤 신버전(유닛 root·`ProtectHome=read-only`·`services/data` 쓰기 허용)이 읽고 지울 수 있는지 — 읽기는 되나 지우기는 엔진이 하므로 문제없다고 보았다. T18 점검 항목으로 서버에서 확인.
11. 엔진 재시작이 전환 때마다 생기므로, 하루 여러 번 적용(MA 변경)하면 업비트 요청이 늘어난다. 횟수 상한(예: 적용 요청 10분 1회)을 둘지 정하지 않았다(목차에 없음 — 범위를 늘리지 않음, 위험으로만 기록).
12. 목차 0-3 절이 말한 verifier 4회·Fable 기록은 이 계획 작성 중 다시 확인하지 않았다(목차와 `docs/fable/2026-10-27-phase2-outline-1.md` 를 근거로 함).
13. (1회째 검증 뒤 새로) reconciler 가 시장가 BUY 의 최종 상태를 늘 `FILLED` 또는 체결량 있는 `CANCELED` 로 남기는지 — 코드 주석(`engine/order_reconciler.py:502-503`)만 보았고 업비트 실제 응답은 확인하지 않았다. 분할 체결 콜백 조건(T6)이 이 가정에 기댄다.
14. 서버에 옛 공용 조건 파일 `{user}_buy_sell_conditions.json`(386B)이 있다는 것은 verifier 실측 인용이다. 다시 보지 않았다.
15. 엔진 스레드가 `stop_event` 를 받고 30초 안에 끝나는지(워밍업 REST 도중 등) — 실측하지 않았다. T11 `restart_engine` 대기 상한 30초는 추정값이다.
16. (2회째 뒤 해소) 변경 기록은 `audit_settings` 를 쓰지 않는다(결정 13-8). 남는 것: 1분 스냅샷이 PULLBACK 에서 `ts_pct`·`threshold` 를 None·0 으로 써도 구버전 감사 뷰어 화면이 깨지지 않는지는 화면으로 확인하지 않았다(T15 실측).
17. 결정 13-4 (가)를 고르면 요청서 3절·pullback spec 85행 문장과 실제 동작이 달라진다. spec 정정 문구는 결정 뒤 9절에 더한다.
18. (2회째 뒤 새로) 서버 EMA 조건 파일에 「현재가 매수(`fixed_price_buy_enabled`)」가 켜져 있는지 — 지적 1 교착이 지금 실제로 생길 수 있는 조건이다. **verifier 3회째 서버 실측(읽기 전용, 키 값만): `mcmax33_EMA_buy_sell_conditions.json` 의 `fixed_price_buy_enabled` = true** — 2회째 교착은 실제로 생길 수 있었다. 새 설계는 켜져 있어도 교착이 없다(T11 시험). 정지선에서 같은 값인지 다시 확인한다(키 이름과 참/거짓만).
19. 엔진 메인 루프(`engine/live_loop.py:1311`) 한 바퀴가 얼마나 걸리는지 — 제어 큐 대기 20초 안에 엔진 스레드가 큐를 꺼내는지는 실측하지 않았다. 워밍업·REST 재시도 중에는 넘길 수 있고, 그때는 `engine_busy` 로 끝난다(주문 없음).
20. `boot_resume` 완료 Event 를 새로 두는 것(T12 9번)이 WO-12 기동 재개 시험(`tests/regressions/test_r_2026_09_30_wo12_boot_resume.py`)을 바꾸지 않는지 — 함수 반환 뒤 Event 를 세우기만 하므로 무변경이라고 보았고 시험으로 확인한다.
21. `READY_WAIT_SEC=180` 은 추정값이다. 대기 시간 합은 약 45초다(바깥 재시도 2+4+8+16 = 30초 `engine/live_loop.py:1156-1159` + 안쪽 `safe_fetch_rest` 1+2초 × 5 = 15초 `core/rest_reconcile.py:417-420`, verifier 3회째). 네트워크 응답 시간은 이 합에 없다. 180초를 넘기면 즉시 전환이 실패하고 드물게 엔진 없음 + CRITICAL 이 된다(T11 알려진 한계 c — 미보유일 때만이라 자산 영향 없음).
22. (3회째) `RUN_MODE=LEGACY_LOCAL` 루프에서는 신버전 강제 매매가 늘 `engine_busy` 다(T11 알려진 한계 d). 서버가 `UPBIT_MATCH`(`config.py:110` 기본값)인지는 환경 변수를 보지 않았다 — 정지선에서 journal `[RUN_MODE]` 줄(`engine/live_loop.py:1108`)로 확인한다.

---

## 13. 사용자 결정 요청

결정 전까지 본문은 「권고」로 쓰고, 해당 곳에 「결정 13-n 에 따름」을 적었다. 권고는 verifier 1·2회째 권고안 기준이다(X2 는 보완안). 13-2·13-3 은 사용자가 이미 승인한 목차(결정 1027-16) 문구를 바꾸는 요청이고, 13-4·13-8 은 투자자 승인 요청서·확정 spec 문구와 관계된다.

| # | 무엇을 정하는지 | 권고 | 다른 선택지 | 고르면 달라지는 것 |
|---|---|---|---|---|
| 13-1 (X1) | 예약·전환 기록과 「옛 행 표식」을 어디에 둘지 — **⚠ 실매매 DB 스키마 변경 추가** | 실매매 DB 새 테이블 2개 `strategy_switch`·`schema_marks`(T7·T12) | `services/data/` 의 파일 2개(엔진이 600 으로 씀) | 권고: DB 백업·무결성 시험(B7)·트랜잭션 안에 들어감, 신버전 로그 탭이 SQL 로 읽음, 배포 승인 항목 +2. 다른 안: 스키마 변경은 T6·T7 만, 대신 파일 손상·백업 누락 위험과 별도 원자적 쓰기 코드 |
| 13-2 (X2) | 마지막 정상 사본을 무엇으로 둘지 — **⚠ 승인된 목차(결정 1027-16) T2 문구 변경 요청** | 보완안: 새 적용본을 쓰고 다시 읽어 검증한 뒤 **같은 내용을 사본에도 씀**(사본 = 마지막으로 검증된 적용본) | 목차 문구대로: 덮어쓰기 전 적용본을 사본으로 | 권고: 첫 적용 직후부터 사본이 있어 첫 거래 중 적용본이 깨져도 같은 설정으로 기동. 다른 안: 첫 적용 뒤 사본 없음 → 그때 깨지면 운영자 절차, 사본이 늘 「한 번 전 설정」이라 fallback 때 TP/SL 이 직전 값과 다를 수 있음 |
| 13-3 (X3) | 적용본 없음·깨짐 + 사본 정상 + **미보유**일 때 — **⚠ 승인된 목차(결정 1027-16) T2 문구 「미보유면 PULLBACK 기동 거부」의 해석 변경 요청** | 사본으로 기동 + CRITICAL 알림(T2 경우 5·7) | 미보유면 기동 거부 + 알림(사본은 보유 중에만 씀) | 권고: 엔진이 멈추지 않고 직전 정상 설정으로 매수까지 계속. 다른 안: 미보유 때는 운영자·투자자가 다시 적용할 때까지 새 매수 없음(더 보수적) |
| 13-4 (F3·X11) | 켠 직후(또는 전환 직후) 골든크로스 없이 눌림목 1회차를 살지 — **⚠ 투자자 승인 요청서 문장 변경: 요청서 3절(html 436행) 한 칸의 「다음 골든크로스를 기다립니다」와 「백테스터도 똑같이 동작합니다」가 서로 맞지 않아 어느 쪽을 골라도 한 문장이 바뀜. pullback spec 85행과 관계** | (가) 원본과 같게 — 감시 구간이면 눌림목 1회차 가능, 골든크로스 1차 매수만 다음 골든크로스를 기다림. 통보 문안 B 에 한 줄 | (나) 기동 뒤 첫 골든크로스 전에는 어떤 매수도 안 함(요청서 문장 그대로) | 가: 일치 시험(B1, spec 목표 G1)이 그대로 성립, 요청서 문장과 달라 문안 B 대상. **엔진 재시작(전환·설정 적용·엔진 시작) 직후에도 조건이 맞으면 바로 1회차 매수 가능.** 나: 요청서 문장 그대로, 대신 기동·재시작 직후 구간은 백테스터와 판정이 달라 일치 시험에서 그 구간을 빼야 함(G1 약화). **재시작마다 다음 골든크로스까지 매수 없음(상승 추세가 길면 며칠 동안 안 살 수 있음).** |
| 13-5 (F4·X12) | 확정 재시도가 다 실패해 들어오는 잠정 봉(O=H=L=C)을 PULLBACK 이 어떻게 다룰지 | (가) 지표·판정에 넣지 않음(NOOP), 확정값이 오면 그 봉부터 재생(주문 없음) | (나) 잠정 봉으로 판정(EMA 의 WO-2 옵션 C 처럼) | 가: 고가·저가가 없는 봉으로 TP/SL·눌림을 잘못 판정하지 않음. 대신 그 봉의 **매수 신호와 매도 신호(익절·손절·데드크로스) 모두** 놓친다 — 확정값이 와서 재생해도 주문은 내지 않으므로, 그 봉에서 손절 가격에 닿았다면 손절은 다음 확정 봉 판정(그 봉의 저가가 여전히 SL 이하일 때)까지 늦어진다. **이 경우 요청서 8절 3 「1분봉이면 판정이 최대 1분 늦을 수 있고」보다 더 늦을 수 있다(잠정 봉이 들어온 드문 경우) — 문안 B 에 넣을지 사용자 판단.** 나: 신호를 놓치지 않으나 O=H=L=C 라 TP/SL·armed 판정이 원본과 달라짐(고가·저가가 종가와 같아 TP/SL 이 덜 닿음) |
| 13-6 (F6) | 운용 설정(거래 시간 제한) 저장이 무엇을 적용할지 | (가) 거래 시간 4키만 지금 적용본에 합침(`ops_settings`) | (나) 저장본 전체를 적용(`apply_params` 재사용) | 가: 백테스터에서 「저장만 하기」한 값이 운용 설정 저장으로 몰래 적용되지 않음(D9 취지). 나: 코드는 단순하나 「저장만」한 TP·MA 등이 함께 적용됨 |
| 13-7 (T9) | 거래 시간 밖에 매수 조건이 맞은 경우의 armed·골든크로스 처리 | (가) 시간 밖에도 원본 규칙대로 armed 를 갱신하되 주문이 막힌 봉에서는 armed 유지 → 시간이 열린 첫 봉에 조건이 맞으면 매수. 시간 밖 골든크로스는 놓친 것으로 두고 다시 사지 않음 | (나) 시간 밖 매수 신호 봉에서 「매수한 것처럼」 armed 해제(원본 매수 직후와 같게), (다) 시간 밖 골든크로스를 시간이 열린 첫 봉에 사기 | 가: 시간이 열리면 바로 눌림 매수 기회, 골든 1차는 한 번 놓침. 나: 시간이 열린 뒤 새 눌림을 기다림(더 보수적). 다: 원본에 없는 「늦은 골든 매수」가 생김 — 백테스터에 없는 규칙이라 비목표에 걸림 |
| 13-8 (2회째 6) | 적용본 변경 기록(바뀐 키·적용 시점)을 어디에 남길지 — **⚠ pullback spec 4.6 「`audit_settings` 에 남긴다」 문구 변경 요청** | (가) 전용 기록: `strategy_switch` kind `PARAMS` 행(T13) + spec 4.6 정정(9절) | (나) `audit_settings` 에 쓰되 정기 스냅샷과 겹치지 않는 키(예: `bar_time` 을 `PARAMS:<KST ISO>` 로, `ticker` 는 그대로) | 가: 1분 정기 스냅샷 UPSERT(`services/db.py:1572-1605`)에 덮이지 않고, `fetch_latest_audit_settings`(`:1527`)가 변경 기록을 「엔진 적용 조건」으로 잘못 읽지 않음. 신버전 로그 탭이 전환 기록과 함께 보임. 나: spec 문구 그대로지만 `bar_time` 칸에 시각이 아닌 값이 들어가 그 표를 시각으로 읽는 곳(`fetch_latest_audit_settings` 의 정렬 등)이 어긋날 수 있음 |

- 13-4·13-5·13-7 은 일치 시험(B1) 범위에, 13-6·13-7 은 거래 시간 제한(D5, 기본 꺼짐)에 닿는다. 13-7 은 T5 의 「회차 건너뜀 뒤 armed 해제」(F12)와 다른 경우다(건너뜀 = 주문을 시도할 수 있었으나 돈이 모자람, 시간 밖 = 주문 자체가 막힘). 13-4 (가)·13-1·13-2 는 배포 승인 요청서와 통보 문안 B 에 그대로 옮긴다.
