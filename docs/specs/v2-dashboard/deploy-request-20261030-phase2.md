# 신버전 대시보드 2차 배포 승인 요청서 (2026-10-30 초안 2판 — 새 전략·전환·엔진 제어 · 대상 = 배포 문서 커밋(8690639 + 이 요청서 등))

**한 줄:** 서버를 `1747fcc`(v1.2026.10.27.1522)에서 **배포 문서 커밋**(8690639 위에 이 요청서·Fable 질의·HANDOFF·B7 스크립트와 그 시험을 더한 커밋, 버전은 그 커밋에서 갱신)으로 올립니다. **이번에는 실매매 엔진(`tradebot`)을 1회 재시작하고, 엔진 기동 때 서버의 사용자 DB 전부(`services/data/tradebot_<user>.db` 중 이름이 비어 있지 않고 크기가 0 이 아닌 파일 — `engine/boot_resume.py:55-57`)에 표 3개·칸 2개·인덱스 1개가 생깁니다.** 활성 전략 파일은 `EMA` 그대로라, 투자자가 신버전에서 전환을 누르기 전까지 매매 판정은 바뀌지 않습니다. 새 전략(눌림목 분할매수)은 모의(TEST)에서만 켤 수 있습니다.
**근거:** 계획 `plan-phase2.md`(결정 1027-17) 8·10·11·12절, 2차 Task T1~T18 커밋(HANDOFF 0-1 1027-22~1030-07), 엔진 멈춤 경보 `docs/plans/2026-10-28-engine-recovery-fix/plan.md` 5.1~5.3(결정 1029-01·1029-02), 시간 밖 손절 허용(결정 1029-08, 1030-11), 바깥 호출 차단(1030-10), 사전 읽기 10/30 20:29(8절), verifier 3회(10/30, 3회째 승인 요청 가능), Fable `docs/fable/2026-10-30-phase2-deploy-request-1.md`(1회째 수정 후 진행 — 막음 2·권고 반영).
**실행:** 사용자 승인 뒤 PO(Claude)가 저장소 폴더 새 세션에서 SSH 로 실행합니다. 순서: 2-0 재측정 → 실행 직전 Fable 질의 1회(「진행」일 때만) → 2-1~2-8. `deploy-tradebot` 은 쓰지 않습니다(`/root/deploy.sh` 가 조건 없이 `systemctl restart tradebot` 을 실행한다는 1차 요청서 기재 — 2-0 에서 파일을 읽어 다시 확인).

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| P0 | 배포 전 DB 백업 + 기존 백업 권한 정리 | 크기가 0 이 아닌 `tradebot_*.db` 마다(빈 이름 `tradebot_.db` 포함) `/root/backup/<이름>_<YYYYMMDD>.db`(600). `services/data/backups/` 의 주간 백업을 644 → 600 | 백업 파일 삭제 |
| P1 | B7 마이그레이션 무손실 시험 | 서버 없음(P0 백업을 로컬 scratchpad 로 복사해 시험, 끝나면 로컬 사본 삭제) | — |
| P2 | `git pull --ff-only` (1747fcc → 배포 문서 커밋) | 커밋 28개 안팎, 198파일 안팎(2-0 에서 다시 셈). ★엔진 경로 26파일(1-1) | 3절 |
| P3 | `tradebot` 재시작 1회 (2-3 조건) | 새 엔진 코드, 기동 마이그레이션(사용자 DB 전부), 엔진 안 제어 감시 스레드 1개, 구버전 화면 버전·입장 단추 한 번 누르기(1027-04) | 3절 |
| P4 | `tradebot-v2` 재시작 (P3 기동 확인 직후) | 운용 탭 단추(전환·복귀·예약 취소·일시정지·엔진 시작/정지·강제 매수/매도·운용 설정 저장) 열림 — 전환·복귀·설정 적용은 모의만 | 같은 명령 / 3절 |
| P5 | 점검 `check_v2_unit.sh mcmax33`(T18 항목 포함) + DB 스키마 읽기 | 없음(읽기·탐침) | — |
| P6 | 운영자 브라우저 확인(1-A, 신버전 412·360·1440 + 구버전) | 없음 | — |
| P7 | 관찰 1시간 + 24시간 | 없음 | 기준 반박이면 3절 |
| P8 | 투자자 통보 문안 B 발송(배포 확인 뒤 운영자) | 없음 | — |

- **별도 승인(6절 4):** 운영자 전용 텔레그램 채널 키 `TELEGRAM_CHAT_ID_OPERATOR` 추가(값은 운영자가 직접 입력 — 서버 설정 변경). **어느 파일에 넣을지는 2-0 에서 정한다:** `config.py:9-16` 은 `.streamlit/secrets.toml` 에 `UPBIT_ACCESS` 가 있으면 `.env` 를 읽지 않고(`load_dotenv()` 가 `except KeyError` 안에만 있음), 알림 모듈은 환경 변수 → `st.secrets` 순으로 찾는다(`services/notifier.py:109-117`). 그래서 secrets.toml 에 `UPBIT_ACCESS` 가 있으면 secrets.toml 에, 없으면 `.env` 에 넣는다. 둘 다 엔진 기동 때 읽으므로 **P3 재시작 전에 넣어야 이번 재시작에 반영**된다. 넣지 않으면 엔진 멈춤 경보(1028-15)는 journal·`logs` 짧은 문구에만 남는다.
- 유닛 파일(`tradebot.service`·`tradebot-v2.service`)·nginx 는 바꾸지 않는다(`git diff 1747fcc 8690639 -- deploy/` 0줄, verifier 확인).
- 배포 전 체크리스트(project-rules): 회귀 게이트(8절 — 배포 문서 커밋에서 다시 돌린 수치를 그 커밋 전에 적음), 로그 수준 INFO(서버 현재본 `scripts/tradebot_boot.py:136`, 배포 뒤 코드는 `:181`, 새 로그 `[PULLBACK-*]`·`[CONTROL]` 은 `logger.info`/`warning`/`error` 만 — 2-0 에서 grep), 자동 재시작 tradebot `Restart=always`·tradebot-v2 `on-failure`, 비밀 파일 600, 감사 로그 백업(P0).

