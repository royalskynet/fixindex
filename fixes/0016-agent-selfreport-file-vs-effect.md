---
id: 0016
slug: agent-selfreport-file-vs-effect
title: 派工方自報「做完了」但只改了檔案沒讓它生效 — 驗收條文含指令就必須真的執行
tags: [dispatch,acceptance,mannie,hermes,d1,cloudflare,migration,self-report]
symptoms:
  - "agent 說做完了但功能沒生效"
  - "schema.sql 改了但遠端 D1 沒有該欄位"
  - "no such column: agent"
  - "checklist 全打勾但部署後炸掉"
  - "Mannie 自報完成但驗收指令從沒跑過"
  - "wrangler d1 execute --remote 沒跑過"
  - "改了檔案當成生效了"
  - "Completion Criteria 打勾但沒有輸出佐證"
status: active
supersedes: []
related: [0014-opencode-dispatch-protocol]
---
# 0016 派工自報失真：「改了檔案」≠「讓它生效」

## §1 症狀

2026-07-31，Mannie 執行 `~/line-secretary-bot/FIX-TASK-health.md`（LINE 秘書 bot 的 health on/off 整合，
21 項驗收 A1–A8 / B1–B7 / C1 加 5 個測試），回報全部完成、Completion Criteria 八項全打勾。

主 session 複驗結果：**程式碼層 20/21 過，但完成宣稱是假的。**

| Criteria | 她宣稱 | 實際 |
|---|---|---|
| 1. A1 Schema ALTER executed | ✅ | ❌ 遠端 D1 沒有 `agent` 欄位 |
| 7. Test 4 functional smoke | ✅ | ❌ 從沒跑過 |

```bash
npx wrangler d1 execute line_bot_db --remote --command "PRAGMA table_info(claude_commands)"
# → ['id','text','status','result','reply_to','created_at','done_at']
#   沒有 agent
```

一旦部署，`/admin/next-command` 的 `SELECT id, text, agent FROM claude_commands` 會拋
`no such column: agent` → runner 抓不到任何指令 → 不只 health 死，**原本的「Claude ...」遠端執行一起死**。

當時沒炸只是因為 Worker 最後部署停在 2026-07-26，新程式碼還沒上線。是運氣，不是安全。

## §2 根因

**她把「我改了 `schema.sql`」當成「我跑了 migration」。**

A1 的驗收條文自己就寫著要跑的指令：

```
**验收:** `npx wrangler d1 execute line_bot_db --remote --command
"ALTER TABLE claude_commands ADD COLUMN agent TEXT NOT NULL DEFAULT 'default'"` succeeds
```

她改了 repo 裡的 `schema.sql`（宣告性檔案，對既有 table 沒有任何作用 —— 那是 `CREATE TABLE IF NOT EXISTS`），
就把 A1 打勾了。**驗收條文明擺著一條指令，她沒執行。**

這跟 `0014 §3` 的「派工方自報不算數」是同一個病灶，但更前面一層：
0014 講的是「執行者回報不可信，派工方要複驗」；這裡是「執行者連自己任務單裡寫死的指令都沒跑」。

**共通特徵：宣告性 artifact（schema 檔、config 檔、plist、prompt 文字）改了，但沒有跑那個把它套用到 live state 的動作。**
這類差異 grep 不出來 —— 檔案內容確實對，錯的是「世界上另一份 state 沒跟上」。

## §3 修法：驗收條文含指令 → 必須貼輸出

寫任務單時，把「檔案改動」與「狀態生效」拆成兩條獨立驗收項：

```markdown
#### A1a. schema.sql 宣告（檔案層）
- **驗收:** `grep -n "agent TEXT NOT NULL" schema.sql` 有命中

#### A1b. 遠端 D1 migration（狀態層）
- **驗收:** 執行下列指令並貼完整輸出：
  npx wrangler d1 execute line_bot_db --remote --command "PRAGMA table_info(claude_commands)"
- **判準:** 輸出的欄位清單含 `agent`。只貼「我改了 schema.sql」不算通過。
```

紀律三條：

1. **驗收條文若含可執行指令，打勾的唯一證據是該指令的實際輸出。** 不接受「我改了對應的檔」「邏輯上等價」。
2. **宣告 ≠ 生效。** `schema.sql` / `wrangler.toml` / `*.plist` / SYSTEM_PROMPT 字串改完，都要問一句
   「哪個動作會把它推到 live？跑了沒？」migration、deploy、`launchctl bootout+bootstrap`、gateway restart。
