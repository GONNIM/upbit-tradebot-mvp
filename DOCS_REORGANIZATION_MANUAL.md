# Upbit Tradebot MVP 문서 구조 활용 매뉴얼

> **"문서는 코드만큼 중요합니다. 체계적인 문서는 개발 효율을 2배로 높입니다."**

---

## 📖 이 매뉴얼의 목적

이 문서는 Upbit Tradebot MVP 프로젝트의 **문서 재구성 프로젝트** 결과물을 최대한 활용하기 위한 완전한 가이드입니다.

**대상 독자:**
- 프로젝트에 처음 합류하는 개발자
- 트레이딩 봇 전략을 이해하고 수정해야 하는 트레이더
- Claude Code AI와 협업하는 개발자
- 미래의 나 자신

**읽는 시간:** 약 15분
**숙달 시간:** 약 1주일 (실제 사용 경험)

---

## 🎯 목차

1. [왜 문서를 재구성했는가?](#1-왜-문서를-재구성했는가)
2. [새로운 문서 구조 이해하기](#2-새로운-문서-구조-이해하기)
3. [문서 검색 및 활용 방법](#3-문서-검색-및-활용-방법)
4. [Claude Code와 효과적으로 소통하기](#4-claude-code와-효과적으로-소통하기)
5. [문서 작성 및 업데이트 가이드라인](#5-문서-작성-및-업데이트-가이드라인)
6. [자주 묻는 질문 (FAQ)](#6-자주-묻는-질문-faq)
7. [베스트 프랙티스](#7-베스트-프랙티스)

---

## 1. 왜 문서를 재구성했는가?

### 1.1 문제 상황 (As-Is)

**2026년 4월 5일 이전 상태:**
```
프로젝트 루트/
├── CLAUDE.md (57K) - AI 가이드
├── CTO_ANALYSIS_CLOSE_PRICE.md (9.5K) - 분석
├── WO-2026-001_IMPLEMENTATION_REPORT.md (17K) - 작업 보고서
├── thoughts/
│   ├── 20260325-01-BACKFILL-Golden-Cross-Fix.md
│   └── 20260326-01-Post-Exit-Reentry-Strategy.md
└── claude-docs/
    ├── 20260212/ (7개 파일)
    ├── 20260213/ (6개 파일)
    └── ... (총 7개 날짜 폴더)
```

**주요 문제점:**
1. **진입점 부재** - README.md 없음, 어디서 시작해야 할지 불명확
2. **문서 분류 모호** - 현행 문서와 역사적 아카이브 혼재
3. **검색 어려움** - "REST Reconcile 설계 문서 어디 있지?" → claude-docs 7개 폴더 순회
4. **AI 컨텍스트 노출** - CLAUDE.md가 프로젝트 루트에 위치

### 1.2 목표 (To-Be)

**핵심 목표 3가지:**
1. **검색성 (Findability)** - 5초 안에 원하는 문서 찾기
2. **일관성 (Consistency)** - 같은 정보는 단 한 곳에만
3. **확장성 (Scalability)** - 새 문서 추가 시 명확한 위치

**비즈니스 가치:**
- 신규 개발자 온보딩 시간 **50% 단축** (2일 → 1일)
- 전략 수정 시간 **30% 감소** (설계 문서 빠른 참조)
- 트러블슈팅 평균 해결 시간 **40% 단축** (CLAUDE.md 교훈 활용)

---

## 2. 새로운 문서 구조 이해하기

### 2.1 전체 구조 개요

```
Upbit Tradebot MVP 프로젝트/
│
├── 📄 README.md                           # 프로젝트 메인 문서 (필독!)
├── 📄 DOCS_REORGANIZATION_PLAN.md         # 재구성 실행 계획
├── 📄 DOCS_REORGANIZATION_MANUAL.md       # 이 파일!
├── 📄 DOCS_REORGANIZATION_COMPLETED.md    # 재구성 완료 보고서
│
├── 📁 docs/                               # 사용자 문서 (공식 문서)
│   ├── 📄 README.md                       # 문서 마스터 인덱스 ⭐
│   │
│   ├── 📁 setup/                          # 설치 및 배포
│   │   ├── installation.md                # 로컬 설치
│   │   └── deployment.md                  # 서버 배포
│   │
│   ├── 📁 operations/                     # 운영 가이드
│   │   ├── strategy-params.md             # 전략 파라미터 ⭐
│   │   └── monitoring.md                  # 모니터링
│   │
│   ├── 📁 architecture/                   # 시스템 아키텍처
│   │   ├── overview.md                    # 전체 구조 ⭐
│   │   ├── rest-reconcile.md              # REST Reconcile
│   │   └── indicators.md                  # 지표 계산
│   │
│   ├── 📁 analysis/                       # 분석 문서
│   │   └── close-price-analysis.md        # 종가 분석
│   │
│   └── 📁 work-orders/                    # 작업 지시서
│       └── 2026-001-confirmed-candle.md   # WO-2026-001
│
├── 📁 .claude/                            # AI 어시스턴트 전용
│   ├── 📄 README.md                       # Claude Code 가이드
│   └── 📁 context/
│       └── project-rules.md               # 프로젝트 규칙 ⭐
│
├── 📁 thoughts/                           # 기획 및 설계
│   ├── 20260325-01-BACKFILL-Golden-Cross-Fix.md
│   └── 20260326-01-Post-Exit-Reentry-Strategy.md
│
└── 📁 claude-docs/                        # 역사적 아카이브
    └── YYYYMMDD/                          # 날짜별 폴더
```

**⭐ 표시 = 필독 문서**

### 2.2 각 디렉토리의 역할

#### 📁 docs/setup/ - 설치 및 배포

**언제 사용:**
- 로컬에서 봇 실행해야 할 때
- 서버에 배포해야 할 때
- Python 환경 설정할 때

**핵심 문서:**
- **installation.md** - 로컬 설치 (pyupbit, pandas, SQLite)
- **deployment.md** - 서버 배포 (squad-tradebot.sh 스크립트)

**사용 예시:**
```bash
# 상황: "로컬에서 봇을 실행하고 싶어요"
1. docs/setup/installation.md 열기
2. "가상환경 설정" 섹션 따라하기
3. pip install -r requirements.txt 실행
```

#### 📁 docs/operations/ - 운영 가이드

**언제 사용:**
- 전략 파라미터 수정할 때
- 매매 로그 확인할 때
- 봇 성능 모니터링할 때

**핵심 문서:**
- **strategy-params.md** - EMA/MACD 파라미터, 필터 설정
- **monitoring.md** - 로그 파일 위치, 실시간 모니터링

**사용 예시:**
```bash
# 상황: "Trailing Stop 10% → 15%로 변경하고 싶어요"
1. docs/operations/strategy-params.md 열기
2. "Trailing Stop Filter" 섹션 확인
3. JSON 파일 수정 방법 따라하기
```

#### 📁 docs/architecture/ - 시스템 아키텍처

**언제 사용:**
- 봇 전체 구조 이해할 때
- REST Reconcile 시스템 공부할 때
- 지표 계산 로직 확인할 때

**핵심 문서:**
- **overview.md** - 전체 아키텍처 (엔진, 전략, 필터)
- **rest-reconcile.md** - REST API 정합성 검증 시스템
- **indicators.md** - EMA, MACD 증분 계산 로직

**사용 예시:**
```bash
# 상황: "Golden Cross 감지가 어떻게 동작하나요?"
1. docs/architecture/indicators.md 열기
2. "EMA 크로스 감지" 섹션 확인
3. prev_ema_fast, ema_fast 비교 로직 이해
```

#### 📁 docs/analysis/ - 분석 문서

**언제 사용:**
- CTO 분석 보고서 참조할 때
- 특정 이슈 근본 원인 확인할 때

**현재 문서:**
- **close-price-analysis.md** - 종가 미확정 문제 분석

#### 📁 docs/work-orders/ - 작업 지시서

**언제 사용:**
- 과거 작업 지시서(WO) 확인할 때
- 구현 결과 검증할 때

**현재 문서:**
- **2026-001-confirmed-candle.md** - 확정 봉 검증 구현

#### 📁 .claude/ - AI 어시스턴트 전용

**⚠️ 중요: 이 디렉토리는 Git에 커밋되지 않습니다!**

**언제 사용:**
- Claude Code AI와 대화할 때 (자동으로 참조됨)
- 과거 교훈(Issue #1~#11)을 빠르게 확인할 때
- 프로젝트 규칙을 AI에게 알려줄 때

**핵심 문서:**
- **context/project-rules.md** - CLAUDE.md (Issue #1~#11 교훈)

**사용자 vs Claude:**
- 사용자: `docs/` 디렉토리 사용
- Claude Code: `.claude/` 자동 참조 + `docs/` 필요 시 읽기

#### 📁 thoughts/ - 기획 및 설계

**언제 사용:**
- 최신 설계 문서 확인할 때
- 전략 개선 아이디어 검토할 때

**현재 문서:**
- **20260325-01-BACKFILL-Golden-Cross-Fix.md** - BACKFILL 지표 오염 수정
- **20260326-01-Post-Exit-Reentry-Strategy.md** - 매도 후 재진입 전략

#### 📁 claude-docs/ - 역사적 아카이브

**언제 사용:**
- 과거 구현 과정 추적할 때
- 날짜별 작업 이력 확인할 때

**구조:**
- 날짜별 폴더 (20260212, 20260213, ...)
- 각 폴더 내 분석/구현 문서

---

## 3. 문서 검색 및 활용 방법

### 3.1 빠른 검색 전략

#### 전략 1: 마스터 인덱스 활용 (권장)

**시작점:** `docs/README.md`

**사용 방법:**
1. `docs/README.md` 열기
2. "빠른 참조" 표에서 작업 찾기
3. 링크 클릭하여 해당 문서로 이동

#### 전략 2: 카테고리별 탐색

**의사결정 트리:**
```
내 목적이 뭐지?
│
├─ 설치/배포하고 싶다 → docs/setup/
│
├─ 전략 파라미터 수정 → docs/operations/strategy-params.md
│
├─ 시스템 이해하고 싶다
│  ├─ 전체 구조 → docs/architecture/overview.md
│  ├─ REST Reconcile → docs/architecture/rest-reconcile.md
│  └─ 지표 계산 → docs/architecture/indicators.md
│
├─ 과거 분석 보고 싶다 → docs/analysis/
│
└─ 최신 설계 문서 → thoughts/
```

#### 전략 3: 파일명으로 직접 검색

```bash
# VS Code 단축키: Cmd+P (Mac) / Ctrl+P (Windows)
# 검색어 예시:

strategy-params  # → docs/operations/strategy-params.md
rest-reconcile   # → docs/architecture/rest-reconcile.md
close-price      # → docs/analysis/close-price-analysis.md
project-rules    # → .claude/context/project-rules.md
```

### 3.2 상황별 문서 활용 가이드

#### 📊 전략 수정: Trailing Stop 15%로 변경

**Step 1: 파라미터 이해**
1. `docs/operations/strategy-params.md` 열기
2. "Trailing Stop Filter" 섹션 확인

**Step 2: JSON 수정**
```bash
# mcmax33_latest_params_EMA.json 편집
"trailing_stop_threshold": 0.15  # 0.10 → 0.15
```

**Step 3: 검증**
```bash
# 로그 확인
tail -f mcmax33_engine_debug.log | grep TRAILING
```

#### 🔍 학습: REST Reconcile 이해

**단계별 학습:**
1. `docs/architecture/rest-reconcile.md` 읽기
2. "동작 원리" 섹션 이해
3. `thoughts/20260228-01-REST-Reconcile-Plan-Final.md` 참조 (claude-docs에서)

#### 🐛 트러블슈팅: Golden Cross 미감지

**Step 1: 교훈 참조**
1. `.claude/context/project-rules.md` 열기
2. "Issue #11: BACKFILL 지표 오염" 섹션 확인

**Step 2: 설계 문서 확인**
1. `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` 열기
2. "수정 후 동작" 검증

---

## 4. Claude Code와 효과적으로 소통하기

### 4.1 효과적인 질문 방법

#### ❌ 나쁜 질문 예시

**질문 1: 너무 모호함**
```
"봇이 안 돼요"
```
**문제점:**
- 어떤 증상인지 불명확 (매수 안 됨? 에러?)
- Claude가 추측으로 답변 → 시간 낭비

#### ✅ 좋은 질문 예시

**질문 1: 구체적 증상 + 환경**
```
"Golden Cross 발생했는데 매수가 안 됩니다.
로그: 'Golden | NO_SIGNAL'
docs/architecture/indicators.md를 참조해서
원인을 찾아주세요."
```
**좋은 점:**
- ✅ 증상 구체적 (Golden Cross인데 NO_SIGNAL)
- ✅ 로그 제공
- ✅ 참조할 문서 제시

### 4.2 Claude Code에게 문서 참조 요청하기

#### 패턴 1: 특정 문서 먼저 읽게 하기

```
".claude/context/project-rules.md의 Issue #11을 읽고,
현재 BACKFILL 로그에서 지표 상태 백업/복원이 제대로 되는지 확인해줘."
```

#### 패턴 2: 교훈 기반 조언 요청

```
".claude/context/project-rules.md의 Issue #7 (Trailing Stop)을 참고해서,
현재 설정(10%)이 Profit-based인지 Peak-based인지 확인해줘."
```

#### 패턴 3: 다중 문서 참조

```
"다음 순서로 문서를 읽고 Golden Cross 감지 로직을 설명해줘:
1. docs/architecture/indicators.md (EMA 계산)
2. .claude/context/project-rules.md (Issue #11)
3. thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md"
```

---

## 5. 문서 작성 및 업데이트 가이드라인

### 5.1 새 문서 작성 시 규칙

#### 규칙 1: 적절한 카테고리 선택

**의사결정 트리:**
```
이 문서는 무엇에 관한 것인가?

├─ 설치/배포 절차 → docs/setup/
│
├─ 운영 중 참조 가이드 → docs/operations/
│
├─ 시스템 아키텍처 → docs/architecture/
│
├─ 분석 보고서 → docs/analysis/
│
├─ 작업 지시서 → docs/work-orders/
│
├─ 설계 문서 → thoughts/
│
└─ AI 컨텍스트 → .claude/
```

#### 규칙 2: 파일명 규칙

**일반 문서:**
```
kebab-case 사용 (소문자 + 하이픈)

✅ 좋은 예:
- strategy-params.md
- rest-reconcile.md
- monitoring.md

❌ 나쁜 예:
- StrategyParams.md (CamelCase)
- strategy_params.md (snake_case)
```

**설계 문서 (thoughts/):**
```
날짜 + 순번 + 주제 형식

형식: YYYYMMDD-NN-{주제}.md

✅ 좋은 예:
- 20260325-01-BACKFILL-Golden-Cross-Fix.md
- 20260326-01-Post-Exit-Reentry-Strategy.md
```

### 5.2 기존 문서 업데이트 시 규칙

#### 규칙 1: 최종 업데이트 일자 기록

**파일 하단에 추가:**
```markdown
---
**작성일**: 2026-03-25
**최종 업데이트**: 2026-04-05
**변경 내역**: Trailing Stop 계산 방식 Profit-based로 수정
```

---

## 6. 자주 묻는 질문 (FAQ)

### Q1. "CLAUDE.md 파일이 없어졌어요!"

**A:** 재구성 과정에서 이동했습니다.

**변경 사항:**
```
CLAUDE.md → .claude/context/project-rules.md
```

**찾는 방법:**
```bash
# VS Code 검색: Cmd+P
project-rules

# 또는 직접 경로
.claude/context/project-rules.md
```

### Q2. "문서가 어디 있는지 모르겠어요"

**A:** 필독 문서 3개만 읽으세요 (⭐ 표시):

**필수 3종 세트:**
1. `README.md` (5분) - 프로젝트 전체 개요
2. `docs/operations/strategy-params.md` (10분) - 전략 설정
3. `.claude/context/project-rules.md` (30분) - 11가지 핵심 교훈

**총 시간: 45분**

### Q3. "Claude Code가 엉뚱한 대답을 해요"

**A:** 다음을 확인하세요:

**체크리스트:**
- [ ] 구체적인 문서를 명시했나요?
- [ ] 증상을 구체적으로 설명했나요?
- [ ] 로그를 제공했나요?

**개선 예:**
```
Before (모호):
"Golden Cross가 안 돼요"

After (구체적):
"Golden Cross 발생했는데 매수 신호가 안 나옵니다.
로그: 'Golden | NO_SIGNAL'
.claude/context/project-rules.md Issue #11을 참조해서
원인을 찾아주세요."
```

---

## 7. 베스트 프랙티스

### 7.1 문서 검색 효율화

**습관 1: 항상 docs/README.md부터**
```
검색 시작 → docs/README.md → 빠른 참조 표 → 링크 클릭
```

**시간 절약:**
- Before: 3분 (여러 파일 열어보기)
- After: 10초 (인덱스 → 바로 이동)

**습관 2: VS Code 단축키 활용**
```
Cmd+P (Mac) / Ctrl+P (Windows)
→ 파일명 일부만 입력
→ 자동 완성
```

### 7.2 Claude Code 협업 효율화

**패턴 1: 컨텍스트 먼저 제공**
```
❌ 비효율:
"Golden Cross 감지 원리 설명해줘"
→ Claude: "어떤 문서를...?"
(2번 왕복)

✅ 효율:
"docs/architecture/indicators.md를 읽고
Golden Cross 감지 원리를 설명해줘."
(1번 요청으로 완료)
```

### 7.3 문서 유지보수 습관

**주간 점검 (5분)**
```bash
# 새로운 .md 파일이 적절한 위치에 있는지 확인
find . -name "*.md" -type f | grep -v ".git" | grep -v "claude-docs"
```

---

## 🎓 마무리: 3가지 핵심 원칙

### 원칙 1: 인덱스부터 시작하라
```
docs/README.md → 빠른 참조 표 → 원하는 문서
```

### 원칙 2: Claude에게 명확하게 요청하라
```
"[문서]를 읽고, [상황]을 [방법]으로 해결해줘"
```

### 원칙 3: 역사적 아카이브를 보존하라
```
claude-docs/: 과거 구현 과정 (보존)
thoughts/: 최신 설계 문서 (활용)
```

---

## 📚 다음 단계

**이 매뉴얼을 읽은 후:**

1. **즉시 실천 (5분)**
   - `docs/README.md` 생성하기
   - VS Code에서 Cmd+P 단축키 연습

2. **오늘 안에 (45분)**
   - 필독 문서 3개 읽기
   - Claude Code에게 간단한 질문 해보기

3. **이번 주 안에 (2시간)**
   - 전략 파라미터 수정 실습
   - REST Reconcile 시스템 이해

---

**작성일**: 2026-04-05
**작성자**: Claude Code AI Assistant
**버전**: 1.0
**대상**: Upbit Tradebot MVP 프로젝트 전체 팀원
**최종 업데이트**: 2026-04-05
