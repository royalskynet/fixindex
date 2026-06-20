---
id: "0003"
slug: free-claude-code-model-mapping
title: free-claude-code (fcc) sonnet/opus 映射模型持續 Provider API request failed
tags: [free-claude-code, fcc, nvidia-nim, model-routing, provider, gpt-oss-120b, thinking-injection, mistral-large, server-down]
symptoms:
  - "free code 持續 Provider API request failed (request_id=req_xxxx)"
  - "fcc 某 tier (sonnet/opus) 映射的免費模型一直失敗"
  - "改了 repo .env 模型映射卻沒生效"
  - "opus tier 回 Invalid request sent to provider / NIM 400 BadRequest，但直打模型 200"
  - "fcc server 沒跑 / port 8082 沒監聽，發請求就報 Provider API request failed"
status: active
supersedes: []
related: ["0002"]
---
# 0003 free-claude-code-model-mapping

`~/free-claude-code`（Anthropic 相容 gateway，把 claude 模型名映射到免費 provider）某 tier 映射的模型持續報 Provider API request failed。

## §1 改 repo .env 沒生效 —— active config 在 managed env

**Symptom:** 編輯 `~/free-claude-code/.env` 的 `MODEL_SONNET=` 後重啟仍是舊模型。

**Root cause:**
- `config/paths.py`：env 載入低→高優先級為 `repo_env`(`~/free-claude-code/.env`) → **`managed_env`(`~/.fcc/.env`)**。
- Admin UI(`/admin`）寫的是 `~/.fcc/.env`，它**覆蓋** repo `.env`。改 repo 檔等於改了被覆蓋的底層，無效。

**Fix:**
- 真正要改的是 **`~/.fcc/.env`**（managed），不是 repo `.env`。

## §2 sonnet 映射模型持續失敗 → 換乾淨的 120b

**Symptom:** `MODEL_SONNET=nvidia_nim/qwen/qwen3.5-397b-a17b`（或 nemotron-3-super-120b-a12b）持續 Provider API request failed。

**Root cause:**
- model id 多半有效（NIM `/v1/models` 查得到、直打 chat/completions HTTP 200）。
- 真凶常是**模型 reasoning 格式不乾淨**：如 `nvidia/nemotron-3-super-120b-a12b` 把 reasoning **同時塞進 `content` 與 `reasoning_content`**，gateway 做 Anthropic 翻譯時雙重 content → 爆。
- `openai/gpt-oss-120b`（NVIDIA NIM 託管、免費）回 `content:null` + reasoning 分離，乾淨可用。

**Fix:**
1. 拿 key 直打 NIM 確認模型存活與格式：
   ```bash
   KEY=$(grep '^NVIDIA_NIM_API_KEY' ~/.fcc/.env | sed -E 's/.*="?([^"]*)"?/\1/')
   curl -s https://integrate.api.nvidia.com/v1/models -H "Authorization: Bearer $KEY" \
     | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)['data']]"
   ```
2. 在 `~/.fcc/.env` 設 `MODEL_SONNET=nvidia_nim/openai/gpt-oss-120b`（FREE ONLY）。
3. **熱重載免重啟 server**（不殺進行中的 fcc-claude session）：
   ```bash
   curl -s -X POST http://127.0.0.1:8082/admin/api/config/apply \
     -H "Content-Type: application/json" \
     -d '{"values":{"MODEL_SONNET":"nvidia_nim/openai/gpt-oss-120b"}}'
   ```
   端點做 `get_cached_settings.cache_clear()` + 重建 ProviderRegistry；`restart.required:false` 即無痛生效。只送要改的欄位，其他不動。

**Verify:** 透過 gateway 發 sonnet 請求確認路由與回應：
```bash
curl -s http://127.0.0.1:8082/v1/messages -H "x-api-key: freecc" \
  -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":64,"messages":[{"role":"user","content":"reply with exactly: ROUTING_OK"}]}'
```
回 `"model":"openai/gpt-oss-120b"` + `ROUTING_OK` + HTTP 200 → 修好。

## §3 opus tier 持續 400 BadRequest / "Invalid request sent to provider" → thinking 參數打到非 reasoning 模型

**Symptom:** `MODEL_OPUS=nvidia_nim/mistralai/mistral-large-3-675b-instruct-2512`，gateway 回 `Invalid request sent to provider.`；日誌 `NIM_ERROR exc_type=BadRequestError http_status=400`。但直打 NIM `/v1/chat/completions` 同模型 **HTTP 200 content 正常**。

**Root cause:**
- 模型本身存活且乾淨（直打 200）。400 只發生在**經過 gateway** 時。
- gateway 對 opus tier 預設 thinking-enabled，往 NIM 請求體注入 `extra_json.chat_template_kwargs={thinking:true, enable_thinking:true, reasoning_budget:N}`（外加 `parallel_tool_calls:true` 但 `tools=0`）。
- `mistral-large-3-675b` **不是 reasoning 模型**，不認 `enable_thinking`/`reasoning_budget` 模板參數 → NIM 回 400。
- 對比：直打不帶 thinking → 200；gateway 帶 thinking → 400。與 §2 不同（§2 是回應雙 content，§3 是請求注入 thinking）。

**Fix:** opus tier 換成**支援 thinking 的乾淨免費模型**。`nvidia_nim/openai/gpt-oss-120b`（NIM 託管、免費、支援 reasoning）經 gateway 驗證可路由 + 回內容。用 §2 step3 的 apply 熱重載：
```bash
curl -s -X POST http://127.0.0.1:8082/admin/api/config/apply \
  -H "Content-Type: application/json" \
  -d '{"values":{"MODEL_OPUS":"nvidia_nim/openai/gpt-oss-120b"}}'
```

**Verify:** gateway 發 opus 請求（`claude-opus-4-6`）回 `routed_model=openai/gpt-oss-120b` + 真實 content + 無 error marker。

**診斷關鍵:** 抓 gateway 發給上游的請求體 —— 日誌 `DEBUG logging "Request options: {...json_data...extra_json...}"`，比對直打 NIM 的 body 差在哪個注入欄位。

## §0 server 根本沒跑 → 先確認進程

報 Provider API request failed 前先查 server 是否活：`lsof -nP -iTCP:8082 -sTCP:LISTEN`。日誌尾 `Shutdown requested / Server shut down cleanly` 表示被主動停過、未重啟。重啟：`cd ~/free-claude-code && nohup fcc-server >/dev/null 2>&1 &`（console script，入口 `cli.entrypoints:serve`）。

**Note:** 模型映射改動不需重啟進程（`pending_fields:[]`）；只有 HOST/PORT 等才需重啟。auth token `ANTHROPIC_AUTH_TOKEN=freecc`。
