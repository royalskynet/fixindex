#!/usr/bin/env bash
# fxsync push 的 pathspec 隔離測試。
# 驗證 sync_push 只 commit 自己收到的 paths，不吞別的 session staged 的檔。
set -u

FX="$(cd "$(dirname "$0")/.." && pwd)"   # 由 script 位置推導，不寫死
D="${1:-${TMPDIR:-/tmp}/fxsync-pathspec-test}"
[ -n "$D" ] || { echo "usage: $0 <scratch-dir>" >&2; exit 1; }   # 0611：路徑變數送進 rm 前硬擋
rm -rf "$D"; mkdir -p "$D"
R="$D/repo"; mkdir -p "$R/fixes"

git -C "$R" init -q
git -C "$R" config user.email t@t; git -C "$R" config user.name t
echo base > "$R/fixes/0001-a.md"
git -C "$R" add -A; git -C "$R" commit -qm base

pass=0; fail=0
chk() { # chk <名稱> <期望> <實際>
  if [ "$2" = "$3" ]; then echo "  PASS $1"; pass=$((pass+1))
  else echo "  FAIL $1 — 期望[$2] 實際[$3]"; fail=$((fail+1)); fi
}

run_push() {  # 只 push 指定的檔
  FIXINDEX_SYNC_DEPTH=0 python3 -c "
import sys; sys.path.insert(0, '$FX')
import fxsync
r = fxsync.push('$R/fixes', paths=['$1'], message='fixindex: scoped')
print(r['kind'], r['detail'] or '')
" 2>&1 | tail -1
}

echo "T1 新檔 + 別人 staged 的檔 → 只 commit 自己的"
echo new > "$R/fixes/0002-mine.md"
echo other > "$R/other.txt"
git -C "$R" add other.txt                 # 別的 session staged
run_push "$R/fixes/0002-mine.md" >/dev/null
files=$(git -C "$R" show --stat --format= HEAD | grep -c 'other.txt')
chk "別人的 other.txt 未被吞" "0" "$files"
mine=$(git -C "$R" show --stat --format= HEAD | grep -c '0002-mine.md')
chk "自己的檔有進去" "1" "$mine"
still=$(git -C "$R" diff --cached --name-only | grep -c 'other.txt')
chk "other.txt 仍留在 index" "1" "$still"

echo "T2 自己的 path 無變動、但別人有 staged → 不得 commit"
before=$(git -C "$R" rev-parse HEAD)
run_push "$R/fixes/0001-a.md" >/dev/null
after=$(git -C "$R" rev-parse HEAD)
chk "HEAD 未前進（noop）" "$before" "$after"

echo "T3 別人 staged 一個改名 → 不得被吞"
git -C "$R" mv fixes/0001-a.md fixes/0001-renamed.md
echo more >> "$R/fixes/0002-mine.md"
run_push "$R/fixes/0002-mine.md" >/dev/null
r1=$(git -C "$R" show --stat --format= HEAD | grep -c '0001-')
chk "改名未被吞" "0" "$r1"

echo "T4 append 既有檔正常 commit"
git -C "$R" reset -q                       # 清掉測試殘留的 staged
git -C "$R" checkout -q -- . 2>/dev/null || true
echo appended >> "$R/fixes/0002-mine.md"
run_push "$R/fixes/0002-mine.md" >/dev/null
a=$(git -C "$R" show --stat --format= HEAD | grep -c '0002-mine.md')
chk "append 有 commit" "1" "$a"

echo "T5 自己的 path 是 git mv 的新路徑 → 舊路徑的刪除必須一起 commit"
git -C "$R" reset -q; git -C "$R" checkout -q -- . 2>/dev/null || true
git -C "$R" mv fixes/0002-mine.md fixes/0002-newname.md
run_push "$R/fixes/0002-newname.md" >/dev/null
adds=$(git -C "$R" show --stat --format= HEAD | grep -c '0002-newname')
chk "新路徑有 commit" "1" "$adds"
left=$(git -C "$R" status --porcelain | grep -c '^D  fixes/0002-mine.md')
chk "舊路徑刪除未殘留在 index" "0" "$left"
dup=$(git -C "$R" ls-tree -r --name-only HEAD | grep -c '0002-')
chk "HEAD 不應同時存在新舊兩份" "1" "$dup"

echo "===="
echo "TOTAL pass=$pass fail=$fail"
[ "$fail" = 0 ]
