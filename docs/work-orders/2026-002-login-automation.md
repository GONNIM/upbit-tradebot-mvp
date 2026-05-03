# WO-2026-002: 로그인 프로세스 자동화 및 UX 개선

**작성일**: 2026-04-30
**작성자**: CTO Assistant (Claude Code)
**상태**: 설계 완료 (구현 대기)
**우선순위**: P0 (사용자 클레임 대응)

---

## Executive Summary

### 비즈니스 문제
- **사용자 클레임**: "로그인할 때마다 계좌검증, 운용자산 저장을 반복해야 하는 불편"
- **영향**: LIVE 모드 진입 시 **3단계 수동 작업** 필요 (로그인 → 계좌검증 → 운용자산 저장 → 입장)
- **근본 원인**: 자동화 플래그(`_auto_checked_in_live`) 존재하지만 실제 활용 안 됨

### 해결 방향
1. **LIVE 모드 자동 계좌검증**: 모드 전환 시 자동으로 Upbit API 호출 및 DB 동기화
2. **운용자산 자동 설정**: 계좌검증 성공 시 즉시 `virtual_krw = live_krw_balance` 설정
3. **파라미터 설정 페이지 접근성 개선**: 검증 조건 완화 (경고만 표시)

### 기대 효과
- 사용자 클릭 횟수: **3회 → 0회** (100% 자동화)
- LIVE 모드 진입 시간: **~30초 → ~5초** (80% 단축)
- UX 만족도: 클레임 해결 및 운영 효율성 향상

---

## 1. 문제 정의 (As-Is 분석)

### 1.1 현재 LIVE 모드 진입 프로세스

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 로그인 (app.py)                                     │
│   - 사용자 ID/PW 입력                                       │
│   - LIVE 모드 토글 ON                                       │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 계좌검증 (app.py:253-309) ⚠️ 수동                   │
│   - "계정 검증 실행" 버튼 클릭                               │
│   - validate_upbit_keys() API 호출                          │
│   - live_krw_balance 저장                                   │
│   - upbit_verified = True                                   │
│   - DB 잔고 동기화 (update_account_from_balances)           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 운용자산 설정 (app.py:341-392) ⚠️ 수동              │
│   - number_input으로 운용자산 입력 (기본값: 전체 잔고)      │
│   - "LIVE 운용자산 저장하기" 버튼 클릭                      │
│   - virtual_krw 저장                                        │
│   - save_user() DB 저장                                     │
│   - live_capital_set = True                                 │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 입장 (app.py:399-403)                               │
│   - "입장하기" 버튼 클릭                                    │
│   - dashboard 페이지로 이동                                 │
└─────────────────────────────────────────────────────────────┘

총 클릭 횟수: 3회 (검증 + 저장 + 입장)
총 소요 시간: ~30초
```

### 1.2 코드 레벨 분석

#### A. 자동검증 플래그 존재하지만 미활용

**파일**: `app.py`

**플래그 정의** (라인 77, 211):
```python
st.session_state.setdefault("_auto_checked_in_live", False)

# 모드 변경 감지
if mode_changed:
    st.session_state["_auto_checked_in_live"] = False  # 플래그 초기화
    st.session_state["_last_mode"] = current_mode
```

**문제점**:
- 플래그는 **선언만** 되고 실제 자동검증 로직 **미구현**
- 모드 전환 감지(`mode_changed`)는 되지만 검증 트리거 없음

#### B. 운용자산 저장 2단계 작업

**계좌검증** (app.py:268-309):
```python
if do_verify:  # ⚠️ 수동 버튼 클릭
    ok, data = validate_upbit_keys(ak, sk)
    if ok:
        st.session_state.upbit_verified = True
        st.session_state.live_krw_balance = krw_balance  # KRW 잔고만 저장
        st.session_state.live_capital_set = True  # ✅ True 설정
        # ❌ virtual_krw는 설정 안 됨!
```

**운용자산 저장** (app.py:379-392):
```python
if save_live_capital:  # ⚠️ 수동 버튼 클릭
    st.session_state.virtual_krw = live_capital  # ✅ virtual_krw 설정
    save_user(user_id, name, live_capital)  # DB 저장
