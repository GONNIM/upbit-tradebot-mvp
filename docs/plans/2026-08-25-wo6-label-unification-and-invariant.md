# WO-6 설계안 — 시각 표기 통일과 봉당 단일 평가 불변식

**작성일**: 2026-08-25
**개정**: 1판 → 2판 → 3판 → 4판 (F1 보완 + F2 dry-run 알림 억제 + F1b ticks 보조 판별 반영, FQ1~FQ3 실측 결과 포함)
**상태**: 배포판 (v1.2026.08.29.1926)
**전제 조건**: WO-1 상태(HEAD `1404c1c`, `3b76e02` 위 AD1 재적용 + 위험 기록) 안정 운영 중

## 4판 개정 요약

- **F1 (2026-08-26)**: `_classify_no_trade_after_exhaustion` 신설. 재시도 소진
  후 다음 봉 존재 판단으로 무거래 봉을 NO_TRADE 로 확정, 실패 계수 미가산.
- **F2 (2026-08-26)**: dry-run 모드에서 `services.notifier.send` 실 발송 억제
  (`WO6_DRY_RUN` 환경변수 기준).
- **F1b (2026-08-29)**: F1 판별 불가(연속 무거래 시작 지점) 시 `/v1/trades/
  ticks` 보조 조회로 체결 여부 확인. 체결 0건 → NO_TRADE, 존재 → None.
- **FQ1~FQ3 실측 (2026-08-29)**: Upbit 원본 2642봉 기준 로컬 dry 실시간
  커버리지 23.5%, 총 지표 반영 98.8%. RETRY 소진 151봉 전량 진짜 무거래.
  missing_bar 2277봉은 UNIQUE 인덱스로 봉당 1행. 서버 회선에서는 실시간
  커버리지 개선 예상.

---

## 1. 배경

WO-2 계열 배포는 세 차례 모두 실패했다. 실패의 표면 증상은 각각 달랐지만
근본 원인은 공통이었다.

- 1차 배포 (2026-08-23, 옵션 6 단독): 5분 만에 5봉 연속 폴백과 CRITICAL 발동.
- 2차 배포 (2026-08-23, v3 옵션 7 + P0 옵션 A): 29분 만에 라벨 이중화 4쌍 확인.
- 3차 배포 (2026-08-24, v3 H-A + AD1): 31시간 후 지표 이탈 확정
  (fast EMA 이탈 +6.34, slow EMA 이탈 +10.23), 매수 신호 소실 8건.

세 번 모두 `core/candle_clock.py:82 get_closed_ts` 함수의 오프바이원과,
봇 라벨(`closed_ts`)과 Upbit 라벨(`upbit_ts`)의 혼용이 근원이었다.

또한 3차 배포에서는 새 결함이 하나 더 드러났다. 같은 봉이 두 번 평가되는
경로가 있었다. `[SKIP-BAR]`가 실시간 판정을 건너뛴 뒤 BACKFILL이 재평가하고,
곧이어 VERIFY 후속 부분 재계산이 다시 매수 판정을 실행했다. 결과적으로
매수 신호 8건이 소실됐고, 우연히 회수된 1건은 -2,198.54원의 실현 손실로
이어졌다.

WO-6은 이 두 근본 결함을 함께 해소한다. 시각 표기를 통일해 오프바이원과
라벨 혼용을 제거하고, 봉당 매매 판단 횟수를 정확히 1회로 강제해 이중 매매
판단을 차단한다.

---

## 2. 중심 원칙

**확정된 모든 봉은 정확히 한 번 실시간 평가를 받는다.**

이 원칙은 WO-6 설계의 모든 결정을 지배한다. 새 경로를 추가할 때도, 기존
경로를 수정할 때도 이 원칙이 지켜지는지 확인한 뒤에만 채택한다.

원칙의 세 가지 세부 조항이다.

- **완결성**: 확정 여부를 아직 판정할 수 없는 봉이라도 실시간 평가를 반드시
  받는다. 평가를 건너뛰는 경로는 만들지 않는다.
- **단일성**: 같은 봉이 두 번 매매 판단을 받지 않는다. 지표 갱신이 여러 번
  일어날 수는 있어도, 매수·매도 판단은 봉당 1회만 실행된다.
- **분리성**: 지표 갱신 경로와 매매 판단 경로를 분리한다. 부분 재계산이나
  BACKFILL이 지표를 다시 갱신하더라도 매매 관문을 다시 통과시키지 않는다.

원칙 준수 여부는 설계안의 모든 경로 표에 명시적으로 표기한다. 아래 §7의
경로 점검 표를 참고한다.

---

## 3. 시각 표기 통일

### 3.1 두 라벨의 의미와 현재 혼용 지점

봇 코드에는 두 종류의 시각이 섞여 있다. 이름과 실제 의미가 어긋나는
지점들이 있다.

- **`closed_ts`**: `candle_clock.get_closed_ts`가 반환하는 값. 현재 정의로는
  "현재 시각을 봉 간격으로 내림한 값"이다. 즉 지금 진행 중인 봉의 시작 시각.
  함수 이름은 "확정된 봉의 시각"으로 읽히지만 실제로는 그렇지 않다. 이것이
  오프바이원 결함의 근원이다.
- **`upbit_ts`**: Upbit REST API가 반환하는 봉 시각. 진짜 확정된 봉의 시작
  시각이다. `closed_ts - interval_sec`와 일치한다.

