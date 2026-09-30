# WO-9 계획서 — 묶인 수량 인지와 발주 거절 가시화 (초안)

- 작성일: 2026-09-30
- 상태: **승인 완료 (A1~A8), 로컬 구현·검증 완료, 배포 승인 대기** — 구현 결과는 10절, A6 측정은 부록 A
- 근거 사건: `docs/plans/2026-09-30-jto-dc-claim/report.md` (판정 확정: 외부 지정가 매도 주문에 의한 수량 묶임)
- 기준 코드: 로컬·서버 HEAD `2a3dcd7` (코드 기준 `4c523e5`와 같고, 이후 커밋은 문서 전용입니다)
- 기준 버전: `pages/dashboard.py:467` `v1.2026.09.18.1600`

---

## 0. 한 줄 요약

사용자가 봇 밖에서 넣은 미체결 주문이 수량을 묶으면, 봇의 매도가 거래소에서 거절됩니다. WO-9는 이 상황을 사용자가 **알림, 대시보드, 감사 로그 페이지에서 바로 알아볼 수 있게** 만듭니다. 매매 판정 로직은 바꾸지 않습니다.

## 1. 원칙

1. **매매 판정 로직은 바꾸지 않습니다.** 매수·매도 신호, 필터 순서, 임계값 판정, 발주 여부, 수량 계산은 그대로 둡니다. 바꾸는 것은 알림, 화면 표시, 감사 기록뿐입니다.
2. 이번 사건의 두 거절(09-30 01:10:10, 03:00:06)은 **소급해서 기록하지 않습니다.** 이 두 건은 조사 문서(`docs/plans/2026-09-30-jto-dc-claim/report.md`)를 참조하는 것으로 대신합니다.
3. 과거 데이터는 고치지 않습니다. 기존 `audit_trades` 행(과거 `BUY_FAILED_API` 4건, `HTS_BUY` 284건, `HTS_BUY_ADD` 340건 포함)은 그대로 둡니다.
4. 커밋은 하나로 만듭니다. 롤백은 `git revert <WO-9 커밋>` 한 번으로 끝나야 합니다. 스키마 변경은 열 추가(ADD COLUMN)만 합니다. 그래서 되돌린 뒤에도 옛 코드가 새 열을 무시하고 정상 동작합니다.

## 2. 현황 점검 결과 (착수 전 사실 확인)

이 절은 요청 항목과 현재 코드가 다른 부분을 먼저 정리합니다.

| 항목 | 요청 내용 | 현재 코드 상태 |
|---|---|---|
| (a) 매도 거절 알림 | CRITICAL 발송 신설 | **이미 있습니다.** `core/trader.py:1200~1218`이 CRITICAL을 보냅니다. 안내 문구가 원인(외부 주문)을 가리키지 않는 점만 부족합니다. |
| (a) 매수 거절 알림 | 같은 경로 검토 | 시장가 매수(`core/trader.py:627~640`)와 지정가 매수(`core/trader.py:965~980`)에 CRITICAL 알림이 **이미 있습니다.** |
| (b) 묶인 수량 보존 | position에 locked_qty 보존 | DB에는 **이미 보존합니다.** `account_positions.virtual_coin_locked` (`services/db.py:692` `update_coin_position`, `services/init_db.py:863~873`). 엔진 메모리(PositionState)와 화면 경고에는 없습니다. |
| (b) 대시보드 표시 | 배지 | `pages/dashboard.py:811~812`에 "🔒 Lock" 수치 표시는 **이미 있습니다.** 매도 불가 상태라는 의미 표시와 알림은 없습니다. |
| (e) 거절 기록 | audit_trades 기록 | 시장가 매수 실패만 `type='BUY'`, `reason='BUY_FAILED_API'`로 기록합니다(`core/trader.py:685~699`). 매도 거절과 지정가 매수 거절은 `logs` 테이블에만 남습니다(`core/trader.py:1194~1198`). |

JTO 사건에서도 CRITICAL 알림은 발송됐을 가능성이 높습니다(조사 보고서 9절). 따라서 이번 WO의 핵심은 알림을 새로 만드는 것이 아닙니다. 핵심은 **원인을 알려 주는 문구**, **묶임 상태의 가시화**, **감사 로그 페이지에서의 확인**입니다.

## 3. 항목별 변경안

### (a) 발주 거절 알림 문구 보강

**변경 파일·함수**
- `services/error_messages.py` — 거절 코드별 사용자 안내 문구 표를 새로 둡니다(함수 `guidance_for_upbit_error(err_summary) -> str`). 기존 `label_for_upbit_error`(라벨, `:23` `"insufficient_funds_ask": "매도 가능 수량 부족"`)는 그대로 둡니다.
- `core/trader.py` `sell_market` 실패 분기(`:1193~1218`) — 알림 본문의 고정 안내 "💡 보유 수량 또는 API 권한 점검"(`:1210`)을 위 함수의 결과로 바꿉니다.
- `core/trader.py` `buy_market` 최종 실패 분기(`:622~640`)와 `buy_limit` 실패 분기(`:965~980`) — 같은 함수로 안내 문구를 붙입니다.

**안내 문구 (초안)**

