# WO-22 핫픽스 — 지갑 동기화 복원 진입가 우선순위 + 외부 매도 기록

- 작성: 2026-10-05 (KST)
- 계기: `incident.md` (10-05 10:59 앱 재매수분 봇 손절 매도)
- 범위: 조사·구현·로컬 검증, 푸시까지. 서버 pull·재시작은 별도 지시. 투자자 안내는 배포 뒤.

## 1. 가설과 조사 결과

가설: "`_reconcile_position_with_wallet` 이 진입가를 정할 때 Upbit avg_buy_price 보다 orders 의 마지막 봇 BUY 를 먼저 쓴다. 그리고 '뒤에 매도가 있는지' 검사가 orders 의 봇 SELL 만 보므로 앱 매도를 모른다."

| 항목 | 결과 |
|---|---|
| A1 진입가 순서 (구 코드 `core/strategy_engine.py` `_reconcile_position_with_wallet` Case 2) | **가설 앞부분 정정.** 순서는 이미 1) `account_positions.entry_price`(주석상 "Upbit avg_buy_price 캐시") → 2) orders 마지막 봇 BUY 였다. 그러나 1) 은 OR 가 **1분마다** 채우는 캐시라 직전 앱 매수는 아직 0 이다(10:58:08 동기화 뒤 10:58:26 매수, 다음 동기화 10:59:09). 이 함수는 Upbit `avg_buy_price` 를 **직접 읽지 않는다** (직접 조회는 `PositionState.sync_from_wallet` 의 2순위에만 있다). 그래서 10:59:05 에 캐시 0 → orders 564 @777 이 선택됐다 (`[DB] last BUY (with status filter=True) => {'price': 777.0, 'entry_bar': 951, …}` → `source=last_open_buy`) |
| A1 청산 검사 | **가설 뒷부분 확인.** `get_last_open_buy_order` 의 `_last_buy_closed_by_later_sell` 은 orders 의 SELL rowid 만 본다. 앱 매도는 orders 에 없으므로 564 를 미청산으로 판정 |
| A2 지갑 0 닫힘 경로 | 같은 함수 Case 1: `self.position.close_position(ts=None, reason="position_sync_wallet_zero")` 뿐. orders·audit_trades 기록 없음 (09:42:11 사건 뒤 orders 마지막 BUY 564 · audit_trades 마지막 JTO 1198 BUY 그대로 — `evidence/db-orders-564-565-audit-1201.txt`) |
| A3 30일 조합 | 아래 표. 지갑 0 닫힘 3건, 그 뒤 첫 외부 매수 복원이 orders 를 쓴 것은 10-05 1건뿐 |

### A3. 최근 30일 지갑 0 닫힘과 그 뒤 첫 복원 (journal 2026-09-07 ~ 10-05, `evidence/a3-30days.txt`)

| 지갑 0 닫힘 (Case 1) | 닫힌 포지션 | 다음 외부 매수 복원 (Case 2) | 진입가 (출처) | 판정 |
|---|---|---|---|---|
| 09-09 15:50:10 · 4,296.280196개 | 앱 매수분(HTS) | 09-09 16:15:08 · 428.512780개 | 626.00 (upbit_avg_buy_price 캐시) | 정상 |
| 09-30 21:50:11 · 1,340.436268개 | 앱 매수분(HTS, 09-30 클레임 포지션) | 09-30 23:25:06 · 307.667517개 | 745.00 (캐시) | 정상 |
| **10-05 09:42:11 · 1,739.904822개** | **봇 매수분 (orders 564 @777)** | **10-05 10:59:05 · 13.054830개** | **777.00 (last_open_buy = orders 564)** | **결함 (실제 766)** |

같은 기간 외부 매수 복원 전체 26건: 캐시 25건, orders 1건(10-05). 진입가 없음으로 복원 보류 3건(09-09 10:40, 09-14 07:45, 10-02 12:15 — 캐시·미청산 BUY 모두 없음, 다음 OR 동기화에서 HTS 감지로 처리).

## 2. 처방 (구현 `dfc075f`)

