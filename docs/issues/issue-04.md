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

