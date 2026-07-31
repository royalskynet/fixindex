---
id: 0011
slug: fts-harness-layer-stall-coverage
title: FTS session 宣告下一步後停擺、HL 三層全數空轉
tags: [fts, harness, codex, stop-hook, goals, poll, launchd, bash]
symptoms:
  - "fts session 最後一句宣告『現在要做 X』然後就收工不動"
  - "session process 還活著但沒人推、rollout 停在 task_complete"
  - "acceptance-gate.log 對停擺 session 只寫 layer2 | pass"
  - "POLL-STATE.json action 恆為 ok 但實際有 session 停擺"
  - "codex exec resume 跑完沒有 agent_message、rollout 只留 task_started/task_complete"
  - "ERROR: Missing environment variable: `OMNIROUTE_API_KEY`."
  - "fts new 不帶 prompt 噴 unbound variable"
  - "fts new 帶初始 prompt 開了 session 但停在 Waiting for messages..."
  - "Not inside a trusted directory and --skip-git-repo-check was not specified."
  - "harness 踢了 session 但目標 rollout 完全沒被推進，logs/session-resume-*.log 是 0 bytes"
  - "warning: This session was recorded with model `gpt-5.4` but is resuming with `gpt-5.5`"
  - "warning: Ignored unsupported project-local config keys in /Users/51mini/.codex/config.toml"
  - "tmux send-keys 到 fts session 回 rc=0 但 rollout 毫無變化"
  - "tmux capture-pane 對 fts-codex-* session 抓到全空白"
status: active
supersedes: []
related: [0010, 0009]
---
# 0011 FTS session 宣告下一步後停擺、HL 三層全數空轉

案例 session `019fb390-316f-76e3-a0fa-e7c692b829f0`（cwd `/Users/51mini/NovelVault`）。
末句「世界聖經改完了，現在清理空行並加 changelog」→ 正常 `task_complete` 收尾後就不動了。
process 存活（happy 75378 / codex app-server 75416），**不是 crash，是沒人推**。

三層 harness layer 對它全數空轉，三個根因彼此獨立：

| 層 | 實測證據 | 為何沒蓋到 |
|---|---|---|
| L1 goals | `~/.codex-fts/config.toml:143` `goals = false`；`goals_1.sqlite` 唯一一筆 goal 已 `complete` | 沒有活躍 goal → 無 continuation 注入 |
| L2 Stop hook | `~/.codex-fts/acceptance-gate.log`：`15:27:02 \| 019fb390-… \| layer2 \| pass` | layer1.5 要求 cwd 在 `/Users/51mini/omniroute-free-tools` 下（本 session 在 NovelVault）；layer2 只比對 6 個吹牛關鍵字。「宣告下一步就停」**零覆蓋** |
| L3 poller | launchd `com.royalskynet.freetools-harnesspoll` 每 120s 有跑，`POLL-STATE.json` `action: ok` | work-dir 寫死 `omniroute-free-tools/tmp/strip-harness-dispatch`，只看 `ASSIGNMENT.md`/`SELF-CHECK.md`；且 `harness-poll-fts.mjs` `--help` 自陳不注入 |

「宣告下一步就停」是最常見的死法，卻是三層裡唯一沒人負責的區塊。

## §1 codex exec resume 缺憑證會靜默空轉（最大的坑）

**Symptom:** 注入後 rollout 只多出 `task_started` → `user_message` → `task_complete`，
2 秒內結束，**完全沒有 `agent_message`**。看起來像「session 收到了但不理」。

**Root cause:** `codex exec resume` 直接跑，沒載入 omniroute 憑證：

```
ERROR: Missing environment variable: `OMNIROUTE_API_KEY`.
```

錯誤只出現在 stderr，rollout 裡看不到，所以從 rollout 端診斷會誤判成「模型不聽話」。

**Fix:** 憑證在 `/Users/51mini/.creds/omniroute/codex-fts.env`（由 `~/.local/bin/happy-codex-fts:4`
載入，裸跑 codex 不會自動吃到）。正確注入姿勢：

```bash
set -a; . /Users/51mini/.creds/omniroute/codex-fts.env; set +a
export CODEX_HOME=/Users/51mini/.codex-fts
cd <session 的 cwd，從 rollout 首行 session_meta 讀>
codex exec resume --skip-git-repo-check -c model="gpt-5.4" <session-id> "<prompt>"
```

