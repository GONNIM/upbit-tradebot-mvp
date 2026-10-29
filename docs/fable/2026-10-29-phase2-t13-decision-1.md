# 질의: 2차 T13(「이 설정으로 동작」·「저장만 하기」) 착수 전 정지선에서 나온 결정 4건을 사용자에게 올리려 함

**지금 단계:** T13 착수 전 정지선이다. 기준은 HEAD 6b6f0b5(T12 커밋 직후)이고, 바꾼 파일은 없다.

**다음에 하려는 일:**
- 아래 결정 A~C 를 사용자에게 요청한다. HANDOFF 에 1029-05 행을 넣는다.
- 결정 D 는 PO 가 정한다(거절).
- 결정을 받으면 실행 에이전트가 구현한다: 시험 → 변이 → 게이트 → 계획 구현 메모.
- 그 뒤 verifier → Fable → 커밋 승인 순서로 간다.

**전제(이미 정해진 것):**
- 바이트 고정 8개: strategy_engine, strategy_incremental, params, live_loop, boot_resume, trading_control, engine_manager, services/db.
- 엔진은 사용자당 1개다.
- 새 전략 PULLBACK 은 모의 전용이다.
- 결정 1029-03: 설정 파일은 하나(D4 유지), 전환은 모의만.

## 실행 에이전트 정지선 결과 (사실)
| # | 사실 | 근거 |
|---|---|---|
| 1 | 계획의 적용본 mtime 감시와 제자리 재시드는 `engine/live_loop.py` 를 고쳐야 한다. 지표는 `_pullback_seed_warmup`(:319-340)이 만들고, 봉 버퍼는 `run_live_loop` 의 지역 변수(:1109)다 | live_loop.py |
| 2 | 익절·손절도 확정 봉 마감 때만 판정한다. 그래서 「즉시」와 「다음 봉부터」는 실제로 같다 | `core/strategy_pullback.py:459-509` |
| 3 | 회당 금액은 회차마다 `floor(base / eff_max_splits)` 로 다시 계산한다. 보유 중 한도를 3→5 로 늘리면 투입 합계가 운용자산의 약 1.27배가 될 수 있다 | `core/strategy_engine.py:1959-1960` |
| 4 | `handle_switch` 는 활성 전략이 PULLBACK 이면 `already_pullback` 으로 거절한다. PARAMS 행은 늘 DONE 이고 예약 판정에 쓰지 않는다 | `engine/strategy_switch.py:593`, 계획 :1030, `test_params_rows_ignored_by_reservation` |
| 5 | `pullback_state` 는 (user, mode)당 1행이다. 종목·봉 단위를 바꿔 재시작하면 복원이 `other_market` 이 되어 기록 저장이 멈추고 투자자에게 CRITICAL 이 간다. T6 의 「정리는 T12」는 T12 에서 하지 않았다 | `services/init_db.py:1040`, `core/strategy_engine.py:1298-1322,1508-1516` |
| 6 | `apply_params` 는 KINDS 에 있지만 처리 함수가 없어 `not_ready` 다 | `engine/control_requests.py:114-115` |

