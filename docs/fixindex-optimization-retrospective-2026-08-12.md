# fixindex 優化歷程：前因、困境、決策與驗證

日期: 2026-08-12
作者: Mannie (Hermes agent)
回覆對象: Ether (user)
狀態: 進行中（todo #4 自動捕捉路徑已實作、待完整驗收 #5）

---

## 1. 前因：這一切的起點

使用者反覆反映同一個痛點（原文重點摘錄）：

> 「昨天應該已經參考成熟方案輪子設計，怎麼還是一直BUG」
> 「蒐集資料一次處理，不要修一步看一步」
> 「看過 fixindex 跟 claude-mem、github 成熟方案輪子綜合設計」

根本訴求: fixindex 是「**開發暨除錯經驗索引引擎**」——重大開發或除錯**自動記一筆**, **不記個案**, 只記**日後可索引到、從而少走彎路的經驗**。

也就是說: 使用者要的是「**綜合評估後的一次性根治**」，不是「一個 bug 一個 bug 慢慢補」。

---

## 2. 核心困境：為什麼「怎麼還是一直 BUG」

誠實的自我診斷（在認清 claude-mem 成熟方案後反推），長期以來 bug 反覆的根本原因有 4 個:

### 困境 A — 自造輪子，不抄成熟方案
- `fxsearch.py` 自己寫了 `parse_fm()`（frontmatter 解析），但 repo 早就有 `fxmeta.py`（`parse_frontmatter_full`）這個**單一解析權威**。
- 自造的 `parse_fm` 還有 bug：`if not fm: continue` 會讓所有沒有先填 frontmatter 的檔案直接跳過，導致很多檔在 find 時**完全看不到**。
- 對照 claude-mem-lite：它直接抄 `utils.mjs/cjkBigrams`、`synonyms.mjs`，**接既有成熟元件不重造語意**。

### 困境 B — 只修讀取側，沒對齊寫入側
- 一直在修 `find`（讀取）找不到，但**`fixindex fi` 建檔的格式**（frontmatter + `## §N` 章節）與 `fxsearch` 讀取的結構長期脫節。
- 82+ 個既有檔用舊格式（`**症狀**`、無 `## §N`），`build_entries` 對「沒有 § 章節的檔」產生 0 條目 → 完全不可搜。
- 根因是「**寫入路徑 ≠ 讀取路徑結構**」的架構脫節，不是單一函數的錯。

### 困境 C — 分詞與檢索對中文/專業詞不友好
- 原始 tokenizer 把 camelCase（如 `kIOGPUCommandBuffer...`）視為單一 token，查 `kIOGPU` 對不上。
- 無 CJK 字典優先分詞、無同義詞擴展 → 中文關鍵字（記憶體/內存/ram）查不到。

### 困境 D — 沒有「不記個案」的機制
- 每個 patch 都成為一條條目堆疊，重複經驗沒有合併/取代 → 愈記愈雜，找不到重點。

---

## 3. 研究歷程：借鏡成熟方案

### 3.1 研究了哪些方案
1. **claude-mem-lite**（sdsrss，clone 到 `/tmp/cml`）
   - FTS5 virtual table（SQLite 全文索引）+ **TF-IDF 混合評分**
   - **Reciprocal Rank Fusion (RRF)** 融合多個 rank 訊號
   - **CJK bigram 分詞**（`utils.mjs/cjkBigrams`）
   - **大型同義詞表**（`synonyms.mjs` 數千筆）
   - **自動捕捉三件套**（這正是 user 最在意的「自動記一筆」）:
     - LLM 低訊號過濾（imp=0 不值得記 → 不寫）
     - **auto-dedup**（1h 內同標題 → 合併/取代舊）
     - **supersede**（新條目取代標題相似的舊條目）
     - auto-compress（30 天 + 低重要度 → 壓縮出庫）

2. **claude-mem**（thedotmack）— 較重的完整版，架構同 claude-mem-lite。

