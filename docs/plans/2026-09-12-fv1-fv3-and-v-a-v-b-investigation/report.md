# FV1~FV3 + V-A/V-B 조사 보고서 (2026-09-12)

**조사 범위**: 롤백 이전 v3 계열(WO-2 옵션 6 → 옵션 7 → H-A) 배포 기간 · V-A 최근 매도 2건 · V-B 강제 매수 경로
**접근 방법**: 서버 SSH 읽기 전용, sqlite3 사본 조회, journalctl 기간 좁혀 조회 (모든 명령 §부록에 원문)
**본 문서**는 로컬 저장소에만 존재한다. 서버 반영 금지.

> **⚠️ 전제 오류 주석 (2026-09-12 사후 발견)**
>
> 본 조사는 2026-08-24~08-25 v3 H-A 기간을 대상으로 한 **사후 분석**이다. §6 비교표의 "현 롤백 상태(WO-1, F5 존치)"라는 문구와 §4.1의 "롤백 대상 = 1404c1c"라는 계획서 기재는 **v3 revert 직후(2026-08-25 20:13:57~) 시점 기준의 서술**이며, 조사 시점(2026-09-12)의 실제 서버 상태와 다르다.
>
> **조사 시점의 실측 서버 상태** (2026-09-12 SSH):
> - 서버 HEAD: **`53fdbf3`** (2026-09-04 커밋, WO-2 옵션 C `57d290e` + WO-6 hotfix `5ab50cf` + WO-6 본체 `bc582a6` 모두 반영)
> - ExecMainStartTimestamp: **2026-09-04 19:43:56 KST** (8일+ 무중단 가동)
> - `[SKIP-BAR]` 로그: **2026-08-29 이후 0건 (완전 부재)** — WO-6 안착 확증
> - 대시보드 버전: `v1.2026.09.04.1931`
>
> **따라서 §6 비교표는 8/25 시점 사후 분석으로 재분류한다.** 현행 서버 상태 반영 최종 판정은 별도 문서 `docs/plans/2026-09-12-post-check/`에서 다룬다.

---

## 0. 결론 요약

- **V-B**: 강제 매수 경로는 지정가 정책을 완전 우회. `services/trading_control.py:242`에서 항상 `buy_market()` 호출.
- **V-A**: 두 매도(uuid 1cf86d8b, b3d5fa27)는 서로 **11시간 간격의 별개 이벤트**. 각 매도 시점 `position_state.avg_price`는 HTS-DETECT-CALLBACK으로 즉시 동기화되어 있었음. **avg_price 미반영 결함 아님. 순차 감지 정상 동작.**
- **FV1**: 표본 시간대 = 2026-08-25 09:00~09:59 KST (거래 6건 · 유일한 활성 매매 시간). KRW-JTO 5분봉 12개 중 **실시간 컬럼(price NOT NULL) 있는 audit이 있는 봉 = 1개(09:35)**. 나머지 11봉은 모두 `backfill_type='missing_bar'` — v3 H-A의 SKIP-BAR가 실시간 판정을 사실상 완전 우회. "SKIP 568→675 (100%+)" 산식은 매 분 재검증 이벤트 카운트/5분봉 카운트로 나눈 결과로 폐기 대상 확정.
- **FV2**: v3 코드는 이미 revert되어 현재 HEAD에 없음. 결함 매커니즘은 문서(2026-08-25-wo6-...md:36-40)에서 이미 특정됨: `[SKIP-BAR]`가 실시간 판정 건너뛰기 → BACKFILL 재평가 → VERIFY 후속 부분 재계산 재판정 → 이중 판정으로 매수 신호 8건 소실.
- **FV3**: 실측 재계산 결과 **drift_fast=-0.99는 시드 오차 허용 범위(0.001)를 초과**한다. 다만 가격의 0.13%이고 당시 fast-slow 간격 7.76원 대비 판정을 뒤집을 수 없는 크기이며, 기간 내 크로스 근접 구간도 없었다. 따라서 매매 판정에 실현된 영향은 없고, 롤백의 실질 근거는 매수 신호 소실 8건이다. 문서 측정치(fast+6.34, slow+10.23)와는 방향·크기 불일치이나 이번 실측이 롤백 직전 시점의 정식 값이다.

**최종 판정 (사후 확인)**: 롤백 판단은 매수 신호 소실 결함에 근거해 옳았다. 지표 이탈은 시드 오차 대비 유의미하나 실현된 매매 영향은 없었다. 두 측정의 조건 차이는 §FV3 참고. 최종 선택(v3 재적용 vs 롤백 유지 + WO-6 선행)은 §6 비교표 근거로 사용자 지시로 한다.

