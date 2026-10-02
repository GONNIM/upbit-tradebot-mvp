버전: v1.2026.10.02.0942 → v1.2026.10.02.2241

# WO-20 구현 보고 — executed_at 기록 + 복원 조회 정렬·시각 대용 + boot_seed 평균가 유지 (로컬 완료, 배포 대기)

- 작성: 2026-10-02 (KST)
- 코드 커밋: `986c9b0` (1건). 문서 커밋은 그 뒤 1건.
- 서버: 읽기만 했다 (HEAD `786b5cb`, 기동 2026-10-02 10:03:18 그대로). pull·재시작·DB 보정 없음. 투자자 안내 없음.
- 결정 사항 1~7 과 보류 사항: `plan.md`.

## 1. 변경 내용 (`impl/wo20-code.diff`)

| 파일 | 변경 | 결정 |
|---|---|---|
| `engine/order_reconciler.py` | `_final_timestamps()` 신설: 체결 수량이 있으면 `trades[].created_at` 중 가장 늦은 값을 KST ISO 로, trades 가 없으면 확정 처리 시각 + `[OR] executed_at 대체` WARNING 1줄. 취소 확정이면 canceled_at = 확정 처리 시각. `_handle` 확정 분기에서 계산해 `_finalize_order(…, executed_at, canceled_at)` → `update_order_completed` 로 전달. `[OR] final` 로그 끝에 두 값을 붙임 | 1·2·7 |
| `services/db.py` `get_last_open_buy_order` | 정렬 `COALESCE(executed_at, updated_at, timestamp) DESC, ROWID DESC`. 시각 열 `COALESCE(executed_at, updated_at)`. 열이 없는 옛 스키마는 있는 열만 사용 | 3·4 |
| `engine/live_loop.py` | boot_seed 분기를 `_apply_boot_seed()` 로 분리. 주문에서 entry_ts·entry_bar 만 복원, avg_price 는 지갑 동기화 값 유지(없을 때만 주문 평균가). 로그 `🔁 Position recovered \| avg_price=… (출처: wallet/order) order_price=…`. 시각을 못 정하면 `⚠️ [BOOT-SEED] 봇 주문의 체결 시각 없음 → boot_seed 미적용, 지갑 동기화 값 유지 \| has_position=… (출처: 지갑) entry_ts=… (기동 시각) \| 정체 포지션 판정은 기동 시각부터 다시 센다` WARNING | 5·6 |
| `pages/dashboard.py` | 버전 0942 → 2241 | — |

바꾸지 않은 것: 매수·매도 판정, 필터, 발주 요청(`core/trader.py`), 지표, OrderReconciler 진행 경로와 체결 callback.

## 2. 회귀 시험 (`tests/regressions/test_r_2026_10_02_wo20_executed_at.py`)

| # | 내용 | 새 코드 | 옛 코드 (`e444114`) |
|---|---|---|---|
| 1 | 정렬: NULL 옛 행 + 채워진 새 행 → 734 선택, 모두 채워도 734 | 통과 | **실패** `Tuples differ: (710.0, 200) != (734.0, 330)` |
| 2 | 확정 경로: done(trades 2건) → executed_at=08:00:14(마지막), cancel → canceled_at, wait → executed_at NULL | 통과 | **실패** `None != '2026-10-02T08:00:14+09:00'` |
| 3 | 복원 대용: executed_at NULL + updated_at → apply_entry, entry_ts=updated_at, `[POSITION-APPLY] source=boot_seed` | 통과 | **실패** `None != '2026-10-02T08:00:14.045644+09:00'` (시각 없음) |
| 4 | 평균가 유지: 지갑 740 / 주문 734 / 수량 400 vs 318 → avg 740, entry_ts 주문 시각. 지갑 평균가 없으면 734 | 통과 | **오류** `_apply_boot_seed` 없음 (옛 코드는 run_live_loop 안의 인라인 분기라 직접 호출 불가) |
| 5 | entry_bar 보정 고정: entry_bar 330 > 현재 201 → 실제 `IncrementalEMAStrategy.on_bar` 에서 audit 보정 18, entry_bar 183 | 통과 | 통과 (기존 경로를 고정하는 시험이라 옛 코드에서도 통과가 정상) |
| 6 | 보유 중 재시작 순서: sync_from_wallet → _seed_entry_price_from_db → _apply_boot_seed, boot_seed 로그 1줄, `[BOOT-SEED]` 0건 | 통과 | **오류** `_apply_boot_seed` 없음 (실데이터 재현은 §3) |
| 7 | (추가) 시각 없음 → apply_entry 미호출 + WARNING 문구, has_position=True | 통과 | **오류** `_apply_boot_seed` 없음 |

