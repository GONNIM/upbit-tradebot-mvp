# Context and Modules

> Bounded Context, 도메인 모듈, 책임 범위 정의

---

## Bounded Context Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           UPBIT TRADEBOT MVP                                │
│                                                                             │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐       │
│  │   Presentation   │    │     Trading      │    │    External      │       │
│  │     Context      │◄──►│     Context      │◄──►│     Context      │       │
│  │                  │    │                  │    │                  │       │
│  │  - Web UI        │    │  - Strategy      │    │  - Upbit API     │       │
│  │  - User Input    │    │  - Order Exec    │    │  - OpenAI API    │       │
│  │  - Visualization │    │  - Risk Mgmt     │    │                  │       │
│  └────────┬─────────┘    └────────┬─────────┘    └──────────────────┘       │
│           │                       │                                         │
│           │    ┌──────────────────┴──────────────────┐                      │
│           │    │                                     │                      │
│           ▼    ▼                                     ▼                      │
│  ┌──────────────────┐                    ┌──────────────────┐               │
│  │   User/Auth      │                    │   Persistence    │               │
│  │    Context       │                    │    Context       │               │
│  │                  │                    │                  │               │
│  │  - Login/Logout  │                    │  - SQLite DB     │               │
│  │  - Session Mgmt  │                    │  - JSON Config   │               │
│  │  - Multi-user    │                    │  - Audit Logs    │               │
│  └──────────────────┘                    └──────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Domain Modules

### Module Hierarchy

```
upbit-tradebot-mvp/
│
├── [PRESENTATION MODULE]
│   ├── app.py                    # Entry point, routing
│   ├── pages/                    # Page components
│   └── ui/                       # UI components
│
├── [TRADING MODULE]
│   ├── core/                     # Strategy, execution
│   └── engine/                   # Trading loop, state
│
├── [INFRASTRUCTURE MODULE]
│   ├── services/                 # DB, API, monitoring
│   └── utils/                    # Helpers
│
└── [CONFIGURATION MODULE]
    ├── config.py                 # Global settings
    ├── credentials.yaml          # Auth config
    └── {user}_*.json             # Per-user params
```

---

## Module Responsibilities

### 1. Presentation Module

> **책임**: 사용자 인터페이스, 입력 처리, 시각화

```
┌─────────────────────────────────────────────────────────────┐
│                   PRESENTATION MODULE                       │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   app.py    │  │   pages/    │  │        ui/          │  │
│  │             │  │             │  │                     │  │
│  │ - 로그인      │  │ - 대시보드    │  │ - 차트 렌더링          │  │
│  │ - 라우팅      │  │ - 설정       │  │ - 사이드바            │  │
│  │ - 세션 초기화  │  │ - 감사 로그   │  │ - 메트릭 카드          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| File | Responsibility | Dependencies |
|------|----------------|--------------|
| `app.py` | 앱 진입점, 인증, 모드 선택 | config, services/db, engine |
| `pages/dashboard.py` | 실시간 모니터링 UI | ui/charts, services/db |
| `pages/set_config.py` | 파라미터 설정 UI | engine/params |
| `pages/set_buy_sell_conditions.py` | 조건 설정 UI | JSON config |
| `pages/audit_viewer.py` | 감사 로그 조회 UI | services/db |
| `ui/charts.py` | Bokeh/Matplotlib 차트 | pandas, numpy |
| `ui/sidebar.py` | 네비게이션 사이드바 | streamlit |
| `ui/metrics.py` | KPI 메트릭 카드 | streamlit |
| `ui/style.py` | CSS 스타일링 | streamlit |

**Interface Contracts**:
- Input: User actions (clicks, form submissions)
- Output: Rendered HTML/charts, session state updates
- Does NOT: Execute trades, access external APIs directly

---

### 2. Trading Module

> **책임**: 트레이딩 전략, 신호 생성, 주문 실행, 엔진 관리

```
┌─────────────────────────────────────────────────────────────┐
│                     TRADING MODULE                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                      core/                          │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │    │
│  │  │ data_feed   │ │ strategy_v2 │ │   trader    │    │    │
│  │  │             │ │             │ │             │    │    │
│  │  │ - OHLCV 수집 │ │ - MACD 계산  │ │ - 주문 실행   │    │    │
│  │  │ - 캔들 관리   │ │ - 신호 생성   │ │ - TEST/LIVE │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                     engine/                         │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌────────────┐   │    │
│  │  │engine_manager│ │  live_loop   │ │   params   │   │    │
│  │  │              │ │              │ │            │   │    │
│  │  │ - 스레드 관리   │ │ - 5초 루프    │ │ - Pydantic │   │    │
│  │  │ - 시작/중지    │ │ - 상태 갱신    │ │ - 검증      │   │    │
│  │  └──────────────┘ └──────────────┘ └────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### core/ Submodule

| File | Responsibility | Input | Output |
|------|----------------|-------|--------|
| `data_feed.py` | Upbit에서 OHLCV 데이터 수집 | ticker, interval | DataFrame (OHLCV) |
| `strategy_v2.py` | MACD 전략, 매수/매도 신호 생성 | OHLCV DataFrame | BUY/SELL/HOLD signal |
| `trader.py` | 주문 실행 (TEST: DB, LIVE: API) | signal, params | order result |

