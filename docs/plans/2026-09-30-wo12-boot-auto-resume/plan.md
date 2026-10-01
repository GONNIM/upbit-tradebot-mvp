# WO-12 계획서 — 서비스 기동 시 엔진 자동 재개 + 마이그레이션 기동 시점 실행 (초안)

- 작성일: 2026-09-30
- 상태: **승인 완료 (C1~C7), 로컬 구현·검증 완료, 배포 승인 대기** — 결과는 8절, 배포 절차는 9절
- 근거: `docs/plans/backlog.md` WO-12 항목
- 기준 코드: 서버·로컬 HEAD `d41e943` (v1.2026.09.30.1746)

---

## 0. 한 줄 요약

지금은 `tradebot.service`가 다시 시작되면, 누군가 대시보드에 접속할 때까지 엔진이 멈춰 있습니다. 서비스가 뜨는 즉시 마지막 LIVE 엔진을 자동으로 다시 켜고, 마이그레이션도 그때 한 번 실행하며, 결과를 텔레그램으로 알립니다. 대시보드 첫 접속 경로와 두 번 켜지지 않도록 잠금을 둡니다. 매매 판정 로직은 바꾸지 않습니다.

## 1. 현황 (실측)

### 1.1 엔진 정지 시간

| 재시작 | 서비스 시작 | 엔진 재개 (첫 접속) | 정지 |
|---|---|---|---|
| 2026-09-18 | 16:40:32 | 17:26:32 | 약 46분 |
| 2026-09-30 WO-9·11 | 16:28:08 | 16:33:05 | 약 5분 |
| 2026-09-30 WO-10 | 17:55:43 | 18:02:06 | 약 6분 |

### 1.2 왜 첫 접속까지 멈추는가

- 자동 재개 코드는 대시보드 페이지 스크립트 안에 있습니다(`pages/dashboard.py:395~` `[AUTO-RESUME]`). Streamlit 은 누군가 페이지를 열어야 스크립트를 실행합니다.
- 엔진 스레드는 Streamlit 서버 프로세스 안에서 돕니다(`engine/engine_manager.py:525` 모듈 전역 `engine_manager`).
- 엔진 시작 함수가 세션 상태에 기대고 있습니다.
  - `current_mode()`(`engine/engine_manager.py:46`)는 `st.session_state["mode"]`를 읽습니다.
  - LIVE 자동 재개 안전 조건 `upbit_verified`, `live_capital_set`(`pages/dashboard.py:405~407`)도 세션에만 있습니다(`app.py:74, 79, 383, 388`).
- 스키마 마이그레이션(`ensure_all_schemas`)도 로그인·대시보드 로드 때만 실행됩니다(`app.py:280`, `pages/dashboard.py:705`).

### 1.3 서비스를 다시 시작시키는 주체

| 주체 | 조건 | 실적 |
|---|---|---|
| 배포 (`systemctl restart tradebot`) | 사람이 실행 | 배포마다 |
| `/root/monitor_tradebot_memory.sh` (cron 10분) | 메모리 1,400MB 초과 | 기록 시작(2026-02-23) 이후 3회, 마지막 2026-03-12 |
| systemd `Restart=always` | 프로세스 비정상 종료 | 기록 없음 (별도 확인 필요) |
| `/root/cleanup_tradebot_db.sh` | 주 1회 | 재시작 제거됨 (2026-05-31 이후) |

- 현재 방어: `/root/watchdog_tradebot_engine.sh`(cron 5분)가 최근 30분 Bar# 로그가 없으면 `🚨 [STALE]` 텔레그램을 보냅니다. 즉 새벽 재시작이면 **최대 30분 뒤 알림**만 가고, 사람이 접속할 때까지 손절을 포함한 매매가 멈춥니다.

## 2. 설계 방향

### 2.1 선택지

| 안 | 방법 | 판단 |
|---|---|---|
| A | systemd `ExecStartPost` 에서 `curl` 로 페이지 호출 | 불가. Streamlit 은 웹소켓 세션이 있어야 스크립트를 돌립니다. HTTP 요청만으로는 실행되지 않습니다. |
| B | 헤드리스 브라우저로 대시보드 접속 | 로그인·세션 흉내가 필요하고 깨지기 쉽습니다. 비권장. |
| C | 엔진을 Streamlit 과 분리한 별도 프로세스로 | 근본 해결이지만 대규모 구조 변경입니다. 이번 범위 밖. |
| **D (제안)** | **Python 기동 스크립트가 같은 프로세스 안에서 ① 기동 스레드로 자동 재개를 실행하고 ② `streamlit.web.bootstrap.run` 으로 서버를 띄운다** | 엔진 스레드와 대시보드가 같은 프로세스·같은 `engine_manager` 를 공유합니다. 변경이 작습니다. |

