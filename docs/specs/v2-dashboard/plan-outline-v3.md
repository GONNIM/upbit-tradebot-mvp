# 검증 대상: v2 P1·P2 계획서(plan.md) 목차·요지 — 개정 3판 (2026-10-22)

작성자: 메인 세션(PO). plan.md 는 아직 쓰지 않았다. 이 목차의 사용자 승인을 받으려는 단계다.
작업 지시: `docs/specs/v2-dashboard/HANDOFF.md` 3판 [3]-3·[3]-4
출발점: `plan-outline-v2.md`(2판) + 검증 보고 `review-20261022-outline-v2.md`(지적 1~16) + 3판 초안 검증 보고 `review-20261022-outline-v3-draft.md`(지적 1~12) + spec 3.1절 E1~E14 + spec 3.2절 E15~E19(개정안)
spec: `docs/specs/v2-dashboard/spec.md`(3.2절 개정안 포함), `docs/specs/pullback-strategy/spec.md`

## 0. 2판에서 바뀐 것 (요약)
- 1차 배포에 `tradebot` 1회 재시작과 봉 누락 판정을 넣었다(E1, 지적 1).
- 「엔진 동작」 출처를 매수·매도 판단 기록 최신 시각 + LIVE 잔고 기록 시각으로 바꿨다(E17).
- 신버전 전용 경량 DB·설정 모듈을 둔다(E2). 신버전 이력은 별도 파일 `v2hist_<user>.db`(E15), 구·신 이력은 따로 관리(E16).
- 실행 계정은 root + systemd 보호(E18).
- 운용 메뉴는 표시만(E10), MA200 제외(E4), 백테스트 계산 시간 판정(E14·E19).
- 1단계 V3 메모리 측정은 서버에서 한다(B-6).

## A. 사실
| # | 사실 | 근거 | 2판 대비 |
|---|---|---|---|
| F1 | 서버 DB 4개는 WAL. ro 연결도 `-shm`·`-wal` 을 만든다(2026-10-22 관측). busy_timeout 없이 `database is locked` 관측 | 3판 초안 검증 F1 | 보강 |
| F2 | nginx 1.18, `location /` → 8501 하나. CSP 없음 | `/etc/nginx/sites-available/tradebot:4-5` | 같음 |
| F3 | available 약 1.38GB. tradebot 실제 RSS 약 200MB(cgroup MemoryCurrent 약 237MB) | 검증 F3 | 정정 |
| F4 | tornado 6.5.1 설치(`requirements.txt:69`). starlette·uvicorn 없음 | 검증 F4 | 같음 |
| F5 | 구버전은 쿠키를 발급하지 않는다 → 1회용 토큰, 「구버전으로」는 재로그인 | 검증 F5 | 같음 |
| F6 | 서버 DB 4개에 OHLC 테이블 없음 | 검증 F6 | 같음 |
| F7 | `engine_status` 는 기동·정지 때만 갱신. `get_running_mode` 는 프로세스 메모리만 | `engine/engine_manager.py:119-123` | 정정 |
| F8 | 엔진에 429·418 처리 없음 | grep 0건 | 같음(백로그) |
| F9 | 잔고는 LIVE 만 60초 주기(`engine/order_reconciler.py:23,27`), KRW `int()` 절사(`services/db.py:2327-2335`), TEST 는 주기 동기화 없음 | 코드 | 정정 |
| F10 | `settings_history` 는 파이썬 허용 목록(`services/settings_history.py:39-44,95-99`)과 DB CHECK(`services/init_db.py:583-588`) 둘 다로 막혀 있다 → 1차는 건드리지 않음(E15) | 코드·서버 스키마 | 정정 |
| F11 | `scoped_params_path` → `{user}_latest_params_{STRATEGY}.json`. `engine.params` import 시 config·streamlit·키 로드 | `engine/params.py:301-319`, `config.py:1-21` | 보강 |
| F12 | 서버 `fileWatcherType = "none"` → `app.py` 변경은 재시작해야 반영. Streamlit 과 엔진은 한 프로세스 | `.streamlit/config.toml:2`, `scripts/tradebot_boot.py:44-67` | 신규 |
| F13 | 엔진 프로세스가 실행 중에 읽는 파일: `app.py`(Streamlit 메인), `pages/*`, `services/settings_history.py`(`engine/live_loop.py:775`, `core/trader.py:314` 늦은 import), `pages/dashboard.py` 버전 문자열(`services/settings_history.py:46,81-92` 가 실행 중 읽음) | grep | 신규 |
| F14 | 서버 봉 단위 minute3. 보유 중 `audit_buy_eval` 최대 282분 공백. 매수 판단 기록 `core/strategy_engine.py:1881,1945,1986`(미보유), 매도 판단 기록 `:2111,2192`(보유). 무거래 봉은 평가를 건너뛰어 둘 다 기록 없음(`engine/live_loop.py:1371-1376`, 미보유 중 24분 공백 관찰) | 검증 B-0·재검증 판정 6, 코드 | 신규 |
| F15 | `audit_*_eval.timestamp` 는 INSERT 시점 KST(`services/db.py:1059`). `bar_time` 은 워밍업 행에서 과거 값 | 코드 | 신규 |
| F16 | 엔진 유닛 `User=root`, override `EnvironmentFile=.env`, systemd 249 | 서버 | 신규 |
| F17 | 정상 봉 처리는 경계 뒤 약 11초에 끝나고, 무거래·미반영 봉은 경계 뒤 5~91초 재시도한다(journal 2026-10-22 06:03~06:07) | 재검증 판정 17 | 신규 |

