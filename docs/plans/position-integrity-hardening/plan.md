# Position Integrity Hardening — 통합 수정 기획안

**작성일**: 2026-07-03
**상태**: 초안 — 결정 항목 D1~D11 사용자 승인 대기
**배포 정책**: 5개 Sub-Phase (SP-PI-1~5) 로컬 완료 후 **단일 배포** ([[feedback_deploy_only_when_complete]])
**전제**: 봇 `inactive` since 2026-07-03 19:57:20 KST (감사·구현·테스트 완료까지 매매 중단)

관련:
- 근거 감사: [[../../analysis/2026-07-03-position-integrity-audit/audit-map.md]] — F1~F9 확정 결함 지도
- 사용자 지시 원문: "근본적인 문제를 찾아서 해결하고 또다른 오작동 가능성 또한 발생해서는 안된다. 사업의 존망이 걸려있는 것만큼 철저하게 순서대로 정확하게 대응"

---

## 1. WHY (목적)

### 1-1. 문제

Phase A 감사에서 9개 결함이 3축으로 얽혀 있음을 확정:

- **축 1** — P1 `open_position()` 미경유 (F7/F8) → P2 자동 복구 상시 활성 (F9) → `entry_ts=None` 만성 → Stale filter 영구 무효
- **축 2** — HTS 감지가 in-memory 무시 (F1) → `bars_held ≤ 0` 안전 로직이 매도 시스템 전체 스킵 (F4)
- **축 3** — has_recent 30초 (F2) 가 SP6 5봉과 mismatch → 봇 매수를 HTS로 오판정 → 축 2로 파급

### 1-2. 해결 원칙

- **근본 하나를 고쳐 여러 하류 결함이 자동 해소**되도록 통합 설계
- 개별 결함별 분리 hotfix 배제 (새 결함 도입 위험 + 축 간 상호작용 미고려)
- 부분 배포 금지 — 모든 SP 로컬 완결 후 단일 배포
- 자본 노출은 완결·검증 이전까지 0 유지 (봇 stopped)

---

## 2. WHAT (요구사항)

| ID | 요구 | 우선순위 |
|---|---|---|
| R1 | 모든 매수 경로(P1 시장가 / P2 자동 복구 / P3 부팅 / HTS 감지)에서 `PositionState` 진입 정보(qty/avg_price/entry_bar/**entry_ts**/highest_since_entry) 완전 세팅 | MUST |
| R2 | SP6 LIMIT 매수 체결 시 `open_position` 상당 처리가 정상 발동 (P2 우회 필연 제거) | MUST |
| R3 | `has_recent_bot_buy_for_ticker` 가 SP6 wait_bars 정책과 정합 (동적 계산) + orders 테이블 pending BUY 병합 확인 | MUST |
| R4 | `bars_held ≤ 0` 안전 로직이 매도 시스템 전체 스킵하지 않음 — audit_trades 실측 fallback 또는 자동 sync 트리거 | MUST |
| R5 | `avg_price=None` 비상 모드 제거 — 부팅 seed 실패 시 has_position=False + Telegram CRITICAL | MUST |
| R6 | 3중 진실 소스(account_positions / audit_trades / PositionState) 격차 즉시 감지·복원 | MUST |
| R7 | 통합 수정이 정상 flow(순수 봇 마켓 매수, close_position, Hot Reload) 를 회귀 없이 지원 | MUST |
| R8 | 배포 후 audit 관측성 — 각 진입 경로가 `PositionState` 필드를 어떻게 세팅했는지 추적 가능한 로그·audit row | SHOULD |

---

## 3. AS-IS (현 흐름 도식)

