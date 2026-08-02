---
id: 0035
slug: strip-proxy-anomaly-jsonl-literal-newline
title: strip-proxy anomalies.jsonl 無法解析 —— 寫的是字面 \n 不是換行；順帶記 ALS 在 req.on('end') 失效的正解
tags: [strip-proxy, omniroute, jsonl, async-hooks, asynclocalstorage, logging, heavy-hl]
symptoms:
  - "json.decoder.JSONDecodeError: Extra data: line 1 column 339"
  - anomalies.jsonl 多筆記錄黏在同一行無法逐行解析
  - anomalies-test.jsonl 整個檔 0 行合法 JSON
  - 測試流量污染生產 anomaly 日誌 / isTest 沒作用
  - AsyncLocalStorage getStore() 在 req.on('end') 裡回 undefined
  - enterWith 設了 store 但下游拿不到
  - 測試跑完後生產 anomaly 紀錄反而消失
status: active
supersedes: []
related: [0009-fts-codex-timeout-prefill-bloat, 0034-mannie-compression-failures-were-hardcoded-model, 0036-guard-permit-hook-never-issues]
---
# 0035 strip-proxy-anomaly-jsonl-literal-newline

## §1 症狀與根因：`'\\n'` 一個字元的差別

`~/omniroute-free-tools/strip-proxy/server.mjs` 的 anomaly 寫檔：

```js
fs.appendFileSync(path.join(logsDir, targetFile), JSON.stringify(anom) + '\\n');
//                                                                        ^^^^ 字面 backslash-n
```

