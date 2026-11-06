# 1104-02 계획 — 모의 지갑이 덮일 수 있는 좁은 틈 3가지 · 2026-11-06 (2판)

- 판 이력: 1판 verifier 「고친 뒤 재검증」(반박 3 · 부분 반박 3 · 지적 12, 11/06 대화 안) → 2판 verifier 「고친 뒤 재검증」(문장 3곳) → 2판 고침(이 판). PO 구현 결정 2건: ① 1분 동기화 건너뜀에도 캐시 평단이 업비트 평단과 다른 종목은 entry_price 0(수량 합 비교는 뺌) ② 그 쓰기는 order_reconciler 안 한 문장 SQL(db.py 바이트 고정 유지).

- 등록: HANDOFF.md 1104-02 · 발견 근거 `docs/specs/v2-dashboard/investor-notice-1101-04-draft.md` 「verifier 반영」 (가)(나)(다), `docs/fable/2026-11-04-1101-04-notice-1.md` 6번.
- 앞 계획: `docs/plans/2026-11-03-mock-wallet-overwrite/plan.md` (1029-12 — W·C1~C4, 서버 eff249a 부터 반영).
- 목차 이력: 목차 1판·2판 verifier 「고친 뒤 재검증」 → 3판 「사용자 결정 요청 가능」(11/06 대화 안, 파일 없음) → Fable `docs/fable/2026-11-06-1104-02-outline-1.md` 2회 「수정 후 진행」 → 막음 2건 반영 → 사용자 결정.
- **사용자 결정 (11/06): 「1104-02 ㉠ 가, ㉡ 저장」** — ㉠ 가 = 예약 중 실계좌 시작은 사람이 누르는 단추 두 곳만 막음, ㉡ = 이 파일에 저장.
- 범위 밖: 표 나누기(모드 칸·새 캐시 표) — 1029-12 D1 (나)와 같은 이유로 하지 않는다.

## 0. 서버 사실 (11/06 14:21 KST 읽기 전용, `sqlite3 -readonly`)
| DB | 미체결(REQUESTED·PARTIALLY_FILLED, provider_uuid 있음) | 예약(RESERVED) | engine_status |
|---|---|---|---|
| tradebot_mcmax33.db | 0 | 0 | mcmax33 is_running=1 last_mode=LIVE |
| tradebot_gon1972.db | 0 | 0 | gon1972 0 TEST |
| tradebot_default.db | 0 | 0 | 없음 |
| tradebot_.db | (orders 에 provider_uuid·state 칸 없음) | (표 없음) | 빈 사용자 0 TEST |

→ 「실계좌 실행 중 + 모의 예약」 사용자 0명. ㉠ 가의 남는 틈(예약을 둔 채 이미 돌던 실계좌)은 지금 해당 없음. 배포 직전에 한 번 더 읽는다.

