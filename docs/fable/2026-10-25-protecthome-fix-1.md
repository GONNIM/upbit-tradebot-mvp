# 질의: ProtectHome=read-only 수정 구현과 verifier 검증을 마쳤고, 사용자에게 커밋·push·서버 반영 승인을 요청하려 합니다

**지금 단계:** 구현 (검수)
**다음에 하려는 일:** 사용자에게 1025-12 로 「커밋·push·서버 반영(신버전만 재시작)」 승인을 요청합니다. 승인 뒤에는 파일을 지정해 add → commit → `git status` 확인 → push 합니다. 서버 반영 직전에는 따로 Fable 실행 질의를 합니다. 이번 커밋에는 deploy-request·deploy-exec-1·deploy-stop-1·HANDOFF 를 넣지 않습니다. 이 문서들은 배포 완료 보고 커밋에 넣습니다. 이 질의서도 그 커밋에 넣습니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 결정 1025-11「1 가, 2 가」: ProtectHome=read-only 로 고쳐 이어서 배포하고, 엔진은 재시작하지 않음 | 사용자 메시지 (10/25 17시대), /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-stop-1.md |
| 2 | 커밋 대상 6개: deploy/tradebot-v2.service(ProtectHome=read-only + 주석), scripts/v2/check_v2_unit.sh(:46 읽기, :55 판정, :68 전달), tests/v2/test_deploy_files.py(required 에 ProtectHome, prop 목록, assertIn 2개, [Service] 지시어 중복 금지 단언), docs/specs/v2-dashboard/spec.md:78 E18, docs/operations/v2-runbook.md:113, pages/dashboard.py:495 1611→1729. 엔진 경로 0 | `git diff` |
| 3 | 게이트 exit 0, tests/v2 190 OK, JS 시험 통과, 회귀 350/350 (지시어 중복 단언 추가 뒤 재실행) | /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/fcb8d941-5702-48ea-a05a-591030fe5f4d/scratchpad/gate2.log |
| 4 | verifier: 반박 0, 「커밋 승인 요청 가능」. 변이 시험 M1~M5 를 시험이 잡음. M6(뒤에 ProtectHome=no 추가)은 빈틈이었고 → PO 가 지시어 중복 단언을 추가해 변이 사본에서 FAIL 확인 | verifier 보고, scratchpad/mut6 |
| 5 | systemd v249.11 원본: ProtectHome read-only 표 /root READONLY(148-152), strict 표 /root READWRITE_IMPLICIT(211-217), READONLY 우선(61·68·644), 더 깊은 ReadWritePaths·InaccessiblePaths 는 deny_list 로 유지(1673-1682), systemd-run 이 ProtectHome 속성을 받음(bus-unit-util.c:920) | verifier 4a, scratchpad/ns249.c·bu249.c |
| 6 | v2 쓰기는 api_write.py:28,69(PULLBACK)·db.py:98-106(services/data v2hist)뿐. pyc 쓰기 실패는 Python 이 조용히 넘김(서버 _bootstrap_external.py:1216-1243) | verifier 4b·4c |
| 7 | verifier 지적 4(pyc 문구 부정확) → 주석·runbook 을 「기존 pyc 는 읽고, 바뀐 모듈은 메모리 컴파일」로 고침 | git diff |
| 8 | verifier 지적 1: 엔진을 재시작하지 않으면 화면 버전이 1611 로 고정된다고 보장할 수 없음(Streamlit script_cache — 재시작 뒤 대시보드를 처음 그린 시점의 파일 기준). 보고에는 「파일 1729 / 엔진 실행 코드 12ddb4f 그대로 / 화면은 1611 또는 1729(동작 같음) / 다음 재시작 때 1729 확정」으로 적음 | verifier 5b |
| 9 | verifier 지적 3: 이번 수정만 되돌리는 절차 → 반영 단계에 「문제 시 `systemctl disable --now tradebot-v2`(엔진 영향 없음), 이어서 요청서 2-10」을 적음 | 승인 요청 본문 |
| 10 | 서버 반영 절차: pull --ff-only(12ddb4f → 새 커밋) → 유닛 cp → daemon-reload → restart tradebot-v2 → tradebot ExecMainStartTimestamp 17:10:35·NRestarts 0 확인 → D5 전체(check FAIL 0·PASS root-readonly·unit-props, a3, RSS, A2, EXPLAIN 8) → D6~D8. tradebot·tradebot-v2 의존 관계 없음, NeedDaemonReload 전부 no | verifier 5a·5c |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 구현이 사용자 결정·Fable 답변 1 막음 1·권고 2~6 을 충족하고, 사용자에게 커밋·push·서버 반영 승인을 요청해도 되는가 | 됨 |
| 2 | HANDOFF·요청서·이전 질의서를 이번 커밋에서 빼고 배포 완료 보고 커밋에 넣는 것이 맞는가 | 맞음(요청서 「배포 완료 보고와 함께 커밋」) |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/deploy/tradebot-v2.service
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit.sh
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/v2/test_deploy_files.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-stop-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: ProtectHome=read-only 수정 구현과 verifier 검증을 마쳤고, 사용자에게 커밋·push·서버 반영 승인을 요청하려 합니다

**판정:** 진행
**이유:** 사실 2~7·9·10 은 로컬 diff·시험 재실행·scratchpad 원본·서버 읽기 전용 SSH 로 직접 확인했고 기재와 일치. 남은 지적은 모두 권고.

(직접 확인 요지: diff 6개·엔진·v2 코드 변경 0, tests/v2 190 OK 재실행, gate2.log JS·350/350, mut6 중복 단언 FAIL, ns249.c·bu249.c 대조, v2 쓰기 호출 api_write.py·db.py 뿐, 서버 12ddb4f·1611·tradebot 17:10:35 NRestarts 0·v2 ProtectHome=no·의존 관계 없음·NeedDaemonReload no·설치 유닛 = 옛 저장소 판·nginx /v2/ 0·.v2_allowlist 없음. 사실 1 은 HANDOFF 기록으로, 사실 4 는 결과물로 간접 확인.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 승인 요청 가능 | 됨. 막음 1·권고 3~6 충족, 권고 2 는 결정 단계 것. 쓰기 경로 실증은 서버 D5 에서 | 높음 |
| 2 | 문서는 배포 완료 보고 커밋에 | 맞음(요청서 4·215행, HANDOFF 7판 보완) | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 권고 | 커밋 메시지·승인 요청·보고에 「1611 → 1729」 | 배포 보고 규칙 | git log -1 |
| 2 | 권고 | 반영 전 check 를 돌리면 FAIL unit-props 가 정상임을 적기 | 순서 혼동 방지 | 본문 |
| 3 | 권고 | git add 6개 이름 지정, status 확인 뒤 push | push 전 스테이징 규칙 | git status |
| 4 | 권고 | 서버 미추적 5개는 원래 있고 ff 에 영향 없음 한 줄 | 정지선 혼동 방지 | 서버 git status |

## 사용자에게 물어야 할 것
- 없음

## PO 처리
- 권고 1~4 를 승인 요청·커밋 절차·반영 보고에 반영. 사용자에게 1025-12 승인 요청.
