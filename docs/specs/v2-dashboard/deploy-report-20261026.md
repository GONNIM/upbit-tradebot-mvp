# 신버전 대시보드 배포 완료 보고 (1차 10/25 + 2차 10/26)

**한 줄:** 신버전 대시보드가 서버에서 `5367334`(v1.2026.10.25.2058)로 돌고 있습니다. 투자자 화면에 입장 버튼이 다시 보입니다. 엔진은 10/26 00:25:22 에 한 번 재시작했고 매매 경로 코드는 바뀌지 않았습니다.

**서버 실행본 = `5367334`(v1.2026.10.25.2058).** 이 보고를 넣은 문서 커밋 뒤에는 GitHub HEAD 의 버전 줄이 이 값과 달라집니다. 문서만 바뀐 커밋이라 서버 pull 은 하지 않습니다.

버전: v1.2026.10.25.1729 → v1.2026.10.25.2058 (2차 배포. 1차는 v1.2026.10.20.1711 → v1.2026.10.25.1611 → v1.2026.10.25.1729)

## 1. 3점 일치 (10/26 00:31 KST)
| 점 | 값 | 근거 |
|---|---|---|
| 로컬 | HEAD `5367334`, `pages/dashboard.py:495` v1.2026.10.25.2058 | `git rev-parse HEAD`, origin/main 같음 |
| 서버 | HEAD `5367334`, `pages/dashboard.py:495` v1.2026.10.25.2058 | SSH `git rev-parse HEAD`, `grep -n v1.2026` |
| 엔진 | `tradebot` ExecMainStartTimestamp `Mon 2026-10-26 00:25:22 KST`, NRestarts 0 | `systemctl show tradebot` |

`tradebot-v2` 는 active 이고 기동 시각은 `Mon 2026-10-26 00:24:59 KST` 입니다.

## 2. 1차 배포 (10/25, 요청서 `deploy-request-20261025.md`, 결정 1025-10·1025-11·1025-12)
| 단계 | 결과 | 근거 |
|---|---|---|
| D1 pull | 156b351 → 12ddb4f(1611) | 출발점 `deploy-request-20261025.md:30`, 결과 `deploy-stop-1.md:9`, 서버 reflog 17:09:49 |
| D2 비밀 파일 | `.v2_secret` 32바이트 600, PULLBACK 0바이트 600 | 같은 파일 사실 2 |
| D3 엔진 재시작 | 17:10:35, BOOT-RESUME success, 결함 태그 0 | 같은 파일 사실 3 |
| D4 v2 기동 | 127.0.0.1:8502, MemoryMax 150M | 같은 파일 사실 4 |
| D5 점검 | FAIL 1(root-writable) → 멈춤 | 같은 파일 사실 5·6 |
| D5 처리 | `ProtectHome=read-only` 커밋 5692998(1729), 엔진 재시작 없음 | 결정 1025-11·1025-12, `docs/fable/2026-10-25-protecthome-apply-1.md` |
| D5~D8 재개 | v2 재시작 17:48:27(17:47:49 포함 2회), nginx `/v2/`, 허용 목록, cron | 계획 `protecthome-apply-1.md:4`, 결과 서버 journal·`HANDOFF.md:12` |
| 화면 확인 | 18:26 운영자 PC 확인에서 시안과 달라 중단, 18:41:55 허용 목록 비움 | `ui-mismatch-1.md:10`, `hide-entry-1.md:48`, 결정 1025-14 |

- 1차 종료 시 3점: 서버 HEAD `5692998`·파일 버전 1729, 실행 중 프로세스는 `12ddb4f` 코드·화면 버전 1611, tradebot 17:10:35. 이 어긋남은 10/26 00:25:22 엔진 재시작으로 풀렸습니다(현재 화면 2058).

- 1차 D5~D8 의 세부 출력은 그 세션의 보고에만 있고 저장소에 원문이 없습니다. 10/26 00시대 읽기 전용 재확인은 다음과 같습니다.
  - nginx `sites-available/tradebot` 에 `location /v2/` 있음, `sites-enabled` 링크 유지.
  - crontab 에 v2hist 백업 줄(`30 11 * * 0 …`) 있음.
  - tradebot-v2 enabled, ProtectHome=read-only, MemoryMax=157286400.
- 1차 통보 문안 A 는 화면 재작업으로 보내지 않았습니다.

