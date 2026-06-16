#!/bin/bash
# Tradebot 엔진 정체 감지 (보조 안전망) + Telegram 알림
THRESHOLD_SECS=600
LOG_FILE="/var/log/tradebot_engine_stale.log"
NOTIFIER=/root/notify_telegram.sh

last_line=$(journalctl -u tradebot --since "30 min ago" --no-pager --output=short-iso 2>/dev/null | grep -E "Bar#" | tail -1)

if [ -z "$last_line" ]; then
    msg="최근 30분간 Bar# 평가 로그 없음 (엔진 정체 가능성)"
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: $msg" >> "$LOG_FILE"
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "⚠️ [STALE] tradebot 엔진" "$msg"
    exit 0
fi

ts_iso=$(echo "$last_line" | awk '{print $1}')
last_epoch=$(date -d "$ts_iso" +%s 2>/dev/null)
if [ -z "$last_epoch" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: 시각 파싱 실패: $last_line" >> "$LOG_FILE"
    exit 0
fi
now_epoch=$(date +%s)
gap=$((now_epoch - last_epoch))

if [ $gap -gt $THRESHOLD_SECS ]; then
    msg="last Bar# was ${gap}s ago (threshold ${THRESHOLD_SECS}s)"
    echo "$(date '+%Y-%m-%d %H:%M:%S') STALE: $msg | $last_line" >> "$LOG_FILE"
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "⚠️ [STALE] tradebot 엔진 정체" "$msg
last_line: $last_line"
fi
exit 0
