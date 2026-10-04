#!/bin/bash
# 1분봉 전환 점검 A3 (서버, 읽기 전용): 구간별 봉 확정 수 · Bar# · CONFIRMED-NO-TRADE 비율
END_NOW="$(date '+%F %T')"
cnt() {  # $1 since $2 until $3 label
  J=$(journalctl -u tradebot --since "$1" --until "$2" --no-pager 2>/dev/null)
  close=$(echo "$J" | grep -cF '[CLOCK-CLOSE] 봉 확정 감지')
  bar=$(echo "$J" | grep -cF 'Bar#')
  nt=$(echo "$J" | grep -cF '[CONFIRMED-NO-TRADE]')
  other=$((close - bar - nt))
  echo "$3 | $1 ~ $2"
  echo "   봉 확정(CLOCK-CLOSE) $close | Bar# $bar ($(awk -v a=$bar -v b=$close 'BEGIN{if(b>0) printf "%.1f", 100*a/b; else print "-"}')%) | CONFIRMED-NO-TRADE $nt ($(awk -v a=$nt -v b=$close 'BEGIN{if(b>0) printf "%.1f", 100*a/b; else print "-"}')%) | 그 밖(차이) $other"
}
echo "== 검색어 코드 존재"
grep -n "CLOCK-CLOSE\] 봉 확정 감지\|CONFIRMED-NO-TRADE\]" /root/upbit-tradebot-mvp/engine/live_loop.py | cut -c1-140 | head -3
grep -n '📊 Bar#' /root/upbit-tradebot-mvp/core/strategy_engine.py | cut -c1-120 | head -2
echo "== 집계"
cnt "2026-10-04 10:22:33" "$END_NOW" "1분봉 (WO-20 기동 이후)"
cnt "2026-10-03 21:03:46" "2026-10-04 10:22:33" "1분봉 (전환~WO-20 재시작)"
cnt "2026-10-02 10:03:18" "2026-10-03 21:02:34" "5분봉 (WO-19 기동~전환 직전 엔진 정지)"
