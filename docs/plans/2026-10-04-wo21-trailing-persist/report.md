# WO-21 조사 보고 — trailing 무장 상태가 재시작에 지속되지 않음 (읽기 전용)

- 작성: 2026-10-04 (KST)
- 범위: 조사와 처방 제안. 코드·DB·서버 파일 무변경. 서버는 읽기만 했다. 투자자 안내 없음.
- 기준 코드: 로컬 `129c6df` = 서버 `e97dec6` 과 엔진 코드 동일 (그 뒤 커밋은 문서·스크립트뿐).
- 코드 인용 전문: `code-quotes.md`. 조회 결과: `results/`.

## 결론

1. **가설은 핵심이 맞고, 한 부분은 고쳐 적어야 한다.**
   - 맞는 부분: 재시작 복원은 trailing 상태를 어디서도 **읽어 오지 않는다**. 복원 경로는 모두 `apply_entry` 를 거쳐 armed=False, peak=평균가(또는 None)로 초기화한다. 수익이 익절 기준에 다시 닿아야 다시 무장한다.
   - 고칠 부분: "어디에도 저장되지 않는다" 는 정확하지 않다. 최고가는 매 봉 `audit_sell_eval.highest` 에 기록된다. 무장 여부와 최고가는 `invariant_snapshots` 에 기록된다(system_health 페이지 표시용). 다만 **어느 쪽도 복원에 쓰이지 않는다.** 고정폭 기준값(`trailing_fixed_amount`, `trailing_activation_price`)은 어디에도 저장되지 않는다.
2. **부수 결함 1건 (표시)**: `audit_sell_eval.ts_armed` 가 항상 0 으로 기록된다. 쓰는 곳 3곳 모두 `ts_armed=False` 로 고정되어 있다(`core/strategy_engine.py:1507·1855·1936`). 실제로 무장된 봉도 0 이다(예: 10-02 09:25 봉 TRAILING_STOP_FIXED 매도 행 ts_armed=0, 전체 1,295행 모두 0).
3. **정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다** (2026-10-04 구현 착수 중 정정). 09-30 19:44 사례의 armed=1 은 BACKFILL 결함으로 생긴 오염값이었다. 18:10:18 BACKFILL 이 매수 전날(09-29 18:50, 종가 772) 봉을 재평가해 무장시켰다. 매수(16:47, 761) 뒤 실제 5분봉 종가 최고는 762(+0.13%)로 익절 기준에 닿은 적이 없다. 그래서 재시작 뒤 armed=0 이 오히려 맞는 상태였다. WO-21 은 결함 수정이 아니라 **예방 조치**(보유 중 재시작 시 무장 상태 보존)다.
   - 정정 전 문구: "실사례 1건: 2026-09-30 19:44:28 재시작. 직전 armed=1·peak 774 → 직후 armed=0·peak 761 … 무장 상태가 재시작으로 초기화된 실사례" — 오염값을 정당한 상태로 오인한 잘못된 판정.
4. **추천: (나) 재시작 때 봉 종가로 다시 계산.** 다만 시작 시점은 `entry_ts` 가 아니라 `audit_trades` 의 마지막 매수(앱 추가 매수 포함) 시각으로 잡는다. 상세는 C절.

## A. 코드 조사

### A1. trailing 관련 상태 변수와 변경 지점

모두 `PositionState` 의 메모리 속성이다 (`core/position_state.py:44~52`).

