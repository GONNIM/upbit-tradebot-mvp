버전: v1.2026.10.05.1526 → v1.2026.10.06.1326

# WO-25 구현 보고 — BUY 평가 통과 뒤 주문 전 봇 안 차단을 audit_trades BUY_REJECTED 로 기록

- 작성: 2026-10-06
- 상태: **로컬 구현과 검증 완료. 배포는 별도 지시를 기다린다.** 서버는 조사 A 집계만 읽었고, pull·재시작은 하지 않았다.
- 코드 커밋: `9dd9bd7` (4개 파일, +441 / −1)
- 계획서: `plan.md`. A 분기 표: `a-branches.csv`
- 근거: 10-06 05:37 KRW-JTO BUY 평가 통과(id 77602) 뒤 가용 KRW 1원으로 주문하지 않았다. 알림은 갔지만 감사 기록은 없었다 (`docs/plans/2026-10-05-wo24-unfilled-buy-audit/deploy-report.md`).

## 1. 요약

| 항목 | 결과 |
|---|---|
| A. 가설 | **대부분 참.** 평가 통과 뒤 주문 전 차단 분기 15개(엔진 7, 지정가 5, 시장가 3) 중 14개가 audit_trades 에 행을 남기지 않았다. **급등 차단은 거짓.** 평가 단계 차단이라 `audit_buy_eval` overall_ok=0, failed_keys=[SURGE_FILTER] 로 이미 기록된다. |
| A. 실제 발생 (10-02 ~ 10-06 13:22) | BUY 평가 통과 7행: 주문 6, KRW 부족 차단 1 (05:37). 다른 분기는 0건이다. |
| B. 구현 | 14개 분기마다 `BUY_REJECTED` 1행. meta `stage='pre_order'`, `error_name`=분기 코드, note=사람이 읽는 사유. 판정식·필터·발주·알림·화면 코드는 바꾸지 않았다. |
| C. 시험 | 17건. 새 코드 17/17 OK. 구 코드는 13건 실패 (failures=12, errors=1). 통과 4건은 "행 없음" 을 확인하는 가드 시험이다 (아래 4절). |
| D. 관문 | `9dd9bd7` 게이트 319/319 통과. 단독 revert 는 충돌 없이 되고, 되돌린 뒤 게이트 **302/302** 통과. |
| 버전 | `pages/dashboard.py:495` v1.2026.10.05.1526 → v1.2026.10.06.1326 |

## 2. 조사 A — 평가 통과 뒤 `[UPBIT-ORDER]` 요청 전 분기

위치는 구 코드(`b37c7a0`) 기준이다. 건수는 서버 journal 10-02 00:00 ~ 10-06 13:22:39 (824,463줄)를 읽기 전용으로 집계했다 (`evidence/server-branch-counts.txt`). 0건으로 보고하기 전에 각 로그 문자열이 서버 코드에 실제로 있는지 먼저 확인했다 (같은 파일 상단).

