# 모든 알림 투자자 사본 보내기 (1122-01 ②~④) 계획 — 4판

- **설계 바뀜 (2026-11-24 22시대, 사용자 지시 「투자자도 내(개발자)가 받는 알림 그대로 받으면 된다. 가공하거나 수정할 필요가 전혀 없다.」)**: 사본 글은 운영자가 받는 글과 바이트까지 같다. 그래서 4절(글 바꾸기 규칙·위치별 문구) 전부 · 3-4 의 점검 실패 고정 문장 · 3-1 의 investor_title/investor_body 인자 · 5절의 셸 줄 삭제·쉬운 문구·같은 제목 30분 1번 제한 · 6절의 글 바꾸기 시험과 전수 시험표(alert-test-table.md) · 7절 문장 (가)의 「줄임」 부분 · 7절 (다)의 「내부 이름은 사본에서 줄인다」 · 7절 코드 주석 지시 「투자자 사본은 내부 이름을 줄여 간다」는 **없앴다**(본문은 기록으로만 남김). 남긴 것: 일꾼 스레드·대기 줄 16·쉼(403·429·연속 실패)·끄는 파일·같은 채팅 건너뜀·토큰 안 남는 로그·curl -K -·상태 9가지·키 만료 단계 알림 사본 끔(직접 발송과 두 번 안 감)·운영자 채널 시험 사본 끔. 시험은 「사본 글 == 운영자 글」(파이썬·셸)과 호출 위치 62곳 수 고정으로 바꿨다. 아래 본문의 4절·5절 글 바꾸기 설명은 기록으로만 남긴다.
- **승인 (2026-11-24 21시대, 사용자 「1122-01 ㉠~㉢ 권고대로」)**: ㉠ 설계 승인(설계만 · 전수 시험표는 커밋 승인 요청 때 보임) · ㉡ 메모리 감시 자동 재시작은 (b) 나중에 따로(8절 3단계 판정 기준에 걸리면 다시 묻기) · ㉢ 7절 규칙 새 문장 3개 그대로 승인(구현 커밋 때 project-rules 고침).
- 검토: verifier 2회 고친 뒤 승인 → 반영 · Fable 1회 수정 후 진행 → 2회째 진행 (docs/fable/2026-11-23-all-alerts-plan-1.md).

- 4판 보완(11/23): Fable 2회째 「진행」 · 권고 4개 반영(할 일 줄 우선 · 9절 판정 기준 · (b) 남는 위험 · 11절 줄 번호 문장 삭제).

- 4판(11/23): Fable 「수정 후 진행」 반영. 승인 범위는 **설계만**이다. 「글 바꾸기가 56곳 + 셸 5개의 내부 낱말을 모두 가린다」는 **추정**이며, 통과 조건은 커밋 승인 요청 때 사용자에게 보이는 전수 시험표다(4절). 바뀐 곳: 4절 규칙 7(기본 문장에서 「하실 일 없음」 삭제) · 투자자 행동 칸 · 3-1 상태 분리(no_token/no_chat) · 3-2 일꾼 안전 · 3-4 점검 실패 고정 문장 · 5절 curl -K 에 chat_id · 6절 시험 추가 · 7절 문구 원문 · 8절 순서(끄는 파일 먼저) · 9절 결정 질문.
- (이전) 3판(11/23): verifier 2차 「수정 후 승인」 반영(send() 설계 하나로 통일 · 사유 줄 좁힘 · 키 만료 사본 = 실패 부분만 · flush 3초 · curl -K - 범위 · 출력 줄 copy 칸). 상태: 초안(코드·서버 변경 없음). 승인 전 verifier 재검증 → 사용자 보고.
- 사용자 지시 11/23: 「키 만료 알림만이 아니라 프로젝트에서 송출되는 알림을 모두 투자자가 받을 수 있어야 한다」. 결정 ② 운영자 전용도 사본으로 보내되 내부 말은 쉬운 말로 · ③ 셸 길 포함 · ④ 엔진 재시작은 눌림목 보유가 없을 때만.
- 값(토큰·채팅 번호)은 쓰지 않는다. 투자자 채팅은 서버 .env 의 TELEGRAM_CHAT_ID_INVESTOR(11/23 21:54 등록).

