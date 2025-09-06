# AGENTS.md — Rules for AI Agents in This Repository

본 문서는 **AI 에이전트(Codex, GPT, Claude, Copilot, Cursor 등)**가 본 리포에서 작업할 때 반드시 따라야 할 규칙을 정의합니다.  
사람용 가이드는 `README.md`, 에이전트용은 본 문서를 우선합니다.

---

## 0. 목적
- Streamlit 기반 **트레이드봇 MVP** (Python + MySQL + Upbit API) 개발을 지원
- 설계/구현/리뷰 단계마다 일관된 규칙 적용
- PLAN/REVIEW 루프 + REPO_MAP/CODE_FLAGS를 활용해 품질 유지

---

## 1. 역할과 범위
- 기본 역할:
  - `docs/PLAN_*.md` 기반 설계 요약, 코드 작성
  - Upbit API 기반 매매 로직 및 DB 연동 구현
  - diff 리뷰 및 개선안 작성(`docs/REVIEW_*.md`)
- 금지 역할:
  - 실제 API 키/시크릿 노출
  - 무단 거래 실행 (샌드박스/테스트 모드 외 금지)
  - 파괴적 마이그레이션 실행 (승인 전 불가)

---

## 2. 컨텍스트 소스 (우선순위)
에이전트는 작업 시 아래 순서로 문서를 참조합니다:

1. 최신 `docs/PLAN_*.md`
2. `docs/REVIEW_*.md`
3. `REPO_MAP.txt`, `CODE_FLAGS.txt`
4. `README.md`, `.env.example`, `pyproject.toml`, `requirements.txt`, `docker-compose.yml`
5. 소스 코드: `app/`, `engine/`, `strategies/`, `db/`, `tests/`

> **PLAN 문서가 Single Source of Truth (SSOT)** 입니다.

---

## 3. 작업 규칙
- PLAN 문서에 없는 변경은 직접 실행하지 말고 **PLAN 제안** 추가 후 진행.
- 코드 수정은 **파일 전체 최종본** 제시 (부분 패치 X).
- DB 변경은 반드시 마이그레이션 SQL + 롤백 플랜 동반.
- MySQL 연결은 ORM(SQLAlchemy) 또는 안전한 쿼리 빌더 사용.
- 모든 거래 로직에는 **모의 실행(Sandbox/Log Only) 옵션** 추가.

---

## 4. 출력 형식
### 코드 출력
FINAL CODE

<파일경로>

# 전체 코드

- 여러 파일일 경우 `# FINAL CODE` 블록 반복
- 설명은 코드 블록 위 간단히, 최종 출력은 반드시 `# FINAL CODE` 블록에만

### 리뷰 출력
REVIEW
- PLAN 대비 충족/누락
- 보안/성능/예외/테스트 지적
- 개선안 (우선순위 1,2,3)

---

## 5. 안전/보안/정책
- API 키/시크릿은 `.env`에서 로드, **코드 내 하드코딩 금지**
- `.env.example`에 키 형식만 제공
- DB 접속 정보도 `.env`로 관리
- 외부 호출 예시는 반드시 더미 키/가짜 URL 사용
- 실제 매매 실행은 `LIVE_MODE=true` 명시적 설정 시에만 허용

---

## 6. 테스트 & 품질 바
- 새 기능에는 반드시 최소 1개 이상 테스트 추가 (`pytest` 사용)
- 테스트 종류:
  - 유닛: 전략 로직, 보조지표 계산
  - 통합: DB CRUD, Streamlit 뷰 렌더링
  - 모의: Upbit API 호출(mock)
- Lint/포맷터(black, flake8, ruff) 통과 필수

---

## 7. 도구 사용 원칙
- **Codex / Code 모델** → 구현, 리팩터링, 테스트 코드 작성
- **Claude / GPT** → 설계 검토, 리스크 리뷰, 품질 점검
- **Copilot / Cursor** → 자동완성 보조, 최종 규칙은 AGENTS.md 우선

---

## 8. 변경 관리
- 커밋 메시지 규칙: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- 파괴적 변경은 `BREAKING CHANGE:`로 명시
- DB 스키마 변경은 항상 마이그레이션 파일 생성 (예: `migrations/xxxx.sql`)

---

## 9. 실패 복구
- 빌드/테스트 실패 시:
  1. 실패 원인 요약
  2. 수정 제안
  3. 재실행
- 거래 로직 오류 발생 시:
  - 즉시 포지션 청산 로직 여부 확인
  - 로그를 DB에 기록 후 보고

---

## 10. 예시 워크플로
1. `make insights` → `REPO_MAP.txt`, `CODE_FLAGS.txt` 갱신
2. GPT: `docs/PLAN_trade-strategy.md` 생성
3. Claude: PLAN 리스크 검토 및 수정
4. Codex: PLAN 기반 코드 작성 (`# FINAL CODE` 출력 형식)
5. GPT/Claude: diff 리뷰 → `docs/REVIEW_trade-strategy.md` 작성
6. Codex: REVIEW 기반 개선
7. PR 생성 → CI(테스트, lint, 안전검사) 통과 → 최종 머지
