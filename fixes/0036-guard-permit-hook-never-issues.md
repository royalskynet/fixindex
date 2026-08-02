---
id: 0036
slug: guard-permit-hook-never-issues
title: guard permit 機制永遠簽不出票 —— UserPromptSubmit hook 讀了只有 PreToolUse 才有的欄位，heavy-hl 相關操作被永久封死
tags: [claude-code, hooks, guard, launchctl, heavy-hl, permissions]
symptoms:
  - "[GUARD] 已攔截 ... 需授權的受保護操作"
  - "請先透過 UserPromptSubmit 取得授權 nonce"
  - "授權無效或已過期/已用完"
  - 加了 GUARD_OK=1 前綴仍然被擋
  - 使用者已明確授權但 launchctl kickstart heavy-hl 還是不能跑
  - guard-state/ 底下只有測試用 permit 檔，沒有真的簽發過
status: fixed
supersedes: []
related: [0035-strip-proxy-anomaly-jsonl-literal-newline]
---
# 0036 guard-permit-hook-never-issues

> **2026-08-02 已修復。** 初版只抓到一個根因，實際上是**兩個獨立 bug 疊加**外加一個缺件。
> §2 保留初版的錯誤歸因當紀錄，正確版本見 §2b；修法與驗收見 §5b。

## §1 症狀：使用者授權了也沒用，`GUARD_OK=1` 對這類指令無效

```
$ GUARD_OK=1 launchctl kickstart -k gui/501/com.royalskynet.heavy-hl
[GUARD] 已攔截：`GUARD_OK=1 launchctl kickstart -k gui/501/com.royalskynet.heavy-hl` —— 需授權的受保護操作
風險：此操作影響系統關鍵服務，需要使用者明確授權。請先透過 UserPromptSubmit 取得授權 nonce。
```

關鍵是**這類指令跟一般攔截不同**：`GUARD_OK=1` 前綴對它完全無效。`~/.claude/hooks/guard.js` 有兩條獨立路徑：

- `PERMIT_PROTECTED` → 必須有 permit 檔，`GUARD_OK` 不看
- `RULES` → 靠 `GUARD_OK=1` 逃生

命中前者就只能拿 permit，沒有第二條路。

## §2 根因：hook 讀錯 payload 欄位

`~/.claude/hooks/authorization-permit.js` 掛在 **UserPromptSubmit**，但它讀的是 **PreToolUse** 才有的欄位：

```js
const toolName  = payload.tool_name || '';
const toolInput = payload.tool_input || {};
const command   = String(toolInput.command || '');
...
if (toolName !== 'Bash' || !command) {
  return allow();          // ← 永遠命中，直接 return，permit 一張都不簽
}
```

UserPromptSubmit 的 payload 只有 `session_id` / `prompt_id` / `prompt`，**沒有 `tool_name`、沒有 `tool_input`**。所以第一個判斷永遠為真，函式在簽發邏輯之前就返回。

於是 `guard.js:158` 那邊在等一張**永遠不會存在**的票：

```js
if (isPermitProtected(cmd)) {
  if (!consumePermit(sessionId, promptId, cmdHash)) {
    return denyMsg('授權無效或已過期/已用完', ...);
  }
}
```

旁證：`~/.claude/guard-state/` 底下只有 2026-08-01 10:02–10:04 留下的四個檔，session id 是 `session-transcript-test` / `valid-session-123` —— **全是開發當時的測試殘留，從來沒有真實簽發過**。

## §2b 完整根因：兩個獨立 bug + 一個缺件

§2 只寫對其中一個，而且**還不是最先擋住的那一個**。從實際 deny 訊息就能分辨——我們收到的是：

```
需要使用者明確授權。請先透過 UserPromptSubmit 取得授權 nonce。
```

不是另一句「授權無效或已過期/已用完」。前者出自 `if (!sessionId || !promptId)`，代表**連 permit 檢查都沒跑到**。§2 那個簽發端 bug 在更後面，根本輪不到它。

| # | 位置 | Bug |
|---|---|---|
| 1 | `guard.js` `checkBash()` | 讀 `process.env.CLAUDE_SESSION_ID` / `CLAUDE_PROMPT_ID`。**hook 子進程沒有這兩個環境變數**，永遠走 `!sessionId` 的 deny 分支 |
| 2 | `authorization-permit.js` `main()` | 讀 `payload.tool_name` / `payload.tool_input.command`（PreToolUse 欄位），UserPromptSubmit 沒有，永遠提前 return |
| 3 | （缺件） | 完全沒有 stage 1。permit 以 `hashCommand(cmd)` 為 key，簽發端在 UserPromptSubmit 時**無從得知指令字串**，就算 #2 修好也簽不出對得上的票 |

還有兩個次要缺陷：