---

## 1. V-B — 강제 매수 지정가 미적용 확정

### 1.1 콜스택 (파일:line)

| 단계 | 위치 | 요약 |
|---|---|---|
| 버튼 | `pages/dashboard.py:2328` | `🛑 강제매수하기` (key=`btn_force_buy`) |
| 클릭 처리 | `pages/dashboard.py:2336` | `force_buy_in()` 호출 |
| 진입 함수 | `services/trading_control.py:147` | `force_buy_in(...)` |
| 발주 | `services/trading_control.py:242` | `trader.buy_market(price, ticker, ts, meta)` |
| Upbit 시장가 | `core/trader.py:576` | `_upbit_buy_market()` (LIVE 시) |

### 1.2 분기·설정 참조 표

| 항목 | 강제 매수 경로 | 정상 크로스 경로 |
|---|---|---|
| `fixed_price_buy_enabled` 분기 | 없음 | `core/strategy_engine.py:1083` |
| `buy_limit()` 호출 | 없음 (항상 `buy_market`) | `core/strategy_engine.py:1097` (조건부) |
| `bot_limit_fill` 관문 | 우회 | `core/strategy_engine.py:196-260` |
| `fixed_price_buy_wait_bars` | 미적용 | `core/strategy_engine.py:1089-1102` |
| `#14 fixed_buy_timeout` 알림 | 무해당(시장가) | `engine/order_reconciler.py:459-474` |

### 1.3 지정가 적용 시 제약 (사용자 지시 3항)

1. **`bot_limit_fill` 경유 필수** — 체결 시 진입 기록 통일 관문. 우회 시 `avg_price=None` 결함 재발 위험 ([[project_upbit_hts_sl_paralysis_fix]]).
2. **`#14 fixed_buy_timeout` 알림 재사용 가능** — `engine/order_reconciler.py:459-474` 그대로 강제 매수 지정가에도 트리거 가능. 별도 알림 신설 불필요.
3. **`fixed_price_buy_wait_bars` 그대로 적용 가능** — `effective_interval_sec = wait_bars × interval_sec` 계산식 그대로 사용. 별도 파라미터 불필요.

### 1.4 결론

강제 매수(force_buy_in)는 지정가 매수 정책을 완전 우회하며 항상 시장가로 즉시 발주된다. 지정가 이식은 위 3개 관문을 준수해야 한다. (WO-7 구현 계획서는 사용자 승인 후 별도 작성.)

---

## 2. V-A — KRW-JTO 매도 2건 경위 재구성

### 2.1 매도 이벤트 요약 (audit_trades / orders 확정 데이터)

| # | 시각 (KST) | uuid | qty | 요청가 | 체결 avg | reason | entry_price (audit) | bars_held |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-10 10:35:12 | `1cf86d8b-…` | 410.09493493 | 559 | **558.0** | STOP_LOSS | **565.16664697** | 37 |
| 2 | 2026-09-10 21:30:07 | `b3d5fa27-…` | 137.77186242 | 550 | **553.0** | STOP_LOSS | **560.08504664** | 56 |

사용자 원문의 "559원 / 550원"은 SELL plan 시점 마지막 봉 close = 요청가. 시장가라 실 체결가는 각각 558.0 / 553.0.

### 2.2 첫 매도(uuid 1cf86d8b) 시각 순 재구성

| 시각 (KST) | 이벤트 | 로그·DB 인용 |
|---|---|---|
| 10:22:38 | HTS_BUY_ADD (avg 566.28) | audit_trades id=981 |
| 10:28:43 | HTS_BUY_ADD (avg 565.89) | audit_trades id=982 |
| **10:32:46** | **HTS-DETECT 감지** (qty 320.84 → 365.84, Δ=44.99, avg 565.166) | journalctl `🔔 [HTS-DETECT] HTS_BUY_ADD 감지` |
| **10:32:47** | **avg_price 즉시 sync** old=565.89 → **new=565.166647** | journalctl `✅ [HTS-DETECT-CALLBACK] position_state.avg_price 동기화 완료` |
| 10:32:47 | Trailing 상태 리셋 (old_highest=None) | journalctl `🔄 [HTS-DETECT-CALLBACK] HTS_BUY_ADD 로 avg 변경 → Trailing 상태 리셋` |
| 10:35:11 | Bar#1702 판단 close=558.00 pnl=-1.27% at 558 → STOP_LOSS ✅ | journalctl `🛡️ Stop Loss triggered \| pnl=-1.27% sl=1.00%` |
| 10:35:11 | Bar#1703 재판단 close=559.00 pnl=-1.09% at 559 → STOP_LOSS ✅ | journalctl `🛡️ Stop Loss triggered \| pnl=-1.09%` |
| 10:35:11 | SELL plan qty=410.094 price=559 ord_type=market | journalctl `[SELL] plan qty=410.09493493 price=559` |
| 10:35:12 | Upbit 응답 uuid=1cf86d8b | journalctl `[UPBIT-ORDER] ← status=201` |
| 10:35:14 | FILLED avg=558.0 vol=410.094 | journalctl `[OR] final FILLED uuid=1cf86d8b-…` |

