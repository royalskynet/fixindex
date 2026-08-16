# fixindex

> 羽毛級、純檔案的個人 bug 修理日誌 — 症狀 → 解法即時查詢，借鑑 `adr-tools` 風格。
> 往後碰上同樣錯誤，`fixindex find "<錯誤>"` 直接帶你到上次寫的解法，不用重新摸索。

[English](./README.en.md) · 中文

`fixindex` 是約 150 行 `bash` + `ripgrep` 的核心 CLI，配上幾個純 Python 的語意搜尋與自動化工具。**無資料庫、無 daemon、無編輯器外掛**。每個你解過的 bug 進到一個 Markdown 檔 `fixes/NNNN-<slug>.md`，下次同樣錯誤再噴出來，一條命令直達解法。

---

## 這套系統在做什麼

`fixindex` 是一份**技術經驗索引**，不是任務日誌。它的目地是讓「往後編程越來越少彎路」：

- **讀**：撞到錯誤 → `fixindex find` 先查是否解過 → 直接讀解法。
- **寫**：修好一個 defect → 補一條 `## §N` 記錄（症狀優先）→ 下次省下重推時間。
- **自動化**：較大的開發、除錯或重大洞察時自動記錄；也可隨時手打 `fi` 補記。

**判準**：寫不出一句別人會拿來搜尋的 `Symptom`，就不是 entry，是進度報告。`fixindex` 收**可復現、省下工的技術筆記**，不是「做了什麼」的流水帳。

---

## 快速開始（5 分鐘可用）

### 1. 取得 repo

```bash
git clone https://github.com/royalskynet/fixindex.git ~/dev/fixindex
cd ~/dev/fixindex
```

### 2. 把 CLI 放上 PATH

任選一種：

```bash
ln -s "$PWD/fixindex" ~/.local/bin/fixindex      # 最常見：symlink
# 或直接把 repo 加進 PATH：
echo 'export PATH="$HOME/dev/fixindex:$PATH"' >> ~/.zshrc
```

> **`~/.local/bin` 已在 PATH？** 先確認：`echo "$PATH" | tr ':' '\n' | grep local/bin`。沒有的話先把 `~/.local/bin` 加進 PATH。

### 3. 設定 runbook 位置（重要）

`fixindex` 資料（你的 fix 檔）放在**你自己的私有 checkout**，不放這個公開 repo。用環境變數指定：

```bash
export FIXINDEX_DIR="$HOME/notes/runbook/fixes"
export FIXINDEX_INDEX="$HOME/notes/runbook/FIX-INDEX.md"
```

把這兩行加進你的 shell profile。**注意三種環境都要設，缺一個就會「看不到你寫的紀錄」**：

| 環境 | 設定位置 | 為什麼 |
|---|---|---|
| 互動 shell（bash/zsh/fish） | `~/.bashrc`、`~/.zshrc` 等 | 你手敲 `fixindex` 時用到 |
| login shell | `~/.zshenv` / `~/.bash_profile` | 某些 agent gateway 從 login shell 起 |
| **agent / daemon 環境** | **agent 自己的 config** 或該 daemon 的 env | 背景服務常不讀你的 rc 檔 —— 這是「紀錄莫名消失」最常見的原因 |

> **不設定會怎樣？** CLI 與工具 fallback 到「目前工作目錄的 `./fixes/`」或 repo 內的 `fixes/`。在錯誤目錄跑 `fixindex new` 會在第二個、沒人會搜的 runbook 裡默默建條目。`find` 從別處也找不到。所以**設定一次，以後忘了它**。

### 4. 驗證安裝

```bash
fixindex help | head
fixindex find "postgres"    # 空結果也正常，表示搜尋管線通（你的 runbook 尚無資料）
```

---

## 檔案結構

一個 fix 檔長這樣（範本見 `fixes/.template.md`）：

