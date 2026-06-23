# Strategy ↔ Conditions 동기화 강화 기획안

**작성일**: 2026-06-22
**작성자**: Claude (사용자 요청 — 본질적 운영 위험 제거 및 헷지)
**상태**: 초안 — 결정 항목 D1~D5 사용자 승인 대기
**배포 정책**: 메모리 규칙 `feedback_deploy_only_when_complete` 에 따라 **SP1~SP4 로컬 완료 후 단일 배포**

관련:
- [[../analysis/trading-performance/2026-06-21-krw-jto-diagnosis.md]] §11 — 본 기획의 발견 근거
- [[../settings-history/plan.md]] — 본 기획이 의존하는 P1~P5 인프라

---

## 1. WHY (목적)

진단 보고서 §11 발견:

- **사용자가 conditions 파일을 변경해도 실제 운영에는 즉시 반영 안 됨**
- 엔진(strategy 객체)은 **init 시점의 conditions 에 고정**됨
- 사용자가 명시적으로 "엔진 재시작" 트리거 한 시점에만 재초기화
- 실측 사례: 사용자 6/22 04:09 저장 → 실제 적용 6/22 12:35:58 → **8시간 27분 격차** 동안 옛 conditions 로 운영
- 운영 데이터 누적 손실 -9.78% 의 본질적 원인이 이 동기화 부재에 있음 (사용자가 의도한 임계가 아닌 옛 임계로 5일간 운영)

### 해결할 4가지 본질적 위험

| # | 위험 | 심각도 |
|---|---|---|
| ① | 사용자 변경 → 엔진 반영 격차 (8.5시간 사례) | 🔴 |
| ② | 엔진 재시작 시점이 명시적이지 않음 | 🔴 |
| ③ | UI conditions ≠ 운영 conditions — 격차 인지 불가 | 🔴 |
| ④ | settings_history saved_at vs 엔진 applied_at 추적 부재 | 🟡 |

---

## 2. WHAT (요구사항)

| ID | 요구 | 우선순위 |
|---|---|---|
| R1 | 사용자가 대시보드에서 **"엔진이 현재 적용 중인 conditions"** 를 즉시 확인 가능 | MUST |
| R2 | UI 저장 conditions 와 운영 conditions 가 **다를 때 시각적으로 명확히 구분** | MUST |
| R3 | conditions 변경 후 사용자에게 **"엔진 재시작 필요" 명시 안내** + 안전한 재시작 트리거 | MUST |
| R4 | strategy 객체 재초기화 시점이 **settings_history 에 자동 row 적재** | MUST |
| R5 | settings_history 의 row 가 **언제 엔진에 적용되었는지(`applied_at`)** 표시 | SHOULD |
| R6 | 모든 매도 거래의 audit_trades 에 **트리거 시점의 sl/tp/ts_pct 실제 임계값** 적재 (사후 분석 정확도 ↑) | SHOULD |

---

## 3. AS-IS (현재 흐름 분석)

### 3-1. conditions 파일 ↔ 엔진 흐름

```
[사용자] /set_buy_sell_conditions 페이지 변경 + 저장
   ↓
save_conditions() → mcmax33_EMA_buy_sell_conditions.json 덮어쓰기
   ↓
record_snapshot(user_id, "set_buy_sell_conditions", strategy_tag)
   ↓ (정상 적재 — settings_history.id += 1)
[settings_history] new row N (saved_at=NOW)
   ↓
[엔진 (live_loop)]
   - 매 분 [COND] loaded — audit_settings 적재용
   - strategy 객체의 self.stop_loss 등은 변경 안 됨   ❗
   ↓
[strategy 재초기화는 명시 트리거 시점에만]
   - 대시보드 "엔진 시작" 또는 systemctl restart
   - 그 시점에 conditions 파일 다시 읽고 strategy 객체 새로 생성
   - 그러면 strategy.self.stop_loss = 파일 값으로 업데이트
```

### 3-2. audit_settings 가 사실상 "운영 임계값" 추적 통로

`services/db.py:insert_settings_snapshot` 가 분당 1회 strategy 객체의 현재 임계값을 적재:

