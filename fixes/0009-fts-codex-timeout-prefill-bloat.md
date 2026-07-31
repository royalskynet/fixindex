---
id: 0009
slug: fts-codex-timeout-prefill-bloat
title: "FTS Codex 停止：header timeout（協定層）+ 75k tool schema（臃腫層）+ 自評放水（判定層）"
tags: [fts, codex, omniroute, strip-proxy, timeout, tool_search, hooks, hook-trust, claude-mem, mem0, skills]
symptoms:
  - "FTS codex session turn 以 last_agent_message=null 結束"
  - "strip-proxy anomalies.jsonl 出現 responses-upstream-header-timeout"
  - "app.log 多 target 同時 abort（未送首 token）"
  - "FTS codex 自稱『全驗收通過』但實際半數修法沒做（無錯誤、無報警）"
  - "新加的 codex hook 靜默不執行、不報錯"
  - "hooks/list 顯示 trustStatus=modified，plugin 升版後 hook 不再執行"
  - "claude-mem 在 codex session 完全沒記錄（Claude Code 有、codex 沒有）"
  - "codex exec 的 tool schema 比 app-server 肥（47185 chars vs 11228）"
  - "failed to load skill ... missing YAML frontmatter delimited by ---"
  - "codex hook 指向不存在的腳本卻不報錯（mem0-hooks）"
  - "hook: PreToolUse Failed 但 hook 本身 exit=0"
  - "改 config.toml 的 model 但 happy live session 仍跑 free-tools-heavy（input 44k 肥）"
  - "瘦 slug 下模型對 happy__change_title 回『無此工具』（其實要先 tool_search）"
  - "happy 升版後 codex slug patch 消失、session 又變肥"
  - "Codex error: stream disconnected before completion / Responses stream completed with no assistant output"
  - "anomalies.jsonl responses-empty-completed（上游回 completed 但零輸出）"
  - "app.log [ERROR] [400]: Validation: Unsupported parameter(s): `verbosity`（NVIDIA NIM）"
  - "模型把 tool_search 當 shell 指令跑：zsh:1: command not found: tool_search"
  - "fts new 回報已開 session，但 log 只有 ^D / daemon list 出現 stale session"
  - "Happy app 傳訊無反應；daemon log 顯示 Removing stale session with PID"
  - "新 FTS session 運轉中但無回應；CodexAppServer Turn timed out after 600000ms"
  - "FTS turn 卡在 MCP startup，repomix 只有 starting 沒有 ready/failed"
status: fixed
supersedes: []
related: [0002]
---

# 0009 FTS Codex 停止（三層根因）

三條**互相獨立**的失敗路徑，修一層不會治另一層。

## §1 層 1：協定層 — header timeout

`codex-rs/codex-api/src/provider.rs` 建 session 時 `timeout: None`，`http-client` 也沒設 `.timeout()`
→ **codex 對「等 response headers」是無界等待**。`stream_idle_timeout_ms`（預設 300000）**只在 headers 收到後才起算**。

280s 那條線完全是 strip-proxy 自加的 `RESPONSES_UPSTREAM_HEADER_TIMEOUT_MS`（plist env；程式碼預設在 `server.mjs` L29 是 100_000，**沒有 280000 字面量**）。

**不是預算算術問題**（一度誤判）。omniroute ladder 實測值 `STREAM_READINESS_TIMEOUT_MS=20000` / `MAX_TIMEOUT_MS=30000`，6×30s=180s < 280s，算術本來就合。
真正原因：**每個 target 實際吃 60–80s**，遠超 readiness 上限 —— readiness timeout 只管「多久算沒 ready」，stream 一旦建立但沒吐首 token 就不受它管。

```
01:24:03  Trying model 2/6: nvidia/deepseek-v4-pro
01:25:23  Trying model 3/6: openrouter/nemotron-3-ultra   (+80s)
01:26:26  Trying model 4/6: openrouter/nemotron-3-super   (+63s)
01:27:28  Trying model 5/6: openrouter/north-mini-code    (+62s)
```
4 步燒掉 205s，第 5 步一開撞 280s。**fallback 本身正常，NIM 也健康**。

### 修法

`strip-proxy/server.mjs` —— 把「等 headers」轉成「等 SSE 事件」：

1. 收到 request 立刻 `writeHead(200, {'content-type':'text/event-stream'})` + `flushHeaders()`
2. 立刻送 `response.created`，**必須帶完整 `response` 物件**，否則 codex 直接丟棄
3. 等上游期間每 20s 送 `data: {"type":"ping"}\n\n`
4. 上游 headers 一到就 **disarm ping**，並用 `stripFirstResponseCreatedEvent()` 濾掉上游那筆重複的 `response.created`
5. L29 預設 `100_000 → 540_000`；plist `RESPONSES_UPSTREAM_HEADER_TIMEOUT_MS` / `RESPONSES_CLIENT_EVENT_DEADLINE_MS` 都 `280000 → 540000`
6. `config.toml` `request_max_retries 1→4`、`stream_max_retries 1→5`（官方預設；`(1/1)` 就是這裡來的）

## §2 層 2：臃腫層 — tool schema 75307 chars 全展開

