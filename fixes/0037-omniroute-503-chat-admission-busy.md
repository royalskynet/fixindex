# 0037 — Mannie 中途死掉的真因是 omniroute admission 閘的 503，不是模型也不是 timeout

- **狀態**：fixed
- **日期**：2026-08-02
- **受影響**：`hermes-agent`（`agent/conversation_loop.py`、`agent/auxiliary_client.py`）、`~/.hermes/profiles/mannie/config.yaml`、`~/Library/LaunchAgents/com.royalskynet.freetools-omniroute.plist`
- **關聯**：`0016`（agent 驗不了自己重啟）、`0034`（fallback_chain 盲區的前半）

---

## 1. 症狀

Mannie 執行派工到一半停住，TG 只吐一句：

```
⚠️ The model provider failed after retries. I kept raw provider details out of chat;
   check gateway logs for diagnostics.
```

表面上像「模型不行 / timeout」。**不是。**

`~/.hermes/profiles/mannie/logs/errors.log`，兩次同型：

```
10:32:56 WARNING API call failed (attempt 1/1) error_type=InternalServerError
         provider=custom    base_url=http://127.0.0.1:20130/v1  model=free-tools-heavy
         summary=HTTP 503: Structurally heavy chat request capacity is busy; retry shortly.
10:32:56 WARNING API call failed (attempt 1/1) error_type=InternalServerError
         provider=omniroute base_url=http://127.0.0.1:20130/v1/ model=free-tools
         summary=HTTP 503: ...（同上）
10:32:56 ERROR   API call failed after 1 retries. msgs=55 tokens=~37,222

18:12:30 （同型，msgs=70 tokens=~41,990）
```

兩次嘗試的時間戳**同一秒**（10:32:56）—— 沒有任何等待，直接放棄。

---

## 2. 根因鏈（四層，缺一不成立）

### 2a. 訊息不是 strip-proxy 發的

```
grep "Structurally heavy" strip-proxy/   → 無命中
```

追鏈路：

```
:20130  strip-proxy (server.mjs)  UPSTREAM_URL=http://127.0.0.1:20128
:20128  omniroute v16.2.12
```

出處在 omniroute 自己的 chat admission control：
`/opt/homebrew/lib/node_modules/omniroute/dist/.build/next/server/chunks/[root-of-the-server]__1dtx_ee._.js`

```js
new Response(JSON.stringify({error:{
  message:"Structurally heavy chat request capacity is busy; retry shortly.",
  type:"server_error", code:"chat_admission_busy", reason:"structure_limit"}}),
  {status:503, headers:{...,"Retry-After":"1"}})
```

**它明明白白回了 `Retry-After: 1`** —— 等一秒重送就好。

### 2b. 門檻預設值把 Mannie 每一次呼叫都判成 heavy

同一 chunk 裡（`r(env, default)` 形式）：

| env | 預設 | Mannie 實際 |
|---|---|---|
| `OMNIROUTE_CHAT_HEAVY_ESTIMATED_TOKENS` | **32,000** | 37k / 42k → 一律 heavy |
| `OMNIROUTE_CHAT_MAX_HEAVY_IN_FLIGHT` | **1** | 全域只准一個 |
| `OMNIROUTE_CHAT_HEAVY_MESSAGE_COUNT` | 200 | 55 / 70，未觸發 |
| `OMNIROUTE_CHAT_HEAVY_TOOL_COUNT` | 64 | — |
| `OMNIROUTE_CHAT_HARD_MAX_BODY_BYTES` | 0x3200000 | — |
| `OMNIROUTE_CHAT_HARD_MAX_MESSAGES` | 800 | — |

Mannie 跑 `asyncio_1` / `asyncio_2` 兩條 thread，加上 background review 子迴圈 → **必撞**。

### 2c. `Retry-After` 沒被遵守，且 retry 預算只有 1

`config.yaml:17` `api_max_retries: 1`。`conversation_loop.py` 只在 `is_rate_limited`（429）分支讀 `Retry-After`，503 不走那條 → 立刻用掉唯一一次重試、立刻放棄。

### 2d. fallback 根本不會觸發

`auxiliary_client.py`：

```python
should_fallback = (
    _is_payment_error(first_err)
    or _is_connection_error(first_err)
    or _is_rate_limit_error(first_err)
)
```

503 / `InternalServerError` 三個都不是 → 不 fallback。`0034` §6 記的盲區只寫了 400/502，**503 也在盲區內**。

### 2e. 就算 fallback 觸發了，對這個錯誤也沒用

`config.yaml` 每一條 `fallback_chain` 的 `base_url` 都是 `http://127.0.0.1:20130/v1`（行 139/146/152/159/165/169/173）。

⚠️ **先前的判斷過頭了，這裡修正**：這**不代表** fallback_chain 是裝飾品。omniroute 是聚合器，換 model 名稱就是換真正的上游供應商，所以對**模型層**的失敗（400 模型下架、502 吐空）fallback 仍然有效。它只對**閘道層**的 admission 503 無效 —— 因為所有 entry 共用同一個 admission 閘。

這正是「503 不該進 fallback 而該退避重試」的理由。

---

## 3. 非模型反事實檢查

