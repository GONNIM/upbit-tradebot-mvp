버전: v1.2026.10.01.1955 → v1.2026.10.02.0942

# WO-19 구현 보고 — 워밍업 감사 행 보존 (로컬 완료, 배포 대기)

- 작성: 2026-10-02 (KST)
- 커밋: `8fd26c1` (코드·시험·가이드), 보고 문서는 후속 docs 커밋
- 서버: 읽기만 했다. pull·재시작은 하지 않았다. 서버 HEAD `962bb46`, 화면 버전 `v1.2026.10.01.1955`, 기동 2026-10-01 20:10:55 KST (`results/server-state.txt`).
- 포지션·주문은 건드리지 않았다. 투자자 안내는 없다.

## 0. 먼저 알릴 사실 — 보유 포지션이 이미 청산됨

지시문은 "현재 KRW-JTO 318.018개 보유"를 전제로 했다. 확인해 보니 이 포지션은 2026-10-02 09:30 에 봇이 이미 매도했다.

- 매수: orders id 555, 08:00:12, 734원, 318.01810267개 (EMA_GC, bar=330)
- 매도: orders id 556, 09:30:11, 체결 평균 740원, 318.01810267개 (TRAILING_STOP_FIXED, bar=348, bars_held=18)
- 근거: journal `✅ SELL 체결 | qty=318.018103 price=742.00 pnl=1.09% bars_held=18`, `[OR] final FILLED ... side=SELL vol=318.01810267 avg=740.0`, audit_trades id 1177.

그래서 C절은 "봇이 산 포지션을 보유한 채 재시작하는 경우"를 코드로 분석했다. 예시 데이터는 방금 청산된 order 555 를 썼다.

## A. 조사

### A1. 결함 코드 (옛 코드 `27d83f2`)

- `engine/live_loop.py:1161` — 워밍업 버퍼를 채우며 봉마다 `engine.record_warmup_log(bar, "(완료 n/200)")` 를 부른다. 같은 함수는 `:1802`, `:1847` 에서도 불린다.
- `core/strategy_engine.py:1423` `record_warmup_log` — 포지션이 없으면 `insert_buy_eval(...)` (`:1473`), 있으면 `insert_sell_eval(...)` (`:1493`) 를 부른다. 이때 `checks={"status": "WARMUP", ...}`, `overall_ok=0` 을 넘긴다.
- `services/db.py:1061` — 기존 행 조회는 다음과 같다. `checks.status` 를 읽지 않는다.

  ```sql
  SELECT id, price, backfill_close FROM audit_buy_eval
  WHERE ticker=? AND bar_time=?
  ```

- `services/db.py:1126` — 기존 행이 있고 BACKFILL 이 아니면 "실시간 재판정" 으로 보고 실시간 컬럼 전체를 UPDATE 한다. 기존 행이 실제 판정인지 WARMUP 자리표시자인지 구분하지 않는다. SELL 쪽도 같다 (`:1280` 조회, `:1341` 재판정 UPDATE).
- 결과: 재기동하면 최근 200봉의 실제 BUY/SELL 평가 행이 WARMUP 자리표시자로 덮인다.

### A2. 최근 7일 집계 (KRW-JTO, journal 대조)

| 테이블 | 전체 행 | WARMUP 행 | 그중 실제 판정 뒤 덮인 행 |
|---|---|---|---|
| audit_buy_eval | 1,927 | 566 | 539 |
| audit_sell_eval | 319 | 0 | 0 |

- 판정 방법: WARMUP 행마다 같은 봉의 journal 기록을 봤다. 실시간 판정 기록(`[CONFIRMED] 봉 처리 완료 | ts=`)이 있고, 그보다 뒤에 `[AUDIT-UPDATE] BUY 실시간 재판정 | ... | bar_time=` 기록이 있으면 "덮임" 으로 셌다. 두 검색어 모두 journal 에 실재한다 (BUY 재판정 봉 1,157개).
- 예: id 73137 (09-25 09:35 봉) 은 실시간 판정 뒤 09-25 12:41:08 기동에서 덮였다.
- 보고 직전(09:5x)에 같은 스크립트를 다시 돌린 값은 1,926 / 563 / 536 이다. 7일 창이 앞으로 밀려 오래된 행이 빠졌기 때문이다 (`results/db-a2-7days.txt`).
- SELL 이 0건인 이유: 최근 7일 동안 봇이 산 포지션을 보유한 채 재기동한 적이 없다. 외부 매수 복원은 워밍업 뒤에 일어나므로 워밍업은 BUY 경로만 탔다.

