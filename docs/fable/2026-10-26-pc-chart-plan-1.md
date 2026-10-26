# 질의: PC 차트 확대 계획서(1026-09)를 verifier 2회로 확정했고, 사용자에게 계획 승인을 요청하려 합니다

**지금 단계:** 계획 (사용자 계획 승인 요청 직전)
**다음에 하려는 일:** 계획서를 사용자에게 올리고 「계획 승인」을 받습니다. 승인되면 계획서를 저장소 `docs/specs/v2-dashboard/plan-pc-chart-20261026.md` 로 옮기고 구현(F1~F13)·로컬 실측을 진행한 뒤, verifier·Fable 을 거쳐 커밋·push 승인을 따로 요청합니다. 계획서 파일 쓰기는 구현 커밋에 함께 넣습니다(문서 묶음). 이 질의는 사실·실현 가능성·위험만 봅니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | 사용자 결정 1026-08: 1 가(PC 도 모바일 화면, 차트 탭만 넓게), 2 200, 3 같이(1025-17 Cache-Control), 1026-04 보류 | HANDOFF.md 0-1 1026-08 행, 사용자 메시지 |
| 2 | 계획서 F1~F13 파일·줄 주장 모두 확인됨(verifier 1차 27항목, 반박 2 → 수정) | verifier 1차 보고(이 세션) |
| 3 | verifier 재검증: 지적 1~7 해소, 새 오류 0, 「계획 승인 요청 가능」. 개선 2건(예약 높이 이중 차감, 낮은 창 스크롤)도 반영 | verifier 2차 보고, 계획서 1절 높이 문단 |
| 4 | 제안 때 「Python 변경 0」이라 했으나 3 「같이」로 `v2/handlers.py` 몇 줄(F7)이 생김. 엔진 파일 0, 배포는 tradebot-v2 재시작만 | 계획서 1절, deploy/tradebot-v2.service |
| 5 | tornado 6.5.1: get_cache_time>0 일 때만 Cache-Control 덮어씀, 304 에도 Cache-Control 남음 | verifier(web.py:1961·2768·2869-2876·3122) |
| 6 | 넘김 삭제로 깨지는 다른 시험은 basic.test.mjs 범위뿐, test_static_lint 백테스터 링크 시험은 계속 통과 | verifier grep |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 계획서가 결정 1026-08·사용자 요구(모바일 그대로)를 충족하고 실현 가능한가 | 됨 |
| 2 | 위험: 매매·엔진·서버 IP 업비트 한도에 닿는 것이 없는가 | 없음 |
| 3 | PO 판단 3건(백테스터→홈 단추 안 넣음, 높이 기준 「세로 스크롤 0」, get_cache_time 0)을 사용자에게 「PO 판단」으로 밝히고 승인받는 방식이 맞는가 | 맞음 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/8c1177c3-33d3-415d-8295-8ecd93eec815/scratchpad/pcchart/plan-pc-chart-20261026.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-26-pc-chart-proposal-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/index.html, app.js, basic.js, chart.js, style.css, basic.css
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/handlers.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/v2/js/basic.test.mjs
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1: PC 차트 확대 계획서(1026-09)를 verifier 2회로 확정했고, 사용자에게 계획 승인을 요청하려 합니다

**판정:** 수정 후 진행
**이유:** 사실 1~6 과 F1~F13 은 코드로 확인됐고 매매·엔진·업비트 한도 위험은 없습니다. 다만 F2 높이 측정이 `getBoundingClientRect().top` 을 그대로 써 문서가 스크롤된 상태에서 높이를 과대 계산해 「세로 스크롤 0」을 어길 수 있습니다.

## 고쳐야 할 것 (요지)
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 막음 | 위치를 문서 기준 `rect.top + window.scrollY` 로(또는 재기 전 scrollTo(0,0)), 실측에 「홈 끝까지 내린 뒤 차트」·「창 높이 500→900」 추가 |
| 2 | 권고 | `.bottom` 에 `right:auto` |
| 3 | 권고 | F10 304 는 If-None-Match |
| 4 | 권고 | 정적 경로 index.html 404 덧붙임 |
| 5 | 권고 | 서버 tornado 버전은 배포 요청서에서 확인 |

(질문 답: 1 충족·실현 가능(측정식 보정 전제), 2 위험 없음, 3 PO 판단 3건 밝혀 승인받는 방식 맞음. 미확인: 서버 tornado 버전, verifier 원문.)

→ PO 반영: 1~5 모두 계획서에 반영. 2회째 질의입니다.

---

# 답변 2: PC 차트 확대 계획서(1026-09)를 verifier 2회로 확정했고, 사용자에게 계획 승인을 요청하려 합니다

**판정:** 진행
**이유:** 답변 1 의 1~5 가 모두 반영됐고(1절 높이 문단·F5·F7·F10·3절·4절 실측), 파일·줄·동작 주장을 다시 대조해 새 사실 오류가 없습니다. 남은 것은 권고 1건입니다.

(추가 확인: nginx `deploy/nginx-v2-location.conf` 에 expires·proxy_cache 없음 → Cache-Control 덮어쓰기 없음. test_static_lint:109 계속 통과. 미확인: 게이트 350/350 은 구현 뒤 실측, 서버 tornado 버전은 배포 요청서에서.)

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | F2 의 641px 판정을 `matchMedia("(min-width: 641px)")` 로, 실측에 640↔641 경계 1항목 |

## 사용자에게 물어야 할 것
- 없음

→ PO 반영: 권고 1 계획서 반영.
