# WO-24 계획서 — 현재가 매수 미체결 취소 감사 기록 + 미체결 시 시장가 전환 옵션 + 알림 성공 로그

- 작성: 2026-10-05
- 근거: 긴급 조사 `docs/plans/2026-10-05-urgent-buy-not-executed/report.md` 와 Fable 판정. 10-04 14:15 건은 매수 경로 결함이 아니다. 하지만 미체결 취소가 감사 로그에 보이지 않는 것은 결함이다.
- 범위: 로컬 구현만 한다. 배포는 별도 지시로 한다.
- 버전: v1.2026.10.05.1145 → v1.2026.10.05.1526

## 1. 문제

| # | 현상 | 근거 |
|---|---|---|
| 1 | 현재가 매수 주문이 대기 봉 안에 체결되지 않아 자동 취소돼도 `audit_trades` 에 기록이 없다. 감사 로그 페이지에는 "평가 통과(overall_ok=1)" 행만 보이고 매수 행은 없다. | 10-04 14:15 bar 76229 → orders 559 (주문가 763, `state=CANCELED`, `executed_volume=0`). 감사 로그 페이지에서는 원인을 볼 수 없다. |
| 2 | 미체결 뒤에 대안이 없다. 가격이 주문가 근처에 머물러도 매수 기회가 사라진다. | 같은 건: 295초 동안 763 이하 체결 0건, 현재가는 주문가보다 조금 높은 구간이었다. |
| 3 | 알림 발송 성공이 로그에 남지 않는다. "알림이 갔는가" 를 경고 부재로만 추정한다. | project-rules "외부 주문 공존" 절의 금지 사항 (성공 로그 없음). |

## 2. 변경

### A. 미체결 취소 감사 기록

- `engine/order_reconciler.py`
  - `_maybe_cancel_fixed_price_buy`: 취소 요청이 성공하면 pending 항목에 `timeout_cancel` 표식(경과 초, 제한 초)을 단다.
  - `_handle`: BUY 이고 최종 상태가 `CANCELED` 이고 표식이 있으면 `_on_timeout_cancel_final` 을 부른다. 부분 체결 콜백 뒤, pending 제거 전에 부른다.
  - `_on_timeout_cancel_final`: `audit_trades` 에 1행을 넣는다.
    - type `BUY_CANCELED`, price 는 주문가, qty 는 주문 수량
    - note: 사유 "대기 N봉 내 체결 없음" 또는 "…일부만 체결" + 전환 결과
    - meta JSON: uuid, order_qty, executed_qty, remaining_qty, limit_price, wait_bars, waited_sec, timeout_sec, orig_reason, convert
- 현재가 매수 주문 meta 에 `wait_bars` 를 추가한다. 봇 경로는 `core/strategy_engine.py` `_execute_buy`, 강제 매수 경로는 `services/trading_control.py`.
- 표시
  - `services/db.py`: `BUY_CANCELED` 의 표시 이름은 "⏱ 매수 미체결 취소", 유형은 "미체결 취소".
  - `pages/audit_viewer.py`: 유형 필터에 "미체결 취소" 를 추가하고, 이 행은 옅은 노란 배경으로 보인다. 거절 행의 붉은 배경과 구분된다.
- 손익·매수 집계에는 넣지 않는다. 집계는 `type='BUY'/'SELL'` 기준이라 영향이 없다.
- 과거 DB 행은 고치지 않는다. 운영 가이드에 한 줄을 넣는다: "이전 미체결 취소는 orders.state=CANCELED 로 확인".

### B. 미체결 시 시장가 전환 옵션

- 설정 키는 두 개다. `buy.fixed_price_unfilled_to_market` 의 기본값은 `config.UNFILLED_TO_MARKET_DEFAULT = False` 이고, `buy.fixed_price_convert_max_gap_pct` 의 기본값은 0.3 이다.
  - 켬/끔 기본값은 운영자가 결정할 때까지 끔으로 둔다. 결정이 오면 config 한 줄만 바꾼다.
