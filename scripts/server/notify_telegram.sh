#!/bin/bash
# Telegram 알림 헬퍼 (shell 스크립트용)
# 사용: notify_telegram.sh "<TITLE>" "<BODY>"
# .env 또는 환경변수에서 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 읽음.
# 실패해도 exit 0 — 호출 스크립트의 본업을 절대 차단하지 않음.
#
# 1122-01 (2026-11-23 사용자 지시): 운영자 발송 뒤 투자자 채팅(.env TELEGRAM_CHAT_ID_INVESTOR)에 사본 1건.
#   - 사본 글은 운영자가 받는 글 그대로(같은 TEXT · 가공·수정 없음 — 2026-11-24 사용자 지시).
#   - 끄는 법: services/data/.investor_copy_off 파일 · .env TELEGRAM_INVESTOR_COPY=0 · INVESTOR 줄 삭제.
#   - 토큰이 든 주소와 채팅 번호는 curl -K - (표준입력 설정)로 넘겨 ps 에 보이지 않게 한다.
# 시험용 환경변수(서버에서는 쓰지 않음): NOTIFY_ENV_FILE · NOTIFY_COPY_OFF_FILE

export LC_ALL=C.UTF-8   # cron 은 로캘이 C 라 한글 글이 깨지지 않게 UTF-8 로 둔다(운영자·사본 글은 같은 TEXT)

ENV_FILE="${NOTIFY_ENV_FILE:-/root/upbit-tradebot-mvp/.env}"
COPY_OFF_FILE="${NOTIFY_COPY_OFF_FILE:-/root/upbit-tradebot-mvp/services/data/.investor_copy_off}"
TITLE="${1:-알림}"
BODY="${2:-}"

env_value() {
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'" | tr -d " "
}

if [ -f "$ENV_FILE" ]; then
    TOKEN_F=$(env_value TELEGRAM_BOT_TOKEN)
    CHAT_F=$(env_value TELEGRAM_CHAT_ID)
    INV_F=$(env_value TELEGRAM_CHAT_ID_INVESTOR)
    COPY_F=$(env_value TELEGRAM_INVESTOR_COPY)
fi
TOKEN="${TOKEN_F:-$TELEGRAM_BOT_TOKEN}"
CHAT_ID="${CHAT_F:-$TELEGRAM_CHAT_ID}"
INV_CHAT="${INV_F:-$TELEGRAM_CHAT_ID_INVESTOR}"
COPY_SW="${COPY_F:-$TELEGRAM_INVESTOR_COPY}"

if [ -z "$TOKEN" ]; then
    exit 0
fi

escape() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' <<< "$1"; }

make_text() {
    local t_e b_e
    t_e=$(escape "$1")
    b_e=$(escape "$2")
    if [ -n "$2" ]; then
        printf '%s' "<b>${t_e}</b>
<pre>${b_e}</pre>"
    else
        printf '%s' "<b>${t_e}</b>"
    fi
}

# send_one <chat> <text> — 주소(토큰)와 chat_id 는 표준입력 설정으로만 넘긴다
send_one() {
    printf 'url = "https://api.telegram.org/bot%s/sendMessage"\ndata-urlencode = "chat_id=%s"\n' "$TOKEN" "$1" \
        | curl -s --max-time 5 -X POST -K - \
            --data-urlencode "text=$2" \
            --data-urlencode "parse_mode=HTML" \
            --data-urlencode "disable_web_page_preview=true" > /dev/null 2>&1
}

TEXT=$(make_text "$TITLE" "$BODY")

# 운영자 발송 (글은 지금과 같음)
if [ -n "$CHAT_ID" ]; then
    send_one "$CHAT_ID" "$TEXT"
fi

# ---- 투자자 사본 (운영자와 같은 TEXT) ----
[ -z "$INV_CHAT" ] && exit 0
[ "$COPY_SW" = "0" ] && exit 0
[ -e "$COPY_OFF_FILE" ] && exit 0
[ "$INV_CHAT" = "$CHAT_ID" ] && exit 0

send_one "$INV_CHAT" "$TEXT"
exit 0
