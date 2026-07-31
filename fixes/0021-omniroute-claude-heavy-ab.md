---
id: 0021
slug: omniroute-claude-heavy-ab
title: OmniRoute Claude Heavy 純官方 A/B 分流
tags: [omniroute, claude-code, heavy, profile, gateway]
symptoms:
  - "Claude 預設設定含非官方 model 與隱形 prompt hooks，無法做可歸因 A/B"
  - "setup-claude --only heavy 同時產生 free-tools-heavy 與 free-tools-heavy-or，無法依唯一名稱選擇"
  - "Happy 開啟 Claude 時需固定走 OmniRoute free-tools-heavy profile"
  - "Happy OmniRoute Heavy session 回覆 You've hit your session limit，OmniRoute 同時間沒有 request"
  - "Happy local probe 走 OmniRoute 成功，但手機 remote turn 仍選 opus 並 hit session limit"
  - "修復後需要開新的 Happy OmniRoute Heavy remote session"
  - "關閉啟動端 PTY 可能連帶終止 Happy Heavy session，需要獨立背景啟動"
  - "Happy Heavy 背景啟動命令需要縮短為 heavy claude"
  - "heavy claude 回 status=starting 且 Happy 看不到新 session，log 顯示 env: node: No such file or directory"
  - "free-tools-heavy 對哈囉回傳 skills 與 system-reminder，發生 prompt leakage"
status: active
supersedes: []
related: []
---
# 0021 omniroute-claude-heavy-ab

## §1 建立可歸因的 Claude 官方／OmniRoute Heavy 分流
**Symptom:** Claude 預設設定含非官方 model 與隱形 prompt hooks，且 `omniroute setup-claude --only heavy --dry-run` 產生兩個 Heavy 候選，不能靠「唯一 heavy」規則選擇。
**Root cause:** `~/.claude/settings.json` 固定 `claude-fable-5[1m]` 並載入 `secret-cheeragent` hooks；現行 OmniRoute catalog 同時公開 `free-tools-heavy` 與 `free-tools-heavy-or`。歷史 request summary 顯示前者是 `comboName`，後者屬 fallback 路由來源。
**Fix:** 備份預設設定，移除固定 model 與 `secret-cheeragent` active hooks；執行 `omniroute setup-claude --only heavy`；建立 `~/.local/bin/claude-heavy`，執行 `omniroute launch --profile free-tools-heavy -- "$@" --model free-tools-heavy`。預設 `claude` 保持 Claude.ai first-party 登入。
**Verify:** `claude auth status` 顯示 `apiProvider=firstParty`；預設設定無 model、gateway env、隱形 hook 路徑；Heavy stream 依序出現 `Write`、`Read`，result success；磁碟內容 exact-byte 比對通過；OmniRoute logs 顯示 `comboName=free-tools-heavy` 且 fallback 後有 HTTP 200。
**Retrospective:** 驗證器需忽略 OmniRoute ANSI/banner 才能解析 stream-json；精確字串可無尾端換行，不應用 `wc -l` 判定內容正確性。

## §2 用 Happy 開啟 OmniRoute Claude Heavy
**Symptom:** 直接執行 `happy` 會使用 Happy 自行解析的 Claude CLI，未保證經過 `claude-heavy` wrapper，因此可能走回 first-party Claude 或其他預設 model。
**Root cause:** Happy 的 Claude launcher 依 `HAPPY_CLAUDE_PATH > PATH > package manager` 順序解析 CLI；單純把 OmniRoute profile 建好，不會自動套用到 Happy session。
**Fix:** 僅對該 session 設定 `HAPPY_CLAUDE_PATH=/Users/51mini/.local/bin/claude-heavy`，再執行 `happy --yolo --no-sandbox --name 'OmniRoute Heavy'`。`claude-heavy` 繼續以 `omniroute launch --profile free-tools-heavy -- "$@"` 傳遞 Happy 注入的 Claude 參數，不修改全域 Happy 或 daemon 設定。
**Verify:** `happy daemon list` 顯示新 direct session；process tree 必須依序出現 `happy → claude_local_launcher.cjs → omniroute launch --profile free-tools-heavy → claude`；Claude 子程序環境顯示 `CLAUDE_CONFIG_DIR=~/.claude/profiles/free-tools-heavy`、`ANTHROPIC_BASE_URL=http://localhost:20128`；Happy log 顯示 `Reported session`、`happyMCP server:ready`、`Socket connected successfully`。
**Retrospective:** Happy 1.1.10 的 `--help` 不公開 `HAPPY_CLAUDE_PATH`，但本機官方 launcher source 明確定義此環境變數為最高優先覆寫點；整合前需讀實作，不能只靠 help 猜 PATH shim。

