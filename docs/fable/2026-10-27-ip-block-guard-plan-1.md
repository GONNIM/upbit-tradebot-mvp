# 질의: 사용자 결정 1027-05 4 「IP 차단 발생하지 않는 방법으로 진행」을 계획서 Task 4-0b 로 설계했고, 구현(subagent)에 들어가려 함

**지금 단계:** 계획
**다음에 하려는 일:** Task 4-0b 를 실행 에이전트에게 맡겨 `v2/candles.py`·`tests/v2/test_candles.py`·runbook·spec 을 고치고(커밋 없음), Task 별 검수 → verifier → 배포 요청서 고침 → Fable → 사용자에게 코드 커밋·push 승인을 다시 받는다(1d0466a 뒤 코드가 바뀌므로 지난 커밋 승인은 넘어가지 않음). 묶은 문서 변경: 배포 요청서 6절 「사용자 결정 1027-05」 기록, 계획서 Task 4-0b 절(이미 작업 트리에 씀, 매매 영향 없음).

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 「1027-05 승인: 1 한 번에, 2 새 세션, 3 문안대로, 4 IP 차단 발생하지 않는 방법으로 진행하시오. , 5 문서 커밋 포함」(직전 「4 IP 차단 우회하시오」를 고친 문장) | 이 세션 사용자 메시지 |
| 2 | 엔진 캔들 호출 로그 분포(서버 60분, 3분 주기 안 초): 5s 53줄, 10~11s 139줄, 15~92s 5초 간격 1~4줄, 92s 뒤 0. **(Fable 1회 보정)** 15~92초의 5초 간격 줄은 HTTP 폴링 1회씩이고, 봉이 보이는 눈금에서 5회 묶음(0.4초 안)이 따라온다. 24시간 「다중 호출 시작」 오프셋: 5~11초 740, 15~16초 8, 20~92초 224(90~92초 156) — 창 −2~+15 는 묶음의 약 76% 만 덮음 | PO 60분 집계 + Fable 24시간 journal 집계 |
| 3 | 418 은 429 를 받고도 요청을 이어 갈 때 생김 — 저장소 spec D8 의 업비트 공식 rate-limits 인용이며, 이번에 원문은 다시 확인하지 않음 | spec.md D8, 직전 verifier·Fable 인용 |
| 4 | 지금 코드: USER_RATE 5, PREFETCH_RATE 1, sec≤4 → 1초 쉼, 429 → 60초, 418 → 정지 파일, pid 변경 300초, 동시 1건 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/candles.py:33-47·320-362 |
| 5 | 서버 IPv4 1개(175.126.73.41), IPv6 전역 주소 없음, api.upbit.com 은 A 레코드만 — 다른 IP 로 나누는 길은 지금 서버에 없음 | `ip -o addr`, `dig AAAA` |
| 6 | 서버 엔진 3분봉(KRW-JTO) | 서버 EMA params |
| 7 | 로컬 실측(맥 IP): 다른 종목 1분·30일 첫 실행 54.2초, 429 0 | impl-report 2·6절 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | Task 4-0b 의 두 장치((가) 엔진 경계 −2~+15초 창에서 부르지 않기, (나) 429 1회 → 10분, 24시간 안 2회째 → 수동 해제 정지)가 「v2 때문에 IP 차단이 생기지 않는다」를 사실상 보장하는가. 빠진 경로(엔진 재시도 꼬리 15~92초 구간과 v2 5회/초 겹침 등)가 있는가 | 보장에 가깝다. 15~92초 구간은 엔진이 5초마다 1회 수준이라 v2 5회/초와 합쳐도 초당 6회, sec≤4 쉼이 남은 여유를 지킨다. 418 은 v2 가 429 뒤 멈추므로 v2 쪽에서는 쌓일 수 없다 |
| 2 | 창 길이 기준을 미리 받기 대상의 엔진 봉 단위로 잡고, 없으면 1분으로 하는 것이 맞는가 | 맞다(가장 보수적) |
| 3 | 첫 429 의 10분 멈춤을 재시작 뒤에도 지키려고 `.cooldown.json` 을 두는 것이 과한가 | 필요하다(배포·재시작 직후 바로 다시 부르는 것을 막음) |
| 4 | 대가: 다른 종목 첫 실행이 창을 한 번 만나면 약 17초 늘어 1분을 조금 넘을 수 있다. 사용자 「1분 이내」와 「IP 차단이 생기지 않게」가 부딪히는데, 새 지시(차단 방지)를 우선하고 실측해 보고하는 것이 맞는가, 구현 전에 사용자에게 물어야 하는가 | 새 지시가 우선(사용자가 「진행하시오」), 실측 값을 커밋 승인 요청 때 보고 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-proposal-match-20261026.md (「Task 4-0b」 절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/candles.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261027-proposal-match.md (6절 「사용자 결정 1027-05」)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/data_feed.py, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/rest_reconcile.py (엔진 캔들 호출 시점)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 1회 (2026-10-27, Agent model: fable)

**판정:** 수정 후 진행
**이유:** (가)·(나) 방향은 맞지만, 서버 24시간 journal 에서 엔진 캔들 묶음의 약 23%(972 중 224)가 창(−2~+15초) 밖(20~92초, 90~92초 156건)에서 일어나고, 그때의 429 는 엔진 요청에 떨어질 수 있어 (나)가 보지 못함.

| # | 답 요지 | 확신 |
|---|---|---|
| 1 | 보장하지 않음. 빠진 경로: 창 밖 5회 묶음, 엔진 쪽 429 를 v2 가 모름. 대책: USER_RATE 4(4+5=9), ENGINE_WINDOW_AFTER 20 | 높음 |
| 2 | 맞음. 1분 폴백 조건을 impl-report 에 | 높음 |
| 3 | 과하지 않음. last_429 도 저장 | 높음 |
| 4 | 새 지시 우선. Step 5 가 75초 넘으면 커밋 승인 전에 따로 묻기 | 보통 |

고쳐야 할 것: 1 막음(계획서 근거 문단 정정·76% 명시) / 2 막음(USER_RATE 4·창 +20, spec·요청서 5→4) / 3 막음(질의서 사실 2·3 보정) / 4 권고(.cooldown.json last_429) / 5 권고(INLINE 창 대기 체감 기록) / 6 권고(요청서 관찰에 [RECONCILE] 예외·[REST-SAFE] 예외·빈 응답).
규칙 메모: Fable 이 답변 중 빈 heredoc 1회(무해) 기록.

## PO 반영 (다시 묻기 전)
- 1: 계획서 Task 4-0b 근거 문단을 24시간 분포·5회 묶음·76%·엔진 쪽 429 로 고침.
- 2: (0) USER_RATE 4.0(간격 ≥0.25초 시험), (가) ENGINE_WINDOW_AFTER 20, 시험 (a) 경계 수치 갱신. spec D8·요청서 4절의 「5회/초」는 구현 단계에서 4 로 고침(구현 지시에 포함).
- 3: 위 사실 표 2·3 보정.
- 4: `.cooldown.json` 에 last_429, 재시작 뒤 2회째 → HALT 시험.
- 5: 계획서 「체감」 줄(1분 폴백·처리기 안 경로 창 대기).
- 6: 배포 요청서 2-0 실패 표지에 3종 추가.
- Step 5: 75초 넘으면 커밋 승인 전 사용자에게 묻기.

## Fable 답변서 2회 (다시 묻기, 2026-10-27)

**판정:** 수정 후 진행
**이유:** 1회차 막음 3·권고 3 반영 확인. 다만 Task 4-0b Interfaces 안에 고치기 전 숫자 두 곳(구간 `[b−2, b+15)`, 「USER_RATE 5 … 바꾸지 않는다」)이 남아 (0)·(가)와 어긋남.

고쳐야 할 것: 1 막음(구간 b+20) / 2 막음(「바꾸지 않는다」 목록에서 USER_RATE·429 빼기) / 3 권고(바꿀 기존 시험 3곳 명시) / 4 권고(runbook 96·101행, spec D8 의 429 60초 문구, 요청서 58·89행도 범위) / 5 권고(창 기준 단위는 `self.prefetch_targets` — 매 요청 `_targets()` 금지).
사용자에게 물어야 할 것: 없음.

## PO 반영 (2회째 뒤)
- 1·2·3·4·5 모두 계획서 Task 4-0b 에 반영(grep 확인: `b+15` 0건, `USER_RATE 는 (0)` 1건, `self.prefetch_targets` 1건).
- 규칙(fable-rules [3]·메모리 fable-two-round-stop): 2회째도 「진행」이 아니므로 Fable 에게 다시 묻지 않고 사용자에게 구현 시작 여부를 묻는다.