3차 배포에서는 두 라벨을 임시로 교정하는 코드(`upbit_ts = closed_ts -
timedelta(seconds=interval_sec)`)를 v3 함수에 넣었지만, 이 교정이 파이프라인
전역에 전파되지 않아 라벨 이중화가 발생했다.

### 3.2 개편안: `closed_ts`의 의미 재정의

`get_closed_ts`의 반환값을 "**방금 확정된 봉의 시작 시각**"으로 재정의한다.
현재 시각을 내림한 값에서 봉 간격 하나를 뺀 값이다.

```python
# 개편 후 (개념)
def get_closed_ts(self, now: datetime) -> datetime:
    boundary = floor_to_interval(now, self.interval_sec)
    closed_ts = boundary - timedelta(seconds=self.interval_sec)
    return closed_ts
```

- 예: `now = 09:05:42` → `boundary = 09:05:00` → `closed_ts = 09:04:00`
- 이 값은 Upbit 봉 시작 시각과 항상 일치한다. 두 라벨의 개념이 하나로
  합쳐진다.
- `upbit_ts`라는 별도 개념은 코드에서 사라진다.

### 3.3 사용 지점 전수 표

시각 라벨 관련 코드 지점을 파일과 줄 번호로 정리했다. 이 표는 "값 의미가
바뀌면 코드도 함께 바뀌어야 하는지" 확인하는 근거 자료다. 아래 §3.5는
`fetch_confirmed_candle`의 세 케이스 동작을 코드 근거로 별도 확인한다.

#### `core/candle_clock.py`

| 줄 | 현재 코드 | 개편안 |
|---|---|---|
| 82 | `def get_closed_ts(self, now)` 반환 = `floor(now)` | 반환 = `floor(now) - interval_sec` |
| 99 | `closed_ts = floor_to_interval(now, self.interval_sec)` | `closed_ts = floor(now) - timedelta(seconds=self.interval_sec)` |
| 102 | `[CLOCK] 봉 확정 \| closed={format_kst(closed_ts)}` | 라벨 이름 유지, 값 의미만 교정 |
| 144 | `def is_duplicate_close(self, closed_ts)` | 파라미터 이름 유지, 새 의미 반영 |

#### `core/rest_reconcile.py`

| 줄 | 현재 | 개편안 |
|---|---|---|
| 437 | `def fetch_confirmed_candle(..., closed_ts: datetime, ...)` | 그대로 유지, 값 의미만 재정의된 것 사용 |
| 452 | 파라미터 설명 "확정되어야 할 봉의 시작 timestamp" | 설명 재확인 (개편 후 정확히 그렇게 동작) |
| 514~524 | 케이스 1: `latest_ts == closed_ts` | §3.5에서 재해석 |
| 526~533 | 케이스 2: `latest_ts < closed_ts` | §3.5에서 재해석 |
| 535~549 | 케이스 3: `latest_ts > closed_ts` | §3.5에서 재해석 |
| 718 | `closed_ts=ts` 전달 | 전달값이 이미 upbit 봉 시작 시각이므로 그대로 |

#### `engine/live_loop.py`

| 줄 | 현재 | 개편안 |
|---|---|---|
| 914 | `closed_ts = clock.get_closed_ts(now)` | 그대로. 반환값 의미만 바뀜 |
| 929 | `if closed_ts <= engine.last_bar_ts` | 그대로. 두 값 모두 upbit 봉 시작 시각으로 통일됨 |
| 934 | `⏰ [CLOCK-CLOSE] 봉 확정 감지 \| ts={closed_ts}` | 로그 표기 유지, 값 의미 교정 |
| 946 | `closed_ts` 봉을 별도로 조회 | 그대로 |
| 953 | `closed_ts=closed_ts` 전달 | 그대로 |
| 961 | `end_ts=closed_ts` | 그대로 |
| 967~970 | `if closed_ts in rest_df.index: rest_df.loc[closed_ts] = confirmed_row` | 그대로. v3에서 도입한 `upbit_ts` 별도 변수는 삭제 |
| 979 | `rest_df에 closed_ts 없으면 추가` | 그대로 |

#### `core/strategy_engine.py`

| 줄 | 현재 | 개편안 |
|---|---|---|
| 84 | `self.last_bar_ts = None` | 그대로. 저장 값 의미 통일 (upbit 봉 시작 시각) |
| 259 | `return bar.ts != self.last_bar_ts` | 그대로 |
| 458 | `logger.warning(f"⚠️ 미확정 봉 무시: {bar.ts}")` | 그대로 |
| 476 | `self.last_bar_ts = bar.ts` | 그대로 |
| 567 | `logger.error(f"[ENGINE] 미확정 봉 거부 \| {bar.ts}")` | 그대로 |
| 587 | `self.last_bar_ts = bar.ts` | 그대로 |
| 592 | `[BACKFILL] 버퍼 추가 스킵 (재평가 모드) \| ts={bar.ts}` | 그대로 |

#### `core/candle_buffer.py`

| 줄 | 현재 | 개편안 |
|---|---|---|
| 70, 74 | `self.last_ts == bar.ts`, `self.last_ts = bar.ts` | 그대로. 봉 시각 통일 |

### 3.4 통일 수정 범위

