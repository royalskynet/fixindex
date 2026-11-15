---
description: 回顧當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後寫入
---

回顧本 session 上次 /fi 之後的內容，只挖**值得永久記入 fixindex** 的經驗，不逐句回報。

## 兩類條目

1. **insight** — 已固化的設計洞見／架構決策／跨案模式：改方式比記解法有價值、別的專案也用得到。
2. **symptom**（一般 defect 條目）— 症狀→根因→解法→驗證：會重複撞到、下次 `fixindex find "<關鍵字>"` 找得到。

## 程序（主 session 就地回顧；不派 deep、不派子代理、不交外部 LLM 重讀逐字稿）

設計借鏡 claude-reflect-system：零 LLM 正則抓訊號，主 session 用自己手上的上下文判斷。**整個流程 30 秒內收完**：主 session 就地跑，不派 od／dcq／deep（11-15 派 od 排隊加重試耗掉 8 分鐘以上）；工具呼叫共兩次（抓訊號、寫入＋收尾）。

1. **抓訊號**（約 0.1 秒）：
   ```bash
   python3 ~/dev/fixindex/tools/fi-signals.py <本 session jsonl 絕對路徑>
   ```
   印出上次 /fi 之後的 `ERR`（工具真的失敗＋觸發指令）與 `USER`（使用者糾正）。rc=5＝沒有新內容，一句帶過。訊號只是提示：主 session 記得的根因、設計決定也算，不限清單內。
2. **挑候選**：只留會重複撞到、下次搜得到的。一次性手誤、護欄照設計擋下、已在本 session 規則裡的不收。
3. **寫入＋收尾（一次 Bash）**：不先另外查重，`fixindex fi` 寫入時自己查重（相近的追加到既有條目，沒有才建新條目）。所有條目一次 pipe，每筆之間一行 `%%`，同一條指令接收尾。**每筆第一行帶 `SLUG: <英文-kebab>`**：沒帶時標題 token 會前綴命中無關舊檔（11-15 實測「session」把新 insight 追加進 11415-session-stop-…）；帶了只認同名檔，沒有就建新：
   ```bash
   printf 'SLUG: …\nSYMPTOM: …\nROOT: …\nFIX: …\nVERIFY: …\nRULE: …\n%%%%\nSLUG: …\nCONTEXT: …\nINSIGHT: …\nIMPLICATION: …\nQUERIES: …\nRULE: …\n' | fixindex fi && fixindex status --json --assert-clean && python3 ~/dev/fixindex/tools/fi-signals.py --ack <jsonl>
   ```
   批次只 pull／commit／push 各一次，每筆約 2–3 秒；逐筆呼叫每筆約 10 秒。驗收看 JSON 的 `"pushed": true`，不用 `fixindex find --json` 找正文字串（它只回標題與規則，不含正文）。
4. **回報**：新增（編號＋核心）、補充（追加到哪條）、略過各一行；沒有就「本 session 無新的可記經驗」。

## 備援（fi-run，等同 claude-reflect 的 --scan-history）

主 session 已 compact、手上沒有那段上下文，或要補掃舊 session，才跑：

```bash
bash ~/dev/fixindex/tools/fi-run.sh <jsonl>      # 背景跑；FI_FULL=1 重掃整個 session
```

流程：抽逐字稿 → 遮罩 → Presidio scrub → 免費模型抽候選與裁決 → 寫入 → 驗收，與 fi-signals 共用標記檔。退出碼：0 完成｜5 沒新內容｜2 找不到 transcript｜3 PII scrub（:4102）不通或 LLM 失敗｜4 寫入失敗｜6 超過 `FI_BUDGET`（預設 90 秒）｜1 驗收失敗。rc=3 是 scrub 時**不准**繞過 scrub 把逐字稿交給外部 LLM（鐵則 6）。

## 欄位

- symptom：`SYMPTOM:` `ROOT:` `FIX:` `VERIFY:` `RULE:`（建新條目必帶 RULE；欄位要用下次會搜的關鍵字）
- insight：`CONTEXT:` `INSIGHT:` `IMPLICATION:` `QUERIES:` `RULE:`

改流程改 `tools/fi-signals.py`／`tools/fi-signals-test.sh`；備援改 `tools/fi-run.sh`、`tools/fi_pipeline.py` 與其測試。
