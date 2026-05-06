# Upbit Tradebot MVP - 프로젝트 규칙 및 Issue 인덱스

**목적**: REST Reconcile 시스템 구축 중 발견한 핵심 교훈 및 트러블슈팅
**상세 내용**: 기존 CLAUDE.md (1,797줄) → docs/issues/ (Phase 3에서 이동 예정)

---

## 🚨 긴급 상황 대응 우선순위 (3단계)

**Golden Cross 발생했는데 매수 안 됨**:
1. Issue #11 확인 (BACKFILL 지표 오염)
2. `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` 참조
3. 로그에서 "지표 상태 백업/복원" 확인

**REST API 종가 불일치 (DB vs Upbit 차트)**:
1. Issue #8 확인 (미확정 종가 문제)
2. `docs/analysis/close-price-analysis.md` 참조
3. `fetch_confirmed_candle` 사용 확인 (Progressive Retry)

**BACKFILL 실행 후 DB audit 미업데이트**:
1. Issue #9 확인 (중복 봉 체크 문제)
2. `is_new_bar` 로직 확인
3. `is_backfill=True` 플래그 확인

---

## 📋 Issue 인덱스 (15개)

| # | 제목 | 핵심 메시지 | 날짜 |
|---|------|------------|------|
| 1 | pyupbit 컬럼명 대소문자 | 컬럼명은 항상 소문자 (open, high, low, close, volume) | 2026-03-03 |
| 2 | bar_time 9시간 오프셋 | Timezone 명시 필수 (Asia/Seoul 또는 UTC) | 2026-03-03 |
| 4 | REST API 지연 | 현재 봉 조회 시 `count=2`로 이전 봉도 함께 가져오기 | 2026-03-07 |
| 5 | EMA 증분 업데이트 누락 | Reconcile 후 EMA 재계산 필수 (상태 복원) | 2026-03-08 |
| 6 | 정체 포지션 필터 오류 | 시간 기반 필터는 실제 시간(datetime) 사용, 봉 개수 아님 | 2026-03-10 |
| 7 | Trailing Stop 계산 오류 | Peak-based → Profit-based 변경 (현재 수익 기준) | 2026-03-12 |
| 8 | REST API 미확정 종가 | Progressive Retry로 확정 봉 검증 (3회 재시도) | 2026-03-13 |
| 9 | BACKFILL 중복 체크 | 재평가 ≠ 중복, `is_backfill` 플래그로 구분 | 2026-03-16 |
| 10 | Enum 속성 접근 오류 | `action.value` 사용, `action.action` 아님 | 2026-03-18 |
| 11 | BACKFILL 지표 오염 | 지표 상태 백업/복원으로 Golden Cross 보호 | 2026-03-25 |
| 13 | Streamlit query_params | 서버 버전 먼저 확인, 웹 검색은 참고만 | 2026-05-06 |
| 14 | session_state 동기화 | URL 파라미터 읽으면 session_state에도 저장 | 2026-05-06 |
| 15 | 페이지 경로 .py 확장자 | Streamlit 멀티페이지는 확장자 없이 파일명만 | 2026-05-06 |
| 16 | 워크플로우 위반 (2차) | 사용자 승인 없이 서버 배포 절대 금지 | 2026-05-06 |
| 17 | Dead Cross HTS 매수 자동매도 | Dead 상태에서 HTS 매수는 STOP_LOSS 스킵 (hts_buy 플래그) | 2026-05-06 |

---

## ❌ 금지 사항 (CRITICAL)

### 코드 레벨 금지 사항

```python
# ❌ 절대 금지
pyupbit.get_ohlcv(..., count=400)  # 미확정 종가 반환 (Issue #8)
# ✅ 올바른 방법
fetch_confirmed_candle(..., retries=3)  # Progressive Retry

# ❌ 절대 금지
ema_fast = ta.EMA(close, timeperiod=7)  # 전체 재계산 (느림, 부정확)
# ✅ 올바른 방법
ema_fast = prev_ema + alpha * (close - prev_ema)  # 증분 업데이트

# ❌ 절대 금지
bar_time = pd.Timestamp.now()  # Timezone 미지정 (Issue #2)
# ✅ 올바른 방법
bar_time = pd.Timestamp.now(tz='Asia/Seoul')  # KST 명시

# ❌ 절대 금지
if not self.is_new_bar(bar):
    return  # BACKFILL도 차단됨 (Issue #9)
# ✅ 올바른 방법
if not self.is_new_bar(bar) and not is_backfill:
    return  # 재평가는 허용

# ❌ 절대 금지
action_value = action.action  # AttributeError (Issue #10)
# ✅ 올바른 방법
action_value = action.value  # Enum 값 접근
```