```markdown
---
id: 0002
slug: postgres-migrations
title: PostgreSQL migrations / locking / connection pool
tags: [postgres, migrations, locking]
symptoms:
  - "ERROR: deadlock detected"
  - "could not obtain lock on relation"
status: active
supersedes: []
related: []
---
# 0002 postgres-migrations

## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** …
**Root cause:** …
**Fix:** …
**Verify:** …（可重跑的指令 + 期望結果）
**Retrospective:**（選填）為什麼舊解法沒擋住？
```

**關鍵**：frontmatter 的 `symptoms:` 陣列是**搜尋索引** —— 那是 `fixindex find` 真正在掃的東西。把它當成「你將來會在 shell 直接打進去的錯誤訊息字串清單」。`## §N` 內文是給人讀的 runbook。

**domain 分組**：一個 domain 一個檔（`postgres-migrations.md` 收 10 條相關 fix），壓住檔案數但不犧牲粒度 —— 每個 `## §N` 仍可獨立引用。

---

## 命令一覽

| 命令 | 作用 |
|------|------|
| `fixindex find <kw>` | 對 frontmatter `symptoms:` 做語意搜尋（BM25，見下）。第一站。 |
| `fixindex grep <kw>` | 跨所有 fix 檔全文 ripgrep。`find` 沒命中時用。 |
| `fixindex show <id>` | 顯示 `fixes/NNNN-*.md`。 |
| `fixindex list` | 每筆一行摘要。 |
| `fixindex new <slug>` | 配下一個 ID、scaffold 檔案、刷新索引表。 |
| `fixindex re-index` | 重生 `FIX-INDEX.md` 內 `<!-- fixindex:table -->` 區塊。冪等。 |
| `fixindex supersede <old> <new>` | 標記 `<old>` 被 `<new>` 取代，保留檔案。 |
| `fixindex fi` | 從 stdin 補記一條，自動配對 domain。見「寫入」一節。 |
| `fixindex doctor` | 診斷並修復損壞的 frontmatter。 |
| `fixindex help` | 顯示說明。 |

環境變數：`FIXINDEX_DIR`、`FIXINDEX_INDEX`、`RG`（ripgrep 二進位路徑）。

---

## 寫入：修完 bug 之後

**修好一個 defect 才寫**，不是 phase 完成、任務交付或收工。只診斷沒修也照寫，但明寫「未修」並留下一步 —— 診斷本身就是資產。

### 一行 pipe（唯一主路徑）

```bash
printf 'SYMPTOM: ...\nROOT: ...\nFIX: ...\nVERIFY: <可重跑的驗證命令>' | fixindex fi
```

自由文字也行（`echo '一行症狀' | fixindex fi`）。`fixindex fi`（零參數）自動：dedup/supersede → domain 匹配 append 新 `## §N`（無匹配則建新檔）→ re-index → commit。不要再手動 append `## §N` 或編輯 frontmatter `symptoms:`。

### 指定 domain（向下相容）

```bash
printf 'SYMPTOM: ...\nFIX: ...' | fixindex fi <domain> [--title "..." --tags a,b] [--push]
```

`fi <domain>` 直接 append 到指定 domain；`--new` 強制開新檔；`--push` 自動 git add/commit/push。

### 語意自動配對（`fi` 的 domain 判定）

`fi` 的 domain 匹配是**純確定性**的：優先走 repo 內 `fxsearch.py`（BM25 語意搜尋）找出語意最相近的檔案；`fxsearch` 不可用或沒命中時，退回「任一 domain 詞 whole-word 出現在檔名/title」的子字串比對。**語意判斷由 agent 或 `fxsearch` 承擔，CLI 本身不做語意猜測** —— 這保持工具可靠，也避免把不相關條目誤併。

`fi` 的相似度低於門檻時會**拒絕 append** 並要求 `--new`，防止污染不相關條目。

---

## 語意搜尋（`find` / `fxsearch`）

```
fixindex find <kw>        # 內部呼叫 fxsearch
python3 fxsearch.py <kw>  # 直接呼叫 BM25 引擎
```

`fxsearch.py` 是章節級 BM25 檢索：
- 每個 `## §N` 是獨立檢索單元
- Fields 權重：`symptoms` 3x、`tags` 1.5x、`heading` 2x、`body` 1x
- 支援 CJK 分詞（字符 + bigram）
- `--json` 輸出結構化結果，供 agent/hook 消費