## 1. 근거 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 파이썬 알림은 services/notifier.py send() 한 곳을 지난다. 등급 채널 → 기본 채널, audience="operator" 는 OPERATOR 채널만 | 확인 | notifier.py:51~120, 150~219 |
| 2 | send() 의 일찍 돌아가는 곳: dry-run(173) · dedupe(180) · 운영자 채팅 없음(185) · 자격 없음(191) · requests 없음(193) · 성공 return(207~210) · 실패 return(211~215) · 예외(216~219). 성공·실패 return 이 앞에 있어 「끝」에 후크를 둘 수 없다 | 확인 | notifier.py:173~219 |
| 3 | import 줄 56 = core 30 · engine 17 · services 2 · pages 6(confirm_init_db.py:55 포함) · scripts 1(daily_health_check.py:220). import 수 ≠ 호출 수: live_loop.py:260 은 별칭 notify, strategy_switch.py:289·1103 은 ctl.notify, boot_resume.py:104 는 감싼 함수. 따로 직접 호출: key_expiry_check.py:221 · scripts/v2/notify_operator_test.py:66 | 확인 | `grep -rn "from services.notifier import" core engine services pages scripts --include='*.py'` (11/23 재실행, 위 분포 일치) |
| 4 | 운영자 전용 발송 지점 **5곳**(`grep -rn audience core engine services pages scripts v2 --include='*.py'` 에서 notifier 밖 `audience=` 전달 줄 기준): engine_manager.py:384 · 625 · strategy_switch.py:271(래퍼, 호출자 310 TABLE_MISSING · 918 DONE_RECORD) · key_expiry_check.py:221(알림이 audience 값을 담아 옴, 생산자 v2/key_expiry.py:147 「키 만료일 점검 실패」) · scripts/v2/notify_operator_test.py:66~67. 같은 grep 의 나머지 v2/key_expiry.py:104·119·130 은 audience=None 생산 줄이라 세지 않음 | 확인 | 위 grep 11/23 재실행 |
| 4-1 | 재시작 때 나가는 알림: engine/boot_resume.py 의 `_notify`(102~108, dedupe 600초)가 기동 재개 INFO 「🔄 서비스 기동 — LIVE 엔진 자동 재개」(174~177)와 실패 CRITICAL 「🚨 … 자동 재개 실패」(157~160 · 190~193)를 낸다 → 엔진 재시작 순간 사본이 가면 투자자가 재시작 알림을 먼저 받게 됨. 그래서 8절은 끄는 파일을 먼저 둔다 | 확인 | engine/boot_resume.py:102~108·157~193 |
| 5 | 엔진(tradebot)과 대시보드는 한 프로세스다(tradebot_boot.py:4~6, 193~205: 같은 프로세스에 Streamlit 서버 + 엔진 스레드). 그러므로 일꾼은 1개 | 확인 | scripts/tradebot_boot.py |
| 6 | 서버 cron(모두 활성): `*/10` memory · `*/5` watchdog · 매일 09:00 daily_digest · 월 09:00 weekly_digest · 일 11:00 cleanup · key_expiry_check 09:05·21:05. daily_health_check.py 는 cron 목록에 없음. /root 의 notify_telegram.sh 와 5개 스크립트 755 | 확인 | 서버 읽기 11/23 22:46 (조정자 전달) |
| 7 | watchdog 은 이미 LOCK_FILE · TTL 3600 dedupe 가 있음(watchdog_tradebot_engine.sh:13~31). memory·digest·cleanup 은 dedupe 없음 | 확인 | 해당 .sh |
| 8 | 엔진 최근 7일 [NOTIFY] sent 34건 = CRITICAL 20 · INFO 9 · WARNING 5(11/18 3 · 11/19 15 · 11/20 3 · 11/21 4 · 11/22 4 · 11/23 5). 하루 5건 안팎. 대시보드·cron 파이썬은 같은 journal 이 아니라 숫자에 없고, 셸은 로그가 없음 | 확인(엔진) / 추정(그 밖) | 서버 읽기 11/23 22:46 |
| 9 | 서버 .env: TELEGRAM_CHAT_ID 값 = OPERATOR 값. 등급별 키 없음. OPERATOR · INVESTOR 있음 | 확인 | 같은 서버 읽기 |
| 10 | 엔진은 .env 를 기동 때만 읽음. config.py:9~16 은 st.secrets 에 UPBIT_ACCESS 가 없을 때만 load_dotenv() 를 부름 → 어떤 환경에서는 .env 가 읽히지 않을 수 있음(엔진 기동 로그로 사본 on/off 를 직접 확인해야 함) | 확인(코드) | config.py:9~16 |
| 11 | requests 예외 글에 토큰 든 주소가 섞인다(urllib3 exceptions.py:99 가 URL 을 메시지에 넣음). 기존 notifier.py:218 `{e}` 가 그대로 로그에 남김 = 기존 결함 | 확인(코드·verifier) / 추정(서버 로그에 실제로 남았는지, 미확인) | notifier.py:218 |
| 12 | 눌림목 보유 중 재시작 안 함은 투자자 메뉴얼 약속 | 확인 | docs/new-version/ver/pullback-live-manual-20261110.html:61 |
| 13 | 시험 격리: regression_gate.sh 는 TELEGRAM_* 를 빈 값으로 export(INVESTOR 없음). netguard 가 api.telegram.org 를 막음 | 확인 | regression_gate.sh:28~32, tests/_netguard/guard.py:27·59 |
| 14 | memory 스크립트는 임계 초과 시 보유와 상관없이 `systemctl restart tradebot` 를 함(monitor_tradebot_memory.sh:35~40) — 메뉴얼 61행 약속과 어긋남 | 확인 | 해당 .sh |
| 15 | 미확인: 서버 streamlit fileWatcherType · 서버 unit 파일 · /root 셸 사본이 저장소 판과 같은지 · Telegram 403/429 한도 | 추정 | 배포 전 읽기 전용 서버 확인에 넣음(8절 3단계) |

## 2. 범위와 원칙
- 운영자 쪽(글·채널·dedupe·반환값)은 byte 단위로 그대로다. 「판정」과 「발송」을 나눠, 운영자 가지의 코드 순서와 반환값은 건드리지 않고 사본은 별도 줄로 덧붙인다.
- 매매·DB·전략 코드는 건드리지 않는다. 고치는 곳: notifier.py · 새 services/investor_copy.py · key_expiry_check.py · notify_telegram.sh · 셸 3개 · 문서·규칙·주석.
- 사본 실패가 운영자 발송·호출자에 영향을 주지 않는다. 토큰·채팅 번호·요청 주소는 로그·문서·알림에 쓰지 않는다.
- 자동 알림 사본은 투자자 연락 원칙의 「연락」이 아니다(원칙의 세 종류는 사람이 보내는 연락). 이 문장을 project-rules 479줄 고침 옆에 넣는다.

