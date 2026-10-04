버전: v1.2026.10.02.0942 → v1.2026.10.02.2241

# WO-20 배포 완료 보고 — executed_at 기록 + 복원 조회 정렬·시각 대용 + boot_seed 평균가 유지

- 작성: 2026-10-04 (KST)
- 배포 대상: `e97dec6` (코드 `986c9b0` + 문서 `e97dec6`)
- 재시작: 명령 2026-10-04 10:22:33, `ExecMainStartTimestamp=Sun 2026-10-04 10:22:33 KST`
- 관찰 로그 출처: `journalctl -u tradebot`
- 포지션·주문·DB 보정 없음. 서버는 pull·restart 외에 읽기만 했다. 투자자 안내 없음. 체감 변경 없음.

## 결론

0~3 단계 모든 항목이 기대값과 같거나 운영자 판단으로 통과했다. 4단계(되돌리기)는 하지 않았다. 판단이 필요했던 점 두 가지:

1. **봉 간격이 1분봉으로 바뀌어 있었다** (2026-10-03 21:03:47 엔진 재시작부터 `timeframe=minute1`, 운영자 설정). 그래서 사후 확인 7 의 `scripts/wo17s_verify_seed.py`(5분봉 고정)는 맞지 않았다. 1분봉 사본으로 대조해 통과했다. 저장소 스크립트는 바꾸지 않았고, 가이드 사후 확증 7번에 주의 문단을 넣었다.
2. **포지션이 없을 때 대시보드 카드는 "없음" 이 아니라 "💹 최근 거래 … (실현)" 을 보여 주는 것이 코드 설계다** (`pages/dashboard.py:862` `if qty > 0` 일 때만 "💹 현재 포지션 … (미실현)", 아니면 else 분기). 운영자 화면 확인 결과 "최근 거래 (실현)" 으로 보였다. 미실현 수익률은 표시되지 않았으므로 운영자 지시로 통과 처리했다.

## 0. 배포 전 확인 (`deploy/pre-check-and-order-compare.txt`, 10:22:22 조회)

| 항목 | 결과 | 판정 |
|---|---|---|
| 10-02 14:15 봇 매도(id 557) 이후 orders | 1건: id 558, 2026-10-03 20:05:11, KRW-JTO **SELL** FILLED 2071.002개 @725 (TRAILING_STOP_FIXED). 마지막 주문 = 558 | 기록 |
| 같은 기간 audit_trades | JTO 앱 매수 10-03 09:18:47(HTS_BUY 710) → 봇 매도 20:05:13. 그 밖에 다른 종목 앱 매수 6건(UP2·MTL·STEEM·FOLD·FLOCK·USDT, 봇 대상 아님) | 기록 |
| account_positions KRW-JTO | virtual_coin 0.0, virtual_coin_locked 0.0 | 통과 |
| Upbit /v1/accounts JTO | 행 없음 = 0 | 통과 |
| origin/main / 서버 HEAD | `e97dec6` / `786b5cb` | 통과 |
| 정렬 비교 (KRW-JTO BUY) | 옛 정렬 `executed_at , timestamp DESC` → **id 555**. 새 정렬 `COALESCE(executed_at, updated_at, timestamp) DESC, ROWID DESC` → **id 555**. 같은 id. executed_at 채워진 행 0 | 통과 |
| 청산 검사 | 마지막 BUY rowid 555 < SELL rowid 558 → `get_last_open_buy_order` 는 None 반환 (기존 B1 규칙) | 기록 |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `e97dec6` |
| 재시작 | 10:22:33 명령, 10:22:33 active (running) |
| 서버 버전 | `v1.2026.10.02.2241` |