| # | 位置 | 問題 |
|---|---|---|
| 4 | `getPermitPath()` | permit 檔名綁 `promptId`，但簽票的是**授權那一輪**、消費的是**執行那一輪**，兩個 promptId 必不相同 → 永遠找不到 |
| 5 | `denyMsg()` | 叫 agent「加 `GUARD_OK=1` 前綴重跑」。permit 路徑不吃 `GUARD_OK`，而且加前綴會**改變指令雜湊**，保證對不上。是主動誤導 |

### UserPromptSubmit 的真實 payload（實測，不要再用猜的）

```
keys: ['session_id', 'transcript_path', 'cwd', 'prompt_id',
       'permission_mode', 'hook_event_name', 'prompt']
```

PreToolUse 那邊確認有 `session_id`、`tool_name`、`tool_input`。

**取得方法**：在 hook 開頭把 stdin 原樣 dump 到檔案，跑一次真實對話就有了。修好的版本固定寫 `~/.claude/guard-state/.last-userpromptsubmit.json`，以後不必再猜。

## §3 被封死的指令清單

`guard.js` 的 `PERMIT_PROTECTED`（與 `authorization-permit.js` 的 `PROTECTED_COMMANDS` 內容相同）：

```js
/launchctl\s+(bootout|unload|remove|kickstart)\s+.*heavy-hl/
/launchctl\s+(bootout|unload|remove|kickstart)\s+.*freetools-omniroute/
/pkill\s+.*heavy-hl/
/kill\s+.*heavy-hl/
/sqlite3\s+.*routes\.db\s+.*(DELETE|UPDATE|INSERT)/i
/sqlite3\s+.*control\.db\s+.*(DELETE|UPDATE|INSERT)/i
```

以上六類目前**無法執行，且無論使用者怎麼授權都不行**。

## §4 為什麼 `:20129` 可以、`:20130` 不行

兩個都是 strip-proxy 的 launchd service，同一個 `launchctl kickstart -k`，結果不同：

| 服務 | XPC 名稱 | 是否命中 PERMIT_PROTECTED | 結果 |
|---|---|---|---|
| `:20129` | `com.royalskynet.freetools-stripproxy` | ❌（列的是 `freetools-omniroute`，名字不同） | 走 RULES，`kickstart` 不在 RULES 裡 → **直接放行** |
| `:20130` | `com.royalskynet.heavy-hl` | ✅ | 要 permit → **永久卡住** |

差別純粹在服務名稱字串，不是風險評估的結果。**兩者其實一樣危險**（都會斷線中的請求），但一個完全不設防、一個完全過不去。這個不對稱本身就是設計缺陷。

## §5 修法（未實作）

`authorization-permit.js` 的 `main()` 改成讀 `payload.prompt`，並且要決定授權語意。兩種設計：

**A. 白名單片語 + 預簽**：prompt 內含明確授權字樣（例如「授權重啟 :20130」）時，對 `PROTECTED_COMMANDS` 全清單預先簽發該 prompt 的 permit。
問題：permit 以 `hashCommand(cmd)` 為 key，預簽必須事先知道**完整指令字串**（含 `GUARD_OK=1` 前綴與否、uid、旗標順序都會改變 hash）。要嘛改成以 pattern 為 key，要嘛 guard 端改成模糊比對。

**B. 兩階段 pending**：guard.js 被擋時寫一份 `pending_<session>_<hash>.json`（`STATE_DIR` 已有這個檔名慣例，顯然原本就是這樣設計的），下一輪 UserPromptSubmit 看到授權字樣就把 pending 升級成 permit。
這條比較貼合現有檔名慣例，且天然解決 hash 對不上的問題 —— hash 由 guard 端產生，不用猜。

**建議 B**，理由是 `pending_` 這個前綴已經在 `STATE_DIR` 出現過，代表原始設計就是兩階段，只是 UserPromptSubmit 那半邊沒寫完。

**改之前要先確認 UserPromptSubmit 的實際 payload 欄位**（用 `node -e` 把 stdin 原樣 dump 到檔案再看），不要重蹈這次「照 PreToolUse 的欄位寫」的覆轍。

## §5b 實際修法（已實作，2026-08-02）

採 §5 的方案 B。五處改動：

**`guard.js`**

1. `checkBash(cmd, sessionId)` —— sessionId 由 `main()` 從 payload 取（`payload.session_id`），不再讀 env
2. 新增 `writePending(sessionId, cmdHash, cmd)`：permit 檢查失敗時落 `pending_<sessionId>_<cmdHash>.json`，記完整指令字串
3. `findPermit(sessionId, cmdHash)` 取代 `getPermitPath()`：掃 `STATE_DIR` 找 `permit_<sessionId>_*_<cmdHash>.json`，**不綁 promptId**
4. 新增 `denyPermitMsg()`：permit 路徑專用，明講「原封不動重跑」且「本路徑不吃 GUARD_OK=1，加了會改雜湊」
5. `PENDING_TTL_MS = 15min`（等人）與 `PERMIT_TTL_MS = 5min`（拿到就用）分開

