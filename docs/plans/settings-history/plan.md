# 설정 정보 History 구축 기획안

**작성일**: 2026-06-15
**작성자**: Claude (사용자 요청에 따른 분석/제안)
**상태**: 초안 — 결정 항목 5건 사용자 승인 대기

---

## 1. WHY (목적)

사용자가 트레이딩 봇의 설정(전략 파라미터·매수/매도 조건)을 변경할 때마다 그 시점의 스냅샷을 누적 보관하고, 별도 페이지에서 시계열로 조회할 수 있도록 한다.

### 해결 문제
- **현재**: 설정 JSON 파일이 매 저장 시 덮어쓰기되어 과거 설정이 소실됨
- **결과**: "이전에 어떤 값을 썼었는지" 추적 불가 → 성과 비교/회귀 분석/사후 디버깅 어려움
- **추가**: 무엇이 언제 어떻게 바뀌었는지 감사 추적(audit trail)이 부재

### 기대 효과
- 설정 변경 이력의 영구 보관 → 회귀 분석 가능
- 사고/이상 발생 시 "그 시점의 설정"으로 원인 추적 가능
- 추후 "이전 시점으로 복원" 기능의 기반 마련

---

## 2. WHAT (요구사항)

사용자 원문(2026-06-15 작업 지시):

> 1. 사용자가 설정 정보 저장 시 해당 정보를 기록 or 저장한다.
> 2. 해당 설정 정보를 확인할 수 있는 뷰어를 독립된 페이지에서 보여준다.
> 3. (대시보드에 설정 History 보기 버튼 클릭 시 해당 페이지 이동)

### 도출된 요구사항
| ID | 요구 | 우선순위 |
|---|---|---|
| R1 | 사용자가 설정을 저장하는 모든 트리거 지점에서 스냅샷이 적재된다 | MUST |
| R2 | 독립된 Streamlit 페이지에서 시계열 조회 가능 | MUST |
| R3 | 대시보드에 진입 버튼이 추가되어 한 클릭으로 페이지 이동 | MUST |
| R4 | 사용자별 격리(다중 사용자 환경) | MUST |
| R5 | 전략/기간/페이지별 필터링 | SHOULD |
| R6 | 행 펼치기 / 다운로드 | SHOULD |
| R7 | 이전 행 대비 변경분(diff) 시각화 | NICE |
| R8 | "이 시점으로 복원" 버튼 | NICE (별도 작업) |

---

## 3. AS-IS (현 저장 흐름 분석)

### 3-1. 설정 저장 트리거 (2곳)

| 페이지 | 함수 | 출력 파일 | 트리거 |
|---|---|---|---|
| `pages/set_config.py:283` | `save_params(params, json_path, strategy_type)` | `{user_id}_mcmax33_latest_params_{STRATEGY}.json` | 사이드바 "💾 저장" |
| `pages/set_buy_sell_conditions.py:710` | `save_conditions()` + 조건부 `save_params()` | `{user_id}_{STRATEGY}_buy_sell_conditions.json` (+ params 파일 갱신 가능) | "💾 설정 저장" 버튼 |

### 3-2. 저장 단위 (snapshot 단위)

- **params**: LiveParams 모델 (ticker, ema_fast/slow, take_profit, stop_loss, risk_pct 등)
- **conditions**: buy/sell 토글 + Surge/Stale/TP/SL/Trailing 파라미터

### 3-3. 파일 간 결합도

- `set_buy_sell_conditions`에서 ticker/TP/SL 변경 시 `params` 파일도 동시에 갱신됨 (set_buy_sell_conditions.py:262-291)
- **한 번의 사용자 저장 액션 = 두 파일이 동시에 바뀔 수 있음** → 스냅샷도 그 액션을 1행으로 묶어 보관해야 일관성 유지

### 3-4. 페이지/네비게이션 구조

- Streamlit 멀티페이지 (`pages/{name}.py` + `app.py`)
- 페이지 이동: `st.switch_page("pages/{file}.py")`
- 기존 패턴: `pages/audit_viewer.py` — URL query params / session_state 기반 진입 + 사이드바 숨김 + 헤더/필터/탭/표
- DB 접근: 사용자별 SQLite `<user_id>.db`, `get_db(user_id)` 헬퍼

---

## 4. 설계 선택지 비교

