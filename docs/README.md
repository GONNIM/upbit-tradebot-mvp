# Upbit Tradebot MVP - 문서 인덱스

> **모든 프로젝트 문서의 중앙 허브**

---

## 📖 빠른 참조

| 작업 | 문서 | 소요 시간 |
|------|------|----------|
| 로컬에서 봇 실행 | [설치 가이드](setup/installation.md) | 10분 |
| 서버에 배포 | [배포 가이드](setup/deployment.md) | 15분 |
| 전략 파라미터 수정 | [전략 파라미터](operations/strategy-params.md) ⭐ | 5분 |
| 시스템 구조 이해 | [전체 구조](architecture/overview.md) ⭐ | 15분 |
| REST Reconcile 이해 | [REST Reconcile](architecture/rest-reconcile.md) | 20분 |
| EMA/MACD 계산 이해 | [지표 계산](architecture/indicators.md) | 15분 |
| 로그 확인 | [모니터링](operations/monitoring.md) | 5분 |
| 종가 문제 분석 | [종가 분석](analysis/close-price-analysis.md) | 10분 |
| WO-2026-001 확인 | [확정 봉 검증](work-orders/2026-001-confirmed-candle.md) | 15분 |

**⭐ = 필독 문서**

---

## 🗂️ 카테고리별 문서

### 📁 setup/ - 설치 및 배포

**목적**: 프로젝트 설치 및 배포 절차

| 문서 | 설명 | 상태 |
|------|------|------|
| [installation.md](setup/installation.md) | 로컬 설치 가이드 (Python, 패키지, 환경 변수) | 📝 작성 예정 |
| [deployment.md](setup/deployment.md) | 서버 배포 가이드 (squad-tradebot.sh) | 📝 작성 예정 |

**언제 사용**:
- 처음 프로젝트를 설치할 때
- 서버에 봇을 배포할 때
- 환경 설정을 변경할 때

---

### 📁 operations/ - 운영 가이드

**목적**: 봇 운영 중 참조하는 실무 가이드

| 문서 | 설명 | 상태 |
|------|------|------|
| [strategy-params.md](operations/strategy-params.md) ⭐ | 전략 파라미터 설정 (EMA, MACD, 필터) | 📝 작성 예정 |
| [monitoring.md](operations/monitoring.md) | 로그 확인 및 성능 모니터링 | 📝 작성 예정 |

**언제 사용**:
- Trailing Stop 비율 변경할 때 → `strategy-params.md`
- Take Profit 목표 수정할 때 → `strategy-params.md`
- 로그 파일 위치 찾을 때 → `monitoring.md`
- 매매 기록 확인할 때 → `monitoring.md`

**예시**:
```bash
# Trailing Stop 10% → 15%로 변경
# 1. strategy-params.md 열기
# 2. "Trailing Stop Filter" 섹션 확인
# 3. mcmax33_latest_params_EMA.json 수정
{
  "trailing_stop_threshold": 0.15  // 0.10 → 0.15
}
```

---

### 📁 architecture/ - 시스템 아키텍처

**목적**: 시스템 내부 구조 및 핵심 로직 이해

| 문서 | 설명 | 상태 |
|------|------|------|
| [overview.md](architecture/overview.md) ⭐ | 전체 아키텍처 (엔진, 전략, 필터) | 📝 작성 예정 |
| [rest-reconcile.md](architecture/rest-reconcile.md) | REST API 정합성 검증 시스템 | 📝 작성 예정 |
| [indicators.md](architecture/indicators.md) | EMA/MACD 증분 계산 로직 | 📝 작성 예정 |

**언제 사용**:
- Golden Cross 감지 원리 이해할 때 → `indicators.md`
- BACKFILL 동작 방식 이해할 때 → `rest-reconcile.md`
- 필터 시스템 구조 파악할 때 → `overview.md`
- 코드 수정 전 설계 이해할 때

