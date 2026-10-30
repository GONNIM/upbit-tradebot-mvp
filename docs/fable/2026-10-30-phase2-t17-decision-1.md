# 질의: 2차 T17(TEST/LIVE 분리, D4) 착수 전 정지선 — PO 결정 5건과 사용자 결정 2건

**지금 단계:** T17 착수 전 정지선입니다. 기준 HEAD 는 70cc4c4 이고 아직 파일은 바꾸지 않았습니다.
- §T17 이 요구한 내용은 대부분 T6·T11~T14 에 이미 들어가 있습니다(실행 에이전트 대조).
- 새로 고칠 코드는 0~1곳입니다.
- 고정 파일 9개, 스키마, 실계좌 EMA 경로는 모두 무변경입니다.

**다음에 하려는 일:**
1. 아래 PO 결정을 확정하고, 사용자 결정 2건을 올립니다(HANDOFF 1030-04).
2. 결정을 받으면 실행 에이전트가 시험 파일 1개(필요하면 strategy_switch.py 1곳도)를 구현합니다.
3. 그 뒤 verifier → Fable → 커밋 승인으로 갑니다.

## 실행 에이전트 정지선 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | pullback_state 는 PK(user_id, mode)이고, load/save/reset 이 모두 mode 로 거른다. 엔진 모드는 trader.test_mode 에서 정한다 | services/init_db.py:1017,1040, services/pullback_state.py:126-206, core/strategy_engine.py:1234 |
| 2 | strategy_switch 는 mode 칸·인덱스가 있고, reservation·last_done·insert·gate_decision 이 모두 mode 로 거른다 | init_db.py:1054,1072, engine/strategy_switch.py:145-322 |
| 3 | 요청 모드는 신버전 세션 입장 모드다. 엔진은 mode ∈ MODES 를 검사한다 | v2/api_write.py:248, engine/control_requests.py:611-624 |
| 4 | 요청 모드 ≠ 실행 중 모드이면 mode_conflict 로 거절한다. 9종 가운데 8종(engine_start·stop·force_buy·sell·switch·revert·apply_params·ops_settings)은 이미 있다. cancel_reservation(strategy_switch.py:706-718)에는 이 검사가 없다. cancel 은 DB 행만 CANCELED 로 바꾸고 엔진은 건드리지 않는다 | control_requests.py:727-768, strategy_switch.py:586-595, pullback_apply.py:354,577 |
| 5 | 설정 파일과 활성 파일은 모드 공용이다(1029-03 ② D4 유지) | engine/pullback_params.py:80-88, engine/params.py:447 |
| 6 | 코드에 `_dry_` 규칙은 없다. 문서 정정은 §9 에 잡혀 있다 | plan-phase2.md:1445,1451 |
| 7 | 의도한 「모든 모드」 예외가 2곳 있다: 구버전 잠금 reservation_any_mode(1029-10 C3 ①)와 D10 | ui/pullback_lock.py:77, services/auto_verify.py:119 |
| 8 | engine_stop 모드 불일치와 cancel_reservation 은 따로 된 시험이 없다 | 시험 grep |
| 9 | 실계좌 로그인 검증 2곳이 모드 칸 없는 accounts·account_positions 를 실계좌 값으로 덮어쓴다(원화와 코인 수량). 모의 거래기도 이 두 표를 지갑으로 읽는다. 같은 표가 실계좌 대시보드의 DB 캐시이기도 하다 | services/auto_verify.py:93-100, app.py:419-431, core/trader.py:323-331,388, init_db.py:176-203, pages/dashboard.py:259-264 |

## PO 결정(사실·위험만 확인 요청)
1. Files 를 정정한다. pullback_state.py·v2/control.py·control_requests.py 는 고칠 것이 없다. 바뀌는 코드는 결정 U1 에 따라 0곳 또는 strategy_switch.py:706 1곳이다.
2. 시험 파일 이름은 test_r_2026_10_30_p4_t17_mode.py 로 한다(작성일 관례).
3. 시험 범위는 셋이다.
   - state_separated: LIVE trader 로 pullback_restore_on_boot 를 돌려 TEST 행이 섞이지 않는지 본다. 반대 방향도 본다.
   - reservation_separated: 엔진·신버전 경로를 보고, 예외 2곳은 「모든 모드」로 단언한다.
   - request_mode_must_match_running: 엔진을 건드리는 8종 각각에 대해 mode_conflict 와 엔진 호출 0건을 단언한다. engine_stop 도 포함한다.
4. D4 문서 정정은 §9 에서 한다. 「설정·활성 파일 모드 공용」과 「구버전 잠금·D10 은 모든 모드 예약」을 함께 적는다.
5. 고정 파일 시험은 영향이 없다. strategy_switch.py 는 고정 목록 밖이다.