| 안 | 저장소 | 장점 | 단점 |
|---|---|---|---|
| **A (권장)** | DB 신규 테이블 `settings_history` | 사용자 격리 자연, SQL 필터·정렬·페이징, orders/logs와 일관 패턴 | 스키마 1개 추가 |
| B | 타임스탬프 JSON 파일 (`settings_history/{user_id}/{ts}_{kind}.json`) | 파일 그대로 보관, 외부 도구 호환 | 디렉토리/IO 증가, 정렬·검색 직접 구현, 사용자별 격리 수동 |
| C | 하이브리드 (DB 메타 + JSON 파일 본문) | 큰 JSON 안전 | 2채널 동기화 부담 |

**권장: A** — 기존 `orders` / `logs` 패턴과 일치하므로 `services/db.py` / `pages/audit_viewer.py` 코드를 그대로 모사 가능.

---

## 5. TO-BE 설계 (A안 상세)

### 5-1. DB 스키마 (services/db.py `ensure_schema` 확장)

```sql
CREATE TABLE IF NOT EXISTS settings_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    saved_at        TEXT NOT NULL,           -- KST ISO8601
    source_page     TEXT NOT NULL,           -- 'set_config' | 'set_buy_sell_conditions'
    strategy_type   TEXT NOT NULL,           -- 'MACD' | 'EMA'
    params_json     TEXT,                    -- LiveParams snapshot
    conditions_json TEXT,                    -- buy/sell conditions snapshot
    app_version     TEXT,                    -- 'v1.YYYY.MM.DD.HHMM'
    note            TEXT                     -- 향후 사용자 메모용 (현재 NULL)
);
CREATE INDEX IF NOT EXISTS idx_settings_history_user_saved
    ON settings_history(user_id, saved_at DESC);
```

### 5-2. 신규 모듈 `services/settings_history.py`

핵심 함수 시그니처:

```python
def record_snapshot(user_id: str, source_page: str, strategy_type: str, *, note: str | None = None) -> int:
    """현 사용자/전략 설정 파일을 읽어 한 행으로 적재. id 반환."""

def seed_initial_snapshot(user_id: str, strategy_type: str) -> int | None:
    """
    P1 마이그레이션 직후 1회 호출.
    settings_history 가 비어 있는 사용자/전략 조합에 대해
    현재 파일 상태(params + conditions)를 source_page='initial_seed'
    note='P1 자동 시드' 로 적재한다. 이미 row 가 있으면 skip.
    이 row 가 첫 active_settings_id 가 된다.
    """

def fetch_history(user_id: str, *, strategy_type: str | None = None,
                  source_page: str | None = None, limit: int = 100,
                  since_ts: str | None = None) -> list[dict]:
    """필터 기반 시계열 조회."""

def fetch_snapshot(snapshot_id: int) -> dict | None:
    """단일 스냅샷 상세 조회."""

def diff_against_previous(snapshot_id: int) -> dict:
    """직전 동일(user, strategy) 스냅샷과 컬럼별 변경분."""
```

### 5-3. 저장 사이트에 record_snapshot 호출 추가 (총 2곳)

- `pages/set_config.py:283` — `save_params(...)` 직후
  ```python
  save_params(params, json_path, strategy_type=selected_strategy_type)
  record_snapshot(user_id, "set_config", selected_strategy_type)
  ```
- `pages/set_buy_sell_conditions.py:710` — `save_conditions()` 직후
  ```python
  save_conditions()
  record_snapshot(user_id, "set_buy_sell_conditions", strategy_tag)
  go_dashboard()
  ```

### 5-4. 신규 페이지 `pages/settings_history.py`

레이아웃 (audit_viewer.py 패턴 모사):

```
📜 설정 History
─────────────────────────────────────────
[필터바]
  전략: [All / MACD / EMA]
  기간: [전체 / 최근 7일 / 30일]
  페이지: [All / set_config / set_buy_sell_conditions]
  표시 행수: [50 / 100 / 200]

[테이블 — 최신순]
  시간(KST)            | 전략 | 페이지                  | 앱 버전          | 상세
  2026-06-15 20:33:52  | EMA  | set_buy_sell_conditions | v1.2026.06.15.2020 | [펼치기▶]
  ...

[행 펼치기]
  좌: params snapshot (JSON pretty)
  우: conditions snapshot (JSON pretty)
  하단: 이전 행 대비 변경분 요약 (P3 단계)

[하단]
  📥 CSV 다운로드   📥 JSON 다운로드
```

진입: `st.switch_page("pages/settings_history.py")` + session_state(`user_id`, `mode`, `strategy_type`) 전달
사이드바: 숨김 (audit_viewer 패턴)

### 5-5. 대시보드 진입 버튼

`pages/dashboard.py` 의 적절한 위치(권장: "⚙️ Option 기능" 섹션)에:

