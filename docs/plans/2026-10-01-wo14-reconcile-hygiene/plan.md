# WO-14 계획서 — 조정(Reconcile) 위생: 인덱스 재생성 제거 · 첫 조정 범위 정합 · 미확정 봉 BACKFILL 제외 · BACKFILL Trailing 상태 보존 (승인본)

- 작성일: 2026-10-01
- 상태: **승인 완료 (E1 포함으로 변경, E2·E3·E5 진행, E4 → WO-15, E6 배포 별도 지시)** — 구현 착수, 커밋 4건 (c)→(b)→(a)→(E1)
- 근거: `docs/plans/2026-10-01-wo13-investigation/report.md` (WO-13 조사 결과 확정)
- 기준 코드: 서버·로컬 HEAD `b029e50` (코드 기준 `0c8e729`), v1.2026.09.30.1917

---

## 0. 한 줄 요약

WO-13 에서 찾은 세 원인을 각각 한 커밋으로 고치고, BACKFILL 재평가가 Trailing 상태를 바꾸지 않도록 커밋 하나를 더합니다(E1). (c) 인덱스를 매번 다시 만들지 않게 하고, (b) 엔진 기동 직후 이미 처리한 과거 봉을 누락으로 보지 않게 하고, (a) 아직 닫히지 않은 봉을 BACKFILL 하지 않게 합니다. 매매 판정 로직은 바꾸지 않습니다.

## 1. 원칙

1. **매매 판정 로직 무변경.** 필터, `Action` 결정, 발주, 봉당 1회 관문(`core/strategy_engine.py:817`), BACKFILL 발주 억제(`:856~873`)는 그대로 둡니다. 바꾸는 것은 마이그레이션 동작과 BACKFILL 대상 선정뿐입니다.
2. **커밋 4건, 각 단독 revert.** 네 변경은 서로 다른 파일 위치를 고칩니다. (a)·(b)·(E1)은 같은 파일(`engine/live_loop.py`)이지만 다른 위치(1126 부근 / 1151 부근 / 1162 이후 백업·복원 블록)라 서로의 문맥 줄에 닿지 않게 둡니다. 커밋마다 `pages/dashboard.py` 버전 줄이 바뀌므로, 앞선 커밋을 단독 revert 할 때는 버전 줄 한 곳만 충돌합니다(WO-9 와 같은 방식으로 현재 버전 유지로 해결).
3. **과거 데이터 무수정.** WO-13 (b)에서 잘못 생성된 `audit_sell_eval` 35행(2026-09-29 16:30~19:20, id 15390~, 생성 2026-09-30 18:10:12~18:10:19, `backfill_type=missing_bar`, price 빈 값)은 고치지 않고 이 문서에 기록만 합니다. 같은 봉의 원래 실시간 기록은 `audit_buy_eval` 35행입니다.

## 2. 항목별 변경안

### (c) 인덱스 재생성 제거 — 커밋 1

**현재**: `services/init_db.py:755~778` `ensure_audit_settings_unique()` 는 호출될 때마다 `DROP INDEX IF EXISTS idx_audit_settings_unique` → `CREATE UNIQUE INDEX IF NOT EXISTS … ON audit_settings(ticker, interval_sec, bar_time)` 를 실행합니다. `ensure_all_schemas`(`:976`)가 로그인·대시보드 로드·기동마다 부릅니다. `audit_settings` 184,028행이라 재생성에 단독 1~2초, 워밍업 쓰기와 겹치면 10초가 걸렸고, DROP~CREATE 사이에는 UNIQUE 인덱스가 없어 설정 스냅샷 upsert 가 실패했습니다(2026-09-30 19:44:30·35).

**변경**
- 인덱스가 이미 있고 목표와 같으면 아무것도 하지 않습니다.
  - 목표: 이름 `idx_audit_settings_unique`, `unique=1`, 열 순서 `(ticker, interval_sec, bar_time)`
  - 확인: `PRAGMA index_list(audit_settings)` 에서 이름과 `unique` 값, `PRAGMA index_info(idx_audit_settings_unique)` 에서 열 순서
