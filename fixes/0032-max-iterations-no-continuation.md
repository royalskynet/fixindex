---
id: 0032
slug: max-iterations-no-continuation
title: 撞 max_iterations 後任務直接斷掉，沒有任何自動續跑
tags: [hermes-agent, goal, max_iterations, continuation, mannie]
symptoms: ["max_iterations_reached", "auto.continue", "agent stops mid-task", "任務中途停止", "tool_turns=41", "撞回合上限", "iteration budget exhausted"]
status: active
supersedes: []
related: [0031]
---
# 0032 max-iterations-no-continuation

## §1 撞 max_iterations 後就結束，沒有續跑

**Symptom:** Mannie 跑長任務常中途停止。`agent.log` 量化：160 回合中 21 次
`max_iterations_reached(40/40)`，8/01 17:12–8/02 01:14 連續 12 次全部撞牆、無一次正常收尾；
撞牆行幾乎都是 `tool_turns=41`（工具還在跑就被切）。`grep -c "auto.continue" agent.log` → **0**。
使用者看到的是「產生一段總結、看起來像做完了」，實際任務沒完成。

**Root cause:**
- `agent/conversation_loop.py` 撞上限後只做三件事：設 `_turn_exit_reason`、`_emit_status` 警告、
  呼叫 `_handle_max_iterations`。做完就 return，**沒有任何續跑**。
- `_turn_exit_reason` 其實**有**放進 `run_conversation()` 的回傳 dict（key `turn_exit_reason`），
  但 gateway 的 `_handle_message_with_agent()` 只回傳 `response` 字串，dict 在那層就被丟掉，
  turn-boundary hook 拿不到。（注意：舊 plan 寫「只進 log 不回傳」是不精確的，實際是回傳了但被上層吃掉。）
- 現成的續跑機制是 goal 系統（`gateway/run.py _post_turn_goal_continuation` /
  `cli.py _maybe_continue_goal_after_turn`），但兩邊開頭都是 `if not mgr.is_active(): return`，
  而沒人設 goal → `is_active()` 永遠 False → 續跑從不觸發。
- 另有 3 次 `max_iterations_reached(16/16)` 是 `agent/background_review.py` 硬編
  `max_iterations=16` 的背景 review fork agent，**不是 bug，別動它**。

**副作用陷阱（這條最容易漏，漏了續跑就是空轉）:**
`agent/chat_completion_helpers.py` 的 `handle_max_iterations()` 會往 messages append 一則
**真的 user 訊息**：「You've reached the maximum number of tool-calling iterations allowed.
Please provide a final response ... without calling any more tools.」
這則訊息從此留在對話歷史裡。續跑 prompt 若不明確推翻它，下一輪模型會把它當成仍然生效的指令，
繼續拒絕呼叫工具，續跑等於白跑一輪再總結一次。

## §2 Fix（local patch，5 個檔案，Hermes 升級會覆蓋，須重貼）

全部複用既有 goal 迴圈，**不新增續跑機制**。標記一律 `[local-patch] ... see fixindex 0032-max-iterations-no-continuation`。

**A2-a｜agent/conversation_loop.py（2 處）**
1. `run_conversation()` 裡重建 IterationBudget 那行（`agent.iteration_budget = IterationBudget(agent.max_iterations)`）
   之後，加 `agent._last_turn_hit_max_iterations = False`。跟 budget 同一處重設，語意才對齊。
2. `if final_response is None and (api_call_count >= agent.max_iterations ...)` 區塊內，
   設 `_turn_exit_reason = f"max_iterations_reached(...)"` 那行之後，加
   `agent._last_turn_hit_max_iterations = True`。
- 旗標掛在 agent instance 上，所以 `background_review` 的 fork agent（自己的 AIAgent、
  `max_iterations=16`、從不進 gateway `_agent_cache` 也不是 `cli.self.agent`）只會設到自己那顆，
  **不會誤觸發主 session 的續跑**。

