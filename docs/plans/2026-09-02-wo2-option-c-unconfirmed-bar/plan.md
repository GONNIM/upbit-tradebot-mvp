# WO-2 옵션 C · 미확정 봉 진입 배선 (소계획서)

**작성일**: 2026-09-02
**상태**: 계획서 작성 완료, 사용자 검토·승인 대기
**전제**: WO-2 재적용 배포(2026-09-02 `v1.2026.09.02.1424`, HEAD `17bb386`) 완료.
`_pending_orders` 큐와 `_execute_buy_or_defer`, `_resolve_pending_buy` 훅이
배선되어 있으나 현행 흐름에서는 자연 발생 트리거가 없다. 옵션 C가 이
배선의 마지막 조각이다.

---

## 1. 목적

`fetch_confirmed_candle`이 재시도를 모두 소진하고도 실패한 봉(그러나 실제로
거래는 존재하는 봉)이 현재는 평가 없이 건너뛰어진다
(`engine/live_loop.py:1329~1331`). 이 봉을 **미확정 상태로 평가**하고
**발주만 지연**시키는 경로를 배선한다.

이 시나리오는 로컬 회선에서 자주 관측된다. `journalctl` 실측에서 24시간
구간에 `RECONCILE 봉 미반영 ... 시도 5` 로그가 589건 발생했다. 이 중
일부는 재시도 후 성공했으나, 일부는 재시도 소진으로 봉이 스킵됐다.

---

## 2. 대상 분기

### 2.1 현재 상태 (`engine/live_loop.py`)

```python
# 라인 1329~1331
if not retry_success:
    logger.error(f"❌ [RETRY] 모든 재조회 실패 ({len(retry_waits)}회) → 봉 스킵 | closed_ts=...")
    logger.error(f"💡 [FALLBACK] Upbit REST API 지연 ... → 다음 봉 대기")
    # 이후 notifier 전송 후 아무 처리 없이 다음 봉 대기
```

봉 시각 `closed_ts`에 대해 REST가 확정 응답을 못 준 상태에서 아무런 평가도
감사도 없이 흐름이 끝난다. 다음 봉이 도착하면 그 봉의 처리로 넘어간다.

### 2.2 옵션 C 최소 수정안

같은 자리에 잠정 종가로 미확정 Bar 를 만들어 `on_new_bar_confirmed`에
전달한다. 엔진은 이를 미확정 봉으로 인지해 매수는 지연 큐 등록,
매도는 즉시 집행으로 분기한다.

```python
if not retry_success:
    logger.warning(
        f"⚠️ [RETRY-EXHAUSTED-TENTATIVE] closed_ts={format_kst(closed_ts)} — "
        f"미확정 종가로 평가 진입 (WO-2 옵션 C)"
    )
    tentative_close = _lookup_tentative_close(local_series, closed_ts)
    if tentative_close is None:
        logger.error(
            f"❌ [TENTATIVE] 잠정 종가 확보 실패 → 기존 동작 유지 (봉 스킵)"
        )
        # 기존 notifier 전송 후 다음 봉 대기 (fallback)
    else:
        bar = Bar(
            ts=closed_ts,
            open=tentative_close,
            high=tentative_close,
            low=tentative_close,
            close=tentative_close,
            volume=0.0,
            is_closed=True,      # 봉 마감 시각 도래는 확인됨
            is_confirmed=False,  # 확정 종가는 미확보
            source="WO2_OPTION_C_TENTATIVE",
        )
        engine.on_new_bar_confirmed(bar, local_series, diff_summary)
        logger.info(
            f"✅ [WO2-OPTION-C] 미확정 봉 평가 진입 완료 | "
            f"ts={format_kst(closed_ts)} tentative_close={tentative_close}"
        )
```

---

## 3. 잠정 종가의 출처 (보완 3 반영: WS 신선도 조건)

우선순위 순서로 확보한다. 첫 번째로 값이 있는 지점을 사용한다.

