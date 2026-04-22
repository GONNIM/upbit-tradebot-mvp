### 🔴 Issue #6: 정체 포지션 필터 - 봉 개수 기반 계산 (잘못된 설계)

**발생일**: 2026-03-04 20:00
**심각도**: 🔴 Critical (사용자 기대와 100% 불일치)

#### 문제

**사용자 설정**:
```
💡 정체 포지션 필터: 2.0시간 동안 진입가 대비 최고 수익률이 1.0% 미만이면 강제 매도
```

**사용자 기대**: 정확히 **2.0시간** 경과 후 매도

**실제 동작**:
- 매수: 2026-03-04 01:05 KST (bar=282)
- 매도: 2026-03-04 08:02 KST (bar=402)
- **경과 시간**: ~7시간 (사용자 기대: 2시간)

#### 근본 원인

**잘못된 설계**: `StalePositionFilter`가 **봉 개수** 기반으로 계산

```python
# core/filters/sell_filters.py:355 (변경 전)
required_bars = int(self.stale_hours * 60 / interval_min)
# 2.0시간 * 60분 / 1분 = 120봉

if bars_held >= required_bars:  # 120봉 경과 시 매도
```

**문제점**:
1. **interval_min 의존**: 1분봉 설정이지만 `set_interval_min()` 미호출로 기본값 1 유지
2. **실제 봉 간격 불일치**: 1분봉 설정이지만 실제로는 평균 3.5분 간격으로 생성됨
   - REST API 지연
   - 합성 봉 생성 간격
   - 서버 타이밍 이슈
3. **결과**: 120봉 = 실제로는 420분(7시간) 소요

**계산 검증**:
- 120봉 × 3.5분/봉 = 420분 = 7시간 ✅

#### 교훈

**"2.0시간"이라고 명시했으면 실제 시간으로 계산되어야 한다**

- ❌ **잘못된 설계**: 봉 개수 기반 (환경에 따라 2시간~7시간 가변)
- ✅ **올바른 설계**: 실제 경과 시간 기반 (정확히 2.0시간)

**일반 원칙**:
1. **UI/문서에 표시된 단위와 실제 구현 일치 필수**
   - "N시간" → `timedelta` 계산
   - "N봉" → 봉 개수 계산
2. **불확실성이 있는 간접 계산 금지**
   - 봉 간격은 이론적 값 (1분, 3분)이지 실제 값이 아님
3. **사용자 피드백 경청**
   > "정체 포지션 필터는 당연히 시간 기반으로 계산이 되어야지..."

#### 수정

**Before (잘못된 설계)**:
```python
# core/filters/sell_filters.py:331-422
def evaluate(self, **kwargs) -> FilterResult:
    position: PositionState = kwargs.get('position')
    current_price: float = kwargs.get('current_price')
    bars_held: int = kwargs.get('bars_held', 0)
    interval_min: int = kwargs.get('interval_min', 3)  # ❌ 의존

    # 필요 봉 개수 계산 (예: 2시간 = 120분 / 3분봉 = 40개)
    required_bars = int(self.stale_hours * 60 / interval_min)  # ❌ 간접 계산

    if bars_held >= required_bars:  # ❌ 봉 개수 기반
```

**After (올바른 설계)**:
```python
# core/filters/sell_filters.py:331-422
def evaluate(self, **kwargs) -> FilterResult:
    from datetime import datetime, timedelta

    position: PositionState = kwargs.get('position')
    current_price: float = kwargs.get('current_price')
    current_time: datetime = kwargs.get('current_time')  # ✅ 현재 시각

    if not position.has_position or position.entry_ts is None:
        return FilterResult(should_block=False, reason="NO_POSITION")

    # ✅ 실제 경과 시간 계산 (시간 기반)
    elapsed = current_time - position.entry_ts
    elapsed_hours = elapsed.total_seconds() / 3600

    if elapsed_hours >= self.stale_hours:  # ✅ 시간 기반
        max_gain = position.get_max_gain_from_entry()
        if max_gain is not None and max_gain < self.stale_threshold_pct:
            return FilterResult(should_block=True, reason="STALE_POSITION", ...)
```

**호출부 수정** (`strategy_incremental.py:740`):
```python
# Before
filter_result = self.sell_filter_manager.evaluate_all(
    position=position,
    current_price=current_price,
    bars_held=bars_held,  # ❌ 봉 개수
    interval_min=self.interval_min,  # ❌ 간격 추정
    ...
)

# After
filter_result = self.sell_filter_manager.evaluate_all(
    position=position,
    current_price=current_price,
    current_time=bar.ts,  # ✅ 현재 시각 (timezone-aware)
    ...
)
```

#### 영향 범위

- **파일 1**: `core/filters/sell_filters.py` (StalePositionFilter.evaluate 메서드)
- **파일 2**: `core/strategy_incremental.py` (IncrementalEMAStrategy.on_bar 메서드)
- **데이터**: `PositionState.entry_ts` 이미 존재하여 추가 작업 불필요

#### 검증 방법

```python
# 테스트 시나리오
# 1. 매수 진입: 2026-03-04 10:00:00
# 2. 설정: stale_hours=2.0
# 3. 현재 시각: 2026-03-04 12:00:01
# 4. 기대 결과: STALE_POSITION 매도 발생

position.entry_ts = datetime(2026, 3, 4, 10, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
current_time = datetime(2026, 3, 4, 12, 0, 1, tzinfo=ZoneInfo("Asia/Seoul"))
elapsed_hours = (current_time - position.entry_ts).total_seconds() / 3600
# elapsed_hours = 2.0003 > 2.0 ✅ 매도 발생
```

#### 사용자 피드백

> "💡 정체 포지션 필터: 2.0시간 동안 진입가 대비 최고 수익률이 1.0% 미만이면 강제 매도 >>> 정체 포지션 필터는 당연히 시간 기반으로 계산이 되어야지..."

**핵심 메시지**:
- ✅ 사용자가 옳다
- ❌ 구현이 잘못되었다
- 📝 즉시 수정 완료

---