## §3 Happy Heavy 誤走 Claude OAuth 五小時限額
**Symptom:** 新 Happy session `cms8rs9gzbmtxyc0truy701qm` 回覆 `You've hit your session limit · resets 7:10pm (Asia/Taipei)`；Happy log 是 `rate_limit_event`、`rateLimitType=five_hour`，同時間 OmniRoute call logs 完全沒有 `/v1/messages` request。
**Root cause:** Happy 1.1.10 會把自己的 hook 檔用 `--settings ~/.happy/tmp/hooks/session-hook-*.json` 傳給 Claude，導致 OmniRoute profile 的 model 設定未成為實際選模依據。Happy 又會吃掉使用者提供的 `--model free-tools-heavy`，`--claude-env ANTHROPIC_MODEL=free-tools-heavy` 也未進入最終 Claude env；即使在 wrapper 先 export `ANTHROPIC_MODEL`，`omniroute launch` 仍會清掉它。最後 Claude 選到官方 `claude-opus-4-8`，在送出 HTTP 前被 macOS Keychain OAuth 五小時限額攔截。
**Fix:** 在 `~/.local/bin/claude-heavy` 的最末端、通過 Happy parser 與 OmniRoute env 處理後，強制追加 CLI flag：`exec /opt/homebrew/bin/omniroute launch --profile free-tools-heavy -- "$@" --model free-tools-heavy`。終止錯誤 session 與卡住的 regression probes，再用相同 `HAPPY_CLAUDE_PATH` 啟動新 Happy session。
**Verify:** regression probe 的最終 process argv 顯示 `--settings .../session-hook-*.json --model free-tools-heavy`；OmniRoute call log 出現 `POST /v1/messages`、HTTP `200`、`comboName=free-tools-heavy`、實際 provider `nvidia`、model `deepseek-ai/deepseek-v4-pro`。新常駐 Happy session `cms8s6ehgr063wc0ul2l9782n` 的 Claude argv 同樣以 `--model free-tools-heavy` 結尾，Happy MCP `server:ready` 且 socket connected。
**Retrospective:** 此修法只覆蓋 Happy local launcher。只驗證 local `CLAUDE_CONFIG_DIR`、`ANTHROPIC_BASE_URL`、process tree 或 `--print` probe 不足以證明手機路由成功；手機訊息會切到另一條 remote SDK 路徑，完整修法見 §4。

## §4 Happy 手機 remote mode 繞過 claude-heavy wrapper
**Symptom:** `claude-heavy` local probe 已經在 OmniRoute 回 `200`，但手機送入常駐 Happy session `cms8s6ehgr063wc0ul2l9782n` 仍收到 `You've hit your session limit`。Happy log 顯示 local→remote 切換後 `User message received with no model override, using current: opus`，並另啟動 `@anthropic-ai/claude-agent-sdk-*/claude --model opus`；同時間 OmniRoute 沒有 request。
**Root cause:** Happy 1.1.10 有兩條完全分離的 Claude 路徑。local mode 使用 `HAPPY_CLAUDE_PATH` 與 `claude_local_launcher.cjs`；手機訊息觸發 remote mode 後，`claudeRemoteLauncher` 直接呼叫 bundled Agent SDK。remote SDK 的 `model` 取自 Happy `options.model`，env 只複製 Happy 主程序 `process.env`；不使用 `HAPPY_CLAUDE_PATH`，也不使用 `options.claudeEnvVars`。因此 wrapper、`omniroute launch`、`--claude-env` 對手機 turn 都無效。
**Fix:** 建立 `~/.local/bin/happy-claude-heavy`，在啟動 Happy 主程序前清除 `ANTHROPIC_API_KEY`，export `CLAUDE_CONFIG_DIR=~/.claude/profiles/free-tools-heavy`、`ANTHROPIC_BASE_URL=http://localhost:20128`、`ANTHROPIC_AUTH_TOKEN=${OMNIROUTE_API_KEY:-omniroute-no-auth}`、gateway discovery 與 compact window；再執行 `happy --happy-starting-mode remote --model free-tools-heavy "$@"`。`omniroute-no-auth` 是 OmniRoute 官方 local-open-backend sentinel，來源為 `bin/cli/commands/launch.mjs`，不是憑證。
**Verify:** 先以 Happy bundled Claude binary + 相同 env 跑 `--print --model free-tools-heavy`，OmniRoute 回 `200`、`comboName=free-tools-heavy`。再啟動常駐 session `cms8sbkx6c7tpyc0tg5fw4fya`：Happy 從第一輪即為 remote mode，bundled Claude argv 是 `--model free-tools-heavy`，最終 PID env 有 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、`CLAUDE_CONFIG_DIR`。手機實際 user turn 後 OmniRoute 連續出現兩筆 `/v1/messages` HTTP `200`，provider `nvidia`、model `deepseek-ai/deepseek-v4-pro`，Happy 收到 assistant/tool result 且 `is_error=false`，無 `rate_limit_event`。
**Retrospective:** Happy 整合的驗收單位必須是「手機 remote turn」，不是 local TUI 或 `--print`。看到 local wrapper 正確只能證明 local mode；要追 `loop Iteration with mode`、實際 SDK PID argv/env、手機訊息時間窗內 OmniRoute call log，四者缺一不可。

