# WO-18 · WO-17 (C)(P) 구현 보고 — hts_buy 플래그 잔존 해제 + 주석 정정 + 부분 재계산 경로 제거 (로컬 완료, 배포 대기)

- 작성일: 2026-10-01
- 승인: [WO-16 완결 승인 — WO-18 신설(hts_buy 잔존) + WO-17 (C)(P) 착수], WO-17 G1~G5 제안대로, (S) 금지 유지
- 상태: **로컬 커밋만, push·배포 안 함**
- 근거 파일: `test_results.txt`, `commands.txt`

버전: v1.2026.10.01.1312 → v1.2026.10.01.1740 (커밋마다 1735 → 1737 → 1740)

## 0. 확정 (a) — Issue #17 STOP_LOSS 스킵 로직은 현재 코드에 없다

Issue #17 의 "Dead 상태 HTS 매수는 STOP_LOSS 건너뜀" 로직은 **제거되어 있다.** `a192d31` (2026-05-26 `fix: POSITION-SYNC/HTS 인수 결함 핫픽스 (v1.2026.05.26.1343)`)에서 `core/filters/sell_filters.py` `StopLossFilter.evaluate` 에 Policy P-3("hts_buy 플래그는 매도 결정에 영향을 주지 않는다")가 들어갔고, 지금 이 함수는 `hts_buy` 를 진단 로그에만 쓴다. 따라서 플래그 잔존의 위험 등급은 "손절 무력화 가능"이 아니라 **알림 등급·표시 오분류**다. 2026-10-01 15:35:11 실측에서도 `hts_buy=True` 인 봇 매수 포지션의 손절이 정상 발화했다.

`hts_buy` 가 읽히거나 쓰이는 지점 (구현 뒤 줄 번호)

| 파일:라인 | 용도 | 판정 영향 |
|---|---|---|
| `core/filters/sell_filters.py:91, 102` | `StopLossFilter` 진단 로그 `hts_buy=…` | 없음 (Policy P-3) |
| `core/strategy_incremental.py:1184, 1186` | WO-8 POS-DESYNC 알림 등급: `hts_buy and bars_held==0` 이면 1봉째 **WARN 강등**(`class=first_bar_guard`), 2봉 연속이면 CRITICAL 승격(`class=pos_desync_promoted`) | 매도 판정 없음(그 분기는 어느 쪽이든 HOLD). **알림 등급만** 바뀜 — 잔존 플래그면 봇 매수의 진짜 결손이 CRITICAL 대신 WARN 으로 시작 |
| `core/strategy_incremental.py:1226` | `class=integrity_gap` 로그에 값 표기 | 없음 |
| `services/db.py:2622` (`get_position_entry_source`, 호출 `pages/dashboard.py:856`) | 대시보드 진입 출처 배지: 최근 BUY 감사 행이 없을 때만 `👤 외부 매수 (감지)` | 표시만 |
| `services/db.py:2642` | `get_position_meta` docstring 예시 | — |
| `engine/order_reconciler.py:675` → `services/db.py:2695~2711` | HTS 매수 감지 시 플래그 설정 | 설정 지점 |
| `core/position_state.py:55, 195` | `sync_from_wallet` 이 DB meta 를 `position.metadata` 로 로드 | 전달 |

## 1. 커밋

| 순서 | 해시 | 내용 | 재현 테스트 | 게이트 |
|---|---|---|---|---|
| WO-18 | `8bf7944` | hts_buy 해제 (§2) | 6건 | 257/257 |
| WO-17 (C) | `17742cb` | 주석 2곳 정정, 실행 코드 무변경 (§3) | 2건 | 259/259 |
| WO-17 (P) | `83f48ba` | 부분 재계산 경로 제거 (§4) | 4건 + 기존 1건 개정 | 263/263 |

## 2. WO-18 — 변경

