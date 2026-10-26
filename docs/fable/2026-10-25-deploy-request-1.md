# 질의: 신버전 대시보드 1차 공개 배포 승인 요청서를 verifier 2회로 다듬었고, 사용자에게 배포 승인을 요청하려 합니다

**지금 단계:** 리뷰 (배포 승인 요청 전 — 되돌리기 어려운 일 직전 질의)
**다음에 하려는 일:** 사용자에게 `docs/specs/v2-dashboard/deploy-request-20261025.md` 의 D1~D8 실행 승인과 결정 4건(실행 방식·시각·A15 관찰 기간·통보 문안 A 발송)을 요청합니다. 승인을 받아도 실행은 **저장소 폴더 새 세션**에서 하기를 권하고, 사용자가 이 세션에서 하라고 하면 순서대로 실행합니다. 이 질의서와 요청서는 배포 완료 보고 커밋에 함께 넣습니다(문서 묶음 고지).

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | 서버 현재 상태가 2-0 기대값과 모두 같음: HEAD 156b351, v1.2026.10.20.1711, ExecMainStartTimestamp 10-20 17:40:51, tradebot-v2·.v2_*·PULLBACK 없음, 미추적 5, 백업 10-25 11:00 | verifier 1차(SSH 읽기 전용) |
| 2 | 배포 diff 156b351..5d4be71: 137 files, 허용 목록 밖 0, core/engine/services/config.py 0 | verifier 1차 판정 8·9 |
| 3 | pull 뒤 재시작 전까지 구버전은 옛 바이트코드로 돌고(파일 감시 꺼짐) 새 import 가 섞이지 않음 | verifier 판정 11 (Streamlit 1.46 script_cache) |
| 4 | D3 조건 문자열이 코드·서버 journal 과 일치, `deploy-tradebot`(/root/deploy.sh)은 pull 직후 무조건 재시작이라 쓰지 않음 | verifier 판정 16·35 |
| 5 | verifier 1차 「수정 후 승인」(지적 16) → 전면 수정 → 2차 「수정 후 승인」(N1 상대 경로, N2 EXPLAIN 8번째) → 반영: 경로 규칙 절·허용 목록과 되돌리기 1단계 절대 경로·`/root/.v2_allowlist` 미생성 확인·SIGNALS_SELL_TICKER 추가. verifier 는 「N1 만 필수, 경로 표기만 보면 됨」 | 요청서 2절 머리·2-7·2-10, progress.md |
| 6 | 버튼 노출은 D7(nginx GET 401 확인 뒤)부터 — 허용 목록 파일은 호출마다 읽어 재시작 불필요 | utils/v2_entry_token.py:100-112 |
| 7 | nginx 편집 스크립트 초안(저장소 밖): /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/a708d392-1e41-496d-8cdc-5ce25f6bb4d1/scratchpad/deploy/nginx_add_v2.py — sites-available 제자리 쓰기, 443 블록 안 앵커가 하나일 때만 6줄 삽입, 이미 있으면 SKIP. 로컬 표본으로 2회 실행(OK → SKIP) 확인 | 이 질의서 |
| 8 | 통보 문안 A 에 spec 필수 문장 그대로, 두 단계 입장 흐름 반영 | 요청서 3절, spec.md:211 |
| 9 | 남는 위험(알려진 틈): /proc environ RESIDUAL 가능, /etc/shadow 읽기 가능, nginx access.log 토큰(60초·1회용, v2 재시작 시 nonce 저장소 초기화) | 요청서 4절 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 요청서의 순서·멈춤 조건·되돌리기가 실매매(tradebot) 안전을 지키고 빠진 단계가 없는가 | 지킴 |
| 2 | verifier 2차 N1 반영(경로 규칙 + 위험 경로 절대화)이 충분한가, 아니면 모든 명령을 절대 경로로 바꿔야 하는가 | 충분(규칙 + 위험 경로 절대화 + 오위치 확인) |
| 3 | 사용자에게 올릴 결정 4건(실행 방식 한 번에/단계별, 시각, A15 기간, 통보 시점)이 맞고 빠진 결정이 없는가 | 맞음 |
| 4 | nginx 편집 스크립트를 이 질의로 함께 봐도 되는가(실행 직전 verifier 가 다시 봄) | 됨 |
| 5 | 사용자에게 배포 승인을 요청해도 되는가 | 예 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/impl-report-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan.md (배포 절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md (E1, E18, A2~A17, 211행)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/v2-runbook.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/deploy/
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit.sh
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/a708d392-1e41-496d-8cdc-5ce25f6bb4d1/scratchpad/deploy/nginx_add_v2.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/sdd/plan/progress.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1

**판정:** 수정 후 진행
**이유:** 순서·멈춤 조건·되돌리기는 엔진 안전을 지키고 로그 문자열·DB 컬럼·코드 줄이 일치함. 다만 D3 재시작 시각 규칙이 「서버 봉 간격 = 3분」 전제인데 2-0 에 확인이 없음(투자자가 봉 간격을 바꾼 전례).

| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 막음 | 2-0 에 서버 interval minute3 확인, 2-3 「3분봉이고」→「2-0 간격 기준」 |
| 2 | 권고 | 미추적 목록에 질의서 |
| 3 | 권고 | nginx 사전 확인(listen 443, 앵커 1) |
| 4 | 권고 | 8502 미사용·backups 폴더 확인 |
| 5 | 권고 | 4절 「ro」를 코드 수준 ro·파일 수준 쓰기 가능으로 |

사용자에게 물어야 할 것: 없음

---

# 재질의 (답변 1 반영, 이 단계 마지막)

| # | 반영 |
|---|---|
| 1 | 막음 1: 2-0 에 interval·[CLOCK] 확인(10-25 PO 서버 읽기 전용: params minute3, 10-20 17:41 [CLOCK] timeframe=minute3), 2-3 문구 고침 |
| 2 | 권고 2~5 반영: 미추적 목록, nginx·8502·backups 사전 확인(10-25 확인: 1·1·0·있음), 4절 표현 |
| 3 | **확인 중 배포 전 결함 발견·수정**: 서버 params ticker "JTO"(접두 없음) — v2 가 원값을 써서 홈 조회 빔·차트 실패·저장 409 가 될 상태. normalize_ticker 로 고친 12ddb4f(verifier 승인, Fable ticker-fix-1 진행, 사용자 커밋·push 승인 1025-08·09). 배포 대상 HEAD 를 12ddb4f(v1.2026.10.25.1611, 190 OK, 138 files)로 바꾸고 「배포 전 결함 수정」 절·운영자 확인(KRW-JTO·판단 불가 아님·차트) 추가 |
| 4 | verifier 3차 「승인 가능」: HEAD·버전·파일 수·시험 수·허용 목록·엔진 변경 0 확인, E1(EXPLAIN 자리표 KRW-JTO)·E2(explain8) 반영 |

물어볼 것: 막음 1 이 해소됐고, 새 배포 대상 12ddb4f 로 사용자에게 배포 승인을 요청해도 되는가

---

# 답변 2

**판정:** 진행
**이유:** 막음 1 반영 확인. 12ddb4f 가 HEAD·origin/main 과 같고 엔진 경로 변경 0·허용 목록 밖 0·138 파일·버전 1611 이 기재와 일치, normalize_ticker 가 엔진 규칙과 같음. 남은 지적은 권고뿐.

| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | 190 OK 출처(12ddb4f 게이트)와 impl-report 187(5d4be71) 구분 |
| 2 | 권고 | orders 조회 오류를 0 으로 읽지 말고 멈춤 |
| 3 | 권고 | listen 443 원문 줄이 주석 아닌지 확인 |
| 4 | 권고 | 결정 5 실행 세션 추가 |
| 5 | 권고 | D5 는 D3 5분 확인 뒤에만 |

사용자에게 물어야 할 것: 없음

## PO 반영 (10/25)
- 권고 1~5 요청서에 반영. 사용자에게 배포 승인 요청(1025-10).
