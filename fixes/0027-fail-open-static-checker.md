## §27 fail-open 的靜態檢查腳本比沒有更糟 —— `scan-undeclared.mjs` 事件

**Symptom:**
- `node scan-undeclared.mjs` 印出 15 個誤報，exit code 卻為 0 → CI/驗收 pipeline 被矇過去
- 誤報內容：`xxx is undeclared`，但實際都在檔案內有宣告
- 腳本從未抓到真正的 `_anomalyIdCounter` 未宣告問題（發生時 exit code 應 ≠ 0）

**Root cause:**
舊版 `scan-undeclared.mjs` 的宣告 regex 使用 `^` 錨定行首：
```
const declaration_regex = /^(let|var|const|function)\s+(\w+)/gm;
```
此 regex 無法匹配縮排宣告（module-scope 常見於頂層嗎？縮排 +2 空格 → `^` 不匹配）、也無法匹配 `async function`。

附帶陷阱：`node script.mjs | tail | grep ...` 取到的 `$?` 是 `tail` 的退出碼（幾乎恆為 0），不是 `node` 的。驗 exit code 不能接管線。

**Fix:**
1. 改用 acorn AST parser 取代 regex：`acorn.parse(fs.readFileSync(f, 'utf8'), {ecmaVersion: 'latest', sourceType: 'module'})`
2. 遍歷 AST 節點找 `Identifier`，比對 scope chain 中是否有對應宣告
3. 自己控制 exit code：0 = 無未宣告引用、1 = 有未宣告引用且報告清單、2 = 語法錯誤
4. 保留原始 `scan-undeclared.mjs` 命名，rename 為 `scan-undeclared.mjs.regex-broken.bak`
5. 新版 `scan-mutable-undeclared.mjs` 同步處理 `const` → `let` 的檢查（非 acorn 核心功能，但對 module-scope mutation 很重要）

**Verify:**
- 不接管線：`node scan-mutable-undeclared.mjs; echo "EXIT: $?"`
- 確認 exit code ≠ 0 時必須有對應的具體變數名稱輸出

**Retrospective:**
- regex 做 scope 分析是已知的抗模式 —— 語言的語法結構需用 parser，不是 regex
- 管線 `$?` 檢查需管取 (`PIPESTATUS`)
- 驗收腳本的 exit code 必須親自驗證 — 不假設「能跑就是對的」