**핵심 개념**:
- **REST Reconcile**: 매 분봉마다 REST API와 로컬 데이터 비교, 변경 감지 시 BACKFILL
- **증분 계산**: 전체 재계산 없이 이전 값 + 현재 값으로 지표 업데이트
- **크로스 감지**: `prev` 값 추적으로 Golden/Dead Cross 정확히 포착

---

### 📁 analysis/ - 분석 문서

**목적**: 특정 이슈 분석 보고서

| 문서 | 설명 | 상태 |
|------|------|------|
| [close-price-analysis.md](analysis/close-price-analysis.md) | 종가 미확정 문제 분석 (CTO) | ✅ 완료 |

**언제 사용**:
- DB 종가와 Upbit 차트 종가 불일치 조사할 때
- REST API 미확정 종가 문제 이해할 때
- 봉 검증 로직 개선할 때

**핵심 내용**:
- Upbit REST API는 봉 확정 후에도 ~1분간 미확정 데이터 반환
- `fetch_confirmed_candle` 함수로 Progressive Retry 구현
- 봉 일관성 검증 추가 (`open[n] ≈ close[n-1]`)

---

### 📁 work-orders/ - 작업 지시서

**목적**: 과거 작업 지시서(WO) 및 구현 보고서

| 문서 | 설명 | 상태 |
|------|------|------|
| [2026-001-confirmed-candle.md](work-orders/2026-001-confirmed-candle.md) | WO-2026-001: 확정 봉 검증 구현 | ✅ 완료 |

**언제 사용**:
- 과거 작업 지시서 확인할 때
- 구현 결과 검증할 때
- 유사한 작업 계획 수립 시 참고할 때

**WO-2026-001 핵심**:
- Task 1-A: 최신 봉 확정 검증 (`fetch_confirmed_candle`)
- Task 1-B: 과거 봉 Upbit 차트 일치 검증 (200일선 기준)
- Task 2: 봉 일관성 검증 (`CandleValidator`)

---

## 🎯 상황별 문서 찾기

### 🚀 처음 시작하는 경우

**읽는 순서**:
1. [프로젝트 README](../README.md) (5분) - 전체 개요
2. [설치 가이드](setup/installation.md) (10분) - 환경 설정
3. [전체 구조](architecture/overview.md) (15분) - 시스템 이해
4. [전략 파라미터](operations/strategy-params.md) (5분) - 파라미터 이해

**총 소요 시간**: 35분

### 📊 전략 수정하는 경우

**시나리오**: Trailing Stop 10% → 15%로 변경

1. [strategy-params.md](operations/strategy-params.md) 열기
2. "Trailing Stop Filter" 섹션 확인
3. JSON 파일 수정 (`mcmax33_latest_params_EMA.json`)
4. 봇 재시작 후 로그 확인 ([monitoring.md](operations/monitoring.md))

### 🐛 트러블슈팅하는 경우

**증상**: Golden Cross 발생했는데 매수 안 됨

1. [프로젝트 규칙](../.claude/context/project-rules.md) Issue #11 확인
2. [indicators.md](architecture/indicators.md)에서 크로스 감지 로직 이해
3. [BACKFILL 설계 문서](../thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md) 참조

**증상**: DB 종가와 Upbit 차트 불일치

1. [close-price-analysis.md](analysis/close-price-analysis.md) 읽기
2. [rest-reconcile.md](architecture/rest-reconcile.md)에서 검증 로직 확인
3. [WO-2026-001](work-orders/2026-001-confirmed-candle.md)에서 구현 결과 확인

### 🔍 시스템 이해하는 경우

**목표**: REST Reconcile 시스템 완전 이해

**읽는 순서**:
1. [rest-reconcile.md](architecture/rest-reconcile.md) (20분) - 동작 원리
2. [close-price-analysis.md](analysis/close-price-analysis.md) (10분) - 배경 이해
3. [WO-2026-001](work-orders/2026-001-confirmed-candle.md) (15분) - 구현 상세
4. [역사적 문서](../claude-docs/20260228/) - 초기 설계 과정

