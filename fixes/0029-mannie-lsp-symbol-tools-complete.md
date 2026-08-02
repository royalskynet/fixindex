---
id: 0029
slug: mannie-lsp-symbol-tools-complete
title: LSP Symbol Tools 完整實作 (A1-A3) — client.py + manager.py + lsp_tool.py + toolsets.py
tags: [lsp, hermes-agent, symbol-navigation, fixindex]
symptoms:
  - "LSP 只做了一半（尚未修，記錄現狀）"
  - "缺少 definition/references/document_symbols/workspace_symbols 同步方法"
  - "缺少對外可用的 LSP symbol 工具 (lsp_document_symbols 等)"
  - "toolsets.py 未註冊 lsp toolset 導致 CLI/平台無法使用"
status: fixed
supersedes: []
related: ["0028-mannie-silent-amnesia-compression-chain", "0020-lsp-symbol-tools"]
---
# 0029 mannie-lsp-symbol-tools-complete

## 背景
fixindex 0028 §10 記載：「LSP 只做了一半（尚未修，記錄現狀）」。`agent/lsp/client.py` 已有四個 LSP symbol 方法，但缺：
1. `manager.py` 的同步包裝方法（A2）
2. 對外工具 `tools/lsp_tool.py`（A3）
3. `toolsets.py` 的註冊（A3）

本修記錄完整補齊過程。

## §1 A2：manager.py 新增同步 + async 方法

**Symptom:** `manager.py` 無 `definition_sync`/`references_sync`/`document_symbols_sync`/`workspace_symbols_sync`，上層無法同步調用 LSP symbol 查詢。

**Root cause:** `client.py` 已有 async 方法，但 `LSPService` (manager.py) 只實作了 `get_diagnostics_sync`，未遵循相同 pattern 補齊 symbol 方法。

**Fix:**
- 在 `from agent.lsp.client import ...` 加入 `ERROR_METHOD_NOT_FOUND`
- 在 `_get_or_spawn` 的 `finally` 區塊後、`async def _shutdown_async` 前插入 4 個 async 內部方法：`_async_definition`、`_async_references`、`_async_document_symbols`、`_async_workspace_symbols`
- 在 `def shutdown` 前插入 4 個同步包裝方法：`definition_sync`、`references_sync`、`document_symbols_sync`、`workspace_symbols_sync`
- 所有方法帶 `# [local-patch] LSP symbol tools — see fixindex 0020-lsp-symbol-tools.` + `# Re-apply after hermes upgrade.`

**關鍵細節：**
- 同步方法完全仿照 `get_diagnostics_sync`：
  ```python
  if not self.enabled_for(path): return []
  t = timeout if timeout is not None else self._wait_timeout + 2.0
  return self._loop.run(self._async_xxx(path, ..., timeout=t), timeout=t) or []
  ```
- async 方法 pattern：
  ```python
  client = await self._get_or_spawn(path)
  if client is None: return []
  await client.open_file(path, language_id=language_id_for(path))
  return await asyncio.wait_for(client.xxx(path, ...), timeout=timeout)
  ```
- `workspace_symbols_sync` 的 `anchor_path: Optional[str] = None` fallback `os.getcwd()`，且 `_async_workspace_symbols` 不呼叫 `open_file`（workspace query 不需要）
- Pyright 型別錯誤修正：4 個 `_async_*` 方法簽名改為 `timeout: Optional[float] = None`（sync 層保證傳非 None）

**Verify:** `python3 -c "from agent.lsp import get_service; svc = get_service(); print(svc.definition_sync.__module__)"` 正常載入；Pyright 無 diagnostics。

---

## §2 A3：建立 tools/lsp_tool.py

**Symptom:** 無對外工具可供 agent 使用 LSP symbol 功能。

**Root cause:** 缺少 `tools/lsp_tool.py` 模組與 `registry.register` 註冊。

