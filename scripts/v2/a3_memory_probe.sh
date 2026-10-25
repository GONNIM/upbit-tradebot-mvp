#!/usr/bin/env bash
# A3 메모리 상한 격리 점검 — 서버에서 배포 승인 뒤에 실행한다.
#
# tradebot-v2 와 같은 보호 속성(여기에 고정값으로 적는다 — 실행 중 유닛에 의존하지 않음)에 MemoryMax=150M·MemorySwapMax=0 을
# 걸어 임시 유닛 하나를 띄우고, 그 안의 파이썬이 300MB 를 잡게 한다. 기대:
#   - 임시 유닛만 OOM 으로 죽는다(문자열 oom-kill 로만 판정 — 종료 코드만으로는 PASS 를 주지 않는다. 메모리 부족 예외 종료도 코드 1).
#   - free -m 의 Swap used 가 늘지 않는다(5MB 이내).
#   - tradebot 의 ExecMainStartTimestamp 가 전후 같다(재시작 없음).
# 출력은 `PASS|FAIL <항목>` 줄뿐이다. tradebot·tradebot-v2 는 건드리지 않는다.
# 종료 코드: 0 = FAIL 없음, 1 = FAIL 있음.
#
# 파이썬은 메모리 부족 예외를 잡지 않고 그대로 둔다(OOM 종료와 구분이 흐려지지 않게).

set -u
set -o pipefail

REPO=/root/upbit-tradebot-mvp
PY="$REPO/venv/bin/python"
UNIT="v2-a3-probe-$$"
FAILS=0
SWAP_LIMIT_MB=5
PROBE_PY='b = bytearray(); [b.extend(b"\xa5" * 1048576) for _ in range(300)]'

swap_used_mb() {
    free -m | awk '/^Swap:/ {print $3}'
}

START_BEFORE=$(systemctl show tradebot -p ExecMainStartTimestamp --value)
SWAP_BEFORE=$(swap_used_mb)

RUN_OUT=$(systemd-run --wait --pipe --collect --unit=v2-a3-probe-$$ \
    -p "WorkingDirectory=$REPO" \
    -p "ProtectSystem=strict" \
    -p "ReadWritePaths=-$REPO/services/data -$REPO/mcmax33_latest_params_PULLBACK.json" \
    -p "InaccessiblePaths=-$REPO/.env -$REPO/.streamlit/secrets.toml -$REPO/credentials.yaml" \
    -p "NoNewPrivileges=yes" \
    -p "UMask=0077" \
    -p "CapabilityBoundingSet=" \
    -p "PrivateTmp=yes" \
    -p MemoryMax=150M \
    -p MemorySwapMax=0 \
    "$PY" -c "$PROBE_PY" 2>&1)

# OOM 판정은 문자열로만: systemd-run 의 결과 줄 또는 임시 유닛의 journal
# (oom-kill = 결과 코드, killed by the OOM killer = systemd 249 journal 문구. 종료 코드만으로는 PASS 를 주지 않는다)
# 파이프 대신 변수로 받아 grep 한다: pipefail 과 grep -q 의 조기 종료(SIGPIPE)로 거짓이 되는 것을 막는다.
OOM_PATTERN='oom-kill|killed by the OOM killer'
JOURNAL_OUT=$(journalctl -u "$UNIT" --no-pager 2>/dev/null || true)
OOM=0
if grep -qE "$OOM_PATTERN" <<< "$RUN_OUT"; then
    OOM=1
elif grep -qE "$OOM_PATTERN" <<< "$JOURNAL_OUT"; then
    OOM=1
fi

if [ "$OOM" = "1" ]; then
    echo "PASS probe-oom-killed"
else
    RESULT=$(grep -o 'Finished with result: [A-Za-z-]*' <<< "$RUN_OUT" | head -n 1 || true)
    RESULT_WORD="${RESULT##*: }"
    if [ -z "$RESULT_WORD" ]; then
        RESULT_WORD="unknown"
    fi
    echo "FAIL probe-not-oom($RESULT_WORD)"
    FAILS=1
fi

SWAP_AFTER=$(swap_used_mb)
if [[ "$SWAP_BEFORE" =~ ^[0-9]+$ ]] && [[ "$SWAP_AFTER" =~ ^[0-9]+$ ]]; then
    SWAP_DIFF=$((SWAP_AFTER - SWAP_BEFORE))
    if [ "$SWAP_DIFF" -le "$SWAP_LIMIT_MB" ]; then
        echo "PASS swap-unchanged(+${SWAP_DIFF}mb)"
    else
        echo "FAIL swap-grew(+${SWAP_DIFF}mb)"
        FAILS=1
    fi
else
    echo "FAIL swap-unreadable"
    FAILS=1
fi

START_AFTER=$(systemctl show tradebot -p ExecMainStartTimestamp --value)
if [ -n "$START_BEFORE" ] && [ "$START_BEFORE" = "$START_AFTER" ]; then
    echo "PASS tradebot-not-restarted"
else
    echo "FAIL tradebot-restarted-or-unknown"
    FAILS=1
fi

if [ "$FAILS" -ne 0 ]; then
    exit 1
fi
exit 0
