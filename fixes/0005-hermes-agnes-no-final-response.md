---
id: "0005"
slug: hermes-agnes-no-final-response
title: Hermes 接 Agnes AI custom provider 設定 + 「no final response was produced」已知 harness bug
tags: [hermes, hermes-agent, agnes-ai, custom-provider, openai-compatible, no-final-response, content-null, tool-calls, vllm, nousresearch, cc-switch, fallback-provider]
symptoms:
  - "hermes -z 回 no final response was produced; treating the run as failed.，且無錯誤 log"
  - "Hermes agent turn 跑完 tool 後空回 / 無 final assistant text"
  - "Hermes log 報 Model returned no content after all retries"
  - "Hermes 報 cannot access local variable 'assistant_msg' where it is not associated with a value"
  - "Agnes / 小 flash 模型接 Hermes 後 agent loop 拿不到 final response"
  - "cc-switch 套 Agnes 報 HTTP 400 Expecting ',' delimiter / 503 No available channel"
  - "Hermes 剛設好 custom provider 後間歇 HTTP 401 无效的令牌 AgnesAI_error，但 curl 同 key 全 200"
status: active
supersedes: []
related: ["0002", "0003"]
---
# 0005 hermes-agnes-no-final-response

把 Agnes AI（`agnes-ai.com`，OpenAI 兼容 gateway）接進 Hermes Agent 當 custom provider。**key/config 全對、HTTP 層全綠**，但 `hermes -z` 仍回 `no final response`。根因是 Hermes agentic harness 對「模型回 `content:null`」的**已知上游 bug**，不是設定錯。

## §1 正解：Hermes custom OpenAI-compatible provider 設定

官方 docs（[providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)）證實：`base_url` 一旦設了，Hermes **直連該端點、忽略 provider 名**，用 `api_key` 或 `OPENAI_API_KEY` 認證。

`~/.hermes/config.yaml` 的 `model:` 區塊：
```yaml
model:
  default: "agnes-2.0-flash"
  provider: "custom"
  base_url: "https://apihub.agnes-ai.com/v1"
```
`~/.hermes/.env`（600 權限，key 別塞進 world-readable 的 config.yaml）：
```
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://apihub.agnes-ai.com/v1
```
改前先備份：`cp config.yaml config.yaml.bak.$(date +%Y%m%d_%H%M%S)`、`.env` 同理。
驗證：`hermes doctor` 應出現 `✓ API key or custom endpoint configured`。

**Agnes 端點**：`https://apihub.agnes-ai.com/v1/chat/completions`，OpenAI 兼容，vLLM 後端。
**Models**（`/v1/models` 撈）：文字 `agnes-1.5-flash`、`agnes-2.0-flash`；另有 `agnes-image-*`、`agnes-video-*`。key 格式 `sk-`。
官方文檔提的高精度 **Claw 系列**文字模型 **free/一般 key 拿不到** —— 直接點名 `claw-*` 回 HTTP **503「No available channel」**（帳號沒分配到該後端 channel，需更高方案）。即 flash 是這把 key 的天花板，null-content agentic 病無法靠換 Agnes 內部模型解，要靠 fallback / 換主備。

## §2 「no final response was produced」根因 = Hermes harness 已知 bug

**Symptom:**
```
$ hermes -z "say hi"
hermes -z: no final response was produced; treating the run as failed.
```
無錯誤 log（Hermes 吞了）。