```bash
python3 fxsearch.py "wrapped frontmatter"                 # 文字輸出
python3 fxsearch.py --json --limit 3 "wrapped frontmatter" # JSON
```

---

## Python 工具生態

| 工具 | 角色 |
|---|---|
| `fxsearch.py` | BM25 語意檢索（`find` 的引擎） |
| `fxmeta.py` | frontmatter 解析/正規化/scan（單一解析權威，不依賴 PyYAML） |
| `fxauto.py` | shadow-mode 自動建立條目 |
| `fxblurb.py` | 為每個 § 生成 contextual blurb + 詞彙擴充（產生 `.blurbs.jsonl`，提升中文召回率） |
| `fxadjudicate.py` | 寫入時裁決：APPEND / SUPERSEDE / NEW（用 `fxsearch` BM25） |

所有工具都讀 `FIXINDEX_DIR`。**不設時 fallback 到 repo 自己的 `fixes/`，因此 clone 到任何路徑都能跑**（見「可移植性」）。

---

## 給 LLM coding agent 用（自動化記錄）

安裝對應的 agent snippet，讓 agent 自動查詢與記錄：

```bash
cat agent-snippets/claude.md >> ~/.claude/CLAUDE.md      # Claude Code / 或 agent 的 AGENTS.md
cat agent-snippets/codex.md   >> ~/.codex/AGENTS.md      # Codex
cat agent-snippets/generic.md >> <你的 agent 規則檔>      # 通用
```

### 雙觸發模式

**A. 顯式口令**
- `Fixindex <問題>` → agent 依語意跑 `find / show / grep / new / supersede / list`
- 貼錯誤訊息 / log → `find "<第一條識別串>"`
- **`fi`（單獨一字，無其他內容）** → 補記口令：立刻把剛才的診斷/修復補成一筆。**不要問「要記什麼」** —— 多問一句就破功。

**B. 隱式觸發（省心）**
- 讀：使用者提到「某系統 + 症狀」「壞了/卡住/沉默」或貼 error → 先 `find` 再動手。
- 寫：使用者說「修好了/搞定/記一下」→ append `## §N` + 更新 `symptoms:`。

**建議的自動記錄時機**（節能、按需，不每句都記）：較大的開發、除錯或重大洞察結束時；修好 defect 時；發現可移植的 rule 時。小改動、無技術含量、純敘事不記。

### 三點式 loop（hook 強制版，Claude Code 參考實作）

提示詞觸發靠模型自覺，忙起來會漏。支援 lifecycle hooks 的 agent 可把查/記強制在**三個時點**——不是「每動都查」（太吵）也不是「只 plan 前查」（執行期盲）：

1. **plan 起點**：session 還沒跑過 `find` → 注入一次性提醒，對 plan 主題＋工具鏈做域級掃雷，並預判高機率踩雷點（外部服務/權限/timeout/stale state）順帶先查
2. **執行期踩雷當下**：同指令指紋已失敗 ≥1 次、正要重試 → hook 直接以上次失敗症狀跑 `fixindex find`，命中條目注入 context 再讓 agent 決定繞路；≥2 次觸發停損
3. **完工收尾**：疑似除錯 session（≥10 次工具呼叫＋error 跡象）未記 → Stop hook 擋下收尾強制補 `fi`；小任務低於門檻靜默