```
┌────────────────────────────────────────────────────────────────┐
│  진입 경로 (in-memory PositionState 세팅)                        │
│                                                                 │
│  ① P1 buy_market 성공 → open_position(qty, price, bar, ts) ✓   │
│  ② P1 buy_limit → limit_pending=True → open_position 보류      │
│     └─ pending release (wait_bars 후) → open_position 없음 ❌  │
│  ③ P2 자동 복구 (매 봉 _reconcile_position_with_wallet)         │
│     └─ has_position=True, avg_price, entry_bar 세팅 (entry_ts ❌)│
│  ④ P3 부팅 (live_loop.sync_from_wallet)                         │
│     └─ has_position=True, avg_price, entry_bar 세팅 (entry_ts ❌)│
│     └─ seed 실패 시 avg_price=None 비상 모드 ❌                 │
│  ⑤ HTS 감지 (mark_position_as_hts_buy)                          │
│     └─ meta.hts_buy=True 만 세팅. in-memory 무시 ❌             │
│                                                                 │
│  현재 사용자 conditions (fixed_price_buy_enabled=true) 상황:    │
│  ① 절대 안 됨 → ② → ③(P2 상시) → entry_ts=None → stale 영구 무효│
└────────────────────────────────────────────────────────────────┘
```

---

## 4. TO-BE (Sub-Phase 설계)

### SP-PI-1 — `PositionState` 통합 진입 API 신설 (근본 축 ①)

**목표**: 모든 진입 경로가 하나의 API 를 통해 완전 세팅. `entry_ts` 누락 물리적 불가능.

`core/position_state.py` 에 신규 메서드:

```python
def apply_entry(
    self,
    qty: float,
    avg_price: float,
    entry_bar: int,
    entry_ts,             # timezone-aware datetime, 필수
    source: str,          # "bot_market" / "bot_limit_fill" / "wallet_sync" / "boot_seed" / "hts_detect"
    highest_since_entry: float = None,  # None이면 avg_price로 초기화
) -> None:
    """
    통합 진입 API — 모든 P1/P2/P3/HTS 경로가 이 API를 호출.
    entry_ts 는 필수 — None 이면 예외 (source 별 caller 가 안전한 시각 결정)
    """
    if entry_ts is None:
        raise ValueError(f"entry_ts is required (source={source})")
    self.has_position = True
    self.qty = qty
    self.avg_price = avg_price
    self.entry_bar = entry_bar
    self.entry_ts = entry_ts
    self.highest_since_entry = highest_since_entry if highest_since_entry is not None else avg_price
    logger.info(
        f"✅ [POSITION-APPLY] source={source} qty={qty:.6f} entry={avg_price:.2f} "
        f"bar={entry_bar} ts={entry_ts.isoformat()}"
    )
```

- `open_position()` 도 내부에서 `apply_entry(source="bot_market")` 호출로 통일 (기존 시그니처 유지)
- P2 자동 복구 (strategy_engine.py:210~219) → `apply_entry(source="wallet_sync", entry_ts=bar.ts)` 사용
- P3 부팅 (live_loop.py:438~454) → `apply_entry(source="boot_seed", entry_ts=사용자 결정)` 사용
- HTS 감지 → `apply_entry(source="hts_detect", entry_ts=감지 시각)` 사용

**결정 항목**:
- **D1** — `apply_entry` API 위치·이름 (`PositionState.apply_entry` 권장)
- **D2** — 각 source 의 `entry_ts` 기준
  - P2 wallet_sync: `bar.ts` (현재 봉 시각) vs `now_kst()` (실시각)
  - P3 boot_seed: `now_kst()` (엔진 부팅 시각) vs audit_trades BUY 의 원 시각 복원
  - HTS_detect: `now_kst()` (감지 시각) vs Upbit avg_buy_price 캐시된 매수 시각
- **D7** — HTS 감지 시 audit_trades BUY row 에 `entry_bar=None` 대신 `entry_bar=현재 bar_count` 저장 여부

### SP-PI-2 — SP6 LIMIT 체결 감지 → `apply_entry` 호출 (근본 축 ②·④)