**兩個旗標缺一不可，原因見 §7。**（本段原本沒有這兩個旗標，2026-07-31 補上——舊版指令在 cwd 是
`$HOME` 時會直接被拒絕執行，或執行成功但走到付費模型。）

**無效嘗試：** 只設 `CODEX_HOME=/Users/51mini/.codex-fts`——那只換 profile 目錄，不帶 key。

## §2 L2：Stop hook 加 layer1.8 未竟宣告偵測

`/Users/51mini/secret-cheeragent/hooks/fts-acceptance-gate.js`，插在 layer1.5 與 layer2 之間，
**不綁 repo**，對任何 cwd 的 fts session 都成立。

命中模式 → `{"decision":"block","reason":"你上一輪自己說要做但沒做：「<原句>」。現在做完再停。"}`

兩個踩過的品質坑：

1. **reason 要擷取整句，不是關鍵詞。** 第一版回 `match[0]`，reason 變成
   「你上一輪自己說要做但沒做：「現在」」——零資訊量。改成依 `/(?<=[。！!\n])/` 切句、
   回第一個命中句（上限 120 字），lookbehind 失敗有 try/catch 退路。
2. **裸「現在」「繼續」會誤攔。** 「現在狀態正常」「系統繼續運作正常」是收尾語不是未竟宣告。
   收窄成要求後接動作動詞：
   `/現在(就)?(要|來|開始|去|進行|處理|清理|補|加|寫|改|跑|做|修|整理|移除|刪除|更新)/`、
   `/繼續(做|處理|執行|完成|寫|改|跑|進行)/`。動詞白名單刻意不含狀態詞。

豁免（任一命中即 pass）：含 `？`/`?` 或 `<options>`（在問使用者）、既有 `hasHonestCaveat()`
（已誠實標記未完成）、已達 `MAX_NUDGES`（沿用既有 nudge cap，不新增計數器）。

上線先掛 dry-run（`HL_UNFINISHED_DRYRUN=1`，只寫 `layer1.8 | would-block` 不 block），
掛在 `~/.codex-fts/hooks.json` 的 Stop 項：

```json
"command": "/usr/bin/env HL_UNFINISHED_DRYRUN=1 node /Users/51mini/secret-cheeragent/hooks/fts-acceptance-gate.js"
```

用 `/usr/bin/env` 絕對路徑而非 `VAR=1 node …` 前綴——後者只在 shell 解析時有效，
hook 若是 argv-split 直接 exec 會整條找不到指令。

## §3 L3：poller 改吃活躍 session

`/Users/51mini/omniroute-free-tools/scripts/harness-poll-fts.mjs`，新增獨立於既有
ASSIGNMENT/SELF-CHECK 分流的 session-scan 分支（既有 18 條 fixture 全綠不動）：

- 掃 `~/.codex-fts/sessions/YYYY/MM/DD/rollout-*.jsonl`（預設近 3 天），讀首行 `session_meta`
  拿 session_id/cwd、末筆事件拿 type/timestamp
- 判定盲區死法：末筆是 `task_started` 且逾 `--stale-seconds` 且 `lsof` 顯示 process 仍持有 fd
  → 這是 L2 蓋不到的區塊（turn 中途斷流，Stop hook 根本不 fire）
- 注入照 §1 姿勢，`bash -lc` + 位置參數傳遞避開引號地雷（`codex` 在 `bash -lc` 下解析到
  `/opt/homebrew/bin/codex`，launchd 的精簡 PATH 無礙）
- 防重複：`tmp/fts-session-resume-locks/<id>.resumed-<epochMs>`，預設 cooldown 30 分
- `--fixture` 完全跳過本分支；`--no-write` 只回報 `wouldResume` 不寫 lock 不執行
- 新旗標：`--no-session-scan`、`--session-scan-days`、`--sessions-dir`、`--resume-cooldown-seconds`

## §4 L1 goals：沒有 `/goal` 這個 slash command

`config.toml:143` `goals = false` → `true` 後，goals 是**給模型的 tool**：`create_goal` /
`update_goal`。實測 codex 0.144.5 native binary
（`…/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex`）`strings` 撈不到任何
`/goal` 字串，slash 清單裡也沒有。

**無效嘗試：** 把初始 prompt 前綴成 `"/goal <prompt>"`——只會被當普通文字送進去，goal 不會登記。

## §5 `fts new` 兩個獨立 bug

