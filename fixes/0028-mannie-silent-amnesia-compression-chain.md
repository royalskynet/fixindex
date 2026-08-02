---
id: 0028
slug: mannie-silent-amnesia-compression-chain
title: Agent 靜默失憶：壓縮鏈五重複合失效（context 砍半 + target_ratio 語意誤解 + 摘要模型過慢 + fallback 死路 + 靜默丟中段）
tags: [hermes, mannie, compression, context, auxiliary, fallback, omniroute, lsp, mcp, toolset]
symptoms:
  - "agent 自報完成但驗收指令從沒跑過"
  - "long coding session 中途忘記前面決定"
  - "Failed to generate context summary"
  - "context compression started ... tokens=~90,000 反覆觸發"
  - "壓縮耗時 200 秒以上"
  - "auxiliary fallback_chain 走到底全失敗"
  - "auto/best-vision 不保證免費"
status: active
supersedes: []
related: [0024, 0023, 0016, 0019]
---
# 0028 Agent 靜默失憶：壓縮鏈五重複合失效

**適用**：Hermes 任何 profile。以 `mannie` 為實例。與 0024 是**不同根因**（0024 是模型下架 + context probe-down；本篇是 config 值本身把壓縮鏈打殘）。

## §0 為什麼單看一條會誤判

症狀表面是「模型太弱、記不住事」。實際是五條各自看起來無害的設定**疊加**後，把「壓縮失敗」變成「靜默丟棄中段訊息」。單獨檢查任何一條都會得出錯誤結論。**這是 CLAUDE.md「非模型反事實閘門」的教科書案例。**

## §1 `model.context_length` 被人為砍半

**Symptom:** 壓縮觸發點約 90K，遠低於模型實際能力。

**Root cause:** config 寫 `context_length: 128000`，但實際模型（`gemma-4-26b-a4b-it`）支援 `262144`。`~/.hermes/hermes-agent/agent/model_metadata.py:1464-1466` 解析順序第 0 步就是 config override，persistent cache 的正確值被完全忽略。

門檻算式 `agent/context_compressor.py:553`：
```python
self.threshold_tokens = max(int(self.context_length * threshold_percent), MINIMUM_CONTEXT_LENGTH)
```
`128000 × 0.7 = 89,600`。

**Fix:** `context_length: 180000` → threshold `126,000`。

**不拉滿 262144 的理由**：`errors.log` 有 14 次上游 `503 chat_admission_busy`，暗示 OmniRoute 對 request 大小/負載有限制。180000 留安全邊際。

**注意** `model_metadata.py:133` `MINIMUM_CONTEXT_LENGTH = 64_000`。設低於此值 gateway 啟動時 `agent_init.py:1453-1463` 直接 `ValueError`。

## §2 `target_ratio` 語意誤解 —— 是相對 threshold，不是相對總 context

**Symptom:** 每次壓縮後殘留只剩 27K–46K，很快又漲回門檻，壓縮頻繁。

**Root cause:** `context_compressor.py:559-561`：
```python
target_tokens = int(self.threshold_tokens * self.summary_target_ratio)
self.tail_token_budget = target_tokens
```
ratio 乘的是 **threshold**，不是 context_length。`0.2` 只留 `89600 × 0.2 = 17,920` tokens 尾段。

**Fix:** `target_ratio: 0.35`（配 180000 → 尾段 `126000 × 0.35 = 44,100`）。clamp 範圍在 `:536` 是 `[0.10, 0.80]`。

**無效路線 —— `protect_last_n` 不是尾段邊界。** `:1545-1548` 顯示它只餵 `_prune_old_tool_results`，完全不參與摘要尾段計算。調它沒用。

## §3 摘要模型與主模型同一顆

**Symptom:** `started:` → `done:` 實測平均 **219 秒**，且常 502 / timeout。

**Root cause:** `auxiliary.compression.model` 設成與主模型同一顆 free gemma-4-26b。摘要是輕任務，用重模型跑 6.4K token 純浪費。

**Fix:** 換小模型 / 免費 router：
```yaml
auxiliary:
  compression:
    provider: omniroute
    model: auto/best-free
    base_url: http://127.0.0.1:20130/v1
    api_key: omniroute-local
    fallback_chain:
    - {provider: omniroute, model: openrouter/openai/gpt-oss-20b:free, base_url: http://127.0.0.1:20130/v1, api_key: omniroute-local}
    - {provider: omniroute, model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free, ...}
    - {provider: omniroute, model: openrouter/inclusionai/ling-3.0-flash:free, ...}
```

## §4 fallback chain 末端是死路（最關鍵，最難發現）

**Symptom:** 摘要一路 fallback 到底，全部失敗，log 只有 `Failed to generate context summary`。

