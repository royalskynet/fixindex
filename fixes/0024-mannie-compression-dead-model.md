---
id: 0024
slug: mannie-compression-dead-model
title: Hermes 壓縮模型下架導致壓縮完全停擺、主模型 context 被 probe-down 猜錯
tags: [hermes, mannie, compression, openrouter, omniroute, auxiliary, context-length]
symptoms:
  - "Compression model openrouter/google/gemma-3-4b-it:free (custom) context is 131,072 tokens"
  - "Auto-lowered this session's threshold"
  - "Auxiliary compression model ... below the main model's compression threshold"
  - "Failed to generate context summary: Error code: 400"
  - "is not a valid model ID"
  - "Further summary attempts paused for 60 seconds"
  - "Could not detect context length for model 'free-tools-heavy' — defaulting to 256,000 tokens (probe-down)"
status: active
supersedes: []
related: [0023, 0016]
---
# 0024 Hermes 壓縮鏈：下架模型 + context 猜測

## §1 壓縮模型下架 → 400 → 壓縮完全停擺（不是退回主模型）
**Symptom:** 啟動噴 `⚠ Compression model openrouter/google/gemma-3-4b-it:free (custom) context is 131,072 tokens, but the main model free-tools-heavy (custom)'s compression threshold was 179,200 tokens. Auto-lowered ...`；`~/.hermes/profiles/<p>/logs/agent.log` 接著出現 `Failed to generate context summary: Error code: 400 - {'error': {'message': 'openrouter/google/gemma-3-4b-it:free is not a valid model ID', 'code': 400}}. Further summary attempts paused for 60 seconds.`

**Root cause:** OpenRouter 已下架 `google/gemma-3-4b-it` 的 `:free` 變體（只剩付費版），OmniRoute free model 清單也查無此 id。呼叫回 **400**（不是 404）。400 不屬 payment / connection / 429，**不會**推進 `auxiliary.<task>.fallback_chain`（gate 在 `~/.hermes/hermes-agent/agent/auxiliary_client.py:5070-5085`：`should_fallback` 只認 `_is_payment_error` / `_is_connection_error` / `_is_rate_limit_error`，且非 payment/connection 的 429 還要求 provider 為 `auto`）。實際行為**不是**靜默退回主模型，而是 `context_compressor` 直接放棄該次摘要並暫停 60 秒 —— 長 session 等於**完全沒有壓縮**，context 就那樣撐到爆。

**Fix:** `~/.hermes/profiles/<profile>/config.yaml` 的 `auxiliary.compression` 換成仍在架上、且 context ≥ 主模型 threshold 的模型，並改走本機 OmniRoute（不要 openrouter.ai 直連，直連會繞過 combo 的配額均衡）：

```yaml
auxiliary:
  compression:
    provider: omniroute
    model: openrouter/google/gemma-4-26b-a4b-it:free   # ctx 262,144
    base_url: http://127.0.0.1:20130/v1
    api_key: omniroute-local
    timeout: 120
    fallback_chain:
    - provider: omniroute
      model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free   # ctx 256,000
      base_url: http://127.0.0.1:20130/v1
      api_key: omniroute-local
```

`auxiliary.web_extract` 若用同一個死 id 要一起換。

**Verify:** 先確認模型還活著再改 config，不要靠模型名猜：

```bash
curl -s http://127.0.0.1:20130/v1/models -H "Authorization: Bearer omniroute-local" \
| python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print([(m['id'],m.get('context_length')) for m in d if 'gemma-4-26b' in m['id']])"
```

改完重啟後，在 `logs/agent.log` 應看到 `Auxiliary compression: using custom (openrouter/google/gemma-4-26b-a4b-it:free)`，且 OmniRoute `call_logs` 有一筆該模型的 200 且 `tokens_in` 遠大於 `tokens_out`（實測 11,346 → 1,066，91.5 秒），即為真實摘要而非 probe。

**Retrospective:** `:free` 變體會無預警下架，而 Hermes 對「模型 id 無效」既不 fallback 也不 fail loud，只在 agent.log 留一行 WARNING。定期用 gateway `/v1/models` 對帳 config 裡所有 `auxiliary.*.model`。

