#!/bin/bash
# WO-19 게이트(.env 격리) + 단독 revert 실측 (임시 worktree, main 무변경)
set -u
REPO=/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp
WT=/private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/9339ae21-5ead-4004-a49c-c5714e34e251/scratchpad/wo19_wt
COMMITS=(8fd26c1)

git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
git -C "$REPO" worktree add --detach "$WT" HEAD >/dev/null 2>&1 || { echo "worktree 생성 실패"; exit 1; }
ls -a "$WT" | grep -c '^\.env$' | sed 's/^/worktree .env 개수: /'
ln -s "$REPO/.streamlit" "$WT/.streamlit"
export UPBIT_ACCESS=dummy UPBIT_SECRET=dummy TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID=

echo "=================== HEAD $(git -C "$WT" log --oneline -1) 게이트 (.env 없음)"
(cd "$WT" && bash scripts/regression_gate.sh 2>&1 | grep -E "회귀 테스트 .*통과|실패|FAILED|❌" | tail -3)

for c in "${COMMITS[@]}"; do
  echo "=================== revert $c ($(git -C "$REPO" log --format=%s -1 "$c" | cut -c1-40))"
  git -C "$WT" reset -q --hard HEAD
  git -C "$WT" clean -qfd
  git -C "$WT" revert --no-commit "$c" >/dev/null 2>&1
  conflicts=$(git -C "$WT" diff --name-only --diff-filter=U)
  echo "충돌 파일: ${conflicts:-없음}"
  echo "변경 파일:"; git -C "$WT" diff --cached --stat | tail -8
  (cd "$WT" && python3 -m py_compile core/strategy_engine.py services/db.py engine/live_loop.py pages/dashboard.py && echo "py_compile OK")
  (cd "$WT" && bash scripts/regression_gate.sh 2>&1 | grep -E "회귀 테스트 .*통과|실패|FAILED|❌" | tail -3)
done

git -C "$WT" reset -q --hard HEAD
git -C "$REPO" worktree remove --force "$WT"
