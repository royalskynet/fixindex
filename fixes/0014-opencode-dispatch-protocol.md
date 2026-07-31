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
  - "opencode reason=length 的 tokens_out 每次都精準等於 8192"
  - "OmniRoute auto/coding:free 路由到 opencode/big-pickle，輸出被 8192 截斷"
  - "opencode.json 的 limit.output 寫死 8192，換模型也沒用"
  - "Mannie 明明有 opencode 卻總是自己動手寫 code"
  - "誤以為 OmniRoute auto/coding:free 是 NVIDIA NIM DeepSeek 優先、OpenRouter FREE fallback"
  - "opencode 把 bash tool call 印成純文字，一個檔都沒建"
  - "opencode 產出的 shell script 混進全形引號 ” 導致語法錯誤"
  - "opencode 寫 bash 測試套件品質崩壞，寫 JS 卻一次過"
  - "opencode reason=stop cost=0 但 git status 什麼都沒有"
status: done
supersedes: []
related: [0012, 0016]
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
| 一次寫 >80 行新程式（如整套測試） | ✅（2026-07-31 修正後） | 原三連敗 `reason=length` 已定位為 model alias 選錯，非能力上限。改 `free-tools` 後實測 123 行測試檔一次 write 完成、24 項全綠。見 §8。**但分流依據應改看產出語言而非行數，見 §9** |
| bash / shell 測試腳本 | ⚠️ | 兩輪都不合格：R1 tool call 退化成純文字零產出，R2 十個單行 bug。引號巢狀深度才是瓶頸，不是行數。派前必加 SECTION 0 樣板並預期主 session 收尾。見 §9 |
| JS / TS / Python / SQL / JSON | ✅ | 同日同 combo 一次過：抽 SQL 模組 + `node:sqlite` 測試，14/14 綠、5 個呼叫點全換對。見 §9 |
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


---

## §8 `reason=length` 真因 — model alias 選錯 + config 寫死 output 8192

日期：2026-07-31 下午。**§7 的歸因錯誤，此節為正解。**

### Symptom

同 §7：`STEP-END reason=length`、零產出、`git status` 乾淨、`err.log` 空白。

### Root cause（兩層疊加，同值 8192 所以看起來像同一件事）

**第一層 — client 端寫死上限。** `~/.config/opencode/opencode.json` 的 provider models 區塊：

```json
"models": { "auto/coding:free": { "limit": { "context": 1048576, "output": 8192 } } }
```

opencode 拿這個 `limit.output` 當 `max_tokens` 送上游。**不管換什麼模型都會在 8192 截斷。**

**第二層 — model alias 路由到 8192 硬頂的模型。** `model` 設的是 `omniroute/auto/coding:free`。`auto/*` 是 OmniRoute 的 **virtual auto-combo**（`open-sse/services/autoCombo/`），每次請求動態挑候選，實測落到 OmniRoute 的 `opencode` 上游連線、model `big-pickle`。

`~/.omniroute/storage.sqlite` 的 `call_logs` 是決定性證據 —— `reason=length` 那幾筆 `tokens_out` 精準等於 8192：

```
2026-07-31T05:32:37  requested=auto/coding:free -> provider=opencode  model=big-pickle  tokens_out=8192
2026-07-31T04:57:25  requested=auto/coding:free -> provider=opencode  model=big-pickle  tokens_out=8192
```

跟任務項數、任務單寫法、讀了幾個檔**全部無關**。§7 那三條「已否決的修法」之所以無效，是因為它們都在調整輸入，而瓶頸在輸出上限。

### Fix

`~/.config/opencode/opencode.json`（備份留在 `opencode.json.bak-20260731`）：

```diff
- "model": "omniroute/auto/coding:free",
- "small_model": "omniroute/auto/coding:free",
+ "model": "omniroute/free-tools",
+ "small_model": "omniroute/free-tools-nim",
```

models 區塊同步改（**這處不改則前一處白改**）：

```json
"free-tools":     { "name": "OmniRoute Free Tools (15-step fallback)", "limit": { "context": 128000, "output": 32768 } },
"free-tools-nim": { "name": "OmniRoute Free Tools NIM (2-step)",       "limit": { "context": 128000, "output": 32768 } }
```

