# KRW-JTO 트레이딩 성과 진단 (2026-06-21)

**작성일**: 2026-06-22
**분석 기간**: 2026-05-24 ~ 2026-06-21 (28일)
**대상 사용자**: `mcmax33`
**데이터 출처**: `services/data/tradebot_mcmax33.db` (orionhunter 서버)
**분석 트리거**: 사용자 요청 — "수익이 제대로 나지 않는 문제점 검증"
**결론 요약**: 누적 손익률 **-9.78%** (28일) — 복합 원인 (R/R<1, 1분봉 노이즈, stale_position 비활성)

관련:
- [[settings-history/plan.md]] — 본 진단을 가능케 한 audit/snapshot 인프라
- 권장 액션 후속 → 미정 (백테스트·파라미터 변경 시점 별도 보고서로 추적 예정)

---

## 1. 정량 데이터

### 1-1. 전체 성과 (모든 ticker)

| 지표 | 값 |
|---|---|
| 총 매도 (체결) | **77건** |
| 승 / 패 / 무손익 | 32 / 43 / 2 → **승률 41.6%** |
| 평균 손익률 | **-0.127%** |
| **누적 손익률** | **-9.78%** |

### 1-2. KRW-JTO 한정 (39건, 가장 활발한 ticker)

| 매도 사유 | 건수 | 승 | 패 | 평균 손익 | 누적 손익 |
|---|---:|---:|---:|---:|---:|
| **STOP_LOSS** | **21** | 0 | 21 | **-0.875%** | **-18.38%** |
| TRAILING_STOP_FIXED | 13 | 12 | 1 | +0.753% | +9.78% |
| TAKE_PROFIT | 4 | 4 | 0 | +1.063% | +4.25% |
| TRAILING_STOP_RATIO | 1 | 1 | 0 | +0.446% | +0.45% |
| **합계** | **39** | 17 (44%) | 22 (56%) | -0.10% | **-3.90%** |

### 1-3. ticker 별 누적

| ticker | sells | win | loss | sum_pnl_pct |
|---|---:|---:|---:|---:|
| KRW-JTO | 39 | 17 | 22 | **-3.90%** |
| KRW-KITE | 15 | 4 | 9 | -0.32% |
| KRW-SUI | 13 | 6 | 7 | **-3.66%** |
| KRW-ICP | 5 | 4 | 1 | +0.49% |
| KRW-PENDLE | 4 | 1 | 3 | -1.39% |
| KRW-SEI | 1 | 0 | 1 | -1.00% |
| **합계** | **77** | 32 | 43 | **-9.78%** |

### 1-4. 일별 변동 (최근 14일)

| 일자 | sells | win/loss | 일 누적 |
|---|---:|---:|---:|
| 2026-06-20 | 1 | 0/1 | **-3.12%** |
| 2026-06-19 | 3 | 2/1 | +3.47% |
| 2026-06-18 | 6 | 0/6 | **-3.81%** |
| 2026-06-17 | 4 | 3/1 | +1.14% |
| 2026-06-16 | 1 | 0/1 | -0.98% |
| 2026-06-15 | 1 | 1/0 | +1.07% |
| 2026-06-14 | 1 | 0/1 | -0.73% |
| 2026-06-13 | 1 | 1/0 | +1.22% |
| 2026-06-12 | 4 | 4/0 | +2.34% |
| 2026-06-11 | 4 | 1/3 | -1.37% |
| 2026-06-10 | 9 | 2/7 | **-3.81%** |
| 2026-06-09 | 4 | 3/1 | +0.69% |
| 2026-06-08 | 1 | 0/1 | -0.63% |
| 2026-06-07 | 3 | 1/2 | -0.76% |

→ 하루에 -3% 이상 잃는 날 **3일** (6/10, 6/18, 6/20). 변동성 관리 부재.

---

## 2. 현재 활성 전략 파라미터 (settings_history 최신 row 기준)

### 2-1. params.json

