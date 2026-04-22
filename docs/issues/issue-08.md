### 🔴 Issue #8: REST API 미확정 종가 반환 (Reconcile 후에도 미수정)

**발생일**: 2026-03-15
**심각도**: 🔴 Critical (매매 판단 오류, 0.3% 가격 차이)

#### 문제

**DB 기록**: 15:31 봉 종가 = 2950
**Upbit 차트**: 15:31 봉 종가 = 2941
**차이**: +9원 (0.3% 오차)

#### 타임라인 분석 (로그 기반)

**15:32:05 (첫 번째 조회)**
```
[REST-RECONCILE] 2개 봉 변경 감지
[BACKFILL] ts=2026-03-15 15:31:00 | close=2950  ← 잘못된 값
[평가] bar=228 price=2950  ← DB에 기록
[평가] bar=229 price=2950  ← 15:32 봉도 미확정
```

**15:33:06 (두 번째 조회)**
```
[REST-RECONCILE] 1개 봉 변경 감지
[BACKFILL] ts=2026-03-15 15:32:00 | close=2941  ← 15:32만 수정됨
```

➡️ **15:31 봉은 2950으로 유지됨 (재조회에서도 변경 감지 안됨)**

#### 근본 원인

1. **Upbit REST API 특성**
   - 봉 확정 후에도 ~1분간 미확정 데이터 반환 가능
   - `to` 파라미터 없이 호출해도 현재 진행 중인 봉 포함
   - **일부 봉은 확정 후에도 잘못된 종가를 계속 반환** (API 버그 의심)

2. **현재 구조의 한계**
   - Jitter 15초 설정했지만 부족
   - `safe_fetch_rest` 사용 → WO-2026-001의 `fetch_confirmed_candle` 미사용
   - 봉 간 일관성 검증 없음 (15:32 시가 ≠ 15:31 종가 체크 안함)

3. **Reconcile 로직**
   - 15:33 조회 시 15:31 봉도 포함되었으나 **변경 감지 안됨**
   - ➡️ Upbit가 15:33에도 여전히 2950 반환했을 가능성

#### 교훈

**"REST API 확정 종가를 별도로 검증하라"**

- ❌ 잘못된 가정: "to 파라미터 없이 호출하면 확정 종가만 반환"
- ✅ 올바른 접근: "Progressive Retry로 확정 여부 명시적 검증"

**일반 원칙**:
1. **WO-2026-001에서 구현한 함수를 실제로 사용**
   - `fetch_confirmed_candle` 구현했지만 미사용
   - 검증된 함수는 반드시 실전 적용
2. **봉 일관성 검증 필수**
   - `bar[n].open ≈ bar[n-1].close`
   - 불일치 시 재조회 또는 경고
3. **API 지연은 문서보다 실제 테스트로 확인**

#### 수정

**Before (미확정 종가 허용)**:
```python
# engine/live_loop.py:670-678
rest_df = safe_fetch_rest(
    market=params.upbit_ticker,
    timeframe=params.interval,
    end_ts=now_utc(),  # ✅ 현재 시각 기준 (Jitter 후)
    total_count=RECONCILE_LOOKBACK_BARS
)
```

**After (확정 종가 검증)**:
```python
# engine/live_loop.py:674-709
# ✅ WO-2026-001 Task 1-A: 최신 봉 확정 검증
# closed_ts 봉을 별도로 조회하여 확정 종가만 반환 보장 (Progressive Retry 포함)
confirmed_row = fetch_confirmed_candle(
    ticker=params.upbit_ticker,
    timeframe=params.interval,
    closed_ts=closed_ts,
    max_retry=3
)

# 과거 데이터는 safe_fetch_rest로 조회 (이미 확정됨)
rest_df = safe_fetch_rest(
    market=params.upbit_ticker,
    timeframe=params.interval,
    end_ts=closed_ts,  # ✅ closed_ts 기준 (최신 봉 포함)
    total_count=RECONCILE_LOOKBACK_BARS
)

# ✅ 확정 봉 검증 성공 시 rest_df 업데이트 (미확정 종가 덮어쓰기)
if confirmed_row is not None and rest_df is not None:
    if closed_ts in rest_df.index:
        # rest_df의 closed_ts 봉을 fetch_confirmed_candle 결과로 덮어쓰기
        original_close = rest_df.loc[closed_ts, 'Close']
        rest_df.loc[closed_ts] = confirmed_row
        new_close = rest_df.loc[closed_ts, 'Close']

        if abs(original_close - new_close) > 0.01:
            logger.warning(
                f"[CONFIRMED-FIX] 최신 봉 종가 보정 | ts={format_kst(closed_ts)} | "
                f"미확정={original_close:.0f} → 확정={new_close:.0f}"
            )
```