| 경로 (보유 0) | 지점 | 해제 사유(reason) |
|---|---|---|
| 봇 SELL 체결 반영 | `core/strategy_engine.py:1356` `close_position(bar.ts, reason="bot_sell")` → `PositionState._clear_hts_flag` | `bot_sell` |
| HTS(외부) 매도 감지 — 지갑 0 강제 청산 | `core/strategy_engine.py:522` POSITION-SYNC Case 1 `close_position(ts=None, reason="position_sync_wallet_zero")` | `position_sync_wallet_zero` |
| HTS(외부) 매도 감지 — 1분 동기화 | `services/db.py` `sync_all_positions_from_balances` "cleared" 직후 | `sync_all_positions_cleared` |
| 기동 시 정합 검사 (c) | `engine/live_loop.py:619` run_live_loop 시작(LIVE) → `services/db.clear_stale_hts_flags` | `boot_reconcile` |

- `services/db.clear_position_hts_flag()`: meta 에서 `hts_buy` 키만 지움(다른 키 유지). 지웠을 때만 `[HTS-FLAG] cleared | reason=… | ticker=…` 1줄.
- `PositionState.close_position(ts, reason)`: 메모리 `metadata` 와 DB 를 함께 지우고, 하나라도 지웠으면 `[HTS-FLAG] cleared | reason=… | ticker=… memory=… db=…` 1줄. 플래그가 없으면 로그 없음.
- 기동 정합 검사: 보유(가용+묶임) 0 이고 `hts_buy=true` 인 행만. **최근 10분 안에 HTS 매수 감사 행이 있는 종목은 건너뜀** — HTS 감지는 플래그 설정·감사 행 기록 뒤 다음 동기화에서 수량을 반영하므로 그 사이를 잔존으로 보지 않기 위함. 끝에 `[HTS-FLAG] 기동 정합 검사 완료 | cleared=N`. 과거 audit 행은 건드리지 않는다.

### 2.1 지시와 다르게 처리한 2곳 (판단 요청)

1. **부팅 복원 실패(`engine/live_loop.py` `[BOOT-SEED] 완전 상태 리셋`, has_position=False)에서는 지우지 않았다.** 이 경로는 지갑에 코인이 **있는데**(외부 매수일 수 있음) 봇 주문 기준 진입가가 없어 메모리만 비우는 경우다. 실제 보유는 0 이 아니므로, 여기서 지우면 진짜 HTS 보유의 표시가 사라지고 WO-12 C7 지갑 기준 복원 뒤 POS-DESYNC 알림이 WARN 강등 대신 CRITICAL 로 시작한다. 보유 0 일 때의 잔존은 기동 정합 검사가 처리한다.
2. **`sync_from_wallet` 의 "지갑 0" 판정에서도 지우지 않았다(구현했다가 되돌림).** `UpbitTrader._coin_balance` 는 API 실패 시 0.0 을 돌려준다(`core/trader.py:359~361`). 일시 오류로 플래그를 지우는 것을 막기 위해, 실제 보유 0 이 확인되는 경로(위 표 4곳)만 쓴다.

### 2.2 현재 잔존 (서버 읽기 전용 조회, 2026-10-01 17:4x)

| 사용자 DB | `hts_buy` 행 | 보유 0 (기동 시 해제 대상) | 보유 중 (유지) |
|---|---|---|---|
| mcmax33 | 91 | **89** (KRW-JTO 포함) | 2 (KRW-FOLD 117.37, KRW-PYUSD 20.10) |
| gon1972, default | 0 | 0 | 0 |

- 최근 HTS 매수 감사 행: KRW-MON 2026-09-30 16:56 이 가장 최근 → 10분 창에 걸리는 종목 없음, 건너뜀 예상 0.
- 배포 뒤 첫 기동에서 `[HTS-FLAG] cleared | reason=boot_reconcile` 89줄 + `기동 정합 검사 완료 | cleared=89` 예상.

### 2.3 재현 테스트 (`test_r_2026_10_01_wo18_hts_flag_clear`, 임시 DB)

