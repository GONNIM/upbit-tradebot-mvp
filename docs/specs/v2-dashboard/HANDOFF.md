# 인수인계 — 신버전 대시보드 · PULLBACK 전략 (4판)

- 작성: 2026-10-21 · 개정: 2026-10-22 (2판), 2026-10-22 (3판 — 결정 1~7·Q1~Q7, spec 3.1절), 2026-10-22 (4판 — 3차 결정 E15~E19, spec 3.2절, 목차 3판)
- 기준: 4판은 목차 3판·spec 3.2절과 같은 커밋에 들어간다(직전 커밋 `ee6efc4`). 서버는 `156b351`이고 `dashboard.py`는 v1.2026.10.20.1711, tradebot 기동 2026-10-20 17:40:51 KST
- 새 세션은 `git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`와 `git status --short`로 커밋 여부를 먼저 확인한다.
- 1판의 [3] 지시, 2판의 [2] 결정 대기 표, 3판의 [3]-1~4 는 **종료**했다. 4판 2절이 우선한다.

## 1. 세션 시작 방법

일반 터미널에서 실행한다. 반드시 프로젝트 폴더에서 시작한다(핸드북 규칙 1).

```
cd "/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp" && claude-thetak
```

첫 메시지로 아래 한 줄을 보낸다.

```
docs/specs/v2-dashboard/HANDOFF.md 를 읽고 그대로 시작하라.
```

## 2. 지금까지 확정된 것

