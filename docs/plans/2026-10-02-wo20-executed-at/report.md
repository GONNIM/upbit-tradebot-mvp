# WO-20 조사 보고 — orders.executed_at 미기록과 boot_seed 미동작 (읽기 전용)

- 작성: 2026-10-02 (KST)
- 범위: 조사와 처방 제안. 코드·DB 무변경. 서버는 읽기만 했다 (재시작 없음). 투자자 안내 없음.
- 기준 코드: 로컬 `e444114`. 서버 `786b5cb` (기동 2026-10-02 10:03:18) 와 엔진 코드가 같다 (두 커밋 차이는 docs 19개 파일뿐).
- 코드 인용 전문: `code-quotes.md`. DB 조회 결과: `results/`.

## 결론

1. **가설은 맞다.** 체결 확인 경로는 orders 의 `state`·`executed_volume`·`avg_price`·`paid_fee`·`updated_at` 을 쓰지만 `executed_at` 은 쓰지 않는다. 쓰는 함수는 있으나 값을 넘기는 호출처가 없다. 전 사용자 orders 557행 모두 `executed_at` 이 NULL 이다. 그래서 boot_seed 복원은 지금 코드로는 한 번도 동작할 수 없다.
2. **가설 밖의 결함을 하나 더 찾았다.** 복원 조회의 정렬이 `ORDER BY executed_at , timestamp DESC` 이다 (`services/db.py:1891`). `executed_at` 이 **오름차순**이다. 지금은 모든 값이 NULL 이라 `timestamp DESC` 로 최신 행이 뽑힌다. 그러나 (가)만 적용하면 새 매수 대신 옛 매수를 고르고, 과거 행까지 채우면 가장 오래된 매수를 고른다 (메모리 DB 재현, `results/order-by-sim.txt`). 이때 진입가도 옛 주문 값이 된다. 어느 안을 고르든 이 정렬을 함께 고쳐야 한다.
3. **추천: (다) + 정렬 수정.** 상세는 D절.

## A. 코드 조사

### A1. orders.executed_at 을 쓰는 코드

| 함수 | 위치 | 쓰는 방식 | 값을 넘기는 호출처 |
|---|---|---|---|
| `insert_order` | `services/db.py:109~165` (INSERT `:140·160`) | 인자 `executed_at` (기본 None) 그대로 INSERT | **없음.** `core/trader.py:568·755·779·1054·1082·1201·1335` 7곳 모두 넘기지 않음 |
| `update_order_progress` | `services/db.py:2064~2100` (`:2086`) | `executed_at = COALESCE(executed_at, ?)` (기본 None) | **없음.** `engine/order_reconciler.py:330` 이 넘기지 않음 |
| `update_order_completed` | `services/db.py:2103~2146` (`:2127`) | `executed_at = COALESCE(executed_at, ?)` (기본 None) | **없음.** `engine/order_reconciler.py:370` 이 넘기지 않음 |
| 마이그레이션 | `services/init_db.py:488` | 열 추가만 | — |

결론: 열에 값을 쓰는 실행 경로는 **없다.** 같은 이유로 `canceled_at` 도 어떤 호출처도 넘기지 않는다 (별건, 참고).

### A2. 체결 확인 경로와 orders 갱신 열

