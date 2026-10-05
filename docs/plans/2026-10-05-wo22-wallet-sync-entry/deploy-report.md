버전: v1.2026.10.04.1731 → v1.2026.10.05.1145

# WO-22 배포 완료 보고 — 지갑 동기화 복원 진입가 우선순위 + 지갑 0 닫힘 외부 매도(HTS_SELL) 기록

- 작성: 2026-10-05 (KST)
- 배포 대상: `3850794`. 코드 `dfc075f`, 문서 `c5b87f9` 와 `3850794` 를 포함한다.
- 서버 HEAD: `ce65f29` → `3850794` (reflog 15:18:44 pull Fast-forward)
- 재시작: 명령 2026-10-05 15:18:44. `ExecMainStartTimestamp=Mon 2026-10-05 15:18:45 KST`, NRestarts=0
- 관찰 로그 출처: `journalctl -u tradebot`
- 서버에서는 pull 과 restart 만 했고 나머지는 읽기만 했다. 투자자 포지션·주문·DB 는 바꾸지 않았다.
- 판정: **0~3 전 항목 통과.** 실패 시 되돌림(`dfc075f` 단독 revert)은 쓰지 않았다.

## 3점 일치

| | HEAD | dashboard.py 버전 | 기동 |
|---|---|---|---|
| 로컬 (배포 시점 origin/main) | `3850794` | v1.2026.10.05.1145 | — |
| 서버 | `3850794` | v1.2026.10.05.1145 | 15:18:45 KST |
| 화면 (운영자 육안) | — | v1.2026.10.05.1145 | — |

로컬에는 배포 뒤 WO-24 커밋 `147efea`(v1.2026.10.05.1526)와 문서 커밋이 쌓여 있다. WO-24 는 서버에 배포하지 않았다.

## 0. 배포 전 확인 (`deploy/pre-check.txt`, 15:18:33 조회)

| 항목 | 결과 | 판정 |
|---|---|---|
| KRW-JTO 포지션: account_positions | virtual_coin 0.0, locked 0.0. meta `{"locked_warned": true}` 가 남아 있다 (WO-23 ③). | 통과 (보유 없음 → 배포 진행) |
| KRW-JTO 포지션: Upbit /v1/accounts | http 200, JTO 행 없음 = 0 | 통과 |
| origin/main / 서버 HEAD | `3850794` / `ce65f29` | 통과 |
| 10:54:58 이후 매매 이력 | orders 1건: 565 SELL FILLED, 10:59:06, 765. 10:59 사건의 STOP_LOSS. audit_trades 1201 | 기록 |
| 사후 확인 9 선행 대조 | 565: executed_at 10:59:06 = Upbit 마지막 체결 10:59:06, 차이 0.0초 | 통과 |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `3850794` (`dfc075f` 포함 확인) |
| 재시작 | 15:18:44 명령, 15:18:45 active (running) |
| 서버 버전 | `v1.2026.10.05.1145` |

## 2. 30분 무접속 관찰 (15:18:44 ~ 15:48:45, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) 기동 줄 3종 | BOOT-RESUME success, 시드 1줄, 감사 행 보존 1줄 | 15:18:51 `[BOOT-RESUME] success` (6.1s), `timeframe=minute1`. 15:18:52 `시드 방식=long_history bars=800 ema_fast=772.7931 ema_slow=769.1553` 1줄. `감사 행 보존 \| kept=198 inserted=1 updated_placeholder=1` 1줄 | 통과 |
| (b) 사후 확인 7 | 폴백 0, 1,200봉 기준 차이 0.1원 이내 | sma200 0, 긴 이력 시드 실패 0. `wo17s_verify_seed.py … 1200 --interval minute1`: 800봉 재현 −0.0000 / +0.0000, 1200봉 기준 −0.0000 / **−0.0030** (`deploy/verify-seed.txt`) | 통과 |
| (c) WO-22 `[POSITION-SYNC] entry_price=… (출처: …)` | 포지션이 생기면 확인 | 서버 `core/strategy_engine.py` 코드 존재 확인: 615행 `entry_price={entry_price} (출처: {source})`, 610행 수량 불일치, 506행 외부 매도 기록. journal 실측은 모두 **0건**. 관찰 중 KRW-JTO 포지션이 없어 **해당 사건 없음** | — |
| (d) HTS_SELL 기록 경로 | 생기면 확인 | 외부 매도 기록 0, 강제 포지션 종료 0. **해당 사건 없음** | — |
| (e) 결함 태그 | 0 | ` ERROR `, Traceback, `[POS-DESYNC] class=`, `Upbit에 없는 timestamp`, `불일치 발견`, `과거 봉 검증 실패`, `database is locked`, `[LOCKED-QTY]`, CRITICAL, VERIFY WARNING 모두 0. 외부 스캐너 0 | 통과 |
| (f) Bar# / 조정 / BACKFILL | Bar# 5 이상, 400봉, BACKFILL 0 | Bar#201 (15:19:11) → Bar#222 (15:48:11), 22봉. 1분봉 30개 중 거래 없는 봉 8개. 조정 400봉 수신 31회. BACKFILL 0, 미확정 봉 제외 0 | 통과 |
| (g) trailing 재계산 (WO-21) | 포지션 없음 → 0 | `[TRAILING-RESTORE]` 전체 0. 기동 시 포지션 없음 (POS-SYNC, boot_seed, BOOT-SEED 0) | 통과 |
| (h) 상설: 평가 통과 ↔ 체결 1:1 | 표 | 아래 표 | 통과 |

