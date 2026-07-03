# Page Navigation Audit Map — 2026-07-03

**작성일**: 2026-07-03
**계기**: 사용자 클레임 재발 — 대시보드→감사 로그 뷰어→뒤로가기 시 `settings_history` 페이지에서 "user_id 가 비어있습니다" 오류
**사용자 명시 지시**: "당장 해당 상황만 회피하려고 하지 말고 전체적으로 페이지 이동시 정상적으로 이동이 되도록 명백하게 구현. 편협적으로 보지 말 것. 전체 페이지 이동 시 모든 상황에서 체크한 후 보고"
**참조 교훈**: #14 (session_state 동기화 누락), #15 (Streamlit 멀티페이지 경로 오류), #19 (편협적 수정 금지)

---

## 1. 페이지 인벤토리 (진입점 7개)

| 파일 | 역할 | 진입 컨트랙트 (필수) |
|---|---|---|
| `app.py` | 로그인 진입점 (Streamlit main) | 없음 (인증 자체 담당) |
| `pages/dashboard.py` | 메인 대시보드 | user_id, mode |
| `pages/audit_viewer.py` | 감사 로그 뷰어 | user_id, mode, strategy_type |
| `pages/settings_history.py` | 설정 History (P2) | user_id, mode, strategy_type |
| `pages/set_config.py` | Config 설정 | user_id, mode |
| `pages/set_buy_sell_conditions.py` | 매수/매도 조건 설정 | user_id |
| `pages/confirm_init_db.py` | DB 초기화 확인 | user_id |

## 2. 전체 이동 흐름 지도 (실측)

```
app.py (로그인)
   └─ authentication_status=True 이후 dashboard 자동 렌더 (Streamlit multipage)

dashboard.py
   ├─ 📜 설정 History 보기          → switch_page("pages/settings_history.py")
   │     · session_state 3개 세팅 ✓
   │     · URL query_params 세팅 ❌  ← 결함 F1
   ├─ Config 이동                    → meta refresh("./set_config?params")
   ├─ DB 초기화 확인 이동            → meta refresh("./confirm_init_db?params")
   ├─ 매수/매도 조건 이동            → meta refresh("./set_buy_sell_conditions?params")
   └─ 감사 로그 뷰어 이동            → meta refresh("./audit_viewer?params")

audit_viewer.py
   └─ 📜 설정 History                → switch_page("pages/settings_history.py")
       · session_state 3개 세팅 ✓
       · URL query_params 세팅 ❌  ← 결함 F1

settings_history.py
   └─ ⬅ 대시보드                     → switch_page("pages/dashboard.py")
       · session_state 세팅 ❌      ← 결함 F4 (핵심)
       · URL query_params 세팅 ❌  ← 결함 F1

set_config.py
   ├─ 인증 실패                       → switch_page("app.py")
   └─ 저장 후 이동                    → meta refresh("./{next_page}?params")

set_buy_sell_conditions.py
   ├─ 인증 실패                       → switch_page("app.py")
   └─ 저장 후                         → meta refresh("./dashboard?params")

confirm_init_db.py
   ├─ 취소                            → switch_page("app.py")
   ├─ 확인                            → meta refresh("./set_config?params")
   └─ 닫기                            → meta refresh("./dashboard?params")
```

## 3. 각 페이지 진입 컨텍스트 획득 방식 (일관성 없음)

모든 페이지 공통 패턴 (일관됨):
```python
qp = st.query_params
def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list): return v[0]
    return v
user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
```

**우선순위**: URL query_params → session_state → 빈 문자열

**세션 유실 시 처리 (일관성 없음)**:

| 페이지 | 유실 시 동작 |
|---|---|
| `dashboard.py` | user_id 빈 문자열로 진행 → 하류 처리 안전 여부 미검증 |
| `audit_viewer.py:220` | `st.stop()` (오류 메시지 없음) |
| `settings_history.py:85` | `st.error(...)` + `st.stop()` |
| `set_config.py` | `st.switch_page("app.py")` 리다이렉트 ✓ (그러나 조건부) |
| `set_buy_sell_conditions.py:75` | `st.switch_page("app.py")` 리다이렉트 ✓ |
| `confirm_init_db.py:40` | `st.switch_page("app.py")` 리다이렉트 ✓ |

## 4. 확정 결함 지도 (F1~F5)

### F1: 🔴 `switch_page` 사용 시 URL query_params 미세팅 (5건)

**위치**:
- `dashboard.py:2042` → settings_history
- `audit_viewer.py:140` → settings_history
- `settings_history.py:82` → dashboard
- `set_config.py:161`, `set_buy_sell_conditions.py:75`, `confirm_init_db.py:40` → app.py (리다이렉트)

