# 신버전 대시보드 2차 배포 완료 보고 (2026-11-01 — 새 전략·전환·엔진 제어)

**한 줄:** 서버를 `1747fcc`(v1.2026.10.27.1522)에서 `f73ec4b`(v1.2026.10.30.2230)로 올렸습니다. 실매매 엔진 `tradebot` 은 14:21:19 에, `tradebot-v2` 는 14:21:31 에 각각 1회 재시작했습니다.
- 기동·마이그레이션·1시간 관찰·운영자 브라우저 확인은 통과했습니다.
- 운영자 정지→시작 시험은 **조건부**입니다. 16:45 1회차에서 정지한 옛 매매 루프가 아직 끝나지 않았는데 새 루프가 떠서, 두 루프가 **24초 동안 함께 돌았습니다**. 보유 0·무거래 봉이라 주문은 없었습니다(2-4절).
- 원인 코드는 이번 배포 전부터 있던 것입니다(2025-11 `a67c9d5`·`40f15b1` 계열). 신버전 시작 요청은 살아 있는 옛 루프를 보고 거절하지만, 구버전 시작 단추는 확인하지 않습니다. 16:46 시작이 구버전 단추였습니다.

**근거:**
- 요청서: `deploy-request-20261030-phase2.md`
- 결정: 1030-13 「1~8 권고대로」, 1031-02(키는 `.env`), 1101-01(운영자 키 넣음), 1101-02(브라우저 확인함), 1101-03(정지·시작함, 알림 옴)
- 실행 직전 Fable 질의: `docs/fable/2026-11-01-phase2-deploy-exec-1.md`, 판정 「진행」(권고 5건)
- 완료 보고 검증: verifier 2회 「수정 후 승인」 → 이 판에 반영

버전: v1.2026.10.27.1522 → v1.2026.10.30.2230 (서버 파일 `pages/dashboard.py:523` 기준. 구버전 화면 버전도 2058 → 2230 — 이번 엔진 재시작으로 반영, 화면은 사용자 확인)

**서버 실행본 = `f73ec4b`(v1.2026.10.30.2230).** 이 보고를 넣은 문서 커밋 뒤에는 GitHub 의 파일 버전이 서버 2230 과 달라집니다. 문서만 바뀐 커밋이라 서버 pull 은 하지 않습니다(의도된 불일치 — 다음 세션 정지선에서 멈추지 않음).

## 1. 3점 일치 (11/01 14:22 KST, verifier 17:04 재확인)
| 점 | 값 | 근거 |
|---|---|---|
| 로컬 | HEAD `f73ec4b`, `pages/dashboard.py:523` v1.2026.10.30.2230 | `git rev-parse HEAD` |
| 서버 | HEAD `f73ec4b`, `pages/dashboard.py:523` v1.2026.10.30.2230 | evidence/06, 07 |
| 엔진 | `tradebot` ExecMainStartTimestamp `Sun 2026-11-01 14:21:19 KST`, NRestarts 0 | evidence/07, 09, 10 |

- `tradebot-v2` 는 active, ExecMainStartTimestamp `Sun 2026-11-01 14:21:31 KST`, NRestarts 0.
- 16:45·16:58 의 정지→시작은 프로세스 안에서 매매 루프만 바꾼 것이라 기동 시각은 그대로입니다(evidence/10, 11).

