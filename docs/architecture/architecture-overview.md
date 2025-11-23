# Architecture Overview

> Upbit TradeBot MVP 시스템 아키텍처 개요

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Streamlit Web Dashboard                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │    │
│  │  │ Login    │  │Dashboard │  │Set Config│  │  Audit Viewer    │     │    │
│  │  │ (app.py) │  │          │  │          │  │                  │     │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                           pages/ + ui/ + config.py                          │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ENGINE LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Engine Manager                                  │    │
│  │                  (engine/engine_manager.py)                         │    │
│  │         ┌────────────────────────────────────────┐                  │    │
│  │         │  Per-User Trading Thread Instance      │                  │    │
│  │         │  - Start / Stop / Restart              │                  │    │
│  │         │  - TEST / LIVE mode separation         │                  │    │
│  │         └────────────────────────────────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│  ┌─────────────────────────────────┼───────────────────────────────────┐    │
│  │              Live Trading Loop (engine/live_loop.py)                │    │
│  │                         [5-second cycle]                            │    │
│  │                                                                     │    │
│  │    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │    │
│  │    │ 1. Fetch │───▶│2. Calc   │───▶│3. Signal │───▶│4. Execute│     │    │
│  │    │   OHLCV  │    │  MACD    │    │  Eval    │    │  Order   │     │    │
│  │    └──────────┘    └──────────┘    └──────────┘    └──────────┘     │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│      CORE LAYER      │ │  SERVICE LAYER   │ │   EXTERNAL APIS      │
│                      │ │                  │ │                      │
│  ┌────────────────┐  │ │ ┌──────────────┐ │ │  ┌────────────────┐  │
│  │  data_feed.py  │  │ │ │    db.py     │ │ │  │   Upbit API    │  │
│  │  - OHLCV 수집   │  │ │ │  - SQLite    │ │ │  │  (pyupbit)     │  │
│  │  - 캔들 스트리밍  │  │ │ │  - Per-user  │ │ │  │                │  │
│  └────────────────┘  │ │ └──────────────┘ │ │  │  - 시세 조회     │  │
│                      │ │                  │ │  │  - 주문 실행     │  │
│  ┌────────────────┐  │ │ ┌──────────────┐ │ │  │  - 잔고 조회     │  │
│  │ strategy_v2.py │  │ │ │ upbit_api.py │ │ │  └────────────────┘  │
│  │  - MACD 전략    │  │ │ │  - API 래퍼   │ │ │                      │
│  │  - 매수/매도     │  │ │ │  - JWT 인증   │ │ │  ┌────────────────┐  │
│  │    신호 생성     │  │ │ └──────────────┘ │ │  │  OpenAI API    │  │
│  └────────────────┘  │ │                  │ │  │  (선택사항)      │  │
│                      │ │ ┌──────────────┐ │ │  └────────────────┘  │
│  ┌────────────────┐  │ │ │health_monitor│ │ │                      │
│  │   trader.py    │  │ │ │  - 24/7 감시  │ │ └──────────────────────┘
│  │  - TEST 모드    │  │ │ │  - 메모리/CPU  │ │
│  │  - LIVE 모드    │  │ │ └──────────────┘ │
│  │  - 주문 실행     │  │ │                  │
│  └────────────────┘  │ └──────────────────┘
└──────────────────────┘

                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA STORAGE                                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                SQLite Database (per-user)                           │   │
│   │                services/data/tradebot_{username}.db                 │   │
│   │                                                                     │   │
│   │   ┌─────────┐ ┌─────────┐ ┌──────────────┐ ┌─────────────────────┐  │   │
│   │   │  users  │ │ account │ │coin_position │ │       orders        │  │   │
│   │   └─────────┘ └─────────┘ └──────────────┘ └─────────────────────┘  │   │
│   │                                                                     │   │
│   │   ┌─────────┐ ┌──────────┐ ┌─────────────┐                          │   │
│   │   │buy_eval │ │sell_eval │ │ trade_audit │                          │   │
│   │   └─────────┘ └──────────┘ └─────────────┘                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     JSON Config Files                               │   │
│   │   {user}_latest_params.json    {user}_buy_sell_conditions.json      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Overview

### 1. User Interface Layer

| Component | File | Description |
|-----------|------|-------------|
| **Main Entry** | `app.py` | 로그인, 모드 선택, 초기 설정 |
| **Dashboard** | `pages/dashboard.py` | 실시간 포지션/수익률 모니터링 |
| **Set Config** | `pages/set_config.py` | 전략 파라미터 조정 |
| **Conditions** | `pages/set_buy_sell_conditions.py` | 매수/매도 조건 설정 |
| **Audit Viewer** | `pages/audit_viewer.py` | 거래 감사 로그 조회 |
| **UI Components** | `ui/` | 차트, 사이드바, 메트릭 카드 |

### 2. Engine Layer

| Component | File | Description |
|-----------|------|-------------|
| **Engine Manager** | `engine/engine_manager.py` | 멀티유저 엔진 인스턴스 관리 |
| **Live Loop** | `engine/live_loop.py` | 5초 주기 트레이딩 루프 |
| **Engine Runner** | `engine/engine_runner.py` | 엔진 스레드 실행 |
| **Params** | `engine/params.py` | Pydantic 기반 파라미터 관리 |
| **Lock Manager** | `engine/lock_manager.py` | 스레드 동기화 |
| **Global State** | `engine/global_state.py` | 공유 상태 관리 |

