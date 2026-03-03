# Claude Code - 트러블슈팅 및 교훈 기록

**프로젝트**: upbit-tradebot-mvp
**작성일**: 2026-03-03
**작성자**: CTO Assistant (Claude Code)

---

## 🎯 목적

이 문서는 Claude Code가 REST Reconcile 시스템 구축 중 발견한 실수, 놓친 사항, 그리고 배운 교훈을 기록합니다. 향후 유사한 실수를 방지하고, 코드 품질을 향상시키기 위한 참고 자료입니다.

---

## 📋 Critical Issues - 놓쳤던 버그들

### 🔴 Issue #1: pyupbit 컬럼명 대소문자 불일치

**발생일**: 2026-03-03 20:08
**심각도**: 🔴 Critical (100% 실패)

#### 문제

```python
df = pyupbit.get_ohlcv(...)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]  # ❌ KeyError!
```

**에러 메시지**:
```
KeyError: "None of [Index(['Open', 'High', 'Low', 'Close', 'Volume'], dtype='object')] are in the [columns]"
```

#### 근본 원인

- **가정**: pyupbit가 대문자 컬럼명을 반환할 것으로 가정
- **실제**: pyupbit는 **소문자 컬럼명** 반환 (`open`, `high`, `low`, `close`, `volume`, `value`)
- **왜 놓쳤나**: API 문서를 확인하지 않고 관례적으로 대문자를 가정함

#### 교훈

1. **외부 라이브러리의 반환값은 반드시 문서 또는 실제 테스트로 확인**
   ```python
   # ✅ 올바른 접근
   import pyupbit
   df = pyupbit.get_ohlcv('KRW-BTC', interval='minute1', count=1)
   print(df.columns.tolist())  # 실제 컬럼명 확인
   ```

2. **가정하지 말고, 검증하라** (REST Reconcile의 핵심 원칙과 동일)

#### 수정

```python
# ✅ 컬럼명 표준화 추가
df.columns = [col.capitalize() for col in df.columns]
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
```

**파일**: `core/rest_reconcile.py:98`
**문서**: `thoughts/20260303-REST-Reconcile-Hotfix-Column-Names.md`

---

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

### 🔴 Issue #4: REST API 지연으로 인한 현재 봉 미조회

**발생일**: 2026-03-03 21:06~21:20
**심각도**: 🔴 Critical (BUY/SELL 평가 로직 미동작)

#### 문제

봉 확정(Clock-Close) 감지 후 REST API 호출 시 현재 봉이 항상 누락됨:

```
2026-03-03 21:06:00 INFO | ⏰ [CLOCK-CLOSE] 봉 확정 감지 | ts=2026-03-03 21:06:00 KST
2026-03-03 21:06:08 INFO | [REST] 다중 호출 완료 | ... ~ 2026-03-03 21:03:00 KST
                                                           ❌ 21:06 봉 없음!
2026-03-03 21:06:10 INFO | ⚠️ [CLOCK-CLOSE] closed_ts=2026-03-03 21:06:00가 local_series에 없음
2026-03-03 21:06:12 INFO | 🔄 [RETRY] closed_ts 단일 재조회 시도...
2026-03-03 21:06:14 INFO | ❌ [RETRY] 재조회도 실패 → 다음 봉 대기
```

**패턴**:
- 항상 1~3분 이전 봉까지만 반환
- 21:06:00 close → 21:03:00까지 반환 (3분 지연)
- 21:07:00 close → 21:06:00까지 반환 (1분 지연)
- 21:08:00 close → 21:07:00까지 반환 (1분 지연)

#### 근본 원인

1. **Upbit REST API 특성**:
   - 봉 확정 후 ~10-20초 지연 후 데이터 반영
   - WebSocket은 실시간, REST는 지연됨
   - Upbit 웹사이트는 WebSocket 사용 (실시간)

2. **초기 Jitter 부족**:
   - `data_feed.py`에서 8.0초 Jitter 사용
   - 실제로는 15초 이상 필요

3. **재시도 대기 부족**:
   - 초기 재시도 로직: 2초 대기 후 1회만 재시도
   - API 지연 시 여전히 데이터 없음

#### 사용자 피드백 (Critical)

> "아~ 미쳐버리겠네... 왜 계속 제자리 맴돌듯이 버그를 양산해내지? 지금까지 몇번이나 실수를 저질러서 수정했었잖아... **추정으로 하지말고... 지금 프로젝트 소스에서 이거 구현전에는 제대로 동작했으니... 정상 소스를 참조 후 정상 동작 방안을 제안해줘.**"

