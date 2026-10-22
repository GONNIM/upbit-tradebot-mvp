# 인수인계 — 신버전 대시보드 · PULLBACK 전략 (2판)

- 작성: 2026-10-21 · 개정: 2026-10-22 (2판)
- 기준 커밋: 로컬과 origin 모두 `bfeae37`(투자자 승인 기록). 서버는 `156b351`이고 `dashboard.py`는 v1.2026.10.20.1711, tradebot 기동 2026-10-20 17:40:51 KST
- 이 문서를 커밋하면 로컬 HEAD는 그 커밋으로 바뀐다. 새 세션은 `git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`로 확인한다.
- 1판(2026-10-21)의 [3] 지시(같은 프로세스 방식 A, `TRADEBOT_V2`, `fill_gaps_sync`, CORS·candle_cache 검증)는 **폐기**했다. 2026-10-22 결정(2절)이 우선한다.

## 1. 세션 시작 방법

일반 터미널에서 실행한다. 반드시 프로젝트 폴더에서 시작한다(핸드북 규칙 1).

```
cd "/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp" && claude-thetak
```

첫 메시지로 아래 한 줄을 보낸다. `[ ]` 는 그 시점의 사실로 바꾼다. 결정을 아직 안 했으면 「미정」으로 둔다.

```
docs/specs/v2-dashboard/HANDOFF.md 를 읽고 그대로 시작하라. 결정 대기 1~7 = [예: 전부 권고대로 / 항목별 내용 / 미정].
```

## 2. 지금까지 확정된 것

