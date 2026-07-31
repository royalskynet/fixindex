---
id: 0020
slug: twitter-cli-search-timeout
title: twitter-cli search timeout／HTTP 404 — 未登入首頁使 ClientTransaction 初始化失敗
tags: [twitter-cli, agent-reach, mannie, graphql, client-transaction, timeout]
symptoms:
  - "twitter-cli 今天全部超時"
  - "Command timed out after 15s"
  - "Command timed out after 60s"
  - "Command timed out after 45s"
  - "Failed to init ClientTransaction: 'NoneType' object has no attribute 'group'"
  - "Twitter API error (HTTP 404)"
status: active
supersedes: []
related: []
---
# 0020 twitter-cli-search-timeout

## §1 SearchTimeline 被誤判為連線超時
**Symptom:** Mannie 的 `twitter search` 先後被 terminal 在 15、60、45 秒終止；直接執行則先出現 `Failed to init ClientTransaction: 'NoneType' object has no attribute 'group'`，接著 `SearchTimeline` 回 HTTP 404。`twitter status` 與 `twitter feed` 正常。
**Root cause:** `twitter-cli 0.8.5` 的 `TwitterClient._ensure_client_transaction()` 未帶登入 cookie 抓取 `https://x.com`。回應是約 34 KB 的公開登入頁，沒有 `ondemand` bundle 資訊，導致 `xclienttransaction` parser 對 `None` 呼叫 `.group()`；缺少 `x-client-transaction-id` 後，X 對 `SearchTimeline` 回 404。Mannie 又把同一失敗命令延長到 60／45 秒重試，表面看起來像網路超時。
**Fix:** 修改 `/Users/51mini/.local/share/uv/tools/twitter-cli/lib/python3.14/site-packages/twitter_cli/client.py`：transaction 初始化請求改為 `https://x.com/home`，並加入現有 `Cookie` 與 `X-Csrf-Token` header。維持 Agent Reach 規則：Twitter 命令最多 12 秒，一次失敗立即切 fallback，不放寬 timeout。此為 site-packages hotfix；`uv tool upgrade/reinstall twitter-cli` 可能覆寫，升級後若症狀復發依本節重套。
**Verify:** 載入 `/Users/51mini/.hermes/profiles/mannie/.env` 後，分別執行 `twitter -c status`、`twitter -c feed -n 1`、`twitter -c search OpenAI -n 1`。2026-07-31 實測三者 exit 0，耗時 1.04／2.77／2.39 秒，且 stderr 不再含 `Failed to init ClientTransaction`；verbose log 顯示 `ClientTransaction initialized for x-client-transaction-id`。
**Retrospective:** `agent-reach doctor` 只確認 CLI 與 credential 存在，不能證明每個 GraphQL operation 可用。診斷需至少分測 `status/feed/search`，並把 HTTP 404 與 transport timeout 分開。
