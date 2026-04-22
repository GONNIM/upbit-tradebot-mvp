# Tradebot 프로젝트 Boilerplate 적용 계획서

**프로젝트**: Upbit Tradebot MVP
**작성일**: 2026-04-21
**작성자**: CTO Assistant (Claude Code)
**목적**: FoodBid Boilerplate를 Tradebot에 적용하여 Claude Code 작업 효율 향상

---

## 📋 목차

1. [프로젝트 현황 분석](#1-프로젝트-현황-분석)
2. [문제점 및 개선 필요성](#2-문제점-및-개선-필요성)
3. [실행 계획 (5단계)](#3-실행-계획-5단계)
4. [예상 효과](#4-예상-효과)
5. [안전장치 및 Rollback](#5-안전장치-및-rollback)
6. [체크리스트](#6-체크리스트)

---

## 1. 프로젝트 현황 분석

### 1-1. 프로젝트 개요

**Upbit Tradebot MVP**
- **도메인**: 암호화폐 자동매매 봇
- **핵심 기능**: EMA/MACD 전략 기반 매매, REST Reconcile, 증분 지표 계산
- **기술 스택**: Python 3.9+, pyupbit, Streamlit, SQLite, systemd

### 1-2. 현재 문서 상태

| 파일 | 크기/줄 수 | 상태 | 문제점 |
|------|-----------|------|--------|
| **CLAUDE.md** | **1,797줄 (56KB)** | 🔴 Critical | Anthropic 권장 200줄의 **9배 초과** |
| **.claude/context/project-rules.md** | 56KB | 🟡 Warning | CLAUDE.md와 **100% 중복** |
| **.claude/lessons-learned.md** | 21KB | ✅ 적정 | 교훈 인덱스 (Issue #1~#11) |
| **docs/** | 3개 파일 | 🟢 Info | 대부분 폴더 비어있음 (확장 가능) |

### 1-3. CLAUDE.md 구조 분석

```
CLAUDE.md (1,797줄)
├── 목적 (9줄, 0.5%)
├── Critical Issues #1~#11 (1,414줄, 79%) ← 대부분 여기
├── High-Risk Issues (43줄, 2.4%)
├── 체계적 교훈 (153줄, 8.5%)
├── 핵심 원칙 (63줄, 3.5%)
├── 통계 (51줄, 2.8%)
├── 향후 개선 사항 (33줄, 1.8%)
└── 결론 (19줄, 1.1%)
```

**핵심 문제**: Issue 상세 설명이 79% 차지 → WHY/WHAT/HOW 구조 아님

### 1-4. Issue 목록

- Issue #1: pyupbit 컬럼명 대소문자
- Issue #2: bar_time 9시간 오프셋
- Issue #4: REST API 지연
- Issue #5: EMA 증분 업데이트 누락
- Issue #6: 정체 포지션 필터
- Issue #7: Trailing Stop (Peak-based → Profit-based)
- Issue #8: REST API 미확정 종가 ⭐
- Issue #9: BACKFILL 봉 중복 체크
- Issue #10: Enum 속성 접근 오류
- Issue #11: BACKFILL Golden Cross 미감지 ⭐

---

## 2. 문제점 및 개선 필요성

### 2-1. 발견한 문제점

#### 🔴 Critical 문제

1. **CLAUDE.md가 Anthropic 권장을 9배 초과**
   - 권장: 200줄 이하
   - 현재: 1,797줄
   - 경고: "Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"

2. **Issue 기반 구조 (WHY/WHAT/HOW 아님)**
   - 현재: 트러블슈팅 문서 (Issue #1~#11 나열)
   - 권장: 목적/구조/명령어 중심

3. **CLAUDE.md와 project-rules.md 100% 중복**
   - 동일 내용이 2곳에 존재
   - 역할 분리 필요

#### 🟡 Warning 문제

4. **핵심 지침이 묻힐 가능성**
   - 1,797줄의 상세 내용 속에 명령어/규칙 분산
   - Claude가 중요한 지침을 무시할 수 있음

5. **Tradebot 특화 내용 부족**
   - REST Reconcile (핵심 기능) 설명 부족
   - 전략 파라미터 (EMA, MACD) 강조 필요
   - Golden/Dead Cross 감지 로직 명확화 필요

### 2-2. 개선 필요성

| 이유 | 근거 | 출처 |
|------|------|------|
| **Anthropic 권장 준수** | 200줄 이하 유지 | CLAUDE-HOW-TO.md |
| **Claude 작업 효율 향상** | ⚠️ CRITICAL 섹션 추가 | FoodBid 교훈 #19 |
| **문서 중복 해소** | 역할 분리 (CLAUDE.md vs project-rules.md) | 문서 계층 구조 |
| **Tradebot 특화** | 도메인 특성 반영 (트레이딩 전략) | - |

---

## 3. 실행 계획 (5단계)

### 📌 전제 조건

- **사용자 승인 후 진행** (FoodBid 교훈 #8, #20)
- **각 주요 단계마다 승인 대기** (5개 승인 지점)
- **Rollback 준비 완료** (.backup/ 디렉토리)

---

### Phase 1: 백업 및 준비 (5분)

#### 작업 내용

```bash
cd /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp

# 1-1. 백업 디렉토리 생성
mkdir -p .backup/$(date +%Y%m%d)

# 1-2. 현재 문서 백업
cp CLAUDE.md .backup/$(date +%Y%m%d)/CLAUDE.md.backup
cp .claude/context/project-rules.md .backup/$(date +%Y%m%d)/project-rules.md.backup
cp .claude/lessons-learned.md .backup/$(date +%Y%m%d)/lessons-learned.md.backup

# 1-3. FoodBid 가이드 복사
cp /Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md ./

# 1-4. .gitignore 업데이트
echo ".backup/" >> .gitignore
```

#### 체크리스트

- [ ] .backup/$(date +%Y%m%d)/ 디렉토리 생성 확인
- [ ] 3개 파일 백업 완료 (CLAUDE.md, project-rules.md, lessons-learned.md)
- [ ] CLAUDE-HOW-TO.md 복사 완료
- [ ] .gitignore에 .backup/ 추가 확인

#### 🚦 사용자 승인 대기 지점 #1

---

### Phase 2: 새로운 CLAUDE.md 작성 (30분)

#### 목표

- **길이**: 150줄 이하 (현재 1,797줄 → 92% 축소)
- **구조**: WHY/WHAT/HOW
- **추가**: ⚠️ CRITICAL 섹션 (FoodBid 철학)

#### 핵심 내용

##### 1. ⚠️ CRITICAL 섹션 (FoodBid 철학)

```markdown
## ⚠️ CRITICAL: Claude Code 작업 수행 원칙

### 🚫 절대 금지
1. 광범위한 와일드카드 검색 금지 (❌ **/*.md)
2. 병렬 도구 호출 금지 (❌ Glob + Grep + Read 동시)
3. 대용량 파일 무분별 읽기 금지 (✅ offset/limit 사용)

### ✅ 필수 준수
- 작업 시작 전: TodoWrite로 계획 (≤4 items)
- 지연 발생 시: 즉시 보고 + 병목 명시
- 검색 시: 가장 가능성 높은 위치부터
```

##### 2. WHY (목적)

```markdown
## WHY (목적)

**Upbit API를 활용한 자동매매 봇**으로, EMA/MACD 지표 기반 체계적인 매매 전략을 실행합니다.

**핵심 가치:**
- ✅ REST Reconcile - 데이터 정합성 보장 (미확정 종가 문제 해결)
- ✅ 증분 지표 계산 - EMA, MACD 실시간 업데이트
- ✅ Golden/Dead Cross 감지 - 빠른 추세 전환 포착
- ✅ 다층 필터 시스템 - Take Profit, Trailing Stop 등

**지원 전략:**
- EMA Strategy - 빠른 EMA(7)와 느린 EMA(25)의 크로스 기반
- MACD Strategy - MACD 라인과 Signal 라인의 크로스 기반
```

##### 3. WHAT (구조)

```markdown
## WHAT (구조)

```
upbit-tradebot-mvp/
├── core/                   # 핵심 엔진
│   ├── strategy_engine.py      # 전략 엔진 (메인)
│   ├── rest_reconcile.py       # REST 정합성 검증 ⭐
│   └── filters/                # 매수/매도 필터
├── engine/                 # 실행 엔진
│   └── live_loop.py            # 메인 루프 (WebSocket + REST)
├── services/               # 외부 서비스
└── docs/                   # 문서
```
```

##### 4. HOW (작업 방법)

```markdown
## HOW (작업 방법)

### 로컬 개발
```bash
pip install -r requirements.txt
python -m engine.live_loop --ticker KRW-ZRO --strategy EMA
```

### 전략 파라미터 수정
```bash
# mcmax33_latest_params_EMA.json
{
  "ema_fast": 7,
  "ema_slow": 25,
  "take_profit": 0.05,
  "trailing_stop_threshold": 0.10
}
```

### 배포
```bash
./deploy.sh  # systemd 재시작 + 로그 확인
```
```

##### 5. 금지 사항 및 특이사항

```markdown
## ❌ 금지 사항

- ❌ Issue #1: pyupbit 컬럼명 대소문자 혼동
- ❌ Issue #2: bar_time timezone 직접 변경
- ❌ Issue #9: BACKFILL 중복 체크로 차단
- ❌ Issue #11: BACKFILL이 prev 값 덮어쓰기

## 🚨 프로젝트 특이사항

### REST Reconcile 시스템 (핵심!)
**문제**: Upbit REST API가 미확정 종가 반환
**해결**: Progressive Retry로 확정 봉 검증

### Golden/Dead Cross 감지
**주의**: BACKFILL이 prev 값을 오염시키지 않도록 백업/복원
```

##### 6. Import 문법

```markdown
## 📚 상세 문서

**Tier 1** (자동 로드):
- @CLAUDE.md - 프로젝트 개요
- @.claude/context/project-rules.md - 핵심 교훈 (Issue #1~#11)
- @.claude/lessons-learned.md - 교훈 인덱스

**Tier 2** (필요 시 참조):
- @docs/architecture/ - 시스템 아키텍처 상세
- @docs/analysis/close-price-analysis.md - 종가 분석
- @.backup/$(date)/CLAUDE.md.backup - Issue 전체 상세
```

#### 체크리스트

- [ ] WHY/WHAT/HOW 구조 완성
- [ ] ⚠️ CRITICAL 섹션 추가
- [ ] 빌드/테스트/배포 명령어 포함
- [ ] Tradebot 특이사항 명시 (REST Reconcile, Golden Cross)
- [ ] Issue #1, #2, #8, #9, #11 요약 포함
- [ ] Import 문법으로 상세 문서 참조
- [ ] 150줄 이하 확인 (`wc -l CLAUDE.md`)

#### 🚦 사용자 승인 대기 지점 #2

---

### Phase 3: project-rules.md 재구성 (20분)

#### 목표

- **역할 분리**: CLAUDE.md와 중복 해소
- **길이**: 300줄 이하
- **내용**: 긴급 대응 + Issue 요약 (표 형식)

#### 새로운 역할 정의

| 파일 | 역할 | 길이 |
|------|------|------|
| **CLAUDE.md** | 프로젝트 개요 + 명령어 | 150줄 |
| **project-rules.md** | 긴급 대응 + 핵심 교훈 요약 | 300줄 |
| **lessons-learned.md** | 교훈 인덱스 (기존 유지) | 21KB |

#### 핵심 내용

##### 1. 긴급 상황 대응 우선순위

```markdown
## 🚨 긴급 상황 대응 우선순위 (3단계)

### 1. 프로세스 상태 확인 (최우선)
```bash
systemctl status tradebot
ps aux | grep streamlit
```

### 2. 로그 확인
```bash
tail -f mcmax33_engine_debug.log | grep "ERROR\|EXCEPTION"
```

### 3. REST Reconcile 상태 확인
```bash
tail -f mcmax33_engine_debug.log | grep "BACKFILL\|RECONCILE"
```
```

##### 2. Issue 요약 (표 형식)

```markdown
## 📚 핵심 교훈 인덱스 (11개)

| # | 교훈 | 핵심 메시지 | 날짜 |
|---|------|------------|------|
| 1 | pyupbit 컬럼명 | 외부 API는 가정하지 말고 검증하라 | 2026-03-03 |
| 2 | bar_time 오프셋 | replace(tzinfo=...) 금지 → astimezone() | 2026-03-03 |
| 8 | REST API 미확정 종가 | Progressive Retry로 확정 봉 검증 | 2026-03-14 |
| 11 | BACKFILL 지표 오염 | prev 값 백업/복원 (Golden Cross) | 2026-03-25 |

**상세**: @.claude/lessons-learned.md
```

#### 체크리스트

- [ ] CLAUDE.md와 역할 분리 완료
- [ ] 긴급 상황 대응 우선순위 추가
- [ ] Issue #1~#11 요약 (표 형식)
- [ ] 300줄 이하 확인 (`wc -l .claude/context/project-rules.md`)

#### 🚦 사용자 승인 대기 지점 #3

---

### Phase 4: Import 추가 및 검증 (15분)

#### 4-1. 줄 수 검증

```bash
wc -l CLAUDE.md
# 목표: 200줄 이하

wc -l .claude/context/project-rules.md
# 목표: 300줄 이하
```

#### 4-2. Claude 테스트 (실제 사용 사례)

| # | 테스트 시나리오 | 예상 답변 |
|---|----------------|----------|
| 1 | "Golden Cross가 발생했는데 매수가 안 됩니다." | Issue #11 참조, BACKFILL 지표 오염, prev 값 백업/복원 확인 |
| 2 | "REST API 종가가 Upbit 차트와 다릅니다." | Issue #8, 미확정 종가 문제, Progressive Retry |
| 3 | "서버에 배포하려고 합니다." | `./deploy.sh` 실행, 6단계 자동화 |
| 4 | "pyupbit KeyError가 발생합니다." | Issue #1, 컬럼명 대소문자 (Open → open) |

#### 체크리스트

- [ ] 4개 시나리오 모두 정확한 답변
- [ ] CLAUDE.md 기반 답변 (토큰 낭비 없음)
- [ ] Import 문법 작동 확인 (@docs/...)
- [ ] 불필요한 파일 읽기 없음

#### 🚦 사용자 승인 대기 지점 #4

---

### Phase 5: Git 커밋 (10분)

#### 커밋 메시지

```bash
git add CLAUDE.md
git add CLAUDE-HOW-TO.md
git add .claude/context/project-rules.md
git add .gitignore

git commit -m "docs: CLAUDE.md 재구성 (Anthropic Best Practices 적용)

- 1,797줄 → 150줄 (92% 축소)
- WHY/WHAT/HOW 구조로 재구성
- ⚠️ CRITICAL 섹션 추가 (작업 효율 향상)
- project-rules.md 역할 분리 (CLAUDE.md와 중복 해소)
- 문서 계층 구조 정리 (Tier 1/2 분리)
- 기존 내용: .backup/$(date +%Y%m%d)/ 백업

참조:
- CLAUDE-HOW-TO.md (Anthropic 공식 가이드)
- FoodBid MVP boilerplate 적용
- docs/templates/external-projects/tradebot-boilerplate-application.md

Issue #1~#11 상세 내용은 .backup/에 보존"
```

#### 체크리스트

- [ ] 커밋 메시지 명확
- [ ] 변경 사항 설명 포함
- [ ] 백업 위치 명시
- [ ] 참조 문서 링크 포함

#### 🚦 사용자 승인 대기 지점 #5 (최종 확인)

---

## 4. 예상 효과

### 4-1. 정량적 효과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| **CLAUDE.md 길이** | 1,797줄 | **150줄** | 92% 축소 |
| **project-rules.md** | 56KB (중복) | **300줄 (역할 분리)** | - |
| **Anthropic 권장** | ❌ (9배 초과) | **✅ 준수** | - |
| **토큰 사용량** | 높음 (56KB × 2) | **낮음 (150줄)** | ~80% 감소 |

### 4-2. 정성적 효과

| 항목 | Before | After |
|------|--------|-------|
| **핵심 지침 가시성** | 낮음 (1,414줄 속에 묻힘) | **높음 (⚠️ CRITICAL 최상단)** |
| **Claude 작업 효율** | 중간 (긴 문서 파싱) | **높음 (150줄 즉시 파악)** |
| **문서 탐색 속도** | 느림 (1,797줄 검색) | **빠름 (Tier 1/2 분리)** |
| **Tradebot 특화** | 부족 | **강화 (REST Reconcile, Golden Cross)** |

### 4-3. 근거

| 효과 | 근거 | 출처 |
|------|------|------|
| **Claude가 지침을 더 잘 따름** | "Bloated CLAUDE.md files cause Claude to ignore instructions" | CLAUDE-HOW-TO.md:70 |
| **토큰 낭비 감소** | 모든 대화에 시스템 프롬프트로 포함됨 | CLAUDE-HOW-TO.md:68 |
| **작업 효율 향상** | ⚠️ CRITICAL 섹션으로 금지 사항 명확화 | FoodBid 교훈 #19 |

---

## 5. 안전장치 및 Rollback

### 5-1. 백업 전략

```bash
.backup/$(date +%Y%m%d)/
├── CLAUDE.md.backup (1,797줄)
├── project-rules.md.backup (56KB)
└── lessons-learned.md.backup (21KB)
```

**보존 기간**: 영구 (Git 추적 안 함, .gitignore 등록)

### 5-2. Rollback 절차

#### 상황 1: 새로운 CLAUDE.md가 작동하지 않음

```bash
# Step 1: 백업에서 복원
cp .backup/$(date +%Y%m%d)/CLAUDE.md.backup CLAUDE.md
cp .backup/$(date +%Y%m%d)/project-rules.md.backup .claude/context/project-rules.md

# Step 2: Git 되돌리기 (커밋 후)
git reset --soft HEAD~1  # 커밋만 취소 (파일 유지)
# 또는
git reset --hard HEAD~1  # 커밋 + 파일 모두 취소

# Step 3: 사용자에게 보고
echo "✅ Rollback 완료. 기존 버전으로 복원되었습니다."
```

#### 상황 2: Claude 테스트 실패 (Phase 4)

```bash
# Git 커밋 전이므로 파일만 복원
cp .backup/$(date +%Y%m%d)/CLAUDE.md.backup CLAUDE.md
cp .backup/$(date +%Y%m%d)/project-rules.md.backup .claude/context/project-rules.md

# 문제 분석 후 재작성
```

### 5-3. 검증 체크리스트 (Rollback 판단 기준)

- [ ] Claude가 4개 테스트 시나리오에 정확히 답변
- [ ] Import 문법 작동 (@docs/...)
- [ ] 불필요한 파일 읽기 없음 (토큰 낭비)
- [ ] 사용자가 CLAUDE.md 길이에 만족 (150줄)

**판단**: 위 4개 중 2개 이상 실패 시 Rollback 권장

---

## 6. 체크리스트

### 6-1. 실행 전 체크리스트

- [ ] FoodBid boilerplate 이해 완료
- [ ] Tradebot 현황 분석 완료
- [ ] 사용자 승인 획득
- [ ] 작업 시간 확보 (80분)

### 6-2. 각 Phase 체크리스트

#### Phase 1: 백업 및 준비
- [ ] .backup/ 디렉토리 생성
- [ ] 3개 파일 백업 완료
- [ ] CLAUDE-HOW-TO.md 복사
- [ ] .gitignore 업데이트
- [ ] 🚦 **사용자 승인 #1**

#### Phase 2: 새로운 CLAUDE.md
- [ ] WHY/WHAT/HOW 구조
- [ ] ⚠️ CRITICAL 섹션
- [ ] 명령어 포함
- [ ] Tradebot 특이사항
- [ ] 150줄 이하
- [ ] 🚦 **사용자 승인 #2**

#### Phase 3: project-rules.md
- [ ] 역할 분리 완료
- [ ] 긴급 대응 우선순위
- [ ] Issue 요약 (표)
- [ ] 300줄 이하
- [ ] 🚦 **사용자 승인 #3**

#### Phase 4: 검증
- [ ] 줄 수 확인
- [ ] 4개 시나리오 테스트
- [ ] Import 작동 확인
- [ ] 🚦 **사용자 승인 #4**

#### Phase 5: Git 커밋
- [ ] 변경 사항 확인
- [ ] 커밋 메시지 작성
- [ ] 🚦 **사용자 승인 #5**

### 6-3. 완료 후 체크리스트

- [ ] Git 커밋 완료
- [ ] 백업 유지 확인
- [ ] 문서 인덱스 업데이트
- [ ] Tradebot README.md 업데이트 (참조 링크)
- [ ] FoodBid 문서 인덱스 업데이트 (이 문서)

---

## 7. 참고 자료

### 7-1. FoodBid 관련 문서

- **Boilerplate 가이드**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/CLAUDE-HOW-TO.md`
- **프로젝트 규칙**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/.claude/context/project-rules.md`
- **교훈 인덱스**: `/Users/gonnim/Project-THETAK/MVP/foodbid-mvp/.claude/lessons-learned.md`

### 7-2. Anthropic 공식

- **Best Practices**: https://code.claude.com/docs/en/best-practices
- **Using CLAUDE.md Files**: https://claude.com/blog/using-claude-md-files

### 7-3. Tradebot 기존 문서

- **현재 CLAUDE.md**: `.backup/$(date +%Y%m%d)/CLAUDE.md.backup` (1,797줄)
- **교훈**: `.claude/lessons-learned.md` (21KB)
- **분석 문서**: `docs/analysis/close-price-analysis.md`

---

## 8. 버전 관리

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 1.0 | 2026-04-21 | 초안 작성 (계획 수립) | Claude Code |
| 1.1 | (예정) | 실행 후 결과 업데이트 | - |

---

## 9. 용어 정리

| 용어 | 설명 |
|------|------|
| **WHY/WHAT/HOW** | Anthropic 권장 CLAUDE.md 구조 (목적/구조/방법) |
| **Tier 1/2** | 문서 계층 (Tier 1: 자동 로드, Tier 2: 필요 시 참조) |
| **Issue #1~#11** | Tradebot 프로젝트에서 발생한 11개 트러블슈팅 사례 |
| **REST Reconcile** | Upbit REST API와 로컬 데이터의 정합성 검증 시스템 |
| **Golden/Dead Cross** | EMA 크로스 기반 매수/매도 신호 |
| **BACKFILL** | 과거 봉 데이터 재평가 (미확정 → 확정 종가) |
| **Progressive Retry** | 확정 봉 검증을 위한 점진적 재시도 메커니즘 |

---

## 10. FAQ

### Q1: 기존 Issue #1~#11 상세 내용은 어디로?

**A**: `.backup/$(date +%Y%m%d)/CLAUDE.md.backup`에 영구 보존. 필요 시 Import 문법으로 참조 가능.

### Q2: 150줄로 충분한가?

**A**: Anthropic 권장 200줄 이하. 핵심만 남기고 상세는 Tier 2 문서로 분리하여 충분함.

### Q3: Rollback 시 Issue 정보 손실?

**A**: 백업에 완전히 보존되어 있으므로 손실 없음. 언제든지 복원 가능.

### Q4: 새로운 Issue 발생 시 어디에 기록?

**A**: `.claude/lessons-learned.md`에 인덱스 추가 → 상세 내용은 별도 문서 (docs/lessons/)

### Q5: FoodBid와 Tradebot 차이점은?

**A**: 도메인이 다름 (공공입찰 vs 트레이딩). 핵심 철학(⚠️ CRITICAL)은 동일하게 적용, 도메인 특화 내용만 조정.

---

**마지막 업데이트**: 2026-04-21
**상태**: 계획 수립 완료 (실행 대기)
**다음 단계**: 사용자 승인 후 Phase 1 시작