| 경로 | 위치 | orders 에 쓰는 열 | executed_at |
|---|---|---|---|
| LIVE 시장가 매수 요청 | `core/trader.py:779~792` | INSERT: timestamp, ticker, side, price, volume=0, status='requested', provider_uuid, state=REQUESTED, requested_at, updated_at, entry_bar, meta, settings_history_id | 쓰지 않음 |
| LIVE 현재가(지정가) 매수 요청 | `core/trader.py:1082~1091` | 위와 같음 | 쓰지 않음 |
| LIVE 시장가 매도 요청 | `core/trader.py:1335~1347` | 위와 같음 (entry_bar 없음) | 쓰지 않음 |
| 발주 실패 | `core/trader.py:755·1054` | INSERT state=FAILED, requested_at | 쓰지 않음 |
| OrderReconciler 진행 (Upbit `wait`) | `engine/order_reconciler.py:268~281` → `:330` → `services/db.py:2081~2090` | executed_volume, avg_price, paid_fee, state(REQUESTED/PARTIALLY_FILLED), updated_at | `COALESCE(executed_at, NULL)` → 바뀌지 않음 |
| OrderReconciler 확정 (Upbit `done`/`cancel`) | `engine/order_reconciler.py:284~296` → `:370` → `services/db.py:2122~2135` | state(FILLED/CANCELED), executed_volume, avg_price, paid_fee, current_krw, current_coin, updated_at | 바뀌지 않음 |
| 확정 시 체결 시각 계산 | `engine/order_reconciler.py:303~316` | Upbit `trades[].created_at` 로 `exec_ts_iso` 를 **계산은 한다.** 그러나 `_fire_fill_callback` 에만 넘기고 orders 에는 쓰지 않는다 | — |
| LIMIT 체결 callback | `core/strategy_engine.py:326~363` | orders 미기록. 메모리 포지션에 `apply_entry(entry_ts=executed_ts, source="bot_limit_fill")` 만 | — |
| 강제 매수 | `services/trading_control.py:308~322` (`trader.buy_limit`/`buy_market`) → `:366` (`reconciler.enqueue`) | 위 매수 요청 INSERT + OR 확정 경로와 같음 | 쓰지 않음 |
| 강제 청산 | `services/trading_control.py:140·174` | 매도 요청 INSERT + OR 확정 경로 | 쓰지 않음 |
| TEST 모드 매수·매도 | `core/trader.py:568·1201` | INSERT status='completed' (state 없음) | 쓰지 않음 |

### A3. boot_seed 복원 경로 — executed_at 이 비었을 때

1. `engine/live_loop.py:689` `position.sync_from_wallet()`.
   - 지갑 수량으로 `has_position=True`, `qty` 를 정한다 (`core/position_state.py:96~102`).
   - `avg_price` 가 비어 있으므로 `account_positions.entry_price` → Upbit `avg_buy_price` 순으로 복구한다 (`:104~139`).
   - `entry_ts` 가 비어 있으므로 **동기화 시각(지금)** 으로 채운다 (`:144~148`).
2. `engine/live_loop.py:695` `_seed_entry_price_from_db` → `services/db.py:1814` `get_last_open_buy_order`.
   - 시각 열은 우선순위 첫 번째인 `executed_at` 을 고른다 (`services/db.py:1907~1913`). `orders` 에 `created_at`·`ts` 열은 없다.
   - 값이 NULL 이면 `entry_ts_iso` 키를 넣지 않는다 (`services/db.py:1850`).
   - 정렬은 `executed_at , timestamp DESC, ROWID DESC` (`:1889~1891`). 지금은 모두 NULL 이라 최신 행이 뽑힌다.
3. `engine/live_loop.py:714` `if entry_price is not None and entry_ts is not None:` 가 거짓이 된다. `apply_entry(source="boot_seed")` 는 불리지 않는다.
4. `engine/live_loop.py:726~732` `else` 분기에서 ERROR 로그만 남긴다. 포지션 상태는 1단계 값 그대로다.

**그때 매수 시각:** 기동 중 `sync_from_wallet` 이 실행된 시각, 곧 **재시작 시각**이다. `entry_bar` 는 `None` 이라 `get_bars_held` 가 0 을 돌려주고 (`core/position_state.py:455~456`), EMA 전략은 audit 개수로 보정한다 (`core/strategy_incremental.py:1138~1155`).

### A4. ERROR 문구

현재 (`engine/live_loop.py:728~732`):

```
❌ P3 boot seed 시각 복원 실패 → has_position=False 유지. entry_price={entry_price} entry_ts_iso={entry_ts_iso}. 수동 정리 또는 force_liquidate 필요.
```

실제로는 `has_position=True` 가 유지되고 SL/TP/DC 매도도 동작한다. "수동 정리 필요" 도 사실과 다르다.

제안 (수준은 WARNING 으로 낮춘다):

