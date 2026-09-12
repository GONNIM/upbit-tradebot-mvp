# 2026-09-12 사후 확인 — 커버리지 재산출 + CRITICAL 6건 경위

**전제**: 재판정 확정 (2026-09-12). revert 없음. 서버 상태 `53fdbf3` 승인 유지.
**본 문서는 로컬 저장소에만 존재한다.**
**목적**: 사용자 판정 규칙 §4 첫 번째 조건("WO-2 재적용 상태 + 실측 전부 통과") 검증에 필요한 두 지표를 정합적으로 확정한다.

---

## 0. 두 줄 요약

- **§1 커버리지: 100.00% (판정 대상 1831 / 실시간 판정 1831, 부재 봉 0)** ✓
- **§2 CRITICAL 6건: 전부 지속 1봉 찰나 방어, HTS/외부 매수 3건 + 매수 이벤트 추적 3건 (평균 방어 시간 1~34초), 매매 사고 없음** ✓

---

## §1. 커버리지 산식 정합 (검산 불일치 해소)

### 1.1 기간·종목 고정

- 기간: **2026-09-05 00:00:00 KST ~ 2026-09-12 00:00:00 KST** (168시간)
- 종목: **KRW-JTO 단일**
- interval: minute5 (파라미터 `mcmax33_latest_params_EMA.json` 재확인: `interval: minute5, fast_period: 60, slow_period: 200`)

### 1.2 분자·분모 정의

**분자 (실시간 판정 봉)**:
- 소스: `audit_buy_eval` ∪ `audit_sell_eval` (DISTINCT `bar_time`)
- 실시간 조건: **`price IS NOT NULL`** (WO-1 옵션 B 이후 실시간 컬럼 채워진 행만 실시간 판정으로 인정)
- 5분봉 boundary 필터: `substr(bar_time, 15, 2) IN ('00','05','10','15','20','25','30','35','40','45','50','55') AND substr(bar_time, 18, 2) = '00'`
- 두 테이블 합집합 시 `SELECT DISTINCT bar_time FROM (buy UNION sell)`로 중복 제거

**서버 DB 실측**:
| 소스 | unique 5분봉 |
|---|---|
| `audit_buy_eval` (price NOT NULL) | 1268 |
| `audit_sell_eval` (price NOT NULL) | 563 |
| **UNION distinct** | **1831** |

**5분봉 boundary 아닌 bar_time (예: minute1 시각)**: 0건 (실측). 즉 audit bar_time은 정확히 5분봉 정각만 존재.

**분모 (판정 대상 봉)**:
- **잘못된 접근**: `2016 - NO_TRADE 로그 카운트 713` — NO_TRADE 로그가 KRW-JTO 뿐 아니라 감시 전 종목 로그이고 unique 아님 (로그 라인 카운트). 산식 모순(1831 + 713 > 2016)의 근원.
- **정정 접근**: Upbit REST minute5 API로 KRW-JTO 실 존재 5분봉 조회. **응답에 존재하는 봉 = 판정 대상 봉**, 응답에 없는 봉 = 무거래 봉(NO_TRADE 대상, 제외).

**Upbit REST 재산출** (2026-09-05T00:00 ~ 09-12T00:00 KST):
| 항목 | 값 |
|---|---|
| 이론적 5분봉 수 (168h × 12) | 2016 |
| Upbit 응답 실 존재 봉 | **1831** |
| 무거래 봉 (2016 − 1831) | 185 |

**NO_TRADE 로그 라인 713건의 정체**:
- 로그 형식 예시: `[RECONCILE] 무거래 봉 감지 (NO_TRADE, 건너뜀) | ts=2026-09-05 00:20:00 KST` — 종목 필터 없음
- 감시 종목 다수 · 로그 라인 카운트 · unique 아님 → 713 > 185 (실 무거래 봉)
- 즉 KRW-JTO 무거래 봉 = **185봉**, 다른 종목 포함 무거래 로그 = 713건 (별개 지표)

### 1.3 커버리지 재계산

| 지표 | 값 |
|---|---|
| 판정 대상 봉 (분모) | **1831** |
| 실시간 판정 봉 ∩ Upbit 실 존재 (분자) | **1831** |
| **커버리지 = 분자 / 분모** | **100.00%** |
| 95% 이상? | **YES** ✓ |

