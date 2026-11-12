# 질의: 1112-01 신버전 화면 시각을 YYMMDD:HH:MM 으로 바꾸는 구현·시험·412px 실측·verifier 를 마쳤고, 사용자에게 커밋·push 승인을 요청하려 한다

**지금 단계:** 리뷰
**다음에 하려는 일:** 사용자에게 구현 완료 보고 + 커밋·push 승인 요청. 승인 뒤: `pages/dashboard.py` 버전 갱신(런타임 소스 변경) → 스테이징 확인 → 비밀값 검사 → `git commit -F <파일>` → `git push`(pre-push 게이트). 배포(tradebot-v2 만 재시작)는 그 뒤 따로 승인 요청. 작은 문서 변경(HANDOFF 1111-01 연기 기록·1112-01 행·1109-01 점검 결과)은 이 커밋에 묶는다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 지시(11/12): 「시각 나오는 부분은 모두 수정 — 홈, 로그(감사로그·엔진·오류), 이외 시각이 표시되는 부분 모두」, 투자자 요청 모양 「261112:15:18」 | 확인 | 대화 원문, HANDOFF 1112-01 |
| 2 | PO 가 정한 제외 7가지(상대 시간·운용 시간대 입력·차트 눈금·백테스터·구버전·텔레그램·CSV/API ISO)는 사용자에게 보고했고, 사용자는 아직 「그대로」라고 답하지 않았다 | 확인 | 직전 보고 「범위 밖으로 둔 것」 |
| 3 | 초를 넣지 않음(홈 기록 시각이 초를 잃음), 「어제」 없어짐, 로그 시각 열 3.6em→7.4em | 확인 | git diff app.js·style.css |
| 4 | 공용 함수: 화면 v2/static/kst_time.js kstStamp(새 파일), 서버 v2/db.py kst_stamp. save.js 에 같은 함수 사본(백테스터 html 이 kst_time.js 를 읽지 않음) — 시험이 두 본문 글자가 같은지 비교 | 확인 | verifier 주장 4 |
| 5 | api_read.py 1094 status_log_text 는 v2 화면에 안 그려지고 구버전 같은 글자 시험에 묶여 그대로 둠 | 확인 | verifier 주장 2 |
| 6 | TestEmaUnchangedVsBase 에 `_old_time_shape`(새 응답 rows[*].text 의 \d{6}:HH:MM → HH:MM 만 되돌린 뒤 기준 커밋과 비교) 추가, 기준 커밋은 올리지 않음 | 확인 | tests/v2/test_api_read_pullback.py:55-63, verifier 주장 5 |
| 7 | 엔진(core·engine·services)·pages·backtester 무변경, 엔진은 v2 를 import 하지 않음 → 배포는 tradebot-v2 재시작만 | 확인 | verifier 주장 3·6 |
| 8 | 정적 파일은 tornado StaticFileHandler(허용 목록 없음), nginx 원본은 /v2/ 통째로 8502. 서버 실제 nginx 는 미확인 | 확인(저장소) / 추정(서버) | v2/handlers.py:133-148, deploy/nginx-v2-location.conf |
| 9 | 게이트: v2 Py 465 OK · JS 206/206 · 회귀 1472/1472 · 바깥 연결 0 (구현 역할 1회 + verifier 1회 재실행) | 확인 | scratchpad gate.log |
| 10 | PO 412px 실측(로컬 dev_server 가짜 계정): 홈 기록 시각·현재가·최신 신호·최근 거래 새 모양, 로그 감사·엔진 시각 칸 한 줄(높이 29px), 감사 묶음 글 「(6회, 261112:15:43~261112:15:58)」은 두 줄로 꺾임, 차트 정상(kst_time.js import 성공) | 확인 | chrome-devtools 화면 캡처 |
| 11 | 엔진·오류 로그 글 본문은 DB message 원문(시각이 들어 있으면 옛 모양). insert_log 78곳에 시각 서식 0곳 | 확인(코드) / 미확인(운영 DB 표본) | verifier 지적 3 |
| 12 | verifier 판정 「사용자 보고 가능」, 반박 0. 지적: 버전 갱신 필요, kst_time.js 로드 실패 때 화면 멈춤 가능(권고: 그대로 둠), 미사용 kst() | 확인 | verifier 보고 |
| 13 | 이 변경은 투자자 체감 변경이라 배포 뒤 투자자 통보·notice-log 기록 대상 | 확인 | project-rules 투자자 연락 원칙 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 구현이 사용자 지시 범위와 맞는가(빠진 표시 곳·과한 변경)? | 맞다. 제외 7가지는 사용자 답 전이므로 보고에서 다시 확인받는다 |
| 2 | `_old_time_shape` 방식이 기준 비교 시험을 약하게 만드는가, 기준 커밋을 올리는 편이 나은가? | 시각 글자만 되돌리므로 약해지지 않는다. 기준 올림은 더 넓은 변경을 덮을 수 있다 |
| 3 | kst_time.js 로드 실패 대비(typeof 확인)를 이번에 넣어야 하는가? | 같은 배포·no-cache 라 그대로 둔다 |
| 4 | 커밋·push 승인 요청으로 넘어가도 되는가? | 그렇다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/kst_time.js, app.js, chart.js, save.js, index.html, style.css
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/db.py, v2/api_read.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/v2/js/time.test.mjs, tests/v2/test_api_read_pullback.py, tests/v2/test_db.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (1112-01 행)
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/b131ac26-0fd8-4dc4-82d2-2ffcbd7b1ed6/scratchpad/gate.log
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 요지 (1회째)
**판정:** 진행 — 구현·시험·게이트 기록이 사실과 맞고 막을 지적 없음. 직접 확인(11/12 16:06~16:12): 바뀐 파일 17·새 파일 3, core·engine·services·pages·backtester 무변경, time.test.mjs 7/7, TestKstStamp·TestEmaUnchangedVsBase 4/4, gate.log 뒤 고친 소스 0, last_status_log 화면 0, index no-store·정적 no-cache.
- 질문 1 대체로 맞음(보통): 백테스터 화면 저장 시각(save.js)과 차트 십자선 시각은 바뀌었으니 제외 설명과 함께 밝힐 것. 질문 2 _old_time_shape 맞음(높음). 질문 3 typeof 확인 불필요(높음). 질문 4 커밋 승인 요청 가능(높음).
- 권고 1 제외 7가지를 커밋 승인과 함께 다시 물음 + 저장 시각·십자선 바뀐 것 밝힘 · 2 없어지는 것(초·어제·열 폭·두 줄 꺾임) 보고 · 3 미사용 kst() 지우거나 이유 주석 · 4 _hhmm 이름은 다음 정리 때 · 5 배포 요청 때 서버 nginx·운영 logs 표본 읽기 확인.
- PO 반영: 권고 1·2·5 는 보고·배포 요청에 넣음. 권고 3 은 이미 주석(app.js 657)이 용도를 적고 있어 그대로 둠(결과에 영향 없음). 권고 4 는 다음 정리 때.
