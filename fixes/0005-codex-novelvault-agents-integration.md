---
id: 0005
slug: codex-novelvault-agents-integration
symptoms:
  - codex手機窗口無法操作NovelVault
  - codex不知道奙子cascade紀律
  - 兩窗口改寫日誌格式不一致
  - 手機改vault無git安全網
cause: |
  NovelVault 無 AGENTS.md，codex 不知道奙子側的 cascade 紀律、工具範本、日誌格式、canon 邊界。
  codex config.toml 未掛 obsidian / smart_connections MCP。
  codex AGENTS.md 無玄君書路由指引。
fix: |
  1. 新建 ~/NovelVault/AGENTS.md（150 行）——萃取 xuanjun config 的 cascade 紀律、工具範本、改寫日誌格式、git 安全網
  2. 追加 obsidian + smart_connections MCP 到 ~/.codex/config.toml
  3. 追加玄言書路這一段到 ~/.codex/AGENTS.md（切目錄 + 遵守 AGENTS.md）
  4. git snapshot 4f5e7d9 封裝導入前狀態（含奙子側 35 檔待改動）
files:
  - ~/NovelVault/AGENTS.md (new)
  - ~/.codex/config.toml (append 2 MCP servers)
  - ~/.codex/AGENTS.md (append route section)
related_fixes: [0127, 0166]
---

# codex↔奙子 NovelVault 整合

## 問題

使用者要用手機 Happy → codex session（danger-full-access，MCP 直接改檔）討論劇情/設定，但兩個窗口沒有共用同一套紀律。

## 解法

不要造新 GitHub 工具——既有堆疊（obsidian-mcp + smart_connections + git）已足夠。只需讓 codex 知道奙子那套 cascade 紀律：

1. **AGENTS.md**（NovelVault 根）——codex 進 vault 第一個讀的紀律檔。內容：canon 宣告、語言鎖、工具範本（從奙子 config 照抄）、cascade 流程、改寫日誌格式、git 安全網、一致性守則
2. **MCP servers**——obsidian + smart_connections，與奙子同級，各自起一份 MCP（共享狀態是檔案本身）
3. **路由段**——codex 全域 AGENTS.md 加一行，討論玄君書自動切 `~/NovelVault`

## 驗證

- 等 codex session 重啟後確認 MCP 工具出現
- 用手機 Happy 問「宋棠的身世？」→ 應切目錄、讀 INDEX、smart_connections 檢索 → 回覆繁中 wikilink

## 關鍵檔案

- 參照來源：`~/.hermes/profiles/xuanjun/config.yaml`（canon、cascade 流程、工具範本）
- 既有格式：`~/NovelVault/_嫙子改寫日誌.md`
- vault 索引：`~/NovelVault/VAULT-MAP.md`、`~/NovelVault/xuanjun/00-INDEX.md`