#### engine/ Submodule

| File | Responsibility | Input | Output |
|------|----------------|-------|--------|
| `engine_manager.py` | 멀티유저 엔진 인스턴스 관리 | username, mode | engine thread |
| `live_loop.py` | 5초 주기 트레이딩 루프 | params | trade executions |
| `engine_runner.py` | 엔진 스레드 실행/종료 | engine instance | thread lifecycle |
| `params.py` | Pydantic 기반 파라미터 관리 | JSON/dict | validated params |
| `lock_manager.py` | 스레드 동기화 (mutex) | - | thread safety |
| `global_state.py` | 공유 상태 관리 | - | state dict |
| `order_reconciler.py` | 주문 상태 조정 | orders | reconciled state |

**Interface Contracts**:
- Input: Market data, user parameters, trigger signals
- Output: Trade executions, audit logs
- Does NOT: Render UI, handle authentication

---

### 3. Infrastructure Module

> **책임**: 데이터 영속성, 외부 API 통신, 시스템 모니터링

```
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE MODULE                      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    services/                        │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐   │    │
│  │  │   db.py  │ │upbit_api │ │  health_monitor    │   │    │
│  │  │          │ │          │ │                    │   │    │
│  │  │ - CRUD   │ │ - REST   │ │ - CPU/Memory       │   │    │
│  │  │ - SQLite │ │ - JWT    │ │ - Uptime           │   │    │
│  │  └──────────┘ └──────────┘ └────────────────────┘   │    │
│  │                                                     │    │
│  │  ┌──────────┐ ┌──────────────-┐ ┌────────────────┐  │    │
│  │  │ init_db  │ │trading_control│ │    logger      │  │    │
│  │  │          │ │               │ │                │  │    │
│  │  │ - Schema │ │ - Force Sell  │ │ - Logging      │  │    │
│  │  │ - Migrate│ │ - Force Buy   │ │ - Rotation     │  │    │
│  │  └──────────┘ └──────────────-┘ └────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                     utils/                          │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐   │    │
│  │  │logging_util │ │ smoke_test  │ │ test_logic   │   │    │
│  │  └─────────────┘ └─────────────┘ └──────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### services/ Submodule

| File | Responsibility | Dependencies |
|------|----------------|--------------|
| `db.py` | SQLite CRUD 작업, 쿼리 실행 | sqlite3 |
| `init_db.py` | DB 스키마 생성, 마이그레이션 | sqlite3 |
| `upbit_api.py` | Upbit REST API 래퍼, JWT 인증 | pyupbit, jwt |
| `health_monitor.py` | 시스템 헬스 체크 (24/7) | psutil |
| `trading_control.py` | 강제 청산/진입 명령 | trader, db |
| `logger.py` | 로깅 유틸리티 | logging |

#### utils/ Submodule

| File | Responsibility |
|------|----------------|
| `logging_util.py` | 로그 파일 관리, 로테이션 |
| `smoke_test.py` | DB 연결 테스트 |
| `test_logic.py` | TEST 모드 로직 |
| `make_credentials.py` | 인증 정보 생성 도우미 |

**Interface Contracts**:
- Input: Domain objects, API requests
- Output: Persisted data, API responses, health metrics
- Does NOT: Make trading decisions, render UI

---

### 4. Configuration Module

> **책임**: 전역 설정, 환경 변수, 사용자별 파라미터

```
┌─────────────────────────────────────────────────────────────┐
│                  CONFIGURATION MODULE                       │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  config.py  │  │credentials  │  │   User JSON Files   │  │
│  │             │  │   .yaml     │  │                     │  │
│  │ - 전역 상수   │  │             │  │ - latest_params     │  │
│  │ - 환경변수    │  │ - 사용자 목록  │  │ - buy_sell_conds    │  │
│  │ - 기본값      │  │ - 비밀번호    │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌─────────────────────────────────────┐   │
│  │    .env     │  │          .streamlit/                │   │
│  │             │  │                                     │   │
│  │ - API Keys  │  │ - config.toml (server settings)     │   │
│  │ - Secrets   │  │ - secrets.toml (cloud secrets)      │   │
│  └─────────────┘  └─────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| File | Responsibility | Access Pattern |
|------|----------------|----------------|
| `config.py` | 전역 상수, 환경변수 로딩 | Import at startup |
| `credentials.yaml` | 사용자 인증 정보 (bcrypt) | Read by streamlit-authenticator |
| `.env` | API 키, 시크릿 | Read by python-dotenv |
| `{user}_latest_params.json` | 사용자별 전략 파라미터 | Read/Write by engine/params |
| `{user}_buy_sell_conditions.json` | 사용자별 매매 조건 | Read/Write by pages |
| `.streamlit/config.toml` | Streamlit 서버 설정 | Read by Streamlit |
| `.streamlit/secrets.toml` | 클라우드 배포용 시크릿 | Read by Streamlit Cloud |

---

## Module Interaction Matrix

