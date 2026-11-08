---
description: 掃描當次 session，挖出值得增補 fixindex 的 insights（設計洞見）與 symptoms（可搜尋經驗），去重後草擬補記
---

掃描本 session 從開始到現在的全部內容與產出，只挖**值得永久記入 fixindex** 的經驗，不逐句回報。

## 兩類條目

1. **insight** — 已固化的設計洞見／架構決策／跨案模式：改方式比記解法有價值、別的專案也用得到。
2. **symptom**（一般 defect 條目）— 症狀→根因→解法→驗證：會重複撞到、下次 `fixindex find "<關鍵字>"` 找得到。

## 程序（2026-11-09 起：掃描、收斂、寫入全派 deep，不派 Claude 子代理）

主 session 只做三件事：跑 `fi-deep` 產工單、裸名派 `deep-run`、收件重驗。

1. **產工單**（抽 transcript → 遮罩 → Presidio scrub → 切塊 → 產 deep 工單 → deep-lint，全在腳本內）：

   ```bash
   bash ~/dev/fixindex/tools/fi-deep.sh            # 或帶 session jsonl 絕對路徑
   ```

   - 同 cwd 有並行 session 時，帶本 session 的 jsonl 路徑（檔名＝session id），不靠最新 mtime。
   - 退出碼：0 已產工單｜2 找不到 transcript｜3 PII scrub（:4102）不通，fail-closed，不留任何產物｜4 deep-lint FAIL。
   - rc=3 → 先看 `launchctl list | grep pii-gateway` 與 :4102，修好再跑；**不准**繞過 scrub 直接把逐字稿交給 deep（deep 是外部 LLM，鐵則 6）。
2. **派 deep**：照抄腳本最後一行 `deep-run <工單> <cwd>`，裸名、單一指令、`run_in_background: true`。
3. **收件**：
   - `wo-verify <工單>` 自己重跑，rc=0 才算完成；deep 的 `VERIFY_FAIL` 照 deep skill 收件規則查。
   - 讀報告（腳本印的 `report:` 路徑），轉述新增（編號＋核心）、補充、略過與 `fixindex status` 結果。
   - 新增條目抽一兩條 `fixindex show <編號>` 看欄位是不是可搜尋關鍵字、RULE 是否可泛化；不合格就寫補單再派 deep，不自己改條目。
4. **候選為空**：報告「## 新增」下是「- 無」→ 一句「本 session 無新的可記經驗」帶過。

工單內容（窮舉候選、逐條 `fixindex find`／`insights` 查重、收斂、`printf … | fixindex fi` 寫入、報告格式、驗收）由 `fi-deep.sh` 產生，改流程就改腳本與 `tools/fi-deep-test.sh`，不在這裡另寫一份。

## 欄位（工單已附，供核對）

- symptom：`SYMPTOM:` `ROOT:` `FIX:` `VERIFY:` `RULE:`（建新條目必帶 RULE）
- insight：`CONTEXT:` `INSIGHT:` `IMPLICATION:` `QUERIES:` `RULE:`
