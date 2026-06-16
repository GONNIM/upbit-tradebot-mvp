# 설정 History — 모듈 API 명세 (Module Contract)

**용도**: P1 구현에 필요한 신규/확장 함수의 시그니처·반환·예외·수명주기·격리 정책 확정.
**작성일**: 2026-06-16
**상태**: 초안 — 사용자 승인 후 P1 구현 착수

관련: [[plan.md]] §5-2, §10-7, [[schema-spec.md]] §5

---

## 1. 모듈 구조

```
services/
├── db.py                          # 기존 — insert_order / insert_trade_audit 확장
├── init_db.py                     # 기존 — ensure_orders_extended_schema 옆에 settings_history 마이그레이션 추가
└── settings_history.py            # 신규 — 본 명세의 주 대상
```

---

## 2. 신규 모듈 `services/settings_history.py`

### 2-1. import 의존성

```python
import json
import logging
from pathlib import Path
from typing import Optional, Any

from services.db import get_db, now_kst
from engine.params import (
    PARAMS_JSON_FILENAME,
    CONDITIONS_JSON_FILENAME,
    load_params,
)
```

`load_conditions` 또는 동일 로직: 기존 `pages/set_buy_sell_conditions.py` 의 로드 로직을 `engine/params.py` 로 분리하거나 본 모듈 안에 내부 `_read_conditions(user_id, strategy_type)` 헬퍼로 둠 — 권장은 후자(외부 의존 최소).

### 2-2. 공개 함수

#### 2-2-1. `record_snapshot`

```python
def record_snapshot(
    user_id: str,
    source_page: str,
    strategy_type: str,
    *,
    note: Optional[str] = None,
    app_version: Optional[str] = None,
) -> int:
    """
    현 사용자/전략 설정 파일을 읽어 settings_history 에 한 행으로 적재.

    동작:
        1. params 파일과 conditions 파일을 읽어 JSON 문자열로 직렬화
            - 파일이 없으면 해당 컬럼 NULL 로 적재 (부분 저장 케이스 보호)
            - 둘 다 없으면 RecordError 발생
        2. saved_at = now_kst()
        3. app_version 미지정 시 환경에서 자동 추출 (dashboard.py 버전 문자열 — 추후 구현)
        4. INSERT INTO settings_history (...)
        5. 새 row id 반환

    Args:
        user_id: 사용자 식별자 (사용자별 DB 파일 경로 결정)
        source_page: 'set_config' | 'set_buy_sell_conditions' | 'initial_seed' | 'restore' | 'auto_pre_restore'
        strategy_type: 'MACD' | 'EMA'
        note: 임의 메모. restore/seed 시 자동 설정
        app_version: 미지정 시 자동 채움

    Returns:
        새 row 의 id

    Raises:
        RecordError: 두 파일 모두 읽기 실패 또는 DB INSERT 실패
        ValueError: source_page / strategy_type 가 화이트리스트 미준수
    """
```

#### 2-2-2. `seed_initial_snapshot`

```python
def seed_initial_snapshot(user_id: str, strategy_type: str) -> Optional[int]:
    """
    settings_history 가 비어있는 사용자/전략 조합에 대해 시드 row 1개 적재.

    동작:
        1. SELECT 1 FROM settings_history WHERE user_id=? AND strategy_type=? LIMIT 1
        2. 이미 있으면 return None (idempotent)
        3. 없으면 record_snapshot(user_id, source_page='initial_seed', strategy_type=strategy_type, note='P1 자동 시드')

    Returns:
        새 row id 또는 None (이미 존재 시)

    Raises:
        RecordError: record_snapshot 실패 시 그대로 전파
    """
```

#### 2-2-3. `get_active_settings_id`

```python
def get_active_settings_id(user_id: str, strategy_type: str) -> Optional[int]:
    """
    사용자/전략 조합의 가장 최신 settings_history.id 를 반환.

    동작:
        SELECT id FROM settings_history
        WHERE user_id=? AND strategy_type=?
        ORDER BY id DESC LIMIT 1

    Returns:
        최신 row id. settings_history 가 비어있으면 None.
    """
```

#### 2-2-4. `fetch_history`

```python
def fetch_history(
    user_id: str,
    *,
    strategy_type: Optional[str] = None,
    source_page: Optional[str] = None,
    since_ts: Optional[str] = None,    # KST ISO8601
    until_ts: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    필터 기반 시계열 조회. 뷰어 페이지에서 사용.

    Returns:
        [{
            "id": int, "user_id": str, "saved_at": str,
            "source_page": str, "strategy_type": str,
            "params_json": str | None, "conditions_json": str | None,
            "app_version": str | None, "note": str | None,
        }, ...]
        최신순 정렬 (saved_at DESC).
    """
```

