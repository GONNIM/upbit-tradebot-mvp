# 1028-15 엔진 조용한 멈춤 알림·LIVE 카운트 멱등화 — 계획 (초안 · 수정 4회차)

- 작성: 2026-10-28 · 기준 로컬 HEAD `13c2d28` (코드는 `1c79fa6` 2차 T11 과 같음 — `13c2d28` 은 문서 커밋) · 서버 실행본 `1747fcc` (git 원문으로만 대조, 서버 접속 없음)
- 상태: **초안. 코드는 고치지 않았다.** 범위는 사용자 결정 1028-17 「권고대로」 = **(나)**. verifier 4차 「수정 후 승인」 → 4회차 반영 대조는 Fable plan-2(`docs/fable/2026-10-29-1028-15-plan-2.md`)로 확인, 반영의 실효(변이가 잡히는지)는 구현 검증(6장 3단계 변이 실행)에서 verifier 가 본다.

## 결론

- **이번 범위 (나):**
  - 엔진이 멈췄는데 아무도 모르는 「조용한 멈춤」을 없앤다.
  - 예외로 멈추면 CRITICAL 로그와 텔레그램을 1건 낸다.
  - LIVE 엔진 수를 사용자별 집합으로 멱등화한다.
- **자동 재시작은 넣지 않는다.** 들어온 날부터 한 번도 동작하지 않던 재시작 분기(D1·D3)는 끄지 않고 **삭제**한다. 자동 재시작은 2단계 별도 작업 **1028-18**(TEST 먼저)로 미루고, 그 설계 후보는 부록 B 에 둔다.
- 예외로 멈출 때 DB 를 「꺼짐」으로 두는 지금 동작은 그대로다. 사람이 확인하고 다시 시작한다.
- **「운영자에게만」은 지금 notifier 로는 보장되지 않는다.** 채널은 등급별로만 나뉘고, 투자자·운영자 구분이 없다(2.3). 그래서 남은 결정 1건이 있다(맨 끝).

## 수정 2회차 바뀐 곳

| 바뀐 것 | 위치 |
|---|---|
| 범위를 (나)로 다시 씀. 자동 재시작 설계(옛 4.2-2~5, 4.4 V1~V3, 4.5, 관련 R·M)는 부록 B 로 옮김 | 전체, 부록 B |
| D4 좀비 제거: 감싸기 함수 finally 에서 시도 stop_event, 관리 루프 `worker.is_alive()`, 루프 뒤 큐 비우기(N7) | 3.1 |
| 사유는 예외 유무로만 판정. stop_event 는 판정에 쓰지 않음(N4 해소) | 3.2 |
| CRITICAL 문구·dedupe·준비 신호로 「기동 중 실패」와 「매매 중 멈춤」 나눔 | 3.3 |
| notifier 채널 확인 결과와 대안 | 2.3, 남은 결정 |
| 재시작 분기 삭제, `_no_recover` 유지, 기존 시험과의 관계 | 3.4, 4.3 |
| `_live_users` 멱등화(187행 N5 처리, 예외 종료 때는 빼지 않음, 동작 변화, N1 범위 밖) | 3.5 |
| 시험을 (나) 범위로 다시 씀(진짜 runner, 항목별 변이) | 4 |
| 「정해 주실 것」을 결정 반영으로 정리 | 맨 끝 |

## 수정 3회차 바뀐 곳 (verifier 3차 「수정 후 승인」 7건)

| 지적 | 위치 |
|---|---|
| 1 운영자 키가 없을 때 투자자 채널로 넘어가지 않음 — S12·V-k, 구현 조건 | 2.3, 4.1 S12, 4.2 V-k |
| 2 대시보드 「트레이딩 엔진 로그」에 `insert_log` CRITICAL 이 보임 → 원문은 journal·파일만 | 3.3, 4.1 S11, 남은 결정 3 |
| 3 순서 「루프 종료 → join(2초) → 큐 비우기(1초·100건)」, S1 에 stop_engine 10초 단언 | 3.1, 4.1 S1 |
| 4 부록 B-7 을 「지적·요지·옮길 B 절·상태」 표로, B-1 문장에 「반박됨(N3)」 | 부록 B-1, B-7 |
| 5 3.5 동작 변화 정정(비실행 사용자 정지), D4 가 `_engine_start` 에서 `start_failed` | 3.5, 3.1 |
| 6 3.2 return/break 목록에 2155, S8 live_loop 거부는 TEST 로 | 3.2, 4.1 S8 |
| 7 TestRecovery 에 `notifier.send` patch, 운영자 키 추가는 사용자 승인 대상 | 4.3, 5.1 |

## 수정 4회차 바뀐 곳 (verifier 4차 「수정 후 승인」 5건)

| 지적 | 위치 |
|---|---|
| A S12 전 경우에 가짜 토큰, 섞인 경우 ④(환경변수 토큰·기본 채널 + secrets 운영자 채널) | 4.1 S12, 4.2 V-k |
| B V-l 을 순서·상한으로 나눔. S3-b 신설, S1 은 500건×50ms 설계 | 4.1 S1·S3·S3-b, 4.2 |
| C S8(b) 는 진짜 `run_live_loop`, `(params, None)`, `(None, None)` 이면 runner 533–537 이 먼저 막음 | 4.1 S8 |
| D S1 「바로 다시 시작」 = Lock 차단 없음 + 두 번째 runner 실행, 정리 때 정지 | 4.1 S1 |
| E `.env` 는 기동 때 한 번만 읽음 → 다음 서비스 재시작부터 반영 | 5.1, 남은 결정 4 |

## 1. 원인 (조사 결과 — 1회차 그대로 유효)

### 1.1 결함 네 겹 (`engine/engine_manager.py`, `engine/live_loop.py`)

| | 내용 | 줄 | (나)에서 |
|---|---|---|---|
| D1 | runner `finally: stop_event.set()` 이 먼저 돌아, 래퍼의 `not stop_event.is_set()` 이 늘 거짓 → 재시작 안 함 | em 619–620, 459 | 재시작 분기 삭제 |
| D2 | 메인 루프 안 예외는 작업 스레드에서 끝남. 래퍼 except 미실행. CRITICAL 없음 | ll 2442–2450, em 572–595 | 감싸기 함수가 예외를 잡아 CRITICAL |
| D3 | 래퍼가 부르는 `_start_engine_internal` 이 자기 스레드를 보고 `False` | em 357, 362, 475 | 재시작 분기 삭제 |
| D4 | 작업 스레드가 메인 `try`(ll 1460) **이전**(`sync_from_wallet` 1135, 전략 생성 1248–1270, `Unknown strategy type` 1270)에서 죽으면 stop_event 가 켜지지 않음 → 관리 루프(em 595) 무한, DB·화면 「실행 중」, 알림 없음 | ll 1135–1460, em 595 | 감싸기 finally + 루프 조건으로 제거 |

함께 확인한 것:
- 482–485 의 CRITICAL `❌ 엔진 최종 실패: 재시작 횟수 초과 또는 사용자 중단 요청` 은 실제 원인과 다른 문구다. 텔레그램도 없다.
- `_live_engine_count` 의 증가는 `_start_engine_locked`(334–336), 감소는 `stop_engine`(425–431) 에서만 한다. 그래서 예외 종료 → 다시 시작 → 정지 뒤에도 카운트가 1 로 남아 Reconciler 가 멈추지 않는다(3.5).

### 1.2 재현 (진짜 runner 경유)

- 스크립트: `/private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fc7131f6-f471-490b-aa6a-ff2242dce9e8/scratchpad/repro_recovery.py`
- 진짜로 둔 것: `_start_engine_internal`·래퍼·`_engine_runner`(finally 포함)·`get_user_lock`·`engine_control.detach`
- 가짜로 바꾼 것: DB·파일 로그·params·trader·`run_live_loop` 본문·관리 스레드 sleep

명령:
```
cd /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp
TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fc7131f6-f471-490b-aa6a-ff2242dce9e8/scratchpad/repro_recovery.py 2>/dev/null
```

