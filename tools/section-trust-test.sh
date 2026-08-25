#!/bin/bash
# section-trust-test.sh — §4/§5/§6 section-level trust 端到端測試
# 自包含：全部在 mktemp sandbox repo 執行；絕不碰私人 runbook（受保護 remote 拒寫）。
# 10 cases（workorder §7）。
# 全過印 ALL PASS; 任一失敗印 FAILURE 且 exit 1。
# 用法: bash tools/section-trust-test.sh

REPO="/Users/51mini/dev/fixindex"
PY="/usr/bin/python3"
FIXMETA="$REPO/fxmeta.py"
FXSEARCH="$REPO/fxsearch.py"
FXAUTO="$REPO/fxauto.py"
FIXINDEX_BIN="$REPO/fixindex"

PASS_CT=0; FAIL_CT=0
ok() { PASS_CT=$((PASS_CT+1)); printf "PASS  %s\n" "$1"; }
ng() { FAIL_CT=$((FAIL_CT+1)); printf "FAIL  %s\n" "$1"; }

# --- sandbox repo helper ---
newlib() {
    local d; d=$(mktemp -d "${TMPDIR:-/tmp}/sctrust.XXXXXX")
    mkdir -p "$d/fixes"
    git -C "$d" init -q
    git -C "$d" config user.name "royalskynet"
    git -C "$d" config user.email "royalskynet+test@users.noreply.github.com"
    echo ok > "$d/base.txt"; git -C "$d" add base.txt; git -C "$d" commit -qm base
    : > "$d/FIX-INDEX.md"
    {
      echo "---"
      echo "name: 修理日誌入口"
      echo "type: feedback"
      echo "---"
      echo "# 修理日誌索引（test sandbox）"
      echo ""
      echo "<!-- fixindex:table:start -->"
      echo "| ID | Slug | Title | Tags |"
      echo "|----|------|-------|------|"
      echo "<!-- fixindex:table:end -->"
    } > "$d/FIX-INDEX.md"
    printf '%s' "$d"
}
# legacy fixture (id 0553, two sections, no trust fields)
write_legacy() {
    local d="$1"
    cat > "$d/fixes/0553-foo.md" <<'EOF'
---
id: "0553"
slug: foo
title: Legacy domain
tags: [test]
symptoms:
  - symptom alpha
status: active
supersedes: []
related: []
---
# 0553 foo

## §1 First issue
**Symptom:** first break
**Root cause:** r1
**Fix:** f1
**Verify:** v1

## §2 Second issue
**Symptom:** second break
**Root cause:** r2
**Fix:** f2
**Verify:** v2
EOF
}
# run fxmeta with sandbox env (STRICT+TEST → protected remote 拒寫)
mx() { FIXINDEX_STRICT_DIR=1 FIXINDEX_TEST=1 FIXINDEX_DIR="$SD/fixes" "$PY" "$FIXMETA" "$@"; }
sx() { FIXINDEX_STRICT_DIR=1 FIXINDEX_TEST=1 FIXINDEX_DIR="$SD/fixes" FIXINDEX_INDEX="$SD/FIX-INDEX.md" "$PY" "$FXSEARCH" "$@"; }
ax() { FIXINDEX_STRICT_DIR=1 FIXINDEX_TEST=1 FIXINDEX_DIR="$SD/fixes" FIXINDEX_INDEX="$SD/FIX-INDEX.md" "$PY" "$FXAUTO" "$@"; }

# ---------- C1: legacy 無 metadata → find [U]，原檔 hash 不變 ----------
SD=$(newlib); write_legacy "$SD"
H0=$(shasum "$SD/fixes/0553-foo.md" | awk '{print $1}')
OUT=$(sx "first break" --limit 3 2>/dev/null)
echo "$OUT" | grep -q '\[U\]' && ok "C1 legacy badge [U]" || ng "C1 legacy badge [U]: $OUT"
H1=$(shasum "$SD/fixes/0553-foo.md" | awk '{print $1}')
[ "$H0" = "$H1" ] && ok "C1 legacy hash unchanged" || ng "C1 legacy hash changed!!"
rm -rf "$SD"

