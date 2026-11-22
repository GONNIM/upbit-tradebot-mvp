# 질의: 업비트 키 만료 미리 알림(1122-01) 계획 3판을 사용자 승인에 올리려 함

**지금 단계:** 계획 (사용자 승인 요청 직전)
**다음에 하려는 일:** 계획 승인을 사용자에게 요청한다. 승인되면 계획 문서를 docs/plans/2026-11-22-key-expiry-alert/plan.md 에 기록하고 구현한다(커밋·배포는 각각 따로 승인).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 지시(11/22): 「㉠ 적용 - 알림 및 페이지상에서 투자자(사용자)가 확인할 수 있도록 고려하시오」 | 확인 | 대화 |
| 2 | 업비트 GET /v1/api_keys: JWT 인증, 별도 권한 불필요, 응답 [{access_key, expire_at(yyyy-MM-dd'T'HH:mm:ss+09:00)}], default 그룹 초당 30회 | 확인 | https://docs.upbit.com/kr/reference/list-api-keys (11/22 열람, 페이지 갱신 2026-11-04) |
| 3 | 서버 실측: 응답 200, 항목 2개(칸 access_key·expire_at), 지금 키 항목 1개 expire_at 2027-11-19T12:21:56+09:00, 옛 키 1개 2026-11-18T23:08:39+09:00 | 확인 | 11/22 11:47 key5_read.sh 출력(사용자 `!` 실행, 대화 기록) |
| 4 | 엔진이 실제로 쓰는 키는 .env 의 UPBIT_ACCESS/SECRET(secrets.toml 최상위에 그 키 없음 → config.py:9-18 KeyError → .env, tradebot EnvironmentFile=.env) | 확인 | config.py:9-18, 서버 실측 #3 |
| 5 | 텔레그램 채널은 .env 의 TELEGRAM_CHAT_ID·TELEGRAM_CHAT_ID_OPERATOR 둘뿐, 둘 다 개인 채팅이고 값이 같음 → 알림은 운영자에게만 감. 투자자 채널 없음 | 확인 | 서버 실측 #3, HANDOFF 1031-05 |
| 6 | 독립 스크립트에서 `import config` 는 작업 폴더에 secrets 가 없으면 StreamlitSecretNotFoundError 로 실패(KeyError 아님) | 확인(verifier 재현) | config.py:13, streamlit errors.py:463 |
| 7 | v2 status 의 _guard 는 FileNotFoundError 를 응답 전체 404 로 바꿈. status 키 집합·홈 배지 개수·위치를 고정한 시험이 있음 | 확인 | v2/api_read.py:420-426, tests/v2/test_api_read.py:392-394, tests/v2/js/home.test.mjs:32, tests/v2/js/pullback_home.test.mjs:31-34·156-158 |
| 8 | tradebot-v2 는 services/data 를 읽고 쓸 수 있고 .env·secrets.toml 은 막혀 있음 | 확인 | deploy/tradebot-v2.service:21·27·28 |
| 9 | 서버 시간대 Asia/Seoul, flock 있음, 기존 cron 09:00 daily_digest | 확인 | 서버 실측 #3 |
| 10 | 만료된 키로 /v1/api_keys 를 부르면 401 expired_access_key 가 온다 | 추정 | core/trader.py:81·94 오류 코드 목록, 문서에 오류 응답 없음 |
| 11 | 새 키는 계좌 주인의 업비트 계정에서 발급한다 | 추정 | 업비트 마이페이지 Open API 관리(이번에 열지 않음). 사용자에게 「누가 발급」을 물음 |