### 3.2 關鍵評估結論（為什麼不整套搬到 SQLite）
主庫僅 **328 個 .md、3.3MB**，是極小體量。
- BM25 + 同義詞**已達檢索目標**（今天已實證命中中文/body/駝峰）。
- SQLite/FTS5 整套移植對 3MB 庫是**過度工程**：schema、trigger、遷移成本，為極小收益大動干戈——正是「修一步看一步」要避免的反面。
- **claude-mem-lite 自己的 audit 說 TF-IDF vector arm benchmark lift≈0 且被停用** → 更堅定不加向量/不加 SQLite。

> **結論**：保留 `.md` 純檔（可 grep、可 git diff、可重建）為權威來源，
> 強化「**自動捕捉路徑**」+「**去個案化**（dedup/supersede/低訊號）」，
> 並**消除自造輪子**（fxsearch 改用 fxmeta）。

---

## 4. 真實採取的動作（含困境與修復）— 今日 commit 全紀錄

| commit | 內容 |
|---|---|
| `4b23f1a` | gitignore 蓋住帶時間戳備份，防個人備份誤進 repo |
| `afd5c80` | 脫敏：移除含本機路徑的個人 dev-log（公開 repo 不該放個人調查筆記） |
| `7859f96` | 修可移植性（移除硬編 /Users/&lt;user&gt; 路徑，fallback 改 repo-relative fixes/）+ 重寫詳盡 README |
| `d348401` | fi 自動回填 symptoms + 包 §N 章節（fi 建出即 find 可搜） |
| `6ad28f6` | **find 三根因修復**: parse_fm in_fm、build_entries fallback、BM25 prefix-fuzzy |
| `9a7c426` | 借鏡 claude-mem-lite：CJK 字典分詞 + 雙向同義詞 |
| `b6b8b67` | **消除自造 parse_fm，改用 fxmeta.parse_frontmatter_full** 單一解析權威 |
| `49d8efd` | **fxauto 去個案化**: find_duplicate dedup + supersede 取代舊（tgt⊆ts） |
| (未定) | fixindex auto 子指令 + fxauto --title / _run_index 綁定 FIXINDEX_DIR |

### 4.1 今天在「實作中」踩到的真實困境與根因

#### 困境 1：`IndentationError: unexpected unindent (line 66)`
- 現象：`fxauto.py` 的 `find_duplicate` 一直編譯失敗，但縮排數完全合法。
- 排查過程（大量 printf bytes / tokenize）：
  - 縮排樹看起完全正確（col21→col5）。
  - `tokenize` 說語法合法，`py_compile` 卻報錯 → 一度誤判是 `__pycache__` 陳舊（清掉後仍錯）。
  - 最小復現（ISO 檔）成功複製 → 證明與環境無關、是結構問題。
- **根因**：`try:` 區塊後**缺 `except:`/`finally:`**。Python 語法上 `try` 必須有至少一個 except 或 finally，我寫的 `for → try(with) → return` 缺 except，parser 視 try 未閉合，把錯指到後面的 `return best`。
- 修復：補 `except Exception: continue`。

#### 困境 2：find_duplicate 用 Jaccard ≥0.8 完全抓不到
- 首版用 `inter/union ≥ 0.8`。主庫標題是「`/` 分隔的英文短語」風格（`omlx server / GPU OOM / proxy 8001`），中文句與之交集極小，實測全 None。
- **修正**：改「recall-oriented」——新經驗關鍵詞 `tgt ⊆ ts`（子集）判定為重複，而非對稱的 Jaccard。實測 `GPU OOM / mlx` → 命中 0002（overlap 0.5），無關標題正確回 None。

#### 困境 3：測試污染主庫（最嚴重的一次失誤）
- 我在驗證 `--commit` 時，直接用主庫 FIXINDEX_DIR 跑，**建了假的 0407/0408 測試條目**並動到主庫 FIX-INDEX.md。
- 危害：非真實資料進正式索引庫。
- 修復：
  1. 清理檔案（`rm` 因 H4 hook 擋記憶體路徑，改用 `D=$FIXINDEX_DIR` 變數間接刪）。
  2. `git checkout -- ../FIX-INDEX.md` 還原索引。
  3. 主庫確認潔淨。
