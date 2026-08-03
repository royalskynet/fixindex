---
id: 0047
slug: A5-fixindex-correction
title: "Phase A5: Fixindex 校正與完整紀錄"
tags: ["mannie", "fixindex", "phase-A5"]
symptoms:
  - "0042-0045 fixindex records 需降級為 draft（A1-A4 完成，A6 待驗收）"
  - "0039 確認 push --force-with-lease 已正確"
status: draft
---

## Fix Actions

| Fixindex | 狀態變更 | 理由 |
|----------|----------|------|
| 0042 | partial → **draft** | A1 完成但 A6 整合測試未過；`related: ["0043", "0045"]` |
| 0043 | partial → **draft** | A3 完成但 A6 待驗證；`related: ["0042", "mannie-m2r-background-review-denied"]` |
| 0044 | partial → **draft** | A2 完成；`related: ["0045", "mannie-m4-patch-lifecycle"]` |
| 0045 | partial → **draft** | A4 定稿；`related: ["0042-0044"]` |
| 0039 | done ✅（無需修正） | 第 39 行 `push --force-with-lease` 已正確；Mannie 維持 git 唯讀、不改版控 |

### 人格層問題結論

| 問題 | 答案 |
|------|------|
| 「當時的指引」有嗎？ | `SOUL.md`：完成聲明必須有實際證據；`AGENTS.md` Fable-style：Outcome first、Bounded retry |
| 應寫入人格層？ | **不**。AGENTS.md 明文：不存 task progress、session outcomes、completed-work logs。勿重複存過期資訊 |

## Current Matrix

| ID | Status | Phase | Reviews |
|----|--------|-------|---------|
| 0039 | done | fork workflow | — |
| 0042 | draft | A1 health checker | need A6 |
| 0043 | draft | A3 bg-review | need A6 |
| 0044 | draft | A2 LSP | need A6 |
| 0045 | draft | A4 patch lifecycle | need A6 |

## Verify

- fixindex re-index 成功
- 0042-0045 狀態改 draft
- 0039 無需變更