| 변수 | 뜻 | 초기값 | 바뀌는 곳 |
|---|---|---|---|
| `trailing_armed` | 무장 여부 | False (`:45`) | `apply_entry` → False (`:253`) · `activate_trailing_stop` → True (`:422`) · `close_position` → False (`:308`) · HTS_BUY_ADD → False (`strategy_engine.py:308`) |
| `highest_price` | 무장 뒤 최고가(peak) | None (`:44`) | `apply_entry` → avg_price (`:252`) · `activate_trailing_stop` → 무장 시점 종가 (`:423`) · 매 봉 `update_highest_price` (무장일 때만, `:364~368`, 호출 `strategy_incremental.py:1255`) · 필터 STEP 2 신고가 (`sell_filters.py` "STEP 2") · `close_position` → None · HTS_BUY_ADD → None |
| `trailing_fixed_amount` | 고정폭(TRAILING_STOP_FIXED) 금액 = (무장 시점 종가 − 평균가) × trailing % | None (`:48`) | 필터 STEP 1 무장 순간 1회 계산 (`sell_filters.py` "고정폭 모드: 활성화 시점 1회 계산") · `apply_entry`·`close_position`·HTS_BUY_ADD → None |
| `trailing_activation_price` | 무장 시점 종가 | None (`:49`) | 위와 같은 자리 |
| `highest_since_entry` | 정체 포지션용 진입 뒤 최고가 (trailing 판정에는 안 씀) | None (`:52`) | `apply_entry` → avg (`:258`) · 매 봉 `update_highest_since_entry` (`:460~471`) · `close_position` → None |

판정 식 (고정폭, 현재 설정 `use_fixed_trailing=True`): 손절선 = `highest_price − trailing_fixed_amount`. 종가가 손절선 이하이면 TRAILING_STOP_FIXED.

### A2. 저장 여부

| 저장 위치 | 무엇 | 복원에 쓰는가 |
|---|---|---|
| `account_positions.meta` | `{"hts_buy": true}`·`locked_warned` 만. trailing 값 없음. 실데이터 예: KRW-JTO `{}` (virtual_coin 0), KRW-USDT `{"hts_buy": true}` (7.36377025, entry_price 1359.0), KRW-ANKR `{"hts_buy": true}`. 전체 meta 분포 `{}` 94 · NULL 6 · hts_buy 4 | — |
| `audit_sell_eval.highest` / `ts_armed` | 매 봉 `highest=position.highest_price`, **`ts_armed=False` 고정** | 아니오 |
| `invariant_snapshots.trailing_armed` / `highest_price` | 매 봉 스냅샷 (46,023행, 07-29 ~), armed=1 행 3,662 | 아니오 (`get_latest_snapshot` 은 `pages/system_health.py` 표시용) |
| `trailing_fixed_amount` / `trailing_activation_price` | 어디에도 저장 안 됨 | — |

`account_positions.meta` 는 JSON 통째로 UPSERT 한다(`services/db.py:2703~2730`). 쓰는 쪽은 OR 스레드(`locked_warned`, hts_buy 감지)와 엔진 스레드(`hts_buy` 해제)다. 모두 읽기-수정-쓰기라 동시에 쓰면 한쪽 변경이 사라질 수 있다 (C절 (가) 위험).

### A3. 재시작 복원 경로에서 trailing 상태

| 경로 | 결과 |
|---|---|
| 봇 매수 포지션 (WO-20 boot_seed) | `sync_from_wallet` → `_apply_boot_seed` → `apply_entry(source="boot_seed")` → armed=False, highest=avg, fixed·activation None (`position_state.py:252~255`) |
| 앱 매수 포지션 | `live_loop.py:776~790` 에서 trailing 필드를 None 으로 리셋 → 워밍업 뒤 `_boot_seed_recover_from_wallet` → `_reconcile_position_with_wallet` → `apply_entry(source="wallet_sync", entry_ts=now)` → 같은 초기화 |
| WO-14 E1 백업·복원 | `_BACKFILL_TRAILING_FIELDS` 5개(`live_loop.py:632~638`)를 `_backup_trailing_state`·`_restore_trailing_state` 가 다룬다. 호출은 BACKFILL 루프 안 1곳뿐(`live_loop.py:1394`, `:1455`). **재시작 경로에서는 쓰이지 않는다** (메모리 객체가 새로 만들어지므로 백업할 값도 없다) |

### A4. 재시작 뒤 첫 매도 평가

