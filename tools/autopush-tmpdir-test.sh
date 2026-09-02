#!/usr/bin/env bash
# autopush-tmpdir-test.sh — 驗證 post-commit autopush hook 的暫存錯誤檔走 ${TMPDIR:-/tmp}
# 且不再出現 Operation not permitted（沙箱 /tmp 不可寫時尤其重要）。
# 做法：
#   1. 建 bare origin + worktree，push 建立 remote-tracking ref（@{u} 可解析）
#   2. 把 origin 改名指向「不存在路徑」→ 後續 commit 觸發 hook push 必失敗
#   3. hook 應把錯誤寫進 ${TMPDIR:-/tmp}/fixindex-autopush.err（可寫）並印 warning、exit 0
set -u
HOOK_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/hooks/post-commit-autopush.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/fxhook.XXXXXX")"
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "mktemp failed" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT

BARE="$WORK/origin.git"
CLONE="$WORK/clone"
git init -q --bare "$BARE"
git clone -q -b main "$BARE" "$CLONE" 2>/dev/null || { git init -q -b main "$CLONE" && (cd "$CLONE" && git remote add origin "$BARE"); }
cd "$CLONE"
git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git push -q -u origin main 2>/dev/null   # 建立 origin/main remote-tracking ref

# 破壞 remote：指向絕對不存在路徑 → push 必失敗，但 @{u} 仍可解析
git remote set-url origin "file:///nonexistent-remote-$$.git"
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1 && echo "upstream OK" || { echo "upstream FAIL"; exit 1; }

mkdir -p .git/hooks
cp "$HOOK_SRC" .git/hooks/post-commit
chmod +x .git/hooks/post-commit

echo "y" > probe2.txt
git add probe2.txt
commit_out="$(git -c user.name=t -c user.email=t@t commit -qm "autopush hook 測試" 2>&1)"

echo "$commit_out" | grep -q "Operation not permitted" && {
  echo "FAIL: 仍出現 Operation not permitted"
  echo "$commit_out"
  exit 1
}

if echo "$commit_out" | grep -q "push 失敗"; then
  echo "PASS: hook push 失敗走 warning 分支（無 Operation not permitted）"
  echo "  warning: $(echo "$commit_out" | head -c 250)"
  exit 0
fi

echo "WARN: 無 push 失敗 warning；commit 輸出："
echo "[$commit_out]"
exit 1