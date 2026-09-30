#!/usr/bin/env bash
# 回歸：`fi <domain> --new` 在 domain 已有匹配檔時仍建新檔，結尾 sync_push 卻拿
# 被匹配的舊檔當 path → 新檔留在 untracked、FIX-INDEX 指向未提交檔（2026-09-30，9775）。
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
t="$(mktemp -d)"; trap 'rm -rf "$t"' EXIT
git init -q --bare -b store "$t/remote.git"
git clone -q "$t/remote.git" "$t/store" 2>/dev/null
cd "$t/store"
git config user.email t@t; git config user.name t
mkdir fixes
printf -- '---\nid: "0001"\nslug: opencode-old\ntitle: opencode old\nsymptoms: []\nstatus: active\nsupersedes: []\nrelated: []\n---\n\n# 0001 opencode old\n' > fixes/0001-opencode-old.md
git add -A; git commit -qm init; git push -q -u origin store 2>/dev/null

printf 'SYMPTOM: new thing\nROOT: r\nFIX: f\n' \
  | FIXINDEX_DIR="$t/store/fixes" "$here/fixindex" fi opencode --new --title "new entry" >/dev/null

left="$(git status --porcelain)"
[[ -z "$left" ]] || { echo "FAIL: 未提交殘留:"; echo "$left"; exit 1; }
[[ "$(ls fixes | wc -l | tr -d ' ')" = 2 ]] || { echo "FAIL: 新檔未建"; ls fixes; exit 1; }
echo PASS
