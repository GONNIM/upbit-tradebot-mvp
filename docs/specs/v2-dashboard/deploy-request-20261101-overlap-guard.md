# 엔진 시작 겹침 막기 배포 승인 요청서 (2026-11-01 — 1101-13 승인)

**사용자 승인 (11/01 21:48):** 「1101-13 승인: 1~5 권고대로」 — (1) 11/02 14:21 이후, 1101-07 24시간 관찰 판정 뒤 (2) 운영자 채널 시험 함께(실행 직전 재확인) (3) 통보 B 에 1줄 붙여 배포 뒤 한 번에 (4) 새 세션에서 실행 (5) 3절 1·2 되돌리기 승인 범위에 포함. 11/02 2-0 정지선에서 JTO 보유가 있으면 미루고 보고한다.

**한 줄:** 서버를 `f73ec4b`(v1.2026.10.30.2230)에서 `ee874a2`(코드 `bc694a4`, 파일 버전 v1.2026.11.01.1849)로 올리고 `tradebot` 을 1회 재시작한다. 정지한 옛 매매 루프가 살아 있을 때 새 엔진이 겹쳐 뜨는 것을 막는다(11/01 16:45 24초 겹침의 재발 방지). `tradebot-v2` 는 재시작하지 않는다.

**근거:**
- 계획: `docs/plans/2026-11-01-engine-start-overlap-guard/plan.md`(verifier 2회·Fable 2회 진행)
- 사용자 결정: 1101-09·10·11·12 ㉠
- 구현 검증: verifier 2회차 「승인 가능」, Fable `docs/fable/2026-11-01-1101-05-impl-1.md`(막음 1건 → 사용자 결정 1101-11 로 메움)
- 게이트: push 때 회귀 1186/1186 · v2 · JS 통과, NETGUARD 0
- 사고 근거: `docs/specs/v2-dashboard/deploy-report-20261101-phase2.md` 2-4절

**실행:** 승인 뒤 PO(Claude)가 SSH 로 실행한다(사용자 허용 규칙 `Bash(ssh root@orionhunter7.cafe24.com:*)`). 순서는 2-0 정지선 → 실행 직전 Fable 질의 1회(「진행」일 때만) → 2-1~2-6 이다. `deploy-tradebot`·`/root/deploy.sh` 는 쓰지 않는다(조건 없이 재시작).

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| Q0 | 배포 전 mcmax33 DB 백업 | `/root/backup/tradebot_mcmax33_<YYYYMMDD>_<HHMM>.db`(600) | 백업 파일 삭제 |
| Q1 | `git pull --ff-only` (f73ec4b → ee874a2) | 18파일. 런타임 코드 4개(1-1), 손 도구 1, 시험 4, 문서 9 | 3절 |
| Q2 | `tradebot` 재시작 1회 (2-2 조건) | 새 시작 검사·경보, 구버전 화면 문구 1개·버전 1849 | 3절 |
| Q3 | 운영자 채널 시험 알림 1건 (운영자 입회) | 텔레그램 운영자 채널에 「운영자 채널 시험」 1건(외부 발송) | 없음(보낸 알림) |
| Q4 | 투자자 통보 1줄 (운영자 발송) | 없음 | — |

### 1-1. 런타임 코드 (f73ec4b → ee874a2, `git diff --name-only`)
- `core/engine_control.py`: `alive_engine_threads` 추가(표준 라이브러리만).
- `engine/control_requests.py`: `_stale_threads` 위임, 신버전 거절 때 5분 경보 판단, 시작 경합 때 `old_engine_alive`.
- `engine/engine_manager.py`: 시작 검사(`_start_engine_locked` MODE-LOCK 뒤·internal 이중), `last_start_reject`, `note_old_alive_reject`, 정지 시각, 운영자 경보(잠금 밖).
- `pages/dashboard.py`: 구버전 시작 거절 문구 1개, 버전 2230 → 1849.
- **EMA 공용 경로 변경 — 시작 검사만, 매매·주문 경로 무변경**(`tests/regressions/baseline_commits.py` 1번 규칙).
- 매매 판정·주문 파일(`core/strategy_engine.py`·`core/trader.py`·`engine/live_loop.py`·`engine/order_reconciler.py`·`core/rest_reconcile.py`)은 0줄이다. DB 스키마 변경은 없다.
- 유닛 파일·nginx·`.env` 는 바꾸지 않는다.
- v2(`-m v2.server`)는 바뀐 모듈을 import 하지 않는다. 그래서 `tradebot-v2` 재시작이 필요 없다(verifier 확인).