`baseURL`（`http://127.0.0.1:20128/v1`）、`apiKey`、`timeout`、`chunkTimeout` 不動。

**為什麼 output 設 32768**：`free-tools` 15 步全鏈最小輸出上限就是 32768（gpt-oss-20b / ling-3.0-flash / laguna / gemma-4 系列），設更高會在 fallback 到這些步時被上游拒。

**為什麼不改走 strip-proxy :20129**：`omniroute-free-tools/docs/gotchas.md` #7 那條是給 Anthropic-format client 做 model 名 strip 用的，opencode 是 OpenAI-compat 送真實 combo 名，不需要。反而 `strip-proxy/server.mjs:28-29` 有全域序列化閘門 `FTS_UPSTREAM_MAX_CONCURRENT=1` + `FTS_UPSTREAM_MIN_GAP_MS=2500`，opencode 一輪數十次 tool call 塞進單槽會 head-of-line block 掉正在跑的 FTS session。

### 免費層與 fallback 查證

`free-tools` = `fill-first` 15 步。`/v1/models` 逐一查：15 步 `pricing.prompt` / `pricing.completion` 皆 `null`、`tool_calling` 皆 `true`、最小 `max_output_tokens` 32768。上游只有 NVIDIA NIM free entitlement 與 OpenRouter `:free`。`api_key_token_limits` / `provider_key_limits` 皆空表。

### Verify（2026-07-31 實測，四關）

1. `curl :20128/v1/chat/completions -d '{"model":"free-tools",...}'` → `X-OmniRoute-Provider: nvidia`、`X-OmniRoute-Model: deepseek-ai/deepseek-v4-pro`、`X-OmniRoute-Response-Cost: 0.0000000000`、`strategy=fill-first`
2. `printf 'reply exactly: FT_STDIN_OK' | opencode run --format json` → `reason=stop`、`cost=0`
3. **回歸測試**：git repo 內 stdin 派「為 3 個函式寫 >=24 項單元測試」。結果 **123 行測試檔一次 write 完成（`out=2416`）**，自跑 `node --test` 抓到 3 項失敗後自行 edit 修正，最終 `reason=stop`、24 pass / 0 fail、`git status` 只有 `?? test/`（白名單內零越界）、`err.log` 空
4. `call_logs` 事後查：13 筆全 `provider=nvidia|openrouter`、`combo_name=free-tools`/`free-tools-nim`、**`big-pickle` 零筆**、全 `cost=0`

**未觸發的判準（誠實記錄）**：本輪最大單步 `tokens_out=2416`，沒有實際超過 8192 的輸出。「天花板解除」是從兩個間接證據推的（client limit 已改 32768、路由不再落到 8192 硬頂的 big-pickle），未做直接壓測。

---

## §9 `auto/coding:free` 不是 NIM DeepSeek 優先 combo

**Symptom:** 誤以為 OmniRoute `auto/coding:free` 會先走 NVIDIA NIM `deepseek-ai/deepseek-v4-pro`，失敗才 fallback 到 OpenRouter FREE；實際 call log 顯示它成功落到 `provider=opencode model=big-pickle`。

**Root cause:** `auto/coding:free` 是 OmniRoute 執行期建立的 virtual auto-combo，會依 auto candidate 規則動態選模型；它不是固定的 DeepSeek→OR FREE 路由。固定「NIM DeepSeek V4 Pro primary，OpenRouter free tools fallback，第二組 NIM tail」的既有 combo 名稱是 `free-tools-heavy`。

**Fix:** 需要該固定順序的 Hermes profile，將主模型改成：

```yaml
model:
  default: free-tools-heavy
  provider: omniroute
  base_url: http://127.0.0.1:20129/v1
```

同步更新 profile 的 model-check，不再檢查 `auto/coding:free`。`free-tools-heavy` 當前順序：

1. NVIDIA NIM `deepseek-ai/deepseek-v4-pro`
2. OR FREE `nvidia/nemotron-3-ultra-550b-a55b:free`
3. OR FREE `nvidia/nemotron-3-super-120b-a12b:free`
4. OR FREE `cohere/north-mini-code:free`
5. OR `openrouter/free`
6. 第二組 NVIDIA NIM `deepseek-ai/deepseek-v4-pro`