- 인덱스가 없으면 `CREATE UNIQUE INDEX IF NOT EXISTS` 만 실행합니다(DROP 없음).
- 인덱스가 있지만 열 구성·unique 가 다르면(옛 timestamp 기준 등) **기존처럼** DROP → CREATE 로 재생성하고, 그때만 `[migrate] ensure_audit_settings_unique 재생성 (기존 열=…)` 경고를 남깁니다.
- 결과 로그: 건너뜀은 WO-10 방식대로 프로세스당 1회 `[migrate] ensure_audit_settings_unique OK (user_id=…)`(`@_log_migrate_ok` 적용), 재생성은 매번 경고.

**변경 파일·함수**: `services/init_db.py` `ensure_audit_settings_unique()` (755~778), `pages/dashboard.py` 버전 줄

**재현 테스트** (`tests/regressions/test_r_2026_10_xx_wo14c_index_idempotent.py`)
1. 목표 인덱스가 있는 DB 에서 `ensure_audit_settings_unique()` 두 번 호출 → 실행 SQL 에 `DROP INDEX` 0건(`sqlite3` `set_trace_callback` 으로 수집), 인덱스 유지
2. 인덱스가 없는 DB → `CREATE UNIQUE INDEX` 1회, 이후 존재
3. 열 구성이 다른 옛 인덱스(`(ticker, interval_sec, timestamp)`) → DROP·CREATE 로 목표 구성으로 바뀜 + 경고 로그
4. 다른 연결이 설정 스냅샷 upsert(`ON CONFLICT(ticker, interval_sec, bar_time)`)를 반복하는 동안 `ensure_audit_settings_unique()` 를 반복 호출 → upsert 실패 0건

### (b) 첫 조정 조회 범위 정합 — 커밋 2

**현재**: 엔진 기동 때 로컬 시계열은 워밍업 200봉으로 새로 만듭니다(`engine/live_loop.py:926~980`). 첫 조정 조회는 `RECONCILE_LOOKBACK_BARS=400`(`config.py:112`)을 요청해 298봉을 받습니다(`engine/live_loop.py:1086~1091`). 워밍업 시작보다 이른 봉이 `reconcile_series`(`:1126`)에서 `inserted` 로 분류되어 BACKFILL 됩니다(`:1151`). 기동마다 92~116봉이 재평가되고, 부팅 복원으로 포지션이 있으면 보유 전 구간에도 `audit_sell_eval` 행이 생깁니다.

**두 안**

| 안 | 방법 | 장점 | 단점 |
|---|---|---|---|
| b-1 | 첫 조정의 `total_count` 를 워밍업 적재 범위(`len(local_series)`) 이내로 줄임 | 조회량 감소 | 첫 조정만 고치면 **두 번째 조정**(다시 400 요청)에서 같은 과거 봉이 `inserted` 로 나타나 BACKFILL 이 한 봉 뒤로 밀릴 뿐입니다. 막으려면 모든 조정의 조회 범위를 로컬 길이에 묶어야 하고, `RECONCILE_LOOKBACK_BARS` 의 원래 목적(EMA200 안정화용 이력 확보)과 충돌합니다. |
| **b-2 (권고)** | `reconcile_series` 호출 직전(`:1126` 앞)에 `rest_df` 를 로컬 시계열 시작 시각 이후로 자름: `rest_df = rest_df[rest_df.index >= local_series.index[0]]` (로컬이 비어 있으면 자르지 않음) | 한 줄. 모든 조정에 같은 규칙이 적용되어 "엔진이 처리한 적 없는 과거 봉"은 언제나 누락 후보에서 빠집니다. 로컬 범위 안의 진짜 누락·변경 봉은 그대로 BACKFILL 됩니다. | 로컬 시계열이 기동 이후로 뒤로 늘어나지 않습니다(지금도 `MAX_LOCAL_SERIES_LEN=500` 으로 잘리므로 실익 없음). |

**권고: b-2.** 변경이 작고, 첫 조정뿐 아니라 이후 조정에서도 같은 문제가 다시 생기지 않습니다.