### 2.2 D 안 구성

1. **기동 스크립트** `scripts/tradebot_boot.py` (신설)
   - 기동 스레드를 시작한 뒤 `streamlit.web.bootstrap.run("app.py", …, flag_options={server.port: 8501, server.address: "0.0.0.0"})` 로 서버를 띄웁니다.
   - systemd `ExecStart` 를 `venv/bin/python scripts/tradebot_boot.py` 로 바꿉니다(서버 설정 변경 — 승인 항목 C1).
2. **기동 재개 함수** `engine/boot_resume.py` (신설) `boot_resume_all()`
   - `ensure_all_schemas(user_id)` 를 먼저 실행합니다(마이그레이션 기동 시점 실행).
   - 대상: `engine_status` 가 실행 중이었고 `last_mode == "LIVE"` 인 사용자.
   - 안전 조건(세션 대신 기동 시점 실측):
     - Upbit 키 조회 전용 검증 — `get_balances()` 성공
     - 운용자산 — KRW + 보유 코인 평가가 0 보다 큼 (세션의 `live_capital_set` 대응)
   - 둘 중 하나라도 실패하면 재개하지 않고 CRITICAL 알림을 보냅니다. DB 상태는 바꾸지 않습니다(첫 접속 경로가 기존대로 판단).
   - `trading_paused` 는 건드리지 않습니다. 정지 상태면 엔진은 돌되 주문은 기존대로 스킵합니다.
3. **세션 비의존 시작 경로** `engine/engine_manager.py`
   - `start_engine(user_id, test_mode=None, restart_count=0, *, mode: str | None = None)` — `mode` 가 주어지면 `current_mode()`(세션) 대신 그 값을 씁니다. 기존 호출은 그대로 동작합니다.
4. **이중 실행 잠금**
   - `EngineManager` 에 사용자별 `threading.Lock` 을 두고, `start_engine` 진입부에서 잠금 안에서 `is_running` 을 다시 확인합니다. 이미 실행 중이면 `True` 를 돌려주고 새로 켜지 않습니다.
   - 기동 재개가 끝나면 `engine_status_thread` 가 참이 되므로, 대시보드 `[AUTO-RESUME]` 블록(`pages/dashboard.py:398` 조건 `not engine_status_thread and engine_status_db`)은 자연히 건너뜁니다.
   - 로그: `[BOOT-RESUME] start|skip|success|fail user=… reason=…`, 대시보드 경로가 건너뛰면 `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)`.
5. **재개 결과 알림**
   - 성공: INFO `🔄 서비스 기동 — LIVE 엔진 자동 재개 (user, 전략, 기동→재개 소요 초)`
   - 실패·보류: CRITICAL `🚨 서비스 기동 — LIVE 엔진 자동 재개 실패 (사유: 키 검증 실패 / 운용자산 0 / 예외)` + "대시보드 접속 시 수동 확인" 안내
   - dedupe 키 `boot_resume:{user}:{결과}`, TTL 600초

### 2.3 바꾸지 않는 것

- 매매 판정, 필터, 발주, `trading_paused` 처리
- 대시보드의 기존 `[AUTO-RESUME]` 코드 (잠금 뒤 보조 경로로 남깁니다)
- watchdog `[STALE]` 알림 (기동 재개 실패 시 최종 안전망)

## 3. 변경 파일

| 파일 | 내용 |
|---|---|
| `scripts/tradebot_boot.py` (신설) | 기동 스레드 + `streamlit.web.bootstrap.run` |
| `engine/boot_resume.py` (신설) | `boot_resume_all()` — 마이그레이션, 대상 선정, 안전 조건, 재개, 알림 |
| `engine/engine_manager.py` | `start_engine(..., mode=None)`, 사용자별 시작 잠금 |
| `pages/dashboard.py` | `[AUTO-RESUME]` 건너뜀 로그 1줄, 버전 갱신 |
| `tests/regressions/test_r_2026_10_xx_wo12_boot_resume.py` | 재현 테스트 |
| 서버 `/etc/systemd/system/tradebot.service` | `ExecStart` 교체 (승인 C1, 배포 절차에 포함) |