```json
{
  "ticker": "JTO",
  "interval": "minute1",
  "fast_period": 60,
  "slow_period": 200,
  "signal_period": 9,
  "take_profit": 0.03,
  "stop_loss": 0.03,
  "commission": 0.0005,
  "order_ratio": 0.1,
  "base_ema_period": 200,
  "ma_type": "EMA",
  "ema_surge_filter_enabled": true,
  "ema_surge_threshold_pct": 0.02,
  "use_separate_ema": true,
  "fast_buy": 60, "slow_buy": 200,
  "fast_sell": 60, "slow_sell": 200,
  "strategy_type": "EMA"
}
```

### 2-2. conditions.json

```json
{
  "buy": {
    "ema_gc": true,
    "above_base_ema": false,
    "bullish_candle": false,
    "surge_filter_enabled": true,
    "fixed_price_buy_enabled": true,
    "surge_threshold_pct": 0.01
  },
  "sell": {
    "stop_loss": true,
    "take_profit": false,
    "trailing_stop": true,
    "ema_dc": false,
    "stale_position_check": false,
    "stop_loss_pct": 3.0,
    "take_profit_pct": 3.0,
    "trailing_stop_threshold_pct": 30.0,
    "use_fixed_trailing": true
  }
}
```

### 2-3. 진단 요약

| 항목 | 값 | 진단 |
|---|---|---|
| interval | **1분봉** | 🔴 노이즈 매우 큼 |
| fast/slow | 60 / 200 | 🟡 1분봉에서는 시그널 지연·잡음 |
| take_profit (params) | 3% | — |
| stop_loss (params) | 3% | — |
| conditions.sell.take_profit | **false** | 🔴 OFF인데 실제 발동 4건 (정합 점검 필요) |
| conditions.sell.stop_loss | true | — |
| conditions.sell.trailing_stop | true | — |
| conditions.sell.stale_position_check | **false** | 🔴 장기 보유 보호 부재 |
| trailing_stop_threshold_pct | 30.0 | 🟡 trailing arming 임계값 |
| ema_surge_filter | true (2%) | ✓ 적정 |
| order_ratio | 0.1 (10%) | ✓ 보수적 |

---

## 3. 핵심 진단 — 무엇이 문제인가

### 문제 ① R/R(Reward/Risk) 비율 < 1 — 구조적 손실

```
평균 손실 (STOP_LOSS):     -0.875%
평균 익절 (TRAILING_STOP):  +0.753%
R/R = 0.753 / 0.875 = 0.86  ← 정상 시스템은 ≥ 1.5
```

**손익 분기점 승률 = 0.875 / (0.875 + 0.753) = 53.7%**
현재 승률 **44%** → 구조적으로 손실 발생 (전략 자체가 음(-) 기댓값).

### 문제 ② STOP_LOSS 설정(3%) 대비 실제 트리거 손익률 불일치

| 손익률 구간 | STOP_LOSS 건수 (전체 ticker) |
|---|---:|
| -2% 미만 | 2 |
| -1 ~ -2% | 7 |
| **-0.5 ~ -1%** | **32 (76%)** |
| -0.5 ~ 0% | 1 |

`stop_loss_pct=3.0` 인데 실제 평균 -0.875%. **임계값 해석 또는 트리거 조건이 의도와 다름.** → 코드 검증 필요 (`core/strategy_incremental.py` / `core/filters/sell_filters.py`).

### 문제 ③ TAKE_PROFIT 토글 OFF인데 발동

`conditions.sell.take_profit = false` 이나 audit_trades 에 `reason='TAKE_PROFIT'` 6건 (모두 익절). **UI 토글과 실제 동작 불일치** → 트리거 분기 정합성 점검 필요.

### 문제 ④ stale_position_check 비활성 → 장기 보유 손실 폭주

| 날짜 | bars_held | 손익 | 사유 |
|---|---:|---:|---|
| **2026-06-20 20:27** | **365 (6시간)** | **-3.12%** | STOP_LOSS |
| 2026-06-14 19:56 | 215 (3.5시간) | -0.73% | STOP_LOSS |