## 2. 실행 결과
| 단계 | 결과 | 시각 |
|---|---|---|
| 2-0 정지선 | 기대값과 다른 것 5건 → 멈추고 원인을 확인한 뒤 Fable 질의로 진행(아래 2-0절) | 13:43 |
| 2-0 운영자 키 위치 | 엔진 유닛 `EnvironmentFile=.env (ignore_errors=no)` → `.env` 에 넣음(3절 1) | 10/31~11/01 |
| 실행 직전 Fable | 「진행」, 권고 5건 반영 | 11/01 |
| 2-1 P0 백업 | DB 4개 백업, 모두 integrity ok, 600 root. 주간 백업 600 정리 | 13:54 |
| 2-1 B7 | default·gon1972·mcmax33 모두 RESULT PASS, rc 0 | 13:5x |
| 운영자 키 | `.env` 600 root, 키 줄 1, 비어 있지 않음, 형식 이상 줄 0(넣기 전·후), 사본 0 | P3 전 |
| 2-2 pull | 1747fcc → f73ec4b `--ff-only`, 미추적 5 그대로 | 14:21:14~17 사이 |
| 2-3 tradebot 재시작 | 봉 처리 직후, 경계까지 166초, 미체결 0, 최근 5분 오류 0, JTO 0 | 14:21:17 |
| 2-3 기동 | 마이그레이션 3 DB OK, BOOT-RESUME success(LIVE 7.8초), 워밍업 완료, 실패 줄 0, 엔진 프로세스 환경에 운영자 키 이름 1 | 14:21:19~31 |
| 2-4 v2 재시작 | active, 오류 0 | 14:21:31 |
| 2-5 점검 | `check_v2_unit.sh mcmax33` 19/19 PASS rc 0, 스키마·응답 확인(2-2절) | 14:22 |
| 첫 봉 2개 | Bar#201·202 HOLD, 배포 전 Bar 줄과 같은 형식, EMA 이어짐 | 14:24·14:27 |
| 2-6 운영자 확인 | 사용자 「1101-02 확인함」(1027-04 입장 단추 포함) | 16시대 |
| 2-7 1시간 관찰 | 모두 기준 통과(2-3절) | 14:21~15:21 |
| 2-7 정지→시작 시험 | **조건부** — 1회차 루프 겹침 24초, 2회차 통과(2-4절) | 16:45·16:58 |

### 2-0. 정지선에서 기대값과 달랐던 것 (evidence/01, 02, Fable 질의 사실 6·11~15)
| 항목 | 요청서 기대 | 실측 | 판단 |
|---|---|---|---|
| 지갑 | 10/30 14:24 JTO qty=1288 | 13:41 JTO 0 | 아래 체결 7건 + 앱 추가매수 1건으로 설명됨 |
| MAX(id) mcmax33 | 10/31 00:09 정지선 값 audit 1464 · orders 638 | 1470 · 643 | 같은 매매로 늘어남 |
| 사용자 DB 목록 | default 없음 | `tradebot_default.db` 204,800B 있음 | 마이그레이션 대상에 넣고 백업·B7 |
| 주간 백업 | 10/18·10/25 (644) | 11/01 11:00 새 파일(644) | P0 chmod 로 함께 600 |
| 24시간 봉 | 10/30 479·고유 479 | 482·고유 480 | 무거래 봉 확정 줄 중복(같은 봉 2줄)로 봄 |

- 체결 7건 + 앱 추가매수 1건(10/30 19:12 ~ 11/01 13:12, evidence/02):
  - 10/30 19:12 STALE_POSITION 시장가 매도 2272.33 @494
  - 19:44 강제 매수(audit `force_buy`) @499
  - 10/31 00:27 매도 @506
  - 07:18 매수 @508
  - 09:12 매도 @514
  - 11/01 00:51 매수 @509
  - 13:11:39 앱 추가매수(HTS_BUY_ADD) 뒤 13:12:08 STALE_POSITION 전량 968.59 @505 매도
  - 모두 FILLED, 13:41 보유 0.
- 그 밖의 2-0 항목:
  - 10/30 19:22 재기동은 운영자 조작입니다(logs 표 19:20:01 「파라미터 설정을 위해 엔진 자동 종료됨」). D4 는 없습니다.
  - `buy.fixed_price_buy_enabled = True`.
  - 기준선 err_1h 1 은 13:12:07 `[NOTIFY] sent kind=CRITICAL` INFO 줄입니다.
  - 활성 전략 3개는 모두 EMA 입니다.
  - 봉 간격 minute3: 서버 params 파일 grep(출력은 보관하지 않음)과 journal 봉 처리 3분 간격(16:46:08 `timeframe=minute3 interval=180sec`)으로 확인했습니다.
- 사실 12·13(10/30 19:12 매도·지갑 대조)의 출처는 `stopline_1031c.sh` 출력 = evidence/02 입니다(Fable 권고 5).

### 2-1. P0 백업과 B7 (evidence/03, 04)
- 백업:
  - `/root/backup/tradebot__20261101.db` 4,284,416B
  - `tradebot_default_20261101.db` 204,800B
  - `tradebot_gon1972_20261101.db` 450,560B
  - `tradebot_mcmax33_20261101.db` 1,061,654,528B
  - 모두 `-rw-------` root, `integrity_check` ok. `.backup` 은 `timeout 900` 으로 감쌌습니다(Fable 권고 4). 백업 뒤 디스크 19G.
