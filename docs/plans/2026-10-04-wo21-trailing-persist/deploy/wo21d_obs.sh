#!/bin/bash
# WO-21 배포 관측 (읽기 전용). 사용: ssh ... "bash -s -- '<START KST>' '<END KST>'" < wo21d_obs.sh
S0="${1:-2026-10-05 10:54:58}"; E0="${2:-$(date '+%F %T')}"
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
echo "== 대시보드 접속 표식"
grep -E "AUTO-RESUME" "$JF" | cut -c1-200
rm -f "$JF"
