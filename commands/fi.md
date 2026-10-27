---
description: 掃描當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後草擬補記
---

掃描本 session 從開始到現在的全部內容與產出，只挖**值得永久記入 fixindex** 的經驗，不逐句回報。

## 兩類條目

1. **insight** — 已固化的設計洞見／架構決策／跨案模式：改方式比記解法有價值、別的專案也用得到。
2. **symptom**（一般 defect 條目）— 症狀→根因→解法→驗證：會重複撞到、下次 `fixindex find "<關鍵字>"` 找得到。

## 程序

步驟 0–2 是機械活，派 sonnet 子代理；步驟 3 起的判斷留主 session。

0. **抽出脫敏的精簡 transcript**（不可省：原始 jsonl 會超過子代理 window）：

   ```bash
   T=$(ls -t ~/.claude/projects/"$(pwd | sed 's#[/.]#-#g')"/*.jsonl | head -1)
   OUT="${TMPDIR:-/tmp}/fi-scan-$$.txt"
   jq -r 'select(.type=="user" or .type=="assistant") | .message.content |
     if type=="array" then (map(
       if .type=="text" then .text
       elif .type=="tool_use" then "TOOL "+.name+" "+((.input|tostring)[0:300])
       elif .type=="tool_result" then "RESULT "+((.content|tostring)[0:600])
       else empty end)|join("\n")) else tostring end' "$T" > "$OUT"
   node ~/.claude/tools/fi-mask-transcript.mjs "$OUT" "$OUT.masked"   # 不可省
   wc -c "$OUT.masked"
   ```

   最新 mtime 的 jsonl 就是本 session；同 cwd 有並行 session 時改用 scratchpad 目錄名（＝session id）。
   - **只把 `$OUT.masked` 給子代理**，不給 `$OUT` 或原始 jsonl；未脫敏版有 key 樣字串、email、IP，會被 sensitive-canary 擋（通常是真陽性）。
   - 不改 canary 規則、不要 allow 標籤、不繞過 guard。
   - 脫敏後確認一次：餵 canary hook `{"tool_name":"Read","tool_input":{"file_path":"<masked>"}}` 應 rc=0。路徑別寫在 Bash 指令列（canary 會展開路徑先擋你），寫成小 node runner 在腳本內組路徑。

1-2. **背景派一次 `Agent`**（`subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`；單塊要跑數分鐘，前景派使用者會以為卡死）。prompt 自含以下全部（子代理看不到本對話）：

   - `$OUT.masked` 的絕對路徑，**逐條掃過**，不抽樣；不要還原 `<MASKED_*>`、不要讀未脫敏原檔。
   - **窮舉候選**：每段改動、每條報錯、每個重新摸索才搞懂的點，含「糾正誤解」。**反事實閘門**：出過錯、查到根因、改了做法的點至少列進候選。寧可多列，值不值得記不歸它判。
   - **逐條去重**：每個候選跑 `fixindex find "<核心關鍵字>"` 與 `fixindex insights "<主題>"`，原始輸出附在該候選下。
   - 回報格式：「候選核心 ≤80 字／建議類型 insight|symptom／查重指令與原始輸出／已存在 or 新」。**只回報，不寫入 fixindex。**

   `$OUT.masked` >150 KB → 切塊，**同一個 response 內一次派完全部塊**，各自回報，主 session 合併。
   子代理仍被 canary 擋 → 它停手回報阻斷點；主 session 先補 `fi-mask-transcript.mjs` 遮罩規則再重派，補不動才用自己 context 內的記憶直接掃。

3. **收斂**（主 session）：濾掉一次性、專案私有、無重現價值的，只留「下次找得到才有意義」的。子代理標「已存在」的，核對查重輸出是否真的等效。
4. **逐項草擬**：類型、≤80 字核心、欄位。欄位值用**可搜尋關鍵字**，不寫流水敘述：
   - symptom：`SYMPTOM:` `ROOT:` `FIX:` `VERIFY:` `RULE:`（建新條目必帶 RULE）
   - insight：`CONTEXT:` `INSIGHT:` `IMPLICATION:` `QUERIES:` `RULE:`
5. **候選為空**：明說「本 session 無新的可記經驗」，一句帶過就停，不硬湊。

## 完成

- 通過閘門的候選**直接自動記入**，不逐項問使用者：`printf 'SYMPTOM: …\nROOT: …\nFIX: …\nVERIFY: …\nRULE: …' | fixindex fi`；insight 同樣 pipe 給 `fixindex fi`（帶 `INSIGHT:` 就走 insight 管線）。欄位與 SLUG 細節見 `fixindex fi --help`。
- 回報：新增哪幾條（編號＋核心）、略過哪些（已存在／無重現價值）。
- 最後跑 `fixindex status --json --assert-clean` 並回報結果。