### A3. 봇 매수 봉의 감사 행 (`results/db-a3-buy-bars.txt`)

| 매수 봉 (KST) | audit_buy_eval 행 | 현재 상태 | 매매 기록 |
|---|---|---|---|
| 10-01 14:10 | id 74864 | **덮임.** overall_ok=0, `⏳ WARMUP 진행 중 (완료 129/200)`, timestamp 10-01 20:11:03 (기동 시각) | audit_trades 1165, EMA_GC, 749원 |
| 10-02 03:35 | id 75021 | 정상. overall_ok=1, `🟢 BUY \| Golden \| bar=286` | audit_trades 1171, 747원 |
| 10-02 07:55 | id 75063 | 정상. overall_ok=1, `🟢 BUY \| Golden \| bar=330` | audit_trades 1174, 734원 |

audit_trades 는 덮이지 않는다. 그래서 매매 사실은 남아 있고, 매수 근거(평가 행)만 사라졌다.

## B. 구현

### B1. 규칙

- 워밍업 호출은 `warmup_placeholder=True` 로 기록한다 (`core/strategy_engine.py:1488`, `:1514`).
- 같은 bar_time 의 기존 행이 WARMUP 자리표시자(`checks.status == "WARMUP"`)일 때만 갱신한다. 결과는 `"updated_placeholder"` 이다.
- 기존 행이 실제 판정이면 건드리지 않는다. 결과는 `"kept"` 이다 (`services/db.py:1086~1087` BUY, `:1314~1315` SELL).
- 행이 없으면 자리표시자를 삽입한다. 결과는 `"inserted"` 이다 (`:1196`, `:1412`).
- 판별 함수는 `services/db.py:1002` `_is_warmup_placeholder_row` 이다.
- 실시간 판정이 WARMUP 자리표시자를 덮는 기존 동작은 바꾸지 않았다. 인자 기본값이 `False` 라서 실시간·BACKFILL 경로는 이전과 같다.
- `:1812`, `:1857` 의 다른 워밍업 호출도 같은 `record_warmup_log` 를 거치므로 같은 규칙을 따른다.

### B2. 기동 로그 1줄

`engine/live_loop.py:1148~1170` 에서 결과를 세고, 버퍼 채우기가 끝나면 한 줄을 남긴다.

```
[WARMUP] 감사 행 보존 | kept=N inserted=M updated_placeholder=K
```

기록이 실패한 행이 있으면 끝에 ` failed=n` 이 붙는다. 실패가 없으면 붙지 않는다.

### B3. 시험 (`tests/regressions/test_r_2026_10_02_wo19_warmup_audit_preserve.py`)

| # | 내용 | 새 코드 | 옛 코드 |
|---|---|---|---|
| 1 | 실제 판정 행이 있으면 행이 그대로이고 결과는 kept | 통과 | **실패** (행이 WARMUP 으로 바뀜) |
| 2 | WARMUP 행이 있으면 갱신하고 결과는 updated_placeholder | 통과 | 실패 (결과값 None) |
| 3 | 행이 없으면 삽입하고 결과는 inserted | 통과 | 실패 (결과값 None) |
| 4 | 워밍업 뒤 실시간 판정이 자리표시자를 덮음 | 통과 | 통과 (기존 동작) |
| 5 | (추가) SELL 경로도 실제 행 보존 | 통과 | 실패 (결과값 None) |
| 6 | (추가) 기동 로그 줄 존재 lint | 통과 | 실패 (줄 없음) |

- 새 코드 출력: `results/test-new-code.txt` (6건 OK).
- 옛 코드 출력: `results/test-old-code.txt` (`FAILED (failures=5)`). 시험 1 의 실패 메시지는 `AssertionError: Lists differ` 이다. 옛 코드가 실제 판정 행을 WARMUP 행으로 바꿨다는 뜻이다.

### B4. 이미 덮인 행