## 사용자에게 올릴 결정 (초안)
| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| A | 엔진이 새 설정을 받는 방식 | (가) 감시 파일을 두지 않는다. `apply_params` 요청 → 엔진이 돌면 엔진 제어 큐(강제 매수와 같은 통로)에서 `apply_saved`·cfg 교체·PARAMS 기록을 한다. 엔진이 멈춰 있으면 적용본만 쓴다. MA 기간·방식 변경은 엔진을 재시작한다(워밍업으로 다시 시드, 분할 상태는 T6 복원). 실패하면 이전 적용본으로 되돌리고 1회 재기동하고 CRITICAL 을 보낸다 / (나) (가)와 같되 보유 중 MA 변경은 거절한다 / (다) live_loop 고정을 풀고 계획대로 한다 | (가). EMA 경로 파일이 바뀌지 않는다 |
| B | 봉 단위·종목 변경 | (가) 미보유일 때만 받는다. `pullback_state` 행의 종목·봉 단위를 새 값으로 바꾸고 재시작한다. 보유 중이면 거절 문구를 띄운다 / (나) 계획대로 예약한다(SWITCH PULLBACK→PULLBACK 행, 복귀 조회·T16 문구 수정) / (다) PARAMS·RESERVED 행을 쓴다 | (가). T12·스키마 무변경. 투자자가 보는 거절 문구 1개가 생긴다(체감 변경). 덧붙여 EMA→PULLBACK 전환 때 남은 옛 `pullback_state` 행도 같은 방식으로 정리할지 함께 묻는다 |
| C | 보유 중 분할 한도 변경 | (가) 새 한도가 지금 회차 이하이면 즉시 추가 매수를 멈춘다. 그 밖의 변경은 이번 거래가 끝난 뒤(지갑 0) 적용한다 / (나) 즉시 적용한다(운용자산 초과 가능) | (가). 금액 계산이 바이트 고정 파일 안에 있다 |
| D | 복귀 예약 중 적용 | 거절(`already_reserved`) | PO 가 정한다 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~6 이 맞는가 | 맞다고 본다. 줄 번호는 실행 에이전트 기준이다 |
| 2 | 결정 A(가)가 실현 가능한가. 엔진 스레드에서 cfg 를 바꿀 때 strategy_engine(고정) 쪽 상태(`_pullback_params_sha` 등)가 엇갈리지 않는가 | 가능하다고 본다. 실행 에이전트가 같은 통로(강제 매수)를 이미 쓰고 있다 |
| 3 | 결정 B(가)에서 `pullback_state` 행을 고치는 것이 T6 복원 규칙·T10 재시작 시험과 충돌하지 않는가. 정리 범위를 EMA→PULLBACK 전환까지 넓혀도 되는가 | 미보유이고 회차가 0 일 때만 고치면 충돌하지 않는다고 본다 |
| 4 | 결정 C(가)의 「지갑 0 뒤 적용」을 담을 곳이 스키마 변경 없이 있는가 | 적용본은 바로 쓰고 엔진 cfg 교체만 미루는 방식이면 된다고 본다. 확인이 필요하다 |
| 5 | 위 표로 사용자 결정을 요청해도 되는가 | 된다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md (§T13, §T12 구현 메모, §8)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/strategy_switch.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/live_loop.py, core/strategy_pullback.py, core/strategy_engine.py, core/engine_control.py, engine/control_requests.py, services/init_db.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-29-phase2-t12-decision-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 수정 후 진행

사실 1~6 은 맞다. 다만 아래 두 가지는 표현을 바로잡는다.
- live_loop·strategy_engine·params 는 바이트 고정이 아니라 AST·함수 집합 고정이다. `test_live_loop_ema_path_unchanged` 는 새 함수와 run_live_loop 본문을 고정한다.
- 사실 2 의 근거 줄은 `strategy_pullback.py:562-570,715-722` 다.

**막음:**
1. 결정 C 의 「cfg 교체만 미룸」은 재시작하면 사라진다. 기동할 때 적용본을 바로 읽기 때문이다(`live_loop.py:381`, `strategy_engine.py:1517`). 보류를 담을 곳을 적어야 한다.
2. 결정 B 의 행 수정은 엔진이 멈춘 뒤에 해야 한다. 엔진이 봉마다 `pullback_state` 를 UPSERT 하기 때문이다(`strategy_engine.py:1229`).
3. 「약 1.27배」가 아니라 최대 1.4배다(3회차 뒤 3→5).

**권고:**
4. 행을 지울지, 종목·봉만 바꿀지 정한다. 바꾸는 쪽이면 `buy_fail_bar_ts`·`prev_golden`·`last_bar_ts` 를 비운다.
5. 결정 A 구현 메모에 세 가지를 적는다.
   - 새 cfg 는 생성자와 같은 방식으로 만든다(파생 키·거래 시간 검사).
   - `_pullback_params_sha` 를 갱신한다.
   - `_guard` 를 거친다.
6. 사실 2 의 줄 번호를 고친다.
7. 고정 방식 표현을 고친다.

## PO 반영 (10/29)
- 막음 1:
  - 계산하면 이렇다. 보유 중 k 회차를 산 뒤 한도를 old→new 로 바꾸면 투입 합계는 운용자산 × (1 + k·(1/old − 1/new)) 다. 한도를 줄이면(new < old) 1 이하이고, 늘릴 때만 1 을 넘는다.
  - 그래서 결정 C 를 「보유 중 늘림은 거절, 줄임은 즉시」로 바꿨다. 이러면 보류를 담을 곳이 필요 없다. 보류 파일 안은 선택지로 남겼다.
- 막음 2: 결정 B 에 「엔진 정지 → 행 수정 → 시작」 순서를 적었다(T12 restart_engine 안에서 한다).
- 막음 3: 최대 1.4배로 고쳤다.
- 권고 4 는 PO 가 정한다. 종목·봉 단위만 바꾸고, 쉼·골든·마지막 봉 칸은 비우고, 실현 손익 누적은 유지한다.
- 권고 5·6·7 은 실행 지시와 이 문서에 반영했다.

# 다시 묻기(2회째): 아래 결정 요청문으로 사용자에게 올려도 되는가