```

**문제점**:
- `live_capital_set`은 검증 시 `True`가 되지만 `virtual_krw`는 별도 설정 필요
- 대부분 사용자는 **전체 잔고를 운용자산으로 사용**할 것으로 예상
- 불필요한 **2단계 작업**

#### C. 파라미터 설정 페이지 접근 제한

**파일**: `pages/set_config.py` (라인 112-122)

```python
if mode == "LIVE":
    if not upbit_ok or not capital_ok:
        st.error("LIVE 모드 진입 조건 미충족")
        if st.button("처음 화면으로 돌아가기"):
            st.switch_page("app.py")
        st.stop()  # ❌ 진입 차단
```

**문제점**:
- LIVE 모드에서 검증 안 하면 파라미터 설정 페이지 **진입 불가**
- 사용자는 "app.py로 돌아가기" 과정을 **"logout"**으로 오인
- 실제로는 TEST 모드로 전환하면 되지만 **UX 불편**

---

## 2. 개선안 (To-Be)

### 2.1 개선 후 프로세스

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 로그인 + 자동 검증 (app.py)                         │
│   - 사용자 ID/PW 입력                                       │
│   - LIVE 모드 토글 ON                                       │
│   ↓                                                         │
│   ✅ 자동 실행: validate_upbit_keys()                        │
│   ✅ 자동 실행: virtual_krw = live_krw_balance              │
│   ✅ 자동 실행: save_user()                                 │
│   ✅ 자동 실행: update_account_from_balances()              │
│   ✅ 성공 메시지: "자동 계좌검증 완료 (운용자산: X KRW)"     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 입장 (app.py)                                       │
│   - "입장하기" 버튼 클릭                                    │
│   - dashboard 페이지로 이동                                 │
└─────────────────────────────────────────────────────────────┘

총 클릭 횟수: 1회 (입장만)
총 소요 시간: ~5초 (검증 3초 + 클릭 2초)
개선율: 클릭 67% 감소, 시간 83% 단축
```

### 2.2 상세 개선안

#### ✅ **개선안 #1: LIVE 모드 자동 계좌검증 + 운용자산 설정**

**목표**: LIVE 모드 진입 시 자동으로 계좌검증 및 운용자산 설정

**구현 위치**: `app.py` (라인 212 직후 추가)

**구현 코드**:
```python
# 현재 코드 (라인 206-212)
current_mode = st.session_state.get("mode", "LIVE")
mode_changed = current_mode != st.session_state.get("_last_mode", "LIVE")
if mode_changed:
    st.session_state["_auto_checked_in_live"] = False
    st.session_state["_last_mode"] = current_mode

# ✅ 개선: LIVE 모드 진입 시 자동검증 + 운용자산 설정 (라인 212 직후)
if current_mode == "LIVE" and not st.session_state.get("_auto_checked_in_live"):
    ak, sk = ACCESS, SECRET
    if ak and sk:
        with st.spinner("🔄 LIVE 모드 자동 계좌검증 중..."):
            ok, data = validate_upbit_keys(ak, sk)

        if ok:
            # 1. 계좌검증 상태 저장
            st.session_state.upbit_verified = True
            st.session_state.upbit_accounts = data or []

            # 2. KRW 잔고 추출
            krw_balance = _extract_krw_balance(data)
            st.session_state.live_krw_balance = krw_balance

            # 3. ✅ 운용자산 자동 설정 (전체 잔고 사용)
            st.session_state.virtual_krw = krw_balance
            st.session_state.live_capital_set = True

            # 4. DB 저장
            save_user(username, name, krw_balance)

            # 5. DB 잔고 동기화
            try:
                from services.db import update_account_from_balances, update_position_from_balances
                update_account_from_balances(username, data)
                # 모든 코인 포지션도 동기화
                for bal in (data or []):
                    currency = bal.get("currency", "").upper()
                    if currency and currency != "KRW":
                        ticker = f"KRW-{currency}"
                        update_position_from_balances(username, ticker, data)
                logger.info(f"✅ [AUTO-VERIFY] DB 잔고 동기화 완료: user={username}")
            except Exception as e:
                logger.error(f"⚠️ [AUTO-VERIFY] DB 잔고 동기화 실패: {e}")

            # 6. 자동검증 플래그 설정
            st.session_state["_auto_checked_in_live"] = True

            # 7. 성공 메시지
            st.success(
                f"✅ 자동 계좌검증 완료\n\n"
                f"- KRW 잔고: {krw_balance:,.0f} KRW\n"
                f"- 운용자산: {krw_balance:,.0f} KRW (자동 설정)\n"
                f"- DB 동기화: 완료",
                icon="✅"
            )
        else:
            # 검증 실패
            st.session_state.upbit_verified = False
            st.session_state.upbit_accounts = []
            st.session_state.live_krw_balance = 0.0
            st.session_state.live_capital_set = False
            st.error(
                f"❌ 자동 계좌검증 실패: {data}\n\n"
                "API 키를 확인하거나 수동으로 '계정 검증 실행' 버튼을 클릭하세요.",
                icon="❌"
            )
```