- 새 코드: `impl/test-new-code.txt` (7건 OK, `.env` 없는 worktree).
- 옛 코드: `impl/test-old-code.txt` (`FAILED (failures=3, errors=3)`).

## 3. 포지션 보유 중 재시작 재현 — 서버 DB 복사본 (`impl/gate-repro-revert.txt` [C])

- 서버 DB 에서 `orders`(557행)·`account_positions` 두 테이블만 읽기 전용(`mode=ro`)으로 SQL 출력해 scratchpad 에 복사했다 (`impl/wo20_dump.py`). 원본은 725MB 라 전체를 복사하지 않았다. 복사본은 저장소 밖에 있다.
- 작업용 사본에서 09:30 매도(556)·14:15 매도(557)를 지워 08:00~09:30 보유 상태를 만들었다. 가짜 지갑: JTO 318.01810267, Upbit avg_buy_price 734. 더미 키, 알림 패치.

| 변형 | 코드 | `_seed_entry_price_from_db` | 결과 | boot_seed 로그 | `[BOOT-SEED]` WARNING |
|---|---|---|---|---|---|
| as_is (executed_at 전부 NULL, 지금 데이터) | 새 `986c9b0` | price 734, entry_bar 330, entry_ts 08:00:14.045644 (updated_at) | apply_entry, avg 734 (출처 wallet), entry_ts 08:00:14.045644 | 1 | 0 |
| as_is | 옛 `e444114` | price 734, entry_bar 330, **시각 없음** | apply_entry 미호출, entry_bar None, **entry_ts = 재현 실행 시각(기동 시각)** | 0 | — (옛 ERROR 분기) |
| exec_set (555 에 executed_at 08:00:12) | 새 | price 734, entry_bar 330, entry_ts 08:00:12 | apply_entry, avg 734 (wallet), entry_ts 08:00:12 = Upbit 실제 체결 시각 | 1 | 0 |
| exec_set | 옛 | **price 747, entry_bar 286 (주문 553, 03:40 매수)** | apply_entry 미호출 | 0 | — |

옛 코드 exec_set 행은 정렬 결함(executed_at 오름차순)이 실데이터에서도 옛 매수를 고른다는 것을 보여 준다. 새 코드는 두 변형 모두 최신 매수를 고른다.

같은 기동에서 `[POS-SYNC] entry_ts 도 함께 복구 (sync 시각)`·`[POS-SYNC] avg_price 복구 성공` 이 WARNING 수준으로 남는다. 이는 지갑 동기화의 기존 정상 기록이고, 바로 뒤 boot_seed 가 entry_ts 를 주문 시각으로 덮는다. 사후 확증 8번 초안에 이 구분을 적었다.

## 4. 관문과 단독 되돌리기 (`impl/gate-repro-revert.txt` [A]·[D])

- 임시 worktree(`.env` 0개, 더미 키)에서 `986c9b0` 게이트: **282/282 통과** (WO-19 때 275 + 이번 7).
- `986c9b0` 단독 revert: **충돌 없음.** 5개 파일, py_compile 통과, 게이트 **275/275 통과**.

## 5. 문서

- `plan.md`: 결정 사항 1~7, 구현 대응, **189건 보정 보류**(정렬 수정 배포 뒤에만 가능).
- `docs/operations/wo8-force-buy-verification-guide.md`: "사후 확증 8번 — 초안" 절 추가 (boot_seed 적용 1줄, `[BOOT-SEED]` WARNING 0건, ts = 주문 체결 시각, avg_price = 지갑 값, 첫 SELL 평가 진행). 배포 전까지 초안 표시.
- 조사 보고(`report.md`, `code-quotes.md`, `commands.txt`, `results/`)도 이번 문서 커밋에 함께 넣었다.

## 6. 배포 때 알아둘 점

- 배포 직후부터 확정되는 주문은 `executed_at`·`canceled_at` 이 채워진다. 확인: `[OR] final … executed_at=… canceled_at=…`.
- 지금 포지션이 없는 상태에서 배포하면 boot_seed 는 타지 않는다. 사후 확증 8번은 이후 봇 포지션 보유 중 재시작이 있을 때 본다.
- 기존 주문은 executed_at 이 비어 있어도 `updated_at` 으로 복원된다. FILLED 는 실제 체결과 수 초, 부분 체결 뒤 취소는 최대 1봉 차이다 (조사 보고 B3).

## 7. 묶음

- `report.md` (이 문서), `plan.md`
- `impl/wo20-code.diff`, `impl/test-new-code.txt`, `impl/test-old-code.txt`, `impl/gate-repro-revert.txt`
- `impl/wo20_check.sh`, `impl/wo20_restart_repro.py`, `impl/wo20_dump.py`
- `commands.txt`, `git-log.txt`