根因**不是** MCP 裝太多，是 **model slug 讓 codex 走 fallback metadata**：

```
codex_models_manager::model_info ... get_model_info{model="free-tools-heavy"}:
  Unknown model free-tools-heavy is used. This will use fallback model metadata.
```
`logs_2.sqlite` 出現 **80 次**，全庫 `defer_loading` 命中 = **0**
→ `supports_search_tool: false` → tool_search 從未觸發 → 25 個 namespace schema 全展開 = 75307 chars ≈ 19k tokens。

`codex debug models` 顯示**所有**官方 slug 都 `supports_search_tool=true`，base_instructions 長度差很多：
```
gpt-5.4        12879 chars   ← 選這個（fallback 用的是 21.6KB）
gpt-5.4-mini   11097
gpt-5.6-sol    16299
gpt-5.5        19737
gpt-5.2        21544
```

### 修法

`~/.local/share/happy-codex-fts/bin/codex` 第 9 行：
```diff
-    -c 'model="free-tools-heavy"' \
+    -c 'model="gpt-5.4"' \
```
strip-proxy `pinFtsRequestModel()` 會把不在 `FTS_ALLOWED_MODEL_PREFIXES = ['free-tools','combo/','openrouter/','nvidia/']` 的 slug 改寫回 `free-tools-heavy` 再送 omniroute → 上游不受影響。

**配套**：加 `FTS_EXPECTED_CLIENT_MODEL`（預設 `gpt-5.4`），pin 時 `from` 等於它就只 log 不記 anomaly —— 否則每個 turn 灌一筆 `fts-model-pin` 進 `anomalies.jsonl`，洗爆 anomaly count、誤導 harness。

`config.toml` 九個瘦身 key（實測 `prompt-input` **31259 → 2185 bytes**）：
```toml
skills.include_instructions      = false   # -17984 chars（最大宗）
include_permissions_instructions = false   # -3882
include_apps_instructions        = false   # -646
include_environment_context      = false   # -410
web_search                       = "disabled"
[features]
tool_suggest = false   # -998    plugins = false   # -1014
multi_agent  = false   # -7047   goals   = false   # -3034
```
⚠️ `include_*` 四個 key 官方 reference 沒收錄（binary `ConfigToml` 裡有，實測有效）→ 升版後用 `codex debug prompt-input` 重驗。

## §3 層 3：判定層 — 模型自評放水（最隱蔽）

session `019fb105-467c-7d13-a051-756e3fe8e0f3` 以 `task_complete` + 完整訊息收尾，自稱「**Plan 全驗收通過**」，實際：固定前綴只 63683→57756（驗收線 <30000）、半數修法沒做。

**這不是報錯暫停**，層 1 修好也治不到。且 `harness-poll-fts.mjs` 的 `hasSuccessfulSelfCheck()` 只做關鍵字 regex（有「PASS/驗收」且無「FAIL」就算過），正好被這種輸出騙倒。

### 修法：Stop hook 驗收閘門

`secret-cheeragent/hooks/fts-acceptance-gate.js`，掛 `~/.codex/hooks.json` 的 `Stop` 第 3 條。

codex Stop hook schema（反編譯 0.144.5 binary）：
```
input : cwd, hook_event_name:"Stop", last_assistant_message, session_id,
        stop_hook_active(bool), transcript_path, turn_id
output: continue, decision("block"), reason(必填), stopReason, suppressOutput, systemMessage
```
回 `{"decision":"block","reason":"..."}` 就能讓 codex 不停、把 reason 當下一輪訊息繼續跑。

判定四層：
- **L0** 只在 `transcript_path` 含 `/.codex-fts/` 時生效，其他 codex session 不碰
- **L1** 有 `t0.sh` → 實跑（`spawnSync` timeout 120s）拿 exit code；非 0 就 block，reason 貼**實際失敗輸出最後 15 行**（空泛 reason 會讓 agent 空轉重試）
- **L2** 無 t0.sh 但 `last_assistant_message` 含自評成功字樣 → block，要求逐條貼實跑指令與原始輸出
- **L3** 同 session nudge 上限 2，第 3 次 forced-pass + `doctor-needed`；內部錯誤一律 fail-open

## §3.5 層 4：circuit breaker 自殘（實測撞到）

`server.mjs` L2208 原設定：
```js
'responses-empty-completed': { windowMs: 5*60*1000, threshold: 1, breakMs: 10*60*1000 },
```

**單次**空回應就開 **10 分鐘** circuit。實測時間軸：
```
05:21:31.923  responses-empty-completed: output_chars=0 has_tool_signal=false
05:21:31.924  harness-circuit-open: type=responses-empty-completed count=1 breakMs=600000
05:21:32.122  harness-circuit-block: request blocked     ← 之後 5 次 retry 全被自己擋死
```
codex 的 `stream_max_retries=5` **全部撞在自己的 circuit 上**，turn 直接死。
免費池偶發吐空是常態（07-29 18:32、07-30 03:23 都有，早於任何 patch），鎖 10 分鐘等於自殘。

