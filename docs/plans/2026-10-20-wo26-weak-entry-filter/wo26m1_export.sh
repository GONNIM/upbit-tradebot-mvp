#!/bin/bash
# WO-26 1단계 읽기 전용 추출: (1) journal Bar# 로그 (2) audit_trades KRW-JTO (3) audit_buy_eval 요약
# 서버에서 아무것도 쓰지 않는다. DB 는 mode=ro.
DB='file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro'
echo "##BAR"
journalctl -u tradebot --since "2026-09-30 20:00" --no-pager -o short-iso -g 'Bar#[0-9]+ \| ts=' 2>/dev/null \
  | grep -v '^-- No' | sed -E 's/^.*\]: //' | cut -c1-260
echo "##TRADES"
sqlite3 -separator '|' "$DB" \
  "SELECT id, timestamp, bar_time, type, reason, price, entry_price, bars_held FROM audit_trades WHERE ticker='KRW-JTO' AND timestamp >= '2026-09-19' ORDER BY id;"
echo "##BUYEVAL"
sqlite3 -separator '|' "$DB" \
  "SELECT id, timestamp, bar_time, have_position, overall_ok, failed_keys, price FROM audit_buy_eval WHERE ticker='KRW-JTO' AND timestamp >= '2026-09-19' ORDER BY id;"