## B. 목차·요지

### 착수 전 — 세션 재개 표준 정지선
- 로컬 HEAD·origin, 서버 HEAD·`dashboard.py` 버전·`ExecMainStartTimestamp`·`tradebot-v2` 부재·비밀 파일 권한을 대조하고, 어긋나면 멈춘다(`.claude/context/project-rules.md` 「세션 재개 표준 정지선」).

### 머리말
- 목표·구조(별도 서비스 `tradebot-v2`, tornado 127.0.0.1:8502)·spec 경로.
- **Global Constraints**
  - D8: 신버전 서버 코드는 업비트 API를 부르지 않는다(시세·계좌).
  - 엔진 프로세스가 읽는 파일 중 1차에서 바꾸는 것은 `app.py`(입장 버튼, E1) 기능 변경과 `pages/dashboard.py` 버전 문자열뿐이다. `services/settings_history.py`·`services/init_db.py`·`pages/settings_history.py` 는 바꾸지 않는다(E15·E16).
  - `app.py` 는 `v2/*` 를 import 하지 않는다. 토큰 생성은 표준 라이브러리 `hmac`·`hashlib`·`secrets` 만 쓴다(lint).
  - 실매매 DB 는 `file:<경로>?mode=ro` URI + `busy_timeout` 로만 연다. 파일이 없으면 만들지 않고 거부. 조회에 LIMIT·시간 제한·인덱스 확인. 실매매 DB 에는 쓰지 않는다.
  - 신버전 쓰기는 `v2hist_<user>.db` INSERT 1문장과 `{user}_latest_params_PULLBACK.json` 하나뿐. `v2hist` 는 평소 `mode=rw` URI 로 열고, 파일이 없을 때는 허용 목록 user 이면서 그 user 의 실매매 DB 가 있을 때만 `mode=rwc` 로 1회 만든다(그 밖에는 거부).
  - 허용 목록 밖 계정은 403. 모바일 412px. 원본 백테스터와 결과 일치. 시각은 KST.
  - **규칙 항목**: 코드 커밋 때 `pages/dashboard.py` 버전 갱신과 보고에 「버전: 구 → 신」 · 여러 줄 텍스트는 파일 도구로만(heredoc 금지, 빈 것도) · 키·서명 키 값은 어떤 문서·로그·보고에도 적지 않음 · 새 비밀 파일 600·root·사본 금지·정기 점검 · Fable 보고는 번들 zip · push 전 `git status` 스테이징 확인 · 커밋·push·배포·서버 설정 변경·외부 발송은 각각 승인 · 배포 전 감사 로그(*.db) 백업 확인.
