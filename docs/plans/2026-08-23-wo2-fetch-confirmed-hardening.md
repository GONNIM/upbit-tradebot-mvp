# WO-2 설계안 (개정 2.1판) — fetch_confirmed_candle 오프바이원 교정 + 옵션 7 (혼합)

**날짜**: 2026-08-23
**작성자**: Claude Code
**개정 사유**: 개정 2판의 D2 분류 (오프바이원 = 별개 결함) 기각. C1~C5 반영으로 오프바이원을 WO-2 필수 범위로 편입. D3 재실측(candles API, 24h+ 1600봉).
**상태**: **개정 2.1판 · 검토 대기 (구현 착수 금지)**

---

## 🎯 핵심 요약 (2줄, 재재재선정)

> **1차 배포 100% fallback의 1차 원인은 오프바이원 (봇 CLOCK-CLOSE 시각 = 진행 중 봉 시작 시각을 확정 봉 라벨로 사용)**. `has_next = ts > closed_ts` 가 실질적으로 "다음다음 봉 존재"가 되어 매 봉 60s+ 대기 → 관측된 5/5 fallback + CRITICAL. D3 재실측 시 JTO 다음 봉 존재율 72.5% (v1 fallback률 27.5%)가 오프바이원과 결합해 100%로 증폭.
> **옵션 7 (혼합) + v2 경계 라벨 교정**: v2 입구에서 `upbit_ts = closed_ts − interval_sec` 변환 (봇 라벨 → Upbit 라벨). Fast path (활성 종목 즉시) + Slow path (완결된 T-1의 close 안정화 2회 일치, 저유동성 커버). 저유동성 실환경 + 라벨 검증 케이스 L 스모크 통과 전 배포 금지.

---

## 📋 목차

