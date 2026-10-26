# 질의: PC 차트 배포 요청서(627b136, tradebot-v2 재시작만)를 verifier 2회로 확정했고, 사용자에게 배포 승인을 요청하려 합니다

**지금 단계:** 리뷰 (배포 승인 요청 직전 — 사실·실현 가능성·위험)
**다음에 하려는 일:** 요청서 `docs/specs/v2-dashboard/deploy-request-20261026-pc-chart.md` 를 사용자에게 올려 「P1~P4 한 번에」·「A′ 수정본」 결정을 받습니다. 승인되면 이 세션에서 SSH 로 2-0~2-5 를 실행합니다(엔진 재시작 없음 — 새 세션 불필요로 판단). 요청서·이 질의서는 배포 완료 보고 문서 커밋에 넣습니다(별도 승인). 실행 직전에 따로 질의하지 않고 이 질의로 갈음할지도 묻습니다(배포 = 되돌리기 어려운 일 → 규칙상 실행 직전 질의).

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | 로컬 HEAD = origin/main = 627b136(v1.2026.10.26.1209), push 때 350/350 | `git rev-parse`, push 출력 |
| 2 | 서버 HEAD 5367334·2058, tradebot 00:25:22 NRestarts 0, v2 00:24:59, allowlist 8바이트, 미추적 5, tornado 6.5.1, 비밀 파일 600·사본 0, 1시간 오류 0 | PO SSH 12:1x, verifier 1차(12:14) |
| 3 | diff 5367334..627b136 32개, 엔진 경로 0, 그 밖 pages/dashboard.py 버전 줄 1줄 | verifier 10~12 |
| 4 | 엔진 쪽 v2 import 0, 서버 Streamlit fileWatcherType none → 엔진 재시작 불필요, 화면 버전은 2058 유지 | verifier 14·15 |
| 5 | nginx 에 add_header·expires·proxy_cache 0 → no-cache 그대로 전달 | verifier 18 |
| 6 | verifier 1차 지적 8·반박 1(A′ 기재) → 반영 → 2차 「배포 승인 요청 가능」, 문구 1건(3번째 문장)도 고침 | verifier 2차 |
| 7 | 결정 1026-04(A′ 보류)·1026-08·1026-10·1026-12 | HANDOFF 0-1 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 배포 승인 요청으로 가도 되는가(사실·위험) | 됨 |
| 2 | 엔진 재시작이 없으므로 이 세션에서 실행해도 되는가 | 됨(이전 2회는 엔진 재시작이 있어 새 세션) |
| 3 | 사용자 승인 뒤 실행 직전 Fable 질의를 이 질의로 갈음해도 되는가(승인 사이 서버 값이 바뀌면 2-0 정지선에서 멈춤) | 갈음 가능. 2-0 을 실행 시점에 다시 재므로 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261026-pc-chart.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/impl-report-20261026-pc-chart.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025-2.md (이전 형식)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: PC 차트 배포 요청서(627b136, tradebot-v2 재시작만)를 verifier 2회로 확정했고, 사용자에게 배포 승인을 요청하려 합니다

**판정:** 수정 후 진행
**이유:** 사실(diff 범위·서버 상태·엔진 무영향·캐시 헤더)은 직접 다시 재어 모두 맞았습니다. 다만 (1) 배포는 새 세션을 사용자에게 권하라는 규칙(fable-rules.md:19)인데 「이 세션에서 실행」을 확정했고, (2) 실행 직전 질의(fable-rules.md:21)는 이 질의로 갈음할 수 없습니다.

(직접 확인 12:20: 로컬·서버 정지선 값 전부 기재와 같음, 엔진 쪽 v2 import 0, 유닛 의존 없음, /root/deploy.sh 는 조건 없는 엔진 재시작, Streamlit 감시 꺼짐으로 화면 2058 유지, tornado no-cache 200·304 유지, nginx 덮어쓰기 0, journal 1시간 오류 0. 미확인: verifier 원문, push 게이트 출력.)

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 막음 | 실행 세션을 6절 결정 항목으로(새 세션 권고 / 이 세션) |
| 2 | 막음 | 승인 뒤 2-0 재측정 → 실행 직전 질의 1회 → 2-1~ 을 요청서에 |
| 3 | 권고 | 기준선 `locked` → `database is locked`, 429·418 단어 경계 |
| 4 | 권고 | 「오류 0」 셈 문자열 명시 |
| 5 | 권고 | verifier 판정 원문을 완료 보고 때 파일로 |

## 사용자에게 물어야 할 것
- 실행 세션: 새 세션(권고) / 이 세션.

→ PO 반영: 1·2·3 반영(요청서 5행·24행·6절 3). 남은 것은 사용자 결정(실행 세션)뿐이라 규칙 [3]에 따라 다시 묻지 않고 사용자에게 올림. 4·5 는 실행 직전 질의·완료 보고에 반영.
