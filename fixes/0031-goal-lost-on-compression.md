---
id: 0031
slug: goal-lost-on-compression
title: /goal 標準目標在 context 壓縮後消失（session_id 沒搬 meta）
tags: [hermes-agent, goal, compression, mannie]
symptoms: ["goal", "compression", "session_id rotation", "/goal status", "goal disappears after compress"]
status: active
supersedes: []
related: []
---
# 0031 goal-lost-on-compression

## §1 /goal 每次 context 壓縮就消失，續跑迴圈靜默中止

**Symptom:** `/goal` 設好目標後跑一陣，一旦觸發 context compression（`/compress` 或自動壓縮），
之後 `/goal status` 變成「No active goal」，依賴 goal 續跑的迴圈直接停掉，沒有任何錯誤訊息。

**Root cause:**
- goal 狀態存在 SessionDB 的 `state_meta` 表，key 是 `goal:{session_id}`
  （`hermes_cli/goals.py` `_meta_key()` / `load_goal()` / `save_goal()`）。
- `load_goal()` 只讀自己那把 key，完全不會沿 `parent_session_id` 往回找。
- 壓縮流程（`agent/conversation_compression.py` 的 `compress_context()`）會產生新
  `session_id` 並 `create_session(parent_session_id=old_session_id)`，但壓縮流程本身完全
  沒碰 `goal:*` 這把 key —— 壓縮前 grep `goal` 是 0 命中。
- 續跑 hook（`gateway/run.py` / `cli.py` 的 `_get_goal_manager()`）讀的是新 `session_id`，
  查不到 goal meta，`is_active()` 回 False，直接 return，迴圈就這樣默默斷掉。
- 對照組：`todo` 壓縮時會補一則 user message 救回
  （`agent/conversation_compression.py` 舊行 367-369）；`memory` / `USER.md` 走 system
  prompt volatile tier，壓縮後 rebuild 自動回來（`agent/system_prompt.py` volatile tier）。
  goal 兩層保護都沒有，是唯一中招的功能。

**Fix（local patch，兩處，Hermes 升級會覆蓋，須重貼）:**

1. `agent/conversation_compression.py` — `compress_context()` 裡
   `if agent._session_db:` 區塊，在 `try/except` 建 session那段之後（緊接在
   `agent._session_db.update_system_prompt(...)` / `agent._last_flushed_db_idx = 0`
   後面），加一段：用 `hermes_cli.goals.load_goal(old_session_id)` /
   `save_goal(agent.session_id, state)` 把 goal meta 複製到新 session_id。
   - 用既有的 `load_goal`/`save_goal`，不直接碰 `db.get_meta`/`set_meta`
   - try/except 包住，goal 不存在是正常狀況，不能讓壓縮流程炸掉
   - 舊 session 的 goal meta **不刪**，保留審計軌跡
   - import 放函式內（避免 `agent.conversation_compression` ↔ `hermes_cli.goals` 模組層循環風險）

2. `agent/system_prompt.py` — `build_system_prompt_parts()` 的 volatile tier，
   在「External memory provider system prompt block」之前加一段：讀
   `hermes_cli.goals.load_goal(agent.session_id)`，status 為 active/paused 時組
   `Standing goal (...): ...` + 未完成 subgoal 區塊塞進 `volatile_parts`。
   - 硬化用：即使 §1 的搬移邏輯以後被繞過，goal 只要真的存在於新 session_id 下就會
     出現在 system prompt，模型看得到。
   - **注意**：這條不能取代第 1 條。`GoalManager` 仍以 session_id 為 key，不搬 meta
     的話這裡讀到的就是空的，印不出東西。兩項都要做。

3. `cli.py` — `/goal set|pause|resume|clear` 四個分支呼叫完
   `mgr.set()`/`mgr.pause()`/`mgr.resume()`/`mgr.clear()` 之後各加一行
   `self.agent._invalidate_system_prompt()`，強制下一輪 rebuild system prompt，
   讓上面第 2 條的 volatile tier 內容跟著更新（代價：破 prefix cache，goal 變動頻率低，
   可接受，跟 memory block 同一條路）。

**Verify:**
- `venv/bin/python -c "import agent.conversation_compression, agent.system_prompt"` → 無錯誤
- 腳本模擬（無互動 session 時的驗法）：直接呼叫 `hermes_cli.goals.GoalManager` 設 goal → 呼叫
  `hermes_state.SessionDB.create_session`（帶 `parent_session_id`）模擬壓縮的 session rotation →
  貼上第 1 條的 goal-migration snippet → 用新 session_id 重建 `GoalManager` → `status_line()`
  應與壓縮前相同；`load_goal(old_session_id)` 應仍存在且未被清除。
- `agent.system_prompt.build_system_prompt_parts()` 對新 session_id 呼叫，回傳的
  `volatile` 應含 `Standing goal (...)` 字串。
- 實際互動驗收：`/goal <text>` → `/goal status` 顯示 active → `/compress` 觸發壓縮 →
  `/goal status` 仍顯示同一 goal（不能靠這條腳本模擬取代，有互動環境時務必補測）。

**受影響檔案清單（升級後需重貼 local patch）:**
- `agent/conversation_compression.py`（goal-migration snippet，緊接 session 建立區塊後）
- `agent/system_prompt.py`（volatile tier 新增 goal block，`External memory provider` 之前）
- `cli.py`（`_handle_goal_command` 四個分支各加一行 `_invalidate_system_prompt()`）

**未涵蓋（另案處理，A2 範圍，不在本條）:**
- `gateway/run.py` / `cli.py` 的續跑掛載點本身（讀新 session_id 判斷 `is_active()` 那段）
  未動，只是 goal meta 現在搬過去了所以那段能讀到東西。