```sql
SELECT timestamp, ticker, tp, sl, ts_pct
FROM audit_settings
WHERE timestamp >= '2026-06-22T12:30';
-- → strategy.self.take_profit × 100 = tp 컬럼
-- → strategy.self.stop_loss   × 100 = sl 컬럼
```

→ 이미 데이터 통로 존재. UI 가시화만 부족.

### 3-3. 영향받는 핵심 파일

| 파일 | 현 역할 | 동기화 부재 지점 |
|---|---|---|
| `pages/set_buy_sell_conditions.py:710~` | 저장 + record_snapshot | 엔진 자동 재시작 안 함 |
| `pages/set_config.py:283~` | 저장 + record_snapshot | 동일 |
| `engine/live_loop.py:run_live_loop` | strategy 객체 1회 init | conditions 파일 변경 후 재호출 트리거 부재 |
| `services/db.py:insert_settings_snapshot` | audit_settings 분당 적재 | OK (변경 불필요) |
| `core/strategy_incremental.py:504~509` | conditions에서 임계값 로드 | OK (init 시점만) |
| `core/trader.py:_audit_emit_trade` | audit_trades 적재 | sl/tp/ts_pct 미전달 (NULL) |

---

## 4. TO-BE (Phase 설계)

### Phase SP1 — 가시화 (시급)

**대시보드에 "엔진 현재 적용 conditions" 패널 추가**.

```
┌──────────────────────────────────────────────────┐
│ 🔧 엔진 현재 적용 conditions (실시간)              │
│ ─────────────────────────────────────────────── │
│ 마지막 strategy_init: 2026-06-22 12:35:58 KST     │
│ 마지막 audit_settings: 2026-06-22 16:30:00 KST    │
│                                                  │
│ ┌──────────────────┬──────────────┬───────────┐ │
│ │ 항목             │ 엔진 적용중  │ UI 저장값 │ │
│ ├──────────────────┼──────────────┼───────────┤ │
│ │ stop_loss        │ ❌ false      │ ✅ true    │ │ ← 차이 시 색상 강조
│ │ take_profit      │ ❌ false      │ ❌ false   │ │
│ │ trailing_stop    │ ✅ true       │ ✅ true    │ │
│ │ ema_dc           │ ✅ true       │ ❌ false   │ │ ← 차이 시 색상 강조
│ │ stop_loss_pct    │ 3.0%          │ 3.0%      │ │
│ │ take_profit_pct  │ 2.5%          │ 2.5%      │ │
│ │ trailing_threshold│ 30%           │ 30%       │ │
│ └──────────────────┴──────────────┴───────────┘ │
│                                                  │
│ ⚠️ 일부 항목이 다릅니다 → 엔진 재시작 필요         │
│   [🔄 엔진 재시작]                                │
└──────────────────────────────────────────────────┘
```

**데이터 출처**:
- "엔진 적용중" = `audit_settings` 최신 row (분당 1회 적재)
- "UI 저장값" = `{user_id}_{STRATEGY}_buy_sell_conditions.json` 현재 파일

**구현 영향**:
- `services/db.py` — `fetch_latest_audit_settings(user_id)` 신규 헬퍼
- `pages/dashboard.py` — 패널 추가 (위치는 D3 결정)

### Phase SP2 — applied_at + strategy_init 자동 row

**`settings_history` 에 `applied_at` 컬럼 추가** + **strategy 재init 시 자동 row 적재**.

#### DB 스키마 변경

```sql
-- settings_history 에 컬럼 추가
ALTER TABLE settings_history ADD COLUMN applied_at TEXT;

-- source_page CHECK 제약 갱신 (strategy_init 추가)
-- SQLite 는 CHECK ALTER 불가 → 테이블 재생성 또는 트리거 우회 필요
-- (실용 결정: 트리거 우회 = 새 source_page 'strategy_init' 추가하되 기존 CHECK 는 보존, 트리거에서 검증)
```

**대안 (간단)**: CHECK 제약을 처음부터 strategy_init 포함하여 신규 생성. 기존 DB 는 _safe_alter 로 컬럼 추가만, CHECK 제약은 기존 그대로 → strategy_init source_page 적재 시 별도 검증 함수에서 차단.

