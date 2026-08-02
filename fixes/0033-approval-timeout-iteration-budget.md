---
id: 0033
slug: approval-timeout-iteration-budget
title: Approval-timeout iterations burned budget silently; compression failures didn't distinguish timeout vs malformed response
tags: [mannie, hermes-agent, iteration-budget, context-compressor, approval]
symptoms:
  - "BLOCKED: Command timed out without user response"
  - "Tool terminal returned error (300.6"
  - "Failed to generate context summary: Request timed out"
  - iteration budget exhausted right after a 5-minute approval wait
  - compression failure log doesn't say whether the aux model replied or not
status: active
supersedes: []
related: [0031-goal-lost-on-compression, 0032-max-iterations-no-continuation]
---
# 0033 approval-timeout-iteration-budget

## §1 待批准逾時吃掉 iteration 預算（A3）

**Symptom:** `agent.log` 出現兩筆 `Tool terminal returned error (300.6Xs): {"output": "", "exit_code": -1, "error": "BLOCKED: Command timed out without user response. The user has NOT consented..."}`（8/01 16:35、17:33）。17:33 那筆之後 67 秒該回合就撞 40/40 max_iterations 結束 — 5 分鐘白等，且錯誤訊息明說「不准重試」，等於這個 iteration 純損失。

**Root cause:** `tools/approval.py` 的 gateway/ask 逾時分支（`check_all_command_guards` 內，約 :1317-1340）回傳 `{"approved": False, "outcome": "timeout", ...}`，但 `tools/terminal_tool.py` 建構最終 JSON（原 :1883-1888）時只保留 `error` 文字訊息，沒有把 `outcome` 往上傳。`agent/tool_executor.py` 的兩個 `logger.warning("Tool %s returned error...")` 站點（concurrent :373、sequential :805）因此無法區分「逾時無回應」跟其他任何工具錯誤，歸因得靠人工重讀錯誤文字。

同時，`agent/iteration_budget.py` 的 `consume()`/`refund()` 是每輪迭代呼叫一次（`conversation_loop.py:696` 附近 consume，budget 重建在 `:393`），不是每個工具呼叫。approval 逾時發生在某次迭代內的某個 tool call 裡，那次迭代（consume 已發生）因此被「浪費」。

**評估過的方案 A（不採用）：逾時時 `iteration_budget.refund()`。**
拒絕理由：模型若忽略 BLOCKED 訊息裡「不准重試」的指示、持續重送同一個危險指令，refund 會讓每次逾時都把預算還回去，導致該回合的 iteration 數永遠不收斂（每 300 秒燒一次牆鐘時間但budget 用量歸零），使用者要等到手動 /stop 才能結束。這違反「不計入預算的改動若導致某些情況下無法收斂就不該做」的判準。

**採用方案：只加明確標記 + log，不動 budget 收斂邏輯。**

**Fix:**
1. `tools/terminal_tool.py`（約 :1883）：approval 被拒絕時，若 `approval.get("outcome")` 存在（目前只有 gateway/ask 逾時路徑會設），把它原樣塞進回傳 JSON 的新欄位 `approval_outcome`。
2. `agent/tool_executor.py`：新增 `_approval_timeout_note(function_name, function_result)` — 偵測 `function_name == "terminal"` 且回傳 JSON 含 `approval_outcome == "timeout"`，回傳一則 `ITERATION-BUDGET-NOTE: ...` 字串。在 concurrent（:373 附近）與 sequential（:805 附近）兩個 `is_error` 分支各加一行 `logger.warning(_budget_note)`，只在符合條件時多印一行，不影響原本的 warning。

**Verify:** 用 `tools.terminal_tool.terminal_tool()` 真實呼叫（monkeypatch `tools.approval._get_approval_config` 把 `gateway_timeout` 壓到 1 秒、註冊一個永不 resolve 的 `register_gateway_notify` callback，對一個會觸發 dangerous-command 偵測的指令如 `rm -rf /tmp/...`）跑出：
```
{"output": "", "exit_code": -1, "error": "BLOCKED: Command timed out without user response. ...", "status": "blocked", "approval_outcome": "timeout"}
```
再把這個 JSON 字串餵給 `agent.tool_executor._approval_timeout_note("terminal", result_json)`，回傳 `ITERATION-BUDGET-NOTE: ...`。全程呼叫的是生產函式本身（`inspect.getsource` 確認過），不是重寫的等價邏輯。

**受影響檔案：** `tools/terminal_tool.py`、`agent/tool_executor.py`

---

## §2 壓縮失敗歸因分不清 timeout 與格式錯（A4-c）

