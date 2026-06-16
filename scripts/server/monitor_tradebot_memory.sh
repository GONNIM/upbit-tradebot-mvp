#!/bin/bash
# Tradebot 메모리 모니터링 및 자동 재시작 스크립트
# v2 (2026-06-16): 알림 메시지 친화화 — 백분율, 천단위, 액션 가이드

# 설정
MAX_MEMORY_MB=1400  # 1.4GB (1900MB 중 70% 임계값)
LOG_FILE="/var/log/tradebot_memory_monitor.log"
NOTIFIER=/root/notify_telegram.sh

# 천단위 쉼표 (awk로 BSD/GNU 호환)
fmt_num() {
    awk -v n="$1" 'BEGIN {
        len = length(n)
        for (i = len; i > 3; i -= 3)
            n = substr(n, 1, i-3) "," substr(n, i-2)
        print n
    }'
}

# 현재 메모리 사용량 확인 (MB 단위)
CURRENT_MEMORY=$(ps -p $(systemctl show -p MainPID tradebot | cut -d= -f2) -o rss= 2>/dev/null | awk '{print int($1/1024)}')

# PID가 없으면 종료 (서비스가 실행 중이 아님)
if [ -z "$CURRENT_MEMORY" ] || [ "$CURRENT_MEMORY" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Tradebot 서비스가 실행 중이 아닙니다." >> $LOG_FILE
    exit 0
fi

# 메모리 임계값 초과 시 재시작
if [ $CURRENT_MEMORY -gt $MAX_MEMORY_MB ]; then
    CUR_FMT=$(fmt_num "$CURRENT_MEMORY")
    MAX_FMT=$(fmt_num "$MAX_MEMORY_MB")
    PCT=$(awk "BEGIN { printf \"%.0f\", $CURRENT_MEMORY / $MAX_MEMORY_MB * 100 }")
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️ 메모리 임계값 초과! 현재: ${CURRENT_MEMORY}MB / 임계값: ${MAX_MEMORY_MB}MB (${PCT}%)" >> $LOG_FILE
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "⚠️ 메모리 임계 초과 — tradebot" "현재: ${CUR_FMT} MB (${PCT}%)
임계: ${MAX_FMT} MB

→ 자동 재시작 시도 중..."
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 🔄 Tradebot 서비스 재시작 중..." >> $LOG_FILE
    systemctl restart tradebot
    sleep 5
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Tradebot 서비스 재시작 완료" >> $LOG_FILE
    [ -x "$NOTIFIER" ] && "$NOTIFIER" "🔄 tradebot 자동 재시작 완료" "사유: 메모리 임계 초과 (${CUR_FMT} MB)

→ Dashboard에서 엔진 재개 확인 권고"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ 메모리 정상: ${CURRENT_MEMORY}MB / ${MAX_MEMORY_MB}MB" >> $LOG_FILE
fi
