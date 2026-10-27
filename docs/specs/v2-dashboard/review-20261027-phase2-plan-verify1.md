# 계획서 초안 verifier 1회째 — 수정 필요 (10/27)

반박(판정표): 13 load_applied/load_for_boot 이름 불일치 · 18 워밍업 재시도는 min_hist+1 만 요청(live_loop.py:1141) · 21 원본은 감시 구간에서 justCrossedGolden 없이도 눌림목 1회차를 삼(원본 HTML:343-357, :352) → T4 시험 test_no_buy_right_after_start_in_golden 과 T10 충돌 · 22 잠정 봉은 on_new_bar(764) 가 아니라 on_new_bar_confirmed 로 is_confirmed=False, O=H=L=C 로 들어옴(live_loop.py:1788-1800) · 25 register_pending_buy_uuid 를 쓰면 _on_limit_fill 이 apply_entry(이번 회차 값) 로 누적을 덮어씀(strategy_engine.py:419-450, order_reconciler.py:310-324). HTS 판정은 has_recent_bot_buy_for_ticker(30초)(order_reconciler.py:771-776) · 32 LIVE 체결 행은 order_reconciler.py:506-529 가 쓰고 meta 를 넣지 않음 · 39 1-2 측정 날짜 틀림(실제 기동 2026-10-26 00:25:30, count=801 1회 성공) · 40 app.py:394 수동 검증도 save_user(krw_balance) · 42 PULLBACK 조건 파일이 없으면 {user}_buy_sell_conditions.json 으로 폴백(live_loop.py:624-631), 서버에 그 파일 있음(386B) · 49 되돌린 동안 쓴 행이 재배포 후 분류 불명 · 52 시험 이름 test_audit_viewer_button_top_level 없음(실제 test_button_in_header_column_context 등).
오차: computeSlope 218-227, 원본 루프 296행, tradebot_boot main 120행, 요청 수 2,012(_long_bars+1).

지적:
- F1(높음) T6 봇 매수 오인 방지 수단 틀림 → uuid 등록하지 않고 _on_limit_fill 에 PULLBACK 분기(apply_split_entry), 「봇 매수 30초」 판정을 시험으로 고정.
- F2(높음) LIVE 분할 체결 실수량·평단 반영 경로 없음(trader.py:595,819-833 추정 수량) → 체결 콜백 executed_qty·avg 로 분할 상태 바로잡기, desync 판정 전 체결 대기 회차 제외 시험.
- F3(높음) 원본은 골든크로스 없이 눌림목 1회차를 삼 — 요청서 3절·spec 3절 85행과 다름 → 사용자 결정(가: 원본 일치 + 통보 B 한 줄 / 나: 기동 뒤 첫 골든크로스 전 매수 금지).
- F4(높음) 잠정 봉 처리 미정 → is_confirmed=False 일 때 PULLBACK 규칙, 확정값 오면 그 봉부터 재생 시험. 권고: 잠정 봉은 지표에 넣지 않음.
- F5(중상) 워밍업 재시도 봉 부족 → PULLBACK 은 min_hist 도 required_bars, 모자라면 기동 거부·알림, 시험.
- F6(중상) T14 운용 설정 저장이 apply_params 로 저장본 전체 적용 → 거래 시간 4키만 적용본에 합치는 별도 요청, 「저장만 한 값은 운용 설정 저장 뒤에도 적용본에 없음」 시험.
- F7(중) stop_engine join 10초 뒤 상태 지움(engine_manager.py:259-268) → 옛 스레드 종료 확인 뒤에만 시작, 넘기면 FAILED, 시험.
- F8(중) 전환 때 미체결 매수 주문 확인 없음 → 미체결 BUY 있으면 예약 또는 거절.
- F9(중) 즉시 전환 start 실패 처리 없음 → 기동 성공 뒤 DONE, 실패 시 FAILED·CRITICAL·활성 파일 되돌림, 시험.
- F10(중) 신버전 강제 매매를 엔진 _execution_lock 없이 실행 → 엔진 잠금 안에서, 동시 실행 시험.
- F11(중) 프로세스 안 재시작은 pid 같음, 세대 값 5초 지연 → 재시작 직전에 쉼 표식을 먼저 쓰기, 시험.
- F12(중) 회차 건너뜀 뒤 armed 처리·알림 dedupe 없음 → armed 규칙 명시, dedupe_key.
- F13(중) 옛 조건 파일 폴백 → PULLBACK 은 조건 파일을 아예 읽지 않게 분기.
- F14(중) LIVE 체결 행 회차·평단 미기록 → T8 Files 에 order_reconciler, orders.meta split_round 옮김.
- F15(중) BACKFILL 과 링 버퍼 연결 위치 미정(live_loop.py:649 이하, :1500-1523) → T3 에 명시.
- F16(중) 재시작 시험 조건(실서버 워밍업은 최근 봉으로 재시드, EMA 잔차) 명시, 실서버 재시작 뒤 판정 변화는 위험·관찰 항목.
- S1(중) 신버전 침해 시 요청 파일로 주문 유발 가능 → 영향표에 적고 요청 종류별 알림.
- D1(중) 마이그레이션이 페이지 실행마다 BEGIN IMMEDIATE → 읽기로 먼저 확인, 다 있으면 쓰기 없이 끝냄.
- D2(중) 되돌린 뒤 재배포 때 분류 불명 → 재배포 규칙·시험.
- D3(낮) 「칸은 있고 표식 없음」 보정 기준 모호 → 정의하거나 지움.
- R1(중) spec 4.6 「변경 사실과 적용 시점을 audit_settings 에」 누락 → T13.
- R2(중) spec 4.5 hts_buy(Issue #17) 처리 미정, D11(b) 와 관계 → 규칙·시험.
- R3(중) 금지 행위 「EMA·MACD 줄은 PULLBACK 분기 안에서만」이 계획과 안 맞음(T7·T11·T12·T15 분기 밖) → 「판정 불변 + 분기 밖 변경 목록·근거」로, 예약 조회 실패 때 EMA 매수 동작 정함.
- R4(중) 결정 요청 절 없음 → X1·X2·X3, T9 시간 밖 armed·놓친 골든크로스, F3, F4, F6 결정 표.
- R5 1-2 날짜 2026-10-26 00:25. R6 D10 범위에 수동 검증(app.py:394) 넣거나 통보 문구 고침. R7 시험 이름 불일치(test_pullback_sell_reject_visible·test_entry_does_not_switch 정의 없음, test_old_ui_locks_* 개수 7 vs 9). R8 배포 전 확인에 로그 레벨·systemd 자동 재시작·비밀 파일 권한 점검. R9 문안 B 에 구버전 잠금 범위 확대·구버전 강제 매수 회차 밖·F3 결과. R10 대응표에 2-마 「(지금은 해당 없음)」, 8절 「익절 판정인데 손해」 관찰. R11 PULLBACK 이면 trader order_ratio 자동 재읽기에 params_file 넘기지 않음. R12 이름·줄 오차.

verifier 권고 결정안: 1 F3 → (가) 원본 일치 + 통보 B. 2 F6 → (가) 4키만. 3 F4 → (가) 잠정 봉 지표 제외·확정값 재생. 4 결정 표를 계획서에 둠.
