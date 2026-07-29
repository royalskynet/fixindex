---
id: 3
slug: heath-bot-silent-pkill-missed-rescue
title: Heath bot 靜默 20 天 — pkill 廣域 pattern 誤殺後漏救
tags:
- heath
- wellally
- tg-bridge
- launchd
- pkill
- fix-0179
symptoms:
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
