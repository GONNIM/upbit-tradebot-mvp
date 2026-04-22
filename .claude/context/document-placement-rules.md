# Upbit Tradebot MVP 문서 배치 규칙

**목적**: 새 문서 생성 시 올바른 디렉토리에 배치하는 규칙

**⚠️ 중요**: 문서 생성 전 **반드시** 이 규칙을 읽고 따를 것!

---

## 📋 의사결정 트리 (5초 안에 결정)

```
새 문서 생성 필요?
  │
  ├─ AI 교훈/규칙?
  │   ├─ 과거 트러블슈팅 교훈? → .claude/lessons-learned.md 업데이트 (/lesson 명령 사용)
  │   ├─ 프로젝트 규칙? → .claude/context/project-rules.md 업데이트 (CLAUDE.md 동기화)
  │   └─ 문서 배치 규칙? → .claude/context/document-placement-rules.md 업데이트 (본 파일)
  │
  ├─ 설치/배포 가이드?
  │   ├─ 로컬 설치? → docs/setup/installation.md
  │   └─ 서버 배포? → docs/setup/deployment.md
  │
  ├─ 운영/모니터링?
  │   ├─ 전략 파라미터 설정? → docs/operations/strategy-params.md ⭐
  │   ├─ 로그 확인/모니터링? → docs/operations/monitoring.md
  │   └─ 트러블슈팅? → docs/operations/troubleshooting.md
  │
  ├─ 시스템 아키텍처?
  │   ├─ 전체 구조? → docs/architecture/overview.md ⭐
  │   ├─ REST Reconcile? → docs/architecture/rest-reconcile.md
  │   ├─ 지표 계산? → docs/architecture/indicators.md
  │   └─ 새 아키텍처 문서? → docs/architecture/{주제}.md
  │
  ├─ 분석 보고서?
  │   ├─ 종가 분석? → docs/analysis/close-price-analysis.md (기존)
  │   └─ 새 분석? → docs/analysis/YYYY-MM-DD-{주제}.md
  │
  ├─ 작업 지시서?
  │   ├─ 확정 봉 검증? → docs/work-orders/2026-001-confirmed-candle.md (기존)
  │   └─ 새 작업 지시서? → docs/work-orders/YYYY-NNN-{주제}.md
  │
  └─ 설계 문서/아이디어?
      ├─ BACKFILL 수정? → thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md (기존)
      ├─ 재진입 전략? → thoughts/20260326-01-Post-Exit-Reentry-Strategy.md (기존)
      └─ 새 설계? → thoughts/YYYYMMDD-NN-{주제}.md
```

---

## 🚫 절대 금지 사항

### 1. 루트 MD 파일 생성 금지

**❌ 절대 금지**:
```
/NEW_DOCUMENT.md  ← 루트에 MD 파일 생성 금지!
```

**✅ 올바른 위치**:
```
/docs/operations/new-document.md
/docs/architecture/new-system.md
/thoughts/20260405-01-new-idea.md
```

**예외 (허용되는 루트 MD 파일)**:
- `README.md` (프로젝트 메인)
- `DOCS_REORGANIZATION_*.md` (3개, 문서 재구조화 관련)
- `CLAUDE.md` (프로젝트 규칙, Git 추적)

### 2. 중복 문서 생성 금지

**기존 문서 확인 필수**:
```bash
# 기존 문서 검색
grep -r "주제" docs/ thoughts/
find docs/ -name "*주제*.md"
```

**❌ 중복 생성**:
```
docs/architecture/rest-reconcile.md (기존)
docs/architecture/rest-reconcile-system.md (중복!)
```

**✅ 기존 문서 업데이트**:
```
docs/architecture/rest-reconcile.md 업데이트
```

### 3. 한글 파일명 금지

**❌ 금지**:
```
docs/operations/골든크로스-분석.md
docs/architecture/전략-파라미터.md
```

**✅ 영문 kebab-case**:
```
docs/operations/golden-cross-analysis.md
docs/architecture/strategy-parameters.md
```

---

## 📁 디렉토리별 상세 규칙

### docs/setup/ - 설치 및 배포

**목적**: 프로젝트 설치 및 배포 절차

**파일명 규칙**: `{주제}.md`