**Verify:** 查 `~/.omniroute/storage.sqlite` 的 `combos.data` 確認步驟順序；送一次 `model=free-tools-heavy` completion，再查 `call_logs`。2026-07-31 實測第一跳 NIM 回 `429`，下一跳 `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` 回 `200`，證明 fallback 生效。Hermes gateway 重啟後，`config.yaml` 顯示 `model.default=free-tools-heavy`，profile model-check 回 PASS。

**Retrospective:** 不從 alias 名稱推測路由。先查 live SQLite combo 定義，再用 `call_logs.requested_model/model/provider/combo_step_id` 驗證實際路徑。

### 附帶收穫

- **fallback 活體證據**：06:36:42 NIM 回 `Stream produced no non-ping SSE event within 20000ms`，fill-first 自動切 step 2 `openrouter/nvidia/nemotron-3-super-120b-a12b:free` —— 寫整份測試檔那筆 2416 輸出就是它完成的。
- **模型會抓任務單的規格錯誤**：任務單寫「`clamp(Infinity)` 回 hi」，模型跑測試失敗後自己推出 `Number.isFinite(Infinity) === false` 所以應回 `lo`，並修正測試。免費池不代表笨。
- **驗收指令自己也要驗**：主 session 用 `node --test test/` 複驗回 `fail 1`，一度誤判 opencode 自報造假。真因是 Node v25 把 `test/` 當模組路徑解析（`MODULE_NOT_FOUND`），改 `node --test test/validate.test.mjs` 就 24 綠。**複驗指令跟被驗程式一樣會有 bug。**

### 教訓

`reason=length` 出現時，第一件事是查 `call_logs` 的 `tokens_out` 跟 client config 的 `limit.output`，**不是**去改任務單。輸出截斷永遠先查上限設定，不查 prompt 工程。這是 `feedback_debug_verify_first`（先驗配置與實際請求，模型永遠擺最後）的又一個案例 —— §7 花了三輪去調 prompt，正解是兩個數字。

---

## §9 語言別品質落差：同一個 combo，寫 JS 一次過，寫 bash 兩輪崩（2026-07-31）

§8 解除 8192 天花板後，同日派了三份任務驗證實戰品質。結果差距極大，而且**不是任務大小造成的**。

| 任務 | 產出語言 | 事件數 | 輪次 | 結果 |
|---|---|---|---|---|
| B：Worker SQL 抽模組 + `node:sqlite` 測試 | JS / SQL | 142 | 1 | **一次過**，14/14 綠，5 個 SQL 呼叫點全換對，兩條指定不動的 INSERT 沒動 |
| A：runner.sh 回歸測試套件 | bash | 9 → 49 | 2（都不合格） | R1 零產出；R2 產出檔案但 10 個 bug |

三次 `step_finish` 全是 `reason=stop`、`cost=0`。**沒有任何錯誤訊號** —— 失敗完全靠主 session 複驗才看得到。

### R1 失敗模式：tool call 退化成純文字

事件流只有 3 筆有效內容：

```
TOOL bash {'command': 'mkdir -p test'}
TOOL bash {'command': 'cat runner.sh'}
TEXT {"command": "mkdir -p test && cat > test/run-tests.sh << 'EOF'\n#!/bin/bash\n..."
```

第三筆該是 `tool_use`，模型卻把整個 tool call 的 JSON **印成 `text`**。opencode 收到的是一段文字，不是工具呼叫，所以什麼都沒執行。`git status --short` 空的，`test/` 是空目錄。

同一段文字裡還混進全形引號：`echo "OK: $*\”` —— `”` 在 bash 是語法錯誤。