# ---------- C2: mark verified 缺 evidence/date 拒絕；合法輸入 read-back 相同 ----------
SD=$(newlib); write_legacy "$SD"
OUT=$(mx mark "$SD/fixes/0553-foo.md" "0553#1" verified 2>&1); RC=$?
[ $RC -ne 0 ] && echo "$OUT" | grep -q "verified requires" && ok "C2 verified no-evidence rejected" || ng "C2 verified no-evidence rejected ($RC $OUT)"
OUT=$(mx mark "$SD/fixes/0553-foo.md" "0553#1" verified --evidence "pytest ok" 2>&1); RC=$?
[ $RC -ne 0 ] && echo "$OUT" | grep -q "requires valid ISO" && ok "C2 verified no-date rejected" || ng "C2 verified no-date rejected ($RC $OUT)"
OUT=$(mx mark "$SD/fixes/0553-foo.md" "0553#1" verified --evidence "pytest ok" --date "2026-08-24" 2>&1); RC=$?
[ $RC -eq 0 ] && echo "$OUT" | grep -q '"ok": true' && ok "C2 verified accepted" || ng "C2 verified accepted ($RC $OUT)"
grep -q '\*\*State:\*\* verified' "$SD/fixes/0553-foo.md" && ok "C2 state written" || ng "C2 state written"
grep -q '\*\*Evidence:\*\* pytest ok' "$SD/fixes/0553-foo.md" && ok "C2 evidence written" || ng "C2 evidence written"
grep -q '^## §2' "$SD/fixes/0553-foo.md" && ok "C2 section2 intact" || ng "C2 section2 intact"
rm -rf "$SD"

# ---------- C3: mark #2 不得改 #1 或 frontmatter ----------
SD=$(newlib); write_legacy "$SD"
FM0=$(sed -n '1,/^---$/p' "$SD/fixes/0553-foo.md" | shasum | awk '{print $1}')
mx mark "$SD/fixes/0553-foo.md" "0553#2" stale --reason "env changed" >/dev/null 2>&1
FM1=$(sed -n '1,/^---$/p' "$SD/fixes/0553-foo.md" | shasum | awk '{print $1}')
[ "$FM0" = "$FM1" ] && ok "C3 frontmatter unchanged" || ng "C3 frontmatter changed"
# §1 仍無 State，§2 有 stale
S1=$(awk '/^## §1/{f=1} /^## §2/{f=0} f' "$SD/fixes/0553-foo.md")
S2=$(awk '/^## §2/{f=1} /^## §3/{f=0} f' "$SD/fixes/0553-foo.md" 2>/dev/null; awk '/^## §2/{f=1} f' "$SD/fixes/0553-foo.md")
echo "$S1" | grep -q '\*\*State:\*\*' && ng "C3 §1 got State" || ok "C3 §1 no State"
echo "$S2" | grep -q '\*\*State:\*\* stale' && ok "C3 §2 stale" || ng "C3 §2 stale: $S2"
rm -rf "$SD"

# ---------- C4: outcome 三類正確累加；非法類型拒絕 ----------
SD=$(newlib); write_legacy "$SD"
mx outcome "$SD/fixes/0553-foo.md" "0553#1" helpful >/dev/null 2>&1
mx outcome "$SD/fixes/0553-foo.md" "0553#1" helpful >/dev/null 2>&1
mx outcome "$SD/fixes/0553-foo.md" "0553#1" failed >/dev/null 2>&1
OCT=$(grep -o '\*\*Outcome:\*\* .*' "$SD/fixes/0553-foo.md")
echo "$OCT" | grep -q 'helpful=2' && echo "$OCT" | grep -q 'failed=1' && echo "$OCT" | grep -q 'irrelevant=0' && ok "C4 outcome sums ($OCT)" || ng "C4 outcome sums: $OCT"
OUT=$(mx outcome "$SD/fixes/0553-foo.md" "0553#1" bogus 2>&1); RC=$?
[ $RC -ne 0 ] && ok "C4 invalid outcome rejected" || ng "C4 invalid outcome rejected"
rm -rf "$SD"