### 상설 항목 — BUY/SELL 평가 통과 행 대 실제 체결 1:1 대조 (`deploy/match-1to1.txt`)

| 구간 | 종류 | 통과/발동 | 체결 | 취소 | 미요청 | 창 안 orders |
|---|---|---|---|---|---|---|
| 15:18:44 ~ 15:48:45 (관찰 창) | BUY 평가 통과 (overall_ok=1) | 0 | 0 | 0 | 0 | 0건 |
| | SELL 평가 발동 (triggered=1) | 0 | 0 | 0 | 0 | |
| 15:48:45 ~ 16:15:52 (접속 구간, 참고) | BUY 평가 통과 | 0 | 0 | 0 | 0 | 0건 |
| | SELL 평가 발동 | 0 | 0 | 0 | 0 | |

대조 방법: 각 통과·발동 행의 bar_time 부터 봉 3개(= interval × 3) 안에 있는 같은 방향 orders 를 찾는다. FILLED 가 있으면 체결, 전부 CANCELED 면 취소, 없으면 미요청으로 센다. 스크립트는 `deploy/wo22d_match.py`.

### 관찰 중 확인 사항 (WO-22 무관, 결함 아님)

1. **관찰 창 안 대시보드 접속 (15:36:13).**
   - 15:36:13 `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)`, 15:36:53 감사 로그 페이지 접속이 있었다.
   - 이 시간에 우리 측은 접속하지 않았다. 접속 주체는 확인하지 못했다. 같은 시각 투자자의 앱 매수(아래 2)가 있어 투자자 접속으로 추정만 한다.
   - 엔진은 다시 시작하지 않았다 (`run_live_loop start` 1회뿐). 무접속 관찰의 목적인 "대시보드 없이 기동이 재개되는가" 는 15:18:51 에 이미 확인됐으므로 판정에 영향이 없다.
2. **투자자 앱 매수, 다른 종목.**
   - 15:30:56 KRW-BIRB HTS_BUY, 15:32:58 KRW-BIRB HTS_BUY_ADD, 15:36:03 KRW-SUI HTS_BUY
   - `[HTS-DETECT]` 가 감지해 audit_trades 1202~1204 에 기록했다. 봇은 KRW-JTO 만 매매하므로 매매 영향은 없다.
   - 다른 종목 HTS 기록은 2026-05-24 부터 475건 있는 기존 동작이다. 손대지 않았다.

## 3. 대시보드 1회 접속 (운영자 접속, 16:15)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 16:15:38 1줄 (boot_resume_at 15:18:51) | 통과 |
| 엔진 스레드 | 1개 | 15:18:44 이후 `run_live_loop start` 1회 (기동 때), NRestarts=0 | 통과 |
| 화면 버전 | v1.2026.10.05.1145 | 운영자 육안 확인 "v1.2026.10.05.1145" | 통과 |
| 15:48:45 ~ 16:15:52 상태 | — | Bar# 13, 결함 태그 0, `[POSITION-SYNC]`, `[TRAILING-RESTORE]`, 매매 0 (`deploy/access.txt`) | 통과 |

## 4. 남은 확인 (사후 확증으로 넘김)

- WO-22 의 두 경로(진입가 출처 우선순위, HTS_SELL 기록)는 관찰 중 KRW-JTO 포지션이 없어 실측하지 못했다. 다음에 외부 매수 복원이나 외부 매도로 지갑이 0 이 되면 아래를 확인한다.
  - `[POSITION-SYNC] entry_price=… (출처: upbit_avg|account_positions|orders)` 1줄
  - audit_trades `HTS_SELL` 1행 (가격 비어 있음, 손익 집계 제외), 감사 로그 페이지에 "외부 매도" 로 표시
- 투자자 안내는 WO-24 배포 뒤 두 배포를 묶어 한다.

## 5. 규칙 준수

- heredoc: 이 배포 작업에서는 쓰지 않았다. 같은 세션의 WO-24 작업에서 1회 위반이 있었고, `docs/plans/2026-10-05-wo24-unfilled-buy-audit/report.md` 8절에 적었다.
- 서버 쓰기는 pull 과 restart 뿐이다. 키 값은 어떤 출력에도 적지 않았다.
## 6. 묶음

- `deploy-report.md` (이 문서), `deploy-commands.txt`
- `deploy/pre-check.txt` (0단계, 서버 reflog), `deploy/deploy.txt`, `deploy/observation-30min.txt`, `deploy/verify-seed.txt`
- `deploy/match-1to1.txt` (상설 1:1 대조), `deploy/access.txt`, `deploy/journal-excerpt.txt`
- 스크립트: `deploy/wo22d_pre.py`, `deploy/wo22d_obs.sh`, `deploy/wo22d_match.py`
