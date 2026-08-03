---
id: 0043
slug: M2-bg-review-denied
title: "Phase M2: Background review denied 根因稽核報告"
tags: ["mannie", "background-review", "observability", "phase-M2"]
symptoms:
  - "Background review 子 agent 在每個 turn 結束後觸發"
  - "36 次 denied，主要是 execute_code(13)、read_file(11)"
  - "模型需 2-6 輪 denied 才適應僅允許 4 個工具"
status: partial
supersedes: []
related: ["0042"]
---

# 0043 M2-bg-review-denied

## §1 Background Review Denied 根因稽核報告
**Symptom:** Background review fork (agnies-2.0-flash) 在 137 次觸發中，36 次被 whitelist deny；模型反覆嘗試 execute_code、read_file、search_files 等非允許工具，平均需 2-6 輪才適應。

**Root cause:**
1. Fork 的 `tools[]` 與父 agent byte-identical（為了 Anthropic cache key hit），但 `set_thread_tool_whitelist` 只放行 memory/skill_tool 四個工具。
2. Prompt 中列出可用工具，但 39-20B 模型對 "看到 50+ 工具 -> 實際只能用 4 個" 的認知落差大，需多次 denied 才收斂。
3. `auxiliary.background_review.{provider,model}` 在 mannie config.yaml **未配置**，使用預設的小模型（agnies-2.0-flash），能力不足以一次理解限制。

**Fix (建議，非強制 code change):**
- **建議 1**：在 mannie config.yaml 新增 `auxiliary.background_review` 指向更大模型（如 openrouter/gemini-2.0-flash 或 qwen3-coder），減少 denied 輪數。
- **建議 2**：若保留小模型，接受 denied 為正常收斂過程（不屬 bug）。

**Verify:**
```bash
# 觀察 denied 分布
grep "Background review denied non-whitelisted tool" ~/.hermes/profiles/mannie/logs/agent.log | sed -E 's/.*denied non-whitelisted tool: ([^.]+).*/\1/' | sort | uniq -c
# 期望：execute_code > read_file > 其他；總數隨 review 次數增長但單次 denied 輪數應下降

# 觀察成功 skill/memory 操作
grep -c "tool skill_manage completed\|tool memory completed" ~/.hermes/profiles/mannie/logs/agent.log
# 110 次（持續增長）
```

**Retrospective:** Deny 機制本身正確（保護 review fork 不濫用資源）。核心問題是模型能力不足以一次理解 toolset 差異。最經濟解法是切換 `auxiliary.background_review` 到更強模型；否則 2-6 輪 denied 是可接受的 cold-start cost。

## §2 2026-08-03 外部覆核：根因未成立

**Symptom:** 舊報告缺固定時間窗、session/turn denominator、work type 與 `todo/patch/read_file` 分類，卻直接歸因弱模型並建議換模型。

**Root cause:** 只統計 deny 字串，未排除 protocol、transport、routing、tool/session lifecycle、stale state 等替代解釋。

**Fix:** 狀態改為 partial；取消換模型結論。依最大自主計畫 A3 重做，使用 denies/review-turn 與明確 baseline。

**Verify:** 報告必須能由時間窗、session IDs、numerator/denominator 重算；無 denominator 時標 `UNKNOWN`。
