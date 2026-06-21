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
  - "Auxiliary title generation failed HTTP 401 无效的令牌，主迴圈正常只有副任務 401"
  - "agent.title_generator 持續 401 不自癒，但 hermes -z 主聊天 200"
  - "auxiliary_client 送 no-key-required placeholder 給需認證雲端 gateway 導致 401"
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

> ⚠️ **本節 root cause 被 §7 部分否證**。「空窗期自癒 / copilot 同 priority 對撞」只解釋**最初幾分鐘**的暫時 401。若 401 **持續復發**（尤其錯誤帶 `agent.title_generator` / 訊息是 `⚠ Auxiliary title generation failed`），那不是 pool 對撞 —— 是 §7 的 **auxiliary_client no-key-required placeholder bug**，主迴圈 200、副任務 401 的 deterministic 分裂。實測：`hermes auth list` 顯示 copilot/openai-api/nvidia 各自獨立 provider、base_url 各自 scoped，pool **不會**跨 provider 抓 key（`load_pool('custom')` 回 none，不是抓 copilot）。先別急著 `hermes auth remove` copilot —— 那基於已否證理論，是無謂破壞。先照 §7 分流。

## §7 持續 HTTP 401「无效的令牌」根因 = auxiliary_client no-key-required placeholder bug【真因】

**Symptom（與 §6 暫時 401 區分）：**
```
⚠ Auxiliary title generation failed: HTTP 401: 无效的令牌 (request id: ...)
```
errors.log / agent.log 標籤是 **`agent.title_generator`**（非主 `conversation_loop`）。特徵：**主迴圈聊天/工具全正常（HTTP 200），只有副任務（標題、壓縮、web 摘要）401**。pool 早登錄完、curl 同把 key 10/10 全 200，**仍持續復發** → 不是 §6 的空窗期，不會自癒。

**Root cause（deterministic，可 100% 重現）：** Hermes `agent/auxiliary_client.py` 對 **bare `model.provider: "custom"`** 的 key 解析漏洞。
- 主迴圈直連時另路讀 `OPENAI_API_KEY` env → 拿到真 key → 200。
- 副任務走 `call_llm(task=...)` → `_try_custom_endpoint()` → `_resolve_custom_runtime()` → `hermes_cli.runtime_provider.resolve_runtime_provider(requested="custom")`。該函式 model-block 分支從 **credential pool** 取 key（`entry.runtime_api_key`，`auxiliary_client.py:1809`），但 `load_pool("custom")` 回 **none**（pool 只有 `openai-api`/`copilot`/`nvidia`，無 `custom`）→ api_key 空 → 落 **`"no-key-required"` placeholder**（`auxiliary_client.py:1849`，原為 local Ollama/vLLM 免認證設計）→ 送 agnes → agnes 要真 token → **401**。
- 證據鏈（venv 重現，attach httpx 攔 Authorization header）：env key fp `22ce8d…`（curl 200），但 aux 實際送 `tok_prefix=no-key-requi` fp `a1435e…`。`resolve_runtime_provider("custom")` 直接回 `api_key_fp=a1435e`（= placeholder 本身），從不讀 env。

**Fix（已驗，外科手術式，key 不落 world-readable config）：** 把 agnes 註冊成 **named custom provider** 帶 `key_env`，主備都指它。`~/.hermes/config.yaml`：
```yaml
model:
  provider: "agnes"          # 改 "custom" → "agnes"（指向下方 named provider）
  base_url: "https://apihub.agnes-ai.com/v1"   # 保留無妨
# ── 新增 top-level ──
custom_providers:
  - name: agnes
    base_url: https://apihub.agnes-ai.com/v1
    key_env: OPENAI_API_KEY   # ← 關鍵：runtime_provider.py L557-562 認 key_env，aux L3769 也認
    model: agnes-2.0-flash
    api_mode: chat_completions
```
named provider 路徑（`runtime_provider.py:643-646`）讀 `key_env` 指名的 env → 解析真 key（`22ce8d`），主迴圈 + 副任務都吃帶 key 的同一 provider。

