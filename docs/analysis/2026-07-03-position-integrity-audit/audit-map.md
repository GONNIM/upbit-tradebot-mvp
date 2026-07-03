# Position Integrity Audit Map — 2026-07-03

**작성일**: 2026-07-03
**계기**: 사용자 클레임 2건 (정체 포지션 필터 미발동 / SP6 매수 후 자동 손절 실패 → HTS 강제매도)
**목적**: 근본 결함 + 재발 가능 결함 후보 전수 파악. 성급한 hotfix 배제, 통합 수정 기획 근거 확립
**대응 프로세스**: 사용자 결정 1-a (Phase A 감사) + 2-i (봇 매매 중단). 봇 `inactive (dead)` since 2026-07-03 19:57:20 KST
**본 문서 상태**: 진행 중 — 각 항목 확인 완료 시 상태 업데이트

관련:
- 사용자 지시 원문: "근본적인 문제를 찾아서 해결하고 또다른 오작동 가능성 또한 발생해서는 안된다. 사업의 존망이 걸려있는 것만큼 철저하게 순서대로 정확하게 대응"
- 배포 원칙: [[feedback_deploy_only_when_complete]] — Phase A~D 완료 후 단일 배포

---

## 감사 항목 요약 (12건)

| ID | flow / 항목 | 심각도 | 상태 |
|---|---|---|---|
| A1 | HTS 매수 감지 시 in-memory position 세팅 | 🔴 결함 확정 | ✅ 확인 완료 |
| A2 | 봇 마켓 매수 (`trader.buy_market`) → position open 경로 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A3 | 봇 LIMIT 매수 (SP6) submit → 부분 체결 → 완전 체결 → position 반영 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A4 | `has_recent_bot_buy_for_ticker(within_seconds=30)` window | 🔴 결함 확정 | ✅ 확인 완료 |
| A5 | 서비스 재시작 시 open position reload | 🟡 확인 필요 | ⏳ 진행 예정 |
| A6 | Hot Reload (조건 변경) 시 position 승계 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A7 | HTS 매도 감지 (잔고 감소 → has_position=False 처리) 정합성 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A8 | `bars_held ≤ 0` 안전 로직 원설계·발동 이력 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A9 | Stale filter가 사용하는 `position.entry_ts` 세팅 경로 전수 | 🔴 결함 후보 | ⏳ 진행 예정 (16:40 매수 케이스에서 elapsed_hours=0 재확인) |
| A10 | 12:24 봉 누락 (REST reconcile 완전성) | 🟢 별건 | ⏳ 진행 예정 |
| A11 | audit_trades / audit_sell_eval / PositionState 3중 진실 소스 정합성 | 🟡 확인 필요 | ⏳ 진행 예정 |
| A12 | position 상태 지속화 (프로세스 죽음 → 재기동 → 상태 복구) | 🟡 확인 필요 | ⏳ 진행 예정 |

---

## 항목 상세

### A1 — HTS 매수 감지 시 in-memory position 세팅 부재 🔴

**결함 확정**.

#### 현 코드 흐름

`engine/order_reconciler.py:_periodic_balance_sync` (1분 주기):

```
Upbit REST get_balances()
  ↓
잔고 증가 감지 (curr_qty > prev_qty + 1e-8)
  ↓
has_recent_bot_buy_for_ticker(within_seconds=30) 스킵 판정
  ↓
HTS 판정 시:
  ├─ mark_position_as_hts_buy(user_id, ticker)     ← ①
  ├─ insert_trade_audit(entry_bar=None, ...)       ← ②
  └─ update_position_from_balances(...)            ← ③
```

**①** `mark_position_as_hts_buy` (services/db.py:2177):
- DB `account_positions.meta` JSON에 `hts_buy=True` 만 추가
- **in-memory `PositionState` 객체는 전혀 건드리지 않음**
- `entry_bar` / `entry_ts` / `avg_price` / `highest_since_entry` 어떤 것도 세팅 안 함

