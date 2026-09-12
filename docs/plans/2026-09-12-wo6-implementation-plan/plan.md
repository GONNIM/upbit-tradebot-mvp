# WO-6 구현 계획서 → 현실 대조표 (2026-09-12 재분류)

**완결 (2026-09-12): 실시간 판정 커버리지 100% (v3 시기 8.3% 대비), 부재 봉 0, 고아 봉 0.** 근거: `docs/plans/2026-09-12-post-check/coverage-and-critical.md`.

**본 문서는 2026-09-12 오전 "구현 지시"로 승인됐으나, 착수 직전 사실 확인 과정에서 §1.1 필수 목록 대부분이 이미 배포 반영된 상태임이 확인됐다. 따라서 문서 지위를 "구현 지시" → "현실 대조표"로 전환한다.**

**서버 실측 결과 (2026-09-12 SSH)**:
- 서버 HEAD: `53fdbf3` (2026-09-04)
- 엔진 기동 시각: 2026-09-04 19:43:56 KST (8일+ 무중단)
- `[SKIP-BAR]` 로그 2026-08-29 이후 0건 (WO-6 안착 확증)
- 대시보드 버전: `v1.2026.09.04.1931`
- 최근 7일 실측: 봉당 1회 원칙 위반 0건, 매매 사고 0건, POLLUTED 0건

**따라서 이 문서의 §1~§4는 "이미 반영된 상태의 사후 대조"로 읽는다. 미반영 항목은 §1.3에 별도 정리. 최종 판정 결과에 따라 별도 문서(예: `docs/plans/2026-09-12-post-check/`)로 이동될 수 있다.**

**근거 문서**: `docs/plans/2026-08-25-wo6-label-unification-and-invariant.md` (설계 문서 4판)
**조사 근거**: `docs/plans/2026-09-12-fv1-fv3-and-v-a-v-b-investigation/report.md` (FV1~FV3 + V-A/V-B 실측)

---

## 0. 개요

WO-6은 두 근본 결함을 함께 해소한다.

1. **시각 표기 통일**: `candle_clock.get_closed_ts` 오프바이원 + `closed_ts`/`upbit_ts` 라벨 이중화 봉쇄.
2. **봉당 매매 판단 1회 강제**: `[SKIP-BAR]` 제거 + `_evaluated_bar_ts` 관문 도입 + 지표 갱신·매매 판단 경로 분리.

**F5(fetch_confirmed_candle 3케이스 재배치, 무거래 봉 NO_TRADE 센티널)**의 이번 라운드 포함 여부는 §2에서 찬반 근거를 정리하고 사용자 판정에 위임한다.

WO-2 재적용(대기 큐·유효성 확인·발주 지연 상한)은 WO-6 안착 후 별도 라운드.

---

## 1. 현실 대조표

### 1.1 확정판 §1.1 vs 서버 실측 (2026-09-12)

**모든 §1.1 필수 항목은 이미 배포 반영. 각 항목에 반영 커밋 해시를 매핑한다.**

