# 召回層棄權設計歷程：兩個被實測否證的門檻，與確定性比對的收斂

日期: 2026-09-26
主題: fixindex 自動召回（PreToolUse hook）的 BM25 層「不相關就閉嘴」怎麼做
狀態: 已落地並驗收（bm25 觸發 3 → 1）

---

## 1. 問題：召回會開火，但開火的內容沒用

自動召回掛在 agent 的 PreToolUse 上，四層依序跑：

| 層 | 查詢鍵 | 性質 |
|---|---|---|
| `pitfall` | 指令原文 → regex 表 | 確定性，不計注入上限 |
| `path` | 即將動到的檔案路徑 → 查表 | 確定性 |
| `bm25` | 觸發器給的字串 → `fixindex find` | 機率性 |

實測數據（生產 1 小時 + 8 條人工探針）：

- bm25 層生產只開火 1 次，3/3 命中無關條目。
- 8 條探針共注入 22 行，人工判定只有 4 行有用（18%）。
- 有用的 4 行全部集中在兩個 case：`git push --force`、`git reset --hard`。
- 1351 筆條目有 541 筆沒有 `**Rule:**`，標題退回 section heading，注入出 `[fix 0528] Fix`、`[fix 0342] 檔案` 這種零資訊行。

結論：不是「排序不夠好」，是**這層沒有棄權能力**——`queryFixindex` 永遠取 top3 注入，查詢跟語料完全無關時也照注。

---

## 2. 第一個設計：絕對分數門檻 —— 查共識時就被否掉

第一版直覺是「BM25 分數低於 N 就不注入」（實測想取 N≈30）。查官方文檔與社群共識後直接作廢：

- Elasticsearch 官方立場：BM25 原始分數**跨查詢不可比**，也隨語料成長漂移，不建議拿絕對值當門檻；要門檻請先 `l2_norm` / `minmax` 正規化。
- 社群（相關性調校討論）對「raw score threshold」的收斂結論一致是反對：原始分數做 abstention 實測 AUC 0.48–0.61，近乎丟硬幣。

**教訓：連自己上一輪的建議都要先過共識這關。** 這條建議是本人提的，也是本人查完文檔後推翻的。

---

## 3. 第二個設計：查詢覆蓋率 —— 實作完被自己的驗收腳本否證

改借鏡 Lucene 的 `coord()` 思路，設計**查詢覆蓋率**：

```
coverage = Σ idf(命中的 query token) / Σ idf(全部 query token)
```

值域 [0,1]、跨查詢可比，不受語料規模影響。`fxsearch.py --json` 加了 `coverage` 欄，並寫一支校準腳本：12 個綠樣本（真實條目的 symptom 當 query，期望命中自身 id）＋ 6 個實測噪音當紅樣本，**紅綠有重疊就 exit 1，禁止自己挑一個折衷值硬過**。

校準結果：

```
所有 12 個綠樣本 coverage = 1.000
所有 6 個紅樣本 coverage = 1.000
max(red) = min(green) = 1.000  → FAIL：覆蓋率無法分離紅綠樣本
```

兩個根因，都是結構性的：

1. **coverage 算在 top hit 上，而 top hit 定義上就是命中最多 query token 的那筆。** 只要語料裡任何一筆命中了全部 token，它就會排到第一，coverage 恆等於 1。這個度量對 top-1 結構上不可用。
2. **原假設「判別性 token 不在索引裡」是假的。** 查 df 才發現：`staging` df=12、`rm` df=123、`-rf` df=52、`todo` df=31、`function` df=81。噪音查詢的 token 全都在語料裡，所以問題不是「命中太少」，而是「**字面命中 ≠ 主題相關**」。門檻調不出來，因為信號一開始就不在字面層。

這一輪最有價值的產出是那條「重疊就 exit 1」的規則：它讓實作端在度量失效時**誠實停手**，而不是把門檻調成剛好過驗收的數字。

---

## 4. 收斂：把已知形狀的坑搬回確定性層

