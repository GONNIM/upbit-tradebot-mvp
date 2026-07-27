#!/usr/bin/env bash
# ✅ [Phase 2] 회귀 테스트 CI 게이트 — 배포 전 필수 실행
#
# 목적:
# - 60일간 5건 결함(F1/F1'/F2/F3/F5) 재발을 물리 차단
# - 모든 회귀 테스트 통과해야 배포 진행
#
# 사용법:
#   ./scripts/regression_gate.sh && deploy-tradebot
#
# CI/CD:
# - .githooks/pre-push 가 자동으로 이 스크립트 호출
# - 실패 시 git push 차단
#
# 실패 시 대응:
# - 어떤 테스트가 실패했는지 확인
# - 실패 원인 = 결함 재발 or 테스트 자체 오류
# - 절대 회귀 테스트를 우회하지 말 것 (2026-07-27 원칙)

set -e  # 어떤 명령이든 실패하면 즉시 종료

# 프로젝트 루트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "🛡️  회귀 테스트 CI 게이트 (Phase 2)"
echo "=========================================="
echo "프로젝트: $PROJECT_ROOT"
echo ""

# 회귀 테스트 실행
echo "▶ 회귀 테스트 스위트 실행 (tests/regressions/)..."
if python3 -m unittest discover -s tests/regressions -v 2>&1 | tee /tmp/regression_gate.log | tail -5; then
    RESULT=$(grep -E "^(OK|FAILED)" /tmp/regression_gate.log | tail -1)
    if [[ "$RESULT" == OK* ]]; then
        TESTS_RUN=$(grep -oE "Ran [0-9]+ tests" /tmp/regression_gate.log | tail -1 | grep -oE "[0-9]+")
        echo ""
        echo "=========================================="
        echo "✅ 회귀 테스트 ${TESTS_RUN}/${TESTS_RUN} 통과 — 배포 진행 가능"
        echo "=========================================="
        exit 0
    fi
fi

# 실패 시
echo ""
echo "=========================================="
echo "🚨 회귀 테스트 실패 — 배포 중단"
echo "=========================================="
echo ""
echo "실패 로그:"
tail -30 /tmp/regression_gate.log
echo ""
echo "⚠️  절대 우회하지 말 것. 실패 원인을 반드시 해결한 후 재배포."
echo "   (2026-07-24 사건 재발 방지 원칙)"
exit 1