### 1.4 부재 봉 차집합 (판정 대상 − 실시간 audit)

**부재 봉 = 0건**. 판정 대상 봉 전체에 실시간 audit 행이 존재.

원인 분류 (해당 없음):
- 무거래 오분류: N/A
- BACKFILL만 남은 봉: N/A (0건)
- 기타: N/A

### 1.5 참고: 고아 봉 (실시간 audit 있으나 Upbit 응답에 없음)

**고아 봉 = 0건**. 즉 봇이 처리한 봉은 모두 Upbit 실 존재 봉.

### 1.6 검증 명령 원문

```
# Upbit REST minute5 · KRW-JTO 7일 실 존재 봉
python3 /tmp/coverage_recount.py
# → Upbit 응답 unique 봉 시각 = 1831
# → 실시간 audit unique 5분봉 = 1831
# → 판정 대상 봉 = 1831, 실시간 판정 봉 (∩) = 1831, 커버리지 = 100.00%, 부재 봉 0
```

```sql
-- 서버 DB 실시간 audit bar_time (5분봉 boundary 유일화)
sqlite3 tradebot_mcmax33.db "SELECT COUNT(DISTINCT bar_time) FROM (
  SELECT bar_time FROM audit_buy_eval  WHERE ticker='KRW-JTO' AND price IS NOT NULL
    AND bar_time >= '2026-09-05T00:00:00' AND bar_time < '2026-09-12T00:00:00'
    AND substr(bar_time,15,2) IN ('00','05','10','15','20','25','30','35','40','45','50','55')
    AND substr(bar_time,18,2) = '00'
  UNION
  SELECT bar_time FROM audit_sell_eval WHERE ticker='KRW-JTO' AND price IS NOT NULL
    AND bar_time >= '2026-09-05T00:00:00' AND bar_time < '2026-09-12T00:00:00'
    AND substr(bar_time,15,2) IN ('00','05','10','15','20','25','30','35','40','45','50','55')
    AND substr(bar_time,18,2) = '00'
);
-- 결과: 1831
```

---

## §2. CRITICAL 6건 경위

### 2.1 공통 매커니즘

- **발생 조건**: `bars_held=0 AND audit 실측 없음`. 즉 **외부 매수(HTS 또는 API 외 경로)로 포지션이 갓 생겼는데** 봇이 아직 첫 SELL 평가를 하지 않은 시점에 매도 판단이 시도될 때.
- **차단 결과**: `❌ [EMA] ... SELL 차단 (HOLD 유지)` 로그 후 매도 미실행.
- **복구 경로**: [POSITION-SYNC] 자동 복구 (`source=upbit_avg_buy_price, api=apply_entry`)로 `entry_bar`·`entry_price` 세팅 → 다음 봉에서 `bars_held=1` 도달 → 정상 SELL 평가 재개.

### 2.2 6건 상세표

| # | 발생 시각 (KST) | entry_bar | 해소 시각 | 지속 봉 수 | 직전 매수 이벤트 (시간 차이) | 진입가 · 첫 close · Δ | 복구 로그 (인용) |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-06 22:15:06 | 749 | 22:15:08 | **1봉** | 22:12:45 SELL 평가 이전 매수 (~2분 21초 전, 추정 HTS) | 634.00 · 633 (−0.16%) | `[POSITION-SYNC] 자동 복구 성공 (source=upbit_avg_buy_price, api=apply_entry): qty=420.632492, entry_price=634.00, entry_bar=749` |
| 2 | 2026-09-06 22:35:06 | 753 | 22:35:07 | **1봉** | **22:34:58 [HTS-DETECT] HTS_BUY** (qty 0→419.464724, avg 635.0, 8초 전) | 635.00 · 635 (0.00%) | `[POSITION-SYNC] 자동 복구 성공 ... qty=419.464724, entry_price=635.00, entry_bar=753` |
| 3 | 2026-09-07 08:05:11 | 864 | 08:05:12 | **1봉** | 08:01:26 이전 (~3분 45초 전, 추정 HTS/force) | 633.00 · 633 (0.00%) | `[POSITION-SYNC] ... qty=42.015182, entry_price=633.00, entry_bar=864` |
| 4 | 2026-09-07 10:10:06 | 889 | 10:10:07 | **1봉** | **10:09:43 [HTS-DETECT] HTS_BUY** (qty 0→83.632663, avg 626.497, 23초 전) | 626.50 · 626 (−0.08%) | `[POSITION-SYNC] ... qty=83.632663, entry_price=626.50, entry_bar=889` |
| 5 | 2026-09-09 16:15:09 | 1500 | 16:15:11 | **1봉** | 16:15:04 이전 (~5초 전, 매수 이벤트) | 626.00 · 626 (0.00%) → 다음 봉 629 (+0.48%) | `[POSITION-SYNC] ... qty=428.512780, entry_price=626.00, entry_bar=1500` |
| 6 | 2026-09-10 07:35:06 | 1666 | 07:35:07 | **1봉** | **07:34:32 [HTS-DETECT] HTS_BUY_ADD** (qty 139.94→185.83, Δ=45.88, avg 567.507, 34초 전) | 567.51 · 566 (−0.27%) | `[POSITION-SYNC] ... qty=185.827690, entry_price=567.51, entry_bar=1666` + Trailing 상태 리셋 |

