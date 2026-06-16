# 설정 History — DB 스키마 명세 (Schema Spec)

**용도**: P1 마이그레이션의 정확한 DDL/ALTER, idempotent 보장 방식, 적용 순서, 롤백 절차 확정.
**작성일**: 2026-06-16
**상태**: 초안 — 사용자 승인 후 P1 구현 착수

관련: [[plan.md]] §5-1, §10-7, §10-9, [[data-baseline.md]] §4-9, §6-5

---

## 1. 적용 범위

- 적용 대상: 사용자별 SQLite DB 파일 (`/root/upbit-tradebot-mvp/services/data/tradebot_<user_id>.db`)
- 현장 측정 결과 (data-baseline.md §4-2):
  - mcmax33: orders 128행, audit_trades 187행 → ALTER 락 시간 무시 가능
  - gon1972: 모든 테이블 0행 → 영향 없음
- 사용자 격리: DB 파일 분리로 보장 (audit_trades에 user_id 없음 확인됨)

---

## 2. 신규 테이블 — `settings_history`

### 2-1. DDL

```sql
CREATE TABLE IF NOT EXISTS settings_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    saved_at        TEXT    NOT NULL,                         -- KST ISO8601 (예: '2026-06-16T14:30:00+09:00')
    source_page     TEXT    NOT NULL,                         -- 'set_config' | 'set_buy_sell_conditions' | 'initial_seed' | 'restore' | 'auto_pre_restore'
    strategy_type   TEXT    NOT NULL,                         -- 'MACD' | 'EMA'
    params_json     TEXT,                                     -- LiveParams snapshot (NULL 허용 — 부분 저장 케이스 보호)
    conditions_json TEXT,                                     -- buy/sell conditions snapshot (NULL 허용)
    app_version     TEXT,                                     -- 'v1.YYYY.MM.DD.HHMM'
    note            TEXT,                                     -- 메모/태그 (NULL 허용)
    CHECK (source_page IN (
        'set_config', 'set_buy_sell_conditions',
        'initial_seed', 'restore', 'auto_pre_restore'
    )),
    CHECK (strategy_type IN ('MACD', 'EMA'))
);
```

### 2-2. 인덱스

```sql
-- 시계열 조회용 (뷰어 메인 쿼리)
CREATE INDEX IF NOT EXISTS idx_settings_history_user_saved
    ON settings_history(user_id, saved_at DESC);

-- 전략별 필터 (뷰어 필터바)
CREATE INDEX IF NOT EXISTS idx_settings_history_user_strategy_saved
    ON settings_history(user_id, strategy_type, saved_at DESC);

-- source_page 필터
CREATE INDEX IF NOT EXISTS idx_settings_history_source_page
    ON settings_history(source_page);
```

### 2-3. 설계 결정 근거

| 컬럼 | 결정 | 근거 |
|---|---|---|
| `id INTEGER PRIMARY KEY AUTOINCREMENT` | 명시적 AUTOINCREMENT | row 재사용 차단 — 복원/감사 추적의 id 변동 방지 |
| `user_id TEXT NOT NULL` | 컬럼 보유 (DB 분리 상태이지만) | 향후 단일 DB 통합 시 보조용, audit_viewer 패턴과 일관 |
| `saved_at TEXT (ISO8601)` | TEXT 저장 | 기존 `orders.timestamp`/`audit_trades.timestamp` 와 동일 패턴 (init_db.py 참조). 정렬·범위 쿼리 가능 |
| `source_page` CHECK 제약 | 화이트리스트 | 잘못된 값 적재 방지. 추후 새 값 추가 시 마이그레이션 필요 |
| `params_json` / `conditions_json` NULL 허용 | NULL 허용 | 부분 저장(예: set_config 만 호출되어 conditions 파일 미변경 시) 케이스 보호 |
| `app_version` | TEXT | dashboard.py 버전 문자열 그대로 (`v1.YYYY.MM.DD.HHMM`) |
| `note` | TEXT NULL | 복원 시 `note="restored_from_id=N"`, 시드 시 `note="P1 자동 시드"` 등 |
| `strategy_type` CHECK | MACD/EMA 한정 | 현재 코드의 화이트리스트와 일치 (config 참조) |

