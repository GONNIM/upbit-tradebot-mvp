# Boilerplate 적용 계획서

**프로젝트**: Upbit Tradebot MVP
**작성일**: 2026-04-21
**출처**: FoodBid MVP Boilerplate

---

## 📋 개요

이 문서는 **FoodBid MVP Boilerplate**를 Tradebot에 적용하는 계획서입니다.

**목적**: Claude Code 작업 효율 향상 (Anthropic Best Practices 적용)

---

## 📚 상세 문서 위치

**전체 계획서 (FoodBid 프로젝트)**:
```
/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/docs/templates/external-projects/tradebot-boilerplate-application.md
```

**또는 Git 경로**:
```
../../../Project-THETAK/MVP/foodbid-mvp/docs/templates/external-projects/tradebot-boilerplate-application.md
```

---

## 🎯 핵심 목표

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| **CLAUDE.md** | 1,797줄 | **150줄** | 92% 축소 |
| **구조** | Issue 기반 | **WHY/WHAT/HOW** | - |
| **Anthropic 권장** | ❌ (9배 초과) | **✅ 준수** | - |

---

## 🚀 실행 계획 (5단계)

| Phase | 작업 | 소요 시간 | 승인 지점 |
|-------|------|----------|----------|
| **Phase 1** | 백업 및 준비 | 5분 | ✅ #1 |
| **Phase 2** | 새로운 CLAUDE.md (WHY/WHAT/HOW) | 30분 | ✅ #2 |
| **Phase 3** | project-rules.md 재구성 | 20분 | ✅ #3 |
| **Phase 4** | 검증 (4개 시나리오) | 15분 | ✅ #4 |
| **Phase 5** | Git 커밋 | 10분 | ✅ #5 |

**총 소요 시간**: 80분

---

## 📖 주요 내용

### 1. ⚠️ CRITICAL 섹션 추가 (FoodBid 철학)

```markdown
## ⚠️ CRITICAL: Claude Code 작업 수행 원칙

### 🚫 절대 금지
1. 광범위한 와일드카드 검색 금지
2. 병렬 도구 호출 금지
3. 대용량 파일 무분별 읽기 금지

### ✅ 필수 준수
- 작업 시작 전: TodoWrite로 계획
- 지연 발생 시: 즉시 보고
```

### 2. WHY/WHAT/HOW 구조

- **WHY**: 프로젝트 목적 (EMA/MACD 트레이딩 봇)
- **WHAT**: 주요 구조 (core, engine, services)
- **HOW**: 명령어 (로컬 실행, 배포, 테스트)

### 3. Tradebot 특화 내용

- REST Reconcile (미확정 종가 문제 해결)
- Golden/Dead Cross 감지 (BACKFILL 주의)
- 전략 파라미터 (EMA, MACD)

### 4. 문서 계층 구조 (Tier 1/2)

- **Tier 1** (자동 로드): CLAUDE.md, project-rules.md, lessons-learned.md
- **Tier 2** (필요 시 참조): docs/, .backup/

---

## 🔐 안전장치

### 백업
```bash
.backup/$(date +%Y%m%d)/
├── CLAUDE.md.backup (1,797줄)
├── project-rules.md.backup (56KB)
└── lessons-learned.md.backup (21KB)
```

### Rollback
```bash
# 파일 복원
cp .backup/$(date +%Y%m%d)/CLAUDE.md.backup CLAUDE.md

# Git 되돌리기
git reset --soft HEAD~1
```

---

## ✅ 체크리스트

### 실행 전
- [ ] FoodBid 상세 문서 확인
- [ ] 사용자 승인 획득
- [ ] 작업 시간 확보 (80분)

### 실행 중 (5개 승인 지점)
- [ ] Phase 1 완료 → 🚦 승인 #1
- [ ] Phase 2 완료 → 🚦 승인 #2
- [ ] Phase 3 완료 → 🚦 승인 #3
- [ ] Phase 4 완료 → 🚦 승인 #4
- [ ] Phase 5 완료 → 🚦 승인 #5

### 완료 후
- [ ] Git 커밋 완료
- [ ] 백업 유지 확인
- [ ] README.md 업데이트

---

## 📞 문의

**상세 문서**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/docs/templates/external-projects/tradebot-boilerplate-application.md`

**FoodBid 참조**:
- CLAUDE-HOW-TO.md (Anthropic 공식 가이드)
- .claude/context/project-rules.md (핵심 교훈)
- .claude/lessons-learned.md (교훈 인덱스)

---

**마지막 업데이트**: 2026-04-21
**상태**: 계획 수립 완료 (실행 대기)
**다음 단계**: 사용자 승인 후 Phase 1 시작
