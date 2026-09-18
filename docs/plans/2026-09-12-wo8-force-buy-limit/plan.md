# WO-8 · 강제 매수 지정가 이식 (구현 계획서)

**작성일**: 2026-09-12
**상태**: 초안 · 사용자 승인 대기
**전제**:
- WO-6 완결 (커버리지 100%, 8일+ 무사고). `docs/plans/2026-09-12-wo6-implementation-plan/plan.md`
- WO-2 재적용 검증 통과. `docs/plans/2026-09-12-post-check/coverage-and-critical.md`
- V-B 조사: 강제 매수 = 시장가 완전 우회 확정. `docs/plans/2026-09-12-fv1-fv3-and-v-a-v-b-investigation/report.md` §V-B

**본 계획서는 문서 작업이다. 코드 수정은 사용자의 계획서 승인 이후.**

---

## 0. 목적

대시보드 강제 매수(`🛑 강제매수하기` 버튼)를 정상 크로스 매수 경로와 동일하게 지정가 정책(fixed_price_buy)에 순응하도록 이식한다. 현재는 `services/trading_control.py:242 force_buy_in()`이 `trader.buy_market()`을 무조건 호출해 지정가 관문 4종을 전부 우회한다.

---

## 1. 변경 지점 (V-B 확정 콜스택 인용)

### 1.1 V-B 확정 현재 콜스택

| 단계 | 위치 (V-B 조사에서 확정) | 요약 |
|---|---|---|
| 버튼 | `pages/dashboard.py:2328` | `🛑 강제매수하기` (key=`btn_force_buy`) |
| 클릭 처리 | `pages/dashboard.py:2336` | `force_buy_in()` 호출 |
| 진입 함수 | `services/trading_control.py:147` | `force_buy_in(user_id, trader, ticker, interval_sec=60)` |
| 발주 | `services/trading_control.py:242` | `trader.buy_market(price, ticker, ts=ts, meta=meta)` (**항상 시장가**) |
| Upbit 시장가 | `core/trader.py:576` | `_upbit_buy_market()` (LIVE 시) |

### 1.2 정상 크로스 매수 경로 (WO-8 대조 원본)

| 단계 | 위치 | 로직 |
|---|---|---|
| 분기 판단 | `core/strategy_engine.py:1083` | `if fixed_price_buy_enabled and LIVE:` |
| 지정가 발주 | `core/strategy_engine.py:1097` | `trader.buy_limit(price, ticker, effective_interval_sec=..., ...)` |
| 대기 봉 수 계산 | `core/strategy_engine.py:1089-1102` | `effective_interval_sec = wait_bars × interval_sec` |
| 체결 콜백 진입 | `core/strategy_engine.py:196-260` | `bot_limit_fill` — `apply_entry(uuid, source='bot_limit_fill')` 진입 기록 통일 관문 |
| 미체결 취소 알림 | `engine/order_reconciler.py:459-474` | `#14 fixed_buy_timeout` (대시보드·텔레그램) |

### 1.3 WO-8 변경 개요 (실측 시그니처 정정본, 2026-09-12)

**`services/trading_control.py:242` 를 `fixed_price_buy_enabled` 분기로 감싸고 지정가 경로에서는 `trader.buy_limit()`을 호출한다.** 정상 크로스 매수 경로의 분기 로직(`core/strategy_engine.py:1080-1102`)을 **글자 그대로 재사용**한다.

**실측 확정 시그니처 (2026-09-12)**:

- **LIVE 판정**: `trader.mode == "LIVE"` 형태는 없다. `trader.mode` 속성 자체 부재. 정상 경로가 사용하는 판정식은 **`not self.trader.test_mode`** (`core/strategy_engine.py:1084`).
- **`buy_limit` 시그니처**: `def buy_limit(self, price: float, ticker: str, ts=None, meta: Optional[Dict[str, Any]] = None, interval_sec: int = 60) -> dict:` (`core/trader.py:807-813`). kwarg 이름은 **`interval_sec`** (NOT `effective_interval_sec`).
- **meta 전파 (자동)**: `buy_limit` 내부에서 `enriched_meta = {**(meta or {}), "is_fixed_price_buy": True, "interval_sec": int(interval_sec or 60), "limit_price": rounded_price}` (`core/trader.py:1010-1015`) → `reconciler.enqueue(uuid, ..., meta=enriched_meta)` (line 1061-1067). 호출자는 `is_fixed_price_buy` / `interval_sec` / `limit_price` 를 직접 넣을 필요 없음.
- **대기 시한 전파**: `enriched_meta.interval_sec` → `engine/order_reconciler.py:436` `interval_sec = int(meta.get("interval_sec", 60) or 60)` → line 438 `timeout_sec = max(5, interval_sec - 5)` → cancel + `#14 fixed_buy_timeout` 알림 (line 459-474, `dedupe_key=f"fixed_buy_timeout:{uuid}"`, `dedupe_ttl=60`).
- **TEST 모드 처리 (정정, 2026-09-12 TEST 실행 결과 반영)**: 두 가지 방어선이 있다.
  1. **1차 방어**: 호출부 `fixed_price_mode` 판정식이 `(not trader.test_mode) and ...` 이므로 **TEST 모드에서는 fixed_price_mode=False로 결정되어 아예 `buy_limit` 호출 자체가 없다**. `buy_market`으로 직접 진입 — 정상 크로스 매수 경로(`strategy_engine.py:1084`)와 동일.
  2. **2차 방어**: 만약 다른 경로에서 TEST 모드에 `buy_limit`이 호출되더라도 `buy_limit` 내부에서 `if self.test_mode: return self.buy_market(...)` 로 자동 폴백.
  - 결과: TEST 모드는 언제나 시장가로 진입. WO-8 호출부에서 별도 TEST 분기 불필요.
- **지정가 기준가**: 정상 경로 = `bar.close`. force_buy_in의 `price` 변수 (line 162-197: MACD 로그 → EMA 로그 → 일반 로그 → Upbit API 순 fallback) 도 개념적 "직전 관측 close"이므로 **동일 값**. WO-8은 `price`를 그대로 buy_limit에 넘긴다.
- **봉 간격 출처 (수정 1 확답)**: 대시보드 호출부(`pages/dashboard.py:2342`)가 `interval_sec=params_obj.interval_sec`을 전달. `params_obj.interval_sec`은 `engine/params.py:272-287 LiveParams.interval_sec` @property로 `self.interval` 문자열(예: `minute5`)을 초 단위(예: 300)로 자동 매핑한다. 하드코딩 없음. minute1 사용자로 바뀌면 60, minute5는 300으로 자동 반영. 정상 크로스 경로가 사용하는 `self.interval_sec` (`core/strategy_engine.py:81`, 엔진 생성 시 `params.interval_sec`에서 초기화)과 **동일 출처**.
  - **minute5 재검증 (2026-09-12)**: interval_sec=300 조건에서 `effective_interval_sec = 300 × 3봉 = 900`, buy_limit(interval_sec=900) 인자 확인, reconciler `timeout_sec = max(5, 900-5) = 895`초 확인. ✓

**개편 후 개념 흐름 (정정본)**:
```python
# services/trading_control.py:232 부근
ts = datetime.now()
meta = {
    "interval": interval_sec,
    "reason": "force_buy",
    "src": "manual",
    "price_ref": price,
    "bar_time": None,
    "bar": current_bar,
}

# ✅ WO-8 이식: 정상 크로스 경로(strategy_engine.py:1080-1102) 판정식 글자 그대로
buy_sell_conditions = load_buy_sell_conditions(user_id, strategy_type)
_buy_cond = buy_sell_conditions.get("buy", {}) or {}
fixed_price_mode = (
    (not trader.test_mode)                                       # LIVE 판정 (strategy_engine.py:1084 동일)
    and bool(_buy_cond.get("fixed_price_buy_enabled", False))
)

if fixed_price_mode:
    meta["fixed_price_buy"] = True
    wait_bars = int(_buy_cond.get("fixed_price_buy_wait_bars", 3) or 3)
    wait_bars = max(1, min(5, wait_bars))                        # 안전 클램프 1~5 (strategy_engine.py:1091 동일)
    effective_interval_sec = interval_sec * wait_bars
    logger.info(
        f"🎯 [FIXED-PRICE][FORCE] 고정가 강제 매수 진입 | "
        f"price={price:,.2f} ticker={ticker} "
        f"wait_bars={wait_bars} effective_timeout≈{effective_interval_sec-5}s"
    )
    result = trader.buy_limit(
        price, ticker,
        ts=ts, meta=meta,
        interval_sec=effective_interval_sec,                     # kwarg 이름 = interval_sec
    )
else:
    result = trader.buy_market(price, ticker, ts=ts, meta=meta)
```

