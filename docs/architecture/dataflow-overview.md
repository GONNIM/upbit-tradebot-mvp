# Dataflow Overview

> 주요 시나리오별 데이터 흐름 정리

---

## End-to-End Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Upbit API  │────▶│  Data Feed   │────▶│   Strategy   │────▶│    Trader    │
│              │     │              │     │              │     │              │
│  pyupbit.    │     │ stream_      │     │ MACDStrategy │     │ UpbitTrader  │
│  get_ohlcv() │     │ candles()    │     │  .next()     │     │  .buy/sell   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │                    │
       │                    ▼                    ▼                    ▼
       │             ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
       │             │  DataFrame   │     │  Signal      │     │   Orders     │
       │             │  (OHLCV)     │     │  Events      │     │   Table      │
       │             └──────────────┘     └──────────────┘     └──────────────┘
       │                                                              │
       │                                                              ▼
       │                                                       ┌──────────────┐
       │                                                       │   Streamlit  │
       │                                                       │   Dashboard  │
       └──────────────────────────────────────────────────────▶│              │
                                                               └──────────────┘
```

---

## 1. Upbit API → Data Feed

### API 호출

```python
# core/data_feed.py
pyupbit.get_ohlcv(ticker, interval=interval, count=max_length, to=to_param)
```

### 수신 데이터 (Raw)

| Column | Type | Description |
|--------|------|-------------|
| `open` | float | 시가 |
| `high` | float | 고가 |
| `low` | float | 저가 |
| `close` | float | 종가 |
| `volume` | float | 거래량 |
| `value` | float | 거래대금 (제거됨) |
| index | datetime | 캔들 시작 시각 (UTC) |

### Data Feed 가공 (`stream_candles`)

```
┌─────────────────────────────────────────────────────────────┐
│                    standardize_ohlcv()                      │
│                                                             │
│  1. 컬럼명 정규화                                              │
│     open → Open, high → High, low → Low                     │
│     close → Close, volume → Volume                          │
│     value → (삭제)                                           │
│                                                             │
│  2. 타임존 변환                                                │
│     UTC → Asia/Seoul (KST-naive)                            │
│                                                             │
│  3. 중복 제거 & 정렬                                           │
│     .drop_duplicates().sort_index()                         │
│                                                             │
│  4. 메모리 최적화                                              │
│     max_length=500 (최근 500봉만 유지)                         │
└─────────────────────────────────────────────────────────────┘
```

### 출력 DataFrame

| Column | Type | Description |
|--------|------|-------------|
| `Open` | float | 시가 |
| `High` | float | 고가 |
| `Low` | float | 저가 |
| `Close` | float | 종가 |
| `Volume` | float | 거래량 |
| index | datetime | KST-naive 시각 |

### 실시간 스트림 흐름

```
[Initial Load]
    │
    ▼
pyupbit.get_ohlcv(count=500, to=bar_close)
    │
    ▼
yield df (초기 DataFrame)
    │
    ▼
[5-second Loop]
    │
    ├── 다음 캔들 경계까지 sleep
    │
    ├── pyupbit.get_ohlcv(count=need, to=next_close)
    │
    ├── standardize_ohlcv() → 정규화
    │
    ├── _optimize_dataframe_memory() → 병합/최적화
    │
    └── yield df (업데이트된 DataFrame)
```

---

## 2. Data Feed → Strategy

### Live Loop에서 전달 (`engine/live_loop.py`)

```python
for df in stream_candles(params.upbit_ticker, params.interval, q, stop_event=stop_event):
    # df.iloc[:-1] → 닫힌 봉만 전략에 전달
    df_bt = df.iloc[:-1].copy()

    bt = Backtest(df_bt, strategy_cls, cash=params.cash, ...)
    bt.run()
```

### Strategy 초기화 (`core/strategy_v2.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                    MACDStrategy.init()                      │
│                                                             │
│  Input: self.data (OHLCV DataFrame)                         │
│                                                             │
│  Indicators 계산:                                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ self.macd_line = EMA(12) - EMA(26)                  │    │
│  │ self.signal_line = EMA(MACD, 9)                     │    │
│  │ self.ma20 = SMA(Close, 20)                          │    │
│  │ self.ma60 = SMA(Close, 60)                          │    │
│  │ self.volatility = SMA(High - Low, 20)               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  State 초기화:                                                │
│  - entry_price = None                                       │
│  - entry_bar = None                                         │
│  - highest_price = None                                     │
│  - trailing_armed = False                                   │
│  - golden_cross_pending = False                             │
└─────────────────────────────────────────────────────────────┘
```

### Strategy 신호 생성 (`MACDStrategy.next()`)

```
┌─────────────────────────────────────────────────────────────┐
│                    MACDStrategy.next()                      │
│                                                             │
│  [매 캔들마다 실행]                                             │
│                                                             │
│  1. _update_cross_state()                                   │
│     └── Golden Cross / Dead Cross 감지                       │
│                                                             │
│  2. _evaluate_sell()                                        │
│     ├── Stop Loss 체크 (price <= entry * (1 - SL))           │
│     ├── Take Profit 체크 (price >= entry * (1 + TP))         │
│     ├── Trailing Stop 체크                                   │
│     ├── MACD Negative 체크                                   │
│     └── Dead Cross 체크                                      │
│                                                             │
│  3. _evaluate_buy()                                         │
│     ├── Golden Cross 체크                                    │
│     ├── MACD > 0 체크                                        │
│     ├── Signal > 0 체크                                      │
│     ├── Bullish Candle 체크                                  │
│     ├── MACD Trending Up 체크                                │
│     └── Above MA20/MA60 체크                                 │
└─────────────────────────────────────────────────────────────┘
```

### 신호 이벤트 출력

```python
# BUY 이벤트 예시
{
    "bar": 245,
    "type": "BUY",
    "reason": "signal_positive",
    "timestamp": "2025-11-22 14:30:00",
    "price": 0.00001234,
    "macd": 0.00000012,
    "signal": 0.00000008,
    "entry_price": None,
    "entry_bar": None,
    "bars_held": 0,
    "tp": None,
    "sl": None,
    "highest": None,
    "ts_pct": 0.1,
    "ts_armed": False,
}

