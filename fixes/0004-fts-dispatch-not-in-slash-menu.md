---
id: 0004
slug: fts-dispatch-not-in-slash-menu
title: "fts codex `/dispatch` 不出現在斜線選單——prompt 放在 Happy 不掃的目錄"
tags: ["codex-fts", "happy", "dispatch", "skill-system"]
symptoms: ["/dispatch not in slash menu", "prompts/dispatch.md exists but not picked up", "Happy discoverCodexSkillCommands only scans skills/ .agents/skills/ plugins/cache/", "斜線選單沒有 dispatch"]
status: active
supersedes: []
related: []
---
# 0004 fts-dispatch-not-in-slash-menu

## §1 `/dispatch` 不出現在 fts codex 斜線選單
**Symptom:** `/dispatch` 已定義在 `~/.codex-fts/prompts/dispatch.md`，但 fts codex 斜線選單（`/`）不出現此指令。
**Root cause:** Happy（fts codex 的 UI 層）透過 `discoverCodexSkillCommands()` 掃描斜線指令，來源僅三處：
1. `<cwd>/.agents/skills`
2. `<CODEX_HOME>/skills`
3. `<CODEX_HOME>/plugins/cache`

遞迴找 `SKILL.md`，指令名 = 父目錄名。完全**不讀 `<CODEX_HOME>/prompts/`**。`prompts/` 僅 Native Codex TUI 使用，fts(Happy) 不認。
**Fix:**
1. 建 `/Users/51mini/.codex-fts/skills/dispatch/SKILL.md`（frontmatter `name: dispatch` + 原 body）
2. 刪 `/Users/51mini/.codex-fts/prompts/dispatch.md`（避免兩處漂移）
**Verify:**
- `test -f $CODEX_HOME/skills/dispatch/SKILL.md` → PASS
- `test ! -f $CODEX_HOME/prompts/dispatch.md` → PASS
- Happy `discoverCodexSkillCommands` 掃描範圍含 `skills/` → 下次啟動會重掃
- 終端驗收：重啟 fts session，打 `/` 可見 `dispatch`。