## 1. 사실 (코드)
F1. 실주문 마감 `engine/order_reconciler.py` :599-600 은 `update_account_from_balances`·`update_position_from_balances` 를 지킴 검사 없이 부른다(감사 기록 :571-595 다음).
F2. `load_inflight_from_db`(:223-250)는 미체결 행 사용자를 `_live_user_ids` 에 넣는다(:249). 호출은 engine_manager.py:455-458(실계좌 시작, `_live_users` 빌 때), PULLBACK 실계좌 거부(:655-669)보다 앞. `fetch_inflight_orders()` 는 기본 사용자(mcmax33) DB 하나만 읽는다(services/db.py:2217 — 설명 글 「전체 조회」와 다름). 다른 사용자 미체결이 복구되지 않는 기존 동작은 바꾸지 않는다.
F3. 1분 동기화 `_periodic_balance_sync`(:773~)는 `_live_user_ids` 모든 사용자에 원화(:806)·HTS 감지(:828-865)·포지션(:911·914) 갱신을 한다.
F4. 구버전 실계좌 화면: 예약 중·예약 확인 실패면 수동 시작·설정 이동을 연다 — 같은 변수 `_pb_start_locked`(pages/dashboard.py:166-169, 시작 단추 :657-664, 설정 이동 :710-715). 결정 1029-11 B (나), 커밋 4e86afb.
F5. 신버전 시작 `engine/control_requests.py:728-757 _engine_start` 는 예약을 보지 않는다(실행 중 모드·옛 스레드만). 신버전 단추는 엔진이 꺼져 있으면 늘 열린다(v2/static/ops.js:82). 신버전 예약 조회는 모드별이다(v2/control.py:163).
F6. 같은 사용자의 모의 엔진이 돌면 실계좌 시작은 MODE-LOCK 거절(engine_manager.py:431-445). 그래서 F4·F5 틈은 모의 엔진이 멈춘 채 예약이 남았을 때(또는 읽기 실패)만 생긴다.
F7. `ui/pullback_lock.py:207-211 keeps_wallet` 설명 「이때 실계좌 엔진은 시작할 수 없다」는 예약·보유·읽기 실패 때 틀리다(거부는 활성 전략 PULLBACK 일 때만, engine_manager.py:655).
F8. 실계좌 수량은 업비트에서 읽고(position_state.py:101, trader.py:392-398), 손절 평단은 메모리 position.avg_price(sell_filters.py:63)다. DB 캐시(account_positions)는 ① 평단이 비었을 때 1순위 복구(position_state.py:117-124) ② HTS 감지 기준 수량(order_reconciler.py:828-831)에 쓰인다.
F9. 회귀 고정 기준: order_reconciler.py(baseline_commits.py:39 f4aac1f AST · :53 FIXED_FILES_COMMIT c0559e3, t11 :1271-1282, T8 마감 원본 비교 t8_pullback_audit.py:308-320), pages/dashboard.py(t15 :191-198·:1170-1174). engine_manager.py·boot_resume.py·live_loop.py·position_state.py 는 이 계획에서 건드리지 않는다. control_requests.py 는 고정 기준 없음(t11 :713-719 「_execution_lock 안 씀」 검사만).
F10. 영향: 지금 틈은 모의 새 전략 분할 상태 초기화·추가 분할매수 멈춤(실자산 무관). G1 은 G1-m 을 함께 넣어야 실자산 무관.
F11. 주문 추적 등록 `enqueue`(order_reconciler.py:70)도 사용자를 `_live_user_ids` 에 넣는다 — 엔진 없는 실계좌 강제 매매(trading_control.py:174·:367, control_requests.py:780-794). 예약 중 강제 매매는 열려 있다(pullback_lock.py:41).
F12. 정상 정지·예외 종료 모두 사용자는 `_live_user_ids` 에 남는다 — `unregister_user` 호출은 C1(order_reconciler.py:82) 한 곳뿐, 정지(engine_manager.py:553-562)는 엔진 관리자 쪽 `_live_users` 만 비운다.
F13. 자동 재개(engine/boot_resume.py:63-71·147-149, 구버전 화면 dashboard.py:440-452)는 예약을 보지 않는다. 시작은 모두 start_engine(engine_manager.py:299-330)으로 모인다.
F14. 구버전 잠금 판정은 화면을 그릴 때(dashboard.py:154) 한다. 단추를 누르면 화면 전체가 다시 실행돼 판정도 새로 하므로(fragment 는 :1442 에만), 「누른 직후 재검사」는 그 사이 수 밀리초를 줄이는 보강이다.
F15. engine_manager.get_running_mode(:285-297)는 잠금 없이 사전 조회·is_alive 만 한다. order_reconciler 는 engine_manager 를 불러오지 않고 반대 방향 불러오기가 있다(engine_manager.py:30, reconciler_singleton.py:4).
F16. 실계좌 기동 순서: PositionState 생성(live_loop.py:1162) → sync_from_wallet(:1167, 평단 DB 캐시 1순위) → 봇 주문이 있으면 _apply_boot_seed(평단 그대로) → register_user(:1210) → StrategyEngine(:1320).
F17. 진입가 캐시(account_positions.entry_price)를 읽는 곳은 position_state.py:121(실계좌만 — TEST 는 :93-97 에서 먼저 돌아감)·strategy_engine.py:781(업비트 평단 다음 2순위)·v2/api_read.py:500(화면)뿐이다. 모의 거래기는 entry_price 를 쓰지 않는다(update_coin_position 기본 None = 기존 값 유지, services/db.py:752-763 「LIVE 전용」, trader.py:1623·1644). 0 은 「진입가 없음」(get_position_entry_price 0 → None, db.py:887-889).