**총 소요 시간**: 45분

---

## 🔗 관련 디렉토리

### 📁 thoughts/ - 설계 문서

**위치**: `../thoughts/`

**현재 문서**:
- [20260325-01-BACKFILL-Golden-Cross-Fix.md](../thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md)
  - BACKFILL 지표 오염 수정 (Issue #11)
  - 지표 상태 백업/복원 패턴

- [20260326-01-Post-Exit-Reentry-Strategy.md](../thoughts/20260326-01-Post-Exit-Reentry-Strategy.md)
  - 매도 후 재진입 전략 설계
  - Cooldown 필터 개선

**언제 사용**:
- 최신 설계 문서 확인할 때
- 전략 개선 아이디어 검토할 때

### 📁 claude-docs/ - 역사적 아카이브

**위치**: `../claude-docs/`

**구조**: 날짜별 폴더 (20260212, 20260213, ...)

**언제 사용**:
- 과거 구현 과정 추적할 때
- 초기 설계 의도 확인할 때
- 날짜별 작업 이력 검토할 때

**주요 폴더**:
- `20260228/` - REST Reconcile 초기 계획
- `20260304/` - Critical Issues 수정
- `20260314/` - EMA 계산 분석, Trailing Stop 수정

### 📁 .claude/ - AI 어시스턴트 전용

**위치**: `../.claude/`

**⚠️ Git 추적 안 됨 (.gitignore)**

**문서**:
- [README.md](../.claude/README.md) - Claude Code 사용 가이드
- [context/project-rules.md](../.claude/context/project-rules.md) ⭐ - Issue #1~#11 교훈

**언제 사용**:
- Claude Code AI와 대화할 때 (자동 참조)
- 과거 트러블슈팅 교훈 확인할 때

---

## 📝 문서 작성 가이드

### 새 문서 추가 시

**카테고리 선택**:
```
설치/배포 절차 → docs/setup/
운영 중 참조 → docs/operations/
시스템 아키텍처 → docs/architecture/
분석 보고서 → docs/analysis/
작업 지시서 → docs/work-orders/
설계 문서 → thoughts/
```

**파일명 규칙**:
- kebab-case 사용 (예: `strategy-params.md`)
- 날짜 포함 시: `YYYY-MM-DD-description.md`

**문서 템플릿**:
```markdown
# 문서 제목

## 📋 개요
- 목적
- 대상 독자

## 본문

## 참고 문서
- [관련 문서](경로)

---
**작성일**: YYYY-MM-DD
**작성자**: 이름
```

### 기존 문서 업데이트 시

**하단에 변경 이력 추가**:
```markdown
---
**최종 업데이트**: 2026-04-05
**변경 내역**: Trailing Stop 계산 방식 수정
```

---

## 🎓 필독 문서 3종 세트

처음 프로젝트를 접하는 경우, 다음 3개 문서만 읽으면 충분합니다:

1. **[프로젝트 README](../README.md)** (5분)
   - 전체 개요, 빠른 시작, 주요 기능

2. **[전략 파라미터](operations/strategy-params.md)** (5분)
   - 실제 매매에 영향을 주는 파라미터 이해

3. **[프로젝트 규칙](../.claude/context/project-rules.md)** (30분)
   - Issue #1~#11 교훈 학습
   - 과거 실수 재발 방지

**총 소요 시간**: 40분

---

## 📞 문의

**문서 개선 제안**:
- GitHub Issue 등록
- 팀 회의에서 논의

**긴급 문의**:
- [.claude/context/project-rules.md](../.claude/context/project-rules.md) 먼저 확인

---

**작성일**: 2026-04-05
**작성자**: Claude Code (AI Assistant)
**최종 업데이트**: 2026-04-05
**관련 문서**: [DOCS_REORGANIZATION_MANUAL.md](../DOCS_REORGANIZATION_MANUAL.md)