| 거절 코드 | 안내 문구 |
|---|---|
| insufficient_funds_ask | 주문 가능 수량 부족 — 외부 미체결 매도 주문 확인 요망 (업비트 앱 → 거래내역 → 미체결) |
| insufficient_funds_bid | 주문 가능 KRW 부족 — 외부 미체결 매수 주문 또는 KRW 잔고 확인 요망 |
| under_min_total_ask / under_min_total_bid | 최소 주문 금액(5,000원) 미만 |
| 그 밖의 코드 | 기존 문구 유지 |

**중복 억제 키와 TTL**

| 경로 | 현재 | 변경안 |
|---|---|---|
| 매도 거절 | `sell_fail:{ticker}:{err_summary}`, 60초 (`:1214~1215`) | `sell_reject:{ticker}:{error_name}`, 300초 |
| 시장가 매수 거절 | `buy_fail:{ticker}:{err_summary}`, 60초 (`:639`) | `buy_reject:{ticker}:{error_name}`, 300초 |
| 지정가 매수 거절 | `fixed_buy_fail:{ticker}:{err_summary[:80]}` (`:980`) | `buy_reject:{ticker}:{error_name}`, 300초 |
| API 인증 실패 | `api_auth:{err_summary}`, 600초 | 변경 없음 |

TTL 300초는 5분봉 한 개 길이입니다. 봉마다 거절이 반복되면 봉마다 한 번씩 알림이 갑니다. 거절 코드 단위로 묶으므로, 응답 문구가 조금씩 달라도 같은 봉 안에서는 한 번만 보냅니다.

**매수 거절도 같은 경로로 다루는지 검토한 결과**: 다룹니다. 세 실패 분기가 모두 이미 CRITICAL을 보내므로, 문구와 dedupe 규칙만 한 함수로 맞춥니다. 알림 등급은 바꾸지 않습니다.

### (b) 묶인 수량 인지

**현재 동작**: 잔고 동기화는 가용(`balance`)과 묶임(`locked`)을 따로 읽어 DB에 저장합니다(`services/db.py:2158~2185`, `:2188~2216`). 그러나 다음 세 가지가 빠져 있습니다.
1. 대시보드는 가용 수량 `qty`로만 보유 여부를 판단합니다. 평가액(`pages/dashboard.py:784` `coin_val = qty × last_price`), WO-7 배지(`:817` `if qty > 0`), 손익 칸(`:827` `if qty > 0`)이 모두 그렇습니다. 그래서 전량이 묶이면 평가액이 0원이 되고, 손익 칸이 "미보유"로 바뀌며, WO-7 배지도 사라집니다. JTO 사건의 22:31~06:23 동안 화면이 이 상태였습니다.
2. "가용 0, 묶임 > 0" 상태를 알려 주는 알림이 없습니다.
3. 엔진 메모리의 포지션(PositionState)은 묶임을 모릅니다.

**변경 파일·함수**
- `engine/order_reconciler.py` 주기 잔고 동기화(`:520~613`) — 봇이 포지션을 들고 있는 종목에서 상태가 "가용 > 0"에서 "가용 0 + 묶임 > 0"으로 바뀌면 WARNING 알림을 **한 번** 보냅니다.
  - 제목: `⚠️ 매도 불가 — {ticker} 전량이 외부 미체결 주문에 묶여 있음`
  - 본문: 묶인 수량, 가용 수량, "봇 매도 신호가 나도 거래소가 거절합니다. 외부 미체결 주문을 확인하세요."
  - 한 번만 보내는 방법: `account_positions.meta`에 `locked_warned=true`를 적습니다. 묶임이 풀려 가용이 0보다 커지면 이 표시를 지웁니다. 재시작 뒤에도 같은 상태에서는 다시 보내지 않습니다. 보조로 dedupe 키 `locked_qty:{ticker}`, TTL 3600초를 둡니다.
- `pages/dashboard.py` 자산 현황의 코인 칸(`:807~823`) — `qty == 0` 이고 `locked_qty > 0` 이면 지표(metric) 바로 아래에 `st.caption("⛔ 매도 불가 — 외부 미체결 주문 대기 (묶임 {locked_qty:,.6f})")`을 표시합니다.
- `core/position_state.py` — 표시·진단용 필드 `locked_qty`를 둡니다. 동기화 때 값만 채웁니다. **매도 판정과 발주는 이 값을 읽지 않습니다.** (발주 전 사전 차단은 판정 로직 변경이므로 이번 범위에서 제외합니다.)

**WO-7 배지와 위치 충돌 점검**: 두 배지는 같은 칸(`col_coin`)에 놓입니다. 표시 순서는 metric → (b) 매도 불가 배지 → WO-7 진입 경로 배지로 제안합니다. 지금은 WO-7 배지 조건이 `qty > 0`(`:817`)이라, 전량이 묶이면 WO-7 배지가 사라집니다. 이 조건을 `(qty + locked_qty) > 0`으로 넓히면 두 배지가 함께 보입니다. 이 조건 변경은 WO-7의 표시 동작을 바꾸므로 **승인 대기 항목 A4**로 둡니다. 평가액(`:784`)과 손익 칸(`:827`)에 묶인 수량을 넣을지도 표시 변경이므로 **승인 대기 항목 A5**로 둡니다.

### (c) HTS 매수 감지 기준 정정

**현재 동작**: `engine/order_reconciler.py:544~547`은 DB의 가용 수량(`get_position_qty`, `services/db.py:2469`, `SELECT virtual_coin`)과 업비트의 가용 수량(`balance`)만 비교합니다. 외부 매도 주문이 취소되면 묶였던 수량이 가용으로 돌아오고, 이것이 "잔고 증가"로 잡혀 HTS 매수로 기록됩니다. 이번 사례는 `audit_trades` id 1158(2026-09-30 06:23:15, `HTS_BUY`, 767.0)입니다.