**목표**: LIMIT pending release 시점 또는 실체결 감지 시점에 P1 상당 처리 발동.

두 가지 접근 (D5 결정):

- **접근 (a)**: `_maybe_release_limit_pending` 안에서 audit_orders 로 체결 여부 조회 → 체결됐으면 `apply_entry` 호출
- **접근 (b)**: OrderReconciler 가 LIMIT 체결 폴링 감지 시 이벤트 발행 → strategy_engine 이 callback 으로 `apply_entry` 호출

**결정 항목**:
- **D5** — 감지 방식 (a) 폴링 vs (b) 이벤트 콜백
- **D6** — 부분 체결 처리 (executed_volume > 0 && < requested) — 부분만이라도 진입 처리할지, 전량 체결 대기할지

### SP-PI-3 — `has_recent_bot_buy_for_ticker` 재설계 (근본 축 ③)

**목표**: SP6 wait_bars 정책과 정합 + orders 테이블 pending BUY 도 함께 확인.

```python
def has_recent_bot_buy_for_ticker(user_id, ticker, dynamic=True):
    """
    Args:
        dynamic: True 면 conditions.fixed_price_buy_wait_bars × interval_sec + margin
                 False 면 within_seconds 명시 (호환 유지)
    """
    # 1) orders 테이블에 pending LIMIT BUY 있으면 즉시 True (봇 매수 진행 중)
    if has_pending_bot_limit_buy(user_id, ticker):
        return True
    # 2) audit_trades 최근 BUY row 조회 (동적 window)
    window_sec = compute_dynamic_window(user_id, ticker) if dynamic else within_seconds
    ...
```

**결정 항목**:
- **D3** — window 정책
  - (a) 동적 계산: `wait_bars × interval_sec + margin(예: 30초)`
  - (b) 고정 여유값: `SP6_MAX_WAIT_SEC` 상수 (예: 600초)
- **D4** — pending BUY 조회 방식 (orders 테이블 SELECT WHERE state IN ('requested','pending') AND side='BUY' AND ticker=? AND user_id=?)

### SP-PI-4 — `bars_held ≤ 0` 안전 로직 대체 (근본 축 ⑤)

**목표**: entry_bar=None 을 결손 판정하지 않고 즉시 sync 트리거. SELL 시스템 스킵 방지.

`core/strategy_incremental.py:1053~1065`:

기존:
```python
if bars_held <= 0:
    logger.error("bars_held=음수/0 — SELL 차단 (HOLD)")
    return Action.HOLD
```

변경 (안):
```python
if bars_held <= 0:
    # 자체 진단: audit_trades 실측 bars_held 로 즉시 복구 시도
    audit_bars_held = estimate_bars_held_from_audit(self.user_id, self.ticker)
    if audit_bars_held > 0:
        logger.warning(
            f"⚠️ [EMA] in-memory bars_held={bars_held} → audit fallback={audit_bars_held} 적용"
        )
        bars_held = audit_bars_held
        # entry_bar 도 동기화 (position 즉시 복구)
        self.position.entry_bar = self.bar_count - audit_bars_held
    else:
        # audit 도 없으면 진짜 결손 → 알람 + SELL 차단
        logger.error("bars_held=음수/0 AND audit 실측 없음 — SELL 차단 + CRITICAL 알림")
        _notify_critical_position_desync(...)
        return Action.HOLD
```

**결정 항목**:
- **D8** — audit fallback 활성화 여부. 원래 제거된 로직이라 재도입 신중 (거부 이유: "잘못된 SELL 위험"). 이번엔 SP-PI-1 통합 API로 진입 데이터가 확실히 세팅되므로 audit fallback 안전성 증가

### SP-PI-5 — `avg_price=None` 비상 모드 제거 + audit 관측성 (근본 축 ⑥)

**목표**: 신뢰 가능한 진입가 없이 has_position=True 가 되는 경로 완전 제거.