```python
if st.button("📜 설정 History 보기", use_container_width=True):
    st.session_state["user_id"] = user_id
    st.session_state["mode"] = mode
    st.session_state["strategy_type"] = strategy_tag
    st.switch_page("pages/settings_history.py")
```

URL 파라미터 대신 session_state 전달 권장 — Issue #14 동기화 패턴 활용.

---

## 6. 분리 작업 패키지 (Phase)

⚠️ §10-6 (고도화안)에서 최종 Phase 표를 갱신함 — 본 §6은 초안 단계 메모로 보관.
최종은 §10-6 참고.

| Phase | 작업 | 영향 | dashboard.py 버전 |
|---|---|---|---|
| **P1 (기반)** | DB 스키마 + `services/settings_history.py` 신규 + 2곳 record_snapshot 호출 + 시드 스냅샷 | 저장 단방향, UI 영향 없음 | 갱신 (런타임 변경) |
| **P2 (뷰어)** | `pages/settings_history.py` 신규 + 대시보드 진입 버튼 | 사용자 가시 | 갱신 |
| **P3 (선택/추후)** | 행 펼치기 diff 시각화 / CSV·JSON 다운로드 / "이 시점으로 복원" | 추가 기능 | 갱신 |

**권장 진행 순서**: P1 → 배포 → 데이터 누적 → P2 → 배포 → 사용 검증 → 필요 시 P3.
**근거**: P2를 만들 때 표시할 데이터가 이미 누적되어 있어야 UI 검증이 의미 있음.

---

## 7. 결정 필요 항목 (사용자 승인)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| D1 | 저장 방식 | A(DB) / B(JSON 파일) / C(하이브리드) | **A** |
| D2 | 저장 단위 | 사용자 저장 액션 1회 = 1행 / 트리거 페이지별 분리 행 | **1행 통합** |
| D3 | 대시보드 진입 버튼 위치 | (a) "⚙️ Option 기능" 섹션 / (b) 상단 헤더 옆 | **(a)** |
| D4 | Phase 진행 방식 | P1 → 배포 → P2 순차 / P1+P2 한 번에 | **순차** |
| D5 | 보존 기간 | 무제한 / N일 자동 정리 옵션 | **무제한 (orders/logs와 동일)** |

---

## 8. 영향 받는 파일 (예상)

### P1
- `services/db.py` — `ensure_schema` 확장
- `services/settings_history.py` — 신규
- `pages/set_config.py` — `record_snapshot` 호출 1줄
- `pages/set_buy_sell_conditions.py` — `record_snapshot` 호출 1줄
- `pages/dashboard.py` — 버전 갱신

### P2
- `pages/settings_history.py` — 신규
- `pages/dashboard.py` — 진입 버튼 + 버전 갱신

### P3 (추후)
- `pages/settings_history.py` — diff/다운로드 추가
- (옵션) services/settings_history.py — `restore_snapshot()` 추가
- `pages/dashboard.py` — 버전 갱신

---

## 9. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-15 20:45 | 초안 작성 | 결정 항목 5건 사용자 승인 대기 |
| 2026-06-15 21:05 | 고도화안 추가 (§10) | "설정→거래 추적" 통합 설계, 결정 항목 D6~D10 추가, Phase P1~P5로 재조정 |
| 2026-06-16 09:** | 설정 불러오기(Restore) 기능 추가 (§10-11) | R13~R17, 결정 항목 D11~D13, Phase에 P4(복원) 신규 권장 |
| 2026-06-16 09:30 | 백필 P2 제거 + 초기 시드 스냅샷 도입 + 복원 P3 격상 | §10-3 §10-6 §10-7 §10-9 §10-11-8 갱신, D10 삭제, D11 확정 (b) |
| 2026-06-16 14:30 | data-baseline 측정 완료 | mcmax33 활성 / 187 audit_trades / 31,113 audit_settings / BUY FILLED-SELL FILLED 불일치 발견 — §10-9 PnL 계산은 audit_trades 우선 명문화 |
| 2026-06-16 15:25 | §10-4 승률 표기 정책 추가 + §10-5 행 요약 컬럼 "승률 (수익/손해)" 형식 확정 | flat(무손익) 별도 분리, 청산 0건은 `-`, 표본 크기 가시화 |
| 2026-06-16 16:55 | P1+P2+P3+P4+P5 로컬 구현·검증 완료 | 13 files 변경 / 2 신규. 시드 + 라벨링 + 뷰어 + 복원 + PnL + diff + 다운로드 통합. 배포는 단일 완성본 정책에 따라 사용자 최종 승인 후 |

---

## 10. 고도화 — 설정별 거래 성과(수익/손해) 추적

