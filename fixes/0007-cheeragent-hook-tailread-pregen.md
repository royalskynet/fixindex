---
id: 0007
title: "cheeragent hook 效能優化 — tail-read + background pregen"
date: 2026-07-30
symptoms: ["stop hook 110s", "pretooluse 1.6s", "tail-read transcript", "inline llm hot path"]
tags: ["cheeragent", "hook", "performance", "node"]
---

## 症狀
`/doctor` transcript 掃描顯示：
- **Stop hook（capture.js）**：平均 10.9s、最壞 **110s**
- **PreToolUse inject（pretool_inject.js）**：每次 Bash/Write/Edit/NotebookEdit 呼叫墊 **~1.6s**

## 根因
1. **lib/detect.js `readTranscript`**：用 `fs.readFileSync` 把整個 JSONL（數十 MB）讀進記憶體再 `split('\n')`，只為留最後 20 行。超長 session O(檔案大小) 同步讀取 + GC。
2. **hooks/pretool_inject.js**：30% 機率（`llm_improv_ratio 0.3`）在熱路徑上同步打 `openrouter/free`（free tier 排隊，逼近 4000ms timeout），加上每次 hook 都是全新 node 進程冷啟動。

## 解法
### 1. `lib/detect.js` — transcript 改 tail-read（消 110s）
- `readTranscript(path, tail=20)` 改為只讀檔案尾端固定 chunk：
  - `fs.statSync` 取 size，`start = max(0, size - CHUNK)`，`CHUNK = 128*1024`（20 行 JSONL 綽綽有餘）。
  - `fs.openSync` + `fs.readSync(fd, buf, 0, len, start)` + `closeSync`，只 decode 尾端 buffer。
  - `buf.toString('utf8').split('\n').filter(Boolean).slice(-tail)`；首行可能不完整 → `filter(Boolean)` 後丟掉不完整首行。
  - 檔案 < CHUNK 時等同全讀（fallback）。
- 從 O(檔案大小) 變 O(128KB) 常數。10 萬行 JSONL 從秒級降到 **1ms**。

### 2. `hooks/capture.js` — enqueue 後 spawn detached 預生成 worker
- `enqueue()` 拿到 queue 檔路徑後，**若 `ingredients.mode === 'llm'`**：
  ```js
  const { spawn } = require('child_process');
  const child = spawn(process.execPath, [workerPath, queueFilePath], { detached: true, stdio: 'ignore' });
  child.unref();
  ```
- capture.js 不等 worker，立即印 JSON 退出（worker 存活於父進程外）。

### 3. 新檔 `hooks/pregen_worker.js` — detached LLM 產生器
- 讀 argv 的 queue 檔路徑 → `JSON.parse` 取 ingredients。
- 呼叫既有 `generate.js` 的 LLM 路徑（`generateWithLLM`），成功則把 finalized `text` + `mode` 標記寫回該 queue 檔。
- **原子寫**：寫 temp 檔 + `fs.renameSync`，避免 inject 讀到半寫 JSON。
- **競態守衛**：寫回前 `fs.existsSync` 檢查檔案還在（inject 可能已 consume+remove）；不在就直接退出，不重建 stale 檔。
- 失敗（timeout/no_api_key）：不寫 `text`，讓 inject 走 template fallback。

### 4. `hooks/pretool_inject.js` — 消 inline LLM
- 現流程：挑 latest queue entry → `canInject` → `generateText(ingredients)`〔**LLM 在此觸發**〕→ record → remove → emit。
- 改為：挑 entry → `canInject` → **若 `entry.text` 存在直接用**；否則 `composeTemplate(ingredients)` inline（本地、近乎瞬間）。**不再 inline 呼叫 LLM**。→ record → remove → emit。

### 5. `lib/queue.js` — 原子寫 helper
- 現 `enqueue` 直接 `writeFileSync` → 抽出 `writeEntryAtomic(path, obj)`（temp + rename），enqueue 與 worker 共用。

## 驗收結果
- **tail-read**：10 萬行 transcript → 1ms（原 ~秒級），正確回傳最後 20 行。
- **pretool_inject template 路徑**：node 冷啟動地板 ~200ms（原 ~1.6s）。
- **背景預生成**：capture.js 即時返回，worker 非阻塞寫回 queue 檔。
- **fallback**：無 `OPENROUTER_API_KEY` 時 worker 不寫 text、inject 走 template、全程無報錯。

## 取捨與已知邊界
- **競態**：Stop 後到下一回合首個工具呼叫通常間隔數秒，worker 有時間跑完；若使用者立刻連發工具，inject 落 template（可接受，即設計中的 fallback 路徑）。
- **budget**：LLM 呼叫移到 worker，`recordInjection` 仍在 inject 時計注入文字 token。若注入後被 budget gate 擋掉，worker 那次 LLM 算浪費——裝飾功能可接受。
- **殘留延遲**：PreToolUse 仍付 node 冷啟動 + `listAll()` 掃描；本次不消（需 daemon 化，另案）。

## 相關檔案
- `lib/detect.js` — tail-read
- `lib/queue.js` — writeEntryAtomic
- `hooks/capture.js` — spawn detached worker
- `hooks/pregen_worker.js` — 新檔，background LLM 生成
- `hooks/pretool_inject.js` — 讀 entry.text / template fallback