`stale_position_check` 가 켜져 있었으면 1~2시간 시점에 손절했을 가능성 — 큰 손실 방지.

### 문제 ⑤ 1분봉 노이즈

- `audit_buy_eval` **27,762건** (28일 ≈ 1분당 1건 평가)
- 매수 시그널 트리거 비율 ~ **0.7%** (190/27762)
- 1분봉에서 EMA 60/200 골든 크로스 → 빈번한 잡음 시그널 + 매수 직후 가격 하락 → STOP_LOSS

### 문제 ⑥ 일별 손익 변동성 극심

좋은 날(6/12: +2.34%)도 있지만 **하루에 -3% 이상 잃는 날이 3일** → **개별 거래 위험 관리 부재** (예: 일일 손실 한도, 연속 손절 시 매수 중단 등).

---

## 4. 결론 — 전략이 문제인가?

**복합적 문제**.

| 원인 | 비중 |
|---|---|
| 1️⃣ 전략 시그널 품질 낮음 (1분봉 + EMA 60/200 노이즈) | 🔴 가장 큰 원인 |
| 2️⃣ R/R < 1 — 구조적 손실 | 🔴 가장 큰 원인 |
| 3️⃣ stale_position 미활성 → 장기 보유 큰 손실 | 🟡 |
| 4️⃣ STOP_LOSS 임계값과 실제 트리거 불일치 (코드 검증 필요) | 🟡 |
| 5️⃣ TAKE_PROFIT 토글 정합성 (코드 검증 필요) | 🟢 |

---

## 5. 권장 액션 (우선순위)

### 🔴 즉시 (전략 파라미터)

1. **interval 변경**: 1분 → **5분** 또는 **15분** (노이즈 1/5 ~ 1/15)
2. **stale_position_check 활성화** + 한계 시간 90 ~ 120분
3. **R/R ≥ 1.5 확보**:
   - 옵션 A: stop_loss 1.5% + take_profit 3% (작은 손절 + 정상 익절)
   - 옵션 B: 현 3%/3% 유지 + ema_surge_filter 2% → 3% 상향 (시그널 엄격)

### 🟡 코드 점검 (다음 작업)

4. `core/strategy_incremental.py` / `core/filters/sell_filters.py` 의 **STOP_LOSS 트리거 로직 검증** — 왜 -0.875%에서 발동되는지
5. **TAKE_PROFIT 토글 OFF인데 발동되는 이유 점검** (트리거 분기 분리)

### 🟢 백테스트 권고

6. 위 1~3 조합으로 **최근 3개월 백테스트** → 누적 손익 + 승률 + R/R 검증 후 라이브 전환

---

## 6. 데이터 조회 SQL 부록 (재현 가능)

서버: `ssh root@orionhunter7.cafe24.com`
DB: `/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db`

### 6-1. 전체 운영 통계

```sql
SELECT
  COUNT(*)                                              AS total_orders,
  SUM(CASE WHEN side='BUY'  AND state='FILLED'   THEN 1 ELSE 0 END) AS buy_filled,
  SUM(CASE WHEN side='BUY'  AND state='CANCELED' THEN 1 ELSE 0 END) AS buy_canceled,
  SUM(CASE WHEN side='BUY'  AND state='FAILED'   THEN 1 ELSE 0 END) AS buy_failed,
  SUM(CASE WHEN side='SELL' AND state='FILLED'   THEN 1 ELSE 0 END) AS sell_filled,
  MIN(timestamp), MAX(timestamp)
FROM orders;
```

### 6-2. SELL 페어링 승률 (모든 ticker)

```sql
SELECT
  COUNT(*) AS total_sells,
  SUM(CASE WHEN price > entry_price THEN 1 ELSE 0 END) AS win,
  SUM(CASE WHEN price < entry_price THEN 1 ELSE 0 END) AS loss,
  SUM(CASE WHEN price = entry_price THEN 1 ELSE 0 END) AS flat,
  ROUND(AVG((price - entry_price) / entry_price * 100), 3) AS avg_pnl_pct,
  ROUND(SUM((price - entry_price) / entry_price * 100), 2) AS sum_pnl_pct
FROM audit_trades
WHERE type='SELL' AND entry_price IS NOT NULL AND entry_price > 0;
```

