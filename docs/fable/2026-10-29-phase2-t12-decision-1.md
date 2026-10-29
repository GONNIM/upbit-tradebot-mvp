# 질의: 2차 T12(전환·예약·복귀·예약 취소)가 착수 전 정지선에서 계획과 코드의 어긋남 5건으로 멈췄고, 사용자 결정 3건을 요청하려 함

**지금 단계:** 구현 착수 전 정지선. 코드 변경 0, 배포 없음. 기준 HEAD 는 abdef41(=origin/main).

**다음에 하려는 일:**
- 사용자에게 결정 3건을 요청한다. HANDOFF 에 1029-03 행을 넣는다.
- 답을 받으면 실행 에이전트가 T12 를 구현한다. 순서는 구현 → 시험 → 변이 → 게이트 → plan 메모 → verifier → Fable → 커밋 승인.

**지금까지의 검수:**
- 실행 에이전트(opus)가 정지선 대조를 했다(아래 사실 1~5). PO 는 보고만 받았다.
- 이 질의에서 사실과 실현 가능성·위험을 확인해 주기 바란다.

## 지금까지 확인한 사실 (실행 에이전트 보고, 검증 필요)
| # | 사실 | 근거 |
|---|---|---|
| 1 | 계획은 예약 중 매수 차단을 `core/strategy_engine.py` `execute` 에 넣으라고 한다. 하지만 EMA 고정 시험 두 건이 비 pullback 함수 전부를 f4aac1f 와 AST 로 비교하므로, 함수가 하나 늘어도 실패한다. 매도 완료 감지 → 전환 신호도 같은 고정에 걸린다 | T9 `test_ema_ignores_trading_hours`(232~235), T11 `test_strategy_engine_non_pullback_unchanged`(1232), `tests/regressions/baseline_commits.py`(기준 올리기는 사용자 승인) |
| 2 | `execute` 를 막아도 다 막히지 않는다. WO-2 지연 매수(`strategy_engine.py:2334` `_execute_buy` 직접 호출)와 구버전 강제 매수(`services/trading_control.force_buy_in`, 바이트 고정)는 `execute` 를 거치지 않는다 | 해당 줄 |
| 3 | 계획에 LIVE 처리가 없다. (a) PULLBACK LIVE 거부를 유지하므로 LIVE 전환은 실계좌 EMA 를 한 번 끊고 되돌린다. (b) `restart_engine` 은 모드와 관계없이 엔진을 멈추므로, TEST 전환 요청이 돌고 있는 LIVE 를 끈다. (c) 활성 전략 파일은 사용자당 1개다. TEST 에서 PULLBACK 으로 전환하면 다음 LIVE 시작과 boot_resume LIVE 가 PULLBACK LIVE 거부에 걸려 실계좌 매매가 시작되지 않는다. TEST/LIVE 분리는 T17 몫이다 | `engine/control_requests.py` `_engine_present`·`restart_engine`, `engine/engine_manager.stop_engine`(user_id 키), `params.save_active_strategy` |
| 4 | 계획은 기동 재개 완료 Event 를 `engine/boot_resume.py` 에 두라고 하지만, 이 파일은 바이트 고정 시험 대상이다 | `test_untouched_ema_files_same_as_base` |
| 5 | 계획의 `_no_recover` 언급은 1028-15 이후 의미가 없다(재시작 분기 삭제) | abdef41 |

