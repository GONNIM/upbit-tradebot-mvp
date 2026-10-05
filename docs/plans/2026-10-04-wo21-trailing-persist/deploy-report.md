버전: v1.2026.10.02.2241 → v1.2026.10.04.1731

# WO-21 배포 완료 보고 — 재시작 때 trailing 상태 재계산 + ts_armed 실제 값

- 작성: 2026-10-05 (KST)
- 배포 대상: `ce65f29` (코드 `770b104` + 문서 `ce65f29`)
- 재시작: 명령 2026-10-05 10:54:58, `ExecMainStartTimestamp=Mon 2026-10-05 10:54:59 KST`
- 관찰 로그 출처: `journalctl -u tradebot`
- 서버는 pull·restart 외 읽기만 했다. 포지션·주문·DB 무변경. 투자자 안내 없음.
- 판정 (Fable): **WO-21 통과.** 관찰 중 10:59 사건은 WO-21 과 무관한 기존 경로 결함 → WO-22 로 분리 (`docs/plans/2026-10-05-wo22-wallet-sync-entry/incident.md`).

## 0. 배포 전 확인 (`deploy/pre-check-and-posthoc9.txt`, 10:54:03 조회)

| 항목 | 결과 | 판정 |
|---|---|---|
| 10-04 10:22 이후 orders | 6건 (559 BUY CANCELED · 560 BUY · 561 SELL · 562 BUY · 563 SELL · 564 BUY, 모두 KRW-JTO). 마지막 = **id 564, 2026-10-05 08:25:12 요청 / 08:26:52 체결, BUY** | 기록 |
| 564 포지션의 행방 | 09:39:53 투자자 앱 지정가 매도 @778 전량 체결 → 09:40:45 `[LOCKED-QTY]` → 09:42:11 `[POSITION-SYNC] 강제 포지션 종료`(지갑 0). orders·audit_trades 매도 기록 없음 (WO-22 A2) | 기록 |
| account_positions KRW-JTO | virtual_coin 0.0, virtual_coin_locked 0.0 (meta `{"locked_warned": true}` 잔존 — WO-23 ③) | 통과 |
| Upbit /v1/accounts JTO | 행 없음 = 0 | 통과 |
| origin/main / 서버 HEAD | `ce65f29` / `e97dec6` | 통과 |
| 사후 확인 9 선행 대조 | 확정 6건: id 559 CANCELED — canceled_at 2026-10-04T14:21:12.764527, trades 0, executed_at 없음(정상). FILLED 5건(560~564) — `executed_at` 과 Upbit `trades[].created_at` 마지막 값 차이 **모두 0.0초** | **통과** |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `ce65f29` |
| 재시작 | 10:54:58 명령, 10:54:59 active (running) |
| 서버 버전 | `v1.2026.10.04.1731` |

## 2. 30분 무접속 관찰 (10:54:58 ~ 11:24:59, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) 기동 | BOOT-RESUME success, 시드 1줄, 감사 행 보존 1줄 | 10:55:05 `success` (6.4s), `timeframe=minute1`, `시드 방식=long_history bars=800 ema_fast=769.9659 ema_slow=771.7653` 1줄, `감사 행 보존 \| kept=143 inserted=57 updated_placeholder=0` 1줄 (57 = 08:26~09:42 보유 구간 봉) | 통과 |
| (b) 재계산 경로 | 포지션 없음 → 성공 줄·재계산 불가·예외 0 | 코드 존재 확인: `core/trailing_restore.py:102` `재계산 불가 → 초기화 \| 사유=`, `:132` `건너뜀`, `:182` `armed=`, `engine/live_loop.py:1223` `사유=예외`. journal `[TRAILING-RESTORE]` 전체 0, armed= 0, 재계산 불가 0, 예외 0, 건너뜀 0 (기동 시 포지션 없음: POS-SYNC·boot_seed·BOOT-SEED 0) | 통과 |
| (c) 사후 확인 7 | 폴백 0, 1,200봉 기준 0.1원 이내, 간격 인자 | sma200 0, 시드 실패 0. `scripts/wo17s_verify_seed.py … 1200 --interval minute1` 첫 줄 `봉 간격: minute1 (출처: --interval 인자)` (= journal `timeframe=minute1`). 800 재현 +0.0000 / +0.0000, 1200 기준 +0.0000 / **+0.0013** (`deploy/verify-seed.txt`). 인자 없이 실행 시 `출처: params JSON …` 로 같은 minute1 | 통과 |
| (d) 결함 태그 | 0 | ` ERROR `·Traceback·`[POS-DESYNC] class=`·`Upbit에 없는 timestamp`·`불일치 발견`·`과거 봉 검증 실패`·VERIFY WARNING·`database is locked`·`[LOCKED-QTY]`·CRITICAL 모두 0. 외부 스캐너 0 | 통과 |
| (e) Bar# / 조정 / BACKFILL | Bar# 5 이상, 400봉, BACKFILL 0 | Bar#201 (10:56:10) → Bar#218 (11:23:10), 18봉 (1분봉 28봉 중 거래 없음 10). 조정 400 요청 28회 모두 400 수신. BACKFILL 0, 미확정 봉 제외 0 | 통과 |
| (f) 봇 매수 뒤 ts_armed·무장 로그 | 있으면 확인 | 봇 매수 0 → **해당 사건 없음** (사후 확인 10 으로). 참고: 10:58 봉 SELL 평가 행(10:59:05, 아래 사건) `ts_armed=0` — 그 포지션은 미무장이었으므로 맞는 값 | — |

