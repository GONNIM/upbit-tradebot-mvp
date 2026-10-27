# 질의: 사용자 지시 4건(홈 그림·잠김/기록 시각·매매 중지/로그아웃·업비트 30일 1분 이내)에 맞춘 재제안을 마쳤고, 사용자에게 결정 요청으로 올리려 함

**지금 단계:** 계획 (결정 요청 — 사실·실현 가능성·위험만 확인)
**다음에 하려는 일:** 재제안서(아래 참고 파일)의 A(홈)·B(백테스터 서버 중계 + 보관, 권고 ③)를 사용자에게 결정 요청으로 올린다. 승인되면 plan-proposal-match-20261026.md 를 고쳐 verifier → Fable 을 다시 받는다. 이번 단계에서 저장소에 쓰는 파일은 이 질의 파일 하나뿐이며 커밋·push·배포·서버 변경은 없다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | Origin 머리가 붙은 업비트 요청은 `group=origin`, 2회째부터 429 | curl 5회 실측(PO), verifier curl 3회 재현 |
| 2 | Origin 없이 초당 5회로 1분봉 30일치 = 216회·43,200봉·429 0건·44.1초 | scratchpad fetch30d.py 실행 출력, verifier 재현 44.0초 |
| 3 | 공식 FAQ: Origin 포함 시 10초당 1회, 프록시 서버 구성 권고 | verifier context7 docs.upbit.com/kr/docs/faq-api |
| 4 | 브라우저 직접 방식 36분 근거 타당(216×10초) | 위 1·3 |
| 5 | 엔진·구버전 대시보드·v2 가 같은 서버 IP. 시세 그룹 IP 단위 초당 10회 | spec.md 47행 D8, pages/dashboard.py 795·2802행 |
| 6 | 엔진 7일 `[REST] … 응답 없음` 0건·TooMany 0건, 봉 미반영 재시도 11,184건 | verifier 서버 journalctl(읽기 전용) |
| 7 | 엔진에 429·418 처리 없음, pyupbit 가 429 를 삼켜 None | grep 0건, 서버 pyupbit errors.py 183-187·quotation_api.py |
| 8 | tradebot-v2 유닛에 바깥 네트워크 차단 없음, services/data 쓰기 허용, UMask 0077 | 서버 systemctl show/cat tradebot-v2 |
| 9 | v2 지금 업비트 호출 경로 0, 시험 2곳이 고정 | v2/*.py grep, tests/v2/test_basic_pause.py 525-532, test_server.py 230-244 |
| 10 | candle_cache 표는 서버 DB 4개 모두 없음(10/22) — 대안 ⑤ 제외 | review-20261022-outline-v2.md 17행 F6, spec.md 145행 |
| 11 | pause·logout 서버 경로 재사용 가능, 서버 변경 없음 | v2/api_write.py 169-203행 |
| 12 | verifier 1회: 「고칠 것 있음」 11건 → 전부 재제안서에 반영 | 이 세션 verifier 보고(측정 방법 정정·Streamlit 몫·비동기·409·압축·경로 검사·sec 잔량 등) |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 권고 ③(서버 중계 + 보관)이 실매매(엔진 시세 조회)에 주는 위험이 상한·`sec` 잔량 확인·429 즉시 멈춤·동시 1건·미리 받기 지연으로 충분히 낮은가 | 낮다고 봄. verifier 는 초당 2~3회를 권했으나 그러면 첫 실행 약 110초로 사용자 지시 「1분 이내」를 못 지킴. 초당 5회 + sec≤4 쉬기로 제안 |
| 2 | D8(10/22 운영자 결정) 변경을 사용자에게 결정 항목으로 묻는 것이 맞는가 | 맞음. 사용자 「기존 요구사항 모두 폐기」 지시가 있었으나 D8 은 안전 제약이라 명시적으로 묻는다 |
| 3 | A(홈) 배치가 그림 2-가를 따르면서 지시 2·3 을 지키는가, 빠진 사실이 있는가 | 지킴. 매매 중지 단추는 배지 줄 아래 top-level(project-rules 1-B) |
| 4 | 결정 요청에 빠진 사실·위험이 있는가(예: 418 차단이 주문 API 까지 미치는지 미확인) | 미확인으로 명시해 올린다 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/e1c17aff-d11f-4e52-bd3f-aedba9d389d8/scratchpad/proposal-home-backtester-20261026.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/e1c17aff-d11f-4e52-bd3f-aedba9d389d8/scratchpad/fetch30d.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-proposal-match-20261026.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-approval-20261021-v2.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/index.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/basic.js
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 전문 (2026-10-26 21시대, Agent model: fable)

**판정:** 진행
**이유:** 확인한 사실 12건 중 11건을 1차 근거로 다시 확인했고 반박된 것이 없습니다(12번은 verifier 원문을 받지 못해 미확인). 고쳐야 할 것은 모두 권고입니다.

### 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | ③ 실매매 위험이 충분히 낮은가 | 낮음. 공유 한도는 `candle` 그룹뿐이고 엔진 현재가·호가는 영향 밖. 엔진 캔들 호출은 평시 분당 1~2회. `sec≤4 쉬기`는 IP 공유 잔량을 읽음. 남는 위험은 같은 1초에 겹쳐 엔진이 429 1회 → pyupbit None → 기존 「봉 미반영 재시도」 경로. 워밍업 중 None 처리는 확인 안 함 | 보통 |
| 2 | D8 변경을 결정 항목으로 묻는가 | 맞음. 안전 제약이고 실매매 영향 범위 | 높음 |
| 3 | 홈 배치가 그림·지시 2·3 을 지키는가 | 지킴. 매매 중지 단추 top-level 은 project-rules 1-B 와 맞음. 계획서 29·30행 수정 누락 1건 | 높음 |
| 4 | 빠진 사실·위험 | 418 은 IP·Pocket·Connection 단위, 같은 IP 주문 API 동반 차단은 문서에 명시 없음(미확인 표기 맞음). v2 가 먼저 떠 있고 엔진이 나중에 재시작하는 경우 미리 받기 조건이 덮지 못함 | 높음 |

### 고쳐야 할 것 (모두 권고 — PO 반영 완료)
1. 「시세 그룹」 → `candle` 그룹, `ticker`·`orderbook` 별도 그룹 명시.
2. 계획서 29·30행을 바뀌는 곳 목록에 추가.
3. 생존 파일 `pid` 가 바뀌면 5분간 수집 쉬기.
4. 봉 미반영 재시도 건수에 조회 시각 붙이기(재조회 12,046건).
5. 「1분 이내」 조건(엔진 종목 수 초, 다른 종목 약 44~55초 + 계산, 겹치면 늘어남)을 요약에서 빼지 않기.

### 사용자에게 물어야 할 것
- 없음
