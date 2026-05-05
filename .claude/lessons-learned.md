# Upbit Tradebot MVP - 교훈 모음

> **총 교훈 수**: 12개 (CLAUDE.md Issue #1-#11 + 배포 검증)

**목적**: 과거 트러블슈팅 경험을 체계적으로 기록하여 동일한 실수 방지

---

## 📚 목차

- [교훈 #1: pyupbit 컬럼명 대소문자 불일치](#교훈-1-pyupbit-컬럼명-대소문자-불일치)
- [교훈 #2: bar_time 9시간 오프셋 버그](#교훈-2-bar_time-9시간-오프셋-버그)
- [교훈 #3: IndentationError (Mass Replace 부작용)](#교훈-3-indentationerror-mass-replace-부작용)
- [교훈 #4: REST API 지연으로 인한 현재 봉 미조회](#교훈-4-rest-api-지연으로-인한-현재-봉-미조회)
- [교훈 #5: EMA 증분 업데이트 누락 (Reconcile 재계산 후)](#교훈-5-ema-증분-업데이트-누락-reconcile-재계산-후)
- [교훈 #6: 정체 포지션 필터 - 봉 개수 기반 계산 (잘못된 설계)](#교훈-6-정체-포지션-필터---봉-개수-기반-계산-잘못된-설계)
- [교훈 #7: Trailing Stop 계산 방식 오류 (Peak-based → Profit-based)](#교훈-7-trailing-stop-계산-방식-오류-peak-based--profit-based)
- [교훈 #8: REST API 미확정 종가 반환 (Reconcile 후에도 미수정)](#교훈-8-rest-api-미확정-종가-반환-reconcile-후에도-미수정)
- [교훈 #9: BACKFILL 봉 중복 체크로 인한 audit UPDATE 미동작](#교훈-9-backfill-봉-중복-체크로-인한-audit-update-미동작)
- [교훈 #10: Enum 속성 접근 오류 (action.action → AttributeError)](#교훈-10-enum-속성-접근-오류-actionaction--attributeerror)
- [교훈 #11: BACKFILL이 실시간 지표를 오염시켜 Golden Cross 미감지](#교훈-11-backfill이-실시간-지표를-오염시켜-golden-cross-미감지)
- [교훈 #12: 배포 후 검증 규칙 위반 (서비스 상태 미확인)](#교훈-12-배포-후-검증-규칙-위반-서비스-상태-미확인)

---

## 교훈 #1: pyupbit 컬럼명 대소문자 불일치

**발생일**: 2026-03-03
**카테고리**: API
**심각도**: P0-Critical (100% 실패)

### 문제 상황

```python
df = pyupbit.get_ohlcv(...)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]  # ❌ KeyError!
```

**에러 메시지**:
```
KeyError: "None of [Index(['Open', 'High', 'Low', 'Close', 'Volume'], dtype='object')] are in the [columns]"
```

### 근본 원인

1. **가정**: pyupbit가 대문자 컬럼명을 반환할 것으로 가정
2. **실제**: pyupbit는 **소문자 컬럼명** 반환 (`open`, `high`, `low`, `close`, `volume`, `value`)
3. **왜 놓쳤나**: API 문서를 확인하지 않고 관례적으로 대문자를 가정함

### 해결 방법

```python
# ✅ 컬럼명 표준화 추가
df.columns = [col.capitalize() for col in df.columns]
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
```

**파일**: `core/rest_reconcile.py:98`

### 재발 방지 대책

1. **외부 라이브러리의 반환값은 반드시 문서 또는 실제 테스트로 확인**
2. **가정하지 말고, 검증하라** (REST Reconcile의 핵심 원칙과 동일)
3. **표준화 레이어 추가** (defensive programming)

### 체크리스트 (향후 작업 시)

- [ ] 외부 API 호출 시 반환 형식 실제 테스트
- [ ] 컬럼명, 데이터 타입, timezone 등 명시적으로 검증
- [ ] 표준화 레이어 추가

### 관련 문서

- `CLAUDE.md` Issue #1
- `thoughts/20260303-REST-Reconcile-Hotfix-Column-Names.md`

---

## 교훈 #2: bar_time 9시간 오프셋 버그

**발생일**: 2026-03-03
**카테고리**: 시스템
**심각도**: P0-Critical (데이터 무결성 100% 손상)

### 문제 상황

DB에 저장된 `bar_time`이 실제 시각보다 9시간 이전 값으로 기록됨:

```
현재 시각: 2026-03-03 20:15:00 KST
bar_time:  2026-03-03 11:15:00+09:00  ❌ 9시간 오프셋
```

### 근본 원인

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

### 해결 방법

```python
# ✅ 올바른 코드
bar_ts_kst = bar.ts.astimezone(ZoneInfo("Asia/Seoul"))
# 11:15:00 UTC → 20:15:00 KST (UTC +9시간)
```

**파일**: `core/strategy_engine.py` (9개 위치)
**라인**: 365, 435, 590, 609, 730, 774, 797, 892, 951

### 재발 방지 대책

1. **Timezone 변환 시 항상 `.astimezone()` 사용**
2. `.replace(tzinfo=...)` 사용 금지 (레이블 변경용으로만 사용)
3. 내부적으로 UTC 저장, 표시 시에만 현지 시각 변환
4. **모드 전환 시 가정 재검증** (WS 모드 → REST Reconcile 모드)

### 체크리스트 (향후 작업 시)

- [ ] Timezone 변환 시 `.astimezone()` 사용
- [ ] 기존 코드 패턴이 새 모드에서도 유효한지 검증
- [ ] End-to-End 테스트 (실제 DB 값 확인)

### 관련 문서

- `CLAUDE.md` Issue #2
- `thoughts/20260303-REST-Reconcile-Hotfix-Timezone-Conversion.md`

---

## 교훈 #3: IndentationError (Mass Replace 부작용)

**발생일**: 2026-03-03
**카테고리**: 기타
**심각도**: P1-High (구문 오류)

### 문제 상황

Edit tool의 `replace_all=true` 사용 시 여러 줄 문자열 치환 중 indentation 불일치 발생:

```python
                    # Comment line 1
                    # Comment line 2
        bar_ts_kst = bar.ts.astimezone(...)  # ❌ 8 spaces (should be 20)
                    insert_sell_eval(
```

### 근본 원인

- **Replace All의 한계**: 각 위치의 context (indentation level)를 고려하지 않음
- **Multi-line 패턴**: 주석 2줄 + 코드 1줄 치환 시 indentation 불일치

### 해결 방법

- 4개 위치 (lines 900, 960) 수동 수정
- Context 포함하여 unique pattern으로 개별 Edit 수행

### 재발 방지 대책

1. **Mass Replace 사용 시 주의**
   - `replace_all=true`는 단순 문자열 치환에만 사용
   - 여러 줄 치환 시 indentation 문제 발생 가능
2. **수정 후 즉시 검증**
   ```bash
   python3 -m py_compile <file>
   ```
3. **Context-aware Replace 필요 시 개별 수정**

### 체크리스트 (향후 작업 시)

- [ ] `replace_all=true` 사용 시 단순 단어/표현 치환만
- [ ] Multi-line 패턴은 개별 수정 (context 포함)
- [ ] 수정 후 즉시 `python3 -m py_compile` 검증

### 관련 문서

- `CLAUDE.md` Issue #3

---

## 교훈 #4: REST API 지연으로 인한 현재 봉 미조회

**발생일**: 2026-03-03 21:06~21:20
**카테고리**: API
**심각도**: P0-Critical (BUY/SELL 평가 로직 미동작)

### 문제 상황

봉 확정(Clock-Close) 감지 후 REST API 호출 시 현재 봉이 항상 누락됨:

```
2026-03-03 21:06:00 INFO | ⏰ [CLOCK-CLOSE] 봉 확정 감지 | ts=2026-03-03 21:06:00 KST
2026-03-03 21:06:08 INFO | [REST] 다중 호출 완료 | ... ~ 2026-03-03 21:03:00 KST
                                                           ❌ 21:06 봉 없음!
```

**패턴**:
- 항상 1~3분 이전 봉까지만 반환
- 21:06:00 close → 21:03:00까지 반환 (3분 지연)

### 근본 원인

1. **Upbit REST API 특성**:
   - 봉 확정 후 ~10-20초 지연 후 데이터 반영
   - WebSocket은 실시간, REST는 지연됨
2. **초기 Jitter 부족**: 8.0초 Jitter 사용했으나 실제로는 15초 이상 필요
3. **재시도 대기 부족**: 초기 재시도 로직이 2초 대기 후 1회만

### 해결 방법

**Step 1: Jitter 증가 (8.0s → 15.0s)**
```python
# core/data_feed.py:50
JITTER_BY_INTERVAL = {
    "minute1": 15.0,  # 1분봉: 종가 확정 대기
}
```

**Step 2: Progressive Retry (5s → 8s → 10s)**
```python
# engine/live_loop.py:691-738
retry_waits = [5, 8, 10]
for retry_num, wait_sec in enumerate(retry_waits, start=1):
    logger.info(f"🔄 [RETRY-{retry_num}] {wait_sec}초 대기 후 재조회...")
    time.sleep(wait_sec)
    retry_df = safe_fetch_rest(...)
    if retry_df is not None and closed_ts in retry_df.index:
        retry_success = True
        break
```

**총 대기 시간**: Main Jitter 15초 + Retry 최대 23초 = 38초

### 재발 방지 대책

1. **기존 동작하는 코드를 먼저 참조하라**
   - `data_feed.py`에 이미 JITTER_BY_INTERVAL 구현됨
2. **외부 API 지연은 문서보다 실제 테스트로 확인**
3. **Progressive Retry 패턴** 적용

### 체크리스트 (향후 작업 시)

- [ ] 외부 API 지연 실제 테스트
- [ ] Progressive Retry 구현
- [ ] Fallback 전략 수립 (봉 스킵 vs WebSocket 임시 사용)

### 관련 문서

- `CLAUDE.md` Issue #4

---

## 교훈 #5: EMA 증분 업데이트 누락 (Reconcile 재계산 후)

**발생일**: 2026-03-03 22:00
**카테고리**: 전략
**심각도**: P0-Critical (EMA 값 정지, BUY/SELL 평가 로직 100% 오작동)

### 문제 상황

REST Reconcile 모드에서 매 분봉마다 **EMA 값이 동일**하게 유지됨:

```
bar=201 | price=2697.00 | ema_fast=2711.37 | ema_slow=2715.94
bar=202 | price=2673.00 | ema_fast=2711.37 | ema_slow=2715.94  ❌ 같음
bar=203 | price=2667.00 | ema_fast=2711.37 | ema_slow=2715.94  ❌ 같음
```

### 근본 원인

**`strategy_engine.py:on_new_bar_confirmed()` 라인 286-296**:

```python
elif changed_count > 0:
    # ✅ Reconcile 변경 발생 → 부분 재계산
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)
    # ❌ 문제: 재계산 후 현재 봉 반영 없음!
```

**왜 문제인가?**

- `recompute_from_changed_ts`: 과거 데이터로 재시드 (현재 봉 미포함)
- **현재 봉(`bar.close`)은 반영되지 않음** → EMA 정지

### 해결 방법

```python
# strategy_engine.py:286-301
elif changed_count > 0:
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)

    # ✅ 재계산 후 현재 봉 반영 (CRITICAL!)
    self.indicators.update_incremental(bar.close)
```

### 재발 방지 대책

1. **분기별 일관성 검증 필수**
   - 모든 분기에서 현재 봉 반영 확인
2. **함수 책임 명확화**
   - `recompute_from_changed_ts`: 과거 데이터로 재시드
   - `update_incremental`: 현재 봉 증분 반영
3. **End-to-End 검증 필수**

### 체크리스트 (향후 작업 시)

- [ ] 모든 분기에서 현재 봉 반영 확인
- [ ] 실제 로그로 EMA 값 변화 검증
- [ ] `recompute` 후 항상 `update_incremental` 호출

### 관련 문서

- `CLAUDE.md` Issue #5

---

## 교훈 #6: 정체 포지션 필터 - 봉 개수 기반 계산 (잘못된 설계)

**발생일**: 2026-03-04
**카테고리**: 전략
**심각도**: P0-Critical (사용자 기대와 100% 불일치)

### 문제 상황

**사용자 설정**: 2.0시간 동안 수익률 1.0% 미만이면 강제 매도

**사용자 기대**: 정확히 **2.0시간** 경과 후 매도

**실제 동작**:
- 매수: 2026-03-04 01:05 (bar=282)
- 매도: 2026-03-04 08:02 (bar=402)
- **경과 시간**: ~7시간 (사용자 기대: 2시간)

### 근본 원인

**잘못된 설계**: `StalePositionFilter`가 **봉 개수** 기반으로 계산

```python
# ❌ 잘못된 구현
required_bars = int(self.stale_hours * 60 / interval_min)
# 2.0시간 * 60분 / 1분 = 120봉

if bars_held >= required_bars:  # 120봉 경과 시 매도
```

**문제점**:
- 실제 봉 간격은 평균 3.5분 (REST API 지연, 서버 타이밍)
- 120봉 × 3.5분/봉 = 420분 = 7시간

### 해결 방법

```python
# ✅ 올바른 설계 (시간 기반)
from datetime import datetime, timedelta

elapsed = current_time - position.entry_ts
elapsed_hours = elapsed.total_seconds() / 3600

if elapsed_hours >= self.stale_hours:  # 정확히 2.0시간
```

### 재발 방지 대책

1. **"N시간"이라고 명시했으면 실제 시간으로 계산**
2. **UI/문서에 표시된 단위와 실제 구현 일치 필수**
3. **불확실성이 있는 간접 계산 금지**
4. **사용자 피드백 경청**

### 체크리스트 (향후 작업 시)

- [ ] 시간 기반 계산인지 확인 (`timedelta` 사용)
- [ ] 봉 간격 의존성 제거
- [ ] 사용자 요구사항과 실제 구현 일치 검증

### 관련 문서

- `CLAUDE.md` Issue #6

---

## 교훈 #7: Trailing Stop 계산 방식 오류 (Peak-based → Profit-based)

**발생일**: 2026-03-05
**카테고리**: 전략
**심각도**: P0-Critical (사용자 기대와 100% 불일치)

### 문제 상황

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

### 근본 원인

**잘못된 계산 방식**: Peak-based Trailing Stop (최고가 대비 하락률)

```python
# ❌ 기존 구현
drop_pct = (highest_price - current_price) / highest_price
```

### 해결 방법

```python
# ✅ Profit-based (수익 금액 대비)
max_profit = self.highest_price - self.avg_price  # 최대 수익
profit_drop = self.highest_price - current_price  # 수익 손실
profit_drop_pct = profit_drop / max_profit  # 수익 손실률

return profit_drop_pct >= threshold_pct
```

**추가 개선**:
- Take Profit 도달 후 활성화
- 자동 전환

### 재발 방지 대책

1. **"사용자가 말한 그대로 구현하라"**
2. **사용자 요구사항을 수식으로 정확히 변환**
3. **예시 시나리오로 검증 필수**
4. **관례적 구현보다 사용자 의도 우선**

### 체크리스트 (향후 작업 시)

- [ ] 사용자 설명을 수식으로 변환
- [ ] 예시 시나리오 검증 (₩1,000 → ₩1,500 → ₩1,450)
- [ ] 최종 결과가 사용자 기대와 일치하는지 확인

### 관련 문서

- `CLAUDE.md` Issue #7
- `thoughts/20260305-Trailing-Stop-Profit-Based.md`

---

## 교훈 #8: REST API 미확정 종가 반환 (Reconcile 후에도 미수정)

**발생일**: 2026-03-15
**카테고리**: API
**심각도**: P0-Critical (매매 판단 오류, 0.3% 가격 차이)

### 문제 상황

**DB 기록**: 15:31 봉 종가 = 2950
**Upbit 차트**: 15:31 봉 종가 = 2941
**차이**: +9원 (0.3% 오차)

### 근본 원인

1. **Upbit REST API 특성**:
   - 봉 확정 후에도 ~1분간 미확정 데이터 반환 가능
2. **현재 구조의 한계**:
   - Jitter 15초 설정했지만 부족
   - `safe_fetch_rest` 사용 → `fetch_confirmed_candle` 미사용
   - 봉 간 일관성 검증 없음

### 해결 방법

**`fetch_confirmed_candle` 함수 사용**:
```python
# engine/live_loop.py:674-709
confirmed_row = fetch_confirmed_candle(
    ticker=params.upbit_ticker,
    timeframe=params.interval,
    closed_ts=closed_ts,
    max_retry=3  # Progressive Retry
)

# 미확정 종가 덮어쓰기
if confirmed_row is not None and rest_df is not None:
    if closed_ts in rest_df.index:
        rest_df.loc[closed_ts] = confirmed_row
```

**CandleValidator 개선**:
```python
# 봉 일관성 검증 (open[n] ≈ close[n-1])
if abs(open_ - self.prev_close) / self.prev_close > continuity_tolerance_pct:
    logger.warning(f"[VALIDATOR] 봉 불연속 감지 ⚠️")
```

### 재발 방지 대책

1. **WO-2026-001에서 구현한 함수를 실제로 사용**
2. **봉 일관성 검증 필수**
3. **API 지연은 문서보다 실제 테스트로 확인**

### 체크리스트 (향후 작업 시)

- [ ] `fetch_confirmed_candle` 함수 사용
- [ ] Progressive Retry 구현
- [ ] 봉 일관성 검증 추가

### 관련 문서

- `CLAUDE.md` Issue #8
- `docs/analysis/close-price-analysis.md`
- `docs/work-orders/2026-001-confirmed-candle.md`

---

## 교훈 #9: BACKFILL 봉 중복 체크로 인한 audit UPDATE 미동작

**발생일**: 2026-03-16
**카테고리**: 시스템
**심각도**: P0-Critical (미확정 종가가 DB에 그대로 유지됨)

### 문제 상황

BACKFILL이 실행되어 확정 종가로 재평가했지만, DB audit 로그가 UPDATE되지 않음:

```
2026-03-16 19:48  |  Upbit=3186  |  Tradebot DB=3189  ❌ (+3원 차이)
```

### 근본 원인

**`strategy_engine.py:260-262` 중복 봉 체크**:

```python
# ✅ 중복 방지
if not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return  # ← audit 로그 기록 없이 종료
```

**BACKFILL 시나리오**:
1. 19:48분: 현재 봉(n) 처리 → DB INSERT
2. 19:49분: BACKFILL로 19:48 봉 재평가 → **중복으로 간주되어 return** → DB UPDATE 안 됨

### 해결 방법

```python
# strategy_engine.py:259-265
backfill_mode = diff_summary.get("backfill_mode", False)
if not backfill_mode and not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return  # BACKFILL 모드는 우회
```

### 재발 방지 대책

1. **"재평가"는 "중복"이 아니다**
2. **Early return의 숨겨진 부작용 검증**
3. **End-to-End 검증** (BACKFILL 후 DB 값 확인)

### 체크리스트 (향후 작업 시)

- [ ] BACKFILL 모드 여부 확인
- [ ] 중복 체크 우회
- [ ] audit UPDATE 로그 확인

### 관련 문서

- `CLAUDE.md` Issue #9

---

## 교훈 #10: Enum 속성 접근 오류 (action.action → AttributeError)

**발생일**: 2026-03-24
**카테고리**: 기타
**심각도**: P0-Critical (엔진 중단 100% 재현)

### 문제 상황

봇이 bar=201 평가 후 반복적으로 중단됨:

```
2026-03-24 09:09:36 | bar=201 평가 완료
❌ 예외: AttributeError: 'Action' object has no attribute 'action'
🛑 엔진 종료
```

### 근본 원인

**`strategy_engine.py:274, 415` Enum 속성 오접근**:

```python
# ❌ 잘못된 코드
logger.debug(f"action={action.action if action else 'NONE'}")
```

**왜 문제인가?**

- `Action`은 Python Enum 클래스
- Enum 객체의 속성: `.value`, `.name`
- ❌ `.action`: **존재하지 않음** → AttributeError

### 해결 방법

```python
# ✅ 올바른 Enum 사용
logger.debug(f"action={action.value if action else 'NONE'}")
```

### 재발 방지 대책

1. **Python 기본 타입 속성 명확히 이해**
2. **디버그 코드도 테스트 필수**
3. **Early Warning 시스템 부족** (초기화 단계에서 기본 검증)

### 체크리스트 (향후 작업 시)

- [ ] Enum 사용 시 `.value` 또는 `.name` 확인
- [ ] 디버그 로그도 런타임 에러 발생 가능
- [ ] 모든 코드 경로 테스트 필요

### 관련 문서

- `CLAUDE.md` Issue #10

---

## 교훈 #11: BACKFILL이 실시간 지표를 오염시켜 Golden Cross 미감지

**발생일**: 2026-03-25
**카테고리**: 전략
**심각도**: P0-Critical (Golden Cross 타이밍 100% 놓침)

### 문제 상황

Dead Cross → Golden Cross 전환 시점인데 매수 신호가 발생하지 않음:

```
2026-03-24 16:50:35 | bar=2856 | Dead Cross | ema_fast=3210.14 < ema_slow=3211.88
2026-03-24 16:52:30 | bar=2857 | Golden Cross (BACKFILL) → BUY 신호
2026-03-24 16:53:06 | bar=2857 | Golden Cross (실시간) → NO_SIGNAL ❌
```

### 근본 원인

**BACKFILL이 지표 상태(`prev_ema_fast`, `prev_ema_slow`)를 덮어씀**:

```python
# BACKFILL에서 update_incremental 호출
update_incremental(bar.close)  # ← prev 값을 덮어씀!
```

**결과**:
- 실시간 봉에서 `prev = BACKFILL에서 업데이트된 값`이 됨
- **16:50 Dead → 16:52 Golden 변화를 추적하지 못함**

### 해결 방법

**핵심 원리: BACKFILL 전후로 지표 상태 백업/복원**

```python
# engine/live_loop.py:750-859
if backfill_ts_list:
    # ✅ BACKFILL 전 지표 상태 백업
    saved_indicators = {
        'ema_fast': engine.indicators.ema_fast,
        'prev_ema_fast': engine.indicators.prev_ema_fast,
        ...
    }

    # BACKFILL 처리
    for ts in sorted(backfill_ts_list):
        engine.on_new_bar_confirmed(bar, ...)

    # ✅ BACKFILL 후 지표 상태 복원
    engine.indicators.ema_fast = saved_indicators['ema_fast']
    engine.indicators.prev_ema_fast = saved_indicators['prev_ema_fast']
    ...
```

### 재발 방지 대책

1. **BACKFILL은 실시간 상태를 오염시켜선 안 된다**
2. **이전 상태(`prev`) 추적이 크로스 감지의 핵심**
3. **수정 시 모든 경로 검증 필수** (BACKFILL 경로 포함)

### 체크리스트 (향후 작업 시)

- [ ] BACKFILL 전 지표 상태 백업
- [ ] BACKFILL 후 지표 상태 복원
- [ ] prev 값들이 정확히 복원되었는지 확인

### 관련 문서

- `CLAUDE.md` Issue #11
- `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md`

---

## 교훈 #12: 배포 후 검증 규칙 위반 (서비스 상태 미확인)

**발생일**: 2026-05-05
**카테고리**: 운영
**심각도**: P0-Critical (사용자가 직접 에러 발견)

### 문제 상황

**배포 후 검증 없이 "배포 완료" 보고**:

```
Timeline:
16:10 - order_ratio 수정 완료 (core/trader.py, ui/sidebar.py)
16:15 - Git commit & push 성공
16:16 - "✅ 배포 완료" 보고 ❌

실제 서버 상태:
- Streamlit 서비스: 재시작 안 함
- 기존 버그: st.switch_page() 경로 오류로 페이지 네비게이션 실패
- 에러 로그: StreamlitAPIException 지속 발생

사용자 피드백:
"지금 서버 에러나고 있다. 배포 후 검증하라는 규칙을 왜 지키지 않는가?"
```

**결과**: 사용자가 직접 에러를 발견하고 지적함

### 근본 원인

1. **체크리스트 미준수**
   - 배포 절차 7단계 중 4, 5, 6단계 생략
   - Git push만 하고 서버 검증 건너뜀

2. **빠른 작업 완료에만 집중**
   - "코드 수정 → Git push → 완료" 단순 사고
   - 검증의 중요성 간과

3. **검증 단계에 대한 인식 부족**
   - "배포 = Git push" 로 잘못 이해
   - 실제 서비스 동작 확인 필수성 미인지

**생략한 단계**:
```bash
# ❌ 4단계: 서버 배포
ssh ... && git pull && systemctl restart tradebot  # 실행 안 함

# ❌ 5단계: 서비스 상태 확인
systemctl status tradebot  # 확인 안 함

# ❌ 6단계: 에러 로그 확인
journalctl -u tradebot -n 30  # 확인 안 함

# ❌ 7단계: UI 접속 검증
# 브라우저로 실제 동작 확인 안 함
```

### 해결 방법

**즉시 조치 (2026-05-05 17:00)**:

```bash
# 1. 실제 에러 확인
tail -100 streamlit.log
# → StreamlitAPIException: Could not find page: `dashboard`

# 2. 근본 원인 파악
# → st.switch_page("dashboard") 사용 (잘못된 경로)
# → 올바른 경로: st.switch_page("pages/dashboard.py")

# 3. 5개 파일 수정
# pages/set_buy_sell_conditions.py
# pages/dashboard.py (2곳)
# pages/confirm_init_db.py
# pages/audit_viewer.py

# 4. 재배포 + 검증 완료
git commit && git push
ssh ... && git pull
systemctl restart tradebot
systemctl status tradebot  # ✅ active (running)
journalctl -u tradebot -n 30  # ✅ 에러 없음
```

**7단계 배포 체크리스트 수립**:

```
✅ 1단계: 로컬 테스트 완료
✅ 2단계: Git commit & push
✅ 3단계: 서버 배포 (git pull + systemctl restart)
✅ 4단계: 서비스 상태 확인 (systemctl status)
✅ 5단계: 에러 로그 확인 (journalctl / tail log)
✅ 6단계: UI 접속 검증 (브라우저 확인)
✅ 7단계: 최종 보고 (검증 완료 후)
```

### 재발 방지 대책

1. **체크리스트 엄격 준수**
   - 모든 배포는 7단계 완료 후 보고
   - 각 단계별 확인 로그 필수 기록

2. **검증 로그 템플릿**
   ```markdown
   ## 배포 검증 보고

   ✅ 1. 로컬 테스트: pytest 통과 (23/23)
   ✅ 2. Git push: 커밋 해시 d8989ab
   ✅ 3. 서버 pull: Fast-forward 성공
   ✅ 4. 서비스 재시작: systemctl restart tradebot
   ✅ 5. 서비스 상태: active (running)
   ✅ 6. 에러 로그: 에러 없음 (최근 30줄 확인)
   ✅ 7. UI 접속: 대시보드 정상 표시

   **배포 완료 시각**: 2026-05-05 17:10 KST
   ```

3. **자동화 검토 (장기)**
   - 배포 스크립트에 검증 단계 포함
   - 서비스 상태 체크 자동화

4. **사용자 기대치 관리**
   - "배포 중"과 "배포 완료"를 명확히 구분
   - 검증 완료 전까지는 "검증 중" 상태 유지

### 체크리스트 (향후 작업 시)

**배포 시**:
- [ ] 로컬 테스트 완료 (unit test, integration test)
- [ ] Git commit & push 성공
- [ ] 서버 git pull 성공
- [ ] systemctl restart 성공
- [ ] systemctl status → active (running) 확인
- [ ] journalctl / tail log → 에러 없음 확인
- [ ] 브라우저 UI 접속 → 정상 동작 확인
- [ ] 최종 보고 작성 (검증 로그 포함)

**보고 시**:
- [ ] "배포 완료"는 모든 검증 완료 후에만 사용
- [ ] 검증 로그 템플릿 작성
- [ ] 사용자 확인 필요한 부분 명시

### 관련 문서

- `.claude/context/project-rules.md` - 개발 방법론 (워크플로우 섹션)
- 실제 발생한 버그: st.switch_page() 경로 오류 (Git 커밋 08639cc)

---

## 🎯 핵심 원칙 (재발 방지)

### 1. "추정하지 말고, 검증하라" (Don't Assume, Verify)

REST Reconcile의 핵심 원칙을 코딩에도 적용

### 2. "레이블이 아닌, 실제 변환" (Convert, Not Replace)

`.replace(tzinfo=...)` 금지 → `.astimezone()` 사용

### 3. "단위 테스트 + 통합 테스트" (Unit + Integration)

코드 작성 후 실제 DB 값, 로그 확인

### 4. "방어적 코딩" (Defensive Programming)

외부 API 반환값 표준화 레이어 추가

### 5. "사용자가 말한 그대로 구현하라"

요구사항을 수식으로 정확히 변환 → 예시 시나리오로 검증

### 6. "BACKFILL은 실시간 상태를 오염시켜선 안 된다"

상태 백업/복원 패턴 필수

### 7. "배포는 검증 완료 후에만 완료된다" (Deployment = Verification)

**7단계 배포 체크리스트 엄격 준수**:
```
1. 로컬 테스트 완료
2. Git commit & push
3. 서버 배포 (git pull + systemctl restart)
4. 서비스 상태 확인 (systemctl status)
5. 에러 로그 확인 (journalctl / tail log)
6. UI 접속 검증 (브라우저 확인)
7. 최종 보고 (검증 로그 포함)
```

**원칙**:
- Git push ≠ 배포 완료
- 서비스 재시작 확인 필수
- 에러 로그 확인 필수
- 실제 동작 검증 필수
- 모든 단계 완료 전까지는 "검증 중" 상태

---

**최종 업데이트**: 2026-05-05
**작성자**: Claude Code (AI Assistant)
**기반 문서**: CLAUDE.md Issue #1-#11 + 배포 검증 (교훈 #12)
**관련 문서**: `.claude/context/project-rules.md`
