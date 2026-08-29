#!/bin/bash
# secret-scan-test.sh — secret-scan.sh 端到端測試
# 自包含: 全部在 mktemp 臨時 repo 執行, 不污染任何真實 repo。
# 10 條: 1)乾淨 2)TG token擋 3)GH PAT擋 4)sk-誤報1不擋 5)hex誤報2不擋
#        6)no-verify 繞pre-commit但push擋 7)SECRET_SCAN_OFF放行 8)fail-closed擋
#        9)歷史leak在別ref,乾淨新分支首次push應過(範圍控制) 10)新分支自身leak仍擋
# 全過印 ALL PASS; 任一失敗印 FAILURE 且 exit 1。
# 假憑證用 python 隨機生成語境+高熵, 不寫字面值(FIX repo 自我誤報防線)。

WRAPPER="${FIXINDEX_HOME:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}/tools/secret-scan.sh"
PASS_CT=0; FAIL_CT=0

ok()   { PASS_CT=$((PASS_CT+1)); printf "PASS  %s\n" "$1"; }
ng()   { FAIL_CT=$((FAIL_CT+1)); printf "FAIL  %s\n" "$1"; }

# --- 產生假憑證行 (隨機, 高熵, 語境封裝) ---
gen_tg() { # telegram_bot_token = digits:A<34>
    /usr/bin/python3 - <<'PY'
import random, string
seg=''.join(random.choice(string.ascii_lowercase+string.digits+'_') for _ in range(34))
print('telegram_bot_token = "%s:A%s"' % (''.join(random.choice('0123456789') for _ in range(12)), seg))
PY
}
gen_gh() { # ghp_ + 36 hex
    /usr/bin/python3 - <<'PY'
import random
print('token = "ghp_%s"' % ''.join(random.choice('0123456789abcdef') for _ in range(36)))
PY
}
gen_apple() { # 散文有 sk- 但不足 20 字元 (誤報樣本1)
    printf 'he wrote "sk-17" in a note about kernels.\n'
}
gen_hex() {  # 40 hex (git sha/lorem) (誤報樣本2)
    /usr/bin/python3 - <<'PY'
import random
print('commit_id = "%s"' % ''.join(random.choice('0123456789abcdef') for _ in range(40)))
PY
}

newrepo() { # $1=dir, 建 base commit
    mkdir -p "$1"; cd "$1" || return 1
    git init -q
    git config user.email t@t; git config user.name t
    echo ok > base.txt; git add base.txt; git commit -qm base
}

install_hook() { # $1=repo $2=hook名 (pre-commit|pre-push)
    local hook="$1/.git/hooks/$2"
    local mode="staged"
    [ "$2" = "pre-push" ] && mode="push"
    cat > "$hook" <<EOF
#!/bin/sh
S="$WRAPPER"
[ -x "\$S" ] || { echo "FATAL: secret-scan.sh missing" >&2; exit 1; }
exec "\$S" $mode "\$@"
EOF
    chmod +x "$hook"
}

[ ! -x "$WRAPPER" ] && { echo "FATAL: wrapper missing -> abort"; exit 99; }

### T1 乾淨 commit → 通過
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
printf '# hi\n' > "$D/r.md"; git -C "$D" add r.md
if git -C "$D" commit -qm t1 >/dev/null 2>&1; then ok "T1 clean commit"; else ng "T1 clean commit"; fi
rm -rf "$D"

### T2 TG token → pre-commit 擋
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
gen_tg > "$D/env.py"; git -C "$D" add env.py
git -C "$D" commit -qm t2 >/dev/null 2>&1
[ $? -ne 0 ] && ok "T2 tg blocked" || ng "T2 tg blocked"
rm -rf "$D"

### T3 GH PAT → pre-commit 擋
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
gen_gh > "$D/conf.py"; git -C "$D" add conf.py
git -C "$D" commit -qm t3 >/dev/null 2>&1
[ $? -ne 0 ] && ok "T3 ghpat blocked" || ng "T3 ghpat blocked"
rm -rf "$D"

### T4 誤報樣本1 sk- 不足 → 不擋
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
gen_apple > "$D/prose.txt"; git -C "$D" add prose.txt
if git -C "$D" commit -qm t4 >/dev/null 2>&1; then ok "T4 sk- false pos not blocked"; else ng "T4 sk- false pos not blocked"; fi
rm -rf "$D"

### T5 誤報樣本2 40hex → 不擋
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
gen_hex > "$D/sha.py"; git -C "$D" add sha.py
if git -C "$D" commit -qm t5 >/dev/null 2>&1; then ok "T5 hex false pos not blocked"; else ng "T5 hex false pos not blocked"; fi
rm -rf "$D"

