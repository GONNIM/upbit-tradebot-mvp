### 🔴 Issue #11: BACKFILL이 실시간 지표를 오염시켜 Golden Cross 미감지

**발생일**: 2026-03-25
**심각도**: 🔴 Critical (Golden Cross 타이밍 100% 놓침)

#### 문제

Dead Cross → Golden Cross 전환 시점인데 매수 신호가 발생하지 않음:

```
2026-03-24 16:50:35 | bar=2856 | Dead Cross | ema_fast=3210.14 < ema_slow=3211.88
2026-03-24 16:52:30 | bar=2857 | Golden Cross | ema_fast=3214.00 > ema_slow=3213.03
                              → BUY 신호 (BACKFILL)
2026-03-24 16:53:06 | bar=2857 | Golden Cross | ema_fast=3215.70 > ema_slow=3213.55
                              → NO_SIGNAL ❌ (실시간)
```

**DB 기록**:
```
timestamp          | bar_time  | bar  | ema_fast | ema_slow | overall_ok | notes
16:52:30 (BACKFILL)| 16:51:00  | 2857 | 3214.00  | 3213.03  | 1          | 🟢 BUY | Golden
16:53:06 (실시간)   | 16:52:00  | 2857 | 3215.70  | 3213.55  | 0          | Golden | NO_SIGNAL
```

**문제점**:
- 16:52:30 BACKFILL에서 Golden Cross 감지했지만 **실제 주문 실행 안 함** (설계 의도)
- 16:53:06 실시간 처리에서 **Golden Cross 감지 실패** → NO_SIGNAL

#### 근본 원인

**BACKFILL이 지표 상태(`prev_ema_fast`, `prev_ema_slow`)를 덮어씀**:

**타임라인 (수정 전):**

```python
# Step 1: 16:50:35 - bar=2856 실시간 처리
update_incremental(3264)
→ prev_ema_fast = 3210.14 (Dead)
→ prev_ema_slow = 3211.88 (Dead)
→ ema_fast = 3210.14
→ ema_slow = 3211.88

# Step 2: 16:52:30 - BACKFILL로 16:51 봉 처리
update_incremental(3268)  # ← BACKFILL인데도 호출!
→ prev_ema_fast = 3210.14 → 3214.00 (덮어씀!)
→ prev_ema_slow = 3211.88 → 3213.03 (덮어씀!)
→ ema_fast = 3214.00
→ ema_slow = 3213.03

Golden Cross 체크:
  prev (3210.14 Dead) → current (3214.00 Golden) = GC 감지! ✅
  하지만 BACKFILL이라 주문 건너뜀 ❌

# Step 3: 16:53:06 - 16:52 봉 실시간 처리
update_incremental(3266)
→ prev_ema_fast = 3214.00 (BACKFILL에서 오염된 값!)
→ prev_ema_slow = 3213.03 (BACKFILL에서 오염된 값!)
→ ema_fast = 3215.70
→ ema_slow = 3213.55

Golden Cross 체크:
  prev (3214.00 Golden) → current (3215.70 Golden) = 변화 없음 ❌
  → Golden Cross 감지 실패!
```

**핵심 문제:**
- BACKFILL에서 `update_incremental` 호출 시 `prev` 값을 덮어씀
- 다음 실시간 봉에서 `prev = BACKFILL에서 업데이트된 값`이 됨
- **16:50 Dead → 16:52 Golden 변화를 추적하지 못함**

#### 왜 놓쳤나?

1. **Issue #5 수정 시 부작용 미고려**
   - Issue #5: "EMA 증분 업데이트 누락" 수정
   - `update_incremental(bar.close)` 추가 (재계산 후)
   - 하지만 **BACKFILL 모드 여부를 확인하지 않음**
   - 항상 실행되어 `prev` 상태 오염

