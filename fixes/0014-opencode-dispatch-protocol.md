---
id: 0014
slug: opencode-dispatch-protocol
title: opencode 派工協定 — argv 吞旗標掛死、stdin + --format json 串流監控
tags: [opencode, dispatch, mannie, yargs, observability, harness]
symptoms:
  - "opencode run '<長 prompt>' 沒有任何輸出，進程活著但十幾分鐘不動"
  - "opencode 派工後 git status 沒有任何新檔，看不出它在幹嘛"
  - "opencode run 輸出被 | tail 緩衝，中途砍掉整段輸出全丟"
  - "派工中途完全沒有進度可看，只能瞎等"
  - "opencode.db 最後活動時間停在上一輪，本輪一筆都沒寫"
  - "opencode 事件流出現 STEP-END reason=length，任務零產出、git status 沒有任何改動"
  - "opencode 只讀了幾個檔就 reason=length 結束，一行程式都沒寫"
  - "任務單已經拆到三項以內，opencode 還是 reason=length 掛掉"
status: done
supersedes: []
related: [0012]
---
# 0014 opencode 派工協定

日期：2026-07-31。實測環境：opencode v1.18.8、`/opt/homebrew/bin/opencode`、model `omniroute/auto/coding:free`（OmniRoute :20128 免費池，零成本）。

---

## §1 argv 傳長 prompt → yargs 吞旗標 → 進程掛死

**Symptom**

```bash
opencode run '<4KB 任務單，內含 --no-write / --json / --help 等字串>'
```

進程存活 18 分鐘，特徵全中：
- stdout 一個 byte 都沒有
- `pgrep -P <pid>` 零子進程
- `lsof -p <pid> -a -i` 零網路連線（連 local server 都沒起）
- `~/.local/share/opencode/opencode.db` 最後 `part` 寫入停在**上一輪**的時間

**Root cause**

`opencode run` 用 yargs 解析 argv。任務單裡出現的 `--no-write`、`--json`、`--help`、`--format` 這類字串會被當成 **opencode 自己的旗標**，而不是 positional message 的一部分。解析結果錯亂 → 進程停在啟動階段，既不報錯也不退出。

**Fix**

prompt 一律走 **stdin**，不走 argv：

```bash
opencode run --format json < /path/to/task.txt > events.jsonl 2> err.log
```

實測 smoke：`printf 'reply exactly: OC_STDIN_OK' | opencode run --format json` → 正常回應。
同一份 4KB 任務單，argv 掛死 18 分鐘；改 stdin 後 **2 分鐘一單過**。

**Invalid attempts（別再試）**

| 做法 | 結果 |
|---|---|
| `opencode run '<prompt>' \| tail -60` | 輸出被 tail 緩衝，進程被砍時整段丟失，等於全瞎 |
| 加大 Bash timeout 等它自己好 | 它不會好，掛死不是慢 |
| 靠 `git status` 判斷進度 | 只能看到「還沒落地」，看不出是在思考還是死了 |

---

## §2 進度監控：`--format json` 事件流

`opencode run --format json` 每個事件一行 JSON。實用欄位：

**外層只有四種 `type`**（v1.18.8 實測，三份事件檔統計交叉確認）：

| 外層 `type` | 意義 |
|---|---|
| `step_start` | 一步開始，訊噪比低，監控可靜音 |
| `tool_use` | 工具呼叫。`part.tool` 是名稱、`part.state.status` 是狀態、`part.state.input` 是參數 |
| `text` | 模型輸出的敘述文字，在 `part.text` |
| `step_finish` | `part.reason`（`tool-calls` / `stop`）、`part.tokens.total`、`part.cost` |

**兩個踩過的坑**：

1. **外層是 `tool_use`，不是 `tool`**。內層 `part.type` 才是 `"tool"` —— 兩層同名不同義，只比對內層會漏。
2. **事件流沒有 `patch` 型別**。`patch`（含 `files` 陣列＝實際落地檔案）只存在 `opencode.db` 的 `part` 表 `data` 欄位裡，不會出現在 `--format json` stdout。想從事件流知道改了哪些檔，只能看 `tool_use` 裡 `edit`/`write` 工具的 `input.filePath`。

**重點**：一定要 `>` 直接寫檔，不要接 pipe。pipe 會緩衝，進程被砍時整段消失。

監控腳本（`ocwatch.mjs`，讀事件檔印一行摘要）核心：