## 3. 2차 배포 (10/26, 요청서 `deploy-request-20261025-2.md`, 결정 1025-24)
| 단계 | 결과 | 시각 |
|---|---|---|
| 2-0 정지선 | 모든 항목이 기재와 같음 | 00:13 |
| 검증 | verifier 반박 0 「S1 착수 가능」, Fable 「진행」(권고 3) | 00:14~00:22 |
| S1 pull | 5692998 → 5367334, 33개, 금지 경로 0 | 00:24:49 |
| S2 v2 재시작 | active, Traceback 0, 엔진 기동 시각 17:10:35 그대로 | 00:24:59 |
| S3 엔진 재시작 | 00:21 봉 `✅ [CONFIRMED]` 00:24:11 뒤, 미체결 0, 남은 98초 | 00:25:22 |
| S3 5분 확인 | 아래 3-1 | 00:28~00:30 |
| S4 점검 | 아래 3-2 | 00:30~00:31 |
| S5 허용 목록 | `.v2_allowlist` 600 root 8바이트, 서버 미추적 5건 그대로 | 00:31 |
| S6 운영자 확인 | 사용자 「1025-13 확인함」 | 00:50 이전 |
| S6 매매 중지/재개 | 아래 3-3 | 00:55:20~00:55:41 |
| S6 30분 관찰 | 아래 3-4 | 00:25:22~00:55:49 |

### 3-1. S3 5분 확인 (출처 `journalctl -u tradebot`)
- `[BOOT-RESUME] success user=mcmax33 mode=LIVE elapsed=6.8s` 1회, `[BOOT] run_live_loop start` 1회(00:25:30).
- 워밍업 REST 801봉, 시드 long_history, 감사 행 보존 kept=168.
- 재시작 뒤 첫 봉(00:24)은 `[CONFIRMED-NO-TRADE]`(00:28:16)이었습니다. 다음 봉 00:27 이 `✅ [CONFIRMED] 봉 처리 완료` 00:30:11(경계 11초 뒤)로 정상 처리됐습니다.
- 결함 태그(pos_desync_promoted·integrity_gap·first_bar_guard·SKIP-BAR·POLLUTED) 0, Traceback·CRITICAL·ERROR·`database is locked` 0, `[ENGINE-ALIVE]` 0.
- `services/data/.engine_alive.json` `-rw------- root`, `.tmp` 잔존 없음. 10초 간격 2회 읽기에서 `at` 이 00:28:44 → 00:28:54 로 바뀌고 `running.mcmax33` true, `pid` 2702287 = MainPID.

### 3-2. S4 점검
- `check_v2_unit.sh mcmax33`: 13항목 모두 PASS(unit-props·live-db-ro-read·live-db-write-lock·v2hist-write·active-strategy-read·env/secrets/credentials-inaccessible·root-readonly·proc-environ-blocked·pullback-open·no-upbit-env·pullback-inode-match). FAIL 0이라 재실행하지 않았습니다. `proc-environ-readable` RESIDUAL 은 나오지 않았습니다(proc-environ-blocked PASS).
- 탐침 뒤 `users` 는 `mcmax33|0` 그대로입니다.
- RSS: tradebot-v2 30,324KB(기준 102,400 이하), tradebot 177,340KB.
- EXPLAIN 7개: 모두 인덱스 SEARCH, `USE TEMP B-TREE` 0.
- 세션 없는 API: `/v2/api/basic` 401, Origin 없는 POST 403 `forbidden_origin`, Origin 있는 POST 401 `unauthorized`, `/v2/static/backtester.html` 200.

### 3-3. 매매 중지/재개 1회 시험 (결정 1025-24 2)
- 조건: KRW-JTO 포지션 0, 미체결 0, 00:51 봉 `✅ [CONFIRMED]` 00:54:10 뒤. 운영자에게 00:55:50 전 재개를 안내했습니다.
- `logs` 에 `⏸️ 매매 일시중지 (사용자 요청)` 00:55:20, `▶️ 매매 재개 (사용자 요청)` 00:55:41. 중지 시간은 21초입니다.
- 시험 뒤 `journalctl -u tradebot` `[PAUSE]` 0, `audit_buy_eval` 의 paused 표시 행 0(failed_keys·checks·notes), `trading_paused` 0.
- 다음 봉 00:54 가 `✅ [CONFIRMED]` 00:57:10 으로 정상 처리됐습니다.
- tradebot-v2 journal ERROR·Traceback 0, 사용 뒤 RSS 30,944KB.

