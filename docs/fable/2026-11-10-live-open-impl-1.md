# 질의: 눌림목 실계좌 열기 구현과 내부 시험을 마쳤고, 사용자에게 커밋·배포 승인을 요청하려 합니다

**지금 단계:** 구현·테스트 끝
**다음에 하려는 일:** 사용자에게 구현 결과와 투자자 메뉴얼을 보고하고 커밋·push·배포 승인을 함께 요청합니다. 승인되면 dashboard 버전 갱신 → 묶음 커밋 1회 → push(게이트) → 표준 정지선 → 실행 직전 질의 → 배포(미보유 때, tradebot·tradebot-v2 재시작) 순서입니다. 커밋 범위에 축소안 관련 문서와 시험 포함.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 구현은 축소안 범위. 운영 코드 18개 수정 + 신규 2개(engine/active_mode.py, core/bounded_call.py). 스키마 변경 없음(services/init_db.py diff 0줄) | 확인 | git status, git diff --stat |
| 2 | 게이트 전체 통과: 회귀 1444/1444, v2 458, JS 191, 바깥 연결 0, 종료 코드 0 | 확인(verifier 11/10 직접 실행) | scratchpad gate3.log |
| 3 | verifier 3회째 「사용자 보고 가능」. 이전 지적 1·2·3·5·12 수정 유지, 지적 11 먼지 허용은 새 상태 사고로 되돌림 | 확인 | verifier-impl-1.md, 재검증 2·3회째 |
| 4 | 화면 실측: 412·360·1440, LIVE·TEST 통과(헤드리스 Chrome, 가짜 자료). 그 뒤 바뀐 확인 문구·강제 매수 금액은 시험으로만 확인, 눈으로는 미실측 | 확인 | scratchpad/ui-check |
| 5 | 서버 로그 10/20 이후 시장가 매수(bid/price) 응답 0건. 시장가 매도 136줄 있음 → 투자자 첫 주문이 시장가 매수의 첫 실제 응답 | 확인(구현자 SSH 읽기) | 구현 보고 |
| 6 | 잔량 1e-6 이상이면 실계좌 전환·복귀 거절. 팔 수 없는 작은 잔량이 있으면 앱에서 정리 필요 | 확인 | engine/strategy_switch.py:52,473,482 |
| 7 | 남은 위험: 일부 잔고 조회에 시간 상한 없음(EMA 와 같은 수준), boot_resume 이 일부 부팅 실패를 성공으로 알림 | 확인 | verifier 지적 7·8 |
| 8 | 11/09 새벽 잔고 조회 실패 원인 미확인, 배포 전 확인 예정 | 추정 | 서버 로그 |
| 9 | 메뉴얼 A4 1쪽, 나눔고딕 포함, 렌더 확인 | 확인 | docs/new-version/pullback-live-manual-20261110.pdf, pdffonts |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 이 상태로 커밋·배포 승인을 요청해도 되는가. 축소안 범위·프로젝트 규칙과 어긋나거나 실제 돈 사고가 남는가 | 된다고 봄 |
| 2 | 시장가 매수 첫 관측이 투자자 첫 주문인 점, 작은 비율 시작 권고로 충분한가 | 사용자 지시로 실측 제외. 고지·첫 거래 로그 확인으로 충분 |
| 3 | 메뉴얼 내용에 실제 동작과 다른 곳이 있는가 | 없다고 봄 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-09-live-open-minimal-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/pullback-live-manual-20261110.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/strategy_switch.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_engine.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/save.js

---

# 답변 요지 (Fable, 원문의 판정·지적을 PO 가 옮겨 적음)

**판정:** 진행
**이유:** 미커밋 변경을 직접 읽었고, 실제 돈이 나가는 경로에서 이중 매수나 보유분 방치로 이어지는 빈틈 없음. 축소안 6개 작업·M1~M5·앞선 권고가 코드에 있음. 지적은 권고 5건.

- 권고 1·2 (보고에 반영): 표식 LIVE + 엔진 꺼짐 때 잔고 표 묵음, 부팅 재시도 약 160초와 준비 대기 180초 근접.
- 권고 3~5 (메뉴얼 반영 끝): 계산식 수수료 표기, 실계좌 복리 미사용, 알림 두 줄 추가.
- 첫 주문 시각에 journal 의 [UPBIT-ORDER]·[SPLIT-FILL] 줄을 읽어 업비트 앱과 대조. 읽기가 막히면 사용자 ! 실행.