## §5 修復後開新 Happy Heavy remote session
**Symptom:** remote gateway 修復完成後，需要建立新的乾淨 Happy session，避免續用先前已綁定 `opus`／OAuth 的錯誤 session。
**Root cause:** Happy session 會保存 current model、run mode 與 Claude session metadata；既有錯誤 session 不會因 launcher 修正自動重建。
**Fix:** 執行 `~/.local/bin/happy-claude-heavy --yolo --no-sandbox --name 'OmniRoute Heavy Remote'`，由 launcher 強制 remote mode、`free-tools-heavy` 與 OmniRoute gateway env。舊 session 不自動刪除，除非使用者明確封存或要求停止。
**Verify:** 新 session `cms8seu6ica2kyc0trka99jks` 已向 daemon 註冊；Happy log 顯示 `Reported session`、`happyMCP server:ready`、`Iteration with mode: remote`、`Starting remote launcher`、`Socket connected successfully`。第一則手機訊息到達後仍須依 §4 gate 確認 `using current: free-tools-heavy` 與同時間 OmniRoute `/v1/messages`。
**Retrospective:** 新 session 尚未收到手機訊息時，只能宣稱「remote session ready」，不能宣稱端到端模型 request 已通過；端到端證據需等實際 user turn。

## §6 未來 Happy Heavy session 改由 launchd 獨立背景啟動
**Symptom:** 從 Codex 工具 PTY 或一般終端前景執行 `happy-claude-heavy` 時，Happy session 與呼叫端生命週期綁定；關閉對話、PTY 或 terminal 可能連帶終止 session。
**Root cause:** 原 `~/.local/bin/happy-claude-heavy` 直接 `exec happy`，Happy 主程序仍是呼叫 shell／PTY 的子程序；Happy daemon 只登記 direct session，不負責接管其程序生命週期。
**Fix:** 將原 remote/gateway 啟動內容移至 `~/.local/libexec/happy-claude-heavy-worker`。公開命令 `~/.local/bin/happy-claude-heavy` 支用 `launchctl submit` 建立唯一 label，指定 stdout/stderr log，再由 launchd 啟動 worker；命令輪詢 `happy daemon list`，輸出 `launchd_label`、`log`、`happy_session_id` 與 `status`。終端或 Claude 都可直接呼叫相同命令。既有 session `cms8seu6ica2kyc0trka99jks` 保持原 PID，不做遷移或中止。
**Verify:** 兩個 shell script 均通過 `sh -n`，權限為 executable，檔案無嵌入 API key/token；`launchctl help submit` 確認 `-l/-o/-e -- command` 介面。修改後既有 Happy PID `83963` 仍存活且 daemon list 保留原 session。依使用者要求，本次不額外開測試 session；下一次實際呼叫仍須確認輸出的 launchd label、session ID，以及 §4 remote-turn gate。
**Retrospective:** `launchd` 只解除 session 與啟動端的生命週期綁定，不設定 KeepAlive；使用者正常封存或 session 自行退出時 job 應結束。公開 launcher 與內部 worker 分離，可避免背景提交遞迴呼叫自己。

## §7 對外命令縮短為 heavy claude
**Symptom:** Happy Heavy 背景 launcher 名稱 `happy-claude-heavy` 太長，不利於 Claude 或終端反覆呼叫。
**Root cause:** 對外命令直接暴露內部實作名稱，缺少穩定且簡短的 command dispatcher。
**Fix:** 新增 executable `~/.local/bin/heavy`；`heavy claude [args...]` 以 `exec` 原樣轉送參數至 `~/.local/bin/happy-claude-heavy`。保留官方 `claude` 命令，不覆寫其路由。
**Verify:** `sh -n ~/.local/bin/heavy` 通過；`heavy --help` 顯示 `Usage: heavy claude [happy/claude options...]`；`command -v heavy` 解析為 `/Users/51mini/.local/bin/heavy`。依使用者要求，本次不建立新 session。
**Retrospective:** 短命令只做薄分派，背景生命週期、OmniRoute env 與模型鎖定仍由既有 launcher/worker 單一負責。

