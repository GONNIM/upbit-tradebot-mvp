# Issue #17 구현 완료 보고

**작성일**: 2026-05-06
**Issue**: #17 - Dead Cross 상태에서 HTS 매수 시 즉시 자동매도
**상태**: ✅ 코드 구현 완료 (백테스팅 대기)

---

## 구현 요약

Dead Cross 상태에서 HTS(업비트 앱) 수동 매수 시 즉시 손절되는 문제를 해결했습니다.

### 핵심 변경사항

1. **HTS 매수 감지 시스템 (1분 주기)** - OrderReconciler에서 수량 0→양수 변화 자동 감지 + audit_trades 기록
2. **Dead Cross 예외 처리** - StopLossFilter에서 HTS 매수 포지션은 Golden Cross까지 손절 스킵
3. **절대 최대 손실 안전장치** - Dead Cross 무관하게 -5% 도달 시 강제 청산
4. **메타데이터 시스템** - account_positions 테이블에 meta 필드 추가 (hts_buy 플래그 저장)
5. **감사 로그 자동 기록** - HTS 매수 감지 시 audit_trades에 reason="HTS_BUY" 자동 저장

---

## 수정 파일 목록

### 1. services/init_db.py (스키마 마이그레이션)

**추가**: `ensure_account_positions_meta()` 함수

```python
def ensure_account_positions_meta(user_id: str):
    """
    account_positions 테이블에 meta 컬럼 추가:
      - meta: JSON 문자열 (hts_buy 플래그 등 메타데이터 저장)
    """
    conn = _connect(user_id)
    _safe_alter(conn, "ALTER TABLE account_positions ADD COLUMN meta TEXT")
    conn.commit()
    conn.close()
```

**수정**: `ensure_all_schemas()` - 마이그레이션 함수 호출 추가

---

### 2. services/db.py (DB Helper 함수)

**추가** (lines 1733-1850):

```python
def get_position_qty(user_id: str, ticker: str) -> float:
    """특정 ticker의 현재 보유 수량 조회"""

def get_position_meta(user_id: str, ticker: str) -> Dict[str, Any]:
    """특정 ticker의 포지션 메타데이터 조회"""

def update_position_meta(user_id: str, ticker: str, meta: Dict[str, Any]):
    """특정 ticker의 포지션 메타데이터 업데이트"""

def mark_position_as_hts_buy(user_id: str, ticker: str):
    """포지션에 HTS 매수 플래그 설정"""
```

---

### 3. core/position_state.py (메타데이터 지원)

**추가** (line 51):

```python
# ✅ Issue #17: HTS 매수 감지용 메타데이터
self.metadata: dict = {}  # {"hts_buy": True, "src": "manual", ...}
```

**수정**: `sync_from_wallet()` - DB에서 metadata 자동 로드

```python
# ✅ Issue #17: metadata 동기화 (hts_buy 플래그)
if hasattr(self.trader, 'user_id'):
    from services.db import get_position_meta
    self.metadata = get_position_meta(self.trader.user_id, self.ticker)
```

---

### 4. engine/order_reconciler.py (HTS 매수 감지)

**수정 1**: `__init__()` - HTS 매수 감지 주기를 1분으로 변경

```python
def __init__(self, upbit: pyupbit.Upbit, *, poll_interval=2.0, balance_sync_interval=60.0):
    # balance_sync_interval: 300.0 (5분) → 60.0 (1분)
```

**수정 2**: `_periodic_balance_sync()` (lines 329-366) - HTS 매수 감지 + audit_trades 기록

```python
if prev_qty == 0 and curr_qty > 0:
    # HTS 매수 감지
    avg_buy_price = float(bal.get("avg_buy_price", 0.0))
    logger.warning(
        f"🔔 [HTS-DETECT] HTS 매수 감지 | "
        f"ticker={ticker} | qty: {prev_qty} → {curr_qty:.6f} | "
        f"avg_price={avg_buy_price}"
    )

    # ✅ Issue #17: HTS 매수 플래그 설정
    mark_position_as_hts_buy(user_id, ticker)

    # ✅ Issue #17: audit_trades 감사 로그 기록
    insert_trade_audit(
        user_id=user_id,
        ticker=ticker,
        interval_sec=60,  # 1분 봉 기준
        bar=0,
        kind="BUY",
        reason="HTS_BUY",  # ← 감사 로그에 HTS_BUY 표시
        price=avg_buy_price if avg_buy_price > 0 else None,
        macd=None,
        signal=None,
        entry_price=avg_buy_price if avg_buy_price > 0 else None,
        entry_bar=None,
        bars_held=None,
        tp=None,
        sl=None,
        highest=None,
        ts_pct=None,
        ts_armed=None,
        timestamp=None,  # 현재 시각 자동 설정
        bar_time=None
    )
    logger.info(
        f"✅ [HTS-DETECT] audit_trades 기록 완료 | "
        f"ticker={ticker} | reason=HTS_BUY | price={avg_buy_price}"
    )
```

