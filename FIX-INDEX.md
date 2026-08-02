# FIX-INDEX

Personal bug runbook — symptom → fix lookup, adr-tools style.

## Quick start

```bash
fixindex find "<symptom keyword>"   # match frontmatter `symptoms:` across fix files
fixindex show 0001                  # cat fixes/0001-*.md
fixindex list                       # all entries
fixindex grep "<keyword>"           # full-text ripgrep including bodies
fixindex new <slug>                 # scaffold next-numbered fix file
fixindex re-index                   # regenerate the directory table below (idempotent)
fixindex supersede <old> <new>      # mark old superseded by new
```

Each fix lives in `fixes/NNNN-<slug>.md` with a YAML frontmatter (`id / slug / title / tags / symptoms[] / status / supersedes[] / related[]`) and one or more `## §N {title}` sections shaped as **Symptom / Root cause / Fix / Verify / Retrospective** (Retrospective optional — record only when there is a lesson worth carrying forward).

## Directory

<!-- fixindex:table:start -->
| ID | Slug | Title | Tags |
|----|------|-------|------|
| 0001 | coco-monday-weekly-schedule-night-shift-notify | TODO |  |
| 0002 | omniroute-fts-tail-nim-fallback | OmniRoute FTS combo tail NIM fallback | omniroute, fts, combo, nvidia-nim, launchd, timeout, readiness |
| 0003 | heath-bot-silent-pkill-missed-rescue | Heath bot 靜默 20 天 — pkill 廣域 pattern 誤殺後漏救 |  |
| 0004 | fts-dispatch-not-in-slash-menu | "fts codex `/dispatch` 不出現在斜線選單——prompt 放在 Happy 不掃的目錄" | "codex-fts", "happy", "dispatch", "skill-system" |
| 0005 | codex-novelvault-agents-integration | TODO |  |
| 0006 | mini-power-failure-vdd-boost-uvlo | Mini 突然斷電重啟 — 供電壓降 UVLO |  |
| 0007 | cheeragent-hook-tailread-pregen | "cheeragent hook 效能優化 — tail-read + background pregen" | "cheeragent", "hook", "performance", "node" |
| 0008 | --help | TODO |  |
| 0009 | fts-codex-timeout-prefill-bloat | "FTS Codex 停止：header timeout（協定層）+ 75k tool schema（臃腫層）+ 自評放水（判定層）" | fts, codex, omniroute, strip-proxy, timeout, tool_search, hooks, hook-trust, claude-mem, mem0, skills |
| 0010 | fts-harness-continue-needed-loop | FTS harness poll 無限 continue-needed、監控空轉、context 無人守門 | fts, harness, codex, launchd, strip-proxy, stop-hook, poll |
| 0011 | fts-harness-layer-stall-coverage | FTS session 宣告下一步後停擺、HL 三層全數空轉 | fts, harness, codex, stop-hook, goals, poll, launchd, bash |
| 0012 | fts-harness-selfheal-online | FTS harness 自癒閉環上線 — 假警報止血、空轉 turn 偵測、doctor/layer1.8 啟用 | fts, harness, launchd, telegram, acceptance-gate, opencode, codex, self-heal |
| 0013 | novelvault-migo-cleanup | TODO |  |
| 0014 | opencode-dispatch-protocol | opencode 派工協定 — argv 吞旗標掛死、stdin + --format json 串流監控 | opencode, dispatch, mannie, yargs, observability, harness |
| 0015 | hermes-send-profile-identity | hermes send 用錯 bot 身分 — 切 profile 的變數是 HERMES_HOME 不是 HERMES_PROFILE | hermes,telegram,profile,send,mannie,koko,identity |
| 0016 | agent-selfreport-file-vs-effect | 派工方自報「做完了」但只改了檔案沒讓它生效 — 驗收條文含指令就必須真的執行 | dispatch,acceptance,mannie,hermes,d1,cloudflare,migration,self-report |
| 0017 | fts-context-compaction-loop | FTS context compaction — OmniRoute 免費池實測可用；HL 加 context 壓力監控與 compact-failed 止血 | fts, codex, compaction, context-window, harness, omniroute, observability |
| 0018 | launchctl-bootstrap-race | launchctl bootout 後立即 bootstrap 發生 race | macos, launchctl, launchagent, hermes |
| 0019 | mannie-agent-reach-skill-exposure | Mannie 看不到已安裝的 Agent Reach | mannie, hermes, agent-reach, skills |
| 0020 | twitter-cli-search-timeout | twitter-cli search timeout／HTTP 404 — 未登入首頁使 ClientTransaction 初始化失敗 | twitter-cli, agent-reach, mannie, graphql, client-transaction, timeout |
| 0021 | omniroute-claude-heavy-ab | OmniRoute Claude Heavy 純官方 A/B 分流 | omniroute, claude-code, heavy, profile, gateway |
| 0022 | heavy-hl-degenerate-circuit | Heavy HL agentic 退化、OmniRoute round-robin 飄移與 NIM 本機 queue timeout | omniroute, claude-code, heavy-hl, openrouter, nvidia-nim, circuit-breaker, launchd |
| 0023 | omniroute-dual-lane-rate-limit | OmniRoute NIM/OR 集中消耗、短冷卻重探與 ALL_ACCOUNTS_INACTIVE | omniroute, hermes, nvidia-nim, openrouter, rate-limit, routing |
| 0024 | mannie-compression-dead-model | Hermes 壓縮模型下架導致壓縮完全停擺、主模型 context 被 probe-down 猜錯 | hermes, mannie, compression, openrouter, omniroute, auxiliary, context-length |
| 0025 | omniroute-anomalyidcounter-runtime-crash | TODO |  |
| 0026 | launchd-env-var-expansion-empty-string | TODO |  |
| 0027 | fail-open-static-checker | TODO |  |
| 0028 | mannie-silent-amnesia-compression-chain | Agent 靜默失憶：壓縮鏈五重複合失效（context 砍半 + target_ratio 語意誤解 + 摘要模型過慢 + fallback 死路 + 靜默丟中段） | hermes, mannie, compression, context, auxiliary, fallback, omniroute, lsp, mcp, toolset |
| 0029 | mannie-lsp-symbol-tools-complete | LSP Symbol Tools 完整實作 (A1-A3) — client.py + manager.py + lsp_tool.py + toolsets.py | lsp, hermes-agent, symbol-navigation, fixindex |
| 0030 | lsp-symbol-tools-local-patch-reapply | LSP Symbol Tools Local Patch 重貼流程 (A7) | lsp, hermes-agent, local-patch, fixindex |
| 0031 | goal-lost-on-compression | /goal 標準目標在 context 壓縮後消失（session_id 沒搬 meta） | hermes-agent, goal, compression, mannie |
| 0032 | max-iterations-no-continuation | 撞 max_iterations 後任務直接斷掉，沒有任何自動續跑 | hermes-agent, goal, max_iterations, continuation, mannie |
| 0033 | approval-timeout-iteration-budget | Approval-timeout iterations burned budget silently; compression failures didn't distinguish timeout vs malformed response | mannie, hermes-agent, iteration-budget, context-compressor, approval |
<!-- fixindex:table:end -->

> Empty after `fixindex new <slug>` — see [docs/example-session.md](docs/example-session.md) for sample fixes.

## Adding entries

- **Same domain, new symptom:** append a `## §N` section to the matching fix file and add the symptom string to its frontmatter `symptoms:` array — that's what `fixindex find` scans.
- **New domain (≥3 expected entries):** `fixindex new <slug>` to scaffold + auto-bump the ID.
- **Deprecate:** `fixindex supersede <old> <new>` — flips `status:` to `superseded` and records the back-link; never delete the file.