**A2-b｜hermes_cli/goals.py**
- `GoalState` 加兩個欄位（都 default False，舊 state_meta row 照常載入）：
  - `auto_created: bool` — 系統自動建立的 goal，`status_line()` 顯示 `, auto` 與使用者手設區分
  - `last_turn_hit_max_iterations: bool` — 驅動續跑 prompt 的推翻前綴
- `from_json()` 補讀這兩個欄位。
- 新增常數 `AUTO_GOAL_MAX_CHARS = 1200`（goal 文字會進每輪 continuation prompt 和每次 judge，
  貼一大坨 user 訊息不能變成永久 per-turn 稅）。
- 新增常數 `MAX_ITERATIONS_OVERRIDE_PREAMBLE` —— **這是 §1 副作用陷阱的解法**，明確寫
  「上一輪那句『不要再呼叫工具』只適用於那一輪，現已取消，你現在應該繼續呼叫工具」。
- 新增 `GoalManager.note_max_iterations(hit)` — 記錄旗標（對使用者手設的 goal 也要記，
  因為它的回合一樣會撞上限、一樣繼承那句毒指令）。
- 新增 `GoalManager.can_auto_create()` — **這是防無限自我餵食的核心**：
  無 state / done / cleared → 可建；active → 不建（已有迴圈）；
  **paused → 不建**（budget 用盡、judge 連續 parse 失敗、使用者手動暫停都會 paused，
  在這裡重建等於復活剛剛被停掉的迴圈）。
- 新增 `GoalManager.ensure_auto_goal(text, max_turns=None)` — 建 `auto_created=True` 的
  GoalState，budget 取 `default_max_turns`（GoalManager 建構時已從 config `goals.max_turns` 帶入，
  沒有就是 `DEFAULT_MAX_TURNS=20`）。
- `next_continuation_prompt()` 結尾：`if self._state.last_turn_hit_max_iterations:` 就把
  `MAX_ITERATIONS_OVERRIDE_PREAMBLE` 接在原 prompt 前面。
- `status_line()` 四個分支都插入 `auto` 標記。

**A2-c｜gateway/run.py（新增 3 個 method + 掛載點 1 處）**
- 新增 `_session_agent_for_key(session_key)` — 先查 `_running_agents` 再查 `_agent_cache`，
  照 `_handle_usage_command` 既有寫法。turn-boundary hook 跑的時候 agent 已釋放，通常命中 cache。
- 新增 `_first_user_text_for_session(session_id)` — 從 `SessionDB.get_messages()` 取第一則 user 訊息，
  當 event 沒有可用文字（純媒體訊息）時的 goal 文字 fallback。
- 新增 `_maybe_arm_auto_goal_after_max_iterations(session_entry, source, event)` —
  取旗標 → `mgr.note_max_iterations(hit)` → `if not hit or mgr.is_active(): return` →
  `mgr.ensure_auto_goal(goal_text)` → log `auto.continue: armed auto goal ...` → 清掉 agent 旗標。
- 掛載點：`_handle_message()` 裡 `if _final_text.strip():` 之後、`await self._post_turn_goal_continuation(...)`
  **之前**，加 try/except 包住的 `self._maybe_arm_auto_goal_after_max_iterations(...)`。
  順序關鍵：先武裝 goal，緊接著既有 hook 才有 active goal 可續。

**A2-c｜cli.py（新增 1 個 method + 掛載點 1 處）**
- 新增 `_maybe_arm_auto_goal_after_max_iterations(user_input)` — 同上邏輯，
  agent 取 `self.agent`，goal 文字取當輪 `user_input`，fallback 走 `self.conversation_history` 第一則 user 訊息。
- 掛載點：`process_loop` 的 `finally:` 區塊，既有
  `self._maybe_continue_goal_after_turn()` 那段 try/except **之前**插入。

## §3 Verify（實測結果，2026-08-02）

