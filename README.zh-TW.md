# fixindex

> 羽毛級、純檔案的個人 bug 修理日誌 — 症狀 → 解法即時查詢，借鑑 `adr-tools` 風格。

[English README](./README.md)

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

## 給 LLM coding agent 用

如果你用 Claude Code 或同類 agent，把這段加到你的全域指令（`CLAUDE.md`、`GEMINI.md`、`AGENTS.md`）：

> 動手 debug 前，先跑 `fixindex find "<症狀關鍵字>"`。命中就讀那個 fix 檔再開始改 code。
>
> 修完新 bug 之後，append `## §N` 區段到對應子檔，並把症狀字串加到 frontmatter `symptoms:` 陣列。全新 domain 就跑 `fixindex new <slug>`。

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
