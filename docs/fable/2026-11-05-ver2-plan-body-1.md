# 질의: Ver2 반영 계획서 본문(3판)을 마쳤고, 사용자에게 계획 승인을 요청하려 합니다

**지금 단계:** 계획 (본문 승인 요청 직전)
**다음에 하려는 일:** 계획서 `docs/plans/2026-11-05-ver2-backtester/plan.md` 3판을 사용자에게 올려 승인을 받습니다. 승인되면 이번 단계의 문서(계획서 · HANDOFF · investor-notice-log #9 · 질문 PDF/html · Fable 질의 파일 3개)를 한 커밋으로 올리고(문서만 — 버전 갱신 없음, 커밋 전 비밀값 검사), 1단계(백테스터 로컬 구현)를 시작합니다. 작은 문서 변경은 이 질의에 묶었습니다.

**검증 이력:** verifier 1회째 「고친 뒤 재검증」(반박 6 · 지적 10) → 2판 → 2회째 「고친 뒤 재검증」(꼭 고칠 것 4 · 권고 5) → 3판 → 3회째 「사용자 보고 가능」(꼭 고칠 것 없음, 권고 5건 반영). 반영 내역은 계획서 9·10절.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 결정 1105-06 ①~⑤: 목차 승인 · 옛 200선 값 버림 · 건너뜀 횟수는 실제로 건너뛴 것만 · 업비트 90일 · 비교 결과 투자자 발송 | 확인 | 사용자 메시지 11/05 「1105-06 ①~⑤ 권고대로」 |
| 2 | 목차 2판은 Fable 2회째 「진행」 | 확인 | docs/fable/2026-11-05-ver2-plan-outline-1.md |
| 3 | 백업: 태그 pre-ver2-20261105 → 35f14e5(원격 `^{}` 같음), 압축본 5,730,111 바이트 · 991 파일 | 확인 | git ls-remote, verifier 1회째 판정 28 |
| 4 | 계획서 본문이 목차에서 바뀐 큰 점 3가지(8절 A·B·C): 연속 손절 수·중단 끝 시각은 엔진 칸(재생 밖) / 90일은 사용자 요청만, 미리 받기 30일, 보관은 마지막 사용자 요청 기간 / 바뀌는 점 안내는 배포 전 비교 PDF 와 함께 | 확인(verifier 지적에서 나옴) | plan.md 8절, 질문 PDF html:78 |
| 5 | 목차에 없던 새 칸 1개 「이 거래 순번」(보유 중 tp 바꿀 때 TP 다시 계산용) → pullback_state 새 칸 5개 | 확인 | plan.md 2-2·2-3·2-3′ |
| 6 | 투자자 그림 두 장의 60선 최소 기울기는 −0.05, 다른 칸은 눌림목 기준선 60/120 만 다름. 그림 1: 160거래·63.125%·59.462%, 그림 2: 150거래·66.667%·84.950% | 확인(PO 그림 1 직접 봄, verifier 두 장 대조) | docs/new-version/20261105-ver2-test-01.png·-02.png |
| 7 | 투자자가 말한 「바이낸스 +6.6%」는 두 그림 수치와 다름 — 어느 설정 값인지 모름 | 추정(다른 조건의 실행일 수 있음) | 1-5 보고에서 밝히기로 함 |
| 8 | 서버 PULLBACK 설정 파일 수 | 추정(확인 못 함 — 자동 모드가 SSH 읽기 막음) | 배포 요청서 단계에서 사용자 `!` 명령으로 셈 |
| 9 | 1분봉 90일 수집 시간 약 4.3분, 파일 크기·v2 메모리 | 추정 | 1-3′ 로컬 실측으로 확인 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 8절 A·B·C 는 승인된 목차에서 바뀐 것이다. 사용자 결정으로 올려야 하는가, 계획 승인 때 함께 확인받으면 되는가 | 함께 확인. A·B 는 내부 설계, C 는 투자자 약속을 지키는 쪽이라 결정 ⑤ 범위 안 |
| 2 | 2-3 칸 배치(엔진 칸 2 · 전략 칸 3)와 재생에 중단 끝 시각을 읽기 전용으로 넘기는 방식에 빈틈이 있는가 | verifier 3회 통과 |
| 3 | 1-3′ 보관 기간 방식(파일 머리 정보에 마지막 사용자 요청 기간, 7일 뒤 30일 복귀, 30MB 는 받기 전 판단)이 엔진과 같은 IP 한도에 위험을 더하는가 | 미리 받기는 30일 그대로라 평소 부하는 같음. 사용자 90일 요청 때만 늘어남 |
| 4 | 강제 매수를 매수 중단 중에도 허용하는 것이 맞는가 | 사용자의 직접 개입이므로 허용 + 로그 |
| 5 | 빠진 영향 범위가 있는가 | — |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-05-ver2-backtester/plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-05-ver2-plan-outline-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/MA_GC_Pullback_Backtester_2611051030(Ver2).html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/investor-questions-20261105.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_pullback.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_engine.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/live_loop.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/pullback_apply.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/services/pullback_state.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/candles.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/bt_ui.js

---

# 답변 (Fable 1회째, 11/05)

**판정:** 수정 후 진행
**이유:** 인용 코드 줄은 모두 맞고 결론을 뒤집는 오류는 없음. 재생에 끝 시각만 넘기면 중단 시작 전 봉까지 막혀 JS 와 어긋남(막음 1). 저장 파일 키 수는 25 가 아니라 24(막음 2).
- 질문 1: 계획 승인 때 함께 확인하면 됨(높음). 8절에 D(강제 매수 허용) 추가 권고.
- 질문 2: 칸 배치는 맞음. 「중단 시작 시각」을 두고 시작 ≤ 봉 시각 < 끝 일 때만 막아야 함(높음).
- 질문 3: 초당 부하는 같고 한 작업 길이만 3배. 1-5 비교는 3분봉만, 1분봉 90일은 실측 1회로(보통).
- 질문 4: 허용이 맞음. 응답·화면에 중단 중 표시 필요(높음).
- 질문 5: 빠진 것 — 중단·상승폭 감사 사유와 문구, v2 화면 중단 표시, api_read PARAM 이름표, 기대값 파일 3개(높음).
- 권고 3~10: 새 사유 SL_PAUSE·GC_GAP, v2 화면 표시, 6절 재생 순번 위험, 미리 받기 `_evict`, 「최소 4.3분」·3분봉만, 새 8칸 적용 분류, 1-4 파일, 8-D.
- 사용자에게 물어야 할 것: 없음.

**PO 반영(계획서 4판 11절):** 막음 1 → 엔진 칸 「중단 시작 시각」 추가, 새 칸 5 → 6, 2-2·2-3 조건 「시작 ≤ 봉 시각 < 끝」. 막음 2 → 2-5 「24키」. 권고 3~10 → 2-6 · 6절 · 1-3′ · 1-5 · 2-3′ · 1-4 · 8-D.

# 다시 묻기 (2회째)
**물어볼 것:** 막음 1·2 와 권고 3~10 을 계획서 4판 11절대로 반영했습니다. 사용자에게 계획 승인을 요청해도 되는가.

---

# 답변 (Fable 2회째, 11/05)

**판정:** 진행
**이유:** 막음 1·2 와 권고 3~10 이 인용한 자리(plan.md 127·128·134·136·142·168·174·175·89·91·158·97줄, 6절, 8-D)에 모두 들어감. 남은 것은 권고 3건.
- 권고 1: 6절 첫 행·8-A 에 「중단 시작 시각」 더하기. 권고 2: 1-4 새 시험에 「재생에서 중단 시작 전 봉은 막지 않음」. 권고 3: 8절 순서 A·B·C·D.
- 사용자에게 물어야 할 것: 없음(8절 A~D 는 계획 승인 때 함께 확인).

**PO 반영:** 권고 1~3 모두 plan.md 에 반영함(다시 묻지 않음 — 권고만 남음).
