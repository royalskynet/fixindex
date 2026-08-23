#!/bin/bash
# fxauto-mixed-test.sh — fxauto 混合輸入三態分流端到端測試 (§1e)
# 純 bash。全過 "ALL PASS (N/M)"; 失過印 FAILURE 且 exit 1。

FXAUTO="/Users/51mini/dev/fixindex/fxauto.py"
PY="${PY:-$(command -v python3)}"
PASS_CT=0; FAIL_CT=0
ok(){ PASS_CT=$((PASS_CT+1)); printf "PASS  %s\n"   "$1"; }
ng(){ FAIL_CT=$((FAIL_CT+1)); printf "FAIL  %s\n" "$1"; }

# 建立隔離 repo, 路徑存 global $NL
newlib(){
    local d; d=$(mktemp -d "${TMPDIR:-/tmp}/fxtest.XXXXXX"); d="$d/lib"
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
    NL="$d"
}
cnt(){ ls -1 "$1"/fixes/*.md 2>/dev/null | wc -l | tr -d ' '; }

MIXED="SYMPTOM: 混合管道 defect 欄位丟失
ROOT: main() 分支早退
FIX: 三態分流 + defer_commit
VERIFY: tools/fxauto-mixed-test.sh
詳情數據只屬 defect
INSIGHT: 遷徙結論
IMPLICATION: advisory 退化
QUERIES: 混合, 兩拆分
"

# ---------- A: shadow 混合 → 無寫出、雙 preview ----------
newlib
A=$NL
printf '%s' "$MIXED" | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_STRICT_DIR=1 "$PY" "$FXAUTO" --shadow > "$A/o.jsonl" 2>/dev/null
A1=1
[ "$(wc -l < "$A/o.jsonl" | tr -d ' ')" -eq 1 ] || A1=0
printf '%s' "$(tail -1 "$A/o.jsonl")" | "$PY" -c '
import sys,json
j=json.load(sys.stdin)
assert j.get("mixed") is True
assert j["defect"].get("preview_lines",0)>0
assert j["insight"].get("preview_lines",0)>0
assert "committed" not in j
' 2>/dev/null || A1=0
[ "$A1" -eq 1 ] && ok "A1 shadow mixed(兩preview, 無commit)" || ng "A1 shadow mixed [$(tail -1 "$A/o.jsonl")]"
[ "$(cnt "$A")" -eq 0 ] && ok "A2 shadow 不寫檔" || ng "A2 shadow 不寫檔"
rm -rf "$A"

# ---------- B commit 混拆 ----------
newlib
B=$NL
printf '%s' "$MIXED" | FIXINDEX_DIR="$B/fixes" FIXINDEX_INDEX="$B/FIX-INDEX.md" FIXINDEX_STRICT_DIR=1 "$PY" "$FXAUTO" --commit > "$B/o.jsonl" 2>/dev/null
printf '%s' "$(tail -1 "$B/o.jsonl")" | "$PY" -c '
import sys,json
j=json.load(sys.stdin)
assert j.get("mixed") is True
assert j.get("committed") and j.get("git_error") is None
assert j["defect"].get("created") and j["insight"].get("created")
' 2>/dev/null && ok "B1 commit mixed 雙 created 單 commit" || ng "B1 commit mixed [$(tail -1 "$B/o.jsonl")]"
[ "$(cnt "$B")" -eq 2 ] && ok "B2 fixes/ 恰 2 檔" || ng "B2 fixes/=2 (got $(cnt "$B"))"
nid=$(grep -c '^| 000[0-9] |' "$B/FIX-INDEX.md" 2>/dev/null); [ "$nid" -ge 2 ] && ok "B3 INDEX ≥2 id ($nid)" || ng "B3 INDEX ≥2 id (got $nid)"
IF=""
for f in "$B"/fixes/*.md; do grep -q '^type: insight' "$f" && IF="$f"; done
[ -n "$IF" ] && [ "$(grep -c '^  - 混合\|^  - 兩拆分' "$IF" 2>/dev/null)" -ge 1 ] && ok "B4 insight type+symptoms(QUERIES 拆分)" || ng "B4 insight type+symptoms"
if [ -n "$IF" ]; then
  dh=$(grep -rl '詳情數據只屬 defect' "$B"/fixes | grep -v "$IF" | wc -l | tr -d ' ')
  ih=$(grep -c '詳情數據只屬 defect' "$IF" 2>/dev/null)
  [ "$dh" -eq 1 ] && [ "$ih" -eq 0 ] && ok "B5 detail 僅屬 defect (dh=$dh ih=$ih)" || ng "B5 detail 僅屬 defect"
fi
n=$(git -C "$B" log --oneline | wc -l | tr -d ' '); [ "$n" -eq 2 ] && ok "B6 單 commit (git log=$n)" || ng "B6 單 commit (git log=$n)"
rm -rf "$B"

# ---------- C 回歸純 defect / 純 insight ----------
newlib
C=$NL
printf 'SYMPTOM: 純 defect ROOT\nROOT: r\nFIX: f\nVERIFY: v\n' | FIXINDEX_DIR="$C/fixes" FIXINDEX_INDEX="$C/FIX-INDEX.md" FIXINDEX_STRICT_DIR=1 "$PY" "$FXAUTO" --commit > "$C/o.jsonl" 2>/dev/null
hasm=$(grep -c '"mixed"' "$C/o.jsonl")
[ "$(cnt "$C")" -eq 1 ] && [ "$hasm" -eq 0 ] && ok "C 純 defect —— 1 檔、無 mixed 鍵" || ng "C 純 defect (cnt=$(cnt "$C") mixed=$hasm)"
rm -rf "$C"

newlib
C2=$NL
printf 'CONTEXT: c\nINSIGHT: i\nQUERIES: q\n' | FIXINDEX_DIR="$C2/fixes" FIXINDEX_INDEX="$C2/FIX-INDEX.md" FIXINDEX_STRICT_DIR=1 "$PY" "$FXAUTO" --commit > "$C2/o.jsonl" 2>/dev/null
hasm=$(printf '%s' "$(tail -1 "$C2/o.jsonl")" | grep -c 'mixed')
[ "$(cnt "$C2")" -eq 1 ] && [ "$hasm" -eq 0 ] && ok "C 純 insight —— 1 檔、無 mixed" || ng "C 純 insight (cnt=$(cnt "$C2") mixed=$hasm)"
rm -rf "$C2"

# ---------- D 邊界: 裸 `SYMPTOM: 空值` + INSIGHT → 純 insight 恰 1 檔 ----------
newlib
D=$NL
printf 'SYMPTOM:\nROOT: r\nCONTEXT: c\nINSIGHT: i\nQUERIES: q\n' | FIXINDEX_DIR="$D/fixes" FIXINDEX_INDEX="$D/FIX-INDEX.md" FIXINDEX_STRICT_DIR=1 "$PY" "$FXAUTO" --commit > "$D/o.jsonl" 2>/dev/null
printf '%s' "$(tail -1 "$D/o.jsonl")" | "$PY" -c '
import sys,json
j=json.load(sys.stdin)
assert j.get("created"), "created insight"
' 2>/dev/null
cntd=$(cnt "$D"); typ=$(grep -c '^type: insight' "$D"/fixes/*.md 2>/dev/null)
[ "$cntd" -eq 1 ] && [ "$typ" -eq 1 ] && ok "D 空 SYMPTOM + INSIGHT → 1 insight 檔" || ng "D 空 SYMPTOM (cnt=$cntd typ=$typ)"
rm -rf "$D"

echo ""
if [ "$FAIL_CT" -eq 0 ]; then echo "RESULT: ALL PASS ($PASS_CT fail-free)"; exit 0
else echo "RESULT: FAILURE ($PASS_CT pass, $FAIL_CT fail)"; exit 1; fi