### T6 --no-verify 繞 pre-commit, 但 push 被 pre-push 擋
D=$(mktemp -d); newrepo "$D"
install_hook "$D" pre-commit; install_hook "$D" pre-push
BARE=$(mktemp -d); git init -q --bare "$BARE" 2>/dev/null
git -C "$D" remote add origin "$BARE"
git -C "$D" push -q origin HEAD:main >/dev/null 2>&1   # 推乾淨 base 建立基準
gen_tg > "$D/leak.py"; git -C "$D" add leak.py
git -C "$D" commit -qm t6 --no-verify >/dev/null 2>&1   # 繞 pre-commit 成功
git -C "$D" push origin HEAD:main >/dev/null 2>&1       # pre-push 應擋
[ $? -ne 0 ] && ok "T6 push blocked" || ng "T6 push blocked"
rm -rf "$D" "$BARE"

### T7 SECRET_SCAN_OFF=1 → 放行
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
gen_tg > "$D/env.py"; git -C "$D" add env.py
if SECRET_SCAN_OFF=1 git -C "$D" commit -qm t7 >/dev/null 2>&1; then ok "T7 escape hatch passes"; else ng "T7 escape hatch passes"; fi
rm -rf "$D"

### T8 fail-closed: PATH 無 gitleaks → 被擋
D=$(mktemp -d); newrepo "$D"; install_hook "$D" pre-commit
# 確認該 PATH 下無 gitleaks
if PATH=/usr/bin:/bin command -v gitleaks >/dev/null 2>&1; then
    ng "T8 PATH /usr/bin:/bin still has gitleaks (test setup broken)"
else
    printf '# fine\n' > "$D/f.txt"; git -C "$D" add f.txt
    if PATH=/usr/bin:/bin git -C "$D" commit -qm t8 >/dev/null 2>&1; then
        ng "T8 fail-closed NOT blocking (should block)"
    else
        ok "T8 fail-closed blocks"
    fi
fi
rm -rf "$D"

### T9 歷史 leak 在別 ref → 乾淨新分支首次 push 應通過（範圍控制回歸）
D=$(mktemp -d); newrepo "$D"
install_hook "$D" pre-commit; install_hook "$D" pre-push
BARE=$(mktemp -d); git init -q --bare "$BARE" 2>/dev/null
git -C "$D" remote add origin "$BARE"
git -C "$D" push -q origin HEAD:main >/dev/null 2>&1           # origin/main = 乾淨 base
git -C "$D" checkout -q -b leak-branch                          # 從 base 開 leak 分支
gen_tg > "$D/leak-legacy.py"; git -C "$D" add leak-legacy.py
git -C "$D" commit -qm t9legacy --no-verify >/dev/null 2>&1    # 製造含 leak 的 commit
git -C "$D" push -q origin HEAD:legacy-backup --no-verify >/dev/null 2>&1  # 歷史 leak 在別的 ref
git -C "$D" checkout -q main                                    # 回乾淨 base
git -C "$D" checkout -q -b feature                              # 從 base(乾淨) 開新分支
printf '# clean\n' > "$D/clean.py"; git -C "$D" add clean.py
git -C "$D" commit -qm t9clean >/dev/null 2>&1                  # pre-commit 應過
git -C "$D" push origin HEAD:feature >/dev/null 2>&1            # 新分支首次 push, rsha=0 → merge-base range
rc=$?
# 退化檢查: wrapper 若含 --all 則應擋(轉紅)。此處只做靜態快速信號, 端到端由上面 push 判定。
if grep -v '^[[:space:]]*#' "$WRAPPER" | grep -q -- '--all'; then
    ng "T9 regression: --all present in wrapper"
else
    [ "$rc" -eq 0 ] && ok "T9 clean new branch push passes (history leak elsewhere)" || ng "T9 clean new branch push passes (history leak elsewhere)"
fi
rm -rf "$D" "$BARE"

### T10 新分支自身新增 leak → 首次 push 應被擋
D=$(mktemp -d); newrepo "$D"
install_hook "$D" pre-commit; install_hook "$D" pre-push
BARE=$(mktemp -d); git init -q --bare "$BARE" 2>/dev/null
git -C "$D" remote add origin "$BARE"
git -C "$D" push -q origin HEAD:main >/dev/null 2>&1
git -C "$D" checkout -q -b leak-branch2
gen_tg > "$D/leak-legacy2.py"; git -C "$D" add leak-legacy2.py
git -C "$D" commit -qm t10legacy --no-verify >/dev/null 2>&1
git -C "$D" push -q origin HEAD:legacy-backup --no-verify >/dev/null 2>&1
git -C "$D" checkout -q main
git -C "$D" checkout -q -b feature2                            # 從 base 開新分支
gen_tg > "$D/leak-new.py"; git -C "$D" add leak-new.py
git -C "$D" commit -qm t10new --no-verify >/dev/null 2>&1      # 繞 pre-commit 製造新分支自身 leak
git -C "$D" push origin HEAD:feature2 >/dev/null 2>&1           # 新分支首次 push 應被擋
[ $? -ne 0 ] && ok "T10 new branch own leak blocked" || ng "T10 new branch own leak blocked"
rm -rf "$D" "$BARE"

echo ""
if [ "$FAIL_CT" -eq 0 ]; then
    echo "ALL PASS ($PASS_CT/10)"
    exit 0
else
    echo "FAILURE ($PASS_CT pass, $FAIL_CT fail)"
    exit 1
fi