이미 덮인 행은 복원하지 않았다. 대신 `docs/operations/wo8-force-buy-verification-guide.md:272` 에 "기동 이전 봉의 BUY 평가 근거 찾기" 절을 넣었다. 근거는 journal 의 `EMA Buy Signal`·`Bar# action=` 줄과 engine_debug.log 의 `cross=` 줄에서 찾는다. audit_trades 는 덮이지 않는다는 점도 적었다.

### B5. 게이트와 단독 revert (`results/gate-and-revert.txt`)

- 임시 worktree 에서 실행했다. worktree 에는 `.env` 가 없다 (개수 0). 업비트 키는 더미 값, 텔레그램은 빈 값이다.
- HEAD `8fd26c1` 게이트: **275/275 통과**.
- `8fd26c1` 단독 revert: **충돌 없음.** 6개 파일이 바뀌고 py_compile 통과, 게이트 **269/269 통과**.

### B6. 커밋·push

- `git status` 로 확인했다. 스테이징된 파일은 6개다: `services/db.py`, `core/strategy_engine.py`, `engine/live_loop.py`, `pages/dashboard.py`, 운영 가이드, 시험 파일. 시험 파일은 `git add -f` 로 넣었다. 남은 미추적 파일은 원래 있던 13개뿐이다.
- 커밋: `8fd26c1`. 보고 문서 커밋은 그 뒤에 따로 했다. push 대상 수는 `git log origin/main..HEAD` 로 확인했다 (`commands.txt`).
- 서버 pull·재시작은 하지 않았다.

## C. 재시작 영향 (코드 읽기만)

### C0. 실제로 타는 경로

봇이 산 포지션을 보유한 채 재시작하면 코드상 의도된 경로는 `boot_seed` 이다. 그러나 지금 데이터로는 이 경로에 들어가지 못한다.

1. `engine/live_loop.py:689` `position.sync_from_wallet()` 이 지갑 잔고로 `has_position=True`, `qty` 를 정한다 (`core/position_state.py:96~102`).
2. 같은 함수가 `avg_price` 가 비어 있으므로 복구한다. 1순위는 `account_positions.entry_price`, 2순위는 Upbit `avg_buy_price` 이다 (`position_state.py:107~139`). 지금 `account_positions.entry_price` 는 0.0 이라 Upbit 값을 쓴다.
3. 같은 자리에서 `entry_ts` 가 비어 있으므로 **재시작 시각**으로 채운다 (`position_state.py:144~148`).
4. `live_loop.py:695` `_seed_entry_price_from_db` → `services/db.py:1814` `get_last_open_buy_order` 가 orders 를 읽는다. 시각 컬럼은 `executed_at` 을 고른다 (`db.py:1907~1913`). 그런데 KRW-JTO BUY 189건 전부 `executed_at` 이 NULL 이다 (`results/db-c-restart.txt`). 그래서 `entry_ts_iso` 가 빠진다 (`db.py:1850`).
5. `live_loop.py:714` 조건(`entry_ts is not None`)이 거짓이 된다. `apply_entry(source="boot_seed")` 는 불리지 않는다. `:728~732` 에서 ERROR 로그만 남긴다. 로그 문구는 "has_position=False 유지" 이지만 실제로는 1단계에서 정한 `has_position=True` 가 그대로 남는다.

### C1. 항목별 표

| 항목 | 재시작 뒤 | 근거 (파일:행) | 비고 |
|---|---|---|---|
| 수량 | **복구** | `live_loop.py:689` → `position_state.py:96~102` | 지갑 잔고 그대로 |
| 평균가 | **복구** (출처가 바뀜) | `position_state.py:107~139` | orders 가 아니라 `account_positions.entry_price` → Upbit `avg_buy_price`. 한 번에 산 포지션이면 값은 같다 (order 555 = 734원) |
| 매수 시각 (stale 기준) | **초기화** → 재시작 시각 | `position_state.py:144~148`, `db.py:1907~1913·1850`, `live_loop.py:714·728` | stale 판정은 `sell_filters.py:508` `current_time - entry_ts` |
| 진입 봉 (bars_held) | 초기화 뒤 audit 로 보정 | `position_state.py:455~456` (entry_bar None → 0), `strategy_incremental.py:1138~1155`, `db.py:1981·2014` | `min_holding_period=1` 이라 매도를 막지 않음 |
| trailing 최고가·무장 | **초기화** (None / False) | `position_state.py:44~45` 초기값, `apply_entry` 를 타더라도 `:252~255` 에서 초기화 | 다음 봉에서 최고가 다시 시작 (`position_state.py:367`), 무장은 익절 기준 재도달 시 (`sell_filters.py:273~`) |
| stale 최고가 | 초기화 → 첫 평가 때 현재가 | `position_state.py:52` 초기값, `:460~471` | |
| cooldown | **해당 없음** | `core/filters/buy_filters.py:13` (SlowEmaSurgeFilter 만 있음), `config.py:65·67` | 매매 cooldown 코드가 없다. `AUDIT_*_COOLDOWN_BARS=0` 은 감사 기록 샘플링 값이다 |
| hts_buy 플래그 | **복구** | `position_state.py:192~196` (`account_positions.meta`) | 지금 meta 는 `{}` |
| 손절·익절 기준가 | **복구** | `position_state.py:430` `get_pnl_pct`, `sell_filters.py:57` (SL), `:174` (TP), 비율은 `live_loop.py:773` 에서 조건 파일 재로드 | 평균가 기준으로 매 봉 계산하므로 평균가가 같으면 기준가도 같다 |