### 1-1. ★엔진 경로 파일 (1747fcc → 8690639, `git diff --name-status`, verifier 확인)
- 새 파일(A) 10: `core/engine_control.py`·`core/pullback_audit.py`·`core/safe_file.py`·`core/strategy_pullback.py`·`engine/control_requests.py`·`engine/pullback_apply.py`·`engine/pullback_params.py`·`engine/strategy_switch.py`·`services/pullback_state.py`·`services/trade_strategy.py`
- 바뀐 파일(M) 16: `app.py`·`core/position_state.py`·`core/strategy_engine.py`·`core/trader.py`·`engine/boot_resume.py`·`engine/engine_manager.py`·`engine/live_loop.py`·`engine/order_reconciler.py`·`engine/params.py`·`scripts/tradebot_boot.py`·`services/auto_verify.py`·`services/db.py`·`services/init_db.py`·`services/notifier.py`·`services/settings_history.py`·`services/terminology.py`
- 그 밖(8690639 까지): `pages/` 6·`ui/` 2·`v2/` 13·`scripts/`(손으로 돌리는 점검·시험 도구) 6·`tests/` 88·`docs/` 51·`.gitignore`·`.claude/` 1 = 합계 194. 배포 문서 커밋이 `scripts/v2/migration_dryrun.py`·`tests/regressions/test_r_2026_10_30_b7_migration_dryrun.py`·문서를 더한다.
- 새 파일은 모두 git 추적 파일이다(diff 에 A) — pull 로 함께 온다.

## 2. 실행 순서와 멈춤 조건
모든 서버 명령은 `cd /root/upbit-tradebot-mvp && ` 를 앞에 붙인다. 여러 줄 스크립트는 로컬 파일로 만들어 `ssh … 'bash -s' < 파일` 로 보낸다(셸 heredoc 금지). 운영 DB 직접 조회는 `sqlite3 -readonly` 만.