**UI 변경**:
```python
# 기존 (라인 244-309): "계정 검증 실행" 버튼 유지 (수동 재검증용)
with st.container(border=True):
    st.subheader("🔐 Upbit 계정 검증 (LIVE 전용)")
    # ... 기존 UI 유지 ...

    # ✅ 자동검증 상태 표시 추가
    if st.session_state.get("_auto_checked_in_live"):
        st.info("✅ 자동 검증 완료됨 (재검증이 필요하면 아래 버튼 클릭)", icon="ℹ️")

    do_verify = st.button("계정 검증 실행 (재검증)", key="btn_verify", ...)
    # ... 기존 로직 유지 ...

# 기존 (라인 341-392): "LIVE 운용자산 설정" 섹션 제거
# ✅ 대체: 자동 설정된 운용자산 표시만
st.subheader("💰 LIVE 운용자산 (자동 설정됨)")
st.info(
    f"현재 운용자산: **{st.session_state['virtual_krw']:,.0f} KRW**\n\n"
    "계좌검증 시 Upbit KRW 잔고로 자동 설정되었습니다.\n"
    "운용자산 변경을 원하시면 파라미터 설정 페이지에서 수정 가능합니다.",
    icon="💰"
)
```

**효과**:
- ✅ 클릭 횟수: **3회 → 1회** (67% 감소)
- ✅ 소요 시간: **~30초 → ~5초** (83% 단축)
- ✅ 사용자 만족도: 클레임 해결

---

#### ✅ **개선안 #2: 파라미터 설정 페이지 접근성 개선**

**목표**: 검증 상태와 무관하게 파라미터 설정 가능 (경고만 표시)

**구현 위치**: `pages/set_config.py` (라인 112-122)

**구현 코드**:
```python
# 기존 코드
if mode == "LIVE":
    if not upbit_ok or not capital_ok:
        st.error("LIVE 모드 진입 조건 미충족")
        if st.button("처음 화면으로 돌아가기"):
            st.switch_page("app.py")
        st.stop()  # ❌ 진입 차단

# ✅ 개선: 경고만 표시하고 진행 허용
if mode == "LIVE":
    if not upbit_ok or not capital_ok:
        st.warning(
            "⚠️ LIVE 모드 진입 조건이 충족되지 않았습니다.\n\n"
            f"- upbit_verified: {upbit_ok}\n"
            f"- live_capital_set: {capital_ok}\n\n"
            "파라미터 설정은 가능하지만, 실제 LIVE 운용을 위해서는\n"
            "app.py에서 계좌검증을 먼저 완료해 주세요.",
            icon="⚠️"
        )
        # ✅ st.stop() 제거 → 진행 허용
```

**효과**:
- ✅ **logout 불필요** (app.py로 돌아갈 필요 없음)
- ✅ 파라미터 사전 설정 가능 (검증 전에도)
- ✅ UX 개선 (페이지 이동 최소화)

---

#### ⚠️ **개선안 #3: 운용자산 변경 기능 보존 (선택)**

