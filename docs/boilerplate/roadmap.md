# Boilerplate 적용 작업 로드맵

**프로젝트**: Upbit Tradebot MVP
**작성일**: 2026-04-22
**버전**: v3.4
**목적**: FoodBid Boilerplate 적용 실행 일정 및 승인 지점 가이드

---

## 📅 전체 일정 개요

**총 소요 시간**: 160분 (2시간 40분)
**실행 단계**: 6 Phase
**승인 지점**: 5회 (사용자 확인 필수)
**작업 날짜**: 2026-04-22

---

## 🗺️ Phase별 로드맵

```
┌─────────────────────────────────────────────────────────────────┐
│                    Boilerplate 적용 타임라인                      │
│                      (총 160분 / 2.7시간)                         │
└─────────────────────────────────────────────────────────────────┘

Phase 1: 백업 및 준비
├─ 소요: 5분
├─ 작업: 백업 실행 + Git 상태 확인
└─ 승인: 없음 (자동 진행)
    │
    ▼
Phase 2-A: 샘플 CLAUDE.md 생성
├─ 소요: 30분
├─ 작업: WHY/WHAT/HOW/CRITICAL 섹션 작성 (150줄)
└─ 🚦 승인 #1: 샘플 150줄 확인 (사용자)
    │
    ▼
Phase 2-B: 전체 구현
├─ 소요: 60분
├─ 작업: CLAUDE.md 완성 (1,797→150줄) + project-rules.md 수정
└─ 🚦 승인 #2: 문서 품질 확인 (사용자)
    │
    ▼
Phase 3: 문서 이동
├─ 소요: 15분
├─ 작업: docs/issues/ 생성 + Issue #1~#11 이동
└─ 🚦 승인 #3: 문서 구조 확인 (사용자)
    │
    ▼
Phase 4: 검증
├─ 소요: 25분
├─ 작업: 자동 검증 (9개) + 수동 검증 (Claude Code 테스트)
└─ 🚦 승인 #4: 검증 결과 확인 (사용자)
    │
    ▼
Phase 5: Git 커밋 및 완료
├─ 소요: 25분
├─ 작업: Git add + commit (BREAKING CHANGE)
└─ 🚦 승인 #5: 커밋 전 최종 확인 (사용자)
    │
    ▼
✅ 완료
```

---

## ⏱️ 시간별 상세 일정

| 시작 | 종료 | 소요 | Phase | 작업 내용 | 승인 |
|------|------|------|-------|----------|------|
| +0분 | +5분 | 5분 | **Phase 1** | 백업 실행 (`./scripts/backup.sh`) | - |
| +5분 | +35분 | 30분 | **Phase 2-A** | WHY/WHAT/HOW/CRITICAL 섹션 작성 | 🚦 #1 |
| +35분 | +95분 | 60분 | **Phase 2-B** | CLAUDE.md 완성 + project-rules.md | 🚦 #2 |
| +95분 | +110분 | 15분 | **Phase 3** | docs/issues/ 문서 이동 | 🚦 #3 |
| +110분 | +135분 | 25분 | **Phase 4** | 검증 (자동 9개 + 수동) | 🚦 #4 |
| +135분 | +160분 | 25분 | **Phase 5** | Git 커밋 및 완료 | 🚦 #5 |

**예상 완료 시간**: 시작 시점 + 2시간 40분

---

## 🚦 승인 지점 상세

### 승인 #1: Phase 2-A 완료 후 (30분 시점)

**확인 항목**:
- [ ] WHY 섹션 작성 완료 (30줄, 프로젝트 목적)
- [ ] WHAT 섹션 작성 완료 (50줄, 핵심 구조)
- [ ] HOW 섹션 작성 완료 (40줄, 실행 명령어)
- [ ] ⚠️ CRITICAL 섹션 작성 완료 (30줄, 작업 원칙)
- [ ] 총 150줄 목표 달성 여부

**사용자 결정**: 샘플 품질 승인 → Phase 2-B 진행

---

### 승인 #2: Phase 2-B 완료 후 (95분 시점)

**확인 항목**:
- [ ] CLAUDE.md 완성 (1,797줄 → 150줄, 92% 축소)
- [ ] project-rules.md 수정 (Issue 요약 + 긴급 대응)
- [ ] lessons-learned.md 검토 (교훈 인덱스 유지)
- [ ] Import 구문 정확성 (`@docs/issues/issue-01.md`)
- [ ] 문서 가독성 및 품질

**사용자 결정**: 문서 품질 승인 → Phase 3 진행

---

### 승인 #3: Phase 3 완료 후 (110분 시점)

