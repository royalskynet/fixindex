#!/bin/bash
# bash 路徑（fixindex new）配號要跟 fxauto 同一套：9999 滿了補空號，不給 10000。
# 2026-10-04 bash next_id 自算 max+1 撞出兩筆 10000。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q && touch 9999-a.md 1000-b.md && git add -A && git -c user.email=t@t -c user.name=t commit -qm i
cd /
FIXINDEX_DIR=$T FIXINDEX_INDEX=$T/FIX-INDEX.md "$FX" new overflow-probe >/dev/null 2>&1
if ls "$T" | grep -q '^10000'; then echo "FAIL: allocated 10000"; exit 1; fi
ls "$T"/1001-overflow-probe.md >/dev/null && echo PASS