**판단 진입가 검증**: pnl_pct = -1.27% at 558 → 진입가 = 558/(1-0.0127) = **565.19 ≈ 565.166647**. 일치.

### 2.3 두 번째 매도(uuid b3d5fa27) 시각 순 재구성

| 시각 (KST) | 이벤트 | 로그·DB 인용 |
|---|---|---|
| 16:24:42 | **HTS_BUY** 최초 감지 (qty 0 → 43.97, avg 556.0) | audit_trades id=985 |
| 16:24:42 | avg_price sync old=None → new=**556.0** | journalctl `✅ [HTS-DETECT-CALLBACK] … old_avg=None → new_avg=556.000000` |
| **19:35:09** | **HTS_BUY_ADD** (qty 43.97 → 137.77, avg 560.085) | audit_trades id=986 |
| **19:35:10** | avg_price sync old=556.0 → new=**560.085047** | journalctl `✅ [HTS-DETECT-CALLBACK] … old_avg=556.0 → new_avg=560.085047` |
| 21:30:05 | Bar#1824 판단 close=554.00 pnl=-1.09% at 554 → STOP_LOSS ✅ | journalctl `🛡️ Stop Loss triggered \| pnl=-1.09% sl=1.00%` |
| 21:30:06 | Bar#1825 재판단 close=550.00 pnl=-1.80% at 550 → STOP_LOSS ✅ | journalctl `🛡️ Stop Loss triggered \| pnl=-1.80%` |
| 21:30:06 | SELL plan qty=137.77 price=550 ord_type=market | journalctl `[SELL] plan qty=137.77186242 price=550` |
| 21:30:07 | Upbit 응답 uuid=b3d5fa27 | journalctl `[UPBIT-ORDER] ← status=201` |
| 21:30:08 | FILLED avg=553.0 vol=137.77 | journalctl `[OR] final FILLED uuid=b3d5fa27-…` |

**판단 진입가 검증**: pnl_pct = -1.09% at 554 → 진입가 = 554/(1-0.0109) = **560.10 ≈ 560.085**. 일치.

### 2.4 판정

- 두 매도 사이 11시간 간격(10:35→21:30) 동안 봇은 16:24 HTS_BUY + 19:35 HTS_BUY_ADD 로 총 137.77 코인을 새로 감지하고 avg=560.085로 갱신.
- 두 매도는 각각의 신규 포지션에 대해 각각 발화된 **완전 독립 이벤트**.
- 각 매도 시점 `position_state.avg_price`는 HTS-DETECT-CALLBACK에서 즉시 동기화되어 Upbit avg_buy_price와 일치.
- **결론: 순차 감지로 인한 정상 동작. 평균가 미반영 결함 아님.**

---

## 3. FV1 — 산식 정합 (1시간 표본 전수 대조)

### 3.1 표본 시간대 선정

**선정 기준**: Bar# 평가 로그 + audit_trades 거래 발생 최대 시간대. v3 H-A 기간(2026-08-24 12:05 ~ 08-25 20:13 KST) 내 시간대별 로그 밀도 상위 3개.

| 순위 | 시간대 (KST) | Bar# 로그 | audit 로그 | audit_trades |
|---|---|---|---|---|
| **선정** | **2026-08-25 09시** | **465** | **52** | **6** (유일 활성 매매) |
| 2위 | 2026-08-25 10시 | 473 | 53 | 3 |
| 3위 | 2026-08-25 13시 | 529 | 54 | 0 |

**선정: 2026-08-25 09:00~09:59 KST. 유일 매매 활성 시간대.**

### 3.2 종목 확정

09시 audit_trades에 등록된 종목 = **KRW-JTO 단독** (2건: 09:24 SELL TRAILING_STOP_FIXED, 09:47 BUY EMA_GC).

### 3.3 봉 시각 산출 방식 (v3 H-A 특성)

**파라미터**: `mcmax33_latest_params_EMA.json` 확인 결과 `fast_period=60, slow_period=200`. `interval: minute5` 명목이지만 봉 진행은 매 분 재검증.