| # | 위치 | 분기 | 로그 문자열 | 알림 | 구 코드 감사 기록 | 발생 | WO-25 |
|---|---|---|---|---|---|---|---|
| E1 | strategy_engine.py:1060 | 매매 일시중지 | `⏸️ [PAUSE] 실주문 스킵 … action=BUY` | 없음 | 없음 | 0 | `trading_paused` (BUY 만) |
| E2 | strategy_engine.py:1066 | 앞선 주문 진행 중 | `⏳ 주문 진행 중 → 매수 액션 대기` | 없음 | 없음 | 0 | `order_in_progress` |
| E3 | strategy_engine.py:1074 | 지표 오염 | `🚫 [POLLUTED] 지표 오염 상태 — 신규 매수 차단` | 없음 | audit_buy_eval 주석만 | 0 | `state_polluted` |
| E4 | strategy_engine.py:1161 | WO-2 지연 매수 교체 | `[PENDING-SUPERSEDE] 기존 대기 매수 취소` | 없음 | audit_buy_eval validation_reason 만 | 0 | `wo2_superseded` |
| E5 | strategy_engine.py:1199 | WO-2 지연 상한 초과 | `[PENDING-EXPIRE] 지연 상한 초과 → 취소` | 없음 | 위와 같음 | 0 | `wo2_max_wait_exceeded` |
| E6 | strategy_engine.py:1227·1242 | WO-2 재확인 불성립·예외 | `[PENDING-RESOLVE] 유효성 불성립 → 취소` 등 | 없음 | 위와 같음 | 0 | `wo2_signal_inverted` |
| E7 | strategy_engine.py:1327 | 이미 포지션 보유 | `⛔ 이미 포지션 보유 중 → BUY 무시` | 없음 | 없음 | 0 | `already_holding` |
| L1 | trader.py:907 | 호가 계산 실패 (예외) | `[BUY-LIMIT] 호가 라운딩 실패: …` | 없음 | 없음 | 0 | `tick_round_error` |
| L2 | trader.py:910 | 호가 단위 이탈 (0.5% 초과) | `[BUY-LIMIT] 호가 라운딩 비정상: …` | CRITICAL | logs 테이블만 | 0 | `tick_out_of_range` |
| L3 | trader.py:938 | KRW 잔고 0 | `[BUY-LIMIT] 활성 KRW 잔고 0 — 현재가 매수 불가` | WARNING | logs 테이블만 | 0 | `krw_zero` |
| **L4** | **trader.py:966** | **KRW 부족 (주문액 < 5,000)** | `[BUY-LIMIT] 활성 KRW 부족: 가용=… 계산=… (최소 5,000 미만)` | WARNING `fixed_buy_balance` | **logs 테이블만** | **1 (10-06 05:37:12 가용=1 계산=0)** | `krw_below_min` |
| L5 | trader.py:993 | 계산 수량 0 | `[BUY-LIMIT] 계산된 수량 0 — …` | 없음 | 없음 | 0 | `qty_zero` |
| M1 | trader.py:538 | KRW 잔고 0 (시장가) | `[BUY] 주문 불가: 잔고=…` | 없음 | 없음 | 0 | `krw_zero` |
| M2 | trader.py:552 | 최소 주문액 미만 (시장가) | `[BUY] 실거래 최소 주문금액 미만: … KRW` | 없음 | 없음 | 0 | `krw_below_min` |
| M3 | trader.py:633 | 재시도 직전 KRW 재확인 부족 | `[BUY-LIVE] attempt … 잔고 부족 중단 → …` | CRITICAL | **이미 BUY_REJECTED** (WO-9) + orders FAILED | 0 | 변경 없음 |

대상이 아닌 것:
- dry-run (trader.py:524·882): 실주문만 억제하는 검증 모드
- TEST 모드 폴백 (trader.py:899)
- WO-2 지연 등록 자체 (strategy_engine.py:1108): 대기이고, 해소 결과는 E4~E6 에서 기록된다
- 급등 필터 (strategy_incremental.py:949·1276): 평가 단계 차단
- BACKFILL 주문 생략 (strategy_engine.py:866·991): 설계상 재평가만 한다

실측 대조 (평가 통과 7행):

| audit_buy_eval id | 봉 | 결과 |
|---|---|---|
| 75021 | 10-02 03:35 | `[BUY-LIMIT] plan` → 주문 |
| 75063 | 10-02 07:55 | 주문 |
| 76229 | 10-04 14:15 | 주문 (뒤에 미체결 취소, 긴급 조사 건) |
| 76327 | 10-04 17:01 | 주문 |
| 76502 | 10-04 23:04 | 주문 |
| 76768 | 10-05 08:24 | 주문 |
| **77602** | **10-06 05:36** | **L4 KRW 부족 → 미주문, 감사 기록 없음** |

`[BUY-LIMIT] plan` 6건과 `❌ BUY 실패` 1건으로 7건이 모두 설명된다. 같은 기간 audit_trades BUY_REJECTED 는 0행이다.

## 3. 구현 B (`9dd9bd7`)

| 파일 | 변경 |
|---|---|
| `core/trader.py` | `_audit_reject(…, note=None)`: note 를 주면 그 문구를 쓴다. 기본은 그대로다. `_audit_preorder_reject(ticker, price, meta, code, note, extra)` 를 새로 뒀다: meta 에 `stage='pre_order'`, `error_name=code`, 그리고 분기별 수치(avail_krw, krw_to_use, risk_pct, rounded_price, order_type)를 넣는다. 호출 7곳: L1 945행, L2 976, L3 1009, L4 1043, L5 1054, M1 566, M2 585. 반환값(`{}`)·로그·알림은 그대로다. |
| `core/strategy_engine.py` | `_audit_buy_blocked(bar_ts, indicators, code, note, price, extra)` 를 새로 뒀다. meta 는 `_execute_buy` 와 같은 모양(bar, reason, bar_time KST, 지표)이고 트레이더 함수에 넘긴다. 호출: E1 1063행(BUY 일 때만), E2 1073, E3 1100(기존 audit_buy_eval 주석은 유지), E7 1394. E4~E6 은 `_audit_wo2_resolution` 에서 `validation_passed == 0` 일 때 1행을 남긴다 (1360행, 사유 문구는 `_WO2_BLOCK_NOTES`). 기록 실패는 삼킨다. |
| `pages/dashboard.py` | 버전 문자열만 바꿨다 |
| `tests/regressions/test_r_2026_10_06_wo25_preorder_reject_audit.py` | 17건 (신규) |