## 2. 바꿀 것
### G1. 쓰는 곳에서 지킴 (가)(나) + F11·F12
- 자리: 마감 처리 :599-600, 1분 동기화 사용자 반복(:806 앞 — 원화·HTS 감지·포지션 모두).
- 조건: 그 사용자의 실계좌 엔진이 실제로 살아 있지 않고(주입 함수 → get_running_mode != "LIVE") W(keeps_wallet) 가 참이면 건너뛴다. 명단 정리는 하지 않는다(F12).
- 판정 함수 주입: 엔진 관리자가 Reconciler 를 켜기 전에(engine_manager.py:455 앞 — 이 줄은 바꾸지 않고 reconciler_singleton 생성 쪽에서 넣는 방안을 구현 때 고른다, 건드릴 파일이 engine_manager.py 로 늘면 F9 고정 기준 이동 추가) 「실계좌 엔진 살아 있음」 함수를 넣는다. 주입이 없으면 지금 동작 그대로.
- W 판정: services/auto_verify.py:124-130 처럼 감싸 예외면 지키는 쪽. Reconciler 잠금(`_lock`) 밖에서 계산. 실계좌 엔진이 살아 있는 사용자에게는 W 를 부르지 않는다. 1분 동기화 1회 안에서 사용자별 W 는 한 번만 계산한다(lock_state 는 sqlite 읽기를 최대 3초씩 2번 — pullback_lock.py:60-63. 그동안 같은 스레드의 실주문 마감 확인이 늦어질 수 있음).
- 새 의존: 엔진(order_reconciler) → ui.pullback_lock(맨 위는 표준 라이브러리만, 함수 안에서 services.db — :22-27·:53). G3 신버전 거절도 같다.
- 로그: `[OR] 모의 지갑 지킴 — 실계좌 잔고 반영 건너뜀 | user= where=finalize|sync` (같은 사용자·같은 자리는 한 번만 INFO, 이후 DEBUG).
- 감사 기록(insert_trade_audit)·주문 표 갱신은 그대로.
### G1-m. 건너뛸 때 그 종목 진입가 캐시만 비움 (Fable 막음 반영)
- 마감 처리에서 건너뛸 때 그 종목 행의 entry_price 만 0 으로 쓴다(원화·수량 그대로).
- 1분 동기화에서 건너뛸 때도, 이미 받아 온 잔고에서 「캐시 진입가 > 0 이고 업비트 avg_buy_price 와 다른」 종목은(캐시 읽기는 order_reconciler 안 한 문장 SELECT — get_position_entry_price 는 예외·0·행 없음을 모두 None 으로 돌려줘 읽기 실패를 구분하지 못함, db.py:887-891. 종목 모양은 같은 두 모양 규칙) entry_price 만 0 으로 쓴다(건너뛰는 동안의 업비트 앱 매수는 업비트 평단을 바꿈 — verifier 지적 1, PO 결정 ①, 2판 재검증 뒤 평단만 비교로 좁힘). 캐시가 이미 0·행 없음이면 쓰지 않는다(매분 쓰기 없음). 캐시 읽기 예외면 0 을 쓴다(지키는 쪽). 수량 합은 비교하지 않는다(건너뛰는 동안 표의 수량은 모의 수량이라 늘 달라짐). 업비트 호출은 늘지 않는다(이미 받은 잔고 사용). 놓치는 경우: 같은 평단으로 사고 같은 양을 판 경우 — 평단이 같으므로 실매매 영향 없음.
- 쓰는 방법(PO 결정 ②): order_reconciler 안에서 한 문장 `UPDATE account_positions SET entry_price=0 WHERE user_id=? AND UPPER(ticker) IN (?, ?)`(「KRW-XXX」와 「XXX」 두 모양, 정규화는 기존 update_position_from_balances 규칙과 같게 — 구현 때 db.py:2429-2456 확인). update_coin_position 은 쓰지 않는다(수량을 다시 써 모의 거래기 쓰기와 경합·position_history 행 추가 — db.py:752-787). services/db.py 는 바꾸지 않는다(바이트 고정 유지). DB 연결은 기존 get_db 를 불러 쓴다.
- 이유: 그 뒤 실계좌 엔진이 켜지면 sync_from_wallet(F16)이 평단을 DB 캐시 1순위로 복구한다. 0 이면 2순위 업비트 avg_buy_price(position_state.py:129-139)로 간다 — 이때 기동 때 잔고 조회가 1회 더 생긴다(포켓당 초당 30회 안, 업비트 공식 한도 문서 11/06 verifier 확인). 메모리 표시가 아니라 재시작을 넘겨도 닿는다.
- 모의 쪽 영향: 모의 거래기는 entry_price 를 쓰지 않는다(F17). 모의 엔진의 외부 매수 복구 2순위(strategy_engine.py:781)는 낡은 실계좌 평단 대신 3순위(orders 마지막 봇 BUY)로 간다.
- 체감 변경: 모의 투자에서 새 전략을 쓰는 동안 엔진 밖 실계좌 체결이나 업비트 앱 매수가 있었던 종목은 신버전 진입가·수익률 칸(v2/api_read.py:500-503)이 비어 보일 수 있다. 실계좌 엔진을 다시 켜면 업비트 평단으로 다시 채워진다.
### G3 (가). 사람이 누르는 실계좌 시작만 막음 (다)
- 구버전 단추: `_pb_start_locked` 를 시작용·설정 이동용 둘로 나눈다. 실계좌 화면 시작 단추는 예약 중·예약 확인 실패면 잠그고, 누른 직후(:662 안, start_engine 직전) 예약을 모든 모드 기준(ui/pullback_lock.reservation_any_mode :77-96)으로 다시 읽어 있거나 읽기 실패면 거절(F14). 설정 이동은 지금처럼 열림(1-B 화이트리스트).
- 신버전 단추: control_requests.py `_engine_start` 에서 mode=LIVE 이고 모든 모드 예약(SWITCH·REVERT)이 있거나 읽기 실패면 거절. 검사 자리는 기존 검사(이미 실행 중 · 모드 충돌 · 옛 엔진, :730-740) 뒤, start_engine 앞 — 기존 결과 코드 순서를 그대로 둔다(시험으로 고정). 새 결과 코드 `live_reserved`(이름은 구현 때 확정) · CODE_TEXT 문구 「모의 투자의 전환·복귀 예약이 있어 실계좌 엔진을 켤 수 없습니다. 모의 투자 화면에서 예약을 취소한 뒤 켜십시오」(실계좌 신버전 화면은 그 모드 예약만 보여 주고 취소 단추도 그때만 열림 — v2/control.py:163, ops.js:79) · 알림 문구. 구버전 화면 안내도 같은 문구. 엔진 → ui.pullback_lock 새 의존(표준 라이브러리만 불러옴, pullback_lock.py:22-27).
- start_engine·자동 재개(boot_resume, 구버전 화면 자동 재개)는 바꾸지 않는다 — 이미 돌던 실계좌를 되살리는 길이라 막으면 손절 공백.
- 1029-11 B (나)의 「수동 시작 열기」만 되돌린다(당시 근거 「T12 전환 안전」은 그대로 참, 새 근거는 모의 지갑 덮어쓰기). 1029-10 C2 는 그대로. 승인 요청서 v2 6절 잠김 표(「엔진 시작 잠김 · 전환 예약 중에도 똑같이 잠급니다」)와 맞아진다.
### G4. keeps_wallet 설명 정정
- 「새 전략이 켜져 있으면 실계좌 엔진은 시작할 수 없다. 예약 중이면 사람이 누르는 실계좌 시작은 막히나 자동 재개는 된다(1104-02)」.