### 10-1. 추가 요구사항 (사용자 원문 2026-06-15)

> 추후 해당 설정으로 얼마나 수익/손해 등 거래내역을 추적할 수 있어야 한다.

도출:
- R9: 각 설정 스냅샷에 묶인 실거래의 실현 손익을 산출할 수 있다 (MUST)
- R10: 각 설정 스냅샷에 묶인 거래 건수·승률·평균 보유 기간을 산출할 수 있다 (SHOULD)
- R11: 현재 활성 스냅샷은 미실현 손익도 함께 표시 (NICE)
- R12: 각 행 펼치기 시 그 구간의 거래 리스트를 볼 수 있고, audit_viewer로 점프 가능 (SHOULD)

### 10-2. 활용 가능한 기존 인프라

| 테이블 | 정의 위치 | 핵심 컬럼 | 본 작업과의 관계 |
|---|---|---|---|
| `audit_trades` | services/init_db.py:297 | timestamp, bar_time, ticker, type(BUY/SELL), price, **entry_price, entry_bar, bars_held**, tp, sl, highest | PnL 계산의 1차 원천 |
| `audit_settings` (기존) | services/init_db.py:326 | timestamp, ticker, tp, sl, ts_pct, signal_gate, buy_json, sell_json | **엔진 시작 시점** 자동 스냅샷 (`insert_settings_snapshot`). 본 작업의 `settings_history`(사용자 명시 저장)와 역할 다름 → **별개 유지** |
| `orders` | services/init_db.py | uuid, side, price, volume, paid_fee, state, executed_at, meta | 체결 수량·수수료 확보용 (audit_trades에 volume 없음 → JOIN 필요) |

### 10-3. 거래 라벨링 방식 (스냅샷 ↔ 거래 매핑)

| 옵션 | 방법 | 장단점 |
|---|---|---|
| **① (권장)** | **실시간 라벨링**: `orders` / `audit_trades` 에 `settings_history_id INTEGER NULL` 컬럼 추가. 엔진 메모리에 `active_settings_id` 유지(record_snapshot 시 갱신), 신규 BUY/SELL INSERT 시 함께 적재 | 정확·조회 빠름. 컬럼 추가 필요 |
| ② | **사후 시각 JOIN**: 스키마 변경 없음. `WHERE settings_history.saved_at <= trade.ts < next_saved_at` | 변경 ↓, 시간 경계 부정확, 인덱스 의존 |
| ③ | 하이브리드 (신규 ①, 과거 ②) | 안전하나 복잡 |

추천: **①**.

**과거 거래 처리 방침** (2026-06-16 결정):
- 백필은 **수행하지 않는다**. P1 이전에는 사용자 명시 스냅샷이 DB에 존재하지 않으므로 매핑할 정답이 없음.
- P1 이전의 거래는 `settings_history_id IS NULL` 인 **"Pre-history"** 그룹으로 유지하고, UI에서 별도 섹션 또는 "이전 거래" 라벨로 표기.
- P1 배포 직후 각 사용자/전략 조합에 대해 **시드 스냅샷 1개**(`source_page="initial_seed"`)를 자동 적재 → 사용자 첫 저장 전 거래는 시드 row 에 자동 묶임.

### 10-4. PnL / 통계 계산 정의

각 `settings_history` 행에 대해:

```
유효 구간 = saved_at ~ NEXT(saved_at, 같은 user/strategy)   # 없으면 NOW
구간 거래 = audit_trades WHERE timestamp ∈ 유효 구간 AND user_id=?
페어링   = 동일 ticker, BUY → 가장 가까운 SELL (FIFO)

실현 손익(KRW) = SUM((sell.price - buy.entry_price) * volume - paid_fee)

# 청산 거래 단위 결과 분류
수익 횟수 (win)   = COUNT(sell.price > buy.entry_price)
손해 횟수 (loss)  = COUNT(sell.price < buy.entry_price)
무손익 횟수 (flat)= COUNT(sell.price = buy.entry_price)   # 통계상 별도 분리
청산 횟수        = win + loss + flat

승률             = win / (win + loss)          # flat 제외 — 순수 결과 비교
표시 형식         = f"{승률*100:.0f}% ({win}/{loss})"     # 예: "60% (3/2)"

평균 보유        = AVG(bars_held)   # SELL 행 기준 — 현장 측정 시 100% 정상

미실현 손익(KRW) = (현재가 - 평단) * 현재 보유 qty   # 활성 구간만
```

`volume`·`paid_fee` 는 audit_trades 단독으로 부족 → `orders` 와 uuid 또는 시각으로 JOIN.