### 2-0. 정지선 (읽기 전용) — 8절 값(8절에 없는 항목은 아래에 적은 계획·이전 보고의 기대값)과 같아야 함
- 로컬 HEAD = origin/main = 배포 문서 커밋, 추적 변경 0(미추적 12건은 이전부터 있던 것 — 그대로 둠). `git diff --name-only 8690639 HEAD` 는 `docs/`·`scripts/v2/migration_dryrun.py`·`tests/regressions/test_r_2026_10_30_b7_migration_dryrun.py`·`pages/dashboard.py`(버전 줄)만.
- 서버 HEAD `1747fcc`, `dashboard.py:495` v1.2026.10.27.1522, tradebot active·`Mon 2026-10-26 00:25:22 KST`·NRestarts 0, tradebot-v2 active·`Tue 2026-10-27 16:47:19 KST`, 서버 미추적 5건, 디스크 여유 ≥ 5G(10/30 20G). `cat /root/deploy.sh`(쓰지 않는 이유 재확인), `.streamlit/config.toml` 의 `fileWatcherType`(1차 `"none"`).
- **사용자 DB 목록:** `ls -l services/data/tradebot_*.db`(이름·크기). 크기가 0 이 아닌 파일은 모두 P0 백업 대상이다. 그 가운데 이름이 비어 있지 않은 `tradebot_<user>.db` 만 B7·2-5 스키마 확인 대상이다(`engine/boot_resume.py:50-58·126-135` — 엔진은 빈 이름 `tradebot_.db` 를 빼고 기동 때 전부 마이그레이션. B7 스크립트도 빈 이름을 거부). 이하 「사용자 DB」는 이 뜻이다.
- 활성 전략 파일 3개(`mcmax33`·`gon1972`·빈 이름) 모두 `EMA`, `mcmax33_latest_params_PULLBACK.json` 0바이트·600, `*_applied_params_PULLBACK*` 없음(1028-04), `services/data/v2hist_*.db` 유무(1029-06 — 있으면 이름·크기만).
- 실매매 DB(사용자 DB 마다): `pullback_state`·`strategy_switch`·`schema_marks` 없음, 마이그레이션 직전 `audit_trades`·`orders` 의 `MAX(id)` 기록(2-5 표식 비교용). mcmax33: `audit_trades.meta` 있음, `BUY_FAILED_API` 행 4, `orders` 미체결(REQUESTED·PARTIALLY_FILLED) 0, `journal_mode` wal(1030-03·1028-08).
- 유닛(이전 확인값, 1028-16·1030-10): tradebot `User=root`·`UMask=0022`·`Restart=always`·`MemoryMax=infinity`, Environment 에 `PYTHONPATH`·`NETGUARD` 없음. tradebot-v2 `User=root`·`UMask=0077`·`Restart=on-failure`·`MemoryMax=157286400`·`StartLimitBurst=5`. 서버 python 3.12.8, `sqlite3` 3.37.2(경로 `/usr/bin/sqlite3`).
- `[RUN_MODE] UPBIT_MATCH`(1029-02, 계획 12절 22).
- 과거 엔진 멈춤 흔적(recovery 5.1): 예외 4종(`엔진 예외|run_live_loop 예외 발생|엔진 최종 실패|Unknown strategy type`) 전체 journal 0(10/30 확인)과 **D4 형태** — journal 의 `🚀 [RUN_MODE]` 줄(엔진 시작마다 찍힘, `engine/live_loop.py:1458`) 뒤에 `✅ [CONFIRMED] 봉 처리 완료`·`[CONFIRMED-NO-TRADE]` 줄이 이어지지 않고 정지 로그도 없는 구간. 엔진 시작 시각은 `mcmax33_engine_debug.log` 또는 `sqlite3 -readonly` `logs` 표의 `🚀 엔진 시작` 으로 보조 확인한다(1747fcc 는 이 줄을 journal 에 남기지 않고, `기동 준비 끝` 은 1747fcc 에 없음 — verifier 2회째). 10/30 19:22:23 의 `[RUN_MODE]` 재기동(프로세스 기동은 10/26 00:25:22 그대로)을 이 기준으로 본다: 그 뒤 봉 처리 줄이 이어졌는지, 원인이 운영자 정지·시작인지 자동 재개인지.
- EMA 조건 파일 `mcmax33_EMA_buy_sell_conditions.json` 의 `buy.fixed_price_buy_enabled` 참/거짓(키 이름과 값만, 계획 12절 18 — 10/30 사전 읽기는 최상위를 읽어 `None`, 2-0 에서 `buy` 아래를 다시 읽는다).
- 텔레그램·키 이름만(값 출력 없음): `.env` 와 `.streamlit/secrets.toml` 각각에 `UPBIT_ACCESS`·`TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`·`_WARNING`·`_CRITICAL`·`_OPERATOR` 이름이 있는지. 10/30 사전 읽기는 `TELEGRAM_CHAT_ID` 가 `.env` 에만 있고 나머지 셋은 두 파일 모두 없음. secrets.toml 에 `UPBIT_ACCESS` 가 있으면 엔진은 `.env` 를 읽지 않으므로 그때 엔진이 실제로 쓰는 채팅 키가 무엇인지 함께 판정한다. 6절 4 승인 뒤 `_OPERATOR` 가 엔진이 읽는 파일에 1. `WARNING` 이 없으므로 분류 불명 경고(1028-06)는 기본 채널로 간다 — 그 채널이 누구 채널인지 운영자 확인(1028-08).
- 비밀 파일 `.env`·`.streamlit/secrets.toml`·`.v2_secret`·`.v2_allowlist` 600 root, 사본 0. `.streamlit/config.toml` 에 `enableStaticServing` 줄 없음(=기본값 꺼짐, 10/30) — 줄이 생겼으면 값 확인.
- 지갑·보유(계획 10절 2): 마지막 `[POSITION-SYNC]`·`HTS_SELL` 줄(10/30 14:24:10 KRW-JTO `qty=1288`·`entry_price=504`)과 업비트 앱 지갑을 운영자가 확인.
- 기준선(배포 전 24시간, `journalctl -u tradebot -o cat`): **엔진 시세 실패 표지 11종**(1차 요청서 `deploy-request-20261027-proposal-match.md` 2-0 목록 — 「응답 없음」 4종 + 429 첫 증상 4종 + `[RECONCILE] 예외 발생`·`[REST-SAFE] 예외`·`[REST-SAFE] 빈 응답`) 0, 처리한 봉 합계·고유 봉 시각(10/30: 479·479), `insufficient_funds_ask` 건수(10/30: 0), 최근 1시간 `ERROR|Traceback|CRITICAL|database is locked` 수, `journalctl -u tradebot-v2` ERROR·Traceback 수·`status=429` 0.
- 하나라도 다르면 멈추고 보고한다.

