#!/bin/bash
# WO-25 B 검증 (임시 worktree, .env 없음, main 무변경): 게이트 · 시험 · B 전 코드(7141d77) 시험 · WO-25 3커밋 함께 revert
set -u
REPO=/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp
S=/private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/9339ae21-5ead-4004-a49c-c5714e34e251/scratchpad
WT=$S/wo25b_wt
WO=$S/wo25b_wt_old
NEW=33a5d9e
OLD=7141d77
TF=tests/regressions/test_r_2026_10_06_wo25_preorder_reject_audit.py
export UPBIT_ACCESS=dummy UPBIT_SECRET=dummy TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID=

for w in "$WT" "$WO"; do git -C "$REPO" worktree remove --force "$w" 2>/dev/null; done
git -C "$REPO" worktree add --detach "$WT" "$NEW" >/dev/null 2>&1 || { echo "worktree 생성 실패"; exit 1; }
git -C "$REPO" worktree add --detach "$WO" "$OLD" >/dev/null 2>&1 || { echo "worktree(old) 생성 실패"; exit 1; }
for w in "$WT" "$WO"; do
  echo "worktree $(basename $w) .env 개수: $(ls -a "$w" | grep -c '^\.env$')"
  ln -s "$REPO/.streamlit" "$w/.streamlit"
done

echo "=================== [A] $NEW 게이트 (.env 없음)"
(cd "$WT" && bash scripts/regression_gate.sh 2>&1 | grep -E "회귀 테스트 .*통과|실패|FAILED|❌" | tail -3)

echo "=================== [B] $NEW WO-25 시험 + WO-9·WO-24 페이지 시험"
(cd "$WT" && python3 -m unittest tests.regressions.test_r_2026_10_06_wo25_preorder_reject_audit tests.regressions.test_r_2026_09_30_wo9_reject_audit_roundtrip tests.regressions.test_r_2026_10_05_wo24_unfilled_buy_audit 2>&1 | grep -E "^Ran|^OK|FAILED")

echo "=================== [C] B 전 코드 $OLD 에서 새 시험 파일 (문구 시험 실패 확인)"
cp "$REPO/$TF" "$WO/$TF"
(cd "$WO" && python3 -m unittest tests.regressions.test_r_2026_10_06_wo25_preorder_reject_audit -v 2>&1 | grep -E "^test_4|^(FAIL|ERROR):|^Ran|^OK|FAILED|AssertionError|ImportError" | cut -c1-220)
(cd "$WO" && git checkout -q -- "$TF")

echo "=================== [D] revert 33a5d9e + 7141d77 + 9dd9bd7 함께 (새 것부터)"
git -C "$WT" revert --no-commit 33a5d9e 7141d77 9dd9bd7 >/dev/null 2>&1
echo "revert 종료 코드: $?"
conflicts=$(git -C "$WT" diff --name-only --diff-filter=U)
echo "충돌 파일: ${conflicts:-없음}"
echo "변경 파일:"; git -C "$WT" diff --cached --stat | tail -20
echo "되돌린 뒤 버전: $(grep -o 'v1\.2026\.[0-9.]*' "$WT/pages/dashboard.py" | head -1)"
(cd "$WT" && python3 -m py_compile core/strategy_engine.py core/trader.py services/db.py pages/audit_viewer.py pages/dashboard.py && echo "py_compile OK")
(cd "$WT" && bash scripts/regression_gate.sh 2>&1 | grep -E "회귀 테스트 .*통과|실패|FAILED|❌" | tail -3)

git -C "$WT" reset -q --hard HEAD
for w in "$WT" "$WO"; do git -C "$REPO" worktree remove --force "$w"; done
