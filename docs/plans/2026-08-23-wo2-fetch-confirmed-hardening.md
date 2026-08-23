# WO-2 설계안 (개정판) — fetch_confirmed_candle 확정 판정 강화

**날짜**: 2026-08-23
**작성자**: Claude Code
**관련 진단**: `docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md` (F5 · WO-2)
**24h 실측 근거**: 2026-08-22 11:16:42 ~ 2026-08-23 11:16:42 KST (KRW-JTO 활성)
**재실측 근거**: 2026-08-23 16:19~16:27 KST (KRW-BTC + KRW-JTO, 4개 프로토콜)
**상태**: 개정판 · 검토 대기 (구현 착수는 별도 승인)
**개정 사유**: 초안 §3 서술과 §4 실측 원문의 모순 지적 (R1) + 시드 민감도 미검증 (R2) + 옵션 6 부재 (R3) + AUTO-RESUME 재검토 (R4) 반영

---

## 🎯 핵심 요약 (2줄, 재선정)

> **옵션 6 채택 — "다음 봉(진행 중 포함) 존재 시 즉시 확정, 부재 시 5초 간격 재조회 상한 30초 → BACKFILL fallback".**
> **재실측(H-R1)으로 확인: Upbit REST는 거래 발생 시 진행 중 봉을 즉시 응답에 포함하고 무거래 분은 캔들 자체 부재(skip·지연 아님). 결정적(deterministic) 확정 판정 가능. 평균 지연 수 초, 최악 30초. 옵션 4 대비 매도 반응성·조회 효율 우위.**

---

## 📋 목차