**변경 파일·함수**: `engine/live_loop.py` `run_live_loop()` 조정 블록 — `reconcile_series` 호출(`:1126`) 직전 1~3줄 + `[RECONCILE] 로컬 시작 이전 봉 제외 | n=… local_start=…` INFO 로그 1줄, `pages/dashboard.py` 버전 줄

**재현 테스트** (`tests/regressions/test_r_2026_10_xx_wo14b_first_reconcile_range.py`)
1. 로컬 200봉(00:35~18:00) + REST 298봉(전날 16:30~18:05) → BACKFILL 대상 0~1봉(로컬 범위 안 새 봉 18:05 는 확정 대상 봉이라 제외 → 0)
2. 포지션 보유 상태로 기동(부팅 복원 직후) → 보유 전 구간(로컬 시작 이전) `audit_sell_eval` 신규 행 0
3. 로컬 범위 안의 진짜 누락 봉(예: 로컬에서 한 봉 제거) → 그 봉만 BACKFILL 1
4. 로컬이 빈 경우 → 자르지 않음(기존 동작)

### (a) 미확정 봉 BACKFILL 제외 — 커밋 3

**현재**: 조정 조회 첫 배치가 `end_ts` 없이 조회해(`core/rest_reconcile.py:225~235`) 아직 닫히지 않은 봉(확정 대상 봉보다 늦은 봉)을 받아 옵니다. 그 봉이 `inserted` 로 분류되고, BACKFILL 필터 `engine/live_loop.py:1151` `[ts for ts in changed_ts_list if ts != closed_ts]` 는 확정 대상 봉만 빼므로 미확정 봉이 평가됩니다(2026-09-30 16:50:05, 20:10:05). 발주는 BACKFILL 분기로 막히지만, 미확정 종가로 감사 행(`backfill_*`)이 남고 매도 평가 경로에서 Trailing 고점이 갱신될 수 있습니다.

**두 안**

| 안 | 방법 | 장점 | 단점 |
|---|---|---|---|
| **a-1 (권고)** | `:1151` 바로 뒤에 한 줄: `backfill_ts_list = [ts for ts in backfill_ts_list if ts <= closed_ts]` (확정 대상 봉보다 늦은 봉은 아직 확정되지 않았으므로 제외) | 한 줄, 영향 범위가 BACKFILL 대상 선정뿐. 다음 주기에 그 봉이 확정 대상 봉이 되면 정상 실시간 평가됨 | 미확정 봉이 `reconcile_series` 를 거쳐 로컬 시계열에는 들어갑니다. 다음 주기 REST 확정값으로 덮어써지므로(`changed`) 남지 않지만, 한 주기 동안 로컬에 미확정 종가가 있습니다(현재도 같은 동작). |
| a-2 | `core/rest_reconcile.py` `fetch_candles_rest_full` 첫 배치에 `end_ts` 적용(`to=end_ts + 봉 간격`) | 미확정 봉을 아예 받지 않음 — 근본 처방. 같은 함수를 쓰는 VERIFY 조회도 함께 정리 | 공용 함수라 영향 범위가 넓음(워밍업 `end_ts=None`, VERIFY, 재시도 경로 `engine/live_loop.py:1422` `end_ts=now_utc()`). 업비트 `to` 경계(포함/제외)와 KST/UTC 변환을 다시 검증해야 함. Issue #8(미확정 종가) 계열 회귀 위험 |

**권고: a-1.** 이번 라운드는 BACKFILL 대상 선정만 고칩니다. a-2 는 별도 WO 로 검토합니다(승인 항목 E3).

**변경 파일·함수**: `engine/live_loop.py` `run_live_loop()` BACKFILL 대상 선정(`:1151` 뒤 1줄 + 제외 시 `[BACKFILL] 미확정 봉 제외 | ts=… closed_ts=…` INFO 로그), `pages/dashboard.py` 버전 줄

