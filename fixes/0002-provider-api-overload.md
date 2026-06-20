---
id: "0002"
slug: provider-api-overload
title: Provider API request failed — 長思考/大 context 單請求過肥中斷
tags: [claude-code, anthropic-api, provider, overload, context, extended-thinking]
symptoms:
  - "Provider API request failed. (request_id=req_xxxx)"
  - "Cogitated for 3m+ 後請求掛掉、任務中斷"
  - "一次讀多篇大文檔合成時 API 報錯"
status: active
supersedes: []
related: []
---
# 0002 provider-api-overload

Claude Code 在長思考 / 大 context 單一請求後，上游 Anthropic API 回失敗中斷任務。

## §1 長思考後 Provider API request failed

**Symptom:** `Provider API request failed. (request_id=req_f827ae49f6e3)`，發生在 `Cogitated for 3m 5s` 之後，當下正一次把 8+ 篇大文檔（QMD 全文）灌進 context 做合成，任務中斷。

**Root cause:**
- `req_` 前綴是 Anthropic 伺服器端 request_id → 失敗源在上游 API，非本機 bug。
- 無自訂 `ANTHROPIC_BASE_URL` / proxy / router，直連 `api.anthropic.com`，無中間層。
- settings.json 的 `timeout:5/10` 是 hook timeout，與 API 請求無關。
- 觸發條件：單一請求過肥 —— 大量 full-doc context + `CLAUDE_EFFORT=high` 的 3 分鐘 extended thinking → 撞上游 529 overloaded / gateway timeout，請求被拒。
- 性質：暫時性上游錯誤，非可 patch 的程式碼缺陷。失敗的請求已不可恢復。

**Fix:**
- 即時：直接重試，暫時性錯誤重跑通常即過。
- 降復發：
  - 同步任務別一次 `get` 多篇全文，先讀摘要 / 分批合成，縮小單請求 context。
  - 大型合成時 `CLAUDE_EFFORT` 降一級，縮短思考爆量。
  - 把長任務拆成多輪、各輪有產出落地（checkpoint），避免一次掛掉全丟。

**Verify:** 重試或分批後同任務跑完不再報 `Provider API request failed`。

**Note:** fixindex `new <slug>` 無 `--help`，誤打 `new --help` 會生出 `0002---help.md` 垃圾檔，直接 `rm` 即可。
