버전: v1.2026.10.01.1955 → v1.2026.10.02.0942

# WO-19 배포 완료 보고 — 워밍업 감사 행 보존

- 작성: 2026-10-02 (KST)
- 배포 대상: `786b5cb` (코드 커밋 `8fd26c1` + 구현 보고 docs `786b5cb`)
- 재시작: 명령 2026-10-02 10:03:17, `ExecMainStartTimestamp=Fri 2026-10-02 10:03:18 KST`
- 관찰 로그 출처: `journalctl -u tradebot`. `mcmax33_engine_debug.log` 는 보조로만 봤다.
- 포지션·주문은 건드리지 않았다. 투자자 안내는 없다 (`docs/operations/investor-notice-log.md` 에 "통보 대상 아님" 기록).
- 체감 변경: 없음.

## 결론

0~3 단계 모든 항목이 기대값과 같다. 4단계(되돌리기)는 하지 않았다. 다만 2(a)의 "kept 가 200 에 가깝다" 는 기대는 전제가 실제와 달랐다. 실측은 kept=133 이고, 이는 창 안 실제 판정 행 수와 정확히 같다 (아래 2(a) 설명).

## 0. 배포 전 확인 (`deploy/baseline-before.txt`)

| 항목 | 결과 | 판정 |
|---|---|---|
| Upbit 잔고 (GET /v1/accounts, 10:02:38) | JTO 행 없음 = 0 | 통과 |
| account_positions KRW-JTO | virtual_coin 0.0, virtual_coin_locked 0.0, entry_price 0.0, meta `{}` | 통과 |
| origin/main | `786b5cb` | 통과 |
| 기준 행 75021 (03:35 봉) | overall_ok=1, checks.reason=BUY_SIGNAL, notes `🟢 BUY \| Golden \| bar=286` | 기록 |
| 기준 행 75063 (07:55 봉) | overall_ok=1, checks.reason=BUY_SIGNAL, notes `🟢 BUY \| Golden \| bar=330` | 기록 |

배포 전에 KRW-JTO 감사 행 스냅샷도 떴다 (`deploy/snapshot-before.tsv`, bar_time ≥ 10-01 16:00). BUY 실제 판정 133행, BUY WARMUP 50행(10-01 20:10 기동이 남긴 자리표시자), SELL 20행이다.

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `786b5cb` |
| 재시작 | 10:03:17 명령, 10:03:18 active (running) |
| 서버 버전 | `v1.2026.10.02.0942` |

## 2. 30분 무접속 관찰 (10:03:18 ~ 10:33:18, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) `[WARMUP] 감사 행 보존` | 1줄, failed 없음, kept≈200 | 1줄, failed 없음, `kept=133 inserted=20 updated_placeholder=47` | 통과 (설명 참조) |
| (b) 기동 구간 `[AUDIT-UPDATE] BUY 실시간 재판정` | = updated_placeholder | 47 = 47. SELL 재판정 0. 관찰 창 전체 BUY 재판정도 47 | 통과 |
| (c) 기준 행 75021·75063 | 0단계와 같음 | 같음 (기동 직후 10:04 스냅샷, 접속 후 11:15 조회 모두) | 통과 |
| (c) 실제 판정 → WARMUP 바뀐 행 | 0 | 0 (기동 뒤 timestamp 갱신된 WARMUP 67행 = 자리표시자 갱신 47 + 신규 20, 그중 기동 전 실제 판정이던 행 0) | 통과 |
| (d) 사후 확인 7 | `시드 방식=long_history bars=800` 1줄, 폴백 0, 1,200봉 기준 0.1원 이내 | 1줄, sma200 0, 시드 실패 0, 폴백 알림 0. 1,200봉 기준과 차이 fast +0.0000 / slow +0.0040 | 통과 |
| (e) 결함 태그 | 0 | ` ERROR `·Traceback·`[POS-DESYNC] class=`·`Upbit에 없는 timestamp`·`불일치 발견`·`과거 봉 검증 실패`·POLLUTED·`database is locked`·`ON CONFLICT clause`·CRITICAL 모두 0. 외부 스캐너 Traceback 0 | 통과 |
| (f) Bar# / 조정 / BACKFILL | Bar# 5 이상, 조정 매번 400, BACKFILL 0 | Bar#201→206 (6봉), 조정 400봉 수신 6회, BACKFILL 시작 0·평가 0·미확정 봉 제외 0 | 통과 |
| (g) WO-12 | `[BOOT-RESUME] success` | 10:03:25 `success user=mcmax33 mode=LIVE elapsed=6.7s`, run_live_loop start 1 | 통과 |
| (h) 매수 신호 | 있으면 해당 봉 행 확인 | EMA Buy Signal 0, action=BUY 0. **해당 사건 없음** | — |

### (a) 원문 1줄

```
2026-10-02 10:03:26 INFO engine.live_loop | [WARMUP] 감사 행 보존 | kept=133 inserted=20 updated_placeholder=47
```

### (a) kept=133 인 이유

워밍업 창 200봉(Upbit 캔들은 거래 없는 봉이 빠지므로 10-01 16:15 ~ 10-02 09:55)을 배포 전 스냅샷과 대조했다 (`deploy/snapshot-compare.txt`).