**핵심 메시지**:
- ❌ 추정하지 말 것
- ✅ 기존 동작하던 소스 참조
- ✅ 검증된 패턴 적용

#### 교훈

1. **기존 동작하는 코드를 먼저 참조하라**
   - `data_feed.py`에 이미 JITTER_BY_INTERVAL 구현됨
   - 검증된 값(minute3: 15.0s) 참조

2. **외부 API 지연은 문서보다 실제 테스트로 확인**
   - Upbit 문서에는 REST API 지연 명시 없음
   - 실제 로그로 10-20초 지연 확인

3. **Progressive Retry 패턴**
   - 단일 재시도는 불충분
   - 점진적 대기 시간 증가 (5s → 8s → 10s)
   - 총 대기 시간: 15s (Main Jitter) + 23s (Retry) = 38초

#### 수정

**Step 1: Jitter 증가 (8.0s → 15.0s)**
```python
# core/data_feed.py:50
JITTER_BY_INTERVAL = {
    "minute1": 15.0,  # 1분봉: 종가 확정 대기 (5.0 → 8.0 → 15.0) - REST API 지연 대응
    ...
}
```

**Step 2: Progressive Retry (5s → 8s → 10s)**
```python
# engine/live_loop.py:691-738
# 🔄 Progressive Retry: 최대 3회 재시도 (5초 → 8초 → 10초 대기)
retry_waits = [5, 8, 10]  # 초 단위 대기 시간 (점진적 증가)
retry_success = False

for retry_num, wait_sec in enumerate(retry_waits, start=1):
    logger.info(f"🔄 [RETRY-{retry_num}/{len(retry_waits)}] {wait_sec}초 대기 후 재조회 시도...")
    time.sleep(wait_sec)

    retry_df = safe_fetch_rest(...)
    if retry_df is not None and closed_ts in retry_df.index:
        # 재조회 성공 → 처리
        retry_success = True
        break

# 모든 재시도 실패 시 처리
if not retry_success:
    logger.error(f"❌ [RETRY] 모든 재조회 실패 ({len(retry_waits)}회) → 봉 스킵")
    logger.error(f"💡 [FALLBACK] Upbit REST API 지연 ({sum(retry_waits)}초 대기했으나 데이터 미수신)")
```

**Step 3: Fallback 전략**
- **선택**: 봉 스킵 (가장 안전)
- **대안 1**: WebSocket 데이터 임시 사용 (추정 위험)
- **대안 2**: 봇 중단 및 알림 (보수적)

**총 대기 시간**:
- Main Jitter: 15초
- Retry 1: +5초 (총 20초)
- Retry 2: +8초 (총 28초)
- Retry 3: +10초 (총 38초)

#### 파일 변경

- `core/data_feed.py:50` - JITTER 8.0 → 15.0
- `engine/live_loop.py:691-738` - Progressive Retry 구현
- 문서: `CLAUDE.md` (본 섹션)

---

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

## 🟡 High-Risk Issues - 놓칠 뻔한 사항들

### Issue #3: IndentationError (Mass Replace 부작용)

**발생일**: 2026-03-03 21:00
**심각도**: 🟡 High (구문 오류)

#### 문제

Edit tool의 `replace_all=true` 사용 시 여러 줄 문자열 치환 중 indentation 불일치 발생:

```python
                    # Comment line 1
                    # Comment line 2
        bar_ts_kst = bar.ts.astimezone(...)  # ❌ 8 spaces (should be 20)
                    insert_sell_eval(
```

#### 근본 원인

- **Replace All의 한계**: 각 위치의 context (indentation level)를 고려하지 않음
- **Multi-line 패턴**: 주석 2줄 + 코드 1줄 치환 시 indentation 불일치

#### 교훈

1. **Mass Replace 사용 시 주의**
   - `replace_all=true`는 단순 문자열 치환에만 사용
   - 여러 줄 치환 시 indentation 문제 발생 가능

2. **수정 후 즉시 검증**
   ```bash
   python3 -m py_compile <file>
   ```

3. **Context-aware Replace 필요 시 개별 수정**
   - 각 위치의 indentation level 확인 후 개별 Edit 수행

#### 해결

- 4개 위치 (lines 900, 960) 수동 수정
- Context 포함하여 unique pattern으로 개별 치환

---

## 📚 체계적 교훈 및 Best Practices

### 1. 외부 API/라이브러리 사용 시

#### ❌ 하지 말아야 할 것