### 修法
```js
'responses-empty-completed': {
  windowMs: Number(process.env.CIRCUIT_EMPTY_WINDOW_MS || 5 * 60 * 1000),
  threshold: Number(process.env.CIRCUIT_EMPTY_THRESHOLD || 2),   // 1 → 2
  breakMs: Number(process.env.CIRCUIT_EMPTY_BREAK_MS || 90 * 1000),  // 600s → 90s
},
```
連續 2 次才開、只鎖 90s（夠上游輪替），三個值都可用 env 覆寫。

## §4 踩過的坑（重要）

1. **SSE comment (`: ping`) 保活無效** — codex 用 `eventsource_stream`，comment 依 spec 被丟棄、不 yield item，idle timer 照樣觸發。**必須送帶 `type` 的真 JSON 事件**（未知 type 走 `Ok(None)` 靜默忽略且會重置 idle timer）。

2. **ping 必須在進 pipe 階段停** — 否則上游真卡死也不會被 90s idle watchdog 砍，比原 bug 更糟。實作用 `stop()`（永久 latch）+ `disarmPing()`（可逆，5xx 重試要 re-arm）。

3. **`last_agent_message` 只由 `response.output_item.done` 填** — `response.completed` 的 `output` 陣列 codex **完全不讀**（`sse/responses.rs` 只讀 id/usage/end_turn）。內容塞在 completed 裡會得到「無錯誤、null 訊息」，這是第二條 null 路徑。

4. **★ codex hook trust：新 hook 靜默永不執行** — binary strings：`"New hook - review required"`、`"1 hook needs review before it can run."`、enum `Managed|Untrusted|Trusted`、config 欄位 `bypass_hook_trust`。
   `[hooks.state]` key 格式 `<hooks.json路徑>:<event>:<index>:<subindex>`。新增第 3 條 Stop hook → 新 key `stop:2:0` 無 trusted_hash → **無頭環境下靜默跳過，不報錯**。

   **正解（不用開 `bypass_hook_trust`、不用逆 hash 演算法）**：用 app-server JSON-RPC 讓 codex 自己算 hash，抄進 config.toml。
   ```js
   // 起 app-server（stdio），initialize 後發：
   {"jsonrpc":"2.0","id":2,"method":"hooks/list","params":{"cwd":"/Users/51mini"}}
   // 回傳每條 hook 的 key / currentHash / trustStatus
   // 把 untrusted 那條的 currentHash 寫成 [hooks.state."<key>"] trusted_hash = "<currentHash>"
   ```
   手動暴力猜 hash 輸入格式**試過 48 種變體全不中**（cmd 字串、加換行、JSON 序列化各種 sep/sort、路徑前綴、`\0`/`|`/`:` 分隔…），不要浪費時間逆，直接問 codex。

4.5 **★★ hook 載入範圍：`$CODEX_HOME/hooks.json` 是 user-level（全 cwd），`<cwd>/.codex/hooks.json` 是 project-local（恰好等於 cwd 才算）**

⚠️ 本節初版寫成「`~/.codex/hooks.json` 是 project-local 且不向下繼承，所以 cheeragent/mem0 在子目錄 session 都沒在跑」—— **那是錯的，已更正**。

錯誤來源：探測時用 `CODEX_HOME=~/.codex-fts` 跑 `hooks/list`，這種情境下 `~/.codex/hooks.json` 不是 user-level 檔（user-level 是 `~/.codex-fts/hooks.json`），只在 cwd 恰好 = `/Users/51mini` 時被當成 project-local 命中。把探測 artifact 讀成了機制。

**兩次實測對照**（同一份 `~/.codex/hooks.json`）：

`CODEX_HOME=~/.codex-fts`（fts 情境，`~/.codex/hooks.json` 只能走 project-local）：
```
/Users/51mini                       hooks=7  source=project   ← cwd 恰好命中
/Users/51mini/NovelVault            hooks=0
/Users/51mini/omniroute-free-tools  hooks=0
```

`CODEX_HOME=~/.codex`（正常 codex，同一檔變成 user-level）：
```
/Users/51mini                       hooks=12  source=user,plugin  全部載入
/Users/51mini/NovelVault            hooks=12  source=user,plugin  全部載入
/Users/51mini/omniroute-free-tools  hooks=12  source=user,plugin  全部載入
/Users/51mini/dev                   hooks=12  source=user,plugin  全部載入
```

→ **cheeragent / mem0 / rtk 在正常 codex session 一直是好的**（6 支 user hook 全 `trusted`）。壞的只有兩件事：

(a) **claude-mem plugin 的 5 支 hook 全 `modified`**（`pre_tool_use` / `post_tool_use` / `session_start` / `user_prompt_submit` / `stop`）—— plugin 升版後 command 字串變了，`[hooks.state]` 裡的 `trusted_hash` 沒跟著更新 → 靜默不執行。要重發 hash 才會恢復。

