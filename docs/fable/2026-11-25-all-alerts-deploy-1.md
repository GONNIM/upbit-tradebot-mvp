# Fable 질의 — 1122-01 투자자에게 모든 알림 사본 배포 (배포 승인 요청 직전, 1회째)

- 단계: main 합침 끝 → 사용자 배포 승인 요청 직전(되돌리기 어려운 일: 서버 git pull · 셸 복사 · 엔진 재시작 · 투자자 실발송 시작). 사실·실현 가능성·위험만.
- 프로젝트 규칙: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md · .claude/context/project-rules.md
- 계획: docs/plans/2026-11-23-investor-all-alerts/plan.md 8절(배포 순서) · 9절(메모리 감시)
- 이전 질의: docs/fable/2026-11-24-all-alerts-impl-1.md (구현 검토 2회 진행)

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 승인: 11/25 「1122-01 ㉠㉡ 권고대로」(규칙 문장·사본 안 가는 3곳·달라지는 점 4가지) · 「1122-01 main push 승인」 | 확인 | 대화 |
| 2 | main = eb79132 (1121-03 2d882c0 위로 옮김) · 버전 v1.2026.11.25.1227 → v1.2026.11.25.1344 · 게이트 회귀 1529/1529 · NETGUARD 0 | 확인 | scratchpad gate_1122b.log · push_1122b.log |
| 3 | 투자자 안내는 이미 보냄: 연락 기록 #21(11/25 13시대 PDF 3쪽 — 화면 수정 + 「텔레그램 모든 알림 곧 시작 · 반영하는 날 시험 알림 1건 먼저 · 운영자용 글도 그대로 보임 · 하실 일 💡·키 만료뿐」) → 계획 8절 9단계 안내는 이 연락으로 갈음 | 확인 | docs/operations/investor-notice-log.md #21 |
| 4 | 서버 11/25 14:16 읽기: HEAD 051e48c · 엔진 11/19 13:06:12 NRestarts 0 · v2 12:31:04 · 끄는 파일 없음 · .env 에 TELEGRAM_CHAT_ID_INVESTOR 있음 · TELEGRAM_INVESTOR_COPY 없음 · .env/secrets.toml 600 root · .env 사본 없음 | 확인 | scratchpad pre1122_read.out |
| 5 | 보유: pullback_state LIVE entry_count 0 · qty 0 · desync 0 · 마지막 체결 11/24 18:03 KRW-JTO SELL. account_positions 에 KRW-WIN·APENFT·USDT 코인 남음(봇 종목 아님) | 확인 | 같은 출력 |
| 6 | /root 셸 6개 = 서버 저장소 판(051e48c) 같음. 051e48c→eb79132 에서 바뀌는 셸은 2개: notify_telegram.sh(동작, /root 판과 71줄 다름) · watchdog_tradebot_engine.sh(주석 3줄) → 둘 다 diff→.prev→install (verifier 지적 3 반영) | 확인 | 같은 출력 · `git diff 051e48c eb79132 --stat -- scripts/server/` · pre1122_read3.out |
| 7 | 서버 작업 트리: 추적 안 되는 옛 파일 5개(check_*.py·sync_balances.py·mcmax33.sqlite3) · 이번 배포 34개 파일과 겹침 0 → git pull 막힘 없음 | 확인 | pre1122_read2.out |
| 8 | 메모리 감시: 로그 첫 줄 2026-02-23 · 임계 초과 3건 마지막 2026-03-12 · 최근 30일(10/26~) 「정상: N MB」 첫 숫자 최대 254MB·최소 119MB·4407줄(한도 1400) → 계획 9절 판정 기준 ①~③ 모두 (b) 유지 쪽. 첫 읽기의 「1400」은 분모를 잡은 스크립트 오류(verifier 지적 2) | 확인 | pre1122_read3.out |
| 9 | streamlit fileWatcherType = "none" · tradebot unit ExecStart = scripts/tradebot_boot.py · EnvironmentFile=.env | 확인 | 같은 출력 |
| 10 | v2(tradebot-v2) 는 이번 변경 파일(v2/key_expiry.py)을 쓰나 재시작 계획 없음 — 키 만료 배지 읽기만, 사본 코드는 엔진·셸·cron 쪽 | 확인 | verifier: 051e48c→eb79132 v2 변경은 v2/key_expiry.py plan_alerts 1줄뿐, 부르는 곳은 cron 의 scripts/key_expiry_check.py:220 하나 · v2 서버는 read_state·badge 만(v2/api_read.py:483~484) |
| 11 | 기동 줄: 서버 .env·unit 에 TRADEBOT_BOOT_RESUME 없음 → boot_resume 스레드 돎 · 11/19 기동 journal 에 INFO 줄 찍힘(엔진 로거) → `[NOTIFY-COPY] off reason=파일` 은 journal 에 보일 것 | 확인(코드·설정) / 추정(실제 줄) | pre1122_read3.out · tradebot_boot.py:47~55·185 · investor_copy.py:63~77 |
| 12 | 시험 사본 명령: 저장소에 사본 경로 시험 인자 없음(`--test-investor` 는 직접 발송·사본 경로 아님, notify_operator_test 는 investor_copy=False) → 서버에서 한 번짜리 파이썬 실행으로 notifier.send(INFO) 1건 → 운영자 1건 + 같은 글 사본 1건 · 그 프로세스 출력에 `[NOTIFY-COPY] sent` (atexit flush) | 확인(코드) | notifier.py:236 · investor_copy.py:100~117·139 |

