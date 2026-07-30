---
id: 0006
slug: mini-power-failure-vdd-boost-uvlo
title: Mini 突然斷電重啟 — 供電壓降 UVLO
symptoms:
  - Mac mini 無預警斷電後自動重啟
  - 無 kernel panic 日誌
  - 啟動後服務正常
  - ResetCounter Boot faults 顯示 uv / vdd_boost_uvlo
date: 2026-07-30
---

## 症狀

設備突然無預警斷電，約 26 分鐘後自動重啟。無 kernel panic、無 shutdown 日誌、服務（OmniRoute、strip-proxy）透過 launchd 自動恢復。

## 診斷

```bash
# 查 ResetCounter 診斷（關鍵）
ls /Library/Logs/DiagnosticReports/ResetCounter-*.diag
cat /Library/Logs/DiagnosticReports/ResetCounter-2026-07-30-081344.diag
```

關鍵行：

```
Boot faults: uv,vdd_boost_uvlo rst sgpio target_off_restart
```

`vdd_boost_uvlo` = 供電回路電壓不足，觸發 SMC 強制斷電保護硬體。
`target_off_restart` = SMC 在電壓恢復後自動嘗試重啟。

## 根因

硬體層級供電問題（非軟體）：
- 台電瞬間壓降／瞬斷（夏季用電高峰最常見）
- Mini 電源供應器輸入端不穩
- 排插總負載過高

## 修復

硬體層無軟體可修。建議：
1. 確認電源線、排插穩固
2. 考慮加小型 UPS 擋瞬間壓降

## 相關

無 kernel panic → 不是系統崩潰
無 shutdown 日誌 → 不是正常關機程序
boot-breadcrumbs 可見正常開機序列 → 硬體供電瞬間掉電後恢復

