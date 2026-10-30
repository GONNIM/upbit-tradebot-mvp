# 질의: 2차 T18(서버 점검 스크립트 항목 추가) 착수 전 정지선 — PO 결정 6건과 사용자 결정 2건

**지금 단계:** T18 착수 전 정지선입니다. 기준 HEAD 는 413516b 이고 아직 파일은 바꾸지 않았습니다.
- 대상 4개 파일(`scripts/v2/check_v2_unit.sh`, `scripts/v2/check_v2_unit_probe.py`, `tests/v2/test_deploy_files.py`, `deploy/tradebot-v2.service`)과 `docs/operations/v2-runbook.md` 는 서버 실행본 1747fcc 와 diff 0 입니다(실행 에이전트 확인).
- 바뀌는 것은 서버에서 손으로 돌리는 읽기 전용 점검 스크립트·시험·runbook 뿐입니다. 고정 파일 9개, 스키마, 실계좌 EMA 경로는 무변경입니다.

**다음에 하려는 일:**
1. 아래 PO 결정을 확정하고 사용자 결정 2건(A·B)을 올립니다(HANDOFF 1030-06).
2. 결정을 받으면 실행 에이전트가 두 스크립트·시험·runbook·계획 메모를 고칩니다(계획 :874 사실 정정 묶음).
3. 그 뒤 verifier → Fable → 커밋 승인으로 갑니다. 스크립트 실행은 배포 때입니다.

## 실행 에이전트 정지선 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | 신버전이 첫 요청 때 v2_control 폴더와 사용자 폴더를 만들고 700 으로 chmod 한다. 엔진은 만들지 않는다(T11 메모). 계획 :874 「엔진도 없으면 만든다」는 메모와 어긋난다 | v2/control.py:47-56, plan-phase2.md:874,968 |
| 2 | 요청 파일은 `.req-<id>.tmp` → `req-<id>.json`(600), 결과 `res-<id>.json` 은 엔진이 600 으로 원자적으로 쓴다. 배포 직후엔 0개일 수 있다 | v2/control.py:126-132, engine/control_requests.py:232,640 |
| 3 | 적용본 `{user}_applied_params_PULLBACK.json`·`.last_good.json` 은 저장소 루트, mkstemp→chmod 600→replace. 활성 EMA 로 배포하므로 첫 전환 전엔 없음이 정상 | engine/pullback_params.py:84,88,282-292, HANDOFF 1028-04 |
| 4 | 기존 시험이 probe 의 open 인자에 「PULLBACK」이 있으면 r+, 없으면 r/rb 만 허용한다. 적용본 변수명이 PULLBACK 을 포함하지 않으면 충돌 | tests/v2/test_deploy_files.py:229-250 |
| 5 | 파일이 없으면 `open r+` 는 FileNotFoundError 라 EROFS 를 증명하지 못한다. 같은 폴더 쓰기 차단은 `root-readonly` 가 이미 본다 | check_v2_unit_probe.py:165-181 |
| 6 | `saved-writable-by-v2` 는 기존 `pullback-open`·`pullback-inode-match` 와 같은 검사다 | probe:200-209, sh:112-121 |
| 7 | 셸은 `PROP_RW_PATHS` 를 넘기기만 하고 비교하지 않는다. `systemctl show` 의 `-` 접두 유지 여부는 미확인 | check_v2_unit.sh:47,69, v2-runbook.md:170 |
| 8 | `EXPECTED_PROBE_LINES=10` 과 검사 함수 수 10 을 시험이 단언하고, runbook 에 「탐침 10항목」이 있다 | sh:29, test:159,262, runbook:146,171 |
| 9 | Step 6 의 「로컬 dev 서버 + Streamlit 으로 전환·예약·복귀·강제 매도 실측」은 dev_server.py 가 엔진 없는 v2 전용 가짜 루트라 그대로는 못 한다. T13~T16 메모는 브라우저 실측을 배포 뒤로 넘겼다 | scripts/v2/dev_server.py, plan-phase2.md:1433, T16 메모 |
| 10 | §12-10 「신버전이 결과 파일을 읽을 수 있는지 T18 로 서버에서 확인」이 T18 항목 목록에서 빠졌다 | plan-phase2.md:1572 |
| 11 | 투자자 통보 초안 B(:1505-1507)는 「전환·복귀·예약 취소를 쓰실 수 있다」고 적었으나 새 전략은 LIVE 거부·실계좌 입장 전환 닫힘이다. T13 거절 문구 2개 등 체감 변경 7건이 빠졌다 | plan-phase2.md:670,1118,1180,1505-1507, HANDOFF 1029-07·1029-11·1029-10·1030-02 |
| 12 | HANDOFF 「2차 배포 때 할 일」 메모 12건 중 다수가 §10·§3 배포 절차에 없다(User/UMask/python/MemoryMax, PRAGMA 24칸, 경고 키 이름, meta 칸, BUY_FAILED_API 4건, 24h ENGINE-EXIT, REVERT_OLD_CODE_COMMIT 갱신 등) | plan-phase2.md:246-260,1472-1499, HANDOFF:76-119 |