- **의미 변경**: `candle_clock.get_closed_ts` 한 함수만 실제 반환값이 바뀐다.
- **파급 없음**: 나머지 지점은 값을 그대로 사용하므로 코드 변경 없이 개념만
  통일된다. 다만 v3 도입 시 추가된 `upbit_ts` 별도 변수와 라벨 교정 코드
  (`upbit_ts = closed_ts - timedelta(...)`)는 삭제된다.
- **문서와 주석 갱신**: 함수 docstring과 관련 주석에서 "현재 봉의 시작 시각"
  표현을 "방금 확정된 봉의 시작 시각"으로 정정한다.

### 3.5 `fetch_confirmed_candle` 세 케이스 재해석과 최소 수정안

새 `closed_ts` 의미(방금 확정된 봉의 시작 시각 = Upbit 봉 시작 시각)
아래에서 `core/rest_reconcile.py:434 fetch_confirmed_candle`의 세 케이스가
어떻게 동작하는지 코드 줄 번호와 함께 확정한다.

#### 케이스 A: `latest_ts > closed_ts` (다음 봉에 이미 거래가 생김)

- **현재 코드 (line 535~549)**:
  ```python
  else:  # latest_ts > closed_ts
      if closed_ts in df.index:
          close_price = df.loc[closed_ts, "Close"]
          logger.info(f"[RECONCILE] 과거 확정 봉 추출 ✅ ...")
          return df.loc[closed_ts]
      else:
          logger.error(f"[RECONCILE] 봉 유실 ...")
          return None
  ```
- **새 의미상 해석**: 다음 봉에 거래가 이미 시작됐다면 대상 봉은 시장에서
  이미 마감된 상태다. 확정으로 볼 수 있다.
- **현재 동작 결과**:
  - `closed_ts`가 응답 안에 있으면 즉시 반환 → **정상 처리**.
  - `closed_ts`가 응답 안에 없으면 유실로 판단하고 `None` 반환 → BACKFILL로
    위임. 이것은 대상 봉 자체가 무거래인 경우다. 무거래 봉은 이전 봉의 종가
    유지가 정확한데, 현재 코드는 이를 명시적으로 다루지 않고 BACKFILL로
    떠넘긴다.
- **8-23 재실측 근거**: 활발한 시간대에는 이 케이스가 가장 흔했다. 24h
  실측에서 FAST 경로(`next_bar_exists`) 관측 262건(18.2%), p50=29ms로 정상
  처리됐다. 다만 케이스 A가 정상 확정임에도 `elif`로 마지막에 배치돼 있어
  케이스 1이 먼저 매칭되는 순서 문제도 함께 있다.

#### 케이스 B: `latest_ts == closed_ts` (다음 봉에 아직 거래가 없음)

- **현재 코드 (line 514~524)**:
  ```python
  if latest_ts == closed_ts:
      close_price = df.iloc[-1]["Close"]
      logger.info(f"[RECONCILE] 확정 종가 ✅ ...")
      _confirmed_fetch_consecutive_failures[ticker] = 0
      return df.iloc[-1]
  ```
- **새 의미상 해석**: 응답의 마지막 봉이 방금 확정된 봉과 같다면, 다음 봉의
  거래는 아직 발생하지 않았다는 뜻이다. 시장 마감 시점을 지났지만 다음 봉
  거래가 없으므로, 대상 봉의 종가가 이론적으로 아주 미세하게 갱신될 여지가
  있다.
- **현재 동작 결과**: 이 경우도 확정으로 처리하여 즉시 종가를 반환한다.
  대부분의 저유동성 봉에서 이 흐름을 탄다.
- **잔여 위험**: 이론적으로는 확정 이후 미세 갱신이 가능하다. 다만 3차 배포
  24h 실측에서는 이 경로로 확정된 봉의 사후 changed_close가 0건으로
  관측됐다. 위험은 존재하나 실측 근거상 매우 낮다.
- **개편안 (5초 안정화 1회)**: 재시도 강등은 저유동성 봉의 약 3분의 1에
  25초 이상의 판단 지연을 만들어 매도 필터 반응까지 늦어진다는 실무 부담이
  있다. 대신 케이스 B에 처음 도달하면 5초 뒤 한 번만 다시 조회한다. 종가가
  같으면 확정으로 반환한다(안정화 확인). 종가가 다르거나 다음 봉이 생겼으면
  그 시점의 케이스로 다시 판정한다. 추가 반복은 하지 않는다.
- **최악 지연 상한**: 종가가 계속 바뀌는 극단적 상황에서는 안정화 확인이
  재시도 한도 안에서 반복될 수 있으며, 최악 지연은 "재시도 한도 × 5초"로
  묶인다(1분봉 기준 최대 27초, 3분봉 기준 최대 87초).

#### 케이스 C: `latest_ts < closed_ts` (Upbit API가 봇 시계보다 지연)

- **현재 코드 (line 526~533)**:
  ```python
  elif latest_ts < closed_ts:
      wait = WAIT_SCHEDULE[attempt] ...
      logger.warning(f"[RECONCILE] 봉 미반영 ...")
      time.sleep(wait)
  ```
- **새 의미상 해석**: Upbit API가 봇의 봉 확정 시각을 아직 반영하지 못한
  상태. 즉 대상 봉 조회 자체가 불가하다.
- **현재 동작 결과**: 5초 대기 후 재시도. 재시도 초과 시 BACKFILL로 위임.
  이 처리 자체는 정상.

