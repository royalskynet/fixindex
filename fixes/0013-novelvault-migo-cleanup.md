---
id: 0013
slug: novelvault-migo-cleanup
title: TODO
tags: []
symptoms: []
status: active
supersedes: []
related: []
---
# 0013 novelvault-migo-cleanup

## §1 TODO 標題
**Symptom:** `error msg`
**Root cause:** TODO
**Fix:** TODO
**Verify:** TODO
## §1 NovelVault 玄君書：米戈→賽戈斯重命名、蟲族刪除、蜂巢聯邦殘留清理
**Symptom:** 玄君書世界觀中仍殘留「米戈」（舊克蘇魯神話稱呼）、「蟲族」（已廢棄設定）、「蜂巢聯邦」（已廢棄）等過時術語，與新 canon「蓋亞人陰謀、第一次銀河聯盟、賽戈斯先鋒隊」不一致

**Root cause:** 改寫計畫「門外之主蓋亞陰謀重構」雖有日誌記錄，但未完成全局替換；蟲族.md 標記廢案未刪除；四族科技樹、銀河盟約、影子政府等關聯檔仍有舊稱呼

**Fix:** 
1. 新建 `xuanjun/世界觀/賽戈斯.md` — 定義為第一次銀河聯盟核心技術文明、基因工程+靈子協議架構師、異端科學家（宋棠生母）反制線
2. 刪除 `xuanjun/世界觀/米戈.md`、`xuanjun/世界觀/蟲族.md`
3. 13 個核心設定/角色/世界觀檔全局 `米戈` → `賽戈斯`（保留 3 處「前稱米戈」歷史引用）
4. 清理 `蟲族`、`蜂巢聯邦` 殘留引用：設定總表、四族科技樹、銀河盟約、影子政府、跨作品共享宇宙、宋棠.md
5. 追加 `廢案紀錄.md` 蟲族刪除記錄 + 連動變更清單
6. 追加 `_嫙子改寫日誌.md` 14 條改寫記錄
7. git commit `58ae70b` 做 cascade 安全網

**Verify:** 
- `rg "米戈" xuanjun/ --type md | grep -v -E "前稱|原稱|changelog|廢案"` → 零殘留
- `rg "蜂巢聯邦" xuanjun/ --type md | grep -v -E "廢案紀錄|蓋亞人"` → 零殘留
- `rg "蟲族" xuanjun/ --type md | grep -v -E "廢案紀錄|atlantis-imported|官僚蟲族"` → 僅保留 atlantis-imported 舊備份與銀河議會「官僚蟲族」（獨立概念）
- git diff 58ae70b^..58ae70b 確認 16 files changed, 102 insertions(+), 123 deletions(-)

**Retrospective:** 分批 sed 全局替換需注意「前稱/原稱」歷史引用保留，避免誤改 changelog/廢案記錄。先讀全文確認語境再 sed 更稳妥。
