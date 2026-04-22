### 🔴 Issue #2: bar_time 9시간 오프셋 버그

**발생일**: 2026-03-03 20:15
**심각도**: 🔴 Critical (데이터 무결성 100% 손상)

#### 문제

DB에 저장된 `bar_time`이 실제 시각보다 9시간 이전 값으로 기록됨:

```
현재 시각: 2026-03-03 20:15:00 KST
bar_time:  2026-03-03 11:15:00+09:00  ❌ 9시간 오프셋
```

#### 근본 원인

```python
# ❌ 잘못된 코드
bar_ts_kst = bar.ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))
```

**왜 문제인가?**

- REST Reconcile 모드에서 `bar.ts`는 **UTC timezone-aware** 객체
- `.replace(tzinfo=...)` 메서드는:
  - 시각 값을 **변환하지 않음**
  - timezone **레이블만 강제로 변경**
  - `11:15:00 UTC` → `11:15:00 KST` (9시간 오프셋 발생)

**올바른 변환**:

```python
# ✅ 올바른 코드
bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
# 11:15:00 UTC → 20:15:00 KST (UTC +9시간)
```

#### 왜 놓쳤나?

1. **`.replace()` vs `.astimezone()` 차이를 정확히 이해하지 못함**
   - `.replace()`: 레이블 강제 변경 (값 유지)
   - `.astimezone()`: 실제 timezone 변환

2. **기존 코드 복사**: WS 모드 기반 기존 코드를 그대로 복사
   - WS 모드: timezone-naive 또는 이미 KST
   - REST Reconcile 모드: UTC timezone-aware (변환 필요)

3. **테스트 부족**: 실제 bar_time 값을 DB에서 확인하지 않음

#### 영향 범위

**총 9개 위치**에서 동일 버그 발생:
- `_execute_buy()`: 매수 평가 bar_time
- `_execute_sell()`: 매도 평가 bar_time
- `_log_buy_rejected()`: 매수 거부 로그 (2곳)
- `_log_sell_rejected()`: 매도 거부 로그 (3곳)
- `evaluate_sell()`: 매도 평가 (2곳)

#### 교훈

1. **Timezone 변환 시 `.astimezone()` 사용 필수**
   ```python
   # ✅ 올바른 패턴
   utc_time = datetime.now(ZoneInfo("UTC"))
   kst_time = utc_time.astimezone(ZoneInfo("Asia/Seoul"))

   # ❌ 잘못된 패턴 (절대 사용 금지)
   utc_time = datetime.now(ZoneInfo("UTC"))
   kst_time = utc_time.replace(tzinfo=ZoneInfo("Asia/Seoul"))
   ```

2. **모드 전환 시 가정 재검증**
   - WS 모드 → REST Reconcile 모드 전환 시
   - timezone-naive → timezone-aware 변경
   - 기존 코드 패턴이 여전히 유효한지 검증 필요

3. **End-to-End 검증 중요**
   - 코드 작성 후 실제 DB 값 확인
   - 단위 테스트만으로는 부족, 통합 테스트 필수

#### 수정

```python
# Before (잘못됨)
bar_ts_kst = bar.ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))

# After (올바름)
bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
```

**파일**: `core/strategy_engine.py` (9개 위치)
**라인**: 365, 435, 590, 609, 730, 774, 797, 892, 951
**문서**: `thoughts/20260303-REST-Reconcile-Hotfix-Timezone-Conversion.md`

---

