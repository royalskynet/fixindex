---
id: 0038
slug: autostash-pop-conflict-half-applied-tree
title: pull --autostash pop 炸 17 檔衝突，agent 沒發現繼續做事；半套修復比未修復更危險
tags: [git, hermes, mannie, autostash, merge-conflict, launchd, bytecode]
symptoms:
  - "Failed to load plugin 'telegram-platform': invalid syntax"
  - git pull --autostash --rebase 之後 git status 一堆 UU
  - agent 在有未解決衝突的樹上繼續工作
  - gateway 還活著但一重啟就會掛
  - 檔案沒有衝突標記、py_compile 過、執行期卻 AttributeError
  - hermes send 失敗 Failed to load gateway config invalid syntax
---

# 0038 — autostash pop 衝突 + 半套修復事故

- **狀態**：fixed
- **日期**：2026-08-02
- **關聯**：`0037`（503 admission）、`0039`（fork 工作流，本案的結構性根治）

## 1. 事故鏈

1. 派工單叫 agent 跑 `git pull --autostash --rebase`。rebase 成功，**autostash pop 產生 17 檔衝突（16 UU + 1 DU）**。git 只印一行警告，被 rebase 成功訊息蓋過，agent 沒發現，繼續改檔做任務。
2. `conversation_compression.py` 帶著 `<<<<<<<` 標記 → 三個 platform plugin（telegram/wecom/whatsapp）import 即炸。**gateway 沒死**，因為跑的是載入時的舊 bytecode —— 任何重啟就會全滅。`hermes` CLI 立即死（每次冷啟動）。
3. 搶修時 subagent 執行「鋪上游全量再重貼補丁」，中途被環境打斷 → `gateway/run.py` / `goals.py` 變成**半套：0 衝突標記、py_compile 過、`/llm` 呼叫點在但方法本體不在**。比留著標記更危險，語法檢查抓不到。

## 2. 修法

- 用 index 三方 stage（`git ls-files -u` → `git cat-file blob`）重建，**不要在工作檔上手改衝突標記**：鋪 stage2（上游全量）→ 從 `diff stage1 stage3` 抽本地補丁 → 逐段語意對位貼回。
- 上游大重構會把補丁錨點搬新家（本案 5 處：slash mixin、turn_finalizer、cli mixins、telegram plugin）。**照原行號硬貼必錯**，要 grep 語意錨點。
- git 標不出的隱藏耦合要主動找：衝突區塊外引用衝突區塊內變數（本案 `_failure_category` 差點 NameError）。

## 3. 教訓

1. **`--autostash` 不是安全操作。** 派工單若含 pull，`git status` 的 UU 檢查必須排在 pull **之後**且非零即停手。本案派工單排在之前 —— 開單者的疏失。
2. **「程式還在跑」≠「程式碼是好的」。** 長駐服務跑舊 bytecode，磁碟壞很久不會被發現。改長駐服務的碼後主動 import 檢查（`python -c "from model_tools import ..."` 這種會拉全鏈的入口）。
3. **半套修復比未修復危險。** 「鋪全量再重貼」被中斷 = 無標記的殘缺檔。此法必須配「補完前不准回報完成 + 逐符號 grep 檢核」。
4. **agent 的 git 寫入要收權。** 事後 Mannie 的 git 永久唯讀化；樹不乾淨一律停手回報。

## 4. 無效嘗試

- 六個 subagent 平行解衝突 → 權限審批通道被打爆（全部 `Tool permission request failed: Stream closed`），寫入全斷。**單線程自己解**反而 40 分鐘收完。平行 agent 適合唯讀分析，不適合大量寫入審批。