- 주간 백업(`services/data/backups/`)을 600 으로 정리했습니다. 11/01 11:00 cron 이 새로 만든 파일도 644 여서 함께 바꿨습니다. cron 은 계속 644 로 만듭니다(5절).
- B7(`scripts/v2/migration_dryrun.py`, 로컬 사본, 바깥 연결 없음):
  - default 1.13초, gon1972 1.09초, mcmax33 16.76초. 모두 RESULT PASS·rc 0.
  - mcmax33 표식 audit_trades 1470·orders 643(= 마이그레이션 전 MAX(id)).
  - evidence/04 는 마지막 80줄이라 default 블록의 이름 줄이 잘렸습니다(행 0·순서로 default).
  - 로컬 사본은 끝난 뒤 삭제했습니다.

### 2-2. 재시작 뒤 확인 (evidence/06, 07, 08)
- pull 직전 MAX(id): default 0/0, gon1972 0/0, mcmax33 audit 1470 / orders 643.
- 마이그레이션 줄: DB 마다 `added audit_trades.strategy_type`, `added orders.strategy_type`, `ensure_trade_strategy_columns OK`, `close_strategy_revert_gap OK` — 3 DB × 4 = 12줄.
- 스키마(`sqlite3 -readonly`): 3 DB 모두 같습니다.
  - 새 표 3개(pullback_state·strategy_switch·schema_marks), pullback_state 24칸
  - strategy_type 칸 1/1, 표식 = pull 직전 MAX(id), 표식 뒤 NULL 행 0
  - quick_check ok
- 신버전 응답: 세션 없는 API 401, POST pause Origin 없음 403·있음 401, `ops.js` 200·no-cache.
- 점검 19항목 가운데 T18 5항목은 `(absent)` 입니다. 요청 폴더가 아직 없어 실제 쓰기 거부 동작은 첫 모의 전환 뒤 2회째 점검에서 봅니다(5절).
- 새 WARNING: `[SWITCH] 모의가 아닌 엔진 … 건너뜀(실계좌는 전환 미지원)` 2줄 — 실계좌 엔진의 예상 동작입니다. `[PHASE2] Redis/WebSocket 기능 비활성화` 는 배포 전에도 있던 줄입니다(재시작 전 구간 1건).
- 첫 봉:
  - 재시작 전 마지막 Bar#781(14:18 봉, ema_fast 506.03) → Bar#201(14:21 봉, 506.10) → Bar#202(14:24 봉, 506.16).
  - 모두 HOLD·pos=False, Bar 줄 형식이 같습니다.
  - 요청서 2-3 의 `[CONFIG]` 줄 형식 비교는 하지 않았습니다(Bar 줄만 비교).
- v2 시세 미리 받기 파일 `KRW-JTO_3.json` 이 14:26:32 에 갱신됐습니다.

### 2-3. 1시간 관찰 (14:21:17~15:21:46, evidence/09, 11)
| 항목 | 기준 | 결과 |
|---|---|---|
| 시세 실패 표지 11개 문자열 | 0 | 모두 0 |
| ERROR·CRITICAL·Traceback·database is locked | 0 | 0 |
| ENGINE-EXIT | 0 | 0 |
| 429·418 (엔진·v2) | 0 | 0 / 0 (15:21:46 뒤 엔진 0 도 확인) |
| v2 ERROR·Traceback | 0 | 0 |
| 처리한 봉 | 빠짐 없음 | 14:21~15:21 21개 연속(3분 간격) |
| 서비스 | active·NRestarts 0 | 둘 다 그대로 |
| JTO 보유 | — | 0 |

- 봉은 `봉 처리 완료` 와 `CONFIRMED-NO-TRADE`(거래 없는 봉, 배포 전과 같은 처리)를 함께 셌습니다.
- 집계 시각 15:21:46 에 19개였던 이유: 15:18 봉이 무거래 확정 재시도 끝에 15:22:31 에 처리되어 집계 범위 밖이었습니다. 15:24:30 까지 다시 세면 21개가 연속입니다(evidence/11).