**Root cause:** chain 末端是付費項：
```yaml
    - provider: nvidia-nim
      model: meta/llama-3.3-70b-instruct
      base_url: https://integrate.api.nvidia.com/v1
      api_key: ${NVIDIA_NIM_API_KEY}
```
**`~/.hermes/.env` 與 profile `.env` 裡根本沒有 `NVIDIA_NIM_API_KEY`**。`config.py:4287 _expand_env_vars` 展開失敗，這條 fallback 就算被觸發也必然失敗。整條鏈是死的。

**Fix:** 刪掉該項。§3 的三條免費 fallback 取代之。同時刪 `custom_providers` 底下已無引用的 `nvidia-nim` / `agnes` 定義（`.env` 的 `AGNES_API_KEY` 不動 —— 只刪 config 引用，不碰 secret 檔）。

**Verify:**
```bash
grep -n "nvidia-nim\|integrate.api.nvidia.com\|NVIDIA_NIM_API_KEY\|agnes" \
     ~/.hermes/profiles/mannie/config.yaml   # 應 0 命中
```

## §5 `abort_on_summary_failure: false` → 靜默丟棄中段

**Symptom:** agent 自報完成、但驗收指令從沒跑過（見 0016）。中段對話憑空消失，agent 自己不知道。

**Root cause:** `context_compressor.py:1640-1655`：摘要全失敗後，若此旗標為 `false`，**直接丟掉中段訊息**，只插一行 placeholder。agent 沒有任何訊號知道自己失憶了。

**Fix:** `abort_on_summary_failure: true`。摘要失敗改為 fail loud（session 中斷）。

**中斷是預期行為，不要一遇中斷就回滾。** 若頻繁中斷，先確認 §3 的免費摘要模型是否真的可用，再考慮回滾此項。靜默失憶才是要消滅的東西。

## §6 觸發點永遠高於理論門檻 —— threshold 是事後檢查

**Symptom:** threshold 算出 89,600，但實測觸發點在 90,291 – 104,076。

**Root cause:** `threshold` 是每輪 turn **結束後**的事後檢查，不是硬上限。單輪塞一個大 tool result（`terminal` / `search_files`）就能從 <89.6K 直接跳到 104K，壓縮在跨過門檻**之後**才觸發。實測值 ≈ 門檻 + 最後一個 tool result 大小。

**影響驗收設計**：驗收條件必須寫「≥ 新門檻且明顯高於舊基線」，不可要求精確等於門檻值。

## §7 `auto/*` router 別名不保證免費（安全陷阱）

**Symptom:** 以為 `auto/best-vision` 這類名稱是免費池。

**Root cause:** OmniRoute 的 `auto/best-vision` / `auto/multimodal` / `auto/vision` / `auto/pro-vision` 的 `owned_by` 都是 **`combo`**，路由池含付費模型，**無 `:free` 保證**。用了等同把「要不要打付費 API」交給路由器決定。

`auto/best-free` 名稱本身約束免費，可安全使用。

**Fix:** 全域零付費約束下，vision 必須指定具體 `:free` 型號。OmniRoute 16 個 `:free` 模型中 `vision: true` 的只有兩顆：
```yaml
  vision:
    model: openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free   # ctx 256,000
    fallback_chain:
    - {provider: omniroute, model: openrouter/nvidia/nemotron-nano-12b-v2-vl:free}   # ctx 128,000
```
**實測 `nemotron-nano-12b-v2-vl:free` 回 502，`nemotron-3-nano-omni` 可用** → 主備順序按實測排，不按 context 大小排。

`_try_configured_fallback_chain`（`auxiliary_client.py:2834`，註解 `:2841`）是泛用函式，vision 也吃 `fallback_chain`，不只 compression。

**Verify:** 掃 `auxiliary` 底下**所有**子項（`vision` / `web_extract` / `skills_hub` / `approval`），不只 `compression`。

## §8 tool schema 開銷：實測後不裁

**實測**（mannie，request dump）：56 tools / **65,686 chars**。
- `browser_*` 佔 **9.3%** —— 低於 25% 行動門檻，**不裁**
- `mcp_*`（github）佔 **27.5%** —— 最大單一來源，但**裁不動**

**`mcp_*` 為何裁不動：** `hermes_cli/tools_config.py:1310-1331` —— `platform_toolsets.<platform>` 若**沒列任何 MCP server 名**，所有 enabled MCP 自動可見；**一旦列了任一個就翻成 allowlist 模式，其他 MCP 全被擋掉**。想單獨關 github 必須把要保留的全部列出來，且此後每加一個 MCP 都要記得補進去。本輪不動。

⚠️ **絕對不要為了「開啟某個 MCP」而把它的名字加進 `platform_toolsets.cli`** —— 那會意外關掉其他所有 MCP。

**統計腳本的正確 JSON 路徑是 `request['body']['tools']`**（不是 `request['tools']`）。

## §9 `hermes mcp add --args` 無法傳多參數

**Symptom:** `hermes --profile X mcp add context7 --command /opt/homebrew/bin/npx --args -y @upstash/context7-mcp` 參數傳不進去。