### 3-4. 30분 관찰 (00:25:22~00:55:49, 출처 `journalctl -u tradebot`)
- 확정 봉 10개(00:24~00:51) 모두 처리: `✅ [CONFIRMED]` 6, 무거래 5줄(00:45 봉이 2줄). 놓친 봉 0.
- Bar# 201 → 206.
- 429·418 0, 결함 태그 0, ERROR·Traceback·CRITICAL·locked 0, `[ENGINE-ALIVE]` 0, `[PAUSE]` 0.
- `.engine_alive.json` `at` 00:55:47(관찰 끝 2초 전), running true.
- tradebot-v2 journal ERROR·Traceback 0.
- RSS: tradebot 222,816KB(재시작 상한 1,400MB), tradebot-v2 31,332KB. NRestarts 0, `trading_paused` 0.

## 4. 관찰한 것 (배포와 무관)
- 00:45 봉에서 `⏰ [CLOCK-CLOSE] 봉 확정 감지` 가 00:48:00 과 00:48:05 에 두 번 났습니다. 두 번 모두 무거래 봉으로 건너뛰어 지표에 반영되지 않았고 매매 영향이 없습니다.
- 같은 중복이 배포 전 옛 프로세스에서도 10/24 04:21·06:42, 10/25 06:15 봉에 있었습니다(`journalctl` 10/24 이후 `uniq -d` 4건). 이번 diff 에 엔진 매매 경로 변경은 0 입니다. 원인 조사는 백로그로 넘깁니다.
- 00:42 봉은 REST 봉 미반영 재시도 17회(약 85초) 뒤 ticks 체결 0건으로 NO_TRADE 확정됐습니다. 기존 Progressive Retry 동작입니다.

## 5. 이 보고 커밋에서 함께 고친 문서
- `docs/operations/v2-runbook.md:111` 「배포 점검 때 한 번만 실행한다」 → 「배포 점검 때 한 번 실행한다(탐침이 엔진 쓰기와 우연히 겹쳐 FAIL 이면 1회 재실행 허용, 두 번 다 FAIL 이면 멈춤)」.
- `docs/specs/v2-dashboard/plan-pc-basic-20261025.md:98` 「tradebot 기동 시각 그대로(엔진 재시작 없음)」 뒤에 「— 8-1 채택(결정 1025-21 가)으로 tradebot 1회 재시작, 2차 배포 요청서 S3」 주석.
- `docs/specs/v2-dashboard/HANDOFF.md` 0-1 진행 표.

## 6. 남은 일
| # | 할 일 | 누가 | 끝 기준 |
|---|---|---|---|
| 1026-04 | 투자자 통보 문안 A′ 발송 | 운영자 | 보낸 뒤 `docs/operations/investor-notice-log.md` 한 줄 |
| 1026-06 | 24시간 journal 확인(결정 1025-10 4) | Claude | 10/27 00:25 이후 tradebot·tradebot-v2 오류 0, 놓친 봉 0 |
| 1026-07 | CLOCK-CLOSE 중복 원인 조사(백로그) | Claude | 별도 승인 |

## 7. 근거 파일
- 요청서: `docs/specs/v2-dashboard/deploy-request-20261025.md`, `docs/specs/v2-dashboard/deploy-request-20261025-2.md`
- Fable: `docs/fable/2026-10-25-deploy-request-1.md`, `-deploy-exec-1.md`, `-deploy-stop-1.md`, `-protecthome-fix-1.md`, `-protecthome-apply-1.md`, `-ui-mismatch-1.md`, `-hide-entry-1.md`, `-deploy-request2-1.md`, `docs/fable/2026-10-26-deploy2-exec-1.md`, 이 보고 질의 `docs/fable/2026-10-26-deploy-report-1.md`
- 번들 zip(근거 보강용): `report.md`(이 보고), `verifier-exec-20261026.md`(실행 직전 판정표), `verifier-report-20261026.md`(이 보고 검증 요지), `d3_restart.sh`·`explain7.sql`·`observe30.sh` 원문, `commands.txt`(실행 명령 원문), `outputs.txt`(S3·S4·시험·30분 관찰 출력 원문).
- zip 경로 `docs/specs/v2-dashboard/v2-deploy-report-20261026.zip`(git 무시). 크기·`unzip -l` 원문은 사용자 보고에 적습니다(zip 안의 이 파일은 자기 zip 크기를 담을 수 없음).
- 이 보고 커밋에서 `pages/dashboard.py` 버전 줄도 갱신합니다(project-rules 커밋 전 2단계, 요청서 2-6). 서버는 pull 하지 않으므로 GitHub HEAD 가 서버보다 1커밋 앞섭니다.