**변경안**
- `services/db.py`에 `get_position_total_qty(user_id, ticker) -> float`를 새로 둡니다. 값은 `virtual_coin + virtual_coin_locked`입니다.
- `engine/order_reconciler.py:544~547`의 비교를 다음처럼 바꿉니다.
  - `prev_total = get_position_total_qty(...)`
  - `curr_total = balance + locked`
  - `qty_delta = curr_total - prev_total`
  - 감지 조건 `qty_delta > 1e-8`, 봇 매수 30초 제외(`has_recent_bot_buy_for_ticker`, `services/db.py:768`), 신규/추가 구분(`prev_total > 0`)은 그대로 둡니다.
- 콜백에 넘기는 수량(`qty=curr_qty`, `:602~608`)은 지금처럼 가용 수량을 유지합니다. 엔진 포지션 수량의 의미를 바꾸지 않기 위해서입니다.

**재현 테스트 케이스 (이번 사례 그대로)**

| 단계 | DB (가용, 묶임) | 업비트 (balance, locked) | 기존 결과 | 변경 후 기대 |
|---|---|---|---|---|
| 22:31 외부 매도 주문 | (2097.517, 0) | (0, 2097.517) | 감지 없음 | 감지 없음 |
| 06:23 외부 주문 취소 | (0, 2097.517) | (2097.517, 0) | **HTS_BUY 오기록** | 감지 없음 |
| 대조: 실제 외부 매수 | (0, 0) | (100, 0) | HTS_BUY | HTS_BUY |
| 대조: 묶인 중 추가 매수 | (0, 2097.517) | (500, 2097.517) | HTS_BUY(오분류: 신규) | HTS_BUY_ADD |

**영향 분석**

| 경로 | 오기록이 일으키던 영향 | 정정 뒤 |
|---|---|---|
| 평균가 재동기화 (`core/strategy_engine.py:275~322` `_on_hts_detect`) | `position.avg_price`를 업비트 `avg_buy_price`로 덮어씁니다. 묶임 해제에서는 평균가가 같아 값 변화는 없었습니다. `position.qty`도 같은 값입니다. | 호출되지 않습니다. 영향 없습니다. |
| Trailing 리셋 (`core/strategy_engine.py:303~316`) | `HTS_BUY_ADD`로 잡히면(일부만 묶였다가 풀린 경우, prev > 0) `highest_price`, `trailing_armed`, `trailing_fixed_amount`가 모두 지워집니다. **이미 켜진 트레일링 스톱이 풀립니다.** JTO 사례는 prev = 0이라 `HTS_BUY`로 잡혀 리셋은 없었습니다. | 잘못된 리셋이 사라집니다. |
| `hts_buy` 표시 (`services/db.py:2612` `mark_position_as_hts_buy`) | 봇 매수 포지션에 `hts_buy=true`가 붙습니다. 이 값은 매도 판정에 쓰이지 않습니다(`core/filters/sell_filters.py:36`, Policy P-3). 그러나 WO-8 알림 등급 조정(`core/strategy_incremental.py:1182~1184`)이 이 값을 읽습니다. | 봇 매수 포지션이 외부 매수로 표시되지 않습니다. |
| WO-7 진입 경로 배지 (`services/db.py:2497` `get_position_entry_source`) | 마지막 `type='BUY'` 행의 reason을 읽습니다. 오기록 뒤에는 봇 매수인데도 "👤 외부 매수(HTS)"로 보입니다. | 봇 매수는 "🤖 봇 매수"로 유지됩니다. |
| audit_trades | 가짜 BUY 행이 생깁니다. 스냅샷 손익 집계(`services/settings_history.py:654`)의 매수 목록에 들어갑니다. | 가짜 행이 생기지 않습니다. |

**남는 한계**: 한 동기화 주기(약 1분) 안에 외부 매도 일부 체결과 외부 매수가 함께 일어나면 합계가 상쇄되어 매수를 놓칠 수 있습니다. 드문 경우이므로 기록만 해 둡니다.

**과거 기록 측정 (승인 대기 항목 A6)**: 과거 `HTS_BUY` 284건과 `HTS_BUY_ADD` 340건 중 묶임 해제 오기록이 몇 건인지 읽기 전용으로 측정할 수 있습니다. 방법은 각 행 시각 ±2분의 업비트 취소 주문 조회(GET `/v1/orders/closed`)입니다. 데이터는 고치지 않습니다.

### (d) 감사 기록의 손절 기준 정정

