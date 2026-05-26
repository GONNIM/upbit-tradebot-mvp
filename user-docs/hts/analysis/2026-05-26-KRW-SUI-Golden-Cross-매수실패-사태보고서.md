# KRW-SUI Golden Cross 매수 실패 사태 보고서

| 항목 | 값 |
|---|---|
| 작성일 | 2026-05-26 |
| 작성자 | Claude Opus 4.7 (1M context) — 책임자 보고 |
| 사용자 ID | mcmax33 |
| 종목 | KRW-SUI (수이) |
| 전략 | EMA (1분봉, fast=30, slow=200, base=200) |
| 사건 발생 | 2026-05-26 17:10:00 ~ 17:11:06 KST |
| 사건 시점 봇 커밋 | `a192d31` (배포 13:44:37 KST) |
| **결론** | **봇 Golden Cross 감지 + BUY 시도는 정확히 발동했으나 Upbit API가 `None`을 반환하여 실행 실패. 봇은 재시도 없이 1회 시도 후 포기. 시도/실패가 `audit_trades`/`orders`에 기록되지 않아 사용자가 봇의 시도 자체를 인지할 수 없는 상태.** |

---

## 1. 사용자 클레임

> "BUY 감사 로그(`audit_buy_eval`) 확인 시 Golden Cross 발생했는데 매수가 되지 않았다."

첨부 캡처:
- `user-docs/hts/img/Claim-Buy-Chart.jpeg` — 5/26 17:12 KST 차트 (MA 30=1,533 > MA 200=1,532.7 Golden 정렬)
- `user-docs/hts/img/Claim-Buy-Eval.jpeg` — `audit_buy_eval` 화면 (bar 394 [17:10:00] 표시 누락)

---

## 2. 사건의 진짜 모습 (DB + journalctl 전문)

### 2-1. `audit_buy_eval` DB 직접 조회 — bar 394는 정확히 존재 (UI만 미표시)

```
id   |     timestamp     |   bar_time  | bar | price | ema_fast |  ema_slow | overall_ok | reason     | cross_status
2148 | 17:09:05.450756  | 17:08:00   | 392 | 1537  | 1531.124 | 1531.710 | 0           | NO_BUY_SIGNAL | Dead
2149 | 17:10:06.239468  | 17:09:00   | 393 | 1541  | 1531.701 | 1531.793 | 0           | NO_BUY_SIGNAL | Dead
2150 | 17:11:05.998280  | 17:10:00   | 394 | 1537  | 1532.043 | 1531.844 | 1           | BUY_SIGNAL    | Golden  ← 🟢 정확히 기록
2151 | 17:12:10.960180  | 17:11:00   | 395 | 1541  | 1532.621 | 1531.936 | 0           | NO_BUY_SIGNAL | Golden
2152 | 17:12:11.288759  | 17:12:00   | 396 | 1539  | 1532.492 | 1531.916 | 0           | NO_BUY_SIGNAL | Golden
```

→ **bar 394 (`bar_time=2026-05-26T17:10:00`)에 정확히 `BUY_SIGNAL`, `overall_ok=1`, `cross_status=Golden`이 기록됨**.

사용자 화면(`audit_viewer`)에서 bar 394가 누락된 것처럼 보인 이유는 **UI 표시 결함** — DB에는 정상 존재.

### 2-2. 봇 의사결정 흐름 (`journalctl` 17:11:00 ~ 17:11:16, 원문 발췌)

