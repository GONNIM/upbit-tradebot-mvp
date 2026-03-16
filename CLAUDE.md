# Claude Code - 트러블슈팅 및 교훈 기록

**프로젝트**: upbit-tradebot-mvp
**작성일**: 2026-03-03
**작성자**: CTO Assistant (Claude Code)

---

## 🎯 목적

이 문서는 Claude Code가 REST Reconcile 시스템 구축 중 발견한 실수, 놓친 사항, 그리고 배운 교훈을 기록합니다. 향후 유사한 실수를 방지하고, 코드 품질을 향상시키기 위한 참고 자료입니다.

---

## 📋 Critical Issues - 놓쳤던 버그들

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
| 2026-03-04 20:30 | 정체 포지션 필터 봉 개수 기반 | 🔴 Critical | 2 files, 80 lines | 30분 |
| 2026-03-05 | Trailing Stop 계산 방식 오류 | 🔴 Critical | 3 files, ~100 lines | 40분 |

### 교훈

- **총 놓친 버그**: 6개 (모두 Critical)
- **근본 원인**:
  - 가정 기반 코딩
  - 외부 API 검증 부족
  - timezone 이해 부족
  - 기존 검증된 코드 미참조
  - 분기별 일관성 검증 부족
  - 함수 책임 명확화 부족
  - **설계 단위와 구현 단위 불일치**
  - **사용자 기대 무시**
  - **관례적 구현에 의존** (신규 - Issue #7)
  - **요구사항을 수식으로 변환하지 않음** (신규 - Issue #7)
- **재발 방지**:
  - 검증 프로세스 확립
  - Best Practices 문서화
  - 기존 동작 코드 우선 참조
  - 분기별 체크리스트 적용
  - End-to-End 로그 검증
  - **UI/문서 표시 단위와 실제 구현 일치 검증**
  - **사용자 피드백 즉시 반영**
  - **요구사항을 수식으로 명확히 변환** (신규 - Issue #7)
  - **예시 시나리오로 구현 검증** (신규 - Issue #7)

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
5. **사용자 요구사항을 수식으로 정확히 변환하라** (신규 - Issue #7)

**REST Reconcile의 원칙을 코딩에도 적용**:
- "추정하지 말고, 진실을 복원하라" (Don't estimate, restore truth)
- "가정하지 말고, 검증하라" (Don't assume, verify)
- "사용자가 말한 그대로 구현하라" (Implement exactly as user described) (신규 - Issue #7)

---

**최종 업데이트**: 2026-03-05
**작성자**: CTO Assistant (Claude Code)
**버전**: v1.3 (Issue #7 추가 - Trailing Stop 수익 기반 개선)