2. **BACKFILL 설계 가정 오류**
   - 가정: "BACKFILL은 감사 로그만 기록한다"
   - 실제: "BACKFILL도 지표를 업데이트한다" (Issue #5 수정 후)
   - **실시간 지표 상태를 보호하지 않음**

3. **End-to-End 검증 부족**
   - BACKFILL 전후 `prev` 상태 변화 확인 안 함
   - 실시간 봉에서 Golden Cross 감지 여부 검증 안 함

#### 교훈

1. **BACKFILL은 실시간 상태를 오염시켜선 안 된다**
   - BACKFILL 목적: 감사 로그 무결성 (과거 데이터 재평가)
   - 실시간 매매 로직과 완전히 분리되어야 함
   - **상태 백업/복원 패턴 필수**

2. **이전 상태(`prev`) 추적이 크로스 감지의 핵심**
   ```python
   # Golden Cross 조건
   prev_ema_fast <= prev_ema_slow  # 이전 Dead
   ema_fast > ema_slow             # 현재 Golden
   ```
   - `prev` 값이 오염되면 크로스 감지 불가능
   - BACKFILL이 `prev`를 건드리면 안 됨

3. **수정 시 모든 경로 검증 필수**
   - Issue #5 수정: Reconcile 후 증분 업데이트 추가
   - ✅ Reconcile 경로: 정상 동작
   - ❌ BACKFILL 경로: 부작용 발생 (미검증)

#### 수정

**핵심 원리: BACKFILL 전후로 지표 상태 백업/복원**

```python
# engine/live_loop.py:750-859

if backfill_ts_list:
    # ✅ Issue #11: BACKFILL 전 지표 상태 백업
    saved_indicators = {
        'ema_fast': engine.indicators.ema_fast,
        'ema_slow': engine.indicators.ema_slow,
        'prev_ema_fast': engine.indicators.prev_ema_fast,
        'prev_ema_slow': engine.indicators.prev_ema_slow,
        'macd': engine.indicators.macd,
        'signal': engine.indicators.signal,
        'prev_macd': engine.indicators.prev_macd,
        'prev_signal': engine.indicators.prev_signal,
        # ... 매수/매도 별도 EMA 포함
    }

    # BACKFILL 처리 (감사 로그 기록)
    for ts in sorted(backfill_ts_list):
        # ... BACKFILL 로직 ...
        engine.on_new_bar_confirmed(bar, local_series, backfill_diff_summary)

    # ✅ Issue #11: BACKFILL 후 지표 상태 복원
    engine.indicators.ema_fast = saved_indicators['ema_fast']
    engine.indicators.ema_slow = saved_indicators['ema_slow']
    engine.indicators.prev_ema_fast = saved_indicators['prev_ema_fast']
    engine.indicators.prev_ema_slow = saved_indicators['prev_ema_slow']
    # ... 복원
```

**수정 후 동작:**

```python
# Step 1: 16:50 봉 처리
prev: Dead (3210.14, 3211.88)
current: Dead (3210.14, 3211.88)

# Step 2: BACKFILL (16:51 봉)
지표 상태 백업 → BACKFILL 처리 → 지표 상태 복원
결과: prev=Dead, current=Dead (그대로!)

# Step 3: 16:52 봉 실시간 처리
prev: Dead (백업에서 복원된 3210.14, 3211.88)
current: Golden (새로 계산된 3215.70, 3213.55)
→ Dead → Golden = Golden Cross 감지! ✅ 매수 발생!
```

#### 영향 범위

- **파일**: `engine/live_loop.py`
- **라인**: 750-859 (BACKFILL 루프)
- **수정 내용**:
  - BACKFILL 시작 전: 지표 상태 백업 (35줄)
  - BACKFILL 종료 후: 지표 상태 복원 (30줄)

#### 검증 방법

```bash
# 1. 봇 재시작 후 BACKFILL 발생 시 로그 확인
tail -f mcmax33_engine_debug.log | grep -E "BACKFILL|지표 상태"

# 출력 예시:
# [BACKFILL] 지표 상태 백업 | prev_ema_fast=3210.14 prev_ema_slow=3211.88
# [BACKFILL] 누락 봉 평가 | ts=16:51:00 | close=3268
# [BACKFILL] 지표 상태 복원 완료 | prev_ema_fast=3210.14 prev_ema_slow=3211.88

# 2. Dead → Golden 전환 시 매수 신호 확인
sqlite3 services/data/tradebot_mcmax33.db \
  "SELECT timestamp, bar_time, bar, overall_ok, notes
   FROM audit_buy_eval
   WHERE notes LIKE '%Golden%'
   ORDER BY timestamp DESC LIMIT 10"

# 3. 실제 거래 발생 확인
sqlite3 services/data/tradebot_mcmax33.db \
  "SELECT timestamp, bar_time, type, reason, price
   FROM audit_trades
   WHERE type='BUY'
   ORDER BY timestamp DESC LIMIT 5"
```

#### 사용자 피드백

> "Dead -> Golden 변환시 GC 발생시점인데... 실질적으로 매수 전략이 돌지 않았다. 원인을 찾아서 해결방안을 강구하라."

**핵심 메시지**:
- ✅ Golden Cross 정확히 감지됨 (16:52:30, BACKFILL)
- ❌ BACKFILL이라 실제 매수 실행 안 됨 (설계 의도)
- ❌ 실시간 처리(16:53:06)에서 Golden Cross 감지 실패
- ✅ **근본 원인**: BACKFILL이 `prev` 상태를 오염시킴

**해결:**
- BACKFILL 전후 지표 상태 백업/복원으로 **실시간 Golden Cross 정확 감지 보장**

**파일**: `engine/live_loop.py`
**문서**: `CLAUDE.md` (Issue #11)

---

