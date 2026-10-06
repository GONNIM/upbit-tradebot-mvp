#!/bin/bash
# WO-25 검증 (임시 worktree, .env 없음, main 무변경): 게이트 · 시험 · 구 코드 재시작 재현 · 단독 revert
set -u
REPO=/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp
S=/private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/9339ae21-5ead-4004-a49c-c5714e34e251/scratchpad
WT=$S/wo25_wt
WO=$S/wo25_wt_old2
NEW=9dd9bd7
OLD=b37c7a0
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

echo "=================== [B] $NEW WO-25 시험 (-v)"
(cd "$WT" && python3 -m unittest tests.regressions.test_r_2026_10_06_wo25_preorder_reject_audit -v 2>&1 | grep -E "\.\.\. (ok|FAIL|ERROR)$|^Ran|^OK|FAILED")


echo "=================== [D] revert $NEW ($(git -C "$REPO" log --format=%s -1 "$NEW" | cut -c1-50))"
git -C "$WT" revert --no-commit "$NEW" >/dev/null 2>&1
conflicts=$(git -C "$WT" diff --name-only --diff-filter=U)
echo "충돌 파일: ${conflicts:-없음}"
echo "변경 파일:"; git -C "$WT" diff --cached --stat | tail -13
(cd "$WT" && python3 -m py_compile core/strategy_engine.py core/trader.py pages/dashboard.py && echo "py_compile OK")
(cd "$WT" && bash scripts/regression_gate.sh 2>&1 | grep -E "회귀 테스트 .*통과|실패|FAILED|❌" | tail -3)

git -C "$WT" reset -q --hard HEAD
for w in "$WT" "$WO"; do git -C "$REPO" worktree remove --force "$w"; done