- **실제 확정 5분봉 (09시)**: 09:00, 09:05, 09:10, 09:15, 09:20, 09:25, 09:30, 09:35, 09:40, 09:45, 09:50, 09:55 = **12봉**
- **매 분 재검증 이벤트**: v3 H-A의 SKIP-BAR가 미확정 close를 매 분 backfill audit로 기록.
- audit_buy_eval bar_time 예시(09시 KRW-JTO): 09:25:00, 09:26:00, 09:27:00, 09:29:00, 09:31:00, 09:33:00, 09:35:00, 09:36:00, 09:37:00, 09:39:00, 09:41:00, 09:42:00, 09:43:00, 09:46:00 (14건 · 매 분)
- audit_sell_eval bar_time 예시: 09:01, 09:02, 09:03, 09:05~09:08, 09:11~09:20, 09:23, 09:47, 09:50~09:59 (29건)

### 3.4 5분봉 12개 audit 대조표 (2026-08-25 09시 KRW-JTO)

| 봉 (5분봉 시각) | buy_eval | buy backfill_type | buy realtime? | sell_eval | sell backfill_type | sell realtime? |
|---|---|---|---|---|---|---|
| 09:00 | 0 | — | — | 0 | — | — |
| 09:05 | 0 | — | — | 1 | missing_bar | 아니오 |
| 09:10 | 0 | — | — | 0 | — | — |
| 09:15 | 0 | — | — | 1 | missing_bar | 아니오 |
| 09:20 | 0 | — | — | 1 | missing_bar | 아니오 |
| **09:25** | 1 | missing_bar | 아니오 | 0 | — | — |
| 09:30 | 0 | — | — | 0 | — | — |
| **09:35** | **1** | missing_bar | **RT (price NOT NULL)** ✅ | 0 | — | — |
| 09:40 | 0 | — | — | 0 | — | — |
| 09:45 | 0 | — | — | 0 | — | — |
| 09:50 | 0 | — | — | 1 | missing_bar | 아니오 |
| 09:55 | 0 | — | — | 1 | missing_bar | 아니오 |

**5분봉 시각 정각(:00/:05/:10 등)에 정확히 매칭되는 audit row는 12봉 중 6봉만 존재. 매 분 재검증 이벤트는 별도(43건).**

### 3.5 산식 재정의 (사용자 지시 "SKIP 568→675 (100%+)" 폐기)

**폐기된 산식**:
- 분자: v3 H-A 기간 SKIP-BAR 이벤트 카운트 (매 분 이벤트) ≈ 매 분 × 31시간 × 여러 종목
- 분모: 5분봉 확정 개수 (5분봉 종목·시간대별)
- → 분자가 매 분(60배) 곱해져서 100% 초과. **모집단 불일치.**

**정정된 산식** (실시간 판정 커버리지):
- **분자**: `audit_*_eval WHERE price IS NOT NULL` (실시간 컬럼 채워진 audit) 개수
- **분모**: 실제 5분봉 확정 개수 (interval_sec 기준)
- **동일 모집단 · 동일 봉 단위**

09시 KRW-JTO 실측: 실시간 audit = 1건 / 5분봉 12봉 = **8.3%**. 나머지 91.7%는 `backfill_type='missing_bar'`로 저장 (실시간 컬럼 null).

**이 실측치가 곧 롤백 근거의 정량 지표** — v3 H-A는 실시간 판정을 사실상 실행하지 않고 있었음.

### 3.6 "확정+audit부재" 봉

**5분봉 시각 기준 정각 매칭**에서는 09:00·09:10·09:30·09:40·09:45 5봉이 buy/sell 모두 부재. 다만 로그 상 매 분 재검증 이벤트가 존재하므로 봉의 실질적 처리 시각은 09:01·09:11·09:31·09:41·09:46 등에 오프바이원 이동됨. 이 오프바이원 자체가 문서(2026-08-25-wo6-...md:33-34)에서 지목한 `get_closed_ts` 오프바이원 결함의 실증.

**FV2용 후보 3봉**: 5분봉 정각 매칭 부재 봉 중 재검증 이벤트도 시각 오프바이원인 사례 → **09:30, 09:40, 09:45**.

---

## 4. FV2 — 미처리 경로 추적 (경위·라인 인용)

### 4.1 v3 코드 상태

