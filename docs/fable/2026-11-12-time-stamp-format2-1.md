# 질의: 1112-01 후속(시각 모양 YY.MM.DD HH:MM · 같은 날 묶음 끝 HH:MM) 구현·시험·412px 실측·verifier 를 마쳤고, 커밋·push·배포 승인을 한 번에 요청하려 한다

**지금 단계:** 리뷰
**다음에 하려는 일:** 사용자에게 커밋·push·배포 승인을 함께 요청. 승인 뒤: `pages/dashboard.py` 버전 갱신 → 스테이징 확인 → 비밀값 검사 → `git commit -F` → `git push`(게이트) → 배포 스크립트(앞서 Fable 진행을 받은 deploy-1112-01.sh 와 같은 구조, EXPECT_OLD=b68ac92 · EXPECT_NEW=새 커밋 · EXPECT_VER=새 버전 · 3단계 기대값 그대로: index 401 · kst_time.js 200 · app.js kstStamp 2 · index kst_time.js 1 · 엔진 기동 시각 그대로 · v2 오류 0)을 새 해시로 만들어 사용자 `!` 실행. 이 커밋에 문서(배포 보고 deploy-report-20261112-1112-01.md · HANDOFF · Fable 질의 2개)도 묶는다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | b68ac92(YYMMDD:HH:MM)는 11/12 17:01:56 배포 끝, 확인 9개 OK. 사용자 「화면 확인함 — 그런데 굉장히 눈에 익지 않다」 → 제안 → 「㉠ ㉡ 권고대로」(㉠ 26.11.12 15:18, ㉡ 같은 날 묶음 끝 HH:MM) | 확인 | 대화, deploy-report-20261112-1112-01.md |
| 2 | 모양을 만드는 곳: kst_time.js kstStamp · save.js 사본 · db.kst_stamp `"%y.%m.%d %H:%M"`. api_read `_span`(같은 KST 날이면 끝 HH:MM, None·날 넘김은 전체), 묶음 글 두 곳이 사용 | 확인 | verifier 주장 1·2 |
| 3 | api_read.py:1102 status_log_text(YYYY-MM-DD HH:MM:SS)는 v2 화면에서 쓰지 않고 구버전 같은 글자 시험에 묶여 그대로(이미 승인된 제외 「구버전」) | 확인 | verifier 지적 1, 이전 질의 time-stamp-impl-1 |
| 4 | 로그 시각 칸 7.4em → 8.2em. 412px 로컬 실측: 시각 칸 29px 한 줄, 묶음 글 「(6회, 26.11.12 16:51~17:06)」 한 줄, 홈 새 모양 | 확인(PO 실측) / 미확인(verifier 재측정 못 함) | chrome-devtools 캡처 |
| 5 | 게이트(17:07:51 시작, 마지막 코드 수정 17:07:38 뒤): v2 Py 466 OK · JS 206/206 · 회귀 1472/1472 · 바깥 연결 0. verifier 가 Py 109·JS 206 다시 돌림 | 확인 | scratchpad gate-1112c.log, verifier 주장 4 |
| 6 | `_old_time_shape` 정규식 `\b\d\d\.\d\d\.\d\d (\d\d:\d\d)\b` 로 같은 날·날 넘김 범위 모두 기준 커밋 모양으로 되돌리고 나머지는 그대로 비교 | 확인 | verifier 주장 3 |
| 7 | 엔진·pages·backtester 무변경 → tradebot-v2 재시작만 | 확인 | verifier 주장 6 |
| 8 | 18:02 이후 1시간 관찰(b68ac92)은 아직 사용자 실행 전 | 확인 | 대화 |
| 9 | 투자자 통보는 최종 모양 배포 뒤 한 번만 보낸다(이전 보고에서 사용자에게 밝힘). 투자자가 「261112:15:18」 모양을 꼭 원했는지는 모름 | 확인 / 추정 | 직전 보고 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 구현이 ㉠ ㉡ 과 맞고 빠진 곳이 없는가? | 맞다 |
| 2 | 커밋·push·배포 승인을 한 번에 요청해도 되는가(사용자가 빠른 반영을 원함)? 배포 스크립트는 앞서 진행 판정을 받은 구조에 해시·버전만 바뀐다 | 된다. 배포 직전 Fable 질의는 이 질의로 갈음하고, 스크립트 원문을 질의 뒤에 붙여 확인받는다 |
| 3 | b68ac92 1시간 관찰이 끝나기 전에 다시 배포해도 되는가? | 된다. 같은 화면 서비스 재시작이고 엔진 무관. 새 배포 뒤 1시간 관찰로 갈음 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/kst_time.js, save.js, style.css, v2/db.py, v2/api_read.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/v2/test_api_read.py(TestSpan), tests/v2/test_api_read_pullback.py
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/b131ac26-0fd8-4dc4-82d2-2ffcbd7b1ed6/scratchpad/gate-1112c.log
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/b131ac26-0fd8-4dc4-82d2-2ffcbd7b1ed6/scratchpad/deploy-1112-01.sh (앞 배포 스크립트 — 해시·버전만 바꿀 예정)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-12-time-stamp-deploy-exec-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 요지 (1회째)
**판정:** 수정 후 진행 — 구현·시험은 ㉠ ㉡ 과 맞음(17:14 재실행 Py 466 OK · JS 206/206, 옛 모양 grep 은 설명 글 1줄·백테스터 마커뿐). 막음 1: 배포 승인 요청 전 verifier 배포 요청 검증 근거 필요.
- 질문 2: 커밋·push 와 배포를 나눠 답받을 것, 배포는 push 게이트·새 스크립트 bash -n 통과 뒤. 질문 3: 관찰 중 재배포 가능, 0단계에서 17:01:56 이후 v2 오류 줄을 읽어 앞 배포 관찰을 숫자로 닫을 것.
- 권고: 새 모양 확인 2줄(서버 kst_time.js 의 YY.MM.DD 줄 1 · style.css 8.2em 1) · 관찰 스크립트 기준 시각 바꿈 · HANDOFF 1112-01 행 지금 상태로 · 투자자 예시와 다른 모양이 된다는 줄 · 실행 전 추가 push 금지·「주의」 안내 · 배포 보고 버전 구→신·3점 일치.
- PO 처리: 이번 보고는 커밋·push 승인만 요청(배포 승인과 나눔). 커밋 뒤 새 해시로 스크립트를 만들고 verifier 배포 요청 검증 → 이 질의 2회째(배포 실행 전) → 배포 승인 요청. HANDOFF 행은 고침.
