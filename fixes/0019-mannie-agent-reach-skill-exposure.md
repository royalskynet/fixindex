---
id: 0019
slug: mannie-agent-reach-skill-exposure
title: Mannie 看不到已安裝的 Agent Reach
tags: [mannie, hermes, agent-reach, skills]
symptoms:
  - "Mannie 說沒有 agent-reach，但本機其實已安裝"
  - "agent-reach CLI 可執行，Mannie 的 skills_list 卻沒有 agent-reach"
  - "Mannie 執行 agent-reach doctor 與 twitter feed 連續 timeout，卡住數分鐘"
status: active
supersedes: []
related: []
---
# 0019 mannie-agent-reach-skill-exposure

## §1 將全域 Agent Reach 暴露給 Mannie profile
**Symptom:** 本機 `/Users/51mini/.local/bin/agent-reach` 與 `~/.agents/skills/agent-reach/` 均存在，`agent-reach doctor --json` 正常，但 Mannie 的 `skills_list` 找不到 `agent-reach`。
**Root cause:** Agent Reach 標準 installer 只辨識 `~/.agents/skills`、OpenClaw、Claude Code 等目錄，不會自動寫入 Hermes 的 profile-local `~/.hermes/profiles/mannie/skills/`。
**Fix:** 將完整 `~/.agents/skills/agent-reach/`（含 `SKILL.md` 與 `references/`）複製到 `~/.hermes/profiles/mannie/skills/agent-reach/`，再執行 `hermes --profile mannie gateway restart`。不要改用 Hermes registry 的同名 community 版本；該版本可能落後於本機已驗證版本。
**Verify:** `hermes --profile mannie skills list --source local --enabled-only` 顯示 `agent-reach | local | enabled`；以不帶 `--skills` 的一般搜尋請求執行 `hermes --profile mannie chat`，日誌出現 `skill_view completed` 與 `terminal completed`，回覆末尾確認實際載入 `agent-reach`。

## §2 Twitter CLI 在 Mannie daemon 環境連續 timeout
**Symptom:** 互動 shell 執行 `agent-reach doctor --json` 與 `twitter feed -n 1` 約 1–3 秒完成；Mannie terminal 依序出現 15、60、45 秒 timeout，並嘗試不存在的 `opencli`，整輪耗時 276 秒。
**Root cause:** Twitter credentials 只存在互動 shell／`~/.agent-reach/twitter-env.sh`，Mannie gateway profile `.env` 沒有 `TWITTER_AUTH_TOKEN` 與 `TWITTER_CT0`。同時 Agent Reach 的 Twitter 重試鏈沒有 agent terminal 的總時間上限，也未要求先確認 OpenCLI 是否存在。
**Fix:** 安全同步既有兩個 Twitter credentials 到 `~/.hermes/profiles/mannie/.env`（權限維持 `600`）並重啟 Mannie gateway。更新全域與 Mannie profile 的 `agent-reach/references/social.md`：doctor／Twitter 命令每次最多 12 秒；一次 timeout 即切路；使用 OpenCLI 前先 `command -v opencli`；熱門趨勢不得以首頁 feed 冒充，改走 X trending 頁或 Trends24／Brave。
**Verify:** profile 環境下 `agent-reach doctor --json` 3.58 秒成功、`twitter status` 1.39 秒且 `ok: true`、`twitter feed -n 1` 2.28 秒成功。Mannie 端到端 session `20260731_171349_723421` 自動載入 `agent-reach`，doctor terminal 3.21 秒、feed terminal 1.70 秒，無 timeout。