**원인 (특정 완료)**
- 감사 행의 `sl_price`와 `tp_price`는 `core/strategy_engine.py:1729~1730`에서 `self.stop_loss`, `self.take_profit`으로 계산합니다.
- 이 두 값은 엔진을 만들 때 한 번만 정해집니다(`core/strategy_engine.py:206~207`, 호출 `engine/live_loop.py:711~712` `params.take_profit`, `params.stop_loss`).
- 조건 파일이 바뀌면 `engine/live_loop.py:365~392`가 `strategy.stop_loss`, `strategy.take_profit`과 필터 임계값만 갱신합니다. 엔진의 두 값은 갱신하지 않습니다.
- 엔진은 2026-09-25 12:41:06에 다시 만들어졌습니다(settings_history id 170, 그때 params `stop_loss=0.015`, `take_profit=0.025`). 09-28 05:16에 손절을 3.0%로 바꾼 것(id 171)은 필터에만 반영됐습니다.
- 그래서 감사 행은 `sl_price = 767 × 0.985 = 755.495`, `tp_price = 767 × 1.025 = 786.175`로 남았습니다. `sl_hit`(`:1761`)도 이 값으로 계산됐습니다. 매도 행의 `trigger_reason`(`:1843~1852`)은 `sl_hit`을 가장 먼저 보므로 실제 사유 `EMA_DC` 대신 `STOP_LOSS`가 적혔습니다.
- `self.stop_loss`와 `self.take_profit`을 읽는 곳은 `:1729~1730` 두 줄뿐입니다. 엔진의 매매 판정은 이 값을 쓰지 않습니다.

**변경안 (기록만 정정)**
- `core/strategy_engine.py:1729~1730` — 임계값을 `self.strategy.stop_loss`, `self.strategy.take_profit`(필터와 같은 값)에서 읽습니다. 값이 없으면 기존 `self.*`로 돌아갑니다. `core/trader.py:292` `_current_thresholds()`와 같은 방식입니다.
- `core/strategy_engine.py:1843~1852` — `trigger_reason`은 전략이 실제로 정한 사유 `self.strategy.last_sell_reason`을 먼저 씁니다(발주 meta와 같은 값, `:1301~1303`). 값이 없을 때만 기존 `sl_hit`, `tp_hit`, `cross_status` 순서로 추정합니다.
- 판정 로직(필터, `Action` 결정, 발주)은 바꾸지 않습니다. 감사 행의 `sl_price`, `tp_price`, `sl_hit`, `tp_hit`, `trigger_reason`, `trigger_key`만 바뀝니다.

### (e) 발주 거절의 감사 기록과 감사 로그 페이지 표시

**기록 지점 (거래소 응답 수신 직후)**

| 경로 | 위치 | 현재 기록 | 변경 |
|---|---|---|---|
| 시장가 매도 | `core/trader.py:1180~1193` (`if not call["ok"]` → `[SELL-LIVE] FAILURE`) | `logs` ERROR만 (`:1194~1198`) | `audit_trades` `type='SELL_REJECTED'` 행 추가 |
| 시장가 매수 | `core/trader.py:615~699` (`[BUY-LIVE] FINAL FAILURE`, `:622`) | `audit_trades` `type='BUY'`, `reason='BUY_FAILED_API'` (`:685~699`), `orders` FAILED (`:703~712`) | `type='BUY_REJECTED'`로 바꿉니다. reason에는 신호 사유를 둡니다. `orders` FAILED 기록은 유지합니다. |
| 지정가 매수(고정가, 강제 매수) | `core/trader.py:953~965` (`if not call["ok"]` → `[BUY-LIMIT] FAILURE`) | `logs` ERROR, `orders` FAILED | `audit_trades` `type='BUY_REJECTED'` 행 추가 |

매도 거절에는 `orders` 행을 만들지 않습니다. 대시보드의 최근 거래 내역과 손익은 `orders`를 읽기 때문입니다(`services/db.py:174` `fetch_recent_orders`, `pages/dashboard.py:852`, `:910~990`).

**행 내용**

| 열 | 값 | 출처 |
|---|---|---|
| timestamp | 거절 응답 수신 시각 (KST) | `now_kst()` |
| ticker | 종목 | 인자 |
| type | `SELL_REJECTED` / `BUY_REJECTED` | 신규 값 |
| reason | 신호 사유 (EMA_DC, STOP_LOSS, EMA_GC, force_buy 등) | `meta["reason"]` (`core/strategy_engine.py:1312`) |
| price | 시도 시점 가격 | 인자 `price` |
| qty (신규 열) | 시도 수량 | 인자 `qty` |
| entry_price, bars_held, entry_bar, bar_time | 포지션 정보 | `meta` |
| note (신규 열) | 사용자용 한글 설명. 예: "주문 가능 수량 부족 — 외부 미체결 매도 주문 확인 요망" | (a)의 `guidance_for_upbit_error` |
| meta (신규 열, JSON) | `{"error_name": "insufficient_funds_ask", "http_status": 400, "error_message": "주문 가능한 금액(JTO)이 부족합니다.", "attempts": n}` | `call` 응답 요지 |

**스키마 변경**: `services/init_db.py`에 `ensure_audit_trades_reject_columns(user_id)`를 새로 두고, `ensure_all_schemas`(`:912`)에서 부릅니다. 방식은 기존 `_safe_alter`(`:386`)와 같습니다.
- `ALTER TABLE audit_trades ADD COLUMN qty REAL`
- `ALTER TABLE audit_trades ADD COLUMN note TEXT`
- `ALTER TABLE audit_trades ADD COLUMN meta TEXT`

`services/db.py:1435` `insert_trade_audit`에 선택 인자 `qty=None, note=None, meta=None`을 더합니다. 기존 호출은 바꿀 필요가 없습니다. `core/trader.py`에는 거절 전용 헬퍼 `_audit_reject(side, ticker, price, qty, meta, call, err_summary)`를 두어 세 경로가 같이 씁니다. 헬퍼 안의 예외는 모두 삼킵니다. 기록 실패가 발주 흐름을 막으면 안 되기 때문입니다.

**집계 질의 전수 점검 (`audit_trades`를 읽는 모든 곳)**