1. [1차 배포 실패 타임라인 + 라벨 교정 시 재기술 (C1)](#1-1차-배포-실패-타임라인--라벨-교정-시-재기술)
2. [D1~D3 진단 결과 (D2 정정 C2, D3 재실측 C3)](#2-d1d3-진단-결과)
3. [1차 설계 오류 분석](#3-1차-설계-오류-분석)
4. [오프바이원 v2 경계 교정 스펙 (C1)](#4-오프바이원-v2-경계-교정-스펙)
5. [옵션 7 (혼합) + 라벨 교정 재설계](#5-옵션-7-혼합--라벨-교정-재설계)
6. [옵션 6 단독 (1차) vs 옵션 7 + 교정 (2.1판) 비교](#6-옵션-6-단독-vs-옵션-7--교정-비교)
7. [스모크 계획 + 라벨 검증 케이스 L (C4)](#7-스모크-계획--라벨-검증-케이스-l)
8. [배포 계획 · 리허설 갱신](#8-배포-계획--리허설-갱신)
9. [문서 정합 (C5)](#9-문서-정합-c5)
10. [범위 외 후속 항목 (WO-6 등)](#10-범위-외-후속-항목)

---

## 1. 1차 배포 실패 타임라인 + 라벨 교정 시 재기술

### 1.1 관측 타임라인 (KST)

| 시각 | 이벤트 |
|---|---|
| 17:17:57 | systemd active |
| 17:19:25 | 🚀 CLOCK-LOOP 시작 |
| **17:20:35** | 첫 fallback (1/5) — 17:20 봉 |
| 17:21:36 | fallback (2/5) |
| 17:22:36 | fallback (3/5) — **17:22 봉 (D1: 체결 7건)** |
| 17:23:36 | fallback (4/5) |
| 17:24:36 | 🚨 CRITICAL (5회 임계) — **17:24 봉 (D1: 체결 7건)** |
| 17:25~17:29 | fallback (6~10회 연속) |
| 17:31:36 | 롤백 restart |
| 17:33:45 | 구 경로 [CONFIRMED] retry=2 재개 ✅ |

### 1.2 라벨 교정 시 재기술 (C1 근거)

**교정 전 (관측)**:
| 봉 (봇 라벨) | 봇 판정 `closed_ts` | 실제 완결된 봉 | `has_next` 대상 봉 | 다음 봉 상태 | 결과 |
|---|---|---|---|---|---|
| 17:20 | 17:20:00 (진행 중) | **17:19** (완결) | **17:21** (다음다음!) | 무거래 (D1) | fallback |
| 17:22 | 17:22:00 (진행 중) | 17:21 (완결) | **17:23** | 무거래 | fallback (체결 있는데도 실패) |
| 17:24 | 17:24:00 (진행 중) | 17:23 (완결) | **17:25** | 무거래 | CRITICAL |

**교정 후 (재기술, A3 반영)**:
| 봉 (봇 라벨) | v3 변환 `upbit_ts` | `has_upbit_T` | `has_next` (봇 라벨 존재) | 결과 |
|---|---|---|---|---|
| 17:20 | 17:19 (무거래) | false | 17:20 진행 중 (봇 라벨), 첫 체결 없음 → false | **NO-DATA 무해 fallback** (T-1·후속 모두 무거래, CRITICAL 미가산) |
| 17:21 | 17:20 (무거래) | false | 17:21 진행 중, 무거래 → false | NO-DATA 무해 |
| 17:22 | 17:21 (무거래) | false | 17:22 진행 중, 곧 체결 → **true (첫 체결 시)** | **I2 즉시 단락** (T-1 무거래) |
| **17:23** | **17:22 (체결 7건)** | **true** | 17:23 진행 중, 무거래 → false | **SLOW path 진입 → close 안정화 2회 일치 → 확정** ⭐ 교정 효과 |
| 17:24 | 17:23 (무거래) | false | 17:24 진행 중, 곧 체결 → true (첫 체결 시) | I2 단락 |
| **17:25** | **17:24 (체결 7건)** | **true** | 17:25 진행 중, 무거래 → false | **SLOW path → 확정** ⭐ |
| 17:26~29 | 17:25~28 (무거래) | false | 후속 무거래 → false | NO-DATA 무해 |

**결과 (정정)**:
- **유해 fallback 소멸** (has_T=true였는데 확정 실패한 봉 = 0건 예상 · CRITICAL 미발동)
- 17:22 체결 데이터는 **17:23봉 처리 시** `has_upbit_T=true` 로 등장하여 **SLOW path 로 확정 반환** (교정의 핵심 효과)
- **무해 fallback(NO-DATA)은 잔존** — JTO 저유동성 시간대 정상 동작. CRITICAL 카운터 무관.

---

## 2. D1~D3 진단 결과

### 2.1 D1 — 17:20~17:29 KRW-JTO ticks 체결 건수

| 분 | 체결 |
|---|---|
| 17:19 | 0 |
| 17:20 | 0 |
| 17:21 | 0 |
| **17:22** | **7** |
| 17:23 | 0 |
| **17:24** | **7** |
| 17:25~29 | 0 |

### 2.2 D2 — 오프바이원 (C2 정정: "본질적 원인 아님" 삭제)

**결함 위치**: `core/candle_clock.py:82 get_closed_ts`
```python
def get_closed_ts(self, now: datetime) -> datetime:
    """방금 확정된 봉의 timestamp ... 확정된 봉의 시작 시각 (UTC)"""
    # Example: now=09:05:42 → returns 09:05:00
```

- 실제 정확한 해석: 09:05:42 시점에는 **09:04 봉이 방금 확정**됨 (09:04:00~09:04:59). `get_closed_ts`는 09:05:00 반환 → **진행 중 09:05 봉 시작 시각을 확정 봉 라벨로 반환**.

**실패 구조 (C2 재기술 — 2층 구조)**:

- **1층 (오프바이원, WO-2에서 수정)**:
  - closed_ts가 진행 중 봉 라벨이라 `has_next = ts > closed_ts`가 실질적으로 "**다음다음 봉 존재**" 조건이 됨
  - 즉 봇 시각 17:20 → `closed_ts=17:20` → has_next는 17:21 봉 (진행 중 or 확정) 존재 여부
  - **관측 ~100% 실패의 1차 원인**. 무거래 봉 여러 개 겹치면 계속 fallback
- **2층 (유동성, 옵션 7 SLOW path 로 해소)**:
  - 오프바이원 교정 후에도 저유동성 종목은 fast path에서 다음 봉 등장 지연
  - D3 candles: JTO 다음 봉 존재율 72.5% → **잔여 27.5%가 SLOW path 대상**
  - SLOW path (close 안정화 2회 일치, 20s) 로 흡수 → 실 fallback률 근사 0%

**기존 시스템이 정상 작동한 이유**:
- Progressive Retry (`fetch_confirmed_candle:515`) 는 `latest_ts == closed_ts` 매칭으로 확정 판정
- Upbit REST 지연 후 진행 중 봉이 등장 → 매칭 성공 → 봇이 그 값을 "확정"으로 사용
- **하지만 반환값은 진행 중 봉의 close** → **이게 Issue #8/F5의 본질** (미확정 종가가 아니라 진행 중 봉을 확정으로 잘못 라벨링)

**배포 중 데이터 오염**: CONFIRMED-D via=next_bar_exists 성공 로그 = **0건** → 진행 중 봉 데이터가 실시간 처리로 흐르지 않음. BACKFILL fallback + WO-1 옵션 B 안전판이 오염 차단.

### 2.3 D3 재실측 (C3, candles/minutes/1 API, 24h+, JTO+RE 각 1600봉)

**측정 방법**: candles API 로 24h+ 분봉 수집 → 활성/무거래 분류 → 다음 봉 존재율 산출. (**ticks API `to` 파라미터는 `HH:mm:ss` 형식만 유효, 페이지네이션 불가로 candles로 대체**).

| 종목 | 수집 봉 | 다음 봉(T+1) 존재율 | **v1 fallback률 근사** | 무거래 gap max |
|---|---|---|---|---|
| **KRW-JTO** | 1600 (~27h) | 72.5% | **27.5%** | **26분** |
| **KRW-RE** | 1600 | 93.6% | 6.4% | 8분 |

**⚠️ 데이터 한계 (C3 명시)**:
- 지표 재정의: "봉 T (체결 존재) 종료 → 다음 분 T+1 첫 체결까지 지연" = fast path 대기 시간. **candles API는 이 지연을 초 단위로 측정 불가** (분 단위 존재 여부만). 정확한 지연 분포는 프로덕션 배포 후 실측이 유일.
- 옵션 7 fast path 실패율 근사는 "다음 봉 존재율" 로 상한.

**갱신된 옵션 7 예상 지표 (A2 정정 — 유해/무거래 skip 분리)**:
- **유해 fallback률** (체결 있는 봉 중 확정 실패) — **목표 0%** (양쪽 종목)
- **무거래 skip률** (I2 NO-TRADE-BAR + NO-DATA 무해 fallback) — 목표치 없음. **JTO ~27.5% 수준은 정상** (D3 다음 봉 존재율 72.5% 의 여집합, 시장 특성)
- KRW-RE 무거래 skip: ~6.4% 수준 정상

**JTO 무거래 gap max 26분**: 극단 저유동성 시간대. 이 시간대는 어차피 매매 신호 자체가 드묾. 매매 판정 왜곡보다는 매매 기회 자체가 부재.

---

## 3. 1차 설계 오류 분석

### 3.1 재실측(H-R1) 해석 편향
- P1 (KRW-BTC 활성)에 편향 → "옵션 6 결정적 성립" 결론
- P2/P4의 저유동성/무거래 케이스를 반증으로 인식 실패

### 3.2 오프바이원 미인식
- WO-2 개정 1판/2판 모두 `closed_ts` 를 "정확한 확정 봉 라벨"로 가정
- Progressive Retry가 매칭으로 우연히 회피하는 구조를 놓침
- **C1이 지적한 대로 이것이 WO-2 필수 범위**임을 인정. 별도 결함으로 이관은 잘못된 분류.

### 3.3 스모크 결함 (C4 근거)
- 로컬 스모크 A (실 API): KRW-BTC 이전 봉 사용. 하네스가 `prev_bar = now - 1min` 로 `closed_ts` 를 계산 → **이때 로컬 계산 라벨과 v2 내부 판정이 우연히 일치** (봇의 오프바이원 로직 미경유). 즉 스모크 A는 라벨 오프바이원 결함을 검증 대상으로 삼지 않음.
- BTC 는 활성 종목이라 다음 봉이 즉시 등장 → 우연히 성공.
- **JTO 저유동성 + 봇 라벨 오프바이원** 조합이 배포 첫 실전에서 즉시 폭발.

### 3.4 D3 미실시
- ticks 지연 분포를 배포 전에 측정했다면 JTO fallback률 즉시 파악 가능.

---

## 4. 오프바이원 v2 경계 교정 스펙 (C1)

### 4.1 변환 매핑 표

| 봇 라벨 (`closed_ts`) | Upbit 라벨 (REST index) | 실제 봉 구간 (KST, 1분봉) | 봇 시각 (`now`) | 상태 |
|---|---|---|---|---|
| 17:20:00 | **17:19:00** | 17:19:00 ~ 17:19:59 | 17:20:00 정각 | 방금 확정 (봇이 감지하려는 봉) |
| 17:20:00 (기존 v2 오해) | 17:20:00 | 17:20:00 ~ 17:20:59 | 17:20:00 정각 | 진행 중 (오프바이원 결과) |
| 17:21:00 | **17:20:00** | 17:20:00 ~ 17:20:59 | 17:21:00 정각 | 방금 확정 (봇이 감지하려는 봉) |

### 4.2 구현 스펙

**v2 함수 입구에서 라벨 변환 (v2 경계 국한)**:

```python
def fetch_confirmed_candle_v3(closed_ts, timeframe):  # closed_ts = 봇 라벨
    interval_sec = TIMEFRAME_SEC[timeframe]  # e.g., 60
    upbit_ts = closed_ts - timedelta(seconds=interval_sec)  # ★ 라벨 교정
    # 이후 모든 판정은 upbit_ts 기준 (Upbit index 매칭용)

    df = pyupbit.get_ohlcv(count=3)
    has_upbit_T = upbit_ts in df.index  # 완결된 봉 존재
    has_next    = closed_ts in df.index  # 봇 라벨 봉 = Upbit의 다음 봉 (진행 중 or 확정)

    # ─── FAST PATH ───
    if has_upbit_T and has_next:
        row = df.loc[upbit_ts].copy()
        row.name = closed_ts  # ★ 봇 라벨로 복원해 반환
        logger.info(f"✅ [CONFIRMED-D-FAST] ts={format_kst(closed_ts)} "
                    f"upbit_ts={format_kst(upbit_ts)} via=next_bar_exists ...")
        return row

    # ─── I2 즉시 단락 ───
    if has_next and not has_upbit_T:
        # upbit_ts (완결된 봉) 이 REST 부재 = 무거래 봉
        logger.info(f"⏭ [NO-TRADE-BAR] upbit_ts={format_kst(upbit_ts)} (봇 라벨={format_kst(closed_ts)}) 무거래")
        return None

    # ─── SLOW PATH (has_next=False) ───
    if has_upbit_T:
        prev_close = df.loc[upbit_ts]['Close']
        for slow_i in range(4):  # 5s×4 = 20s
            time.sleep(5)
            df2 = pyupbit.get_ohlcv(count=3)
            if upbit_ts in df2.index and df2.loc[upbit_ts]['Close'] == prev_close:
                row = df2.loc[upbit_ts].copy(); row.name = closed_ts
                logger.info(f"✅ [CONFIRMED-D-SLOW] ts={format_kst(closed_ts)} "
                            f"upbit_ts={format_kst(upbit_ts)} via=close_stable_2consec ...")
                return row
            if upbit_ts in df2.index:
                prev_close = df2.loc[upbit_ts]['Close']
    # 최종: 상한 도달 → BACKFILL fallback
    return None
```

**변환 국한**: v2 함수 입구/출구에서만 변환. 파이프라인 전역의 `closed_ts` 라벨링 (candle_clock.py, live_loop.py, audit 기록 등) 은 **WO-6에서 별도 개편** (전역 영향 큼).

### 4.3 SLOW path 재기술 (C1 요구)

**교정 후 SLOW path 의미**: "**완결된 직전 봉 T-1(upbit_ts)의 REST 재확인**". T-1은 이미 종료된 봉이므로 close 값이 시간 경과에 따라 안정화됨. 2회 연속 조회 일치 = 확정.

**⚠️ 경고 (C1 명시)**:
> **교정 없이 SLOW path 를 붙이면 F5 재생산**. 오프바이원 있는 상태로 close 안정화 검증하면 진행 중 봉의 close 를 안정화된 값으로 오판 → 매매 판정을 진행 중 봉 값으로 실행하는 위험. **교정과 SLOW path는 반드시 함께 도입**.

### 4.5 P0 옵션 A — v3 None 시 호출측 즉시 스킵 (F5 뒷문 봉쇄)

**배경 (2026-08-23 P0 정적 확인)**: v3 자체는 확정 판정을 정확히 하지만, 호출측 (`live_loop.py:983-984`) 에서 v3 None 시 `logger.error("Reconcile 계속 (미확정 종가 사용 가능)")` 만 찍고 흐름 계속 → `rest_df` (별도 `safe_fetch_rest` 결과, 미확정 종가 포함) 가 그대로 `reconcile_series` → `local_series` → 라인 1217 → `Bar(is_confirmed=True, source="REST_RECONCILED")` → 매매 판정 실행. **이 경로는 v3 뒷문이 아니라 현행 프로덕션 F5 본체 경로였음**. 1차 배포가 우연히 안전했던 것은 오프바이원 상태에서 봇 라벨이 rest_df에도 없어 라인 1217 False로 흐른 것이며 데이터 오염 0건도 우연이었다.

**옵션 A 스펙**:
```python
elif confirmed_row is None:
    logger.info("⏸ [SKIP-BAR] ts=... v3 미확정 → 봉 처리 보류 (차기 reconcile/BACKFILL 위임, F5 뒷문 봉쇄)")
    time.sleep(1)
    continue
```

**스킵 의미론 명문화**:
- 스킵된 봉의 close 값은 **실시간 지표(EMA/MACD) 스트림에 미반영**됨.
- 다만 다음 iteration REST-RECONCILE 이 이 봉을 `changed_ts` 로 감지 → BACKFILL 경로 진입 → 지표 재계산 및 audit 기록. **WO-1 Issue #11 백업/복원 정책으로 지표는 원복되므로 실시간 스트림 오염 없음**.
- v3 정상 작동 시 유해 fallback 목표 0%이므로 실질 스킵은 **무거래·I2 케이스에 국한** (원래도 close 기여 없는 봉). 활성 봉은 FAST/SLOW 로 확정 → 정상 처리.

**V1 부수 효과 확인 결과** (라인 인용):
- 스킵되는 코드 (라인 987 reconcile → 1256 실시간 처리) 모두 안전
- LIMIT pending 타임아웃·알림·포지션 동기화는 별도 스레드에서 처리 → 이 iteration 무관
- `engine.last_bar_ts` 미갱신은 다음 봉 처리에 무영향 (closed_ts=T+1 > last_bar_ts=T-1 조건 만족)
- `time.sleep(1)` 은 continue 앞에 명시 (라인 1328 sleep 이 건너뛰어짐, CPU 스핀 방지)

### 4.4 무해/유해 fallback 분류 (A1 필수)

**목적**: D3 실측 "JTO 무거래 gap 최대 26분" 시나리오에서 CRITICAL 오경보 방지. 알림 신뢰 유지.

**분류 스펙** (v3 함수 내부 tracking):
- 각 iteration 에서 `has_upbit_T`, `has_next` 값 관찰
- 두 플래그 (`had_upbit_T_ever`, `had_next_ever`) 로 이력 트래킹
- 상한 30s 도달 시 최종 분류:

| 조건 | 분류 | 로그 | CRITICAL 카운터 |
|---|---|---|---|
| `had_upbit_T_ever=false` AND `had_next_ever=false` | **NO-DATA 무해** | `⏸ [NO-DATA] upbit_ts=... (봇 라벨=...) 대상·후속 봉 모두 무거래` | **미가산** |
| `had_upbit_T_ever=true` 인 순간 존재 | **유해 fallback** | `[CONFIRMED-D] 확정 실패 (FAST·SLOW 모두 불발) upbit_ts=...` | **가산** (연속 5회 시 CRITICAL notify) |
| `has_next AND NOT has_upbit_T` (첫 iteration 즉시) | **I2 (NO-TRADE-BAR)** | `⏭ [NO-TRADE-BAR] upbit_ts=... 무거래` | **미가산** (기존과 동일) |

**함의**:
- 저유동성 정체 시간대는 NO-DATA 로 조용히 흐르고, 진짜 시스템 이슈 (has_T=true인데 확정 실패) 만 CRITICAL 발동.
- JTO 무거래 26분 gap 케이스: 26봉 연속 NO-DATA 발생하지만 CRITICAL 무발동. 정상.

---

## 5. 옵션 7 (혼합) + 라벨 교정 재설계

### 5.1 정책 요약

- **활성 종목 (RE류)**: FAST path 즉시 성공 (다음 봉 존재율 93.6%). 지연 ≤ 5s.
- **저유동성 종목 (JTO류)**: FAST path 실패 시 SLOW path 진입 (완결된 T-1의 close 안정화). ~10~20s.
- **완전 무거래 봉 (I2)**: `has_next AND NOT has_upbit_T` → 즉시 단락.
- **극단 저유동성 (SLOW 실패)**: 30s 상한 → BACKFILL fallback (기존 정책).

### 5.2 예상 지연 프로파일

| 종목 | 시나리오 | Path | 예상 지연 |
|---|---|---|---|
| KRW-RE (활성) | 항상 | FAST | 0.1~5s |
| KRW-JTO (활성 시간대) | 다음 봉 첫 거래 즉시 | FAST | 0.1~5s |
| KRW-JTO (다음 봉 무거래 짧게) | I2 즉시 | 단락 | 0s (매매 판정 없음) |
| KRW-JTO (다음 봉 무거래 → 완결된 T-1 안정화) | SLOW | ~10~20s |
| KRW-JTO (극단 저유동성 26분 gap) | fallback | 30s → BACKFILL |

### 5.3 예상 지표 (D3 갱신, A2 분리)

- **유해 fallback률** (체결 있는 봉 중 has_upbit_T=true 인 상태로 SLOW 도 실패): **목표 0%** (JTO/RE 양쪽). 유해 fallback 발생 시 CRITICAL 발동 조건 유지.
- **무거래 skip률** (I2 + NO-DATA): JTO ~27.5%, RE ~6.4% 수준 **정상 동작**. CRITICAL 무관.
- **정확한 실측은 저유동성 실환경 스모크 + 소규모 배포 후 24h 관측으로만 검증 가능**.

---

## 6. 옵션 6 단독 vs 옵션 7 + 교정 비교

| 항목 | 옵션 6 단독 (1차 실패) | **옵션 7 + 라벨 교정 (2.1판)** |
|---|---|---|
| 라벨 처리 | 오프바이원 노출 | **v2 입구 upbit_ts 변환** |
| has_next 조건 | 다음다음 봉 (증폭 원인) | **다음 봉 (봇 라벨 = Upbit의 다음)** |
| 평균 지연 (활성) | 5~30s | **0.1~5s** |
| 평균 지연 (저유동성 T+1 무거래) | 30s → fallback | **10~20s SLOW 성공** |
| I2 무거래 봉 | (라벨 혼동으로 오판 가능) | **명확 (upbit_ts 부재)** |
| JTO 실전 결과 | **100% fallback (전부 CRITICAL 유발)** | **유해 fallback 예상 0%** (무거래 skip ~27.5%는 정상 동작, CRITICAL 무관) |
| 매도 반응성 | 저유동성 30s+ | 저유동성 10~20s |
| SLOW path 안전성 | (해당 없음) | **교정 필수** (교정 없으면 F5 재생산) |
| 저유동성 스모크 | (부재로 실패) | **필수 (§7 케이스 L 추가)** |

---

## 7. 스모크 계획 + 라벨 검증 케이스 L (C4)

### 7.1 스모크 프로토콜 갱신

**기존 (개정 1판)**:
- A: 실 API 즉시 확정 (KRW-BTC) — **하네스 라벨 주입으로 결함 은폐 사례 확인**
- B/C/D: mock

**개정 2.1판 필수 추가**:

**케이스 L (라벨 검증, 신규 필수)**:
- v2 함수에 **봇의 실 `get_closed_ts()` 로 계산한 `closed_ts`** 를 넣고 실행
- 반환 bar 의 `close` 값을 **해당 upbit_ts 분의 ticks API 마지막 체결가**와 대조
- **JTO 실환경 1봉 + BTC 1봉 (활성)** 최소 각 1건
- 불일치 시 **구현 불합격** (라벨 교정 결함)

**케이스 M (JTO 저유동성 실환경, 신규 필수)**:
- 활성 시간대 3봉 + 저유동성 시간대 3봉 = 최소 6봉
- FAST/SLOW/I2/fallback 각 최소 1건 관찰
- fallback률이 D3 예측 (JTO ~0%) 범위 검증

**케이스 F/G (SLOW path mock)**:
- F: close 안정화 2회 일치 → SLOW 성공
- G: close 계속 변동 → SLOW 실패 → 상한 fallback

### 7.2 하네스 라벨 주입 결함 (스모크 A 사후 분석)

**A의 문제**: 
```python
now = datetime.now(timezone.utc)
prev_bar = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
r = fetch_confirmed_candle_v2('KRW-BTC', 'minute1', prev_bar)  # ★ 하네스가 로컬 계산
```
- `prev_bar` = 1분 전 정각 = Upbit 실제 확정 봉의 라벨 (이 경우 우연히 봇 오프바이원 로직 미경유)
- v2가 `closed_ts=prev_bar` 를 Upbit index와 매칭 → 성공
- **봇 실전에서는 `clock.get_closed_ts()` 결과 (진행 중 봉 라벨) 전달** → v2 오프바이원 노출
- 즉 스모크 A는 라벨 결함을 은폐. **케이스 L 필수화로 봉쇄**.

---

## 8. 배포 계획 · 리허설 갱신

### 8.1 옵션 7 배포 전 필수 검증
- ✅ D3 재실측 (candles 24h+ 1600봉 × JTO/RE) 완료 (§2.3)
- 케이스 L 통과 (라벨 교정 검증)
- 케이스 M 통과 (JTO 저유동성 실환경)
- 로컬 스모크 F/G (SLOW path mock)

### 8.2 배포 절차 (WO-2 1차 준용, 차이점만)
- 커밋 파일: `core/rest_reconcile.py` (v3 신설) + `engine/live_loop.py` (v3 호출 교체) + `pages/dashboard.py` 버전 갱신 + `scripts/migrate_all_users.py` + `docs/operations/deploy-checklist.md` (§9 항목 추가) + 개정 2.1판 자체
- Unit: ExecStartPre 재추가 (1차 배포에서 성공한 부분, 롤백으로 제거됨)
- 배포 확인 5건 + `[CONFIRMED-D-FAST]` 와 `[CONFIRMED-D-SLOW]` 둘 다 등장 확인

### 8.3 롤백 조건 강화 (2.1판)
기존:
- (c) 30분 내 CONFIRMED-D 미등장 + BACKFILL 급증

추가:
- (f) **배포 후 30분 내 유해 fallback 1건이라도 발생 시 즉시 롤백** (A1 목표 0% 위반) — 사용자 지시
- (g) SLOW path 진입 로그가 5봉 연속 상한(20s) 초과 시 롤백
- (h) **라벨 결함 재발 시** (예: NO-DATA/유해 분류가 예상과 크게 다름, has_upbit_T tracking 결함 의심) 즉시 롤백 + WO-6 착수 검토
- (i) **CRITICAL 알림이 배포 후 30분 내 발동 시** 즉시 롤백 (연속 5회 유해 fallback 판정)

---

## 9. 문서 정합 (C5)

- **`core/candle_clock.py:82 get_closed_ts` docstring 오류**: WO-2에서 **수정하지 않음** (전역 영향). 대신 결함 주석 추가:
  ```python
  def get_closed_ts(self, now: datetime) -> datetime:
      """
      ⚠️ [DOCSTRING BUG · WO-6 후보] docstring/example 이 "방금 확정된 봉의 시작 시각"
      이라 주장하지만 실제 반환값은 진행 중 봉의 시작 시각 (오프바이원). 파이프라인의
      다른 코드는 이 관행에 맞춰 작성됨. WO-2 (rest_reconcile.py v3) 는 함수 경계에서
      upbit_ts = closed_ts − interval_sec 변환으로 국지 보정. 전역 개편은 WO-6.
      ...
      """
  ```
- **`docs/operations/deploy-checklist.md` 신규 항목** (§9.1):
  > 신규 확정 판정 로직은 저유동성 실환경 스모크 (케이스 L + M, WO-2 §7) 통과 전 배포 금지. 하네스 라벨 주입 스모크만으로는 라벨 결함을 검증 불가 (2026-08-23 WO-2 1차 배포 실패 사례).
- **커밋**: 2.1판 승인 시 위 결함 주석 + deploy-checklist 신규 항목 + v3 코드 + 스크립트 + 개정 2.1판 자체를 **일괄 커밋**.

---

## 10. 범위 외 후속 항목

- **WO-6 (파이프라인 전역 라벨 개편)**: `get_closed_ts` 오프바이원을 근본 수정. `closed_ts` 를 완결된 봉 라벨 (T-1) 로 반환하도록 변경 + 전역 사용처(live_loop, audit, invariant 등) 동시 수정. 전역 영향 큼 → 별도 WO. WO-2 배포 후 24h 실측 안정성 확인 후 착수.
- **WO-5 (서비스 분리)**: AUTO-RESUME 51분 공백 근본 해결. 24h 실측 후 착수.
- **ticks API `to` 파라미터 문서 조사**: `HH:mm:ss` 형식 한계로 페이지네이션 불가. Upbit API 문서 정독 or POST 방식 검토 (D3 정밀 지연 측정 필요 시).

---

## 부록 A. 1차 배포 산출물

### 사용 안 함 (되돌림)
- `core/rest_reconcile.py:597 fetch_confirmed_candle_v2` (1차) — v3 재작성 시 대체
- `pages/dashboard.py:313 v1.2026.08.23.1713` → 롤백으로 v1.2026.08.22.1002

### 재사용 예정 (2.1판 배포 시)
- `scripts/migrate_all_users.py` — 로컬 커밋에 있음, 서버 롤백으로 제거됨. 2.1판 배포 시 동시 반영.
- unit 백업 `override.conf.bak-wo2-20260823` — 이번 롤백에서 복원용으로 사용, 유지.

---

## 부록 B. D1~D3 인용 원본

- **D1** (17:19~17:29 KRW-JTO ticks): 원문 §2.1 표
- **D2** (오프바이원 감사): `core/candle_clock.py:82`, `core/rest_reconcile.py:515` 라인 인용 §2.2
- **D3** (지연 분포, candles API): 최근 1600봉 × JTO+RE — 원문 §2.3. ticks API `to` 파라미터 한계로 candles 로 대체 (분 단위 존재율 근사).

---

**작성 완료 일시**: 2026-08-23 (KST)
**개정 2.1판 상태**: C1~C5 반영 완료. 구현 착수 금지. 검토 대기.
**다음 단계**: (a) 사용자 검토 → (b) 구현 승인 → (c) 케이스 L/M 스모크 통과 → (d) 배포 (별도 승인)