**세부 규칙**:
- `fixed_price_buy_enabled=False` 또는 TEST 모드 → 기존 시장가 경로 유지.
- `wait_bars` 안전 클램프 1~5 (정상 경로와 동일).
- `meta.reason="force_buy"` 유지 → notifier가 이 값으로 강제 매수 구분 (§2.2).
- `strategy_type` 조회: `set_config_manager` 또는 파라미터 파일 참조 (구현 시 정상 경로 방식 그대로 재사용).

### 1.4 수정 파일·함수 목록

| 파일 | 함수·라인 | 변경 내용 |
|---|---|---|
| `services/trading_control.py` | `force_buy_in` (line 147~) | `fixed_price_buy_enabled` 조건 분기 추가, `buy_limit()` 호출 지점 신설 |
| `services/trading_control.py` | 상단 import | `load_buy_sell_conditions` 헬퍼 참조 (정상 경로에서 사용 중인 함수 재사용) |
| `pages/dashboard.py` | 강제 매수 버튼 근처 (§3 UX) | 미체결 취소 시 안내 문구 추가 (Streamlit `st.info` 또는 `st.caption`) |
| `.claude/context/project-rules.md` | (선택) | WO-8 배포 이력 append |

---

## 2. 재사용 관문 3건 배선 확인

### 2.1 `bot_limit_fill` 콜백 경유 (진입 기록 통일 관문)

- **정상 경로**: `trader.buy_limit()` 성공 시 `order_reconciler`가 uuid를 큐에 등록 → 체결 이벤트 → `bot_limit_fill` 콜백 발동 → `strategy_engine.apply_entry(uuid, source='bot_limit_fill')` (`core/strategy_engine.py:196-260`) → `entry_bar`·`entry_price`·`qty` 세팅
- **WO-8 이식 시**: `trader.buy_limit()` 반환 uuid가 정상 경로와 동일하게 `order_reconciler`에 enqueue되고 fill 콜백이 발동하는지 확인 필요.
- **핵심 검증 항목**: 강제 매수 지정가 체결 후 `[LIMIT-FILL] apply_entry 완료 | uuid=... source=bot_limit_fill` 로그 관측 (`core/strategy_engine.py:196` 근처).
- **관련 위험**: `apply_entry`를 우회하면 `avg_price=None` 결함이 재발한다 (참조: [[project_upbit_hts_sl_paralysis_fix]] — 2026-07-27 4단 봉쇄 근거).

### 2.2 `#14 fixed_buy_timeout` 알림 재사용

- **정상 경로**: `engine/order_reconciler.py:459-474` — 지정가 미체결 시 봉 경계에서 취소 후 대시보드·텔레그램 알림 발송.
- **WO-8 이식 시**: `force_buy_in`으로 발주한 지정가 주문도 `order_reconciler`의 같은 큐에 등록되므로 `#14 fixed_buy_timeout` 알림이 자동 재사용됨. **별도 알림 코드 신설 불필요**.
- **다만**: 알림 문구가 자동 크로스 매수 기준으로 작성되어 있으면 "강제 매수"임을 구분 표기하기 위해 `meta.reason="force_buy"` 값을 알림 렌더링에 노출하는 소규모 개선이 필요할 수 있다. `engine/order_reconciler.py:459-474` 부근 알림 메시지 포맷 확인 후 판단.

### 2.3 `fixed_price_buy_wait_bars` 그대로 적용

- **정상 경로**: `effective_interval_sec = wait_bars × interval_sec` (`core/strategy_engine.py:1089-1102`).
- **WO-8 이식 시**: 동일 계산식 사용. `interval_sec`은 `force_buy_in`이 이미 파라미터로 받고 있으므로(line 147: `interval_sec: int = 60`) 그대로 사용 가능.
- **별도 파라미터 신설 없음**. `buy_sell_conditions.buy.fixed_price_buy_wait_bars` 를 정상 경로와 동일하게 조회.

