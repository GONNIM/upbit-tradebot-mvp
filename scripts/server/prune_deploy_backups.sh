#!/bin/bash
# 배포 때 만든 DB 백업 정리 (2026-11-08 신설)
# - 배포 스크립트는 /root/backup/ 이나 /root/backup-<이름>/ 에 사용자 DB 백업(1.1GB 안팎)을 만들고 지우지 않았다.
#   11/01~11/06 6일에 6개(6.2GB)가 쌓였다.
# - 사용자 DB 마다(파일 이름의 날짜·시각 앞부분이 같으면 같은 DB) 가장 새 백업 KEEP 개만 남기고 지운다.
#   -shm · -wal 짝 파일도 함께 지운다. 비게 된 /root/backup-<이름>/ 폴더는 지운다.
# - 주간 정리 백업(services/data/backups/)은 건드리지 않는다(그쪽은 7일 규칙이 따로 있다).
# 사용: prune_deploy_backups.sh [남길 개수=2] [--dry-run]
# 출력 마지막 줄: FREED_BYTES=<지운 바이트>
set -u
KEEP="${1:-2}"
DRY=0
[ "${2:-}" = "--dry-run" ] && DRY=1
ROOTS="/root/backup /root/backup-*"

LIST=$(for d in $ROOTS; do [ -d "$d" ] && find "$d" -maxdepth 1 -type f -name 'tradebot_*.db' -printf '%T@ %p\n'; done 2>/dev/null | sort -rn)
[ -z "$LIST" ] && { echo "배포 백업 없음"; echo "FREED_BYTES=0"; exit 0; }

FREED=0
declare -A SEEN
while read -r _ts f; do
    b=$(basename "$f" .db)
    # 사용자 DB 이름 = 날짜·시각 꼬리를 뗀 앞부분 (tradebot_mcmax33_20261101 · tradebot_mcmax33-213558 → tradebot_mcmax33)
    key=$(echo "$b" | sed -E 's/[_-][0-9]{6,8}(_[0-9]{4})?$//')
    SEEN[$key]=$(( ${SEEN[$key]:-0} + 1 ))
    if [ "${SEEN[$key]}" -le "$KEEP" ]; then
        echo "남김: $f ($key ${SEEN[$key]}번째로 새 것)"
        continue
    fi
    for x in "$f" "$f-shm" "$f-wal"; do
        [ -f "$x" ] || continue
        sz=$(stat -c %s "$x")
        FREED=$((FREED + sz))
        if [ "$DRY" -eq 1 ]; then
            echo "지울 것: $x ($sz 바이트)"
        else
            rm -f -- "$x" && echo "지움: $x ($sz 바이트)"
        fi
    done
done < <(printf '%s\n' "$LIST")

if [ "$DRY" -eq 0 ]; then
    for d in /root/backup-*; do
        [ -d "$d" ] && [ -z "$(ls -A "$d")" ] && rmdir "$d" && echo "빈 폴더 지움: $d"
    done
fi
echo "FREED_BYTES=$FREED"
