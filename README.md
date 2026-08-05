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

## 什麼該寫進來 — 症狀先於敘事

fixindex 收的是**可復現、省下工的技術筆記**,不是做了什麼的紀錄。

**修好一個 defect 之後才寫。** 不是 phase 做完、不是任務交付、不是收工。只診斷沒修也算 — 照寫,但明寫「未修」並留下一步;診斷本身就是資產,它讓下一個人不必重推一遍。

判準很機械:**如果你寫不出一句別人會拿去搜尋的 `Symptom`,你手上的就不是 entry,是進度報告。** 放別的地方。

| 不要 | 為什麼 | 改成 |
|---|---|---|
| 日期進檔名 `0042-thing-20250105.md` | entry 講的是那個缺陷,不是那一天 | `0042-thing.md` |
| `## §N 更正(日期)` 小節 | 對自己前一份記錄的勘誤是對話產物 | 直接回改 §1 |
| `Verify` 寫一次性讀數 —「配額 348/1000、錯誤率 2.3%」 | 明天重跑數字就不同,證明不了任何事 | 可重跑的指令 **+ 期望結果** |
| `Fix` 寫成專案進度 —「Phase 3 建立了新的 pool」「在 Block B 修好」 | 那份文件消失後就沒有意義 | 寫指令或 diff |
| `symptoms:` 放數據 —「50.8% / 49.2%」「PID 81681」「2025-01-05 出現 6 次」 | 沒有人會把這串打進搜尋框 | 只放你真的會 grep 的字串 |
| 一個 entry 塞多個缺陷 | 違反 one entry per defect;那些段落的共通點只是同一個下午 | 拆開 |
| 收工驗收表 — F1 ✅ / F2 ✅ / PID 未變 | 幾小時後就失效 | 拿掉,留可重跑的 Verify |
| 指向一次性文件 —「見 plan-xyz.md 的 Block B」 | 外部文件會消失 | 把重點抄進來 |
| Secret,即使只貼前綴 | 「為了標示是哪一把」從來不是理由 | 引用變數名 |

**為什麼在意這件事。** 症狀優先寫的 entry 能活好幾年 — 有人撞到同一串錯誤訊息,直接落在答案上。敘事優先寫的 entry,在你忘記那個專案的詞彙那一刻就搜不到了,而且會把真正的修法擠到索引下面。前者是 runbook,後者是日記。

**關於 phase 式流程。** 如果你的流程寫著「每個 phase 更新 runbook」,不要把 phase 對應成 entry。修了三個缺陷的 phase 產出三筆;沒修到東西的 phase 產出零筆。**phase 驅動的寫法是把 runbook 填滿日記最可靠的方式。**

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
| **`fi`（單獨一個字，沒有其他內容）** | **補記口令** — 把「剛才這段對話」的技術成果補成一筆，見下方 |

> **原理**：Agent 負責語意判斷 → 決定指令 → 執行 CLI。`fixindex` 本身仍是純確定性的 CLI — NL 理解由 agent 層承擔，保持工具本身的可靠性。

觸發點分兩類：**主動口令**（`Fixindex <問題>`、`fi`）讓你掌控時機；**隱性觸發**（說出症狀、貼 log、說修好了）讓 agent 在正確時間點自動查找或記錄，不需要你記得。

### 收尾自動帶一筆，`fi` 是補救

安裝 snippet 之後 agent 應該在**每個重大任務收尾時自動補一筆** — 前提是那次任務真的修好了 defect（沒修到就不寫，見上一節的判準）。

漏了的時候，你只要打兩個字元：

```
fi
```

單獨的 `fi`（前後沒有其他內容）= **立刻把剛才那段對話的診斷／修復補成一筆**。不是列清單、不是問你要記什麼 — 多問一句就破功，`fi` 的價值就在收工那一刻零摩擦落地。

Agent 收到 `fi` 之後應該：

1. `fixindex list` 心算屬於哪個 domain
2. `fixindex find` 確認有沒有更貼近的既有檔
3. 有既有檔 → 追加 `## §N` 並補 frontmatter `symptoms:`；沒有 → `fixindex new <slug>`
4. `fixindex re-index`（只有新建檔案時需要）

寫進去的是**根因公式／數據佐證／已否決的路／可移植的 rule**，不是「改了什麼」的流水帳。**修法還沒實作也照樣記** — 明寫「未修」並留下一步即可，診斷本身就是資產，下次撞到同症狀不必重查一遍。

也可以直接餵管線（`fi` 子命令從 stdin 讀內容，自動配對 domain）：

```bash
printf '**Symptom:** ...\n**Root cause:** ...\n**Fix:** ...\n**Verify:** ...\n' \
  | fixindex fi redis --title "Redis cluster failover" --tags redis,cluster
```

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
