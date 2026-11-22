# 업비트 키 만료 미리 알림 (1122-01) 계획

- 승인: 2026-11-22 사용자 「1122-01 ① 승인 ② 투자자 ③ 그대로 둠 ④ 그대로 둠」
  - ① 이 계획대로 만든다 · ② 새 키는 투자자가 발급한다(알림 문구) · ③ 투자자 텔레그램 채널은 두지 않는다 · ④ 구버전 Streamlit 화면은 고치지 않는다
- 배경: 1119-01 — 2026-11-19 07:51~13:06 키 만료(expired_access_key)로 실계좌 손절 매도가 거절됐다. 만료일을 미리 아는 장치가 없었다.
- 검토: verifier 1회(수정 후 승인 → 반영), Fable 2회(수정 후 진행 → 진행) — docs/fable/2026-11-22-key-expiry-plan-1.md

## 1. 근거 사실
| # | 사실 | 출처 |
|---|---|---|
| 1 | 업비트 GET https://api.upbit.com/v1/api_keys — JWT 인증, 별도 권한 불필요, 응답 [{access_key, expire_at}], expire_at 형식 yyyy-MM-dd'T'HH:mm:ss+09:00, default 그룹 초당 30회. 오류 응답은 문서에 없음 | https://docs.upbit.com/kr/reference/list-api-keys (2026-11-22 열람, 페이지 갱신 2026-11-04) |
| 2 | 서버 실측 2026-11-22 11:47 KST: 응답 200 · 항목 2개 · 지금 키 expire_at 2027-11-19T12:21:56+09:00 · 옛 키 2026-11-18T23:08:39+09:00 | 읽기 전용 실측(사용자 `!` 실행) |
| 3 | 서버 시간대 Asia/Seoul · flock 있음 · venv Python 3.12.8 · 기존 cron 09:00 daily_digest | 같은 실측 |
| 4 | 엔진이 쓰는 키: secrets.toml 최상위에 UPBIT_ACCESS 가 없어 config.py 는 KeyError → .env (tradebot EnvironmentFile=.env) | config.py:9-18, 같은 실측 |
| 5 | 텔레그램: .env 의 TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_OPERATOR, 둘 다 개인 채팅 → 알림은 지금 운영자에게만 감 | 같은 실측, HANDOFF 1031-05 |
| 6 | 독립 프로세스에서 `import config` 는 작업 폴더에 secrets 가 없으면 StreamlitSecretNotFoundError(KeyError 아님)로 실패 | verifier 재현 |

## 2. 범위 원칙
- 엔진(tradebot)·매매 규칙·DB 스키마는 고치지 않는다. 엔진 재시작 없음. config.py 는 고치지 않는다.
- 키 값·텔레그램 토큰·채팅 번호·업비트 응답 원문은 어떤 파일·로그·화면·알림에도 쓰지 않는다.
- tradebot-v2 는 비밀 파일을 읽지 않는다(deploy/tradebot-v2.service InaccessiblePaths 그대로). 키를 쓰는 조회는 점검 스크립트만 한다.
- 점검 스크립트는 core.trader·pyupbit·config 를 import 하지 않는다.

## 3. 만드는 것
### 3-1. 계산 함수 — services/key_expiry.py (새 파일, 비밀을 읽지 않음)
- 결과 파일 경로 상수 RESULT_FILE = services/data/.key_expiry.json (시험에서 바꿀 수 있게 함수 인자·모듈 상수).
- days_left(expire_at, now): KST 달력 날짜 차(expire_at 날짜 − 오늘 날짜). expire_at 시각이 지났으면 「만료됨」.
- 단계 STEPS = (30, 14, 7, 3, 1, 0). 보낼 단계 = 「남은 날 ≤ 단계」인 단계 가운데 가장 작은 것, 단 그 (expire_at, 단계) 짝을 아직 안 보냈을 때만. 여러 단계를 한꺼번에 건너뛰면 가장 가까운 단계 1번만.
- 배지 판정 순서: 저장 expire_at 지남 「만료됨」(위험) → last_ok_at 이 2일 넘음 「확인 안 됨」(위험) → 7일 이하(위험) → 30일 이하(경고) → 보통.
- 결과 파일 읽기(깨짐·없음·권한 오류는 None)와 원자적 쓰기(임시 파일 → os.replace, 권한 600).