回頭看數據：整層 bm25 只有兩個 case 真的有用，而那兩個 case 的**指令形狀是已知且固定的**（`git push --force`、`git reset --hard`）。這正是 `pitfalls.tsv` 的形狀——該檔自述就寫著「BM25 搜不到純符號的坑（`===`、`${PIPESTATUS}`、`--short` 多 rev），所以需要這一層」。

所以：

- `pitfalls.tsv` 加兩列（`ID<TAB>tool<TAB>regex<TAB>action<TAB>advice`，action 一律 `warn`），advice 直接取自對應條目的 `**Rule:**`。精度不依賴任何門檻，命中就是命中。
- hook 刪掉 bm25 的 `destructive` 觸發與 `DESTRUCTIVE_RE`；上一輪已刪 `enumeration`（Grep/Glob 的 pattern 當查詢鍵，實測 0/6 有用）。
- bm25 層只留 `consecutive-failures` 一個觸發——它的查詢鍵**取自錯誤輸出**，不是指令原文，那才是語意檢索該做的事。
- `fxsearch.py` 的 `coverage` 欄與校準腳本整個刪掉（零資訊量的欄位留著只會被下一個人當真）。`title` / `rule` 兩欄保留，hook 改吃 `--json` 而不是拿 regex 剝 ANSI 輸出。

同時修掉的兩個宣告≠生效問題：

- `FIX_DIR` 預設路徑寫的是一個不存在的目錄，能跑只因 shell 恰好 export 了 `FIXINDEX_DIR`；拔掉環境變數後每行退化成 `[fix NNNN] Fix`，而且照樣記帳成「注入成功」。
- 生效檔與版控鏡像漂了 159 行（先前只改生效檔沒回推），驗收步驟補上回推＋乾淨樹斷言。

---

## 5. 驗收（紅樣本在內，主 session 自己重跑）

```
1. git push --force        → [fix 9246] force push 前先驗證無共同祖先＋遠端僅孤立 init commit…
2. git reset --hard        → [fix 9489] 不可逆操作先用 branch／備份把它變可逆，再談授權…
3. git push（無 force）    → （無注入）
4. rm -rf staging / node_modules / Grep TODO / Glob *.js → 全部（無注入）
5. 紅樣本：抽掉那兩列後再打 force push → （無注入）＝門確實擋在新列上，不是別層在頂
6. COVERAGE_MIN 0｜DESTRUCTIVE_RE 0｜enumeration 0｜校準腳本 NO｜consecutive-failures 3
7. 既有 hook 測試 cases=10 pass=10 fail=0 / ALL GREEN（含「自測未污染生產狀態」一條）
```

淨效果：bm25 觸發 3 → 1；git 破壞性召回從機率性猜測（2/3、1/3）變成確定性精確比對；零資訊注入行 8/22 → 0。噪音查詢現在輸出完全空白，連注入上限的額度都不佔。

---

## 6. 給未來的自己

1. **要給檢索加棄權閘門前，先用 df 驗證你以為的判別性 token 是否真的 out-of-vocabulary。** df>0 就代表問題是「字面命中≠主題相關」，門檻再調都是白工。
2. **禁用絕對分數門檻**（跨查詢不可比、語料成長會漂）**與 top-hit 查詢覆蓋率**（結構上恆為 1.0）。要門檻先正規化，而且要算在候選集合而非 top-1 上。
3. **指令形狀已知的坑，用確定性比對表，不要用檢索。** 檢索只留「查詢鍵取自錯誤輸出」的觸發。
4. **驗收一定要有紅樣本，而且紅樣本要能證明門是擋在你新加的東西上。** 抽掉新列後仍然命中，就代表斷言是空包彈。
5. **度量失效時讓驗收腳本 exit 1，不要留「折衷值」的後門。** 本輪就是靠這條才沒把一個恆為 1.0 的度量當成可用門檻上線。
6. **`set -e` 下負向斷言禁寫 `cmd && { exit 1; }`**——命令回非零會直接中止腳本，斷言永遠不會失敗。一律寫 `if cmd; then exit 1; fi`。