**Root cause:** 不是 config/key 問題。raw curl 同 key/model/端點，**streaming + tool-calling 全正常**。是 Hermes agentic harness 已知 bug：模型發 tool_call 時回 `content:null`（Agnes vLLM 後端確實這樣回），工具跑完模型又回空 content → Hermes 撞 `Model returned no content after all retries` / unbound `assistant_msg` 失敗路徑。
上游 issue：[#17248](https://github.com/NousResearch/hermes-agent/issues/17248)（empty final after tool calls）、[#34452](https://github.com/NousResearch/hermes-agent/issues/34452)（turn ends empty after tools）。小 flash 模型（`agnes-2.0-flash`）特別容易觸發。

**Fix / 緩解（非根治，bug 在 Hermes 端）：**
- 設能穩定回 content 的 fallback：Agnes 當主、NVIDIA NIM 兜底（[docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers)）。`hermes fallback add` 是純互動 picker（無 flag），無頭環境改 `config.yaml` 直接寫 **top-level** `fallback_providers`（schema 見 `hermes_cli/fallback_config.py`：list of `{provider, model, base_url?}`）：
  ```yaml
  fallback_providers:
    - provider: nvidia
      model: meta/llama-3.3-70b-instruct
      base_url: https://integrate.api.nvidia.com/v1
  ```
  `.env` 配 `NVIDIA_API_KEY=nvapi-...`。NIM OpenAI 端點 `https://integrate.api.nvidia.com/v1`，`meta/llama-3.3-70b-instruct` 回正常 content + tool_calls，不踩 null bug。驗證：`hermes fallback list`。
- **⚠️ caveat**：fallback **只在 rate-limit / 5xx / connection error 觸發**，**不接** no-final-response（harness 內部 bug，非失敗類）也不接 401（non-retryable client error 直接 abort）。要靠 fallback 救 no-final-response 是無效的。
- 真要 agentic 穩，把 NIM `meta/llama-3.3-70b-instruct` 拉成 **primary**（回 content 穩），Agnes 降 fallback。
- 純 chat / 簡短 prompt（不觸發 tool call）多半正常 —— 設好 fallback 後實測 `hermes -z` 4/4 通。失敗集中在會觸發 tool-call→空回的 prompt。

## §3 隔離法：raw curl 直打端點，分開 config 問題 vs harness 問題

遇 Hermes 沉默/無 final，**先 curl 直打端點**，把「key/config/provider 問題」跟「Hermes harness 問題」切開：
```bash
KEY=$(grep '^OPENAI_API_KEY=' ~/.hermes/.env | cut -d= -f2)
# 基本
curl -sS https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"agnes-2.0-flash","messages":[{"role":"user","content":"reply: OK"}]}'
# tool-calling（Hermes agent 必用，要驗）
curl ... -d '{"model":"agnes-2.0-flash","messages":[...],"tools":[{"type":"function","function":{...}}]}'
# models 列表
curl -sS https://apihub.agnes-ai.com/v1/models -H "Authorization: Bearer $KEY"
```
curl 綠 + `hermes doctor` 綠 = config 對，剩下是 Hermes 端。curl 紅 = key/端點/model 問題。

## §4 社群雷：別用 Codex /v1/responses wire 接 Agnes

cc-switch [#4143](https://github.com/farion1231/cc-switch/issues/4143)「无法应用agnes」根因是 **Codex `/v1/responses` wire** 轉成 chat completions 時 JSON 截斷（char 28 `Expecting ',' delimiter` → HTTP 400），且 model 沒 remap（送出 `gpt-5.x` → Agnes 503 `No available channel`）。
**結論**：Agnes 走 **chat completions wire**（`/v1/chat/completions`）安全；別走 Codex/responses wire。Hermes custom provider 預設就是 chat completions wire，不踩此雷。

## §6 間歇 HTTP 401「无效的令牌」= setup 空窗期 credential pool 抓錯 token

**Symptom:**
```
⚠️ API call failed: AuthenticationError [HTTP 401]
   Provider: custom  Model: agnes-2.0-flash  Endpoint: https://apihub.agnes-ai.com/v1
   Error: HTTP 401: 无效的令牌 (request id: ...)  type: AgnesAI_error
❌ Non-retryable client error (HTTP 401). Aborting.
```
但同把 key curl 直打 **10/10 全 200**。

**Root cause:** key 有效（`printf '%s' "$KEY" | shasum -a 256 | cut -c1-16` 對得上 `~/.hermes/auth.json` 裡 openai-api 的 `secret_fingerprint`）。401 是 **Hermes 送錯 token**：剛 `provider: custom` 設好、credential pool 還沒把 `openai-api`（`env:OPENAI_API_KEY`）entry 寫進 `auth.json` 的空窗期，Hermes fallback 抓了 pool 裡**另一筆 cred（如 copilot 的 `gh auth token`，同 priority 0）**送去 agnes 端點 → 「无效的令牌」。時間線可證：`.env` 寫 key → 數分後 401 報錯 → 報錯**之後** `auth.json` 的 `updated_at` 才登錄 openai-api。

**Fix:** pool 登錄後**自癒**，無需動作。確認法：
```bash
hermes auth list            # 應見 openai-api (1 credentials) #1 ... ← 且 base_url 指 agnes
KEY=$(grep '^OPENAI_API_KEY=' ~/.hermes/.env | tail -1 | cut -d= -f2)
printf '%s' "$KEY" | shasum -a 256 | cut -c1-16   # = auth.json secret_fingerprint 後 16 hex → key 對
```
若仍間歇 401（pool 多筆同 priority 互搶）：`hermes auth remove <copilot-id/label>` 把無關 cred 移出，或拉開 priority，只留 agnes 那筆給 custom 端點。

## §5 檢討 / 經驗

- **官方文檔要查到「正主」**：第一輪只查了 Agnes doc + cc-switch issue（周邊），沒查 Hermes 自己的官方文檔，被連問兩次「查过官方文档吗」。SOP 第1步「查日誌與文檔」—— 問題出在工具 X，就要查 **X 的官方 docs + X 的 GitHub issues**，不是只查跟 X 互動的第三方。查了 Hermes 官方 providers/FAQ + GitHub issues 才證實是上游 bug。
- **doctor 綠 + curl 綠 ≠ 功能可用**：config 正確跟 agentic loop 可用是兩件事。別看到 `✓ configured` 就宣告成功（Fail Loud）。
- **隔離優先**：raw curl 一招把問題域從「我的 config」縮到「Hermes harness」，省掉瞎調 config。錯誤連鎖警戒 —— 別在 config 上反覆換變體，先驗到底哪層壞。