## §2 主模型 context 被 probe-down 猜成 256,000
**Symptom:** `agent.log` 反覆出現 `Could not detect context length for model 'free-tools-heavy' at http://127.0.0.1:20130/v1 — defaulting to 256,000 tokens (probe-down). Set model.context_length in config.yaml to override.`，連帶 compression threshold 被算成 `0.7 × 256000 = 179,200`。

**Root cause:** profile 未設 `model.context_length`，且舊版 OmniRoute build 的 `/v1/models` 不回報 combo 的 `context_length`。`~/.hermes/hermes-agent/agent/model_metadata.py:1583` 走到最後的 `DEFAULT_FALLBACK_CONTEXT = 256_000`。179,200 是幻覺值，**高於實際可用 context**，會讓壓縮太晚觸發。該值只在 Ollama/local 分支才寫進 `~/.hermes/context_length_cache.yaml`，這條路徑不快取，所以每次冷啟重探、數字會在 gateway 有沒有回報之間漂移。

**Fix:** 在 profile config.yaml 的 `model:` 區塊釘死：

```yaml
model:
  default: free-tools-heavy
  provider: omniroute
  base_url: http://127.0.0.1:20130/v1
  context_length: 128000
```

值取 gateway 回報值（combo 取所有 target 的最小值 —— `free-tools-heavy` 的瓶頸是 NIM `nvidia/deepseek-ai/deepseek-v4-pro`）。`model_metadata.py:1461-1463` 是 resolver 第 0 步，config 最優先。**不要**改 `compression.threshold` 去湊 —— 官方警告建議的 `0.51` 是拿錯誤的 256,000 算出來的補丁，治標不治本。

**Verify:** 重啟後 `grep 'probe-down' logs/agent.log` 不應再有新行；`grep 'Cached context length' logs/agent.log` 應顯示 aux 模型的正確 context。

## §3 重啟特定 profile 的 gateway：只有 global `--profile` 有效
**Symptom:** 跑 `hermes gateway restart` 回 `✓ Service restarted`，但目標 profile 的 PID 沒變、log 也沒有新的啟動紀錄 —— 實際重啟的是別人。

**Root cause:** `hermes gateway restart` 作用於 sticky current profile（`hermes gateway list` 標 `(current)` 那個），子指令沒有 `--profile` flag（只有 `--system` / `--all`），而 `HERMES_PROFILE=<p>` 環境變數**無效**。實跑 `ps` 可見進程本身是 `hermes_cli.main --profile <p> gateway run`。

**Fix:** 用 **global** flag，位置在子指令之前：

```bash
hermes --profile mannie gateway status    # 先驗，plist 應指向 ai.hermes.gateway-mannie
hermes --profile mannie gateway restart
```

**Verify:** `hermes gateway list` 比對 PID 是否改變；`logs/gateway.log` 應有新的 `Starting Hermes Gateway...` + `Active profile: <p>`。重啟前先確認該 profile 不在 `receiving stream response`（看 gateway.log 最後是否只剩 memory_monitor 心跳）。

**Retrospective:** 誤用會靜默重啟錯誤的 profile 並中斷別人的服務，而輸出仍是 `✓ Service restarted` —— 這是典型「宣告 ≠ 生效」，務必用 PID 對帳。另注意 agent log 在 `~/.hermes/profiles/<p>/logs/agent.log`，不是 `~/.hermes/profiles/<p>/agent.log`。

## §4 OmniRoute 本機 gateway 不驗 Authorization
**Symptom:** config 裡的 `api_key: ${OMNIROUTE_API_KEY}` 指向 `~/.hermes/.env` 中不存在的變數，卻沒有任何 401。

**Root cause:** OmniRoute 20130 完全不檢查 `Authorization` header。實測四組 Bearer 值（有效 key / 未展開的 `${OMNIROUTE_API_KEY}` 字面值 / 空字串 / 亂數字串）全部回 HTTP 200。

**Fix:** 功能上無需修；為避免後人追一個不存在的 credential，把 profile 內所有指向 OmniRoute 的 `api_key` 統一寫成 literal `omniroute-local`（`auxiliary.*` 與 `custom_providers` 兩處都要，容易漏掉後者）。

**Verify:** `grep -c 'OMNIROUTE_API_KEY' config.yaml` 應為 0。

**Retrospective:** 附帶事實 —— 任何本機 process 都能透過 20130 燒掉 OpenRouter 每日 1000 次共用配額。它 bind `127.0.0.1`，暴露面限本機，但若要多用戶或容器共用需另行處理。
