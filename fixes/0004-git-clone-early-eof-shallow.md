---
id: "0004"
slug: git-clone-early-eof-shallow
title: git clone 大歷史 repo 反覆 early EOF / .invalid HEAD —— 用 shallow clone 繞過
tags: [git, git-clone, early-eof, rpc-failed, http2-cancel, shallow-clone, depth-1, invalid-head, broken-branch, zombie-process, prophet-protocol]
symptoms:
  - "git clone 報 error: RPC failed; curl 92 HTTP/2 stream was not closed cleanly: CANCEL (err 8)"
  - "git clone 報 fetch-pack: unexpected disconnect while reading sideband packet / fatal: early EOF"
  - "git clone 報 fatal: fetch-pack: invalid index-pack output，clone 中途斷"
  - "clone 後 .git/HEAD = ref: refs/heads/.invalid，git log 報 your current branch appears to be broken"
  - "git show-ref 空、git branch -a 報 failed to resolve HEAD as a valid ref"
  - "ps aux 出現多個殭屍 git clone 進程互搶 .git lock，clone 都不動"
status: active
supersedes: []
related: []
---
# 0004 git-clone-early-eof-shallow

肥大歷史的 GitHub repo（`.git` ~96M，如 `royalskynet/prophet-protocol`）full clone 反覆中途斷線，且 default clone 留下壞掉的 `.invalid` HEAD。只需 main tip 改檔+push 時，用 shallow clone 一招解決。

## §1 full clone 大歷史反覆 early EOF / RPC failed

**Symptom:**
```
error: RPC failed; curl 92 HTTP/2 stream 7 was not closed cleanly: CANCEL (err 8)
error: NNNN bytes of body are still expected
fetch-pack: unexpected disconnect while reading sideband packet
fatal: early EOF
fatal: fetch-pack: invalid index-pack output
```

**Root cause:** repo 歷史肥大（`.git` ~96M，含大 blob），HTTP/2 長傳輸中途被取消，pack 沒收完。

**Fix:** 只要 tip（改檔+push）就用 **shallow clone**，不抓全歷史：
```bash
git clone --depth 1 -b main https://github.com/<owner>/<repo>.git ~/<repo>
```
`.git` 從 ~96M 降到 ~7M，一次成功。**shallow clone 照樣能 commit + push origin main**（push 只送新 commit）。

備選（要全歷史時）：`git config --global http.version HTTP/1.1` 關掉 HTTP/2，或 `git config --global http.postBuffer 524288000`。

## §2 default clone 後 HEAD = refs/heads/.invalid（branch broken）

**Symptom:**
```
$ git log
fatal: your current branch appears to be broken
$ cat .git/HEAD
ref: refs/heads/.invalid
$ git show-ref        # 空，無任何 ref
```
`du -sh .git` 顯示物件其實在（幾十 M），但工作區空、無 refs。

**Root cause:** clone 中途斷（見 §1）時 HEAD 卡在 setup 階段寫的 `.invalid` sentinel，沒走到結尾 checkout；加上該 repo GitHub 端 default HEAD symref 異常。`git remote show origin` 仍能看到 `HEAD branch: main`、`git ls-remote --heads origin` 仍列得出 `refs/heads/main`。

**Fix:** 別在壞 clone 上硬修。直接刪掉重來 + shallow + 明確 `-b main`：
```bash
rm -rf ~/<repo>
git clone --depth 1 -b main <url> ~/<repo>
cat ~/<repo>/.git/HEAD   # 應為 ref: refs/heads/main
```

## §3 多個背景 git clone 殭屍互搶 .git lock

**Symptom:** clone 一直不動；`ps aux | grep "[g]it.*<repo>"` 數出多個（如 6 個）並行 clone/fetch 進程，refs 始終空。

**Root cause:** 反覆重試時開了多個背景 clone/fetch，全指同一 `.git`，互搶 lock 卡死。

**Fix:** 先清殭屍再單線 clone：
```bash
pkill -f "git.*<repo>"
rm -rf ~/<repo>
git clone --depth 1 -b main <url> ~/<repo>   # 單線、前景或單一背景，別並行
```