## 4. 검증

1. 로컬 재현 테스트
   - LIVE·실행 중이던 사용자 → 세션 없이 `boot_resume_all()` 이 `start_engine(mode="LIVE")` 호출, 성공 알림 1건
   - 키 검증 실패 / 운용자산 0 → 재개 안 함, CRITICAL 알림, DB 무변경
   - `last_mode="TEST"` 또는 실행 중 아님 → 대상 제외
   - 기동 재개 뒤 대시보드 경로 호출 → 엔진 1개 유지(스레드 수 1), 건너뜀 로그
   - 두 경로 동시 호출(스레드 2개) → 잠금으로 1회만 시작
   - `trading_paused=1` 이어도 엔진은 재개, 주문 스킵 유지
2. 회귀 게이트 (.env 격리)
3. 배포 후 관측 (대시보드 **접속하지 않은 상태**로)
   - `systemctl restart` 뒤 1분 안에 `[BOOT-RESUME] success`, `[migrate] … OK` 14줄, `[BOOT] run_live_loop start`
   - 첫 `[CONFIRMED]` 가 사람 접속 없이 발생
   - 그 뒤 대시보드 접속 시 `[AUTO-RESUME] skip`, 엔진 중복 없음
   - 30분: 결함 태그(`class=pos_desync_promoted`·`class=integrity_gap`·SKIP-BAR·POLLUTED·엔진 Traceback) 0건, Bar# 5봉 이상

## 5. 롤백

- 코드: `git revert <WO-12 커밋>`
- 서버: `tradebot.service` 의 `ExecStart` 를 원래 줄(`venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0`)로 되돌리고 `systemctl daemon-reload && systemctl restart tradebot`. 원본 unit 파일은 배포 전 `/root/backup/tradebot.service.<날짜>` 로 보관합니다.

## 6. 위험

| 위험 | 대응 |
|---|---|
| 사람이 모르는 사이 LIVE 엔진이 켜짐 | 재개 조건을 "직전에 LIVE 로 실행 중이었음"으로 한정하고, 결과를 반드시 텔레그램으로 알립니다. |
| 키 만료 상태에서 재개 시도 반복 | 기동 1회만 시도합니다. 실패 시 알림 후 대기(첫 접속 경로에 맡김). |
| `streamlit.web.bootstrap.run` 동작 차이 (버전 1.46) | 로컬에서 `streamlit run` 과 같은 포트·옵션·페이지 동작을 AppTest 가 아닌 실제 기동으로 확인합니다. |
| 기동 직후 REST/웹소켓 준비 전 엔진 시작 | 기존 `[WARMUP]` 재시도(최대 5회)를 그대로 씁니다. |

## 6-A. 관련 발견 — 외부 매수 포지션의 부팅 복원 실패 (2026-09-30 WO-10 관측)

- 18:02:07 `CRITICAL ❌ 지갑에 코인(1340.436268) 있으나 DB 진입가 seed 실패 → has_position=False 유지`.
- 부팅 복원 `engine/live_loop.py` `_seed_entry_price_from_db` 는 `get_last_open_buy_order`(봇 `orders` 의 체결 BUY)만 읽습니다. 앱에서 산 포지션은 봇 주문이 없어 복원에 실패합니다(`[SEED] raw_last_open=None`).
- 첫 봉(18:10:11)에서 `[POSITION-SYNC] 자동 복구 (source=upbit_avg_buy_price, entry=761.00)` 로 복구됐지만, 그 사이 약 8분 매도 평가가 없습니다.
- WO-12 로 기동 즉시 엔진이 돌기 시작하면, 외부 매수 포지션을 들고 재시작할 때마다 이 CRITICAL 과 공백이 반복됩니다.
- 처방 후보: 부팅 복원이 봇 주문을 못 찾으면 첫 봉 `[POSITION-SYNC]` 와 같은 방식(업비트 `avg_buy_price` + `account_positions.entry_price` 캐시)으로 바로 복원합니다. 포지션 상태를 만드는 경로라 판정 로직에 가깝습니다 → 승인 항목 C7.

## 7. 승인 대기 항목