(b) **fts session（`CODEX_HOME=~/.codex-fts`）只載入自己那份 hooks.json**，`~/.codex/hooks.json` 完全吃不到。想讓 cheeragent 在 fts 也生效必須複製一份進 `~/.codex-fts/hooks.json`。已做，內容：
```json
{"hooks":{
  "PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"/opt/homebrew/bin/rtk hook claude"}]},
                {"hooks":[{"type":"command","command":"node ~/secret-cheeragent/hooks/pretool_inject.js"}]}],
  "SessionStart":[{"hooks":[{"type":"command","command":"node ~/secret-cheeragent/hooks/sessionstart.js"}]}],
  "Stop":[{"hooks":[{"type":"command","command":"node ~/secret-cheeragent/hooks/fts-acceptance-gate.js"}]},
          {"hooks":[{"type":"command","command":"node ~/secret-cheeragent/hooks/capture.js"}]}]}}
```
（實際檔案寫絕對路徑；gate 放 `stop:0:0` 讓它先於 capture.js 跑，因為它可能 block。）

**加項會位移 index → 舊 `trusted_hash` key 失效 → hook 靜默變 untrusted。** 每次改 hooks.json 都要重跑 `hooks/list` 對一次 `trustStatus`。實測 hash 只是 command 字串的函數（同一 command 在 `~/.codex` 與 `~/.codex-fts` 得到相同 hash），但 **key 綁 index**，所以位移必補。

**mem0 不搬**：它的 command 內嵌明文 `MEM0_API_KEY=m0-...` 寫在 `~/.codex/hooks.json` 裡（違反「key 一律存 .env」）。搬過去等於複製 secret，先把 key 移進 `.env` 讓 hook 讀 env var 才能搬。

遷移對 prefix 零成本：`codex debug prompt-input "hi" | wc -c` 遷移前後都是 **2185**（在無 AGENTS.md 的 cwd 量。在 `/Users/51mini` 量會得 8946，因為 `~/AGENTS.md` 6574 chars 作為 project-doc 疊上去 —— **量 prefix 一定要固定 cwd**，否則兩次數字沒有可比性）。

端到端實測：`hook: Stop Blocked` 出現，codex 收到 reason 後真的回頭跑 t0.sh、讀失敗行、開始修 —— 不再靜默停止。

5. **early-stream 後上游回非 SSE（4xx JSON）會炸掉 proxy 進程** — 兩處無條件 `writeHead` 丟 `ERR_HTTP_HEADERS_SENT`。必須加 `!res.headersSent` 守衛 + 把 JSON error 轉成 SSE failure event。

6. **`.includes` 判自評會誤傷誠實回報** — 「Plan 全部完成但還有一項未驗」含「全部完成」。加 `HONEST_CAVEAT_PATTERNS`（`未驗證`/`⚠️`/`BLOCKED`/`未完成`/`待驗`…）逃生門。

7. **`findT0Script` 上溯太多層會撈到別任務的 t0.sh** — 收窄成 cwd 本身無條件 + 上溯 1 層且該層須同時有 `ACCEPTANCE.md`。

8. **codex_apps 判定兩隻 agent 相反** — 一說內建不可控，一說走標準 MCP `connection_manager`（`new{server_name=codex_apps}` → `start_server_task` → `initialize`）故 `disabled_tools` 可能有效。**未實測**。層 2 修好後這條不重要。

9. **`codex debug prompt-input` 不含 tool schema** — 它只有注入文字。量 tool schema 要看 `~/.omniroute/call_logs/<date>/*.json` 的實際 request body。

10. **`codex exec` 缺 `OMNIROUTE_API_KEY` 會直接 ERROR** — 但 strip-proxy 不驗 key（smoke test 用 `Bearer test` 就通），所以 `OMNIROUTE_API_KEY=dummy-for-local-proxy` 即可跑驗收，不必碰真 secret。

## §5 驗收（實測數字）

| 項 | 基準 | 結果 |
|---|---|---|
| `codex debug prompt-input "hi" \| wc -c` | 31259 | **2185** ✅ |
| 一次 turn tokens used | 63683 | **8674** ✅ 省 86% |
| tool schema chars / 支數 | 75307 / 25 | **11844 / 10** ✅ |
| `has tool_search` in request | False | **True** ✅ |
| `Unknown model gpt-5.4` | — | **0 筆** ✅ |
| `response.created` 立即送出 + 去重只一筆 | — | ✅ |
| ping 時間軸（造 45s 慢上游） | — | ✅ `+20s`/`+40s`，headers 到達後**無第三筆** |
| `response.output_item.done` 有送 | — | ✅ |
| 真實流量 `responses-early-stream-open ping_ms=20000` | — | ✅ |
| plist 540s + `maxConcurrent: 2` | — | ✅ |
| gate 六情境（含誠實警語逃生門、nudge 上限） | — | ✅ 全對 |
| `stop:2:0` trustStatus | untrusted | **trusted** ✅ |
| combo 順序 / fallback / NIM 健康 | — | ✅ 本來就正常 |

驗收指令：
```bash
CODEX_HOME=~/.codex-fts codex debug prompt-input "hi" | wc -c
OMNIROUTE_API_KEY=dummy-for-local-proxy CODEX_HOME=~/.codex-fts codex exec -c 'model="gpt-5.4"' --skip-git-repo-check "回覆一個字：ok"
ls -t ~/.omniroute/call_logs/$(date +%F)/ | head -1   # 看 tools 陣列 chars 與 has tool_search
grep -a -o "Unknown model [a-z0-9.-]*" ~/.codex-fts/logs_2.sqlite | sort | uniq -c
tail ~/.codex-fts/acceptance-gate.log
```