3~5초 뒤 상태 줄:
```
[setup_exception] wrapper alive after 3~5s=False stop_event set=True live workers=[] set_engine_status so far=[False] logs so far=['ERROR', 'INFO', 'CRITICAL']
[runtime_exception] wrapper alive after 3~5s=False stop_event set=True live workers=[] set_engine_status so far=[True, False] logs so far=['INFO', 'ERROR', 'INFO']
[setup_exception] wrapper alive after 3~5s=False stop_event set=False live workers=[] set_engine_status so far=[False] logs so far=['ERROR', 'INFO', 'ERROR']
[pre_main_try_exception] wrapper alive after 3~5s=True stop_event set=False live workers=[] set_engine_status so far=[True] logs so far=['INFO']
```

판독:
- ① 기동 중 예외(D1): 재시작 0회. 오해를 부르는 「최종 실패」 CRITICAL.
- ② 매매 중 예외(D2): CRITICAL 없음.
- ③ D1 을 없앤 변이(D3): `recovery sleeps requested=[60]` 뒤 `_start_engine_internal calls=[(1, False)]` — 새 엔진이 뜨지 않는다.
- ④ D4: 관리 스레드는 살아 있다. stop_event 는 꺼져 있고, 작업 스레드는 없다. DB 는 `[True]` 뿐이고 로그는 「엔진 시작」 1줄이다.
- 전체 출력은 1회차 기록과 같다. 스크립트는 정리용으로 ④ 뒤에 stop_event 를 켠다.

### 1.3 이력

| 커밋 | 날짜 | 내용 |
|---|---|---|
| `45e2ee1` | 2025-08-05 | runner `finally: stop_event.set()` |
| `02fcae9` | 2025-08-25 | 래퍼 신설. 이때부터 D1·D3 성립 |
| `1747fcc` | 2026-10-27 | 서버 실행본. 같은 원문 |
| `1c79fa6` | 2026-10-28 | T11. D1–D4 그대로 |

D4 의 시작 시점은 이번에 blame 하지 않았다(미확인).

## 2. 지금 알림·상태 경로 확인

### 2.1 예외 종료 때 지금 남는 것

| 경우 | logs(insert_log) | journal | 텔레그램 | DB is_running | is_running() |
|---|---|---|---|---|---|
| runner 본문 예외 | ERROR `❌ 엔진 예외` + INFO `🛑 엔진 종료` + CRITICAL 「최종 실패」 | 같음 + traceback | 없음 | False | False |
| 작업 스레드 메인 try 안 예외 | ERROR `❌ 예외:`(경합으로 빠질 수 있음) + INFO `🛑 엔진 종료` | traceback(excepthook) | 없음 | False | False |
| D4 | INFO `🚀 엔진 시작` 만 | traceback(excepthook) | 없음 | **True** | **True** |
| 사용자 정지 | INFO `🔌 엔진 종료 요청됨`·`🛑 엔진 종료` | 같음 | 없음 | False | False |
| PULLBACK LIVE 거부 | ERROR `[PULLBACK-PARAMS] …` | 같음 | 기존 CRITICAL 1건(거부 알림) | False | False |

### 2.2 준비 신호(`_ready`)

- 시작마다 새 Event 가 생긴다(em 372–373). `live_loop.py:1687` `_control_ready` 에서 set 된다.
- 다만 이 호출은 **UPBIT_MATCH 분기 안에만** 있고, LEGACY_LOCAL 분기(2231)에는 없다.
- (나)에서는 문구를 고르는 데에만 쓴다. LEGACY_LOCAL 에서는 늘 「기동 중 실패」 문구가 나간다(문구만 다르고 경보는 같다). 서버 RUN_MODE 는 배포 전에 확인한다(5.1).

### 2.3 notifier 채널 — 「운영자에게만」이 가능한가

`services/notifier.py` `_get_credentials(level)` (51–92)를 확인했다.
- 채널은 **등급별로만** 고른다.
  - `TELEGRAM_CHAT_ID_<LEVEL>`(예: `TELEGRAM_CHAT_ID_CRITICAL`)이 있으면 그 채널을 쓴다.
  - 없으면 기본 `TELEGRAM_CHAT_ID` 를 쓴다(환경변수가 먼저, 다음이 streamlit secrets).
- **받는 사람(투자자/운영자)을 나누는 인자나 설정은 없다.** `send()` 에는 `level·title·body·dedupe_key·dedupe_ttl` 만 있다(123–128).
- 지금 CRITICAL 알림은 이미 투자자를 독자로 쓴다. 예: `NO_ACTION_TEXT = "투자자님이 따로 하실 일은 없습니다."`(core/strategy_engine.py:47), control_requests 의 CRITICAL 본문, PULLBACK 거부 알림. 그래서 CRITICAL 채널은 투자자도 보는 채널이라고 보는 것이 맞다.
- 서버에 등급별 채널이 설정돼 있는지, 그 채널을 누가 보는지는 서버 비밀 파일 값이라 확인하지 않았다(**미확인** — 값을 읽지 않는 규칙).
- 따라서 이번 경보를 `send(LEVEL_CRITICAL, …)` 로 보내면 **기존 CRITICAL 알림과 같은 곳으로 간다.** 이것은 「운영자에게만」이 아니다.

대안:

| 안 | 내용 | 바뀌는 것 | 투자자에게 보이나 |
|---|---|---|---|
| (가) 기존 CRITICAL 채널 그대로 | 지시 문구(「운영자가 확인하고 다시 시작합니다」 + NO_ACTION_TEXT)로 보냄 | engine_manager.py 만 | 보임. 투자자 연락 원칙의 「체감 변경 통보」 대상인지 판단 필요 |
| (나) 운영자 전용 채널 신설 | `send(..., audience="operator")` 인자 추가. `TELEGRAM_CHAT_ID_OPERATOR` 가 있으면 그곳, **없으면 텔레그램을 보내지 않고 journal·logs 에만 남김** | notifier.py 인자 1개(기본값이면 지금과 같음) + 서버 비밀 파일에 키 1개(운영자가 직접 추가, 권한 600) | 안 보임 |
| (다) 텔레그램 없음 | CRITICAL 로그만 | engine_manager.py 만 | 안 보임. 「조용한 멈춤」은 journal 을 봐야만 알 수 있어 목적에 미달 |

- 권고는 **(나)** 다. 사용자 결정 ③ 「운영자만」을 코드로 보장하는 유일한 안이다.
- 키가 없으면 보내지 않으므로, 서버 설정 전에 배포해도 투자자에게 새 알림이 가지 않는다.
- 다만 설정 전에는 경보가 journal·logs 에만 남는다. 그래서 운영자 채널 키 추가를 배포 체크리스트에 넣는다(5.1).
- 이 선택은 남은 결정이다(맨 끝).

(나) 안의 구현 조건 (verifier 3차 1):
- `_get_credentials(level="OPERATOR")` 를 **그대로 쓰지 않는다.** 그 함수는 등급 키가 없으면 기본 `TELEGRAM_CHAT_ID` 로 넘어가므로(74–76·87–88), 운영자 경보가 투자자 채널로 갈 수 있다.
- 운영자 전용 함수 `_get_operator_credentials()` 를 따로 둔다.
  - 토큰은 기존처럼 환경변수 → secrets 순서로 찾는다.
  - 채팅 ID 는 `TELEGRAM_CHAT_ID_OPERATOR` 를 **환경변수와 secrets 에서만** 찾는다.
  - 없으면 `(None, None)` 을 돌려준다. 기본 채널·등급 채널로 넘어가지 않는다.
- `send(..., audience="operator")` 인데 운영자 채팅 ID 가 없으면 HTTP 요청을 하지 않는다. `logger.info("[NOTIFY] operator 채널 없음 — 로그만")` 1줄만 남긴다(키 이름·값은 적지 않음). dedupe 검사가 이 분기보다 먼저라, 1시간 안 두 번째 예외 종료 때는 이 줄도 남지 않는다(`[ENGINE-EXIT]` CRITICAL 로그는 매번 남음).
- `audience` 기본값(`None`)이면 지금 경로 그대로다(`_get_credentials(level)`).

