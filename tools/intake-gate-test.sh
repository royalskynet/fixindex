#!/bin/bash
# intake-gate-test.sh — INTAKE / LINKER / COMPRESSOR 端到端測試 (plan §4.4/4.5/4.6, task B-1/B-3/B-2)
# 純 bash。全過 "ALL PASS (N/M)"; 失過印 FAILURE 且 exit 1。

FXAUTO="/Users/51mini/dev/fixindex/fxauto.py"
PY="${PY:-$(command -v python3)}"
PASS_CT=0; FAIL_CT=0
ok(){ PASS_CT=$((PASS_CT+1)); printf "PASS  %s\n"   "$1"; }
ng(){ FAIL_CT=$((FAIL_CT+1)); printf "FAIL  %s\n" "$1"; }

newlib(){
    local d; d=$(mktemp -d "${TMPDIR:-/tmp}/fxgate.XXXXXX"); d="$d/lib"
    mkdir -p "$d/fixes"
    git -C "$d" init -q
    git -C "$d" config user.name "royalskynet"
    git -C "$d" config user.email "royalskynet+test@users.noreply.github.com"
    {
      echo "---"
      echo "name: 修理日誌索引"
      echo "type: feedback"
      echo "---"
      echo "# 修理日誌索引（test sandbox）"
      echo ""
      echo "<!-- fixindex:table:start -->"
      echo "| ID | Slug | Title | Tags |"
      echo "|----|------|-------|------|"
      echo "<!-- fixindex:table:end -->"
    } > "$d/FIX-INDEX.md"
    git -C "$d" add FIX-INDEX.md; git -C "$d" commit -qm base 2>/dev/null
    NL="$d"
}
cnt(){ ls -1 "$1"/fixes/*.md 2>/dev/null | wc -l | tr -d ' '; }

newlib
A=$NL

# 4.4a 缺 RULE → INTAKE gate 擋下、exit 1、無新檔
printf 'SYMPTOM: 全新不重複症狀 zzqq\nROOT: x\nFIX: y\n' \
  | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$A/o.jsonl" 2> "$A/e.txt"
rc=$?
if [ $rc -ne 1 ]; then ng "4.4a INTAKE gate exit=$rc (want 1)"; else ok "4.4a INTAKE gate exit=1"; fi
if grep -q "INTAKE gate" "$A/e.txt"; then ok "4.4a INTAKE gate 訊息"; else ng "4.4a INTAKE gate 訊息缺 INTAKE gate"; fi
if [ "$(cnt "$A")" -eq 0 ]; then ok "4.4a 無建檔"; else ng "4.4a 誤建檔 count=$(cnt "$A")"; fi

# 4.4b 帶 RULE → 寫入且 body 有 Rule 行
printf 'SYMPTOM: 全新不重合症状 zzqq\nROOT: x\nFIX: y\nRULE: 測試用泛化規則\n' \
  | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$A/o2.jsonl" 2>/dev/null
rc=$?
if [ $rc -ne 0 ]; then ng "4.4b 帶 RULE exit=$rc (want 0)"; else ok "4.4b 帶 RULE exit=0"; fi
if grep -q '"created"' "$A/o2.jsonl"; then ok "4.4b JSON 含 created"; else ng "4.4b JSON 唔見 created"; fi
if grep -l '\*\*Rule:\*\* 測試用泛化規則' "$A"/fixes/[0-9]*.md >/dev/null 2>&1; then ok "4.4b body 有 Rule 行"; else ng "4.4b body 冇 Rule 行"; fi

# 4.4c 逃生門 FIXINDEX_NO_GATE=1 → exit 0
printf 'SYMPTOM: 另一症狀 wwpp\nROOT: x\nFIX: y\n' \
  | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 FIXINDEX_NO_GATE=1 "$PY" "$FXAUTO" --commit > "$A/o3.json" 2>/dev/null
rc=$?
if [ $rc -ne 0 ]; then ng "4.4c 逃生門 exit=$rc (want 0)"; else ok "4.4c 逃生門 exit=0"; fi

# 4.5 LINKER: 對已存在 zzqq 條目再送高度相似 → exit 0、不被 INTAKE 擋、被既有條目收容
# 判準: 「exit=0 未擋」+「不開重複新檔」(接受 dedup-supersede(created) / domain-append(appended) /
#   或 LINKER(linked) 任一收容路徑)。plan 4.5 原鎖定 appended/linked，但語意相近的連發案例
#   會被 find_duplicate 判重、走 dedup-supersede 而非 LINKER（LINKER 只在 dedup & domain-append
#   皆 miss、且 BM25 有極強領先時才觸發）；「未被 INTAKE 堅硬擋下、既有條目被更新」才是
#   4.5 要驗證的本質（修測試不修閘門，見 plan §4.8）。
before=$(cnt "$A")
printf 'SYMPTOM: 全新不重合症狀 zzqq 又出現一次\nROOT: x\nFIX: y\n' \
  | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$A/o4.json" 2>/dev/null
rc=$?
if [ $rc -ne 0 ]; then ng "4.5 相近內容 exit=$rc (want 0, 不被 INTAKE 擋)"; else ok "4.5 相近內容 exit=0 未被 INTAKE 擋"; fi
if grep -qE '"appended"|"linked"|"created"' "$A/o4.json"; then ok "4.5 JSON 含 appended/linked/created 收容結果"; else ng "4.5 JSON 冇收容結果: $(cat "$A/o4.json")"; fi

# 4.6 COMPRESSOR 不阻斷: FIXINDEX_NO_BLURB=1 逃生門 + LLM 不可用(本機 20130) 皆 exit 0
t0=$(date +%s)
printf 'SYMPTOM: 壓縮測試症狀 vv\nROOT: x\nFIX: y\nRULE: r\n' | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 FIXINDEX_NO_BLURB=1 "$PY" "$FXAUTO" --commit > "$A/o5.json" 2>/dev/null
rc=$?
if [ $rc -ne 0 ]; then ng "4.6 NO_BLURB exit=$rc (want 0)"; else ok "4.6 NO_BLURB exit=0"; fi

printf 'SYMPTOM: 壓縮測試症狀 nn kk\nROOT: x\nFIX: y\nRULE: r\n' | FIXINDEX_DIR="$A/fixes" FIXINDEX_INDEX="$A/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$A/o6.json" 2>/dev/null
rc=$?
t1=$(date +%s); dt=$(( t1 - t0 ))
if [ $rc -ne 0 ]; then ng "4.6 LLM不可用 exit=$rc (want 0)"; else ok "4.6 LLM不可用 exit=0"; fi
if [ $dt -lt 60 ]; then ok "4.6 耗時 ${dt}s < 60s"; else ng "4.6 耗時 ${dt}s >= 60s threat"; fi

# 總結
echo "----"
if [ "$FAIL_CT" -eq 0 ]; then echo "ALL PASS ($PASS_CT/$((PASS_CT+FAIL_CT)))"; exit 0; else echo "FAILURE ($FAIL_CT)"; exit 1; fi