#### 신규 함수 `services/settings_history.py`

```python
def record_strategy_init(user_id: str, strategy_type: str, applied_conditions: dict) -> int:
    """
    strategy 객체 재초기화 시점에 자동 호출.
    - source_page='strategy_init'
    - params_json, conditions_json = strategy 객체가 실제 로드한 값
    - applied_at = NOW (이 row 의 saved_at 과 동일)
    - note = "strategy 재초기화 — 활성 운영 conditions 기록"

    이후 사용자가 set_buy_sell_conditions 등으로 변경 시 record_snapshot 호출 →
    그 row 의 applied_at 은 NULL (아직 엔진 미반영)
    → 다음 strategy_init 시 그 row 의 applied_at 을 NOW 로 UPDATE
    """
```

#### 호출 사이트

`engine/live_loop.py` strategy 객체 생성 직후:

```python
strategy = ... 생성
record_strategy_init(user_id, strategy_tag, {
    "stop_loss_pct": strategy.stop_loss * 100,
    "take_profit_pct": strategy.take_profit * 100,
    ...
})
# 동시에 settings_history 에서 applied_at IS NULL 인 row 들의 applied_at 을 NOW 로 UPDATE
```

**효과**:
- 사용자 저장 시점 vs 엔진 적용 시점 둘 다 추적 가능
- settings_history 뷰어에 "변경 vs 적용 격차 (시간)" 컬럼 신설 가능

### Phase SP3 — 변경 후 명시 안내 + 안전한 재시작

#### 변경 후 안내 배너

`pages/set_buy_sell_conditions.py` 저장 직후:

```python
record_snapshot(...)
st.warning(
    "⚠️ 설정이 저장되었으나 **엔진은 아직 이전 값으로 운영 중**입니다.\n"
    "변경을 즉시 반영하려면 대시보드에서 '엔진 재시작' 버튼을 눌러주세요.\n"
    "(현재 활성 포지션이 있다면 TP/SL 즉시 영향 가능)"
)
```

#### 대시보드 "엔진 재시작" 버튼

SP1 패널의 비교 표 아래 또는 별도 위치 (D3·D4 결정):

```python
if engine_running:
    if has_open_position:
        st.warning("⚠️ 활성 포지션 보유 중 — 재시작 시 TP/SL 즉시 적용됩니다.")
    if st.button("🔄 엔진 재시작 (conditions 재로드)"):
        if confirmed_with_open_position_check:
            restart_engine(user_id)
            st.success("✅ 엔진 재시작 완료. 새 conditions 가 적용되었습니다.")
```

#### 안전 장치 (D4)

- (i) 활성 포지션 보유 중 차단 OR (ii) 강한 경고 후 진행 가능 — 사용자 결정

### Phase SP4 — audit_trades 에 트리거 시점 임계값 적재

`core/trader.py:_audit_emit_trade` 가 호출하는 `insert_trade_audit` 에 sl/tp/ts_pct 인자 전달:

```python
# trader.py
strategy = getattr(self, "_strategy_ref", None)
sl_val = strategy.stop_loss if strategy else None
tp_val = strategy.take_profit if strategy else None
ts_pct_val = strategy.trailing_stop_threshold if strategy else None

insert_trade_audit(
    ...,
    sl=sl_val,
    tp=tp_val,
    ts_pct=ts_pct_val,
)
```

**선결 조건**: trader 가 strategy 객체에 대한 참조를 가지거나, strategy 가 self.last_thresholds 같은 캐시를 제공.

**효과**: 사후 분석 시 "이 거래는 어떤 임계값으로 발동되었는지" 정확히 추적 가능 — 진단 §9-2 결함 해소.

---

## 5. 영향 받는 파일 (Phase별)

### SP1
- `services/db.py` — `fetch_latest_audit_settings(user_id)` 신규
- `pages/dashboard.py` — 패널 추가 + 버전 갱신