## 3. 고치는 내용 (모두 `engine/engine_manager.py` — 2.3 (나) 안이면 `services/notifier.py` 인자 1개 추가)

### 3.1 D4 좀비 제거와 작업 스레드 예외 붙잡기

1. 작업 스레드 대상을 `run_live_loop` 대신 `_run_live_loop_guarded(holder, attempt_stop, params, q, trader, stop_event, test_mode, user_id, **kw)` 로 바꾼다.
   - 본문: 모듈 전역 `run_live_loop` 를 **호출 시점에** 찾아 그대로 부른다. 시험의 `mock.patch.object(mod, "run_live_loop")` 가 그대로 먹게 하려는 것이다.
   - `except BaseException as e: holder["exc"] = e; raise` — excepthook traceback 은 지금처럼 journal 에 남는다.
   - `finally: attempt_stop.set()` — 그 시도의 stop_event 다. 메인 try 이전에 죽어도 관리 루프가 끝난다.
   - 스레드 이름(`run_live_loop_{user}_{mode}`)·daemon·`add_script_run_ctx(worker)`·`add_engine_thread(user_id, worker, stop_event)` 는 그대로 둔다.
2. 관리 루프 조건: `while not stop_event.is_set() and worker.is_alive():` (이중 방어).
3. **순서: 루프 종료 → `worker.join(timeout=WORKER_JOIN_SEC=2)` → 큐 비우기** (verifier 3차 3).
   - join 을 먼저 한다. 그래야 작업 스레드가 끝나면서 넣은 마지막 이벤트(`q.put(EXCEPTION)`·마지막 BUY/SELL)까지 큐에 들어온 뒤에 비울 수 있고, holder 도 확정된다.
4. **큐를 한 번 비운다**(N7). `q.get_nowait() → _process_event(...)` 를 `queue.Empty` 가 나오거나 **1초 또는 100건 중 먼저 오는 쪽**에서 멈춘다.
   - 지금은 작업 스레드가 `q.put(EXCEPTION)` 뒤 stop_event 를 켜는 경합 때문에 `❌ 예외:` ERROR 와 마지막 체결 기록이 빠질 수 있다. 이 경합을 없앤다.
   - 시간 상한을 두는 이유: `stop_engine` 의 10초 join(em 406)이 넘으면 관리 스레드가 runner finally 의 `user_lock.release()` 전에 표에서만 지워진다. 그러면 다음 시작이 `user_lock` 을 얻지 못해 「⚠️ 이미 실행 중 (Lock 차단)」으로 바로 끝난다(em 498–502). 관리 스레드는 10초 안에 끝나야 한다.
   - 시간 예산: 0.5초 `q.get` + 2초 join + 1초 비우기 + finally 정리 → 10초 안. 실제 join 시간은 측정하지 않았다(미확인, 2차 판정 25). S1 에서 단언한다.
5. holder 에 예외가 있으면 runner try 안에서 `raise EngineWorkerError(...) from holder["exc"]` 를 던진다. 그러면 지금의 except 경로(로그·`update_engine_status("error")`)를 그대로 탄다.
6. **T11 시작 확인과의 관계:** D4 가 없어지면 T11 신버전 시작 요청 `_engine_start`(`engine/control_requests.py`:668–676, 4초 생존 확인)가 D4 형 실패를 `started` 대신 `start_failed` 로 잡는다. 지금은 관리 스레드가 좀비로 살아 있어 `started` 가 된다. 좋아지는 쪽이다.
   - **조건 (구현 수정 1회차):** 이렇게 잡히는 것은 작업 스레드가 4초 안에 죽고, 그 뒤 관리 스레드의 텔레그램 발송(`notifier` HTTP timeout 최대 5초)까지 4초 안에 끝났을 때뿐이다. 발송이 길어지면 4초 확인 시점에 관리 스레드가 아직 살아 있어 `started` 로 판정될 수 있다.
   - 발송 중에는 최대 5초 동안 `is_running`(관리 스레드 생존)이 참인 창이 있다. 이 창이 끝나면 거짓이 된다. 운영자 채널 키가 없으면 HTTP 요청이 없으므로 이 창도 없다.

### 3.2 사유 판정 — 예외 유무로만 (N4 해소)

- 판정: runner 본문 예외가 있거나 holder 예외가 있으면 **예외 종료**다. 그 밖(사용자 정지·PULLBACK 거부·파라미터 없음·잠금 차단·예외 없는 작업 스레드 종료)은 **정상 종료**다.
- stop_event 는 판정에 쓰지 않는다. 어차피 runner finally 와 작업 스레드 finally 가 모두 켠다.
- 사용자 정지와 겹친 실제 예외(정지 버튼과 동시에 터진 예외)는 예외 종료로 본다. 실제 예외이므로 알리는 것이 맞다.
- 남는 것(범위 밖, 부록 B 로): 작업 스레드가 예외 **없이** 끝나는 경로가 있다.
  - PULLBACK 거부(ll 1072)는 자체 알림이 있다.
  - LEGACY_LOCAL 의 `stream_candles` 생성기가 스스로 끝나는 경우가 있다(ll 2236–2247).
  - 이 경우는 이번에도 「정상 종료」로 알림이 없다. UPBIT_MATCH 메인 루프는 `while not stop_event.is_set()`(1688) 밖으로 예외 없이 나가는 return/break 가 워밍업 재시도 `break`(1506)와 확정 봉 재조회 재시도 루프의 `break`(2155, 안쪽 재시도 루프만 빠져나감 — 무해) 뿐이라 해당하지 않는다(맨 `return`/`break` 줄만 찾은 검색 기준 — 값을 돌려주는 return 등은 구현 때 전수 확인).
  - 이를 구분하려면 사용자 정지 표식이 필요하다(부록 B-2).

### 3.3 CRITICAL 로그·텔레그램

- **원문 로그** (`logger.critical`·`log_to_file` — journal·파일만). 예외 원문은 여기에만 둔다:
  - `[ENGINE-EXIT] 예외 종료 — 자동 재시작 없음, 운영자 시작 필요 | phase=boot|trading mode=LIVE|TEST exc=<Type>: <msg>`
  - 지금의 「❌ 엔진 최종 실패: 재시작 횟수 초과 또는 사용자 중단 요청」 문구는 삭제한다(위 문구로 대체).
  - 정상 종료는 지금 로그 그대로 두고, CRITICAL 은 내지 않는다.
- **`insert_log`(DB logs 테이블) — 투자자에게 보인다** (verifier 3차 2):
  - 대시보드 「📚 트레이딩 엔진 로그」(`pages/dashboard.py:1936–1944`)는 `fetch_logs(user_id, limit=200)` 를 등급 제한 없이 보여 준다.
  - 그래서 `[ENGINE-EXIT]` 원문 줄을 `insert_log` 에 넣으면 투자자 화면에 예외 원문이 보인다.
  - 권고: `insert_log(user, "CRITICAL", "엔진이 오류로 멈췄습니다. 운영자가 확인하고 다시 시작합니다.")` 처럼 **투자자용 짧은 문구 1줄**만 넣는다. 예외 원문·종목·전략 코드는 넣지 않는다.
  - 선택지(남은 결정 3): 원문 그대로 / 짧은 문구 1줄(권고) / 남기지 않음.
  - 참고: runner except 의 기존 `insert_log(user, "ERROR", "❌ 엔진 예외(mode=…): {e}")`(em 612–614)와 `_process_event` 의 `❌ 예외:` ERROR 는 지금도 원문을 화면에 보인다. 이번 범위에서는 바꾸지 않는다. 결정 3 에서 「원문 비노출」을 고르면 이 두 줄도 같은 기준으로 맞출지 함께 정한다.
  - **사실 정정 (구현 수정 1회차, PO 확인):** 위 「등급 제한 없이」는 틀렸다.
    - 옛 대시보드 「📚 트레이딩 엔진 로그」는 `fetch_logs(user_id, limit=200)` 를 부르는데, `fetch_logs` 의 기본 등급이 `level="LOG"` 라서(`services/db.py:289`·336–345) **LOG 등급만** 보여 준다(`pages/dashboard.py:1943`).
    - 「상태/경고/에러」 칸(`pages/dashboard.py:1066`)은 CRITICAL 을 뺀다.
    - 그래서 CRITICAL 짧은 문구는 **옛 화면에는 보이지 않고**, v2 화면(`api_read.py:91–100`)에서만 보인다.
    - 등급은 CRITICAL 그대로 둔다(verifier 권고 (가)). 2차 배포에 묶기로 했으므로(결정 ②) 배포 때부터 v2 에서 보인다.
    - 「❌ 예외:」·「❌ 엔진 예외」 원문 ERROR 줄도 옛 「트레이딩 엔진 로그」에는 나오지 않는다. 다만 ERROR 원문 줄은 옛 화면의 「상태/경고/에러」 토글(db.py:323–333 `level IN (…'ERROR')`)과 v2(api_read.py:95 `_ERROR_LEVELS`)에서 보인다. 원래 있던 노출이고 이번 범위에서는 바꾸지 않는다.
