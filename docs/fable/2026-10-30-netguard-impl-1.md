# 질의: 1030-09 「시험 중 업비트(바깥) 호출 차단」 구현 검수 — 커밋 승인 요청 전

**지금 단계:** 구현과 verifier 재검증을 마쳤습니다(커밋 승인 요청 가능). 기준 HEAD 는 5dffe25 이고 아직 커밋하지 않았습니다.

**배경:**
- 10/29 23:16~10/30 00:19, 로컬 맥에서 개발 중 실행한 T15 시험이 업비트로 요청을 보냈습니다.
  - 실행 방식은 게이트 밖 단독 실행과 변이 스크립트였습니다. 변이 스크립트는 subprocess 출력을 DEVNULL 로 버리고 종료 코드만 봤습니다.
  - 요청 내용은 로컬 .env 실키를 쓴 잔고 조회입니다.
- 업비트가 투자자에게 「등록되지 않은 IP」 알림을 보냈습니다. 요청은 모두 401 로 거절됐고 주문은 0건입니다.
- 클레임 답변은 발송했습니다(1030-08, investor-notice-log #7).
- 사용자 결정(1030-09 권고대로)은 두 가지입니다.
  1. 로컬 키 값을 비웁니다. PO 가 처리를 마쳤습니다: .env·secrets.toml 의 UPBIT_ACCESS·UPBIT_SECRET 값 길이 0.
  2. 시험 중 업비트 호출을 차단합니다.

**다음에 하려는 일(이번 질의로 함께 묻습니다):**
1. 사용자에게 커밋·push 승인을 요청합니다(HANDOFF 1030-10).
2. 승인되면 다음 순서로 진행합니다.
   1. `pages/dashboard.py:523` 버전을 v1.2026.10.30.1413 → 커밋 시각으로 바꿉니다.
   2. HANDOFF 를 갱신합니다.
   3. 파일 이름을 하나씩 지정해 add 합니다: 수정 3, 새 6, 이 질의 파일, dashboard.py.
   4. staged 개수 확인 → 비밀 grep → 게이트 전체 실행 → commit → push.
3. 서버에서 게이트를 돌리는 일은 하지 않습니다. 배포 때 확인 항목에 넣습니다.

## 구현 결과
| # | 사실 | 근거 | 확인/추정 |
|---|---|---|---|
| 1 | 게이트 바깥 껍데기가 하는 일 (아래 차례대로) | scripts/regression_gate.sh 바깥 블록 | 확인 (verifier) |
|   | 1) *_PROXY 를 대소문자 모두 unset | | |
|   | 2) NETGUARD=1·NETGUARD_LOG·PYTHONPATH=tests/_netguard 와 업비트 키 자리표시를 export | | |
|   | 3) 자신을 다시 띄워 출력을 tee 로 받음 | | |
|   | 4) 출력·로그 파일·회귀 로그 어디든 [NETGUARD] 줄이 있으면 exit 1, 안쪽 종료 코드는 PIPESTATUS 로 보존 | | |
| 2 | 차단 장치가 감싸는 함수와 동작 | tests/_netguard/guard.py | 확인 |
|   | - 감싸는 함수: getaddrinfo·gethostbyname(_ex)·create_connection·socket.connect/connect_ex | | |
|   | - 막는 범위: 루프백·유닉스 소켓을 뺀 모든 연결. 이름 풀이 전에 막으므로 패킷이 나가지 않음 | | |
|   | - 막으면 NetguardBlocked(RuntimeError) 를 던짐 | | |
|   | - 로그 줄에는 분류·host·via·pid 만 적음 | | |
|   | - 두 번 감싸지 않음 | | |
| 3 | tests.regressions·tests.v2 패키지 __init__ 이 activate() 를 부른다 | tests/_netguard/__init__.py, tests/*/__init__.py | 확인 |
|   | - NETGUARD 환경 변수가 없어도 차단을 켬 | | |
|   | - UPBIT 키 env 를 자리표시 값으로 덮어씀 | | |
|   | - os.environ 에 NETGUARD=1 과 PYTHONPATH 를 넣어 단독 실행의 하위 프로세스도 막음 | | |
| 4 | `discover -s tests/regressions`(-t 없음)에서도 켜진다 | unittest 소스(모듈을 모두 import 한 뒤 실행), 순서 시험 | 확인 |
|   | - test_00_netguard_active.py 가 이름순 맨 앞이라 실행 전에 켜짐 | | |
|   | - 이름순 앞 폴더(fixtures·js)에 test*.py 가 없고 __init__ 가 비어 있는지 시험으로 고정 | | |
| 5 | 차단이 한 번이라도 있었던 패키지 프로세스는 atexit 에서 os._exit(1) 로 끝난다 | guard.py:86-104 | 확인 |
|   | - expected_blocks() 헬퍼는 시험 3곳에서만 씀. 정적 시험이 단어 경계 정규식으로 고정 | | |
|   | - T15 결함을 되살린 변이를 단독 실행: 89 OK 인데 rc=1 (stderr 를 버려도 rc=1) | scratchpad/mutation_t15_standalone2.log | |
| 6 | 게이트 변이 2건(예외를 삼키는 시험)에서도 잡혔다: 시험은 모두 OK 인데 게이트 rc=1 | scratchpad/gate_mutation_swallow.log, gate_mutation_t15.log | 확인 |
| 7 | 시험 결과 (verifier 가 netguard·v2·회귀를 다시 돌림) | scratchpad/gate_netguard4.log | 확인 |
|   | - 게이트 rc=0: 회귀 1139(1122+17), v2 433(430+3), JS 165, [NETGUARD] 0줄 | | |
| 8 | 운영 코드(core·engine·services·ui·v2·pages·app.py·config.py·scripts/v2)·고정 파일 9개·유닛 파일·deploy.sh 는 무변경. 비밀 시그니처 0건 | git diff HEAD --stat | 확인 |
| 9 | 서버 엔진은 tests 패키지와 sitecustomize 를 불러오지 않는다 | git grep(tests 를 import 하는 곳은 scripts/v2/dev_server.py 하나), tradebot-v2.service 에 PYTHONPATH 없음 | 확인(저장소). tradebot.service Environment 는 미확인 |
| 10 | dev_server 가 tests.v2 를 불러오므로 개발 서버에서도 업비트 캔들 받기가 막힌다. 차단이 생기면 종료 코드 1 (PO 결정: 유지) | scripts/v2/dev_server.py:27 | 확인 |
| 11 | 남는 틈 (PO 결정으로 둠) | 게이트 머리 주석, _netguard/__init__.py:6 | 확인 |
|   | - 파일 직접 실행(`python3 tests/.../x.py`): 안내 문구만 둠 | | |
|   | - 패키지를 불러오지 않는 -c·스크립트: 막지 않음 | | |
|   | - python -I/-E 하위 프로세스: 현재 0건 | | |
|   | - 단독 실행 하위 프로세스: 막기만 하고 기록 파일은 없음 | | |
| 12 | 로컬 secrets.toml 의 UPBIT 키는 [secrets] 섹션 아래에 있다. 그래서 config.py 의 최상위 조회가 KeyError → .env 로 넘어간다. 사고 때 쓰인 키도 .env 로 본다 | config.py:9-18, secrets.toml 1행 섹션 이름(값은 안 봄), verifier 실측(config.ACCESS == 자리표시) | 확인(경로) / 사고 때 출처는 추정 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 이 장치로 이번 사고와 같은 경로(개발 중 단독 실행·출력을 버린 변이 스크립트)가 다시 업비트로 나갈 수 있는가 | 없다. 패키지를 불러오면 막히고, 막히면 rc=1 이다 |
| 2 | 운영(서버 엔진·tradebot-v2)에 영향이 생길 경로가 있는가 | 없다. tests 를 불러오지 않는다 |
| 3 | os._exit(1)·환경 변수 덮어쓰기가 정상 시험 실행에 부작용을 주는가 | 차단이 없으면 아무 일도 하지 않는다 |
| 4 | 남는 틈(사실 11)을 그대로 두어도 되는가 | 된다. 사고 경로가 아니고, 키가 비어 있어 계정 알림도 나지 않는다 |
| 5 | 이 상태로 커밋 승인 요청을 올려도 되는가 | 된다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/regression_gate.sh, tests/_netguard/, tests/regressions/__init__.py, tests/v2/__init__.py, tests/regressions/test_00_netguard_active.py, tests/v2/test_00_netguard_active.py, tests/regressions/test_r_2026_10_30_netguard.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/config.py, scripts/v2/dev_server.py, services/upbit_api.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (1030-08·09), docs/operations/investor-notice-log.md (#7)
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fc7131f6-f471-490b-aa6a-ff2242dce9e8/scratchpad/gate_netguard4.log, mutation_t15_standalone2.log, gate_mutation_swallow.log, gate_mutation_t15.log
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 진행. 작업 트리를 직접 읽고 게이트 전체(v2 433·JS 165·회귀 1139·NETGUARD 0건·rc 0)와 netguard 시험을 다시 돌렸습니다. 사실 12개 중 반박 없음, 막음 없음.

- 질문 1: 사고 경로(`-m unittest tests.regressions.X` + DEVNULL)는 패키지 __init__ 이 차단을 켜고, 삼켜도 rc=1 — 같은 경로 재현으로 rc=1 확인. 남는 틈은 패키지를 거치지 않는 실행뿐.
- 질문 2: 운영 영향 경로 없음. tradebot.service Environment 는 미확인이나 켜지는 조건상 결론 불변.
- 질문 3·4·5: 부작용 없음, 틈은 그대로 둬도 됨(로컬 키 비어 서명 요청이 안 됨), 커밋 승인 요청 가능.

**권고:**
1. 커밋 승인 요청(1030-10)에 사용자 결정 문구보다 넓어진 범위 4가지를 적는다: ① 게이트뿐 아니라 tests.regressions·tests.v2 를 불러오는 모든 실행 ② 업비트만이 아니라 루프백 밖 모든 연결 ③ 차단 시 종료 코드 1 ④ dev_server 도 영향.
2. 시험 docstring 이 인용하는 「결정 1030-09 (가)」「지적 3」 원문을 저장소에 남긴다.
3. 사실 5·6 의 변이 로그는 최종 파일 저장 전(14:47~15:02) 실행이고, 같은 내용은 test_r_2026_10_30_netguard 2건으로 스위트에 고정됐다고 적는다.
4. dev_server.py 머리 주석에 차단·종료 1 을 적는다.
5. 배포 때 확인 항목에 「tradebot.service Environment 에 PYTHONPATH·NETGUARD 없음」을 넣는다.

## PO 반영 (10/30)
- 권고 1: HANDOFF 1030-10 행에 넣었습니다.
- 권고 2: 아래 「PO 구현 결정 기록」에 남겼습니다(HANDOFF 1030-09 가 이 파일을 가리킴).
- 권고 3: 사실 5·6 근거 보충 — 변이 로그 3개(gate_mutation_swallow·gate_mutation_t15·mutation_t15_standalone2)는 최종 저장 전 판본에서 돌렸습니다. 같은 동작은 test_swallowed_block_exits_nonzero·test_unittest_run_with_swallowed_block_exits_nonzero 가 최종 파일로 매번 확인합니다.
- 권고 4: scripts/v2/dev_server.py 머리 주석 3줄 추가(코드 변경 없음).
- 권고 5: HANDOFF 1030-10 행의 배포 확인 항목에 넣었습니다.

## PO 구현 결정 기록 (1030-09, 사용자 결정 「권고대로」의 구현 방법)
- 1차 실행 보고 뒤: 결정 (가) — 단독 실행도 막는다. tests/regressions·tests/v2 패키지 __init__ 에서 차단을 켜고 UPBIT 키 env 를 자리표시로 덮어쓴다(이번 사고 실행이 모두 게이트 밖 단독 실행이었기 때문). 업비트 키 자리표시 export 를 게이트에 둔다. 범위는 루프백 밖 전부.
- 2차: 차단이 있었던 패키지 프로세스는 atexit 에서 종료 코드 1(변이 스크립트가 출력을 버리고 종료 코드만 봤기 때문). expected_blocks() 헬퍼는 시험 3곳만, 정적 시험으로 고정.
- verifier 1차 지적 반영: 지적 3(단독 실행 하위 프로세스 미차단) → activate() 가 NETGUARD=1·PYTHONPATH 를 환경에 넣음. 지적 2(파일 직접 실행) → 코드로 막지 않고 안내 문구. 지적 4(dev_server) → 차단 유지. 지적 5 → 이름순 앞 폴더 검사. 지적 6 → 단어 경계 정규식. 지적 7 → 게이트에서 *_PROXY unset.