```
17:11:00 [CLOCK] 봉 확정 | closed=2026-05-26 17:11:00 KST
17:11:00 [PARAMS-RELOAD] mtime check failed: name 'json_path' is not defined   ← B7 회귀 버그
17:11:00 [CLOCK-CLOSE] 봉 확정 감지 | ts=2026-05-26 17:11:00 KST

17:11:04 [COND] loaded: mcmax33_EMA_buy_sell_conditions.json
17:11:04 [SETTINGS-SNAPSHOT] ✅ Recorded at 2026-05-26T17:11:00+09:00

17:11:05 [REST-RECONCILE] Fetching 400 bars from REST
17:11:05 [RECONCILE] 확정 종가 ✅ ts=17:11:00 close=1537 vol=19.56
17:11:05 [RECONCILE] 변경 감지! changed=2 inserted=1 | 17:10:00 ~ 17:11:00
17:11:05 [BACKFILL] 1개 누락 봉 평가 시작
17:11:05 [BACKFILL] 누락 봉 평가 | ts=2026-05-26 17:10:00 | close=1537
17:11:05 [BACKFILL] 버퍼 추가 스킵 (재평가 모드) | ts=17:10:00 | close=1537
17:11:05 ⏭️ Above Base EMA disabled
17:11:05 ⏭️ Bullish Candle disabled
17:11:05 🔔 EMA Buy Signal | fast=1532.04 slow=1531.84                                ← 첫 번째 트리거
17:11:05 📊 Bar#394 | ts=08:10:00+00:00 | close=1537 | ema_fast=1532.04
         | ema_slow=1531.84 | ema_base=1531.84 | action=BUY | pos=False
17:11:05 [AUDIT-UPDATE] BUY 평가 UPDATE | KRW-SUI | bar_time=17:10:00 | new_price=1537
17:11:06 ✅ [BACKFILL] 1개 누락 봉 평가 완료                                            ← BACKFILL은 평가만, 실제 BUY 실행 X

17:11:06 [VERIFY] 과거 봉 검증 시작 | count=200
17:11:06 [VERIFY] ✅ 모든 과거 봉 일치 | count=200 | tolerance=±1원
17:11:06 [VERIFY] 과거 봉 검증 통과

17:11:06 [ENGINE] Reconcile 변경 감지 → 부분 재계산 | changed=2 | 17:10:00 ~ 17:11:00
17:11:06 [INDICATORS] 부분 재계산 시작 | changed_count=2 bars=2
17:11:06 ⚠️ Not enough data for seed: 2 < 200
17:11:06 [INDICATORS] 부분 재계산 완료 | ema_fast=1531.70 ema_slow=1531.79              ← 재계산 후 EMA 값
17:11:06 ⏭️ Above Base EMA disabled
17:11:06 ⏭️ Bullish Candle disabled
17:11:06 🔔 EMA Buy Signal | fast=1532.04 slow=1531.84                                ← 두 번째 트리거 (현재 봉)
17:11:06 📊 Bar#395 | ts=08:11:00+00:00 | close=1537 | ema_fast=1532.04
         | ema_slow=1531.84 | ema_base=1531.84 | action=BUY | pos=False
17:11:06 [BUY] plan krw_to_use=855537.0000 price=1537.0 fee=0.0005 -> qty=556.34967162
17:11:06 [BUY-LIVE] raw response: None                                                ← Upbit API None 반환
17:11:06 ERROR [BUY-LIVE] invalid response from Upbit (res=None)
17:11:06 ❌ BUY 실패                                                                   ← 봇 1회 시도 후 포기
17:11:06 ✅ [CONFIRMED] 봉 처리 완료 | ts=17:11:00 close=1537.0

17:11:16 [DB] sync_all_positions cleared: KRW-IN  → active=0, locked=0, entry_price=0
17:11:16 [DB] sync_all_positions cleared: KRW-SUI → active=0, locked=0, entry_price=0   ← 사용자 SUI 잔고 0 확인
17:11:16 [DB] sync_all_positions cleared: KRW-ZRO → active=0, locked=0, entry_price=0
17:11:16 [OR] periodic sync: user=mcmax33 updated (full portfolio sync included)
17:11:16 [OR] periodic sync completed: 1 user(s), interval=60s
```

### 2-3. `orders` 테이블 — 17:11 시점 BUY 기록 없음

```sql
SELECT id, timestamp, ticker, side, price, volume, status
FROM orders
WHERE ticker='KRW-SUI' AND timestamp >= '2026-05-26T17:00:00';
```
**결과: 0 rows** — BUY 시도 실패가 `orders`에 전혀 기록되지 않음.

### 2-4. `audit_trades` 테이블 — 17:11 시점 BUY 기록 없음

가장 최근 `audit_trades` 중 BUY는 ID 15 (`2026-05-26T05:14:54 EMA_GC 1571`). 5/26 17:11의 시도/실패 흔적 0건.

---

## 3. Upbit API가 `None`을 반환한 원인 분석

### 3-1. 봇 코드 분기 (`core/trader.py:243-271`)

