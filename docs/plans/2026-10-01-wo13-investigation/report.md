# WO-13 조사 보고 — 미확정 봉 이중 평가 · 97봉 누락 · DB 잠금 경합 (읽기 전용)

- 작성일: 2026-10-01
- 성격: 원인 특정까지만 (코드 수정·수정 제안 없음)
- 기준: 서버 HEAD `e7927e6`, 코드 기준 `0c8e729`, 버전 v1.2026.09.30.1917, 서비스 시작 2026-10-01 09:55:59, ExecStart=`scripts/tradebot_boot.py`

**(a) 미확정 봉 이중 평가 — 원인은 `fetch_confirmed_candle` 케이스 A/B/C 가 아니라, 조정용 전체 조회의 첫 배치가 `end_ts` 를 쓰지 않아 형성 중인 봉을 받아 오는 것입니다. 발주는 BACKFILL 경로라 막혔고, 지표 직전값 오염은 없습니다.**
**(b) 97봉 누락 — "무거래/엔진 정지/수집 실패" 어디에도 해당하지 않는 기타입니다. 엔진 기동 직후 워밍업(200봉)과 첫 조정 조회(298봉)의 범위 차이로, 이미 실시간 처리된 과거 봉을 누락으로 판정한 것입니다. 기동할 때마다 반복됩니다.**
**(c) DB 잠금 경합 — 페이지 로드 측 `ensure_audit_settings_unique()` 가 `audit_settings`(184,028행)의 UNIQUE 인덱스를 매번 지우고 다시 만드는 동안, 엔진 워밍업의 `audit_buy_eval` 쓰기가 3초 대기를 넘긴 것입니다.**

---

## 0. 정기 점검 (세션 개시 표준 정지선 + §확인 4)

| 항목 | 예상 | 실측 |
|---|---|---|
| 로컬·서버 HEAD | `e7927e6` | `e7927e6` / `e7927e6` |
| 버전 | v1.2026.09.30.1917 | 로컬·서버 동일 |
| 서비스 시작 | 2026-10-01 09:55:59 | 일치, active |
| ExecStart | `tradebot_boot.py` | `argv[]=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py` |

| 사후 확증 | 결과 |
|---|---|
| 0번 JTO 묶임 중 SELL_REJECTED | `SELL_REJECTED` 0행. JTO 는 2026-09-30 23:24 묶임 해제 뒤 23:40 봇 EMA_DC 매도(740.0)로 정리됐고 현재 가용·묶임 0, `trading_paused=0`. 확증 조건이 사라졌습니다. |
| 5,000원 미만 HTS 증가 | WO-10 배포(2026-09-30 17:55:43) 이후 `[HTS-DETECT] HTS_BUY` 0건, HTS 감사 행 0건 — 잔고 증가 자체가 없어 미발생 |
| 강제 매수 원자 경로 | WO-8b 배포(2026-09-18 16:40) 이후 `force_buy` 0건 — 미발생. 이전 5건(09-13~14)은 WO-8b 이전 |
| 승격 가드 `class=` | WO-10 이후 first_bar_guard 0, pos_desync_promoted 0, integrity_gap 0 |

---

## (a) 미확정 봉 이중 평가

### 사례 2건

| 시각 | 확정 대상 봉 (`[CLOCK] 봉 확정`) | 함께 평가된 미확정 봉 | 그 봉의 REST 응답 |
|---|---|---|---|
| 2026-09-30 16:50:05 | 16:45 | 16:50 (5초 경과) | `[REST] 최신 확정 봉 ✅ \| ts=16:50 \| close=763 \| high=763 \| low=763 \| volume=18.49` |
| 2026-09-30 20:10:05 | 20:05 | 20:10 (5초 경과) | `[REST] 최신 확정 봉 ✅ \| ts=20:10 \| close=749 \| high=749 \| low=749 \| volume=400.53` |

### 경로 (로그 순서와 코드 라인)