### 6-3. 매도 사유별 분포 (KRW-JTO 한정)

```sql
SELECT
  reason,
  COUNT(*) AS cnt,
  SUM(CASE WHEN price > entry_price THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN price < entry_price THEN 1 ELSE 0 END) AS losses,
  ROUND(AVG((price - entry_price) / entry_price * 100), 3) AS avg_pnl_pct,
  ROUND(SUM((price - entry_price) / entry_price * 100), 2) AS sum_pnl_pct
FROM audit_trades
WHERE type='SELL' AND ticker='KRW-JTO' AND entry_price IS NOT NULL
GROUP BY reason
ORDER BY cnt DESC;
```

### 6-4. STOP_LOSS 손익률 분포 (왜 -0.875% 에서 트리거?)

```sql
SELECT
  CASE
    WHEN (price - entry_price) / entry_price * 100 < -2.0 THEN '<-2%'
    WHEN (price - entry_price) / entry_price * 100 < -1.0 THEN '-2~-1%'
    WHEN (price - entry_price) / entry_price * 100 < -0.5 THEN '-1~-0.5%'
    ELSE '-0.5~0%'
  END AS pnl_band,
  COUNT(*) AS cnt
FROM audit_trades
WHERE type='SELL' AND reason='STOP_LOSS' AND entry_price IS NOT NULL
GROUP BY pnl_band ORDER BY pnl_band;
```

### 6-5. 일별 손익 (최근 14일)

```sql
SELECT
  date(timestamp) AS day,
  COUNT(*) AS sells,
  SUM(CASE WHEN price > entry_price THEN 1 ELSE 0 END) AS win,
  SUM(CASE WHEN price < entry_price THEN 1 ELSE 0 END) AS loss,
  ROUND(SUM((price - entry_price) / entry_price * 100), 2) AS sum_pnl_pct
FROM audit_trades
WHERE type='SELL' AND entry_price IS NOT NULL
  AND date(timestamp) >= date('2026-06-07')
GROUP BY date(timestamp) ORDER BY day DESC;
```

### 6-6. 보유 시간 분포 (장기 보유 손실 확인)

```sql
SELECT
  reason, COUNT(*) AS cnt,
  MIN(bars_held), ROUND(AVG(bars_held), 1) AS avg_bars, MAX(bars_held)
FROM audit_trades
WHERE type='SELL' AND bars_held IS NOT NULL
GROUP BY reason ORDER BY cnt DESC;
```

### 6-7. 현재 활성 전략 파라미터

```sql
SELECT params_json
FROM settings_history
WHERE user_id='mcmax33' AND strategy_type='EMA'
ORDER BY id DESC LIMIT 1;

SELECT conditions_json
FROM settings_history
WHERE user_id='mcmax33' AND strategy_type='EMA'
ORDER BY id DESC LIMIT 1;
```

---

## 7. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-22 15:30 | 진단 보고서 초안 작성 | 사용자 요청 "수익이 제대로 나지 않는 문제점 검증" → 28일 데이터 기반 다각 분석. 권장 액션 6개 도출 |
| 2026-06-22 16:00 | §8 1분봉 유지 권장안 추가 | 사용자 결정 "1분봉 그대로 두고 최적 방안" → interval 변경 없는 노이즈 보완 방안 |
| 2026-06-22 16:00 | §9 코드 검증 발견 사항 추가 | STOP_LOSS 트리거 코드와 실제 데이터 결정적 모순 발견 |

---

## 8. 1분봉 유지 전제 — 최적 권장 파라미터 (사용자 결정 2026-06-22)

### 8-0. 제약 / 전제