**목표**: 자동 설정된 운용자산을 사용자가 변경 가능하도록 유지

**방안 A: 파라미터 설정 페이지에서 운용자산 변경**

이미 `pages/set_config.py`에서 `virtual_amount` 설정 가능하므로 별도 작업 불필요

**방안 B: app.py에서 간단한 변경 UI 추가 (선택)**

```python
# app.py에 추가 (라인 ~350)
st.subheader("💰 LIVE 운용자산")

col1, col2 = st.columns([3, 1])
with col1:
    st.info(
        f"현재 운용자산: **{st.session_state['virtual_krw']:,.0f} KRW**\n\n"
        "계좌검증 시 자동 설정되었습니다.",
        icon="💰"
    )
with col2:
    if st.button("변경", key="btn_change_capital"):
        # Expander 또는 다이얼로그로 변경 UI 표시
        st.session_state["show_capital_edit"] = True

if st.session_state.get("show_capital_edit"):
    new_capital = st.number_input(
        "새 운용자산 입력",
        min_value=MIN_CASH,
        max_value=int(st.session_state.get("live_krw_balance", 0)),
        value=int(st.session_state["virtual_krw"]),
        step=10_000,
    )
    if st.button("저장", key="btn_save_new_capital"):
        st.session_state.virtual_krw = new_capital
        save_user(username, name, new_capital)
        st.session_state["show_capital_edit"] = False
        st.success(f"운용자산이 {new_capital:,.0f} KRW로 변경되었습니다.")
        st.rerun()
```

**우선순위**: P2 (선택 사항)

---

## 3. 구현 계획

### 3.1 Phase 1: 핵심 자동화 (P0, 즉시)

| Task | 파일 | 라인 | 소요 시간 |
|------|------|------|----------|
| 1-A: LIVE 모드 자동검증 로직 추가 | `app.py` | 212 직후 | 30분 |
| 1-B: 운용자산 자동 설정 추가 | `app.py` | 1-A에 통합 | - |
| 1-C: UI 메시지 개선 | `app.py` | 244-392 | 15분 |
| 1-D: "LIVE 운용자산 저장" 섹션 제거 | `app.py` | 341-392 | 10분 |

**총 소요 시간**: 55분

### 3.2 Phase 2: 접근성 개선 (P1, 단기)

| Task | 파일 | 라인 | 소요 시간 |
|------|------|------|----------|
| 2-A: 파라미터 설정 페이지 접근 조건 완화 | `pages/set_config.py` | 112-122 | 10분 |
| 2-B: 경고 메시지 추가 | `pages/set_config.py` | 112-122 | 5분 |

**총 소요 시간**: 15분

### 3.3 Phase 3: 운용자산 변경 UI (P2, 선택)

| Task | 파일 | 라인 | 소요 시간 |
|------|------|------|----------|
| 3-A: app.py 운용자산 변경 UI 추가 | `app.py` | ~350 | 20분 |

**총 소요 시간**: 20분

**전체 소요 시간**: Phase 1+2 = 70분, Phase 1+2+3 = 90분

---

## 4. 테스트 계획

### 4.1 Unit Test (자동검증 로직)

**테스트 시나리오**:

```python
def test_auto_verify_on_live_mode_switch():
    """LIVE 모드 전환 시 자동검증 실행"""
    # Setup
    st.session_state["mode"] = "TEST"
    st.session_state["_auto_checked_in_live"] = False

    # Action: LIVE 모드로 전환
    st.session_state["mode"] = "LIVE"

    # Assert
    assert st.session_state["_auto_checked_in_live"] == True  # 자동검증 실행됨
    assert st.session_state["upbit_verified"] == True
    assert st.session_state["virtual_krw"] == st.session_state["live_krw_balance"]

def test_auto_verify_skip_if_already_verified():
    """이미 검증되었으면 자동검증 스킵"""
    # Setup
    st.session_state["mode"] = "LIVE"
    st.session_state["_auto_checked_in_live"] = True

    # Action: 페이지 새로고침
    # (자동검증 로직 재실행)

    # Assert
    # validate_upbit_keys() 호출 횟수 == 0 (스킵됨)
```

