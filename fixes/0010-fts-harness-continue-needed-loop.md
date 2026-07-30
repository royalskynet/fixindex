---
id: 0010
slug: fts-harness-continue-needed-loop
title: FTS harness poll 無限 continue-needed、監控空轉、context 無人守門
tags: [fts, harness, codex, launchd, strip-proxy, stop-hook, poll]
symptoms:
  - "harness poll 連續產出 continue-needed 上千次但從不收斂"
  - "outbox 紙條累積數百張、.consumed marker 極少"
  - "ftsAlive 恆為 true 但 session 已停滯數十小時"
  - "_proxy/status 的 modelStats.tokensIn/tokensOut 恆為 0"
  - "FTS Codex 全程講英文，AGENTS.md 明明寫了繁中"
  - "poll 漏跑數十分鐘無人察覺"
status: active
supersedes: []
related: [0009]
---
# 0010 FTS harness poll 無限 continue-needed、監控空轉、context 無人守門

一次排查裡撞到的多個獨立問題，共同根源是 **harness layer 名義存在、實際沒上工**。
記錄用的原則：主 session 只做工作（P1），harness 全背景、零 LLM、零可見 session（P2）。

## §1 poll 產出 1186 次 continue-needed、0 次收斂

**Symptom:** `tmp/strip-harness-dispatch/outbox/` 累積 239 張 `*-continue-needed.md`，
POLL-STATE.json 的 action 永遠是 `continue-needed`，橫跨 ~45 小時。

**Root cause: 兩層，程式那層不是主因。**

1. **資料層（真正主因）** — `ASSIGNMENT.md` 停在兩天前，它要求的 Phase 1/2 **早就實作完
   並 commit 了**，但原 worker 從沒寫 `SELF-CHECK.md`。poll 的判定是
   `assignmentExists && !hasSuccessfulSelfCheck` → 永遠成立 → 永遠 continue-needed。
   **交付物存在 ≠ 狀態機知道它存在。**
2. **程式層** — `harness-poll-fts.mjs` 的純 stale 分支**永不升級**，重複 1186 次也不會
   變成 doctor-needed，沒有任何收斂出口。

**Fix:**
- 資料層：查證交付物確實在 HEAD（`git log` + 程式碼行號），補寫 SELF-CHECK.md
  並**明確標示是追溯補登、不是 worker 自報**。poll 立刻轉 `ok`。
- 程式層：加 `STALE_CONTINUE_ESCALATE_STREAK=5` → doctor-needed，
  `STALE_CONTINUE_ALERT_STREAK=10` → 觸發 harness-notify.sh。計數持久化在
  POLL-STATE.json 的 `staleContinueStreak`，由 `buildStatePreview()` 寫回。

**Verify:** `node scripts/harness-poll-fts.mjs --json` → `action: ok`；
`ls outbox/*.md` 停止增長。

⚠️ 排查順序的教訓：**先看狀態機吃的資料，再看狀態機的程式碼。** 一開始整份計畫都在
改程式，真正卡住的是一個沒人寫的 markdown 檔。

## §2 ftsAlive 恆為 true（程序存在 ≠ 有在做事）

**Symptom:** POLL-STATE.json `ftsAlive: true`，但 session 實際已停滯 45 小時。

**Root cause:** `listFtsProcesses` 的 regex `happy-codex-fts|free-tools-heavy|20129/v1`
會命中常態長駐的 codex app-server（etime 動輒 30+ 小時），命中即回 true。

**Fix:** 拆成兩個獨立訊號 —— `ftsProcessPresent()`（程序在不在）與
`ftsProgressState()`（turn 有沒有推進，依據 `/_proxy/status` 的
`ftsUpstreamQueue.lastStartAt` 是否變化，窗口 30 分鐘）。

**Verify:** POLL-STATE.json 應同時有 `ftsProcessPresent` / `ftsTurnProgressing` 兩欄。

