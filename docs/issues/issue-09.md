### 🔴 Issue #9: BACKFILL 봉 중복 체크로 인한 audit UPDATE 미동작

**발생일**: 2026-03-16
**심각도**: 🔴 Critical (미확정 종가가 DB에 그대로 유지됨)

#### 문제

BACKFILL이 실행되어 확정 종가로 재평가했지만, DB audit 로그가 UPDATE되지 않음:

```
2026-03-16 19:48  |  Upbit=3186  |  Tradebot DB=3189  ❌ (+3원 차이)
2026-03-16 19:56  |  Upbit=3187  |  Tradebot DB=3191  ❌ (+4원 차이)
```

**로그**:
```
[19:48:18] price=3189.00 (현재 봉 처리)
[19:49:31] 🔄 [BACKFILL] 누락 봉 평가 | ts=19:48:00 | close=3186
[19:49:31] ✅ [BACKFILL] 1개 누락 봉 평가 완료
```

BACKFILL이 3186으로 재평가했지만 DB는 3189 유지됨.

#### 근본 원인

**`strategy_engine.py:260-262` 중복 봉 체크**:

```python
# ✅ 중복 방지
if not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return  # ← audit 로그 기록 없이 종료
```

**BACKFILL 시나리오**:
1. **19:48분**: 현재 봉(n) 처리
   - `self.last_bar_ts = 19:48`
   - `insert_buy_eval(..., bar_time='19:48', price=3189)`
   - DB INSERT
2. **19:49분**: BACKFILL로 19:48 봉 재평가
   - `is_new_bar(bar)` 체크: `bar.ts (19:48) != last_bar_ts (19:48)` → **False**
   - **중복으로 간주되어 return**
   - `insert_buy_eval` 호출 안 됨 → **DB UPDATE 안 됨**

#### 왜 놓쳤나?

1. **BACKFILL 설계 가정 오류**
   - 가정: "BACKFILL은 누락 봉을 처리한다"
   - 실제: "BACKFILL은 **변경된 봉**도 재평가한다" (미확정 → 확정 종가)
   - 중복 체크 로직이 재평가를 차단함

2. **audit UPSERT 의존**
   - `insert_buy_eval`은 UPSERT 방식 (ticker, bar_time 일치 시 UPDATE)
   - 하지만 `is_new_bar` 체크에서 early return하여 함수 호출 자체가 안 됨

3. **로그 검증 부족**
   - BACKFILL 완료 로그는 있지만 audit UPDATE 로그 없음
   - DEBUG 레벨 로그 (`[ENGINE] 중복 봉 무시`)는 확인하지 않음

#### 교훈

1. **"재평가"는 "중복"이 아니다**
   - 중복 체크: 동일한 시각의 봉을 여러 번 처리하는 것 방지
   - 재평가: 이미 처리된 봉의 **값을 수정**하는 것 (BACKFILL)
   - 별도 플래그로 구분 필요

2. **Early return의 숨겨진 부작용**
   - 중복 체크가 audit 로그 기록까지 차단
   - 모든 early return 위치에서 side effect 검증 필요

3. **End-to-End 검증**
   - BACKFILL 실행 후 DB 값 확인
   - `[AUDIT-UPDATE]` 로그 추가로 검증 강화

#### 수정

**Before (중복 체크가 BACKFILL 차단)**:
```python
# strategy_engine.py:259-262
# ✅ 중복 방지
if not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return  # ← BACKFILL도 차단됨
```

**After (BACKFILL 모드는 중복 체크 우회)**:
```python
# strategy_engine.py:259-265
# ✅ 중복 방지 (BACKFILL 모드는 제외)
# Issue #9: BACKFILL은 이미 처리된 봉을 재평가하여 audit 로그를 UPDATE하므로
# 중복 체크를 우회해야 함
backfill_mode = diff_summary.get("backfill_mode", False)
if not backfill_mode and not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return
```

**추가 수정 (버퍼 추가 스킵)**:
```python
# strategy_engine.py:270-277
# 1. 버퍼 추가 (BACKFILL 모드는 제외)
# Issue #9: BACKFILL은 과거 봉 재평가이므로 버퍼 추가/bar_count 증가 불필요
if not backfill_mode:
    self.buffer.append(bar)
    self.last_bar_ts = bar.ts
    self.bar_count += 1
else:
    logger.info(f"[BACKFILL] 버퍼 추가 스킵 (재평가 모드) | ts={bar.ts} | close={bar.close:.0f}")
```

**검증 로그 추가 (`services/db.py`)**:
```python
# insert_buy_eval, insert_sell_eval
if existing:
    logger.info(
        f"[AUDIT-UPDATE] BUY 평가 UPDATE | ticker={ticker} | bar_time={bar_time} | "
        f"old_id={existing[0]} | new_price={price:.0f}"
    )
```

#### 영향 범위

- **파일 1**: `core/strategy_engine.py` (중복 체크, 버퍼 추가)
- **파일 2**: `services/db.py` (audit UPDATE 로그 추가)

#### 검증 방법

봇 재시작 후 다음 BACKFILL 발생 시:
```bash
# 1. BACKFILL 로그 확인
tail -f mcmax33_engine_debug.log | grep BACKFILL

# 2. audit UPDATE 로그 확인
tail -f mcmax33_engine_debug.log | grep AUDIT-UPDATE

# 3. DB 데이터 정합성 확인
sqlite3 services/data/tradebot_mcmax33.db \
  "SELECT ticker, bar_time, price FROM audit_buy_eval WHERE bar_time='...' ORDER BY timestamp DESC LIMIT 1"
```

**파일**: `core/strategy_engine.py`, `services/db.py`
**문서**: `CLAUDE.md` (Issue #9)

---