### 2-4. 운영자 엔진 정지→시작 시험 — 조건부 (evidence/10, 11)
**1회차 (16:45~16:46, 신버전 정지 → 구버전 시작) — 매매 루프 2개가 24초 겹침**
- 16:45:28 신버전 `engine_stop` 요청 → 16:45:33 `[OR] stopped`, `[CONTROL] … status=done code=stopped` → 16:45:34 `v2_control` WARNING 알림.
- 그런데 옛 매매 루프는 그 봉(16:42)의 REST 확정 재시도(`[RECONCILE] 봉 미반영`, 16:45:05~16:46:26, 17줄) 중이었습니다. 정지 신호는 루프 머리(`engine/live_loop.py:1688`)에서만 보고, 한 바퀴 안의 확정 재시도 함수는 정지 신호를 받지 않습니다(`core/rest_reconcile.py:608-613`·:656-667). 그래서 재시도가 끝날 때까지 돌았습니다(코드 확인).
- 16:46:04 `[OR] started` → 16:46:07 `engine_start` 알림 → 16:46:08 새 `[BOOT] run_live_loop start` → 16:46:15 메인 루프 진입.
- 16:46:32 옛 루프가 16:42 봉을 무거래로 확정한 뒤에야 `run_live_loop 종료` 했습니다. **16:46:08~16:46:32 동안 두 루프가 함께 돌았습니다.**
- 주문·체결: orders id>643 0건, audit_trades id>1470 0건. 보유 0·무거래 봉이라 주문 신호가 없었습니다.
- 실제 위험: 새 루프는 다음 봉 경계(16:48)까지 판정하지 않습니다(`live_loop.py:1692-1693`). 그래서 가까운 위험은 「옛 루프가 늦게 낸 주문을 새 루프의 포지션 상태가 모르는 것」입니다(다음 `[OR] periodic sync` 60초까지). 같은 봉을 두 루프가 모두 처리하는 일은 옛 루프 한 바퀴가 3분을 넘을 때만 생깁니다.
- 원인(코드):
  - `stop_engine` 은 관리 스레드(`engine_runner_*`)만 10초 기다립니다(`engine/engine_manager.py:449`).
  - 관리 스레드는 정지 신호를 보면 작업 스레드(`run_live_loop_*`, 실제 매매 루프, :628-634)를 2초만 기다립니다(`WORKER_JOIN_SEC`, :168·:671). 그 뒤 등록부에서 지우고 잠금을 풀고 끝납니다(:691-692).
  - 그래서 작업 스레드가 살아 있어도 `_start_engine_internal`(:400-406, 관리 스레드만 봄)과 사용자 잠금이 다음 시작을 막지 못합니다.
  - :449 뒤에 관리 스레드 생존만 확인하는 고침으로는 막을 수 없습니다. 작업 스레드 생존을 확인해야 합니다.
  - 같은 구조는 배포 전 `1747fcc` 에도 있습니다(:258 join, :480 잠금 해제). 449 줄은 `a67c9d5`(2025-11-16)·`dfd0ed4`(2026-01-17), 452-456 줄은 `40f15b1`(2025-11-23)에서 왔고, 2차 T11(`1c79fa6`)은 mode 인자만 더했습니다.
- 이번 배포와의 관계:
  - **신버전 시작 요청은 이미 막혀 있습니다.** 살아 있는 옛 루프(`threading.enumerate()` 로 `run_live_loop_*`·`engine_runner_*` 이름을 찾음)가 있으면 `old_engine_alive` 로 거절합니다(`engine/control_requests.py:716-720·733-734`). 전환·복귀는 옛 스레드가 끝날 때까지 30초 기다립니다(:826-855).
  - **구멍은 구버전 시작 단추**(`pages/dashboard.py:663` → `start_engine`)와 `start_engine` 자체입니다. 16:46:04 시작이 구버전 단추였기 때문에 겹쳤습니다.
  - 구버전 정지·시작 단추로도 생기는 원래 있던 위험입니다. 고침 후보는 `_stale_threads` 와 같은 검사를 `_start_engine_internal` 에 넣는 것입니다(계획·승인은 별도).
  - 신버전만 끊는 롤백(3절 1단계)은 오히려 이 거절 장치를 닫고 구버전 단추는 남기므로 위험을 줄이지 않습니다.
- 고치기 전 임시 규칙: 정지 뒤 **3분 이상** 기다린 뒤 시작합니다. 가능하면 시작은 **신버전 단추로** 합니다(옛 루프가 살아 있으면 거절됨).
  - 근거: 한 바퀴 대기 상한(HTTP 시간 제외)은 무거래 경로 약 97초, 실패 경로 약 129초입니다. 지터 5초 + 확정 재시도 최대 17회×5초 + RETRY 5+8+10초 등입니다.
  - 과거 봉 대조에서 불일치가 나면 1건마다 최대 30초가 더 붙습니다(`rest_reconcile.py:656-667·951-962`, Fable 계산).
  - 이번 관측은 81초였습니다.