## 3. 실패 경로
- R1 실계좌 BUY 체결(엔진 없는 강제 매수 포함) 수량 갱신을 건너뛴 뒤 그 사용자가 실계좌를 켜면 첫 동기화가 수량 증가를 HTS 추가매수로 볼 수 있다(봇 매수 30초 창 밖, order_reconciler.py:828-865) → 평단·트레일링·정체 시계를 업비트 평단으로 다시 맞춤(strategy_engine.py:446-476). 같은 표를 쓰는 데서 오는 기존 위험(1029-12 R1)과 같은 종류. 시험으로 동작을 고정한다.
- R2 「LIVE 아님」으로 잘못 보는 구간: 실계좌 시작 직전 수 밀리초(Reconciler 시작 :456 이 `_engine_mode` :496 보다 앞), 정지에서 상태를 지운 뒤(join 이 끝나거나 10초가 다 된 뒤 :537-541 — 시간이 다 되면 옛 스레드가 살아 있어도 None). join 동안에는 「LIVE」로 본다. W 참이면 그 체결 캐시 갱신 1회가 빠지고 entry_price 0(G1-m) — 다음 실계좌 시작은 업비트 평단으로 복구.
- R3 실계좌 화면은 DB 캐시를 보여 주므로 건너뛴 동안 보유가 옛 값으로 보인다.
- R4 강제 매도 수량은 업비트에서 읽으므로(trading_control.py:86) 캐시가 낡아도 두 번 팔지 않는다.
- R5 (기존 위험, 기록) 예약 중 로그인 검증이 지갑을 건너뛴 뒤(1029-12 C2) 자동 재개로 실계좌가 켜지면 평단 1순위 복구가 그 종목의 낡은 캐시를 쓸 수 있다. 로그인 검증이 건너뛰면(C2, auto_verify.py:91-93, app.py:426-428) 캐시는 건너뛰기 직전에 쓴 실계좌 값 그대로다. 그 사이 봇·강제 매매 체결은 마감 처리 G1-m 이, 업비트 앱 매수는 1분 동기화 G1-m(평단 비교)이 entry_price 를 0 으로 둔다. Reconciler 가 멈춰 있던 동안의 앱 매수는 1분 동기화가 돌지 않아 잡지 못한다 — 이때 실계좌 기동 첫 1분 동기화의 HTS 감지(수량 증가)가 평단을 다시 맞추나, 수량 합이 같으면(앱 매수 뒤 같은 양 앱 매도 등) 잡지 못한다. 첫 동기화 전 최대 60초는 낡은 평단이 쓰이고, 비교 대상 캐시 수량도 모의 수량일 수 있다(기존 위험, 기록). G3 가로 사람이 켜는 길은 막힌다.
- R7 캐시 0 인데 기동 때 업비트 잔고 조회가 실패하면 avg_price 가 None — 기존 방어: CRITICAL 알림·불변 검사(position_state.py:164-193), 봇 주문이 있으면 _apply_boot_seed 가 주문 가격 사용(live_loop.py:709-712), 없으면 매도 판정이 멈추고 알림. 시험 1건.
- R6 ㉠ 가의 남는 틈: 예약을 둔 채 이미 돌던 실계좌는 자동 재개로 계속 돌고 모의 지갑이 덮인다 — 11/06 서버 0명(0절), 배포 직전에 다시 셈.

