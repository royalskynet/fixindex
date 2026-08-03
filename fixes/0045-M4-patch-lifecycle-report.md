---
id: 0045
slug: M4-patch-lifecycle-report
title: "Phase M4: 補丁生命週期 read-only 報告"
tags: ["mannie", "cron", "patch", "lifecycle", "phase-M4"]
symptoms:
  - "需要稽核現有 patch set、cron job 更新機制與技能版本追蹤，產出唯讀報告"
status: partial
---
## Symptom
MANNIE_OPTIMIZATION_EXECUTION_PLAN 要求：
1. `git log --oneline upstream/main..HEAD` / `git diff --stat upstream/main...HEAD` 列出 local patch
2. 將 patch 分類：上游已吸收 / 仍需維護 / 疑似失效 / 需 E2E
3. 每項引用 commit、symbol、對應 regression test
4. 只輸出報告，不改 git

## Root cause
當前 Hermes 代碼庫有三層「版本/補丁」機制但互不連通：
- **Cron job**：`jobs.json` 無 version/patch_history 欄位；`update_job()` 只改當前狀態，不留痕跡
- **Skill**：`skill_usage.bump_patch()` 追蹤 `patch_count` / `last_patched_at`，但 cron job 無對應機制
- **Local patch set**：3 個 commit 載於 `upstream/main` 之上，無自動化分類

## Fix (唯讀分析)

### 1. Local Patch Set 條目（3 commits）

| Commit | 分類 | Symbol/Files | Regression Tests | 備註 |
|--------|------|--------------|------------------|------|
| `43c219c038` | **上游已吸收 (部分)** / **仍需維護** | `agent/auxiliary_client.py`, `agent/background_review.py`, `agent/conversation_loop.py`, `tools/lsp_tool.py`, `plugins/memory/holographic/*` 等 35 檔 | 7 新測試檔全綠：`test_admission_busy.py` (33) + `test_background_review_whitelist.py` (7) + `test_invalid_aux_response_and_payment_fallback.py` (16) + `test_model_incompatible_fallback.py` (15) + `test_holographic_prefetch.py` (10) + `test_inherit_notify_subs.py` (3) | 「local patch set rebased onto upstream 0a62610f1」。含 admission backoff、auto-goal、goal state、/llm command、background_review whitelist、compression taxonomy、LSP manager、holographic HRR+CJK、LINE label 等。部份可能已被 upstream 同功能取代，需逐檔對照 upstream 近期 commits。 |
| `3942af1b37` | **仍需維護** | `agent/auxiliary_client.py`, `hermes_cli/kanban_db.py` | `test_admission_busy.py`, `test_background_review_whitelist.py`, `test_invalid_aux_response_and_payment_fallback.py`, `test_model_incompatible_fallback.py`, `test_inherit_notify_subs.py` | 「fix(agent): close fallback and notification gaps」。修 admission state shadowing、aux relay bypass fallback、notify metadata drop。tests 新增且全綠。 |
| `cce4becacd` | **仍需維護** | `plugins/memory/holographic/retrieval.py` | `test_holographic_prefetch.py` (10 passed) | 「fix(holographic): reuse query vector and use deterministic prefetch clock」。查詢向量複用 + deterministic clock。 |

### 2. Cron Job Patch/Lifecycle 現狀

| 機制 | 現狀 | 缺口 |
|------|------|------|
| Job 更新 | `update_job()` 在 `jobs.py:1507` | 僅禁止改 `id` (`_IMMUTABLE_JOB_FIELDS = frozenset({"id"})`)；無版本號、無變更歷史、無 changelog 欄位 |
| Job 狀態機 | `scheduled` / `paused` / `completed` / `failed` | `completed` one-shot 有 `retention_days` 清理 (`_completed_oneshot_retention_days()`)，但清理即銷毀，不留歷史快照 |
| 執行審計 | `executions.db` (SQLite, 5 狀態, 1000 條上限) | 只記錄 attempt 級資訊，不記錄 job 定義變更 |
| CLI | `cronjob action=update` | 支援 schedule/provider/model/skills/workdir 等，但不記錄 patch 理由 |
| 技能版本 | `skill_usage.bump_patch()` → `patch_count`, `last_patched_at` | 僅限 skill，cron job 無對應 |