```
⚠️ [BOOT-SEED] 봇 주문의 체결 시각 없음 → boot_seed 미적용, 지갑 동기화 값 유지 | has_position=True qty={qty} avg_price={position.avg_price} (출처: 지갑) entry_ts={position.entry_ts} (기동 시각) | 정체 포지션 판정은 기동 시각부터 다시 센다
```

이 문구 수정은 D절 (나)·(다)에 묶는다. (나)가 들어가면 이 분기는 `updated_at` 마저 없는 비정상 행일 때만 탄다.

## B. 데이터 조사 (서버 DB, 읽기 전용, `results/db-b1-b3.txt`)

### B1. orders 집계 (전 사용자·전 종목)

DB 파일: `tradebot_mcmax33.db` 557행. `tradebot_default.db`·`tradebot_gon1972.db` 0행. `tradebot_.db` 는 executed_at 열 없음.

| state | side | 행 | executed_at NULL | 채워짐 |
|---|---|---|---|---|
| FILLED | BUY | 116 | 116 | 0 |
| FILLED | SELL | 286 | 286 | 0 |
| CANCELED | BUY | 134 | 134 | 0 |
| FAILED | BUY | 4 | 4 | 0 |
| (NULL), status='completed' | BUY | 8 | 8 | 0 |
| (NULL), status='completed' | SELL | 9 | 9 | 0 |

state 가 NULL 인 17행은 모두 status='completed' 이고 2026-05-24 ~ 05-26 에 몰려 있다. TEST 모드 경로(`core/trader.py:568·1201`)가 남기는 형태와 같다.

### B2. executed_at 이 채워진 행

**전무.**

### B3. KRW-JTO 매수 189건 — updated_at 을 체결 시각 대용으로 쓸 수 있는가

189건은 복원 조회와 같은 필터(`FILLED` 97건 + `CANCELED` 이면서 executed_volume>0 인 92건)다.

| 지표 | 값 |
|---|---|
| requested_at·updated_at 결측 | 0 |
| updated_at − requested_at (초) | 최소 1.6 / 중앙 2.8 / 90% 65.4 / 99% 302.5 / 최대 304.8 |
| 5초 이하 / 60초 이하 / 300초 이하 | 139 / 169 / 185 |
| 차이 > interval_sec | **6건** (id 250·306·309·384·396·409, 모두 CANCELED 부분 체결) |
| meta.interval_sec 없음 | 86건 (옛 행. 비교 제외) |

Upbit 실제 체결 시각과 직접 대조했다 (GET `/v1/order` 18건, 조회 전용, `results/db-b3-upbit-fill-time.txt`).

| 구분 | updated_at − 마지막 체결 시각 |
|---|---|
| FILLED 최근 12건 | 0.8 ~ 6.5초 |
| CANCELED 부분 체결 6건 | 102.8 ~ 305.7초 (미체결 잔량 취소 시각이 updated_at 이 됨) |

**판단:** `updated_at` 은 FILLED 행에서는 체결 시각과 수 초 차이라 대용으로 쓸 수 있다. CANCELED 부분 체결 행에서는 취소 시각이므로 최대 1봉(관측 최대 306초) 늦다. 정체 포지션 판정은 시간 단위이므로 이 차이는 판정을 최대 1봉 늦출 뿐이다. 정확한 값이 필요하면 Upbit `trades[].created_at` 이 원본이다.

## C. executed_at 을 읽는 기능과 지금의 실제 값

