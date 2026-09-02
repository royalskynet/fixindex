#!/bin/bash
# intake-gate-test.sh — INTAKE / LINKER / COMPRESSOR 端到端測試 (plan §4.4/4.5/4.6, task B-1/B-3/B-2)
# 純 bash。全過 "ALL PASS (N/M)"; 失過印 FAILURE 且 exit 1。

FXAUTO="${FXAUTO:-$(cd "$(dirname "$0")/.." && pwd)/fxauto.py}"
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

# 4.5 LINKER: 專門構造走 LINKER 的案例 —— 新 title 的 token 全在既有條目 body 裡
#   (覆蓋率 1.0)，但與既有 title 幾乎不重疊、檔名 slug 也不匹配，因此 find_duplicate
#   與 find_domain_file_auto 雙 miss，只剩 LINKER 能收容。
#   斷言只接受 "linked" —— 不接受 created/appended，那是 LINKER 沒生效時的 fallback
#   輸出，混進允許集合會讓斷言恆真 (見 fixindex 0590)。
newlib; B=$NL
printf 'SYMPTOM: alphaqq betaqq 服務啟動失敗\nROOT: gammaqq deltaqq epsilonqq 設定錯誤\nFIX: 改回預設值\nRULE: 測試用泛化規則\n' \
  | FIXINDEX_DIR="$B/fixes" FIXINDEX_INDEX="$B/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$B/seed.json" 2>/dev/null
printf 'SYMPTOM: gammaqq deltaqq epsilonqq\nROOT: x\nFIX: y\n' \
  | FIXINDEX_DIR="$B/fixes" FIXINDEX_INDEX="$B/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$B/o4.json" 2>/dev/null
rc=$?
if [ $rc -ne 0 ]; then ng "4.5 LINKER exit=$rc (want 0, 不被 INTAKE 擋)"; else ok "4.5 LINKER exit=0 未被 INTAKE 擋"; fi
if grep -q '"linked"' "$B/o4.json"; then ok "4.5 JSON 含 linked (LINKER 實際生效)"; else ng "4.5 JSON 無 linked: $(cat "$B/o4.json")"; fi
if [ "$(cnt "$B")" -eq 1 ]; then ok "4.5 未開新檔 (count=1)"; else ng "4.5 開了新檔 count=$(cnt "$B")"; fi
if grep -q '## §2' "$B"/fixes/[0-9]*.md 2>/dev/null; then ok "4.5 既有條目長出 §2"; else ng "4.5 既有條目冇 §2"; fi

# 4.5x 反向自檢: 把門檻拉到不可能達到 (9.9) → 同一輸入必須改走建新檔。
#   這條在證明上面的斷言不是恆真 —— 關掉被測功能它會轉紅 (fixindex 0590 的 VERIFY)。
newlib; C=$NL
printf 'SYMPTOM: alphaqq betaqq 服務啟動失敗\nROOT: gammaqq deltaqq epsilonqq 設定錯誤\nFIX: 改回預設值\nRULE: 測試用泛化規則\n' \
  | FIXINDEX_DIR="$C/fixes" FIXINDEX_INDEX="$C/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 "$PY" "$FXAUTO" --commit > "$C/seed.json" 2>/dev/null
printf 'SYMPTOM: gammaqq deltaqq epsilonqq\nROOT: x\nFIX: y\nRULE: r\n' \
  | FIXINDEX_DIR="$C/fixes" FIXINDEX_INDEX="$C/FIX-INDEX.md" FIXINDEX_NO_SYNC=1 FIXINDEX_LINK_COVERAGE=9.9 "$PY" "$FXAUTO" --commit > "$C/o4x.json" 2>/dev/null
if grep -q '"linked"' "$C/o4x.json"; then ng "4.5x 門檻 9.9 仍 linked → 4.5 斷言恆真"; else ok "4.5x 門檻 9.9 不再 linked (斷言非恆真)"; fi

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