#### 케이스 D: 대상 봉 자체가 무거래 (`latest_ts > closed_ts` 하위 조건)

- **현재 동작 결과**: 케이스 A의 하위 조건. `closed_ts not in df.index` 이면
  "봉 유실"로 판단해 `None` 반환.
- **개편안 (NO_TRADE 표지 반환, 가짜 봉 합성 금지)**: Upbit는 무거래 분에
  봉을 만들지 않는다. 차트, 과거 데이터, 백테스트 모두 무거래 분이 빠진
  시계열이다. 가짜 봉을 지표에 넣으면 봇과 차트의 지표가 달라지고, 봇 내부
  시계열과 Upbit 응답 사이에 영구 불일치가 생겨 재조정이 매 주기 오탐할 수
  있다. 따라서 가짜 봉을 합성하지 않는다.
- **동작**: 케이스 A에서 대상 봉이 응답에 없으면 `NO_TRADE` 표지를 반환한다.
  호출한 쪽은 로그 한 줄을 남기고 그 봉을 건너뛴다. 지표 미반영이라는 기존
  동작을 유지한다. 실패 계수(`_confirmed_fetch_consecutive_failures`)와
  CRITICAL 집계에서 제외한다. BACKFILL로도 위임하지 않는다. 재평가할
  데이터 자체가 없기 때문이다.
- **표지 방식 예시**: 반환 타입을 `Optional[pd.Series] | Literal['NO_TRADE']`
  로 확장하거나, 별도 상수/센티널 객체(`NO_TRADE_MARKER`)를 사용한다. 구현
  단계에서는 센티널 객체 방식을 채택한다(호출부 분기 명확성 확보).

#### 최소 수정안 (3판 반영)

**처리 순서를 케이스 A → C → B로 재배치한다. 무거래 봉은 NO_TRADE 표지로
반환한다. 케이스 B는 5초 안정화 1회로 바꾼다.** 케이스 B/C 모두 실패해
아무것도 반환하지 못한 경우는 `None`을 반환한다.

수정 후 개념 흐름은 다음과 같다.

```python
# 개편 후 (개념)
NO_TRADE = object()  # 센티널 (합성 봉 아님)

_case_b_stabilized: dict[str, datetime] = {}  # 티커별 케이스 B 첫 진입 시각

def fetch_confirmed_candle(ticker, timeframe, closed_ts, max_retry=None):
    for attempt in range(max_retry):
        df = pyupbit.get_ohlcv(ticker=ticker, interval=timeframe, count=10)
        if df is None or df.empty:
            time.sleep(wait); continue

        latest_ts = df.index[-1]

        # 케이스 A: 다음 봉 존재 → 즉시 확정
        if latest_ts > closed_ts:
            if closed_ts in df.index:
                return df.loc[closed_ts]                        # 거래 있음
            else:
                return NO_TRADE                                 # 무거래 표지
        # 케이스 C: API 지연 → 재시도
        elif latest_ts < closed_ts:
            time.sleep(wait); continue
        # 케이스 B: 다음 봉 미존재 → 5초 안정화 1회
        else:
            first_ts = _case_b_stabilized.get((ticker, closed_ts))
            first_close = _case_b_stabilized_close.get((ticker, closed_ts))
            now = datetime.now(timezone.utc)
            current_close = df.iloc[-1]["Close"]

            if first_ts is None:
                # 첫 진입: 5초 뒤 재조회 예약
                _case_b_stabilized[(ticker, closed_ts)] = now
                _case_b_stabilized_close[(ticker, closed_ts)] = current_close
                time.sleep(5); continue
            elif (now - first_ts).total_seconds() >= 5:
                if current_close == first_close:
                    # 안정화 확인 → 확정
                    return df.iloc[-1]
                else:
                    # 종가 변경 감지 → 다음 조회의 케이스로 재판정
                    _case_b_stabilized[(ticker, closed_ts)] = now
                    _case_b_stabilized_close[(ticker, closed_ts)] = current_close
                    time.sleep(5); continue
            else:
                # 5초 안 지났음 → 계속 대기
                time.sleep(1); continue

    return None  # 재시도 초과 → 재조정 계속 진행 (기존 흐름)
```

- **케이스 A** 최상단 승격 → 다음 봉 존재 시 즉시 확정. 무거래 봉은
  `NO_TRADE` 센티널 반환(가짜 봉 합성 금지).
- **케이스 B** 5초 안정화 1회 → 첫 진입 시 5초 뒤 재조회, 종가 같으면 확정,
  다르면 다음 조회의 케이스로 재판정. 추가 반복 없음.
- **케이스 B/C 재시도 실패 시** `None` 반환. 호출부(`engine/live_loop.py:982
  ~984`)가 ERROR 로그만 남기고 `reconcile_series`로 계속 진행. 즉 그 봉도
  §4.2 검사를 거쳐 실시간 매매 판단을 받는다(중심 원칙 준수).

**잔여 위험 서술**: 케이스 A 즉시 확정과 케이스 B 5초 안정화 확정 모두
이론적 잔여 위험이 있다. Upbit가 이미 다음 봉을 반환하고 있어도 이전 봉의
종가 확정 처리가 내부적으로 완료되지 않았을 이론적 가능성이다. 다만 24h
실측 근거상 FAST 경로 262건 전체에서 사후 changed_close가 0건으로
관측됐다. 위험은 존재하나 실측상 매우 낮다. 검증 세 겹(§5)에서 이 항목을
명시적으로 추적한다.

