# 설정 History — 현장 데이터 측정 (Data Baseline)

**용도**: P1 구현 전 데이터 가설을 1회 측정하여 설계 결정의 근거를 확보.
**작성일**: 2026-06-16
**측정일**: 2026-06-16 14:30 (KST)
**상태**: ✅ 측정 완료 — 결과 §4 기록

관련: [[plan.md]] §10-2, §10-3, §10-4, §10-9

---

## 1. 측정 목표

| ID | 측정 | 좌우하는 설계 결정 |
|---|---|---|
| M4-1 | 테이블 존재 확인 | 기본 — schema spec 작성 가능 여부 |
| M4-2 | 행 수 (orders, audit_trades, audit_settings, logs) | DB 크기 추정 — ALTER 부담·뷰어 페이지네이션 정책 |
| M4-3 | 시간 범위 (orders, audit_trades) | Pre-history 거래 규모 — 뷰어 상단 표기 정책 |
| M4-4 | orders 상태 분포 (side × state) | NULL 컬럼 처리 정책, 표시 필터 후보 |
| M4-6 | audit_trades 페어링 가능성 (entry_price·bars_held NULL 비율) | D7 (PnL 지표 범위) 결정 근거 |
| M4-8 | audit_settings 활동 분포 | 사용자/전략 활동도 — record_snapshot 호출 빈도 추정 |
| M4-9 | PRAGMA table_info (실제 컬럼) | ALTER idempotent 패턴 — 컬럼 이미 존재 시 skip |

> M4-5 (orders 정합 — 백필 매핑) 와 M4-7 (orders ↔ audit_trades 매칭률) 은 **백필 미수행 결정 (2026-06-16)** 에 따라 제거됨.

---

## 2. 환경

- 서버: `ssh root@orionhunter7.cafe24.com`
- DB 경로 패턴: `/root/upbit-tradebot-mvp/data/tradebot_<user_id>.db`
- DB 파일명 규칙: `services/init_db.py:13 DB_PREFIX="tradebot"`, `services/init_db.py:17 get_db_path`

---

## 3. 측정 절차 (방식 a — ssh 직접 실행)

### Step 0. DB 파일 목록 확인

```bash
ls -la /root/upbit-tradebot-mvp/data/tradebot_*.db
```

→ 측정 대상 사용자 목록 확보.

### Step 1. 사용자별 측정 SQL 실행

대상 사용자의 DB 경로를 `$DB` 환경변수로 지정 후 아래 SQL 일괄 실행:

```bash
DB=/root/upbit-tradebot-mvp/data/tradebot_<user_id>.db     # 사용자별 실제 경로로 교체

sqlite3 -header -column "$DB" <<'SQL'
-- ============================================================
-- M4-1. 테이블 존재 확인
-- ============================================================
.tables

-- ============================================================
-- M4-2. 데이터 양 (P1 마이그레이션 부담 추정)
-- ============================================================
SELECT 'orders'         AS tbl, COUNT(*) AS rows FROM orders
UNION ALL SELECT 'audit_trades',   COUNT(*) FROM audit_trades
UNION ALL SELECT 'audit_settings', COUNT(*) FROM audit_settings
UNION ALL SELECT 'logs',           COUNT(*) FROM logs;

-- ============================================================
-- M4-3. 시간 범위 (Pre-history 규모 추정)
-- ============================================================
SELECT 'orders'       AS tbl, MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts FROM orders
UNION ALL
SELECT 'audit_trades',         MIN(timestamp),          MAX(timestamp)            FROM audit_trades;

-- ============================================================
-- M4-4. orders 상태 분포
-- ============================================================
SELECT side, state, COUNT(*) AS cnt
FROM orders
GROUP BY side, state
ORDER BY side, cnt DESC;

-- ============================================================
-- M4-6. audit_trades 페어링 가능성 (PnL 계산 기반)
-- ============================================================
SELECT
    type,
    COUNT(*) AS rows,
    SUM(CASE WHEN entry_price IS NULL THEN 1 ELSE 0 END) AS entry_price_null,
    SUM(CASE WHEN bars_held   IS NULL THEN 1 ELSE 0 END) AS bars_held_null,
    SUM(CASE WHEN price       IS NULL THEN 1 ELSE 0 END) AS price_null
FROM audit_trades
GROUP BY type;

-- ============================================================
-- M4-8. audit_settings 활동 분포 (사용자/전략 활성도)
-- ============================================================
SELECT
    ticker,
    COUNT(*) AS snapshots,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM audit_settings
GROUP BY ticker
ORDER BY snapshots DESC
LIMIT 10;

-- ============================================================
-- M4-9. PRAGMA — 실제 컬럼 (idempotent ALTER 패턴 확정 근거)
-- ============================================================
SELECT 'orders'        AS tbl, name, type, "notnull", dflt_value
FROM pragma_table_info('orders')
UNION ALL
SELECT 'audit_trades', name, type, "notnull", dflt_value
FROM pragma_table_info('audit_trades')
ORDER BY tbl, name;
SQL
```

