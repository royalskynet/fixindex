#!/bin/bash
# 兩裝置共用一個 fix-store 時的撞號驗收。用法：test_two_device_collision.sh online|offline
#
#   online   B 正要 push 時 A 搶先寫入 → B 被 reject → rebase → 改號 → 重推
#   offline  B 離線寫入（留 pending marker），A 佔掉同號，B 上線後下一次寫入
#
# 配號鎖是本機 flock，鎖不住第二台機器，所以兩台會在同一個 max 上配號。撞號在
# git 眼裡不是衝突（檔名不同，兩份都留），驗收條件因此是「遠端沒有重複的 4 碼前綴」。
set -e
SB=$(mktemp -d "${TMPDIR:-/tmp}/t2d.XXXXXX"); F="$(cd "$(dirname "$0")" && pwd)/fixindex"
cd $SB; git init -q --bare o.git; git clone -q o.git A 2>/dev/null; git clone -q o.git B 2>/dev/null
cd A && mkdir fixes && printf -- '---\nid: "0001"\nslug: seed\ntitle: seed\nsymptoms: []\nstatus: active\nsupersedes: []\nrelated: []\n---\n\n# 0001 seed\n' > fixes/0001-seed.md
git -c user.email=t@t -c user.name=t add -A; git -c user.email=t@t -c user.name=t commit -qm seed; git push -q origin HEAD:refs/heads/main
cd $SB/B && git pull -q --rebase
fiA(){ cd $SB/A && FIXINDEX_DIR=$SB/A/fixes FIXINDEX_INDEX=$SB/A/FIX-INDEX.md FIXINDEX_NO_BLURB=1 $F fi >/dev/null 2>&1; }
fiB(){ cd $SB/B && FIXINDEX_DIR=$SB/B/fixes FIXINDEX_INDEX=$SB/B/FIX-INDEX.md FIXINDEX_NO_BLURB=1 $F fi 2>&1 | grep -v "^ source line\|^awk:\|^\[fi\]\|^依 commands"; }
A_ENTRY='SYMPTOM: 裝置 A 的症狀 gamma 掛了
ROOT: gamma root cause here
FIX: fixed gamma
VERIFY: verified gamma
RULE: A 的規則'
B_ENTRY='SYMPTOM: 裝置 B 的症狀 beta 徹底壞掉
ROOT: beta root cause here
FIX: fixed beta
VERIFY: verified beta
RULE: B 的規則'
if [[ "$1" == online ]]; then
  # B 正要 push 時 A 搶先 → reject
  printf '#!/bin/bash\n[ -f %s/.raced ] && exit 0\ntouch %s/.raced\ncd %s/A && FIXINDEX_DIR=%s/A/fixes FIXINDEX_INDEX=%s/A/FIX-INDEX.md FIXINDEX_NO_BLURB=1 %s fi <<%s >/dev/null 2>&1\n%s\nEOF\nexit 0\n' "$SB" "$SB" "$SB" "$SB" "$SB" "$F" "'EOF'" "$A_ENTRY" > $SB/B/.git/hooks/pre-push
  chmod +x $SB/B/.git/hooks/pre-push
  echo "$B_ENTRY" | fiB
else
  # B 離線寫入（假離線訊息 → pending marker），A 佔號，B 上線後再寫一筆
  printf '#!/bin/bash\n[ -f %s/.online ] && exit 0\necho "fatal: unable to access: Could not resolve host: github.com" >&2\nexit 1\n' "$SB" > $SB/B/.git/hooks/pre-push
  chmod +x $SB/B/.git/hooks/pre-push
  echo "$B_ENTRY" | fiB
  echo "$A_ENTRY" | fiA
  touch $SB/.online
  echo 'SYMPTOM: 裝置 B 上線後寫的症狀 delta 壞了
ROOT: delta later root cause here
FIX: fixed delta
VERIFY: verified delta
RULE: B 第二條規則' | fiB
fi
echo "--- 遠端最終:"; cd $SB/A && git fetch -q origin && git ls-tree --name-only origin/main fixes/
dups=$(git ls-tree --name-only origin/main fixes/ | xargs -n1 basename | grep -oE '^[0-9]{4}' | sort | uniq -d)
if [[ -n "$dups" ]]; then echo "FAIL: 遠端仍有重複 ID: $dups"; exit 1; fi
echo "PASS: 遠端無重複 ID"