### 2-1. 배포 전 (P0·P1)
1. 크기가 0 이 아닌 `tradebot_*.db` 마다 `sqlite3 -cmd ".timeout 5000" services/data/<이름>.db ".backup /root/backup/<이름>_<YYYYMMDD>.db"` → `chmod 600` → `ls -l`(크기) → `sqlite3 -readonly <백업> "PRAGMA integrity_check"` = ok. 디스크 여유가 3G 아래로 떨어지면 멈춤.
2. `chmod 600 services/data/backups/tradebot_*.db.backup_*` (project-rules 비밀 파일 권한 — DB 에 계정·거래 기록이 있음. 주간 백업 cron 이 다음에 644 로 만드는지는 7절 후속).
3. B7: 1 의 백업 중 사용자 DB(2-0 정의)를 `scp` 로 로컬 scratchpad 의 빈 폴더에 `tradebot_<user>.db` 이름으로 복사 → 저장소 폴더에서 사본마다 `time python3 scripts/v2/migration_dryrun.py <사본>`(로컬 실행. 스크립트가 services 를 불러오기 전에 바깥 연결 차단을 켜고, 비어 있는 로컬 업비트 키 자리에 자리표시 값을 넣고, 텔레그램을 끈다 — Fable 1030 막음 1, 시험 `test_cli_runs_with_empty_keys_env`. 실행 시간을 보고에 적는다 — 서버 기동 마이그레이션 시간의 참고값) — 엔진 기동과 같은 `ensure_all_schemas` + `close_strategy_revert_gap` 를 2회 돌려 기존 테이블 행 수·MAX(id)·칸 보존, 새 표 3개, 새 칸 NULL, 표식 = 전 MAX(id), `integrity_check`·`foreign_key_check` 전후, 2회째 무변화를 본다(`RESULT PASS`, 종료 코드 0). 출력은 테이블 이름·숫자만. 로컬 sqlite 는 3.54.0 이라 서버(3.37.2)와 판이 다르다 — 서버 판 차이는 2-5 스키마 확인으로 덮는다. 끝나면 로컬 사본 `<사본>*`(-wal·-shm 포함) 삭제. **하나라도 실패하면 배포 멈춤.**

### 2-2. P2 pull
- `git pull --ff-only` → `git rev-parse HEAD` = 배포 문서 커밋, `git status --short` 미추적 5건 그대로.
- pull 뒤에도 이미 불러온 엔진 모듈은 그대로다(엔진 프로세스 그대로). 그러나 **신버전 정적 파일(JS·CSS)과 구버전의 아직 한 번도 열지 않은 페이지는 새 파일을 읽는다**(Streamlit 스크립트 캐시는 이미 컴파일한 페이지만, tornado 정적 파일은 요청마다 디스크). 그래서 pull 은 P3 직전(같은 봉 간격 안)에 하고, P4 는 P3 기동 확인 직후 바로 한다. pull~P4 사이 신버전 화면은 새 JS 와 옛 API 가 섞여 오류가 날 수 있다(매매 무관).
- 예정 밖 엔진 재시작(`Restart=always`)이 pull 과 P3 사이에 나면 새 코드로 뜬다 — 그때는 바로 2-3 확인으로 간다.

### 2-3. P3 tradebot 재시작 (조건 모두 맞을 때)
- 조건: 현재 봉 `✅ [CONFIRMED] 봉 처리 완료` 또는 `[CONFIRMED-NO-TRADE]` 줄 확인 직후, 다음 3분봉 경계까지 60초 이상, journal `[RECONCILER]` 로 미체결 0, 최근 5분 `ERROR|CRITICAL` 0. 보유 중이어도 재시작한다(계획 10절 2 — `[BOOT-RESUME]`·`[POSITION-SYNC]` 로 복구).
- `systemctl restart tradebot` → 기동 확인: `[BOOT-RESUME] success`, `[migrate]` 줄(사용자 DB 마다 — 성공: `[migrate] added audit_trades.strategy_type`·`[migrate] added orders.strategy_type`·`[migrate] ensure_trade_strategy_columns OK`·`[migrate] close_strategy_revert_gap OK`. 멈춤: `[migrate] … 실패 — 기동 계속` 또는 `[BOOT-RESUME] 마이그레이션 실패` 1줄이라도 — 실패해도 기동은 계속되므로 이 문자열로 찾는다, `services/init_db.py:1176·1212·1250`, `engine/boot_resume.py:134`), `🚀 [RUN_MODE] UPBIT_MATCH`, `[WARMUP] REST 데이터 로드 완료` → **여기서 P4 로**. 그다음 첫 봉 2개: 보유 중이면 `[POSITION-SYNC]` 수량이 2-0 과 같음, 활성 전략 `EMA` 그대로 → `[CONFIG]`·EMA 판정 줄이 배포 전과 같은 형식, `[ENGINE-EXIT]` 0, `journalctl -u tradebot` 429·418 0.
- 기동 실패·`[migrate]` 실패·판정 줄 형식 다름 → 멈추고 3절 2.

### 2-4. P4 tradebot-v2 재시작
- `systemctl restart tradebot-v2` → active, `journalctl -u tradebot-v2` ERROR·Traceback 0, 세션 없는 API 401·403(1차 2-3 과 같음), 미리 받기 재개(`v2_candles/KRW-JTO_3.json` 갱신, `[V2-CANDLES]` 0줄).

### 2-5. P5 점검·스키마·3점
- `bash scripts/v2/check_v2_unit.sh mcmax33` — 기존 항목 + T18 5개(`v2-control-dir-700`·`files-600`·`applied-600`·`applied-not-writable-by-v2`·`results-readable`)·`unit-rw-paths-unchanged`. 새 항목은 대부분 「없음」이 정상(요청 폴더가 첫 요청 때 생김). 결정 1030-06 A 로 첫 모의 전환 입회 뒤 1회 더(7절). 서버 ReadWritePaths 출력 형식·EROFS 는 이 첫 실행에서 확인(1030-07).
- DB 스키마(`sqlite3 -readonly`, 사용자 DB 마다): 새 표 3개, `PRAGMA table_info(pullback_state)` 24칸(1028-05·계획 T6), `audit_trades`·`orders` 의 `strategy_type` 칸, `schema_marks` 의 `…strategy_type.legacy_max_id` 2행이 각각 2-0 에서 기록한 MAX(id) 이상(표식 = 마이그레이션 순간의 MAX(id), `services/init_db.py:1170-1173`). 표식보다 큰 id 행 중 `strategy_type` 이 NULL 인 행이 있으면 그 행의 type·reason 을 적고 journal 의 분류 불명 경고(1028-06)와 대조한다(멈춤 조건 아님 — 전략 없이 쓰는 행은 정상으로 NULL 일 수 있음).
- 3점: 로컬 HEAD·버전 / 서버 HEAD·파일 버전·**구버전 화면 버전(이번 재시작으로 대상 커밋 버전으로 바뀜)** / tradebot·tradebot-v2 ExecMainStartTimestamp. 보고에 「버전: v1.2026.10.27.1522 → <대상 버전>」(화면은 2058 → <대상 버전>).