### SP2
- `services/init_db.py` — `settings_history` 에 `applied_at` 컬럼 ALTER (idempotent)
- `services/settings_history.py` — `record_strategy_init`, `update_applied_at_for_pending` 헬퍼 + `source_page` 화이트리스트에 `strategy_init` 추가
- `engine/live_loop.py` — strategy 객체 init 직후 `record_strategy_init` 호출
- `pages/settings_history.py` — 컬럼 표시 (변경 vs 적용 격차 분 단위)

### SP3
- `pages/set_buy_sell_conditions.py`, `pages/set_config.py` — 저장 직후 안내 배너
- `pages/dashboard.py` — "엔진 재시작" 버튼 + 안전 장치
- `engine/engine_manager.py` 또는 `engine/engine_runner.py` — restart_engine 함수 (정지+시작) — 기존 코드 활용

### SP4
- `core/trader.py` — `_audit_emit_trade` 에서 strategy 객체 참조 + sl/tp/ts_pct 전달
- `engine/live_loop.py` — trader 생성 시 strategy 참조 전달 또는 setter 호출

### 공통
- `pages/dashboard.py` — 버전 v1.YYYY.MM.DD.HHMM 갱신 (모든 Phase 완료 후 1회)

---

## 6. Phase 순서 (로컬 완료 후 단일 배포)

```
P0 — 기획안 승인 (현재 단계)
   ↓
SP1 (가시화) — 데이터는 이미 있음, UI만 추가
   ↓
SP2 (applied_at + 자동 row) — DB 스키마 + 호출 사이트
   ↓
SP3 (안내 + 재시작) — UX
   ↓
SP4 (audit_trades 임계값 적재) — 분석 정확도
   ↓
통합 검증 (로컬 + 임시 user_id)
   ↓
사용자 최종 승인 → 커밋 → push → 단일 배포 (deploy-tradebot)
   ↓
서버 검증 (audit_settings 가시화, applied_at 채워짐 확인, 재시작 동작 확인)
```

---

## 7. 결정 필요 항목 (D1~D5)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| D1 | `source_page` 새 값 추가 | (a) `strategy_init` 만 / (b) `engine_restart` 도 함께 | **(a)** — 두 개념 동일 |
| D2 | `applied_at` 채우는 시점 | (a) strategy_init 시점에 그 이전 NULL row 들 일괄 UPDATE / (b) 같은 시점의 새 row 1개만 적재 (이전 row 들은 NULL 그대로) | **(a)** — 격차 시계열 추적 가능 |
| D3 | 대시보드 SP1 패널 위치 | (a) "⚙️ Option 기능" 섹션 위 / (b) "📊 Dashboard" 헤더 직후 / (c) 별도 신규 섹션 ("🔧 엔진 상태") | **(c)** — 운영 모니터링 영역 신설 (장기 확장 여지) |
| D4 | 엔진 재시작 안전 장치 | (i) 활성 포지션 보유 중 차단 / (ii) 강한 경고 후 진행 가능 (settings-history P3 D12 패턴 재사용) | **(ii)** — 일관성 (D12 와 동일 정책) |
| D5 | SP4 sl/tp/ts_pct 값 출처 | (a) strategy 객체 self.* × 100 직접 참조 (필요시 ref 전달) / (b) audit_settings 최신 row 의 값 참조 (간접) / (c) StrategyEngine 이 last_thresholds 캐시 제공 | **(c)** — 시그니처 변경 최소, 정합성 ↑ |

---

## 8. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| `ALTER TABLE settings_history ADD COLUMN applied_at` 위험 | NULL 허용이므로 안전, 기존 row 영향 없음 | _ensure_column 패턴(settings-history 와 동일) |
| `CHECK source_page` 제약 — strategy_init 추가 시 SQLite 한계 | ALTER CHECK 불가 | 신규 DB 는 처음부터 포함, 기존 DB 는 CHECK 미적용 → 적재 시 코드 레벨 검증 |
| 엔진 재시작 시 활성 포지션 영향 | TP/SL 즉시 변경 → 의도치 않은 청산 | D4 안전 장치 (강한 경고 + 명시 승인) |
| trader 가 strategy 참조를 갖게 되면 순환 참조 가능성 | 모듈 의존도 ↑ | D5(c) — StrategyEngine 이 캐시 제공 → trader 는 caller 가 전달 |
| audit_settings 최신 row 가 1분 지연 | UI 표시값 최대 1분 stale | 1분 이내 의미 있음 — 허용 |
| 대시보드 패널 표시 부하 | 매 페이지 렌더링마다 SQL 조회 | st.cache_data 또는 1초~5초 캐시 |

