#!/bin/bash
# bash 路徑（fixindex new）配號要跟 fxauto 同一套：數值取 max，9999 之後是 10000，
# 而且再配一次要是 10001（舊版字典序永遠回 10000 而撞號，2026-10-04）。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q && touch 9999-a.md 1000-b.md && git add -A && git -c user.email=t@t -c user.name=t commit -qm i
cd /
FIXINDEX_DIR=$T FIXINDEX_INDEX=$T/FIX-INDEX.md "$FX" new overflow-probe >/dev/null 2>&1
FIXINDEX_DIR=$T FIXINDEX_INDEX=$T/FIX-INDEX.md "$FX" new overflow-probe2 >/dev/null 2>&1
ls "$T"/10000-overflow-probe.md "$T"/10001-overflow-probe2.md >/dev/null && echo PASS
