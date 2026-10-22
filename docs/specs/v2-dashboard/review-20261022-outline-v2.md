# 검증 보고 — v2 P1·P2 계획 목차 개정 2판 (2026-10-22)

- 대상: `docs/specs/v2-dashboard/plan-outline-v2.md`
- 검증: `verifier` 역할(`.claude/agents/verifier.md`, opus, 읽기 전용, 서버 SSH 읽기 전용)
- 메인 세션 재확인: 아래 「반박됨」 중 F7-b, B-1 과 지적 3의 `config.py:1` 은 메인 세션이 직접 다시 확인했다.
- 판정: **수정 후 승인**. 사실 주장 11건 중 7건 확인, 계획 전제 3건이 실측과 다름.

## 1. 주장별 판정

| # | 주장 | 판정 | 근거 | 영향 |
|---|---|---|---|---|
| F1 | 서버 DB는 WAL | 확인됨 | DB 4개 `PRAGMA journal_mode` = `wal`, 헤더 18·19 바이트 `2 2` | ro 연결도 -shm 을 만들 수 있다. root 가 아닌 계정이면 못 열 수 있다 |
| F2 | nginx 1.18, `location /` → 8501 하나 | 확인됨 | `/etc/nginx/sites-available/tradebot:4-5`. CSP·add_header 0건 | 서버 CSP가 브라우저 업비트 직접 호출을 막지 않는다 |
| F3 | available 1.39GB, tradebot RSS 240MB | 일부 | available 1391MB. 실제 RSS 약 200MB(`ps` 204,596KB). 240MB는 cgroup `MemoryCurrent`(페이지 캐시 포함) | 수치 출처 정정 |
| F4 | tornado 6.5.1 설치, starlette·uvicorn 없음 | 확인됨 | 서버 `pip list`, `requirements.txt:69` `tornado==6.5.1` | 새 의존성 0 |
| F5 | 구버전 쿠키 미발급 | 확인됨 | 서버 `secrets.toml` environment="local" → `app.py:134` IS_CLOUD False → `credentials.yaml` expiry_days 0 → streamlit_authenticator `cookie_model.py:94` 쿠키 설정 안 함 | 1회용 토큰 방향. 「구버전으로」 링크는 재로그인 필요 |
| F6 | candle_cache 서버 DB 4개 모두 없음 | 확인됨 | `sqlite_master` 조회 0. OHLC 테이블 자체가 없음 | P3 Upbit 출처는 엔진에 봉 기록 기능 신설이 필요 |
| F7-a | engine_status 테이블 존재 | 확인됨 | `services/init_db.py:219-226` | — |
| F7-b | engine_status 로 엔진 동작 표시 가능 | **반박됨** | 서버 값 `mcmax33\|1\|2026-10-20T17:40:59` = 엔진 기동 시각에서 멈춤(2026-10-22 14시 조회). `set_engine_status` 는 기동·정지 때만 호출(`engine/engine_runner.py:120,173,198`, `engine/engine_manager.py:198,268,425`) | 엔진이 죽어도 「동작 중」 표시. 대안: `audit_buy_eval.timestamp`(분마다), `accounts.updated_at`(LIVE 60초) 경과 시간 |
| F7-c | get_running_mode 는 프로세스 메모리만 | 확인됨 | `engine/engine_manager.py:119-123` | 별도 프로세스에서 Mode Lock Guard 재사용 불가 |
| F8 | 엔진에 429·418 처리 없음 | 확인됨 | grep 0건 | 백로그 |
| F9 | 잔고·포지션 DB 기록 | 일부 | LIVE: `engine/order_reconciler.py:23` 60초 주기, `:733,741,845,848`. 서버 `account_history` 1분 간격. KRW 는 `int()` 절사(`services/db.py:2329-2340`). TEST 는 주기 동기화 대상 아님(`:723-728`) | 평가손익용 현재가 출처 없음. TEST 에서 기록 시각이 멈춰 보임 |
| F10 | settings_history 화이트리스트에 v2·PULLBACK 없음 | 확인됨 | `services/settings_history.py:39-44`, `_validate` `:95-99` | 확장 필요 |
| F11 | scoped_params_path 이름 규칙 | 확인됨(조건부) | `engine/params.py:301-319`, 기본 이름 `config.py:26` `latest_params.json` | spec 4.5 `{user}_PULLBACK_params.json` 과 불일치. `engine.params` import 시 config·streamlit·키 로드 |
| B-1 | 1차 배포에 tradebot 재시작 없음 | **반박됨** | 서버 `.streamlit/config.toml:2` `fileWatcherType = "none"`. Streamlit 1.46 은 파일 감시가 꺼지면 스크립트 캐시를 비우지 않음(`app_session.py:474`). Streamlit 은 엔진과 같은 프로세스(`scripts/tradebot_boot.py:44-67`) | 입장 버튼(`app.py`) 반영·제거에 tradebot 재시작 필요 |
| B-2 | 업비트 시세 한도 IP 공유, 429 누적 → 418 | 확인됨 | https://docs.upbit.com/kr/reference/rate-limits 원문 「같은 IP의 모든 요청은 하나의 한도를 공유합니다」, 「418 … 429 누적으로 일시 차단 (동일 IP·포켓·커넥션 단위)」 | — |
| B-3 | 브라우저(Origin) 요청 10초당 1회 | 확인됨 | 문서 원문 + 로컬 1회 호출 `access-control-allow-origin: *`, `remaining-req: group=origin; min=6; sec=0` | 30초 1회는 한도 안. 같은 브라우저의 두 번째 요청(현재가·다른 탭·새로고침)은 초과 |
| B-4 | 차트 200봉 1회 요청 | spec 모순 | MA200 은 200봉으로 마지막 1점만 계산됨. 400봉은 2회 요청 → 한도 | MA200 표시 불가 |
| B-5 | 휴대폰 브라우저 직접 호출 | 미확인 | 실측 수단 없음 | 1단계 V2 |
| B-6 | 메모리 로컬 측정 | 미확인(방법 부적절) | 로컬 venv 없음, 서버 Python 3.12 | 서버 측정 필요 |