### 4.2 Integration Test (E2E)

**테스트 시나리오 1: 정상 흐름**

```
1. 로그인 (TEST 모드)
2. LIVE 모드 토글 ON
   → ✅ 자동검증 실행됨
   → ✅ "자동 계좌검증 완료" 메시지 표시
   → ✅ virtual_krw == live_krw_balance
3. "입장하기" 버튼 클릭
   → ✅ dashboard 페이지로 이동
```

**테스트 시나리오 2: 검증 실패**

```
1. 로그인 (TEST 모드)
2. config.py에서 잘못된 ACCESS/SECRET 설정
3. LIVE 모드 토글 ON
   → ✅ 자동검증 실행됨
   → ✅ "자동 계좌검증 실패" 에러 메시지
   → ✅ "계정 검증 실행 (재검증)" 버튼 표시
4. 수동 검증 버튼 클릭
   → ✅ 수동 검증 가능
```

**테스트 시나리오 3: 파라미터 설정 접근**

```
1. 로그인 (LIVE 모드, 검증 안 함)
2. "파라미터 설정하기" 버튼 클릭
   → ✅ 페이지 진입 가능 (기존: 차단됨)
   → ✅ 경고 메시지 표시
   → ✅ 파라미터 설정 가능
```

### 4.3 수동 테스트 체크리스트

**Phase 1 테스트**:
- [ ] LIVE 모드 전환 시 자동검증 실행 확인
- [ ] 자동검증 성공 시 `virtual_krw` 자동 설정 확인
- [ ] 자동검증 실패 시 에러 메시지 확인
- [ ] 수동 재검증 버튼 동작 확인
- [ ] "LIVE 운용자산 저장" 섹션 제거 확인
- [ ] DB 동기화 확인 (account, position 테이블)

**Phase 2 테스트**:
- [ ] 검증 없이 파라미터 설정 페이지 진입 확인
- [ ] 경고 메시지 표시 확인
- [ ] 파라미터 설정 및 저장 확인

**Phase 3 테스트** (선택):
- [ ] 운용자산 변경 UI 표시 확인
- [ ] 운용자산 변경 후 DB 저장 확인

---

## 5. 리스크 관리

### 5.1 주요 리스크

| 리스크 | 영향 | 확률 | 완화 방안 |
|--------|------|------|----------|
| **API 호출 실패** | 자동검증 실패 → 수동 검증 필요 | 중 | 에러 메시지 + 수동 검증 버튼 제공 |
| **DB 동기화 실패** | 잔고 불일치 | 낮 | try-except 처리 + 에러 로그 |
| **사용자가 운용자산 변경 못 함** | UX 불만 | 낮 | Phase 3 구현 또는 파라미터 설정 페이지 안내 |
| **session_state 초기화** | 자동검증 재실행 | 낮 | `_auto_checked_in_live` 플래그로 방지 |
| **모드 변경 감지 오류** | 자동검증 미실행 | 낮 | 단위 테스트로 검증 |

### 5.2 Rollback 계획

**트리거 조건**:
- 자동검증 실패율 > 50% (1시간 내)
- DB 동기화 실패 > 10회 (1시간 내)
- 사용자 클레임 재발생

**Rollback 절차**:
```bash
# 1. Git 이전 커밋으로 되돌리기
git revert HEAD

# 2. 서버 배포
git push
ssh root@orionhunter7.cafe24.com "cd /root/upbit-tradebot-mvp && git pull && systemctl restart streamlit"

# 3. 로그 확인
ssh root@orionhunter7.cafe24.com "tail -f /root/upbit-tradebot-mvp/logs/streamlit.log"
```

### 5.3 백워드 호환성

**✅ 보존되는 기능**:
- "계정 검증 실행" 버튼 (수동 재검증)
- 파라미터 설정 페이지 기존 기능
- TEST 모드 동작 (변경 없음)

**⚠️ 변경되는 기능**:
- "LIVE 운용자산 저장하기" 버튼 제거 (자동화)
- 파라미터 설정 페이지 진입 조건 완화

