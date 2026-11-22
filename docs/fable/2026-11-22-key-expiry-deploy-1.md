# 질의: 1122-01 업비트 키 만료 미리 알림 — 투자자 안내 초안과 배포 승인 요청을 사용자에게 올리려 함

**지금 단계:** 배포 승인 요청 직전 (커밋·push 끝)
**다음에 하려는 일:** 사용자에게 (1) 투자자 안내 글 발송(사용자가 보냄) (2) 배포 승인을 묻는다. 승인되면 사용자가 `! ssh root@orionhunter7.cafe24.com 'bash -s' < deploy-1122-01.sh` 로 배포 파일을 실행한다(자동 모드에서 SSH 쓰기는 사용자 실행으로 해 옴). 배포 뒤 브라우저 새로고침 확인 · 다음 21:05 cron 실행 기록 확인 · 배포 보고 · 연락 기록 #19 · HANDOFF 갱신을 문서 커밋으로 묶는다(이번 안내 초안·이 질의 파일·HANDOFF 행 변경도 그 커밋에 넣음).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 「1122-01 ① 승인 ② 넣음」 → 커밋 3753da4(문서) · 2f6f1f3(기능, v1.2026.11.17.1407 → v1.2026.11.22.1339) push, pre-push 게이트 회귀 1472/1472 · NETGUARD 0 | 확인 | git log, push 출력 |
| 2 | 서버 11/22 14:12 읽기: HEAD 9f70dac · 버전 1407 · 추적 파일 변경 없음(안 올린 파일 5개뿐, 새 파일 경로와 겹치지 않음) · tradebot 기동 11/19 13:06:12 · tradebot-v2 기동 11/17 15:15:02 · 둘 다 active | 확인 | scratchpad key6_predeploy_read.sh 출력(대화) |
| 3 | 서버 설치 유닛 /etc/systemd/system/tradebot-v2.service 가 저장소 deploy/tradebot-v2.service 와 같음(주석·빈 줄 뺀 diff), drop-in 없음. ReadWritePaths 에 services/data 있음 · InaccessiblePaths 는 .env·secrets.toml·credentials.yaml 뿐 · User=root | 확인 | 같은 출력, deploy/tradebot-v2.service |
| 4 | crontab key_expiry 줄 0 · 결과 파일 없음 · services/data 755 root · venv jwt 2.10.1 · requests 2.32.4 · dotenv 있음 · /tmp/key_expiry.lock 없음 | 확인 | 같은 출력 |
| 5 | 9f70dac..2f6f1f3 변경: 코드는 v2/·scripts/key_expiry_check.py·pages/dashboard.py(버전 글자만)·deploy/key-expiry.cron, 나머지는 docs·tests·project-rules. 엔진·config·DB 코드 없음 | 확인 | git diff --stat 9f70dac..2f6f1f3 |
| 6 | 구버전(Streamlit) 화면 버전 글자는 엔진을 재시작하지 않으므로 그대로 1407 로 보임(fileWatcherType none, 1106-02·1112-01·1111-01 과 같은 의도된 불일치) | 추정(11/17 배포 보고 기록) | docs/specs/v2-dashboard/deploy-report-20261117-1111-01.md |
| 7 | v2 정적 파일은 Cache-Control no-cache 라 새로고침으로 새 app.js 를 받음 | 확인 | v2/handlers.py:140 |
| 8 | 지금 키 만료 2027-11-19 12:21:56 → 손 실행 결과 alerts=0/0 예상, 텔레그램 발송 경로는 이번 배포로 증명되지 않음. 확인 방법: 배포 뒤 scripts/v2/notify_operator_test.py(운영자 시험 발송) 또는 첫 실제 알림 때 cron 로그 alerts= 값 | 추정 | scripts/key_expiry_check.py, plan.md |
| 9 | 홈 배지는 투자자가 보는 변경 → 투자자 연락 원칙 2번(체감 변경 통보) 대상. 초안: docs/plans/2026-11-22-key-expiry-alert/investor-notice-draft.md | 확인 | project-rules 투자자 연락 원칙 |
| 10 | 배포 파일은 HEAD·추적 변경·cron 중복을 먼저 보고 어긋나면 멈춤, 기능 커밋 뒤 docs 밖 변경이 있으면 멈춤, tradebot-v2 만 재시작, crontab 백업(/root/crontab-before-1122-01.txt, 600) 뒤 한 줄 추가, 손 실행 1번, 결과 파일·배지·엔진 기동 시각 그대로·v2 Traceback 줄 수 출력 | 확인 | scratchpad deploy-1122-01.sh(bash -n 통과) |
| 11 | 되돌리기: crontab 백업으로 되돌림(`crontab /root/crontab-before-1122-01.txt`) · 결과 파일 치움 · 로컬 되돌림 커밋 push 뒤 ff 병합·tradebot-v2 재시작. 서버에서 git reset 하지 않음 | 확인 | 배포 파일, 11/17 배포 보고 되돌리기 절 |

| 12 | verifier 1회: 「고친 뒤 승인할 수 있음」, 반박 0. 지적 반영: ① crontab 백업 실패·빈 백업이면 멈춤, 설치 뒤 줄 수가 이전+1 아니면 백업으로 되돌리고 멈춤 ② 서버 시간대 KST 아니면 멈춤 ③ 자식 python 에 `< /dev/null` ④ 안내 초안 3번에 「(마지막으로 받은 만료일 …)」 ⑤ 완료 조건에 「브라우저에서 회색 키 배지 보임」(v2 샌드박스 읽기는 이것으로만 증명) ⑥ 되돌리기 커밋도 dashboard.py 버전 갱신 ⑦ 단계 알림 채널 증명은 첫 30일 단계(2027-10-20 무렵) cron 로그 alerts=1/1 로 남김(notify_operator_test 는 운영자 채널만 시험) | 확인 | verifier 보고(대화), deploy-1122-01.sh bash -n 통과 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 배포 파일과 순서(안내 먼저 보내고 배포)에 빠진 확인·위험이 있는가 | 엔진 무관·되돌리기 쉬움, 손 실행이 업비트 API 를 1번 부르는 것만 바깥 영향 |
| 2 | 투자자 안내 초안이 사실과 맞고 원칙(키 값 메신저 금지·투자자가 발급)에 맞는가 | 맞음 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/deploy-1122-01.sh
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-22-key-expiry-alert/investor-notice-draft.md, plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/key_expiry_check.py, v2/key_expiry.py, deploy/key-expiry.cron, deploy/tradebot-v2.service
- 규칙: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변 1회째 요지 (Fable · 11/22)

- 판정: 진행. 지적 7개 모두 권고. 직접 확인: 커밋·버전 diff·시험 36+5·diff stat·유닛·no-cache·안내 글과 배지 코드 일치. 서버 출력과 verifier 보고는 직접 못 봄(배포 파일이 실행 때 다시 보고 멈춤).
- 반영: ① 손 실행 실패면 경고 줄과 처리 기준(원인 확인 뒤 결과 파일 치울지 정하고 다시 실행) ② 14초 뒤 기동 시각·NRestarts 가 바뀌면 멈춤 ③ 안내 뒤 배포가 멈추면 배지가 늦게 보임을 승인 요청에 적음 ④ 안내 1번에 「(362일 남음)」 ⑤ 감사 DB 백업 생략 까닭(엔진·DB 코드 변경 없음, tradebot-v2 만 재시작)을 승인 요청에 적음 ⑥ HANDOFF 행·plan.md 5절 「다음 cron 실행(21:05 또는 09:05)」 ⑦ 배포 파일 5단계에 fileWatcherType 출력, 배포 보고에 버전 구→신.
