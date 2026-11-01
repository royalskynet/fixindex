#!/bin/sh
# pre-commit：staged 有程式（.py／.sh／.js／fixindex）就跑全部 test_*.py 與 test_*.sh，任一 fail 擋 commit。
# 32dda15 的 MULTI-ENTRY 拒收等回歸測試靠這層才算機械攔截。
cd "$(git rev-parse --show-toplevel)" || exit 1
# hooks/*.js 也算程式：plan-path-notice.js 在 ~/.claude/hooks 曾被舊副本蓋掉（2026-11-02），
# hook 改了卻沒測＝線上行為沒驗過。
git diff --cached --name-only --diff-filter=ACM | grep -qE '(\.py|\.sh|\.js$|^fixindex)$' || exit 0
fail=0
for t in test_*.py; do
  python3 "$t" >/dev/null 2>&1 || { echo "pre-commit: FAIL $t" >&2; fail=1; }
done
for t in test_*.sh; do
  bash "$t" >/dev/null 2>&1 || { echo "pre-commit: FAIL $t" >&2; fail=1; }
done
for t in hooks/*.test.sh; do
  [ -e "$t" ] || continue
  bash "$t" >/dev/null 2>&1 || { echo "pre-commit: FAIL $t" >&2; fail=1; }
done
[ $fail -eq 0 ] || echo "pre-commit: 測試沒過，commit 已擋（逃生門 git commit --no-verify）" >&2
exit $fail
