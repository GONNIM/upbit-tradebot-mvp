#!/bin/bash
# position_history 오래된 줄 지우기 (2026-11-08 신설)
# - 이 표는 엔진이 보유 수량을 바꿀 때마다 쓰기만 하고, 코드 어디에서도 읽지 않는다
#   (services/db.py insert_position_history · core/trader.py 만 씀). 하루 약 17만 줄씩 늘어 DB 의 약 80% 를 차지했다.
# - 기본 30일만 남긴다(audit_buy_eval · audit_sell_eval · logs 와 같은 기준).
# - 엔진 쓰기를 오래 막지 않도록 작은 묶음(기본 5,000줄)으로 나눠 지우고, 묶음 사이에 잠깐 쉰다.
# - 파일 크기는 줄지 않는다(VACUUM 없음). 빈 칸은 다음 쓰기에 다시 쓰이므로 DB 가 더 커지지 않는다.
# 사용: prune_position_history.sh [남길 날수=30] [묶음 크기=5000] [--dry-run]
# 출력 마지막 줄: DELETED=<지운 줄 수>
set -u
DB_PATH="${DB_PATH:-/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db}"
KEEP_DAYS="${1:-30}"
BATCH="${2:-5000}"
DRY=0
[ "${3:-}" = "--dry-run" ] && DRY=1
BUSY_TIMEOUT_MS=5000
MAX_BATCHES=4000   # 안전 상한

q() { sqlite3 -cmd ".timeout $BUSY_TIMEOUT_MS" "$DB_PATH" "$1"; }

# 날짜만 비교한다. timestamp 는 '2026-11-08T11:43:25.9+09:00' 모양(KST)이라 앞 10글자 비교가 정확하다.
CUTOFF=$(date -d "-${KEEP_DAYS} days" +%F)
# 기준 날짜 이후의 첫 id. id 는 시간 순으로만 늘어난다(AUTOINCREMENT).
FIRST_KEEP=$(q "SELECT id FROM position_history WHERE substr(timestamp,1,10) >= '$CUTOFF' ORDER BY id LIMIT 1;")
if [ -z "$FIRST_KEEP" ]; then
    echo "기준 날짜($CUTOFF) 이후 줄이 없음 — 아무것도 지우지 않음"
    echo "DELETED=0"
    exit 0
fi
TO_DELETE=$(q "SELECT COUNT(*) FROM position_history WHERE id < $FIRST_KEEP;")
echo "기준 날짜=$CUTOFF 남길 첫 id=$FIRST_KEEP 지울 줄=$TO_DELETE 묶음=$BATCH"
if [ "$DRY" -eq 1 ]; then
    echo "DELETED=0 (dry-run)"
    exit 0
fi

TOTAL=0
N=0
MAXMS=0
while [ "$N" -lt "$MAX_BATCHES" ]; do
    T1=$(date +%s%N)
    C=$(q "DELETE FROM position_history WHERE id IN (SELECT id FROM position_history WHERE id < $FIRST_KEEP ORDER BY id LIMIT $BATCH); SELECT changes();" 2>&1 | tail -1)
    MS=$(( ($(date +%s%N) - T1) / 1000000 ))
    [ "$MS" -gt "$MAXMS" ] && MAXMS=$MS
    case "$C" in
        ''|*[!0-9]*) echo "멈춤: 지우기 실패 — $C"; break ;;
    esac
    [ "$C" -eq 0 ] && break
    TOTAL=$((TOTAL + C))
    N=$((N + 1))
    # 엔진은 잠금을 3초까지 기다린다(services/db.py busy_timeout=3000). 한 묶음이 1초를 넘으면 멈춘다.
    if [ "$MS" -gt 1000 ]; then echo "멈춤: 한 묶음이 ${MS}ms 걸림(기준 1000ms)"; break; fi
    sleep 0.3
done
echo "묶음=$N 가장 오래 걸린 묶음=${MAXMS}ms"
echo "DELETED=$TOTAL"
