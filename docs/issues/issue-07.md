### 🔴 Issue #7: Trailing Stop 계산 방식 오류 (Peak-based → Profit-based)

**발생일**: 2026-03-05
**심각도**: 🔴 Critical (사용자 기대와 100% 불일치)

#### 문제

**사용자 설정**: Trailing Stop 10%

**사용자 기대**:
```
진입 ₩1,000 → 최고가 ₩1,500 → 수익 ₩500
하락 허용: 500 × 10% = ₩50
매도가: ₩1,450
```

**실제 동작 (기존 구현)**:
```
진입 ₩1,000 → 최고가 ₩1,500
하락 허용: 1,500 × 10% = ₩150
매도가: ₩1,350 ❌ (사용자 기대: ₩1,450)
```

#### 근본 원인

**잘못된 계산 방식**: Peak-based Trailing Stop (최고가 대비 하락률)
```python
# ❌ 기존 구현
drop_pct = (highest_price - current_price) / highest_price
```

**문제점**:
1. 최고가 기준 계산으로 하락 허용폭이 너무 넓음
2. "수익의 N%가 사라지면 매도"라는 사용자 의도와 불일치
3. Take Profit 도달 전에도 작동하여 초기 변동성에 취약

#### 교훈

**"사용자가 말한 그대로 구현하라"**

사용자: "1,500 - 1,000 = 500 수익에서 10% (50원) 하락 시 매도"
- ❌ 잘못된 이해: "최고가에서 10% 하락 시 매도"
- ✅ 올바른 이해: "벌어들인 수익의 10%가 사라지면 매도"

**일반 원칙**:
1. **사용자 요구사항을 수식으로 정확히 변환**
   - "수익의 10%" → `(수익) × 0.10`
   - NOT "최고가의 10%" → `(최고가) × 0.10`
2. **예시 시나리오로 검증 필수**
3. **관례적 구현보다 사용자 의도 우선**

#### 수정

**Before (Peak-based)**:
```python
# core/position_state.py
def arm_trailing_stop(self, threshold_pct, current_price):
    drop_pct = (self.highest_price - current_price) / self.highest_price
    return drop_pct >= threshold_pct
```

**After (Profit-based)**:
```python
# core/position_state.py
def arm_trailing_stop(self, threshold_pct, current_price):
    # ✅ 수익 기반 하락률
    max_profit = self.highest_price - self.avg_price  # 최대 수익
    profit_drop = self.highest_price - current_price  # 수익 손실
    profit_drop_pct = profit_drop / max_profit  # 수익 손실률

    return profit_drop_pct >= threshold_pct

def activate_trailing_stop(self, current_price):
    # ✅ NEW: Take Profit 도달 시 활성화
    self.trailing_armed = True
    self.highest_price = current_price
```

**추가 개선**:
1. **Take Profit 도달 후 활성화**: 최소 수익 확보 후에만 작동
2. **자동 전환**: Take Profit 도달 → Trailing Stop 자동 활성화
3. **Take Profit 필터 스킵**: `trailing_armed == True` 상태에서는 중복 체크 방지

#### 영향 범위

- **파일 1**: `core/position_state.py` (3개 메서드 수정)
- **파일 2**: `core/filters/sell_filters.py` (TrailingStopFilter, TakeProfitFilter)
- **파일 3**: `core/strategy_incremental.py` (TrailingStopFilter 생성 부분)

#### 비교표

| 구분 | Before (Peak-based) | After (Profit-based) |
|------|---------------------|----------------------|
| 계산 기준 | 최고가 대비 | **수익 금액 대비** |
| 하락 허용 (₩1,500 → 10%) | ₩150 | **₩50** |
| 매도가 | ₩1,350 | **₩1,450** |
| 최종 수익 | +35.0% | **+45.0%** |
| 활성화 조건 | 진입 즉시 | **Take Profit 도달 후** |
| 특징 | 공격적 | **보수적 (수익 보호)** |

#### 사용자 피드백

> "Trailing Stop을 잘못 이해하고 있다. 1,500 - 1,000 = 500 수익에서 10% (50원) 하락 시 매도하기. 1,450 매도 발동"

**핵심 메시지**:
- ✅ 사용자 설명이 명확했다
- ❌ 관례적 구현으로 오해했다
- 📝 수식으로 정확히 변환하여 수정 완료

**파일**: `core/position_state.py`, `core/filters/sell_filters.py`, `core/strategy_incremental.py`
**문서**: `thoughts/20260305-Trailing-Stop-Profit-Based.md`

---