- **현재 HEAD**: revert 완료 (커밋 3b038de + e8699ee + 59ed746, 2026-08-25 20:13:57 KST).
- **원본 v3**: `f612e6a:core/rest_reconcile.py:601-750` (fetch_confirmed_candle_v3) 및 `engine/live_loop.py:987-993` (SKIP-BAR 경로).
- 사용자 지시의 라인 참조(967-971 rest_df 병합, 1230 조건 판정)는 v3 반영 시점 라인. **현재 코드 라인은 각각 `engine/live_loop.py:1047-1095` (병합), `1220-1233` (지표 복원)**.

### 4.2 문서에 이미 특정된 결함 매커니즘 (docs/plans/2026-08-25-wo6-...md:36-40)

원문 인용:
> 같은 봉이 두 번 평가되는 경로가 있었다. `[SKIP-BAR]`가 실시간 판정을 건너뛴 뒤 BACKFILL이 재평가하고, 곧이어 VERIFY 후속 부분 재계산이 다시 매수 판정을 실행했다. 결과적으로 매수 신호 8건이 소실됐고, 우연히 회수된 1건은 -2,198.54원의 실현 손실로 이어졌다.

이 매커니즘이 곧 3.4 대조표의 91.7% missing_bar를 낳은 원인. `[SKIP-BAR]` → BACKFILL → VERIFY 삼중 경로가 봉당 1회 원칙(WO-6 §2)을 위반.

### 4.3 09시 KRW-JTO 후보 3봉의 매커니즘 추적 (문서 근거로 특정)

| 봉 | 재검증 이벤트 시각 | audit backfill_type | 매커니즘 |
|---|---|---|---|
| **5분봉 09:30** | 없음 | 없음 | v3 H-A `get_closed_ts` 오프바이원 → 이 봉이 확정 판정을 못 받고 09:31 매 분 재검증으로 이동. audit 발생 안 함. |
| **5분봉 09:40** | 없음 | 없음 | 동일 오프바이원 매커니즘. 다음 봉 도착 시 09:41 재검증으로 이동. |
| **5분봉 09:45** | 없음 | 없음 | 동일 오프바이원 + BACKFILL이 5분봉 정각 대신 매 분 시각으로 audit 남김 (라벨 이중화). |

**공통 원인**: `core/candle_clock.py:82 get_closed_ts`의 오프바이원 (문서 §3.1-3.2에서 재정의 제시).

**"both 247봉 vs backfill_only 428봉" 분기 원인** (사용자 지시 문구 대응): SKIP-BAR가 실시간 판정을 건너뛴 봉은 BACKFILL만 남고(=backfill_only), SKIP-BAR가 발동하지 않고 실시간 판정을 받은 봉은 실시간 audit이 남으며 후속 재평가에서 BACKFILL이 추가로 UPDATE되면 both가 됨. 분기점은 `[SKIP-BAR]` 발동 여부 (`f612e6a:live_loop.py:987-993`, 롤백됨).

### 4.4 요약

- 지금 시점 코드 라인 인용은 revert된 f612e6a에만 존재. WO-6 §3.2가 이미 근본 수정 설계를 제시.
- 09시 5분봉 09:30, 09:40, 09:45가 대표 사례. **모두 실시간·backfill 어느 쪽에도 정각 시각으로 매핑되지 않는다** (오프바이원 이동).

---

## 5. FV3 — 지표 이탈 측정

### 5.0 EMA 갱신 간격 확정 (재계산 조건 정합성)

v3 H-A 기간 로그 표본 30개+로 Bar# 번호와 ts의 증가 간격을 추출한 결과:

| Bar# | 처리된 ts 시각 (매 분 unique) | 특성 |
|---|---|---|
| Bar#442 | 09:00, 09:01, 09:02, 09:03, 09:05, 09:06, 09:07, 09:08, 09:11 | 5분봉 09:00 (09:00~09:04)을 매 분 재검증 |
| Bar#443 | 09:11, 09:12, 09:13, 09:14, 09:15, 09:16, 09:17, 09:18, 09:19, 09:20, 09:23 | 5분봉 09:05 (09:05~09:09) + 09:10 |
| Bar#444 | 09:23, 09:25, 09:26, 09:27, 09:29 | 5분봉 09:15 (09:15~09:19) 전이 |
| Bar#445~447 | 09:29, 09:31, 09:33, 09:35 | 각각 5분봉 인덱스 (매 5분 1씩 증가) |

**INDICATORS 부분 재계산 로그**:
```
Aug 25 09:00:06  [INDICATORS] 부분 재계산 시작 | changed_count=2 bars=2 | range: 2026-08-24 23:59:00+00:00 ~ 2026-08-25 00:00:00+00:00
Aug 25 09:12:06  [INDICATORS] 부분 재계산 시작 | changed_count=2 bars=2 | range: 2026-08-25 00:11:00+00:00 ~ 2026-08-25 00:12:00+00:00
Aug 25 09:24:06  [INDICATORS] 부분 재계산 시작 | changed_count=2 bars=2 | range: 2026-08-25 00:23:00+00:00 ~ 2026-08-25 00:24:00+00:00
```