1. `fetch_confirmed_candle` 은 **확정 대상 봉만** 올바르게 확정했습니다. 두 사례 모두 케이스 A(다음 봉 존재 → 즉시 확정)입니다.
   - `core/rest_reconcile.py:673~688` — `[RECONCILE] 확정 종가 (다음 봉 존재) ✅ | ts=16:45`, `ts=20:05`
2. 이어서 조정용 전체 조회를 `end_ts=closed_ts` 로 부릅니다.
   - `engine/live_loop.py:1086~1091` — `safe_fetch_rest(..., end_ts=closed_ts, total_count=RECONCILE_LOOKBACK_BARS)`, 로그 `[REST] 다중 호출 시작 | total_count=400 end=16:45`
3. 그러나 첫 배치는 `end_ts` 를 쓰지 않고 `to` 없이 조회합니다.
   - `core/rest_reconcile.py:225~235` — `if batch_num == 1: df = pyupbit.get_ohlcv(ticker=..., interval=..., count=batch_size)` (주석: "to 파라미터 없음 → Upbit 확정 봉만 반환")
   - 실제 업비트 응답에는 **아직 닫히지 않은 현재 봉**이 들어 있습니다. 두 사례의 최신 봉은 시작 5초 뒤의 봉이고, 고가·저가가 같거나 거래량이 작습니다.
4. 로컬 시계열에 없는 봉이므로 `inserted` 로 분류됩니다.
   - `core/rest_reconcile.py:404~` `reconcile_series` — `if ts not in local_series.index: inserted_ts.append(ts); changed_ts.append(ts)`, 로그 `changed=2 inserted=2 | 범위: 16:45 ~ 16:50`
5. BACKFILL 대상에서 확정 대상 봉만 빼고 나머지를 "누락 봉"으로 평가합니다. 확정 대상 봉보다 **늦은** 봉은 거르지 않습니다.
   - `engine/live_loop.py:1151` — `backfill_ts_list = [ts for ts in changed_ts_list if ts != closed_ts]`, 로그 `[BACKFILL] 1개 누락 봉 평가 | ts=16:50 | close=763`
6. 그 뒤 확정 대상 봉(16:45 / 20:05)을 실시간으로 평가합니다. 다음 주기에 미확정이던 봉(16:50 / 20:10)은 확정 봉으로 다시 실시간 평가됩니다. 그래서 같은 봉이 두 번 평가되고 Bar# 가 두 번 찍힙니다(16:50:07 Bar#202 07:50Z → Bar#203 07:45Z, 20:10:05 Bar#204 11:10Z → 20:10:06 Bar#205 11:05Z).

### 발주 차단 재확인

- 미확정 봉 평가는 `backfill_mode=True` 입니다(`[ENGINE-ENTRY] … backfill_mode=True`).
- 봉당 매매 판단 1회 관문 `core/strategy_engine.py:817` 은 BACKFILL 을 검사에서 제외하지만, 주문 실행은 `core/strategy_engine.py:856~873` 에서 `if not backfill_mode:` 일 때만 `self.execute()` 를 부릅니다. BACKFILL 은 `[BACKFILL] 실제 주문 건너뜀` 경로입니다.
- 실시간 평가 이력 등록도 `not backfill_mode` 일 때만입니다(`core/strategy_engine.py:884~891`). 따라서 같은 봉의 실시간 평가는 막히지 않습니다.
- 20:10:05 미확정 봉 평가 결과는 `action=SELL` 이었으나 `UPBIT-ORDER` 0건입니다. 당시 일시정지 중이었지만, 발주를 막은 것은 BACKFILL 분기입니다(일시정지 스킵 로그 `[PAUSE] 실주문 스킵` 은 이 봉에서 찍히지 않고 다음 실시간 봉 20:10:06 에서 찍힘).
- 16:50:05 미확정 봉 평가는 `action=HOLD`(외부 매수 첫 봉 방어)였습니다.

### 지표 상태 오염 여부