## 2. 30분 무접속 관찰 (10:22:33 ~ 10:52:33, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) 기동 | BOOT-RESUME success, 시드 long_history 1줄, 감사 행 보존 1줄, boot_seed 미진입, `[BOOT-SEED]` 0 | success 10:22:40 (6.6s) · `시드 방식=long_history bars=800` 1줄 · `감사 행 보존 \| kept=200 inserted=0 updated_placeholder=0` 1줄. boot_seed 분기 표식(코드 존재 확인: `live_loop.py:360` `[SEED] raw_last_open`, `:439` `Position recovered`, `:447` `[BOOT-SEED]`, `position_state.py:264` `[POSITION-APPLY] source=`) 모두 0건 | 통과 |
| (b) 체결 확정 | 있으면 executed_at 대조 | `[OR] final` 0건, orders id>558 없음. **해당 사건 없음** → 사후 확증 9번으로 넘김 | — |
| (c) 복원 조회 | 0단계 기준과 같은 id | 배포 코드 `get_last_open_buy_order` 호출(SELECT 만): 선택 행 `{price 734, entry_bar 330, entry_ts_iso 2026-10-02T08:00:14.045644 (updated_at 대용)}` = id 555 → 청산 검사로 None. 0단계와 같음 (`deploy/restore-lookup.txt`) | 통과 |
| (d) 사후 확인 7 | 폴백 0, 1,200봉 기준 0.1원 이내 | 폴백 0(sma200 0, 시드 실패 0). **1분봉 대조**: 800 재현 차이 +0.0000 / +0.0000, 1,200 기준 +0.0000 / +0.0052 (`deploy/verify-seed-1min.txt`). 참고: 저장소 스크립트(5분봉 고정) 그대로는 +3.6428 / −12.5917 (`deploy/verify-seed-5min-script.txt`, 간격 불일치로 무효) | 통과 |
| (e) 결함 태그 | 0 | ` ERROR `·Traceback·`[POS-DESYNC] class=`·`Upbit에 없는 timestamp`·`불일치 발견`·`과거 봉 검증 실패`·`database is locked`·`[LOCKED-QTY]`·CRITICAL 모두 0. 따로: 기동 `[POS-SYNC]` WARNING 0(포지션 없음), 외부 스캐너 Traceback 0 | 통과 |
| (f) Bar# / 조정 / BACKFILL | Bar# 5 이상, 조정 400, BACKFILL 0 | Bar#201 (10:27:11) → Bar#215 (10:51:05), 15봉. 10:22~10:25 봉은 무거래(`CONFIRMED-NO-TRADE`, 1분봉에서 흔함). 조정 400 요청 29회 모두 400 수신. BACKFILL 0, 미확정 봉 제외 0 | 통과 |
| (g) `[OR] executed_at 대체` | 0 | 코드 존재 `engine/order_reconciler.py:380`. journal 0건 | 통과 |

## 3. 대시보드 1회 접속 (10:52:33 이후, 운영자 접속)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 1줄 (10:53:48, boot_resume_at 10:22:40) | 통과 |
| 엔진 스레드 | 1개 | 접속 뒤 `run_live_loop start` 0회 | 통과 |
| 화면 버전 | v1.2026.10.02.2241 | 운영자 육안 확인 | 통과 |
| 미실현 수익률 | "없음" | 운영자 화면: "💹 최근 거래 … (실현)" — 포지션 없을 때의 설계 표시(미실현 미표시). 운영자 지시로 통과 | 통과 (설명 위 결론 2) |
| 접속 구간 결함 태그 | 0 | ERROR·Traceback·CRITICAL·Missing file·locked·POS-DESYNC·VERIFY 실패·불일치·`[BOOT-SEED]` 모두 0, Bar# 2 (10:52:33 ~ 10:54:09) | 통과 |

## 4. 문서

- 운영 가이드 `docs/operations/wo8-force-buy-verification-guide.md`
  - 사후 확증 8번: "초안" → 정식. 기준 시각 10-04 10:22:33, 배포 기동은 포지션 없음이라 해당 없음.
  - 사후 확증 9번 신설: 배포 뒤 첫 확정 주문의 executed_at 이 Upbit `trades[].created_at` 마지막 값과 수 초 이내, 취소 확정이면 canceled_at 존재, `[OR] executed_at 대체` 0건.
  - 사후 확증 7번: 검증 스크립트가 5분봉 고정이라는 주의 문단.
- 문서 커밋 1건. 서버 pull 없음. zip 미추적.

## 5. 묶음

- `report.md` (이 문서)
- `deploy/journal-excerpt.txt` (10:22:33 ~ 10:55:00 주요 줄)
- `deploy/pre-check-and-order-compare.txt` (정렬 비교), `deploy/restore-lookup.txt` (복원 조회)
- `deploy/verify-seed-1min.txt`, `deploy/verify-seed-5min-script.txt`
- `deploy/observation-30min.txt`, `deploy/access.txt`, `deploy/deploy.txt`
- 스크립트: `deploy/wo20d_pre.py`, `deploy/wo20d_restore.py`, `deploy/wo20d_verify_seed_m1.py`, `deploy/wo20d_obs.sh`
- `commands.txt`, `git-log.txt`