- **Review Focus**: 토큰 재사용·만료, 토큰 `?t=` 가 nginx 접근 로그와 Referer 로 새는 경로, 같은 브라우저 계정 전환, 쓰기 API CSRF, DB 기록 지연으로 오래된 잔고 표시, TEST 잔고 기록 정지, 브라우저 업비트 호출 실패·한도 초과(다른 탭·새로고침), TEST/LIVE 표시 혼동(입장 모드 ≠ `last_mode`), E18 남는 위험 2건.

### 1단계 — 코드 무변경 확인 (서버 읽기 전용, DB 를 여는 조회는 `-shm` 이 생김을 전제로 최소화)
- V1 「엔진 동작」 출처 실측(E17): 미보유 때 `audit_buy_eval`, 보유 때 `audit_sell_eval` 의 `timestamp` 간격 분포, journal `[CONFIRMED-NO-TRADE]` 빈도(최근 7일), LIVE `accounts.updated_at` 간격, TEST 모드 모습. 결과로 「정상·지연·판단 불가」 경계를 계획서 본문에서 정한다(결정 A (a)).
- V2 휴대폰 브라우저 업비트 직접 호출 — 실측 수단이 없으면 「미확인」, 공개 후 투자자 화면 확인(백로그).
- V3 신버전 서버 골격 상주 메모리 — 서버 Python 3.12 venv 에서 측정.
- V4 파일 권한 실측: `/root` 700, `services/data/` 와 DB·`-wal`·`-shm`·params 파일 소유자·권한. 배포 뒤에는 신버전 `UMask=0077` 때문에 실매매 DB 의 `-wal`·`-shm` 이 600 root 로 생길 수 있으며 정상이다(접근은 모두 root).

### P1 (엔진 무변경, `app.py`·버전 문자열 제외)
- **T1 서버 골격 + systemd 유닛 초안 (E11·E18)**
  - tornado, 127.0.0.1:8502, 독립 프로세스. `v2/server.py`, `deploy/tradebot-v2.service`.
  - 유닛: `User=root`, `ProtectSystem=strict`, `ReadWritePaths=-`(`services/data/` 폴더, `{user}_latest_params_PULLBACK.json` — 배포 때 빈 파일 선생성, 제자리 쓰기), `InaccessiblePaths=-`(`.env`·`.streamlit/secrets.toml`·`credentials.yaml`), `NoNewPrivileges=yes`, `UMask=0077`, 후보 `CapabilityBoundingSet=`·`AmbientCapabilities=`(빈 값, A17 에서 environ 차단 실측), `MemoryMax=150M`(V3 후 확정), `OOMScoreAdjust=500` 이상, `Nice`·`CPUWeight`, `EnvironmentFile` 없음, `Restart=on-failure`.
  - 허용 목록 계정 추가 절차(운영 문서): 빈 PULLBACK 파일 선생성 → 유닛 `ReadWritePaths` 추가 → `daemon-reload` → `tradebot-v2` 재시작 → A17 재실측.
  - 수용 기준 A2·A3·A12·A17.
- **T2 경량 DB·설정 모듈 (E2·E15)**
  - `v2/db.py`: `sqlite3` 만 사용. `config`·`streamlit`·`pyupbit`·`services.*`·`engine.*` import 금지.
  - user_id 는 허용 목록·정규식 검증 뒤 경로 생성. 실매매 DB 는 ro URI·`busy_timeout`, 파일 없으면 거부(`engine/boot_resume.py:54` glob 보호). `journal_mode` PRAGMA 를 보내지 않는다.
  - `v2hist_<user>.db`: 열은 `settings_history` 와 같게(`saved_at` KST ISO +09:00, `app_version` 은 `pages/dashboard.py` 정규식 추출, `params_json` 원문, `conditions_json`·`applied_at` NULL, `source_page='v2_backtester'`, `strategy_type='PULLBACK'`). 같은 입력의 `record_snapshot` 행과 열 비교 시험.
  - 수용 기준 A14·A16.