| 파일 | 함수·라인 | 계획된 변경 | 반영 커밋 | 실측 상태 |
|---|---|---|---|---|
| `core/candle_clock.py` | `get_closed_ts` (line 82) | 반환값 `floor(now)` → `floor(now) - timedelta(interval_sec)` | **`bc582a6`** (2026-08-29 19:28) | ✅ 반영 · line 105-106 확인: `boundary - timedelta(seconds=self.interval_sec)` |
| `core/candle_clock.py` | 라벨 의미 통일 (line 99, 102, 144) | 주석·로그 정정 | **`bc582a6`** | ✅ 반영 · docstring line 84-91에 WO-6 개편 명시 |
| `engine/live_loop.py` | `upbit_ts` 별도 변수 삭제 | v3 잔재 삭제 | **`bc582a6`** | ✅ 반영 · grep 결과 `upbit_ts` 0건 |
| `engine/live_loop.py` | line 983~996 `[SKIP-BAR]` 제거 | 블록 통째 제거 | **`bc582a6`** | ✅ 반영 · 로그 2026-08-29 이후 [SKIP-BAR] 0건 |
| `core/strategy_engine.py` | `_evaluated_bar_ts` OrderedDict 신설 | 자료구조 신설 | **`bc582a6`** | ✅ 반영 · line 96 확인 |
| `core/strategy_engine.py` | 봉당 1회 관문 (on_bar 호출 직전) | 검사 로직 추가 | **`bc582a6`** | ✅ 반영 · line 676 확인 |
| `core/strategy_engine.py` | `_evaluated_bar_ts_register` 메서드 | popitem(last=False)로 상한 관리 | **`bc582a6`** | ✅ 반영 · line 760-762 확인 |
| `core/strategy_engine.py` | 부분 재계산 지표·판정 분리 | on_bar 관문 통과 필요 | **`bc582a6`** | ✅ 반영 |
| `core/strategy_engine.py` | last_bar_ts 갱신 위치 hotfix | 안착 판정 정정 | **`5ab50cf`** (2026-08-30 16:34) | ✅ 반영 · dashboard `v1.2026.08.30.1633` 배포 |
| `core/candle_buffer.py` | 봉 시각 통일 반영 (코드 무변경) | — | **`bc582a6`** | ✅ 확인 · 관련 조사 시 grep 무변경 |
| `core/rest_reconcile.py` | closed_ts 파라미터 의미 재정의 | 라벨 통일 | **`bc582a6`** | ✅ 반영 (F5 케이스 재배치는 §2 미포함) |

### 1.2 F5 (§3.5) — **이번 라운드 미포함 확정**

WO-2 재적용 라운드로 이관. 다음 항목은 이번 라운드 대상 아님:
- `fetch_confirmed_candle` 케이스 순서 A → C → B 재배치
- `NO_TRADE` 센티널 신설
- 케이스 B 5초 안정화 1회
- `_case_b_state_gc`

### 1.3 미반영 항목 (잔여 작업)

| 항목 | 배포 상태 | 우선순위 |
|---|---|---|
| **dry-run 플래그 신설** | 미반영 | **재평가 필요 (§8 참고)** — WO-6이 이미 8일+ 실측 통과 상태이므로 병행 실행 검증 요구가 소멸. dry-run 필요성은 향후 WO-8 지정가 이식 검증 시 재평가 |

### 1.4 배포 이력 요약 (참고)

| 커밋 | 로컬 존재 | 서버 반영 | 실 가동 시작 | 목적 |
|---|---|---|---|---|
| `bc582a6` | 2026-08-29 19:28 | 2026-08-29 (배포 커밋 `b874ccc`) | 2026-08-29 19:26~ | WO-6 본체 (시각 통일 + 봉당 1회 + NO_TRADE) |
| `5ab50cf` | 2026-08-30 16:34 | 2026-08-30 자체 배포 | 2026-08-30 16:34~ | WO-6 hotfix (last_bar_ts 갱신 위치) |
| `da871da` | 2026-09-02 13:29 | 2026-09-02 배포 커밋 `17bb386` (14:24) | 2026-09-02 14:24~ | WO-2 재적용 본체 |
| `57d290e` | 2026-09-04 17:36 | 2026-09-04 배포 커밋 `0a256fb` (17:37) | 2026-09-04 17:37~ | WO-2 옵션 C |
| `53fdbf3` | 2026-09-04 19:43 | 2026-09-04 자체 배포 | **2026-09-04 19:43:56** (ExecMainStart) | dashboard 손익 표시 변경 |

**현재 서버는 2026-09-04 19:43:56 KST부터 8일+ 무중단 가동 (재시작 없음).**

### 1.2 F5 (§3.5 포함 시)

