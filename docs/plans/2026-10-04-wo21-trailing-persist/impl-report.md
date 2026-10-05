버전: v1.2026.10.02.2241 → v1.2026.10.04.1731

# WO-21 구현 보고 — 재시작 때 trailing 상태 재계산 + ts_armed 실제 값 (로컬 완료, 배포 대기)

- 작성: 2026-10-04 ~ 10-05 (KST)
- 코드 커밋: `770b104` (1건). 문서 커밋은 그 뒤 1건.
- 서버: 읽기만 했다 (HEAD `e97dec6`, 기동 2026-10-04 10:22:33 그대로). pull·재시작 없음. 투자자 안내 없음.
- 성격: **예방 조치** (보유 중 재시작 시 무장 상태 보존). 정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다 — 조사 보고 결론 3·B2 정정.
- 결정 사항·구현 조건 1~7: `plan.md`.

## 0. 착수 중 정지·정정 (운영자 결정 반영)

지시의 시험 (3) 기대값(09-30 19:44 재시작 → armed=True, peak 774, fixed 3)이 오염값임을 확인해 착수 전에 멈추고 보고했다.
- 09-30 16:47:09 매수(761) 뒤 실제 5분봉 종가 최고 762(+0.13%) → 당시 익절 기준(1.0%) 미도달 (`tests/regressions/fixtures/wo21_jto_5m_20260930.json`).
- 19:25 스냅샷 armed=1·peak 774 는 `2026-09-30 18:10:18 [BACKFILL] 누락 봉 평가 | ts=2026-09-29 18:50:00 KST | close=772` 직후 `Trailing Stop ACTIVATED … initial_highest=₩772` — 매수 전날 봉 재평가로 생긴 값 (`results/wo21_0930_arm.txt`).
- 운영자 결정 1번: (3) 을 "armed=False, peak 761, fixed·activation None" 으로 정정, 실데이터 C 추가, 조사 보고 결론 3·B2 정정, 성격을 예방 조치로.
- 추가 확인: 실데이터 A(10-02)·C(10-03)의 무장은 실시간 평가였다 — 두 구간 모두 BACKFILL 줄 0, 누락 봉 평가 0, 엔진 기동 0. A 무장 09:15:11(747, 고정폭 ₩13×30%), C 무장 18:55:11(722, 고정폭 ₩12×30%) (`results/legit-arming-check.txt`).

## 1. 변경 내용 (`impl/wo21-code.diff`)

| 파일 | 변경 | 조건 |
|---|---|---|
| `core/trailing_restore.py` (신규) | `restore_trailing_on_boot`: 마지막 BUY 시각부터 확정 봉(마감 > 매수 시각, 마감 ≤ 지금)을 골라 재생. 워밍업 봉 밖이면 REST 추가 조회(필요 봉 수 > 2000 이면 조회 없이 실패). 마지막 BUY 없음·평균가 없음·한도 초과·조회 실패·재생 예외 → 초기 상태 + WARNING `[TRAILING-RESTORE] 재계산 불가 → 초기화 \| 사유=…` 1줄. 성공 → INFO `[TRAILING-RESTORE] armed=… peak=… fixed=… activation=… 기준 봉 n개 시작=… (사유=…, 평균가=…, 추가 조회 n봉)` 1줄 | 1·2·3·5·7 |
| `core/filters/sell_filters.py` | `TrailingStopFilter.advance_state(position, price, log=True)` — evaluate STEP 1(무장·고정폭)·STEP 2(신고가)를 그대로 옮김. evaluate 는 이 함수를 호출한 뒤 STEP 3 판정 | 4 |
| `core/position_state.py` | `activate_trailing_stop(current_price, log=True)` — 로그 생략 인자만 | 4 |
| `services/db.py` | `get_last_open_buy_trade(user_id, ticker)` — 마지막 BUY 뒤 SELL 없을 때만 `{timestamp, reason, price}` | 1 |
| `engine/live_loop.py` | 형성 중 봉 제거 뒤 `_wu_full_df` 보관(시드가 200봉으로 자르기 전), 워밍업·`_boot_seed_recover_from_wallet` 직후 `engine.position.has_position` 이면 1회 호출 (봇 매수 boot_seed 경로는 워밍업 전 복원, 앱 매수 wallet_sync 경로는 워밍업 직후 복원 → 둘 다 이 지점 뒤, 첫 매도 평가 전) | 5 |
| `core/strategy_engine.py` | `ts_armed=bool(getattr(self.position, "trailing_armed", False))` 3곳 (1507 워밍업, 1855 HOLD, 1936 SELL). 감사 기록은 주문 실행 전이라 매도 봉에서도 무장 값이 남는다 | 6 |
| `pages/dashboard.py` | 버전 2241 → 1731 | — |

