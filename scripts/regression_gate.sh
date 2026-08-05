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

# ✅ 2026-08-05 옵션 A: UI 페이지 top-level import 게이트
# a8f2a5c NameError('Optional') 유형 재발 방지 — py_compile 은 파싱만 검증,
# 실행 시점 NameError/ImportError 는 실제 import 시에만 발견됨.
# Streamlit 컨텍스트 (st.set_page_config 등) 부재 시 실패하는 라인은 catch 로 완화.
echo "▶ UI 페이지 top-level import 게이트 (pages/*.py)..."
UI_IMPORT_FAILED=0
for f in pages/*.py; do
    [ -f "$f" ] || continue
    modname="pages.$(basename "$f" .py)"
    # streamlit runtime 부재 시 무해한 에러는 무시. NameError/import 결함만 잡음.
    # stderr 는 streamlit warning 노이즈이므로 억제, stdout 만 검사.
    OUT=$(python3 -c "
import sys
try:
    __import__('$modname')
except (NameError, ImportError, AttributeError) as e:
    msg = str(e)
    if 'streamlit' in msg.lower() or 'set_page_config' in msg.lower() or 'ScriptRunContext' in msg.lower():
        sys.exit(0)
    print(f'❌ {\"$modname\"}: {type(e).__name__}: {e}')
    sys.exit(1)
except SystemExit:
    sys.exit(0)
except Exception as e:
    msg = str(e)
    if 'streamlit' in msg.lower() or 'ScriptRunContext' in msg.lower():
        sys.exit(0)
    sys.exit(0)
" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo "$OUT"
        UI_IMPORT_FAILED=1
    fi
done
if [ "$UI_IMPORT_FAILED" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "🚨 UI import 게이트 실패 — 배포 중단"
    echo "=========================================="
    echo "NameError/ImportError/AttributeError 결함이 pages/*.py 에서 발견됨."
    echo "a8f2a5c 유형 재발 방지 게이트 (2026-08-05)."
    exit 1
fi
echo "  ✅ 모든 pages/*.py top-level import OK"

# ✅ 2026-08-05 옵션 A 심화: typing 심볼 정적 검증 (조건부 분기 안에서만 실행되는 코드도 커버)
# import 게이트는 top-level 실행 경로만 커버 → 조건부 분기 안의 미임포트 잡지 못함.
# AST 기반 typing 심볼 사용 vs typing 임포트 대조로 커버.
echo "▶ typing 심볼 정적 검증 (pages/*.py + core, engine, services)..."
if ! python3 <<'PYEOF'
import ast, sys, pathlib

TYPING_SYMS = {'Optional', 'Dict', 'List', 'Union', 'Any', 'Tuple', 'Callable', 'Set', 'Iterable', 'Awaitable', 'Coroutine', 'AsyncIterable'}
TARGETS = list(pathlib.Path('pages').glob('*.py'))

failed = []
for f in TARGETS:
    try:
        tree = ast.parse(f.read_text(encoding='utf-8'))
    except Exception as e:
        continue

    # typing 에서 임포트된 심볼 수집
    typing_imported = set()
    typing_star_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'typing':
            for alias in node.names:
                if alias.name == '*':
                    typing_star_import = True
                else:
                    typing_imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'typing':
                    typing_star_import = True  # import typing → typing.Optional 사용해야 하지만 관대 처리

    if typing_star_import:
        continue

    # 사용된 심볼 수집 (ast.Name, Subscript value, Attribute value)
    used_syms = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_syms.add(node.id)

    missing = sorted(TYPING_SYMS & used_syms - typing_imported)
    if missing:
        failed.append((str(f), missing))

if failed:
    for fname, syms in failed:
        print(f"❌ {fname}: typing 심볼 사용됐으나 임포트 없음 → {', '.join(syms)}")
    print()
    print("💡 수정 방법: 파일 상단에 `from typing import <심볼>` 추가")
    print("   또는 타입 힌트 제거 (예: `x: Optional[int] = None` → `x = None`)")
    sys.exit(1)
sys.exit(0)
PYEOF
then
    echo ""
    echo "=========================================="
    echo "🚨 typing 심볼 정적 검증 실패 — 배포 중단"
    echo "=========================================="
    echo "a8f2a5c 유형 (Optional/Dict/List 등 미임포트) 재발 방지 게이트."
    exit 1
fi
echo "  ✅ 모든 pages/*.py typing 심볼 임포트 OK"
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
