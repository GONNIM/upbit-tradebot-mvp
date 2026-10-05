# 사건 기록 — 2026-10-05 10:59 앱 재매수분 봇 손절 매도 (KRW-JTO)

- 작성: 2026-10-05 (KST)
- 판정 (Fable): WO-21 과 무관한 기존 경로의 결함 → WO-22 로 분리. 봇 계속 운영. 투자자 안내는 WO-22 배포 뒤.
- 로그 출처: `journalctl -u tradebot`. 조회는 모두 읽기 전용(서버 DB `mode=ro`, Upbit `GET` 만).

## 1. 시간표

| 시각 (KST) | 사건 | 근거 |
|---|---|---|
| 08:26:52 | 봇 매수 orders **id 564**: 1,739.90482236개 @777 (EMA_GC, 현재가 매수) | `evidence/db-orders-564-565-audit-1201.txt`, audit_trades 1198 |
| 09:39:27 | 투자자 앱 지정가 매도 @779 전량 → 취소 | `evidence/upbit-closed-orders-0930-1110.txt` |
| 09:39:53 | 투자자 앱 지정가 매도 @778 전량 1,739.90482236개 → 체결 (₩1,353,645.95) | 같음 |
| 09:40:45 | `⛔ [LOCKED-QTY] 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 \| 가용=0 묶임=1739.904822` | `evidence/journal-0826-0945-jto.txt` |
| 09:42:11 | `[POSITION-SYNC] 강제 포지션 종료 실행: 지갑 잔고=0 … qty=1739.904822` → `Position CLOSE`. **orders·audit_trades 에 매도 기록 없음** | 같음 |
| 10:54:59 | WO-21 배포 재시작 (JTO 0, 포지션 없음) | WO-21 배포 보고 |
| **10:58:26** | **투자자 앱 지정가 매수 @766, 13.05483028개 (₩9,999.99) → 체결** | Upbit closed |
| 10:58:08 · 10:59:09 | OR 1분 주기 잔고 동기화 (외부 매수 감지 포함) — 앱 매수는 두 실행 사이 | `evidence/journal-1054-1100.txt` |
| 10:59:05 | 엔진 매 봉 `[POSITION-SYNC] … 외부 매수 감지: 지갑 잔고=13.054830` → 진입가 1순위 `account_positions.entry_price`(캐시, 직전 동기화 때 0) 없음 → 2순위 `get_last_open_buy_order` = **orders 564 @777** (`[DB] last BUY … {'price': 777.0, 'entry_bar': 951, …}`) → `자동 복구 성공 (source=last_open_buy) … entry_price=777.00` | `evidence/journal-1055-1059-key.txt` |
| 10:59:05 | 첫 매도 평가 종가 766: `STOP_LOSS_CHECK … pnl_pct=-1.42%, threshold=-1.00%, hts_buy=False` → `Sell triggered by StopLossFilter` | 같음 |
| 10:59:06 | 시장가 매도 **orders id 565** 13.05483028개 → 체결 평균 765 (₩9,986.95), audit_trades **1201** SELL STOP_LOSS | 같음, Upbit closed |

## 2. 영향 금액

| 항목 | 값 |
|---|---|
| 앱 매수 (10:58:26) | 13.05483028개 × 766 = ₩9,999.99 (수수료 약 ₩5.00 별도) |
| 봇 매도 (10:59:06) | 13.05483028개 × 765 = ₩9,986.95 (수수료 약 ₩4.99) |
| 차액 | 가격 −₩13.05, 수수료 포함 약 **−₩23** |
| 올바른 진입가였다면 | 진입가 766 기준 pnl −0.13% → 손절 기준 1% 미달 → 매도 없음 (투자자 보유 유지) |

금액은 작으나, 투자자가 앱에서 산 지 39초 만에 봇이 잘못된 진입가로 판단해 팔았다.

## 3. WO-21 과 무관한 근거

1. 이 경로는 매 봉 지갑 동기화 `StrategyEngine._reconcile_position_with_wallet` (Case 2 외부 매수 복원)이다. WO-21 재계산(`core/trailing_restore.py`)은 기동 시 1회만 실행되며 이번 기동에서 `[TRAILING-RESTORE]` 0건이었다(포지션 없음).
2. 잘못된 진입가 777 은 `get_last_open_buy_order` 의 orders 마지막 봇 BUY 이다. 청산 검사(B1)는 orders 의 봇 SELL 만 보아 앱 매도(09:39:53)를 몰랐다. 이 함수의 정렬·시각 열은 WO-20 에서 바뀌었으나 이번 선택(564)은 구 정렬로도 같다(id 564 가 유일한 마지막 BUY).
3. 매도를 낸 것은 `StopLossFilter`(손절 1%)이며 trailing 필터·재계산과 관계없다.
4. 같은 조합(봇 매수 → 앱 전량 매도 → 다음 1분 동기화 전 앱 재매수)은 WO-21 전부터 가능했다. 최근 30일 지갑 동기화 복원 26건 중 orders 를 진입가로 쓴 것은 이번 1건뿐 (WO-22 조사 A3).

## 4. 처방

WO-22 (`plan.md`): 진입가 우선순위를 Upbit avg_buy_price 직접 → account_positions → orders(수량 일치 시만)로 바꾸고, 지갑 0 닫힘을 audit_trades `HTS_SELL`(외부 매도)로 기록해 옛 봇 BUY 차용을 막는다.

## 5. 증거 파일 (`evidence/`)

| 파일 | 내용 |
|---|---|
| `journal-1054-1100.txt` | 10:54 ~ 11:00 journal (다른 종목 sync 줄 제외) |
| `journal-1055-1059-key.txt` | 10:55 ~ 10:59 핵심 줄 (외부 매수 감지 · last BUY 777 · STOP_LOSS · 매도) |
| `journal-0826-0945-jto.txt` | 08:26 매수 뒤 매도 평가, 09:40 LOCKED-QTY, 09:42 지갑 0 닫힘 |
| `upbit-closed-orders-0930-1110.txt` | Upbit `GET /v1/orders/closed` (KRW-JTO 09:30 ~ 11:10, done·cancel) + orders 564·565 |
| `db-orders-564-565-audit-1201.txt` | orders 564·565, audit_trades 1198·1201 |
| `a3-30days.txt` | 최근 30일 지갑 0 닫힘·외부 매수 복원 사건 목록 |
| `wo21d_closed.py`, `wo22_a3.py` | 조회 스크립트 (읽기 전용) |