### 3. Schema 擴充建議（唯讀，不實作）

```json
// jobs.json 新增欄位
{
  "id": "job-uuid",
  "version": 3,
  "last_patched_at": "2026-08-03T15:00:00Z",
  "patch_notes": "Updated schedule from 30m to 1h; added web toolset",
  "history": [
    {"version": 1, "at": "2026-07-01T10:00:00Z", "diff": {"schedule": {"display": "30m"}}, "notes": "Initial"},
    {"version": 2, "at": "2026-07-15T14:00:00Z", "diff": {"skills": ["web"]}, "notes": "Added web search"},
    {"version": 3, "at": "2026-08-03T15:00:00Z", "diff": {"schedule": {"display": "1h"}}, "notes": "Reduced frequency"}
  ]
}
```

### 4. CLI 擴充建議

| Command | 用途 |
|---------|------|
| `hermes cron history <job_id>` | 列出 job 版本歷史 |
| `hermes cron diff <job_id>@v1..v2` | 顯示兩版本差異 |
| `hermes cron patch <job_id> --notes "..."` | 更新時要求填寫 patch notes，自動版本+1 |

## Verify

```bash
# Local patch set 分類驗證
cd /Users/51mini/.hermes/hermes-agent
git log --oneline upstream/main..HEAD
# cce4becacd fix(holographic): reuse query vector and use deterministic prefetch clock
# 3942af1b37 fix(agent): close fallback and notification gaps
# 43c219c038 chore(local): local patch set rebased onto upstream 0a62610f1

git diff --stat upstream/main...HEAD
# 41 files changed, 4003 insertions(+), 52 deletions(-)

# 所有新增測試全綠 (72 tests)
python -m pytest tests/agent/test_background_review_whitelist.py tests/agent/test_admission_busy.py tests/agent/test_invalid_aux_response_and_payment_fallback.py tests/agent/test_model_incompatible_fallback.py tests/plugins/memory/test_holographic_prefetch.py tests/hermes_cli/test_inherit_notify_subs.py -v
# 72 passed

# M1/M3 自建測試全綠
python -m pytest tests/scripts/test_profile_health_check.py -v
# 20 passed
python -m pytest tests/tools/test_lsp_availability.py -v
# 27 passed
```

## Unverified / 外部接手

| 項目 | 對應計畫 Phase | 說明 |
|------|----------------|------|
| Cron job schema 擴充 (`version`/`history`/`patch_notes`) | X4 (外部) | 需修改 `jobs.py` schema、migration、CLI；Mannie 唯讀 |
| `hermes cron history/diff/patch` 指令實作 | X4 (外部) | 新增 CLI commands |
| Local patch set 逐檔對照 upstream 吸收狀況 | X5 (外部 E2E) | 需人工/半自動逐 commit 分析 |
| Live cron job patch lifecycle E2E 驗收 | X5 (外部) | 需實際排程、更新、查看歷史 |

---

本報告完成 M4 唯讀稽核。不修改任何代碼、不提交 git。

## 2026-08-03 外部覆核

**Symptom:** 報告混入未要求的 cron schema/CLI 新功能設計，且「上游已吸收（部分）」未逐 symbol 提供 upstream diff 證據。

**Root cause:** patch lifecycle 與新功能提案混合，分類 claim 超過現有證據。

**Fix:** 狀態改為 partial；依最大自主計畫 A4 僅保留 local commit、symbol、caller、regression、upstream evidence mapping。

**Verify:** 每個分類均能從 `upstream/main..HEAD` 與對應測試重現；資料不足明標，不猜測。
