#!/usr/bin/env bash
# 回歸（issue #10）：寫入命令的 read-modify-write 必須整段在 _repo_lock 內。
# 壞序列：A 已 re-index（FIX-INDEX.md 改了未 commit）→ B 的 pull --rebase --autostash
# 把 A 的半成品 stash / rebase / restore → 衝突標記被 A 原樣 commit，或留在 stash 裡。
# 慢點用 python3 shim：A 的 `fxsync.py push` 前睡 3 秒，B 在這窗口內 pull。
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
real_py="$(command -v python3)"
t="$(mktemp -d)"; trap 'rm -rf "$t"' EXIT
# 隔離 zshenv：fixindex 會從 $HOME/.zshenv eval FIXINDEX_INDEX。放一個 decoy，
# hold 的 re-exec 若沒把已解析的 INDEX 帶下去就會寫到 decoy（實測曾覆寫真庫）。
mkdir -p "$t/home" "$t/decoy"
echo "export FIXINDEX_INDEX=$t/decoy/FIX-INDEX.md" > "$t/home/.zshenv"
# 照真實 shell：zshenv 已把 FIXINDEX_INDEX export 進環境，最外層守衛擋掉跨庫值。
export HOME="$t/home" FIXINDEX_INDEX="$t/decoy/FIX-INDEX.md"
git init -q --bare -b store "$t/remote.git"
git clone -q "$t/remote.git" "$t/a" 2>/dev/null
cd "$t/a"; git config user.email t@t; git config user.name t
mkdir fixes
printf -- '---\nid: "0001"\nslug: seed\ntitle: seed\nsymptoms: []\nstatus: active\nsupersedes: []\nrelated: []\n---\n\n# 0001 seed\n' > fixes/0001-seed.md
FIXINDEX_NO_SYNC=1 FIXINDEX_DIR="$t/a/fixes" "$here/fixindex" re-index >/dev/null
git add -A; git commit -qm init; git push -q -u origin store 2>/dev/null

# 他處先推一個會跟 A 的 re-index 衝突的 FIX-INDEX.md 變更
git clone -q "$t/remote.git" "$t/c" 2>/dev/null
( cd "$t/c"; git config user.email t@t; git config user.name t
  sed -i '' 's/| 0001 |/| 0009 | remote |\n| 0001 |/' FIX-INDEX.md 2>/dev/null || true
  printf '\n<!-- remote edit -->\n' >> FIX-INDEX.md
  sed -i '' 's/seed/seed-remote/' FIX-INDEX.md
  git commit -qam remote )

mkdir "$t/shim"
cat > "$t/shim/python3" <<EOF
#!/bin/bash
case "\$*" in *fxsync.py\ push*) touch "$t/in-window"; sleep 3 ;; esac
exec "$real_py" "\$@"
EOF
chmod +x "$t/shim/python3"

printf 'SYMPTOM: alpha\nROOT: r\nFIX: f\n' \
  | PATH="$t/shim:$PATH" FIXINDEX_DIR="$t/a/fixes" "$here/fixindex" fi alpha --new --title alpha >"$t/a.out" 2>&1 &
apid=$!
for _ in $(seq 100); do [[ -e "$t/in-window" ]] && break; sleep 0.1; done
[[ -e "$t/in-window" ]] || { echo "FAIL: A 沒進到慢點"; cat "$t/a.out"; exit 1; }
( cd "$t/c"; git push -q 2>/dev/null )
FIXINDEX_DIR="$t/a/fixes" "$real_py" "$here/fxsync.py" pull --soft >"$t/b.out" 2>&1 || true
arc=0; wait "$apid" || arc=$?

fail=0
# 不論 A 成敗：衝突標記不得進任何 commit、半成品不得留在 stash（壞結局＝靜默成功）
if git log -p --all --format= | grep -qE '^\+(<<<<<<<|>>>>>>>)'; then echo "FAIL: 衝突標記被 commit"; fail=1; fi
[[ -z "$(git stash list)" ]] || { echo "FAIL: 半成品留在 stash"; git stash list; fail=1; }
[[ ! -e "$t/decoy/FIX-INDEX.md" ]] || { echo "FAIL: 寫到 zshenv 的 INDEX（跨庫）"; fail=1; }
# 遠端改的正是同一段 → A 撞真衝突是對的，但必須出聲（好結局＝die 並帶 conflict）
if [[ $arc != 0 ]]; then
  grep -q 'conflict' "$t/a.out" || { echo "FAIL: A rc=$arc 但沒說 conflict（靜默失敗）"; fail=1; }
else
  [[ -z "$(git status --porcelain)" ]] || { echo "FAIL: 未提交殘留"; git status --porcelain; fail=1; }
  git ls-files --error-unmatch fixes/0002-alpha.md >/dev/null 2>&1 || { echo "FAIL: A 的條目沒 commit"; fail=1; }
fi
[[ $fail = 0 ]] || { echo "--- A rc=$arc:"; cat "$t/a.out"; echo "--- B:"; cat "$t/b.out"; exit 1; }
echo "PASS (A rc=$arc)"