---

## 9. 결정 항목 승인 후 진행 흐름

1. D1~D5 승인
2. SP1 로컬 구현 + 검증 (임시 user_id 시나리오)
3. SP2 로컬 구현 + 검증
4. SP3 로컬 구현 + 검증
5. SP4 로컬 구현 + 검증
6. 통합 검증 — SP1~SP4 모두 동시 동작 확인
7. 사용자 최종 승인
8. 커밋 (단일 또는 Phase 분리 — 결정 항목 후속)
9. push → 사용자 배포 트리거 → 서버 검증

---

## 10. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-22 19:30 | 초안 작성 | 진단 보고서 §11 발견 → 본 기획안 분리. SP1~SP4 로컬 완료 후 단일 배포 정책. D1~D5 사용자 승인 대기 |
| 2026-06-23 10:00 | 사용자 클레임 2건 검증 → §11/§12 추가 | (1) 6/23 09:59 LIMIT BUY 1봉만 기다리고 cancel 클레임 정확 / (2) 설정 저장 즉시 적용(hot reload) 요구 → SP5 재포함, SP6 신규. D6/D7 추가. Phase 순서: SP6 → SP5 → SP1~SP4 |

---

## 11. SP5 — Conditions Hot Reload (사용자 명시 요구 — 2026-06-23)

### 11-1. 사용자 요구

> "기존 기능이 정상적으로 동작해야 한다. 즉, 설정을 저장하면 현재 엔진이 동작하고 있더라도 해당 설정 파일을 읽어서 적용이 되어야 한다."

→ strategy 객체 init 시점 고정이 아닌, **변경 즉시 또는 다음 봉부터 자동 반영** 필요.

### 11-2. 현재 흐름의 한계

- 엔진은 매 봉 `[COND] loaded` 로 conditions 파일 read — audit_settings 적재용
- **strategy 객체의 self.stop_loss / self.take_profit / SellFilterPipeline 임계값은 init 시점에 고정**
- 따라서 파일 변경해도 명시적 엔진 재시작 전까지 미반영

### 11-3. 기술 설계

#### 신규 메서드 `core/strategy_incremental.py`

MACD/EMA 양쪽 클래스에 `reload_conditions(conditions: dict)` 추가:

```python
def reload_conditions(self, conditions: dict) -> dict:
    """
    엔진 재시작 없이 conditions 갱신.
    Returns:
        {"changed": {"stop_loss_pct": (old, new), ...},
         "filter_rebuild": bool}
    """
    sell = conditions.get("sell", {})
    buy = conditions.get("buy", {})

    changes = {}

    # 매도 임계
    new_stop_loss = sell.get("stop_loss_pct", 1.0) / 100.0
    if abs(self.stop_loss - new_stop_loss) > 1e-9:
        changes["stop_loss_pct"] = (self.stop_loss, new_stop_loss)
        self.stop_loss = new_stop_loss

    new_take_profit = sell.get("take_profit_pct", 3.0) / 100.0
    if abs(self.take_profit - new_take_profit) > 1e-9:
        changes["take_profit_pct"] = (self.take_profit, new_take_profit)
        self.take_profit = new_take_profit

    new_trailing = sell.get("trailing_stop_threshold_pct", 10.0) / 100.0
    if abs(self.trailing_stop_pct - new_trailing) > 1e-9:
        changes["trailing_stop_pct"] = (self.trailing_stop_pct, new_trailing)
        self.trailing_stop_pct = new_trailing
        self.trailing_stop_activation_pct = self.take_profit

    # boolean flags
    for flag in ["stop_loss", "take_profit", "trailing_stop", "ema_dc",
                 "stale_position_check"]:
        new_val = sell.get(flag, getattr(self, f"enable_{flag}", True))
        cur_val = getattr(self, f"enable_{flag}", None)
        if cur_val is not None and cur_val != new_val:
            changes[f"enable_{flag}"] = (cur_val, new_val)
            setattr(self, f"enable_{flag}", new_val)

    # Buy flags (ema_gc, above_base_ema, bullish_candle, surge_filter_enabled,
    # fixed_price_buy_enabled, surge_threshold_pct)
    # ... 동일 패턴

    self.sell_conditions = sell
    self.buy_conditions = buy

    # SellFilterPipeline 재구성 — 임계값 변경 시 필터 인스턴스 재생성
    filter_rebuild = bool(changes)
    if filter_rebuild:
        self._rebuild_sell_filter_manager()

    return {"changed": changes, "filter_rebuild": filter_rebuild}
```