```
                    ┌──────────┬──────────┬──────────┬──────────┐
                    │Presentat.│ Trading  │ Infra    │ Config   │
┌───────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Presentation      │    -     │   R/W    │    R     │    R     │
├───────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Trading           │    -     │    -     │   R/W    │    R     │
├───────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Infrastructure    │    -     │    -     │    -     │    R     │
├───────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Configuration     │    -     │    -     │    -     │    -     │
└───────────────────┴──────────┴──────────┴──────────┴──────────┘

R = Read, W = Write, - = No direct dependency
```

---

## Context Boundaries

### 1. Presentation ↔ Trading Boundary

```
┌─────────────────┐          ┌─────────────────┐
│   Presentation  │          │     Trading     │
│                 │          │                 │
│  Dashboard      │─────────▶│  EngineManager  │
│  - start_engine │  Command │  - start()      │
│  - stop_engine  │          │  - stop()       │
│                 │          │                 │
│  Display        │◀─────────│  State          │
│  - position     │  Query   │  - get_status() │
│  - balance      │          │  - get_trades() │
└─────────────────┘          └─────────────────┘
```

**Boundary Rules**:
- Presentation은 Trading에 명령(Command)만 전달
- Trading 상태는 Query를 통해서만 조회
- 직접적인 Trading 로직 호출 금지

### 2. Trading ↔ Infrastructure Boundary

```
┌─────────────────┐          ┌─────────────────┐
│     Trading     │          │ Infrastructure  │
│                 │          │                 │
│  Trader         │─────────▶│  UpbitAPI       │
│  - buy()        │  API     │  - place_order()│
│  - sell()       │          │  - get_balance()│
│                 │          │                 │
│  LiveLoop       │─────────▶│  DB             │
│  - log_trade()  │  Persist │  - insert()     │
│  - get_params() │          │  - select()     │
└─────────────────┘          └─────────────────┘
```

**Boundary Rules**:
- Trading은 Infrastructure 구현 상세를 모름
- API/DB 변경 시 Trading 코드 수정 최소화
- 인터페이스 통해서만 통신

### 3. Configuration Access Pattern

```
                    ┌─────────────────┐
                    │  Configuration  │
                    │                 │
                    │  - config.py    │
                    │  - .env         │
                    │  - *.json       │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌────────────┐    ┌────────────┐    ┌────────────┐
    │Presentation│    │  Trading   │    │   Infra    │
    │            │    │            │    │            │
    │ Read-only  │    │ Read-only  │    │ Read-only  │
    └────────────┘    └────────────┘    └────────────┘
```

**Boundary Rules**:
- Configuration은 모든 모듈에서 Read-only
- 설정 변경은 Presentation을 통해서만 수행
- Runtime 설정 변경 시 JSON 파일 업데이트

---

## Data Ownership

| Data Entity | Owner Module | Storage | Access |
|-------------|--------------|---------|--------|
| User credentials | Configuration | credentials.yaml | Auth only |
| API keys | Configuration | .env | Infra only |
| Trading params | Configuration | JSON files | Trading R, Presentation R/W |
| OHLCV candles | Trading | In-memory | Trading only |
| Orders | Infrastructure | SQLite | Trading W, Presentation R |
| Audit logs | Infrastructure | SQLite | Trading W, Presentation R |
| Account balance | Infrastructure | SQLite | Trading R/W, Presentation R |
| Positions | Infrastructure | SQLite | Trading R/W, Presentation R |

---

## Anti-Corruption Layer

외부 API 변경으로부터 내부 모듈을 보호하는 레이어:

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING MODULE                           │
│                                                             │
│   core/trader.py                                            │
│   ┌────────────────────────────────────────────────────┐    │
│   │              Internal Interface                    │    │
│   │  - buy(ticker, amount)                             │    │
│   │  - sell(ticker, amount)                            │    │
│   │  - get_balance()                                   │    │
│   └────────────────────────────────────────────────────┘    │
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              ANTI-CORRUPTION LAYER                          │
│                                                             │
│   services/upbit_api.py                                     │
│   ┌────────────────────────────────────────────────────┐    │
│   │  - Upbit API 응답 변환                               │    │
│   │  - 에러 처리 및 표준화                                 │    │
│   │  - Rate limiting                                   │    │
│   │  - JWT 토큰 관리                                     │    │
│   └────────────────────────────────────────────────────┘    │
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL API                             │
│                                                             │
│   Upbit REST API (https://api.upbit.com)                    │
│   - Different response format                               │
│   - Rate limits                                             │
│   - Authentication requirements                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Communication Patterns

### 1. Synchronous (동기)

```
Presentation → Trading (엔진 시작/중지)
Trading → Infrastructure (주문 실행, DB 저장)
```

### 2. Event-Driven (이벤트 기반)

```
Trading Loop → Presentation (상태 업데이트 via session_state)
Health Monitor → Presentation (헬스 알림)
```

### 3. Polling (폴링)

```
Presentation → Trading (5초마다 상태 조회)
Trading → External API (5초마다 시세 조회)
```

---

**Last Updated**: 2025-11-22