---

## 4. 승인된 조치 두 가지

### 4.1 조치 A: 건너뛰기(`[SKIP-BAR]`) 제거

`[SKIP-BAR]` 경로는 WO-2 v3의 P0 옵션 A가 도입했다. 매수 신호 소실의
직접 원인이었다.

**개편안**: `[SKIP-BAR]` 코드를 삭제한다. 확정 판정이 실패하더라도 실시간
평가는 반드시 실행된다. 다만 매수 결정이 나온 경우에는 발주를 안전하게
지연한다. 지연 규칙은 아래 §6(WO-2 재적용)에서 정의한다.

**영향 위치**: `engine/live_loop.py:983~996` 근처(3차 배포에서 추가된
`⏸ [SKIP-BAR]` 로직). 이 블록은 통째로 제거된다.

### 4.2 조치 B: 봉당 매매 판단 1회 강제 (검사 위치와 등록 주체 명시)

같은 봉이 두 번 매매 판단을 받지 못하도록 봉당 판단 여부 플래그를 둔다.

#### 검사 위치

**함수 입구가 아니라 매매 판단 직전에 검사한다.** 지표 갱신과 재평가
기록(WO-1의 실시간/BACKFILL 컬럼 분리, 종가 변경 감지, Issue #11 백업과
복원)은 기존과 동일하게 작동해야 한다.

- 검사 지점: `core/strategy_engine.py:644 self.strategy.on_bar(...)` 호출
  직전.
- 지표 갱신 코드(라인 594~628)는 그대로 실행한다.
- 매매 판단 함수 호출 직전에만 `_evaluated_bar_ts` 검사를 통과해야 한다.

```python
# 개념 (line 630~ 사이)
with self._execution_lock:
    self.position.sync_from_wallet()
    has_position_before_eval = self.position.has_position
    ...
    ind_snapshot = self.indicators.get_snapshot(is_buy_eval=is_buy_eval)

    # 봉당 1회 검사 (매매 판단 직전)
    if bar.ts in self._evaluated_bar_ts:
        logger.info(
            f"[ENGINE] 봉당 매매 판단 1회 규칙 적용 | ts={bar.ts} "
            f"(이미 실시간 평가 완료, 매매 판단 건너뜀. 지표는 이미 갱신됨)"
        )
        return  # 매매 판단만 건너뜀. 지표 갱신·재평가 기록은 위에서 완료

    action = self.strategy.on_bar(bar, ind_snapshot, self.position, self.bar_count)

    # 등록: 실시간 평가만
    if not backfill_mode:
        self._evaluated_bar_ts_register(bar.ts)
    ...
```

#### 등록 주체

**실시간 평가(`backfill_mode=False`)만 평가 이력에 등록한다.** 뒤늦은
재평가(`backfill_mode=True`)는 등록하지 않는다.

- 이렇게 해야 순서가 꼬여도(예: `[SKIP-BAR]` 제거로 실시간이 먼저 실행되고
  뒤이어 BACKFILL이 재평가하는 정상 순서, 혹은 그 반대 순서) 실시간 평가가
  BACKFILL의 앞선 등록에 막히지 않는다.
- 예상 순서:
  1. `[CLOCK-CLOSE]` → 실시간 평가 → `_evaluated_bar_ts`에 등록 → 매매 판단
     1회 실행.
  2. 이후 BACKFILL이 같은 봉을 재평가해도 지표 갱신만 실행. 매매 판단은
     건너뜀(등록 검사에 걸림).
- 반대 순서(드묾): BACKFILL이 먼저 실행돼도 등록하지 않으므로, 이후 실시간
  평가가 정상적으로 매매 판단을 실행함.

#### 자료구조

`collections.OrderedDict`를 사용한다. 등록 순서가 유지되며, 상한 초과 시
`popitem(last=False)`로 오래된 항목부터 삭제할 수 있다.

```python
# 개념
from collections import OrderedDict

class StrategyEngine:
    _EVAL_HISTORY_MAX = 1000  # 최근 1000봉 (분봉 기준 약 16시간)

    def __init__(...):
        ...
        self._evaluated_bar_ts: OrderedDict[datetime, None] = OrderedDict()

    def _evaluated_bar_ts_register(self, ts: datetime):
        self._evaluated_bar_ts[ts] = None
        while len(self._evaluated_bar_ts) > self._EVAL_HISTORY_MAX:
            self._evaluated_bar_ts.popitem(last=False)
```

- 크기 상한: 1000봉(분봉 기준 약 16시간 분량). 상한을 넘으면 가장 오래된
  봉부터 자동 삭제.
- 검색은 `in` 연산자로 평균 O(1).
- 등록 시각과 삭제 시각의 순서가 유지되므로 예측 가능한 동작.

#### 재시작 시 이력 소실 대응

재시작 시 `_evaluated_bar_ts`는 비어 있게 된다. 이 경우 `last_bar_ts` 검사
(`core/strategy_engine.py:574`)가 방어선이 된다.

```python
# 기존 코드 (재시작 시 방어선 역할)
if not backfill_mode and not self.is_new_bar(bar):
    logger.debug(f"[ENGINE] 중복 봉 무시 | {bar.ts}")
    return
```