**예시**:
- `installation.md` - 로컬 설치 가이드
- `deployment.md` - 서버 배포 가이드

**언제 사용**:
- 처음 프로젝트를 설치할 때 참조
- 서버에 봇을 배포할 때 참조

### docs/operations/ - 운영 가이드

**목적**: 봇 운영 중 참조하는 실무 가이드

**파일명 규칙**: `{주제}.md`

**예시**:
- `strategy-params.md` ⭐ - 전략 파라미터 설정 (EMA, MACD, 필터)
- `monitoring.md` - 로그 확인 및 성능 모니터링
- `troubleshooting.md` - 트러블슈팅 가이드

**언제 사용**:
- Trailing Stop 비율 변경할 때
- Take Profit 목표 수정할 때
- 로그 파일 위치 찾을 때
- 매매 기록 확인할 때

### docs/architecture/ - 시스템 아키텍처

**목적**: 시스템 내부 구조 및 핵심 로직 이해

**파일명 규칙**: `{주제}.md`

**예시**:
- `overview.md` ⭐ - 전체 아키텍처 (엔진, 전략, 필터)
- `rest-reconcile.md` - REST API 정합성 검증 시스템
- `indicators.md` - EMA/MACD 증분 계산 로직

**언제 사용**:
- Golden Cross 감지 원리 이해할 때
- BACKFILL 동작 방식 이해할 때
- 필터 시스템 구조 파악할 때
- 코드 수정 전 설계 이해할 때

### docs/analysis/ - 분석 문서

**목적**: 특정 이슈 분석 보고서

**파일명 규칙**: `YYYY-MM-DD-{주제}.md` 또는 `{주제}-analysis.md`

**예시**:
- `close-price-analysis.md` - 종가 미확정 문제 분석 (CTO)
- `2026-04-05-golden-cross-failure.md` - Golden Cross 미감지 분석

**언제 사용**:
- DB 종가와 Upbit 차트 종가 불일치 조사할 때
- REST API 미확정 종가 문제 이해할 때
- 봉 검증 로직 개선할 때

### docs/work-orders/ - 작업 지시서

**목적**: 과거 작업 지시서(WO) 및 구현 보고서

**파일명 규칙**: `YYYY-NNN-{주제}.md` (예: `2026-001-confirmed-candle.md`)

**예시**:
- `2026-001-confirmed-candle.md` - WO-2026-001: 확정 봉 검증 구현
- `2026-002-filter-optimization.md` - WO-2026-002: 필터 최적화

**언제 사용**:
- 과거 작업 지시서 확인할 때
- 구현 결과 검증할 때
- 유사한 작업 계획 수립 시 참고할 때

### thoughts/ - 설계 문서

**목적**: 최신 설계 문서 및 아이디어

**파일명 규칙**: `YYYYMMDD-NN-{주제}.md`

**예시**:
- `20260325-01-BACKFILL-Golden-Cross-Fix.md` - BACKFILL 지표 오염 수정
- `20260326-01-Post-Exit-Reentry-Strategy.md` - 매도 후 재진입 전략
- `20260405-01-New-Filter-Idea.md` - 새 필터 아이디어

**언제 사용**:
- 최신 설계 문서 확인할 때
- 전략 개선 아이디어 검토할 때

**Git 추적**: ❌ (.gitignore에 등록, 로컬 전용)

---

## 🎯 실전 예시

### 예시 1: Golden Cross 트러블슈팅 분석 문서 작성

**사용자 요청**: "Golden Cross가 감지 안 됐어. 분석 문서 작성해줘."

**의사결정 트리**:
```
분석 보고서? → YES
→ docs/analysis/YYYY-MM-DD-{주제}.md
```

**올바른 위치**:
```
docs/analysis/2026-04-05-golden-cross-failure-analysis.md
```

**파일 내용**:
```markdown
# Golden Cross 미감지 분석 (2026-04-05)

## 문제 상황
...

## 근본 원인
...

## 해결 방법
...

## 관련 문서
- .claude/context/project-rules.md Issue #11
- docs/architecture/indicators.md
```

### 예시 2: 새로운 필터 구현 가이드 작성

**사용자 요청**: "새 필터 구현 가이드 작성해줘."

**의사결정 트리**:
```
운영/모니터링? → 아니오 (개발 가이드)
시스템 아키텍처? → YES
→ docs/architecture/{주제}.md
```

