---
id: 0012
slug: fts-harness-selfheal-online
title: FTS harness 自癒閉環上線 — 假警報止血、空轉 turn 偵測、doctor/layer1.8 啟用
tags: [fts, harness, launchd, telegram, acceptance-gate, opencode, codex, self-heal]
symptoms:
  - "收到 HARNESS ALERT 但 state 路徑是 /var/folders/.../harness-poll-test-XXXX/POLL-STATE.json"
  - "單元測試跑完就收到 Telegram 警報"
  - "[FTS HARNESS DOCTOR-NEEDED] 警報內容是 ftsProcessPresent=... 欄位湯看不懂"
  - "codex session task_started 後 2 毫秒就 task_complete，零 agent_message 零 tool call"
  - "FTS session 停擺但 harness 抓不到（isStalledMidTurn 漏抓）"
  - "plutil -p 顯示 plist 沒有 --doctor 但檔案裡其實有"
  - "layer1.8 一直是 would-block 不會真的 block"
  - "opencode run / codex exec / verify-codex.sh 前景執行 exit code 137"
status: done
supersedes: []
related: [0009]
---
# 0012 FTS harness 自癒閉環上線

日期：2026-07-31。倉庫：`/Users/51mini/omniroute-free-tools`。
背景脈絡：`notes/fts-codex-session-no-response-20260731.md`（session 無回應三層根因）。

---

## §1 單元測試打真 Telegram（假警報）

**Symptom**
使用者收到：
```
[FTS HARNESS DOCTOR-NEEDED] | No active FTS session while acceptance is open for 3 consecutive poll(s)
| ftsProcessPresent=false ftsTurnProgressing=true staleStreak=0
| state: /var/folders/77/.../T/harness-poll-test-Wl2jVs/POLL-STATE.json
```
`state:` 是 `mktemp` 目錄 → 不是 live 停擺。

**Root cause**
`scripts/test-harness-poll.mjs:39 runFixtureWithWrite()` 用 `--work-dir <temp>` 跑 poll，但**沒帶 `--no-write`**，`opts.writeOutbox` 預設 true。
`scripts/harness-poll-fts.mjs:553 triggerNotify()` 只看 `verdict.action`，**不看 `opts.fixture`** → fixture 一產生 `doctor-needed` 就經 `harness-notify.sh` → koko Hermes → Telegram 真的送出。
新增的 `scripts/fixtures/harness-poll-doctor-autoheal.json` 正是產 `doctor-needed`，所以是自己的測試噴使用者。

**Fix**
`triggerNotify()` 本體第一行（在 `verdict.action` 檢查之前）：
```js
if (opts.fixture) return { notified: false, reason: "fixture-mode" };
```
**為什麼不在測試端加 `--no-write`**：`--no-write` 會連 `POLL-STATE.json` 都不寫，現有 26 項斷言靠它讀 state。fixture 模式定義上就是合成資料，在來源端短路才是對的層級。

**Verify**
```bash
TMPD=$(mktemp -d); node scripts/harness-poll-fts.mjs --doctor --json \
  --fixture scripts/fixtures/harness-poll-doctor-autoheal.json --work-dir "$TMPD"
```
→ `notified: false fixture-mode`。
另比對 `strip-proxy/logs/.notify-cooldown-poll-doctor-needed` 的 mtime，跑測試前後不變（停在 09:42）才算過 —— 這是唯一能證明「真的沒發出去」的客觀證據，光看 JSON 的 `notified` 欄位不夠。

---

## §2 警報內容欄位湯

**Symptom** 警報主體是 `ftsProcessPresent=false ftsTurnProgressing=true staleStreak=0` + temp 絕對路徑，人看不懂要做什麼。

**Fix** 同 `triggerNotify()`，`message` 由四段 `" | "` join 改成兩行 `"\n"` join：
```js
const message = [
  `[FTS 自癒] ${verdict.action === "stuck" ? "卡住需人介入" : "偵測到停擺，正在自動修復"}`,
  `原因：${verdict.reason}；已連續 ${streak} 輪`,
].join('\n');
```
保留 `execFileSync` 與 `--cooldown-key` 不變。

---

## §3 空轉 turn（no-op turn）偵測

**Symptom**
`019fb390` 的 rollout 顯示真正的停擺型態：`task_started` → **2 毫秒**後 `task_complete`，零 `agent_message`、零 tool call，連續 4 次（15:43:51.995→.997、15:44:37.630→.632）。
原 `isStalledMidTurn()` 只認「最後一筆是 `task_started`」，空轉 turn 有 `task_complete` → **完全漏抓**。

