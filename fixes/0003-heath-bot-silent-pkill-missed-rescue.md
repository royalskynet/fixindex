---
id: 3
slug: heath-bot-silent-pkill-missed-rescue
title: Heath bot 靜默 20 天 — pkill 廣域 pattern 誤殺後漏救
tags:
- token-401
- session-not-found
- session-store
- heath
- wellally
- tg-bridge
- launchd
- pkill
- fix-0179
symptoms:
- GrammyError 401 Unauthorized getUpdates/getMe/setMyCommands
- Claude: No conversation found with session ID
- bridge.log ELIFED52 exit code 143/1 crash-loop
- launchd state=running but actually crash-looping
- Heath/@healthetherbot 不回話
- bot 靜默數週
- launchctl list 查無服務
- launchctl print health.wellally.tg-bridge → Could not find service
status: active
supersedes: []
related:
- 0179-alice-tg-bridge-409-crash-loop
---

# 0003 heath-bot-silent-pkill-missed-rescue

## §1 Heath bot 靜默 20 天 — pkill 廣域 pattern 誤殺後只救回 Alice

**Symptom:** Heath/@healthetherbot 不回消息；`launchctl print gui/501/health.wellally.tg-bridge` → `Could not find service`；`ps` 全機只有 Alice（cwd=alice-tg-bridge）的 tsx 進程，Heath 零進程；bridge.log 末筆 Jul 9 01:19 `[bridge] starting…` 之後無新紀錄

**Root cause:** fix 0179（Alice 409 crash-loop）第 3 步用 `pkill -f 'wellally-tg-bridge.*src/main.ts'` 一併殺掉 Heath（Heath/Alice 共用同一 wellally-tg-bridge code + node_modules，靠 cwd 區分 token），但收尾只 `launchctl bootstrap` 了 Alice 的 plist，Heath 未載回 → 靜默 ~20 天

**Fix:**
1. `launchctl bootstrap gui/501 health.wellally.tg-bridge.plist` → job 載回，即復活
2. `~/.claude.json` 中 `/Users/51mini/wellally-health` 設 `hasTrustDialogAccepted: true`（Heath 底層 Claude SDK 被 trust dialog 擋住）
3. 修 fix 0179 的危險 pkill pattern 改為 cwd-aware：

```bash
for p in $(pgrep -f 'tsx.*main\.ts'); do
  if [ "$(lsof -a -p $p -d cwd | tail -1 | awk '{print $NF}')" = "/Users/51mini/alice-tg-bridge" ]; then
    kill $p
  fi
done
```

**Verify:**
1. `launchctl print gui/501/health.wellally.tg-bridge` → state=running, PID 穩定
2. `for p in $(pgrep -f 'tsx.*main\.ts'); do echo -n "$p "; lsof -a -p $p -d cwd | tail -1 | awk '{print $NF}'; done` → 兩隻 bot：alice-tg-bridge + wellally-tg-bridge
3. `curl "https://api.telegram.org/bot<TOKEN>/getMe"` → ok:true
4. `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` → url:"" (no webhook conflict)
5. Telegram 端對 @healthetherbot 發訊息有回覆
6. `~/.claude.json` 中 wellally-health 的 hasTrustDialogAccepted=true

**Retrospective:**
- 共用 code 的多 instance（Heath/Alice）用 pkill 廣域 pattern 是定時炸彈，應永遠用 cwd-aware pattern 兜底
- launchd domain check → `launchctl print` 非 0 比看 exit code 更能抓「根本不在 domain」的 case
- Claude SDK bot 的工作區 trust 設定也會讓 bridge 卡住不回應

## §2 Token 401 + Session not found — 雙重故障致 crash-loop

**Symptom:** `bridge.error.log` 重複 `GrammyError: Call to 'getUpdates' failed! (401: Unauthorized)` + `getMe` 401 + `setMyCommands` 401；`bridge.log` 顯示多次 `ELIFECYCLE Command failed with exit code 143/1`，每次重啟立即 crash；launchd 顯示 `state=running` 但因 KeepAlive 反覆重啟不易察覺；用戶發訊息時 Claude 回報 `No conversation found with session ID: fe78e0ae-d20d-4b33-be3d-b49ef549ab0e`

**Root cause:** 兩層疊加：(1) Telegram bot token 失效，grammy 所有 API 呼叫 401；(2) `data/sessions/7852197786.json` 存的 sessionId `fe78e0ae` 在 Claude 端已被清理，bridge 每次 `--resume` 都傳不存在的 session

**Fix:**
1. `.env` → 換新 `TELEGRAM_BOT_TOKEN=8288581464:AAEJZUtwi_ya3Izn-ChPuCsaH43naInVGsI`
2. 清 session：`echo '{"sessionId":null,"updatedAt":"..."}' > data/sessions/7852197786.json`
3. `launchctl bootout gui/501/health.wellally.tg-bridge` → `launchctl bootstrap gui/501 ~/Library/LaunchAgents/health.wellally.tg-bridge.plist`

**Verify:**
- `curl "https://api.telegram.org/bot<TOKEN>/getMe"` → ok:true, `first_name: Heath希思`
- `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` → url:""，無 webhook 衝突
- `ps -o etime=,pid= -p $pid` → 存活 >2 分鐘無 crash
- `bridge.error.log` 不再增長

**Retrospective:**
- Bot 401 crash-loop 很難從 launchd `state=running` 發現，依靠 `bridge.error.log` 時間戳判斷是否新錯誤
- Session not found 原因：session store 不感知 Claude 端 session 存活狀態，應考慮在 runner 層 catch `No conversation found` 錯誤後自動清 session 重試
