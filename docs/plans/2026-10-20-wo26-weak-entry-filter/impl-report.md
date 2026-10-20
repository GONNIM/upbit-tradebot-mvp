버전: v1.2026.10.06.1440 → v1.2026.10.20.1711

# WO-26 약매수 차단 필터 — 구현 보고 (로컬 완료, 배포 대기)

- 작성: 2026-10-20 17:2x KST
- 커밋: 문서 `8d75b57`(측정·PRD·백로그, 푸시 완료), 코드 `035a552`, 문서 (이 보고 커밋, 아래 git log)
- 서버: 무변경. pull·재시작 없음. 서버 HEAD `33a5d9e`, 기동 2026-10-06 14:45:06 (작업 시작 시 확인)
- 시험: `.env` 격리(`env -i` + 더미 키 + 텔레그램 빈 값). 관문 339/339. WO-26 시험 18건 — 구 코드 18건 모두 실패, 새 코드 18건 모두 통과

---

## 1. Fable 결정 반영

| 결정 | 반영 |
|---|---|
| 기본값 "매수 안 함", 익절 축소 0.5%, 2시간 | `config.py` `WEAK_ENTRY_MODE_DEFAULT="block"`, `WEAK_ENTRY_TP_PCT_DEFAULT=0.005`, `WEAK_ENTRY_WINDOW_HOURS_DEFAULT=2.0`, `WEAK_ENTRY_FILTER_ENABLED_DEFAULT=False` |
| D/C 기준선 = 매도 EMA 쌍 | `IndicatorState._sell_pair_dead_cross` (core/indicator_state.py:276) — `use_separate_ema` 면 `*_sell`, 아니면 공통 쌍. `strategy_incremental` 의 `ema_dead_cross` 와 같은 식 |
| 직전 D/C 모름 → 일반 매수 + 로그 | `WeakEntryFilter` 가 `last_dead_cross_ts=None` 이면 `WEAK_UNKNOWN`(통과). 폴백 기동 로그 `[WARMUP] 시드 방식=sma200 bars=N | 직전 D/C 알 수 없음 → 약매수 판정 안 함(일반 매수)` (engine/live_loop.py:1225-1226, 같은 줄) |

## 2. 변경 내용 (지시 A~F)