**A. import / AST** — `venv/bin/python -c "import agent.conversation_loop, agent.chat_completion_helpers, gateway.run, hermes_cli.goals"` → OK。

**B. 邏輯層（judge 以 stub 取代，其餘全生產函式，用 `inspect.getsource` 證明被測的是生產碼）:**
- `ensure_auto_goal()` → `status_line()` = `⊙ Goal (active, 0/3 turns, auto): ...`
- `next_continuation_prompt()` 實際輸出含「that instruction applied only to that turn and is now cancelled」
  + 「You SHOULD call tools again now」
- budget 耗盡測試：turn1 continue → turn2 continue → **turn3 `should_continue=False`,
  status=paused, paused_reason=`turn budget exhausted (3/3)`** → 有界
- paused 後 `can_auto_create()` = False、`ensure_auto_goal()` 回 None → 不會復活迴圈
- gateway hook 用真實 `_session_agent_for_key` 跑通，武裝成功且清掉旗標

**C. 真實模型端對端（無 stub：真 AIAgent + 真 free-tools-heavy@127.0.0.1:20130 + 真工具）:**
```
turn_exit_reason : max_iterations_reached(3/3)
A2-a FLAG        : True
tool calls turn1 : ['read_file', 'read_file', 'read_file']
handle_max_iterations 'no more tools' message present: True
Turn ended: reason=max_iterations_reached(3/3) ... tool_turns=3 ... session=a2live_0c38fea2
goal auto-created after max_iterations stop: session=a2live_0c38fea2 budget=3
>>> TOOL CALLS AFTER CONTINUATION: 2   ← 續跑後模型確實還在呼叫 read_file，沒被毒指令卡住
```
副作用推翻有效：續跑後第一則 assistant 訊息（new_msgs index 0）就帶 tool_calls。

**D. 真實迴圈終止（真 judge，無 stub，`goals.max_turns=2`）** — 見 §3 log，
judge 回 `verdict=continue` 續跑，達 budget 後正常 paused，未觸發 harness 的 HARD_STOP。

## §4 重貼流程（升級後 local patch 被蓋掉時）

1. `cd ~/.hermes/hermes-agent && git diff > ~/.hermes/backups/hermes-agent-$(date +%Y%m%d-%H%M%S).diff`
2. 依 §2 逐檔重貼，每處保留 `[local-patch] ... see fixindex 0032-max-iterations-no-continuation` 註解
   —— 這行註解是升級後唯一能找回這些改動的線索。
3. `venv/bin/python -c "import agent.conversation_loop, agent.chat_completion_helpers, gateway.run, hermes_cli.goals"`
4. 重跑 §3 的 B / C 兩組驗證腳本
5. `hermes --profile mannie gateway restart` → **PID 對帳**：`ps -o pid,lstart -p <新pid>`，
   確認 START 時間是剛剛。**不看 `✓ Service restarted` 字樣**（見 0016）。

**受影響檔案清單:**
- `agent/conversation_loop.py`（旗標 set + reset，2 處）
- `hermes_cli/goals.py`（2 常數、2 GoalState 欄位、from_json、status_line、
  note_max_iterations / can_auto_create / ensure_auto_goal、next_continuation_prompt、`__all__`）
- `gateway/run.py`（3 個新 method + `_handle_message` 掛載點）
- `cli.py`（1 個新 method + `process_loop` finally 掛載點）
- 未改但相關：`agent/chat_completion_helpers.py`（`handle_max_iterations` 注入的毒指令來源，
  刻意不動，改用續跑 prompt 推翻，避免影響非續跑路徑的正常收尾行為）

**紅線（本條處理範圍外）:**
- `agent/background_review.py` 的 `max_iterations=16` 是設計如此，不要動
- `~/.hermes/profiles/mannie/config.yaml` 的 `agent.max_turns` / `goals.max_turns` 本輪未改
  （A3 範圍）。本條只**讀** `goals.max_turns`（現值 40）當 auto goal 的 budget。
