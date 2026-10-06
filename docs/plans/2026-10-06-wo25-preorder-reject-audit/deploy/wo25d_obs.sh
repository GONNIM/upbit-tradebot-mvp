#!/bin/bash
# WO-25 배포 관측 (읽기 전용). 사용: ssh ... "bash -s -- '<START KST>' '<END KST>'" < wo21d_obs.sh
S0="${1:-2026-10-06 14:45:05}"; E0="${2:-$(date '+%F %T')}"
R=/root/upbit-tradebot-mvp
D="file:$R/services/data/tradebot_mcmax33.db?mode=ro"
JF=$(mktemp -p /dev/shm)
journalctl -u tradebot --since "$S0" --until "$E0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //' > "$JF"
C() { grep -cF -- "$1" "$JF"; }

echo "== 창: $S0 ~ $E0 | HEAD=$(git -C $R rev-parse --short HEAD) active=$(systemctl is-active tradebot) start=$(systemctl show tradebot -p ExecMainStartTimestamp --value) 버전=$(grep -o 'v1\.2026\.[0-9.]*' $R/pages/dashboard.py | head -1)"
echo "== (a) 기동"
grep -E "BOOT-RESUME\] success|run_live_loop start|CLOCK\] Initialized|\[WARMUP\] 시드 방식|\[WARMUP\] 감사 행 보존" "$JF" | cut -c1-200
echo "   BOOT-RESUME success $(C 'BOOT-RESUME] success')  시드 long_history bars=800 $(C '[WARMUP] 시드 방식=long_history bars=800')  sma200 $(C '시드 방식=sma200')  긴 이력 시드 실패 $(C '긴 이력 시드 실패')  감사 행 보존 $(C '[WARMUP] 감사 행 보존')"
echo "== (b) 재계산 경로 — 코드 존재 확인 후 건수"
grep -n 'TRAILING-RESTORE\] armed=\|TRAILING-RESTORE\] 재계산 불가\|TRAILING-RESTORE\] 건너뜀\|사유=예외' $R/core/trailing_restore.py $R/engine/live_loop.py | cut -c1-150
echo "   [TRAILING-RESTORE] 전체 $(C '[TRAILING-RESTORE]')  armed= $(C '[TRAILING-RESTORE] armed=')  재계산 불가 $(C '[TRAILING-RESTORE] 재계산 불가')  예외 $(C '사유=예외')  건너뜀 $(C '[TRAILING-RESTORE] 건너뜀')"
grep -F "[TRAILING-RESTORE]" "$JF" | cut -c1-220
echo "   기동 포지션: POS-SYNC $(grep -cE 'POS-SYNC\] (avg_price|entry_ts)' "$JF")  boot_seed $(C '[POSITION-APPLY] source=boot_seed')  BOOT-SEED $(C '[BOOT-SEED]')"
echo "== (d) 결함 태그"
for t in " ERROR " "Traceback" "[POS-DESYNC] class=" "Upbit에 없는 timestamp" "불일치 발견" "과거 봉 검증 실패" "database is locked" "[LOCKED-QTY]" "CRITICAL"; do echo "   '$t': $(C "$t")"; done
echo "   VERIFY WARNING 줄: $(grep -F 'WARNING' "$JF" | grep -cF '[VERIFY]')  외부 스캐너(따로): Missing file $(C 'MediaFileHandler: Missing file')  MediaFileStorageError $(C 'MediaFileStorageError')"
echo "== (e) Bar# / 조정 / BACKFILL"
echo "   봉 확정 고유 $(grep -F '[CLOCK-CLOSE] 봉 확정 감지' "$JF" | grep -oE 'ts=[0-9: -]+' | sort -u | wc -l)  Bar# $(C 'Bar#')  거래 없음 고유 $(grep -F '[CONFIRMED-NO-TRADE]' "$JF" | grep -oE 'closed_ts=[0-9: -]+' | sort -u | wc -l)  처음·끝: $(grep -F 'Bar#' "$JF" | sed -n '1p;$p' | awk '{print $2, $7}' | tr '\n' ' ')"
echo "   조정 400 수신: $(awk '/다중 호출 시작/{r=($0 ~ /total_count=400/); next} /다중 호출 완료/{ if(r){match($0,/total=[0-9]+/); print substr($0,RSTART+6,RLENGTH-6)} }' "$JF" | sort | uniq -c | tr '\n' ' ')"
echo "   BACKFILL '누락 봉 평가 시작' $(C '누락 봉 평가 시작')  '누락 봉 평가 |' $(C '누락 봉 평가 |')  '미확정 봉 제외' $(C '미확정 봉 제외')"
echo "== (f) 봇 매수·무장·ts_armed"
echo "   EMA Buy Signal $(C 'EMA Buy Signal')  action=BUY $(C 'action=BUY')  action=SELL $(C 'action=SELL')  [OR] final $(C '[OR] final')  ACTIVATED $(C 'Trailing Stop ACTIVATED')  AUTO-SWITCH $(C 'AUTO-SWITCH')"
grep -E "EMA Buy Signal|action=(BUY|SELL)|\[OR\] final|Trailing Stop ACTIVATED|AUTO-SWITCH|고정 금액 폭" "$JF" | cut -c1-220 | head -10
sqlite3 "$D" "SELECT 'sell_eval(창)', id, bar_time, highest, ts_armed, triggered FROM audit_sell_eval WHERE ticker='KRW-JTO' AND timestamp >= '${S0/ /T}' ORDER BY id;"
sqlite3 "$D" "SELECT 'orders(창)', id, timestamp, side, state, executed_at FROM orders WHERE timestamp >= '${S0/ /T}' ORDER BY id;"
echo "== WO-22 경로 — 코드 존재 확인 후 건수"
grep -n '\[POSITION-SYNC\] entry_price=\|외부 매도 기록 (audit_trades HTS_SELL)\|orders 마지막 봇 BUY 수량 불일치' $R/core/strategy_engine.py | cut -c1-150
echo "   [POSITION-SYNC] entry_price= $(C '[POSITION-SYNC] entry_price=')  외부 매도 기록 $(C '외부 매도 기록 (audit_trades HTS_SELL)')  수량 불일치 $(C 'orders 마지막 봇 BUY 수량 불일치')  외부 매수 감지 $(C '외부 매수 감지')  강제 포지션 종료 $(C '강제 포지션 종료')"
grep -E "POSITION-SYNC\]|HTS_SELL|HTS-DETECT\] HTS_BUY" "$JF" | cut -c1-220 | head -10
sqlite3 "$D" "SELECT 'HTS_SELL 행(창)', id, timestamp, ticker, qty, entry_price FROM audit_trades WHERE type='HTS_SELL' AND timestamp >= '${S0/ /T}';"
echo "== WO-24 경로 — 코드 존재 확인 후 건수"
grep -n '\[NOTIFY\] sent' $R/services/notifier.py | cut -c1-150
grep -n '매수 미체결 취소 기록 (audit_trades BUY_CANCELED)' $R/engine/order_reconciler.py | cut -c1-150
grep -n '\[UNFILLED-CONVERT\]' $R/core/strategy_engine.py | cut -c1-150
echo "   [NOTIFY] sent $(C '[NOTIFY] sent')  BUY_CANCELED 기록 $(C '매수 미체결 취소 기록 (audit_trades BUY_CANCELED)')  [UNFILLED-CONVERT] $(C '[UNFILLED-CONVERT]')  LIMIT BUY timeout $(C 'LIMIT BUY timeout')  [NOTIFY] 경고(전체) $(C '[NOTIFY]')"
grep -E "\[NOTIFY\]|BUY_CANCELED|UNFILLED-CONVERT|LIMIT BUY timeout" "$JF" | cut -c1-220 | head -10
sqlite3 "$D" "SELECT 'BUY_CANCELED 행(창)', id, timestamp, ticker, price, qty, note FROM audit_trades WHERE type='BUY_CANCELED' AND timestamp >= '${S0/ /T}';"
echo "   토큰·채팅 ID 노출 검사: bot 토큰 형식 $(grep -cE 'bot[0-9]{6,}:' "$JF")  chat_id= $(grep -c 'chat_id=' "$JF")"
echo "== WO-25 경로 — 코드 존재 확인 후 건수"
grep -n '_audit_preorder_reject(' $R/core/trader.py | grep -v 'def ' | cut -c1-80
grep -n '_audit_buy_blocked(' $R/core/strategy_engine.py | grep -v 'def ' | cut -c1-80
grep -n '\[AUDIT-REJECT\] {side.upper()}_REJECTED 기록' $R/core/trader.py | cut -c1-120
echo "   [AUDIT-REJECT] BUY_REJECTED 기록 $(C '[AUDIT-REJECT] BUY_REJECTED 기록')  [BUY-LIMIT] 활성 KRW 부족 $(C '[BUY-LIMIT] 활성 KRW 부족')  [BUY-LIMIT] plan $(C '[BUY-LIMIT] plan')  ❌ BUY 실패 $(C '❌ BUY 실패')  [AUDIT-REJECT] 기록 실패 $(C '[AUDIT-REJECT] 기록 실패')  엔진 주문 전 차단 기록 예외 $(C '엔진 주문 전 차단 기록 예외')"
grep -E "AUDIT-REJECT|BUY-LIMIT\]|EMA Buy Signal|❌ BUY 실패" "$JF" | cut -c1-230 | head -10
sqlite3 "$D" "SELECT 'BUY_REJECTED 행(창)', id, timestamp, bar_time, reason, price, json_extract(meta,'\$.stage'), json_extract(meta,'\$.error_name'), note FROM audit_trades WHERE type='BUY_REJECTED' AND timestamp >= '${S0/ /T}' ORDER BY id;"
echo "== 대시보드 접속 표식"
grep -E "AUTO-RESUME" "$JF" | cut -c1-200
rm -f "$JF"
