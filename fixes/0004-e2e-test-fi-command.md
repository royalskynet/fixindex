---
id: 0004
slug: e2e-test-fi-command
title: "/fi 斜線命令 E2E 驗證——能 scaffold + 填內容 + push 到 fixindex-log"
tags: ["fixindex", "codex-fts", "e2e-test"]
symptoms: ["e2e test fi command fixindex scaffold push", "fixindex new e2e-test-fi-command exit 0", "/fi prompt executed successfully"]
status: active
supersedes: []
related: []
---
# 0004 e2e-test-fi-command

## §1 /fi 斜線命令 E2E 驗證
**Symptom:** `fixindex new e2e-test-fi-command` exit 0, auto-sync push succeeded
**Root cause:** 需要驗證 `/fi` 完整流程（scaffold → 填內容 → re-index → push）
**Fix:** 執行 `fixindex new <slug>` → fill frontmatter + 四欄 → `fixindex re-index`
**Verify:** `fixindex find e2e-test-fi` 命中本條；git log 有對應 commit
