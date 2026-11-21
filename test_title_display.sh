#!/bin/bash
# list / insights / externals / re-index 顯示的是 title 的值，不是 YAML 原文：
# fxmeta 寫檔時 `: `、引號等會包成 '…' 或 "…"（含 \" \\ 跳脫），顯示前要解開；
# title 裡的 `|` 在 FIX-INDEX 表格要跳脫成 `\|`，否則整列欄位錯位。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
R=$(mktemp -d); trap 'rm -rf "$R"' EXIT
T=$R/fixes; mkdir "$T"
mk() { printf -- '---\nid: "%s"\nslug: %s\ntype: %s\ntitle: %s\ntags: [t]\n---\n\n## §1 Fix\nx\n' "${1%%-*}" "${1#*-}" "$2" "$3" > "$T/$1.md"; }
mk 0001-colon   defect   "'fix: crash on resume'"
mk 0002-escaped defect   '"it'"'"'s \"quoted\" C:\\tmp"'
mk 0003-pipe    defect   'a | b pipe'
mk 0004-ins     insight  "'note: cache key'"
mk 0005-ext     external '"don'"'"'t trust: docs"'
run() { (cd / && FIXINDEX_DIR=$T FIXINDEX_INDEX=$R/FIX-INDEX.md FIXINDEX_NO_SYNC=1 "$FX" "$@" 2>/dev/null); }
fail=0
expect() { printf '%s\n' "$2" | grep -qF -- "$3" || { echo "FAIL $1: missing [$3]"; printf '%s\n' "$2" | sed 's/^/    /'; fail=1; }; }

out=$(run list)
expect list "$out" "fix: crash on resume"
expect list "$out" "it's \"quoted\" C:\\tmp"
if printf '%s\n' "$out" | grep -q "'fix: crash"; then echo "FAIL list: quote marks kept"; fail=1; fi

expect insights "$(run insights)" "  0004-ins                                  note: cache key"
expect externals "$(run externals)" "  0005-ext                                  don't trust: docs"

run re-index >/dev/null
idx=$(cat "$R/FIX-INDEX.md")
expect re-index "$idx" "| 0001 | colon | fix: crash on resume | t |"
expect re-index "$idx" "| 0002 | escaped | it's \"quoted\" C:\\tmp | t |"
expect re-index "$idx" "| 0003 | pipe | a \\| b pipe | t |"

[ $fail -eq 0 ] && echo PASS
exit $fail