- **T3 인증·허용 목록 (E6)**
  - 입장 화면(`app.py`)이 60초 1회용 서명 토큰(HMAC, user_id·모드·만료·nonce)을 만들어 `/v2/?t=` 로 넘긴다. 신버전은 nonce 를 한 번만 받고 세션 쿠키(`HttpOnly`, `Secure`, `SameSite=Lax`, path `/v2/`)를 준 뒤 바로 302 로 `/v2/` 로 보내 주소에서 토큰을 지운다. `Referrer-Policy: no-referrer`. 쓰기 API 는 Origin 검사.
  - 서명 키: 새 비밀 파일(600·root, 사본 금지, `.gitignore`, 정기 점검 목록). 서버에서 생성하고 값은 어디에도 적지 않는다.
  - 허용 목록 파일: 서버 전용, 화면을 그릴 때마다 읽음, 없거나 손상이면 전부 거부. 600·root.
  - 수용 기준 A13.
- **T4 입장 버튼 (`app.py`, 엔진 프로세스 파일)**
  - 허용 계정에만 보임, 접힘 금지(1-B), UI 1-A 3층(`regression_gate.sh`, diff 브리핑, 브라우저 실측), 회귀 lint.
  - 서명 키·허용 목록을 읽다 예외가 나면 try/except 로 버튼만 숨긴다. 키 값은 로그에 남기지 않는다. 시험: 파일 없음·권한 오류·손상 3종에서 구버전 정상.
  - 수용 기준 A1·A4.
- **T5 읽기 API**: 상태(E17: 판단 기록 `timestamp` 최신값 + LIVE `accounts.updated_at` 보조, 「마지막 판단 N분 전」 표시, 정상·지연·판단 불가 3단계, 경계는 V1 실측 뒤 계획서 본문에서(결정 A (a)). 모드 배지는 `engine_status.last_mode`, 입장 모드와 다르면 경고. 현재 전략 배지는 엔진 실제 출처 `{user}_active_strategy.txt` 를 직접 읽음 — `engine_status` 에 전략 열 없음, `v2hist` 추정은 쓰지 않음(E16). `engine/params.py:444` 가 파일 이름만 돌려주므로 절대 경로 `/root/upbit-tradebot-mvp/<user>_active_strategy.txt` 로 읽는다. 이 값은 엔진이 기동 때 읽으므로(`engine/engine_manager.py:354-370`) 배지에 파일 수정 시각을 함께 보인다. A17 에 「신버전 안에서 이 파일 읽기 성공」 포함)·자산·포지션(DB 값 + 기록 시각, 평가손익 현재가 = 엔진 기록 가격 + 시각, E5)·신호·거래·로그(페이지 단위). `v2/api_read.py`.
- **T6 정적 화면 (spec 4.3)**: 홈·차트·로그·운용·「구버전으로」.
  - 카드마다 자기 API 를 5~10초마다 호출, 숨김 탭에서 멈춤. 상태는 색만이 아니라 글자로도.
  - 차트: 브라우저 직접 업비트 200봉, 30초 갱신, 실패 시 마지막 데이터 + 「갱신 실패 · 시각」, 형성 중 봉 구분, MA60·눌림목 MA, MA200 없음(E4). 업비트 외 외부 호출 없음(허용 도메인 목록).
  - 운용 탭 표시만(버튼 비활성 「2차 공개 때 열림」, 현재 전략·모드·일시정지 읽기, E10). 「구버전으로」 재로그인 안내.
  - Alpine·Lightweight Charts 를 `v2/static/vendor/` 에 버전 고정. 수용 기준 A4·A5.