1. **WebSocket 최신 ticker 가격**. `run_mode` 가 `UPBIT_MATCH`(현행 기본)일
   때 WS 는 `HINT_ONLY` 로 유지되며 최신 체결가가 별도 채널로 흐른다.
   **신선도 조건 (보완 3)**: 체결 시각이 대상 봉의 구간 안(`[closed_ts,
   closed_ts + 1min)`)이거나 봉 마감 후 10초 이내일 때만 채택한다. 그보다
   오래된 값이면 스킵하고 2순위로 넘어간다.
2. **마지막 성공 REST 응답의 이전 봉 close**. `local_series` 에 `closed_ts`
   직전 봉이 있으면 그 close 를 사용한다.
3. **fallback**: 실패 시 잠정 종가 확보 불가로 판정하고 기존 동작(봉 스킵)을
   유지한다. 알림도 기존 그대로.

`_lookup_tentative_close(local_series, closed_ts)` 를 `live_loop.py` 내부
helper 로 신설해 위 순서를 캡슐화한다. 채택된 출처(`WS_FRESH`,
`PREV_CLOSE`, `NONE`)와 체결 시각을 로그에 남긴다.

예:
```
[WO2-C-TENTATIVE-SOURCE] ts=2026-09-03 03:22:00 KST close=612.0
  source=WS_FRESH ws_trade_ts=2026-09-03T03:22:47+09:00 (age=13s within window)
```

---

## 4. 엔진에서 미확정 봉 처리 규칙

### 4.1 평가와 감사 기록

- 평가 자체는 실시간과 동일하게 진행한다.
- 감사(`_record_audit_log`)도 실시간과 동일하게 저장한다. 다만 checks JSON
  에 `via_tentative=True` 표시를 추가한다.
- 봉당 감사 판단 1회 원칙은 그대로 지킨다 (`_register_evaluated_bar` 호출).

### 4.2 매수 결정

- 이미 배선된 `_execute_buy_or_defer` 가 `bar.is_confirmed=False` 이면
  `PendingOrderQueue.register` 로 진입한다 (현행 코드 그대로 동작).
- `pending_created_at`, `tentative_close` 는 감사 `insert_buy_eval` 파라미터
  로 자연히 흐른다.

### 4.3 매도 결정 (근거 명시, 보완 2 필드 조사 포함)

- **매도는 잠정 종가로 즉시 집행한다. 지연 금지.**
- **근거**: 급락 손절(`stop_loss`) 조건이 잠정 종가로 이미 성립했다면
  확정 종가가 도착할 때까지 매도를 미루면 손실이 커진다. 잠정 종가는
  최선의 가용 정보이며 대체로 확정 종가와 오차 ±2원 수준이다 (24시간
  실측 5건 정합 결과 근거). 확정을 기다리는 것보다 잠정으로 즉시
  집행하는 것이 리스크가 낮다.
- 코드상 매도 경로는 이미 `_execute_sell` 이 지연 큐를 우회하므로
  추가 수정 불필요. `execute` 검사 순서 재정비(보정 1)로 확보됨.
- Trailing Stop 도 같은 원칙. 잠정 종가로 활성/발동 판정 즉시 집행.

**보완 2 매도 필터 봉 필드 참조 전수 조사**:

`core/filters/sell_filters.py` 의 모든 필터가 봉 정보를 `current_price` 인자
하나로만 받는다. 엔진 호출부에서 `current_price = bar.close` 로 항상 종가만
전달한다 (`core/strategy_incremental.py:376,1080`, `core/strategy_engine.py
:1296,1391`). `bar.high`, `bar.low`, `bar.open`, `bar.volume` 을 직접 읽는
매도 필터는 없다.