🔍 **승률 표기 정책 (2026-06-16 사용자 결정)**:
- 단순 % 만 표시하지 않고 **"% (수익/손해)"** 형식 병기.
- 청산 횟수가 적을 때(예: 1건) % 만 보이면 오해 소지 — 분자/분모를 함께 보여줘 정확한 표본 크기 인지.
- flat(무손익)은 표기에서 제외하되 0건이 아닐 경우 행 펼치기 상세에서 별도 표시.
- 청산 0건: 승률 컬럼은 `"-"` 로 표시.

### 10-5. UI 확장 (settings_history 페이지)

행 요약 컬럼:

| 시간(KST) | 전략 | 페이지 | 앱 버전 | 유효 구간 | 실현 손익 | 거래(B/S) | 승률 (수익/손해) | 평균 보유 |
|---|---|---|---|---|---|---|---|---|
| 2026-06-15 20:33 | EMA | set_buy_sell_conditions | v1.2026.06.15.2020 | 1h 23m (활성) | +12,340원 | 3/2 | **60% (3/2)** | 12분 |
| 2026-06-15 18:10 | EMA | set_config | v1.2026.06.15.2007 | 2h 23m | -3,400원 | 5/5 | **40% (2/3)** | 8분 |
| 2026-06-15 17:00 | EMA | set_config | v1.2026.06.15.1700 | 1h 10m | - | 0/0 | **-** | - |

- "거래(B/S)" 컬럼: 구간 내 발생한 BUY 시도 수 / SELL 체결 수
- "승률 (수익/손해)" 컬럼: §10-4 정의대로 `f"{pct}% ({win}/{loss})"`. 청산 0건이면 `-`
- "평균 보유": SELL 행의 `bars_held` 평균 → "N분" 또는 "N시간 M분" 자연어 포맷
- 음수 실현 손익은 빨강, 양수는 초록 (st.dataframe column_config 또는 st.markdown HTML)

행 펼치기 (탭/컬럼):
- 좌: params · conditions JSON pretty
- 우: 그 구간 거래 리스트 (BUY/SELL 페어 손익 표 + audit_viewer 링크)
- 하단: 직전 행 대비 변경분 요약
- 무손익(flat) 거래가 있을 경우 별도 카운트 표기 (예: "기타: flat 1건")
- (선택) 누적 손익 시계열 미니 차트

### 10-6. Phase 재조정 (최종)

(2026-06-16 갱신: 백필 P2 제거 + 복원 P3 격상)

| Phase | 작업 | 영향 |
|---|---|---|
| **P1 (기반)** | `settings_history` 테이블 + `services/settings_history.py` + 2곳 record_snapshot + 시드 스냅샷 1회 적재 + 엔진 메모리 `active_settings_id` 유지 + `orders` / `audit_trades` 에 `settings_history_id` ALTER + 신규 INSERT 경로에 id 적재 | DB 스키마 ↑ |
| **P2 (뷰어 기본)** | `pages/settings_history.py` 신규 + 대시보드 진입 버튼 + 유효 구간/메타 컬럼 | UI |
| **P3 (복원)** | 행 단위 "📥 불러오기" 버튼 + 자동 사전 스냅샷 + 복원 이벤트 row + active_id 갱신 채널 + Telegram 알림 (§10-11) | UI + 엔진 갱신 채널 |
| **P4 (PnL 통합)** | 각 행 컬럼 확장 (실현 손익·B/S·승률·평균 보유) + 펼치기 거래 리스트 + 활성 행 미실현 손익 | UI (성능 주의) |
| **P5 (선택)** | diff 시각화 / 누적 손익 그래프 / audit_viewer ↔ settings_history 상호 링크 / 다운로드 | 가치추가 |

분리 근거:
- **P2 / P3 분리**: P2 는 조회 단방향, P3 는 파일 덮어쓰기 + 엔진 갱신을 동반하므로 안전 장치 검증 분리.
- **P3 / P4 분리**: P4 는 집계 — 성능·정합 검증 분리 필요.

**제거된 Phase (구 P2 백필)**: 사용자 명시 스냅샷이 P1 이전에 존재하지 않으므로 매핑할 정답이 없음. Pre-history 그룹 + 시드 스냅샷으로 대체.

### 10-7. 영향 받는 파일 (최종, §8 대체)