#### 호출 사이트 `engine/live_loop.py`

```python
# 매 봉 처리 직전 (기존 [COND] loaded 흐름)
conditions, mtime = _load_trade_conditions_with_mtime(user_id, strategy_tag)
if mtime != last_conditions_mtime:
    result = strategy.reload_conditions(conditions)
    if result["changed"]:
        logger.warning(
            f"🔄 [HOT-RELOAD] conditions 변경 감지 → strategy 객체 갱신 | "
            f"changes={list(result['changed'].keys())}"
        )
        # 활성 포지션 보유 중이면 Telegram CRITICAL (D7 결정 ii)
        if position.in_position:
            _notify_critical_hot_reload(user_id, result["changed"])
    last_conditions_mtime = mtime
```

#### mtime 캐싱

매 봉 파일 read 부담 방지: file mtime 변경 시에만 reload.

### 11-4. 안전 장치 (D7 결정: 즉시 적용 + Telegram CRITICAL)

활성 포지션 보유 중 임계값 변경 감지 시:

```
🚨 [HOT-RELOAD] 운영 중 conditions 변경 감지 — {user_id}
변경 항목: stop_loss_pct: 0.5% → 1.5%, take_profit_pct: 1.0% → 3.0%
⚠️ 활성 포지션 보유 중 → TP/SL 즉시 새 임계로 적용됩니다.
의도하지 않은 변경이라면 dashboard 에서 즉시 원복 저장 권장.
```

### 11-5. SP3 단순화

SP5 도입으로 SP3 의 "엔진 재시작 버튼" 은 **불필요** (자동 적용됨). SP3 는 다음으로 단순화:

- 변경 저장 후 안내: "✅ 설정이 저장되었습니다. 엔진은 **다음 봉부터 자동 적용**됩니다."

---

## 12. SP6 — 지정가 매수 대기 봉 수 사용자 설정 (사용자 클레임 — 2026-06-23)

### 12-1. 클레임 원문

> "지정가 매수 보니까 한 봉 기다리고 취소되는 것 같은데 3봉 정도는 기다려 줘야 할 것 같은데 검토해줘 (오전 9:59분에 매수 안 됨 참조)"

### 12-2. 검증 결과 — 클레임 정확

6/23 09:59:17 BUY-LIMIT 등록 → 10:00:16 cancel (elapsed=57.3s, timeout=55s) → executed_volume=0.
`engine/order_reconciler.py:331`:
```python
timeout_sec = max(5, interval_sec - 5)  # 1분봉 → 55초 → 1봉만 대기
```

### 12-3. 기술 설계

#### UI — `pages/set_buy_sell_conditions.py`

`fixed_price_buy_enabled` 활성화 시 추가 입력 노출:

```python
if st.session_state.get("fixed_price_buy_enabled", False):
    wait_bars = st.number_input(
        "지정가 매수 대기 봉 수 (1~5 봉)",
        min_value=1, max_value=5, value=3, step=1,
        help="설정한 봉 수 만큼 체결을 기다린 후 자동 취소. "
             "권장: 1분봉 = 3봉(3분). 변동성 큰 시장은 5봉까지."
    )
    st.session_state["fixed_price_buy_wait_bars"] = int(wait_bars)
```

#### conditions.json 신규 키

```json
{
  "buy": {
    "fixed_price_buy_enabled": true,
    "fixed_price_buy_wait_bars": 3,    ← 신규
    ...
  }
}
```

#### `core/strategy_engine.py` `_handle_buy_signal`

