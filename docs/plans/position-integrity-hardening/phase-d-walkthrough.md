# Phase D — 로컬 다각도 테스트 Walkthrough

**작성일**: 2026-07-03
**목적**: SP-PI-1~5 변경이 9개 시나리오(T1~T9)에서 사용자 클레임 재발을 물리적으로 차단함을 검증
**결과 요약**: **unittest 15/15 통과** + 서버 시나리오 walkthrough 정합성 확인
**관련**: [[plan.md]] · [[../../analysis/2026-07-03-position-integrity-audit/audit-map.md]]

---

## 1. Unit Test 커버 (`tests/test_position_integrity.py`)

```
Ran 15 tests in 1.251s — OK

TestApplyEntryContract  (4)   T1/T2 근본 검증 — apply_entry 필수 필드
TestOpenPositionDelegation  (2)   T6 회귀 — open_position 위임
TestClosePositionReset  (1)   T7 회귀
TestHasPendingAndRecent  (3)   T3 SP-PI-3 — pending BUY 우선 확인
TestLimitFillUuidDedupe  (3)   T9 SP-PI-2 — uuid dedupe
TestBarsHeldAuditFallback  (1)   SP-PI-4 — entry_bar 즉시 복구
TestHotReloadPositionRegression  (1)   T5 회귀
```

## 2. 시나리오별 정합성 (T1~T9)

### T1 — 오늘 10:25 시나리오 replay (HTS + 6초 후 봇 매수)

**결함 시나리오 (수정 전)**:
1. 10:25:26 HTS 매수 감지 → mark_position_as_hts_buy (DB meta만) → in-memory position 무시
2. 10:25:32 봇 EMA_GC 매수 → 이미 has_position=True (sync 로) → open_position 스킵 → entry_bar/entry_ts=None
3. 매 봉 SELL 평가: bars_held ≤ 0 → SELL 통째 차단 → Stale 영구 무효

**수정 후 흐름**:
1. HTS 매수 감지 → mark_position_as_hts_buy (DB 처리 유지)
2. 다음 봉 `_reconcile_position_with_wallet` (P2, Case 2 감지) → **`apply_entry(source="wallet_sync", entry_ts=now_kst())`** 호출 → 완전 세팅
3. 봇 EMA_GC 매수 (해당 case 는 이미 has_position=True 라 buy_market 스킵 or 추가 매수) — 진입 상태는 이미 apply_entry 로 세팅되어 있어 Stale 계산 정상
4. 2시간 경과 후 stale filter `elapsed_hours ≥ 2.0 AND max_gain < 1%` 도달 시 **STALE_POSITION 매도 트리거 정상 발동**

**정합성 근거**:
- `TestApplyEntryContract.test_apply_entry_requires_entry_ts` — entry_ts 누락 물리 차단
- `TestApplyEntryContract.test_apply_entry_source_variants` — "wallet_sync" 소스 라벨 정상
- 최대 지연: HTS 감지 후 1분 (periodic sync 주기) → 다음 봉 apply_entry
- 2시간 stale 검증 지연 무시 가능 (전체 대비 1/120)

---

### T2 — 오늘 16:40 시나리오 replay (순수 봇 LIMIT 매수)

**결함 시나리오 (수정 전)**:
1. 16:40 봇 EMA_GC → SP6 buy_limit → `limit_pending=True`, `_pending_buy_uuid` 세팅
2. 5봉 후 `_maybe_release_limit_pending` → uuid clear, **open_position 호출 없음**
3. 잔고 반영 (5분 지연) → periodic sync (30초 초과) → **HTS 오판정** → mark_position_as_hts_buy → entry_bar=None
4. 매 봉 P2 자동 복구 (entry_ts 세팅 없음) → stale_elapsed_hours=0 만성

**수정 후 흐름**:
1. buy_limit → limit_pending, `_pending_buy_uuid` 세팅 (기존과 동일)
2. OrderReconciler 폴링 → state='done' AND exec_vol > 0 감지 → `_fire_fill_callback` 발화
3. StrategyEngine `_on_limit_fill(uuid=..., executed_price=, executed_qty=, executed_ts=)`
4. `uuid == _pending_buy_uuid` 확인 → **`apply_entry(source="bot_limit_fill", entry_ts=executed_ts)`** 호출
5. pending 해제 → 다음 봉부터 정상 SELL 평가 (stale_elapsed_hours 정확 진행)
6. 2시간 후 stale 정상 발동