不失敗不觸發，頻率天然有界；plan 前查不到的雷，踩到當下查得到。實作細節與兩個實測坑（PostToolUse 失敗不觸發、hook 內嵌 find 的 timeout 餘裕）見 [`docs/agent-integration.md`](./docs/agent-integration.md) Mode C；參考實作在 [Ether-prompt hooks](https://github.com/royalskynet/Ether-prompt/tree/main/hooks)。

### 一鍵自動紀錄（`auto` 一鍵直落）

開發/除錯結束想快速記一筆，不需開 stdin。一行版（`auto --symptom`/`--fix`/`--tags`）：

```bash
fixindex auto --commit --title "gateway 401" --symptom "creds exhausted 401" --fix "輪換 token" --tags "hermes,gateway"
```

多行可讀版：

```bash
fixindex auto \
  --title  "hermes gateway 401 / creds exhausted" \
  --symptom "gateway DTNotFound; HMAC signer 回錯; creds 用完 401" \
  --fix    "查 hermes-gateway-debug；輪換 token 後重啟" \
  --tags   "hermes,gateway,401"
```

`--title`/`--symptom`/`--fix`（`--tags` 可省）齊時 → **非互動直落**：不讀 stdin，
直接走 dedup → supersede → re-index 管線並回傳 JSON（`created` / `dedup` /
`supersedes`）。`--title` 未給時以第一個 symptom 為標題。同主題含新語彙
（overlap ≥ 60%）仍會取代舊條目，不重複建檔。

---

## 可移植性（為什麼「clone 到哪都能跑」）

- `fixindex` CLI 用 `$PWD/fixes` 當預設，repo 內可直接驗證。
- 所有 Python 工具 fallback 到「腳本同目錄的 `fixes/`」，**不硬編任何使用者路徑**（修復前的版本硬編 `/Users/<user>/...`，導致 clone 到別處就壞）。
- 你的真實 runbook 靠 `FIXINDEX_DIR` 指向私有 checkout，與這個公開 repo 分離。
- 本 repo 的 `fixes/[0-9]*.md` 被 `.gitignore` 排除 —— 個人記錄不會誤 commit 進公開 repo。

---

## 環境需求

- `bash` 4+
- `ripgrep`（`brew install ripgrep`）— `find`/`grep` 需要
- `awk`、`find`（macOS/Linux 內建）
- 語意工具（`fxsearch`/`fixmeta`/`fxauto`/`fxblurb`/`fxadjudicate`）需要 `python3`

CLI 本身不需要 Node 或 Python；只有語意/自動化工具需要 Python。

---

## 故障排除

| 症狀 | 原因 | 解法 |
|---|---|---|
| `fixindex: fixes dir missing: <路徑>` | `FIXINDEX_DIR` 指向的目錄不存在 | `mkdir -p "$FIXINDEX_DIR"` 或修正 env |
| `fixindex find` 空結果、但你確定寫過 | `find` 只搜 frontmatter `symptoms:`，不是全文 | 用 `fixindex grep "<內容細節>"` 全文搜 |
| 記錄「消失」了 | agent/daemon 沒設 `FIXINDEX_DIR`，寫到別處了 | 在 agent 自身環境設 env（見「設定」表格） |
| `fi` 拒絕 append | 相似度低，怕污染 | 用 `--new` 強制開新檔 |
| 找不到 `rg` | ripgrep 未裝 | `brew install ripgrep`，或設 `RG` 指到系統 grep |
| `fi` 誤併到不相關條目 | 舊版語意過寬 | 更新到新版（`fi` 用 fxsearch BM25 + 門檻拒絕） |

---

## 為什麼羽毛級

考慮過其他方案，沒收進來的理由：

- **SQLite / vector DB**：多一個二進位、多一個 daemon。對幾百個 markdown 檔 `ripgrep` 本來就 < 50ms。
- **編輯器外掛**：綁死一個編輯器。CLI 在任何 terminal 都能用，含 SSH 與 agent 的 `bash` 工具。
- **一個 fix 一個檔（純 adr-tools）**：個人 bug 日誌會炸成幾百個小檔。改用 *domain* 分組壓住檔案數。
- **LLM 自動摘要 / tag**：非確定性。frontmatter 是索引，你手寫一次永遠信它。

## License

MIT — 詳見 [LICENSE](./LICENSE)。

## 致敬

- [npryce/adr-tools](https://github.com/npryce/adr-tools) — 編號 + 自動 index 模式。
- [danluu/post-mortems](https://github.com/danluu/post-mortems) — 證明純 markdown 就夠用。
- [tldr-pages](https://github.com/tldr-pages/tldr) — 把「症狀優先查找」當 UX primitive。