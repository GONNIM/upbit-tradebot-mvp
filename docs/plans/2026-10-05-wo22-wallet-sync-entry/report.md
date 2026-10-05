버전: v1.2026.10.04.1731 → v1.2026.10.05.1145

# WO-22 구현 보고 — 지갑 동기화 복원 진입가 우선순위 + 외부 매도 기록 (로컬 완료, 배포 대기)

- 작성: 2026-10-05 (KST)
- 코드 커밋: `dfc075f` (1건). 문서 커밋은 그 뒤 1건.
- 서버: 읽기만 했다 (HEAD `ce65f29`, 기동 2026-10-05 10:54:59 그대로). pull·재시작 없음. 포지션·주문·DB 무변경. 투자자 안내 없음(배포 뒤).
- 사건 기록: `incident.md`. 가설·조사·처방·WO-23 이관: `plan.md`.

## A. 조사 (요약 — 상세 `plan.md` §1)

1. **진입가 순서** — 가설 일부 정정. 구 코드 순서는 이미 `account_positions.entry_price`(1분 주기 캐시) → orders 마지막 봇 BUY 였다. 함수는 Upbit `avg_buy_price` 를 직접 읽지 않았다. 10:58:26 앱 매수는 직전 동기화(10:58:08) 뒤라 캐시가 0 → 10:59:05 에 orders 564 @777 선택 (journal `[DB] last BUY (with status filter=True) => {'price': 777.0, 'entry_bar': 951, 'entry_ts_iso': '2026-10-05T08:26:52+09:00'}` → `자동 복구 성공 (source=last_open_buy) … entry_price=777.00`).
2. **청산 검사** — 가설 확인. `_last_buy_closed_by_later_sell` 은 orders SELL rowid 만 본다. 앱 매도(09:39:53)는 orders 에 없다.
3. **지갑 0 닫힘** — Case 1 은 `close_position(reason="position_sync_wallet_zero")` 뿐, orders·audit_trades 기록 없음 (09:42:11 뒤 마지막 JTO 기록은 orders 564 BUY · audit_trades 1198 BUY 그대로).
4. **30일 조합 (A3)** — 지갑 0 닫힘 3건(09-09 15:50, 09-30 21:50, 10-05 09:42). 그 뒤 첫 외부 매수 복원이 orders 를 쓴 것은 10-05 1건(777), 나머지 2건은 캐시(626, 745)로 정상. 외부 매수 복원 전체 26건 중 orders 1건.

| 지갑 0 닫힘 | 닫힌 포지션 | 다음 외부 매수 복원 | 진입가 (출처) | 판정 |
|---|---|---|---|---|
| 09-09 15:50:10 · 4,296.280196 | 앱 매수분 | 09-09 16:15:08 · 428.512780 | 626.00 (캐시) | 정상 |
| 09-30 21:50:11 · 1,340.436268 | 앱 매수분 | 09-30 23:25:06 · 307.667517 | 745.00 (캐시) | 정상 |
| **10-05 09:42:11 · 1,739.904822** | **봇 매수분 (orders 564 @777)** | **10-05 10:59:05 · 13.054830** | **777.00 (orders)** | **결함 (실제 766)** |

## B. 구현 (`impl/wo22-code.diff`)

| 파일 | 변경 |
|---|---|
| `core/strategy_engine.py` | `_fetch_upbit_avg_buy_price()` 신설 (LIVE 만, Upbit 잔고 avg_buy_price). Case 2 진입가 순서 **Upbit 직접 → account_positions → orders(체결 수량 = 지갑 수량일 때만)**, 로그 `[POSITION-SYNC] entry_price=… (출처: upbit_avg\|account_positions\|orders)`, 수량 불일치 WARNING. `_record_external_sell()` 신설 — Case 1 에서 `close_position` 직전 audit_trades `HTS_SELL` 1행 (가격 비움, 수량·직전 진입가, 메모) |
| `services/db.py` | `get_last_open_buy_order`: `executed_volume` 반환, 선택된 BUY 체결 시각 뒤 `HTS_SELL` 이 있으면 None. `get_last_open_buy_trade`: `type IN ('SELL','HTS_SELL')` 을 청산으로. `_TRADE_TYPE_DISPLAY["HTS_SELL"]="외부 매도"`, `trade_kind("HTS_SELL")="매도"` |
| `pages/dashboard.py` | 버전 1731 → 1145 |
| `tests/regressions/test_r_2026_09_30_wo12_boot_resume.py` | 출처 이름 변경 반영(`upbit_avg_buy_price` → `account_positions`, 캐시 출처) + 가짜 엔진에 보조 함수 2개 바인딩 |