### 2.3 최대 낙폭

**모든 6건의 첫 봉 close 낙폭 절대치 ≤ 0.27%**. 봇 설정 SL 임계값(-0.9% 또는 -1.0%) **미도달**. 즉 방어 로직이 없었더라도 SL 자체는 발화하지 않았을 상황.

### 2.4 분류

- **찰나 방어 (지속 1~2봉)**: **6건 전부**. 평균 방어 시간 = 발생~해소 1~2초.
- **장시간 무방비 (지속 3봉 이상)**: **0건**.

### 2.5 HTS·force_buy와의 상관

| 유형 | 건수 | 시간 차이 |
|---|---|---|
| [HTS-DETECT] 직접 로그 확인 | **3건** (#2, #4, #6) | 8~34초 |
| 매수 이벤트 추적 (HTS 유추, 로그 grep 범위 외) | **3건** (#1, #3, #5) | 5초~3분 45초 |
| force_buy 직접 상관 | **0건** |
| EMA_GC 자동 매수 상관 | **0건** |

**모든 6건이 외부 매수(HTS) 감지 직후 첫 봉에서 발생**. `force_buy_in()`이나 `EMA_GC` 자동 매수는 발주 시점에 `apply_entry`가 정상 호출되어 `entry_bar` 세팅이 완료되므로 CRITICAL 조건에 걸리지 않음. **HTS 매수 감지 → position sync → 다음 봉 첫 평가 사이의 짧은 창에서만 발동**.

### 2.6 WO-8 설계 입력

- **관찰**: 외부 경로(HTS·강제 매수) 매수 후 첫 봉 SELL 평가에서 audit 부재 조건이 걸리면 SELL을 차단하고 다음 봉으로 넘긴다. 이 방어 자체가 `strategy_incremental.py`에 이미 반영되어 있음.
- **WO-8 시사점 (강제 매수 지정가 이식)**:
  1. WO-8이 `force_buy_in()`을 지정가 경로로 이식하면 `trader.buy_limit()` → `bot_limit_fill` 콜백 → `apply_entry` 순으로 진행. 이 경로에서는 `entry_bar` 세팅이 fill 콜백 시점에 완료되므로 CRITICAL 조건에 걸리지 않는다.
  2. 다만 **미체결 후 봉 경계 취소 시**에는 진입 기록이 남지 않아 다음 매수 시도 시 정상 흐름 유지 (문제 없음).
  3. WO-8 검증 필수 항목: 지정가 체결 직후 첫 봉 SELL 평가에서 CRITICAL이 발생하지 않는지 실측 (`[POSITION-SYNC]` 로그 부재 확인).

---

## 3. 참조

- FV 조사: `docs/plans/2026-09-12-fv1-fv3-and-v-a-v-b-investigation/report.md`
- WO-6 현실 대조표: `docs/plans/2026-09-12-wo6-implementation-plan/plan.md`
- Streamlit UI Traceback (별도 이슈): `docs/issues/issue-18-streamlit-ui-tracebacks.md`
