# RATIO-1 · 주문 비율 설정 이동 + 1% 옵션 추가

**작성일**: 2026-07-10
**상태**: 구현 착수 승인 (2026-07-10)
**우선순위**: 1

---

## 배경

- 현재 `order_ratio`는 `ui/sidebar.py` 사이드바 4개 버튼(10/25/50/100%)으로만 편집 가능.
- 사용자는 "설정 페이지에서 수시로 변경 가능하도록" + "1% 옵션 추가" 요청.
- 실제 페이지: `pages/set_buy_sell_conditions.py` (URL `/set_buy_sell_conditions`).

## 목표

1. `set_buy_sell_conditions.py`의 `⚙️ 전략 핵심 설정` 섹션 내 `자주 변경하는 설정` expander에 **주문 비율 선택 UI** 신설.
2. 5개 버튼(1% / 10% / 25% / 50% / 100%) 형식.
3. 기존 저장값을 읽어 해당 버튼이 선택된 상태로 렌더링.
4. 페이지 하단 기존 저장 버튼 클릭 시 params JSON에 함께 저장.

## In-scope

- `pages/set_buy_sell_conditions.py` — UI 블록 신설 (~30줄).
- 5개 버튼 렌더링, 선택 상태 표시, session_state 갱신.
- 저장 로직: 기존 params 저장 흐름에 `order_ratio` 필드 반영.
- `현재 설정 안내` `st.info` 라인에 비율 표시 추가.

## Out-of-scope (이번 라운드 절대 건드리지 않음)

- 사이드바 기존 버튼(`ui/sidebar.py CASH_OPTIONS`) 제거.
- 엔진 hot-reload (엔진 재기동 없이 즉시 반영) — 저장 후 엔진 재기동 필요는 기존 흐름 그대로.
- 슬라이더 / 직접 입력 UI.
- 감사로그에 비율 변경 이력 기록.
- admin 권한 체크, 사용자별 제한.

## 변경 파일

| 파일 | 변경 규모 |
|---|---|
| `pages/set_buy_sell_conditions.py` | ~30줄 삽입 |

## 상세 변경 (단계별)

### Step 1. UI 블록 삽입
- 위치: `st.expander("🎯 자주 변경하는 설정", expanded=True):` 내부, TP/SL `col1,col2` 이후, `st.info` 안내 라인 이전.
- 상수 정의: `RATIO_OPTIONS = [("1%", 0.01), ("10%", 0.10), ("25%", 0.25), ("50%", 0.50), ("100%", 1.0)]`.
- 5개 컬럼 버튼 (`st.columns(5)`), 클릭 시 `st.session_state["order_ratio_quick"] = value`.
- 저장값 로드: `params_obj.order_ratio` 있으면 사용, 없으면 `1.0` 기본.
- 선택된 버튼은 `type="primary"`로 강조.

### Step 2. `st.info` 안내 라인에 비율 추가
- 기존: `💰 TP: +3.0% | 🔻 SL: -1.0%`
- 신규: `... | 💰 비율: 25%`

### Step 3. 저장 로직 연결
- 페이지 하단 기존 저장 함수 (`save_conditions()`) 호출 흐름에서 `order_ratio` 값을 params JSON에 반영.
- 저장 대상 파일: `{user_id}_{PARAMS_JSON_FILENAME}` (기존 위치 그대로).

## 리스크

- **낮음**. 기존 저장 흐름 재사용, UI 위치만 이동.
- 사이드바 버튼도 그대로 있어 이중 UI 상태이지만 사용자 지시대로 유지.

## 테스트 체크리스트

- [ ] 페이지 진입 시 저장된 비율이 강조 표시된다.
- [ ] 각 버튼(1/10/25/50/100%) 클릭 후 상태 변경이 즉시 화면에 반영된다.
- [ ] 저장 후 JSON 파일에 `order_ratio: 0.01` 등 정확한 값이 기록된다.
- [ ] 페이지 재진입 시 저장된 값이 유지된다.
- [ ] `py_compile pages/set_buy_sell_conditions.py` 통과.

## 배포

- 로컬 구현 → py_compile → `pages/dashboard.py` 버전 갱신 → 커밋 → 사용자 승인 후 서버 배포.

## 롤백

- Git revert 1건.