**재현 테스트** (`tests/regressions/test_r_2026_10_xx_wo14a_unconfirmed_bar.py`)
1. REST 응답에 형성 중 봉(closed_ts + 5분)이 포함돼도 BACKFILL 대상 0
2. 그 봉으로 매도 평가가 일어나지 않아 `position.highest_price` 미갱신(Trailing 무장 상태에서 형성 중 종가 > 기존 고점인 경우로 확인)
3. 그 봉의 `audit_sell_eval`/`audit_buy_eval` 신규 행·`backfill_*` 갱신 0
4. 확정 대상 봉보다 이른 진짜 누락 봉은 그대로 BACKFILL (기존 동작 유지)

### (E1) Trailing 상태 BACKFILL 백업·복원 — 커밋 4 (포함, 정책 확정)

**정책 (2026-10-01 확정)**: BACKFILL 재평가는 지표를 바로잡는 작업이며 포지션 상태를 바꾸지 않는다. 과거 누락 봉의 가격은 실시간에 보지 못한 가격이므로 Trailing 고점에 반영하지 않는다.

**위험 (확인된 사실)**
- BACKFILL 전 백업(`engine/live_loop.py:1162~`)은 지표 직전값(`prev_ema_*`, `prev_macd`, `prev_signal`, 매수·매도 분리 EMA)만 저장·복원합니다.
- 매도 평가 경로의 `position.update_highest_price(current_price)`(`core/strategy_incremental.py:1255`, 매수 측 `:435`)는 BACKFILL 재평가에서도 실행됩니다. Trailing 이 무장된 상태에서 재평가 봉의 종가가 기존 고점보다 높으면 고점이 올라가고 복원되지 않습니다.
- (a)·(b)가 들어가도 "로컬 범위 안의 진짜 누락·변경 봉" 재평가에서는 같은 일이 생길 수 있습니다.

**변경**
- 지표 직전값과 같은 방식(백업 → 재평가 → 복원)으로 position 의 5개 필드를 백업·복원 대상에 추가합니다: `highest_price`, `highest_since_entry`, `trailing_armed`, `trailing_fixed_amount`, `trailing_activation_price`.
- 복원 시 값이 바뀌어 있었으면 INFO 로그 1줄: `[BACKFILL] trailing 상태 복원 | highest old→new 되돌림` (관측용, 바뀐 필드 병기).
- 판정 로직은 바꾸지 않습니다. 실시간 봉의 고점 갱신은 기존대로입니다.

**변경 파일·함수**: `engine/live_loop.py` `run_live_loop()` BACKFILL 백업 블록(`:1162~`)과 복원 블록, `pages/dashboard.py` 버전 줄

**재현 테스트** (`tests/regressions/test_r_2026_10_01_wo14e1_backfill_trailing_restore.py`)
1. Trailing 무장 상태에서 BACKFILL 봉 종가 > 기존 고점 → 재평가 뒤 고점이 원래 값으로 복원 + 복원 로그 1줄
2. 무장 전 상태 → 5개 필드 변화 없음, 복원 로그 없음
3. 실시간 봉(BACKFILL 아님)에서는 고점 갱신이 기존대로 됨 (회귀 확인)
4. 포지션 없음 상태 → 백업·복원이 예외 없이 지나감

### 관련 관찰 (이번 범위 밖, 기록만)

- 워밍업도 같은 첫 배치(`end_ts=None`)를 씁니다. "+1개 요청 후 마지막 봉 제거"(`engine/live_loop.py:927, 958~980`)를 의도했으나 실제 수신이 요청보다 적어(201 → 200) 매 기동 `[WARMUP] 마지막 봉 유지 (여유분 없음)` 이 찍히고, **형성 중 봉이 지표 시드에 들어갑니다**(예: 2026-09-30 18:02:09 마지막 봉 18:00, 시작 2분 경과). 조정 조회도 400 요청에 298 수신입니다. 요청 수보다 적게 받는 원인은 이번에 조사하지 않았습니다 → **WO-15 (읽기 전용 조사, WO-14 바로 다음)** 로 backlog 등록.

## 3. 변경 파일 요약

