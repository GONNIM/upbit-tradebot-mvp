# WO-20 구현 계획 — orders.executed_at 기록과 boot_seed 복원

- 작성: 2026-10-02 (KST)
- 근거: 조사 보고 `report.md` (가설 확인 + 정렬 결함 발견), Fable 검토 승인
- 처방: (다) = (가) 체결 확인 시 executed_at 기록 + (나) 복원 시 updated_at 대용, 여기에 D1 정렬 수정과 A4 문구 수정을 더한다.
- 범위: 구현과 로컬 검증, 푸시까지. 서버 pull·재시작은 별도 지시. DB 보정 없음. 투자자 안내 없음.

## 결정 사항 (운영자 확정)

1. **executed_at 의 뜻**: 체결 확정 시점의 마지막 체결 시각이다. 곧 Upbit `trades[].created_at` 중 가장 늦은 값이다. 진행 중(부분 체결) 경로에서는 쓰지 않는다. trades 가 비어 있으면 확정 처리 시각으로 대신하고 로그 1줄을 남긴다.
2. **canceled_at**: 취소 확정 시 같은 자리에서 기록한다 (조사 보고의 참고 별건 편입).
3. **복원 조회의 시각 열**: `COALESCE(executed_at, updated_at)`.
4. **복원 조회의 정렬**: `ORDER BY COALESCE(executed_at, updated_at, timestamp) DESC, ROWID DESC`.
5. **boot_seed 의 복원 범위**: entry_ts 와 entry_bar 만 복원한다. avg_price 는 지갑 동기화 값(`account_positions.entry_price` 또는 Upbit `avg_buy_price`)을 유지한다. 지갑 평균가를 구하지 못한 경우에만 주문 평균가를 쓴다.
6. **문구**: `engine/live_loop.py` 의 "P3 boot seed 시각 복원 실패 → has_position=False 유지" ERROR 를 WARNING 으로 낮추고, 실제 동작(has_position=True 유지, entry_ts=기동 시각)에 맞게 바꾼다.
7. **바꾸지 않는 것**: 매수·매도 판정, 필터, 발주 요청 경로, 지표 경로. OrderReconciler 수정은 DB 기록 인자 추가에 한정한다.

## 구현 대응

| 결정 | 파일 | 내용 |
|---|---|---|
| 1·2 | `engine/order_reconciler.py` | `_final_timestamps()` 신설. `_handle` 확정 분기에서 계산해 `_finalize_order(..., executed_at, canceled_at)` → `update_order_completed` 로 전달. 진행 경로·체결 callback 무변경 |
| 3·4 | `services/db.py` `get_last_open_buy_order` | 시각 열·정렬을 COALESCE 로. 열이 없는 옛 스키마는 있는 열만 쓴다 |
| 5·6 | `engine/live_loop.py` | boot_seed 분기를 `_apply_boot_seed()` 로 분리하고 평균가 규칙을 docstring·로그(`출처: wallet/order`)에 명시. 시각을 못 정하면 `⚠️ [BOOT-SEED] …` WARNING |
| — | `pages/dashboard.py` | 버전 v1.2026.10.02.0942 → v1.2026.10.02.2241 |

## 보류 사항

- **기존 주문 보정(KRW-JTO 매수 189건 등)의 executed_at 채우기는 보류한다.** 운영자 결정 사항이다.
  - (나)로 복원은 보정 없이 동작한다.
  - 보정은 정렬 수정(결정 4)이 배포된 뒤에만 할 수 있다. 정렬 수정 전에 보정하면 가장 오래된 매수를 고른다 (조사 보고 `results/order-by-sim.txt`).
  - 값의 출처(updated_at 또는 Upbit trades 시각)와 백업 절차는 결정 시 정한다.

## 검증 계획

- 회귀 시험 `tests/regressions/test_r_2026_10_02_wo20_executed_at.py` (메모리·임시 DB, `.env` 없는 worktree).
- 포지션 보유 중 재시작 재현: 서버 DB 의 `orders`·`account_positions` 를 읽기 전용으로 scratchpad 에 복사, 더미 키·가짜 지갑으로 `sync_from_wallet → _seed_entry_price_from_db → _apply_boot_seed` 실행. 복사본은 저장소에 넣지 않는다.
- 배포 뒤 사후 확증 8번(초안, `docs/operations/wo8-force-buy-verification-guide.md`)으로 실 서버 확인. 일부러 재시작하지 않는다.
