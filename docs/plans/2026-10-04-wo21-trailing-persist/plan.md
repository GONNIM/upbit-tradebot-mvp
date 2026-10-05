# WO-21 구현 계획 — 재시작 때 trailing 상태를 봉 종가로 재계산 (예방 조치)

- 작성: 2026-10-04 (KST), 2026-10-05 마감
- 근거: 조사 보고 `report.md` (2026-10-04 구현 착수 중 결론 3·B2 정정), Fable 검토 승인
- 처방: (나) 재시작 때 종가로 trailing 상태를 다시 계산 + `audit_sell_eval.ts_armed` 실제 값 기록
- 범위: 구현과 로컬 검증, 푸시까지. 서버 pull·재시작은 별도 지시. 투자자 안내 없음.

## 성격 — 결함 수정이 아니라 예방 조치

조사 결론:
- trailing 상태(무장 여부·최고가·고정폭·활성화 가격)는 `PositionState` 메모리에만 있다. 재시작 복원(boot_seed / wallet_sync)은 `apply_entry` 로 이를 초기화한다. 보유 중 재시작이면 수익이 익절 기준에 다시 닿을 때까지 trailing 매도가 나오지 않는다.
- 최고가는 `audit_sell_eval.highest`·`invariant_snapshots` 에, 무장 여부는 `invariant_snapshots` 에 기록되지만 복원에는 쓰이지 않는다.
- **정당한 무장 상태를 재시작으로 잃은 실사례는 아직 없다.** 09-30 19:44 사례의 armed=1·peak 774 는 BACKFILL 결함(WO-13/14)으로 매수 전날 봉이 재평가된 오염값이었다. 재시작 뒤 armed=0 이 맞는 상태였다.
- 최근 30일 TRAILING_STOP 매도 15건 중 재시작을 거친 포지션 0건. 보유 시간이 짧아 겹칠 기회가 적었을 뿐이다. 보유 중 배포·설정 변경 재시작이 있으면 생길 수 있다 → **예방 조치**(보유 중 재시작 시 무장 상태 보존).
- 부수 표시 결함: `audit_sell_eval.ts_armed` 가 3곳에서 `False` 로 고정되어 무장 봉도 0 으로 기록됐다.

## 구현 조건 (운영자 확정)

1. 시작점은 `audit_trades` 의 마지막 BUY(HTS_BUY_ADD 포함) 시각이다. 평균가는 지갑 동기화 값을 쓴다. 마지막 BUY 가 없으면 재계산하지 않고 지금처럼 초기화한다.
2. 미확정(형성 중) 봉은 제외한다 (WO-16 (W) 규칙).
3. 워밍업 때 받은 봉 안에 시작점이 있으면 추가 조회 없이 계산한다. 밖에 있으면 REST 로 과거 봉을 더 받되 최대 10회(200봉×10)로 제한한다. 초과하거나 조회에 실패하면 지금처럼 초기화하고 `[TRAILING-RESTORE] 재계산 불가 → 초기화 | 사유=…` WARNING 1줄을 남긴다.
4. 무장 판정, 최고가 갱신, 고정폭 계산은 `TrailingStopFilter` 와 `PositionState` 의 기존 함수를 그대로 호출한다. 규칙을 따로 베껴 쓰지 않는다. 필요하면 필터의 해당 부분을 함수로 뽑아 두 곳이 같은 함수를 쓰게 한다.
5. 재계산은 복원 2경로(boot_seed, wallet_sync) 뒤, 첫 매도 평가 전에 1회 실행한다. 결과는 `[TRAILING-RESTORE] armed=… peak=… fixed=… activation=… 기준 봉 n개 시작=<마지막 BUY 시각>` 1줄로 남긴다. 무장 조건에 닿지 않았으면 armed=False 로 같은 줄을 남긴다.
6. `audit_sell_eval.ts_armed` 를 실제 `position.trailing_armed` 값으로 기록한다 (`core/strategy_engine.py:1507·1855·1936`).
7. 매수·매도 판정식, 필터 순서, 발주, 지표 경로는 바꾸지 않는다. 재계산은 `PositionState` 의 trailing 필드만 바꾼다.

## 구현 대응 (`770b104`)

| 조건 | 파일 | 내용 |
|---|---|---|
| 1 | `services/db.py` `get_last_open_buy_trade` | 마지막 BUY 뒤 SELL 이 없을 때만 시작점 반환 |
| 1·2·3·5·7 | `core/trailing_restore.py` (신규) `restore_trailing_on_boot` | 봉 선택(마감 > 매수 시각, 마감 ≤ 지금), REST 추가 조회 한도, 실패 시 초기화 + WARNING, 결과 1줄 |
| 4 | `core/filters/sell_filters.py` `TrailingStopFilter.advance_state` | evaluate 의 STEP 1·2 를 그대로 옮긴 함수. evaluate 와 재계산이 함께 씀. `log=False` 는 로그만 생략 |
| 4 | `core/position_state.py` `activate_trailing_stop(log=True)` | 재생 때 로그 생략용 인자만 추가 |
| 5 | `engine/live_loop.py` | 형성 중 봉 제거 뒤 워밍업 전체 봉 보관(`_wu_full_df`), 워밍업·`_boot_seed_recover_from_wallet` 직후 1회 호출 |
| 6 | `core/strategy_engine.py` 3곳 | `ts_armed=bool(getattr(self.position, "trailing_armed", False))` |

재생 순서는 실시간 SELL 블록과 같다: 봉마다 `update_highest_price(종가)` → `advance_state(종가)`. `min_holding_period` 만큼 첫 봉을 건너뛴다.

알려진 근사: 손절 등 앞선 필터가 매도를 낸 봉도 재생은 trailing 상태를 전진시킨다. 실시간에서 그런 봉은 포지션이 청산되므로, 지금도 보유 중인 포지션에서는 매도 거절 같은 드문 경우에만 차이가 난다.

## 보류

- 기존 `audit_sell_eval.ts_armed`(과거 행 전부 0)는 보정하지 않는다.
- 무장 상태 저장 방식 (가)·(다)는 채택하지 않았다 (`report.md` C절).