재시작 뒤 첫 SELL 평가에서 `TrailingStopFilter` 는 `trailing_armed=False` 를 본다. 그래서 STEP 1 로 들어가 그 봉 종가의 수익률이 익절 기준(`take_profit_pct`, 지금 1.5%) 이상인지만 본다. 미만이면 `TS_NOT_ARMED` 로 끝나 trailing 매도는 나오지 않는다. 이상이면 그 봉 종가로 다시 무장한다. 이때 `highest_price` 는 재시작 전 최고가가 아니라 그 종가다. 고정폭도 `(그 종가 − 평균가) × 30%` 로 새로 계산된다. 재시작 전 무장 시점 값과 다르다. 그래서 재시작 전 이미 무장되어 수익이 줄고 있던 포지션은 두 가지로 갈린다. 익절 기준 아래로 내려와 있으면 trailing 보호를 잃고, 손절·Dead Cross 만 남는다. 기준 위에 있으면 더 낮은 peak 로 다시 무장해 손절선이 내려간다.

## B. 데이터 조사 (서버, 읽기 전용, `results/`)

### B1. 최근 30일 엔진 기동과 KRW-JTO 보유 여부

journal 보존이 2026-09-06 03:52 부터라 실제 구간은 09-06 ~ 10-04 다. 엔진 기동(`run_live_loop start`, 서비스 재시작과 앱 안 재시작 포함) 15회.

| 기동 시각 | 직전 JTO 거래 (audit_trades) | 보유 |
|---|---|---|
| 09-12 17:36:25 | 09-12 00:30 SELL TRAILING_STOP_FIXED | 아니오 |
| 09-13 17:00:57 | 09-12 00:30 SELL | 아니오 |
| 09-18 17:26:34 | 09-15 06:05 SELL STOP_LOSS | 아니오 |
| 09-25 12:41:06 | 09-21 13:30 SELL STOP_LOSS | 아니오 |
| 09-30 16:33:05 | 09-30 15:40 SELL STOP_LOSS | 아니오 |
| **09-30 18:02:06** | 09-30 16:47 BUY HTS_BUY @761 | **예** |
| **09-30 19:44:28** | 09-30 16:47 BUY HTS_BUY @761 | **예** |
| 10-01 09:56:08 | 09-30 23:40 SELL EMA_DC | 아니오 |
| 10-01 11:42:08 | 같음 | 아니오 |
| 10-01 13:24:48 | 같음 | 아니오 |
| 10-01 18:10:30 | 10-01 15:35 SELL STOP_LOSS | 아니오 |
| 10-01 20:11:02 | 같음 | 아니오 |
| 10-02 10:03:25 | 10-02 09:30 SELL TRAILING_STOP_FIXED | 아니오 |
| 10-03 21:03:47 | 10-03 20:05 SELL TRAILING_STOP_FIXED | 아니오 |
| 10-04 10:22:40 | 같음 | 아니오 |

보유 중 기동 2회. 둘 다 09-30 앱 지정가 매도 주문으로 수량이 묶였던 KRW-JTO 1,340.436268개 포지션이다(그날 23:40 EMA_DC 로 매도).

### B2. 보유 중 기동 전후 trailing 상태 (`results/b2-before-after.txt`, `results/b2-restart-0930-detail.txt`)

`invariant_snapshots` 기준 (journal 은 무장·판정 줄로 교차 확인):

| 기동 | 직전 상태 | 직후 첫 상태 | 그 뒤 |
|---|---|---|---|
| 09-30 18:02:06 | 17:55:11 armed=0, peak 761 (= 평균가, 무장 전) | 18:10:12 armed=0, peak 761 | 18:10:18 무장(`initial_highest=₩772`) — 재시작 직후 BACKFILL 이 **매수 전날(09-29 18:50) 봉** 772 종가로 무장시킨 오염. **잃은 무장 상태 없음** |
| 09-30 19:44:28 | 19:25:10 armed=1, peak 774 — **오염값** (아래) | 19:50:10 armed=0, peak 761 — **맞는 상태** | 19:50:10 `[BACKFILL] 97개 누락 봉 평가 시작` → 19:50:12 과거 봉 772 종가로 다시 무장(같은 결함 재발) |