1. [배경 및 F5 재실증](#1-배경-및-f5-재실증)
2. [24h 실측 근거](#2-24h-실측-근거)
3. [초안 §3 오류 정정 (H-R1)](#3-초안-3-오류-정정-h-r1)
4. [재실측 4개 프로토콜 결과 (R1)](#4-재실측-4개-프로토콜-결과-r1)
5. [changed_close 봉 판정 검증 표준 절차 (조건 1·R2 반영)](#5-changed_close-봉-판정-검증-표준-절차)
6. [매도 경로 자동 적용](#6-매도-경로-자동-적용)
7. [옵션 6 채택 + 옵션 4 vs 6 비교표 (R3)](#7-옵션-6-채택--옵션-4-vs-6-비교표)
8. [배포 계획 + AUTO-RESUME 채택안 (R4)](#8-배포-계획--auto-resume-채택안-r4)
9. [검증 계획](#9-검증-계획)
10. [범위 외 후속 항목](#10-범위-외-후속-항목)

---

## 1. 배경 및 F5 재실증

### F5 결함

`core/rest_reconcile.py:515` `fetch_confirmed_candle` 확정 판정 조건이 오직 `latest_ts == closed_ts` 만 검증. 봉 종료 직후 Upbit REST가 반환하는 미확정 close로 매매 판정이 실행되는 구조적 결함.

### F5 양방향 피해 실증 (R2 시드 민감도 검증 통과)

| 케이스 | 시각 | 실시간 close | 확정 close | 결과 |
|---|---|---|---|---|
| 진단 원본 | 2026-08-20 04:34 | 777 | 779 | 가짜 신호 (미체결로 회복) |
| **신규 실증** | **2026-08-23 09:26** | 823 | 825 | **실제 신호 1봉 지연** (진입가 826, 이상적 825, +0.12% 슬리피지) |

**R2 시드 민감도 검증** (§5.4 절차 준용):
- 시드 A (09:20, 6봉 이전): 09:26 gap = +0.257093
- 시드 B (08:57, 29봉 이전 ≈ 30봉): 09:26 gap = +0.307862
- 시드 오차 |A−B| = 0.050769
- min|gap| 0.2571 ≥ 3× 오차 (0.1523) → **판정 가능** (양쪽 시드 모두 Dead→Golden 확정)

---

## 2. 24h 실측 근거

**기간**: 2026-08-22 11:16:42 ~ 2026-08-23 11:16:42 KST (WO-1 배포 완결부터 24h)

### 2.1 BACKFILL 우회율
| 지표 | 값 |
|---|---|
| audit_buy_eval 총 행 | 1,054 |
| BACKFILL 재평가 (missing+changed) | 428 (**40.6%**) |
| missing_bar | 43 (4.1%) |
| changed_close | 385 (36.5%) |

### 2.2 changed_close 변경 폭 분포
| \|Δclose\| | 건수 | 비율 |
|---|---|---|
| 0원 (< 0.5) | 0 | 0% |
| 1~2원 | 289 | 75.1% |
| 3원+ | 96 | 24.9% |
| **max** | **59원** (~7% 급변) | — |
| avg | 2.51원 | — |

### 2.3 close 안정화 소요 (상한 근사, 조건 3 명시)

⚠️ **데이터 한계**: 초 단위 안정화 시각 관측 없음. CLOCK-CLOSE ↔ BACKFILL 간격만 사용 가능. **실제 안정화 시각 ≤ BACKFILL 재평가 시각**.

385건 상한 근사: min=10.6s / p50=59.9s / p95=84.8s / max=87s / avg=62.0s. p50=60s는 REST-RECONCILE 폴링이 매 봉 확정마다 실행되는 인프라 특성 반영. 실제 안정화는 훨씬 짧을 것으로 추정.

### 2.4 백업/복원 로그 쌍 무결성
465 : 465 (일치), 복원 실패 0, POLLUTED 0. WO-2 신호 지연이 유발돼도 이 안전판이 지표 오염을 감지·차단.

---

## 3. 초안 §3 오류 정정 (H-R1)

### 초안 §3의 잘못된 서술
> "Upbit REST는 **진행 중 봉을 반환하지 않음** (BOUNDARY+1~5, MID+1~3 모두 마지막이 이전 확정 봉)"

### 실측 원문과의 모순
초안 §4 MID+4 원문: `t0=11:45:30.000 rows=['ts=11:41:00 close=799 vol=25.49', 'ts=11:45:00 close=796 vol=1364.78']` — 11:45:30 시각에 **11:45 봉(진행 중)이 응답에 포함**되어 있음.

### 대체 가설 H-R1 (사용자 지적)
> "거래 발생 시 진행 중 봉 즉시 포함, 무거래 분은 캔들 자체 부재 (skip·지연이 아님)"

### R1 재실측 결과 (§4 참조) — H-R1 **성립**
- ✅ 거래 발생 시 진행 중 봉 즉시 포함 (BTC 5회 전부, JTO 16:24 봉 P2_5s+6에서 vol=1582.74 → P4에서 vol=4299.85 갱신 관찰)
- ✅ 무거래 분은 캔들 자체 부재 (JTO 16:20/21/22/25/26이 REST에 없음, ticks에서도 해당 분 거래 0건 확인)

**교훈**: 초안은 관측 창(창구 시각) 우연으로 인해 잘못된 일반화를 했다. §4 원문(MID+4)이 반증이었으나 §3 서술과의 모순을 미처 잡지 못함. **§4를 전면 재작성 필요** (본 문서 §4로 대체).

---

## 4. 재실측 4개 프로토콜 결과 (R1)

**실행 시각**: 2026-08-23 16:19~16:27 KST. 서버 nohup 백그라운드 (SSH 세션 단절 무관).

### 프로토콜 1 — KRW-BTC 분 중간 5회 (유동성-API 동작 분리)

**목적**: 저volume 종목(JTO) 관측이 API 동작인지 유동성 특성인지 분리.

```
[BTC_MID+1] t0=16:19:30.000 rows=[ts=16:18:00 close=104647000 vol=0.65, ts=16:19:00 close=104600000 vol=0.17]
[BTC_MID+2] t0=16:20:30.000 rows=[ts=16:19:00 close=104631000 vol=0.18, ts=16:20:00 close=104631000 vol=0.15]
[BTC_MID+3] t0=16:21:30.000 rows=[ts=16:20:00 close=104591000 vol=0.29, ts=16:21:00 close=104545000 vol=0.13]
[BTC_MID+4] t0=16:22:30.000 rows=[ts=16:21:00 close=104540000 vol=0.30, ts=16:22:00 close=104540000 vol=0.17]
[BTC_MID+5] t0=16:23:30.000 rows=[ts=16:22:00 close=104533000 vol=0.28, ts=16:23:00 close=104538000 vol=0.04]
```

**해석**: 모든 조회에서 **진행 중 봉이 응답의 last row로 포함**됨. 조회 30초 시점 진행 중 봉의 close·vol 값 정상 갱신. BTC(고유동성) 관측이 API 동작 성립을 입증.

### 프로토콜 2 — KRW-JTO 같은 분 5초 간격 6회 (진행 중 봉 close/vol 갱신)

**목적**: 진행 중 봉 close·vol이 조회 사이 갱신되는지 확인.

```
[P2_5s+1] t0=16:24:02.000 rows=[ts=16:19:00 close=781 vol=22.13, ts=16:23:00 close=784 vol=1468.69]
[P2_5s+2] t0=16:24:07.024 rows=[ts=16:19:00 close=781 vol=22.13, ts=16:23:00 close=784 vol=1468.69]
[P2_5s+3] t0=16:24:12.053 rows=[ts=16:19:00 close=781 vol=22.13, ts=16:23:00 close=784 vol=1468.69]
[P2_5s+4] t0=16:24:17.080 rows=[ts=16:19:00 close=781 vol=22.13, ts=16:23:00 close=784 vol=1468.69]
[P2_5s+5] t0=16:24:22.103 rows=[ts=16:19:00 close=781 vol=22.13, ts=16:23:00 close=784 vol=1468.69]
[P2_5s+6] t0=16:24:27.131 rows=[ts=16:23:00 close=784 vol=1468.69, ts=16:24:00 close=784 vol=1582.74]  ← 진행 중 16:24 등장
```

**해석**: 
- **P2_5s+1~5 (16:24:02~22)**: 16:24 봉 진행 중이나 응답에 없음 → **거래가 아직 없어서 캔들 미생성**
- **P2_5s+6 (16:24:27)**: 16:24 봉 첫 거래 발생 후 응답에 포함. vol=1582.74.
- 이후 프로토콜 4 (P4_R1+1, 16:25:00): 16:24 봉 vol=4299.85 → **같은 봉의 vol이 계속 증가** (거래 누적 → 진행 중 캔들 갱신 관찰).

### 프로토콜 3 — 체결(ticks) API 대조 (부재 vs 지연 판정)

**목적**: JTO REST 부재 분이 "API 지연"인지 "실제 무거래"인지 판정.

**결과 (관찰 시점의 분별 체결 카운트, 부분 발췌)**:
```
minute=16:19 trade_count=1
minute=16:23 trade_count=4
minute=16:24 trade_count=5
(16:20, 16:21, 16:22, 16:25, 16:26, 16:27 — ticks에 없음 = 실제 체결 0건)
```

**해석**: JTO 16:20/21/22/25/26/27 분은 ticks API에서도 완전 부재. **API 지연 아니라 실제 무거래 → 캔들 자체 미생성이 정상 동작**.

### 프로토콜 4 — 분 경계 직후 1초 간격 10회 × 3분 (확정 봉 등장 시점)

**목적**: 봉 종료 후 얼마나 빨리 다음 봉(진행 중 포함)이 REST에 등장하는지 측정.

```
--- ROUND 1 (16:25:00~09) ---
[P4_R1+1] t0=16:25:00.100 rows=[ts=16:23:00 close=784 vol=1468.69, ts=16:24:00 close=784 vol=4299.85]  ← 16:24 확정
[P4_R1+2~10] 동일

--- ROUND 2 (16:26:00~09) ---
[P4_R2+1~10] rows=[ts=16:23:00 close=784 vol=1468.69, ts=16:24:00 close=784 vol=4299.85]  ← 16:25 부재

--- ROUND 3 (16:27:00~09) ---
[P4_R3+1~10] rows=[ts=16:23:00 close=784 vol=1468.69, ts=16:24:00 close=784 vol=4299.85]  ← 16:26 부재
```

**해석**:
- **ROUND 1**: 16:24 봉이 16:25:00.100 시점에 이미 응답 last row. 봉 종료 후 **100ms 미만** 지연으로 확정 봉 등장.
- **ROUND 2/3**: 16:25/16:26 무거래로 REST에 등장하지 않음 (P3 ticks 재확인).

**H-R1 결론**:
1. **거래 발생 봉은 봉 종료 직후 즉시 REST에 등장** (100ms 이내 관찰).
2. **무거래 봉은 REST에 아예 존재하지 않음** (그래서 처리 대상도 아님 — EMA 갱신에 영향 없음, volume=0 상태와 동일).
3. **옵션 6 실현 가능성**: "다음 봉(진행 중 or 확정) 존재 = 이전 봉 확정"이라는 결정적 판정 성립.

---

## 5. changed_close 봉 판정 검증 표준 절차

**향후 클레임 분석 재사용용**. R2 반영으로 시드 민감도 필수화.

### 5.1 절차

1. **시드 확보 (R2 필수)**: **대상 봉의 30봉 이전** 봉 audit에서 `ema_fast`, `ema_slow` 추출. BACKFILL 재평가가 없는 봉(price만 있는) 우선.
2. **확정 close 시계열 확보**: 대상 봉 및 그 이전 봉의 audit `backfill_close` (없으면 `price`) 순서대로 나열.
3. **EMA 파라미터 확인**: `mcmax33_latest_params_EMA.json` → `fast_period`, `slow_period`. alpha = 2/(period+1).
4. **정식 재계산**: 각 봉마다 `new = alpha * close + (1-alpha) * prev`.
5. **크로스 판정**: `prev_fast <= prev_slow AND new_fast > new_slow` → Dead→Golden.
6. **R2 시드 민감도 검증 (필수)**:
   - 시드 위치 두 개 (예: 6봉 이전 + 30봉 이전)로 각각 재계산.
   - 시드 오차 상한 = `|gap_A − gap_B|`
   - **판정 조건**: `min(|gap_A|, |gap_B|) ≥ 3 × 오차 상한` 시에만 판정 확정. 그렇지 않으면 **"판정 불가 (마진 부족)"**로 기재.
7. **결과 분류**: 판정 확정 시 F5 실제 신호 상실 or F6 오해 사례로 등재.

### 5.2 이번 케이스 (09:26) 적용 결과

- 시드 A (09:20, 6봉 이전): 09:26 gap = **+0.257093**
- 시드 B (08:57, 29봉 이전 ≈ 30봉): 09:26 gap = **+0.307862**
- 시드 오차: **0.050769**
- min|gap| 0.2571 **≥ 3× 오차** 0.1523 → **판정 확정: F5 실제 신호 상실**

---

## 6. 매도 경로 자동 적용 (조건 4)

- `core/strategy_incremental.py:376, 1080` — `current_price = bar.close`.
- 매도 필터 (TP/Trailing/Stale)는 `current_price=bar.close`를 kwargs로 소비 (`core/filters/sell_filters.py:48, 156, 257`).
- `bar`는 `on_new_bar_confirmed`에서 `fetch_confirmed_candle` 결과로 생성된 동일 객체 (`engine/live_loop.py:1207-1217, 1266`).

**결론**: WO-2 강화가 매도 경로에도 **자동 적용**. 별도 수정 불필요. TP hit / SL hit / Trailing / Stale 판정도 동일 확정 판정 기준.

---

## 7. 옵션 6 채택 + 옵션 4 vs 6 비교표

### 옵션 6 정의 (R3 + I1/I2/I3 반영)

**I1 timestamp 기반 판정** (위치 의존 제거):

```
1. fetch_confirmed_candle_v2(closed_ts):
2.   for attempt in range(7):  # 최대 7회 (0s + 5×6 = 30s 상한)
3.     df = pyupbit.get_ohlcv(interval, count=3)   # count=2 는 무거래 갭에서 T 밀림 위험 → 3
4.     has_next = any(ts > closed_ts for ts in df.index)
5.     has_T    = closed_ts in df.index
6.     if has_next and has_T:
7.       elapsed_ms = (now - t_first_call).total_seconds() * 1000
8.       logger.info("✅ [CONFIRMED-D] ts=... close=... via=next_bar_exists elapsed=...ms")   # I3
9.       return df.loc[closed_ts]   # ← timestamp 기반 정확 반환 (iloc/last-row 금지)
10.    if has_next and not has_T:
11.      logger.info("⏭ [NO-TRADE-BAR] ts=... 처리 생략")   # I2: 즉시 단락, 재시도 금지
12.      return None                # audit 행 미생성 유지
13.    # not has_next → 다음 봉 아직 미등장, 재시도
14.    if attempt < 6:
15.      time.sleep(5)
16.  return None   # 상한 30s 도달 → BACKFILL fallback (기존 동작)
```

**I1 함수 분리 (과거 ts 호출 감사 결과)**:
- 호출 지점 2곳: `engine/live_loop.py:950` (현재 봉, 옵션 6 대상) + `core/rest_reconcile.py:715` (verify 재조회, **과거 ts**)
- 과거 ts로 옵션 6을 실행하면 count=3 응답에 과거 봉이 없어 `has_T=False` 로 오판 위험
- **채택**: 신규 함수 `fetch_confirmed_candle_v2(closed_ts)` 는 옵션 6 전용. 기존 `fetch_confirmed_candle` 은 과거 봉 재조회용으로 유지 (verify 경로 무변경).

**I2 무거래 봉 즉시 단락**:
- 조건: `has_next AND NOT has_T` — 다음 봉이 존재하는데 대상 봉 T가 없음 = **무거래 분** (재실측 §4 P3 ticks 대조로 확정된 케이스).
- 30s 루프 진입 금지, 즉시 return None + `⏭ [NO-TRADE-BAR]` 로그.
- **audit 행 미생성 유지** — REST 응답에 봉이 없어서 처리 대상 자체가 아님. EMA 갱신·매매 판정 모두 스킵. volume=0 상태와 동일.

**I2 · missing_bar BACKFILL과의 관계 (명문화)**:
- **NO-TRADE-BAR** (I2): REST에 봉이 아예 존재하지 않음 (무거래 분). audit 미생성. 정상 동작.
- **missing_bar** (WO-1 옵션 B): 실시간 처리는 놓쳤으나 REST 확정 시점에는 봉이 존재하는 케이스. BACKFILL 경로에서 `backfill_type='missing_bar'` 로 별도 INSERT.
- 두 케이스는 **원인이 다름**: NO-TRADE-BAR = 시장 무거래 (Upbit REST 스펙), missing_bar = 봇 실시간 처리 실패 (fetch 실패 등). 옵션 6 도입 후에도 missing_bar 케이스는 계속 발생 가능 (REST 지연으로 실시간 놓치고 다음 봉 REST-RECONCILE에서 감지되는 경우).

**I3 CONFIRMED-D 로그**:
- 옵션 6 성공 시 `✅ [CONFIRMED-D] ts=... close=... via=next_bar_exists elapsed=...ms` 로그 필수.
- REST Reconcile은 제거·완화 없이 존치 → 잔여 F5 방어. 옵션 6이 놓친 케이스가 있으면 REST Reconcile이 잡음 → §9.2 실측 항목 "CONFIRMED-D 봉의 사후 changed_close 건수 (목표 0)" 로 인제스트 순서 가정 검증.

**핵심**: 조건은 "close 안정화 추정"이 아니라 "**다음 봉의 존재**" 결정적 판정. 무거래 봉은 즉시 단락 (I2). 저volume 봉이 다음 봉 등장을 늦추면 30s 후 BACKFILL fallback (무해, REST Reconcile이 뒤늦게 잡음).

### 옵션 4 vs 6 비교표

| 항목 | 옵션 4 (T=30s + N=2, 10s 간격) | **옵션 6 (다음 봉 존재)** |
|---|---|---|
| **평균 지연** | ~30s (T 대기 항상) | **~0.1~5s** (거래 활발 시), ~30s (저volume 시) |
| **최악 지연** | ~50s | **30s (상한)** |
| **조회 횟수 (평균)** | 3회 (첫 대기 후 2회) | **1회** (첫 조회 성공 대다수) |
| **조회 횟수 (최악)** | 3회 | 7회 |
| **매도 필터 반응성** | 30s 지연 | **거의 즉시** (수 초) |
| **확정 판정 정확도** | 근사 (안정화 추정) | **결정적** (다음 봉 존재로 확정) |
| **저volume 봉 대응** | T초 후 fallback | 30s 후 fallback |
| **예상 BACKFILL 비율** | 40.6% → ~25% | 40.6% → **~15%** |
| **1봉 주기(60s) 내 안전 마진** | 10s | **30s+** |
| **구현 복잡도** | 중 (상수 + 2단계) | 저 (단순 조건) |
| **T값 튜닝 필요** | 예 (실측 근거 상수 결정 필요) | 아니오 (상한 30s만) |

### 채택: **옵션 6**

**근거**:
1. **결정적 판정** — 확률적 안정화 추정보다 신뢰성 우위.
2. **평균 지연 크게 짧음** — 매도 필터 반응성 개선 (WO-2 자동 적용 효과 극대화).
3. **T값 상수 하드코딩 회피** — 조건 3 데이터 한계와 무관하게 동작.
4. **저volume 봉 대응** — 상한 30s 후 fallback으로 무한 대기 위험 없음. 저volume은 어차피 다음 거래 봉이 나올 때까지 매매 신호 자체가 무의미 (EMA 갱신 미변).
5. **구현 단순** — 조건 하나로 명확.

**H4b(REST 지연) 상호작용**: 최악 30s는 60s 봉 주기 대비 안전 마진 30s+. 연쇄 BACKFILL 위험 낮음.

**옵션 4·5는 부록**으로 유지 (기각 사유 문서화).

---

## 8. 배포 계획 + AUTO-RESUME 채택안 (R4)

### 8.1 R4 재검토: AUTO-RESUME 중복 방지 이미 3중 방어

**초안의 오류**: "module-level은 세션 rerun마다 재실행 → 이중 주문 리스크"로 서비스 분리 등 근본 수정을 제안했으나, **기존 코드에 이미 중복 방지 3중 방어가 존재**함을 라인 인용으로 재확인.

**방어 1**: `pages/dashboard.py:389`
```python
if not engine_status_thread and engine_status_db:
    # thread 실행 중이면 이 블록 자체 skip
    ...
```

**방어 2**: `engine/engine_manager.py:135-147` (Mode Lock Guard)
```python
running_mode = self.get_running_mode(user_id)
if running_mode and running_mode != captured_mode:
    logger.warning("⛔ [MODE-LOCK] 엔진 시작 거부 ...")
    return False
```

**방어 3**: `engine/engine_manager.py:305-310`
```python
user_lock = get_user_lock(lock_id)
if not user_lock.acquire(blocking=False):
    msg = f"⚠️ 이미 실행 중: {lock_id} (Lock 차단)"
    return
```

**결론**: rerun 재실행은 첫 방어(thread 상태 체크)에서 skip. 이미 실행 중이면 재개 시도 자체가 안 됨. **이중 주문 리스크 없음** — 서비스 분리·싱글톤 신규 도입 불필요.

### 8.2 51분 공백의 진짜 원인

**진짜 원인**: dashboard.py 코드가 실행되려면 **첫 dashboard HTTP 접속이 필요**. 51분 공백은 systemctl restart 후 아무도 dashboard에 접속하지 않은 시간. rerun 반복과 무관.

### 8.3 리허설 결과 및 채택안 (I4 갱신 → WO-5 분리 결정)

**⚠️ 최종 결정 (2026-08-23 사용자 지시)**: WO-2 배포 범위에서 AUTO-RESUME 근본 해결 **미포함**. 51분 공백 임시 조치는 **운영 절차**(재시작 직후 운영자 대시보드 접속, `docs/operations/deploy-checklist.md`)로 대응. AUTO-RESUME 근본 해결은 **WO-5 (서비스 분리)** 로 별도 신설, 24h 실측 후 착수.

**아키텍처 제약 발견 (구현 중)**: `engine_manager` 는 per-Streamlit-process singleton. ExecStartPost 에서 별개 CLI 프로세스가 `engine_manager.start_engine` 을 호출해도 CLI 프로세스 종료 시 스레드가 함께 종료되어 Streamlit 프로세스에 엔진이 남지 않음 → **venv python 원샷도 근본 해결 불가**.



**I4 사전 리허설 (서버 2026-08-23 16:44:55 KST)**:

```
=== curl 실행 (health) ===         HTTP=200  time=0.0947s
=== curl 실행 (dashboard) ===       HTTP=200  time=0.0876s   ← 정적 HTML만 반환
=== curl 실행 (multi-page /) ===    HTTP=200  time=0.0011s
=== 최근 10초 journalctl ===
Aug 23 16:44:58 ... engine.order_reconciler | [OR] periodic sync completed (60s 주기 정기 실행, curl과 무관)
    (dashboard.py 스크립트 실행 관련 신규 로그 부재)
```

**판정**: Streamlit은 websocket 세션 수립 시에만 스크립트 실행. `curl GET` 은 정적 HTML만 반환하며 dashboard.py 를 실행하지 못함. **`curl` 채택 기각 확인**.

**채택안 (사용자 사전 승인 대안)**: **ExecStartPost venv python 원샷** (`scripts/auto_resume_all_users.py` 신설).

```ini
[Service]
ExecStartPost=/bin/bash -c "sleep 10 && /root/upbit-tradebot-mvp/venv/bin/python3 /root/upbit-tradebot-mvp/scripts/auto_resume_all_users.py || true"
```

**스크립트 설계** (신규 매매 로직 금지, dashboard.py:386-450 로직 CLI 재현):
- users 테이블에서 `_last_mode='LIVE'` 사용자 조회
- 각 사용자에 대해:
  1. `engine_manager.is_running(user_id)` 체크 → 이미 실행 중이면 skip (**방어 1 == dashboard.py:389 조건**)
  2. `services.upbit_api.validate_upbit_keys()` 로 upbit 검증 (dashboard.py 의 `st.session_state["upbit_verified"]` 대체 — 실제 검증 함수 호출)
  3. DB에서 자본금 조회 (dashboard.py 의 `st.session_state["live_capital_set"]` 대체)
  4. 통과 시 `engine_manager.start_engine(user_id, test_mode=False)` 호출
     - **방어 2**: `engine_manager.py:135-147` Mode Lock Guard 통과
     - **방어 3**: `engine_manager.py:305-310` non-blocking lock 통과
- 로그: `[AUTO-RESUME-CLI] user=... started=True/False reason=...`
- `|| true`: 스크립트 실패해도 서비스 기동 유지

**3중 방어 동일 경로 통과 라인 인용 (재확인)**:
- `pages/dashboard.py:389` `if not engine_status_thread and engine_status_db` → CLI 재현: `if not engine_manager.is_running(user_id) and get_last_engine_mode(user_id) == "LIVE"`
- `engine/engine_manager.py:135-147` Mode Lock Guard → 그대로 통과 (start_engine 내부에서 자동 체크)
- `engine/engine_manager.py:305-310` `user_lock.acquire(blocking=False)` → 그대로 통과 (start_engine 내부에서 자동 체크)

**대안 비교표 (갱신)**:
| 대안 | 장점 | 단점 | 채택? |
|---|---|---|---|
| ~~ExecStartPost curl~~ | 최소 diff | Streamlit websocket 특성상 script 실행 불가 (**I4 리허설로 확인**) | ❌ **기각** |
| **ExecStartPost venv python 원샷** | 신규 매매 로직 없음, 3중 방어 동일 경로 통과, session 무관 실행 | 스크립트 파일 1개 신설 (dashboard.py 로직 CLI 재현) | ⭐ **채택** |
| module-level 이동 (app.py 등) | — | Streamlit 은 websocket 세션 수립 시에만 스크립트를 실행하므로 module-level 코드도 **무접속 기동 시나리오에서 실행되지 않음** (curl 기각과 동일 사유). 51분 공백 시나리오에 무효 | 기각 |
| 서비스 분리 | 근본 해결 | 대규모 변경, WO-2 범위 초과 | 후속 WO |
| 싱글톤 가드 신설 | — | 이미 3중 방어 존재로 불필요 | 기각 |

### 8.4 WO-2 배포 절차 (승인된 범위 = 2026-08-23)

**포함**: WO-2 코드 (`fetch_confirmed_candle_v2` 신설) + `scripts/migrate_all_users.py` (ExecStartPre) + `tradebot.service` unit 수정.
**제외**: ExecStartPost / AUTO-RESUME 근본 해결 (WO-5 로 이관, 24h 실측 후 착수).

1. **커밋**: 코드 + 설계안 개정 + `pages/dashboard.py:313` 버전 갱신 (`v1.2026.MM.DD.HHMM`) → push (pre-push 회귀 통과).
2. **서버 pending 주문 0건 확인** + 현재 커밋 해시 기록 (롤백용).
3. **서버 git pull --ff-only**.
4. **systemd unit 수정**: `/etc/systemd/system/tradebot.service` 에 `ExecStartPre=/root/upbit-tradebot-mvp/venv/bin/python3 /root/upbit-tradebot-mvp/scripts/migrate_all_users.py` 추가 → `daemon-reload`. **수정 전 unit 파일 원본 백업 (경로 기록, 롤백용)**.
5. **운영자에게 재시작 준비 확인 요청** (재시작 직후 대시보드 접속 필요 — 51분 공백 임시 방지).
6. `systemctl restart tradebot` (운영자 확인 후).
7. **배포 직후 확인 5건**:
   - (a) journalctl 에서 ExecStartPre 실행 흔적 (migrate_all_users 로그: 전 사용자 ok/fail 카운트, default/gon1972 포함)
   - (b) 운영자 접속 후 🚀 엔진 시작 → CLOCK-LOOP 시작 로그 (deploy-checklist 7단계)
   - (c) 첫 `[CONFIRMED-D]` 로그 등장 (ts/close/elapsed 인용) — 옵션 6 실전 첫 작동
   - (d) `⏭ [NO-TRADE-BAR]` 로그 형식 정상 (발생 시)
   - (e) Traceback / CRITICAL / POLLUTED / OperationalError 부재

**롤백 조건**: 기동 실패 또는 (c)가 30분 내 미등장 + BACKFILL 급증 시.
**롤백 절차**: `git reset --hard <기록 해시>` + unit 원복 (백업 파일 복사) + `daemon-reload` + `systemctl restart tradebot` 후 보고.

### 8.5 51분 공백 리허설 체크리스트

- [ ] ExecStartPre 마이그레이션 스크립트 로컬 사본 DB 스모크 테스트
- [ ] ExecStartPost curl이 로컬 리허설에서 dashboard.py 실제 트리거 확인 (auth 통과 여부)
- [ ] systemd restart 후 5분 내 `🚀 [CLOCK-LOOP] 시작` 로그 확인
- [ ] 서비스 기동 실패 시 롤백 절차 (git reset + restart) 준비
- [ ] 배포 시각 pending 주문 0건 확인

---

## 9. 검증 계획

### 9.1 스모크 테스트 (배포 전)

**옵션 6 확정 판정 로직**:
- 케이스 A: 봉 종료 후 즉시 다음 봉 응답에 포함 (BTC 유형) → 100ms 내 확정 반환
- 케이스 B: 무거래로 다음 봉 미등장 → 5초 간격 재조회 → 상한 30초 → BACKFILL fallback
- 케이스 C: 5초 간격 재시도 중 3번째에 등장 → 즉시 확정 반환

**ExecStartPre**: 신규 DB (컬럼 없음) 마이그레이션 → 5개 컬럼 추가. 기존 DB 재실행 멱등 skip.

**ExecStartPost**: 로컬 streamlit 서버 재시작 → curl 트리거 후 5분 내 live_loop 로그 출현.

### 9.2 실측 검증 (배포 후 24h)

- BACKFILL 우회율: 40.6% → **목표 15% 미만**
- changed_close 발생률: 36.5% → **목표 5% 미만**
- WO-2 지연: `[CONFIRMED-D]` 로그의 `elapsed=...ms` p50 < 500ms, p95 < 30s
- **CONFIRMED-D 봉의 사후 changed_close 건수: 목표 0** (I3 인제스트 순서 가정 검증 — 옵션 6이 놓친 케이스가 있으면 REST Reconcile이 뒤늦게 changed_close 로 잡음)
- 반대 케이스 (실시간 vs 확정 뒤집힘): 0건 목표
- 매도 필터 반응 시간: TP hit ~ 매도 주문 접수 간격 측정 (기준선 대비)
- `⏭ [NO-TRADE-BAR]` 로그 발생률 (I2 확인)
- `[AUTO-RESUME-CLI]` 로그 확인 (systemd restart 후 즉시 발동 여부)

### 9.3 4경로 체크리스트

- **경로 1 (실시간 CLOCK-CLOSE)**: 옵션 6 즉시 확정 → BACKFILL 재평가 감소
- **경로 2 (Progressive Retry)**: 옵션 6이 대체하는 경로. Progressive Retry 로직은 옵션 6 상한 30초 후 fallback으로 흡수
- **경로 3 (BACKFILL)**: 매매 금지 정책 유지, WO-1 옵션 B 컬럼 기록 유지
- **경로 4 (예외)**: 옵션 6 대기 중 예외 시 기존 fallback으로 흐름

---

## 10. 범위 외 후속 항목

- **AUTO-RESUME 서비스 분리 (근본 해결)**: 별도 WO. 트레이딩 엔진을 Streamlit UI에서 분리한 독립 systemd 서비스로 이관.
- **1분 미만 정밀도 안정화 시간 측정**: 조건 3 데이터 한계. WO-2 옵션 6 채택으로 T값 결정 불필요해져 우선순위 낮음.
- **매도 필터 tick 기반 이동**: 현재는 봉 확정 기준. tick 기반이면 반응성 극대화 (별도 WO 후보).
- **[POLLUTED] 자동 해제**: WARMUP 자동 재시드. 별도 WO.
- **저volume 봉 처리 정책 명문화**: 현재 REST 부재 → 처리 안 함. 명시적 정책 문서 필요.

---

## 부록 A. 옵션 4·5 기각 사유

### 옵션 4 (T=30s + N=2, 10s 간격)
- 옵션 6 대비 평균 지연 6배 이상 (30s vs 5s)
- 매도 필터 반응성 열세
- T값이 상수 하드코딩 (조건 3 데이터 한계로 정밀 값 산정 어려움)
- 옵션 6이 결정적 판정으로 대체 가능

### 옵션 5 (초안 정의)
- 초안의 "진행 중 봉 미반환" 서술이 재실측(H-R1)으로 반증됨
- 재정의된 옵션 5는 사실상 옵션 6과 동일 (옵션 6로 통합)

---

## 부록 B. 조사에 사용된 인용 원본

- 24h 실측: `journalctl -u tradebot --since '2026-08-22 11:16:42' --until '2026-08-23 11:16:42'` + `sqlite3 tradebot_mcmax33.db`
- R1 재실측: `/tmp/wo2_reprobe.log` (서버, 2026-08-23 16:19~16:27)
- R2 시드 민감도: Python 재계산 (alpha_f=2/21, alpha_s=2/201)
- R4 AUTO-RESUME 코드 인용: `pages/dashboard.py:389`, `engine/engine_manager.py:88-113, 115-147, 295-310`
- 소스: `core/rest_reconcile.py:434-624`, `engine/live_loop.py:914-1180`, `core/strategy_incremental.py:376, 1080`, `core/filters/sell_filters.py:48, 156, 257`

---

**작성 완료 일시**: 2026-08-23 (KST)
**개정판 상태**: R1~R4 반영 완료. 검토 대기.
**다음 단계**: (a) 사용자 검토 → (b) 구현 착수 승인 → (c) 배포 (별도 승인)