### Step 2. (선택) 사용자 합산 요약

```bash
for DB in /root/upbit-tradebot-mvp/data/tradebot_*.db; do
    USER=$(basename "$DB" .db | sed 's/^tradebot_//')
    echo "=== $USER ==="
    sqlite3 "$DB" "SELECT 'orders', COUNT(*) FROM orders UNION ALL SELECT 'audit_trades', COUNT(*) FROM audit_trades;"
done
```

---

## 4. 측정 결과

### 4-0. 측정 대상 사용자

| user_id | DB 경로 | 크기 | 최종 활동 | 측정 대상 |
|---|---|---|---|---|
| `mcmax33` | `/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db` | 65.9 MB | 2026-06-16 14:25 | ✅ |
| `gon1972` | `…/tradebot_gon1972.db` | 180 KB | 2026-05-14 (DB 빈 상태) | ⚠️ 모든 테이블 0행 |
| `(빈 user_id)` | `…/tradebot_.db` | 1.2 MB | 2026-05-27 | 측정 제외 (legacy) |
| `default` | `…/tradebot_default.db` | 32 KB | 2026-01-28 | 측정 제외 (스켈레톤) |

**활성 사용자**: `mcmax33` 1명. 본 측정의 모든 의미 있는 결과는 mcmax33 기준.

### M4-1. 테이블 존재 확인 (mcmax33)

13개 테이블 확인. 본 작업 관련:
```
orders, audit_trades, audit_settings, logs,
audit_buy_eval, audit_sell_eval,
accounts, account_history, account_positions, position_history,
users, engine_status, thread_status, data_collection_status
```

### M4-2. 데이터 양

| 사용자 | orders | audit_trades | audit_settings | logs |
|---|---:|---:|---:|---:|
| **mcmax33** | 128 | 187 | **31,113** | 8,122 |
| gon1972 | 0 | 0 | 0 | 0 |

🔍 **관찰**: `audit_settings` 가 3.1만 행 — 엔진 봉마다 적재되는 것으로 추정. settings_history 와 역할이 완전히 다름이 데이터로 재확인 (별개 유지 결정 D8 타당).

### M4-3. 시간 범위 (mcmax33)

| 테이블 | min | max | 운영 기간 |
|---|---|---|---|
| orders | 2026-05-24T21:00:05 | 2026-06-15T12:27:16 | 약 3주 |
| audit_trades | 2026-05-24T21:00:05 | 2026-06-16T13:18:58 | 약 3주, 현재 활성 |

### M4-4. orders 상태 분포 (mcmax33)

| side | state | cnt |
|---|---|---:|
| BUY | CANCELED | 53 |
| BUY | (빈값) | 8 |
| BUY | FAILED | 4 |
| BUY | FILLED | **1** |
| SELL | FILLED | 53 |
| SELL | (빈값) | 9 |