**올바른 위치**:
```
docs/architecture/filter-implementation-guide.md
```

### 예시 3: 과거 OOM 사고 교훈 기록

**사용자 요청**: "OOM 사고 교훈 기록해줘."

**의사결정 트리**:
```
AI 교훈/규칙? → YES
과거 트러블슈팅 교훈? → YES
→ .claude/lessons-learned.md 업데이트
```

**올바른 방법**:
```
/lesson 명령 사용
또는
.claude/lessons-learned.md 직접 편집 (교훈 #12 추가)
```

---

## 📝 문서 생성 체크리스트

### 생성 전 (필수)

- [ ] 의사결정 트리로 올바른 디렉토리 선택
- [ ] 기존 문서 검색 (중복 확인)
- [ ] 파일명 규칙 확인 (kebab-case, 날짜 형식)
- [ ] 사용자에게 위치 확인 (불확실하면)

### 생성 후 (선택)

- [ ] docs/README.md 인덱스 업데이트 (필요 시)
- [ ] 관련 문서에 링크 추가
- [ ] Git 추적 상태 확인

---

## ⚠️ 예외 처리

### 예외 1: 긴급 문서 (임시)

긴급 상황에서 임시로 루트에 MD 파일 생성 가능하나, **24시간 이내** 적절한 위치로 이동:

```bash
# 긴급 생성
/EMERGENCY_FIX_2026-04-05.md

# 24시간 이내 이동
mv EMERGENCY_FIX_2026-04-05.md docs/analysis/2026-04-05-emergency-fix.md
```

### 예외 2: 마이그레이션 문서 (백업)

문서 재구조화 시 백업 폴더 사용:

```
/migration-backup/20260405-root-files/
  ├── OLD_DOCUMENT_1.md
  └── OLD_DOCUMENT_2.md
```

---

## 🎓 Best Practices

### 1. 문서 생성 전 항상 검색

```bash
# 주제 관련 문서 검색
grep -r "REST Reconcile" docs/
find docs/ -name "*reconcile*.md"
```

### 2. 파일명 규칙 일관성 유지

**날짜 형식**:
- docs/analysis: `YYYY-MM-DD-{주제}.md`
- thoughts: `YYYYMMDD-NN-{주제}.md`
- docs/work-orders: `YYYY-NNN-{주제}.md`

**주제 형식**:
- kebab-case 사용
- 소문자
- 영문만 (한글 금지)

### 3. 관련 문서 링크 추가

```markdown
## 관련 문서

- [시스템 아키텍처](../architecture/overview.md)
- [Issue #11](./.claude/context/project-rules.md#issue-11)
- [BACKFILL 수정](../thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md)
```

### 4. docs/README.md 인덱스 업데이트

새 문서 생성 시 `docs/README.md`의 빠른 참조 표에 추가:

```markdown
| 작업 | 문서 | 소요 시간 |
|------|------|----------|
| 새 필터 구현 | [필터 가이드](architecture/filter-guide.md) | 10분 |
```

---

## 🔍 트러블슈팅

### Q1: 어느 디렉토리에 넣어야 할지 모르겠어요

**A**: 의사결정 트리를 따라가세요. 여전히 불확실하면:
1. 사용자에게 "docs/operations 또는 docs/architecture 중 어디에 넣을까요?" 질문
2. 유사한 기존 문서 찾기
3. 임시로 thoughts/에 작성 후 나중에 이동

### Q2: 기존 문서와 중복인 것 같은데...

**A**: 기존 문서 업데이트 우선:
1. 기존 문서 읽기
2. 새 내용 추가 (섹션 추가)
3. 중복 생성하지 않기

### Q3: 파일명이 너무 길어요

**A**: 약어 사용 또는 핵심 키워드만:
```
# 길어짐
docs/analysis/2026-04-05-golden-cross-failure-due-to-backfill-indicator-pollution.md

# 간결함
docs/analysis/2026-04-05-golden-cross-failure.md
```

---

**최종 업데이트**: 2026-04-05
**작성자**: Claude Code (AI Assistant)
**적용 프로젝트**: Upbit Tradebot MVP
**참고**: FoodBid MVP 문서 배치 규칙 기반