## PO 결정(사실·위험만 확인 요청)
1. **없음 표기:** 폴더·파일이 없으면 `PASS <항목>(absent)`(선례 `v2hist-write(folder)`). 있을 때만 lstat 으로 모드·소유자·링크 여부를 본다. 내용은 열지 않는다.
2. **적용본 없음:** 파일을 만들어 시험하지 않는다(엔진의 「0바이트」 경우를 건드림). 없으면 `os.access(ROOT, W_OK)` False 확인 후 `(absent)`. 있으면 `os.access(W_OK)` False 와 `open(…,"r+")` 실패(OSError, errno EROFS 또는 EACCES)를 기대한다. 시험 규칙은 「PULLBACK 또는 적용본 변수 인자는 r+ 만」으로 넓힌다.
3. **`saved-writable-by-v2`:** 새 항목을 만들지 않고 기존 `pullback-open` 을 대응 항목으로 runbook·계획에 적는다(이름 무변경).
4. **`unit-rw-paths-unchanged`:** 셸이 `PROP_RW_PATHS` 를 토큰으로 나누고 앞 `-` 를 뗀 뒤, 모든 토큰이 `…/services/data` 또는 `…/<user>_latest_params_PULLBACK.json` 이고 그 둘이 모두 있는지 본다. 값은 출력하지 않는다. 적용본 경로가 들어가는 것도 막는다.
5. **결과 파일 읽기 항목 추가(§12-10):** `v2-control-results-readable` — 결과 파일 1개에 `rb` 로 `read(1)` 만. 없으면 `(absent)`.
6. 탐침 줄 수 10 → 15, 시험 단언·runbook :146·:171 을 함께 고친다. 계획 :874 를 「엔진은 만들지 않음」으로 정정한다. 사실 11·12 는 T18 코드와 무관하므로 HANDOFF 2차 배포 줄에 「배포 승인 요청서에서 §10 에 모아 넣고 통보 문안 B 를 다시 쓴다」로 적고, 그 결정은 배포 요청서 때 사용자에게 올린다.