**정합성 근거**:
- `TestLimitFillUuidDedupe.test_matching_uuid_applies_entry` — pending uuid 일치 시 apply_entry 호출 검증
- `TestApplyEntryContract` — entry_ts 완전 세팅 검증
- 게다가 periodic sync 가 HTS 오판정하지 않도록 `has_pending_bot_limit_buy` 가 pending 상태 감지 (T3)

---

### T3 — SP6 정상 흐름 (HTS 오판정 방지)

**시나리오**: 봇 LIMIT submit 후 5봉 대기 중 (아직 미체결)에 periodic_balance_sync 발동.

**수정 후 흐름**:
1. periodic_balance_sync — 잔고 증가 없거나 아직 미반영
2. `has_recent_bot_buy_for_ticker(user_id, ticker)` 호출
3. **`has_pending_bot_limit_buy` 가 True 반환** — orders 테이블에 state IN ('REQUESTED','PARTIALLY_FILLED') BUY 존재
4. → HTS 마킹 스킵 (정상 봇 매수로 인식)
5. LIMIT 체결 완료 후 T2 흐름으로 이어짐

**정합성 근거**:
- `TestHasPendingAndRecent.test_has_pending_true_when_requested` — REQUESTED 감지
- `TestHasPendingAndRecent.test_has_pending_true_when_partially_filled` — PARTIALLY_FILLED 감지
- `TestHasPendingAndRecent.test_has_pending_false_when_filled` — 체결 완료 후는 pending 아님 (audit_trades 30s window 로 이어짐)

---

### T4 — 재시작 시 seed 성공/실패

**시나리오 (a) — seed 성공**:
1. 봇 재시작 → `sync_from_wallet` 감지: 지갑에 코인 있음
2. `_seed_entry_price_from_db` 호출 → `get_last_open_buy_order` 가 (price, entry_bar, **entry_ts_iso**) 반환
3. entry_ts_iso 를 timezone-aware datetime 으로 파싱 → **`apply_entry(source="boot_seed", entry_ts=원시각)`** 호출
4. 재시작 후 첫 봉부터 stale 계산 정확

**시나리오 (b) — seed 실패** (avg_price 또는 entry_ts 없음):
1. entry_price/entry_ts 복원 실패 → 로그 CRITICAL + `has_position=False` 유지
2. 봇 매매 정지, 사용자 개입 필요 안내 (Telegram CRITICAL)

**정합성 근거**:
- `services/db.py:get_last_open_buy_order` 에 `ts_col_pick` 로직 추가 (executed_at > created_at > ts > timestamp)
- `engine/live_loop.py` boot seed 블록에서 entry_ts 없으면 has_position=False 유지 (SP-PI-5)
- 근본: `apply_entry` 는 entry_ts=None 시 ValueError → 물리적으로 신뢰 없는 상태로 has_position=True 불가

---

### T5 — Hot Reload 회귀 (position 유지)

**시나리오**: 사용자가 매매 조건 저장 → `reload_conditions` 호출 → position 필드 유지 확인.

**정합성 근거**:
- `TestHotReloadPositionRegression.test_reload_conditions_does_not_touch_position` — 소스 정적 검증. `reload_conditions` 함수 안에 `self.position`, `position.has_position`, `position.close_position` 접근 없음 확인.

---

### T6 — 봇 마켓 매수 회귀

**시나리오**: SP6 비활성 상태에서 봇 buy_market → open_position 정상.

**정합성 근거**:
- `TestOpenPositionDelegation.test_open_position_delegates_and_sets_fields` — open_position 이 apply_entry(source="bot_market") 위임, 모든 필드 세팅 검증

---

### T7 — close_position 회귀

**정합성 근거**:
- `TestClosePositionReset.test_close_position_resets_all` — SELL 후 has_position/qty/avg_price/entry_bar/entry_ts/highest_since_entry/highest_price 모두 리셋

---

### T8 — HTS 매도 감지 (Case 1)

**시나리오**: 사용자가 HTS 로 전량 매도 → periodic_balance_sync 다음 주기 잔고 0 감지.

**수정 후 흐름 (변경 없음, 기존 정상)**:
1. `_reconcile_position_with_wallet` Case 1: `has_coins_in_wallet=False AND memory_has_position=True`
2. `self.position.close_position(ts=None)` 호출 → 모든 필드 리셋
3. audit_trades 에는 SELL row 자동 기록 없음 (G2 별건 후속 개선)