사유 문구 (note → 감사 로그 '거절 사유' 열):

| code | 문구 |
|---|---|
| krw_below_min | `매수 가능 KRW 부족 (가용 1원, 주문 비율 적용 주문액 0원 < 최소 5,000원) — 현재가 매수 주문 전 차단` (시장가는 "시장가 매수 주문 전 차단") |
| krw_zero | `매수 가능 KRW 없음 (가용 0원) — 현재가 매수 주문 전 차단` |
| tick_out_of_range | `주문가 호가 단위 이탈 (요청가 … → 조정가 …, 0.5% 초과) — 현재가 매수 주문 전 차단` |
| tick_round_error | `주문가 호가 단위 계산 실패 (…) — 현재가 매수 주문 전 차단` |
| qty_zero | `주문 수량 계산 결과 0 (주문가 …원, 주문액 …원) — 현재가 매수 주문 전 차단` |
| trading_paused | `매매 일시중지 상태 — 매수 주문 전 차단` |
| order_in_progress | `앞선 매수 주문이 진행 중(체결 대기) — 새 매수 주문 전 차단` (meta pending_buy_uuid) |
| state_polluted | `지표 오염 상태(재시작 전까지 신규 매수 금지) — 매수 주문 전 차단` |
| already_holding | `이미 포지션 보유 중 — 매수 주문 전 차단` |
| wo2_superseded / wo2_max_wait_exceeded / wo2_signal_inverted | `지연 매수 대기 중 새 매수 신호로 교체 …` / `지연 매수 대기 시간 초과 …` / `확정 종가로 다시 확인한 결과 매수 신호 불성립 …` |

지시의 "필요 811,830원" 꼴은 쓰지 않았다. 이 분기의 기준은 최소 주문액 5,000원이고, 평소 주문액은 그 순간의 가용 KRW × 주문 비율이라 따로 정해진 필요액이 없다. 그래서 가용·주문 비율 적용 주문액·최소액을 함께 적었다.

감사 로그 페이지 확인 (시험 (4), Streamlit AppTest 실제 렌더):
- 유형이 `⛔ 매수 거절` 로 보인다 (`services/db.py` `_TRADE_TYPE_DISPLAY`).
- note 가 '거절 사유' 열에 그대로 나온다 (`pages/audit_viewer.py:879·909`).
- 유형 필터 "거절" 로 걸러진다.
- 붉은 배경이다 (`_reject_mask`).
- 화면 코드는 바꾸지 않았다.

부수 효과: 같은 트레이더 함수를 쓰는 다른 경로에서도 주문 전 차단 시 1행이 생긴다.
- 강제 매수 (reason=force_buy)
- WO-24 미체결 시장가 전환 (`buy_market(krw_amount=…)` 의 M1·M2)

`terminology.md` 에 BUY_REJECTED(pre_order) 행을 추가했다 (문서 커밋).

## 4. 시험 C

| # | 시험 | 새 코드 | 구 코드 (b37c7a0) |
|---|---|---|---|
| (1) | KRW 부족 지정가 (05:37 재현: 가용 1, 비율 0.5) → 1행, note "매수 가능 KRW 부족 (가용 1원 … < 최소 5,000원)", reason EMA_GC, bar_time 05:36 | ok | FAIL `0 != 1` |
| (2) | 급등 차단: `SlowEmaSurgeFilter` 가 +3.9% 를 SURGE_FILTER 로 막고 `execute(HOLD)` → **행 없음** | ok | ok (가드) |
| (3) | 정상 주문 (지정가·시장가 성공) → 행 없음 | ok | ok (가드) |
| (4) | 페이지 표시 (AppTest): ⛔ 매수 거절, 거절 사유, 거절 필터 | ok | ERROR IndexError (행 없음) |
| L3 | 지정가 KRW 0 | ok | FAIL |
| L2 | 호가 이탈 (779 → 800) | ok | FAIL |
| L1 | 호가 계산 예외 | ok | FAIL |
| L5 | 수량 0 (가격 1e14) | ok | FAIL |
| M1 | 시장가 KRW 0 | ok | FAIL |
| M2 | 시장가 최소액 미만 (가용 6,000, 비율 0.5 → 2,998원) | ok | FAIL |
| E1 | 일시중지 BUY | ok | FAIL |
| E1' | 일시중지 SELL → 행 없음 | ok | ok (가드) |
| E2 | 주문 진행 중 (meta pending_buy_uuid) | ok | FAIL |
| E3 | 지표 오염 | ok | FAIL |
| E7 | 이미 보유 | ok | FAIL |
| E4~E6 | WO-2 3사유 각 1행, 유효성 통과는 행 없음 | ok | FAIL `[] != [...]` |
| 집계 | 거절 행은 type='BUY' 집계·최근 봇 매수 판정에 섞이지 않음 | ok | ok (가드) |