---

## 3. 미체결 시 사용자 경험 (UX)

### 3.1 현재(시장가) UX

- 사용자가 `🛑 강제매수하기` 클릭 → 즉시 시장가 체결 (LIVE) → 대시보드에 즉시 반영.
- "강제 매수 했는데 왜 체결 안 되지?" 문제 없음 (시장가는 유동성 있으면 즉시 체결).

### 3.2 지정가 이식 후 UX (예상)

- 사용자 클릭 → `trader.buy_limit()` 발주 → **주문 접수됨, 체결은 대기**.
- 대기 봉 수(`fixed_price_buy_wait_bars`) 내 체결되지 않으면 봉 경계에서 취소.
- 사용자 관점에서 "강제 매수를 눌렀는데 잔고가 그대로다"라는 혼란 발생 가능.

### 3.3 대시보드·텔레그램 표시

- **대시보드**: 강제 매수 발주 직후 `insert_log(user_id, "INFO", f"강제 매수 지정가 발주 완료: {price:,.2f}원 (대기 {wait_bars}봉)")`. 미체결 취소 시 `#14 fixed_buy_timeout` 알림이 대시보드 알림 카드에 자동 표시.
- **텔레그램**: `#14 fixed_buy_timeout` 알림이 그대로 전송. 문구 예시: `⚠️ 지정가 매수 취소 (미체결 5봉 초과) | KRW-JTO 612원 → 잔고 미반영`.
  - `meta.reason="force_buy"` 노출 검토: `[FORCE] 지정가 매수 취소 (미체결)` 처럼 자동 크로스와 구분 표기.

### 3.4 UI 안내 문구 추가 (신규)

**`pages/dashboard.py:2328` 근처 강제 매수 버튼 아래에 안내 문구 추가**:

```python
# 강제 매수 버튼
force_buy_clicked = st.button("🛑 강제매수하기", key="btn_force_buy", use_container_width=True)

# ✅ WO-8: 지정가 매수 활성 시 안내
if buy_sell_conditions.get("buy", {}).get("fixed_price_buy_enabled", False):
    wait_bars = buy_sell_conditions.get("buy", {}).get("fixed_price_buy_wait_bars", 5)
    st.caption(
        f"ℹ️ 지정가 매수 활성 상태. 강제 매수도 지정가로 발주되며 최대 {wait_bars}봉 내 미체결 시 자동 취소됩니다. "
        f"즉시 시장가 매수를 원하면 '설정' 페이지에서 지정가 매수를 끄세요."
    )
```

- 지정가 매수가 꺼져 있으면 안내 미표시 (기존 시장가 UX 그대로).
- 사용자 항의 "강제 매수인데 체결 안 됨"의 근원 사전 봉쇄.

---

## 4. TEST 모드 동작

### 4.1 현행 강제 매수 TEST 분기

- `services/trading_control.py:242 trader.buy_market()` → `core/trader.py`의 `buy_market()`이 TEST 모드에서는 가상 체결(즉시 성공, 실 주문 안 함)로 처리.
- 결과: TEST 모드에서 강제 매수는 즉시 성공, `orders` 테이블에 가상 체결 기록.

### 4.2 WO-8 이식 후 TEST 모드 필수 확인 항목

- **`trader.buy_limit()`의 TEST 분기가 존재하는가?** → 정상 크로스 매수 경로의 `trader.buy_limit()`이 TEST 모드에서 어떻게 동작하는지 확인 필요.
- **가상 체결이 즉시 발생하는가 아니면 대기 봉 수 후 발생하는가?** → 사용자 관점 UX 일관성 확보 필요.
- **`bot_limit_fill` 콜백이 TEST 모드에서도 발동하는가?** → `apply_entry` 진입이 TEST에서도 정상 이루어져야 `entry_bar` 등 상태 관측 가능.

**계획 단계에서 결정**: `trader.buy_limit()`의 TEST 분기가 정상 크로스 경로에서 이미 검증된 상태라면 WO-8은 별도 변경 없이 동일 동작 재사용. TEST 분기가 미비하면 별도 소규모 개선 계획 필요 (구현 착수 시 코드 조사로 확정).

---

## 5. 검토 항목 — CRITICAL 알림 등급 재조정

### 5.1 현행