### 3. Core Layer

| Component | File | Description |
|-----------|------|-------------|
| **Data Feed** | `core/data_feed.py` | Upbit OHLCV 데이터 수집 |
| **Strategy** | `core/strategy_v2.py` | MACD 기반 트레이딩 전략 |
| **Trader** | `core/trader.py` | 주문 실행 엔진 (TEST/LIVE) |

### 4. Service Layer

| Component | File | Description |
|-----------|------|-------------|
| **Database** | `services/db.py` | SQLite CRUD 작업 |
| **Init DB** | `services/init_db.py` | 스키마 초기화 |
| **Upbit API** | `services/upbit_api.py` | Upbit REST API 래퍼 |
| **Health Monitor** | `services/health_monitor.py` | 시스템 헬스 체크 |
| **Trading Control** | `services/trading_control.py` | 강제 청산/진입 명령 |

---

## Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Upbit API   │────▶│  Data Feed   │────▶│   Strategy   │────▶│    Trader    │
│  (시세 조회)   │     │  (OHLCV)     │     │  (신호 생성)   │     │  (주문 실행)    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                     │                    │
                            ▼                     ▼                    ▼
                     ┌──────────────────────────────────────────────────────┐
                     │                    SQLite DB                         │
                     │  - 캔들 데이터 캐시   - 매수/매도 신호 로그                  │
                     │  - 주문 내역          - 감사 로그                        │
                     └──────────────────────────────────────────────────────┘
                                              │
                                              ▼
                     ┌──────────────────────────────────────────────────────┐
                     │                   Dashboard                          │
                     │  - 실시간 포지션     - 수익률 차트                         │
                     │  - 거래 내역         - 감사 로그 뷰어                     │
                     └──────────────────────────────────────────────────────┘
```

---

## Trading Loop Sequence

```
[Every 5 seconds]
        │
        ▼
┌───────────────────┐
│ 1. Fetch OHLCV    │  ← Upbit API (pyupbit.get_ohlcv)
│    from Upbit     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 2. Calculate      │  ← EMA(12), EMA(26), Signal(9)
│    MACD/Signal    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 3. Evaluate       │  ← Check buy/sell conditions
│    Signals        │     - Golden Cross?
│                   │     - TP/SL reached?
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 4. Execute Order  │  ← TEST: Virtual DB update
│    (if condition) │     LIVE: pyupbit.Upbit.buy/sell
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 5. Log Audit      │  ← buy_eval, sell_eval, trade_audit
│    & Update DB    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 6. Update UI      │  ← Streamlit session state
│    Dashboard      │
└───────────────────┘
```

---

## Multi-User Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Engine Manager                          │
│                                                             │
│   ┌─────────────────┐  ┌─────────────────┐                  │
│   │  User A Thread  │  │  User B Thread  │  ...             │
│   │  ┌───────────┐  │  │  ┌───────────┐  │                  │
│   │  │Live Loop  │  │  │  │Live Loop  │  │                  │
│   │  │ - Params  │  │  │  │ - Params  │  │                  │
│   │  │ - State   │  │  │  │ - State   │  │                  │
│   │  └───────────┘  │  │  └───────────┘  │                  │
│   └────────┬────────┘  └────────┬────────┘                  │
│            │                    │                           │
└────────────┼────────────────────┼───────────────────────────┘
             │                    │
             ▼                    ▼
    ┌────────────────┐   ┌────────────────┐
    │ tradebot_A.db  │   │ tradebot_B.db  │
    │ A_params.json  │   │ B_params.json  │
    └────────────────┘   └────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite per user** | 데이터 격리, 단순한 백업/복원, 스케일 제한 수용 |
| **5-second loop** | Upbit API rate limit 고려, 충분한 반응 속도 |
| **Thread per user** | 사용자별 독립 실행, 장애 격리 |
| **JSON params** | 빠른 설정 변경, 파일 기반 버전 관리 |
| **TEST/LIVE 분리** | 안전한 전략 검증 후 실거래 전환 |

---

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                               │
│  Streamlit 1.46.0 │ Bokeh 3.7.3 │ Matplotlib 3.10.7         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND                                │
│  Python 3.11+ │ pandas 2.3.0 │ numpy 2.3.1 │ Pydantic       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      DATA LAYER                             │
│  SQLite │ JSON Files │ In-memory State                      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                        │
│  Upbit API (pyupbit 0.2.34) │ OpenAI API (optional)         │
└─────────────────────────────────────────────────────────────┘
```

---

## File Dependencies

```
app.py
├── config.py
├── credentials.yaml
├── services/db.py
│   └── services/init_db.py
├── services/upbit_api.py
├── engine/engine_manager.py
│   ├── engine/live_loop.py
│   │   ├── core/data_feed.py
│   │   ├── core/strategy_v2.py
│   │   └── core/trader.py
│   ├── engine/params.py
│   └── engine/lock_manager.py
├── pages/
│   ├── dashboard.py
│   ├── set_config.py
│   └── audit_viewer.py
└── ui/
    ├── charts.py
    ├── sidebar.py
    └── metrics.py
```

---

**Last Updated**: 2025-11-22
