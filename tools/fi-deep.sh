#!/usr/bin/env bash
# fi-deep — /fi 的 deep 派工準備：抽 transcript → 遮罩 → Presidio scrub → 切塊 → 產 deep 工單 → deep-lint。
# 用法：fi-deep [session.jsonl]（省略＝cwd 對應專案目錄裡最新的 jsonl）
# 成功時最後一行印「deep-run <工單> <cwd>」，主 session 照抄裸名呼叫（deep-run 不能從腳本內呼叫，會掉回沙箱）。
# 退出碼：0 工單已產且 lint 無 FAIL｜2 找不到 transcript｜3 PII scrub 失敗（fail-closed，不留任何產物）｜4 deep-lint FAIL
set -eu

J="${1:-}"
if [ -z "$J" ]; then
  slug="$(pwd | sed 's#[/.]#-#g')"
  J="$(ls -t "$HOME/.claude/projects/$slug"/*.jsonl 2>/dev/null | head -1 || true)"
fi
[ -n "$J" ] && [ -s "$J" ] || { echo "fi-deep: 找不到 transcript：${J:-（空）}" >&2; exit 2; }

MASK="${FI_MASK:-$HOME/.claude/tools/fi-mask-transcript.mjs}"
SCRUB="${FI_SCRUB_URL:-http://127.0.0.1:4102}"
TASKS="${FI_TASK_DIR:-$HOME/.deepclaude/work/tasks}"
LINT="${FI_DEEP_LINT:-deep-lint}"
CHUNK="${FI_CHUNK_BYTES:-140000}"
ALLOWF="${FI_SCRUB_ALLOW:-$(cd "$(dirname "$0")" && pwd)/fi-scrub-allow.txt}"
STORE="${FIXINDEX_DIR:-$HOME/dev/fix-store/fixes}"
DUPCHK="${FI_DUP_CHECK:-$(cd "$(dirname "$0")" && pwd)/fi-dup-check.py}"
DEEP_CWD="$(dirname "$STORE")"

sid="$(basename "$J" .jsonl)"
sid8="$(printf '%s' "$sid" | cut -c1-8)"
W="$(mktemp -d "${TMPDIR:-/tmp}/fi-deep-$sid8.XXXXXX")"
ok=0
# 未脫敏的中間檔一律不留；失敗時整個工作目錄清掉
trap 'rm -f "$W/raw.txt" "$W/masked.txt"; [ "$ok" = 1 ] || rm -rf "$W"' EXIT

jq -r 'select(.type=="user" or .type=="assistant") | .message.content |
  if type=="array" then (map(
    if .type=="text" then .text
    elif .type=="tool_use" then "TOOL "+.name+" "+((.input|tostring)[0:300])
    elif .type=="tool_result" then "RESULT "+((.content|tostring)[0:600])
    else empty end)|join("\n")) else tostring end' "$J" > "$W/raw.txt"
node "$MASK" "$W/raw.txt" "$W/masked.txt" >/dev/null
rm -f "$W/raw.txt"

# Presidio scrub（錢包、交易雜湊、姓名、電話、卡號…）；回應的 mapping 含原值，只取 texts、不落檔
python3 - "$W/masked.txt" "$W" "$SCRUB" "$CHUNK" "$ALLOWF" <<'PY' || { echo "fi-deep: PII scrub 失敗（${SCRUB}），fail-closed 不產工單" >&2; exit 3; }
import json, os, re, sys, urllib.request
src, outdir, url, chunk, allow_path = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]

# Presidio 在中英混雜的技術逐字稿會把識別字、路徑、中文片語標成 PERSON／LOCATION／URL。
# 只還原這三類裡「看起來是技術詞」的值；錢包、雜湊、卡號、電話、email、IP、身分證等一律不還原。
PH = re.compile(r"<([A-Z][A-Z_]*?)_(\d+)>")
SOFT = {"PERSON", "LOCATION", "URL"}
ALLOW = set()
if os.path.exists(allow_path):
    ALLOW = {ln.strip().lower() for ln in open(allow_path, encoding="utf-8") if ln.strip() and not ln.startswith("#")}