| 파일 | 함수·라인 | 변경 내용 | 근거 |
|---|---|---|---|
| `core/rest_reconcile.py` | `fetch_confirmed_candle` (line 434~) | **케이스 순서 A → C → B로 재배치.** 케이스 A 최상단 승격 | 설계문서 §3.5 최소 수정안 |
| `core/rest_reconcile.py` | 신규 | `NO_TRADE = object()` 센티널 상수. 무거래 봉 반환 | 설계문서 §3.5 케이스 D |
| `core/rest_reconcile.py` | 케이스 B 로직 | 5초 안정화 1회 (`_case_b_state` 딕셔너리, 첫 진입 시 종가 저장 → 5초 뒤 동일 종가 확인 → 확정, 다르면 재판정) | 설계문서 §3.5 케이스 B |
| `core/rest_reconcile.py` | 신규 | `_case_b_state_gc()` — 함수 진입 시 오래된 항목(30분 이전) 자동 삭제 | 설계문서 §5.0 |
| `engine/live_loop.py` | line 982~984 부근 | `fetch_confirmed_candle` 결과가 `NO_TRADE`면 로그 한 줄 남기고 봉 건너뜀. `None`이면 ERROR 로그 후 `reconcile_series` 계속 진행 (즉 §4.2 관문 통과) | 설계문서 §3.5 잔여 위험 |

### 1.3 문서·주석

- `docs/issues/issue-08.md` line 참조 갱신 (fetch_confirmed_candle 라인이 재배치되면).
- `docs/issues/issue-11.md` line 참조 갱신 (BACKFILL 백업·복원 관련 라인).
- `.claude/context/project-rules.md` 및 `CLAUDE.md` 관련 절 갱신 (필요 시).

---

## 2. F5(§3.5) 이번 라운드 포함 여부 — 찬반

### 2.1 찬(포함) 근거

- **JTO-GC 04:34 사례 원천 처방**: 미확정 종가(777→779원) 위 매수 판정이 F5의 실증 사례 (docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md). WO-6 라벨 통일만으로는 이 결함이 해소되지 않는다.
- **NO_TRADE 센티널**: 저유동성 무거래 봉에서 가짜 봉 합성 방지. Upbit 차트/백테스트와 봇 내부 시계열 정합성 확보.
- **케이스 A 순서 승격**: 24h 실측 262건(18.2%) FAST 경로 p50=29ms로 정상 확인됨 (설계문서 §3.5). 순서 재배치로 성능·정확성 동시 개선.
- **WO-2 재적용 사전 조건**: WO-2 재적용은 확정 판정 강화를 전제로 하는데, F5가 미봉쇄 상태면 재적용 진입 조건이 미비.

### 2.2 반(제외) 근거

- **단일 라운드 범위 원칙**: WO-6의 중심 원칙(설계문서 §2)은 "모든 봉은 정확히 한 번 실시간 평가"다. 라벨 통일 + 봉당 1회 관문만으로도 이 원칙은 성립. F5는 별도 원칙(확정 판정 정확성).
- **회귀 위험 분산**: 라벨 통일 + `[SKIP-BAR]` 제거 + `_evaluated_bar_ts` 관문 3중 변경만으로도 배포 시점 관측 항목이 많다. F5 재배치를 함께 넣으면 회귀 원인 격리가 어려움.
- **F5 자체 방어망 존재**: 현재 고정가 미체결이 F5의 사실상 방어망 (미확정 종가 위 매수 시 지정가가 안 잡히면 취소됨). 시장가 전환은 별도 결정 (WO-8이 강제 매수 지정가 이식 다룸).
- **단일 revert 단위**: F5 미포함 시 revert 대상이 좁아져 롤백 안전. F5 포함 시 revert 시 라벨 통일까지 함께 되돌아감.

### 2.3 초안 권고 (사용자 판정 대기)

**F5 미포함 (반 근거 우세) 권고**. 근거:
- WO-6의 원칙 §2가 라벨 통일 + 봉당 1회로 충분 성립.
- 회귀 위험 분산이 배포 안전성에 더 중요.
- F5는 WO-2 재적용 라운드 시 함께 처방.

다만 사용자가 "F5 존치를 유지할 수 없는 시장 위험이 있다"라고 판단하면 §3.5 포함 방향으로 재작성.

---

## 3. 검증 계획

### 3.1 배포 전 병행 실행 (설계문서 §5.1)