| 번호 | 내용 | 제안 |
|---|---|---|
| C1 | systemd `ExecStart` 를 기동 스크립트로 교체 (서버 설정 변경) | 진행 |
| C2 | 설계 D 안 채택 (같은 프로세스 기동 스레드) — C 안(엔진 분리)은 별도 장기 과제 | 진행 |
| C3 | LIVE 재개 안전 조건 = 키 조회 성공 + 운용자산 > 0 | 진행 |
| C4 | 재개 실패 시 DB 상태 무변경, 첫 접속 경로에 맡김 | 진행 |
| C5 | 재개 결과 알림 등급: 성공 INFO / 실패 CRITICAL | 진행 |
| C6 | 배포 시점 (서비스 재시작 필요) | 로컬 검증 보고 뒤 별도 지시 |
| C7 | 6-A 부팅 복원 보강(봇 주문이 없으면 업비트 평균가로 즉시 복원)을 WO-12 에 포함할지, 별도 WO 로 나눌지 | WO-12 에 포함 (기동 재개와 같은 시점의 문제이고, 첫 봉 복구와 같은 방식을 앞당기는 것) |

## 8. 구현 결과 (2026-09-30)

### 8.1 변경

| 파일 | 내용 |
|---|---|
| `scripts/tradebot_boot.py` (신설) | `streamlit run` 과 같은 순서(`_config._main_script_path` → `bootstrap.load_config_options` → `bootstrap.run`)로 서버를 띄웁니다. 그 전에 기동 재개 스레드(`boot_resume`, 3초 지연)를 시작합니다. `TRADEBOT_BOOT_RESUME=0` 이면 재개를 끕니다. |
| `engine/boot_resume.py` (신설) | `boot_resume_all()` — 알려진 사용자 마이그레이션(`ensure_all_schemas`) → 대상(engine_status=실행 중 + last_mode=LIVE) → 안전 조건(키 조회 + 운용자산>0) → `start_engine(mode="LIVE")` → 결과 알림(성공 INFO / 실패 CRITICAL, dedupe 600초). 실패 시 DB 무변경, `trading_paused` 무접촉 |
| `engine/engine_manager.py` | `start_engine(..., *, mode=None)` — mode 가 있으면 세션 대신 사용합니다. 사용자별 시작 잠금 안에서 "이미 실행 중"을 다시 확인합니다(같은 모드면 Reconciler 카운트·DB 무변경, False 반환 — 기존 반환 의미 유지). |
| `pages/dashboard.py` | 기동 재개 성공 뒤 첫 접속 시 `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)` 1회. 동시 진입으로 `start_engine=False` 인데 LIVE 가 실제로 돌면 DB 를 "정지"로 정정하지 않습니다. 버전 갱신 |
| `engine/live_loop.py` (C7) | 봇 주문 기준 seed 실패 시 CRITICAL 을 바로 내지 않습니다. 워밍업 직후 `_boot_seed_recover_from_wallet()` 이 첫 봉과 같은 `StrategyEngine._reconcile_position_with_wallet()` 을 호출해 복원합니다. 성공 `[BOOT-SEED] source=… entry=… qty=… entry_bar=…`, 실패 시 기존 CRITICAL·알림 |
| `core/strategy_engine.py` (C7) | `_reconcile_position_with_wallet()` 이 복구 출처를 반환합니다(기존 호출부 무영향). 부팅 복원 뒤 첫 봉에서 `[POSITION-SYNC] 이미 일치 → 스킵 (boot_seed source=…)` 1회 |

### 8.2 계획과 달라진 점

- **대시보드 경쟁 경로 보호를 추가했습니다.** 기존 `[AUTO-RESUME]` 은 `start_engine` 이 False 면 "재개 실패"로 보고 DB 엔진 상태를 "정지"로 정정합니다. 기동 재개와 대시보드 접속이 겹치면 엔진은 도는데 DB 는 정지로 남을 수 있었습니다. False 일 때 실제 실행 모드를 다시 확인하도록 했습니다.
- **`start_engine` 의 기존 누수도 함께 막혔습니다.** 예전에는 이미 실행 중일 때 "시작"을 누르면 Reconciler 카운트(`_live_engine_count`)가 1 늘고 False 가 반환됐습니다. 잠금 안 재확인으로 카운트가 늘지 않습니다.

### 8.3 검증

