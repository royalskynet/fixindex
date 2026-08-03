---
id: "0006"
slug: hermes-amy-telegram-qmd-skills
title: Hermes Amy Telegram gateway、slash commands、QMD 與全模型存取整合
tags: [hermes, hermes-agent, amy, telegram, gateway, slash-commands, qmd, llm-wiki, skills, openrouter, model-routing, allowlist]
symptoms:
  - "Amy Telegram 收到訊息但沒有回覆"
  - "Telegram bot 顯示 Unauthorized、Blocked unauthorized user 或 polling Conflict"
  - "Telegram slash command 選單沒有 research / audit"
  - "Hermes profile 想查本機 llm-wiki 或 fixindex 知識"
  - "研究與魔鬼代言人 skill 要用簡短指令呼叫"
status: active
supersedes: []
related: ["0005"]
---
# 0006 hermes-amy-telegram-qmd-skills

## §1 Symptom / Root cause / Fix / Verify

**Symptom:** Amy profile 的 Telegram bot 不回覆；slash command 選單看不到 `research`、`audit`；對話無法穩定使用本機知識庫。

**Root cause:**
- Telegram allowlist 若寫成 JSON 字串（例如 `"[\\\"7852197786\\\"]"`），Hermes 不會把它解析成 user ID，訊息會被 `Blocked unauthorized user` 擋下；應使用純數字字串或正確的 YAML list。
- 一個 token 只能由一個 gateway polling；重複 instance 會造成 Telegram `Conflict: terminated by other getUpdates`。
- Hermes Telegram command menu 有數量上限；核心命令先佔滿選單，skill 會被隱藏。應用 `skills.platform_disabled.telegram` 關閉不需要在 Telegram 暴露的 skill，再把 `platforms.telegram.extra.command_menu.max_commands` 提高到合適值。
- skill 是否跟隨模型，取決於是否有獨立 auxiliary/provider override；沒有 override 時，skill 會沿用 Amy 當前 session 的模型路由。

**Fix:**
1. 所有命令顯式指定 `HERMES_HOME=/Users/m2/.hermes/profiles/amy`；token 只放該 profile 的 `.env`，不寫入聊天、log 或 config。
2. `telegram.dm_policy: allowlist` 搭配 `allowed_users`、`allow_from`、`home_chat_id` 使用已核對的 numeric Telegram user ID；改 token/config 後 restart gateway。
3. 在 Amy profile 建立 `research` 與 `audit` 薄 alias skill，分別轉入 canonical `evidence-research-report` 與 `devils-advocate`；Telegram 以 `/research`、`/audit` 呼叫。
4. Telegram 僅保留必要 skill，設定 command menu 上限；向 Bot API 查 `all_private_chats` 與 `all_group_chats` scope，確認兩個命令已發布。客戶端若仍顯示舊選單，重新開啟 Telegram 對話或重啟 app。
5. 在 `SOUL.md` 寫入繁體中文規則，以及遇到 CoinW／風控／AML／OTC／KYC 等問題先用 `qmd query ... -c wiki-llm` 查本機 `llm-wiki`，引用檔名與行號並標記查不到的內容為 `[待核]`。

**Verify:**
```bash
HERMES_HOME=/Users/m2/.hermes/profiles/amy hermes gateway status --deep
HERMES_HOME=/Users/m2/.hermes/profiles/amy hermes gateway list
HERMES_HOME=/Users/m2/.hermes/profiles/amy hermes pairing list
qmd query "<問題>" -c wiki-llm -n 5 --no-rerank --line-numbers
```
Telegram 端必須實測 inbound（本人傳 `ping`）與 outbound（`hermes send --to telegram`）；只看到 process running 不算完成。確認 log 沒有 Unauthorized、Conflict 或 restart loop，且 `getMyCommands` 的 private/group scopes 都包含 `research`、`audit`。

## §2 安全與限制

- 每個 Hermes profile 使用獨立 Telegram bot/token；token 外洩立即在 BotFather `/revoke`，更新 `.env` 後 restart。
- `openrouter/free` 是動態路由，不是固定模型；切換 Amy 的 session/global model 後，沒有獨立 override 的 skill 會跟隨該路由。
- `devils-advocate` 不會憑空宣稱外部模型已完成審查；沒有收到並驗證外部回傳包時，狀態應保持 `PENDING_EXTERNAL_RESPONSE`。
