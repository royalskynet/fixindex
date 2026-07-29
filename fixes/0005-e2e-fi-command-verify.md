---
id: 0005
slug: e2e-fi-command-verify
title: "/fi 斜線指令 E2E 全驗收"
tags: ["e2e", "fixindex", "fi"]
symptoms: ["e2e fi command verification", "/fi 記 fix log 自動 push"]
status: active
supersedes: []
related: []
---
# 0005 e2e-fi-command-verify

## §1 /fi E2E 全流程驗收
**Symptom:** `fixindex new e2e-fi-command-verify`
**Root cause:** E2E test for /fi flow
**Fix:** `fixindex new <slug>` → edit file → `fixindex re-index`
**Verify:** `fixindex find e2e-fi` hit; git log has commit; `fixindex show 0005` works