### 2-4. FK / DELETE 정책

- `orders.settings_history_id` / `audit_trades.settings_history_id` 에 **FK 제약을 명시하지 않음**
- 근거: 기존 `orders`/`audit_trades` 도 FK 없는 패턴 유지 (init_db.py 확인됨). 단순성·마이그레이션 부담 최소화.
- `settings_history` row 는 **영구 보관**(D5 결정: 무제한). DELETE 시나리오 없음.

---

## 3. ALTER — 기존 테이블 컬럼 추가

### 3-1. `orders.settings_history_id`

```sql
ALTER TABLE orders ADD COLUMN settings_history_id INTEGER NULL;
CREATE INDEX IF NOT EXISTS idx_orders_settings_history_id
    ON orders(settings_history_id);
```

### 3-2. `audit_trades.settings_history_id`

```sql
ALTER TABLE audit_trades ADD COLUMN settings_history_id INTEGER NULL;
CREATE INDEX IF NOT EXISTS idx_audit_trades_settings_history_id
    ON audit_trades(settings_history_id);
```

### 3-3. NULL 정책

- 두 컬럼 모두 `NULL 허용`
- Pre-history 거래(P1 이전): NULL
- P1 이후 신규 거래: 엔진 메모리의 `active_settings_id` 값 적재. 엔진이 active_id를 확보하지 못한 일시적 상태에서는 NULL 허용 → 시드 스냅샷 도입으로 거의 발생하지 않음

---

## 4. idempotent 보장 패턴

### 4-1. CREATE TABLE / CREATE INDEX

`IF NOT EXISTS` 사용. 재실행 시 무동작.

### 4-2. ALTER TABLE

SQLite는 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 미지원. 따라서 기존 `_safe_alter` 패턴(services/init_db.py:383) 활용:

```python
def _safe_alter(conn, sql: str):
    try:
        conn.execute(sql)
    except Exception:
        # 이미 존재/타입불일치 등은 조용히 무시 (idempotent)
        pass
```

또는 명시적 점검 (권장 — 로그 가능):

```python
def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def _ensure_column(conn, table: str, column: str, ddl_type: str):
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
        logger.info(f"[migrate] added {table}.{column}")
    else:
        logger.debug(f"[migrate] skip {table}.{column} (already exists)")
```

P1 마이그레이션은 **명시적 점검 방식 권장** (로그가 남아 추적 가능).

---

## 5. 마이그레이션 시퀀스

`services/db.py` 의 `ensure_schema(user_id)` 함수 확장. 호출 순서:

```python
def ensure_schema(user_id: str):
    ensure_orders_extended_schema(user_id)       # 기존
    ensure_accounts_locked(user_id)              # 기존
    ensure_account_positions_locked(user_id)     # 기존
    ensure_account_positions_entry_price(user_id)# 기존
    ensure_engine_status_last_mode(user_id)      # 기존
    # ✅ 신규 추가
    ensure_settings_history_schema(user_id)      # P1
```

`ensure_settings_history_schema(user_id)` 내부:

```
1. settings_history 테이블 CREATE IF NOT EXISTS
2. 인덱스 3종 CREATE IF NOT EXISTS
3. orders.settings_history_id _ensure_column
4. idx_orders_settings_history_id CREATE IF NOT EXISTS
5. audit_trades.settings_history_id _ensure_column
6. idx_audit_trades_settings_history_id CREATE IF NOT EXISTS
```

각 단계는 트랜잭션 단위 분리 (실패 시 다음 단계 진행 가능 — idempotent 재실행으로 복구).

---

## 6. 호환성 영향