**Fix**
獨立模組 `scripts/harness-session-scan.mjs`（134 行），非塞進 poll 主檔：
- `parseSessionFile()` 從尾端回掃到最近一筆 `task_started`，多回傳 `lastTaskStartedTs` / `lastTaskCompleteTs` / `sawTaskCompleteAfterStart` / `agentMessageCount` / `toolCallCount`
- `isNoOpTurn(entry, nowMs):69` 四重條件：有 `task_complete` + `agentMessageCount===0` + `toolCallCount===0` + `完成-開始 < NOOP_TURN_MAX_MS(10s)` + `nowMs - complete >= NOOP_QUIET_MS(120s)` 靜置窗
- `runSessionScanBranch():99` 同時收 `stalled[]` 與 `noOp[]`，各自獨立 resume prompt
- 護欄：per-session 30 分鐘 resume cooldown（`tmp/fts-session-resume-locks/`）+ `processAlive`（lsof）前提 + 只掃最近 3 天

**JSONL 格式坑（踩過兩次，務必記住）**
1. 事件是**雙層 envelope**：外層 `{"type":"event_msg", ...}`，真正種類在 `payload.type`。誤判 `e.type === "task_started"` 會永遠掃不到東西（見 mem obs 31848）。
2. `parseSessionFile` 用的是 `Date.parse(e.timestamp)`（ISO 字串），**不是** `started_at`/`completed_at`（那兩個是 epoch **秒**）。
3. 第一行必須是 `{"type":"session_meta","payload":{"session_id":...,"cwd":...}}`，缺了整份被 `return null` 略過。
4. `listRecentSessionFiles()` 走 `<root>/YYYY/MM/DD/rollout-*.jsonl`，且用**本地時區** `getFullYear/getMonth/getDate`。fixture 目錄日期要對齊 `nowMs` 的本地日期 —— `nowMs=1785260000000` 是 `2026-07-28T17:33:20Z`，GMT+8 下是 07/29，但掃描從 nowMs 當天往回，所以要放 **07/28**。放錯目錄 → `scannedFiles: 0` 靜默無結果。

**Verify（合成 dry-run，零 live 風險）**
造 `scripts/fixtures/sessions/2026/07/28/rollout-{noop,normal,midturn}.jsonl`：
```bash
node scripts/harness-poll-fts.mjs --no-write --json \
  --sessions-dir scripts/fixtures/sessions \
  --fixture scripts/fixtures/harness-poll-doctor-autoheal.json
```
實測輸出：
```json
"scannedFiles": 3,
"stalled": [{"sessionId":"...midt...","ageSeconds":1800,"processAlive":false}],
"noOp":    [{"sessionId":"...noop...","ageSeconds":300,"turnDurationMs":2,"processAlive":false}],
"resumed": [], "resumedNoOp": [], "wouldResume": [], "errors": []
```
`normal`（有 agent_message）不在任何清單 → 無誤報。

真實 dry-run `node scripts/harness-poll-fts.mjs --no-write --json`：掃 80 檔、抓到 6 個歷史空轉（`turnDurationMs` 269~8206ms）、全 `processAlive=false` 故正確不進 `wouldResume`、零 errors。

---

## §4 doctor 模組曾是死碼（承 §5 上線前置）

**Symptom** plist 加 `--doctor` 會讓 poll 整個壞掉。

**Root cause** `scripts/harness-doctor-run.mjs` 原本沒有任何 `export`，且結尾是**無 guard 的頂層 CLI 進入點**。`harness-poll-fts.mjs` 的 `await import()` 會：import 當下就拿 poll 的 `process.argv` 跑一次 doctor；命中閘門 skip 時該檔 `process.exit(0)` → **直接殺掉 poll 進程**，`triggerNotify` 與 session-scan 全不執行。

**Fix**
- 加 `export { runDoctor, consumeOutbox }`
- CLI 區塊包 guard，**必須用 `fileURLToPath`**：
  ```js
  import { fileURLToPath } from 'node:url';
  if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) { … }
  ```
  不可用 `new URL(import.meta.url).pathname` —— 路徑含非 ASCII 會 percent-encode 而比不中。
- poll 端整段包 `try/catch`，且 `consumeOutbox()` **只在 `!doctorResult.skipped` 時呼叫**（被閘門 skip 代表 doctor 沒跑，outbox 必須留著給下一輪；CLI 路徑 skip 就 `process.exit(0)` 不 consume，這是正確語意的對照組）。

**Verify（poll 存活是關鍵反證）**
```bash
node scripts/harness-poll-fts.mjs --doctor --json --fixture <doctor-autoheal> --work-dir $(mktemp -d)
```
→ stdout **能完整 JSON.parse**（含 `sessionScan` 區塊）就證明沒被 `process.exit(0)` 殺。實測 `action: doctor-needed`、`doctor: {"error":null}`、`DOCTOR-LAST.json` 產出 `outcome=cannot-fix` + `summary/remaining/evidence` 四欄。

doctor 三道防爆閘實測 reason 原文（temp dir 造檔即可觸發，不會外呼）：
`"cooldown: 1s / 1800s"`、`"singleton: pid=34249 started 1s ago"`、`"attempt cap: 2/2 for 864299fd"`

---

## §5 上線：plist --doctor 與 layer1.8 sentinel

**坑：`plutil -p` 讀到舊快取**
`plutil -p <plist>` 顯示 `ProgramArguments` 只有 `--json`，但 `cat` 同一個檔案**已含 `<string>--doctor</string>`**。據此誤判「Stage 3 全未動」。
→ **改 plist 前一律 `cat` 原始 XML，不信 `plutil -p`。**