#### 2-2-5. `fetch_snapshot`

```python
def fetch_snapshot(user_id: str, snapshot_id: int) -> Optional[dict]:
    """
    단일 row 상세 조회. 행 펼치기 / 복원 시 사용.

    Returns:
        dict (fetch_history 와 동일 키) 또는 None.
    """
```

#### 2-2-6. `diff_against_previous`

```python
def diff_against_previous(user_id: str, snapshot_id: int) -> dict:
    """
    직전 동일 (user_id, strategy_type) 스냅샷과 컬럼별 변경분.

    동작:
        1. 대상 row 조회
        2. 같은 (user_id, strategy_type) 에서 saved_at 가 더 이른 가장 가까운 row 조회
        3. params_json / conditions_json 키별로 비교

    Returns:
        {
            "params":     {"key": {"before": ..., "after": ...}, ...},
            "conditions": {"key": {"before": ..., "after": ...}, ...},
            "no_previous": bool,   # 직전 row 없으면 True (시드 또는 첫 row)
        }

    Raises:
        ValueError: snapshot_id 미존재
    """
```

#### 2-2-7. `restore_snapshot` (P3에서 구현)

```python
class RestoreError(Exception):
    pass

def restore_snapshot(
    snapshot_id: int,
    *,
    user_id: str,
    actor: str = "user",                    # 'user' | 'system'
    require_strategy_match: bool = True,
    require_no_open_position: bool = True,
) -> dict:
    """
    snapshot_id 의 params/conditions 를 현재 파일에 덮어쓰고
    안전 스냅샷 + 복원 이벤트 row 적재 + active_settings_id 갱신.

    동작 (§10-11-3 참고):
        ① 자동 안전 스냅샷 (source_page='auto_pre_restore')
        ② 파일 덮어쓰기 (params + conditions)
        ③ 복원 이벤트 row (source_page='restore', note=f'restored_from_id={snapshot_id}')
        ④ Telegram CRITICAL 알림
        ⑤ diff 계산 후 반환

    Returns:
        {
            "pre_snapshot_id": int,
            "restored_from_id": int,
            "new_active_id": int,
            "diff": dict,
            "warnings": list[str],
        }

    Raises:
        RestoreError:
            - snapshot_id 없음
            - require_strategy_match=True 인데 현재 활성 전략과 row.strategy_type 불일치
            - require_no_open_position=True 인데 보유 포지션 있음
            - 파일 쓰기 실패
    """
```

### 2-3. 내부 헬퍼 (Private)

```python
def _read_params_file(user_id: str, strategy_type: str) -> Optional[str]:
    """엔진 표준 파일 경로 규칙으로 params 파일을 읽어 JSON 문자열 반환."""

def _read_conditions_file(user_id: str, strategy_type: str) -> Optional[str]:
    """동일 규칙으로 conditions 파일 반환."""

def _resolve_app_version() -> Optional[str]:
    """현재 dashboard.py 의 버전 문자열을 추출 (best-effort)."""
```

---

## 3. 기존 함수 확장

### 3-1. `services/db.py:insert_order`

```python
def insert_order(
    user_id, ticker, side, price, volume, status,
    current_krw=None, current_coin=None, profit_krw=None,
    *,
    provider_uuid: str | None = None,
    state: str | None = None,
    requested_at: str | None = None,
    executed_at: str | None = None,
    canceled_at: str | None = None,
    executed_volume: float | None = None,
    avg_price: float | None = None,
    paid_fee: float | None = None,
    entry_bar: int | None = None,
    meta: str | None = None,
    settings_history_id: int | None = None,   # ✅ 신규
):
    ...
    INSERT INTO orders (
        user_id, timestamp, ticker, side, price, volume, status,
        current_krw, current_coin, profit_krw,
        provider_uuid, state, requested_at, executed_at, canceled_at,
        executed_volume, avg_price, paid_fee, updated_at, entry_bar, meta,
        settings_history_id                                            -- ✅ 신규
    ) VALUES (..., ?)
```

기존 호출부는 인자 미지정 → NULL 자동 채움. 호환성 보장.

### 3-2. `services/db.py:insert_trade_audit`