- **phase**: 그 시도의 준비 Event 가 set 이고(`self._ready.get(key)` 의 `stop_event` 가 이 시도 것이고 `is_set()`) 이면 `trading`, 아니면 `boot`. 문구를 고르는 데에만 쓴다.
- **텔레그램 1건** (2.3 결정에 따라 채널 결정):
  - 기동 중 실패: 제목 「🚨 엔진 기동 중 실패 — 자동 매매가 시작되지 않았습니다」. 본문 「엔진이 시작하는 도중 오류로 멈췄습니다.\n지금 자동 매매는 멈춰 있습니다. 운영자가 확인하고 다시 시작합니다.\n{NO_ACTION_TEXT}」
  - 매매 중 멈춤: 제목 「🚨 엔진이 매매 중 멈췄습니다」. 본문 「엔진이 오류로 멈췄습니다.\n지금 자동 매매는 멈춰 있습니다. 운영자가 확인하고 다시 시작합니다.\n{NO_ACTION_TEXT}」
  - 예외 원문·종목 코드·전략 코드는 본문에 넣지 않는다(투자자 문구 규칙 T8 과 같음).
  - `dedupe_key=f"engine_exit_exception:{user_id}"`, `dedupe_ttl=3600`(사용자별, 같은 사용자 1시간 1건).
  - `NO_ACTION_TEXT` 는 `core.strategy_engine` 에서 import 한다. engine_manager 는 이미 live_loop 를 통해 이 모듈을 불러오므로 새 import 비용은 없다.
  - 발송 예외는 삼킨다(경보 실패가 정리를 막지 않게).
- 위치: 래퍼 `except` 안. 정리(runner finally)는 이미 끝난 뒤다.

### 3.4 재시작 분기 삭제

- 래퍼(em 434–485)는 `try: self._engine_runner(...)` / `except Exception as e: <3.3 CRITICAL>` 만 남긴다. `MAX_RESTART_ATTEMPTS`·`RESTART_DELAYS`·`time.sleep(delay)`·`_start_engine_internal(restart_count+1)` 호출은 삭제한다.
- 메서드 이름 `_engine_runner_with_recovery` 는 남긴다. 스레드 대상이고 시험(`test_r_2026_10_28_p4_t11_control.py:960`)이 부른다. 독스트링은 「복구 없음 — 1028-18」로 고친다.
- **`_no_recover` 는 남긴다.**
  - `start_engine` 의 `discard`(구현 뒤 em 311), `engine/control_requests.py:801` 의 `add`, 시험 `test_start_engine_clears_no_recover`(t11_control 992–997)·fix1 276·287 이 그대로 성립한다.
  - 래퍼에서 읽던 곳(454·474)이 사라지므로 (나) 이후에는 쓰기만 하는 표식이 된다. 1028-18 에서 다시 읽는다고 주석에 적는다.
- `start_engine(restart_count=…)`·`_restart_counts` 는 호환을 위해 남긴다(값만 기록, 읽는 곳 없음).

### 3.5 LIVE 엔진 수 멱등화 (`_live_users`)

- `__init__`(187): `self._live_engine_count = 0` 을 지우고 `self._live_users: set = set()` 으로 바꾼다(N5). 그대로 두면 읽기 속성과 충돌해 `AttributeError` 가 난다.
- 읽기 속성 `_live_engine_count` → `len(self._live_users)`. `test_r_2026_09_30_wo12_boot_resume.py:166·179` 의 `assertEqual(self.em._live_engine_count, 1)` 와 미추적 `tests/test_mode_lock.py:96` 의 `== 0` 은 고치지 않고 성립한다. 대입하는 곳은 코드·시험 모두 없다(grep 확인).
- `_start_engine_locked`(331–336): `if not self._live_users: rec.load_inflight_from_db(...)` → `self._live_users.add(key)`.
- `stop_engine`(425–431): `self._live_users.discard(key)` → `if not self._live_users: get_reconciler().stop()`.
  - 판단 기준은 지금처럼 `running_mode == MODE_LIVE` 다(401 의 `_engine_mode` 대체 포함).
  - `discard` 라서 같은 사용자를 두 번 빼도 다른 사용자 항목은 남는다.
- **예외로 종료될 때는 집합에서 빼지 않는다**(지금 동작과 같다 — 래퍼·runner 는 카운트를 건드리지 않음). Reconciler 도 계속 돈다. 미체결 추적이 남는 쪽이 안전하다.
- **동작 변화 (명시):** LIVE 예외 종료 → 사용자가 다시 시작 → 정지.
  - 지금: 카운트가 1→2→1 이 되어 **Reconciler 가 멈추지 않는다.**
  - 바뀐 뒤: 집합이 {u}→{u}→{} 이 되어 **Reconciler 가 멈춘다**(의도한 대로). 다시 시작할 때 `load_inflight_from_db` 는 지금과 같이 부르지 않는다(이미 비어 있지 않음).
  - **함께 바뀌는 경우 (verifier 3차 5):** `stop_engine` 은 `running_mode = self._engine_mode.get(key, ui_mode)`(401)라서, 실행 중이 아닌 사용자라도 ui_mode 가 LIVE 이면 카운트를 깎았다. 정지를 두 번 누르거나 이미 꺼진 엔진을 정지하는 경우다.
    - 지금: 다른 사용자의 LIVE 엔진이 돌고 있어도 카운트가 0 이 되어 Reconciler 를 멈출 수 있다.
    - 바뀐 뒤: 집합에 없는 사용자의 `discard` 는 아무 일도 하지 않으므로 다른 사용자의 Reconciler 가 유지된다. 좋아지는 쪽이다.
  - 위 두 경우 말고는 같은 동작이다.
- **N1 (비원자성) — 범위 밖, 기존 결함:** 「비었는지 확인 → stop/load」가 한 잠금 아래에 있지 않다. `_start_engine_locked` 는 사용자별 `_start_lock` 아래에서, `stop_engine` 은 잠금 없이 돈다. 서로 다른 사용자의 시작과 정지가 겹치면 Reconciler 가 엇갈리게 stop 될 여지가 지금도 있다.
  - **이번 변경이 새 배경 스레드 경로를 만들지 않음을 확인했다.** 집합을 바꾸는 곳은 지금 카운트를 바꾸는 두 곳과 같다.
  - 부르는 쪽도 그대로다: 대시보드 스크립트 스레드, boot_resume, control_requests 감시 스레드(`restart_engine`·`stop_engine`).
  - 삭제되는 재시작 분기는 `_start_engine_internal` 만 불렀고 카운트를 건드리지 않았다. 래퍼·감싸기 함수도 집합을 건드리지 않는다.

## 4. 시험 계획

새 파일 `tests/regressions/test_r_2026_10_29_engine_exit_alert.py`. 실행: `TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_29_engine_exit_alert -v`.

### 4.1 진짜 runner 를 거치는 시험