## 3. 만드는 것
### 3-1. send() 구조 (설계 하나)
- 지금 send() 본문(173~219)을 `_send_core(...)` 로 옮긴다. **분기와 순서는 그대로, return 값만 상태로 바꾼다**: `dry_run` · `dedupe` · `no_op_chat` · `no_token` · `no_chat` · `no_requests` · `sent` · `http_fail` · `exception`. (3판의 `no_creds` 를 둘로 나눔: `_get_credentials` 는 토큰·채팅 중 하나라도 없으면 둘 다 None 을 돌려줘(notifier.py:91~92) 어느 쪽이 없는지 모른다 → 상태를 정하는 자리에서 `os.environ` 의 토큰 유무를 따로 본다. 사본 길도 토큰을 스스로 찾는다: 환경변수 → streamlit secrets, 운영자 채팅과 무관.) (`_prepare`·스레드 지역 변수 안은 쓰지 않는다.)
- 바깥 `send()`: `status = _send_core(...)` → `ok = (status == "sent")` → 3-3 표대로 사본 큐 넣기(try/except 로 감쌈) → `return ok`. `ok` 는 지금 반환값(True 는 200 응답일 때만)과 모든 상태에서 같다.
- 새 인자 `investor_copy: bool = True`, 사본용 `investor_title=None`, `investor_body=None`(있으면 글 바꾸기 대신 이 글을 사본으로 쓴다).
- 시험: 3-3 표의 모든 행에서 변경 전과 변경 후 send() 의 bool 반환값이 같다(변경 전 값은 시험 안에 고정값으로 적음).

### 3-2. 일꾼과 프로세스별 방식 (막음 3)
| 프로세스 | 방식 | 까닭 |
|---|---|---|
| tradebot(엔진 + 대시보드, 한 프로세스) | 일꾼 스레드 1개(daemon) + 길이 16 대기 줄. 줄이 차면 새 글 버림 + `[NOTIFY-COPY] 대기 줄 가득` 로그(분당 1번) | 매매 스레드가 사본 때문에 5초 늦으면 안 됨 |
| cron 파이썬(key_expiry_check) | 같은 일꾼 + 종료 때 `flush(timeout=3)` | 한 번 돌고 끝나는 프로세스 |
| daily_health_check.py | 서버 cron 에 없음. 코드는 같은 길을 타므로 시험만 함. 어디서 도는지는 추정 | 사실 6 |
| 셸 5개 | 5절 | |
- **호출한 스레드는 큐에 (등급·제목·본문·키)만 넣는다.** 글 바꾸기(sanitize)와 끄는 파일 확인은 **일꾼 스레드 안**에서 한다(매매 스레드가 정규식·파일 접근으로 늦어지지 않게). 정적 시험: notifier.py 의 `send()` 가 `sanitize` 를 호출하지 않음.
- 일꾼 안전: 일꾼 본문은 모든 예외를 삼킨다 · 큐에 넣을 때마다 `is_alive()` 를 보고 죽었으면 새로 띄운다(띄우는 부분은 잠금 하나로 감싸 두 스레드가 동시에 띄우지 않게 함, 스레드 시작 실패는 흡수하고 `[NOTIFY-COPY] 일꾼 시작 실패` 로그 1줄) · 큐 넣기는 `put_nowait` 만(정적 시험이 `.put(` 사용·`block` 인자를 찾아 막음) · 짧은 `atexit` flush 를 모든 프로세스에 등록. **flush 대기 시간은 한 값 3초**(이전 초안의 3초·8초 혼용 정리). 권장 3초: 대기 줄이 길어도 종료가 최대 3초 늦어진다 → **tradebot 정지·재시작이 최대 3초 느려질 수 있음**을 배포 보고에 적는다.
- 알려진 한계: `timeout 60` 의 SIGTERM 과 `os._exit` 는 atexit 를 건너뛴다 → 그 경우 줄에 남은 사본은 사라진다. 하위 프로세스 시험 1개로 동작을 못 박는다(정상 종료는 사본 도착, SIGTERM 은 유실을 문서화).

### 3-3. send() 상황별 사본 여부 (막음 4)
| 상황 | 운영자 | 사본 |
|---|---|---|
| WO6_DRY_RUN=1 | 안 감 | 안 감 |
| dedupe 스킵 | 안 감 | 안 감 |
| `no_op_chat`: 운영자 전용인데 운영자 채팅 없음(185) | 안 감 | **간다**(확정: 운영자 채팅이 없어도 사본) |
| `no_chat`: 토큰 있음 · 기본 채팅 없음 · audience None(191) | 안 감 | **간다**(같은 원칙: 운영자 쪽 채팅이 없어도 사본. 토큰은 있으므로 보낼 수 있음) |
| `no_token`: 토큰 없음 / `no_requests` | 안 감 | 안 감(토큰 없이 못 보냄) |
| 운영자 발송 실패(`http_fail`·`exception`) | 실패 | 간다(별개 채팅). **한계**: 호출자가 다시 시도하면 사본이 반복될 수 있다 — key_expiry_check.py:224~226 은 운영자 발송 성공 때만 기록(marks)을 남겨, 운영자 발송이 계속 실패하면 하루 2번(09:05·21:05) 점검마다 사본이 최대 2번 간다. 시험으로 이 횟수를 못 박는다 |
| 운영자 발송 성공 | 감 | 간다 |
| 투자자 채팅이 이번 운영자·등급 채팅과 같음 | 감 | 안 감 |
| 끄는 파일 있음·INVESTOR 없음 | 감 | 안 감 |

