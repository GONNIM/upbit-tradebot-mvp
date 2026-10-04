#!/bin/bash
# 세션 시작 정기 점검 (읽기 전용). 사용: ssh ... "bash -s -- '<END KST>'" < sc_main.sh
S0="2026-10-04 10:22:33"; E0="${1:-$(date '+%F %T')}"
R=/root/upbit-tradebot-mvp
D="file:$R/services/data/tradebot_mcmax33.db?mode=ro"
JF=$(mktemp -p /dev/shm)
journalctl -u tradebot --since "$S0" --until "$E0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //' > "$JF"
C() { grep -cF -- "$1" "$JF"; }
G(){ journalctl -u tradebot --since "$1" --no-pager 2>/dev/null | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //'; }

echo "== 창: $S0 ~ $E0"
echo "== 1. 서버 상태"
echo "   HEAD=$(git -C $R rev-parse --short HEAD) active=$(systemctl is-active tradebot) start=$(systemctl show tradebot -p ExecMainStartTimestamp --value) NRestarts=$(systemctl show tradebot -p NRestarts --value) 버전=$(grep -o 'v1\.2026\.[0-9.]*' $R/pages/dashboard.py | head -1)"
echo "   서비스 재기동(ExecMainStart 이후): $( [ "$(systemctl show tradebot -p ExecMainStartTimestamp --value)" = "Sun 2026-10-04 10:22:33 KST" ] && echo 0 || echo '있음')  엔진 기동 run_live_loop start: $(C 'run_live_loop start')  run_live_loop 종료: $(C 'run_live_loop 종료')  BOOT-RESUME success: $(C 'BOOT-RESUME] success')  AUTO-RESUME skip: $(C 'AUTO-RESUME] skip')"

echo "== 2. 기동 이력"
grep -E "BOOT-RESUME\] success|run_live_loop start|\[WARMUP\] 시드 방식|\[WARMUP\] 감사 행 보존|POSITION-APPLY\] source=boot_seed|BOOT-SEED|\[SEED\] raw_last_open" "$JF" | cut -c1-200
echo "   시드 long_history bars=800: $(C '[WARMUP] 시드 방식=long_history bars=800')  sma200: $(C '시드 방식=sma200')  긴 이력 시드 실패: $(C '긴 이력 시드 실패')  감사 행 보존: $(C '[WARMUP] 감사 행 보존')  boot_seed: $(C '[POSITION-APPLY] source=boot_seed')  [BOOT-SEED]: $(C '[BOOT-SEED]')"

echo "== 3. 운영 상태"
echo "   봉 확정(CLOCK-CLOSE) $(C '[CLOCK-CLOSE] 봉 확정 감지') (고유 $(grep -F '[CLOCK-CLOSE] 봉 확정 감지' "$JF" | grep -oE 'ts=[0-9: -]+' | sort -u | wc -l))  Bar# $(C 'Bar#')  CONFIRMED-NO-TRADE $(C '[CONFIRMED-NO-TRADE]') (고유 $(grep -F '[CONFIRMED-NO-TRADE]' "$JF" | grep -oE 'closed_ts=[0-9: -]+' | sort -u | wc -l))"
echo "   Bar# 처음·끝: $(grep -F 'Bar#' "$JF" | sed -n '1p;$p' | awk '{print $2, $7}' | tr '\n' ' ')"
echo "   Bar# 이중(같은 ts 2회 이상): $(grep -oE 'Bar#[0-9]+ \| ts=[0-9: +-]+' "$JF" | sed -E 's/Bar#[0-9]+ \| //' | sort | uniq -d | wc -l)"
echo "   EMA Buy Signal $(C 'EMA Buy Signal')  action=BUY $(C 'action=BUY')  action=SELL $(C 'action=SELL')  FIXED-PRICE 진입 $(C '[FIXED-PRICE] 고정가 매수 모드 진입')  [OR] final $(C '[OR] final')  [OR] enqueued $(C '[OR] enqueued')"
grep -E "EMA Buy Signal|action=(BUY|SELL)|\[OR\] (final|enqueued)|FIXED-PRICE\] 고정가" "$JF" | cut -c1-220 | head -20
echo "   SELL_REJECTED/BUY_REJECTED 로그: $(grep -cE 'SELL_REJECTED|BUY_REJECTED' "$JF")"
echo "   결함 태그:"
for t in " ERROR " "Traceback" "[POS-DESYNC] class=" "Upbit에 없는 timestamp" "불일치 발견" "과거 봉 검증 실패" "database is locked" "[LOCKED-QTY]" "CRITICAL"; do echo "     '$t': $(C "$t")"; done
echo "     VERIFY WARNING 줄: $(grep -F 'WARNING' "$JF" | grep -cF '[VERIFY]')"
echo "   외부 스캐너 (따로): Missing file $(C 'MediaFileHandler: Missing file')  MediaFileStorageError $(C 'MediaFileStorageError')"
grep -F 'MediaFileHandler: Missing file' "$JF" | cut -c1-160
echo "   기타 WARNING 상위 (참고):"
grep -F ' WARNING ' "$JF" | sed -E 's/^[0-9-]+ [0-9:]+ //' | cut -c1-90 | sed -E 's/[0-9]+(\.[0-9]+)?/N/g' | sort | uniq -c | sort -rn | head -8

echo "== DB (읽기 전용)"
sqlite3 "$D" "SELECT 'orders id>558', id, timestamp, ticker, side, state, executed_volume, avg_price, executed_at, canceled_at, updated_at FROM orders WHERE id > 558 ORDER BY id;"
sqlite3 "$D" "SELECT 'audit_trades', id, timestamp, ticker, type, price, reason FROM audit_trades WHERE timestamp >= '2026-10-04T10:22:33' ORDER BY id;"
sqlite3 "$D" "SELECT 'REJECTED 행(창)', type, COUNT(*) FROM audit_trades WHERE type LIKE '%REJECTED' AND timestamp >= '2026-10-04T10:22:33' GROUP BY type;"
sqlite3 "$D" "SELECT 'account_positions JTO', virtual_coin, virtual_coin_locked, entry_price, meta FROM account_positions WHERE ticker='KRW-JTO';"

echo "== 5. 사후 확인 1~7 (기준 시각은 가이드 그대로)"
S1='2026-09-30 16:33:05'
echo "-- (1) 강제 매수: FORCE 발주 $(G "$S1" | grep -cF '[FIXED-PRICE][FORCE]')  LIMIT-FILL apply_entry $(G "$S1" | grep -cF '[LIMIT-FILL] apply_entry')  force_buy 감사 행 $(sqlite3 "$D" "SELECT COUNT(*) FROM audit_trades WHERE reason='force_buy' AND timestamp >= '2026-09-30T16:33:05';")"
echo "-- (2) HTS 승격 가드 (KRW-JTO): SELL 차단 $(G "$S1" | grep -cF 'SELL 차단 (HOLD 유지)')  streak 리셋 $(G "$S1" | grep -cF '[POS-DESYNC] streak 리셋')  class= $(G "$S1" | grep -cF '[POS-DESYNC] class=')  JTO HTS_BUY 최근: $(sqlite3 "$D" "SELECT MAX(timestamp) FROM audit_trades WHERE ticker='KRW-JTO' AND reason IN ('HTS_BUY','HTS_BUY_ADD');")"
G "$S1" | grep -E 'SELL 차단 \(HOLD 유지\)|POS-DESYNC\] (streak|class=)' | cut -c1-170 | tail -4
echo "-- (3) WO-9: HTS_BUY 감지 $(G "$S1" | grep -cF '[HTS-DETECT] HTS_BUY')  LOCKED-QTY $(G "$S1" | grep -cF '[LOCKED-QTY]')  AUDIT-REJECT $(G "$S1" | grep -cF '[AUDIT-REJECT]')  REJECTED 감사 행: $(sqlite3 "$D" "SELECT group_concat(type||':'||n) FROM (SELECT type, COUNT(*) n FROM audit_trades WHERE type LIKE '%REJECTED' GROUP BY type);")"
S4='2026-10-01 11:42:01'
echo "-- (4) WO-14 (a) 미확정 봉 제외: $(G "$S4" | grep -cF '미확정 봉 제외')  최근: $(G "$S4" | grep -F '미확정 봉 제외' | tail -1 | cut -c1-120)"
echo "-- (5) WO-14 E1 trailing 복원: 복원 $(G "$S4" | grep -cF 'trailing 상태 복원')  건너뜀 $(G "$S4" | grep -cF 'trailing 상태 복원 건너뜀')  실패 $(G "$S4" | grep -cF 'trailing 상태 복원 실패')  BACKFILL 시작 $(G "$S4" | grep -cF '누락 봉 평가 시작')"
S6='2026-10-01 18:10:24'
echo "-- (6) WO-18: HTS_BUY 감지 $(G "$S6" | grep -cF '[HTS-DETECT] HTS_BUY')  cleared(boot_reconcile 제외) $(G "$S6" | grep -F '[HTS-FLAG] cleared' | grep -vc boot_reconcile)  reason 분포: $(G "$S6" | grep -F '[HTS-FLAG] cleared' | grep -v boot_reconcile | grep -oE 'reason=[a-z_]+' | sort | uniq -c | tr '\n' ' ')"
echo "   STOP_LOSS_CHECK hts_buy: $(G "$S6" | grep -F 'STOP_LOSS_CHECK' | grep -oE 'hts_buy=(True|False)' | sort | uniq -c | tr '\n' ' ')  잔존 SQL: $(sqlite3 "$D" "SELECT COUNT(*) FROM account_positions WHERE meta LIKE '%\"hts_buy\": true%' AND COALESCE(virtual_coin,0)+COALESCE(virtual_coin_locked,0)=0;")  보유 중 hts_buy: $(sqlite3 "$D" "SELECT group_concat(ticker) FROM account_positions WHERE meta LIKE '%\"hts_buy\": true%' AND COALESCE(virtual_coin,0)+COALESCE(virtual_coin_locked,0)>0;")"
G "$S6" | grep -F '[HTS-FLAG] cleared' | grep -v boot_reconcile | cut -c1-170 | tail -3
echo "-- (7) 시드: 기동별 (창 안)"
grep -E "BOOT-RESUME\] success|CLOCK\] Initialized|시드 방식=" "$JF" | cut -c1-200

echo "== 6. 비밀 파일"
ls -l "$R/.env" "$R/.streamlit/secrets.toml"
echo "   백업 접미사 파일 (/root, 저장소 루트·하위 1단계, ls -la + awk 접미사 비교):"
for d in /root "$R" $(ls -la "$R" | awk -v r="$R" 'NR>1 && $1 ~ /^d/ && $9 != "." && $9 != ".." {print r"/"$9}'); do
  ls -la "$d" 2>/dev/null | awk -v d="$d" 'NR>1 && ($9 ~ /\.bak$/ || $9 ~ /\.old$/ || $9 ~ /\.orig$/ || $9 ~ /~$/) {print "     " d "/" $9, $1, $5}'
done
echo "   (끝 — 위에 줄이 없으면 0개)"
echo "   enableStaticServing = $($R/venv/bin/python -c 'import streamlit.config as c; print(c.get_option("server.enableStaticServing"))' 2>/dev/null)"
S7="$(date -d '7 days ago' '+%F %T')"
J7=$(journalctl -u tradebot --since "$S7" --no-pager 2>/dev/null)
echo "   7일($S7~): Missing file $(echo "$J7" | grep -cF 'MediaFileHandler: Missing file')  MediaFileStorageError $(echo "$J7" | grep -cF 'MediaFileStorageError')"
echo "$J7" | grep -F 'MediaFileHandler: Missing file' | sed -E 's/.*Missing file //' | sort | uniq -c
rm -f "$JF"
