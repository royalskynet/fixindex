---
id: 0040
slug: hermes-profile-confusion-send-is-not-dispatch
title: hermes send 不帶 -p 走 active_profile 錯投；send 是 outbound 不是派工；Mannie 派工只走 md 手貼
tags: [hermes, profile, mannie, koko, telegram, dispatch, plugins, launchd]
symptoms:
  - hermes send 回 sent 但目標 agent 完全沒反應
  - 訊息從別的 bot 出現在使用者聊天室
  - 目標 profile 的 gateway.log 找不到那筆訊息
  - "[HERMES_HOME fallback] HERMES_HOME is unset but active profile is 'koko'"
  - 改了 hermes-agent 程式碼但某些 profile 沒生效
  - "Failed to load plugin 'line-platform': invalid syntax"
  - 怎麼派工給 Mannie / hermes agent
---

# 0040 — profile 混淆 + send≠dispatch + 多 gateway 舊 bytecode

- **狀態**：fixed
- **日期**：2026-08-02
- **關聯**：`0038`（衝突事故，本案同日）、`0039`（fork 工作流）

## 1. 架構事實（先讀這節，混淆都從不懂這個開始）

- **一份 repo（`~/.hermes/hermes-agent`），N 個 profile，各自獨立 gateway**：`~/.hermes/profiles/{koko,cl,shiyue,xuanjun,effie,agnes,penny,mannie}`，launchd 服務名 `ai.hermes.gateway-<profile>`，各有自己的 TG bot 與 logs
- `hermes` CLI 不帶 `-p`/`--profile` → 讀 `~/.hermes/active_profile`（本機 = **koko**），credentials 走 `~/.hermes/.env`（`main.py` pre-parse 段）
- 共用資源只有兩個：repo 程式碼、`~/.hermes/kanban.db`
- **每個 gateway 跑的是它啟動當下的 bytecode**。改完 repo 只重啟一個 profile，其他 profile 全部還在跑舊碼

## 2. 當日三個錯

### 2a. `hermes send` 錯投（無聲失敗）

給 Mannie 的〔停手〕〔復工〕兩則用 `hermes send --to telegram:<chat>` 送，沒帶 `-p mannie` → 走 koko 的 bot。CLI 照樣回 `sent`，使用者在 TG 看得到（從 koko 那邊來），**Mannie 的 gateway.log 完全沒有這筆**。她 19:53 停下純屬那輪自然結束，運氣。

### 2b. 範式錯：send 是 outbound，不是派工

就算帶對 `-p`，`hermes send` 也只是 bot→人 發訊息（`send_cmd.py`：無 LLM、無 agent loop、不需 gateway 在跑）。**agent 只對 inbound（人→bot）起反應**。派工兩條路：使用者在該 profile 聊天室發 inbound、或 kanban dispatch。

### 2c. 多 gateway 舊 bytecode 盲區

修完 17 檔衝突只重啟了 mannie。事後盤點：koko 在手術中途（21:21）被 launchd 重啟過，載入時 `line/adapter.py` 還有衝突標記 → koko 跑著「缺 line-platform」的狀態兩小時沒人發現；cl/shiyue 是 7/30 的 bytecode。**改共用 repo = 逐一盤點所有 `launchctl list | grep gateway` 的 PID 起始時間。**

## 3. 定調（使用者裁示，永久）

1. **派工 Mannie 一律寫 md 檔、給使用者路徑、由使用者貼**。除非找到新方法並**實驗證實**（目標 profile gateway.log 看到 inbound）才可改。已寫入 memory `feedback_dispatch_policy` §3.5
2. koko 不需要 LINE → `plugins.disabled: [line-platform]`（config.yaml deny-list，`plugins.py _get_disabled_plugins`，deny 永遠贏過 enabled）。已改並重啟驗證：PID 33837→87640，telegram connected，載入失敗 0

## 4. 正確操作備忘

```
cat ~/.hermes/active_profile                              # 動手前先看預設是誰
hermes -p <profile> <cmd>                                  # 對特定 profile 一律帶 -p
grep "<訊息片段>" ~/.hermes/profiles/<目標>/logs/gateway.log   # 驗送達看這裡，不看 CLI 回傳
launchctl list | grep gateway                              # 改 repo 後盤點誰在跑舊碼
launchctl kickstart -k gui/501/ai.hermes.gateway-<profile> # 逐一重啟（先確認閒置）
```

## 5. 教訓

1. **多租戶 CLI 的預設值是地雷**。回 `sent` ≠ 送對地方；驗證要看接收端的 log，不看發送端的回傳值。
2. **「訊息送到聊天室」≠「agent 收到指令」**。搞清楚系統裡誰讀哪個方向的訊息，再選管道。
3. **共用程式碼的多服務架構，部署動作是「對每個服務」不是「對程式碼」**。改一次 code，N 個服務就欠 N 次重啟，欠著的每一個都是舊行為。