## 2. 지적 (심각도 순)

| # | 심각도 | 지적 | 권고 |
|---|---|---|---|
| 1 | 실매매 | 1차 배포에 엔진 재시작 필요(B-1). A2 「엔진 기동 시각 불변」은 1차 배포에 성립 안 함 | 배포 절에 tradebot 재시작 1회 + 기존 재시작 점검(WO-12 재개, 봉 누락 확인). A2 범위를 「1차 배포 뒤 tradebot-v2 재시작·정지」로 좁힘. 입장 버튼은 허용 목록 파일을 렌더마다 읽어, 닫을 때 재시작이 필요 없게 |
| 2 | 실매매 | 「엔진 동작」 출처 engine_status 는 주기 갱신 없음(F7-b) | 생존 판단은 `audit_buy_eval` 최신 시각과 `accounts.updated_at`(LIVE) 경과 시간. 1단계 V1 기대값 변경 |
| 3 | 보안 | `services/db.py`·`services/settings_history.py`·`engine/params.py` → `config` → `import streamlit` + 업비트 키 로드(`config.py:1-21`). 키 없으면 EnvironmentError. secrets.toml 없을 때의 `StreamlitSecretNotFoundError` 는 `except KeyError` 에 안 잡힘 | config·streamlit 없는 v2 전용 경량 DB 모듈. 유닛에 EnvironmentFile 없음. A14 시험: 기동 후 `sys.modules` 에 config·streamlit·pyupbit 없음, 환경에 `UPBIT_*` 없음 |
| 4 | 보안 | v2 실행 계정 미정(`/root` 700, 파일 root 소유 → 사실상 root). 1회용 토큰 서명 키 보관 미정 | 유닛 초안에 실행 계정과 이유. 서명 키는 새 비밀 파일(600, 사본 금지, 정기 점검). 허용 목록 파일 권한. 토큰 `?t=` 가 nginx access log 에 남는 점 Review Focus |
| 5 | 데이터 | 「DB 읽기 전용」과 settings_history 쓰기 불일치. `get_db` 는 매 연결 `PRAGMA journal_mode=WAL`, 없는 user_id 면 DB 파일 생성(서버에 `tradebot_.db` 존재). `engine/boot_resume.py:54` 가 `tradebot_*.db` glob | 읽기 `file:...?mode=ro`, 쓰기는 settings_history INSERT 1문장 짧은 트랜잭션, 파일 없으면 거부. 조회 LIMIT·인덱스·시간 제한(DB 947MB, 긴 읽기는 체크포인트 지연) |
| 6 | 누락 | 홈 평가손익의 현재가 출처 없음 | 결정 5 |
| 7 | spec 모순 | MA200 은 200봉 1회 요청으로 불가 | 결정 4 |
| 8 | 누락 | 「구버전으로」 링크는 재로그인 필요(F5). A4 「재로그인 없음」과 충돌 | 재로그인 수용 + 문구 반영, 또는 새 탭 |
| 9 | 누락 | TEST/LIVE 가 같은 테이블(accounts 는 user 당 1행). 토큰 모드와 `engine_status.last_mode` 불일치 시 혼동 | 홈 모드 배지·자산은 `last_mode` 기준, 입장 모드와 다르면 경고 |
| 10 | spec·규칙 | A14 lint 「api.upbit.com 금지」를 v2 전체에 걸면 브라우저 차트 JS 가 걸림 | lint 는 서버 Python 과 그 import 그래프. 정적 JS 는 허용 도메인 목록 |
| 11 | 데이터 | 화이트리스트에 PULLBACK 을 넣으면 구버전 `pages/settings_history.py` 「All」에 PULLBACK 행 표시·`restore_snapshot` 복원 가능(`pages/settings_history.py:113-115,485-491`, `services/settings_history.py:459-496`) | A1 회귀 시험에 포함하거나 구버전 화면에서 제외 |
| 12 | 실매매(수명주기) | 두 서비스가 같은 작업 트리. v2 배포 `git pull` 이 엔진 파일도 바꿈. 엔진의 늦은 import(`services/settings_history.py:515`, `engine/order_reconciler.py:764`)가 섞인 코드를 읽을 수 있음 | 배포 전 `git diff --stat <서버HEAD> <배포HEAD>` 가 v2·문서·`app.py` 만인지 확인 |
| 13 | 누락(P3) | spec 4.4 「엔진이 받은 확정 봉 기록」에 해당하는 OHLC 테이블 없음 | spec 4.4 에 「엔진에 봉 기록 기능 신설」 명시 |
| 14 | spec 모순 | spec 개정본 잔존 문구: (a) §2 실패 조건 「API 스레드…엔진 스레드」 (b) §4.2 쿠키 1순위 (c) §4.6 Mode Lock Guard, §4.7·A11 `start_engine` 인자화 — **별도 프로세스에서 호출하면 v2 안에 두 번째 엔진이 떠 이중 매매 위험** (d) §4.5 파일 이름 (e) HANDOFF [3] 구 내용 | §2·§4.2·§4.6·§4.7·A11 을 별도 프로세스 기준으로. P4 엔진 제어는 「엔진 프로세스가 DB·파일 명령을 읽는 방식」 등으로 재설계한다고 명시 |
| 15 | 규칙 | 목차에 명시 안 됨: `dashboard.py` 버전 갱신과 「버전: 구 → 신」 표기, heredoc 금지, 비밀 값 비기재·새 비밀 파일 600, Fable 보고 zip | Global Constraints·배포 절에 한 줄씩 |
| 16 | 개선 | 유닛 자원 제한 없음(tradebot 도 `MemoryMax=infinity`, `OOMScoreAdjust=0`). v2 누수 시 OOM killer 가 엔진을 고를 수 있음 | tradebot-v2 에 `MemoryMax`(예 150M), `OOMScoreAdjust=500` 이상, `Nice`/`CPUWeight` + 시험 |

