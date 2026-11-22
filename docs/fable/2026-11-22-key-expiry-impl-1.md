# 질의: 1122-01 업비트 키 만료 미리 알림 구현을 끝냈고, 커밋 승인을 사용자에게 요청하려 함

**지금 단계:** 구현 (커밋 승인 요청 직전)
**다음에 하려는 일:** 사용자에게 커밋·push 승인을 요청한다(pages/dashboard.py 버전 갱신 포함). 승인 뒤 커밋·push, 그다음 투자자 안내 초안과 배포 승인 요청(git pull · tradebot-v2 만 재시작 · crontab 한 줄 설치 · 스크립트 손 실행 1회)은 따로 묻는다. 이번 커밋에는 앞 일의 문서(1121-01/02 Fable 질의 2개 · claim/ver9 폴더 · investor-notice-log #18 · HANDOFF)도 함께 넣을지 사용자에게 묻는다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 승인된 계획: 사용자 「1122-01 ① 승인 ② 투자자 ③ 그대로 둠 ④ 그대로 둠」 | 확인 | docs/plans/2026-11-22-key-expiry-alert/plan.md |
| 2 | 바뀐 코드: 새 v2/key_expiry.py · scripts/key_expiry_check.py · deploy/key-expiry.cron · tests/v2/test_key_expiry.py(36) · tests/v2/js/key_expiry.test.mjs(5), 고침 v2/api_read.py(StatusHandler) · v2/static/app.js(배지 맨 끝) · v2/static/style.css(.p-bad) | 확인 | git status / git diff |
| 3 | 계획과 다른 점: 계산 함수 위치 services/→v2/(tests/v2/test_server.py:234 가 v2→services import 금지), cron 09:05·21:05 두 번(만료 당일 「만료됨」 그날 안에), 만료 뒤 알림 기록 칸 last_expired_alert_date 분리, 보내기 실패한 알림은 기록 안 해 다음 실행에 다시 보냄, 「확인 안 됨」 배지 글에 「(마지막으로 받은 만료일 YYYY-MM-DD)」 붙임(plan.md 3-4 도 고침) | 확인 | v2/key_expiry.py, deploy/key-expiry.cron, plan.md |
| 4 | verifier 1회 「고친 뒤 승인」(누락 2·문구 1·채널 비교·OverflowError) → 모두 고침 → 2회 「승인할 수 있음, 남은 반박·누락 없음」(「확인 안 됨」 412px 새 글 화면만 미확인 → PO 가 찍음) | 확인 | 대화 기록 |
| 5 | 시험(고친 뒤 최종): 새 시험 36 OK · v2 시험 502 OK · JS 224/224 · regression_gate rc=0 · 회귀 1472/1472 · NETGUARD 바깥 연결 0건 | 확인 | scratchpad gate-1122c.log |
| 6 | 브라우저 실측(로컬 개발 서버 + 헤드리스 Chrome): 412px 보통 362일(회색)·경고 18일(노랑)·만료됨(빨강)·확인 안 됨(빨강, 새 글 한 줄)·배지 없음(파일 없음), 1280px 확인 안 됨. 배지는 모두 맨 끝 | 확인 | scratchpad ke-412-ok/warn/bad/stale/none.png, ke-pc-stale.png |
| 7 | 412px 스크린샷은 배지 없는 화면까지 오른쪽이 잘림 → 이번 변경과 무관. 헤드리스 창 크기 탓인지 원래 넘침인지는 미확인 | 추정 | ke-412-none.png |
| 8 | 엔진·config.py·DB·매매 규칙 파일은 diff 에 없음. 스크립트는 core·pyupbit·config·streamlit 을 import 하지 않음 | 확인 | git diff, verifier sys.modules 확인 |
| 9 | 문서: project-rules.md 투자자 연락 세 번째 종류(키 발급 부탁) · 정기 점검 한 줄 · 키 교체 뒤 손 실행 한 줄 · 버전 2.15 | 확인 | git diff .claude/context/project-rules.md |
| 10 | 서버 .env 에 TELEGRAM_CHAT_ID_CRITICAL/_WARNING 키 없음(키 이름 목록) → 알림은 기본=운영자 채팅 하나로 감 | 확인 | 11/22 11:47 key5_read.sh 출력 |
| 11 | 서버에 설치된 tradebot-v2 유닛이 저장소 deploy/tradebot-v2.service 와 같다 | 추정 | 배포 뒤 배지 확인으로 드러남 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 커밋 승인을 요청해도 될 만큼 사실·위험이 정리됐는가(특히 계획과 다른 점 3번이 사용자 재승인이 필요한 변경인가) | 모두 계획 목적 안의 구현 세부라 보고에 적는 것으로 충분 — 다만 cron 두 번은 서버에 설치되는 값이라 보고에 분명히 적음 |
| 2 | 앞 일 문서를 같은 커밋에 묶을지, 따로 커밋할지 | 따로 커밋(문서 커밋 1 + 기능 커밋 1)이 되돌리기 쉬움 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-22-key-expiry-alert/plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/key_expiry.py, scripts/key_expiry_check.py, deploy/key-expiry.cron, v2/api_read.py, v2/static/app.js, v2/static/style.css, tests/v2/test_key_expiry.py, tests/v2/js/key_expiry.test.mjs
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/ke-412-stale.png (외 ke-412-*.png)
- 규칙: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1회째 요지 (Fable · 11/22)

- 판정: 진행. 시험 36·JS 224 직접 실행, 게이트 기록 시각이 마지막 수정보다 뒤, 엔진·config·DB 파일 diff 없음, 비밀 시그니처 0건. 권고: plan.md 에 「구현에서 달라진 점」 절, 스크립트 첫 줄 「하루 2번」, 커밋은 파일 단위 둘로(문서 / 기능), 투자자 원본 PDF 커밋 사실 알림, 배포 때 텔레그램 발송 경로 확인 방법·서버 유닛 대조(systemctl cat tradebot-v2)·notifier 의 늦은 streamlit import 경로 적기. 사용자에게: 커밋 둘로 나눌지, 투자자 PDF 넣을지, 다른 점 5가지 함께 승인하는지.
- 반영: plan.md 7절(8가지), 스크립트 첫 줄 고침(시험 36 OK). PDF 글자에는 이름·연락처·계좌 없음(pdftotext 확인). 배포 쪽 권고 5·6·7 은 배포 승인 요청서에 넣음.