**정합성 근거**:
- `TestClosePositionReset` — close_position 자체는 정상 리셋
- G2 는 사후 분석 정확도 개선이며 매매 로직 안전성엔 영향 없음

---

### T9 — 부분 체결 edge case (D6: FILLED만 처리)

**시나리오**: LIMIT 부분 체결 상태로 wait_bars 초과 → Reconciler cancel → executed_volume > 0 (부분).

**수정 후 흐름**:
1. state 'cancel' + executed_volume > 0 → db_state='CANCELED' (FILLED 아님)
2. `_finalize_order` 진행, `_fire_fill_callback` **호출 안 함** (조건: `db_state == "FILLED"`)
3. 잔고에는 부분만 반영 → 다음 봉 P2 자동 복구 → `apply_entry(source="wallet_sync")` 로 세팅

**정합성 근거**:
- OrderReconciler `_handle` 수정 코드에서 `db_state == "FILLED"` 조건 명시
- 부분 체결도 P2 wallet_sync 를 통해 entry_ts 세팅되므로 stale 정상 동작
- D6 결정: 부분 체결 세부 처리 (avg_price 재계산 등) 은 별건 개선

**정합성 근거 (추가)**:
- 부분 체결도 `has_pending_bot_limit_buy` 가 PARTIALLY_FILLED 감지 시 True → HTS 오판정 없음 (T3 케이스 유효)

---

## 3. 회귀 위험 및 검증

| 영역 | 검증 방법 |
|---|---|
| 순수 봇 마켓 매수 (SP6 비활성) | T6 unit test 통과 |
| 순수 봇 LIMIT 매수 (SP6 활성) | T2 walkthrough + T9 부분 체결 |
| HTS 매수 감지 | T1 walkthrough (기존 mark_position_as_hts_buy 그대로 유지) |
| HTS 매도 감지 | T8 walkthrough (변경 없음) |
| 부팅 시 seed | T4 walkthrough (성공/실패 두 시나리오) |
| Hot Reload | T5 정적 검증 |
| close_position | T7 unit test |
| bars_held ≤ 0 안전 | SP-PI-4 audit fallback unit test |
| Stale filter (원 클레임 A) | T1/T2 walkthrough — 실제 stale_elapsed_hours 정상 진행 |
| SL/TP/Trailing | 결함 없음. `bars_held ≤ 0` 시스템 스킵 해소로 자동 정상화 |

## 4. 배포 전 필수 사전 검토

- [x] SP-PI-1~5 syntax 검증
- [x] Unit test 15/15 통과
- [x] Walkthrough 정합성 (9 시나리오)
- [ ] **사용자 최종 검토**: 본 문서 + `plan.md` + `audit-map.md` 확인 → 커밋 승인
- [ ] **커밋 → push → 서버 배포**
- [ ] **Phase F 사후 모니터링**: 72시간 (사용자 클레임 재발 없음 확인)

## 5. 배포 후 모니터링 지표 (Phase F)

- **각 SP 검증 로그**:
  - `[POSITION-APPLY] source=bot_market` — SP6 비활성 매수
  - `[POSITION-APPLY] source=bot_limit_fill` — SP6 활성 체결 (신설)
  - `[POSITION-APPLY] source=wallet_sync` — P2 자동 복구
  - `[POSITION-APPLY] source=boot_seed` — 재시작
  - `[POSITION-APPLY] source=hts_detect` — HTS 감지 (다음 봉 wallet_sync 형태로 나타남)
- **결함 재발 감지 신호**:
  - `bars_held=0 AND audit 실측 없음` CRITICAL — 발생 시 즉시 대응
  - `entry_ts is required` ValueError — 코드 결함 (테스트 커버 이후 재현 안 되어야 함)
- **Stale filter 발동 최초 실적**: 배포 후 첫 stale filter 발동 로그 (`💤 Stale Position 감지`) 반드시 관측 — 결함 해소 최종 증명

---

## 6. Phase D 완료 상태

- unittest 15/15 통과 ✅
- Walkthrough 9 시나리오 정합성 확인 ✅
- 회귀 리스크 검증 ✅
- 배포 준비 완료 — 사용자 최종 검토 대기