## 계획 요지
- 스크립트 scripts/key_expiry_check.py(cron 매일 09:05, `cd 저장소 &&`, flock, timeout 5초, 재시도 없음): 저장소 루트로 chdir → .env 를 직접 읽음(load_dotenv override=False) → query 없는 JWT → /v1/api_keys → 지금 access_key 항목 expire_at 만 → services/data/.key_expiry.json(600, 임시 파일 뒤 os.replace) 칸 expire_at·last_ok_at·checked_at·first_fail_at·error_code·last_alert_step·last_alert_date. 실패해도 마지막 성공 expire_at 유지. 401 expired_access_key 는 「만료됨」.
- 알림: 30·14·7·3·1·0일 단계에 처음 들어갈 때 한 번, 만료 뒤 하루 1번. notifier.send(level 지정) 기본 채널 = 지금은 운영자 개인 채팅. 조회 실패 2일 이상은 audience="operator". notifier 로거를 끄고 cron 출력은 600 로그나 /dev/null. core.trader·pyupbit 를 import 하지 않음.
- 화면: GET /v2/api/status 에 key_expiry{expire_at, days_left, level, last_ok_at}(요청 시각 KST 로 계산, 파일 없으면 키 뺌, 읽기 예외 그 자리에서 잡음). 홈 배지 줄 맨 끝에 배지 하나(31일 이상 보통 · 30일 이하 경고 · 7일 이하·만료·last_ok_at 2일 넘음 위험/「확인 안 됨」). style.css 에 위험색 클래스 하나 추가.
- 엔진·매매 규칙·DB 는 고치지 않음, 엔진 재시작 없음. 배포 = git pull + tradebot-v2 재시작 + crontab 한 줄 설치 + 손으로 1회 실행. 투자자 체감 변경(홈 배지) 안내 뒤 연락 기록.
- 시험(바깥 연결 없음): 단계 경계, 중복 없음, 만료 뒤 하루 1번, 401·네트워크·시간 초과, 배열 아님·빈 배열·지금 키 없음·같은 키 2개·시간대 없는 형식, 결과 파일 600, 출력·파일에 업비트 키·텔레그램 토큰 없음, status 파일 없음/깨짐 때 200, 배지 색 경계, 주문 경로 import 없음.
- 정할 것(사용자): ① 새 키 발급 주체(알림 문구) ② 투자자 텔레그램 채널을 새로 둘지(투자자 채팅 ID 를 받아 .env 에 키 추가 = 서버 설정 변경, 투자자 연락 필요) — 권고: 지금은 홈 배지로 투자자, 텔레그램은 운영자.

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 계획에 사실 오류나 실매매(엔진·주문·키)에 닿는 위험이 남았는가 | 엔진과 떨어진 프로세스, 하루 1번 GET 이라 영향 없음 |
| 2 | 「투자자(사용자)」 지시를 홈 배지 + 운영자 텔레그램으로 채우는 것이 지시와 맞는가, 투자자 채널은 사용자 결정으로 올리는 것이 맞는가 | 맞다 — 투자자 채널은 서버 설정 변경·투자자 연락이 필요 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/key-expiry-plan-draft.md (3판 절 → 2판 고침 → 1판 본문 순으로 우선)
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/key5.py (서버 실측 원본)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/config.py, services/notifier.py, scripts/v2/notify_operator_test.py, v2/api_read.py, v2/static/app.js, deploy/tradebot-v2.service, deploy/v2hist-backup.cron
- 규칙: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1회째 요지 (Fable · 11/22)

- 판정: 수정 후 진행. 엔진·주문 위험 없음, 사실 오류 없음(문서 직접 확인). 막음 2: ① 키 교체(expire_at 바뀜) 때 단계 기록을 비우지 않으면 다음 해 알림이 빠짐 ② 만료·단계 판정을 응답이 아니라 저장된 expire_at 과 지금 시각으로 — 401 이름이 추정(#10)이라. 권고: 키 읽기 config 순서, 옛 키 expire_at 과 journal 대조, 남은 날 계산 함수 하나로 공유·정의, cron 미실행 위험·정기 점검, v2 결과 파일 경로 시험용 교체, 배지는 v2 홈에만임을 승인 요청에 적기. 사용자에게: 키 발급 주체, 투자자 텔레그램 채널, 발급 부탁 연락이 투자자 연락 원칙에 없음, 구버전 대시보드 배지.
- 반영: 계획 4판 F1~F8(막음 2 · 권고 3·5·6·7·8 반영, 권고 4 는 결과를 바꾸지 않아 뒤로 미룸). 다시 묻기(2회째)로 확인받음.


# 답변 2회째 요지 (Fable · 11/22)

- 판정: 진행. 막음 1·2 는 4판 F1·F2 로 풀림, 새 사실 오류·엔진 위험 없음. 권고 4: 배지 판정 순서(만료됨 먼저), 단계 판정 ≤ 와 건너뛴 날 시험, 401 운영자 알림 하루 1번, plan.md 에 4판 내용만. 권고 4(journal 대조) 미뤄도 됨. 사용자에게: 결정 4가지 + 「텔레그램은 지금 운영자에게만」「배지는 신버전 홈에만」을 사실로 적기.
- 반영: 계획 4판 F9~F12.