| 기능 | 위치 | 읽는 방식 | 지금 동작하는 값 |
|---|---|---|---|
| boot_seed 복원 (매수 시각) | `services/db.py:1907~1913·1850`, `engine/live_loop.py:714` | SELECT 시각 열 | NULL → boot_seed 미적용. 매수 시각 = 재시작 시각 (`core/position_state.py:144~148`) |
| boot_seed 복원 (행 선택 정렬) | `services/db.py:1889~1891` | ORDER BY 첫 키 (오름차순) | 모두 NULL → `timestamp DESC` 로 최신 매수 선택 (지금은 맞게 동작) |
| 정체 포지션 판정 | `core/filters/sell_filters.py:492·508` | DB 를 직접 읽지 않음. `position.entry_ts` 사용 | 재시작이 없으면 체결 callback·매수 경로의 실제 시각. 재시작 뒤에는 재시작 시각 |
| trailing 복원 | — | DB 를 읽지 않음 (메모리 값만) | 재시작 시 초기화 (executed_at 과 무관) |
| POSITION-SYNC 자동 복구 | `core/strategy_engine.py:554~575` | `get_last_open_buy_order` 의 price·entry_bar 만 사용 | 진입가 = 최신 매수가, 매수 시각 = 감지 시각(now). 정렬 결함의 영향은 (가) 적용 뒤에 생김 |
| 대시보드 미실현 수익률 | `pages/dashboard.py:865` | `get_last_open_buy_order` 의 price 만 사용 | 최신 매수가 (지금 맞음). 정렬 결함의 영향은 (가) 적용 뒤에 생김 |
| 대시보드 주문 상태 | `pages/dashboard.py:2888` `fetch_order_statuses` | SELECT executed_at | 표준출력 print 만. 화면 표시 아님 |
| 최근 체결 조회 | `services/db.py:2149` `fetch_recent_fills` | SELECT executed_at | 호출처 없음 |
| 설정 이력 손익 | `services/settings_history.py:666~697` → `pages/settings_history.py:219` | SELL 주문 매칭에 `executed_at or timestamp` | executed_at 없음 → `orders.timestamp`(요청 시각)로 ±60초 매칭. 시장가 매도는 요청~체결이 수 초라 매칭 성립 (코드 근거, 실측 대조는 하지 않음) |
| 감사 로그 페이지 체결 시각 | — | `pages/` 안에 executed_at 사용처 없음 | 해당 없음 (감사 로그는 audit_trades.timestamp 사용) |
| `detect_position_and_seed_entry` | `engine/live_loop.py:391·404` | `get_last_open_buy_order` | 정의만 있고 호출처 없음 |

## D. 처방 제안 (구현하지 않음)

### D1. 필수 동반 수정 — 정렬

어느 안이든 `services/db.py:1889~1891` 의 정렬을 "최신 체결 우선" 으로 고쳐야 한다. 예: `ORDER BY COALESCE(executed_at, updated_at, timestamp) DESC, ROWID DESC`. 고치지 않으면 (가) 적용 뒤 boot_seed·POSITION-SYNC·대시보드 미실현 수익률이 **옛 매수의 진입가**를 쓴다 (`results/order-by-sim.txt`).

### D2. 세 안 비교

| | (가) 체결 확인 시 executed_at 기록 | (나) 복원 시 updated_at 대용 | (다) (가)+(나) |
|---|---|---|---|
| 변경 범위 | `engine/order_reconciler.py` `_finalize_order`·`_update_order_progress` 에 `executed_at` 전달. 값은 이미 계산하는 Upbit `trades[].created_at` (`:303~311` 과 같은 방식). + D1 정렬 | `services/db.py:1907~1913` 시각 열을 `COALESCE(executed_at, updated_at)` 로. + D1 정렬 + A4 문구 | 두 가지 모두 + D1 + A4 |
| 해결 대상 | 앞으로의 주문만. 지금 보유분·과거 189건은 그대로 | 과거·미래 주문 모두. 시각 정밀도는 FILLED 수 초, CANCELED 부분 체결 최대 1봉 | 과거는 updated_at, 미래는 실제 체결 시각 |
| 위험 | D1 없이 배포하면 옛 진입가 선택 (치명). OR 확정 경로 수정이라 체결 처리 회귀 위험 | boot_seed 가 처음으로 실제 동작한다. `apply_entry` 가 **orders 의 단일 주문 평균가**로 avg_price 를 덮는다 → 봇 매수 뒤 앱 추가 매수가 섞인 포지션이면 Upbit 평균가와 달라진다 (지금은 Upbit 평균가 사용). entry_bar 는 옛 봉 번호라 bars_held 음수 → audit 보정 (기존 경로) | (가)·(나) 위험의 합. 평균가 위험은 (나)와 같음 |
| 위험 완화 | D1 정렬 시험 필수 | 지갑 수량과 주문 executed_volume 이 다르면 avg_price 는 지갑 값을 유지하고 entry_ts 만 주문에서 가져온다 | 같음 |
| 시험 | 메모리 DB: OR 확정 호출 시 executed_at 저장, 정렬이 최신 행 선택 (옛 NULL 행 섞인 경우 포함) | 메모리 DB: executed_at NULL + updated_at 있음 → boot_seed apply_entry, entry_ts=updated_at. 혼합 포지션 → avg_price 지갑 유지. 옛 코드에서 실패 확인 | 두 시험 모두 + 기존 게이트 |

