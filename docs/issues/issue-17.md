### 🔴 Issue #17: Dead Cross 상태에서 HTS 매수 시 즉시 자동매도

**발생일**: 2026-05-06
**심각도**: 🔴 Critical (사용자 클레임 발생, 트레이딩 로직 근본 문제)

#### 문제

사용자가 Dead Cross 상태(ema_fast < ema_slow)에서 HTS(업비트 거래소 앱)로 수동 매수 후, 2~3분 내 자동 매도됨:

**실제 거래 로그 (5월 4일)**:
```
11:23:32 | BUY  | EMA_GC     | 2049원 | entry_price=2049 | (봇 자동매수)
15:19:56 | SELL | STOP_LOSS  | 2024원 | entry_price=2048 | bars_held=75
15:38:17 | SELL | STOP_LOSS  | 2019원 | entry_price=2049 | bars_held=82
21:08:13 | SELL | STOP_LOSS  | 1992원 | entry_price=2049 | bars_held=195
```

**audit_sell_eval 로그 분석**:
```json
{
  "cross_status": "Golden",  // ← Dead Cross 아님!
  "ema_dc_detected": 0,      // ← Dead Cross 이벤트 없음
  "trigger_reason": "STOP_LOSS",
  "pnl_pct": -0.0131,        // -1.31% 손실
  "stop_loss": 0.011         // 1.1% 손절 기준
}
```

**사용자 기대 동작**:
- Dead Cross 상태에서 HTS 매수 → Golden Cross까지 보유 유지
- 손절(STOP_LOSS)은 Golden Cross 상태에서만 작동

**실제 동작**:
- Dead Cross 상태 무관하게 손실률 > 1.1% 시 즉시 매도
- 사용자 불만: "D/C에서 매수했는데 왜 바로 팔아?"

#### 근본 원인

**Codex Review 결과 (2026-05-06)**:

1. **SellFilterManager 필터 실행 순서**:
   ```python
   # core/strategy_incremental.py:557-577
   StopLossFilter       # 1순위 (CORE_STRATEGY)
   TakeProfitFilter     # 2순위
   TrailingStopFilter   # 3순위
   DeadCrossFilter      # 4순위 ← 도달하지 못함
   ```

2. **조기 반환 메커니즘**:
   ```python
   # core/filters/__init__.py:86-97
   for filter_instance in self.filters:
       result = filter_instance.evaluate(**kwargs)
       if result.should_block:
           return result  # ← 첫 번째 매도 신호에서 즉시 반환
   ```

3. **DeadCrossFilter의 실제 동작** (Codex 발견):
   ```python
   # core/filters/sell_filters.py:327-343
   ema_dead_cross: bool = kwargs.get('ema_dead_cross', False)
   if ema_dead_cross:  # ← "Dead Cross 이벤트"만 감지
       return FilterResult(should_block=True, reason="EMA_DC")
   ```
   - ❌ "현재 Dead 상태 (ema_fast < ema_slow)" 감지 아님
   - ✅ "Dead Cross 발생 이벤트" 감지 (이전 봉에서 전환)
   - **결론**: 필터 순서를 바꿔도 "이미 Dead 상태에서 HTS 매수" 케이스는 해결 안 됨

4. **핵심 문제**:
   - StopLossFilter가 Dead Cross 상태 체크 없이 손실률만 평가
   - HTS 매수든 force_buy든 모든 포지션에 동일하게 손절 적용
   - Dead Cross 상태 보유 정책 미구현

#### 왜 놓쳤나?

1. **필터 설계 시 순서 의존성 미고려**
   - CORE_STRATEGY 카테고리 내 필터 간 상호작용 검토 부족
   - "손절 vs Dead Cross" 우선순위 정책 부재

2. **DeadCrossFilter의 제한된 역할**
   - "이벤트" 감지만 가능, "상태" 감지 불가
   - HTS 매수 시나리오 테스트 부족

3. **HTS 매수 vs 봇 자동매수 구분 부재**
   - 모든 포지션에 동일한 손절 정책 적용
   - 수동 매수는 별도 관리 필요 (사용자 의도 존중)

#### 교훈

**핵심 교훈**:
> Dead Cross 상태에서 수동 매수한 포지션은 Golden Cross까지 보유 정책 필요.
> STOP_LOSS 필터에 시장 상태(Dead/Golden) 예외 처리 추가.

**상세 교훈**:

1. **필터 실행 순서의 중요성**
   - 조기 반환 메커니즘으로 하위 필터 미도달 가능
   - 순서 의존적 로직은 명확한 우선순위 정책 필요

2. **이벤트 vs 상태 구분**
   - `ema_dead_cross`: 전환 이벤트 (1회성)
   - `ema_fast < ema_slow`: 현재 상태 (지속)
   - 정책에 따라 적절한 조건 사용 필요

3. **수동 매수 구분 정책**
   - force_buy (우리 사이트): 메타데이터 `src="manual"` 존재
   - HTS 매수 (외부): 메타데이터 없음, 수량 0→양수 변화로 감지
   - `hts_buy` 플래그로 구분 필요

4. **Codex Review의 가치**
   - 초기 분석의 맹점 발견 (DeadCrossFilter 역할 오해)
   - 잠재적 부작용 사전 발견 (모든 포지션 손절 비활성화 위험)

#### 수정 (Codex 권장 방안)