- `py_compile` 변경 파일 전부 통과
- 재현 테스트 `tests/regressions/test_r_2026_09_30_wo12_boot_resume.py` 14건 통과
  - §4-1: ① LIVE 실행 중 사용자 세션 없이 재개·INFO 1건 (+ 기본 경로가 `start_engine(U, test_mode=False, mode="LIVE")` 호출) ② 키 실패·운용자산 0 → 미재개·CRITICAL·DB 무변경 ③ TEST·미실행 제외 ④ 두 번째 경로 skip·카운트 1 ⑤ 동시 2경로 → 1회 시작 ⑥ `trading_paused=1` 유지하며 재개. 추가: 기동 시 마이그레이션 호출, 세션 모드 미참조
  - C7: 봇 주문 없음 → `[BOOT-SEED] source=upbit_avg_buy_price entry=761.0 qty=1340.436268`, 첫 봉 `이미 일치 → 스킵` 1회, 두 번째 봉 로그 없음 / 잔고 0 → has_position=False·CRITICAL / 출처 없음 → 기존 CRITICAL
  - 변경 전 코드로 실행 시 7건 실패·오류 (신설 `boot_resume` 단위 테스트는 새 모듈이라 통과)
- 회귀 게이트 (.env 격리) 214/214
- **로컬 실기동 (AppTest 아님)** — 리포 사본(`services/data` 제외 → 알려진 사용자 0명, 로컬 실거래 엔진 기동 위험 차단), Telegram 변수 비움, 서버와 같은 `streamlit==1.46.0` + `streamlit-authenticator==0.4.2`

| 항목 | A: `streamlit run app.py` (8611) | B: `scripts/tradebot_boot.py` (8612) |
|---|---|---|
| `/_stcore/health` · `/` · `/_stcore/host-config` | ok · 200 · 200 | ok · 200 · 200 |
| 헤드리스 Chrome(CDP) 렌더 화면 | 로그인 화면 84자 | 동일 (텍스트 일치, 페이지 링크 일치) |
| 서버 로그 Traceback / ERROR | 0 / 0 | 0 / 0 |
| 기동 재개 스레드 | — | `2026-09-30 19:16:00 INFO engine.boot_resume \| [BOOT-RESUME] start \| known=[] targets=[]` |

- 실제 LIVE 재개 성공 경로는 로컬에서 실행하지 않았습니다(로컬 `.env` 에 실거래 키). 서버 배포 후 관측이 이 경로의 확증입니다.

## 9. 배포 절차 초안 (실행은 별도 지시)

unit 파일 본문은 고치지 않고 **drop-in 파일**로 `ExecStart` 만 바꿉니다. 롤백은 그 파일을 지우면 됩니다. 기존 drop-in `override.conf`(`EnvironmentFile=.env`)는 그대로 둡니다. 2026-09-30 확인 기준 `/etc/systemd/system/tradebot.service.d/` 에는 `override.conf`, `override.conf.bak-wo2-20260823` 두 파일이 있습니다.

1. 로컬 push: `git push origin main` (코드 커밋 1건)
2. 서버 백업
   - `mkdir -p /root/backup`
   - `cp /etc/systemd/system/tradebot.service /root/backup/tradebot.service.20260930`
   - `cp -r /etc/systemd/system/tradebot.service.d /root/backup/tradebot.service.d.20260930`
   - `systemctl show tradebot -p ExecStart > /root/backup/tradebot.ExecStart.before.20260930`
3. 서버 코드 pull: `cd /root/upbit-tradebot-mvp && git pull --ff-only && git rev-parse --short HEAD`
4. ExecStart 교체 (drop-in `/etc/systemd/system/tradebot.service.d/wo12-boot.conf`, 내용 3줄)
   - `[Service]`
   - `ExecStart=`
   - `ExecStart=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py`
   - 이어서 `systemctl daemon-reload` → `systemctl show tradebot -p ExecStart` 로 교체 확인
5. 재시작·상태 (대시보드 접속하지 않음): `systemctl restart tradebot` → `systemctl is-active tradebot` → `systemctl show tradebot -p ExecMainStartTimestamp` → `ss -ltnp | grep 8501`

**배포 후 관측 (대시보드 접속 없이 — 통과 조건의 핵심)**

기준 시각 `S` = `systemctl show tradebot -p ExecMainStartTimestamp --value`, 조회는 `journalctl -u tradebot --since "$S"` 에 `grep -F` 고정 문자열로 합니다.

