---
id: 0034
slug: mannie-compression-failures-were-hardcoded-model
title: Mannie 壓縮失敗 14 次的原因是硬編 gemma 模型，換 auto/best-free 後歸零 — 別再當成待處理風險
tags: [mannie, hermes-agent, context-compressor, llm-routing, omniroute, false-alarm]
symptoms:
  - "Failed to generate context summary: Request timed out"
  - "Auxiliary compression: connection error on custom"
  - "upstream returned an empty response without usable output"
  - "upstream_empty_response"
  - 壓縮反覆失敗擔心 context 持續累積逼近視窗上限
  - "Payload Too Large" 413 on 127.0.0.1:20130
status: active
supersedes: []
related: [0023-omniroute-throttle, 0028-mannie-silent-amnesia-compression-chain, 0033-approval-timeout-iteration-budget]
---
# 0034 mannie-compression-failures-were-hardcoded-model

## §1 結論先講：這個「風險」已經解掉了，不要再排工

2026-08-02 有人（我）看 8/01 的 log 看到 6 次壓縮 timeout，標記為「未解風險：持續失敗會讓未壓縮訊息累積、逼近真實視窗」。**這個判斷是錯的**，原因是只看 log 沒對時間線，沒注意 config 已經改過。

實測數字：

```
context compression started : 38
context compression done    : 38    ← 全部完成，沒有一次卡住
Failed to generate summary  : 14    ← 是「單次嘗試失敗」，重試後都成功
```

`started == done` 是關鍵。壓縮從來沒有「持續失敗導致累積」過，每次都在重試後完成。

## §2 真正的根因：硬編模型，符合 feedback_llm_routing §4 的既有禁令

14 次失敗**全部**集中在兩個硬編模型：

| 模型 | 失敗次數 | 錯誤類型 |
|---|---|---|
| `openrouter/google/gemma-3-4b-it:free` | 4 | `400` — Model is not allowed |
| `openrouter/google/gemma-4-26b-a4b-it:free` | 3+ | `502 upstream_empty_response`、`Request timed out` |

時間線對比（決定性證據）：

```
最後一次失敗            2026-08-01 23:29:17
auto/best-free 首次使用  2026-08-02 00:56:51
切換後失敗數            0
```

這正是 memory `feedback_llm_routing` §4 已經寫過的事：**禁止硬編特定模型 ID 當預設 —— 單一模型會 429 / 下架 / 配額爆**。gemma-3-4b 的 `400 Model is not allowed` 就是下架/停權，gemma-4-26b 的 `502 upstream_empty_response` 就是模型吐空。

**不需要再做任何模型選型改動。** 現況已合規：

```yaml
auxiliary:
  compression:
    provider: omniroute
    model: auto/best-free                      # 動態選型，符合 §4
    base_url: http://127.0.0.1:20130/v1        # 本地 gateway，符合 §3
    timeout: 120
```

實測 `auto/best-free` 路由到 `z-ai/glm-5.2`（連續三次一致）。`~/omniroute-free-tools/config/` 全域 grep 無 `api.openai.com` / `api.anthropic.com` / `api.deepseek.com` / `api.groq.com` — 鏈上無付費端點，符合 §1 真免費。

## §3 fallback_chain 的硬編是刻意例外，不要「順手改成 openrouter/free」

```yaml
    fallback_chain:
    - model: openrouter/openai/gpt-oss-20b:free
    - model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free
    - model: openrouter/inclusionai/ling-3.0-flash:free
```

看起來違反 §4「禁止硬編」，但 fallback **必須**指向與主路徑不同的具體模型才有備援意義。四層全填 `openrouter/free` / `auto/best-free` 等於四層都是同一個選擇器，主路徑掛掉時 fallback 會做出同樣的選擇 —— 備援形同虛設。

這是 §4 所說的「例外必須寫明理由」，理由就是這條。2026-08-02 實測三個 fallback 全部存活：

```
openrouter/openai/gpt-oss-20b:free              http=200  3.86s
openrouter/nvidia/nemotron-3-nano-30b-a3b:free  http=200  0.83s
openrouter/inclusionai/ling-3.0-flash:free      http=200  0.98s
```

## §4 timeout: 120 綽綽有餘，不要調

實測真實量級的壓縮請求（`127.0.0.1:20130`，`auto/best-free`）：

| 請求 | tokens | bytes | 耗時 | 結果 |
|---|---|---|---|---|
| 70 則 × 8k 字（仿真實壓縮） | ~139,740 | 561,558 | **8.2s** | OK |
| 70 則 × 2k 字 | ~35,003 | 142,608 | 14.6s | OK |
| 200 則 × 1k 字 | ~47,778 | 198,323 | 15.3s | OK |

最慢 15.3s，離 120s 很遠。慢的來源是 fixindex 0023 刻意加的節流（`minTime=15000` / `rpm=4` / `maxConcurrent=1`），不是模型或網路 —— 那是拿速度換「不被鎖帳號」的設計取捨，**不要動**。

## §5 附帶發現：20130 的 413 門檻是 800 則訊息（與本案無關，但記著）

排查過程中發現 `127.0.0.1:20130` 會對**訊息則數**過多的請求回 `413 Payload Too Large`，且是 0.0s 立即拒絕。

反直覺的是它**不是** byte 或 token 驅動的：

```
70 則 × 8k字  = 561,558 bytes / 139,740 tok → OK  8.2s
801 則 × 400字 = 337,642 bytes /  77,274 tok → 413 立即拒絕
```

更大的 payload 通過、更小的被拒。二分找到確切門檻：

```
799 則 → OK
800 則 → 413
```

**與 Mannie 壓縮失敗無關** —— Mannie 實際壓縮請求最多 105 則（log 實測），`compression.hygiene_hard_message_limit: 400` 也遠低於 800。這是 probe 造出來的極端情境，不是現實問題。

記在這裡是因為：若未來有任何 agent 開始送 800+ 則訊息給 20130，症狀會是**立即 413、0 秒、無重試價值**，而不是逾時。屆時不要往「模型太慢 / timeout 太短」的方向查。

## §6 教訓：為什麼會誤判

歸因錯誤的動作序列：

1. 讀 8/01 的 log，數到 6 次 `Failed to generate context summary`
2. 直接推論「持續失敗 → 累積 → 逼近視窗」
3. **沒有數 `started` vs `done`** —— 數了就會發現 38/38 全部完成
4. **沒有對時間線** —— 對了就會發現失敗全在 config 改動之前

正確順序見 memory `feedback_debug_verify_first`：**先驗配置與實際請求，模型永遠擺最後**。這次「模型」確實是根因，但也只有在「配置改過、時間線對得上」被驗證之後才能這樣說 —— 而且結論是「已經修好了」，不是「要改模型」。

## 重貼流程

本條目**沒有任何程式碼改動**，純調查結論。無需重貼。

唯一需要保護的是 `~/.hermes/profiles/mannie/config.yaml` 的：

- `auxiliary.compression.model: auto/best-free` — 不要退回任何硬編 gemma
- `auxiliary.compression.fallback_chain` 的三個具體模型 — 不要「統一」成 `openrouter/free`

## 受影響檔案

- `~/.hermes/profiles/mannie/config.yaml`（`auxiliary.compression` 區塊，唯讀確認，本輪未改）
- `~/omniroute-free-tools/config/`（唯讀確認無付費端點）