### 2026-10-21
- 투자자 승인 완료: 승인 요청서 v2 PDF, 5개 항목 전부 승인, 의견 없음 (`docs/operations/investor-notice-log.md` #5, 커밋 `bfeae37`)
- spec 결정 D1~D7 (spec 3절)

### 2026-10-22 운영자 결정 (spec 반영 완료)
- **R4 변경:** 신버전은 별도 systemd 서비스 `tradebot-v2`. 엔진(`tradebot`)과 시작·정지·재시작이 묶이지 않는다.
- **R7 변경:** 1차(P1·P2) 백테스터 데이터는 Binance만. 업비트 칸은 「준비 중」. Upbit 출처는 P3에서 엔진이 기록한 확정 봉으로 연다. 2차 공개는 그 뒤.
- **D8 신설:** 신버전은 서버에서 업비트 API(시세·계좌)를 부르지 않는다. 근거: 업비트 시세 한도는 IP 단위 공유, 429 누적 → IP 단위 418 차단(공식 문서 rate-limits). 서버 신버전 호출이 엔진의 확정 봉 조회를 막을 수 있다.
- **차트:** 투자자 브라우저가 업비트 공개 시세를 직접 호출(투자자 IP). 브라우저 요청은 10초당 1회 제한 → 30초 갱신.
- **잔고·포지션:** DB 기록 + 기록 시각 표시.
- **투자자 통보:** 1차 공개 통보 문안 A에 「업비트 데이터 준비 중」을 넣는다. 재승인 없음.
- **검증 역할:** `.claude/agents/verifier.md` 신설(영향 범위 분석 단계 포함). `.gitignore` 에 `!.claude/agents/` 추가.
- **백로그 추가:** 엔진 429·418 처리 없음(4절).

## 3. 새 세션이 할 일

핸드북(`/Users/gonnim/Downloads/Bot/GONNIM 에이전트 운용 핸드북 · 모든 프로젝트 공통 인수인계서.md`)을 숙지한 뒤 시작한다.
- 보고는 4단 형식: 결과 보고 / 백로그 / 전달용 프롬프트 / 다음 우선순위.
- 결정이 필요한 지점에서는 STOP하고 묻는다.

### [0] 세션 시작 체크리스트 + 정지선

`.claude/context/project-rules.md`의 「세션 재개 표준 정지선」을 따른다. 결과는 표 하나로 보고한다.

- `pwd`가 git 최상위 폴더와 같은지, `CLAUDE_CONFIG_DIR`이 `~/.claude-thetak`인지.
- 로컬: HEAD = 이 HANDOFF 커밋, 바로 앞 커밋 `bfeae37`. `main` = `origin/main`.
- 서버(SSH 읽기 전용): HEAD `156b351`, `dashboard.py` v1.2026.10.20.1711, `tradebot` active, 기동 2026-10-20 17:40:51, `.env`·`.streamlit/secrets.toml` 600.
- `git diff --stat 156b351 HEAD` 가 문서·`.gitignore`·`.claude/agents/` 뿐인지.
- `verifier` 에이전트가 사용 가능한 에이전트 목록에 보이는지.
- 미추적 파일 13건은 건드리지 않는다: JTO 분석 문서 4개, `tests/test_*.py` 7개, `__pycache__` 2개.
- 기대값과 하나라도 다르면 STOP.

### [1] 읽을 파일

- `docs/specs/v2-dashboard/spec.md` — 2026-10-22 개정본(R4·R7·D8)
- `docs/specs/v2-dashboard/review-20261022-outline-v2.md` — **최신 검증 보고**(반박 3건, 지적 16건, 영향 범위 표, 결정 대기 7건)
- `docs/specs/v2-dashboard/plan-outline-v2.md` — 검증받은 목차 2판(3판의 출발점)
- `docs/specs/pullback-strategy/spec.md` — P3 엔진 전략
- `.claude/agents/verifier.md`
- 필요할 때만: 원본 백테스터 `docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html` 의 `simulate()`(246~383행)

### [2] 결정 대기 — 사용자 답을 받은 뒤 진행

검증 보고 4절의 7건:

| # | 결정 | 권고 |
|---|---|---|
| 1 | 1차 배포의 엔진 재시작(입장 버튼은 `app.py` → `fileWatcherType="none"` 이라 재시작해야 반영) | 버튼과 함께 1회 재시작 + 봉 누락 확인 절차 |
| 2 | v2 DB·설정 접근 | config·streamlit·키 없는 v2 전용 경량 모듈 |
| 3 | 「엔진 동작」 표시 출처 | `audit_buy_eval` 최신 시각·`accounts.updated_at` 경과 시간 (engine_status 는 기동 시각에 멈춰 있음) |
| 4 | 차트 MA200 | 1차 제외 |
| 5 | 평가손익 현재가 | 엔진 기록 가격 + 기록 시각 |
| 6 | spec 옛 문구 정리·P4 엔진 제어 재설계 명시 | plan 작성 전 |
| 7 | CLAUDE.md 「에이전트 운용」 절 | 적용 (diff 는 5절) |

목차 2판 C절의 미결 권고 Q1~Q7(1회용 서명 토큰, 빈 봉 규칙 정정은 P3, 파일 이름 `{user}_latest_params_PULLBACK.json`, settings_history 화이트리스트 확장, P2 TEST/LIVE 구분 없음, 1차 운용 메뉴 숨김, tornado)도 함께 확정받는다.

### [3] 이번 세션 작업 순서

1. 결정 반영: spec 정리(검증 지적 14 — §2, §4.2, §4.5 파일 이름, §4.6·§4.7·A11 별도 프로세스 기준, §4.4 「엔진에 봉 기록 기능 신설」, §4.3 MA200·평가손익, A2 범위, A4 「구버전으로」 재로그인). 기존 파일이므로 diff 를 먼저 보이고 승인받는다.
2. 목차 3판 작성: 검증 지적 1~16 을 모두 반영(실행 계정·서명 키 비밀 파일, DB ro URI·쓰기 1문장·파일 생성 금지, A14 를 import 그래프·`sys.modules`·환경변수 시험으로, 유닛 MemoryMax·OOMScoreAdjust, 배포 diff 범위 확인, 규칙 항목 명시).
3. `verifier` 로 목차 3판 재검증 → 반박·누락이 남으면 고치고 다시 검증 → 사용자에게 목차 승인 요청.
4. 승인 후 `superpowers:writing-plans` 로 `docs/specs/v2-dashboard/plan.md` 작성 → `verifier` 검증 → 보고.

### [4] 금지와 주의

- 파일을 쓰기 전에 목록과 요지를 보여 준다. 기존 파일은 diff를 먼저 보여 준다.
- 커밋, push, 배포, 서버 설정 변경은 각각 따로 승인받는다.
- 여러 줄 텍스트는 파일 도구(Write·Edit)로만 쓴다. 셸 heredoc 은 빈 것도 쓰지 않는다 (2026-10-22 세션에서 2회 위반, 모두 무해).
- 코드를 커밋할 때는 `dashboard.py` 버전을 갱신한다. 문서만 바꾼 커밋은 버전을 그대로 둔다.
- 키 값은 대화에도 문서에도 적지 않는다.
- 확인하지 못한 것은 「미확인」으로 적는다. 검증 보고의 「반박됨」을 고치지 않은 채 사용자에게 올리지 않는다.

## 4. 넘겨받는 백로그

- 엔진에 업비트 429·418 처리가 없다(`core`·`engine`·`services` grep 0건, 시세 호출 지점 27곳). 차단 시 엔진이 확정 봉을 못 받아 손절·익절 판정이 멈출 수 있다. 차단 시 동작 시험과 처리 방안을 별도 작업으로. v2와 무관한 기존 잠재 결함
- 8501이 외부에 평문 HTTP로 열려 있다(nginx 우회 가능, ufw 비활성)
- `docs/operations/server-optimization.md:35` candle_cache 기재 정정 — 서버 DB 4개 모두 테이블 없음
- 서버 `services/data/tradebot_.db`(빈 user_id DB) 출처 조사 — `get_db` 가 없는 user_id 로 파일을 만든 흔적. `engine/boot_resume.py:54` glob 대상
- 휴대폰 브라우저 업비트 직접 호출(1단계 V2), 승인 요청서 PDF 휴대폰 렌더 — 미확인
- 핸드북 「알려진 함정」 추가 제안 1건: 「2026-10-21 · 운영자 계정이라고 지정한 ID가 투자자 계정이었음 · 계정을 지정받으면 설정 이력·통보 기록과 대조해 실제 사용자를 확인한다」. 핸드북 원본 위치를 먼저 정해야 한다
- ~~승인 요청서 발송 기록과 투자자 회신 반영~~ 2026-10-21 완료(`bfeae37`)

## 5. 적용 대기 diff — CLAUDE.md 「에이전트 운용」 (결정 7)

`CLAUDE.md` 끝의 `**마지막 업데이트**` 바로 앞 `---` 다음에 넣는다.

```diff
+## 에이전트 운용
+
+되돌리기 어려운 동작(커밋·push·배포·서버 설정 변경·외부 발송)은 사용자 승인 후에 실행합니다.
+
+| 이런 일 | 맡는 역할 | 완료 확인 |
+|---|---|---|
+| 계획·설계·구현 보고·배포 요청의 주장 검증 | verifier (`.claude/agents/verifier.md`, opus, 읽기 전용) | 주장별 판정표(확인됨/반박됨/미확인) · 실매매 영향 범위 축별 표 · spec·규칙 대응표 |
+
+- 실행 시점: 계획 목차 승인 요청 전, 구현 완료 보고 전, 배포 승인 요청 전.
+- 검증 결과의 「반박됨」·「누락」은 고친 뒤 다시 검증받고 나서 사용자에게 올립니다.
+
+## 축적된 규칙
+<!-- 작업을 마칠 때마다 1~3줄 추가합니다. 형식: - (YYYY-MM-DD) 규칙 — 이유 -->
+
+---
```

## 6. 시작 후 확인할 점

| 시점 | 확인할 것 |
|---|---|
| 첫 보고 | 로컬 HEAD 가 이 HANDOFF 커밋(바로 앞 `bfeae37`), 서버 `156b351`·v1.2026.10.20.1711 |
| 기대값이 다를 때 | STOP 하고 묻는지. 그 사이 누군가 배포했을 수 있다 |
| 결정 대기 | 7건 답 없이 spec·목차를 고치지 않는지 |
| 목차 3판 | 사용자에게 올리기 전에 `verifier` 재검증을 거치는지 |