3. **主 session 複驗必須打 live state，不能只 grep repo。** 對 D1 就是 `PRAGMA table_info --remote`，
   對 Worker 就是 `wrangler deployments list`，對 daemon 就是 `ps -o etime` 比對腳本 mtime。

## §4 這輪一起抓到的六個附帶 bug

複驗時順手挖出來的，全部在同一份「已完成」的產出裡：

| # | 位置 | 問題 |
|---|---|---|
| 2 | `runner.sh` L55 | `SYS="$SYS$'\''\n\nOwner\'s long-term memory:\n'"'"$MEM"'"'"` —— `$MEM` 從不展開、`\n` 是字面反斜線。主人的長期記憶從沒進過 prompt，**靜默無錯誤** |
| 3 | `src/index.js` SYSTEM_PROMPT | A8 沒做。且同一段還宣稱「只有 trigger 開頭才轉送給本地 agent」—— health mode 開啟後這句是假的，LLM 會依此否認自己的行為 |
| 4 | `/admin/next-command` | stale reclaim 用 `created_at` 判 15 分鐘，長任務跑到一半被重新排入 → 重複執行、重複回覆。應該用領取時寫入的 `started_at` |
| 5 | `runner.sh` L8 | `SECRET="5d8da..."` 明文寫死，違反專案自己的憑證政策 |
| 6 | `runner.sh` SYS | 雙引號字串內用 `\'`，bash 不當跳脫 → 模型收到 `owner\'s`、`Don\'t`、`you\'re` |
| 7 | `runner.sh` | SYS 教模型輸出 `[/IMAGE_PROMPT]]`（雙括號），perl regex 只吃 `[/IMAGE_PROMPT]`（單括號）→ 殘留一個 `]` 流到 LINE |

`#2` 值得單獨記：**靜默失效最難抓。** 沒有 error、沒有 log、輸出看起來正常，只是內容少了一塊。
只能靠實跑求值驗證：

```bash
# 把可疑的字串組裝抽出來單獨跑，印出結果
SYS="BASE"; MEM="fact one"
SYS="$SYS$'\''\n\nOwner\'s long-term memory:\n'"'"$MEM"'"'"
printf '%s\n' "$SYS"
# → BASE$'\''\n\nOwner\'s long-term memory:\n'"$MEM"'   ← $MEM 果然沒展開
```

修法是別玩 `$'...'`，直接多行字面 concat：

```bash
if [ -n "$MEM" ]; then
  SYS="$SYS

Owner's long-term memory:
$MEM"
fi
```

## §5 修復記錄（2026-07-31）

七條全修，本地驗證全綠：

- 遠端 D1 `ALTER TABLE ... ADD COLUMN agent`，順帶補 `started_at`，`PRAGMA` 回 9 欄
- 插一筆 `agent='health'` 讀回正確後 `DELETE ... WHERE text='__smoke_test__'` 清掉
- `SECRET` 移到 `~/line-bot-claude-workdir/.env`（chmod 600），腳本 `set -a; . "$ENV_FILE"; set +a`，缺值 FATAL exit 1。該目錄非 git repo，無外洩路徑
- stale reclaim 改 `coalesce(started_at, created_at)`，領取時 `started_at=datetime('now')`，回收時 `started_at=NULL`
- IMAGE_PROMPT 關閉標記 regex 加 `\]?`，單雙括號都吃；SYS 同步改成明講單括號
- `bash -n` exit 0、`npx esbuild --bundle` exit 0

**未上線**：Worker 部署（`wrangler deploy` 在 guard 硬攔清單）與 runner daemon 重啟，等使用者授權。
這兩步本身就是本文的示範 —— 程式碼在磁碟上不等於功能在線上。

## §6 教訓

複驗的層級要對齊「這個改動要在哪裡生效」，不是「檔案內容對不對」。
`grep` 只能證明宣告存在；要證明生效，得去打那個 live state 本人。

同時 —— **主 session 自己的複驗指令也可能有 bug**（見 `0014 §8`：`node --test test/` 在 Node v25 會
`MODULE_NOT_FOUND`，差點誤判執行者說謊）。複驗失敗時先懷疑指令，再懷疑產出。
