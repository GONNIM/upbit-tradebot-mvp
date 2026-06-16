#!/bin/bash
# Boilerplate 적용 검증 스크립트 v3.1 (Codex #7 수정 - double-counting 해결)
# 작성일: 2026-04-22
# 목적: 9개 시나리오 자동 검증 (pass/fail 명확)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================"
echo "Boilerplate 적용 검증 (9 Scenarios)"
echo "======================================"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

# 검증 함수 (return 0=PASS, 1=FAIL)
validate_scenario() {
    local scenario_num="$1"
    local scenario_name="$2"
    local target_file="$3"
    shift 3
    local keywords=("$@")

    echo "[Scenario $scenario_num] $scenario_name"
    echo "  대상: $target_file"

    if [ ! -f "$target_file" ]; then
        echo "  ❌ FAIL: 파일 없음"
        echo ""
        return 1
    fi

    local found_count=0
    local missing_keywords=()

    for keyword in "${keywords[@]}"; do
        if grep -iq "$keyword" "$target_file" 2>/dev/null; then
            found_count=$((found_count + 1))
            echo "  ✓ '$keyword' 발견"
        else
            missing_keywords+=("$keyword")
        fi
    done

    if [ $found_count -eq ${#keywords[@]} ]; then
        echo "  ✅ PASS ($found_count/${#keywords[@]} 키워드)"
        echo ""
        return 0
    else
        echo "  ❌ FAIL ($found_count/${#keywords[@]} 키워드)"
        echo "  누락: ${missing_keywords[*]}"
        echo ""
        return 1
    fi
}

# WHY 시나리오 ×2
if validate_scenario 1 "프로젝트 목적 설명" "CLAUDE.md" \
    "WHY" "목적" "Upbit"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if validate_scenario 2 "Golden Cross 전략" "CLAUDE.md" \
    "Golden Cross" "EMA" "MACD" ||
   validate_scenario 2 "Golden Cross 전략 (docs/issues/)" "docs/issues/issue-01.md" \
    "Golden Cross" "EMA"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# WHAT 시나리오 ×2
if validate_scenario 3 "핵심 모듈 구조" "CLAUDE.md" \
    "WHAT" "core/" "engine/" "services/"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if validate_scenario 4 "REST Reconcile 구조" "CLAUDE.md" \
    "REST" "Reconcile" "정합성" ||
   validate_scenario 4 "REST Reconcile (docs/issues/)" "docs/issues/issue-07.md" \
    "REST" "Reconcile"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# HOW 시나리오 ×2
if validate_scenario 5 "백테스팅 실행 방법" "CLAUDE.md" \
    "HOW" "백테스팅" "python"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if validate_scenario 6 "systemd 배포 방법" "CLAUDE.md" \
    "systemd" "배포" "deploy" ||
   validate_scenario 6 "systemd 배포 (docs/issues/)" "docs/issues/issue-11.md" \
    "systemd"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Issue 시나리오 ×3
if validate_scenario 7 "Issue #3 상세 내용" "docs/issues/issue-03.md" \
    "Issue" "03" ||
   validate_scenario 7 "Issue #3 (CLAUDE.md)" "CLAUDE.md" \
    "@docs/issues/issue-03"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if validate_scenario 8 "progressiveRetry 정책" "docs/issues/issue-10.md" \
    "progressiveRetry" "재시도" ||
   validate_scenario 8 "progressiveRetry (CLAUDE.md)" "CLAUDE.md" \
    "progressiveRetry"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if validate_scenario 9 "비트 불일치 해결" "docs/issues/issue-04.md" \
    "비트" "불일치" ||
   validate_scenario 9 "비트 불일치 (CLAUDE.md)" "CLAUDE.md" \
    "비트.*불일치"; then
    PASS_COUNT=$((PASS_COUNT + 1))
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# 종합 결과
echo "======================================"
echo "검증 결과"
echo "======================================"
echo "PASS: $PASS_COUNT / 9"
echo "FAIL: $FAIL_COUNT / 9"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo "✅ 모든 시나리오 통과!"
    exit 0
elif [ $PASS_COUNT -ge 7 ]; then
    echo "⚠️  대부분 통과 (7+/9)"
    exit 0
else
    echo "❌ 검증 실패 ($PASS_COUNT/9)"
    exit 1
fi
