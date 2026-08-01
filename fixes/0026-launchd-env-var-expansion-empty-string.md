## §26 launchd 服務的 `${VAR}` 展開成空字串 —— Mannie 事件

**Symptom:**
- `Missing Authentication header` 錯誤（而非 `Invalid API key`），措辭本身證明 header 缺席
- `.env` 檔案中 key 存在
- `ps eww -p <pid>` 查實際進程環境：變數不在環境中（為空字串或 unset）
- 問題在沒被 launchd 讀進去，而非 key 無效

**Root cause:**
launchd plist 中使用 `${VAR_NAME}` 語法讀取環境變數，但該變數並未在 plist 的 `EnvironmentVariables` 鍵下定義，於是展開成空字串。`.env` 檔案僅供本機腳本使用，launchd 不會自動掃讀。

**Fix:**
1. 把所需的 key（如 `OPENROUTER_API_KEY`、`NIM_API_KEY`）直接寫入 launchd plist 的 `EnvironmentVariables` 字典
2. 或者改用 `EnvironmentFile` 指向 `.env`（需要 launchd 版本支援）
3. 測試：`launchctl print gui/501/<label>` 確認變數出現在環境中
4. 重新載入：`launchctl kickstart -k gui/501/<label>`（不需重啟整個 launchd）

**Verify:**
- `ps eww -p $(pgrep -f strip-proxy)` 能看到變數正確傳入
- `/v1/models` 呼叫返回模型列表而非 401

**Retrospective:**
- `.env` 檔案存在 ≠ launchd 能讀到
- 必須檢查實際進程環境（`ps eww`），而非 soltanto檢查 `.env`
- launchd 的 `${VAR}` 展開只作用於其內部定義的鍵，外部檔案不會自動掃入