**정정 (2026-10-04, 구현 착수 중 확인)**: 직전 상태 armed=1·peak 774 는 정당한 무장이 아니었다. journal `2026-09-30 18:10:18 [BACKFILL] 누락 봉 평가 | ts=2026-09-29 18:50:00 KST | close=772` 바로 뒤에 `Trailing Stop ACTIVATED | entry=₩761 initial_highest=₩772` 가 나온다. 매수(09-30 16:47:09) **전날** 봉을 BACKFILL 이 재평가해 무장시킨 것이다(WO-13/14 결함, `results/wo21_0930_arm.txt`). 매수 뒤 실제 5분봉 종가(16:45 ~ 19:40, `tests/regressions/fixtures/wo21_jto_5m_20260930.json`) 최고는 762(+0.13%)로 당시 익절 기준 1.0% 에 닿은 적이 없다. 따라서 **정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다.** 09-30 19:44 재시작 뒤 armed=0 이 오히려 맞는 상태였다. 같은 결함 경로는 WO-14 E1(BACKFILL trailing 상태 백업·복원)과 WO-13·16(97봉 누락 원인 제거)으로 막혔다. 이 포지션은 당시 수량이 묶여 어떤 매도도 체결될 수 없었으므로 손익 영향은 없다.

- 정정 전 문구: "**무장 상태가 재시작으로 초기화된 실사례**", "두 번째 사례의 재무장은 … 우연히 상태가 비슷하게 되돌아왔다. … 지금 코드라면 19:44 재시작 뒤 armed=0 이 유지된다 … trailing 보호 없이 손절·Dead Cross 만 남는다" — 오염값을 기준으로 한 잘못된 판정.

### B3. 최근 30일 TRAILING_STOP 계열 매도

| 항목 | 값 |
|---|---|
| KRW-JTO SELL 전체 | 38건 |
| TRAILING_STOP 계열 (모두 TRAILING_STOP_FIXED) | 15건 |
| 그중 매수 뒤 재시작을 거친 같은 포지션에서 나온 매도 | **0건** |

15건 모두 매수 뒤 매도까지 재시작이 없었다. 지금까지 재시작 때문에 trailing 매도를 놓치거나 늦춘 체결 사례는 없다. 다만 보유 시간이 짧아(대부분 수십 분~몇 시간) 재시작과 겹칠 기회가 적었을 뿐이다. 운영자 설정 변경(10-03 사례처럼 엔진 정지·재시작)이나 배포가 보유 중에 있으면 바로 생길 수 있다.

## C. 처방 제안 (구현하지 않음)

공통 전제:
- 엔진은 매 봉 **종가**(`bar.close`)로 판정한다 (`strategy_incremental.py:376`). 무장 시점·최고가·고정폭은 매수 뒤 종가 열만 있으면 같은 규칙으로 다시 만들 수 있다. 거래 없는 봉은 평가하지 않으므로 캔들이 없어도 결과는 같다.
- 앱 추가 매수(HTS_BUY_ADD)로 평균가가 바뀌면 기존 정책은 trailing 상태를 리셋한다 (`strategy_engine.py:302~314`). 어느 안이든 이 정책을 그대로 따른다.

