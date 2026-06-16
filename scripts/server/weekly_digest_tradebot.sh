#!/bin/bash
# 매주 월요일 09:00 KST: 지난 7일 요약 → Telegram
# v2 (2026-06-16): 옵션 B 개편
#   - balance 컬럼 버그 → virtual_krw + virtual_krw_locked 교체
#   - timezone 보정: datetime('now', 'localtime', ...) 으로 일관
#   - 보유 종목 (account_positions.virtual_coin > 0)
#   - 매도 사유 분포 + 평균 수익률 (audit_trades)
#   - 평가 → 체결 전환율
#   - state=NULL 이상 주문 경고

DB=/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db
NOTIFIER=/root/notify_telegram.sh
USER_ID=mcmax33
[ ! -x "$NOTIFIER" ] && exit 0
[ ! -f "$DB" ] && exit 0

# sqlite3 -cmd "PRAGMA busy_timeout=N;" 는 N 자체를 stdout으로 prefix → 값 오염.
# .timeout 도트 명령을 stdin으로 전달해 PRAGMA 출력 회피.
q() { printf '.timeout 5000\n%s\n' "$1" | sqlite3 "$DB" 2>/dev/null; }

WINDOW="datetime('now', 'localtime', '-7 days')"

# 자산
KRW_ACTIVE=$(q "SELECT printf('%,d', COALESCE(virtual_krw, 0)) FROM accounts WHERE user_id='$USER_ID' LIMIT 1;")
KRW_LOCKED=$(q "SELECT printf('%,d', COALESCE(virtual_krw_locked, 0)) FROM accounts WHERE user_id='$USER_ID' LIMIT 1;")
[ -z "$KRW_ACTIVE" ] && KRW_ACTIVE="0"
[ -z "$KRW_LOCKED" ] && KRW_LOCKED="0"

# 보유 종목
HELD_COUNT=$(q "SELECT COUNT(*) FROM account_positions WHERE user_id='$USER_ID' AND virtual_coin > 0;")
HELD=$(q "SELECT GROUP_CONCAT(ticker || '(' || printf('%,.2f', virtual_coin) || ')', ', ') FROM account_positions WHERE user_id='$USER_ID' AND virtual_coin > 0;")
[ -z "$HELD" ] && HELD="(없음)"
HELD_COUNT="${HELD_COUNT:-0}"

# 체결 통계
ORDER_STATS=$(q "SELECT
  COALESCE(SUM(CASE WHEN side='BUY' AND state='FILLED' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN side='SELL' AND state='FILLED' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN state='CANCELED' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN state IS NULL OR state='' THEN 1 ELSE 0 END),0)
FROM orders WHERE requested_at >= $WINDOW;")
IFS='|' read -r BUY_F SELL_F FAIL_C CAN_C NULL_S <<< "$ORDER_STATS"
BUY_F="${BUY_F:-0}"; SELL_F="${SELL_F:-0}"; FAIL_C="${FAIL_C:-0}"; CAN_C="${CAN_C:-0}"; NULL_S="${NULL_S:-0}"

# 매도 사유 분포
SELL_REASONS=$(q "SELECT
  COALESCE(SUM(CASE WHEN reason='TAKE_PROFIT' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN reason='STOP_LOSS' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN reason='DEAD_CROSS' THEN 1 ELSE 0 END),0) || '|' ||
  COALESCE(SUM(CASE WHEN reason NOT IN ('TAKE_PROFIT','STOP_LOSS','DEAD_CROSS') AND reason IS NOT NULL THEN 1 ELSE 0 END),0)
FROM audit_trades WHERE type='SELL' AND timestamp >= $WINDOW;")
IFS='|' read -r TP_C SL_C DC_C OTHER_C <<< "$SELL_REASONS"
TP_C="${TP_C:-0}"; SL_C="${SL_C:-0}"; DC_C="${DC_C:-0}"; OTHER_C="${OTHER_C:-0}"

# 평균 수익률 + 최고/최저
PNL_STATS=$(q "SELECT
  printf('%+.2f%%', AVG(CASE WHEN entry_price > 0 THEN (price - entry_price) / entry_price * 100.0 ELSE NULL END)) || '|' ||
  printf('%+.2f%%', MAX(CASE WHEN entry_price > 0 THEN (price - entry_price) / entry_price * 100.0 ELSE NULL END)) || '|' ||
  printf('%+.2f%%', MIN(CASE WHEN entry_price > 0 THEN (price - entry_price) / entry_price * 100.0 ELSE NULL END))
FROM audit_trades WHERE type='SELL' AND timestamp >= $WINDOW;")
IFS='|' read -r AVG_PNL MAX_PNL MIN_PNL <<< "$PNL_STATS"
[ -z "$AVG_PNL" ] || [ "$AVG_PNL" = "+nan%" ] && AVG_PNL="(데이터 없음)"
[ -z "$MAX_PNL" ] || [ "$MAX_PNL" = "+nan%" ] && MAX_PNL="-"
[ -z "$MIN_PNL" ] || [ "$MIN_PNL" = "+nan%" ] && MIN_PNL="-"

# 평가 카운트
BUY_EVAL=$(q "SELECT COUNT(*) FROM audit_buy_eval WHERE timestamp >= $WINDOW;")
SELL_EVAL=$(q "SELECT COUNT(*) FROM audit_sell_eval WHERE timestamp >= $WINDOW;")
BUY_EVAL="${BUY_EVAL:-0}"; SELL_EVAL="${SELL_EVAL:-0}"

# 체결률
BUY_RATE="0.00%"
[ "$BUY_EVAL" -gt 0 ] && BUY_RATE=$(awk "BEGIN { printf \"%.2f%%\", $BUY_F / $BUY_EVAL * 100 }")
SELL_RATE="0.00%"
[ "$SELL_EVAL" -gt 0 ] && SELL_RATE=$(awk "BEGIN { printf \"%.2f%%\", $SELL_F / $SELL_EVAL * 100 }")

# 이상 라인
ANOMALY=""
[ "$NULL_S" -gt 0 ] && ANOMALY="

⚠️ 이상: state=NULL 주문 ${NULL_S}건 (정리 필요)"

BODY="기간: 최근 7일 KST

💰 자산
  활성 KRW: ${KRW_ACTIVE}
  잠금 KRW: ${KRW_LOCKED}
  보유 종목 (${HELD_COUNT}종): ${HELD}

📈 매매 체결
  BUY=${BUY_F}  SELL=${SELL_F}  실패=${FAIL_C}  취소=${CAN_C}
  매도 사유: TP=${TP_C} SL=${SL_C} DC=${DC_C} 기타=${OTHER_C}
  수익률  평균=${AVG_PNL}  최고=${MAX_PNL}  최저=${MIN_PNL}

🔍 평가 → 체결률
  BUY:  ${BUY_EVAL}건 → ${BUY_F}건 (${BUY_RATE})
  SELL: ${SELL_EVAL}건 → ${SELL_F}건 (${SELL_RATE})${ANOMALY}"

"$NOTIFIER" "📈 [주간 요약] tradebot" "$BODY"
