# Upbit Tradebot MVP 문서 재구조화 실행계획

**작성일**: 2026-04-05
**목적**: 루트 디렉토리 마크다운 파일 정리 및 체계적 문서 관리
**접근**: 보수적 방식 (파일 복사 → 병행 운영 → 점진적 삭제)

---

## 📊 현재 상황 분석

### 루트 디렉토리 마크다운 파일 (3개, 총 82KB)

```
CLAUDE.md (57K) - AI 어시스턴트 가이드 ⚠️
CTO_ANALYSIS_CLOSE_PRICE.md (9.5K) - 분석 문서 ⚠️ 날짜별
WO-2026-001_IMPLEMENTATION_REPORT.md (17K) - 구현 보고서 ⚠️
```

### 하위 디렉토리

- `thoughts/`: 2개 (설계 문서 - BACKFILL, Post-Exit Reentry)
- `claude-docs/`: 7개 폴더 (날짜별 분석/구현 문서 아카이브)

### 문제점

1. ❌ 문서 위계 불분명 (어떤 문서부터 읽어야 하는지 모호)
2. ❌ 역사적 문서(claude-docs)와 현행 문서 혼재
3. ❌ README.md 부재 (프로젝트 진입점 없음)
4. ❌ 설계 문서와 구현 문서 분류 모호

---

## ✅ 목표 디렉토리 구조

```
upbit-tradebot-mvp/
├── README.md                    # 프로젝트 메인 (새로 생성)
├── .gitignore
│
├── docs/                        # 📚 사용자 문서 (개발자/운영자용)
│   ├── README.md               # docs 인덱스 (모든 문서 링크)
│   │
│   ├── setup/                  # 설치 및 설정
│   │   ├── installation.md    # 로컬 설치 가이드
│   │   └── deployment.md      # 서버 배포 가이드
│   │
│   ├── operations/             # 운영 가이드
│   │   ├── strategy-params.md # 전략 파라미터 설정
│   │   └── monitoring.md      # 모니터링 및 로그
│   │
│   ├── architecture/           # 시스템 아키텍처
│   │   ├── overview.md        # 전체 구조
│   │   ├── rest-reconcile.md  # REST Reconcile 시스템
│   │   └── indicators.md      # 지표 계산 로직
│   │
│   ├── analysis/               # 분석 문서
│   │   └── close-price-analysis.md  # CTO_ANALYSIS_CLOSE_PRICE.md 이동
│   │
│   └── work-orders/            # 작업 지시서 (WO)
│       └── 2026-001-confirmed-candle.md  # WO-2026-001 이동
│
├── .claude/                     # 🤖 AI 어시스턴트 전용
│   ├── README.md               # Claude Code 사용 가이드
│   └── context/                # 컨텍스트 파일
│       └── project-rules.md    # CLAUDE.md 이동
│
├── thoughts/                    # 💭 기획 및 설계 (기존 유지)
│   ├── 20260325-01-BACKFILL-Golden-Cross-Fix.md
│   └── 20260326-01-Post-Exit-Reentry-Strategy.md
│
└── claude-docs/                 # 📦 역사적 아카이브 (기존 유지)
    └── YYYYMMDD/               # 날짜별 폴더
```

---

## 🎯 실행 계획 (보수적 접근)

### Phase 1: 디렉토리 구조 생성 (5분)

```bash
# 새 디렉토리 생성
mkdir -p docs/setup
mkdir -p docs/operations
mkdir -p docs/architecture
mkdir -p docs/analysis
mkdir -p docs/work-orders
mkdir -p .claude/context
```

### Phase 2: 파일 복사 (이동 X) (10분)

#### A. 분석 문서 복사
```bash
cp CTO_ANALYSIS_CLOSE_PRICE.md docs/analysis/close-price-analysis.md
```

#### B. 작업 지시서 복사
```bash
cp WO-2026-001_IMPLEMENTATION_REPORT.md docs/work-orders/2026-001-confirmed-candle.md
```

#### C. AI 어시스턴트 문서 복사
```bash
cp CLAUDE.md .claude/context/project-rules.md
```

### Phase 3: 인덱스 문서 생성 (15분)

#### A. README.md 생성 (프로젝트 진입점)
- 프로젝트 개요
- 빠른 시작 가이드
- 주요 기능 소개
- 문서 네비게이션

#### B. docs/README.md 생성
- 모든 하위 문서 링크
- 카테고리별 분류
- 빠른 참조 섹션

#### C. .claude/README.md 생성
- Claude Code 사용 가이드
- 컨텍스트 파일 설명

### Phase 4: .gitignore 업데이트 (2분)

```gitignore
# .gitignore에 확인/추가
.claude/
```

### Phase 5: 검증 및 테스트 (5분)

```bash
# 모든 링크 확인
# 문서 가독성 확인
# 누락된 파일 확인
```

### Phase 6: 병행 운영 (2주)

- 새 구조 사용 시작
- 루트 파일은 유지
- 사용자 피드백 수집

### Phase 7: 루트 파일 삭제 (최종)

2주 후, 문제 없으면 루트의 중복 파일 삭제:

```bash
# 삭제 대상 (Phase 7에서만 실행)
rm CLAUDE.md
rm CTO_ANALYSIS_CLOSE_PRICE.md
rm WO-2026-001_IMPLEMENTATION_REPORT.md
```

---

## 📋 파일 매핑 테이블

| 기존 파일 | 새 위치 | 작업 |
|----------|---------|------|
| CLAUDE.md | .claude/context/project-rules.md | 복사 |
| CTO_ANALYSIS_CLOSE_PRICE.md | docs/analysis/close-price-analysis.md | 복사 |
| WO-2026-001_IMPLEMENTATION_REPORT.md | docs/work-orders/2026-001-confirmed-candle.md | 복사 |
| thoughts/*.md | thoughts/*.md | 유지 (변경 없음) |
| claude-docs/* | claude-docs/* | 유지 (역사적 아카이브) |

---

## ⚠️ 주의사항

1. **절대 원본 삭제 금지** (Phase 7 전까지)
2. **링크 검증 필수** (새 문서 내부 링크)
3. **Git 커밋 단위** (Phase별로 커밋)
4. **사용자 공지** (문서 위치 변경 안내)

---

## 🎁 기대 효과

1. ✅ 프로젝트 진입점 생성 (README.md)
2. ✅ 문서 위계 명확화 (docs/ 인덱스 중심)
3. ✅ 역할별 분류 (setup, operations, architecture, analysis, work-orders)
4. ✅ AI 문서 분리 (.claude/)
5. ✅ 역사적 아카이브 보존 (claude-docs/, thoughts/)
6. ✅ 유지보수성 향상

---

## 📅 타임라인

- **Day 1**: Phase 1-5 완료 (오늘)
- **Day 1-14**: Phase 6 병행 운영
- **Day 15**: Phase 7 루트 파일 정리

---

**작성자**: Claude Code (AI Assistant)
**승인자**: 프로젝트 매니저
**최종 업데이트**: 2026-04-05