1. 재시작 1분 안에 `[BOOT-RESUME] success user=mcmax33 mode=LIVE`, `[migrate] … OK (user_id=mcmax33)` 14줄, `[BOOT] run_live_loop start`
2. JTO 포지션 보유 시 `[BOOT-SEED] source=upbit_avg_buy_price entry=761.0 qty=1340.436268` (seed CRITICAL 없음), 첫 봉 `[POSITION-SYNC] 이미 일치 → 스킵`
3. 사람 접속 없이 첫 `[CONFIRMED] 봉 처리 완료` 발생, 그때까지 `[AUTO-RESUME]` 0건
4. 그 뒤 운영자 접속 1회: `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)`, 엔진 스레드 1개 (새 `[BOOT] run_live_loop start` 가 더 찍히지 않는지로 확인)
5. 30분: `class=pos_desync_promoted`·`class=integrity_gap`·SKIP-BAR·POLLUTED·엔진 Traceback 0건, Bar# 5봉 이상. JTO 는 관측만(개입 없음)

**롤백**

- 기동 방식만 되돌리기 (코드는 두어도 무해 — 기동 스크립트를 쓰지 않으면 기존 첫 접속 재개와 같음)
  - `rm -f /etc/systemd/system/tradebot.service.d/wo12-boot.conf`
  - `systemctl daemon-reload` → `systemctl show tradebot -p ExecStart` (원래 `venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0` 확인)
  - `systemctl restart tradebot` → `systemctl is-active tradebot`
- 코드까지 되돌리기: 로컬 `git revert <WO-12 커밋>` → push → 서버 pull → restart

## 10. 1단계 배포와 완결 (2026-09-30) — 코드만, 기동 방식 유지

운영자 지시로 배포를 두 단계로 나눴습니다. 1단계는 코드만 배포하고 기동 방식은 기존 `streamlit run` 을 유지했습니다. 2단계(기동 방식 전환)는 운영자가 지정하는 시각에 `docs/operations/wo8-force-buy-verification-guide.md` §확인 4-W12 로 실행합니다.

### 10.1 배포

| 항목 | 값 |
|---|---|
| 커밋 | `0c8e729` (구현 `d12f47b` 에 규칙 v2.9·가이드 §확인 4-W12 를 amend) — 되돌릴 대상 |
| 서버 HEAD | `a3e3a2d` → `0c8e729` (로컬과 일치) |
| 버전 | v1.2026.09.30.1746 → v1.2026.09.30.1917 |
| 백업 | `/root/backup/tradebot.service.20260930`, `/root/backup/tradebot.service.d.20260930/`, `/root/backup/tradebot.ExecStart.before.20260930` |
| ExecStart | `argv[]=/root/upbit-tradebot-mvp/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0` (변경 없음, drop-in 미생성) |
| 서비스 재시작 | 19:26:30 KST |
| 엔진 시작 | 19:44:26 `[AUTO-RESUME] LIVE 자동 재개 시도` → 19:44:27 성공 → 19:44:28 `[BOOT] run_live_loop start` (운영자 새로고침) |

**엔진 정지 약 18분 (19:26:30 ~ 19:44:28)**: 재시작 전부터 열려 있던 브라우저 탭이 새 서버에 다시 붙었지만, 자동 새로고침 조각(fragment)만 호출했습니다(`The fragment with id … does not exist anymore`, 19:27:08 부터 10초마다 89건). 페이지 전체 스크립트가 다시 돌지 않아 `[AUTO-RESUME]` 이 실행되지 않았습니다. 운영자가 새로고침한 뒤에야 엔진이 시작됐습니다. "사람이 접속해 있어도 엔진이 멈춰 있을 수 있다"는 사례로, 2단계(기동 방식 전환)의 근거에 더합니다.

### 10.2 30분 관측 (19:44:28 ~ 20:14:28) — 통과

