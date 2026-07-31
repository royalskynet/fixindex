# FTS Codex Session 無回應問題整理（2026-07-31）

## 背景

使用者要求新開 FTS Codex session，手機端 Happy app 傳訊後連續遇到兩種「無回應」：

1. session 看似已開，但傳訊完全無反應。
2. 新 session 仍在運轉中，但傳訊後卡 10 分鐘，最後 timeout。

相關主修理日誌：`/Users/51mini/dev/fixindex/fixes/0009-fts-codex-timeout-prefill-bloat.md`

## 問題 1：`fts new` 假成功，session host 很快退出

**症狀**

- `fts new` 回報已開 session。
- Happy daemon 一度出現新 session：`cms7t3whreuh1yc0thzovb9f1`。
- 手機端傳訊無反應。
- daemon log：

```text
[DAEMON RUN] Registered externally-started session cms7t3wh...
[DAEMON RUN] Removing stale session with PID 45790 (process no longer exists)
```

**根因**

`~/.local/bin/fts` 原本用 `script(1)` 建偽 TTY：

```bash
nohup /usr/bin/script -q /dev/null "$happy" codex --yolo </dev/null >"$log" 2>&1 &
```

headless 下 `script` 收到 EOF，或保 stdin 後仍會在 daemon stale cleanup 前退出。Happy daemon 追蹤 `hostPid`，host 死後移除 session，手機端傳訊就沒有路由目標。

**修法**

`~/.local/bin/fts` 改用 `tmux` 當 detached host：

```bash
session="fts-codex-$ts"
"$tmux_bin" new-session -d -s "$session" "exec \"$happy\" codex --yolo >>\"$log\" 2>&1"
```

**驗證**

- `tmux list-sessions` 仍看到 session。
- `daemon list` 等過 40 秒 stale cleanup 後仍含新 Happy session。
- `ps -p <pid>` 顯示 `happy/dist/index.mjs codex --yolo` 存活。

## 問題 2：session 活著但 turn 卡死 600 秒

**症狀**

- 新 session `cms7t9cjety1xwc0uctgblool` 在 daemon list。
- PID `48404` 存活，local MCP port `127.0.0.1:62060` listen。
- 手機端傳訊後無回應。
- Happy log：

```text
[WARN] [CodexAppServer] Turn timed out after 600000ms — treating as abort
```

**關鍵證據**

- Happy log 顯示 `09:01:52` 收到 user message。
- `09:01:53` 已 `turn/start`。
- `strip-proxy /_proxy/status` 沒有新 upstream request，`ftsUpstreamQueue.lastStartAt` 沒更新。
- OmniRoute app.log 沒有新模型請求。

結論：不是模型不回，是 Codex 本地層還沒送出 Responses request。

**根因**

Codex 在 turn 開始時啟動外部 MCP。`repomix` 卡在 startup：

```text
mcpServer startup status: { name: 'repomix', status: 'starting' }
```

後續沒有 `ready`，也沒有 `failed`。Codex 等 MCP startup，模型請求未送出，最後 Happy wrapper 600 秒 timeout。

`node_repl` / `openspace` 會明確 failed，不是主卡點。

## 問題 3：FTS profile 仍讀到 `~/.codex/config.toml` 的 MCP

**症狀**

`CODEX_HOME=/Users/51mini/.codex-fts codex mcp list` 仍顯示這些 MCP enabled：

- `market-data`
- `markitdown`
- `mem0`
- `node_repl`
- `obsidian`
- `openspace`
- `repomix`
- `smart_connections`

**根因**

FTS wrapper 雖然設定：

```bash
export CODEX_HOME="/Users/51mini/.codex-fts"
```

但 `codex mcp list` 仍讀到 `~/.codex/config.toml` 的 `[mcp_servers.*]`。因此 FTS 隔離不完整。

`codex mcp remove <name>` 不是有效修法：命令回報 removed，但 list 仍顯示 enabled。

**修法**

在 `~/.local/bin/happy-codex-fts` 的 `codex` 子命令加啟動層覆寫：

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

**驗證**

覆寫測試：

```bash
CODEX_HOME=/Users/51mini/.codex-fts /opt/homebrew/bin/codex mcp list \
  -c mcp_servers.market-data.enabled=false \
  -c mcp_servers.markitdown.enabled=false \
  -c mcp_servers.mem0.enabled=false \
  -c mcp_servers.node_repl.enabled=false \
  -c mcp_servers.obsidian.enabled=false \
  -c mcp_servers.openspace.enabled=false \
  -c mcp_servers.repomix.enabled=false \
  -c mcp_servers.smart_connections.enabled=false
```

結果：8 個 MCP 全顯示 `disabled`。

新版 session：

- Happy session id：`cms893pf9pk09yc0ts2nykot8`
- PID：`27055`
- tmux：`fts-codex-20260731-091533`
- 過 40 秒 stale cleanup 後仍在 `daemon list`
- `ps -p 27055` 顯示啟動參數包含全部 `mcp_servers.*.enabled=false`

## 當前可用 session

請使用：

```text
cms893pf9pk09yc0ts2nykot8
```

## 後續注意

- FTS channel 目標是低摩擦手機接管與免費池執行，不應啟動 heavy / flaky MCP。
- 若再次「運轉中無回應」，先看 Happy pid log 是否有 `turn/start`，再看是否有模型 upstream request。
- 若 `turn/start` 有、OmniRoute 無請求，優先查 MCP startup/hook 卡住。
- 若 session 不在 daemon list，優先查 daemon log 是否 `Removing stale session with PID`。