| 위치 | 용도 | type 필터 | 새 type의 영향 |
|---|---|---|---|
| `services/settings_history.py:654~655` `compute_pnl_for_snapshot` | 설정 스냅샷별 손익 | `== "BUY"`, `== "SELL"` 정확 일치 | 제외됩니다. 안전합니다. |
| `services/settings_history.py:601` `fetch_trades_for_snapshot` | 스냅샷별 거래 목록 표시 (`pages/settings_history.py:370`) | 없음 | 목록에 보입니다. 표시 목적이므로 그대로 둡니다. 손익 계산은 위 줄에서 걸러집니다. |
| `services/db.py:790` `has_recent_bot_buy_for_ticker` | 봇 매수 30초 제외 | `type='BUY'` | 제외됩니다. 현재는 과거식 `BUY_FAILED_API` 행이 "최근 봇 매수"로 잘못 잡힐 수 있었습니다. 정정 뒤 이 문제가 사라집니다. |
| `services/db.py:1913` `estimate_bars_held_from_audit` | 보유 봉수 추정 | `type='BUY'` | 제외됩니다. 안전합니다. |
| `services/db.py:2517` `get_position_entry_source` (WO-7) | 진입 경로 배지 | `type='BUY'` | 제외됩니다. 안전합니다. |
| `services/db.py:541` `fetch_latest_trade_audit` → `pages/dashboard.py:1215` `get_latest_any_signal` | 대시보드 "최근 신호" 카드 | 없음 | 거절 행이 "최근 체결"로 보일 수 있습니다. **승인 대기 항목 A3**으로 둡니다. |
| `services/db.py:1604` `fetch_trades_audit` → `pages/audit_viewer.py:796` | 감사 로그 체결 탭 | 없음 | 표시됩니다. 이번 목적에 맞습니다. |
| `utils/smoke_test.py:81` | 전체 행 수 | 없음 | 행 수만 셉니다. 영향 없습니다. |
| 대시보드 최근 거래 손익 (`pages/dashboard.py:852`, `:910~990`) | 실현 손익 | `orders` 테이블 사용 | `audit_trades`를 읽지 않습니다. 매도 거절은 `orders`에 쓰지 않으므로 영향이 없습니다. |

**감사 로그 페이지 표시 (`pages/audit_viewer.py`)**

이 페이지는 렌더 함수로 나뉘어 있지 않습니다. 섹션 라디오(`:237` `label_map`, `:251` `st.radio`)가 고른 값에 따라 최상위 `elif` 블록이 그립니다. 체결 탭은 `:794` `elif section == "trades":` 블록입니다.

- 조회: `services/db.py:1604~1625` `fetch_trades_audit`의 SELECT에 `qty, note, meta`를 더합니다. 이에 맞춰 `pages/audit_viewer.py:800~803`의 열 목록도 고칩니다. 두 곳의 열 순서가 어긋나면 표가 깨지므로 테스트로 묶습니다.
- 유형 필터: 체결 탭 제목(`:795`) 바로 아래에 `st.multiselect("유형", ["매수", "매도", "거절"], default=전체)`를 둡니다. "거절"은 `type`이 `_REJECTED`로 끝나는 행입니다.
- 눈에 띄는 구분: `type` 표시값 앞에 `⛔`를 붙입니다(예: `⛔ 매도 거절`). 행 배경은 pandas Styler로 옅은 붉은색을 칠합니다. 색만으로 구분하지 않도록 아이콘과 글자를 함께 씁니다.
- 한글 설명: `note` 열을 "거절 사유"라는 이름으로 그대로 보여 줍니다. 열 폭 때문에 잘리지 않도록 `st.dataframe`의 `column_config`로 넓게 잡습니다.
- 이 수정은 UI 파일 수정이므로 project-rules 1-A, 1-B 단계를 따릅니다. 접힘(`expanded=False`)으로 옮기는 요소는 없습니다.

**재현 테스트 (왕복 4단계)**: `tests/regressions/test_r_2026_09_30_wo9_sell_reject_roundtrip.py`
1. 모의 거래소 응답: `_upbit_sell_market`을 바꿔치기(monkeypatch)해 `status=400`, `error_name="insufficient_funds_ask"`를 돌려줍니다.
2. 기록: `sell_market(...)` 호출 뒤 임시 DB의 `audit_trades`에 `type='SELL_REJECTED'`, `reason='EMA_DC'`, `qty`, `note`(한글 설명 포함), `meta.error_name`이 있는지 확인합니다.
3. 표시: `fetch_trades_audit` 결과로 체결 탭 표 생성 로직을 돌려, 거절 행에 `⛔`와 한글 설명이 들어 있는지 확인합니다. "거절" 필터만 골랐을 때 이 행만 남는지도 확인합니다.
4. 손익 제외: 같은 DB에 정상 BUY/SELL 한 쌍을 넣고 `compute_pnl_for_snapshot` 결과가 거절 행을 넣기 전과 같은지 확인합니다. `has_recent_bot_buy_for_ticker`, `get_position_entry_source`가 거절 행을 무시하는지도 확인합니다.

같은 방식으로 `BUY_REJECTED`(시장가, 지정가) 테스트를 둡니다.

## 4. 변경 파일 목록