`live_loop.py:450~454` 삭제:
```python
# 삭제 대상:
position.has_position = True
position.qty = actual_qty
position.avg_price = None  # 진입가 불명 ← 이 경로 완전 제거
```

대체:
```python
logger.critical(
    f"❌ 지갑에 코인({actual_qty:.6f}) 있으나 DB seed 실패 → "
    f"has_position=False 유지. 봇 매매 스킵. 사용자 정리 필요."
)
_notify_critical(
    "포지션 seed 실패 — 수동 정리 필요",
    f"ticker={ticker}, qty={actual_qty:.6f}, DB에서 진입가를 찾을 수 없음. "
    f"HTS 강제매도 or force_liquidate 필요."
)
```

**관측성 (R8)** — `audit_trades` 신규 컬럼 검토:
- `entry_source`: "bot_market" / "bot_limit_fill" / "wallet_sync" / "boot_seed" / "hts_detect"
- `entry_ts_setter`: entry_ts 를 세팅한 source (사후 분석 정확도)

**결정 항목**:
- **D9** — 비상 모드 완전 제거 vs 강한 경고 후 진행 옵션 유지
- **D10** — audit_trades 스키마 변경 여부 (컬럼 추가 필요 시 `_safe_alter_column` 패턴)

---

## 5. 영향 받는 파일

### SP-PI-1
- `core/position_state.py` — `apply_entry` 신규 메서드, `open_position` 내부 위임
- `core/strategy_engine.py` — P2 자동 복구 블록 (line 210~219) `apply_entry` 사용으로 교체
- `engine/live_loop.py` — P3 부팅 복구 (line 438~454) `apply_entry` 사용으로 교체
- `engine/order_reconciler.py` — HTS 감지 (line 456) 이후 `apply_entry` 호출 추가
- `services/db.py` — `mark_position_as_hts_buy` 는 유지 (DB meta 세팅), in-memory 는 별도 경로

### SP-PI-2
- `engine/order_reconciler.py` — LIMIT 체결 감지 이벤트 발행 (D5 결정에 따라)
- `core/strategy_engine.py` — `_maybe_release_limit_pending` 확장 or fill-callback 등록

### SP-PI-3
- `services/db.py` — `has_recent_bot_buy_for_ticker` 재설계, `has_pending_bot_limit_buy` 신규
- `engine/order_reconciler.py` — 호출 부분 유지 (내부 로직만 변경)

### SP-PI-4
- `core/strategy_incremental.py` — `bars_held ≤ 0` 블록 audit fallback 로직
- `services/db.py` — `estimate_bars_held_from_audit` 신규 (또는 기존 있으면 확인)

### SP-PI-5
- `engine/live_loop.py` — `avg_price=None` 경로 제거, CRITICAL 알림
- `services/notifier.py` — 필요 시 `_notify_critical_position_desync` helper
- `services/db.py` + `services/init_db.py` — audit_trades 컬럼 추가 (D10 결정 시)

### 공통
- 로컬 테스트용 시나리오 스크립트 신규 (Phase D 산출물)

---

## 6. Phase 순서

```
P0 — 기획안 결정 항목 D1~D11 사용자 승인 (현재 단계)
   ↓
SP-PI-1 (통합 진입 API) — 근본 축 ①, 다른 SP 의존
   ↓
SP-PI-2 (SP6 fill 감지) — SP-PI-1 API 사용
   ↓
SP-PI-3 (has_recent 재설계)
   ↓
SP-PI-4 (bars_held 안전 로직)
   ↓
SP-PI-5 (avg_price=None 제거 + 관측성)
   ↓
Phase D — 로컬 다각도 테스트
  ├─ 오늘 10:25 시나리오 replay (HTS + 봇 매수 → 2h stale 발동)
  ├─ 16:40 시나리오 replay (순수 봇 EMA_GC → 2h stale 발동)
  ├─ SP6 5봉 대기 후 체결 시나리오 (HTS 오판정 없음)
  ├─ 서비스 재시작 후 position reload 정확성
  ├─ Hot Reload 시 position 유지 (회귀)
  ├─ 부분 체결·주문 취소·잔여 처리 edge case
  ├─ 정상 봇 마켓 매수 (회귀)
  ├─ close_position 흐름 (회귀)
  └─ 비상 seed 실패 시 has_position=False 유지 + Telegram
   ↓
Phase E — 사용자 최종 승인 → 커밋 → push → 서버 배포
   ↓
Phase F — 사후 모니터링 (72시간, 지도의 F1~F9 각 결함이 실제로 재발 안 하는지 audit 로 검증)
```