| 假設 | 判定 | 依據 |
|---|---|---|
| 弱模型 | ❌ | 503 在 27ms 內回，沒進到模型 |
| timeout | ❌ | 同上，兩次嘗試同一秒 |
| strip-proxy C 卷改動 | ❌ | 503 字串不在 `server.mjs`；:20130 只轉發 |
| transport / admission-control | ✅ | 根因層 |
| routing | ✅（部分） | fallback 目標共用閘道 |

---

## 4. 修法（四處，全部已實施）

### 4a. 止血：放寬 omniroute 併發名額

`~/Library/LaunchAgents/com.royalskynet.freetools-omniroute.plist` `EnvironmentVariables` 加：

```xml
<key>OMNIROUTE_CHAT_MAX_HEAVY_IN_FLIGHT</key>
<string>3</string>
```

**必須 `bootout` + `bootstrap`，不能只 `kickstart -k`** —— kickstart 用 launchd 已載入的 job 設定，不重讀 plist，env 改動不會生效。

token 門檻刻意不動，結構性防護維持原樣。

### 4b. `auxiliary_client.py`：新增分類器 + 退避重試

新增 `_is_admission_busy_error()` 與 `_admission_retry_after()`（`Retry-After` 優先，缺省 1s，夾在 0–30s），sync / async 兩條路徑各插一段退避重試迴圈，`_ADMISSION_MAX_RETRIES = 3`。

關鍵設計：**不塞進 `should_fallback`**。理由見 §2e。

註：`asyncio` 原本只在函式內 local import，模組層沒有 —— async 分支用 `await asyncio.sleep()` 會 `NameError`。已補模組層 `import asyncio`。

### 4c. `conversation_loop.py`：admission 等待不吃 retry 預算

在 `except` 處理的最前面（`retry_count += 1` **之前**）插入分支：命中 admission 503 → 讀 `Retry-After` → 可中斷睡眠 → `continue`，**retry_count 不動**。

獨立計數 `max_admission_waits = 5`。理由：`api_max_retries=1` 時一次排隊碰撞就會結束整個 turn。

### 4d. `config.yaml`：`api_max_retries` 1 → 3

---

## 5. 驗收（實測數據）

### 5a. omniroute 併發（真併發，不是只看 env）

3 個 135KB / ~34k token 的請求同時打 `:20128`：

```
req1 http=200 t=3.341160
req2 http=200 t=3.612808
req3 http=200 t=3.591085
chat_admission_busy 命中數：0
```

三個各跑 3.3–3.6 秒、時間重疊 → 真併發。舊值 `1` 的話 req2/req3 必吃 503。

⚠️ 第一次探測用 `__nonexistent_probe_model__` 得到 3 個 400，**那個測試無效** —— 400 回得太快（毫秒級），三個請求根本沒重疊，證明不了併發放寬。換成真模型讓每個請求佔住 3 秒才是有效測試。

### 5b. 分類器離線測試

17 條全過（`scratchpad/test_admission_busy.py`）：

- 三種 admission 503 形狀（含 SDK 省略 `status_code` 的情況）→ 命中，且**都不進 fallback**
- 503 但非 admission、402、429、連線錯誤、400 bad model → 分類不變（回歸保護）
- `Retry-After`：有 header / 小寫 header / 缺省 / 垃圾值 / 9999→夾成 30 / -5→夾成 0

### 5c. 上線

```
omniroute  PID 90750 → 61437 @ 18:43:25
gateway    PID 21707 → 67486 @ 18:57:45   telegram connected，無 import 錯誤
20128 http=200   20129 http=200   20130 http=200
live probe: aux has classifier=True, _ADMISSION_MAX_RETRIES=3, loop has backoff=True
```

---

## 6. 無效嘗試

1. **`kickstart -k` 改 env** —— 不重讀 plist，白做。
2. **`ps eww` 驗 omniroute 子行程 env** —— 子行程把 argv/env 區改寫成 `omniroute (v16.2.12)`，`ps` 讀不到，回傳 0 個變數。**這不是 env 沒生效的證據**，父行程 61408 讀得到。要驗就打真實請求。
3. **用不存在的模型名做併發探測** —— 見 §5a 警告。
4. **只查 strip-proxy** —— 訊息不在那裡，浪費一輪。錯誤訊息要先確認是哪一層發的再往下追。

---

## 7. 教訓

1. **「provider failed after retries」是最沒有資訊量的錯誤訊息。** 它同時涵蓋模型錯誤、網路錯誤、閘道排隊。看到它一律去 `errors.log` 撈原始 summary，不要從訊息本身推論。
2. **回應裡的 `Retry-After` 是伺服器在直接告訴你解法。** 沒讀它就等於把「等一秒」變成「整個 turn 死掉」。新增錯誤處理分支時先問：對方有沒有給重試指引？
3. **併發上限類的 bug，測試必須讓請求真的重疊。** 快速失敗的請求測不出併發閘。
4. **「fallback 沒觸發」和「fallback 觸發了也沒用」是兩個不同的缺陷**，要分開判斷。混為一談會導出「fallback_chain 是裝飾品」這種過頭的結論（見 §2e 的自我修正）。