`HTS_SELL` 은 `type='SELL'` 이 아니라서 손익 집계(대시보드 최근 거래·설정 이력 손익은 `type='SELL'` 행 사용)에 들어가지 않는다 (`*_REJECTED` 와 같은 방식). 감사 로그 페이지는 유형 "외부 매도", 유형 필터 "매도" 로 보인다. `docs/operations/terminology.md` 에 대응 추가. 체결가 칸은 빈칸.

바꾸지 않은 것: 매수·매도 판정식, 필터, 발주, 지표, WO-21 재계산 경로.

## C. 회귀 시험 (`tests/regressions/test_r_2026_10_05_wo22_wallet_sync_entry.py`, 5건)

| # | 내용 | 새 코드 | 구 코드 (`ce65f29`) |
|---|---|---|---|
| 1 | 사건 재현: 봇 BUY 777(앱 매도 기록 없음), 캐시 0, 지갑 13.05 avg 766 → 766 (출처 upbit_avg) | 통과 | **실패** `777.0 != 766.0` |
| 2 | Upbit 없음·캐시 770 → 770 / 둘 다 없음·BUY 수량=지갑 → 777(orders) / 수량 다름 → 진입가 없음 + WARNING·ERROR | 통과 | **실패** `False is not true` (수량 다름에도 777 로 복원) |
| 3 | 지갑 0 닫힘 → HTS_SELL 1행(가격 비움, 수량·진입가 777), 이후 `get_last_open_buy_order`·`get_last_open_buy_trade` None, 표시 "외부 매도"·필터 "매도" | 통과 | **실패** `0 != 1` |
| 4 | HTS_SELL 뒤 앱 재매수, Upbit·캐시 없음 → 옛 BUY 777 로 돌아가지 않음(복원 보류) | 통과 | **실패** `True is not false` (777 로 복원) |
| 5 | 사건 전체 재생: 777 보유 → 지갑 0 → 앱 매수 766 → 종가 765: pnl −0.13%, StopLossFilter 미발동 | 통과 | **실패** `777.0 != 766.0` (구 코드 pnl −1.54% → 손절) |

- 새 코드: `impl/test-new-code.txt` (WO-22 5건 + WO-12 14건, 19건 OK, `.env` 없는 worktree).
- 구 코드: `impl/test-old-code.txt` (`FAILED (failures=5)`, 모두 단언 실패).

## D. 관문과 단독 되돌리기 (`impl/gate-revert.txt`)

- 임시 worktree(`.env` 0개)에서 `dfc075f` 게이트 **295/295 통과** (WO-21 290 + 5). (출력의 `[B]` 머리말 "WO-21 시험" 은 WO-21 검사 스크립트를 고쳐 쓴 흔적이며 실제 실행은 WO-22 시험 파일 — 5건 OK.)
- `dfc075f` 단독 revert: **충돌 없음**, 5개 파일, py_compile 통과, 게이트 **290/290 통과**.

## E. 배포 때 알아둘 점

- 첫 외부 매수 복원 때 `[POSITION-SYNC] entry_price=… (출처: upbit_avg)` 1줄이 생긴다. 출처가 `orders` 이면 체결 수량이 지갑 수량과 같았다는 뜻이다.
- 지갑 0 닫힘이 생기면 `[POSITION-SYNC] 외부 매도 기록 (audit_trades HTS_SELL)` 1줄, 감사 로그 페이지에 "외부 매도" 행(체결가 빈칸)이 생긴다.
- 투자자 안내(배포 뒤): 체감 변경 — 감사 로그 페이지에 "외부 매도" 유형이 새로 보인다. 10-05 사건 답변과 함께.

## F. 묶음

- `report.md` (이 문서), `plan.md`, `incident.md`
- `impl/wo22-code.diff`, `impl/test-new-code.txt`, `impl/test-old-code.txt`, `impl/gate-revert.txt`, `impl/wo22_check.sh`
- `evidence/` (사건·A3 조회 결과와 스크립트)
- `commands.txt`, `git-log.txt`