**Fix:** 直接編 profile `config.yaml` 的 `mcp_servers:`：
```yaml
  context7:
    command: /opt/homebrew/bin/npx
    args:
    - -y
    - '@upstash/context7-mcp'
```
**command 必須絕對路徑** —— gateway daemon 的 PATH 與互動 shell 不同（見 0019 §2），stdio 子行程只繼承 `PATH/HOME/USER/LANG/LC_ALL/TERM/SHELL/TMPDIR/XDG_*`。

**Verify:**
```bash
hermes --profile mannie mcp list                                   # 應顯示 ✓ enabled
tail -5 ~/.hermes/profiles/mannie/logs/mcp-stderr.log              # 應有 "... running on stdio"
```
MCP **無 hot-reload**，改完必須 `hermes --profile <p> gateway restart`。

## §10 LSP 已修 — 見 fixindex 0029（2026-08-02）

`agent/lsp/client.py` 已內建 4 個 LSP symbol 方法（`definition`、`references`、`document_symbols`、`workspace_symbols`）。
補齊項目：
- `agent/lsp/manager.py` — 新增 4 個同步包裝 + 4 個 async 內部方法（A2）
- `tools/lsp_tool.py` — 新建 4 個對外工具 + helpers + `registry.register`（A3）
- `toolsets.py` — 註冊 `lsp` toolset + 加入 `_HERMES_CORE_TOOLS`（A3）

完整記錄：**fixindex 0029-mannie-lsp-symbol-tools-complete**

## §11 無效嘗試（別再走一次）

| 路線 | 為何無效 |
|---|---|
| 調小 `file_read_max_chars` | agent 本來就用 `offset+limit` 精準讀，該閘門近乎從不觸發；且 `tools/file_tools.py:645-661` 是**硬報錯不是截斷**，調小只會造成 read→error→retry 空轉。真正的大 payload 來自 `skill_view`（實測單次 23,959 chars）與 plan markdown，兩者是不同 code path，完全不受此值限制 |
| 調 `protect_last_n` | 只餵 `_prune_old_tool_results`（`:1545`），不影響摘要尾段邊界。真正的旋鈕是 `target_ratio` |
| 引入 Serena / Aider / OpenHands 等外部 coding CLI | 與 SOUL.md「不委派外部 coding CLI」衝突（見 0014）。Hermes 已有 LSP 基礎設施，缺的只是 4 個 request + tool 暴露 |
| 改 `compression.threshold` 去湊 | 見 0024 §2 —— 治標不治本，該修的是 `context_length` |

## §12 驗收與回滾

改前備份：
```bash
cp ~/.hermes/profiles/<p>/config.yaml ~/.hermes/profiles/<p>/config.yaml.bak-$(date +%Y%m%d-%H%M%S)-ctxopt
```

驗收基線（改前必須先量，否則無法比對）：
```bash
L=~/.hermes/profiles/mannie/logs
grep -c "context compression started" $L/agent.log
grep -c "Summary generation was unavailable" $L/agent.log
grep -c "Failed to generate context summary" $L/agent.log
grep "context compression" $L/agent.log | tail -20    # 觸發點 / 殘留 / 耗時
```

**壓縮相關的驗收（觸發點、殘留、耗時、頻率）需要 restart 後產生新壓縮事件才觀察得到。短時間沒有新事件就標「待觀察」並說明需要多久，不得假裝已驗證**（memory `feedback_declaration_vs_effect`）。

`hermes --profile <p> gateway restart` 後用 **PID 對帳**確認真的重啟（見 0024 §3）。注意 restart 會**移除 profile PID 檔但不重建**，以 `ps aux | grep "hermes.*<profile>"` 為準。另：Hermes 會同時跑多個 profile gateway，且 `~/Library/LaunchAgents/ai.hermes.gateway-<p>.plist` 可能是 stale 的（`hermes gateway status` 會警告 `Service definition is stale`）。

`hermes config` **沒有 `get` 子命令**，要看生效值只能讀 config.yaml 或 log。

回滾：
```bash
cp ~/.hermes/profiles/<p>/config.yaml.bak-<stamp>-ctxopt ~/.hermes/profiles/<p>/config.yaml
hermes --profile <p> gateway restart
```

## §13 Retrospective

- **複合失效不會在單點檢查中現形。** 五條裡任何一條單獨看都像小問題，疊起來才變成靜默失憶。遇到「agent 記不住事」先把整條壓縮鏈攤開，不要停在「換個模型」。
- **`${VAR}` 引用的 env var 不存在時是靜默失敗**，config 看起來完全正常。定期對帳 config 裡所有 `${...}` 與 `.env` 實際內容。
- **fail loud 優先於 fail silent。** `abort_on_summary_failure: false` 這種「盡量別打斷使用者」的預設，在 agent 場景下會製造更貴的錯誤。
- **macOS 沒有 `timeout` 指令** —— 腳本裡用會反覆踩到，改用 `gtimeout`（coreutils）或 Python。
