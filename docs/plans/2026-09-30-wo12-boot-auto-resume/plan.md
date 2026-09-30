# WO-12 계획서 — 서비스 기동 시 엔진 자동 재개 + 마이그레이션 기동 시점 실행 (초안)

- 작성일: 2026-09-30
- 상태: **초안, 사용자 승인 대기** (코드 수정 착수 전)
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