1. **진입가 우선순위** (`_reconcile_position_with_wallet` Case 2):
   1) Upbit `avg_buy_price` 직접 조회 (`_fetch_upbit_avg_buy_price`, LIVE 만)
   2) `account_positions.entry_price`
   3) orders 마지막 봇 BUY — **그 BUY 의 체결 수량이 지갑 수량과 같을 때만** (다르면 WARNING `orders 마지막 봇 BUY 수량 불일치 → 진입가로 쓰지 않음` 후 기존 "신뢰 가능한 진입가 없음" 경로)
   - 로그: `[POSITION-SYNC] entry_price=… (출처: upbit_avg|account_positions|orders)`. 반환 출처 이름도 같은 값 (`[BOOT-SEED] source=` 로그에 반영).
2. **외부 매도 기록** (Case 1): `close_position` 직전 `audit_trades` 에 `type='HTS_SELL'`, `reason='HTS_SELL'`, `qty`=닫힌 수량, `entry_price`=직전 진입가, `price`=비움, `note`="외부 매도 — 지갑 잔고 0 감지 (앱 매도 등). 체결 가격은 알 수 없음".
   - `type` 을 `'SELL'` 이 아닌 `'HTS_SELL'` 로 둔 이유: 대시보드 "최근 거래(실현)"·설정 이력 손익은 `type='SELL'` 행의 가격으로 계산한다. 가격 없는 행이 섞이지 않게 `*_REJECTED` 유형과 같은 방식으로 분리했다.
   - `get_last_open_buy_order`: 선택된 BUY 의 체결 시각 뒤에 `HTS_SELL` 이 있으면 청산(None). `get_last_open_buy_trade`(WO-21 시작점): `type IN ('SELL','HTS_SELL')` 을 청산으로.
   - 감사 로그 페이지: 유형 표시 "외부 매도" (`trade_type_display`), 유형 필터 "매도" 에 포함 (`trade_kind`). `docs/operations/terminology.md` 에 대응 추가.
3. 매수·매도 판정식, 필터, 발주, 지표, WO-21 재계산 경로 무변경.

## 3. WO-23 으로 넘기는 항목

| 항목 | 내용 | 근거 |
|---|---|---|
| ② 외부 매수 감지 경합 | 매 봉 지갑 동기화(엔진)가 OR 의 1분 주기 HTS 감지보다 먼저 외부 매수를 잡으면 `hts_buy` 플래그 설정·첫 봉 방어(외부 매수 처리)가 빠진다. 10:59:05 사건에서 `hts_buy=False`. WO-22 로 진입가는 바로잡히지만 "외부 매수" 분류·기록(audit_trades HTS_BUY)은 여전히 OR 가 다음 주기에 잡아야 남는다 (이번 사건은 그 전에 팔려 HTS_BUY 기록 없음) | incident.md 시간표 |
| ③ `locked_warned` 잔존 | 앱 지정가 매도로 묶였다가 **전량 체결**되면(가용 0, 묶임 0) 해제 조건(`avail > 0`)에 닿지 않아 `account_positions.meta.locked_warned=true` 가 남는다 (KRW-JTO 현재 `{"locked_warned": true}`). 다음 묶임 때 경고가 생략될 수 있다 | `engine/order_reconciler.py` LOCKED-QTY 분기, 0단계 조회 |
| (표시) 감사 로그 열 이름 | `note`·`qty` 열 이름이 "거절 사유"·"시도수량" 이라 외부 매도 행의 메모가 "거절 사유" 아래 보인다. UI 변경 규칙(1-A 브라우저 실측) 대상이라 WO-22 에서 바꾸지 않았다 | `pages/audit_viewer.py` 열 이름 매핑 |
| (기존) 지갑 0 의 다른 경로 | 같은 봉 안 `sync_from_wallet` 이 먼저 지갑 0 을 보면 `has_position=False` 만 바뀌고 Case 1(외부 매도 기록)을 거치지 않는다. 호출 순서상 `_reconcile_position_with_wallet` 이 봉 처음에 먼저 돌므로 드묾 | `core/strategy_engine.py` 호출 순서 |