| 분류 | 행 수 | 내용 |
|---|---|---|
| kept (실제 판정 보존) | 133 | 10-01 20:10 기동 뒤 실시간으로 쓴 BUY 판정 행 전부. 배포 전 스냅샷의 실제 판정 133행과 같다 |
| updated_placeholder | 47 | 10-01 16:15 ~ 20:05 봉. 이전 기동(10-01 20:10)이 남긴 WARMUP 자리표시자 |
| inserted | 20 | 포지션 보유 봉(03:40·03:50, 08:00 ~ 09:25). 보유 중에는 SELL 평가만 쓰므로 BUY 행이 없었다 |

지시문의 "직전 200봉 대부분이 실제 판정 행" 이라는 전제는 실제와 달랐다. 이전 기동이 남긴 자리표시자 47행과 보유 구간 20봉이 있었다. 실제 판정 행은 하나도 덮이지 않았다.

### (b) 비교

| 값 | 건수 |
|---|---|
| `[WARMUP] 감사 행 보존` 의 updated_placeholder | 47 |
| 기동 구간(보존 줄 10:03:26 이전) `[AUDIT-UPDATE] BUY 실시간 재판정` | 47 (첫 줄 bar_time 10-01 16:15 old_id 74873, 끝 줄 20:05 old_id 74935) |
| 이전 기동(10-01 20:10)의 같은 건수 | 200 |

### (d) 검증 스크립트 출력 (`deploy/verify-seed.txt`)

```
마지막 확정 봉 KST: 2026-10-02 09:55  bars_long=1200
로그        fast=736.1508 slow=733.8483
800 재현    fast=736.1508 slow=733.8483  (로그와 차이 +0.0000 / +0.0000)
1200 기준  fast=736.1508 slow=733.8523  (로그와 차이 +0.0000 / +0.0040)
```

## 3. 대시보드 1회 접속 (10:33:18 이후, 운영자 접속)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 1줄 (10:43:35, "boot-resume 로 이미 실행 중", boot_resume_at 10:03:25) | 통과 |
| 엔진 스레드 | 1개 | 접속 뒤 run_live_loop start 0회 (기동 때 1회만) | 통과 |
| 화면 버전 | v1.2026.10.02.0942 | 운영자 육안 확인: v1.2026.10.02.0942 | 통과 |
| 감사 로그 03:35 봉 BUY 행 | `🟢 BUY \| Golden \| bar=286` | 운영자 육안 확인: 원래 판정으로 보임 | 통과 |
| 감사 로그 07:55 봉 BUY 행 | `🟢 BUY \| Golden \| bar=330` | 운영자 육안 확인: 원래 판정으로 보임 | 통과 |
| 결함 태그 (10:33:18 ~ 11:15:25) | 0 | ERROR 0, CRITICAL 0, database is locked 0. Bar# 10:35 ~ 11:15 5분마다 9봉 | 통과 |
| Traceback 3줄 | — | 모두 11:15:24 외부 스캐너의 `....//....//....//app/.streamlit/secrets.toml` 요청 1건이 "Missing file" 로 거부된 것 (`deploy/journal-traceback-scanner.txt`). 엔진 결함 아님 | 별도 집계 |

## 기준 행 조회 결과 (배포 전 · 관찰 후 · 접속 후)

| 시점 | 75021 (03:35 봉) | 75063 (07:55 봉) | 출처 |
|---|---|---|---|
| 배포 전 10:02:38 | ok=1, BUY_SIGNAL, `🟢 BUY \| Golden \| bar=286`, ts 03:40:12.157886 | ok=1, BUY_SIGNAL, `🟢 BUY \| Golden \| bar=330`, ts 08:00:12.017163 | `deploy/baseline-before.txt` |
| 기동 직후 10:04 | 같음 | 같음 | `deploy/snapshot-after-boot.tsv`, `deploy/snapshot-compare.txt` |
| 접속 후 11:15:50 | 같음 | 같음 | `deploy/baseline-after-access.txt` |

"관찰 후" 는 30분 종료 시각에 따로 조회하지 않았다. 기동 직후와 접속 후 조회가 모두 같고, 그 사이 이 두 봉의 행을 쓸 수 있는 경로(워밍업, 같은 봉의 실시간 판정)는 없었으므로 관찰 종료 시점 값도 같다.

접속 후에도 Upbit JTO 0, account_positions KRW-JTO 0.0 / 0.0 이다.

## 문서 정리

- 구현 보고 커밋(`786b5cb`)에 `wo19-impl-20261002.zip` 이 `git add -f` 로 잘못 들어갔다. 번들 zip 규칙(`docs/plans/*/*.zip` 커밋 제외)에 따라 이번 문서 커밋에서 추적을 뺐다 (`git rm --cached`, 로컬 파일은 유지).
- 엔진 코드는 바꾸지 않았다. 서버 pull 은 하지 않았다 (문서 커밋만 push).

## 묶음 목록

- `deploy-report.md` (이 문서), `report.md` (구현 보고)
- `deploy/journal-excerpt.txt` (기동 ~ 접속 확인, 10:03:17 ~ 11:16:00 주요 줄)
- `deploy/journal-traceback-scanner.txt`
- `deploy/observation-30min.txt`, `deploy/wo19d_obs.sh`
- `deploy/baseline-before.txt`, `deploy/baseline-after-access.txt`, `deploy/wo19d_pre.py`
- `deploy/snapshot-before.tsv`, `deploy/snapshot-after-boot.tsv`, `deploy/snapshot-compare.txt`, `deploy/wo19d_snap.py`, `deploy/wo19d_compare.py`
- `deploy/verify-seed.txt`, `deploy/deploy.txt`
- `deploy-commands.txt`, `deploy-git-log.txt`