### 3-4. 키 만료 알림 중복 막기
- 지금: plan_alerts 가 audience=None 알림(단계·만료 알림, 투자자 직접 발송이 이미 같은 내용을 보냄)과 운영자 전용 「키 만료일 점검 실패」(v2/key_expiry.py:147)를 낸다. same_channel 이면 점검 실패 글이 첫 알림 본문에 `(운영자)` 로 합쳐진다(key_expiry.py:143~145).
- 방법: key_expiry_check.py:221 에서 audience=None 알림에만 `investor_copy=False`. 운영자 전용 「점검 실패」는 **사본이 가야 하므로** 끄지 않는다. 서버는 same_channel(TELEGRAM_CHAT_ID == OPERATOR, 사실 9)이라 합쳐지는 길이 실제 경로다. 합쳐진 알림은 audience=None 으로 나가므로 `investor_copy=False` 와 충돌한다 → 합쳐진 알림(점검 실패 글이 끼어 있는 것)은 **`send(합친 글, investor_copy=True, investor_title="키 만료일 점검 실패", investor_body=<점검 실패 본문만>)`** 로 부른다. 사본에는 점검 실패 부분만 가고, 만료일·단계 문구는 들어가지 않는다(투자자가 직접 발송으로 이미 받음). 합쳐지지 않은 audience=None 알림만 `investor_copy=False`. (plan_alerts 반환에 `copy_body`(실패 본문만) 칸 하나만 더한다. copy_parts 안은 폐기.)
- `investor_body` 는 원문이 아니라 **고정 투자자 문장**이다: 「업비트 키 만료일 확인이 잠시 안 되고 있습니다. 운영자가 확인 중입니다. 투자자님이 하실 일은 없습니다.」 이유: 원문(v2/key_expiry.py:140~142)의 「401 이면 키 만료나 허용 IP 를 확인하세요」는 투자자가 할 일로 읽힌다. 시험 2번에서 이 문장을 고정한다(코드·첫 실패 시각 같은 값은 사본에 없음).
- 시험 2개: (1) audience=None 알림에서 투자자 채팅으로 간 건 = 직접 발송 1건뿐. (2) same_channel 합치기 경우: 사본 = 점검 실패 1건, 만료일 문구 0건. 합치지 않은 운영자 전용 「점검 실패」도 사본 1건.
- 문구 고침: `--test-investor` 시험 알림(key_expiry_check.py 제목 185줄, 본문 186~187줄)과 docstring 10줄(「단계·만료 알림을 투자자 채팅에도」)을 「모든 알림」으로 맞춘다. key_expiry_check 는 quiet_notifier_log(64~69)로 notifier 로그를 꺼 두므로 `[NOTIFY-COPY]` 기동 줄이 안 보인다 → 이 스크립트의 마지막 출력 줄(약 244줄 `key_expiry ok … investor=…`)에 `copy=on|off|fail:<코드>` 칸을 더한다.

### 3-5. 실패 로그와 반복 오류
- notifier.py:218 는 `type(e).__name__` 만 남긴다. `resp.text[:200]` 는 상태 숫자와 응답 error_code 숫자만. 시험: 가짜 ConnectionError(메시지에 `https://api.telegram.org/bot<가짜토큰>/…`)를 일으켜 로그 전체에 가짜 토큰이 없음.
- 사본 403: 1시간 쉼, 429: retry_after(없으면 60초) 쉼, 연속 실패 5번: 30분 쉼. 쉼 시작·해제 알림은 운영자에게 하루 최대 1건, **`investor_copy=False`** 로 보낸다(사본의 사본 방지).

### 3-6. 끄는 법 (롤백)
- 1순위: `services/data/.investor_copy_off` 파일 — 엔진 재시작 없이 즉시. 일꾼이 사본 직전에 파일 존재만 본다. 운영자가 서버에서 touch/삭제.
- 2순위: .env 의 TELEGRAM_INVESTOR_COPY=0 또는 INVESTOR 줄 삭제. 규칙: 권한 600 유지 · 백업 사본 만들지 않음 · 편집 뒤 `ls -la .env*` 로 사본 없음 확인. 엔진은 재시작 뒤에 먹음(config.py 가 .env 를 읽는 조건이 있어 기동 로그로 확인).
- 기동 로그: 프로세스가 시작할 때 `[NOTIFY-COPY] on|off reason=<파일|env끔|채팅없음|켜짐>` 1줄(값 없음). 엔진·cron 모두.
- 코드 롤백: git revert + 재시작(보유 없을 때). /root/notify_telegram.sh 는 복사 전 옛 판을 같은 폴더에 `.prev` 로 둔다(비밀 아님).

