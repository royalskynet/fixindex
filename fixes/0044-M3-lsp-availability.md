---
id: 0044
slug: M3-lsp-availability
title: "Phase M3: LSP 可用性離線契約測試"
tags: ["mannie", "lsp", "testing", "phase-M3"]
symptoms:
  - "需要驗證 LSP 工具在不活躍、無 workspace、broken-set 等情境下的行為"
status: partial
---
## Symptom
驗證 `tools.lsp_tool` 四工具在 LSP 服務不活躍時正確回傳 `"error": "LSP service is not active"`，在輸入參數缺失時回傳具體錯誤，且 broken-set 機制正確存在。

## Root cause
LSP 工具依賴 `_get_service()`（內部）→ `agent.lsp.get_service()` 決定可用性。若 LSP 未啟動（config 未載入、非 git workspace、servers 未安裝），四種 tool handler 應停止在有結構的錯誤訊息而非 fall-through 到空結果。

## Fix
建立離線契約測試 `tests/tools/test_lsp_availability.py`（27 個測試 case）：
- `TestLSPActiveCheck`：4 個測試 → 覆蓋 `_check_lsp_active()` 的四狀態（exception / None / is_active=False / is_active=True）
- `TestLSPToolsWhenInactive`：4 個測試 → `is_active()=False` 時回 `error` 格式
- `TestLSPToolsValidation`：4 個測試 → 缺失必要參數回報錯誤
- `TestLSPToolsWhenActiveEmptyResults`：4 個測試 → 各工具在 non-zero 回傳空結果結構正確
- `TestLSPToolsWhenActiveWithResults`：4 個測試 → 各工具在有效結果時輸出正確 count/locations/content
- `TestLSPConfigContract`：3 個測試 → 確認 `LSPService.create_from_config`、`is_active`、`enabled_for` 合約存在
- `TestLSPBrokenSetContract`：3 個測試 → 確認 `_broken` 初始化在 `__init__`、`enabled_for` 檢查 broken、`_mark_broken_for_file` 新增到 set
- CLI test：`hermes lsp status` 不 crash

**關鍵坑**：Mock 目標需改 `agent.lsp.get_service`（不是 `tools.lsp_tool.get_service`，因 `_check_lsp_active()` 直接在函式內部從 `agent.lsp` 載入 get_service）。

## Verify
```bash
cd /Users/51mini/.hermes/hermes-agent && python -m pytest tests/tools/test_lsp_availability.py -v
# 27 passed (2026-08-03)
```

## 2026-08-03 外部覆核

**Symptom:** 測試檔仍 untracked，主要為 mock/contract；尚無 temp repo real local server 路徑，也不能證明 X5 live `lsp_definition` 成功。

**Root cause:** 離線 handler 測試與 live availability 被當成同一完成條件。

**Fix:** 狀態維持 partial；依最大自主計畫 A2 補 temp repo contract、dependency/skip matrix，live 證據留外部 gate。

**Verify:** A2 tests + 外部 X5 live evidence 分別成立後才可 completed。