| 번호 | 시나리오 | 결과 |
|---|---|---|
| ① | HTS 매수(플래그·감사 행·수량) → 봇 포지션 SELL 평가 `hts_buy=True` → 봇 매도 전량 `close_position(bot_sell)` → `[HTS-FLAG] cleared | reason=bot_sell` + DB·메모리 해제 → **다음 봇 매수(749 × 308.4559189)의 SELL 평가 `hts_buy=False`** | 통과 |
| ② | HTS 매도 감지 경로: 지갑에서 사라짐 → `sync_all_positions` cleared → `[HTS-FLAG] cleared | reason=sync_all_positions_cleared` → 다음 매수 `hts_buy=False` | 통과 |
| ③ | 지갑 0 강제 청산 `close_position(position_sync_wallet_zero)` | 통과 |
| ④ | 플래그 없으면 로그 없음 | 통과 |
| ⑤ | 기동 정합 검사: 보유 0 잔존 → 해제 / 보유 중 → 유지 / 막 감지(플래그·감사 행, 수량 0) → 건너뜀 | 통과 |
| ⑥ | 호출 위치 lint (사유 인자 2곳, 기동 훅, sync 경로) | 통과 |

- **옛 코드 대조**: 6건 모두 실패 — ①③④⑤ ERROR(사유 인자·함수 없음), ② FAIL(`sync_all_positions cleared` 로그만 있고 플래그 잔존 — 결함 자체 재현), ⑥ FAIL.

## 3. WO-17 (C) — 주석 2곳 (실행 코드 무변경)

| 위치 | 전 | 후 |
|---|---|---|
| `core/rest_reconcile.py` `fetch_confirmed_candle` docstring·본문 주석 | "to 파라미터 (완전) 제거/없음 → Upbit가 확정한 최신 봉만 반환" | "to 없음 → 형성 중 봉 포함 최신 봉 반환, 확정 판정은 다음 봉 존재·재시도(케이스 A/B/C)" |
| `core/data_feed.py` `stream_candles` 주석 | "to 파라미터 제거 - 항상 최신 확정 봉만 조회" | "to 없음 → 형성 중 봉 포함 가능 (확정 판정은 호출부 책임)" |

- G1: `core/data_feed.py` 로그 문자열 `(최신 확정 봉)` 은 그대로(테스트로 고정).
- **실행 코드 무변경 증명**: 두 함수의 AST(docstring 제거, 주석은 AST 에 없음) SHA-256 을 정정 **전** 코드에서 계산해 테스트에 고정 — `fetch_confirmed_candle 2c47d11b…`, `stream_candles 6cc132e6…`. 정정 뒤 같은 값.

## 4. WO-17 (P) — 부분 재계산 경로 제거 (P1)

- `core/strategy_engine.py` `on_new_bar_confirmed` 의 `changed_count > 0` 분기: `recompute_from_changed_ts` 호출 제거, `update_incremental(bar.close)` 1회. 로그 `[ENGINE] Reconcile 변경 감지 (지표는 증분만, 재시드 없음)`(WARNING → INFO, 매 주기 정상 동작이므로).
- `core/indicator_state.py` `recompute_from_changed_ts` 함수 제거(사유 주석 4줄). `[INDICATORS] 부분 재계산 완료` 오기 소멸.
- `engine/live_loop.py` `[REST-RECONCILE] N개 봉 변경 감지 (지표는 증분만)`.
- **기존 테스트 개정 1건**: `test_r_2026_09_02_wo2_option_c_indicator_correction` 은 "recompute 1회 호출 → 802 기준 교정" 을 고정하고 있었으나, 운영에서 그 호출은 꼬리 1봉 < 200 으로 늘 무동작이었다. 개정 뒤 "재시드 없이 `update_incremental(802)` 1회" 를 고정하고, docstring 에 사유를 적었다.

재현 테스트 (`test_r_2026_10_01_wo17p_no_partial_recompute`, 실제 `IndicatorState` + 엔진 스텁)