### 2026-10-21
- 투자자 승인 완료: 승인 요청서 v2 PDF, 5개 항목 전부 승인, 의견 없음 (`docs/operations/investor-notice-log.md` #5, 커밋 `bfeae37`)
- spec 결정 D1~D7 (spec 3절)

### 2026-10-22 운영자 결정 (2판, spec 반영 완료)
- R4: 신버전은 별도 systemd 서비스 `tradebot-v2`.
- R7: 1차(P1·P2) 백테스터 데이터는 Binance만. 업비트 칸은 「준비 중」.
- D8: 신버전은 서버에서 업비트 API(시세·계좌)를 부르지 않는다.
- 차트는 투자자 브라우저가 업비트 공개 시세를 직접 호출(30초 갱신). 잔고·포지션은 DB 기록 + 기록 시각.
- 검증 역할 `.claude/agents/verifier.md` 신설.

### 2026-10-22 사용자 결정 (3판, spec 3.1절 E1~E14 반영 — 미커밋)
| # | 결정 |
|---|---|
| 결정 1 → E1 | 1차 배포 때 입장 버튼과 함께 `tradebot` 1회 재시작 + `journalctl -u tradebot` 봉 누락 확인 |
| 결정 2 → E2 | v2 전용 경량 DB·설정 모듈(config·streamlit·pyupbit import 없음, 키 미로드) |
| 결정 3 → E3 | 「엔진 동작」 = `audit_buy_eval` 최신 시각·`accounts.updated_at`(LIVE) 경과 시간 |
| 결정 4 → E4 | 차트 MA200 1차 제외 |
| 결정 5 → E5 | 평가손익 현재가 = 엔진 기록 가격 + 기록 시각 |
| 결정 6 | spec 옛 문구 정리·P4 엔진 제어 재설계(4.7: 신버전은 요청 기록만, 엔진 프로세스가 실행) — 완료(미커밋) |
| 결정 7 | `CLAUDE.md` 「에이전트 운용」·「축적된 규칙」 절 추가 — 완료(미커밋) |
| Q1 → E6 | 60초 1회용 서명 토큰. 「구버전으로」는 재로그인 |
| Q2 → E12 | 빈 봉 규칙 정정은 P3 spec·계획에서 |
| Q3 → E7 | 설정 파일 `{user}_latest_params_PULLBACK.json` (pullback spec 4.2 도 같이 고침) |
| Q4 → E8 | settings_history 허용 목록 확장 + 구버전 이력 화면 회귀 시험 |
| Q5 → E9 | 「저장만 하기」 TEST/LIVE 구분 없음 |
| Q6 → E10 | 1차 운용 메뉴는 **표시만**(버튼 비활성 「2차 공개 때 열림」, 상태 읽기). 사용자가 한때 「1차부터 실제 동작」을 골랐다가 「너무 복잡해진다」며 권고안으로 되돌림 |
| Q7 → E11 | tornado (서버 설치 6.5.1) |
| W2 → E13 | Binance 결과는 「저장만」 유지. P3 엔진 봉 기록은 워밍업 확정 봉도 기록하는 안으로 설계. 전환 여는 기준은 P3 계획에서 |
| 사용자 요구 → E14 | **백테스트 실행은 원본 HTML처럼 빠르게 끝나야 한다.** A6 에 실행 시간 측정 추가 (PO 해석. 사용자가 다른 뜻이라고 하면 고친다) |

### 2026-10-22 사용자 결정 (4판, spec 3.2절 E15~E19 반영)
| # | 결정 |
|---|---|
| 결정 1 (c2) → E15 | 1차 신버전 이력은 별도 파일 `services/data/v2hist_<user>.db`. 실매매 DB 는 읽기만, 구조 변경 없음. 기존 `settings_history`·허용 목록·CHECK 는 1차에서 바꾸지 않음 |
| 결정 B (a) → E15 | `v2hist` 는 별도 cron 줄로 백업(기존 `/root/cleanup_tradebot_db.sh` 무변경, 백업본 600) |
| 결정 3 → E16 | 구·신 이력은 따로 관리, 각 대시보드는 자기 이력으로 전략 추정. 화면 현재 전략 배지는 `{user}_active_strategy.txt`. **P3 선행 조건:** 엔진 PULLBACK 기동 시 이력 기록 위치(지금 코드는 `_validate` 에서 거부 → 경고만, 거래 이력 id NULL) |
| 결정 2 (a) + 결정 A (a) → E17 | 「엔진 동작」= 매수·매도 판단 기록 최신 `timestamp`(+ LIVE 잔고 기록 보조). 무거래 봉은 기록이 없으므로 임계는 1단계 실측 뒤 계획서에서. 화면은 「마지막 판단 N분 전」 + 정상·지연·판단 불가 |
| 결정 4 (a) → E18 | 신버전 root 실행 + `ProtectSystem=strict`·`ReadWritePaths=-`(`services/data/`, PULLBACK params)·`InaccessiblePaths=-`(키 파일 3개)·`NoNewPrivileges`·`UMask=0077`, 후보 `CapabilityBoundingSet=`. 남는 위험 2건(엔진 환경변수, 실DB 파일 쓰기)은 코드로 막고 A17 실측 |
| 결정 5 (a) → E19 | 백테스트 속도는 계산 시간 중앙값 +20% 이내, 데이터 받기는 요청 수·봉 수 동일 |

### 2026-10-22 보고·진행 방식 (사용자 지시)
- 이후 모든 보고는 claude-studio 규칙의 양식을 따른다: `/Users/gonnim/GON-Dev/claude-studio/agents/po.md` 「보고 양식」(결론 / 한 것·확인한 것·남은 것 / 결정해 주실 것 / 산출물), Fable 질의서·답변서는 po.md 「질의서 양식」·`fable-advisor.md` 「답변 양식」.
- Fable 질의 규칙(세션 시작 훅이 넣음)을 지킨다. 파일 쓰기·커밋·결정 요청·단계 넘김 직전마다 Fable 판정 「진행」을 받는다. 같은 단계 재질의 2회 뒤에도 「진행」이 아니면 멈추고 사용자에게 묻는다.
- Fable 호출: 프로젝트에 fable-advisor 역할이 없으므로 Agent 도구 `model: "fable"` + `fable-advisor.md` 본문을 프롬프트 앞에 붙인다. 질의·답변은 `docs/fable/YYYY-MM-DD-<단계>-<번호>.md`(po.md 23행·세션 시작 훅 규칙의 경로). po.md 22행은 fable-advisor 역할이 없으면 멈추라고 하지만, Agent `model: "fable"` 방식은 세션 시작 훅 규칙 [3]이 정한 대안이고 2026-10-22 세션에서 이 방식으로 진행했다. 프로젝트에 역할 배치는 백로그.
- 같은 지시를 `CLAUDE.md` 「축적된 규칙」에도 적었다. 메모리 저장은 사용자 허용 전이라 하지 않았다(핸드북 규칙 3).

## 3. 새 세션이 할 일

핸드북(`/Users/gonnim/Downloads/Bot/GONNIM 에이전트 운용 핸드북 · 모든 프로젝트 공통 인수인계서.md`)을 숙지한 뒤 시작한다.

### [0] 세션 시작 체크리스트 + 정지선

`.claude/context/project-rules.md`의 「세션 재개 표준 정지선」을 따른다. 결과는 표 하나로 보고한다.

- `pwd`가 git 최상위 폴더와 같은지, `CLAUDE_CONFIG_DIR`이 `~/.claude-thetak`인지.
- 로컬: HEAD 와 커밋 여부. 4판 기대값은 HEAD = `origin/main` = 이 HANDOFF 4판이 들어간 커밋(`git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`), 추적 파일 미커밋 0건. push 가 안 됐으면 HEAD 가 origin 보다 1커밋 앞선다.
- 서버(SSH 읽기 전용): HEAD `156b351`, `dashboard.py` v1.2026.10.20.1711, `tradebot` active, 기동 2026-10-20 17:40:51, `tradebot-v2` 없음, `.env`·`.streamlit/secrets.toml` 600, 사본 없음. 서버 미추적 5건(`check_all_balances.py`, `check_balance.py`, `check_pepe.py`, `sync_balances.py`, `mcmax33.sqlite3`)은 손대지 않는다.
- `verifier` 에이전트가 사용 가능한 목록에 보이는지.
- 로컬 미추적 13건은 건드리지 않는다: JTO 분석 문서 4개, `tests/test_*.py` 7개, `__pycache__` 2개.
- 기대값과 하나라도 다르면 STOP.

### [1] 읽을 파일

- `docs/specs/v2-dashboard/spec.md` — 3.1절 E1~E14, 3.2절 E15~E19 반영본
- `docs/specs/v2-dashboard/plan-outline-v3.md` — 목차 3판(plan.md 의 출발점, C1~C5 대응표)
- `docs/specs/v2-dashboard/review-20261022-outline-v3-draft.md`, `review-20261022-outline-v3-recheck.md` — 3판 검증 보고
- `docs/specs/v2-dashboard/review-20261022-outline-v2.md` — 2판 검증 보고(지적 1~16)
- `docs/specs/pullback-strategy/spec.md` — P3
- `docs/fable/2026-10-22-*.md` — 이번 결정 과정의 Fable 질의서·답변서(각 파일 끝 「Fable 답변서 전문」 절)
- `.claude/agents/verifier.md`, `/Users/gonnim/GON-Dev/claude-studio/agents/po.md`, `/Users/gonnim/GON-Dev/claude-studio/agents/fable-advisor.md`
- 필요할 때만: 원본 백테스터 `docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html`의 `simulate()`(246~383행)

### [2] 결정 대기

없음. (결정 1~7·Q1~Q7·3차 결정 1~5·A·B 확정. 목차 3판 승인과 아래 [3]의 각 단계 승인은 따로 받는다.)

### [3] 이번 세션 작업 순서

1~4. (2026-10-22 완료) 미커밋 커밋 `ee6efc4`·push, review 2판 4절 「결정 완료」, 목차 3판 작성·verifier 3회·Fable, 3차 결정 반영(spec 3.2).
5. 목차 3판 사용자 승인이 없으면 먼저 받는다.
6. 승인 후 `superpowers:writing-plans`로 `docs/specs/v2-dashboard/plan.md` 작성 → `verifier` 검증 → Fable → 보고. plan.md 에 넣을 것(목차 3판·Fable 지적에서 넘어온 것): E17 「정상·지연·판단 불가」 경계(V1 실측 뒤), 「대기 중 주문 0」 확인 테이블·로그 태그, `{user}_active_strategy.txt` 절대 경로 읽기와 수정 시각 표시, `v2hist` 백업 cron 줄, `CapabilityBoundingSet=` 실측(A17).

### [4] 금지와 주의

- 파일을 쓰기 전에 목록과 요지를 보여 준다. 기존 파일은 diff를 먼저 보여 준다.
- 커밋, push, 배포, 서버 설정 변경은 각각 따로 승인받는다.
- 여러 줄 텍스트는 파일 도구(Write·Edit)로만 쓴다. 셸 heredoc 은 빈 것도 쓰지 않는다 (2026-10-22 세션에서 3회 위반, 모두 무해. 3판 세션의 1회는 `python3 - <<'X'` 빈 본문).
- 코드를 커밋할 때는 `dashboard.py` 버전을 갱신한다. 문서만 바꾼 커밋은 버전을 그대로 둔다.
- 키 값은 대화에도 문서에도 적지 않는다.
- 확인하지 못한 것은 「미확인」으로 적는다. 검증 보고의 「반박됨」을 고치지 않은 채 사용자에게 올리지 않는다.
- 사용자 답이 템플릿 그대로이거나 두 가지로 읽히면 확정하지 않고 다시 묻는다(Q6 사례).
- Fable 판정 「진행」 전에는 파일을 쓰지 않는다. 「수정 후 진행」은 고친 뒤 다시 질의해 「진행」을 받는다 (2026-10-22 1회 위반: CLAUDE.md 1줄, 무해).

## 4. 넘겨받는 백로그

- 엔진에 업비트 429·418 처리가 없다(`core`·`engine`·`services` grep 0건, 시세 호출 지점 27곳). v2와 무관한 기존 잠재 결함
- 8501이 외부에 평문 HTTP로 열려 있다(nginx 우회 가능, ufw 비활성)
- `docs/operations/server-optimization.md:35` candle_cache 기재 정정 — 서버 DB 4개 모두 테이블 없음
- 서버 `services/data/tradebot_.db`(빈 user_id DB) 출처 조사 — `engine/boot_resume.py:54` glob 대상
- 서버 미추적 5건(`check_*.py` 3, `sync_balances.py`, `mcmax33.sqlite3`) 출처 조사 (2026-10-22 신규)
- 휴대폰 브라우저 업비트 직접 호출(1단계 V2), 승인 요청서 PDF 휴대폰 렌더 — 미확인
- 핸드북 「알려진 함정」 추가 제안 1건(2026-10-21 운영자 계정 오지정). 핸드북 원본 위치를 먼저 정해야 한다
- 프로젝트에 po·fable-advisor 역할 배치(`/project-intake`) 제안 — 승인 전 만들지 않음
- 서버 `/root/upbit-tradebot-mvp/_active_strategy.txt`(빈 사용자 이름) 출처 조사 — `tradebot_.db` 와 같은 유형 (2026-10-22 신규)
- P3 선행 조건: 엔진 PULLBACK 기동 시 이력 기록 위치(E16), 엔진 주기 기록(heartbeat) 검토(E17), 허용 목록·CHECK 확장 여부(선례 `services/init_db.py:508-545`)
- 서버 감시 스크립트 `/root/watchdog_tradebot_engine.sh` 도 journal `Bar#` 600초 기준이라 무거래 봉에 같은 약점 (2026-10-22 verifier 관찰)
- 세션 중 DB 를 여는 조회(`sqlite3 -readonly` 포함)는 서버 `-wal`·`-shm` 을 만든다. 검증 역할에는 「서버 DB 열기 금지」를 기본으로 적는다

## 5. 시작 후 확인할 점

| 시점 | 확인할 것 |
|---|---|
| 첫 보고 | 정지선 표, 미커밋 변경 목록, 보고 양식이 po.md 「보고 양식」인지 |
| 기대값이 다를 때 | STOP 하고 묻는지 |
| 파일 쓰기·결정 요청 전 | Fable 판정 「진행」을 받았는지, 질의 파일 경로를 「확인한 것」에 적는지 |
| 목차 3판 | 사용자에게 올리기 전에 `verifier` 재검증과 Fable 질의를 거치는지 |
