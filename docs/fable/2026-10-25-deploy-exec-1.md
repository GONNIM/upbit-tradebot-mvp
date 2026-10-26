# 질의: 배포 실행 직전 정지선(2-0)과 nginx 스크립트 검증을 마쳤고, D1~D8 실행에 착수하려 합니다

**지금 단계:** 리뷰 (배포 실행 직전)
**다음에 하려는 일:** 요청서 `docs/specs/v2-dashboard/deploy-request-20261025.md` 2-1~2-9 순서대로 D1(git pull)~D8(cron)을 SSH 로 실행합니다. 멈춤 조건이 하나라도 나오면 그 자리에서 멈추고 보고합니다. 사용자 결정 1025-10「1 가」(D1~D8 한 번에 승인, 멈춤 조건 없으면 끝까지)에 따른 실행입니다. 이 질의서는 배포 완료 보고 커밋에 함께 넣습니다(문서 묶음).

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 로컬 HEAD = origin/main = 12ddb4f, 미추적 15(기존 13 + 요청서 + deploy-request-1 질의서), 추적 변경은 M HANDOFF.md 1건 | `git rev-parse`, `git status --short` (verifier 1a·1b 확인됨) |
| 2 | diff 156b351..12ddb4f 138개, 허용 목록 밖 0, core/engine/services/config.py 0, ff 가능 | `git diff --name-only`, `merge-base --is-ancestor` (verifier 1c) |
| 3 | 서버: HEAD 156b351, dashboard.py:495 v1.2026.10.20.1711, tradebot active·기동 2026-10-20 17:40:51 KST·NRestarts 0, tradebot-v2·.v2_*·PULLBACK 없음, 미추적 5건 그대로 | SSH 읽기 전용 (verifier 2a~2d) |
| 4 | params interval minute3·ticker JTO, [CLOCK] timeframe=minute3 | verifier 2e·2f |
| 5 | nginx: listen 443 지시문 1개(14행), 앵커 1개, /v2/ 0, sites-enabled → sites-available 링크, 8502 미사용, 최신 백업 backup_20261025_110001, 현재 `nginx -t` 통과 | verifier 2g~2k, 지적 2 |
| 6 | 기준선: https 루트 200, 24h journal locked 0·Traceback 0·ERROR 0·CRITICAL 2(둘 다 INFO `[NOTIFY] sent kind=CRITICAL` 매매 알림 — 결함 아님) | verifier 3a·3b |
| 7 | nginx 스크립트가 요청서 부록 A 와 바이트 동일, 서버 파일 sha256 = 로컬 사본 81c45030…70ec, 사본 시험 OK inserted lines=6 → 재실행 SKIP, diff 는 443 블록 location / 앞 6줄뿐 | verifier 4a~4d |
| 8 | verifier 결론「D1 착수 가능」, 반박 0. 권고: D6 백업 직후 sha256 81c45030…70ec 확인, 편집 뒤 31b6a7d0…3427 확인, 출력이 `OK inserted lines=6` 이 아니면 멈춤 → PO 가 실행 단계에 추가(확인만 더함, 요청서 범위 변화 없음) | verifier 지적 1·3 |
| 9 | 2-3 D3 재시작은 확정 봉 처리 직후·미체결 0(숫자 아니면 멈춤)·경계까지 60초 이상일 때만, 재시작 뒤 5분 BOOT-RESUME·결함 태그 확인, D5 는 그 뒤에만 | 요청서 2-3·2-5 |
| 10 | 원 배포 요청서에 대한 Fable 판정 2회째「진행」 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-request-1.md |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 2-0 정지선이 모두 기재와 일치하므로 D1~D8 실행에 착수해도 되는가 | 착수 가능. 멈춤 조건은 요청서대로 적용 |
| 2 | verifier 권고(해시 대조·OK 출력 아니면 멈춤)를 실행 단계에만 넣고 요청서 문서는 배포 보고 때 반영하는 것이 맞는가 | 맞음. 확인 단계 추가뿐이라 승인 범위 안 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (0절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-request-1.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fcb8d941-5702-48ea-a05a-591030fe5f4d/scratchpad/deploy/nginx_add_v2.py
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fcb8d941-5702-48ea-a05a-591030fe5f4d/scratchpad/deploy/nginx_tradebot_server_copy.conf
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fcb8d941-5702-48ea-a05a-591030fe5f4d/scratchpad/deploy/dryrun.conf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: 배포 실행 직전 정지선(2-0)과 nginx 스크립트 검증을 마쳤고, D1~D8 실행에 착수하려 합니다

**판정:** 진행
**이유:** 2-0 정지선의 모든 항목을 서버 읽기 전용 SSH 와 로컬 git 으로 직접 다시 확인했고 기재와 일치합니다. nginx 스크립트는 요청서 부록 A 와 바이트 동일하고 서버 파일 해시도 기재와 같습니다. 남은 지적은 모두 권고입니다.

(직접 확인 표 요지 — 2026-10-25 17:06 KST: 로컬 HEAD=origin 12ddb4f, 미추적 16(이 질의서 포함), diff 138·엔진 0·ff 가능, 서버 156b351·v1.2026.10.20.1711·tradebot 17:40:51 NRestarts 0, v2 흔적 없음, 미추적 5, params JTO·minute3, nginx sha256 81c45030…70ec·443 1·앵커 1·/v2/ 0·nginx -t 통과, 8502 0, 백업 20261025_110001, 루트 200, journal 0·0·0·CRITICAL 2(알림), orders 미체결 0, 사본 결과 sha256 31b6a7d0…3427, 서버 .gitignore 에 .v2_* 없음 → D1 선행 필요, 확정 봉 17:03:05·17:06:10 정상, crontab·nginx 백업 파일명 충돌 없음.)

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | D1~D8 착수 가능한가 | 착수 가능. 미추적 16(이 질의서 추가)은 서버·배포 영향 없음. 멈춤 조건은 2-1~2-8 그대로 | 높음 |
| 2 | verifier 권고를 실행 단계에만 넣는 것이 맞는가 | 맞음. 서버 변경을 늘리지 않아 승인 범위 안. 기대 해시 두 값 직접 재계산해 확인 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인하는지 |
|---|---|---|---|---|
| 1 | 권고 | 2-0 미추적 기준을 `docs/fable/2026-10-25-deploy-*.md` 로, 보고에 16 기재 | 글자 그대로면 멈춤에 걸림(서버 영향 없음) | `git status --short \| grep -c '^??'` → 16 |
| 2 | 권고 | D6 직전 스크립트 원문 표시·보고에 기재 | 1025-10 1 가 조건 | 보고 D6 절 |
| 3 | 권고 | 사후 해시는 사전 해시 81c45030…70ec 일 때만 31b6a7d0…3427 기대 | 사전이 다르면 그 자리에서 멈춤 | sha256sum 사전·사후 |
| 4 | 권고 | explain8.sql 을 scratchpad 에 파일 도구로 미리 작성 | heredoc 금지 | ls explain8.sql |
| 5 | 권고 | 보고에 버전 구→신·3점 일치 의무 기재 | project-rules 배포 보고 규칙 | 보고 본문 |

## 사용자에게 물어야 할 것
- 없음

## PO 처리
- 권고 1~5 반영: 1·5 는 배포 보고에, 2 는 이 세션 화면에 원문 표시(17:0x, D6 전), 3 은 D6 실행 조건, 4 는 scratchpad/deploy/explain8.sql 작성.