- 진짜로 둔 것: `start_engine`/`_start_engine_internal`·래퍼·`_engine_runner`·감싸기 함수·`get_user_lock`·`engine_control`·`stop_engine`
- 가짜로 바꾼 것: DB 기록, 파일 로그, params·trader, `run_live_loop` 본문, `get_reconciler`(MagicMock), `services.notifier.send`(기록만)

| # | 상황 | 기대 |
|---|---|---|
| S1 | 사용자 정지(`stop_engine`). 가짜 작업 스레드는 정지 직전까지 큐에 이벤트를 많이 넣는다(예: 500건). 가짜 `_process_event` 는 건마다 지연을 둔다(예: 50ms). 상한(1초·100건)이 있으면 비우기가 1초 안에 끝나고, 상한이 없으면 500×50ms=25초로 10초를 넘도록 설계한다 | CRITICAL 로그 0, notifier CRITICAL 0, DB False, `is_running` False. **`stop_engine` 이 10초 안에 반환하고 관리 스레드가 끝남**(`not th.is_alive()`). **바로 다시 시작** 단언은 두 가지다(em 406·498–502): ① `insert_log` 기록에 「Lock 차단」이 없음 ② 두 번째 runner 가 실제로 돌았음(가짜 `run_live_loop` 호출 2회째 기록). 다시 시작한 엔진은 시험 정리 단계에서 `stop_engine` 으로 정지한다 |
| S2 | runner 본문 예외(trader 생성) | CRITICAL 로그 1(`phase=boot`), notifier 1(기동 중 실패 문구, dedupe 사용자별), DB 마지막 False |
| S3 | 작업 스레드 메인 루프 안 예외(준비 신호 set 뒤, 진짜 끝부분 모양) | CRITICAL 1(`phase=trading`, 매매 중 멈춤 문구), DB False, `❌ 예외:` ERROR 가 빠지지 않음(큐 비우기). 주: 진짜 끝부분(ll 2442–2450)은 `q.put(EXCEPTION)` 이 stop 보다 **먼저**라, 이 시험은 비우기 순서 변이(V-l 순서)를 잡지 못한다 → S3-b |
| S3-b | 비우기 순서: 가짜 작업 스레드가 stop_event 가 켜진 **뒤에** 마지막 이벤트(`LOG` 또는 `BUY`)를 넣고 0.2초 뒤 끝난다 | 그 마지막 이벤트가 `insert_log` 에 기록됨(join 2초 → 비우기 순서일 때만 성립) |
| S4 | **D4**: 작업 스레드가 stop_event·q 없이 즉시 raise | 관리 스레드가 3초 안에 종료, CRITICAL 1(`phase=boot`), DB 마지막 False, `is_running` False |
| S5 | S2·S3·S4 각각에서 재시작 | `_start_engine_internal` 추가 호출 0, `_gen` 증가 0, 새 스레드 0 |
| S6 | `_live_users` 멱등: U1·U2 LIVE 시작 → U1 `stop_engine` 두 번 | 집합 {U2}, `_live_engine_count == 1`, Reconciler `stop` 호출 0 → U2 정지 뒤 1 |
| S7 | LIVE 예외 종료 → 재시작 → 정지 | 집합 {U}→{U}→{}, Reconciler `stop` 1회, `load_inflight_from_db` 첫 시작 1회만 |
| S8 | PULLBACK 거부 — (a) LIVE: runner 거부(516–530). (b) live_loop 거부(1051–1073): LIVE 에서는 runner 가 먼저 막아 (b) 에 닿지 않는다. 그래서 (b) 만은 **가짜 본문이 아니라 진짜 `run_live_loop`** 를 쓴다(본문을 가짜로 두면 거부 코드가 실행되지 않음). TEST 에서 다음 중 하나로 거부시킨다: `_pullback_boot_params` 가 **`(params, None)`** 을 돌려주게 patch(→ `pullback_cfg is None`), 또는 `live_loop.RUN_MODE` 를 `LEGACY_LOCAL` 로 patch. 주의: `(None, None)` 을 돌려주면 runner 533–537(「새 전략 설정 없음·변환 실패 → 기동 거부」)이 먼저 막아 live_loop 에 닿지 않는다. 거부 경로는 거부 직후 `return` 하므로 진짜 `run_live_loop` 의 나머지(지갑·REST)는 실행되지 않는다 | 둘 다 새 CRITICAL(`[ENGINE-EXIT]`) 0, notifier 는 기존 거부 알림 1건만(dedupe 키 `pullback_live_refused:`·`pullback_boot_refused:`) |
| S9 | 같은 사용자 1시간 안 예외 종료 2회 | notifier 실제 발송 1(dedupe), CRITICAL 로그는 2 |
| S10 | 발송이 예외를 던짐 | 래퍼가 예외 없이 끝남, DB False(정리 영향 없음) |
| S11 | 예외 원문 노출 | notifier 본문과 **`insert_log` CRITICAL 줄**에 `exc` 문자열·종목·전략 코드 없음(결정 3 이 권고대로면 짧은 문구 1줄만). `logger.critical`·`log_to_file` 의 `[ENGINE-EXIT]` 줄에는 원문 있음 |
| S12 | 운영자 채널 대체 금지 (`services/notifier.py`, `requests.post` 를 가짜로 바꿔 호출 기록) — 환경변수 경로와 secrets 경로(`streamlit.secrets` 가짜) 각각 3가지: ① `TELEGRAM_CHAT_ID`·`TELEGRAM_CHAT_ID_CRITICAL` 만 있고 운영자 키 없음 + `audience="operator"` ② 운영자 키 있음 + `audience="operator"` ③ `audience` 기본값. 섞인 경우 ④: 환경변수에는 토큰과 기본 `TELEGRAM_CHAT_ID` 만, 운영자 키는 secrets 에만 + `audience="operator"`. **7가지 모두 시험 안에서 가짜 토큰을 넣는다**(`mock.patch.dict(os.environ, {...})` 또는 가짜 secrets). 실행 명령이 `TELEGRAM_BOT_TOKEN=` 로 토큰을 비우므로, 토큰이 없으면 `send` 가 notifier.py 152–153(자격증명 없음 반환)에서 멈춰 ① 이 우연히 0건이 되고 V-k 가 살아남는다. dedupe 상태는 경우마다 비운다 | ① post 0건, `[NOTIFY] operator 채널 없음 — 로그만` 1줄 ② 운영자 채팅 ID 로 1건 ③ 지금과 같은 채널(`TELEGRAM_CHAT_ID_CRITICAL`)로 1건 ④ secrets 의 운영자 채팅 ID 로 1건(환경변수 기본 채널로 가지 않음) |

### 4.2 변이 (각 항목이 잡히는지)

구현 뒤 임시 사본 모듈에 문자열 치환으로 하나씩 넣고, 지목한 시험이 **실패**하는지 본다. 저장소 파일은 그대로 둔다.

| 변이 | 잡아야 할 시험 |
|---|---|
| V-a 감싸기 finally 의 `attempt_stop.set()` 과 루프 `worker.is_alive()` 둘 다 제거 | S4 |
| V-b 감싸기 함수의 `holder["exc"]` 기록 제거 | S3 |
| V-c 판정을 다시 `stop_event.is_set()` 기준으로 | S2·S3 |
| V-d 래퍼 CRITICAL 을 정상 종료에도 냄 | S1·S8 |
| V-e 재시작 분기 되살림(D1 우회 포함) | S5 |
| V-f `discard` 를 정수 감소로 되돌림 | S6 |
| V-g 예외 종료에서도 집합에서 뺌 | S7(Reconciler 조기 stop) |
| V-h 큐 비우기 제거 | S3(`❌ 예외:` 누락 — 경합 재현을 위해 작업 스레드가 put 직후 set) |
| V-i dedupe 키에서 사용자 제거·dedupe 없음 | S9 |
| V-j 본문에 `str(exc)` 넣기 / `insert_log` 에 `[ENGINE-EXIT]` 원문 넣기 | S11 |
| V-k 운영자 키가 없으면 기본 채널(`TELEGRAM_CHAT_ID`·등급 채널)로 대체 — 예: `_get_credentials(level="OPERATOR")` 를 그대로 씀 | S12 ①(가짜 토큰이 있어야 잡힘), ④ |
| V-l(순서) 큐 비우기를 join 앞으로 | S3-b (S3 는 못 잡음 — put 이 stop 보다 먼저) |
| V-l(상한) 비우기의 시간·개수 상한 **모두** 제거 | S1(10초 단언 — 500건×50ms 설계로 상한이 없을 때만 넘음) |