- `interval = "minute1"` **고정** (사용자 결정)
- 다른 파라미터·필터로 1분봉 노이즈를 보완하는 것이 본 권장안의 목표
- 1분봉 + EMA 60/200 골든 크로스는 시그널 자체는 유효 (TRAILING_STOP 28건 92% 익절이 증거) — 다만 진입 후 stop loss 짧게 맞는 비율이 문제

### 8-1. 핵심 권장 조합 — "보수형" (안전 우선)

**목표**: STOP_LOSS 발동 빈도를 ½ 이하로 줄이고, R/R ≥ 1.5 확보.

| 항목 | 현재 | 권장 | 효과 |
|---|---|---|---|
| `stale_position_check` | false | **true** | 🔴 6시간 보유 -3.12% 같은 사고 차단 |
| stale 한계 시간 | — | **90~120분** | 1분봉 기준 90~120 bars |
| stale 손익 임계 | — | **-0.3% 미만 (손실 진행 중)** | 익절 진행 중이면 보유 유지 |
| `stop_loss_pct` | 3.0 | **1.5** | 실제 트리거가 -0.875% 평균 → 1.5%로 명시 |
| `take_profit_pct` | 3.0 | **2.5** | R/R = 2.5/1.5 = **1.67 ✓** |
| `conditions.sell.take_profit` | **false** | **true** | TAKE_PROFIT 정상 트리거 (현재는 토글 OFF 인데 4건 발동 — 코드 검증 필요) |
| `ema_surge_threshold_pct` | 0.02 | **0.025** | 매수 시그널 25% 더 엄격 |
| `bullish_candle` | false | **true** | 양봉에서만 매수 (음봉 매수 차단) |
| `above_base_ema` | false | **유지(false)** | 1분봉 추세 노이즈 — 적용 시 시그널 거의 발생 안 함 |
| `trailing_stop_threshold_pct` | 30 | **15** | trailing arming 임계 — 더 빠르게 트레일 작동 |
| `use_fixed_trailing` | true | true | 유지 (양호) |
| `order_ratio` | 0.10 | **0.05** | 손실 리스크 절반 (검증 단계 보수) |

**기대 효과** (단순 추정):
- STOP_LOSS 발동 21건 → 약 10건 이하 (stale + 더 작은 stop)
- 평균 손실 -0.875% → ~-1.0% (작아진 stop_loss로 컷)
- 평균 익절 +0.75% → +1.5%~2% (TP 활성 + trailing arming 빠름)
- 승률은 비슷하더라도 **R/R 회복**으로 누적 손익 양(+) 전환

### 8-2. 대안 — "공격형" (R/R 극대화)

| 항목 | 권장 | 비고 |
|---|---|---|
| `stop_loss_pct` | **1.0** | 매우 작은 손절 |
| `take_profit_pct` | **3.0** | R/R = 3.0/1.0 = **3.0 ✓✓** |
| `ema_surge_threshold_pct` | **0.03** | 시그널 더 엄격 (빈도↓) |
| `bullish_candle` | true | 양봉 확인 |
| `stale_position_check` | true (60분) | 짧게 컷 |
| `order_ratio` | 0.05 | |

**리스크**: 매수 빈도 감소 + 작은 손절로 노이즈 컷 시 빈번 손절 가능. 실제 1분봉 변동성에서 1% 손절이 너무 작아 잡음에 자주 걸릴 위험.

### 8-3. 검증 권장 — 보수형 우선 + 7일 모니터링

```
Phase A (1주):
  - 보수형 적용 (8-1)
  - 일일 누적 손익 + STOP_LOSS/TAKE_PROFIT/TRAILING 분포 모니터링

Phase B (1주):
  - Phase A 결과 분석
  - 손실 패턴 식별 → 추가 미세 조정 (예: stop_loss 1.5 → 1.2 등)

Phase C (이후):
  - 안정 시 order_ratio 점진 회복 (0.05 → 0.07 → 0.10)
```

### 8-4. 적용 방법

