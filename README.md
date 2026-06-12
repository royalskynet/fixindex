# fixindex

> 羽毛級、純檔案的個人 bug 修理日誌 — 症狀 → 解法即時查詢，借鑑 `adr-tools` 風格。

[English](./README.en.md)

`fixindex` 是約 150 行 `bash` + `ripgrep`。無資料庫、無 daemon、無編輯器外掛。每個你解過的 bug 都進到一個 Markdown 檔 `fixes/NNNN-<slug>.md`。下次同樣的錯誤訊息再噴出來，`fixindex find "<錯誤>"` 直接跳到你上季寫的解法。

它存在的理由：

- 多數「第二大腦」工具太重。你想要的只是一個命令、答案直接吐到 stdout。
- LLM coding agent（Claude Code、Codex…）每次都重新探索你已經解過的 bug，白燒 token。把它指向 `fixindex find` 再開始動手，省下幾小時的重複 debug。

## 安裝

```bash
# 1. clone 或內嵌到你的個人筆記 repo
git clone https://github.com/royalskynet/fixindex.git ~/dev/fixindex
cd ~/dev/fixindex

# 2. 把 CLI 放上 PATH
ln -s "$PWD/fixindex" ~/.local/bin/fixindex
# 或：echo 'export PATH="$HOME/dev/fixindex:$PATH"' >> ~/.zshrc

# 3. 指向你的 runbook（如果直接在這 repo 用就不用設）
export FIXINDEX_DIR="$HOME/notes/runbook/fixes"
export FIXINDEX_INDEX="$HOME/notes/runbook/FIX-INDEX.md"
```

需求：`bash` 4+、`ripgrep`（`brew install ripgrep`）、`awk`、`find`。macOS 與 Linux。CLI 本身不需要 Node 或 Python。

## 工作流

### 遇到 bug 時

```bash
$ fixindex find "deadlock detected"
## symptoms match:
  0002-postgres-migrations        L7       - "ERROR: deadlock detected"

(use `fixindex grep 'deadlock detected'` for full-text search)

$ fixindex show 0002
# 0002 postgres-migrations
…
## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** Migration hangs forever on `ALTER TABLE … ADD COLUMN`…
**Root cause:** Another session holds an `AccessShareLock`…
**Fix:** Set a lock timeout before the migration, retry-on-failure:
…
```

### 修完新 bug 之後

1. 追加 `## §N` 區段到對應的 domain 子檔，並把新症狀字串加進 frontmatter `symptoms:` 陣列；
2. 或開一個全新 domain：

```bash
$ fixindex new redis-cluster
/path/to/fixes/0004-redis-cluster.md
re-indexed: /path/to/FIX-INDEX.md
```

接著編輯 `fixes/0004-redis-cluster.md`，把 `Symptom / Root cause / Fix / Verify` 填上即可。

### 檔案結構

每個 fix 檔長這樣（範本在 `fixes/.template.md`）：

```markdown
---
id: 0002
slug: postgres-migrations
title: PostgreSQL migrations / locking / connection pool
tags: [postgres, migrations, locking]
symptoms:
  - "ERROR: deadlock detected"
  - "could not obtain lock on relation"
  - "remaining connection slots are reserved"
status: active
supersedes: []
related: []
---
# 0002 postgres-migrations

## §1 ALTER TABLE blocks on long-running transaction
**Symptom:** …
**Root cause:** …
**Fix:** …
**Verify:** …
**Retrospective:** （選填）為什麼舊解法沒擋住？沒教訓就跳過。
```

frontmatter 的 `symptoms:` 陣列是**搜尋索引** — 那是 `fixindex find` 真正在掃的東西。把它當成「將來你會在 shell 直接打進去的錯誤訊息字串清單」。`## §N` 內文是給人讀的 runbook。

## 命令一覽