### 4.3 기존 시험과의 관계

- `test_r_2026_10_28_p4_t11_control.py` `TestRecovery.test_failed_start_not_recovered`:
  - `mark=True` → `[]` 단언은 그대로 성립한다(재시작 자체가 없음).
  - 기준 커밋 비교(`now == old`, `now[0] == 1`)는 성립하지 않는다. 래퍼가 `_start_engine_internal` 을 더는 부르지 않기 때문이다.
  - 이 부분은 S5 로 바꾸고, 주석에 「1028-15 (나): 재시작 분기 삭제 — 기준 커밋의 재시작 1회는 실제 운영에서 D1·D3 로 일어나지 않던 호출이었다」를 적는다.
  - `TestRecovery._run` 의 patch 목록에 **`services.notifier.send` patch 를 넣는다**(verifier 3차 7). 가짜 runner 예외가 이제 래퍼의 CRITICAL 경보 경로를 타므로, patch 하지 않으면 시험이 실제 발송을 시도한다(TELEGRAM 값을 비우면 발송은 안 되지만, 기록으로 0/1건을 단언하기 위해서다).
- `test_engine_manager_no_arg_calls_same_trace_as_base`(t11_control 1260–1266, `_trace` 1269–):
  - 인자 없는 시작 → 실행 확인 → 재시작 거부 → `stop_engine` 의 정상 흐름에서, 호출 흔적을 기준 커밋과 정렬 비교한다. 예외 경로는 이 시험에 없다(독스트링: 「재시작 횟수는 TestRecovery 가 본다」).
  - 따라서 정상 흐름에서 새 `insert_log`·`log_to_file`·`set_*`·notifier 호출이 없어야 이 시험이 그대로 통과한다.
  - 지켜야 할 조건 4가지:
    - 큐 비우기는 빈 큐면 아무 호출도 하지 않는다.
    - 감싸기 함수는 `run_live_loop` 를 같은 인자·같은 kwargs 로 부른다(흔적 `("run_live_loop", test_mode, user_id, kw)` 동일).
    - `add_engine_thread` 첫 인자는 그대로다.
    - CRITICAL 은 예외 때만 낸다.
  - 구현 뒤 이 시험이 **고치지 않고** 통과하는 것을 완료 기준으로 둔다.
- `test_r_2026_09_30_wo12_boot_resume.py` 166·179: 읽기 속성으로 그대로 통과해야 한다.
- 함께 돌릴 것: t11_control·t11_control_fix1·p3_t5_pullback_engine·wo12_boot_resume·`tests/v2/test_engine_alive.py`·`bash scripts/regression_gate.sh`.
- `tests/test_mode_lock.py` 는 git 미추적 파일이다. 참고로만 돌리고 판정 근거로 쓰지 않는다. t11_control `TestOldEngineBehaviour` 독스트링은 이 파일을 언급하지만, 실제로는 wo12 만 불러온다.

## 5. 배포할 때 볼 것

### 5.1 배포 전

- 표준 정지선: 로컬·서버 HEAD(서버 `1747fcc`, 로컬 `13c2d28`), ExecMainStartTimestamp, `dashboard.py` 버전.
- 서버 RUN_MODE: journal 의 `🚀 [RUN_MODE]` 줄로 확인한다(.env 를 읽지 않음). LEGACY_LOCAL 이면 문구가 늘 「기동 중 실패」다.
- 2.3 결정이 (나)면 운영자가 서버 비밀 파일에 운영자 채널 키를 추가한다. 키 이름만 보고하고, 값은 적지 않으며, 권한은 600 이고 사본은 만들지 않는다.
  - 키가 없으면 텔레그램이 나가지 않으므로, 배포와 키 추가의 순서는 상관없다.
  - **운영자 키 추가는 서버 설정 변경이므로 사용자 승인 대상이다**(배포 승인과 따로 묻는다). 승인 전에는 경보가 journal·파일·logs 짧은 문구에만 남는다.
  - `.env` 는 config.py:14–16 의 `load_dotenv()` 로 기동할 때 한 번만 읽는다. 그래서 키를 넣으면 **다음 서비스 재시작부터** 반영된다. 이 `load_dotenv()` 는 `st.secrets["UPBIT_ACCESS"]` 가 없을 때의 `except KeyError` 분기(9–16) 안에 있다. secrets 에 넣는 경우도 프로세스 재시작 뒤 확인한다.
- 과거 피해 규모(읽기 전용): `journalctl -u tradebot | grep -E "엔진 예외|run_live_loop 예외 발생|엔진 최종 실패|Unknown strategy type"`. D4 형태(엔진 시작 뒤 `기동 준비 끝`·봉 처리가 없는데 정지 로그도 없음)도 함께 본다.
- 배포 묶음: 2차 배포에 묶을지 따로 낼지는 사용자가 정한다(남은 결정 2). 따로 낸다면 `1747fcc` 에는 `_ready` 가 없으므로 phase 구분 없이 단일 문구로 줄인다.

### 5.2 배포 직후·관찰 (journal, 24시간)

- `[ENGINE-EXIT]` 0건이 기대값이다.
- 운영자가 정지 → 시작을 1회 해 보고 확인한다.
  - `[ENGINE-EXIT]` 0
  - Reconciler 정지·기동 로그 1회씩
  - (LIVE 사용자가 한 명이면) 정지 때 Reconciler 가 멈춤
- 텔레그램이 오면 문구·채널(운영자 채널인지)·dedupe 를 확인한다.

### 5.3 되돌리기

- engine_manager.py(와 notifier.py) 되돌림. DB 스키마·DB 값 변경은 없다(예외 종료 DB False 는 지금과 같다).
- 되돌리면 「조용한 멈춤」과 카운트 어긋남이 다시 생길 뿐, 매매 경로는 같다.

## 6. 구현 순서 (승인 후)

1. 4.1 시험을 먼저 쓰고, 지금 코드에서 S2(텔레그램 없음)·S3·S4·S6/S7 이 실패하는 것을 확인한다.
2. 3.1–3.5 를 구현한다.
3. 4.1 통과 → 4.2 변이 13개(V-a–V-k, V-l 순서·상한) 모두 잡힘 → 4.3 기존 시험(trace 시험은 고치지 않고 통과).
4. verifier 검증 → 보고 → 커밋 승인 → 배포 승인.

---

## 부록 B. 2단계(1028-18) 후보 — 자동 재시작 (TEST 먼저)

1회차·verifier 2차 지적을 반영해 두었던 설계다. (나)에서는 구현하지 않는다. 1028-18 착수 때 다시 검증한다.

### B-1 권고안 A 요지

- 래퍼를 한 스레드 안의 재시도 루프로 바꾼다. 시도마다 새 stop_event·준비 Event·`_gen +1`.
- 재시도 조건(모두 참일 때만):
  - 예외 종료이고, 준비 신호까지 간 시도
  - 옛 `run_live_loop_{user}_{mode}` 스레드 0(`control_requests._stale_threads` 이름 규칙). `user_lock` 은 작업 스레드를 막지 못하므로 이 확인이 이중 엔진의 유일한 방어다. 살아 있으면 CRITICAL
  - `_no_recover` 없음, 사용자 정지 표식 없음
  - 60분 창 3회 예산 안, 모드별 스위치 켬
