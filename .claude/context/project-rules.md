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
4. **GitHub 커밋 준비** → 변경 내용 명시
   - ⚠️ **필수**: `pages/dashboard.py` 버전 업데이트
   - 형식: `v1.YYYY.MM.DD.HHMM` (예: `v1.2026.05.14.1430`)
   - 위치: `st.markdown(f"### 📊 Dashboard ({mode}) : \`{user_id}\`님 --- v1.YYYY.MM.DD.HHMM")`
   - 버전 미업데이트 시 커밋 금지
5. **GitHub 커밋** → 변경 내용 및 버전 포함
6. **서버 배포 전 승인** → 사용자 확인 ⚠️
7. **서버 배포** → systemd 재시작
8. **서버 테스트** → 실시간 로그 확인 (1시간)
9. **완료 보고** → 검증 결과 보고

**⚠️ 사용자 승인 없이 다음 단계 진행 금지**

---

## ⚠️ 커밋 전 필수 체크리스트 (MANDATORY)

**GitHub 커밋 전 반드시 확인** (순서대로 실행):

### 1단계: 코드 수정 완료 확인
- [ ] 모든 코드 수정 완료
- [ ] Syntax 검증 완료 (`python3 -m py_compile`)
- [ ] 로직 테스트 완료

### 1-A단계 (UI 파일 수정 시 필수): 브라우저 실측 · 접근성 회귀 방지
**⚠️ pages/*.py 수정 시 이 단계 스킵 = 즉시 회귀 위험. 2026-08-05 6건 사고 근거.**

**적용 대상**: `pages/dashboard.py`, `pages/set_buy_sell_conditions.py`, `pages/set_config.py`, `pages/audit_viewer.py` 등 Streamlit UI 파일.

**필수 검증 3층** ([[feedback_ui_render_measurement]] 원칙):

1. **py_compile 만으로는 부족** — 실행 시점 NameError/AttributeError 는 실제 import·render 시에만 발견
   - `bash scripts/regression_gate.sh` 실행 → UI top-level import 게이트 + typing 심볼 검증 자동 통과 확인 (a8f2a5c 유형 봉쇄)

2. **UI 변경 diff 사용자 브리핑** — "추가" 만 보고 "삭제/이동/접힘" 은 개발자가 놓치기 쉬움
   - 커밋 전 diff 검토: `st.subheader → st.expander`, `st.button 위치 이동`, `expanded=True → False` 등 사용자 관점 사라짐 유발 변화 있으면 사용자에게 명시 보고
   - 접힘 처리(`st.expander(expanded=False)`)는 사실상 삭제와 동급 — 자주 쓰는 액션(설정 페이지 이동, 감사 뷰어 등)은 접힘 대상 제외 (아래 "화이트리스트" 참조)

3. **브라우저 실측 필수** — 배포 후 사용자에게 브라우저 새로고침 요청 → 화면 표시 문구/버튼 위치 확인
   - "코드에 있음" ≠ "사용자가 볼 수 있음" — 개발자 관점 vs 사용자 관점 격차 봉쇄

### 1-B단계 (UI 파일 수정 시 필수): 접힘 화이트리스트 원칙
**모바일 UX 개선 시 다음 액션 버튼·섹션은 접힘 대상 제외 (top-level 노출 유지)**:

| 대상 | 이유 |
|---|---|
| 감사로그 뷰어 열기 버튼 | 사용자 자주 접근 (오늘 f0c291a 회귀 사고) |
| 설정 페이지 이동 버튼 | 파라미터 수정 진입점 |
| 헬스 배지 · 동기화 상태 카드 | 봇 정상 상태 확인 진입점 |
| 강제 매수·매도 버튼 | 사용자 즉시 개입 필요 |

접힘(`expanded=False`) 은 상세 정보(전체 파라미터 표, 감사 필터 옵션 등)에만 적용.

**회귀 봉쇄**: `tests/regressions/test_r_2026_08_05_audit_viewer_accessibility.py` 유형처럼 특정 버튼이 top-level 컬럼(`_audit_hdr_col*`) 안에 있는지 lint 필수.

### 2단계: dashboard.py 버전 업데이트 (필수!)
```bash
# ⚠️ CRITICAL: 이 단계를 빠뜨리면 커밋 금지!
# 1. 현재 시간 확인
date '+%H%M'

# 2. dashboard.py 버전 업데이트
# 형식: v1.2026.05.14.HHMM
# 위치: pages/dashboard.py:318 (대략)
# 예: v1.2026.05.14.1430 → v1.2026.05.14.1845
```

**체크리스트**:
- [ ] `date '+%H%M'` 실행하여 현재 시간 확인
- [ ] `grep "v1.2026" pages/dashboard.py` 실행하여 현재 버전 확인
- [ ] `pages/dashboard.py:318` 라인의 버전을 새 시간으로 업데이트
- [ ] `git add pages/dashboard.py` 실행

### 3단계: Git 커밋
```bash
# ⚠️ 반드시 모든 변경 파일 add
git add <수정한_파일들>
git add pages/dashboard.py  # ← 필수!

# 커밋 (heredoc 사용)
git commit -m "$(cat <<'EOF'
...커밋 메시지...
EOF
)"
```

**체크리스트**:
- [ ] `git status`로 변경 파일 확인
- [ ] `pages/dashboard.py`가 Changes to be committed에 포함되었는지 확인
- [ ] 커밋 메시지에 버전 정보 포함
- [ ] `git push` 실행

### 4단계: 서버 배포 승인 대기
- [ ] 사용자에게 "서버 배포를 진행해도 될까요?" 요청
- [ ] ⚠️ 사용자 승인 없이 절대 배포 금지 (Issue #16 교훈)

### 5단계: 서버 배포 (승인 후)
```bash
# deploy-tradebot 명령어 사용 (권장)
deploy-tradebot
```

**체크리스트**:
- [ ] 사용자 승인 확인됨
- [ ] `deploy-tradebot` 실행
- [ ] 배포 로그 확인 (에러 없음)
- [ ] 서비스 상태 확인 (active running)

---

## ❌ 과거 실수 사례 (반복 금지)

### 실수 #1: dashboard.py 버전 미업데이트
**발생일**: 2026-05-14 (2회)
**문제**: app.py 수정 후 커밋 시도 → 사용자가 "작업 규칙에 따라 진행해야 하는거 아닌가?" 지적
**교훈**:
- 코드 수정 후 **무조건** dashboard.py 버전 업데이트
- `git commit` 전 **반드시** "2단계: dashboard.py 버전 업데이트" 실행

### 실수 #2: 교훈 문서 선행 작성
**발생일**: 2026-05-14
**문제**: Issue #20 교훈을 사용자 요청 전에 작성 → 사용자가 삭제 지시
**사용자 지시**: "기록하라고 요청시에만 기록하기. 절대 먼저 앞서서 생각하기. 모르거나 판단이 안되면 묻기."
**교훈**:
- lessons-learned.md는 **사용자 요청 시에만** 작성
- 선제적 교훈 작성 절대 금지

### 실수 #3: 편협적 수정 (Issue #19)
**발생일**: 2026-05-14
**문제**: set_config.py만 수정, dashboard.py 누락 → 문제 지속
**사용자 지시**: "지금까지 작업 및 검증을 지시하면 편협적으로 해당 부분만 확인한다"
**교훈**:
- 상태 변수 수정 전 **반드시** `grep -r "변수명" --include="*.py" .` 실행
- 모든 관련 파일 함께 수정

### 실수 #4: 사용자 승인 없이 배포 (Issue #16)
**발생일**: 2026-05-06
**문제**: 서버 배포를 사용자 승인 없이 진행
**교훈**:
- "서버 배포를 진행해도 될까요?" 필수 질문
- 승인 전 절대 배포 금지

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

## 🛑 세션 재개 표준 정지선 (2026-09-12 신설)

**세션 유실·압축 이후 재개할 때는 어떤 계획서보다 먼저 로컬 git log 와 서버 HEAD·기동 시각·로그 표식을 대조해 현재 상태를 확정한다.**

**근거 사례 (2026-09-12)**: FV1~FV3 조사 후 WO-6 구현 계획서 초안이 §1.1 필수 목록 12개 항목을 "구현 지시"로 나열했다. 사용자 승인을 받고 착수 직전에 실행한 사실 확인에서 이 항목 전부가 이미 `bc582a6` (2026-08-29 배포)에 반영되어 있었고 서버는 이 코드로 8일간 무사고 가동 중이었다. 확인 없이 착수했다면 이미 배포된 코드를 재구현하거나 최악의 경우 WO-2 재적용(`da871da` + `57d290e`)까지 되돌릴 뻔했다. 이 확인 절차로 사고를 막았다.

**표준 정지선 절차 (착수 전 필수)**:

1. **로컬 상태 스냅샷**
   ```
   git log --oneline -10
   git rev-parse HEAD
   ```

2. **서버 상태 스냅샷** (SSH 읽기 전용)
   ```
   ssh root@orionhunter7.cafe24.com "git -C /root/upbit-tradebot-mvp log --oneline -10"
   ssh root@orionhunter7.cafe24.com "git -C /root/upbit-tradebot-mvp rev-parse HEAD"
   ssh root@orionhunter7.cafe24.com "systemctl show tradebot -p ExecMainStartTimestamp"
   ssh root@orionhunter7.cafe24.com "grep -n 'v1.2026' /root/upbit-tradebot-mvp/pages/dashboard.py | head -1"
   ```

3. **실 가동 코드 표식 확인** (계획서·문서 내용을 로그로 교차 확증)
   - 제거되었어야 할 태그 부재 확인 (예: `[SKIP-BAR]`, `upbit_ts` 잔재)
   - 반영되었어야 할 태그 존재 확인 (예: `[PENDING-REGISTER]`, `[LIMIT-FILL]`, `[POSITION-SYNC]`)
   - 실측 로그는 코드 배포보다 신뢰도 높음

4. **불일치 시 정지**
   - 계획서가 "미구현"으로 나열한 항목이 실측에서 존재 → 계획서를 "현실 대조표"로 전환
   - 계획서가 "구현 완료"로 나열한 항목이 실측에서 부재 → 실 배포 이력 재조사
   - 이 정지 없이 진행하면 재구현 · 잘못된 revert · 무사고 코드 파괴 위험

**금지 사항**:
- 로컬 `git log`만 보고 "배포됐다"고 단정 금지 → 서버 SSH 대조 필수
- 계획서 문구("확정판 승인 완료")를 근거로 착수 금지 → 계획서 승인 시점과 실 배포 시점이 다를 수 있음
- FV 조사 등 사후 분석 문서의 "서버 HEAD" 기재를 신뢰 금지 → 사후 분석 시점 이후 재배포가 있을 수 있음

**표준 정지선 사례 인용**: `docs/plans/2026-09-12-post-check/coverage-and-critical.md`, `docs/plans/2026-09-12-wo6-implementation-plan/plan.md` 상단 재분류 절.

---

## 📌 배포 보고 규칙 — 버전 문자열 갱신 명시 (2026-09-12 신설)

**배포 관련 보고 규칙**: `pages/dashboard.py`의 `v1.YYYY.MM.DD.HHMM` 버전 문자열을 갱신한 커밋(또는 후속 fixup)이 포함된 배포는 보고 본문에 **"버전: 구 → 신"** 을 의무 기재한다.

**근거 사례 (2026-09-12)**: WO-8 배포 시 `7d75a10 (v1.2026.09.12.1659)` 후속 보완 커밋 `1618030`이 `1659 → 1715`로 갱신했으나 fixup으로 squash되어 최종 커밋 메시지 헤더에는 `1659`만 남고 실 반영본은 `1715`. 재검증 보고에서 이 갱신을 명시하지 않아 운영자 화면 버전(`1715`)과 보고 표기(`1659`) 불일치. 사용자가 정합 확인 절차로 명시 요구.

**표기 형식 (필수)**:
```
버전: v1.2026.09.12.1659 → v1.2026.09.12.1715  (fixup으로 후속 보완 흡수)
```

**적용 조건**:
- `pages/dashboard.py`의 버전 문자열이 배포 세션 안에서 변경된 경우
- squash · fixup · amend로 여러 갱신이 하나로 합쳐진 경우 (특히 이력이 감춰지는 상황)
- 로컬 최종 커밋 메시지 헤더 표기와 실 코드 반영본이 다른 경우

**검증 시점**: 배포 완료 보고에서 다음 3점 일치를 인용해 확정한다.
- 로컬 HEAD 해시 · 로컬 `dashboard.py` 버전
- 서버 HEAD 해시 · 서버 `dashboard.py` 버전
- ExecMainStartTimestamp

**금지 사항**:
- 커밋 메시지 헤더만 인용해 "버전 = X"로 확정 금지 → 실 코드 인용 필수
- fixup으로 squash된 상황에서 초기 커밋 시각 버전을 최종 버전으로 오해 금지

---

**마지막 업데이트**: 2026-09-12
**버전**: 2.5 (배포 보고 버전 명시 규칙 추가)