### 3-2. 점검 스크립트 — scripts/key_expiry_check.py (새 파일)
1. 저장소 루트로 chdir.
2. 업비트 키: config.py 와 같은 순서 — secrets.toml 최상위 UPBIT_ACCESS/UPBIT_SECRET(tomllib) → 없으면 .env. 텔레그램 값은 .env 를 load_dotenv(override=False)로 직접 읽는다(scripts/v2/notify_operator_test.py 방식).
3. services.notifier 로거를 끈다(예외 로그에 토큰 든 URL 이 섞일 수 있음).
4. query 없는 JWT(access_key·nonce, HS256) → GET /v1/api_keys, timeout 5초, 재시도 없음.
5. 응답 처리: 배열이고 지금 access_key 항목이 정확히 1개이고 expire_at 이 시간대 있는 형식이면 성공. 그 밖(배열 아님·빈 배열·지금 키 없음·같은 키 2개·시간대 없음·500·네트워크·시간 초과)은 실패. 401 은 따로 표시.
6. 결과 파일 칸: expire_at, last_ok_at, checked_at, first_fail_at, error_code, alerts{(expire_at, 단계)}, last_alert_date, last_fail_alert_date.
   - 새로 받은 expire_at 이 저장값과 다르면(키 교체) 알림 기록·first_fail_at 을 비운다.
   - 실패해도 마지막으로 성공한 expire_at 을 유지한다.
7. 알림 판정은 조회 응답이 아니라 저장된 expire_at 과 지금 시각으로 한다(조회가 실패해도 단계 알림·만료 알림이 나감).
   - 단계 알림: 3-1 규칙대로, 기본 채널(level WARNING, 7일 이하는 CRITICAL).
   - 만료 뒤: 하루 1번(last_alert_date).
   - 401: 이름과 상관없이 그날 바로 운영자 채널(audience="operator"), 하루 1번(last_fail_alert_date). 그 밖의 실패는 first_fail_at 부터 2일 넘게 이어지면 운영자 채널, 하루 1번. 지금은 두 채널이 같은 채팅이라 같은 날 만료 알림과 겹치면 한 건으로 합친다.
8. 출력은 짧은 상태 줄(성공/실패 · 남은 날 · 보낸 알림 수)만. 키·토큰·응답 원문 없음.

알림 문구(투자자용, ② 결정): 「업비트 Open API 키가 2027-11-19 12:21 에 만료됩니다(30일 남음). 만료되면 자동 매매 주문이 거절됩니다. 투자자님이 업비트에서 새 키를 발급해 운영자에게 전해 주세요.」 만료 뒤: 「업비트 Open API 키가 만료되었습니다. 자동 매매 주문이 거절됩니다. 새 키를 발급해 운영자에게 전해 주세요.」

### 3-3. cron — deploy/key-expiry.cron (새 파일, 설치는 배포 승인 대상)
`5 9 * * * cd /root/upbit-tradebot-mvp && umask 077 && flock -n /tmp/key_expiry.lock nice -n 10 timeout 60 venv/bin/python scripts/key_expiry_check.py >> services/data/key_expiry_cron.log 2>&1`

### 3-4. 화면 — v2
- v2/api_read.py StatusHandler: 결과 파일을 읽어 key_expiry {expire_at, days_left, level, label, last_ok_at} 를 요청 시각(KST)으로 계산해 더한다. 읽기 예외는 그 자리에서 잡는다(_guard 가 FileNotFoundError 를 404 로 바꾸므로). 파일이 없거나 못 읽으면 key_expiry 키 자체를 뺀다(tests/v2/test_api_read.py:392-394 키 집합 고정).
- v2/static/app.js: 홈 배지 줄 맨 끝에 push(tests/v2/js/home.test.mjs:32, pullback_home.test.mjs:31-34·156-158 위치·개수 고정). 글: 「업비트 키 · 2027-11-19 만료 (362일 남음)」 / 「업비트 키 만료됨 — 새 키 필요」 / 「업비트 키 만료일 확인 안 됨 (마지막으로 받은 만료일 2027-11-19)」(verifier 지적으로 날짜 뜻을 밝힘).
- v2/static/style.css: 위험색 배지 클래스 하나 추가(지금 .p-live·.p-off·.p-run·.p-st·.p-warn 뿐).
- 구버전 Streamlit 화면은 고치지 않는다(④).

## 4. 시험 (바깥 연결 없음 — requests 가짜 응답, notifier 가짜)
- 남은 날 경계 31/30/29, 건너뛴 날(31→29 = 30일 단계 1번, 15→6 = 7일 단계 1번), 같은 단계 중복 없음
- 키 교체: 7일 단계까지 보낸 뒤 expire_at 이 1년 뒤로 → 기록 비워짐 → 새 만료일 30일 전에 다시 알림
- 저장 expire_at 지남 + 응답 401 다른 이름 / 500 / 시간 초과 → 그날 만료 알림 1번, 만료 뒤 401 3일 → 하루 1건
- 조회 실패 중 14일 단계 진입 → 단계 알림 감, 실패 2일 → 운영자 알림 1번
- 응답 형식: 배열 아님 · 빈 배열 · 지금 키 없음 · 같은 키 2개 · 시간대 없음
- 키 읽기 출처: secrets.toml 최상위 있음/없음
- 결과 파일 권한 600, 출력·결과 파일에 업비트 키·텔레그램 토큰 문자열 없음
- 스크립트·계산 함수가 core.trader·pyupbit·config 를 import 하지 않음(정적 시험)
- v2 status: 파일 없음/깨짐/권한 오류 때 200 · key_expiry 칸 · 배지 판정 순서(만료됨이 확인 안 됨보다 먼저) · 실제 결과 파일 유무와 상관없이 시험 통과(경로 교체)
- JS: 배지 맨 끝 · 글·색 경계