### C2. 초기화 항목의 영향

매수 시각이 재시작 시각으로 바뀌면 stale position 판정이 그만큼 늦어진다. 예를 들어 08:00 에 산 포지션을 12:00 에 재시작하면 stale 시계가 12:00 부터 다시 간다. 그러면 정체 포지션 매도가 최대 4시간 늦게 나온다. trailing stop 이 이미 무장된 상태였다면 무장이 풀린다. 이 경우 수익이 다시 익절 기준까지 올라야 trailing 이 다시 무장된다. 그 사이 수익이 줄어도 trailing 매도는 나오지 않는다. 손절·익절·Dead Cross 매도는 평균가와 지표로 판정하므로 그대로 작동한다. bars_held 는 audit 개수로 보정되고 `min_holding_period=1` 이라 매도를 막지 않는다.

### C3. WO-19 가 bars_held 보정에 주는 영향 — 없음

- `estimate_bars_held_from_audit` (`db.py:1981`) 는 마지막 BUY 의 `audit_trades.timestamp` 이후 `audit_sell_eval.timestamp` 행 수를 센다 (`db.py:2014`).
- 옛 코드: 워밍업이 최근 200봉 SELL 행을 덮거나 삽입하며 timestamp 를 재시작 시각으로 바꾼다. 매수 이전 봉 행까지 모두 세어진다.
- 새 코드: 매수 이후의 실제 SELL 행은 보존된다. 이 행의 timestamp 는 원래 매수 뒤 시각이므로 그대로 세어진다. 매수 이전 봉은 자리표시자가 새로 삽입되어(재시작 시각) 역시 세어진다.
- 그래서 두 코드의 개수는 같다. 둘 다 실제 보유 봉 수보다 크게(약 200) 세는 기존 특성이 있다. 이 값은 `min_holding_period` 판정과 감사 표기에만 쓰여 매도를 막지 않는다.

### C4. 별건으로 보고하는 사실 (수정하지 않음)

- orders 의 `executed_at` 이 비어 있어 봇 매수 포지션의 `boot_seed` 복원(`apply_entry`)이 실제로는 한 번도 타지 않는다. journal 보존 범위(2026-09-02~)에서 `source=boot_seed` 기록은 0건이다. 검색어는 `core/position_state.py` 의 `[POSITION-APPLY] source=` 로그에 실재한다.
- `live_loop.py:729` 의 ERROR 문구 "has_position=False 유지" 는 실제 동작(True 유지)과 다르다.
- 이 두 가지는 WO-19 범위 밖이다. 필요하면 별도 WO 로 다루기를 제안한다.

## D. 묶음 목록

- `report.md` (이 문서)
- `wo19-code.diff` (`git show 8fd26c1`)
- `results/test-new-code.txt`, `results/test-old-code.txt`
- `results/gate-and-revert.txt`, `results/wo19_revert_check.sh`
- `results/db-a2-7days.txt`, `results/db-a3-buy-bars.txt`, `results/db-c-restart.txt` 와 조회 스크립트 (`wo19_a2.py`, `wo19_a3.py`, `wo19_c*.py`)
- `results/server-state.txt`
- `commands.txt`
- `git-log.txt`