**③** `update_position_from_balances` (services/db.py:1776):
- DB `account_positions` 테이블에 (수량, 잠금, avg_buy_price=entry_price) 저장
- 역시 **in-memory `PositionState` 건드리지 않음**

#### 격차 위치

- DB 진실 소스: `account_positions` — HTS 매수 반영됨 ✓
- in-memory 진실 소스: `PositionState` (strategy 객체 내부) — 반영 안 됨 ❌

이후 매 봉 SELL 평가 시 사용되는 것은 in-memory `PositionState` 이며, 이곳의 `entry_bar=None` 상태가 유지된다. 따라서:

- `position.get_bars_held(current_bar) = current_bar - None` → 예외/0/음수
- `strategy_incremental.py:1053` 안전 로직 `bars_held ≤ 0` → **SELL 통째 차단**

#### 실측 증거 (오늘 10:25 시나리오)

```
10:25:26 audit_trades BUY HTS_BUY entry_bar=NULL      (id=396)
10:25:32 audit_trades BUY EMA_GC   entry_bar=NULL     (id=397)
10:34:36 로그: [EMA] bars_held=0 (음수/0) — SELL 차단
         entry_bar=None, current_bar=1564
         action=HOLD | pos=True
```

`pos=True` 인 이유는 별도 `has_position` sync 경로가 존재함(→ A11 조사 대상). 하지만 그 sync 도 `entry_bar` 는 채우지 못하고 있다.

#### 후속 확인 필요