- 대기 1·5·15분. 다음 시도의 stop_event 로 `wait(delay)` 해서 대기 중 정지가 바로 먹게 한다.
- ~~대기 뒤에는 전역 잠금 아래에서 `self._threads.get(key) is threading.current_thread()` 로 소유를 확인하고, 조건 전체를 다시 확인한다.~~ **반박됨(N3)** — `stop_engine`(409–413 사전 지우기)과 `_start_engine_internal`(365–373·388 사전 쓰기)이 그 잠금을 잡지 않아 배제가 되지 않는다. 1028-18 에서 사전 쓰기·지우기를 모두 같은 잠금 아래로 옮기는 설계를 새로 세운다(B-7).
- LIVE 집합 변경과 Reconciler start/stop 은 전용 잠금 아래 한 덩어리로 묶는다(N1, B-7).
- 래퍼 루프 본문을 try/finally 로 감싸 정리가 반드시 돌게 한다.
- 기동 전 실패는 복구하지 않는다. `restart_engine` 의 180초 준비 대기와 충돌하기 때문이다. LEGACY_LOCAL 은 `mark_ready` 가 없어 복구가 사실상 꺼진다.

### B-2 사용자 정지 구분 (3.2 남은 경로 포함)

- `stop_engine` 이 Event 를 켜기 전에 시도 Event 에 `user_stop = True`, 보조로 `self._stop_requested.add(key)`. 판정은 시도 Event 속성을 우선한다. `start_engine` 이 `_stop_requested` 를 지운다.
- 이 표식이 생기면 3.2 의 「예외 없는 작업 스레드 종료(LEGACY 생성기 종료 등)」도 「사용자 정지 아님 → 경보」로 구분할 수 있다.

### B-3 DB 상태와 AUTO-RESUME

- ③-a(권고 후보): 재시도 대기·재시도 중에만 True, 포기하면 False.
- ③-b: True 유지 + DB 금지 표식. DB 구조·boot_resume·`pages/dashboard.py`(UI 1-A·1-B 범위)까지 바뀐다.
- 근거: `pages/dashboard.py:412–426` AUTO-RESUME(`not engine_status_thread and engine_status_db`)이 페이지를 그릴 때마다 `start_engine` 을 부르고, `start_engine` 이 `_no_recover` 를 지워(268) 한도·대기를 우회한다.

### B-4 LIVE 위험 (미확인, 1028-18 착수 전 확인)

- **V1 LIVE 고정가 매수 켜짐 + 체결 대기 중 예외.** `_pending_buy_uuid`·`_pending_buy_bar` 가 엔진 메모리에만 있다(core/strategy_engine.py:2475–2510). 체결 콜백은 uuid 가 다르면 건너뛴다(497–504). 재시작하면 이 값을 잃는다. 확인할 것:
  - 새 엔진이 다시 매수를 내는가
  - 옛 주문 체결이 포지션에 반영될 때까지 공백이 생기는가
  - Reconciler 의 봉 마감 취소와 새 엔진이 어긋나는가
  - ~~서버 `fixed_price_buy_enabled` 값은 서버 DB 에 있다~~ → 정정(N6): 이 값은 사용자 조건 JSON 파일(live_loop.py:907–933)에 있고 핫 리로드(838–854)로 실행 중에도 바뀐다. 그래서 「켜짐/꺼짐」 사용자 구분 대신 **예외 시점에 `_pending_buy_uuid` 가 있거나 Reconciler 에 그 사용자의 미체결 매수가 있는지**를 재시작 금지 기준으로 잡는다.
  - `[PENDING-REGISTER]` 는 내부 판정 큐라 이 위험과 별개다.
- V2 기동 직후 첫 봉이 이미 Golden 상태일 때의 매수 여부.
- V3 같은 봉에서 같은 예외가 반복되는지(예산으로 상한).
- 권고 후보(N6 반영): LIVE 재시작은 예외 시점에 미체결 매수(`_pending_buy_uuid` 또는 Reconciler 미체결 매수)가 없을 때만 한다. 있으면 V1 확인 전까지 재시작하지 않고 CRITICAL 을 낸다.

### B-5 폭주·요청 한도

- 시간당 기동은 최대 3회다.
- 업비트 요청 한도(Task 4-0b: 초당 4회·봉 경계 창·429 장기 멈춤)와 복구 워밍업 REST 가 겹치는 문제: 엔진 REST 는 v2 제한기 **밖**이다(N8 — engine·core·services 에서 v2 import 0건). 제한기가 엔진 워밍업을 막아 주지 않으므로, 복구 워밍업 빈도 상한(예산)과 봉 경계 창 회피를 엔진 쪽에서 따로 둔다.

### B-6 시험·변이 후보 (1회차 번호)

- R1–R21: 재시작 1회, 예산·창, 기동 전 실패, 사용자 정지, 대기 중 정지, `_no_recover`, PULLBACK 거부, 전략 바뀜, override, restart_engine 충돌, DB·AUTO-RESUME(R17), 옛 작업 스레드 생존(R14), D4(R15), LEGACY(R16), 카운트(R18), 소유(R19), finally(R20), 고정가 매수(R21).
- M1–M14: 판정·감싸기·새 스레드 재시작·ready 조건·정지 표식·`_no_recover` 재확인·예산 창·`time.sleep`·finally 해제·DB·생존 확인·소유 확인·카운트 멱등·D4 이중 방어.
- (나)에서 이미 다루는 것: R15 → S4, R18 → S6, M13 → V-f, M14 → V-a.

### B-7 verifier 2차 지적 대조표

| 지적 | 요지 | 옮길 B 절 | 상태 |
|---|---|---|---|
| N1 | `_live_users` 변경과 Reconciler start/stop 이 원자적이지 않다. 전용 잠금 아래에서 「넣기·읽기·start」, 「빼기·stop」 을 한 덩어리로 묶어야 한다 | B-1, 본문 3.5(기존 결함) | (나): 범위 밖(새 경로 없음 확인). 1028-18 에서 해결 |
| N2 | 포기할 때 집합에서 빼면 Reconciler 가 멈추고, 미체결 지정가의 시간 초과 취소·체결 기록·HTS 감지도 멈춘다. 권고 (a) 미체결이 있으면 빼지 않는다 | B-3 | (나): 3.5 「예외 종료 땐 빼지 않음」으로 같은 방향. 1028-18 에서 포기 경로에 (a) 적용 |
| N3 | 소유 확인을 전역 잠금으로 해도 `stop_engine`(409–413 사전 지우기)·`_start_engine_internal`(365–373·388 사전 쓰기)이 그 잠금을 잡지 않아 배제가 안 된다. 옛 래퍼가 `_ready` 를 덮으면 새 엔진이 attach 에서 준비 신호를 세우지 않고, `restart_engine` 이 180초 뒤 정상 엔진을 끈다 | B-1 | B-1 해당 문장 **반박됨** 표시. 1028-18 에서 재설계 |
| N4 | 판정을 stop_event 로 하면 안 된다 | — | (나)에서 해소(3.2) |
| N5 | 187행 `__init__` 대입이 읽기 속성과 충돌 | — | (나)에서 해소(3.5) |
| N6 | 고정가 값은 서버 DB 가 아니라 조건 JSON 파일(live_loop.py:907–933)에 있고 핫 리로드(838–854)로 바뀐다. 기준은 「예외 시점 `_pending_buy_uuid` 또는 Reconciler 미체결 매수 유무」로 잡는다 | B-4 | 1028-18. B-4 V1 의 「서버 DB」 서술은 이 지적으로 정정(조건 JSON·핫 리로드, 판정 기준은 예외 시점 미체결 매수 유무) |
| N7 | 루프 종료 뒤 큐에 남은 이벤트 | — | (나)에서 해소(3.1, 3차에서 순서·시간 상한 보강) |
| N8 | 엔진 REST 는 v2 제한기 밖이다(engine·core·services 에서 v2 import 0건) | B-5 | 1028-18. B-5 의 「제한기 공유 여부 미확인」은 「공유 안 함」으로 정정 — 복구 워밍업 빈도 상한은 엔진 쪽에서 따로 둔다 |
| N9 | R17 은 `pages/dashboard.py:390·412` 조건식 원문(`engine_status_thread = engine_manager.is_running(user_id)`, `if not engine_status_thread and engine_status_db:`)을 인용한다 | B-6 | 1028-18 시험 작성 때 반영 |
| 2차 판정 11 | 전역 잠금 구간 안에서 다른 잠금·DB·알림을 부르지 않는다(재진입 교착) | B-1 | 1028-18 설계 조건 |
| 2차 판정 25 | 관리 스레드·작업 스레드 join 시간 미확인 | B-1, 본문 3.1 | (나): S1 의 10초 단언으로 확인. 1028-18 에서 재시도 경로 시간도 측정 |