### P2 (엔진 무변경)
- **T7 백테스터 이식 (spec 4.4)**: 원본 JS 그대로, Binance 전용, 업비트 칸 「준비 중」 비활성.
  - 체크리스트: 입력 24개, 「데이터 가져오기 + 백테스트」, 스윕(TP·SL·분할 횟수 범위, 정렬 4종), CSV 4종, 차트(확대·축소·다시 그리기·표시 봉 수), 결과 요약·분할 단계별 누적 통계·주간·월간 표(KST), 전략 설명 접기.
  - Node 로 원본 vs 이식본 3세트 CSV 4종 비교.
  - 속도(E19): 같은 입력·같은 브라우저(chrome-devtools performance trace)에서 계산 시간(백테스트·스윕) 원본·이식본 각 3회, 중앙값 +20% 이내. 데이터 받기는 요청 수·받은 봉 수 동일, 시간은 기록만.
  - 수용 기준 A6.
- **T8 「저장만 하기」 (E7·E9·E15·E16)**: 범위 검증, `{user}_latest_params_PULLBACK.json` 만 씀(EMA·MACD 파일 해시 불변), 엔진이 이 파일을 읽지 않음 시험(`engine/live_loop.py:531-550` 은 자기 전략 조건 파일만 감시), `v2hist` INSERT, TEST/LIVE 구분 없음, 확인 창. 신버전 이력 기능의 전략 추정은 `v2hist` 로만 하고, 화면의 현재 전략 표시는 `{user}_active_strategy.txt`(T5)를 따른다(E16).
  - 회귀: 구버전 설정 이력 화면·복원·`_resolve_active_strategy`·`get_active_settings_id` 가 배포 전후 같음(A18).
  - 수용 기준 A7·A16·A18.

### 엔진 프로세스가 읽는 1차 변경 파일
| 파일 | 엔진 쪽 사용 위치 | 반영 시점 | 위험 | 시험 |
|---|---|---|---|---|
| `app.py` | Streamlit 메인 스크립트(엔진과 같은 프로세스) | 1차 배포 `tradebot` 재시작(E1) | import 실패·파일 읽기 예외 시 구버전 전체 중단 | `regression_gate.sh` top-level import 게이트, T4 예외 3종, `v2/*` import 금지 lint |
| `pages/dashboard.py`(버전 문자열만) | Streamlit 페이지, `services/settings_history.py:46,81-92` 가 실행 중 읽음 | 1차 배포 재시작 | 정규식 불일치 시 `app_version` NULL | 버전 형식 정규식 시험 |
| `ui/v2_entry.py`·`utils/v2_entry_token.py`(신규, 2026-10-22 계획서에서 추가) | `app.py` 가 import(엔진과 같은 프로세스) | 1차 배포 재시작. 이후 **동결**(바꾸면 `tradebot` 재시작 필요) | 예외 시 버튼만 숨김, 형식 불일치 시 입장 실패 | AppTest 렌더 시험, 형식 버전 `"v": 1`, v2 배포 diff 에 있으면 정지 |
| `services/settings_history.py`·`services/init_db.py`·`pages/settings_history.py` | `live_loop.py:775`, `trader.py:314`, `db.py` `ensure_schema` | **바꾸지 않음**(E15) | — | diff 범위 확인에서 0줄 |
| 그 밖(`v2/*`, `deploy/*`, 문서, 시험) | 없음 | `tradebot-v2` 재시작만 | — | A14 import 그래프 |

