---
id: 0030
slug: lsp-symbol-tools-local-patch-reapply
title: LSP Symbol Tools Local Patch 重貼流程 (A7)
tags: [lsp, hermes-agent, local-patch, fixindex]
symptoms:
  - "Hermes 升級後 LSP 工具標記指向錯誤的 fixindex 條目"
  - "toolsets.py 缺少 LSP 工具的 local-patch 標記"
  - "LSP 工具誤加進 _HERMES_CORE_TOOLS，影響全部 8 個 profile"
status: fixed
supersedes: []
related: ["0029-mannie-lsp-symbol-tools-complete"]
---
# 0030 lsp-symbol-tools-local-patch-reapply

## 背景

前版工作（fixindex 0029）將 LSP symbol tools 加入 `_HERMES_CORE_TOOLS`，影響全部 8 個 profile（koko / penny / shiyue / agnes / effie / cl / xuanjun / mannie）。Mannie 項目改用 `platform_toolsets.cli` 的 opt-in 機制，所以需要：

1. 移除 LSP 工具從 `_HERMES_CORE_TOOLS`（爆炸半徑太大）
2. 更正三處錯誤指向不存在條目的標記
3. 在 `toolsets.py` 補上標記，說明 LSP 工具刻意不放進 `_HERMES_CORE_TOOLS`

## 受影響檔案清單

- `~/.hermes/hermes-agent/toolsets.py`
- `~/.hermes/hermes-agent/tools/lsp_tool.py`
- `~/.hermes/hermes-agent/agent/lsp/client.py`
- `~/.hermes/hermes-agent/agent/lsp/manager.py`

## 改動詳情

### A7-a｜移除 LSP 工具從 `_HERMES_CORE_TOOLS`

**檔案：** `toolsets.py:73-74`

移除這兩行：

```python
    # LSP symbol navigation (gated on LSP being enabled + language server available)
    "lsp_document_symbols", "lsp_definition", "lsp_references", "lsp_workspace_symbols",
```

**理由：** `_HERMES_CORE_TOOLS` 影響全部 8 個 profile。若要限制 LSP 工具只給特定 profile（如 Mannie），必須：
- 刪除 `_HERMES_CORE_TOOLS` 中的條目
- 靠個別 profile 的 `platform_toolsets.cli` opt-in

**保留：** `TOOLSETS["lsp"]` 定義（`:322-334`）不刪，只讓它脫離核心工具集。

### A7-b｜更正並補上 `[local-patch]` 標記

**三個錯誤標記的更正（指向不存在的 0020）：**

1. `tools/lsp_tool.py:338`
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0020-lsp-symbol-tools.
   ```
   改為：
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0030-lsp-symbol-tools-local-patch-reapply.
   ```

2. `agent/lsp/client.py:883`
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0020-lsp-symbol-tools.
   ```
   改為：
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0030-lsp-symbol-tools-local-patch-reapply.
   ```

3. `agent/lsp/manager.py:441`
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0020-lsp-symbol-tools.
   ```
   改為：
   ```python
   # [local-patch] LSP symbol tools — see fixindex 0030-lsp-symbol-tools-local-patch-reapply.
   ```

**新增標記（`toolsets.py` 的 `TOOLSETS["lsp"]` 定義處）：**

在 `toolsets.py:322` 的 `"lsp": {` 前加入標記：

```python
    # [local-patch] LSP symbol tools — see fixindex 0030-lsp-symbol-tools-local-patch-reapply.
    # LSP tools are intentionally NOT in _HERMES_CORE_TOOLS; profiles opt-in via platform_toolsets.
    # Re-apply after hermes upgrade.
    "lsp": {
```

## Hermes 升級後的重貼步驟

### Step 1: 檢查 git 狀態

```bash
cd ~/.hermes/hermes-agent
git status  # 確認無未 commit 的改動
```

### Step 2: 移除 LSP 工具從 `_HERMES_CORE_TOOLS`

編輯 `toolsets.py:73-74`，刪除 LSP 工具的兩行。

### Step 3: 更新三處標記指向新條目

編輯以下三個檔案，將標記中的 `0020-lsp-symbol-tools` 改為 `0030-lsp-symbol-tools-local-patch-reapply`：
- `tools/lsp_tool.py:338`
- `agent/lsp/client.py:883`
- `agent/lsp/manager.py:441`

### Step 4: 在 `TOOLSETS["lsp"]` 補上標記

編輯 `toolsets.py:322`，在 `"lsp": {` 前加入：

```python
    # [local-patch] LSP symbol tools — see fixindex 0030-lsp-symbol-tools-local-patch-reapply.
    # LSP tools are intentionally NOT in _HERMES_CORE_TOOLS; profiles opt-in via platform_toolsets.
    # Re-apply after hermes upgrade.
```

### Step 5: 驗證

```bash
# Python import 驗證
~/.hermes/hermes-agent/venv/bin/python -c "import toolsets"
~/.hermes/hermes-agent/venv/bin/python -c "import tools.lsp_tool"

# 檢查所有標記
grep -rn "local-patch" ~/.hermes/hermes-agent | grep lsp

# 確認 fixindex 條目存在
fixindex find "0030"
```

### Step 6: git commit

```bash
git add toolsets.py tools/lsp_tool.py agent/lsp/client.py agent/lsp/manager.py
git commit -m "A7: Remove LSP tools from _HERMES_CORE_TOOLS, fix local-patch references"
```

## 關鍵設計決策

**為什麼 LSP 工具不在 `_HERMES_CORE_TOOLS`？**

- `_HERMES_CORE_TOOLS` 影響所有 8 個 profile（CLI 端），LSP 是代碼編輯工具，不適合所有場景
- Mannie 專案需要 LSP（程式碼導航），但其他 profile（如 Telegram bot）不需要
- 靠 `platform_toolsets.cli` 的 opt-in 機制，只給需要的 profile 加上（由別項 A7-c 完成）

**為什麼要補標記在 `TOOLSETS["lsp"]` 定義？**

- 提醒維護者：此定義是 local patch，升級後需要重新套用
- 防止「順手」把 LSP 加回 `_HERMES_CORE_TOOLS` 導致迴圈回到舊設計

## 驗收

1. `~/.hermes/hermes-agent/venv/bin/python -c "import toolsets"` → OK
2. `~/.hermes/hermes-agent/venv/bin/python -c "import tools.lsp_tool"` → OK
3. `grep -rn "local-patch" ~/.hermes/hermes-agent` → 涵蓋四個檔案，每個標記指向本條目
4. `_HERMES_CORE_TOOLS` 中無 LSP 工具名稱
5. `TOOLSETS["lsp"]` 存在且定義不變
