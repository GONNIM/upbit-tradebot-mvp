# 질의: Task 5 를 push(194a134) 했고, Task 6 착수 전 사용자 결정 1023-01(3건)과 PO 판정 1건을 올리려 합니다

**지금 단계:** 계획 (Task 6 착수 전 결정 요청)
**다음에 하려는 일:** 아래 결정 3건(선택지·PO 권고)과 PO 판정 1건을 사용자에게 올립니다. 이 질의서만 저장하고 다른 파일 쓰기·커밋은 없습니다. 사용자 답을 받으면 progress.md 에 적고 Task 6 착수 질의서에 넣습니다. 사실·실현 가능성·위험만 확인합니다.

## PO 판정 (사용자에게는 알림만)
- 홈에서 백테스터로 가는 길(사전 점검 X10): spec 이 백테스터를 「메뉴」로 정했으므로(spec 11·20·124행) Task 6 하단 메뉴에 「백테스터」 항목을 넣어 `backtester.html`(Task 7)로 연결합니다. Task 6 시점에는 파일이 없어 링크만 둡니다.

## 결정 1: 로컬에서 화면을 직접 확인하는 방법 (사전 점검 X11)
plan Task 6 Step 6(412px 실측)·Task 8 Step 5(확인 창 실측)·Task 10(통합)은 로컬 서버로 화면을 띄워야 하는데, 지금 서버는 (1) 쓰기 요청 출처를 운영 주소 `https://orionhunter7.cafe24.com` 로만 허용하고 (2) 세션 쿠키가 `Secure` 이며 (3) 시험 DB·서명 키·허용 목록 경로를 정하는 방법이 없고 (4) 로컬엔 nginx 가 없어 구버전(8501)의 `/v2/?t=` 링크가 8502 에 닿지 않습니다.
| 안 | 내용 | 영향 |
|---|---|---|
| 가 (PO 권고) | 개발용 실행 스크립트 `scripts/v2/dev_server.py` 를 둔다. 임시 폴더에 가짜 실매매 DB(시험 픽스처 DDL + 예시 행)·서명 키·허용 목록을 만들고, 그 폴더를 저장소 루트로 바꿔 `make_app(allowed_origin="http://127.0.0.1:8502")` 로 띄우며, 입장 URL(`http://127.0.0.1:8502/v2/?t=…`)을 찍는다. `Secure` 쿠키는 브라우저가 localhost 에서 받아 주는지 실측, 안 되면 개발 스크립트에서만 끈다. 서비스 유닛·배포에는 포함하지 않는다 | 실매매 DB·운영 파일을 건드리지 않음. 서버 코드(v2/*) 변경 없음 또는 make_app 인자 1개 추가 수준 |
| 나 | 로컬 화면 확인을 하지 않고 배포 뒤 서버에서 확인 | plan 의 412px·확인 창 실측이 배포 뒤로 밀림. 문제가 배포 뒤에 발견됨 |

## 결정 2: 홈 「최신 신호」에 무엇을 보일지
지금 `GET /v2/api/signals` 는 매수 판단 기록(`audit_buy_eval`)만 돌려준다. 엔진은 미보유 때 매수 판단만, 보유 중엔 매도 판단(`audit_sell_eval`)만 기록한다(spec E17 근거 줄 `core/strategy_engine.py:1881·1945·1986`, `:2111·2192`).
| 안 | 내용 | 화면에서 일어나는 일 |
|---|---|---|
| 가 | 매수 판단만(현재) | 보유 중에는 목록이 멈춤(마지막이 매수 직전 기록). TP/SL·데드크로스 발동 같은 매도 신호는 안 보임 |
| 나 (PO 권고) | 매수 판단 + 매도 판단을 시각순으로 합쳐 보임(종류 표시, 매도는 발동 여부·발동 사유 `trigger_key`) | 보유 중에도 최신 판단이 보이고, 매도 발동이 보임. API 응답에 `kind` 키 추가, SQL 2개(각각 인덱스·LIMIT)로 받아 합침 |
| 다 | 최신 1건만 상태로(「매수 대기」/「보유 중 · TP/SL 판단」) | 목록 없이 상태 한 줄. spec 「최신 신호」 단수 표현과 가장 가까움 |

## 결정 3: 긴 봉(10분 이상)에서 「지연」 단계
결정 1022-06(안 다) 기준값: 지연 = 봉 초 × 3 초과, 판단 불가 = 1800초 초과. 10분봉부터 봉 초 × 3 ≥ 1800 이라 「지연」 구간이 없어짐(15분봉: 45분까지 정상 → 바로 판단 불가). 구버전 사이드바에서 1·3·5·10·15분봉을 고를 수 있음(`ui/sidebar.py:13-17`). 지금 운영은 3분봉.
| 안 | 내용 | 영향 |
|---|---|---|
| 가 | 그대로 | 10·15분봉에서 정상 → 판단 불가로 바로 넘어감 |
| 나 (PO 권고) | 판단 불가 기준 = max(1800초, 봉 초 × 3 × 2) | 3분봉·5분봉은 지금과 같음(1800초). 10분봉 지연 30~60분·판단 불가 60분 초과, 15분봉 지연 45~90분·판단 불가 90분 초과. `v2/status.py` 상수 계산 한 곳 + 시험 |

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | Task 5 push 완료, HEAD = origin/main = 194a134 | `git rev-parse` |
| 2 | 서버 Origin 기본값·쿠키 Secure | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/server.py, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/handlers.py |
| 3 | signals SQL 은 audit_buy_eval 만 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/api_read.py 37~42행 |
| 4 | audit_sell_eval 에 triggered·trigger_key 열 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/services/init_db.py 343~366행 |
| 5 | 상태 판정 상수·규칙 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/status.py |
| 6 | spec 백테스터 메뉴 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md 11·20·120~124행 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 결정 1 안 가가 실매매·운영 파일에 닿지 않고 구현 가능한가(쿠키 Secure·Origin 처리 포함) | 예 |
| 2 | 결정 2 안 나가 Task 4 SQL 규칙(인덱스·LIMIT·「WHERE ticker ORDER BY id」 금지)과 맞게 구현 가능한가 | 예(ticker 조건 + timestamp 정렬 2개) |
| 3 | 결정 3 안 나가 결정 1022-06 과 충돌하지 않는가 | 충돌 없음(결합 규칙 그대로, 긴 봉 기준값만) |
| 4 | X10 을 PO 판정으로 처리해도 되는가 | 예(spec 이 정함) |
| 5 | 사용자에게 올려도 되는가 | 예 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/sdd/plan/preflight.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/sdd/plan/progress.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/api_read.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/status.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/server.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/handlers.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/ui/sidebar.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: Task 5 를 push(194a134) 했고, Task 6 착수 전 사용자 결정 1023-01(3건)과 PO 판정 1건을 올리려 합니다

**판정:** 진행
**이유:** 질의서의 사실 6건과 세 결정의 「영향」은 모두 코드와 맞습니다. 고칠 것은 전부 권고입니다.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 결정 1 안 가 | 가능. 경로는 모듈 전역(호출 때 읽음), make_app(allowed_origin) 인자 이미 있음, Origin 검사는 쓰기 요청만. Secure 는 handlers.py 고정값이라 끄려면 설정값 1개 추가. Chrome·Firefox 는 http://localhost 에서 Secure 쿠키를 받고 Safari 는 안 받음(127.0.0.1 미확인). 8501→8502 링크 문제는 풀지 못함 | 코드 높음 / 브라우저 보통 |
| 2 | 결정 2 안 나 | 가능. sell_eval ticker_ts 인덱스 있음, 엔진이 미보유 때 매수·보유 때 매도 판단만 기록함 확인(core/strategy_engine.py:1842·2004). 기존 시험 기대값 수정 필요 | 높음 |
| 3 | 결정 3 안 나 | 1022-06 과 충돌 없음. `UNKNOWN_SEC == 1800` 시험 수정 따름. 사이드바는 30·60분봉·일봉도 있음 | 높음 |
| 4 | X10 PO 판정 | 예(spec 124행). Task 6 시점 404 링크임을 보고에 | 높음 |
| 5 | 올림 | 예 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | 결정 1 안 가가 덮는 범위(Task 6 Step 6·Task 8 Step 5), 버튼→입장 흐름(Task 10 Step 2)은 로컬에서 못 봄 → 배포 뒤 서버 확인 (반영) |
| 2 | 권고 | 결정 3 표에 30·60분봉·일봉 (반영) |
| 3 | 권고 | Secure 끄기는 개발 스크립트 전용, 기본 True 유지, 첫 시도 localhost (반영) |
| 4 | 권고 | 임시 폴더에 active_strategy·params 파일도 (반영) |
| 5 | 권고 | 결정 2 안 나는 기존 시험 수정·kind 키 추가 포함 (반영) |

## 사용자에게 물어야 할 것
- 없음
