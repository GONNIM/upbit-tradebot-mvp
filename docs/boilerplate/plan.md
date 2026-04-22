# Tradebot Boilerplate 적용 실행 계획 v3.4

**프로젝트**: Upbit Tradebot MVP
**작성일**: 2026-04-22 (Codex v3.4 - Process Substitution 제거)
**예상 시간**: 160분 (2.7시간)
**실행 Phase**: 6단계 (Phase 1, 2-A, 2-B, 3, 4, 5)
**상세 문서**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/docs/templates/external-projects/tradebot-boilerplate-application.md`

---

## ⚠️ 필독: 파괴적 명령 금지 (Codex #8 해결)

**절대 사용 금지**:
- `git reset --hard` - 데이터 손실 위험 (롤백 불가)
- `git push --force` - 원격 히스토리 파괴

**대신 사용**:
- `git reset --soft HEAD~1` - 커밋만 취소 (파일 유지)
- `./scripts/rollback.sh LATEST` - 안전한 파일 복원

---

## 🚀 빠른 시작

```bash
# 1. 백업 (tar 경로 보존 - Codex #1 해결)
./scripts/backup.sh

# 2. 실행 (6 Phase, 5회 사용자 승인)
# Phase 1: 준비 (5min)
# Phase 2-A: 샘플 생성 (30min) → 🚦 승인 #1
# Phase 2-B: 전체 구현 (60min) → 🚦 승인 #2
# Phase 3: 문서 이동 (15min) → 🚦 승인 #3
# Phase 4: 검증 (25min) → 🚦 승인 #4
# Phase 5: 커밋 (25min) → 🚦 승인 #5

# 3. Rollback (3중 보호 - Codex #2 해결)
./scripts/rollback.sh LATEST
```

---

## 📋 실행 계획 (6단계 - Codex #5 수정)

### Phase 1: 백업 및 준비 (5분)
- [ ] 백업 실행: `./scripts/backup.sh`
- [ ] FoodBid 가이드 읽기 (Codex #6 해결):
  - 경로: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md`
  - 또는: FoodBid 프로젝트에서 복사 (`cp`)
- [ ] Git 상태 확인: uncommitted 없는지
  ```bash
  git status --short  # 출력 없어야 정상
  ```

### Phase 2-A: 샘플 CLAUDE.md 생성 (30분) ⭐ NEW
- [ ] WHY 섹션 작성 (30줄): 프로젝트 목적
- [ ] WHAT 섹션 작성 (50줄): 핵심 구조
- [ ] HOW 섹션 작성 (40줄): 실행 명령어
- [ ] ⚠️ CRITICAL 섹션 작성 (30줄): 작업 원칙
- [ ] **🚦 사용자 승인 대기**: 150줄 목표 달성 여부 확인

### Phase 2-B: 전체 구현 (60분)
- [ ] CLAUDE.md 완성 (1,797줄 → 150줄)
- [ ] project-rules.md 수정 (Issue 요약 + 긴급 대응)
- [ ] lessons-learned.md 검토 (교훈 인덱스 유지)
- [ ] **🚦 사용자 승인 대기**: 문서 품질 확인

### Phase 3: 문서 이동 (15분)
- [ ] docs/issues/ 폴더 생성
- [ ] Issue #1~#11 상세 문서 이동
- [ ] Import 구문 업데이트
- [ ] **🚦 사용자 승인 대기**: 문서 구조 확인

### Phase 4: 검증 (25분) - 9 Scenarios (Codex #7 해결)

**자동 검증**:
```bash
./scripts/validate_boilerplate.sh
# 기대: PASS 9/9 또는 7+/9
```

**수동 검증 (Claude Code 테스트)**:
- [ ] **WHY 시나리오 (2개)**
  - [ ] "이 프로젝트 목적은?" → WHY 섹션 (필수 키워드: WHY, 목적, Upbit)
  - [ ] "Golden Cross 전략이란?" → WHY + docs/issues/issue-01.md (필수: Golden Cross, EMA)