| 命令 | 作用 |
|------|------|
| `fixindex find <kw>` | 對 frontmatter `symptoms:` 條目做匹配。第一站。 |
| `fixindex grep <kw>` | 跨所有 fix 檔的全文 ripgrep。`find` 沒命中時用。 |
| `fixindex show <id>` | `cat fixes/NNNN-*.md`。 |
| `fixindex list` | 每筆一行摘要。 |
| `fixindex new <slug>` | 配下一個 ID、scaffold 檔案、刷新索引表。 |
| `fixindex re-index` | 重生 `FIX-INDEX.md` 內 `<!-- fixindex:table -->` 區塊。冪等。 |
| `fixindex supersede <old> <new>` | 標記 `<old>` 被 `<new>` 取代，但保留檔案。 |
| `fixindex help` | 顯示說明。 |

環境變數：`FIXINDEX_DIR`、`FIXINDEX_INDEX`、`RG`。

## 自然語言觸發（不用記指令）

安裝對應的 agent snippet 之後，你不需要手敲 `fixindex` 指令 — 直接跟 Agent 說話就夠了。Agent 判斷語意，自動選對應的子命令執行：

| 你說 | Agent 自動跑 |
|------|-------------|
| `Fixindex` 或 `Fixindex <問題描述>` | 依語意選 `find / show / grep / new / supersede / list` |
| 「postgres 卡住了」「redis 沒回應」（系統名 + 症狀） | `fixindex find "<關鍵字>"` → 讀命中檔 |
| 貼上錯誤訊息、log 或 stack trace | `fixindex find "<第一條識別字串>"` |
| 「上次怎麼修的？」「之前有解法嗎？」 | `fixindex find` 查歷史紀錄 |
| 「修好了」「搞定了」「記一下這個解法」 | 自動 append `## §N` 區段 + 更新 `symptoms:` 陣列 |
| 全新問題域、沒有對應的 fix 檔 | `fixindex new <slug>` → 填寫範本 |

> **原理**：Agent 負責語意判斷 → 決定指令 → 執行 CLI。`fixindex` 本身仍是純確定性的 CLI — NL 理解由 agent 層承擔，保持工具本身的可靠性。

觸發點分兩類：**主動口令**（`Fixindex <問題>`）讓你掌控時機；**隱性觸發**（說出症狀、貼 log、說修好了）讓 agent 在正確時間點自動查找或記錄，不需要你記得。

## 給 LLM coding agent 用

**多平台一鍵 snippet** 在 [`agent-snippets/`](./agent-snippets/) — 挑你工具對應的檔（Claude / Codex / Cursor / Gemini / opencode / 通用），`cat … >> <規則檔>` 就裝完。

完整自然語言 dispatch 表（含範例與完整說明）見 [`docs/agent-integration.md`](./docs/agent-integration.md)。

把「我從頭探索一遍 repo」變成「我先翻 runbook」 — 同一個解法不會讓 agent 每個月重新推一次。

## 為什麼要羽毛級

考慮過其他方案，沒收進來的理由：

- **SQLite / vector DB。** 多一個 binary 進 dotfiles、多一個 daemon 要顧。對 ~30 個 markdown 檔做 `ripgrep`，反正本來就 < 50 ms。
- **編輯器外掛。** 綁死一個編輯器。CLI 在任何 terminal 都能用，包含 SSH 與 agent 的 `bash` 工具。
- **一個 fix 一個檔（純 adr-tools 風格）。** 個人 bug 日誌很快會炸成幾百個只有一段內容的小檔。改用 *domain* 分組（`postgres-migrations.md` 收 10 條相關 fix）能壓住檔案數但不犧牲粒度 — 每個 `## §N` 區段仍可獨立引用。
- **LLM 自動摘要 / 自動 tag。** 非確定性。frontmatter 就是索引 — 你手寫一次，永遠信它。

## License

MIT — 詳見 [LICENSE](./LICENSE)。

## 致敬

- [npryce/adr-tools](https://github.com/npryce/adr-tools) — 編號 + 自動 index 模式。
- [danluu/post-mortems](https://github.com/danluu/post-mortems) — 證明純 markdown 就夠用。
- [tldr-pages](https://github.com/tldr-pages/tldr) — 把「症狀優先查找」當成 UX primitive。