- `core/strategy_incremental.py`: `❌ [EMA] bars_held=0 AND audit 실측 없음 — 데이터 무결성 결손 CRITICAL. SELL 차단 (HOLD 유지).` ERROR 레벨 로그.
- 최근 7일 실측 6건 발생 (CRITICAL 6건 = 이 로그 6건). 전부 HTS 매수 감지 후 첫 봉 지속 1봉 찰나 방어. **매매 사고 없음**.

### 5.2 재조정 안 (찬반)

**안**: `외부 매수 감지 후 첫 봉 + [POSITION-SYNC] 자동 복구 성공` 조건에 한해 **CRITICAL → WARN 강등 + dedupe** (동일 entry_bar 내 첫 발생만 로그).

**찬(강등)**:
- 6건 전부 자동 복구 성공. 매매 사고 0건.
- CRITICAL 태그가 알림 채널에 즉시 발송되면 오탐성 알림 피로 유발.
- WARN 로그로 강등하면 관측 지속하되 알림 우선순위 낮춤.
- dedupe로 로그 스팸 방지 (동일 entry_bar 내 반복 발생 시 첫 1회만).

**반(유지)**:
- CRITICAL 유지가 방어 로직의 발동 자체를 명확히 관측 가능하게 유지.
- 향후 자동 복구 실패 케이스(예: `apply_entry` 미호출로 `entry_bar` 세팅 실패)가 발생하면 WARN 강등 상태에서 놓칠 위험.
- CRITICAL 6건은 알림 등급 문제가 아니라 관측 문제. 알림 필터를 별도 조정하면 됨.

### 5.2b 승격 가드 (2026-09-12 배포 전 보완, 후속 커밋)

**추가**: 같은 ticker에서 `hts_buy=True + bars_held=0 차단`이 **2봉 연속** 발생하면 WARN 강등을 중단하고 **CRITICAL로 승격**한다 (자동 복구 실패의 증거).

**연속 카운터 리셋 규칙**:
- `bars_held > 0` 진입 시점 정상 통과 시 리셋 (line 1122-1125).
- `audit fallback` (`audit_bh > 0`) 성공 시 리셋 (line 1150-1154).
- 자동 리셋 없는 상황: `hts_buy=False`인 진짜 결손 (streak 유지, CRITICAL 그대로).

**신설 인스턴스 속성**: `IncrementalEMAStrategy.__init__` (line 707-710) 에 `self._pos_desync_streak: int = 0`.

**승격 조건**:
```python
if _downgrade_cond:  # hts_buy=True AND bars_held=0
    self._pos_desync_streak += 1
    if self._pos_desync_streak >= 2:
        # CRITICAL 승격 (dedupe_key=pos_desync_promoted:{ticker}:{entry_bar}, ttl=300)
    else:
        # WARN 강등 (dedupe_key=pos_desync_warn:{ticker}:{entry_bar}, ttl=600)
```

**정적 시뮬레이션 검증 결과 (3흐름)**:
| 봉 | 조건 | streak | 발화 |
|---|---|---|---|
| 봉 1 | hts_buy=True, bars_held=0 | 1 | **WARN 강등** |
| 봉 2 | hts_buy=True, bars_held=0 (연속) | 2 | **CRITICAL 승격** |
| 봉 3 | bars_held > 0 (자동 복구) | 0 (리셋) | 정상 SELL 평가 |
| 봉 4 | hts_buy=True, bars_held=0 (재발) | 1 | **WARN 강등 (재시작)** |
| 봉 5 (부가) | hts_buy=False, bars_held=0 | 유지 | **CRITICAL 유지** |

---

### 5.3 절충안 확정 (2026-09-12 승인)

**로그 레벨 유지, notifier 등급 매핑에서만 강등**. 로그 파일에는 CRITICAL/ERROR 그대로 남기되 텔레그램/대시보드 알림 우선순위만 낮춤.

**강등 조건 (전부 충족 시)**:
1. `position.metadata.get("hts_buy", False) == True` (외부 매수 감지 후 상태)
2. `bars_held == 0` (첫 봉)
3. `audit fallback (audit_bh > 0)` 성공 여부는 이 시점에서 미리 알 수 없으므로 조건 (1)+(2)를 "외부 매수 감지 후 첫 봉 + 자동 복구 예상 상황"의 근사 지표로 사용