- `core/strategy_engine.convert_unfilled_limit_buy`
  - 옵션이 꺼져 있으면 전환하지 않는다. 사유: "미체결 시 시장가 전환 꺼짐".
  - 현재가가 주문가 × (1 + 허용 %) 이하일 때만 전환한다. 넘으면 취소하고 사유 "가격 차이 x% > 허용 y%" 를 남긴다.
  - 전환은 엔진 실행 락 아래에서 한다.
    - 기존 `trader.buy_market` 으로 남은 수량 × 현재가 만큼 KRW 를 쓴다.
    - `apply_entry(source=bot_market_convert)` 를 부른다. 부분 체결이 있었으면 가중 평균가로 들어간다.
    - pending 상태를 정리한다.
  - 이미 포지션이 있고 체결 수량이 0 이면 건너뛴다.
  - 강제 매수는 전환 대상이 아니다.
- `core/trader.buy_market(krw_amount=None)`: 값을 줄 때만 금액을 제한한다. 기본 동작은 그대로다.
- `pages/set_buy_sell_conditions.py`
  - "현재가 매수 대기 봉 수" 아래에 체크박스와 허용 % 입력, 안내 문구를 추가한다.
  - 안내 문구: "현재가 매수가 대기 봉 안에 체결되지 않으면 시장가로 전환합니다. 현재가가 주문가보다 x% 이상 높으면 전환하지 않고 취소합니다." + 대기 시간(봉 간격 × 대기 봉 수).

### C. 알림 성공 로그

- `services/notifier.py`: HTTP 200 이면 `[NOTIFY] sent | kind=… dedupe=…` 를 INFO 로 1줄 남긴다. 토큰과 채팅 ID 는 남기지 않는다.

## 3. 바꾸지 않는 것

- 매수·매도 판정식, 필터, 대기 봉 계산(timeout = interval × wait_bars − 5초)
- 시장가 매수 경로의 기본 동작
- 과거 DB 행
- 투자자 포지션과 주문

## 4. 시험 (`tests/regressions/test_r_2026_10_05_wo24_unfilled_buy_audit.py`)

| # | 내용 | 구 코드 기대 |
|---|---|---|
| 1 | 미체결 취소 → BUY_CANCELED 1행 (주문가, 주문 수량, 사유 "대기 5봉 내 체결 없음", uuid) | 실패 |
| 2 | 부분 체결 뒤 취소 → BUY_CANCELED 1행, 체결 수량 기록 | 실패 |
| 3 | 옵션 끔 → 전환 없음, 사유 "미체결 시 시장가 전환 꺼짐" | 실패 |
| 4 | 옵션 켬, 가격 차이 ≤ 허용 → 시장가 매수 + apply_entry(bot_market_convert) | 실패 |
| 5 | 옵션 켬, 가격 차이 > 허용 → 전환 안 함, 사유 "가격 차이 x% > 허용 y%" | 실패 |
| 6 | 표시 이름 "⏱ 매수 미체결 취소", 유형 "미체결 취소" | 실패 |
| 7 | 알림 성공 → `[NOTIFY] sent` 로그, 토큰과 채팅 ID 없음 | 실패 |

시험은 네트워크를 쓰지 않는다. 가격 조회는 시험용 함수로 바꾸고, 바뀌지 않은 조회가 불리면 예외를 낸다.

## 5. 검증과 되돌림

- `bash scripts/regression_gate.sh`: 임시 worktree 에서 더미 env 로 전체 통과해야 한다.
- 단독 되돌림: `git revert <코드 커밋>` 이 충돌 없이 되고, 되돌린 뒤 게이트가 통과해야 한다.
- UI 변경 브리핑(1-A): 추가만 있다. 삭제, 이동, 접힘은 없다. 배포 뒤 브라우저에서 확인한다.

## 6. 배포 관찰 항목 (배포 지시 때 사용)

- 부팅 줄과 결함 태그 0
- BUY_CANCELED 행: 미체결 취소가 생기면 1건당 1행인지, 사유 문구, 감사 로그 페이지 노출
- `[NOTIFY] sent` 줄: 알림이 생기면 확인한다. 토큰과 채팅 ID 문자열은 없어야 한다.
- **상설**: BUY/SELL 평가 통과 행 대 실제 체결 1:1 대조 (통과·체결·취소·미요청 수)
- 옵션 기본 끔: `[UNFILLED-CONVERT]` 줄은 0 이어야 한다. 운영자가 켜기 전까지 유지된다.

## 7. 운영자 결정 대기

- 시장가 전환의 기본 켬/끔 (현재 끔)
- 허용 가격 차이 기본값 (현재 0.3%)