## 2. 실행 순서와 멈춤 조건
- 여러 줄 서버 명령은 로컬 scratchpad 파일로 쓰고 `ssh … 'bash -s' < 파일` 로 보낸다(셸 heredoc 금지).
- 운영 DB 는 `sqlite3 -readonly` 로만 읽는다(Q0 `.backup` 제외).
- **「ERROR 0」의 정의:** journal(`-o cat`) 줄 수준이 ERROR·CRITICAL 인 줄이다(`grep -E '^\S+ \S+ (ERROR|CRITICAL) '`). 여기에 `Traceback`·`database is locked` 줄을 더한다. INFO 줄 안의 `[NOTIFY] sent | kind=CRITICAL` 은 세지 않는다. 글자 grep 으로 세면 14:21 뒤에도 3줄이 걸린다(16:46:07·16:58:02·16:58:11 알림 발송 INFO).

### 2-0. 정지선 (읽기 전용 — 하나라도 다르면 멈추고 보고)
| 항목 | 기대값 (11/01 18:57~19:0x 실측) |
|---|---|
| 서버 HEAD | `f73ec4b`, `pages/dashboard.py:523` 2230, 서버 미추적 5 |
| tradebot | active, `Sun 2026-11-01 14:21:19 KST`, NRestarts 0, `Restart=always` |
| tradebot-v2 | `Sun 2026-11-01 14:21:31 KST`, NRestarts 0 |
| 14:21:17 뒤 엔진 | 실패 표지 0, 위 정의의 ERROR 0, ENGINE-EXIT 0, 429·418 0 |
| KRW-JTO 보유 | 0 (`account_positions` virtual_coin·locked) |
| 활성 전략 | `_active_strategy.txt`·`gon1972_…`·`mcmax33_active_strategy.txt` 모두 `EMA` (`head -c 20`) |
| 로그 수준 | INFO (`scripts/tradebot_boot.py:180-181`) |
| 비밀 파일 | `.env`·`.streamlit/secrets.toml`·`.v2_secret`·`.v2_allowlist` 600 root, 사본(`.bak`·`.old`·`.orig`·`~`) 0 |
| 디스크 | 여유 3G 이상(18:5x 실측 19G) |
| 로컬 | HEAD `ee874a2` = origin/main, 추적 변경 0. 이 요청서는 배포 뒤 문서 커밋에 넣는다(배포 대상은 ee874a2) |

### 2-1. Q0 백업
- 봉 처리 줄 직후에 `timeout 900 sqlite3 … ".backup /root/backup/…"` 를 한다(2차 P0 과 같은 방식). 끝나면 `chmod 600` 하고 `integrity_check` 가 ok 인지 본다.
- 다른 사용자 DB(default·gon1972·빈 이름)는 뺀다. 이번 변경에는 스키마·쓰기 경로 변경이 없고, 거절 때 logs 1줄은 mcmax33 시작 때만 생긴다.
- 백업 폴더에 남는 `-shm`·`-wal` 사본도 600 인지 본다(지우지 않음).

### 2-2. Q1 pull → Q2 재시작 (2차 2-3 과 같은 조건)
- 조건: 봉 처리 줄을 막 본 뒤 다음 3분 경계까지 60초 이상 남음, 미체결 주문 0, 최근 5분 ERROR 0, **JTO 보유 0**.
  - 보유가 있으면 멈추고 보고한다(재시작 중 손절·익절이 멈추므로).
- 순서: `git pull --ff-only` → HEAD `ee874a2` 확인 → `systemctl restart tradebot`. pull 직후 곧바로 재시작하고, 그 사이 화면 조작은 하지 않는다.
  - 새 `pages/dashboard.py` 가 옛 `engine_manager` 를 만나면 시작 실패 분기에서 `last_start_reject` 가 없어 오류가 날 수 있다(몇 초 창).
- 기동 확인: `[BOOT-RESUME] success`, `REST 데이터 로드 완료`, 실패 줄 0, `[migrate]` 실패 0(스키마 변경 없음 — OK 줄만).
- **기동 확인 실패, 위 정의의 ERROR, 재시작 반복(NRestarts 증가), 첫 봉 판정 형식이 다르면 → 3절 1 비상 되돌리기.**