**Phase 1: Dead Cross 상태에서 STOP_LOSS 스킵 (HTS 매수 전용)**

파일: `core/filters/sell_filters.py:StopLossFilter.evaluate()`

```python
def evaluate(self, **kwargs) -> FilterResult:
    position: PositionState = kwargs.get('position')
    current_price: float = kwargs.get('current_price')

    if position is None or current_price is None:
        return FilterResult(should_block=False, reason="NO_DATA", ...)

    # ✅ NEW: HTS 매수 여부 확인 (메타데이터 없음)
    is_hts_buy = position.metadata.get('hts_buy', False)

    # ✅ NEW: Dead Cross 상태 체크
    ema_fast: Optional[float] = kwargs.get('ema_fast')
    ema_slow: Optional[float] = kwargs.get('ema_slow')

    # Dead Cross 상태 + HTS 매수인 경우 STOP_LOSS 스킵
    if is_hts_buy and ema_fast is not None and ema_slow is not None and ema_fast <= ema_slow:
        logger.info(
            f"⏭️ STOP_LOSS 스킵 (HTS 매수 + Dead Cross 상태) | "
            f"ema_fast={ema_fast:.2f} <= ema_slow={ema_slow:.2f}"
        )
        return FilterResult(
            should_block=False,
            reason="SL_SKIPPED_HTS_DEAD_CROSS",
            details=f"HTS buy position held until Golden Cross"
        )

    # 기존 STOP_LOSS 로직...
    pnl_pct = position.get_pnl_pct(current_price)
    # ...
```

**Phase 2: HTS 매수 감지 로직 (OrderReconciler)**

파일: `engine/order_reconciler.py:_periodic_balance_sync()`

```python
def _periodic_balance_sync(self):
    """
    주기적 잔고 동기화 (기본 5분마다)
    - HTS 매수 감지: Ticker 수량 0 → 양수 변화
    """
    # ...기존 코드...

    for bal in balances:
        currency = bal.get("currency", "").upper()
        if currency and currency != "KRW":
            ticker = f"KRW-{currency}"

            # ✅ NEW: 이전 수량 조회
            prev_qty = get_position_qty(user_id, ticker)  # DB 조회
            curr_qty = float(bal.get("balance", 0.0))

            # ✅ HTS 매수 감지: 0 → 양수
            if prev_qty == 0 and curr_qty > 0:
                logger.warning(
                    f"🔔 HTS 매수 감지 | ticker={ticker} | "
                    f"qty: {prev_qty} → {curr_qty}"
                )
                # ✅ 포지션에 hts_buy 플래그 추가
                mark_position_as_hts_buy(user_id, ticker)

            update_position_from_balances(user_id, ticker, balances)
```

**Phase 3: 안전장치 추가**

```python
# Dead Cross 상태에서도 절대 최대 손실은 강제 청산
MAX_LOSS_OVERRIDE = 0.05  # 5%

if pnl_pct <= -MAX_LOSS_OVERRIDE:
    logger.warning(
        f"🚨 절대 최대 손실 도달 (Dead Cross 무시) | "
        f"pnl={pnl_pct:.2%} > {MAX_LOSS_OVERRIDE:.2%}"
    )
    return FilterResult(
        should_block=True,
        reason="MAX_LOSS_OVERRIDE",
        details=f"Absolute max loss reached: {pnl_pct:.2%}"
    )
```

#### 검증

**백테스팅 시나리오 (5월 4일 데이터)**:

```python
# Before: HTS 매수 → 즉시 손절
11:23 BUY @ 2049 (봇 자동)
15:19 SELL @ 2024 (-1.4% 손절) ❌

# After: HTS 매수 → Golden Cross까지 대기
11:23 BUY @ 2049 (봇 자동)
15:19 HOLD (Dead Cross 상태, STOP_LOSS 스킵) ✅
17:00 SELL @ 2060 (Golden Cross or Take Profit) ✅
```

**테스트 체크리스트**:
- [ ] HTS 매수 감지 정확도 (수량 0→양수)
- [ ] Dead Cross 상태에서 STOP_LOSS 스킵 동작
- [ ] Golden Cross 복귀 시 정상 손절 재활성화
- [ ] 절대 최대 손실(5%) 안전장치 동작
- [ ] force_buy는 정상 손절 유지 (hts_buy=False)

#### 영향 범위

**수정 파일**:
- `core/filters/sell_filters.py` (StopLossFilter)
- `engine/order_reconciler.py` (_periodic_balance_sync)
- `services/db.py` (mark_position_as_hts_buy, get_position_qty)
- `core/position_state.py` (metadata 필드)

**테스트 필요**:
- 로컬 백테스팅 (5월 4~6일 데이터)
- 서버 배포 후 1시간 실시간 모니터링

**롤백 계획**:
- Git 커밋 전 백업
- 문제 발생 시 `git revert` 즉시 실행

#### 관련 Issue

- Issue #11: BACKFILL 지표 오염 (지표 상태 보존 중요성)
- Issue #16: 워크플로우 위반 (사용자 승인 필수)

#### 참고 문서

- Codex Review: 2026-05-06 (분석 정확성 검증)
- `docs/analysis/trailing-stop-logic-analysis.md` (매도 필터 로직 분석)
- `core/filters/README.md` (필터 시스템 설계)

---

**작성일**: 2026-05-06
**작성자**: Claude Code (Codex Review 기반)
**최종 업데이트**: 2026-05-06