**`authorization-permit.js`**（整支重寫）

6. 改讀 `payload.prompt` / `payload.session_id` / `payload.prompt_id`
7. `AUTHORIZE_RE = /授權|批准|同意|允許|放行|authoriz|authoris|approve|確定執行|確認執行/i`
8. 命中授權字樣 → 掃本 session 未過期的 pending，逐一簽成 permit 並刪除 pending
9. 每次呼叫先 `reapExpired()` 掃掉過期的 pending/permit
10. 簽發內容寫 `guard-state/authorizations.log`，並用 `systemMessage` **把授權了哪些指令顯示給使用者看**
11. 固定 dump payload 到 `.last-userpromptsubmit.json`

### 授權字樣刻意排除「執行」和「確定」

兩者單獨出現時在一般指令裡太常見（「執行派工B卷」「確定要用這個方案」），會變成靜默授權。只認「確定執行」「確認執行」這種連用形式。

### 驗收（9 項離線 + 3 項活體）

離線（用 throwaway session id，不碰真實狀態）：

```
1. 首次嘗試            → deny + 寫出 pending          ✅
2. 非授權訊息          → 不簽票，pending 保留          ✅
3. 授權訊息            → 簽出 permit、刪除 pending     ✅
4. 原封不動重跑        → ALLOW                        ✅
5. 再跑一次            → deny（一次性）                ✅
6. 指令字串不同        → deny                         ✅
7. 別的 session 用同一張票 → deny                     ✅
8. 無關指令（ls）      → ALLOW（未波及）               ✅
9. 既有 RULES（rm -rf 受保護路徑）→ deny（未削弱）     ✅
```

活體（真實 session）：

```
A. PreToolUse payload 帶得出真實 session_id    ✅ f9baf681-3165-…
B. 非授權訊息不簽票                             ✅ 「先驗 hook 沒問題再說」→ 無 permit
C. 過期 pending 自動 reap                       ✅ 塞一筆過期的，跑一次 hook 即消失
```

### 正確用法（給未來的 agent）

```
1. 直接跑受保護指令 → 被 deny，此時 pending 已自動登記
2. 向使用者說明影響，等他回覆含「授權/批准/同意/允許」
3. 原封不動重跑同一道指令 —— 不要加 GUARD_OK=1、不要改任何字元
```

備份：`~/.claude/hooks/guard.js.bak-20260802-170222`、`authorization-permit.js.bak-20260802-170222`。

## §6 無效的嘗試

| 做法 | 結果 |
|---|---|
| 加 `GUARD_OK=1` 前綴 | ❌ `PERMIT_PROTECTED` 路徑根本不看 `GUARD_OK` |
| 把 `GUARD_OK=1` 包進 `bash -c '...'` | ❌ 一樣被擋，而且 hash 也變了 |
| 使用者在對話中明確說「授權」 | ❌ hook 不讀 prompt 內容 |
| 同一輪內連下兩個受保護指令 | ❌ 第一個成功純粹是因為它不在清單上（見 §4），不是「一輪一張票」 |
| 改寫指令避開 `heavy-hl` 字串（例如變數拼接、用 label 以外的識別方式） | **禁止**。這是繞過攔截層，違反 `~/.claude/CLAUDE.md` 的紀律。攔截層是防呆不是沙箱，界線在紀律不在技術 |

## §7 影響（已解除）

修復前，`0035` 的 strip-proxy 改動無法完整上線：`:20130` 仍跑舊碼，持續往共用 logs 目錄寫字面 `\n`。hook 修好後這條路已通，`:20130` 重啟只需使用者一句授權。

## §8 教訓

**「先驗 payload 再寫 hook」不是可選步驟。** 這支 hook 從頭到尾沒有跑通過一次，卻在 `guard-state/` 留下四個測試檔看起來像驗過了（session id 是 `session-transcript-test` / `valid-session-123`）——那些是用**手工捏的 payload** 測的，捏的時候用了 PreToolUse 的欄位名，所以測試自己也錯得一模一樣。**用假資料測，只會驗證你的假設跟你的程式一致，不會驗證程式跟現實一致。**

第二個教訓：**deny 訊息本身是介面，寫錯會主動誤導。** 舊 `denyMsg` 叫 agent 加 `GUARD_OK=1`，在 permit 路徑上不但無效還會改變雜湊；agent 照做、失敗、再試一次，看起來像「授權機制壞了」而不是「指示錯了」。

## 受影響檔案

- `~/.claude/hooks/authorization-permit.js`（根因所在）
- `~/.claude/hooks/guard.js`（`PERMIT_PROTECTED` / `consumePermit`）
- `~/.claude/guard-state/`（只有 2026-08-01 的測試殘留）