# ---------- C5: audit --json schema 固定，exit 0/1/2 有斷言 ----------
SD=$(newlib); write_legacy "$SD"
# clean fixture: mark verified valid
mx mark "$SD/fixes/0553-foo.md" "0553#1" verified --evidence "ok" --date "2026-08-24" >/dev/null 2>&1
mx audit "$SD/fixes/0553-foo.md" --json > "$SD/audit0.json" 2>&1; RC=$?
[ $RC -eq 0 ] && grep -q '"issues": \[\]' "$SD/audit0.json" && ok "C5 audit clean (0, issues:[])" || ng "C5 audit clean ($RC $(cat "$SD/audit0.json"))"
# quality problem: verified missing evidence
printf '%s\n' '---' 'id: "0553"' 'slug: foo' 'title: Broken' 'symptoms: []' 'status: active' '---' '' '# 0553 foo' '' '## §1 Bad' '**State:** verified' '**Symptom:** x' > "$SD/fixes/0553-foo.md"
mx audit "$SD/fixes/0553-foo.md" --json > "$SD/audit1.json" 2>&1; RC=$?
[ $RC -eq 1 ] && grep -q 'verified but empty Evidence' "$SD/audit1.json" && ok "C5 audit quality problem (rc1)" || ng "C5 audit quality problem ($RC $(cat "$SD/audit1.json"))"
# usage error: no sections
printf '%s\n' '---' 'id: "0553"' 'title: Empty' '---' '' '# 0553' > "$SD/fixes/0554-empty.md"
mx audit "$SD/fixes/0554-empty.md" --json >/dev/null 2>&1; RC=$?
[ $RC -eq 2 ] && ok "C5 audit usage error (rc2)" || ng "C5 audit usage error ($RC)"
rm -rf "$SD"

# ---------- C6: find --json 原欄位不減、排序與 baseline 相同，只新增 trust ----------
SD=$(newlib); write_legacy "$SD"
B0=$(sx "first break" --json 2>/dev/null)
# mark #1 verified
mx mark "$SD/fixes/0553-foo.md" "0553#1" verified --evidence "ok" --date "2026-08-24" >/dev/null 2>&1
B1=$(sx "first break" --json 2>/dev/null)
# 新欄位存在
echo "$B1" | grep -q '"trust_state": "verified"' && ok "C6 json has trust_state" || ng "C6 json trust_state: $B1"
echo "$B1" | grep -q '"last_verified": "2026-08-24"' && ok "C6 json has last_verified" || ng "C6 json last_verified"
echo "$B1" | grep -q '"outcome"' && ok "C6 json has outcome" || ng "C6 json outcome"
# 原欄位仍在 & 排序相同（key 順序：0553#1 前）
K0=$(echo "$B0" | /usr/bin/python3 -c 'import sys,json;print([h["key"] for h in json.load(sys.stdin)["hits"]])')
K1=$(echo "$B1" | /usr/bin/python3 -c 'import sys,json;print([h["key"] for h in json.load(sys.stdin)["hits"]])')
[ "$K0" = "$K1" ] && ok "C6 hit keys/order unchanged ($K0)" || ng "C6 hit keys changed ($K0 vs $K1)"
rm -rf "$SD"

# ---------- C7: insights 與 defects 不串型，badge 正確 ----------
SD=$(newlib); write_legacy "$SD"
cat > "$SD/fixes/0554-ins.md" <<'EOF'
---
id: "0554"
slug: ins
type: insight
title: Insight domain
symptoms: [query]
status: active
---
# 0554 ins

## §1 Context
**Context:** c
**State:** stale
**Evidence:** why
EOF
OUT=$(sx "query" --type insight --limit 3 2>/dev/null)
echo "$OUT" | grep -q '\[S\]' && ok "C7 insight badge stale [S]" || ng "C7 insight badge [S]: $OUT"
OUT=$(sx "first break" --type defect --limit 3 2>/dev/null)
echo "$OUT" | grep -q '\[U\]' && echo "$OUT" | grep -q '0553#1' && ok "C7 defect badge [U]" || ng "C7 defect badge [U]: $OUT"
# 不串型：insight query 不含 defect
OUT=$(sx "query" --type defect --limit 3 2>/dev/null)
echo "$OUT" | grep -q '0554' && ng "C7 insight leaks into defect" || ok "C7 no type leak"
rm -rf "$SD"