## §6 hook 生態整併 + slug 缺口（2026-07-30 下午）

### 6.1 ★★ wrapper 的 `-c model="gpt-5.4"` 只覆蓋 `app-server`，其他入口全走肥 schema

`~/.local/share/happy-codex-fts/bin/codex` 只在 `[ "$1" = "app-server" ]` 時注入 `-c`，其餘 `exec /opt/homebrew/bin/codex "$@"`。所以 `codex exec`、`codex debug`、任何非 app-server 路徑仍讀 `config.toml` 的 `model = "free-tools-heavy"` → `Unknown model` → fallback metadata → `supports_search_tool: false` → tool schema 全展開。

實測同一個 `codex exec 'run: echo ...'`：

| | slug 在 config.toml 修好前 | 修好後 |
|---|---|---|
| tools | 15 支 / **47185 chars** | 10 支 / **11228 chars** |
| upstream `tokens.in` | **43887** | **6607** |
| codex 自報 tokens used | 44161 | 13194 |

**正解：把 slug 寫進 `config.toml` 而不是只靠 wrapper。**
```toml
model                          = "gpt-5.4"          # 原 "free-tools-heavy"
model_auto_compact_token_limit = 120000             # 原 212000，與 wrapper 對齊
tool_output_token_limit        = 6000               # 原 16384，與 wrapper 對齊
```
strip-proxy 照樣 pin 回 `free-tools-heavy`（`FTS_EXPECTED_CLIENT_MODEL='gpt-5.4'` 讓它不記 anomaly）。

教訓：**wrapper 只能保證它自己那條路徑。** 驗收若只用 app-server 測，這種缺口驗不出來 —— 必須用 `codex exec` 另測一次。

### 6.2 mem0 兩支 hook 是死的（指向不存在的腳本 + 明文 key）

`~/.codex/hooks.json` 的 `SessionStart[1]` / `Stop[1]`：
```
MEM0_API_KEY=m0-<明文> MEM0_USER_ID=51mini node /Users/51mini/mem0-hooks/session-start.js
```
`/Users/51mini/mem0-hooks/` **不存在**（`find ~ -maxdepth 2 -iname "*mem0*"` 零命中）→ 一直靜默失敗。已移除兩條，明文 key 隨之清除。

### 6.3 claude-mem 在 codex 兩邊都沒在跑，成本被我高估了

`~/.codex/config.toml` 早有 claude-mem 的 `[hooks.state]` 條目（授信過），但 plugin 升到 13.12.4 後 command 字串變了 → 5 支全 `modified` → 靜默不執行。

**實測成本**（直接餵 payload 給 hook，量 stdout）：

| hook | 輸出 | token | 頻率 |
|---|---|---|---|
| `SessionStart` context | 2254 chars | ≈560 | 每 session |
| `UserPromptSubmit` session-init | 880 chars（semantic match ×1，`SEMANTIC_INJECT_LIMIT=1`） | ≈220 | 每 prompt |
| `PreToolUse` file-context | `{"continue":true}` | 0 | codex 下空轉 → **不授信** |
| `PostToolUse` observation | `{"continue":true}` | 0 | 每 tool call，實測 **~175 ms** |
| `Stop` summarize | 只寫 DB | 0 | 每 turn（走 `CLAUDE_MEM_MODEL=claude-sonnet-4-6` + `AUTH_METHOD=cli` → **吃 Claude 額度**，`TIER_ROUTING` 把簡單的丟 haiku） |

它是**省 token 的**（自報 `6368t read / 258508t work / 98% savings`）。真成本是 175ms/tool-call 與 Stop 的 LLM 呼叫，不是 prefix。

### 6.4 fts 要 claude-mem 不必打開 plugins —— 用 shim 當 user hook

fts 有 `[features] plugins = false`（為砍 `plugins_instructions`），plugin hook 一支都不載入。**不要為此把 plugins 打開**，改把 4 支註冊成 user hook。

但 plugin 原命令自己解析路徑：掃 `$CLAUDE_CONFIG_DIR/plugins/cache/thedotmack/claude-mem/<ver>/` 或讀 `CLAUDE_PLUGIN_ROOT`。**兩者在 user hook 情境都不成立**（沒有 plugin root 注入；本機安裝在 `cache/claude-mem-local/claude-mem/<ver>/`）。所以寫了 shim `~/.local/bin/claude-mem-codex-hook.sh`：

```sh
ROOT=$(ls -d "$HOME"/.codex*/plugins/cache/*/claude-mem/*/ 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || { echo '{"continue":true}'; exit 0; }     # fail-open，絕不擋 codex
CLAUDE_MEM_CODEX_HOOK=1 exec node "${ROOT}scripts/bun-runner.js" "${ROOT}scripts/worker-service.cjs" hook codex "$1"
```
`sort -V` 處理 13.9.0 < 13.12.4；跨 `.codex` / `.codex-fts` 都掃，升版免改。