- **실행 방법**: 로컬에서 `python -m engine.live_loop --ticker KRW-JTO --strategy EMA --dry-run` (dry-run 플래그 신설 필요 시 구현 단계에서 결정). 서버 봇과 로컬 봇이 같은 종목 대상 나란히 작동.
- **관측 시간대**:
  - 저유동성 (KST 03:00~06:00) 최소 30봉
  - 활성 (KST 09:00~11:00) 최소 30봉
- **필수 확인**:
  - `[SKIP-BAR]` 로그 부재
  - `[CONFIRMED]` 처리가 봉당 1회
  - BACKFILL 재평가 시 매매 판단 미실행 (`_evaluated_bar_ts` 검사 통과 확인)
  - 봉당 매매 판단 횟수 정확히 1
  - `_evaluated_bar_ts` 등록 로그와 판단 스킵 로그가 짝을 이룸
  - F5 포함 시: fetch_confirmed_candle 케이스 A/B/C 각각 예상 동작 (A: 즉시 확정, C: 재시도, B: 5초 안정화)

### 3.2 배포 직후 30분 확인 (설계문서 §5.2)

- 서비스 restart 후 7단계 기동 로그 관측
- `[SKIP-BAR]` 로그 부재
- Traceback, CRITICAL, POLLUTED 부재
- 첫 30분 처리 봉 목록 → 봉당 매매 판단 횟수 정확히 1
- 지정가 매수 활성 상태에서 봉 경계 주문 접수·취소 정상

### 3.3 24시간 실측 (설계문서 §5.3)

- **필수 SQL 확인**:
  ```sql
  -- 봉별 매매 판단 결과 행이 정확히 1개인지
  SELECT bar_time, COUNT(*) 
  FROM audit_buy_eval 
  WHERE ticker = 'KRW-JTO' 
    AND timestamp >= '2026-XX-XX 00:00:00' 
    AND timestamp <  '2026-XX-XX 23:59:59'
    AND price IS NOT NULL  -- 실시간 컬럼
  GROUP BY bar_time 
  HAVING COUNT(*) > 1;   -- 결과가 0행이어야 봉당 1회 원칙 충족
  ```
- BACKFILL 컬럼이 추가로 채워지는 것은 허용 (지표 갱신 결과)
- BACKFILL 트리거 이후 실주문 미발화 확인
- `changed_count > 0` 시 지표 갱신은 있어도 매매 판단은 봉당 1회

### 3.4 FV1 정정 산식 커버리지 검산 (추가 필수)

**본 조사의 FV1 §3.5 정정 산식을 배포 후 검증 항목에 포함한다. 분모는 audit 행 수가 아니라 "기간 내 기대 확정 봉 수"다.**

**기대 봉 수 산출**:
- `기대 봉 수 = ((end_ts - start_ts) / interval_sec) - 무거래 봉(NO_TRADE 대상) 수`
- KRW-JTO 5분봉 기준 24h = 24 × 12 = 288봉 (무거래 봉 제외 전)
- 무거래 봉은 Upbit REST minute5로 시계열 조회 후, 응답에 존재하지 않는 봉 시각을 세어 제외 (설계문서 §3.5 케이스 D 근거)

**메인 커버리지 질의**:
```sql
-- 실시간 판정 커버리지 (WO-6 이후 목표 ≥ 95%)
-- 분모 = 기대 봉 수 (interval_sec 기반, NO_TRADE 봉 제외)
WITH expected AS (
  -- 로컬에서 Upbit minute5 시계열 조회 결과를 임시 테이블로 로드 후
  -- SELECT bar_time_kst FROM expected_bars WHERE ticker='KRW-JTO' AND bar_time_kst BETWEEN ... AND ...
  SELECT bar_time_kst FROM expected_bars
   WHERE ticker = 'KRW-JTO'
     AND bar_time_kst >= '2026-XX-XX 00:00:00'
     AND bar_time_kst <  '2026-XX-XX 23:59:59'
),
realtime AS (
  SELECT bar_time
    FROM audit_buy_eval
   WHERE ticker = 'KRW-JTO'
     AND price IS NOT NULL  -- 실시간 컬럼 채워진 봉만
     AND bar_time >= '2026-XX-XX 00:00:00'
     AND bar_time <  '2026-XX-XX 23:59:59'
)
SELECT
  (SELECT COUNT(*) FROM expected)                                   AS expected_cnt,
  (SELECT COUNT(DISTINCT bar_time) FROM realtime)                   AS realtime_cnt,
  100.0 * (SELECT COUNT(DISTINCT bar_time) FROM realtime) 
        / (SELECT COUNT(*) FROM expected)                           AS coverage_pct;
```