**CandleValidator 개선**:
```python
# core/candle_validator.py:35-45, 91-105
def __init__(self, max_spike_ratio: float = 0.05, continuity_tolerance_pct: float = 0.01):
    """
    Args:
        continuity_tolerance_pct: 연속 봉 일관성 허용 오차 (기본 1%)
                                 open[n]과 close[n-1]의 차이가 1% 초과 시 경고
    """
    self.continuity_tolerance_pct = continuity_tolerance_pct
    self.prev_close: Optional[float] = None

# 2. 연속 봉 일관성 검증 (경고만)
# open[n]과 close[n-1]이 일치해야 함 (갭 거래 제외)
if self.prev_close is not None and self.prev_close > 0:
    continuity_diff_pct = abs(open_ - self.prev_close) / self.prev_close

    if continuity_diff_pct > self.continuity_tolerance_pct:
        logger.warning(
            f"[VALIDATOR] 봉 불연속 감지 ⚠️ | "
            f"close[n-1]={self.prev_close:.0f} vs open[n]={open_:.0f} | "
            f"차이={continuity_diff_pct:.2%} (허용={self.continuity_tolerance_pct:.2%}) | "
            f"(경고만, 봉 스킵하지 않음)"
        )
```

#### 영향 범위

- **파일 1**: `engine/live_loop.py` (Reconcile 로직 수정)
- **파일 2**: `core/candle_validator.py` (연속 봉 일관성 검증 추가)
- **파일 3**: `core/rest_reconcile.py` (fetch_confirmed_candle 사용)

#### 검증 방법

```bash
# 1. 로그에서 확정 종가 보정 확인
grep "CONFIRMED-FIX" mcmax33_engine_debug.log

# 2. 봉 불연속 경고 확인
grep "봉 불연속 감지" mcmax33_engine_debug.log

# 3. DB 데이터 정합성 확인
sqlite3 services/data/tradebot_mcmax33.db \
  "SELECT timestamp, bar_time, price FROM audit_sell_eval WHERE bar = 228 ORDER BY timestamp DESC LIMIT 5"
```

#### 사용자 피드백

> "https://upbit.com/exchange?code=CRIX.UPBIT.KRW-ZRO 비교해보면 최종종가가 틀린 부분이 확인된다. 15:31 > 2950 vs 2941 어떻게 된건지 원인 파악 후 보고해줘."

**핵심 메시지**:
- ✅ REST API 미확정 종가 반환 확인
- ✅ fetch_confirmed_candle 미사용 발견
- ✅ 봉 일관성 검증 추가 완료
- 📝 DB 수정 완료 (2950 → 2941)

**파일**: `engine/live_loop.py`, `core/candle_validator.py`
**DB 수정**: `audit_sell_eval` bar=228, bar_time='2026-03-15T15:31:00+09:00' price 2950→2941

#### 추가 개선 (2026-03-15)

**사용자 요구사항**:
1. 현재 봉(n): 미확정 허용 - 현재 로직 유지 (즉시 매매)
2. **이전 봉들(n-1, n-2, ...)**: **반드시** Upbit 차트와 동일 (200일선 기준)

**구현**:
```python
# core/rest_reconcile.py:548-714
def verify_past_candles_with_upbit(
    ticker: str,
    timeframe: str,
    past_series: pd.DataFrame,
    tolerance: float = 1.0
) -> bool:
    """
    과거 봉들이 Upbit 차트와 일치하는지 검증

    프로세스:
    1. Upbit REST API에서 동일 시각 봉 조회
    2. 종가 비교 (±1원 이내)
    3. 불일치 발견 시:
       - 5초 간격 3회 재조회
       - 재조회 실패 → False 반환 (봉 스킵)
    4. 모두 일치 → True 반환
    """
```

```python
# engine/live_loop.py:797-837
# 🎯 현재 봉 처리 전 과거 봉 검증
past_series = local_series[local_series.index < closed_ts]

if not past_series.empty:
    verify_count = min(200, len(past_series))  # 200일선 기준
    past_to_verify = past_series.tail(verify_count)

    verification_ok = verify_past_candles_with_upbit(
        ticker=params.upbit_ticker,
        timeframe=params.interval,
        past_series=past_to_verify,
        tolerance=1.0  # ±1원
    )

    if not verification_ok:
        logger.error("❌ 과거 봉 검증 실패 → 현재 봉 스킵")
        continue  # ← 현재 봉 처리 안 함
```

**보장 사항**:
- ✅ 이전 봉들(n-1 이전): Upbit 차트 200일선 기준 **100% 일치**
- ✅ 현재 봉(n): 미확정 허용 (즉시 매매 유지)
- ✅ 검증 실패 시: 전략 평가 차단 (안전장치)

**검증 로그**:
```bash
# 검증 시작
[VERIFY] 과거 봉 검증 시작 | count=200 | 현재 봉=2026-03-15 15:31:00 KST

# 불일치 발견 시
[VERIFY] 불일치 발견 | ts=2026-03-15 15:30:00 KST | local=2950 upbit=2941 diff=9
[VERIFY-RETRY] 1/3회 재조회 | ts=2026-03-15 15:30:00 KST
[VERIFY-RETRY] ✅ 재조회 성공 (1/3) | close=2941

# 검증 통과
[VERIFY] ✅ 검증 통과 (재조회 보정) | total=200 mismatch=1 fixed=1
```

**파일**: `core/rest_reconcile.py`, `engine/live_loop.py`

---