**전제:**
- 엔진은 사용자당 1개다. 새 전략은 모의 전용이다. 설정 파일은 하나다(1029-03).
- live_loop·strategy_engine·params 는 AST·함수 집합 고정이다(`test_live_loop_ema_path_unchanged`, `test_strategy_engine_non_pullback_unchanged`, T9). boot_resume·trading_control 은 바이트 고정이다.

| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| A | 엔진이 새 설정을 받는 방식 | (가) 적용 요청을 받으면 처리한다. 엔진이 돌고 있으면 엔진 제어 큐에서 다음을 차례로 한다: `apply_saved` → 생성자와 같은 방식으로 만든 새 cfg 로 교체 → `_pullback_params_sha` 갱신 → PARAMS 기록. 반영은 다음 확정 봉부터다. 엔진이 멈춰 있으면 적용본만 쓰고, 다음 기동에서 읽는다. MA 기간·방식이 바뀌면 엔진을 재시작한다(워밍업이 새 MA 로 다시 시드, 분할 상태는 T6 복원, 그동안 매수 없음). 실패하면 이전 적용본으로 되돌리고 1회 재기동하고 CRITICAL 을 보낸다. LIVE 는 `_guard` 가 거절한다 / (나) (가)와 같되, 보유 중 MA 변경은 거절한다 / (다) live_loop 고정을 풀고 계획대로 감시·제자리 재시드를 한다 | (가) |
| B | 봉 단위·종목 변경 | (가) 보유가 없을 때만 받는다. 엔진 정지 → `pullback_state` 행 수정(종목·봉 단위를 새 값으로, 쉼·골든·마지막 봉 칸은 비움, 실현 손익 누적은 유지) → 시작 순서로 한다. 보유 중이면 「보유 중에는 봉 단위·종목을 바꿀 수 없습니다 — 매도 뒤 다시 적용해 주세요」로 거절한다. 같은 정리를 EMA→PULLBACK 전환 때도 한다. 다른 종목의 옛 행이 남아 있으면 지금은 전환 직후 저장이 막히고 투자자에게 CRITICAL 이 가기 때문이다 / (나) 계획대로 예약한다(SWITCH PULLBACK→PULLBACK 행, 복귀 조회·T16 문구 수정) | (가). 거절 문구 1개가 체감 변경이다 |
| C | 보유 중 분할 한도 변경 | (가) 늘림은 보유 중에 거절한다(B 와 같은 형태의 문구). 줄임은 즉시 적용한다. 줄이면 투입 합계가 운용자산 이하이고, 새 한도가 지금 회차 이하이면 추가 매수가 멈춘다 / (나) 늘림은 보류 파일(600)에 두었다가 지갑이 0 이 되면 적용한다 / (다) 즉시 적용한다(늘리면 최대 운용자산의 1.4배) | (가). 저장할 곳이 늘지 않는다. 모의 전용이라 실돈 위험은 없다 |

**PO 가 정함:** 복귀 예약 중 적용 요청은 거절한다(`already_reserved`).

**질문:** 위 표로 사용자 결정을 요청해도 되는가. 결정 C(가)의 계산식(1 + k·(1/old − 1/new))과 「줄이면 1 이하」가 `strategy_engine.py:1944-1959` 와 맞는가. 결정 B(가)를 restart_engine 안(정지와 시작 사이)에서 할 수 있는가.

---

# 답변(2회째) 요지 (Fable)

**판정:** 수정 후 진행

**확인된 것:**
- 결정 C 계산식이 맞다. floor 를 쓰면 실제 투입은 식의 값과 같거나 작다. 한도를 줄이면 투입 합계는 1 이하다.
- 결정 B 는 고정 파일을 건드리지 않고 `restart_engine` 안에서 할 수 있다. 위치는 옛 스레드가 끝나기를 기다린 뒤, `start_engine` 앞이다. 그 자리에서 회차 0·수량 0 을 다시 확인해야 한다.
- T12·1029-03 과 어긋나는 결정은 없다.

**막음:**
1. 결정 B: 재시작이 실패하면 행의 종목·봉 단위를 이전 값으로 되돌린다.

**권고:**
2. 체감 변경 거절 문구는 2개다(B, C).
3. 결정 A: 옛 적용본 바이트는 `apply_saved` 전에 호출자가 읽어 둔다.
4. 종목 변경은 화면 기능이 아니다(X8). 화면에서는 봉 단위만 바뀐다.
5. 계획 T13 규칙, 시험 이름, pullback spec 4.6 을 정정 대상으로 적는다.

## PO 반영 (10/29)
- 막음 1 과 권고 2·4 는 사용자 결정 요청문(HANDOFF 1029-05)에 넣었다.
- 권고 3·5 는 실행 지시에 넣는다.
- 단계 질의 2회를 다 썼고, 남은 것이 사용자 결정뿐이라 사용자에게 바로 묻는다.