## 4. 투자자용 글 바꾸기 (막음 7)
- 조사 방법: `grep -rnE "from services.notifier import" ...` 56줄 + scratchpad/inv.py(각 호출 뒤 28줄을 정규식으로 훑음). 위험 낱말 대략: user_id 45곳 안팎(남김) · `{e}`/`{err` 예외 글 11곳 · .db/테이블 8곳 · uuid 8곳. 직접 읽어 확인한 곳: dashboard.py 683(「엔진 시작」: 경로·명령 없음, 출처 한 줄) · 703 알림(709~712 에 `tail -50 /root/…log` · `systemctl status tradebot`) · strategy_switch.py 83~86 · engine_manager.py 377·617 일부 · daily_health_check.py 218~230. 나머지 글 전체는 사람이 안 읽음 → 추정.
- **승인 범위와 통과 조건**: 이번 승인은 **설계만**이다. 「글 바꾸기가 56곳 + 직접 호출 + 셸 5개의 내부 낱말을 모두 가린다」는 **추정**이다. 통과 조건 = **커밋 승인 요청 때 전수 시험표(56 import 곳 + 직접 호출(key_expiry_check · notify_operator_test) + 셸 5개)를 사용자에게 보여 준다**.
- **구현 전 필수**: 전부의 본문을 읽어 「알림 본문 시험표」를 만든다. 열: 호출 위치 · 등급 · 본문 예 · **투자자가 할 일이 있는가(예/아니오, 있으면 그 줄)** · 규칙 적용 뒤 결과 · 통과/실패. 실패(내부 말이 남음·뜻이 사라짐·할 일 줄이 사라짐)가 나온 곳에만 호출 위치별 투자자 문구(`investor_title`/`investor_body`)를 따로 단다.
- **정적 시험**: 알림 호출 지점(import 줄 + 직접 `send(` 호출)을 세어 시험표 행 수와 다르면 실패한다(표에 없는 새 호출을 막음).
- **이미 알려진 놓침**(지금 규칙으로 못 잡음, 표에서 처리): strategy_engine.py:449~454 「sync_from_wallet」「엔진 재시작 검토 필요」(둘째 줄은 투자자에게 할 일처럼 읽힘) · watchdog_tradebot_engine.sh:62 「last Bar# was …s ago (threshold …)」 · trader.py 의 「신호: STOP_LOSS」꼴 줄(영문 코드).
- **투자자 행동 줄은 살아야 한다**: 거절 알림 trader.py 919~935(매수 거절)·1276~1300(현재가 매수 거부)의 `💡 {안내}` 줄은 업비트 앱에서 할 일(예: 외부 미체결 주문 확인)이다. 규칙 1·3 이 이 줄을 지우면 안 된다. 시험: 거절 코드 `insufficient_funds_ask` 가 든 본문에서 `💡` 안내 줄이 사본에 남고 `err:` 아래(─────)는 사라짐. 근거: project-rules 「외부 주문 공존 시 발주 실패 가시화 규칙」(09/30 KRW-JTO 클레임 — 알림이 사용자 할 일을 가리켜야 함, 거절 알림 본문에 거절 코드와 할 일을 적는다).
- 규칙(순수 함수, 순서대로). 지우는 단위: **줄 단위**가 기본. 문장 단위는 4번만.
  1. 줄 삭제: `/root/` `/home/` `systemctl` `journalctl` `tail -` `git ` `venv` 및 `.py` `.log` `.db` `.sh` `sqlite` 가 든 줄. 「💡 즉시 확인」 같은 머리줄 뒤 들여쓴 줄 묶음도 함께.
  2. 대입·내부 필드 줄 삭제: 정규식 `^\s*[A-Za-z_][A-Za-z0-9_.]*\s*=` 에 맞는 줄.
  3. 오류 원문 줄 삭제(대소문자 무시): `^\s*(err|error|exception|에러|오류|last_line)\s*:` 로 시작하는 줄. **`사유:` 줄은 좁게**: 뒤에 ASCII 식별자(`[A-Za-z_]+_[A-Za-z_]+`) · `True`/`False` · 예외 꼴(`\w+(Error|Exception)`)이 있을 때만 삭제. 그래서 dashboard.py:708 「사유: engine_manager가 False 반환」 은 지워지고, trader.py:1187 「사유: KRW 잔고 0원」 · trader.py:1153 「사유: 호가 단위 이탈 (0.5% 초과)」 · 메모리 알림 「사유: 메모리 임계 초과」 는 원문 그대로 남는다(시험 행으로 못 박음). 같은 규칙을 셸에도 쓴다. 이어서 줄 중간 꼬리 `에러: …` `exception: …` 는 그 꼬리만 삭제, `Traceback` 줄, `\w+(Error|Exception)\b` 가 든 줄. 단 daily_health_check 의 오류 건수 줄(daily_health_check.py:226~)은 숫자 요약이라 통째로 지우지 않고 건수는 남긴다(「오류 로그 (Traceback/CRITICAL/POLLUTED): a / b / c」 모양은 허용 목록).
  4. 구분선 `─────` 이 나오면 그 아래를 모두 버린다. 내부 표·함수 이름이 든 문장(strategy_switch · ensure_pullback_tables · 마이그레이션)은 **문장 단위**로 삭제.
  5. 식별자: user_id 는 남김(투자자 본인 계정, 확정). uuid 앞 8자. 30자 이상 base64/hex·`eyJ`·`sk-`·`AKIA` 는 `***`.
  6. 제목의 `[운영자]` 와 내부 영문 이름 삭제.
  7. 본문이 비면 등급별 기본 문장(CRITICAL · WARNING 모두 「운영자가 확인 중입니다.」 / INFO 는 제목만). **「별도로 하실 일은 없습니다」는 쓰지 않는다**(할 일이 있는 알림에서 거짓이 됨). 투자자 행동 줄이 있는 알림은 그 줄을 지우지 않는다. 지운 줄이 본문의 절반을 넘으면 본문 전체를 기본 문장으로 바꾼다(안전 쪽 기본값). **이때도 투자자 할 일 줄은 기본 문장 뒤에 남긴다**(할 일 줄 1개 + 지워질 줄 3개 본문 시험으로 못 박음). 빈 줄은 분모·분자 어디에도 세지 않는다.
  8. 남는 내부 낱말(force_liquidate · position_invariants.py:166, sync_from_wallet · strategy_engine.py:450, risk_pct · trader.py:926 등)은 지금 규칙으로 못 잡을 수 있다 → 구현 전 56곳 전수 시험표에서 잡고, 실패한 호출 위치만 위치별 투자자 문구를 단다.