```js
if (e.type === 'tool_use')    console.log(`${t} TOOL ${p.tool} [${p.state?.status}] ${JSON.stringify(p.state?.input||{}).slice(0,120)}`);
else if (e.type === 'text')   console.log(`${t} TEXT ${(p.text||'').replace(/\n/g,' ').slice(0,160)}`);
else if (e.type === 'step_finish') console.log(`${t} STEP-END reason=${p.reason} tok=${p.tokens?.total} cost=${p.cost}`);
else if (e.type === 'step_start') { /* 靜音 */ }
else console.log(`${t} ${e.type.toUpperCase()} ${JSON.stringify(e).slice(0,260)}`);
```

**健康判準**：
- `step_finish` 的 `tokens.total` 持續上升 = 在推進
- 連續數個 `step_finish` 但 `tokens.total` 幾乎不動 = 空轉
- 完全沒有事件寫入 = 卡在啟動（見 §1）

**離線查證**（進程已死、事件檔沒留）：

```bash
sqlite3 -readonly ~/.local/share/opencode/opencode.db \
  "SELECT datetime(time_created/1000,'unixepoch','localtime'), session_id, substr(data,1,180)
   FROM part ORDER BY time_created DESC LIMIT 12;"
```

`part` 表存所有 tool/text/patch/step-finish，是唯一可靠的事後 forensics。**最後一筆的時間戳**直接告訴你它死在哪一步。

---

## §2.5 workdir 外的路徑被自動拒絕（靜默失敗）

**Symptom**

派工調查任務，opencode 跑完 exit 0，但**該產出的報告檔根本沒建**。事件流只有 `tool_use` / `step_finish`，沒有任何 `text` 說明，看起來像正常結束。

真相在 **stderr**（`2> err.log` 那個檔）：

```
! permission requested: external_directory (/Users/51mini/.omniroute/logs/application/*); auto-rejecting
```

**Root cause**

opencode 只能讀寫 workdir（啟動時的 cwd）底下的檔案。碰到外部路徑會發 permission request，非互動模式下**自動拒絕**，然後模型拿不到資料就放棄任務、正常退出。exit code 是 0，不是錯誤。

**Fix**

派工前先確認任務需要的所有路徑都在 workdir 內。三種解法：

1. **改 workdir** —— 要改 `~/.hermes/profiles/mannie/` 就 `cd` 到那裡再跑，不要從別的 repo 跑
2. **預先把外部資料撈進 workdir** —— 主 session 先把 log 片段寫進 workdir 下的暫存檔，任務單改成「讀這個檔」
3. **加 `--auto`** —— 自動核准未被明確拒絕的權限。**危險**，等於放掉沙箱邊界，只在完全信任的唯讀任務用

**教訓**：`2> err.log` 一定要留，而且**每次都要看**。這條訊息只在 stderr，事件流裡完全看不到，光看 `--format json` 會誤以為任務正常完成。

---

## §3 任務單四段格式（缺一不派）

免費池模型會改範圍外的檔，白名單是唯一防線。

1. **白名單** — 只准改/建哪些檔，明寫「不准碰其他任何檔」；例外（如 fixture 目錄）也要明說
2. **改什麼** — 具體到函式名、行號、回傳物件欄位、判斷順序；不寫目標敘述，寫實作規格。貼出「現在長這樣」的原始碼片段，再貼「要變成這樣」
3. **驗收指令** — opencode 自己要跑到綠的具體指令 + 判準（項數下限、輸出必含哪些欄位）
4. **絕對禁止** — 列出不可逆操作：`launchctl`、`git commit`/`checkout`/`add`、改 `~/.codex-fts/`、改 plist、刪既有測試

**派工方回來後仍要自己複驗**：重跑驗收指令 + `git status --short` 看範圍 + `git diff` 逐行讀。opencode 自報「兩項驗收都綠」不算數。

---

## §4 適用性判斷（實測）

| 任務型態 | 划算？ | 依據 |
|---|---|---|
| 改既有函式（明確規格） | ✅ | Stage A 一單過 28 項綠；respawn 模組 2 分鐘一單過，還多寫 2 項測試 |
| 新建模組（有現成範本可抄） | ✅ | `harness-session-respawn.mjs` 照 `harness-doctor-run.mjs` 抄閘門結構，一次到位 |
| 造多個小 fixture 檔 | ❌ | 啟動成本高過自己寫（3 分鐘手寫完成） |
| 一次寫 >80 行新程式（如整套測試） | ✅（2026-07-31 修正後） | 原三連敗 `reason=length` 已定位為 model alias 選錯，非能力上限。改 `free-tools` 後實測 123 行測試檔一次 write 完成、24 項全綠。見 §8 |
| 不可逆 live 操作 | ❌ | `launchctl kickstart`、刪 sentinel、`tmux kill-session` 一律主 session 執行 —— opencode 沒有 guard hook 保護 |