### A. 지표
- `update_incremental(close, ts=None)` (core/indicator_state.py:225): 갱신 뒤 매도 쌍 D/C 이고 `ts` 가 있으면 `last_dead_cross_ts = ts`.
- `seed_long_history(closes, base_len, timestamps=None)` (core/indicator_state.py:190): 재생 루프에 `ts` 전달. 마지막 `prev_* = None`·`bar_count = 0` 초기화는 그대로, `last_dead_cross_ts` 는 유지. `seed_from_closes` 는 `None` 으로 초기화(새 시드 = 모름).
- 엔진 증분 4곳 `update_incremental(bar.close, bar.ts)` (core/strategy_engine.py:804·941·953·958).
- `get_snapshot` 에 `"last_dead_cross_ts"` (core/indicator_state.py:330).
- 워밍업: `_seed_warmup_indicators` 가 `timestamps=list(initial_df.index[-long_bars:])` 전달 (engine/live_loop.py:214). long_history 로그에 `직전 D/C=<KST>` 또는 `없음(800봉 안)`.
- BACKFILL(Issue #11): 백업 dict 에 `saved_indicators.update(_backup_dead_cross_ts(...))` (engine/live_loop.py:1473), 지표 복원 try 안에서 `_restore_dead_cross_ts(...)` (engine/live_loop.py:1576). 복원 실패는 기존 지표 오염 처리와 같은 except 로 간다.

### B. 필터
- `WeakEntryFilter` (core/filters/buy_filters.py:92). `BuyFilterManager` 에 등록하지 않는다(설계 B-1: 매 봉 차단 기록 방지 + 통과 metadata 보존).
  - `window_hours<=0` → `WEAK_OFF`, `last_dc=None` → `WEAK_UNKNOWN`, 경과 > 기준 → `WEAK_OK` (모두 통과)
  - 경과 ≤ 기준 + block → `should_block=True, reason="WEAK_ENTRY_FILTER", details="약매수 차단 (D/C 뒤 n분, 기준 h시간)"`
  - 경과 ≤ 기준 + reduce_tp → `should_block=False, reason="WEAK_ENTRY", metadata.tp`
- 호출: 모든 매수 조건 통과 직후·`EMA Buy Signal` 직전 (core/strategy_incremental.py:1090~1110). block 이면 `last_buy_filter_result=결과` 후 HOLD → 기존 감사 경로가 `failed_keys=["WEAK_ENTRY_FILTER"]`, 메모 `"<cross> | 약매수 차단 (D/C 뒤 n분, 기준 h시간) | bar=N"` (core/strategy_engine.py:1937~). reduce_tp 이면 `strategy.last_weak_entry={"tp","elapsed_min","window_h"}`, BUY 평가 메모 끝에 ` | 약매수 진입 · 익절 x%`, `checks.weak_entry` (core/strategy_engine.py:1976~).
- 매수 블록 진입 때 `last_weak_entry=None` 초기화 (core/strategy_incremental.py:981).

### C. 포지션
- `PositionState.take_profit_override: Optional[float]` (core/position_state.py:60). `apply_entry` 는 건드리지 않는다.
- `effective_take_profit(position, default)` (core/filters/sell_filters.py:14) — TakeProfitFilter 판정(193)과 TrailingStopFilter `advance_state` 무장(280)에 사용. 재시작 재계산(`core/trailing_restore.py:95`)은 `advance_state` 를 그대로 부르므로 같이 따라간다. 고정폭 계산식은 무변경(0.5% 무장 시 약 1호가 — PRD 4.3).
- 기록: `core/weak_entry.py record_weak_entry` — override + `metadata["weak_entry"]` + `account_positions.meta.weak_entry={"tp","elapsed_min","window_h","order_uuid","bar_time"}`.
  - 시장가: `open_position` 직후, `result["uuid"]` (core/strategy_engine.py:1516)
  - 지정가 체결: 주문 등록 때 `_pending_buy_weak` 보관(1500) → `_on_limit_fill` 의 `apply_entry` 뒤 (460)
  - 미체결 시장가 전환: `convert_unfilled_limit_buy` 의 `apply_entry` 뒤, 전환 주문 uuid (216)
- `orders.meta`: `_execute_buy` 의 meta 에 `weak_entry`·`audit_note` (core/strategy_engine.py:1451). live 경로는 `insert_order(meta=meta_json)`(core/trader.py:831)로 저장, 지정가→전환은 `conv_meta` 가 물려받는다.

### D. 복원·초기화
- `restore_weak_entry(position, source)` (core/weak_entry.py): `meta.weak_entry.order_uuid` 와 `get_last_open_buy_order(...)["provider_uuid"]` 가 같을 때만 override 복원(INFO `[WEAK-ENTRY] restored`). 다르거나 대조할 수 없으면 `clear_weak_entry` + WARNING `[WEAK-ENTRY] 표식이 마지막 봇 BUY 와 다름 → 삭제 (일반 익절 기준) | source= meta_uuid= last_buy_uuid=`.
  - boot_seed: `_apply_boot_seed` 의 `apply_entry(source="boot_seed")` 직후 (engine/live_loop.py:450). `restore_trailing_on_boot`(워밍업 뒤)보다 앞.
  - wallet_sync: `apply_entry(source="wallet_sync")` 직후 (core/strategy_engine.py:737). `_boot_seed_recover_from_wallet` 도 이 함수를 쓰므로 같은 순서.
  - `get_last_open_buy_order` 가 `provider_uuid` 를 함께 반환 (services/db.py:1951, 기존 키 무변경).
- 삭제: `PositionState.clear_weak_entry(reason)` (core/position_state.py:326) — override·metadata·DB 를 함께 지우고 `[WEAK-ENTRY] cleared` 1줄.
  - HTS_BUY_ADD 리셋 자리 (core/strategy_engine.py:409, 기존 Trailing 리셋과 같은 정책)
  - `close_position` (봇 매도·지갑 0 강제 청산) (core/position_state.py:324)
  - `sync_all_positions` 보유 0 정리 (services/db.py:2435)
  - 기동 정합 검사 `clear_stale_weak_entries` (services/db.py:2914, 호출 engine/live_loop.py:764) — 보유 0 인데 표식이 남은 행

### E. 설정
- 키: `weak_entry_filter_enabled`(False) · `weak_entry_window_hours`(2.0) · `weak_entry_mode`("block") · `weak_entry_tp_pct`(0.005). 해석은 `IncrementalEMAStrategy.weak_entry_settings` 한 곳(core/strategy_incremental.py:730) — 엔진·설정 페이지·기동 로그 공용.
- 설정 페이지 (pages/set_buy_sell_conditions.py): 토글 목록에 "🐢 약매수 차단 필터 (데드크로스 직후 골든크로스 매수 제한)"(154), 급등 차단 블록 바로 아래 파라미터 블록(661~): 시간 number_input 0~6·0.5 단위, 처리 방식 radio(매수 안 함 / 익절 기준 축소, 가로), 축소 익절 % 0.3~1.5·0.1 단위(익절 기준 축소일 때만 활성), 안내 caption(PRD 5절 문구 + "수익 추적 매도는 이 경우 고정폭이 매우 작아 사실상 즉시 매도에 가깝습니다"), 0시간 경고, 현재 설정 info. 요약 칸 "└─ 2시간 · 매수 안 함 / 익절 x%"(984). 저장은 EMA 전략이면 켬/끔과 무관하게 4개 키 저장(다시 켤 때 값 보존), 범위 보정 `dump_weak_entry_settings`.
- hot reload:
  - SP5 `reload_conditions` (core/strategy_incremental.py:911): `_apply_weak_entry_conditions` 로 필터 재생성, 바뀐 키는 `changes` 에 들어가 기존 `[HOT-RELOAD]` 로그·알림에 나온다. 필터 매니저 재구성(879-883 원 위치)과 무관하게 매 호출 갱신.
  - B7 `_maybe_reload_params` (engine/live_loop.py:565): 같은 함수 호출 추가.
  - 이미 보유한 약매수 포지션의 override 는 진입 때 값 유지(포지션 상태). 새 매수부터 새 설정.
- 기동 로그 1줄 (백로그 항목 완결, engine/live_loop.py:922): 서버 현재 조건 파일로 만든 예
  ```
  [CONFIG] 적용값 (*=기본값) | buy: above_base_ema=False bullish_candle=False ema_gc=True fixed_price_buy_enabled=True fixed_price_buy_wait_bars=5 fixed_price_convert_max_gap_pct=0.3 fixed_price_unfilled_to_market=True surge_filter_enabled=True surge_threshold_pct=0.020000000000000004 weak_entry_filter_enabled=False* weak_entry_mode=block* weak_entry_tp_pct=0.005* weak_entry_window_hours=2.0* | sell: ema_dc=True stale_hours=2.0 stale_position_check=True stale_threshold_pct=0.005000000000000002 stop_loss=True stop_loss_pct=0.5 take_profit=False take_profit_pct=1.0 trailing_stop=True trailing_stop_threshold_pct=30.0 use_fixed_trailing=True
  ```
  → **배포 직후 필터는 꺼진 상태**다(서버 조건 파일에 키 없음). 투자자가 켜야 동작한다.

### F. 감사·용어
- BUY 평가 표: 새 칸 "약매수" — 차단 "🐢 약매수 차단 (D/C 뒤 n분, 기준 h시간)", 진입 "🐢 약매수 진입 · 익절 x%" (pages/audit_viewer.py:328·526·541, `core/weak_entry.weak_entry_display`). 급등 칸은 `surge_pct` 가 있을 때만 채우도록 고쳤다(302 — 약매수 metadata 를 급등 0.00% 로 잘못 그리던 경로 차단).
- 체결 표: 새 칸 "비고" — 매수 행 "약매수 진입 · 익절 x%", 매도 행 "약매수 포지션 · 기준 x%". `note` 는 거절·주문 전 차단·미체결 취소 행이면 기존 "거절 사유" 칸, 그 외 행이면 "비고" 칸 (875~935). 기록은 주문 meta `audit_note` → 체결 확정 `insert_trade_audit(note=…)` (engine/order_reconciler.py:528, TEST 경로 core/trader.py:437).
- SELL 평가 감사의 tp 가격은 약매수 포지션이면 축소 기준으로 기록 (core/strategy_engine.py:2017, 기록 전용).
- 용어: docs/operations/terminology.md 2절에 "약매수"(설정 키 4개), "약매수 차단"(`WEAK_ENTRY_FILTER`), "약매수 진입", "약매수 포지션" 4행.

### UI 변경 브리핑 (1-A·1-B단계)
- 추가만 있다: 설정 페이지 토글 1개·파라미터 블록 1개(토글 켬일 때만)·요약 1줄, 감사 로그 BUY 평가 "약매수" 칸, 체결 표 "비고" 칸.
- 이동: 체결 표에서 **매수·매도 행**의 `note` 가 "거절 사유" 칸 → "비고" 칸으로 보인다. 지금까지 매수·매도 행의 note 는 비어 있었다(WO-9·24·25 는 거절·취소 행만 note 사용). 거절·주문 전 차단·미체결 취소 행은 그대로 "거절 사유" 칸.
- 삭제·접힘 없음. 새 블록은 기존 "🔍 매수 필터" expander(expanded=True) 안. 화이트리스트 항목 무변경.
- 브라우저 실측은 배포 후(사용자 새로고침) 단계에서 한다.

## 3. 시험 (지시 G)

`tests/regressions/test_r_2026_10_20_wo26_weak_entry_filter.py` 18건, 고정 자료 `tests/regressions/fixtures/wo26_m1_1000.csv`(1분봉 1,000봉, 10-11 17:31 ~ 10-12 16:36 KST, Upbit 공개 API — 측정 D/C 10-12 15:13·G/C 16:37 직전).

| 시험 | 내용 | 구 코드(8d75b57) | 새 코드 |
|---|---|---|---|
| 01 | D/C 뒤 1.5h G/C + block → HOLD, audit_buy_eval failed_keys `["WEAK_ENTRY_FILTER"]`·메모 "약매수 차단 (D/C 뒤 90분, 기준 2시간)" | FAIL (BUY != HOLD) | ok |
| 02 | 2.5h → BUY. 끔·0시간·직전 D/C 모름 → BUY | ERROR | ok |
| 03 | reduce_tp → BUY, 주문 meta weak_entry·audit_note, override 0.005, account_positions.meta.weak_entry(order_uuid u-w1, bar_time). 지정가 등록 → 체결 전 override 없음 → `_on_limit_fill` 뒤 0.007·uuid u-lim | ERROR | ok |
| 03b | BUY 평가 메모 "약매수 진입 · 익절 0.5%", 표시 함수 | FAIL | ok |
| 04 | override 0.005 포지션: 603/600 → TAKE_PROFIT(threshold 0.005), override 없으면 1% 기준 미발동 | FAIL | ok |
| 04b | 매도 주문 meta audit_note "약매수 포지션 · 기준 0.5%", 청산 뒤 override 해제 | ERROR | ok |
| 05 | TS 무장 0.5%(고정폭 0.9원), `replay_trailing` 재계산도 무장 | FAIL | ok |
| 06 | `_apply_boot_seed`: uuid 일치 → override 복원 / 불일치 → override 없음·meta 삭제·WARNING | ERROR | ok |
| 06b | wallet_sync 복원(`_reconcile_position_with_wallet`) → override 0.006 | ERROR | ok |
| 07 | HTS_BUY_ADD(`_on_hts_detect`) → override·meta 삭제, close_position 삭제, 기동 정합 검사 1행 삭제 | ERROR | ok |
| 08 | 800봉 시드 `last_dead_cross_ts` = 실시간 재생(앞 800 시드 + 200봉 증분) = 전략 식 재생 = **측정 사건 목록 D/C 10-12 15:13 KST** | ERROR | ok |
| 09 | BACKFILL 백업·복원으로 재평가 D/C 가 덮어쓴 값 복원, live_loop 백업 dict·복원 try 안 호출 | ERROR | ok |
| 10 | 300봉(800 미만) → sma200 폴백·None·로그 문구, 1,000봉 → long_history·15:13 | ERROR | ok |
| 11 | 저장·적재 왕복(1.7h→1.5, 0.0072→0.007), 옛 파일 기본값, 필터 값, `reload_conditions` 반영·changes, B7 경로, `[CONFIG]` 줄 | ERROR | ok |
| 12 | 실데이터: `wo26_gc_outcomes.csv` 44건 → block 12건(경과 ≤ 2h 와 1:1 일치), 통과 32건 | ERROR | ok |
| r1 | 설정 페이지 렌더: 토글·시간 2.0·익절 0.5(활성)·radio reduce_tp·안내 문구·요약 "└─ 2시간 · 익절 0.5%" → 매수 안 함으로 바꾸면 익절 칸 비활성 → 저장 → 파일 4키 | FAIL | ok |
| r2 | 약매수 키 없는 옛 파일 → 토글 끔, 블록 없음 | ERROR | ok |
| r3 | 감사 로그 렌더: BUY 평가 "약매수" 칸 문구·급등 칸 "-", 체결 표 매수 행 "비고" 칸·"거절 사유" 비움 | FAIL | ok |

- 구 코드: `Ran 18 | failures=6 errors=12 | FAILED`. 새 코드: `Ran 18 | failures=0 errors=0 | OK` (원문 `impl_test_results.txt` 1절).
- 기존 시험 수정 1건: `test_r_2026_09_02_wo2_option_c_indicator_correction` 의 `update_incremental.assert_called_once_with(802.0)` → `(802.0, confirmed_bar.ts)`. 확정 종가 증분 1회라는 시험 의도는 같고 봉 시각 인자만 늘었다.
- WO-17 (S) 문구 검사(`f"[WARMUP] 시드 방식=sma200 bars={len(initial_df)}"`)는 원 문자열을 그대로 두고 같은 줄에 이어 붙여 통과시켰다(시험 무수정).

## 4. 관문·단독 되돌리기·버전 (지시 H)

- `bash scripts/regression_gate.sh`: UI top-level import OK, typing 심볼 OK, **339/339 통과** (기존 321 + WO-26 18).
- 단독 되돌리기: `git revert --no-commit 035a552` 충돌 없음 → 버전 v1.2026.10.06.1440 복귀, 관문 **321/321 통과** → `git revert --abort` 로 HEAD 035a552 복귀 (원문 `impl_test_results.txt` 3절).
- 버전: `pages/dashboard.py:495` v1.2026.10.06.1440 → **v1.2026.10.20.1711** (코드 커밋 1건 안. 시험 파일 수정은 푸시 전 amend 로 같은 커밋에 합침, 버전 문자열 변동 없음).

## 5. 작업 중 있었던 일

- 기존 시험 2건이 1차 관문에서 실패했다(위 3절의 WO-2 인자, WO-17 문구). 의도를 바꾸지 않는 범위에서 각각 시험 1줄 수정·코드 문구 유지로 맞췄다.
- 체결 표 note 칸 이름을 "비고·거절 사유"로 바꾸려다 WO-9·WO-25 렌더 시험이 칸 이름 "거절 사유"를 검사해서 되돌렸다. 대신 행 종류로 "거절 사유"/"비고" 두 칸으로 나눴다(기존 시험 무수정).
- 렌더 시험 r1 의 저장 클릭 뒤 `st.switch_page` 가 AppTest 단독 실행에서 페이지를 못 찾아 traceback 을 찍었다(시험은 통과). `navigate_to` 를 시험 안에서만 막고 저장 뒤 예외 0 을 확인하도록 고쳤다 → amend.
- 출력 정리용 러너(스크래치패드)가 `logging.disable` 로 assertLogs 시험을 깨고, 빈 메시지 예외에서 죽는 결함이 있어 고쳤다. 저장소 코드와 무관하다.
- 셸 묶음 실행 중 `python3 -I -`(표준 입력 없음, 즉시 종료) 1회 — heredoc 아님, 무해.

## 6. 배포 시 확인 (별도 지시)

`plan.md` 3절. 요지: 서버 조건 파일에 키가 없어 필터는 꺼진 채 시작, `[CONFIG]`·`[WARMUP] … 직전 D/C`·`[WEAK-ENTRY] 기동 정합 검사` 3줄 확인, 포지션 없는 시점 배포, 투자자 통보(설정 페이지 새 항목·감사 로그 칸).
