#!/usr/bin/env python3
"""
fxauto.py — shadow-mode fixindex entry generator with de-individuation.
Usage: echo '...' | fxauto.py --shadow       (preview + dedup check)
       echo '...' | fxauto.py --commit       (write/supersede + re-index)
Input: lines in KEY: value format (SYMPTOM, ROOT, FIX, VERIFY)

去個案化 (借鏡 claude-mem-lite auto-dedup / supersede):
  - 建檔前先比對既有條目標題, 新經驗關鍵詞 (tgt ⊆ ts) 判定為重複經驗
  - 重複時取代舊條目 (保留線索, 少走彎路)
"""

import sys, os, json, re, subprocess, glob as _glob
import fxmeta

FIXINDEX_DIR = os.environ.get('FIXINDEX_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixes'))

# 去個案化：同主題（新舊 tgt⊆ts 或 overlap >= 門檻）即視為重複經驗
OVERLAP_THRESHOLD = 0.6


def next_id():
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    if not files:
        return '0001'
    last = os.path.basename(files[-1])[:4]
    return f'{int(last) + 1:04d}'


def slugify(text):
    import unicodedata
    s = unicodedata.normalize('NFKD', text.lower())
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]


def _title_tokens(text):
    """Split title into tokens (reuse fxsearch.tokenize for CJK awareness)."""
    try:
        import fxsearch
        return set(fxsearch.tokenize(text))
    except Exception:
        norm = re.sub(r'[\s，。,.!?、:：;；()（）\[\]{}"\'`~\-—]+', '', text.lower())
        return {norm}


def find_duplicate(title, etype='defect'):
    """Return (fid, overlap_ratio) if an existing title contains ALL tokens of
    the new title (tgt ⊆ ts) or shares >= OVERLAP_THRESHOLD of the existing
    title's tokens (同主題含新語彙 → still supersede).

    Dedup 直覺（對齊 '不記個案'）：新經驗的關鍵詞若都已在某舊條目標題出現過
    （tgt ⊆ ts），或新標題涵蓋舊標題 >= OVERLAP_THRESHOLD 比例的關鍵詞，
    視為重複經驗, 回傳舊條目供 supersede 取代。
    """
    import glob as _glob
    files = sorted(_glob.glob(os.path.join(FIXINDEX_DIR, '[0-9]*.md')))
    tgt = _title_tokens(title)
    if not tgt:
        return None
    best = None
    for fp in files:
        try:
            with open(fp) as f:
                txt = f.read()
        except Exception:
            continue
        fm, _ = fxmeta.parse_frontmatter_full(txt)
        # 同型過濾：insight 與 defect 不互相 supersede（預設 defect）
        if str(fm.get('type') or 'defect') != etype:
            continue
        t = fm.get('title') or os.path.basename(fp)
        ts = _title_tokens(str(t))
        if not ts:
            continue
        if tgt <= ts or (len(tgt & ts) / len(ts) >= OVERLAP_THRESHOLD):
            overlap = len(tgt & ts) / len(ts)   # 新詞涵蓋舊標題比例
            if best is None or overlap > best[1]:
                best = (os.path.basename(fp)[:4], round(overlap, 2))
    return best


def build_entry(fid, title, symptoms, root, fix, verify, slug, tags=None, detail=''):
    parts = []
    parts.append('---')
    parts.append(f'id: {fid}')
    parts.append(f'slug: {slug}')
    parts.append(f'title: {title}')
    tag_items = ['auto', 'shadow'] + (tags or [])
    parts.append('tags:\n' + '\n'.join(f'  - {t}' for t in tag_items))
    parts.append('symptoms:')
    for s in symptoms:
        parts.append(f'  - {s}')
    parts.append('status: active')
    parts.append('supersedes: []')
    parts.append('related: []')
    parts.append('---')
    parts.append('')
    parts.append(f'# {fid} {title}')
    parts.append('')
    parts.append('## §1 Symptom')
    parts.append('')
    parts.append('; '.join(symptoms))
    parts.append('')
    parts.append('## §2 Root cause')
    parts.append('')
    parts.append(root)
    parts.append('')
    parts.append('## §3 Fix')
    parts.append('')
    parts.append(fix)
    parts.append('')
    parts.append('## §4 Verify')
    parts.append('')
    parts.append(verify)
    if detail:
        parts.append('')
        parts.append('## §5 詳情')
        parts.append('')
        parts.append(detail)
    return '\n'.join(parts) + '\n'