| 항목 | 결과 | 기준 |
|---|---|---|
| (1) 부팅 복원 | 19:44:29 `[SEED] raw_last_open=None` → `[BOOT-SEED] 봇 주문 기준 진입가 없음 (외부 매수 가능) → 워밍업 뒤 지갑 기준 복원 시도` → 19:44:40 **`[BOOT-SEED] source=upbit_avg_buy_price entry=761.0 qty=1340.436268 entry_bar=200`** | 인용 |
| (1) seed 실패 CRITICAL / 레벨 CRITICAL | 0 / 0 (18:02 에는 1건) | 0 |
| (2) 첫 봉 | 19:50:10 `[POSITION-SYNC] 이미 일치 → 스킵 (boot_seed source=upbit_avg_buy_price) \| qty=1340.436268 entry=761.0` 1건 | 1회 |
| (3) 시작 경로 | `[AUTO-RESUME] … 자동 재개 성공` 1 · `[BOOT] run_live_loop start` 1 · `[BOOT-RESUME]` 0 (기존 방식이라 정상) · `start_engine skip` 0 (겹친 시작 요청 없음) | — |
| (4) `class=pos_desync_promoted` / `integrity_gap` / `first_bar_guard` | 0 / 0 / 0 | 0 |
| (4) SKIP-BAR / POLLUTED / Traceback | 0 / 0 / 0 | 0 |
| (4) Bar# | 201(19:45 봉) → 202 → 203 → 204 → 205(20:05 봉) | 5봉 |
| JTO (관측만, 개입 없음) | `trading_paused=1`, 가용 0·묶임 1,340.436268·entry 761.0, 손절 신호 스킵 5건, `SELL_REJECTED` 0건 | — |
| `[NOTIFY]` 발송 실패 / fragment 경고(창 내) | 0 / 0 | — |

`[POSITION-SYNC] 자동 복구 성공` 1건(19:44:40)은 첫 봉 재복구가 아니라 부팅 복원이 같은 함수를 부른 기록입니다. 순서가 `Buffer seeded`(19:44:39) → `[POSITION-SYNC] 자동 복구`(19:44:39~40) → `[BOOT-SEED]`(19:44:40) 입니다.

**관측 중 확인한 사항 (통과 조건 밖)**
- 19:44:33, 19:44:37 `ERROR core.strategy_engine | ❌ WARMUP 로그 기록 실패: database is locked` 2건. `record_warmup_log()` 가 워밍업 200봉의 감사 행을 쓰다 SQLite 잠금 대기(`busy_timeout=3000ms`)를 넘긴 것입니다. 워밍업은 정상 완료(`Buffer seeded | bar_count=200`)했고 영향은 워밍업 감사 행 2건 누락입니다. journal 보존분(08-30~) 첫 발생이며, 운영자 새로고침으로 페이지 로드(마이그레이션·동기화)와 워밍업 기록이 같은 시각에 겹쳤습니다. WO-12 변경과의 인과는 확인하지 못했습니다(부팅 복원 호출은 워밍업 뒤 19:44:39~40 이라 시각이 다릅니다).
- 20:10:05 Bar#204 가 한 번 더 찍힘 — WO-13(미확정 봉 BACKFILL 평가)과 같은 유형.

### 10.3 1단계 완결 문안

**WO-12 1단계 완결**: 세션 비의존 엔진 시작(`start_engine(mode=)`)·사용자별 시작 잠금·기동 재개 모듈·부팅 복원 보강(C7)을 2026-09-30 19:26 배포했습니다. 기동 방식은 기존대로 두었습니다. 30분 관측에서 통과 조건을 모두 만족했고, 앱에서 산 JTO 포지션이 부팅 직후 업비트 평균가(761.0)로 복원되어 18:02 형 CRITICAL 과 8분 공백이 사라졌습니다.

**2단계 대기 상태**: 기동 방식 전환(`wo12-boot.conf` drop-in)은 운영자가 시각을 지정할 때까지 실행하지 않습니다. 절차·통과 조건 8개·되돌리기는 검증 가이드 §확인 4-W12 에 있습니다. 백업은 `/root/backup/` 에 준비돼 있습니다.

## 11. 2단계 — 기동 방식 전환과 WO-12 완결 (2026-10-01)

### 11.1 실행 (검증 가이드 §확인 4-W12)

| 항목 | 값 |
|---|---|
| 탭 닫힘 확인 | 마지막 fragment 경고 09:53:58, 09:55:18·09:55:40 두 차례 8501 연결 0건 |
| drop-in | `/etc/systemd/system/tradebot.service.d/wo12-boot.conf` (printf 한 줄 생성) — `[Service]` / `ExecStart=` / `ExecStart=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py` |
| ExecStart (daemon-reload 뒤) | `argv[]=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py` |
| 재시작 | 2026-10-01 09:55:59 KST, active, 8501 은 `python` (pid 2253068) |
| 코드·버전 | 서버 HEAD `39689e8`, v1.2026.09.30.1917 — 1단계와 동일 (버전 변경 없음) |

