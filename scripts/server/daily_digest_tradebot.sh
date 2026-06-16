#!/bin/bash
# 매일 09:00 KST: 전일 거래/평가 요약 → Telegram
DB=/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db
NOTIFIER=/root/notify_telegram.sh
[ ! -x "$NOTIFIER" ] && exit 0
[ ! -f "$DB" ] && exit 0

q() { sqlite3 -cmd "PRAGMA busy_timeout=5000;" "$DB" "$1" 2>/dev/null; }

BUY=$(q "SELECT COUNT(*) FROM audit_buy_eval WHERE timestamp >= datetime('now', '-1 day');")
SELL=$(q "SELECT COUNT(*) FROM audit_sell_eval WHERE timestamp >= datetime('now', '-1 day');")
LOGS=$(q "SELECT COUNT(*) FROM logs WHERE timestamp >= datetime('now', '-1 day');")
ORDERS=$(q "SELECT COUNT(*), COALESCE(SUM(CASE WHEN side='BUY' AND state='FILLED' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN side='SELL' AND state='FILLED' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END),0) FROM orders WHERE requested_at >= datetime('now', '-1 day');")
KRW=$(q "SELECT printf('%,.0f', balance) FROM accounts WHERE user_id='mcmax33' LIMIT 1;")
"$NOTIFIER" "📊 [일일 요약] tradebot" "기간: 최근 24시간
BUY 평가: $BUY
SELL 평가: $SELL
로그: $LOGS
주문(total/buy-filled/sell-filled/failed): $ORDERS
KRW 잔고: $KRW"
