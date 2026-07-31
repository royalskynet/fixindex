---
id: 0018
slug: launchctl-bootstrap-race
title: launchctl bootout 後立即 bootstrap 發生 race
tags: [macos, launchctl, launchagent, hermes]
symptoms: ["Bootstrap failed: 5: Input/output error", "Could not find service in domain for user gui"]
status: active
supersedes: []
related: []
---
# 0018 launchctl-bootstrap-race

## §1 bootout 後立即 bootstrap 回 Input/output error
**Symptom:** `launchctl bootout gui/$(id -u)/<label>` 成功後，緊接著 `launchctl bootstrap gui/$(id -u) <plist>` 回 `Bootstrap failed: 5: Input/output error`；此時 `launchctl print` 可能短暫查無服務。
**Root cause:** launchd 尚未完成舊 job 的非同步移除，立即以相同 label bootstrap 形成短暫 race；plist 本身可通過 `plutil -lint`。
**Fix:** 先用 `launchctl print gui/$(id -u)/<label>` 確認舊 job 已消失，等待數秒後再執行同一 `bootstrap`。不要因 error 5 立即改 plist 或使用 root。
**Verify:** `launchctl bootstrap` exit 0；`launchctl print gui/$(id -u)/<label>` 顯示 `state = running` 與新 PID；服務 log 顯示 adapter connected。
**Retrospective:** 涉及 live LaunchAgent reload 時，把「確認 label 消失」納入 bootout/bootstrap 間的固定 gate。