---

## §5 落到 Mannie 派工流程

Mannie（`hermes --profile mannie gateway run`）的 TG `/code` → `mannie-opencode-worker` skill → `opencode run`。同一條後端，所以 §1 的坑同樣適用：**skill 內若用 argv 傳使用者訊息，遇到含 `--` 字串的任務就會靜默掛死**。

Mannie 側該改的：
1. `opencode run` 改 stdin 餵 prompt
2. 加 `--format json` 並落檔，讓 TG 端能回報階段性進度而不是只有最終結果
3. 掛死偵測：事件檔 N 秒無新增就回報異常，不要讓使用者在 TG 前面瞎等

---

## §6 現況

- respawn 功能已由 opencode 落地並複驗（單元 5 項新測試全綠、dry-run 乾淨、範圍無越界）
- `opencode-watch.mjs` 已收進 `omniroute-free-tools/scripts/`（原 scratchpad 版本 `ocwatch.mjs` 作廢）
- FTS harness 一期 + A2 + A3 全部結案：spawn 送達修復、`kick-not-delivered` 反假成功、lsof 減半、premature 門檻 argv 化、7 項 premature 單元測試（總 39 項綠）
- ~~Mannie 側改造未做~~ → **2026-07-31 複查：§5 三項其實都已落地**。`~/.hermes/profiles/mannie/skills/mannie-opencode-worker/SKILL.md` 已是 stdin 餵 prompt + `--format json` 落檔 + `2> err.log` + 180s 無新事件判掛死
- 2026-07-31：`reason=length` 根因定位並修復，見 §8

---

## §7 `reason=length` — 天花板是單次輸出量，不是任務項數

> **2026-07-31 更正：本節的歸因是錯的。** 真因是 model alias 選錯 + config 寫死 `output: 8192`，不是 opencode 或任務單寫法的問題。下面整節保留當時的推論過程，正確答案見 **§8**。

**Symptom**

事件流最後一行 `STEP-END reason=length tok=NNNNN`，之後沒有任何 tool call。零產出、無殘留、`git status` 乾淨、`err.log` 空白。看起來像「跑完了」，其實一行都沒寫。

**Root cause**

`reason=length` = 該 step 的**輸出 token 上限**被撞到。它跟任務有幾項無關，跟「這一步要吐多少 token」有關。而讀檔的內容會**佔用同一個預算**，所以有兩條不同的死法，症狀完全一樣：

| 死法 | 特徵 | 實測 |
|---|---|---|
| **讀爆** | 事件流裡有一串 `read`，最後一個 read 之後直接 `reason=length` | 讀 3 個大 `.mjs`（17k+3k+10k）→ `tok=30367` → 下一步 `tok=43249` 爆 |
| **寫爆** | 只讀了一個檔就爆，或完全沒讀就爆 | 只讀 161 行的測試檔（`tok=18912`）→ 想一次 Write ~120 行測試 → `tok=29515` 爆 |

**已否決的修法（實測無效）**

1. **拆單** — 原單 8 項 3 檔爆；拆成 3 項 1 檔仍爆。項數不是變因。
2. **把已知事實寫進任務單、明令「禁止自行探索驗證」** — 擋得住它跑指令，**擋不住它 read 原始碼**。它為了確認 helper 簽章照樣整份讀。
3. **加寫「禁止 read 這兩個檔」+ 把簽章/資料結構/控制流全貼進單子** — 讀爆解決了，直接轉成寫爆。單子再瘦也沒用，因為要生成的程式量沒變。

**Rule**

派工前先問「**這一步 opencode 要吐幾行？**」不是「這任務幾項？」

- **改既有函式** ✅ —— 輸出是小 diff，即使檔案大也安全（Stage A 28 項綠、respawn 模組一次到位）
- **新建模組有範本可抄** ✅ —— 抄比生成便宜
- **一次寫 >80 行全新程式** ❌ —— 自己寫。三連敗證明沒有任務單寫法能繞過

想派大段生成，唯一可行是**把生成本身切成多單**（每單一個測試案例、各自獨立 Edit），但那時候派工協調成本已經高過自己寫。

**Verify**

```bash
node scripts/opencode-watch.mjs <events>.jsonl | tail -5   # 看最後一行 reason=
git status --short                                          # 確認零殘留
```

`reason=length` 出現就是**零產出**，不要去猜「是不是做了一半」。三次實測都是完全沒動檔案。