## 5. 셸 길 (③) — scripts/server/notify_telegram.sh
- 운영자 curl 뒤 사본 curl 1번. 조건: .env 에 INVESTOR 있음 · 끄는 파일(서버 경로 services/data/.investor_copy_off) 없음 · TELEGRAM_INVESTOR_COPY≠0 · 운영자 CHAT_ID 와 다름.
- `curl -K -`(표준입력 설정)로 **URL(토큰)과 chat_id** 를 옮긴다: 표준입력에 `url = "https://api.telegram.org/bot…/sendMessage"` 와 `data-urlencode = "chat_id=…"` 줄. text·parse_mode 등 나머지는 지금처럼 인자에 둔다(채팅 번호도 `ps` 에 안 보임). 운영자 curl·사본 curl 둘 다. 출력·오류는 /dev/null, exit 0 유지. 시험(가짜 curl): 표준입력의 url·chat_id 줄을 읽고 가짜 토큰·가짜 채팅 번호가 argv 에 없는지 확인.
- 스크립트 맨 위에 `export LC_ALL=C.UTF-8` 를 더한다(watchdog 9줄과 같음, cron 로캘 C 에서 한글 정규식이 어긋나지 않게). 시험: LC_ALL=C 로 부른 경우에도 운영자 글은 바이트까지 그대로이고, 사본에서 「사유: 메모리 임계 초과」가 남는다.
- 끄는 파일: 셸도 `/root/upbit-tradebot-mvp/services/data/.investor_copy_off` 가 있으면 사본 curl 을 건너뛴다(시험 포함).
- 셸 사본 글 바꾸기는 파이썬 sanitizer 를 부르지 않고(느림·의존) 아래 grep 규칙을 쓴다. 두 구현이 어긋나지 않게 같은 입력표(시험 2번)를 셸 시험에도 넣는다.
- 본문(스크립트별, 구현 전 5개 본문을 읽어 확정 — 지금은 부분 확인):
  - daily·weekly digest: 숫자는 모두 남기고 경로·원문 줄만 삭제.
  - watchdog: `last_line:` 줄 삭제(내부 로그 원문). 이미 3600초 dedupe 가 있어 사본도 같은 빈도.
  - memory monitor: dedupe 가 없어 `*/10` 마다 반복 가능 → **사본에만** 같은 제목 30분 1번 제한(`/var/run/notify_copy_<제목해시>` 파일 시각). 운영자 쪽은 그대로.
  - cleanup: 제목 + 숫자 요약.
- 셸에서는 같은 규칙 중 줄 삭제(`grep -vE '/root/|systemctl|journalctl|tail -|\.log|\.db|\.sh|Traceback|^\s*(last_line|error|err|exception)\s*:|^\s*사유\s*:.*([A-Za-z]+_[A-Za-z]+|True|False|(Error|Exception))'`; 「사유: 메모리 임계 초과」는 남음)를 쓰고, 비면 기본 문장.
- 서버 반영: 복사 전 `diff`(저장소 판 vs /root 사본, 사실 15) → 옛 판 `.prev` → `install -m 755`. 복사 순서는 8절. 코드 주석 고침: watchdog_tradebot_engine.sh:7 「알림 글은 바꾸지 않는다(투자자가 받는 알림 형식 그대로)」는 이제 사본이 다르다는 점을 한 줄로 갱신.

## 6. 시험 (바깥 연결 없음, unittest 만)
1. 새 tests/regressions/test_r_2026_11_23_investor_copy.py: requests.post 가짜로 chat_id·본문 수집.
   - 3-3 표 8행 · 같은 채팅이면 안 감 · INVESTOR 없음 · 끄는 파일 · TELEGRAM_INVESTOR_COPY=0
   - 사본 500·예외·403·429 가 운영자 결과·반환값에 영향 없음, 403 쉼 · 429 retry_after · 연속 5회 실패 쉼, 쉼 알림은 사본이 안 붙음
   - 큐 가득 시 send() 즉시 반환(가짜 post 가 sleep) · 일꾼 죽었을 때 다시 띄움 · 일꾼 본문 예외 흡수
   - 정적 시험: investor_copy.py 에 `.put(`·`put(block` 없음(put_nowait 만)
   - atexit flush: 정상 종료는 도착, SIGTERM 은 유실을 문서화하는 하위 프로세스 시험 1개
   - 로그에 가짜 토큰·`/bot` 주소 없음: 가짜 ConnectionError(메시지에 주소 포함) 시험