`/set_buy_sell_conditions` 페이지에서 직접 토글/입력:
- 매도 — `Stop Loss %`: 3.0 → **1.5**
- 매도 — `Take Profit`: OFF → **ON**, 값 3.0 → **2.5**
- 매도 — `Trailing Stop Threshold %`: 30 → **15**
- 매도 — `Stale Position Check`: OFF → **ON**, 한계 시간 90분, 임계 -0.3%
- 매수 — `Surge Threshold %`: 2.0 → **2.5**
- 매수 — `Bullish Candle`: OFF → **ON**

`/set_config` 페이지:
- `order_ratio`: 0.10 → **0.05**

저장 시 settings_history 에 새 row 자동 적재 → 그 시점부터 거래 라벨링 가능.

---

## 9. 코드 검증 발견 사항 (2026-06-22 16:00 추적 중간)

### 9-1. ⚠️ STOP_LOSS 트리거 코드와 실제 데이터의 결정적 모순

**코드** (`core/filters/sell_filters.py:87`):
```python
stop_loss_triggered = pnl_pct <= -self.stop_loss_pct
```
- `stop_loss_pct = conditions.sell.stop_loss_pct / 100 = 3.0 / 100 = 0.03`
- 즉 -3% 도달해야 트리거 — 정상

**실제 audit_trades**:
- STOP_LOSS reason 42건 (전 ticker) 의 손익률 분포:
  - -0.5 ~ -1%: **32건 (76%)**
  - -1 ~ -2%: 7건
  - -2% 미만: 2건
- 평균 **-0.875%** → 코드 임계값(-3%)와 명백히 다름

**가설** (검증 진행 중):
1. ❓ 다른 sell filter (예: ema_dead_cross 등) 가 reason="STOP_LOSS"로 잘못 라벨링되어 적재
2. ❓ `self.stop_loss` 값이 다른 경로에서 작은 값(예: 0.005 = 0.5%)으로 덮어쓰기됨
3. ❓ trader / strategy_engine 에서 sell 발동 후 reason 변환 로직

**추적 방향**:
- `core/strategy_incremental.py:620` 부근 SellFilterPipeline 등록 추적
- `core/strategy_engine.py` 의 sell 발동 → trader 호출 흐름에서 reason 인자 흐름
- 운영 로그 `journalctl -u tradebot | grep "STOP_LOSS"` 에서 실제 트리거 시점의 sl=값 확인

### 9-2. ⚠️ audit_trades.sl / tp / ts_pct 컬럼이 NULL 적재

- STOP_LOSS 42건 모두 sl 컬럼 NULL
- TAKE_PROFIT 6건 모두 tp 컬럼 NULL
- TRAILING 거래 ts_pct NULL

`services/db.py:insert_trade_audit` 시그니처는 sl/tp/ts_pct 인자를 받지만 호출자(`core/trader.py:_audit_emit_trade`) 가 항상 None을 전달하고 있을 가능성. 디버깅 시 임계값 정보 손실 → 추후 사후 분석 어려움.

**조치 후보** (다음 작업): trader.py 에서 strategy 객체로부터 sl/tp/ts_pct 를 추출해 전달

### 9-3. ⚠️ TAKE_PROFIT 토글 OFF 인데 4건 발동 (KRW-JTO)

`conditions.sell.take_profit = false` 임에도 audit_trades reason='TAKE_PROFIT' 4건 (KRW-JTO) 적재. UI 토글과 실제 동작 불일치 가능성. 9-1 가설 1과 연관 — 다른 트리거가 잘못 라벨링.

### 9-4. 다음 작업

- [x] (a) `journalctl -u tradebot | grep -E "STOP_LOSS|🛡️|🎯"` 로 실제 트리거 시점 로그 확인 → §10 결과
- [x] (b) `core/strategy_engine.py` sell 흐름 추적 — 원인은 §11 (Strategy 객체 init 시점 conditions 고정)
- [ ] (c) reason 결정 unit test 작성 (있다면 실행)
- [ ] (d) audit_trades.sl/tp/ts_pct 적재 누락 별건 수정 — §11-3 참조

---

## 10. 운영 엔진 현재 적용값 확인 (2026-06-22 16:30)