### 2-3. 확인
- 첫 봉 2개: 배포 전과 같은 형식, HOLD·EMA 이어짐.
- 3점 일치: 로컬 `ee874a2` / 서버 `ee874a2`·파일 1849 / tradebot 새 기동 시각.
- `check_v2_unit.sh mcmax33` 19/19.
- 새 코드 표식은 grep 으로 본다. `core/engine_control.py` 에 `alive_engine_threads`, `engine/engine_manager.py` 에 `[ENGINE-START]`. 거절 로그는 거절이 있을 때만 찍히므로, 0줄이 정상이다.

### 2-4. Q3 운영자 채널 시험 (운영자 입회 — 실행 직전 한 번 더 묻는다)
- 읽기 전용 확인: `systemctl show tradebot -p EnvironmentFiles`, `ls -l .env .streamlit/secrets.toml`, `venv/bin/python -c "import dotenv"`.
- 실행: `cd /root/upbit-tradebot-mvp && venv/bin/python scripts/v2/notify_operator_test.py`
  - 엔진과 같은 해석기(3.12.8)·라이브러리로 돌린다. 시스템 `python3` 는 3.10.12 다.
  - 출력은 있음/없음·보냄/못 보냄뿐이다.
- 운영자가 운영자 채널에서 「운영자 채널 시험」 수신을 확인한다. 이것으로 1101-06 「미시험」을 닫는다.

### 2-5. 운영자 확인 (브라우저, 보유 0 일 때만)
- 구버전 화면 버전이 1849 인지 본다.
- 구버전에서 엔진 「정지」 → **곧바로** 「엔진 실행하기」를 누른다.
  - 옛 루프가 아직 돌고 있으면 「⏳ 이전 엔진이 아직 정리 중입니다. 1~3분 뒤 다시 눌러 주세요.」가 나온다.
  - 옛 루프가 2초 안에 끝났으면 바로 시작된다(둘 다 정상).
- 3분 뒤 다시 눌러 시작되는지 본다.
- 이 확인에서 거절 경로가 실제로 나올지는 그때 옛 루프 상태에 달려 있다. 거절 경로의 실증은 단위 시험(23건·변이 3)에 기댄다. 정지~재시작 사이에는 매수 신호를 놓칠 수 있다(보유 0 이라 손절 공백은 없음).
- Claude 는 journal 에서 확인한다: `[ENGINE-START]` 줄(거절이 있었으면), 루프 겹침 0(`[BOOT] run_live_loop start` 와 `run_live_loop 종료` 순서), ENGINE-EXIT 0.

### 2-6. 관찰·보고
- 1시간: 실패 표지 0, 빠진 봉 0, ERROR 류 0, ENGINE-EXIT 0, 429·418 0.
- 완료 보고에 3점 일치와 「버전: v1.2026.10.30.2230 → v1.2026.11.01.1849」를 적는다. 문서 커밋은 별도 승인을 받는다.
- 2차 배포 24시간 관찰(1101-07)과의 관계는 6절 결정 1 에 따른다.

## 3. 되돌리기 (승인 범위에 함께 넣음)
1. **비상(서버만, 엔진이 멈춘 시간을 줄임):** 서버에서 `git checkout f73ec4b`(detached) → `systemctl restart tradebot` → 2-2 기동 확인.
   - 보유가 있으면 손절·익절 공백이 생기므로 바로 실행한다.
   - 서버 파일 버전은 2230 으로 돌아간다.
2. **정식(로컬 → push → 서버):** 로컬에서 코드·시험만 경로를 지정해 되돌린다.
   - `git checkout f73ec4b -- core/engine_control.py engine/control_requests.py engine/engine_manager.py tests/regressions/baseline_commits.py tests/regressions/test_r_2026_10_29_p4_t15_old_ui.py`
   - `git rm tests/regressions/test_r_2026_11_01_engine_start_overlap.py`
   - `scripts/v2/notify_operator_test.py`·`tests/regressions/test_r_2026_11_01_notify_operator_tool.py` 는 남긴다(엔진과 독립, 시험은 바깥 연결 없음).
   - `pages/dashboard.py` 의 거절 문구 분기를 지우고 버전을 갱신한다.
   - 게이트를 통과시키고 커밋·push 한다.
   - 서버: `git checkout main && git pull --ff-only` → 2-2 조건으로 `systemctl restart tradebot`.
   - `git revert ee874a2 bc694a4` 는 쓰지 않는다. bc694a4 는 계획서·Fable 문서·운영자 도구까지 담고 있어, 배포 뒤 문서 커밋과 충돌할 수 있다.