**복구 실패 유지**: 조건 (1) 또는 (2) 미충족 → CRITICAL 그대로. 즉 봇 자체 매수인데 무결성 결손이 발생한 진짜 결함은 CRITICAL 유지.

**구현 위치**: `core/strategy_incremental.py:1157-1171` (CRITICAL 알림 발송 지점).

**변경 개요**:
```python
# core/strategy_incremental.py:1157 부근
try:
    from services.notifier import send as _notify_send, LEVEL_CRITICAL, LEVEL_WARNING

    # ✅ WO-8 절충안: 외부 매수 감지 후 첫 봉 방어는 WARN 강등
    _hts_buy = bool(position.metadata.get("hts_buy", False))
    _first_bar = (bars_held == 0)
    _downgrade = _hts_buy and _first_bar

    if _downgrade:
        _notify_send(
            LEVEL_WARNING,
            f"⏳ 외부 매수 감지 후 첫 봉 방어 — {self.ticker}",
            (
                f"HTS 감지된 신규 진입 봉에서 audit 미기록 상태.\n"
                f"자동 복구 대기 중 (다음 봉에서 [POSITION-SYNC] 예상).\n"
                f"entry_bar={position.entry_bar} current_bar={current_bar_idx}"
            ),
            dedupe_key=f"pos_desync_warn:{self.ticker}:{position.entry_bar}",
            dedupe_ttl=600,   # 10분
        )
    else:
        _notify_send(
            LEVEL_CRITICAL,
            f"🚨 포지션 무결성 결손 — {self.ticker}",
            (
                f"in-memory bars_held={bars_held}, audit_trades 실측도 없음.\n"
                f"봇 매도 필터 스킵 상태. 사용자 개입 필요.\n"
                f"entry_bar={position.entry_bar} current_bar={current_bar_idx}"
            ),
            dedupe_key=f"pos_desync:{self.ticker}",
            dedupe_ttl=300,   # 원 유지
        )
except Exception:
    pass
```

**dedupe 키 · TTL 명시**:
| 조건 | dedupe_key | dedupe_ttl |
|---|---|---|
| WARN 강등 (외부 매수 첫 봉) | `pos_desync_warn:{ticker}:{entry_bar}` | 600초 (10분) |
| CRITICAL 유지 (진짜 결손) | `pos_desync:{ticker}` (기존) | 300초 (5분) |

- WARN dedupe 키가 `entry_bar` 포함 → 같은 진입 봉 내 반복 강등 억제.
- CRITICAL dedupe 키는 기존 유지 (ticker 단위) → 진짜 결손 재발 시 5분마다 알림.
- 두 흐름 분리로 강등 알림이 진짜 결손 알림을 억제하지 않음.

**로그 자체는 그대로 유지**: line 1146-1151 `err_msg = f"❌ [EMA] ... CRITICAL. SELL 차단 ..."` + `logger.error(err_msg)` + `insert_log(user_id, "ERROR", err_msg)` 모두 그대로. 관측성 유지 목적.

---

## 6. 검증 계획

### 6.1 로컬 스모크

```
python3 -m py_compile services/trading_control.py pages/dashboard.py
```
- `import` 게이트 확인 (typing 심볼 누락 회귀 방지: [[project_upbit_2026_08_05_ui_guardrails]])

### 6.2 TEST 모드 강제 매수 시나리오

TEST 모드로 실행:
- **케이스 A**: `fixed_price_buy_enabled=False` (기본값) → 시장가 즉시 체결. 기존 동작 유지 확인.
- **케이스 B**: `fixed_price_buy_enabled=True` → 지정가 발주 → 대기 봉 수 내 가상 체결. `[LIMIT-FILL] apply_entry 완료` 로그 관측.
- **케이스 C**: `fixed_price_buy_enabled=True` + 대기 봉 초과 → 자동 취소. `#14 fixed_buy_timeout` 알림 확인.

각 케이스에서 `orders` 테이블 · `audit_trades` 테이블 · 대시보드 표시 · 텔레그램 알림 4개 채널 정합성 실측.

### 6.3 배포 후 실측 (필수 항목)

