---
id: 0017
slug: fts-context-compaction-loop
title: FTS context compaction — OmniRoute 免費池實測可用；HL 加 context 壓力監控與 compact-failed 止血
tags: [fts, codex, compaction, context-window, harness, omniroute, observability]
symptoms:
  - "fts codex session 上下文越來越長，不知道會不會自己 compact"
  - "codex rollout 完全沒有 compaction 記錄，token 卻已破 model_auto_compact_token_limit"
  - "HL harness 只看 agent_message 有沒有推進，看不到 context 用量"
  - "Happy 手機端看不到任何 token 用量"
  - "compaction 失敗後 harness 反覆 codex exec resume，帶滿 context 每次都炸，燒免費池 quota"
status: in-progress
supersedes: []
related: [0009, 0011, 0012, 0014]
---
# 0017 FTS context compaction 閉環

日期：2026-07-31。環境：codex v0.144.5、`CODEX_HOME=~/.codex-fts`、provider `omniroute`（`http://127.0.0.1:20129/v1`，wire_api `responses`）。

---

## §1 結論先講

| 問題 | 答案 |
|---|---|
| codex 會自己 compact 嗎？ | **會**。`run_pre_sampling_compact` 在 turn loop 裡，`exec` / `--yolo` / app-server 都吃得到 |
| 走 OmniRoute 免費池撐得住嗎？ | **撐得住，實測 3 次全成功、cost=0** |
| 為什麼現役 session 從沒 compact 過？ | 門檻 `model_auto_compact_token_limit=120000` 是 2026-07-30 23:57 才寫進 config；之後所有 session 峰值 97,465 < 120000，**還沒碰到門檻**。07-29/07-30 那些 154k~177k 的 rollout 是設定前的，不算反例 |
| HL 看得到嗎？ | 原本**完全看不到**。`harness-session-scan.mjs` 只抓 `task_started`/`task_complete`/`agent_message`/`function_call`，全檔零 token 邏輯 |

---

## §2 Block A 實測 — 拋棄式 CODEX_HOME probe

不碰現役 `~/.codex-fts`（改它會動到 `[hooks.state]` trusted_hash，見 0009）。做法：

```bash
# probe HOME 只留 model / model_provider / [model_providers.omniroute] / [projects."<cwd>"] trusted
# 關鍵兩行 —— 把門檻壓到必然觸發
model_context_window           = 30000
model_auto_compact_token_limit = 6000
```

移除 `notify`、`[plugins.*]`、`[hooks.state.*]`（probe 不要 Stop hook 介入）。跑：

```bash
set -a; . ~/.creds/omniroute/codex-fts.env; set +a
export CODEX_HOME="$PROBE_HOME"
codex exec --skip-git-repo-check -c model="gpt-5.4" - < task.txt
```

任務：`cat` 三個 14~28KB 的 `.mjs` 並逐檔寫 5 點摘要（累積必破 6000）。

### 判定證據（probe rollout jsonl）

```
line 18: {"timestamp":"2026-07-31T07:46:41.546Z","type":"compacted","payload":{"message":"Another language model started to solve this problem and produced a summary of its thinking process. ..."}}
line 22: {"timestamp":"2026-07-31T07:46:41.550Z","type":"event_msg","payload":{"type":"context_compacted"}}
```

- `"type":"compacted"` 出現 **3 次**，任務全程跑完
- 失敗字串 `Error running remote compact task` / `remote compaction v2 stream closed before response.completed` / `remote compaction v2 expected exactly one compaction output item` → **零命中**
- token 軌跡：`5034 → (compact) → 5035 → 5211`（`token_count` 事件的 `info.last_token_usage.input_tokens`）
- CLI 尾巴印 `context compacted` + codex 自己的警告 `Long threads and multiple compactions can cause the model to be less accurate`
- `~/.omniroute/storage.sqlite` `call_logs` 同時段全 `provider=nvidia|openrouter`、`status=200`、cost 0；壓縮摘要由 free 池模型產出（summary 內含 `<｜DSML｜tool_calls>` DeepSeek 標記）

### 附帶收穫

probe 期間 upstream 抖了三次都自動復原，**沒有害 compaction 失敗**：

```
07:45:45 429 Too Many Requests (nvidia)
07:46:25 429 Semaphore timeout after 30000ms for nvidia:...
07:46:28 504 Stream produced no non-ping SSE event within 20000ms
```

`request_max_retries=4` / `stream_max_retries=5` 吃掉了。

### 別再試的做法

| 做法 | 為什麼不行 |
|---|---|
| 直接在現役 `~/.codex-fts/config.toml` 調門檻做實驗 | 會動到 `[hooks.state.*]` trusted_hash 與 89 個 rollout 的判讀基準（0009 記過的坑） |
| 用 `window_number` / `replacement_history` / `first_window_id` 當 compaction 偵測主 key | 能中（都在同一行），但**真正穩定的 key 是 `type === "compacted"` 與 `event_msg.payload.type === "context_compacted"`** |
| 靠 Happy 手機端看用量 | Happy 直接丟棄 `token_count` 事件（`index-Cji64kS2.mjs:9451` 回 `envelopes: []`），永遠看不到 |

---

## §3 外部量測點（Happy 丟掉的，自己撈）

每個 turn 都會在 rollout jsonl 寫一筆：

```jsonl
{"type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":76538,...},"model_context_window":237500}}}
```

- `info.last_token_usage.input_tokens` = **當前 context 實際大小**
- `info.model_context_window` = **有效窗**，會被 provider metadata 蓋。實測 `237500 = 0.95 × 250000`，但 07-29 那批是 `258400`。**不可硬編**
- 壓力真正該除的是 `model_auto_compact_token_limit`（120000），不是 window

一行取值：

```bash
grep 'token_count' <rollout>.jsonl | tail -1 \
  | python3 -c "import sys,json;i=json.load(sys.stdin)['payload']['info'];print(i['last_token_usage']['input_tokens'], i.get('model_context_window'))"
```

---

## §4 進行中

- Block B：`omniroute-free-tools/scripts/harness-context-scan.mjs`（新模組，唯讀）+ 接進 `harness-poll-fts.mjs`
- Block C：`harness-session-scan.mjs` kick gate（`compact-failed` → 停止踢）+ HANDOFF 交接摘要 + respawn 觸發

（完工後回填實測結果）