## 5. 순서
1. 구현(3-1~3-4) + 시험(4)
2. 게이트: scripts/regression_gate.sh, JS 시험, 바깥 연결 0
3. 브라우저 실측(PC·412px): 배지 보통·경고·위험·확인 안 됨, 배지 없음(파일 없음)
4. verifier → Fable → 커밋 승인 요청(dashboard.py 버전 갱신)
5. 투자자 체감 변경 안내(홈 배지) 초안 → 배포 승인 요청(git pull · tradebot-v2 만 재시작 · crontab 한 줄 설치 · 스크립트 손으로 1회 실행해 결과 파일·배지 확인 · 엔진 기동 시각 그대로) → 다음 날 09:05 실행 확인 → 보고 · 연락 기록

## 6. 위험과 되돌리기
- cron 이 돌지 않으면 텔레그램으로는 모른다 → 배지 「확인 안 됨」 + 세션 시작 정기 점검에 결과 파일 checked_at 날짜 확인 한 줄.
- 키 교체 뒤 결과 파일이 옛 만료일을 보여 줄 수 있음 → 다음 09:05 까지. 키 교체 절차에 「점검 스크립트 손으로 1회 실행」을 더한다.
- 텔레그램 알림은 지금 운영자에게만 간다(③). 투자자에게는 홈 배지와 운영자의 전달로 닿는다.
- 투자자에게 키 발급을 부탁하는 연락은 투자자 연락 원칙의 세 번째 종류로 더한다(② 결정).
- 1121-03 과 같은 파일(app.js·api_read.py)을 고친다. 커밋을 따로 하고, 먼저 들어간 쪽 위에 다시 맞춘다.
- 하지 않음: 옛 키 expire_at 과 실제 거절 시작 시각 대조(알림이 30일 전부터라 결과를 바꾸지 않음).
- 되돌리기: crontab 줄 지움 → 결과 파일 치움 → v2 이전 커밋으로 되돌려 tradebot-v2 재시작.

## 7. 구현에서 달라진 점 (2026-11-22 · verifier 2회 승인 · Fable 진행 · 커밋 승인 요청에 적음)
위 3절 본문은 승인된 그대로 두고, 실제 구현과 다른 곳만 여기에 적는다.
1. 계산 함수 위치: services/key_expiry.py → v2/key_expiry.py. tests/v2/test_server.py:234 가 v2 의 services import 를 막기 때문. 표준 라이브러리만 쓰고 비밀을 읽지 않는다. 점검 스크립트도 이 모듈을 쓴다.
2. cron: 하루 1번(09:05) → 하루 2번(09:05·21:05). 만료 당일(만료 시각 12:21 무렵) 「만료됨」 알림을 그날 안에 보내기 위해서다. 같은 알림은 하루 1번만 나간다.
3. 만료 뒤 알림 기록 칸을 last_expired_alert_date 로 단계 알림(last_alert_date)과 나눴다. 만료 당일 09:05 「오늘 만료」와 21:05 「만료됨」이 각각 나가게 하려는 것이다. 키를 바꾸면 이 칸도 비운다.
4. 텔레그램 보내기가 실패한 알림은 기록하지 않는다. 다음 실행(12시간 뒤)에 다시 보낸다.
5. 「확인 안 됨」 배지 글: 「업비트 키 만료일 확인 안 됨 (마지막으로 받은 만료일 YYYY-MM-DD)」(날짜 뜻을 밝힘, 3-4 에 반영).
6. 같은 채널 판정: WARNING·CRITICAL 두 등급 채널이 모두 운영자 채팅과 같을 때만 한 건으로 합친다. 같은 실행 안에서만 합친다.
7. 끝 값(0001-01-01 등)·깨진 결과 파일은 None 으로 보고 홈 상태 응답이 500 이 되지 않게 했다(OverflowError·RecursionError).
8. 문서: project-rules.md 에 투자자 연락 세 번째 종류(키 발급 부탁) · 세션 시작 정기 점검 한 줄 · 키 교체 뒤 손 실행 한 줄을 더했다(버전 2.15).