**Symptom:** `agent.log` 6 次（8/01 14:56、18:32、19:04、20:08、20:48、23:29）都印：
```
WARNING agent.context_compressor: Failed to generate context summary: Request timed out.. Further summary attempts paused for 30 seconds.
INFO agent.auxiliary_client: Auxiliary compression: connection error on custom (Request timed out.), trying fallback
```
訊息文字雖含「timed out」，但無法從 log 直接確認：這是真的網路逾時（aux 模型完全沒回），還是模型回了但 body 不是合法 JSON（如反向代理回 502 HTML page）。兩者根因與後續動作不同，歸因時得靠猜。

**Root cause:** `agent/context_compressor.py` 的 `_generate_summary()` 例外處理（約 :1095-1192）內部其實已經算出 `_is_timeout` / `_is_json_decode` / `_is_model_not_found` / `_is_streaming_closed` 四個分類旗標（用於決定要不要 fallback 到 main model 重試），但最終落地的 `logger.warning("Failed to generate context summary: %s. ...")` 沒有把分類寫進去 —— 分類資訊算出來了卻被丟掉。

**Fix:** 在同一個 except 區塊，落地 log 前用既有旗標算出 `_failure_category`（`malformed_response` > `model_unavailable` > `timeout` > `unknown`，`_is_json_decode` 優先於逾時判定，因為「模型回了但解析失敗」跟「完全沒收到回覆」是不同故障模式），寫進新屬性 `self._last_summary_error_category`，並把 log 訊息改成 `"Failed to generate context summary [category=%s]: %s. ..."`。同時在 `__init__`、`on_session_reset()`、成功路徑、`compress()` 的每呼叫重置區塊都同步重置這個新屬性，避免殘留舊分類。

**`compression.abort_on_summary_failure: true` 的實際行為**（`agent/context_compressor.py:1642-1655`，呼叫端 `agent/conversation_compression.py:327-334`）：摘要生成失敗時，`compress()` 直接 `return messages`（原封不動），設 `_last_compress_aborted = True`；呼叫端偵測到這個旗標後**不做任何 session 輪替**，往使用者發一次（去重）警告「Compression aborted: ...，No messages were dropped — conversation continues unchanged. Run /compress to retry, or /new to start a fresh session.」，然後直接把系統提示 + 原始 messages 回傳。結論：**不會截斷、不會回合中斷、不會資料遺失** —— 是 fail-open 到「這輪暫不壓縮」，不是 fail-closed。唯一風險：若壓縮持續失敗（如觀測到的 6 次），未壓縮的訊息會持續累積，可能在下一輪逼近或超過模型真實 context window（`config.yaml` 的 `context_length` 已於本輪之前修正為 128000，緩解了視窗誤判，但沒有解決「壓縮持續失敗導致視窗持續逼近上限」本身）。此風險本輪只指出，不動 `config.yaml`。

**Verify:** monkeypatch `agent.context_compressor.call_llm`（`_generate_summary` 呼叫的正是這個模組層名稱）直接丟出兩種例外，餵給真實的 `ContextCompressor._generate_summary()`：
- `Exception("Request timed out.")` → log 印出 `[category=timeout]`，`_last_summary_error_category == "timeout"`
- `json.JSONDecodeError("Expecting value", "<html>502 Bad Gateway</html>", 0)` → log 印出 `[category=malformed_response]`，`_last_summary_error_category == "malformed_response"`

`inspect.getsource(ContextCompressor._generate_summary)` 確認測試打的是生產程式碼路徑。

**受影響檔案：** `agent/context_compressor.py`

---

## 重貼流程

若這輪改動被回滾（逐檔 `git checkout -- agent/tool_executor.py tools/terminal_tool.py agent/context_compressor.py`），重貼步驟：
1. `tools/terminal_tool.py` 約 :1883：approval 被拒絕的 JSON 回傳裡補 `approval_outcome` 欄位（來源 `approval.get("outcome")`）。
2. `agent/tool_executor.py`：新增 `_approval_timeout_note()` helper，掛在 concurrent（`_is_error`/`is_error` 分支）與 sequential 兩個 `logger.warning("Tool %s returned error...")` 呼叫之後。
3. `agent/context_compressor.py`：`_generate_summary()` 例外處理內，落地 log 前算 `_failure_category`（json_decode > model_not_found > timeout/streaming_closed > unknown），寫入 `self._last_summary_error_category`，log 訊息加 `[category=%s]`；同步在 4 個重置點（`on_session_reset`、`__init__`、成功路徑、`compress()` per-call reset）加 `self._last_summary_error_category = None`（或對應值）。

**不要碰：** `agent/conversation_loop.py:393`／`:696`（consume/rebuild 邏輯本身不動）、`agent/conversation_compression.py`、`auxiliary.compression` 的 provider/model/fallback_chain、`~/.hermes/profiles/mannie/config.yaml` 任何值。
