---
id: 0015
slug: hermes-send-profile-identity
title: hermes send 用錯 bot 身分 — 切 profile 的變數是 HERMES_HOME 不是 HERMES_PROFILE
tags: [hermes,telegram,profile,send,mannie,koko,identity]
symptoms:
  - "hermes send 用錯 bot 身分發出"
  - "HERMES_PROFILE=xxx hermes send 無效"
  - "訊息傳到 koko 而不是指定 profile"
  - "你傳錯傳到 coco 了"
  - "hermes send 回 sent 但身分錯"
  - "HERMES_HOME fallback"
  - "hermes 頂層沒有 -p/--profile"
  - "fixindex 寫進 memory/fixes 但索引不到"
status: active
supersedes: []
related: [0259-mannie-real-commands]
---
# 0015 hermes send profile 身分

## §1 `hermes send` 用錯 bot 身分 — `HERMES_PROFILE` 不是切換旗標

**Symptom**
要用 Mannie 身分把任務單發到 Telegram DM：
```bash
HERMES_PROFILE=mannie hermes send --to telegram:7852197786 --file /path/task.md
# → sent
```
回 `sent`，但訊息是 **Koko 的 bot** 發出去的。使用者：「你傳錯傳到 coco 了」。

**Root cause**
兩個獨立事實疊起來：

1. `HERMES_PROFILE` **不是** profile 切換旗標。全 repo 只有 kanban 用它，語意是「task/comment 的 author 名」
   （`tools/kanban_tools.py:623`、`hermes_cli/kanban.py:502`）。`hermes send` 完全不看它。
2. 真正的切換是 `HERMES_HOME`（`hermes_constants.py: get_hermes_home()`）。未設時**回退 `~/.hermes` 根**，
   而根目錄就是 Koko 的資料 → 讀到 Koko 的 `.env` / bot token。

`~/.hermes/active_profile` 寫著 `koko` 也救不了 —— `get_hermes_home()` 明確不吃 sticky profile，
fallback 時只寫一行警告，而且**只進 `errors.log`，CLI 前景完全看不到**
（原始碼註解：raise 會 brick 30+ 個 module-level caller）。所以現象是「靜默成功、身分錯掉」。

`hermes` 頂層也沒有 `-p/--profile` 全域旗標；`--profile` 只存在於 gateway / launchd plist。

**Fix**
```bash
HERMES_HOME=/Users/51mini/.hermes/profiles/mannie \
  hermes send --to telegram:7852197786 --subject "[驗收退回]" --file /path/task.md --json
# → {"success": true, "platform":"telegram", "chat_id":"7852197786", "message_id":"544"}
```
Rule：**任何 `hermes <子命令>` 要指定 profile，一律 `HERMES_HOME=~/.hermes/profiles/<name>` 前綴。**

**Verify**
發送前用同一個 `HERMES_HOME` 跑 dry list：
```bash
HERMES_HOME=/Users/51mini/.hermes/profiles/mannie hermes send --list telegram
# telegram:Ether  [7852197786]   ← 來自 profiles/mannie/channel_directory.json
```
**但這一步不足以分辨身分** —— 不同 profile 常指向同一個 DM chat_id，`--list` 看起來一模一樣。
真差異在各 profile 自己 `.env` 裡的 bot token。`--list` 只驗頻道存在，身分靠 `HERMES_HOME` 釘死。

**代價（不可逆）**
誤發那則以 Koko 身分留在 DM 裡。bot 只能刪自己發的，且要用發它的那個 profile 才刪得掉。
這類「代發身分」是一次性外送，**發之前 `HERMES_HOME` 看兩遍**。

**旁註：`hermes send` 送到 bot 的 DM ≠ 叫得動那個 bot。**
bot 不處理自己發的訊息，`send` 只是把文字貼進聊天室。要 Mannie 真的執行，得是使用者本人在 DM 打
bare command（`code <path>`，見 `0259-mannie-real-commands`，該檔在舊倉），
或本機 `HERMES_HOME=… hermes -z "…"` 直接驅動她的 agent loop。

**來源**：2026-07-31，驗收 Mannie 改的 line-secretary-bot health 整合、要退回修復清單時踩到。

## §2 fixindex 倉庫已搬家 — `memory/fixes/` 是舊倉，寫進去索引不到

**Symptom**
`fixindex list` 只回 14 筆（0001-coco-monday…0014-opencode），但
`~/.claude/projects/-Users-51mini/memory/fixes/` 底下有 190 個檔、且 ID 對不上
（該處 0001 是 `0001-hermes.md`，CLI 的 0001 是 `0001-coco-monday-…`）。
照舊記憶去 append `memory/fixes/0001-hermes.md`，寫完 `fixindex find` **查不到**。

**Root cause**
`~/.zshrc:51` 已 export：
```bash
export FIXINDEX_DIR="$HOME/dev/fixindex/fixes"
export FIXINDEX_INDEX="$HOME/dev/fixindex/FIX-INDEX.md"
```
腳本 `fixes/.bin/fixindex:9` 的 memory 路徑只是**沒有 env 時的預設值**，已被覆蓋。
現役倉是 `~/dev/fixindex`（14 筆，重新編號），`memory/fixes/`（190 筆）是歷史檔案，
CLI 完全不讀。memory 的 `feedback_fixindex.md` 仍寫著舊路徑 —— 已過時。

**Fix**
一律 `cd ~/dev/fixindex` 或直接靠 env；新增走 `fixindex new <slug>`，不要手動挑目錄。
確認當下實際路徑：
```bash
env | grep -i fixindex
bash -x $(which fixindex) grep foo 2>&1 | grep -m1 'rg -i'   # 印出真正掃的檔案清單
```

**Verify**
```bash
fixindex find "HERMES_PROFILE"   # 應命中 0015
```

**來源**：2026-07-31，同一次任務中誤寫舊倉、`fixindex grep` 回空才發現（已 `git checkout` 撤回舊倉那筆）。
