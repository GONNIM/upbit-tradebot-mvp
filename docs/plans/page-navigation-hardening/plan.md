# Page Navigation Hardening — 통합 수정 기획안

**작성일**: 2026-07-03
**상태**: 초안 — 결정 항목 D1~D8 사용자 승인 대기
**배포 정책**: 6개 Sub-Phase (SP-NAV-1~6) 로컬 완료 후 **단일 배포** ([[feedback_deploy_only_when_complete]])
**전제**: 봇 정상 운영 중 (자본 노출 X — 페이지 이동 결함은 UI 층 한정)

관련:
- 근거 감사: [[../../analysis/2026-07-03-page-navigation-audit/audit-map.md]] — F1~F5 확정 결함 지도
- 사용자 지시 원문: "당장 해당 상황만 회피하려고 하지 말고 전체적으로 페이지 이동시 정상적으로 이동이 되도록 명백하게 구현. 편협적으로 보지 말 것"
- 참조 교훈: [[../../../.claude/lessons-learned.md#교훈-14]] session_state 동기화 / [[../../../.claude/lessons-learned.md#교훈-19]] 편협적 수정 금지 / [[../../../.claude/lessons-learned.md#교훈-20]] 광범위 감사 우선

---

## 1. WHY (목적)

Phase A 감사에서 F1~F5 결함이 얽혀 확인됨:

- **F1** — `switch_page` 사용 5건에서 URL query_params 미세팅 → 뒤로가기 시 컨텍스트 복원 불가
- **F2** — `switch_page` vs `meta refresh` **혼용** → 이동 흐름 예측 불가
- **F3** — 세션 유실 시 자동 복구 부재 (2건은 오류 stop, 3건은 리다이렉트 → 일관성 없음)
- **F4** — settings_history → dashboard 이동 시 세션 재세팅 없음
- **F5** — dashboard.py user_id 빈 문자열 관대함

**근본 원칙**: 편협적 수정 배제. **이동 방식 단일화 + 컨텍스트 이중 소유 + 자동 복구** 세 축으로 통합 대응.

---

## 2. WHAT (요구사항)

| ID | 요구 | 우선순위 |
|---|---|---|
| R1 | 앱 내 모든 페이지 이동을 **단일 방식** 으로 통일 (switch_page + query_params) | MUST |
| R2 | 모든 이동 시 **session_state 와 URL query_params 이중 세팅** (하나 유실 시 다른 하나로 복구) | MUST |
| R3 | 필수 컨텍스트(user_id) 부재 시 모든 페이지에서 **로그인 페이지 자동 리다이렉트** 통일 | MUST |
| R4 | 페이지 진입 컨트랙트 헬퍼 통합 (`bootstrap_page_context`) — 6개 페이지 개별 구현 종식 | MUST |
| R5 | 페이지 이동 헬퍼 통합 (`navigate_to`) — 15개 이동 지점 표준화 | MUST |
| R6 | 브라우저 뒤로가기·직접 URL 접근 모두 안전 (F1 재발 방지) | MUST |
| R7 | 회귀 없음 — 정상 이동 흐름(로그인→대시보드→다른 페이지) 무영향 | MUST |

---

## 3. AS-IS (현재 흐름 요약)

```
┌───────────────────────────────────────────────────────────┐
│ 15개 이동 지점 (혼용):                                     │
│                                                            │
│  switch_page (5건)              meta refresh (10건)        │
│  ─────────────────              ─────────────────          │
│  dashboard → settings_history   dashboard → set_config     │
│  audit_viewer → settings_history dashboard → confirm_init  │
│  settings_history → dashboard   dashboard → set_buy_sell   │
│  set_config → app               dashboard → audit_viewer   │
│  set_buy_sell → app             confirm → set_config       │
│  confirm → app                  confirm → dashboard        │
│                                 set_config → next_page     │
│                                 set_buy_sell → dashboard   │
│                                 dashboard → app(redirect)  │
│                                                            │
│  → URL params 세팅 여부·session state 세팅 여부 일관성 없음│
└───────────────────────────────────────────────────────────┘
```

---

## 4. TO-BE (Sub-Phase 설계)

### SP-NAV-1 — 공통 헬퍼 신규 (`services/page_context.py`)

**목표**: 진입·이동 두 함수로 6개 페이지 표준화.

```python
# services/page_context.py (신규)
"""
페이지 진입·이동 표준 헬퍼 — SP-NAV-1.

원칙:
- 컨텍스트 이중 소유: URL query_params + session_state 둘 다 세팅
- 세션 유실 시 자동 로그인 페이지 리다이렉트
- 이동 방식 단일화: st.switch_page + query_params.update
"""
from __future__ import annotations

from typing import Iterable, Optional
import streamlit as st

# 페이지 컨텍스트 표준 키 (필수 + 선택)
_CONTEXT_KEYS_DEFAULT = ("user_id", "mode", "strategy_type", "virtual_krw")
_REQUIRED_DEFAULT = ("user_id",)


def _get_param(qp, key: str, default=None):
    """query_params 값 획득 (list 대응)."""
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v


def bootstrap_page_context(
    required: Iterable[str] = _REQUIRED_DEFAULT,
    keys: Iterable[str] = _CONTEXT_KEYS_DEFAULT,
    login_page: str = "app.py",
) -> dict:
    """
    페이지 진입 시 컨텍스트 획득·검증·세션 이중 저장·유실 시 리다이렉트.

    Priority: URL query_params → session_state → 기본값(빈 문자열/기본).
    
    Args:
        required: 필수 컨텍스트 키 (없으면 로그인 페이지 리다이렉트).
        keys: 획득 대상 전체 키 (query_params + session_state 이중 저장).
        login_page: 리다이렉트 대상 (기본 app.py).
    
    Returns:
        dict: 획득된 컨텍스트 값들.
    """
    qp = st.query_params
    ctx: dict = {}

    # 1) 획득 (URL 우선, session_state fallback)
    for k in keys:
        default = st.session_state.get(k, "")
        v = _get_param(qp, k, default)
        # mode 는 대문자 정규화
        if k == "mode" and v:
            v = str(v).upper()
        ctx[k] = v

    # 2) 필수 검증
    for k in required:
        if not ctx.get(k):
            # 세션·URL 모두 부재 → 로그인 리다이렉트
            st.warning("세션이 만료되었습니다. 로그인 페이지로 이동합니다.")
            st.switch_page(login_page)
            st.stop()

    # 3) 이중 저장 (session_state)
    for k, v in ctx.items():
        st.session_state[k] = v

    return ctx


def navigate_to(target_page: str, **params) -> None:
    """
    페이지 이동 표준 — session_state + query_params 이중 세팅 후 switch_page.
    
    Args:
        target_page: 대상 페이지 경로 (예: "pages/dashboard.py").
        **params: 이동 시 함께 전달할 컨텍스트 (user_id, mode, ...).
    
    Note:
        params 값은 문자열로 자동 변환. None 값은 제외.
    """
    clean = {k: str(v) for k, v in params.items() if v is not None and v != ""}
    
    # 1) session_state 이중 저장
    for k, v in clean.items():
        st.session_state[k] = v

    # 2) URL query_params 세팅 (뒤로가기 시 복원용)
    if clean:
        st.query_params.update(clean)

    # 3) Streamlit native switch_page
    st.switch_page(target_page)
```

**결정 항목**:
- **D1** — 헬퍼 파일 위치·이름 (`services/page_context.py` 권장 vs `utils/`, `pages/_common.py` 등)
- **D2** — `navigate_to` 시그니처: `target_page` positional + `**params` (권장) vs dict 명시
- **D3** — `bootstrap_page_context` 리다이렉트 UX: 즉시 리다이렉트 (권장) vs 3초 후 자동
- **D5** — query_params 세팅 범위: 필수 컨텍스트만(권장, 5개) vs 모든 페이지 상태 (복잡)

### SP-NAV-2 — `dashboard.py` 진입·이동 통일

**변경 대상 라인**:
- `dashboard.py:72~127` (진입 컨텍스트 획득) → `bootstrap_page_context()` 호출로 교체
- `dashboard.py:2037~2042` (설정 History switch_page) → `navigate_to("pages/settings_history.py", ...)` 통일
- `dashboard.py:609~626` (set_config meta refresh) → `navigate_to("pages/set_config.py", ...)`
- `dashboard.py:2118~2121` (confirm_init_db meta refresh) → `navigate_to(...)`
- `dashboard.py:2347~2355` (set_buy_sell_conditions meta refresh) → `navigate_to(...)`
- `dashboard.py:2483~2486` (audit_viewer meta refresh) → `navigate_to(...)`
- `dashboard.py:631` (로그아웃 리다이렉트 `/`) → `st.switch_page("app.py")`

### SP-NAV-3 — `audit_viewer.py` 진입·이동 통일

- `audit_viewer.py:50~127` (진입 컨텍스트) → `bootstrap_page_context()`
- `audit_viewer.py:135~140` (settings_history 이동) → `navigate_to("pages/settings_history.py", ...)`
- `audit_viewer.py:220` `st.stop()` 오류 스톱 → bootstrap 헬퍼가 리다이렉트 처리로 흡수 (F3 해소)

### SP-NAV-4 — `settings_history.py` 진입·이동 통일 (F4 핵심)

- `settings_history.py:52~86` (진입 컨텍스트) → `bootstrap_page_context()`
- `settings_history.py:81~82` (대시보드 이동) → `navigate_to("pages/dashboard.py", user_id=..., mode=..., strategy_type=...)` — **F4 해소**
- `settings_history.py:85` 오류 메시지 → bootstrap 헬퍼가 흡수 (F3 해소)

### SP-NAV-5 — `set_config` / `set_buy_sell_conditions` / `confirm_init_db` 통일

- 각 파일 진입부 → `bootstrap_page_context()`
- 인증 실패 시 `st.switch_page("app.py")` (기존 유지, bootstrap 헬퍼가 자동화)
- 저장 후 `meta refresh` → `navigate_to(...)` 전량 변경

### SP-NAV-6 — `app.py` 페이지 직접 접근 방어

- Streamlit multipage 특성상 `/pages/xxx` 직접 접근이 app.py 를 우회
- 각 페이지의 `bootstrap_page_context` 가 이 방어를 흡수 — app.py 자체 변경 없음
- **선택적**: `app.py` 최상단에 인증 상태 없이 페이지 접근한 경우의 UX 배너 추가 (D8 결정)

---

## 5. 영향 받는 파일

| 파일 | 변경 규모 | 종류 |
|---|---|---|
| `services/page_context.py` | 신규 (~100줄) | 헬퍼 |
| `pages/dashboard.py` | 진입 헤더 + 5개 이동 지점 + 로그아웃 | 편집 |
| `pages/audit_viewer.py` | 진입 헤더 + 1개 이동 지점 | 편집 |
| `pages/settings_history.py` | 진입 헤더 + 1개 이동 지점 (F4) | 편집 |
| `pages/set_config.py` | 진입 헤더 + 이동 1건 | 편집 |
| `pages/set_buy_sell_conditions.py` | 진입 헤더 + 이동 1건 | 편집 |
| `pages/confirm_init_db.py` | 진입 헤더 + 이동 3건 | 편집 |
| `pages/dashboard.py` 버전 갱신 | 1줄 | Issue #16 정책 |

**미변경**:
- `app.py` (다만 D8 결정 시 최상단 배너 추가 가능)
- 봇 매매 로직 (`core/`, `engine/`) 무관

---

## 6. Phase 순서

```
P0 — 기획안 D1~D8 사용자 승인 (현재 단계)
   ↓
SP-NAV-1 — services/page_context.py 신규 (헬퍼 완성)
   ↓
SP-NAV-2 — dashboard.py 적용
   ↓
SP-NAV-3 — audit_viewer.py 적용
   ↓
SP-NAV-4 — settings_history.py 적용 (F4 해소)
   ↓
SP-NAV-5 — set_config / set_buy_sell_conditions / confirm_init_db 적용
   ↓
SP-NAV-6 — app.py 방어 (선택적, D8 결정)
   ↓
Phase D — 로컬 다각도 테스트
   ├─ unittest — bootstrap 필수 검증 / navigate_to 파라미터 세팅
   ├─ walkthrough — 재현 시나리오 A/B/C + 6개 페이지 상호 이동 전수
   └─ 회귀 — 정상 로그인·이동 무영향
   ↓
Phase E — 사용자 최종 승인 → 커밋 → push → 서버 배포
   ↓
Phase F — 24시간 모니터링 (사용자 이동 오류 재발 없음 확인)
```

---

## 7. 결정 필요 항목 (D1~D8)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| **D1** | 헬퍼 파일 위치 | (a) `services/page_context.py` (b) `utils/page_context.py` (c) `pages/_common.py` | **(a)** — services 계층 일관 |
| **D2** | `navigate_to` 시그니처 | (a) `navigate_to(target, **params)` (b) `navigate_to(target, params: dict)` | **(a)** — 호출 간결 |
| **D3** | 세션 유실 리다이렉트 UX | (a) 즉시 리다이렉트 + warning (b) 3초 안내 후 자동 (c) 사용자 클릭 대기 | **(a)** — 즉시 안전 복구 |
| **D4** | `meta refresh` 완전 폐지 | (a) 전량 `navigate_to` 대체 (b) 특정 경우만 유지 (예: LIVE 전환 시 강제 새로고침) | **(a)** — 이동 방식 단일화 |
| **D5** | query_params 세팅 범위 | (a) 필수 5개(user_id, mode, strategy_type, virtual_krw, verified) (b) 모든 페이지 상태 | **(a)** — 최소 침습 |
| **D6** | dashboard.py user_id 빈 문자열 방어(F5) | (a) bootstrap 헬퍼에서 흡수 (`required=("user_id",)`) (b) 별도 방어 로직 | **(a)** — 일관성 |
| **D7** | 롤아웃 순서 | (a) 헬퍼 완성 → 페이지 순차 적용 → 통합 배포 (b) 페이지별 개별 배포 | **(a)** — 단일 배포 원칙 준수 |
| **D8** | app.py 최상단 방어 | (a) 각 페이지 bootstrap 만으로 충분 (변경 없음) (b) app.py 에도 배너 추가 | **(a)** — 이중 방어 불필요, 헬퍼가 흡수 |

---

## 8. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| bootstrap 헬퍼 도입 시 기존 초기화 로직 회귀 | 페이지 진입 시 새로운 오류 | Phase D unittest + 로컬 실행 walkthrough (SP-PI-1 hotfix 교훈: 위젯 순서 검증 필수) |
| `st.switch_page` 스트림릿 버전별 동작 차이 | 특정 케이스에서만 재발 | 로컬 서버(운영과 동일 streamlit 1.46) 로 T1~T9 실행 검증 |
| `meta refresh` 폐지 시 특정 UX 회귀 (예: 저장 후 새로고침 필요 케이스) | 상태 반영 지연 | 필요 시 `navigate_to` 이후 명시적 `st.rerun()` 추가 옵션 |
| query_params 갱신이 위젯 인스턴스화와 충돌 (교훈 #25) | Streamlit API 예외 | 헬퍼 내부에서 위젯 인스턴스화 이전 실행 강제. bootstrap 호출은 페이지 최상단 규약 |
| 사용자 클레임의 실제 시나리오와 수정 방향 불일치 | 재발 | 결함 F1~F4 근본 수정은 A/B/C 시나리오 모두 커버 (§5 감사 지도 근거) |
| 6개 페이지 파일 대량 편집 → 실수 | 배포 후 특정 페이지 접근 불가 | 각 SP 별 py_compile + 로컬 실행 검증. Phase D 에 6페이지 진입 walkthrough 포함 |

---

## 9. 로컬 테스트 시나리오 (Phase D 상세 초안)

### T1 — bootstrap 필수 검증
- user_id 없이 페이지 진입 시 `switch_page("app.py")` 호출 + `st.stop`
- unittest 로 리다이렉트 호출 검증

### T2 — navigate_to 이중 저장
- `navigate_to("pages/dashboard.py", user_id="mcmax33", mode="LIVE")` 호출 후
- session_state["user_id"] == "mcmax33", session_state["mode"] == "LIVE"
- query_params["user_id"] == "mcmax33", query_params["mode"] == "LIVE"

### T3 — 원 재현 시나리오 A walkthrough
- 대시보드 → 감사 로그 뷰어 → 설정 History → 뒤로가기 → 설정 History URL 복원 → **세션 유지되면 정상 표시**, 유실 시 자동 로그인 리다이렉트

### T4 — 원 재현 시나리오 C (직접 URL)
- `/settings_history` URL 직접 입력 → bootstrap 이 세션 부재 감지 → 로그인 리다이렉트

### T5 — 정상 흐름 회귀
- 로그인 → 대시보드 → 각 페이지 순회 → 대시보드 복귀 → 로그아웃
- 모든 이동에서 세션·URL 정합

### T6 — 뒤로가기·앞으로가기 정합성
- 각 페이지 이동 후 브라우저 뒤로/앞으로 → URL 로 컨텍스트 복원 확인

### T7 — 로그아웃 후 페이지 접근
- 로그아웃 후 `/settings_history` 접근 → 로그인 리다이렉트

### T8 — 모든 페이지 상호 이동 매트릭스
- 6 페이지 x 6 페이지 = 30개 조합 중 실제 존재하는 이동 링크 (약 15개) 정상 동작 확인

### T9 — Streamlit 위젯 규칙 준수 (교훈 #25)
- bootstrap / navigate_to 가 어느 위젯 인스턴스화 이후 session_state 세팅하지 않음을 코드 정적 검증

---

## 10. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-07-03 21:40 | 감사 완료 | audit-map.md (F1~F5) |
| 2026-07-03 21:50 | 초안 작성 | Phase B 기획안. D1~D8 사용자 승인 대기. SP-NAV-1~6 로컬 완료 후 단일 배포 |

---

## 다음 단계

**D1~D8 결정** 알려주시면 SP-NAV-1 부터 순차 로컬 구현 착수. "모두 추천안대로" 또는 특정 항목 조정 형식 무방.
