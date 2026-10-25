#!/usr/bin/env bash
# tradebot-v2 유닛 보호 속성 점검 (A14·A17) — 서버에서 배포 승인 뒤에 실행한다.
#
# 하는 일:
#   1) 실행 중인 tradebot-v2 의 보호 속성 값을 systemctl 로 읽어 그대로 systemd-run 임시 유닛에 넘기고,
#      그 안에서 scripts/v2/check_v2_unit_probe.py 를 돌려 10항목을 검사한다.
#   2) 호스트에서 tradebot-v2 프로세스의 환경 변수 이름 중 UPBIT_ 로 시작하는 것이 0개인지 센다(이름만, 값 출력 없음).
#   3) 호스트에서 실행 중 v2 가 보는 PULLBACK 파일 inode 와 디스크 파일 inode 가 같은지 비교한다(읽기 전용 stat).
# 출력은 `PASS|FAIL|RESIDUAL <항목>` 줄뿐이다. 서비스는 재시작·중지하지 않는다.
# 사용: check_v2_unit.sh [user] (기본 mcmax33)
# 종료 코드: 0 = FAIL 없음, 1 = FAIL 있음, 2 = user 인자 형식 오류(bad-user-argument) 또는 tradebot-v2 가 켜져 있지 않음.
#
# 주의:
#  - `set -e` 는 쓰지 않는다. `grep -c` 가 0건일 때 종료 1 을 내는데 그것이 정상이기 때문이다(그 줄은 `|| true`).
#  - 속성은 `systemctl show -p <하나> --value` 로 하나씩 읽는다. 여러 -p 를 한 번에 쓰면 출력 순서가
#    -p 순서와 달라지고 빈 값이 섞이면 값이 어긋난다.
#  - CapabilityBoundingSet 이 빈 값이면 `-p CapabilityBoundingSet=` (빈 값) 으로 넘긴다. 유닛이 `CapabilityBoundingSet=`
#    로 모든 권한을 뺐으면 systemctl show 는 빈 문자열을 낸다. 빈 값이 아니라 권한 목록이 나오면
#    유닛이 의도대로 적용되지 않은 것이므로 unit-props 항목이 FAIL 이 된다.
#  - `systemctl show -p ReadWritePaths --value` 가 `-` 접두(없으면 무시)를 유지하는지는 로컬에서 확인할 수 없다.
#    배포 때 첫 실행에서 probe-run-failed 가 나오면 접두 처리부터 볼 것(docs/operations/v2-runbook.md).

set -u
set -o pipefail

REPO=/root/upbit-tradebot-mvp
PY="$REPO/venv/bin/python"
PROBE="$REPO/scripts/v2/check_v2_unit_probe.py"
EXPECTED_PROBE_LINES=10
FAILS=0

# 첫 인자: 점검할 계정(기본 mcmax33). 형식이 어긋나면 FAIL 후 종료 2.
USER_ID="${1:-mcmax33}"
if ! [[ "$USER_ID" =~ ^[A-Za-z0-9_]{1,32}$ ]]; then
    echo "FAIL bad-user-argument"
    exit 2
fi
PULLBACK_REL="${USER_ID}_latest_params_PULLBACK.json"

if ! systemctl is-active --quiet tradebot-v2; then
    echo "FAIL tradebot-v2-not-active"
    exit 2
fi

PROP_PROTECT_SYSTEM=$(systemctl show -p ProtectSystem --value tradebot-v2)
PROP_PROTECT_HOME=$(systemctl show -p ProtectHome --value tradebot-v2)
PROP_RW_PATHS=$(systemctl show -p ReadWritePaths --value tradebot-v2)
PROP_INACCESSIBLE=$(systemctl show -p InaccessiblePaths --value tradebot-v2)
PROP_NO_NEW_PRIVS=$(systemctl show -p NoNewPrivileges --value tradebot-v2)
PROP_UMASK=$(systemctl show -p UMask --value tradebot-v2)
PROP_CAP_BOUNDING=$(systemctl show -p CapabilityBoundingSet --value tradebot-v2)
PROP_PRIVATE_TMP=$(systemctl show -p PrivateTmp --value tradebot-v2)