**보조 검사: 부재 봉 목록 질의** (커버리지 미달 시 원인 특정용):
```sql
-- 기대 봉 목록 - 실시간 audit bar_time 목록 = 부재 봉 목록
SELECT bar_time_kst AS missing_bar_time
  FROM expected_bars
 WHERE ticker = 'KRW-JTO'
   AND bar_time_kst >= '2026-XX-XX 00:00:00'
   AND bar_time_kst <  '2026-XX-XX 23:59:59'
   AND bar_time_kst NOT IN (
     SELECT bar_time FROM audit_buy_eval
      WHERE ticker = 'KRW-JTO'
        AND price IS NOT NULL
        AND bar_time >= '2026-XX-XX 00:00:00'
        AND bar_time <  '2026-XX-XX 23:59:59'
   )
 ORDER BY bar_time_kst;
```

- **목표**: coverage_pct ≥ 95% (기대 봉 수 대비 실시간 판정 봉 수)
- **v3 H-A 실측(비교 기준)**: 09시 KRW-JTO 5분봉 12개 중 실시간 판정 1개 = **8.3%**
- **95% 미만이면 롤백 조건**
- **부재 봉 목록이 3봉 이상**이면 원인 조사 후 재배포 결정

### 3.5 검증 실패 시 조치 (설계문서 §5.4)

세 단계 중 어느 하나라도 실패하면 즉시 롤백. 아래 §4 참고.

---

## 4. 롤백 계획 (단일 revert 단위)

### 4.1 단일 revert 원칙

- WO-6은 **하나의 커밋** 또는 **연속된 원자적 커밋 집합**으로 배포한다.
- 롤백은 `git revert <WO-6 커밋>`으로 실행. force push 없음.
- **원문 정정 (2026-09-12)**: 기존 기재 "대상 상태: 현재 서버 HEAD 기준 `1404c1c`"는 계획서 초안 시점(2026-08-25 롤백 직후) 상태 인용이었으며, 실제 배포 후 대상 상태는 배포 직전 커밋. 배포 이력표(§1.4)에 따라 각 revert의 정확한 롤백 대상은:
  - `bc582a6` (WO-6 본체) revert 시 → 대상 = `1404c1c`
  - `5ab50cf` (WO-6 hotfix) revert 시 → 대상 = `bc582a6`
  - `da871da` (WO-2 재적용) revert 시 → 대상 = `5ab50cf`
  - `57d290e` (WO-2 옵션 C) revert 시 → 대상 = `17bb386`

### 4.2 F5 포함 시 revert 단위

- F5 포함하면 revert 시 라벨 통일까지 함께 되돌아감. 이를 피하려면:
  - **분리 커밋 A**: 라벨 통일 + 봉당 1회 (필수)
  - **분리 커밋 B**: F5 재배치 (별도, 선택적 revert 가능)
- 두 커밋을 순차 배포하고 각각의 검증 세 겹을 별개로 통과시켜야 함.

### 4.3 즉시 롤백 트리거

- 배포 직후 30분 내 Traceback, CRITICAL, POLLUTED 1건 이상
- `[SKIP-BAR]` 로그 재출현 (제거 실패)
- 24h 실측 시 봉당 매매 판단 2회 이상 봉이 1건 이상
- 24h 실측 시 실시간 판정 커버리지 <95% (FV1 정정 산식)
- 매매 결정 지연 (60초 이상 발주 지연 관측 시)

### 4.4 롤백 절차