## 다음에 하려는 일 (사용자 승인 뒤, 계획 8절 순서)
1. 서버에 `services/data/.investor_copy_off` 만들기(pull 전)
2. `git pull` → HEAD eb79132 · 버전 grep
3. /root 셸 2개(notify_telegram.sh · watchdog_tradebot_engine.sh): diff → .prev 사본 → install -m 755. 나머지 4개는 바뀌지 않아 손대지 않음
4. 보유 0 다시 확인 → `systemctl restart tradebot` → 기동 시각 · `[NOTIFY-COPY] off reason=파일` 확인. `채팅없음` 이거나 기동 줄이 2분 안에 안 보이면 멈춤(끄는 파일 둔 채 보고)
5. 9단계 안내는 #21 로 갈음(보내지 않음)
6. 끄는 파일 삭제 → 서버에서 `set -a; . ./.env; set +a; venv/bin/python -c 'notifier.send("INFO", "[시험] 투자자 알림 사본 시작", …)'` 한 번 실행(투자자 시험 1건 = #21 약속) → 출력의 `[NOTIFY-COPY] sent` 확인 · .env 값은 출력하지 않음. 셸 사본 길은 다음 날 09:00 일일 요약(cron 셸)으로 journal·운영자/투자자 건수 비교
7. 24시간 관찰(403·429·큐 가득·쉼 · 사본:운영자 건수) · 되돌리기: 끄는 파일(즉시) / git revert + /root 셸 2개 .prev 로 복원 + 재시작(보유 없을 때)

## 물음
- 배포 승인 요청을 올려도 되는가? 빠진 위험(매매 지연·운영자 알림 유실·투자자에게 내부 키 노출·반쪽 배포·재시작 때 보유 생김)이 있는가?
- verifier(11/25 14시대): 수정 후 승인 → 지적 5개(시험 명령 누락·메모리 근거·셸 2개·기동 줄 없을 때·되돌리기 셸) 모두 위에 반영.
- 6단계 시험 방법(한 번짜리 파이썬 1건 · 셸 길은 다음 날 일일 요약으로)이 타당한가?
- 사용자에게 물어야 할 것은?


## Fable 답 (1회째, 11/25 14시대)
- 판정: 수정 후 진행 — 사실 12개 맞음 · 빠진 큰 위험 없음 · 막음 2(순서 글)
- 막음 1: 새 notify_telegram.sh 운영자 발송이 `curl -K -` 로 바뀌었는데 서버 curl 로 돌려 본 적 없음 → 셸 설치 직후 끄는 파일 둔 채 운영자 시험 1건, 사용자가 운영자 채팅 도착 확인, 안 오면 .prev 로 되돌리고 멈춤 · curl 판 기록
- 막음 2: 6단계 `python -c` 는 로깅 설정이 없어 `[NOTIFY-COPY] sent` 가 안 보임 → 재실행하면 투자자에게 시험 2번 → basicConfig(INFO) + send 반환값 + flush 뒤 investor_copy.last_result 출력, 다르면 다시 실행하지 않음
- 권고 3~7: dotenv 로 .env 읽기 · 끄는 파일 삭제와 시험을 한 줄로·cron 5분 시각 피함 · 재시작 직전 미체결 0·분 경계 피함 · 승인 요청에 「엔진 정지·재시작 최대 3초 느려짐」「DB 백업」 · 관찰 출처 journal / key_expiry_cron.log copy= 구분

## 고친 것 (2회째 질의용)
- 막음 1 → deploy_1122_a.sh: 끄는 파일 → 감사 DB 백업(sqlite backup·600) → pull(--ff-only·HEAD eb79132 아니면 멈춤) → 셸 2개 .prev·install → `curl --version` → `/root/notify_telegram.sh "[시험] 셸 알림 길 확인" …` 1건 → 여기서 멈추고 사용자에게 운영자 채팅 도착 확인 받음. 안 오면 rollback_1122.sh full(끄는 파일 유지 + 셸 .prev 복원)
- 막음 2 → deploy_1122_c.sh: cron 5분 시각(분%5 가 4·0) 피함 → `rm 끄는 파일 && venv/bin/python -c` 한 줄: logging.basicConfig(INFO) · dotenv load_dotenv(.env) · notifier.send(INFO, "[시험] 투자자 알림 사본 시작", …) · investor_copy.flush(5) · `RESULT send= flush= copy=<last_result>` 출력(정정: notifier.flush_copies 는 notifier.py:281 에 있음 — PO 가 grep 을 잘못 읽음. investor_copy.flush(timeout) 를 써도 같음). copy=sent 가 아니면 다시 실행하지 않고 끄는 파일 다시 두고 보고
- 권고 5 → deploy_1122_b.sh: 끄는 파일 있는지 → 눌림목 LIVE 회차·보유 + 묶인 코인 종목 + 묶인 원화 계정이 모두 0(「0 0 0 0」)일 때만 → 초 :50~:07 피해 restart → 2분 안에 `[NOTIFY-COPY] off reason=파일` 아니면 멈춤
- 권고 6·7 → 승인 요청 글과 관찰 지시에 넣음
- 스크립트: /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/f030db45-bfaa-44d4-9fd0-ab15a99f24e0/scratchpad/deploy_1122_a.sh · deploy_1122_b.sh · deploy_1122_c.sh · rollback_1122.sh (bash -n 통과 · heredoc 없음)

## 물음 (2회째)
- 막음 2개가 위 스크립트로 풀렸는가? 스크립트에 새 위험(되돌리기 어려운 동작·값 노출·순서 오류)이 있는가? 배포 승인 요청을 올려도 되는가?

## Fable 답 (2회째, 11/25 14시대)
- 판정: 수정 후 진행 — 1회째 막음 2개 풀림 · 새 막음 2 · 2회째라 고친 뒤 다시 묻지 말고 사용자에게 승인 요청
- 막음 1: (나) 보유 확인 뒤 최대 18초 기다림 → :00 봉 매수가 끼면 보유 중 재시작 → 「기다림 → 확인 → 바로 restart」
- 막음 2: (다) import 실패 등이 안 보이고 끄는 파일이 이미 지워져 시험 없이 실제 사본이 먼저 감 → rm 전 import 확인 · copy=sent 아니면 끄는 파일 다시 둠
- 권고: (가) 설치 실패·같음 아님이면 멈춤 · .prev 덮어쓰지 않음 · pull </dev/null · cron 5분 시각 피함 · (다) flush(8) · (나) 앞머리에 HEAD·셸 같음 확인 · 배포 끝까지 main push 하지 않음(이 문서도) · 질의서 flush_copies 문장 정정

## 반영 (사용자 승인 요청 전)
- 막음 1·2 와 권고 7개 모두 deploy_1122_a/b/c.sh 에 반영 · bash -n 4개 통과 · 이 문서는 배포 끝날 때까지 커밋·push 하지 않음
- 확인 안 함: (다) 실패 길을 로컬에서 일부러 실패시켜 보는 시험(서버 venv 대신 이 맥 venv 구성이 달라 대표성 낮음 → 서버에서 import 미리 확인 줄로 갈음)