---

## 7. 결정 필요 항목 (D1~D11)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| **D1** | 통합 진입 API 이름 | (a) `PositionState.apply_entry` (b) `PositionState.reset_from_entry` (c) `PositionState.record_open` | **(a) apply_entry** — 의도 명확 |
| **D2** | 각 source 의 entry_ts 기준 | 위 SP-PI-1 상세 참조 | **P2: `bar.ts` / P3: audit_trades BUY 원 시각 복원 / HTS: `now_kst()`** |
| **D3** | has_recent window 정책 | (a) 동적 `wait_bars × interval_sec + 30s` (b) 고정 상수 600초 | **(a) 동적** — 정확성 |
| **D4** | pending BUY 조회 조건 | (a) `state IN ('requested','pending')` (b) `canceled_at IS NULL AND executed_volume < volume` | **(a) state** — 명확 |
| **D5** | SP6 fill 감지 방식 | (a) `_maybe_release_limit_pending` 폴링 확장 (b) OrderReconciler → strategy_engine 이벤트 콜백 | **(b) 이벤트 콜백** — 결합 낮음 |
| **D6** | 부분 체결 처리 | (a) 전량 대기 후 처리 (b) 부분만이라도 즉시 apply_entry (avg_price 는 가중 평균) | **(a) 전량 대기** — 안전, 부분 체결은 별건 개선 |
| **D7** | HTS 감지 시 entry_bar 저장 | (a) audit_trades entry_bar=None 유지 (b) 감지 시점 self.bar_count 저장 | **(b) bar_count** — 사후 추적 가능 |
| **D8** | bars_held ≤ 0 audit fallback | (a) 재도입 (SP-PI-1 로 진입 확실해진 후 안전) (b) 유지(HOLD 차단) | **(a) 재도입** — 하지만 CRITICAL 알림 함께 |
| **D9** | avg_price=None 비상 모드 | (a) 완전 제거 (has_position=False 강제) (b) 강한 경고 후 진행 옵션 유지 | **(a) 완전 제거** — 반쪽 상태 위험 |
| **D10** | audit_trades 컬럼 추가 (entry_source, entry_ts_setter) | (a) 추가 (관측성 ↑) (b) 유지 (스키마 변경 회피) | **(a) 추가** — 사후 분석 필수, `_safe_alter_column` 사용 |
| **D11** | Phase F 사후 모니터링 기간 | (a) 24h (b) 48h (c) 72h | **(c) 72h** — 각 결함의 재발 검증 여유 |

---