| 사례 | 백업 (`[BACKFILL] 지표 상태 백업`) | 복원 (`[BACKFILL] 지표 상태 복원 완료`) | 판정 |
|---|---|---|---|
| 16:50:05 | prev_ema_fast=759.73 prev_ema_slow=756.51 | 759.73 / 756.51 | 오염 없음 |
| 20:10:05 | prev_ema_fast=755.40 prev_ema_slow=756.79 | 755.40 / 756.79 | 오염 없음 |

- 백업 범위는 지표 직전값(`prev_ema_*`, `prev_macd`, `prev_signal`, 매수·매도 분리 EMA)뿐입니다(`engine/live_loop.py:1162~1185`).
- 포지션의 Trailing 고점(`highest_price`)은 백업 대상이 아니며, 매도 평가에서 `position.update_highest_price(current_price)`(`core/strategy_incremental.py:1255`)로 갱신될 수 있습니다. 이번 두 사례는 영향이 없습니다. 16:50:05 는 첫 봉 방어로 이 줄 전에 HOLD 반환했고, 20:10:05 의 미확정 종가 749 는 기존 고점보다 낮아 고점이 바뀌지 않습니다(고점은 오르기만 함).
- 감사 기록: 미확정 봉 평가는 `[AUDIT-INSERT] SELL BACKFILL only (missing_bar) | backfill_close=763 / 749` 로 `backfill_*` 열에 남습니다. 20:10:05 행은 `reason=SELL_SIGNAL` 로 기록됐습니다.

---

## (b) 97봉 누락 (약 8시간)

### 구간 특정

- 2026-09-30 18:10:11 `[BACKFILL] 97개 누락 봉 평가 시작` (18:02:06 엔진 시작 뒤 첫 조정)
- 대상: **2026-09-29 16:30 ~ 2026-09-30 00:30 KST**, 97봉 (`ts=2026-09-29 16:30:00 KST | close=754` ~ `ts=2026-09-30 00:30:00 KST | close=749`)

### 대조

| 확인 | 결과 | 판정 근거 |
|---|---|---|
| 업비트 REST 응답 | 조정 조회가 이 구간을 모두 받아 옴: `[REST] 다중 호출 완료 \| total=298 batches=2 \| 2026-09-29 16:30 ~ 2026-09-30 18:05` | 무거래 아님 |
| 엔진 로그 | 그 구간(09-29 16:30~09-30 00:40) 원래 실시간 `[CONFIRMED] 봉 처리 완료` 98건 — 엔진 가동 중 | 엔진 정지 아님 |
| audit 행 | `audit_buy_eval` 97행·`audit_sell_eval` 97행 존재 | 수집 실패 아님 |
| 엔진 로컬 시계열 | 18:02:09 워밍업이 200봉만 적재: `2026-09-30 00:35 ~ 18:00` | **누락 판정 원인** |

### 원인

- 엔진은 재시작 때 로컬 시계열을 워밍업 200봉(`count=201`, 마지막 봉 제거)으로 새로 만듭니다.
- 첫 조정 조회는 400봉을 요청해 298봉을 받았고, 그중 워밍업 시작(00:35)보다 이른 98봉이 로컬에 없으므로 `inserted` 로 분류됩니다(`changed=98 inserted=98`). 확정 대상 봉 1개를 빼고 97봉이 BACKFILL 됩니다(`engine/live_loop.py:1151`).
- 즉 실제로 빠진 봉이 아니라, **이미 실시간 처리된 과거 봉을 재평가한 것**입니다.

### 반복성

| 엔진 시작 | 첫 조정 BACKFILL |
|---|---|
| 2026-09-18 16:40 재시작 → 17:31:40 | 116개 |
| 2026-09-30 16:33:05 → 16:40:11 | 96개 |
| 2026-09-30 18:02:06 → 18:10:11 | 97개 |
| 2026-09-30 19:44:28 → 19:50:10 | 97개 |
| 2026-10-01 09:56:08 → 10:00:11 | 92개 |