## 4. 시험
- G1: 마감·동기화 × 실계좌 엔진 있음/없음 × W 참/거짓 · 주입 없음 → 원본과 같은 호출 · 판정 예외 → 지킴 · 실계좌 엔진 사용자에게 W 호출 0회 · enqueue 길 · 정지 뒤 명단에 남은 사용자 · W 판정이 잠금 밖.
- G1-m: 건너뛴 마감 → 그 종목 entry_price 0, 원화·수량·position_history 그대로 · 이어서 실계좌 기동 → sync_from_wallet 뒤 평단이 업비트 값(복구 단계를 지나서 단언) · 프로세스 재시작을 흉내 내도 같음 · 1분 동기화 건너뜀: 캐시 진입가 > 0 이고 업비트 평단과 다른 종목만 entry_price 0, 같거나 이미 0·행 없음은 안 씀(매분 쓰기 없음), 캐시 읽기 예외면 0 · 「건너뛰는 동안 앱 매수 → 실계좌 기동 → 업비트 평단」 · 「KRW-XXX」「XXX」 두 모양 · R7(캐시 0 + 기동 조회 실패 → 기존 CRITICAL 경로).
- W 계산 횟수: 1분 동기화 1회에 사용자당 1번.
- R1: 건너뛴 강제 매수 뒤 실계좌 등록 → 첫 동기화 동작 고정.
- G3: 구버전 실계좌 단추 잠김·누른 직후 재검사 거절(예약 생김·읽기 실패)·설정 이동 열림·모의 화면 그대로 · 신버전 LIVE 거절 코드·문구·알림, TEST 그대로, 예약 없음이면 지금과 같음 · 자동 재개 그대로(boot_resume·화면 자동 재개).
- G3 검사 순서: 이미 실행 중·모드 충돌·옛 엔진이 먼저 나오는지(기존 결과 코드 그대로).
- 뒤집을 시험(이유 주석): tests/regressions/test_r_2026_10_29_p4_t15_old_ui.py `test_live_reservation_unknown_opens_start`(:522) · `test_live_reservation_start_click_starts_live`(:530-539) · 같은 묶음 :504-540 의 실계좌 시작 열림 단언. `test_live_reservation_set_config_still_locked`(:541)는 그대로.
- 예약 조회를 가짜로 바꿀 기존 실계좌 시작 시험(로컬 사용자 DB 예약 행 때문에 뜻밖에 거절되지 않게): test_r_2026_11_01_engine_start_overlap.py :206·:216·:218·:224 · test_r_2026_10_28_p4_t11_control.py :326 · tests/v2/test_control.py 의 실계좌 시작.
- 기준 이동: order_reconciler.py(AST·파일 기준·T8 마감 원본 비교 — 바뀐 함수만), pages/dashboard.py(t15 화면 기준). 바꾼 이유를 baseline_commits.py 주석에. 고친 시험은 이유 주석.
- 게이트: `bash scripts/regression_gate.sh` 전체 통과.