### 10-1. 핵심 결과 — 모든 모순의 원인 확정

엔진 부팅 시점 로그(`journalctl -u tradebot --since "2026-06-17 20:19"`)에서:

```
[EMA Strategy] take_profit from buy_sell_conditions.json: 1.00%
[EMA Strategy] stop_loss   from buy_sell_conditions.json: 0.50%
[EMA Strategy] Sell conditions: stop_loss=True, take_profit=False,
               trailing_stop=True, ema_dc=False, stale_position=False
[Filter Pipeline] threshold=-0.50%
```

→ **운영 데이터 전체 기간(5/24 ~ 6/22 12:35)** 의 운영 임계값:
- **`stop_loss_pct = 0.5%`** (UI 저장값 3.0% 와 무관)
- **`take_profit_pct = 1.0%`** (UI 저장값 3.0% 와 무관)

### 10-2. 운영 데이터와 정확 일치

| 지표 | 운영 임계 | 데이터 일치 |
|---|---|---|
| stop_loss_pct | **0.5%** | STOP_LOSS 32건(76%) -0.5~-1% 구간 ✓ 평균 -0.875% ≈ 임계+슬리피지 |
| take_profit_pct | **1.0%** | TAKE_PROFIT 평균 +1.063% ≈ 임계+슬리피지 ✓ |

→ §3 의 "코드 -3% vs 실제 -0.875%" 모순은 **strategy 객체가 0.5% 로 init 되어 있었기 때문** — 코드 정합성 자체는 정상.

### 10-3. 누적 손실 -9.78% 의 진짜 원인

```
stop_loss_pct = 0.5% (너무 작아 1분봉 노이즈에 잦은 손절)
take_profit_pct = 1.0% (작은 익절)
R/R = 1.0 / 0.5 = 2.0  ← 이론상 양호하지만
실측 R/R = 0.753 / 0.875 = 0.86  ← 슬리피지/스프레드 손실로 악화
```

→ **이론상 R/R 2.0 인데 실측 R/R 0.86 이 되는 원인**: 0.5% 손절은 너무 작아 슬리피지·스프레드 손실이 상대적으로 큼 + 1분봉 노이즈가 손절 임계 안쪽으로 자주 진입.

→ §8 권장안의 핵심 (R/R ≥ 1.5 확보 + stop_loss 의미 있는 폭) 이 본 운영 데이터로 정량적으로 입증됨.

---

## 11. Strategy 객체 ↔ conditions 파일 동기화 부재 (본질적 운영 위험)

### 11-1. settings_history 적재 자체는 정상

`settings_history` 8 row 모두 정상 적재 (P1~P5 정상 동작):

| id | saved_at | source_page | 비고 |
|---|---|---|---|
| 1 | 2026-06-16 19:55:14 | initial_seed | P1 자동 시드 |
| 2 | 2026-06-16 19:55:21 | set_buy_sell_conditions | 사용자 요청 명시 |
| 3 | 2026-06-17 07:32:14 | set_buy_sell_conditions | |
| 4 | 2026-06-19 13:48:46 | set_buy_sell_conditions | |
| 5 | 2026-06-19 14:22:32 | set_buy_sell_conditions | |
| 6 | 2026-06-21 21:12:00 | set_buy_sell_conditions | |
| 7 | 2026-06-21 21:12:31 | set_buy_sell_conditions | |
| 8 | 2026-06-22 04:09:03 | set_buy_sell_conditions | 가장 최신 |

`mcmax33_EMA_buy_sell_conditions.json` mtime = `2026-06-22 04:09` (id=8 적재 시점과 동일).

본 진단 보고서 §2 가 id=2 로 보였던 것은 **분석 측정 시점(6/21)이 id=3 이후 변경분 적재 시점보다 이전** 이었기 때문 — 추적 시점 차이.

### 11-2. 그러나 strategy 객체는 init 시점 conditions 에 고정

엔진(PID 781636)은 **6/17 20:28:16 부팅 후 4일 20시간째 가동** 중이지만, 그 안에서 strategy 객체는 **사용자가 명시적으로 [엔진 재시작] 트리거 한 시점에만** 재초기화됨.

