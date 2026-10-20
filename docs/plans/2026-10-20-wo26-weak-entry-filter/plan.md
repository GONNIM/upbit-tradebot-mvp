# WO-26 약매수 차단 필터 — 구현 계획 (2단계, 로컬 완료까지)

- 작성: 2026-10-20
- 근거: `report.md`(1단계 측정·설계 B-1~B-5), `prd.md`(Fable 개정, 기본값 "매수 안 함")
- 범위: 코드 1건 + 문서 1건, 서버 무변경. 배포는 별도 지시.

## 1. Fable 결정 (2026-10-20)

| # | 결정 |
|---|---|
| 1 | 처리 방식 기본값 "매수 안 함"(`block`). 익절 축소(`reduce_tp`)는 선택지, 기본 0.5%. 시간 기본 2시간 |
| 2 | D/C 기준선 = 매도에 쓰는 EMA 쌍 |
| 3 | 직전 D/C 를 모르면(200봉 SMA 폴백 기동 등) 일반 매수 + `[WARMUP]` 로그 1줄 "직전 D/C 알 수 없음" |
| — | 설계 B-1~B-5 승인 |

## 2. 구현 항목 (지시 A~I)

| 항목 | 내용 | 위치 |
|---|---|---|
| A 지표 | `update_incremental(close, ts=None)` → 매도 쌍 D/C 이면 `last_dead_cross_ts = ts`. `seed_long_history(..., timestamps)`, 마지막 `prev_*` 초기화에서 유지. 엔진 4곳 `bar.ts`. `get_snapshot` 키. BACKFILL 백업·복원 dict | core/indicator_state.py, core/strategy_engine.py, engine/live_loop.py |
| B 필터 | `WeakEntryFilter(window_hours, mode, weak_tp_pct)`. 매수 조건 통과 직후 직접 호출. block → HOLD + `WEAK_ENTRY_FILTER`, reduce_tp → `strategy.last_weak_entry` | core/filters/buy_filters.py, core/strategy_incremental.py |
| C 포지션 | `PositionState.take_profit_override`. TP 판정·TS 무장(`effective_take_profit`). 체결 확정 3곳에서 override + `account_positions.meta.weak_entry`, `orders.meta.weak_entry` | core/position_state.py, core/filters/sell_filters.py, core/strategy_engine.py, core/weak_entry.py |
| D 복원·초기화 | boot_seed·wallet_sync 직후 uuid 대조 복원(불일치 삭제·WARNING). HTS_BUY_ADD·청산·sync_all_positions·기동 정합 검사에서 삭제. 복원은 `restore_trailing_on_boot` 앞 | engine/live_loop.py, core/strategy_engine.py, services/db.py |
| E 설정 | buy 키 4개(config 기본값), 설정 페이지 블록, hot reload 2경로, 기동 `[CONFIG]` 적용값 1줄 | config.py, pages/set_buy_sell_conditions.py, core/strategy_incremental.py, engine/live_loop.py |
| F 감사·용어 | BUY 평가 "약매수" 칸, 체결 표 "비고" 칸, terminology.md | pages/audit_viewer.py, engine/order_reconciler.py, core/trader.py, docs/operations/terminology.md |
| G 시험 | (1)~(12) + 매도 비고 + 렌더 3건 = 18건, 구 코드 전부 실패 | tests/regressions/test_r_2026_10_20_wo26_weak_entry_filter.py |
| H 관문·되돌리기·버전 | 339/339, 단독 revert 321/321, v1.2026.10.06.1440 → v1.2026.10.20.1711 | — |
| I 보고 zip | `wo26-impl-20261020.zip` | 이 폴더 |

## 3. 배포 시 확인할 것 (별도 지시 때)

1. 서버 조건 파일에 약매수 키가 없으면 필터는 **꺼진 상태**(config 기본 `weak_entry_filter_enabled=False`)로 시작한다. 기동 로그 `[CONFIG] 적용값` 에서 `weak_entry_*=…*` 로 확인한다.
2. 기동 로그 `[WARMUP] 시드 방식=long_history … 직전 D/C=…` 가 나오는지, 폴백이면 "직전 D/C 알 수 없음" 이 나오는지 본다.
3. `[WEAK-ENTRY] 기동 정합 검사 완료 | cleared=0` 1줄.
4. 포지션이 없는 시점에 배포한다(PRD 8절). 투자자가 설정 페이지에서 필터를 켠 뒤 첫 G/C 에서 `[WEAK-ENTRY]` 로그와 감사 로그 "약매수" 칸을 대조한다.
5. 투자자 통보(체감 변경): 설정 페이지 새 항목·감사 로그 "약매수"·"비고" 칸.