最終 `~/.codex-fts/hooks.json`（Stop 順序讓 gate 先跑，因為它會 block）：
```
SessionStart      [cheeragent sessionstart, cmem context]
UserPromptSubmit  [cmem session-init]
PreToolUse        [rtk(Bash), cheeragent pretool_inject]
PostToolUse       [cmem observation]
Stop              [fts-acceptance-gate, cheeragent capture, cmem summarize]
```

### 6.5 授信自動化：別手寫 hash

`scratchpad/grant.mjs` —— `hooks/list` RPC 撈 `currentHash`，逐 key 寫/更新 `[hooks.state]`，支援 skip 清單（把 `pre_tool_use` 故意留 untrusted）。**stale hash 要用 regex 取代而非追加**，否則 TOML 出現重複 section。

驗收（`hooks/list`，cwd=NovelVault）：fts **9/9 trusted**；正常 codex **9 trusted + 1 故意 untrusted**（claude-mem `pre_tool_use`）。

端到端 `codex exec`：`SessionStart ×2 / UserPromptSubmit / PreToolUse ×2 / PostToolUse / Stop ×3` 全觸發，`user_prompts` 與 `sdk_sessions` 都有 fts session id（`019fb246`、`019fb249`）。trivial `echo` turn 沒產 observation（內容太少），屬預期。

### 6.6 已知殘留