### 2-6. P6 운영자 확인 (강력 새로고침)
- 신버전 412·360·1440: 운용 탭 단추·안내 줄(1차 안내 앞 문장 삭제·추가 단추 3개, 1029-07), 「시간 밖에도 익절」 바꿀 수 있음(1030-11), 저장 창 단추 흐름(1029-06), 홈 회차·예약 배지·로그 새 줄·차트 긴 선·가짜 ▼ 없음(1030-03).
- 구버전: 입장 단추 한 번 누르기(1027-04), 활성 전략 EMA 일 때 화면이 배포 전과 같음, 감사 로그 뷰어·설정 페이지 이동·강제 매수·매도 단추가 맨 위에 그대로(화이트리스트).
- **사용자 관점에서 사라지거나 바뀌는 것:** 신버전 차트의 거절·취소 행 ▼「매도」 표시가 없어짐(1030-02 U2 — EMA 사용자도), 신버전 로그 「다시 시드」 → 「지표 다시 계산(그동안 매수 없음)」(U4). 그 밖의 잠금·안내는 새 전략 운용·예약 중에만 보인다.

### 2-7. P7 관찰
- 1시간(project-rules 워크플로 8, 첫 봉 20개): 판정 줄 형식, 엔진 시세 실패 표지 11종 0, 확정 봉 누락 0, `journalctl -u tradebot` ERROR·Traceback·CRITICAL·`database is locked`·`[ENGINE-EXIT]` 0, 429·418 0, tradebot-v2 ERROR 0·`status=429` 0.
- 운영자 엔진 정지 → 시작 1회(recovery 5.2): `[ENGINE-EXIT]` 0, Reconciler 정지·기동 로그 1회씩, 실계좌 사용자가 한 명이면 정지 때 Reconciler 가 멈춤. 텔레그램이 오면 문구·채널(운영자 채널인지)·dedupe 확인. **보유 중이면 이 시험은 보유가 없을 때로 미룬다.**
- 24시간(`journalctl -u tradebot`·`-u tradebot-v2`): 실패 표지 11종 0, 처리한 봉 고유 수 ≥ 478, `[ENGINE-EXIT]` 0, 첫 판정·체결가를 배포 전 형식과 비교(1028-13). 실패 표지가 늘거나 봉이 줄면 보고(엔진 보호 우선 — 3절 판단).

### 2-8. 완료 보고
- 3점·「버전: 구 → 신」, 마이그레이션 줄, B7 결과, 점검·스키마 출력, 운영자 확인, 1시간 결과. deploy-report + Fable 번들 zip. 보고 문서·HANDOFF·notice-log 는 다음 문서 커밋(승인 별도, 버전 갱신).

## 3. 되돌리기 (계획 10절 7을 엔진 정지 시간이 짧게 고친 순서)
1. **신버전만 끊기(가장 빠름):** `systemctl stop tradebot-v2` — 요청 파일로 엔진에 주문·전환·정지를 시키는 통로가 닫힌다. 엔진·구버전 영향 없음. 이미 써 둔 요청은 60초 안에 엔진이 처리할 수 있으므로(`engine/control_requests.py:82` `REQUEST_TTL_SEC = 60`) 60초 기다린 뒤 `services/data/v2_control/<user>/` 에 `req-*.json` 이 없는지 본다.
2. **엔진 코드 되돌리기:** 엔진을 멈춘 채 커밋·승인·push 를 하지 않는다(그동안 실계좌 EMA 보유분의 손절·익절이 멈춤).
   ① 새 전략 미보유 확인(지갑) 또는 운영자 수동 청산. ② 활성 전략 파일 `EMA` 확인(다르면 신버전 복귀 단추, 또는 운영자가 파일 도구로 `EMA` 를 씀). ③ **로컬에서 되돌림 커밋을 먼저 만든다**(버전 갱신, 되돌리기 승인 범위) → push. ④ 서버: `systemctl stop tradebot` → DB 백업(2-1 1) → `python3 scripts/v2/mark_revert.py <user>`(사용자 DB 마다 — 운영 DB 쓰기 1회, `schema_marks` 행 2개. **종료 코드 0 이면 진행, 1·2·3·4 이면 멈추고 보고** — 2 = DB 없음·마이그레이션 전) → `git pull --ff-only` → `systemctl start tradebot` → `tradebot-v2` 재시작 → 2-3·2-4 점검. 엔진 정지 구간은 백업·기록·pull 몇 분이다. **`mark_revert.py` 실행은 되돌리기 승인 범위에 함께 넣어 승인받는다.**