| 파일 | 항목 | 변경 내용 |
|---|---|---|
| `services/error_messages.py` | a, e | `guidance_for_upbit_error` 신설 |
| `core/trader.py` | a, e | 세 실패 분기 알림 문구·dedupe 변경, `_audit_reject` 신설, 시장가 매수 실패 기록의 type 변경 |
| `engine/order_reconciler.py` | b, c | HTS 감지 합계 비교, 묶임 전환 WARNING 1회 |
| `services/db.py` | b, c, e | `get_position_total_qty` 신설, `insert_trade_audit` 선택 인자, `fetch_trades_audit` SELECT 열 추가 |
| `services/init_db.py` | e | `ensure_audit_trades_reject_columns` 신설, `ensure_all_schemas` 등록 |
| `core/position_state.py` | b | 표시용 `locked_qty` 필드 |
| `core/strategy_engine.py` | d | 감사용 임계값 출처, `trigger_reason` 우선순위 |
| `pages/dashboard.py` | b | 매도 불가 배지, (승인 시) WO-7 배지 조건 |
| `pages/audit_viewer.py` | e | 유형 필터, ⛔ 표시, 거절 사유 열 |
| `tests/regressions/test_r_2026_09_30_wo9_*.py` | a~e | 재현 테스트 |

필터(`core/filters/*`), 전략 판정(`core/strategy_incremental.py`의 매수·매도 결정부), 발주 수량 계산은 수정 대상이 아닙니다.

## 5. 검증

1. **로컬**
   - `python3 -m py_compile` (변경 파일 전부)
   - `bash scripts/regression_gate.sh` (UI 파일 수정 포함)
   - 재현 테스트: (c) 묶임 해제 케이스 4행 표, (d) 임계값 1.5% 엔진 + 3.0% 필터 조건에서 감사 행 `sl_price = entry × 0.97` 확인, (e) 왕복 4단계
   - 기존 회귀 테스트 전부 통과
   - 판정 무변경 확인: 변경 전후 커밋에서 같은 봉 입력으로 `Action` 결과가 같은지 비교하는 테스트 한 개(`tests/test_sell_filter_execution.py` 확장)
2. **배포 뒤 30분 관측** (재시작 필요, 사용자 승인 뒤)
   - journal에 새 오류(Traceback, `[AUDIT]` 실패) 0건
   - 감사 로그 페이지 체결 탭에서 유형 필터와 표 렌더 확인(브라우저 새로고침 요청, 1-A 3층)
   - 대시보드 자산 현황 칸 배치 확인(WO-7 배지 포함)
   - 새 열 존재 확인: `sqlite3 "file:...?mode=ro" "PRAGMA table_info(audit_trades);"`
3. **자연 발생 관측**
   - 다음 HTS 매수가 일어났을 때 (c) 관측: `[HTS-DETECT]` 로그의 수량이 합계 기준으로 찍히는지, 봇 매수 포지션에 외부 주문을 걸었다가 취소했을 때 `HTS_BUY`가 생기지 않는지 확인합니다.
   - 다음 발주 거절이 일어났을 때 (a)·(e) 관측: 텔레그램 문구, 감사 로그 페이지의 ⛔ 행과 한글 설명을 확인합니다.

## 6. 롤백

- `git revert <WO-9 커밋>` 한 번 → `deploy-tradebot`.
- 새 열(`qty`, `note`, `meta`)은 남지만 옛 코드는 이 열을 읽지 않으므로 동작에 영향이 없습니다. 열을 지우는 작업은 하지 않습니다.
- `account_positions.meta`의 `locked_warned` 키도 옛 코드는 읽지 않습니다.

## 7. 다른 워크오더와의 충돌 점검

| 대상 | 점검 내용 | 결과 |
|---|---|---|
| WO-7 (`ad09377`, 진입 경로 배지) | 배지 위치 | (b) 배지와 같은 칸(`pages/dashboard.py:807~823`)입니다. 순서는 metric → (b) → WO-7로 제안합니다. 표시 조건 `qty > 0`(`:817`) 확장 여부는 A4입니다. |
| WO-7 | 진입 경로 판정 | `get_position_entry_source`는 `type='BUY'`만 읽습니다. 거절 행은 영향이 없습니다. (c) 정정으로 묶임 해제 뒤 "👤 외부 매수" 오표시가 사라집니다. |
| WO-8b (`8982d27`, 강제 매수 uuid 등록 → apply_entry 관문) | 지정가 매수 실패 분기에 기록을 더하는 것 | 실패 분기는 uuid 등록 전에 `return {}` 합니다(`core/trader.py:965~995`). 거절 기록은 이 반환 직전에만 들어가므로 uuid 등록·체결 콜백 경로와 겹치지 않습니다. 강제 매수 거절 행은 `reason='force_buy'`, `type='BUY_REJECTED'`로 남고, WO-7 배지의 "🛑 강제 매수" 판정(`type='BUY'`만 읽음)에는 들어가지 않습니다. |
| WO-8 (알림 등급 절충안) | `hts_buy` 기반 강등·승격 (`core/strategy_incremental.py:1175~1200`) | (c) 정정으로 가짜 `hts_buy`가 줄어 강등 조건이 잘못 켜지는 일이 줄어듭니다. 로직은 바꾸지 않습니다. |
| Issue #17 (Dead 상태 HTS 매수 손절 스킵) | `hts_buy` 플래그 의존 여부 | 현재 필터는 Policy P-3에 따라 `hts_buy`를 판정에 쓰지 않습니다(`core/filters/sell_filters.py:36`). 영향이 없습니다. |

## 8. 승인 대기 항목

