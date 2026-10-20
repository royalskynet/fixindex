#!/bin/bash
# doctor 重複 ID 檢查要比完整數字 ID：1000 與 10000 不算重複，兩個 10000 才算（2026-10-20 誤報 11 筆）。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
for f in 1000-a 10000-b 10000-c 1001-d; do printf -- '---\nid: "%s"\ntitle: t\n---\n\n## §1 Fix\nx\n' "${f%%-*}" > "$T/$f.md"; done
out=$(cd / && FIXINDEX_DIR=$T FIXINDEX_INDEX=$T/FIX-INDEX.md "$FX" doctor 2>&1 || true)
dup=$(printf '%s\n' "$out" | sed -n '/^duplicate ids/,/^[^ ]/p')
echo "$dup" | grep -q '10000-b.md' && echo "$dup" | grep -q '10000-c.md' || { echo "FAIL 真重複 10000 沒報"; exit 1; }
if echo "$dup" | grep -qE '1000-a.md|1001-d.md'; then echo "FAIL 4 碼 ID 被誤判重複"; exit 1; fi
echo PASS
