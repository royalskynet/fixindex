---
id: 0046
slug: mannie-optimization-progress-and-max-autonomy-plan
title: Mannie 優化外部卷進度與最大自主執行計畫
tags: [mannie, hermes-agent, optimization, execution-plan, progress, handoff]
symptoms:
  - "Mannie 優化 plan 總共多少章目前完成多少"
  - "需要盡可能交給 Mannie 完成的執行計畫"
  - "health checker 和 LSP 測試已有草稿但仍未追蹤"
  - "X0 X1 X2 完成 X3 X4 部分 X5 X6 X7 Final 未完成"
status: active
supersedes: []
related: [0039, 0041, 0042, 0043, 0044, 0045]
---

# 0046 Mannie 優化進度與最大自主計畫

## §1 2026-08-03 進度快照

**Symptom:** 舊 summary、Mannie 草稿與 live git 狀態不同，容易把 partial 誤報 completed，也未清楚劃分 Mannie 可完成範圍。

**Root cause:** 外部卷、Mannie 卷、未追蹤 WIP、Fixindex 0042–0045 各自更新，缺單一 evidence-backed 進度與責任表。

**Fix:** 外部卷固定為 9 章 `X0–X7 + Final`。X0/X1/X2 完成=`3/9=33%`；X3/X4 partial；X5/X6/X7/Final 未完成。Hermes `HEAD=origin/main=cce4becacd5bdca9aff4da8453463736b8a3a207`，目前三個未追蹤 WIP：health checker、health checker tests、LSP tests。

**Verify:** `git status --short` 顯示上述三檔；`git rev-parse HEAD` 與 `git rev-parse origin/main` 均回傳 `cce4becacd5bdca9aff4da8453463736b8a3a207`。

## §2 最大自主執行決策

**Symptom:** 使用者要求需要決定的直接決定，並盡量讓 Mannie 完成。

**Root cause:** 舊分工把部分離線實作、Fixindex 文件與驗收設計留給外部，增加交接面。

**Fix:** 新增 `/Users/51mini/.claude/plans/MANNIE_MAXIMUM_AUTONOMOUS_EXECUTION_PLAN_20260803.md`。Mannie 負責 A0–A8：preflight、M1/M3 修補與測試、M2/M4 報告、Fixindex 校正、離線整合、live gate 腳本、交接包。外部只保留 git 發布、live mutation/probe、credential/cost 與 Final 簽核。決定維持 OmniRoute-only；不新增 direct provider 或費用；無失敗證據不重啟 gateway。

**Verify:** Plan 明列決策、threshold、停止條件、逐 phase 輸出與完成定義；X7 預設 `DEFERRED（OmniRoute-only）`。

## §3 Fixindex 真實性校正

**Symptom:** 0042/0043 標 completed 但證據不足；0044/0045 無正確狀態；0039 使用不安全 `push -f`。

**Root cause:** 草稿產出即被當完成，缺第三方反向驗證與遠端租約保護。

**Fix:** 0042–0045 改 partial 並附缺口；0039 改 manual clean-tree rebase + regression + `push --force-with-lease`，記錄 native update 對 local commits preserve/skip。

**Verify:** `fixindex re-index` 後，以「盡可能交給 Mannie」、「health checker 未追蹤」、「fork force-with-lease」反查可命中。

## §4 Fixindex 發布完成

**Symptom:** 進度若只留在 working tree，下一個 session 或設備無法可靠取得。

**Root cause:** 0041–0046 原為未追蹤草稿，`FIX-INDEX.md` 也只存在本地修改。

**Fix:** 校正、re-index 後，以 commit `94f44b8`（`fixes: record Mannie optimization progress and handoff plan`）推送 `origin/main`；包含 0039 SOP 修正、0041–0046 與索引。

**Verify:** push 回應 `dc343ff..94f44b8 main -> main`；兩個 symptoms query 命中 0046，`push --force-with-lease` grep 命中 0039/0046。