# ---------- C8: malformed/重複 section、CRLF、symlink escape 均 fail-safe ----------
SD=$(newlib); write_legacy "$SD"
# duplicate section number
printf '%s\n' '---' 'id: "0555"' 'title: Dup' '---' '' '# 0555' '' '## §1 A' '**State:** verified' '**Evidence:** e' '**Last verified:** 2026-08-24' '## §1 B' '**Symptom:** dup' > "$SD/fixes/0555-dup.md"
mx audit "$SD/fixes/0555-dup.md" --json >/dev/null 2>&1; RC=$?
[ $RC -eq 1 ] && grep -q 'duplicate_section_numbers' <(mx audit "$SD/fixes/0555-dup.md" --json 2>/dev/null) && ok "C8 duplicate section detected" || ng "C8 duplicate section ($RC)"
# bad date
printf '%s\n' '---' 'id: "0556"' 'title: BadDate' '---' '' '# 0556' '' '## §1 B' '**State:** verified' '**Evidence:** e' '**Last verified:** 2026-31-99' > "$SD/fixes/0556-baddate.md"
RC=$(mx audit "$SD/fixes/0556-baddate.md" --json >/dev/null 2>&1; echo $?)
[ $RC -eq 1 ] && ok "C8 bad date flagged" || ng "C8 bad date ($RC)"
# symlink escape: mark 不追 symlink 外（resolve 前檔案本身不是目錄）
ln -s /etc/hosts "$SD/fixes/9999-link.md" 2>/dev/null
RC=$(mx audit "$SD/fixes/9999-link.md" --json >/dev/null 2>&1; echo $?)
[ $RC -ge 1 ] && ok "C8 symlink fail-safe (rc=$RC)" || ng "C8 symlink fail-safe (rc=$RC)"
rm -rf "$SD"

# ---------- C9: repeat 第2次不提示、第3次恰一提示；failed outcome 達2恰一提示 ----------
SD=$(newlib)
BASE="$SD/fixes/0888-http-500.md"
cat > "$BASE" <<'EOF'
---
id: "0888"
slug: http-500
title: Network issue log
symptoms: []
status: active
---
# 0888 http-500

## §1 HTTP 500 on login
**Symptom:** login 500
**Verify:** v

## §2 HTTP 500 on logout
**Symptom:** logout 500
**Verify:** v
EOF
# append 第2筆類似（檔內變 3 個相似 heading）→ 恰一提示
OUT=$(printf 'SYMPTOM: HTTP 500 on signup\nFIX: f\nVERIFY: v\n' | FIXINDEX_STRICT_DIR=1 FIXINDEX_TEST=1 FIXINDEX_DIR="$SD/fixes" FIXINDEX_INDEX="$SD/FIX-INDEX.md" "$PY" "$FXAUTO" --commit 2>&1)
N=$(echo "$OUT" | grep -c 'FIXINDEX_REPEAT_EVAL')
[ "$N" -eq 1 ] && ok "C9 3rd similar exactly one hint ($OUT)" || ng "C9 3rd similar exactly one hint (n=$N $OUT)"
rm -rf "$SD"

# ---------- C10: 測試 remote 命中受保護名單拒寫，公開 repo 與私人 runbook 均無變更 ----------
# 公開 repo 工作樹在測試前已有開發中的未 commit 改動（本 branch）；測試不得新增 dirty 檔。
GIT_BEFORE=$(git -C "$REPO" status --porcelain | sort)
SD=$(newlib)
# 把 sandbox remote 指向受保護名單（royalskynet/fixindex-log）
git -C "$SD" remote add origin "https://github.com/royalskynet/fixindex-log.git"
write_legacy "$SD"
# fxsync push 在測試模式遇受保護 remote 應拒寫
OUT=$(FIXINDEX_STRICT_DIR=1 FIXINDEX_TEST=1 FIXINDEX_DIR="$SD/fixes" "$PY" "$REPO/fxsync.py" push --path "$SD/fixes/0553-foo.md" 2>&1)
echo "$OUT" | grep -qi '測試模式禁止寫入\|protected' && ok "C10 protected remote blocked" || ng "C10 protected remote blocked: $OUT"
GIT_AFTER=$(git -C "$REPO" status --porcelain | sort)
[ "$GIT_BEFORE" = "$GIT_AFTER" ] && ok "C10 public repo unchanged" || ng "C10 public repo changed: diff=$GIT_BEFORE|$GIT_AFTER"
rm -rf "$SD"

echo ""
if [ "$FAIL_CT" -eq 0 ]; then echo "ALL PASS ($PASS_CT checks, 0 fail)"; exit 0
else echo "FAILURE ($PASS_CT pass, $FAIL_CT fail)"; exit 1; fi