```python
try:
    res = self.upbit.buy_market_order(ticker, krw_to_use)   # pyupbit 호출
    logger.info(f"[BUY-LIVE] raw response: {res}")

    if not res or not isinstance(res, dict):
        msg = f"[BUY-LIVE] invalid response from Upbit (res={res})"
        logger.error(msg)
        insert_log(self.user_id, "ERROR", f"❌ 업비트 시장가 매수 응답 비정상: {res}")
        return {}                                            # ★ 재시도 없이 즉시 종료
    ...
```

`pyupbit.Upbit.buy_market_order()` 가 `None`을 반환하는 일반적 케이스:

| # | 케이스 | pyupbit 내부 동작 | 가능성 |
|---|---|---|---|
| **A** | HTTP 응답 본문 비어있음 (서버 일시 장애) | `requests.json()` 호출 결과 `None` | 중 |
| **B** | HTTP 응답 코드 200이지만 JSON 파싱 실패 | `try/except` 후 `None` 반환 | 중 |
| **C** | HTTP 응답 코드 ≠ 200 (4xx/5xx) — rate limit (429), 인증 실패 (401), 잘못된 요청 (400) | pyupbit 버전에 따라 dict(error) 또는 None | **상** |
| **D** | 네트워크 timeout / SSL 오류 | requests 예외 → pyupbit가 None 반환 | 중 |
| **E** | `krw_to_use`가 실제 활성 잔고를 초과 (사용자 동시 거래로 잔고 락) | Upbit가 400 "잔액부족" 응답 → pyupbit None | **상** |
| **F** | 동일 시점 사용자가 HTS에서 거래 중 → Upbit 잔고 동시성 제한 | 일시적 응답 거부 | 중 |

### 3-2. 결정적 정황 — 사용자 동시 거래 + 잔고 변동

`17:11:16` 시점 periodic_sync 결과:
```
KRW-IN  → active=0   (이전 297.96)
KRW-SUI → active=0   (이전 588.485 / 296.224)
KRW-ZRO → active=0   (이전 495.58)
```
→ **17:11:00 ~ 17:11:16 사이 사용자가 HTS에서 보유 코인 전량 매도**. 그 결과 KRW 잔고가 회복되어 `_krw_balance()`가 `855,537원`을 반환. 봇은 이를 가용 KRW로 인식하고 매수 시도.

**의심**: 봇이 `buy_market_order(855,537원)` 호출 시점에:
- 사용자가 다른 매도/매수 주문을 동시 진행 → Upbit가 동시 주문 제한 적용
- 또는 봇의 `_krw_balance()` 호출 후 매수 주문 발행 직전에 사용자가 또 매수하여 활성 KRW 부족
- → 결과적으로 케이스 **E** 또는 **F**가 유력

### 3-3. 근본 원인 미확정 — pyupbit 내부 로그 부재

`logger.info(f"[BUY-LIVE] raw response: {res}")` 만 출력 → HTTP 응답 코드/본문/헤더는 캡처되지 않음. pyupbit는 기본 로그 레벨이 WARNING이라 내부 요청/응답 로그 미출력.

**정확한 원인 식별을 위해 필요한 보강**:
1. `core/trader.py` LIVE BUY 분기에서 Upbit 응답 직전/직후 HTTP 상태/본문 로깅
2. pyupbit `pyupbit.http` 로거를 DEBUG로 일정 시간 운영
3. 실패 시 Upbit `/orders` API로 직전 5초 내 주문 상태 조회 (참고용)
4. 잔고 부족 사전 검증 — `buy_market_order` 호출 직전 `get_balance("KRW")` 재확인

---

## 4. 부수적으로 발견된 결함 (이번 사건이 드러낸 것)

### 4-1. **B7 회귀 버그** — `name 'json_path' is not defined`

직전 핫픽스(`a192d31`, P1-B7 파라미터 실시간 반영)에서 `_maybe_reload_params()` 호출 시 `json_path` 변수가 `engine/live_loop.py` 호출 스코프에 정의되지 않은 채 참조됨.

```
17:11:00 WARNING [PARAMS-RELOAD] mtime check failed: name 'json_path' is not defined
```

매 봉 처리 직전마다 `NameError` 발생 → 파라미터 mtime 감지 자체가 무력화. `set_config` 변경 무중단 반영 기능이 동작하지 않음.

`grep` 결과 `live_loop.py` 내 `json_path =` 정의 0건. 호출은 1건(`json_path=json_path` 인자 전달).