| 비교 항목 | (가) 매 봉 meta 저장 → 재시작 때 읽기 | (나) 재시작 때 종가로 다시 계산 | (다) 저장값 우선, 없으면 (나) |
|---|---|---|---|
| 변경 범위 | 매 봉 저장 지점(엔진 스레드) + 무장·리셋·청산 때 저장값 갱신·삭제 + 복원 2경로(boot_seed, wallet_sync)에서 읽기 + 일치 검사 | 복원 2경로 뒤 1곳에 "재계산" 함수 추가 (REST 캔들 조회 + 필터와 같은 규칙으로 armed·peak·fixed 산출). 저장 없음 | (가)+(나) 모두 |
| 정확도 | 재시작 직전 메모리 값 그대로 (설정 변경과 무관하게 당시 값) | 종가·현재 설정으로 재현. 보유 중 TP%·trailing% 를 바꿨으면 바뀐 값으로 다시 계산됨 (재시작 뒤 엔진이 어차피 새 설정을 쓰므로 일관) | 저장값이 있으면 (가) |
| 앱 추가 매수로 평균가가 바뀐 포지션 | 추가 매수 순간 리셋·저장 삭제가 빠짐없이 되어야 함. 놓치면 옛 평균가 기준 peak·fixed 를 읽어 옴 | 시작점을 `audit_trades` 의 마지막 BUY(HTS_BUY_ADD 포함) 시각으로, 평균가를 지갑 값으로 잡아 계산 → 기존 리셋 정책과 같은 결과 | (가)의 위험 + (나) |
| 오래된(다른 포지션의) 저장값 안전장치 | 필수: 저장 시 `qty`·`avg_price`·기준 매수 시각(또는 주문 uuid)을 함께 저장, 읽을 때 지갑 수량·평균가(허용 오차)·마지막 BUY 시각이 모두 같을 때만 사용, 청산 때 삭제. 하나라도 다르면 버림 | 저장값 없음 → 해당 없음. 시작점이 마지막 BUY 라 다른 포지션 값이 섞일 수 없음 | (가)와 같음 |
| 동시 쓰기 위험 | meta 는 OR 스레드(locked_warned·hts_buy)와 엔진 스레드가 JSON 통째 읽기-수정-쓰기 → 매 봉 쓰기가 더해지면 서로 덮을 위험. 별도 열·테이블이 안전 | 없음 (읽기만) | (가)와 같음 |
| REST 조회 비용 (Upbit 200봉/회) | 0 | 보유 시간 ÷ 봉 간격. **1분봉**: 3시간 1회, 10시간 3회, 3일 22회. **5분봉**: 16시간 1회, 3일 5회. 재시작 1회당 1번뿐(매 봉 아님), 기동 시 이미 801봉을 받으므로 대부분 그 안에서 해결 | (나)와 같음 (저장값 없을 때만) |
| 첫 배포·기존 보유분 | 저장값이 없어 효과 없음 | 바로 효과 | (나)로 효과 |
| 위험 | 저장·삭제 지점 누락 시 틀린 값 복원 (매도 판정에 직접 영향) | 재계산 규칙이 필터와 달라지면 틀린 무장 → 필터 코드와 같은 함수를 쓰고 회귀 시험으로 고정. REST 실패 시 지금처럼 초기화 상태로 폴백 | 두 경로 유지 비용 |
| 시험 | 메모리 DB: 저장→재시작→복원 일치, 수량·평균가 불일치 시 버림, 청산 뒤 삭제, 동시 쓰기 | 메모리: 종가 열 고정 → 실시간 판정 경로와 재계산 결과(armed·peak·fixed) 일치. 실데이터: 10-02 08:00~09:30 포지션(09:10 무장 747, 09:25 매도) 과 09-30 19:44 사례를 종가로 재현해 스냅샷 값과 대조 | 둘 다 |

**추천: (나).**
- 저장 없이 모든 보유 포지션(첫 배포 때 이미 들고 있던 것 포함)에 바로 효과가 있다.
- 오래된 저장값, meta 동시 쓰기 같은 새 위험을 만들지 않는다.
- 판정이 종가 기반이라 재현이 정확하고, 비용은 재시작 1회당 REST 몇 번이다.
- 구현 조건:
  - 시작점은 마지막 BUY 시각, 평균가는 지갑 값으로 잡는다.
  - 무장·고정폭 계산은 필터와 같은 함수를 쓴다.
  - REST 가 실패하면 지금처럼 초기화하고 WARNING 1줄을 남긴다.
  - 결과는 `[TRAILING-RESTORE] armed=… peak=… fixed=… 기준 봉 n개` 로 1줄 남긴다.
- (가)의 장점(설정 변경 전 값 유지)은 재시작 뒤 엔진이 새 설정으로 판정한다는 점에서 이득이 작다.

**함께 고칠 것 (선택)**: `audit_sell_eval.ts_armed` 를 실제 `position.trailing_armed` 로 기록 (`strategy_engine.py:1507·1855·1936`). 감사 로그에서 무장 여부가 보이게 되고, (나) 검증에도 쓸 수 있다.

## D. 묶음

- `report.md` (이 문서), `code-quotes.md`, `commands.txt`
- `results/a2-b1-b3.txt` (meta·audit_sell_eval·invariant_snapshots·기동 목록·TRAILING 매도), `results/b2-before-after.txt`, `results/b2-restart-0930-detail.txt`
- 스크립트: `results/wo21_b.py`, `results/wo21_b2.py`, `results/wo21_quotes.sh`