**2회차 (16:58, 구버전 정지 → 구버전 시작) — 통과**
- 시험 전 16:47: JTO 보유 0, 15:21 뒤 오류 0, NRestarts 0.
- 16:58:00 `run_live_loop 종료 (LIVE)` → 16:58:01 `[OR] stopped` → 16:58:02 `[NOTIFY] sent kind=CRITICAL dedupe=engine_stop:mcmax33` → 16:58:09 `[OR] started` → 16:58:10 `[BOOT] run_live_loop start mode=LIVE strategy=EMA` → 16:58:11 `engine_start:mcmax33` 알림 → 16:58:14 메인 루프 진입.
- 16:47~17:01 집계: ENGINE-EXIT 0, 오류 0, OR 정지 1·시작 1, 정지 알림 1·시작 알림 1(중복 없음).
- 재시작 뒤 첫 봉: 17:00:10 Bar#201(16:57 봉) HOLD·pos=False, ema_fast 506.67.

**알림 채널:**
- 구버전 단추의 `engine_stop`·`engine_start` 알림(`pages/dashboard.py:2556-2563`·`:673`)은 받는 곳을 지정하지 않습니다. 그래서 `TELEGRAM_CHAT_ID_CRITICAL` 이 없는 지금은 기본 채널(`TELEGRAM_CHAT_ID`)로 갑니다(`services/notifier.py:182-187`).
- 사용자 「알림 옴」은 기본 채널 수신입니다.
- 운영자 채널(`TELEGRAM_CHAT_ID_OPERATOR`)은 엔진 예외 종료 경보 등(`engine/engine_manager.py:526-534`)에서만 씁니다. 실제 발송은 **아직 시험하지 않았습니다**. 엔진 프로세스 환경에 키 이름이 있는 것까지만 확인했습니다.
- 신버전 정지는 `engine_stop` 알림 없이 `v2_control` WARNING 1건만 보냅니다.

**함께 본 것 (원인 미확인):**
- 16:46·16:58 시작 직후 `[AUDIT-UPDATE] BUY 실시간 재판정` 이 각각 148줄 찍혔습니다(오늘 00:51~13:09 봉의 `audit_buy_eval` 실시간 칸 UPDATE, `services/db.py:1205-1207`, 08-22 `3b76e02` 코드). 14:21 재시작·10/30 19:22 시작에는 0줄입니다.
- 매매 행(audit_trades·orders)은 바뀌지 않았습니다. 왜 이번에만 찍혔는지는 확인하지 않았습니다(5절).
- 신버전 v2 journal 의 `[V2-CANDLES] engine generation changed — pause 300s` 2줄(16:46:34·17:06:34)은 엔진 세대 값이 바뀐 것을 v2 가 감지한 줄입니다(`v2/candles.py:310-315`). 17:06:34 는 16:58:10 재기동보다 8분 24초 늦게 나왔습니다(감지 주기 원인은 미확인). 24시간 관찰에서는 「직전 엔진 재기동 뒤 첫 감지 1줄」을 예상 동작으로 봅니다.

## 3. 요청서와 다르게 한 것
1. **운영자 키를 넣은 파일:** 요청서 1절은 「secrets.toml 에 `UPBIT_ACCESS` 가 있으면 secrets.toml」로 정했습니다(업비트 키는 실제로 secrets.toml 에 있음, evidence/01). 그러나 2-0 에서 `systemctl show tradebot -p EnvironmentFiles` 가 `.env (ignore_errors=no)` 를 보여 주었습니다. 엔진 프로세스는 `.env` 값을 systemd 환경 변수로 받고, 알림 모듈은 환경 변수를 먼저 읽습니다(`services/notifier.py:97,110`). 그래서 `.env` 에 넣었습니다(사용자 1031-02). 재시작 뒤 엔진 프로세스 환경에 키 이름이 있음을 확인했습니다(값은 보지 않음, evidence/05·06).
2. **회귀 게이트:** 결정 1030-13 의 7번대로 서버에서 돌리지 않았습니다. 배포 커밋 `f73ec4b` 직전 로컬 게이트는 회귀 1162/1162 · v2 433 · JS 165 입니다(커밋 메시지).
3. **Fable 권고 1:** 「간격 grep 을 서버에서 다시」는 Fable 이 잘못 읽은 것입니다. 2-0 에서 서버 params 파일로 이미 돌렸고 minute3 이었습니다. journal 근거는 2-0절에 적었습니다.
4. **2-0 정지선:** 기대값과 다른 5건이 있었습니다. 요청서대로 멈추고 원인을 확인한 뒤 Fable 질의 「진행」을 받아 넘어갔습니다(2-0절).
5. **2-7 정지→시작:** 요청서 기준 「`[ENGINE-EXIT]` 0, Reconciler 정지·시작 각 1, 운영자 채널 수신」 가운데 운영자 채널 수신은 확인하지 못했습니다(기본 채널로 감). 1회차에서 기준에 없던 루프 겹침이 나왔습니다(2-4절).