## 5. UI·버전·배포·통보
- UI 1-A: 구버전 실계좌 화면 예약 중 「엔진 실행하기」가 잠김 표시로 바뀜(사라짐 변화) · 신버전 실계좌 시작이 거절 문구로 끝남. 배포 뒤 브라우저 실측. 1-B 설정 이동 단추는 열린 채.
- 버전: 런타임 파일 변경 → pages/dashboard.py 버전 갱신.
- 배포: order_reconciler.py 는 엔진 프로세스 → tradebot 재시작 필요(dashboard.py·control_requests.py 도 엔진 서비스). tradebot-v2 는 바뀌는 파일 없음(v2/ 안 건드림 — 구현 때 확인). 배포 전 서버 읽기 전용: 0절 다시. 배포는 따로 승인.
- 배포 영향: tradebot 재시작 때 mcmax33 실계좌 엔진이 boot_resume 으로 다시 켜진다(tradebot_boot.py 한 프로세스) — 배포 요청서에 재시작 시각(봉 경계 피함)·보유·미체결 확인을 넣는다.
- 배포 뒤 관찰: 1시간(project-rules 워크플로우 8) — journal 의 `[OR] 모의 지갑 지킴` 줄 수(mcmax33 은 0 이어야 함) · ERROR · 실계좌 1분 동기화 정상.
- 되돌리기: 서버에서 직전 커밋으로 `git reset --hard <배포 전 HEAD>` 뒤 tradebot 재시작(DB 스키마 변경 없음, entry_price 0 은 다음 실계좌 동기화가 다시 채움). 되돌리기도 서버를 바꾸는 일이라 실행 전 사용자 승인.
- 통보: 체감 변경 2가지(실계좌 시작 거절 · 모의 새 전략을 쓰는 동안 엔진 밖 실계좌 체결·앱 매수가 있던 종목의 진입가·수익률 칸이 비어 보일 수 있음). 11/05 통보 8번이 「모의 예약이 있을 때 실계좌 기존 화면에서 엔진 실행하기를 쓰실 수 있습니다」를 알렸으므로 고친 내용을 한 번 통보한다(운영자 발송). 보낸 뒤 docs/operations/investor-notice-log.md 에 한 줄 기록.