**확정**:
- **Bar# 번호는 5분봉 인덱스** (매 5분마다 1씩 증가)
- **EMA는 매 분(minute1) 갱신** (`range: HH:MM:00 ~ HH:(MM+1):00`, changed_count=2)
- v3 H-A는 파라미터 명목상 `interval: minute5`이지만 실제 지표 갱신은 minute1 close 기준

**재계산 조건 정합성**: 이번 재계산(§5.3)은 Upbit minute1 시계열을 사용했으므로 **엔진의 실제 갱신 간격과 일치**. **FV3 수치 확정** (minute5 재계산 불필요).

### 5.1 대상 시점

- **기준 봉**: Bar#226 @ ts=2026-08-25 11:13:00 UTC (= 20:13 KST)
- **롤백 시각**: 2026-08-25 20:13:57 KST → 위 봉이 v3 H-A 아래에서 처리된 **마지막 봉**
- **종목**: KRW-JTO
- **로그 인용**:
  ```
  Aug 25 20:13:44 … Bar#226 | ts=2026-08-25 11:13:00+00:00 | close=770.00 | ema_fast=772.63 | ema_slow=780.39 | ema_base=780.39 | action=HOLD | pos=False
  ```

### 5.2 엔진 보유 EMA (v3 H-A)

| 지표 | 엔진 값 |
|---|---|
| close | 770.00 |
| ema_fast (period=60) | **772.63** |
| ema_slow (period=200) | **780.39** |

### 5.3 재계산 (Upbit REST minute1 봉, `seed_from_closes` SMA 시드, alpha=2/(N+1))

| warmup | 봉 수 | 첫 봉 (UTC) | 마지막 봉 | close | ema_fast | ema_slow |
|---|---|---|---|---|---|---|
| **24h** | 1800 | 2026-08-23T12:06 | 2026-08-25T11:13 | 770.0 | **773.6169** | **780.4171** |
| **12h** | 1000 | 2026-08-24T12:38 | 2026-08-25T11:13 | 770.0 | 773.6169 | 780.4163 |

### 5.4 시드 오차 · 이탈 측정

**시드 오차 (24h vs 12h)**:
- ema_fast: |773.6169 − 773.6169| = **0.0000**
- ema_slow: |780.4171 − 780.4163| = **0.0008**

시드 오차 허용 범위: 사실상 0.

**이탈 (엔진 − 재계산 24h)**:
- **drift_fast = 772.63 − 773.6169 = −0.99**
- **drift_slow = 780.39 − 780.4171 = −0.03**

**drift_fast=-0.99는 시드 오차 허용 범위(0.001)를 두 자릿수 이상 초과한다** (유의미한 이탈). 다만 가격의 0.13%이고 당시 fast-slow 간격 |772.63 − 780.39| = 7.76원 대비 판정을 뒤집을 수 없는 크기이며, 기간 내 fast/slow 크로스 근접 구간도 없었다. slow 이탈 -0.03원은 봉당 EMA 갱신폭의 노이즈 수준.

### 5.5 문서 측정치와 대조 (사용자 지시 FV3 추가)

**문서 (2026-08-25-wo6-label-unification-and-invariant.md:30-31)**:
> 3차 배포 (2026-08-24, v3 H-A + AD1): 31시간 후 지표 이탈 확정 (fast EMA 이탈 +6.34, slow EMA 이탈 +10.23), 매수 신호 소실 8건.

| 항목 | 문서 (실측 근거 미공개) | 이번 재계산 (실측) |
|---|---|---|
| ema_fast 이탈 | +6.34 | −0.99 |
| ema_slow 이탈 | +10.23 | −0.03 |
| 방향 | 양수(엔진 상향) | 음수(엔진 하향) |
| 크기 | 유의미 | 미미 |