## 사용자에게 올릴 결정(실행 에이전트 권고 → PO 정리)
| # | 결정 | 선택지 | 권고 |
|---|---|---|---|
| 1 | 예약 중 매수 차단 위치 | (가) `core/engine_control.attach` 가 엔진 인스턴스의 `execute`·지연 매수 경로를 「예약이 있을 때만」 막는 래퍼로 감쌈. strategy_engine 파일은 무변경 / (나) 계획대로 `strategy_engine.execute` 를 고치고, 「EMA 경로 변경」 승인 뒤 기준 커밋을 올림 | (가). 예약이 없으면 흐름이 지금과 같음을 시험(호출 흔적 비교)으로 고정한다. 보고에는 「EMA 매수 경로에 예약 게이트(예약 있을 때만)」를 명시한다. 전환 신호는 감시 스레드가 예약이 있을 때만 엔진 큐로 보유 확인 항목을 넣어 판정한다 |
| 2 | LIVE 처리 | PULLBACK LIVE 거부를 해제하기 전에는 LIVE `switch` 를 엔진에 손대지 않고 바로 거부. 다른 모드 엔진이 돌면 `mode_conflict`. 공용 활성 파일 문제는 (ㄱ) 마지막 LIVE 기록이 있는 사용자는 TEST 전환도 거부 / (ㄴ) T17(TEST/LIVE 분리)을 T12 앞으로 | 거부 규칙은 넣는다. 공용 파일은 (ㄱ)? 또는 (ㄴ)? — PO 는 아래 물어볼 것 2 |
| 3 | 구버전 강제 매수가 예약 중에 나가는 틈 | T15(구버전 대시보드 처리)로 넘김 / T12 에서 막음 | T15 로 넘김. 구버전 파일은 바이트 고정이다 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~5 가 맞는가 | 코드로 확인해 달라 |
| 2 | 공용 활성 파일 문제는 (ㄱ)과 (ㄴ) 중 무엇이 맞는가 | 지금 서버 사용자는 LIVE EMA 로 실매매 중이다. (ㄱ)이면 그 사용자는 TEST 에서도 새 전략으로 전환할 수 없어 T12 가 실제로 쓸모가 없다. (ㄴ)이 맞아 보인다. 다만 T17 의 범위와 선행 조건을 확인해 달라 |
| 3 | 결정 1 (가)의 실행 시점 래퍼는 「EMA 경로 무변경」 원칙의 우회가 아닌가. 위험을 어떻게 막는가 | 예약이 없을 때는 래퍼가 원 함수를 그대로 부르고, 이를 호출 흔적 시험과 변이로 고정한다. 그래도 EMA LIVE 매수 경로에 실행 시점 분기가 생기므로 사용자에게 분명히 알린다. 대안으로, LIVE 전환을 거부하면 LIVE 에서는 예약이 생길 수 없으므로 래퍼를 TEST 엔진에만 붙이는 방법이 있다 |
| 4 | 이 결정 요청을 T12 하나로 올릴지, T12·T17 순서 변경까지 묶어 올릴지 | 묶어서 올린다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md («### T12:» 절, «### T17:» 절, T11 넘김, LIVE 거부 해제 전 조건)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/control_requests.py, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/engine_control.py, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/engine_manager.py, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_engine.py (2334), /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/params.py (save_active_strategy)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/regressions/baseline_commits.py, test_r_2026_10_28_p3_t9_*.py, test_r_2026_10_28_p4_t11_control.py (1232)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 수정 후 진행

**사실 확인:** 사실 1~5 는 코드로 확인됐다.

**추가로 확인된 것:**
- 신버전 강제 매수(`core/engine_control.py:151-166`, `engine/control_requests.py:689-715`)도 `execute` 를 거치지 않는다.
- 엔진은 사용자당 1개이므로 TEST 와 LIVE 를 동시에 돌릴 수 없다(`engine_manager.py:203-213`).
- boot_resume 은 LIVE 가 돌던 중 프로세스가 죽은 경우에만 대상이 된다.

**막음:**
1. (ㄴ)의 전제가 틀렸다. D4 「설정 파일은 하나」(`plan-outline-phase2.md:124`)와 T17 본문(`plan-phase2.md:1259-1261`)을 보면, T17 을 앞당겨도 활성 파일은 나뉘지 않는다. 선택지를 (ㄷ) D4 재결정 / (ㄹ) D4 유지로 다시 쓴다.
2. 「엔진 사용자당 1개」를 결정 요청문에 적는다.

**권고:**
- 3: `execute`·`_execute_buy` 를 둘 다 감싼다. TEST 엔진에만 붙인다. 보고 제목은 「EMA 매수 경로 실행 시점 변경」으로 한다.
- 4: 결정 3 은 수동 강제 매수 전부를 다루고, D7 과의 관계를 적는다.
- 5: 기동 완료 Event 는 `scripts/tradebot_boot.py` `_boot_resume_thread` finally 에서 세우고, 60초 예비 규칙을 유지한다.
- 6: 계획의 `_no_recover` 문구를 고친다.
- 7: 사실 3 (c) 의 서술을 정확히 고친다.

## PO 반영 (10/29)
- 막음 1·2 와 권고 3·4·7 은 아래 결정 요청문에 반영했다.
- 권고 5·6 은 PO 가 정해 실행 에이전트 지시에 넣는다(사용자 결정 대상이 아님).
  - Event 는 tradebot_boot finally 에서 세우고, 60초 예비 규칙을 유지한다.
  - 계획 `_no_recover` 문구는 「표식만 남음(1028-18 에서 다시 읽음)」으로 바꾼다.

# 다시 묻기(2회째): 아래 결정 요청문으로 사용자에게 올려도 되는가

**전제 사실(요청문에 적음):**
- 엔진은 사용자당 1개다. 그래서 어느 안을 고르든, 실매매 사용자가 모의에서 새 전략을 시험하려면 실계좌 엔진을 멈춘 동안에 하거나 모의 전용 ID 를 써야 한다.
- 새 전략은 지금 모의 전용이다(실계좌 기동 거부 유지).

| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| 1 | 예약 중 매수를 막는 방식 | (가) 엔진 바깥 래퍼: 엔진을 붙일 때 `execute`·`_execute_buy` 두 이름을 「예약이 있을 때만 매수 차단」으로 감싼다. **모의 엔진에만 붙이고**, 실계좌 거부를 해제할 때 다시 본다. EMA 파일은 바뀌지 않지만 모의 엔진의 매수 경로에 실행 시점 분기가 생긴다 / (나) 계획대로 `strategy_engine.execute` 를 고치고 EMA 기준 커밋을 올린다(EMA 경로 변경 승인) | (가). 실계좌 EMA 인스턴스는 지금과 실행·바이트가 모두 같다. 예약 없음 호출 흔적 시험과 변이로 고정한다 |
| 2 | 설정 파일이 하나인 문제(D4) | (ㄹ) D4 유지: 다른 모드 엔진이 없을 때만 모의 전환을 허용한다(`mode_conflict`). 실계좌 `switch` 는 엔진을 건드리지 않고 거부한다. 복귀는 활성 파일을 EMA 로 되돌린다. 활성이 새 전략인 채로 실계좌를 시작하면 지금처럼 거부하고 CRITICAL 을 보낸다 / (ㄷ) D4 재결정: 「새 전략 활성」을 모드별로 기록해 실계좌 기동이 모의 전환을 보지 않게 한다. engine_manager `_decide_strategy_type` 와 params 를 바꾸고, T17 범위가 커진다 | (ㄹ). EMA 실매매 경로를 건드리지 않는다. 엔진이 1개라 (ㄷ)을 골라도 동시 실행은 안 된다. (ㄷ)은 실계좌 거부를 해제할 때 다시 본다 |
| 3 | 예약 중 사용자 수동 강제 매수(구버전·신버전 모두) | 허용: 전환은 그 보유분까지 기존 전략이 매도한 뒤로 미뤄지고, 결과 문구로 알린다 / 막음: 요청서 7절·D7(구버전 강제 매수를 열어 둠)과 문구 조정이 필요하다 | 허용. D7 과 맞고 사용자의 직접 조작이다. 계획 `plan-phase2.md:238` 「예약 중 어떤 매수도」는 「앱 자동 매수」로 고친다 |

**질문:** 위 표와 전제 사실로 사용자 결정을 요청해도 되는가. 결정 3 「허용」일 때 계획의 다른 절과 충돌하는 곳이 있는가.

---

# 답변(2회째) 요지 (Fable)

**판정:** 수정 후 진행

**전제 사실과 결정 1·2:** 코드와 맞다(높음).
- 엔진 1개: `engine_manager.py:203-213`, MODE-LOCK 은 `:356-368`.
- 모의 전용: `:570-583`, `TestLiveRefusalKept` 3건이 통과한다.

**막음 1:** 결정 3 「허용」이 T15 와 어긋난다(`plan-phase2.md:1176,1196,1198`).
- 예약 중에는 활성 전략이 EMA/MACD 이고, 적용본은 전환 때 만들어진다(`:1034,1036`).
- 그래서 T15 대로면 예약 중 강제 매매가 PULLBACK 종목으로 나가거나, 적용본이 없어 화면이 멈춘다.
- 고칠 문장: 「예약 중(활성 EMA/MACD)에는 구버전 표시·강제 매매 종목 = 활성 전략 params 종목. PULLBACK 표시 경로는 활성 파일이 PULLBACK 일 때만」.

**권고:**
2. 「모든 매수」 뜻의 문장 4곳을 「봇 자동 매수(골든크로스·WO-2 지연 매수) 차단」으로 좁힌다.
   - `:238` · `:1035` · `:1071` 시험 설명 · T16 문구
3. 결정 3 에 범위를 적는다: 전환·복귀 예약 모두, 구버전·신버전 모두, 끼어든 매수는 예약 유지, 결과 문구 1회.
4. T12 흐름 5 에 다음 두 가지를 넣는다.
   - F8(미체결 매수 없음, `services/db.py:792`)
   - 파일 쓰기 직전 재확인(근거: `services/trading_control.py:287-292`)
5. 결정 1: 예약 조회는 처음부터 `mode` 로 거른다.
6. 결정 2: 「EMA 로」를 「직전 전략(EMA 또는 MACD)으로」로 고친다.

**사용자에게 물어야 할 것:** 결정 3건 외에는 없다.

## PO 반영 (10/29)
- 2회째 판정이 「수정 후 진행」이라 한도(2회)에 따라 더 묻지 않는다. 사용자에게 결정을 요청한다.
- 막음 1 과 권고 3·5·6 은 결정 요청문에 반영했다(HANDOFF 1029-03).
- 권고 2·4 와 T15 메모 수정은 사용자 결정 뒤 실행 에이전트 지시와 계획 수정에 넣는다.