## 8. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| SP-PI-1 통합 API 도입 시 기존 open_position 호출자 회귀 | 정상 flow 파괴 | Phase D 회귀 테스트 필수. `open_position` 은 내부 위임 유지 (외부 시그니처 불변) |
| SP-PI-2 이벤트 콜백 도입 시 순환 참조·race | LIMIT 체결 누락·중복 | fill 이벤트를 idempotent 하게 (uuid 기반 dedupe) |
| SP-PI-3 has_recent 확대 시 진짜 HTS 매수도 봇으로 오인 | HTS_BUY audit 누락 | orders 테이블 pending BUY 명확 조회 (submit 후 미체결만 True), 체결 완료 후에는 자연스러운 30s window |
| SP-PI-4 audit fallback 재도입 시 잘못된 bars_held | 조기 매도 | 원설계 우려 재고 필요. SP-PI-1 로 진입 완전 세팅 확실 → fallback 은 예외 상황만. 게다가 audit_trades 실측이 이미 로그로 출력됨 (신뢰도 검증됨) |
| SP-PI-5 비상 모드 제거 시 지갑에 코인 있는데 매도 불가 상황 | 자본 매몰 | CRITICAL 알림 + 사용자 수동 개입 안내. 봇이 임의 매도하는 것보다 안전 |
| audit_trades 스키마 변경 (D10) 실패 | 배포 실패 | `_safe_alter_column` idempotent, 롤백 스크립트 준비 |
| Phase D 로컬 테스트에서 커버되지 않은 edge case | Phase F에서 재발 | 테스트 시나리오 목록 Phase D 진입 전 사용자 재검토 |
| **모든 SP 완결까지의 시간** — 봇 stopped 상태 지속 | 시장 기회 손실 | 사용자 결정 (봇 재가동은 완결·배포·검증 이후) — 사업 존망 대비 기회비용은 감수 |

---

## 9. 로컬 테스트 시나리오 (Phase D 상세)

### T1 — 오늘 10:25 시나리오 replay
- 초기: has_position=False
- HTS 매수 시뮬 → mark_position_as_hts_buy + apply_entry(source="hts_detect")
- 봇 EMA_GC 시그널 → 이미 has_position=True 로 skip 또는 add
- 2시간 봉 진행 → stale filter 발동 확인 (기대: STALE_POSITION reason)

### T2 — 16:40 시나리오 replay
- 초기: has_position=False
- 봇 EMA_GC → buy_limit → limit_pending
- 5봉 후 체결 감지 → apply_entry(source="bot_limit_fill")
- 2시간 봉 진행 → stale filter 발동 확인

### T3 — SP6 정상 흐름
- 봇 매수 → LIMIT submit → orders 테이블 pending 조회 → has_recent True → HTS 오판정 없음
- 체결 → apply_entry(source="bot_limit_fill")
- 매도 조건 도달 → SL/TP/Stale/Trailing 각각 발동

### T4 — 재시작 시 seed
- 지갑에 코인 있고 audit_trades BUY row 있음 → apply_entry(source="boot_seed") 성공
- 지갑에 코인 있고 audit_trades·avg_buy_price 캐시 모두 없음 → has_position=False + CRITICAL

### T5 — Hot Reload (회귀)
- SP6 활성화 → 비활성화 저장 → next bar 매수는 buy_market 경유
- position 유지 확인

### T6 — 정상 봇 마켓 매수 (회귀)
- fixed_price_buy_enabled=false → buy_market → open_position → apply_entry(source="bot_market")
- 매도 시나리오 정상

### T7 — close_position (회귀)
- SL/TP 도달 → sell 실행 → close_position → has_position=False

### T8 — HTS 매도 감지 (Case 1)
- 사용자가 HTS 로 전량 매도 → periodic sync 잔고 0 감지 → close_position(ts=None) 정상 리셋

### T9 — 부분 체결 edge case (D6 결정에 따라)
- LIMIT 부분 체결 상태로 wait_bars 초과 → Reconciler cancel → 부분만 잔고
- 처리 정책 검증

---

## 10. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-07-03 20:45 | 초안 작성 | Phase A 감사 지도 완결(F1~F9) → 통합 수정 5축 설계. 결정 항목 D1~D11 사용자 승인 대기 |

---

## 다음 단계

**D1~D11 결정 알려주시면** SP-PI-1 부터 순차 로컬 구현 착수합니다. 결정 축약 (예: "모두 추천안"·"D5 는 (a)로 변경" 등) 도 무방합니다.