| 커밋 | 파일 | 위치 |
|---|---|---|
| 1 (c) | `services/init_db.py`, `pages/dashboard.py`, 테스트 1개 | `ensure_audit_settings_unique()` 755~778 |
| 2 (b) | `engine/live_loop.py`, `pages/dashboard.py`, 테스트 1개 | `reconcile_series` 호출 직전 (`:1126` 앞) |
| 3 (a) | `engine/live_loop.py`, `pages/dashboard.py`, 테스트 1개 | BACKFILL 대상 선정 (`:1151` 뒤) |
| 4 (E1) | `engine/live_loop.py`, `pages/dashboard.py`, 테스트 1개 | BACKFILL 백업 블록(`:1162~`)·복원 블록 |

필터, 전략, 발주, 포지션 상태 코드(`core/strategy_*`, `core/filters/*`, `core/trader.py`, `core/position_state.py`)는 수정 대상이 아닙니다.

## 4. 검증

1. 로컬: 커밋마다 `py_compile`, 재현 테스트, 회귀 게이트(.env 격리). 커밋별 단독 revert 를 실제로 해 보고 남은 테스트 통과 확인.
2. 배포 후 **기동 1회**(WO-12 기동 스크립트, 대시보드 접속 없이)로 실측:
   - (b) 첫 조정 `[BACKFILL] N개 누락 봉 평가 시작` 의 N — 기대 0 (또는 `[BACKFILL]` 줄 없음), `[RECONCILE] 로컬 시작 이전 봉 제외 | n=…` 1줄
   - (c) 기동 시 인덱스 재생성 경고 부재, `[migrate] ensure_audit_settings_unique OK` 1회, `database is locked`·`[SETTINGS-SNAPSHOT] ❌ Failed: ON CONFLICT` 0
   - (a) 관측 30분 동안 `[BACKFILL] 누락 봉 평가 | ts=` 가 확정 대상 봉보다 늦은 봉으로 찍히지 않음, `[BACKFILL] 미확정 봉 제외` 가 나오면 그 봉의 감사 행 미생성 확인
   - (E1) `[BACKFILL] trailing 상태 복원` 이 찍히면 그 직후 Trailing 고점이 BACKFILL 전 값과 같은지 확인 (BACKFILL 이 0이면 미발생 정상)
   - 공통: 결함 태그(`class=pos_desync_promoted`·`integrity_gap`·SKIP-BAR·POLLUTED·엔진 Traceback) 0, Bar# 5봉
3. 그 뒤 운영자 접속 1회로 (c) 실측 보강: 페이지 로드 시 인덱스 재생성 없음, 잠금 오류 0

## 5. 롤백

- 커밋별 `git revert <해시>` → push → 서버 pull → restart(기동 스크립트라 접속 불필요).
- (c)를 되돌리면 매 호출 재생성으로 돌아갑니다. 인덱스 자체는 남으므로 데이터 영향 없음.
- (E1)을 되돌리면 BACKFILL 재평가가 Trailing 고점을 올릴 수 있는 기존 동작으로 돌아갑니다. 저장 데이터 영향 없음.

## 6. 승인 결과 (2026-10-01)

| 번호 | 내용 | 결정 |
|---|---|---|
| E1 | Trailing 고점 관련 5개 필드를 BACKFILL 백업·복원 대상에 추가 | **포함, 정책 확정** — 커밋 4 (단독 revert). 정책: BACKFILL 재평가는 포지션 상태를 바꾸지 않으며 과거 누락 봉 가격은 Trailing 고점에 반영하지 않음 |
| E2 | (b) b-2 안 (rest_df 를 로컬 시작 이후로 자름) | 진행 |
| E3 | (a) a-1 안, a-2(공용 조회 함수에 end_ts 적용)는 별도 WO | 진행 |
| E4 | 워밍업 형성 중 봉 시드 + REST 요청 수 대비 적게 수신(201→200, 400→298) 원인 조사 | **WO-15** 읽기 전용 조사로 backlog 등록, 우선순위 WO-14 바로 다음 |
| E5 | 커밋 순서 (c) → (b) → (a) → (E1), 배포는 네 커밋 한 번에(기동 1회 실측) | 진행 |
| E6 | 배포 시점 | 로컬 검증 보고 뒤 별도 지시 |