**마이그레이션 가이드** (사용자 공지):
```
📢 LIVE 모드 진입 프로세스 개선 안내

변경 전:
1. 로그인 → 2. 계좌검증 클릭 → 3. 운용자산 저장 클릭 → 4. 입장

변경 후:
1. 로그인 → 2. 입장 (자동 검증 완료)

✅ 운용자산은 Upbit KRW 잔고로 자동 설정됩니다.
✅ 변경이 필요하면 파라미터 설정 페이지에서 수정 가능합니다.
```

---

## 6. Definition of Done

### 6.1 구현 완료 기준

**Phase 1**:
- [ ] LIVE 모드 전환 시 자동검증 로직 구현 (app.py:212)
- [ ] 운용자산 자동 설정 로직 구현 (virtual_krw = live_krw_balance)
- [ ] DB 동기화 로직 구현 (update_account_from_balances)
- [ ] 성공/실패 메시지 UI 구현
- [ ] "LIVE 운용자산 저장" 섹션 제거 (app.py:341-392)
- [ ] 단위 테스트 2개 통과 (자동검증, 스킵)
- [ ] E2E 테스트 3개 시나리오 통과

**Phase 2**:
- [ ] 파라미터 설정 페이지 진입 조건 완화 (set_config.py:112-122)
- [ ] 경고 메시지 추가
- [ ] 수동 테스트 체크리스트 완료

**Phase 3** (선택):
- [ ] 운용자산 변경 UI 구현 (app.py:~350)
- [ ] 저장 로직 구현 (save_user)
- [ ] 테스트 완료

### 6.2 배포 완료 기준

- [ ] 로컬 테스트 완료 (모든 시나리오)
- [ ] Git Commit (변경 내용 명시)
- [ ] 서버 배포 (streamlit restart)
- [ ] 서버 로그 모니터링 (1시간)
- [ ] 사용자 피드백 확인

---

## 7. 결론

### 7.1 핵심 성과 (예상)

| 지표 | 기존 (As-Is) | 개선 (To-Be) | 개선율 |
|------|-------------|-------------|--------|
| **클릭 횟수** | 3회 (검증 + 저장 + 입장) | 1회 (입장만) | **67% 감소** |
| **소요 시간** | ~30초 | ~5초 | **83% 단축** |
| **사용자 만족도** | 클레임 발생 | 클레임 해결 | **100% 개선** |
| **UI 복잡도** | 3단계 | 1단계 | **67% 단순화** |

### 7.2 비즈니스 가치

1. **즉시 효과**: 사용자 클레임 해결 (P0 대응)
2. **운영 효율**: LIVE 모드 진입 시간 83% 단축
3. **UX 개선**: 불필요한 수동 작업 제거
4. **확장성**: 자동화 프레임워크 구축 (향후 개선 기반)

### 7.3 다음 단계

**CTO 의사결정 요청**:

1. **Phase 1 구현 승인 여부**:
   - [ ] 승인 (즉시 구현 시작)
   - [ ] 보류 (추가 검토 필요)

2. **Phase 2 구현 여부**:
   - [ ] Phase 1과 함께 구현
   - [ ] Phase 1 완료 후 결정

3. **Phase 3 구현 여부**:
   - [ ] 필수 (운용자산 변경 UI 필요)
   - [ ] 선택 (파라미터 설정 페이지 활용)
   - [ ] 불필요 (자동화로 충분)

**구현 일정** (승인 시):
- Phase 1: 2026-04-30 (오늘, 55분)
- Phase 2: 2026-04-30 (오늘, 15분)
- Phase 3: 2026-05-01 ~ 2026-05-02 (선택, 20분)

---

## 8. 관련 문서

- **프로젝트 규칙**: `.claude/context/project-rules.md`
- **문서 배치 규칙**: `.claude/context/document-placement-rules.md`
- **WO-2026-001**: `docs/work-orders/2026-001-confirmed-candle.md` (참고 형식)

---

**작성자**: CTO Assistant (Claude Code)
**최종 업데이트**: 2026-04-30
**버전**: v1.0 (설계 완료)

Generated with [Claude Code](https://claude.com/claude-code)