## 3. 영향 범위 (tradebot-v2 ↔ 실매매 엔진)

| 축 | 공유 | 최악의 실매매 영향 | 차단 수단 | 확인 시험 |
|---|---|---|---|---|
| 업비트 시세(IP) | v2 서버가 부르면 공유 | 429 누적 → 418 IP 차단 → 확정 봉 조회 실패 → 손절·익절 판정 정지 | D8 | A14(import 그래프, `sys.modules` 에 pyupbit 없음), A15 |
| 업비트 거래·자산(포켓) | 키를 로드하면 공유 가능 | 주문·잔고 동기화 429 | 키 미로드, EnvironmentFile 없음 | 환경 `UPBIT_*` 없음·config 미import 시험 |
| 투자자 브라우저(Origin) | 공유 안 함(투자자 IP) | 없음. 차트만 멈춤 | 30초 1회, 숨김 탭 정지 | 휴대폰 실측(V2), 동시 요청 수 시험 |
| 프로세스 | GIL·크래시는 분리. CPU 6코어·RAM 1.96GB·페이지 캐시 공유 | v2 누수 → OOM killer 가 엔진 종료 | MemoryMax, OOMScoreAdjust, Nice | 상한 초과 시 v2만 종료(A3 보강) |
| 수명주기 | 작업 트리 공유. 1차 배포는 tradebot 재시작 | 재시작 중 봉 누락·재개 실패, 섞인 코드 | 재시작 절차, diff 범위 확인 | A2(범위 수정), 배포 직후 봉 누락 0 |
| DB 잠금 | 같은 WAL DB | 긴 읽기 → 체크포인트 지연·WAL 비대. 쓰기 겹침 busy(엔진 busy_timeout 3000ms, `services/db.py:44`). 잘못된 user_id 로 DB 파일 생성 → boot_resume 대상 | ro URI, 쓰기 1문장, LIMIT·시간 제한, 파일 생성 금지 | 동시 부하 시험, 없는 user 파일 미생성 시험 |
| 설정 파일 | 같은 폴더 params JSON | 이름 규칙 오류 시 EMA·MACD 파일 덮어씀 | `_PULLBACK` 접미사 고정, 저장 경로 화이트리스트 | 「엔진이 읽지 않음」, EMA·MACD 파일 해시 불변 |
| 자격증명 | config import 시 공유 | v2 침해 → 실계좌 키 유출 | 키 없이 기동, 실행 계정 분리 검토 | 키 파일을 못 읽는 상태에서 v2 기동 시험 |