- 배포 후 30분: Traceback·CRITICAL·POLLUTED 부재 (Streamlit UI Traceback [[issue-18]] 제외).
- 배포 후 24시간: 강제 매수 지정가 발주 1건 이상 관측 (실주문 또는 TEST) → `bot_limit_fill` 콜백 → `apply_entry` 성공 로그.
- **필수 확인 항목**: **지정가 체결 직후 첫 봉 SELL 평가에서 `[POSITION-SYNC]` 자동 복구 로그 부재**. 이 조건은 WO-8이 `apply_entry` 정상 관문을 경유했음의 결정적 증거. `[POSITION-SYNC]` 로그가 나타나면 강제 매수 지정가 경로가 `apply_entry`를 우회한 것이므로 즉시 롤백.

### 6.4 커버리지 유지 확인

- WO-8 배포 후 7일 실측에서 커버리지 100% 유지 (WO-6 완결 상태 회귀 없음 확인).
- 산식은 `docs/plans/2026-09-12-post-check/coverage-and-critical.md` §1과 동일.

---

## 7. 롤백 계획

### 7.1 단일 revert 단위

- WO-8은 **하나의 커밋**으로 배포한다. 단일 파일 (`services/trading_control.py`) 변경 + UI 안내 (`pages/dashboard.py`) + 옵션 (§5 절충안 채택 시 notifier)의 원자적 세트.
- 롤백: `git revert <WO-8 커밋>` 후 push, force 없음.
- 대상 상태: 배포 직전 커밋 (배포 이력표 §1.4 참조).

### 7.2 즉시 롤백 트리거

- 배포 후 30분 내 Traceback (엔진·매매 관련) 1건 이상
- 배포 후 24h 내 강제 매수 지정가 체결 후 `[POSITION-SYNC] 자동 복구` 로그 1건 이상 (`apply_entry` 우회 결함)
- 강제 매수 시장가로 발주됐는데 지정가 활성 상태 (분기 실패)
- `#14 fixed_buy_timeout` 알림 발송 실패 (알림 경로 회귀)
- 커버리지 회귀 (100% → 미달)

---

## 8. WO-7과의 경계 (명시)

**이번 라운드(WO-8)는 발주 경로만 변경한다. avg 계산·표시는 건드리지 않는다.**

- **WO-8 범위**: 강제 매수 → 지정가 발주 경로 이식 (`buy_market` → `buy_limit` 분기).
- **WO-7 범위 (별도 라운드)**: 현행 평균가 동작의 화면 노출과 사용 여부 옵션 (avg 계산 로직 변경 아님).
- **경계 조건**: WO-8 구현 시 `avg_price` 관련 코드는 읽기만 하고 수정하지 않는다. `apply_entry`가 `avg_price`를 세팅하는 방식(현행)을 그대로 사용.

---

## 9. 완료 기준 (Definition of Done, WO-8b 라운드 재정의)

**핵심 원칙 (2026-09-18 재승인)**: 사용자의 강제 매수는 HTS 경유가 대부분이라 봇 버튼 사용 시점을 예측할 수 없다. 자연 발생 관측을 기다리며 완결을 무기한 유보하는 대신 다음 3항목 통과로 완결을 선언한다.

### WO-8 완결 조건 (3항목)

- [ ] **1. WO-8b 구현**: `services/trading_control.py`가 `trader.buy_limit()` 반환 uuid를 `StrategyEngine._pending_buy_uuid`에 등록. `_execution_lock` 아래 원자적 수행.
- [ ] **2. 왕복 TEST 통과**: 발주 → uuid 등록 → 모의 체결 → `_on_limit_fill` 콜백 → `apply_entry(source='bot_limit_fill')` 발화 → `[POSITION-SYNC] 자동 복구` 미발화. 회귀 161건 통과.
- [ ] **3. 배포 후 30분 무결성**: 결함 태그 6종 부재 (SKIP-BAR/POLLUTED/CRITICAL 엔진/pos_desync_promoted/Traceback 엔진).

### 사후 승인 사항 (2026-09-18)

**활성 엔진 레지스트리(`_active_engines`) 신설은 사후 승인**한다. 근거: Streamlit 대시보드 스레드에서 봉 처리 스레드가 소유한 `StrategyEngine` 인스턴스에 도달할 통로가 부재. 기존 구조는 `strategy_engine` 참조를 `engine/live_loop.py` 스코프 내로 한정하며 대시보드 관점에서는 접근 API가 없다. 레지스트리는 이 통로를 최소 침습으로 신설하며 스레드 안전성은 `_active_engines_lock` + `engine._execution_lock` 이중으로 보장한다.