```python
wait_bars = int(_buy_cond.get("fixed_price_buy_wait_bars", 3) or 3)
effective_interval_sec = self.interval_sec * wait_bars

result = self.trader.buy_limit(
    bar.close, self.ticker, ts=bar.ts, meta=meta,
    interval_sec=effective_interval_sec,   # ← 곱해진 값 전달
)
```

#### `core/trader.py` `buy_limit`

기존 코드 변경 최소 — `interval_sec` 파라미터를 그대로 받아 meta 에 저장. Reconciler 가 `meta.interval_sec` 그대로 timeout 계산 → 자연스럽게 3분 대기.

#### `core/strategy_engine.py` pending 자동 해제

`_maybe_release_limit_pending` 는 `bar_count > _pending_buy_bar` 즉 1봉 후 해제. SP6 와 충돌 — 3봉 후 해제로 변경:

```python
if self.bar_count > self._pending_buy_bar + (wait_bars - 1):
    # pending 해제
```

### 12-4. 기본값 결정 (D6)

- **기본 3 봉** (3분, 사용자 결정)
- UI 노출 범위: 1~5 봉
- 기존 데이터 (`fixed_price_buy_wait_bars` 키 없음) 도 기본 3 적용

### 12-5. 효과

- 1봉(55초) → 3봉(175초) 대기 → 체결 확률 증가
- 변동성 큰 코인은 5봉(295초) 까지 시도 가능
- 너무 길게 잡지 않음 (5분 이상 자금 묶이지 않도록 상한 5봉)

---

## 13. 결정 항목 D6 / D7 확정 (사용자 결정 2026-06-23)

| # | 항목 | 옵션 | 결정 |
|---|---|---|---|
| D6 | SP6 LIMIT BUY 대기 봉 수 기본값 | (a) 1 (현 동작 유지) / (b) **3** / (c) UI 노출만 | **(b) 3 ✓** |
| D7 | SP5 Hot reload 활성 포지션 정책 | (i) 즉시 적용 / (ii) **즉시 적용 + Telegram CRITICAL** / (iii) 차단 | **(ii) ✓** |

---

## 14. Phase 순서 갱신 (2026-06-23 사용자 결정 3-b)

```
SP6 (LIMIT BUY 3봉 대기) — 가장 시급 (사용자 클레임 즉시 해소 필요)
   ↓
SP5 (Hot reload) — 사용자 핵심 요구 (재시작 없이 즉시 적용)
   ↓
SP1 (가시화) — 대시보드 패널
   ↓
SP2 (applied_at + 자동 row) — DB 스키마
   ↓
SP3 (안내) — SP5 도입으로 단순화 (재시작 버튼 불요)
   ↓
SP4 (audit_trades 임계값 적재) — 분석 정확도
   ↓
통합 검증 (로컬 + 임시 user_id)
   ↓
사용자 최종 승인 → 커밋 → push → 단일 배포
   ↓
서버 검증
```

**모든 Phase 로컬 완료 후 단일 배포** (메모리 규칙 `feedback_deploy_only_when_complete` + 사용자 결정 3-b).

---

## 15. 영향 받는 파일 — Phase 종합 (§5 갱신)

### SP6 (신규)
- `pages/set_buy_sell_conditions.py` — wait_bars 입력 UI
- `core/strategy_engine.py` — `_handle_buy_signal` interval_sec 곱셈, `_maybe_release_limit_pending` 봉 수 조정
- 기존 `core/trader.py`, `engine/order_reconciler.py` — 변경 없음 (meta.interval_sec 자연 전파)

### SP5 (신규)
- `core/strategy_incremental.py` (MACD/EMA 양쪽) — `reload_conditions()` + `_rebuild_sell_filter_manager()`
- `engine/live_loop.py` — mtime 캐싱 + reload 호출
- `services/notifier.py` — (기존 활용, 변경 없음)

### SP1, SP2, SP3, SP4
- §5 참조 (변경 없음, 다만 SP3 는 단순화)

### 공통
- `pages/dashboard.py` — 버전 v1.YYYY.MM.DD.HHMM (모든 Phase 완료 후 1회)
