---
id: 0022
slug: heavy-hl-degenerate-circuit
title: Heavy HL agentic 退化、OmniRoute round-robin 飄移與 NIM 本機 queue timeout
tags: [omniroute, claude-code, heavy-hl, openrouter, nvidia-nim, circuit-breaker, launchd]
symptoms:
  - "上游回覆偵測為 agentic 退化，重試後仍未產生工具呼叫"
  - "Request dropped after exceeding the local rate-limit queue budget maxWaitMs (15000ms)"
  - "launchctl bootstrap failed: 5: Input/output error"
  - "NIM deepseek-v4-pro 持續 429 但降 max_concurrent 無效"
  - "429 Too Many Requests 秒拒 265ms 上游直接拒非本機 queue"
  - "调 max_concurrent 1 或 2 對 NIM 429 率無變化"
  - "NIM#1 每輪先 429 再跳 OpenRouter，健康的 NIM#2 被 pool-A 遮蔽"
  - "free-tools-heavy 新 nested pool 上線後最終模型切換率升到 66.7%"
status: active
supersedes: []
related: []
---
# 0022 heavy-hl-degenerate-circuit

## §1 Heavy session 工具後空回並反覆等待
**Symptom:** Claude Code 已成功執行 Bash，工具結果回傳後卻收到「上游回覆偵測為 agentic 退化」，每次約等待 60 秒。
**Root cause:** `free-tools-heavy-or` 使用 14-model round-robin 且 sticky limit=1；弱模型/不相容模型空回後，OmniRoute 又 fallback 到 NVIDIA DeepSeek Flash。NIM 請求不是 upstream timeout，而是在 OmniRoute 本機 request queue 連續兩次超過 15 秒後被丟棄。HL 雖建立 `degenerate-fail-loud` circuit，`/v1/messages` 原本不讀該 circuit。
**Fix:** combo 收斂為實測能產生 tool call 的 OpenRouter Nemotron Super 120B + Cohere North Mini Code，策略改 fill-first，暫時移除 NIM；HL 在 circuit 開啟後只對含既有 `tool_result` 的 agentic request fail-fast，一般問答保持可用。
**Verify:** 經 `:20130` 對 combo 發 tool-call probe，回 `stop_reason=tool_use`；OmniRoute call log 顯示 OpenRouter Nemotron Super、HTTP 200；`/_proxy/status` 顯示 circuit `openCount=0`；`test-heavy-mode.mjs` 驗證 circuit 期間不再呼叫 mock upstream。

## §2 launchd 重裝 Heavy HL 偶發 EIO
**Symptom:** `launchctl bootstrap` 或緊接的 `launchctl load -w` 回 `Bootstrap failed: 5: Input/output error`，20130 暫時離線。
**Root cause:** user LaunchAgent `bootout` 後 launchd 尚未完成移除舊 job，立即 bootstrap/load 命中 race。
**Fix:** installer 先嘗試 bootstrap；失敗後每 2 秒用 legacy user LaunchAgent loader 重試，最多 3 次；健康檢查通過才回成功。
**Verify:** 重跑 installer，20130 回 `mode=heavy-transparent`；PID 25707 保留，Happy session 數不增加。