CJK = re.compile(r"[㐀-鿿]")
def technical(kind, v):
    if v.lower() in ALLOW:
        return True
    if kind == "URL":
        return "@" not in v and "?" not in v
    if CJK.search(v):
        return len(v) >= 5                      # 人名多為 2–4 字
    if re.search(r"[_./\\\-0-9:$`<>=]", v):
        return True                             # 識別字、路徑、旗標
    if v.islower() or v.isupper():
        return True                             # 全小寫指令名、全大寫常數
    if " " not in v.strip() and re.search(r"[a-z][A-Z]", v):
        return True                             # 內部帶大寫的 CamelCase（DeepSeek）
    return False                                # 「Alice」「John Smith」這類首字大寫：維持遮罩
def restore(m, mp):
    ph = m.group(0)
    v = mp.get(ph)
    return v if v is not None and m.group(1) in SOFT and technical(m.group(1), v) else ph
lines = open(src, encoding="utf-8").read().splitlines(keepends=True)
blocks, cur = [], ""
for ln in lines:
    if cur and len(cur) + len(ln) > 6000:
        blocks.append(cur); cur = ""
    cur += ln
if cur:
    blocks.append(cur)
out = []
for i in range(0, len(blocks), 20):
    batch = blocks[i:i + 20]
    req = urllib.request.Request(url + "/scrub", data=json.dumps({"texts": batch}).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    got, mp = d["texts"], d.get("mapping") or {}
    if len(got) != len(batch):
        raise SystemExit("scrub 回傳筆數不符")
    # 誤遮還原：mapping 只在本機用。佔位符編號每次請求重算，所以逐批還原
    got = [PH.sub(lambda m: restore(m, mp), t) for t in got]
    out.extend(got)
# 依行切塊，避免 UTF-8 字元被切斷
n, buf = 0, b""
for text in out:
    for ln in text.splitlines(keepends=True):
        b = ln.encode("utf-8")
        if buf and len(buf) + len(b) > chunk:
            n += 1; open(f"{outdir}/part.{n:02d}.txt", "wb").write(buf); buf = b""
        buf += b
if buf:
    n += 1; open(f"{outdir}/part.{n:02d}.txt", "wb").write(buf)
PY
rm -f "$W/masked.txt"

R="$W/report.md"
mkdir -p "$TASKS"
TASK="$TASKS/$(date +%Y-%m-%d)-fi-$sid8.md"
{
  printf '# /fi：掃 session %s，記入 fixindex\n\n' "$sid8"
  printf '## 任務\n\n'
  printf '逐塊、逐段讀完下列已脫敏的 session 精簡逐字稿（不抽樣）：\n\n'
  for p in "$W"/part.*.txt; do printf -- '- `%s`\n' "$p"; done
  cat <<EOF

1. **窮舉候選**：每段改動、每條報錯、每個重新摸索才搞懂的點，含糾正誤解。出過錯、查到根因、改了做法的點至少列進候選。
2. **批次查重（一次查完，不要一條一條跑）**：把每個候選的核心關鍵字一行一個寫進 \`$W/queries.txt\`，
   然後只跑這兩條：\`fixindex find --queries-file $W/queries.txt --limit 5 --spill\` 與
   \`fixindex insights --queries-file $W/queries.txt --limit 5 --spill\`。
   模型與索引只載一次；逐條跑會讓這一步從 1 回合變成 N 回合。
3. **收斂（含同輪去重）**：濾掉一次性、只對單一專案有意義、無重現價值的；只留「下次 \`fixindex find\` 找得到才有意義」的。已存在且等效的不重記。
   **寫入前把全部候選攤在一起兩兩比一次**：同一個根因、同一條規則的候選合併成一條，不要同主題寫兩三條。
   查重只看得到庫裡既有的條目，看不到你這一輪剛寫的，所以同輪重複只能在這一步擋掉。
4. **寫入**：每條通過的用 \`printf '…' | fixindex fi\`（不帶任何參數）寫入。欄位值寫可搜尋關鍵字：
   - symptom：\`SYMPTOM:\` \`ROOT:\` \`FIX:\` \`VERIFY:\` \`RULE:\`（RULE 必填，寫拿掉專案名後仍成立的可泛化規則）
   - insight：\`CONTEXT:\` \`INSIGHT:\` \`IMPLICATION:\` \`QUERIES:\` \`RULE:\`
   - fixindex fi 回 INTAKE gate 時照它的提示補 RULE 再寫；回 JSON 的 \`created\`／\`appended\` 路徑記下編號。
   - **SYMPTOM／CONTEXT 必須含一段逐字引用**：從 part 檔複製同一行內連續 ≥12 字的原文（報錯原文、指令輸出或使用者原話），用「原文：」標出；寫進條目的引用一字不改。part 檔找不到能佐證的原文，這個候選就略過，不憑印象補寫症狀。
5. **報告**：寫 \`$R\`，格式固定（每個編號下一行是兩個空格開頭的「原文：」，內容與條目裡的引用相同）：

\`\`\`
## 新增
- <編號> <≤80 字核心>
  原文：<從 part 檔逐字複製的同一段引用>
## 補充既有
- <編號> <≤80 字核心>
  原文：<從 part 檔逐字複製的同一段引用>
## 略過
- <≤80 字核心> — <已存在 NNNN｜無重現價值｜一次性>
## status
<fixindex status --json --assert-clean 的原始輸出>
\`\`\`

沒有可記的就在「## 新增」下寫「- 無」，其餘段照列。

## 不動

- \`$STORE\` 裡的既有條目檔不手改，一律經 \`fixindex fi\`。
- 只讀上列 part 檔；其他 transcript、\`~/.claude/projects/**/*.jsonl\` 不讀。

## 禁止

- 不還原 \`<MASKED_*>\` 與 \`<PERSON_1>\` 這類佔位符，不猜原值寫進條目。
- 不給 \`fixindex fi\`／\`fixindex new\` 帶參數（參數會被當 slug 建垃圾檔）。
- 不用 \`set -x\`，不印憑證值。
- \`launchctl bootout/bootstrap/kickstart\` 必帶完整 service target \`gui/\$(id -u)/<label>\`；裸 domain 與 \`launchctl reboot\` 禁止。本任務用不到 launchctl。
- 無頭機：禁止回報「請使用者手動貼 token／授權／執行指令」；fixindex push 失敗就停手回報阻斷點。

## 驗收

預期：報告存在且四段齊全；報告列出的每個編號都查得到條目；每個編號都有「原文：」引用，且引用同時出現在 part 檔與該條目；本輪新增的條目彼此沒有同主題重複；fixindex 狀態乾淨。

\`\`\`bash
set -eu
R='$R'
W='$W'
test -s "\$R"
for h in '## 新增' '## 補充既有' '## 略過' '## status'; do grep -qxF "\$h" "\$R"; done
ids="\$(awk '/^## (新增|補充既有)\$/{f=1;next} /^## /{f=0} f && /^- [0-9]+ /{print \$2}' "\$R")"
for id in \$ids; do fixindex show "\$id" >/dev/null; done
awk '/^## (新增|補充既有)\$/{f=1;next} /^## /{f=0} f && /^- [0-9]+ /{id=\$2; n[id]=0} f && /^  原文：/{q=\$0; sub(/^  原文：/,"",q); print id "\t" q; n[id]++} END{for(i in n) if(!n[i]) print "MISSING\t" i}' "\$R" > "\$W/quotes.tsv"
if grep '^MISSING' "\$W/quotes.tsv"; then echo "缺原文引用" >&2; exit 1; fi
while IFS="\$(printf '\t')" read -r id q; do
  [ "\$(printf '%s' "\$q" | LC_ALL=en_US.UTF-8 wc -m | tr -d ' ')" -ge 12 ] || { echo "引用太短：\$id" >&2; exit 1; }
  cat "\$W"/part.*.txt | grep -qF -- "\$q" || { echo "引用不在逐字稿：\$id" >&2; exit 1; }
  fixindex show "\$id" | grep -qF -- "\$q" || { echo "引用不在條目：\$id" >&2; exit 1; }
done < "\$W/quotes.tsv"
echo "ids=\$(printf '%s ' \$ids)"
newids="\$(awk '/^## 新增\$/{f=1;next} /^## /{f=0} f && /^- [0-9]+ /{print \$2}' "\$R")"
[ -z "\$newids" ] || python3 '$DUPCHK' \$newids
fixindex status --json --assert-clean
\`\`\`
EOF
} > "$TASK"

if "$LINT" "$TASK" 2>&1 | grep -q 'LINT FAIL'; then
  "$LINT" "$TASK" >&2 || true
  echo "fi-deep: deep-lint FAIL：$TASK" >&2
  exit 4
fi
ok=1
echo "report: $R"
echo "deep-run $TASK $DEEP_CWD"