## 4. 남은 것
| # | 할 일 | 조건 |
|---|---|---|
| 24시간 관찰 | 실패 표지 0, 처리 봉 고유 ≥ 478, ENGINE-EXIT 0, 429·418 0 | 11/02 14:21 이후 |
| 루프 겹침 | 작업 스레드(`run_live_loop_*`) 생존 확인을 `start_engine` 에 넣는 계획. 고치기 전에는 정지 뒤 3분 이상, 시작은 신버전 단추 | 사용자 결정 |
| 운영자 채널 | 실제 발송 확인 방법 | 사용자 결정 |
| 1101-04 | 통보 문안 B 발송 → `investor-notice-log.md` 기록 | 운영자 발송 뒤 |
| 1031-05 | 기본 텔레그램 채널 주인·앱 JTO 수량 | 사용자 답 |

## 5. 후속 (요청서 7절 + 이번에 나온 것)
- 운영자 입회 첫 모의 전환과 그 뒤 `check_v2_unit.sh` 2회째(T18 실제 동작).
- `tests/regressions/baseline_commits.py:60` 의 `REVERT_OLD_CODE_COMMIT`(지금 `1747fcc`)를 배포 커밋으로 갱신.
- 주간 백업 cron 이 파일을 644 로 만듭니다. 고치려면 별도 승인이 필요합니다.
- 운영 DB 파일 자체(`services/data/tradebot_*.db`)는 644 입니다(`/root` 700). 기록만 합니다.
- `start_engine` 이 작업 스레드 생존을 확인하게 하기(위 2-4절) — 계획·승인 별도.
- 시작 직후 `BUY 실시간 재판정` 148줄 원인 확인.
- 11/01 13:11:39 앱 추가매수 29초 뒤 STALE_POSITION 이 앱 매수분까지 전량 매도했습니다. 배포와는 무관하지만 투자자 클레임 소지가 있습니다. 1031-05 답과 함께 따로 봅니다.
- 1029-12·1028-18 은 이 배포 뒤 계획할 수 있습니다.

## 6. 관찰 방법 메모
- 서버 명령은 모두 scratchpad 스크립트를 `ssh … 'bash -s' <` 로 보내거나 한 줄 `ssh` 읽기로 실행했습니다.
- 운영 DB 는 `sqlite3 -readonly` 와 P0 의 `.backup`(읽기)만 썼습니다. PO 스크립트는 서버에 임시 파일을 만들지 않았습니다(P0 백업 파일 제외). `check_v2_unit.sh` 는 요청서대로 `systemd-run` 임시 유닛으로 탐침합니다.
- 키 값은 어느 출력에도 나오지 않습니다. 개수·형식·이름만 셌습니다.
- evidence/02 에는 주문 UUID 가 들어 있습니다(키 아님). zip 은 커밋하지 않습니다(`.gitignore` `docs/specs/*/*.zip`).

## 7. Fable 검산 번들
- 경로: `/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/v2-phase2-deploy-report-20261101.zip`
- 크기: 38,141 바이트, 24개 항목(report.md + evidence 11개 + commands.txt + scripts 9개). zip 속 report.md 는 이 7절의 숫자와 2-4절 `engine_manager.py` 줄 번호 3곳(Fable 2회차 권고)을 고치기 전 판입니다. 그 밖의 본문은 같습니다.
- `unzip -l` 요약: report.md 20142 · evidence/01~11(11번 1977) · evidence/commands.txt · evidence/scripts/(p0_backup·p2p4_run·p3_bars·p5_check·p7_1h·stopline_1031·1031b·1031c·wait_bar) — 합계 89,707 바이트.
