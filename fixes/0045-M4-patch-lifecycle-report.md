---
id: 0045
slug: M4-patch-lifecycle-report
title: "Phase M4: 補丁生命週期 read-only 報告"
tags: ["mannie", "patch", "lifecycle", "phase-M4", "git-history"]
symptoms:
  - "需要稽核現有 patch set、cron job 更新機制與技能版本追蹤，產出唯讀報告"
status: draft
---

## Symptom

MANNIE_MAXIMUM_AUTONOMOUS_EXECUTION_PLAN 要求（§6 A4）：
1. 重做 `upstream/main..HEAD` 唯讀報告
2. 逐 commit 對應 symbol、caller、regression test、上游差異
3. `43c219c038`、`3942af1b37`、`cce4becacd` 分類為保留／重寫／上游吸收／資料不足
4. 不臆造 cron schema 擴充，不把未要求的新功能塞入此修復案
5. 輸出 `.claude/plans/evidence/mannie-m4-patch-lifecycle.md`

## Root cause

當前 Hermes 代碼庫有三層「版本/補丁」機制但互不連通：
- **Local patch set**：3 個 commit 載於 `upstream/main` 之上，無自動化分類
- **Cron job**：`jobs.json` 無 version/patch_history 欄位；`update_job()` 只改當前狀態，不留痕跡
- **Skill**：`skill_usage.bump_patch()` 追蹤 `patch_count` / `last_patched_at`，但 cron job 無對應機制

## Fix (唯讀分析)

### 1. Commit 概覽

| Commit | 日期 | 分類 | 檔案數 | ± 行數 | 主要領域 |
|--------|------|------|--------|--------|----------|
| `43c219c038` | 2026-08-02 | **大合併/重新錨定** | 35 | +2704/-40 | 全域：admission、auto-goal、goal、/llm、bg-review、compression、file_tools、mcp、LSP、telegram、holographic、LINE、calendar、terminal |
| `3942af1b37` | 2026-08-03 | **修復/測試補強** | 7 | +1268/-5 | auxiliary_client（admission busy 503）、kanban_db（notify 繼承）、6 個新測試檔 |
| `cce4becacd` | 2026-08-03 | **優化/最小化** | 2 | +49/-25 | holographic retrieval：query vector 重用、deterministic clock |

### 2. 逐 Commit 分析

#### 2.1 `43c219c038` — 大合併/重新錨定

**性質**：Local patch set rebased onto upstream `0a62610f1`；35 檔、2704 行增刪

| 子項目 | Symbol/Caller | Regression Test | 上游差異 | 分類 |
|--------|---------------|-----------------|----------|------|
| Admission backoff（fixindex 0037） | `agent/auxiliary_client.py:_is_admission_busy_error`、`call_llm` retry loop | 無（此 commit 僅重新錨定） | Upstream 無 503 classifier | **保留** — 需 3942af1b37 補測試 |
| Auto-goal（fixindex 0032） | `agent/goals.py`、`turn_finalizer.py`、gateway arming hooks | 無 | Upstream 無 auto-goal 機制 | **保留** |
| Goal state migration | `agent/system_prompt.py`、`agent/goals.py` | 無 | Upstream 目標系統不同 | **保留** |
| /llm command | `cli.py`、`gateway/slash_commands.py`、`hermes_cli/commands.py` | 無 | Upstream 無 /llm | **保留** |
| Background review whitelist | `agent/background_review.py`（prompt + deny message） | 無 | Upstream 無 bg-review | **保留** |
| Compression taxonomy（fixindex 0033） | `agent/context_compressor.py` | 無 | Upstream 錯誤分類較簡 | **保留** |
| File tools suggested_limit | `tools/file_tools.py` | 無 | Upstream 只有 truncation | **保留** |
| MCP keepalive/probe | `tools/mcp_tool.py` | 無 | Upstream 行為不同 | **保留** |
| LSP manager sync wrappers | `agent/lsp/manager.py`：`definition_sync`、`references_sync`、`document_symbols_sync`、`workspace_symbols_sync` | 無（A2 新增 27 tests） | Upstream 無同步 wrapper | **保留** |
| Telegram inbound audit | `plugins/platforms/telegram/adapter.py`：`[TG-AUDIT]` | 無 | Upstream 無 audit | **保留** |
| Holographic HRR + CJK | `plugins/memory/holographic/retrieval.py`、`store.py`、`__init__.py` | `test_holographic_prefetch.py`（154 行） | Upstream 無 HRR/CJK | **保留** |
| LINE text label | `plugins/platforms/line/adapter.py` | 無 | Upstream 無 LINE | **保留** |
| Calendar tool | `tools/calendar_tool.py` | 無 | 新工具 | **保留** |
| Terminal tool keepalive | `tools/terminal_tool.py` | 無 | Upstream 無對應 | **保留** |

> **資料不足**：此 commit 包含 `generated with Claude Code` 等說明，多項修改無獨立測試、無上游 PR 參考。需依 A6 整合測試驗證。

#### 2.2 `3942af1b37` — 修復/測試補強