| 번호 | 내용 | 제안 |
|---|---|---|
| A1 | (a) dedupe 키를 거절 코드 단위로 바꾸고 TTL을 300초로 할지 | 제안대로 진행 |
| A2 | (a) 안내 문구 표 초안 | 제안대로 진행, 문구는 수정 가능 |
| A3 | 대시보드 "최근 신호" 카드(`get_latest_any_signal`)에 거절 행을 보일지 | ⛔ 표시와 함께 보이기(가시화가 목적이므로) |
| A4 | WO-7 배지 표시 조건을 `qty > 0`에서 `(qty + locked_qty) > 0`으로 넓힐지 | 넓히기 |
| A5 | 자산 현황의 평가액과 손익 칸에 묶인 수량을 포함할지 | 이번에는 제외하고, 배지 문구에 묶인 수량만 보이기. 평가액 변경은 ROI 기준선에 영향을 주므로 별도 WO에서 다루기 |
| A6 | 과거 HTS_BUY/HTS_BUY_ADD 오기록 규모 측정(읽기 전용) | 착수 전에 실행해 (c)의 효과 규모를 수치로 남기기 |
| A7 | 시장가 매수 실패 기록의 type을 `BUY`에서 `BUY_REJECTED`로 바꾸는 것 (과거 4건은 그대로) | 진행 |
| A8 | 배포 시점 | 로컬 검증 완료 보고 뒤 별도 승인 |

## 9. 작업 순서

1. 이 계획서 승인 (A1~A8 결정)
2. 로컬 구현 → 재현 테스트 → 회귀 게이트
3. 완료 보고, 승인 대기
4. `pages/dashboard.py` 버전 갱신(`v1.2026.09.18.1600 → v1.YYYY.MM.DD.HHMM`) 포함 단일 커밋
5. 배포 승인 → `deploy-tradebot` → 30분 관측 → 보고 (버전 "구 → 신" 표기)
6. 자연 발생 관측((c), (a)·(e))은 발생 시 추가 보고

## 10. 승인 결과와 구현 결과 (2026-09-30)

### 10.1 승인 결과

| 번호 | 결정 |
|---|---|
| A1 | 승인 |
| A2 | 승인. insufficient_funds_ask 문구에 "업비트 앱에서 직접 넣은 미체결 매도 주문이 있는지 확인하세요"를 반드시 넣습니다. 이후 WO-11 용어 통일로 최종 문구는 "주문 가능 수량 부족 — 업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요."입니다. |
| A3 | 승인 (⛔ 표시) |
| A4 | 승인 (가용+묶임 합계) |
| A5 | 이번에는 제외합니다. 대신 (b) 배지에 "묶임 N개"를 함께 적습니다. |
| A6 | 읽기 전용 측정 완료 (부록 A) |
| A7 | 승인 (과거 4건 유지) |
| A8 | 배포는 로컬 검증 보고 뒤 별도 지시 |

### 10.2 커밋 (로컬, push 전)

| 커밋 | 범위 | 버전 |
|---|---|---|
| `4347e7f` fix(wo9c) | (c) 감지 기준 정정 단독 | v1.2026.09.18.1600 → v1.2026.09.30.1526 |
| `f288832` feat(wo9) | (e) → (b) → (a) → (d) → A7 | v1.2026.09.30.1526 → v1.2026.09.30.1536 |

두 커밋이 함께 고친 파일은 `engine/order_reconciler.py`, `pages/dashboard.py`, `services/db.py` 세 개입니다. 각 커밋은 따로 되돌릴 수 있습니다. `f288832`만 되돌리면 (c) 테스트 6건이 통과합니다. `4347e7f`만 되돌리면 `pages/dashboard.py` 버전 줄 한 곳만 충돌하고, 나머지 테스트 11건이 통과합니다.

### 10.3 계획과 달라진 점

- `core/position_state.py`의 `locked_qty` 필드는 만들지 않았습니다. 이 값을 읽는 곳이 없어 쓰이지 않는 코드가 되기 때문입니다. 묶인 수량은 이미 DB(`account_positions.virtual_coin_locked`)에 있고, 대시보드와 알림은 DB 값을 읽습니다.
- (b)의 WARNING 대상은 "봇 엔진이 감시 중인 종목"(HTS 감지 콜백이 등록된 종목)으로 한정했습니다. 봇 자신의 매도 주문이 체결을 기다리는 동안 생기는 묶임은 제외합니다.
- `fetch_trades_audit`와 `fetch_latest_trade_audit`는 새 열이 아직 없는 DB에서도 동작하도록 예전 조회로 돌아가는 경로를 두었습니다.
- `pages/audit_viewer.py`의 delta 계산을 숫자 변환 뒤에 하도록 바꿨습니다. 거절 행만 걸러 보면 macd/signal 이 모두 비어 계산 오류가 날 수 있었기 때문입니다.

### 10.4 검증 결과