🔍 **관찰**:
- BUY CANCELED 53건 / FILLED 1건 — 매수 미체결 비율 극도로 높음 (52/66 ≈ 79%)
- SELL FILLED 53건 — BUY FILLED 1건과 매우 불일치
- 가설: 실제 체결 추적은 `audit_trades` 가 더 정확하고, `orders.state` 는 비동기 갱신으로 일부 누락 가능
- 영향: PnL 계산은 `audit_trades` 우선. `orders.state='FILLED'` 만으로는 페어링 불가능 → §10-4 페어링 로직 검증 필요

### M4-6. audit_trades 페어링 가능성 (mcmax33)

| type | rows | entry_price_null | bars_held_null | price_null |
|---|---:|---:|---:|---:|
| BUY | 125 | 66 (53%) | **113 (90%)** | 0 |
| SELL | 62 | 0 | 0 | 0 |

🔍 **관찰**:
- SELL 행은 모든 컬럼 정상
- BUY 행의 `bars_held` 90% NULL — 매수 시점에 보유 봉 수가 의미 없으므로 NULL은 정상 (매도 시점에서 의미 있음)
- BUY 행의 `entry_price` 53% NULL — 약 절반은 매수 가격을 entry_price 컬럼에 별도 적재하지 않음
- 영향:
  - D7 (PnL 지표 범위) 재평가: 실현 손익은 **SELL 행만으로 산출 가능** (SELL.price - SELL.entry_price). BUY.entry_price NULL 비율은 PnL 계산에 영향 없음
  - 평균 보유 시간(`bars_held`)도 SELL 행 기준이라 정상 산출 가능 — D7 (b) 권장안 **유지**

### M4-8. audit_settings 활동 분포 (mcmax33, 상위 10)

| ticker | snapshots | first_seen | last_seen |
|---|---:|---|---|
| **KRW-JTO** | 9,582 | 2026-06-09 05:56 | 2026-06-16 14:25 (현재) |
| KRW-KITE | 7,621 | 2026-05-28 12:38 | 2026-06-03 14:58 |
| KRW-PENDLE | 6,658 | 2026-06-04 14:49 | 2026-06-09 05:54 |
| KRW-SUI | 4,541 | 2026-05-24 20:55 | 2026-05-28 05:54 |
| KRW-ICP | 2,146 | 2026-05-31 20:16 | 2026-06-04 14:47 |
| KRW-ONT | 290 | 2026-05-28 07:48 | 2026-05-28 12:37 |
| KRW-SEI | 161 | 2026-05-31 17:36 | 2026-05-31 20:16 |
| KRW-CHIP | 86 | 2026-05-28 06:23 | 2026-05-28 07:48 |
| KRW-KAITO | 27 | 2026-05-28 05:57 | 2026-05-28 06:23 |
| KRW-KA | 1 | 2026-05-28 05:56 | 2026-05-28 05:56 |

🔍 **관찰**: 현재 활성 티커는 KRW-JTO. ticker 전환이 종종 발생 (총 10개 ticker). settings_history 는 strategy_type 별 격리이지만 ticker 전환도 빈도가 있어 추후 ticker 단위 필터/그룹화 UI 고려할 만함.

### M4-9. PRAGMA — 실제 컬럼

#### orders (22 columns)

```
id INTEGER, user_id TEXT, timestamp TEXT(KST), ticker TEXT, side TEXT,
price REAL, volume REAL, status TEXT, current_krw INTEGER, current_coin REAL,
profit_krw INTEGER, provider_uuid TEXT, state TEXT,
executed_volume REAL, avg_price REAL, paid_fee REAL,
requested_at TEXT, executed_at TEXT, canceled_at TEXT, updated_at TEXT,
entry_bar INTEGER, meta TEXT
```

🔍 **관찰**:
- `user_id` 컬럼 존재 — 다중 사용자 대응 가능 (현재는 사용자별 DB로 분리)
- `paid_fee`, `executed_volume`, `avg_price` 존재 — PnL 계산을 위한 정확한 수수료·체결가·체결량 확보 가능
- **`settings_history_id` 컬럼 없음 → P1 ALTER 필요**

#### audit_trades (19 columns)