3. 새 표·칸은 남긴다(옛 코드는 읽지 않음 — `test_revert_old_code_ignores_new_schema`).

## 4. 영향
| 축 | 바뀌는 것 | 위험 | 막는 장치 |
|---|---|---|---|
| 매매(EMA, 지금 운용) | 활성 파일 EMA 그대로 → 판정 무변경. ★엔진 경로 26파일(1-1) 전부가 같은 프로세스에서 돔 | 기동 실패·판정 형식 변화 | 회귀 게이트 EMA 판정 고정, 2-3 확인, 3절 2 |
| 재시작 | tradebot 재시작 1회 | 재시작 중 봉 누락, 보유분 복구, pull~P4 사이 화면 혼재 | 2-3 조건(봉 직후·60초·미체결 0), BOOT-RESUME·POSITION-SYNC, pull 을 P3 직전·P4 를 기동 직후 |
| 데이터 | 사용자 DB 전부에 표 3·칸 2·인덱스 1(IF NOT EXISTS·열 추가만) | 마이그레이션 실패·손실 | P0 백업(DB 마다), B7(DB 마다), 되돌리기 무해성 시험, 2-5 스키마 확인 |
| 업비트 한도 | 새 전략 워밍업 최대 약 11회(전환·적용 때만), 이번 재시작 워밍업 1회(EMA 801봉) | 신버전 수집과 겹쳐 429 | 1차 장치 그대로(4회/초·경계 창·429 멈춤), 2-7 관찰. 업비트 공식 한도 문서는 이번에 다시 읽지 않음(계획 12절 3) |
| 프로세스 | 엔진 안 제어 감시 스레드 1개(2초) | 스레드 예외가 엔진에 번짐 | 예외 격리 시험, 한 번에 하나 |
| 자격증명·권한 | 키를 읽는 곳 추가 없음. 신버전이 요청 파일로 엔진에 주문·전환·정지를 시킬 수 있음 | 신버전 침해 시 요청 파일만으로 강제 매매·정지(남는 위험 S1) | 세션 user·입장 모드·60초 만료·한 번에 하나, 금액은 엔진이 정함, 요청 종류별 텔레그램, 실계좌 전환·복귀·설정 적용은 엔진이 거절, `systemctl stop tradebot-v2` |
| 알림 | 엔진 멈춤 경보(운영자 채널), 분류 불명 경고 | 키가 엔진이 읽는 파일에 없으면 journal 에만 남음 | 6절 4, 2-0 키 이름 확인 |
| 투자자 화면 | 운용 탭 단추 열림, 구버전 입장 한 번 누르기, 신버전 차트 가짜 ▼ 없어짐 | 새로고침 전 옛 화면 | 5절 통보 |

