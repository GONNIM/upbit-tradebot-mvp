# KRW-SUI Golden Cross 매수 실패 — 해결방안 보고서

| 항목 | 값 |
|---|---|
| 작성일 | 2026-05-26 |
| 작성자 | Claude Opus 4.7 (1M context) — 책임자 보고 |
| 사태 보고서 | `2026-05-26-KRW-SUI-Golden-Cross-매수실패-사태보고서.md` (선행 문서) |
| 적용 대상 커밋 | `a192d31` (현재 main) → 신규 핫픽스 커밋 |
| 상태 | **계획 — 사용자 승인 후 진행** |

---

## 1. 결함 매트릭스 (정확 재정리)

| # | 결함 | 위치 | 우선순위 | 영향 |
|---|---|---|---|---|
| **B11** | LIVE BUY가 Upbit API `None` 응답 시 **재시도 없이 1회 시도 후 포기** | `core/trader.py:243-271` (`buy_market`) | **P0** | 일시적 API 장애 = 영구 BUY 누락. 본 사고의 직접 원인 |
| **B12** | BUY 시도 실패가 `audit_trades`/`orders`에 **기록되지 않음** | `core/trader.py` LIVE BUY 실패 분기 | **P0** | 사용자가 봇의 시도 자체를 추적 불가. "감지 안 됨"으로 오인 |
| **B14** | Upbit `None` 응답의 **근본 원인 식별 불가** — HTTP 상태/본문 미로깅 | `core/trader.py` LIVE BUY 호출부 | **P0** | 동일 사고 재발 시 진단 불가 |
| **B7-회귀** | `_maybe_reload_params` 호출 시 `json_path` 미정의로 매 봉마다 `NameError` | `engine/live_loop.py:684-694` (직전 핫픽스 a192d31에서 도입) | **P0** | `set_config` 변경 무중단 반영 기능 완전 무력화 |
| **B13** | `audit_viewer` UI가 `BUY_SIGNAL` 봉(bar 394)을 사용자 화면에 표시하지 못함 (DB엔 정상 존재) | `pages/audit_viewer.py` | **P1** | 봇 정상 감지를 사용자가 의심하게 만드는 신뢰 훼손 |
| **B15** | LIVE 매수 직전 활성 KRW 잔고 사전 재확인 부재 → 잔고 변동 시 API None 유발 | `core/trader.py:180-194` (`buy_market` 진입부) | **P1** | 사용자 동시 거래 환경에서 BUY 실패 확률 증가 |
| **B16** | BACKFILL이 BUY_SIGNAL을 발견해도 실제 BUY를 실행하지 않고 다음 봉으로 미룸 | `core/strategy_engine.py` BACKFILL 분기 | **P2** | 1봉 지연. 빠른 시장에서 진입가 격차 |

---

## 2. 수정 방안 (단계별)

### **P0-B11 — LIVE BUY 재시도 + 지수 백오프**

**파일**: `core/trader.py:243-271` (`buy_market` LIVE 분기)

**변경 전**:
```python
try:
    res = self.upbit.buy_market_order(ticker, krw_to_use)
    logger.info(f"[BUY-LIVE] raw response: {res}")
    if not res or not isinstance(res, dict):
        logger.error(f"[BUY-LIVE] invalid response from Upbit (res={res})")
        insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매수 응답 비정상: {res}")
        return {}
    ...
```

