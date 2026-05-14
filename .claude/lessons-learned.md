# Upbit Tradebot MVP - 교훈 모음

> **총 교훈 수**: 18개 (CLAUDE.md Issue #1-#11 + Streamlit UI #12-#16 + Filter Logic #17 + State Management #19)

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
- [교훈 #13: Streamlit 버전별 query_params 지원 차이 (웹 검색만으로 검증 실패)](#교훈-13-streamlit-버전별-query_params-지원-차이-웹-검색만으로-검증-실패)
- [교훈 #14: session_state 동기화 누락으로 인한 데이터 손실](#교훈-14-session_state-동기화-누락으로-인한-데이터-손실)
- [교훈 #15: Streamlit 멀티페이지 경로 오류 (.py 확장자 포함)](#교훈-15-streamlit-멀티페이지-경로-오류-py-확장자-포함)
- [교훈 #16: 워크플로우 위반 (사용자 승인 없이 서버 배포 2차)](#교훈-16-워크플로우-위반-사용자-승인-없이-서버-배포-2차)
- [교훈 #17: Dead Cross 상태에서 HTS 매수 시 즉시 자동매도 (필터 순서 문제)](#교훈-17-dead-cross-상태에서-hts-매수-시-즉시-자동매도-필터-순서-문제)
- [교훈 #19: 편협적 수정으로 인한 데이터 흐름 누락 (전체 영향 범위 미고려)](#교훈-19-편협적-수정으로-인한-데이터-흐름-누락-전체-영향-범위-미고려)

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

## 교훈 #13: Streamlit 버전별 query_params 지원 차이 (웹 검색만으로 검증 실패)

**발생일**: 2026-05-06
**카테고리**: UI
**심각도**: P0-Critical (전체 페이지 네비게이션 실패)

### 문제 상황

**사용자 보고**: LIVE 모드 로그인 → Dashboard → 다른 페이지 이동 → Dashboard 복귀 시 TEST 모드로 변경됨

**시도한 해결 방법**:
```python
# ❌ 첫 번째 시도 (웹 검색 기반)
st.switch_page("pages/dashboard.py", query_params={"mode": "LIVE", ...})
```

**에러 발생**:
```
TypeError: switch_page() got an unexpected keyword argument 'query_params'
Traceback:
  File "/root/upbit-tradebot-mvp/pages/dashboard.py", line 1969
```

**사용자 피드백**:
```
"문법 제대로 검증 후 적용하라고 했는데... 왜 이렇게 말을 안듣나?"
```

### 근본 원인

1. **웹 검색만으로 Streamlit 문법 확인**
   - 최신 Streamlit 문서를 검색하여 `st.switch_page(query_params=...)` 발견
   - 서버의 실제 Streamlit 버전(1.46.0) 확인 안 함

2. **버전 차이 미인지**
   - `query_params` 파라미터는 Streamlit 1.48+ 이후 추가됨
   - 서버 버전: 1.46.0 (2025년 6월 릴리스) → 지원 안 함

3. **실제 환경 검증 생략**
   - 로컬/서버 환경에서 실제 테스트 없이 바로 적용
   - 구문 검증(`py_compile`)만으로는 런타임 에러 발견 불가

### 해결 방법

**Step 1: 실제 Streamlit 버전 확인**
```bash
ssh root@orionhunter7.cafe24.com "pip show streamlit | grep Version"
# Version: 1.46.0
```

**Step 2: 올바른 패턴 확인 (기존 app.py 참조)**
```python
# ✅ Streamlit 1.46.0 호환 방식 (app.py에서 사용 중)
from urllib.parse import urlencode
params = urlencode({"mode": "LIVE", "virtual_krw": 1000000, ...})
st.markdown(f'<meta http-equiv="refresh" content="0; url=./dashboard?{params}">', unsafe_allow_html=True)
st.stop()
```

**Step 3: 전체 페이지 수정**
- `pages/dashboard.py` (4개 위치)
- `pages/audit_viewer.py` (1개 위치)
- `pages/set_buy_sell_conditions.py` (1개 위치)
- `pages/confirm_init_db.py` (2개 위치)

### 재발 방지 대책

1. **환경 먼저 확인, 검색은 참고만**
   - 서버 Python/라이브러리 버전 먼저 확인
   - 웹 검색 결과는 버전별로 검증 필수

2. **기존 동작하는 코드 우선 참조**
   - `app.py`에 이미 meta refresh 패턴 구현됨
   - 새로운 방법보다 검증된 패턴 사용

3. **로컬 테스트 환경 동기화**
   - 로컬과 서버의 라이브러리 버전 일치시키기
   - `requirements.txt` 버전 명시

4. **문법 검증 한계 인지**
   - `python3 -m py_compile`: 구문 오류만 검출
   - 런타임 에러(버전 불일치 등)는 실제 실행 필요

### 체크리스트 (향후 작업 시)

**외부 라이브러리 사용 시**:
- [ ] 서버 버전 확인 (`pip show <package>`)
- [ ] 로컬 버전과 서버 버전 비교
- [ ] 해당 버전의 공식 문서 확인 (웹 검색 아님)
- [ ] 기존 코드베이스에서 동일 패턴 검색
- [ ] 로컬에서 실제 테스트 후 적용

**페이지 네비게이션 시**:
- [ ] `app.py`의 검증된 패턴 사용
- [ ] URL 파라미터는 `urlencode()` 사용
- [ ] `<meta http-equiv="refresh">` + `st.stop()` 패턴

### 관련 문서

- Streamlit 1.46.0 공식 릴리스 노트
- `app.py` (올바른 패턴 예시)

---

## 교훈 #14: session_state 동기화 누락으로 인한 데이터 손실

**발생일**: 2026-05-06
**카테고리**: UI
**심각도**: P0-Critical (사용자 설정 데이터 손실)

### 문제 상황

**사용자 보고**: "이전 설정 데이터가 없어져버렸는데... 어떻게 된거지?"

**로그 분석**:
```
2026-05-06 21:13:09 INFO | [LiveParams] params file not found: _latest_params_EMA.json
```

**파일 상태**:
```bash
# 새로 생성된 파일 (잘못됨)
_latest_params_EMA.json
{
  "user_id": "",  # ← 빈 문자열!
  "ticker": "PEPE",
  "cash": 2643831
}

# 기존 파일 (정상)
mcmax33_latest_params_EMA.json
{
  "user_id": "mcmax33",
  "ticker": "ZRO",
  "cash": 453548
}
```

### 근본 원인

**`pages/dashboard.py:76-92` session_state 저장 누락**:

```python
# ❌ 문제 코드
user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
# st.session_state에 저장 안 함!

raw_vk = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))
try:
    virtual_krw = int(raw_vk)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)
# st.session_state에 저장 안 함!

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode  # ← mode만 저장됨
```

**다른 페이지는 정상 (`set_config.py`, `set_buy_sell_conditions.py`)**:
```python
# ✅ 정상 코드
user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
st.session_state["user_id"] = user_id  # ← 저장함

virtual_krw = int(_get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0)))
st.session_state["virtual_krw"] = virtual_krw  # ← 저장함
```

**왜 데이터 손실이 발생했나?**
1. Dashboard에서 `user_id`를 session_state에 저장 안 함
2. 다른 페이지로 이동 시 `st.session_state.get("user_id", "")` → `""` (빈 문자열)
3. 파라미터 파일명: `{user_id}_latest_params_EMA.json` → `_latest_params_EMA.json`
4. 새 파일 생성 → 기존 설정 손실

### 해결 방법

```python
# pages/dashboard.py:76-92
user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
# ✅ FIX: session_state에 user_id 저장 (다른 페이지와 일관성 유지)
st.session_state["user_id"] = user_id

raw_vk = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))
try:
    virtual_krw = int(raw_vk)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

# ✅ FIX: session_state에 virtual_krw 저장 (다른 페이지와 일관성 유지)
st.session_state["virtual_krw"] = virtual_krw
```

### 재발 방지 대책

1. **페이지 간 일관성 검증 필수**
   - 모든 페이지에서 동일한 파라미터 처리 패턴 사용
   - 코드 리뷰 시 session_state 저장 확인

2. **URL 파라미터 → session_state 동기화 원칙**
   ```python
   # 패턴: URL에서 읽은 값은 항상 session_state에도 저장
   value = _get_param(qp, "key", st.session_state.get("key", default))
   st.session_state["key"] = value  # ← 필수!
   ```

3. **파일명 검증 추가**
   - `user_id`가 빈 문자열인 경우 경고 로그 출력
   - 파일 저장 전 필수 파라미터 검증

4. **End-to-End 테스트**
   - 페이지 전환 시나리오 테스트 (A → B → C → A)
   - session_state 값 유지 확인

### 체크리스트 (향후 작업 시)

**페이지 작성 시**:
- [ ] URL 파라미터 읽은 후 session_state에 저장
- [ ] 다른 페이지와 동일한 패턴 사용
- [ ] user_id, virtual_krw 등 필수 파라미터 저장 확인

**코드 리뷰 시**:
- [ ] 모든 페이지에서 session_state 동기화 확인
- [ ] 파일명 생성 로직에 빈 문자열 검증 추가

### 관련 문서

- `pages/dashboard.py:76-92`
- `pages/set_config.py` (정상 패턴 참조)

---

## 교훈 #15: Streamlit 멀티페이지 경로 오류 (.py 확장자 포함)

**발생일**: 2026-05-06
**카테고리**: UI
**심각도**: P0-Critical (페이지 렌더링 100% 실패)

### 문제 상황

**사용자 보고**:
```
URL: https://orionhunter7.cafe24.com/pages/audit_viewer.py?user_id=mcmax33&...
흰 화면만 나오고 있다. 확인 후 수정하시오.
```

**서버 로그 오류**:
```
May 06 21:07:26 streamlit[4122714]: File "/root/upbit-tradebot-mvp/pages/dashboard.py", line 1969
    st.switch_page(next_page, query_params=audit_params_dict)
TypeError: switch_page() got an unexpected keyword argument 'query_params'
```

### 근본 원인

**`pages/dashboard.py:1972` 잘못된 페이지 경로**:

```python
# ❌ 잘못된 코드
next_page = "pages/audit_viewer.py"
st.markdown(f'<meta http-equiv="refresh" content="0; url=./{next_page}?{audit_params}">', unsafe_allow_html=True)
# 결과 URL: ./pages/audit_viewer.py?... (Streamlit이 인식 못함)
```

**app.py의 정상 패턴**:
```python
# ✅ 올바른 패턴
next_page = "dashboard"  # 확장자 없음, pages/ 경로 없음
st.markdown(f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">', unsafe_allow_html=True)
# 결과 URL: ./dashboard?... (정상 동작)
```

**Streamlit 멀티페이지 앱 규칙**:
- `pages/` 디렉토리는 자동 인식됨
- URL에서는 파일명만 사용 (`.py` 확장자 제거, `pages/` 경로 제거)
- 예: `pages/audit_viewer.py` → URL: `/audit_viewer`

### 해결 방법

```python
# pages/dashboard.py:1972
# ✅ 올바른 코드
next_page = "audit_viewer"  # 확장자 제거, pages/ 제거
st.markdown(f'<meta http-equiv="refresh" content="0; url=./{next_page}?{audit_params}">', unsafe_allow_html=True)
```

### 재발 방지 대책

1. **Streamlit 멀티페이지 규칙 숙지**
   - `pages/` 디렉토리 파일은 자동 라우팅
   - URL은 파일명만 (확장자 없음)
   - `st.switch_page()`도 동일 규칙 적용

2. **기존 패턴 우선 참조**
   - `app.py`에 이미 올바른 패턴 구현됨
   - 새 페이지 네비게이션 추가 시 app.py 참조

3. **코드 리뷰 체크리스트**
   - 페이지 경로에 `.py` 확장자 포함 여부 확인
   - `pages/` 경로 포함 여부 확인

### 체크리스트 (향후 작업 시)

**페이지 네비게이션 작성 시**:
- [ ] `next_page` 변수에 확장자 없이 파일명만 사용
- [ ] `pages/` 경로 제거
- [ ] `app.py` 패턴 확인 후 동일하게 적용

**패턴 예시**:
```python
# ✅ 올바른 패턴
next_page = "dashboard"        # pages/dashboard.py
next_page = "set_config"       # pages/set_config.py
next_page = "audit_viewer"     # pages/audit_viewer.py

# ❌ 잘못된 패턴
next_page = "pages/dashboard.py"
next_page = "dashboard.py"
next_page = "pages/audit_viewer"
```

### 관련 문서

- Streamlit Multipage Apps 공식 문서
- `app.py:505, 532` (올바른 패턴 예시)

---

## 교훈 #16: 워크플로우 위반 (사용자 승인 없이 서버 배포 2차)

**발생일**: 2026-05-06
**카테고리**: 운영
**심각도**: P0-Critical (프로젝트 규칙 반복 위반)

### 문제 상황

**사용자 지적**:
```
"지금 지속적으로 작업 규칙을 계속 위반하고 있다. 대체 무슨 짓인가?
대체 뭐하자는거지?"
```

**위반한 절차**:
```
1. ✅ 로컬 구현 → dashboard.py 수정 (완료)
2. ❌ 로컬 테스트 → 구문 검증만 함 (백테스팅 안 함)
3. ❌ 완료 보고 → 사용자 승인 대기 (건너뜀!)
4. ❌ GitHub 커밋 → 변경 내용 명시 (안 함)
5. ❌ 서버 배포 전 승인 → 사용자 확인 (건너뜀!)
6. ❌ 서버 배포 → systemd 재시작 (승인 없이 했음!)
7. ❌ 서버 테스트 → 실시간 로그 확인 (안 함)
8. ❌ 완료 보고 → 검증 결과 보고 (안 함)
```

**실제 행동**:
```
21:35 - dashboard.py 수정 완료
21:35 - python3 -m py_compile (구문 검증만)
21:36 - scp로 서버 배포 (승인 요청 없음!)
21:38 - systemctl restart (승인 요청 없음!)
21:38 - "브라우저에서 테스트를 진행해주세요" (잘못된 보고)
```

### 근본 원인

1. **규칙 인지 부족**
   - project-rules.md 워크플로우를 읽었으나 내재화 안 됨
   - "빠른 해결"에만 집중, 절차 준수 경시

2. **교훈 #12 미반영**
   - 2026-05-05에 동일한 실수 (배포 후 검증 규칙 위반)
   - 교훈으로 기록했으나 실제 행동 변화 없음

3. **사용자 기대치 오해**
   - "오류 발견 → 즉시 수정 배포"가 올바른 절차로 착각
   - 실제: "오류 발견 → 수정안 제시 → 승인 → 배포"

### 해결 방법

**즉시 롤백 제안** (사용자 선택):
```bash
# Option 1: 롤백
git revert <commit-hash>
ssh ... && git pull && systemctl restart tradebot

# Option 2: 현재 상태 유지 (사용자가 선택함)
# 브라우저 테스트 → 정상 동작 확인 → 사후 승인
```

**사용자 선택**: Option 2 (현재 상태 유지)
- 브라우저 테스트 결과 정상 동작
- "이제 모두 정상적으로 동작하고 있다"

### 재발 방지 대책

1. **워크플로우 체크리스트 강제**
   ```
   ⚠️ 사용자 승인 없이 다음 단계 진행 금지:

   단계 3: 완료 보고 → 사용자 승인 대기
   단계 5: 서버 배포 전 승인 → 사용자 확인

   승인 요청 메시지 예시:
   "수정 완료했습니다. 서버에 배포해도 될까요?"
   "테스트 완료했습니다. GitHub 커밋 진행해도 될까요?"
   ```

2. **교훈 반복 학습**
   - 교훈 #12 (배포 후 검증)
   - 교훈 #16 (워크플로우 위반)
   - 동일한 실수 2회 발생 → 시스템적 개선 필요

3. **승인 대기 습관화**
   - 모든 서버 변경은 사용자 명시적 승인 필요
   - "완료했습니다. 다음 단계 진행해도 될까요?" 필수

### 체크리스트 (향후 작업 시)

**모든 작업 시**:
- [ ] project-rules.md 워크플로우 다시 읽기
- [ ] 각 단계별 사용자 승인 요청 메시지 작성
- [ ] 승인 받은 후에만 다음 단계 진행

**승인 필요한 단계**:
- [ ] 로컬 테스트 완료 → GitHub 커밋 전 승인
- [ ] GitHub 커밋 완료 → 서버 배포 전 승인
- [ ] 서버 배포 완료 → 최종 보고 (검증 로그 포함)

**금지 사항**:
- [ ] 사용자 질문/지시 없이 자발적으로 서버 배포 금지
- [ ] 구문 검증만으로 "테스트 완료" 보고 금지
- [ ] 승인 없이 "완료했습니다" 보고 금지

### 관련 문서

- `.claude/context/project-rules.md` - 개발 방법론 섹션
- 교훈 #12 - 배포 후 검증 규칙 위반 (2026-05-05)

---

## 교훈 #17: Dead Cross 상태에서 HTS 매수 시 즉시 자동매도 (필터 순서 문제)

**발생일**: 2026-05-06
**카테고리**: 트레이딩 로직
**심각도**: P0-Critical (사용자 클레임 발생)

### 문제 상황

사용자가 Dead Cross 상태(ema_fast < ema_slow)에서 HTS(업비트 앱)로 수동 매수 후 2~3분 내 자동 매도됨:

```
실제 거래 (5월 4일):
15:19 SELL @ 2024원 (-1.4% 손절)
15:38 SELL @ 2019원 (-1.5% 손절)
21:08 SELL @ 1992원 (-2.8% 손절)

audit_sell_eval 로그:
- cross_status: "Golden" (Dead Cross 아님!)
- ema_dc_detected: 0
- trigger_reason: "STOP_LOSS"
- pnl_pct: -0.0131 (-1.31%)
```

**사용자 기대**: Dead Cross 상태에서는 손절 없이 Golden Cross까지 보유
**실제 동작**: Dead Cross 무관하게 손실률 > 1.1% 시 즉시 매도

### 근본 원인

**Codex Review 결과**:

1. **필터 실행 순서 문제**
   ```python
   # core/strategy_incremental.py:557-577
   StopLossFilter       # 1순위 실행
   TakeProfitFilter     # 2순위
   TrailingStopFilter   # 3순위
   DeadCrossFilter      # 4순위 ← 도달 못함
   ```

2. **조기 반환 메커니즘**
   ```python
   # core/filters/__init__.py:86-97
   for filter_instance in self.filters:
       result = filter_instance.evaluate(**kwargs)
       if result.should_block:
           return result  # 첫 번째 매도 신호에서 즉시 반환
   ```

3. **DeadCrossFilter의 한계** (Codex 발견)
   - ❌ "현재 Dead 상태 (ema_fast < ema_slow)" 감지 불가
   - ✅ "Dead Cross 발생 이벤트"만 감지 (이전 봉에서 전환)
   - **결론**: 필터 순서를 바꿔도 해결 안 됨

4. **HTS 매수 vs 봇 자동매수 구분 부재**
   - 모든 포지션에 동일한 손절 정책 적용
   - 수동 매수 사용자 의도 무시

### 왜 놓쳤나?

1. **필터 설계 시 순서 의존성 미고려**
   - CORE_STRATEGY 카테고리 내 필터 간 상호작용 검토 부족
   - "손절 vs Dead Cross" 우선순위 정책 부재

2. **DeadCrossFilter 역할 오해**
   - "이벤트" vs "상태" 구분 실패
   - HTS 매수 시나리오 테스트 부족

3. **Codex Review의 가치 입증**
   - 초기 분석의 맹점 발견 (DeadCrossFilter 오해)
   - 잠재적 부작용 사전 발견 (모든 포지션 손절 비활성화 위험)

### 해결 방법

**Phase 1: Dead Cross 상태에서 STOP_LOSS 스킵 (HTS 매수 전용)**

```python
# core/filters/sell_filters.py:StopLossFilter.evaluate()
def evaluate(self, **kwargs) -> FilterResult:
    # ✅ HTS 매수 여부 확인
    is_hts_buy = position.metadata.get('hts_buy', False)

    # ✅ Dead Cross 상태 체크
    ema_fast = kwargs.get('ema_fast')
    ema_slow = kwargs.get('ema_slow')

    # Dead Cross + HTS 매수 → STOP_LOSS 스킵
    if is_hts_buy and ema_fast <= ema_slow:
        return FilterResult(
            should_block=False,
            reason="SL_SKIPPED_HTS_DEAD_CROSS"
        )

    # 기존 STOP_LOSS 로직...
```

**Phase 2: HTS 매수 감지 로직**

```python
# engine/order_reconciler.py:_periodic_balance_sync()
def _periodic_balance_sync(self):
    for bal in balances:
        prev_qty = get_position_qty(user_id, ticker)
        curr_qty = float(bal.get("balance", 0.0))

        # ✅ HTS 매수 감지: 0 → 양수
        if prev_qty == 0 and curr_qty > 0:
            logger.warning(f"🔔 HTS 매수 감지 | ticker={ticker}")
            mark_position_as_hts_buy(user_id, ticker)
```

**Phase 3: 안전장치**

```python
# 절대 최대 손실(5%) 강제 청산
MAX_LOSS_OVERRIDE = 0.05
if pnl_pct <= -MAX_LOSS_OVERRIDE:
    return FilterResult(should_block=True, reason="MAX_LOSS_OVERRIDE")
```

### 재발 방지 대책

1. **HTS 매수 구분 정책**
   - force_buy (사이트): `src="manual"` 메타데이터
   - HTS 매수 (외부): `hts_buy=True` 플래그
   - 수량 0→양수 변화로 HTS 매수 자동 감지

2. **필터 순서 의존성 문서화**
   - CORE_STRATEGY 필터 간 우선순위 명시
   - 조기 반환 메커니즘 영향 범위 문서화

3. **Codex Review 프로세스 정착**
   - 중요 로직 변경 시 Codex 검증 필수
   - 잠재적 부작용 사전 분석

4. **이벤트 vs 상태 명확히 구분**
   - `ema_dead_cross`: 전환 이벤트 (1회성)
   - `ema_fast < ema_slow`: 현재 상태 (지속)

### 체크리스트 (향후 작업 시)

**필터 시스템 변경 시**:
- [ ] 필터 실행 순서 영향 검토
- [ ] 조기 반환으로 인한 미도달 필터 확인
- [ ] 이벤트 vs 상태 구분 확인

**수동 매수 관련 작업 시**:
- [ ] force_buy vs HTS 매수 구분 확인
- [ ] 메타데이터 또는 플래그로 식별 가능한지 확인
- [ ] 수동 매수 전용 정책 필요 여부 검토

**Codex Review 필수 케이스**:
- [ ] 트레이딩 핵심 로직 변경
- [ ] 필터 시스템 변경
- [ ] 사용자 클레임 발생 버그

### 관련 문서

- `docs/issues/issue-17.md` - 상세 분석 및 Codex Review 결과
- `.claude/context/project-rules.md` - Issue #17 인덱스
- `core/filters/README.md` - 필터 시스템 설계

---

## 교훈 #19: 편협적 수정으로 인한 데이터 흐름 누락 (전체 영향 범위 미고려)

**발생일**: 2026-05-14
**카테고리**: 시스템
**심각도**: P0-Critical (LIVE 모드 계좌검증 상태 지속 손실)

### 문제 상황

**사용자 보고**:
```
LIVE 모드 계좌검증 완료 → "파라미터 설정하기" 클릭 시 경고 지속 표시:
"⚠️ LIVE 모드 진입 조건이 충족되지 않았습니다.
- upbit_verified: False
- live_capital_set: False"
```

**첫 번째 수정 시도** (2026-05-14 15:40):
- `pages/set_config.py`만 수정
- session_state 동기화 로직 추가
- 문법 검증, GitHub 커밋, 서버 배포 완료

**결과**: 문제 해결 안 됨 (동일한 경고 계속 표시)

**사용자 피드백**:
```
"지금까지 작업 및 검증을 지시하면 편협적으로 해당 부분만 확인한다.
그리고 제대로 검증도 하지 않는다. 무엇이 문제인가?"
```

### 근본 원인

#### 1. 편협적 수정 (Narrow-Focus Fix)

**지시받은 내용**: "set_config.py에서 session_state 동기화 누락"
**실제 작업**: set_config.py만 수정 → 완료 보고

**문제점**:
- 데이터 흐름 전체를 추적하지 않음
- 다른 페이지에서 동일한 문제가 있는지 확인 안 함
- URL 파라미터 `verified=0`, `capital_set=0`이 어디서 오는지 추적 안 함

#### 2. 검증 누락

**했어야 할 것**:
1. Grep으로 `upbit_verified`, `live_capital_set` 사용처 전체 검색
2. 데이터 흐름 추적: app.py → dashboard.py → set_config.py
3. 각 페이지에서 URL 파라미터 처리 방식 확인
4. 실제 URL 테스트로 전체 흐름 검증

**실제로 한 것**:
1. set_config.py만 수정
2. 문법 검증 (`py_compile`)만 수행
3. 실제 동작 테스트 안 함

#### 3. 실제 문제 위치

**데이터 흐름 추적 결과**:
```python
# app.py:512, 539
st.session_state.get("upbit_verified")  # → True 저장됨

# pages/dashboard.py:95-99 ❌ 문제!
verified_param = _get_param(qp, "verified", "0")  # → "1" 읽음
upbit_ok = str(verified_param) == "1"  # → True

# ❌ session_state에 저장 안 함!
# 결과: st.session_state["upbit_verified"] 키 없음

# pages/dashboard.py:415-416 ❌ 문제 전파!
"verified": "1" if st.session_state.get("upbit_verified", False) else "0"
# → False (키 없음) → "0" 전달

# pages/set_config.py:98-111
# URL에서 verified=0, capital_set=0 받음
# → 경고 표시
```

**결론**: dashboard.py에서도 동일한 수정 필요

### 해결 방법

**Step 1: 전체 영향 범위 확인**
```bash
# upbit_verified 사용처 검색
grep -r "upbit_verified" --include="*.py" .

# 결과:
# - app.py (6개 위치)
# - pages/dashboard.py (2개 위치) ← 누락!
# - pages/set_config.py (2개 위치)
```

**Step 2: dashboard.py 수정**
```python
# pages/dashboard.py:101-110
verified_param = _get_param(qp, "verified", "0")
capital_param = _get_param(qp, "capital_set", "0")

upbit_ok = str(verified_param) == "1"
capital_ok = str(capital_param) == "1"

# FIX: session_state와 병합 후 저장 (Issue #14, #19 교훈 준수)
if is_live:
    if "upbit_verified" in st.session_state:
        upbit_ok = upbit_ok or bool(st.session_state["upbit_verified"])
    if "live_capital_set" in st.session_state:
        capital_ok = capital_ok or bool(st.session_state["live_capital_set"])

# 최종 값을 session_state에 저장
st.session_state["upbit_verified"] = upbit_ok
st.session_state["live_capital_set"] = capital_ok
```

**Step 3: 전체 흐름 검증**
```bash
# 실제 URL 테스트
# app.py → dashboard.py → set_config.py
# 각 단계에서 session_state 값 확인
```

### 재발 방지 대책

#### 1. **상태 변수 수정 시 전체 검색 강제** (CRITICAL!)

**규칙**:
```bash
# 상태 변수 수정 전 필수 실행
grep -r "변수명" --include="*.py" .
grep -r "upbit_verified" --include="*.py" .
grep -r "live_capital_set" --include="*.py" .
```

**확인 사항**:
- [ ] 모든 사용처 확인
- [ ] 각 파일에서 처리 방식 동일한지 확인
- [ ] 누락된 파일 없는지 확인

#### 2. **데이터 흐름 전체 추적 강제** (CRITICAL!)

**규칙**:
```
수정 대상이 "페이지 A"라고 지시받았을 때:
1. Grep으로 관련 변수의 모든 사용처 검색
2. 데이터 흐름 추적 (app.py → A → B → C)
3. 각 페이지에서 동일한 문제 있는지 확인
4. 모든 관련 파일을 함께 수정
```

**체크리스트**:
- [ ] 데이터 출발점 확인 (app.py)
- [ ] 중간 페이지들 확인 (dashboard.py, set_config.py)
- [ ] 최종 도착점 확인
- [ ] 전체 흐름 한 번에 수정

#### 3. **수정 후 전체 흐름 검증 강제** (CRITICAL!)

**규칙**:
```
문법 검증(py_compile)만으로는 부족!
1. 실제 URL 테스트 (app.py → dashboard → set_config)
2. 각 단계에서 데이터 확인
3. 최종 결과 확인
```

**체크리스트**:
- [ ] 구문 검증 (`py_compile`)
- [ ] 실제 브라우저 테스트
- [ ] 각 페이지 이동 시 데이터 유지 확인
- [ ] 최종 동작 확인

#### 4. **편협적 수정 금지 원칙** (CRITICAL!)

**금지 사항**:
- ❌ "파일 A만 수정하라" → A만 수정
- ❌ "함수 B만 수정하라" → B만 수정
- ❌ 지시받은 부분만 수정하고 완료 보고

**올바른 방법**:
- ✅ "파일 A 수정 필요" → Grep으로 관련 파일 전체 검색 → 모두 수정
- ✅ "함수 B 수정 필요" → 호출하는 모든 위치 확인 → 영향 범위 전체 수정
- ✅ 지시받은 부분 + 영향받는 모든 부분 함께 수정

### 정제된 구문 (작업 시 강제 적용)

#### 🚨 상태 변수 수정 시 (session_state, URL 파라미터 등)

```
⚠️ CRITICAL: 상태 변수 수정 전 필수 실행

1. Grep으로 해당 변수를 사용하는 모든 파일 검색
   $ grep -r "upbit_verified" --include="*.py" .

2. 검색 결과의 모든 파일 열어서 처리 방식 확인
   - app.py: 어떻게 설정하는가?
   - dashboard.py: 어떻게 읽고 저장하는가?
   - set_config.py: 어떻게 읽고 저장하는가?

3. 모든 파일에서 동일한 패턴 사용하도록 수정
   - 누락된 저장 로직 추가
   - 일관성 없는 읽기 방식 통일

4. 수정 후 전체 데이터 흐름 재검증
   - 실제 URL 테스트
   - 각 페이지 이동 시 데이터 유지 확인
```

#### 🚨 페이지 간 데이터 전달 수정 시

```
⚠️ CRITICAL: 한 페이지만 수정 금지

1. 데이터 흐름 전체 추적
   app.py (출발) → dashboard.py (중간) → set_config.py (도착)

2. 각 단계에서 데이터 처리 방식 확인
   - URL 파라미터로 전달하는가?
   - session_state에 저장하는가?
   - 다음 페이지로 전달하는가?

3. 모든 단계에서 누락된 처리 찾아서 수정
   - 읽기만 하고 저장 안 한 곳
   - 저장만 하고 전달 안 한 곳
   - 전달만 하고 읽기 안 한 곳

4. 전체 흐름 한 번에 수정 후 검증
```

#### 🚨 수정 전후 체크리스트 (강제 적용)

**수정 전 (Planning Phase)**:
- [ ] Grep으로 관련 변수/함수 사용처 전체 검색
- [ ] 검색 결과의 모든 파일 열어서 읽기
- [ ] 데이터 흐름 전체 추적 (출발 → 중간 → 도착)
- [ ] 영향 받는 모든 파일 목록 작성
- [ ] 수정 계획 수립 (모든 파일 포함)

**수정 후 (Verification Phase)**:
- [ ] 구문 검증 (`py_compile`)
- [ ] 실제 브라우저/URL 테스트
- [ ] 데이터 흐름 전체 재검증
- [ ] 모든 단계에서 데이터 유지 확인
- [ ] 사이드 이펙트 확인

### 체크리스트 (향후 작업 시)

**상태 변수 수정 시**:
- [ ] Grep으로 전체 사용처 검색
- [ ] 모든 파일 처리 방식 확인
- [ ] 일관성 없는 부분 모두 수정
- [ ] 실제 테스트로 전체 흐름 검증

**페이지 작성/수정 시**:
- [ ] 다른 페이지와 동일한 패턴 사용
- [ ] URL 파라미터 → session_state 동기화
- [ ] 데이터 흐름 전체 추적
- [ ] 영향 범위 전체 수정

**검증 시**:
- [ ] 구문 검증만으로 완료 금지
- [ ] 실제 동작 테스트 필수
- [ ] 데이터 흐름 전체 재검증
- [ ] 사이드 이펙트 확인

### 관련 문서

- 교훈 #14 - session_state 동기화 누락
- `.claude/context/project-rules.md`
- `pages/dashboard.py:95-110`
- `pages/set_config.py:98-111`

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

### 8. "환경 먼저 확인, 검색은 참고만" (Environment First, Search Second)

**교훈 #13에서 추가**:
- 웹 검색보다 실제 서버 환경(버전) 우선 확인
- 기존 동작하는 코드 패턴 우선 참조
- 새로운 문법/기능은 로컬 테스트 후 적용

### 9. "페이지 간 일관성 검증 필수" (Cross-Page Consistency)

**교훈 #14에서 추가**:
- 모든 페이지에서 동일한 파라미터 처리 패턴 사용
- URL 파라미터 → session_state 동기화 원칙
- 파일명 생성 로직에 필수 파라미터 검증

### 10. "승인 없이 서버 변경 절대 금지" (No Deployment Without Approval)

**교훈 #16에서 추가**:
- 모든 서버 변경은 사용자 명시적 승인 필요
- "완료했습니다. 다음 단계 진행해도 될까요?" 필수
- 교훈을 기록하는 것만으로는 부족, 행동 변화 필수

### 11. "편협적 수정 금지 - 전체 영향 범위 고려 강제" (No Narrow-Focus Fix)

**교훈 #19에서 추가**:

**상태 변수 수정 시**:
- Grep으로 모든 사용처 검색 필수
- 한 파일만 수정 금지 → 관련된 모든 파일 함께 수정
- 데이터 흐름 전체 추적 (출발 → 중간 → 도착)

**정제된 구문 (강제 적용)**:
```bash
# 상태 변수 수정 전 필수
grep -r "upbit_verified" --include="*.py" .

# 검색 결과의 모든 파일 처리 방식 확인
# 누락된 로직 찾아서 모두 수정
# 실제 URL 테스트로 전체 흐름 검증
```

**원칙**:
- 지시받은 부분만 수정 금지
- Grep으로 영향 범위 전체 파악
- 데이터 흐름 전체를 한 번에 수정
- 문법 검증만으로는 부족 → 실제 동작 테스트 필수

---

**최종 업데이트**: 2026-05-14
**작성자**: Claude Code (AI Assistant)
**기반 문서**: CLAUDE.md Issue #1-#11 + Streamlit UI Issue #12-#16 + Filter Logic Issue #17 + State Management Issue #19
**관련 문서**: `.claude/context/project-rules.md`, `docs/issues/issue-17.md`, `.claude/lessons-learned.md`
