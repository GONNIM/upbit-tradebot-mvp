# 질의: 1122-01 ㉠ 투자자 텔레그램 키 만료 알림 구현을 끝냈고, 커밋·배포 승인을 사용자에게 요청하려 함

**지금 단계:** 구현 (커밋·배포 승인 요청 직전)
**다음에 하려는 일:** 사용자에게 한 번에 묻는다 — (1) 커밋·push 승인(문서 커밋: 지난 배포 요청 문서·PDF / 기능 커밋: ㉠ 코드·시험·규칙·dashboard.py 버전 갱신) (2) 배포 승인(앞서 만든 deploy-1122-01.sh 의 FEATURE 를 새 기능 커밋으로 바꾸고 「기능 커밋 뒤 docs 밖 변경 없음」 검사 유지, 투자자 채팅이 없으면 investor=off 로 돈다) (3) PDF 발송(사용자가 보냄). 투자자가 「시작」을 누른 뒤의 .env 등록(--pick)은 서버 설정 변경이라 그때 따로 묻는다(등록 전 서버 읽기: getMe 봇 이름·getWebhookInfo·`ls -l .env` 심볼릭 링크 여부).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 「1122-01 ㉠ 적용」 = 키 만료 알림만 투자자에게도(단계·만료 뒤), 매매·운영 알림은 운영자만, 채팅은 .env 새 칸 TELEGRAM_CHAT_ID_INVESTOR. 계획 승인 때 ③ 「그대로 둠」을 다시 정한 것 | 확인 | docs/plans/2026-11-22-key-expiry-alert/plan.md 8절, 대화 |
| 2 | 구현: v2/key_expiry.py plan_investor_alerts(기록 칸 따로 investor_alerts·last_investor_expired_date, 키 교체 시 비움) · scripts/key_expiry_check.py investor_chat(기본·등급 채널과 같으면 off)·send_direct(_why)·--test-investor · 새 scripts/telegram_investor_register.py(getMe·getUpdates 목록, --pick 으로 .env 한 줄 원자적 쓰기, 기본·운영자·WARNING·CRITICAL 채팅 거부) | 확인 | git diff, 파일 |
| 3 | services/notifier.py·core·engine·config·pages 변경 0 (dashboard.py 버전은 커밋 때 갱신 예정) | 확인 | git diff --stat |
| 4 | 시험: 키 만료 51 OK(새 15), 게이트 v2 517 OK · JS 통과 · 회귀 1472/1472 · NETGUARD 0 | 확인 | scratchpad gate-1122e.log |
| 5 | verifier 1회 「고친 뒤 승인」: 반박 1(가벼움, 등록 목록에 @아이디 등 더 나옴 → 계획서 문구 고침·출력 보고 금지 줄). 반영: 등급 채널 거부 · 시험 알림 실패 코드 출력 · 정기 점검에 cron 로그 investor= 확인 · 키 교체 뒤 err=None 확인 · 사본 확인 · 재등록 때 기록 안 비움 메모 · 옛 안내 초안 「대체됨」 · PDF 에 알림 시점·24시간 넘으면 다시 글 보내기. 남긴 것(②): 투자자 발송 실패 운영자 알림 없음, 키 교체 뒤 조회 실패 시 옛 만료일 「만료됨」 계속 — 절차로 막음 | 확인 | verifier 보고(대화), plan.md 8절 7번 |
| 6 | 텔레그램 공식: 봇은 먼저 대화를 시작할 수 없음, getUpdates 는 24시간 보관, 웹후크가 있으면 getUpdates 안 됨 | 확인(verifier 11/22 16:01 core.telegram.org/bots, /bots/api) | 원문 인용 verifier 보고 |
| 7 | @upbit_tradebot_bot 공개 페이지 이름 「Upbit Tradebot 알림」 | 확인 | curl t.me/upbit_tradebot_bot 11/22 14시대 |
| 8 | 서버 .env 의 봇 토큰이 이 봇인지, 웹후크·다른 poller 유무, .env 심볼릭 링크 여부 | 추정(미확인) | 등록 전 서버 읽기로 확인 예정 |
| 9 | PDF A4 1쪽 119,283바이트 · 나눔고딕 3종 emb/sub yes · sha256 앞 16자 165f32925d188de9 · 80dpi 렌더 직접 열어 글자 보임 | 확인 | pdfinfo·pdffonts·pdftoppm |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 커밋·배포 승인을 함께 요청해도 될 만큼 사실·위험이 정리됐는가 | 됨. 배포는 투자자 등록 전이라 investor=off 로 지금과 같다 |
| 2 | PDF 를 지금 보내도 되는가(등록·시험 알림은 투자자 「시작」 뒤) | 됨. 사실 8 은 등록 단계에서 확인되고, 틀리면 등록 전에 멈춘다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-22-key-expiry-alert/plan.md (8절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/key_expiry.py, scripts/key_expiry_check.py, scripts/telegram_investor_register.py, tests/v2/test_key_expiry.py, .claude/context/project-rules.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-22-key-expiry-alert/investor-guide-20261122.html (.pdf)
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/deploy-1122-01.sh
- 규칙: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변 1회째 요지 (Fable · 11/22)

- 판정: 수정 후 진행. 막음 3: ① PDF 발송 전에 서버 봇 아이디 확인(바깥 발송은 되돌릴 수 없음) ② 배포 파일 NEWVER 도 새 버전으로 ③ HANDOFF 행 PDF 크기·sha256 낡음. 권고 5: 휴대폰 미리보기 부탁 · 공개 저장소라 등록 때 이름·시각 맞춰 보기 · 배포 출력 investor=off 확인 · 발송 뒤 연락 기록 #19(회신 대기 금지) · .gitignore .env 임시 파일.
- 반영: ① scratchpad key7_bot_read.sh(getMe 봇 아이디·이름, getWebhookInfo 웹후크 있음/없음·대기 수, .env 종류·권한·사본 수만 출력, bash -n 통과) — 순서 「서버 읽기 → 봇 아이디가 upbit_tradebot_bot 이면 PDF 발송」 ② 배포 파일 FEATURE·NEWVER 를 자리표시로 바꾸고 안 채우면 0단계 전에 멈춤, 커밋 뒤 채움 ③ HANDOFF 행 119,283바이트·165f32925d188de9 로 고침. 권고: 등록 때 이름·「시작」 시각 맞춰 보기(plan 8절 5번·project-rules) · 4단계에 investor=off 확인 줄 · 휴대폰 미리보기 부탁은 요청 글에 · .gitignore 는 이미 `*.tmp`(32줄)가 막아 바꾸지 않음(git check-ignore 확인) · 연락 기록은 발송 뒤.

# 답변 2회째 요지 (Fable · 11/22)

- 판정: 진행. 막음 3개 모두 고쳐짐 확인, 권고 5: 발송 조건에 웹후크 없음 · 봇 이름도 PDF 와 대조 · .env regular file·사본 0 확인 · --pick 의 「등록함: 이름」 다시 대조 · HANDOFF·질의서 표기. 반영: 권고 4·5 는 문서에, 1~3 은 사용자 요청 글의 볼 것으로.