### 배포 절 (P1+P2 한 번에)
1. 착수 전 정지선 재확인. 배포 전 `git diff --stat <서버 HEAD> <배포 HEAD>` 가 `v2/`·`deploy/`·`app.py`·`pages/dashboard.py`(버전)·`scripts/regression_gate.sh`(lint 추가 시)·시험·문서·`.gitignore`·`.claude/`·`CLAUDE.md` 뿐인지 확인.
2. 감사 로그(*.db) 백업 확인(실매매 DB 구조 변경은 없음).
3. `pages/dashboard.py` 버전 갱신, 보고에 「버전: 구 → 신」.
4. 서버 설정 변경(배포 승인 범위, 대상 목록 명시): `tradebot-v2` 유닛 추가·enable, nginx `location /v2/` 한 블록, 서명 키·허용 목록 비밀 파일 생성(600), 빈 PULLBACK params 파일 선생성, `v2hist` 백업용 별도 cron 줄 추가(기존 `/root/cleanup_tradebot_db.sh` 무변경, 백업본 600, E15).
5. **`tradebot` 1회 재시작(E1)**: 시각이 아니라 조건으로 실행한다 — 현재 봉의 `[CONFIRMED] 봉 처리 완료` 또는 `[CONFIRMED-NO-TRADE]` 로그 확인, 대기 중 주문 0(확인할 테이블·로그 태그는 계획서 본문에서 정함), 다음 봉 경계까지 60초 이상 남음. `ExecMainStartTimestamp` 변경 확인. `journalctl -u tradebot` 로 `[BOOT-RESUME]` 기동 재개, WO-12 판정표(`docs/plans/2026-09-30-wo12-boot-auto-resume/plan.md:285`) 결함 태그 0건(`pos_desync_promoted`·`integrity_gap`·`first_bar_guard`·SKIP-BAR·POLLUTED·Traceback·CRITICAL·ERROR), 재시작 앞뒤 확정 봉 사이 누락 0(`[CONFIRMED-NO-TRADE]` 봉은 누락으로 세지 않음).
6. `tradebot-v2` 기동 → A14(`sys.modules`·환경변수), A17(유닛 보호 실측), A12(메모리).
7. 3점 일치: 로컬·서버 HEAD/버전, `ExecMainStartTimestamp`.
8. 즉시 닫기: `systemctl stop tradebot-v2` 또는 허용 목록 비움(엔진 재시작 없음).
9. **되돌리기**: 엔진 쪽 변경(`app.py`·버전 문자열)은 `git revert` + `tradebot` 재시작(5와 같은 점검). 실매매 DB 는 바뀌지 않으므로 DB 되돌리기 없음. `v2hist`·PULLBACK params 파일은 남겨 두고 엔진은 읽지 않음.
10. 관찰 A15(`journalctl -u tradebot` — 429·418·놓친 봉 0), 비밀 파일 권한 점검.
11. 투자자 통보 문안 A(「업비트 데이터 준비 중」 포함) + `investor-notice-log.md` 기록 — 외부 발송 별도 승인.
12. Fable 검산용 보고 번들 zip.

### 역할·수용 기준 표
- 구현 sonnet, 설계·리뷰 opus, 검증 verifier(계획 승인 전·구현 보고 전·배포 승인 전), Fable 은 단계 끝마다.
- A1~A18 ↔ 담당 과제 대응표. A8~A10 은 P3·P4 범위 「해당 없음」. A11 은 P4 범위이나 「신버전에 `engine.*` import 없음」은 A14 로 1차에서 확인.

## C. 대응표

### C1. 2판 검증 지적 1~16
| 지적 | 반영 위치 |
|---|---|
| 1 엔진 재시작 | 배포 절 5, A2 범위, T4 |
| 2 엔진 동작 출처 | T5, V1 (E17) |
| 3 config·키 로드 | T2, A14 |
| 4 실행 계정·서명 키 | T1 유닛(E18), T3 서명 키, V4 |
| 5 DB ro·쓰기·파일 생성 | Global, T2, A16 |
| 6 평가손익 현재가 | T5 (E5) |
| 7 MA200 | T6 (E4) |
| 8 「구버전으로」 재로그인 | T6, A4 |
| 9 TEST/LIVE 혼동 | T5 모드 배지·경고, Review Focus |
| 10 A14 범위 | T2, T6 허용 도메인, 배포 절 6 |
| 11 PULLBACK 이력 복원 | E15·E16 으로 해소(구버전 이력에 PULLBACK 행 없음), A18 |
| 12 같은 작업 트리 | 배포 절 1, 엔진 import 표 |
| 13 OHLC 테이블 | P3 범위(spec 4.4) — 이 계획 밖 |
| 14 spec 옛 문구 | `ee6efc4` 에서 해결, 남은 4.5:140 은 개정안에서 정정 |
| 15 규칙 항목 | Global 규칙 항목 |
| 16 유닛 자원 제한 | T1 유닛, A3 |