**性質**：針對 43c219c038 引入的 admission/aux/notify 三大缺口，補充修復 + 完整測試

| 檔案 | 修改重點 | Symbol | 新測試 | 上游差異 | 分類 |
|------|----------|--------|--------|----------|------|
| `agent/auxiliary_client.py` | 1) `_is_admission_busy_error` guard 在 retry 前 raise（防 shadow）<br>2) `_relay_sync/async_completion` 取代原生 `create`（aux relay 不繞過 fallback） | `_is_admission_busy_error`、`call_llm`、`async_call_llm`、`_relay_*` | `test_admission_busy.py`（352 行，17 條件）<br>`test_invalid_aux_response_and_payment_fallback.py`（327 行）<br>`test_model_incompatible_fallback.py`（314 行） | Upstream 無 admission busy classifier/relay | **保留** — 修復 43c219c038 遺漏 |
| `hermes_cli/kanban_db.py` | `_inherit_notify_subs`：新增 `chat_type`、`delivery_metadata` 欄位（繼承完整 metadata） | `_inherit_notify_subs` | `test_inherit_notify_subs.py`（86 行） | Upstream notify schema 較簡 | **保留** |
| `tests/agent/test_background_review_whitelist.py` | 背景審查白名單機制測試 | — | 144 行 | Upstream 無 bg-review | **保留** |

> **結論**：此 commit 是**必要修復層**，補上 43c219c038 的測試與邊界缺口。全部保留。

#### 2.3 `cce4becacd` — 優化/最小化

**性質**：Holographic retrieval 效能優化，無行為變更

| 檔案 | 修改 | Symbol | 測試 | 分類 |
|------|------|--------|------|------|
| `plugins/memory/holographic/retrieval.py` | `prefetch_candidates`：重用 query vector（避免重複 encode）、deterministic clock（取代 `time.time()`） | `prefetch_candidates`、`_encode_query` | `test_holographic_prefetch.py`（+37/-4 行，既有擴充） | **保留** — 效能優化，向後相容 |

### 3. 分類總表

| 分類 | Commits | 風險 | 行動 |
|------|---------|------|------|
| **保留** | 全部 3 commits | 低 | 納入 A6 整合測試，外部發布時一併 commit |
| **重寫** | 無 | — | — |
| **上游吸收** | 無（upstream `0a62610f1` 為基準，此三 commits 全為 local 獨有） | — | — |
| **資料不足** | `43c219c038` 中 14 子項缺獨立測試/上游對照 | 中 | A6 必須跑全測試集；失敗者標 `BLOCKED` |

### 4. 關鍵 Symbol 清單（供外部審查）

```
agent/auxiliary_client.py:
  - _is_admission_busy_error
  - call_llm / async_call_llm（含 relay 分支）
  - _relay_sync_completion / _relay_async_completion

agent/background_review.py:
  - _build_review_prompt（白名單告知）
  - spawn_background_review_thread（whitelist 設置）

agent/lsp/manager.py:
  - definition_sync / references_sync / document_symbols_sync / workspace_symbols_sync
  - enabled_for（workspace gating）

agent/goals.py + agent/turn_finalizer.py:
  - auto-goal 觸發邏輯
  - goal migration across compression

plugins/memory/holographic/retrieval.py:
  - prefetch_candidates（query vector reuse）
  - _encode_query

hermes_cli/kanban_db.py:
  - _inherit_notify_subs（chat_type + delivery_metadata）

plugins/platforms/telegram/adapter.py:
  - [TG-AUDIT] 事件發射點
```

### 5. Fixindex 關聯

| Fixindex | 對應 Commit | 狀態 |
|----------|-------------|------|
| 0031 | goal migration | → `43c219c038` 保留 |
| 0032 | auto-goal | → `43c219c038` 保留 |
| 0033 | compression taxonomy | → `43c219c038` 保留 |
| 0037 | admission backoff | → `43c219c038` + `3942af1b37` 保留 |
| 0043 | bg-review denied | → `43c219c038`（whitelist）+ `3942af1b37`（測試）保留 |
| 0030 | LSP symbol tools | → `43c219c038`（manager sync）+ A2（契約測試）保留 |
| 0045 | patch lifecycle | → 本報告（draft） |

## Verify

- `git log --oneline upstream/main..HEAD` → 3 commits（cce4becacd, 3942af1b37, 43c219c038）
- `git diff --stat upstream/main...HEAD` → 37 files changed, 3951 insertions(+), 70 deletions(-)
- A2 LSP contract tests: 27/27 passed
- A1 Health checker tests: 24/24 passed
- A3 BG review report: evidence file written

## Conclusion

- **全部 3 commits 歸類為「保留」**，無「重寫」、「上游吸收」項目
- 唯一風險：`43c219c038` 為大合併，14 子項缺獨立回歸測試 → **A6 離線整合驗收必須跑完整測試集**（health checker、LSP contract、X1/X2 既有 136 tests、敏感資訊掃描），任一失敗即標 `BLOCKED`

詳細報告見：`.claude/plans/evidence/mannie-m4-patch-lifecycle.md`