**확인 항목**:
- [ ] `docs/issues/` 폴더 생성
- [ ] Issue #1~#11 상세 문서 이동 완료
- [ ] Import 구문 업데이트 (경로 정확성)
- [ ] 원본 파일 정리 (중복 제거)
- [ ] 문서 구조 적절성

**사용자 결정**: 문서 구조 승인 → Phase 4 진행

---

### 승인 #4: Phase 4 완료 후 (135분 시점)

**확인 항목**:

**자동 검증 결과**:
- [ ] `./scripts/validate_boilerplate.sh` 실행 결과
- [ ] PASS 7+/9 (78% 이상 합격)

**수동 검증 결과** (Claude Code 테스트):
- [ ] WHY 시나리오 2개 통과
- [ ] WHAT 시나리오 2개 통과
- [ ] HOW 시나리오 2개 통과
- [ ] Issue 시나리오 3개 통과

**사용자 결정**: 검증 통과 승인 → Phase 5 진행

---

### 승인 #5: Phase 5 완료 후 (160분 시점)

**확인 항목**:
- [ ] Git 변경 사항 확인 (`git status`)
- [ ] 커밋 메시지 검토
- [ ] BREAKING CHANGE 표기 확인
- [ ] Co-Authored-By 확인
- [ ] 최종 백업 존재 확인 (`.backup/LATEST`)

**사용자 결정**: 최종 승인 → Git 커밋 실행

---

## 📋 Phase별 상세 작업 내용

### Phase 1: 백업 및 준비 (5분)

**작업 순서**:
```bash
1. 백업 실행
   ./scripts/backup.sh
   → .backup/YYYYMMDD_HHMMSS/ 생성

2. FoodBid 가이드 읽기
   /Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md

3. Git 상태 확인
   git status --short
   → 출력 없어야 정상
```

**산출물**:
- `.backup/YYYYMMDD_HHMMSS/files.tar.gz`
- `.backup/YYYYMMDD_HHMMSS/git-full-state.txt`
- `.backup/LATEST` (심볼릭 링크)

---

### Phase 2-A: 샘플 CLAUDE.md 생성 (30분)

**작업 순서**:
```markdown
1. WHY 섹션 작성 (30줄)
   - Upbit 자동매매 봇 목적
   - EMA/MACD 전략 기반
   - REST Reconcile 데이터 정합성

2. WHAT 섹션 작성 (50줄)
   - core/ (전략 엔진)
   - engine/ (실행 루프)
   - services/ (Upbit API, DB)

3. HOW 섹션 작성 (40줄)
   - 로컬 실행 명령어
   - 백테스팅 실행 방법
   - systemd 배포 방법

4. ⚠️ CRITICAL 섹션 작성 (30줄)
   - 작업 수행 원칙
   - 금지 사항
   - 필수 체크리스트
```

**산출물**: CLAUDE.md (초안 150줄)

**🚦 승인 #1 대기**

---

### Phase 2-B: 전체 구현 (60분)

**작업 순서**:
```markdown
1. CLAUDE.md 완성 (1,797줄 → 150줄)
   - Import 구문으로 상세 문서 참조
   - Issue #1~#11 링크 추가
   - 핵심 명령어만 유지

2. project-rules.md 수정
   - Issue 요약 추가
   - 긴급 대응 우선순위 업데이트

3. lessons-learned.md 검토
   - 교훈 인덱스 유지 확인
   - Import 구문 정확성 확인
```

**산출물**:
- `CLAUDE.md` (최종 150줄)
- `.claude/context/project-rules.md` (수정)

**🚦 승인 #2 대기**

---

### Phase 3: 문서 이동 (15분)

**작업 순서**:
```bash
1. docs/issues/ 폴더 생성
   mkdir -p docs/issues

2. Issue #1~#11 상세 문서 이동
   mv issue-01-*.md docs/issues/issue-01.md
   mv issue-02-*.md docs/issues/issue-02.md
   ...
   mv issue-11-*.md docs/issues/issue-11.md

3. Import 구문 업데이트
   CLAUDE.md 내 모든 @docs/issues/ 경로 확인
```

**산출물**:
- `docs/issues/issue-01.md` ~ `issue-11.md` (11개 파일)

**🚦 승인 #3 대기**

---

### Phase 4: 검증 (25분)

**작업 순서**:

**자동 검증 (10분)**:
```bash
./scripts/validate_boilerplate.sh

# 기대 결과:
# PASS: 7+ / 9 (78% 이상)
```