### 부수 영향 (감사 기록)

- 18:10 의 재평가는 부팅 복원 직후(포지션 있음)에 실행됐습니다. 그래서 **봇이 JTO 를 보유하지 않았던 2026-09-29 16:30~19:20 의 35봉에 대해 `audit_sell_eval` 행을 새로 만들었습니다**(생성 시각 2026-09-30 18:10:12~18:10:19, `backfill_type=missing_bar`, price 빈 값, 예: id 15390 bar_time 09-29 16:30 `backfill_reason=SELL_SIGNAL`). 같은 봉의 원래 실시간 기록은 `audit_buy_eval` 35행입니다.
- 실제 보유 구간(19:25~00:30)의 62봉은 `backfill_*` 열이 다음 기동(19:50)에서 다시 덮어써졌습니다. 원래 실시간 열은 WO-1 설계대로 보존됩니다.
- 2026-09-30 클레임 조사(`docs/plans/2026-09-30-jto-dc-claim/`)의 표는 이 덮어쓰기(18:10) 이전에 조회한 값입니다.

---

## (c) DB 잠금 경합 (2026-09-30 19:44:33 · 19:44:37)

### 겹친 지점

| 시각 | 페이지 로드 측 (운영자 새로고침) | 엔진 측 (워밍업) |
|---|---|---|
| 19:44:26 | `[AUTO-RESUME] LIVE 자동 재개 시도` → 엔진 시작 | |
| 19:44:29 | `[migrate] ensure_audit_settings_bar_time OK` (`ensure_all_schemas` 진행 중) | |
| 19:44:29~39 | **`ensure_audit_settings_unique()` 실행 구간** (로그 없음 — 다음 `[migrate] ensure_audit_buy_eval_bar_time OK` 가 19:44:39) | 19:44:30 워밍업 REST 200봉 → `record_warmup_log` 가 `audit_buy_eval` 에 기록 시작 (19:44:30~39, 166행 생성) |
| 19:44:30, 19:44:35 | | `[SETTINGS-SNAPSHOT] ❌ Failed: ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint` |
| 19:44:33, 19:44:37 | | `ERROR … ❌ WARMUP 로그 기록 실패: database is locked` |
| 19:44:39 | 나머지 마이그레이션 OK | `Buffer seeded` |

### 원인

- `services/init_db.py:755~778` `ensure_audit_settings_unique()` 는 호출될 때마다 `DROP INDEX IF EXISTS idx_audit_settings_unique` → `CREATE UNIQUE INDEX … ON audit_settings(ticker, interval_sec, bar_time)` 를 실행합니다. `ensure_all_schemas`(`services/init_db.py:976`)가 로그인·대시보드 로드·기동마다 부르므로 매번 인덱스를 다시 만듭니다.
- `audit_settings` 는 184,028행입니다. 인덱스 생성 동안 쓰기 잠금을 잡습니다.
- 연결은 자동 커밋(`isolation_level=None`, `services/init_db.py:377~383` `_connect`)이라 DROP 과 CREATE 사이에 UNIQUE 인덱스가 없는 순간이 생깁니다. 이때 엔진의 설정 스냅샷(`ON CONFLICT` upsert)이 실패한 것이 19:44:30·19:44:35 의 `[SETTINGS-SNAPSHOT] ❌` 2건입니다.
- 인덱스 생성 중 엔진 워밍업의 `audit_buy_eval` 쓰기가 잠금 대기 3초(`busy_timeout=3000`)를 넘겨 2건 실패했습니다.

### 다른 기동과의 비교

| 기동 | 인덱스 재생성 구간 (앞뒤 migrate 로그) | 워밍업 쓰기 시작 | 겹침 | 잠금 오류 |
|---|---|---|---|---|
| 2026-09-30 18:02 (첫 접속 재개) | 18:02:07 → 18:02:08 (약 1초) | 18:02:09 | 없음 | 0 |
| **2026-09-30 19:44 (새로고침 재개)** | **19:44:29 → 19:44:39 (약 10초)** | **19:44:30** | **있음** | **2** |
| 2026-10-01 09:56 (기동 스크립트) | 09:56:03 → 09:56:05 (약 2초) | 09:56:09 | 없음 | 0 |