**변경 후**:
```python
import time as _time

MAX_BUY_RETRIES = 3
BACKOFF_SECONDS = [1.0, 2.0, 4.0]   # 지수 백오프

last_err = None
res = None
for attempt in range(1, MAX_BUY_RETRIES + 1):
    try:
        # ✅ B15: 매 시도 직전 활성 KRW 재확인 (사용자 동시 거래 대응)
        current_krw = self._krw_balance()
        if current_krw < krw_to_use:
            # 잔고 변동 감지 — krw_to_use를 활성 잔고로 축소 (최소 주문금액 보호)
            adjusted = math.floor(current_krw * self.risk_pct)
            if adjusted < 5000:
                last_err = f"잔고 부족: 활성 KRW={current_krw} (요청={krw_to_use})"
                logger.warning(f"[BUY-LIVE] attempt #{attempt}/{MAX_BUY_RETRIES} skip → {last_err}")
                break
            logger.warning(
                f"[BUY-LIVE] attempt #{attempt}/{MAX_BUY_RETRIES} 잔고 변동 감지 — "
                f"krw_to_use {krw_to_use} → {adjusted}"
            )
            krw_to_use = adjusted

        res = self.upbit.buy_market_order(ticker, krw_to_use)
        logger.info(f"[BUY-LIVE] attempt #{attempt}/{MAX_BUY_RETRIES} raw response: {res}")

        if res and isinstance(res, dict) and "uuid" in res and "error" not in res:
            # 성공
            break

        # 실패 케이스 분류
        if isinstance(res, dict) and "error" in res:
            err_msg = res["error"].get("message") if isinstance(res["error"], dict) else str(res["error"])
            last_err = f"Upbit error: {err_msg}"
            # 명시적 잔고 부족 등은 재시도 무의미 → 즉시 중단
            if "insufficient" in str(err_msg).lower() or "잔액" in str(err_msg):
                logger.error(f"[BUY-LIVE] non-retriable error: {err_msg}")
                break
        else:
            last_err = f"invalid response (res={res})"

        logger.warning(
            f"[BUY-LIVE] attempt #{attempt}/{MAX_BUY_RETRIES} failed → {last_err}"
        )
    except Exception as e:
        last_err = f"exception: {e}"
        logger.warning(f"[BUY-LIVE] attempt #{attempt}/{MAX_BUY_RETRIES} exception: {e}")

    # 마지막 시도가 아니면 백오프
    if attempt < MAX_BUY_RETRIES:
        _time.sleep(BACKOFF_SECONDS[attempt - 1])

# ✅ B12: 최종 실패 시 audit/orders/log에 명시 기록
if not res or not isinstance(res, dict) or "uuid" not in res:
    logger.error(f"[BUY-LIVE] all {MAX_BUY_RETRIES} attempts failed | last_err={last_err}")
    insert_log(self.user_id, "ERROR",
               f"❌ Upbit 시장가 매수 {MAX_BUY_RETRIES}회 재시도 모두 실패: {last_err}")
    # B12: 실패도 audit 기록
    self._audit_trade(
        side="BUY",
        ticker=ticker,
        price=price,
        qty=None,
        status_note=f"market buy(FAILED: {last_err})",
        ts=ts,
        meta={**(meta or {}), "reason": "BUY_FAILED_API", "last_err": last_err},
        balances_before=(self._krw_balance(), self._coin_balance(ticker)),
        balances_after=(None, None),
        fee_ratio=MIN_FEE_RATIO,
        risk_pct=self.risk_pct,
    )
    # B12: orders 테이블에도 REQUESTED 상태로 기록 (사후 추적용)
    try:
        insert_order(
            self.user_id, ticker, "BUY",
            price, 0.0, "FAILED",
            current_krw=int(self._krw_balance()), current_coin=self._coin_balance(ticker),
            profit_krw=0, entry_bar=(meta or {}).get("bar"),
        )
    except Exception as e:
        logger.warning(f"[BUY-LIVE] insert_order(FAILED) 실패: {e}")
    return {}
```

**왜 이렇게**:
- 3회 재시도 + 1s/2s/4s 백오프 — Upbit 일시 응답 거부 자연 회복 윈도우 커버
- 잔고 부족 같은 비재시도 에러는 즉시 중단 (불필요한 호출 방지)
- 매 시도 직전 활성 KRW 재확인 (B15) — 사용자 동시 거래 대응
- 최종 실패도 `audit_trades`/`orders`/`logs` 모두 기록 — 사용자 추적 가능

---

### **P0-B14 — Upbit 응답 상세 로깅**

**파일**: `core/trader.py` LIVE BUY 호출부 (위 B11 패치 내부에 통합)

**추가 로깅**:
- `pyupbit.http` 로거를 INFO 이상으로 설정 (필요 시 일정 기간 DEBUG)
- pyupbit이 `requests.Response` 객체를 노출하지 않으므로 응답이 `None`/dict/list일 때 `type`/`repr` 모두 로깅
- 실패 직후 `self.upbit.get_balance("KRW")` 호출하여 잔고 상태 캡처 → 잔고 부족 케이스 식별

**환경 설정** (`engine/live_loop.py` 또는 부팅 시점):
```python
import logging
logging.getLogger("pyupbit.http").setLevel(logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
```

---

### **P0-B7-회귀 — `json_path` NameError 수정**

**파일**: `engine/live_loop.py`