# SELL 이벤트 예시
{
    "bar": 250,
    "type": "SELL",
    "reason": "Take Profit",
    "timestamp": "2025-11-22 15:45:00",
    "price": 0.00001280,
    "macd": 0.00000015,
    "signal": 0.00000010,
    "entry_price": 0.00001234,
    "entry_bar": 245,
    "bars_held": 5,
    "tp": 0.00001271,
    "sl": 0.00001222,
    "highest": 0.00001290,
    "ts_pct": 0.1,
    "ts_armed": True,
}
```

---

## 3. Strategy → Trader

### Live Loop 주문 분기

```
┌─────────────────────────────────────────────────────────────┐
│                  run_live_loop() 주문 분기                    │
│                                                             │
│  [BUY 신호]                                                  │
│  ├── check_buy_conditions() 검증                             │
│  ├── trader.buy_market(price, ticker, ts, meta)             │
│  └── q.put((ts, "BUY", qty, price, reason, ...))            │
│                                                             │
│  [SELL 신호]                                                 │
│  ├── check_sell_conditions() 검증                            │
│  ├── trader.sell_market(qty, ticker, price, ts, meta)       │
│  └── q.put((ts, "SELL", qty, price, reason, ...))           │
└─────────────────────────────────────────────────────────────┘
```

### Trader 주문 실행 (`core/trader.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                    UpbitTrader                              │
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │     TEST Mode       │    │     LIVE Mode       │         │
│  │                     │    │                     │         │
│  │ _simulate_buy()     │    │ upbit.buy_market_   │         │
│  │ _simulate_sell()    │    │   order()           │         │
│  │                     │    │                     │         │
│  │ → DB 가상 거래        │    │ → Upbit API 실거래    │         │
│  └─────────────────────┘    └─────────────────────┘         │
│                                                             │
│  공통:                                                       │
│  ├── insert_order() → orders 테이블                           │
│  └── _audit_trade() → trade_audit 테이블                      │
└─────────────────────────────────────────────────────────────┘
```

### BUY 주문 흐름 (TEST Mode)

```
buy_market(price, ticker)
    │
    ├── krw_to_use = _krw_balance() * risk_pct
    │
    ├── qty = krw_to_use / (price * (1 + fee))
    │
    ├── _simulate_buy(ticker, qty, price, ...)
    │   ├── update_account(new_krw)
    │   ├── update_coin_position(new_coin)
    │   ├── insert_account_history()
    │   └── insert_position_history()
    │
    ├── insert_order(side="BUY", status="completed")
    │
    └── _audit_trade(side="BUY", ...)
```

### SELL 주문 흐름 (LIVE Mode)

```
sell_market(qty, ticker, price)
    │
    ├── res = upbit.sell_market_order(ticker, qty)
    │
    ├── uuid = res.get("uuid")
    │
    ├── insert_order(side="SELL", status="requested", provider_uuid=uuid)
    │
    ├── _audit_trade(side="SELL", ...)
    │
    └── reconciler.enqueue(uuid)  → 체결 확인 대기열
