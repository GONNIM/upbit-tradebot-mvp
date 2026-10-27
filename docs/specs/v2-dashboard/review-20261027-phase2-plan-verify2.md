# 계획서 2판 verifier 2회째 — 수정 필요 (10/27)

반박·누락(심각도 순):
1. (최상) T11 강제 매수를 `_execution_lock`(strategy_engine.py:305, threading.Lock — 재진입 불가) 안에서 `force_buy_in` 으로 부르면, 지정가 모드에서 `execute_force_buy_limit_atomic`(strategy_engine.py:125)이 같은 잠금을 다시 잡아 교착 → 엔진 봉 처리·매도·손절 정지(trading_control.py:309-310). 권고: 잠금 쥔 채 force_buy_in 부르지 않음, 엔진 인스턴스 메서드가 잠금 안에서 직접 주문하고 지정가 경로는 잠금을 다시 잡지 않는 내부 함수로 나눔. 시험 `test_force_buy_fixed_price_no_deadlock`(제한 시간). 분기 밖 변경 표에 위험으로.
2. (높음) T3 BACKFILL 재생: live_loop.py:1427-1523 은 changed_ts 만 넣음. 바뀐 첫 봉부터 직전 확정 봉까지 링/local_series 로 전부 재생한다고 명시. 시험 「바뀐 봉 1개 + 바뀌지 않은 뒤 봉 5개」.
3. (높음) T12 전환 성공 판정: start_engine 은 스레드만 띄우고 True. 워밍업 완료 Event(live_loop 가 워밍업 끝에 세움)·최대 대기 시간·실패 때 복구 래퍼가 재시도하지 않게 하는 규칙. 처리 중 죽은 RESERVED·note switching 행의 기동 복구 규칙도.
4. (중) T12 예약 조회 실패 → BUY 차단인데 마이그레이션 실패 시(boot_resume.py:131-133 로그만) strategy_switch 테이블 없음 → EMA 매수 계속 막힘. 「테이블 없음 + 활성 전략 EMA/MACD」 = 예약 없음 + CRITICAL 알림, 시험.
5. (중) T6 콜백에 상태 없음(order_reconciler.py:166-167). EMA 지정가 부분 체결 뒤 CANCELED 가 `_pending_buy_uuid` 일치로 apply_entry 갈 수 있음 → 콜백에 state 인자, PULLBACK 아닌 경로는 FILLED 만. 문구는 「BUY FILLED 전부(:310 은 주문 종류 안 봄)」로. 실제 오인 방지 장치는 「체결 확정 때 포지션 수량 갱신(:535)」— 시험에 함께 고정.
6. (중) T13 audit_settings 변경 기록은 db.py:1593-1605 UPSERT(ticker, interval_sec, bar_time) 로 매분 정기 기록(live_loop.py:1018-1022)에 덮어써지고, fetch_latest_audit_settings(db.py:1527-1560)가 「엔진 적용 조건」으로 읽어 구버전에 잘못 보임 → audit_settings 를 쓰지 않고 전용 기록(strategy_switch 에 kind 추가 등), spec 4.6 문구 정정을 결정 항목(13-8)으로: (가) 전용 기록 + spec 정정(권고) / (나) audit_settings 에 겹치지 않는 키.
7. (중) live_loop.py:997 1분 스냅샷 `_do_snapshot` 이 PULLBACK 에서도 `_load_trade_conditions` 로 옛 조건 파일을 읽음 → PULLBACK 분기에서는 적용본 TP/SL 과 빈 조건으로, 시험.
8. (낮) T7 되돌림 구간: 구버전 이력 조회 WHERE 에 revert_from~revert_to 조건 넣기, mark_revert.py 는 운영 DB 쓰기 1회 → 배포 절 되돌리기 ③ 승인 범위에.
9. (낮) TEST 모드 분할 반영(reconciler 없음 → buy_market 결과로 apply_split_entry), 복구 대기 sleep(60/300/900, engine_manager.py:318) 중엔 stop 으로 안 깨어 old_thread_alive 로 전환 실패(안전) — 명시, 복구 래퍼 안 재시작(:320-326)은 쉼 표식을 안 씀 — 명시.
10. (낮) 13절 표: 13-2·13-3 에 「승인된 목차(1027-16) 문구 변경」 표시, 13-5 (가)는 잠정 봉 위 매도 신호(TP/SL/데드크로스)도 놓친다는 점 기재.
미확인: 서버 EMA 조건 파일에 「현재가 매수」가 켜져 있는지(지적 1 실현 가능성).
