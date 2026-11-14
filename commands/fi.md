---
description: 回顧當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後寫入
---

回顧本 session 上次 /fi 之後的內容，只挖**值得永久記入 fixindex** 的經驗，不逐句回報。

## 兩類條目

1. **insight** — 已固化的設計洞見／架構決策／跨案模式：改方式比記解法有價值、別的專案也用得到。
2. **symptom**（一般 defect 條目）— 症狀→根因→解法→驗證：會重複撞到、下次 `fixindex find "<關鍵字>"` 找得到。

## 程序（主 session 就地回顧；不派 deep、不派子代理、不交外部 LLM 重讀逐字稿）

設計借鏡 claude-reflect-system：零 LLM 正則抓訊號，主 session 用自己手上的上下文判斷。目標 30–60 秒。

1. **抓訊號**（約 0.1 秒）：
   ```bash
   python3 ~/dev/fixindex/tools/fi-signals.py <本 session jsonl 絕對路徑>
   ```
   印出上次 /fi 之後的 `ERR`（工具真的失敗＋觸發指令）與 `USER`（使用者糾正）。rc=5＝沒有新內容，一句帶過。訊號只是提示：主 session 記得的根因、設計決定也算，不限清單內。
2. **挑候選**：只留會重複撞到、下次搜得到的。一次性手誤、護欄照設計擋下、已在本 session 規則裡的不收。
3. **查重一次**：候選的關鍵字寫進一個檔（一行一個），跑
   `fixindex find --queries-file <檔> --json --limit 3` 與 `fixindex insights --queries-file <檔> --json --limit 3`（同一則訊息平行）。已存在且沒新東西的略過。
4. **寫入**：每條一次 `printf 'SYMPTOM: …\nROOT: …\nFIX: …\nVERIFY: …\nRULE: …\n' | fixindex fi`（insight 用 `CONTEXT／INSIGHT／IMPLICATION／QUERIES／RULE`）。`fixindex fi` 自己查重：相近的追加到既有條目，沒有才建新條目。
5. **收尾**：`fixindex status --json --assert-clean` 過了，再跑 `python3 ~/dev/fixindex/tools/fi-signals.py --ack <jsonl>` 前移標記。
6. **回報**：新增（編號＋核心）、補充、略過各一行；沒有就「本 session 無新的可記經驗」。

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
