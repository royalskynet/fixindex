#!/usr/bin/env bash
# fixindex find --spill（2026-11-02）：預設回全文，加了 --spill 只回 ID／檔案／標題，要全文再 show。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
FX="$HERE/fixindex"
export FIXINDEX_DIR="$HERE/fixes"
fail=0
chk() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }

o="$(python3 "$HERE/fxsearch.py" merge --limit 2 --spill 2>&1)"
case "$o" in *"概略模式"*) chk "spill 標示概略模式" 1 1 ;; *) chk "spill 標示概略模式" 1 0 ;; esac
case "$o" in *"0002-"*.md*) chk "spill 給檔名" 1 1 ;; *) chk "spill 給檔名 (輸出: $o)" 1 0 ;; esac
case "$o" in *"§"*) chk "spill 不給節號" 0 1 ;; *) chk "spill 不給節號" 0 0 ;; esac

o2="$(python3 "$HERE/fxsearch.py" merge --limit 2 2>&1)"
case "$o2" in *"§"*) chk "預設仍給節號" 1 1 ;; *) chk "預設仍給節號 (輸出: $o2)" 1 0 ;; esac
case "$o2" in *"概略模式"*) chk "預設不進概略" 0 1 ;; *) chk "預設不進概略" 0 0 ;; esac

# 兩段式真的接得上：spill 給的檔名可直接餵 show
f="$(printf '%s\n' "$o" | sed -n 's/.* \([0-9][0-9]*\)-[^ ]*\.md.*/\1/p' | head -1)"
if [ -n "$f" ] && "$FX" show "$f" >/dev/null 2>&1; then chk "spill 檔名可餵 show" 0 0; else chk "spill 檔名可餵 show" 0 1; fi

"$FX" find 2>&1 | grep -q -- '--spill' && chk "usage 提 --spill" 0 0 || chk "usage 提 --spill" 0 1

[ "$fail" = 0 ] && echo "PASS find_spill" || echo "FAIL find_spill"
exit "$fail"