### C2. 3판 초안 검증 지적 1~12
| 지적 | 반영 위치 |
|---|---|
| 1 E8 CHECK 제약 | E15(별도 파일), Global, 엔진 import 표 |
| 2 E3 보유 중 공백 | E17, T5, V1 |
| 3 root 실행 키 차단 | E18, T1, A17 |
| 4 구버전 현재 전략 추정 | E16, T8, A18 |
| 5 경량 INSERT·4.5:140 | T2 열 비교 시험, spec 4.5 개정 |
| 6 import 표 누락 | 엔진 import 표(dashboard.py 행, 바꾸지 않는 파일 행), `app.py` → `v2/*` import 금지, 배포 diff 허용 목록 |
| 7 되돌리기 | 배포 절 9 |
| 8 `app.py` 예외 | T4 |
| 9 Referer·CSRF | T3 |
| 10 4.3·4.4·4.7 누락 | T6·T7 체크리스트, 역할 표 A11 |
| 11 E1 판정 기준·정지선 | 배포 절 5, 착수 전 정지선 |
| 12 `mode=rw`·PRAGMA·인덱스 | Global, T2 |
| 기타 감사 로그 백업 | 배포 절 2 |

### C3. spec 3.1·3.2 E1~E19
| E | 반영 위치 |
|---|---|
| E1 | 배포 절 5, import 표 |
| E2 | T2, A14 |
| E3 | E17 로 대체 |
| E4 | T6 |
| E5 | T5 |
| E6 | T3 |
| E7 | T8 |
| E8 | E15·E16 으로 대체 |
| E9 | T8 |
| E10 | T6 |
| E11 | T1 |
| E12 | P3 범위 — 이 계획 밖 |
| E13 | P3 범위 — 이 계획 밖(T7 은 「저장만」 유지) |
| E14 | T7, A6 (판정 범위 E19) |
| E15 | T2, T8, Global |
| E16 | T5, T8, A18. P3 선행 조건으로 HANDOFF 에 기록 |
| E17 | T5, V1 |
| E18 | T1, A17 |
| E19 | T7, A6 |

### C4. spec 4절
| 절 | 반영 위치 |
|---|---|
| 4.1 구조 | T1, Global, 배포 절 |
| 4.2 인증 | T3, T4 |
| 4.3 화면 | T5, T6 |
| 4.4 백테스터 | T7 |
| 4.5 저장(「저장만 하기」) | T8. 「이 설정으로 동작」은 P4 |
| 4.6 전환·복귀 | P4 범위 — 이 계획 밖 |
| 4.7 엔진 제어 | P4 범위 — 이 계획 밖. 1차는 신버전에 `engine.*` import 없음(A14) |

### C5. 재검증 지적 N1~N8
| 지적 | 반영 위치 |
|---|---|
| N1 무거래 봉 공백 | 결정 A (a): E17·V1·T5 |
| N2 재시작 시점·누락 판정 | 배포 절 5 |
| N3 v2hist 권한·백업 | T1 `UMask=0077`, A17, E15 백업 방침 D 절 결정 B |
| N4 environ 차단 후보 | T1 `CapabilityBoundingSet=`, A17 실측 |
| N5 계정 추가 절차·`-` 접두사 | T1 절차, `InaccessiblePaths=-` |
| N6 `scripts/regression_gate.sh` | 배포 절 1 |
| N7 인용 줄 | F14, spec E17 |
| N8 세 곳 불일치 | V1·T5·spec E17 을 결정 A (a) 로 통일 |

## D. 결정
- 2026-10-22 사용자 결정으로 모두 확정: 결정 1 (c2)→E15, 결정 2 (a)→E17(임계는 결정 A), 결정 3→E16, 결정 4 (a)→E18, 결정 5 (a)→E19, 결정 A (a)→E17, 결정 B (a)→E15.
- 남은 사용자 결정 없음. 목차 승인만 남음.