## 5. 투자자 통보 문안 B (배포 확인 뒤 운영자 발송, 계획 10절 초안을 1030-06 메모·verifier 1회째대로 고침)
> 투자자님, 신버전 대시보드 2차 공개를 오늘 마쳤습니다.
>
> 이제 신버전 운용 메뉴에서 「백테스터 규칙으로 전환」, 「기존 전략으로 복귀」, 「예약 취소」, 그리고 설정 저장 창의 「이 설정으로 동작」을 쓰실 수 있습니다. **새 전략 「눌림목 분할매수」는 지금은 모의 투자에서만 쓸 수 있습니다.** 실계좌로 들어오시면 운용 메뉴의 전환·복귀·운용 설정 저장 단추는 닫혀 있고, 설정 저장 창의 「이 설정으로 동작」은 설정을 저장한 뒤 전환 확인 창이 뜨고, 확인하시면 「새 전략 전환·복귀는 아직 실계좌(LIVE)에서 할 수 없어 처리하지 않았습니다. 엔진은 그대로입니다.」 안내가 나옵니다. 승인 요청서 6절의 규칙(보유 중이면 기존 방식으로 판 뒤 전환)대로 동작합니다.
>
> 지금 매매 방식은 바뀌지 않았습니다. 투자자님이 전환을 확인하실 때만 새 전략이 시작됩니다.
>
> 승인 요청서와 다르게 정한 점이 있습니다.
> - 새 전략으로 코인을 보유 중이거나 전환 예약 중일 때는 로그인해도 운용자산이 바뀌지 않습니다. 1회 매수 금액(운용자산 ÷ 최대 횟수)이 거래 도중 바뀌지 않게 하기 위해서입니다. 보유가 없을 때는 지금처럼 로그인 때 원화 잔고로 다시 정해집니다.
> - 감시 구간(60선이 200선 위, 200선 상승)이면 켠 직후에도 「가격이 60선 아래로 내려왔다가 다시 위에서 마감할 때」 1회차를 살 수 있습니다. 골든크로스 순간의 1차 매수는 다음 골든크로스를 기다립니다. 백테스터와 똑같이 동작합니다.
> - 업비트에서 확정된 봉을 받지 못하는 드문 경우에는 그 봉을 판정에 쓰지 않으므로, 익절·손절 판정이 다음 확정 봉까지 늦어질 수 있습니다.
> - 새 전략의 매수 주문이 실패하면 3봉 동안 다시 주문하지 않습니다(봇 매도가 체결되면 바로 풀립니다).
> - 신버전 운용 메뉴의 「시간 밖에도 익절」을 끄면, 거래 시간 밖에는 익절만 미루고 손절·데드크로스 매도는 바로 합니다.
> - 새 전략으로 보유 중일 때는 봉 단위를 바꾸거나 분할 매수 횟수를 늘릴 수 없습니다. 「보유 중에는 … 바꿀 수 없습니다 — 매도 뒤 다시 적용해 주세요」 안내가 나옵니다(줄이는 것은 바로 됩니다).
> - 모의 투자로 새 전략을 쓰시는 동안 실계좌로 로그인하시면 모의 지갑이 실계좌 잔고로 바뀌어 새 전략의 추가 분할매수가 멈출 수 있습니다(고칠 예정이며, 실제 자산과는 무관합니다).
>
> 새 전략 운용 중이거나 전환 예약 중에 기존 대시보드를 여시면 설정 저장·전략 변경·엔진 시작이 잠기고, 「파라미터 설정」·「설정 History 복원」·「시스템 초기화」도 함께 잠깁니다. 서비스 재시작 뒤 엔진 자동 재개는 그대로 됩니다(보유분 익절·손절이 끊기지 않게 하려는 것이며, 예약 중이면 봇 추가 매수는 막힙니다). 모의 투자에 예약이 있을 때 실계좌 기존 화면에서는 「엔진 실행하기」와 파라미터 설정 이동은 쓰실 수 있고, 설정 저장·시스템 초기화만 잠깁니다. 강제 매수·매도, 엔진 정지, 감사 로그는 그대로 쓰실 수 있습니다. 기존 대시보드의 「강제 매수」는 새 전략의 회차 밖 매수로 다루어, 그 뒤 새 전략의 추가 분할매수가 멈추고 익절·손절만 적용됩니다(신버전 운용 메뉴의 「강제 매수」는 회차 1회로 셉니다). 새 전략이 켜진 상태에서 실계좌로 기존 대시보드에 들어오시면 「새 전략은 모의 투자에서만 씁니다」 안내가 나오고 화면이 멈춥니다. 이때는 이 화면의 실계좌 강제 매도도 할 수 없으니 업비트 앱에서 파시거나 모의 투자로 들어오세요.
>
> 그 밖에 바뀐 점: 기존 대시보드의 「신버전 대시보드 입장」은 이제 한 번만 누르시면 됩니다. 신버전 차트에 거절·취소된 주문이 「매도」 표시로 보이던 것을 고쳤습니다. 화면이 이상하게 보이면 새로고침(PC 는 Ctrl+Shift+R 또는 Cmd+Shift+R)해 주세요.
>
> 투자자님이 따로 하실 일은 없습니다.

- 보낸 뒤 `docs/operations/investor-notice-log.md` 에 한 줄 기록(투자자 연락 원칙 — 체감 변경 통보).
- 넣지 않은 것: 같은 봉 익절·손절 동시 → 손절 매도와 감사 칸 `SELL:TP` 표식(운영자 메모, 1030-11), 종목 기호 규칙 축소(1029-06 「통보 안 함」), 엔진 멈춤 경보(운영자만), 신버전 로그 문구 「지표 다시 계산」(U4 — 화면 글자만), 1028-02 PO 결정 2건(앱 매도 직후 재매수 없음·보유 불일치 때 매수 막음 — 새 전략 모의 전용, 6절 5).

## 6. 결정 항목
1. P0~P7 실행: **한 번에(권고 — 멈춤 조건이 없으면 2-7 1시간 관찰까지)** / 단계별.
2. 실행 세션: **저장소 폴더 새 세션(권고)** / 이 세션.
3. 사용자 DB·B7: **크기가 0 이 아닌 `tradebot_*.db` 전부 백업하고, 엔진이 마이그레이션하는 사용자 DB(빈 이름 제외) 사본마다 B7(권고 — 기동 마이그레이션이 전부 바꿈)** / mcmax33 만 하고 나머지도 바뀐다는 것만 승인 범위에 적기.
4. 운영자 채널 키 `TELEGRAM_CHAT_ID_OPERATOR`: **2-0 키 이름 확인 뒤 엔진이 읽는 파일(secrets.toml 또는 .env)에 P3 전 운영자가 직접 추가(권고 — 이번 재시작에 반영, 값은 Claude 가 보지 않음)**. 1차 24시간에 `[NOTIFY] sent` 줄이 있고 `TELEGRAM_CHAT_ID` 가 `.env` 에만 있으므로 엔진은 `.env` 를 읽는 것으로 추론된다(추정 — 2-0 에서 확정) / 나중에(다음 엔진 재시작까지 경보는 journal 에만).
5. 문안 B: **위 문안대로 배포 확인 뒤 운영자 발송(권고 — 1029-12 한 줄 포함, U4·1028-02 는 넣지 않음)** / 고쳐서.
6. 「이 설정으로 동작」 실계좌 처리: **문안만 실제 동작(저장 뒤 엔진 거절 안내)에 맞춤(권고 — 배포 범위를 늘리지 않음)** / save.js 에서 실계좌일 때 단추를 닫는 코드 수정(별도 구현·검증·승인, 배포 늦어짐).
7. 서버에서 회귀 게이트 실행(1028-13): **돌리지 않음(권고 — 로컬 게이트 + B7, 서버에서 새 코드를 미리 돌리지 않음)** / 서버에서 돌림.
8. 배포 전 문서 커밋: **이 요청서·Fable 질의·HANDOFF·B7 스크립트·시험을 커밋 1개(버전 갱신)로 커밋·push 하고 그 커밋을 배포(권고 — 1차와 같은 방식, 서버 HEAD = GitHub HEAD. 문서·시험 커밋이지만 버전을 올리는 것은 배포 커밋 = 서버 화면 버전을 맞추기 위해서다)**. 커밋은 경로를 지정해 `git add` 하고, 로컬 미추적 파일(커밋 대상 밖 `tests/test_*.py` 7·`docs/analysis/…` 4·`.superpowers/`)은 그대로 둔다 / 8690639 를 배포(B7 스크립트는 미커밋으로 로컬 실행).

