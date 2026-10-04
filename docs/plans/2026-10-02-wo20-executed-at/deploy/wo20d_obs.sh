#!/bin/bash
# WO-20 배포 관측 (읽기 전용). 사용: ssh ... "bash -s -- '<START KST>' '<END KST>'" < wo20d_obs.sh
S0="${1:-2026-10-04 10:22:33}"; E0="${2:-$(date '+%F %T')}"
R=/root/upbit-tradebot-mvp
J() { journalctl -u tradebot --since "$S0" --until "$E0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //'; }
C() { J | grep -cF -- "$1"; }
D="file:$R/services/data/tradebot_mcmax33.db?mode=ro"

echo "== 창: $S0 ~ $E0 | HEAD=$(git -C $R rev-parse --short HEAD) active=$(systemctl is-active tradebot) start=$(systemctl show tradebot -p ExecMainStartTimestamp --value) 버전=$(grep -o 'v1\.2026\.[0-9.]*' $R/pages/dashboard.py | head -1)"

echo "== (a) 기동"
J | grep -E "BOOT-RESUME\] success|\[WARMUP\] 시드 방식|\[WARMUP\] 감사 행 보존|HTS-DETECT\] LIVE user|run_live_loop start" | cut -c1-200
echo "   BOOT-RESUME success: $(C 'BOOT-RESUME] success')  시드 long_history bars=800: $(C '[WARMUP] 시드 방식=long_history bars=800')  감사 행 보존: $(C '[WARMUP] 감사 행 보존')"
echo "   boot_seed 분기 진입 표식 — 코드 존재 확인:"
grep -n 'logger.info(f"\[SEED\] raw_last_open\|\[POSITION-APPLY\] source=\|⚠️ \[BOOT-SEED\] 봇 주문의 체결 시각 없음\|🔁 Position recovered' $R/engine/live_loop.py $R/core/position_state.py | cut -c1-150
echo "   [SEED] raw_last_open: $(C '[SEED] raw_last_open')  [POSITION-APPLY] source=boot_seed: $(C '[POSITION-APPLY] source=boot_seed')  Position recovered: $(C 'Position recovered')  [BOOT-SEED] WARNING: $(C '[BOOT-SEED] 봇 주문의 체결 시각 없음')"

echo "== (b) 체결 확정 ([OR] final)"
J | grep -F "[OR] final" | cut -c1-260
echo "   [OR] final 건수: $(C '[OR] final')"
echo "   관찰 창 orders (id>558):"
sqlite3 "$D" "SELECT id, timestamp, ticker, side, state, executed_volume, avg_price, executed_at, canceled_at, provider_uuid FROM orders WHERE id > 558 ORDER BY id;"

echo "== (e) 결함 태그"
for t in " ERROR " "Traceback" "[POS-DESYNC] class=" "Upbit에 없는 timestamp" "불일치 발견" "과거 봉 검증 실패" "database is locked" "[LOCKED-QTY]" "CRITICAL"; do echo "   '$t': $(C "$t")"; done
echo "   (따로) [POS-SYNC] WARNING 줄: $(J | grep -F 'WARNING' | grep -cF '[POS-SYNC]')  외부 스캐너 파일 요청(Missing file / MediaFileStorageError): $(J | grep -cE 'Missing file|MediaFileStorageError')"
J | grep -F "WARNING" | grep -F "[POS-SYNC]" | cut -c1-200 | head -5

echo "== (f) Bar# / 조정 / BACKFILL"
echo "   Bar# 건수: $(C 'Bar#')  처음·끝: $(J | grep -F 'Bar#' | sed -n '1p;$p' | awk '{print $2, $7}' | tr '\n' ' ')"
echo "   조정 요청 total_count 분포: $(J | grep -oE '다중 호출 시작.*total_count=[0-9]+' | grep -oE 'total_count=[0-9]+' | sort | uniq -c | tr '\n' ' ')"
echo "   조정 400 수신: $(J | awk '/다중 호출 시작/{r=($0 ~ /total_count=400/); next} /다중 호출 완료/{ if(r){match($0,/total=[0-9]+/); print substr($0,RSTART+6,RLENGTH-6)} }' | sort | uniq -c | tr '\n' ' ')"
echo "   BACKFILL '누락 봉 평가 시작': $(C '누락 봉 평가 시작')  '누락 봉 평가 |': $(C '누락 봉 평가 |')  '미확정 봉 제외': $(C '미확정 봉 제외')"

echo "== (g) '[OR] executed_at 대체' — 코드 존재 확인 후 건수"
grep -n "executed_at 대체" $R/engine/order_reconciler.py | cut -c1-150
echo "   journal: $(C '[OR] executed_at 대체')"

echo "== 매매 신호"
echo "   EMA Buy Signal: $(C 'EMA Buy Signal')  action=BUY: $(C 'action=BUY')  action=SELL: $(C 'action=SELL')"
J | grep -E "AUTO-RESUME" | cut -c1-200