#### P1
- `services/init_db.py` — `settings_history` 테이블 + 인덱스, `orders` / `audit_trades` 에 `settings_history_id` ALTER
- `services/db.py` — `ensure_schema` 갱신, `insert_order` / `insert_audit_trade` 시그니처에 `settings_history_id` 추가
- `services/settings_history.py` — 신규 (`record_snapshot`, `seed_initial_snapshot`, `fetch_history`, `fetch_snapshot`, `diff_against_previous`, `get_active_settings_id`)
- `engine/live_loop.py` 또는 `core/strategy_engine.py` — 엔진 시작 시 `active_settings_id` 로딩 (없으면 `seed_initial_snapshot` 호출), 새 record_snapshot 발생 시 갱신 채널
- `pages/set_config.py`, `pages/set_buy_sell_conditions.py` — `record_snapshot` 호출 추가
- `pages/dashboard.py` — 버전 갱신

#### P2 (뷰어 기본)
- `pages/settings_history.py` — 신규 (조회 + 시드 row 식별 표기 + Pre-history 거래 카운트 영역)
- `pages/dashboard.py` — 진입 버튼 + 버전 갱신

#### P3 (복원)
- `services/settings_history.py` — `restore_snapshot()` 추가 (§10-11-6)
- `services/db.py` — `latest_active_settings` 테이블 또는 settings_history 의 가장 최신 active row 조회 헬퍼
- `pages/settings_history.py` — "📥 불러오기" 버튼 + 확인 다이얼로그 + diff 미리보기
- `engine/live_loop.py` 또는 `core/strategy_engine.py` — `active_settings_id` 핫리로드 채널
- `pages/dashboard.py` — 버전 갱신

#### P4 (PnL 통합)
- `services/settings_history.py` — `compute_pnl_for_snapshot()` 추가
- `pages/settings_history.py` — 컬럼/펼치기 확장

#### P5 (선택)
- `pages/settings_history.py` + `pages/audit_viewer.py` — 상호 링크, diff 시각화, 누적 손익 차트, 다운로드

### 10-8. 결정 필요 항목 (D6 ~ D9, §7 확장)

| # | 항목 | 옵션 | 추천 / 결정 |
|---|---|---|---|
| D6 | 거래 라벨링 방식 | ① 실시간만 / ② 사후 JOIN / ③ 하이브리드 | **①** |
| D7 | 성과 지표 범위 | (a) 실현 손익만 / (b) 실현+승률+보유 / (c) (b)+미실현+MDD | **(b)** (P4) |
| D8 | 기존 `audit_settings` 관계 | 통합 / 별개 유지 | **별개 유지** (역할 다름) |
| D9 | audit_viewer ↔ settings_history 상호 링크 | YES / NO | **YES (P5)** |
| ~~D10~~ | ~~백필 스크립트 배포 형태~~ | — | **삭제 (2026-06-16) — 백필 자체 미수행** |

### 10-9. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| **`orders.state` 정합 어긋남** (현장 측정 2026-06-16: BUY FILLED 1건 vs SELL FILLED 53건) | orders.state='FILLED' 만으로는 BUY↔SELL 페어링 불가능 → PnL 부정확 | PnL 계산은 **`audit_trades` 우선** (type='SELL' 행이 entry_price·bars_held 100% 보존). `orders` 는 volume·paid_fee 조회 보조용으로만 사용 |
| `audit_trades` 컬럼에 volume·paid_fee 없음 | PnL 정확도 ↓ | `orders` 와 uuid/시각 JOIN (보조). JOIN 실패 시 PnL은 NULL 처리(표시: "-")하고 거래 건수·평균 보유만 표시 |
| `audit_trades` 에 `user_id` 컬럼 없음 (현장 측정으로 확인) | 다중 사용자 운영 시 격리 모호 | 사용자별 DB 파일 분리(`tradebot_<user_id>.db`)로 격리됨 — 신규 `settings_history` 도 동일 패턴 |
| 엔진 미실행 중 사용자가 설정 저장 | active_settings_id 갱신 채널 없음 | record_snapshot 시 DB에 row 적재, 엔진 시작 시 최신 row id를 DB에서 로드 |
| 다중 사용자에서 active_settings_id 충돌 | 사용자 격리 실패 | active_settings_id 는 user_id 별로 메모리 dict / DB row 단위로 관리 |
| 시드 스냅샷 누락 (P1 마이그레이션 실패) | 첫 거래가 NULL 라벨 | 엔진 시작 루틴에서 settings_history 비어있으면 `seed_initial_snapshot` 자동 호출 (idempotent) |
| Pre-history 거래 라벨 NULL | 뷰어에서 표시 누락 | 뷰어 상단에 "Pre-history (P1 이전) 거래 N건" 카운트 영역으로 별도 표기. 현장 측정 결과 187건으로 단순 카운트 충분 |
| ALTER TABLE on production DB | 배포 시 락 / 마이그레이션 실패 | `_safe_alter` 패턴 (services/init_db.py:383) 따라 idempotent ALTER, 사전 DB 백업. 현장 측정 결과 orders 128행/audit_trades 187행으로 락 시간 무시 가능 |