| 필터 | 참조하는 봉 필드 | 평평한 잠정 봉 영향 |
|---|---|---|
| `StopLoss` (라인 32~) | `current_price`=`bar.close` | 없음 (종가만 씀) |
| `TakeProfit` (라인 144~) | `current_price`=`bar.close` | 없음 |
| `TrailingStop` (라인 243~) | `current_price`=`bar.close`, `position.highest_price` (누적) | 없음 |
| `DeadCross` (라인 397~) | 지표만 사용 (봉 필드 직접 참조 없음) | 없음 |
| `StalePosition` (라인 469~) | 시간 기반, 봉 필드 미참조 | 없음 |

**결론**: 잠정 봉의 open/high/low/volume 을 잠정 종가와 동일 값으로 채워도
매도 필터 판정에 영향 없음. `_execute_buy` 의 고정가 매수 로직도 `bar.close`
를 참조한다. 잠정 봉 구성 방식(전 필드 동일 값, volume=0)이 안전.

### 4.4 봉당 1회 원칙과의 정합 (보완 1: 지표 교정 경로 증명)

미확정 평가 후 다음 봉 경계에서 확정 값이 도착했을 때 같은 봉을 **다시
판단하지 않는** 구조가 필요하다.

- 미확정 평가에서 `_register_evaluated_bar(bar.ts)` 호출로 이 봉을 이력에
  등록한다. 그 결과 확정 봉이 나중에 도착해 두 번째 `on_new_bar_confirmed`
  진입이 발생해도 봉당 1회 검사(`_evaluated_bar_ts`)로 차단된다.
- 대신 대기 매수 큐에 항목이 있으면 다음 봉의 `_resolve_pending_buy` 훅이
  유효성 확인만 실행한다 (판단 아님). 이 부분은 이미 배선되어 있다.

**보완 1 지표 교정 경로 코드 인용 (필수)**:

미확정 봉의 잠정 종가가 지표에 반영된 뒤(`core/strategy_engine.py:655`
`self.indicators.update_incremental(bar.close)` — `changed_count=0` 분기),
확정 종가는 다음 두 경로로 지표에 영구 교정된다.

**경로 1: 다음 봉의 REST-RECONCILE 변경 감지 (실측 대다수 사례)**

다음 봉이 확정되면 `engine/live_loop.py` 가 `reconcile_series` 를 호출한다.
이때 이전 봉(옵션 C 처리 봉)의 close 가 잠정과 다르면 `changed_ts` 에
포함된다. `on_new_bar_confirmed` 가 다음 봉 처리 컨텍스트에서 진입하고
`core/strategy_engine.py:635~650` 이 실행된다:

```python
elif changed_count > 0:
    # ✅ Reconcile 변경 발생 → 부분 재계산
    logger.warning(f"[ENGINE] Reconcile 변경 감지 → 부분 재계산 | ...")
    # 🔒 리스크 헷지: 전체 400개 재계산 금지
    # changed_ts 이후만 재계산
    self.indicators.recompute_from_changed_ts(full_series, changed_ts)
    # ✅ 재계산 후 현재 봉 반영 (CRITICAL!)
    self.indicators.update_incremental(bar.close)
```

이 경로에서는 다음 봉의 실시간 판단 흐름 안에서 이전 봉의 확정 종가가
지표에 반영된다. 판단은 다음 봉에 대해서만 이루어지고, 이전 봉의 지표
값은 확정으로 교정된다.

**경로 2: BACKFILL 재평가 (같은 봉에 대한 확정 재도달)**

REST-RECONCILE 이 옵션 C 처리 봉을 BACKFILL 대상으로 감지하면 (같은 봉의
close 값이 잠정 → 확정으로 바뀜) `on_new_bar_confirmed(bar, ...,
backfill_mode=True)` 로 진입한다. `core/strategy_engine.py:671~676` 봉당 1회
검사는 `backfill_mode=True` 를 우회하므로 진입은 통과. 이후 `changed_count>0`
분기(라인 645)에서 `recompute_from_changed_ts` 실행 → 확정 종가로 지표
교정. `_register_evaluated_bar` 는 BACKFILL 경로에서 호출되지 않으므로
(`strategy_engine.py:731` `if not backfill_mode`) 봉당 1회 이력이 오염되지
않는다. `last_bar_ts` 도 BACKFILL 경로에서 갱신되지 않는다 (`strategy_engine
.py:738` 같은 조건 안). 결함 조건 없음.