- 새 코드: `Ran 17 tests … OK` (`evidence/test-newcode.txt`)
- 구 코드: `FAILED (failures=12, errors=1)` (`evidence/test-oldcode-failures.txt`)
  - 임시 worktree(`b37c7a0`)에 새 시험 파일만 복사해 실행했다. 작업 트리는 건드리지 않았다.
- 실제 지정가·시장가 발주 함수는 시험 기본 설정에서 부르면 실패하도록 막았다. 정상 경로 시험만 성공 응답으로 바꿔 끼웠다.

## 5. 관문 D (`evidence/gate-and-revert.txt`)

임시 worktree 에서 돌렸다. `.env` 0개, 더미 env, main 은 바꾸지 않았다.

| 단계 | 결과 |
|---|---|
| [A] 9dd9bd7 게이트 | ✅ 회귀 테스트 319/319 통과 (302 + 17) |
| [B] 9dd9bd7 WO-25 시험 | Ran 17, OK |
| [D] 9dd9bd7 단독 revert | 충돌 없음. 4개 파일 +2 / −441. py_compile OK. 게이트 302/302 통과 |

UI 규칙 1-A: 바뀐 UI 파일은 `pages/dashboard.py` 의 버전 문자열뿐이다. 화면 추가·삭제·이동·접힘은 없다. 감사 로그 페이지는 기존 거절 표시를 그대로 쓰고, 새 행이 생길 수 있다.

## 6. 운영자 결정 필요

1. **시험 (2) 급등 차단.** 지시는 "→ 1행" 이었지만 조사 결과 평가 단계 차단이라 "행 없음" 으로 구현하고 시험했다. 근거는 2절과 `core/strategy_incremental.py:949`. 급등 차단 봉마다 BUY_REJECTED 를 남기려면 별도 결정이 필요하다. 조건이 이어지는 동안 매 봉 생길 수 있다.
2. **감사 로그 페이지 문구.** 거절 경고 "⛔ 발주 거절 N건 — 거래소가 봇 주문을 받지 않았습니다 (체결 아님)" (`pages/audit_viewer.py:818`) 와 필터 도움말 "거절 = 거래소가 봇 주문을 받지 않은 건" (`:803`) 은 주문 전 봇 안 차단 행에는 맞지 않는다. '거절 사유' 열의 "— … 주문 전 차단" 으로 구분은 된다. 문구를 바꾸려면 UI 변경(규칙 1-A)이므로 지시를 기다린다.
3. 배포 관찰 새 기준 (계획서 5절): 1:1 대조의 "미요청" 행마다 같은 봉의 BUY_REJECTED 행이 있어야 한다.

## 7. 규칙 준수

- heredoc 과 와일드카드 패턴은 쓰지 않았다.
- 서버는 조사 A 집계(journal, DB `mode=ro`)만 읽었다.
- 투자자 포지션·주문·설정은 건드리지 않았다.

## 8. 근거 파일

| 파일 | 내용 |
|---|---|
| `a-branches.csv` | 조사 A 표 (분기, 위치, 로그, 알림, 감사 기록, 발생, WO-25 처리) |
| `evidence/server-branch-counts.txt` | 서버 journal·DB 집계 출력 (코드 존재 확인 포함) |
| `evidence/wo25_count.sh` | 집계 스크립트 (읽기 전용) |
| `evidence/code-diff-9dd9bd7.txt` | `git show 9dd9bd7` |
| `evidence/test-newcode.txt` / `test-oldcode-failures.txt` | 새 코드 / 구 코드 시험 출력 |
| `evidence/gate-and-revert.txt`, `evidence/wo25_check.sh` | 게이트·단독 revert 출력과 스크립트 |
| `commands.txt`, `git-log.txt` | 실행 명령 원문, git log |