- **① 어디서 in-memory `PositionState.has_position=True` 로 세팅되는가?** 별도 sync 함수 존재 확인 필요 → A11 조사
- **② `open_position()` (position_state.py:130) 이 HTS 감지 경로에서 호출되지 않는 것은 의도된 설계인가?** → 개발자 원의도 파악 필요 (Issue #17 관련 코멘트 재검토)

---

### A4 — has_recent_bot_buy_for_ticker 30초 window 🔴

**결함 확정**.

#### 현 코드

`services/db.py:716`

```python
def has_recent_bot_buy_for_ticker(user_id, ticker, within_seconds=30):
    """B3-잔여: audit_trades 최근 within_seconds 내 BUY 기록 확인.
    HTS 매수 감지 시 봇 BUY 와 충돌 방지용."""
    cur.execute(
        "SELECT timestamp FROM audit_trades WHERE ticker=? AND type='BUY' "
        "ORDER BY id DESC LIMIT 1",
        (ticker,),
    )
    row = cur.fetchone()
    ...
    return 0 <= (now - ts).total_seconds() <= within_seconds
```

호출자: `order_reconciler.py:440` (HTS 판정 스킵 로직)

#### 결함 근거

- SP6 정책: `fixed_price_buy_wait_bars=5` (현재 서버 조건 파일 실측)
- LIMIT BUY 흐름: submit → 최대 5봉(5분=300초) 대기 → 체결/취소 → 잔고 반영
- `has_recent_bot_buy_for_ticker` window = **30초**
- 즉 **LIMIT 체결이 30초를 넘기면 봇 매수를 HTS 매수로 오판정**

#### 파생 결함

- 오판정 시 `mark_position_as_hts_buy` 실행 → position에 `hts_buy=True` 세팅
- Policy P-3: "hts_buy 는 매도 결정에 영향 X" — 원칙상 문제 없어야 하지만
- **A1 격차로 인해 사실상 SELL 차단** — Policy P-3 위반 결과 발생

#### 후속 확인 필요

- **① audit_trades BUY row 기록 시점** — LIMIT submit 시점인가 체결 시점인가? (A3 조사)
- **② 봇 LIMIT BUY 미체결 상태도 skip 조건에 포함해야 하는가?** — orders 테이블에 pending BUY 있으면 skip

---

### A9 — Stale filter `position.entry_ts` 세팅 경로 🔴

**결함 확정 (16:40 매수 실측 근거)**.

#### 진입 경로 3가지 매핑

| 경로 | 코드 위치 | 세팅되는 필드 | entry_ts 세팅? |
|---|---|---|---|
| **P1** open_position (정상 봇 마켓/체결 매수) | `strategy_engine.py:579~584` | qty, avg_price, entry_bar, entry_ts, highest_since_entry | ✅ |
| **P2** POSITION-SYNC 자동 복구 (매 봉 방어) | `strategy_engine.py:210~219` | has_position=True, qty, avg_price, entry_bar | ❌ **누락** |
| **P3** live_loop 부팅 시 복구 | `live_loop.py:438~454` | has_position=True, qty, avg_price, entry_bar (실패 시 avg_price=None) | ❌ **누락** |

#### 실측 증거 (오늘 16:40 EMA_GC 매수)

- audit_trades id=398 EMA_GC BUY 기록 존재
- 그러나 로그에 `✅ BUY 체결 | qty=...` (P1) 부재
- 16:41~ 매 15~30초마다 `[DB] last BUY (with status filter=True) => {'price': 1161.0, 'entry_bar': 201}` 로그 반복 = **매 봉 P2 자동 복구 조회 반복**
- 결과: `entry_price=1138.0`(다른 캐시?), `entry_bar` 세팅되나 `entry_ts=None` → `stale_elapsed_hours=0.0` 매 봉 유지

#### 근본 원인

`strategy_engine.py:210~219` 자동 복구 블록에 `self.position.entry_ts = <시각>` 세팅 라인 없음. `open_position()` 을 우회하는 직접 필드 세팅이 entry_ts를 빠뜨림.

#### 후속 확인 필요

- **P1 open_position 이 16:40에 왜 호출 안 됐는지** 조사 (`trader.buy_market` 결과 handling / SP6 pending release 흐름)
- **P3 부팅 복구 경로 (live_loop.py:453) `avg_price=None` 비상 모드** — SL/TP 계산 불가 시나리오

---

### A11 — 3중 진실 소스 정합성 🔴

**심각 격차 확정**.

| 진실 소스 | 위치 | HTS 매수 반영 | 봇 매수 반영 | Stale 계산 사용 |
|---|---|---|---|---|
| `account_positions` (DB) | services/db.py | ✅ (`update_position_from_balances`) | ✅ | ❌ (매 봉 조회는 하지만 실 계산엔 미사용) |
| `audit_trades` (DB) | services/db.py | ✅ (entry_bar=NULL) | ✅ (entry_bar=NULL) | ❌ |
| `PositionState` (in-memory) | core/position_state.py | ❌ **완전 무시** | ✅ P1만 (P2/P3 부분만) | ✅ entry_ts 사용 (그러나 세팅 누락됨) |

**심각도**: 
- DB에는 매수 사실이 있음
- in-memory에는 has_position=True 만 있고 entry_ts는 없음
- **매도 필터가 사용하는 유일한 소스인 in-memory의 entry_ts가 세팅 안 되어 stale 영원 미발동**

---

### A8 — bars_held ≤ 0 안전 로직 🔴

**의도된 안전 장치가 오히려 정상 매도까지 차단하는 확대 결함**.

`strategy_incremental.py:1053~1065`:
```python
if bars_held <= 0:
    err_msg = f"⚠️ [EMA] bars_held={bars_held} (음수/0) — 데이터 무결성 결손 감지. SELL 차단 ..."
    logger.error(err_msg)
    ...
    return Action.HOLD   # ← sell_filter_manager 전체 스킵
```

**원설계 의도**: `estimate_bars_held_from_audit` 보정 로직이 잘못된 SELL을 유도할 수 있어 제거하고 방어적 HOLD로 대체 (comment 근거).

**결함**: entry_bar=None 인 P2 자동 복구 케이스가 만성적으로 발생하면 이 로직이 상시 활성 → 매도 필터 시스템 전체가 무력화. 즉 A1/A9의 하류 결과지만 **매도 시스템 전체를 정지시키는 결정적 위치**.

**설계 재검토 필요**: audit_trades에서 실제 bars_held 는 log에 이미 나옴 (`[BARS_HELD] BUY=... 이후 SELL 평가 N개 → bars_held=N`). 이 값을 신뢰할지 여부가 관건.

---

### F7 (신규 추가) — 부팅 시 `avg_price=None` 비상 모드 🔴

`live_loop.py:450~454`:
```python
# ⚠️ DB에서 진입가를 찾지 못했지만 지갑에 코인이 있는 경우
# qty만이라도 설정해서 비상 매도는 가능하도록
position.has_position = True
position.qty = actual_qty
position.avg_price = None  # 진입가 불명
```

**결함**: avg_price=None 이면 SL/TP/Trailing 모두 계산 불가 (`get_pnl_pct` 에서 avg_price 필요). 실제로는 "비상 매도"조차 불가능한 상태.

**발동 조건**: 지갑에 코인 있지만 DB 에서 seed 못 찾을 때 (엔진 재시작 + audit_trades 정리 + upbit avg_buy_price 캐시 부재의 조합).

---

## 감사 진행 로그

| 일시 | 항목 | 상태 |
|---|---|---|
| 2026-07-03 19:57 | 준비 | 봇 매매 중단 (systemctl stop tradebot), inactive 확인 |
| 2026-07-03 20:00 | A1 | HTS 감지 시 in-memory PositionState 세팅 부재 확정 |
| 2026-07-03 20:00 | A4 | has_recent window 30초 vs SP6 5봉 mismatch 확정 |
| 2026-07-03 20:15 | A9 | 진입 경로 3가지(P1/P2/P3) 매핑 + P2/P3에서 entry_ts 세팅 누락 확정 |
| 2026-07-03 20:15 | A11 | 3중 진실 소스 격차 확정 |
| 2026-07-03 20:15 | A8 | bars_held ≤ 0 안전 로직이 SELL 시스템 전체 무력화 확정 |
| 2026-07-03 20:15 | F7 | avg_price=None 비상 모드 결함 확정 (부팅 경로) |
| 2026-07-03 20:30 | A2 | fixed_price_buy_enabled=True 시 buy_market 대신 buy_limit 강제 → P1 절대 미경유 확정 |
| 2026-07-03 20:30 | A3 | SP6 LIMIT 흐름은 pending release에서 open_position 호출 없음 → 필연적 P2 우회 확정 |
| 2026-07-03 20:35 | A5 | 재시작 P3(_seed_entry_price_from_db) 는 F7 결함 재확인 (avg_price=None 비상 경로) |
| 2026-07-03 20:35 | A6 | Hot Reload (reload_conditions) 는 self.position 안 건드림 ✓ 안전 |
| 2026-07-03 20:35 | A7 | HTS 매도 감지는 close_position(ts=None) 정상 리셋. 다만 audit_trades에 SELL 기록 안 됨 (별건 G2) |
| 2026-07-03 20:35 | A10 | 12:24 봉 누락 확인 (실측: 12:22, 12:23, 12:25, 12:26 존재, 12:24 부재). Stale 결함과 직접 관계 없음 — 별건 G1 |
| 2026-07-03 20:35 | A12 | 프로세스 죽음 → 재기동 시 P3 경유 = F3 확대 (별도 결함 아님) |

---

### A2 — 봇 매수 함수 선택 로직 🔴

**결함 확정: `fixed_price_buy_enabled=True` 상태에서 P1 절대 미경유**.

`strategy_engine.py:529~560`:
```python
fixed_price_mode = (not self.trader.test_mode) and bool(_buy_cond.get("fixed_price_buy_enabled", False))
if fixed_price_mode:
    result = self.trader.buy_limit(...)   # ← LIMIT 강제
else:
    result = self.trader.buy_market(...)  # P1 open_position 호출 경로
```

**현재 사용자 conditions**: `fixed_price_buy_enabled: true` → 오늘 이후 **100% buy_limit 경유** → **F8/A3와 결합해 stale filter 영구 무효화**.

---

### A3 — SP6 LIMIT pending release 흐름 🔴

**결함 확정: pending release 시 open_position 호출 부재**.

`strategy_engine.py:109~135` `_maybe_release_limit_pending`:
```python
if self.bar_count > self._pending_buy_bar + (self._pending_buy_wait_bars - 1):
    self.position.set_pending(False)
    self._pending_buy_uuid = None
    self._pending_buy_bar = None
    # ⚠️ open_position 호출 없음 — 체결된 경우 P2 자동 복구 우회
```

**결함 위력**:
- LIMIT submit → `open_position` 보류 (result["limit_pending"]=True 시)
- 5봉 대기 후 pending release — 이 시점에서 이미 체결 완료됐어도 `open_position` 호출 없음
- 다음 봉 `_reconcile_position_with_wallet` (Case 2) → **P2 자동 복구 진입** → **entry_ts=None** (F3 결함 발동)

---

### A6 — Hot Reload 시 position 승계 ✅ 안전

`strategy_incremental.py:732~` `reload_conditions`: 임계값·flag만 update, `self.position` 절대 접근하지 않음. **결함 없음**.

---

### A7 — HTS 매도 감지 정합성 (Case 1) 🟡 별건

`strategy_engine.py:163~173`: 지갑 코인 없고 memory has_position=True → `close_position(ts=None)`. 리셋 자체는 정상.

다만 **audit_trades 에 SELL row 자동 기록 없음** — 사용자가 HTS로 손절한 경우 봇 audit 통계에 누락. 사후 분석·손익 계산 부정확.

**분류**: G2 (별건 후속 개선). Stale 결함과 직접 관계 없음.

---

### A10 — 12:24 봉 누락 🟡 별건

실측 (audit_sell_eval):
```
12:22:00 ✓
12:23:00 ✓
12:24:00 ✗ 부재
12:25:00 ✓
12:26:00 ✓
```

REST reconcile 로직에서 12:24 봉을 skip 한 원인은 별도 조사 필요. Stale filter 결함(F3)과 직접 관계 없음 — 12:22, 12:23, 12:25 시점에서도 stale 발동 안 됐음.

**분류**: G1 (별건 후속 개선).

---

## 확정 결함 종합 (9건)

| ID | 위치 | 결함 | 심각도 | 사용자 클레임 연결 |
|---|---|---|---|---|
| **F1** | `order_reconciler.py:459~479` + `mark_position_as_hts_buy` | HTS 감지 시 in-memory PositionState 무시 | 🔴 | 클레임 A/B 모두 |
| **F2** | `services/db.py:716` | has_recent window 30초 vs SP6 5봉 mismatch | 🔴 | 클레임 B |
| **F3** | `strategy_engine.py:210~219`, `live_loop.py:438~454` | P2/P3 경로에서 `entry_ts` 세팅 누락 | 🔴 | 클레임 A |
| **F4** | `strategy_incremental.py:1053~1065` | `bars_held ≤ 0` 안전 로직이 매도 시스템 전체 스킵 | 🔴 | 클레임 A/B 모두 |
| **F5** | `live_loop.py:450~454` | 부팅 시 `avg_price=None` 비상 모드 (SL/TP 계산 불가) | 🔴 | 잠재 |
| **F6** | 3중 진실 소스 격차 | account_positions / audit_trades / PositionState 정합성 부재 | 🔴 | 근본 |
| **F7** | `strategy_engine.py:529~560` | `fixed_price_buy_enabled=True` 시 buy_market 미경유 = P1 절대 안 됨 | 🔴 | 클레임 B (핵심) |
| **F8** | `strategy_engine.py:109~135` | SP6 pending release 시 `open_position` 호출 없음 → P2 우회 필연 | 🔴 | 클레임 B (핵심) |
| **F9** | `strategy_engine.py:137~230` | `_reconcile_position_with_wallet` 매 봉 실행 + Case 2 P2 자동 복구 상시 활성 = F3 상시 재현 | 🔴 | 클레임 A (핵심) |

## 별건 후속 개선 (2건, 이번 수정 범위 밖)

| ID | 항목 | 사유 |
|---|---|---|
| G1 | 12:24 봉 누락 (REST reconcile 완전성) | Stale 결함과 무관, 별건 데이터 무결성 개선 |
| G2 | HTS 매도 시 audit_trades SELL 기록 없음 | 사후 분석용 개선, 매매 로직 결함 아님 |

---

## 근본 원인 축약

**한 축**: **in-memory `PositionState` 의 진입 정보(특히 `entry_ts`)를 세팅하는 유일한 경로는 P1 `open_position()` 인데, 실제 운영에서는 SP6 LIMIT 흐름(F7/F8)이 P1 을 우회하여 P2/P3 자동 복구 경로(F3)로만 진입한다. 결과적으로 `entry_ts=None` 상시 유지 → Stale filter 영구 무효.**

**두 축**: **HTS 매수(F1) 시에도 in-memory 상태 세팅이 없어 다른 매도 필터(F4) 안전 로직이 SELL 을 통째 차단한다.**

**세 축**: **`has_recent`(F2) window 30초가 SP6(5봉) 정책과 불일치하여 봇 매수를 HTS로 오판정 → F1/F4 결함이 봇 매수 흐름에도 재현.**

---

## 통합 수정 방향 (Phase B 기획안 착수 시 상세화)

원칙: **근본 하나를 고쳐 여러 하류 결함이 자동 해소**되도록 설계.

| 수정 축 | 접근 |
|---|---|
| **① in-memory Position 상태를 P1 이외 경로에서도 완전 세팅** | `PositionState.reset_from_wallet(qty, avg_price, entry_bar, entry_ts, source)` 통합 진입 API 신설. P2/P3/HTS 감지 모두 이 API로 통일. entry_ts는 `bar.ts` 또는 `now_kst()` 강제 세팅. `open_position()` 도 내부에서 이 API 호출로 정리 가능 |
| **② has_recent 로직 재설계** | audit_trades BUY row 만 보지 말고 `orders` 테이블의 pending LIMIT BUY 도 함께 확인. window 는 SP6 wait_bars × interval_sec 을 기준으로 동적 계산 |
| **③ bars_held ≤ 0 안전 로직 대체** | audit_trades에서 실제 bars_held 산출 (이미 로그에 있음). in-memory `entry_bar=None` 자체를 "결손"이 아니라 "복구 필요"로 분류하고 즉시 sync 시도. SELL 차단은 오히려 위험 |
| **④ SP6 pending release 시 실체결 감지 → open_position 호출** | Reconciler 가 체결 확정 시점에 이벤트 발행 → strategy_engine 이 해당 이벤트로 `open_position` 호출 (LIMIT-fill callback 추가) |
| **⑤ avg_price=None 비상 모드 제거** | 부팅 시 seed 실패 = 안전하게 has_position=False 유지 + Telegram CRITICAL 알림. "비상 매도"는 사용자 결정 |

각 축의 상세 설계·리스크·테스트 시나리오는 Phase B 기획안에서.

---

## Phase A 감사 완료 상태

- **총 감사 항목**: 12건
- **확정 결함**: 9건 (F1~F9)
- **별건 후속**: 2건 (G1, G2)
- **결함 없음 확인**: 1건 (A6 Hot Reload)
- **본 지도**: Phase B 기획안 근거 자료로 확정

**감사 완료 시각**: 2026-07-03 20:40 KST (봇 stopped 상태 유지 중)
