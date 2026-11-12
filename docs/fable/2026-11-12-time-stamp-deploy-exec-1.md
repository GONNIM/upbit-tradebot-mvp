# 질의: 1112-01(신버전 화면 시각 YYMMDD:HH:MM) 배포 실행 직전 — 배포 스크립트를 사용자에게 드리고 승인을 받으려 한다

**지금 단계:** 리뷰(배포 실행 전)
**다음에 하려는 일:** 사용자에게 배포 승인 요청 + 스크립트 실행 안내(`! ssh root@orionhunter7.cafe24.com 'bash -s' < <스크립트>`). 승인·실행 뒤 결과로 3점 일치 확인, 배포 보고(deploy-report-20261112-1112-01.md), 1시간 관찰, 투자자 체감 변경 통보 초안. 엔진(tradebot) 재시작 없음, `deploy-tradebot` 쓰지 않음.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 서버(11/12 16시대 사용자 실행 읽기 점검): HEAD d329171, v1.2026.11.10.1827, 추적 변경 0, tradebot·tradebot-v2 기동 11/10 19:15:21·19:15:31, NRestarts 0, 11/12 00:50 이후 주문 줄 0·ERROR 0·429 0, app.js 200, 디스크 52% | 확인 | 사용자 `!` 실행 출력(대화) |
| 2 | 서버 nginx 의 `location /v2/` 를 /etc/nginx/sites-enabled/ 에서 grep 했으나 0줄 — 설정 파일 위치가 다를 수 있음. 앞선 배포 1106-02·1106-01 은 정적 파일 변경을 tradebot-v2 재시작만으로 반영했고 사용자 화면에서 확인됨 | 확인(grep 0줄) / 추정(위치) | 점검 출력, docs/specs/v2-dashboard/deploy-report-20261106-1106-02.md |
| 3 | 배포 대상 b68ac92(origin/main, push 게이트 통과). bb15819·072260c 는 문서·시험, b68ac92 는 v2 화면·서버 코드 + 시험 + HANDOFF + dashboard.py 버전 줄. d329171..b68ac92 에서 core·engine·services 변경 0 | 확인 | `git diff --stat d329171 b68ac92 -- core engine services` |
| 4 | 엔진은 v2 를 import 하지 않음 → 엔진 재시작 불필요. 구버전 화면 버전 글자는 엔진 재시작 때 바뀜(의도된 불일치, 1106-02 와 같음) | 확인 | verifier 보고, deploy-report-20261106-1106-02.md:5 |
| 5 | 스크립트: 0단계 HEAD·추적 변경·엔진 active 확인 → 0-b v2 :443 연결 8번 확인(3번 이상이면 멈춤) → `git pull --ff-only` → HEAD b68ac92 아니면 재시작 안 함 → tradebot-v2 재시작 → index·kst_time.js 응답·app.js kstStamp·엔진 기동 시각 그대로·v2 오류 줄 | 확인 | scratchpad deploy-1112-01.sh |
| 6 | 투자자는 11/11 17:50 부터 눌림목 실계좌 운용, 보유 여부는 이번 점검에서 보지 않음. v2 재시작은 엔진 매매에 영향 없음(다른 프로세스) | 확인(프로세스 분리) / 미확인(보유) | v2-runbook, 점검 출력 |
| 7 | 되돌리기: 서버에서 직접 고치지 않음. 로컬에서 되돌림 커밋(버전 새 시각) push → 서버 pull + tradebot-v2 재시작 | 확인 | 1106-02 선례 |
| 8 | 사용자 지시: 배포는 승인 뒤. 사용자는 화면이 바뀌지 않았다고 지적해 오늘 반영을 원함 | 확인 | 대화 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 스크립트의 멈춤 조건·순서가 충분한가? 빠진 확인이 있는가? | 1106-02 와 같은 형태라 충분하다 |
| 2 | nginx 위치 미확인(사실 2)이 배포를 막아야 하는가? | 앞선 배포 선례와 no-cache 설정으로 막지 않는다. 배포 뒤 사용자 화면으로 확인한다 |
| 3 | 사용자 승인 요청으로 넘어가도 되는가? | 그렇다 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/b131ac26-0fd8-4dc4-82d2-2ffcbd7b1ed6/scratchpad/deploy-1112-01.sh
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-report-20261106-1106-02.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-12-time-stamp-impl-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/v2-runbook.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/deploy/nginx-v2-location.conf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 요지 (1회째)
**판정:** 수정 후 진행 — 막음 1: 배포 요청 전 verifier 검증 근거 없음 · 막음 2: 쿠키 없는 /v2/ 는 401(handlers.py 89~107) 기대값. 권고: 원격 머리 비교 뒤 ff 병합 · 실행 전 push 금지 · 3단계 OK/주의 비교와 14초 재확인 · nginx -T 로 /v2/ 블록 읽기 · 보유 미확인·:443 추정 근거 밝힘 · 브라우저 실측에 백테스터 저장 시각.