**결함으로 보고할 조건**: 없음. 기존 BACKFILL 경로가 미확정 봉에도 그대로
작동하며 봉당 1회 원칙과 `last_bar_ts` 갱신 정책과 충돌하지 않는다.

**잠재적 예외 (기존 §4.4 유지)**: 미확정 평가에서 매수 결정이 나와 큐에
등록됐는데, 다음 봉 확정 응답이 도착하기 전에 3번째 확정 재조회가 성공한
경우. `_resolve_pending_buy` 는 다음 봉 진입 시점에만 훅에서 호출되므로,
같은 봉의 재조회 성공은 이 훅이 잡지 못한다. 이 경우 다음 봉 진입까지
대기하고 그때 확정 종가로 유효성 확인. 지연 상한(60초) 안이면 발주,
초과면 취소. 정상 동작.

---

## 5. 회귀 테스트 목록 (기본 5건 + 보완 2건)

기존 파일 `tests/regressions/` 하위 신설. 파일명 규약 준수.

| 파일 | 검증 항목 | 통과 조건 |
|---|---|---|
| `test_r_2026_09_02_wo2_option_c_tentative_entry.py` | 재시도 소진 시 미확정 Bar 로 `on_new_bar_confirmed` 진입 | Mock live_loop 흐름, `_execute_buy_or_defer` 가 `PendingOrderQueue.register` 호출됨 |
| `test_r_2026_09_02_wo2_option_c_sell_immediate_on_tentative.py` | 미확정 봉의 매도 판단이 잠정 종가로 즉시 집행 | `_execute_sell` mock 호출 1회, 지연 큐 미사용 |
| `test_r_2026_09_02_wo2_option_c_no_double_evaluation.py` | 미확정 평가 후 같은 봉 재진입이 봉당 1회 검사에서 차단 | `_evaluated_bar_ts` 등록됨, 두 번째 진입 조기 반환 |
| `test_r_2026_09_02_wo2_option_c_tentative_close_source.py` | `_lookup_tentative_close` 우선순위 (WS 신선 → PREV_CLOSE → None) | 각 우선순위 값 반환 검증 |
| `test_r_2026_09_02_wo2_option_c_audit_via_tentative_flag.py` | 미확정 평가의 감사 `checks` JSON 에 `via_tentative=True` 포함 | audit_buy_eval.checks 필드에 플래그 확인 |
| **`test_r_2026_09_02_wo2_option_c_indicator_correction.py` (보완 1)** | 미확정 평가(잠정 800) 후 확정 종가(802) 도착 시 지표가 802 기준으로 교정 | `recompute_from_changed_ts` 호출, `indicators.ema_fast_buy` 가 802 반영 값과 일치 |
| **`test_r_2026_09_02_wo2_option_c_ws_freshness.py` (보완 3)** | WS 체결가의 신선도 조건 (구간 내 또는 봉 마감 후 10초 이내만 채택) | 신선한 WS 는 채택, 오래된 WS 는 스킵 후 PREV_CLOSE 사용 |

기존 회귀 게이트 `scripts/regression_gate.sh` 는 디렉토리 기반 수집이므로
추가 등록 불필요. `.githooks/pre-push` 가 push 시점 물리 차단.

---

## 6. dry-run 검증 방법

로컬 회선 특성을 활용한다. 이번 세션 dry-run 30봉 관측에서 실제로 재시도
소진 시나리오는 발생하지 않았으나, 이는 KRW-JTO 저유동성 시간대의 관측
구간이 짧았기 때문이다. 옵션 C 배포 후 dry-run 관측 계획:

- 대상: `scripts/live_dry_run.py --ticker KRW-JTO --strategy EMA --user-id mcmax33_dry`
- 관측 시간: 활성 시간대 60봉 이상 (60분). 저유동성 시간대에 관측 시간
  절반 이상 잡히는 KRW-JTO 특성 상 재시도 발생 확률이 높다.
- 통과 조건:
  - `[WO2-OPTION-C] 미확정 봉 평가 진입 완료` 로그 최소 1건.
  - 그 봉의 `audit_buy_eval` 행에 `via_tentative=True` 확인.
  - `[PENDING-REGISTER]` 발생 시 `pending_created_at` 과 `tentative_close`
    감사 컬럼 값 확인.
  - 다음 봉 경계에서 `[PENDING-RESOLVE]` 로그와 유효성 확인 결과 확인.
- 예외 절차: 60봉 관측에서 재시도 소진 사례가 발생하지 않으면 저유동성
  시간대(심야)로 연장. 그래도 확보가 어려우면 보고 후 판단 요청. 모의
  조작 금지.

---

## 7. 롤백 조건 (보완 4: 숫자 확정)

WO-6·WO-2 배포와 동일한 5종 트리거를 유지하고 옵션 C 관측 항목을 다음과
같이 확정한다.

### 7.1 즉시 롤백

다음 중 하나라도 24시간 관측 구간에서 발생하면 즉시 롤백.

- **트리거 A**: 미확정 봉 진입 후 `Traceback` 또는 `CRITICAL` **1건**.
- **트리거 B**: 잠정 종가로 즉시 집행된 매도 중, 확정 종가 기준 조건
  불성립이었던 비율이 **20% 초과**이고 **동시에** 해당 사례가 **3건 이상**.
  (두 조건 AND. 매도 총수가 적어서 비율만 튀는 경우를 배제.)

### 7.2 관찰 신호 (롤백 아님)

수치만 집계해 보고. 롤백 트리거 아님.

- **관찰 A**: 잠정 종가와 확정 종가의 편차 5원 초과 봉의 비율.
- **관찰 B**: 유효성 확인 취소율 (`validation_passed=0` / `pending_created_at
  NOT NULL` 총수).

관찰 신호가 지속적으로 상승하면 파라미터 조정 검토 대상. 즉시 롤백 대상
아님. "심각 임계" 같은 미정의 표현은 이 계획서에서 제거되었다.

---

## 8. 구현 순서 (승인 후)

1. 이 계획서 사용자 검토·승인.
2. `engine/live_loop.py:1329` 대상 분기 수정 + `_lookup_tentative_close`
   helper 신설.
3. `core/strategy_engine.py` `_record_audit_log` 에 `via_tentative` 플래그
   반영 (선택). 감사 checks JSON 확장.
4. 회귀 테스트 5건 신설.
5. `scripts/regression_gate.sh` 로컬 통과.
6. `pages/dashboard.py` 버전 갱신 + 커밋.
7. 배포 승인 요청 → 서버 배포 → 60봉 dry-run → 24시간 실측.

**주의**: 이번 배포(2026-09-02 `v1.2026.09.02.1424`)와 섞지 않는다.
별도 배포로 진행한다.

---

## 9. 승인 이력

- 2026-09-02: 골격 승인. 감사 플래그는 `checks` JSON 방식으로 확정.
  보완 4건(지표 교정 경로 증명, 매도 필터 필드 전수, WS 신선도 10초,
  롤백 숫자 확정) 반영 후 구현 착수.

## 10. 후속 순서

1. 구현·회귀 테스트(5+2건)·회귀 게이트 통과 (현재 진행 중).
2. 현행 WO-2 배포의 24시간 실측(2026-09-03 14:26:32 KST 집계) 합격 확인.
3. 실측 합격 후 옵션 C 배포 승인 요청.
4. 배포 후 §6 검증(60봉, 미발생 시 심야 연장, 모의 조작 금지).
