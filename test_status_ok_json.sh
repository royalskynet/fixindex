#!/bin/bash
# `fixindex status`（人類可讀）尾行要給一行 JSON，讓 `fixindex status | grep -q '"ok": true'` 成立；
# 有 error 時必須是 false，不能一律 true（fix 0007§27 驗收踩到 status 無 JSON 的坑，2026-11-12）。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/fixes"
git init -q "$T"
export FIXINDEX_DIR=$T/fixes FIXINDEX_INDEX=$T/FIX-INDEX.md
printf '# x\n' > "$T/fixes/0001-a.md"
printf '# index\n' > "$T/FIX-INDEX.md"
sleep 1  # mtime 秒級解析度，stale 判定靠先後
[ "$("$FX" status | tail -1)" = '{"ok": true, "errors": 0}' ]
# index 比 fixes 舊 → 必須 false（不能寫死 true）
touch "$T/fixes/0001-a.md"
[ "$("$FX" status | tail -1)" = '{"ok": false, "errors": 1}' ]
echo PASS