## 고친 것 (2회째 질의)
| # | 지적 | 고친 것 |
|---|---|---|
| 막음 1 | verifier | 배포 요청 verifier 실행 — 「승인 요청 가능」, 반박 0, 미확인 1(서버 상태 → 스크립트 0단계가 다시 확인). 지적: 구버전 화면 버전 글자 불일치 명시 · 「주의」 출력 시 되돌리기 판단 · 브라우저 실측 계획 명시 → 승인 요청 글에 반영 |
| 막음 2 | index 기대값 | 3단계 `ok … "401" "index(쿠키 없음)"` |
| 권고 3 | 원격 비교 | `git fetch origin main` → origin/main 이 b68ac92 아니면 exit 7(파일 안 바꿈) → `git merge --ff-only origin/main` |
| 권고 4 | push 금지 | 실행 전 push 하지 않음. `git ls-remote origin main` = b68ac92 확인. HANDOFF·질의 파일은 배포 뒤 커밋 |
| 권고 5 | 비교 | ok() 함수로 HEAD·버전·v2 상태(4초·14초)·NRestarts·kstStamp 2·index kst_time.js 1·엔진 기동 시각·v2 오류 0 을 OK/주의로 출력 |
| 권고 6 | nginx | 0-a `nginx -T 2>/dev/null \| grep -n -A5 'location /v2/'` |
| 권고 7·8 | 승인 요청 문구 | 보유 미확인·프로세스 분리, :443 은 추정 근거, 실측 항목(홈·로그 3종·차트 십자선·백테스터 저장 시각) 명시 |
- 스크립트 `bash -n` 통과. 기대값: `git show b68ac92:v2/static/app.js | grep -c kstStamp` = 2, index kst_time.js = 1.
- PO 규칙 위반 1회(11/12): 이 절을 `python3 -I -c "…"` 로 덧붙이다 큰따옴표 안의 백틱이 로컬 셸 명령으로 실행됨 — `git fetch origin main`(받기만) · `git merge --ff-only origin/main`(「Already up to date」, 바뀐 것 없음) · `git ls-remote` · `git show|grep` · `bash -n`(파일 없음) · `ok`·`nginx -T`(로컬에 없음, 실패). 서버 접속·push·파일 변경 없음, 무해. 표 글자는 Edit 로 바로잡음.

## Fable 답변서 요지 (2회째)
**판정:** 진행 — 막음 2건 처리 확인, 스크립트 59줄에 엔진을 건드리는 줄 없음, 파일 바꾸기 전 멈춤 조건 맞음(bash -n 통과, HEAD=origin/main=b68ac92, push 없음).
- 권고 1 질의서 빈 칸 바로잡기(Fable 이 본 뒤 이미 Edit 로 고침) · 2 「주의」 줄이 나오면 추가 실행 없이 출력 전체를 보내 달라고 안내 · 3 v2 오류 줄은 재시작 시각 뒤인지 가림 · 4 배포 보고 근거에 verifier 결과와 0-a nginx 출력.