**결함 근거**:
- `switch_page` 은 URL 을 변경하지만 이전 페이지가 별도로 `st.query_params.update(...)` 하지 않으면 URL 이 `/settings_history` (query_params 없음) 상태로 이동
- 이후 브라우저 뒤로가기 시 이 URL 로 복원 → **query_params 소스 없음 → session_state 유실 시 즉각 오류**
- 반면 `meta refresh` 방식은 URL 에 params 세팅 → 뒤로가기 시 URL 로 복원 가능

**영향**: 사용자 뒤로가기 시 세션 컨텍스트 복원 불가.

### F2: 🔴 두 이동 방식(switch_page vs meta refresh) 혼용

**위치**: 앱 전체

**결함 근거**:
- `switch_page` — Streamlit native, session_state 유지, URL query_params 안 세팅
- `meta refresh` — HTML redirect, URL query_params 세팅, 브라우저 히스토리 정상 스택
- **한 앱 안에서 이 두 방식이 뒤섞임** → 사용자·개발자 예측 불가
- 각 방식의 부작용(뒤로가기 스택, 세션 유지, 브라우저 새로고침 등) 다름

**영향**: 이동 흐름의 정합성 붕괴. 특정 조합에서만 재발하는 결함 만듦.

### F3: 🔴 session_state 유실 시 자동 복구 부재 (2건)

**위치**:
- `audit_viewer.py:220` — 오류 메시지 없이 `st.stop()`
- `settings_history.py:85` — 오류 메시지 + `st.stop()`, 로그인 페이지 자동 이동 없음

**결함 근거**:
- 세션 유실은 사용자 실수(예: 다른 탭 로그아웃, 세션 만료)로 발생 가능
- 오류 메시지만 표시하고 사용자에게 "대시보드에서 다시 진입" 안내 → **사용자 조작 강제**
- `set_config.py` / `set_buy_sell_conditions.py` / `confirm_init_db.py` 는 `st.switch_page("app.py")` 로 자동 로그인 리다이렉트 → **불일치**

**영향**: 사용자 UX 나쁨. 재발 시나리오 반복 발생.

### F4: 🔴 settings_history → dashboard 이동 시 session_state 미세팅

**위치**: `settings_history.py:81~82`
```python
if st.button("⬅ 대시보드", use_container_width=True):
    st.switch_page("pages/dashboard.py")
```

**결함 근거**:
- audit_viewer → settings_history 이동은 `session_state["user_id"] = user_id` 등 3개 세팅 후 switch_page (audit_viewer.py:137~140)
- settings_history → dashboard 이동은 **세션 재확인·재세팅 없음**
- dashboard.py 는 session_state fallback 을 사용하므로 이미 세팅된 값 있으면 정상. 하지만 유실됐다면?

**영향**: 결함 자체는 dashboard 의 fallback 로직으로 완화되지만, F3 와 결합 시 오류 재현.

### F5: 🟡 dashboard.py 자체의 user_id 빈 문자열 방어 부재

**위치**: `dashboard.py:80~82`
```python
user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
st.session_state["user_id"] = user_id  # ← 빈 문자열이어도 세팅
```

**결함 근거**:
- user_id 가 빈 문자열이어도 그대로 진행
- 하류 로직(예: DB 조회, 잔고 조회)에서 사용자별 데이터 조회 시 문제 발생 가능
- 다른 페이지는 명시 오류 표시하는데 dashboard 는 관대함 → 일관성 없음

**영향**: 세션 완전 유실 상태에서 대시보드 진입 시 하류 오류 예측 어려움.

---

## 5. 사용자 클레임 재현 시나리오 (추정)

### 시나리오 A (가장 유력)
```
① 로그인 → 대시보드 (session_state["user_id"]="mcmax33")
② 대시보드에서 감사 로그 뷰어 이동 (meta refresh, URL: /audit_viewer?user_id=mcmax33&mode=LIVE&...)
   → URL에 user_id 있음
③ 감사 로그 뷰어에서 "📜 설정 History" 클릭 (switch_page, URL: /settings_history)
   → URL에 query_params 없음, session_state 만 있음
④ 브라우저 뒤로가기 → /audit_viewer?user_id=mcmax33&... 복원 → 정상
⑤ 다시 앞으로가기 → /settings_history 복원 → session_state 유지되면 정상
```

이 시나리오에서 오류 발생 조건: **③ 이후 세션이 무언가에 의해 초기화**되어 뒤로가기 → 앞으로가기 시 유실.