3. DB 스키마 변경이 없어 DB 되돌리기는 필요 없다. 되돌린 뒤에는 임시 규칙(정지 뒤 3분 이상, 시작은 신버전 단추)으로 돌아간다.

## 4. 영향
| 축 | 바뀌는 것 | 위험 | 막는 장치 |
|---|---|---|---|
| 매매 | 없음(판정·주문 파일 0줄) | 재시작 중 봉 1개 지연 | 2-2 조건, 보유 0 일 때만 |
| 엔진 시작 | 옛 스레드 생존 시 거절 | 정상 시작 잘못 거절 | 이름 정확 일치·시험 23·변이 3 |
| 재시작 | tradebot 1회 | 기동 실패 | 2-2 기동 확인, 3절 |
| 화면 | 구버전 거절 문구 1개·버전. 거절 때 logs 표 1줄 「⏳ 이전 엔진 정리 중 — 시작을 미뤘습니다. 1~3분 뒤 다시 눌러 주세요.」(구버전 로그·신버전 로그 탭 모두 보임, `v2/api_read.py:127`) | 투자자 혼선 | 통보 1줄(5절) |
| 자동 재개 | 구버전 화면 자동 재개가 거절되면 화면이 DB 를 「정지」로 고침(`dashboard.py:496·499`) | 「DB 정지·옛 루프 한 바퀴 도는 중」 짧은 구간 | 2-6 관찰에서 `[AUTO-RESUME]` 줄을 함께 본다 |
| 알림 | 정지 뒤 5분 넘는 거절에 운영자 1건/10분 | — | dedupe 600초 |
| 외부 발송 | 운영자 채널 시험 1건. 2-5 운영자 확인의 구버전 정지·시작 단추가 기본 채널로 `engine_stop`·`engine_start` 알림 각 1건(logs 표에도 줄) | 소음 | 운영자 입회·직전 확인 |
| 자격증명 | 손 도구가 `.env` 를 읽음(값 미출력, notifier 로그 끔) | 출력 노출 | 시험(토큰 미출력) |
| 업비트 한도 | 새 호출 없음, 재시작 워밍업 1회(801봉) | 429 | 2차 때 0, 1차 장치 그대로 |

## 5. 투자자 통보 (체감 변경 1줄)
> 엔진을 멈춘 직후 바로 다시 시작하면 「이전 엔진이 아직 정리 중입니다」 안내가 나올 수 있습니다. 1~3분 뒤 다시 누르시면 됩니다.

- 2차 통보 문안 B(1101-04)를 아직 보내지 않았으면, B 끝에 이 줄을 붙여 한 번에 보낸다(권고 — 6절 결정 3).
- 보낸 뒤 `docs/operations/investor-notice-log.md` 에 기록한다.

## 6. 정해 주실 것
| # | 정할 것 | 선택지 | 권고 |
|---|---|---|---|
| 1 | 배포 시점 | (가) 2차 24시간 관찰(1101-07) 뒤 — 11/02 14:21 이후 (나) 지금 | (가) — 2차 관찰을 재시작 없이 끝내고, 그동안 임시 규칙 |
| 2 | 운영자 채널 시험 1건(Q3) | 함께 함 / 미룸 | 함께 함(운영자 입회, 직전 재확인) |
| 3 | 통보 | B 에 1줄 붙여 배포 뒤 한 번에 / 따로 | B 에 붙여 한 번에 |
| 4 | 실행 방식 | 새 세션 / 이 세션 | 이 세션이 길면 새 세션(HANDOFF 로 시작) |
| 5 | 되돌리기 | 3절 1(서버 비상)·2(경로 지정 정식)를 승인 범위에 함께 넣음 | 넣음 |

- 검증: verifier 1회 「수정 후 승인」 → 지적 1~12 반영. 1186/1186 은 커밋 B 직전 로컬 게이트·push 때 pre-push 게이트 두 번 실측(11/01 18:5x).