```bash
# 1. 로컬에서 revert
git revert <WO-6-COMMIT-HASH>
# 2. push
git push
# 3. 서버 배포
deploy-tradebot
# 4. 30분 관측 (원상복귀 확인)
```

**force push 금지, hook 우회 금지.**

---

## 5. WO-7 (평균가 옵션) · WO-8 (강제 매수 지정가) 충돌 점검

### 5.1 WO-7 (평균가 옵션) 관련성

**V-A 조사 결과 (report.md §2)**: HTS-DETECT-CALLBACK이 `position_state.avg_price`를 즉시 동기화 (`old_avg=565.891 → new_avg=565.166`). 매도 판단은 갱신된 avg 기준 정상 실행. **결함 없음**.

**WO-7 범위 한정 (승인 확정)**: WO-7은 현행 평균가 동작의 **화면 노출과 사용 여부 옵션**에 한정한다. avg 계산 로직 변경(슬리피지 반영, 부분 체결 정책 등)은 별도 워크오더로 분리한다.

**WO-6와 충돌 여부**:
- WO-6은 `position_state.avg_price` 자체를 건드리지 않음. HTS-DETECT-CALLBACK 로직도 변경 없음.
- **충돌 없음.** WO-7이 avg_price 계산·저장 로직만 개선하면 WO-6 관문(_evaluated_bar_ts)과 무관.

**주의 사항**:
- WO-6 배포 시 매도 필터(`core/filters/sell_filters.py`)의 avg 사용은 그대로. WO-7이 avg 계산 방식을 바꾸면 매도 필터 계산도 함께 바뀌므로 검증 필요.

### 5.2 WO-8 (강제 매수 지정가) 관련성

**V-B 조사 결과 (report.md §1)**: `services/trading_control.py:242 force_buy_in()`이 무조건 `trader.buy_market()` 호출. `fixed_price_buy_enabled` 분기 없음. bot_limit_fill/wait_bars/#14 알림 모두 우회.

**WO-8 이식 시**: `force_buy_in()`에 `fixed_price_buy_enabled` 분기 추가 → `trader.buy_limit()` 호출 → bot_limit_fill 콜백 경유 → strategy_engine의 `apply_entry` 진입.

**WO-6와 충돌 여부**:
- WO-8이 지정가 이식 시 `bot_limit_fill` 콜백에서 `strategy_engine.apply_entry(uuid, ...)` 호출. 이 apply_entry가 봉당 1회 관문을 통과해야 하는지가 관건.
- 설계문서 §4.2에 따르면 `_evaluated_bar_ts` 검사는 **매매 판단 직전** (`self.strategy.on_bar` 호출 직전)에만 발동. apply_entry는 이미 발주 후 체결 응답 처리이므로 관문 적용 대상 아님.
- **충돌 없음.** WO-8이 지정가 이식만 하면 WO-6 관문 로직과 무관.

**주의 사항**:
- WO-6 배포 후 지정가 매수 시 봉 경계 주문 접수·취소가 정상 작동해야 함 (§3.2 필수 확인 항목).
- WO-8 이식 시점에는 WO-6이 이미 배포 완료 상태여야 함 (WO-6 미배포 상태에서 WO-8 우선 이식은 위험).

### 5.3 배포 순서 (사용자 판정 대상)

| 순위 | 대안 | 근거 |
|---|---|---|
| 1위 (권고) | WO-6 → WO-8 → WO-7 → WO-2 재적용 | WO-6 안착 후 WO-8(강제 매수 지정가) 이식으로 F5 방어망 강화. WO-7·WO-2는 후속 |
| 2위 | WO-6 → WO-7 → WO-8 → WO-2 재적용 | WO-7이 avg 계산 개선 위주면 매도 로직 안정성 먼저 |
| 3위 | WO-6 → WO-2 재적용 (F5 포함) → WO-7 · WO-8 | 확정 판정 강화 우선. 다만 WO-2 재적용은 4번 시도 |

---

## 6. 완료 기준 · Definition of Done

