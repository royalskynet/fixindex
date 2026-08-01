---
id: 0023
slug: omniroute-dual-lane-rate-limit
title: OmniRoute NIM/OR 集中消耗、短冷卻重探與 ALL_ACCOUNTS_INACTIVE
tags: [omniroute, hermes, nvidia-nim, openrouter, rate-limit, routing]
symptoms:
  - "Service temporarily unavailable: all upstream accounts are inactive"
  - "ALL_ACCOUNTS_INACTIVE"
  - "All credentials for model deepseek-ai/deepseek-v4-pro are cooling down"
  - "Model-only lockout for nvidia:deepseek-ai/deepseek-v4-pro"
  - "maximum iterations (40) but couldn't summarize"
status: active
supersedes: []
related: []
---
# 0023 OmniRoute 雙泳道配額與 NVIDIA 慢速 probe

## §1 單一路徑集中消耗導致 429／503
**Symptom:** `ALL_ACCOUNTS_INACTIVE`、NVIDIA DeepSeek 反覆 429、Mannie 在第 40 次迭代無法產生摘要；OpenRouter 成功路徑被 20 秒 timeout 誤殺。
**Root cause:** `free-tools-heavy` stopgap 只保留 NIM#2 並採 67/33 NIM/OR，未啟用既有 pool-A/pool-B；NVIDIA 404/429 model lockout 只有 3→96 秒；OR 正常回應可超過 20 秒；global fallback 又固定單吃一個 provider。Mannie 的 40 次是 `agent.max_turns`，不是 API rate limit。
**Fix:** 將 `free-tools-heavy` 改成 50/50 雙泳道：pool-A 為 NIM#1↔`heavy-or-stable`、pool-B 為 NIM#2↔`heavy-or-stable`，外層與內層 sticky 都設 1；兩個 NIM 皆設 `maxConcurrent=1,minTime=15000,rpm=4`；OR timeout 設 45000ms；NVIDIA 404/429 AUTH cooldown 下限設 900000ms；`agent.api_max_retries=1`；停用單模型 `globalFallbackModel`。配置位於 `~/omniroute-free-tools/config/combo-{pool-A,pool-B,free-tools-heavy}.json`，production chunk 備份位於 `~/omniroute-free-tools/backups/rate-limit-20260801-1020/dist-chunks/`。
**Verify:** `node --check` production chunks；受控不存在-model 404 的 runtime log 必須顯示 `900s (connection stays active)`；連續 combo 請求落點應呈 NIM#1、NIM#2、OR、OR 並全為 2xx；觀察 `call_logs` 至少 15 分鐘，確認無 429/5xx/503。
**Retrospective:** OmniRoute npm 安裝缺少完整 build script，production 實跑 `dist/.build/next/server/chunks`，只改 TypeScript source 不會生效；套件升級會覆蓋 chunk 補丁，升級後必須重驗 900 秒 runtime claim。OpenRouter `:free` daily tracker 是 process-memory best effort，重啟會歸零；1000/day 的最終硬限制仍以 OpenRouter upstream header/429 為準。
