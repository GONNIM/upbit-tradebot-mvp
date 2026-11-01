# 1101-05 엔진 시작 겹침 막기 — 계획 (초안 · 수정 3회차 — verifier 2회·Fable 2회차 진행)

- 작성: 2026-11-01 · 기준 로컬 HEAD `ea386f7`(코드는 `f73ec4b` 와 같음 — 서버 실행본)
- 상태: **초안. 코드는 고치지 않았다.** 사용자 결정 1101-05 「㉠ 고칠 계획 작성」, 1101-06 「㉠ 운영자 채널 확인 방법은 이 계획에」.
- 근거: `docs/specs/v2-dashboard/deploy-report-20261101-phase2.md` 2-4절(원 출처 evidence/11), Fable `docs/fable/2026-11-01-phase2-deploy-report-1.md`·`-2.md`.
- 수정 1회차: verifier 1차 「수정 후 승인」 12건 반영. 반영한 곳은 맨 끝 표에 있다.

## 결론
- **엔진 시작에 검사를 하나 더한다.** 이 사용자의 옛 매매 루프(작업 스레드 `run_live_loop_<user>_<MODE>`)나 관리 스레드(`engine_runner_<user>_<MODE>`)가 아직 살아 있으면 시작을 거절한다.
  - 검사 위치: `engine_manager._start_engine_locked` 안, MODE-LOCK 검사 바로 뒤. LIVE Reconciler 기동과 DB 「실행 중」 기록보다 앞이다.
  - 이중 방어로 `_start_engine_internal` 에도 같은 검사를 둔다.
  - 검사 함수는 신버전이 이미 쓰는 것(`control_requests._stale_threads`)과 같은 하나로 만든다.