```python
# ❌ 가정에 기반한 코드
df = api_call()
df = df[['Open', 'High', 'Low']]  # 컬럼명을 가정함
```

#### ✅ 해야 할 것

```python
# ✅ 검증 후 사용
df = api_call()
print(f"Available columns: {df.columns.tolist()}")  # 실제 확인

# 표준화 (방어적 코딩)
df.columns = [col.capitalize() for col in df.columns]
df = df[['Open', 'High', 'Low']]
```

**원칙**:
1. 외부 라이브러리의 반환 형식을 문서 또는 실제 테스트로 확인
2. 컬럼명, 데이터 타입, timezone 등 명시적으로 검증
3. 표준화 레이어 추가 (defensive programming)

---

### 2. Timezone 처리

#### ❌ 하지 말아야 할 것

```python
# ❌ .replace(tzinfo=...) 사용 (레이블만 변경)
utc_time = datetime.now(ZoneInfo("UTC"))
kst_time = utc_time.replace(tzinfo=ZoneInfo("Asia/Seoul"))
# 결과: 시각 변환 없음, 9시간 오프셋 발생
```

#### ✅ 해야 할 것

```python
# ✅ .astimezone() 사용 (실제 변환)
utc_time = datetime.now(ZoneInfo("UTC"))
kst_time = utc_time.astimezone(ZoneInfo("Asia/Seoul"))
# 결과: UTC +9시간 변환
```

**원칙**:
1. **Timezone 변환 시 항상 `.astimezone()` 사용**
2. `.replace(tzinfo=...)` 사용 금지 (레이블 변경용으로만 사용)
3. 내부적으로 UTC 저장, 표시 시에만 현지 시각 변환

---

### 3. 모드 전환 시 검증

#### 문제

기존 코드 패턴이 새 모드에서도 유효한지 확인하지 않음

#### ✅ 체크리스트

모드 전환 시 (예: WS → REST Reconcile) 다음 사항 검증:

1. **Timezone 처리**
   - [ ] 기존: timezone-naive? timezone-aware?
   - [ ] 신규: timezone-naive? timezone-aware?
   - [ ] 변환 로직 필요 여부

2. **데이터 형식**
   - [ ] 컬럼명 (대소문자)
   - [ ] 데이터 타입 (int, float, Decimal)
   - [ ] Index 타입 (DatetimeIndex with tz?)

3. **End-to-End 테스트**
   - [ ] 실제 API 호출 테스트
   - [ ] DB에 저장된 값 확인
   - [ ] 로그에서 값 확인

---

### 4. Edit Tool 사용 시

#### ❌ 하지 말아야 할 것

```python
# ❌ Multi-line pattern with replace_all=true
# Indentation 문제 발생 가능
Edit(
    old_string="    # Comment\n    bar_ts = ...",
    new_string="    # Comment\n    bar_ts = ...",
    replace_all=true
)
```

#### ✅ 해야 할 것

```python
# ✅ 개별 위치 수정 (context 포함)
Edit(
    old_string="    prev_line\n    # Comment\n    bar_ts = ...\n    next_line",
    new_string="    prev_line\n    # Comment\n    bar_ts = ...\n    next_line"
)
```

**원칙**:
1. `replace_all=true`는 단순 단어/표현 치환에만 사용
2. Multi-line 패턴은 개별 수정 (context 포함)
3. 수정 후 즉시 `python3 -m py_compile` 검증

---

### 5. 검증 프로세스

#### 단계별 검증

1. **구문 검증**
   ```bash
   python3 -m py_compile <file>
   ```

2. **논리 검증**
   ```bash
   # Grep으로 패턴 확인
   grep -n "pattern" <file>

   # 개수 확인
   grep -c "pattern" <file>
   ```

3. **통합 테스트**
   ```python
   # 실제 함수 호출 테스트
   from core.rest_reconcile import fetch_candles_rest_full
   df = fetch_candles_rest_full(...)
   print(df.columns)
   print(df.index.tz)
   ```

4. **End-to-End 검증**
   ```bash
   # DB 값 확인
   sqlite3 db.db "SELECT * FROM table LIMIT 5"

   # 로그 확인
   tail -f logs/bot.log
   ```

---

## 🎯 핵심 원칙 (재발 방지)

### 1. "추정하지 말고, 검증하라" (Don't Assume, Verify)

REST Reconcile의 핵심 원칙을 코딩에도 적용:

```python
# ❌ 가정
df = api_call()
df = df[['Open', 'High']]  # 가정: 대문자 컬럼명

# ✅ 검증
df = api_call()
print(f"Columns: {df.columns.tolist()}")  # 실제 확인
df.columns = [col.capitalize() for col in df.columns]
df = df[['Open', 'High']]
```

### 2. "레이블이 아닌, 실제 변환" (Convert, Not Replace)

```python
# ❌ 레이블만 변경
kst_time = utc_time.replace(tzinfo=ZoneInfo("Asia/Seoul"))

# ✅ 실제 변환
kst_time = utc_time.astimezone(ZoneInfo("Asia/Seoul"))
```

### 3. "단위 테스트 + 통합 테스트" (Unit + Integration)

```python
# ✅ 단위 테스트
def test_timezone_conversion():
    utc = datetime(2026, 3, 3, 11, 15, tzinfo=ZoneInfo("UTC"))
    kst = utc.astimezone(ZoneInfo("Asia/Seoul"))
    assert kst.hour == 20  # 11 + 9 = 20

# ✅ 통합 테스트
def test_bar_time_db():
    # 실제 봇 실행 후 DB 확인
    bar_time = fetch_latest_bar_time_from_db()
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    assert abs((bar_time - now_kst).total_seconds()) < 60
```

### 4. "방어적 코딩" (Defensive Programming)

```python
# ✅ 표준화 레이어 추가
def standardize_dataframe(df):
    """외부 API 응답을 표준화"""
    # 컬럼명 통일
    df.columns = [col.capitalize() for col in df.columns]

    # Timezone 통일 (UTC)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("Asia/Seoul")
    df.index = df.index.tz_convert("UTC")

    return df
```

---

## 📊 통계

### 수정 완료

| 날짜 | 이슈 | 심각도 | 영향 범위 | 수정 시간 |
|------|------|--------|----------|----------|
| 2026-03-03 20:08 | pyupbit 컬럼명 불일치 | 🔴 Critical | 1 file, 1 line | 5분 |
| 2026-03-03 20:15 | bar_time 9시간 오프셋 | 🔴 Critical | 1 file, 9 lines | 15분 |
| 2026-03-03 21:06 | REST API 지연 현재 봉 미조회 | 🔴 Critical | 2 files, 3 lines | 20분 |
| 2026-03-03 22:00 | EMA 증분 업데이트 누락 | 🔴 Critical | 1 file, 4 lines | 10분 |

### 교훈

- **총 놓친 버그**: 4개 (모두 Critical)
- **근본 원인**:
  - 가정 기반 코딩
  - 외부 API 검증 부족
  - timezone 이해 부족
  - 기존 검증된 코드 미참조
  - **분기별 일관성 검증 부족** (신규)
  - **함수 책임 명확화 부족** (신규)
- **재발 방지**:
  - 검증 프로세스 확립
  - Best Practices 문서화
  - 기존 동작 코드 우선 참조
  - **분기별 체크리스트 적용** (신규)
  - **End-to-End 로그 검증** (신규)

---

## 🚀 향후 개선 사항

### 1. 자동화된 검증

```python
# pre-commit hook 추가
# .git/hooks/pre-commit
python3 -m py_compile core/*.py
python3 -m pytest tests/
```

### 2. Timezone 헬퍼 함수

```python
# utils/timezone.py
def utc_to_kst(utc_dt: datetime) -> datetime:
    """UTC를 KST로 변환 (안전하게)"""
    if utc_dt.tzinfo is None:
        raise ValueError("timezone-naive datetime not supported")
    return utc_dt.astimezone(ZoneInfo("Asia/Seoul"))
```

### 3. 통합 테스트 자동화

```python
# tests/integration/test_bar_time.py
def test_bar_time_accuracy():
    """bar_time이 현재 시각과 일치하는지 검증"""
    # 봇 실행 후 DB 확인
    # ±1분 이내 오차 허용
```

---

## 📝 결론

**핵심 메시지**:

1. **외부 라이브러리의 반환값은 가정하지 말고 검증하라**
2. **Timezone 변환 시 `.astimezone()` 사용 필수**
3. **모드 전환 시 기존 가정을 재검증하라**
4. **End-to-End 테스트로 실제 데이터 확인하라**

**REST Reconcile의 원칙을 코딩에도 적용**:
- "추정하지 말고, 진실을 복원하라" (Don't estimate, restore truth)
- "가정하지 말고, 검증하라" (Don't assume, verify)

---

**작성 완료**: 2026-03-03
**작성자**: CTO Assistant (Claude Code)
**버전**: v1.0
