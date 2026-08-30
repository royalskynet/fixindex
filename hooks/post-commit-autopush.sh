#!/usr/bin/env bash
# post-commit-autopush — commit 後自動 push 目前分支（0171 autosync 復原，Phase 1c）
#
# 靈感與防線（GitHub 成熟輪子研究，2026-08-18）：
#   - SO#7925850 i4h hook：推 current branch（git symbolic-ref），不硬編碼 origin/分支；
#     detached HEAD 跳過；`_local` suffix 逃生門。
#   - ariaxhan/kernel-claude autopush：skip detached/mid-rebase、origin-only、non-fatal、
#     hard-disable env（AUTOPUSH_OFF=1）。他們因共享 repo 放棄 per-commit autopush；
#     本場景是單人私人筆記 repo，commit-但-忘-push 才是病，故保留 per-commit push。
#
# 規則：
#   - 逃生門：FIXINDEX_NO_SYNC=1 或 AUTOPUSH_OFF=1 → 跳過
#   - 非 git repo / detached HEAD / mid-rebase / 無 upstream → 跳過（不干擾 rebase, feature 分支）
#   - push 失敗 → 印警告、exit 0（post-commit 只通知，不該讓 `git commit` 顯示失敗）
set -u

[ "${FIXINDEX_NO_SYNC:-0}" = "1" ] && exit 0
[ "${AUTOPUSH_OFF:-0}" = "1" ] && exit 0

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$ROOT" ] || exit 0

BRANCH="$(git symbolic-ref --short -q HEAD 2>/dev/null)" || exit 0   # detached HEAD → 跳過
[ -n "$BRANCH" ] || exit 0

# mid-rebase/mid-apply → 跳過（rebase 中途 push 半成品有害）
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)" || GIT_DIR="$ROOT/.git"
{ [ -d "$GIT_DIR/rebase-merge" ] || [ -d "$GIT_DIR/rebase-apply" ]; } && exit 0

# 無 upstream（local-only / feature 分支）→ 跳過
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1 || exit 0

if ! git push -q 2>"${TMPDIR:-/tmp}/fixindex-autopush.err"; then
  echo "fixindex post-commit: push 失敗（warning；commit 已保留，稍後手動 push）: $(head -c 200 "${TMPDIR:-/tmp}/fixindex-autopush.err")" >&2
  rm -f "${TMPDIR:-/tmp}/fixindex-autopush.err"
  exit 0
fi
rm -f "${TMPDIR:-/tmp}/fixindex-autopush.err"