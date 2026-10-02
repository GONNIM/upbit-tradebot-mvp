#!/bin/bash
# WO-19 배포 관측 (읽기 전용). 사용: ssh ... "bash -s -- '<END KST>'" < wo19d_obs.sh
S0="2026-10-02 10:03:17"; E0="${1:-$(date '+%F %T')}"
R=/root/upbit-tradebot-mvp
J() { journalctl -u tradebot --since "$S0" --until "$E0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //'; }
C() { J | grep -cF -- "$1"; }
F() { awk -v s="[${S0/ /T}" -v e="[${E0/ /T}" '$1 >= s && $1 <= e' $R/mcmax33_engine_debug.log; }

echo "== 창: $S0 ~ $E0 | HEAD=$(git -C $R rev-parse --short HEAD) active=$(systemctl is-active tradebot) start=$(systemctl show tradebot -p ExecMainStartTimestamp --value) 버전=$(grep -o 'v1\.2026\.[0-9.]*' $R/pages/dashboard.py | head -1)"
echo "== (a) '[WARMUP] 감사 행 보존' — 코드 존재 확인 후 건수"
grep -n "감사 행 보존" $R/engine/live_loop.py | cut -c1-120
J | grep -F "[WARMUP] 감사 행 보존" | cut -c1-200
echo "   journal 건수: $(C '[WARMUP] 감사 행 보존')  failed= 포함: $(J | grep -F '[WARMUP] 감사 행 보존' | grep -c 'failed=')  engine_debug.log 안 건수: $(F | grep -cF '감사 행 보존')"
echo "== (b) 기동 구간(보존 줄 이전) '[AUDIT-UPDATE] BUY 실시간 재판정'"
WEND=$(J | grep -F "[WARMUP] 감사 행 보존" | head -1 | awk '{print $1, $2}')
echo "   보존 줄 시각: $WEND"
echo "   기동 구간 BUY 재판정: $(J | awk -v w="$WEND" '$0 ~ /\[WARMUP\] 감사 행 보존/{exit} /AUDIT-UPDATE\] BUY 실시간 재판정/{n++} END{print n+0}')  SELL 재판정: $(J | awk '$0 ~ /\[WARMUP\] 감사 행 보존/{exit} /AUDIT-UPDATE\] SELL 실시간 재판정/{n++} END{print n+0}')"
echo "   관찰 창 전체 BUY 재판정: $(C 'AUDIT-UPDATE] BUY 실시간 재판정')  (기동 뒤 실시간 판정이 자기 봉을 다시 쓰는 경우 포함)"
echo "== (d) 사후 확인 7: 시드"
J | grep -F "[WARMUP] 시드 방식" | cut -c1-220
echo "   long_history bars=800: $(C '[WARMUP] 시드 방식=long_history bars=800')  sma200: $(C '시드 방식=sma200')  '긴 이력 시드 실패': $(C '긴 이력 시드 실패')  '지표 시드 폴백': $(C '지표 시드 폴백')"
echo "== (e) 결함 태그"
for t in " ERROR " "Traceback" "[POS-DESYNC] class=" "Upbit에 없는 timestamp" "불일치 발견" "과거 봉 검증 실패" "POLLUTED" "database is locked" "ON CONFLICT clause" "CRITICAL"; do echo "   '$t': $(C "$t")"; done
echo "   Traceback 중 외부 스캐너 파일 요청(Missing file / MediaFileStorageError): $(J | grep -cE 'Missing file|MediaFileStorageError')"
J | grep -E "Missing file" | cut -c1-200 | head -5
echo "== (f) Bar# / 조정 / BACKFILL"
J | grep -F "Bar#" | awk '{print $1, $2, $7}' | tr '\n' ' '; echo
echo "   Bar# 건수: $(C 'Bar#')"
echo "   조정 400 수신: $(J | awk '/다중 호출 시작/{r=($0 ~ /total_count=400/); next} /다중 호출 완료/{ if(r){match($0,/total=[0-9]+/); print substr($0,RSTART+6,RLENGTH-6)} }' | sort | uniq -c | tr '\n' ' ')"
echo "   BACKFILL '누락 봉 평가 시작': $(C '누락 봉 평가 시작')  '누락 봉 평가 |': $(C '누락 봉 평가 |')  '미확정 봉 제외': $(C '미확정 봉 제외')"
echo "== (g) WO-12"
J | grep -E "BOOT-RESUME|AUTO-RESUME" | cut -c1-170
echo "   run_live_loop start: $(C 'run_live_loop start')  engine_runner 시작: $(C 'engine_runner 시작')"
echo "== (h) 매수 신호"
echo "   EMA Buy Signal: $(C 'EMA Buy Signal')  action=BUY: $(C 'action=BUY')  action=SELL: $(C 'action=SELL')  UPBIT-ORDER: $(C 'UPBIT-ORDER')"
J | grep -E "EMA Buy Signal|action=BUY" | cut -c1-200