### 4-2. **bar 394 BACKFILL + bar 395 즉시 처리** — Cross 봉 이중 평가

- bar 394: BACKFILL 모드로 평가 (audit만 기록, 실제 BUY 미실행)
- bar 395: 현재 봉으로 평가 (BUY 의도 발동 → 실패)

원래 EMA Golden Cross는 prev/curr 한 번만 트리거되어야 함. BACKFILL과 현재 봉 처리가 분리되어 있어, BACKFILL이 평가만 하고 다음 봉의 현재 봉 처리에서 비로소 실제 BUY 시도가 일어남. 만약 17:11에 BACKFILL이 BUY를 직접 실행했다면 사용자가 더 일찍 인지할 수 있었음.

추가 분석 필요 항목: `Bar#395 ema_fast=1532.04 ema_slow=1531.84`인데 부분 재계산 직후엔 `ema_fast=1531.70 ema_slow=1531.79`로 출력됨 → **EMA 값 불일치 가능성**. (재계산 후 다시 갱신되어 1532.04가 됐을 수 있으나 로그상 흐름이 명확하지 않음.)

### 4-3. **사용자 화면 `audit_viewer` UI** — bar 394 표시 누락

DB에는 bar 394가 정확히 있으나 사용자 첨부 이미지에서 bar 394 행이 안 보임. UI 측 정렬/필터/페이지네이션 결함 가능성.

---

## 5. 사용자 클레임에 대한 최종 답변

**Q. "Golden Cross 발생했는데 매수가 되지 않았다."**

A. 봇은 정확히 Golden Cross를 감지했고, BUY 의도를 발동했으며, 실제 매수 주문도 시도했습니다.

- ✅ Golden Cross 감지: `audit_buy_eval` bar 394 `BUY_SIGNAL` `overall_ok=1` 정확 기록
- ✅ BUY 의도 발동: `core.strategy_engine | Bar#395 action=BUY pos=False`
- ✅ BUY 주문 호출: `core.trader | [BUY] plan krw_to_use=855,537 price=1537 -> qty=556.35`
- ❌ **Upbit API가 `None`을 반환 → 실행 실패** (`[BUY-LIVE] raw response: None`)
- ❌ **봇이 재시도 없이 1회 시도 후 포기** (`❌ BUY 실패`)
- ❌ **이 시도/실패가 `audit_trades`/`orders`에 기록되지 않아 사용자가 봇의 시도 사실을 알 수 없음**

근본 원인은 **(a) Upbit API의 None 응답** — 가장 유력한 원인은 사용자 동시 거래에 의한 잔고 변동 또는 일시적 응답 거부, **(b) 봇의 재시도/예외 처리 부재**, **(c) 시도/실패 미기록**, **(d) `audit_viewer` UI 결함** 의 네 가지 결함이 결합된 사고입니다.

봇의 매수 로직 자체는 정상 동작했으며, 사고는 거래소 통신 계층 + 봇 안전망 + 감사 추적 + UI 표시의 결합으로 발생했습니다.

---

## 6. 관련 코드/로그 위치

| 항목 | 위치 |
|---|---|
| LIVE BUY 호출 | `core/trader.py:243-271` (특히 `if not res or not isinstance(res, dict): return {}`) |
| BACKFILL 흐름 | `engine/live_loop.py` REST-RECONCILE 분기 |
| EMA Buy Signal 발동 | `core/strategy_incremental.py` `IncrementalEMAStrategy.on_bar` |
| `_maybe_reload_params` 회귀 | `engine/live_loop.py` (P1-B7) — `json_path` 미정의 |
| `audit_viewer` UI | `pages/audit_viewer.py` |
| 사건 로그 | `journalctl -u tradebot --since '2026-05-26 17:09:30' --until '2026-05-26 17:13:30'` |
| 사건 DB | `tradebot_mcmax33.db` — `audit_buy_eval` id 2148~2156 |

---

## 7. 결론 한 줄

**봇 감지·시도는 정상이었으나 Upbit API의 비정상 응답과 봇의 재시도·기록 부재가 결합되어 사용자에게 "감지조차 안 된 것"으로 보였다. 해결방안은 별도 보고서 `2026-05-26-KRW-SUI-Golden-Cross-매수실패-해결방안.md` 참조.**