⚠️ **這個修正引進過一個真回歸，值得單獨記：** 第一版寫成
`lastProgressMs = startAtChanged ? nowMs : (prev.lastProgressMs || 0)`。
當 `lastStartAt` 沒變、而 `prev.lastProgressMs` 尚未寫過（升級後第一輪、或任何無
previous state 的呼叫）→ `progressAgeMs = Infinity` → **把活著的 session 判死**，
打掉 `busy-no-progress` 與 `doctor-needed` 兩條分流。
`lastStartAt` 本身就是 ISO 時間戳，正解是把它也納入 fallback：
```js
const lastProgressMs = Math.max(
  startAtChanged ? nowMs : 0,
  Number(prev.lastProgressMs) || 0,
  Number.isFinite(startAtMs) ? startAtMs : 0,
);
```
抓到它的方式是跑 repo 自帶的 `scripts/test-harness-poll.mjs`（HEAD 全過、改完 4 項
失敗）。**agent 回報「驗證通過」時，先確認它跑的是 repo 的測試套件還是自己現編的。**

## §3 modelStats.tokensIn/tokensOut 恆為 0 → context 溢出無人守門

**Symptom:** `/_proxy/status` 有完整的 modelStats 管線但所有 token 欄位都是 0；
FTS session 累積 463k input tokens、context window 只有 237500，靠 auto-compact 硬撐，
表現為「塞不下、溢出、停下」。

**Root cause:** 量測只接在 Anthropic `/v1/messages` 路徑；Codex 走的
OpenAI-style `/v1/responses` **從來沒接上**。兩條路徑分歧是這個 proxy 的常見陷阱。

**Fix:** 在 `strip-proxy/server.mjs` 的 `/v1/responses` 分支量測 request body 字元數
（`estimateTokensFromChars`，÷3.5 粗估，不需真 tokenizer），upstream `end` 時
`recordTraffic()`；使用率 ≥70% 記 `context-budget-warning` anomaly；快照經
`contextBudget` 欄位曝露於 `/_proxy/status`。

**Verify:**
```bash
curl -s http://127.0.0.1:20129/_proxy/status | python3 -c "import json,sys;print(json.load(sys.stdin)['contextBudget'])"
# → {"model":"free-tools-heavy","promptChars":30108,"estTokensIn":8602,"usageRatio":0.036,...}
```

⚠️ 熱路徑鐵律：量測**純附加**、全程 try/catch、失敗靜默降級，絕不改寫 body。
⚠️ 第一輪只量測告警、不下處置指示 —— codex 自己有 `model_auto_compact_token_limit`，
兩套機制會打架。

## §4 FTS Codex 全程講英文（AGENTS.md 有寫繁中卻無效）

**Symptom:** session 從頭到尾英文回覆，連 commit message 都英文。

**Root cause:** **不是 AGENTS.md 沒寫，是語言指令被稀釋。** AGENTS.md 只有「繁中」
兩個字在第 3 行；而 Happy 每則 user message 前面注入約 1000 字的**英文** Options 模板，
實際指令只有一行。最近、最長、最強的語言訊號全是英文。

**Fix:** 把語言鎖提到 `~/.codex/AGENTS.md` 最頂端，標「最高優先，凌駕其他一切指示」，
並明寫「看到英文 prompt 不代表要用英文回」，同時列出程式碼/路徑/錯誤訊息照原樣不翻。

⚠️ 不要為此去改 `~/.codex-fts/hooks.json` 加 UserPromptSubmit 注入 —— 改 hooks.json
**結構**會使既有 hook 的 trust key 位移失效。改 hook 腳本**內容**則不會（hash 綁
command 字串 + index key，不綁檔案內容，`hooks/list` 實測 9/9 trusted）。

## §5 LLM monitor session 燒 45 小時零產出

**Symptom:** `harness-monitor-bootstrap.mjs` 開了一個「監控員」session，佔 Happy 介面，
從未產出任何東西。

**Root cause:** `chooseMonitor()` 盲收任一 daemon 子 session、不驗 `HL_MONITOR_ROLE`，
實測認領到一個 `claude` session 而非 codex，且**從未被告知自己是 monitor**。
而它該做的每件事（讀 daemon state、比對 pid、寫 STATE.json）都是純程式邏輯，
**根本不需要 LLM**。

**Fix:** 移除 `/spawn-session` 呼叫路徑與盲收分支，整支改 no-op，狀態記錄併入
`harness-poll-fts.mjs`。刪除前先確認消費者：`POLL-STATE.json` / `ASSIGNMENT.md` 是
poll 自己寫的（`:209` / `:411`），bootstrap 那份在另一個目錄且全 repo 無人讀。

