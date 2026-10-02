#!/bin/bash
# WO-20 코드 인용 생성 (로컬 HEAD 기준, 읽기만)
cd /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp || exit 1
q() { echo; echo "### $1:$2-$3 — $4"; echo '```python'; sed -n "$2,$3p" "$1" | awk -v s="$2" '{printf "%5d  %s\n", s+NR-1, $0}'; echo '```'; }
echo "# WO-20 코드 인용 (HEAD $(git rev-parse --short HEAD), 서버 HEAD 786b5cb 와 엔진 코드 동일)"
echo
echo "## A1. orders.executed_at 를 쓰는 코드"
q services/db.py 109 165 "insert_order: executed_at 인자 → INSERT (기본값 None)"
q services/db.py 2064 2100 "update_order_progress: executed_at = COALESCE(executed_at, ?) (기본값 None)"
q services/db.py 2103 2146 "update_order_completed: executed_at = COALESCE(executed_at, ?) (기본값 None)"
q services/init_db.py 485 490 "열 추가 마이그레이션"
echo
echo "## A2. 체결 확인 경로"
q core/trader.py 566 580 "TEST 시장가 매수: insert_order(status='completed'), state·executed_at 없음"
q core/trader.py 779 792 "LIVE 시장가 매수: insert_order(state='REQUESTED', requested_at=now), executed_at 없음"
q core/trader.py 1082 1092 "LIVE 지정가(현재가) 매수: insert_order(state='REQUESTED'), executed_at 없음"
q core/trader.py 1201 1213 "TEST 시장가 매도: insert_order(status='completed')"
q core/trader.py 1335 1348 "LIVE 시장가 매도: insert_order(state='REQUESTED')"
q engine/order_reconciler.py 239 323 "체결 처리: wait → progress, done/cancel → finalize. exec_ts_iso 는 fill callback 에만 전달"
q engine/order_reconciler.py 324 345 "_update_order_progress: executed_at 미전달"
q engine/order_reconciler.py 346 385 "_finalize_order: update_order_completed 에 executed_at 미전달"
q services/trading_control.py 300 325 "강제 매수: trader.buy_limit / buy_market 위임"
q services/trading_control.py 360 369 "강제 매수: reconciler.enqueue → 위 OR 경로로 확정"
q core/strategy_engine.py 326 363 "LIMIT 체결 callback: entry_ts=executed_ts 를 메모리 포지션에만 반영 (orders 미기록)"
echo
echo "## A3. boot_seed 복원 경로"
q engine/live_loop.py 688 745 "기동 시 지갑 동기화 → DB seed → apply_entry 또는 ERROR 분기"
q services/db.py 1838 1853 "_fetch_one: 시각 열 값이 NULL 이면 entry_ts_iso 를 넣지 않음"
q services/db.py 1888 1913 "ORDER BY(executed_at 오름차순) · 시각 열 선택(executed_at 우선)"
q core/position_state.py 104 156 "sync_from_wallet: avg_price 복구 + entry_ts 를 동기화 시각으로"
q core/position_state.py 218 266 "apply_entry"
echo
echo "## A4. ERROR 문구"
q engine/live_loop.py 726 732 "실제로는 has_position=True 유지"
echo
echo "## C. executed_at 을 읽는 기능"
q core/strategy_engine.py 550 580 "POSITION-SYNC 자동 복구: price·entry_bar 만 사용, entry_ts=now"
q pages/dashboard.py 862 868 "대시보드 미실현 수익률: price 만 사용"
q pages/dashboard.py 2886 2890 "fetch_order_statuses: 표준출력 print 만 (화면 표시 아님)"
q services/db.py 2149 2162 "fetch_recent_fills: 호출처 없음"
q services/settings_history.py 662 705 "설정 이력 손익: executed_at 없으면 orders.timestamp 로 ±60초 매칭"
q core/filters/sell_filters.py 488 512 "정체 포지션: position.entry_ts 사용 (DB 직접 조회 아님)"
q core/strategy_incremental.py 1125 1156 "bars_held ≤ 0 → audit fallback"