### 10-10. 사용자 승인 대기 항목 (요약)

- §7 결정 항목 D1~D5 (기존)
- §10-8 결정 항목 D6~D9 (D10 삭제)
- §10-11 결정 항목 D11~D13 (복원 기능 — D11은 백필 제거로 추천 갱신)

승인 후 P1부터 순차 진행. 각 Phase 종료 시:
- 코드 커밋·배포
- 본 문서의 §9 진행 이력에 한 줄 추가
- 필요 시 결정 항목 사후 보정 기록

---

### 10-11. 설정 불러오기(Restore) 기능

(2026-06-16 사용자 요청으로 추가됨 — §3 R8 "이 시점으로 복원"을 NICE에서 정규 기능으로 격상)

#### 10-11-1. 사용자 원문

> 불러오기 기능은 해당 설정 History 내 설정 불러오면 현재 설정으로 사용하는 기능이다.

#### 10-11-2. 도출 요구사항

- R13: 사용자가 History 행을 선택해 그 시점의 설정을 **현재 설정으로 적용**할 수 있다 (MUST)
- R14: 복원 직전에 **현재 상태의 자동 스냅샷이 적재**되어 되돌릴 수 있다 (MUST)
- R15: 복원 동작 자체도 `settings_history`에 새 row로 기록되어 추적 가능하다 (MUST)
- R16: 엔진이 실행 중이면 복원 시점을 인지하고 `active_settings_id` 를 갱신한다 (MUST)
- R17: 복원 후 사용자에게 어떤 항목이 어떻게 바뀌었는지 diff를 보여준다 (SHOULD)

#### 10-11-3. 동작 흐름

```
[사용자] History 행 N의 "📥 이 설정 불러오기" 버튼 클릭
   │
   ├─ 확인 다이얼로그 (st.dialog 또는 expander 확인 영역)
   │     "행 N(2026-06-15 18:10, EMA, set_config)의 설정을
   │      현재 설정으로 덮어쓰기 합니다. 진행할까요?"
   │
[승인]
   │
   ├─ ① 자동 안전 스냅샷: record_snapshot(source_page="auto_pre_restore")
   │      → 현재 파일 상태를 row M으로 적재
   │      → 사고 발생 시 row M으로 다시 복원 가능
   │
   ├─ ② 파일 덮어쓰기:
   │      - {user_id}_mcmax33_latest_params_{STRATEGY}.json ← row N.params_json
   │      - {user_id}_{STRATEGY}_buy_sell_conditions.json ← row N.conditions_json
   │
   ├─ ③ 복원 이벤트 적재: record_snapshot(
   │      source_page="restore", strategy_type=row_N.strategy_type,
   │      note=f"restored_from_id={N}"
   │   )
   │      → row R 생성. R이 새로운 active_settings_id가 됨
   │
   ├─ ④ active_settings_id 갱신 채널:
   │      - DB: latest_active_settings(user_id, strategy_type, settings_history_id) UPSERT
   │      - 엔진 메모리: get_engine_state(user_id).set_active_settings_id(R)
   │        (엔진 미실행 중이면 다음 시작 시 DB에서 로드)
   │
   ├─ ⑤ Telegram 알림:
   │      LEVEL_CRITICAL
   │      title: "🔄 [LIVE 설정 복원] {ticker}"
   │      body: "row N(saved_at=…) → 현재 설정으로 적용"
   │
   └─ ⑥ UI 피드백:
         - 성공 토스트 + 변경된 항목 요약 (diff)
         - 페이지 자동 새로고침
```

#### 10-11-4. 안전 장치

| 장치 | 목적 |
|---|---|
| **자동 사전 스냅샷 (①)** | 사용자가 잘못 복원해도 즉시 직전 상태로 재복원 가능 |
| **복원 이벤트 row (③)** | 복원 자체가 추적되어 "언제 어떤 row를 복원했는지" 감사 가능 |
| **확인 다이얼로그** | 1회 명시 승인 — 우발적 클릭 방지 |
| **엔진 실행 중 보호** | 엔진이 활성 포지션을 보유 중이면 복원 차단 OR 강한 경고 |
| **전략 일치 확인** | 현재 활성 전략과 row.strategy_type 이 다르면 차단 OR 전략까지 함께 변경할지 명시 승인 |
| **체크섬/version 검증** | row.app_version 이 현재 코드 버전과 크게 다르면(메이저 차) 경고 |
| **잠금** | 복원 중 다른 저장 트리거 차단 (file lock 또는 user_id 단위 락) |