**추천: (다) + D1 + A4 문구.** 이유:
- (가)만으로는 지금 보유분과 과거 주문이 풀리지 않는다. 그리고 D1 없이 들어가면 진입가를 잘못 고른다.
- (나)만으로는 앞으로도 시각이 최대 1봉 부정확하다. 원본 체결 시각을 이미 계산하고 있어 (가)의 추가 비용이 작다.

### D3. 기존 189건 보정 (운영자 결정 사항)

- 내용: KRW-JTO 매수 189건(전체로는 FILLED·CANCELED 체결 행)의 `executed_at` 을 채운다.
- 값의 출처 두 가지:
  - `updated_at`: DB 안에서 끝난다. CANCELED 부분 체결은 최대 1봉 늦다.
  - Upbit `trades[].created_at`: 정확하다. 행마다 GET `/v1/order` 1회(조회 전용)가 필요하다.
- (나)가 들어가면 복원에는 보정이 필요 없다. 보정은 손익 매칭 등 다른 조회의 정확도를 위한 선택이다.
- D1 없이 보정하면 복원이 가장 오래된 매수를 고른다 (`results/order-by-sim.txt` 세 번째 줄). **보정은 D1 배포 뒤에만** 할 수 있다.
- DB 를 쓰는 작업이므로 백업과 운영자 승인이 필요하다. 이번 조사에서는 하지 않았다.

### D4. 포지션 보유 중 재시작 실측 검증

| 방법 | 내용 | 장점 | 단점 |
|---|---|---|---|
| 실 서버 | 봇이 포지션을 잡은 뒤(인위 매수 없이) 다음 배포 재시작 때 확인: journal `[POSITION-APPLY] source=boot_seed ts=<주문 체결 시각>`, ERROR 부재, 첫 매도 평가의 entry_ts·avg_price | 실제 지갑·Upbit 응답·Streamlit 기동 순서까지 검증 | 시점을 고를 수 없다 (봇 매수 대기). 보유 중 재시작 자체가 실매매 위험 (재시작 공백 약 10초, trailing 무장 초기화). 결함이면 실자금 포지션에 바로 영향 |
| 로컬 시험 DB | 서버 DB 를 읽기 전용으로 복사해 오거나 메모리 DB 를 만들어, `.env` 격리·더미 키·가짜 지갑으로 `sync_from_wallet` → `_seed_entry_price_from_db` → `apply_entry` 순서를 재현. 회귀 시험으로 고정 | 안전하다. 반복할 수 있다. 앱 혼합 포지션·NULL 행 혼재·부분 체결 같은 경계 사례를 만들 수 있다. 옛 코드 실패를 보일 수 있다 | Upbit 실제 응답·타이밍·Streamlit 기동 순서는 검증하지 못한다 |

**제안:** 로컬 시험 DB 검증을 배포 조건으로 삼는다. 실 서버 검증은 일부러 재시작하지 않는다. 봇 포지션 보유 중에 다른 이유로 배포할 때 운영자 승인 아래 관찰 항목으로 붙인다.

## E. 묶음

- `report.md` (이 문서)
- `code-quotes.md` (A1~A4·C 코드 인용, 행 번호 포함)
- `results/db-b1-b3.txt`, `results/db-b3-upbit-fill-time.txt`, `results/order-by-sim.txt`
- `results/wo20_b.py`, `results/wo20_b3.py`, `results/wo20_order_sim.py`, `results/wo20_quotes.sh`
- `commands.txt`