## 사용자에게 올릴 결정(초안)
| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| U1 | 예약 취소에도 「다른 모드 엔진이 돌면 거절」을 넣을지 | (가) 지금처럼 취소는 허용한다. 규칙을 「엔진을 건드리는 요청만 mode_conflict」로 적고 시험으로 고정한다 / (나) 거절한다. 그러면 실계좌 엔진이 도는 동안 모의 예약을 취소할 수 없고, 그 예약 때문에 걸린 구버전 설정 저장 잠금도 실계좌 엔진을 멈춰야 풀린다 | (가). 취소는 매수 차단을 푸는 쪽이라 주문이 생기지 않는다 |
| U2 | 실계좌 로그인이 모의 지갑(원화·코인)을 덮어쓰는 기존 동작(1029-12)을 T17 에 넣을지 | (가) T17 은 계획 범위대로 하고, 1029-12 에 「코인 수량도 덮음」과 「실계좌 화면 캐시와 같은 표」를 더해 따로 처리한다 / (나) T17 에 넣는다. 모의 새 전략 보유·예약 중이면 로그인 검증이 두 표 갱신을 건너뛴다. 그동안 실계좌 화면의 잔고 캐시가 멈춘다(app.py 1-A) / (다) 표를 모드별로 나눈다. 스키마 변경이고 services/db.py(고정 파일)를 건드린다 | (가). 새 전략은 모의 전용이라 실자산 영향이 없다 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~9 가 맞는가 | 맞다 |
| 2 | U1 (가)일 때, 다른 모드 엔진이 도는 중에 예약을 취소하면 T12 전환·감시 스레드와 경합하거나 상태가 꼬이는가 | 감시 스레드는 TEST 엔진에서만 돌고, cancel 은 RESERVED → CANCELED 행 갱신뿐이라 꼬이지 않는다 |
| 3 | U2 (가)로 미뤄도 2차 배포 뒤 모의 새 전략 운용에 실질적 위험이 있는가. 있다면 배포 전에 해야 하는가 | 실계좌 로그인을 하는 사용자가 모의 새 전략도 함께 쓸 때만 생긴다. 모의 자산 문제다 |
| 4 | 이 표로 사용자 결정을 요청해도 되는가 | 된다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md §T17(:1394-1402), §9
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/strategy_switch.py, engine/control_requests.py, services/pullback_state.py, v2/control.py, ui/pullback_lock.py, services/auto_verify.py, app.py, core/trader.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (1029-12)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 멈춤. 사용자 결정 U1·U2 만 남아서 멈춤으로 둡니다. 사실 1~9 와 PO 결정 1~5 는 맞습니다.

- U1 (가)에서 경합은 없습니다. 요청 처리와 감시 tick 이 같은 `_GLOBAL_LOCK` 을 잡고(control_requests.py:488, strategy_switch.py:881), cancel 은 switching 행을 거절한 뒤 행 갱신 한 문장만 실행합니다.
- U2 에는 빠진 경로가 있습니다. 실계좌 엔진이 돌 때 order_reconciler.py:769-915 가 1분마다 같은 두 표를 실계좌 값으로 덮어쓰고, DB 에만 있는 코인은 0 으로 만듭니다. 그 결과 모의 새 전략 보유분은 다음 봉 지갑 확인에서 분할 상태가 초기화되거나 desync 로 추가 매수가 멈춥니다. 실자산 위험은 없고, 배포 전에 꼭 해야 하는 일도 아닙니다.

**막음:**
1. U2 설명에 엔진 1분 동기화 경로를 더합니다. 1029-12 범위도 넓힙니다.

**권고:**
2. reservation_separated 시험에 switching_rows 는 mode 로 거르지 않는다는 점을 적습니다. 대신 호출처(recover_all·settle_switching)가 TEST 만 고르는지 단언합니다.
3. request_mode 시험에 cancel_reservation(U1 가)을 넣고, 「done·ok, 엔진 호출 0건」을 단언합니다.
4. §9 줄 번호를 1451 에서 1449 로 고칩니다.

## PO 반영 (10/30)
- 막음 1: 사용자 결정 표 U2 와 HANDOFF 1029-12 문구에 반영했습니다.
- 권고 2·3·4: 실행 지시에 넣습니다.
- 남은 일이 사용자 결정뿐이라 다시 묻지 않고 사용자에게 바로 묻습니다(HANDOFF 1030-04).

## 사용자 결정 (10/30 · 1030-04 「권고대로」)
- U1 (가): 예약 취소는 다른 모드 엔진이 실행 중이어도 허용한다. mode_conflict 거절은 엔진을 건드리는 8종에만 적용한다. 이 규칙을 계획에 적고 시험으로 고정한다.
- U2 (가): T17 은 계획 범위대로 한다. 실계좌 쪽이 모의 지갑을 덮어쓰는 문제(로그인 검증과 엔진 1분 동기화 두 경로)는 1029-12 에서 따로 처리한다.