**수동 검증 (15분)** - Claude Code 테스트:
```
질문 1: "이 프로젝트 목적은?"
→ WHY 섹션 확인 (필수: WHY, 목적, Upbit)

질문 2: "Golden Cross 전략이란?"
→ WHY + docs/issues/issue-01.md

질문 3: "핵심 모듈은?"
→ WHAT 섹션 (필수: WHAT, core/, engine/, services/)

질문 4: "REST Reconcile 구조는?"
→ WHAT + docs/issues/issue-07.md

질문 5: "백테스팅 실행 방법은?"
→ HOW 섹션 (필수: HOW, 백테스팅, python)

질문 6: "systemd 배포 방법은?"
→ HOW + docs/issues/issue-11.md

질문 7: "Issue #3 상세 내용은?"
→ docs/issues/issue-03.md

질문 8: "progressiveRetry 정책은?"
→ docs/issues/issue-10.md

질문 9: "비트 불일치 해결은?"
→ docs/issues/issue-04.md
```

**산출물**: 검증 결과 보고서

**🚦 승인 #4 대기**

---

### Phase 5: Git 커밋 및 완료 (25분)

**작업 순서**:
```bash
1. Git add (15분)
   git add CLAUDE.md
   git add .claude/context/project-rules.md
   git add .claude/lessons-learned.md
   git add docs/issues/

2. Git commit (10분)
   git commit -m "$(cat <<'EOF'
   refactor(docs): CLAUDE.md Anthropic Best Practices 적용

   BREAKING CHANGE: CLAUDE.md 구조 개편 (1,797줄 → 150줄, 92% 축소)

   변경 사항:
   - WHY/WHAT/HOW 구조 도입
   - Issue #1~#11 상세 문서 분리 (docs/issues/)
   - ⚠️ CRITICAL 섹션 추가 (작업 원칙)
   - Import 구문으로 모듈화

   효과:
   - Anthropic 권장 200줄 이하 준수
   - 핵심 지침 가시성 향상
   - Claude Code 작업 효율 개선

   참조: docs/boilerplate/plan.md

   Co-Authored-By: FoodBid MVP Team <noreply@anthropic.com>
   EOF
   )"

3. 백업 유지 확인
   ls -la .backup/LATEST
```

**산출물**: Git 커밋 (1개)

**🚦 승인 #5 대기**

---

## 🔒 안전 장치

### 백업 전략 (3중 보호)

1. **자동 백업**: `.backup/YYYYMMDD_HHMMSS/` (Phase 1 생성)
2. **LATEST 포인터**: `.backup/LATEST` → 최신 백업
3. **임시 백업**: Rollback 전 현재 상태 보존

### Rollback 방법

```bash
# 최신 백업에서 복원
./scripts/rollback.sh LATEST

# 특정 시점으로 복원
./scripts/rollback.sh 20260422_HHMMSS

# Git 되돌리기 (커밋 후)
git reset --soft HEAD~1  # 커밋만 취소 (파일 유지)
```

### 금지 사항 (절대 실행 안 함)

```bash
❌ git reset --hard       # 데이터 손실 위험
❌ git push --force       # 원격 히스토리 파괴
❌ rm -rf CLAUDE.md       # 백업 없이 삭제
```

---

## ✅ 작업 전 최종 체크리스트

### 환경 준비
- [ ] Git 상태 clean (`git status` 확인)
- [ ] 작업 시간 확보 (2시간 40분)
- [ ] FoodBid 가이드 읽기 완료
- [ ] Backup 스크립트 실행 가능 확인

### 문서 확인
- [ ] `docs/boilerplate/plan.md` 읽기 완료
- [ ] Rollback 방법 숙지
- [ ] 승인 지점 5개 인지

### 사용자 준비
- [ ] 5회 승인 준비 (각 Phase 완료 시)
- [ ] 검증 시나리오 9개 테스트 준비
- [ ] 최종 커밋 검토 준비

---

## 🎯 예상 결과

**Before**:
- CLAUDE.md: 1,797줄
- 토큰 사용량: ~56KB
- Anthropic 권장: ❌ (9배 초과)

**After**:
- CLAUDE.md: 150줄 (92% 축소)
- 토큰 사용량: ~6KB (89% 감소)
- Anthropic 권장: ✅ 준수

**효과**:
- Claude Code 작업 효율 향상
- 핵심 지침 가시성 향상 (⚠️ CRITICAL 최상단)
- 문서 구조화 (WHY/WHAT/HOW + Import)

---

## 📞 참조 문서

- **실행 계획**: `docs/boilerplate/plan.md` (v3.4)
- **README**: `docs/boilerplate/README.md` (v3.4)
- **백업 스크립트**: `scripts/backup.sh` (v3.4)
- **롤백 스크립트**: `scripts/rollback.sh` (v3.4)
- **검증 스크립트**: `scripts/validate_boilerplate.sh` (v3.1)
- **FoodBid 가이드**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md`

---

**마지막 업데이트**: 2026-04-22
**버전**: v3.4
**상태**: 실행 대기 (사용자 승인 후 Phase 1 시작)
