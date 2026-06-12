---
id: "0001"
slug: lark-meeting-notes
title: lark-meeting-notes / audio-meeting-notes 摘要與 LLM 卡住
tags: [lark, meeting-notes, llm, spawnSync]
symptoms:
  - "UI 按「重新摘要」後轉圈不停，server 無回應"
  - "curl 超時 exit 28"
  - "resummarize 永久卡住、不完成"
  - "spawnSync hang"
status: active
supersedes: []
related: []
---
# 0001 lark-meeting-notes

lark-meeting-notes / audio-meeting-notes 的 LLM 呼叫與摘要流程問題。

## §1 重新生成摘要（resummarize）永久卡住

**Symptom:** UI 按「重新摘要」後轉圈不停，server 無回應，curl 超時（exit 28）

**Root cause:**
1. `spawnSync` 無 `timeout`，`claude -p` 忽略 SIGTERM → server event loop 永久 block
2. `/resummarize` 先呼 `cleanTranscript`（第一次 LLM），再呼 `summarize`（第二次 LLM），串聯總等待 150s+
3. LLM provider 順序 codex 優先，codex 每次啟動需載入 skill 系統（30s+ overhead）

**Fix:**
- `spawnSync` 加 `timeout: 90_000` + `killSignal: "SIGKILL"`（強殺子進程，SIGTERM 被 claude 忽略）
- 移除 `/resummarize` 中的 `cleanTranscript` 前處理（summarize prompt 本身已有 STT 校正邏輯）
- provider 順序改 `claudeCli` 優先

**Verify:** `curl -X POST http://localhost:7321/resummarize` 在 90s 內回應，不超時

**位置:** `src/llm/router.ts`、`src/server.ts`
**commit:** `8d327ac` (2026-06-11)
