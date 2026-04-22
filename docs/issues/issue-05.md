### 🔴 Issue #5: EMA 증분 업데이트 누락 (Reconcile 재계산 후)

**발생일**: 2026-03-03 22:00
**심각도**: 🔴 Critical (EMA 값 정지, BUY/SELL 평가 로직 100% 오작동)

#### 문제

REST Reconcile 모드에서 매 분봉마다 **EMA 값이 동일**하게 유지됨:

```
bar=201 | price=2697.00 | ema_fast=2711.37 | ema_slow=2715.94
bar=202 | price=2673.00 | ema_fast=2711.37 | ema_slow=2715.94  ❌ 같음
bar=203 | price=2667.00 | ema_fast=2711.37 | ema_slow=2715.94  ❌ 같음
bar=204 | price=2680.00 | ema_fast=2711.37 | ema_slow=2715.94  ❌ 같음
```

**증상**:
- 가격은 변동 (2697 → 2673 → 2667 → 2680)
- **EMA는 정지** (2711.37, 2715.94로 고정)
- BUY/SELL 평가 로직 완전 무용지물

#### 근본 원인

**`strategy_engine.py:on_new_bar_confirmed()` 라인 286-296**:

```python
elif changed_count > 0:
    # ✅ Reconcile 변경 발생 → 부분 재계산
    logger.warning(...)

    # 🔒 리스크 헷지: 전체 400개 재계산 금지
    # changed_ts 이후만 재계산
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)

    # ❌ 문제: 재계산 후 현재 봉 반영 없음!
```

**왜 문제인가?**

1. **`recompute_from_changed_ts`의 동작**:
   ```python
   # indicator_state.py:183-227
   def recompute_from_changed_ts(self, full_series, changed_ts):
       tail = full_series.loc[recompute_start:]  # 과거 데이터 추출
       closes = tail['Close'].tolist()
       self.seed_from_closes(closes)  # 과거 데이터로 재시드
   ```
   - `full_series`는 **REST에서 가져온 과거 데이터**
   - **현재 봉(`bar.close`)은 포함되지 않음**

2. **결과**:
   - 재계산 → 과거 시점의 EMA로 초기화
   - **현재 봉 반영 없음** → EMA 정지
   - 매 분봉마다 같은 과거 시점으로 재시드 → 같은 EMA 값

3. **비교**:
   ```python
   # ✅ rest_failed 경로 (라인 284)
   self.indicators.update_incremental(bar.close)  # 현재 봉 반영

   # ✅ changed_count == 0 경로 (라인 301)
   self.indicators.update_incremental(bar.close)  # 현재 봉 반영

   # ❌ changed_count > 0 경로 (라인 296)
   # 현재 봉 반영 없음! ← 버그
   ```

#### 왜 놓쳤나?

1. **분기별 일관성 검증 부족**
   - 3개 분기(`rest_failed`, `changed_count > 0`, `changed_count == 0`)
   - 2개 분기는 `update_incremental()` 호출, 1개는 누락
   - 분기 간 로직 일관성을 확인하지 않음

2. **End-to-End 테스트 부족**
   - 재계산 후 EMA 값이 업데이트되는지 실제 로그 미확인
   - 단위 테스트만으로는 발견 불가

3. **`recompute_from_changed_ts`의 제한 이해 부족**
   - "재계산"이라는 이름에서 "완전한 업데이트"로 오해
   - 실제로는 "과거 데이터로 재시드"일 뿐
   - 현재 봉 반영은 별도 호출 필요

#### 교훈

1. **분기별 일관성 검증 필수**
   ```python
   # ✅ 체크리스트
   if rest_failed:
       # [ ] 현재 봉 반영?
       self.indicators.update_incremental(bar.close)

   elif changed_count > 0:
       # [ ] 현재 봉 반영?
       self.indicators.recompute_from_changed_ts(...)
       self.indicators.update_incremental(bar.close)  # ✅ 추가

   else:
       # [ ] 현재 봉 반영?
       self.indicators.update_incremental(bar.close)
   ```

2. **함수 책임 명확화**
   - `recompute_from_changed_ts`: 과거 데이터로 재시드 (현재 봉 미포함)
   - `update_incremental`: 현재 봉 1개만 증분 반영
   - **재시드 후 항상 현재 봉 반영 필요**

3. **End-to-End 검증 필수**
   ```bash
   # ✅ 실제 로그로 검증
   tail mcmax33_engine_debug.log | grep ema_fast
   # → EMA 값이 매 봉마다 변하는지 확인
   ```

#### 수정

**Before (버그)**:
```python
# strategy_engine.py:286-296
elif changed_count > 0:
    logger.warning(...)
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)
    # ❌ 현재 봉 반영 없음
```

**After (수정)**:
```python
# strategy_engine.py:286-301
elif changed_count > 0:
    logger.warning(...)
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)

    # ✅ 재계산 후 현재 봉 반영 (CRITICAL!)
    # recompute_from_changed_ts는 full_series(과거 데이터)로만 재시드
    # 현재 봉(bar.close)은 아직 반영되지 않으므로 증분 업데이트 필수
    self.indicators.update_incremental(bar.close)
```

#### 영향 범위

- **파일**: `core/strategy_engine.py`
- **라인**: 286-301 (on_new_bar_confirmed 메서드)
- **분기**: `changed_count > 0` 경로

#### 검증 방법

```bash
# 1. 봇 재시작 후 로그 확인
tail -f mcmax33_engine_debug.log | grep ema_fast

# 2. EMA 값이 매 분봉마다 변하는지 확인
# Before: ema_fast=2711.37 (고정)
# After: ema_fast=2711.37 → 2710.89 → 2710.15 (변동)
```

---

