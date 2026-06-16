#!/bin/bash
# 매주 월요일 09:00 KST: 지난 7일 요약 → Telegram
DB=/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db
NOTIFIER=/root/notify_telegram.sh
[ ! -x "$NOTIFIER" ] && exit 0
[ ! -f "$DB" ] && exit 0

q() { sqlite3 -cmd "PRAGMA busy_timeout=5000;" "$DB" "$1" 2>/dev/null; }

BUY=$(q "SELECT COUNT(*) FROM audit_buy_eval WHERE timestamp >= datetime('now', '-7 days');")
SELL=$(q "SELECT COUNT(*) FROM audit_sell_eval WHERE timestamp >= datetime('now', '-7 days');")
FILLED_BUY=$(q "SELECT COUNT(*) FROM orders WHERE side='BUY' AND state='FILLED' AND requested_at >= datetime('now', '-7 days');")
FILLED_SELL=$(q "SELECT COUNT(*) FROM orders WHERE side='SELL' AND state='FILLED' AND requested_at >= datetime('now', '-7 days');")
FAILED=$(q "SELECT COUNT(*) FROM orders WHERE state='FAILED' AND requested_at >= datetime('now', '-7 days');")
KRW=$(q "SELECT printf('%,.0f', balance) FROM accounts WHERE user_id='mcmax33' LIMIT 1;")
"$NOTIFIER" "📈 [주간 요약] tradebot" "기간: 최근 7일
BUY 평가: $BUY  SELL 평가: $SELL
체결: BUY=$FILLED_BUY SELL=$FILLED_SELL
실패 주문: $FAILED
KRW 잔고: $KRW"
