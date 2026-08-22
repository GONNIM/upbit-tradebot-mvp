# KRW-JTO Golden Cross 미매수 클레임 진단 리포트 (JTO-Claim-20260821-001)

**날짜**: 2026-08-21
**작성자**: Claude Code (Opus 4.7 · 1M context)
**대상 사건**: 2026-08-20 04:29~04:39 KST, KRW-JTO, 1분봉, EMA 전략
**심각도**: 🔴 CRITICAL (감사 결함 + 매매 판정 미확정 데이터 사용)
**소요 시간**: 약 2시간 (진단 · 검증 · 보고서)

---

## 🎯 핵심 요약 (2줄)

> **매수는 04:34:11에 정상 발화되어 LIMIT 지정가 777원으로 주문 접수됐고(uuid ab1f0804…), 시장가가 779~783으로 상승해 5분 내 미체결로 04:39:16 자동 취소됐다.**
> **사용자가 audit 화면에서 "매수 안 됨"으로 보게 된 진짜 원인은 04:35:31 BACKFILL 재평가가 실시간 매수 시도 audit를 UPDATE로 덮어써 소거한 감사 시스템 결함이며, 추가로 fetch_confirmed_candle 이 미확정 종가(777)를 "확정"으로 오판해 매수 판정을 유발한 Issue #8 부분 회귀도 확인됐다.**

## 📢 사용자 회신 문안 (기술 용어 최소화)

> 04:34분 봉에서 봇이 Golden Cross를 정확히 감지하고 매수 주문을 낸 것은 사실입니다(주문번호 ab1f0804…, 지정가 777원, 수량 3,404 JTO). 하지만 이 시점 이후 JTO 가격이 779원→782원까지 계속 오르면서 5분 대기 시간 안에 777원에 팔려는 매도벽이 없었고, 결국 04:39:16에 주문이 자동 취소됐습니다. 매수 자체가 "안 된 것"이 아니라 "체결되지 못하고 취소된 것"입니다.
>
> 그런데 감사 화면(audit_viewer)에서 이 매수 시도 흔적이 보이지 않는 이유는 별개의 결함입니다. 봉 확정이 늦게 되는 종목의 특성상 BACKFILL(뒤늦은 재평가)이 같은 봉의 감사 기록을 덮어쓰도록 되어 있는데, 이 로직이 실시간 매수 시도의 기록마저 지웠습니다. 이 부분은 즉시 수정하겠습니다. 또한 매수 판정의 근거가 된 04:34 봉의 종가 777원은 실제 최종 확정 종가 779원과 다른 "미확정 값"이었음이 확인됐고, 이번엔 방향이 같아 무해했지만 반대 방향에서는 가짜 매수가 발생할 수 있는 구조적 리스크입니다. 지정가 777원이 시장가를 못 따라잡는 문제는 종목/파라미터 판단이라 별도 안내 드리겠습니다.

---

## 📋 목차