---

### 5. core/filters/sell_filters.py (Stop Loss 예외 처리)

**수정**: `StopLossFilter.evaluate()` (lines 32-138)

#### Phase 1: Dead Cross 상태에서 STOP_LOSS 스킵

```python
# ✅ Issue #17: HTS 매수 여부 확인
is_hts_buy = position.metadata.get('hts_buy', False)

# ✅ Issue #17: Dead Cross 상태 체크
ema_fast: Optional[float] = kwargs.get('ema_fast')
ema_slow: Optional[float] = kwargs.get('ema_slow')

# Dead Cross 상태 + HTS 매수인 경우 STOP_LOSS 스킵
if is_hts_buy and ema_fast is not None and ema_slow is not None and ema_fast <= ema_slow:
    logger.info(
        f"⏭️ [STOP_LOSS] HTS 매수 + Dead Cross 상태 → STOP_LOSS 스킵 | "
        f"pnl={pnl_pct:.2%} | ema_fast={ema_fast:.2f} <= ema_slow={ema_slow:.2f}"
    )
    return FilterResult(
        should_block=False,
        reason="SL_SKIPPED_HTS_DEAD_CROSS",
        details=f"HTS buy position held until Golden Cross (pnl={pnl_pct:.2%})"
    )
```

#### Phase 2: 절대 최대 손실 안전장치

```python
# ✅ Issue #17: 절대 최대 손실 안전장치 (5%)
MAX_LOSS_OVERRIDE = 0.05
if pnl_pct <= -MAX_LOSS_OVERRIDE:
    logger.warning(
        f"🚨 [STOP_LOSS] 절대 최대 손실 도달 (Dead Cross 무시) | "
        f"pnl={pnl_pct:.2%} > {MAX_LOSS_OVERRIDE:.2%}"
    )
    return FilterResult(
        should_block=True,
        reason="MAX_LOSS_OVERRIDE",
        details=f"Absolute max loss reached: {pnl_pct:.2%}"
    )
```

---

## 동작 원리

### 1. HTS 매수 감지 (OrderReconciler)

```
1. 1분마다 Upbit API로 잔고 조회 (_periodic_balance_sync)
2. 각 ticker의 prev_qty (DB) vs curr_qty (API) 비교
3. prev_qty == 0 && curr_qty > 0 → HTS 매수 감지
4. mark_position_as_hts_buy(user_id, ticker) 호출
5. account_positions.meta = {"hts_buy": true} 저장
6. insert_trade_audit(..., reason="HTS_BUY") 호출
7. audit_trades 테이블에 HTS_BUY 기록 저장
```

### 2. 매도 평가 시 메타데이터 로드 (PositionState)

```
1. strategy_incremental.py에서 매 봉마다 sell 필터 평가
2. position.sync_from_wallet() 호출
3. DB에서 metadata 조회 → position.metadata 업데이트
4. StopLossFilter.evaluate(position=position, ema_fast=..., ema_slow=...)
```

### 3. Stop Loss 예외 처리 (StopLossFilter)

```
1. position.metadata.get('hts_buy', False) 체크
2. ema_fast <= ema_slow (Dead Cross 상태) 체크
3. 두 조건 모두 만족 시 → STOP_LOSS 스킵
4. 단, pnl <= -5% 시 → 강제 청산 (안전장치)
```

---

## 백테스팅 시나리오

### 테스트 케이스 1: 정상 동작 (HTS 매수 → Golden Cross 대기)

