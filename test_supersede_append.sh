#!/bin/bash
# supersede 多次指向同一新條目：supersedes 要累加、不重複（2026-10-27 只留第一筆）。
set -e
FX="$(cd "$(dirname "$0")" && pwd)/fixindex"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
for f in 0001-a 0002-b 0003-c 0009-new; do printf -- '---\nid: "%s"\ntitle: t %s\nstatus: active\nsupersedes: []\n---\n\n## §1 Fix\nx\n' "${f%%-*}" "$f" > "$T/$f.md"; done
run() { (cd / && FIXINDEX_DIR=$T FIXINDEX_INDEX=$T/FIX-INDEX.md FIXINDEX_NO_SYNC=1 "$FX" supersede "$@" >/dev/null 2>&1); }
run 0001 0009; run 0002 0009; run 0003 0009; run 0002 0009
got=$(grep '^supersedes:' "$T/0009-new.md")
[ "$got" = "supersedes: [0001, 0002, 0003]" ] || { echo "FAIL got: $got"; exit 1; }
echo PASS