### 원자화 사후 수정 (2026-09-18)

WO-8b 배포 전 확답에서 buy_limit 반환 → register_pending_buy_uuid 사이 경합 위험 확인됨(체결 감지 = 2초 주기 poll이지만 첫 순회가 등록 이후임을 구조적으로 100% 보장 못 함). `execute_force_buy_limit_atomic` 헬퍼 신설: `engine._execution_lock` 아래에서 `trader.buy_limit` 호출 + uuid 등록을 원자적으로 수행. fill callback은 이 락 획득까지 대기 → 등록 완료 후에만 매칭 검사에 진입. 원자화 왕복 TEST 통과 (fill callback 92.6ms 락 대기 후 `apply_entry(source='bot_limit_fill')` 정상 발화).

### WO-8 초기 배포 (2026-09-12 `de28fea`) 완료 사항

- [x] `services/trading_control.py` `force_buy_in` 지정가 분기 추가 (V-B 확정 라인 인용)
- [x] `pages/dashboard.py` UI 안내 문구 추가 (§3.4)
- [x] py_compile 통과 (§6.1)
- [x] TEST 모드 케이스 A/B/C 시나리오 통과 (§6.2)
- [x] 배포 후 30분 확인 통과 (§6.3) — 결함 태그 6종 전부 0건, Bar# 정상 진행
- [x] dashboard.py 버전 갱신 (`v1.2026.09.12.1715`)
- [x] 배포 커밋 메시지에 롤백 트리거 명시 (`de28fea`)
- [x] 검증 가이드 신설 (`docs/operations/wo8-force-buy-verification-guide.md`)
- [x] 24h 무결성 (2026-09-13 17:24 KST 기준): 커버리지 100%, 결함 6종 0

### 사후 확증 (기한 없이 세션 개시 정기 점검 편입)

WO-8 완결 선언 후에도 다음 2건은 세션 개시 시 정기 점검한다. 기한·강제 실행 요구 없음.

**사후 확증 1 — 자연 발생 강제 매수 로그**:
- [ ] `[FIXED-PRICE][FORCE]` + `interval_sec=1500` 로그
- [ ] `[LIMIT-FILL] apply_entry(source='bot_limit_fill')` 발화 (WO-8b 이식 검증)
- [ ] 이후 첫 봉 SELL 평가에서 `[POSITION-SYNC] 자동 복구` 부재
- [ ] 미체결 시 `[FORCE]` 취소 알림 발송
- [ ] `audit_trades.reason='force_buy'` 행 `entry_price` (기존 관례상 빈값 허용)

**사후 확증 2 — 승격 가드 실전 관측 (HTS 매수 발생 시)**:
- [ ] HTS_BUY 감지 후 첫 봉: `pos_desync_warn` (WARN 강등) 발화 정확성
- [ ] 2봉 연속 시: `pos_desync_promoted` (CRITICAL 승격) 발화 정확성
- [ ] 오탐 여부 (정상 매매 봉에서 잘못 발화 방지)

---

## 10. 승인 결과 (2026-09-12)

**모든 항목 사용자 승인 완료**:
1. **§5 CRITICAL 등급 재조정 절충안**: 채택. 조건·dedupe·TTL 상세는 §5.3 구현부에 반영.
2. **§4 TEST 모드 `trader.buy_limit()` 분기**: 실측 확정 (§1.3) — `buy_limit` 내부에서 `if self.test_mode: return self.buy_market(...)` 자동 폴백. 정상 크로스 경로에서 이미 검증 상태. WO-8 별도 개선 불요.
3. **`#14 fixed_buy_timeout` 알림 문구에 `reason=force_buy` 노출**: 채택. §2.2에 반영.
4. **배포 순서 확정**: WO-6(완결) → **WO-8(이 라운드)** → WO-7. WO-2 재적용은 이미 완료.

**정지선**: 로컬 구현 + TEST 3종(§6.2) 통과까지 진행 후 보고. 서버 배포는 검증 확인 후 별도 지시.