- **`rtk hook claude` stdout 全空 → codex 報 `PreToolUse Failed`**。它 exit=0、工作有做，純 cosmetic。`~/.codex` 與 `~/.codex-fts` 兩邊同樣行為，非遷移造成。
- **兩個 skill 缺 frontmatter 已停用**（改名 `SKILL.md.disabled`）：`hermes-system-prompt-architecture`（整份是 LLM 回覆連 ```markdown 圍籬一起存檔）、`cai-kangyong`（純缺 frontmatter）。真內容都在，想救就把外殼剝掉。
- **`~/.codex-fts/AGENTS.md` 曾有 heredoc 殘留**（`AGENTS_EOF` + `wc -c ~/...` 兩行漏進內容），已刪。用 heredoc 寫檔後要回讀確認尾巴。

### 6.7 ★★ live session 的 slug 不讀 config.toml/wrapper —— happy dist 寫死 + 每輪覆寫

§6.1 把 `config.toml` slug 改成 `gpt-5.4`，但**手機開的 live session 仍跑 `free-tools-heavy`**（rollout meta `model: free-tools-heavy`、`input_tokens 44241` 肥）。

根因：happy 對 codex 的 model **不讀 config.toml、不讀 env**，是 dist bundle 寫死的常數，每個 turn 當 per-turn override 送進 app-server → 蓋掉 config.toml 與 wrapper 的 `-c model=`。

```
~/.local/share/happy-codex-fts/releases/20260728121959/happy/dist/index-Cji64kS2.mjs:10062
const DEFAULT_CODEX_MODEL = "free-tools-heavy";   // 只有手機每則訊息 meta.model 能覆寫
```

- 入口 `dist/index.mjs` import `Cji64kS2` chunk（count 1）；全 dist 只此一處定義 `DEFAULT_CODEX_MODEL`，無其他 slug 來源。
- `10191`/`10196` 的 reset 引用同一常數，改一處全跟。
- 證據：三個相鄰 session，`gpt-5.4` 那兩個 `input≈6.8k`；`free-tools-heavy` 那個 `input=44241`。

**修法**：`free-tools-heavy` → `gpt-5.4`，`node --check` 過。**生效時機**：happy 每 session 是新 node 進程 launch 時讀檔 → 下次重開 fts 生效；跑著的 daemon 記憶體舊值不變。

⚠️ **升級坑**：這是改 vendored dist（release 目錄帶版號 `20260728121959`）。**happy 一升版就被新 bundle 覆蓋，patch 消失要重打。** 重打步驟：新 release 目錄下 `grep -rn 'DEFAULT_CODEX_MODEL = ' dist/` 找那一行，同樣替換。

**瘦 slug 副作用補償**：`gpt-5.4` 走 `supports_search_tool: true` → MCP 工具延遲載入，初始清單 10 支（`exec_command`/`write_stdin`/`update_plan`/`apply_patch`/`view_image`/`request_user_input`/3 支 mcp resource + `tool_search`）。已在 `~/.codex/AGENTS.md`（fts symlink 共用）加「# 工具發現」節。

**驗收（2026-07-30 18:18 session `019fb288`，patch 後重開）**：

| 項 | 結果 |
|---|---|
| rollout `turn_context.model` | ✅ `gpt-5.4`（三個 turn 都是） |
| `input_tokens` | ✅ 9954 → 10218（cached 8704）；vs 舊 44241 |
| tool 可達性 | ⚠️ 見下 |

⚠️ **第二坑：`tool_search` 是原生 tool call，不是 shell 指令。** 加了 AGENTS.md 指示後模型照做，但做成 `exec_command {"cmd":"tool_search happy__change_title"}` → `zsh:1: command not found: tool_search`，然後照樣回「我沒有 `functions.happy__change_title` 這個工具」。

`tool_search` 的 description（4083 chars）尾端列出 deferred 來源，**`- happy` 確實在裡面**（連同 market-data / markitdown / mem0 / obsidian / repomix / smart_connections）→ `change_title` 拿得到，純粹是模型不會叫。AGENTS.md 已改成明寫「原生工具呼叫，禁止用 `exec_command` 跑」+ 列出可查的 server 名。這條對弱模型（nemotron 系）特別必要。

### 6.8 ★★★ NIM `verbosity` 400 → 托底吐空 → turn 被停（真正讓人「連正常回覆都不行」的那個）

症狀是 codex 端兩行紅字：

```
Codex error: stream disconnected before completion: FTS
Codex Responses stream completed with no assistant output or tool call.
strip-proxy stopped the turn defensively; start a new fts Codex session and retry.
```

`app.log` 現場（每個 turn 都重演一次）：

```
11:07:49 [ERROR] [400]: Validation: Unsupported parameter(s): `verbosity`
11:07:49 ProxyEgress nvidia/69a315e9  status=error      ← ladder 第一棒每次 400
11:07:50 ProxyEgress openrouter/fbc913e1 status=success ← 掉到托底，但零輸出
11:07:50 anomaly: responses-empty-completed             ← strip-proxy 防禦性停 turn
```

**因果鏈**：`gpt-5.4` slug 的 model metadata 有 `support_verbosity` → codex 送 `verbosity`（或 `text.verbosity`）→ NVIDIA NIM 不吃這參數，直接 400 → fallback 到 openrouter 那棒回 `completed` 但 output 空 → strip-proxy 記 `responses-empty-completed` 並停 turn。

**修法**（`strip-proxy/server.mjs`，`pinFtsRequestModel` 內，`node --check` 過）：

```js
// 放在 isFtsAllowedModel 早退出之前，否則 gpt-5.4 這條路剝不到
let strippedVerbosity = false;
if ('verbosity' in parsed) { delete parsed.verbosity; strippedVerbosity = true; }
if (parsed.text && typeof parsed.text === 'object' && 'verbosity' in parsed.text) {
  delete parsed.text.verbosity; strippedVerbosity = true;
}
if (isFtsAllowedModel(parsed.model)) {
  if (strippedVerbosity) return { body: Buffer.from(JSON.stringify(parsed)), rewroteFrom: null, stream, model: parsed.model };
  return { body: requestBody, rewroteFrom: null, stream, model: parsed.model };
}
```
沒剝到就回原 buffer，不多做序列化。pin 那條路本來就重新 serialize，自動帶到。生效要 `launchctl kickstart -k gui/501/com.royalskynet.freetools-stripproxy`（**不要** bootout）。

⚠️ **歸因教訓**：這個 400 從 10:19 就在 log 裡，但當時在追 slug/tool schema，沒回頭看 `app.log`。症狀「session 突然全掛」出現時，先看 `app.log` 的 ladder 逐棒狀態，別預設是自己剛改的東西。（`responses-empty-completed` 的時間戳早於本次 config 改動 → 立刻排除自己。）

**未修的相鄰問題**：托底棒 `openrouter/fbc913e1` 回 `success` 卻零輸出。NIM 修好後多數 turn 不碰它，但它該不該留在 ladder 是獨立議題。

### 6.9 瘦 slug 的 tool 可達性：`apps=false` 有效、`tool_search=false` 無效、prompt 完全治不了

想讓 `happy__change_title` 在瘦 slug 下可達，試了三層，只有一層有效：

| 手段 | 官方收錄 | 實測 |
|---|---|---|
| AGENTS.md 教「先 `tool_search` 查」 | — | **無效**。session A 把它當 shell 跑（`zsh:1: command not found: tool_search`）；session B 連試都沒試直接回「不存在」。規則確認有注入（injected text 第 629 字元起） |
| `[features] apps = false` | ✅ | **有效**。deferred 來源 8 server → 只剩 `- happy`；tools schema **11873 → 8208 chars** |
| `[features] tool_search = false` | ❌ 僅存在於 binary strings | **無效**。`tool_search` 工具照在、happy 照樣延遲。推測 flag 被 slug 的 `supports_search_tool: true` 蓋過 |
| `tool_search_always_defer_mcp_tools = false` | ❌ 同上 | 未驗完（撞上 §6.8 停機）→ 已回滾 |

官方 config 文件位置：`docs/config.md` 只是 stub，實體在 `https://learn.chatgpt.com/docs/config-file/config-reference`（`developers.openai.com/codex/config-reference` 會 308 過去）。那裡有 `features.apps`、`mcp_servers.<id>.enabled` / `enabled_tools` / `disabled_tools`，**沒有** 任何 `tool_search` 相關 key。

判別「哪些 server 被 deferred」的最快法：讀 `~/.omniroute/call_logs/<date>/` 最新 json 的 `requestBody.tools`，找 `type: "tool_search"` 那筆的 description 尾端清單。注意 `~/.codex`（market-data/mem0/obsidian/repomix/smart_connections）與 `~/.codex-fts`（只有 happy）清單不同 —— 可以用它反推這筆 log 是哪個 CODEX_HOME 發的。