### 관찰 중 사건 (WO-21 무관, WO-22 로 분리)

10:58:26 투자자 앱 지정가 매수 13.05483028개 @766 → 10:59:05 엔진 매 봉 지갑 동기화가 외부 매수로 복원하며 진입가를 orders 564 @777(이미 앱 매도된 봇 매수)로 차용 → pnl −1.42% → STOP_LOSS → 10:59:06 시장가 매도 @765 (orders 565, audit_trades 1201). 영향 약 −₩23(수수료 포함). `[TRAILING-RESTORE]` 0건, 매도 필터는 StopLossFilter — WO-21 경로와 무관. 상세·증거: `docs/plans/2026-10-05-wo22-wallet-sync-entry/incident.md`, `evidence/`.

## 3. 대시보드 1회 접속 (운영자 접속, 14:08)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 1줄 (14:08:13, boot_resume_at 10:55:05) | 통과 |
| 엔진 스레드 | 1개 | 11:24:59 이후 `run_live_loop start` 0회, NRestarts 0 | 통과 |
| 화면 버전 | v1.2026.10.04.1731 | 운영자 육안 확인 | 통과 |
| 11:24:59 ~ 14:08:49 상태 | — | Bar# 97, 결함 태그 0, `[TRAILING-RESTORE]`·`[POSITION-SYNC]`·`[LOCKED-QTY]`·매매 0 (`deploy/access.txt`) | 통과 |

## 4. 문서

- 운영 가이드 `docs/operations/wo8-force-buy-verification-guide.md`
  - 사후 확증 8번: 정식 유지, ⑥ "(WO-21, 2026-10-05 10:54:59 배포 뒤 기동부터 적용) 보유 중 재시작 시 `[TRAILING-RESTORE]` 1줄, 값이 직전 invariant_snapshots 와 일치".
  - 사후 확증 9번: 2026-10-05 확인 기록 추가 (6건 대조, 0.0초) — **통과**.
  - 사후 확증 10번 신설: WO-21 배포 뒤 첫 봇 포지션에서 무장 로그(ACTIVATED·고정 금액 폭·AUTO-SWITCH)가 이전 형태로 1회, 무장 뒤 `audit_sell_eval.ts_armed`=1, 무장 전 0.
  - 세션 개시 정기 점검 목록: 사후 확인 1~10.
- 문서 커밋 1건. 서버 pull 없음. zip 미추적.

## 5. 묶음

- `report.md` (이 문서), `commands.txt`, `git-log.txt`
- `deploy/journal-excerpt.txt` (10:54:58 ~ 14:09, 기동·관찰·사건·접속), `deploy/observation-30min.txt`, `deploy/access.txt`, `deploy/deploy.txt`
- `deploy/pre-check-and-posthoc9.txt` (0단계 + 사후 확인 9 대조), `deploy/verify-seed.txt`
- 스크립트: `deploy/wo21d_pre.py`, `deploy/wo21d_obs.sh`
- 사건 증거 (`incident/`): journal 10:54 ~ 11:00 발췌, Upbit 주문 조회 결과, orders 564·565 · audit_trades 1201, incident.md