- 재시작 후 첫 봉 처리에서 `last_bar_ts`가 새로 세팅되므로, 이전에 이미
  처리한 봉을 다시 매매 판단할 수 있는 경우는 재시작 시점 봉 하나로
  국한된다.
- 이 경우도 매매 판단은 봉당 1회 원칙에 맞다(재시작 이전에 판단했더라도
  이후에 판단 이력이 소실됐으므로 새 판단이 유일하다).

### 4.3 부분 재계산 경로의 지표 갱신과 관문 평가 분리

현재 `strategy_engine.py:608~623`의 부분 재계산 경로는 지표 갱신과 매매
판단이 하나의 흐름에 묶여 있다.

**개편안**: 두 흐름을 분리한다.

- **지표 갱신 함수**: 기존 `recompute_from_changed_ts` + `update_incremental`
  호출을 그대로 사용. 지표만 갱신한다.
- **매매 판단 함수**: 기존 `strategy.on_bar` 유지. 하지만 §4.2의 검사(봉당
  1회)를 통과해야 실행된다.

**흐름**:

1. REST 재조회가 `changed_count > 0`을 반환하면 지표 갱신 코드 실행.
2. 매매 판단 직전 검사에서 `_evaluated_bar_ts`에 봉이 있으면 판단 건너뜀.
3. VERIFY 후속 재계산 등이 같은 봉의 지표를 갱신하더라도 매매 판단은 다시
   실행되지 않는다.

이로써 부분 재계산의 순기능(지표 정확성 유지)은 보존하되, 이번 사고의
근원인 이중 매매 판단은 차단된다.

---

## 5. 검증 세 겹

WO-6 배포는 다음 세 단계 검증을 모두 통과해야 한다.

### 5.0 dry-run 안전성 근거 (P2 검증 결과)

- **주문 상태 추적 스레드**: `order_reconciler`는 `get_reconciler().enqueue`
  로 등록된 uuid 만 조회한다. `UpbitTrader.buy_market`/`sell_market`/`buy_limit`
  의 dry-run 조기 반환은 이 enqueue 호출에 도달하기 전에 종결되므로,
  `DRY_RUN` uuid 는 추적 큐에 등록되지 않고 즉시 종결된다.
- **pending 상태 자동 해제**: dry-run 이 반환한 `DRY_RUN` uuid 가
  `_pending_buy_uuid`에 저장되더라도, `_maybe_release_limit_pending`가 봉
  경계 통과 시 자동 해제한다. `apply_entry`는 uuid 매칭 검사(strategy_engine
  라인 205)로 실 fill 이 아닌 이벤트를 무시한다.
- **_case_b_state 정리**: 확정, NO_TRADE, 재시도 초과, 예외 발생 등 모든
  종료 경로에서 해당 봉의 항목을 삭제한다(rest_reconcile.py 라인 555, 572,
  598, 615~620, 623). 안전장치로 함수 진입 시 오래된 항목(30분 이전)을
  자동 삭제하는 `_case_b_state_gc`를 실행한다.

### 5.1 배포 전 실환경 확인 (병행 실행 방식)

서버 배포 전에 **로컬 환경에서 실제 Upbit API를 상대로 병행 실행**한다.
서버 봇과 로컬 봇이 같은 종목을 대상으로 나란히 작동하며, 로그를 비교한다.

- **실행 방법**:
  1. 로컬에서 `python -m engine.live_loop --ticker KRW-JTO --strategy EMA --dry-run` 형태로 실행. `--dry-run` 플래그는 실주문을 억제하되 매매 판단은 실행하는 옵션(필요 시 이번 WO-6 구현 단계에서 신설).
  2. 로컬 실행 봇은 서버와 다른 감사 데이터베이스를 사용하도록 격리.
  3. 서버는 기존 코드 그대로 유지.
  4. 두 봇의 로그를 시각별로 대조. `[CLOCK-CLOSE]`, `[CONFIRMED]`, 매매
     판단, 지표 값을 비교.
- **관측 시간대**:
  - 저유동성 시간대(예: KST 03:00~06:00) 최소 30봉. `[SKIP-BAR]` 로그
    부재, `[CONFIRMED]` 처리가 봉마다 1회 발생, BACKFILL 재평가 시 매매
    판단 미실행 확인.
  - 활성 시간대(예: KST 09:00~11:00) 최소 30봉.
- **필수 확인 항목**:
  - 봉당 매매 판단 횟수가 정확히 1인지 로그로 확인.
  - `_evaluated_bar_ts` 등록 로그와 매매 판단 스킵 로그가 짝을 이루는지.
  - fetch_confirmed_candle 케이스 A/B/C 각각에서 예상대로 동작하는지.
- **필요 시 도구**: `scripts/regression_gate.sh`에 라이브 스모크 서브
  커맨드를 추가하거나 `scripts/live_smoke_wo6.py` 신설을 고려. 이 결정은
  구현 단계에서 승인 후 진행.

### 5.2 배포 직후 30분 확인

- 서비스 restart 후 7단계 기동 로그가 모두 관측되는지.
- `[SKIP-BAR]` 로그 부재.
- Traceback, CRITICAL, POLLUTED 부재.
- 첫 30분 동안 처리된 봉 목록을 뽑아 봉당 매매 판단 횟수가 정확히 1인지
  확인.
- 지정가 매수가 켜져 있는 상태라면, 지정가 주문 접수와 취소가 봉 경계에서
  정상 작동하는지 확인.