def _resolve_index_file():
    """FIXINDEX_INDEX 取值：環境早已由呼叫者 export 鎖定者，僅當它與
    FIXINDEX_DIR 同庫（dirname 相同）才沿用，否則一律改算到
    <FIXINDEX_DIR 的上層>/FIX-INDEX.md，防止 shell 全域殘留的 FIXINDEX_INDEX
    把 sandbox re-index 寫進真實庫。"""
    env_index = os.environ.get('FIXINDEX_INDEX')
    if env_index and os.path.dirname(os.path.abspath(env_index)) == os.path.dirname(os.path.abspath(FIXINDEX_DIR)):
        return env_index
    return os.path.join(os.path.dirname(FIXINDEX_DIR), 'FIX-INDEX.md')


def _run_index(cmd, *args):
    """Run a fixindex subcommand bound to THIS FIXINDEX_DIR and its index file
    (so sandbox tests don't leak into the real library). Uses the fixindex
    next to this file. list-arg subprocess（路徑帶空格不炸）。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixindex')
    if not os.path.exists(script):
        script = 'fixindex'  # fall back to PATH
    env = dict(os.environ)
    env['FIXINDEX_DIR'] = FIXINDEX_DIR
    env['FIXINDEX_INDEX'] = _resolve_index_file()
    quiet = not cmd.startswith('re-index')
    if cmd == 're-index':
        return subprocess.run([script] + cmd.split(' ') + list(args), env=env)
    if quiet:
        return subprocess.run([script] + cmd.split(' ') + list(args), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run([script] + cmd.split(' ') + list(args), env=env)


def _git_commit_push(paths):
    """If FIXINDEX_DIR sits inside a git repo, add the given paths, commit with
    a fixindex message, and push. Returns a dict reflecting reality
    (宣告≠生效): committed=<short hash>|None, pushed=bool, git_error=<str>|None.
    All git calls use list-arg subprocess (no shell, no '>' redirect chars).
    Raises RuntimeError on commit/add failure (so caller can set exit code)."""
    try:
        r = subprocess.run(
            ['git', '-C', FIXINDEX_DIR, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True)
    except Exception as e:
        return {'committed': None, 'pushed': False, 'git_error': f'git unavailable: {e}'}
    repo = (r.stdout or '').strip()
    if r.returncode != 0 or not repo:
        # 不在 git repo（sandbox）→ 不算錯誤
        return {'committed': None, 'pushed': False, 'git_error': None}

    # macOS /tmp → /private/tmp symlink：統一用 realpath 比對與算相對路徑
    fixdir_real = os.path.realpath(FIXINDEX_DIR)
    if not os.path.realpath(fixdir_real).startswith(os.path.realpath(repo) + os.sep):
        return {'committed': None, 'pushed': False, 'git_error': None}

    rel = []
    for p in paths:
        rp = os.path.realpath(p)
        if os.path.exists(rp):
            rel.append(os.path.relpath(rp, os.path.realpath(repo)))
    add = subprocess.run(['git', '-C', repo, 'add', '--'] + rel,
                         capture_output=True, text=True)
    if add.returncode != 0:
        return {'committed': None, 'pushed': False,
                'git_error': f'git add: {(add.stderr or add.stdout).strip()[:200]}'}
    # commit only if there are staged changes
    diff = subprocess.run(['git', '-C', repo, 'diff', '--cached', '--quiet'],
                          capture_output=True, text=True)
    if diff.returncode == 0:
        return {'committed': None, 'pushed': False, 'git_error': None}  # 無變動
    title = os.path.basename(paths[0]) if paths else 'update'
    cmsg = f"fixindex: {title}"
    cm = subprocess.run(['git', '-C', repo, 'commit', '-m', cmsg],
                        capture_output=True, text=True)
    if cm.returncode != 0:
        return {'committed': None, 'pushed': False,
                'git_error': f'git commit: {(cm.stderr or cm.stdout).strip()[:200]}'}
    short = 'unknown'
    m = re.search(r'\[[^\]]+ ([0-9a-f]{7,})', cm.stdout or '')
    if m:
        short = m.group(1)
    push = subprocess.run(['git', '-C', repo, 'push'],
                          capture_output=True, text=True)
    if push.returncode != 0:
        return {'committed': short, 'pushed': False,
                'git_error': f'git push: {(push.stderr or push.stdout).strip()[:200]}'}
    return {'committed': short, 'pushed': True, 'git_error': None}


def main():
    args = sys.argv[1:]
    mode = None
    title_override = None
    symptom_arg = None
    fix_arg = None
    tags_arg = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--title' and i + 1 < len(args):
            title_override = args[i + 1]
            i += 1
        elif a == '--symptom' and i + 1 < len(args):
            symptom_arg = args[i + 1]
            i += 1
        elif a == '--fix' and i + 1 < len(args):
            fix_arg = args[i + 1]
            i += 1
        elif a == '--tags' and i + 1 < len(args):
            tags_arg = args[i + 1]
            i += 1
        elif a in ('--shadow', '--commit'):
            mode = a
        i += 1
    if not mode:
        print("usage: fxauto.py [--shadow|--commit] [--title T] [--symptom S] [--fix F] [--tags T]", file=sys.stderr)
        sys.exit(1)

    fields = {}
    # flags 是最高優先 baseline
    if symptom_arg:
        fields['symptom'] = symptom_arg
    if fix_arg:
        fields['fix'] = fix_arg
    # D2: stdin 一律讀（即使 flags 齊也不再靜默跳過）：
    #   - KEY 行（SYMPTOM/ROOT/FIX/VERIFY）補進 flags 沒給的欄位
    #   - 非 KEY 行整段保留 → §5 詳情（實測數據/無效嘗試落點）
    detail_lines = []
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ''
    for raw in stdin_text.splitlines():
        st = raw.strip()
        m = re.match(r'^([A-Z]+):\s*(.+)', st)
        if m and m.group(1).lower() in ('symptom', 'root', 'fix', 'verify'):
            fields.setdefault(m.group(1).lower(), m.group(2).strip())
        elif st:
            detail_lines.append(raw)
    detail = '\n'.join(detail_lines)

    sympt = fields.get('symptom', '')
    root = fields.get('root', 'untraced')
    fix = fields.get('fix', 'applied')
    verify = fields.get('verify', 'verified')

    if not sympt:
        print(
            "SYMPTOM required — stdin expects KEY: value lines. Minimal example:\n"
            "  echo 'SYMPTOM: web PUT /soul crashes on NUL path\n"
            "ROOT: os.open raises ValueError, only OSError caught\n"
            "FIX: catch (OSError, ValueError)\n"
            "VERIFY: pytest tests/x.py -q -> N passed' | fixindex auto --tags a,b\n"
            "(or pass --symptom/--fix/--tags flags without stdin)",
            file=sys.stderr,
        )
        sys.exit(1)

    symps = [s.strip() for s in sympt.split(';') if s.strip()]
    if not symps:
        symps = [sympt.strip()]

    # tags：--tags 透傳（逗號/空白分隔），或留 default auto/shadow
    if tags_arg:
        tags = [t.strip() for t in re.split(r'[,，\s]+', tags_arg) if t.strip()]
    else:
        tags = []

    title = (title_override or symps[0])[:80]
    dup = find_duplicate(title)

    if mode == '--shadow':
        payload = {'preview_lines': len(build_entry(next_id(), title, symps, root, fix, verify, '', tags).split('\n'))}
        if dup:
            payload['dedup'] = {'supersedes': dup[0], 'overlap': round(dup[1], 2)}
        else:
            payload['dedup'] = None
        print(json.dumps(payload))
        return

    if dup:
        # 去個案化：取代舊條目, 不創重複檔
        old_id = dup[0]
        new_id = next_id()
        slug = slugify(title)
        entry = build_entry(new_id, title, symps, root, fix, verify, slug, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        old_path = os.path.join(FIXINDEX_DIR, f'{old_id}-*.md')
        import glob as _g
        old_files = sorted(_g.glob(old_path))
        path = os.path.join(FIXINDEX_DIR, f'{new_id}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _run_index(f'supersede {old_id} {new_id}')
        payload = {'created': path, 'dedup': True, 'supersedes': old_id}
        git_paths = [path, _resolve_index_file()] + old_files
        payload.update(_git_commit_push(git_paths))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return
    else:
        fid = next_id()
        slug = slugify(title)
        entry = build_entry(fid, title, symps, root, fix, verify, slug, tags, detail)
        os.makedirs(FIXINDEX_DIR, exist_ok=True)
        path = os.path.join(FIXINDEX_DIR, f'{fid}-{slug}.md')
        with open(path, 'w') as f:
            f.write(entry)
        _run_index('re-index')
        payload = {'created': path, 'dedup': False}
        payload.update(_git_commit_push([path, _resolve_index_file()]))
        print(json.dumps(payload))
        if payload.get('git_error'):
            sys.exit(1)
        return


if __name__ == '__main__':
    main()