**Fix:** 新建 `tools/lsp_tool.py`（374 行），包含：
- `_trim_to_limits(result, max_bytes, max_lines)` — 用 `tools.tool_output_limits.get_max_bytes()/get_max_lines()` 截斷輸出
- `_format_symbols(symbols, indent)` — 扁平 Markdown list 呈現 DocumentSymbol 樹，SymbolKind 1-26 對應名稱，行號 1-based
- `_get_service()` — `from agent.lsp import get_service` + `svc.is_active()` gate，未啟用回錯誤字串
- 4 個 handler：
  - `tool_lsp_document_symbols(path)` → `svc.document_symbols_sync(path)`
  - `tool_lsp_definition(path, line, character)` → `svc.definition_sync(path, line, character)`
  - `tool_lsp_references(path, line, character, include_declaration=False)` → `svc.references_sync(...)`
  - `tool_lsp_workspace_symbols(query, anchor_path=None)` → `svc.workspace_symbols_sync(query, anchor_path)`
- 每個 handler 尾端 `registry.register(name="lsp_xxx", toolset="lsp", schema=..., handler=..., check_fn=..., emoji="🔍")`

**修正過程：**
- 刪除重複的 `_format_symbol_tree` 定義（Pyright `reportRedeclaration`）
- 修正 `svc.breakings_sync` typo → `svc.references_sync`

**Verify:** 模組 import 正常；4 個 `registry.register` 呼叫存在。

---

## §3 A3：toolsets.py 註冊

**Symptom:** 新工具未在任何 toolset 中，CLI 與所有 messaging platform 無法使用。

**Root cause:** `_HERMES_CORE_TOOLS` 未包含 4 個新工具名稱；缺 `lsp` toolset 定義。

**Fix:**
1. `_HERMES_CORE_TOOLS`（第 31-73 行）末尾加入：
   ```python
   # LSP symbol navigation (gated on LSP being enabled + language server available)
   "lsp_document_symbols", "lsp_definition", "lsp_references", "lsp_workspace_symbols",
   ```
2. 在 `spotify` toolset 之後、Scenario-specific toolsets 之前新增 `lsp` toolset：
   ```python
   "lsp": {
       "description": "Language Server Protocol tools for code navigation and symbol lookup. Requires LSP enabled in config.yaml and a supported language server available for the file's extension.",
       "tools": ["lsp_document_symbols", "lsp_definition", "lsp_references", "lsp_workspace_symbols"],
       "includes": []
   }
   ```

**Verify:**
```python
from toolsets import get_toolset, resolve_toolset
t = get_toolset('lsp')
# {'description': '...', 'tools': ['lsp_document_symbols', 'lsp_definition', 'lsp_references', 'lsp_workspace_symbols'], 'includes': []}
r = resolve_toolset('lsp')
# ['lsp_definition', 'lsp_document_symbols', 'lsp_references', 'lsp_workspace_symbols']
```

---

## §4 遺留問題（非本修引入）

**Symptom:** `tools/registry.py:182` 型別標註 `Callable | None` 在 Python < 3.10 語法錯誤（`TypeError: unsupported operand type(s) for |: '_CallableType' and 'NoneType'`），導致 `discover_builtin_tools()` 無法 import 驗證。

**Root cause:** 既有程式碼使用 Python 3.10+ union syntax，但環境可能較舊或 mypy/pyright 設定不相容。

**Fix:** 非本任務範圍。建議改為 `Optional[Callable]` 或 `Union[Callable, None]`。

---

## Retrospective / 教訓

1. **Patch 錨點要帶足夠 context**：第一次嘗試用 `# ---` 為錨插入 manager.py 方法失敗（8 處匹配），改用 `def shutdown` 區塊為唯一錨點成功。
2. **Pyright 型別錯誤要真改簽名**：`float | None` 不能傳給 `float` 參數，改 async 方法簽名為 `Optional[float] = None` 解決，而非用 `cast` 掩蓋。
3. **工具輸出限制用現有工具**：`tools/tool_output_limits.py` 已有 `get_max_bytes()/get_max_lines()`，不要硬編碼常數。
4. **local-patch 標記必帶**：所有修改既有檔案處需帶 `# [local-patch] ... # Re-apply after hermes upgrade.` 便於升級後重套。
5. **Registry 自動發現機制**：`tools/registry.py` 的 `discover_builtin_tools()` 掃描 `tools/*.py` 的 AST 找 `registry.register(...)` 呼叫，新增檔案無需手動改 loader。
6. **先查 fixindex 再動手**：本次開工前跑 `fixindex find "LSP"` 命中 0028 §10 確認缺口，避免重複造輪子或遺漏既有 pattern。