## 5-1. Fable 권고 반영 (docs/fable/2026-11-06-1104-02-plan-1.md 「진행」, 권고 6)
- 판정 방법: 「실계좌 엔진 살아 있음」은 주입 대신 `core.engine_control.alive_engine_threads(user)`(표준 라이브러리만, 이름 `…_LIVE` 스레드)로 하는 안을 먼저 검토한다 — 순환 불러오기가 없고 R2 의 「join 시간 초과 뒤 None」 구간이 사라진다(1101-05 가 같은 함수를 시작 거절에 씀). 시험: `run_live_loop_<user>_LIVE` 스레드가 살아 있으면 건너뛰지 않음 · `import engine.order_reconciler` 가 engine_manager 를 불러오지 않음(sys.modules). 주입 안으로 가면 reconciler_singleton 지연 불러오기 + get_reconciler 가짜 시험 3개 확인.
- 평단 비교 허용 오차: 상대 1e-9. 시험 「문자열 자릿수만 다르면 쓰지 않음」.
- 실패 경로 R8: 1분 동기화는 업비트 잔고에 있는 종목만 비교하므로 캐시에만 남은 종목(앱 전량 매도)의 entry_price > 0 은 남는다 — 실계좌 기동 때 수량 0 이면 복구를 타지 않아(position_state.py:103-110) 실매매 영향 없음, strategy_engine.py:781 2순위에서만 닿음(기록).
- 실패 경로 R9 (G3 가 체감): 실계좌 엔진이 복구 횟수를 다 쓰고 멈춘 사용자가 모의 예약을 둔 채면 사람이 켜는 길이 막혀 예약을 취소해야 다시 켤 수 있다 — 손절 공백이 생기는 유일한 경우. 거절 문구 「모의 투자 화면에서 예약을 취소한 뒤 켜십시오」가 이 경우를 덮고, 통보·운영자 대응에 넣는다.
- T8 원본 비교: G1 의 새 속성은 모두 기본값(주입·판정 없음 = 지금 동작) — 게이트 전체 + T8 묶음 단독 실행.
- 관찰 기준: `[OR] 모의 지갑 지킴` 은 사용자·자리별 첫 줄만 INFO 이므로 journal 관찰은 INFO 줄 원문 검색어로 센다(배포 요청서에 검색 문자열 원문).

## 6. 순서
1. 이 계획서 verifier → Fable → 사용자 구현 승인.
2. 구현(G1·G1-m → G3 → G4) · 시험 · 게이트 · verifier · Fable → 커밋·push 승인.
3. 배포 요청서(엔진 재시작 시각·정지선) → 배포 승인 → 배포 → 통보.
