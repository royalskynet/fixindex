---
id: "0001"
slug: lark-meeting-notes
title: lark-meeting-notes / audio-meeting-notes 摘要與 LLM 卡住
tags: [lark, meeting-notes, llm, spawnSync, superpowers, skill-bootstrap, timeout, nvidia-nim, openrouter, env, opt-in, caveman, codex, claude-cli]
symptoms:
  - "UI 按「重新摘要」後轉圈不停，server 無回應"
  - "curl 超時 exit 28"
  - "resummarize 永久卡住、不完成"
  - "spawnSync hang"
  - "摘要區塊變成（摘要失敗：所有 LLM 供應商皆失敗或無憑證）"
  - "claude-cli(訂閱): claude CLI 失敗:（冒號後空白、無 stderr）"
  - "codex CLI 失敗，log 顯示 codex 跑去 sed using-superpowers/SKILL.md"
  - "90s timeout 仍不夠，claude/codex provider 全被 SIGKILL"
  - "OPENROUTER_API_KEY / NVIDIA_API_KEY 不見/為空，免費備援被跳過"
status: active
supersedes: []
related: []
---
# 0001 lark-meeting-notes

lark-meeting-notes / audio-meeting-notes 的 LLM 呼叫與摘要流程問題。

## §1 重新生成摘要（resummarize）永久卡住

**Symptom:** UI 按「重新摘要」後轉圈不停，server 無回應，curl 超時（exit 28）

**Root cause:**
1. `spawnSync` 無 `timeout`，`claude -p` 忽略 SIGTERM → server event loop 永久 block
2. `/resummarize` 先呼 `cleanTranscript`（第一次 LLM），再呼 `summarize`（第二次 LLM），串聯總等待 150s+
3. LLM provider 順序 codex 優先，codex 每次啟動需載入 skill 系統（30s+ overhead）

**Fix:**
- `spawnSync` 加 `timeout: 90_000` + `killSignal: "SIGKILL"`（強殺子進程，SIGTERM 被 claude 忽略）
- 移除 `/resummarize` 中的 `cleanTranscript` 前處理（summarize prompt 本身已有 STT 校正邏輯）
- provider 順序改 `claudeCli` 優先

**Verify:** `curl -X POST http://localhost:7321/resummarize` 在 90s 內回應，不超時

**位置:** `src/llm/router.ts`、`src/server.ts`
**commit:** `8d327ac` (2026-06-11)

## §2 摘要失敗「所有 LLM 供應商皆失敗或無憑證」— skill bootstrap 撐爆 timeout + 免費 API 無 key

**Symptom:** 會議 .md 摘要區塊變成 `（摘要失敗：所有 LLM 供應商皆失敗或無憑證）`，含 `claude-cli(訂閱): claude CLI 失敗:`（冒號後空白）與 `codex-cli(訂閱): codex CLI 失敗`，且 codex 輸出顯示它在跑 `sed ... using-superpowers/SKILL.md`。

**Root cause:**
1. `claude -p` 與 `codex exec` 每次啟動被 SessionStart 強制注入整份 `using-superpowers` skill bootstrap（claude=superpowers plugin hook；codex=`~/.codex/skills` 原生 skill 自動觸發），claude 再疊 caveman/ARS/gsd/lsp hooks，codex 疊 `model_reasoning_effort=xhigh` + AGENTS.md。
2. 載 skill + 大逐字稿（~1.2 萬字）超過 §1 設的 90s timeout → SIGKILL → status≠0 → fail（claude stderr 空 = timeout 特徵）。
3. provider 3/4（OpenRouter / NVIDIA free）的 key 從未持久化（不在任何 .zshrc/.env），`process.env` 空 → `available()` false → 直接跳過，無可用備援。

**Fix:**
- superpowers 自動注入改 **opt-in**（皆在 repo 外）：
  - claude：`~/.claude/plugins/cache/claude-plugins-official/superpowers/<ver>/hooks/session-start` 開頭加 `if [ "${SUPERPOWERS_AUTO:-0}" != "1" ]; then printf '{}\n'; exit 0; fi`（⚠ plugin 升級會覆蓋，需重打）
  - codex：`~/.codex/skills/using-superpowers/SKILL.md` frontmatter `description` 改 opt-in、移除「before ANY response」自動觸發語
- codex 呼叫加 `-c model_reasoning_effort=low`（不動全域 xhigh）
- `spawnSync` timeout 90s→180s
- 補免費備援：`~/lark-meeting-notes/.env` 設 `NVIDIA_API_KEY=`（bun 啟動自動載入；.gitignore 已擋）。端點 `https://integrate.api.nvidia.com/v1/chat/completions`，預設 model `meta/llama-3.3-70b-instruct`

**Verify:** 重啟 `bun run ui`（載 .env + 新 router）→ `curl -X POST localhost:7321/resummarize -d '{"file":"..."}'` 回 `{"ok":true,"provider":"claude-cli(訂閱)"}`，2~3 分內完成、輸出乾淨簡體（caveman **不**污染 `claude -p` 摘要，已實測）。superpowers 仍可手動用 Skill 呼叫。

**位置:** `src/llm/router.ts`（commit `f998931`，branch `fix/summary-provider-overhead`）、`~/lark-meeting-notes/.env`、claude superpowers `session-start` hook、`~/.codex/skills/using-superpowers/SKILL.md`
**related:** §1（同檔 90s timeout 為本次根因之一）
