#!/usr/bin/env python3
"""fxsync.py — fixindex 單一 git 同步權威（0171/0467 同型復發根治）。

所有 git 同步邏輯收斂於此。bash（fixindex sync_*）、python（fxauto/fxstatus）
一律呼叫本檔，不再各自跑 git。

守衛（集中判斷，不靠各處手動傳 flag）：
  FIXINDEX_NO_SYNC=1      逃生門：pull/push 全停。
  FIXINDEX_SYNC_DEPTH>=2  巢狀呼叫 no-op（消除雙 commit）。最外層命令由
                          fixindex main() export =1；fxauto 反呼內層 subprocess
                          由 child_env() 升到 >=2。

push 失敗分級（依 git stderr 特徵，G/H 解）：
  offline  → 不 die：local commit 保留、寫 $root/.git/fixindex-pending-push、
             WARNING、exit 0（離線可用而不靜默，狀態面負責）
  conflict → die（需人介入 rebase）
  fatal    → die，帶 git 真實 stderr 前 300 字

CLI:
  fxsync.py pull [--soft]                  exit 1 硬 pull 失敗（die）；0 其他
  fxsync.py push [--path P ...] [--msg M]  exit 2 conflict/fatal（die）；0 ok/noop/offline
  fxsync.py state [--json]                 唯讀本地狀態（不碰網路）
  fxsync.py flush                          有 pending marker 就補推
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys

OFFLINE_PATTERNS = [
    re.compile(r'Could not resolve host'),
    re.compile(r'Network is unreachable'),
    re.compile(r'Connection refused'),
    re.compile(r'Operation timed out'),
    re.compile(r"Couldn't connect to server"),
    re.compile(r'Failed to connect'),
    re.compile(r'ssh: connect to host .*? port'),
]
CONFLICT_PATTERNS = [
    re.compile(r'non-fast-forward'),
    re.compile(r'rejected'),
    re.compile(r'fetch first'),
]
CO_AUTHORS = [
    'Claude <noreply@anthropic.com>',
    'Happy <noreply@anthropic.com>',
]
PENDING_MARKER = 'fixindex-pending-push'
PROTECTED_REMOTES_DEFAULT = ['royalskynet/fixindex-log']


# ── helpers ────────────────────────────────────────────────

def strict_dir_guard(fixdir_env=None):
    """B2: FIXINDEX_STRICT_DIR=1 且 FIXINDEX_DIR 未顯式提供 → 回 True（呼叫端 die）。

    單一權威：bash（fixindex）自行 inline 實作；python 兩處（fxstatus/fxauto）都走這。"""
    return os.environ.get('FIXINDEX_STRICT_DIR') == '1' and not fixdir_env

def _real(p):
    return os.path.realpath(os.path.expanduser(str(p)))


def _run(cmd, cwd=None, env=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=60)
        return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()
    except Exception as e:
        return -1, '', str(e)


def _branch(root):
    rc, b, _ = _run(['git', '-C', root, 'symbolic-ref', '--short', '-q', 'HEAD'])
    return b or '?'


def protected_remote_block(root):
    """B3: 測試模式（STRICT_DIR=1 / FIXINDEX_TEST=1）下，remote 命中受保護名單 → 回 fatal dict。

    B1/B2 全繞過、路徑算錯時的最後一道：只要跑在測試模式就打不進 LOG。
    名單可用 FIXINDEX_PROTECTED_REMOTES（逗號分隔）覆寫。"""
    mode = os.environ.get('FIXINDEX_STRICT_DIR') == '1' or os.environ.get('FIXINDEX_TEST') == '1'
    if not mode:
        return None
    rc, url, _ = _run(['git', '-C', root, 'remote', 'get-url', 'origin'])
    if rc != 0 or not url:
        return None
    protect = os.environ.get('FIXINDEX_PROTECTED_REMOTES', ','.join(PROTECTED_REMOTES_DEFAULT))
    for sub in [s.strip() for s in protect.split(',') if s.strip()]:
        if sub in url:
            return {'committed': None, 'pushed': False, 'kind': 'fatal',
                    'detail': f'測試模式禁止寫入受保護 runbook: {url}', 'pending_push': None}
    return None


def _classify(stderr):
    s = stderr or ''
    for p in OFFLINE_PATTERNS:
        if p.search(s):
            return 'offline'
    for p in CONFLICT_PATTERNS:
        if p.search(s):
            return 'conflict'
    return 'fatal'


def _nested_skip():
    """巢狀守衛：FIXINDEX_SYNC_DEPTH >= 2 → 跳過（消除雙 commit）。"""
    try:
        return int(os.environ.get('FIXINDEX_SYNC_DEPTH', '0') or '0') >= 2
    except ValueError:
        return False


def _sync_disabled():
    return os.environ.get('FIXINDEX_NO_SYNC') == '1'


def child_env(base):
    """回傳 env copy，FIXINDEX_SYNC_DEPTH 遞增（供 fxauto 反呼內層 subprocess 消音）。

    雙守衛分工（勿拆任一個，都擋同一問題：一次 fixture 兩次 commit）：
    - FIXINDEX_SYNC_DEPTH（這裡遞增 + fixindex main() export 1）：巢狀
      re-index/supersede 的 pull/push 自動變啞，屬「深度」守衛。
    - FIXINDEX_NO_SYNC=1（fxauto._run_index 設給 bash 子程序）：更嚴 —
      整棵處理樹先停同步，commit/push 統一由 fxauto 結尾單點收，屬「禁用」守衛。
    """
    env = dict(base or {})
    try:
        cur = int(env.get('FIXINDEX_SYNC_DEPTH', '0') or '0')
    except ValueError:
        cur = 0
    env['FIXINDEX_SYNC_DEPTH'] = str(max(cur + 1, 2))
    return env


# ── 公開 API ──────────────────────────────────────────────

def repo_root(fixdir):
    """git rev-parse --show-toplevel；非 repo → None。"""
    rc, out, _ = _run(['git', '-C', _real(fixdir), 'rev-parse', '--show-toplevel'])
    if rc != 0 or not out:
        return None
    return out


def has_upstream(root):
    rc, _, _ = _run(['git', '-C', root, 'rev-parse',
                     '--abbrev-ref', '--symbolic-full-name', '@{u}'])
    return rc == 0


def _write_pending_marker(root, sha, branch):
    try:
        data = {'sha': sha,
                'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'branch': branch}
        with open(os.path.join(root, '.git', PENDING_MARKER), 'w') as f:
            f.write(json.dumps(data, ensure_ascii=False))
    except OSError:
        pass


def _read_pending(root):
    marker = os.path.join(root, '.git', PENDING_MARKER)
    if not os.path.isfile(marker):
        return None
    try:
        with open(marker) as f:
            d = json.load(f)
        return {'sha': d.get('sha'), 'since': d.get('at'), 'branch': d.get('branch')}
    except Exception:
        return {'sha': None, 'since': None, 'branch': None}


def flush_pending(fixdir):
    """有 pending marker 就補推；成功刪 marker。離線/失敗只警告（不 die，補推不該殺寫入）。"""
    root = repo_root(fixdir)
    if not root:
        return {'flushed': False, 'offline': False, 'detail': 'not-a-git-repo', 'marker': None}
    marker = os.path.join(root, '.git', PENDING_MARKER)
    if not os.path.isfile(marker):
        return {'flushed': False, 'offline': False, 'detail': 'no-marker', 'marker': None}
    if not has_upstream(root):
        return {'flushed': False, 'offline': False, 'detail': 'no-upstream', 'marker': marker}
    rc, out, err = _run(['git', '-C', root, 'push'])
    if rc != 0:
        kind = _classify(err or out)
        print(f"fixindex: WARNING — pending 補推失敗（{kind}），marker 保留: "
              f"{(err or out).strip()[:200]}", file=sys.stderr)
        return {'flushed': False, 'offline': kind == 'offline',
                'detail': (err or out)[:300], 'marker': marker}
    try:
        os.remove(marker)
    except OSError:
        pass
    print(f"fixindex: pending 補推完成，marker 已移除（{os.path.basename(marker)}）",
          file=sys.stderr)
    return {'flushed': True, 'offline': False, 'detail': 'flushed', 'marker': None}


def pull(fixdir, soft=False):
    """寫入前 pull-first（含離線積壓補推）。回傳 {ok, skipped, reason, stderr}。

    skipped=True = 不需 sync（no-sync / 巢狀 / 非 git / 無 upstream），非錯誤。
    ok=False = 硬失敗（conflict/fatal），呼叫端應 die。offline 對硬 pull 也不 die
    （離線可寫入本地，由後續 push 累積 pending marker）。"""
    if _sync_disabled() or _nested_skip():
        return {'ok': True, 'skipped': True, 'reason': 'no-sync-or-nested', 'stderr': ''}
    root = repo_root(fixdir)
    if not root:
        return {'ok': True, 'skipped': True, 'reason': 'not-a-git-repo', 'stderr': ''}
    if not has_upstream(root):
        return {'ok': True, 'skipped': True, 'reason': 'no-upstream', 'stderr': ''}
    if not soft:
        flush_pending(fixdir)
    rc, out, err = _run(['git', '-C', root, 'pull', '--rebase', '--autostash'])
    if rc != 0:
        detail = (err or out or 'unknown').strip()[:300]
        kind = _classify(err or out)
        if soft:
            print(f"fixindex: warning — 唯讀 sync pull 失敗，續跑（可能非最新）: {detail}",
                  file=sys.stderr)
            return {'ok': True, 'skipped': False, 'reason': 'soft-pull-fail', 'stderr': detail}
        if kind == 'offline':
            print(f"fixindex: WARNING — sync_pull 離線失敗，續跑（寫入將累積 pending）: {detail}",
                  file=sys.stderr)
            return {'ok': True, 'skipped': False, 'reason': 'offline', 'stderr': detail}
        return {'ok': False, 'skipped': False, 'reason': detail, 'stderr': detail}
    return {'ok': True, 'skipped': False, 'reason': '', 'stderr': ''}


def push(fixdir, paths=None, message=None):
    """paths-scoped 結尾 push（消 0171§2 並發搶檔；空/無效 paths → 不 fallback add -A，Fail Loud）。

    回傳 {committed, pushed, kind, detail, pending_push}。
    kind ∈ skip/noop/ok/offline/conflict/fatal。"""
    if _sync_disabled() or _nested_skip():
        return {'committed': None, 'pushed': False, 'kind': 'skip',
                'detail': 'no-sync-or-nested', 'pending_push': None}
    root = repo_root(fixdir)
    if not root:
        return {'committed': None, 'pushed': False, 'kind': 'noop',
                'detail': 'not-a-git-repo', 'pending_push': None}
    block = protected_remote_block(root)
    if block:
        return block
    if not paths:
        print("fixindex: WARNING — sync_push 未收到任何 path，跳過 commit"
              "（寧可不 commit 也不 add -A 掃別人的檔）", file=sys.stderr)
        return {'committed': None, 'pushed': False, 'kind': 'noop',
                'detail': 'no-paths', 'pending_push': None}
    rroot = _real(root)
    rel, missing = [], []
    for p in paths:
        rp = _real(p)
        if not os.path.exists(rp):
            missing.append(p)
            continue
        if not (rp == rroot or rp.startswith(rroot + os.sep)):
            print(f"fixindex: WARNING — path 不在 repo 內，跳過: {p}", file=sys.stderr)
            continue
        rel.append(os.path.relpath(rp, rroot))
    if not rel:
        detail = 'all-paths-outside-repo' if not missing else 'no-valid-paths: ' + ', '.join(missing)
        return {'committed': None, 'pushed': False, 'kind': 'fatal',
                'detail': detail, 'pending_push': None}
    rc, out, err = _run(['git', '-C', root, 'add', '--'] + rel)
    if rc != 0:
        return {'committed': None, 'pushed': False, 'kind': 'fatal',
                'detail': f'git add: {(err or out).strip()[:200]}', 'pending_push': None}
    rc, _, _ = _run(['git', '-C', root, 'diff', '--cached', '--quiet'])
    if rc == 0:
        return {'committed': None, 'pushed': False, 'kind': 'noop',
                'detail': 'no-changes', 'pending_push': None}
    title = os.path.basename(rel[0]) if rel else 'update'
    cmsg = message or f'fixindex: {title}'
    cm = ['git', '-C', root, 'commit', '-m', cmsg]
    for a in CO_AUTHORS:
        cm += ['-m', f'Co-Authored-By: {a}']
    rc, out, err = _run(cm)
    if rc != 0:
        return {'committed': None, 'pushed': False, 'kind': 'fatal',
                'detail': f'git commit: {(err or out).strip()[:200]}', 'pending_push': None}
    short = 'unknown'
    m = re.search(r'\[[^\]]+ ([0-9a-f]{7,})', out or '')
    if m:
        short = m.group(1)
    if not has_upstream(root):
        return {'committed': short, 'pushed': False, 'kind': 'ok',
                'detail': 'no-upstream', 'pending_push': None}
    rc, out, err = _run(['git', '-C', root, 'push'])
    if rc != 0:
        kind = _classify(err or out)
        detail = (err or out or 'unknown').strip()[:300]
        if kind == 'offline':
            _write_pending_marker(root, short, _branch(root))
            print(f"fixindex: WARNING — push 離線失敗；local commit 已保留，pending marker 已寫"
                  f"（網路恢復後下次寫入自動補推）: {detail}", file=sys.stderr)
            return {'committed': short, 'pushed': False, 'kind': 'offline',
                    'detail': detail, 'pending_push': True}
        return {'committed': short, 'pushed': False, 'kind': kind,
                'detail': detail, 'pending_push': None}
    return {'committed': short, 'pushed': True, 'kind': 'ok',
            'detail': '', 'pending_push': None}


def state(fixdir):
    """唯讀本地狀態（不碰網路）。非 git repo → 完整 schema（解 K）。"""
    s = {'root': None, 'branch': None, 'upstream': None, 'ahead': 0, 'behind': 0,
         'detached': False, 'dirty_files': 0, 'dirty_paths': [], 'pending_push': None,
         'errors': [], 'warnings': []}
    root = repo_root(fixdir)
    if not root:
        s['errors'].append('not a git repo（狀態不可查詢）')
        return s
    s['root'] = root
    s['pending_push'] = _read_pending(root)
    rc, branch, _ = _run(['git', '-C', root, 'symbolic-ref', '--short', '-q', 'HEAD'])
    if rc != 0 or not branch:
        s['detached'] = True
        s['warnings'].append('detached HEAD（不可查 upstream 狀態）')
        return s
    s['branch'] = branch
    rc, up, _ = _run(['git', '-C', root, 'rev-parse',
                      '--abbrev-ref', '--symbolic-full-name', '@{u}'])
    if rc != 0 or not up:
        s['warnings'].append(f"no upstream（branch '{branch}' 無遠端追蹤）")
        return s
    s['upstream'] = up
    rc, ahead, _ = _run(['git', '-C', root, 'rev-list', '--count', '@{u}..HEAD'])
    rc2, behind, _ = _run(['git', '-C', root, 'rev-list', '--count', 'HEAD..@{u}'])
    try:
        s['ahead'] = int(ahead or 0)
    except ValueError:
        s['ahead'] = 0
    try:
        s['behind'] = int(behind or 0)
    except ValueError:
        s['behind'] = 0
    if s['ahead'] > 0:
        s['errors'].append(f"{s['ahead']} unpushed commit(s)（[ahead {s['ahead']}]）")
    if s['behind'] > 0:
        s['errors'].append(f"{s['behind']} remote commit(s) not pulled（[behind {s['behind']}]）")
    rc, porc, _ = _run(['git', '-C', root, 'status', '--porcelain'])
    if rc == 0:
        lines = [l for l in porc.splitlines() if l.strip()]
        s['dirty_files'] = len(lines)
        s['dirty_paths'] = [l[3:].strip() for l in lines][:20]
    if s['dirty_files'] > 0:
        s['warnings'].append(f"{s['dirty_files']} dirty file(s)（未 commit 的工作樹）")
    if s['pending_push']:
        s['errors'].append(f"離線積壓 pending push"
                           f"（{s['pending_push'].get('sha', '?')[:7]}"
                           f"@{s['pending_push'].get('since', '?')}）"
                           f"；網路恢復後下次寫入自動補推")
    return s


# ── CLI ───────────────────────────────────────────────────

def _env_fixdir():
    return os.environ.get('FIXINDEX_DIR') or os.path.join(os.getcwd(), 'fixes')


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    cmd = args[0]
    rest = args[1:]
    fixdir = _env_fixdir()
    if cmd == 'pull':
        res = pull(fixdir, soft='--soft' in rest)
        if not res.get('ok'):
            print(f"fixindex: fxsync pull 失敗（非離線）: {res.get('reason')}", file=sys.stderr)
            return 1
        return 0
    if cmd == 'push':
        paths, message = [], None
        i = 0
        while i < len(rest):
            if rest[i] == '--path' and i + 1 < len(rest):
                paths.append(rest[i + 1])
                i += 2
            elif rest[i] in ('--message', '--msg') and i + 1 < len(rest):
                message = rest[i + 1]
                i += 2
            else:
                i += 1
        res = push(fixdir, paths=paths, message=message)
        if res.get('kind') in ('conflict', 'fatal'):
            print(f"fixindex: sync_push 失敗（{res.get('kind')}）: {res.get('detail')}",
                  file=sys.stderr)
            print("fixindex: 檢查 remote/網路後重試，或 FIXINDEX_NO_SYNC=1 跳過", file=sys.stderr)
            return 2
        if res.get('committed'):
            print(f"sync_push: committed {res.get('committed')}"
                  + (" pushed" if res.get('pushed') else "（未 push）"))
        return 0
    if cmd == 'state':
        s = state(fixdir)
        if '--json' not in rest:
            s = {k: v for k, v in s.items()
                 if k not in ('errors', 'warnings', 'dirty_paths')}
        print(json.dumps(s, ensure_ascii=False))
        return 0
    if cmd == 'flush':
        flush_pending(fixdir)
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())