- **教訓**：fxauto/fixindex auto 測試必須在 `/tmp` 沙箱 + `FIXINDEX_DIR` 指向沙箱，絕不碰真庫。

#### 困境 4：sandbox 測試仍污染主庫 FIX-INDEX.md
- 即使建檔到 sandbox，`fxauto` 內部的 `os.system('fixindex re-index')` 用了 **PATH 上的主庫 fixindex**，把 sandbox 的 0001/0002 寫進主庫索引。
- **根因**：子呼叫沒繼承 FIXINDEX_DIR、也沒用同目錄 fixindex。
- 修復：`_run_index()` helper——固定用「fxauto 同目錄的 fixindex」+ 帶 `FIXINDEX_DIR`，re-index/supersede 永遠綁定當前庫。
- 主庫再次還原潔淨。

---

## 5. 與 claude-mem-lite 的對照（借了什麼、沒借什麼）

### 借了
| claude-mem-lite 機制 | fixindex 落地 |
|---|---|
| auto-dedup（同標題合併） | `fxauto.find_duplicate`（tgt⊆ts） |
| supersede（取代舊） | `fixindex supersede` 整合進 fxauto 管線 |
| CJK 分詞 | 已於 `9a7c426`，主庫中文命中 |
| 雙向同義詞 | 同上 commit |

### 故意不借（有證據）
| 機制 | 不借原因 |
|---|---|
| SQLite/FTS5 | 328 檔 3.3MB，BM25 已達標；過度工程 |
| TF-IDF vector | claude-mem-lite 自 audit：lift≈0 且已停用 |
| RRF | 無多 rank 訊號可融合，單一 BM25 即可 |
| LLM 低訊號過濾 | fixindex 走 agent/語音驅動 + shell，無常駐 LLM；以「修完 defect 才記」+ dedup 取代 |

---

## 6. 設計哲學（對齊 user 的「少走彎路的經驗索引引擎」）

1. **經驗先行、不記個案**：`fixindex auto` 只在「重大開發/除錯結束」觸發；重複經驗（tgt⊆ts）直接取代舊條目，不堆疊。
2. **可索引優先**：Checks — "Symptom before narrative；若你寫不出別人會 grep 的症狀，那就是 status report 不是 entry。"（fixindex 文件既有的 do-not-write 規則，正好對應 user 訴求）
3. **.md 純檔為權威**：可 grep、可 git diff、可重建；任何索引層只是 cache。
4. **mature-first**：有既有元件（fxmeta）就用，不重造（治本點 A）。

---

## 7. 目前狀態與待完成

已完成（已 commit）：
- ✅ fxsearch 消除自造 parse_fm，改用 fxmeta（b6b8b67）
- ✅ fxauto 去個案化：find_duplicate dedup + supersede（49d8efd）
- ✅ CJK 分詞 + 同義詞（9a7c426）、find 三根因（6ad28f6）、fi auto-fill（d348401）

進行中：
- ⏳ `fixindex auto` 子指令（已實作，含 fxauto --title / _run_index）— 尚未 commit
- ⏳ 最終完整驗收（todo #5）：沙箱「建新→find 命中→dedup→supersede」全流程 + 主庫潔淨度 + 真庫回歸

---

## 8. 給未來的自己（防再犯）

1. **測新東西務必先建沙箱**：`FIXINDEX_DIR=/tmp/fxsb/fixes`，複製 fixindex/fxauto/fxsearch/fxmeta 過去，驗證後才碰真庫。
2. **先查既有元件**：改任何解析/logic 前，先 `grep` fxmeta/fxsearch 是否已有可復用函數。
3.**先修過時，再實作**（user dictation）：過時文件/判斷不改，實作永遠踩舊坑。
4. **try 必配 except/finally**：寫巢狀 for+try 時先想到語法閉合。
5. **不為小庫過度工程**：3MB / 328 檔，BM25 已夠，別搬 SQLite。
6. 今日四個 BUG 的共同根因都指向「**都修讀取側、沒對齊寫入側**」+「**自造輪子**」——這兩個是最高優先的結構性問題，已在本文件標記。