## §3 NIM deepseek-v4-pro 持續 429 —— `max_concurrent` 是無效槓桿（反證）
**Symptom:** `nvidia/deepseek-ai/deepseek-v4-pro` 當 combo 主力（`free-tools-heavy` fill-first 第 1 順位），持續 429 → fallback 到 OpenRouter。`call_logs` 近 6h nvidia 27.8% 429（1005 次 / 279）。試圖用 `provider_connections.max_concurrent` 限併發止血。
**歸因驗證（重點）：** **併發不是根因，是誤判。** 證據三條：
1. `max_concurrent` 從 `NULL` → `2` → `1` 逐步收緊，429 率**完全不動**（單併發下仍 265ms 秒被拒）。`max_concurrent` 只擋 OmniRoute **本機併發排隊**，擋不了上游 per-account 限流。
2. 429 body 只有 `[429]: {"status":429,"title":"Too Many Requests"}`，**無 `retry-after`、無 `x-ratelimit-*`**（OmniRoute 未捕捉上游 header，看不到窗口類型）。
3. 逐小時看 429 **集中在高峰時段**（07–10 點 55–71%），離峰同一 key 同一模型可掉到 14%（16 點 6/42）。→ 是 NIM free tier 的**帳號級時窗配額 / 全域尖峰限流**，非本機可調。
**對比 §1：** §1 的 `maxWaitMs (15000ms)` 是**本機 queue 超時**（`max_concurrent` 造成排隊 → 等太久被丟），那個 `max_concurrent` / `RATE_LIMIT_MAX_WAIT_MS` 有用；本節的 429 是**上游秒拒**，同一組槓桿無效。**先分清 429（上游）vs maxWaitMs（本機）再決定動哪個旋鈕。**
**Fix（現階段）：** 不再糾結 NIM 併發。`RATE_LIMIT_MAX_WAIT_MS=45000`（配 NIM 成功請求 6–33s 的真實 duration，改對了，屬本機層）＋ fill-first 讓 429 快速 fallback 到 OpenRouter Nemotron（實測秒成功）。真要 NIM 當穩定主力需第二把 NIM key 輪替或改離峰跑，非單機配置能解。
**Verify:** `sqlite3 storage.sqlite "SELECT strftime('%H:00',timestamp) hr,count(*),sum(status=429) FROM call_logs WHERE model='deepseek-ai/deepseek-v4-pro' AND timestamp>=datetime('now','-8 hours') GROUP BY hr;"` → 看 429 是否隨時段起伏（起伏＝配額窗口，恆高＝key/帳號問題）。連線本身健康對照：同 6h `model='connection-test'` 應近 100% 200。
**Retrospective:** 症狀（持續 429）誘導往「限併發」修，但那是驗配置前的臆測。先驗**上游拒 vs 本機拒**（看 duration：秒拒＝上游、卡滿 maxWaitMs＝本機），再選旋鈕。對照 memory `feedback_debug_verify_first`：模型/上游擺最後，但「上游限流」這種**外部不可控**因素也要早點認列，別把可調旋鈕當萬能。

## §4 pool-A 的 OR 成功遮蔽 NIM#2，NIM#1 quarantine 止血（2026-08-01）
**Symptom:** `free-tools-heavy` 改成父層 `priority`、子層 `pool-A → pool-B` 後，NIM#1（`69a315e9`）持續先回 429，再由 pool-A 內的 OpenRouter 成功；父層因此不進 pool-B，NIM#2（`f89610c3`）幾乎收不到流量。新架構 13 分鐘內 40 個 request 全由 OR 完成，NIM#1 21/21 次 429、NIM#2 0 次，最終模型切換率 66.7%。
**Root cause:** nested combo 的 child success 會結束父層 fallback。把 NIM#1 與 OR 放在同一個第一順位 child，等於讓 OR 成為 NIM#1 的就地終點，而不是讓同模型的 NIM#2 先接手。`reset-aware` 又會在短 cooldown 到期後重新把 NIM#1 排前，形成週期性無效 429。三個 OR 模型在 pool-A 內頻繁輪替，放大輸出漂移。
**Fix:** 建立 `free-tools-heavy-stopgap-v1`：父層 `weighted` + `stickyWeightedLimit=12` + `nestedComboMode=execute`，以 67% `heavy-deepseek-stable`（只含 NIM#2）及 33% `heavy-or-stable`（fill-first：Nemotron Ultra → Super → North）形成長駐留區塊。Opus/Sonnet mappings 切到 stopgap；Haiku 保持 OR-only；NIM#1 暫時移出 production combo。兩把 NIM 的 `max_concurrent` 都設 1 作安全上限，但不把它宣稱為 429 根因修復。套用前備份：`~/.omniroute/db_backups/storage-pre-nim1-stopgap-20260801-020557.sqlite`。
**Verify:** OmniRoute 既有 `combo-strategy-fallbacks.test.ts` + `combo-dispatch-prelude.test.ts` 共 43 tests 全綠。重啟後向 `:20129/v1/messages` 發 1 次 `claude-opus-4-8` PONG probe，HTTP 200；`call_logs` 顯示 `combo_name=free-tools-heavy-stopgap-v1`、`combo_execution_key=heavy-deepseek-stable-...f89610c3`、NIM#2 HTTP 200，NIM#1 attempts=0。DB 反向檢查三個 stopgap combos 均不含 `69a315e9`，Haiku mapping 仍指向 `free-tools-heavy-or`。
**Retrospective:** fallback tree 的順序不能只看葉節點清單；nested child 的任何成功都會吃掉父層後續。兩把 NIM 是不同 connection、同一模型，應先切 connection 保持模型一致，再以長區塊切 OR。OR daily quota guard 與 NIM#1 自動低頻探測仍是後續 hardening，不屬本次已完成止血。