### 11.2 접속 없이 30분 관측 (09:55:59 ~ 10:25:59) — 통과

| # | 통과 조건 | 결과 |
|---|---|---|
| 1 | 재시작 1분 내 BOOT-RESUME | 09:56:05 `[BOOT-RESUME] start \| known=['default', 'gon1972', 'mcmax33'] targets=['mcmax33']` → 09:56:08 `[BOOT-RESUME] success user=mcmax33 mode=LIVE elapsed=8.5s capital≈2,962,905` |
| 2 | `[migrate] OK` 14줄 | 14줄 (09:56:03~05) |
| 3 | BOOT-SEED (JTO) | 해당 없음 — JTO 는 2026-09-30 23:40:09 봇이 전량 매도(EMA_DC, 740.0, orders 550). 복원 대상 없음. seed 실패 CRITICAL 0 |
| 4 | 엔진 시작·워밍업 | 09:56:08 `[BOOT] run_live_loop start` → 09:56:09 `[WARMUP] REST 데이터 로드 완료 bars=200` → 09:56:10 `Buffer seeded` |
| 5 | 사람 접속 없이 첫 `[CONFIRMED]` | 10:00:34 (09:55 봉). 그때까지 `[AUTO-RESUME]` 0, 8501 연결 0 |
| 6 | Bar# 5봉 | 201 → 202 → 203 → 204 → 205 → 206 (09:55 ~ 10:20 봉) |
| 7 | 결함 태그 | `class=pos_desync_promoted` 0 · `integrity_gap` 0 · `first_bar_guard` 0 · SKIP-BAR 0 · POLLUTED 0 · Traceback 0 · 레벨 CRITICAL 0 · ERROR 0 |
| 8 | 재개 성공 INFO 알림 | `[BOOT-RESUME] success` 기록, `[NOTIFY]` 발송 실패 0, 토큰·기본 채팅 설정 있음(INFO 전용 채널 없음 → 기본 채팅). 알림 모듈은 성공 시 로그를 남기지 않으므로(규칙 v2.8) 수신은 운영자 확인 항목 |

- 비교: 접속 없는 워밍업에서 `database is locked` 0건 → 1단계의 2건은 페이지 로드 경합 쪽으로 판단(backlog WO-13 기재).

### 11.3 접속 후 확인 (운영자 접속 10:33) — 통과

| 항목 | 결과 |
|---|---|
| `[AUTO-RESUME] skip` | 10:33:45 `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중): mcmax33 \| boot_resume_at=2026-10-01T09:56:08.345431+09:00 mode=LIVE` 1건 |
| 엔진 스레드 1개 | 재시작 이후 `[BOOT] run_live_loop start` 1건, 엔진 로그 `🚀 엔진 시작` 1건(09:56:08) — 접속 시 새 엔진 없음 |
| 대시보드 렌더 | 10:33:35 `[DB-LOAD]` → `[AUTO-VERIFY]` → 10:33:45 skip → 10:33:48 `[CHART]` 까지 진행, Traceback·ERROR·DB 잠금 0 |

### 11.4 WO-12 완결 문안

**서비스 기동 시 자동 재개 + 부팅 복원 보강 완료. 재시작 후 사람 접속 없이 9초(기동 스크립트 기준 8.5초) 만에 엔진 재개, 첫 봉 처리까지 약 4.6분(09:55:59 재시작 → 10:00:34 첫 `[CONFIRMED]`, 5분봉 다음 마감 시각).** 이전에는 재시작 뒤 사람이 접속할 때까지 엔진이 멈췄습니다(2026-09-18 46분, 09-30 5분·6분·18분). 부팅 복원은 1단계(2026-09-30 19:44)에서 앱 매수 JTO 포지션을 워밍업 직후 업비트 평균가로 복원해 확인했습니다.

**되돌리기**: 기동 방식만 — `rm -f /etc/systemd/system/tradebot.service.d/wo12-boot.conf` → `systemctl daemon-reload` → `systemctl restart tradebot`. 코드까지 — `git revert 0c8e729`.
