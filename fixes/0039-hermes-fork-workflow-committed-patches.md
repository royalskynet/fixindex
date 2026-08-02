---
id: 0039
slug: hermes-fork-workflow-committed-patches
title: hermes-agent 本地補丁改走 fork + committed patches，終結 autostash 賭博
tags: [hermes, git, fork, rerere, workflow, upstream]
symptoms:
  - 每次 hermes update 都 autostash 一大包未提交改動
  - 上游一更新本地補丁就衝突或消失
  - 本地新增的工具檔（lsp_tool.py 等）不在 git 裡沒有任何保護
  - 想知道 hermes 本地補丁的正確維護方式
---

# 0039 — fork + committed patches 工作流

- **狀態**：done（2026-08-02 遷移完成）
- **關聯**：`0038`（促成本次遷移的事故）

## 1. 機制（hermes 原生支援，寫在源碼裡）

`hermes_cli/update_cmd.py`：`_is_fork()` @1425（只看 origin URL ≠ 官方清單）、`_sync_fork_with_upstream()` @1497、`_sync_with_upstream_if_needed()` @1513。origin 非官方 → updater 走 fork 路徑：自動掛官方為 `upstream` remote、`origin/main` 嚴格落後時自動同步、照樣處理 npm build / gateway 重啟 / 上游檔案搬家。

## 2. 本機現況（2026-08-02 起）

```
repo      ~/.hermes/hermes-agent
origin    git@github.com:royalskynet/hermes-agent-local.git   （私有，SSH）
upstream  https://github.com/NousResearch/hermes-agent.git
HEAD      7c049eb58 = upstream 0a62610f1 + 單一補丁 commit（12 項功能，見 commit body）
rerere    enabled
排除      SOUL.md / USER.md / skills/leisure/ / tinker-atropos/ / *.bak → .git/info/exclude
入版控    tools/lsp_tool.py、tools/calendar_tool.py、plugins/context/、plugins/memory/memtensor/
```

## 3. 更新 SOP

```
git -C ~/.hermes/hermes-agent fetch upstream
git -C ~/.hermes/hermes-agent rebase upstream/main    # 衝突逐 commit 顯式暫停，rerere 重放已解過的
git -C ~/.hermes/hermes-agent push -f origin main     # rebase 後必然要 force；origin 是自己的私有 repo，安全
                                                       # （guard 攔 push --force：屬預期，說明後授權執行）
```

rebase 起衝突時：優先用三方 stage 重建（見 `0038` §2），解完跑補丁回歸測試集（`tests/agent/test_admission_busy.py` 等，Mannie T2 產出）確認補丁全活著。

## 4. 坑

1. **`gh repo create` 的 OAuth token 缺 `workflow` scope** → push 含 `.github/workflows/` 的 repo 被拒。解法：`git remote set-url origin git@github.com:...`（SSH key 不受 scope 限制）。
2. GitHub 公開 repo 的 fork 強制公開。要私有就 `gh repo create <name> --private` + 手動接 remote，`_is_fork` 一樣認得（它只比對 URL）。
3. 個人檔（SOUL.md 等）用 `.git/info/exclude` 不用 `.gitignore` —— 後者本身會進版控、造成與上游的永久 diff。
4. 補丁 commit 訊息要含**功能清單與丟棄清單**：rebase 衝突時這就是「哪邊該贏」的判準。