**觸發條件推測**：模型想用單一巨大 heredoc（`cat > f << 'EOF' … EOF`）寫一整份 bash 測試檔。bash 測試碼本身塞滿 `"`、`'`、`\`，再包進 heredoc、再包進 JSON tool 參數 —— 三層跳脫疊起來，模型在中途丟失結構，退回吐文字。

### R2：加了「怎麼寫檔」的前置規範才產出檔案

任務單最前面插一段 SECTION 0：

```
1. 用 write 工具建檔，NOT bash、NOT cat、NOT heredoc、NOT echo。
2. 只准 ASCII 引號 " 和 ' ，禁止 “ ” ‘ ’ 與 Unicode dash。
3. 可以分批：先寫 test 1-4，跑一次，再用 edit 追加 5-8。不要一次求完美。
4. 每次 write / edit 之後立刻跑 bash -n，有語法錯先修再往下加。
5. 測試腳本不准用 set -e（斷言失敗不能中止整輪）。
```

檔案這次有了，`bash -n` 也過，但跑起來 exit 1。10 個缺陷：

| 類別 | 實例 |
|---|---|
| `set -u` 違反 | `echo "Test 1: ... $MEM"` —— `$MEM` 此時未定義，直接 `unbound variable` |
| 抽取錨點錯 | `grep -E '^(IMG_PROMPT\|TEXTOUT)=' ` —— 目標行在 runner.sh 縮排 4 空白，`^` 永不命中 |
| 拼字 | `freel "..."` 應為 `fail` |
| sed 語法 | `sed -n '/^    if .../$/^    fi$/p'` —— range 分隔應為 `,` 不是 `/` |
| 引用不存在的變數 | 宣告 `LITERAL_BSLASH_QUOTE`，使用 `$LITERAL_BSLASH_APOTE` |
| 作用域 | test 8 包在 `( … )` 子 shell，`PASS`/`FAIL` 計數器改動被丟棄 |
| 自相矛盾 | 期望 `TEXTOUT == "hello dog] tail"`，下一行卻斷言 `TEXTOUT` 不含 `]` |

全部是單行層級。依 `SOUL.md` 派工門檻（單檔 < 30 行自己動手）主 session 收尾，沒派第三輪。

### 判準：不看行數，看引號巢狀深度

原本 §4 的適用性表按「一次寫幾行」分流。§8 已推翻輸出上限那條，**§9 再推翻一次分流依據**：

| 產出型態 | 派 opencode | 理由 |
|---|---|---|
| JS / TS / Python / SQL / JSON / Markdown | ✅ | 引號單層，工具參數不需巢狀跳脫 |
| **bash / zsh 測試腳本、含 heredoc 的 shell** | ⚠️ 派前先加 SECTION 0，且預期要收尾 | 測試碼含 `"` `'` `\`，包進 heredoc 再包進 JSON = 三層跳脫 |
| perl / awk / sed 單行 regex 密集 | ⚠️ 同上 | 分隔符與跳脫衝突 |

派 shell 任務時，SECTION 0 那五條當固定樣板貼上去。

### 產出測試套件時必加的兩道自檢

複驗「模型寫的測試」時，測試全綠**不代表測試有效**。兩個實際救回問題的手法：

**1. 抽空守衛。** R2 的測試用 `sed`/`grep` 從真 runner.sh 抽片段再 `eval`。抽不到 → 空字串 → `eval ""` 什麼都不做 → 後面的斷言**假性全綠**。所以每個抽取器前面加一條檢查：

```bash
for fn in extract_mem_block extract_agent_block extract_img_lines extract_fallback; do
  if [ -z "$($fn)" ]; then
    fail "extract:$fn" "anchor did not match anything in $RUNNER — the tests cannot run"
  else
    ok "extract:$fn"
  fi
done
```

**2. 突變測試。** 把被測檔路徑做成可覆寫（`RUNNER="${RUNNER:-<預設>}"`），造幾個把已知舊 bug 塞回去的變體，確認測試會紅：

```
變體 m1（塞回舊的 $'...' memory 拼接）  → 5 條紅
變體 m2（regex 拿掉 \]? ）             → 2 條紅
變體 m3（明文 SECRET 寫回去）          → 3 條紅
乾淨版                                  → 30/30 綠，exit 0
```

三個變體都被抓到才算證明測試有效。這比「測試全綠」強得多 —— 全綠也可能是斷言根本沒執行。

### 教訓

- `reason=stop` + `cost=0` **不是成功訊號**，只代表模型認為自己講完了。判斷成功一律看 `git status --short` 加實跑驗收指令。
- 派工失敗要先分類是**能力問題**還是**輸出通道問題**。R1 不是不會寫 bash，是 tool call 序列化崩掉 —— 換寫法（write 工具取代 heredoc）就解決一半，換模型不會。
- 模型寫的測試要當成「未經審查的程式碼」看待，不是「驗收工具」。它自己也要被驗。
