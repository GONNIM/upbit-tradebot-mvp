# Upbit Tradebot MVP - 사용 가이드

**버전**: 2.0 (Anthropic Best Practices 적용)
**마지막 업데이트**: 2026-04-22

---

## 📖 목차

1. [Claude Code 시작하기](#1-claude-code-시작하기)
2. [CLAUDE.md 활용 방법](#2-claudemd-활용-방법)
3. [Issue 문서 참조 방법](#3-issue-문서-참조-방법)
4. [문서 업데이트 방법](#4-문서-업데이트-방법)
5. [트러블슈팅](#5-트러블슈팅)
6. [FAQ](#6-faq)

---

## 1. Claude Code 시작하기

### 1.1 기본 사용법

Claude Code는 프로젝트 루트의 `CLAUDE.md` 파일을 자동으로 읽어 프로젝트 컨텍스트를 파악합니다.

**질문 예시**:
```
"REST API에서 미확정 종가가 반환되는 문제를 어떻게 해결하나요?"
"Golden Cross가 감지되었는데 매수가 안 됩니다. 어떻게 디버깅하나요?"
"로컬에서 봇을 실행하려면 어떻게 하나요?"
```

### 1.2 문서 구조 이해

- **CLAUDE.md**: 프로젝트 개요 및 핵심 규칙 (200줄 이내)
- **.claude/context/project-rules.md**: Issue 인덱스 및 긴급 대응
- **.claude/lessons-learned.md**: 전체 교훈 상세 설명
- **docs/issues/**: Issue #1-11 상세 문서 (10개 파일)

### 1.3 빠른 참조

**긴급 상황 발생 시**:
1. `@.claude/context/project-rules.md` → "긴급 상황 대응 우선순위" 섹션
2. 해당하는 Issue 번호 확인
3. `@docs/issues/issue-XX.md` 참조

**특정 Issue 찾기**:
- Golden Cross 미감지 → Issue #11
- REST API 종가 불일치 → Issue #8
- BACKFILL 중복 체크 → Issue #9

---

## 2. CLAUDE.md 활용 방법

### 2.1 WHY 섹션 (목적)

**언제 참조하나요?**
- 프로젝트가 무엇을 하는지 파악할 때
- 핵심 기능과 해결하는 문제를 이해할 때

**예시 질문**:
```
"이 봇은 어떤 전략을 사용하나요?"
"REST Reconcile이 왜 필요한가요?"
```

**답변 위치**: CLAUDE.md의 "WHY (목적)" 섹션

### 2.2 WHAT 섹션 (구조)

**언제 참조하나요?**
- 코드 구조를 파악할 때
- 특정 기능이 어느 모듈에 있는지 찾을 때

**예시 질문**:
```
"EMA 증분 계산 코드는 어디에 있나요?"
"포지션 관리 로직은 어느 파일인가요?"
```

**답변 위치**: CLAUDE.md의 "WHAT (구조)" 섹션 → 핵심 모듈 설명

### 2.3 HOW 섹션 (작업 방법)

**언제 참조하나요?**
- 로컬에서 봇을 실행할 때
- 서버에 배포할 때
- 전략 파라미터를 수정할 때

**예시 질문**:
```
"로컬에서 EMA 전략으로 봇을 실행하려면?"
"서버에 배포하는 절차는?"
```

**답변 위치**: CLAUDE.md의 "HOW (작업 방법)" 섹션

### 2.4 CRITICAL 섹션 (작업 원칙 및 금지 사항)

**언제 참조하나요?**
- 코드를 수정하기 전에 (금지 사항 확인)
- Issue가 발생했을 때 (교훈 적용)
- 배포 전 체크리스트 확인

**예시 질문**:
```
"REST API를 직접 호출해도 되나요?"
"BACKFILL 실행 전 확인할 사항은?"
```

**답변 위치**: CLAUDE.md의 "⚠️ CRITICAL - 작업 원칙 및 금지 사항" 섹션

---

## 3. Issue 문서 참조 방법

### 3.1 Issue 인덱스에서 찾기

**단계**:
1. `.claude/context/project-rules.md` 열기
2. "📋 Issue 인덱스 (10개)" 테이블 확인
3. 증상과 일치하는 Issue 번호 찾기
4. `docs/issues/issue-XX.md` 파일 열기

**예시**:
```
증상: "Golden Cross 발생했는데 매수 안 됨"
→ Issue 인덱스에서 검색: "BACKFILL 지표 오염"
→ Issue #11 확인
→ docs/issues/issue-11.md 열기
```

### 3.2 Issue 문서 구조

각 Issue 문서는 다음 섹션으로 구성됩니다:

```markdown
### 🔴 Issue #XX: 제목

#### 문제
[증상 및 발생 상황]

#### 근본 원인
[왜 이 문제가 발생했는지]

#### 왜 놓쳤나?
[초기 진단에서 놓친 점]

#### 교훈
[핵심 교훈 3가지]

#### 수정
[Before/After 코드 예시]

#### 영향 범위
[수정된 파일 및 라인]

#### 검증 방법
[수정 후 확인 절차]
```

### 3.3 Claude Code에 질문하기

**잘못된 질문**:
```
"Issue #11이 뭐죠?"  # 너무 일반적
```

**올바른 질문**:
```
"Golden Cross가 감지되었는데 매수 신호가 발생하지 않습니다. Issue #11과 관련이 있나요?"
"BACKFILL 실행 후 지표 상태를 어떻게 복원하나요? (Issue #11 참조)"
```

**Claude Code 응답 예시**:
```
Issue #11 (BACKFILL 지표 오염)과 관련이 있습니다.

근본 원인: BACKFILL이 `prev_ema_fast`, `prev_ema_slow` 값을 덮어씀
→ 다음 실시간 봉에서 Golden Cross 감지 실패

해결 방법:
1. BACKFILL 시작 전: 지표 상태 백업
2. BACKFILL 처리
3. BACKFILL 종료 후: 지표 상태 복원

상세: @docs/issues/issue-11.md
```

---

## 4. 문서 업데이트 방법

### 4.1 새로운 Issue 추가

**시나리오**: Issue #12가 발생했고 문서화가 필요합니다.

**단계**:

1. **Issue 파일 생성** (`docs/issues/issue-12.md`):
```markdown
### 🔴 Issue #12: [제목]

**발생일**: 2026-XX-XX
**심각도**: 🔴 Critical

#### 문제
[증상]

#### 근본 원인
[원인]

#### 교훈
1. [교훈 1]
2. [교훈 2]

#### 수정
[Before/After 코드]

#### 재발 방지
- [ ] [체크리스트 1]
- [ ] [체크리스트 2]
```

2. **project-rules.md 업데이트**:
```markdown
## 📋 Issue 인덱스 (11개)  # 10개 → 11개

| # | 제목 | 핵심 메시지 | 날짜 |
|---|------|------------|------|
| 12 | [제목] | [핵심 메시지] | 2026-XX-XX |
```

3. **CLAUDE.md 업데이트** (필요 시):
```markdown
## ⚠️ CRITICAL - 작업 원칙 및 금지 사항

### 금지 사항

```python
# ❌ 절대 금지 (Issue #12)
[잘못된 코드]
# ✅ 올바른 방법
[올바른 코드]
```

4. **lessons-learned.md 업데이트**:
```markdown
### 교훈 #12: [제목]

**증상**: [...]
**근본 원인**: [...]
**핵심 교훈**: [...]
```

### 4.2 CLAUDE.md 수정 (200줄 제한 유지)

**원칙**:
- 새 내용 추가 시 기존 내용을 `docs/`로 이동
- WHY/WHAT/HOW/CRITICAL 비율 유지
- Import 구문 활용

**예시**:
```markdown
# Before (CLAUDE.md에 전체 내용)
### 백테스팅 방법
1. [긴 설명 50줄]

# After (CLAUDE.md → Import)
### 백테스팅
상세: @docs/operations/backtesting-guide.md
```

### 4.3 Git 커밋 가이드

**커밋 메시지 형식**:
```bash
git commit -m "docs: Issue #12 추가 - [간단한 설명]"
git commit -m "refactor(docs): CLAUDE.md 200줄 준수 - [내용]을 docs/로 이동"
git commit -m "fix(docs): project-rules.md Issue 인덱스 오타 수정"
```

---

## 5. 트러블슈팅

### 5.1 "Claude Code가 Issue 문서를 참조하지 않습니다"

**증상**:
```
질문: "Issue #11 관련해서 설명해주세요"
응답: "Issue #11에 대한 정보가 없습니다"
```

**원인**: Import 구문이 잘못되었거나 파일 경로가 틀림

**해결**:
1. `CLAUDE.md`에서 Import 구문 확인:
   ```markdown
   - @docs/issues/issue-11.md  # ✅ 올바름
   - docs/issues/issue-11.md   # ❌ @ 누락
   ```

2. 파일 존재 여부 확인:
   ```bash
   ls docs/issues/issue-11.md
   ```

3. `.gitignore` 확인 (docs/ 폴더가 무시되지 않았는지):
   ```bash
   cat .gitignore | grep docs
   ```

### 5.2 "CLAUDE.md가 200줄을 초과합니다"

**증상**: CLAUDE.md 줄 수가 250줄

**원인**: 상세 내용을 CLAUDE.md에 직접 작성

**해결**:
1. 상세 내용을 별도 파일로 분리:
   ```bash
   # 예: 백테스팅 가이드를 별도 파일로
   echo "[백테스팅 상세 내용]" > docs/operations/backtesting-guide.md
   ```

2. CLAUDE.md에서 Import로 변경:
   ```markdown
   # Before
   ### 백테스팅
   [50줄의 상세 내용]

   # After
   ### 백테스팅
   상세: @docs/operations/backtesting-guide.md
   ```

3. 줄 수 확인:
   ```bash
   wc -l CLAUDE.md
   # 200 이하 확인
   ```

### 5.3 "Issue 인덱스와 실제 파일이 불일치합니다"

**증상**: project-rules.md에 Issue #15가 있는데 `docs/issues/issue-15.md` 파일이 없음

**원인**: 문서 누락 또는 인덱스 오류

**해결**:
1. 실제 Issue 파일 목록 확인:
   ```bash
   ls docs/issues/
   ```

2. project-rules.md 인덱스와 비교:
   ```bash
   grep "^|" .claude/context/project-rules.md | grep -v "^| #"
   ```

3. 누락된 파일 생성 또는 인덱스에서 제거

### 5.4 "Git이 .claude/ 디렉토리를 추적하지 않습니다"

**증상**: `git status`에서 .claude/ 파일이 보이지 않음

**원인**: `.gitignore`에서 .claude/ 전체를 무시

**해결**:
1. `.gitignore` 확인:
   ```bash
   cat .gitignore | grep .claude
   ```

2. 선택적 추적 패턴으로 변경:
   ```
   # Before
   .claude/

   # After
   .claude/*
   !.claude/context/
   !.claude/lessons-learned.md
   ```

3. Git 캐시 갱신:
   ```bash
   git rm -r --cached .claude/
   git add .claude/context/ .claude/lessons-learned.md
   ```

### 5.5 "Boilerplate 검증이 실패합니다"

**증상**: `validate_boilerplate.sh` 실행 시 FAIL

**원인**: CLAUDE.md에 필수 키워드가 없음

**해결**:
1. 실패한 시나리오 확인:
   ```bash
   ./scripts/validate_boilerplate.sh
   # Scenario 6: FAIL (missing 'deploy')
   ```

2. CLAUDE.md에 키워드 추가:
   ```markdown
   # Before
   # systemd 배포 (권장)

   # After
   # systemd deploy (권장)
   ```

3. 재검증:
   ```bash
   ./scripts/validate_boilerplate.sh
   # Scenario 6: PASS
   ```

---

## 6. FAQ

### Q1. CLAUDE.md는 왜 200줄 제한인가요?

**A**: Anthropic Best Practices에 따르면 Claude Code는 200줄 이하의 CLAUDE.md를 가장 효과적으로 처리합니다. 길이가 길어지면 컨텍스트 우선순위가 낮아져 무시될 수 있습니다.

### Q2. Issue #3은 왜 없나요?

**A**: Issue #3는 낮은 심각도(IndentationError)로 별도 문서화가 불필요하다고 판단되었습니다. lessons-learned.md에는 기록되어 있지만 독립 파일로 분리되지 않았습니다.

### Q3. 어떤 파일을 Git에 커밋해야 하나요?

**A**:
- ✅ 커밋: CLAUDE.md, .claude/context/, .claude/lessons-learned.md, docs/
- ❌ 무시: .claude/personal-settings.md (개인 설정)

### Q4. Issue 문서는 어떤 순서로 읽어야 하나요?

**A**:
1. 문제 발생 시 → `.claude/context/project-rules.md` (Issue 인덱스)
2. 증상과 일치하는 Issue 번호 찾기
3. `docs/issues/issue-XX.md` 읽기 (문제 → 원인 → 교훈 → 수정)
4. 필요 시 `.claude/lessons-learned.md` 참조 (전체 교훈 맥락)

### Q5. CLAUDE.md를 수정한 후 Claude Code를 재시작해야 하나요?

**A**: 아니요. CLAUDE.md는 각 대화 시작 시 자동으로 로드됩니다. 수정 후 새 대화를 시작하면 변경 사항이 반영됩니다.

### Q6. Import 구문(@)을 사용할 수 없는 경우는?

**A**:
- 파일이 Git에 커밋되지 않은 경우
- `.gitignore`에서 무시되는 경로인 경우
- 파일 경로가 잘못된 경우

Import는 Git 추적 파일만 참조 가능합니다.

### Q7. 여러 Issue가 동시에 발생하면 어떻게 하나요?

**A**:
1. `.claude/context/project-rules.md` → "긴급 상황 대응 우선순위" 확인
2. 우선순위 순서대로 해결 (Golden Cross → REST API → BACKFILL)
3. 각 Issue 문서 참조하여 순차 해결

### Q8. 새로운 전략을 추가하려면 문서를 어떻게 업데이트하나요?

**A**:
1. `CLAUDE.md` → "WHY (목적)" → "지원 전략" 섹션에 추가
2. `CLAUDE.md` → "WHAT (구조)" → 해당 모듈 경로 추가
3. `CLAUDE.md` → "HOW (작업 방법)" → 실행 명령어 추가
4. 필요 시 `docs/strategies/` 폴더에 상세 가이드 추가

### Q9. 테스트 스크립트는 어디에 작성하나요?

**A**: **반드시 `tests/` 디렉토리에 작성**해야 합니다.

**규칙**:
```bash
✅ 올바른 위치:
tests/test_tp_sl_integration.py
tests/test_sell_filter_execution.py
tests/test_candle_validator.py

❌ 잘못된 위치:
test_something.py              # 루트 디렉토리 금지
scripts/test_something.py      # scripts는 운영용
```

**sys.path 설정 (필수)**:
```python
import sys
from pathlib import Path

# tests/ 디렉토리에서 프로젝트 루트 참조
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_incremental import IncrementalEMAStrategy
```

**실행 방법**:
```bash
# tests/ 디렉토리에서 실행
python3 tests/test_tp_sl_integration.py

# 또는 pytest 사용
pytest tests/
```

**이유**:
- `.gitignore`에 `/tests*` 규칙으로 로컬 전용 처리
- 루트 디렉토리 정리 (운영 파일과 분리)
- 기존 패턴 준수 (`test_candle_validator.py` 위치)

---

## 📚 추가 자료

- **Anthropic Best Practices**: CLAUDE.md 작성 가이드 (공식)
- **FoodBid Boilerplate**: 이 프로젝트에 적용된 구조의 원본
- **Issue 타임라인**: `.claude/lessons-learned.md` (Issue #1-11 발생 순서 및 맥락)

---

**문의 및 피드백**:
- 이 가이드의 개선 사항은 `docs/USAGE_GUIDE.md`에 직접 수정 후 커밋해주세요.
- 새로운 패턴이나 팁을 발견하면 FAQ에 추가해주세요.

**마지막 업데이트**: 2026-04-22