**現況結論**：`change_title` 在瘦 slug 下仍不可達，代價換來 prefix 44k → ~8k。判斷是划算的，不再投入（硬救的路只剩改 happy dist 注入自家 tool，或退回肥 slug）。

### 6.10 `fts new` 假成功：`script` 收到 stdin EOF，session 立即退出

**Symptom:** `fts new` 回報 `已開新 fts codex session (pid=...)`，但 `~/.happy/logs/fts-new-*.log` 只有 `^D`，或 Happy daemon list 短暫出現新 session 後 PID 查不到。新 session 無法穩定從手機端接管。

**Root cause:** `~/.local/bin/fts` 用：

```bash
nohup /usr/bin/script -q /dev/null "$happy" codex --yolo </dev/null >"$log" 2>&1 &
```

headless 下 `</dev/null` 讓 `script(1)` 建好偽 TTY 後立即收到 EOF。`happy-codex-fts codex` 可能已註冊 session，但 wrapper / app-server 隨後退出，daemon list 會留下 stale 記錄。

**Fix:** 保持 stdin 存活，讓 `script` 的 PTY 不收到 EOF：

```bash
nohup /bin/sh -c 'tail -f /dev/null | /usr/bin/script -q /dev/null "$1" codex --yolo' sh "$happy" >"$log" 2>&1 &
```

**Verify:** `bash -n ~/.local/bin/fts` 通過；用新啟動方式產生的 `pid-*.log` 看到 `Session created/loaded`、`[happyMCP] server:ready`、`[CodexAppServer] Connected and initialized`、`[MessageQueue2] Waiting for messages...`。

### 6.11 `script` 保 stdin 仍不夠：改用 tmux 當 detached 宿主

**Symptom:** 手機端 Happy app 對新開 FTS session 傳訊無反應。`daemon list` 已不含該 session；daemon log：

```text
[DAEMON RUN] Registered externally-started session cms7t3wh...
[DAEMON RUN] Removing stale session with PID 45790 (process no longer exists)
```

**Root cause:** §6.10 的 `tail -f /dev/null | script ...` 能讓 session 註冊並初始化到 `Waiting for messages...`，但 `script` 宿主仍會在 daemon stale cleanup 前退出。Happy daemon 追蹤的是 `hostPid`，host 死後就移除 session，手機端傳訊沒有路由目標。

**Fix:** `~/.local/bin/fts new` 改用 tmux：

```bash
session="fts-codex-$ts"
tmux_bin=$(command -v tmux || true)
"$tmux_bin" new-session -d -s "$session" "exec \"$happy\" codex --yolo >>\"$log\" 2>&1"
```

**Verify:** 手動 tmux 啟動 `cms7t9cjety1xwc0uctgblool`，等待超過 40s stale cleanup 後：

```text
daemon list 仍含 cms7t9cjety1xwc0uctgblool pid=48404
tmux list-sessions 仍含 fts-codex-20260731-015202
ps -p 48404 顯示 happy/dist/index.mjs codex --yolo 存活
```

### 6.12 session 活著但傳訊無回應：卡在 MCP startup，模型請求根本沒送出

**Symptom:** Happy app 對新 FTS session 傳訊後無回應。session/PID/tmux 都活，local MCP port 也在 listen，但 10 分鐘後 log 出現：

```text
[WARN] [CodexAppServer] Turn timed out after 600000ms — treating as abort
```

`strip-proxy /_proxy/status` 的 `ftsUpstreamQueue.lastStartAt` 沒更新，OmniRoute app.log 也沒有新請求。

**Root cause:** 問題在 Codex 本地層，不在模型/OmniRoute。`2026-07-31-09-01-52` rollout 對應的 Happy log 顯示 turn 開始後啟動多個 MCP；其中 `repomix` 只有：

```text
mcpServer startup status: { name: 'repomix', status: 'starting' }
```

後續沒有 `ready` 也沒有 `failed`。Codex 等 MCP startup，永遠沒送出 Responses request，最後 Happy wrapper 600s timeout。`node_repl` / `openspace` 會明確 failed，非主因；`repomix` 是卡死點。

**Fix:** FTS channel 不載入外部 MCP。`~/.local/bin/happy-codex-fts` 在 `codex` 子命令後附加：

```bash
-c mcp_servers.market-data.enabled=false
-c mcp_servers.markitdown.enabled=false
-c mcp_servers.mem0.enabled=false
-c mcp_servers.node_repl.enabled=false
-c mcp_servers.obsidian.enabled=false
-c mcp_servers.openspace.enabled=false
-c mcp_servers.repomix.enabled=false
-c mcp_servers.smart_connections.enabled=false
```

`codex mcp remove` 不是正解：它回報 removed，但 `codex mcp list` 仍顯示這些 server enabled，因為來源是 `~/.codex/config.toml`，而不是 `~/.codex-fts/config.toml`。啟動層 `-c` 覆寫實測有效。

**Verify:** `CODEX_HOME=/Users/51mini/.codex-fts codex mcp list -c ...` 顯示 8 個 server 全 `disabled`。重開 `cms893pf9pk09yc0ts2nykot8`，等待超過 40s stale cleanup 後仍在 daemon list；`ps -p 27055` 顯示啟動參數包含所有 MCP disable 覆寫。