## §8 launchd 找不到 Node 導致新 Heavy session 未出現
**Symptom:** 執行 `heavy claude` 後只回 `status=starting`，Happy 看不到新 session；launchd log 反覆顯示 `env: node: No such file or directory`，job exit code `127`。
**Root cause:** `launchctl submit` job 的預設 `PATH` 僅有 `/usr/bin:/bin:/usr/sbin:/sbin`；`/opt/homebrew/bin/happy` 使用 `#!/usr/bin/env node`，因此找不到 Homebrew Node。
**Fix:** 在 `~/.local/libexec/happy-claude-heavy-worker` 明確 export `PATH=/opt/homebrew/bin:/Users/51mini/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`。移除單一失敗 job，再以 `heavy claude --yolo --no-sandbox --name 'OmniRoute Heavy'` 重啟。
**Verify:** launcher 回 `happy_session_id=cms8tv3kmdqyswc0u84046v69`、`status=ready`；`happy daemon list` 可查到 PID `4821`；launchd job 為 `state=running`、`runs=1`、未退出；程序 argv 含 `--happy-starting-mode remote --model free-tools-heavy`，父程序 PID 為 `1`，背景 log 無錯誤。
**Retrospective:** 背景 job 不繼承互動 shell PATH；所有透過 `/usr/bin/env` 找 runtime 的 CLI，worker 必須顯式提供 runtime PATH，不能只驗證 shell 內 `command -v`。

## §9 Heavy 路由發生 prompt leakage，平行改測 Heavy OR Safe
**Symptom:** Happy session `cms901c0klpiuwc0uips9udzz` 對「哈囉」回傳 skills 清單、`Unprocessed user inputs`、grounding 指令與 `system-reminder`，開始胡言亂語。
**Root cause:** `free-tools-heavy` 命中 NVIDIA `deepseek-ai/deepseek-v4-pro`；約 26k-token Claude Code/Happy prompt 與 25 個工具 schema 下，模型直接續寫隱形 prompt。OmniRoute 原始 response 已包含洩漏內容，排除 Happy UI 串流問題。污染有三層：Happy iOS 每則訊息帶 Options XML `appendSystemPrompt`；Happy CLI 再追加 change-title/commit-credit prompt；Claude Code preset 注入 agents、skills 與 `/loop`、ultracode、排程、shell/session 等 system reminders。Happy 1.1.10 remote SDK 不轉送一般 `claudeArgs` 至 query，單加 `--safe-mode` 不足。
**Fix:** 保留問題 session 不動；將未來 `heavy claude` worker切到 `free-tools-heavy-or` profile/model，實驗性 export `CLAUDE_CODE_SAFE_MODE=1`，並保留 `--safe-mode` 供 local 路徑使用。建立平行 session `cms90fzwtzr8cwc0u6h6zvk2j`，名稱 `OmniRoute Heavy OR Safe`。
**Verify:** bundled Claude one-shot 最終回覆 exact `哈囉`；OR step 1 Ultra 550B 空回覆後落 step 2 Nemotron Super。手機 remote turn 則落 step 3 `cohere/north-mini-code:free`，回覆可讀但偏通用。新 remote transcript 仍列 14 skills 與 5 agents，故只能證明 worker env/argv 含 Safe Mode，不能宣稱 Happy SDK remote 已清除 customizations。舊 PID `68050` 與 session 仍存活。
**Retrospective:** 純 A/B 必須固定 route 並實際檢查 SDK init metadata；環境變數存在不等於功能生效。gateway HTTP 200 也不能當品質通過，必須檢查原始 assistant content。

## §10 Heavy OR fallback 正常，但不會判斷語意胡話
**Symptom:** `free-tools-heavy` 已回 prompt leakage，使用者懷疑 OmniRoute fallback／OR model 是否失效。
**Root cause:** fallback 以技術可用性判斷，不做語意品質審核。DeepSeek 的胡話 response 是 HTTP 200、非空 content、`finish_reason=stop`，因此 `free-tools-heavy` 視為成功；`free-tools-heavy-or` 又是獨立 combo，不是前者自動附帶的救援開關。
**Fix:** 本節只調查，未改 route 或 session。若要求模型穩定，應固定單一已驗證 model；若要求最大可用性，才使用 OR combo並接受跨 step 品質漂移。
**Verify:** OR one-shot 的 step 1 `nemotron-3-ultra-550b...:free` 回 HTTP 200 但 content null、0 tokens，隨即改用 step 2 `nemotron-3-super-120b...:free` 完成 title 與主回覆；手機 remote turn實際落 step 3 `cohere/north-mini-code:free`。三者皆由 `comboStepId` 與 gateway raw response確認。
**Retrospective:** 「fallback 正常」只代表能找到可回應 upstream，不代表同一品質、同一模型或不洩漏 prompt；A/B 測試不可把 combo 當固定模型。
