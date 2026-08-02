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
status: active
supersedes: []
related: [0035-strip-proxy-anomaly-jsonl-literal-newline]
---
# 0036 guard-permit-hook-never-issues

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

## §6 無效的嘗試

| 做法 | 結果 |
|---|---|
| 加 `GUARD_OK=1` 前綴 | ❌ `PERMIT_PROTECTED` 路徑根本不看 `GUARD_OK` |
| 把 `GUARD_OK=1` 包進 `bash -c '...'` | ❌ 一樣被擋，而且 hash 也變了 |
| 使用者在對話中明確說「授權」 | ❌ hook 不讀 prompt 內容 |
| 同一輪內連下兩個受保護指令 | ❌ 第一個成功純粹是因為它不在清單上（見 §4），不是「一輪一張票」 |
| 改寫指令避開 `heavy-hl` 字串（例如變數拼接、用 label 以外的識別方式） | **禁止**。這是繞過攔截層，違反 `~/.claude/CLAUDE.md` 的紀律。攔截層是防呆不是沙箱，界線在紀律不在技術 |

## §7 影響

`0035` 的 strip-proxy 修復無法完整上線：`:20130` 仍跑舊碼，持續往共用 logs 目錄寫字面 `\n`，會把剛修好的 `anomalies.jsonl` 重新弄壞。

在 hook 修好之前，`:20130` 的任何重啟都要走別的途徑（使用者手動、或改 plist 後由 launchd 自行 reload）。

## 受影響檔案

- `~/.claude/hooks/authorization-permit.js`（根因所在）
- `~/.claude/hooks/guard.js`（`PERMIT_PROTECTED` / `consumePermit`）
- `~/.claude/guard-state/`（只有 2026-08-01 的測試殘留）