---

## 정해 주실 것

결정된 것(1028-17 「권고대로」):
- 범위 (나): 조용한 멈춤만 알리고 표시하며, 자동 재시작은 넣지 않는다.
- LIVE 엔진 수를 사용자별 집합으로 멱등화한다.
- 멈춤 경보는 운영자에게만 보내고, 투자자 통보는 없다.
- 자동 재시작은 1028-18(TEST 먼저)로 미룬다.
- 예외 종료 때 DB False 는 유지한다.

남은 결정:
1. **「운영자에게만」을 어떻게 지킬지 (2.3).** 지금 notifier 는 등급별 채널만 있어, CRITICAL 은 투자자도 보는 채널로 간다.
   - 권고: **(나) 운영자 전용 채널 신설.** `send(..., audience="operator")` 를 추가하고, `TELEGRAM_CHAT_ID_OPERATOR` 가 없으면 텔레그램을 보내지 않고 로그에만 남긴다. 운영자가 서버 비밀 파일에 키 1개를 추가한다.
   - 다른 안:
     - (가) 기존 CRITICAL 채널: 투자자에게 보이며, 「체감 변경 통보」 판단이 필요하다.
     - (다) 텔레그램 없음: 목적에 미달한다.
   - 참고: 지시받은 본문의 NO_ACTION_TEXT(「투자자님이 따로 하실 일은 없습니다」)는 투자자를 독자로 한 문장이다. (나)를 고르면 운영자 채널 문구에서 이 줄을 뺄지도 함께 정해 주십시오. 권고는 뺌이다.
2. **배포 묶음.** 2차 배포에 묶을지(권고 — T11 의 `_ready` 로 문구를 나눌 수 있음), `1747fcc` 위에 따로 낼지(단일 문구로 줄임). 묶으면 2차 배포 때까지 서버의 조용한 멈춤(D4) 위험이 그대로 남는다(02fcae9 이후 같은 상태).
3. **대시보드 「트레이딩 엔진 로그」에 남길 예외 종료 줄 (3.3).** 이 화면은 투자자에게 보인다.
   - 선택지: 원문 그대로 / **짧은 문구 1줄(권고)** / 남기지 않음.
   - 원문 비노출을 고르면, 기존 `❌ 엔진 예외(mode=…): {e}`(em 612–614)와 `❌ 예외:` ERROR 줄도 같은 기준으로 맞출지 함께 정한다. 권고: 이번에는 새 줄만 짧게, 기존 두 줄은 별도 작업.
4. **운영자 채널 키 추가 승인 (5.1).** 결정 1 이 (나)이면, 서버 비밀 파일에 `TELEGRAM_CHAT_ID_OPERATOR` 1개를 추가하는 서버 설정 변경을 승인해 주셔야 한다. 배포 승인과 따로 받는다. `.env` 는 config.py:14–16 `load_dotenv()` 로 기동할 때 한 번만 읽으므로, 키를 넣으면 다음 서비스 재시작부터 반영된다.

## 지금 남은 일

- 결정 1–4: 10/29 사용자 「권고대로 승인」(1029-01) — ① (나) 운영자 전용 채널, NO_ACTION_TEXT 뺌 ② 2차 배포에 묶음 ③ 짧은 문구 1줄 ④ 키 추가는 배포 때 따로 승인.
- 구현 → verifier(변이 실행) → Fable → 커밋 승인.
- 결정 뒤 6장 순서로 구현. 1028-18 은 부록 B 에서 시작.

## 구현 메모 (10/29)

계획과 다르게 하거나 더한 것:
1. 텔레그램 제목에서 🚨 를 뺐다. notifier 가 CRITICAL 앞에 이미 붙이기 때문이다.
2. 운영자 본문 끝에 「사용자: {user_id} · 모드: 실계좌/모의」 1줄을 넣었다. 어느 엔진인지 알아야 하기 때문이다. 예외 원문·종목·전략 코드와 NO_ACTION_TEXT 는 넣지 않았다(결정 ①).
3. 작업 스레드 예외(`EngineWorkerError`)일 때는 runner 의 `insert_log("ERROR", "❌ 엔진 예외 …{e}")` 를 생략한다. 새 경로라서, 생략하지 않으면 투자자 화면에 원문 줄이 새로 생긴다. 같은 원문은 큐의 기존 `❌ 예외:` 줄로 이미 남는다. runner 본문 예외일 때의 기존 줄은 그대로다(결정 ③).
4. S3-b 의 가짜 작업 스레드는 stop 뒤 0.7초 쉬고 마지막 이벤트를 넣는다. 0.7초 미만이면 관리 루프의 `q.get(timeout=0.5)` 와 겹쳐 V-l(순서) 변이가 살아남는다.
5. S3 는 앞에 처리가 느린 LOG(0.3초)를 하나 넣어, 큐에 남은 EXCEPTION 을 큐 비우기만 기록하게 했다. 그래야 V-h 를 잡는다.
6. `scripts/regression_gate.sh:26` 의 빈 값 목록에 `TELEGRAM_CHAT_ID_OPERATOR=""` 를 더했다(PO). 로컬 `.streamlit/secrets.toml` 에는 TELEGRAM 키가 0개라 지금도 발송될 경로는 없다. 그래도 운영자 키가 생길 때를 막아 둔다.
7. **사실 정정(3.3):** 옛 대시보드 「트레이딩 엔진 로그」는 LOG 등급만 보여 준다(`pages/dashboard.py:1943` → `services/db.py:289`·336–345). 「상태/경고/에러」(1066)는 CRITICAL 을 뺀다. 그래서 짧은 문구는 옛 화면에는 보이지 않고 v2(`api_read.py:91–100`)에서만 보인다. 등급은 CRITICAL 그대로 둔다(verifier 권고 (가), 2차 배포 때 v2 에서 보임).
8. **구현 수정 1회차 시험 보강:**
   - S3·S11(trading)에 「작업 스레드 예외일 때 insert_log 에 `❌ 엔진 예외` 줄 0건」 단언(X1).
   - S3·S4 에 「`run_live_loop_` 스레드가 excepthook 에 잡힘(감싸기 함수가 다시 raise)」 단언(X4).
   - S13 신설: 다른 시작의 준비 Event(이미 set)로 바뀌어 있으면 「기동 중 실패」 문구(X5, 준비 Event 소유 확인).
   - 결과: 새 시험 24개. 변이 17개(V-a–V-l 13 + V-j2 + X1·X4·X5) 모두 잡힘.

결과:
- 새 시험 24개(`tests/regressions/test_r_2026_10_29_engine_exit_alert.py`), 반복과 동시 실행에서 모두 OK(verifier 재검증 5회).
- 변이 17개(V-a–V-l 13 + V-j2 + X1·X4·X5)를 모두 잡았다(verifier 직접 실행).
- 게이트(10/29 PO 실행): 회귀 846/846, v2 363 OK, v2 JS 통과.
- 미추적 `tests/test_mode_lock.py` 의 `test_mode_match_proceeds_past_guard` 는 HEAD 원본에서도 실패한다(무관, 게이트 밖).
- 남는 경우(Fable impl-1 권고 1): 사용자 정지 때 작업 스레드가 join 2초를 넘겨 살아 있다가 그 뒤 예외로 죽으면 holder 를 다시 읽지 않아 경보가 없다(정상 종료로 처리, 668–673). 지금 코드보다 나빠지지는 않는다. 1028-18 설계 때 참고한다.