`/Users/51mini/.local/bin/fts`。

1. **bash 3.2 空陣列崩潰。** shebang 是 `#!/bin/bash` = macOS 內建 3.2.57，`set -euo pipefail`
   下展開空陣列直接 `unbound variable`：
   ```
   $ /bin/bash -c 'set -euo pipefail; a=(); printf "%s\n" "${a[@]}"'
   /bin/bash: a[@]: unbound variable
   ```
   `bash -n` 只驗語法，**查不出來**。要 `${arr[@]+"${arr[@]}"}` 保護，或實際跑空參數路徑。
2. **happy wrapper 丟棄 positional prompt。** `fts new "<prompt>"` 開得起 session，但 log 停在
   `Waiting for messages...`，prompt 從未送出——happy 把 codex 跑成 app-server 模式，不是
   TUI passthrough。且 session 在第一個 turn 之前**不產生 rollout**，所以 `codex exec resume`
   也無從指定 session id；daemon 只有 `/list`、`/spawn-session`、`/stop-session`、`/stop`，
   沒有 send-message endpoint。

   **結論：headless 下無管道自動送出第一則訊息。** 與其靜默吞掉，`fts new` 改成帶參數就
   `exit 2` 明確報錯，help 標明限制。goal 登記改由使用者在 session 內下第一則訊息時自然發生。

## §6 附帶觀察：踢醒不等於會動手

§1 修好後真的注入成功（該 turn 燒了 929k tokens），但 session 回應完**三項任務仍然零完成**
——又是一次「宣告→停」。單靠注入救不回已經進入這個模式的 session，最後是另派 agent 直接做完。
這反過來佐證 layer1.8 的必要性：要在它第一次「宣告下一步就收工」時就 block，而不是事後補救。

---

## §7 踢醒送不到的兩個真根因：cwd 是 $HOME

2026-07-31 實測。harness 用 rollout `session_meta.cwd` 當工作目錄，而 FTS session 的 cwd 多半是
`/Users/51mini`。這一件事同時觸發兩個獨立故障。

### §7.1 非 git repo → codex 直接拒絕執行

**Symptom**

```
Not inside a trusted directory and --skip-git-repo-check was not specified.
```

harness 端的表現是「踢了但目標 rollout 完全沒被推進」，`kickFailedStreak` 一路累加。
**在 `logs/session-resume-<sid>.log` 是 0 bytes 的時期完全看不到這行**——先修好 spawn
（`stdio: ['ignore', fd, fd]`，見 §7.3）讓 log 寫得出東西，錯誤才浮出來。

**Root cause**

`codex exec` 預設要求 cwd 是受信任目錄（git repo）。`$HOME` 不是，直接拒絕，連 session 都不查。

**Fix** — 加 `--skip-git-repo-check`。

**Verify**（便宜，不燒 token：用不存在的 session id 只驗閘門）

```bash
cd /Users/51mini
codex exec resume 00000000-0000-0000-0000-000000000000 "x"
#   → Not inside a trusted directory ...
codex exec resume --skip-git-repo-check 00000000-0000-0000-0000-000000000000 "x"
#   → Error: no rollout found for thread id ...   ← 閘門已放行
```

### §7.2 `~/.codex/config.toml` 被當 project-local config → 漏到付費模型

**Symptom**

```
warning: This session was recorded with model `gpt-5.4` but is resuming with `gpt-5.5`.
warning: Ignored unsupported project-local config keys in /Users/51mini/.codex/config.toml
```

**Root cause**

cwd 是 `$HOME` 時，`~/.codex/config.toml` 就成了 codex 眼中的 **project-local config**，
其 `model = "gpt-5.5"` 蓋掉 `CODEX_HOME=~/.codex-fts` 的 `model = "gpt-5.4"`。

`happy-codex-fts` wrapper 靠 `CODEX_HOME` 做渠道隔離，**擋不住 cwd 帶進來的覆蓋**。
後果照 wrapper 自己的註解：`codex/*` = 真金錢，且被 key allowlist 擋 403。harness 每踢一次漏一次。

**Fix** — 顯式釘 model，讓 project-local 蓋不掉。動態讀 fts config 免得日後漂移：

```js
function ftsModel() {
  try {
    const m = fs.readFileSync(path.join(CODEX_FTS_HOME, 'config.toml'), 'utf8')
      .match(/^\s*model\s*=\s*"([^"]+)"/m);
    if (m) return m[1];
  } catch {}
  return 'gpt-5.4';
}
// codex exec resume --skip-git-repo-check -c model="$6" "$4" "$5"
```