#### 10-11-5. 엣지 케이스

| 케이스 | 처리 |
|---|---|
| 활성 포지션 보유 중 복원 | 차단 또는 "포지션 보유 중 — TP/SL 변경 시 즉시 영향. 진행하시겠습니까?" 강한 경고 |
| 현재 전략(MACD)과 복원 대상(EMA) 불일치 | 별도 전략 파일이라 자동 절체 어려움. "전략까지 EMA로 전환합니다" 명시 승인 후 진행 |
| row.params_json/conditions_json 이 NULL/손상 | 차단 + 사용자 안내 ("이 행은 복원 불가") |
| 복원 직후 사용자가 set_config / set_buy_sell_conditions 으로 또 저장 | 정상 동작. 그 저장이 새 row 생성 + active_id 갱신 |
| 엔진 미실행 중 복원 | DB only 갱신. 다음 엔진 시작 시 active_settings_id 자동 로드 |

#### 10-11-6. API 추가 (services/settings_history.py)

```python
def restore_snapshot(
    snapshot_id: int,
    *,
    user_id: str,
    actor: str = "user",            # 'user' | 'system'
    require_strategy_match: bool = True,
    require_no_open_position: bool = True,
) -> dict:
    """
    snapshot_id 의 params/conditions 를 현재 파일에 덮어쓰고
    안전 스냅샷 + 복원 이벤트 row 를 적재한 뒤 active_settings_id 를 갱신한다.

    반환: {
        "pre_snapshot_id": int,    # ① 사전 스냅샷 id
        "restored_from_id": int,   # = snapshot_id
        "new_active_id": int,      # ③ 복원 이벤트 row id (= active id)
        "diff": dict,              # 변경 항목 요약 (key → before/after)
        "warnings": list[str],     # 안전 장치 발동 메시지
    }

    실패 시: 예외 발생 (RestoreError) → UI 에서 사용자 안내
    """
```

#### 10-11-7. UI 변경

- 행 단위 "📥 이 설정 불러오기" 버튼 (또는 행 펼치기 내부에 배치)
- 확인 다이얼로그(`st.dialog` 또는 expander 확인 영역) — 적용될 핵심 항목 미리보기 포함
- 복원 후 토스트 + 변경 요약(diff) 표시
- "📦 자동 사전 스냅샷 row 보기" 링크

#### 10-11-8. Phase 재배치 (확정 — 2026-06-16)

(백필 P2 제거 후 한 단계 당김)

| 옵션 | 배치 |
|---|---|
| (a) | P2(뷰어 기본)에 통합 — 뷰어 출시 시 복원도 가능 |
| (b) | **별도 P3 "복원" 신규** (확정) |
| (c) | 기존 P5(선택) 안에 포함 — NICE 그대로 유지 |

**확정: (b)** — 복원은 안전 장치 검증이 필요하므로 PnL과 분리해 단독 검증.
최종 Phase 표는 §10-6 참고 (P1 기반 → P2 뷰어 → P3 복원 → P4 PnL → P5 선택).

#### 10-11-9. 영향 받는 파일 (P3 = 복원)

- `services/settings_history.py` — `restore_snapshot()` 추가 + `latest_active_settings` 테이블 UPSERT
- `services/db.py` — `latest_active_settings` 테이블 신규 (`ensure_schema` 확장) — 또는 settings_history 의 가장 최신 active row 를 조회로 대체
- `pages/settings_history.py` — 복원 버튼 + 다이얼로그 + diff 미리보기
- `engine/live_loop.py` 또는 `core/strategy_engine.py` — `active_settings_id` 핫리로드 채널 (파일 시그널 또는 주기적 폴링)
- `pages/dashboard.py` — 버전 갱신

#### 10-11-10. 결정 필요 항목 (D11~D13)

| # | 항목 | 옵션 | 추천 / 결정 |
|---|---|---|---|
| D11 | 복원 기능 Phase 배치 | (a) P2 통합 / (b) 별도 P3 / (c) P5(NICE) | **(b) — 확정 2026-06-16** |
| D12 | 활성 포지션 보유 중 복원 | (i) 차단 / (ii) 강한 경고 후 진행 가능 / (iii) 무조건 진행 | **(ii)** |
| D13 | 전략 타입 불일치 복원 | (i) 차단 / (ii) 전략까지 전환 (강한 경고) / (iii) 차단하되 별도 "전략 전환" 버튼 제공 | **(ii)** |