2. 글 바꾸기 시험: 4절 규칙별 + 「알림 본문 시험표」 전부(호출 위치마다 1행) + 오류 건수 줄 허용 + `──` 아래 버림 + 대소문자(`Error:` `ERR :` `에러:`) + 비게 된 글.
3. 키 만료 중복 시험 2개(3-4절, 고정 투자자 문장 포함). 운영자 발송 실패 때 사본 반복 횟수(3-3절 한계 행) 시험 1개.
3-1. 끄는 파일 시험: 파일이 있으면 파이썬 사본 0건 · 셸 사본 0건(둘 다, 가짜 post/curl). 파일 삭제 뒤 바로 사본이 감.
3-2. scripts/v2/notify_operator_test.py:66 은 `investor_copy=False` 로 고치고, 시험으로 투자자 쪽 0건을 확인(운영자 채널 시험 글이 투자자에게 가면 안 됨).
3-3. 일꾼 시험: 글 바꾸기·파일 확인이 호출 스레드가 아니라 일꾼에서 도는지(스레드 이름 기록), 동시 호출 두 개가 일꾼을 둘 띄우지 않음, 스레드 시작 실패 흡수.
3-4. 상태 시험: `no_token`(토큰 없음 → 사본 0) · `no_chat`(토큰만 있음 → 사본 1) 구분, 모든 상태에서 bool 반환값이 변경 전과 같음.
4. 셸 시험: PATH 앞에 가짜 curl(표준입력 설정 `-K -` 내용을 파일 없이 환경변수 대신 임시 폴더에 기록). 운영자·투자자 2번 호출, INVESTOR 비면 1번, 사본 글에 경로 없음, 주소가 인자에 없음, memory 30분 제한, 끄는 파일.
5. 환경 격리: `TELEGRAM_CHAT_ID_INVESTOR` · `TELEGRAM_INVESTOR_COPY` · `TELEGRAM_BOT_TOKEN` 을 **빈 문자열로 설정**(pop 아님 — config.py:16 load_dotenv 가 비어 있는 키를 채움). scripts/regression_gate.sh 의 export 줄과 tests/_netguard/__init__.py activate() 둘 다. 켜야 하는 시험은 mock.patch.dict 로만.
6. 게이트: `bash scripts/regression_gate.sh` 통과 · [NETGUARD] 줄 0 · py_compile.

## 7. 문서·규칙 고침
- 승인 요청에 **그대로** 보일 문구(project-rules.md 「서버 비밀 파일 권한 규칙」 479줄 `(2026-11-22 추가, 1122-01 ㉠)` 줄의 「키 만료 알림만 이 채팅으로 간다(매매·운영 알림은 운영자 채팅).」 문장을 아래로 교체):
  - 새 문장: 「(2026-11-23 사용자 지시) 투자자 채팅에는 이 프로젝트의 모든 텔레그램 알림이 사본으로 간다(운영자 전용 알림 포함). 사본은 서버 경로·명령·예외 원문·내부 표 이름을 줄이고 투자자가 할 일 줄은 남긴다. 운영자 쪽 알림은 바뀌지 않는다. 끄는 법: 서버 `services/data/.investor_copy_off` 파일(엔진 재시작 없이 바로) · `.env` 의 TELEGRAM_INVESTOR_COPY=0 또는 TELEGRAM_CHAT_ID_INVESTOR 줄 삭제(권한 600·사본 파일 금지·`ls -la .env*` 확인). 로그: `[NOTIFY-COPY]`. 배포·재시작 때는 먼저 끄는 파일을 둔다.」
  - 「투자자 연락 원칙」(project-rules 같은 파일) 끝에 넣을 문장: 「자동 알림 사본은 이 원칙의 연락이 아니다(사람이 보내는 연락 세 종류와 별개).」
  - 같은 자리에 넣을 대체 표시: 「결정 1028-15 (나)(운영자 전용 알림은 투자자에게 가지 않는다)는 2026-11-23 사용자 지시로 대체됨. 운영자 전용 알림도 사본이 가며, 내부 이름은 사본에서 줄인다.」
  - 날짜 11/23 · 근거 사용자 지시 원문 「키 만료 알림만이 아니라 … 알림을 모두 받을 수 있어야 한다」.
- 코드 주석: strategy_switch.py:83·268~271, engine_manager.py:384·625 의 「투자자에게 가지 않아」 → 「투자자 사본은 내부 이름을 줄여 간다」. watchdog.sh:7 주석(5절).
- docs/operations/notifications.md 에 사본 길·끄는 법 절. 세션 시작 점검에 `[NOTIFY-COPY]` 확인.
- 투자자 체감 변경 통보 대상(알림이 늘어남) → 배포 뒤 1건 + investor-notice-log.md 한 줄.

