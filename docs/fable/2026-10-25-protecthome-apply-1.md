# 질의: ProtectHome 수정을 커밋·push 했고(5692998), 서버 반영과 D5~D8 재개를 실행하려 합니다

**지금 단계:** 리뷰 (서버 반영 직전)
**다음에 하려는 일:** 서버에서 다음 순서로 실행합니다. ① `git pull --ff-only`(12ddb4f → 5692998) ② `cp deploy/tradebot-v2.service /etc/systemd/system/` ③ `systemctl daemon-reload` ④ `systemctl restart tradebot-v2` ⑤ tradebot ExecMainStartTimestamp 17:10:35·NRestarts 0 확인(A2) ⑥ D5 전체(check FAIL 0·PASS root-readonly·unit-props, a3, RSS, A2, EXPLAIN 8) ⑦ D6 nginx(백업 sha256 81c45030…70ec 확인 → 스크립트 → 결과 31b6a7d0…3427 → nginx -t → reload → /v2/ 401·루트 200) ⑧ D7 허용 목록 ⑨ D8 cron. 멈춤 조건은 요청서 2-x 그대로이고, ①~④ 전에 check 를 돌리면 FAIL unit-props 가 정상입니다. 엔진은 재시작하지 않습니다(사용자 결정 1025-11 2 가). 사용자 승인 1025-12「승인」.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 커밋 5692998 = origin/main, 6개 파일만, HANDOFF 는 미스테이징으로 남음 | `git diff --cached --name-only`, `git rev-parse` |
| 2 | push 훅 게이트 350/350 통과 | push 출력 |
| 3 | 직전 Fable 판정 「진행」(구현 검수), verifier 반박 0 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-protecthome-fix-1.md |
| 4 | 서버(검수 때 읽기 전용 확인): HEAD 12ddb4f, tradebot 17:10:35·NRestarts 0, v2 ProtectHome=no, 의존 관계 없음, NeedDaemonReload no, nginx /v2/ 0, 허용 목록 없음, 미추적 5개는 커밋 경로와 겹치지 않음 | 위 파일 답변 직접 확인 요지 |
| 5 | 되돌리기: 문제 시 `systemctl disable --now tradebot-v2`(엔진 영향 없음) → 요청서 2-10 | 요청서 2-10 |
| 6 | D6~D8 실행 계획은 deploy-exec-1 에서 Fable 「진행」을 받은 그대로이며, D6 해시 조건(사전 해시가 81c45030…70ec 일 때만 사후 31b6a7d0…3427 기대)도 같음 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-exec-1.md |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 위 순서로 서버 반영과 D5~D8 재개를 실행해도 되는가 | 됨 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-protecthome-fix-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-exec-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: ProtectHome 수정을 커밋·push 했고(5692998), 서버 반영과 D5~D8 재개를 실행하려 합니다

**판정:** 진행
**이유:** 사실 1·3·4·6 을 로컬 git·서버 읽기 전용 SSH·문서 원문으로 직접 확인. ①~⑨ 는 요청서 2-4~2-8 과 이전 「진행」 범위 안. 남은 지적은 권고뿐. 1025-12 사용자 승인은 Fable 이 볼 수 없어 PO 가 확정(사실 2 push 출력도 미확인).

(직접 확인 요지 — 17:4x: 로컬 5692998 = origin, 6개 파일, 커밋 제목에 1611 → 1729. 서버 12ddb4f·추적 변경 0·fetch dry-run 12ddb4f..5692998, tradebot 17:10:35 NRestarts 0·오류 0·CONFIRMED 17:36·17:39·17:42 정상, v2 ProtectHome=no, nginx sha256 81c45030…70ec·/v2/ 0·백업 파일명 충돌 없음, 허용 목록·cron v2hist 없음.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 실행해도 되는가 | 됨. ff 가능, ②~④ 는 엔진과 의존 없음, ⑥~⑨ 는 승인 범위·실행 전 상태 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 권고 | ④ 직후 is-active·ProtectHome·journal Traceback·8502 응답 확인 | 첫 ro 기동 | 출력 |
| 2 | 권고 | ① 뒤 버전 1729, ② 뒤 유닛 diff 없음 | 누락 즉시 포착 | 출력 |
| 3 | 권고 | 3점 일치를 5692998·1729·화면 1611/1729·실행 12ddb4f·tradebot 17:10:35·v2 새 시각으로 | 보고 규칙 | 보고 |
| 4 | 권고 | 요청서 A17 문구·HANDOFF 1025-12 갱신 | 문서·실제 불일치 | grep |
| 5 | 권고 | Co-Authored-By 표기 — push 된 커밋은 고치지 않음 | force push 방지 | git log |

## 사용자에게 물어야 할 것
- 없음

## PO 처리
- 1025-12 승인은 사용자 메시지(10/25 17시대 「1025-12 승인」)로 확정.
- 권고 1·2: 실행에 넣음(v2 active·read-only·Traceback 0·/v2/ 401·버전 1729·UNIT_SAME). 권고 3·4: 배포 완료 보고·요청서·HANDOFF 에 반영. 권고 5: 이 세션의 커밋 서명 지시가 「Claude Opus 5.5」이므로 지적 대상 아님, 고치지 않음.
