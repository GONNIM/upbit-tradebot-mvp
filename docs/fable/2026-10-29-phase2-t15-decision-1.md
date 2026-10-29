# 질의: 2차 T15(구버전 화면의 새 전략 표시·잠금·강제 매매·D10) 착수 전 정지선 — PO 결정 3건과 사용자 결정 2건

**지금 단계:** T15 착수 전 정지선이다(기준 HEAD 8464b58). 아직 아무 파일도 바꾸지 않았다.

**다음에 하려는 일:**
- 아래 PO 결정 3건(C1-a, C1-b, C4)을 확정한다.
- 사용자 결정 2건(C2, C3)을 올린다. HANDOFF 1029-10 에 적는다.
- 결정을 받으면 실행 에이전트가 구현한다. 순서는 다음과 같다.
  1. 새 파일 ui/pullback_lock.py
  2. pages 5개, app.py, services/auto_verify.py, ui/sidebar.py
  3. 시험 → 변이 → 게이트 → 구현 메모와 UI 1-A 목록
- 그 뒤 verifier → Fable → 커밋 승인 순서로 간다.

**전제:**
- 이번 범위는 고정 파일 9개를 하나도 고치지 않는다. pages·app.py·auto_verify·ui/sidebar 는 고정 대상 밖이다.
- pages/dashboard.py 는 실계좌 EMA 사용자가 쓰는 화면이다.
- 모든 분기는 「활성 파일 == PULLBACK」 또는 lock_state 잠김 뒤에만 둔다.
- 잠기지 않은 EMA 화면은 원본(8464b58)과 비교하는 AppTest 로 고정한다.
- 결정 1029-03-③ 메모를 따른다: 예약 중 구버전 표시와 강제 매매 종목은 활성 전략 params 종목이고, PULLBACK 표시 경로는 활성 파일이 PULLBACK 일 때만 쓴다.

## 실행 에이전트 정지선 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | TEST 화면이 그려질 때마다 세션 `virtual_krw` 로 `accounts.virtual_krw` 를 덮어쓴다. PULLBACK 1회차 매수 뒤 새로 고치면 가짜 현금이 생긴다. EMA TEST 에도 원래 있던 동작이다 | pages/dashboard.py:145-157, services/db.py:684, app.py:487 |
| 2 | set_config 374·392 는 「엔진 시작」이 아니라 「Go Dashboard」 화면 이동이다. 사이드바 메뉴는 CSS 로 숨겨져 있다 | pages/set_config.py:42-44,374,392,401-434 |
| 3 | 서비스 기동 재개는 LIVE 만 한다. TEST 엔진의 재개는 구버전 dashboard 의 자동 재개(412-481)가 유일한 경로다 | engine/boot_resume.py:12,62-67,149, pages/dashboard.py:412-481 |
| 4 | 예약은 모드별(strategy_switch.mode)이고, 활성 파일과 EMA 설정 파일은 모드 공용이다(D4). 계획의 `lock_state(user_id)` 에는 모드가 없다 | engine/strategy_switch.py:145, 결정 D4 |
| 5 | PULLBACK 활성이면 `is_ema` 가 거짓이라 MACD 분기를 탄다. 그래서 MACD 칸과 조건 표가 OFF 로 보인다. 지금은 PULLBACK 이 None 으로 돌아와 MACD 파일을 읽는다. 파일이 없으면 st.stop, 있으면 MACD 종목으로 강제 매매가 나간다 | pages/dashboard.py:582-592,730-759, config.py:40 |
| 6 | 강제 매수 경로: PULLBACK 이면 `force_buy_in(strategy_type=None)` 을 넘겨 시장가를 보장한다. 옛 공용 조건 파일을 읽지 않게 하려는 것이다 | engine/live_loop.py:916-922, services/trading_control.py:21 |

## PO 결정(이 질의에서 사실·위험만 확인 요청)
- **C1-a (가):** lock_state 가 잠겼고, 새 전략 보유 중(qty>0 또는 회차>0 또는 체결 대기)이거나 예약 중이면 `update_account` 를 건너뛴다. 계정 생성은 그대로 한다. D10 과 같은 판정이다. EMA 사용자 동작은 같다.
- **C1-b (가):** 「Go Dashboard」 이동은 열어 둔다. 시험 이름 `test_old_ui_locks_set_config_engine_start` 를 `test_set_config_go_dashboard_open` 으로 바꾸고, 잠금 표를 고친다. app.py 「파라미터 설정하기」 잠금을 1곳 더한다.
- **C4 (가):** PULLBACK 일 때 접힌 칸 4곳 안의 EMA·MACD 표를 「새 전략 조건은 신버전에서 확인합니다」 한 줄로 바꾼다. 종목·TP·SL·거래 시간은 적용본 값으로 보인다. 사라짐·이동·접힘은 0 이다.