**Before (Issue #17 발생)**:
```
11:23 BUY @ 2049원 (봇 자동)
15:19 SELL @ 2024원 (-1.4% 손절) ❌
```

**After (수정 후)**:
```
11:23 BUY @ 2049원 (HTS 수동)
15:19 HOLD (Dead Cross 상태, STOP_LOSS 스킵) ✅
17:00 SELL @ 2060원 (Golden Cross or Take Profit) ✅
```

### 테스트 케이스 2: 절대 최대 손실 안전장치

```
11:23 BUY @ 2049원 (HTS 수동)
12:00 price = 1947원 (-5.0% 도달) → 강제 청산 ✅
```

### 테스트 케이스 3: force_buy (사이트 수동매수)

```
11:23 BUY @ 2049원 (force_buy, src="manual")
15:19 SELL @ 2024원 (-1.4% 손절) ✅  ← 정상 손절 유지
```

---

## 테스트 체크리스트

### 로컬 테스트

- [ ] 스키마 마이그레이션 정상 실행 확인
  ```bash
  python3 -c "from services.init_db import ensure_all_schemas; ensure_all_schemas('mcmax33')"
  ```

- [ ] HTS 매수 감지 주기 확인 (1분)
  ```bash
  # 로그에서 확인:
  # [OR] periodic sync completed: 1 user(s), interval=60s (HTS 매수 감지 포함)
  tail -f mcmax33_engine_debug.log | grep "periodic sync"
  ```

- [ ] HTS 매수 감지 정확도 (수량 0→양수)
  ```sql
  -- account_positions 메타데이터 확인
  SELECT ticker, meta FROM account_positions WHERE user_id='mcmax33';
  -- meta = {"hts_buy": true} 확인
  ```

- [ ] HTS 매수 감사 로그 기록 확인
  ```sql
  -- audit_trades에서 HTS_BUY reason 확인
  SELECT timestamp, ticker, type, reason, price, entry_price
  FROM audit_trades
  WHERE user_id='mcmax33' AND reason='HTS_BUY'
  ORDER BY timestamp DESC LIMIT 10;
  ```

- [ ] Dead Cross 상태에서 STOP_LOSS 스킵 동작
  ```bash
  # 로그에서 확인:
  # ⏭️ [STOP_LOSS] HTS 매수 + Dead Cross 상태 → STOP_LOSS 스킵
  tail -f mcmax33_engine_debug.log | grep "STOP_LOSS"
  ```

- [ ] Golden Cross 복귀 시 정상 손절 재활성화
- [ ] 절대 최대 손실(5%) 안전장치 동작
- [ ] force_buy는 정상 손절 유지 (hts_buy=False)

### 서버 배포 후 테스트

- [ ] 1시간 실시간 로그 모니터링
- [ ] HTS 매수 감지 로그 확인 (1분 주기)
  ```bash
  ssh root@orionhunter7.cafe24.com "tail -f /root/mcmax33_engine_debug.log" | grep "HTS-DETECT"
  ```
- [ ] audit_trades 테이블 확인 (reason="HTS_BUY")
  ```bash
  ssh root@orionhunter7.cafe24.com "sqlite3 /root/tradebot_mcmax33.db 'SELECT * FROM audit_trades WHERE reason=\"HTS_BUY\" ORDER BY timestamp DESC LIMIT 5'"
  ```
- [ ] audit_sell_eval 테이블 확인 (reason="SL_SKIPPED_HTS_DEAD_CROSS")

---

## 주의사항

1. **사용자 승인 필수** - 로컬 테스트 완료 후 사용자 승인 받고 서버 배포
2. **stop_loss 파라미터 절대 수정 금지** - 사용자 고유 권한
3. **절대 최대 손실 안전장치** - Dead Cross 상태에서도 -5% 도달 시 강제 청산
4. **force_buy와 구분** - 사이트 수동매수(force_buy)는 정상 손절 유지

---

## 롤백 계획

문제 발생 시:

```bash
# Git 커밋 전 백업 확인
git log --oneline -5

# 롤백 (커밋 ID 확인 후)
git revert <commit-id>

# 또는 hard reset (주의!)
git reset --hard HEAD~1
```

---

## 관련 문서

- `docs/issues/issue-17.md` - 문제 분석 및 근본 원인
- `.claude/lessons-learned.md` - 교훈 #17 추가
- `.claude/context/project-rules.md` - Issue 인덱스 업데이트

---

**다음 단계**: 로컬 백테스팅 후 사용자 승인 대기