### 5.3 24시간 실측

- `audit_buy_eval`의 봉별 매매 판단 결과 행이 정확히 1개인지 SQL로 확인.
  BACKFILL 컬럼이 추가로 채워지는 것은 허용(지표 갱신 결과).
- BACKFILL 트리거 이후 실주문이 발화되지 않는지 확인.
- `changed_count > 0` 상황에서 지표 갱신은 있어도 매매 판단이 봉당 1회로
  유지되는지 확인.
- **필수 확인 항목**: 봉당 매매 판단 횟수 분포가 (1: 전체, 2 이상: 0)인지.
- 실주문과 감사 로그의 정합.

### 5.4 검증 실패 시 조치

- 위 세 단계 중 어느 하나라도 실패하면 즉시 롤백한다.
- 롤백 대상은 WO-6 이전 상태(현재 서버 HEAD 기준 `1404c1c`).
- 롤백 절차는 이번 세션에서 정립한 옵션 A 절차를 따른다(revert 커밋 후
  push, force 없음).

---

## 6. WO-6 완료 후 WO-2 재적용 계획

WO-6이 안착하면 WO-2(확정 판정 강화)를 다시 시도한다. 이번에는 `[SKIP-BAR]`
없이, 확정 실패 봉도 실시간 평가를 받되 발주만 지연하는 구조로 설계한다.

### 6.1 재적용 원칙

- **모든 봉은 실시간 평가를 받는다.** 확정 여부와 무관하다.
- **매매 결정이 나온 봉은 확정 조건이 충족될 때까지 발주를 지연한다.**
- **지연 최대 시간**을 두어 무한 대기를 방지한다.
- **BACKFILL은 지연 발주를 대신하지 않는다.** BACKFILL은 지표 갱신과 감사
  로그만 담당한다.

### 6.2 흐름

1. `[CLOCK-CLOSE]` → 실시간 평가 실행 (봉당 1회).
2. 평가 결과 매매 결정이 나오면 확정 판정 함수 호출.
3. 확정이면 즉시 유효성 확인(§6.4) → 발주.
4. 미확정이면 `_pending_orders`에 등록 후 대기.
5. 다음 CLOCK-CLOSE 시각에 확정 재판정.
6. 확정되면 유효성 확인 → 발주. 여전히 미확정이면 다시 대기.
7. 최대 대기 시간 초과 시 발주 취소, 로그와 감사 기록.

### 6.3 데이터 구조

```python
# 개념
class PendingOrder:
    bar_ts: datetime
    decision: str           # 'BUY' or 'SELL'
    context: dict           # 관문 통과 시점의 스냅샷
    tentative_close: float  # 평가 시점 종가
    created_at: datetime
    max_wait_sec: int
```

### 6.4 유효성 확인 (재판정이 아님)

**대기 중이던 주문이 확정 조건을 충족한 시점에, 확정된 종가로도 신호가
성립하는지 한 번만 확인한다.** 성립하면 발주하고, 성립하지 않으면 발주를
취소하고 감사 기록에 사유를 남긴다. **이 확인은 재판정이 아니라 유효성
확인이다.** 두 개념의 차이는 다음과 같다.

- **재판정**: 관문(오염 차단, 재사용 대기, 포지션 제한, 필터 등) 전체를
  다시 실행. 봉당 매매 판단 1회 원칙에 위배됨.
- **유효성 확인**: 원래 판단에서 사용한 신호 조건(예: EMA fast > EMA slow)
  하나만 확정된 종가로 다시 계산해서 여전히 성립하는지 확인. 관문은 다시
  실행하지 않음.

**근거 사례 (2026-08-20 04:34)**: 04:34 봉의 실시간 평가 시점 종가는
777원이었고, 이후 확정 시점 종가는 779원으로 갱신됐다. 봇의 원래 판단은
777원 기준으로 EMA Golden Cross가 성립했다. 유효성 확인은 확정 종가
779원으로 EMA를 재계산해 여전히 Golden Cross가 성립하는지 한 번만 확인한다.
결과가 성립이면 발주, 미성립이면 취소.

**감사 기록**: 유효성 확인 결과를 `audit_buy_eval`에 별도 컬럼으로 남긴다
(예: `validation_passed`, `validation_reason`). 발주 취소된 경우 사유를
명확히 기록해 사후 감사 가능.

### 6.5 관문 결정과 발주 분리의 안전성

- **관문 통과 시점의 스냅샷 보존**: 매매 결정은 봉 확정 시점의 지표와 조건
  스냅샷을 그대로 사용한다. 이후 시장이 변해도 발주는 이 스냅샷을 기준으로
  집행된다. 다만 §6.4의 유효성 확인은 확정 종가로 한 번만 실행된다.
- **재판단 없음**: 대기 중인 주문은 관문 재판단을 받지 않는다. 오직 유효성
  확인만 받는다.

### 6.6 검증

WO-6 재적용에도 §5의 세 겹 검증을 적용한다. 특히 다음을 확인한다.

- 지연 발주가 최대 대기 시간 안에 처리되는 비율.
- 대기 취소 비율(취소가 잦으면 파라미터 조정 필요).
- 유효성 확인 통과율과 취소율.
- 지연 발주와 감사 로그의 정합.

---

## 7. 경로 점검 표 (원칙 준수 여부)