### 사용자 결정 1030-13 (2026-10-30 21시대)
- 원문: 「1030-13 승인: 1~8 권고대로」
- 1 한 번에 · 2 저장소 폴더 새 세션 · 3 사용자 DB 전부 백업·B7 · 4 운영자 키는 2-0 판정 뒤 P3 전 운영자가 직접 추가 · 5 문안 B 대로 배포 확인 뒤 운영자 발송 · 6 문안만 맞춤 · 7 서버 게이트 안 돌림 · 8 문서 커밋 1개(버전 갱신)를 배포 대상으로.
- 10/30 19:22 엔진 재기동을 직접 했는지는 답이 없었다 → 2-0 에서 journal 로 확인.

## 7. 후속 항목
- 첫 모의 전환은 운영자 입회 권고(계획 10절 5): `[PULLBACK-PARAMS] source=applied`, `[CONTROL] switch done`, 워밍업 봉 수 = `required_bars`+1, 첫 판정 줄. 입회 뒤 `check_v2_unit.sh` 2회째(1030-06 A).
- `tests/regressions/baseline_commits.py:60` `REVERT_OLD_CODE_COMMIT = "1747fcc"` 를 2차 배포 커밋으로 갱신(배포 뒤 다음 코드 커밋, 1030-06).
- 1029-12(모의 지갑 덮어쓰기)·1028-18(자동 재시작 2단계)은 이 배포 뒤 계획부터.
- 주간 백업 cron 이 644 로 만드는지 확인·수정(2-1 2 의 후속, 별도 승인).
- 운영 DB 원본 `tradebot_mcmax33.db` 도 644(8절). 600 으로 바꿀지는 v2 읽기·cron 영향 확인 뒤 별도 승인(이번 범위 아님).

## 8. 사전 읽기 결과 (2026-10-30 20:29 KST, 사용자 실행 읽기 전용 스크립트 2개) · 로컬 게이트
| 항목 | 값 |
|---|---|
| 서버 HEAD·버전 | 1747fcc · v1.2026.10.27.1522, 미추적 5 |
| tradebot | active · 10/26 00:25:22 · NRestarts 0 |
| tradebot-v2 | active · 10/27 16:47:19 · NRestarts 0 |
| 1차 24시간(10/27 16:47~10/28 16:47) | 실패 표지 11종 0, 봉 합계 481·고유 480, v2 오류·429 0 → 1026-06 통과 |
| 그 24시간 ERROR/CRITICAL 줄 | `[SELL-LIVE] insufficient_funds_ask`(앱 지정가 묶임, 1027-12) 1, `[NOTIFY] sent kind=CRITICAL dedupe=fixed_buy_req:…`(INFO 줄 안 글자) 1, `[SETTINGS-SNAPSHOT] database is locked` WARNING 1(17:11:03, 1차 보고 기재) |
| 지금 24시간 | 실패 표지 0, 봉 479·479, `insufficient_funds_ask` 0 |
| 활성 전략 | 3개 모두 EMA, PULLBACK 파일 0바이트·600 |
| mcmax33 DB | 새 표 없음, `audit_trades.meta` 있음, BUY_FAILED_API 4, 미체결 0, wal, 1,043,705,856B |
| 백업 | `services/data/backups/` 10/18·10/25 (644), `/root/backup/` 있음 |
| 유닛 | tradebot root·0022·always·infinity / v2 root·0077·on-failure·157286400·5, PYTHONPATH·NETGUARD 없음 |
| RUN_MODE | UPBIT_MATCH (10/26 00:25:30, 10/30 19:22:23) |
| 과거 엔진 예외 4종 | 전체 journal 0 |
| 마지막 지갑 동기화 | 10/30 14:24:10 KRW-JTO qty=1288 · entry 504 |
| 텔레그램 키 | CHAT_ID `.env` 에만, WARNING·CRITICAL·OPERATOR 두 파일 모두 없음 |
| 기타 | python 3.12.8, `/usr/bin/sqlite3` 3.37.2, 디스크 20G, enableStaticServing 줄 없음, 로그 수준 INFO(:136) |
| 로컬 게이트(8690639 + B7 파일, 10/30) | 회귀 1161/1161(B7 시험 4건 포함) · v2 433 · JS 165, rc 0, 바깥 연결 차단 켜짐. 배포 문서 커밋 직전에 한 번 더 돌린다 — 그 뒤 B7 시험이 5건(빈 키 CLI 시험 추가)이 되어 기대 회귀 합계는 1162 |
