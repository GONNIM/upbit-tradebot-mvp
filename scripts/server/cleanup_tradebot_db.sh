#!/bin/bash
# Tradebot DB 정리 스크립트 — 무중단 버전 v2 (2026-05-31)
# 변경점:
#   - systemctl stop/start 제거 (live_loop 그대로 가동)
#   - VACUUM 제거 → PRAGMA wal_checkpoint(TRUNCATE)로 대체 (exclusive lock 없음)
#   - WAL 모드 기반 동시 read/write 보장
# 사유: 매주 일요일 04:00 cron 후 약 4시간+ BUY 평가 공백 발생 → 1년 365일 무중단 요구

DB_PATH="/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db"
BACKUP_DIR="/root/upbit-tradebot-mvp/services/data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/var/log/tradebot_cleanup.log"
BUSY_TIMEOUT_MS=5000

log_message() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG_FILE"; }

log_message "=========================================="
log_message "DB 정리 시작 (무중단 v2)"

mkdir -p "$BACKUP_DIR"

# 1) 백업 — sqlite3 .backup 명령은 WAL 포함 일관성 보장 (cp보다 안전)
log_message "DB 백업 시작 (.backup, WAL 일관성)..."
if sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/tradebot_mcmax33.db.backup_$TIMESTAMP" 2>>"$LOG_FILE"; then
    log_message "DB 백업 완료: tradebot_mcmax33.db.backup_$TIMESTAMP"
else
    log_message "ERROR: DB 백업 실패 (계속 진행)"
fi

# 2) 7일 이전 백업 삭제
find "$BACKUP_DIR" -name "tradebot_mcmax33.db.backup_*" -mtime +7 -delete 2>>"$LOG_FILE"
log_message "7일 이상 된 백업 삭제 완료"

# 3) 30일 이전 로그 DELETE — WAL 모드라 reader 차단 없음, busy 시 5초 대기
run_sql() {
    sqlite3 -cmd "PRAGMA busy_timeout=$BUSY_TIMEOUT_MS;" "$DB_PATH" "$1" 2>>"$LOG_FILE"
}

log_message "30일 이전 로그 삭제 시작..."
DELETED_BUY=$(run_sql "DELETE FROM audit_buy_eval WHERE timestamp < datetime('now', '-30 days'); SELECT changes();" | tail -1)
DELETED_SELL=$(run_sql "DELETE FROM audit_sell_eval WHERE timestamp < datetime('now', '-30 days'); SELECT changes();" | tail -1)
DELETED_LOGS=$(run_sql "DELETE FROM logs WHERE timestamp < datetime('now', '-30 days'); SELECT changes();" | tail -1)
log_message "삭제: audit_buy_eval=$DELETED_BUY, audit_sell_eval=$DELETED_SELL, logs=$DELETED_LOGS"

# 4) WAL checkpoint — VACUUM 대신 (exclusive lock 없이 WAL→main 머지 + WAL 압축)
log_message "WAL 체크포인트(TRUNCATE) 실행..."
DB_SIZE_BEFORE=$(du -b "$DB_PATH" | cut -f1)
WAL_SIZE_BEFORE=$([ -f "${DB_PATH}-wal" ] && du -b "${DB_PATH}-wal" | cut -f1 || echo "0")
CKPT_RESULT=$(run_sql "PRAGMA wal_checkpoint(TRUNCATE);" | tail -1)
DB_SIZE_AFTER=$(du -b "$DB_PATH" | cut -f1)
WAL_SIZE_AFTER=$([ -f "${DB_PATH}-wal" ] && du -b "${DB_PATH}-wal" | cut -f1 || echo "0")
log_message "체크포인트 result=$CKPT_RESULT | main: $DB_SIZE_BEFORE → $DB_SIZE_AFTER | wal: $WAL_SIZE_BEFORE → $WAL_SIZE_AFTER"

DB_SIZE_FINAL=$(du -h "$DB_PATH" | cut -f1)
log_message "DB 정리 완료 - 최종 크기: $DB_SIZE_FINAL (서비스 중단 없음)"
log_message "=========================================="

# 정보성 #13: cleanup 결과 알림 (v2 — 친화 표현)
# 천단위 쉼표 (awk fmt_num, BSD/GNU 호환)
fmt_num() {
    awk -v n="$1" 'BEGIN {
        len = length(n)
        for (i = len; i > 3; i -= 3)
            n = substr(n, 1, i-3) "," substr(n, i-2)
        print n
    }'
}

BUY_FMT=$(fmt_num "${DELETED_BUY:-0}")
SELL_FMT=$(fmt_num "${DELETED_SELL:-0}")
LOGS_FMT=$(fmt_num "${DELETED_LOGS:-0}")
CKPT_LABEL="OK"
[ -z "$CKPT_RESULT" ] && CKPT_LABEL="실패"

NOTIFIER=/root/notify_telegram.sh
[ -x "$NOTIFIER" ] && "$NOTIFIER" "🧹 주간 DB 정리 완료" "삭제된 30일 이전 레코드:
  BUY 평가: ${BUY_FMT}건
  SELL 평가: ${SELL_FMT}건
  로그: ${LOGS_FMT}건
체크포인트: ${CKPT_LABEL}
DB 크기: ${DB_SIZE_FINAL}
가동 중단 없음 ✅"

exit 0