### 운영 레벨 금지 사항

```bash
# ❌ 절대 금지
systemctl restart upbit-tradebot  # 지표 상태 손실
# ✅ 올바른 방법
./squad-tradebot.sh restart  # 안전한 재시작 (상태 저장)

# ❌ 절대 금지
rm -rf *.db  # 감사 로그 삭제
# ✅ 올바른 방법
mv mcmax33.db archive/  # 백업 후 보관
```

---

## ✅ 필수 체크리스트

### BACKFILL 실행 전/후 확인

- [ ] 지표 상태 백업 확인 (`prev_ema_fast`, `prev_ema_slow`)
- [ ] `is_backfill=True` 플래그 전달
- [ ] BACKFILL 완료 후 지표 상태 복원 확인
- [ ] DB audit 로그 UPDATE 확인 (`[AUDIT-UPDATE]` 로그)
- [ ] Golden Cross 상태 유지 확인

### REST API 호출 시 확인

- [ ] `fetch_confirmed_candle` 사용 (pyupbit 직접 호출 금지)
- [ ] Progressive Retry 활성화 (retries=3)
- [ ] 봉 일관성 검증 (open[n] ≈ close[n-1], ±0.3% 허용)
- [ ] Timezone 명시 (Asia/Seoul 또는 UTC)

### 지표 계산 시 확인

- [ ] 증분 업데이트 사용 (전체 재계산 금지)
- [ ] `prev` 값 추적 (Golden/Dead Cross 감지용)
- [ ] Reconcile 후 EMA 재계산 (상태 복원)

### 배포 전 확인

- [ ] 로컬 테스트 완료 (백테스팅 포함)
- [ ] systemd 설정 확인 (자동 재시작 활성화)
- [ ] 로그 레벨 설정 (DEBUG → INFO)
- [ ] 감사 로그 백업 (*.db 파일)

---

## 🔄 개발 방법론 (워크플로우)

**순차 진행 필수**:

1. **로컬 구현** → 코드 작성
2. **로컬 테스트** → 백테스팅 (과거 30일 데이터)
3. **완료 보고** → 사용자 승인 대기 ⚠️
4. **GitHub 커밋** → 변경 내용 명시
5. **서버 배포 전 승인** → 사용자 확인 ⚠️
6. **서버 배포** → systemd 재시작
7. **서버 테스트** → 실시간 로그 확인 (1시간)
8. **완료 보고** → 검증 결과 보고

**⚠️ 사용자 승인 없이 다음 단계 진행 금지**

---

## 📖 상세 문서

### Issue 상세 (필요 시 명시적으로 Read)

**15개 Issue 상세 문서** (문제, 근본 원인, 교훈, 수정):
- `docs/issues/issue-01.md` - pyupbit 컬럼명 대소문자
- `docs/issues/issue-02.md` - bar_time 9시간 오프셋
- `docs/issues/issue-04.md` - REST API 지연
- `docs/issues/issue-05.md` - EMA 증분 업데이트 누락
- `docs/issues/issue-06.md` - 정체 포지션 필터 오류
- `docs/issues/issue-07.md` - Trailing Stop 계산 오류
- `docs/issues/issue-08.md` - REST API 미확정 종가 ⭐
- `docs/issues/issue-09.md` - BACKFILL 중복 체크
- `docs/issues/issue-10.md` - Enum 속성 접근 오류
- `docs/issues/issue-11.md` - BACKFILL 지표 오염 ⭐
- `docs/issues/issue-17.md` - Dead Cross HTS 매수 자동매도 ⭐
- `.claude/lessons-learned.md` - Issue #13~#17 (Streamlit UI + Filter Logic) ⭐

### 분석 보고서 (완료 문서, 필요 시 참조)

- `docs/analysis/close-price-analysis.md` - 미확정 종가 문제 분석
- `docs/work-orders/2026-001-confirmed-candle.md` - 확정 봉 검증 구현

### 설계 문서 (필요 시 명시적으로 Read)

- `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` - BACKFILL 지표 오염 해결
- `thoughts/20260326-01-Post-Exit-Reentry-Strategy.md` - 재진입 전략

---

## 📊 Issue 통계

**총 Issue**: 15개 (Issue #3, #12 없음)
**Critical (🔴)**: 15개 (100%)
**평균 해결 시간**: 3.9시간
**재발 빈도**: 6.7% (교훈 #12 → #16 재발 1건)

---

**마지막 업데이트**: 2026-05-06
**버전**: 2.2 (Streamlit UI Issue #13-#16 + Filter Logic Issue #17 추가)