| 번호 | 내용 | 결과 |
|---|---|---|
| ① | 꼬리 1봉(매 주기 실제 상황) → 지표 = 증분 1회, 정정 로그 | 통과 |
| ② | 꼬리 250봉(옛 코드라면 재시드 성공) → 여전히 증분 1회, `prev_ema` 유지 | 통과 |
| ③ | (대조) 옛 경로 흉내(꼬리 SMA 재시드 + 현재 봉 증분) → 정답과 다름 | 통과 |
| ④ | 함수 없음, `부분 재계산 완료`·호출 문자열 소멸, 새 로그 문구 | 통과 |

- **옛 코드 대조**: 3건 실패. 특히 ② 는 옛 코드에서 EMA60 **731.075 ≠ 정답 730.576** — 이중 반영 위험이 실제 값으로 재현됐다.

## 5. 단독 revert 실측 (임시 worktree, 더미 키)

| 되돌린 커밋 | 충돌 | py_compile | 게이트 |
|---|---|---|---|
| WO-18 `8bf7944` | 버전 줄만 → 현재 버전 유지 | OK | 257/257 |
| WO-17 (C) `17742cb` | 버전 줄만 | OK | 261/261 |
| WO-17 (P) `83f48ba` | 없음 | OK | 259/259 |

## 6. 배포 절차 초안 (실행은 별도 지시)

1. `git status` → push (코드 기준 `83f48ba`, 목표 HEAD = 이 문서 커밋) → 서버 `git pull --ff-only` → `systemctl restart tradebot` → `is-active`. 서버 HEAD·버전 v1.2026.10.01.1740 인용, "버전: v1.2026.10.01.1312 → v1.2026.10.01.1740".
2. 접속 없이 30분 관측

| 항목 | 기대 |
|---|---|
| WO-18 기동 정합 검사 | `[HTS-FLAG] cleared \| reason=boot_reconcile` 89줄, `[HTS-FLAG] 기동 정합 검사 완료 \| user_id=mcmax33 cleared=89`, `건너뜀` 0 |
| hts_buy 잔존 0 확인 SQL (읽기 전용) | `sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' "SELECT COUNT(*) FROM account_positions WHERE meta LIKE '%\"hts_buy\": true%' AND COALESCE(virtual_coin,0)+COALESCE(virtual_coin_locked,0)=0;"` → **0** (보유 중 2행 FOLD·PYUSD 는 유지) |
| WO-17 (P) | `부분 재계산 완료` 0, `Not enough data for seed` 0, `[ENGINE] Reconcile 변경 감지 (지표는 증분만, 재시드 없음)` 조정마다 1줄, `[REST-RECONCILE] N개 봉 변경 감지 (지표는 증분만)` |
| WO-16 유지 | 조정 `total=400`, VERIFY `없는 timestamp` 0·검증 실패 0 |
| 공통 | 결함 태그(`pos_desync_promoted`·`integrity_gap`·`POLLUTED`·Traceback) 0, Bar# 5봉, `database is locked` 0 |
| 매매 발생 시 | 봇 매도 체결 뒤 `[HTS-FLAG]` 로그는 플래그가 있던 경우에만(정리 뒤에는 보통 없음) |

3. 30분 통과 뒤 운영자 접속 1회: `[AUTO-RESUME] skip` 1줄, 엔진 스레드 1개, 대시보드 보유 종목 출처 배지 확인(FOLD·PYUSD 는 최근 BUY 감사 행 기준).
4. 이상 시: 해당 커밋만 revert — (P) `83f48ba` / (C) `17742cb` / WO-18 `8bf7944` (서로 독립).

## 7. 승인 요청

| 번호 | 내용 | 제안 |
|---|---|---|
| H1 | §2.1-1 부팅 복원 실패 경로 미해제 | 그대로 (실보유 있음) |
| H2 | §2.1-2 `sync_from_wallet` 지갑 0 판정 미사용 | 그대로 (API 실패 시 0 반환) |
| H3 | 기동 정합 검사 건너뜀 창 10분 | 그대로 |
| H4 | 배포 시점 | 별도 지시 |
