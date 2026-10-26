# 질의: PC 차트 배포(627b136) 2-0 정지선과 verifier 대조를 마쳤고, 2-1~2-5 실행에 착수하려 합니다

**지금 단계:** 리뷰 (배포 실행 직전)
**다음에 하려는 일:** 요청서 `docs/specs/v2-dashboard/deploy-request-20261026-pc-chart.md` 2-1~2-5 순서대로 P1(`git pull --ff-only`, 5367334 → 627b136)·P2(`systemctl restart tradebot-v2` 만)·P3(점검: check_v2_unit.sh, RSS, curl 응답 머리, 세션 없는 API, `__v2toPC` 0)·P4(운영자 강력 새로고침 확인 요청)·30분 관찰을 SSH 로 실행합니다. 엔진(`tradebot`) 재시작 없음, `deploy-tradebot` 쓰지 않음. 멈춤 조건이 하나라도 나오면 그 자리에서 멈추고 3절 1(버튼 숨김) 뒤 보고합니다. 사용자 결정 1026-14(1 한 번에, 2 A′ 수정본 초안대로, 3 새 세션)에 따른 실행이며 이 세션이 그 새 세션입니다. 이 질의서는 배포 완료 보고 문서 커밋에 함께 넣습니다(문서 묶음). 저장소에 `.claude/hooks/` 가 없어 훅 차단 대상 명령은 없습니다(커밋·push 는 이번 단계에 없음).

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 로컬 HEAD = origin/main = 627b136, 추적 변경 M HANDOFF.md 1건(HANDOFF 0절이 정상이라고 명시, 요청서 2-0 「추적 변경 0」 문구와는 다름) | `git rev-parse HEAD origin/main`, `git status --short` (10/26 17:2x) |
| 2 | diff 5367334..627b136 32개, 엔진 경로 0, v2·tests·docs 밖은 pages/dashboard.py 하나이며 495줄 버전 줄만 바뀜 | `git diff --name-only`, verifier 2a~2c |
| 3 | 서버 HEAD 5367334, dashboard.py:495 v1.2026.10.25.2058, tradebot active·00:25:22·NRestarts 0, tradebot-v2 active 00:24:59, .v2_allowlist 8바이트, 미추적 5건, tornado 6.5.1, users mcmax33\|0 | SSH 읽기 전용 17:25, verifier 3a~3g |
| 4 | 비밀 파일 5개 600 root, 사본 0, 루트 200·/v2/ 401 | SSH 17:25, verifier 4·5 |
| 5 | 기준선 1시간: tradebot grep 1건은 16:48:11 `INFO … Bar#429` (봉 번호가 `\b429\b` 에 걸림, 오류 아님), tradebot-v2 ERROR·Traceback 0 | journalctl grep 원문, verifier 6a·6b |
| 6 | 2-3 기대값(FAIL 0·탐침 10줄, no-cache, 304, 401, 403 forbidden_origin, Origin 붙이면 401, `__v2toPC` 0)이 627b136 코드와 맞음 | verifier 7a~7h (v2/handlers.py:30-35·78·134-141, server.py:17, check_v2_unit.sh:29) |
| 7 | `git fetch --dry-run` 기준 서버 5367334..627b136 fast-forward 가능 | verifier 3 |
| 8 | verifier 결론 「2-1 착수 가능」, 반박 0, 지적 4(Fable 질의 필요·요청서 「추적 변경 0」 문구 차이·`\b429\b` 봉 번호 오탐·구버전 화면 반영 시점 미확인 — 모두 차단 아님) | verifier 보고(이 세션) |
| 9 | 요청서 자체에 대한 Fable 판정 「수정 후 진행」 → 막음 2건 반영 완료 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-26-pc-chart-deploy-request-1.md |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 2-0 정지선이 기재와 같으므로(로컬 HANDOFF M 1건은 HANDOFF 0절이 정상으로 명시) 2-1~2-5 실행에 착수해도 되는가 | 착수 가능. 멈춤 조건은 요청서대로 적용 |
| 2 | 2-5 관찰에서 `\b429\b` 에 걸린 줄은 원문을 열어 HTTP 429 인지 봉 번호인지 판정하는 것이 맞는가 | 맞음. 판정 근거 줄을 보고에 적음 |
| 3 | 구버전 화면 버전은 실제 화면에서 보이는 값을 운영자 확인(2-4)으로 받아 보고에 적는 것이 맞는가(요청서는 2058 유지 예상) | 맞음. 예상과 다르면 차이만 기록, 매매 영향 없음 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261026-pc-chart.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (0절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-26-pc-chart-deploy-request-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: PC 차트 배포(627b136) 2-0 정지선과 verifier 대조를 마쳤고, 2-1~2-5 실행에 착수하려 합니다

**판정:** 진행
**이유:** 질의서의 사실 1~7을 17:29 KST에 로컬·서버(SSH 읽기 전용)·코드에서 직접 다시 재었고 모두 기재와 같았습니다. 사용자 결정 1026-14와 프로젝트 규칙에 맞고, 남은 지적은 권고뿐입니다.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 2-1~2-5 착수 가능 여부 | 됩니다. HANDOFF M 1건은 HANDOFF 0절이 정상으로 명시, 완료 보고에 차이로 적기 | 높음 |
| 2 | `\b429\b` 걸린 줄 원문 판정 | 맞습니다. 현재 1건은 Bar#429 INFO 줄 | 높음 |
| 3 | 구버전 화면 버전은 운영자 확인값으로 | 맞습니다. 파일 1209 / 화면(운영자 확인값) 따로 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인하는지 |
|---|---|---|---|---|
| 1 | 권고 | 완료 보고 2-0 절에 HANDOFF M 1건 차이 한 줄 | 멈추지 않은 근거 | 보고 문서 |
| 2 | 권고 | `grep -c '__v2toPC'` 단독 실행(전부 0이면 종료 코드 1) | 오판 방지 | 출력 0 3줄 |
| 3 | 권고 | 2-2 뒤·2-5 끝에 ExecMainStartTimestamp·NRestarts 둘 다 | 엔진 재시작 없음 근거 | 00:25:22·0 |
| 4 | 권고 | 2-5 에 `HTTP.*429\|status.*429\|Too Many` 보조 검색 | 오탐과 실제 한도 구분 | 0건 |

## 사용자에게 물어야 할 것
- 없음