바꾸지 않은 것: 매수·매도 판정식, 필터 순서, 발주, 지표 경로. 재계산은 `highest_price`·`trailing_armed`·`trailing_fixed_amount`·`trailing_activation_price` 만 바꾼다 (`highest_since_entry` 무변경).

## 2. 회귀 시험 (`tests/regressions/test_r_2026_10_04_wo21_trailing_restore.py`, 8건)

봉 자료: Upbit 공개 캔들 조회 결과를 `tests/regressions/fixtures/wo21_jto_5m_20260930.json`(40봉)·`_20261002.json`(20봉)·`_20261003.json`(119봉)로 고정. `setUp` 이 실제 REST 함수를 "호출되면 실패" 로 막아 네트워크 비의존을 보장한다.

| # | 내용 | 새 코드 | 구 코드 (`129c6df`) |
|---|---|---|---|
| 1 | 합성 종가 7봉(무장 전 → 무장 → 하락 → 신고가 → 하락): 봉마다 실시간 경로와 재계산 상태 일치, 최종 (True, 103, 0.6, 102) | 통과 | 오류: 재계산 모듈 없음 |
| 2 | 실데이터 A 10-02: 09:10 봉까지 / 09:20 봉까지 → (True, 747, 3.9, 747) = 스냅샷 09:20:11·09:30:11 armed=1 peak 747, 로그 1줄 확인 | 통과 | 오류: 모듈 없음 (재시작 직후 상태 (False, 734, None, None) — §3) |
| 3 | 실데이터 B 09-30 19:44:28 → (False, 761, None, None), 기준 봉 35개. 매수 전 봉 미사용 고정. 19:25 스냅샷은 BACKFILL 오염값이라 재현하지 않음 | 통과 | 오류: 모듈 없음 (상태는 구 코드와 같음 — 정상) |
| 3-C | 실데이터 C 10-03: 18:50 봉까지 → (True, 722, 3.6, 722), 19:55 봉까지 → (True, 734, 3.6, 722) = 스냅샷 19:00:11·20:05:11. 전 구간 5분봉 | 통과 | 오류: 모듈 없음 (재시작 직후 (False, 710, None, None) — §3) |
| 4 | HTS_BUY_ADD 섞인 포지션: 추가 매수 뒤 3봉만 사용(앞의 110 무시), 평균가 105 유지 → 미무장 | 통과 | 오류: 모듈 없음 (기존 동작 고정 시험) |
| 5 | 워밍업 밖 시작점: REST 1회(total_count 24, end_ts 09:55) → (True, 747, 3.9, 747). 한도 초과(조회 없이)·조회 실패 → 초기화 + WARNING 정확히 1줄 | 통과 | 오류: 모듈 없음 |
| 6 | 끝의 형성 중 봉(종가 110) 제외 → 2봉·미무장, 마감 뒤면 3봉·무장 | 통과 | 오류: 모듈 없음 |
| 7 | `_record_audit_log` HOLD 2회: 미무장 → ts_armed False, 무장 → True | 통과 | **실패** `Lists differ: [False, False] != [False, True]` |