原始碼寫成 `'\\n'`（跳脫過的反斜線 + n），寫進檔案的是**兩個字元** `\` `n`，不是換行。於是連續多筆 anomaly 全部黏在同一個物理行上。

`python3 -c "json.loads(line)"` 的報錯長這樣，很容易被誤讀成「檔案被截斷」：

```
json.decoder.JSONDecodeError: Extra data: line 1 column 339 (char 338)
```

實際 dump bytes 才看得出分隔符：

```python
b'generate gate","policyAction":"block"}\\n{"id":"anom_20260801T110817.865Z_0004",...'
#                                       ^^^^ 字面，不是換行
```

**判別法（一秒分辨是「缺換行」還是「字面 \n」）：**

```python
data = open('anomalies.jsonl','rb').read()
data.count(b'\n')                      # 902  ← 真換行數量正常
len(re.findall(rb'\}\{', data))        # 0    ← 沒有「缺換行」的黏連
len(re.findall(rb'\}\\n\{', data))     # >0   ← 字面 \n 才是兇手
```

## §2 用 backup 時間軸釘住是哪次編輯帶進來的

不要靠猜。`server.mjs.*.bak` 逐個 grep 同一行，交叉點就是肇事編輯：

```
server.mjs.a5-20260801-185548.bak:3014   ... + '\n');     ← 好
server.mjs.a5-20260801-203031.bak:3102   ... + '\\n');    ← 壞
```

第一筆壞行 ts `2026-08-01T11:08:17.857Z`（本地 19:08）落在 18:55 與 20:30 兩個 backup 之間 → 確定是 A5.2 加 `targetFile` 分流那次編輯。

**這條編輯是用 Python 腳本批次改的，雙重轉義沒注意。** 同一段的縮排也被打亂（`try {` 內縮成 12 空白），那是同一個腳本留下的第二個指紋。看到「縮排突然亂掉」就要懷疑同一次批次編輯還幹了別的事。

## §3 資料 100% 可救

不要重建、不要丟。字面 `\n` 只是分隔符錯了，每個 JSON 物件本身都完整：

```python
SPLIT = re.compile(r'(?<=\})\\n')      # 注意：match 的是字面 backslash + n
parts = [p for p in SPLIT.split(line) if p.strip()]
```

實測結果：

```
anomalies.jsonl        908 物理行 → 已合法 863 / 壞行 45 → 還原 144 物件 → 共 1007，unrecoverable 0
anomalies-test.jsonl    29 物理行 → 已合法  28 / 壞行  1 → 還原   7 物件 → 共  35，unrecoverable 0
```

**重要教訓：修復前的任何統計都是錯的。** 修復前數到 mock 紀錄 12 筆，修復後實際 51 筆 —— 39 筆藏在無法解析的壞行裡。壞掉的日誌上不能做歸因。

裝機時記得保留期間 live proxy 追加的尾巴（以 backup size 當 baseline，讀 `f.seek(base_size)` 之後的 bytes 接回去），否則會吃掉修復期間的新紀錄。實測本次接回 288 bytes。

## §4 ALS：`enterWith` 和 `run()` **都到不了** `req.on('end')`

這是本輪最反直覺的發現，計畫裡原本假設 `enterWith` 可用，被實測推翻。

目標是讓頂層純函式（`stripReasoningPlaceholder` / `processSSEStream` / `isDegenerateResponse`）拿得到 request context，而不必逐點傳參數 —— **逐點傳參數正是那個 live ReferenceError 的成因**（在拿不到 context 的地方硬寫 `options.path`）。

最小 probe（可直接抄）：

```js
const als = new AsyncLocalStorage();
http.createServer((req, res) => {
  als.enterWith({ tag: req.headers['x-tag'] });      // 或 als.run(store, () => {...})
  console.log('handler sync :', als.getStore());     // → { tag: 'A' }
  req.on('end', () => console.log('on(end) :', als.getStore()));   // → undefined
});
```

```
in handler sync : {"tag":"A"}
in req.on(end)  : NO_STORE      ← enterWith 失敗
in setImmediate : NO_STORE
```

`run()` 結果完全一樣，也是 NO_STORE。

**原因**：`'end'` 是 HTTP parser 在 **socket 的 async context** 裡 emit 的，不是我們 handler 那個 context 的延續。EventEmitter 的 listener 在 `emit()` 當下同步執行，繼承的是 emitter 的 context，不是註冊時的 context。

**正解：`AsyncResource.bind()` 包 listener。** 包一層之後，整條下游鏈（在裡面建立的 `http.request`、它的 response events、SSE data/end）全部自動繼承：

```js
import { AsyncLocalStorage, AsyncResource } from 'node:async_hooks';

req.on('end', AsyncResource.bind(() => {
  // 這裡以下 getStore() 都拿得到
}));
```

probe 驗證：

```
handler sync         : A
req.on(end) [BOUND]  : A
upstream response cb : A
upstreamRes.on(data) : A
upstreamRes.on(end)  : A
```

server.mjs 只有兩個 `req.on('end')` 掛載點需要包（`/v1/messages` 分支、FTS 分支）；`req.pipe(makeUpstreamReq())` 那條是 handler 內同步呼叫，本來就繼承，不用動。

store 必須是**可變物件**：`isTest` / `route` 在 entry 就知道，`ctxModel` 要等 body 解析完（`ctxModel = body.model` 之後補 `store.model = ctxModel`）。

合併時**顯式參數優先**，既有已接線的呼叫端行為才會完全不變：

```js
function withRequestCtx(context = {}) {
  const store = requestCtx.getStore();
  if (!store) return context;                    // 背景 timer：維持原行為
  const merged = { isTest: store.isTest, route: store.route, model: store.model };
  for (const k in context) if (context[k] !== undefined) merged[k] = context[k];
  return merged;
}
```

效果：43 個 `recordAnomaly` 站點裡原本 30 個拿不到 `isTest`，一行呼叫端都沒改就全部補齊。**新增站點也不需要記得傳。**

## §5 附帶抓到：throttle 只用 type 當 key，測試流量會「吃掉」生產紀錄

`normalizeAnomaly` 的 60 秒 throttle：

```js
const lastThrottled = anomalyThrottle.get(type) || 0;    // ← 只有 type
```

後果比污染更嚴重：跑一次測試產生 `reasoning-placeholder-strip`，接下來 60 秒內**真實**的同型 anomaly 被判為 throttled，直接不寫檔。**紀錄是消失而不是錯放。**

隔離測試就是這樣抓到的 —— 20 個交錯併發請求（10 tagged / 10 untagged），生產檔拿到 0 筆。

修法是把 lane 併進 key：

```js
const throttleKey = isTest ? `test:${type}` : `prod:${type}`;
```

## §6 無效的嘗試（別再走一次）

| 做法 | 結果 |
|---|---|
| `als.enterWith()` 在 handler 開頭 | ❌ 到不了 `req.on('end')` |
| `als.run(store, () => {...})` 包整個 handler | ❌ 同樣到不了，而且要 re-indent 850 行 |
| 用 `raw_decode` 迴圈切壞行 | ❌ 失敗。分隔符是**字面** `\n` 不是空白，`raw_decode` 停在第 338 char 就報 `Expecting value` |
| 靠 `node --check` 抓這類 bug | ❌ 抓不到。`'\\n'` 語法完全合法，是語意錯 |
| 修復前先數 mock 筆數再決定要不要清 | ❌ 數到 12，真值 51。**壞日誌上不能做統計** |
| mock 上游用 `res.end(json)` 不設 content-length | ❌ Node 退回 chunked，proxy 依 `transfer-encoding: chunked` 判定為 streaming，整條非串流路徑測不到 |

## §7 驗收（實測數字）

```
node --check server.mjs                 → SYNTAX_OK
node test-degenerate-gate.mjs           → PASS=51 FAIL=0
    anomalies.jsonl      delta 0        ← 零洩漏（修好前每跑一次漏 298 bytes）
    anomalies-test.jsonl delta 1362
node test-anomaly-isolation.mjs         → PASS=8 FAIL=0（20 併發交錯，兩線歸屬全對）
背景 self-check probe                    → prod +288 / test +0，route/model 空字串（無 store，行為不變）
```

新增回歸測試 `strip-proxy/test-anomaly-isolation.mjs` —— 它守的是 §4 那個 `AsyncResource.bind`。**拿掉 bind 之後功能測試（degenerate-gate）依然全綠**，只有這支會紅。

## 重貼流程

`server.mjs` 的改動，升級或從 backup 還原後要重打：

1. `import { AsyncLocalStorage, AsyncResource } from 'node:async_hooks';` + `const requestCtx = new AsyncLocalStorage();`
2. `const isTestRequest = ...` 之後 `requestCtx.enterWith({ isTest, route: options.path, model: null })`
3. 兩個 `req.on('end', ...)` 包 `AsyncResource.bind()`；兩處 `ctxModel = ...` 之後補 `store.model = ctxModel`
4. `recordAnomaly` / `writeHarnessReport` 套 `withRequestCtx()`；throttle key 加 lane 前綴
5. **確認 `+ '\n'` 不是 `+ '\\n'`**

## 未完成

`:20130`（`com.royalskynet.heavy-hl`）**未重啟，仍跑舊碼**，會繼續往同一個 logs 目錄寫字面 `\n`。原因不是不想重啟，是 guard hook 壞掉導致無法授權 —— 見 `0036-guard-permit-hook-never-issues`。

`:20129`（`com.royalskynet.freetools-stripproxy`）已於 2026-08-02 16:50:51 重啟生效（PID 87328 → 18994）。

## 受影響檔案

- `~/omniroute-free-tools/strip-proxy/server.mjs`
- `~/omniroute-free-tools/strip-proxy/test-anomaly-isolation.mjs`（新增）
- `~/omniroute-free-tools/strip-proxy/logs/anomalies.jsonl`、`anomalies-test.jsonl`（已修復，備份 `.bak-20260802-165136`）
- `~/omniroute-free-tools/strip-proxy/logs/anomalies-mock-extracted.jsonl`（抽出的 51 筆，未刪）