# 유닛이 의도한 값으로 적용됐는지(값 자체는 출력하지 않는다)
if [ "$PROP_PROTECT_SYSTEM" = "strict" ] && [ "$PROP_PROTECT_HOME" = "read-only" ] && [ "$PROP_NO_NEW_PRIVS" = "yes" ] \
    && [ "$PROP_UMASK" = "0077" ] && [ -z "$PROP_CAP_BOUNDING" ] && [ "$PROP_PRIVATE_TMP" = "yes" ]; then
    echo "PASS unit-props"
else
    echo "FAIL unit-props"
    FAILS=1
fi

TRADEBOT_PID=$(systemctl show -p MainPID --value tradebot)

OUT=$(systemd-run --wait --pipe --collect --quiet \
    -p "WorkingDirectory=$REPO" \
    -p "ProtectSystem=$PROP_PROTECT_SYSTEM" \
    -p "ProtectHome=$PROP_PROTECT_HOME" \
    -p "ReadWritePaths=$PROP_RW_PATHS" \
    -p "InaccessiblePaths=$PROP_INACCESSIBLE" \
    -p "NoNewPrivileges=$PROP_NO_NEW_PRIVS" \
    -p "UMask=$PROP_UMASK" \
    -p "CapabilityBoundingSet=$PROP_CAP_BOUNDING" \
    -p "PrivateTmp=$PROP_PRIVATE_TMP" \
    "$PY" -B "$PROBE" "$TRADEBOT_PID" "$USER_ID" 2>/dev/null)
RUN_RC=$?

# 탐침 출력에서 상태 줄 형식만 통과시킨다(그 밖의 출력은 버림)
FILTERED=$(printf '%s\n' "$OUT" | grep -E '^(PASS|FAIL|RESIDUAL) [A-Za-z0-9_().=-]+$' || true)
PROBE_LINES=$(printf '%s\n' "$FILTERED" | grep -c -E '^(PASS|FAIL|RESIDUAL) ' || true)

if [ -n "$FILTERED" ]; then
    printf '%s\n' "$FILTERED"
fi
if printf '%s\n' "$FILTERED" | grep -q '^FAIL '; then
    FAILS=1
fi
if [ "$RUN_RC" -ne 0 ]; then
    echo "FAIL probe-run-failed"
    FAILS=1
fi
if [ "$PROBE_LINES" != "$EXPECTED_PROBE_LINES" ]; then
    echo "FAIL probe-line-count=$PROBE_LINES"
    FAILS=1
fi

# 7번(호스트): tradebot-v2 프로세스의 환경 변수 이름 중 UPBIT_ 접두 개수 (값은 읽어도 출력하지 않음)
V2_PID=$(systemctl show -p MainPID --value tradebot-v2)
if [ -z "$V2_PID" ] || [ "$V2_PID" = "0" ] || [ ! -r "/proc/$V2_PID/environ" ]; then
    echo "FAIL upbit-env-unreadable"
    FAILS=1
else
    UPBIT_COUNT=$(tr '\0' '\n' < "/proc/$V2_PID/environ" | cut -d= -f1 | grep -c '^UPBIT_' || true)
    if [ "$UPBIT_COUNT" = "0" ]; then
        echo "PASS no-upbit-env"
    else
        echo "FAIL upbit-env-count=$UPBIT_COUNT"
        FAILS=1
    fi
fi

# 호스트(읽기 전용): 실행 중인 v2 가 보는 PULLBACK 파일과 호스트의 파일이 같은 inode 인가.
# 파일을 지우고 새로 만들었으면 v2 는 옛 inode 에 bind mount 된 채라 저장이 닿지 않는다(→ restart tradebot-v2).
INODE_V2=$(stat -Lc %i "/proc/$V2_PID/root$REPO/$PULLBACK_REL" 2>/dev/null || true)
INODE_HOST=$(stat -Lc %i "$REPO/$PULLBACK_REL" 2>/dev/null || true)
if [ -n "$INODE_V2" ] && [ "$INODE_V2" = "$INODE_HOST" ]; then
    echo "PASS pullback-inode-match"
else
    echo "FAIL pullback-inode-mismatch"
    FAILS=1
fi

if [ "$FAILS" -ne 0 ]; then
    exit 1
fi
exit 0