- 새 코드 출력: `impl/test-new-code.txt` (8건 OK, `.env` 없는 worktree).
- 구 코드 출력: `impl/test-old-code.txt` (`FAILED (failures=1, errors=7)`).

## 3. 구 코드 재시작 동작 재현 (`impl/gate-tests-oldsim-revert.txt` [C])

구 코드에는 재계산이 없으므로 재시작 복원(`apply_entry`) 직후 상태가 첫 매도 평가에 그대로 들어간다. `.env` 없는 `129c6df` worktree 에서 실데이터 A·C 의 네 시점을 재현했다:

| 시점 | 구 코드 재시작 직후 | 재시작 전 실제(스냅샷) | 새 코드 재계산 |
|---|---|---|---|
| A 09:20:11 (09:10 봉까지) | (False, 734, None, None) | (True, 747, 3.9, 747) | (True, 747, 3.9, 747) |
| A 09:30:11 (09:20 봉까지) | (False, 734, None, None) | (True, 747, 3.9, 747) | (True, 747, 3.9, 747) |
| C 19:00:11 (18:50 봉까지) | (False, 710, None, None) | (True, 722, 3.6, 722) | (True, 722, 3.6, 722) |
| C 20:05:11 (19:55 봉까지) | (False, 710, None, None) | (True, 734, 3.6, 722) | (True, 734, 3.6, 722) |

예: A 09:30:11 에 재시작했다면 구 코드는 그 봉(종가 742, 수익 1.09% < 1.5%)에서 미무장이라 실제로 나간 TRAILING_STOP_FIXED 매도가 나오지 않았다. 새 코드는 손절선 743.1 로 같은 매도를 낸다.

## 4. 관문과 단독 되돌리기 (`impl/gate-tests-oldsim-revert.txt` [A]·[D])

- 임시 worktree(`.env` 0개, 더미 키)에서 `770b104` 게이트: **290/290 통과** (WO-20 때 282 + 이번 8).
- `770b104` 단독 revert: **충돌 없음.** 11개 파일, py_compile 통과, 게이트 **282/282 통과**.

## 5. 문서 (문서 커밋)

- `plan.md` 신설: 조사 결론(예방 조치), 구현 조건 1~7, 구현 대응, 알려진 근사, 보류.
- `report.md`(조사 보고) 정정: 결론 3·B2 — "정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다. 09-30 19:44 사례의 armed=1 은 BACKFILL 결함으로 생긴 오염값이었고, 재시작 뒤 armed=0 이 오히려 맞는 상태였다". 정정 전 문구 병기.
- 조사 보고 묶음(`report.md`·`code-quotes.md`·`commands.txt`·`results/`)을 이번 문서 커밋에 함께 넣었다.
- 운영 가이드 사후 확증 8번 ⑥ 보강: 보유 중 재시작 시 `[TRAILING-RESTORE]` 1줄, 그 armed·peak 가 재시작 직전 `invariant_snapshots` 와 일치 (BACKFILL 오염 예외 명시).

## 6. 배포 때 알아둘 점

- 포지션이 없으면 재계산은 실행되지 않는다(로그 없음). 보유 중 재시작 때만 `[TRAILING-RESTORE]` 1줄.
- 배포 직후부터 감사 로그의 ts_armed 가 무장 봉에서 1 로 기록된다(과거 행은 0 그대로).
- 알려진 근사: 손절 등 앞선 필터가 매도를 낸 봉도 재생은 trailing 상태를 전진시킨다(매도 거절 같은 드문 경우에만 차이).

## 7. 묶음

- `report.md` (이 문서), `plan.md`
- `impl/wo21-code.diff`, `impl/test-new-code.txt`, `impl/test-old-code.txt`, `impl/gate-tests-oldsim-revert.txt`
- `impl/wo21_check.sh`, `impl/wo21_old_restart_sim.py`, `impl/wo21_fetch.py`
- `commands.txt`, `git-log.txt`