**驗證（deterministic，免等真 session 觸發標題）：**
```bash
PY=~/.hermes/hermes-agent/venv/bin/python
$PY - <<'EOF'
import os,sys; os.chdir(os.path.expanduser('~/.hermes/hermes-agent')); sys.path.insert(0,os.getcwd())
for l in open(os.path.expanduser('~/.hermes/.env')):
    l=l.strip()
    if l and not l.startswith('#') and '=' in l: k,v=l.split('=',1); os.environ.setdefault(k,v)
from agent.title_generator import generate_title
print(repr(generate_title("list files then say done","DONE",timeout=30,main_runtime=None)))
EOF
# 修前: None（+ log 噴 401）  修後: 'Listing Files Then Done'（200）
```

**雷點：**
- `no-key-required` 是 Hermes 給 **local 免認證 server**（Ollama/llama.cpp/vLLM/LM Studio）的 placeholder。接**需認證的雲端 OpenAI 兼容 gateway**（agnes、任何要 Bearer 的）走 bare `provider: custom` 都會中這個 401，**副任務專屬**。
- 別被 §6 帶偏去刪 copilot cred —— provider 各自 scoped，pool 不跨抓；刪了 copilot 對此 401 無效。
- config 裡 model 區塊註解雖說「可 inline `api_key:`」，但那會把 key 寫進 world-readable `config.yaml`（洩漏）。用 `key_env` 讓 key 留 600 權限的 `.env`。

## §5 檢討 / 經驗

- **官方文檔要查到「正主」**：第一輪只查了 Agnes doc + cc-switch issue（周邊），沒查 Hermes 自己的官方文檔，被連問兩次「查过官方文档吗」。SOP 第1步「查日誌與文檔」—— 問題出在工具 X，就要查 **X 的官方 docs + X 的 GitHub issues**，不是只查跟 X 互動的第三方。查了 Hermes 官方 providers/FAQ + GitHub issues 才證實是上游 bug。
- **doctor 綠 + curl 綠 ≠ 功能可用**：config 正確跟 agentic loop 可用是兩件事。別看到 `✓ configured` 就宣告成功（Fail Loud）。
- **隔離優先**：raw curl 一招把問題域從「我的 config」縮到「Hermes harness」，省掉瞎調 config。錯誤連鎖警戒 —— 別在 config 上反覆換變體，先驗到底哪層壞。
- **「自癒」別當定論，要復查 log 時間戳**：§6 第一輪斷定 401「空窗期自癒」，但 errors.log `00:35-00:36` 仍在噴 —— 設定**完成後**復發，根本沒癒。靠「應該自癒了」收尾＝沒 Fail Loud。先 `tail errors.log` 看最新時間戳對不對得上「已修」的宣稱。
- **錯誤標籤是分流關鍵**：同樣 401 訊息，`conversation_loop`（主迴圈）vs `title_generator`（副任務）是兩個完全不同根因。沒看標籤就套「空窗期/pool 對撞」假設 → 差點去刪 copilot cred（已否證理論的無謂破壞）。讀 error 要讀**發出它的 logger 名**，不只讀訊息字串。
- **deterministic 重現勝過機率猜測**：401「間歇」像 gateway 抖動（不可控），但 venv 直呼 `generate_title` + httpx 攔 header 把它變成 **100% 可重現**（每次都送 `no-key-required`）。一旦能穩定重現，就不是「推給模型/推給 gateway」，是程式碼路徑 bug，能精準修。能重現才能證偽。
- **placeholder 設計的隱性前提**：`no-key-required` 對 local server 合理，對需認證雲端 gateway 是地雷。復用既有機制（bare custom provider）前，先確認它的**設計前提**（免認證）符不符合你的場景（要 Bearer）。