**원인**: `_maybe_reload_params(json_path=json_path, ...)` 호출 시 `json_path` 변수가 해당 스코프에 정의되지 않음. `live_loop.py` 함수 인자로는 `params: LiveParams`만 받음.

**수정 방향 두 옵션** (택일):

**옵션 A (권장)**: params 파일 경로를 규칙 기반으로 재구성
```python
def _resolve_params_json_path(user_id: str, strategy_type: str) -> str:
    """mcmax33_latest_params_EMA.json 같은 규칙으로 경로 구성"""
    from config import PARAMS_JSON_FILENAME
    strategy_tag = _strategy_tag(strategy_type)
    return f"{user_id}_latest_{PARAMS_JSON_FILENAME.replace('.json', '')}_{strategy_tag}.json"
    # 또는 실제 dashboard.py의 경로 규칙과 동일하게 맞춰서 정의
```

호출 측:
```python
json_path = _resolve_params_json_path(user_id, params.strategy_type)
_params_mtime = _maybe_reload_params(
    user_id=user_id,
    params_ref=params,
    strategy=strategy,
    json_path=json_path,
    cond_path=_cond_path,
    mtime_state=_params_mtime,
)
```

**옵션 B (간소)**: `json_path` 인자 자체 제거, conditions만 추적
```python
_params_mtime = _maybe_reload_params(
    user_id=user_id,
    params_ref=params,
    strategy=strategy,
    cond_path=_cond_path,
    mtime_state=_params_mtime,
)
```
`_maybe_reload_params`에서 `json_path` 관련 분기 전체 제거. `params.json` 변경은 사용자 알람(`insert_log`) 없이 무시 — 변경 시 엔진 재시작이 필요한 항목이므로 무중단 reload 대상 외.

**권장**: 옵션 B (간소, 안전). params.json 변경은 지표 구조에 영향 → 엔진 재시작이 안전한 정책.

---

### **P1-B13 — `audit_viewer` UI 표시 결함**

**파일**: `pages/audit_viewer.py`

**확인 후 수정 항목**:
1. `audit_buy_eval` 조회 시 정렬 키 (`bar_time` vs `bar` vs `timestamp`) 정확성
2. 페이지네이션/LIMIT가 특정 봉을 누락시키는지
3. `overall_ok=1` 행(BUY_SIGNAL)을 강조 표시 (🟢 아이콘, 행 하이라이트)

이 작업은 본 핫픽스 범위 밖. 별도 PR로 진행 권고.

---

### **P2-B16 — BACKFILL 시 BUY 직접 실행 여부 정책 결정**

**현재**: BACKFILL은 audit 평가만 하고 실제 매수는 다음 봉의 현재 봉 처리에서 발생 → 1봉 지연.

**옵션 1**: BACKFILL 시점에 BUY_SIGNAL이면 즉시 실행 (지연 제거).
- 장점: 즉각 반응
- 단점: BACKFILL 다중 봉인 경우 의도하지 않은 다중 BUY 발생 가능. 정합성 위험.

**옵션 2 (권장)**: 현재 정책 유지. 단, BACKFILL이 발견한 BUY_SIGNAL을 명시적으로 로그 + audit 기록 강화.

본 핫픽스 범위 외. 별도 정책 검토 후 결정.

---

## 3. 영향 범위 분석

| 변경 | 영향 받는 경로 | 검증 포인트 |
|---|---|---|
| `trader.buy_market` 재시도 루프 | LIVE BUY 전체 | 정상 매수 흐름 보존(첫 시도 성공 시 즉시 break), 실패 시 3회 재시도 |
| 잔고 사전 재확인 (B15) | LIVE BUY 직전 | 활성 KRW 변동 시 `krw_to_use` 자동 축소 (최소 주문금액 5000원 미만이면 중단) |
| 실패 시 audit/orders 기록 (B12) | DB 두 테이블 | 실패 행 INSERT 정상 작동, `reason='BUY_FAILED_API'` 검색 가능 |
| `pyupbit.http` 로그 레벨 INFO | 로그 양 증가 | journalctl 디스크 사용량 모니터링 |
| `_maybe_reload_params` `json_path` 제거 | mtime 감지 부분 | `conditions` 파일 mtime은 유지, `params.json` 변경 시 알람 없음 (정책상 엔진 재시작 필요) |

거래 로직 안전성:
- 정상 매수(API 정상 응답): 첫 시도 성공 → 동일 동작 (회귀 없음)
- API 비정상 응답(None/error): 3회 재시도 후 명시 실패 + 기록
- 잔고 부족: 즉시 중단(불필요 호출 방지)
- TEST 모드: 변경 없음 (LIVE 분기만 수정)