## 8. 배포 순서 (되돌리기 어려운 일은 각 단계 앞 사용자 승인)
1. 로컬: 코드·시험 → pages/dashboard.py:527 버전 갱신(런타임 소스 변경) → py_compile → 게이트 → 사용자 보고·승인.
2. 커밋·push (`git status` 로 스테이징 확인).
3. 서버 읽기 전용 확인(사용자 `!` 실행 가능): 로컬·서버 HEAD · ExecMainStartTimestamp · 보유 상태 + 미확인 4가지(streamlit fileWatcherType · unit 파일 · /root 셸 사본 diff · Telegram 403/429 문서) + 5개 셸 본문 + /var/log/tradebot_memory_monitor.log 의 최근 30일 재시작 건수.
4. **끄는 파일 만들기**: `git pull` **전에** 서버에 `services/data/.investor_copy_off` 를 만든다(cron 파이썬·셸·엔진 어느 쪽도 pull 뒤 첫 실행부터 사본 0건).
5. `git pull`. (반쪽 상태: 코드는 새 것, 엔진은 아직 옛 프로세스. 사본은 끄는 파일 때문에 어디서도 안 감.)
6. 셸 복사(diff → .prev → install -m 755).
7. 눌림목 보유 0 확인(메뉴얼 61행). 보유 있으면 기다린다(사용자 결정 ④, 약속 유지).
8. `systemctl restart tradebot` → status · 기동 시각 · 기동 로그 `[NOTIFY-COPY] off reason=파일` 확인(재시작 때 나가는 boot_resume 알림 INFO/CRITICAL 의 사본이 투자자에게 가지 않음, 사실 4-1).
   - (11/24 Fable 구현 검토 권고) 기동 줄이 `off reason=파일` 이 아니라 `off reason=채팅없음` 이면 10단계로 가지 않고 멈춘다(엔진이 투자자 채팅 값을 못 읽음 → 셸·cron 사본만 켜지는 반쪽 상태 방지).
9. 투자자 체감 변경 안내 1건 → 연락 기록. 안내에 「모드(실계좌/모의)가 적힌 알림은 엔진 시작·정지 알림 두 종류뿐」처럼 실제에 맞게 쓴다.
10. 끄는 파일 삭제 → 시험 사본 1건(INFO) 보내기 → 서버 로그 `[NOTIFY-COPY] on` · `[NOTIFY] sent` 와 사본 건수 비교. (엔진은 파일을 매 사본마다 보므로 재시작 없이 켜짐.)
11. 24시간 관측: 403·429·큐 가득·쉼 건수, 사본:운영자 건수.

## 9. 결정 필요: 메모리 감시의 자동 재시작
- 사실: monitor_tradebot_memory.sh:35~43 은 RSS 가 MAX_MEMORY_MB=1400(1.4GB, 시스템 1.9GB 의 70%)을 넘으면 보유와 상관없이 `systemctl restart tradebot` 를 한다(알림 #25 「메모리 임계 초과」, #26 「tradebot 자동 재시작 완료」: docs/operations/notifications.md:156~162). 메뉴얼 61행 약속과 어긋난다. 이번 배포 뒤 이 알림도 투자자에게 가므로 어긋남이 투자자 눈에 보인다. 사본 curl 은 재시작을 최대 5초 늦출 수 있다.
- 발동 빈도: docs/operations 에는 건수 기록이 없다 → **미확인**(서버 /var/log/tradebot_memory_monitor.log 읽기 필요, 8절 3단계에 넣음). 11/19 이후 엔진이 안 끊긴 것은 11/19 13:06 기동 기록뿐이라 최근 발동은 없었을 가능성이 있다(추정).
- 선택지: (a) 이번에 고침 — 눌림목 보유 중에는 재시작을 건너뛰고 운영자에게만 알림, 단 하드 상한(예: 1800MB 초과는 보유와 상관없이 재시작) 유지 · (b) 나중에 따로 처리 · (c) 그 알림만 사본에서 뺌 · (d) 그대로.
- 권고: **(b) 따로, 단 서버 로그로 발동 빈도를 먼저 확인하고 최근 30일에 발동했으면 (a)로 올린다.** 까닭: (a)는 셸 재시작 규칙(실매매 안정성)을 바꾸는 일이라 이번 알림 사본 배포와 묶으면 한 번에 되돌릴 일이 늘어난다. 메모리 한도(1.9GB 서버, 하드 상한 값)는 실측 없이 정할 수 없다. (c)는 투자자에게 약속과 어긋나는 재시작을 숨기는 것이라 권하지 않는다. (d)는 약속 위반이 반복되면 투자자가 알림으로 알게 되므로 가장 나쁘다.
- 판정 기준(8절 3단계 읽기에서 함께 봄): ① 로그 첫 줄 날짜 · 「임계값 초과」 줄 수 · 30일 최대 「메모리 정상: N MB」 값 세 가지를 본다. ② 로그가 30일치에 못 미치거나 없으면 「발동 없음」으로 보지 않고 사용자에게 다시 묻는다. ③ 발동 0건이어도 최대값이 1400MB 에 가까우면(예: 1200MB 이상) 사용자에게 다시 묻는다.
- (b)를 고르면 남는 위험: 배포 뒤 메모리 재시작이 일어나면 투자자가 「자동 재시작 완료」 알림을 받는다(보유 중이면 메뉴얼 약속과 어긋남이 보임).

## 10. 사용자에게 남은 질문
- 9절 하나(권고 (b)). 그 밖에는 없음(확정 기본값: 운영자 채팅 없어도 사본 · user_id 유지 · 전 등급 · 끄는 파일 둠 · 보유 없을 때까지 대기 · 차단 시 운영자에게 하루 1건).

## 11. 이번에 확인하지 못한 것
- 「글 바꾸기가 내부 낱말을 모두 가린다」(추정, 4절 통과 조건) · memory 자동 재시작 발동 빈도(서버 로그 필요) · 56곳 본문 전수(4절의 시험표를 구현 첫 단계로 둠) · 5개 셸 본문 전체 · /root 사본이 저장소와 같은지 · 서버 streamlit 설정·unit 파일 · Telegram 403/429 한도 · 서버 로그에 토큰 든 주소가 실제 남았는지 · daily_health_check.py 가 어디서 도는지.