- [ ] 배포 전 병행 실행 검증 통과 (설계문서 §5.1)
- [ ] 배포 직후 30분 확인 통과 (§3.2)
- [ ] 24시간 실측 봉당 1회 원칙 100% 유지 (§3.3)
- [ ] **FV1 정정 산식 실시간 판정 커버리지 ≥ 95%** (§3.4, 분모 = 기간 내 기대 확정 봉 수 (interval_sec 기반, NO_TRADE 봉 제외))
- [ ] `[SKIP-BAR]` 로그 완전 부재 (24h)
- [ ] 지정가 매수 봉 경계 정상 작동 (KRW-JTO fixed_price_buy_enabled=true 상태)
- [ ] Traceback·CRITICAL·POLLUTED 0건 (24h)
- [ ] dashboard.py 버전 갱신
- [ ] docs/plans/2026-08-25-wo6-...md 참조 라인 갱신 (변경된 라인이 있는 경우)
- [ ] docs/issues/issue-08.md, issue-11.md 참조 라인 갱신
- [ ] 배포 커밋 메시지에 revert 방법·롤백 트리거 명시

---

## 7. 예상 리스크 · 대응

| 리스크 | 확률 | 영향 | 대응 |
|---|---|---|---|
| `_evaluated_bar_ts` 상한 초과로 오래된 봉 재판단 | 낮음 (1000봉/16h 여유) | 매매 1회 원칙 위배 | 상한 정책 명시. 재시작 시 `last_bar_ts` 방어선 (§4.2) |
| 재시작 시 `_evaluated_bar_ts` 소실 | 확실 (재시작 시) | 재시작 봉 1개 이중 판단 가능 | `last_bar_ts` 방어선 (설계문서 §4.2 재시작 대응) |
| BACKFILL이 먼저 실행되어 실시간 판단이 막힘 | 매우 낮음 | 매수 신호 소실 | 등록 주체 = 실시간만. BACKFILL은 등록 안 함 (§4.2) |
| F5 포함 시 케이스 B 5초 안정화가 매도 필터 반응 지연 | 낮음 (실측 changed_close 0건) | 매도 신호 지연 | 최악 지연 상한 = 재시도 한도 × 5초 (설계문서 §3.5) |
| 라벨 통일 후 `last_bar_ts` 비교 오프바이원 재발 | 매우 낮음 | is_new_bar False positive | `candle_clock.py:82` 반환값 재정의 후 24h 실측 (§3.3) |

---

## 8. 승인·재분류 이력 (2026-09-12)

**오전 승인**:
1. **F5(§3.5) 포함 여부**: 미포함. WO-2 재적용 라운드로 이관.
2. **배포 순서**: WO-6 → WO-8 → WO-7 → WO-2 재적용.
3. **dry-run 플래그 신설**: 승인. 조회는 실계정 그대로, 발주 함수 진입 한 지점만 차단, 기본값 꺼짐, 로컬 전용.
4. 최종 판정: (A) 롤백 유지 + WO-6 선행.

**오후 사실 확인 결과 (착수 정지)**:
- §1.1 필수 목록이 이미 `bc582a6` (2026-08-29) + `5ab50cf` (2026-08-30)로 서버 반영·8일+ 무중단 가동 상태 확인.
- WO-2 재적용(`da871da`) + WO-2 옵션 C(`57d290e`)도 정상 배포·가동 중 (2026-09-04 19:43:56 KST~).
- "WO-2 실패로 종결" 기재는 전제 오류. 임시 유보 상태로 되돌림 (사용자 판정 규칙 §4 대기).

**코드 수정 금지 재적용**. 사용자 재판정 대기.

**dry-run 필요성 재평가 의견**:
- WO-6은 이미 8일+ 실 운영 실측으로 검증 통과 (§1.4). §3.1 병행 실행 검증의 사전 존재 이유(라이브 검증 회피)는 소멸.
- **결론**: 이번 WO-6 라운드에서는 dry-run 신설 **불필요**.
- **향후 필요성**: WO-8(강제 매수 지정가) 이식 시 발주 함수 진입점에 지정가 분기가 새로 들어가므로, 그 라운드의 로컬 검증 도구로 재신설 검토.
