#!/bin/bash
# Tradebot 엔진 정체 감지 (보조 안전망) + Telegram 알림 + dedupe
# 변경 이력:
#   2026-06-16: flag 파일 dedupe (TTL 3600s) + RECOVERED 복구 알림 추가
THRESHOLD_SECS=600
LOG_FILE="/var/log/tradebot_engine_stale.log"
NOTIFIER=/root/notify_telegram.sh
LOCK_FILE=/var/run/tradebot_stale.lock
DEDUPE_TTL=3600  # 60분: 동일 stale 사유 재알림 최소 간격

# dedupe 가드 — flag 없음 또는 TTL 초과 시에만 true(0) 반환
should_send_stale() {
    [ ! -f "$LOCK_FILE" ] && return 0
    local flag_epoch
    flag_epoch=$(stat -c %Y "$LOCK_FILE" 2>/dev/null)
    [ -z "$flag_epoch" ] && return 0
    local age=$(( $(date +%s) - flag_epoch ))
    [ $age -ge $DEDUPE_TTL ] && return 0
    return 1
}

notify_stale() {
    local title="$1" body="$2"
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "$title" "$body"
    touch "$LOCK_FILE"
}

notify_recovered_if_needed() {
    [ ! -f "$LOCK_FILE" ] && return 0
    local body="$1"
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "✅ [RECOVERED] tradebot 엔진" "$body"
    rm -f "$LOCK_FILE"
    echo "$(date '+%Y-%m-%d %H:%M:%S') RECOVERED: $body" >> "$LOG_FILE"
}

last_line=$(journalctl -u tradebot --since "30 min ago" --no-pager --output=short-iso 2>/dev/null | grep -E "Bar#" | tail -1)

if [ -z "$last_line" ]; then
    msg="최근 30분간 Bar# 평가 로그 없음 (엔진 정체 가능성)"
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: $msg" >> "$LOG_FILE"
    if should_send_stale; then
        notify_stale "⚠️ [STALE] tradebot 엔진" "$msg"
    fi
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
    if should_send_stale; then
        notify_stale "⚠️ [STALE] tradebot 엔진 정체" "$msg
last_line: $last_line"
    fi
    exit 0
fi

# 정상 상태 — flag 있으면 RECOVERED 1회 알림 후 flag 제거
notify_recovered_if_needed "Bar# 평가 정상화 (gap=${gap}s)
last_line: $last_line"
exit 0