## 4. 결정 완료 (2026-10-22 사용자 결정 — 결정 1~5 는 spec 3.1절 E1~E5, 결정 6·7 은 문서 반영, 커밋 `ee6efc4`)

| # | 결정 | 선택지 | 권고 | 결정 결과 |
|---|---|---|---|---|
| 1 | 1차 배포의 엔진 재시작 | (a) 입장 버튼과 함께 1회 재시작 (b) 버튼 없이 v2 먼저, 주소 따로 안내 | (a) + 봉 누락 확인 절차 | (a) — spec E1 |
| 2 | v2 DB·설정 접근 | (a) 기존 모듈 재사용(키 로드) (b) 키·streamlit 없는 v2 전용 경량 모듈 | (b) | (b) — spec E2 |
| 3 | 「엔진 동작」 출처 | (a) engine_status (b) audit_buy_eval·accounts.updated_at 경과 시간 | (b) | (b) — spec E3 |
| 4 | 차트 MA200 | (a) 1차 제외 (b) 첫 로드만 2회 요청(10초 간격) | (a) | (a) — spec E4 |
| 5 | 평가손익 현재가 | (a) 차트 마지막 봉 종가 (b) 엔진 기록 가격 + 기록 시각 | (b) | (b) — spec E5 |
| 6 | spec 옛 문구·HANDOFF [3] 정리, P4 엔진 제어 재설계 명시 | plan 작성 전 / 후 | 작성 전 | 작성 전 — 완료(spec 2절 실패 조건·4.2·4.5·4.6·4.7·A11, pullback spec 4.2, HANDOFF 3판, `ee6efc4`) |
| 7 | CLAUDE.md 「에이전트 운용」 절 추가 | 적용 / 수정 | 적용 (diff 는 HANDOFF 5절) | 적용 — 완료(`ee6efc4`, 「축적된 규칙」 절 포함) |

- 목차 2판 C절의 Q1~Q7 결정은 spec 3.1절 E6~E12 에 있다(Q1→E6, Q2→E12, Q3→E7, Q4→E8, Q5→E9, Q6→E10, Q7→E11). E13(W2)·E14(사용자 요구)는 Q1~Q7 밖의 추가 결정이다.