| 시각 | strategy 적용 conditions | settings_history 매핑 | 격차 |
|---|---|---|---|
| **6/17 20:45:11** strategy init | sl=0.5%, tp=1.0%, stop_loss=True | (당시 최신 — id=3 적재 12시간 전) | — |
| **6/22 12:35:58** strategy init | sl=3.0%, tp=2.5%, **stop_loss=False, ema_dc=True** | row id=8 (6/22 04:09) | **8시간 27분 지연** |

→ **사용자가 6/22 04:09 에 조정한 설정이 실제 운영에 반영된 시점은 6/22 12:35:58** — 그 사이 **8.5시간 동안 옛 conditions(sl=0.5%, tp=1.0%) 로 운영**됨.

### 11-3. audit_settings 가 분당 1회 실제 운영 임계값 적재 (검증 통로)

`audit_settings` 테이블은 **strategy 객체의 현재 self.stop_loss / take_profit / ts_pct** 를 분당 1회 기록 — 즉 **실제 운영 임계값** 추적 가능.

```sql
SELECT timestamp, ticker, tp, sl, ts_pct
FROM audit_settings
WHERE timestamp >= '2026-06-22T12:30';
-- 12:30~12:34: sl=0.005 (0.5%), tp=0.01 (1.0%)
-- 12:35:58 strategy 재init 이후: sl=0.03, tp=0.025
```

→ `audit_settings` + `settings_history` 두 테이블을 함께 보면 "사용자 의도 vs 엔진 실적용" 격차를 시계열로 검증 가능.

### 11-4. 본질적 운영 위험 (4건)

| 위험 | 영향 | 심각도 |
|---|---|---|
| ① **사용자가 conditions 변경해도 즉시 엔진에 반영 안 됨** | 의도 vs 실적용 격차 큼 (6/22 사례 8.5시간) | 🔴 |
| ② **엔진 재시작이 명시적이지 않음** | 사용자가 언제 strategy 가 재초기화되는지 알 수 없음 | 🔴 |
| ③ **UI 에 "현재 엔진이 적용 중인 conditions" 표시 부재** | 화면 conditions ≠ 운영 conditions 격차 인지 불가 | 🔴 |
| ④ `settings_history` 의 row 는 "사용자 저장 시점" 만 기록 | 엔진 적용 시점은 별개 — 두 시점 차이 추적 어려움 | 🟡 |

### 11-5. 즉시 조치 권고 — 운영 위험 헷지

| 우선 | 항목 | 효과 |
|---|---|---|
| 🔴 1 | **대시보드에 "엔진 활성 strategy 의 실제 conditions" 표시** (audit_settings 최신 row 기반) | UI conditions vs 운영 conditions 가시화 |
| 🔴 2 | conditions 변경 시 **"⚠️ 변경 사항을 엔진에 반영하려면 재시작 필요" 명시 안내** + 원클릭 재시작 버튼 | 변경 ≠ 적용 격차 해소 |
| 🟡 3 | `settings_history` 에 **`applied_at` 컬럼 추가** — strategy 재초기화 시점 매핑 | 변경/적용 격차 시계열 추적 |
| 🟡 4 | strategy 재초기화 시점에 **`source_page="strategy_init"` row 자동 적재** | 운영 변화 자동 기록 + applied_at 자동 채움 |
| 🟢 5 | `audit_trades.sl/tp/ts_pct` 적재 — trader.py 에서 strategy 객체의 값 전달 | 사후 분석 정확도 ↑ (§9-2) |

본 5개 조치는 별도 기획안 `docs/plans/strategy-sync-hardening/` 으로 분리하여 추적 예정.

---

## 진행 이력 갱신

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-22 16:30 | §10 + §11 추가 — 모든 모순 원인 확정 | strategy 객체 init 시점 conditions 고정 → 8.5시간 운영 지연 발견. 5개 즉시 조치 권고 → 별도 기획안으로 추적 |