### 시나리오 B (혼합)
```
① 로그인 → 대시보드
② 대시보드에서 "📜 설정 History 보기" 클릭 (switch_page, URL: /settings_history 로 이동, query_params 없음)
③ settings_history 에서 "감사 로그 뷰어" 링크 없음 — 이 경로 불가
```

### 시나리오 C (직접 URL)
```
① 사용자가 북마크·주소창으로 /settings_history 직접 입력
② URL query_params 없음 + session_state 없음 (새 세션) → 오류
```

**정확 시나리오 사용자 재확인 없이도**: F1~F4 근본 수정하면 시나리오 A/B/C 모두 안전해짐.

---

## 6. 통합 수정 방향 (원칙)

### 원칙 P1 — 이동 방식 단일화
`switch_page` vs `meta refresh` 혼용 종식. 한 가지 방식으로 통일:
- 옵션 α: **모든 페이지 이동을 meta refresh + query_params 로 통일** (URL 이 항상 컨텍스트 소유)
- 옵션 β: **모든 페이지 이동을 switch_page + query_params 세팅으로 통일** (Streamlit native)
- **옵션 β 권장** — Streamlit 표준 API + 명시적 세션 세팅

### 원칙 P2 — 컨텍스트 이중 소유
모든 페이지 이동 시:
1. `st.query_params.update({user_id, mode, strategy_type, ...})` — URL 로 뒤로가기 시 복원
2. `st.session_state[...] = ...` — 세션 유지
→ **두 통로 모두 세팅** → 하나 유실돼도 다른 하나로 복구

### 원칙 P3 — 세션 유실 시 자동 리다이렉트
모든 페이지에서 필수 컨텍스트(user_id) 없으면 → `st.switch_page("app.py")` 자동 리다이렉트. 오류 메시지 + `st.stop()` 는 개발자용 fallback 만.

### 원칙 P4 — 페이지 진입 헬퍼 통합
현재 각 페이지가 `_get_param` 및 세션 세팅을 개별 구현. 다음 헬퍼로 통일:
```python
# services/page_context.py (신규)
def bootstrap_page_context(required=("user_id",)) -> dict:
    """페이지 진입 시 URL/세션에서 컨텍스트 획득 + 유실 시 로그인 리다이렉트."""
    qp = st.query_params
    ctx = {
        "user_id": qp.get("user_id") or st.session_state.get("user_id", ""),
        "mode": (qp.get("mode") or st.session_state.get("mode", "TEST")).upper(),
        "strategy_type": (qp.get("strategy_type") or st.session_state.get("strategy_type", "EMA")).upper(),
        ...
    }
    # 필수 체크
    for k in required:
        if not ctx.get(k):
            st.warning(f"세션이 만료되었습니다. 로그인 페이지로 이동합니다.")
            st.switch_page("app.py")
            st.stop()
    # 세션·URL 이중 저장
    for k, v in ctx.items():
        st.session_state[k] = v
    return ctx
```

### 원칙 P5 — 페이지 이동 헬퍼 통합
```python
# services/page_context.py (동일 파일)
def navigate_to(target_page: str, **params) -> None:
    """페이지 이동 표준 방법 — session_state 세팅 + query_params 세팅 + switch_page."""
    for k, v in params.items():
        st.session_state[k] = v
    st.query_params.update(params)
    st.switch_page(target_page)
```

---

## 7. 수정 대상 파일 · Sub-Phase 초안 (Phase B 상세 기획 예정)

| Sub-Phase | 대상 파일 | 변경 |
|---|---|---|
| **SP-NAV-1** | `services/page_context.py` (신규) | bootstrap_page_context + navigate_to 헬퍼 |
| **SP-NAV-2** | `pages/dashboard.py` | 진입 시 bootstrap 사용, 5개 이동 지점 navigate_to 로 통일 |
| **SP-NAV-3** | `pages/audit_viewer.py` | 진입·이동 통일 |
| **SP-NAV-4** | `pages/settings_history.py` | 진입·이동 통일, 대시보드 이동 시 세션 재세팅 (F4) |
| **SP-NAV-5** | `pages/set_config.py`, `set_buy_sell_conditions.py`, `confirm_init_db.py` | 진입·이동 통일 (meta refresh → navigate_to) |
| **SP-NAV-6** | `app.py` | 인증 상태 없이 페이지 직접 접근 시 대응 (P3 리다이렉트) |

---

## 8. 감사 완료 상태

- **감사 항목**: 페이지 7개 진입점 + 이동 지점 15개 전수 조사
- **확정 결함**: F1~F5 (5건)
- **근본 원칙**: P1~P5 도출
- **본 지도**: Phase B 통합 수정 기획안 근거 자료

**감사 완료 시각**: 2026-07-03 21:40 KST