## 사용자에게 올릴 결정(초안)
| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| C2 | 구버전 자동 재개(서비스 재시작 뒤 엔진 되살리기)를 새 전략 운용·예약 중에도 열어 둘지 | (가) 계획대로 잠근다. 서비스 재시작 뒤 모의 새 전략 보유분과 예약 중 모의 EMA 엔진은 사용자가 신버전에서 「엔진 시작」을 누를 때까지 멈춘다. 그동안 익절·손절이 없다. DB 정정도 하지 않고 안내 한 줄을 띄운다 / (나) 열어 둔다. 사용자가 이미 고른 상태를 되살리는 것으로 본다. 수동 「엔진 실행하기」만 잠근다 | (나). 보유분 관리가 끊기지 않는다. D7 「같은 효과를 내는 길도 잠금」의 예외가 된다 |
| C3 | 구버전 설정 저장 잠금의 범위와 실패 처리 | ① 모든 모드의 예약을 본다. 그래서 모의 예약이 있으면 실계좌 EMA 화면의 설정 저장도 잠긴다(파일이 공용이라서). ② 표가 없으면 「예약 없음」으로 본다(T12 EMA 규칙과 같음). 그 밖의 읽기 예외는 잠김 배지 「전환 예약 상태를 확인하지 못해 설정 저장을 잠시 막습니다」를 띄운다(fail closed). 강제 매수·매도·엔진 정지는 늘 열려 있다 / 대안: 입장 모드의 예약만 보고, 읽기 예외는 열어 둔다(fail open) | ①+② fail closed. 공용 파일을 지킨다. 실계좌 사용자는 모의 예약이 있거나 DB 가 잠깐 바쁠 때만 배지를 본다 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~6 이 맞는가 | 맞다고 본다 |
| 2 | C1-a 판정이 EMA TEST 사용자 동작을 바꾸지 않는가. 예약 중(활성 EMA) 건너뛰기는 맞는가. 그때 EMA TEST 엔진이 쓴 현금이 덮어써지지 않는 것도 맞는 방향인가 | 바꾸지 않는다. 예약 중에는 EMA 엔진의 현금도 지켜지므로 오히려 맞는 방향이다 |
| 3 | C2(나)가 D7·요청서 6절과 충돌하는가. 자동 재개를 열 때 잠금 상태(예약 중)의 EMA 엔진이 다시 켜지면, T12 래퍼(attach 때 설치)가 매수 차단을 그대로 거는가 | 충돌은 D7 문구뿐이라 사용자 결정이 필요하다. 래퍼는 attach 에서 설치되므로 걸린다고 본다 |
| 4 | C3 ①이 실계좌 EMA 사용자에게 주는 영향(설정 저장 잠김)이 위 표대로인가. 표가 없을 때와 예외일 때의 구분이 T12 규칙과 맞는가 | 맞다 |
| 5 | 위 표로 사용자 결정을 요청해도 되는가 | 된다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md §T15 (:272 「PO 에게 보고」, :345, 1-A), §T12 구현 메모
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/pages/dashboard.py, pages/set_config.py, pages/set_buy_sell_conditions.py, pages/settings_history.py, pages/confirm_init_db.py, app.py, services/auto_verify.py, ui/sidebar.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/boot_resume.py, engine/strategy_switch.py, core/engine_control.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-29-phase2-t12-decision-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-outline-phase2.md (D4·D7·D10)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 수정 후 진행

사실 1~6 은 모두 맞다. 래퍼는 모든 시작 경로에서 걸린다(`live_loop.py:1304` → `engine_control.py:81-84`).

**막음:**
1. C2 (가) 의 설명에 다음 결과를 적는다. 서비스를 재시작한 뒤에는 예약 전환도 진행되지 않는다. 감시 스레드는 실행 중인 모의 엔진에만 동작하기 때문이다(`strategy_switch.py:938-941`).

**권고:**
2. C1-a 를 다음과 같이 고쳐 적는다. 예약이 없는 EMA 사용자는 그대로다. 예약 중인 EMA TEST 는 덮어쓰기를 건너뛴다.
3. lock_state 의 보유 판정은 TEST 행을 읽는다고 명시한다.
4. app.py 「파라미터 설정하기」는 잠그지 않는다. 화면 이동일 뿐이고, 잠그면 set_config 로 들어가는 길이 없어진다.
5. 강제 매수 안내 `is_force_buy_fixed_price_active` 에서 PULLBACK 이면 None 을 넘긴다.
6. 계획 :1287·:1278 의 문장을 사실에 맞게 고친다.
7. 모드 없이 예약을 읽는 도우미를 만든다. 화면 경로에서는 표 없음 알림을 보내지 않는다.
8. C4 는 칸의 줄 번호를 적고, cash 에 넣을 운용자산을 정한다.

## PO 반영 (10/29)
- 막음 1 은 사용자 결정 요청문의 C2 (가)에 반영했다. Fable 의 「사용자에게 물어야 할 것」이 이미 그 문장으로 정리되어 있다. 그래서 남은 일은 사용자 결정뿐이고, 다시 묻지 않고 사용자에게 바로 묻는다.
- 권고 2~8 은 실행 지시에 넣는다.
  - 4 를 받아들여 app.py 「파라미터 설정하기」는 열어 둔다(C1-b 수정).
  - 8 의 cash 는 to_live_params 가 쓰는 운용자산과 같은 값으로 한다. 실행 에이전트가 근거를 적는다.

## 사용자 결정 (10/29 · 1029-10 「권고대로」)
- C2 (나): 구버전 자동 재개(서비스 재시작 뒤 엔진 되살리기)는 새 전략 운용·예약 중에도 열어 둔다. 수동 「엔진 실행하기」만 잠근다. D7 의 예외로 기록한다. 봇 매수 차단 래퍼는 다시 붙을 때 그대로 걸린다.
- C3 ①+②: 설정 저장 잠금은 모든 모드의 예약을 본다. 표가 없으면 「예약 없음」으로 본다. 그 밖의 읽기 예외는 fail closed 로 처리하고 잠김 배지를 띄운다. 강제 매수·매도와 엔진 정지는 늘 열려 있다.
