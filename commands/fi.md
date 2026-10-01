---
description: 掃描當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後草擬補記
---

掃描本 session（從開始到現在）的全部內容與產出，找出**值得永久記入 fixindex** 的經驗。不是逐句回報，是挖金：有價值的才列出。

## 目標：兩類條目

1. **insight（`type: insight`）** — 已固化的設計洞見／架構決策／跨案模式。判準：改方式比記解法更有價值、以後別的專案也可能用到。
2. **symptom（一般 fix 條目）** — 可搜尋的錯誤經驗：症狀→根因→解法→驗證。判準：撞到會重複、下次用 `fixindex find "<關鍵字>"` 找得到。

## 程序

步驟 1-2 是機械活（讀 transcript、逐條查重），派 sonnet 子代理做；步驟 3 起的判斷留主 session。

0. **抽出精簡 transcript**（**不可省**：原始 jsonl 一個中等 session 就 1.2 MB／約 300k token，超過子代理 window，直接餵進去只會爆掉或被迫抽樣然後硬掰）：

   ```bash
   T=$(ls -t ~/.claude/projects/"$(pwd | sed 's#[/.]#-#g')"/*.jsonl | head -1)
   OUT="${TMPDIR:-/tmp}/fi-scan-$$.txt"
   jq -r 'select(.type=="user" or .type=="assistant") | .message.content |
     if type=="array" then (map(
       if .type=="text" then .text
       elif .type=="tool_use" then "TOOL "+.name+" "+((.input|tostring)[0:300])
       elif .type=="tool_result" then "RESULT "+((.content|tostring)[0:600])
       else empty end)|join("\n")) else tostring end' "$T" > "$OUT"
   node ~/.claude/tools/fi-mask-transcript.mjs "$OUT" "$OUT.masked"   # fix 9767：不可省
   wc -c "$OUT.masked"
   ```

   最新 mtime 那支就是本 session（它正在被寫入）；同 cwd 有並行 session 時會取錯，屆時改用 scratchpad 目錄名（＝session id）。保留對話全文（金礦在對話裡），工具 input 砍到 300 字、輸出砍到 600 字——錯誤訊息幾乎都在開頭，砍尾巴不傷。實測 1.2 MB → 74 KB。

   **脫敏不可省（fix 9767）**：精簡 transcript 原樣保留本 session 出現過的 key 樣字串、email、public IPv4，子代理一讀就被 sensitive-canary 擋，兩隻各燒 ~38k token 什麼也沒做。`fi-mask-transcript.mjs` 遮 key 前綴／PEM／`VAR=值`／長不透明串／hex≥32／email／public IP，**只把 `$OUT.masked` 餵給子代理**。注意這通常是**真陽性**不是誤報（session 裡自己寫過的假 token 也算），所以不要去改 canary 規則、不要要 allow 標籤。
   脫敏後確認一次（路徑別出現在 Bash 指令列，否則 canary 展開路徑掃內容會先擋掉你的檢查，fix 9622/9689 —— 寫成小 node runner 在腳本內組路徑）：餵 hook `{"tool_name":"Read","tool_input":{"file_path":"<masked>"}}` 應 rc=0。

1-2. **派遣一次 `Agent`**（`subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`），prompt 自含以下全部（子代理看不到本對話）：

   - `$OUT.masked` 的絕對路徑（步驟 0 產出的**脫敏版**，不是 `$OUT`、更不是原始 jsonl）。要它**逐條掃過**，不是抽樣。順便叮嚀它不要試圖還原 `<MASKED_*>` 佔位符、不要去讀未脫敏原檔。
   - **窮舉候選**：每一段改動、每條報錯、每個重新摸索才搞懂的地方。連「糾正我誤解」也算（例：學到某設定其實沒生效、某 key 是錯的）。**反事實閘門**：凡出過錯、查到根因、改了做法的點，至少列進候選。
   - **逐條去重**：每個候選跑 `fixindex find "<核心關鍵字>"` 與 `fixindex insights "<主題>"`，把原始輸出附在該候選下。
   - 回報格式：每條給「候選核心 ≤80 字／建議類型 insight|symptom／查重指令與原始輸出／已存在 or 新」。**只回報，不寫入 fixindex。**
   - 判斷「值不值得記」不是它的工作，寧可多列。

   `$OUT.masked` 仍 >150 KB（超長 session）→ 切塊平行派，**同一個 response 內一次派完全部塊**（不要一塊一塊等），每塊獨立回報，主 session 合併。

   背景派的理由：每個子代理要跑十幾次 `fixindex find`／`insights`，實測單塊 4–5 分鐘，前景派期間主 session 完全沒輸出，使用者會以為卡死。背景派時 harness 完成後會叫回來，使用者中途還能插話。

   脫敏後子代理仍被 sensitive-canary 擋住（遮罩規則漏了新形狀）→ 它停手回報阻斷點，主 session 先補 `fi-mask-transcript.mjs` 的遮罩規則再重派；補不動才改用自己 context 內的記憶直接掃。都不繞過 guard、都不要 allow 標籤。

3. **收斂**（主 session 做）：對子代理回報的候選，過濾掉一次性、專案私有、無重現價值的。只留通過「下次找得到才有意義」閘門的。子代理標「已存在」的核對一下查重輸出是否真的等效，不盲信。
4. **逐項輸出候選**：每條給
   - 類型（insight / symptom）
   - 一段 ≤80 字核心（這條在講什麼、為什麼值得記）
   - 擬好的 frontmatter／fields（SYMPTOM / ROOT / FIX / VERIFY，或 insight 的 summary；key 值用 **可搜尋關鍵字**，不是流水敘述，確保 `find` 命中）
5. **若候選為空**：明說「本 session 無新的可記經驗」，一句帶過就停，不硬湊。

## 完成

- 篩過「泛化後有意義」閘門的候選，**直接自動記入**（`fixindex fi`／`fixindex insight`），不必使用者逐項確認。模型評估＝權威。
- 記完回報：新增哪幾條（編號＋核心）、略過哪些（已存在／無重現價值）。
- 最後跑一次 `fixindex status --json --assert-clean` 確認同步狀態並回報。