| 영역 | 영향 | 대응 |
|---|---|---|
| `INSERT INTO orders (...)` 기존 호출부 | 새 컬럼 미지정 → NULL 자동 채움 | 코드 변경 없이 호환. 신규 INSERT 경로만 settings_history_id 추가 |
| `INSERT INTO audit_trades (...)` 기존 호출부 | 동일 | 동일 |
| `SELECT * FROM orders` 기존 호출부 | 컬럼 1개 추가 | 컬럼 위치 명시한 SELECT 확인 필요. `SELECT *` 사용 위치 점검 |
| 기존 BI/스크립트 | 컬럼 추가는 호환 | 영향 없음 |

`SELECT * FROM orders` 사용 위치 사전 grep 필요 → module-contract.md 의 영향 분석에 포함.

---

## 7. 롤백 절차

P1 마이그레이션 후 문제 발생 시 단계별 롤백:

### 7-1. 가벼운 롤백 (코드 호출 차단만)
- `services/db.py` ensure_settings_history_schema 호출 제거
- `record_snapshot` 호출 제거
- 신규 컬럼 / 테이블 그대로 둠 (NULL로 남음)

### 7-2. 깊은 롤백 (스키마 제거)
SQLite는 컬럼 DROP을 직접 지원하지 않음. 절차:

```sql
-- 1. DB 백업
.backup '/root/backup/tradebot_<user_id>_pre_p1_rollback.db'

-- 2. orders 재구성 (settings_history_id 제거)
CREATE TABLE orders_new AS SELECT
    id, user_id, timestamp, ticker, side, price, volume, status,
    current_krw, current_coin, profit_krw, provider_uuid, state,
    executed_volume, avg_price, paid_fee,
    requested_at, executed_at, canceled_at, updated_at, entry_bar, meta
FROM orders;
DROP TABLE orders;
ALTER TABLE orders_new RENAME TO orders;
-- 인덱스 재생성 (기존 인덱스 정의 적용)

-- 3. audit_trades 동일 절차
-- 4. settings_history 테이블 DROP
DROP TABLE settings_history;
```

### 7-3. 권장
- P1 배포 직전 DB 파일 백업 (`cp tradebot_<user_id>.db tradebot_<user_id>.db.pre_p1`)
- 깊은 롤백 필요 시 백업 파일로 swap (가장 안전·빠름)

---

## 8. 검증 SQL (P1 배포 직후)

```sql
-- 1. 테이블·컬럼 생성 확인
SELECT name FROM sqlite_master WHERE type='table' AND name='settings_history';
SELECT name FROM pragma_table_info('orders') WHERE name='settings_history_id';
SELECT name FROM pragma_table_info('audit_trades') WHERE name='settings_history_id';

-- 2. 인덱스 확인
SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%settings_history%';

-- 3. 시드 스냅샷 적재 확인 (P1 마이그레이션 후 첫 엔진 시작 후)
SELECT id, user_id, saved_at, source_page, strategy_type
FROM settings_history
WHERE source_page='initial_seed';

-- 4. 신규 거래의 라벨링 확인 (활동 발생 후)
SELECT COUNT(*) AS labeled, SUM(CASE WHEN settings_history_id IS NULL THEN 1 ELSE 0 END) AS nulls
FROM orders WHERE timestamp >= '<P1 배포 시각>';
```

---

## 9. 결정 필요 항목 (DS1~DS3)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| DS1 | source_page CHECK 제약 | (a) 적용 (잘못된 값 적재 차단) / (b) 미적용 (유연성) | **(a)** |
| DS2 | strategy_type CHECK 제약 | (a) MACD/EMA 한정 / (b) 미적용 | **(a)** |
| DS3 | `_ensure_column` 적용 방식 | (a) 명시적 점검+로그 / (b) 기존 `_safe_alter` 그대로 | **(a)** — 추적성 |

---

## 10. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-16 14:50 | 초안 작성 | data-baseline.md 측정 결과 반영 |