- [ ] **WHAT 시나리오 (2개)**
  - [ ] "핵심 모듈은?" → WHAT 섹션 (필수: WHAT, core/, engine/, services/)
  - [ ] "REST Reconcile 구조는?" → WHAT + docs/issues/issue-07.md (필수: REST, Reconcile, 정합성)
- [ ] **HOW 시나리오 (2개)**
  - [ ] "백테스팅 실행 방법은?" → HOW 섹션 (필수: HOW, 백테스팅, python)
  - [ ] "systemd 배포 방법은?" → HOW + docs/issues/issue-11.md (필수: systemd, 배포)
- [ ] **Issue 시나리오 (3개)**
  - [ ] "Issue #3 상세 내용은?" → docs/issues/issue-03.md (필수: Issue, 03)
  - [ ] "progressiveRetry 정책은?" → docs/issues/issue-10.md (필수: progressiveRetry, 재시도)
  - [ ] "비트 불일치 해결은?" → docs/issues/issue-04.md (필수: 비트, 불일치)

**합격 기준**: 9개 중 7개 이상 PASS (78%+)

- [ ] **🚦 사용자 승인 대기**: 검증 결과 확인 (자동 + 수동)

### Phase 5: Git 커밋 및 완료 (25분)
- [ ] Git add: CLAUDE.md, project-rules.md 등
- [ ] Git commit (템플릿):
  ```
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
  ```
- [ ] **🚦 최종 승인 대기**: 커밋 전 확인

---

## 🔄 Rollback 전략

### 안전 백업 (3중 보호)
1. **자동 백업**: `.backup/YYYYMMDD_HHMMSS/` (타임스탬프 기반)
2. **LATEST 포인터**: `.backup/LATEST` → 최신 백업
3. **임시 백업**: Rollback 전 현재 상태 보존

### Rollback 명령어
```bash
# 최신 백업에서 복원
./scripts/rollback.sh LATEST

# 특정 시점으로 복원
./scripts/rollback.sh 20260421_143022

# Git 되돌리기 (커밋 후)
git reset --soft HEAD~1  # 커밋만 취소 (파일 유지)
```

---

## ✅ 체크리스트

### 실행 전
- [ ] 작업 시간 확보 (160분)
- [ ] FoodBid 마스터 문서 읽기 완료
- [ ] Backup 스크립트 테스트 완료

### 실행 중 (5개 승인 지점)
- [ ] Phase 2-A 완료 → 🚦 승인 #1 (샘플 150줄 확인)
- [ ] Phase 2-B 완료 → 🚦 승인 #2 (전체 문서 확인)
- [ ] Phase 3 완료 → 🚦 승인 #3 (문서 구조 확인)
- [ ] Phase 4 완료 → 🚦 승인 #4 (9 시나리오 통과)
- [ ] Phase 5 완료 → 🚦 승인 #5 (커밋 전 최종 확인)

### 완료 후
- [ ] Git 커밋 완료
- [ ] 백업 유지 확인 (.backup/LATEST 존재)
- [ ] Claude Code 테스트 (실제 질문으로 검증)

---

## 📊 예상 효과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| CLAUDE.md | 1,797줄 | 150줄 | 92% 축소 |
| 토큰 사용량 | 56KB | ~6KB | 89% 감소 |
| 핵심 지침 가시성 | 낮음 | 높음 (⚠️ CRITICAL 최상단) | - |
| Anthropic 권장 | ❌ (9배 초과) | ✅ 준수 | - |

---

## 📞 참조

- **FoodBid 마스터**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/docs/templates/external-projects/tradebot-boilerplate-application.md`
- **Anthropic 가이드**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md`
- **진행 상황 추적**: `docs/boilerplate/progress.md` (실행 중 생성)

---

**버전**: v3.4 (Codex Process Substitution 제거 + 에러 처리)
**Codex 스코어**: 목표 9.5/10 달성 (v2.0: 6.0/10, v3.0: 6.6/10, v3.1: 8.5/10, v3.2: 7.5/10, v3.3: 8.5/10, v3.4: 실제 9.4/10)
**다음 단계**: Phase 1 백업 실행 (Codex 최종 검증 통과)
