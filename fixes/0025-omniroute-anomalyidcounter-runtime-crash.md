## §25 node --check 過但執行期炸 —— `_anomalyIdCounter` 事件

**Symptom:**
- launchd 每 60 秒重啟 strip-proxy（PID 不斷變、`KeepAlive`）
- 日誌反覆出現 `Strip proxy started`
- `node --check server.mjs` 語法檢查通過 → 誤以為 code 沒問題
- 炸點在 `normalizeAnomaly()` 內的 `_anomalyIdCounter`，但這個函數只在從 handler 呼叫時才經過，3 秒基本冒煙根本踩不到

**Root cause:**
重構時刪掉了 module-scope 的 `let _anomalyIdCounter = 0` 宣告，但函數內仍引用 `_anomalyIdCounter++`。`node --check` 只做 parsing 不做 scope 解析，沒有 SyntaxError 就給 pass。只有延遲觸發的 timer/handler 路徑才會踩到 `ReferenceError`。

**Fix:**
1. 補回 module-scope `let _anomalyIdCounter = 0`
2. 四定時器週期全改為 env 可調（避免硬編碼）：`HARNESS_SWEEP_INTERVAL_MS`、`SESSION_HISTORY_GC_INTERVAL_MS`、`SELFCHECK_INTERVAL_MS`、`SELFCHECK_WARMUP_MS`
3. 12 秒壓縮週期冒煙：把所有定時器設為 2000ms、跑 12 秒、閒置埠（20139），每個定時器至少觸發 5 次
4. `scan-mutable-undeclared.mjs` 用 acorn AST 掃描未宣告的 module-scope 引用（取代舊的 regex 版 `scan-undeclared.mjs`）

**Verify:**
- `scan-mutable-undeclared.mjs` 只印 `_anomalyIdCounter`（精準命中），exit code ≠ 0
- 四定時器壓縮冒煙：每個印出觸發次數 ≥ 5

**Retrospective:**
- `node --check` 不足信 —— 它是語法檢查，不做 scope/執行期檢查
- 3 秒冒煙只測到 port bind 路徑，測不到定時器回呼
- 定時器參數寫死在程式內 → 短冒煙不可行 → 參數化才能做快速循環驗證