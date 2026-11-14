---
description: 掃描當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後草擬補記
---

掃描本 session 從開始到現在的全部內容與產出，只挖**值得永久記入 fixindex** 的經驗，不逐句回報。

## 兩類條目

1. **insight** — 已固化的設計洞見／架構決策／跨案模式：改方式比記解法有價值、別的專案也用得到。
2. **symptom**（一般 defect 條目）— 症狀→根因→解法→驗證：會重複撞到、下次 `fixindex find "<關鍵字>"` 找得到。

## 程序（主 session 只跑一條指令，不讀逐字稿、不派 deep、不派 Claude 子代理）

```bash
bash ~/dev/fixindex/tools/fi-run.sh <本 session jsonl 絕對路徑>
```

用 `run_in_background: true` 跑，完成通知到了只讀輸出末尾，照轉述新增（編號＋核心）、補充、略過。不另跑 `fixindex show` 抽查、不重讀報告或 part 檔。

- 腳本內含：增量抽 transcript（只取上次 /fi 之後的行）→ 遮罩 → Presidio scrub → 切塊 → `fi_pipeline.py`（每塊一次 flash 抽候選 → 機械過濾引用與 RULE → 一次批次查重 → 一次 flash 裁決含同輪去重 → 寫入）→ 工單驗收段 → 全過才前移標記。
- 退出碼：0 完成且驗收過｜5 上次 /fi 後沒有新內容（一句帶過）｜2 找不到 transcript｜3 PII scrub（:4102）不通或 pipeline 的 LLM 失敗｜4 deep-lint 或 `fixindex fi` 失敗｜1 驗收失敗。
- rc=3 且訊息是 scrub → 先看 `launchctl list | grep pii-gateway` 與 :4102，修好再跑；**不准**繞過 scrub 把逐字稿交給外部 LLM（鐵則 6）。
- 「## 新增」下是「- 無」→ 一句「本 session 無新的可記經驗」帶過。
- 要重掃整個 session：前面加 `FI_FULL=1`。
- pipeline 連續失敗時才退回舊流程：`FI_MODE=agent bash ~/dev/fixindex/tools/fi-deep.sh <jsonl>`，照最後一行裸名 `deep-run`（背景），收件跑 `wo-verify <工單>`。

LLM 兩段走 ds-claude 的 `ds-run.sh --ask`，prompt 在 `tools/fi-prompts/`。改流程就改腳本、prompt 與 `tools/fi-deep-test.sh`／`tools/fi-pipeline-test.sh`，不在這裡另寫一份。

## 欄位（工單已附，供核對）

- symptom：`SYMPTOM:` `ROOT:` `FIX:` `VERIFY:` `RULE:`（建新條目必帶 RULE）
- insight：`CONTEXT:` `INSIGHT:` `IMPLICATION:` `QUERIES:` `RULE:`