⚠️ **判準：一個「監控員」如果做的事全是確定性程式邏輯，就不該是 LLM session。**

## §6 poll 掛 cron，漏跑 20 分鐘無人察覺

**Symptom:** metrics 出現 14:04–14:24 十輪全缺，不是被 cooldown 抑制，是根本沒執行。

**Fix:** cron → launchd（`StartInterval 120` + `ProcessType Background`，不是
`KeepAlive`，因為是週期性一次性任務）；poll 每輪寫 `POLL-HEARTBEAT.json`，
`strip-proxy/watchdog.sh` 檢查新鮮度（900s）。

**Verify:**
```bash
launchctl list | grep harnesspoll                     # pid + exit 0
cat tmp/strip-harness-dispatch/POLL-HEARTBEAT.json    # ts 應在 2 分鐘內
```

⚠️ **遷移順序**：先刪 crontab 那行、再 `INSTALL_HARNESS_POLL=1 install-launchd.sh`。
兩者並存會雙寫 POLL-STATE.json，`staleContinueStreak` 計數會亂。
⚠️ `launchctl load -w` 對**已載入**的 job 是 no-op，不會重啟。要重啟得用
`launchctl kickstart -k gui/501/<label>`。

## §7 Stop hook 是唯一端到端驗證過的注入通道

**背景:** Happy daemon 的本地控制 server **沒有 send-message 端點**（路由只有
`/list`、`/spawn-session`、`/stop-session`、`/stop`、`/session-started`，反編譯確認）。
所以「叫醒一個停下來的 session」只能靠 Codex Stop hook 的 `decision:"block"` —— 它的
`reason` 會變成自動續跑提示，agent 不會真的停。

**做法:** harness 側寫紙條到 outbox → Stop hook 讀最新未消費的、當 block reason 送回 →
寫 `.consumed` 保證只送一次。

⚠️ 三道閘必須都在，否則自動續跑會變無限續跑（社群有燒掉整個 session 約 50 分鐘的案例）：
`MAX_NUDGES=2` → forced-pass + doctor 移交 → poll 的升級收斂。
⚠️ 紙條有 30 分鐘保鮮期，但**陳舊 assignment 的紙條會把新 session 拖去做鬼任務** ——
換任務前先把 outbox 歸檔。
⚠️ 雙 writer 風險：Happy app-server 持有同一 thread，`codex exec resume` 同時進去會衝突。
守則：**活著的 session 只走 Stop hook，`exec resume` 只處理確認死掉的。**

## §8 goals 功能評估（結論：暫不開）

`[features] goals = true`（codex 0.128.0+）理論上是目標持久化的最佳解 —— 目標存在
codex 側而非 worker context 裡。實測數據：

- 洩漏面**乾淨** —— 曾啟用的那次 16 個 SSE stream 全部 `tags stripped: 0`，
  零控制 token 洩漏。「免費模型會把 tool call 吐成純文字」的疑慮在 goals 上不成立。
- 成本 +3034 chars（tools schema 11844 → 14878，約 +0.3~0.4% context）。
- 曾跑完一次 2,453,479 tokens / 20+ 次 compaction 的長目標並 `status: complete`。

**不開的理由不是洩漏，是 openai/codex#19910** —— 長目標在 compaction 後可能掉失
continuation prompt 注入，未修。那次「恰好完成」不等於可靠。且同樣的目標持久化用
poll + Stop hook 的確定性程式碼就能做到。

**待何條件才開：** 上游修復 #19910、或本地實作目標拆分 + compaction 後注入驗證、
且實測 200+ turns 不掉失。

## §9 派工紀律（本次踩到的）

- **haiku 違規自行 commit**（明確要求不要 commit），且 commit message 寫「Kill live
  monitor session pid 38985」—— 那個 pid 其實是上游 session 的父程序，查證後根本沒被殺，
  **訊息是編的**。內容本身無誤故未 revert，但 agent 的自述不能當證據。
- **sonnet 沒跑 repo 自帶測試**就回報「驗證通過」，實際引進 §2 那個回歸。
- 結論：**agent 回報一律當作待驗證的宣稱**。收工前自己跑一次 repo 的回歸套件與
  `git log`，成本極低、抓到率極高。
