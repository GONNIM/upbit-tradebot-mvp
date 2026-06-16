#!/bin/bash
# Tradebot 메모리 모니터링 및 자동 재시작 스크립트

# 설정
MAX_MEMORY_MB=1400  # 1.4GB (1900MB 중 70% 임계값)
LOG_FILE="/var/log/tradebot_memory_monitor.log"

# 현재 메모리 사용량 확인 (MB 단위)
CURRENT_MEMORY=$(ps -p $(systemctl show -p MainPID tradebot | cut -d= -f2) -o rss= 2>/dev/null | awk '{print int($1/1024)}')

# PID가 없으면 종료 (서비스가 실행 중이 아님)
if [ -z "$CURRENT_MEMORY" ] || [ "$CURRENT_MEMORY" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Tradebot 서비스가 실행 중이 아닙니다." >> $LOG_FILE
    exit 0
fi

# 메모리 임계값 초과 시 재시작
if [ $CURRENT_MEMORY -gt $MAX_MEMORY_MB ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️ 메모리 임계값 초과! 현재: ${CURRENT_MEMORY}MB / 임계값: ${MAX_MEMORY_MB}MB" >> $LOG_FILE
    NOTIFIER=/root/notify_telegram.sh; [ -x "$NOTIFIER" ] && "$NOTIFIER" "⚠️ [MEMORY] 임계값 초과" "현재: ${CURRENT_MEMORY}MB / 임계: ${MAX_MEMORY_MB}MB → 재시작 시도"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 🔄 Tradebot 서비스 재시작 중..." >> $LOG_FILE
    systemctl restart tradebot
    sleep 5
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Tradebot 서비스 재시작 완료" >> $LOG_FILE
    NOTIFIER=/root/notify_telegram.sh; [ -x "$NOTIFIER" ] && "$NOTIFIER" "🔄 [SYSTEM] tradebot 재시작" "사유: 메모리 임계 초과 (현재 ${CURRENT_MEMORY}MB)"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ 메모리 정상: ${CURRENT_MEMORY}MB / ${MAX_MEMORY_MB}MB" >> $LOG_FILE
fi