1. [사건 개요 및 사용자 클레임](#1-사건-개요-및-사용자-클레임)
2. [확정 사실 (레코드/로그 인용)](#2-확정-사실-레코드로그-인용)
3. [타임라인 (초 단위)](#3-타임라인-초-단위)
4. [가설 판정 요약](#4-가설-판정-요약)
5. [근본 원인 4중 + F6 관찰](#5-근본-원인-4중)
6. [수정 제안](#6-수정-제안)
7. [검증 계획 (4경로 체크리스트)](#7-검증-계획-4경로-체크리스트)
8. [교훈](#8-교훈)
9. [문서 정합성](#9-문서-정합성)

---

## 1. 사건 개요 및 사용자 클레임

**사용자 클레임 (audit 스크린샷 근거)**:
- 04:34 봉에서 EMA Golden Cross 전환이 발생했으나 BUY 없음
- BACKFILL 마킹이 7봉 중 3봉(43%) — 과다
- 04:30/04:32/04:35 봉 audit 부재

**클레임의 전제**: audit_buy_eval 화면이 실시간 판정 결과를 반영한다.

**진단 결과 반전**: 클레임의 두 전제 모두 부분적으로 사실과 다르다.
1. **매수는 정상 발화**됐고, 클레임의 "매수 안 됨"은 미체결로 인한 취소를 audit 결함이 은폐한 것.
2. **audit 화면의 상태는 최종 UPDATE 결과**이며 실시간 시도 흔적을 보존하지 않는다.

---

## 2. 확정 사실 (레코드/로그 인용)

### 2.1 04:34:11 실시간 매수 발화 (journalctl 인용, 인용 원문)

```
Aug 20 04:34:10  [RECONCILE] 확정 종가 ✅ | ts=2026-08-20 04:34:00 KST | close=777 | high=777 | low=777 | volume=301.53
Aug 20 04:34:10  [REST] 최신 확정 봉 ✅ | ts=2026-08-20 04:34:00 KST | close=777
Aug 20 04:34:10  🔄 [REST-RECONCILE] 1개 봉 변경 감지 → 부분 재계산
Aug 20 04:34:11  📊 Bar#3096 | ts=2026-08-19 19:34:00+00:00 | close=777.00 | ema_fast=773.26 | ema_slow=773.20 | ema_base=773.20 | action=BUY | pos=False
Aug 20 04:34:11  🎯 [FIXED-PRICE] 고정가 매수 모드 진입 | close=777.0 ticker=KRW-JTO wait_bars=5 effective_timeout≈295s
Aug 20 04:34:11  [BUY-LIMIT] plan close=777.0 rounded=777.0 krw_to_use=2646633 qty=3404.51781831
Aug 20 04:34:12  [UPBIT-ORDER] ← status=201 body={'uuid': 'ab1f0804-c07f-4487-9509-c482086bddee', 'side': 'bid', 'ord_type': 'limit', 'price': '777', 'state': 'wait', ..., 'volume': '3404.51781831', 'executed_volume': '0', 'trades_count': 0}
Aug 20 04:34:12  [BUY-LIMIT] ok=True status=201 error_name=None
Aug 20 04:34:13  🎯 LIMIT BUY 등록(체결 대기) | price=777.0000 uuid=ab1f0804... bar=3096 wait_bars=5
Aug 20 04:34:13  ✅ [CONFIRMED] 봉 처리 완료 | ts=2026-08-20 04:34:00 KST | close=777.0
```

**확정**: 봇은 04:34 봉의 Dead→Golden 전환을 정확히 감지하고 BUY action을 발화, Upbit에 LIMIT 매수 주문 접수(status=201)까지 정상 실행.

### 2.2 04:39:12 주문 timeout → 취소

```
Aug 20 04:39:12  ⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도 | uuid=ab1f0804... elapsed=299.1s timeout=295s ticker=KRW-JTO
Aug 20 04:39:12  [OR] cancel_order resp uuid=ab1f0804...: {'state': 'wait', ..., 'executed_volume': '0', 'trades_count': 0}
Aug 20 04:39:16  [OR] final CANCELED uuid=ab1f0804... user=mcmax33 side=BUY vol=0.0 avg=0.0 fee=0.0 krw=2647956.80865583 coin=None
Aug 20 04:40:31  🎯 LIMIT BUY pending 자동 해제 | uuid=ab1f0804... start_bar=3096 now_bar=3101 wait_bars=5
```

**orders 테이블 최종 상태** (SQLite 인용):

```
id   timestamp                         ticker   side  price  volume  status     state     executed_volume  canceled_at  updated_at
402  2026-08-20T04:34:12.447517+09:00  KRW-JTO  BUY   777.0  0.0     requested  CANCELED  0.0                           2026-08-20T04:39:16.143490+09:00
```

**확정**: 5분(295초) 대기 시간 만료로 자동 취소. executed_volume=0 (완전 미체결).

### 2.3 04:35:31 BACKFILL의 audit UPDATE (audit_buy_eval id 58080)

```
id     timestamp                         bar_time                    price  overall_ok  failed_keys      notes
58080  2026-08-20T04:35:31.251737+09:00  2026-08-20T04:34:00+09:00   779.0  0           ["NO_SIGNAL"]    Golden | NO_SIGNAL | bar=3096
```

**checks 컬럼** (JSON):
```
{"reason": "NO_BUY_SIGNAL", "ema_fast": 773.80..., "ema_slow": 773.26..., "price": 779.0,
 "via_backfill": 1, "cross_status": "Golden"}
```

**확정**: audit_buy_eval 04:34 봉 레코드는 04:35:31 BACKFILL이 close 777→779, via_backfill 0→1, overall_ok 1→0으로 UPDATE(services/db.py:1030-1045)했다. **04:34:11 실시간 BUY 시도의 audit 흔적은 완전히 소거됐다.**

### 2.4 24시간 KRW-JTO 통계

- audit_buy_eval 총 714건 중 최종 BACKFILL UPDATE 상태 **258건 (36.1%)**
- 실시간 BUY action 발화 총 3건 (04:34, 14:07, 17:31) 중 **1건 (04:34)이 BACKFILL로 소거됨** (**표본 소규모, 비율 일반화 불가**)
- `[RECONCILE] 봉 미반영` 로그 5,476건, `[RECONCILE] 확정 종가 ✅` 505건 (전체 서비스 기준)

### 2.5 30일 LIMIT BUY 체결률 (orders 테이블)

| 티커 | 총 시도 | FILLED | CANCELED | 체결률 |
|---|---|---|---|---|
| KRW-JTO | 46 | 25 | 21 | **54.3%** |
| KRW-RE | 19 | 18 | 1 | **94.7%** |
| 전체 | 65 | 43 | 22 | 66.2% |

취소 21건 중 완전 미체결(executed_volume=0) 7건, 부분 체결 후 취소 14건.

---

## 3. 타임라인 (초 단위)

### 3.1 사건 구간 (04:28~04:41)

| 시각 | 이벤트 | 결과 |
|---|---|---|
| 04:28:00 | CLOCK-CLOSE 04:28 → CONFIRMED close=774 | 정상 |
| 04:29:00 | CLOCK-CLOSE 04:29 → CONFIRMED close=775 | 정상 |
| **04:30:00** | CLOCK-CLOSE 04:30 감지 | 진행 |
| 04:30:30 | fetch_confirmed_candle 5회 재시도 초과 → `❌ [CONFIRMED] closed_ts=04:30 조회 실패` | 봉 skip |
| **04:31:00** | CLOCK-CLOSE 04:31 감지 | 진행 |
| 04:31:16 | 정상 CONFIRMED close=775 (bar 3094 첫 처리) | 정상 |
| **04:32:00** | CLOCK-CLOSE 04:32 감지 | 진행 |
| 04:32:31 | fetch 실패 → BACKFILL로 04:31 재평가 close=**778** (실시간 775와 다름) | via_backfill=1 |
| **04:33:00** | CLOCK-CLOSE 04:33 감지 | 진행 |
| 04:33:30 | fetch 실패 → Progressive Retry | 대기 |
| 04:33:36 | Retry 성공 → CONFIRMED 04:33 close=778 (bar 3095 실시간) | 정상 |
| **04:34:00** | CLOCK-CLOSE 04:34 감지 | 진행 |
| 04:34:10 | fetch_confirmed_candle 성공 → **close=777 "확정"으로 반환** | ⚠️ 미확정 값을 확정 판정 |
| 04:34:11 | **📊 Bar#3096 close=777 → ema_fast=773.26 > ema_slow=773.20 → action=BUY** | **매수 발화** |
| 04:34:11 | 🎯 FIXED-PRICE 진입, wait_bars=5, timeout≈295s | LIMIT 준비 |
| 04:34:12 | Upbit LIMIT 주문 접수 성공 (status=201, uuid=ab1f0804…) | **주문 접수** |
| 04:34:13 | CONFIRMED 완료 | 정상 |
| 04:34~04:39 | REQUESTED 상태로 300+ progress 이벤트, executed_volume=0 유지 | 미체결 |
| **04:35:00** | CLOCK-CLOSE 04:35 감지 | 진행 |
| 04:35:30 | fetch 실패 → BACKFILL 04:34 재평가 close=**779** (실시간 777과 다름) | 04:34 audit UPDATE (via_backfill=1, overall_ok=0, NO_SIGNAL) — **실시간 BUY 흔적 소거** |
| **04:36:00** | CLOCK-CLOSE 04:36 → 정상 CONFIRMED close=779 | 이미 Golden 유지 상태 → not detected (정상) |
| 04:37:00 | 정상 CONFIRMED close=782 | ← 시장가 계속 상승 |
| 04:38:00 | 정상 CONFIRMED close=780 | 지정가 777로는 매수 불가 |
| **04:39:12** | LIMIT BUY timeout 도달 (elapsed=299.1s > 295s) → cancel 요청 | **취소** |
| 04:39:16 | final CANCELED (executed_volume=0) | 최종 |
| 04:40:31 | LIMIT BUY pending 자동 해제 (bar 3101) | 정리 |

### 3.2 시각별 최종 audit 상태 vs 실시간 발생 순서 요약

| bar | 최종 audit | 실시간 첫 처리 시각 | BACKFILL 재평가 시각 | 결과 |
|---|---|---|---|---|
| 3094 (04:31) | 04:32:31 BACKFILL close=778 (via_bf=1, Dead) | 04:31:16 close=775 | 04:32:31 close=778 | 실시간 audit UPDATE로 소거 |
| 3095 (04:33) | 04:33:35 실시간 close=778 (via_bf=0, Dead) | 04:33:36 Progressive Retry | 없음 | 실시간 유지 |
| **3096 (04:34)** | **04:35:31 BACKFILL close=779 (via_bf=1, Golden, NO_SIGNAL)** | **04:34:11 close=777, action=BUY, LIMIT 접수** | **04:35:31 close=779** | **실시간 BUY 흔적 소거** |
| 3097 (04:36) | 04:36:26 실시간 close=779 (via_bf=0, Golden) | 04:36:26 | 없음 | 실시간 유지 |
| 3098 (04:37) | 04:38:31 BACKFILL close=782 (via_bf=1, Golden) | 04:37:26 close=781 | 04:38:31 close=782 | 실시간 audit UPDATE로 소거 |

---

## 4. 가설 판정 요약

| 가설 | 판정 | 근거 |
|---|---|---|
| H1 (04:36 실시간 크로스 감지 실패) | **기각** | 04:34:11 정상 감지·BUY 발화. 04:36은 이미 Golden 상태 유지 중이라 신규 전환 이벤트 없음(정상) |
| H2 (Issue #11 백업/복원 회귀) | **기각** | 매수 시그널 정상 발화. F2 동일값 쌍은 백업/복원 정상 동작의 자연 결과 (a) 시나리오 (지시 1 항목 4 반증) |
| H3 (매수 게이트 차단) | **기각** | LIMIT 주문 status=201 성공, 미체결로 자동 취소 (orders id 402 state=CANCELED) |
| H4a (bar_time off-by-one) | **기각** | 3095는 04:33:35 실시간 INSERT (라인 1266 Retry 경로), (b) 시나리오 반증 완료 |
| H4b (실시간 확정 봉 수신 반복 실패) | **채택** | Upbit REST 지연으로 04:30/04:32/04:35 fetch_confirmed_candle 실패 |
| H4c (BACKFILL 비율) | 정량화 | JTO 24h 36.1% (258/714) |
| **F5 (미확정 종가 위 매수 판정, Issue #8 부분 회귀)** | **채택 (신규)** | fetch_confirmed_candle이 timestamp 일치만 검증. 04:34 close 777→779 갱신 미포착. 24h 반대 케이스 1/3 (33%) |
| **지시 1 항목 2 (백업~복원 try/finally 부재)** | **잠재 결함 (신규)** | live_loop.py:1021-1133 try/finally 부재. 예외 발생 시 복원 스킵 가능 |

---

## 5. 근본 원인 4중 + 잠재 결함 + F6 관찰

우선순위 정렬 (심각도 · 재발 확률 · 파급 영향 기준). 5.6은 근본 원인이 아니라 5.1/5.2 해석에 필수인 관찰 사항.

### 5.1 [HIGH · 감사 결함] audit_buy_eval UPDATE 덮어쓰기가 실시간 매매 시도를 소거

- **위치**: `services/db.py:1030-1045` `insert_buy_eval` UPDATE 분기
- **동작**: 같은 (ticker, bar_time) 기존 레코드 존재 시 timestamp·price·macd·signal·have_position·overall_ok·failed_keys·checks·notes 전체 UPDATE
- **결함**: BACKFILL 재평가가 실시간 판정 결과를 무조건 덮어쓴다. 실시간에서 `action=BUY`, `overall_ok=1`이었어도 BACKFILL이 이후 `overall_ok=0`으로 UPDATE하면 사후 감사에서 매수 시도 흔적 소거.
- **사용자 영향**: audit 화면 근거 클레임 자체를 왜곡. "매수 안 됨" 오해의 직접 원인.
- **재발 확률**: 24h JTO 실시간 BUY 3건 중 1건이 이미 소거됨 (표본 소규모, 비율 일반화 불가).

### 5.2 [HIGH · 매매 판정 데이터] fetch_confirmed_candle 확정 판정 조건 부족 (Issue #8 부분 회귀)

- **위치**: `core/rest_reconcile.py:515-524`
- **동작 (인용)**:
  ```python
  if latest_ts == closed_ts:
      close_price = df.iloc[-1]["Close"]
      logger.info(f"[RECONCILE] 확정 종가 ✅ ...")
      return df.iloc[-1]
  ```
- **결함**: "확정" 판단이 오직 timestamp 일치만 검증. close 값 안정화·연속 조회 일치·API 확정 플래그 검증 부재.
- **사고 인용**: 04:34:10 시점 Upbit 반환 close=777을 확정 판정 → 04:34:11 BUY 발화. 이후 04:35:31 BACKFILL 재조회 시 실제 확정 close=779. 방향이 같아 무해했으나 반대 방향(NO_SIGNAL→BUY 뒤집기) 시 "가짜 크로스 매수" 리스크.
- **완화 지점**: 현재 `fixed_price_buy_enabled=True`라 지정가 취소로 복구되지만, 시장가 전환 시 즉시 위험.

### 5.3 [MED · 전략 파라미터] fixed_price LIMIT 매수 미체결 반복 (사용자 결정 사안)

- **위치**: 매매 전략 파라미터. `wait_bars=5`, `fixed_price_buy_enabled=True`.
- **동작**: 크로스 전환 봉 close 값으로 LIMIT 지정가 매수. 5분 내 미체결 시 취소.
- **통계 (30일)**: KRW-JTO 체결률 54.3% (25/46), 취소 21건 중 완전 미체결 7건. KRW-RE 94.7%로 대조. 종목 변동성 편차 큼.
- **판단은 사용자 몫**: 시장가 전환·wait_bars 조정·추격 지정가·종목별 파라미터 분리 등 옵션 존재. 무엇이 적정인지는 손실 회피 성향과 슬리피지 허용도에 따라 다름.

### 5.4 [MED · 외부 의존] Upbit REST API 지연 → BACKFILL 우회 36%

- **위치**: `core/rest_reconcile.py:189-` `safe_fetch_rest`, `fetch_confirmed_candle`
- **동작**: 봉 종료 후 Upbit REST가 새 봉을 반환하기까지 지연이 자주 발생. 실패 시 다음 봉 REST-RECONCILE가 값 변경 봉으로 감지 → BACKFILL 리스트로 편입.
- **통계**: KRW-JTO 24h audit_buy_eval 714건 중 BACKFILL UPDATE 최종 상태 258건(36.1%). 서비스 전체 `봉 미반영` 로그 5,476건/24h.
- **원인 자체는 외부**이지만, BACKFILL 우회된 봉이 크로스 전환 봉일 경우 실시간 매매 판정을 놓칠 수 있음 (BACKFILL은 `backfill_mode=True`로 매매 금지 라인 1089).

### 5.5 [잠재 결함] Issue #11 백업~복원 try/finally 부재

- **위치**: `engine/live_loop.py:1021-1133`
- **결함**: 백업(1021)과 복원(1104)이 try/finally로 감싸져 있지 않아 백업~복원 사이 예외 발생 시 복원 스킵.
- **실사고 미확인**. Issue #11 재발 대비 예방 조치 필요.

### 5.6 [관찰 · F6] 변경형 BACKFILL 재평가의 상태 이중 반영

- **관찰 내용**: 2.3의 audit id 58080 checks (ema_fast=773.80 / ema_slow=773.26)는 백업 시점의 실시간 지표 상태(04:34 실시간 처리 후: 773.26/773.20)에 close=779를 다시 `update_incremental` 한 결과다. 즉 **같은 04:34 봉이 EMA 갱신에 두 번 반영**됐다 (첫 번째: 실시간 close=777, 두 번째: BACKFILL close=779).
- **함의**:
  1. **변경형 봉의 BACKFILL 재평가 audit 값은 지표로서 무효** — 참고 불가. 실시간 지표 상태 위에 두 번째 close를 더 얹은 결과이므로 어느 시점 어느 close를 어떻게 반영한 값인지 불분명.
  2. **BACKFILL이 NO_SIGNAL을 낸 이유는 prev가 이미 Golden이라 신규 전환 이벤트가 없었을 뿐**이다. "확정 데이터가 매수를 부정했다"는 의미가 결코 아니다.
- **필수 확인 사항**: **확정 종가 779 기준으로도 Dead→Golden 크로스는 유효했다 (779 > 777이므로 EMA fast 우위가 더 강화됨). 매수 판정 자체는 옳았고, 미확정 데이터의 실질 피해는 지정가 산정 기준(777)뿐이다.**
- **범위 결정**: 상태 이중 반영의 근본 수정(봉별 상태 스냅샷 필요)은 비용이 크므로 **이번 사건 범위에서 제외**. 대신 WO-1 설계에서 backfill_reason(또는 notes)에 "변경형 재평가 값은 상태 이중 반영으로 참고용" 표기(변경형/누락형 구분)를 포함해 audit 뷰어 오독을 방지한다.

---

## 6. 수정 제안

### WO-1 (승인 · 단독 선배포) — audit UPDATE 결함 통합 수정

**채택안**: **옵션 B (별도 컬럼)**. 채택 사유 — 이력 보존 + `(ticker, bar_time)` UNIQUE 제약 유지 + UI 변경 최소. 옵션 A는 스키마·뷰어 재작성 비용, 옵션 C는 동시성 취약 (본 리포트 초안이 스스로 지적).

**본체 (옵션 B)**: `services/db.py:1030-1045` audit_buy_eval UPDATE 로직 재설계.
- 신규 컬럼: `backfill_close`, `backfill_reason`, `backfill_at` (BACKFILL 재평가 결과만 여기에 UPDATE).
- 실시간 컬럼 (`price`, `overall_ok`, `failed_keys`, `checks`, `notes` 등)은 BACKFILL이 절대 건드리지 않는다.
- audit 뷰어는 실시간 판정을 기본 표시하고 `backfill_*` 값이 있으면 참고 정보로 병기.

**옵션 B 보완 2건** (지시 사항):
1. **동일 봉 재-BACKFILL 시 컬럼 무한 증식 금지**: 같은 봉에 BACKFILL이 2회 이상 발생하면 `backfill_*` 컬럼은 **최신값만 유지** + `[AUDIT-UPDATE]` 로그에 이전 값 남김. 예: `[AUDIT-UPDATE] BACKFILL 재평가 2회 이상 | ticker=... bar_time=... prev_backfill_close=778 new_backfill_close=779`.
2. **F6 표기 (변경형/누락형 구분)**: `backfill_reason` (또는 `notes`)에 `type=changed_close` (실시간 처리 후 close 값이 갱신됨) / `type=missing_bar` (실시간 처리 자체가 없었음) 구분값을 기록. **변경형은 상태 이중 반영으로 지표 값이 참고용**임을 명시. audit 뷰어에서 이 구분값을 아이콘/색상으로 표기해 오독 방지.

**추가 A** (본 리포트 결함): `engine/live_loop.py:1050, 1129` 백업/복원 로그 `logger.debug` → `logger.info` 승격. 프로덕션에서 감시 가능하도록.

**추가 B** (F5 실측 관측성): BACKFILL UPDATE 시 **변경 전 close 값 보존**. 별도 컬럼 `prev_close` 또는 `[AUDIT-UPDATE]` 로그에 `prev_close=X new_close=Y` 명시. 이 데이터가 WO-2 설계의 실측 근거가 된다.

**추가 C** (지시 1 항목 2): 백업~복원 try/finally 구조화. **설계 제약**:
1. **백업 dict 생성은 try 밖에서 완성** — 백업 도중 예외 시 finally가 미완성 dict 참조로 2차 사고 방지.
   ```python
   saved_indicators = {...}   # try 밖 (실패 시 BACKFILL 중단, 복원 불필요)
   try:
       for ts in sorted(backfill_ts_list):
           ...
       # 완료 로그도 try 안
   finally:
       # 복원 (라인 1104-1133)
   ```
2. **복원 자체 예외 처리**: finally 내부 복원 코드를 try/except로 감싸되, except에서 `logger.error("복원 실패 = 지표 오염 상태")` 명시 + 엔진 안전 정지 또는 WARMUP 재시드 유도 방안 비교 제시 (silent continue 금지).
3. **로그 쌍 보장**: `[BACKFILL] 지표 상태 백업` ↔ `[BACKFILL] 지표 상태 복원 완료` / `[BACKFILL] 지표 상태 복원 실패` 별도 문구로 구분. Issue #11 회귀 감시 체계로 활용.

**Issue #9 회귀 체크**: `is_backfill=True` 플래그 우회 로직(`core/strategy_engine.py:574` `if not backfill_mode and not self.is_new_bar(bar):`)과 옵션 B가 충돌하지 않는지 검증 필수.

**배포 정책**: 단독 선배포. 구현 → py_compile → 4경로 체크리스트 → 사용자 보고. **배포 승인은 별도 요청** (구현 완료 보고 시). 24h 실측 관측성 확보가 WO-2 설계의 전제.

**공통 요구**: 4경로 검증 체크리스트, 문서 라인 참조 갱신, `pages/dashboard.py:313` 버전 갱신.

### WO-2 (조건부 승인 · WO-1 배포 24h 후 착수) — fetch_confirmed_candle 확정 판정 강화

**본체**: `core/rest_reconcile.py:515-524` "확정 판정" 조건 강화.

**설계 옵션** (옵션 5 우선 검토 지시):

1. **N회 연속 조회 일치**: closed_ts 이후 최소 3회 (5초 간격) 재조회하여 close 값이 안정화된 뒤 확정 판정.
2. **최소 대기 시간**: 봉 종료 후 최소 T초(예: 15초) 대기 후 첫 조회. Upbit REST 특성상 봉 종료 직후 close 갱신이 이어짐. **상수 하드코딩 금지 — 실측 분포 근거 필수**.
3. **Upbit API 확정 플래그 조사**: pyupbit 응답에 is_confirmed 유사 필드가 있는지 확인 (문서 조사 필요).
4. **혼합**: 최소 대기 + 2회 연속 조회 일치.
5. **⭐ "다음 봉 존재 = 확정" 기준 (우선 검토)**: Upbit REST 분봉 응답에서 봉 T의 확정 판정을 "봉 T+1이 응답에 존재하는가"로 한다 (`count=2` 조회). timestamp 일치·close 안정화 추정·N회 일치보다 **결정적(deterministic)**이고 조회 비용이 낮다. 전제: Upbit 분봉 API가 진행 중 봉을 항상 포함하는가 (응답 스펙 조사 필요). 만약 진행 중 봉을 포함한다면 옵션 5는 이론상 완전한 판정.

**실측 선행 (필수)**: WO-1 배포로 확보되는 관측성(`prev_close` 보존 + INFO 로그 + `type=changed_close/missing_bar` 구분)을 활용해 **24h 실측 데이터** 수집:
- close 변경형 BACKFILL 빈도 (24h)
- 변경 폭 분포 (min / p50 / p95 / max, 원 단위)
- 봉 종료 후 안정화 소요 시간 분포 (첫 확정 판정 시각 - closed_ts, 초 단위)
- 종목별 편차 (KRW-JTO vs KRW-RE 등)

이 실측 분포로 옵션 1/2/4의 상수(T, N)를 결정한다. 옵션 5는 실측 후에도 API 스펙 확인 결과가 우선 판단 기준.

**트레이드오프 명시 의무**: 확정 조건 강화 = 신호 지연 증가 = **1분봉 전략에서 진입 지연 비용**. H4b (REST 지연 자체)와 결합 시 BACKFILL 우회 비율이 오히려 늘 수 있다. 설계안에는 각 옵션의 **예상 BACKFILL 비율 변화 추정** 포함 필수 (실측 데이터 기반 시뮬레이션).

**진행 순서**: 실측 데이터 확보 → 옵션 5 API 스펙 조사 → 설계안 보고 → 사용자 승인 → 구현 → 별도 배포.

**심각도 판정**: CRITICAL. 시장가 매수로 전환 시 즉시 실질 손실 위험. `fixed_price_buy_enabled=True`로 완화 중이지만 파라미터 변경에 취약. 시장가 전환은 본 WO 완료 전 금지.

### WO-3 (사용자 결정 · 안내문 초안 준비) — fixed_price 파라미터 재검토

**참고자료 제공** (통계 근거는 5.3):
- 30일 KRW-JTO LIMIT BUY 체결률 54.3%. RE 94.7%. 종목별 편차 큼.
- 취소 21건 중 완전 미체결 7건.

**옵션**:
- (a) 현행 유지 (fixed_price=True, wait_bars=5)
- (b) wait_bars 확장 (예: 10) — 체결 확률 증가, 놓친 시장가 상승 손실 증가
- (c) 시장가 매수 전환 — 즉시 체결, 슬리피지 리스크. **⚠️ WO-2 완료 전 금지 — 미확정 종가로 시장가 매수 시 F5 리스크가 실손실로 직결됨**
- (d) 추격 지정가 (post-only limit chase) — 지정가를 시장 movement에 맞춰 재산정
- (e) 종목별 파라미터 분리 (KRW-JTO만 (b)/(c)/(d))

**작업**: 안내문 초안 작성 (기술 용어 최소화, 옵션별 득실 1줄씩). 발송은 사용자(운영자) 검토 후. 사용자 결정 후 별도 WO 발행.

### WO-4 (보류) — Upbit REST 지연 완화

**착수 조건**: WO-1 배포 후 24h 실측(BACKFILL 비율 · 지연 분포) 확보. 그 데이터로 재평가. **지금 착수 금지**.

검토 예정 항목 (실측 후 조정):
1. Progressive Retry 간격/횟수 튜닝 (현행 5회·25초).
2. BACKFILL 우회 봉이 크로스 전환 봉일 때의 처리 정책. 현행: BACKFILL은 매매 금지 → 다음 실시간 봉에서 재감지에 의존.
3. WebSocket 체결 데이터 기반 캔들 조립을 보조 소스로 사용. **설계 검토 단계** (구현 아님).

### 후속 확인 항목 (본 사건 범위 외, 별도 추적)

- **부분 체결 소량 포지션의 매도 필터 정상 작동 검증**: 30일 KRW-JTO LIMIT BUY 취소 21건 중 14건이 부분 체결 후 취소로, 소량 포지션(계획 수량 미달)이 실제 보유 상태로 남았을 가능성. 이 소량 포지션에 대해 TP/SL/Trailing Stop 등 매도 필터가 계획 수량 기준이 아니라 실제 executed_volume 기준으로 정상 작동하는지 별도 검증 필요. audit-map A11 "3중 진실 소스" 문제(로컬 position vs upbit 실보유 vs audit 기록 삼중 정합성)와 연결 가능성 있음.

---

## 7. 검증 계획 (4경로 체크리스트)

WO-1, WO-2 배포 전 필수 검증:

**경로 1 — 실시간 확정 봉 처리** (live_loop.py:1220 CLOCK-CLOSE 성공 경로):
- [ ] 크로스 전환 봉에서 실시간 BUY 발화 → audit INSERT with `via_backfill=0`
- [ ] 이후 BACKFILL 재평가 발생 시 → audit UPDATE가 실시간 결과를 덮어쓰지 않음 (WO-1)

**경로 2 — Progressive Retry 성공 후 처리** (live_loop.py:1266):
- [ ] Retry 성공 시 audit INSERT with `via_backfill=0` (경로 1과 동일 로직)

**경로 3 — BACKFILL 재평가 경로** (live_loop.py:1091):
- [ ] `via_backfill=1` 로 별도 기록 (옵션 A/B/C에 따라)
- [ ] 백업/복원 로그 `INFO` 레벨로 매 BACKFILL마다 쌍 출력 (WO-1 추가 A)
- [ ] 백업~복원 예외 시 `복원 실패` 로그 + 안전 정지 (WO-1 추가 C)
- [ ] 변경 전 close 값 보존 (WO-1 추가 B)

**경로 4 — Error 경로** (fetch 실패, verify 실패, 예외):
- [ ] fetch_confirmed_candle이 timestamp 일치 + close 안정화 모두 통과 시에만 반환 (WO-2)
- [ ] BACKFILL 루프 중 예외 발생 시 복원 반드시 실행 + 로그 (WO-1 추가 C)
- [ ] 안전 정지 발동 시 사용자 CRITICAL 알림

**회귀 방지**:
- [ ] Issue #8 확정 봉 검증 회귀 테스트에 F5 케이스 추가 (미확정 close→확정 close 뒤바뀜 시나리오)
- [ ] Issue #9 (BACKFILL 중복 체크 우회) 회귀 테스트 통과
- [ ] Issue #11 (BACKFILL 지표 오염) 회귀 테스트 통과 + 백업/복원 예외 시나리오 신설

**배포 후 실측 (배포 후 24h)**:
- [ ] `[AUDIT-UPDATE]` 로그가 BUY 발화 행에 대해서는 0건 (WO-1 옵션 C 채택 시)
- [ ] 또는 BACKFILL이 별도 컬럼/행에만 기록되는지 audit 뷰어에서 시각적 확인 (옵션 A/B)
- [ ] `[BACKFILL] 지표 상태 백업/복원 완료` 로그 쌍 카운트 일치
- [ ] `[RECONCILE] 확정 종가 ✅` 로그 이후 BACKFILL 재평가에서 close 변경 발생 건수 (F5 개선 효과)

---

## 8. 교훈

### 8.1 audit는 판정 근거가 될 수 있어야 한다 — 덮어쓰기 금지

- 최종 상태만 남기는 UPDATE 정책은 감사(audit)라는 이름을 배신한다. 실시간 시도와 사후 재평가의 이력이 모두 보존되어야 사후 진단이 가능하다.
- 이번 사건은 audit 화면을 근거로 한 사용자 클레임 자체가 잘못된 결론(매수 안 됨)을 유도했다. 사용자의 클레임 능력이 감사 결함으로 왜곡되면 안 된다.

### 8.2 미확정 데이터로 매매 판정을 하면 안 된다 — 확정 조건은 timestamp뿐이 아니다

- Upbit REST의 봉 timestamp는 봉 시작 즉시 반환되지만 close 값은 이후 갱신된다. "timestamp가 있으니 확정"이 아니다.
- Issue #8 대책이 "미확정 종가 사용 금지"였는데, WO-2026-001 대책이 timestamp 지연만 방지하고 close 안정화는 놓쳤다. **부분 회귀**.

### 8.3 사용자 클레임의 전제부터 검증하라

- "Golden Cross 인데 매수 안 됨"이라는 클레임을 그대로 받으면 잘못된 가설(H1, H2)로 시간을 소진한다.
- Step 0 원본 데이터 확보 → journalctl 인용으로 첫 30분에 반전이 나왔다. **audit 표만 보지 말고 로그와 orders 테이블 크로스 체크가 필수**.

### 8.4 예외 안전성은 로직만큼 중요하다

- Issue #11 대책이 코드적으로는 완결됐지만 try/finally 부재로 예외 상황에서 무효화될 수 있다. 회귀 방지 대책 자체가 회귀 가능성을 가지면 안 된다.
- **로그가 없으면 감시가 없다**. `logger.debug`는 프로덕션에서 존재하지 않는 것과 같다. 감시 대상 로그는 INFO 이상 필수.

### 8.5 정적 분석과 실측을 병행하라

- 지시 1 항목 4의 (b) 시나리오 반증은 audit id 58079의 존재 + timestamp + retry 로그로 **1분 만에** 결정됐다. 코드만 봤으면 며칠 걸릴 수 있는 판정.
- 반대로 항목 2 (try/finally 부재)는 실측으로는 안 나오는 잠재 결함이므로 정적 분석 필수.

---

## 9. 문서 정합성

**정정 사항**:
- `docs/issues/issue-11.md` 및 `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md`에 언급된 "live_loop.py:750~859" 라인 참조는 **현재 코드에서 라인 1018-1133**이다. 리팩토링/삽입으로 라인이 이동함.
- WO-1 완료 시 두 문서의 라인 참조 갱신을 체크리스트에 포함할 것.
- 라인 참조가 낡으면 다음 조사자가 잘못된 구간을 먼저 읽는다 — 이번 조사 초반에도 사용자 지시서의 "750~859" 참조가 잘못된 구간(SETTINGS-SNAPSHOT 스레드 / WARMUP)을 가리켰다.

---

## 부록 A. 조사에 사용된 인용 원본

- systemd journalctl: `journalctl -u tradebot --since '2026-08-20 04:28:00' --until '2026-08-20 04:50:00'`
- SQLite 조회: `/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db`
  - `audit_buy_eval` (id 58074-58090, KRW-JTO, bar_time 04:26~04:45)
  - `audit_trades` (04:00~06:00, 결과 없음)
  - `orders` (id 402, provider_uuid=ab1f0804…)
- 소스 코드:
  - `engine/live_loop.py:914-1133` (CLOCK-CLOSE → RECONCILE → BACKFILL → VERIFY → CONFIRMED 흐름)
  - `core/rest_reconcile.py:434-624` (fetch_confirmed_candle)
  - `services/db.py:1000-1070` (insert_buy_eval UPDATE/INSERT 로직)
  - `core/strategy_engine.py:570-680` (on_new_bar_confirmed → _record_audit_log)

## 부록 B. 판정 조사 진행 요약

- Step 0 → H1~H4c → 중간보고(1차) → 보완 1 → 중간보고(2차) → 지시 1 정적 분석 → 결함 격상 보고(3차) → 지시 2 F5 조사 → 보완 2 → 보완 3 + 보고서 작성 → 정정 3건 + F6 반영 (확정판)

## 부록 C. WO 단계 배포 정책 (일괄 배포 금지)

| 단계 | 작업 | 전제 | 산출물 | 승인 필요 지점 |
|---|---|---|---|---|
| 1 | 보고서 정정 3건 + F6 반영 | — | 확정판 커밋 | 정정 검토 후 승인 (본 문서 배포) |
| 2 | WO-1 구현 (옵션 B + 추가 A/B/C + 보완 2건) | 1 완료 | 코드 diff + py_compile + 4경로 체크리스트 | **배포는 별도 승인** (구현 완료 보고 시) |
| 3 | WO-3 안내문 초안 | 병행 가능 (1 이후) | 초안 문서 | 사용자 검토 후 발송 |
| 4 | WO-1 배포 | 2 배포 승인 | 서버 반영 + 버전 갱신 | 사용자 승인 필수 |
| 5 | 24h 실측 (BACKFILL 비율 · 변경 폭 · 안정화 소요 분포) | 4 배포 후 24h 경과 | 실측 리포트 | 실측 결과 보고 |
| 6 | WO-2 설계안 (옵션 5 우선 검토 + 실측 근거 상수 + BACKFILL 비율 예측) | 5 완료 | 설계안 문서 | 사용자 승인 필수 |
| 7 | WO-2 구현 · 배포 | 6 승인 | 코드 + 배포 | 사용자 승인 필수 |
| 8 | WO-4 재평가 (착수 여부 판단) | 4 이후 실측 데이터 확보 | 판단 리포트 | 사용자 승인 필수 |

**공통 원칙**:
- 각 단계 완료 시 사용자 보고 후 대기.
- "보고 후 대기" 조건 유지 — 다음 단계로 자동 진행 금지.
- 서버 조회 전용 정책은 진단·실측 기간 내내 유지, 배포 승인 시에만 예외.
- WO-1과 WO-2 일괄 배포 금지 (실측 관측성이 없는 상태로 WO-2를 짜면 상수 하드코딩 결함 재발).
- **배포 완결 기준은 `systemctl active`가 아니라 엔진 세션 개시 로그(`🚀 [CLOCK-LOOP] 시작`)까지**. 2026-08-22 WO-1 배포에서 systemd `active` 시각과 엔진 세션 개시 사이에 51분 트레이딩 공백이 발생했다. 상세 체크리스트: `docs/operations/deploy-checklist.md`.

---

**작성 완료 일시**: 2026-08-21 (KST)
**확정판 상태**: 정정 3건 + F6 반영 완료. WO-1 옵션 B 확정. WO-2 실측 선행 조건부 승인.
**최종 승인 대기**: (1) 본 확정판 커밋 승인 (2) WO-1 구현 착수 승인 (3) WO-3 안내문 초안 검토