| 경로 | 원칙 준수 | 근거 |
|---|---|---|
| 정상 실시간 확정 봉 | 예 | 봉당 1회 매매 판단, 지표 갱신 후 판단, `_evaluated_bar_ts` 등록 |
| BACKFILL 재평가 | 예 | 지표 갱신만, 매매 판단 직전 검사로 차단, 등록하지 않음 |
| VERIFY 후속 부분 재계산 | 예 | 지표 갱신만, 매매 판단 직전 검사로 차단 |
| 확정 실패 후 재판정 (WO-2 재적용 시) | 예 | 실시간 평가는 봉당 1회, 대기 중 유효성 확인만, 관문 재판정 없음 |
| REST 응답 지연 (케이스 C) | 예 | 재시도 후 케이스 A로 전환되거나 BACKFILL로 위임 |
| 무거래 봉 (케이스 D) | 예 | `NO_TRADE` 표지 반환 → 호출부 로그 1줄 + 건너뜀. 지표 미반영 유지, BACKFILL 위임 없음, 실패 계수 제외 |
| 케이스 B/C 재시도 실패 (fetch None 반환) | 예 | `engine/live_loop.py:982~984` ERROR 로그 후 `reconcile_series`로 계속 진행 → §4.2 검사 거쳐 봉당 1회 매매 판단 실행 |
| 재시작 직후 첫 봉 | 예 | `_evaluated_bar_ts` 비어 있으나 `last_bar_ts` 검사가 방어 |
| 예외 발생 시 fallback | 예 | 무해 fallback만, 유해 fallback은 CRITICAL 알림 |

`[SKIP-BAR]` 경로는 이 표에 존재하지 않는다. 삭제되기 때문이다.

---

## 8. 회귀 테스트 신설

`tests/regressions/`에 다음 네 테스트를 추가한다.

- **`test_r_2026_08_25_wo6_closed_ts_semantics.py`**: `get_closed_ts` 반환값이
  Upbit 봉 시작 시각과 일치하는지 단위 테스트.
- **`test_r_2026_08_25_wo6_single_evaluation.py`**: 같은 봉이 두 번
  `on_new_bar_confirmed`에 진입해도 매매 판단은 1회만 실행되는지 통합
  테스트. 실시간 등록만 이루어지고 BACKFILL은 등록하지 않는지도 확인.
- **`test_r_2026_08_25_wo6_indicator_recompute_isolation.py`**: 부분 재계산이
  지표를 갱신하지만 매매 판단을 실행하지 않는지 확인.
- **`test_r_2026_08_25_wo6_fetch_case_reorder.py`**: `fetch_confirmed_candle`
  케이스 A/B/C/D의 재배치 후 동작 확인. 다음 봉 존재 시 즉시 확정, 무거래
  봉은 `NO_TRADE` 표지 반환(가짜 봉 합성 없음), 케이스 B는 5초 안정화 1회
  후 확정 또는 재판정, 케이스 C 재시도, 재시도 실패 시 `None` 반환 확인.

네 테스트 모두 `scripts/regression_gate.sh`와 `.githooks/pre-push`에
포함되어야 한다.

---

## 9. 롤백 정책

- 롤백 대상: 현재 서버 HEAD `1404c1c`.
- 롤백 절차: 이번 세션의 옵션 A 절차 재사용(revert 커밋 후 push, force 없음).
- 롤백 트리거:
  - 배포 후 30분 내 유해 fallback 1건 발생.
  - 배포 후 30분 내 CRITICAL 발동.
  - 배포 후 30분 내 봉당 매매 판단 횟수 위반 1건.
  - 24시간 실측 중 봉당 매매 판단 횟수 위반 1건.
  - 24시간 실측 중 지표 이탈이 시드 오차 상한의 3배(최소 0.5원) 초과.

---

## 10. 관련 문서

- `docs/plans/2026-08-23-wo2-fetch-confirmed-hardening.md`: WO-2 v3 세
  차례 실패의 상세 기록. WO-6 개편의 근거 자료.
- `docs/operations/deploy-checklist.md`: 배포 절차 표준. WO-6도 이 절차를
  따른다. **개편 후 감사 시각 표시 변화 운영 주석 포함**.
- `docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md`: WO-1 사고 조사 자료.
- `.claude/context/project-rules.md`: 커밋과 배포 표준.

---

## 11. 승인 요청 항목

- §3.2 `get_closed_ts` 반환값 재정의 방향 승인.
- §3.5 `fetch_confirmed_candle` 케이스 재배치와 무거래 봉 합성 반환 최소
  수정안 승인.
- §4.1 `[SKIP-BAR]` 제거 승인 (기 승인 재확인).
- §4.2 봉당 매매 판단 1회 강제 승인 (검사 위치는 매매 판단 직전, 등록 주체는
  실시간 평가만, 자료구조는 `OrderedDict` + 상한 1000봉).
- §4.3 부분 재계산 지표/관문 분리 승인.
- §5.1 배포 전 병행 실행 방식 승인 (`--dry-run` 옵션 신설 여부 포함).
- §6 WO-2 재적용 계획 방향 승인. §6.4 유효성 확인(재판정 아님) 개념 승인.
- §8 회귀 테스트 4건 신설 승인.
- §9 롤백 정책 승인.

승인 이후에 구현을 시작한다. 승인 없이 구현하지 않는다.