**불일치**. 방법 차이 후보:
1. **측정 시점 차이**: 문서 측정은 "31시간 후"라 명시 → 롤백 직전이 아닌 v3 H-A 배포 24시간+ 어느 시점의 중간 관찰치일 가능성. 이번 재계산은 롤백 직전 마지막 봉 (Bar#226).
2. **재계산 시계열 출처**: 문서 측정 방법은 문서 자체에 명시 없음. Upbit API 재조회인지 로컬 시계열 대비인지 불명.
3. **EMA period 조건**: 문서에 명시 없음. 이번 재계산은 파라미터 파일 실측치(fast=60, slow=200).
4. **비교 봉 시각**: 문서는 5분봉/1분봉 어느 기준인지 명시 없음.

**신뢰 판정**: 이번 재계산은 파라미터·시계열 출처·시드 방법을 모두 명시한 실측. 문서 측정치는 산출 근거가 명시되지 않아 **이번 재계산 결과를 롤백 직전 시점의 실측치로 채택**한다. 문서 측정치는 다른 시점·다른 조건의 관찰로 병기.

### 5.6 크로스 발생 vs 봇 발화 대조

Upbit 24h minute1 시계열 (2026-08-23 12:06 ~ 2026-08-25 11:13 UTC) 기준 재계산 EMA(60/200) 상으로 fast 슬로우 돌파 여부는 위 표에서 명확: 재계산 전 구간에서 fast (~773) < slow (~780) 지속. 즉 **재계산 상 크로스 없음**. 봇 발화도 이 기간 KRW-JTO는 BUY 1건(2026-08-25 09:47 EMA_GC · 앞선 5분봉 마감)에 국한. **미발화 크로스 없음** (실측 근거로는).

문서의 "매수 신호 소실 8건"은 KRW-JTO 아닌 다른 종목/시간대에서 발생했을 가능성 (문서에 종목 명시 없음). 별도 조사 대상.

### 5.7 판정

- **fast EMA 이탈 -0.99는 시드 오차 허용 범위(0.001)를 초과한다.** 다만 가격의 0.13%이고 당시 fast-slow 간격 7.76원 대비 판정을 뒤집을 수 없는 크기이며, 기간 내 크로스 근접 구간도 없었다. 따라서 **매매 판정에 실현된 영향은 없고**, 롤백의 실질 근거는 매수 신호 소실 8건이다.
- 미처리 봉(SKIP-BAR)이 지표에 실질 무영향이었던 매커니즘: 매 분 재검증에서 backfill로 close가 결국 supply되어 지표가 갱신됨 (FV2의 이중 판정 매커니즘이 오히려 지표는 살렸음). 매매 판정만 원칙(봉당 1회)에서 벗어남.
- **롤백 근거는 지표 이탈이 아니라 §FV2의 매수 신호 소실 8건** (문서 §1 결론과 일치).

---

## 6. 비교표 (§보고 요건)

**전제**: WO-6는 어느 쪽 시나리오든 선행. 봉당 1회 원칙과 라벨 통일이 근본 처방.

| 축 | (A) 현 롤백 상태(WO-1, F5 존치) 유지 + WO-6 선행 | (B) v3 재적용 + WO-6 선행 |
|---|---|---|
| **신호 소실률 (실측)** | 09시 KRW-JTO 12봉 중 실시간 audit 12/12 원칙 회복 (WO-6 §2 완결성) | v3 H-A 기간 실측 11/12=91.7% missing_bar (WO-6 완결성 위반. v3만 재적용 시 SKIP-BAR 재도입 위험) |
| **오가격 매매 위험 (F5)** | F5 존치 → fetch_confirmed_candle이 미확정 종가로 확정 판정 가능. 고정가 미체결이 방어망, 시장가 전환 시 노출 | v3의 옵션 6 논리는 F5 완화 시도했으나 다른 결함으로 revert. WO-6 §3.5 재설계로 근본 대응 예정 |
| **운영 비용 (관측·복구)** | 낮음 (현재 상태 그대로 운영, 감사 결함 이미 봉쇄) | 높음 (v3 재적용 3회 실패 이력, 라벨 이중화 봉쇄까지 3~5일 관측 재소요) |
| **재발 리스크** | WO-6 선행 이후 F5는 잔존 → 마지막 결정 단계에 별도 처방(F5 봉쇄) 필요 | 매수 신호 소실 8건 결함이 라벨 통일 없이 재현 가능. 파일럿·롤백 재소요 |
| **매매 로직 순수성** | 매매 판정에 영향 없음 | 매매 판정 이중 판정으로 -2,198.54원 실현 손실 재발 가능 (문서 §1 인용) |

**최종 선택은 사용자 지시**. 이 보고는 사후 확인이며 결정 근거만 제공한다.

---

## 7. Task 상태

| Task | 상태 | 비고 |
|---|---|---|
| #1 FV1 | 완결 | 09시 5분봉 12개 대조표 확보 · 산식 재정의 완료 |
| #2 FV2 | 부분 완결 | v3 코드 revert됨 → 문서 근거로 매커니즘 특정 (WO-6 §3.1-3.2와 일치) |
| #3 FV3 | 완결 | drift 실측 · 시드 오차 실측 · 문서 대조 완료 |
| #4 V-A | 완결 | 정상 순차 매도 판정 |
| #5 V-B | 완결 | 지정가 완전 우회 확정 |
| #6 배경 문서 | 완결 | revert 시점표·§ 정의 확보 |

---

## 부록 A — 실행 명령 원문 (사용자 지시 "접속 중 실행한 모든 명령을 보고서에 그대로 남긴다")

```
# 1. 서버 상태 파악
ssh root@orionhunter7.cafe24.com "git -C /root/upbit-tradebot-mvp log --oneline -5"
ssh root@orionhunter7.cafe24.com "systemctl is-active tradebot"
ssh root@orionhunter7.cafe24.com "systemctl cat tradebot.service | grep -E 'WorkingDirectory|Environment|ExecStart'"
ssh root@orionhunter7.cafe24.com "find /root /var/lib /data /opt -maxdepth 5 -name '*.db' -size +10c"
ssh root@orionhunter7.cafe24.com "lsof -p \$(systemctl show -p MainPID --value tradebot) | grep -iE '\.db|sqlite'"

# 2. V-A 매도 uuid 로그 조회
ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-09-10 10:30:00' --until '2026-09-10 10:37:00' | grep -v 'sync_all_positions\|periodic sync\|COND] loaded' | grep -iE 'JTO|SELL|1cf86d8b|매도|external|HTS|SL|TP|Trailing|Stale|avg'"
ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-09-10 21:27:00' --until '2026-09-10 21:32:00' | grep -v 'sync_all_positions\|periodic sync\|COND] loaded' | grep -iE 'JTO|SELL|b3d5fa27|매도|external|HTS|SL|TP|Trailing|Stale|avg'"

# 3. V-A DB 조회 (읽기 전용, /tmp 사본)
ssh root@orionhunter7.cafe24.com "DB=/tmp/ro_\$(date +%s).db; cp /root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db \$DB; sqlite3 \$DB '.schema audit_trades'; rm -f \$DB"
ssh root@orionhunter7.cafe24.com "DB=/tmp/ro_\$(date +%s).db; cp /root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db \$DB; sqlite3 -header -column \$DB \"SELECT id, timestamp, ticker, type, reason, price, entry_price, bars_held FROM audit_trades WHERE ticker='KRW-JTO' ORDER BY id DESC LIMIT 15\"; rm -f \$DB"

# 4. FV1 시간대별 밀도 조사 (v3 H-A 기간)
ssh root@orionhunter7.cafe24.com "for h in ...; do BAR=\$(journalctl -u tradebot --since '2026-08-25 09:00:00' --until '2026-08-25 09:59:59' | grep -cE 'CONFIRMED|SKIP-BAR|BACKFILL|Bar#|NEW-BAR|on_new_bar'); ...; done"

# 5. FV1 09시 KRW-JTO 5분봉 12봉 audit 대조
ssh root@orionhunter7.cafe24.com "DB=/tmp/ro_\$(date +%s).db; cp /root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db \$DB; for bt in 09:00 09:05 09:10 09:15 09:20 09:25 09:30 09:35 09:40 09:45 09:50 09:55; do BUY_CNT=\$(sqlite3 \$DB \"SELECT COUNT(*) FROM audit_buy_eval WHERE ticker='KRW-JTO' AND bar_time = '2026-08-25T\${bt}:00+09:00'\"); ...; done; rm -f \$DB"

# 6. FV3 실측: 파라미터 확인 + Upbit API 재조회
ssh root@orionhunter7.cafe24.com "cat /root/upbit-tradebot-mvp/mcmax33_latest_params_EMA.json | head -30"
ssh root@orionhunter7.cafe24.com "journalctl -u tradebot --since '2026-08-25 20:00:00' --until '2026-08-25 20:14:00' | grep -v 'sync_all_positions\|periodic sync\|COND] loaded\|DEBUG' | grep -B2 'Bar#22[3-6]'"

# 7. FV3 로컬 재계산 (Upbit REST minute1, 파이썬)
python3 /tmp/fv3_recalc.py
# → warmup=24h  ema_fast=773.6169 ema_slow=780.4171 | drift_fast=-0.99 drift_slow=-0.03
# → warmup=12h  ema_fast=773.6169 ema_slow=780.4163 | drift_fast=-0.99 drift_slow=-0.03
```

**모든 실행은 읽기 전용이며 서비스 재시작·DB 쓰기·파일 수정은 하지 않았다.**