## 사용자에게 올릴 결정(초안)
| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| A | 점검 스크립트를 언제 다시 돌릴지 | (가) 배포 때 한 번 + 첫 모의 전환 입회(§10-5) 때 한 번 더 돌린다. 읽기 전용이고 서비스는 건드리지 않는다 / (나) 배포 때 한 번만 돌린다. 배포 직후 새 항목 5개 중 4개는 「없음」이라 실제 검증이 안 된다 | (가) |
| B | Step 6 「로컬 흐름 실측」 방법 | (가) 가짜 루트 실측 도구를 새로 만든다. dev 서버에 새 전략 픽스처를 넣고 같은 루트에서 Controller 와 가짜 엔진 관리자·거래기로 요청을 처리한다. 로컬 `.env` 를 읽지 않고 업비트 호출 0. 화면은 배포 뒤 412·360·1440 실측 / (나) 로컬에서 실제 엔진을 TEST 가짜 계정으로 띄운다. 로컬 `.env` 를 읽고 업비트 공개 캔들을 받는다. 1025-05 「실제 계정 값 자동 입력」 사건과 같은 위험 / (다) 로컬 실측을 빼고 배포 뒤 실측만 한다(T13~T16 과 같음). 계획 Step 6 을 그렇게 고친다 | (가) |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~12 가 맞는가 | 맞다 |
| 2 | PO 결정 2 의 「있으면 r+ 실패 기대」가 유닛 안에서 파일을 만들거나 내용을 바꿀 위험이 없는가(`r+` 는 O_CREAT 없음·O_TRUNC 없음) | 없다. 열기 실패를 기대하고, 혹시 열리면 닫기만 하고 FAIL 로 쓴다 |
| 3 | 결정 B (가)의 가짜 루트 도구가 시험 이상으로 무엇을 더 증명하는가. 들이는 노력에 비해 (다)가 맞지 않은가 | (가)는 신버전 쓰기 API → 파일 통로 → Controller → 결과 파일 → 화면 응답을 한 프로세스 안에서 실제 파일로 잇는다. 단위 시험은 각 구간을 따로 본다. 실 엔진·업비트 없이 할 수 있는 최대 범위라 (가)를 권한다 |
| 4 | 사실 11·12 를 T18 밖(배포 요청서)으로 미루는 것이 맞는가 | 맞다. T18 코드와 무관하고, 배포는 따로 승인받는다 |
| 5 | 이 표로 사용자 결정을 요청해도 되는가 | 된다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md §T18(:1419-1433), §10(:1472-1510), §12(:1560-1580), :874, :968
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit.sh, scripts/v2/check_v2_unit_probe.py, tests/v2/test_deploy_files.py, deploy/tradebot-v2.service, docs/operations/v2-runbook.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/control.py, engine/control_requests.py, engine/pullback_params.py, scripts/v2/dev_server.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 멈춤. 사용자 결정 A·B 만 남아서 멈춤으로 둡니다. 사실 1~12 와 PO 결정 1~6 은 근거와 맞고 막음은 없습니다(사실 11 의 「7건」 수만 확신 보통).

- 질문 2: `open(…,"r+")` 는 O_CREAT·O_TRUNC 가 없어 파일을 만들거나 바꾸지 않습니다. 기존 시험(:248 `.write(` 금지, :250 os.open RDWR 금지)이 구현 실수도 잡습니다.
- 질문 3: 가짜 루트 도구가 메우는 틈(`write_request` → Controller → `read_result` 를 실제 파일로 잇는 시험 없음)은 실제로 있습니다. 다만 임시 폴더 통합 시험 1건(T11 가짜 관리자·거래기 재사용, 게이트 포함)으로 같은 값을 얻으므로 (라)를 권합니다.

**권고:**
1. 결정 B 에 (라)를 더하고, 어느 선택지든 계획 :1433 Step 6 의 「로컬 Streamlit」 문구를 고칩니다.
2. A (가)이면 runbook :161·probe :47 의 「한 번만 실행」을 「배포 때와 첫 전환 입회 뒤(전환 완료·워밍업 뒤)」로 고칩니다. `live-db-write-lock` 항목 때문입니다.
3. 결정 4 토큰 규칙을 「`<REPO>/services/data` 와 `<REPO>/[A-Za-z0-9_]{1,32}_latest_params_PULLBACK.json` 꼴만 허용 + 점검 계정 파일 토큰 있음」으로 넓힙니다(계정 추가 때 FAIL 방지).
4. §12-10(:1572) 「읽고 지울 수 있는지」를 「읽을 수 있는지」로 정정합니다(지우기는 엔진).
5. 결정 5 대상은 사용자 폴더의 `res-*.json` 만, 이름 정렬 첫 1개로 적습니다.
6. 사실 1 정정에 「control_requests.py:818 mkdir 은 services/data 용」을 덧붙입니다.

## PO 반영 (10/30)
- 권고 1~6: 실행 지시에 넣습니다. 결정 B 권고를 (라)로 바꿉니다.
- 남은 일이 사용자 결정뿐이라 다시 묻지 않고 사용자에게 바로 묻습니다(HANDOFF 1030-06).

## 사용자 결정 (10/30 · 1030-06 「권고대로」)
- A (가): 점검 스크립트는 배포 때 한 번, 첫 모의 전환 입회 뒤(전환 완료·워밍업 뒤) 한 번 더 돌린다. runbook :161·probe :47 의 「한 번만」을 함께 고친다.
- B (라): Step 6 로컬 흐름 실측은 `v2.control.write_request` → Controller → `v2.control.read_result` 를 실제 파일로 잇는 통합 시험 1건(게이트 포함, 업비트 호출 0)으로 갈음한다. 화면은 배포 뒤 412·360·1440 폭으로 실측한다. 계획 :1433 「로컬 Streamlit」 문구를 고친다.