- 구버전 「엔진 실행하기」 단추가 거절되면 「⏳ 이전 엔진이 아직 정리 중입니다. 1~3분 뒤 다시 눌러 주세요.」를 보여 준다.
- 거절이 정지 뒤 5분을 넘으면 운영자 채널에 WARNING 1건을 보낸다. 옛 루프가 끝나지 않는 경우를 알기 위해서다.
- **매매 판정·주문·REST 확정 재시도(Issue #8)는 바꾸지 않는다.** 정지 뒤 옛 루프가 하던 한 바퀴를 끝까지 도는 것(그 안에서 주문할 수 있음)도 이번 범위 밖이다. 이 계획은 「새 루프가 겹쳐 뜨는 것」만 막는다.
- 운영자 채널(1101-06): 손 도구 1개를 더한다. 배포 때 운영자 입회로 시험 알림 1건을 보낸다(4절).

## 1. 지금 동작 (코드 확인)
| # | 사실 | 근거 |
|---|---|---|
| 1 | `stop_engine` 은 정지 신호를 세우고 관리 스레드만 10초 기다린 뒤, 살아 있는지 보지 않고 `EngineManager._threads` 등 상태를 지운다 | `engine/engine_manager.py:446-456` |
| 2 | 관리 스레드는 작업 스레드를 2초(`WORKER_JOIN_SEC`)만 기다린다. `finally` 에서 `global_state` 등록(`remove_engine_thread`)을 지우고 사용자 잠금을 푼 뒤 끝난다 | `:168`·`:671`·`:686-692` |
| 3 | 작업 스레드는 정지 신호를 루프 머리에서만 본다. 한 바퀴 안의 확정 재시도(최대 17×5초)와 RETRY(5+8+10초)는 정지 신호를 받지 않는다. 주문 경로(`core/strategy_engine.py`)에도 정지 참조가 없다 | `engine/live_loop.py:1688·2112`, `core/rest_reconcile.py:608-613·656-667`, `grep stop_event core/strategy_engine.py` 0건 |
| 4 | `start_engine`(:291-345)은 잠금 안에서 `_start_engine_locked`(:347-388)를 부른다. 이것이 MODE-LOCK(:359-371) → LIVE Reconciler 기동·`_live_users` 추가(:374-379) → `set_engine_status(True, last_mode)`(:384) → `_start_engine_internal`(:390-) 순서로 간다 | 코드 |
| 5 | `_start_engine_internal` 은 등록부의 관리 스레드만 본다 → 옛 작업 스레드가 살아 있어도 시작한다 | `:399-406` |
| 6 | 사용자 잠금(`user_lock`)은 관리 스레드가 잡고(:551-552) 풀므로(:692) 작업 스레드를 막지 못한다 | 코드 |
| 7 | 신버전 시작 요청은 살아 있는 옛 스레드를 `threading.enumerate()` 로 찾아 `old_engine_alive` 로 거절한다. 전환·복귀(`restart_engine`)는 30초 기다리고, 넘으면 CRITICAL 로 멈춘다 | `engine/control_requests.py:715-720·733-734·826-855`, `:84`·`:113` |
| 8 | `start_engine` 직접 호출자는 운영 코드 6곳이다: 구버전 단추 `pages/dashboard.py:663`, 구버전 자동 재개 `:451`·`:489`, 기동 재개 `engine/boot_resume.py:149`, 신버전 `control_requests.py:735·866`. 간접 호출자(`restart_engine` 경유)는 `engine/pullback_apply.py:442·462·487`, `engine/strategy_switch.py:781·850·1064` 이다 | `grep -rn "start_engine("` |
| 9 | 스레드 이름의 MODE 는 대문자(TEST·LIVE)다 | `:314-316`·`:428`·`:634` |
| 10 | 11/01 16:45~16:46 실측: 신버전 정지 → 옛 작업 스레드 81초 재시도 → 구버전 시작 → 24초 겹침, 주문 0 | 보고 2-4절, evidence/11 |

## 2. 고칠 것
### 2-1. 살아 있는 옛 스레드 찾기 — 한 함수로
- `core/engine_control.py`(엔진·신버전 제어가 이미 같이 쓰는 가벼운 모듈)에 `alive_engine_threads(user_id) -> list` 를 둔다.
  - 내용은 지금 `control_requests._stale_threads` 와 같다: 이름이 정확히 `engine_runner_<user>_<MODE>`·`run_live_loop_<user>_<MODE>`(MODE ∈ {TEST, LIVE}) 이고 `is_alive()` 인 스레드.
  - `engine_manager` 를 맨 위에서 import 하지 않게 하려고 이 위치에 둔다.
- `control_requests.Controller._stale_threads` 는 이 함수를 부르게 바꾼다(동작 같음).
- `engine_manager` 는 이 함수를 import 해서 쓴다.

### 2-2. 시작 막기
- 거절 검사는 `_start_engine_locked` 안, MODE-LOCK 검사(:359-371) 바로 뒤, LIVE Reconciler 기동(:374)과 `set_engine_status`(:384)보다 앞에 둔다. MODE-LOCK 과 같은 원칙이다(:356-358 주석).
  - `start_engine` 맨 앞에는 두지 않는다. 정상 실행 중인 엔진의 `engine_runner_` 스레드가 걸려 「이미 실행 중」(:324-329)·MODE-LOCK 판정을 가리기 때문이다.
  - 여기서 거절하면 `engine_status`·`last_mode`·Reconciler·`_live_users` 를 건드리지 않는다(logs 표에 1줄만 쓴다). `_start_engine_internal` 에서만 거절하면 DB 가 「실행 중」으로 남는다. 그러면 구버전 자동 재개(`dashboard.py:440`)나 기동 재개가 사용자가 누르지 않은 엔진을 켤 수 있다.
- `_start_engine_internal` 의 머리에도 같은 검사를 둔다(이중 방어, 경합 대비).
- 거절할 때 하는 일:
  - journal: `logger.warning("[ENGINE-START] 옛 엔진 스레드가 아직 살아 있어 시작 거절 | user=… alive=<이름 목록> since_stop=<초>")` 1줄
  - 투자자 화면 logs: `insert_log(user, "INFO", "이전 엔진 정리 중 — 시작을 미뤘습니다")` 1줄
  - 거절 이유 `self._last_start_reject[key] = "old_engine_alive"`
  - `False` 반환
- 거절 이유 저장: `__init__` 에 `self._last_start_reject = {}` 를 만들고, `start_engine` 호출마다 맨 먼저 이 사용자 키를 지운다. 읽는 함수는 `last_start_reject(user_id, mode)` 이다.
- 정상 경로(거절이 아닐 때)는 로그·DB 호출을 하나도 더하지 않는다. 기준 커밋과 호출 흔적을 비교하는 기존 시험(`test_r_2026_10_28_p4_t11_control.py:1255-1261`)이 있다.
- 모드가 달라도 막는다. 같은 사용자의 실계좌·모의 루프가 겹치는 것도 막고, 신버전과 같은 기준이다.
- 신버전 시작 경합: `_engine_start`(:735-738)가 `start_engine` False 를 받았는데 `last_start_reject == "old_engine_alive"` 이면 `start_failed` 대신 `old_engine_alive` 를 돌려준다. 전환·복귀(:866)는 이미 옛 스레드 대기 뒤에 부르므로 경합 때만 `start_failed` 가 된다. 이 부분은 지금 그대로 둔다.

### 2-3. 거절이 오래 이어질 때 (운영자 경보)
- `stop_engine` 이 정지 시각을 `self._stopped_at[key] = time.monotonic()` 으로 남긴다.
- 거절 때 정지 뒤 경과가 300초를 넘으면 운영자 채널(`audience=AUDIENCE_OPERATOR`)로 WARNING 1건을 보낸다.
  - 문구: 「앞 엔진이 5분 넘게 끝나지 않아 시작을 거절하고 있습니다 — 운영자 확인」
  - dedupe 키 `engine_start_old_alive:{user}`, 600초
  - 신버전 전환의 30초 CRITICAL(`control_requests.py:846-855`)과 짝을 맞춘다.
- `_stopped_at` 수명: `stop_engine` 의 상태 pop(:452-456)에 넣지 않는다. 시작에 성공하면 지운다. 정지 기록이 없는데 옛 스레드만 살아 있으면 경보 없이 로그에 `since_stop=?` 만 남긴다.
- 경보 HTTP(`send`, 최대 5초 — `notifier.py:37`)는 시작 잠금(`_start_lock`)을 푼 뒤 보낸다. 잠금 안에서는 「보낼지」만 정한다. 그래야 다른 시작과 화면이 멈추지 않는다.
- 한계: 경보는 누군가 다시 시작을 눌렀을 때만 나간다. 아무도 누르지 않으면 경보가 없다. 이때는 엔진이 멈춘 상태라 화면의 「정지」 표시로 보인다.

### 2-4. 구버전 화면 (`pages/dashboard.py:663` 실패 분기 `:681-`)
- `engine_manager.last_start_reject(...) == "old_engine_alive"` 이면:
  - `st.warning("⏳ 이전 엔진이 아직 정리 중입니다. 1~3분 뒤 다시 눌러 주세요.")`
  - 실패 알림(`engine_start_fail`)은 보내지 않는다. 반복 클릭에 따른 알림 남발을 막으려는 것이다. 오래 이어지면 2-3 경보가 간다.
- 그 밖의 실패는 지금 문구·알림 그대로다.
- 자동 재개(`:451`·`:489`)가 거절되면, 엔진 쪽은 DB 를 바꾸지 않는다. 화면 쪽은 지금처럼 `_resumed` 가 거짓이면 `set_engine_status(False)` 로 정정한다(안전한 방향, `dashboard.py:496·499`). 지금 실패 분기는 그대로 둔다.
- 이 화면 변경은 투자자 체감 변경(문구 1개)이다(5절 통보).

### 2-5. 하지 않는 것
| 후보 | 왜 안 하는지 |
|---|---|
| 확정 재시도·RETRY 안에서 정지 신호 보기 | Issue #8(미확정 종가) 핵심 경로. 정지 응답을 빠르게 할 뿐이고 겹침은 2-2 로 막힘. 따로 계획 |
| 정지 뒤 옛 루프가 하던 한 바퀴의 주문 막기 | 주문 경로에 정지 신호를 넣는 일. 매매 경로 변경이라 따로 계획 |
| `stop_engine` 이 작업 스레드를 끝까지 기다리기 | 화면(Streamlit)과 신버전 요청 처리 스레드가 최대 2분 넘게 멈춤 |
| 자동 재시작(1028-18) | 별도 작업. 이 고침이 그 전제(옛 작업 스레드 0 확인)를 채운다 |

## 3. 시험 (바깥 연결 없음, netguard 켬)
새 회귀 시험 `tests/regressions/test_r_2026_11_01_engine_start_overlap.py`. 사용자 이름은 이 파일만 쓰는 고유 이름으로 하고, 띄운 가짜 스레드는 tearDown 에서 풀고 join 한다(다른 시험과 경합 방지).
1. 이름이 `run_live_loop_<U>_LIVE` 인 가짜 스레드(Event 로 붙잡음)가 살아 있을 때:
   - `start_engine(U, mode="LIVE")`·`mode="TEST")` 모두 `False`, `last_start_reject` = `old_engine_alive`
   - 관리 스레드 생성 0
   - `services.db.set_engine_status` 호출 0(patch 위치는 `services.db`)
   - LIVE 일 때 `rec.start` 0회, `_live_users` 무변경, `_strategy_override` 원복
2. 가짜 스레드를 풀어 끝낸 뒤 같은 호출은 `True`, `last_start_reject` 는 None.
3. 다른 사용자 이름의 스레드는 막지 않는다.
4. `engine_runner_<U>_TEST` 만 살아 있어도 막는다.
5. `Controller._stale_threads` 와 `alive_engine_threads` 가 같은 결과를 돌려준다. 신버전 시작 경합 때 `old_engine_alive` 코드가 나온다.
6. 정상 경로 무변경:
   - (a) 실행 중 같은 모드 재시작은 False, `last_start_reject` None, WARNING 없음
   - (b) 다른 모드는 MODE-LOCK WARN 그대로
   - (c) 정지 직후 옛 작업 스레드가 2초 안에 끝나면 바로 시작이 True
7. 2-3: 정지 시각을 301초 전으로 두고 거절하면 가짜 notifier 가 `audience=operator`·WARNING 으로 1번 불린다. 299초면 0번이다.
8. 화면: `pages/dashboard.py` 실패 분기에 `old_engine_alive` 문구가 있고, 그 분기에 알림 호출이 없는지 소스 검사로 본다.
9. 변이: 2-2 검사를 지우면 1번이 실패하는지, 검사를 `_start_engine_internal` 에만 두면 1번의 `set_engine_status` 0 이 실패하는지 확인한다.
- 기존 시험 전체(`scripts/regression_gate.sh`, 지금 1162 — 11/01 `ea386f7` push 때 pre-push 게이트 실측 + 새 시험)와 v2·JS 시험을 돌린다.
- 기존 시험에서 `start_engine` 이 뜻밖에 False 를 돌려주면, 앞 시험이 흘린 `engine_runner_<USER>_*`·`run_live_loop_<USER>_*` 스레드일 수 있다. 검사를 느슨하게 하지 말고 그 시험의 정리(stop·join)를 고친다.
- 화면 확인(1-A): 배포 뒤 운영자 브라우저 확인. 보유 0 일 때만, 정지 직후 바로 「엔진 실행하기」를 눌러 문구가 나오는지 본다.
- **고정 파일 기준 올리기:** `engine/engine_manager.py` 는 바이트 고정 파일이다.
  - 고정 시험 3개:
    - T13 `test_r_2026_10_29_p4_t13_apply.py:45-46·654-660`(`FIXED_FILES_COMMIT 6b6f0b5`)
    - T14 `test_r_2026_10_29_p4_t14_ops.py:297-298`
    - T15 `test_r_2026_10_29_p4_t15_old_ui.py:1164-1172` `TestFixedFiles`(`8464b58`)
  - 이번 변경은 일부러 바꾸는 것이므로 `tests/regressions/baseline_commits.py:14-24` 1번 규칙을 따른다:
    1. 보고에 「EMA 공용 경로 변경 — 시작 검사만, 매매 경로 무변경」을 적는다.
    2. 코드 커밋 뒤 `FIXED_FILES_COMMIT` 을 그 커밋으로 올린다.
    3. T15 `TestFixedFiles` 는 `engine_manager.py` 만 새 기준으로 비교하게 바꾼다. 그 테스트의 `BASE_COMMIT` 은 화면 비교에도 쓰이므로 통째로 올리지 않는다.
    4. 커밋 메시지에 「기준 커밋 <옛> → <새>: 사유」를 적는다.
  - `pages/dashboard.py`·`engine/control_requests.py`·`core/engine_control.py` 도 같은 고정 목록에 있는지 구현 첫 단계에서 `grep` 으로 보고, 있으면 같이 다룬다.

## 4. 운영자 채널 실제 발송 확인 (1101-06)
- 손 도구 `scripts/v2/notify_operator_test.py`:
  - 저장소 루트에서 실행한다. 맨 먼저 저장소 루트의 `.env` 를 스스로 읽는다(`dotenv.load_dotenv(ROOT / ".env", override=False)`). `import config` 에 기대지 않는다.
    - 서버의 tradebot 은 systemd `EnvironmentFile=/root/upbit-tradebot-mvp/.env` 로 `.env` 를 환경 변수로 받는다(11/01 서버 확인, 배포 보고 evidence/05). 도구는 systemd 밖에서 돈다.
    - `config.py:10-16` 은 `st.secrets["UPBIT_ACCESS"]` 가 있으면 `load_dotenv()` 를 부르지 않는다. 서버는 업비트 키가 secrets.toml, 텔레그램 키가 `.env` 에 있다(요청서 1절·:43). 그래서 `config` 로는 운영자 키를 못 읽어 거짓 「없음」이 된다(Fable 1101-05-plan-1).
    - `load_dotenv` 는 파일이 없어도 예외 없이 False 를 돌려준다. 그래서 `ROOT/.env` 존재와 반환값을 함께 보고, 없으면 「.env 없음」을 따로 출력하고 끝낸다. 읽다가 예외가 나면 예외 종류만 출력한다(값 비기재).
  - `WO6_DRY_RUN` 이 켜져 있으면 「드라이런 — 중단」을 출력하고 끝낸다.
  - `services.notifier._get_operator_credentials()` 로 토큰·운영자 채팅 ID 의 **있음/없음만** 출력한다(값 비기재). 운영자 키는 `TELEGRAM_BOT_TOKEN` 과 `TELEGRAM_CHAT_ID_OPERATOR` 둘이다. 하나라도 없으면 보내지 않고 끝낸다.
  - `send(LEVEL_INFO, "운영자 채널 시험", …, audience=AUDIENCE_OPERATOR, dedupe_key="operator_channel_test")` 1건을 보낸다.
  - 결과는 「보냄(True)」 또는 「못 보냄(False — journal `[NOTIFY]` 줄 확인)」로만 출력한다.
- 시험(바깥 연결 없음):
  - 가짜 notifier 로 `audience=operator` 1번 호출을 확인한다.
  - 키가 없거나 `WO6_DRY_RUN` 이면 보내지 않는지 본다.
  - 환경 변수는 비우고 임시 `.env` 에만 가짜 키 이름 2개를 넣은 상태(secrets 에 `UPBIT_ACCESS` 가 있는 경우 포함)에서 「있음」으로 판정하는지 본다. 발송 직전에서 멈추는 `WO6_DRY_RUN=1` 로 돌린다.
  - 출력에 값이 없는지 소스 검사(`print` 인자에 키 변수 없음)로 본다.
- 배포 때(별도 승인) 운영자 입회로 서버에서 1회 실행한다. 운영자가 운영자 채널 수신을 확인한다.
  - 실행 전 읽기 전용 확인: `systemctl show tradebot -p EnvironmentFiles`, `ls -l .env .streamlit/secrets.toml`
  - **외부 발송이므로 실행 직전에 한 번 더 묻는다.**

## 5. 커밋·배포 (각각 별도 승인)
- 커밋 순서: 코드 커밋(버전 갱신) → 고정 파일 기준 올림 커밋(3절) → push 1회. 기준은 push 된 커밋이어야 하므로(`baseline_commits.py:22`) 두 커밋을 함께 push 하고, push 때 게이트가 돈다.
- 커밋 전: `pages/dashboard.py` 버전 `v1.YYYY.MM.DD.HHMM` 을 갱신한다. `regression_gate.sh` 수치를 보고에 적는다. UI diff(문구 1개 추가, 접힘·이동 없음)를 사용자에게 적는다.
- 배포: tradebot 재시작 1회(엔진 코드). 2차 배포 2-3 조건(봉 직후·경계 60초·미체결 0·보유 확인)을 그대로 쓴다.
  - v2 는 재시작하지 않는다. `core/engine_control.py`·`control_requests.py`·`engine_manager.py` 는 tradebot 프로세스 모듈이고, v2(`-m v2.server`)는 이 파일들을 import 하지 않는다.
  - 보고에 「버전: 구 → 신」과 3점 일치를 적는다.
- 통보(체감 변경): 「엔진을 멈춘 직후 다시 시작하면 『이전 엔진이 아직 정리 중』 안내가 나올 수 있습니다. 1~3분 뒤 다시 누르시면 됩니다.」 한 줄. 보낸 통보는 `docs/operations/investor-notice-log.md` 에 기록한다.
- 고치기 전까지 임시 규칙: 정지 뒤 3분 이상, 시작은 신버전 단추.

## 6. 영향
| 축 | 바뀌는 것 | 위험 | 막는 장치 |
|---|---|---|---|
| 매매 | 없음(판정·주문 경로 무변경) | — | 시험 1~6·9, 게이트 |
| 엔진 시작 | 옛 스레드가 살아 있으면 거절 | 정상 시작을 잘못 거절(이름 충돌·경합) | 이름 정확 일치, 시험 3·6 |
| 엔진 시작(장기) | 옛 루프가 안 끝나면 프로세스 재시작 전까지 거절 | 운영자가 모름 | 2-3 운영자 경보(5분) |
| DB | 거절 때 `engine_status`·`last_mode` 무변경 | internal 에서만 거절하면 「실행 중」 잔존 | 2-2 위치, 시험 1·9 |
| 기동 재개 | 서버 재시작 직후에는 옛 스레드가 없음 → 영향 없음 | — | boot_resume 시험 그대로 |
| 화면 | 구버전 실패 문구 1개 | 투자자 혼선 | 통보 한 줄, 브라우저 확인 |
| 알림 | 거절 때 투자자 실패 알림 없음, 5분 넘으면 운영자 경보 | — | 시험 7 |
| 자격증명 | 손 도구가 토큰·운영자 채팅 ID 를 읽음 | 값 출력 | 있음/없음만 출력, 소스 검사 |
| 업비트 한도 | 새 호출 없음(겹침이 막히면 줄어듦) | — | — |

## 정해 주실 것 (계획 승인 때)
| # | 정할 것 | 권고 |
|---|---|---|
| 1 | 이 계획대로 구현 | 승인 |
| 2 | 거절이 5분 넘게 이어지면 운영자 채널 경보 1건 | 넣음 |

## 수정 1회차 반영표 (verifier 1차)
| 지적 | 반영 |
|---|---|
| 1 화면 문구 「새 매매 없음」은 보장 안 됨 | 결론·2-4 문구에서 지움, 2-5 에 한 바퀴 주문 가능성 |
| 2 검사 위치 `_start_engine_locked` MODE-LOCK 뒤 필수 | 결론·2-2, 정할 것에서 뺌 |
| 3 장기 거절 경보 | 2-3 신설, 시험 7, 정할 것 2 |
| 4 버전 갱신 | 5절 |
| 5 거절 이유 초기화·지우기 | 2-2 |
| 6 정상 경로 시험 | 시험 1·6 |
| 7 손 도구 자격증명 출처·출력 | 4절 |
| 8 공용 함수 위치 | 2-1 `core/engine_control.py` |
| 9 신버전 시작 경합 코드 | 2-2 끝, 시험 5 |
| 10 시험 사용자 이름·join | 3절 머리 |
| 11 로그 대상 구분 | 2-2 |
| 12 통보 기록 | 5절 |
| 판정 2·3·7·17·19 문장 | 1절 2·3·8, 2-1, 5절 |

## 수정 2회차 반영표 (verifier 2차 「수정 후 승인」)
| 지적 | 반영 |
|---|---|
| 1 engine_manager.py 바이트 고정 시험 3개 | 3절 끝 「고정 파일 기준 올리기」, 5절 커밋 순서 |
| 2 `.env` 경로 근거 | 4절 — 서버 systemd EnvironmentFile 확인(evidence/05)과 도구의 `load_dotenv` 를 나눠 적음 |
| 3 경보 HTTP 잠금 밖 | 2-3 |
| 4 `_stopped_at` 수명 | 2-3 |
| 5 config import 실패 | 4절 |
| 6 「DB 를 건드리지 않는다」 문구 | 2-2 |
| R8 경보 한계 | 2-3 |

- verifier 1·2차 판정 원문은 세션 안에만 있고 파일로 남기지 않았다. 위 두 반영표가 그 요약이다.

## 수정 3회차 반영표 (Fable `docs/fable/2026-11-01-1101-05-plan-1.md` 「수정 후 진행」)
| 지적 | 반영 |
|---|---|
| 1 (막음) 도구가 `config` 로 `.env` 를 못 읽음 | 4절 — `.env` 를 직접 읽음, 시험 추가 |
| 2 자동 재개 DB 정정 문장 | 2-4 |
| 3 흘린 스레드로 기존 시험 실패 가능 | 3절 |
| 4 verifier 원문 미보관 | 위 한 줄 |
| 5 1162 출처 | 3절 |

## 구현 기록 (11/01 · 사용자 승인 1101-09 ㉠, 1101-10 ㉠)
- 바뀐 파일:
  - `core/engine_control.py`(`alive_engine_threads`)
  - `engine/control_requests.py`(위임·경합 코드)
  - `engine/engine_manager.py`(검사·경보·`last_start_reject`)
  - `pages/dashboard.py`(문구·버전)
  - 새 `scripts/v2/notify_operator_test.py`
  - 새 시험 2개(overlap 16·도구 7)
- 계획과 다른 점:
  - 투자자 화면 logs 문구를 「⏳ 이전 엔진 정리 중 — 시작을 미뤘습니다. 1~3분 뒤 다시 눌러 주세요.」로 늘렸다. 투자자가 할 일을 함께 적으려는 것이다.
  - 도구가 notifier 로거를 끈다(`quiet_notifier_log`). `notifier.py:218` 의 예외 경고 문구에 토큰 URL 이 섞일 수 있어서다(verifier 지적).
  - 도구는 `load_dotenv` 반환값도 본다(빈 `.env` 면 「읽을 줄 없음」).
- 남긴 한계:
  - 거절 이유 지우기(`_last_start_reject.pop`)는 시작 잠금 밖이다. 같은 사용자의 시작 2건이 동시에 오면, 앞 호출이 일반 「시작 실패」 안내·알림을 볼 수 있다(알림 1건 오발송 수준).
  - 예외 종료 뒤 작업 스레드만 남은 경우는 정지 시각이 없어 5분 경보가 없다(예외 종료 CRITICAL 이 따로 나감).
  - `notifier.py:218` 의 journal 토큰 노출 가능성은 매매 무관 별도 변경으로 남긴다(후속).
  - **신버전 시작 단추로 거절될 때는 5분 운영자 경보가 나가지 않는다.** 신버전은 `control_requests.py:733-734` 에서 `start_engine` 을 부르기 전에 `old_engine_alive` 로 거절한다. 경보는 `start_engine` 안에서만 정한다(`engine_manager.py:353`). 경보가 나가는 것은 구버전 단추·자동 재개·기동 재개·신버전 경합 때다. 임시 규칙이 「시작은 신버전 단추」라 실제로는 경보가 드물다(Fable impl-1 막음). → **사용자 결정 1101-11 ㉠ 으로 메움:** 신버전 거절 자리에서 `EngineManager.note_old_alive_reject(user, mode)` 를 불러 같은 기준(정지 뒤 300초 초과)·같은 dedupe 키로 운영자 경보를 보낸다. 판단 예외는 결과(`old_engine_alive`)를 바꾸지 않는다. 시험 3개 추가(23 OK), 변이 D(호출 끔) 실패 확인.
- 검증:
  - 새 시험 23 OK(overlap 16·도구 7).
  - 변이 A(락 단계 검사 끔)에서 LIVE·TEST 모두 실패하고, 변이 C(로거 끄기 끔)에서 토큰 시험이 실패한다.
  - 전체 게이트는 고정 파일 3건 외 통과(기준 올림은 커밋 단계).
  - verifier 1회 「수정 후 승인」 → 반영.
