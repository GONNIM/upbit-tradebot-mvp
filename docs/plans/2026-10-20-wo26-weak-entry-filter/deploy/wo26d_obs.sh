#!/bin/bash
# WO-26 배포 관찰 (읽기 전용). 사용: ssh root@orionhunter7.cafe24.com "bash -s -- '<START KST>' '<END KST>'" < wo26d_obs.sh
S0="${1:-2026-10-20 17:40:50}"; E0="${2:-$(date '+%F %T')}"
R=/root/upbit-tradebot-mvp
D="file:$R/services/data/tradebot_mcmax33.db?mode=ro"
JF=$(mktemp -p /dev/shm)
journalctl -u tradebot --since "$S0" --until "$E0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //' > "$JF"
C() { grep -cF -- "$1" "$JF"; }

echo "== 창: $S0 ~ $E0 | HEAD=$(git -C $R rev-parse --short HEAD) active=$(systemctl is-active tradebot) start=$(systemctl show tradebot -p ExecMainStartTimestamp --value) NRestarts=$(systemctl show tradebot -p NRestarts --value) 버전=$(grep -o 'v1\.2026\.[0-9.]*' $R/pages/dashboard.py | head -1)"
echo "== (a) 기동"
grep -E "BOOT-RESUME\] success|run_live_loop start|CLOCK\] Initialized|\[WARMUP\] 시드 방식|\[WARMUP\] 감사 행 보존|\[CONFIG\] 적용값|\[WEAK-ENTRY\] 기동 정합 검사" "$JF" | cut -c1-260
echo "   BOOT-RESUME success $(C 'BOOT-RESUME] success')  run_live_loop start $(C 'run_live_loop start')  long_history bars=800 $(C '[WARMUP] 시드 방식=long_history bars=800')  sma200 $(C '시드 방식=sma200')  긴 이력 시드 실패 $(C '긴 이력 시드 실패')  직전 D/C 알 수 없음 $(C '직전 D/C 알 수 없음')  감사 행 보존 $(C '[WARMUP] 감사 행 보존')  [CONFIG] $(C '[CONFIG] 적용값')  WEAK 정합 $(C '[WEAK-ENTRY] 기동 정합 검사 완료')"
echo "== (c) settings_history · 조건 파일"
sqlite3 "$D" "SELECT 'settings_history', count(*), max(id) FROM settings_history;"
sqlite3 "$D" "SELECT 'id>=215', id, saved_at, source_page FROM settings_history WHERE id >= 215 ORDER BY id;"
echo "   조건 파일 sha256=$(sha256sum $R/mcmax33_EMA_buy_sell_conditions.json | cut -c1-64) mtime=$(stat -c '%y' $R/mcmax33_EMA_buy_sell_conditions.json | cut -c1-19)"
echo "== (d) 약매수 판정 로그 — 검색 문자열 코드 존재 확인 후 건수"
grep -n 'WEAK-ENTRY\] {weak.details}' $R/core/strategy_incremental.py | cut -c1-120
grep -n 'WEAK-ENTRY\] recorded\|WEAK-ENTRY\] restored\|표식이 마지막 봇 BUY 와 다름' $R/core/weak_entry.py | cut -c1-120
grep -n 'WEAK-ENTRY\] cleared' $R/core/position_state.py | cut -c1-100
echo "   [WEAK-ENTRY] 전체 $(C '[WEAK-ENTRY]')  기동 정합 검사 $(C '[WEAK-ENTRY] 기동 정합 검사')  판정(약매수 차단) $(C '약매수 차단 (D/C 뒤')  판정(익절 기준 축소) $(C '매수 진행 (익절 기준 축소)')  판정(일반) $(grep -F '[WEAK-ENTRY]' "$JF" | grep -cF '일반 매수')  recorded $(C '[WEAK-ENTRY] recorded')  restored $(C '[WEAK-ENTRY] restored')  cleared $(C '[WEAK-ENTRY] cleared')  불일치 $(C '표식이 마지막 봇 BUY 와 다름')"
grep -F "[WEAK-ENTRY]" "$JF" | cut -c1-220
echo "== (d) 매수 판정 1:1"
echo "   EMA Buy Signal $(C 'EMA Buy Signal')  action=BUY $(C 'action=BUY')  action=SELL $(C 'action=SELL')  [OR] final $(C '[OR] final')  AUDIT-REJECT $(C '[AUDIT-REJECT]')  BUY_CANCELED $(C 'BUY_CANCELED')  SURGE $(C 'Buy blocked by SlowEmaSurgeFilter')"
grep -E "EMA Buy Signal|action=(BUY|SELL)|\[OR\] final|AUDIT-REJECT|BUY_CANCELED|LIMIT BUY" "$JF" | cut -c1-220 | head -20
sqlite3 "$D" "SELECT 'buy_eval 통과(창)', id, bar_time, price, notes FROM audit_buy_eval WHERE ticker='KRW-JTO' AND overall_ok=1 AND timestamp >= '${S0/ /T}' ORDER BY id;"
sqlite3 "$D" "SELECT 'buy_eval 분포(창)', failed_keys, count(*) FROM audit_buy_eval WHERE ticker='KRW-JTO' AND timestamp >= '${S0/ /T}' GROUP BY failed_keys;"
sqlite3 "$D" "SELECT 'orders(창)', id, timestamp, side, state, provider_uuid FROM orders WHERE timestamp >= '${S0/ /T}' ORDER BY id;"
sqlite3 "$D" "SELECT 'audit_trades(창)', id, timestamp, ticker, type, reason, price, note FROM audit_trades WHERE timestamp >= '${S0/ /T}' ORDER BY id;"
echo "== (e) 결함 태그"
for t in " ERROR " "Traceback" "[POS-DESYNC] class=" "Upbit에 없는 timestamp" "불일치 발견" "과거 봉 검증 실패" "database is locked" "[LOCKED-QTY]" "CRITICAL" "[POLLUTED]" "지표 상태 복원 실패"; do echo "   '$t': $(C "$t")"; done
echo "   VERIFY WARNING 줄: $(grep -F 'WARNING' "$JF" | grep -cF '[VERIFY]')  외부 스캐너(따로): Missing file $(C 'MediaFileHandler: Missing file')  MediaFileStorageError $(C 'MediaFileStorageError')"
echo "== (e) Bar# / 조정 / BACKFILL"
echo "   봉 확정 고유 $(grep -F '[CLOCK-CLOSE] 봉 확정 감지' "$JF" | grep -oE 'ts=[0-9: -]+' | sort -u | wc -l)  Bar# $(C 'Bar#')  거래 없음 고유 $(grep -F '[CONFIRMED-NO-TRADE]' "$JF" | grep -oE 'closed_ts=[0-9: -]+' | sort -u | wc -l)  처음·끝: $(grep -F 'Bar#' "$JF" | sed -n '1p;$p' | awk '{print $1, $2, $7}' | tr '\n' ' ')"
echo "   조정 400 수신: $(awk '/다중 호출 시작/{r=($0 ~ /total_count=400/); next} /다중 호출 완료/{ if(r){match($0,/total=[0-9]+/); print substr($0,RSTART+6,RLENGTH-6)} }' "$JF" | sort | uniq -c | tr '\n' ' ')"
echo "   BACKFILL '누락 봉 평가 시작' $(C '누락 봉 평가 시작')  '지표 상태 백업' $(C '지표 상태 백업')  '지표 상태 복원 완료' $(C '지표 상태 복원 완료')  '미확정 봉 제외' $(C '미확정 봉 제외')"
grep -E "누락 봉 평가 시작|지표 상태 백업|지표 상태 복원" "$JF" | cut -c1-220 | head -6
echo "== 기동 포지션·알림"
echo "   POSITION-SYNC $(C '[POSITION-SYNC]')  boot_seed $(C '[POSITION-APPLY] source=boot_seed')  [NOTIFY] sent $(C '[NOTIFY] sent')  AUTO-RESUME $(C 'AUTO-RESUME')"
grep -E "AUTO-RESUME|AuditViewer\] Strategy detection" "$JF" | cut -c1-200 | head -5
rm -f "$JF"