```

---

## 4. Trader → DB

### 저장되는 데이터 및 테이블

```
┌─────────────────────────────────────────────────────────────┐
│                    SQLite Database                          │
│                 services/data/tradebot_{user}.db            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ orders                                              │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, timestamp, ticker, side, price,        │    │
│  │ volume, status, current_krw, current_coin,          │    │
│  │ profit_krw, provider_uuid, state, requested_at,     │    │
│  │ executed_at, canceled_at, executed_volume,          │    │
│  │ avg_price, paid_fee, updated_at                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ trade_audit                                         │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, timestamp, ticker, interval, bar,      │    │
│  │ side, reason, price, macd, signal, entry_price,     │    │
│  │ entry_bar, bars_held, tp_price, sl_price,           │    │
│  │ highest, ts_pct, ts_armed                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ buy_eval                                            │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, timestamp, ticker, interval_sec, bar,  │    │
│  │ price, macd, signal, have_position, overall_ok,     │    │
│  │ failed_keys, checks (JSON), notes                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ sell_eval                                           │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, timestamp, ticker, interval_sec, bar,  │    │
│  │ price, macd, signal, tp_price, sl_price, highest,   │    │
│  │ ts_pct, ts_armed, bars_held, checks (JSON),         │    │
│  │ triggered, trigger_key, notes                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ account                                             │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, krw_balance, updated_at                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ coin_position                                       │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, ticker, balance, updated_at            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ account_history / position_history                  │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ id, user_id, timestamp, balance/ticker/qty          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 데이터 저장 시점

| Event | Tables Updated |
|-------|----------------|
| BUY 주문 체결 | `orders`, `trade_audit`, `account`, `coin_position`, `account_history`, `position_history`, `buy_eval` |
| SELL 주문 체결 | `orders`, `trade_audit`, `account`, `coin_position`, `account_history`, `position_history` |
| BUY 평가 (미체결) | `buy_eval` |
| SELL 평가 | `sell_eval` |
| 설정 변경 | `settings_snapshot` |

---

## 5. DB → UI (Streamlit)

### Dashboard (`pages/dashboard.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                    Dashboard 데이터 조회                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 계좌 정보                                             │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ get_account(user_id) → account.krw_balance          │    │
│  │ get_coin_balance(user_id, ticker) → coin_position   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 최근 거래 내역                                         │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ fetch_recent_orders(user_id, limit=10)              │    │
│  │ → timestamp, ticker, side, price, volume, status    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 차트 데이터                                            │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ get_ohlcv_once(ticker, interval, count=500)         │    │
│  │ → OHLCV DataFrame (Upbit API 직접 호출)               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 실시간 이벤트 (Queue)                                  │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ st.session_state.trade_q.get()                      │    │
│  │ → (timestamp, type, qty, price, reason, macd, sig)  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Set Config (`pages/set_config.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                 Set Config 데이터 흐름                         │
│                                                             │
│  [읽기]                                                      │
│  ├── {user}_latest_params.json                              │
│  │   └── ticker, interval, TP, SL, MACD params...           │
│  │                                                          │
│  └── {user}_buy_sell_conditions.json                        │
│      └── buy/sell conditions (golden_cross, tp, sl...)      │
│                                                             │
│  [쓰기]                                                      │
│  ├── Save → {user}_latest_params.json                       │
│  └── Save → {user}_buy_sell_conditions.json                 │
└─────────────────────────────────────────────────────────────┘
```

### Audit Viewer (`pages/audit_viewer.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                 Audit Viewer 데이터 조회                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ BUY 평가 로그                                         │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ fetch_buy_eval(user_id, ticker, limit=100)          │    │
│  │ → timestamp, bar, price, macd, signal, overall_ok   │    │
│  │   failed_keys, checks (JSON)                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ SELL 평가 로그                                        │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ fetch_sell_eval(user_id, ticker, limit=100)         │    │
│  │ → timestamp, bar, price, tp_price, sl_price,        │    │
│  │   triggered, trigger_key, checks (JSON)             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 거래 감사 로그                                         │    │
│  │ ─────────────────────────────────────────────────── │    │
│  │ fetch_trade_audit(user_id, limit=50)                │    │
│  │ → timestamp, side, reason, price, entry_price,      │    │
│  │   bars_held, tp_price, sl_price, highest            │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Type Summary

### Input/Output by Component

| Component | Input | Output |
|-----------|-------|--------|
| **Upbit API** | ticker, interval, count | Raw OHLCV (dict) |
| **Data Feed** | ticker, interval | DataFrame (OHLCV, KST-naive) |
| **Strategy** | DataFrame (OHLCV) | log_events, trade_events (list) |
| **Trader** | signal, price, qty | order result (dict) |
| **DB** | order/audit data | persisted rows |
| **Dashboard** | user_id | rendered UI |

### Key Data Structures

```python
# OHLCV DataFrame
{
    "Open": float,
    "High": float,
    "Low": float,
    "Close": float,
    "Volume": float,
    # index: DatetimeIndex (KST-naive)
}

# Trade Event
{
    "bar": int,
    "type": "BUY" | "SELL",
    "reason": str,
    "timestamp": datetime,
    "price": float,
    "macd": float,
    "signal": float,
    "entry_price": float | None,
    "entry_bar": int | None,
    "bars_held": int,
    "tp": float | None,
    "sl": float | None,
    "highest": float | None,
    "ts_pct": float | None,
    "ts_armed": bool,
}

# Order Result
{
    "time": datetime,
    "side": "BUY" | "SELL",
    "qty": float,
    "price": float,
    "uuid": str | None,  # LIVE mode only
    "raw": dict | None,  # LIVE mode only
}
```

---

**Last Updated**: 2025-11-22