---

## 4. 검증 계획

### 로컬 검증
- 변경 파일 `python3 -m py_compile` 통과
- `dashboard.py` 버전 갱신 (`v1.2026.05.26.HHMM`)

### 서버 배포 후 검증
1. **B7-회귀**: 봉 처리 직후 `[PARAMS-RELOAD] mtime check failed: name 'json_path' is not defined` 로그 사라짐 확인
2. **B11**: 의도적으로 `pyupbit.Upbit`을 mock하여 None 응답 시뮬레이션 (별도 테스트 스크립트) — 운영 환경에서는 다음 BUY 발동 시 정상 동작 모니터링
3. **B12**: BUY 실패 시 `audit_trades`에 `status_note='market buy(FAILED: ...)'` 행 + `orders`에 `status='FAILED'` 행 출현 확인
4. **B14**: 다음 LIVE BUY 시도 시 `[BUY-LIVE] attempt #1/3 raw response: ...` 로그가 `type`/`repr` 포함하여 출력되는지 확인

### 회귀 검증
- 정상 봇 매수 사이클(`EMA_GC` BUY) 첫 시도 성공 → 동일 동작 보존
- TEST 모드 시뮬레이션 영향 없음

---

## 5. 롤백 계획

- 모든 변경은 단일 git commit 단위. 문제 발생 시 직전 안정 커밋(`a192d31` 또는 그 이전)으로 `git revert`.
- DB 스키마 변경 없음 → DB 롤백 불필요.
- 가장 위험한 변경: B11 재시도 루프. 만약 재시도가 추가 부작용 발생 시 `MAX_BUY_RETRIES=1`로 즉시 축소 가능.

---

## 6. 우선순위 + 진행 옵션

### P0 (즉시, 본 클레임 직접 해결)
- **B11** LIVE BUY 재시도 + 백오프
- **B12** 실패 시 audit/orders/log 기록
- **B14** 응답 상세 로깅
- **B7-회귀** `json_path` NameError 해결

### P1 (별도 PR)
- **B13** `audit_viewer` UI 수정
- **B15** 잔고 사전 재확인 (B11과 함께 적용)

### P2 (정책 검토)
- **B16** BACKFILL BUY 즉시 실행 여부

---

## 7. 진행 옵션 (승인 요청)

- **(가)** P0 전체(B11/B12/B14/B7-회귀)를 단일 핫픽스 커밋으로 즉시 적용
- **(나)** P0 + P1(B13/B15)를 함께 적용
- **(다)** B7-회귀만 우선 핫픽스(긴급도 최고, 변경 최소) 후 나머지 별도 진행

**권고**: **(가)**. B7-회귀는 매 봉마다 NameError가 발생하므로 즉시 해결이 필요하고, B11+B12+B14는 사용자 클레임의 직접 해결 + 재발 방지에 필수적입니다. B11과 B12는 같은 함수(`trader.buy_market`)에 있어 단일 커밋으로 묶는 것이 깔끔합니다.

---

## 8. 작업 체크리스트 (승인 후)

- [ ] `core/trader.py:243-271` LIVE BUY 재시도/백오프/잔고 재확인 추가 (B11+B15)
- [ ] `core/trader.py` 최종 실패 시 `_audit_trade` + `insert_order(status='FAILED')` 호출 (B12)
- [ ] `core/trader.py` LIVE BUY 응답 type/repr 상세 로깅 (B14)
- [ ] `engine/live_loop.py:684-694` `_maybe_reload_params` 호출에서 `json_path` 제거 또는 `_resolve_params_json_path` 신설 (B7-회귀)
- [ ] `engine/live_loop.py` `_maybe_reload_params` 시그니처 정합화
- [ ] `pages/dashboard.py` 버전 갱신
- [ ] `python3 -m py_compile` 전 변경 파일
- [ ] git commit + push
- [ ] `deploy-tradebot`
- [ ] 사후 검증 (NameError 로그 사라짐, 향후 BUY 실패 시 audit 기록 확인)

---

## 9. 결론 한 줄

**(가) 옵션 — P0 4종(B11/B12/B14/B7-회귀) 단일 핫픽스 커밋 — 으로 즉시 적용 권고. B7-회귀는 매 봉마다 발생 중이므로 긴급. 사용자 승인 후 즉시 진행.**