- 단독일 때 1~2초인 인덱스 재생성이 워밍업 쓰기와 겹친 19:44 에만 10초로 늘었습니다. WO-12 기동 방식(10-01)에서는 마이그레이션이 워밍업 전에 끝나 겹치지 않았습니다.
- `[SETTINGS-SNAPSHOT] ❌ Failed: ON CONFLICT` 는 journal 보존분(08-30~)에서 3건(09-14 10:46:01, 09-30 19:44:30, 19:44:35)입니다. 09-14 건도 같은 인덱스 재생성 순간과 겹친 것으로 보이나 이번 조사에서 확인하지 않았습니다.

### SQLite 설정 실측

| 항목 | 값 | 출처 |
|---|---|---|
| journal_mode | `wal` | `PRAGMA journal_mode` (읽기 전용 조회) |
| busy_timeout | 연결마다 `PRAGMA busy_timeout=3000` (3초). `sqlite3.connect(timeout=30)` 은 이 PRAGMA 로 덮어써짐 | `services/db.py:35~45` `get_db`, `services/init_db.py:377~383` `_connect` |
| DB 파일 | 710,529,024 바이트 (2026-10-01 10:49 기준) | `ls -la` |

WAL 모드는 읽기와 쓰기를 동시에 허용하지만 쓰기는 한 번에 하나입니다. 인덱스 생성처럼 오래 쓰기 잠금을 잡는 작업이 있으면 다른 쓰기는 기다려야 합니다.

---

## 실행 명령 (모두 읽기 전용)

- 정지선: `git log --oneline -3; git rev-parse --short HEAD`, 서버 `git -C /root/upbit-tradebot-mvp log --oneline -3`, `systemctl show tradebot -p ExecMainStartTimestamp -p ExecStart`, `systemctl is-active tradebot`
- 사후 확증: `sqlite3 "file:…?mode=ro"` 로 `audit_trades`(type LIKE '%REJECTED', reason='force_buy', HTS 행), `account_positions`, `users`; `journalctl -u tradebot --since … | grep -F "[HTS-DETECT] HTS_BUY" / "[POS-DESYNC] class=" / "[LIMIT-FILL] apply_entry"`
- (a): `journalctl -u tradebot --since "2026-09-30 16:50:00" --until "2026-09-30 16:50:09"` 및 `20:10:00~20:10:08` 구간을 `grep -E "CLOCK|확정 종가|다중 호출|최신 확정 봉|변경 감지|BACKFILL|ENGINE-ENTRY|Bar#|UPBIT-ORDER|PAUSE|AUDIT-INSERT"`; 코드 `core/rest_reconcile.py:225~235, 404~470, 640~700`, `engine/live_loop.py:1080~1160`, `core/strategy_engine.py:805~895`
- (b): `journalctl … --since "2026-09-30 18:02:00" --until "18:02:15"`, `--since "18:10:00" --until "18:10:40"` 의 WARMUP·다중 호출·BACKFILL 줄; 다른 기동 직후 `누락 봉 평가 시작` 첫 줄; `audit_sell_eval`·`audit_buy_eval` 의 해당 구간 count·timestamp·backfill_* 분포
- (c): `journalctl … --since "2026-09-30 19:44:20" --until "19:44:40"`; `audit_buy_eval` 19:44 생성 행 수; `SELECT count(*) FROM audit_settings`; `PRAGMA journal_mode; PRAGMA busy_timeout`; `journalctl --since "2026-08-30" | grep -F "SETTINGS-SNAPSHOT] ❌ Failed: ON CONFLICT"`; 코드 `services/init_db.py:377~383, 755~778, 970~980`