- `python3 -m py_compile` 변경 파일 전부 통과
- `bash scripts/regression_gate.sh`: UI import 게이트 통과, 회귀 테스트 178/178 통과 (기존 161 + (c) 6 + 나머지 11)
- 구 코드 대상 실행: (c) 테스트 3건 실패, 나머지 테스트 7건 실패 → 테스트가 결함을 실제로 잡는 것을 확인
- 감사 로그 페이지는 Streamlit AppTest 로 실제 렌더해 확인했습니다 (⛔ 경고, "거절 사유" 열의 한글 설명, "거절"/"매수" 필터).
- `tests/test_sell_filter_execution.py`, `tests/test_tp_sl_integration.py`는 pytest 형식인데 로컬에 pytest 가 없어 실행하지 못했습니다.
- 검증 중 사고 1건: 로컬 테스트 환경은 `config`가 `.env`를 읽어 텔레그램 자격증명이 살아 있습니다. (c) 테스트가 (b)의 WARNING 경로를 지나면서, 두 번의 실행(회귀 게이트 177건 실행, 16건 실행)에서 실제 텔레그램 WARNING("⛔ 매도 불가 — KRW-JTO …")이 발송됐을 가능성이 있습니다. 두 테스트 파일에 발송 차단 patch 를 넣었고, 전체 회귀 스위트 실행에서 실제 발송 호출이 0건임을 확인했습니다.

## 부록 A. A6 측정 — 과거 HTS 감지 624건 분류 (읽기 전용)

**결론: 실피해 없음.** 묶임 해제 오기록 22건 가운데 Trailing 리셋 경로(HTS_BUY_ADD)에 해당하는 것은 2건입니다. 두 건 모두 리셋 코드가 들어오기 전에 일어났고, 봇이 감시하던 종목도 아니었습니다.

### A.1 자료 범위

| 자료 | 범위 | 영향 |
|---|---|---|
| position_history | 2026-05-24 21:00 ~ 2026-09-30 (약 915만 행) | 624건 전부 포함 |
| journal | 2026-08-30 18:28 이후 | 그 이전 리셋 여부는 로그로 확인 불가, 코드 도입 시점으로 판단 |
| 업비트 체결·취소 주문 (GET `/v1/orders/closed`) | 2026-05-20 ~ 2026-09-30, 1,782건 | 전체 기간 대조 |

`position_history`에는 묶임 열이 없습니다. 그래서 가용 수량의 변화 시점을 뽑은 뒤, 증가량이 "취소된 외부 매도 지정가 주문의 남은 수량"과 정확히 같은지(상대 오차 1e-6)로 판정했습니다. 같은 증가량이 매수 체결 수량과 맞으면 실제 매수로 판정했습니다.

### A.2 분류 결과

| reason | 묶임 해제 오기록 | 실제 매수 (정확 일치) | 실제 매수 (부분 체결 배분) | 판정 불가 | 합계 |
|---|---|---|---|---|---|
| HTS_BUY | 20 | 224 | 40 | 0 | 284 |
| HTS_BUY_ADD | 2 | 267 | 71 | 0 | 340 |
| 합계 | **22 (3.5%)** | 491 (78.7%) | 111 (17.8%) | 0 | 624 |

- 오기록 22건은 모두 업비트의 취소된 외부 매도 주문과 수량이 정확히 맞았습니다. 봇이 낸 주문은 없었습니다.
- 오기록 id: 78, 79, 88, 210, 264, 284, 286, 381\*, 433, 486\*, 499, 524, 584, 788, 928, 1128, 1143, 1144, 1147, 1148, 1154, 1158 (\*는 HTS_BUY_ADD)
- 1158은 이번 KRW-JTO 사례(uuid 72bc7993)와 일치합니다.

### A.3 Trailing 리셋과 실피해

| id | 종목 | 시각 | 리셋 여부 | 실피해 |
|---|---|---|---|---|
| 381 | KRW-IRYS | 2026-06-30 15:37 | 없음 — 리셋 분기 도입(e182230, 2026-07-27 21:16) 전이고 감시 종목도 아님 | 없음 |
| 486 | KRW-SOL | 2026-07-11 21:44 | 없음 — 같은 이유 | 없음 |

- journal 보존 기간 안의 `Trailing 상태 리셋` 로그 28건은 모두 KRW-JTO이고, 모두 실제 매수와 짝지어집니다.
- HTS_BUY(이전 수량 0) 오기록 20건은 리셋 분기를 타지 않습니다. 다만 `hts_buy` 표시를 켭니다. 현재 매도 필터는 이 표시를 판정에 쓰지 않습니다(Policy P-3).

### A.4 측정 중 발견한 별도 사항 (이번 WO 범위 밖, 기록만)

1. 봇 자신의 지정가 매수가 HTS 매수로 기록된 경우가 있습니다(id 212, 225, 259, 396, KRW-JTO). 체결이 30초 넘게 걸려 "최근 봇 매수" 제외 검사(`has_recent_bot_buy_for_ticker`, 30초)를 통과하지 못한 것으로 보입니다.
2. 아주 작은 증가(Δ = 9e-8)가 HTS_BUY_ADD로 잡혀 실제 Trailing 리셋이 일어난 경우가 1건 있습니다(id 990, KRW-JTO, 2026-09-11 14:38). 묶임 해제는 아니고, 증가 원인은 확인하지 못했습니다. 감지 임계값이 1e-8이라 소수점 잔량 변화도 매수로 잡힙니다. 이 리셋의 피해는 평가하지 않았습니다.
3. 부분 체결 배분 111건은 판정 근거가 상대적으로 약합니다. 업비트 목록은 주문별 총 체결량만 주기 때문입니다.

원자료: `a6/a6_rows.csv` (624행, 열: id, timestamp, ticker, reason, prev_qty, new_qty, class, evidence, cancel_order_uuid_if_found, buy_order_uuid, buy_order_is_bot, match_type, reset_logged, next_sell_id, harm_judgement)