**重載**：`launchctl kickstart -k gui/$(id -u)/com.royalskynet.freetools-harnesspoll`
（`launchctl unload` 被 `~/.claude/hooks/guard.js` 硬攔）。
`StartInterval` 型 agent 跑完即退，`launchctl print` 顯示 `state = not running` 是**正常**，不是失敗。

**layer1.8 sentinel 機制**
`/Users/51mini/secret-cheeragent/hooks/fts-acceptance-gate.js:401-403`：
```js
const DRYRUN_SENTINEL = '/Users/51mini/.codex-fts/.layer18-dryrun';
const dryRun = process.env.HL_UNFINISHED_DRYRUN === '1' && fs.existsSync(DRYRUN_SENTINEL);
```
`~/.codex-fts/hooks.json:65` 是 `/usr/bin/env HL_UNFINISHED_DRYRUN=1 node .../fts-acceptance-gate.js` → env **恆為 1**，所以開關實質由 sentinel 決定：
- 刪 sentinel = 上線（真 block）
- `touch` sentinel = 回觀察模式

**為什麼用 sentinel 不改 hooks.json**：見 `0009:200-215` —— 改 `hooks.json` 條目會位移 index 讓 `trusted_hash` 靜默失效。

**順帶修的順序 bug**：`applyNudgeCap(sessionId, turnId, true)` 必須放在 dryRun 分支**之後**（`:414`）。放前面的話觀察模式也吃 nudge 額度、排擠 layer2。現況 `:408-412` dryRun 直接 `return pass()`，順序正確。

**Verify**
```bash
HL_UNFINISHED_DRYRUN=1 node -e 'const fs=require("fs");const s="/Users/51mini/.codex-fts/.layer18-dryrun";
console.log("dryRun="+(process.env.HL_UNFINISHED_DRYRUN==="1"&&fs.existsSync(s)))'
```
→ `dryRun=false` 即 block 模式開啟。
`~/.codex-fts/acceptance-gate.log` 歷史證據（觀察期已驗證偵測器有效）：
```
... | layer1.8 | block | matched: "繼續改寫作業。", nudge#1
... | layer1.8 | block | matched: "現在處理亞特蘭提斯.md。", nudge#2
... | dry | layer1.8 | would-block | match | matched: "改完了，現在要跑測試。"
```
`MAX_NUDGES=2` 上限生效（第三次 Stop 必放行）。

---

## §6 無效嘗試 / 誤判紀錄

| 做法 | 結果 |
|---|---|
| 前景跑 `opencode run <長任務>` / `verify-codex.sh` / `codex exec` | **exit 137 (SIGKILL)** ×3。記憶體 80% free、swap 0 → **不是 OOM**，是前景長指令（>2 分鐘外呼）逾時被砍。改 `run_in_background: true` + `until [ -s <file> ]` 等待即正常 |
| `plutil -p` 判斷 plist 內容 | 讀到舊快取，誤判 `--doctor` 未加。要 `cat` 原始 XML |
| 派 opencode 造小批 fixture | 被 137 砍，自己 3 分鐘寫完。**免費池派工對「改既有函式」划算（Stage A 一單過，28 項測試綠），對「造 3 個小檔」不划算 —— 啟動成本高過自己寫** |
| `git diff scripts/harness-doctor-run.mjs` 驗證改動 | 回傳空 —— 該檔是 **untracked**，diff 不顯示。要直接 grep 檔案內容 |
| 早期直接 `CODEX_HOME=... codex exec` 不 source cred | `ERROR: Missing environment variable: OMNIROUTE_API_KEY`。必須 `set -a; . "$HOME/.creds/omniroute/codex-fts.env"; set +a`（見 0009） |
| macOS 用 `timeout` 指令 | `command not found: timeout`。用 Bash tool 的 `timeout` 參數 |

---

## §7 上線後現況與回滾

**live 驗證**（kickstart 後真實一輪）：
`action: ok`｜`doctor: {"skipped":true}`（健康時不觸發）｜`sessionScan.scannedFiles: 82`｜`notified: false action-not-escalated`｜poll 活到完整 JSON。
回歸：`node scripts/test-harness-poll.mjs` 28 項全綠；`/_proxy/anomalies` `totalCount:24` 僅 `omniroute-version-drift`(22) + `fts-model-pin`(2) 兩種已知類型；FTS 渠道 `codex exec` → `FTS_PONG` exit 0，hooks（含 Stop）正常。

**回滾**
- layer1.8：`touch /Users/51mini/.codex-fts/.layer18-dryrun`（一秒回觀察模式）
- doctor：plist 拿掉 `--doctor` + `launchctl kickstart -k`
- session-scan：plist 加 `--no-session-scan`
- 程式：`git checkout scripts/harness-poll-fts.mjs`
- 備份：`fts-acceptance-gate.js.bak-20260731-1002`、`com.royalskynet.freetools-harnesspoll.plist.bak-20260731-1001`
