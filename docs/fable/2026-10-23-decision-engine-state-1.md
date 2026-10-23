# 질의: Task 3 을 push(02c3e0e) 했고, Task 4 착수 전 사용자 결정 1022-06(LIVE 엔진 상태 결합 규칙) 선택지를 올리려 합니다

**지금 단계:** 계획 (Task 4 착수 전 결정 요청)
**다음에 하려는 일:** 아래 선택지 3개와 PO 권고를 사용자에게 올립니다(파일 쓰기·커밋 없음, 이 질의서만 저장). 사용자 답을 받으면 progress.md 에 적고, Task 4 착수 질의서에 그 결정을 넣습니다. 이 질의는 사실·실현 가능성·위험만 확인합니다.

## 정할 것
LIVE 모드에서 화면의 「엔진 동작」 3단계(정상·지연·판단 불가)를 정할 때, 매수·매도 판단 기록 시각(`audit_buy_eval`·`audit_sell_eval` 최신 `timestamp`)과 잔고 기록 시각(`accounts.updated_at`)을 어떻게 합칠지. TEST 모드는 판단 기록만 본다(spec E17).

## 선택지 (기준값: 지연 = 540초 초과, 판단 불가 = 1800초 초과, 3분봉)
| 안 | 규칙 | LIVE 화면에서 일어나는 일 |
|---|---|---|
| 가 | 판단 기록만으로 3단계 판정. 잔고 시각은 「잔고 갱신 N분 전」으로 따로 한 줄 보조 표시 | 엔진 루프가 멈추면 30분 뒤 「판단 불가」. 거래 없는 긴 공백(실측 최대 5시간 9분)에도 같은 「판단 불가」가 뜸 |
| 나 | 두 시각 중 더 최근 값으로 판정 | 잔고 동기화가 1분마다 돌아 거의 항상 「정상」. 엔진 루프가 멈춰도 「정상」으로 보일 수 있음 |
| 다 (PO 권고) | 판단 기록으로 판정하되, 판단 기록이 1800초를 넘었어도 잔고 시각이 540초 안이면 「판단 불가」 대신 「지연」으로 한 단계만 낮춤. 「정상」으로는 올리지 않음. 「마지막 판단 N분 전」은 항상 판단 기록 기준 | 루프 정지·긴 무거래 공백 모두 「지연」(정상으로 가려지지 않음). 잔고까지 멈추면 「판단 불가」 |

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | spec E17: 판단 기록 최신 시각으로 판단, LIVE 는 `accounts.updated_at` 도 보조로 봄(잔고 동기화 스레드 기록이라 엔진 루프 생존과 같지 않음), 「정지」로 단정하지 않음 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md 77행 |
| 2 | plan Task 4: `engine_state(last_eval_ts, accounts_ts, mode, bar_sec, now)` → `basis: "eval"|"accounts"|"none"`, 시험 이름 `test_live_uses_accounts_ts_as_secondary`·`test_test_mode_ignores_accounts`·`test_engine_state_no_trade_gap_is_delay`(24분 → delay). 결합 규칙 정의 없음 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan.md 127~134행 |
| 3 | 실측(10-22 22:58, 7일): 판단 기록 간격 중앙값 180초·95% 539초·최대 18,540초. `accounts.updated_at` 은 실행 약 1초 전 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/measure-20261023.md Step 2 |
| 4 | `accounts.updated_at` 쓰는 곳: 엔진 `OrderReconciler._periodic_balance_sync`(기본 60초, LIVE 만), 주문 처리 경로, 구버전 화면 계정 검증(`app.py` 396~398행) — 엔진 매매 루프와 별개 스레드·경로 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/order_reconciler.py 23·534·708~741행, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/services/db.py 2295~2336행 |
| 5 | 1800초 넘는 공백이 7일에 몇 번인지는 재지 않음(최대값만 앎) | measure Step 2 관찰 |
| 6 | 안 다의 `basis`: 판정이 낮춰졌을 때 `"accounts"`, 그 밖 `"eval"`, 둘 다 없으면 `"none"` 로 plan 시그니처 안에서 구현 가능 | plan 129행 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 선택지 3개의 「화면에서 일어나는 일」 설명이 사실과 맞는가(특히 안 나의 「루프가 멈춰도 정상」) | 맞음 — 잔고 동기화는 reconciler 스레드라 매매 루프와 따로 돎 |
| 2 | 안 다가 spec E17(「정지」로 단정 않음, 잔고는 보조)과 plan 시그니처·시험 이름에 맞게 구현 가능한가 | 예 |
| 3 | 결정 전에 1800초 초과 공백 빈도를 서버에서 더 재야 하는가 | 아니오 — 세 안 모두 빈도와 무관하게 동작이 정해짐. 원하면 선택지로만 제시 |
| 4 | 사용자에게 이 결정 요청을 올려도 되는가 | 예 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/measure-20261023.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/order_reconciler.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/services/db.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/app.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/sdd/plan/progress.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: Task 3 을 push(02c3e0e) 했고, Task 4 착수 전 사용자 결정 1022-06(LIVE 엔진 상태 결합 규칙) 선택지를 올리려 합니다

**판정:** 진행
**이유:** 사실 6건을 코드·문서로 대조해 모두 맞음을 확인했고, 세 선택지의 「화면에서 일어나는 일」도 코드 구조와 맞습니다. 고칠 것은 안 다의 빈 값 처리 정의와 설명 보강뿐이며 모두 권고입니다.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 설명이 사실과 맞는가 | 맞음. `accounts.updated_at` UPDATE 는 services/db.py 636·2332행 두 곳. LIVE 에서 매매 루프는 쓰지 않음(636행 호출은 TEST 시뮬레이션·구버전 화면). reconciler 는 별도 daemon 스레드(order_reconciler.py 41·205~226행), 매매 루프는 engine_manager.py 429~433행 다른 스레드. 사용자가 엔진을 정지하면 reconciler 도 멈춰(282행) 세 안 모두 30분 뒤 판단 불가. 루프가 예외로 죽고 자동 재시작 3회(299~331행)가 실패해도 reconciler 는 계속 돌아 안 나는 계속 정상, 안 다는 계속 지연 | 높음 |
| 2 | 안 다 구현 가능 | 예. eval None + accounts 540초 안 경우 규칙 추가 필요 | 높음 |
| 3 | 빈도 추가 측정 | 아니오. measure 58행 자료로 충분 | 보통 |
| 4 | 결정 요청 올림 | 예 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | 안 다: LIVE 에서 eval None + accounts 540초 안 → 지연·basis accounts·ago_sec None, 둘 다 없거나 accounts 도 오래되면 판단 불가·basis none (반영) |
| 2 | 권고 | 안 다·나 설명에 루프 사망·재시작 실패 때 동작 추가 (반영) |
| 3 | 권고 | 사실 4 에 636행 경로 추가 (반영) |

## 사용자에게 물어야 할 것
- 없음