```
id INTEGER, timestamp TEXT(KST), bar_time TEXT, ticker TEXT, interval_sec INTEGER,
bar INTEGER, type TEXT, reason TEXT, price REAL, macd REAL, signal REAL,
entry_price REAL, entry_bar INTEGER, bars_held INTEGER,
tp REAL, sl REAL, highest REAL, ts_pct REAL, ts_armed INTEGER
```

🔍 **관찰**:
- **`user_id` 컬럼 없음** — 사용자 격리는 DB 파일 분리로만 보장
- `volume`/`paid_fee` 없음 → PnL 계산 시 `orders` 와 시각 JOIN 또는 `audit_trades.price` × 추정 수량 사용. §10-9 리스크 (volume·paid_fee 없음) 재확인됨
- **`settings_history_id` 컬럼 없음 → P1 ALTER 필요**

---

## 5. 결과 해석 가이드

측정 후 다음 항목을 plan.md / schema-spec.md 작성 시 참고.

| 결과 패턴 | 영향 |
|---|---|
| orders / audit_trades 가 모두 수십만 건 이상 | ALTER TABLE 시 락 시간 ↑ → 배포 전 DB 백업 + 새벽 시간 마이그레이션 권장 |
| audit_trades.entry_price BUY 행에서 NULL 비율 ↑ | D7 (PnL 지표) (a) 실현 손익만 — 다른 지표 부정확 가능 |
| audit_settings.snapshots / ticker 가 한 사용자에 집중 | record_snapshot 호출 빈도 추정 가능, latest_active_settings 캐시 우선순위 결정 |
| `orders` 또는 `audit_trades` 컬럼에 `settings_history_id` 가 이미 존재 | `_safe_alter` 패턴으로 무시. spec 에 idempotent 보장 명시 |
| audit_settings.first_seen 이 모든 사용자에서 매우 최근 | Pre-history 규모 작음 — 뷰어에서 "Pre-history" 영역을 단순 카운트로 처리해도 충분 |
| audit_settings.first_seen 이 오래된 사용자 다수 | Pre-history 영역에 별도 페이지/펼치기 제공 검토 |

---

## 6. 측정 결과 기반 핵심 시사점

1. **사용자 격리 정책**: `orders.user_id` 있음 / `audit_trades` 없음. 사용자별 DB 파일 분리로만 격리됨. P1 신규 `settings_history` 도 동일 패턴 — 파일 분리 격리 채택, user_id 컬럼은 보조용으로 보존.
2. **D7 (PnL 지표) 재확인**: SELL 행은 entry_price/bars_held 모두 정상. **실현 손익·평균 보유 시간 산출 가능**. D7 (b) 권장안 유지.
3. **D8 (audit_settings 별개 유지)**: audit_settings 31,113행은 봉마다 적재된 운영 자동 스냅샷. **settings_history (사용자 명시 저장)와 의미 다름** 재확인. 별개 유지.
4. **신규 리스크 발견 — orders/audit_trades 정합 어긋남**: BUY FILLED 1건 vs SELL FILLED 53건. orders.state 만으로는 페어링 부정확. PnL 계산은 audit_trades 기반 권장. plan.md §10-9 보강 필요.
5. **ALTER 부담 가벼움**: orders 128행, audit_trades 187행 — ALTER TABLE 락 시간 무시 가능 수준. 배포 부담 낮음.
6. **D10 삭제 (백필 미수행) 재확인**: Pre-history 거래 187건 (audit_trades) — UI에서 단순 카운트 라벨로 처리 가능. 별도 페이지 불필요.

## 7. 다음 단계

- [x] 측정 SQL 실행 (2026-06-16 14:30)
- [x] §4 결과 기록
- [ ] plan.md §10-9 리스크 보강 (orders.state 정합 어긋남 항목 추가) — 다음 작업
- [ ] schema-spec.md 작성 (DDL · ALTER · idempotent 패턴)
- [ ] module-contract.md 작성 (함수 시그니처 · 수명주기 · 예외)
- [ ] P1 구현 착수
