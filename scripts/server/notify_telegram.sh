#!/bin/bash
# Telegram 알림 헬퍼 (shell 스크립트용)
# 사용: notify_telegram.sh "<TITLE>" "<BODY>"
# .env 또는 환경변수에서 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 읽음.
# 실패해도 exit 0 — 호출 스크립트의 본업을 절대 차단하지 않음.

ENV_FILE="/root/upbit-tradebot-mvp/.env"
TITLE="${1:-알림}"
BODY="${2:-}"

if [ -f "$ENV_FILE" ]; then
    TOKEN_F=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'" | tr -d " ")
    CHAT_F=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'" | tr -d " ")
fi
TOKEN="${TOKEN_F:-$TELEGRAM_BOT_TOKEN}"
CHAT_ID="${CHAT_F:-$TELEGRAM_CHAT_ID}"

if [ -z "$TOKEN" ] || [ -z "$CHAT_ID" ]; then
    exit 0
fi

escape() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' <<< "$1"; }
TITLE_E=$(escape "$TITLE")
BODY_E=$(escape "$BODY")
if [ -n "$BODY" ]; then
    TEXT="<b>${TITLE_E}</b>
<pre>${BODY_E}</pre>"
else
    TEXT="<b>${TITLE_E}</b>"
fi

curl -s --max-time 5 -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${TEXT}" \
    --data-urlencode "parse_mode=HTML" \
    --data-urlencode "disable_web_page_preview=true" > /dev/null 2>&1
exit 0