```python
def insert_trade_audit(
    user_id: str, ticker: str, interval_sec: int, bar: int,
    kind: str, reason: str, price: float, macd: float, signal: float,
    entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed,
    timestamp: str | None = None,
    bar_time: str | None = None,
    settings_history_id: int | None = None,   # ✅ 신규
):
    ...
    INSERT INTO audit_trades
    (timestamp, bar_time, ticker, interval_sec, bar, type, reason, price, macd, signal,
     entry_price, entry_bar, bars_held, tp, sl, highest, ts_pct, ts_armed,
     settings_history_id)                                              -- ✅ 신규
    VALUES (?, ?, ..., ?)
```

### 3-3. `services/init_db.py` — `ensure_settings_history_schema(user_id)` 신규

schema-spec.md §5 의 시퀀스 그대로 구현. `ensure_schema` 가 본 함수를 마지막으로 호출.

---

## 4. `active_settings_id` 수명주기

### 4-1. 단일 source of truth

**`settings_history` 테이블의 가장 최신 row id = active.**
별도 캐시 테이블 / 메모리 캐시 불요.

### 4-2. 거래 INSERT 시 라벨링 흐름

```
[BUY/SELL 발생] (engine/live_loop.py 또는 core/strategy_engine.py)
    │
    ├─ active_id = get_active_settings_id(user_id, strategy_type)
    │     # 인덱스 idx_settings_history_user_strategy_saved 사용 — <1ms
    │
    ├─ insert_order(..., settings_history_id=active_id)
    └─ insert_trade_audit(..., settings_history_id=active_id)
```

### 4-3. record_snapshot 후 엔진 통지

별도 통지 채널 **불요**.
- 다음 BUY/SELL 발생 시 `get_active_settings_id` 가 자연스럽게 최신 row id 반환
- 사용자가 설정 저장 → 즉시 거래가 발생하지 않으므로 latency 무시 가능

### 4-4. 엔진 시작 시 시드 보장

```
[engine start] (engine/live_loop.py 의 초기화 루틴)
    │
    ├─ ensure_schema(user_id)                              # 기존 호출 — settings_history 스키마 보장
    └─ seed_initial_snapshot(user_id, strategy_type)       # 신규 — idempotent
```

---

## 5. 예외 정책

| 예외 | 발생 위치 | UI 노출 | 로깅 |
|---|---|---|---|
| `RecordError` | record_snapshot 실패 | 사용자에게 토스트 ("설정 저장은 완료되었으나 History 적재 실패") — 단, 파일 저장은 이미 성공 | ERROR + Telegram CRITICAL |
| `RestoreError` | restore_snapshot 실패 | 사용자에게 다이얼로그 명시 ("복원 실패: ...") | ERROR + Telegram CRITICAL |
| `ValueError` (입력 검증) | record_snapshot / restore_snapshot 호출부 | 즉시 차단 | ERROR (개발 오류 가정) |
| SQLite OperationalError | 일시적 락 | 1회 재시도 (busy_timeout 3000ms 의존) | WARNING |

**중요 원칙**: settings_history 적재 실패가 **사용자 설정 저장 자체를 막아서는 안 된다**. 파일 저장은 별도 트랜잭션. 적재 실패 시 ERROR 로깅 + 사용자 토스트 + Telegram 알림으로 끝.

---

## 6. 호출 사이트 변경

### 6-1. P1 (기반)

| 파일:라인 | 변경 |
|---|---|
| `services/db.py:106` `insert_order` | 시그니처에 `settings_history_id` kwarg 추가, INSERT VALUES 확장 |
| `services/db.py:1081` `insert_trade_audit` | 동일 |
| `services/init_db.py` | `ensure_settings_history_schema` 신규 함수, `ensure_schema` 에서 호출 |
| `services/db.py:20` `ensure_schema` | `ensure_settings_history_schema(user_id)` 추가 |
| `pages/set_config.py:283` | `save_params(...)` 직후 `record_snapshot(user_id, "set_config", selected_strategy_type)` |
| `pages/set_buy_sell_conditions.py:710` | `save_conditions()` 직후 `record_snapshot(user_id, "set_buy_sell_conditions", strategy_tag)` |
| `engine/live_loop.py` 또는 `core/strategy_engine.py` | (a) 엔진 시작 루틴에 `seed_initial_snapshot` 호출, (b) BUY/SELL INSERT 직전 `get_active_settings_id` 조회 → `insert_order/insert_trade_audit` 인자 전달 |
| `pages/dashboard.py` | 버전 갱신 |