**Verify** — warning 方向對調就是鐵證：

```
修前：recorded with gpt-5.4 but resuming with gpt-5.5   ← 漏了
修後：recorded with gpt-5.5 but resuming with gpt-5.4   ← 覆蓋成功
新增段落 model 分布：4 × gpt-5.4，零 gpt-5.5
```

### §7.3 為什麼這兩個 bug 藏了這麼久

踢醒的 spawn 原本是 `stdio: ['ignore','pipe','pipe']` + `child.unref()`。父進程（poll）一退出就
扯斷 pipe，子進程寫 stdout 拿 EPIPE 當場死 → **log 檔 0 bytes**。錯誤訊息全部被吞掉。

改成 fd-backed 就好：

```js
const fd = fs.openSync(logFile, 'a');
const child = spawn('/bin/bash', [...], { detached: true, stdio: ['ignore', fd, fd] });
child.unref();
fs.closeSync(fd);
```

**Rule：踢醒/注入這類 fire-and-forget 子進程，stdout/stderr 一定要落檔，而且落檔要用 fd 不用 pipe。**
否則所有故障都長成同一張臉（「踢了沒反應」），沒有任何線索可查。

---

## §8 已證偽的三個認知（別再照舊的想）

| 舊認知 | 實測結果 |
|---|---|
| `codex exec resume` 本身正常，問題在 spawn | **錯**。當初兩次實測都在 `omniroute-free-tools`（git repo）裡跑，條件沒對齊 harness 實際路徑（cwd=`$HOME`）。spawn 只是遮住錯誤的那層 |
| resume 會另開一份新 rollout，所以送達偵測不可能成立 | **錯**。resume 是 **append 回原檔**。實測 45495→99462→124616 bytes、目錄檔數維持 19、`HARNESS_KICK_OK` 就落在原 rollout。比對原檔 `lastTaskStartedTs > lastKickMs` 的送達偵測架構正確 |
| resume 固定燒 682k tokens，貴到必須換管道 | **錯**。成本隨 rollout 大小線性成長。427KB 的大 session 量到 682k、929k；45KB 的小 session 只花 **28,463**。仍需要 `MAX_KICKS_PER_SESSION` 上限，但沒有急到要換管道 |

## §9 死路：tmux send-keys 不能當踢醒管道

**動機**（已作廢）：活著的 app-server 記憶體裡已有 context，`send-keys` 送一行應該比 resume 重放
整份 context 便宜兩個數量級。

**為什麼不行**

FTS session 的 tmux pane 跑的不是 codex REPL：

```
tmux new-session -d -s fts-codex-<ts> exec "happy-codex-fts" codex --yolo >>"<log>" 2>&1
  └─ node happy/dist/index.mjs codex --yolo
      └─ codex ... app-server --listen stdio://
```

stdout 被 `>>` 導進 log 檔，`tmux capture-pane` 全空——沒有 TUI。pane 後面是 **JSON-RPC over stdio**，
不是可打字的提示符。`send-keys` 的 `rc=0` 只代表 tmux 收下按鍵，跟 app-server 有沒有收到無關。

**實測**：送出探針後 rollout 零變化（size/mtime 都沒動），且該 tmux session 在數分鐘內整個消失
（`no server running`）。無法證明是 send-keys 殺的，但時間點高度相關。**代價是一個活 session。**

**配對方法本身是可行的**（若日後有別的用途）—— log 檔沒有 session id、時間戳也對不上
（tmux 建於 10:32:46、rollout 是 10:40:15），但 `lsof` 反查可靠：

```bash
lsof -t -- <rollout.jsonl>            # → 持有它的 codex app-server pid
# 往上走 ppid 直到撞到 tmux list-panes -a -F '#{session_name} #{pane_pid}' 裡的 pane_pid
```

**但有個陷阱**：同一個 app-server 可能同時開著**多份** rollout（實測 pid 52423 同時持有 `019fb60b`
和 `019fb656`，前者 mtime 已停在 12:22、後者 12:34）。所以 `processAlive === true` **不等於**
「這個 session 是活的」——舊 rollout 只是還沒被關檔。要判斷「app-server 當前在哪個 session」，
得取同一 holder pid 持有的 rollout 中 mtime 最新那份。這條尚未實作。
