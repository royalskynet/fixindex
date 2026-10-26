#!/bin/sh
# pre-commit：staged 有程式（.py／.sh／fixindex）就跑全部 test_*.py 與 test_*.sh，任一 fail 擋 commit。
# 32dda15 的 MULTI-ENTRY 拒收等回歸測試靠這層才算機械攔截。
cd "$(git rev-parse --show-toplevel)" || exit 1
git diff --cached --name-only --diff-filter=ACM | grep -qE '(\.py|\.sh|^fixindex)$' || exit 0
fail=0
for t in test_*.py; do
  python3 "$t" >/dev/null 2>&1 || { echo "pre-commit: FAIL $t" >&2; fail=1; }
done
for t in test_*.sh; do
  bash "$t" >/dev/null 2>&1 || { echo "pre-commit: FAIL $t" >&2; fail=1; }
done
[ $fail -eq 0 ] || echo "pre-commit: 測試沒過，commit 已擋（逃生門 git commit --no-verify）" >&2
exit $fail