엔진 측 BUY/SELL INSERT 호출 위치는 `core/trader.py` 의 `buy_market`/`buy_limit`/`sell_market` 안의 `insert_order` / `insert_trade_audit` 호출부 가능성 큼 → 구현 시점에 정확 위치 grep 결과로 확정.

### 6-2. P2 (뷰어 기본)

| 파일 | 변경 |
|---|---|
| `pages/settings_history.py` | 신규 — `fetch_history`, `fetch_snapshot`, `diff_against_previous` 사용 |
| `pages/dashboard.py` | 진입 버튼 추가 + 버전 갱신 |

### 6-3. P3 (복원)

| 파일 | 변경 |
|---|---|
| `services/settings_history.py` | `restore_snapshot` + `RestoreError` 추가 |
| `pages/settings_history.py` | 복원 버튼 + 다이얼로그 + diff 미리보기 |
| `pages/dashboard.py` | 버전 갱신 |

---

## 7. 격리 / 동시성

### 7-1. 사용자 격리

- 사용자별 DB 파일로 보장 (audit_trades에 user_id 컬럼 없는 패턴 그대로)
- `settings_history` 에는 user_id 컬럼 보유 (단일 DB 통합 시 보조)
- 모든 함수 시그니처에 user_id 첫 인자 — 함수가 어떤 사용자 DB에 접근할지 명시

### 7-2. 동시성

- SQLite WAL 모드 (`PRAGMA journal_mode=WAL`) 이미 활성 (services/db.py:39)
- `busy_timeout=3000` (services/db.py:41) 으로 락 대기 보장
- 추가 락 불요. 다만 record_snapshot 과 동시에 INSERT 발생 시:
  - record_snapshot 의 INSERT 완료 후 신규 거래의 `get_active_settings_id` 가 최신 row 반환
  - 가장 빠른 BUY/SELL 이 record_snapshot 보다 microseconds 앞서면 이전 active_id 적재 — 무시 가능 (운영상 의미 없음)

---

## 8. 테스트 시나리오 (구현 시점)

| ID | 시나리오 | 검증 항목 |
|---|---|---|
| T1 | 빈 DB 에 ensure_schema 호출 | 테이블·인덱스·컬럼 생성됨 |
| T2 | T1 후 재호출 | 변경 없음 (idempotent) |
| T3 | record_snapshot — params 파일만 존재 | row 적재, conditions_json NULL |
| T4 | record_snapshot — 두 파일 모두 없음 | RecordError 발생 |
| T5 | seed_initial_snapshot — 빈 settings_history | row 1개 적재, id 반환 |
| T6 | T5 후 재호출 | None 반환 (idempotent), 추가 row 없음 |
| T7 | get_active_settings_id — 빈 settings_history | None 반환 |
| T8 | record_snapshot 후 BUY 발생 | orders.settings_history_id == 최신 row id |
| T9 | fetch_history 필터 (strategy_type=EMA) | EMA row 만 반환 |
| T10 | diff_against_previous — 직전 row 없음 | no_previous=True |
| T11 | diff_against_previous — 한 키 변경 | params 또는 conditions 에 해당 키 변경 표기 |
| T12 (P3) | restore_snapshot — 정상 케이스 | pre/restore row 2개 적재, 파일 덮어쓰기 확인 |
| T13 (P3) | restore_snapshot — 활성 포지션 보유 + require=True | RestoreError |

---

## 9. 결정 필요 항목 (DM1~DM3)

| # | 항목 | 옵션 | 추천 |
|---|---|---|---|
| DM1 | active_settings_id 조회 방식 | (a) 매 INSERT 직전 DB SELECT / (b) 엔진 메모리 캐시 / (c) latest_active_settings 테이블 | **(a)** — 단순/충분 (인덱스 < 1ms, 거래 빈도 분당 1건 미만) |
| DM2 | record_snapshot 실패 시 거동 | (i) 사용자 저장 실패 처리 / (ii) 파일 저장은 성공, 적재 실패만 토스트+로그+Telegram | **(ii)** — 사용자 영향 최소 |
| DM3 | `_resolve_app_version()` 구현 | (a) dashboard.py 파일을 정규식으로 파싱 / (b) 환경변수 / (c) 설정 파일 / (d) 미구현 (NULL) | **(a) best-effort, 실패 시 NULL** — 운영 부담 ↓ |

---

## 10. 진행 이력

| 일시 | 단계 | 비고 |
|---|---|---|
| 2026-06-16 15:05 | 초안 작성 | schema-spec.md / data-baseline.md 측정 결과 반영. INSERT 함수명 확인 (insert_order, insert_trade_audit) |
